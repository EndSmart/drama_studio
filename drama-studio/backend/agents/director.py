"""
总导演 Agent（Stage 0）。

职责：接收用户创作主题和参数，分析类型、拆解创意要点，
产出"导演工作单"（creative brief），供下游编剧/分镜/角色/视频各 agent 遵循。

它是流水线的大脑，不直接生成媒体，而是确保所有 agent 遵循统一的创意方向和角色设定。
"""

from typing import Any, Dict

from .base import BaseAgent
from ..services.storage import store


class DirectorAgent(BaseAgent):
    """总导演 Agent。"""

    name = "director"
    description = "总导演：分析主题、制定创意方向与全局工作单"

    SYSTEM_PROMPT = """你是资深的短剧总导演。你的职责是分析用户给出的创作主题，产出一份结构化的"导演工作单"（creative brief），作为后续编剧、分镜、角色设计、视频生成等所有环节的统一指导纲领。

工作单必须包含：
1. theme：短剧主题
2. genre：类型（言情/悬疑/喜剧/都市/奇幻/科幻/古装等）
3. tone：整体基调（如：暗恋虐心/轻甜欢喜/悬疑紧张等）
4. story_highlights：核心看点与卖点（2-4 条）
5. characters：主要角色清单，每个含 name / role（主角/配角/反派）/ personality（性格）/ appearance（外貌，尽量具体到发型/脸型/服饰，供角色设计使用）
6. plot_arc：情节脉络（起/承/转/合四个阶段的简述）
7. target_audience：目标受众
8. visual_style：视觉风格建议（如：电影质感/日系清新/都市写实等）

严格要求：
- 角色外貌描述必须具体、可被图像生成模型理解（描述发型、脸型、眼睛、体型、标志性服饰），这是后续角色一致性的基础
- 用 JSON 格式输出
- 不要写完整剧本，那是编剧的事
"""

    async def run(self, state: Dict, config: Dict) -> Any:
        self.log(f"总导演分析主题: {config.get('theme', '')}")

        theme = config.get("theme", "")
        target_duration = config.get("target_duration", 60)
        genre_hint = config.get("genre_hint", "")
        style = config.get("style", "cinematic")

        user_prompt = f"""请为以下短剧创作主题制作导演工作单。

主题：{theme}
目标时长：{target_duration}秒（单集）
类型提示：{genre_hint or '（由你判断）'}
视觉风格：{style}

请输出 JSON 格式的导演工作单。"""

        brief = await self.chat_json(self.SYSTEM_PROMPT, user_prompt, temperature=0.6)

        # 保存导演工作单
        path = store.save_artifact(self.project_id, "director", "creative_brief.json", brief)
        store.log(self.project_id, self.name, "导演工作单已生成")

        return {
            "brief": brief,
            "path": path,
            "genre": brief.get("genre"),
            "characters": brief.get("characters", []),
        }
