import unittest
from types import SimpleNamespace

from wcwidth import wcswidth

from printable import (
    ANSI_ESCAPE_PATTERN,
    ColumnExecutionError,
    calc_text_width,
    native_widths_of,
    normalize_cell_value,
    readable,
    render_with_column,
    render_with_engine,
)


class NativeColumnTest(unittest.TestCase):
    def test_column_engine_matches_python_default_output(self):
        rows = [
            {'name': 'alpha', 'value': 1},
            {'name': 'beta', 'value': 22},
            {'name': '', 'value': ''},
        ]
        engine_args = SimpleNamespace(
            engine='column',
            grid=None,
            sep_col=None,
            sep_row=None,
            bar=[],
            bar_char='o',
            bar_width=100,
            bar_scale='linal',
            limit=None,
        )

        for separator in (None, '|'):
            engine_args.sep_col = separator
            try:
                output = '\n'.join(render_with_engine(rows, engine_args))
            except FileNotFoundError as error:
                self.skipTest(str(error))

            self.assertEqual(output, readable(rows, col_sep=separator))

    def test_missing_engine_automatically_uses_column(self):
        engine_args = SimpleNamespace(
            grid=None,
            sep_col=None,
            sep_row=None,
            bar=[],
            bar_char='o',
            bar_width=100,
            bar_scale='linal',
            limit=None,
        )

        try:
            output = '\n'.join(render_with_engine([['name'], ['alpha']], engine_args))
        except FileNotFoundError as error:
            self.skipTest(str(error))

        self.assertEqual(output, readable([['name'], ['alpha']]))

    def test_column_engine_rejects_grid_styles(self):
        engine_args = SimpleNamespace(
            engine='column',
            grid='full',
            sep_col=None,
            sep_row=None,
            bar=[],
            bar_char='o',
            bar_width=100,
            bar_scale='linal',
            limit=None,
        )

        with self.assertRaisesRegex(ValueError, '不能与 --grid 同时使用'):
            render_with_engine([['name'], ['alpha']], engine_args)

    def test_renders_with_structured_options(self):
        try:
            output = render_with_column(
                'name\tvalue\nalpha\t1\n',
                table=True,
                separator='\t',
                output_separator='\t',
            )
        except FileNotFoundError as error:
            self.skipTest(str(error))

        self.assertEqual(output, 'name \tvalue\nalpha\t1\n')

    def test_reports_column_exit_code(self):
        try:
            with self.assertRaises(ColumnExecutionError) as context:
                render_with_column('name\n', table=True, table_columns_limit=0)
        except FileNotFoundError as error:
            self.skipTest(str(error))

        self.assertEqual(context.exception.exit_code, 1)

    def test_rejects_unknown_keyword(self):
        with self.assertRaises(TypeError):
            render_with_column('name\n', not_an_option=True)

    def test_native_widths_match_python_wcwidth(self):
        samples = ['abc', '中文', 'a中b', '👍', 'é', '', '\x1b[31m红\x1b[0m', 'a\tb']
        visible = [ANSI_ESCAPE_PATTERN.sub('', normalize_cell_value(sample)) for sample in samples]
        native_widths = native_widths_of(visible)
        if native_widths is None:
            self.skipTest('column 动态库不可用')

        reference_widths = []
        for text in visible:
            width = wcswidth(text)
            reference_widths.append(width if width >= 0 else len(text))
        self.assertEqual(native_widths, reference_widths)

    def test_calc_text_width_matches_reference(self):
        samples = ['abc', '中文', '\x1b[31m红\x1b[0m', 'é', '', 'a\tb']
        for sample in samples:
            visible = ANSI_ESCAPE_PATTERN.sub('', normalize_cell_value(sample))
            width = wcswidth(visible)
            self.assertEqual(calc_text_width(sample), width if width >= 0 else len(visible))


if __name__ == '__main__':
    unittest.main()
