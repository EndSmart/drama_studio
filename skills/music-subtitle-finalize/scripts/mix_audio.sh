#!/usr/bin/env bash
# mix_audio.sh — 音视频合成脚本
# 功能：将视频、配音、配乐混合为最终音视频
#
# 用法：
#   ./mix_audio.sh <video_mp4> <voiceover_dir> <music_dir> <music_plan_json> <output_mp4> [voice_volume] [music_volume]
#
# 参数：
#   video_mp4       - 输入视频（精剪版）
#   voiceover_dir   - 配音目录（含 shot_N_角色.wav）
#   music_dir       - 配乐目录（含 segment_N.mp3）
#   music_plan_json - 配乐计划 JSON
#   output_mp4      - 输出视频
#   voice_volume    - 配音音量（默认 1.0）
#   music_volume    - 配乐音量（默认 0.3）

set -euo pipefail

VIDEO="$1"
VOICEOVER_DIR="$2"
MUSIC_DIR="$3"
MUSIC_PLAN="$4"
OUTPUT="$5"
VOICE_VOL="${6:-1.0}"
MUSIC_VOL="${7:-0.3}"

WORK_DIR="$(dirname "$OUTPUT")/working_mix"
mkdir -p "$WORK_DIR"

# 获取视频时长
VIDEO_DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO" 2>/dev/null || echo "60")
echo "[mix_audio] 视频时长：${VIDEO_DURATION}s"

# Step 1: 合并所有配音为一条音轨
VOICEOVER_ALL="$WORK_DIR/voiceover_all.wav"
VOICE_LIST="$WORK_DIR/voice_list.txt"
> "$VOICE_LIST"

if [ -d "$VOICEOVER_DIR" ] && ls "$VOICEOVER_DIR"/*.wav >/dev/null 2>&1; then
    # 按文件名排序合并配音
    for f in $(ls "$VOICEOVER_DIR"/*.wav | sort); do
        echo "file '$(abspath "$f")'" >> "$VOICE_LIST"
    done
    ffmpeg -y -f concat -safe 0 -i "$VOICE_LIST" \
        -c:a pcm_s16le -ar 44100 \
        "$VOICEOVER_ALL" 2>&1
    echo "[mix_audio] 配音合并完成"
else
    # 无配音，生成静音音轨
    ffmpeg -y -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=44100" \
        -t "$VIDEO_DURATION" \
        "$VOICEOVER_ALL" 2>&1
    echo "[mix_audio] 无配音，使用静音音轨"
fi

# Step 2: 按配乐计划混合配乐
MUSIC_ALL="$WORK_DIR/music_all.wav"

# 使用 Python 解析 music_plan 并生成配乐混合
python3 - "$MUSIC_PLAN" "$MUSIC_DIR" "$WORK_DIR" "$VIDEO_DURATION" "$MUSIC_ALL" "$MUSIC_VOL" <<'PYEOF'
import json
import sys
import os
import subprocess

music_plan_path = sys.argv[1]
music_dir = sys.argv[2]
work_dir = sys.argv[3]
video_duration = float(sys.argv[4])
output_music = sys.argv[5]
music_vol = float(sys.argv[6])

with open(music_plan_path, 'r', encoding='utf-8') as f:
    music_plan = json.load(f)

segments = music_plan.get('segments', [])

if not segments:
    # 无配乐段落，生成静音
    cmd = ['ffmpeg', '-y', '-f', 'lavfi',
           '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
           '-t', str(video_duration),
           '-c:a', 'pcm_s16le',
           output_music]
    subprocess.run(cmd, capture_output=True)
    print("[mix_audio] 无配乐段落，使用静音")
    sys.exit(0)

# 为每段配乐添加延迟并混合
delay_inputs = []
filter_parts = []
for i, seg in enumerate(segments):
    shot_range = seg.get('shot_range', [0, 0])
    # 估算起始时间（每镜头 5 秒）
    start_time = shot_range[0] * 5
    seg_duration = seg.get('duration_seconds', 25)
    
    # 查找配乐文件
    music_file = os.path.join(music_dir, f"segment_{i+1}.mp3")
    if not os.path.exists(music_file):
        # 尝试其他命名
        for ext in ['.mp3', '.wav', '.aac', '.m4a']:
            candidate = os.path.join(music_dir, f"segment_{i+1}{ext}")
            if os.path.exists(candidate):
                music_file = candidate
                break
        else:
            print(f"[warn] 配乐段 {i+1} 文件不存在，跳过")
            continue
    
    delay_inputs.extend(['-i', music_file])
    # 延迟（毫秒）
    delay_ms = int(start_time * 1000)
    filter_parts.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms},volume={music_vol}[m{i}]")

# 混合所有配乐段
mix_inputs = ''.join([f"[m{i}]" for i in range(len(filter_parts))])
filter_complex = ';'.join(filter_parts) + f";{mix_inputs}amix=inputs={len(filter_parts)}:duration=longest:dropout_transition=0[mixed]"

cmd = ['ffmpeg', '-y'] + delay_inputs + [
    '-filter_complex', filter_complex,
    '-map', '[mixed]',
    '-c:a', 'pcm_s16le', '-ar', '44100',
    '-t', str(video_duration),
    output_music
]

print(f"[mix_audio] 混合 {len(filter_parts)} 段配乐")
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"[error] 配乐混合失败: {result.stderr[-300:]}")
    # 降级：静音
    cmd = ['ffmpeg', '-y', '-f', 'lavfi',
           '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
           '-t', str(video_duration),
           '-c:a', 'pcm_s16le',
           output_music]
    subprocess.run(cmd, capture_output=True)
PYEOF

echo "[mix_audio] 配乐混合完成"

# Step 3: 混合视频 + 配音 + 配乐
ffmpeg -y -i "$VIDEO" -i "$VOICEOVER_ALL" -i "$MUSIC_ALL" \
    -filter_complex "[1:a]volume=${VOICE_VOL}[voice];[2:a]volume=${MUSIC_VOL}[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=0[aout]" \
    -map 0:v -map "[aout]" \
    -c:v copy \
    -c:a aac -b:a 192k \
    -movflags +faststart \
    "$OUTPUT" 2>&1

echo "[mix_audio] 音视频合成完成：$OUTPUT"
echo "[mix_audio] 配音音量：$VOICE_VOL / 配乐音量：$MUSIC_VOL"
