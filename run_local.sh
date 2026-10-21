#!/usr/bin/env bash
# 로컬에서 소개팅 앱 + 로컬 LLM 서버를 한 번에 실행
#   ./run_local.sh              → http://localhost:8000 (LLM: 3B)
#   ./run_local.sh --model 1.5b → 더 빠른 1.5B 모델
#   ./run_local.sh --lan        → 같은 와이파이의 폰에서도 (http://<PC IP>:7861, README 참고)
#   ./run_local.sh --lan --port 5000 → 같은 와이파이에서 http://<PC IP>:5000
# 종료: Ctrl+C (둘 다 함께 꺼짐)
set -e
cd "$(dirname "$0")"

# --port 값 읽기 (LLM 서버 겸 다른 기기용 주소의 포트, 기본 7861)
PORT=7861
prev=""
for a in "$@"; do [ "$prev" = "--port" ] && PORT="$a"; prev="$a"; done

if ! python3 -c "import llama_cpp, flask" 2>/dev/null; then
  echo "필요한 패키지 설치 중 (처음 한 번)..."
  pip install --user -q llama-cpp-python flask --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
fi

# 이미 켜져 있는 서버가 있으면 알려 주고 멈춤 (예전 실행이 남아 있는 경우)
for port in 8000 $PORT; do
  if python3 -c "import socket,sys; s=socket.socket(); sys.exit(s.connect_ex(('127.0.0.1',$port))!=0)"; then
    echo "포트 $port 를 이미 다른 프로그램이 쓰고 있어요. 예전에 켠 서버를 끄고 다시 실행하세요."
    echo "  (확인: ps aux | grep -E 'http.server|llm_server')"
    exit 1
  fi
done

python3 llm_server.py "$@" &
LLM_PID=$!
trap 'kill $LLM_PID 2>/dev/null' EXIT

echo "LLM 모델 불러오는 중... (30초 정도)"
for _ in $(seq 1 180); do
  curl -s http://localhost:$PORT/health >/dev/null 2>&1 && break
  if ! kill -0 $LLM_PID 2>/dev/null; then echo "LLM 서버가 시작되지 못했어요. 위 오류를 확인하세요."; exit 1; fi
  sleep 1
done

echo
if [ "$PORT" = 7861 ]; then
  echo "  준비 완료 → 브라우저에서 http://localhost:8000"
else
  echo "  준비 완료 → 이 PC에서는 http://localhost:$PORT"
fi
case " $* " in *" --lan "*) echo "  같은 와이파이의 다른 기기에서는 → http://<이 PC의 IP>:$PORT  (Windows 설정은 README 참고)";; esac
echo "  (데모 모드, 채팅 상대는 로컬 LLM이 대답합니다. 종료: Ctrl+C)"
echo
python3 -m http.server 8000 --bind 127.0.0.1
