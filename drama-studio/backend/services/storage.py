"""
JSON 文件持久化层。

沙箱无数据库，用 JSON 文件存储项目状态、中间产物信息、任务进度。
每个项目一个目录：data/<project_id>/
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from .. import config

logger = logging.getLogger("drama-studio.services.storage")


class ProjectStore:
    """项目持久化存储。"""

    def __init__(self):
        self.base = config.DATA_DIR
        self.base.mkdir(exist_ok=True)

    # ---------- 路径 ----------
    def project_dir(self, project_id: str) -> Path:
        return self.base / project_id

    def file_path(self, project_id: str, rel_path: str) -> Path:
        return self.project_dir(project_id) / rel_path

    def ensure_dir(self, project_id: str, rel_dir: str = "") -> Path:
        d = self.project_dir(project_id)
        if rel_dir:
            d = d / rel_dir
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---------- 项目元数据 ----------
    def create_project(self, project_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        d = self.project_dir(project_id)
        d.mkdir(parents=True, exist_ok=True)
        state = {
            "id": project_id,
            "status": "created",
            "current_stage": 0,
            "meta": meta,
            "stages": {},
            "artifacts": {},
            "logs": [],
            "created_at": None,
            "updated_at": None,
        }
        self.save_state(project_id, state)
        return state

    def save_state(self, project_id: str, state: Dict[str, Any]) -> None:
        import datetime
        state["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        with open(self.file_path(project_id, "state.json"), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def load_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        p = self.file_path(project_id, "state.json")
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_projects(self) -> list:
        projects = []
        for d in self.base.iterdir():
            if d.is_dir() and (d / "state.json").exists():
                try:
                    with open(d / "state.json", "r", encoding="utf-8") as f:
                        st = json.load(f)
                    projects.append({
                        "id": st.get("id"),
                        "status": st.get("status"),
                        "title": st.get("meta", {}).get("theme", "未命名"),
                        "updated_at": st.get("updated_at"),
                    })
                except Exception:
                    continue
        return projects

    # ---------- 中间产物 ----------
    def save_artifact(self, project_id: str, stage: str, name: str, content: Any, ext: str = "json"):
        """保存结构化中间产物（如 storyboard.json、script.md）。"""
        rel = f"artifacts/{stage}/{name}"
        p = self.file_path(project_id, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            with open(p, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
        return str(p)

    def load_artifact(self, project_id: str, rel_path: str) -> Optional[Any]:
        p = self.file_path(project_id, rel_path)
        if not p.exists():
            return None
        if p.suffix == ".json":
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        with open(p, "r", encoding="utf-8") as f:
            return f.read()

    # ---------- 日志 ----------
    def log(self, project_id: str, stage: str, message: str):
        import datetime
        state = self.load_state(project_id)
        if not state:
            return
        state.setdefault("logs", []).append({
            "stage": stage,
            "message": message,
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
        })
        self.save_state(project_id, state)

    def delete_project(self, project_id: str):
        d = self.project_dir(project_id)
        if d.exists():
            shutil.rmtree(d)


# 全局单例
store = ProjectStore()
