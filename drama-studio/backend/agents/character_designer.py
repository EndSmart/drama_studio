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
from ..services.prompts import prompt_store

logger = logging.getLogger("drama-studio.agents.character")


class CharacterDesignerAgent(BaseAgent):
    """角色设计 Agent。"""

    name = "character_designer"
    description = "角色设计：生成角色设定与基准关键帧图，建立角色卡"

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

    @staticmethod
    def _build_seed_prompt(card: Dict) -> str:
        """本地兜底：把 appearance 各字段拼成一句一致性描述。"""
        parts = []
        appearance = card.get("appearance") or {}
        if isinstance(appearance, dict):
            for v in appearance.values():
                if v:
                    parts.append(str(v))
        if not parts:
            return card.get("name", "角色")
        return "，".join(parts)

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

        # 用户预定义角色（角色管理面板写入），若有则以用户定义为基准
        user_characters = store.load_artifact(self.project_id, "artifacts/characters/characters.json")
        user_characters = user_characters if isinstance(user_characters, list) and user_characters else []

        system_prompt = prompt_store.get_effective(self.project_id, self.name, "system")

        if user_characters:
            self.log("检测到用户预定义角色，以其为基准做补全/规范化")
            user_msg = (
                "以下是用户已经预定义的角色，请直接沿用其 name / role / appearance / seed_prompt，"
                "仅做必要的补全与规范化（例如补全缺失的 seed_prompt），不要替换或重命名角色。\n"
                + json.dumps(user_characters, ensure_ascii=False, indent=2)
            )
            if instruction:
                user_msg += f"\n\n【用户修改意见，请据此调整角色设定】{instruction}"
            try:
                character_cards = await self.chat_json(system_prompt, user_msg, temperature=0.3)
            except Exception as e:
                logger.warning("角色补全 LLM 调用失败，回退使用用户定义: %s", e)
                character_cards = None
            if not isinstance(character_cards, list) or not character_cards:
                # 兜底：直接使用用户定义，本地补全 seed_prompt
                character_cards = []
                for c in user_characters:
                    c = dict(c)
                    if not c.get("seed_prompt"):
                        c["seed_prompt"] = self._build_seed_prompt(c)
                    character_cards.append(c)
        else:
            user_msg = (
                "请根据以下剧本和分镜中的角色设计角色卡。\n\n"
                f"剧本中的角色线索：\n{script[:3000]}\n\n"
                f"分镜出现的角色：{list(chars_in_shots)}\n请为这些角色设计角色卡，输出 JSON 数组。"
            )
            if instruction:
                user_msg += f"\n\n【用户修改意见，请据此调整角色设定】{instruction}"
                self.log("角色设计按用户意见润色")
            character_cards = await self.chat_json(system_prompt, user_msg, temperature=0.5)

        if not isinstance(character_cards, list):
            character_cards = [character_cards]

        style = config.get("style", "cinematic")
        result = []
        image_provider = self._get_image_provider()

        for card in character_cards:
            if not isinstance(card, dict):
                continue
            name = card.get("name", "角色")
            # 若 LLM 未给 seed_prompt，本地补全
            if not card.get("seed_prompt"):
                card["seed_prompt"] = self._build_seed_prompt(card)
            card["style"] = style

            # 生成角色基准正面图（若尚未有参考图）
            reference_image = card.get("reference_image") or None
            if not reference_image and image_provider:
                try:
                    img_prompt = (
                        f"角色设计标准照，{card.get('seed_prompt', '')}，{style}风格，"
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

            result.append(card)

        # 聚合写入 characters.json，便于「角色管理」面板加载/编辑，以及后续重跑时注入
        store.save_artifact(self.project_id, "characters", "characters.json", result)

        self.log(f"角色设计完成，共 {len(result)} 个角色")
        return {
            "characters": result,
            "image_provider": self.image_provider,
        }
