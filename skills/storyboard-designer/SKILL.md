---
name: storyboard-designer
description: "分镜脚本设计 + 配乐基调规划。将剧本拆分为逐镜头分镜脚本（storyboard.json）并生成配乐计划（music_plan.json），被 storyboard-agent 加载后指导 Stage 3 的分镜与配乐设计流程。包含镜头类型/运镜/转场规范、image_prompt 和 video_prompt 编写规范、配乐基调标签体系。"
---

# Storyboard Designer — 分镜脚本设计 + 配乐基调规划

> 被 `storyboard-agent` 加载，指导 Stage 3 分镜与配乐设计。详细执行逻辑见 `../../agents/storyboard-agent.md`。
> 分镜模板规范见 `../../references/storyboard-template.md`。

---

## 分镜拆分原则

### 场景 → 镜头拆分规则

| 规则 | 说明 |
|------|------|
| 一个动作单元 = 一个镜头 | 角色完成一个完整动作（如"走到窗前"）归为一个镜头 |
| 对白切换 = 镜头切换 | 说话人变化时切换镜头（正反打） |
| 情绪转折 = 镜头切换 | 同一场景内情绪明显转折时拆分为新镜头 |
| 时长控制 | 每镜头默认 5 秒，短至 3 秒（快切），长至 8 秒（情绪延展） |
| 总时长对齐 | 所有镜头 duration_seconds 之和接近 target_duration，偏差 ±10% |

### 镜头类型表 (shot_type)

| shot_type | 说明 | 适用场景 | 占比建议 |
|-----------|------|---------|---------|
| `extreme_closeup` | 大特写 | 眼神、手部细节、关键道具 | 10%-15% |
| `closeup` | 特写 | 面部表情、情绪表达 | 35%-40% |
| `medium` | 中景 | 半身对话、日常互动 | 25%-30% |
| `wide` | 全景/远景 | 场景交代、环境展示 | 15%-25% |

> 竖屏短剧以 `closeup` 和 `medium` 为主。

### 运镜方式表 (camera_movement)

| camera_movement | 说明 | 使用建议 |
|------------------|------|---------|
| `static` | 固定机位 | 默认运镜，大多数镜头使用 |
| `pan` | 水平摇摄 | 环境展示 |
| `tilt` | 垂直俯仰 | 上下打量 |
| `zoom_in` | 推镜头 | 强调表情/细节 |
| `zoom_out` | 拉镜头 | 揭示全貌 |
| `tracking` | 跟随移动 | 慎用，仅用于关键运动镜头 |

> 竖屏短剧以 `static` 和 `zoom_in` 为主。`tracking` 慎用（生成成本高且易出伪影）。

### 转场方式 (transition_to_next)

| 值 | 说明 | 使用场景 |
|----|------|---------|
| `cut` | 硬切 | 默认转场，占比 80% 以上 |
| `fade` | 淡入淡出 | 场景结束/开始、时间跳跃 |
| `dissolve` | 溶解叠化 | 情绪转换、回忆过渡 |

---

## image_prompt 编写规范

`image_prompt` 用于 ImageGen 生成首帧，必须包含以下要素（按顺序，逗号分隔）：

1. **角色外貌描述**：年龄、发型、脸型、眼睛、肤色、体型、服装。多角色按出场顺序。
   - 示例：`a 25-year-old woman with long black hair, fair skin, wearing a white floral dress`
2. **角色动作/表情**：姿态和表情。
   - 示例：`looking out the window with a melancholic expression`
3. **场景环境**：地点、室内/室外、关键道具。
   - 示例：`in a dimly lit bedroom, raindrops on the window`
4. **光线氛围**：光源方向、色温、明暗对比。
   - 示例：`soft moonlight from the window, cool blue tones`
5. **摄影风格**：镜头类型 + 画幅。
   - 示例：`close-up shot, shallow depth of field, cinematic composition, 9:16 vertical aspect ratio`

**完整示例**：
```
a 25-year-old Chinese woman with long straight black hair, fair skin, wearing a white floral dress, looking out the window with a melancholic expression, hands resting on the windowsill, in a dimly lit bedroom, raindrops on the window, soft moonlight from the window, cool blue tones, gentle shadows, close-up shot, shallow depth of field, cinematic composition, 9:16 vertical aspect ratio
```

> 必须包含角色外貌描述，供 S4 角色卡生成参考。从 `characters` 的 `appearance` 字段提取。

---

## video_prompt 编写规范

`video_prompt` 仅描述运动/动作/镜头运动，**不描述角色外貌**（角色已由首帧 image_prompt 锁定）。

1. **角色动作变化**：角色在视频中做什么动作（非外貌）。
   - 示例：`the woman slowly turns her head to the right, her expression shifts from calm to surprised`
2. **镜头运动**：`camera_movement` 对应的运动描述。
   - `static`：`camera remains still`
   - `zoom_in`：`camera slowly zooms in on the face`
   - `tracking`：`camera follows the person as they walk`
3. **环境动态**：场景中动态元素。
   - 示例：`rain continues to fall on the window, curtains gently swaying`

> **禁止**在 `video_prompt` 中出现角色外貌描述（年龄、发型、肤色、服装等）。

---

## 配乐基调标签体系

每个镜头的 `music_mood` 使用以下 7 种标签之一：

| 标签 | 说明 | BPM 范围 | 典型场景 |
|------|------|----------|---------|
| `tense` | 紧张 | 80-120 | 冲突对峙、危机逼近 |
| `romantic` | 浪漫 | 60-80 | 暧昧互动、表白、温情时刻 |
| `sad` | 悲伤 | 50-70 | 失去、离别、悲伤独白 |
| `happy` | 欢快 | 100-140 | 喜剧、团聚、轻松日常 |
| `suspense` | 悬疑 | 70-100 | 谜团、未知、等待揭晓 |
| `neutral` | 中性 | 60-80 | 过渡镜头、环境交代 |
| `action` | 动作 | 120-160 | 追逐、打斗、快节奏事件 |

---

## storyboard.json 输出格式

```json
{
  "$schema": "storyboard_v1",
  "request_id": "<uuid-v4>",
  "created_at": "<ISO-8601>",
  "aspect_ratio": "9:16",
  "target_duration": 60,
  "total_duration": 60,
  "shot_count": 12,
  "shots": [
    {
      "shot_id": "shot_01",
      "scene_id": "scene_01",
      "shot_type": "wide",
      "camera_movement": "static",
      "visual_description": "画面描述（中文）",
      "characters_in_shot": [],
      "dialogue": "",
      "action_notes": "动作指示和表演备注（中文）",
      "duration_seconds": 5,
      "transition_to_next": "cut",
      "music_mood": "neutral",
      "image_prompt": "ImageGen prompt（英文，含角色外貌+场景+光线+风格）",
      "video_prompt": "VideoGen prompt（英文，仅运动描述）",
      "negative_prompt": "禁止元素（英文）"
    }
  ]
}
```

---

## music_plan.json 输出格式

```json
{
  "$schema": "music_plan_v1",
  "request_id": "<uuid-v4>",
  "created_at": "<ISO-8601>",
  "overall_tone": "sad",
  "total_duration": 60,
  "segments": [
    {
      "segment_id": "seg_01",
      "shot_range": "shot_01 - shot_04",
      "mood": "sad",
      "tempo": 60,
      "instruments": ["piano", "strings"],
      "duration_seconds": 20,
      "source": "auto",
      "description": "配乐描述（中文）"
    }
  ]
}
```

配乐分段规则：遍历所有镜头，连续相同或相近 `music_mood` 的镜头归为一个 segment。

---

## 纪律约束

1. **只做分镜，不碰角色图/视频**：不调用 ImageGen、VideoGen。角色关键帧是 S4 职责，视频片段是 S5 职责
2. **产物是中间态**：不调用 `present_files` 展示 `storyboard.json` 或 `music_plan.json`
3. **image_prompt 必须含角色外貌**：从 `characters` 的 `appearance` 提取
4. **video_prompt 禁止含角色外貌**：只描述运动
5. **不修改剧本**：分镜基于 S2 产出的 `script.md`，不重写对白或修改情节
6. **不预创建目录**：`stage4/` 由 S4 创建
