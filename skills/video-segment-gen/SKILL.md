---
name: video-segment-gen
description: "Stage 5 视频片段生成能力：逐镜头生成视频片段。核心为角色一致性三层锁定机制（角色卡 reference_image → ImageGen 图生图首帧 → VideoGen 图生视频）。由 video-gen-agent 加载执行。"
---

# Video Segment Gen — Stage 5 视频片段生成

> **职责**：根据 S3 分镜脚本和 S4 角色卡，逐镜头生成视频片段（`shot_{N}.mp4`）。
>
> **核心**：角色一致性三层锁定机制 —— 确保视频中角色外貌与 S4 角色卡高度一致。
>
> **边界**：只做逐镜头视频生成。不做粗剪（S6）、不碰配乐字幕（S8）、不展示中间态。
>
> **执行者**：`video-gen-agent`（详见 `../../agents/video-gen-agent.md`），本文件为能力声明，不展开执行细节。

---

## 角色一致性三层锁定机制

```
character_card.json                  storyboard.json
      │                                     │
      ├─ reference_image (front.png)        ├─ image_prompt (场景/光线/动作)
      ├─ seed_prompt (固定外貌前缀)          ├─ video_prompt (仅运动描述)
      │                                     ├─ duration_seconds
      │                                     ├─ characters_in_shot
      ▼                                     ▼
┌───────────────────────────────────────────────────────────────┐
│ 第一层：读取角色基准                                            │
│ 从 character_card.json 读取 reference_image 和 seed_prompt      │
│ 确定本镜头主角（characters_in_shot[0]）                         │
└────────────────────────┬──────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────┐
│ 第二层：ImageGen 图生图 → 镜头首帧                              │
│ input image = reference_image (角色卡 front.png)               │
│ prompt = seed_prompt + image_prompt (场景部分)                  │
│ input_fidelity = 0.5                                          │
│ → 输出 keyframe_shot_{N}.png                                  │
└────────────────────────┬──────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────┐
│ 第三层：VideoGen 图生视频 → 镜头片段                             │
│ image = keyframe_shot_{N}.png (第二层输出的首帧)                │
│ prompt = video_prompt (仅运动描述，不含角色外貌)                 │
│ seconds = duration_seconds, resolution, aspect_ratio           │
│ → 输出 shot_{N}.mp4                                           │
└───────────────────────────────────────────────────────────────┘
```

> 完整机制与约束详见 [`../../references/character-consistency-guide.md`](../../references/character-consistency-guide.md)。

---

## ImageGen 图生图调用规范

```
ImageGen:
  image: [{path: "{character_card.reference_image}"}]
  prompt: "{seed_prompt}, {storyboard.image_prompt 中场景/光线/构图部分}"
  input_fidelity: 0.5
  size: "1024x1536"
  quality: "high"
  output_dir: "{clips_dir}/"
```

**关键约束**：
- `image` 输入必须使用角色卡 `reference_image`（即 front.png），禁止纯文生图。
- `prompt` = `seed_prompt`（固定外貌前缀）+ `image_prompt` 场景部分，确保角色外貌与 S4 一致。
- `input_fidelity` 设为 0.5（适中：保留角色特征，允许场景变化）。

---

## VideoGen 图生视频调用规范

```
VideoGen:
  image: "{clips_dir}/keyframe_shot_{N}.png"
  prompt: "{storyboard.video_prompt}"
  seconds: {storyboard.duration_seconds}
  resolution: "{resolution}"          # "720P" | "1080P"
  aspect_ratio: "{aspect_ratio}"      # 默认 "9:16"
  negative_prompt: "{storyboard.negative_prompt}"
  enable_audio: false
  output_dir: "{clips_dir}/"
```

**关键约束**：
- `prompt` 严格使用 `video_prompt`（仅运动描述），禁止加入角色外貌描述（外貌已由首帧锁定）。
- `enable_audio` 设为 `false`，音频在 S8 统一处理。

---

## 多角色镜头处理

当 `characters_in_shot` 包含多个角色时：

1. 取 `characters_in_shot[0]` 的 `reference_image` 作为图生图输入。
2. 在 `prompt` 中拼接其他角色的 `seed_prompt`，用 `, alongside` 连接。

```
ImageGen:
  image: [{path: "stage4/characters/{主角}/front.png"}]
  prompt: "{主角.seed_prompt}, alongside {配角.seed_prompt}, {image_prompt 场景部分}"
```

---

## 失败重试策略

1. **首次失败**：重试 1 次，使用相同参数。
2. **重试仍失败**：标记该镜头 `status: "failed"`，记录错误原因到 `manifest.json` 的 `error_message`。
3. **不阻塞流水线**：跳过失败镜头，继续处理下一个镜头。
4. **汇总报告**：所有镜头处理完毕后，声明成功/失败数量。

```
[video-gen-agent] 镜头生成完成：{成功数}/{总数} 成功，{失败数} 失败。失败镜头：{shot_id 列表}。
```

---

## manifest.json 输出格式

```json
{
  "$schema": "manifest_v1",
  "request_id": "<uuid-v4>",
  "created_at": "<ISO-8601>",
  "total_shots": 12,
  "success_shots": 11,
  "failed_shots": 1,
  "total_credits_used": 907.5,
  "clips": [
    {
      "shot_id": "shot_01",
      "clip_path": "stage5/clips/shot_01.mp4",
      "keyframe_path": "stage5/clips/keyframe_shot_01.png",
      "duration": 5,
      "status": "completed",
      "credits_used": 82.5,
      "imagegen_credits": 7.5,
      "videogen_credits": 75
    },
    {
      "shot_id": "shot_03",
      "clip_path": null,
      "keyframe_path": null,
      "duration": 5,
      "status": "failed",
      "credits_used": 7.5,
      "imagegen_credits": 7.5,
      "videogen_credits": 0,
      "error_message": "VideoGen failed after 1 retry"
    }
  ]
}
```

---

## 输入 / 输出

### 输入

```yaml
storyboard_path: "stage3/storyboard.json"
character_cards:                              # 从 S4 透传
  - name: string
    card_path: string                         # character_card.json 路径
    reference_image: string                   # = front.png
characters_dir: "stage4/characters"
resolution: "1080P"
aspect_ratio: "9:16"
```

### 输出

```yaml
clips_dir: "stage5/clips"
manifest_path: "stage5/clips/manifest.json"
total_shots: int
success_shots: int
failed_shots: int
total_credits_used: float
```

---

## 纪律约束

1. 必须使用角色卡 `reference_image` 作为 ImageGen 图生图输入，禁止纯文生图。
2. VideoGen 必须使用图生视频模式（传入首帧），禁止纯文生视频。
3. VideoGen prompt 仅含运动描述，禁止含角色外貌。
4. 产物是中间态，不调用 `present_files`。
5. 失败不阻塞流水线。
6. 不修改上游数据（`storyboard.json` / `character_card.json`）。
7. 不生成音频（`enable_audio: false`）。
8. credits 如实记录在 `manifest.json` 中。
