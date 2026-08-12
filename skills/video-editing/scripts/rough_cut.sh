#!/usr/bin/env bash
# rough_cut.sh — 短剧粗剪脚本
# 功能：按分镜顺序拼接视频片段，添加基础转场，生成粗剪版
#
# 用法：
#   ./rough_cut.sh <clips_dir> <manifest_json> <storyboard_json> <output_mp4> <transition_style>
#
# 参数：
#   clips_dir       - 视频片段目录（含 shot_N.mp4）
#   manifest_json   - 片段清单 JSON
#   storyboard_json - 分镜脚本 JSON
#   output_mp4      - 输出文件路径
#   transition_style - 转场风格：cut | fade | dissolve

set -euo pipefail

CLIPS_DIR="$1"
MANIFEST="$2"
STORYBOARD="$3"
OUTPUT="$4"
TRANSITION="${5:-cut}"

# 工作目录
WORK_DIR="$(dirname "$OUTPUT")/working_rough"
mkdir -p "$WORK_DIR"

# 从 storyboard.json 提取镜头顺序和转场信息
# 使用 python3 解析 JSON
python3 - "$STORYBOARD" "$MANIFEST" "$WORK_DIR" <<'PYEOF'
import json
import sys
import os

storyboard_path = sys.argv[1]
manifest_path = sys.argv[2]
work_dir = sys.argv[3]

with open(storyboard_path, 'r', encoding='utf-8') as f:
    storyboard = json.load(f)

with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)

# 构建 shot_id -> clip_path 映射
clip_map = {}
for clip in manifest.get('clips', []):
    if clip.get('status') == 'success':
        clip_map[clip['shot_id']] = clip['clip_path']

# 按 storyboard 顺序输出有效镜头列表
shots = storyboard.get('shots', [])
valid_shots = []
for shot in shots:
    shot_id = shot['shot_id']
    if shot_id in clip_map:
        valid_shots.append({
            'shot_id': shot_id,
            'clip_path': clip_map[shot_id],
            'transition': shot.get('transition_to_next', 'cut'),
            'duration': shot.get('duration_seconds', 5)
        })

# 写入有效镜头列表
with open(os.path.join(work_dir, 'valid_shots.json'), 'w', encoding='utf-8') as f:
    json.dump(valid_shots, f, ensure_ascii=False, indent=2)

# 生成 concat list 文件
concat_file = os.path.join(work_dir, 'concat_list.txt')
with open(concat_file, 'w', encoding='utf-8') as f:
    for vs in valid_shots:
        clip_path = vs['clip_path']
        if not os.path.isabs(clip_path):
            clip_path = os.path.join(os.path.dirname(manifest_path), '..', clip_path)
        f.write(f"file '{os.path.abspath(clip_path)}'\n")

print(f"valid_shots: {len(valid_shots)}")
print(f"concat_list: {concat_file}")
PYEOF

CONCAT_LIST="$WORK_DIR/concat_list.txt"

if [ "$TRANSITION" = "cut" ]; then
    # 简单拼接：使用 concat demuxer
    ffmpeg -y -f concat -safe 0 -i "$CONCAT_LIST" \
        -c:v libx264 -preset fast -crf 23 \
        -c:a aac -b:a 128k \
        -movflags +faststart \
        "$OUTPUT" 2>&1 || {
        # 如果直接 concat 失败（编码不一致），重新编码每个片段再拼接
        echo "[rough_cut] 直接拼接失败，尝试重新编码后拼接..."
        REENCODE_DIR="$WORK_DIR/reencoded"
        mkdir -p "$REENCODE_DIR"
        
        while IFS= read -r line; do
            # 解析 file 路径
            clip_path=$(echo "$line" | sed "s/^file '//;s/'$//")
            clip_name=$(basename "$clip_path" .mp4)
            ffmpeg -y -i "$clip_path" \
                -c:v libx264 -preset fast -crf 23 \
                -c:a aac -b:a 128k -ar 44100 \
                -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
                -r 30 \
                "$REENCODE_DIR/${clip_name}.mp4" 2>&1
        done < "$CONCAT_LIST"
        
        # 生成新的 concat list
        REENCODE_LIST="$WORK_DIR/concat_reencoded.txt"
        > "$REENCODE_LIST"
        for f in "$REENCODE_DIR"/*.mp4; do
            echo "file '$(abspath "$f")'" >> "$REENCODE_LIST"
        done
        
        ffmpeg -y -f concat -safe 0 -i "$REENCODE_LIST" \
            -c copy \
            -movflags +faststart \
            "$OUTPUT" 2>&1
    }
else
    # 带转场：使用 xfade filter（复杂，这里简化为逐个片段 reencode + xfade）
    # 对于粗剪，简化处理：先 concat 再加全局 fade in/out
    ffmpeg -y -f concat -safe 0 -i "$CONCAT_LIST" \
        -c:v libx264 -preset fast -crf 23 \
        -c:a aac -b:a 128k \
        -vf "fade=t=in:st=0:d=0.5,fade=t=out:st=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$CONCAT_LIST" 2>/dev/null || echo 0):d=0.5" \
        -movflags +faststart \
        "$OUTPUT" 2>&1
    
    echo "[rough_cut] 已添加 fade in/out 转场"
fi

# 获取输出视频信息
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTPUT" 2>/dev/null || echo "unknown")
echo "[rough_cut] 粗剪完成：$OUTPUT"
echo "[rough_cut] 时长：${DURATION}s"
