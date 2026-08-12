---
name: character-keyframe-gen
description: "角色关键帧生成。为每个角色生成 6 张关键帧设定图（正面/侧面/4 表情），建立角色卡 character_card.json，被 character-agent 加载后指导 Stage 4 的角色关键帧生成流程。首张文生图 + 后续 5 张图生图，角色卡是 S5 视频生成时保持角色一致性的核心依据。"
---

# Character Keyframe Gen — 角色关键帧生成

> 被 `character-agent` 加载，指导 Stage 4 角色关键帧生成。详细执行逻辑见 `../../agents/character-agent.md`。
> 角色一致性保障详细说明见 `../../references/character-consistency-guide.md`。

---

## 关键帧生成策略

### 每角色 6 张关键帧

| 关键帧文件 | 说明 | 生成方式 |
|------------|------|----------|
| `front.png` | 正面标准照（基准参考图） | **文生图** |
| `side.png` | 侧面照 | **图生图**，input image = `front.png` |
| `expr_neutral.png` | 中性表情 | **图生图**，input image = `front.png` |
| `expr_happy.png` | 开心表情 | **图生图**，input image = `front.png` |
| `expr_sad.png` | 悲伤表情 | **图生图**，input image = `front.png` |
| `expr_angry.png` | 愤怒表情 | **图生图**，input image = `front.png` |

### 生成顺序

1. 先为每个角色创建目录：`characters_dir/{角色名}/`
2. 生成 `front.png`（文生图）
3. 以 `front.png` 为输入，依次生成其余 5 张（图生图）

### 信用消耗

每张 ImageGen 约 7.5 credits。每角色：6 × 7.5 = **45 credits/角色**。信用预估在 S0 由 orchestrator 完成并请求用户确认。

---

## ImageGen 调用规范

### front.png — 文生图

```
ImageGen:
  prompt: "{seed_prompt}, front-facing portrait, looking directly at camera, neutral expression, full body visible, plain light gray background, character reference sheet style, 1024x1536 vertical"
  size: "1024x1536"
  quality: "high"
  style: "{输入 style 参数（realistic/anime/cinematic）}"
  output_dir: "{characters_dir}/{角色名}/"
```

### 后续 5 张 — 图生图

```
ImageGen:
  image: [{path: "{characters_dir}/{角色名}/front.png"}]
  input_fidelity: 0.8
  prompt: "{seed_prompt}, {目标表情/角度描述}"
  size: "1024x1536"
  quality: "high"
  output_dir: "{characters_dir}/{角色名}/"
```

各张的 prompt 后缀：
- `side.png`: `"side profile view, looking to the left, same character, same outfit, 1024x1536 vertical"`
- `expr_neutral.png`: `"neutral expression, slight smile, relaxed face, same character, same outfit, 1024x1536 vertical"`
- `expr_happy.png`: `"happy expression, big smile, bright eyes, same character, same outfit, 1024x1536 vertical"`
- `expr_sad.png`: `"sad expression, slightly frowning, downcast eyes, same character, same outfit, 1024x1536 vertical"`
- `expr_angry.png`: `"angry expression, furrowed brows, intense eyes, same character, same outfit, 1024x1536 vertical"`

**关键参数**：
- `input_fidelity` = `0.8`：较高值，确保图生图与 `front.png` 的角色特征一致
- `size` = `"1024x1536"`：竖屏比例，统一
- `quality` = `"high"`：高质量输出

---

## seed_prompt 编写规范

`seed_prompt` 是角色外貌的**固定描述前缀**，写入 `character_card.json` 后不可修改。后续所有 S4 表情生成和 S5 视频首帧生成时，prompt 都拼接此前缀。

### 必须包含的 7 个要素

| 序号 | 要素 | 英文描述 | 示例 |
|------|------|----------|------|
| 1 | 年龄 | `a 25-year-old woman` | `a 30-year-old man` |
| 2 | 发型 | `with long straight black hair` | `short neatly combed black hair` |
| 3 | 脸型 | `oval face` | `angular face with a strong jawline` |
| 4 | 眼睛 | `large almond-shaped dark brown eyes` | `small deep-set eyes with a sharp gaze` |
| 5 | 肤色 | `fair skin` | `warm skin tone` |
| 6 | 体型 | `slim build` | `tall athletic build` |
| 7 | 默认服装 | `wearing a white floral dress` | `wearing a tailored black suit with a white shirt and dark tie` |

### 完整示例

```
a 25-year-old Chinese woman with long straight black hair reaching her waist, oval face, large almond-shaped dark brown eyes, fair skin, slim build, wearing a white floral dress
```

```
a 30-year-old Chinese man with short neatly combed black hair, angular face with a strong jawline, small deep-set eyes with a sharp gaze, warm skin tone, tall athletic build, wearing a tailored black suit with a white shirt and dark tie
```

### 编写规则

- 使用英文，逗号分隔
- 从 `characters` 输入的 `physical_description`、`clothing_description`、`personality` 提取
- **不包含**场景、光线、镜头描述（由 S3 的 `image_prompt` 负责）
- 写入 `character_card.json` 后**不可修改**

---

## character_card.json 输出格式

```json
{
  "$schema": "character_card_v1",
  "name": "角色名",
  "role": "主角/配角/反派/路人",
  "physical_description": "中文物理描述",
  "clothing_description": "中文服装描述",
  "personality": "中文性格描述",
  "style_locked": "realistic",
  "seed_prompt": "固定描述前缀（英文）",
  "keyframe_paths": {
    "front": "characters/{角色名}/front.png",
    "side": "characters/{角色名}/side.png",
    "expressions": {
      "neutral": "characters/{角色名}/expr_neutral.png",
      "happy": "characters/{角色名}/expr_happy.png",
      "sad": "characters/{角色名}/expr_sad.png",
      "angry": "characters/{角色名}/expr_angry.png"
    }
  },
  "reference_image": "characters/{角色名}/front.png",
  "consistency_notes": "角色面部特征以 front.png 为基准。所有后续生成使用 seed_prompt 作为前缀 + 图生图以 front.png 为输入。表情变化时面部结构保持不变，仅改变眉毛、眼睛和嘴角。"
}
```

| 关键字段 | 说明 |
|----------|------|
| `seed_prompt` | 角色外貌固定前缀，后续所有生成拼接此前缀 |
| `reference_image` | 必须等于 `front.png` 路径，S5 图生图首帧以此作为 `image` 输入 |
| `keyframe_paths` | 所有关键帧的相对路径，供 S5 按情绪选择表情帧 |

---

## 角色一致性保障原则

1. **三层锁定机制**：
   - 第一层（S4）：`seed_prompt` 固定前缀 + `reference_image` 基准图
   - 第二层（S5）：首帧 `image_prompt` = `seed_prompt` + 场景描述
   - 第三层（S5）：图生图以 `reference_image` 为输入，`input_fidelity` ≥ 0.7
2. **`reference_image` 必须指向 `front.png`**：不得指向其他关键帧
3. **`input_fidelity` = 0.8**：图生图时使用较高值确保与基准图一致
4. **`seed_prompt` 不可修改**：写入后即锁定，S5 全部复用
5. **空镜头不生成角色卡**：`characters_in_shot` 为空数组的镜头不为其创建角色

---

## 纪律约束

1. **只做角色关键帧，不碰视频**：不调用 VideoGen
2. **产物是中间态**：不调用 `present_files` 展示关键帧图片或 `character_card.json`
3. **`reference_image` 必须指向 `front.png`**
4. **`seed_prompt` 写入后不可修改**
5. **`input_fidelity` = 0.8**
6. **不修改上游数据**：只读取 `script.md` 和 `storyboard.json`
7. **生成失败处理**：单张失败时重试 1 次，仍失败则标记在 `consistency_notes` 中，不阻塞其他角色
