"""
Usage Example:

    from printable import readable, styles
    readable(list_of_dict, **styles['full'])
"""

import argparse
import math
import os
import string
import subprocess
import sys

from data_process.io_csv import new_csv_reader
from data_process.io_json import read_json
from data_process.io_yaml import read_yaml

# Grid box-drawing characters
GRID_TOP, GRID_MID, GRID_BOT = "┌┬┐", "├┼┤", "└┴┘"
ROW_CHAR, COL_CHAR = "─", "│"

GRID_STYLES = {
    "full": {"grid": "full", "col_sep": COL_CHAR, "row_sep": ROW_CHAR},
    "inner": {"grid": "inner", "col_sep": COL_CHAR, "row_sep": ROW_CHAR},
    "markdown": {"grid": "markdown", "col_sep": "|", "row_sep": None},
    "default": {"grid": None, "col_sep": "  ", "row_sep": None},
}

SINGLE_WIDTH_CHARS = set(string.ascii_letters + string.digits + string.punctuation + " ·")
DEBUG = os.getenv("DEBUG")


def calc_text_width(text):
    """计算文本显示宽度（半角1，全角2）"""
    return sum(1 if c in SINGLE_WIDTH_CHARS else 2 for c in (text or ""))


def format_cell_value(text, cell_width, prefix=" ", suffix=" "):
    """格式化单个单元格：添加前后缀并右对齐"""
    return f"{prefix}{text}{' ' * (cell_width - calc_text_width(text))}{suffix}"


def format_row_cells(row_values, cell_widths, prefix=" ", suffix=" "):
    """格式化整行单元格"""
    return [format_cell_value(v, cell_widths[i], prefix, suffix) for i, v in enumerate(row_values)]


def convert_value_to_bar(value, key, bar_config, max_values, scale_func):
    """将数值转换为条形图字符串"""
    bars, bar_char, bar_width = bar_config

    if bars and key in bars and value and max_values.get(key):
        try:
            ratio = scale_func(float(value)) / scale_func(max_values[key])
            return bar_char * int(ratio * bar_width)
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    return str(value).replace("\n", " ").replace("\t", " ")


def readable(
    data,
    headers=None,
    grid=None,
    col_sep="  ",
    row_sep=None,
    prefix=" ",
    suffix=" ",
    bars=None,
    bar_char="x",
    bar_width=100,
    bar_scale="linal",
    limit=None,
):
    """生成可打印的表格文本"""
    if not data:
        return ""

    bars = bars or []
    scale_func = {"linal": lambda x: x, "ln": math.log, "log10": math.log10}[bar_scale]
    bar_config = (bars, bar_char, bar_width)

    # 调整分隔符
    if not grid:
        col_sep = row_sep = ""
    elif grid == "markdown":
        col_sep, row_sep = "|", "-"

    # 处理数据格式
    data = data[:limit] if limit else data
    if isinstance(data[0], dict):
        headers = headers or list(data[0].keys())
        records = data
    else:
        headers = headers or data[0]
        records = data[1:]

    # 计算条形图的最大值
    max_bar_values = {k: 0 for k in bars}
    for record in records:
        rec_dict = (
            record
            if isinstance(record, dict)
            else {headers[i]: record[i] if i < len(record) else "" for i in range(len(headers))}
        )
        for k in bars:
            if rec_dict.get(k):
                try:
                    max_bar_values[k] = max(float(rec_dict[k]), max_bar_values[k])
                except (ValueError, TypeError):
                    pass

    # 转换并格式化数据
    formatted_records = []
    col_widths = [0] * len(headers)

    for record in records:
        row = tuple(
            convert_value_to_bar(
                record.get(h) if isinstance(record, dict) else (record[i] if i < len(record) else ""),
                h,
                bar_config,
                max_bar_values,
                scale_func,
            )
            for i, h in enumerate(headers)
        )
        formatted_records.append(row)
        for i, v in enumerate(row):
            col_widths[i] = max(calc_text_width(v), col_widths[i])

    # 包含表头的宽度
    for i, h in enumerate(headers):
        col_widths[i] = max(calc_text_width(h), col_widths[i])

    # 构建最终行列表（包含分隔行）
    all_rows = [tuple(headers)] + formatted_records
    final_rows = []

    if grid and (row_sep or grid == "markdown"):
        sep_row = tuple(row_sep * (w + len(prefix) + len(suffix)) for w in col_widths)

        for idx, row in enumerate(all_rows):
            if grid == "inner":
                final_rows.append((row, False))
                if idx < len(all_rows) - 1:
                    final_rows.append((sep_row, True))
            elif grid == "full":
                final_rows.append((sep_row, True))
                final_rows.append((row, False))
                if idx == len(all_rows) - 1:
                    final_rows.append((sep_row, True))
            elif grid == "markdown":
                final_rows.append((row, False))
                if idx == 0:
                    final_rows.append((sep_row, True))
    else:
        final_rows = [(row, False) for row in all_rows]

    # 渲染表格
    lines = []
    for row_idx, (row_data, is_separator) in enumerate(final_rows):
        if is_separator:
            # 分隔行
            if grid == "full":
                is_edge = row_idx in [0, len(final_rows) - 1]
                sep_char = (GRID_TOP[1] if row_idx == 0 else GRID_BOT[1]) if is_edge else GRID_MID[1]
                line = sep_char.join(row_data)
                edges = (
                    (GRID_TOP[0], GRID_TOP[2])
                    if row_idx == 0
                    else (GRID_BOT[0], GRID_BOT[2]) if is_edge else (GRID_MID[0], GRID_MID[2])
                )
                line = edges[0] + line + edges[1]
            elif grid == "inner":
                line = GRID_MID[1].join(row_data)
            else:  # markdown
                line = col_sep + col_sep.join(row_data) + col_sep

            lines.append(line)
        else:
            # 数据行
            if grid == "markdown":
                cells = format_row_cells(row_data, col_widths, prefix, suffix)
                line = col_sep + col_sep.join(cells) + col_sep
            else:
                need_padding = (
                    not grid or (grid == "inner" and row_idx % 2 == 0) or (grid == "full" and row_idx % 2 == 1)
                )
                pad_prefix = prefix if need_padding else ""
                pad_suffix = suffix if need_padding else ""

                cells = format_row_cells(row_data, col_widths, pad_prefix, pad_suffix)
                line = col_sep.join(cells)

                if grid == "full":
                    line = COL_CHAR + line + COL_CHAR

            lines.append(line)

    return "\n".join(lines)


def read_csv(path):
    """读取CSV文件"""
    with new_csv_reader(
        path,
        csv_format={
            "delimiter": os.getenv("CSV_DELIMITER", ","),
            "quotechar": os.getenv("CSV_QUOTE", '"'),
        },
    ) as reader:
        return list(reader)


def write_to_pager(text, line_numbers):
    """使用less分页查看输出"""
    cmd = ["less", "-S"] + (["-N"] if line_numbers else [])
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        p.stdin.write(text.encode("utf-8"))
    except BrokenPipeError:
        sys.exit(1)
    p.communicate()


def main():
    parser = argparse.ArgumentParser(description="可打印的表格生成器")
    parser.add_argument("-f", "--file", default="/dev/stdin", help="输入文件路径")
    parser.add_argument("--sep-col", default=COL_CHAR, help="列分隔符")
    parser.add_argument("--sep-row", default=ROW_CHAR, help="行分隔符")
    parser.add_argument(
        "--grid", default=os.getenv("PRINTABLE_GRID"), choices=["inner", "full", "markdown"], help="网格样式"
    )
    parser.add_argument("--less", action="store_true", help="使用less查看")
    parser.add_argument("-N", "--line-numbers", action="store_false", default=True, help="显示行号")
    parser.add_argument("-t", "--type", default="json", choices=["json", "csv", "yaml"], help="文件格式")
    parser.add_argument("-b", "--bar", nargs="*", help="数值字段转换为条形图")
    parser.add_argument("-c", "--bar-char", default="o", help="条形图字符")
    parser.add_argument("-w", "--bar-width", default=100, type=int, help="条形图宽度")
    parser.add_argument("-s", "--bar-scale", default="linal", choices=["linal", "ln", "log10"], help="轴缩放")
    parser.add_argument("-l", "--limit", type=int, help="记录数限制")

    args = parser.parse_args()
    if args.grid == "markdown":
        args.less = False

    try:
        readers = {"json": read_json, "csv": read_csv, "yaml": read_yaml}
        data = readers[args.type](args.file)

        output = readable(
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
            write_to_pager(output, args.line_numbers)
        else:
            print(output)
    except Exception as e:
        if DEBUG:
            raise
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
