"""
项目 API - 主智能体 + 专有智能体编排
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from database import get_db, Project, AgentInstance, Template, PortAllocation
from docker_service import PortPoolManager
from audit_service import AuditService
from agent_api import _create_container_task

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ============ Pydantic 模型 ============

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    template_id: Optional[str] = None  # 主智能体模板
    agent_templates: Optional[List[str]] = None  # 专有智能体模板列表
    project_config: Optional[Dict[str, Any]] = None  # 项目级统一配置

class ProjectConfigUpdate(BaseModel):
    project_config: Dict[str, Any] = Field(..., description="项目级配置策略")

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    main_agent_id: Optional[str]
    project_config: Optional[Dict]
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ProjectDetailResponse(ProjectResponse):
    agents: List[Dict[str, Any]] = []


# ============ 项目 API ============

@router.post("", response_model=ProjectResponse)
def create_project(project: ProjectCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """创建项目 - 自动生成主智能体 + N个专有智能体"""
    
    project_id = str(uuid.uuid4())
    
    # 1. 创建主智能体
    port_manager = PortPoolManager(db)
    main_agent_port = port_manager.allocate_port("")
    if not main_agent_port:
        raise HTTPException(status_code=500, detail="端口池已耗尽")
    
    main_agent_id = str(uuid.uuid4())
    main_container_name = f"openclaw-main-{main_agent_id[:8]}"
    
    # 获取主智能体模板
    main_image = "openclaw/openclaw:latest"
    main_config = {}
    if project.template_id:
        template = db.query(Template).filter(Template.id == project.template_id).first()
        if template:
            main_image = template.image
            main_config = template.default_config or {}
    
    # 应用项目级配置
    if project.project_config:
        main_config.update(project.project_config)
    
    main_agent = AgentInstance(
        id=main_agent_id,
        name=f"{project.name}-main",
        template_id=project.template_id,
        host_port=main_agent_port,
        image=main_image,
        status="creating",
        config=main_config
    )
    db.add(main_agent)
    
    # 更新端口分配
    port_alloc = db.query(PortAllocation).filter_by(port=main_agent_port).first()
    if port_alloc:
        port_alloc.agent_id = main_agent_id
    
    # 2. 创建专有智能体
    agent_ids = []
    for idx, template_id in enumerate(project.agent_templates or []):
        agent_port = port_manager.allocate_port("")
        if not agent_port:
            break  # 端口不足，停止创建
        
        agent_id = str(uuid.uuid4())
        container_name = f"openclaw-agent-{agent_id[:8]}"
        
        # 获取模板
        agent_image = "openclaw/openclaw:latest"
        agent_config = {}
        template = db.query(Template).filter(Template.id == template_id).first()
        if template:
            agent_image = template.image
            agent_config = template.default_config or {}
        
        # 应用项目级配置
        if project.project_config:
            agent_config.update(project.project_config)
        
        agent = AgentInstance(
            id=agent_id,
            name=f"{project.name}-agent-{idx+1}",
            template_id=template_id,
            host_port=agent_port,
            image=agent_image,
            status="creating",
            config=agent_config
        )
        db.add(agent)
        agent_ids.append(agent_id)
        
        # 更新端口分配
        port_alloc = db.query(PortAllocation).filter_by(port=agent_port).first()
        if port_alloc:
            port_alloc.agent_id = agent_id
        
        # 后台创建容器
        background_tasks.add_task(
            _create_container_task, agent_id, container_name, agent_image, agent_port, agent_config
        )
    
    # 3. 创建项目
    db_project = Project(
        id=project_id,
        name=project.name,
        description=project.description,
        main_agent_id=main_agent_id,
        project_config=project.project_config,
        status="active"
    )
    db.add(db_project)
    db.commit()
    
    # 更新主智能体的 project_id
    main_agent.project_id = project_id
    db.commit()
    
    # 更新专有智能体的 project_id
    for agent_id in agent_ids:
        agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
        if agent:
            agent.project_id = project_id
    db.commit()
    
    # 后台创建主容器
    background_tasks.add_task(
        _create_container_task, main_agent_id, main_container_name, main_image, main_agent_port, main_config
    )
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="create",
        entity_type="project",
        entity_id=project_id,
        description=f"创建项目: {project.name} (主智能体 + {len(agent_ids)} 个专有智能体)"
    )
    
    return db_project

@router.get("", response_model=List[ProjectResponse])
def list_projects(status: Optional[str] = None, db: Session = Depends(get_db)):
    """列出所有项目"""
    query = db.query(Project)
    if status:
        query = query.filter(Project.status == status)
    return query.all()

@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    """获取项目详情"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 获取项目下的所有智能体
    agents = db.query(AgentInstance).filter(AgentInstance.project_id == project_id).all()
    agent_list = [{
        "id": a.id,
        "name": a.name,
        "status": a.status,
        "host_port": a.host_port,
        "console_url": f"http://127.0.0.1:{a.host_port}" if a.host_port else None
    } for a in agents]
    
    result = ProjectDetailResponse.from_orm(project)
    result.agents = agent_list
    return result

@router.post("/{project_id}/config")
def apply_project_config(project_id: str, config: ProjectConfigUpdate, db: Session = Depends(get_db)):
    """批量应用项目级配置到所有智能体"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 更新项目配置
    old_config = project.project_config
    project.project_config = config.project_config
    db.commit()
    
    # 获取所有智能体
    agents = db.query(AgentInstance).filter(AgentInstance.project_id == project_id).all()
    
    # 批量应用配置
    from openclaw_service import OpenClawService
    oc_service = OpenClawService()
    
    results = []
    for agent in agents:
        if agent.container_id:
            # 合并项目配置到实例配置
            new_config = agent.config or {}
            new_config.update(config.project_config)
            
            result = oc_service.apply_config_to_container(agent.container_id, new_config)
            if result["success"]:
                agent.config = new_config
            results.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "success": result["success"]
            })
    
    db.commit()
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="config_change",
        entity_type="project",
        entity_id=project_id,
        description=f"批量更新项目配置: {project.name}",
        old_value=old_config,
        new_value=config.project_config,
        project_id=project_id
    )
    
    return {
        "success": True,
        "project_id": project_id,
        "agents_updated": len([r for r in results if r["success"]]),
        "details": results
    }

@router.post("/{project_id}/archive")
def archive_project(project_id: str, db: Session = Depends(get_db)):
    """归档项目 - 停止所有智能体"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 停止所有智能体
    agents = db.query(AgentInstance).filter(AgentInstance.project_id == project_id).all()
    from docker_service import DockerService
    docker = DockerService()
    
    stopped_count = 0
    for agent in agents:
        if agent.container_id and agent.status == "running":
            result = docker.stop_container(agent.container_id)
            if result["success"]:
                agent.status = "stopped"
                stopped_count += 1
    
    project.status = "archived"
    db.commit()
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="archive",
        entity_type="project",
        entity_id=project_id,
        description=f"归档项目: {project.name} (停止 {stopped_count} 个智能体)",
        project_id=project_id
    )
    
    return {
        "success": True,
        "message": f"项目 {project.name} 已归档",
        "stopped_agents": stopped_count
    }

@router.delete("/{project_id}")
def delete_project(project_id: str, force: bool = False, db: Session = Depends(get_db)):
    """删除项目 - 删除所有智能体"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    name = project.name
    
    # 删除所有智能体
    agents = db.query(AgentInstance).filter(AgentInstance.project_id == project_id).all()
    from docker_service import DockerService, PortPoolManager
    docker = DockerService()
    port_manager = PortPoolManager(db)
    
    for agent in agents:
        if agent.container_id:
            docker.remove_container(agent.container_id, force=force)
        if agent.host_port:
            port_manager.release_port(agent.host_port)
        db.delete(agent)
    
    # 删除项目
    db.delete(project)
    db.commit()
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="delete",
        entity_type="project",
        entity_id=project_id,
        description=f"删除项目: {name} (包含 {len(agents)} 个智能体)"
    )
    
    return {"success": True, "message": f"项目 {name} 已删除"}

@router.get("/{project_id}/agents")
def get_project_agents(project_id: str, db: Session = Depends(get_db)):
    """获取项目中的所有智能体"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    agents = db.query(AgentInstance).filter(AgentInstance.project_id == project_id).all()
    return [{
        "id": a.id,
        "name": a.name,
        "status": a.status,
        "health_status": a.health_status,
        "host_port": a.host_port,
        "console_url": f"http://127.0.0.1:{a.host_port}" if a.host_port else None,
        "template_id": a.template_id,
        "created_at": a.created_at
    } for a in agents]

@router.get("/{project_id}/main-agent")
def get_main_agent_console(project_id: str, db: Session = Depends(get_db)):
    """获取主智能体控制台入口"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    if not project.main_agent_id:
        raise HTTPException(status_code=404, detail="项目没有主智能体")
    
    main_agent = db.query(AgentInstance).filter(AgentInstance.id == project.main_agent_id).first()
    if not main_agent:
        raise HTTPException(status_code=404, detail="主智能体不存在")
    
    return {
        "agent_id": main_agent.id,
        "agent_name": main_agent.name,
        "status": main_agent.status,
        "console_url": f"http://127.0.0.1:{main_agent.host_port}" if main_agent.host_port else None
    }


class CloneTemplateRequest(BaseModel):
    template_id: str

@router.post("/{project_id}/clone-template")
def clone_template_to_project(
    project_id: str,
    req: CloneTemplateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """克隆模板到项目 - 创建一个新实例（复制模板配置）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    template = db.query(Template).filter(Template.id == req.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    # 分配端口
    port_manager = PortPoolManager(db)
    host_port = port_manager.allocate_port("")
    if not host_port:
        raise HTTPException(status_code=500, detail="端口池已耗尽")
    
    # 创建实例
    agent_id = str(uuid.uuid4())
    container_name = f"openclaw-{project.name}-{agent_id[:8]}"
    config = template.default_config or {}
    
    # 应用项目级配置
    if project.project_config:
        config.update(project.project_config)
    
    agent = AgentInstance(
        id=agent_id,
        name=f"{project.name}-agent-{agent_id[:4]}",
        template_id=template.id,
        project_id=project_id,
        host_port=host_port,
        image=template.image,
        status="creating",
        config=config
    )
    db.add(agent)
    
    # 更新端口分配
    port_alloc = db.query(PortAllocation).filter_by(port=host_port).first()
    if port_alloc:
        port_alloc.agent_id = agent_id
    
    # 如果是项目的第一个实例，设为主实例
    existing_agents = db.query(AgentInstance).filter(AgentInstance.project_id == project_id).count()
    if existing_agents == 0:
        project.main_agent_id = agent_id
    
    db.commit()
    db.refresh(agent)
    
    # 后台创建容器
    background_tasks.add_task(_create_container_task, agent_id, container_name, template.image, host_port, config)
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="clone",
        entity_type="project",
        entity_id=project_id,
        description=f"克隆模板 {template.name} 到项目 {project.name}",
        agent_id=agent_id,
        project_id=project_id
    )
    
    return {
        "success": True,
        "agent_id": agent_id,
        "message": f"正在克隆模板 {template.name} 到项目 {project.name}"
    }
