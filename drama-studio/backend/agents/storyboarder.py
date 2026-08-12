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


class StoryboarderAgent(BaseAgent):
    """分镜 Agent。"""

    name = "storyboarder"
    description = "分镜：将剧本拆分为逐镜头脚本并规划配乐基调"

    PROMPT = """你是专业的短剧分镜师。根据剧本，将其拆分为逐镜头分镜脚本，并规划配乐基调。

要求：
1. 每个镜头包含：shot_id、scene_id、shot_type（closeup/medium/wide）、camera_movement（static/pan/tilt/zoom_in/zoom_out/tracking）、visual_description、characters_in_shot、dialogue、duration_seconds、transition_to_next（cut/fade/dissolve）、music_mood、image_prompt、video_prompt、negative_prompt
2. image_prompt：完整的画面描述（含角色外貌特征 + 场景环境 + 光线氛围 + 视觉风格），供图像生成首帧。角色外貌必须保持与角色设定一致
3. video_prompt：仅描述运动/动作/镜头运动，不要重复角色外貌（因为首帧已锁定角色）
4. duration_seconds：默认 5 秒，总时长约 {duration} 秒
5. 竖屏短剧以中近景和特写为主
6. music_mood 用以下标签：tense/romantic/sad/happy/suspense/neutral/action

另外输出 music_plan.json：
{{
  "overall_tone": "整体基调",
  "segments": [
    {{
      "shot_range": [起始镜头, 结束镜头],
      "mood": "情绪标签",
      "tempo": "slow/medium/fast",
      "instruments": ["钢琴","弦乐"],
      "duration_seconds": 时长,
      "source": "auto",
      "description": "音乐描述"
    }}
  ]
}}

严格输出 JSON，格式：
{{"storyboard": {{"shots": [...]}}, "music_plan": {{...}} }}
不要输出任何多余文字。"""

    async def run(self, state: Dict, config: Dict, instruction: str = None) -> Any:
        self.log("分镜 Agent 开始拆分剧本")

        # 读取剧本
        script_text = store.load_artifact(self.project_id, "artifacts/screenwriter/script.md")
        if not script_text:
            # 尝试直接读 screenplay 阶段产物
            script_text = store.load_artifact(self.project_id, "artifacts/screenwriter/script.md")
        if not script_text:
            raise ValueError("未找到剧本，请先运行编剧 Agent")

        target_duration = config.get("target_duration", 60)
        aspect_ratio = config.get("aspect_ratio", "9:16")

        user_msg = (
            self.PROMPT.format(duration=target_duration)
            + f"\n\n剧本内容：\n{script_text}\n\n画幅比例：{aspect_ratio}\n请输出 JSON。"
        )
        # 交互式润色：附上用户的修改意见
        if instruction:
            user_msg += f"\n\n【用户修改意见，请据此调整分镜】{instruction}"
            self.log("分镜按用户意见润色")

        result = await self.chat_json(
            "你是专业分镜师。严格按照 JSON 格式输出分镜脚本和配乐计划。",
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
