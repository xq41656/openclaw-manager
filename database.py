from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import settings
import json

Base = declarative_base()
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============ 模型定义 ============

class Template(Base):
    """智能体模板"""
    __tablename__ = "templates"
    
    id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(100), nullable=False)
    description = Column(Text)
    image = Column(String(200), default="openclaw/openclaw:latest")
    default_config = Column(JSON)  # 默认配置 openclaw.json
    capabilities = Column(JSON)    # 能力/插件列表
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    instances = relationship("AgentInstance", back_populates="template")


class AgentInstance(Base):
    """智能体实例"""
    __tablename__ = "agent_instances"
    
    id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(100), nullable=False)
    template_id = Column(String(36), ForeignKey("templates.id"), nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    
    # Docker 相关
    container_id = Column(String(100))  # Docker 容器 ID
    container_name = Column(String(200))
    host_port = Column(Integer, unique=True)  # 宿主机端口 (映射到容器 18789)
    image = Column(String(200))
    
    # 状态: creating, running, stopped, error, archived
    status = Column(String(20), default="creating")
    health_status = Column(String(20))  # healthy, unhealthy, unknown
    
    # 配置 (实例级覆盖)
    config = Column(JSON)
    
    # 创建日志（后台任务日志）
    creation_logs = Column(Text)  # 存储创建过程的日志
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_health_check = Column(DateTime)
    
    # 关系
    template = relationship("Template", back_populates="instances")
    project = relationship("Project", back_populates="agents", foreign_keys="AgentInstance.project_id")
    audit_logs = relationship("AuditLog", back_populates="agent")


class Project(Base):
    """项目"""
    __tablename__ = "projects"
    
    id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(100), nullable=False)
    description = Column(Text)
    
    # 主智能体
    main_agent_id = Column(String(36), ForeignKey("agent_instances.id"), nullable=True)
    
    # 项目级配置策略
    project_config = Column(JSON)  # 统一模型提供商、审计策略等
    
    # 状态: active, archived
    status = Column(String(20), default="active")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系 - 指定 foreign_keys 避免歧义
    agents = relationship("AgentInstance", back_populates="project", foreign_keys="AgentInstance.project_id")
    audit_logs = relationship("AuditLog", back_populates="project")


class AuditLog(Base):
    """审计日志"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(50), nullable=False)  # create, update, delete, start, stop, config_change, etc.
    entity_type = Column(String(50))  # template, agent, project
    entity_id = Column(String(36))
    
    # 关联
    agent_id = Column(String(36), ForeignKey("agent_instances.id"), nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    
    # 变更详情
    old_value = Column(JSON)
    new_value = Column(JSON)
    description = Column(Text)
    
    # 操作人
    operator = Column(String(100), default="system")
    ip_address = Column(String(50))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    agent = relationship("AgentInstance", back_populates="audit_logs")
    project = relationship("Project", back_populates="audit_logs")


class PortAllocation(Base):
    """端口分配记录"""
    __tablename__ = "port_allocations"
    
    port = Column(Integer, primary_key=True)
    agent_id = Column(String(36), ForeignKey("agent_instances.id"), nullable=True)
    is_allocated = Column(Boolean, default=False)
    allocated_at = Column(DateTime)


# 创建表
Base.metadata.create_all(bind=engine)
