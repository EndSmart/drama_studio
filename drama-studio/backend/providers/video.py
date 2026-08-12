"""
视频生成 Provider 统一抽象层。

各家视频生成 API 的异步流程不同（提交任务 → 轮询 → 取结果），
这里定义统一接口 VideoProvider，并为 Seedance / 可灵 / 万相 / 智谱分别实现适配器。

统一接口：
    submit_task(prompt, image_url=None, last_image_url=None, **kwargs) -> task_id
    query_task(task_id) -> {"status": "pending|running|succeeded|failed", "video_url": str|None, "error": str|None}
    wait_for_result(task_id, timeout=600) -> video_url  # 阻塞轮询直到完成
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Dict, Optional

import httpx

from .. import config

logger = logging.getLogger("drama-studio.providers.video")


class VideoProviderError(Exception):
    """视频生成 provider 错误。"""


class VideoProvider:
    """视频 provider 抽象基类。子类实现具体 API。"""

    name = "base"

    def __init__(self, api_key: str = None):
        self.api_key = api_key

    async def submit_task(self, prompt: str, image_url: str = None, last_image_url: str = None, **kwargs) -> str:
        raise NotImplementedError

    async def query_task(self, task_id: str) -> Dict:
        raise NotImplementedError

    async def wait_for_result(self, task_id: str, timeout: float = 600, interval: float = 10) -> str:
        """阻塞轮询直到任务完成，返回视频 URL。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = await self.query_task(task_id)
            status = result.get("status", "pending")
            if status == "succeeded":
                video_url = result.get("video_url")
                if not video_url:
                    raise VideoProviderError(f"{self.name} 任务成功但无 video_url")
                return video_url
            if status == "failed":
                raise VideoProviderError(f"{self.name} 任务失败: {result.get('error', '未知错误')}")
            await asyncio.sleep(interval)
        raise VideoProviderError(f"{self.name} 任务超时（{timeout}s）")

    @staticmethod
    def _auth_header(api_key: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}


# ==================== Seedance（火山引擎）====================
class SeedanceProvider(VideoProvider):
    """字节跳动 Seedance 2.0 视频生成。异步：提交 + 轮询。"""

    name = "seedance"
    base_url = config.VIDEO_PROVIDERS["seedance"]["base_url"]
    text_model = config.VIDEO_PROVIDERS["seedance"]["text_model"]
    image_model = config.VIDEO_PROVIDERS["seedance"]["image_model"]

    def __init__(self, api_key: str = None):
        api_key = api_key or config.get_env(config.VIDEO_PROVIDERS["seedance"]["env_key"])
        super().__init__(api_key)
        if not self.api_key:
            raise ValueError("Seedance 未配置 ARK_API_KEY")

    async def submit_task(self, prompt, image_url=None, last_image_url=None, **kwargs) -> str:
        content = [{"type": "text", "text": prompt}]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
        if last_image_url:
            content.append({"type": "image_url", "image_url": {"url": last_image_url}})

        model = self.image_model if (image_url or last_image_url) else self.text_model
        params = {
            "duration": kwargs.get("duration", 5),
            "resolution": kwargs.get("resolution", "720p"),
            "fps": kwargs.get("fps", 24),
        }
        if "aspect_ratio" in kwargs:
            params["aspect_ratio"] = kwargs["aspect_ratio"]

        payload = {"model": model, "content": content, "parameters": params}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/contents/generations/tasks",
                json=payload,
                headers=self._auth_header(self.api_key),
            )
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("id")
            if not task_id:
                raise VideoProviderError(f"Seedance 提交失败: {data}")
            return task_id

    async def query_task(self, task_id: str) -> Dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/contents/generations/tasks/{task_id}",
                headers=self._auth_header(self.api_key),
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "pending")
            if status == "succeeded":
                return {"status": "succeeded", "video_url": data.get("content", {}).get("video_url")}
            if status == "failed":
                return {"status": "failed", "error": data.get("error", "未知")}
            return {"status": status, "video_url": None}


# ==================== 可灵 Kling（JWT 鉴权）====================
class KlingProvider(VideoProvider):
    """快手可灵视频生成。使用 AK/SK 动态生成 JWT 鉴权。异步提交+轮询。"""

    name = "kling"
    base_url = config.VIDEO_PROVIDERS["kling"]["base_url"]
    text_model = config.VIDEO_PROVIDERS["kling"]["text_model"]

    def __init__(self, access_key: str = None, secret_key: str = None):
        self.access_key = access_key or config.get_env(config.VIDEO_PROVIDERS["kling"]["env_key_access"])
        self.secret_key = secret_key or config.get_env(config.VIDEO_PROVIDERS["kling"]["env_key_secret"])
        if not (self.access_key and self.secret_key):
            raise ValueError("可灵未配置 KLING_ACCESS_KEY / KLING_SECRET_KEY")

    def _jwt_token(self) -> str:
        """生成 JWT token（HS256）。"""
        header = {"alg": "HS256", "typ": "JWT"}
        now = int(time.time())
        payload = {"iss": self.access_key, "nbf": now - 5, "exp": now + 3600, "iat": now}

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header_b64 = b64url(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = b64url(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}"
        sig = hmac.new(self.secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
        sig_b64 = b64url(sig)
        return f"{signing_input}.{sig_b64}"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._jwt_token()}"}

    async def submit_task(self, prompt, image_url=None, last_image_url=None, **kwargs) -> str:
        if image_url or last_image_url:
            # 图生视频：需要先上传图片到可灵，返回 image_url（简化：用给定 url）
            endpoint = f"{self.base_url}/videos/image2video"
            model = self.text_model
            payload = {
                "model_name": model,
                "model_version": kwargs.get("model_version", "pro"),
                "prompt": prompt,
                "image": image_url,
                "duration": kwargs.get("duration", 5),
                "aspect_ratio": kwargs.get("aspect_ratio", "9:16"),
            }
            if last_image_url:
                payload["tail_image"] = last_image_url
        else:
            endpoint = f"{self.base_url}/videos/text2video"
            payload = {
                "model_name": self.text_model,
                "model_version": kwargs.get("model_version", "pro"),
                "prompt": prompt,
                "duration": kwargs.get("duration", 5),
                "aspect_ratio": kwargs.get("aspect_ratio", "9:16"),
            }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(endpoint, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise VideoProviderError(f"可灵提交失败: {data.get('message')}")
            return data.get("data", {}).get("task_id")

    async def query_task(self, task_id: str) -> Dict:
        # 判断是文生还是图生（简化：查询两个端点，取有结果的那个）
        endpoints = [
            f"{self.base_url}/videos/text2video/{task_id}",
            f"{self.base_url}/videos/image2video/{task_id}",
        ]
        async with httpx.AsyncClient(timeout=30) as client:
            for ep in endpoints:
                resp = await client.get(ep, headers=self._headers())
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == 0:
                    task_data = data.get("data", {})
                    status = task_data.get("task_status", "processing")
                    if status == "succeed":
                        return {"status": "succeeded", "video_url": task_data.get("task_result", {}).get("videos", [{}])[0].get("url")}
                    if status == "failed":
                        return {"status": "failed", "error": task_data.get("task_status_msg", "未知")}
                    return {"status": status, "video_url": None}
            return {"status": "pending", "video_url": None}


# ==================== 万相 Wan（阿里 DashScope）====================
class WanxProvider(VideoProvider):
    """阿里通义万相视频生成。需要 X-DashScope-Async: enable 头。异步提交+轮询。"""

    name = "wanx"
    base_url = config.VIDEO_PROVIDERS["wanx"]["base_url"]
    text_model = config.VIDEO_PROVIDERS["wanx"]["text_model"]
    image_model = config.VIDEO_PROVIDERS["wanx"]["image_model"]

    def __init__(self, api_key: str = None):
        api_key = api_key or config.get_env(config.VIDEO_PROVIDERS["wanx"]["env_key"])
        super().__init__(api_key)
        if not self.api_key:
            raise ValueError("万相未配置 DASHSCOPE_API_KEY")

    def _headers(self) -> Dict[str, str]:
        h = self._auth_header(self.api_key)
        h["X-DashScope-Async"] = "enable"
        h["Content-Type"] = "application/json"
        return h

    async def submit_task(self, prompt, image_url=None, last_image_url=None, **kwargs) -> str:
        model = self.image_model if (image_url or last_image_url) else self.text_model
        inp = {"prompt": prompt}
        if image_url:
            inp["img_url"] = image_url
        if last_image_url:
            inp["last_frame_url"] = last_image_url

        size_map = {
            "9:16": "720*1280",
            "16:9": "1280*720",
            "1:1": "1024*1024",
        }
        params = {
            "size": size_map.get(kwargs.get("aspect_ratio", "9:16"), "720*1280"),
            "duration": kwargs.get("duration", 5),
        }

        payload = {"model": model, "input": inp, "parameters": params}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("output", {}).get("task_id")
            if not task_id:
                raise VideoProviderError(f"万相提交失败: {data}")
            return task_id

    async def query_task(self, task_id: str) -> Dict:
        query_url = "https://dashscope.aliyuncs.com/api/v1/tasks/" + task_id
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(query_url, headers=self._auth_header(self.api_key))
            resp.raise_for_status()
            data = resp.json()
            status = data.get("output", {}).get("task_status", "PENDING")
            if status == "SUCCEEDED":
                videos = data.get("output", {}).get("video_url") or []
                url = videos[0] if isinstance(videos, list) else videos
                return {"status": "succeeded", "video_url": url}
            if status == "FAILED":
                return {"status": "failed", "error": data.get("output", {}).get("message", "未知")}
            return {"status": "pending" if status == "PENDING" else "running", "video_url": None}


# ==================== 智谱 CogVideoX ====================
class CogVideoXProvider(VideoProvider):
    """智谱 CogVideoX 视频生成。异步提交+轮询。"""

    name = "cogvideox"
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    text_model = config.VIDEO_PROVIDERS["cogvideox"]["text_model"]

    def __init__(self, api_key: str = None):
        api_key = api_key or config.get_env(config.VIDEO_PROVIDERS["cogvideox"]["env_key"])
        super().__init__(api_key)
        if not self.api_key:
            raise ValueError("CogVideoX 未配置 ZHIPU_API_KEY")

    async def submit_task(self, prompt, image_url=None, last_image_url=None, **kwargs) -> str:
        inp = {"prompt": prompt}
        if image_url:
            inp["image_url"] = image_url
        if last_image_url:
            inp["last_image_url"] = last_image_url
        payload = {
            "model": self.text_model,
            "input": inp,
            "parameters": {
                "quality": kwargs.get("quality", "quality"),
                "with_audio": kwargs.get("with_audio", True),
                "size": kwargs.get("resolution", "720P"),
                "fps": kwargs.get("fps", 30),
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/videos/generations",
                json=payload,
                headers=self._auth_header(self.api_key),
            )
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("id")
            if not task_id:
                raise VideoProviderError(f"CogVideoX 提交失败: {data}")
            return task_id

    async def query_task(self, task_id: str) -> Dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/videos/retrieve/{task_id}",
                headers=self._auth_header(self.api_key),
            )
            resp.raise_for_status()
            data = resp.json()
            task_status = data.get("task_status", "PROCESSING")
            if task_status == "SUCCESS":
                videos = data.get("video_result", [])
                url = videos[0].get("url") if videos else None
                return {"status": "succeeded", "video_url": url}
            if task_status == "FAIL":
                return {"status": "failed", "error": data.get("fail_reason", "未知")}
            return {"status": "running", "video_url": None}


# ==================== 工厂 ====================
class VideoProviderFactory:
    """按 provider 名创建视频 provider 实例。"""

    @staticmethod
    def create(provider: str, **kwargs) -> VideoProvider:
        providers = {
            "seedance": SeedanceProvider,
            "kling": KlingProvider,
            "wanx": WanxProvider,
            "cogvideox": CogVideoXProvider,
        }
        cls = providers.get(provider)
        if not cls:
            raise ValueError(f"未知视频 provider: {provider}")
        return cls(**kwargs)

    @staticmethod
    def list_available():
        """返回视频 provider 配置状态（供前端展示）。"""
        result = []
        for k, v in config.VIDEO_PROVIDERS.items():
            result.append({
                "key": k,
                "name": v["name"],
                "desc": v["desc"],
                "configured": config.is_video_provider_configured(k),
            })
        return result
