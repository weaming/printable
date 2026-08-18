"""将 JSON、YAML 或 CSV 数据渲染为终端表格。"""

import argparse
import csv
import io
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator, Mapping

import yaml
from wcwidth import wcswidth

from . import column as _column

ColumnExecutionError = _column.ColumnExecutionError
render_with_column = _column.render
native_widths_of = _column.widths_of

try:
    from yaml import CLoader as YAML_LOADER
except ImportError:
    from yaml import Loader as YAML_LOADER

GRID_TOP, GRID_MID, GRID_BOT = '┌┬┐', '├┼┤', '└┴┘'
ROW_CHAR, COL_CHAR = '─', '│'

GRID_STYLES = {
    'full': {'grid': 'full', 'col_sep': COL_CHAR, 'row_sep': ROW_CHAR},
    'inner': {'grid': 'inner', 'col_sep': COL_CHAR, 'row_sep': ROW_CHAR},
    'markdown': {'grid': 'markdown', 'col_sep': '|', 'row_sep': '-'},
    'default': {'grid': None, 'col_sep': '', 'row_sep': None},
}

# 各网格的边框与分隔线配置（header_conditional：仅在有数据行时画表头下划线）
GRID_LAYOUTS = {
    'full': {
        'edges': (COL_CHAR, COL_CHAR),
        'top': GRID_TOP,
        'header_line': GRID_MID,
        'row_line': GRID_MID,
        'bottom': GRID_BOT,
        'header_conditional': True,
    },
    'inner': {
        'edges': None,
        'top': None,
        'header_line': ('', GRID_MID[1], ''),
        'row_line': ('', GRID_MID[1], ''),
        'bottom': None,
        'header_conditional': True,
    },
    'markdown': {
        'edges': ('|', '|'),
        'top': None,
        'header_line': ('|', '|', '|'),
        'row_line': None,
        'bottom': None,
        'header_conditional': False,
    },
    'default': {
        'edges': None,
        'top': None,
        'header_line': None,
        'row_line': None,
        'bottom': None,
        'header_conditional': False,
    },
}

ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
CONTROL_PATTERN = re.compile(r'[\x00-\x1f\x7f-\x9f]')
VALID_GRIDS = frozenset(GRID_STYLES)
VALID_BAR_SCALES = frozenset(('linear', 'linal', 'ln', 'log10'))
DEBUG = os.getenv('DEBUG')


def normalize_cell_value(value):
    """将任意单元格值转换为可安全输出的一行文本。"""
    text = '' if value is None else str(value)
    return CONTROL_PATTERN.sub(' ', text)


def _python_text_width(text):
    """用纯 Python wcwidth 计算显示宽度。"""
    width = wcswidth(text)
    return width if width >= 0 else len(text)


# 默认渲染参数的终端宽度（全局常量，' ' 恒占 1 列，空串 0 列）
PREFIX_WIDTH = 1
SUFFIX_WIDTH = 1
SEP_COL_WIDTH = 0


def _raw_text_width(text):
    """计算已归一化文本的显示宽度；native 库可用时走 C。"""
    native_widths = native_widths_of([text])
    if native_widths is not None:
        return native_widths[0]
    return _python_text_width(text)


def calc_text_width(text):
    """计算终端显示宽度，忽略 ANSI 控制序列；native 库可用时走 C。"""
    visible_text = ANSI_ESCAPE_PATTERN.sub('', normalize_cell_value(text))
    return _raw_text_width(visible_text)


def _calc_widths(cells):
    """批量计算已归一化文本的显示宽度；native 库可用时一次 C 调用。

    输入须为 normalize_cell_value 处理过的文本（不含控制字符/ANSI 转义）。
    """
    native_widths = native_widths_of(cells)
    if native_widths is not None:
        return native_widths
    return [_python_text_width(cell) for cell in cells]


def _calculate_widths(rows):
    """平铺计算多行单元格宽度，一次批量调用。

    返回（列宽列表, 平铺宽度）；rows 须为已归一化的等宽行列表。
    """
    column_count = len(rows[0])
    flat_cells = [cell for row in rows for cell in row]
    flat_widths = _calc_widths(flat_cells)
    widths = list(flat_widths[:column_count])
    for row_index in range(1, len(rows)):
        row_start = row_index * column_count
        for column_index in range(column_count):
            widths[column_index] = max(widths[column_index], flat_widths[row_start + column_index])
    return widths, flat_widths


def format_cell_value(text, cell_width, prefix=' ', suffix=' ', value_width=None):
    """格式化单个单元格并补齐显示宽度。"""
    normalized_text = normalize_cell_value(text)
    if value_width is None:
        value_width = _raw_text_width(normalized_text)
    padding_width = max(0, cell_width - value_width)
    return f'{prefix}{normalized_text}{" " * padding_width}{suffix}'


def validate_headers(headers):
    """规范化并验证表头。"""
    normalized_headers = [normalize_cell_value(header) for header in headers]
    if not normalized_headers:
        raise ValueError('表格至少需要一列表头')
    if any(not header for header in normalized_headers):
        raise ValueError('表头不能为空')
    if len(set(normalized_headers)) != len(normalized_headers):
        raise ValueError('表头不能重复')
    return normalized_headers


def normalize_table(data, headers=None, limit=None):
    """将字典记录或二维数据规范化为表头和记录列表。"""
    if limit is not None and limit < 0:
        raise ValueError('limit 不能小于 0')
    if isinstance(data, (str, bytes)) or not isinstance(data, Iterable):
        raise TypeError('data 必须是记录的可迭代对象')
    if isinstance(data, Mapping):
        data = [data]

    data_iterator = iter(data)
    try:
        first_record = next(data_iterator)
    except StopIteration:
        return [], []

    if isinstance(first_record, Mapping):
        raw_records = [first_record, *data_iterator]
        records = []
        inferred_headers = []
        for record_index, record in enumerate(raw_records, start=1):
            if not isinstance(record, Mapping):
                raise TypeError('字典表格中的每条记录都必须是字典')
            if None in record:
                raise ValueError(f'第 {record_index} 条记录包含超出表头的字段')
            normalized_record = {normalize_cell_value(key): value for key, value in record.items()}
            records.append(normalized_record)
            for key in normalized_record:
                if key not in inferred_headers:
                    inferred_headers.append(key)
        normalized_headers = validate_headers(headers) if headers is not None else validate_headers(inferred_headers)
        return normalized_headers, records[:limit] if limit is not None else records

    inferred_headers = validate_headers(first_record)
    normalized_headers = validate_headers(headers) if headers is not None else inferred_headers
    records = list(data_iterator)
    for record_index, record in enumerate(records, start=1):
        if isinstance(record, (str, bytes)) or not isinstance(record, Iterable):
            raise TypeError(f'第 {record_index} 条记录必须是序列')
        if len(record) > len(normalized_headers):
            raise ValueError(f'第 {record_index} 条记录的列数超过表头')
    return normalized_headers, records[:limit] if limit is not None else records


def record_value(record, header, index):
    """从字典或序列记录中读取单元格值。"""
    if isinstance(record, Mapping):
        return record.get(header, '')
    if isinstance(record, (str, bytes)):
        raise TypeError('记录必须是字典或序列')
    return record[index] if index < len(record) else ''


def scale_bar_value(value, bar_scale):
    """按指定尺度计算条形图的非负数值。"""
    absolute_value = abs(value)
    if bar_scale in ('linear', 'linal'):
        return absolute_value
    if bar_scale == 'ln':
        return math.log1p(absolute_value)
    return math.log10(1 + absolute_value)


def calculate_bar_maximums(records, headers, bars, bar_scale):
    """计算每个条形图列的最大缩放值。"""
    maximums = {header: 0.0 for header in bars}
    header_indices = {header: index for index, header in enumerate(headers)}
    for record in records:
        for header in bars:
            if header not in header_indices:
                continue
            try:
                value = float(record_value(record, header, header_indices[header]))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                maximums[header] = max(maximums[header], scale_bar_value(value, bar_scale))
    return maximums


def convert_value_to_bar(value, header, bars, bar_char, bar_width, maximums, bar_scale):
    """将配置为条形图的数值转换为有符号条形文本。"""
    normalized_value = normalize_cell_value(value)
    if header not in bars or not normalized_value:
        return normalized_value
    try:
        numeric_value = float(normalized_value)
    except ValueError:
        return normalized_value
    if not math.isfinite(numeric_value) or numeric_value == 0:
        return normalized_value

    maximum = maximums.get(header, 0.0)
    if maximum <= 0:
        return normalized_value
    ratio = scale_bar_value(numeric_value, bar_scale) / maximum
    bar_length = min(bar_width, max(1, int(ratio * bar_width)))
    return ('-' if numeric_value < 0 else '') + bar_char * bar_length


def format_record(record, headers, bars, bar_char, bar_width, maximums, bar_scale):
    """将一条原始记录转换为渲染用单元格。"""
    return tuple(
        convert_value_to_bar(
            record_value(record, header, index), header, bars, bar_char, bar_width, maximums, bar_scale
        )
        for index, header in enumerate(headers)
    )


def escape_markdown_row(row):
    """转义 Markdown 单元格中的列分隔符。"""
    return tuple(value.replace('|', '\\|') for value in row)


def render_data_row(row, widths, col_sep, prefix, suffix, edges=None, row_widths=None):
    """渲染一行数据单元格；row_widths 已提供时跳过批量计算。"""
    if row_widths is None:
        row_widths = _calc_widths(row)
    cells = [
        format_cell_value(value, widths[index], prefix, suffix, value_width=row_widths[index])
        for index, value in enumerate(row)
    ]
    line = col_sep.join(cells)
    return f'{edges[0]}{line}{edges[1]}' if edges else line


def render_separator(widths, row_sep, prefix_suffix_width, left='', junction='', right=''):
    """渲染一行横向分隔线。"""
    cell_widths = [width + prefix_suffix_width for width in widths]
    return left + junction.join(row_sep * width for width in cell_widths) + right


def iter_readable(
    data,
    headers=None,
    grid=None,
    col_sep=None,
    row_sep=None,
    prefix=' ',
    suffix=' ',
    bars=None,
    bar_char='x',
    bar_width=100,
    bar_scale='linal',
    limit=None,
):
    """逐行生成可打印的表格文本。"""
    if grid is not None and grid not in VALID_GRIDS:
        raise ValueError(f'不支持的 grid: {grid}')
    if bar_scale not in VALID_BAR_SCALES:
        raise ValueError(f'不支持的 bar_scale: {bar_scale}')
    if bar_width < 0:
        raise ValueError('bar_width 不能小于 0')

    normalized_headers, records = normalize_table(data, headers, limit)
    if not normalized_headers:
        return

    selected_bars = set(bars or [])
    maximums = calculate_bar_maximums(records, normalized_headers, selected_bars, bar_scale)

    rendered_rows = [normalized_headers]
    for record in records:
        row = format_record(record, normalized_headers, selected_bars, bar_char, bar_width, maximums, bar_scale)
        if grid == 'markdown':
            row = escape_markdown_row(row)
        rendered_rows.append(row)

    column_count = len(normalized_headers)
    widths, flat_widths = _calculate_widths(rendered_rows)

    style = GRID_STYLES[grid or 'default']
    effective_col_sep = style['col_sep'] if col_sep is None else col_sep
    effective_row_sep = style['row_sep'] if row_sep is None else row_sep
    if (prefix, suffix) == (' ', ' '):
        prefix_suffix_width = PREFIX_WIDTH + SUFFIX_WIDTH
    else:
        prefix_suffix_width = sum(_calc_widths([prefix, suffix]))

    def row_widths(row_index):
        row_start = row_index * column_count
        return flat_widths[row_start : row_start + column_count]

    layout = GRID_LAYOUTS[grid or 'default']
    if layout['top'] is not None:
        yield render_separator(widths, effective_row_sep, prefix_suffix_width, *layout['top'])
    yield render_data_row(normalized_headers, widths, effective_col_sep, prefix, suffix, layout['edges'], row_widths(0))
    if layout['header_line'] is not None and (records or not layout['header_conditional']):
        yield render_separator(widths, effective_row_sep, prefix_suffix_width, *layout['header_line'])
    for row_index in range(1, len(rendered_rows)):
        yield render_data_row(
            rendered_rows[row_index], widths, effective_col_sep, prefix, suffix, layout['edges'], row_widths(row_index)
        )
        if layout['row_line'] is not None and row_index < len(rendered_rows) - 1:
            yield render_separator(widths, effective_row_sep, prefix_suffix_width, *layout['row_line'])
    if layout['bottom'] is not None:
        yield render_separator(widths, effective_row_sep, prefix_suffix_width, *layout['bottom'])


def readable(*args, **kwargs):
    """生成可打印的表格文本。"""
    return '\n'.join(iter_readable(*args, **kwargs))


def render_column_data(data: Iterable, args: argparse.Namespace) -> str:
    """使用 column 渲染默认表格，并保持 Python 默认边距。"""
    headers, records = normalize_table(data, limit=args.limit)
    if not headers:
        return ''

    selected_bars = set(args.bar or [])
    maximums = calculate_bar_maximums(records, headers, selected_bars, args.bar_scale)
    formatted_records = [
        format_record(record, headers, selected_bars, args.bar_char, args.bar_width, maximums, args.bar_scale)
        for record in records
    ]
    rows = [headers, *formatted_records]
    tsv_input = ''.join('\t'.join(row) + '\n' for row in rows)
    column_options: dict[str, str | bool] = {
        'output_width': 'unlimited',
        'separator': '\t',
        'table': True,
        'table_empty_lines': True,
    }
    if args.sep_col:
        column_options['output_separator'] = f' {args.sep_col} '

    column_output = render_with_column(tsv_input, **column_options)
    widths, _ = _calculate_widths([headers, *formatted_records])

    separator_text = args.sep_col or ''
    separator_width = SEP_COL_WIDTH if separator_text == '' else _calc_widths([separator_text])[0]
    target_width = sum(widths) + (2 * len(widths)) + (separator_width * (len(widths) - 1))
    padded_lines = [f' {line} ' for line in column_output.splitlines()]
    normalized_lines = []
    for line, line_width in zip(padded_lines, _calc_widths(padded_lines)):
        padding_width = max(0, target_width - line_width)
        normalized_lines.append(line + (' ' * padding_width))
    return '\n'.join(normalized_lines)


def render_with_engine(data: Iterable, args: argparse.Namespace) -> Iterator[str]:
    """根据 CLI engine 选择 Python 或 column 渲染器。"""
    engine = getattr(args, 'engine', 'auto')

    def python_lines() -> Iterator[str]:
        """使用原生 Python 渲染器逐行输出。"""
        yield from iter_readable(
            data,
            col_sep=args.sep_col,
            row_sep=args.sep_row,
            grid=args.grid,
            bars=args.bar or [],
            bar_char=args.bar_char,
            bar_width=args.bar_width,
            bar_scale=args.bar_scale,
            limit=args.limit,
        )

    if engine == 'python':
        return python_lines()
    if args.grid is not None:
        if engine == 'auto':
            return python_lines()
        raise ValueError('column engine 只支持默认表格格式，不能与 --grid 同时使用')

    if engine == 'auto':
        try:
            return iter(render_column_data(data, args).splitlines())
        except FileNotFoundError:
            return python_lines()
    return iter(render_column_data(data, args).splitlines())


def detect_file_format(path, content=None):
    """按扩展名和内容嗅探文件格式，返回 json/csv/yaml；content 为已读入的字节内容。"""
    extension_map = {'.json': 'json', '.csv': 'csv', '.yaml': 'yaml', '.yml': 'yaml'}
    extension = os.path.splitext(path)[1].lower()
    if extension in extension_map:
        return extension_map[extension]

    if content is None:
        with open(path, 'rb') as file:
            content = file.read(4096)
    head = content[:4096].decode('utf-8-sig', errors='replace')
    stripped = head.lstrip()
    if not stripped:
        return 'json'
    if stripped[0] in '{[':
        return 'json'
    for line in head.splitlines()[:20]:
        stripped_line = line.strip()
        if re.match(r'^[\w.\-/]+:\s*\S', stripped_line) or (
            stripped_line.startswith('- ') and ',' not in stripped_line
        ):
            return 'yaml'
    return 'csv'


def read_json(path, content=None):
    """读取 JSON 文件或字节内容，返回解析结果。"""
    if content is None:
        with open(path, 'rb') as file:
            content = file.read()
    return json.loads(content.decode('utf-8-sig'))


def read_yaml(path, content=None):
    """读取 YAML 文件或字节内容，返回解析结果。"""
    if content is None:
        with open(path, 'rb') as file:
            content = file.read()
    return yaml.load(content.decode('utf-8-sig'), Loader=YAML_LOADER)


def read_csv(path, content=None):
    """以 UTF-8 CSV 格式读取并校验表格数据；content 为已读入的字节内容。"""
    delimiter = os.getenv('CSV_DELIMITER', ',')
    quotechar = os.getenv('CSV_QUOTE', '"')
    encoding = os.getenv('CSV_ENCODING', 'utf-8-sig')
    if len(delimiter) != 1 or len(quotechar) != 1:
        raise ValueError('CSV_DELIMITER 和 CSV_QUOTE 必须是单个字符')

    if content is None:
        csv_file = open(path, encoding=encoding, newline='')
    else:
        csv_file = io.TextIOWrapper(io.BytesIO(content), encoding=encoding, newline='')
    with csv_file:
        reader = csv.DictReader(csv_file, delimiter=delimiter, quotechar=quotechar)
        if reader.fieldnames is None:
            return []
        validate_headers(reader.fieldnames)
        records = []
        for record in reader:
            if None in record:
                raise ValueError(f'CSV 第 {reader.line_num} 行的列数超过表头')
            records.append(record)
    return records


def write_to_pager(lines, line_numbers):
    """使用 less 分页查看输出。"""
    command = ['less', '-S'] + (['-N'] if line_numbers else [])
    with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
        try:
            if process.stdin is None:
                raise RuntimeError('无法创建分页器输入流')
            for line in lines:
                process.stdin.write(f'{line}\n'.encode('utf-8'))
            process.stdin.close()
        except BrokenPipeError:
            return
        process.wait()


def main():
    """解析命令行参数并输出表格。"""
    parser = argparse.ArgumentParser(description='可打印的表格生成器')
    parser.add_argument('-f', '--file', default='/dev/stdin', help='输入文件路径')
    parser.add_argument('--sep-col', default=None, help='列分隔符')
    parser.add_argument('--sep-row', default=None, help='行分隔符')
    parser.add_argument(
        '--grid', default=os.getenv('PRINTABLE_GRID'), choices=['inner', 'full', 'markdown'], help='网格样式'
    )
    parser.add_argument('--less', action='store_true', help='使用less查看')
    parser.add_argument(
        '-e',
        '--engine',
        choices=['python', 'column', 'auto'],
        default=os.getenv('PRINTABLE_ENGINE', 'auto'),
        help='渲染引擎，默认 auto；无网格时优先使用 column',
    )
    parser.add_argument('-N', '--line-numbers', action='store_false', default=True, help='显示行号')
    parser.add_argument('-t', '--type', default=None, choices=['json', 'csv', 'yaml'], help='文件格式，默认自动检测')
    parser.add_argument('-b', '--bar', nargs='*', help='数值字段转换为条形图')
    parser.add_argument('-c', '--bar-char', default='o', help='条形图字符')
    parser.add_argument('-w', '--bar-width', default=100, type=int, help='条形图宽度')
    parser.add_argument('-s', '--bar-scale', default='linal', choices=sorted(VALID_BAR_SCALES), help='轴缩放')
    parser.add_argument('-l', '--limit', type=int, help='记录数限制')

    args = parser.parse_args()
    if args.grid == 'markdown':
        args.less = False

    try:
        readers = {'json': read_json, 'csv': read_csv, 'yaml': read_yaml}
        stdin_content = sys.stdin.buffer.read() if args.file == '/dev/stdin' else None
        file_type = args.type or detect_file_format(args.file, stdin_content)
        data = readers[file_type](args.file, stdin_content)
        lines = render_with_engine(data, args)
        if args.less:
            write_to_pager(lines, args.line_numbers)
        else:
            for line in lines:
                print(line)
    except Exception as error:
        if DEBUG:
            raise
        print(f'错误: {error}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
