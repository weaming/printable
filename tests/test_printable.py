import os
import tempfile
import unittest

from printable import read_csv, readable


class PrintableTest(unittest.TestCase):
    def test_csv_supports_bom_quotes_and_embedded_newline(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", delete=False) as file:
            file.write('name,note\r\nA,"one, two\r\nthree"\r\n')
            path = file.name
        try:
            self.assertEqual(read_csv(path), [{"name": "A", "note": "one, two\r\nthree"}])
        finally:
            os.unlink(path)

    def test_csv_rejects_invalid_headers_and_extra_columns(self):
        for content, message in (("name,name\nA,B\n", "表头不能重复"), ("name\nA,extra\n", "列数超过表头")):
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as file:
                file.write(content)
                path = file.name
            try:
                with self.assertRaisesRegex(ValueError, message):
                    read_csv(path)
            finally:
                os.unlink(path)

    def test_full_grid_has_complete_border_by_default(self):
        output = readable([["name"], ["A"]], grid="full")
        self.assertEqual(output.splitlines()[0], "┌──────┐")
        self.assertEqual(output.splitlines()[-1], "└──────┘")

    def test_markdown_escapes_column_separator(self):
        output = readable([["name"], ["left|right"]], grid="markdown")
        self.assertIn("left\\|right", output)

    def test_generator_numeric_headers_and_limit_zero(self):
        data = (row for row in [[1], ["A"], ["B"]])
        self.assertEqual(readable(data, limit=0), " 1 ")

    def test_bar_chart_handles_negative_and_fractional_log_values(self):
        negative = readable([["metric"], ["-1"], ["2"]], bars=["metric"], bar_width=4)
        fractional = readable([["metric"], ["0.1"], ["0.5"]], bars=["metric"], bar_width=4, bar_scale="ln")
        self.assertIn("-xx", negative)
        self.assertNotIn("xxxxxxxxxxxxx", fractional)

    def test_invalid_grid_and_negative_limit_raise_clear_errors(self):
        with self.assertRaisesRegex(ValueError, "不支持的 grid"):
            readable([["name"], ["A"]], grid="unknown")
        with self.assertRaisesRegex(ValueError, "limit 不能小于 0"):
            readable([["name"], ["A"]], limit=-1)
