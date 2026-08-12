"""
角色设计 Agent（Stage 4）。

职责：为每个角色生成角色设定与基准关键帧图（正面照），建立角色卡。
角色卡（seed_prompt + reference_image）是视频生成时保持角色一致性的核心。

当前使用图像 provider 生成角色基准图。若无图像 provider 配置，
则退化输出角色卡描述（不含图），供后续文生视频使用。
"""

import asyncio
import json
import logging
from typing import Any, Dict, List

from .base import BaseAgent
from ..providers.image import ImageProviderFactory
from ..services.storage import store

logger = logging.getLogger("drama-studio.agents.character")


class CharacterDesignerAgent(BaseAgent):
    """角色设计 Agent。"""

    name = "character_designer"
    description = "角色设计：生成角色设定与基准关键帧图，建立角色卡"

    PROMPT = """你是角色设计总监。根据剧本和分镜中的角色，为每个角色生成标准化的角色卡。

对每个角色输出：
{{
  "name": "角色名",
  "role": "主角/配角/反派",
  "personality": "性格",
  "appearance": {{
    "age": "年龄",
    "hair": "发型",
    "face": "脸型",
    "eyes": "眼睛",
    "complexion": "肤色",
    "body": "体型",
    "clothing": "标志性服装"
  }},
  "seed_prompt": "一段固定的外貌描述前缀，用于所有后续图像/视频生成保持一致性（整合 age/hair/face/eyes/complexion/body/clothing 为一句话，如：20岁长发瓜子脸大眼睛皮肤白皙的少女，穿着白色连衣裙）",
  "style": "视觉风格"
}}

严格输出 JSON 数组格式：[角色卡1, 角色卡2, ...]"""

    def __init__(self, project_id: str, llm_provider: str = None, api_key: str = None,
                 image_provider: str = None, image_api_key: str = None):
        super().__init__(project_id, llm_provider, api_key)
        self.image_provider = image_provider or "wanx"
        self.image_api_key = image_api_key
        self._image = None

    def _get_image_provider(self):
        if self._image is None:
            try:
                self._image = ImageProviderFactory.create(self.image_provider, api_key=self.image_api_key)
            except Exception as e:
                logger.warning("图像 provider 不可用: %s", e)
                self._image = None
        return self._image

    async def run(self, state: Dict, config: Dict, instruction: str = None) -> Any:
        self.log("角色设计 Agent 开始")

        # 读取剧本和分镜中的角色
        script = store.load_artifact(self.project_id, "artifacts/screenwriter/script.md") or ""
        storyboard = store.load_artifact(self.project_id, "artifacts/storyboarder/storyboard.json") or {}

        # 收集分镜中出现的角色
        chars_in_shots = set()
        for shot in storyboard.get("shots", []):
            for c in shot.get("characters_in_shot", []):
                chars_in_shots.add(c)

        user_msg = (
            self.PROMPT
            + f"\n\n剧本中的角色线索：\n{script[:3000]}\n\n分镜出现的角色：{list(chars_in_shots)}\n请为这些角色设计角色卡，输出 JSON 数组。"
        )
        if instruction:
            user_msg += f"\n\n【用户修改意见，请据此调整角色设定】{instruction}"
            self.log("角色设计按用户意见润色")

        character_cards = await self.chat_json(
            "你是角色设计总监，严格输出 JSON 数组。",
            user_msg,
            temperature=0.5,
        )

        if not isinstance(character_cards, list):
            character_cards = [character_cards]

        style = config.get("style", "cinematic")
        result = []
        image_provider = self._get_image_provider()

        for card in character_cards:
            name = card.get("name", "角色")
            seed_prompt = card.get("seed_prompt", "")
            card["style"] = style

            # 生成角色基准正面图（如果有图像 provider）
            reference_image = None
            if image_provider:
                try:
                    img_prompt = (
                        f"角色设计标准照，{seed_prompt}，{style}风格，"
                        "正面全身照，居中，纯色或简单背景，电影感打光，高清"
                    )
                    reference_image = await image_provider.generate(img_prompt, size="1024*1536")
                    self.log(f"角色 {name} 基准图已生成")
                except Exception as e:
                    logger.warning("角色 %s 基准图生成失败: %s", name, e)
                    self.log(f"角色 {name} 基准图生成失败: {e}")

            card["reference_image"] = reference_image
            card["character_card_path"] = store.save_artifact(
                self.project_id, "characters", f"{name}/character_card.json", card
            )
            if reference_image:
                store.save_artifact(self.project_id, "characters", f"{name}/reference.png", "", ext="png")

            result.append(card)

        self.log(f"角色设计完成，共 {len(result)} 个角色")
        return {
            "characters": result,
            "image_provider": self.image_provider,
        }
