"""
drama-studio FastAPI 入口。

启动方式：
    uvicorn app:app --host 0.0.0.0 --port $PORT

必须监听 $PORT 环境变量并绑定 0.0.0.0（发布平台要求）。
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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
