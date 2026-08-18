import ctypes
import os
import platform
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias


ColumnOptionItem: TypeAlias = 'ColumnOption | tuple[str, str | None]'
ColumnInput: TypeAlias = str | bytes


class ColumnExecutionError(RuntimeError):
    """column 命令执行失败。"""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(f'column 执行失败，退出码 {exit_code}: {message}')
        self.exit_code = exit_code
        self.message = message


@dataclass(frozen=True)
class ColumnOption:
    """描述一个 util-linux column 长选项。"""

    name: str
    value: str | None = None


@dataclass(frozen=True)
class ColumnOptions:
    """描述 column 的选项和输入文件。"""

    items: Sequence[ColumnOptionItem] = ()
    input_files: Sequence[str] = ()


class _ColumnOption(ctypes.Structure):
    _fields_ = [
        ('name', ctypes.c_char_p),
        ('value', ctypes.c_char_p),
        ('has_value', ctypes.c_int),
    ]


class _ColumnOptions(ctypes.Structure):
    _fields_ = [
        ('items', ctypes.POINTER(_ColumnOption)),
        ('item_count', ctypes.c_size_t),
        ('input_files', ctypes.POINTER(ctypes.c_char_p)),
        ('input_file_count', ctypes.c_size_t),
    ]


class _ColumnResult(ctypes.Structure):
    _fields_ = [
        ('output', ctypes.c_void_p),
        ('output_size', ctypes.c_size_t),
        ('error', ctypes.c_void_p),
        ('error_size', ctypes.c_size_t),
        ('exit_code', ctypes.c_int),
    ]


def _target_name() -> str:
    """返回当前 Python 进程对应的 native 构建目录名。"""
    if sys.platform == 'darwin':
        platform_name = 'macos'
    elif sys.platform.startswith('linux'):
        platform_name = 'linux'
    else:
        raise RuntimeError('column native wrapper 仅支持 macOS 和 Linux')

    architecture = platform.machine().lower()
    architecture = {'amd64': 'x86_64', 'aarch64': 'aarch64'}.get(architecture, architecture)
    return f'{platform_name}-{architecture}'


def _load_library() -> ctypes.CDLL:
    """加载本地 column 动态库并配置 ctypes 签名。"""
    library_override = os.getenv('COLUMN_LIBRARY')
    if library_override:
        library_paths = (Path(library_override),)
    else:
        library_suffix = '.dylib' if sys.platform == 'darwin' else '.so'
        library_name = f'libcolumn{library_suffix}'
        target_name = _target_name()
        package_library = Path(__file__).resolve().parent / 'lib' / target_name / library_name
        development_library = Path(__file__).resolve().parents[2] / 'build' / 'native' / target_name / library_name
        library_paths = (package_library, development_library)

    library_path = next((path for path in library_paths if path.is_file()), library_paths[0])

    if not library_path.is_file():
        target_name = _target_name()
        target_arguments = target_name.replace('-', ' ')
        build_command = f'printable/native/build.fish {target_arguments}'
        raise FileNotFoundError(f'找不到 column 动态库: {library_path}，请先运行 {build_command}')

    library = ctypes.CDLL(str(library_path), use_errno=True)
    library.column_render.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.POINTER(_ColumnOptions),
        ctypes.POINTER(_ColumnResult),
    ]
    library.column_render.restype = ctypes.c_int
    library.column_result_free.argtypes = [ctypes.POINTER(_ColumnResult)]
    library.column_result_free.restype = None
    library.column_widths.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_size_t,
    ]
    library.column_widths.restype = ctypes.c_size_t
    return library


_CELL_SEPARATOR = '\x1f'

_widths_library: ctypes.CDLL | bool | None = None


def _get_widths_library() -> ctypes.CDLL | None:
    """惰性加载 column 动态库；不可用时返回 None（不报错）。"""
    global _widths_library
    if _widths_library is None:
        try:
            _widths_library = _load_library()
        except FileNotFoundError:
            _widths_library = False
    return _widths_library if _widths_library else None


def widths_of(cells: Sequence[str]) -> list[int] | None:
    """批量计算单元格的终端显示宽度；column 动态库不可用时返回 None。"""
    library = _get_widths_library()
    if library is None:
        return None
    if not cells:
        return []
    input_bytes = _CELL_SEPARATOR.join(cells).encode('utf-8', errors='replace')
    widths_array = (ctypes.c_size_t * len(cells))()
    cell_count = library.column_widths(input_bytes, len(input_bytes), widths_array, len(cells))
    if cell_count != len(cells):
        return None
    return list(widths_array)


def _normalize_options(
    options: ColumnOptions | Sequence[ColumnOptionItem],
    input_files: Sequence[str],
) -> tuple[list[tuple[bytes, bytes | None]], list[bytes]]:
    """把选项对象和输入文件转换成统一结构。"""
    if isinstance(options, ColumnOptions):
        if input_files:
            raise TypeError('ColumnOptions 和 input_files 不能同时传入')
        option_items = options.items
        input_files = options.input_files
    else:
        option_items = options

    if not isinstance(option_items, Sequence) or isinstance(option_items, (str, bytes)):
        raise TypeError('options 必须是 ColumnOptions 或选项对象序列')
    if not isinstance(input_files, Sequence) or isinstance(input_files, (str, bytes)):
        raise TypeError('input_files 必须是文件名序列')

    normalized_items = []
    for option in option_items:
        if isinstance(option, ColumnOption):
            option_name, option_value = option.name, option.value
        else:
            try:
                option_name, option_value = option
            except (TypeError, ValueError) as error:
                raise TypeError('每个 column 选项必须是 ColumnOption 或二元组') from error
        if not isinstance(option_name, str) or '\x00' in option_name:
            raise ValueError('column 选项名必须是不含 NUL 的字符串')
        if option_value is not None and (not isinstance(option_value, str) or '\x00' in option_value):
            raise ValueError('column 选项值必须是不含 NUL 的字符串或 None')
        encoded_value = None if option_value is None else option_value.encode('utf-8')
        normalized_items.append((option_name.encode('utf-8'), encoded_value))

    normalized_files = []
    for input_file in input_files:
        if not isinstance(input_file, str) or '\x00' in input_file:
            raise ValueError('column 输入文件名必须是不含 NUL 的字符串')
        normalized_files.append(input_file.encode('utf-8'))

    return normalized_items, normalized_files


def render(
    input_text: ColumnInput,
    options: ColumnOptions | Sequence[ColumnOptionItem] = (),
    input_files: Sequence[str] = (),
) -> str:
    """在当前进程内调用完整 util-linux column。"""
    if isinstance(input_text, str):
        input_bytes = input_text.encode('utf-8')
    elif isinstance(input_text, bytes):
        input_bytes = input_text
    else:
        raise TypeError('input_text 必须是 str 或 bytes')

    option_items, input_files = _normalize_options(options, input_files)

    option_array = (_ColumnOption * len(option_items))()
    option_buffers = []
    for index, (option_name, option_value) in enumerate(option_items):
        option_buffers.extend((option_name, option_value))
        option_array[index] = _ColumnOption(option_name, option_value, option_value is not None)

    input_file_array = (ctypes.c_char_p * len(input_files))()
    for index, input_file in enumerate(input_files):
        input_file_array[index] = input_file
    option_buffers.extend(input_files)

    column_options = _ColumnOptions(option_array, len(option_items), input_file_array, len(input_files))
    result = _ColumnResult()
    library = _load_library()
    status = library.column_render(
        input_bytes,
        len(input_bytes),
        ctypes.byref(column_options),
        ctypes.byref(result),
    )
    if status != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))

    exit_code = result.exit_code
    try:
        output = ctypes.string_at(result.output, result.output_size).decode('utf-8')
        error = ctypes.string_at(result.error, result.error_size).decode('utf-8', errors='replace')
    finally:
        library.column_result_free(ctypes.byref(result))

    if exit_code != 0:
        raise ColumnExecutionError(exit_code, error.strip())
    return output
