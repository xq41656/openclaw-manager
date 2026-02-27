#!/bin/bash

# OpenClaw Manager 快速启动脚本

echo "🚀 OpenClaw Manager 启动脚本"
echo "================================"

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

# 检查 Docker 运行状态
if ! docker info &> /dev/null; then
    echo "❌ Docker 守护进程未运行，请启动 Docker"
    exit 1
fi

echo "✅ Docker 已就绪"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

echo "✅ Python 已就绪"

# 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "📥 安装依赖..."
pip install -q -r requirements.txt

# 启动服务
echo ""
echo "🌟 启动 OpenClaw Manager..."
echo "📖 API 文档: http://localhost:8000/docs"
echo "🛑 按 Ctrl+C 停止服务"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
