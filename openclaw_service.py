"""
OpenClaw 服务 - 配置管理 + 健康检查
"""
import json
import requests
from typing import Dict, Any, Optional
from docker_service import DockerService
from config import settings


class OpenClawService:
    """OpenClaw 配置与运维服务"""
    
    def __init__(self):
        self.docker = DockerService()
    
    def generate_config(
        self,
        ai_key: Optional[str] = None,
        provider: Optional[str] = None,
        gateway_token: Optional[str] = None,
        gateway_password: Optional[str] = None,
        **extra_config
    ) -> Dict[str, Any]:
        """生成 OpenClaw 配置 (openclaw.json)"""
        config = {
            "gateway": {
                "port": settings.GATEWAY_INTERNAL_PORT,
                "host": "0.0.0.0"
            },
            "logging": {
                "level": "info"
            }
        }
        
        if gateway_token:
            config["gateway"]["token"] = gateway_token
        if gateway_password:
            config["gateway"]["password"] = gateway_password
        
        # AI 提供商配置
        if provider:
            config["llm"] = {
                "default_provider": provider,
                "providers": {}
            }
            if ai_key:
                config["llm"]["providers"][provider] = {
                    "api_key": ai_key
                }
        
        # 合并额外配置
        config.update(extra_config)
        
        return config
    
    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """校验配置有效性"""
        errors = []
        
        # 检查必需的键
        if "gateway" not in config:
            errors.append("缺少 gateway 配置")
        else:
            if "port" not in config["gateway"]:
                errors.append("缺少 gateway.port")
        
        # 类型检查
        if "gateway" in config and "port" in config["gateway"]:
            if not isinstance(config["gateway"]["port"], int):
                errors.append("gateway.port 必须是整数")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def apply_config_to_container(
        self,
        container_id: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """将配置应用到容器"""
        # 先校验
        validation = self.validate_config(config)
        if not validation["valid"]:
            return {"success": False, "errors": validation["errors"]}
        
        # 将配置写入容器的 ~/.openclaw/openclaw.json
        config_json = json.dumps(config, indent=2)
        
        # 使用 docker exec 写入文件
        mkdir_result = self.docker.exec_command(
            container_id,
            ["mkdir", "-p", "/root/.openclaw"]
        )
        
        # 使用 echo 写入 (简单方式)
        write_result = self.docker.exec_command(
            container_id,
            ["sh", "-c", f"echo '{config_json}' > /root/.openclaw/openclaw.json"]
        )
        
        if not write_result["success"]:
            return {
                "success": False,
                "error": f"写入配置失败: {write_result.get('output', '')}"
            }
        
        # 重启容器使配置生效
        restart_result = self.docker.restart_container(container_id)
        
        return {
            "success": restart_result["success"],
            "config_applied": True,
            "restarted": restart_result["success"]
        }
    
    def health_check(self, host: str, port: int) -> Dict[str, Any]:
        """健康检查 - 通过 Gateway WebSocket/HTTP"""
        try:
            url = f"http://{host}:{port}/health"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                return {
                    "healthy": True,
                    "status_code": response.status_code,
                    "response": response.json() if response.text else {}
                }
            else:
                return {
                    "healthy": False,
                    "status_code": response.status_code,
                    "error": f"HTTP {response.status_code}"
                }
        except requests.exceptions.ConnectionError:
            return {
                "healthy": False,
                "error": "无法连接到 Gateway"
            }
        except requests.exceptions.Timeout:
            return {
                "healthy": False,
                "error": "连接超时"
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }
    
    def check_gateway_status(self, container_id: str) -> Dict[str, Any]:
        """在容器内执行 openclaw gateway status"""
        result = self.docker.exec_command(
            container_id,
            ["openclaw", "gateway", "status"]
        )
        
        if result["success"]:
            return {
                "success": True,
                "status": result["output"]
            }
        else:
            return {
                "success": False,
                "error": result.get("output", result.get("error", "未知错误"))
            }
    
    def get_console_url(self, host: str, port: int, token: Optional[str] = None) -> str:
        """生成控制台访问 URL"""
        base = f"http://{host}:{port}"
        if token:
            return f"{base}?token={token}"
        return base
    
    def get_agent_info(self, container_id: str) -> Dict[str, Any]:
        """获取智能体信息"""
        # 读取容器内的配置
        result = self.docker.exec_command(
            container_id,
            ["cat", "/root/.openclaw/openclaw.json"]
        )
        
        if result["success"]:
            try:
                config = json.loads(result["output"])
                return {
                    "success": True,
                    "config": config
                }
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error": "配置文件解析失败"
                }
        else:
            return {
                "success": False,
                "error": "无法读取配置"
            }
