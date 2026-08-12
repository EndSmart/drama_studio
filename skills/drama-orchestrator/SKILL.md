---
name: drama-orchestrator
description: "短剧制作统一编排入口。职责：识别意图 → 预估信用消耗并请求用户确认 → 编排 9 个 Stage 能力链（S0 编排 / S1 故事 / S2 剧本 / S3 分镜+配乐 / S4 角色关键帧 / S5 视频生成 / S6 粗剪 / S7 精剪迭代 / S8 配乐字幕成片）→ 委派对应子 Agent 执行；S8 产出 final_drama.mp4 后**强制 present_files 展示成片**，本 skill 调用结束。"
---

# Drama Maker Orchestrator

> **Orchestrator = 意图识别 + 信用预算 + 能力编排（composer，不是 lookup table）。**
> 自身不创作/不生成图片/不生成视频/不剪辑，只做五件事：识别场景 → 预估信用消耗 → 组合 Stage 能力链 → 分派子 Agent 执行 → 记录溯源。
> **编排层只拥有"路由 + 跨层数据衔接 + 人工介入暂停"；每个能力"内部怎么干、I/O 契约"由对应 `agents/*.md` 负责，本文件不复述。**

> 📁 **子 Agent 路径约定**：`story-agent` / `script-agent` / `storyboard-agent` / `character-agent` / `video-gen-agent` / `editing-agent` / `finalize-agent` 七份 Agent 定义位于 **plugin 根的 `agents/` 目录**下。从本文件出发的相对路径为 `../../agents/<name>.md`。

---

## 意图识别与编排（唯一决策点）

Orchestrator 按能力组合工作，不穷举场景。预设只是高频组合的命名，遇到长尾场景可按编排规则自行组合。

### 原子能力（编排的积木 = 路由表）

| Stage | 能力 | 执行者 | 输入 → 输出 |
|-------|------|--------|-------------|
| S0 | 意图识别 + 信用预算 + pipeline 初始化 | orchestrator | 主题文本 → `entry_type` + `stage_chain` + pipeline-state.yaml |
| S1 | 故事文本生成 | `story-agent` | 主题 → `story.md` + 角色列表 |
| S2 | 剧本生成 | `script-agent` | `story.md` → `script.md`（场景/对白/动作） |
| S3 | 分镜脚本 + 配乐基调 | `storyboard-agent` | `script.md` → `storyboard.json` + `music_plan.json` |
| S4 | 角色关键帧生成 | `character-agent` | `script.md` + `storyboard.json` → `characters/` 目录 + 角色卡 |
| S5 | 视频片段生成 | `video-gen-agent` | `storyboard.json` + `characters/` → `clips/` 目录 |
| S6 | 粗剪 | `editing-agent` | `clips/` + `storyboard.json` → `rough_cut.mp4` |
| S7 | 精剪（人工反馈迭代） | `editing-agent` | `rough_cut.mp4` + feedback → `fine_cut.mp4`（可回溯 S5） |
| S8 | 配乐 + 字幕 + 成片 | `finalize-agent` | `fine_cut.mp4` + `music_plan.json` → `final_drama.mp4` + `.srt` |

### 承接边界与出口

- **本 skill 承接**：S1-S8 的类型连通组合，任何链路都**终于 S8**（配乐字幕成片）。
- **S8 即链路终点**：finalize-agent 完成配乐/字幕/合成、**强制 `present_files` 展示 `final_drama.mp4`** 后，声明检查点、**本 skill 调用结束**。
- **S6→S7 人工暂停**：S6 粗剪完成后触发 mandatory checkpoint，**暂停执行**等待人工反馈，不自动进入 S7。

### 常见预设（entry_type → 链路映射，唯一真相源）

| 预设 `entry_type` | 链路（控制流） | 触发场景 |
|-------------------|---------------|---------|
| `full_pipeline` | S1→S2→S3→S4→S5→S6→S7→S8 | 给定主题，从零制作完整短剧 |
| `from_script` | S3→S4→S5→S6→S7→S8 | 已有剧本，从分镜开始 |
| `from_storyboard` | S4→S5→S6→S7→S8 | 已有分镜脚本，从角色生成开始 |
| `from_clips` | S6→S7→S8 | 已有视频片段，从剪辑开始 |
| `refinement` | S7→S8 | 已有粗剪/精剪，需精修 + 成片 |

### 编排规则（组合 > 穷举）

合法链 = S1-S8 的类型连通子序列，且必须满足：

1. **类型衔接**：前一 Stage 的输出类型必须匹配后一 Stage 的输入。
2. **创作后必分镜**：走了 S1 就必须经 S2→S3，不允许 S1 直连 S4。
3. **分镜后必角色卡**：走了 S3 就必须经 S4，S5 视频生成依赖 S4 角色卡。
4. **角色卡后必视频**：走了 S4 就必须经 S5，角色卡是 S5 的输入。
5. **S8 出口**：任何链路必须终于 S8（本编排层内 S8 只有 `finalize-agent` 一个执行者）。
6. **S6→S7 暂停**：S6 完成后暂停等待人工反馈，不自动推进。

---

## Stage 0：意图识别 + 信用预算 + pipeline 初始化

### S0.1 意图识别

接收用户输入，判断：

1. **entry_type**：按"常见预设"表匹配。检测用户是否已提供故事/剧本/分镜/视频片段。
2. **global_config**：提取全局参数（主题、类型、目标时长、画幅、分辨率、视觉风格、集数）。

### S0.2 信用预算预估

根据 entry_type 和预估的镜头数/角色数，计算 ImageGen / VideoGen 消耗：

```
估算公式：
  角色关键帧 ImageGen = 角色数 × 6 张 × 7.5 credits/张
  镜头首帧 ImageGen = 镜头数 × 7.5 credits/张
  视频片段 VideoGen = 镜头数 × 75 credits/5s
  总估算 = ImageGen + VideoGen
```

> 镜头数预估：目标时长 ÷ 5s（每个镜头默认 5 秒）。如目标 60s → 12 镜头。

### S0.3 用户确认（强制，不可跳过）

向用户展示预估消耗并请求确认：

```
[信用消耗预估]
- 角色关键帧：{角色数} 角色 × 6 张 = {N1} 张 ImageGen → ~{C1} credits
- 镜头首帧：{镜头数} 张 ImageGen 图生图 → ~{C2} credits
- 视频片段：{镜头数} 段 VideoGen 图生视频 → ~{C3} credits
- 预估总消耗：~{C_total} credits

请确认是否继续执行？（可输入"调整"来修改镜头数/角色数/分辨率等参数以降低消耗）
```

用户确认后 → 创建 pipeline-state.yaml → 进入 S1（或 entry_type 对应的首个 Stage）。

> 📖 信用消耗详细估算表与降级策略见 [`references/credit-estimation.md`](references/credit-estimation.md)

---

## 数据流衔接（预设表之外、必须由编排层填的字段）

### S1→S2：故事 → 剧本
- story-agent 输出 `story_path` + `characters[]` → 透传给 script-agent 作为 `story_path` + `characters`

### S2→S3：剧本 → 分镜
- script-agent 输出 `script_path` + `scenes[]` → 透传给 storyboard-agent

### S3→S4：分镜 → 角色卡
- storyboard-agent 输出 `storyboard_path` + `music_plan_path` → 透传给 character-agent
- character-agent 同时需要 `script_path`（获取角色描述）和 `storyboard_path`（获取镜头中的角色出场信息）

### S4→S5：角色卡 → 视频（**角色一致性核心衔接**）
- character-agent 输出 `characters_dir` + `character_cards[]`
- video-gen-agent 从每个 `character_card.json` 读取：
  - `reference_image`：角色基准正面照（用于 ImageGen 图生图首帧）
  - `seed_prompt`：角色描述前缀（拼接到 image_prompt）
  - `keyframe_paths`：表情关键帧（按镜头情绪选择）
- **编排层必须传递 `characters_dir` 和 `character_cards` 完整列表给 video-gen-agent**

### S5→S6：视频片段 → 粗剪
- video-gen-agent 输出 `clips_dir` + `manifest_path`
- editing-agent 需要 `storyboard_path`（获取镜头顺序和转场信息）

### S6→S7：粗剪 → 精剪（**人工暂停点**）
- editing-agent 输出 `rough_cut_path` + `edit_decision_list`
- **mandatory checkpoint**：暂停，present_files 展示 rough_cut.mp4，等待人工反馈
- 用户反馈解析为结构化 `feedback[]`，支持回溯 S5（replace 类型）

### S7→S8：精剪 → 成片
- editing-agent 输出 `fine_cut_path`
- finalize-agent 需要 `music_plan_path` + `script_path`（对白）+ `storyboard_path`（时间戳）

---

## 人工介入点（S6→S7 mandatory checkpoint）

### 暂停机制

S6 粗剪完成后：

```
[Stage 6 粗剪完成] 产物：{rough_cut.mp4 路径}（时长 {N}s，{shot_count} 镜头）
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

此时 `pipeline-state.yaml` 的 `stage_6.status = completed`，`current_stage = 7`，但**暂停执行**等待人工反馈。

### 反馈类型

| type | 说明 | 是否回溯 S5 |
|------|------|------------|
| `trim` | 裁剪镜头时长 | 否（ffmpeg 处理） |
| `replace` | 替换镜头，需重新生成 | **是**（回溯 S5 重新生成该镜头） |
| `reorder` | 调整镜头顺序 | 否（ffmpeg 重新拼接） |
| `transition` | 修改转场效果 | 否（ffmpeg 重新拼接） |
| `speed` | 调整播放速度 | 否（ffmpeg setpts） |

### 回溯 S5 安全保障

- 回溯时只重新生成指定 shot，不影响其他 shot
- 重新生成的片段写入 `stage5/clips/shot_{N}_v2.mp4`（保留原版本）
- `pipeline-state.yaml` 的 `stage_5.regenerated_shots` 记录所有回溯
- 精剪迭代无上限，用户满意后才进入 S8

---

## 编排原则（铁律，共 7 条）

> ⚠️ 本节优先级高于任何 Stage 内部决策。违反 = 流水线异常。

1. **弹性入口** — 每次请求先在 S0 识别意图组合链路，不默认走完整链路；S0 不可跳过。

2. **信用预算前置确认** — S0 完成后给出预估信用消耗，用户确认后才进入首个执行 Stage。禁止跳过确认直接消耗 credits。

3. **链路不可中断** — 链路一旦组合，必须**顺序执行到 S8 结束**（S6→S7 间的人工暂停除外）：不脱轨、不跳过、不在中途交付、不调用 Pipeline 外的 Skill。

4. **真委派** — 每个 Stage 通过**角色切换**执行：加载 `agents/<name>.md` 并严格照其定义执行。**禁止"读了 agent.md 然后自己顺手做"**。

   ```
   方式（角色切换 — 默认）：
     → 声明："[角色切换] 现在以 {agent-name} 身份执行 Stage {N}"
     → 读取 agents/<name>.md，严格按其定义的流程执行
     → 完成后声明："[角色切换结束] 回到 Orchestrator 身份"
     → 回到 Orchestrator 继续流转
   ```

5. **角色一致性不可破坏** — S5 生成视频时**必须**使用 S4 产出的角色卡 `reference_image` 作为 ImageGen 图生图输入。**禁止纯文生视频跳过角色锁定**。详见 [`../../references/character-consistency-guide.md`](../../references/character-consistency-guide.md)

6. **中间产物 ≠ 最终交付，且不主动展示** — S1-S7 的产物是中间态，**编排层与各子 Agent 不得对其调用 `present_files`**（S6 粗剪除外，需展示供人工审看），仅在检查点里给出路径与简短摘要。只有 S8 的 `final_drama.mp4` 会**强制 `present_files` 展示**，作为**本轮请求的唯一最终交付**。

7. **溯源必写** — 每个 Stage 完成后**先更新 `pipeline-state.yaml` 再声明检查点**；日志不记用户原文，仅记意图长度与决策。

检查点声明格式（声明后**立即**执行下一 Stage，不等用户确认；S6→S7 除外）：
```
[Stage N 完成] 产物：{路径/摘要}。下一步：进入 Stage {N+1}。
```

### 禁止的行为

```
❌ 读了 agents/character-agent.md 后，不声明角色切换，直接"顺手"生成角色图
❌ 跳过读取 Agent 定义，凭记忆/猜测执行 Stage 逻辑
❌ S5 纯文生视频，不使用 S4 角色卡 reference_image
❌ S0 跳过信用预算确认直接进入 S1
❌ 在 S6→S7 人工暂停点自动推进到 S7
❌ 对 S1-S5 中间产物（.md / .json / .png）主动调用 present_files（S6 粗剪除外）
❌ 拿到 final_drama.mp4 后没有立即 present_files 展示成片
```

---

## Pipeline State & Log（溯源记录）

> `pipeline-state.yaml` 是本次 Pipeline 的**溯源记录（audit trail）**，不是执行锁。

- **唯一进度真相源**：文件不存在 = 未启动；`current_stage` = 当前进度。
- **写入时机**：S0 创建 → 每个 Stage 完成后更新对应块并推进 `current_stage` → 结束写 `consistency_check`。
- **YAML 先于检查点**：更新 YAML 的动作必须在声明 `[Stage N 完成]` 之前完成。

### 输出目录（速查）

```
output/<request_id>/
├── pipeline-state.yaml
├── stage1/story.md
├── stage2/script.md
├── stage3/
│   ├── storyboard.json
│   └── music_plan.json
├── stage4/characters/
│   ├── {角色A}/
│   │   ├── character_card.json
│   │   ├── front.png / side.png
│   │   └── expr_{neutral,happy,sad,angry}.png
│   └── {角色B}/ ...
├── stage5/
│   ├── clips/
│   │   ├── shot_{N}.mp4
│   │   ├── keyframes/keyframe_shot_{N}.png
│   │   └── manifest.json
├── stage6/
│   ├── rough_cut.mp4
│   └── edl.json
├── stage7/
│   ├── fine_cut.mp4
│   ├── edl_v2.json
│   └── feedback_log.md
├── stage8/
│   ├── final_drama.mp4
│   ├── final_drama.srt
│   ├── audio/
│   │   ├── voiceover/
│   │   └── music/
│   └── working/
├── working/
└── trace/pipeline.log
```

> 📖 完整 Schema、写入协议、命名规则见 [`references/pipeline-state-protocol.md`](references/pipeline-state-protocol.md)
> 📖 结构化日志字段定义见 [`references/log-schema.md`](references/log-schema.md)
