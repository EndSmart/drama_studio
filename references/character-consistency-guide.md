# 角色一致性策略详解

角色一致性是短剧制作的核心质量指标。本文档定义三层锁定机制及全流程一致性保障规范。

---

## 1. 三层锁定机制

### 第一层：角色卡（character_card.json）

角色卡是角色视觉身份的不可变基准。每个角色必须拥有独立的 `character_card.json`，包含以下字段：

```json
{
  "character_id": "char_001",
  "name": "林晓",
  "seed_prompt": "25-year-old Asian woman, long straight black hair, oval face, almond-shaped brown eyes, fair skin, slim build, wearing a white cotton blouse with collar and dark navy slim trousers",
  "reference_image": "assets/characters/char_001_ref.png",
  "description": "温柔但坚韧的女主角，默认服装为白衬衫+深蓝长裤"
}
```

- `seed_prompt`：固定描述角色年龄、发型、脸型、眼睛、肤色、体型、默认服装，作为所有后续生成的不可变前缀。
- `reference_image`：基准参考图，必须与 `seed_prompt` 描述严格一致。该图作为 ImageGen 的 `input image` 使用。

### 第二层：ImageGen 图生图首帧

生成每个镜头的首帧时，使用图生图模式：

- **input image** = 角色卡 `reference_image`
- **prompt** = `seed_prompt` + 镜头画面描述（场景、光线、构图、情绪）
- **input_fidelity** = 控制与参考图的相似程度（见下方参数建议）

生成流程：

1. 从角色卡读取 `seed_prompt` 和 `reference_image` 路径。
2. 将 `seed_prompt` 作为 prompt 的开头前缀。
3. 追加当前镜头的场景描述、光线、构图信息。
4. 设置 `input_fidelity` 参数。
5. 调用 ImageGen，传入 `reference_image` 作为 input image。

**示例 prompt 结构：**

```
{seed_prompt}, standing in a sunlit hospital corridor, soft warm natural light from left window, medium shot, cinematic composition, shallow depth of field
```

### 第三层：VideoGen 图生视频

将首帧转化为视频时，仅描述运动，不重复角色外貌：

- **image** = 第二层生成的首帧
- **prompt** = 仅运动描述（角色动作、镜头运动、环境动态）

**示例 video prompt：**

```
The woman walks forward slowly, camera tracks forward following her, sunlight shifts through the corridor windows
```

不在此层重复 `seed_prompt` 中的外貌描述，避免与首帧产生冲突。

---

## 2. seed_prompt 编写规范

`seed_prompt` 是角色视觉锁定的根基。编写时必须遵循以下规范：

### 必须包含的要素

| 要素 | 说明 | 示例 |
|------|------|------|
| 年龄 | 具体数字或合理范围 | `28-year-old` |
| 发型 | 长度、形状、颜色、造型 | `short curly brown hair` |
| 脸型 | 具体形状描述 | `square jawline` |
| 眼睛 | 形状、颜色 | `deep-set dark eyes` |
| 肤色 | 具体色调 | `light tan skin` |
| 体型 | 身材描述 | `athletic build, broad shoulders` |
| 默认服装 | 具体衣物描述 | `wearing a charcoal grey suit jacket over a white shirt` |

### 编写原则

- 使用英文编写，逗号分隔的描述性短语。
- 从整体到细节：年龄 → 发型 → 脸型 → 眼睛 → 肤色 → 体型 → 服装。
- 避免主观情绪词（如 "beautiful"），使用客观可量化描述。
- 服装描述需具体到款式和颜色，不使用模糊词（如 "casual clothes"）。
- 作为一个不可变前缀，在所有镜头的 image_prompt 中原样拼接。

### 错误示例

```
# 错误：缺少脸型、眼睛、肤色，服装模糊
young woman, pretty, nice hair, casual outfit
```

### 正确示例

```
# 正确：要素完整，描述客观
30-year-old Asian man, short undercut black hair, square jawline, narrow monolid eyes, light olive skin, athletic build, wearing a black leather jacket over a grey crew-neck t-shirt
```

---

## 3. input_fidelity 参数使用建议

`input_fidelity` 控制生成图像与输入参考图的相似程度。值越高越接近参考图，值越低越允许变化。

### 参数选择指南

| 场景 | input_fidelity | 说明 |
|------|---------------|------|
| 角色关键帧（特写、正脸） | 0.8 - 0.9 | 高保真，严格锁定角色面部特征 |
| 镜头首帧（中景、全景） | 0.5 - 0.7 | 允许场景和构图变化，保持角色特征 |
| 换装镜头 | 0.4 - 0.6 | 保留面部特征，允许服装变化 |
| 情绪转变镜头 | 0.6 - 0.8 | 保留角色特征，允许表情变化 |

### 使用原则

- 默认值设为 **0.7**，适用于大多数标准镜头。
- 角色面部是视觉识别的核心，任何镜头都不要低于 0.4。
- 同一场景内的连续镜头保持相同的 `input_fidelity` 值。
- 如果生成结果角色特征漂移，提高 `input_fidelity` 后重新生成。

---

## 4. 多角色镜头一致性

当一个镜头中出现多个角色时：

1. **选择主要角色** 的 `reference_image` 作为 ImageGen 的 input image。
2. **其他角色** 在 prompt 中通过文字描述补充。
3. prompt 结构：`{主角seed_prompt} + {配角文字描述} + 场景描述`。

### 示例

主角林晓与配角陈默对话镜头：

```
# input image: char_001 (林晓) 的 reference_image
# input_fidelity: 0.7

{林晓seed_prompt}, standing face to face with a 32-year-old Asian man in a dark grey business suit with short black hair and glasses, modern office interior, fluorescent overhead lighting, medium two-shot, cinematic composition
```

### 多角色注意事项

- 一个镜头最多在 prompt 中描述 3 个角色，超过 3 个角色时使用群景描述。
- 配角如果反复出现，也应建立独立的角色卡。
- 多角色镜头的 `input_fidelity` 不超过 0.7，避免主角色过度锁定导致配角无法生成。

---

## 5. 跨镜头一致性增强

同一场景中的连续镜头，可利用前一镜头的末帧作为下一镜头首帧的参考，增强视觉连贯性。

### 操作流程

1. 生成镜头 N 的首帧并生成视频后，使用 ffmpeg 从视频末尾提取末帧：
   ```bash
   ffmpeg -i shot_N.mp4 -ss <duration-0.5> -frames:v 1 shot_N_lastframe.png
   ```
2. 生成镜头 N+1 的首帧时，将 `shot_N_lastframe.png` 作为 ImageGen 的 input image（替代角色卡 reference_image）。
3. `input_fidelity` 设为 0.6-0.8，保持场景连贯。
4. prompt 中仍然包含 `seed_prompt` 前缀，确保角色特征不漂移。

### 适用场景

- 同一场景的连续镜头切换（如正反打对话）。
- 时间上紧密衔接的镜头（如角色推门进入 → 室内转身）。

### 不适用场景

- 场景跳转（如从室内切到室外）。
- 时间跳跃（如回忆闪回）。
- 以上情况仍使用角色卡 `reference_image` 作为 input image。

---

## 6. 一致性验证检查清单

每个镜头生成后，按以下清单逐项检查：

### 必检项

- [ ] **首帧输入源**：首帧是否使用了角色卡 `reference_image`（或前一镜头末帧）作为 input image？
- [ ] **seed_prompt 前缀**：image_prompt 是否以 `seed_prompt` 开头？
- [ ] **面部特征一致**：生成图像中角色面部（脸型、眼睛、发型、肤色）是否与 reference_image 一致？
- [ ] **服装一致**：角色服装是否与 `seed_prompt` 中的默认服装一致（除非剧情要求换装）？
- [ ] **input_fidelity 合理**：当前镜头的 `input_fidelity` 值是否符合参数使用建议？
- [ ] **video_prompt 纯运动**：video_prompt 是否仅包含运动描述，未重复角色外貌？

### 抽检项

- [ ] **多角色描述完整**：多角色镜头中，配角是否有文字描述？
- [ ] **跨镜头连贯**：连续镜头的场景光线、构图是否衔接？
- [ ] **换装记录**：如果发生换装，是否更新了角色卡或 prompt 中的服装描述？

### 检查不通过时的处理

- 面部特征漂移：提高 `input_fidelity` 至 0.85+，重新生成首帧。
- 服装变化：在 prompt 中强化服装描述，或提高 `input_fidelity`。
- 整体不相似：检查 `seed_prompt` 是否完整，检查 `reference_image` 是否清晰。

---

## 7. 常见问题与解决方案

### 问题 1：角色外貌漂移

**现象**：不同镜头中角色的面部特征（脸型、眼睛、发型）出现明显差异。

**原因**：
- `input_fidelity` 设置过低。
- `seed_prompt` 描述不完整或含模糊词。
- 未使用 `reference_image` 作为 input image。

**解决方案**：
1. 确认每次生成都传入了 `reference_image`。
2. 将 `input_fidelity` 提高至 0.8 以上。
3. 检查 `seed_prompt` 是否包含全部 7 个必要要素。
4. 移除 `seed_prompt` 中的主观形容词，替换为客观描述。

### 问题 2：服装变化

**现象**：同一场景中角色服装在不同镜头间发生变化。

**原因**：
- `seed_prompt` 中服装描述模糊。
- `input_fidelity` 过低导致服装生成不可控。
- prompt 中追加了与 `seed_prompt` 矛盾的服装描述。

**解决方案**：
1. 在 `seed_prompt` 中使用精确的服装描述（款式+颜色+材质）。
2. 确保镜头描述中不包含与默认服装矛盾的内容。
3. 如剧情需要换装，创建换装后的新 `seed_prompt` 变体，并在分镜脚本中标注。
4. 换装镜头使用较低的 `input_fidelity`（0.4-0.6），换装完成后恢复。

### 问题 3：表情不匹配

**现象**：角色表情与镜头要求的情绪不符。

**原因**：
- video_prompt 中缺少动作/表情描述。
- 首帧生成的表情与视频运动方向冲突。

**解决方案**：
1. 在 image_prompt 中加入情绪关键词（如 "with a determined expression"）。
2. 在 video_prompt 中明确描述面部动作（如 "her expression shifts to a subtle smile"）。
3. 情绪转变镜头的 `input_fidelity` 设为 0.6-0.8，允许表情变化但保持角色特征。

### 问题 4：多角色镜头中配角面貌不一致

**现象**：配角在不同镜头中面貌不同。

**原因**：配角未建立角色卡，仅靠文字描述。

**解决方案**：
1. 为出现 2 次以上的配角建立独立角色卡。
2. 配角首次出现时即生成 `reference_image` 并锁定。
3. 后续镜头使用配角 `reference_image` 作为 input image（或与主角参考图交替使用）。

### 问题 5：跨镜头场景不连贯

**现象**：同一场景的连续镜头中，光线、背景出现跳变。

**原因**：每个镜头独立生成首帧，未利用跨镜头参考。

**解决方案**：
1. 使用前一镜头末帧作为下一镜头首帧的 input image。
2. 在 prompt 中保持场景描述一致（相同的光线、背景描述）。
3. 连续镜头使用相同的 `input_fidelity` 值。

### 问题 6：生成图像风格不一致

**现象**：不同镜头的画面风格（写实/动漫/油画感）不统一。

**原因**：prompt 中缺少风格关键词。

**解决方案**：
1. 在所有 image_prompt 末尾追加统一风格关键词（如 "cinematic photorealistic style"）。
2. 将风格关键词加入 `seed_prompt` 或作为全局后缀模板。
3. 所有镜头使用相同的风格后缀，确保整体视觉风格统一。
