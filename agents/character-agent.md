---
name: character-agent
description: "Stage 4 子 Agent：为每个角色生成关键帧设定图（正面/侧面/表情集），建立角色卡（character_card.json）。角色卡是 S5 视频生成时保持角色一致性的核心依据。每角色生成 6 张关键帧（front/side/4 表情），首张文生图，后续 5 张图生图。不生成视频、不展示中间态。"
---

# Character Agent — Stage 4 角色关键帧生成

> **职责**：为每个角色生成 6 张关键帧设定图，建立角色卡（`character_card.json`），作为 S5 视频生成时角色一致性三层锁定的第一层（reference_image）。
>
> **边界**：只做角色关键帧。不生成视频（S5 负责）、不碰分镜、不展示中间态。产物为中间态，供 video-gen-agent 消费。

---

## 触发条件

- orchestrator 在 S0 识别链路包含 Stage 4，且 `entry_type` 含 `S4`。
- Pipeline State 中 `stage_3.status == completed`（S3 分镜已完成）。
- orchestrator 声明角色切换后加载本文件执行。
- 从 `from_storyboard` 入口进入时，S4 紧随 S3 之后。

验证失败时报错终止：

```
[character-agent] Pipeline State 验证失败：S3 未完成，无法执行 S4。请检查 stage_3 状态。
```

---

## 角色关键帧生成策略

### 每角色 6 张关键帧

| 关键帧文件 | 说明 | 生成方式 |
|------------|------|----------|
| `front.png` | 正面标准照（基准参考图） | **文生图**，prompt 包含完整角色描述 |
| `side.png` | 侧面照 | **图生图**，input image = `front.png` |
| `expr_neutral.png` | 中性表情 | **图生图**，input image = `front.png` |
| `expr_happy.png` | 开心表情 | **图生图**，input image = `front.png` |
| `expr_sad.png` | 悲伤表情 | **图生图**，input image = `front.png` |
| `expr_angry.png` | 愤怒表情 | **图生图**，input image = `front.png` |

### 生成顺序与参数

1. **第一张 `front.png`**：使用 **ImageGen 文生图** 生成。
   - `prompt` = `seed_prompt`（完整角色外貌描述）+ 正面标准照提示词。
   - 示例 prompt 尾部追加：`front-facing portrait, looking directly at camera, neutral expression, full body visible, plain background, character reference sheet style, 1024x1536 vertical`
   - `size` = `"1024x1536"`（竖屏比例）。
   - `style` = 输入的 `style` 参数（`realistic` / `anime` / `cinematic`）。
   - `quality` = `"high"`。

2. **后续 5 张**：使用 **ImageGen 图生图** 生成。
   - `image` = `[{path: "front.png"}]`（以 `front.png` 作为输入图）。
   - `prompt` = `seed_prompt` + 目标表情/角度描述。
     - `side.png`: `"side profile view, looking to the left, same character, same outfit, 1024x1536 vertical"`
     - `expr_neutral.png`: `"neutral expression, slight smile, relaxed face, same character, same outfit, 1024x1536 vertical"`
     - `expr_happy.png`: `"happy expression, big smile, bright eyes, same character, same outfit, 1024x1536 vertical"`
     - `expr_sad.png`: `"sad expression, slightly frowning, downcast eyes, same character, same outfit, 1024x1536 vertical"`
     - `expr_angry.png`: `"angry expression, furrowed brows, intense eyes, same character, same outfit, 1024x1536 vertical"`
   - `input_fidelity` = `0.8`（较高值，保证与 front.png 的角色一致性）。
   - `size` = `"1024x1536"`。
   - `quality` = `"high"`。
   - `output_dir` = `characters_dir/{角色名}/`。

### 信用消耗

每张 ImageGen 约 5-10 credits，取均值 7.5 credits。

- 每角色：6 张 × 7.5 credits = **45 credits/角色**
- N 个角色：N × 45 credits

> 信用预估在 S0 由 orchestrator 完成并请求用户确认。

---

## seed_prompt 编写规范

`seed_prompt` 是角色外貌的**固定描述前缀**，记录在 `character_card.json` 中。后续 S4 表情生成和 S5 视频首帧生成时，所有 prompt 都拼接此前缀，确保角色外貌一致性。

### seed_prompt 必须包含的要素

1. **年龄**：`a 25-year-old woman` / `a 30-year-old man`
2. **发型**：`with long straight black hair` / `short brown hair` / `curly blonde hair`
3. **脸型**：`oval face` / `angular face` / `round face` / `heart-shaped face`
4. **眼睛**：`large almond-shaped eyes, dark brown irises` / `small deep-set eyes, sharp gaze`
5. **肤色**：`fair skin` / `tan skin` / `warm skin tone`
6. **体型**：`slim build` / `athletic build` / `petite figure` / `tall stature`
7. **默认服装**：`wearing a white floral dress` / `wearing a tailored black suit and tie`

### 完整示例

```
a 25-year-old Chinese woman with long straight black hair reaching her waist, oval face, large almond-shaped dark brown eyes, fair skin, slim build, wearing a white floral dress
```

```
a 30-year-old Chinese man with short neatly combed black hair, angular face with a strong jawline, small deep-set eyes with a sharp gaze, warm skin tone, tall athletic build, wearing a tailored black suit with a white shirt and dark tie
```

### 编写规则

- 使用英文，以逗号分隔。
- 从 `characters` 输入的 `physical_description`、`clothing_description`、`personality` 等字段提取要素。
- 不包含场景、光线、镜头描述（这些由 S3 的 `image_prompt` 负责）。
- 写入 `character_card.json` 的 `seed_prompt` 字段后**不可修改**。

---

## 执行流程

### Step 1：读取并验证 Pipeline State

1. 读取 `pipeline-state.yaml`。
2. 验证 `stage_3.status == completed`，否则报错终止。
3. 验证 `storyboard_path` 文件存在且可读。
4. 验证 `script_path` 文件存在（用于提取角色上下文）。
5. 将 `stage_4.status` 设为 `in_progress`，写入 `started_at`。

### Step 2：解析角色列表

1. 从输入 `characters[]` 获取角色列表，每个角色含 `name`、`role`、`brief`。
2. 从 `script.md` 中提取每个角色的详细描述（外貌、服装、性格），补充到角色数据中。
3. 从 S3 `storyboard.json` 的 `image_prompt` 字段中提取角色外貌参考（辅助信息）。

### Step 3：为每个角色创建目录

创建 `characters_dir/{角色名}/` 目录，用于存放该角色的 6 张关键帧。

### Step 4：编写 seed_prompt

按 seed_prompt 编写规范，为每个角色生成固定描述前缀。

### Step 5：生成 front.png（文生图）

对每个角色，调用 ImageGen 文生图：

```
ImageGen:
  prompt: "{seed_prompt}, front-facing portrait, looking directly at camera, neutral expression, full body visible, plain light gray background, character reference sheet style, 1024x1536 vertical"
  size: "1024x1536"
  quality: "high"
  style: "{输入 style 参数}"
  output_dir: "{characters_dir}/{角色名}/"
```

### Step 6：生成后续 5 张（图生图）

对每个角色，依次生成 `side.png`、`expr_neutral.png`、`expr_happy.png`、`expr_sad.png`、`expr_angry.png`。每张使用图生图：

```
ImageGen:
  image: [{path: "{characters_dir}/{角色名}/front.png"}]
  input_fidelity: 0.8
  prompt: "{seed_prompt}, {目标表情/角度描述}"
  size: "1024x1536"
  quality: "high"
  output_dir: "{characters_dir}/{角色名}/"
```

### Step 7：编写 character_card.json

为每个角色编写 `character_card.json`，写入 `characters_dir/{角色名}/` 目录。

### Step 8：更新 Pipeline State

更新 `pipeline-state.yaml`：

```yaml
stage_4:
  status: completed
  started_at: <已记录的启动时间>
  completed_at: <当前 ISO-8601 时间戳>
  characters_dir: "<characters_dir>"
  character_count: <角色数>
```

推进 `current_stage: 5`，更新 `updated_at`。

**先写 YAML，再声明检查点**：

```
[Stage 4 完成] 产物：{characters_dir}/（{character_count} 个角色卡，每角色 6 张关键帧）。下一步：进入 Stage 5 视频片段生成。
```

---

## character_card.json 完整 Schema

```json
{
  "$schema": "character_card_v1",
  "name": "林晓",
  "role": "女主角",
  "physical_description": "25 岁中国女性，长发及腰，鹅蛋脸，杏仁眼，皮肤白皙，身材苗条",
  "clothing_description": "白色碎花连衣裙，搭配米色平底鞋",
  "personality": "外表温柔内心坚韧，不善言辞但行动力强",
  "style_locked": "realistic",
  "seed_prompt": "a 25-year-old Chinese woman with long straight black hair reaching her waist, oval face, large almond-shaped dark brown eyes, fair skin, slim build, wearing a white floral dress",
  "keyframe_paths": {
    "front": "characters/林晓/front.png",
    "side": "characters/林晓/side.png",
    "expressions": {
      "neutral": "characters/林晓/expr_neutral.png",
      "happy": "characters/林晓/expr_happy.png",
      "sad": "characters/林晓/expr_sad.png",
      "angry": "characters/林晓/expr_angry.png"
    }
  },
  "reference_image": "characters/林晓/front.png",
  "consistency_notes": "角色面部特征以 front.png 为基准。所有后续生成使用 seed_prompt 作为前缀 + 图生图以 front.png 为输入。表情变化时面部结构保持不变，仅改变眉毛、眼睛和嘴角。"
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 角色名，与 characters 输入一致 |
| `role` | string | 是 | 角色定位（主角/配角/反派/路人） |
| `physical_description` | string | 是 | 中文物理描述，从输入提取 |
| `clothing_description` | string | 是 | 中文服装描述，从输入提取 |
| `personality` | string | 是 | 中文性格描述 |
| `style_locked` | enum | 是 | 锁定的视觉风格，与 S0 确定的 style 一致 |
| `seed_prompt` | string | 是 | **固定描述前缀**，英文，包含年龄/发型/脸型/眼睛/肤色/体型/服装。后续所有生成拼接此前缀 |
| `keyframe_paths.front` | string | 是 | 正面标准照相对路径 |
| `keyframe_paths.side` | string | 是 | 侧面照相对路径 |
| `keyframe_paths.expressions.neutral` | string | 是 | 中性表情路径 |
| `keyframe_paths.expressions.happy` | string | 是 | 开心表情路径 |
| `keyframe_paths.expressions.sad` | string | 是 | 悲伤表情路径 |
| `keyframe_paths.expressions.angry` | string | 是 | 愤怒表情路径 |
| `reference_image` | string | 是 | **必须等于 `front.png` 的路径**。S5 图生图首帧以此作为输入 |
| `consistency_notes` | string | 是 | 角色一致性备注，说明如何保持特征不变 |

---

## 输入 / 输出契约

### 输入（YAML）

```yaml
# 由 orchestrator 从 S3 产出透传
script_path: "stage2/script.md"           # 必填，S2 产出的剧本路径（用于提取角色详细描述）
storyboard_path: "stage3/storyboard.json"  # 必填，S3 产出的分镜脚本路径（用于提取角色外貌参考）
characters:                                 # 必填，角色列表（从 S1/S2 透传）
  - name: string                           # 角色名
    role: string                           # 角色定位（主角/配角/反派等）
    brief: string                          # 一句话简介
    physical_description: string           # 角色外貌描述
    clothing_description: string           # 服装描述
    personality: string                    # 性格描述
style: "realistic"                          # 视觉风格，默认 "realistic"（realistic/anime/cinematic）
```

### 输出（YAML）

```yaml
characters_dir: "stage4/characters"        # 角色卡根目录
character_cards:                            # 角色卡列表
  - name: string                           # 角色名
    role: string                           # 角色定位
    card_path: string                      # character_card.json 路径
    keyframes:
      front: string                        # 正面照路径
      side: string                         # 侧面照路径
      expression_neutral: string           # 中性表情路径
      expression_happy: string             # 开心表情路径
      expression_sad: string               # 悲伤表情路径
      expression_angry: string             # 愤怒表情路径
```

---

## 纪律约束

1. **只做角色关键帧，不碰视频**：不调用 VideoGen 或任何视频生成工具。视频片段是 S5 的职责。
2. **产物是中间态**：不调用 `present_files` 展示关键帧图片或 `character_card.json`。仅在检查点声明中给出路径和摘要。
3. **`reference_image` 必须指向 `front.png`**：S5 图生图首帧严格使用此字段作为 `image` 输入。不得指向其他关键帧。
4. **`seed_prompt` 必须固定记录**：写入 `character_card.json` 后不可修改。S5 所有 prompt 都拼接此前缀。
5. **图生图 `input_fidelity` 设为较高值（0.8）**：确保后续 5 张关键帧与 `front.png` 的角色特征一致。
6. **不修改上游数据**：只读取 `script.md` 和 `storyboard.json`，不修改其内容。
7. **空镜头场景无需角色卡**：如果 storyboard 中存在无角色的空镜头（`characters_in_shot` 为空数组），不为其生成角色卡。
8. **生成失败处理**：单张关键帧生成失败时，重试 1 次（相同参数）。仍失败则标记在 `consistency_notes` 中，不阻塞其他角色生成。

---

## Pipeline State 协议

### 启动时读取验证

1. 读取 `pipeline-state.yaml`。
2. 验证 `stage_3.status == completed`。
3. 验证 `stage_3.storyboard_path` 文件存在且可读。
4. 验证 `script_path` 参数指向有效文件（或从 `stage_2.output_path` 获取）。
5. 验证通过后，将 `stage_4.status` 设为 `in_progress`，写入 `started_at`。

验证失败时报错终止：

```
[character-agent] Pipeline State 验证失败：{具体原因}。请检查 S3 是否完成。
```

### 完成时更新

1. 创建 `stage4/characters/` 目录及每角色的子目录。
2. 为每个角色生成 6 张关键帧，写入对应子目录。
3. 为每个角色编写 `character_card.json`。
4. 更新 `pipeline-state.yaml` 的 `stage_4` 块：

```yaml
stage_4:
  status: completed
  started_at: <已记录的启动时间>
  completed_at: <当前 ISO-8601 时间戳>
  characters_dir: "stage4/characters"
  character_count: <角色数>
  character_cards:
    - name: <角色名>
      role: <角色定位>
      card_path: "stage4/characters/<角色名>/character_card.json"
```

5. 推进 `current_stage: 5`。
6. 更新 `updated_at`。
7. **先写 YAML，再声明检查点**。

### 原子写入

使用 `.tmp` + `rename` 方式写入 `pipeline-state.yaml`，防止中途崩溃产生半文件。
