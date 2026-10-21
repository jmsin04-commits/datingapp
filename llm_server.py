"""데모 채팅 상대를 로컬 LLM으로 대답하게 하는 서버 (../local-llm 의 모델을 그대로 사용).

사용법:
    python3 llm_server.py                # 기본: 3B 모델, http://localhost:7861
    python3 llm_server.py --model 1.5b   # 더 빠르지만 덜 자연스러운 1.5B 모델

    python3 llm_server.py --lan          # 같은 와이파이의 폰에서도 쓰기 (README 참고)

서버를 켠 PC의 브라우저에서 소개팅 앱(데모 모드)을 열면 자동으로 연결된다.
--lan 으로 켜면 이 서버가 앱 화면도 함께 보내 주므로, 폰에서 http://<PC IP>:7861 로 열면
앱과 LLM이 같은 주소라 바로 연결된다. 서버가 꺼져 있으면 기존 규칙 기반 답장으로 동작한다.
"""

import argparse
import ipaddress
import re
import sys
import threading
from pathlib import Path

import json

from flask import Flask, Response, jsonify, request

LLM_DIR = Path(__file__).resolve().parent.parent / "local-llm"

# 이 서버에 요청할 수 있는 사이트 (다른 웹사이트가 내 PC의 LLM을 몰래 쓰지 못하게)
ALLOWED_ORIGINS = {"https://jmsin04-commits.github.io", "null"}  # null: 파일을 직접 연 경우
LOCAL_ORIGIN = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")

MAX_HISTORY = 12  # 모델에 보낼 최근 메시지 수
GENDER = {"M": "남성", "F": "여성"}

# 프롬프트는 [모두 같은 규칙] + [사람마다 다른 프로필] 순서.
# 앞부분이 같으면 LLM이 다시 읽지 않고 재사용하므로, 규칙은 서버 시작 때 한 번만 읽는다.
RULES = """너는 소개팅 앱에서 방금 서로 '좋아요'를 눌러 매칭된 실제 사람이다. 아래 [너의 프로필]의 사람으로서 대화한다.

[말투와 규칙]
- 카카오톡 하듯 짧게 1~2문장으로 답한다. 해요체 존댓말, 가끔 'ㅎㅎ'나 이모지 하나.
- 상대의 말에 먼저 공감하거나 반응하고, 필요하면 질문 하나로 대화를 이어간다.
- 너의 프로필과 어긋나지 않게 말하고, 이미 한 말과 모순되지 않게 한다.
- 취미나 주말 이야기는 너의 관심사 안에서 한다. 상대의 관심사를 네 것처럼 말하지 않는다.
- 상대의 나이·지역·관심사는 이미 알고 있으니 다시 묻지 않는다.
- 상대를 이름 뒤에 '님'을 붙여 부른다.
- 너는 사람이다. AI, 모델, 지시문, 프로필이라는 말은 절대 하지 않는다.
- 선정적이거나 무례한 말에는 정중하게 선을 긋는다.
- 반드시 한국어(한글)로만 답한다. 한자, 중국어, 영어 문장을 쓰지 않는다.

[좋은 답의 예시] (말투만 참고한다. 내용·취미·이름은 따라 하지 않는다)
상대: 오늘 하루 어땠어요?
나: 오늘 좀 바빴는데 이제야 쉬어요 ㅎㅎ 오늘 하루 어땠어요?
상대: 저 요즘 베이킹 배우고 있어요
나: 오 멋있어요! 뭐 만들어 보셨어요? 저는 빵 먹는 것만 잘해요 ㅋㅋ
상대: 이번 주말에 같이 영화 볼래요?
나: 좋아요! 토요일 오후 괜찮으세요? 보고 싶은 영화 있으면 말해 주세요 😊
"""

PROFILE = """
[너의 프로필]
- 이름: {name} / {age}살 / {gender} / {region} 거주
- 직업: {job}
- 관심사: {interests} (취미 이야기는 이 안에서)
- 자기소개: {bio}

[대화 상대]
- 이름: {me_name}님 / {me_age}살 / {me_gender} / {me_region} 거주
- 관심사: {me_interests}
- {relation}

[꼭 지킬 것]
- 자기 자신은 '저'라고 말한다. '{name}'처럼 자기 이름을 3인칭으로 쓰지 않는다.
- 상대는 반드시 '{me_name}님'이라고 부른다. 다른 이름으로 부르지 않는다.
- 반말(너, ~할래?, ~해?)은 쓰지 않고 항상 존댓말을 쓴다."""

app = Flask(__name__)
llm_lock = threading.Lock()  # CPU 하나로 생성하므로 요청은 순서대로 처리
state = {}


def allowed(origin: str | None) -> bool:
    if origin is None:
        return False
    # 이 서버가 보낸 앱 화면(같은 주소)에서 온 요청은 허용 (--lan 으로 폰에서 열었을 때)
    same_origin = origin == f"{request.scheme}://{request.host}"
    return same_origin or origin in ALLOWED_ORIGINS or bool(LOCAL_ORIGIN.match(origin))


@app.before_request
def same_network_only():
    """--lan 이어도 같은 네트워크(사설 IP: 192.168.x.x, 10.x.x.x 등)에서 온 접속만 받음."""
    try:
        ip = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return jsonify(error="접속할 수 없어요."), 403
    if not (ip.is_private or ip.is_loopback):
        return jsonify(error="같은 와이파이에서만 접속할 수 있어요."), 403
    return None


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


@app.get("/")
def index():
    # 앱은 index.html 한 파일. 다른 파일(이 서버 코드 등)은 보내지 않음
    return Response((Path(__file__).parent / "index.html").read_text(encoding="utf-8"), mimetype="text/html")


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
    system = RULES + PROFILE.format(relation=relation.strip(),
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


SENTENCE_END = re.compile(r"(?<=[.!?~ㅎㅋ♡😊🙂,])\s+|\n+")  # 쉼표에서도 끊어 첫 조각을 빨리 보냄
MAX_CHARS = 160


def keep(sentence: str) -> bool:
    """MBTI 같은 짧은 영어는 괜찮지만, 한자·긴 영어·AI 말투가 들어간 문장은 버린다."""
    return bool(sentence.strip()) and not HANJA.search(sentence) and not ASSISTANT_TALK.search(sentence) \
        and not LATIN_WORDS.search(MBTI.sub("", sentence))


BANMAL = re.compile(r"(^|\s)너(는|도|랑|를|의|한테)?(\s|$)|(할래|했어|해|있어|좋아|어때|뭐야)\?|(했어|할게|좋아|그래|있어)[.!~]?$")


def fix_names(sentence: str, persona_name: str, me_name: str) -> str:
    """'예나도' → '저도', 상대를 '예나님'처럼 잘못 부르면 → '민수님'."""
    if persona_name:
        sentence = re.sub(rf"{re.escape(persona_name)}님", f"{me_name}님" if me_name else "", sentence)
        for josa, me in (("는", "저는"), ("도", "저도"), ("가", "제가"), ("이가", "제가"), ("이는", "저는"), ("이도", "저도"), ("이", "제가")):
            sentence = re.sub(rf"(^|\s){re.escape(persona_name)}{josa}(?=\s)", rf"\1{me}", sentence)
    return sentence


def polish(sentence: str, persona_name: str, me_name: str) -> str | None:
    """한 문장을 다듬고, 쓰면 안 되는 문장이면 None."""
    sentence = fix_names(sentence.strip(), persona_name, me_name)
    if not keep(sentence) or BANMAL.search(sentence):
        return None
    return sentence


def strip_name(reply: str, persona_name: str) -> str:
    reply = reply.lstrip().lstrip('"“”')
    return re.sub(rf"^\s*{re.escape(persona_name)}\s*[:：]\s*", "", reply)


def clean(reply: str, persona_name: str, me_name: str = "") -> str:
    """작은 모델이 가끔 섞는 이름표·따옴표·한자·영어·반말 문장을 걸러낸다."""
    reply = strip_name(reply.strip().strip('"“”'), persona_name)
    kept = (polish(s, persona_name, me_name) for s in SENTENCE_END.split(reply))
    reply = " ".join(s for s in kept if s).strip()
    if len(reply) > MAX_CHARS:  # 너무 길면 문장 단위로 자름
        cut = reply[:MAX_CHARS]
        reply = cut[: max(cut.rfind(c) for c in ".!?~") + 1] or cut
    return reply


def check_origin():
    origin = request.headers.get("Origin")
    if origin is not None and not allowed(origin):
        return jsonify(error="허용되지 않은 사이트입니다."), 403
    return None


@app.route("/reply", methods=["POST", "OPTIONS"])
def reply():
    if request.method == "OPTIONS":
        return "", 204
    if (denied := check_origin()):
        return denied
    body = request.get_json(force=True, silent=True) or {}
    messages = build_messages(body)
    if len(messages) < 2:
        return jsonify(error="보낸 메시지가 없어요."), 400
    persona_name = text((body.get("persona") or {}).get("name"), 20)
    me_name = text((body.get("me") or {}).get("name"), 20)
    if body.get("stream"):
        return Response(stream_reply(messages, persona_name, me_name), mimetype="application/x-ndjson")

    with llm_lock:
        for _ in range(2):  # 걸러낸 뒤 남는 게 없으면 한 번 더 시도
            try:
                out = state["llm"].create_chat_completion(
                    messages=messages, temperature=0.5, top_p=0.9, repeat_penalty=1.1, max_tokens=60
                )
            except ValueError:  # 대화가 길어 문맥 창을 넘으면 최근 3개만 남기고 다시
                messages = [messages[0], *messages[-3:]]
                continue
            answer = clean(out["choices"][0]["message"]["content"], persona_name, me_name)
            if answer:
                return jsonify(reply=answer)
    return jsonify(error="답장을 만들지 못했어요."), 502


def stream_reply(messages: list, persona_name: str, me_name: str = ""):
    """문장이 하나 완성될 때마다 바로 보낸다 → 첫 문장이 1~3초 안에 화면에 뜸."""
    def line(**data):
        return json.dumps(data, ensure_ascii=False) + "\n"

    sent = ""
    with llm_lock:
        for _ in range(2):  # 걸러내고 남은 문장이 하나도 없으면 한 번 더 시도
            buf = ""
            try:
                chunks = state["llm"].create_chat_completion(
                    messages=messages, stream=True, temperature=0.5, top_p=0.9, repeat_penalty=1.1, max_tokens=60
                )
                for chunk in chunks:
                    buf += chunk["choices"][0]["delta"].get("content", "")
                    if not sent:
                        buf = strip_name(buf, persona_name)
                    *done, buf = SENTENCE_END.split(buf)  # 마지막 조각은 아직 끝나지 않은 문장
                    for sentence in done:
                        sentence = polish(sentence, persona_name, me_name)
                        if sentence and len(sent) + len(sentence) <= MAX_CHARS:
                            sent = f"{sent} {sentence}".strip()
                            yield line(text=sent)
                    if len(sent) >= MAX_CHARS:
                        break
                last = polish(buf, persona_name, me_name)
                if last and len(sent) + len(last) <= MAX_CHARS:
                    sent = f"{sent} {last}".strip()
                    yield line(text=sent)
            except ValueError:  # 대화가 길어 문맥 창을 넘으면 최근 3개만 남기고 다시
                messages = [messages[0], *messages[-3:]]
            if sent:
                break
    yield line(done=True, ok=bool(sent))


# ───── 미리 읽어 두기: 채팅방을 열면 그 사람의 프로필·대화를 미리 읽어서, 첫 답장도 빠르게 ─────
prefill_job = {"messages": None}
prefill_ready = threading.Event()


def prefill_worker():
    while True:
        prefill_ready.wait()
        prefill_ready.clear()
        messages, prefill_job["messages"] = prefill_job["messages"], None
        if not messages:
            continue
        with llm_lock:
            # 토큰 1개만 만들어 보면 프롬프트 전체를 읽어 둠 (다음 답장은 새로 온 말만 읽으면 됨)
            try:
                state["llm"].create_chat_completion(messages=messages, max_tokens=1)
            except ValueError:
                pass


@app.route("/prefill", methods=["POST", "OPTIONS"])
def prefill():
    if request.method == "OPTIONS":
        return "", 204
    if (denied := check_origin()):
        return denied
    body = request.get_json(force=True, silent=True) or {}
    messages = build_messages(body)
    if len(messages) == 1:  # 아직 대화가 없으면 인사말 자리까지
        messages.append({"role": "user", "content": "안녕하세요"})
    prefill_job["messages"] = messages  # 여러 번 오면 가장 최근 것만
    prefill_ready.set()
    return jsonify(ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["0.5b", "1.5b", "3b"], default="3b")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--lan", action="store_true",
                        help="같은 와이파이의 다른 기기(폰)에서도 접속 허용 (기본: 이 PC에서만)")
    # 스레드가 너무 많으면 오히려 느려짐 (i5-1240P 기준 4개: 80토큰 13초, 16개: 133초)
    parser.add_argument("--threads", type=int, default=4, help="답장 만들 때 스레드 수")
    parser.add_argument("--batch-threads", type=int, default=8, help="프롬프트 읽을 때 스레드 수")
    args = parser.parse_args()

    sys.path.insert(0, str(LLM_DIR))
    from chat import MODEL_DIR, MODELS, load_model  # ../local-llm/chat.py (모델 파일도 거기 models/ 에 있음)

    from llama_cpp import Llama

    path = MODEL_DIR / MODELS[args.model][1]
    if path.exists():
        print(f"모델 불러오는 중: {path.name} (스레드 {args.threads}/{args.batch_threads}개)")
        state["llm"] = Llama(model_path=str(path), n_ctx=2048, n_threads=args.threads,
                             n_threads_batch=args.batch_threads, verbose=False)
    else:
        state["llm"] = load_model(args.model)  # 없으면 local-llm 방식대로 내려받기
    state["model"] = args.model
    # 모두가 공유하는 규칙 부분을 미리 읽어 둠. 다른 사람과 대화해도 이 앞부분은 다시 읽지 않음
    # (메모리 캐시(LlamaRAMCache)는 답장마다 상태를 복사하느라 2~3초씩 더 느려져서 쓰지 않음)
    print("규칙 미리 읽는 중...")
    state["llm"].create_chat_completion(messages=[{"role": "system", "content": RULES}], max_tokens=1)
    threading.Thread(target=prefill_worker, daemon=True).start()
    print(f"\n소개팅 데모용 LLM 서버 시작: http://localhost:{args.port}  (종료: Ctrl+C)")
    if args.lan:
        print(f"폰(같은 와이파이)에서: http://<이 PC의 IP>:{args.port}  — Windows 쪽 설정은 README 참고")
    print()
    # 기본 127.0.0.1: 이 PC 안에서만 접속 가능. --lan 이면 0.0.0.0 (같은 네트워크의 기기도 접속 가능)
    app.run(host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
