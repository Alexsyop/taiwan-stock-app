"""
台股分析系統 — Streamlit App
==============================
部署方式：
  1. 上傳到 GitHub
  2. 到 share.streamlit.io 連結 repo
  3. iPhone Safari 開啟 → 加入主畫面

本機測試：
  pip install streamlit requests pandas numpy yfinance plotly
  streamlit run streamlit_app.py
"""

import time, warnings, re
from datetime import date, datetime, timedelta
from collections import defaultdict
import csv, io

import streamlit as st
import requests
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
try:
    import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception: pass

# ──────────────────────────────────────────────────────────────
# 頁面設定（必須是第一個 st 指令）
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="台股分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"Get Help": None, "Report a bug": None, "About": "台股策略分析系統 v2.0"}
)

# ──────────────────────────────────────────────────────────────
# 全域 CSS（手機優先）
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* 手機優先全域 */
[data-testid="stAppViewContainer"] { background: #f4f6f8 !important; }
[data-testid="stHeader"] { display: none; }
[data-testid="stSidebar"] { background: #1a2332 !important; }
.block-container { padding: 0.8rem 0.8rem 2rem !important; max-width: 750px; margin: 0 auto; }

/* 隱藏 Streamlit 預設元件 */
#MainMenu, footer, .stDeployButton { display: none !important; }

/* 卡片 */
.st-card { background: #fff; border-radius: 12px; padding: 14px 16px;
  margin-bottom: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }

/* 評等圓圈 */
.rating-s  { background:#1a5c38; color:#D0F0DC; }
.rating-a  { background:#27ae60; color:#fff; }
.rating-b  { background:#854F0B; color:#FAE0A8; }
.rating-c  { background:#A32D2D; color:#F7C1C1; }

/* 漲跌顏色 */
.up { color: #27ae60 !important; font-weight: 600; }
.dn { color: #c0392b !important; font-weight: 600; }
.wn { color: #e67e22 !important; }

/* 提示框 */
.box-ok   { background:#f0f9f4; border-left:3px solid #27ae60;
  padding:8px 12px; border-radius:0 6px 6px 0; font-size:13px; margin:6px 0; }
.box-warn { background:#fef9ec; border-left:3px solid #f39c12;
  padding:8px 12px; border-radius:0 6px 6px 0; font-size:13px; margin:6px 0; }
.box-danger { background:#fdf2f2; border-left:3px solid #e74c3c;
  padding:8px 12px; border-radius:0 6px 6px 0; font-size:13px; margin:6px 0; }

/* 按鈕美化 */
.stButton > button {
  background: #27ae60; color: #fff; border: none;
  border-radius: 8px; padding: 10px 20px;
  font-size: 15px; font-weight: 600; width: 100%;
  transition: opacity .15s;
}
.stButton > button:hover { opacity: .85; }
.stButton > button:active { opacity: .7; }

/* 底部 nav bar */
.bottom-nav {
  position: fixed; bottom: 0; left: 0; right: 0;
  background: #1a2332; display: flex; justify-content: space-around;
  padding: 8px 0 max(8px, env(safe-area-inset-bottom));
  z-index: 999; box-shadow: 0 -2px 8px rgba(0,0,0,.2);
}
.nav-btn { color: #8fa3b8; text-align: center; font-size: 10px;
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  cursor: pointer; padding: 4px 12px; border-radius: 8px; }
.nav-btn.active { color: #27ae60; }
.nav-btn-icon { font-size: 20px; line-height: 1; }

/* 股票標題列 */
.stock-header { background: #1a2332; border-radius: 12px 12px 0 0;
  padding: 14px 16px; color: #fff; }
.stock-sum { background: #fff; border-left: 4px solid #27ae60;
  border-radius: 0 0 0 0; padding: 10px 14px;
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.sum-cell p:first-child { font-size: 10px; color: #777; margin-bottom: 2px; }
.sum-cell p:last-child  { font-size: 17px; font-weight: 700; }

/* 標籤 */
.tag { display: inline-block; font-size: 10px; padding: 2px 7px;
  border-radius: 99px; font-weight: 500; margin: 2px; }
.tag-g { background:#27ae6022; color:#27ae60; border:1px solid #27ae6055; }
.tag-r { background:#e74c3c22; color:#e74c3c; border:1px solid #e74c3c55; }
.tag-a { background:#f39c1222; color:#e67e22; border:1px solid #f39c1255; }

/* 法人籌碼格 */
.chip-buy  { background:#eaf3de; border:1px solid #97c459; border-radius:8px;
  padding:9px; text-align:center; }
.chip-sell { background:#fceaea; border:1px solid #f09595; border-radius:8px;
  padding:9px; text-align:center; }
.chip-neut { background:#f8f9fa; border:1px solid #ddd; border-radius:8px;
  padding:9px; text-align:center; }

/* 手機底部安全距離 */
.pb-nav { padding-bottom: 70px; }

@media (max-width: 480px) {
  .block-container { padding: 0.5rem 0.5rem 5rem !important; }
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# Session State 初始化
# ──────────────────────────────────────────────────────────────
if "page"         not in st.session_state: st.session_state.page = "home"
if "results"      not in st.session_state: st.session_state.results = []
if "last_run"     not in st.session_state: st.session_state.last_run = None
if "scanner_data" not in st.session_state: st.session_state.scanner_data = {}
if "disposed_set" not in st.session_state: st.session_state.disposed_set = set()

# ──────────────────────────────────────────────────────────────
# 預設設定（可在 Secrets 或側邊欄覆寫）
# ──────────────────────────────────────────────────────────────
DEFAULT_TOKEN = st.secrets.get("FINMIND_TOKEN", "") if hasattr(st, "secrets") else ""
DEFAULT_STOCKS = "2330,2454,6669,3661,3034,3017,3037,6515,5274,2376"

HDR = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
FINMIND_API = "https://api.finmindtrade.com/api/v4/data"

STOCK_NAMES = {
    "2330":"台積電","2454":"聯發科","6669":"緯穎","3661":"世芯-KY",
    "3034":"聯詠","3017":"奇鋐","3037":"欣興","6515":"穎威",
    "5274":"信驊","2313":"華通","3048":"益登","3231":"緯創",
    "2376":"技嘉","2317":"鴻海","2382":"廣達","2308":"台達電",
    "2603":"長榮","2609":"陽明","1513":"中興電","3529":"力旺",
    "3293":"鈊象","3665":"貿聯-KY","3167":"達亮","2368":"金像電",
    "3081":"聯惠","2059":"川湖","6510":"精測","3048":"益登",
}

RATING_EMOJI = {"S":"⭐⭐","A":"✅","B":"👀","C":"❌"}
RATING_COLOR = {"S":"#1a5c38","A":"#27ae60","B":"#854F0B","C":"#A32D2D"}

# ──────────────────────────────────────────────────────────────
# 工具函式
# ──────────────────────────────────────────────────────────────
def to_f(s, d=0.0):
    try:    return float(str(s).replace(",","").strip())
    except: return d

def to_i(s, d=0):
    try:    return int(str(s).replace(",","").strip())
    except: return d

def safe_api(dataset, sid, start, token):
    try:
        r = requests.get(FINMIND_API, headers=HDR, timeout=20, verify=False,
            params={"dataset":dataset,"data_id":sid,"start_date":start,"token":token})
        if r.status_code == 200:
            d = r.json()
            return d.get("data",[])
    except Exception as e:
        st.warning(f"API 請求失敗（{sid}）：{e}")
    return []

def ma(closes, n):
    return round(sum(closes[-n:])/n,2) if len(closes)>=n else None

def dev(p,m):
    return round((p-m)/m*100,2) if p and m and m>0 else None

def calc_con(series):
    if not series: return 0
    last = series[-1]
    if last == 0: return 0
    d = 1 if last>0 else -1
    c = 0
    for v in reversed(series):
        if (v>0 and d==1) or (v<0 and d==-1): c+=1
        else: break
    return c*d

# ──────────────────────────────────────────────────────────────
# 資料抓取
# ──────────────────────────────────────────────────────────────
def fetch_price(sid, token):
    start = (date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows  = safe_api("TaiwanStockPrice", sid, start, token)
    recs  = []
    for r in rows:
        c = to_f(r.get("close",0))
        if c>0:
            recs.append({
                "date":  r.get("date","")[:10],
                "close": c,
                "high":  to_f(r.get("max",  r.get("high",0))),
                "low":   to_f(r.get("min",   r.get("low",0))),
                "vol":   to_i(r.get("Trading_Volume",0))//1000,
            })
    recs.sort(key=lambda x: x["date"])
    return recs

def fetch_institution(sid, token):
    start = (date.today()-timedelta(days=30)).strftime("%Y-%m-%d")
    rows  = safe_api("TaiwanStockInstitutionalInvestorsBuySell", sid, start, token)
    _F = {"Foreign_Investor","Foreign_Dealer_Self","外資"}
    _T = {"Investment_Trust","投信"}
    _D = {"Dealer_self","Dealer_Hedging","自營商"}
    dm  = defaultdict(lambda:{"f":0,"t":0,"d":0})
    for r in rows:
        name = str(r.get("name",""))
        net  = to_i(r.get("buy",0))-to_i(r.get("sell",0))
        d    = r.get("date","")[:10]
        if   name in _F or "Foreign" in name or "外資" in name: dm[d]["f"]+=net
        elif name in _T or "Trust"   in name or "投信" in name: dm[d]["t"]+=net
        elif name in _D or "Dealer"  in name or "自營" in name: dm[d]["d"]+=net
    result = []
    for d in sorted(dm.keys())[-5:]:
        v = dm[d]
        result.append({"date":d,"f":v["f"]//1000,"t":v["t"]//1000,"d":v["d"]//1000})
    return result

def fetch_per(sid, token):
    start = (date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows  = safe_api("TaiwanStockPER", sid, start, token)
    recs  = []
    for r in rows:
        pe = to_f(r.get("PER",r.get("PE",0)))
        if pe>0: recs.append({"date":r.get("date","")[:10],"pe":pe,"pbr":to_f(r.get("PBR",0))})
    recs.sort(key=lambda x: x["date"])
    return recs[-250:]

def get_target(sid):
    try:
        import yfinance as yf
        for suffix in (".TW",".TWO"):
            tk = yf.Ticker(f"{sid}{suffix}")
            tp = tk.info.get("targetMeanPrice")
            if tp and float(tp)>0:
                return float(tp), "Yahoo共識"
    except Exception: pass
    return None, "N/A"

def fetch_disposed():
    disposed = set()
    try:
        r = requests.get("https://openapi.twse.com.tw/v1/announcement/punish",
                         headers=HDR, timeout=10, verify=False)
        if r.status_code==200:
            for item in r.json():
                c = str(item.get("SecuritiesCode","")).strip()
                if c: disposed.add(c)
    except Exception: pass
    return disposed

# ──────────────────────────────────────────────────────────────
# 分析引擎
# ──────────────────────────────────────────────────────────────
def analyze_one(sid, token, disposed_set):
    price_rows = fetch_price(sid, token)
    if not price_rows:
        return None
    closes = [r["close"] for r in price_rows]
    last   = price_rows[-1]
    prev   = price_rows[-2] if len(price_rows)>=2 else last
    p      = last["close"]
    chg    = round((p-prev["close"])/prev["close"]*100,2) if prev["close"] else 0

    ma5  = ma(closes,5);  ma20=ma(closes,20)
    ma60 = ma(closes,60); ma200=ma(closes,200)
    dev5 = dev(p,ma5);    dev200=dev(p,ma200)

    inst = fetch_institution(sid, token)
    time.sleep(0.3)

    per_data = fetch_per(sid, token)
    pe_latest = per_data[-1]["pe"] if per_data else None
    pe_avg    = round(sum(r["pe"] for r in per_data[-250:])/len(per_data),1) if per_data else None
    pbr       = per_data[-1]["pbr"] if per_data else None
    time.sleep(0.3)

    tp, ts = get_target(sid)

    f_con = calc_con([d["f"] for d in inst])
    t_con = calc_con([d["t"] for d in inst])

    # 評分
    sc = 50; pos=[]; neg=[]; warn=[]
    if dev5 is not None:
        if   dev5<-5:  sc+=18; pos.append(f"5日線回測 {dev5:+.1f}%")
        elif dev5<=2:  sc+=10; pos.append(f"5日線乖離健康 {dev5:+.1f}%")
        elif dev5<=8:  sc+=2;  warn.append(f"5日線乖離偏高 {dev5:+.1f}%")
        else:          sc-=10; neg.append(f"5日線乖離過高 {dev5:+.1f}%")
    if dev200 and dev200>50: sc-=8; warn.append(f"年線乖離偏高 {dev200:+.1f}%")
    if tp and p:
        up=(tp-p)/p*100
        if   up>20:  sc+=15; pos.append(f"距目標+{up:.1f}%")
        elif up>10:  sc+=8;  pos.append(f"距目標+{up:.1f}%")
        elif up>0:   sc+=3
        elif up>-10: sc-=5;  warn.append(f"現價略超目標 {up:.1f}%")
        else:        sc-=12; neg.append(f"現價超目標 {up:.1f}%")
    if   f_con>=3: sc+=12; pos.append(f"外資連買{f_con}日")
    elif f_con>=1: sc+=5;  pos.append("外資今日買超")
    elif f_con<=-3:sc-=10; neg.append(f"外資連賣{abs(f_con)}日")
    elif f_con<0:  sc-=4;  warn.append("外資今日賣超")
    if   t_con>=5: sc+=12; pos.append(f"投信連買{t_con}日")
    elif t_con>=3: sc+=8;  pos.append(f"投信連買{t_con}日")
    elif t_con>=1: sc+=3;  pos.append("投信今日買超")
    elif t_con<=-3:sc-=10; neg.append(f"投信連賣{abs(t_con)}日")
    elif t_con<0:  sc-=4;  warn.append("投信今日賣超")
    if f_con>0 and t_con>0: sc+=5; pos.append("外資投信同向買超")
    elif f_con<0 and t_con<0: sc-=8; neg.append("外資投信同向賣超")
    if pe_latest and pe_avg and pe_avg>0:
        pv=(pe_latest-pe_avg)/pe_avg*100
        if   pv<-20: sc+=8; pos.append(f"PE低估（{pe_latest:.1f}x vs均{pe_avg:.1f}x）")
        elif pv<0:   sc+=4
        elif pv>20:  sc-=5; warn.append(f"PE偏高（{pe_latest:.1f}x）")
    sc = max(0,min(100,sc))
    if   sc>=80: r,l="S","強烈推薦"
    elif sc>=65: r,l="A","建議買入"
    elif sc>=45: r,l="B","觀　望"
    else:        r,l="C","避　開"

    return {
        "sid": sid, "name": STOCK_NAMES.get(sid, sid),
        "price": p, "prev": prev["close"], "chg": chg,
        "ma5": ma5, "ma20": ma20, "ma60": ma60, "ma200": ma200,
        "dev5": dev5, "dev200": dev200,
        "h52": round(max(r["high"] for r in price_rows[-252:]),2) if len(price_rows)>=252 else round(max(r["high"] for r in price_rows),2),
        "l52": round(min(r["low"]  for r in price_rows[-252:]),2) if len(price_rows)>=252 else round(min(r["low"]  for r in price_rows),2),
        "vol": last["vol"],
        "last5": [r["close"] for r in price_rows[-5:]],
        "inst": inst,
        "f_con": f_con, "t_con": t_con,
        "d_con": calc_con([d["d"] for d in inst]),
        "pe": pe_latest, "pe_avg": pe_avg, "pbr": pbr,
        "tp": tp, "ts": ts,
        "score": sc, "rating": r, "label": l,
        "pos": pos, "neg": neg, "warn": warn,
        "is_disposed": sid in disposed_set,
        "date": last["date"],
    }

# ──────────────────────────────────────────────────────────────
# UI 元件
# ──────────────────────────────────────────────────────────────
def render_stock_card(r):
    rc  = RATING_COLOR.get(r["rating"],"#854F0B")
    chg = r["chg"] or 0
    cc  = "up" if chg>=0 else "dn"
    devv = r.get("dev5") or 0

    # 標籤
    tags = ""
    if r["is_disposed"]: tags += '<span class="tag tag-r">🚨 處置股</span>'
    if r["t_con"]>=5:    tags += f'<span class="tag tag-g">投信連買{r["t_con"]}日</span>'
    elif r["t_con"]>=1:  tags += '<span class="tag tag-g">投信買超</span>'
    elif r["t_con"]<=-3: tags += f'<span class="tag tag-r">投信連賣{abs(r["t_con"])}日</span>'
    if r["f_con"]>=3:    tags += f'<span class="tag tag-g">外資連買{r["f_con"]}日</span>'
    elif r["f_con"]<=-3: tags += f'<span class="tag tag-r">外資連賣{abs(r["f_con"])}日</span>'
    if devv>8:           tags += f'<span class="tag tag-r">⚠乖離{devv:+.1f}%</span>'
    if r["tp"] and r["price"]:
        up=(r["tp"]-r["price"])/r["price"]*100
        if up>10: tags += f'<span class="tag tag-a">目標+{up:.0f}%</span>'

    # 主卡片 HTML
    st.markdown(f"""
<div style="margin-bottom:12px">
<div class="stock-header">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <div style="font-size:18px;font-weight:700">{r['name']}
        <span style="font-size:13px;color:#8fa3b8;font-weight:400"> {r['sid']}</span>
      </div>
      <div style="font-size:11px;color:#8fa3b8;margin-top:2px">
        {r.get('date','')} | 評分 {r['score']}/100
      </div>
      <div style="margin-top:8px">{tags}</div>
    </div>
    <div style="width:56px;height:56px;border-radius:50%;background:{rc};
      display:flex;flex-direction:column;align-items:center;justify-content:center;
      flex-shrink:0">
      <span style="font-size:20px;font-weight:700;color:white;line-height:1">{r['rating']}</span>
      <span style="font-size:8px;color:rgba(255,255,255,.7)">{r['label']}</span>
    </div>
  </div>
</div>
<div class="stock-sum">
  <div class="sum-cell"><p>今日收盤</p>
    <p class="{cc}">{r['price']:,.1f} 元</p></div>
  <div class="sum-cell"><p>漲跌幅</p>
    <p class="{cc}">{("+" if chg>=0 else "")}{chg:.2f}%</p></div>
  <div class="sum-cell"><p>5日線乖離</p>
    <p class="{'wn' if abs(devv)>5 else ''}">{devv:+.1f}%</p></div>
  <div class="sum-cell"><p>目標價</p>
    <p>{f"{r['tp']:,.0f}元" if r['tp'] else "N/A"}</p></div>
</div>
</div>
""", unsafe_allow_html=True)

    with st.expander("📋 詳細分析", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**技術面**")
            st.write(f"MA5：{r['ma5'] or 'N/A'} 元")
            st.write(f"MA20：{r['ma20'] or 'N/A'} 元")
            st.write(f"MA200：{r['ma200'] or 'N/A'} 元")
            st.write(f"52W 高：{r.get('h52','N/A')} 元")
            st.write(f"52W 低：{r.get('l52','N/A')} 元")

        with col2:
            st.markdown("**估值**")
            st.write(f"PE：{r['pe'] or 'N/A'}x")
            st.write(f"年均PE：{r['pe_avg'] or 'N/A'}x")
            st.write(f"PBR：{r['pbr'] or 'N/A'}x")
            if r["tp"]:
                up = (r["tp"]-r["price"])/r["price"]*100
                st.write(f"目標：{r['tp']:,.0f}元（{up:+.1f}%）")
                st.write(f"來源：{r['ts']}")

        # 籌碼
        st.markdown("**三大法人（近5日，張）**")
        if r["inst"]:
            inst_df = pd.DataFrame(r["inst"])
            inst_df.columns = [c.replace("date","日期").replace("f","外資").replace("t","投信").replace("d","自營商")
                                for c in inst_df.columns]
            st.dataframe(inst_df, use_container_width=True, hide_index=True)

        # 近5日K線 mini chart
        if r.get("last5"):
            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                y=r["last5"], mode="lines+markers",
                line=dict(color="#27ae60" if r["last5"][-1]>=r["last5"][0] else "#e74c3c", width=2),
                marker=dict(size=5)
            ))
            fig.update_layout(
                height=100, margin=dict(l=0,r=0,t=0,b=0),
                showlegend=False, plot_bgcolor="#f8f9fa",
                xaxis=dict(showgrid=False,showticklabels=False),
                yaxis=dict(showgrid=True,gridcolor="#eee",showticklabels=True,
                           tickfont=dict(size=9))
            )
            st.plotly_chart(fig, use_container_width=True)

        # 評分說明
        if r["pos"]:
            for p in r["pos"][:3]:
                st.markdown(f'<div class="box-ok">✅ {p}</div>', unsafe_allow_html=True)
        if r["neg"]:
            for n in r["neg"][:2]:
                st.markdown(f'<div class="box-danger">✗ {n}</div>', unsafe_allow_html=True)
        if r["warn"]:
            for w in r["warn"][:2]:
                st.markdown(f'<div class="box-warn">⚠ {w}</div>', unsafe_allow_html=True)
        if r["is_disposed"]:
            st.error("🚨 **處置股警告**：處置期間流動性極差，策略建議暫不操作，靜待出關。")


# ──────────────────────────────────────────────────────────────
# 頁面：首頁 / 分析儀表板
# ──────────────────────────────────────────────────────────────
def page_home():
    st.markdown('<div class="pb-nav">', unsafe_allow_html=True)

    # App 標題
    st.markdown("""
    <div style="background:#1a2332;border-radius:14px;padding:16px 20px;margin-bottom:16px">
      <div style="font-size:22px;font-weight:700;color:#fff">📊 台股分析系統</div>
      <div style="font-size:12px;color:#8fa3b8;margin-top:4px">
        三大法人籌碼 × 技術面 × 基本面 × 目標價
      </div>
    </div>
    """, unsafe_allow_html=True)

    token     = st.session_state.get("token","")
    stock_str = st.session_state.get("stock_list", DEFAULT_STOCKS)
    sids      = [s.strip() for s in stock_str.split(",") if s.strip()]

    if not token:
        st.warning("⚠️ 請先到「⚙️ 設定」頁填入 FinMind Token")
        if st.button("前往設定"):
            st.session_state.page = "settings"
            st.rerun()
        return

    # 上次更新時間
    if st.session_state.last_run:
        diff = datetime.now()-st.session_state.last_run
        mins = int(diff.total_seconds()//60)
        st.caption(f"最後更新：{st.session_state.last_run.strftime('%H:%M')}（{mins} 分鐘前）")

    col1, col2 = st.columns([3,1])
    with col1:
        run_all = st.button("🔄 開始分析全部股票", use_container_width=True)
    with col2:
        pass

    if run_all:
        with st.spinner("分析中..."):
            disposed_set = fetch_disposed()
            st.session_state.disposed_set = disposed_set

            results = []
            bar = st.progress(0, text="準備中...")
            for i, sid in enumerate(sids):
                bar.progress((i+1)/len(sids),
                             text=f"分析 {STOCK_NAMES.get(sid,sid)} ({sid}) {i+1}/{len(sids)}")
                r = analyze_one(sid, token, disposed_set)
                if r:
                    results.append(r)
                time.sleep(0.5)
            bar.empty()

            st.session_state.results = sorted(results, key=lambda x:x["score"], reverse=True)
            st.session_state.last_run = datetime.now()
            st.success(f"✅ 完成！分析了 {len(results)} 支股票")

    # 顯示結果
    results = st.session_state.results
    if not results:
        st.info("點「開始分析」取得最新數據")
        return

    # 評等統計
    from collections import Counter
    cnts = Counter(r["rating"] for r in results)
    c1,c2,c3,c4 = st.columns(4)
    for col, (rating, label, emoji) in zip(
        [c1,c2,c3,c4],
        [("S","強烈推薦","⭐"),("A","建議買入","✅"),("B","觀望","👀"),("C","避開","❌")]
    ):
        col.metric(f"{emoji} {rating}", cnts.get(rating,0), label)

    st.markdown("---")

    # 篩選
    filter_opt = st.selectbox("顯示篩選",
        ["全部", "S（強烈推薦）","A（建議買入）","B（觀望）","C（避開）","處置股"],
        label_visibility="collapsed")

    filtered = results
    if "S（" in filter_opt:   filtered = [r for r in results if r["rating"]=="S"]
    elif "A（" in filter_opt: filtered = [r for r in results if r["rating"]=="A"]
    elif "B（" in filter_opt: filtered = [r for r in results if r["rating"]=="B"]
    elif "C（" in filter_opt: filtered = [r for r in results if r["rating"]=="C"]
    elif "處置" in filter_opt: filtered = [r for r in results if r["is_disposed"]]

    for r in filtered:
        render_stock_card(r)

    st.markdown('</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 頁面：排行榜
# ──────────────────────────────────────────────────────────────
def page_rank():
    st.markdown('<div class="pb-nav">', unsafe_allow_html=True)
    st.markdown("### 🏆 今日評等排行")

    results = st.session_state.results
    if not results:
        st.info("請先在「首頁」執行分析")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # 建立 DataFrame
    df = pd.DataFrame([{
        "評等": r["rating"],
        "股票": f"{r['name']}({r['sid']})",
        "分數": r["score"],
        "現價": r["price"],
        "漲跌%": r["chg"],
        "外資": r["f_con"],
        "投信": r["t_con"],
        "目標": r["tp"] or "-",
        "來源": r["ts"],
    } for r in results])

    # 顯示
    st.dataframe(
        df.style.apply(
            lambda row: ["background-color: #d0f0dc" if row["評等"] in ("S","A")
                        else "background-color: #fdf2f2" if row["評等"]=="C"
                        else "" for _ in row], axis=1),
        use_container_width=True, hide_index=True
    )

    # 外資 / 投信同向買超
    buy_both = [r for r in results if r["f_con"]>0 and r["t_con"]>0]
    if buy_both:
        st.markdown("### ✅ 外資+投信同向買超")
        for r in sorted(buy_both, key=lambda x:(x["f_con"]+x["t_con"]), reverse=True):
            chg = r["chg"] or 0
            st.markdown(f"""
            <div class="st-card" style="border-left:4px solid #27ae60">
              <strong>{r['name']}（{r['sid']}）</strong>　
              <span class="{'up' if chg>=0 else 'dn'}">{r['price']:,.0f}元
              {("+" if chg>=0 else "")}{chg:.1f}%</span>　
              外資: <span class="up">+{r['f_con']}日</span>　
              投信: <span class="up">+{r['t_con']}日</span>　
              評分: <strong>{r['score']}</strong>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 頁面：籌碼掃描
# ──────────────────────────────────────────────────────────────
def page_scanner():
    st.markdown('<div class="pb-nav">', unsafe_allow_html=True)
    st.markdown("### 📡 籌碼掃描")

    results = st.session_state.results
    if not results:
        st.info("請先在「首頁」執行分析，即可看到籌碼掃描結果")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    disposed = st.session_state.disposed_set

    # 策略一：外資+投信同向，吸籌率>5%
    st.markdown("#### 🔥 法人焦點熱門股（外資+投信同向，吸籌率≥5%）")
    hot = []
    for r in results:
        if r["is_disposed"]: continue
        inst = r["inst"]
        if not inst: continue
        ft = inst[-1]["f"]; tt = inst[-1]["t"]
        vol = r.get("vol",0) or 1
        if ft>0 and tt>0:
            ab = (ft+tt)/vol*100
            if ab>=5:
                hot.append({**r, "ft":ft,"tt":tt,"absorption":round(ab,1)})
    hot.sort(key=lambda x:x["absorption"], reverse=True)
    if hot:
        for r in hot[:10]:
            tier = "🔴極熱" if r["absorption"]>=15 else "🟠熱門" if r["absorption"]>=8 else "🟡升溫"
            st.markdown(f"""
            <div class="st-card" style="border-left:4px solid #27ae60">
              <div style="display:flex;justify-content:space-between">
                <div>
                  <strong>{r['name']}（{r['sid']}）</strong>
                  <span style="font-size:11px;color:#888;margin-left:6px">{r['date']}</span>
                </div>
                <span style="font-weight:700;color:#e67e22">{tier} {r['absorption']}%</span>
              </div>
              <div style="margin-top:6px;font-size:13px">
                現價 <strong>{r['price']:,.0f}</strong>元　
                外資 <span class="up">+{r['ft']:,}張</span>　
                投信 <span class="up">+{r['tt']:,}張</span>　
                評分 <strong>{r['score']}</strong>
              </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("今日無外資+投信同向且吸籌率≥5%的個股")

    # 策略二：投信鎖碼
    st.markdown("#### 🕵️ 投信佈局觀察（10日買超天數≥5，漲幅<7%）")
    trust_build = []
    for r in results:
        if r["is_disposed"]: continue
        inst = r["inst"]
        if len(inst)<5: continue
        t_vals = [d["t"] for d in inst]
        buy_days = sum(1 for v in t_vals if v>0)
        if buy_days>=4:
            trust_build.append({**r,"buy_days":buy_days,"t_total":sum(t_vals)})
    trust_build.sort(key=lambda x:x["buy_days"], reverse=True)
    if trust_build:
        for r in trust_build:
            st.markdown(f"""
            <div class="st-card" style="border-left:4px solid #8e44ad">
              <strong>{r['name']}（{r['sid']}）</strong>
              <span style="float:right;color:#8e44ad;font-weight:700">{r['buy_days']}/5天買超</span><br>
              <span style="font-size:13px">
                現價 {r['price']:,.0f}元　漲幅 {r["chg"]:+.1f}%　
                5日投信累計 +{r['t_total']:,}張
              </span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("持股清單中目前無符合條件的佈局股")

    st.markdown('</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 頁面：設定
# ──────────────────────────────────────────────────────────────
def page_settings():
    st.markdown('<div class="pb-nav">', unsafe_allow_html=True)
    st.markdown("### ⚙️ 設定")

    with st.form("settings_form"):
        token = st.text_input(
            "FinMind Token",
            value=st.session_state.get("token", DEFAULT_TOKEN),
            type="password",
            help="從 FinMind 網站取得，請妥善保管"
        )
        stock_list = st.text_area(
            "追蹤股票清單（股號以逗號分隔）",
            value=st.session_state.get("stock_list", DEFAULT_STOCKS),
            height=120,
            help="最多建議 20 支，太多會跑很久"
        )
        save = st.form_submit_button("💾 儲存設定", use_container_width=True)

    if save:
        st.session_state.token      = token.strip()
        st.session_state.stock_list = stock_list.strip()
        st.success("✅ 設定已儲存！回首頁重新分析即可套用。")

    st.markdown("---")
    st.markdown("#### ℹ️ 使用說明")
    st.markdown("""
    **分析流程：**
    1. 輸入 FinMind Token（免費）
    2. 設定追蹤股票清單（預設 10 支）
    3. 回首頁點「開始分析」
    4. 等待約 1-2 分鐘（每支約 8 秒）
    5. 查看評等、籌碼、目標價

    **取得 FinMind Token：**
    - 前往 [finmindtrade.com](https://finmindtrade.com)
    - 免費註冊後在帳號頁面取得 Token

    **安裝為 App（iPhone）：**
    - Safari 開啟此頁面
    - 點右下角「分享」圖示
    - 選「加入主畫面」
    - 即可像 App 一樣開啟
    """)

    st.markdown("---")
    st.markdown("#### 🔧 進階參數")
    with st.expander("調整掃描參數"):
        st.slider("吸籌率門檻（%）",1,20,5,key="hot_absorption")
        st.slider("投信連買天數門檻",2,7,4,key="trust_days")
        st.slider("投信發動最低張數",100,1000,500,step=50,key="launch_lots")

    st.markdown('</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 底部導覽列
# ──────────────────────────────────────────────────────────────
def render_bottom_nav():
    pages = [
        ("home",    "🏠", "首頁"),
        ("rank",    "🏆", "排行"),
        ("scanner", "📡", "掃描"),
        ("settings","⚙️", "設定"),
    ]
    current = st.session_state.page
    cols = st.columns(len(pages))
    for col, (pid, icon, label) in zip(cols, pages):
        active = "font-weight:700;color:#27ae60;" if current==pid else "color:#8fa3b8;"
        with col:
            if st.button(f"{icon}\n{label}", key=f"nav_{pid}",
                         use_container_width=True):
                st.session_state.page = pid
                st.rerun()


# ──────────────────────────────────────────────────────────────
# 主程式
# ──────────────────────────────────────────────────────────────
def main():
    # 頂部導覽（手機風格）
    render_bottom_nav()

    # 路由
    page = st.session_state.page
    if   page == "home":    page_home()
    elif page == "rank":    page_rank()
    elif page == "scanner": page_scanner()
    elif page == "settings":page_settings()


if __name__ == "__main__":
    main()
