"""
分镜 Agent（Stage 3）。

职责：将剧本拆分为逐镜头分镜脚本，每个镜头含画面描述、运镜、时长、
配乐基调。产出 storyboard.json 和 music_plan.json。

image_prompt 供图像生成（含角色外貌+场景），video_prompt 供视频生成（仅运动）。
"""

import json
from typing import Any, Dict

from .base import BaseAgent
from ..services.storage import store
from ..services.prompts import prompt_store


class StoryboarderAgent(BaseAgent):
    """分镜 Agent。"""

    name = "storyboarder"
    description = "分镜：将剧本拆分为逐镜头脚本并规划配乐基调"

    async def run(self, state: Dict, config: Dict, instruction: str = None) -> Any:
        self.log("分镜 Agent 开始拆分剧本")

        # 读取剧本
        script_text = store.load_artifact(self.project_id, "artifacts/screenwriter/script.md")
        if not script_text:
            raise ValueError("未找到剧本，请先运行编剧 Agent")

        target_duration = config.get("target_duration", 60)
        aspect_ratio = config.get("aspect_ratio", "9:16")

        user_template = prompt_store.get_effective(self.project_id, self.name, "user_template")
        # 兼容模板中可能存在的 {duration} 占位符
        try:
            user_msg = user_template.format(duration=target_duration)
        except (KeyError, IndexError):
            user_msg = user_template
        user_msg += f"\n\n剧本内容：\n{script_text}\n\n画幅比例：{aspect_ratio}\n请输出 JSON。"

        # 交互式润色：附上用户的修改意见
        if instruction:
            user_msg += f"\n\n【用户修改意见，请据此调整分镜】{instruction}"
            self.log("分镜按用户意见润色")

        system_prompt = prompt_store.get_effective(self.project_id, self.name, "system")
        result = await self.chat_json(
            system_prompt,
            user_msg,
            temperature=0.4,
        )

        storyboard = result.get("storyboard", {"shots": []})
        music_plan = result.get("music_plan", {"overall_tone": "neutral", "segments": []})

        # 规范化 shots
        shots = storyboard.get("shots", [])
        for i, shot in enumerate(shots):
            shot["shot_id"] = shot.get("shot_id", i + 1)
            shot["duration_seconds"] = shot.get("duration_seconds", 5)
            shot.setdefault("transition_to_next", "cut")
            shot.setdefault("music_mood", "neutral")

        storyboard_path = store.save_artifact(self.project_id, "storyboarder", "storyboard.json", storyboard)
        music_path = store.save_artifact(self.project_id, "storyboarder", "music_plan.json", music_plan)
        self.log(f"分镜完成，共 {len(shots)} 个镜头")

        return {
            "storyboard": storyboard,
            "music_plan": music_plan,
            "storyboard_path": storyboard_path,
            "music_path": music_path,
            "shot_count": len(shots),
        }
