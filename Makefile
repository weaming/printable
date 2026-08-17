.PHONY: bench

test:
	uv run python -m printable -t csv -f samples/sample.csv -e python
	uv run python -m printable -t csv -f samples/sample.csv -e column
	uv run python -m printable -t csv -f samples/sample.csv --grid inner
	uv run python -m printable -t csv -f samples/sample.csv --grid full
	uv run python -m printable -t csv -f samples/sample.csv --grid markdown
	uv run python -m printable -t json -e python -f samples/kline-qqq.json
	uv run python -m printable -t json -e column -f samples/kline-qqq.json

bench:
	uv run python bench/column.py
