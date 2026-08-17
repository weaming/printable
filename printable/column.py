import os
from collections.abc import Mapping, Sequence
from typing import TypeAlias

from .native.column import ColumnExecutionError as ColumnExecutionError
from .native.column import render as render_native_column

InputFile: TypeAlias = str | os.PathLike[str]
OptionScalar: TypeAlias = str | int | float | bool | None
OptionValue: TypeAlias = OptionScalar | Sequence[OptionScalar]


def _normalize_input_files(input_files: InputFile | Sequence[InputFile] | None) -> tuple[str, ...]:
    """规范化 column 输入文件参数。"""
    if input_files is None:
        return ()
    if isinstance(input_files, (str, os.PathLike)):
        return (os.fspath(input_files),)
    if not isinstance(input_files, Sequence):
        raise TypeError('input_files 必须是文件名或文件名序列')
    normalized_files = []
    for input_file in input_files:
        normalized_file = os.fspath(input_file)
        if isinstance(normalized_file, bytes):
            raise TypeError('input_files 不支持 bytes 路径')
        normalized_files.append(normalized_file)
    return tuple(normalized_files)


def _build_options(options: Mapping[str, OptionValue]) -> tuple[tuple[str, str | None], ...]:
    """把 Python 关键字参数转换为 column 长选项。"""
    option_items = []
    for option_name, option_value in options.items():
        if not isinstance(option_name, str) or not option_name:
            raise TypeError('column 选项名必须是非空字符串')

        normalized_name = option_name.replace('_', '-')
        if option_value is None or option_value is False:
            continue
        if option_value is True:
            option_items.append((normalized_name, None))
            continue

        if isinstance(option_value, Sequence) and not isinstance(option_value, (str, bytes)):
            option_values = option_value
        else:
            option_values = (option_value,)
        for value in option_values:
            if value is None or value is False:
                continue
            if value is True:
                option_items.append((normalized_name, None))
            else:
                option_items.append((normalized_name, str(value)))

    return tuple(option_items)


def render(
    input_text: str | bytes,
    *,
    columns: str | int | None = None,
    color: str | bool | None = None,
    fillrows: bool = False,
    help: bool = False,
    input_separator: str | None = None,
    json: bool = False,
    keep_empty_lines: bool = False,
    output_separator: str | None = None,
    output_width: str | int | None = None,
    separator: str | None = None,
    table: bool = False,
    table_colorscheme: str | None = None,
    table_columns: str | None = None,
    table_column: str | Sequence[str] | None = None,
    table_columns_limit: int | str | None = None,
    table_hide: str | None = None,
    table_name: str | None = None,
    table_maxout: bool = False,
    table_noextreme: str | None = None,
    table_noheadings: bool = False,
    table_order: str | None = None,
    table_right: str | None = None,
    table_truncate: str | None = None,
    table_wrap: str | None = None,
    table_empty_lines: bool = False,
    table_header_repeat: bool = False,
    table_header_as_columns: bool = False,
    tree: str | None = None,
    tree_id: str | None = None,
    tree_parent: str | None = None,
    use_spaces: int | str | None = None,
    version: bool = False,
    wrap_separator: str | None = None,
    input_files: InputFile | Sequence[InputFile] | None = (),
) -> str:
    """使用 Python 关键字参数调用 util-linux column。"""
    if input_separator is not None and separator is not None:
        raise ValueError('input_separator 和 separator 不能同时传入')
    if columns is not None and output_width is not None:
        raise ValueError('columns 和 output_width 不能同时传入')

    options = {
        'columns': columns,
        'color': color,
        'fillrows': fillrows,
        'help': help,
        'input-separator': input_separator,
        'json': json,
        'keep-empty-lines': keep_empty_lines,
        'output-separator': output_separator,
        'output-width': output_width,
        'separator': separator,
        'table': table,
        'table-colorscheme': table_colorscheme,
        'table-columns': table_columns,
        'table-column': table_column,
        'table-columns-limit': table_columns_limit,
        'table-hide': table_hide,
        'table-name': table_name,
        'table-maxout': table_maxout,
        'table-noextreme': table_noextreme,
        'table-noheadings': table_noheadings,
        'table-order': table_order,
        'table-right': table_right,
        'table-truncate': table_truncate,
        'table-wrap': table_wrap,
        'table-empty-lines': table_empty_lines,
        'table-header-repeat': table_header_repeat,
        'table-header-as-columns': table_header_as_columns,
        'tree': tree,
        'tree-id': tree_id,
        'tree-parent': tree_parent,
        'use-spaces': use_spaces,
        'version': version,
        'wrap-separator': wrap_separator,
    }
    normalized_files = _normalize_input_files(input_files)
    normalized_options = _build_options(options)
    return render_native_column(input_text, normalized_options, normalized_files)
