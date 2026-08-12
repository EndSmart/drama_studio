# 🎬 Drama Studio — 短剧制作智能体集群 Web 应用

> 从**创意到成片**的完整自动化短剧制作智能体集群。输入一个创作主题，智能体集群自动完成：故事 → 剧本 → 分镜 → 角色设计 → 视频生成 → 剪辑 → 配乐字幕 → 成片。

## ✨ 核心特性

- **多智能体协同**：总导演、编剧、分镜、角色设计、视频生成、剪辑共 6 个智能体分工协作
- **主流大模型接入**：DeepSeek、阿里千问 Qwen、Kimi、智谱 GLM、火山豆包（全部 OpenAI 兼容）
- **主流视频平台接入**：火山 Seedance、快手可灵、阿里万相、智谱 CogVideoX
- **角色一致性三层锁定**：角色卡 → 图生图首帧 → 图生视频
- **Web 实时进度**：WebSocket 推送每个智能体的执行进度
- **竖屏短剧**：默认 9:16 竖屏，符合短剧观看习惯
- **用户登录认证**：基于 HttpOnly 会话 Cookie 的登录鉴权，所有 `/api` 与 `/ws` 接口均受保护
- **管理员用户管理**：管理员可在界面中添加 / 删除用户（普通用户仅可使用制作功能）

## 🚀 快速开始

### 方式一：在线使用（已发布）

直接访问部署好的在线链接即可使用。

### 方式二：本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量（API Key）
export DEEPSEEK_API_KEY="sk-xxx"          # 或任一大模型 key
export DASHSCOPE_API_KEY="sk-xxx"         # 千问/万相
export KLING_ACCESS_KEY="xxx"              # 可灵
export KLING_SECRET_KEY="xxx"
export ARK_API_KEY="xxx"                   # 火山/豆包/Seedance

# 启动
PORT=8000 python app.py
# 或
uvicorn app:app --host 0.0.0.0 --port 8000
```

打开 http://localhost:8000 即可使用。

## 🔐 登录认证

应用默认开启登录认证，首次启动会自动创建默认管理员账户：

- **用户名**：`admin`
- **密码**：`admin123`

> 请尽快在「用户管理」中修改密码或新增专属账户。如需更强安全性，可通过环境变量 `SESSION_SECRET` 设置一个随机长字符串（用于会话签名）。

权限说明：

- **普通用户（user）**：可使用短剧制作的全部功能
- **管理员（admin）**：在「用户管理」中添加 / 删除用户，且不能删除最后一个管理员账户、不能删除当前登录账户

认证机制：密码使用 `pbkdf2_hmac`（sha256 + 随机 salt）哈希存储；登录后会话 token 经 HMAC-SHA256 签名后写入 HttpOnly Cookie，前端 `/final` 下载与 `/ws` 进度推送均自动携带该 Cookie。

## 🔧 API Key 说明

所有 API Key 通过**环境变量**配置（推荐），或在**前端界面**输入（存于运行时，不入代码库）。

| 平台 | 环境变量 | 用途 |
|------|---------|------|
| DeepSeek | `DEEPSEEK_API_KEY` | 文本生成 |
| 阿里千问/万相 | `DASHSCOPE_API_KEY` | 文本生成 + 图像 + 万相视频 |
| Kimi | `MOONSHOT_API_KEY` | 文本生成 |
| 智谱 GLM | `ZHIPU_API_KEY` | 文本生成 + CogVideoX |
| 火山豆包/Seedance | `ARK_API_KEY` | 文本生成 + Seedance |
| 快手可灵 | `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | 视频生成 |

## 🏗️ 架构

```
drama-studio/
├── app.py                    # FastAPI 入口（读 $PORT，绑 0.0.0.0）
├── backend/
│   ├── config.py             # provider 配置表
│   ├── agents/               # 6 个智能体
│   │   ├── director.py       # 总导演（创意方向）
│   │   ├── screenwriter.py   # 编剧（故事+剧本）
│   │   ├── storyboarder.py   # 分镜
│   │   ├── character_designer.py  # 角色设计
│   │   ├── video_producer.py # 视频生成
│   │   └── editor.py         # 剪辑成片
│   ├── providers/            # AI 平台接入
│   │   ├── llm.py            # OpenAI 兼容统一 LLM
│   │   ├── video.py          # 视频平台适配器
│   │   └── image.py          # 图像平台
│   ├── services/             # 业务服务
│   │   ├── pipeline.py       # 流水线编排
│   │   ├── storage.py        # JSON 持久化
│   │   └── ffmpeg.py         # ffmpeg 封装
│   └── routes/               # API + WebSocket
├── frontend/                 # 单页应用
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
└── data/                     # 项目持久化
```

## 🔗 API

| 端点 | 说明 |
|------|------|
| `GET /api/providers` | 获取各平台配置状态 |
| `POST /api/projects` | 创建项目 |
| `GET /api/projects` | 项目列表 |
| `GET /api/projects/{id}` | 项目详情 |
| `POST /api/projects/{id}/run` | 启动完整流水线 |
| `POST /api/projects/{id}/agents/{name}/run` | 单独运行某智能体 |
| `GET /api/projects/{id}/artifacts` | 中间产物列表 |
| `GET /api/projects/{id}/final` | 下载成片 |
| `WS /ws/{id}` | 实时进度 |

## 📄 License

开源使用，欢迎自由修改扩展。
