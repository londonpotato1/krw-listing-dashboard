#!/usr/bin/env python3
"""v7: 카테고리별 픽 대시보드 + GLOSSARY + 외부 템플릿.

흐름:
  1) dashboard_data_v72_final.min.json 로드 (스크립트 디렉토리)
  2) issue_counts / dist_sum 자동 검증
  3) GLOSSARY 첫 등장 풀이 (idempotent)
  4) verified JSON 다시 저장
  5) template_v72_final.html → __DATA__ 치환 → dashboard_v72_final.html 출력

GLOSSARY 변경 시 build_dashboard_v6.py 와 동기화 필요.
"""
import json, pathlib, sys, re

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

script_dir = pathlib.Path(__file__).parent
data_path = script_dir / 'dashboard_data_v72_final.min.json'
template_path = script_dir / 'template_v72_final.html'
out_path = script_dir / 'dashboard_v72_final.html'

payload = json.loads(data_path.read_text())

# 자동 검증
counts = {'critical': 0, 'major': 0, 'minor': 0}
for t in payload['tokens']:
    for sev, _ in t['fund'].get('flags', []):
        k = sev.lower()
        if k in counts:
            counts[k] += 1
payload['meta']['issue_counts'] = counts

dist_errors = []
for t in payload['tokens']:
    dist = t['fund'].get('distribution', [])
    actual = round(sum(p for _, p in dist), 2)
    stored = t['fund'].get('dist_sum')
    if stored is not None and abs(stored - actual) > 0.5:
        dist_errors.append(f"{t['symbol']}: stored={stored} vs actual={actual}")
    t['fund']['dist_sum'] = actual

if dist_errors:
    print("⚠️ 분배 합계 불일치:", file=sys.stderr)
    for e in dist_errors:
        print(f"  {e}", file=sys.stderr)

# fx_timestamp fallback (v6 과 동일 설계)
if 'fx_timestamp' not in payload['meta']:
    payload['meta']['fx_timestamp'] = payload['meta'].get('fx_source', '미확인')

# GLOSSARY 적용
GLOSS_FIELDS = ['description', 'utility', 'vesting', 'rank_reason']
glossary_applied = 0
for t in payload['tokens']:
    fund = t.get('fund', {})
    for k in GLOSS_FIELDS:
        v = fund.get(k)
        if isinstance(v, str):
            new_v = apply_glossary(v)
            if new_v != v:
                glossary_applied += 1
                fund[k] = new_v

print(f"✅ v7 빌드 자동 검증:")
print(f"   토큰: {len(payload['tokens'])}개")
print(f"   이슈: Critical {counts['critical']}, Major {counts['major']}, Minor {counts['minor']}")
print(f"   분배: {len(dist_errors)} 불일치")
print(f"   GLOSSARY 풀이: {glossary_applied} 필드 (idempotent)")

data_raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
data_path.write_text(data_raw)
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
print(f"\n✅ v7 HTML 빌드 완료: {out_path} ({len(html)} bytes)")
