# Pipeline State Protocol — 短剧制作溯源记录参考

> `pipeline-state.yaml` 是本次 Pipeline 的**溯源记录（audit trail）**，不是执行锁。
> 每个 Stage 完成后追加写入自己的产物与决策，便于事后回溯与问题定位。

---

## Schema（v1）

```yaml
schema_version: 1
request_id: <uuid-v4>
created_at: <ISO-8601>
updated_at: <ISO-8601>

entry_type: full_pipeline | from_script | from_storyboard | from_clips | refinement
# full_pipeline: S1->S2->S3->S4->S5->S6->S7->S8 全链路
# from_script: 已有剧本，S3->S4->S5->S6->S7->S8
# from_storyboard: 已有分镜，S4->S5->S6->S7->S8
# from_clips: 已有视频片段，S6->S7->S8
# refinement: S7->S8 精修+成片

stage_chain: [1, 2, 3, 4, 5, 6, 7, 8]  # 由 entry_type 映射

current_stage: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | completed

# 全局参数
global_config:
  theme: string                    # 创作主题
  genre: string                    # 类型（romance/suspense/comedy/general）
  target_duration: int             # 目标总时长（秒）
  aspect_ratio: "9:16"             # 画幅（竖屏短剧默认 9:16）
  resolution: "720P | 1080P"       # 分辨率
  visual_style: "cinematic"        # 视觉风格
  episodes: int                    # 集数（默认 1）

# 角色一致性核心：角色卡索引
character_cards:
  - name: string
    card_path: "stage4/characters/{name}/character_card.json"
    reference_image: "stage4/characters/{name}/front.png"

stages:
  stage_0:
    status: pending | completed
    completed_at: null | <ISO-8601>
    decision: <entry_type>
    credit_budget_estimate: int    # 预估总信用消耗
    user_confirmed: false           # 用户是否确认信用预算

  stage_1:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    output_path: "stage1/story.md"
    genre: null | string
    expert_used: null | string
    characters: []                  # 角色列表 [{name, role, brief}]

  stage_2:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    output_path: "stage2/script.md"
    scene_count: null | int
    dialogue_lines: null | int

  stage_3:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    storyboard_path: "stage3/storyboard.json"
    music_plan_path: "stage3/music_plan.json"
    shot_count: null | int
    total_duration: null | int

  stage_4:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    characters_dir: "stage4/characters/"
    character_cards: []             # 角色卡路径列表
    images_generated: null | int
    credits_used: null | int        # ImageGen 消耗

  stage_5:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    clips_dir: "stage5/clips/"
    manifest_path: "stage5/clips/manifest.json"
    clips_generated: null | int
    clips_failed: null | int
    credits_used: null | int         # VideoGen + ImageGen 消耗
    regenerated_shots: []            # 精剪阶段回溯重新生成的镜头

  stage_6:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    output_path: "stage6/rough_cut.mp4"
    edl_path: "stage6/edl.json"
    transition_style: null | string
    present_files_opened: false      # 粗剪是否已展示供人工审看

  stage_7:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    output_path: "stage7/fine_cut.mp4"
    feedback_rounds: null | int      # 迭代轮次
    feedback_log: []                 # 每轮反馈摘要
    shots_regenerated: []            # 回溯 S5 重新生成的镜头列表

  stage_8:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    output_path: "stage8/final_drama.mp4"
    subtitle_path: "stage8/final_drama.srt"
    music_source: null | "suno" | "library" | "user_provided"
    tts_engine: null | "sag" | "whisper" | "none"
    present_files_opened: false      # 是否已调用 present_files 展示成片

consistency_check:
  output_files_exist: null | pass | fail
  stage_chain_complete: null | pass | fail
  character_consistency_verified: null | pass | fail
  last_checked_at: null | <ISO-8601>
  errors: []

# 信用消耗追踪
credit_tracking:
  estimated_total: null | int
  actual_total: null | int
  breakdown:
    image_gen:
      calls: null | int
      credits: null | int
    video_gen:
      calls: null | int
      credits: null | int
    tts:
      characters: null | int
      credits: null | int
```

---

## 写入时机（三个节点）

| 节点 | 动作 |
|------|------|
| **S0 判定入口后** | 创建 `output/<request_id>/` 目录结构；写入 `schema_version / request_id / created_at / entry_type / stage_chain / current_stage / global_config`；各 stage 设 `pending`，不在链中的设 `skipped` |
| **每个 Stage 完成后** | 更新该 stage 块（`status: completed` + `completed_at` + `output_path` + 其他字段）；推进 `current_stage`；更新 `updated_at`；**先写 YAML 再声明检查点** |
| **S6 完成后** | 写入 `stage_6.status=completed` / `present_files_opened=true`，`current_stage=7`，**暂停执行**等待人工反馈 |
| **S7 反馈迭代** | 每轮反馈处理后更新 `feedback_rounds` / `feedback_log`；如有回溯 S5，同步更新 `stage_5.regenerated_shots` 和 `stage_7.shots_regenerated` |
| **S8 完成后** | 写入 `stage_8.status=completed` / `present_files_opened=true`，`current_stage=completed`；写 `consistency_check`；写 `credit_tracking.actual_total` |
| **Pipeline 结束** | 写 `consistency_check`（见下） |

### consistency_check 字段

| 字段 | 检查内容 |
|------|---------|
| `output_files_exist` | 检查 stage_chain 中每个 Stage 的 output_path 文件是否实际存在 |
| `stage_chain_complete` | 检查 stage_chain 中所有 stage 的 status 是否为 completed |
| `character_consistency_verified` | 检查 S5 的 manifest.json 中每个 clip 是否使用了 character_card 的 reference_image |
| `errors` | 检查中发现的问题列表 |

> consistency_check 如实留痕，不阻塞交付。

---

## 原子写入协议

```bash
# 先写 .tmp 再 rename，防止中途崩溃产生半文件
cat > pipeline-state.yaml.tmp << 'EOF'
{完整 YAML 内容}
EOF
mv pipeline-state.yaml.tmp pipeline-state.yaml
```
