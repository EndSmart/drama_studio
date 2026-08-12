---
name: music-subtitle-finalize
description: "Stage 8 配乐 + 字幕 + 成片能力：配乐获取/生成（三选一） + 字幕生成（二选一） + 配音（sag TTS） + 音视频合成 + 字幕烧录，输出最终成片 final_drama.mp4。由 finalize-agent 加载执行。"
---

# Music + Subtitle + Finalize — Stage 8 配乐 + 字幕 + 成片

> **职责**：将 S7 精剪成片配以与剧情对齐的音乐、字幕和（可选）配音，合成并烧录为最终交付的 `final_drama.mp4`。
>
> **核心工具**：sag (ElevenLabs TTS) / openai-whisper-api / ffmpeg (adelay + amix + libass) / generate_srt.py / agent-browser (Suno)。
>
> **边界**：S8 是链路终点。不回溯上游 Stage，不修改 fine_cut.mp4 的视频内容。只在视频上叠加音频轨道和字幕。
>
> **执行者**：`finalize-agent`（详见 `../../agents/finalize-agent.md`），本文件为能力声明，不展开执行细节。

---

## 配乐获取：三选一策略

根据 `music_plan.json` 中每个 segment 的 `source` 字段选择获取方式：

| source | 方式 | 说明 |
|--------|------|------|
| `suno` | Suno 浏览器生成 | 使用 agent-browser 访问 Suno，按 mood/tempo/instruments 构造 prompt 生成音乐 |
| `library` | ffmpeg 已有音频 | 从已有音频素材库匹配 → ffmpeg 截取到 segment 时长 |
| `user_provided` | 用户上传 | 用户提供的音乐文件，ffmpeg 截取/循环到 segment 时长 |

`source=auto` 时按优先级降级：先尝试 `library`（零成本），无匹配则使用 `suno`。

### 配乐拼接

所有 segment 配乐按时间顺序 concat 为一条完整音轨：

```bash
ffmpeg -f concat -safe 0 -i stage8/audio/music/concat_list.txt \
  -c copy stage8/audio/music/full_music_track.mp3
```

---

## 字幕生成：二选一策略

| 方案 | 条件 | 说明 |
|------|------|------|
| 方案 A（推荐） | `script_path` 有效 | 从剧本直接生成 SRT |
| 方案 B | `enable_voiceover=true` 且无剧本 | 从配音语音转录 SRT |

### 方案 A：剧本直生成 SRT

```bash
python3 generate_srt.py \
  --script stage2/script.md \
  --storyboard stage3/storyboard.json \
  --edl stage7/edl_v2.json \
  --output stage8/final_drama.srt
```

逻辑：遍历 EDL 每个镜头 → 提取对白文本（storyboard.json `dialogue` 字段） → 生成 SRT 条目（基于 EDL 实际 `start_time`/`end_time`）。对白为空的镜头跳过。

### 方案 B：whisper 转录

```bash
openai-whisper-api \
  --input stage8/audio/voiceover/combined_voiceover.wav \
  --output stage8/final_drama.srt \
  --format srt --language zh
```

---

## 配音流程（sag TTS 逐角色）

1. 解析剧本对白，按镜头和角色分组。
2. 为每个有对白的角色分配 ElevenLabs `voice_id`（按性别/年龄/性格匹配）。
3. 逐角色逐镜头生成配音：

```bash
sag --voice-id "{voice_id}" \
    --text "[情感标签] 对白文本" \
    --output stage8/audio/voiceover/shot_{N}_{角色}.wav
```

4. 使用 ffmpeg `adelay` 将每段配音对齐到视频时间点。

---

## ffmpeg 音视频合成

将视频与配音、配乐混合：

```bash
ffmpeg -i stage7/fine_cut.mp4 \
  -i stage8/audio/voiceover/combined_voiceover.wav \
  -i stage8/audio/music/full_music_track.mp3 \
  -filter_complex "
    [1:a]volume=1.0[voice];
    [2:a]volume=0.25[music];
    [voice][music]amix=inputs=2:duration=first[aout]
  " \
  -map 0:v -map "[aout]" \
  -c:v copy -c:a aac \
  stage8/working/merged.mp4
```

**混音策略**：配音音量 100%（主体），配乐音量 20%-30%（背景）。有对白段配乐进一步降低。

---

## 字幕烧录（libass）

使用 ffmpeg `libass` 滤镜烧录字幕，样式模板来自 `assets/subtitle-styles/`：

```bash
ffmpeg -i stage8/working/merged.mp4 \
  -vf "ass=stage8/working/final_drama.ass" \
  -c:v libx264 -crf 18 -preset medium \
  -c:a copy \
  stage8/final_drama.mp4
```

样式模板：

| 模板文件 | 适用场景 |
|---------|---------|
| `assets/subtitle-styles/default.ass` | 通用默认（白色字体，黑色描边） |
| `assets/subtitle-styles/cinematic.ass` | 电影感（浅灰字体，半透明黑底） |
| `assets/subtitle-styles/drama.ass` | 短剧风格（黄色字体，大字号） |

---

## 脚本引用

| 脚本 | 用途 |
|------|------|
| `scripts/mix_audio.sh` | 音视频合成（adelay + amix） |
| `scripts/generate_srt.py` | 从剧本直接生成 SRT 字幕文件 |
| `scripts/burn_subtitles.sh` | 字幕烧录（libass） |

---

## 强制 present_files 展示 final_drama.mp4

S8 完成后，强制调用 `present_files` 展示 `final_drama.mp4`，然后声明链路完成：

```
[Stage 8 成片完成] 产物：stage8/final_drama.mp4（时长 {N}s）
→ present_files 展示 final_drama.mp4

配乐来源：{music_source}
字幕：stage8/final_drama.srt
TTS 引擎：{tts_engine}

短剧制作流水线已全部完成。最终成片已展示。
```

**S8 即链路终点**，finalize-agent 完成后本 skill 调用结束。

---

## 输入 / 输出

### 输入

```yaml
fine_cut_path: "stage7/fine_cut.mp4"
music_plan_path: "stage3/music_plan.json"
script_path: "stage2/script.md"
storyboard_path: "stage3/storyboard.json"
subtitle_style: "default"
enable_voiceover: true
```

### 输出

```yaml
final_video_path: "stage8/final_drama.mp4"
subtitle_path: "stage8/final_drama.srt"
music_tracks:
  - segment: "seg_01"
    source: "suno"
    path: "stage8/audio/music/segment_01.mp3"
```

---

## 纪律约束

1. 必须 `present_files` 展示 `final_drama.mp4`，这是本轮请求的唯一最终交付。
2. 配乐 mood/tempo/instruments 必须与 `music_plan.json` 一致，时间段与镜头对齐。
3. 字幕时间戳必须基于 EDL 实际 `start_time`/`end_time`，文本来自 `script.md` 对白。
4. S8 即链路终点，不回溯任何上游 Stage。
5. 不修改 `fine_cut.mp4` 的视频内容。
6. 配音音量 > 配乐音量，有对白段配乐进一步降低。
7. 中间文件写入 `stage8/working/`，最终产物写入 `stage8/` 根目录。

> ffmpeg 命令参考详见 [`../../references/ffmpeg-cookbook.md`](../../references/ffmpeg-cookbook.md)。
> 配乐平台参考详见 [`../../references/music-platforms.md`](../../references/music-platforms.md)。
> 字幕样式模板位于 `../../assets/subtitle-styles/`。
