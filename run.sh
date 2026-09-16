#!/bin/bash
# 拼豆图纸生成器 — Web 版启动
cd "$(dirname "$0")"

# 找一个有依赖的 python
PY=""
for cand in /Users/xbowlove/.hermes/hermes-agent/venv/bin/python3 \
            "$(command -v python3)"; do
  "$cand" -c "import PIL, fastapi, uvicorn" 2>/dev/null && PY="$cand" && break
done
[ -z "$PY" ] && { echo "需要 PIL + fastapi + uvicorn: pip install pillow fastapi uvicorn python-multipart"; exit 1; }

PORT="${PINDOU_PORT:-8600}"
echo "拼豆图纸生成器 → http://127.0.0.1:$PORT"
exec "$PY" server.py
