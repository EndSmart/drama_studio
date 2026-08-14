"""
编剧 Agent（Stage 1-2）。

职责：
1. 基于导演工作单生成完整故事文本（story）
2. 将故事转化为标准短剧剧本（script），含场景/对白/动作指示

产出两个中间产物：story.md 和 script.md。
"""

import json
from typing import Any, Dict

from .base import BaseAgent
from ..services.storage import store
from ..services.prompts import prompt_store


class ScreenwriterAgent(BaseAgent):
    """编剧 Agent。"""

    name = "screenwriter"
    description = "编剧：生成故事文本与标准剧本"

    async def run(self, state: Dict, config: Dict, instruction: str = None) -> Any:
        self.log("编剧开始创作")

        # 读取导演工作单
        brief = store.load_artifact(self.project_id, "artifacts/director/creative_brief.json")
        if not brief:
            # 无导演工作单时，直接基于主题生成
            brief = {"theme": config.get("theme", ""), "characters": []}

        theme = brief.get("theme", config.get("theme", ""))
        genre = brief.get("genre", config.get("genre_hint", ""))

        # Step 1: 生成故事
        story_system = prompt_store.get_effective(self.project_id, self.name, "story")
        story_text = await self.llm.chat([
            {"role": "system", "content": story_system},
            {"role": "user", "content": f"导演工作单：\n主题：{theme}\n类型：{genre}\n角色设定：{json.dumps(brief.get('characters', []), ensure_ascii=False)}\n\n请生成故事。"},
        ], temperature=0.7)

        story_path = store.save_artifact(self.project_id, "screenwriter", "story.md", story_text, ext="md")
        self.log("故事文本已生成")

        # Step 2: 生成剧本
        target_duration = config.get("target_duration", 60)
        # 用 replace 而非 format，避免示例中的 {N}/{地点} 占位符触发 KeyError
        script_system = prompt_store.get_effective(self.project_id, self.name, "script")
        script_prompt = script_system.replace("{duration}", str(target_duration))

        # 交互式润色：若用户给出修改意见，则基于现有故事 + 意见修改剧本
        if instruction:
            user_msg = (
                f"这是当前的故事文本：\n{story_text}\n\n"
                f"请根据以下修改意见对剧本进行润色/改写（保持整体结构与角色一致）：\n"
                f"【修改意见】{instruction}\n\n请直接输出修改后的标准剧本。"
            )
            self.log("编剧按用户意见润色剧本")
        else:
            user_msg = f"故事文本：\n{story_text}\n\n请将其转化为标准剧本。"

        script_text = await self.llm.chat([
            {"role": "system", "content": script_prompt},
            {"role": "user", "content": user_msg},
        ], temperature=0.6)

        script_path = store.save_artifact(self.project_id, "screenwriter", "script.md", script_text, ext="md")
        self.log("剧本已生成")

        # 尝试提取剧本信息用于分镜
        return {
            "story": story_text,
            "script": script_text,
            "story_path": story_path,
            "script_path": script_path,
        }
