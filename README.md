# 부동산 브리핑 → 카카오톡 나에게 보내기

매일 오전 9시(KST)에 국내 부동산 뉴스를 요약해 카카오톡 "나와의 채팅"으로 보냅니다.
GitHub Actions에서 돌아가므로 **PC를 꺼두어도 동작**합니다.

---

## STEP 1. 카카오 개발자 앱 만들기 (10분)

[developers.kakao.com](https://developers.kakao.com) 로그인 후:

| 위치 | 할 일 |
|---|---|
| 내 애플리케이션 | **애플리케이션 추가하기** → 앱 이름 아무거나 |
| 앱 설정 → 앱 키 | **REST API 키** 복사해 둠 |
| 앱 설정 → 플랫폼 → Web | 사이트 도메인에 `https://news.google.com` 등록 |
| 제품 설정 → 카카오 로그인 | **활성화 ON** |
| 제품 설정 → 카카오 로그인 → Redirect URI | `https://example.com/oauth` 등록 |
| 제품 설정 → 카카오 로그인 → 동의항목 | **카카오톡 메시지 전송 (`talk_message`)** → 선택 동의로 설정 |

> 사업자등록번호는 필요 없습니다. "나에게 보내기"는 개인 계정으로 가능합니다.
> (친구에게 보내는 건 별도 권한 신청이 필요하지만, 우리는 나에게만 보냅니다.)

---

## STEP 2. refresh token 발급 (1회)

내 PC에서 한 번만 실행합니다.

```bash
pip install requests
python get_token.py
```

브라우저에서 동의하면 `https://example.com/oauth?code=XXXX` 로 이동합니다.
페이지는 안 열려도 정상이고, **주소창의 `code=` 뒤 값**만 복사해 붙여넣으면 됩니다.

출력된 두 값을 다음 단계에서 씁니다. **절대 코드에 하드코딩하거나 남에게 공유하지 마세요.**

---

## STEP 3. GitHub 저장소 + Secrets

1. GitHub에 **Private** 저장소 생성
2. 이 폴더의 파일 전부 push
3. 저장소 → Settings → Secrets and variables → Actions → **New repository secret**

| Secret 이름 | 값 |
|---|---|
| `KAKAO_REST_API_KEY` | STEP 1의 REST API 키 |
| `KAKAO_REFRESH_TOKEN` | STEP 2에서 출력된 값 |
| `ANTHROPIC_API_KEY` | (선택) console.anthropic.com 에서 발급 |

`ANTHROPIC_API_KEY`가 없으면 요약 없이 **헤드라인 목록만** 발송됩니다.
있으면 카테고리별로 정리된 브리핑이 옵니다. 비용은 하루 몇 원 수준입니다.

---

## STEP 4. 테스트

저장소 → **Actions** 탭 → "부동산 브리핑" → **Run workflow**

카톡 "나와의 채팅"으로 메시지가 오면 성공입니다.
이후로는 매일 오전 9시에 자동 발송됩니다.

---

## 커스터마이징

- **검색어**: `main.py`의 `QUERIES` 수정 (예: 관심 지역 추가 `"동탄 아파트"`)
- **시간**: `.github/workflows/daily.yml`의 cron 수정
  - `0 0 * * *` = 09:00 KST / `0 22 * * *` = 07:00 KST / `30 23 * * *` = 08:30 KST
- **요약 스타일**: `main.py`의 `summarize()` 안 prompt 수정

---

## 알아둘 것

- **200자 제한**: 카카오 기본 텍스트 템플릿은 최대 200자까지만 표시됩니다.
  그래서 요약을 190자 단위로 쪼개 여러 건으로 나눠 보냅니다. (1/3, 2/3 …)
- **refresh token 만료**: 유효기간 약 60일. 매일 실행되면 카카오가 자동 갱신하며,
  새 토큰이 발급되면 Actions 로그에 표시됩니다 → Secrets를 그 값으로 교체하세요.
  발송이 갑자기 멈추면 `get_token.py`를 다시 실행하면 됩니다.
- **GitHub Actions cron은 정시에 정확히 안 돌 수 있습니다.** 부하에 따라 5~20분 지연이
  흔합니다. 정확한 시각이 중요하면 cron을 조금 앞당겨 두세요.
- **뉴스 출처**: 구글 뉴스 RSS(무료). 정책 원문이 필요하면 국토교통부 보도자료를,
  가격 데이터는 한국부동산원 주간 동향(매주 목요일)을 별도로 확인하는 걸 권합니다.
