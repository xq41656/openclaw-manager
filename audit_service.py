"""
审计日志服务
"""
from sqlalchemy.orm import Session
from database import AuditLog
from typing import Optional, Dict, Any


class AuditService:
    """审计日志服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def log(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        description: str = "",
        old_value: Optional[Dict] = None,
        new_value: Optional[Dict] = None,
        agent_id: Optional[str] = None,
        project_id: Optional[str] = None,
        operator: str = "system",
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """记录审计日志"""
        log = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            old_value=old_value,
            new_value=new_value,
            agent_id=agent_id,
            project_id=project_id,
            operator=operator,
            ip_address=ip_address
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log
    
    def get_logs(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ):
        """查询审计日志"""
        query = self.db.query(AuditLog)
        
        if entity_type:
            query = query.filter(AuditLog.entity_type == entity_type)
        if entity_id:
            query = query.filter(AuditLog.entity_id == entity_id)
        if action:
            query = query.filter(AuditLog.action == action)
        
        return query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
