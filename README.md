# OpenClaw Manager 🦞

一个用于管理多个 OpenClaw 实例的 Web UI 工具，基于 FastAPI 和 Docker。

## 功能特性 ✨

### 📋 模板管理
- **创建模板**：一键创建 OpenClaw 模板，同时生成对应的 Docker 实例
- **编辑模板**：修改模板名称和描述
- **删除模板**：删除模板及其关联的 Docker 实例
- **本地镜像选择**：从本地 Docker 镜像中选择，无需拉取远程镜像
- **容器 ID 关联**：可随时修改模板指向的容器

### 📁 项目管理
- **创建项目**：组织多个智能体实例为一个项目
- **项目克隆**：从模板克隆实例到项目中
- **项目归档**：归档不再使用的项目

### 🐳 Docker 实例管理
- **实例状态**：实时查看容器运行状态（创建中、运行中、已停止、错误）
- **端口映射**：自动分配或手动指定主机端口（映射到容器 18789）
- **启动/停止**：控制实例的启停
- **配置管理**：为每个实例配置 AI Provider、API Key、Gateway Token
- **日志查看**：查看容器运行日志和创建日志

### 🔧 系统功能
- **端口池管理**：自动分配和管理端口（默认 18800-18900）
- **创建日志**：完整记录容器创建过程，方便调试
- **审计日志**：记录所有操作历史

## 项目结构

```
openclaw-manager/
├── config.py              # 配置管理（端口池、数据库等）
├── database.py            # 数据库模型（Template、AgentInstance、Project、AuditLog）
├── docker_service.py      # Docker 服务（端口池、镜像管理）
├── openclaw_service.py    # OpenClaw 服务（配置生成、健康检查）
├── agent_api.py           # 智能体 API（模板/实例 CRUD）
├── project_api.py         # 项目 API
├── audit_service.py       # 审计日志服务
├── main.py                # FastAPI 主应用
├── templates/             # Web 界面
│   └── dashboard.html    # 仪表盘（模板/项目管理）
├── requirements.txt
└── start.sh               # 启动脚本
```

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
./start.sh
# 或
uvicorn main:app --host 0.0.0.0 --port 8080
```

访问：http://localhost:8080

## API 文档

- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

## 端口配置

| 端口 | 说明 |
|------|------|
| 8080 | OpenClaw Manager Web UI |
| 18800-18900 | 新实例默认端口池 |
| 18789 | OpenClaw Gateway 内部端口（容器内固定） |

## 使用场景

1. **多实例管理**：运行多个 OpenClaw 实例，每个实例使用不同的 API Key
2. **环境隔离**：不同项目使用不同的智能体配置
3. **快速部署**：通过模板一键创建新实例

## 技术栈

- **后端**：Python, FastAPI, Docker SDK, SQLite
- **前端**：HTML, CSS, Vanilla JavaScript
- **部署**：Docker, systemd

## 许可证

MIT License