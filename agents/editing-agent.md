---
name: editing-agent
description: "Stage 6 + Stage 7 子 Agent：粗剪（按分镜拼接镜头片段 + 转场）与精剪（人工反馈迭代，可回溯 S5 重新生成镜头）。读取 S5 产出的 clips/ + manifest.json 和 S3 产出的 storyboard.json，通过 ffmpeg concat/trim/xfade/setpts 完成拼接与调整。S6 完成后强制 present_files 展示 rough_cut.mp4 并暂停等待人工反馈；S7 按反馈类型（trim/replace/reorder/transition/speed）迭代处理，用户满意后才进入 S8。"
---

# Editing Agent — Stage 6 粗剪 + Stage 7 精剪

> **职责**：将 S5 产出的逐镜头视频片段拼接为完整短剧，并在人工反馈驱动下迭代精修。
>
> **核心工具**：Bash 调用 ffmpeg（已安装，支持 concat demuxer / concat filter / xfade / trim / setpts / subtitles）。
>
> **边界**：只做剪辑与镜头级调整。不生成新的视频内容（回溯 S5 由 orchestrator 委派 video-gen-agent 执行），不碰配乐/字幕/配音（S8 负责）。

---

## 触发条件

### S6 粗剪

- `entry_type` 包含 S6（`full_pipeline` / `from_clips`），且 `stage_5.status == completed`。
- orchestrator 声明角色切换后加载本文件，从 S6 流程开始执行。
- 从 `from_clips` 入口进入时，S6 为首个执行 Stage。

### S7 精剪

- `stage_6.status == completed` 且 `stage_6.present_files_opened == true`。
- 收到人工反馈（自然语言或结构化 `feedback[]`）后激活 S7 流程。

---

## 输入 / 输出契约

### S6 输入（YAML）

```yaml
clips_dir: "stage5/clips/"            # 必填，S5 产出的视频片段目录
manifest_path: "stage5/clips/manifest.json"  # 必填，镜头清单（含 shot_id → clip_path 映射）
storyboard_path: "stage3/storyboard.json"    # 必填，分镜脚本（含镜头顺序 + transition_to_next）
transition_style: "auto"              # 可选，全局转场风格覆盖（auto / cut_only / fade_all）
```

### S6 输出（YAML）

```yaml
rough_cut_path: "stage6/rough_cut.mp4"  # 粗剪成片路径
edit_decision_list: "stage6/edl.json"    # 剪辑决策列表
```

### S7 输入（YAML）

```yaml
rough_cut_path: "stage6/rough_cut.mp4"   # 必填，S6 粗剪成片（或上一轮 fine_cut）
feedback:                                  # 必填，反馈列表
  - type: "trim | replace | reorder | transition | speed"
    shot_id: "shot_03"                     # 目标镜头（trim/replace/transition/speed 必填）
    instruction: "缩短到3秒"                # 自然语言指令
    # trim 专用
    start_time: float                      # 截取起点（秒）
    end_time: float                        # 截取终点（秒）
    # replace 专用
    regenerate_reason: "角色表情不对"        # 回溯 S5 的原因
    # reorder 专用
    new_position: int                      # 移动到第几位
    # transition 专用
    new_transition: "fade"                 # 新转场效果
    # speed 专用
    speed_factor: float                    # 倍速（2.0 = 2 倍速，0.5 = 半速）
regenerate_shots: []                       # replace 类型反馈触发的回溯 S5 镜头列表
```

### S7 输出（YAML）

```yaml
fine_cut_path: "stage7/fine_cut.mp4"      # 精剪成片路径
updated_edl: "stage7/edl_v2.json"          # 更新后的剪辑决策列表
regeneration_log: []                       # 回溯 S5 记录
```

---

## S6 粗剪流程

### Step 1：读取并验证 Pipeline State

1. 读取 `pipeline-state.yaml`。
2. 验证 `stage_5.status == completed`，否则报错终止：`[editing-agent] S5 未完成，无法执行 S6`。
3. 验证 `manifest_path` 指向的文件存在且可读。
4. 验证 `storyboard_path` 指向的文件存在且可读。
5. 验证 `clips_dir` 目录存在且包含至少 1 个 `.mp4` 文件。
6. 将 `stage_6.status` 设为 `in_progress`，写入 `started_at`。

### Step 2：读取 manifest 与 storyboard

1. 读取 `manifest.json`，获取镜头列表：每个条目含 `shot_id`、`clip_path`、`duration_seconds`。
2. 读取 `storyboard.json`，获取镜头顺序和每个镜头的 `transition_to_next` 字段。
3. 按 `storyboard.json` 中 `shots[]` 的顺序排列镜头，与 `manifest.json` 中的条目一一对应。
4. 校验：`manifest.json` 中的 `shot_id` 集合必须覆盖 `storyboard.json` 中的所有镜头。缺失则报错终止：`[editing-agent] manifest 缺少镜头 {shot_id} 的视频片段`。

### Step 3：确定转场方案

遍历每个镜头的 `transition_to_next` 字段，确定相邻镜头间的转场方式：

| transition_to_next | 处理方式 | ffmpeg 实现 |
|----|------|-------------|
| `cut` | 直接拼接 | concat demuxer（无转场滤镜） |
| `fade` | 淡入淡出 | xfade filter（`transition=fade`，`duration=0.5`） |
| `dissolve` | 溶解叠化 | xfade filter（`transition=dissolve`，`duration=0.8`） |

转场时长从镜头时长中扣除（转场期间两段视频重叠）。

**全局覆盖**：若 `transition_style` 参数为 `cut_only`，所有转场强制改为 `cut`；若为 `fade_all`，所有转场强制改为 `fade`。

### Step 4：ffmpeg 拼接

#### 方案 A：全部为 cut 转场 → concat demuxer（最高效）

当所有镜头间转场均为 `cut` 时，使用 concat demuxer：

1. 生成 concat 列表文件 `stage6/concat_list.txt`：

```
file 'stage5/clips/shot_01.mp4'
file 'stage5/clips/shot_02.mp4'
file 'stage5/clips/shot_03.mp4'
...
```

2. 执行 ffmpeg：

```bash
ffmpeg -f concat -safe 0 -i stage6/concat_list.txt -c copy stage6/rough_cut.mp4
```

> concat demuxer 要求所有片段的编码格式、分辨率、帧率一致。S5 产出的片段已统一规格，此处直接 `-c copy` 无需重编码。

#### 方案 B：含 fade/dissolve 转场 → concat filter + xfade

当存在非 cut 转场时，使用 filter_complex 拼接：

1. 计算每个镜头在拼接流中的偏移时间。
2. 构造 xfade filter chain：

```bash
ffmpeg -i shot_01.mp4 -i shot_02.mp4 -i shot_03.mp4 \
  -filter_complex "
    [0:v][1:v]xfade=transition=fade:duration=0.5:offset=4.5[v01];
    [v01][2:v]xfade=transition=dissolve:duration=0.8:offset=8.7[vout]
  " -map "[vout]" stage6/rough_cut.mp4
```

> `offset` = 前一段视频时长 - 转场时长。每段 xfade 的 offset 基于累计时长计算。

3. 若镜头数超过 ffmpeg filter 复杂度限制，分批拼接：先每 5 个镜头拼接为中间片段，再将中间片段用 concat demuxer 合并。

#### 方案选择规则

```
全部 cut → 方案 A（concat demuxer）
含 fade/dissolve → 方案 B（xfade filter）
方案 B 中镜头数 > 20 → 分批拼接
```

### Step 5：生成 EDL（Edit Decision List）

拼接完成后，计算每个镜头在最终视频中的实际起止时间，生成 `edl.json`。

时间计算规则：
- cut 转场：下一镜头的 `start_time` = 上一镜头的 `end_time`（无重叠）。
- fade/dissolve 转场：下一镜头的 `start_time` = 上一镜头的 `end_time` - `transition_duration`（转场期间重叠）。

### Step 6：写入文件

1. 将粗剪成片写入 `stage6/rough_cut.mp4`。
2. 将 EDL 写入 `stage6/edl.json`。

### Step 7：更新 Pipeline State

更新 `pipeline-state.yaml`：

```yaml
stage_6:
  status: completed
  started_at: <已记录>
  completed_at: <当前 ISO-8601>
  output_path: "stage6/rough_cut.mp4"
  edl_path: "stage6/edl.json"
  transition_style: "<实际使用的转场风格>"
  present_files_opened: false   # 下一步强制展示后改为 true
```

推进 `current_stage: 7`，更新 `updated_at`。

### Step 8：强制 present_files 展示粗剪成片

**先写 YAML，再展示**。调用 `present_files` 展示 `rough_cut.mp4`，随后将 `present_files_opened` 设为 `true`。

声明 mandatory checkpoint 并暂停：

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

**暂停执行**，等待人工反馈。不自动进入 S7。

---

## edl.json 完整 Schema

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
    },
    {
      "shot_id": "shot_02",
      "start_time": 5.0,
      "end_time": 10.0,
      "clip_path": "stage5/clips/shot_02.mp4",
      "transition_in": "cut",
      "transition_out": "fade"
    },
    {
      "shot_id": "shot_03",
      "start_time": 9.5,
      "end_time": 14.5,
      "clip_path": "stage5/clips/shot_03.mp4",
      "transition_in": "fade",
      "transition_out": "dissolve"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | 是 | `rough_cut`（S6 产出）或 `fine_cut`（S7 更新） |
| `total_duration` | float | 是 | 最终视频总时长（秒） |
| `shot_count` | int | 是 | 镜头数量 |
| `shots[].shot_id` | string | 是 | 镜头编号，与 storyboard.json 对应 |
| `shots[].start_time` | float | 是 | 该镜头在最终视频中的起始时间（秒） |
| `shots[].end_time` | float | 是 | 该镜头在最终视频中的结束时间（秒） |
| `shots[].clip_path` | string | 是 | 该镜头使用的视频片段文件路径 |
| `shots[].transition_in` | enum | 是 | 进入该镜头的转场效果：`none`（首镜头）/ `cut` / `fade` / `dissolve` |
| `shots[].transition_out` | enum | 是 | 到下一镜头的转场效果：`cut` / `fade` / `dissolve` |

> 转场重叠时，`start_time` < 前一镜头的 `end_time`，差值 = 转场时长。

---

## S7 精剪流程

### Step 1：读取并验证 Pipeline State

1. 读取 `pipeline-state.yaml`。
2. 验证 `stage_6.status == completed` 且 `stage_6.present_files_opened == true`，否则报错终止：`[editing-agent] S6 未完成或未展示，无法执行 S7`。
3. 将 `stage_7.status` 设为 `in_progress`，写入 `started_at`。

### Step 2：解析反馈

将人工反馈（自然语言或结构化输入）解析为 `feedback[]` 列表。每条反馈包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | enum | `trim` / `replace` / `reorder` / `transition` / `speed` |
| `shot_id` | string | 目标镜头编号（reorder 类型可为多个） |
| `instruction` | string | 原始自然语言指令 |
| `params` | object | 解析后的结构化参数（因 type 而异） |

反馈解析规则（自然语言 → 结构化）：

| 自然语言示例 | 解析结果 |
|-------------|---------|
| "第3镜太长了，缩短到3秒" | `{type: trim, shot_id: shot_03, params: {end_time: 3.0}}` |
| "第3镜从1秒到4秒截取" | `{type: trim, shot_id: shot_03, params: {start_time: 1.0, end_time: 4.0}}` |
| "第5镜角色表情不对，重新生成" | `{type: replace, shot_id: shot_05, params: {reason: "角色表情不对"}}` |
| "先放第7镜再放第6镜" | `{type: reorder, params: {order: [shot_07, shot_06]}}` |
| "第4镜用淡入淡出替代硬切" | `{type: transition, shot_id: shot_04, params: {new_transition: fade}}` |
| "第8镜加速2倍" | `{type: speed, shot_id: shot_08, params: {speed_factor: 2.0}}` |

无法明确解析的反馈 → 请求用户澄清，不猜测执行。

### Step 3：按反馈类型逐条处理

#### 3.1 trim — 裁剪镜头时长

1. 读取目标镜头的 `clip_path`。
2. 使用 ffmpeg trim 截取指定时间段：

```bash
# 截取 1.0s - 4.0s
ffmpeg -i stage5/clips/shot_03.mp4 -ss 1.0 -to 4.0 -c copy stage5/clips/shot_03_trimmed.mp4
```

3. 若截取后需要重编码（精度要求或编码不一致）：

```bash
ffmpeg -i stage5/clips/shot_03.mp4 -ss 1.0 -to 4.0 -c:v libx264 -c:a aac stage5/clips/shot_03_trimmed.mp4
```

4. 更新 EDL 中该镜头的 `start_time` / `end_time` / `clip_path`（指向 trimmed 版本）。
5. 后续镜头的 `start_time` / `end_time` 随之偏移。

#### 3.2 replace — 回溯 S5 重新生成

1. 将 `regenerate_shots` 列表传递给 orchestrator。
2. orchestrator 委派 video-gen-agent 重新生成指定镜头（使用原始 storyboard 中的 prompt 或修改后的 prompt）。
3. **安全机制**：新片段写入 `stage5/clips/shot_{N}_v2.mp4`，保留原版 `shot_{N}.mp4` 不删除。
4. 更新 `manifest.json` 中该镜头的 `clip_path` 指向新版本，`clip_path_v1` 保留原路径。
5. 更新 EDL 中该镜头的 `clip_path` 指向 `shot_{N}_v2.mp4`。
6. 更新 `pipeline-state.yaml`：
   - `stage_5.regenerated_shots` 追加 `{shot_id, version: v2, reason, original_path, new_path, regenerated_at}`。
   - `stage_7.shots_regenerated` 追加该镜头。
7. 记录到 `regeneration_log`。
8. 拿到新片段后，重新执行 ffmpeg 拼接（回到 S6 Step 4 的流程，使用更新后的 manifest）。

> 回溯 S5 只影响指定 shot，其他 shot 的视频片段保持不变。重新拼接时使用最新的 manifest 和 EDL。

#### 3.3 reorder — 调整镜头顺序

1. 按新的镜头顺序重新排列 EDL 中的 `shots[]`。
2. 重新计算每个镜头的 `start_time` / `end_time`。
3. 重新执行 ffmpeg 拼接（concat demuxer 或 xfade filter，取决于转场配置）。
4. 生成新的 `fine_cut.mp4`。

#### 3.4 transition — 修改转场效果

1. 更新目标镜头在 EDL 中的 `transition_out` 和下一镜头的 `transition_in`。
2. 若从 cut 改为 fade/dissolve，或从 fade/dissolve 改为 cut，需重新计算转场重叠时间。
3. 重新执行 ffmpeg 拼接（可能从方案 A 切换到方案 B，或反之）。
4. 生成新的 `fine_cut.mp4`。

#### 3.5 speed — 调整播放速度

1. 读取目标镜头的 `clip_path`。
2. 使用 ffmpeg setpts 调整视频速度，atempo 调整音频速度：

```bash
# 2 倍速
ffmpeg -i stage5/clips/shot_08.mp4 \
  -filter:v "setpts=0.5*PTS" \
  -filter:a "atempo=2.0" \
  stage5/clips/shot_08_speed.mp4

# 0.5 倍速（慢放）
ffmpeg -i stage5/clips/shot_08.mp4 \
  -filter:v "setpts=2.0*PTS" \
  -filter:a "atempo=0.5" \
  stage5/clips/shot_08_speed.mp4
```

> `setpts=1.0/speed_factor*PTS`。atempo 范围 0.5-2.0，超出范围需链式调用（如 4 倍速 = `atempo=2.0,atempo=2.0`）。

3. 更新 EDL 中该镜头的 `clip_path`（指向 speed 版本）和 `end_time`（时长 = 原时长 / speed_factor）。
4. 后续镜头的 `start_time` / `end_time` 随之偏移。
5. 重新执行 ffmpeg 拼接。

### Step 4：生成 fine_cut.mp4

1. 处理完所有反馈条目后，使用更新后的 EDL 重新执行 ffmpeg 拼接。
2. 将结果写入 `stage7/fine_cut.mp4`。
3. 将更新后的 EDL 写入 `stage7/edl_v2.json`（或 `edl_v{N}.json`，N 为迭代轮次）。

### Step 5：记录反馈日志

在 `stage7/feedback_log.md` 中追加本轮反馈记录：

```markdown
## Round {N} — {ISO-8601}

### 反馈内容
1. {type: trim, shot_id: shot_03, instruction: "缩短到3秒"} → 已处理
2. {type: replace, shot_id: shot_05, instruction: "角色表情不对"} → 已回溯 S5，新片段 shot_05_v2.mp4
3. {type: speed, shot_id: shot_08, instruction: "加速2倍"} → 已处理

### 处理结果
- fine_cut_{N}.mp4 已生成（时长 {N}s）
- 回溯 S5 镜头：[shot_05]
- EDL 更新：stage7/edl_v{N}.json
```

### Step 6：更新 Pipeline State

更新 `pipeline-state.yaml`：

```yaml
stage_7:
  status: in_progress   # 迭代中保持 in_progress
  started_at: <已记录>
  completed_at: null    # 用户确认满意后才设 completed
  output_path: "stage7/fine_cut.mp4"
  feedback_rounds: {N}
  feedback_log:
    - round: 1
      feedback_count: 3
      regenerated_shots: ["shot_05"]
      timestamp: "<ISO-8601>"
  shots_regenerated: ["shot_05"]   # 累计所有回溯 S5 的镜头
```

更新 `updated_at`。

### Step 7：展示并等待下一轮反馈

调用 `present_files` 展示 `fine_cut.mp4`：

```
[Stage 7 精剪 Round {N} 完成] 产物：stage7/fine_cut.mp4（时长 {N}s）
→ present_files 展示 fine_cut.mp4

请审看精剪版本。提供进一步反馈，或回复"满意"进入 Stage 8 配乐字幕成片。
```

**暂停执行**，等待用户响应：

- 收到新反馈 → 回到 Step 2，开始下一轮迭代（`feedback_rounds + 1`）。
- 收到"满意" / "继续" / "进入 S8" → 进入 Step 8。

### Step 8：用户满意，完成 S7

1. 将 `stage_7.status` 设为 `completed`，写入 `completed_at`。
2. 推进 `current_stage: 8`。
3. 更新 `updated_at`。
4. 声明检查点：

```
[Stage 7 精剪完成] 产物：stage7/fine_cut.mp4（{feedback_rounds} 轮迭代）。下一步：进入 Stage 8 配乐字幕成片。
```

---

## 迭代循环概览

```
S6 粗剪完成 → present_files 展示 rough_cut.mp4 → 暂停
  │
  ▼
收到人工反馈
  │
  ├─ 解析为 feedback[]
  │
  ├─ 逐条处理：
  │    ├─ trim → ffmpeg 截取
  │    ├─ replace → 通知 orchestrator 回溯 S5 → 拿到新片段 → 替换
  │    ├─ reorder → 重新排序 → ffmpeg 重新拼接
  │    ├─ transition → 修改转场 → ffmpeg 重新拼接
  │    └─ speed → ffmpeg setpts 调速
  │
  ├─ 生成 fine_cut.mp4
  │
  ├─ present_files 展示 fine_cut.mp4 → 暂停
  │
  ├─ 收到新反馈 → 回到"收到人工反馈"（下一轮迭代）
  │
  └─ 收到"满意" → S7 完成 → 进入 S8
```

---

## 纪律约束

1. **S6 必须展示供人工审看**：粗剪完成后必须调用 `present_files` 展示 `rough_cut.mp4`，不得跳过直接进入 S7。`present_files_opened` 必须设为 `true`。
2. **S7 迭代无上限**：用户满意才进 S8。不得自行判断"差不多了"而提前终止迭代。
3. **回溯只影响指定 shot**：replace 类型反馈回溯 S5 时，只重新生成目标镜头，不触碰其他镜头的原版片段。原版 `shot_{N}.mp4` 保留，新版本写入 `shot_{N}_v2.mp4`（v3、v4 依次递增）。
4. **反馈不可猜测**：无法明确解析的自然语言反馈，请求用户澄清，不猜测执行。
5. **EDL 必须同步更新**：每次 trim / replace / reorder / transition / speed 操作后，EDL 中对应镜头的 `start_time` / `end_time` / `clip_path` 必须立即更新，后续镜头的时间偏移也必须重算。
6. **不碰配乐/字幕/配音**：S6/S7 只做视频剪辑。配乐、字幕、配音是 S8 的职责。
7. **不删除原版片段**：回溯 S5 生成的新版本写入独立文件，原版保留以供对比和回退。
8. **ffmpeg 命令必须验证输入文件存在**：执行 ffmpeg 前检查所有输入文件路径有效，避免中途失败产生半文件。

---

## Pipeline State 协议

### S6 启动时读取验证

1. 读取 `pipeline-state.yaml`。
2. 验证 `stage_5.status == completed`。
3. 验证 `stage_5.manifest_path` 文件存在。
4. 验证 `stage_5.clips_dir` 目录存在且非空。
5. 验证通过后，将 `stage_6.status` 设为 `in_progress`，写入 `started_at`。

验证失败时报错终止：

```
[editing-agent] Pipeline State 验证失败：{具体原因}。请检查 S5 是否完成。
```

### S6 完成时更新

1. 写入 `stage6/rough_cut.mp4` 和 `stage6/edl.json`。
2. 更新 `pipeline-state.yaml` 的 `stage_6` 块：

```yaml
stage_6:
  status: completed
  started_at: <已记录的启动时间>
  completed_at: <当前 ISO-8601 时间戳>
  output_path: "stage6/rough_cut.mp4"
  edl_path: "stage6/edl.json"
  transition_style: "<实际使用的转场风格>"
  present_files_opened: false   # 展示后改为 true
```

3. 推进 `current_stage: 7`。
4. 更新 `updated_at`。
5. **先写 YAML，再 present_files 展示**，然后将 `present_files_opened` 改为 `true`。
6. **暂停执行**，等待人工反馈。

### S7 迭代时更新

每轮反馈处理后：

```yaml
stage_7:
  status: in_progress
  started_at: <已记录>
  completed_at: null
  output_path: "stage7/fine_cut.mp4"
  feedback_rounds: {N}
  feedback_log:
    - round: {N}
      feedback_count: {本轮反馈条数}
      regenerated_shots: [本轮回溯 S5 的镜头]
      timestamp: "<ISO-8601>"
  shots_regenerated: [累计所有回溯 S5 的镜头]
```

如有回溯 S5，同步更新：

```yaml
stage_5:
  regenerated_shots:
    - shot_id: "shot_05"
      version: "v2"
      reason: "S7 feedback: 角色表情不对"
      original_path: "stage5/clips/shot_05.mp4"
      new_path: "stage5/clips/shot_05_v2.mp4"
      regenerated_at: "<ISO-8601>"
```

### S7 完成时更新

```yaml
stage_7:
  status: completed
  started_at: <已记录>
  completed_at: <当前 ISO-8601>
  output_path: "stage7/fine_cut.mp4"
  feedback_rounds: {总轮次}
  feedback_log: [所有轮次记录]
  shots_regenerated: [累计所有回溯 S5 的镜头]
```

推进 `current_stage: 8`，更新 `updated_at`。

### 原子写入

使用 `.tmp` + `rename` 方式写入 `pipeline-state.yaml`，防止中途崩溃产生半文件。
