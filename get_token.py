"""
[1회만 실행] 카카오 refresh_token 발급 스크립트

사전 준비 (developers.kakao.com):
  1. 애플리케이션 추가하기 → 앱 생성
  2. [앱 키] 에서 'REST API 키' 복사
  3. [카카오 로그인] → 활성화 ON
  4. [카카오 로그인] → Redirect URI 에 https://example.com/oauth 등록
  5. [카카오 로그인] → [동의항목] → '카카오톡 메시지 전송(talk_message)' 을 선택 동의로 설정
  6. [앱] → [플랫폼] → Web 사이트 도메인에 https://news.google.com 등록

사용법:
  python get_token.py
"""

import sys
import webbrowser
from urllib.parse import urlencode

import requests

REDIRECT_URI = "https://example.com/oauth"


def main() -> None:
    rest_api_key = input("REST API 키를 붙여넣으세요: ").strip()
    if not rest_api_key:
        sys.exit("REST API 키가 필요합니다.")

    auth_url = "https://kauth.kakao.com/oauth/authorize?" + urlencode(
        {
            "client_id": rest_api_key,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "talk_message",
        }
    )

    print("\n아래 주소를 브라우저에서 열고 '동의하고 계속하기'를 누르세요.")
    print(auth_url)
    print(
        "\n동의하면 https://example.com/oauth?code=XXXXX 로 이동합니다."
        "\n(페이지는 안 열려도 정상입니다. 주소창의 code= 뒤 값만 필요합니다.)\n"
    )
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    code = input("주소창의 code= 뒤 값을 붙여넣으세요: ").strip()
    if not code:
        sys.exit("인가 코드가 필요합니다.")

    resp = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": rest_api_key,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
        timeout=15,
    )

    if resp.status_code != 200:
        sys.exit(f"토큰 발급 실패 ({resp.status_code}): {resp.text}")

    data = resp.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        sys.exit(f"refresh_token이 응답에 없습니다: {data}")

    print("\n" + "=" * 60)
    print("발급 완료. 아래 두 값을 GitHub Secrets에 등록하세요.")
    print("(절대 코드나 채팅에 붙여넣지 마세요.)")
    print("=" * 60)
    print(f"KAKAO_REST_API_KEY = {rest_api_key}")
    print(f"KAKAO_REFRESH_TOKEN = {refresh_token}")
    print("=" * 60)
    print("\nrefresh_token 유효기간은 약 60일입니다.")
    print("매일 실행되면 카카오가 자동 갱신해 주지만, 만료 시 이 스크립트를 다시 실행하세요.")


if __name__ == "__main__":
    main()
