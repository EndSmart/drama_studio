---
name: story-writer
description: "故事文本生成。根据创作主题生成完整短剧故事（标题/梗概/角色列表/情节大纲/结局），被 story-agent 加载后指导 Stage 1 的故事生成流程。支持路由到 romance / suspense / comedy / general 四类领域 Expert，产出结构化 story YAML 供 script-agent 消费。"
---

# Story Writer — 故事文本生成

> 被 `story-agent` 加载，指导 Stage 1 故事生成。详细执行逻辑见 `../../agents/story-agent.md`。

---

## 故事结构规范

生成的短剧故事 YAML 必须包含以下完整结构：

| 结构元素 | 要求 | 说明 |
|----------|------|------|
| 标题 (title) | 10 字以内，吸引人 | 如「雨夜的秘密」「总裁的契约新娘」 |
| 故事梗概 (plot_summary) | 500-1000 字 | 涵盖核心冲突、人物关系和主要情节走向 |
| 角色列表 (characters) | 主要角色 ≤ 8 个 | 每角色含 name / role / gender / age / appearance / personality / costume |
| 情节大纲 (plot_outline) | 起承转合 4 个阶段 | 每阶段标注覆盖的集数范围 |
| 结局类型 (ending_type) | HE / BE / OE | 必须明确 |
| 整体基调 (tone) | 如「虐恋」「轻松搞笑」「紧张悬疑」 | 从主题推断 |

---

## Expert 路由表

Story Writer 根据 `theme` 或 `genre_hint` 中的关键词路由到领域 Expert。Expert 定义位于 `../../experts/` 目录。

| Expert ID | 关键词 | 文件路径 |
|-----------|--------|----------|
| `romance` | 爱情、恋爱、甜宠、虐恋、霸总、先婚后爱、校园恋、姐弟恋、总裁、初恋 | `../../experts/romance-expert/` |
| `suspense` | 悬疑、推理、破案、刑侦、反转、烧脑、密室、谋杀、失踪、谜团 | `../../experts/suspense-expert/` |
| `comedy` | 搞笑、喜剧、穿越、沙雕、反转搞笑、无厘头、整蛊、沙雕剧 | `../../experts/comedy-expert/` |
| `general` | 无匹配时的默认兜底 | `../../experts/general-drama-expert/` |

**路由决策流程**：
1. `genre_hint` 非空 → 用 `genre_hint` 精确匹配 `expert_id`
2. `genre_hint` 为空 → 用 `theme` 文本关键词匹配
3. 命中 → 路由到对应 Expert；未命中 → 降级到 `general` Expert
4. 降级时在产物中记录 `degraded_from` 和 `degraded_reason`

---

## 故事输出格式模板

```yaml
story_output:
  title: "故事标题"
  genre: "流派"
  plot_summary: "500-1000 字的故事梗概，描述核心冲突、人物关系和情节走向"
  characters:
    - name: "角色名"
      role: "主角/配角/反派/路人"
      gender: "男/女"
      age: 25
      appearance: "外貌描述：发型、脸型、眼睛、肤色、体型"
      personality: "性格描述"
      costume: "服装风格描述"
  plot_outline:
    - phase: "起"
      description: "开端阶段情节描述"
      episodes: "1-3"
    - phase: "承"
      description: "发展阶段情节描述"
      episodes: "4-6"
    - phase: "转"
      description: "转折阶段情节描述"
      episodes: "7-9"
    - phase: "合"
      description: "结局阶段情节描述"
      episodes: "10"
  ending_type: "HE/BE/OE"
  tone: "整体基调描述"
```

---

## 质量检查清单

故事产出后，story-agent 必须验证以下项目：

- [ ] **标题质量**：标题是否 10 字以内且具有吸引力
- [ ] **梗概完整**：梗概是否在 500-1000 字，是否涵盖核心冲突和人物关系
- [ ] **角色描述完整**：每个角色是否包含 name / role / gender / age / appearance / personality / costume 全部字段
- [ ] **情节起承转合**：plot_outline 是否包含起、承、转、合四个阶段，每阶段是否有明确的 episodes 范围
- [ ] **结局明确**：ending_type 是否为 HE / BE / OE 之一
- [ ] **角色数量合理**：主要角色是否 ≤ 8 个
- [ ] **流派一致**：生成的故事风格是否与路由到的 Expert 流派规则一致

---

## 纪律约束

1. **只做故事生成**：不生成剧本格式、分镜或镜头语言
2. **产物为中间态**：story YAML 仅供 script-agent 消费，不直接面向最终用户
3. **渐进加载 Expert**：按需加载对应 Expert，不预加载全部
4. **降级必记录**：Expert 降级到 general 时必须记录原因
5. **幂等性**：若 `story_path` 已存在且有效，跳过生成直接返回
6. **不修改上游数据**：只读取 Pipeline State，不修改 story-agent 职责范围外的字段
