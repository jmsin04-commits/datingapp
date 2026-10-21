#!/usr/bin/env bash
# 로컬에서 소개팅 앱 + 로컬 LLM 서버를 한 번에 실행
#   ./run_local.sh              → http://localhost:8000 (LLM: 3B)
#   ./run_local.sh --model 1.5b → 더 빠른 1.5B 모델
# 종료: Ctrl+C (둘 다 함께 꺼짐)
set -e
cd "$(dirname "$0")"

if ! python3 -c "import llama_cpp, flask" 2>/dev/null; then
  echo "필요한 패키지 설치 중 (처음 한 번)..."
  pip install --user -q llama-cpp-python flask --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
fi

python3 llm_server.py "$@" &
LLM_PID=$!
trap 'kill $LLM_PID 2>/dev/null' EXIT

echo "LLM 모델 불러오는 중... (30초 정도)"
for _ in $(seq 1 180); do
  curl -s http://localhost:7861/health >/dev/null 2>&1 && break
  if ! kill -0 $LLM_PID 2>/dev/null; then echo "LLM 서버가 시작되지 못했어요. 위 오류를 확인하세요."; exit 1; fi
  sleep 1
done

echo
echo "  준비 완료 → 브라우저에서 http://localhost:8000"
echo "  (데모 모드, 채팅 상대는 로컬 LLM이 대답합니다. 종료: Ctrl+C)"
echo
python3 -m http.server 8000 --bind 127.0.0.1
