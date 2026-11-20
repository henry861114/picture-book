#!/bin/bash
set -euo pipefail

# 从完整副本同步二进制资产到本仓库,使本仓库可以直接 ./build_level_app.sh N 编译。
# 依次尝试: 命令行参数 > ../magic-tool-for-english > ../英语/GreenIslandAndroid
# 用法: ./sync_assets.sh            (自动找源)
#       ./sync_assets.sh /path/to/full/copy

DST="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-}"
if [ -z "$SRC" ]; then
    if [ -d "$DST/../magic-tool-for-english/app/src/main/assets/oxford/pdf" ]; then
        SRC="$DST/../magic-tool-for-english"
    fi
fi
SRC="${SRC%/}"

if [ ! -d "$SRC/app/src/main/assets/oxford/pdf" ]; then
    echo "错误: $SRC 下没有 app/src/main/assets/oxford/pdf — 请传入完整副本路径"
    exit 1
fi

A_SRC="$SRC/app/src/main/assets"
A_DST="$DST/app/src/main/assets"
mkdir -p "$A_DST/oxford"

echo "==> 同步二进制资产(仅复制仓库缺失的文件)..."
rsync -a "$A_SRC/home_hero.jpg" "$A_DST/"
rsync -a "$A_SRC/oxford/pdf/"      "$A_DST/oxford/pdf/"
rsync -a "$A_SRC/oxford/audio/"    "$A_DST/oxford/audio/"
rsync -a "$A_SRC/oxford/covers/"   "$A_DST/oxford/covers/"
# 文本数据以本仓库为准(仓库是权威源),不覆盖:
echo "==> 完成。注意: 这些文件已被 .gitignore 排除,不会进入 git。"
du -sh "$A_DST/oxford/pdf" "$A_DST/oxford/audio" "$A_DST/oxford/covers"
