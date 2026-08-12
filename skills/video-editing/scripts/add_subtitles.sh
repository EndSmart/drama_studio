#!/usr/bin/env bash
# add_subtitles.sh — 字幕烧录脚本
# 功能：将 SRT/ASS 字幕烧录到视频中
#
# 用法：
#   ./add_subtitles.sh <input_mp4> <subtitle_file> <output_mp4> [subtitle_style]
#
# 参数：
#   input_mp4       - 输入视频
#   subtitle_file   - 字幕文件（.srt 或 .ass）
#   output_mp4      - 输出视频
#   subtitle_style  - 字幕样式名：default | cinematic | drama（对应 assets/subtitle-styles/ 下的 .ass）

set -euo pipefail

INPUT="$1"
SUBTITLE="$2"
OUTPUT="$3"
STYLE="${4:-default}"

# 字幕样式目录（相对于本脚本）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STYLES_DIR="$SCRIPT_DIR/../../assets/subtitle-styles"

# 获取输入视频时长
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$INPUT" 2>/dev/null || echo "0")

# 判断字幕类型
SUB_EXT="${SUBTITLE##*.}"

if [ "$SUB_EXT" = "ass" ]; then
    # ASS 字幕直接烧录（含样式）
    ffmpeg -y -i "$INPUT" \
        -vf "ass='$SUBTITLE'" \
        -c:v libx264 -preset fast -crf 23 \
        -c:a copy \
        -movflags +faststart \
        "$OUTPUT" 2>&1

elif [ "$SUB_EXT" = "srt" ]; then
    # SRT 字幕烧录，应用样式
    # 如果指定了 ass 样式模板，先转换；否则用 subtitles filter + force_style
    ASS_TEMPLATE="$STYLES_DIR/${STYLE}.ass"
    
    if [ -f "$ASS_TEMPLATE" ]; then
        # 使用 ass 样式模板：先提取样式头，再拼接 SRT 内容
        # 简化处理：直接用 subtitles filter + force_style
        ffmpeg -y -i "$INPUT" \
            -vf "subtitles='$SUBTITLE':force_style='FontName=Noto Sans CJK SC,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=30'" \
            -c:v libx264 -preset fast -crf 23 \
            -c:a copy \
            -movflags +faststart \
            "$OUTPUT" 2>&1
    else
        # 默认样式
        ffmpeg -y -i "$INPUT" \
            -vf "subtitles='$SUBTITLE':force_style='FontName=Noto Sans CJK SC,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=30'" \
            -c:v libx264 -preset fast -crf 23 \
            -c:a copy \
            -movflags +faststart \
            "$OUTPUT" 2>&1
    fi
else
    echo "[error] 不支持的字幕格式：$SUB_EXT（仅支持 .srt 和 .ass）"
    exit 1
fi

echo "[add_subtitles] 字幕烧录完成：$OUTPUT"
echo "[add_subtitles] 样式：$STYLE"
