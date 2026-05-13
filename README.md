# KRW 신규상장 대시보드

빗썸 단독 KRW 신규상장 토큰 분석 · 김프·언락·펀더멘털 비교.

🌐 **[Live Dashboard](https://londonpotato1.github.io/krw-listing-dashboard/)**

## 대시보드

| 대시보드 | 토큰 | 설명 |
|---|---|---|
| [v6](https://londonpotato1.github.io/krw-listing-dashboard/dashboard_v6.html) | 8 | 빗썸 KRW 신규상장 8종. 김프·유통률·언락 비교 |
| [v7.2](https://londonpotato1.github.io/krw-listing-dashboard/dashboard_v72_final.html) | 9 | 텔레그램 사이드 정보 기반 4 카테고리 픽 |

## 구조

```
.
├── index.html                          # 랜딩 페이지
├── dashboard_v6.html                   # v6 빌드 산출물
├── dashboard_v72_final.html            # v7.2 빌드 산출물
├── template_v6.html                    # v6 HTML 템플릿 (__DATA__ 자리표시자)
├── template_v72_final.html             # v7.2 HTML 템플릿
├── build_dashboard_v6.py               # v6 빌드 스크립트
├── build_dashboard_v7.py               # v7.2 빌드 스크립트
├── dashboard_data_v6_verified.min.json # v6 데이터 (verified)
└── dashboard_data_v72_final.min.json   # v7.2 데이터 (verified)
```

## 빌드

```bash
python3 build_dashboard_v6.py   # → dashboard_v6.html
python3 build_dashboard_v7.py   # → dashboard_v72_final.html
```

빌드 파이프라인:
1. verified JSON 로드
2. issue_counts / dist_sum 자동 재계산
3. GLOSSARY 첫 등장 1회 한국어 풀이 삽입 (idempotent)
4. verified JSON 저장
5. HTML 템플릿의 `__DATA__` 자리에 데이터 주입 → 최종 HTML 출력

빌드는 멱등 (두 번 실행해도 md5 동일).

## 데이터 출처

- 가격: CoinGecko, 거래소 공식 API
- 컨트랙트·DEX 유동성: DEX Screener
- 언락 스케줄: TokenUnlocks / 프로젝트 공식 공지
- 환율: exchangerate-api.com

## 보안

- HTML escape (`esc`) + URL scheme allowlist (`safeUrl`) — innerHTML 데이터 주입 경로
- `</script>` breakout 방어 — PAYLOAD 임베드 시 `</` → `<\/` 치환
- 외부 링크 `rel="noopener noreferrer"`

## 면책

본 대시보드는 공개 데이터를 가공한 개인 분석 자료입니다.
**투자 권유가 아니며, 데이터 정확성을 보장하지 않습니다.**
토큰 가격·언락 스케줄·김프는 데이터 수집 시점 기준이며 현재 시세와 다를 수 있습니다.
투자 판단의 모든 책임은 본인에게 있습니다.

## License

MIT — 단, 면책 조항은 데이터 사용 시 함께 표기 권장.
