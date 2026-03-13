#!/bin/bash

# 确保在脚本所在目录
cd "$(dirname "$0")"

echo "🚀 Starting Backend Service..."

# 直接使用虚拟环境的 Python 运行，无需手动 activate
./venv/bin/python main.py
