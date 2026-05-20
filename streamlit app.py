"""
台股分析系統 — Streamlit App v2（修正版）
用 st.tabs() 取代 fixed 底部導覽，手機顯示正常
"""

import time, warnings
from datetime import date, datetime, timedelta
from collections import defaultdict

import streamlit as st
import requests
import pandas as pd

warnings.filterwarnings("ignore")
try:
    import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception: pass

# ── 頁面設定（必須第一行）──────────────────────────────────
st.set_page_config(
    page_title="台股分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #f4f6f8 !important; }
[data-testid="stHeader"] { display:none; }
#MainMenu, footer { display:none !important; }
.block-container { padding: 0.6rem 0.8rem 1rem !important;
                   max-width: 720px; margin: 0 auto; }

/* ── 強制全域文字深色（修正淺色問題）── */
*, p, span, div, label,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stText"],
[data-testid="stExpander"] p,
[data-testid="stExpander"] span,
[data-testid="stExpander"] label,
[data-testid="stExpander"] div {
  color: #1a1a1a !important;
}

/* expander 本體白底深字 */
[data-testid="stExpander"] {
  background: #fff !important;
  border: 1px solid #e0e6ed !important;
  border-radius: 8px !important;
}
[data-testid="stExpander"] summary {
  background: #f4f6f8 !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
  color: #1a2332 !important;
}

/* dataframe 文字 */
[data-testid="stDataFrame"] * { color: #1a1a1a !important; }

/* st.write / st.markdown 輸出 */
.stMarkdown, .stText { color: #1a1a1a !important; }

/* 分頁標籤美化 */
.stTabs [data-baseweb="tab-list"] {
  background: #1a2332; border-radius: 10px; padding: 4px;
  gap: 4px; position: sticky; top: 0; z-index: 99;
}
.stTabs [data-baseweb="tab"] {
  border-radius: 8px; color: #8fa3b8 !important;
  font-size: 13px; font-weight: 600; padding: 6px 0;
}
.stTabs [aria-selected="true"] {
  background: #27ae60 !important; color: #fff !important;
}

/* 按鈕 */
.stButton > button {
  background: #27ae60 !important; color: #fff !important;
  border: none; border-radius: 10px;
  font-size: 16px; font-weight: 700; padding: 14px; width: 100%;
}
.stButton > button:hover { opacity:.85; }
.stButton > button:disabled { background: #aaa !important; }

/* 卡片 */
.st-card { background:#fff; border-radius:12px; padding:14px 16px;
  margin-bottom:10px; box-shadow:0 1px 5px rgba(0,0,0,.08); }

/* 顏色（漲跌/評等）─ 強制覆蓋 */
.up  { color:#27ae60 !important; font-weight:600; }
.dn  { color:#c0392b !important; font-weight:600; }
.wn  { color:#e67e22 !important; font-weight:600; }

/* 提示框 */
.box-ok     { background:#f0f9f4; border-left:3px solid #27ae60;
  padding:8px 12px; border-radius:0 6px 6px 0;
  font-size:12px; margin:5px 0; color:#145a2c !important; }
.box-danger { background:#fdf2f2; border-left:3px solid #e74c3c;
  padding:8px 12px; border-radius:0 6px 6px 0;
  font-size:12px; margin:5px 0; color:#7b1818 !important; }
.box-warn   { background:#fef9ec; border-left:3px solid #f39c12;
  padding:8px 12px; border-radius:0 6px 6px 0;
  font-size:12px; margin:5px 0; color:#7d4e00 !important; }

/* 標籤 */
.tag { display:inline-block; font-size:10px; padding:2px 7px;
  border-radius:99px; font-weight:600; margin:2px; }
.tag-g { background:#27ae6022; color:#145a2c !important;
  border:1px solid #27ae6055; }
.tag-r { background:#e74c3c22; color:#7b1818 !important;
  border:1px solid #e74c3c55; }
.tag-a { background:#f39c1222; color:#7d4e00 !important;
  border:1px solid #f39c1255; }

/* selectbox 文字 */
[data-testid="stSelectbox"] * { color: #1a1a1a !important; }

/* input / textarea */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
  color: #1a1a1a !important; background: #fff !important; }
</style>
""", unsafe_allow_html=True)

# ── Session State ───────────────────────────────────────────
for k, v in [("results",[]),("last_run",None),("disposed",set()),("token","")]:
    if k not in st.session_state: st.session_state[k] = v

# ── 常數 ────────────────────────────────────────────────────
FINMIND_API = "https://api.finmindtrade.com/api/v4/data"
HDR = {"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"}
STOCK_NAMES = {
    "2330":"台積電","2454":"聯發科","6669":"緯穎","3661":"世芯-KY",
    "3034":"聯詠","3017":"奇鋐","3037":"欣興","6515":"穎威",
    "5274":"信驊","2313":"華通","3048":"益登","3231":"緯創",
    "2376":"技嘉","2317":"鴻海","2382":"廣達","2308":"台達電",
    "2603":"長榮","2609":"陽明","1513":"中興電","3293":"鈊象",
}
RATING_COLOR = {"S":"#1a5c38","A":"#27ae60","B":"#854F0B","C":"#A32D2D"}
DEFAULT_LIST = "2330,2454,6669,3661,3034,3017,3037,6515,5274,2376"

# ── 工具 ────────────────────────────────────────────────────
def to_f(s,d=0.0):
    try: return float(str(s).replace(",","").strip())
    except: return d
def to_i(s,d=0):
    try: return int(str(s).replace(",","").strip())
    except: return d
def ma(closes,n):
    return round(sum(closes[-n:])/n,2) if len(closes)>=n else None
def dev(p,m):
    return round((p-m)/m*100,2) if p and m and m>0 else None
def calc_con(series):
    if not series: return 0
    last=series[-1];
    if last==0: return 0
    d=1 if last>0 else -1; c=0
    for v in reversed(series):
        if (v>0 and d==1) or (v<0 and d==-1): c+=1
        else: break
    return c*d

# ── API 呼叫 ────────────────────────────────────────────────
def call_api(dataset, sid, start, token):
    try:
        r = requests.get(FINMIND_API, headers=HDR, timeout=20, verify=False,
            params={"dataset":dataset,"data_id":sid,"start_date":start,"token":token})
        if r.status_code==200:
            return r.json().get("data",[])
    except Exception as e:
        st.toast(f"⚠ {sid} API 失敗：{e}", icon="⚠️")
    return []

def fetch_price(sid, token):
    start = (date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows  = call_api("TaiwanStockPrice", sid, start, token)
    recs  = []
    for r in rows:
        c=to_f(r.get("close",0))
        if c>0:
            recs.append({"date":r.get("date","")[:10],"close":c,
                         "high":to_f(r.get("max",r.get("high",0))),
                         "low":to_f(r.get("min",r.get("low",0))),
                         "vol":to_i(r.get("Trading_Volume",0))//1000})
    recs.sort(key=lambda x:x["date"])
    return recs

def fetch_institution(sid, token):
    start = (date.today()-timedelta(days=30)).strftime("%Y-%m-%d")
    rows  = call_api("TaiwanStockInstitutionalInvestorsBuySell", sid, start, token)
    dm    = defaultdict(lambda:{"f":0,"t":0,"d":0})
    for r in rows:
        name=str(r.get("name",""))
        net=to_i(r.get("buy",0))-to_i(r.get("sell",0))
        d=r.get("date","")[:10]
        if "Foreign" in name or "外資" in name: dm[d]["f"]+=net
        elif "Trust" in name or "投信" in name: dm[d]["t"]+=net
        elif "Dealer" in name or "自營" in name:dm[d]["d"]+=net
    return [{"date":d,"f":dm[d]["f"]//1000,"t":dm[d]["t"]//1000,"d":dm[d]["d"]//1000}
            for d in sorted(dm.keys())[-5:]]

def fetch_per(sid, token):
    start = (date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows  = call_api("TaiwanStockPER", sid, start, token)
    recs  = [{"pe":to_f(r.get("PER",0)),"pbr":to_f(r.get("PBR",0))}
             for r in rows if to_f(r.get("PER",0))>0]
    return recs[-250:] if recs else []

def get_tp(sid):
    try:
        import yfinance as yf
        for s in (".TW",".TWO"):
            tp = yf.Ticker(f"{sid}{s}").info.get("targetMeanPrice")
            if tp and float(tp)>0: return float(tp),"Yahoo共識"
    except: pass
    return None,"N/A"

def fetch_disposed():
    disposed=set()
    try:
        r=requests.get("https://openapi.twse.com.tw/v1/announcement/punish",
                       headers=HDR,timeout=10,verify=False)
        if r.status_code==200:
            for item in r.json():
                c=str(item.get("SecuritiesCode","")).strip()
                if c: disposed.add(c)
    except: pass
    return disposed

# ── 分析引擎 ────────────────────────────────────────────────
def analyze_one(sid, token, disposed):
    rows = fetch_price(sid, token)
    if not rows: return None
    closes=[r["close"] for r in rows]
    last=rows[-1]; prev=rows[-2] if len(rows)>=2 else last
    p=last["close"]
    chg=round((p-prev["close"])/prev["close"]*100,2) if prev["close"] else 0

    ma5=ma(closes,5); ma20=ma(closes,20); ma60=ma(closes,60); ma200=ma(closes,200)
    dev5=dev(p,ma5); dev200=dev(p,ma200)

    inst=fetch_institution(sid,token); time.sleep(0.3)
    per=fetch_per(sid,token)
    pe=per[-1]["pe"] if per else None
    pe_avg=round(sum(r["pe"] for r in per)/len(per),1) if per else None
    pbr=per[-1]["pbr"] if per else None
    time.sleep(0.3)
    tp,ts=get_tp(sid)

    f_con=calc_con([d["f"] for d in inst])
    t_con=calc_con([d["t"] for d in inst])

    sc=50; pos=[]; neg=[]; warn=[]
    if dev5 is not None:
        if   dev5<-5:  sc+=18;pos.append(f"5日線回測{dev5:+.1f}%")
        elif dev5<=2:  sc+=10;pos.append(f"5日乖離健康{dev5:+.1f}%")
        elif dev5<=8:  sc+=2; warn.append(f"5日乖離偏高{dev5:+.1f}%")
        else:          sc-=10;neg.append(f"5日乖離過高{dev5:+.1f}%")
    if dev200 and dev200>50: sc-=8;warn.append(f"年線乖離偏高{dev200:+.1f}%")
    if tp and p:
        up=(tp-p)/p*100
        if   up>20:  sc+=15;pos.append(f"距目標+{up:.1f}%")
        elif up>10:  sc+=8; pos.append(f"距目標+{up:.1f}%")
        elif up>0:   sc+=3
        elif up>-10: sc-=5; warn.append(f"現價略超目標{up:.1f}%")
        else:        sc-=12;neg.append(f"現價超目標{up:.1f}%")
    if   f_con>=3: sc+=12;pos.append(f"外資連買{f_con}日")
    elif f_con>=1: sc+=5; pos.append("外資今日買超")
    elif f_con<=-3:sc-=10;neg.append(f"外資連賣{abs(f_con)}日")
    elif f_con<0:  sc-=4; warn.append("外資今日賣超")
    if   t_con>=5: sc+=12;pos.append(f"投信連買{t_con}日")
    elif t_con>=3: sc+=8; pos.append(f"投信連買{t_con}日")
    elif t_con>=1: sc+=3; pos.append("投信今日買超")
    elif t_con<=-3:sc-=10;neg.append(f"投信連賣{abs(t_con)}日")
    elif t_con<0:  sc-=4; warn.append("投信今日賣超")
    if f_con>0 and t_con>0:  sc+=5;pos.append("外資投信同向買超")
    elif f_con<0 and t_con<0:sc-=8;neg.append("外資投信同向賣超")
    if pe and pe_avg and pe_avg>0:
        pv=(pe-pe_avg)/pe_avg*100
        if   pv<-20:sc+=8; pos.append(f"PE低估{pe:.1f}x")
        elif pv<0:  sc+=4
        elif pv>20: sc-=5; warn.append(f"PE偏高{pe:.1f}x")
    sc=max(0,min(100,sc))
    if   sc>=80: r2,l="S","強烈推薦"
    elif sc>=65: r2,l="A","建議買入"
    elif sc>=45: r2,l="B","觀　望"
    else:        r2,l="C","避　開"

    r52=rows[-252:] if len(rows)>=252 else rows
    return {
        "sid":sid,"name":STOCK_NAMES.get(sid,sid),
        "price":p,"prev":prev["close"],"chg":chg,
        "ma5":ma5,"ma20":ma20,"ma60":ma60,"ma200":ma200,
        "dev5":dev5,"dev200":dev200,
        "h52":round(max(r["high"] for r in r52),2),
        "l52":round(min(r["low"]  for r in r52),2),
        "vol":last["vol"],"last5":[r["close"] for r in rows[-5:]],
        "inst":inst,"f_con":f_con,"t_con":t_con,
        "d_con":calc_con([d["d"] for d in inst]),
        "pe":pe,"pe_avg":pe_avg,"pbr":pbr,
        "tp":tp,"ts":ts,"score":sc,"rating":r2,"label":l,
        "pos":pos,"neg":neg,"warn":warn,
        "is_disposed":sid in disposed,"date":last["date"],
    }

# ── 卡片元件 ────────────────────────────────────────────────
def stock_card(r):
    rc  = RATING_COLOR.get(r["rating"],"#854F0B")
    chg = r["chg"] or 0
    cc  = "up" if chg>=0 else "dn"
    d5  = r.get("dev5") or 0
    tags = ""
    if r["is_disposed"]: tags+='<span class="tag tag-r">🚨處置股</span>'
    if r["t_con"]>=5:    tags+=f'<span class="tag tag-g">投信連買{r["t_con"]}日</span>'
    elif r["t_con"]>=1:  tags+='<span class="tag tag-g">投信買超</span>'
    elif r["t_con"]<=-3: tags+=f'<span class="tag tag-r">投信連賣{abs(r["t_con"])}日</span>'
    if r["f_con"]>=3:    tags+=f'<span class="tag tag-g">外資連買{r["f_con"]}日</span>'
    elif r["f_con"]<=-3: tags+=f'<span class="tag tag-r">外資連賣{abs(r["f_con"])}日</span>'
    elif r["f_con"]<0:   tags+='<span class="tag tag-a">外資賣超</span>'
    if r["tp"] and r["price"]:
        up=(r["tp"]-r["price"])/r["price"]*100
        if up>10: tags+=f'<span class="tag tag-a">目標+{up:.0f}%</span>'

    st.markdown(f"""
<div style="margin-bottom:12px">
  <div style="background:#1a2332;border-radius:12px 12px 0 0;padding:14px 16px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div>
        <div style="font-size:19px;font-weight:700;color:#fff">
          {r['name']} <span style="font-size:13px;color:#8fa3b8;font-weight:400">{r['sid']}</span>
        </div>
        <div style="font-size:11px;color:#8fa3b8;margin-top:2px">
          {r.get('date','')} &nbsp;|&nbsp; 評分 <strong style="color:#27ae60">{r['score']}</strong>/100
        </div>
        <div style="margin-top:8px">{tags}</div>
      </div>
      <div style="width:56px;height:56px;border-radius:50%;background:{rc};flex-shrink:0;
        display:flex;flex-direction:column;align-items:center;justify-content:center">
        <span style="font-size:20px;font-weight:700;color:#fff;line-height:1">{r['rating']}</span>
        <span style="font-size:8px;color:rgba(255,255,255,.75)">{r['label']}</span>
      </div>
    </div>
  </div>
  <div style="background:#fff;border-left:4px solid {rc};border-radius:0 0 0 0;
    padding:10px 14px;display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div>
      <div style="font-size:10px;color:#777;text-transform:uppercase;margin-bottom:2px">今日收盤</div>
      <div style="font-size:18px;font-weight:700" class="{cc}">{r['price']:,.1f} 元</div>
    </div>
    <div>
      <div style="font-size:10px;color:#777;text-transform:uppercase;margin-bottom:2px">漲跌幅</div>
      <div style="font-size:18px;font-weight:700" class="{cc}">{("+" if chg>=0 else "")}{chg:.2f}%</div>
    </div>
    <div>
      <div style="font-size:10px;color:#777;text-transform:uppercase;margin-bottom:2px">5日線乖離</div>
      <div style="font-size:18px;font-weight:700" class="{'wn' if abs(d5)>5 else ''}">{d5:+.1f}%</div>
    </div>
    <div>
      <div style="font-size:10px;color:#777;text-transform:uppercase;margin-bottom:2px">目標價</div>
      <div style="font-size:18px;font-weight:700">{f"{r['tp']:,.0f}元" if r['tp'] else "N/A"}</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    with st.expander("▼ 展開詳細分析"):
        # ── 技術面 ────────────────────────────────────────────
        st.markdown('''<div style="font-size:14px;font-weight:700;color:#1a2332;
            padding:6px 0;border-bottom:2px solid #27ae60;margin-bottom:8px">
            📐 技術面</div>''', unsafe_allow_html=True)
        tech_rows = [
            ("MA5",   f"{r['ma5']:,.1f} 元"   if r["ma5"]   else "N/A"),
            ("MA20",  f"{r['ma20']:,.1f} 元"  if r["ma20"]  else "N/A"),
            ("MA60",  f"{r['ma60']:,.1f} 元"  if r["ma60"]  else "N/A"),
            ("MA200", f"{r['ma200']:,.1f} 元" if r["ma200"] else "N/A"),
            ("52W 高", f"{r.get('h52','N/A')} 元"),
            ("52W 低", f"{r.get('l52','N/A')} 元"),
            ("5日乖離", f"{r.get('dev5',0):+.1f}%"),
        ]
        for lbl,val in tech_rows:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;'
                f'padding:5px 2px;border-bottom:1px solid #eee;font-size:14px">'
                f'<span style="color:#555">{lbl}</span>'
                f'<strong style="color:#1a2332">{val}</strong></div>',
                unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── 估值 ──────────────────────────────────────────────
        st.markdown('''<div style="font-size:14px;font-weight:700;color:#1a2332;
            padding:6px 0;border-bottom:2px solid #27ae60;margin-bottom:8px">
            💰 估值指標</div>''', unsafe_allow_html=True)
        val_rows = [
            ("本益比 PE",  f"{r['pe']:.1f}x"    if r["pe"]    else "N/A"),
            ("年均 PE",    f"{r['pe_avg']:.1f}x" if r["pe_avg"] else "N/A"),
            ("淨值比 PBR", f"{r['pbr']:.2f}x"   if r["pbr"]   else "N/A"),
        ]
        if r["tp"]:
            up=(r["tp"]-r["price"])/r["price"]*100
            uc="color:#27ae60" if up>0 else "color:#c0392b"
            val_rows += [
                ("目標價", f"{r['tp']:,.0f} 元"),
                ("空間",   f"<span style='{uc};font-weight:700'>{up:+.1f}%</span>"),
                ("來源",   r["ts"]),
            ]
        for lbl,val in val_rows:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;'
                f'padding:5px 2px;border-bottom:1px solid #eee;font-size:14px">'
                f'<span style="color:#555">{lbl}</span>'
                f'<strong style="color:#1a2332">{val}</strong></div>',
                unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── 三大法人 ──────────────────────────────────────────
        if r["inst"]:
            st.markdown('''<div style="font-size:14px;font-weight:700;color:#1a2332;
                padding:6px 0;border-bottom:2px solid #27ae60;margin-bottom:8px">
                💼 三大法人近5日（張）</div>''', unsafe_allow_html=True)
            df=pd.DataFrame(r["inst"])
            df.columns=["日期","外資","投信","自營商"]
            st.dataframe(df,use_container_width=True,hide_index=True)

        # ── 評分依據 ──────────────────────────────────────────
        if r["pos"] or r["neg"] or r["warn"]:
            st.markdown('''<div style="font-size:14px;font-weight:700;color:#1a2332;
                padding:6px 0;border-bottom:2px solid #27ae60;margin:8px 0">
                📋 評分依據</div>''', unsafe_allow_html=True)
        for p2 in r["pos"][:3]:
            st.markdown(f'<div class="box-ok">✅ {p2}</div>',unsafe_allow_html=True)
        for n in r["neg"][:2]:
            st.markdown(f'<div class="box-danger">✗ {n}</div>',unsafe_allow_html=True)
        for w in r["warn"][:2]:
            st.markdown(f'<div class="box-warn">⚠ {w}</div>',unsafe_allow_html=True)
        if r["is_disposed"]:
            st.error("🚨 **處置股**：流動性極差，建議暫不操作，靜待出關。")
# ================================================================
def tab_home():
    st.markdown("""
    <div style="background:#1a2332;border-radius:14px;padding:16px 20px;margin-bottom:16px">
      <div style="font-size:22px;font-weight:700;color:#fff">📊 台股分析系統</div>
      <div style="font-size:12px;color:#8fa3b8;margin-top:4px">
        三大法人籌碼 × 技術面 × 目標價自動取得
      </div>
    </div>
    """, unsafe_allow_html=True)

    token = st.session_state.token
    results = st.session_state.results

    # Token 狀態提示
    if not token:
        st.error("⚠️ **尚未設定 FinMind Token！** 請點上方「⚙️ 設定」頁填入後再回來。")
    else:
        st.success(f"✅ Token 已設定｜上次更新：{st.session_state.last_run.strftime('%H:%M') if st.session_state.last_run else '尚未執行'}")

    # 分析按鈕
    sids = [s.strip() for s in
            st.session_state.get("stock_list", DEFAULT_LIST).split(",") if s.strip()]
    st.markdown(f"**追蹤清單：{len(sids)} 支股票**")

    if st.button("🔄 開始分析全部股票", disabled=not token):
        with st.spinner("取得處置股清單..."):
            st.session_state.disposed = fetch_disposed()

        all_results = []
        bar = st.progress(0, text="準備中...")
        for i, sid in enumerate(sids):
            name = STOCK_NAMES.get(sid, sid)
            bar.progress((i+1)/len(sids), text=f"分析 {name}（{i+1}/{len(sids)}）")
            r = analyze_one(sid, token, st.session_state.disposed)
            if r:
                all_results.append(r)
            time.sleep(0.3)
        bar.empty()

        st.session_state.results = sorted(all_results,
                                          key=lambda x: x["score"], reverse=True)
        st.session_state.last_run = datetime.now()
        st.success(f"✅ 分析完成！{len(all_results)} 支股票")
        st.rerun()

    if not results:
        st.info("👆 點「開始分析」按鈕取得最新數據")
        return

    # 評等統計
    from collections import Counter
    cnts = Counter(r["rating"] for r in results)
    c1,c2,c3,c4 = st.columns(4)
    for col,(rt,em) in zip([c1,c2,c3,c4],[("S","⭐"),("A","✅"),("B","👀"),("C","❌")]):
        col.metric(f"{em} {rt}", cnts.get(rt,0))

    st.markdown("---")

    # 篩選
    opt = st.selectbox("篩選顯示",
        ["全部","⭐ S 強烈推薦","✅ A 建議買入","👀 B 觀望","❌ C 避開","🚨 處置股"],
        label_visibility="collapsed")
    show = results
    if "S" in opt:   show=[r for r in results if r["rating"]=="S"]
    elif "A" in opt: show=[r for r in results if r["rating"]=="A"]
    elif "B" in opt: show=[r for r in results if r["rating"]=="B"]
    elif "C" in opt: show=[r for r in results if r["rating"]=="C"]
    elif "處置" in opt: show=[r for r in results if r["is_disposed"]]

    for r in show:
        stock_card(r)


# ================================================================
# 頁面：排行榜
# ================================================================
def tab_rank():
    st.markdown("### 🏆 評等排行")
    results = st.session_state.results
    if not results:
        st.info("請先在「🏠 首頁」執行分析")
        return

    df = pd.DataFrame([{
        "評等": f"{r['rating']}（{r['label']}）",
        "股票": f"{r['name']}（{r['sid']}）",
        "分數": r["score"],
        "現價(元)": r["price"],
        "漲跌%": f"{r['chg']:+.2f}%",
        "外資": f"{r['f_con']:+d}日",
        "投信": f"{r['t_con']:+d}日",
        "目標(元)": f"{r['tp']:,.0f}" if r["tp"] else "-",
    } for r in results])
    st.dataframe(df, use_container_width=True, hide_index=True)

    # 外資+投信同向買
    buy2 = [r for r in results if r["f_con"]>0 and r["t_con"]>0 and not r["is_disposed"]]
    if buy2:
        st.markdown("### ✅ 外資+投信同向買超")
        for r in sorted(buy2, key=lambda x:x["f_con"]+x["t_con"], reverse=True):
            chg=r["chg"] or 0
            cc="up" if chg>=0 else "dn"
            st.markdown(f"""
            <div class="st-card" style="border-left:4px solid #27ae60">
              <strong>{r['name']}（{r['sid']}）</strong>　
              <span class="{cc}">{r['price']:,.0f}元 {chg:+.1f}%</span>　
              外資<span class="up">+{r['f_con']}日</span>　
              投信<span class="up">+{r['t_con']}日</span>　
              評分<strong>{r['score']}</strong>
            </div>
            """, unsafe_allow_html=True)

    # 處置股
    disp = [r for r in results if r["is_disposed"]]
    if disp:
        st.markdown("### 🚨 處置股觀察")
        for r in disp:
            st.error(f"⏸ **{r['name']}（{r['sid']}）** {r['price']:,.0f}元 — 處置期，暫不操作")


# ================================================================
# 頁面：籌碼掃描
# ================================================================
def tab_scanner():
    st.markdown("### 📡 籌碼掃描")
    results = st.session_state.results
    if not results:
        st.info("請先在「🏠 首頁」執行分析")
        return

    disposed = st.session_state.disposed

    # 策略一：吸籌率 ≥ 5%
    st.markdown("#### 🔥 法人焦點熱門股（外資+投信同向，吸籌率≥5%）")
    hot = []
    for r in results:
        if r["is_disposed"]: continue
        inst = r["inst"]
        if not inst: continue
        ft=inst[-1]["f"]; tt=inst[-1]["t"]
        vol=r.get("vol",0) or 1
        if ft>0 and tt>0:
            ab=(ft+tt)/vol*100
            if ab>=5: hot.append({**r,"ft":ft,"tt":tt,"ab":round(ab,1)})
    hot.sort(key=lambda x:x["ab"], reverse=True)

    if hot:
        for r in hot[:10]:
            tier=("🔴極熱" if r["ab"]>=15 else "🟠熱門" if r["ab"]>=8 else "🟡升溫")
            chg=r["chg"] or 0
            st.markdown(f"""
            <div class="st-card" style="border-left:4px solid #27ae60">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <strong>{r['name']}（{r['sid']}）</strong>
                <span style="font-weight:700;color:#e67e22">{tier} {r['ab']}%</span>
              </div>
              <div style="margin-top:5px;font-size:13px">
                現價 <strong>{r['price']:,.0f}</strong>元
                &nbsp;<span class="{'up' if chg>=0 else 'dn'}">{chg:+.1f}%</span>
                &nbsp;外資<span class="up">+{r['ft']:,}張</span>
                &nbsp;投信<span class="up">+{r['tt']:,}張</span>
                &nbsp;評分<strong>{r['score']}</strong>
              </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("今日無外資+投信同向且吸籌率≥5%的個股")

    # 策略二：投信佈局
    st.markdown("#### 🕵️ 投信佈局觀察（5日內買超天數≥4）")
    trust = []
    for r in results:
        if r["is_disposed"]: continue
        inst=r["inst"]
        if len(inst)<4: continue
        buy_days=sum(1 for d in inst if d["t"]>0)
        if buy_days>=4:
            trust.append({**r,"buy_days":buy_days,"t_total":sum(d["t"] for d in inst)})
    trust.sort(key=lambda x:x["buy_days"], reverse=True)
    if trust:
        for r in trust:
            st.markdown(f"""
            <div class="st-card" style="border-left:4px solid #8e44ad">
              <strong>{r['name']}（{r['sid']}）</strong>
              <span style="float:right;color:#8e44ad;font-weight:700">{r['buy_days']}/5天買超</span><br>
              <span style="font-size:13px">現價{r['price']:,.0f}元
              &nbsp;累計投信+{r['t_total']:,}張</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("目前無符合條件的佈局股")


# ================================================================
# 頁面：設定
# ================================================================
def tab_settings():
    st.markdown("### ⚙️ 設定")

    # 從 Streamlit Secrets 讀取預設 Token
    default_token = ""
    try:
        default_token = st.secrets.get("FINMIND_TOKEN","")
    except Exception:
        pass

    with st.form("sf"):
        token = st.text_input(
            "FinMind Token",
            value=st.session_state.token or default_token,
            type="password",
            placeholder="貼上你的 FinMind Token...",
        )
        stock_list = st.text_area(
            "追蹤股票（股號以逗號分隔）",
            value=st.session_state.get("stock_list", DEFAULT_LIST),
            height=100,
        )
        saved = st.form_submit_button("💾 儲存", use_container_width=True)

    if saved:
        st.session_state.token      = token.strip()
        st.session_state.stock_list = stock_list.strip()
        st.success("✅ 設定儲存完成！請切換到「🏠 首頁」開始分析。")

    if st.session_state.token:
        st.success("✅ Token 已設定")
    else:
        st.warning("⚠ 尚未設定 Token")

    st.markdown("---")
    st.markdown("""
    **📌 取得 FinMind Token（免費）**
    1. 前往 [finmindtrade.com](https://finmindtrade.com)
    2. 免費註冊帳號
    3. 登入後在右上角「帳號」頁面複製 Token

    **📱 加入 iPhone 主畫面**
    1. Safari 開啟此 App 網址
    2. 點右下角分享圖示 📤
    3. 選「加入主畫面」→「新增」
    4. 完成！從主畫面直接開啟
    """)


# ================================================================
# 主程式 — 使用 st.tabs()
# ================================================================
def main():
    tab1, tab2, tab3, tab4 = st.tabs(["🏠 首頁", "🏆 排行", "📡 掃描", "⚙️ 設定"])
    with tab1: tab_home()
    with tab2: tab_rank()
    with tab3: tab_scanner()
    with tab4: tab_settings()

if __name__ == "__main__":
    main()
