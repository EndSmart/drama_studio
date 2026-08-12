# Credit Estimation — 信用消耗估算参考

> ImageGen / VideoGen 调用额外模型并消耗独立 credits。本文件提供估算公式、消耗表与降级策略。

---

## 消耗基准

| 操作 | 工具 | 单次消耗 | 说明 |
|------|------|---------|------|
| 角色关键帧 | ImageGen | 5-10 credits/张（中值 7.5） | 每角色 6 张：正面 + 侧面 + 4 表情 |
| 镜头首帧 | ImageGen 图生图 | 5-10 credits/张（中值 7.5） | 每镜头 1 张 |
| 视频片段 | VideoGen 图生视频 | 50-100 credits/5s（中值 75） | 每镜头 1 段 |
| TTS 配音 | sag (ElevenLabs) | 按字符计费 | 每角色对白 |
| 配乐 | Suno（外部平台） | 按平台计费 | 非 credits 体系 |

---

## 估算公式

### 镜头数预估

```
镜头数 = ceil(目标总时长 / 每镜头时长)
默认每镜头 5 秒
```

示例：目标 60s 短剧 → 12 镜头；目标 90s → 18 镜头

### ImageGen 消耗

```
角色关键帧 = 角色数 × 6 张 × 7.5 credits/张
镜头首帧 = 镜头数 × 7.5 credits/张
ImageGen 总计 = 角色关键帧 + 镜头首帧
```

### VideoGen 消耗

```
VideoGen 总计 = 镜头数 × 75 credits/段
```

### 总估算

```
总 credits = ImageGen 总计 + VideoGen 总计
```

### 估算示例

| 场景 | 角色数 | 镜头数 | ImageGen | VideoGen | 总计 |
|------|--------|--------|----------|----------|------|
| 60s 短剧，2 角色 | 2 | 12 | 2×6×7.5 + 12×7.5 = 180 | 12×75 = 900 | ~1080 |
| 90s 短剧，3 角色 | 3 | 18 | 3×6×7.5 + 18×7.5 = 270 | 18×75 = 1350 | ~1620 |
| 30s 短剧，2 角色 | 2 | 6 | 2×6×7.5 + 6×7.5 = 135 | 6×75 = 450 | ~585 |

---

## S0 预估提示模板

```
[信用消耗预估]
- 角色关键帧：{角色数} 角色 × 6 张 = {N1} 张 ImageGen → ~{C1} credits
- 镜头首帧：{镜头数} 张 ImageGen 图生图 → ~{C2} credits
- 视频片段：{镜头数} 段 VideoGen 图生视频 → ~{C3} credits
- TTS 配音：{角色数} 角色（可选）→ 按字符计费
- 预估总消耗：~{C_total} credits

请确认是否继续执行？（可输入"调整"来修改参数以降低消耗）
```

---

## 降级策略

当用户认为消耗过高时，提供以下降级选项（按效果递减排列）：

| 降级选项 | 节省量 | 质量影响 |
|---------|--------|---------|
| 降低分辨率 1080P → 720P | VideoGen 减少约 30% | 画质降低 |
| 减少角色表情关键帧 6张→3张（正面+中性+1表情） | 每角色省 22.5 credits | 表情一致性略降 |
| 减少镜头数（合并相近镜头） | 每减 1 镜头省 82.5 credits | 节奏变快 |
| 跳过 TTS 配音，仅使用字幕 | 省 TTS 全部消耗 | 无语音对白 |
| 使用已有音频库替代 Suno 生成 | 省 Suno 平台费用 | 配乐非定制 |
| 减少角色数 | 每减 1 角色省 45+ credits | 故事角色减少 |

### 降级交互

```
用户输入"调整"后：

当前参数：{角色数} 角色 / {镜头数} 镜头 / {分辨率} / {是否配音}
预估消耗：~{C_total} credits

可选降级方案：
1. 降低分辨率到 720P（省 ~{C} credits）
2. 减少表情关键帧到 3 张/角色（省 ~{C} credits）
3. 减少镜头数到 {N}（省 ~{C} credits）
4. 跳过 TTS 配音，仅字幕（省 TTS 消耗）
5. 组合降级

请选择（输入编号或"自定义"）：
```

---

## 实际消耗追踪

每个消耗 Stage 完成后，在 `pipeline-state.yaml` 的 `credit_tracking` 中记录实际消耗：

```yaml
credit_tracking:
  estimated_total: 1080
  actual_total: 1185
  breakdown:
    image_gen:
      calls: 24
      credits: 180
    video_gen:
      calls: 12
      credits: 900
    tts:
      characters: 12
      credits: 105
```

### S8 完成后总结

```
[信用消耗总结]
- ImageGen：{actual_image_calls} 次，{actual_image_credits} credits
- VideoGen：{actual_video_calls} 次，{actual_video_credits} credits
- TTS：{actual_tts_calls} 次，{actual_tts_credits} credits
- 总计：{actual_total} credits（预估 {estimated_total}，偏差 {diff}%）
```
