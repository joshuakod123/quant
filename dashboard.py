# dashboard.py — QUANT STATION PRO v1.2 (KR+US 통합)
import streamlit as st
import requests as req
import xml.etree.ElementTree as ET
import json, os, time
from datetime import datetime
from kis_client import get_price_kr, get_balance_kr, get_balance_us

st.set_page_config(
    page_title="QUANT STATION PRO",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
:root {
    --bg-base:#03070f; --bg-panel:#070d1a; --bg-card:#0a1628; --bg-hover:#0f1f3a;
    --border:#112240; --border-bright:#1a3a6a;
    --cyan:#00c8ff; --cyan-dim:#0066aa;
    --green:#00e676; --red:#ff1744; --red-dim:#4d0011;
    --gold:#ffd600; --gold-dim:#4d4000; --orange:#ff6d00;
    --text-primary:#ccd6f6; --text-secondary:#4a6fa5; --text-dim:#1e3a5f;
}
html,body,[class*="css"],.stApp{font-family:'IBM Plex Mono',monospace!important;background:var(--bg-base)!important;color:var(--text-primary)!important;}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:var(--bg-base)}::-webkit-scrollbar-thumb{background:var(--border-bright);border-radius:2px}
section[data-testid="stSidebar"]{display:none}
.main .block-container{padding:0!important;max-width:100%!important}
.topbar{background:var(--bg-panel);border-bottom:2px solid var(--cyan-dim);padding:8px 24px;display:flex;align-items:center;gap:16px}
.topbar-logo{font-size:15px;font-weight:700;color:var(--cyan);letter-spacing:6px}
.topbar-badge{font-size:9px;letter-spacing:2px;padding:3px 8px;border:1px solid var(--cyan-dim);color:var(--cyan);background:#001a2e}
.topbar-badge-warn{border-color:var(--gold)!important;color:var(--gold)!important;background:#1a1000!important}
.topbar-time{margin-left:auto;font-size:11px;color:var(--text-secondary);letter-spacing:2px}
.ticker-bar{background:#020509;border-bottom:1px solid var(--border);padding:5px 24px;display:flex;gap:28px;overflow-x:auto;white-space:nowrap}
.ticker-item{display:inline-flex;align-items:center;gap:7px}
.ticker-name{font-size:8px;color:var(--text-secondary);letter-spacing:2px}
.ticker-val{font-size:11px;color:var(--text-primary);font-weight:600}
.ticker-up{font-size:10px;color:var(--green)}.ticker-dn{font-size:10px;color:var(--red)}
.panel{background:var(--bg-panel);border:1px solid var(--border);margin-bottom:8px}
.panel-header{padding:7px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;background:var(--bg-card)}
.panel-title{font-size:9px;letter-spacing:3px;color:var(--text-secondary);text-transform:uppercase;font-weight:600}
.panel-dot{width:6px;height:6px;border-radius:50%;background:var(--cyan);box-shadow:0 0 6px var(--cyan);animation:blink 2s infinite}
.panel-dot-green{background:var(--green)!important;box-shadow:0 0 6px var(--green)!important}
.panel-dot-red{background:var(--red)!important;box-shadow:0 0 6px var(--red)!important}
.panel-dot-gold{background:var(--gold)!important;box-shadow:0 0 6px var(--gold)!important}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
.idx-card{padding:9px 14px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.idx-card:hover{background:var(--bg-hover)}
.idx-label{font-size:8px;letter-spacing:2px;color:var(--text-secondary);margin-bottom:3px}
.idx-val{font-size:15px;font-weight:700;color:var(--text-primary)}
.idx-up{font-size:11px;color:var(--green);font-weight:600;text-align:right}
.idx-dn{font-size:11px;color:var(--red);font-weight:600;text-align:right}
.idx-sub{font-size:9px;color:var(--text-dim);text-align:right;margin-top:2px}
.idx-live{font-size:7px;letter-spacing:1px;color:var(--cyan);margin-top:2px}
.commodity-row{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;border-bottom:1px solid var(--border)}
.commodity-name{font-size:9px;letter-spacing:1px;color:var(--text-secondary)}
.commodity-unit{font-size:8px;color:var(--text-dim);margin-top:1px}
.stock-header{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;padding:5px 14px;border-bottom:1px solid var(--border);font-size:8px;letter-spacing:2px;color:var(--text-dim)}
.stock-row{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;padding:8px 14px;border-bottom:1px solid var(--border);align-items:center}
.stock-row:hover{background:var(--bg-hover)}
.stock-name{font-size:12px;color:var(--text-primary);font-weight:600}
.stock-code{font-size:8px;color:var(--text-dim);margin-top:2px}
.stock-price{font-size:12px;color:var(--text-primary);text-align:right}
.stock-up{font-size:11px;color:var(--green);text-align:right;font-weight:700}
.stock-dn{font-size:11px;color:var(--red);text-align:right;font-weight:700}
.stock-vol{font-size:9px;color:var(--text-secondary);text-align:right}
.bar-up{height:2px;background:var(--green);border-radius:1px;margin-top:3px}
.bar-dn{height:2px;background:var(--red);border-radius:1px;margin-top:3px}
.acct-grid{display:grid;gap:1px;background:var(--border)}
.acct-cell{background:var(--bg-card);padding:12px 10px;text-align:center}
.acct-label{font-size:8px;letter-spacing:2px;color:var(--text-secondary);margin-bottom:5px}
.acct-val{font-size:15px;font-weight:700;color:var(--cyan)}
.news-link{text-decoration:none;color:inherit;display:block}
.news-item{padding:9px 14px;border-bottom:1px solid var(--border);transition:background 0.15s}
.news-item:hover{background:var(--bg-hover);border-left:2px solid var(--cyan)}
.news-src{font-size:8px;letter-spacing:2px;color:var(--cyan);margin-bottom:3px}
.news-src-war{color:var(--red)!important}.news-src-oil{color:var(--orange)!important}
.news-src-kr{color:var(--gold)!important}.news-src-fed{color:#aa88ff!important}
.news-title{font-size:11px;color:var(--text-primary);line-height:1.5;font-family:'IBM Plex Sans',sans-serif}
.news-time{font-size:8px;color:var(--text-dim);margin-top:3px}
.news-click-hint{font-size:8px;color:var(--cyan-dim);margin-top:2px;opacity:0}
.news-item:hover .news-click-hint{opacity:1}
.news-tag{display:inline-block;font-size:7px;letter-spacing:1px;padding:1px 5px;border-radius:1px;margin-right:3px;margin-bottom:3px}
.tag-war{background:var(--red-dim);color:var(--red);border:1px solid var(--red)}
.tag-oil{background:#1a0d00;color:var(--orange);border:1px solid var(--orange)}
.tag-fed{background:#1a0d2e;color:#aa88ff;border:1px solid #aa88ff}
.tag-tech{background:#001a1a;color:var(--cyan);border:1px solid var(--cyan)}
.tag-kr{background:#001a0d;color:var(--green);border:1px solid var(--green)}
.trade-row{display:grid;grid-template-columns:80px 55px 1fr 90px 1fr;padding:7px 14px;border-bottom:1px solid var(--border);font-size:10px;align-items:center;gap:6px}
.trade-buy{color:var(--green);font-weight:700}.trade-sell{color:var(--red);font-weight:700}
.trade-time{color:var(--text-secondary);font-size:9px}
.risk-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px}
.risk-name{font-size:10px;color:var(--text-primary)}
.risk-badge{font-size:8px;font-weight:700;letter-spacing:1px;padding:2px 8px;border-radius:1px}
.fear-track{height:5px;background:linear-gradient(90deg,var(--green),var(--gold),var(--red));border-radius:3px;position:relative;margin:8px 0 4px}
.fear-needle{position:absolute;top:-5px;width:14px;height:14px;border-radius:50%;background:white;box-shadow:0 0 8px rgba(255,255,255,0.8);transform:translateX(-50%)}
.stProgress>div>div{background:linear-gradient(90deg,var(--cyan),var(--green))!important}
hr{display:none!important}
#MainMenu,footer,header{visibility:hidden}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════
# 데이터 함수
# ═══════════════════════════════════════════
@st.cache_data(ttl=30)
def fetch_yahoo(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d&includePrePost=false"
        r = req.get(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}, timeout=5)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev  = meta.get("chartPreviousClose", price)
        chg   = ((price - prev) / prev * 100) if prev else 0
        ts    = meta.get("regularMarketTime", 0)
        updated = datetime.fromtimestamp(ts).strftime("%H:%M") if ts else "—"
        return {"price": price, "change": chg, "prev": prev, "updated": updated}
    except:
        return {"price": 0, "change": 0, "prev": 0, "updated": "—"}

@st.cache_data(ttl=300)
def fetch_all_news():
    feeds = [
        ("REUTERS",     "https://feeds.reuters.com/reuters/businessNews",              "global"),
        ("BLOOMBERG",   "https://feeds.bloomberg.com/markets/news.rss",                "global"),
        ("REUTERS WAR", "https://feeds.reuters.com/Reuters/worldNews",                 "war"),
        ("INVESTING",   "https://www.investing.com/rss/news_301.rss",                  "oil"),
        ("연합뉴스",     "https://www.yonhapnewstv.co.kr/category/news/economy/feed/",  "kr"),
        ("FED/FINANCE",  "https://feeds.reuters.com/reuters/financialsNews",            "fed"),
    ]
    articles = []
    for source, url, category in feeds:
        try:
            r = req.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:6]:
                title = item.findtext("title", "").strip()
                pub   = item.findtext("pubDate", "")[:22] if item.findtext("pubDate") else ""
                link  = item.findtext("link", "")
                if not link:
                    for child in item:
                        if child.tag == "link":
                            link = child.text or child.get("href", "") or ""
                            break
                if title:
                    articles.append({"source": source, "title": title,
                                     "time": pub, "category": category,
                                     "link": link.strip() if link else ""})
        except:
            continue
    return articles[:40]

def load_trade_log():
    if os.path.exists("trades.json"):
        try:
            with open("trades.json", "r") as f:
                return json.load(f)
        except:
            return []
    return []

def tag_news(title, category):
    t = title.lower()
    tags = []
    if any(w in t for w in ["war","iran","russia","ukraine","conflict","missile","attack","strike","군사","전쟁"]):
        tags.append('<span class="news-tag tag-war">⚔ WAR</span>')
    if any(w in t for w in ["oil","crude","opec","energy","brent","wti","gas","유가","원유"]):
        tags.append('<span class="news-tag tag-oil">🛢 OIL</span>')
    if any(w in t for w in ["fed","rate","inflation","fomc","powell","interest","금리","인플레"]):
        tags.append('<span class="news-tag tag-fed">🏦 FED</span>')
    if any(w in t for w in ["tech","ai","nvidia","semiconductor","chip","apple","google","반도체"]):
        tags.append('<span class="news-tag tag-tech">💻 TECH</span>')
    if category == "kr" or any(w in t for w in ["korea","한국","삼성","현대","kospi","코스피"]):
        tags.append('<span class="news-tag tag-kr">🇰🇷 KR</span>')
    return "".join(tags)

def src_cls(cat):
    return {"war":"news-src-war","oil":"news-src-oil","kr":"news-src-kr","fed":"news-src-fed"}.get(cat,"")

def market_status():
    now = datetime.now()
    if now.weekday() >= 5: return "CLOSED", "#ff1744"
    h, m = now.hour, now.minute
    if 9 <= h < 15 or (h == 15 and m <= 20): return "OPEN", "#00e676"
    return "CLOSED", "#ff1744"

def us_market_status():
    now = datetime.now()
    if now.weekday() >= 5: return "CLOSED", "#ff1744"
    h = now.hour
    if h >= 22 or h < 5: return "OPEN", "#00e676"
    return "CLOSED", "#4a6fa5"

# ═══════════════════════════════════════════
# 데이터 로드
# ═══════════════════════════════════════════
now_str = datetime.now().strftime("%Y.%m.%d  %H:%M:%S")
mstatus, mcolor   = market_status()
usstatus, uscolor = us_market_status()

tickers = {
    "S&P500":"^GSPC","NASDAQ":"^IXIC","KOSPI":"^KS11","KOSDAQ":"^KQ11",
    "USD/KRW":"USDKRW=X","WTI":"CL=F","GOLD":"GC=F","VIX":"^VIX","BTC":"BTC-USD"
}
ticker_vals = {k: fetch_yahoo(v) for k, v in tickers.items()}

# ═══════════════════════════════════════════
# 탑바
# ═══════════════════════════════════════════
st.markdown(f"""
<div class="topbar">
    <div class="topbar-logo">⚡ QUANT STATION</div>
    <div class="topbar-badge">PRO v1.2</div>
    <div class="topbar-badge">KIS MOCK API</div>
    <div class="topbar-badge topbar-badge-warn">⚠ 모의투자</div>
    <div style="font-size:10px;letter-spacing:1px;color:{mcolor}">● KRX {mstatus}</div>
    <div style="font-size:10px;letter-spacing:1px;color:{uscolor}">● NYSE {usstatus}</div>
    <div class="topbar-time">{now_str}</div>
</div>
""", unsafe_allow_html=True)

# 티커바
ticker_html = '<div class="ticker-bar">'
for name, d in ticker_vals.items():
    chg = d['change']
    c = "ticker-up" if chg >= 0 else "ticker-dn"
    s = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
    p = f"{d['price']:,.2f}" if d['price'] > 0 else "—"
    ticker_html += f'<div class="ticker-item"><span class="ticker-name">{name}</span><span class="ticker-val">{p}</span><span class="{c}">{s}</span></div>'
ticker_html += '</div>'
st.markdown(ticker_html, unsafe_allow_html=True)

# ═══════════════════════════════════════════
# 메인 3컬럼
# ═══════════════════════════════════════════
L, M, R = st.columns([1, 1.7, 1.3])

# ────────── 왼쪽 ──────────
with L:
    st.markdown('<div class="panel"><div class="panel-header"><div class="panel-dot"></div><div class="panel-title">GLOBAL INDICES</div><div style="margin-left:auto;font-size:8px;color:var(--cyan);letter-spacing:1px">~1분 딜레이</div></div>', unsafe_allow_html=True)
    for name, sym in [("S&P 500","^GSPC"),("NASDAQ","^IXIC"),("KOSPI","^KS11"),("KOSDAQ","^KQ11"),("NIKKEI","^N225"),("상해종합","000001.SS"),("달러인덱스","DX-Y.NYB"),("USD/KRW","USDKRW=X")]:
        d = fetch_yahoo(sym)
        chg = d['change']
        cc = "idx-up" if chg >= 0 else "idx-dn"
        cs = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
        p  = f"{d['price']:,.2f}" if d['price'] > 0 else "—"
        ab = abs(d['price'] - d['prev'])
        upd = d.get('updated','—')
        st.markdown(f'<div class="idx-card"><div><div class="idx-label">{name}</div><div class="idx-val">{p}</div><div class="idx-live">업데이트 {upd}</div></div><div><div class="{cc}">{cs}</div><div class="idx-sub">{"▲" if chg>=0 else "▼"} {ab:,.2f}</div></div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="panel-header"><div class="panel-dot panel-dot-red"></div><div class="panel-title">COMMODITIES & MACRO</div></div>', unsafe_allow_html=True)
    for name, sym, unit in [("WTI 원유","CL=F","USD/bbl"),("브렌트유","BZ=F","USD/bbl"),("천연가스","NG=F","USD/MMBtu"),("금 GOLD","GC=F","USD/oz"),("은 SILVER","SI=F","USD/oz"),("구리","HG=F","USD/lb"),("VIX 공포","^VIX","변동성"),("비트코인","BTC-USD","USD")]:
        d = fetch_yahoo(sym)
        chg = d['change']
        color = "#00e676" if chg >= 0 else "#ff1744"
        cs = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
        p  = f"{d['price']:,.2f}" if d['price'] > 0 else "—"
        st.markdown(f'<div class="commodity-row"><div><div class="commodity-name">{name}</div><div class="commodity-unit">{unit}</div></div><div style="text-align:right"><div style="font-size:14px;font-weight:700;color:{color}">{p}</div><div style="font-size:9px;color:{color}">{cs}</div></div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ────────── 가운데 ──────────
with M:

    # ── 계좌 현황 (KR + US) ──
    st.markdown('<div class="panel"><div class="panel-header"><div class="panel-dot panel-dot-gold"></div><div class="panel-title">ACCOUNT STATUS — KR + US</div></div>', unsafe_allow_html=True)

    cash_krw = 0
    cash_usd = 0
    usd_krw  = fetch_yahoo("USDKRW=X")["price"] or 1400

    try:
        bal_kr  = get_balance_kr()
        cash_krw = bal_kr["available_cash_krw"]
    except Exception as e:
        pass

    try:
        bal_us  = get_balance_us()
        cash_usd = bal_us["available_cash_usd"]
    except:
        pass

    total_krw = cash_krw + int(cash_usd * usd_krw)
    target    = 30_000_000
    start     = 10_000_000
    profit    = total_krw - start
    ppct      = profit / start * 100 if start > 0 else 0
    prog      = total_krw / target

    st.markdown(f"""
    <div class="acct-grid" style="grid-template-columns:1fr 1fr 1fr 1fr">
        <div class="acct-cell">
            <div class="acct-label">KRW 예수금</div>
            <div class="acct-val" style="font-size:13px">{cash_krw:,}</div>
            <div style="font-size:8px;color:var(--text-dim)">원</div>
        </div>
        <div class="acct-cell">
            <div class="acct-label">USD 예수금</div>
            <div class="acct-val" style="font-size:13px;color:#00e676">${cash_usd:,.2f}</div>
            <div style="font-size:8px;color:var(--text-dim)">≈ {int(cash_usd*usd_krw):,}원</div>
        </div>
        <div class="acct-cell">
            <div class="acct-label">목표금액</div>
            <div class="acct-val" style="font-size:13px;color:var(--gold)">{target:,}</div>
            <div style="font-size:8px;color:var(--text-dim)">원</div>
        </div>
        <div class="acct-cell">
            <div class="acct-label">달성률</div>
            <div class="acct-val" style="font-size:18px;color:{'#00e676' if profit>=0 else '#ff1744'}">{prog*100:.1f}%</div>
            <div style="font-size:9px;color:{'#00e676' if profit>=0 else '#ff1744'}">{'+' if profit>=0 else ''}{ppct:.2f}%</div>
        </div>
    </div>
    <div style="padding:6px 14px;background:var(--bg-card)">
    """, unsafe_allow_html=True)
    st.progress(min(prog, 1.0))
    st.markdown("</div></div>", unsafe_allow_html=True)

    # ── KR 관심종목 ──
    KR_WATCHLIST = {
        "005930":"삼성전자","000660":"SK하이닉스","035420":"NAVER",
        "035720":"카카오","005380":"현대차","000270":"기아",
        "051910":"LG화학","068270":"셀트리온"
    }
    st.markdown('<div class="panel"><div class="panel-header"><div class="panel-dot"></div><div class="panel-title">🇰🇷 KRX WATCHLIST — KIS 실시간</div></div><div class="stock-header"><div>종목</div><div style="text-align:right">현재가</div><div style="text-align:right">등락률</div><div style="text-align:right">거래량</div></div>', unsafe_allow_html=True)
    for code, name in KR_WATCHLIST.items():
        try:
            p = get_price_kr(code)
            chg = p['change_rate']
            cc = "stock-up" if chg >= 0 else "stock-dn"
            cs = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
            vol = f"{p['volume']/10000:.0f}만" if p['volume'] > 10000 else str(p['volume'])
            bw = min(abs(chg)*10, 100)
            bc = "bar-up" if chg >= 0 else "bar-dn"
            st.markdown(f'<div class="stock-row"><div><div class="stock-name">{name}</div><div class="stock-code">{code}</div><div class="{bc}" style="width:{bw}%"></div></div><div class="stock-price">{p["price"]:,}원</div><div class="{cc}">{cs}</div><div class="stock-vol">{vol}</div></div>', unsafe_allow_html=True)
        except:
            st.markdown(f'<div class="stock-row"><div><div class="stock-name">{name}</div><div class="stock-code">{code}</div></div><div style="color:var(--text-dim);font-size:9px;text-align:right;grid-column:2/5">장 마감</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── US 관심종목 ──
    US_WATCHLIST = {
        "NVDA":"NVIDIA","AMD":"AMD","TSLA":"Tesla",
        "AAPL":"Apple","MSFT":"Microsoft","META":"Meta",
        "SOXL":"반도체 3x ETF","TQQQ":"나스닥 3x ETF"
    }
    st.markdown('<div class="panel"><div class="panel-header"><div class="panel-dot panel-dot-green"></div><div class="panel-title">🇺🇸 US WATCHLIST — Yahoo 실시간</div></div><div class="stock-header"><div>종목</div><div style="text-align:right">현재가</div><div style="text-align:right">등락률</div><div style="text-align:right">거래량</div></div>', unsafe_allow_html=True)
    for ticker, name in US_WATCHLIST.items():
        d = fetch_yahoo(ticker)
        if d['price'] > 0:
            chg = d['change']
            cc = "stock-up" if chg >= 0 else "stock-dn"
            cs = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
            bw = min(abs(chg)*10, 100)
            bc = "bar-up" if chg >= 0 else "bar-dn"
            st.markdown(f'<div class="stock-row"><div><div class="stock-name">{name}</div><div class="stock-code">{ticker}</div><div class="{bc}" style="width:{bw}%"></div></div><div class="stock-price">${d["price"]:,.2f}</div><div class="{cc}">{cs}</div><div class="stock-vol">—</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="stock-row"><div><div class="stock-name">{name}</div><div class="stock-code">{ticker}</div></div><div style="color:var(--text-dim);font-size:9px;text-align:right;grid-column:2/5">장 마감</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 에이전트 + 트레이드 로그 ──
    trades = load_trade_log()
    today  = datetime.now().strftime("%Y-%m-%d")
    buy_cnt   = sum(1 for t in trades if t.get("action")=="BUY"  and t.get("time","").startswith(today))
    sell_cnt  = sum(1 for t in trades if t.get("action")=="SELL" and t.get("time","").startswith(today))
    today_pnl = sum(t.get("pnl",0) for t in trades if t.get("time","").startswith(today))
    kr_trades = sum(1 for t in trades if t.get("currency")=="KRW")
    us_trades = sum(1 for t in trades if t.get("currency")=="USD")

    st.markdown(f"""
    <div class="panel">
        <div class="panel-header"><div class="panel-dot panel-dot-gold"></div><div class="panel-title">AGENT & TRADE LOG</div></div>
        <div style="padding:8px 14px;background:var(--bg-card);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px">
            <div style="width:8px;height:8px;border-radius:50%;background:var(--gold);box-shadow:0 0 8px var(--gold);animation:blink 1.5s infinite;flex-shrink:0"></div>
            <div style="font-size:10px;letter-spacing:2px;color:var(--gold)">QUANT AGENT — {'🟢 RUNNING' if mstatus=='OPEN' or usstatus=='OPEN' else '🟡 STANDBY'}</div>
            <div style="margin-left:auto;font-size:8px;color:var(--text-dim)">12 RULES ACTIVE</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:1px;background:var(--border)">
            <div style="background:var(--bg-card);padding:10px;text-align:center"><div style="font-size:8px;letter-spacing:2px;color:var(--text-secondary)">오늘 매수</div><div style="font-size:16px;font-weight:700;color:var(--green)">{buy_cnt}건</div></div>
            <div style="background:var(--bg-card);padding:10px;text-align:center"><div style="font-size:8px;letter-spacing:2px;color:var(--text-secondary)">오늘 매도</div><div style="font-size:16px;font-weight:700;color:var(--red)">{sell_cnt}건</div></div>
            <div style="background:var(--bg-card);padding:10px;text-align:center"><div style="font-size:8px;letter-spacing:2px;color:var(--text-secondary)">KR거래</div><div style="font-size:16px;font-weight:700;color:var(--cyan)">{kr_trades}건</div></div>
            <div style="background:var(--bg-card);padding:10px;text-align:center"><div style="font-size:8px;letter-spacing:2px;color:var(--text-secondary)">US거래</div><div style="font-size:16px;font-weight:700;color:#00e676">{us_trades}건</div></div>
        </div>
        <div style="padding:8px 14px;background:var(--bg-card);border-bottom:1px solid var(--border);border-top:1px solid var(--border);text-align:center">
            <span style="font-size:8px;letter-spacing:2px;color:var(--text-secondary)">오늘 누적 손익 </span>
            <span style="font-size:16px;font-weight:700;color:{'#00e676' if today_pnl>=0 else '#ff1744'}">{'+' if today_pnl>=0 else ''}{today_pnl:,.0f}원</span>
        </div>
    """, unsafe_allow_html=True)

    if trades:
        st.markdown('<div style="padding:5px 14px;background:var(--bg-base);border-bottom:1px solid var(--border);display:grid;grid-template-columns:80px 55px 1fr 90px 1fr;gap:6px;font-size:8px;letter-spacing:2px;color:var(--text-dim)"><div>TIME</div><div>ACT</div><div>종목</div><div>수량/가격</div><div>사유</div></div>', unsafe_allow_html=True)
        for t in reversed(trades[-15:]):
            ac  = "trade-buy" if t.get("action")=="BUY" else "trade-sell"
            sym = "▲ BUY"    if t.get("action")=="BUY" else "▼ SELL"
            cur = t.get("currency","KRW")
            price_str = f"${t.get('price',0):.2f}" if cur=="USD" else f"{t.get('price',0):,}원"
            flag = "🇺🇸" if cur=="USD" else "🇰🇷"
            st.markdown(f'<div class="trade-row"><div class="trade-time">{t.get("time","")[-8:]}</div><div class="{ac}">{flag}{sym}</div><div style="color:var(--text-primary)">{t.get("name","")}</div><div style="color:var(--text-secondary);font-size:9px">{t.get("qty",0)}주 {price_str}</div><div style="color:var(--text-dim);font-size:9px">{t.get("reason","")[:25]}</div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="padding:18px;text-align:center;color:var(--text-dim);font-size:9px;letter-spacing:2px">NO TRADES YET — AGENT SCANNING MARKET</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ────────── 오른쪽 ──────────
with R:
    # 뉴스
    st.markdown('<div class="panel"><div class="panel-header"><div class="panel-dot panel-dot-red"></div><div class="panel-title">GLOBAL INTELLIGENCE FEED</div><div style="margin-left:auto;font-size:8px;color:var(--cyan-dim);letter-spacing:1px">클릭 → 원문</div></div>', unsafe_allow_html=True)
    news = fetch_all_news()
    fallback = [
        ("BLOOMBERG","Global stocks extend selloff as Iran-US tensions escalate","war","https://bloomberg.com"),
        ("REUTERS WAR","Iran launches drone strikes; US repositions carriers to Gulf","war","https://reuters.com"),
        ("INVESTING","WTI crude surges 4% on Middle East supply disruption fears","oil","https://investing.com"),
        ("BLOOMBERG","Fed signals no rate cuts until inflation sustainably at 2%","fed","https://bloomberg.com"),
        ("연합뉴스","삼성전자 HBM 수요 급증, 반도체 수출 12% 증가","kr","https://yonhapnews.co.kr"),
        ("REUTERS","NVIDIA posts record revenue; AI chip demand accelerates","global","https://reuters.com"),
        ("BLOOMBERG","China PMI contracts for third consecutive month","global","https://bloomberg.com"),
        ("연합뉴스","한국은행 기준금리 3.0% 동결 결정","kr","https://yonhapnews.co.kr"),
    ]
    articles = news if news else [{"source":s,"title":t,"time":"LIVE","category":c,"link":l} for s,t,c,l in fallback]
    for a in articles[:22]:
        tags  = tag_news(a['title'], a['category'])
        sc    = src_cls(a['category'])
        title = a['title'][:95] + ('…' if len(a['title'])>95 else '')
        link  = a.get('link','')
        if link and link.startswith('http'):
            st.markdown(f'<a href="{link}" target="_blank" class="news-link"><div class="news-item"><div class="news-src {sc}">{a["source"]}</div>{tags}<div class="news-title">{title}</div><div class="news-time">{a["time"]}</div><div class="news-click-hint">↗ 원문 보기</div></div></a>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="news-item"><div class="news-src {sc}">{a["source"]}</div>{tags}<div class="news-title">{title}</div><div class="news-time">{a["time"]}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # 시장 심리
    vix_val = fetch_yahoo("^VIX")['price']
    if vix_val > 30:   fl,fc,fp = "EXTREME FEAR",  "#ff1744", 88
    elif vix_val > 20: fl,fc,fp = "FEAR",          "#ff6d00", 68
    elif vix_val > 15: fl,fc,fp = "NEUTRAL",       "#ffd600", 50
    elif vix_val > 12: fl,fc,fp = "GREED",         "#00e676", 32
    else:              fl,fc,fp = "EXTREME GREED", "#00c8ff", 12

    st.markdown(f"""
    <div class="panel">
        <div class="panel-header"><div class="panel-dot"></div><div class="panel-title">MARKET SENTIMENT & RISK</div></div>
        <div style="padding:12px 14px;border-bottom:1px solid var(--border)">
            <div style="font-size:8px;letter-spacing:2px;color:var(--text-secondary)">VIX 공포탐욕 지수</div>
            <div style="font-size:20px;font-weight:700;color:{fc};margin-top:4px">{fl}</div>
            <div style="font-size:10px;color:var(--text-secondary);margin-top:2px">VIX {vix_val:.2f}</div>
            <div class="fear-track"><div class="fear-needle" style="left:{fp}%"></div></div>
            <div style="display:flex;justify-content:space-between;font-size:8px;color:var(--text-dim)"><span>GREED</span><span>NEUTRAL</span><span>FEAR</span></div>
        </div>
        <div style="padding:12px 14px">
            <div style="font-size:8px;letter-spacing:2px;color:var(--text-secondary);margin-bottom:10px">주요 리스크 팩터</div>
    """, unsafe_allow_html=True)
    for factor, level, color in [
        ("이란-미국 긴장","HIGH","#ff1744"),("Fed 금리 정책","MED","#ffd600"),
        ("중국 경기 둔화","MED","#ffd600"),("반도체 사이클","LOW","#00e676"),
        ("원/달러 환율","MED","#ffd600"),("WTI 유가","HIGH","#ff6d00"),
    ]:
        st.markdown(f'<div class="risk-row"><div class="risk-name">{factor}</div><div class="risk-badge" style="color:{color};border:1px solid {color};background:{color}22">{level}</div></div>', unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

    # 에이전트 12원칙 요약
    st.markdown("""
    <div class="panel">
        <div class="panel-header"><div class="panel-dot panel-dot-gold"></div><div class="panel-title">ACTIVE TRADING RULES</div></div>
        <div style="padding:10px 14px">
    """, unsafe_allow_html=True)
    rules = [
        ("R1","VIX 시장 국면 필터","#00c8ff"),
        ("R2","갭 다운 -2% 매수 차단","#ff1744"),
        ("R3","켈리 공식 포지션 사이징","#ffd600"),
        ("R4","상관계수 > 0.7 분산","#00e676"),
        ("R5","볼린저+RSI+거래량 3중 확인","#00c8ff"),
        ("R6","ATR 동적 손절/익절","#ffd600"),
        ("R7","개장/마감 시간대 필터","#ff6d00"),
        ("R8","일일 손실 -5% 자동 중단","#ff1744"),
        ("R9","모멘텀 동적 종목 선정","#00e676"),
        ("R10","전쟁/유가 뉴스 차단","#ff1744"),
        ("R11","피라미딩/물타기 금지","#ffd600"),
        ("R12","R-Multiple 2.0R 이상만 진입","#00c8ff"),
    ]
    for rule, desc, color in rules:
        st.markdown(f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:5px"><div style="font-size:8px;font-weight:700;color:{color};letter-spacing:1px;min-width:24px">{rule}</div><div style="font-size:10px;color:var(--text-primary)">{desc}</div><div style="margin-left:auto;width:6px;height:6px;border-radius:50%;background:{color};box-shadow:0 0 4px {color}"></div></div>', unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

# 하단
st.markdown(f'<div style="background:var(--bg-panel);border-top:1px solid var(--border);padding:5px 24px;display:flex;gap:20px;margin-top:4px"><div style="font-size:8px;letter-spacing:2px;color:var(--text-dim)">QUANT STATION PRO v1.2 | KR+US 혼합운용 | 12 RULES | AUTO-REFRESH 30s</div><div style="margin-left:auto;font-size:8px;letter-spacing:2px;color:var(--text-dim)">LAST UPDATE: {now_str}</div></div>', unsafe_allow_html=True)

time.sleep(30)
st.rerun()