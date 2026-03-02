"""
Docker 服务 - 容器生命周期管理 + 端口池
"""
import docker
import time
from docker.errors import NotFound, APIError
from typing import List, Optional, Dict, Any, Union
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
            print(f"DEBUG pull_image: original repository='{repository}', tag='{tag}'")
            # 处理完整的镜像名称 (如 "openclaw/openclaw:latest" 或 "openclaw-custom:latest")
            if ":" in repository:
                parts = repository.rsplit(":", 1)
                print(f"DEBUG pull_image: parts={parts}")
                # 如果第二部分是有效的tag（不是端口号），使用它作为tag
                if "/" in parts[0] or "." in parts[0] or not parts[1].isdigit():
                    repository = parts[0]
                    tag = parts[1]
                    print(f"DEBUG pull_image: updated repository='{repository}', tag='{tag}'")
            
            print(f"DEBUG pull_image: final repository='{repository}', tag='{tag}', combined='{repository}:{tag}'")
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
            # 检查端口是否已被 Docker 使用
            try:
                containers = self.client.containers.list(all=True)
                if containers:
                    for c in containers:
                        # 获取容器详细信息以获取端口映射
                        attrs = c.attrs
                        ports = attrs.get('NetworkSettings', {}).get('Ports', {})
                        if ports:
                            for container_port, host_ips in ports.items():
                                if host_ips:
                                    # host_ips 可能是列表或字符串
                                    if isinstance(host_ips, list):
                                        for host_ip_info in host_ips:
                                            public_port = host_ip_info.get('HostPort') if isinstance(host_ip_info, dict) else None
                                            if public_port and int(public_port) == host_port:
                                                return {
                                                    "success": False,
                                                    "error": f"端口 {host_port} 已被容器 {c.name} ({c.id[:12]}) 占用"
                                                }
                                    elif isinstance(host_ips, dict):
                                        public_port = host_ips.get('HostPort')
                                        if public_port and int(public_port) == host_port:
                                            return {
                                                "success": False,
                                                "error": f"端口 {host_port} 已被容器 {c.name} ({c.id[:12]}) 占用"
                                            }
            except Exception as e:
                # 忽略端口检查错误，继续创建容器
                print(f"端口检查异常: {e}")
                pass
            
            # 端口映射: 宿主机 host_port -> 容器 18789
            ports = {
                f"{settings.GATEWAY_INTERNAL_PORT}/tcp": ("0.0.0.0", host_port)
            }
            
            container = self.client.containers.run(
                image=image,
                name=name,
                ports=ports,
                environment=environment or {},
                volumes=volumes or {},
                command=None,
                detach=True,
                restart_policy={"Name": "unless-stopped"}
            )
            
            return {
                "success": True,
                "container_id": container.id,
                "name": container.name,
                "status": container.status,
                "image": image
            }
        except NotFound:
            return {"success": False, "error": f"镜像不存在: {image}"}
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
        """获取容器状态（Docker 支持 12 位或 64 位 ID）"""
        try:
            container = self.client.containers.get(container_id)
            return {
                "exists": True,
                "id": container.id,
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
        try:
            containers = self.client.containers.list(all=True)
            result = []
            for c in containers:
                result.append({
                    "id": c.id,
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else c.image.id[:12],
                    "status": c.status,
                    "state": c.attrs.get("State", {}).get("Status", "unknown"),
                    "ports": c.ports,
                    "created": c.attrs.get("Created", "")
                })
            return result
        except Exception as e:
            print(f"获取容器列表失败: {e}")
            return []
    
    def get_container_by_id(self, container_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取容器信息（Docker 支持 12 位或 64 位 ID）"""
        try:
            container = self.client.containers.get(container_id)
            return {
                "id": container.id,
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
    
    def run_entrypoint(self, container_id: str) -> Dict[str, Any]:
        """在容器内执行 openclaw-entrypoint.sh 脚本（后台运行 gateway）"""
        try:
            container = self.client.containers.get(container_id)
            # 重新加载并运行 entrypoint 脚本
            result = container.exec_run(
                ["sh", "-c", "source /usr/local/bin/openclaw-entrypoint.sh"],
                stdout=True,
                stderr=True,
                demux=True
            )
            stdout, stderr = result.output
            output = (stdout.decode('utf-8') if stdout else '') + (stderr.decode('utf-8') if stderr else '')
            return {
                "success": True,
                "exit_code": result.exit_code,
                "output": output
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def copy_file_to_container(self, container_id: str, src_path: str, dest_path: str) -> Dict[str, Any]:
        """将文件复制到容器"""
        try:
            container = self.client.containers.get(container_id)
            with open(src_path, 'rb') as f:
                container.put_archive('/tmp', f.read())
            result = container.exec_run(f"cp /tmp/{src_path.split('/')[-1]} {dest_path}", stdout=True, stderr=True)
            return {
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "output": result.output.decode('utf-8') if result.output else ""
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def stop_openclaw_process(self, container_id: str) -> Dict[str, Any]:
        """停止容器内的 openclaw 进程"""
        try:
            # 使用 pkill 停止所有 openclaw 进程
            result = self.exec_command(container_id, ["pkill", "-f", "openclaw"])
            if result["success"]:
                return {"success": True, "message": "openclaw 进程已停止"}
            return {"success": False, "error": result.get("output", "停止进程失败")}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def copy_openclaw_config_to_container(self, container_id: str) -> Dict[str, Any]:
        """将程序目录下的 openclaw.json 复制到容器"""
        import os
        try:
            config_path = os.path.join(os.path.dirname(__file__), "openclaw.json")
            
            if not os.path.exists(config_path):
                return {"success": False, "error": f"配置文件不存在: {config_path}"}
            
            with open(config_path, 'rb') as f:
                config_data = f.read()
            
            container = self.client.containers.get(container_id)
            
            # 创建目录
            result = self.exec_command(container_id, ["mkdir", "-p", "/root/.openclaw"])
            if not result["success"]:
                return {"success": False, "error": "创建目录失败"}
            
            # 直接使用 exec 写入文件
            import json
            config_str = config_data.decode('utf-8')
            python_code = f"""
import json
config = {json.dumps(json.loads(config_str), indent=2)}
with open('/root/.openclaw/openclaw.json', 'w') as f:
    json.dump(config, f, indent=2)
"""
            write_result = self.exec_command(container_id, ["python3", "-c", python_code])
            
            if write_result["success"]:
                return {"success": True, "message": "配置文件已复制"}
            return {"success": False, "error": write_result.get("output", "写入失败")}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def check_gateway_status(self, container_id: str) -> Dict[str, Any]:
        """检查容器内 OpenClaw (Gateway) 是否正在运行"""
        try:
            container = self.client.containers.get(container_id)
            
            result = container.exec_run(
                ["cat", "/root/.openclaw/status"],
                stdout=True,
                stderr=True
            )
            
            if result.exit_code != 0:
                return {"success": False, "status": "stopped"}
            
            status_content = result.output.decode('utf-8').strip()
            
            if "running" in status_content.lower():
                return {"success": True, "status": "running"}
            else:
                return {"success": False, "status": "stopped"}
                
        except NotFound:
            return {"success": False, "error": "容器不存在"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def gateway_command(self, container_id: str, command: str) -> Dict[str, Any]:
        """执行 Gateway 命令 (start/stop/restart/status)"""
        try:
            container = self.client.containers.get(container_id)
            
            if command == "stop":
                # 停止 Gateway：直接 kill openclaw-gateway 进程
                result = container.exec_run(
                    ["pkill", "-f", "openclaw-gateway"],
                    stdout=True,
                    stderr=True
                )
                output = result.output.decode('utf-8') if result.output else ""
                return {
                    "success": True,
                    "exit_code": result.exit_code,
                    "output": output if output else "Gateway process stopped"
                }
            
            elif command in ["start", "restart"]:
                # 启动/重启 Gateway：先 kill 旧进程，再启动新进程
                container.exec_run(
                    ["pkill", "-f", "openclaw-gateway"],
                    stdout=False,
                    stderr=False
                )
                # 等待一小会儿让旧进程清理
                time.sleep(1)
                # 启动新 Gateway 进程（后台运行）
                result = container.exec_run(
                    ["openclaw", "gateway"],
                    stdout=True,
                    stderr=True,
                    demux=True,
                   detach=True
                )
                return {
                    "success": True,
                    "exit_code": 0,
                    "output": f"Gateway {command}ed"
                }
            
            else:
                # status 命令
                result = container.exec_run(
                    ["openclaw", "gateway", command],
                    stdout=True,
                    stderr=True,
                    demux=True
                )
                
                stdout, stderr = result.output
                output = (stdout.decode('utf-8') if stdout else '') + (stderr.decode('utf-8') if stderr else '')
                
                return {
                    "success": result.exit_code == 0,
                    "exit_code": result.exit_code,
                    "output": output
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
