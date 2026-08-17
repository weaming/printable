#define _POSIX_C_SOURCE 200809L

#include "column_wrapper.h"

#include <errno.h>
#include <pthread.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#if !defined(__APPLE__) && !defined(__linux__)
#error "column wrapper supports macOS and Linux only"
#endif

#define HAS_FEATURE_ADDRESS_SANITIZER 1
#define main column_main
#define exit column_exit
#define err column_err
#define errx column_errx

static _Thread_local jmp_buf *column_active_jump;
static _Thread_local int column_active_exit_code;
static pthread_mutex_t column_render_mutex = PTHREAD_MUTEX_INITIALIZER;

static void column_exit(int status) __attribute__((noreturn));
static void column_err(int status, const char *format, ...) __attribute__((noreturn));
static void column_errx(int status, const char *format, ...) __attribute__((noreturn));

#include "../util-linux/text-utils/column.c"

#undef main
#undef exit
#undef err
#undef errx

static int duplicate_descriptor(int descriptor)
{
	int duplicate = dup(descriptor);

	return duplicate >= 0 ? duplicate : -1;
}

static void close_descriptor(int *descriptor)
{
	if (*descriptor >= 0) {
		close(*descriptor);
		*descriptor = -1;
	}
}

static int read_stream(FILE *stream, char **data, size_t *data_size)
{
	long stream_size;
	size_t bytes_read;
	char *buffer;

	if (fseek(stream, 0, SEEK_END) != 0) {
		return -1;
	}

	stream_size = ftell(stream);
	if (stream_size < 0 || fseek(stream, 0, SEEK_SET) != 0) {
		return -1;
	}

	buffer = calloc((size_t)stream_size + 1, sizeof(*buffer));
	if (buffer == NULL) {
		return -1;
	}

	bytes_read = fread(buffer, 1, (size_t)stream_size, stream);
	if (bytes_read != (size_t)stream_size && ferror(stream)) {
		free(buffer);
		return -1;
	}

	*data = buffer;
	*data_size = bytes_read;
	return 0;
}

static int write_input(FILE *stream, const char *input, size_t input_size)
{
	size_t bytes_written;

	if (input_size == 0) {
		return 0;
	}

	bytes_written = fwrite(input, 1, input_size, stream);
	if (bytes_written != input_size || fflush(stream) != 0) {
		return -1;
	}

	return fseek(stream, 0, SEEK_SET);
}

static char *make_option_argument(const struct column_option *option)
{
	const char *name;
	const char *prefix = "--";
	size_t name_offset;
	size_t name_size;
	size_t value_size;
	size_t argument_size;
	char *argument;

	if (option == NULL || option->name == NULL ||
		(option->has_value && option->value == NULL)) {
		errno = EINVAL;
		return NULL;
	}

	name = option->name;
	name_offset = strncmp(name, prefix, 2) == 0 ? 0 : 2;
	name_size = strlen(name);
	value_size = option->has_value ? strlen(option->value) : 0;
	argument_size = name_size + name_offset + 1;

	argument_size += option->has_value ? 1 + value_size : 0;
	argument = calloc(argument_size, sizeof(*argument));
	if (argument == NULL) {
		return NULL;
	}

	if (name_offset == 0) {
		memcpy(argument, name, name_size);
	} else {
		memcpy(argument, prefix, 2);
		memcpy(argument + 2, name, name_size);
	}

	if (option->has_value) {
		argument[name_offset + name_size] = '=';
		memcpy(argument + name_offset + name_size + 1, option->value, value_size);
	}

	return argument;
}

static char **make_argv(
	const struct column_options *options,
	size_t *argument_count)
{
	size_t allocated_count = 1;
	size_t option_index;
	size_t argument_index = 1;
	char **arguments;

	if (options == NULL) {
		options = &(struct column_options) {0};
	}
	if (options->item_count > 0 && options->items == NULL) {
		errno = EINVAL;
		return NULL;
	}
	if (options->input_file_count > 0 && options->input_files == NULL) {
		errno = EINVAL;
		return NULL;
	}

	allocated_count += options->item_count + options->input_file_count;
	arguments = calloc(allocated_count + 1, sizeof(*arguments));
	if (arguments == NULL) {
		return NULL;
	}
	arguments[0] = strdup("column");
	if (arguments[0] == NULL) {
		free(arguments);
		return NULL;
	}

	for (option_index = 0; option_index < options->item_count; option_index++) {
		arguments[argument_index] = make_option_argument(&options->items[option_index]);
		if (arguments[argument_index] == NULL) {
			for (size_t index = 0; index < argument_index; index++) {
				free(arguments[index]);
			}
			free(arguments);
			return NULL;
		}
		argument_index++;
	}

	for (option_index = 0; option_index < options->input_file_count; option_index++) {
		if (options->input_files[option_index] == NULL) {
			errno = EINVAL;
			for (size_t index = 0; index <= options->item_count; index++) {
				free(arguments[index]);
			}
			free(arguments);
			return NULL;
		}
		arguments[argument_index++] = (char *)options->input_files[option_index];
	}

	*argument_count = argument_index;
	return arguments;
}

static void free_argv(char **arguments, size_t option_count)
{
	if (arguments == NULL) {
		return;
	}

	for (size_t index = 0; index <= option_count; index++) {
		free(arguments[index]);
	}
	free(arguments);
}

static int save_standard_descriptors(int descriptors[3])
{
	for (int index = 0; index < 3; index++) {
		descriptors[index] = duplicate_descriptor(index);
		if (descriptors[index] < 0) {
			for (int restore_index = 0; restore_index < index; restore_index++) {
				close_descriptor(&descriptors[restore_index]);
			}
			return -1;
		}
	}

	return 0;
}

static int redirect_standard_descriptors(FILE *input, FILE *output, FILE *error)
{
	if (dup2(fileno(input), STDIN_FILENO) < 0 ||
		dup2(fileno(output), STDOUT_FILENO) < 0 ||
		dup2(fileno(error), STDERR_FILENO) < 0) {
		return -1;
	}

	clearerr(stdin);
	clearerr(stdout);
	clearerr(stderr);
	return 0;
}

static int restore_standard_descriptors(int descriptors[3])
{
	int result = 0;

	fflush(NULL);
	for (int index = 0; index < 3; index++) {
		if (dup2(descriptors[index], index) < 0) {
			result = -1;
		}
		close_descriptor(&descriptors[index]);
	}
	clearerr(stdin);
	clearerr(stdout);
	clearerr(stderr);
	return result;
}

static void write_error_message(const char *format, va_list arguments)
{
	vfprintf(stderr, format, arguments);
	fputc('\n', stderr);
}

static void column_exit(int status)
{
	if (column_active_jump != NULL) {
		column_active_exit_code = status;
		longjmp(*column_active_jump, 1);
	}

	_Exit(status);
}

static void column_err(int status, const char *format, ...)
{
	va_list arguments;

	va_start(arguments, format);
	write_error_message(format, arguments);
	va_end(arguments);
	column_exit(status);
}

static void column_errx(int status, const char *format, ...)
{
	va_list arguments;

	va_start(arguments, format);
	write_error_message(format, arguments);
	va_end(arguments);
	column_exit(status);
}

static int run_column_main(
	char **arguments,
	size_t argument_count,
	FILE *input,
	FILE *output,
	FILE *error)
{
	int descriptors[3] = {-1, -1, -1};
	int exit_code = EXIT_FAILURE;
	jmp_buf jump_buffer;

	if (save_standard_descriptors(descriptors) != 0) {
		return -1;
	}
	if (redirect_standard_descriptors(input, output, error) != 0) {
		restore_standard_descriptors(descriptors);
		return -1;
	}

	optind = 1;
#ifdef __APPLE__
	optreset = 1;
#endif
	column_active_jump = &jump_buffer;
	if (setjmp(jump_buffer) == 0) {
		exit_code = column_main((int)argument_count, arguments);
	} else {
		exit_code = column_active_exit_code;
	}
	column_active_jump = NULL;

	if (restore_standard_descriptors(descriptors) != 0) {
		return -1;
	}

	return exit_code;
}

int column_render(
	const char *input,
	size_t input_size,
	const struct column_options *options,
	struct column_result *result)
{
	FILE *input_file = NULL;
	FILE *output_file = NULL;
	FILE *error_file = NULL;
	char **arguments = NULL;
	size_t argument_count = 0;
	int exit_code;

	if (result == NULL || (input_size > 0 && input == NULL)) {
		errno = EINVAL;
		return -1;
	}

	memset(result, 0, sizeof(*result));
	if (pthread_mutex_lock(&column_render_mutex) != 0) {
		errno = EBUSY;
		return -1;
	}

	input_file = tmpfile();
	output_file = tmpfile();
	error_file = tmpfile();
	if (input_file == NULL || output_file == NULL || error_file == NULL) {
		if (errno == 0) {
			errno = EIO;
		}
		goto fail;
	}

	if (write_input(input_file, input, input_size) != 0) {
		goto fail;
	}

	arguments = make_argv(options, &argument_count);
	if (arguments == NULL) {
		goto fail;
	}

	exit_code = run_column_main(arguments, argument_count, input_file, output_file, error_file);
	if (exit_code < 0 || read_stream(output_file, &result->output, &result->output_size) != 0 ||
		read_stream(error_file, &result->error, &result->error_size) != 0) {
		goto fail;
	}
	result->exit_code = exit_code;

	free_argv(arguments, options ? options->item_count : 0);
	fclose(input_file);
	fclose(output_file);
	fclose(error_file);
	pthread_mutex_unlock(&column_render_mutex);
	return 0;

fail:
	free_argv(arguments, options ? options->item_count : 0);
	if (input_file != NULL) {
		fclose(input_file);
	}
	if (output_file != NULL) {
		fclose(output_file);
	}
	if (error_file != NULL) {
		fclose(error_file);
	}
	column_result_free(result);
	pthread_mutex_unlock(&column_render_mutex);
	return -1;
}

void column_result_free(struct column_result *result)
{
	if (result == NULL) {
		return;
	}

	free(result->output);
	free(result->error);
	memset(result, 0, sizeof(*result));
}
