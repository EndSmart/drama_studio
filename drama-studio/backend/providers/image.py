"""
图像生成 Provider 统一抽象层。

用于角色关键帧生成和镜头首帧生成。
已实现：万相（wanx）文生图/图生图、OpenAI（gpt-image-1 / DALL·E 3）文生图/图生图编辑。
"""

import asyncio
import base64
import logging
import time
import uuid
from typing import Dict, Optional

import httpx

from .. import config

logger = logging.getLogger("drama-studio.providers.image")


class ImageProviderError(Exception):
    """图像生成 provider 错误。"""


class ImageProvider:
    """图像 provider 抽象基类。"""

    name = "base"

    async def generate(self, prompt: str, **kwargs) -> str:
        """生成单张图片，返回图片 URL。"""
        raise NotImplementedError


class WanxImageProvider(ImageProvider):
    """阿里通义万相文生图/图生图。异步提交+轮询。"""

    name = "wanx"
    base_url = config.IMAGE_PROVIDERS["wanx"]["base_url"]
    default_model = config.IMAGE_PROVIDERS["wanx"]["default_model"]

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.get_env(config.IMAGE_PROVIDERS["wanx"]["env_key"])
        if not self.api_key:
            raise ValueError("万相图像未配置 DASHSCOPE_API_KEY")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-DashScope-Async": "enable",
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str, **kwargs) -> str:
        size = kwargs.get("size", "1024*1536")  # 竖屏角色图
        model = kwargs.get("model", self.default_model)
        inp = {"prompt": prompt}
        if kwargs.get("reference_image"):
            # 图生图：传参考图，保持一致性
            inp["image"] = kwargs["reference_image"]

        payload = {
            "model": model,
            "input": inp,
            "parameters": {"size": size, "n": 1, "prompt_extend": True},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("output", {}).get("task_id")
            if not task_id:
                raise ImageProviderError(f"万相图像提交失败: {data}")

        # 轮询结果
        query_url = "https://dashscope.aliyuncs.com/api/v1/tasks/" + task_id
        deadline = time.time() + 120
        while time.time() < deadline:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    query_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
            status = data.get("output", {}).get("task_status", "PENDING")
            if status == "SUCCEEDED":
                results = data.get("output", {}).get("results", [])
                if results:
                    return results[0].get("url")
                # 兼容其他字段
                url = data.get("output", {}).get("image_url")
                if url:
                    return url
                raise ImageProviderError("万相图像成功但无结果 URL")
            if status == "FAILED":
                raise ImageProviderError(f"万相图像失败: {data.get('output', {}).get('message', '未知')}")
            await asyncio.sleep(3)

        raise ImageProviderError("万相图像生成超时")


class OpenAIImageProvider(ImageProvider):
    """OpenAI 图像生成（gpt-image-1 / DALL·E 3）。支持文生图与图生图编辑。"""

    name = "openai"
    base_url = config.IMAGE_PROVIDERS["openai"]["base_url"]
    default_model = config.IMAGE_PROVIDERS["openai"]["default_model"]

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.get_env(config.IMAGE_PROVIDERS["openai"]["env_key"])
        if not self.api_key:
            raise ValueError("OpenAI 图像未配置 OPENAI_API_KEY")

    async def generate(self, prompt: str, **kwargs) -> str:
        model = kwargs.get("model", self.default_model)
        # OpenAI 尺寸格式为 "1024x1536"（万相是 "1024*1536"），统一转换
        size = kwargs.get("size", "1024x1536").replace("*", "x")
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size,
        }

        reference = kwargs.get("reference_image")
        if reference:
            # 图生图编辑：reference 可为公网 URL 或 base64 data URI
            payload["image"] = [reference]

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/images/generations",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        item = (data.get("data") or [{}])[0]
        if item.get("url"):
            return item["url"]
        if item.get("b64_json"):
            # gpt-image-1 默认返回 base64，落盘为本地文件并返回绝对路径
            raw = base64.b64decode(item["b64_json"])
            out_dir = config.DATA_DIR / "images"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{uuid.uuid4().hex}.png"
            path.write_bytes(raw)
            logger.info("OpenAI 图像以 base64 返回，已保存至 %s", path)
            return str(path.resolve())
        raise ImageProviderError("OpenAI 图像返回中无 url / b64_json 字段")


class ImageProviderFactory:
    """图像 provider 工厂。"""

    @staticmethod
    def create(provider: str = None, **kwargs) -> ImageProvider:
        provider = provider or "wanx"
        if provider == "wanx":
            return WanxImageProvider(**kwargs)
        if provider == "openai":
            return OpenAIImageProvider(**kwargs)
        raise ValueError(f"未知图像 provider: {provider}")

    @staticmethod
    def list_available():
        return [
            {
                "key": k,
                "name": v["name"],
                "desc": v["desc"],
                "configured": config.is_image_provider_configured(k),
            }
            for k, v in config.IMAGE_PROVIDERS.items()
        ]
