#ifndef COLUMN_WRAPPER_H
#define COLUMN_WRAPPER_H

#include <stddef.h>

#if defined(__APPLE__) || defined(__linux__)
#define COLUMN_API __attribute__((visibility("default")))
#else
#error "column wrapper supports macOS and Linux only"
#endif

struct column_option {
	const char *name;
	const char *value;
	int has_value;
};

struct column_options {
	const struct column_option *items;
	size_t item_count;
	const char *const *input_files;
	size_t input_file_count;
};

struct column_result {
	char *output;
	size_t output_size;
	char *error;
	size_t error_size;
	int exit_code;
};

COLUMN_API int column_render(
	const char *input,
	size_t input_size,
	const struct column_options *options,
	struct column_result *result);

COLUMN_API void column_result_free(struct column_result *result);

#endif
