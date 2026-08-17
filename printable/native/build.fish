#!/usr/bin/env fish

function fail
    echo "错误: $argv" >&2
    exit 1
end

if test (count $argv) -lt 1
    fail '用法: printable/native/build.fish macos|linux [arm64|x86_64]'
end

set -l target (string lower -- $argv[1])
set -l architecture $argv[2]
set -l script_directory (dirname (status filename))
set -l project_root (cd "$script_directory/../.."; and pwd)
set -l native_directory "$project_root/printable/native"
set -l util_linux_directory "$project_root/util-linux"

if not contains -- $target macos linux
    fail "不支持目标平台 '$target'，仅支持 macos 和 linux"
end

if test -z "$architecture"
    if test "$target" = macos
        set architecture (uname -m)
    else
        set architecture x86_64
    end
end

if command -q brew
    set -l bison_prefix (brew --prefix bison 2>/dev/null)
    if test -x "$bison_prefix/bin/bison"
        set -gx PATH "$bison_prefix/bin" $PATH
    end
end

set -l host_triplet
set -l compiler_command
set -l compiler_flags -O2 -g0 -fPIC -fvisibility=hidden -ffunction-sections -fdata-sections
set -l wrapper_link_flags
set -l library_suffix
set -l system_libraries -lm

if test "$target" = macos
    if not contains -- $architecture arm64 x86_64
        fail "macOS 架构 '$architecture' 不受支持"
    end

    set host_triplet (test "$architecture" = arm64; and echo aarch64-apple-darwin; or echo x86_64-apple-darwin)
    set compiler_command clang
    set compiler_flags $compiler_flags -arch $architecture
    set wrapper_link_flags \
        -dynamiclib \
        -Wl,-dead_strip \
        -Wl,-install_name,@rpath/libcolumn.dylib \
        -Wl,-exported_symbol,_column_render \
        -Wl,-exported_symbol,_column_result_free
    set library_suffix dylib
    set system_libraries -lncurses -lm

else
    if not contains -- $architecture x86_64 aarch64
        fail "Linux 架构 '$architecture' 不受支持"
    end
    if not command -q zig
        fail 'Linux 交叉编译需要 zig'
    end

    set host_triplet "$architecture-linux-gnu"
    set compiler_command zig cc -target $host_triplet
    set compiler_flags $compiler_flags -pthread
    set wrapper_link_flags -shared -Wl,--gc-sections
    set library_suffix so
end

if not command -q bison
    fail '缺少 bison'
end
if not command -q flex
    fail '缺少 flex'
end
set -l bison_command (command -v bison)

git -C "$project_root" submodule update --init --depth=1 util-linux
or fail '无法初始化 util-linux submodule'

if not test -x "$util_linux_directory/configure"
    begin
        cd "$util_linux_directory"
        ./autogen.sh
    end
    or fail '无法生成 util-linux configure'
end

set -lx CC (string join -- ' ' $compiler_command)
set -lx CFLAGS (string join -- ' ' $compiler_flags)
set -lx LDFLAGS ''
if test "$target" = linux
    set -lx AR 'zig ar'
    set -lx RANLIB 'zig ranlib'
end

set -l artifact_directory "$project_root/build/native/$target-$architecture"
set -l util_build_directory "$artifact_directory/util-linux"
mkdir -p "$util_build_directory" "$artifact_directory"

set -l configure_options \
    --disable-nls \
    --disable-shared \
    --enable-static \
    --disable-asciidoc \
    --disable-poman \
    "--host=$host_triplet" \
    "--prefix=$artifact_directory/sysroot"

if not test -f "$util_build_directory/Makefile"
    begin
        cd "$util_build_directory"
        "$util_linux_directory/configure" $configure_options
    end
    or fail 'util-linux configure 失败'
end

set -l jobs 2
if test "$target" = macos; and command -q sysctl
    set jobs (sysctl -n hw.ncpu)
else if command -q nproc
    set jobs (nproc)
end

set -l make_tool_options BISON="$bison_command"
if test "$target" = linux
    set make_tool_options $make_tool_options AR='zig ar' RANLIB='zig ranlib'
end

make -C "$util_build_directory" -j $jobs $make_tool_options libcommon.la libsmartcols.la libtcolors.la
or fail 'util-linux 依赖库编译失败'

set -l wrapper_source "$native_directory/column_entry.c"
set -l wrapper_library "$artifact_directory/libcolumn.$library_suffix"
set -l include_flags \
    -I"$native_directory" \
    -I"$util_linux_directory/include" \
    -I"$util_linux_directory/libsmartcols/src" \
    -I"$util_build_directory" \
    -I"$util_build_directory/libsmartcols/src"
set -l compile_flags \
    -std=gnu23 \
    -DHAVE_CONFIG_H \
    -include "$util_build_directory/config.h" \
    -fvisibility=hidden \
    $compiler_flags
set -l static_libraries \
    "$util_build_directory/.libs/libcommon.a" \
    "$util_build_directory/.libs/libsmartcols.a" \
    "$util_build_directory/.libs/libtcolors.a"
$compiler_command $compile_flags $include_flags $wrapper_link_flags \
    "$wrapper_source" $static_libraries -o "$wrapper_library" $system_libraries
or fail 'column wrapper 编译失败'

echo "已生成: $wrapper_library"
