"""
台股分析系統 — Streamlit App v3
修正：
  v3 Fix-1  移除 yfinance（Streamlit Cloud 超時），改用 FinMind PE 估算目標價
  v3 Fix-2  淺色背景 + 深色文字，完全用 Streamlit 原生元件避免 CSS 衝突
  v3 Fix-3  加入錯誤訊息，避免分析失敗無提示
"""

import time, warnings
from datetime import date, datetime, timedelta
from collections import defaultdict
import pandas as pd
import streamlit as st
import requests

warnings.filterwarnings("ignore")
try:
    import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception: pass

# ── 頁面設定 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="📊 台股分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS：淺色背景 + 深色文字，避免衝突 ───────────────────────
st.markdown("""
<style>
/* 全域背景白色 */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main { background: #f5f7fa !important; }

/* 隱藏 Streamlit 預設元素 */
[data-testid="stHeader"], #MainMenu, footer,
.stDeployButton { display:none !important; }

/* 最大寬度置中 */
.block-container {
  padding: 0.5rem 0.8rem 1rem !important;
  max-width: 700px; margin: 0 auto;
}

/* 所有文字強制深色 */
body, p, span, div, li, h1,h2,h3,h4,
[class*="stMarkdown"],
[data-testid="stMarkdownContainer"] > * {
  color: #1a1a2e !important;
}

/* Tabs 導覽列 */
.stTabs [data-baseweb="tab-list"] {
  background: #1a2332 !important;
  border-radius: 12px; padding: 5px; gap: 3px;
}
.stTabs [data-baseweb="tab"] {
  color: #8fa3b8 !important;
  font-size: 13px; font-weight: 600;
  border-radius: 8px; padding: 7px 2px;
}
.stTabs [aria-selected="true"] {
  background: #27ae60 !important;
  color: #ffffff !important;
}
.stTabs [data-baseweb="tab-panel"] {
  background: transparent !important;
  padding-top: 10px !important;
}

/* 主要按鈕 */
.stButton > button {
  background: #27ae60 !important; color: #fff !important;
  border: none !important; border-radius: 10px !important;
  font-size: 16px !important; font-weight: 700 !important;
  padding: 12px 0 !important; width: 100%;
  box-shadow: 0 2px 8px rgba(39,174,96,.3) !important;
}
.stButton > button:hover   { opacity: .88 !important; }
.stButton > button:disabled {
  background: #ccc !important;
  box-shadow: none !important;
}

/* selectbox 文字 */
[data-testid="stSelectbox"] label,
[data-testid="stSelectbox"] * { color: #1a1a2e !important; }

/* 成功/警告/錯誤框 */
[data-testid="stAlert"] { border-radius: 10px !important; }

/* expander */
[data-testid="stExpander"] {
  background: #fff !important;
  border: 1px solid #dde3ed !important;
  border-radius: 10px !important;
}
details summary {
  color: #1a2332 !important;
  font-weight: 600 !important;
  background: #f0f4ff !important;
  border-radius: 10px !important;
  padding: 10px 14px !important;
}
details[open] summary {
  border-radius: 10px 10px 0 0 !important;
}
details > div { padding: 10px 14px !important; }

/* dataframe */
[data-testid="stDataFrame"] * { color: #1a1a2e !important; }
</style>
""", unsafe_allow_html=True)

# ── Session State 初始化 ─────────────────────────────────────
for k,v in [("results",[]),("last_run",None),
            ("disposed",set()),("token",""),
            ("stock_list","2330,2454,6669,3661,3034,3017,3037,6515,5274,2376")]:
    if k not in st.session_state: st.session_state[k] = v

# 從 Streamlit Secrets 自動載入 Token（若已設定）
if not st.session_state.token:
    try:
        tok = st.secrets.get("FINMIND_TOKEN","")
        if tok: st.session_state.token = tok
    except Exception: pass

# ── 常數 ─────────────────────────────────────────────────────
API  = "https://api.finmindtrade.com/api/v4/data"
HDR  = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"}
NAMES = {
    "2330":"台積電","2454":"聯發科","6669":"緯穎","3661":"世芯-KY",
    "3034":"聯詠","3017":"奇鋐","3037":"欣興","6515":"穎威",
    "5274":"信驊","2313":"華通","3048":"益登","3231":"緯創",
    "2376":"技嘉","2317":"鴻海","2382":"廣達","2308":"台達電",
    "2603":"長榮","2609":"陽明","1513":"中興電","3293":"鈊象",
    "3529":"力旺","3665":"貿聯-KY","3167":"達亮","3081":"聯惠",
}
R_COLOR = {"S":"#1a5c38","A":"#27ae60","B":"#9b6a15","C":"#c0392b"}
R_BG    = {"S":"#d4edda","A":"#d4edda","B":"#fff3cd","C":"#f8d7da"}

# ── 工具 ─────────────────────────────────────────────────────
def fi(s,d=0):
    try: return int(str(s).replace(",","").strip())
    except: return d
def ff(s,d=0.0):
    try: return float(str(s).replace(",","").strip())
    except: return d
def ma(cls,n):
    return round(sum(cls[-n:])/n,2) if len(cls)>=n else None
def dev(p,m):
    return round((p-m)/m*100,2) if p and m and m>0 else None
def con(series):
    if not series: return 0
    last=series[-1]
    if last==0: return 0
    d=1 if last>0 else -1; c=0
    for v in reversed(series):
        if (v>0 and d==1) or (v<0 and d==-1): c+=1
        else: break
    return c*d
def name(sid): return NAMES.get(sid,sid)

# ── API ───────────────────────────────────────────────────────
def api(dataset, sid, start, token):
    try:
        r = requests.get(API, headers=HDR, timeout=15, verify=False,
            params={"dataset":dataset,"data_id":sid,
                    "start_date":start,"token":token})
        if r.status_code == 200:
            return r.json().get("data",[])
        else:
            return []
    except Exception:
        return []

# ── 資料抓取 ─────────────────────────────────────────────────
def get_price(sid, token):
    s=(date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows=api("TaiwanStockPrice",sid,s,token)
    recs=[]
    for r in rows:
        c=ff(r.get("close",0))
        if c>0: recs.append({
            "date": r.get("date","")[:10], "close":c,
            "high": ff(r.get("max",r.get("high",0))),
            "low":  ff(r.get("min",r.get("low",0))),
            "vol":  fi(r.get("Trading_Volume",0))//1000
        })
    recs.sort(key=lambda x:x["date"])
    return recs

def get_inst(sid, token):
    s=(date.today()-timedelta(days=35)).strftime("%Y-%m-%d")
    rows=api("TaiwanStockInstitutionalInvestorsBuySell",sid,s,token)
    dm=defaultdict(lambda:{"f":0,"t":0,"d":0})
    for r in rows:
        nm=str(r.get("name",""))
        net=fi(r.get("buy",0))-fi(r.get("sell",0))
        d=r.get("date","")[:10]
        if "Foreign" in nm or "外資" in nm: dm[d]["f"]+=net
        elif "Trust" in nm or "投信" in nm:  dm[d]["t"]+=net
        elif "Dealer" in nm or "自營" in nm: dm[d]["d"]+=net
    return [{"date":d,"f":dm[d]["f"]//1000,"t":dm[d]["t"]//1000,"d":dm[d]["d"]//1000}
            for d in sorted(dm.keys())[-5:]]

def get_per(sid, token):
    s=(date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows=api("TaiwanStockPER",sid,s,token)
    recs=[{"pe":ff(r.get("PER",0)),"pbr":ff(r.get("PBR",0))}
          for r in rows if ff(r.get("PER",0))>0]
    return recs[-250:] if recs else []

def get_rev(sid, token):
    """月營收，回傳近13筆"""
    s=(date.today()-timedelta(days=450)).strftime("%Y-%m-%d")
    rows=api("TaiwanStockMonthRevenue",sid,s,token)
    recs=[{"rev":ff(r.get("revenue",0)),
           "year":fi(r.get("revenue_year",0)),
           "month":fi(r.get("revenue_month",0))}
          for r in rows if ff(r.get("revenue",0))>0]
    recs.sort(key=lambda x:(x["year"],x["month"]))
    return recs[-13:]

def get_disposed():
    disposed=set()
    try:
        r=requests.get("https://openapi.twse.com.tw/v1/announcement/punish",
                       headers=HDR,timeout=8,verify=False)
        if r.status_code==200:
            for item in r.json():
                c=str(item.get("SecuritiesCode","")).strip()
                if c: disposed.add(c)
    except Exception: pass
    return disposed

# ── 分析引擎 ─────────────────────────────────────────────────
def analyze(sid, token, disposed):
    try:
        # 股價
        price_rows=get_price(sid,token)
        if not price_rows: return None,"無股價數據"
        closes=[r["close"] for r in price_rows]
        last=price_rows[-1]; prev=price_rows[-2] if len(price_rows)>=2 else last
        p=last["close"]
        chg=round((p-prev["close"])/prev["close"]*100,2) if prev["close"] else 0

        ma5=ma(closes,5); ma20=ma(closes,20)
        ma60=ma(closes,60); ma200=ma(closes,200)
        dev5=dev(p,ma5); dev200=dev(p,ma200)
        time.sleep(0.3)

        # 法人
        inst=get_inst(sid,token)
        f_con=con([d["f"] for d in inst])
        t_con=con([d["t"] for d in inst])
        d_con=con([d["d"] for d in inst])
        time.sleep(0.3)

        # PE / PBR
        per=get_per(sid,token)
        pe=per[-1]["pe"] if per else None
        pe_avg=round(sum(r["pe"] for r in per)/len(per),1) if per else None
        pbr=per[-1]["pbr"] if per else None
        time.sleep(0.3)

        # 月營收（用來算目標價）
        rev_rows=get_rev(sid,token)
        rev_yoy=None
        if len(rev_rows)>=13:
            latest=rev_rows[-1]["rev"]; prev12=rev_rows[-13]["rev"]
            if prev12>0: rev_yoy=round((latest-prev12)/prev12*100,1)

        # Fix-1：目標價用 FinMind PE 估算（不用 yfinance）
        tp=None; ts="未取得"
        if pe_avg and pe and rev_yoy is not None:
            # 目標 PE = 近一年均值
            # 成長因子 = 1 + YoY，限制在 0.7~1.8 倍
            yf=min(max(1+rev_yoy/100,0.7),1.8)
            # 目標價 = 現價 × (目標PE/當前PE) × 成長因子
            if pe>0:
                tp=round(p*(pe_avg/pe)*yf,0)
                ts="PE均值×成長估算"
        time.sleep(0.2)

        # 評分
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
        if f_con>0 and t_con>0:   sc+=5;pos.append("外資投信同向買超")
        elif f_con<0 and t_con<0: sc-=8;neg.append("外資投信同向賣超")
        if pe and pe_avg and pe_avg>0:
            pv=(pe-pe_avg)/pe_avg*100
            if   pv<-20:sc+=8; pos.append(f"PE低估 {pe:.1f}x")
            elif pv<0:  sc+=4
            elif pv>20: sc-=5; warn.append(f"PE偏高 {pe:.1f}x")
        sc=max(0,min(100,sc))
        if   sc>=80: r2,l="S","強烈推薦"
        elif sc>=65: r2,l="A","建議買入"
        elif sc>=45: r2,l="B","觀　望"
        else:        r2,l="C","避　開"

        r52=price_rows[-252:] if len(price_rows)>=252 else price_rows
        return {
            "sid":sid,"name":name(sid),
            "price":p,"prev":prev["close"],"chg":chg,
            "ma5":ma5,"ma20":ma20,"ma60":ma60,"ma200":ma200,
            "dev5":dev5,"dev200":dev200,
            "h52":round(max(r["high"] for r in r52),2),
            "l52":round(min(r["low"]  for r in r52),2),
            "vol":last["vol"],"last5":[r["close"] for r in price_rows[-5:]],
            "inst":inst,"f_con":f_con,"t_con":t_con,"d_con":d_con,
            "pe":pe,"pe_avg":pe_avg,"pbr":pbr,
            "rev_yoy":rev_yoy,
            "tp":tp,"ts":ts,
            "score":sc,"rating":r2,"label":l,
            "pos":pos,"neg":neg,"warn":warn,
            "is_disposed":sid in disposed,
            "date":last["date"],
        }, None
    except Exception as e:
        return None, str(e)

# ── 股票卡片 UI ──────────────────────────────────────────────
def stock_card(r):
    rc   = R_COLOR.get(r["rating"],"#9b6a15")
    rbg  = R_BG.get(r["rating"],"#fff3cd")
    chg  = r["chg"] or 0
    dev5 = r.get("dev5") or 0

    # 評等標籤
    emoji = {"S":"⭐","A":"✅","B":"👀","C":"❌"}.get(r["rating"],"")

    with st.container():
        # 標題列（深色背景）
        st.markdown(f"""
<div style="background:#1a2332;border-radius:12px 12px 0 0;
  padding:13px 16px;margin-top:10px">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <span style="font-size:18px;font-weight:700;color:#fff">{r['name']}</span>
      <span style="font-size:12px;color:#8fa3b8;margin-left:8px">{r['sid']}</span>
      <br>
      <span style="font-size:11px;color:#8fa3b8">{r.get('date','')}
        &nbsp;|&nbsp;評分 <span style="color:#27ae60;font-weight:700">{r['score']}</span>/100
      </span>
    </div>
    <div style="background:{rc};border-radius:50%;width:52px;height:52px;
      display:flex;flex-direction:column;align-items:center;justify-content:center;
      flex-shrink:0">
      <span style="font-size:18px;font-weight:800;color:#fff;line-height:1">{r['rating']}</span>
      <span style="font-size:8px;color:rgba(255,255,255,.8)">{r['label']}</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

        # 數字摘要列（白底）
        chg_color = "#27ae60" if chg>=0 else "#c0392b"
        d5_color  = "#e67e22" if abs(dev5)>5 else "#27ae60" if dev5<0 else "#1a1a2e"
        tp_str    = f"{r['tp']:,.0f}元" if r["tp"] else "估算中"
        st.markdown(f"""
<div style="background:#fff;border-left:4px solid {rc};
  display:grid;grid-template-columns:1fr 1fr 1fr 1fr;
  padding:10px 14px;gap:6px;border-radius:0 0 0 0;
  border:1px solid #e8ecf0;border-top:none">
  <div>
    <div style="font-size:10px;color:#666;margin-bottom:2px">收盤</div>
    <div style="font-size:16px;font-weight:700;color:{chg_color}">{r['price']:,.0f}</div>
  </div>
  <div>
    <div style="font-size:10px;color:#666;margin-bottom:2px">漲跌</div>
    <div style="font-size:16px;font-weight:700;color:{chg_color}">{chg:+.1f}%</div>
  </div>
  <div>
    <div style="font-size:10px;color:#666;margin-bottom:2px">5日乖離</div>
    <div style="font-size:16px;font-weight:700;color:{d5_color}">{dev5:+.1f}%</div>
  </div>
  <div>
    <div style="font-size:10px;color:#666;margin-bottom:2px">目標</div>
    <div style="font-size:14px;font-weight:700;color:#1a2332">{tp_str}</div>
  </div>
</div>
""", unsafe_allow_html=True)

        # 標籤列
        tags = ""
        if r["is_disposed"]: tags+="🚨處置股  "
        if r["t_con"]>=5:    tags+=f"📌投信連買{r['t_con']}日  "
        elif r["t_con"]>=1:  tags+="📌投信買超  "
        elif r["t_con"]<=-3: tags+=f"⚠️投信連賣{abs(r['t_con'])}日  "
        if r["f_con"]>=3:    tags+=f"💰外資連買{r['f_con']}日  "
        elif r["f_con"]<=-3: tags+=f"⚠️外資連賣{abs(r['f_con'])}日  "
        elif r["f_con"]<0:   tags+="⚠️外資賣超  "
        if r["rev_yoy"] and r["rev_yoy"]>20: tags+=f"📈營收YoY+{r['rev_yoy']:.0f}%  "
        if tags:
            st.markdown(
                f'<div style="background:#f0f7ff;border:1px solid #c8dff5;'
                f'border-top:none;padding:7px 14px;font-size:12px;'
                f'color:#1a3a5c;border-radius:0">{tags}</div>',
                unsafe_allow_html=True)

        # 展開詳細
        with st.expander("展開詳細分析 ▼"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**📐 技術面**")
                data = [
                    ("MA5",   r["ma5"],   "元"),
                    ("MA20",  r["ma20"],  "元"),
                    ("MA60",  r["ma60"],  "元"),
                    ("MA200", r["ma200"], "元"),
                    ("52W高", r.get("h52"), "元"),
                    ("52W低", r.get("l52"), "元"),
                ]
                for lbl,val,unit in data:
                    v = f"{val:,.1f}{unit}" if val else "N/A"
                    st.markdown(
                        f'<p style="color:#1a1a2e;font-size:13px;'
                        f'margin:3px 0;padding:3px 0;'
                        f'border-bottom:1px solid #eee">'
                        f'<span style="color:#555">{lbl}</span>'
                        f' &nbsp; <strong>{v}</strong></p>',
                        unsafe_allow_html=True)

            with col2:
                st.markdown("**💰 估值 & 目標**")
                up_str = ""
                if r["tp"] and r["price"]:
                    up=(r["tp"]-r["price"])/r["price"]*100
                    uc="#27ae60" if up>0 else "#c0392b"
                    up_str=f' <span style="color:{uc}">（{up:+.1f}%）</span>'
                val_data = [
                    ("PE",     f"{r['pe']:.1f}x"    if r["pe"]    else "N/A"),
                    ("年均PE", f"{r['pe_avg']:.1f}x" if r["pe_avg"] else "N/A"),
                    ("PBR",    f"{r['pbr']:.2f}x"   if r["pbr"]   else "N/A"),
                    ("目標價", f"{r['tp']:,.0f}元{up_str}" if r["tp"] else "N/A"),
                    ("來源",   r["ts"]),
                    ("營收YoY",f"{r['rev_yoy']:+.1f}%" if r["rev_yoy"] is not None else "N/A"),
                ]
                for lbl,val in val_data:
                    st.markdown(
                        f'<p style="color:#1a1a2e;font-size:13px;'
                        f'margin:3px 0;padding:3px 0;'
                        f'border-bottom:1px solid #eee">'
                        f'<span style="color:#555">{lbl}</span>'
                        f' &nbsp; <strong>{val}</strong></p>',
                        unsafe_allow_html=True)

            # 三大法人表格
            if r["inst"]:
                st.markdown("**💼 三大法人近5日（張）**")
                df = pd.DataFrame(r["inst"])
                df.columns = ["日期","外資","投信","自營商"]
                st.dataframe(df, use_container_width=True, hide_index=True)

            # 評分依據
            cols_ev = []
            for p2 in r["pos"][:3]: cols_ev.append(("✅",p2,"#e8f5e9","#1b5e20"))
            for n  in r["neg"][:2]: cols_ev.append(("✗", n, "#fce4ec","#7b1818"))
            for w  in r["warn"][:2]:cols_ev.append(("⚠",w, "#fff8e1","#6d4c00"))
            if cols_ev:
                st.markdown("**📋 評分依據**")
                for icon,txt,bg,tc in cols_ev:
                    st.markdown(
                        f'<div style="background:{bg};border-radius:6px;'
                        f'padding:6px 10px;margin:3px 0;'
                        f'color:{tc};font-size:12px">{icon} {txt}</div>',
                        unsafe_allow_html=True)

            if r["is_disposed"]:
                st.error("🚨 **處置股**：流動性極差，建議暫不操作，靜待出關。")

        # 底部空間
        st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)

# ================================================================
# 🏠 首頁
# ================================================================
def tab_home():
    st.markdown("""
<div style="background:linear-gradient(135deg,#1a2332,#2c3e50);
  border-radius:14px;padding:18px 20px;margin-bottom:14px">
  <div style="font-size:22px;font-weight:800;color:#fff">📊 台股分析系統</div>
  <div style="font-size:12px;color:#8fa3b8;margin-top:4px">
    三大法人籌碼 × 技術面 × 月營收 × 目標價估算
  </div>
</div>""", unsafe_allow_html=True)

    token  = st.session_state.token
    sids   = [s.strip() for s in
              st.session_state.stock_list.split(",") if s.strip()]
    results= st.session_state.results

    # 狀態列
    if token:
        lr = st.session_state.last_run
        lr_str = lr.strftime("%m/%d %H:%M") if lr else "尚未執行"
        st.success(f"✅ Token 已設定 | 上次分析：{lr_str} | 追蹤 {len(sids)} 支")
    else:
        st.error("⚠️ 尚未設定 Token！請先到「⚙️ 設定」頁填入 FinMind Token。")

    # 分析按鈕
    run = st.button("🔄 開始分析全部股票",
                    disabled=not token,
                    use_container_width=True)

    if run:
        errors = []
        with st.spinner("取得處置股清單..."):
            st.session_state.disposed = get_disposed()

        all_results = []
        bar = st.progress(0, text="準備中...")
        status_ph = st.empty()

        for i, sid in enumerate(sids):
            nm = name(sid)
            bar.progress((i+1)/len(sids),
                         text=f"分析 {nm}（{sid}）... {i+1}/{len(sids)}")
            status_ph.info(f"⏳ 正在抓取 **{nm}** 的數據...")
            r, err = analyze(sid, token, st.session_state.disposed)
            if r:
                all_results.append(r)
            else:
                errors.append(f"{sid} {nm}：{err}")
            time.sleep(0.2)

        bar.empty()
        status_ph.empty()

        if all_results:
            st.session_state.results = sorted(
                all_results, key=lambda x: x["score"], reverse=True)
            st.session_state.last_run = datetime.now()
            st.success(f"✅ 完成！成功分析 {len(all_results)} 支股票")
        else:
            st.error("❌ 所有股票分析失敗！請確認 Token 是否正確，或稍後再試。")

        if errors:
            with st.expander(f"⚠️ {len(errors)} 支失敗（點擊查看）"):
                for e in errors: st.write(e)

        st.rerun()

    # 結果顯示
    if not results:
        st.info("👆 點上方「開始分析全部股票」按鈕取得最新數據")
        return

    # 評等統計
    from collections import Counter
    cnts = Counter(r["rating"] for r in results)
    c1,c2,c3,c4 = st.columns(4)
    for col,(rt,em,bg) in zip([c1,c2,c3,c4],[
        ("S","⭐","#d4edda"),("A","✅","#d4edda"),
        ("B","👀","#fff3cd"),("C","❌","#f8d7da")
    ]):
        n=cnts.get(rt,0)
        col.markdown(
            f'<div style="background:{bg};border-radius:10px;'
            f'padding:10px;text-align:center">'
            f'<div style="font-size:20px">{em}</div>'
            f'<div style="font-size:22px;font-weight:800;'
            f'color:{R_COLOR[rt]}">{n}</div>'
            f'<div style="font-size:11px;color:#555">{rt}</div></div>',
            unsafe_allow_html=True)

    st.markdown("---")

    # 篩選
    opt = st.selectbox("篩選",
        ["全部","⭐ S 強烈推薦","✅ A 建議買入",
         "👀 B 觀望","❌ C 避開","🚨 處置股"],
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
# 🏆 排行
# ================================================================
def tab_rank():
    st.markdown("### 🏆 今日評等排行")
    results = st.session_state.results
    if not results:
        st.info("請先在「🏠 首頁」執行分析")
        return

    df = pd.DataFrame([{
        "評等": r["rating"],
        "股票": f"{r['name']}({r['sid']})",
        "分數": r["score"],
        "現價": r["price"],
        "漲跌%": f"{r['chg']:+.2f}%",
        "外資": f"{r['f_con']:+d}日",
        "投信": f"{r['t_con']:+d}日",
        "目標": f"{r['tp']:,.0f}" if r["tp"] else "-",
    } for r in results])
    st.dataframe(df, use_container_width=True, hide_index=True)

    buy2=[r for r in results if r["f_con"]>0 and r["t_con"]>0 and not r["is_disposed"]]
    if buy2:
        st.markdown("### ✅ 外資+投信同向買超")
        for r in sorted(buy2,key=lambda x:x["f_con"]+x["t_con"],reverse=True):
            chg=r["chg"] or 0
            cc="#27ae60" if chg>=0 else "#c0392b"
            st.markdown(
                f'<div style="background:#fff;border-left:4px solid #27ae60;'
                f'border-radius:8px;padding:10px 14px;margin:5px 0;'
                f'border:1px solid #c3e6cb">'
                f'<strong style="color:#1a2332">{r["name"]}（{r["sid"]}）</strong> &nbsp; '
                f'<span style="color:{cc}">{r["price"]:,.0f}元 {chg:+.1f}%</span> &nbsp; '
                f'外資<span style="color:#27ae60;font-weight:700">+{r["f_con"]}日</span> '
                f'投信<span style="color:#27ae60;font-weight:700">+{r["t_con"]}日</span> '
                f'評分<strong style="color:#1a2332">{r["score"]}</strong>'
                f'</div>', unsafe_allow_html=True)

    disp=[r for r in results if r["is_disposed"]]
    if disp:
        st.markdown("### 🚨 處置股")
        for r in disp:
            st.error(f"⏸ **{r['name']}（{r['sid']}）** {r['price']:,.0f}元 — 暫不操作")

# ================================================================
# 📡 掃描
# ================================================================
def tab_scanner():
    st.markdown("### 📡 籌碼掃描")
    results = st.session_state.results
    if not results:
        st.info("請先在「🏠 首頁」執行分析")
        return

    # 策略一：吸籌率
    st.markdown("#### 🔥 法人焦點熱門股（外資+投信同向，吸籌率≥5%）")
    hot=[]
    for r in results:
        if r["is_disposed"] or not r["inst"]: continue
        ft=r["inst"][-1]["f"]; tt=r["inst"][-1]["t"]
        vol=r.get("vol",0) or 1
        if ft>0 and tt>0 and (ft+tt)/vol*100>=5:
            hot.append({**r,"ab":round((ft+tt)/vol*100,1),"ft":ft,"tt":tt})
    hot.sort(key=lambda x:x["ab"],reverse=True)
    if hot:
        for r in hot[:10]:
            tier="🔴極熱" if r["ab"]>=15 else "🟠熱門" if r["ab"]>=8 else "🟡升溫"
            chg=r["chg"] or 0; cc="#27ae60" if chg>=0 else "#c0392b"
            st.markdown(
                f'<div style="background:#fff;border-left:4px solid #27ae60;'
                f'border-radius:8px;padding:10px 14px;margin:5px 0;'
                f'border:1px solid #c3e6cb">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<strong style="color:#1a2332">{r["name"]}（{r["sid"]}）</strong>'
                f'<span style="font-weight:700;color:#e67e22">{tier} {r["ab"]}%</span></div>'
                f'<span style="font-size:13px;color:#1a1a2e">'
                f'{r["price"]:,.0f}元 <span style="color:{cc}">{chg:+.1f}%</span> &nbsp; '
                f'外資<span style="color:#27ae60">+{r["ft"]:,}張</span> '
                f'投信<span style="color:#27ae60">+{r["tt"]:,}張</span>'
                f'</span></div>', unsafe_allow_html=True)
    else:
        st.info("今日無外資+投信同向且吸籌率≥5%的個股")

    # 策略二：投信佈局
    st.markdown("#### 🕵️ 投信佈局（5日買超天數≥4天）")
    trust=[]
    for r in results:
        if r["is_disposed"] or len(r["inst"])<4: continue
        bd=sum(1 for d in r["inst"] if d["t"]>0)
        if bd>=4: trust.append({**r,"bd":bd,"tt":sum(d["t"] for d in r["inst"])})
    trust.sort(key=lambda x:x["bd"],reverse=True)
    if trust:
        for r in trust:
            st.markdown(
                f'<div style="background:#fff;border-left:4px solid #8e44ad;'
                f'border-radius:8px;padding:10px 14px;margin:5px 0;'
                f'border:1px solid #d7bde2">'
                f'<strong style="color:#1a2332">{r["name"]}（{r["sid"]}）</strong>'
                f'<span style="float:right;color:#8e44ad;font-weight:700">'
                f'{r["bd"]}/5天買超</span><br>'
                f'<span style="font-size:13px;color:#1a1a2e">'
                f'現價{r["price"]:,.0f}元 &nbsp; 5日累計<span style="color:#27ae60">'
                f'+{r["tt"]:,}張</span></span></div>',
                unsafe_allow_html=True)
    else:
        st.info("目前追蹤清單中無符合條件的佈局股")

# ================================================================
# ⚙️ 設定
# ================================================================
def tab_settings():
    st.markdown("### ⚙️ 設定")

    with st.form("sf", clear_on_submit=False):
        st.markdown("**🔑 FinMind Token**")
        token = st.text_input(
            "Token",
            value=st.session_state.token,
            type="password",
            placeholder="貼上你的 FinMind Token...",
            label_visibility="collapsed",
        )
        st.markdown("**📋 追蹤股票（股號以逗號分隔，建議最多15支）**")
        stock_list = st.text_area(
            "stocks",
            value=st.session_state.stock_list,
            height=90,
            label_visibility="collapsed",
        )
        saved = st.form_submit_button("💾 儲存設定", use_container_width=True)

    if saved:
        st.session_state.token      = token.strip()
        st.session_state.stock_list = stock_list.strip()
        st.success("✅ 儲存完成！請切換到「🏠 首頁」開始分析。")

    st.markdown("---")

    st.markdown("""
**📌 如何取得 FinMind Token（免費）**
1. 開啟 [finmindtrade.com](https://finmindtrade.com)
2. 點右上角「免費註冊」
3. 登入後在帳號頁面複製 Token（很長一串）

**📱 加入 iPhone 主畫面（像 App 一樣）**
1. 用 Safari 開啟本頁
2. 點最下方中間的「分享」圖示 📤
3. 往下找「加入主畫面」→ 點「新增」
4. 完成！主畫面出現圖示，直接點開使用
    """)

    if st.session_state.token:
        st.success(f"✅ Token 已設定（前10碼：{st.session_state.token[:10]}...）")
    else:
        st.warning("⚠️ 尚未設定 Token")

# ================================================================
# 主程式
# ================================================================
def main():
    tab1,tab2,tab3,tab4 = st.tabs(["🏠 首頁","🏆 排行","📡 掃描","⚙️ 設定"])
    with tab1: tab_home()
    with tab2: tab_rank()
    with tab3: tab_scanner()
    with tab4: tab_settings()

if __name__ == "__main__":
    main()
