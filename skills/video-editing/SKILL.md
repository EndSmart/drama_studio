---
name: video-editing
description: "Stage 6 + Stage 7 视频剪辑能力：粗剪（concat 拼接 + 转场处理）与精剪（5 种反馈类型迭代，可回溯 S5 重新生成镜头）。由 editing-agent 加载执行。"
---

# Video Editing — Stage 6 粗剪 + Stage 7 精剪

> **职责**：将 S5 产出的逐镜头视频片段拼接为完整短剧，并在人工反馈驱动下迭代精修。
>
> **核心工具**：Bash 调用 ffmpeg（concat demuxer / xfade filter / trim / setpts）。
>
> **边界**：只做剪辑与镜头级调整。不生成新视频内容（回溯 S5 由 video-gen-agent 执行），不碰配乐/字幕/配音（S8 负责）。
>
> **执行者**：`editing-agent`（详见 `../../agents/editing-agent.md`），本文件为能力声明，不展开执行细节。

---

## 粗剪流程（S6）

### 方案 A：全部 cut 转场 → ffmpeg concat demuxer

生成 concat 列表文件，使用 concat demuxer 直接拼接：

```bash
# concat_list.txt
file 'stage5/clips/shot_01.mp4'
file 'stage5/clips/shot_02.mp4'
...

# 执行
ffmpeg -f concat -safe 0 -i stage6/concat_list.txt -c copy stage6/rough_cut.mp4
```

> concat demuxer 要求所有片段编码格式、分辨率、帧率一致。S5 产出的片段已统一规格。

### 方案 B：含 fade/dissolve 转场 → ffmpeg xfade filter

```bash
ffmpeg -i shot_01.mp4 -i shot_02.mp4 -i shot_03.mp4 \
  -filter_complex "
    [0:v][1:v]xfade=transition=fade:duration=0.5:offset=4.5[v01];
    [v01][2:v]xfade=transition=dissolve:duration=0.8:offset=8.7[vout]
  " -map "[vout]" stage6/rough_cut.mp4
```

> `offset` = 前一段视频时长 - 转场时长。镜头数 > 20 时分批拼接。

### 转场映射

| transition_to_next | ffmpeg 实现 |
|---|---|
| `cut` | concat demuxer（无滤镜） |
| `fade` | xfade filter `transition=fade, duration=0.5` |
| `dissolve` | xfade filter `transition=dissolve, duration=0.8` |

---

## 精剪 5 种反馈处理（S7）

| type | 处理方式 | ffmpeg 命令 |
|------|---------|-------------|
| `trim` | 裁剪镜头时长 | `ffmpeg -i shot_N.mp4 -ss {start} -to {end} -c copy shot_N_trimmed.mp4` |
| `reorder` | 调整镜头顺序 | 重新计算 EDL → 重新 ffmpeg 拼接 |
| `transition` | 修改转场效果 | 更新 EDL 转场字段 → 重新 ffmpeg 拼接（可能切换方案 A/B） |
| `speed` | 调整播放速度 | `ffmpeg -i shot_N.mp4 -filter:v "setpts={factor}*PTS" -filter:a "atempo={speed}" shot_N_speed.mp4` |
| `replace` | 回溯 S5 重新生成镜头 | 委托 video-gen-agent 重新生成 → 新片段写入 `shot_{N}_v2.mp4` → 更新 manifest + EDL → 重新拼接 |

> replace 类型回溯 S5 时，只重新生成目标镜头，不触碰其他镜头。原版 `shot_{N}.mp4` 保留。

---

## 脚本引用

| 脚本 | 用途 |
|------|------|
| `scripts/rough_cut.sh` | 粗剪拼接（concat demuxer / xfade filter） |
| `scripts/fine_cut.sh` | 精剪迭代处理（trim / reorder / transition / speed） |
| `scripts/add_subtitles.sh` | 字幕烧录（S8 消费） |

---

## edl.json 格式

```json
{
  "$schema": "edl_v1",
  "request_id": "<uuid-v4>",
  "created_at": "<ISO-8601>",
  "source": "rough_cut",
  "total_duration": 60.0,
  "shot_count": 12,
  "shots": [
    {
      "shot_id": "shot_01",
      "start_time": 0.0,
      "end_time": 5.0,
      "clip_path": "stage5/clips/shot_01.mp4",
      "transition_in": "none",
      "transition_out": "cut"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | string | `rough_cut`（S6）或 `fine_cut`（S7） |
| `total_duration` | float | 最终视频总时长（秒） |
| `shots[].start_time` | float | 镜头在最终视频中的起始时间 |
| `shots[].end_time` | float | 镜头在最终视频中的结束时间 |
| `shots[].transition_in` | enum | `none` / `cut` / `fade` / `dissolve` |
| `shots[].transition_out` | enum | `cut` / `fade` / `dissolve` |

---

## S6 完成后 mandatory checkpoint

S6 粗剪完成后，强制 `present_files` 展示 `rough_cut.mp4`，然后**暂停执行**等待人工反馈：

```
[Stage 6 粗剪完成] 产物：stage6/rough_cut.mp4（时长 {N}s，{shot_count} 镜头）。
→ present_files 展示 rough_cut.mp4

下一步：进入 Stage 7 精剪 —— 请审看粗剪版本并提供反馈。

反馈示例：
- "第3镜太长了，缩短到3秒"（trim）
- "第5镜角色表情不对，重新生成"（replace → 回溯 S5）
- "先放第7镜再放第6镜"（reorder）
- "第4镜用淡入淡出替代硬切"（transition）
- "第8镜加速2倍"（speed）
- 或直接说"满意，继续"进入 S8
```

**不自动进入 S7**，等待人工反馈后才继续。

---

## 输入 / 输出

### S6 输入

```yaml
clips_dir: "stage5/clips/"
manifest_path: "stage5/clips/manifest.json"
storyboard_path: "stage3/storyboard.json"
transition_style: "auto"              # auto | cut_only | fade_all
```

### S6 输出

```yaml
rough_cut_path: "stage6/rough_cut.mp4"
edit_decision_list: "stage6/edl.json"
```

### S7 输入

```yaml
rough_cut_path: "stage6/rough_cut.mp4"
feedback:
  - type: "trim | replace | reorder | transition | speed"
    shot_id: "shot_N"
    instruction: "自然语言指令"
```

### S7 输出

```yaml
fine_cut_path: "stage7/fine_cut.mp4"
updated_edl: "stage7/edl_v2.json"
regeneration_log: []
```

---

## 纪律约束

1. S6 完成后必须 `present_files` 展示 `rough_cut.mp4`，不得跳过。
2. S7 迭代无上限，用户满意才进 S8。
3. replace 回溯 S5 时只重新生成目标镜头，原版保留。
4. 反馈无法明确解析时请求用户澄清，不猜测执行。
5. EDL 每次操作后必须同步更新（时间偏移重算）。
6. 不碰配乐/字幕/配音（S8 职责）。

> ffmpeg 命令参考详见 [`../../references/ffmpeg-cookbook.md`](../../references/ffmpeg-cookbook.md)。
