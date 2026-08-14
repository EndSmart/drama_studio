"""
总导演 Agent（Stage 0）。

职责：接收用户创作主题和参数，分析类型、拆解创意要点，
产出"导演工作单"（creative brief），供下游编剧/分镜/角色/视频各 agent 遵循。

它是流水线的大脑，不直接生成媒体，而是确保所有 agent 遵循统一的创意方向和角色设定。
"""

import json
from typing import Any, Dict

from .base import BaseAgent
from ..services.storage import store
from ..services.prompts import prompt_store


class DirectorAgent(BaseAgent):
    """总导演 Agent。"""

    name = "director"
    description = "总导演：分析主题、制定创意方向与全局工作单"

    async def run(self, state: Dict, config: Dict, instruction: str = None) -> Any:
        self.log(f"总导演分析主题: {config.get('theme', '')}")

        theme = config.get("theme", "")
        target_duration = config.get("target_duration", 60)
        genre_hint = config.get("genre_hint", "")
        style = config.get("style", "cinematic")

        # 用户预定义角色（角色管理面板写入），若有则注入工作单，避免 AI 另起炉灶
        user_characters = store.load_artifact(self.project_id, "artifacts/characters/characters.json")
        user_characters = user_characters if isinstance(user_characters, list) and user_characters else []

        user_prompt = f"""请为以下短剧创作主题制作导演工作单。

主题：{theme}
目标时长：{target_duration}秒（单集）
类型提示：{genre_hint or '（由你判断）'}
视觉风格：{style}
"""
        if user_characters:
            user_prompt += (
                "\n以下是用户已经预定义的角色，请直接沿用其 name 与 role，"
                "不要另起炉灶，可在其基础上补充性格与外貌细节：\n"
                + json.dumps(user_characters, ensure_ascii=False, indent=2)
                + "\n"
            )
        user_prompt += "\n请输出 JSON 格式的导演工作单。"

        if instruction:
            user_prompt += f"\n\n【用户修改意见，请据此调整导演工作单】{instruction}"

        system_prompt = prompt_store.get_effective(self.project_id, self.name, "system")
        brief = await self.chat_json(system_prompt, user_prompt, temperature=0.6)

        # 保存导演工作单
        path = store.save_artifact(self.project_id, "director", "creative_brief.json", brief)
        store.log(self.project_id, self.name, "导演工作单已生成")

        return {
            "brief": brief,
            "path": path,
            "genre": brief.get("genre"),
            "characters": brief.get("characters", []),
        }
