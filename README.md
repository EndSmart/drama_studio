# 🎬Gwsmart Drama Maker — 短剧制作 Skill

> 端到端自动化短剧制作流水线：从**创作主题 → 故事 → 剧本 → 分镜 → 角色关键帧 → 视频生成 → 粗剪 → 精剪 → 配乐字幕成片**全流程自动编排。

Drama Maker 是一个面向 CodeBuddy 平台的自定义 Skill，采用 **Orchestrator + 子 Agent** 架构，覆盖短剧制作的 9 个完整阶段。核心亮点是**角色一致性三层锁定机制**和**人工介入精剪迭代**，让 AI 也能稳定生成剧情连贯、角色统一、声画俱佳的竖屏短剧。

---

## ✨ 核心能力（9 个阶段）

| Stage | 能力 | 执行者 | 输出产物 |
|-------|------|--------|---------|
| S0 | 意图识别 + 信用预算 + Pipeline 初始化 | orchestrator | `pipeline-state.yaml` |
| S1 | 故事文本生成 | story-agent → 领域 Expert | `story.md` |
| S2 | 剧本生成 | script-agent | `script.md` |
| S3 | 分镜脚本 + 配乐基调 | storyboard-agent | `storyboard.json` + `music_plan.json` |
| S4 | 角色关键帧生成 | character-agent | `characters/` + `character_card.json` |
| S5 | 视频片段生成 | video-gen-agent | `clips/shot_N.mp4` |
| S6 | 粗剪 | editing-agent | `rough_cut.mp4` |
| S7 | 精剪（人工反馈迭代） | editing-agent | `fine_cut.mp4` |
| S8 | 配乐 + 字幕 + 成片 | finalize-agent | `final_drama.mp4` 🎬 |

---

## 🏗️ 架构设计

```
drama-maker/
├── SKILL.md                          # 入口 skill（强制路由到 orchestrator）
├── skills/
│   ├── drama-orchestrator/           # 编排核心 + 溯源协议
│   │   └── references/               # pipeline-state / log / credit-estimation
│   ├── story-writer/                 # 故事生成
│   ├── scriptwriter/                 # 剧本生成
│   ├── storyboard-designer/          # 分镜 + 配乐计划
│   ├── character-keyframe-gen/       # 角色关键帧
│   ├── video-segment-gen/            # 视频片段生成
│   ├── video-editing/                # 粗剪 + 精剪（含 ffmpeg 脚本）
│   └── music-subtitle-finalize/      # 配乐 + 字幕 + 成片（含脚本）
├── agents/                           # 7 个子 Agent 定义
├── experts/                          # 4 个领域 Expert（言情/悬疑/喜剧/通用）
├── references/                       # 一致性指南 / ffmpeg 速查 / 音乐平台 / 分镜模板
└── assets/
    ├── subtitle-styles/              # 字幕样式（.ass）
    └── transition-presets/           # 转场预设
```

### 关键设计亮点

1. **角色一致性三层锁定** —— 角色卡 `seed_prompt` → ImageGen 图生图首帧 → VideoGen 图生视频，禁止纯文生视频，保证跨镜头角色外观统一
2. **信用预算前置确认** —— S0 预估 ImageGen/VideoGen 消耗，用户确认后才执行，避免意外消耗
3. **人工介入精剪** —— S6 粗剪后暂停展示，支持 5 种反馈（trim / replace / reorder / transition / speed），replace 可回溯 S5 重新生成
4. **配乐三种方案** —— Suno 浏览器生成 / ffmpeg 已有音频 / 用户上传
5. **Pipeline State 全程溯源** —— 每个 Stage 完成后更新 YAML 再声明检查点

---

## 📦 安装与使用

### 安装

将 `drama-maker/` 目录放到本地 CodeBuddy 的 skills 目录后重启：

```bash
# macOS
~/.codebuddy/skills/drama-maker/

# Linux
~/.codebuddy/skills/drama-maker/
```

### 触发方式

对话中输入触发词即可激活，例如：

```
做一部悬疑短剧，主题是"深夜密室"，时长60秒
制作一部甜宠短剧
生成一个关于外卖小哥的喜剧短剧
```

---

## ⚙️ 依赖工具

| 工具 | 用途 | 需要 |
|------|------|------|
| **ImageGen** | 文生图 / 图生图（角色关键帧、镜头首帧） | 内置，消耗 credits |
| **VideoGen** | 图生视频（视频片段生成） | 内置，消耗 credits |
| **ffmpeg** | 剪辑、拼接、转场、字幕烧录、音视频合成 | 需已安装 |
| **sag (ElevenLabs)** | TTS 角色配音（可选） | 需 `ELEVENLABS_API_KEY` |
| **Suno** | AI 配乐生成（可选） | 需账号，浏览器访问 |
| **Whisper** | 语音转字幕（可选） | 内置/API |

---

## 🛡️ 信用消耗参考

| 操作 | 工具 | 单次消耗 |
|------|------|---------|
| 角色关键帧 | ImageGen | 5-10 credits/张 |
| 镜头首帧 | ImageGen 图生图 | 5-10 credits/张 |
| 视频片段 | VideoGen 图生视频 | 50-100 credits/5s |

> 一个 60s 短剧（2 角色、12 镜头）预估约 **1080 credits**。S0 会先给出精确预估并请求确认。

---

## 📝 License

本 Skill 源码开放使用，欢迎基于你的需求自由修改和扩展。

---

## 🤝 贡献

欢迎通过 Issues / PR 完善短剧制作的更多能力（多集支持、更多领域 Expert、降级策略等）。
