# 在线音乐平台使用指南

短剧制作中音乐获取、处理与对齐的完整方案。

---

## 1. Suno AI 平台使用指南

### 基本信息

- **访问地址**：https://suno.com
- **账号要求**：需要注册账号（支持 Google/微软/Discord 账号登录）
- **付费模式**：免费额度有限，大量生成需订阅付费计划
- **版权说明**：Suno 付费用户生成的音乐可用于商业用途，免费用户仅限个人使用。使用前确认当前账号的版权授权状态。

### 使用 agent-browser 访问流程

1. **启动 agent-browser**，访问 https://suno.com。
2. 登录账号（如已保存 session 则跳过）。
3. 进入 Create 页面。
4. 在 prompt 输入框中填入音乐描述。
5. 选择模式（Simple / Custom）。
6. 点击生成，等待处理完成（通常 30-60 秒）。
7. 在生成结果页面，点击下载按钮获取音频文件。

### prompt 编写建议

将 `music_plan.json` 中的 `mood`、`tempo`、`instruments` 转化为 Suno prompt：

#### 转化规则

| music_plan 字段 | Suno prompt 用法 |
|-----------------|------------------|
| `mood` | 直接作为情绪关键词，如 "melancholic"、"uplifting"、"tense" |
| `tempo` | 转化为 BPM 或速度词，如 "slow tempo 70bpm"、"fast tempo 140bpm" |
| `instruments` | 列出乐器名称，如 "piano and strings"、"acoustic guitar" |
| `genre` | 作为风格前缀，如 "cinematic ambient"、"orchestral" |
| `duration` | Suno 免费版生成约 30s-2min，需多段拼接 |

#### prompt 模板

```
{genre}, {mood}, {tempo}, featuring {instruments}, no vocals, background music for short drama scene
```

#### 示例

music_plan.json 片段：
```json
{
  "mood": "melancholic",
  "tempo": "slow",
  "instruments": ["piano", "cello"],
  "genre": "cinematic"
}
```

转化的 Suno prompt：
```
cinematic, melancholic, slow tempo, featuring piano and cello, no vocals, background music for short drama scene
```

### 下载生成的音乐

1. 在 Suno 结果页面，找到下载图标。
2. 下载音频文件（通常为 mp3 或 wav 格式）。
3. 将文件保存到 `assets/music/` 目录。
4. 使用 ffmpeg 进行后续处理（截取、归一化、对齐）。

### 注意事项

- **版权**：商业使用必须使用付费账号生成。在最终输出中标注音乐来源为 Suno AI。
- **账号额度**：免费账号每日生成次数有限，大型项目需提前规划额度。
- **一致性**：同一场景的多个分段，在 Suno 中使用相同的 prompt + 不同的 seed，保持风格一致。
- **纯音乐**：prompt 中加入 "no vocals" 或 "instrumental only"，避免生成人声。
- **生成质量**：一次生成多个候选，选择最佳结果使用。

---

## 2. 免版权音频库方案

### 适用场景

- 纯背景音乐需求，无需定制旋律。
- 快速获取，不依赖在线平台。
- 预算有限的场景。

### 使用已有免版权 BGM 文件

1. 将免版权 BGM 文件放置在 `assets/music/royalty_free/` 目录。
2. 按 `music_plan.json` 的 segments 配置，选择合适的 BGM 文件。
3. 使用 ffmpeg 截取所需长度。

### ffmpeg 截取和处理

```bash
# 截取 BGM 的前 30 秒
ffmpeg -i assets/music/royalty_free/bgm_01.mp3 -t 30 -c copy assets/music/segments/bgm_seg1.mp3

# 截取 30-60 秒部分
ffmpeg -i assets/music/royalty_free/bgm_01.mp3 -ss 30 -t 30 -c copy assets/music/segments/bgm_seg2.mp3

# 音量归一化（统一到 -16 dB）
ffmpeg -i bgm_seg1.mp3 -af "loudnorm=I=-16:TP=-1.5:LRA=11" -c:a aac bgm_seg1_normalized.mp3
```

### 免版权音频库推荐来源

- YouTube Audio Library
- Free Music Archive (FMA)
- Pixabay Music
- 项目内置的免版权 BGM 文件（如有）

### 注意事项

- 确认每首 BGM 的授权协议，商业使用需选择允许商用的授权。
- 保留原始授权信息，在最终输出中标注音乐来源。
- 不同来源的 BGM 音量可能差异较大，统一使用 loudnorm 归一化。

---

## 3. 用户上传音乐处理

### 接受格式

- **mp3**：最常见，兼容性好。
- **wav**：无损，适合高质量需求。
- **aac**：压缩格式，体积小。

### ffmpeg 转码和归一化

```bash
# 转码为统一的 wav 格式
ffmpeg -i user_music.mp3 -c:a pcm_s16le -ar 44100 -ac 2 user_music.wav

# 音量归一化
ffmpeg -i user_music.wav -af "loudnorm=I=-16:TP=-1.5:LRA=11" -c:a aac user_music_normalized.m4a

# 转码为 mp3（如需压缩体积）
ffmpeg -i user_music.wav -c:a libmp3lame -b:a 192k user_music.mp3
```

### 按分段对齐

根据 `music_plan.json` 的 segments 配置截取分段：

```bash
# segment 1: 0-30秒
ffmpeg -i user_music_normalized.m4a -t 30 -c copy music_seg1.m4a

# segment 2: 30-60秒
ffmpeg -i user_music_normalized.m4a -ss 30 -t 30 -c copy music_seg2.m4a

# segment 3: 60-90秒
ffmpeg -i user_music_normalized.m4a -ss 60 -t 30 -c copy music_seg3.m4a
```

### 处理流程

1. 接收用户上传的音乐文件。
2. 使用 ffprobe 检查格式和时长。
3. 转码为统一格式（推荐 wav 或 192k mp3）。
4. 音量归一化到 -16 dB。
5. 按 `music_plan.json` segments 截取分段。
6. 保存到 `assets/music/segments/` 目录。

---

## 4. 音乐与视频对齐策略

### 按 music_plan.json 的 segments 分段

`music_plan.json` 定义了每个音乐分段的起始时间、时长和情绪：

```json
{
  "segments": [
    {
      "id": "seg_01",
      "start_time": 0,
      "duration": 15,
      "mood": "calm",
      "music_file": "assets/music/segments/bgm_seg1.mp3"
    },
    {
      "id": "seg_02",
      "start_time": 15,
      "duration": 20,
      "mood": "tense",
      "music_file": "assets/music/segments/bgm_seg2.mp3"
    },
    {
      "id": "seg_03",
      "start_time": 35,
      "duration": 10,
      "mood": "uplifting",
      "music_file": "assets/music/segments/bgm_seg3.mp3"
    }
  ]
}
```

### adelay 设置每段起始时间

将每段配乐按 `start_time` 延迟后混合：

```bash
# seg_01 从 0 秒开始（无需延迟）
# seg_02 从 15 秒开始（延迟 15000ms）
# seg_03 从 35 秒开始（延迟 35000ms）

ffmpeg -i bgm_seg1.mp3 -i bgm_seg2.mp3 -i bgm_seg3.mp3 \
  -filter_complex \
  "[0:a]adelay=0|0[a1]; \
   [1:a]adelay=15000|15000[a2]; \
   [2:a]adelay=35000|35000[a3]; \
   [a1][a2][a3]amix=inputs=3:duration=longest:dropout_transition=0[outa]" \
  -map "[outa]" music_track.wav
```

### amix 混合多段

使用 `amix` 将所有分段混合为一路音频：

```bash
ffmpeg -i bgm_seg1.mp3 -i bgm_seg2.mp3 -i bgm_seg3.mp3 \
  -filter_complex \
  "[0:a]volume=0.3,adelay=0|0[a1]; \
   [1:a]volume=0.3,adelay=15000|15000[a2]; \
   [2:a]volume=0.3,adelay=35000|35000[a3]; \
   [a1][a2][a3]amix=inputs=3:duration=longest:dropout_transition=0[outa]" \
  -map "[outa]" music_track.wav
```

### 配音与配乐的音量比例

**标准比例：配音 1.0，配乐 0.3**

配音（语音对白）是短剧的核心信息载体，配乐仅作为氛围烘托。混音时：

```bash
ffmpeg -i voiceover.wav -i music_track.wav \
  -filter_complex \
  "[0:a]volume=1.0[a1]; \
   [1:a]volume=0.3[a2]; \
   [a1][a2]amix=inputs=2:duration=first:dropout_transition=0[outa]" \
  -map "[outa]" final_audio.wav
```

### 完整混音流程

将配音、配乐分段、音效（如有）混合为最终音轨：

```bash
ffmpeg -i voiceover.wav \
       -i bgm_seg1.mp3 -i bgm_seg2.mp3 -i bgm_seg3.mp3 \
       -i sfx.mp3 \
  -filter_complex \
  "[0:a]volume=1.0[a_voice]; \
   [1:a]volume=0.3,adelay=0|0[a_m1]; \
   [2:a]volume=0.3,adelay=15000|15000[a_m2]; \
   [3:a]volume=0.3,adelay=35000|35000[a_m3]; \
   [4:a]volume=0.5,adelay=10000|10000[a_sfx]; \
   [a_voice][a_m1][a_m2][a_m3][a_sfx]amix=inputs=5:duration=longest:dropout_transition=0[outa]" \
  -map "[outa]" final_audio.wav
```

### 音轨与视频合并

```bash
ffmpeg -i video.mp4 -i final_audio.wav \
  -c:v copy -c:a aac -map 0:v -map 1:a -shortest final_video.mp4
```

### 对齐验证

1. 使用 ffprobe 检查最终音频时长是否与视频时长匹配。
2. 检查每个音乐 segment 的 `start_time` 是否与对应镜头的时间点对齐。
3. 播放检查配音清晰度，确保配乐不盖过配音。
4. 如配乐过大，降低 `volume` 值（如从 0.3 降至 0.2）。
5. 如配音过小，对配音单独做 loudnorm 归一化后再混合。
