#!/usr/bin/env bash
# burn_subtitles.sh — 字幕烧录到最终视频
# 功能：将 SRT 字幕烧录到视频中，应用指定样式
#
# 用法：
#   ./burn_subtitles.sh <input_mp4> <srt_file> <output_mp4> [style_name]
#
# 参数：
#   input_mp4   - 输入视频（已合成音频）
#   srt_file    - SRT 字幕文件
#   output_mp4  - 输出视频（最终成片）
#   style_name  - 字幕样式：default | cinematic | drama

set -euo pipefail

INPUT="$1"
SRT="$2"
OUTPUT="$3"
STYLE="${4:-default}"

# 字幕样式目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STYLES_DIR="$SCRIPT_DIR/../../assets/subtitle-styles"

# 字体名称（优先使用 Noto Sans CJK SC，降级到系统默认）
FONT_NAME="Noto Sans CJK SC"
if ! fc-list | grep -qi "noto sans cjk" 2>/dev/null; then
    FONT_NAME="sans-serif"
fi

# 根据样式选择参数
case "$STYLE" in
    cinematic)
        # 电影风格：底部居中，较大字体，柔和描边
        FORCE_STYLE="FontName=${FONT_NAME},FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=40"
        ;;
    drama)
        # 短剧风格：底部居中，大字体，粗描边
        FORCE_STYLE="FontName=${FONT_NAME},FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV=25"
        ;;
    default|*)
        # 默认风格
        FORCE_STYLE="FontName=${FONT_NAME},FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=30"
        ;;
esac

# 烧录字幕
# 处理 SRT 文件路径中的特殊字符
SRT_ESCAPED=$(echo "$SRT" | sed "s/'/\\\\'/g")

ffmpeg -y -i "$INPUT" \
    -vf "subtitles='${SRT_ESCAPED}':force_style='${FORCE_STYLE}'" \
    -c:v libx264 -preset medium -crf 20 \
    -c:a copy \
    -movflags +faststart \
    "$OUTPUT" 2>&1

echo "[burn_subtitles] 字幕烧录完成：$OUTPUT"
echo "[burn_subtitles] 样式：$STYLE"
