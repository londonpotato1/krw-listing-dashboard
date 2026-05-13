#!/usr/bin/env python3
"""v6: 빌드 시점 자동 검증 + GLOSSARY 자동 치환 + 외부 템플릿 주입.

흐름:
  1) verified JSON 로드 (스크립트 디렉토리 기준)
  2) issue_counts / dist_sum 재계산 (정적 값 덮어쓰기)
  3) GLOSSARY 첫 등장 1회 한국어 풀이 삽입 (idempotent)
  4) verified JSON 다시 저장
  5) template_v6.html 로드 → __DATA__ 치환 → dashboard_v6.html 출력

HTML 템플릿이 template_v6.html 로 분리됨. 빌드 재실행 시 expand/UI 드리프트 없음.
GLOSSARY 변경 시 build_dashboard_v7.py 와 동기화 필요.
"""
import json, pathlib, sys, re

# 약어 풀이 사전 (일반 약어만; 토큰 고유 내용은 수동 큐레이트)
GLOSSARY = {
    'DPoS': '위임 지분증명',
    'PoS': '지분증명',
    'PoW': '작업증명',
    'AVS': '액티브 검증 서비스',
    'AMM': '자동시장조성자',
    'TVL': '예치 자산 가치',
    'MAU': '월간 활성 사용자',
    'ARR': '연간 반복 매출',
    'KYC': '신원인증',
    'ZK': '영지식',
    'L1': '레이어 1',
    'L2': '레이어 2',
    'LP': '유동성 공급',
    'DEX': '탈중앙 거래소',
    'CEX': '중앙화 거래소',
    'TGE': '토큰 생성 이벤트',
    'NFT': '대체불가 토큰',
    'DAO': '탈중앙 자율조직',
}
_GLOSSARY_ORDER = sorted(GLOSSARY.keys(), key=len, reverse=True)

def apply_glossary(text: str) -> str:
    """첫 등장 한 번만 ` (풀이)` 삽입. 이미 직후에 `(풀이)` 있으면 skip → idempotent."""
    if not isinstance(text, str) or not text:
        return text
    for term in _GLOSSARY_ORDER:
        pattern = re.compile(r'(?<![A-Za-z0-9])' + re.escape(term) + r'(?![A-Za-z0-9])')
        m = pattern.search(text)
        if not m:
            continue
        end = m.end()
        rest = text[end:end+30].lstrip()
        if rest.startswith('(') and GLOSSARY[term] in rest[:len(GLOSSARY[term])+5]:
            continue
        text = text[:end] + f'({GLOSSARY[term]})' + text[end:]
    return text

# === 경로: 스크립트와 같은 디렉토리 ===
script_dir = pathlib.Path(__file__).parent
data_path = script_dir / 'dashboard_data_v6_verified.min.json'
template_path = script_dir / 'template_v6.html'
out_path = script_dir / 'dashboard_v6.html'

payload = json.loads(data_path.read_text())

# === 1. 이슈 카운트 자동 재계산 ===
counts = {'critical': 0, 'major': 0, 'minor': 0}
for token in payload['tokens']:
    for sev, _ in token['fund'].get('flags', []):
        key = sev.lower()
        if key in counts:
            counts[key] += 1
payload['meta']['issue_counts'] = counts

# === 2. 분배 합계 검증 ===
dist_errors = []
for token in payload['tokens']:
    dist = token['fund'].get('distribution', [])
    actual_sum = round(sum(p for _, p in dist), 2)
    stored = token['fund'].get('dist_sum')
    if stored is not None and abs(stored - actual_sum) > 0.5:
        dist_errors.append(f"{token['symbol']}: stored={stored} vs actual={actual_sum}")
    token['fund']['dist_sum'] = actual_sum

if dist_errors:
    print("⚠️ 분배 합계 불일치 (자동 정정):", file=sys.stderr)
    for e in dist_errors:
        print(f"  {e}", file=sys.stderr)

# === 3. fx_timestamp 보강 ===
if 'fx_timestamp' not in payload['meta']:
    payload['meta']['fx_timestamp'] = payload['meta'].get('fx_source', '미확인')

# === 4. GLOSSARY 풀이 (idempotent) ===
GLOSS_FIELDS = ['description', 'utility', 'vesting', 'rank_reason']
glossary_applied = 0
for token in payload['tokens']:
    fund = token.get('fund', {})
    for k in GLOSS_FIELDS:
        v = fund.get(k)
        if isinstance(v, str):
            new_v = apply_glossary(v)
            if new_v != v:
                glossary_applied += 1
                fund[k] = new_v

# === 5. 검증 로그 ===
print(f"✅ 빌드 자동 검증 완료:")
print(f"   이슈 카운트: Critical {counts['critical']}, Major {counts['major']}, Minor {counts['minor']}")
print(f"   환율: {payload['meta']['fx_rate']} ({payload['meta']['fx_source']})")
print(f"   GLOSSARY 풀이: {glossary_applied} 필드 (idempotent)")
for token in payload['tokens']:
    s = token['fund']['dist_sum']
    if s < 100:
        print(f"   ⚠ {token['symbol']} 분배 {s}% (미공시 {round(100-s, 2)}%)")

# === 6. verified JSON 저장 + 템플릿 주입 ===
data_raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
data_path.write_text(data_raw)
# script breakout 방어: PAYLOAD 임베드 시 데이터 안의 `</` 시퀀스 차단
data_embed = data_raw.replace('</', '<\\/')

if not template_path.exists():
    print(f"❌ 템플릿 없음: {template_path}", file=sys.stderr)
    sys.exit(1)
template = template_path.read_text()
if '__DATA__' not in template:
    print(f"❌ 템플릿에 __DATA__ 자리표시자 없음", file=sys.stderr)
    sys.exit(1)
html = template.replace('__DATA__', data_embed)
out_path.write_text(html)
print(f"\n✅ HTML 빌드 완료: {out_path} ({len(html)} bytes)")
