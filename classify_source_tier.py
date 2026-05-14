#!/usr/bin/env python3
"""fund.source_tier 자동 분류.

각 토큰의 fund.sources 배열을 도메인 기준으로 평가:
  Tier 1: 공식 docs / whitepaper / litepaper / 프로젝트 메인 도메인
  Tier 2: CoinGecko / CryptoRank / Tokenomist / CoinMarketCap / DefiLlama
  Tier 3: 거래소 Academy (bithumb/binance/coinbase) / Medium / 뉴스 기사
  Tier 0: 미검증 (sources 비어있음, 또는 명시 잠정)

토큰의 source_tier = 가장 신뢰도 높은 (낮은 숫자) tier.
빈 sources 또는 토큰이 "공식 docs 미확인" 명시한 경우 → 0.

직접 실행: python3 classify_source_tier.py
"""
import json, re, pathlib, sys

TIER1_PATTERNS = [
    r'docs\.[\w-]+\.(io|com|ai|xyz|org|foundation|tech|finance|fi|so|app)',
    r'whitepaper|litepaper',
    r'(?:gitbook|notion)\.io',
]
TIER2_DOMAINS = {
    'coingecko.com', 'www.coingecko.com',
    'cryptorank.io', 'www.cryptorank.io',
    'tokenomist.ai', 'www.tokenomist.ai',
    'coinmarketcap.com', 'www.coinmarketcap.com',
    'defillama.com', 'www.defillama.com',
    'dropstab.com', 'www.dropstab.com',
}
TIER3_DOMAINS = {
    'medium.com', 'mirror.xyz', 'substack.com',
    'theblock.co', 'decrypt.co', 'cointelegraph.com', 'coindesk.com',
    'banklesstimes.com', 'beincrypto.com', 'chainwire.org',
    'feed.bithumb.com',
    'en.bloomingbit.io',
}

PROJECT_OFFICIAL_HOSTS_OF = {
    'lighter': ['lighter.xyz', 'docs.lighter.xyz'],
    'goplus-security': ['gopluslabs.io'],
    'ethgas-2': ['docs.ethgas.com'],
    'cysic': ['cysic.xyz', 'docs.cysic.xyz'],
    'robo-token-2': ['fabric.foundation', 'fabricprotocol.com'],
    'pha': ['phala.network', 'forum.phala.network'],
    'based-one': ['fabric.foundation'],
    'edgex': ['edgex-1.gitbook.io', 'edgex.exchange'],
    'gensyn': ['gensyn.ai', 'docs.gensyn.ai'],
    'opengradient': ['opengradient.ai', 'docs.opengradient.ai'],
    'stable-2': ['stable.xyz', 'docs.stable.xyz'],
    'the-open-network': ['ton.org', 'telegram.org'],
    'morpho': ['morpho.org', 'docs.morpho.org'],
    'babylon': ['babylonlabs.io', 'docs.babylonlabs.io'],
    'initia': ['initia.xyz', 'docs.initia.xyz'],
    'tria': ['tria.so', 'docs.tria.so'],
    'superform': ['superform.xyz', 'docs.superform.xyz'],
    'kaia': ['kaia.io', 'kaia.foundation', 'docs.kaia.io'],
    'spacecoin-2': ['spacecoin.io', 'spacecoin.xyz'],
}

UNVERIFIED_MARKERS = ('공식 docs 미확인', '잠정 평가')

def classify_url(url, cg_id=None):
    """단일 URL 의 tier 반환 (1/2/3/0)."""
    if not url:
        return 0
    u = url.lower().strip()
    host = re.match(r'^https?://([^/]+)', u)
    host = host.group(1) if host else u
    # Tier 1: 공식 도메인 (cg_id 기반 화이트리스트)
    if cg_id and cg_id in PROJECT_OFFICIAL_HOSTS_OF:
        if any(off in host for off in PROJECT_OFFICIAL_HOSTS_OF[cg_id]):
            return 1
    # Tier 1: 패턴 (docs.*/whitepaper/litepaper)
    for pat in TIER1_PATTERNS:
        if re.search(pat, host):
            return 1
    # Tier 2
    if host in TIER2_DOMAINS:
        return 2
    # Tier 3
    if host in TIER3_DOMAINS:
        return 3
    return 3  # 알 수 없는 기타 도메인 = Tier 3 보수적

def token_source_tier(token):
    """토큰의 source_tier 결정. 미검증 마커 우선 검출 → Tier 0."""
    fund = token.get('fund', {})
    cg_id = token.get('coingecko_id')
    # 미검증 마커 검출
    for k in ('description', 'utility', 'vesting', 'rank_reason', 'category'):
        v = fund.get(k, '') or ''
        if isinstance(v, str) and any(mk in v for mk in UNVERIFIED_MARKERS):
            return 0, 'unverified-marker'
    sources = fund.get('sources') or []
    if not sources:
        return 0, 'no-sources'
    tiers = []
    for src in sources:
        # sources 는 [[name, url], ...] 형식
        if isinstance(src, (list, tuple)) and len(src) >= 2:
            tiers.append(classify_url(src[1], cg_id))
    if not tiers:
        return 0, 'no-valid-urls'
    best = min(tiers)
    return best, f'best-of-{len(tiers)}-sources'

def process(path):
    p = pathlib.Path(path)
    d = json.loads(p.read_text())
    changed = 0
    for t in d.get('tokens', []):
        tier, note = token_source_tier(t)
        fund = t.setdefault('fund', {})
        if fund.get('source_tier') != tier or fund.get('source_tier_note') != note:
            fund['source_tier'] = tier
            fund['source_tier_note'] = note
            changed += 1
        print(f"  {t['symbol']:8} → Tier {tier} ({note})")
    p.write_text(json.dumps(d, ensure_ascii=False, separators=(',', ':')))
    print(f"\n{path.name}: {changed} 토큰 갱신")

if __name__ == '__main__':
    script_dir = pathlib.Path(__file__).parent
    for f in ['dashboard_data_v6_verified.min.json', 'dashboard_data_v72_final.min.json']:
        print(f"\n=== {f} ===")
        process(script_dir / f)
