import argparse
import gc
import math
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import printable
from printable import readable, render_with_column


@dataclass(frozen=True)
class BenchmarkResult:
    """保存一组渲染耗时。"""

    median_seconds: float
    minimum_seconds: float
    p95_seconds: float


def build_rows(row_count: int, column_count: int) -> list[list[str]]:
    """生成两种渲染器共用的表格数据。"""
    headers = [f'列-{column_index} / column-{column_index}' for column_index in range(column_count)]
    rows = [headers]
    rows.extend(
        [f'值-{row_index}-{column_index} / value-{row_index}-{column_index}' for column_index in range(column_count)]
        for row_index in range(row_count)
    )
    return rows


def serialize_tsv(rows: Sequence[Sequence[str]]) -> str:
    """把表格数据序列化为 column 的输入格式。"""
    return ''.join('\t'.join(row) + '\n' for row in rows)


def measure(
    render: Callable[[], str],
    warmup_count: int,
    repeat_count: int,
) -> BenchmarkResult:
    """预热并测量渲染函数。"""
    for _ in range(warmup_count):
        render()

    was_gc_enabled = gc.isenabled()
    gc.disable()
    try:
        durations = []
        for _ in range(repeat_count):
            start_time = time.perf_counter()
            output = render()
            elapsed_seconds = time.perf_counter() - start_time
            if not output:
                raise RuntimeError('渲染器返回了空结果')
            durations.append(elapsed_seconds)
    finally:
        if was_gc_enabled:
            gc.enable()

    sorted_durations = sorted(durations)
    p95_index = min(len(sorted_durations) - 1, math.ceil(len(sorted_durations) * 0.95) - 1)
    return BenchmarkResult(
        median_seconds=statistics.median(sorted_durations),
        minimum_seconds=sorted_durations[0],
        p95_seconds=sorted_durations[p95_index],
    )


def parse_args() -> argparse.Namespace:
    """解析基准测试参数。"""
    parser = argparse.ArgumentParser(description='比较纯 Python 和 C column wrapper 的渲染性能')
    parser.add_argument('--rows', type=int, default=5000, help='数据行数，默认 5000')
    parser.add_argument('--columns', type=int, default=6, help='列数，默认 6')
    parser.add_argument('--warmup', type=int, default=2, help='预热次数，默认 2')
    parser.add_argument('--repeat', type=int, default=10, help='测量次数，默认 10')
    args = parser.parse_args()
    if args.rows <= 0 or args.columns <= 0 or args.warmup < 0 or args.repeat <= 0:
        parser.error('rows、columns、repeat 必须大于 0，warmup 不能小于 0')
    return args


def print_result(name: str, result: BenchmarkResult) -> None:
    """打印一组基准结果。"""
    print(
        f'{name:<14} median={result.median_seconds * 1000:10.3f} ms '
        f'min={result.minimum_seconds * 1000:10.3f} ms '
        f'p95={result.p95_seconds * 1000:10.3f} ms'
    )


def readable_without_native_widths(rows: Sequence[Sequence[str]]) -> str:
    """以纯 Python 宽度计算渲染，临时禁用 native 宽度库。"""
    saved_widths_of = printable.native_widths_of
    printable.native_widths_of = lambda cells: None
    try:
        return readable(rows)
    finally:
        printable.native_widths_of = saved_widths_of


def main() -> None:
    """对比纯 Python、C 宽度 + Python 渲染与 column 引擎。"""
    args = parse_args()
    rows = build_rows(args.rows, args.columns)
    tsv_input = serialize_tsv(rows)

    python_width_result = measure(lambda: readable_without_native_widths(rows), args.warmup, args.repeat)
    c_width_result = measure(lambda: readable(rows), args.warmup, args.repeat)
    column_result = measure(
        lambda: render_with_column(tsv_input, table=True, separator='\t'),
        args.warmup,
        args.repeat,
    )

    print(f'rows={args.rows} columns={args.columns} repeat={args.repeat} charset=mixed-zh-en')
    print_result('python', python_width_result)
    print_result('python+c-width', c_width_result)
    print_result('c-column', column_result)
    print(
        f'speedup vs python: c-width={python_width_result.median_seconds / c_width_result.median_seconds:.2f}x '
        f'column={python_width_result.median_seconds / column_result.median_seconds:.2f}x'
    )


if __name__ == '__main__':
    main()
