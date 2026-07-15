"""
매일 오전 9시(KST) 국내 부동산 뉴스 요약을 카카오톡 '나와의 채팅'으로 발송.

필요한 환경변수 (GitHub Secrets):
  KAKAO_REST_API_KEY   : 카카오 REST API 키
  KAKAO_REFRESH_TOKEN  : get_token.py 로 발급받은 refresh token
  ANTHROPIC_API_KEY    : (선택) 없으면 요약 없이 헤드라인만 발송
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse

import feedparser
import requests

KST = timezone(timedelta(hours=9))
TEXT_LIMIT = 190  # 카카오 텍스트 템플릿 표시 한도 200자 — 여유 두고 190
TOP_LINKS = 5  # 요약 뒤에 개별 링크로 보낼 주요 기사 개수

# 카카오는 앱에 '등록된 도메인' 링크만 열어준다. 뉴스사 도메인은 수백 개라 다 등록할 수
# 없으므로, 등록해 둔 GitHub Pages 페이지를 거쳐 실제 기사로 넘긴다.
# 형식: ".../go.html?u="  (뒤에 실제 기사 URL을 인코딩해 붙인다)
REDIRECT_BASE = "https://lucas-dy.github.io/mobunet-briefing/go.html?u="

# 수집할 검색어. 관심사에 맞게 자유롭게 수정하세요.
QUERIES = [
    "부동산 정책 대출규제",
    "아파트 매매가격 전세",
    "청약 분양 경쟁률",
    "재건축 재개발 정비사업",
    "부동산 PF 건설사",
    "금리 주택담보대출",
]

MORE_LINK = "https://news.google.com/search?q=%EB%B6%80%EB%8F%99%EC%82%B0&hl=ko&gl=KR&ceid=KR%3Ako"


# ---------------------------------------------------------------- 1. 뉴스 수집
def collect_news() -> list[dict]:
    seen: set[str] = set()
    articles: list[dict] = []

    for query in QUERIES:
        url = (
            "https://news.google.com/rss/search?"
            f"q={quote(query)}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
        )
        try:
            feed = feedparser.parse(url)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] RSS 실패 ({query}): {exc}", file=sys.stderr)
            continue

        for entry in feed.entries[:12]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            key = title.split(" - ")[0][:40]
            if key in seen:
                continue
            seen.add(key)
            articles.append(
                {
                    "title": title,
                    "link": entry.get("link", ""),
                    "source": entry.get("source", {}).get("title", ""),
                }
            )
        time.sleep(0.5)

    print(f"[info] 수집된 기사 {len(articles)}건")
    return articles


# ------------------------------------------------------------- 2. Claude 요약
def summarize(articles: list[dict]) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    today = datetime.now(KST).strftime("%m/%d")

    if not api_key:
        lines = [f"[부동산 브리핑] {today}", ""]
        lines += [f"· {a['title']}" for a in articles[:12]]
        return "\n".join(lines)

    headlines = "\n".join(f"- {a['title']}" for a in articles[:60])

    prompt = f"""아래는 오늘 수집한 국내 부동산 관련 뉴스 헤드라인입니다.

{headlines}

이걸 바탕으로 카카오톡으로 읽을 짧은 아침 브리핑을 작성해줘.

규칙:
- 전체 900자 이내
- 아래 카테고리 중 실제 내용이 있는 것만 사용 (없으면 생략):
  [정책·규제] [시장동향] [청약·분양] [업계·PF]
- 각 카테고리는 불릿 2개 이내, 한 불릿은 한 문장
- 헤드라인에 없는 내용은 절대 지어내지 말 것
- 숫자와 지역명은 헤드라인에 나온 그대로만 사용
- 맨 앞줄에 오늘의 핵심을 한 문장으로
- 이모지, 마크다운 기호(**, ##) 사용 금지
- 브리핑 본문만 출력. 다른 말 붙이지 말 것"""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-5",
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=90,
    )
    resp.raise_for_status()

    body = "".join(
        block["text"] for block in resp.json()["content"] if block["type"] == "text"
    ).strip()

    return f"[부동산 브리핑] {today}\n\n{body}"


# --------------------------------------------------------------- 3. 카카오 발송
def get_access_token() -> str:
    resp = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": os.environ["KAKAO_REST_API_KEY"],
            "refresh_token": os.environ["KAKAO_REFRESH_TOKEN"],
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if "refresh_token" in data:
        print(
            "[중요] 카카오가 새 refresh_token을 발급했습니다. "
            "GitHub Secrets의 KAKAO_REFRESH_TOKEN을 아래 값으로 교체하세요:"
        )
        print(f"::add-mask::{data['refresh_token']}")
        print(data["refresh_token"])

    return data["access_token"]


def chunk(text: str, size: int = TEXT_LIMIT) -> list[str]:
    """문단 경계를 최대한 지키면서 size자 이하로 자른다."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > size:  # 한 줄이 너무 길면 강제 분할
            chunks.append(line[:size])
            line = line[size:]
        if len(current) + len(line) + 1 > size:
            if current:
                chunks.append(current.strip())
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current.strip():
        chunks.append(current.strip())
    return chunks


def decode_google_news_url(url: str, timeout: int = 20) -> str | None:
    """구글 뉴스 RSS 중계 링크(.../articles/CBMi…)를 실제 기사 URL로 변환.

    구글이 방식을 바꾸는 등 실패하면 None을 돌려주고, 호출부에서 폴백한다.
    """
    try:
        art_id = urlparse(url).path.split("/")[-1]
        if "news.google.com" not in url:
            return url  # 이미 실제 주소면 그대로 사용

        headers = {"User-Agent": "Mozilla/5.0"}
        page = requests.get(
            f"https://news.google.com/rss/articles/{art_id}",
            headers=headers,
            timeout=timeout,
        )
        page.raise_for_status()
        sig = re.search(r'data-n-a-sg="([^"]+)"', page.text)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page.text)
        if not (sig and ts):
            return None

        req = json.dumps(
            [
                "garturlreq",
                [
                    ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
                     None, None, None, None, None, 0, 1],
                    "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0,
                ],
                art_id, int(ts.group(1)), sig.group(1),
            ]
        )
        resp = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={
                **headers,
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            },
            data={"f.req": json.dumps([[["Fbv4je", req, None, "generic"]]])},
            timeout=timeout,
        )
        resp.raise_for_status()
        for line in resp.text.splitlines():
            if "garturlres" in line:
                return json.loads(json.loads(line)[0][2])[1]
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 링크 디코딩 실패: {exc}", file=sys.stderr)
        return None


def article_link(article: dict) -> str:
    """기사 메시지에 걸 링크. 실제 기사 주소를 등록 도메인(리다이렉트) 뒤에 붙인다.

    디코딩 실패 시엔 등록 도메인인 구글 뉴스 검색으로 폴백(제목으로 검색).
    """
    real = decode_google_news_url(article.get("link", ""))
    if real:
        return REDIRECT_BASE + quote(real, safe="")
    title = article["title"].rsplit(" - ", 1)[0].strip()
    return f"https://news.google.com/search?q={quote(title)}&hl=ko&gl=KR&ceid=KR:ko"


def send_message(
    access_token: str, text: str, link_url: str, button_title: str | None = None
) -> None:
    """카카오 '나에게' 텍스트 메시지 1건 발송. 메시지 전체가 link_url로 연결된다."""
    template = {
        "object_type": "text",
        "text": text[:200],
        "link": {"web_url": link_url, "mobile_web_url": link_url},
    }
    if button_title:
        template["button_title"] = button_title

    resp = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[error] 발송 실패: {resp.text}", file=sys.stderr)
        resp.raise_for_status()


def send_to_kakao(text: str, articles: list[dict]) -> None:
    access_token = get_access_token()

    # 1) 요약 본문 (200자 제한 때문에 여러 건으로 쪼갬)
    parts = chunk(text)
    total = len(parts)
    for i, part in enumerate(parts, start=1):
        suffix = f"\n\n({i}/{total})" if total > 1 else ""
        button = "뉴스 더보기" if i == total else None
        send_message(access_token, part + suffix, MORE_LINK, button)
        print(f"[info] 요약 발송 {i}/{total}")
        time.sleep(1)

    # 2) 주요 기사: 각 메시지를 누르면 해당 기사로 이동
    linkable = [a for a in articles if a.get("link")][:TOP_LINKS]
    for j, a in enumerate(linkable, start=1):
        # 제목 끝의 " - 언론사" 꼬리표 제거
        title = a["title"].rsplit(" - ", 1)[0].strip()
        source = a.get("source", "")
        body = f"[주요 기사 {j}/{len(linkable)}] {title}"
        if source:
            body += f"\n— {source}"
        send_message(access_token, body, article_link(a), "기사 보기")
        print(f"[info] 기사 발송 {j}/{len(linkable)}")
        time.sleep(1)


def main() -> None:
    articles = collect_news()
    if not articles:
        print("[warn] 수집된 기사가 없습니다. 발송을 건너뜁니다.")
        return

    text = summarize(articles)
    print("---- 발송할 내용 ----")
    print(text)
    print("--------------------")

    send_to_kakao(text, articles)


if __name__ == "__main__":
    main()
