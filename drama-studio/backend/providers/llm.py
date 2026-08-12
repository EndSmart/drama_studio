"""
统一 LLM Provider 调用层。

所有支持的 provider 均兼容 OpenAI /v1/chat/completions 格式，
通过 base_url + api_key 切换。后端只需一套调用逻辑。
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional

from openai import AsyncOpenAI

from .. import config

logger = logging.getLogger("drama-studio.providers.llm")


class LLMProvider:
    """OpenAI 兼容统一 LLM 调用封装。"""

    def __init__(self, provider: str = None, api_key: str = None, model: str = None):
        cfg = config.LLM_PROVIDERS.get(provider)
        if not cfg:
            raise ValueError(f"未知 LLM provider: {provider}")
        self.provider = provider
        self.cfg = cfg
        # API Key 优先级：传入 > 环境变量
        self.api_key = api_key or config.get_env(cfg["env_key"])
        if not self.api_key:
            raise ValueError(
                f"LLM provider '{provider}' 未配置 API Key。"
                f"请设置环境变量 {cfg['env_key']} 或在请求中传入 api_key。"
            )
        self.model = model or cfg["default_model"]
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=cfg["base_url"])

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """同步对话（非流式），返回纯文本。"""
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.4,
        **kwargs,
    ) -> str:
        """请求 JSON 输出（通过 system 提示词约束），返回原始 JSON 字符串。"""
        sys_prompt = (
            "你是一个严格遵循 JSON 输出格式的助手。"
            "只输出合法的 JSON，不要包含任何多余文字、解释或 Markdown 代码块标记。"
        )
        msg = [{"role": "system", "content": sys_prompt}] + messages
        return await self.chat(msg, temperature=temperature, **kwargs)


class LLMFactory:
    """按 provider 创建 LLMProvider 实例。"""

    @staticmethod
    def create(provider: str = None, api_key: str = None, model: str = None) -> LLMProvider:
        return LLMProvider(provider=provider, api_key=api_key, model=model)

    @staticmethod
    def list_available():
        """返回已配置 API Key 的 provider 列表（供前端展示）。"""
        return [
            {
                "key": k,
                "name": v["name"],
                "model": v["default_model"],
                "desc": v["desc"],
                "configured": config.is_provider_configured(k),
            }
            for k, v in config.LLM_PROVIDERS.items()
        ]
