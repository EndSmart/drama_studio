---
name: finalize-agent
description: "Stage 8 子 Agent：配乐生成/获取 + 字幕生成 + 配音（可选）+ 音视频合成 + 字幕烧录，输出最终成片 final_drama.mp4。读取 S7 产出的 fine_cut.mp4、S3 产出的 music_plan.json + storyboard.json、S2 产出的 script.md，通过 sag (ElevenLabs TTS) / openai-whisper-api / ffmpeg / generate_srt.py / agent-browser (Suno) 完成配乐对齐、字幕烧录和最终合成。完成后强制 present_files 展示 final_drama.mp4，S8 即链路终点。"
---

# Finalize Agent — Stage 8 配乐 + 字幕 + 成片

> **职责**：将 S7 精剪成片配以与剧情对齐的音乐、字幕和（可选）配音，合成并烧录为最终交付的 `final_drama.mp4`。
>
> **核心工具**：
> - `sag` (ElevenLabs TTS) — 配音生成，支持情感标签 `[whispers]` / `[excited]` / `[laughs]` 等
> - `openai-whisper-api` — 语音转字幕（从配音转录 SRT）
> - Bash 调用 `ffmpeg` — 音视频合成、混音、字幕烧录
> - `agent-browser` — 访问 Suno 平台生成配乐（可选，source="suno" 时使用）
> - Bash 调用 `generate_srt.py` — 从剧本直接生成 SRT 字幕文件
>
> **边界**：S8 是链路终点。不回溯上游 Stage，不修改 fine_cut.mp4 的视频内容。只在视频上叠加音频轨道和字幕。

---

## 触发条件

- `stage_7.status == completed`（用户已确认满意，精剪迭代结束）。
- orchestrator 声明角色切换后加载本文件执行。
- `refinement` 入口类型下，S8 为首个执行 Stage（此时 `stage_7.output_path` 指向已有精剪/粗剪文件）。

---

## 输入 / 输出契约

### 输入（YAML）

```yaml
fine_cut_path: "stage7/fine_cut.mp4"          # 必填，S7 精剪成片路径
music_plan_path: "stage3/music_plan.json"     # 必填，S3 配乐计划
script_path: "stage2/script.md"               # 必填，S2 剧本（含对白，用于字幕/配音）
storyboard_path: "stage3/storyboard.json"     # 必填，S3 分镜脚本（含时间戳，用于字幕对齐）
subtitle_style: "default"                     # 可选，字幕样式模板名称（对应 assets/subtitle-styles/ 下的 .ass 文件）
enable_voiceover: true                        # 可选，是否生成 TTS 配音，默认 true
```

### 输出（YAML）

```yaml
final_video_path: "stage8/final_drama.mp4"    # 最终成片路径
subtitle_path: "stage8/final_drama.srt"       # 字幕文件路径
music_tracks:                                  # 配乐轨道列表
  - segment: "seg_01"
    source: "suno"                             # 配乐来源
    path: "stage8/audio/music/segment_01.mp3"
```

---

## 执行流程

### Step 1：读取并验证 Pipeline State

1. 读取 `pipeline-state.yaml`。
2. 验证 `stage_7.status == completed`，否则报错终止：`[finalize-agent] S7 未完成，无法执行 S8`。
3. 验证 `fine_cut_path` 文件存在且可读。
4. 验证 `music_plan_path` / `script_path` / `storyboard_path` 文件存在且可读。
5. 将 `stage_8.status` 设为 `in_progress`，写入 `started_at`。

### Step 2：创建工作目录

```bash
mkdir -p stage8/audio/voiceover
mkdir -p stage8/audio/music
mkdir -p stage8/working
```

### Step 3：配音生成（可选，enable_voiceover=true 时执行）

#### 3.1 解析剧本对白

1. 读取 `script.md`，按场景和对白行解析。
2. 读取 `storyboard.json`，获取每个镜头的 `dialogue` 字段和 `duration_seconds`。
3. 将对白按镜头分组，计算每句对白在视频中的时间段（基于 EDL 的 `start_time` / `end_time`）。

#### 3.2 角色音色分配

1. 从 `pipeline-state.yaml` 的 `stage_1.characters` 获取角色列表。
2. 为每个有对白的角色分配 ElevenLabs `voice_id`（按角色性别/年龄/性格匹配）。
3. 支持情感标签：在对白文本中嵌入 `[whispers]` / `[excited]` / `[laughs]` / `[sad]` / `[angry]` 等标签，sag 会据此调整语气。

#### 3.3 逐角色逐镜头生成配音

```bash
# 示例：为 shot_02 的林晓生成配音
sag --voice-id "{voice_id_林晓}" \
    --text "[sad] 又是这样的雨夜……" \
    --output stage8/audio/voiceover/shot_02_林晓.wav
```

每个有对白的镜头生成一个或多个配音音频文件，命名格式：`shot_{N}_{角色}.wav`。

#### 3.4 配音对齐

使用 ffmpeg `adelay` 将每段配音对齐到视频中的正确时间点：

```bash
# shot_02 的配音在视频中从 5.0s 开始
ffmpeg -i stage8/audio/voiceover/shot_02_林晓.wav \
  -filter:a "adelay=5000|5000" \
  stage8/audio/voiceover/shot_02_林晓_aligned.wav
```

若 `enable_voiceover=false`，跳过本步，后续直接使用字幕。

### Step 4：字幕生成

#### 方案选择

| 方案 | 条件 | 说明 |
|------|------|------|
| 方案 A（推荐） | `script_path` 有效 | 从剧本直接生成 SRT |
| 方案 B | `enable_voiceover=true` 且无剧本 | 从配音语音转录 SRT |

#### 4.1 方案 A：从剧本生成 SRT（推荐）

1. 读取 `script.md`，提取每个镜头的对白文本。
2. 读取 `storyboard.json`，获取每个镜头的时间段（`start_time` / `end_time`，从 EDL 获取）。
3. 执行 `generate_srt.py`：

```bash
python3 generate_srt.py \
  --script stage2/script.md \
  --storyboard stage3/storyboard.json \
  --edl stage7/edl_v2.json \
  --output stage8/final_drama.srt
```

`generate_srt.py` 逻辑：
- 遍历 EDL 中每个镜头。
- 提取该镜头的对白文本（从 storyboard.json 的 `dialogue` 字段）。
- 生成 SRT 条目：序号 + 起止时间（`HH:MM:SS,mmm` 格式） + 对白文本。
- 对白为空的镜头跳过（不生成字幕条目）。
- 长对白（超过镜头时长合理阅读速度）自动拆分为多条字幕。

#### 4.2 方案 B：从配音转录 SRT

1. 将所有配音片段按时间顺序合并为一个完整音轨。
2. 使用 `openai-whisper-api` 转录：

```bash
openai-whisper-api \
  --input stage8/audio/voiceover/combined_voiceover.wav \
  --output stage8/final_drama.srt \
  --format srt \
  --language zh
```

3. Whisper 生成的时间戳基于音频文件，需对齐到视频时间轴（加上每段配音的 `adelay` 偏移量）。

### Step 5：配乐获取/生成

根据 `music_plan.json` 中每个 segment 的 `source` 字段，选择配乐获取方式。

#### 5.1 source="suno" — Suno 浏览器生成

1. 使用 `agent-browser` 访问 Suno 平台。
2. 按 segment 的 `mood` / `tempo` / `instruments` / `description` 构造 Suno prompt：

```
Prompt 构造规则：
  mood → 情感关键词（如 "melancholic", "tense", "romantic"）
  tempo → BPM 指定（如 "60 BPM"）
  instruments → 乐器列表（如 "piano, strings"）
  description → 直接作为风格补充描述

示例 prompt：
  "Melancholic piano piece with gentle strings, 60 BPM, sad and emotional, 
   suitable for a rainy night scene, cinematic background music"
```

3. 在 Suno 平台提交 prompt 生成音乐。
4. 下载生成的音乐文件到 `stage8/audio/music/segment_{N}.mp3`。
5. 使用 ffmpeg 截取/循环到 segment 需要的 `duration_seconds`：

```bash
# 截取到指定时长
ffmpeg -i stage8/audio/music/segment_01.mp3 -t 20 -c copy stage8/audio/music/segment_01_trimmed.mp3

# 若音乐短于需要时长，循环播放
ffmpeg -stream_loop -1 -i stage8/audio/music/segment_01.mp3 -t 20 -c copy stage8/audio/music/segment_01_loop.mp3
```

#### 5.2 source="library" — 已有音频库

1. 从已有音频素材库中按 `mood` / `tempo` / `instruments` 匹配最接近的音频文件。
2. 使用 ffmpeg 截取到 segment 需要的时长：

```bash
ffmpeg -i library/{matched_file}.mp3 -t 20 -c copy stage8/audio/music/segment_{N}.mp3
```

3. 如需淡入淡出处理：

```bash
ffmpeg -i library/{matched_file}.mp3 -t 20 \
  -af "afade=t=in:st=0:d=2,afade=t=out:st=18:d=2" \
  stage8/audio/music/segment_{N}.mp3
```

#### 5.3 source="user_provided" — 用户提供

1. 从用户上传的音乐文件中按 segment 分段对齐。
2. 使用 ffmpeg 截取/循环到每个 segment 的 `duration_seconds`。
3. 输出到 `stage8/audio/music/segment_{N}.mp3`。

#### 5.4 配乐拼接

将所有 segment 的配乐按时间顺序拼接为一条完整配乐音轨：

```bash
# 生成 concat 列表
file 'stage8/audio/music/segment_01.mp3'
file 'stage8/audio/music/segment_02.mp3'
file 'stage8/audio/music/segment_03.mp3'

# 拼接
ffmpeg -f concat -safe 0 -i stage8/audio/music/concat_list.txt -c copy stage8/audio/music/full_music_track.mp3
```

### Step 6：音视频合成

将视频（fine_cut.mp4）与配音音轨、配乐音轨混合。

#### 6.1 混音策略

- **配音音量大**：为主体，音量 100%。
- **配乐音量小**：为背景，音量降至 20%-30%（`volume=0.25`）。
- 有对白的镜头段配乐进一步降低（ducking），无对白段配乐恢复正常。

#### 6.2 ffmpeg 合成命令

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

> 若 `enable_voiceover=false`，只有配乐音轨，直接将配乐混入视频：

```bash
ffmpeg -i stage7/fine_cut.mp4 \
  -i stage8/audio/music/full_music_track.mp3 \
  -map 0:v -map 1:a \
  -c:v copy -c:a aac \
  -shortest \
  stage8/working/merged.mp4
```

### Step 7：字幕烧录

使用 ffmpeg `libass` 滤镜将 SRT 字幕烧录到视频中。

#### 7.1 选择字幕样式

1. 检查 `subtitle_style` 参数。
2. 从 `assets/subtitle-styles/` 目录查找对应的 `.ass` 样式模板文件。
3. 若未指定或文件不存在，使用默认样式 `assets/subtitle-styles/default.ass`。

#### 7.2 SRT → ASS 转换（若需要）

若只有 SRT 文件，使用 ffmpeg 转换为 ASS 并应用样式：

```bash
ffmpeg -i stage8/final_drama.srt \
  -c:s ass \
  -style "FontName=Noto Sans CJK SC,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=30" \
  stage8/working/final_drama.ass
```

#### 7.3 烧录字幕

```bash
ffmpeg -i stage8/working/merged.mp4 \
  -vf "ass=stage8/working/final_drama.ass" \
  -c:v libx264 -crf 18 -preset medium \
  -c:a copy \
  stage8/final_drama.mp4
```

> 字幕烧录需要重编码视频（`-c:v libx264`），使用 `crf=18` 保证画质。音频直接 copy（`-c:a copy`）。

### Step 8：验证最终产物

1. 验证 `stage8/final_drama.mp4` 文件存在且可播放。
2. 验证视频时长与 `fine_cut.mp4` 一致（允许 ±0.5s 偏差）。
3. 验证字幕文件 `stage8/final_drama.srt` 存在且非空。
4. 验证配乐文件列表 `music_tracks[]` 中每个文件存在。

### Step 9：更新 Pipeline State

更新 `pipeline-state.yaml`：

```yaml
stage_8:
  status: completed
  started_at: <已记录>
  completed_at: <当前 ISO-8601>
  output_path: "stage8/final_drama.mp4"
  subtitle_path: "stage8/final_drama.srt"
  music_source: "<suno | library | user_provided | mixed>"
  tts_engine: "<sag | whisper | none>"
  present_files_opened: false   # 下一步强制展示后改为 true
```

推进 `current_stage: completed`，更新 `updated_at`。

### Step 10：强制 present_files 展示成片

**先写 YAML，再展示**。调用 `present_files` 展示 `final_drama.mp4`，随后将 `present_files_opened` 设为 `true`。

声明链路完成：

```
[Stage 8 成片完成] 产物：stage8/final_drama.mp4（时长 {N}s）
→ present_files 展示 final_drama.mp4

配乐来源：{music_source}
字幕：stage8/final_drama.srt
TTS 引擎：{tts_engine}

短剧制作流水线已全部完成。最终成片已展示。
```

**S8 即链路终点**。finalize-agent 完成后，本 skill 调用结束。

---

## music_plan.json 消费说明

finalize-agent 读取 `music_plan.json` 的 `segments[]` 数组，逐段获取/生成配乐：

| music_plan 字段 | 消费方式 |
|-----------------|---------|
| `segments[].segment_id` | 命名输出文件 `segment_{N}.mp3` |
| `segments[].shot_range` | 确定该段配乐覆盖的视频时间段 |
| `segments[].mood` | Suno prompt 的情感关键词 |
| `segments[].tempo` | Suno prompt 的 BPM 指定 |
| `segments[].instruments` | Suno prompt 的乐器列表 |
| `segments[].duration_seconds` | 截取/循环配乐到此时长 |
| `segments[].source` | 选择获取方式：`suno` / `library` / `user_provided` |
| `segments[].description` | Suno prompt 的风格补充描述 |

> `source` 字段为 `auto` 时，按优先级降级：先尝试 `library`（零成本），无匹配则使用 `suno`（生成定制音乐）。

---

## 字幕样式模板

`assets/subtitle-styles/` 目录下的 `.ass` 样式模板：

| 模板文件 | 适用场景 | 样式说明 |
|---------|---------|---------|
| `default.ass` | 通用默认 | 白色字体，黑色描边，底部居中 |
| `cinematic.ass` | 电影感 | 浅灰字体，无描边，底部居中，半透明黑底 |
| `drama.ass` | 短剧风格 | 黄色字体，黑色描边，底部偏上，大字号 |

> 用户可通过 `subtitle_style` 参数指定样式名称（不含 `.ass` 后缀）。未指定时使用 `default`。

---

## 纪律约束

1. **必须 present_files 展示成片**：S8 完成后必须调用 `present_files` 展示 `final_drama.mp4`，不得跳过。`present_files_opened` 必须设为 `true`。这是本轮请求的唯一最终交付。
2. **音乐必须与剧情对齐**：配乐的 mood / tempo / instruments 必须与 `music_plan.json` 一致。配乐时间段必须与对应镜头段对齐，不得错位。
3. **字幕必须与对白对齐**：字幕的时间戳必须基于 EDL 中镜头的实际 `start_time` / `end_time`，不得使用 storyboard 中的预估时间。字幕文本必须来自 `script.md` 的对白，不得自行编造。
4. **S8 即链路终点**：finalize-agent 完成后不回溯任何上游 Stage。如需修改，需发起新请求。
5. **不修改 fine_cut.mp4 的视频内容**：S8 只在视频上叠加音频和字幕，不剪辑、不调色、不改变视频画面顺序。
6. **配音音量 > 配乐音量**：混音时配音为主体（100%），配乐为背景（20%-30%）。有对白段配乐进一步降低，保证对白清晰可闻。
7. **所有中间文件写入 stage8/working/**：ffmpeg 中间产物（merged.mp4、.ass 等）写入 `stage8/working/`，不污染输出目录。最终产物写入 `stage8/` 根目录。

---

## Pipeline State 协议

### 启动时读取验证

1. 读取 `pipeline-state.yaml`。
2. 验证 `stage_7.status == completed`。
3. 验证 `stage_7.output_path`（即 `fine_cut_path`）文件存在。
4. 验证 `stage_3.music_plan_path` 文件存在。
5. 验证 `stage_3.storyboard_path` 文件存在。
6. 验证 `stage_2.output_path`（即 `script_path`）文件存在。
7. 验证通过后，将 `stage_8.status` 设为 `in_progress`，写入 `started_at`。

验证失败时报错终止：

```
[finalize-agent] Pipeline State 验证失败：{具体原因}。请检查 S7 是否完成。
```

### 完成时更新

1. 写入 `stage8/final_drama.mp4` 和 `stage8/final_drama.srt`。
2. 更新 `pipeline-state.yaml` 的 `stage_8` 块：

```yaml
stage_8:
  status: completed
  started_at: <已记录的启动时间>
  completed_at: <当前 ISO-8601 时间戳>
  output_path: "stage8/final_drama.mp4"
  subtitle_path: "stage8/final_drama.srt"
  music_source: "<suno | library | user_provided | mixed>"
  tts_engine: "<sag | whisper | none>"
  present_files_opened: false   # 展示后改为 true
```

3. 推进 `current_stage: completed`。
4. 更新 `updated_at`。
5. 写入 `consistency_check`：

```yaml
consistency_check:
  output_files_exist: pass | fail     # 检查 stage_chain 中每个 Stage 的 output_path 文件是否存在
  stage_chain_complete: pass | fail   # 检查 stage_chain 中所有 stage 的 status 是否为 completed
  character_consistency_verified: pass | fail  # 检查 S5 manifest 中每个 clip 是否使用了 character_card 的 reference_image
  last_checked_at: "<ISO-8601>"
  errors: []
```

6. 写入 `credit_tracking.actual_total`（汇总所有 Stage 的实际消耗）。
7. **先写 YAML，再 present_files 展示**，然后将 `present_files_opened` 改为 `true`。

### 原子写入

使用 `.tmp` + `rename` 方式写入 `pipeline-state.yaml`，防止中途崩溃产生半文件。
