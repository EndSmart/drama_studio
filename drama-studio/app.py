"""
drama-studio FastAPI 入口。

启动方式：
    uvicorn app:app --host 0.0.0.0 --port $PORT

必须监听 $PORT 环境变量并绑定 0.0.0.0（发布平台要求）。
"""

import logging
import os
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend import auth

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("drama-studio")

app = FastAPI(title="Drama Studio — 短剧制作智能体集群", version="1.0.0")

# CORS（允许跨域，便于开发调试）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 登录鉴权中间件 ============
# 公开路径：首页、健康检查、登录/登出、provider 信息查询、静态资源。
# 其余 /api 与 /ws 均要求携带有效的会话 Cookie。
PUBLIC_PATHS = {
    "/",
    "/ping",
    "/api/health",
    "/api/login",
    "/api/logout",
    "/api/providers",
}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path

        # 静态资源直接放行
        if path.startswith(("/static", "/css", "/js")):
            return await call_next(request)

        # 公开路径放行
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # 仅对 /api 路径做会话校验
        if path.startswith("/api"):
            token = request.cookies.get(auth.SESSION_COOKIE)
            username = auth.verify_session_token(token)
            if not username:
                return JSONResponse(
                    {"detail": "未登录或登录已过期"}, status_code=401
                )
            request.state.user = username
            return await call_next(request)

        # 其它未知路径默认放行（首页已在公开列表中）
        return await call_next(request)


app.add_middleware(AuthMiddleware)


# 注册路由
from backend.routes import api as api_router
from backend.routes import websocket as ws_router

app.include_router(api_router.router, prefix="")
app.include_router(ws_router.router, prefix="")


# 静态前端（同源托管，避免 CORS）
FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# 托管前端静态资源
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
# 兼容 js/css 直接访问
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")


@app.get("/ping")
async def ping():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
