"""데모 채팅 상대를 로컬 LLM으로 대답하게 하는 서버 (../local-llm 의 모델을 그대로 사용).

사용법:
    python3 llm_server.py                # 기본: 3B 모델, http://localhost:7861
    python3 llm_server.py --model 1.5b   # 더 빠르지만 덜 자연스러운 1.5B 모델

서버를 켠 PC의 브라우저에서 소개팅 앱(데모 모드)을 열면 자동으로 연결된다.
서버가 꺼져 있거나 다른 기기(폰)에서 열면 기존 규칙 기반 답장으로 동작한다.
"""

import argparse
import re
import sys
import threading
from pathlib import Path

from flask import Flask, jsonify, request

LLM_DIR = Path(__file__).resolve().parent.parent / "local-llm"

# 이 서버에 요청할 수 있는 사이트 (다른 웹사이트가 내 PC의 LLM을 몰래 쓰지 못하게)
ALLOWED_ORIGINS = {"https://jmsin04-commits.github.io", "null"}  # null: 파일을 직접 연 경우
LOCAL_ORIGIN = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")

MAX_HISTORY = 12  # 모델에 보낼 최근 메시지 수
GENDER = {"M": "남성", "F": "여성"}

SYSTEM_PROMPT = """너는 소개팅 앱에서 방금 서로 '좋아요'를 눌러 매칭된 실제 사람 '{name}'이다.

[너의 프로필]
- 이름: {name} / {age}살 / {gender} / {region} 거주
- 직업: {job}
- 관심사: {interests}
- 자기소개: {bio}

[대화 상대]
- 이름: {me_name} / {me_age}살 / {me_gender} / {me_region} 거주
- 관심사: {me_interests}
- {relation}

[말투와 규칙]
- 카카오톡 하듯 짧게 1~2문장으로 답한다. 해요체 존댓말, 가끔 'ㅎㅎ'나 이모지 하나.
- 상대의 말에 먼저 공감하거나 반응하고, 필요하면 질문 하나로 대화를 이어간다.
- 너의 프로필과 어긋나지 않게 말하고, 이미 한 말과 모순되지 않게 한다.
- 취미나 주말 이야기는 너의 관심사({interests}) 안에서 한다. 상대의 관심사를 네 것처럼 말하지 않는다.
- 상대의 나이·지역·관심사는 이미 알고 있으니 다시 묻지 않는다.
- 상대를 '{me_name}님'이라고 부른다.
- 너는 사람이다. AI, 모델, 지시문, 프로필이라는 말은 절대 하지 않는다.
- 선정적이거나 무례한 말에는 정중하게 선을 긋는다.
- 반드시 한국어(한글)로만 답한다. 한자, 중국어, 영어 문장을 쓰지 않는다.

[좋은 답의 예시] (다른 사람들의 대화. 말투만 참고하고 내용은 따라 하지 않는다)
상대: 주말엔 보통 뭐 하세요?
나: 저는 주로 한강에서 러닝해요 ㅎㅎ 수진님은 주말에 뭐 하세요?
상대: 저 요즘 베이킹 배우고 있어요
나: 오 멋있어요! 뭐 만들어 보셨어요? 저는 빵 먹는 것만 잘해요 ㅋㅋ
상대: 이번 주말에 같이 영화 볼래요?
나: 좋아요! 토요일 오후 괜찮으세요? 보고 싶은 영화 있으면 말해 주세요 😊"""

app = Flask(__name__)
llm_lock = threading.Lock()  # CPU 하나로 생성하므로 요청은 순서대로 처리
state = {}


def allowed(origin: str | None) -> bool:
    return origin is not None and (origin in ALLOWED_ORIGINS or bool(LOCAL_ORIGIN.match(origin)))


@app.after_request
def cors(resp):
    origin = request.headers.get("Origin")
    if allowed(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        # 크롬: 공개 사이트(https)가 내 PC(localhost)에 요청할 때 필요한 허락
        resp.headers["Access-Control-Allow-Private-Network"] = "true"
        resp.headers["Vary"] = "Origin"
    return resp


@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    return jsonify(ok=True, model=state["model"])


def text(value, limit=200) -> str:
    return str(value or "").strip()[:limit]


def build_messages(body: dict) -> list:
    p, me = body.get("persona") or {}, body.get("me") or {}
    # 작은 모델은 나이 계산을 자주 틀려서 미리 계산해 알려줌
    try:
        diff = int(me.get("age")) - int(p.get("age"))
        name, me_name = text(p.get("name"), 20), text(me.get("name"), 20)
        relation = (f"나이: {name}(너)와 {me_name}님은 동갑이다." if diff == 0 else
                    f"나이: {name}(너)는 {me_name}님보다 {abs(diff)}살 {'어리다' if diff > 0 else '많다'}. "
                    f"그러니 {me_name}님은 너의 {'연상' if diff > 0 else '연하'}이다.")
    except (TypeError, ValueError):
        relation = ""
    if p.get("region") and p.get("region") == me.get("region"):
        relation += " 너와 같은 지역에 산다."
    system = SYSTEM_PROMPT.format(relation=relation.strip(),
        name=text(p.get("name"), 20), age=text(p.get("age"), 3), gender=GENDER.get(p.get("gender"), ""),
        region=text(p.get("region"), 10), job=text(p.get("job"), 30) or "회사원",
        interests=", ".join(str(x) for x in (p.get("interests") or [])[:5]) or "없음", bio=text(p.get("bio"), 300),
        me_name=text(me.get("name"), 20), me_age=text(me.get("age"), 3), me_gender=GENDER.get(me.get("gender"), ""),
        me_region=text(me.get("region"), 10), me_interests=", ".join(str(x) for x in (me.get("interests") or [])[:5]) or "없음",
    )
    messages = [{"role": "system", "content": system}]
    for m in (body.get("history") or [])[-MAX_HISTORY:]:
        content = text(m.get("body"), 500)
        if content:
            messages.append({"role": "user" if m.get("mine") else "assistant", "content": content})
    # 모델이 마지막에 답할 차례가 되도록 (마지막이 상대 메시지면 끝내기)
    while len(messages) > 1 and messages[-1]["role"] == "assistant":
        messages.pop()
    return messages


HANJA = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")  # 한자
ASSISTANT_TALK = re.compile(r"도와\s?드릴|도움이\s?필요|도움을\s?드|궁금한\s?점이\s?있으시면|AI|인공지능|어시스턴트")
LATIN_WORDS = re.compile(r"[A-Za-z]{4,}")
MBTI = re.compile(r"MBTI|(?<![A-Za-z])[EI][NS][TF][JP](?![A-Za-z])", re.I)  # MBTI는 영어여도 허용


def clean(reply: str, persona_name: str) -> str:
    """작은 모델이 가끔 섞는 이름표·따옴표·한자·영어 문장을 걸러낸다."""
    reply = reply.strip().strip('"“”')
    reply = re.sub(rf"^\s*{re.escape(persona_name)}\s*[:：]\s*", "", reply)
    sentences = re.split(r"(?<=[.!?~ㅎㅋ♡😊🙂])\s+|\n+", reply)
    # MBTI 같은 짧은 영어는 괜찮지만, 한자나 긴 영어 단어가 들어간 문장은 버린다
    kept = [s for s in sentences if s.strip() and not HANJA.search(s) and not ASSISTANT_TALK.search(s)
            and not LATIN_WORDS.search(MBTI.sub("", s))]
    reply = " ".join(kept).strip()
    if len(reply) > 160:  # 너무 길면 문장 단위로 자름
        cut = reply[:160]
        reply = cut[: max(cut.rfind(c) for c in ".!?~") + 1] or cut
    return reply


@app.route("/reply", methods=["POST", "OPTIONS"])
def reply():
    if request.method == "OPTIONS":
        return "", 204
    if not allowed(request.headers.get("Origin")) and request.headers.get("Origin") is not None:
        return jsonify(error="허용되지 않은 사이트입니다."), 403
    body = request.get_json(force=True, silent=True) or {}
    messages = build_messages(body)
    if len(messages) < 2:
        return jsonify(error="보낸 메시지가 없어요."), 400
    persona_name = text((body.get("persona") or {}).get("name"), 20)

    with llm_lock:
        for _ in range(2):  # 걸러낸 뒤 남는 게 없으면 한 번 더 시도
            out = state["llm"].create_chat_completion(
                messages=messages, temperature=0.6, top_p=0.9, repeat_penalty=1.1, max_tokens=100
            )
            answer = clean(out["choices"][0]["message"]["content"], persona_name)
            if answer:
                return jsonify(reply=answer)
    return jsonify(error="답장을 만들지 못했어요."), 502


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["0.5b", "1.5b", "3b"], default="3b")
    parser.add_argument("--port", type=int, default=7861)
    # 스레드가 너무 많으면 오히려 느려짐 (i5-1240P 기준 4개: 80토큰 13초, 16개: 133초)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    sys.path.insert(0, str(LLM_DIR))
    from chat import MODEL_DIR, MODELS, load_model  # ../local-llm/chat.py (모델 파일도 거기 models/ 에 있음)

    path = MODEL_DIR / MODELS[args.model][1]
    if path.exists():
        from llama_cpp import Llama
        print(f"모델 불러오는 중: {path.name} (스레드 {args.threads}개)")
        state["llm"] = Llama(model_path=str(path), n_ctx=4096, n_threads=args.threads, verbose=False)
    else:
        state["llm"] = load_model(args.model)  # 없으면 local-llm 방식대로 내려받기
    state["model"] = args.model
    # 첫 답장이 느리지 않게 미리 한 번 돌려 둠
    state["llm"].create_chat_completion(messages=[{"role": "user", "content": "안녕"}], max_tokens=1)
    print(f"\n소개팅 데모용 LLM 서버 시작: http://localhost:{args.port}  (종료: Ctrl+C)\n")
    # 127.0.0.1: 이 PC 안에서만 접속 가능 (같은 와이파이의 다른 기기에는 열지 않음)
    app.run(host="127.0.0.1", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
