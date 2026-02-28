"""
智能体 API - 模板 + 实例生命周期
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import Column
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import uuid
from docker_service import NotFound

from database import get_db, Template, AgentInstance, PortAllocation, AuditLog
from docker_service import DockerService, PortPoolManager
from openclaw_service import OpenClawService
from audit_service import AuditService
from config import settings

router = APIRouter(prefix="/api/agents", tags=["agents"])
docker_service = DockerService()


# ============ 容器 API ============

@router.get("/containers")
def list_containers(db: Session = Depends(get_db)):
    """列出所有容器"""
    containers = docker_service.list_all_containers()
    return containers


@router.get("/containers/{container_id}")
def get_container(container_id: str, db: Session = Depends(get_db)):
    """获取单个容器详情（支持 12 位或 64 位 ID）"""
    container = docker_service.get_container_by_id(container_id)
    return container


@router.post("/containers/{container_id}/start")
def start_container(container_id: str, db: Session = Depends(get_db)):
    """启动容器"""
    result = docker_service.start_container(container_id)
    if result["success"]:
        # 记录审计日志
        audit = AuditService(db)
        # 获取 agent_id 用于审计日志关联
        agent = db.query(AgentInstance).filter(AgentInstance.container_id == container_id).first()
        agent_id = agent.id if agent else None
        
        audit.log(
            action="start",
            entity_type="container",
            entity_id=container_id,
            description=f"启动容器: {result.get('status', 'unknown')}",
            agent_id=agent_id
        )
        
        return {"success": True, "message": "容器已启动", "status": result.get("status")}
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "启动失败"))


@router.post("/containers/{container_id}/stop")
def stop_container(container_id: str, db: Session = Depends(get_db)):
    """停止容器"""
    result = docker_service.stop_container(container_id)
    if result["success"]:
        # 记录审计日志
        audit = AuditService(db)
        # 获取 agent_id 用于审计日志关联
        agent = db.query(AgentInstance).filter(AgentInstance.container_id == container_id).first()
        agent_id = agent.id if agent else None
        
        audit.log(
            action="stop",
            entity_type="container",
            entity_id=container_id,
            description="停止容器",
            agent_id=agent_id
        )
        
        return {"success": True, "message": "容器已停止"}
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "停止失败"))


@router.post("/containers/{container_id}/restart")
def restart_container(container_id: str, db: Session = Depends(get_db)):
    """重启容器"""
    result = docker_service.restart_container(container_id)
    if result["success"]:
        # 记录审计日志
        audit = AuditService(db)
        # 获取 agent_id 用于审计日志关联
        agent = db.query(AgentInstance).filter(AgentInstance.container_id == container_id).first()
        agent_id = agent.id if agent else None
        
        audit.log(
            action="restart",
            entity_type="container",
            entity_id=container_id,
            description=f"重启容器: {result.get('status', 'unknown')}",
            agent_id=agent_id
        )
        
        return {"success": True, "message": "容器已重启", "status": result.get("status")}
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "重启失败"))


@router.get("/containers/{container_id}/logs")
def get_container_logs(container_id: str, tail: int = 200, db: Session = Depends(get_db)):
    """获取容器日志"""
    logs = docker_service.get_container_logs(container_id, tail=tail)
    return {"container_id": container_id, "logs": logs}


@router.get("/containers/{container_id}/inspect")
def inspect_container(container_id: str, db: Session = Depends(get_db)):
    """获取容器详细信息 (inspect)"""
    try:
        container = docker_service.client.containers.get(container_id)
        info = container.attrs
        return {
            "id": container.id,
            "name": container.name,
            "image": container.image.tags[0] if container.image.tags else container.image.id[:12],
            "status": container.status,
            "info": info
        }
    except NotFound:
        raise HTTPException(status_code=404, detail="容器不存在")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ Pydantic 模型 ============

class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    image: str = Field(default="openclaw/openclaw:latest")
    host_port: Optional[int] = None  # 用户指定的主机端口
    default_config: Optional[Dict[str, Any]] = None
    capabilities: Optional[List[str]] = None

class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    default_config: Optional[Dict[str, Any]] = None
    capabilities: Optional[List[str]] = None

class TemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    image: str
    default_config: Optional[Dict]
    capabilities: Optional[List[str]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    template_id: Optional[str] = None
    config_override: Optional[Dict[str, Any]] = None

class AgentConfigUpdate(BaseModel):
    ai_key: Optional[str] = None
    provider: Optional[str] = None
    gateway_token: Optional[str] = None
    gateway_password: Optional[str] = None
    extra_config: Optional[Dict[str, Any]] = None

class AgentResponse(BaseModel):
    id: str
    name: str
    template_id: Optional[str]
    project_id: Optional[str]
    container_id: Optional[str]
    container_name: Optional[str]
    host_port: Optional[int]
    image: str
    status: str
    health_status: Optional[str]
    config: Optional[Dict]
    creation_logs: Optional[str]  # 创建日志
    created_at: datetime
    updated_at: datetime
    last_health_check: Optional[datetime]
    
    class Config:
        from_attributes = True


# ============ 模板 API ============

@router.post("/templates", response_model=TemplateResponse)
def create_template(template: TemplateCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """创建智能体模板，同时创建 Docker 实例"""
    
    # 1. 创建模板
    db_template = Template(
        id=str(uuid.uuid4()),
        name=template.name,
        description=template.description,
        image=template.image,
        default_config=template.default_config,
        capabilities=template.capabilities
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    
    # 2. 分配端口
    port_manager = PortPoolManager(db)
    host_port = template.host_port
    
    # 如果用户指定了端口，检查是否可用
    if host_port:
        port_alloc = db.query(PortAllocation).filter_by(port=host_port).first()
        if port_alloc and port_alloc.is_allocated:
            raise HTTPException(status_code=400, detail=f"端口 {host_port} 已被占用")
        elif not port_alloc:
            # 创建端口分配记录
            port_alloc = PortAllocation(port=host_port, is_allocated=True, allocated_at=datetime.utcnow())
            db.add(port_alloc)
    else:
        # 自动分配端口
        host_port = port_manager.allocate_port("")
        if not host_port:
            raise HTTPException(status_code=500, detail="端口池已耗尽，无法创建实例")
    
    # 3. 创建智能体实例（关联到模板）
    agent_id = str(uuid.uuid4())
    container_name = f"M-{db_template.id[:8]}"  # M-模板id
    
    db_agent = AgentInstance(
        id=agent_id,
        name=f"{db_template.name}-instance",
        template_id=db_template.id,
        host_port=host_port,
        image=db_template.image,
        status="creating",
        config=db_template.default_config or {}
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    
    # 更新端口分配记录
    port_alloc = db.query(PortAllocation).filter_by(port=host_port).first()
    if port_alloc:
        port_alloc.agent_id = agent_id
        db.commit()
    
    # 4. 异步创建 Docker 容器
    background_tasks.add_task(
        _create_container_task, 
        agent_id, 
        container_name, 
        template.image, 
        host_port, 
        template.default_config or {}
    )
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="create",
        entity_type="template",
        entity_id=db_template.id,
        description=f"创建模板: {template.name} (端口: {host_port})"
    )
    
    return db_template

@router.get("/templates", response_model=List[TemplateResponse])
def list_templates(db: Session = Depends(get_db)):
    """列出所有模板"""
    return db.query(Template).all()

@router.get("/templates/{template_id}", response_model=TemplateResponse)
def get_template(template_id: str, db: Session = Depends(get_db)):
    """获取模板详情"""
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return template

@router.put("/templates/{template_id}", response_model=TemplateResponse)
def update_template(template_id: str, template: TemplateUpdate, db: Session = Depends(get_db)):
    """更新模板"""
    db_template = db.query(Template).filter(Template.id == template_id).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    update_data = template.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_template, key, value)
    
    db.commit()
    db.refresh(db_template)
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="update",
        entity_type="template",
        entity_id=template_id,
        description=f"更新模板: {db_template.name}"
    )
    
    return db_template

@router.delete("/templates/{template_id}")
def delete_template(template_id: str, force: bool = False, db: Session = Depends(get_db)):
    """删除模板及其关联的实例和容器"""
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    name = template.name
    
    # 删除关联的实例和容器
    for agent in template.instances:
        # 删除容器
        if agent.container_id:
            docker_service.remove_container(agent.container_id, force=force)
        
        # 释放端口
        if agent.host_port:
            port_manager = PortPoolManager(db)
            port_manager.release_port(agent.host_port)
        
        # 删除实例记录
        db.delete(agent)
    
    # 删除模板
    db.delete(template)
    db.commit()
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="delete",
        entity_type="template",
        entity_id=template_id,
        description=f"删除模板及实例: {name}"
    )
    
    return {"success": True, "message": f"模板 {name} 及关联实例已删除"}


# ============ 实例 API ============

@router.post("/instances", response_model=AgentResponse)
def create_agent(agent: AgentCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """创建智能体实例"""
    # 分配端口
    port_manager = PortPoolManager(db)
    host_port = port_manager.allocate_port("")
    if not host_port:
        raise HTTPException(status_code=500, detail="端口池已耗尽，无法创建新实例")
    
    # 获取模板配置
    template = None
    config = {}
    image = settings.DEFAULT_OPENCLAW_IMAGE
    
    if agent.template_id:
        template = db.query(Template).filter(Template.id == agent.template_id).first()
        if template:
            # 使用 template.default_config 或生成默认配置
            if template.default_config:
                config = template.default_config.copy()
            else:
                from openclaw_service import OpenClawService
                config = OpenClawService().generate_config()
            image = template.image
    
    # 应用实例级配置覆盖
    if agent.config_override:
        config.update(agent.config_override)
    
    # 创建数据库记录
    agent_id = str(uuid.uuid4())
    container_name = f"openclaw-agent-{agent_id[:8]}"
    
    db_agent = AgentInstance(
        id=agent_id,
        name=agent.name,
        template_id=agent.template_id,
        host_port=host_port,
        image=image,
        status="creating",
        config=config
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    
    # 更新端口分配记录
    port_alloc = db.query(PortAllocation).filter_by(port=host_port).first()
    if port_alloc:
        port_alloc.agent_id = agent_id
        db.commit()
    
    # 异步创建 Docker 容器
    background_tasks.add_task(_create_container_task, agent_id, container_name, image, host_port, config)
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="create",
        entity_type="agent",
        entity_id=agent_id,
        description=f"创建智能体实例: {agent.name}",
        agent_id=agent_id
    )
    
    return db_agent

def _create_container_task(agent_id: str, container_name: str, image: str, host_port: int, config: dict):
    """后台任务：创建 Docker 容器"""
    from database import SessionLocal, AgentInstance
    from datetime import datetime
    import traceback
    from docker_service import DockerService
    from openclaw_service import OpenClawService
    
    logs = []
    
    def log(msg, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level}] {msg}"
        logs.append(line)
        print(line)
    
    db = SessionLocal()
    docker_service = DockerService()
    oc_service = OpenClawService()
    
    def save_logs():
        """保存日志到数据库"""
        agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
        if agent:
            agent.creation_logs = "\n".join(logs)
            db.commit()
    
    try:
        log("=" * 60)
        log(f"开始创建容器: {container_name}")
        log(f"Agent ID: {agent_id}")
        log(f"主机端口: {host_port}")
        log(f"镜像: {image}")
        log(f"容器端口: 18789 (固定)")
        save_logs()
        
        # 检查本地镜像
        log("步骤1: 检查/拉取镜像...")
        pull_result = docker_service.pull_image(image)
        log(f"镜像检查结果: {pull_result}")
        save_logs()
        
        if not pull_result["success"]:
            error_msg = pull_result.get("error", "")
            if "no such host" in error_msg or "dial tcp" in error_msg or "resolve" in error_msg:
                log("❌ 网络/DNS 错误，无法拉取镜像", "ERROR")
                log(f"错误详情: {error_msg}", "ERROR")
                _update_agent_status(db, agent_id, "error", error="无法拉取镜像: 网络/DNS 问题。请检查网络连接或手动导入镜像。")
            else:
                log(f"❌ 拉取镜像失败: {error_msg}", "ERROR")
                _update_agent_status(db, agent_id, "error", error=f"拉取镜像失败: {error_msg}")
            save_logs()
            return
        
        if pull_result.get("from_local"):
            log("✅ 使用本地已有镜像")
        else:
            log("✅ 镜像拉取成功")
        
        # 创建容器
        log(f"步骤2: 创建容器 (名称: {container_name}, 端口映射: {host_port}->18789)...")
        save_logs()
        
        result = docker_service.create_container(
            name=container_name,
            image=image,
            host_port=host_port
        )
        log(f"创建结果: {result}")
        save_logs()
        
        if result["success"]:
            container_id = result["container_id"]
            log(f"✅ 容器创建成功")
            log(f"容器ID: {container_id}")
            
            # 等待容器启动（openclaw 已自启动）
            import time
            log("等待容器启动...")
            time.sleep(5)  # 等待5秒让openclaw启动完成
            save_logs()
            
            # 应用配置
            log("步骤3: 应用 OpenClaw 配置...")
            save_logs()
            
            # 如果 config 为空，生成默认配置
            if not config:
                config = oc_service.generate_config()
            config_result = oc_service.apply_config_to_container(container_id, config)
            log(f"配置应用结果: {config_result}")
            
            if config_result.get("success"):
                log("✅ 配置应用成功")
            else:
                log(f"⚠️ 配置应用失败: {config_result.get('error')}", "WARNING")
            
            # 重启容器使配置生效（openclaw只在启动时读取配置）
            log("步骤3.5: 重启容器使配置生效...")
            save_logs()
            restart_result = docker_service.restart_container(container_id)
            if restart_result["success"]:
                log("✅ 容器重启成功")
            else:
                log(f"⚠️ 容器重启失败: {restart_result.get('error')}", "WARNING")
            
            # 等待容器重启完成
            log("等待容器重启完成...")
            time.sleep(3)
            save_logs()
            
            # 更新数据库状态
            log("步骤4: 更新数据库状态为 running...")
            _update_agent_status(
                db, agent_id, "running",
                container_id=container_id,
                container_name=container_name
            )
            log("✅ 状态更新成功")
            log(f"🎉 容器创建完成！访问地址: http://<服务器IP>:{host_port}")
        else:
            error = result.get("error", "未知错误")
            log(f"❌ 容器创建失败: {error}", "ERROR")
            _update_agent_status(db, agent_id, "error", error=error)
        
        save_logs()
        
    except Exception as e:
        error_msg = str(e)
        log(f"❌ 创建容器异常: {error_msg}", "ERROR")
        log(traceback.format_exc(), "ERROR")
        _update_agent_status(db, agent_id, "error", error=error_msg)
        save_logs()
    finally:
        db.close()
        log("=" * 60)

def _update_agent_status(db: Session, agent_id: str, status: str, container_id: str = None, container_name: str = None, error: str = None):
    """更新智能体状态"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if agent:
        agent.status = status
        if container_id:
            agent.container_id = container_id
        if container_name:
            agent.container_name = container_name
        # 保存错误信息到 config
        if error:
            if agent.config is None:
                agent.config = {}
            agent.config["error"] = error
        db.commit()
        db.refresh(agent)
        import logging
        logging.getLogger(__name__).info(f"Agent {agent_id} status updated to {status}")

@router.get("/instances", response_model=List[AgentResponse])
def list_agents(
    status: Optional[str] = None,
    template_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """列出所有智能体实例"""
    query = db.query(AgentInstance)
    if status:
        query = query.filter(AgentInstance.status == status)
    if template_id:
        query = query.filter(AgentInstance.template_id == template_id)
    return query.all()

@router.get("/instances/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    """获取智能体详情"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    return agent

@router.post("/instances/{agent_id}/start")
def start_agent(agent_id: str, db: Session = Depends(get_db)):
    """启动智能体"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    if not agent.container_id:
        raise HTTPException(status_code=400, detail="容器尚未创建")
    
    result = docker_service.start_container(agent.container_id)
    if result["success"]:
        import time
        time.sleep(2)
        
        oc_service = OpenClawService()
        entrypoint_result = oc_service.docker.run_entrypoint(agent.container_id)
        
        agent.status = "running"
        db.commit()
        
        audit = AuditService(db)
        audit.log(
            action="start",
            entity_type="agent",
            entity_id=agent_id,
            description=f"启动智能体: {agent.name}",
            agent_id=agent_id,
            extra_data={"entrypoint_result": entrypoint_result}
        )
        
        return {"success": True, "message": f"智能体 {agent.name} 已启动", "entrypoint": entrypoint_result}
    else:
        raise HTTPException(status_code=500, detail=result.get("error"))

@router.post("/instances/{agent_id}/stop")
def stop_agent(agent_id: str, db: Session = Depends(get_db)):
    """停止智能体"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    if not agent.container_id:
        raise HTTPException(status_code=400, detail="容器尚未创建")
    
    result = docker_service.stop_container(agent.container_id)
    if result["success"]:
        agent.status = "stopped"
        db.commit()
        
        # 审计日志
        audit = AuditService(db)
        audit.log(
            action="stop",
            entity_type="agent",
            entity_id=agent_id,
            description=f"停止智能体: {agent.name}",
            agent_id=agent_id
        )
        
        return {"success": True, "message": f"智能体 {agent.name} 已停止"}
    else:
        raise HTTPException(status_code=500, detail=result.get("error"))

@router.post("/instances/{agent_id}/restart")
def restart_agent(agent_id: str, db: Session = Depends(get_db)):
    """重启智能体"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    if not agent.container_id:
        raise HTTPException(status_code=400, detail="容器尚未创建")
    
    result = docker_service.restart_container(agent.container_id)
    if result["success"]:
        agent.status = "running"
        db.commit()
        
        # 审计日志
        audit = AuditService(db)
        audit.log(
            action="restart",
            entity_type="agent",
            entity_id=agent_id,
            description=f"重启智能体: {agent.name}",
            agent_id=agent_id
        )
        
        return {"success": True, "message": f"智能体 {agent.name} 已重启"}
    else:
        raise HTTPException(status_code=500, detail=result.get("error"))

@router.post("/instances/{agent_id}/start-claw")
def start_claw(agent_id: str, db: Session = Depends(get_db)):
    """启动 Claw（执行 entrypoint 脚本）"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    if not agent.container_id:
        raise HTTPException(status_code=400, detail="容器尚未创建")
    
    oc_service = OpenClawService()
    entrypoint_result = oc_service.docker.run_entrypoint(agent.container_id)
    
    audit = AuditService(db)
    audit.log(
        action="start_claw",
        entity_type="agent",
        entity_id=agent_id,
        description=f"启动 Claw: {agent.name}",
        agent_id=agent_id
    )
    
    return {"success": entrypoint_result.get("success", False), "message": f"Claw 启动完成", "result": entrypoint_result}

@router.get("/instances/{agent_id}/logs")
def get_agent_logs(agent_id: str, tail: int = 200, db: Session = Depends(get_db)):
    """获取智能体容器日志"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    if not agent.container_id:
        return {"agent_id": agent_id, "logs": "容器尚未创建", "log_type": "container"}
    
    logs = docker_service.get_container_logs(agent.container_id, tail=tail)
    return {"agent_id": agent_id, "logs": logs, "log_type": "container"}

@router.get("/instances/{agent_id}/creation-logs")
def get_creation_logs(agent_id: str, db: Session = Depends(get_db)):
    """获取智能体创建日志（后台任务日志）"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    
    creation_logs = agent.creation_logs or "暂无创建日志"
    return {
        "agent_id": agent_id,
        "logs": creation_logs,
        "log_type": "creation",
        "status": agent.status
    }

class ContainerUpdateRequest(BaseModel):
    container_id: str
    container_name: Optional[str] = None
    host_port: Optional[int] = None

@router.post("/instances/{agent_id}/update-container")
def update_agent_container(
    agent_id: str,
    req: ContainerUpdateRequest,
    db: Session = Depends(get_db)
):
    """更新智能体关联的容器信息"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    
    # 验证容器是否存在
    container_status = docker_service.get_container_status(req.container_id)
    if not container_status.get("exists"):
        raise HTTPException(status_code=400, detail="容器不存在")
    
    # 保存旧值用于审计
    old_container_id = agent.container_id
    old_port = agent.host_port
    
    # 更新容器信息
    agent.container_id = req.container_id
    if req.container_name:
        agent.container_name = req.container_name
    if req.host_port:
        agent.host_port = req.host_port
    
    # 根据容器状态更新agent状态
    if container_status.get("status") in ["running", "up"]:
        agent.status = "running"
    else:
        agent.status = "stopped"
    
    db.commit()
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="update",
        entity_type="agent",
        entity_id=agent_id,
        description=f"更新智能体容器关联: {agent.name}",
        old_value={"container_id": old_container_id, "host_port": old_port},
        new_value={"container_id": req.container_id, "host_port": req.host_port, "container_name": req.container_name},
        agent_id=agent_id
    )
    
    return {
        "success": True,
        "message": "容器信息已更新",
        "agent": agent
    }

@router.post("/instances/{agent_id}/config")
def update_agent_config(agent_id: str, config: AgentConfigUpdate, db: Session = Depends(get_db)):
    """更新智能体配置"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    
    # 保存旧配置用于审计
    old_config = agent.config
    
    # 生成新配置
    if not config:
        config = oc_service.generate_config()
    new_config = oc_service.generate_config(
        ai_key=config.ai_key,
        provider=config.provider,
        gateway_token=config.gateway_token,
        gateway_password=config.gateway_password,
        **(config.extra_config or {})
    )
    
    # 应用配置
    if agent.container_id:
        result = oc_service.apply_config_to_container(agent.container_id, new_config)
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "配置应用失败"))
    
    # 更新数据库
    agent.config = new_config
    db.commit()
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="config_change",
        entity_type="agent",
        entity_id=agent_id,
        description=f"更新智能体配置: {agent.name}",
        old_value=old_config,
        new_value=new_config,
        agent_id=agent_id
    )
    
    return {"success": True, "message": "配置已更新并应用"}

@router.get("/instances/{agent_id}/health")
def check_agent_health(agent_id: str, db: Session = Depends(get_db)):
    """健康检查"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    
    # 容器状态
    if agent.container_id:
        container_status = docker_service.get_container_status(agent.container_id)
    else:
        container_status = {"exists": False}
    
    # Gateway 健康检查
    health_result = {"checked": False}
    if agent.host_port:
        if not config:
            config = oc_service.generate_config()
        health_result = oc_service.health_check("127.0.0.1", agent.host_port)
        agent.health_status = "healthy" if health_result.get("healthy") else "unhealthy"
        agent.last_health_check = datetime.utcnow()
        db.commit()
    
    return {
        "agent_id": agent_id,
        "status": agent.status,
        "container": container_status,
        "gateway_health": health_result,
        "console_url": f"http://127.0.0.1:{agent.host_port}" if agent.host_port else None
    }

@router.delete("/instances/{agent_id}")
def delete_agent(agent_id: str, force: bool = False, db: Session = Depends(get_db)):
    """删除智能体"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    
    name = agent.name
    
    # 删除容器
    if agent.container_id:
        result = docker_service.remove_container(agent.container_id, force=force)
        if not result["success"] and not force:
            raise HTTPException(status_code=500, detail=result.get("error"))
    
    # 释放端口
    if agent.host_port:
        port_manager = PortPoolManager(db)
        port_manager.release_port(agent.host_port)
    
    # 删除记录
    db.delete(agent)
    db.commit()
    
    # 审计日志
    audit = AuditService(db)
    audit.log(
        action="delete",
        entity_type="agent",
        entity_id=agent_id,
        description=f"删除智能体: {name}",
        agent_id=agent_id
    )
    
    return {"success": True, "message": f"智能体 {name} 已删除"}

@router.post("/instances/{agent_id}/backup")
def backup_agent(agent_id: str, tag: Optional[str] = None, db: Session = Depends(get_db)):
    """备份智能体为镜像"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    if not agent.container_id:
        raise HTTPException(status_code=400, detail="容器尚未创建")
    
    backup_tag = tag or f"backup-{agent_id[:8]}-{datetime.now().strftime('%Y%m%d')}"
    repository = f"openclaw-backup/{agent.name}"
    
    result = docker_service.commit_container(agent.container_id, repository, backup_tag)
    
    if result["success"]:
        # 审计日志
        audit = AuditService(db)
        audit.log(
            action="backup",
            entity_type="agent",
            entity_id=agent_id,
            description=f"备份智能体: {agent.name} -> {repository}:{backup_tag}",
            agent_id=agent_id
        )
        
        return {
            "success": True,
            "image_tag": result["tag"],
            "image_id": result["image_id"]
        }
    else:
        raise HTTPException(status_code=500, detail=result.get("error"))


@router.get("/instances/{agent_id}/config-logs")
def get_config_logs(agent_id: str, db: Session = Depends(get_db)):
    """获取智能体配置变更日志"""
    agent = db.query(AgentInstance).filter(AgentInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")
    
    logs = db.query(AuditLog).filter(
        AuditLog.agent_id == agent_id,
        AuditLog.action == "config_change"
    ).order_by(AuditLog.created_at.desc()).all()
    
    return {
        "logs": [{
            "id": log.id,
            "action": log.action,
            "description": log.description,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "created_at": log.created_at.isoformat()
        } for log in logs]
    }
