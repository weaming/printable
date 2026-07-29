"""将 JSON、YAML 或 CSV 数据渲染为终端表格。"""

import argparse
import csv
import math
import os
import re
import subprocess
import sys
import unicodedata
from collections.abc import Iterable, Mapping

from data_process.io_json import read_json
from data_process.io_yaml import read_yaml
from wcwidth import wcswidth

GRID_TOP, GRID_MID, GRID_BOT = "┌┬┐", "├┼┤", "└┴┘"
ROW_CHAR, COL_CHAR = "─", "│"

GRID_STYLES = {
    "full": {"grid": "full", "col_sep": COL_CHAR, "row_sep": ROW_CHAR},
    "inner": {"grid": "inner", "col_sep": COL_CHAR, "row_sep": ROW_CHAR},
    "markdown": {"grid": "markdown", "col_sep": "|", "row_sep": "-"},
    "default": {"grid": None, "col_sep": "", "row_sep": None},
}

ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
VALID_GRIDS = frozenset(GRID_STYLES)
VALID_BAR_SCALES = frozenset(("linear", "linal", "ln", "log10"))
DEBUG = os.getenv("DEBUG")


def normalize_cell_value(value):
    """将任意单元格值转换为可安全输出的一行文本。"""
    text = "" if value is None else str(value)
    return "".join(" " if unicodedata.category(char) == "Cc" else char for char in text)


def calc_text_width(text):
    """计算终端显示宽度，忽略 ANSI 控制序列。"""
    visible_text = ANSI_ESCAPE_PATTERN.sub("", normalize_cell_value(text))
    width = wcswidth(visible_text)
    return width if width >= 0 else len(visible_text)


def format_cell_value(text, cell_width, prefix=" ", suffix=" "):
    """格式化单个单元格并补齐显示宽度。"""
    normalized_text = normalize_cell_value(text)
    padding_width = max(0, cell_width - calc_text_width(normalized_text))
    return f"{prefix}{normalized_text}{' ' * padding_width}{suffix}"


def validate_headers(headers):
    """规范化并验证表头。"""
    normalized_headers = [normalize_cell_value(header) for header in headers]
    if not normalized_headers:
        raise ValueError("表格至少需要一列表头")
    if any(not header for header in normalized_headers):
        raise ValueError("表头不能为空")
    if len(set(normalized_headers)) != len(normalized_headers):
        raise ValueError("表头不能重复")
    return normalized_headers


def normalize_table(data, headers=None, limit=None):
    """将字典记录或二维数据规范化为表头和记录列表。"""
    if limit is not None and limit < 0:
        raise ValueError("limit 不能小于 0")
    if isinstance(data, (str, bytes)) or not isinstance(data, Iterable):
        raise TypeError("data 必须是记录的可迭代对象")

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
                raise TypeError("字典表格中的每条记录都必须是字典")
            if None in record:
                raise ValueError(f"第 {record_index} 条记录包含超出表头的字段")
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
            raise TypeError(f"第 {record_index} 条记录必须是序列")
        if len(record) > len(normalized_headers):
            raise ValueError(f"第 {record_index} 条记录的列数超过表头")
    return normalized_headers, records[:limit] if limit is not None else records


def record_value(record, header, index):
    """从字典或序列记录中读取单元格值。"""
    if isinstance(record, Mapping):
        return record.get(header, "")
    if isinstance(record, (str, bytes)):
        raise TypeError("记录必须是字典或序列")
    return record[index] if index < len(record) else ""


def scale_bar_value(value, bar_scale):
    """按指定尺度计算条形图的非负数值。"""
    absolute_value = abs(value)
    if bar_scale in ("linear", "linal"):
        return absolute_value
    if bar_scale == "ln":
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
    return ("-" if numeric_value < 0 else "") + bar_char * bar_length


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
    return tuple(value.replace("|", "\\|") for value in row)


def render_data_row(row, widths, col_sep, prefix, suffix, edges=None):
    """渲染一行数据单元格。"""
    cells = [format_cell_value(value, widths[index], prefix, suffix) for index, value in enumerate(row)]
    line = col_sep.join(cells)
    return f"{edges[0]}{line}{edges[1]}" if edges else line


def render_separator(widths, row_sep, prefix, suffix, left="", junction="", right=""):
    """渲染一行横向分隔线。"""
    cell_widths = [width + calc_text_width(prefix) + calc_text_width(suffix) for width in widths]
    return left + junction.join(row_sep * width for width in cell_widths) + right


def iter_readable(
    data,
    headers=None,
    grid=None,
    col_sep=None,
    row_sep=None,
    prefix=" ",
    suffix=" ",
    bars=None,
    bar_char="x",
    bar_width=100,
    bar_scale="linal",
    limit=None,
):
    """逐行生成可打印的表格文本。"""
    if grid is not None and grid not in VALID_GRIDS:
        raise ValueError(f"不支持的 grid: {grid}")
    if bar_scale not in VALID_BAR_SCALES:
        raise ValueError(f"不支持的 bar_scale: {bar_scale}")
    if bar_width < 0:
        raise ValueError("bar_width 不能小于 0")

    normalized_headers, records = normalize_table(data, headers, limit)
    if not normalized_headers:
        return

    selected_bars = set(bars or [])
    maximums = calculate_bar_maximums(records, normalized_headers, selected_bars, bar_scale)
    widths = [calc_text_width(header) for header in normalized_headers]
    for record in records:
        row = format_record(record, normalized_headers, selected_bars, bar_char, bar_width, maximums, bar_scale)
        if grid == "markdown":
            row = escape_markdown_row(row)
        for index, value in enumerate(row):
            widths[index] = max(widths[index], calc_text_width(value))

    style = GRID_STYLES[grid or "default"]
    effective_col_sep = style["col_sep"] if col_sep is None else col_sep
    effective_row_sep = style["row_sep"] if row_sep is None else row_sep
    def formatted_rows():
        """按最终网格格式逐条生成已格式化记录。"""
        for record in records:
            row = format_record(record, normalized_headers, selected_bars, bar_char, bar_width, maximums, bar_scale)
            yield escape_markdown_row(row) if grid == "markdown" else row

    if grid == "full":
        yield render_separator(widths, effective_row_sep, prefix, suffix, *GRID_TOP)
        yield render_data_row(normalized_headers, widths, effective_col_sep, prefix, suffix, (COL_CHAR, COL_CHAR))
        if records:
            yield render_separator(widths, effective_row_sep, prefix, suffix, *GRID_MID)
        for index, row in enumerate(formatted_rows()):
            yield render_data_row(row, widths, effective_col_sep, prefix, suffix, (COL_CHAR, COL_CHAR))
            if index < len(records) - 1:
                yield render_separator(widths, effective_row_sep, prefix, suffix, *GRID_MID)
        yield render_separator(widths, effective_row_sep, prefix, suffix, *GRID_BOT)
        return

    if grid == "inner":
        yield render_data_row(normalized_headers, widths, effective_col_sep, prefix, suffix)
        if records:
            yield render_separator(widths, effective_row_sep, prefix, suffix, "", GRID_MID[1], "")
        for index, row in enumerate(formatted_rows()):
            yield render_data_row(row, widths, effective_col_sep, prefix, suffix)
            if index < len(records) - 1:
                yield render_separator(widths, effective_row_sep, prefix, suffix, "", GRID_MID[1], "")
        return

    if grid == "markdown":
        yield render_data_row(normalized_headers, widths, effective_col_sep, prefix, suffix, ("|", "|"))
        yield render_separator(widths, effective_row_sep, prefix, suffix, "|", "|", "|")
        for row in formatted_rows():
            yield render_data_row(row, widths, effective_col_sep, prefix, suffix, ("|", "|"))
        return

    yield render_data_row(normalized_headers, widths, effective_col_sep, prefix, suffix)
    for row in formatted_rows():
        yield render_data_row(row, widths, effective_col_sep, prefix, suffix)


def readable(*args, **kwargs):
    """生成可打印的表格文本。"""
    return "\n".join(iter_readable(*args, **kwargs))


def read_csv(path):
    """以 UTF-8 CSV 格式读取并校验表格数据。"""
    delimiter = os.getenv("CSV_DELIMITER", ",")
    quotechar = os.getenv("CSV_QUOTE", '"')
    encoding = os.getenv("CSV_ENCODING", "utf-8-sig")
    if len(delimiter) != 1 or len(quotechar) != 1:
        raise ValueError("CSV_DELIMITER 和 CSV_QUOTE 必须是单个字符")

    with open(path, encoding=encoding, newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=delimiter, quotechar=quotechar)
        if reader.fieldnames is None:
            return []
        validate_headers(reader.fieldnames)
        records = []
        for record in reader:
            if None in record:
                raise ValueError(f"CSV 第 {reader.line_num} 行的列数超过表头")
            records.append(record)
    return records


def write_to_pager(lines, line_numbers):
    """使用 less 分页查看输出。"""
    command = ["less", "-S"] + (["-N"] if line_numbers else [])
    with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
        try:
            if process.stdin is None:
                raise RuntimeError("无法创建分页器输入流")
            for line in lines:
                process.stdin.write(f"{line}\n".encode("utf-8"))
            process.stdin.close()
        except BrokenPipeError:
            return
        process.wait()


def main():
    """解析命令行参数并输出表格。"""
    parser = argparse.ArgumentParser(description="可打印的表格生成器")
    parser.add_argument("-f", "--file", default="/dev/stdin", help="输入文件路径")
    parser.add_argument("--sep-col", default=None, help="列分隔符")
    parser.add_argument("--sep-row", default=None, help="行分隔符")
    parser.add_argument("--grid", default=os.getenv("PRINTABLE_GRID"), choices=["inner", "full", "markdown"], help="网格样式")
    parser.add_argument("--less", action="store_true", help="使用less查看")
    parser.add_argument("-N", "--line-numbers", action="store_false", default=True, help="显示行号")
    parser.add_argument("-t", "--type", default="json", choices=["json", "csv", "yaml"], help="文件格式")
    parser.add_argument("-b", "--bar", nargs="*", help="数值字段转换为条形图")
    parser.add_argument("-c", "--bar-char", default="o", help="条形图字符")
    parser.add_argument("-w", "--bar-width", default=100, type=int, help="条形图宽度")
    parser.add_argument("-s", "--bar-scale", default="linal", choices=sorted(VALID_BAR_SCALES), help="轴缩放")
    parser.add_argument("-l", "--limit", type=int, help="记录数限制")

    args = parser.parse_args()
    if args.grid == "markdown":
        args.less = False

    try:
        readers = {"json": read_json, "csv": read_csv, "yaml": read_yaml}
        data = readers[args.type](args.file)
        lines = iter_readable(
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
        if args.less:
            write_to_pager(lines, args.line_numbers)
        else:
            for line in lines:
                print(line)
    except Exception as error:
        if DEBUG:
            raise
        print(f"错误: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
