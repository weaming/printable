import unittest

from printable import ColumnExecutionError, render_with_column


class NativeColumnTest(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
