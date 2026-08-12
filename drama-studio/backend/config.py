"""
drama-studio 配置模块。

集中管理：
1. LLM provider 配置表（OpenAI 兼容，全部可通过 base_url + api_key 切换）
2. 视频生成 provider 配置表
3. 图像生成 provider 配置
4. 项目默认参数

所有 API Key 优先从环境变量读取，其次由前端请求传入（存于运行时，不进代码库）。
"""

import os
from pathlib import Path

# ============ 基础路径 ============
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ============ LLM Provider 配置表 ============
# api_style:
#   "openai"    —— 兼容 OpenAI /v1/chat/completions 格式（用 AsyncOpenAI 调用）
#   "anthropic" —— 使用 Anthropic 原生 /v1/messages 接口（用 httpx 直连）
LLM_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
        "api_style": "openai",
        "desc": "OpenAI GPT 系列，通用能力强，亦可用于图像生成",
    },
    "claude": {
        "name": "Anthropic Claude",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-sonnet-latest",
        "env_key": "ANTHROPIC_API_KEY",
        "api_style": "anthropic",
        "anthropic_version": "2023-06-01",
        "desc": "Anthropic Claude，长上下文、强推理（原生 Messages API）",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        "env_key": "DEEPSEEK_API_KEY",
        "api_style": "openai",
        "desc": "DeepSeek V4，性价比高，支持 Thinking 模式",
    },
    "qwen": {
        "name": "阿里千问 Qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen3.8-max",
        "env_key": "DASHSCOPE_API_KEY",
        "api_style": "openai",
        "desc": "阿里百炼平台，OpenAI 兼容",
    },
    "moonshot": {
        "name": "Kimi Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "kimi-k3",
        "env_key": "MOONSHOT_API_KEY",
        "api_style": "openai",
        "desc": "月之暗面 Kimi，长上下文",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "default_model": "glm-5.2",
        "env_key": "ZHIPU_API_KEY",
        "api_style": "openai",
        "desc": "智谱清言 GLM，多模态",
    },
    "doubao": {
        "name": "火山豆包 Doubao",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "ep-2025xxxxxxxxxxxx",  # 需在方舟控制台创建 Endpoint
        "env_key": "ARK_API_KEY",
        "api_style": "openai",
        "desc": "火山方舟，model 填 Endpoint ID (ep-xxx)",
        "requires_endpoint": True,
    },
}

# ============ 视频生成 Provider 配置表 ============
# 各家异步流程不同，无法用 OpenAI 格式统一，走统一抽象接口
VIDEO_PROVIDERS = {
    "seedance": {
        "name": "火山 Seedance",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "text_model": "seedance-2.0-text-to-video",
        "image_model": "seedance-2.0-image-to-video",
        "env_key": "ARK_API_KEY",
        "auth": "bearer",
        "desc": "字节跳动视频生成，多模态输入，支持文/图生视频",
    },
    "kling": {
        "name": "快手可灵 Kling",
        "base_url": "https://api-beijing.klingai.com/v1",
        "text_model": "kling-v3",
        "image_model": "kling-v3",
        "env_key_access": "KLING_ACCESS_KEY",
        "env_key_secret": "KLING_SECRET_KEY",
        "auth": "jwt",  # 需要 AK/SK 动态生成 JWT
        "desc": "快手可灵，JWT 鉴权，需 Access Key + Secret Key",
    },
    "wanx": {
        "name": "阿里万相 Wan",
        "base_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis",
        "text_model": "wan2.6-t2v",
        "image_model": "wan2.6-i2v",
        "env_key": "DASHSCOPE_API_KEY",
        "auth": "bearer",
        "async_header": "enable",  # X-DashScope-Async: enable
        "desc": "阿里通义万相，支持多镜头叙事",
    },
    "cogvideox": {
        "name": "智谱 CogVideoX",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/videos/generations",
        "text_model": "cogvideox-3",
        "image_model": "cogvideox-3",
        "env_key": "ZHIPU_API_KEY",
        "auth": "bearer",
        "desc": "智谱清言 CogVideoX，图生视频支持首尾帧",
    },
}

# ============ 图像生成 Provider ============
IMAGE_PROVIDERS = {
    "openai": {
        "name": "OpenAI 图像生成",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-image-1",
        "env_key": "OPENAI_API_KEY",
        "auth": "bearer",
        "desc": "OpenAI gpt-image-1 / DALL·E 3 文生图，支持图生图编辑（image 编辑）",
    },
    "wanx": {
        "name": "阿里通义万相",
        "base_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
        "default_model": "wanx2.1-t2i-plus",
        "env_key": "DASHSCOPE_API_KEY",
        "auth": "bearer",
        "async_header": "enable",
        "desc": "文生图 + 图生图（支持 input.image 参考图）",
    },
}

# ============ 默认项目参数 ============
DEFAULT_CONFIG = {
    "target_duration": 60,        # 目标时长（秒）
    "shot_duration": 5,           # 单镜头默认时长（秒）
    "aspect_ratio": "9:16",       # 竖屏短剧
    "resolution": "720p",         # 视频分辨率
    "llm_provider": "openai",     # 默认 LLM provider（可选 openai / claude / deepseek / qwen ...）
    "video_provider": "seedance", # 默认视频 provider（可选 seedance / kling / wanx / cogvideox）
    "image_provider": "wanx",     # 默认图像 provider（可选 wanx / openai）
    "style": "cinematic",         # 视觉风格
    "episodes": 1,                # 集数
}


def get_env(key):
    """从环境变量读取配置，返回 None 表示未配置。"""
    return os.environ.get(key)


def is_provider_configured(provider_key):
    """检查某 LLM provider 是否已在环境变量中配置 API Key。"""
    cfg = LLM_PROVIDERS.get(provider_key)
    if not cfg:
        return False
    return bool(get_env(cfg["env_key"]))


def is_video_provider_configured(provider_key):
    """检查某视频 provider 是否已配置。"""
    cfg = VIDEO_PROVIDERS.get(provider_key)
    if not cfg:
        return False
    if cfg["auth"] == "jwt":
        return bool(get_env(cfg["env_key_access"]) and get_env(cfg["env_key_secret"]))
    return bool(get_env(cfg["env_key"]))


def is_image_provider_configured(provider_key):
    """检查某图像 provider 是否已配置（环境变量中存在 API Key）。"""
    cfg = IMAGE_PROVIDERS.get(provider_key)
    if not cfg:
        return False
    return bool(get_env(cfg["env_key"]))
