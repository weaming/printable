"""
Usage Example:

    from printable import readable, styles
    readable(list_of_dict, **styles['full'])
"""
import json
import sys
import string
import subprocess
import os

from data_process.io_json import read_json
from data_process.io_csv import read_csv
from data_process.io_yaml import read_yaml, save_yaml

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


def get_text_width(text):
    """get the print width of text accordding to whether it's printable ascii except the blank ' '"""
    if not str(text):
        return 0

    # parse to string
    text = str(text)

    assert not any(
        x in string.whitespace.replace(" ", "") for x in text
    ), "text should not contains whitespace: '{}'".format(text)

    def _width(x):
        if x in string.ascii_letters + string.digits + string.punctuation + " ":
            return 1
        else:
            return 2

    rv = 0
    for x in text:
        rv += _width(x)
    return rv


def get_max_width(data):
    """get the maximum widths of every columns"""

    def _set(lst, index, x):
        if len(lst) < index + 1:
            lst += [None] * (index + 1 - len(lst))
        lst[index] = x
        return lst

    def _index(lst, index, default):
        try:
            return lst[index]
        except IndexError:
            return default

    rv = []
    for r in data:
        for i, x in enumerate(r):
            _set(rv, i, max(get_text_width(x), _index(rv, i, 0)))
    return rv


def table_print_row(lst, max_width_list, prefix=" ", suffix=" "):
    """just print a row data in the format of list"""
    return [
        "{}{}{}{}".format(
            prefix, x, " " * (max_width_list[i] - get_text_width(x)), suffix
        )
        for i, x in enumerate(lst)
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
    ), 'grid must be in [None, "inner", "full"], got {}'.format(grid)


def _get_cell_prefix_or_suffix(grid, fix, index):
    _check_grid(grid)
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
    "full": {"grid": "full", "col_sep": COL, "row_sep": ROW},
    "inner": {"grid": "inner", "col_sep": COL, "row_sep": ROW},
    "default": {"grid": None, "col_sep": "  ", "row_sep": None},
}


def readable(
    data: dict,
    headers=None,
    grid=None,
    col_sep="  ",
    row_sep=None,
    prefix=" ",
    suffix=" ",
):
    """return the printable text of a list of dict"""
    if not grid:
        col_sep = row_sep = ""

    headers = headers or list(data[0].keys())
    data = [tuple(r[k] for k in headers) for r in data]
    rows = [headers] + data
    max_width_list = get_max_width(rows)

    # add row lines as data type
    if grid and row_sep:
        grid_row_list = [
            tuple(
                row_sep * (max_width_list[j] + len(prefix) + len(suffix))
                for j in range(len(max_width_list))
            )
        ] * len(rows)

        final_rows = []

        for i, r in enumerate(rows):
            if grid == "inner":
                final_rows.append(r)
                if i < len(rows) - 1:
                    final_rows.append(grid_row_list[i])
            elif grid == "full":
                final_rows.append(grid_row_list[i])
                final_rows.append(r)
                if i == len(rows) - 1:
                    final_rows.append(grid_row_list[i])
    else:
        final_rows = rows

    if DEBUG:
        print(final_rows)

    return "\n".join(
        "{}{}{}".format(
            _get_row_grid_edge(grid, i, 0, i in [0, len(final_rows) - 1]),
            _get_row_sep(grid, col_sep, i, is_edge=i in [0, len(final_rows) - 1]).join(
                table_print_row(
                    r,
                    max_width_list,
                    _get_cell_prefix_or_suffix(grid, prefix, i),
                    _get_cell_prefix_or_suffix(grid, suffix, i),
                )
            ),
            _get_row_grid_edge(grid, i, 99, i in [0, len(final_rows) - 1]),
        )
        for i, r in enumerate(final_rows)
    )


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
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f", "--file", default="/dev/stdin", help="the path of JSON file"
    )
    parser.add_argument(
        "--sep-col", default=COL, help="the sepatrator of columns, e.g. │"
    )
    parser.add_argument("--sep-row", default=ROW, help="the sepatrator of rows, e.g. ─")
    parser.add_argument(
        "--grid",
        default=os.getenv("PRINTABLE_GRID", None),
        choices=["inner", "full"],
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
    args = parser.parse_args()

    try:
        data = {"json": read_json, "csv": read_csv, "yaml": read_yaml}[args.type](
            args.file
        )
        if DEBUG:
            print(data)
        output = readable(
            data, col_sep=args.sep_col, row_sep=args.sep_row, grid=args.grid
        )
        if args.less:
            write_to_less(output, line_numbers=args.line_numbers)
        else:
            print(output)
    except Exception as e:
        print(e)
        sys.exit(1)
