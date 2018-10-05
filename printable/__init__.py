import json
import sys
import string

CROSS = "┼"
ROW = "─"
COL = "│"


def get_text_width(text):
    """get the print width of text accordding to whether it's printable ascii excep the blank ' '"""
    if not text:
        return 0

    assert not all(
        x in string.whitespace for x in text.replace(" ", "-")
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
    assert grid in (None, "odd", "even")
    if grid:
        if grid == "odd" and index % 2 == 1:
            return wanted
        if grid == "even" and index % 2 == 0:
            return wanted
    return origin


def readble(
    data: dict,
    headers=None,
    col_sep="  ",
    row_sep=None,
    grid=False,
    prefix=" ",
    suffix=" ",
):
    """return the printable text of a list of dict"""
    if not grid:
        col_sep = row_sep = ""
    else:
        grid = "odd"

    def _get_x_fix(grid, fix, index):
        assert grid in (None, "odd", "even")
        return change_based_on_is_grid_index(grid, fix, "", index)

    def _get_col_sep(grid, sep, index):
        assert grid in (None, "odd", "even")
        return change_based_on_is_grid_index(grid, sep, CROSS, index)

    headers = headers or list(data[0].keys())
    data = [tuple(r[k] for k in headers) for r in data]
    rows = [headers] + data
    max_width_list = get_max_width(rows)

    if row_sep:
        row_sep_list = [
            tuple(
                row_sep * (max_width_list[j] + len(prefix) + len(suffix))
                for j in range(len(max_width_list))
            )
        ] * len(rows)
        final_rows = []
        for i, r in enumerate(rows):
            final_rows.append(r)
            if i < len(rows) - 1:
                final_rows.append(row_sep_list[i])
    else:
        final_rows = rows

    return "\n".join(
        _get_col_sep(grid, col_sep, i).join(
            table_print_row(
                r,
                max_width_list,
                _get_x_fix(grid, prefix, i),
                _get_x_fix(grid, suffix, i),
            )
        )
        for i, r in enumerate(final_rows)
    )


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="the path of JSON file")
    parser.add_argument(
        "--sep-col", default=COL, help="the sepatrator of columns, e.g. │"
    )
    parser.add_argument("--sep-row", default=ROW, help="the sepatrator of rows, e.g. ─")
    parser.add_argument(
        "--grid", default=False, action="store_true", help="whether print the grid"
    )
    args = parser.parse_args()

    try:
        with open(args.file) as f:
            print(
                readble(
                    json.load(f),
                    col_sep=args.sep_col,
                    row_sep=args.sep_row,
                    grid=args.grid,
                )
            )
    except Exception as e:
        print(e)
        sys.exit(1)
