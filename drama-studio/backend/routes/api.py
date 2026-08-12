"""
REST API 路由。

提供：
- 项目管理（创建/查询/列表/删除）
- 流水线执行（完整流水线 / 单个 Agent）
- 中间产物访问
- 成片下载
- Provider 信息查询
"""

import uuid
import logging
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from ..services.storage import store
from ..services.pipeline import pipeline_service
from ..services.interactive import interactive_service
from ..providers.llm import LLMFactory
from ..providers.video import VideoProviderFactory
from ..providers.image import ImageProviderFactory
from .. import auth, config

logger = logging.getLogger("drama-studio.routes.api")

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok", "service": "drama-studio"}


# ============ 登录认证 ============
def _current_username(request: Request) -> str:
    token = request.cookies.get(auth.SESSION_COOKIE)
    username = auth.verify_session_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return username


def _require_admin(request: Request) -> dict:
    username = _current_username(request)
    user = auth.get_user(username)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


@router.post("/login")
async def login(body: Dict, response: Response):
    """登录。成功后在 HttpOnly Cookie 中写入会话 token。"""
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = auth.authenticate(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth.create_session_token(user["username"])
    response.set_cookie(
        key=auth.SESSION_COOKIE,
        value=token,
        httponly=True,
        max_age=auth.SESSION_MAX_AGE,
        path="/",
        samesite="lax",
    )
    return {"username": user["username"], "role": user["role"]}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me")
async def me(request: Request):
    username = _current_username(request)
    user = auth.get_user(username)
    return {"username": user["username"], "role": user["role"]}


# ============ 用户管理（仅管理员） ============
@router.get("/users")
async def get_users(request: Request):
    _require_admin(request)
    return {"users": auth.list_users()}


@router.post("/users")
async def add_user(body: Dict, request: Request):
    _require_admin(request)
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role") or "user"
    try:
        user = auth.create_user(username, password, role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "user": user}


@router.delete("/users/{username}")
async def remove_user(username: str, request: Request):
    _require_admin(request)
    current = _current_username(request)
    if username == current:
        raise HTTPException(status_code=400, detail="不能删除当前登录的账户")
    try:
        auth.delete_user(username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


# ---------- Provider 信息 ----------
@router.get("/providers")
async def get_providers():
    return {
        "llm": LLMFactory.list_available(),
        "video": VideoProviderFactory.list_available(),
        "image": ImageProviderFactory.list_available(),
        "defaults": {
            "llm": config.DEFAULT_CONFIG["llm_provider"],
            "video": config.DEFAULT_CONFIG["video_provider"],
            "image": config.DEFAULT_CONFIG["image_provider"],
        },
    }


# ---------- 项目管理 ----------
@router.post("/projects")
async def create_project(body: Dict):
    """创建项目。body: {theme, config:{...}}"""
    theme = body.get("theme", "").strip()
    if not theme:
        raise HTTPException(400, "主题不能为空")

    project_id = uuid.uuid4().hex[:12]
    cfg = body.get("config", {})
    meta = {
        "theme": theme,
        "config": {**config.DEFAULT_CONFIG, **cfg},
    }
    state = store.create_project(project_id, meta)
    import datetime
    state["created_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    store.save_state(project_id, state)

    return {"id": project_id, "status": "created", "theme": theme}


@router.get("/projects")
async def list_projects():
    return {"projects": store.list_projects()}


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    state = store.load_state(project_id)
    if not state:
        raise HTTPException(404, "项目不存在")
    return state


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    store.delete_project(project_id)
    return {"status": "deleted"}


# ---------- 流水线执行 ----------
@router.post("/projects/{project_id}/run")
async def run_pipeline(project_id: str, body: Dict):
    """运行完整流水线。body: {llm_provider, api_key, config:{...}}"""
    state = store.load_state(project_id)
    if not state:
        raise HTTPException(404, "项目不存在")

    llm_provider = body.get("llm_provider") or config.DEFAULT_CONFIG["llm_provider"]
    api_key = body.get("api_key")
    config_override = body.get("config", {})

    try:
        result = await pipeline_service.run_pipeline(
            project_id, llm_provider, api_key=api_key, config_override=config_override
        )
        return {"status": "started", "project_id": project_id}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- 交互式（分步精修）执行 ----------
@router.get("/projects/{project_id}/stages")
async def get_stage_defs(project_id: str):
    """返回交互式阶段的顺序与定义（供前端渲染步骤条）。"""
    state = store.load_state(project_id)
    if not state:
        raise HTTPException(404, "项目不存在")
    return {
        "stages": interactive_service.stage_defs(),
        "order": interactive_service.stage_order(),
    }


@router.post("/projects/{project_id}/stage")
async def run_stage(project_id: str, body: Dict):
    """
    交互式分阶段执行。

    body:
      stage:   阶段 key（screenwriter / storyboarder / character_designer / video_producer / editor）
      action:  "run"    —— 运行该阶段（生成/重新生成）
               "refine" —— 按 instruction 润色重生成
               "save"   —— 保存用户对产物的编辑（content 字段）
      llm_provider / api_key / video_provider / video_api_key / image_provider / image_api_key
      config:  {...}                      # 覆盖配置
      instruction: "润色意见..."          # refine 时使用
      content: "用户编辑后的文本/JSON"     # save 时使用
    """
    state = store.load_state(project_id)
    if not state:
        raise HTTPException(404, "项目不存在")

    stage = body.get("stage")
    action = (body.get("action") or "run").lower()

    providers = {
        "llm_provider": body.get("llm_provider") or config.DEFAULT_CONFIG["llm_provider"],
        "api_key": body.get("api_key"),
        "video_provider": body.get("video_provider") or config.DEFAULT_CONFIG["video_provider"],
        "video_api_key": body.get("video_api_key"),
        "image_provider": body.get("image_provider") or config.DEFAULT_CONFIG["image_provider"],
        "image_api_key": body.get("image_api_key"),
    }
    config_override = body.get("config", {})
    instruction = body.get("instruction")
    content = body.get("content")

    try:
        if action == "save":
            if content is None:
                raise ValueError("save 操作需要提供 content")
            envelope = await interactive_service.save(project_id, stage, content)
        elif action in ("run", "refine"):
            envelope = await interactive_service.execute(
                project_id, stage, providers,
                config_override=config_override,
                instruction=instruction if action == "refine" else None,
            )
        else:
            raise ValueError(f"未知 action: {action}")
        return {"status": "ok", "action": action, "artifact": envelope}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/projects/{project_id}/agents/{agent_name}/run")
async def run_single_agent(project_id: str, agent_name: str, body: Dict):
    """单独运行某个 Agent（调试/分步执行）。"""
    state = store.load_state(project_id)
    if not state:
        raise HTTPException(404, "项目不存在")

    llm_provider = body.get("llm_provider") or config.DEFAULT_CONFIG["llm_provider"]
    api_key = body.get("api_key")
    config_override = body.get("config", {})

    # 确保 director 先生成（若尚未执行）
    try:
        if agent_name != "director":
            brief = store.load_artifact(project_id, "artifacts/director/creative_brief.json")
            if not brief:
                await pipeline_service.run_agent(project_id, "director", llm_provider, api_key, config_override)

        result = await pipeline_service.run_agent(project_id, agent_name, llm_provider, api_key, config_override)
        return {"status": "completed", "result": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- 产物访问 ----------
@router.get("/projects/{project_id}/artifacts")
async def list_artifacts(project_id: str):
    state = store.load_state(project_id)
    if not state:
        raise HTTPException(404, "项目不存在")

    artifacts_dir = store.project_dir(project_id) / "artifacts"
    files = []
    if artifacts_dir.exists():
        for p in sorted(artifacts_dir.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(store.project_dir(project_id)))
                files.append({
                    "path": rel,
                    "size": p.stat().st_size,
                    "name": p.name,
                })
    return {"artifacts": files}


@router.get("/projects/{project_id}/artifacts/content")
async def get_artifact_content(project_id: str, path: str = Query(...)):
    """读取中间产物文本内容。path 如 artifacts/storyboarder/storyboard.json"""
    full = store.project_dir(project_id) / path
    if not full.exists():
        raise HTTPException(404, "产物不存在")
    try:
        content = full.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(400, "无法读取二进制文件")
    return {"path": path, "content": content}


@router.get("/projects/{project_id}/final")
async def get_final_video(project_id: str):
    """获取最终成片文件。"""
    state = store.load_state(project_id)
    if not state:
        raise HTTPException(404, "项目不存在")
    final_path = store.project_dir(project_id) / "artifacts" / "editor" / "final_drama.mp4"
    if not final_path.exists():
        raise HTTPException(404, "成片尚未生成")
    return FileResponse(
        final_path,
        media_type="video/mp4",
        filename=f"drama_{project_id}.mp4",
    )
