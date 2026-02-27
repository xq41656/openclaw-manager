# OpenClaw Manager - 完整版

## 项目结构
```
openclaw-manager/
├── config.py           # 配置管理
├── database.py         # 数据库模型
├── docker_service.py   # Docker 服务（端口池）
├── openclaw_service.py # OpenClaw 服务（配置/健康）
├── agent_api.py        # 智能体 API
├── project_api.py      # 项目 API
├── audit_service.py    # 审计日志
├── main.py             # 主应用入口
├── templates/          # Web 界面
│   └── dashboard.html
└── requirements.txt
```

## 快速启动

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## API 文档
- Swagger UI: http://localhost:8000/docs
- 仪表盘: http://localhost:8000/
