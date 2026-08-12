"""
视频生成 Agent（Stage 5）。

职责：逐镜头生成视频片段，核心是角色一致性三层锁定：
1. 读取角色卡（seed_prompt + reference_image）
2. 图像 provider 图生图生成镜头首帧（参考角色基准图）
3. 视频 provider 图生视频（首帧为输入，video_prompt 描述运动）

支持并行生成多个镜头（asyncio.gather）。
"""

import asyncio
import logging
from typing import Any, Dict, List

from .base import BaseAgent
from ..providers.video import VideoProviderFactory
from ..providers.image import ImageProviderFactory
from ..services.storage import store

logger = logging.getLogger("drama-studio.agents.video")


class VideoProducerAgent(BaseAgent):
    """视频生成 Agent。"""

    name = "video_producer"
    description = "视频生成：逐镜头生成视频片段，保证角色一致性"

    def __init__(self, project_id: str, llm_provider: str = None, api_key: str = None,
                 video_provider: str = None, video_api_key: str = None,
                 image_provider: str = None, image_api_key: str = None):
        super().__init__(project_id, llm_provider, api_key)
        self.video_provider = video_provider or "kling"
        self.video_api_key = video_api_key
        self.image_provider = image_provider or "wanx"
        self.image_api_key = image_api_key
        self._video = None
        self._image = None

    def _get_video(self):
        if self._video is None:
            self._video = VideoProviderFactory.create(self.video_provider, api_key=self.video_api_key)
        return self._video

    def _get_image(self):
        if self._image is None:
            try:
                self._image = ImageProviderFactory.create(self.image_provider, api_key=self.image_api_key)
            except Exception as e:
                logger.warning("图像 provider 不可用: %s", e)
                self._image = None
        return self._image

    def _get_character_card(self, name: str, cards: List[Dict]) -> Dict:
        for c in cards:
            if c.get("name") == name or name in c.get("name", ""):
                return c
        # 模糊匹配
        for c in cards:
            if name and name in c.get("name", "") or c.get("name", "") in name:
                return c
        return {}

    async def _generate_shot(self, shot: Dict, character_cards: List[Dict], config: Dict) -> Dict:
        shot_id = shot.get("shot_id", 0)
        video = self._get_video()
        image = self._get_image()
        image_prompt = shot.get("image_prompt", shot.get("visual_description", ""))
        video_prompt = shot.get("video_prompt", shot.get("visual_description", ""))
        duration = shot.get("duration_seconds", 5)
        resolution = config.get("resolution", "720p")
        aspect_ratio = config.get("aspect_ratio", "9:16")

        # 角色的参考图
        chars = shot.get("characters_in_shot", [])
        ref_image = None
        seed = ""
        for name in chars:
            card = self._get_character_card(name, character_cards)
            if card.get("reference_image"):
                ref_image = card["reference_image"]
                seed = card.get("seed_prompt", "")
                break

        first_frame = None
        video_url = None

        # 1. 生成镜头首帧（图生图，参考角色）
        if image and ref_image:
            try:
                frame_prompt = f"{seed}，{image_prompt}" if seed else image_prompt
                first_frame = await image.generate(frame_prompt, reference_image=ref_image, size="720*1280")
                self.log(f"镜头 {shot_id} 首帧已生成")
            except Exception as e:
                logger.warning("镜头 %d 首帧生成失败: %s", shot_id, e)
                self.log(f"镜头 {shot_id} 首帧失败，改用文生视频")

        # 2. 生成视频
        try:
            video_url = await video.submit_task(
                prompt=video_prompt,
                image_url=first_frame,
                duration=duration,
                resolution=resolution,
                aspect_ratio=aspect_ratio,
            )
            self.log(f"镜头 {shot_id} 视频任务已提交: {video_url}")
            # 异步等待结果（阻塞）
            result_url = await video.wait_for_result(video_url, timeout=600, interval=5)
            self.log(f"镜头 {shot_id} 视频生成完成")
            return {
                "shot_id": shot_id,
                "clip_url": result_url,
                "first_frame_url": first_frame,
                "status": "succeeded",
            }
        except Exception as e:
            logger.exception("镜头 %d 视频生成失败", shot_id)
            self.log(f"镜头 {shot_id} 视频生成失败: {e}")
            return {
                "shot_id": shot_id,
                "clip_url": None,
                "first_frame_url": first_frame,
                "status": "failed",
                "error": str(e),
            }

    async def run(self, state: Dict, config: Dict) -> Any:
        self.log("视频生成 Agent 开始")

        storyboard = store.load_artifact(self.project_id, "artifacts/storyboarder/storyboard.json") or {}
        shots = storyboard.get("shots", [])

        # 读取角色卡
        character_cards = []
        import json
        chars_dir = store.project_dir(self.project_id) / "artifacts" / "characters"
        if chars_dir.exists():
            for card_file in chars_dir.rglob("character_card.json"):
                try:
                    with open(card_file, "r", encoding="utf-8") as f:
                        character_cards.append(json.load(f))
                except Exception:
                    continue

        self.log(f"读取到 {len(shots)} 个镜头，{len(character_cards)} 个角色卡")

        # 并发生成所有镜头
        results = await asyncio.gather(
            *[self._generate_shot(shot, character_cards, config) for shot in shots]
        )

        # 保存剪辑清单
        clips_manifest = {
            "video_provider": self.video_provider,
            "clips": results,
        }
        store.save_artifact(self.project_id, "video_producer", "clips_manifest.json", clips_manifest)

        succeeded = [r for r in results if r["status"] == "succeeded"]
        failed = [r for r in results if r["status"] == "failed"]
        self.log(f"视频生成完成：成功 {len(succeeded)}，失败 {len(failed)}")

        return {
            "clips": results,
            "succeeded_count": len(succeeded),
            "failed_count": len(failed),
        }
