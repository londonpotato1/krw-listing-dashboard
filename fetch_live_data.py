#!/usr/bin/env python3
"""실시간 데이터 갱신.

verified JSON 의 다음 필드를 외부 API 로 덮어쓴다:
  meta_strip.market_cap_usd / total_volume_usd / circulating_supply / dex_liquidity_usd / dex_top_pool
  meta.fx_rate / fx_timestamp
  fund.kimchi.bithumb_krw / global_usd / kimchi_pct  (같은 배치 timestamp 로 일관성 보장)

같은 수집 배치 timestamp 만 사용한다 — Codex 가이드라인 ("섞이면 stale 표시").

호출 빈도: GitHub Actions 30분 cron. ENV: COINGECKO_API_KEY (Demo 무료, optional).
"""
import json, os, sys, time, datetime, urllib.request, urllib.parse, pathlib

UA = {'User-Agent': 'krw-listing-dashboard/1.0'}
COINGECKO_KEY = os.environ.get('COINGECKO_API_KEY', '').strip()
COINGECKO_BASE = 'https://api.coingecko.com/api/v3'
TIMEOUT = 30

# chain → CoinGecko platform key + DEX Screener chain slug
CHAIN_MAP = {
    'ethereum': ('ethereum', 'ethereum'),
    'binance-smart-chain': ('binance-smart-chain', 'bsc'),
    'bsc': ('binance-smart-chain', 'bsc'),
    'base': ('base', 'base'),
    'arbitrum': ('arbitrum-one', 'arbitrum'),
    'polygon': ('polygon-pos', 'polygon'),
    'mantle': ('mantle', 'mantle'),
    'the-open-network': ('the-open-network', 'ton'),
    'ton': ('the-open-network', 'ton'),
    'solana': ('solana', 'solana'),
}
# DefiLlama Coins API chain prefix
DEFILLAMA_CHAIN = {
    'ethereum': 'ethereum',
    'binance-smart-chain': 'bsc', 'bsc': 'bsc',
    'base': 'base',
    'arbitrum': 'arbitrum',
    'polygon': 'polygon',
    'mantle': 'mantle',
    'solana': 'solana',
}

def get_json(url, params=None, headers=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())

# ─────────────────────────────────────────────────────────────
# CoinGecko: /coins/markets — multi-id 한 번에
# ─────────────────────────────────────────────────────────────
def fetch_coingecko_markets(ids):
    if not ids:
        return {}
    h = {'x-cg-demo-api-key': COINGECKO_KEY} if COINGECKO_KEY else {}
    data = get_json(f'{COINGECKO_BASE}/coins/markets', {
        'vs_currency': 'usd',
        'ids': ','.join(ids),
        'per_page': len(ids),
        'page': 1,
        'sparkline': 'false',
        'price_change_percentage': '',
    }, h)
    return {c['id']: c for c in data}

# ─────────────────────────────────────────────────────────────
# DefiLlama Coins fallback (가격만, key 무필요, 무제한)
# ─────────────────────────────────────────────────────────────
def fetch_defillama_prices(contracts_list):
    """contracts_list: [(chain, address), ...] → {(chain_lc, addr_lc): price_usd}"""
    keys = []
    rev = {}
    for chain, addr in contracts_list:
        c = DEFILLAMA_CHAIN.get((chain or '').lower())
        if c and addr:
            k = f"{c}:{addr}"
            keys.append(k)
            rev[k.lower()] = (chain.lower(), addr.lower())
    if not keys:
        return {}
    try:
        d = get_json(f'https://coins.llama.fi/prices/current/{",".join(keys)}')
    except Exception:
        return {}
    result = {}
    for k, v in (d.get('coins') or {}).items():
        if 'price' in v:
            result[rev.get(k.lower(), (None, None))] = v['price']
    return result

# ─────────────────────────────────────────────────────────────
# DEX Screener: /tokens/{address} — chain 무관 multi-pair 응답
# ─────────────────────────────────────────────────────────────
def fetch_dex_screener(address):
    try:
        data = get_json(f'https://api.dexscreener.com/latest/dex/tokens/{address}')
    except Exception:
        return None
    pairs = data.get('pairs') or []
    if not pairs:
        return None
    pairs.sort(key=lambda p: (p.get('liquidity') or {}).get('usd') or 0, reverse=True)
    top = pairs[0]
    return {
        'dex_liquidity_usd': (top.get('liquidity') or {}).get('usd'),
        'dex_top_pool': top.get('pairAddress'),
        'dex_chain': top.get('chainId'),
        'dex_dex': top.get('dexId'),
        'price_usd': float(top['priceUsd']) if top.get('priceUsd') else None,  # CoinGecko fallback 용
    }

# ─────────────────────────────────────────────────────────────
# 환율 USD/KRW
# ─────────────────────────────────────────────────────────────
def fetch_fx_rate():
    try:
        d = get_json('https://open.er-api.com/v6/latest/USD')
        rate = d.get('rates', {}).get('KRW')
        if rate:
            return rate
    except Exception:
        pass
    # fallback
    try:
        d = get_json('https://api.frankfurter.app/latest', {'from':'USD','to':'KRW'})
        return d.get('rates', {}).get('KRW')
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────
# Bithumb public ticker (서버 사이드, CORS 무관)
# ─────────────────────────────────────────────────────────────
def fetch_bithumb_krw(symbol):
    try:
        d = get_json(f'https://api.bithumb.com/public/ticker/{symbol}_KRW')
        if d.get('status') != '0000':
            return None
        closing = (d.get('data') or {}).get('closing_price')
        return float(closing) if closing else None
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────
# Upbit public ticker (서버 사이드)
# ─────────────────────────────────────────────────────────────
def fetch_upbit_krw(symbol):
    try:
        d = get_json('https://api.upbit.com/v1/ticker', {'markets': f'KRW-{symbol}'})
        if isinstance(d, list) and d:
            return float(d[0].get('trade_price') or 0) or None
    except Exception:
        return None
    return None

# ─────────────────────────────────────────────────────────────
# USDT 시장 김프 (업비트 + 빗썸)
# ─────────────────────────────────────────────────────────────
def compute_usdt_market(fx_rate, batch_ts):
    """meta.usdt 객체 반환. 실패 시 None (전체 stale 안 함, 해당 필드만 null)."""
    if not fx_rate:
        return None
    upbit = fetch_upbit_krw('USDT')
    bithumb = fetch_bithumb_krw('USDT')
    if upbit is None and bithumb is None:
        return None
    def premium(krw): return None if krw is None else round((krw / fx_rate - 1) * 100, 2)
    gap_krw = round(upbit - bithumb, 2) if (upbit is not None and bithumb is not None) else None
    gap_pct = round((gap_krw / bithumb) * 100, 3) if (gap_krw is not None and bithumb) else None
    return {
        'upbit_krw': upbit,
        'bithumb_krw': bithumb,
        'upbit_premium_pct': premium(upbit),
        'bithumb_premium_pct': premium(bithumb),
        'exchange_gap_krw': gap_krw,
        'exchange_gap_pct': gap_pct,
        'updated_at': batch_ts,
    }

# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────
def process_file(path):
    p = pathlib.Path(path)
    if not p.exists():
        print(f"  ✗ {path}: not found", file=sys.stderr)
        return False
    payload = json.loads(p.read_text())
    tokens = payload.get('tokens', [])
    if not tokens:
        return False

    batch_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    fields_meta = payload.setdefault('meta', {}).setdefault('live', {})
    fields_meta['batch_ts'] = batch_ts
    errors = fields_meta.setdefault('errors', [])
    errors.clear()

    # 1) 환율
    fx = fetch_fx_rate()
    if fx:
        payload['meta']['fx_rate'] = round(fx, 2)
        payload['meta']['fx_timestamp'] = batch_ts
        fields_meta['fx_last_success_at'] = batch_ts
    else:
        errors.append('fx_rate')

    # 1a) USDT 시장 김프 (업비트 + 빗썸) — 같은 batch_ts, 같은 fx_rate 사용
    usdt = compute_usdt_market(payload['meta'].get('fx_rate'), batch_ts)
    if usdt:
        payload['meta']['usdt'] = usdt
        fields_meta['usdt_last_success_at'] = batch_ts
    else:
        payload['meta']['usdt'] = None  # 부분 stale (전체는 유지)
        errors.append('usdt_market')

    # 2) CoinGecko markets (multi-id 한 번에)
    cg_ids = [t['coingecko_id'] for t in tokens if t.get('coingecko_id')]
    cg_data = {}
    try:
        cg_data = fetch_coingecko_markets(cg_ids)
        fields_meta['coingecko_last_success_at'] = batch_ts
    except Exception as e:
        errors.append(f'coingecko_markets: {e}')

    # 2a) CoinGecko 실패하거나 응답에 빠진 토큰 → DefiLlama 가격 fallback
    missing_price = []
    for t in tokens:
        cg_id = t.get('coingecko_id')
        if cg_id and cg_id in cg_data and cg_data[cg_id].get('current_price') is not None:
            continue
        for c in (t.get('meta_strip', {}).get('contracts') or []):
            chain = c.get('chain'); addr = c.get('address')
            if chain and addr:
                missing_price.append((chain, addr, t['symbol']))
    dll_prices = {}
    if missing_price:
        dll_prices = fetch_defillama_prices([(c, a) for c, a, _ in missing_price])
        if dll_prices:
            fields_meta['defillama_fallback_at'] = batch_ts

    fx_rate = payload['meta'].get('fx_rate')

    for t in tokens:
        m = t.setdefault('meta_strip', {})
        cg_id = t.get('coingecko_id')
        cg = cg_data.get(cg_id) if cg_id else None

        # CoinGecko 값 갱신
        if cg:
            if cg.get('market_cap') is not None:
                m['market_cap_usd'] = cg['market_cap']
            if cg.get('total_volume') is not None:
                m['total_volume_usd'] = cg['total_volume']
            if cg.get('circulating_supply') is not None:
                m['circulating_supply'] = cg['circulating_supply']
            if cg.get('fully_diluted_valuation') is not None:
                m['fully_diluted_usd'] = cg['fully_diluted_valuation']

        # 가격 우선순위: CoinGecko → DefiLlama → DEX Screener
        global_usd = cg.get('current_price') if cg else None
        if global_usd is None:
            for c in (m.get('contracts') or []):
                key = ((c.get('chain') or '').lower(), (c.get('address') or '').lower())
                if key in dll_prices:
                    global_usd = dll_prices[key]
                    break
        if global_usd is not None and t.get('fund', {}).get('kimchi'):
            t['fund']['kimchi']['global_usd'] = global_usd

        # DEX Screener (primary contract만, top pool)
        contracts = m.get('contracts') or []
        if contracts:
            addr = contracts[0].get('address')
            if addr:
                dex = fetch_dex_screener(addr)
                if dex:
                    if dex['dex_liquidity_usd'] is not None:
                        m['dex_liquidity_usd'] = dex['dex_liquidity_usd']
                    if dex['dex_top_pool']:
                        m['dex_top_pool'] = dex['dex_top_pool']
                    # 가격 마지막 fallback (CoinGecko + DefiLlama 모두 실패한 경우)
                    if global_usd is None and dex.get('price_usd') is not None:
                        global_usd = dex['price_usd']
                        if t.get('fund', {}).get('kimchi'):
                            t['fund']['kimchi']['global_usd'] = global_usd

        # Bithumb KRW (빗썸 상장 토큰만)
        if t.get('bithumb_listed'):
            kr = fetch_bithumb_krw(t['symbol'])
            if kr is not None and t.get('fund', {}).get('kimchi'):
                t['fund']['kimchi']['bithumb_krw'] = kr
                # 같은 배치에서 김프 재계산 (Codex 가이드: 일관성)
                if global_usd and fx_rate:
                    bithumb_usd_eq = kr / fx_rate
                    t['fund']['kimchi']['bithumb_usd_equiv'] = round(bithumb_usd_eq, 6)
                    t['fund']['kimchi']['kimchi_pct'] = round((bithumb_usd_eq / global_usd - 1) * 100, 2)

    # 마지막 성공 timestamp (배치 성공 시)
    if not errors:
        fields_meta['last_success_at'] = batch_ts

    # 저장
    p.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    print(f"  ✓ {path}: batch_ts={batch_ts}, errors={len(errors)}")
    if errors:
        for e in errors:
            print(f"    - {e}", file=sys.stderr)
    return True

def main():
    script_dir = pathlib.Path(__file__).parent
    targets = [
        script_dir / 'dashboard_data_v6_verified.min.json',
        script_dir / 'dashboard_data_v72_final.min.json',
    ]
    ok = 0
    for t in targets:
        if process_file(t):
            ok += 1
    print(f"\n총 {ok}/{len(targets)} 파일 갱신")
    return 0 if ok == len(targets) else 1

if __name__ == '__main__':
    sys.exit(main())
