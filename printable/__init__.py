"""
Usage Example:

    from printable import readable, styles
    readable(list_of_dict, **styles['full'])
"""
import sys
import string
import argparse
import subprocess
import os
import math

from data_process.io_json import read_json
from data_process.io_csv import read_csv
from data_process.io_yaml import read_yaml

GRID_TOP = "┌┬┐"
GRID_MID = "├┼┤"
GRID_BOT = "└┴┘"
ROW = "─"
COL = "│"

ROW_TOP = GRID_TOP[1]
CROSS = GRID_MID[1]
ROW_BOTTOM = GRID_BOT[1]

LEFT_TOP = GRID_TOP[0]
RIGHT_TOP = GRID_TOP[2]

COL_LEFT = GRID_MID[0]
COL_RIGHT = GRID_MID[2]

LEFT_BOTTOM = GRID_BOT[0]
RIGHT_BOTTOM = GRID_BOT[2]

DEBUG = os.getenv("DEBUG")

single_width_str = string.ascii_letters + string.digits + string.punctuation + " "


def _width(x):
    if x in single_width_str:
        return 1
    else:
        return 2


def get_text_width(text):
    """get the print width of text accordding to whether it's printable ascii except the blank ' '"""
    if not text:
        return 0

    return sum(map(_width, text))


def table_print_row(lst, max_width_list, prefix=" ", suffix=" "):
    """just print a row data in the format of list"""
    return [
        "{}{}{}{}".format(
            prefix, v, " " * (max_width_list[i] - get_text_width(v)), suffix
        ) for i, v in enumerate(lst)
    ]


def change_based_on_is_grid_index(grid, origin, wanted, index):
    """if current index is grid, print the wanted text except of the origin separator"""
    _check_grid(grid)
    if grid:
        if grid == "inner" and index % 2 == 1:
            return wanted
        if grid == "full" and index % 2 == 0:
            return wanted
    return origin


def _check_grid(grid):
    assert grid in (
        None,
        "inner",
        "full",
        "markdown",
    ), 'grid must be in [None, "inner", "full", "markdown"], got {}'.format(
        grid
    )


def _get_cell_prefix_or_suffix(grid, fix, index):
    _check_grid(grid)
    # no prefix suffix for grid=markdown
    if grid == "markdown" and index == 1:
        return ""
    return change_based_on_is_grid_index(grid, fix, "", index)


def _get_row_sep(grid, sep, index, is_edge):
    _check_grid(grid)
    if grid == "full" and is_edge:
        if index == 0:
            return ROW_TOP
        return ROW_BOTTOM
    return change_based_on_is_grid_index(grid, sep, CROSS, index)


def _get_row_grid_edge(grid, row_index, col_index, is_row_edge):
    """
    return the symbol for the left and right table line
    """
    _check_grid(grid)
    if grid == "full":
        if is_row_edge:
            if row_index == 0:
                if col_index == 0:
                    return LEFT_TOP
                else:
                    return RIGHT_TOP
            else:
                if col_index == 0:
                    return LEFT_BOTTOM
                else:
                    return RIGHT_BOTTOM
        else:
            return change_based_on_is_grid_index(
                grid, COL, COL_LEFT if col_index == 0 else COL_RIGHT, row_index
            )
    return ""


styles = {
    "full": {
        "grid": "full",
        "col_sep": COL,
        "row_sep": ROW
    },
    "inner": {
        "grid": "inner",
        "col_sep": COL,
        "row_sep": ROW
    },
    "markdown": {
        "grid": "markdown",
        "col_sep": '|',
        "row_sep": None
    },
    "default": {
        "grid": None,
        "col_sep": "  ",
        "row_sep": None
    },
}


def readable(
    data: dict,
    headers=None,
    grid=None,
    col_sep="  ",
    row_sep=None,
    prefix=" ",
    suffix=" ",
    bars: list = None,
    bar_char="x",
    bar_width=100,
    bar_scale="linal",
):
    """return the printable text of a list of dict"""
    if not grid:
        col_sep = row_sep = ""
    elif grid == 'markdown':
        col_sep = '|'
        row_sep = '-'

    headers = headers or list(data[0].keys())

    max_width_list = [0] * len(headers)
    max_value_dict = {k: 0 for k in headers}

    axis_scale_func = {
        "linal": lambda x: x,
        "ln": math.log,
        "log10": math.log10
    }[bar_scale]

    def _set_max_width(r):
        for i, x in enumerate(r):
            # lock when write for column
            # with locks[i]:
            max_width_list[i] = max(get_text_width(x), max_width_list[i])

    def _set_max_value(r: dict):
        for k, v in r.items():
            if v and k in bars:
                max_value_dict[k] = max(float(v), max_value_dict[k])

    def _parse_text(text, key=None):
        # convert numerics to bar graph
        if text and key and key in bars:
            return bar_char * int(
                axis_scale_func(float(text)) /
                axis_scale_func(max_value_dict[key]) * bar_width
            )

        # parse to string
        return str(text).replace("\n", " ").replace("\t", " ")

    def _set_width_and_return_tuple(r):
        rv = tuple(_parse_text(r[k], key=k) for k in headers)
        return rv

    # set and update max value for every numeric columns
    for r in data:
        _set_max_value(r)

    data = [_set_width_and_return_tuple(r) for r in data]
    rows = [headers] + data

    # set and update max width for every columns
    for r in rows:
        _set_max_width(r)

    # add row lines as data type
    if grid and (row_sep or grid == 'markdown'):
        cal_cell_width = lambda w: w + len(prefix) + len(suffix)
        grid_row = tuple(row_sep * cal_cell_width(w) for w in max_width_list)

        final_rows = []
        for i, r in enumerate(rows):
            if grid == "inner":
                final_rows.append(r)
                if i < len(rows) - 1:
                    final_rows.append(grid_row)
            elif grid == "full":
                final_rows.append(grid_row)
                final_rows.append(r)
                if i == len(rows) - 1:
                    final_rows.append(grid_row)
            elif grid == "markdown":
                if i == 1:
                    final_rows.append(grid_row)
                    final_rows.append(r)
                else:
                    final_rows.append(r)
    else:
        final_rows = rows

    if DEBUG:
        print(final_rows)

    def fn(i, r):
        return "{}{}{}".format(
            _get_row_grid_edge(grid, i, 0, i in [0, len(final_rows) - 1]),
            _get_row_sep(
                grid, col_sep, i, is_edge=i in [0, len(final_rows) - 1]
            ).join(
                table_print_row(
                    r,
                    max_width_list,
                    _get_cell_prefix_or_suffix(grid, prefix, i),
                    _get_cell_prefix_or_suffix(grid, suffix, i),
                )
            ),
            _get_row_grid_edge(grid, i, None, i in [0, len(final_rows) - 1]),
        )

    results = [fn(i, r) for i, r in enumerate(final_rows)]
    return "\n".join(results)


def write_to_less(text, line_numbers):
    less_cmd = ["less", "-S"]
    if line_numbers:
        less_cmd.append("-N")

    p = subprocess.Popen(less_cmd, stdin=subprocess.PIPE)

    try:
        p.stdin.write(text.encode("utf-8"))
    except BrokenPipeError as e:
        print(e)
        sys.exit(1)

    p.communicate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f", "--file", default="/dev/stdin", help="the path of JSON file"
    )
    parser.add_argument(
        "--sep-col", default=COL, help="the sepatrator of columns, e.g. │"
    )
    parser.add_argument(
        "--sep-row", default=ROW, help="the sepatrator of rows, e.g. ─"
    )
    parser.add_argument(
        "--grid",
        default=os.getenv("PRINTABLE_GRID", None),
        choices=["inner", "full", "markdown"],
        help="whether print the grid",
    )
    parser.add_argument(
        "--less",
        default=os.getenv("PRINTABLE_LESS", False),
        action="store_true",
        help="use less to view the output",
    )
    parser.add_argument(
        "-N",
        "--line-numbers",
        default=True,
        action="store_false",
        help="print line numbers when using less",
    )
    parser.add_argument(
        "-t",
        "--type",
        default="json",
        choices=["json", "csv", "yaml"],
        help="the file format",
    )
    parser.add_argument(
        "-b", "--bar", nargs="*", help="convert numeric fields to bar graphs"
    )
    parser.add_argument(
        "-c", "--bar-char", default="o", help="the basic char of bar graph"
    )
    parser.add_argument(
        "-w",
        "--bar-width",
        default=100,
        type=int,
        help="the width of bar graph"
    )
    parser.add_argument(
        "-s",
        "--bar-scale",
        default="linal",
        help="the scale of axis in bar graph",
        choices=["linal", "ln", "log10"],
    )
    args = parser.parse_args()

    if args.grid == 'markdown':
        args.less = False

    try:
        data = {
            "json": read_json,
            "csv": read_csv,
            "yaml": read_yaml
        }[args.type](args.file)
        if DEBUG:
            print(data)

        output = readable(
            data,
            col_sep=args.sep_col,
            row_sep=args.sep_row,
            grid=args.grid,
            bars=args.bar or [],
            bar_char=args.bar_char,
            bar_width=args.bar_width,
            bar_scale=args.bar_scale,
        )
        if args.less:
            write_to_less(output, line_numbers=args.line_numbers)
        else:
            print(output)
    except Exception as e:
        if DEBUG:
            raise
        sys.exit(1)
