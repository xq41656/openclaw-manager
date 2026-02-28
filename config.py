from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # 服务配置
    APP_NAME: str = "OpenClaw Manager"
    APP_VERSION: str = "1.0.0"
    SERVER_PORT: int = 8080  # 程序运行端口（只能是8080）
    
    # 端口池配置 (OpenClaw Gateway 默认 18789，映射到宿主机端口池)
    PORT_POOL_START: int = 30001  # 端口池起始
    PORT_POOL_END: int = 30500  # 端口池结束
    GATEWAY_INTERNAL_PORT: int = 18789
    
    # 基础容器实例名称（用于克隆）
    BASE_CONTAINER_NAME: str = "openclaw-26.2.26"
    
    # 数据库
    DATABASE_URL: str = "sqlite:///./openclaw_manager.db"
    
    # OpenClaw 镜像
    DEFAULT_OPENCLAW_IMAGE: str = "openclaw/openclaw:latest"
    
    # 存储路径
    DATA_DIR: str = "./data"
    BACKUP_DIR: str = "./backups"
    
    class Config:
        env_file = ".env"

settings = Settings()
