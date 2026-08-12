"""
统一 LLM Provider 调用层。

provider 分两类：
  - "openai" 风格：兼容 OpenAI /v1/chat/completions 格式，用 AsyncOpenAI 调用
    （openai / deepseek / qwen / moonshot / zhipu / doubao）
  - "anthropic" 风格：使用 Anthropic 原生 /v1/messages 接口，用 httpx 直连
    （claude）

由 config.LLM_PROVIDERS[<key>]["api_style"] 决定走哪条路径，LLMFactory 自动路由。
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional

import httpx
from openai import AsyncOpenAI

from .. import config

logger = logging.getLogger("drama-studio.providers.llm")


class LLMProvider:
    """LLM provider 抽象基类。子类实现具体 chat 调用。"""

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

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """对话（非流式），返回纯文本。子类实现。"""
        raise NotImplementedError

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


class OpenAICompatLLMProvider(LLMProvider):
    """OpenAI 兼容 provider（openai / deepseek / qwen / moonshot / zhipu / doubao）。"""

    def __init__(self, provider: str = None, api_key: str = None, model: str = None):
        super().__init__(provider, api_key, model)
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.cfg["base_url"])

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return resp.choices[0].message.content or ""


class AnthropicLLMProvider(LLMProvider):
    """Anthropic Claude provider，走原生 /v1/messages 接口。"""

    def __init__(self, provider: str = None, api_key: str = None, model: str = None):
        super().__init__(provider, api_key, model)
        self.base_url = self.cfg["base_url"].rstrip("/")
        self.anthropic_version = self.cfg.get("anthropic_version", "2023-06-01")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = 1024,
        **kwargs,
    ) -> str:
        # Claude Messages API 不支持 system 角色混在 messages 里，需单独提取
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        conversation = [m for m in messages if m.get("role") != "system"]

        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or 1024,
            "messages": conversation,
            "temperature": temperature,
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/messages", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

        # 拼装所有 text 段
        text = "".join(
            p.get("text", "") for p in data.get("content", []) if p.get("type") == "text"
        )
        return text


class LLMFactory:
    """按 provider 创建 LLMProvider 实例（自动按 api_style 路由）。"""

    @staticmethod
    def create(provider: str = None, api_key: str = None, model: str = None) -> LLMProvider:
        cfg = config.LLM_PROVIDERS.get(provider)
        if not cfg:
            raise ValueError(f"未知 LLM provider: {provider}")
        style = cfg.get("api_style", "openai")
        if style == "anthropic":
            return AnthropicLLMProvider(provider=provider, api_key=api_key, model=model)
        return OpenAICompatLLMProvider(provider=provider, api_key=api_key, model=model)

    @staticmethod
    def list_available():
        """返回已配置 API Key 的 provider 列表（供前端展示）。"""
        return [
            {
                "key": k,
                "name": v["name"],
                "model": v["default_model"],
                "desc": v["desc"],
                "style": v.get("api_style", "openai"),
                "configured": config.is_provider_configured(k),
            }
            for k, v in config.LLM_PROVIDERS.items()
        ]
