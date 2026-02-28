"""
Docker 服务 - 容器生命周期管理 + 端口池
"""
import docker
from docker.errors import NotFound, APIError
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from database import PortAllocation, AgentInstance, AuditLog
from config import settings
import uuid
from datetime import datetime


class PortPoolManager:
    """端口池管理器"""
    
    def __init__(self, db: Session):
        self.db = db
        self._init_port_pool()
    
    def _init_port_pool(self):
        """初始化端口池"""
        for port in range(settings.PORT_POOL_START, settings.PORT_POOL_END + 1):
            existing = self.db.query(PortAllocation).filter_by(port=port).first()
            if not existing:
                allocation = PortAllocation(port=port, is_allocated=False)
                self.db.add(allocation)
        self.db.commit()
    
    def allocate_port(self, agent_id: str) -> Optional[int]:
        """分配可用端口"""
        port_alloc = self.db.query(PortAllocation).filter_by(
            is_allocated=False
        ).first()
        
        if not port_alloc:
            return None
        
        port_alloc.is_allocated = True
        port_alloc.agent_id = agent_id
        port_alloc.allocated_at = datetime.utcnow()
        self.db.commit()
        
        return port_alloc.port
    
    def release_port(self, port: int):
        """释放端口"""
        port_alloc = self.db.query(PortAllocation).filter_by(port=port).first()
        if port_alloc:
            port_alloc.is_allocated = False
            port_alloc.agent_id = None
            port_alloc.allocated_at = None
            self.db.commit()
    
    def get_allocated_ports(self) -> List[int]:
        """获取已分配端口列表"""
        return [p.port for p in self.db.query(PortAllocation).filter_by(is_allocated=True).all()]


class DockerService:
    """Docker 服务"""
    
    def __init__(self):
        self.client = docker.from_env()
    
    def pull_image(self, repository: str, tag: str = "latest") -> Dict[str, Any]:
        """检查本地镜像是否存在（不拉取远程镜像）"""
        try:
            # 处理完整的镜像名称 (如 "openclaw/openclaw:latest")
            if ":" in repository and tag == "latest":
                parts = repository.rsplit(":", 1)
                if "/" in parts[0] or "." in parts[0]:
                    repository = parts[0]
                    tag = parts[1]
            
            # 只检查本地是否已有镜像，不拉取
            try:
                image = self.client.images.get(f"{repository}:{tag}")
                return {
                    "success": True,
                    "id": image.id,
                    "tags": image.tags,
                    "from_local": True
                }
            except NotFound:
                return {
                    "success": False,
                    "error": f"本地镜像不存在: {repository}:{tag}"
                }
        except Exception as e:
            return {"success": False, "error": f"检查镜像失败: {str(e)}"}
    
    def list_local_images(self) -> List[Dict[str, Any]]:
        """列出所有本地镜像"""
        try:
            images = self.client.images.list()
            result = []
            for img in images:
                if img.tags:
                    for tag in img.tags:
                        result.append({
                            "id": img.id[:12],
                            "tag": tag,
                            "size": img.attrs.get("Size", 0),
                            "created": img.attrs.get("Created", "")
                        })
            return result
        except Exception as e:
            print(f"获取本地镜像列表失败: {e}")
            return []
    
    def create_container(
        self,
        name: str,
        image: str,
        host_port: int,
        environment: Optional[Dict] = None,
        volumes: Optional[Dict] = None,
        command: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建并启动 OpenClaw 容器"""
        try:
            # 端口映射: 宿主机 host_port -> 容器 18789
            ports = {
                f"{settings.GATEWAY_INTERNAL_PORT}/tcp": ("0.0.0.0", host_port)
            }
            
            # 先检查镜像是否存在
            try:
                self.client.images.get(image)
            except NotFound:
                # 镜像不存在，尝试拉取
                pass
            
            container = self.client.containers.run(
                image=image,
                name=name,
                ports=ports,
                environment=environment or {},
                volumes=volumes or {},
                command=command,
                detach=True,
                restart_policy={"Name": "unless-stopped"}
            )
            
            return {
                "success": True,
                "container_id": container.id,
                "name": container.name,
                "status": container.status
            }
        except NotFound as e:
            return {"success": False, "error": f"镜像不存在: {str(e)}"}
        except APIError as e:
            return {"success": False, "error": f"Docker API 错误: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"创建容器失败: {str(e)}"}
    
    def start_container(self, container_id: str) -> Dict[str, Any]:
        """启动容器"""
        try:
            container = self.client.containers.get(container_id)
            container.start()
            return {"success": True, "status": container.status}
        except NotFound:
            return {"success": False, "error": "容器不存在"}
        except APIError as e:
            return {"success": False, "error": str(e)}
    
    def stop_container(self, container_id: str, timeout: int = 30) -> Dict[str, Any]:
        """停止容器"""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=timeout)
            return {"success": True}
        except NotFound:
            return {"success": False, "error": "容器不存在"}
        except APIError as e:
            return {"success": False, "error": str(e)}
    
    def restart_container(self, container_id: str) -> Dict[str, Any]:
        """重启容器"""
        try:
            container = self.client.containers.get(container_id)
            container.restart()
            return {"success": True, "status": container.status}
        except NotFound:
            return {"success": False, "error": "容器不存在"}
        except APIError as e:
            return {"success": False, "error": str(e)}
    
    def remove_container(self, container_id: str, force: bool = False) -> Dict[str, Any]:
        """删除容器"""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=force)
            return {"success": True}
        except NotFound:
            return {"success": False, "error": "容器不存在"}
        except APIError as e:
            return {"success": False, "error": str(e)}
    
    def get_container_logs(self, container_id: str, tail: int = 200) -> str:
        """获取容器日志"""
        try:
            container = self.client.containers.get(container_id)
            logs = container.logs(tail=tail, timestamps=True).decode('utf-8')
            return logs
        except NotFound:
            return "容器不存在"
        except Exception as e:
            return f"获取日志失败: {str(e)}"
    
    def get_container_status(self, container_id: str) -> Dict[str, Any]:
        """获取容器状态（支持 12 位或 64 位 ID）"""
        try:
            # Docker 支持使用 12 位或 64 位 ID
            container = self.client.containers.get(container_id)
            return {
                "exists": True,
                "id": container.id,  # 完整 64 位 ID
                "id_short": container.id[:12],  # 12 位缩写
                "name": container.name,
                "status": container.status,
                "state": container.attrs.get("State", {}),
                "health": container.attrs.get("State", {}).get("Health", {}).get("Status", "none")
            }
        except NotFound:
            return {"exists": False}
        except Exception as e:
            return {"exists": False, "error": str(e)}
    
    def list_all_containers(self) -> List[Dict[str, Any]]:
        """列出所有容器（返回完整 64 位 ID）"""
        containers = self.client.containers.list(all=True)
        result = []
        for c in containers:
            result.append({
                "id": c.id,  # 返回完整 64 位 ID
                "id_short": c.id[:12],  # 12 位缩写 ID 用于显示
                "name": c.name,
                "image": c.image.tags[0] if c.image.tags else c.image.id[:12],
                "status": c.status,
                "state": c.attrs.get("State", {}).get("Status", "unknown"),
                "ports": c.ports,
                "created": c.attrs.get("Created", "")
            })
        return result
    
    def get_container_by_id(self, container_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID（支持 12 位或 64 位）获取容器信息"""
        try:
            # Docker 支持使用 12 位或 64 位 ID
            container = self.client.containers.get(container_id)
            return {
                "id": container.id,  # 完整 64 位
                "id_short": container.id[:12],  # 12 位缩写
                "name": container.name,
                "image": container.image.tags[0] if container.image.tags else container.image.id[:12],
                "status": container.status,
                "state": container.attrs.get("State", {}),
                "ports": container.ports,
                "exists": True
            }
        except NotFound:
            return {"exists": False}
        except Exception as e:
            return {"exists": False, "error": str(e)}
    
    def commit_container(self, container_id: str, repository: str, tag: str) -> Dict[str, Any]:
        """提交容器为镜像（备份）"""
        try:
            container = self.client.containers.get(container_id)
            image = container.commit(repository=repository, tag=tag)
            return {
                "success": True,
                "image_id": image.id,
                "tag": f"{repository}:{tag}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def save_image(self, image_tag: str, output_path: str) -> Dict[str, Any]:
        """保存镜像到 tar 文件"""
        try:
            image = self.client.images.get(image_tag)
            with open(output_path, 'wb') as f:
                for chunk in image.save():
                    f.write(chunk)
            return {"success": True, "path": output_path}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def exec_command(self, container_id: str, command: List[str]) -> Dict[str, Any]:
        """在容器内执行命令"""
        try:
            container = self.client.containers.get(container_id)
            result = container.exec_run(command, stdout=True, stderr=True)
            return {
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "output": result.output.decode('utf-8') if result.output else ""
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
