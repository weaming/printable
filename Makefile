.PHONY: bench publish

# 发布时构建的 native 平台组合（与 column.py 的 _target_name 目录名一致）
NATIVE_LIBS := \
	build/native/macos-arm64/libcolumn.dylib \
	build/native/macos-x86_64/libcolumn.dylib \
	build/native/linux-x86_64/libcolumn.so \
	build/native/linux-aarch64/libcolumn.so

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

publish: publish-prepare
	uv publish

# 为所有平台构建 native 库并复制进包内（wheel 打包需要），最后发布 PyPI（需配置 UV_PUBLISH_TOKEN）
publish-prepare: $(NATIVE_LIBS)
	for lib in $(NATIVE_LIBS); do \
		target=$$(basename $$(dirname $$lib)); \
		mkdir -p printable/native/lib/$$target; \
		cp $$lib printable/native/lib/$$target/; \
	done
	uv build

build/native/macos-%/libcolumn.dylib:
	./printable/native/build.fish macos $*

build/native/linux-%/libcolumn.so:
	./printable/native/build.fish linux $*
