#!/usr/bin/env bash
# fine_cut.sh — 短剧精剪脚本
# 功能：根据人工反馈对粗剪版本进行精修（裁剪/重排/变速/转场调整/替换镜头）
#
# 用法：
#   ./fine_cut.sh <rough_cut_mp4> <clips_dir> <manifest_json> <storyboard_json> <feedback_json> <output_mp4>
#
# feedback_json 格式：
# [
#   {"type": "trim", "shot_id": 3, "new_duration": 3},
#   {"type": "replace", "shot_id": 5, "new_clip": "clips/shot_5_v2.mp4"},
#   {"type": "reorder", "shot_ids": [1, 3, 2, 4]},
#   {"type": "transition", "shot_id": 4, "new_transition": "fade"},
#   {"type": "speed", "shot_id": 8, "speed_factor": 2.0}
# ]

set -euo pipefail

ROUGH_CUT="$1"
CLIPS_DIR="$2"
MANIFEST="$3"
STORYBOARD="$4"
FEEDBACK="$5"
OUTPUT="$6"

WORK_DIR="$(dirname "$OUTPUT")/working_fine"
mkdir -p "$WORK_DIR"

# 使用 Python 解析反馈并生成 ffmpeg 命令
python3 - "$ROUGH_CUT" "$CLIPS_DIR" "$MANIFEST" "$STORYBOARD" "$FEEDBACK" "$OUTPUT" "$WORK_DIR" <<'PYEOF'
import json
import sys
import os
import subprocess

rough_cut = sys.argv[1]
clips_dir = sys.argv[2]
manifest_path = sys.argv[3]
storyboard_path = sys.argv[4]
feedback_path = sys.argv[5]
output = sys.argv[6]
work_dir = sys.argv[7]

# 加载数据
with open(manifest_path, 'r', encoding='utf-8') as f:
    manifest = json.load(f)
with open(storyboard_path, 'r', encoding='utf-8') as f:
    storyboard = json.load(f)
with open(feedback_path, 'r', encoding='utf-8') as f:
    feedbacks = json.load(f)

# 构建 shot_id -> clip 映射
clip_map = {}
for clip in manifest.get('clips', []):
    if clip.get('status') == 'success':
        clip_map[clip['shot_id']] = os.path.join(clips_dir, clip['clip_path'])

# 获取镜头顺序
shots = storyboard.get('shots', [])
shot_order = [s['shot_id'] for s in shots if s['shot_id'] in clip_map]

# 应用反馈
speed_map = {}      # shot_id -> speed_factor
duration_map = {}   # shot_id -> new_duration
transition_map = {} # shot_id -> new_transition
replace_map = {}    # shot_id -> new_clip_path

for fb in feedbacks:
    fb_type = fb.get('type')
    shot_id = fb.get('shot_id')
    
    if fb_type == 'trim':
        duration_map[shot_id] = fb.get('new_duration', 3)
    elif fb_type == 'replace':
        new_clip = fb.get('new_clip', '')
        if not os.path.isabs(new_clip):
            new_clip = os.path.join(os.path.dirname(manifest_path), '..', new_clip)
        replace_map[shot_id] = new_clip
    elif fb_type == 'reorder':
        new_order = fb.get('shot_ids', [])
        if new_order:
            shot_order = new_order
    elif fb_type == 'transition':
        transition_map[shot_id] = fb.get('new_transition', 'fade')
    elif fb_type == 'speed':
        speed_map[shot_id] = fb.get('speed_factor', 1.0)

# 处理每个镜头
processed_clips = []
for i, shot_id in enumerate(shot_order):
    # 获取片段路径（可能是替换后的）
    clip_path = replace_map.get(shot_id, clip_map.get(shot_id))
    if not clip_path or not os.path.exists(clip_path):
        print(f"[warn] shot {shot_id} clip not found, skipping")
    processed_path = os.path.join(work_dir, f"processed_{i+1}.mp4")
    
    # 构建 ffmpeg 命令
    cmd = ['ffmpeg', '-y', '-i', clip_path]
    
    filters = []
    
    # 变速处理
    if shot_id in speed_map:
        factor = speed_map[shot_id]
        filters.append(f"setpts={1.0/factor}*PTS")
        # 音频变速
        audio_factor = min(factor, 2.0)  # atempo 限制
        filters.append(f"atempo={audio_factor}")
    
    # 裁剪处理
    if shot_id in duration_map:
        new_dur = duration_map[shot_id]
        cmd.extend(['-t', str(new_dur)])
    
    if filters:
        cmd.extend(['-vf', ','.join(filters)])
    
    cmd.extend([
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
        '-r', '30',
        '-vf', f"scale=trunc(iw/2)*2:trunc(ih/2)*2{''.join([','+f for f in filters])}" if filters else 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
        processed_path
    ])
    
    # 修正 filter 语法
    vf_parts = ['scale=trunc(iw/2)*2:trunc(ih/2)*2']
    if shot_id in speed_map:
        factor = speed_map[shot_id]
        vf_parts.append(f"setpts={1.0/factor}*PTS")
    
    cmd = ['ffmpeg', '-y', '-i', clip_path]
    if shot_id in duration_map:
        cmd.extend(['-t', str(duration_map[shot_id])])
    cmd.extend(['-vf', ','.join(vf_parts)])
    cmd.extend([
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
        '-r', '30',
        processed_path
    ])
    
    print(f"[fine_cut] processing shot {shot_id} -> {processed_path}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[error] shot {shot_id} processing failed: {result.stderr[-200:]}")
        # 降级：直接复制原片段
        subprocess.run(['ffmpeg', '-y', '-i', clip_path,
                       '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                       '-c:a', 'aac', '-b:a', '128k',
                       '-r', '30',
                       '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                       processed_path], capture_output=True)
    
    processed_clips.append(processed_path)

# 生成 concat list 并拼接
concat_file = os.path.join(work_dir, 'fine_concat.txt')
with open(concat_file, 'w') as f:
    for pc in processed_clips:
        f.write(f"file '{os.path.abspath(pc)}'\n")

# 最终拼接
final_cmd = [
    'ffmpeg', '-y',
    '-f', 'concat', '-safe', '0',
    '-i', concat_file,
    '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
    '-c:a', 'aac', '-b:a', '128k',
    '-movflags', '+faststart',
    output
]

print(f"[fine_cut] final concat -> {output}")
result = subprocess.run(final_cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"[error] final concat failed: {result.stderr[-500:]}")
    sys.exit(1)

# 获取输出时长
probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', output]
result = subprocess.run(probe_cmd, capture_output=True, text=True)
duration = result.stdout.strip() if result.returncode == 0 else 'unknown'

print(f"[fine_cut] 精剪完成：{output}")
print(f"[fine_cut] 时长：{duration}s")
print(f"[fine_cut] 处理镜头数：{len(processed_clips)}")
PYEOF
