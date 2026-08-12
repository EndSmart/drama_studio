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


class ScreenwriterAgent(BaseAgent):
    """编剧 Agent。"""

    name = "screenwriter"
    description = "编剧：生成故事文本与标准剧本"

    STORY_PROMPT = """你是资深短剧编剧。根据导演工作单，生成一个适合竖屏短剧的完整故事文本。

要求：
1. 故事要有完整的起承转合，节奏紧凑（短剧需要高频冲突和钩子）
2. 明确所有主要角色的性格和外形
3. 包含故事梗概（300-500字）和分场大纲
4. 结尾要有一个钩子或反转，吸引观众看下一集

输出 Markdown 格式：
# 故事标题
## 故事梗概
（正文）
## 角色设定
（每个角色一段）
## 分场大纲
（每场一段，标注地点/时间/核心事件）"""

    SCRIPT_PROMPT = """你是专业短剧编剧。根据故事文本，将故事转化为标准的短剧分场剧本。

要求：
1. 用标准剧本格式：场景标题（场景编号、地点、时间）、人物、对白、动作指示
2. 对白要口语化、符合角色性格、每句简洁有力（短剧对白要短促、有张力）
3. 动作指示放在括号中
4. 目标总时长约 {duration} 秒，平均每场景 15-20 秒
5. 每场包含 1-2 个核心情节点

输出 Markdown 格式：
## 场景 {N}：{地点}（{时间}）
人物：{角色1}、{角色2}
{动作/环境描述}
**{角色1}**：（{动作指示}）{对白}
**{角色2}**：{对白}
..."""

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
        story_text = await self.llm.chat([
            {"role": "system", "content": self.STORY_PROMPT},
            {"role": "user", "content": f"导演工作单：\n主题：{theme}\n类型：{genre}\n角色设定：{json.dumps(brief.get('characters', []), ensure_ascii=False)}\n\n请生成故事。"},
        ], temperature=0.7)

        story_path = store.save_artifact(self.project_id, "screenwriter", "story.md", story_text, ext="md")
        self.log("故事文本已生成")

        # Step 2: 生成剧本
        target_duration = config.get("target_duration", 60)
        # 用 replace 而非 format，避免示例中的 {N}/{地点} 占位符触发 KeyError
        script_prompt = self.SCRIPT_PROMPT.replace("{duration}", str(target_duration))

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
