"""
OpenClaw Manager - 主应用入口
"""
import os
from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlalchemy.orm import Session

from database import get_db, AgentInstance, Project, Template
from docker_service import DockerService
from config import settings

# 导入路由
from agent_api import router as agent_router
from project_api import router as project_router

# 创建应用
app = FastAPI(
    title=settings.APP_NAME,
    description="OpenClaw 多实例 Docker 管理平台",
    version=settings.APP_VERSION
)

# 挂载路由
app.include_router(agent_router)
app.include_router(project_router)

# 静态文件和模板
templates_directory = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_directory)

# Docker 服务实例
docker_service = DockerService()


# ============ Web 界面 ============

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """主仪表盘"""
    return templates.TemplateResponse("index.html", {"request": request})


# ============ 统计 API ============

@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """获取系统统计信息"""
    # Docker 统计
    containers = docker_service.list_all_containers()
    running = sum(1 for c in containers if c["state"] == "running")
    
    # 数据库统计
    total_agents = db.query(AgentInstance).count()
    running_agents = db.query(AgentInstance).filter(AgentInstance.status == "running").count()
    total_projects = db.query(Project).count()
    total_templates = db.query(Template).count()
    
    return {
        "docker": {
            "total_containers": len(containers),
            "running_containers": running,
            "stopped_containers": len(containers) - running
        },
        "agents": {
            "total": total_agents,
            "running": running_agents,
            "creating": db.query(AgentInstance).filter(AgentInstance.status == "creating").count(),
            "stopped": db.query(AgentInstance).filter(AgentInstance.status == "stopped").count(),
            "error": db.query(AgentInstance).filter(AgentInstance.status == "error").count()
        },
        "projects": {
            "total": total_projects,
            "active": db.query(Project).filter(Project.status == "active").count(),
            "archived": db.query(Project).filter(Project.status == "archived").count()
        },
        "templates": total_templates
    }


@app.get("/api/ui/overview")
async def get_overview_content():
    """获取总览内容"""
    try:
        with open(os.path.join(templates_directory, "overview.js"), "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except:
        return {"content": "// Overview content not found"}

@app.get("/api/ui/templates")
async def get_templates_content():
    """获取模板内容"""
    try:
        with open(os.path.join(templates_directory, "templates.js"), "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except:
        return {"content": "// Templates content not found"}

@app.get("/api/ui/projects")
async def get_projects_content():
    """获取项目内容"""
    try:
        with open(os.path.join(templates_directory, "projects.js"), "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except:
        return {"content": "// Projects content not found"}


@app.get("/api/containers/all")
async def get_all_containers():
    """获取所有 Docker 容器"""
    return docker_service.list_all_containers()


@app.get("/api/docker/images")
async def get_local_images():
    """获取本地 Docker 镜像列表"""
    return docker_service.list_local_images()


# ============ 健康检查 ============

@app.get("/api/health")
async def health_check():
    """服务健康检查"""
    docker_ok = docker_service.client is not None
    try:
        docker_service.client.ping()
        docker_ok = True
    except:
        docker_ok = False
    
    return {
        "status": "healthy" if docker_ok else "degraded",
        "docker_connected": docker_ok,
        "version": settings.APP_VERSION
    }


# ============ 启动入口 ============

if __name__ == "__main__":
    import uvicorn
    
    # 确保数据目录存在
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    
    uvicorn.run(app, host="0.0.0.0", port=settings.SERVER_PORT)
