"""
台股分析系統 — Streamlit App v5（全面重寫）
=============================================
改進清單：
  v5.1  淺色主題 + 深色文字，文字不再消失
  v5.2  籌碼掃描為第一頁，App開啟即自動呈現
  v5.3  全市場掃描：TWSE + TPEx（免Token，單次API呼叫）
  v5.4  @st.cache_data 快取所有API（防止重複爬蟲）
  v5.5  /tmp JSON 持久快取個股分析結果
  v5.6  個股分析若已有快取，直接載入不重爬
"""

import os, json, time, warnings
from datetime import date, datetime, timedelta
from collections import defaultdict

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

warnings.filterwarnings("ignore")
try:
    import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception: pass

# ── 頁面設定（最優先）────────────────────────────────────────
st.set_page_config(
    page_title="📊 台股分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 最小 CSS（只隱藏 Streamlit 預設元素）────────────────────
st.markdown("""
<style>
[data-testid="stHeader"], #MainMenu, footer { display:none!important; }
.block-container { padding:.5rem .8rem 1rem!important; max-width:780px; margin:0 auto; }
.stTabs [data-baseweb="tab-list"] {
    background:#1a2332!important; border-radius:12px; padding:5px; gap:3px;
}
.stTabs [data-baseweb="tab"] {
    color:#9db5cc!important; font-size:13px; font-weight:600;
    border-radius:8px; padding:8px 2px;
}
.stTabs [aria-selected="true"] {
    background:#27ae60!important; color:#fff!important;
}
/* 所有文字確保深色 */
p, span, label, div, li, td, th { color: #1a1a2e; }
.stMarkdown p, .stText { color: #1a1a2e !important; }
</style>
""", unsafe_allow_html=True)

# ── 常數 ─────────────────────────────────────────────────────
API       = "https://api.finmindtrade.com/api/v4/data"
HDR       = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"}
CACHE_DIR = "/tmp/tw_stock_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

NAMES = {
    # 上市 TWSE
    "2330":"台積電","2317":"鴻海","2454":"聯發科","2308":"台達電",
    "2382":"廣達","2303":"聯電","2327":"國巨","2357":"華碩",
    "2379":"瑞昱","2376":"技嘉","2313":"華通","2368":"金像電",
    "2603":"長榮","2609":"陽明","2615":"萬海","3711":"日月光投控",
    "2412":"中華電","2886":"兆豐金","2881":"富邦金","2882":"國泰金",
    "2884":"玉山金","2891":"中信金","1301":"台塑","1303":"南亞",
    "2002":"中鋼","2408":"南亞科","2474":"可成","2385":"群光",
    "3661":"世芯-KY","6669":"緯穎","2353":"宏碁","2356":"英業達",
    "3034":"聯詠","3037":"欣興","3231":"緯創","1513":"中興電",
    "2059":"川湖","2881":"富邦金",
    # 上櫃 TPEx
    "6515":"穎威","5274":"信驊","3017":"奇鋐","3048":"益登",
    "3529":"力旺","3665":"貿聯-KY","3167":"達亮","6510":"精測",
    "3443":"創意","3035":"智原","4966":"譜瑞-KY","6239":"力成",
    "6488":"環球晶","6533":"晶心科","3293":"鈊象","3081":"聯惠",
    "8299":"群聯","5347":"世界先進","3533":"嘉澤","4958":"臻鼎-KY",
    "5269":"祥碩","6271":"同欣電","4919":"新唐","6526":"達發",
}

RC  = {"S":"#1a5c38","A":"#27ae60","B":"#854F0B","C":"#A32D2D"}
RL  = {"S":"#D0F0DC","A":"#D0F0DC","B":"#FAE0A8","C":"#F7C1C1"}
RS  = {"S":"#A8E6BB","A":"#A8E6BB","B":"#F5C842","C":"#F09595"}
VBG = {"S":"#f0f9f4","A":"#f0f9f4","B":"#fef9ec","C":"#fdf2f2"}
VBC = {"S":"#27ae60","A":"#27ae60","B":"#f39c12","C":"#e74c3c"}
VTC = {"S":"#145a2c","A":"#145a2c","B":"#5a3e00","C":"#7b1818"}

def nm(s): return NAMES.get(s, s)

# ── Session State ─────────────────────────────────────────────
for k, v in [("token",""), ("stock_list","2330,2454,6669,3661,3034,3017,3037,6515,5274,2376"),
             ("results",[]), ("last_run",None), ("disposed",set())]:
    if k not in st.session_state: st.session_state[k] = v

if not st.session_state.token:
    try:
        t = st.secrets.get("FINMIND_TOKEN", "")
        if t: st.session_state.token = t
    except Exception: pass

# ─────────────────────────────────────────────────────────────
# 工具函式
# ─────────────────────────────────────────────────────────────
def fi(s, d=0):
    try:    return int(str(s).replace(",","").replace(" ","").strip())
    except: return d

def ff(s, d=0.0):
    try:    return float(str(s).replace(",","").replace(" ","").strip())
    except: return d

def parse_tw(s):
    """TWSE 數字格式（含千分位逗號）→ int，負數用負號或空 → 0"""
    if not s or str(s).strip() in ("--", "", "－"):
        return 0
    s = str(s).replace(",","").replace(" ","").strip()
    try:    return int(s)
    except: return 0

def ma_n(cls, n):
    return round(sum(cls[-n:])/n, 2) if len(cls) >= n else None

def dev_pct(p, m):
    return round((p-m)/m*100, 2) if p and m and m > 0 else None

def con_days(series):
    if not series: return 0
    last = series[-1]
    if last == 0: return 0
    d = 1 if last > 0 else -1; c = 0
    for v in reversed(series):
        if (v>0 and d==1) or (v<0 and d==-1): c+=1
        else: break
    return c*d

# ─────────────────────────────────────────────────────────────
# 持久快取（/tmp JSON）
# ─────────────────────────────────────────────────────────────
def cache_path(sid): return os.path.join(CACHE_DIR, f"{sid}.json")

def save_cache(sid, data):
    try:
        with open(cache_path(sid), "w", encoding="utf-8") as f:
            json.dump({"ts": datetime.now().isoformat(), "data": data},
                      f, ensure_ascii=False)
    except Exception: pass

def load_cache(sid, max_hours=4):
    p = cache_path(sid)
    if not os.path.exists(p): return None
    try:
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        if datetime.now() - datetime.fromisoformat(obj["ts"]) < timedelta(hours=max_hours):
            return obj["data"]
    except Exception: pass
    return None

def save_results_cache(results):
    """儲存整批分析結果快取"""
    try:
        with open(os.path.join(CACHE_DIR, "batch_results.json"), "w", encoding="utf-8") as f:
            json.dump({"ts": datetime.now().isoformat(), "results": results},
                      f, ensure_ascii=False)
    except Exception: pass

def load_results_cache(max_hours=4):
    """載入整批快取結果"""
    p = os.path.join(CACHE_DIR, "batch_results.json")
    if not os.path.exists(p): return None
    try:
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        if datetime.now() - datetime.fromisoformat(obj["ts"]) < timedelta(hours=max_hours):
            return obj["results"]
    except Exception: pass
    return None

# ─────────────────────────────────────────────────────────────
# 全市場數據（免 Token，4小時快取）
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=14400, show_spinner=False)
def fetch_twse_prices_all():
    """TWSE 全市場今日股價與成交量。"""
    out = {}
    try:
        r = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            headers=HDR, timeout=20, verify=False)
        if r.status_code == 200:
            for item in r.json():
                sid = str(item.get("Code","")).strip()
                if not sid or not sid.isdigit(): continue
                p   = ff(str(item.get("ClosingPrice","0")).replace(",",""))
                v   = fi(str(item.get("TradeVolume","0")).replace(",",""))
                chg_s = str(item.get("Change","")).replace("+","").replace(",","")
                chg = ff(chg_s)
                prev = p - chg if p else None
                cp   = round(chg/prev*100, 2) if prev and prev > 0 else 0.0
                if p > 0 and v > 0:
                    out[sid] = {"price":p, "volume":v, "chg_pct":cp,
                                "name":str(item.get("Name","")).strip()}
    except Exception: pass
    return out

@st.cache_data(ttl=14400, show_spinner=False)
def fetch_twse_institution_all():
    """TWSE 全市場今日三大法人（T86，以張為單位）。"""
    out = {}
    today = date.today().strftime("%Y%m%d")
    for url in [
        f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={today}&selectType=ALL",
        f"https://www.twse.com.tw/fund/T86?response=json&date={today}&selectType=ALL",
    ]:
        try:
            r = requests.get(url, headers=HDR, timeout=20, verify=False)
            d = r.json()
            rows = d.get("data", d.get("Data", []))
            if not rows: continue
            for row in rows:
                if len(row) < 11: continue
                sid = str(row[0]).strip()
                if not sid.isdigit(): continue
                # col[7]=外陸資淨買(不含自營) col[10]=投信淨買 col[14]=自營淨買(自行)
                f_net = parse_tw(row[7])  // 1000
                t_net = parse_tw(row[10]) // 1000
                d_net = parse_tw(row[14]) // 1000 if len(row) > 14 else 0
                name  = str(row[1]).strip() if len(row) > 1 else ""
                out[sid] = {"f":f_net, "t":t_net, "d":d_net, "name":name}
            if out: break   # 成功就不重試
        except Exception: continue
    return out

@st.cache_data(ttl=14400, show_spinner=False)
def fetch_tpex_prices_all():
    """TPEx 全市場今日股價與成交量。"""
    out = {}
    try:
        r = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            headers=HDR, timeout=20, verify=False)
        if r.status_code == 200:
            for item in r.json():
                sid = str(item.get("SecuritiesCompanyCode","")).strip()
                if not sid or not sid.isdigit(): continue
                p = ff(str(item.get("Close","0")).replace(",",""))
                v = fi(str(item.get("TradingShares","0")).replace(",","")) // 1000
                chg = ff(str(item.get("Change","0")).replace(",",""))
                prev = p - chg if p else None
                cp   = round(chg/prev*100,2) if prev and prev > 0 else 0.0
                if p > 0:
                    out[sid] = {"price":p, "volume":v, "chg_pct":cp,
                                "name":str(item.get("CompanyName","")).strip()}
    except Exception: pass
    return out

@st.cache_data(ttl=14400, show_spinner=False)
def fetch_tpex_institution_all():
    """TPEx 全市場今日三大法人（以張為單位）。"""
    out = {}
    today = date.today().strftime("%Y/%m/%d")
    try:
        url = f"https://www.tpex.org.tw/web/fund/tripleFund/index.php?l=zh-tw&o=json&d={today}"
        r   = requests.get(url, headers=HDR, timeout=20, verify=False)
        d   = r.json()
        rows = d.get("aaData", d.get("data", []))
        for row in rows:
            if len(row) < 19: continue
            sid = str(row[0]).strip()
            if not sid.isdigit(): continue
            # TPEx格式：col[3]=外資淨  col[6]=投信淨  col[18]=自營淨
            f_net = parse_tw(row[3])  // 1000
            t_net = parse_tw(row[6])  // 1000
            d_net = parse_tw(row[18]) // 1000 if len(row) > 18 else 0
            out[sid] = {"f":f_net, "t":t_net, "d":d_net, "name":str(row[1]).strip()}
    except Exception: pass
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_disposed_cached():
    """處置股（TWSE+TPEx），1小時快取。"""
    disposed = set()
    for url in [
        "https://openapi.twse.com.tw/v1/announcement/punish",
        "https://www.tpex.org.tw/openapi/v1/tpex_announcement_punish",
    ]:
        try:
            r = requests.get(url, headers=HDR, timeout=8, verify=False)
            if r.status_code == 200:
                for item in r.json():
                    c = str(item.get("SecuritiesCode", item.get("code",""))).strip()
                    if c: disposed.add(c)
        except Exception: pass
    return disposed

# ─────────────────────────────────────────────────────────────
# 個股 API（需 Token，使用 st.cache_data 快取）
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _api(dataset, sid, start, token):
    try:
        r = requests.get(API, headers=HDR, timeout=15, verify=False,
            params={"dataset":dataset,"data_id":sid,"start_date":start,"token":token})
        if r.status_code == 200: return r.json().get("data", [])
    except Exception: pass
    return []

def get_price(sid, token):
    s = (date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows = _api("TaiwanStockPrice", sid, s, token)
    recs = [{"date":r.get("date","")[:10],
             "close":ff(r.get("close",0)),
             "high":ff(r.get("max",r.get("high",0))),
             "low":ff(r.get("min",r.get("low",0))),
             "vol":fi(r.get("Trading_Volume",0))//1000}
            for r in rows if ff(r.get("close",0)) > 0]
    recs.sort(key=lambda x: x["date"])
    return recs

def get_inst(sid, token):
    s = (date.today()-timedelta(days=35)).strftime("%Y-%m-%d")
    rows = _api("TaiwanStockInstitutionalInvestorsBuySell", sid, s, token)
    dm = defaultdict(lambda:{"f":0,"t":0,"d":0})
    for r in rows:
        n2  = str(r.get("name",""))
        net = fi(r.get("buy",0)) - fi(r.get("sell",0))
        d   = r.get("date","")[:10]
        if "Foreign" in n2 or "外資" in n2: dm[d]["f"] += net
        elif "Trust" in n2 or "投信" in n2: dm[d]["t"] += net
        elif "Dealer" in n2 or "自營" in n2:dm[d]["d"] += net
    return [{"date":d,"f":dm[d]["f"]//1000,"t":dm[d]["t"]//1000,"d":dm[d]["d"]//1000}
            for d in sorted(dm.keys())[-5:]]

def get_per(sid, token):
    s = (date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows = _api("TaiwanStockPER", sid, s, token)
    return [{"pe":ff(r.get("PER",0)),"pbr":ff(r.get("PBR",0))}
            for r in rows if ff(r.get("PER",0)) > 0][-250:]

def get_rev(sid, token):
    s = (date.today()-timedelta(days=450)).strftime("%Y-%m-%d")
    rows = _api("TaiwanStockMonthRevenue", sid, s, token)
    recs = [{"rev":ff(r.get("revenue",0)),
             "yr":fi(r.get("revenue_year",0)),
             "mo":fi(r.get("revenue_month",0))}
            for r in rows if ff(r.get("revenue",0)) > 0]
    recs.sort(key=lambda x:(x["yr"],x["mo"]))
    return recs[-13:]

# ── Yahoo Finance 分析師目標價（選用）─────────────────────────
def get_yahoo_target(sid):
    """Yahoo Finance 分析師共識目標價，自動試 .TW / .TWO。"""
    try:
        import yfinance as yf
        import pandas as _pd
    except ImportError:
        return None
    for suffix in [".TW", ".TWO"]:
        try:
            info = yf.Ticker(f"{sid}{suffix}").info or {}
            if not info.get("regularMarketPrice"): continue
            mean = info.get("targetMeanPrice")
            if mean and not _pd.isna(mean) and float(mean) > 0:
                count = info.get("numberOfAnalystOpinions")
                return {
                    "target": round(float(mean), 2),
                    "high":   round(float(info["targetHighPrice"]),2) if info.get("targetHighPrice") else None,
                    "low":    round(float(info["targetLowPrice"]), 2) if info.get("targetLowPrice")  else None,
                    "count":  int(count) if count else 0,
                    "source": f"Yahoo共識（{int(count or 0)}位分析師）",
                }
        except Exception: continue
    return None

# ─────────────────────────────────────────────────────────────
# 分析引擎（含持久快取）
# ─────────────────────────────────────────────────────────────
def analyze(sid, token, disposed, force=False):
    """分析單支股票，優先讀取快取。"""
    # 嘗試讀取快取
    if not force:
        cached = load_cache(sid)
        if cached:
            return cached, None

    try:
        pr = get_price(sid, token)
        if not pr: return None, "無股價數據"
        cls  = [r["close"] for r in pr]
        last = pr[-1]; prev = pr[-2] if len(pr) >= 2 else last
        p    = last["close"]
        chg  = round((p-prev["close"])/prev["close"]*100, 2) if prev["close"] else 0

        ma5 = ma_n(cls,5);  ma20=ma_n(cls,20)
        ma60= ma_n(cls,60); ma200=ma_n(cls,200)
        d5  = dev_pct(p,ma5); d200=dev_pct(p,ma200)
        time.sleep(0.3)

        inst = get_inst(sid, token)
        fc   = con_days([d["f"] for d in inst])
        tc   = con_days([d["t"] for d in inst])
        dc   = con_days([d["d"] for d in inst])
        time.sleep(0.3)

        per = get_per(sid, token)
        pe  = per[-1]["pe"]  if per else None
        pea = round(sum(r["pe"] for r in per)/len(per),1) if per else None
        pbr = per[-1]["pbr"] if per else None
        time.sleep(0.3)

        rev     = get_rev(sid, token)
        rev_yoy = None
        if len(rev) >= 13 and rev[-13]["rev"] > 0:
            rev_yoy = round((rev[-1]["rev"]-rev[-13]["rev"])/rev[-13]["rev"]*100,1)
        rev_mom = None
        if len(rev) >= 2 and rev[-2]["rev"] > 0:
            rev_mom = round((rev[-1]["rev"]-rev[-2]["rev"])/rev[-2]["rev"]*100,1)

        # 目標價：Yahoo 優先，PE公式備用
        tp=None; ts="未取得"; tp_h=None; tp_l=None; tp_n=0
        ya = get_yahoo_target(sid)
        if ya:
            tp=ya["target"]; tp_h=ya["high"]; tp_l=ya["low"]
            tp_n=ya["count"]; ts=ya["source"]
        elif pea and pe and rev_yoy is not None and pe > 0:
            tp  = round(p*(pea/pe)*min(max(1+rev_yoy/100,0.7),1.8), 0)
            ts  = "PE均值×成長估算"

        # 評分
        sc=50; pos=[]; neg=[]; warn=[]
        if d5 is not None:
            if   d5<-5:  sc+=18;pos.append(f"5日線回測{d5:+.1f}%")
            elif d5<=2:  sc+=10;pos.append(f"5日乖離健康{d5:+.1f}%")
            elif d5<=8:  sc+=2; warn.append(f"5日乖離偏高{d5:+.1f}%")
            else:        sc-=10;neg.append(f"5日乖離過高{d5:+.1f}%")
        if d200 and d200>50: sc-=8; warn.append(f"年線乖離偏高{d200:+.1f}%")
        if tp and p:
            up=(tp-p)/p*100
            if   up>20:  sc+=15;pos.append(f"距目標+{up:.1f}%空間")
            elif up>10:  sc+=8; pos.append(f"距目標+{up:.1f}%")
            elif up>0:   sc+=3
            elif up>-10: sc-=5; warn.append(f"現價略超目標{up:.1f}%")
            else:        sc-=12;neg.append(f"現價超目標{up:.1f}%")
        if rev_yoy is not None:
            if   rev_yoy>=20:sc+=8; pos.append(f"月營收YoY+{rev_yoy:.1f}%（高成長）")
            elif rev_yoy>=5: sc+=4; pos.append(f"月營收YoY+{rev_yoy:.1f}%")
            elif rev_yoy<0:  sc-=5; neg.append(f"月營收年減{rev_yoy:.1f}%")
        if   fc>=3:  sc+=12;pos.append(f"外資連買{fc}日")
        elif fc>=1:  sc+=5; pos.append("外資今日買超")
        elif fc<=-3: sc-=10;neg.append(f"外資連賣{abs(fc)}日")
        elif fc<0:   sc-=4; warn.append("外資今日賣超")
        if   tc>=5:  sc+=12;pos.append(f"投信連買{tc}日")
        elif tc>=3:  sc+=8; pos.append(f"投信連買{tc}日")
        elif tc>=1:  sc+=3; pos.append("投信今日買超")
        elif tc<=-3: sc-=10;neg.append(f"投信連賣{abs(tc)}日")
        elif tc<0:   sc-=4; warn.append("投信今日賣超")
        if fc>0 and tc>0:   sc+=5; pos.append("外資投信同向買超")
        elif fc<0 and tc<0: sc-=8; neg.append("外資投信同向賣超")
        if pe and pea and pea>0:
            pv=(pe-pea)/pea*100
            if pv<-20:  sc+=8; pos.append(f"PE{pe:.1f}x 低估")
            elif pv<0:  sc+=4
            elif pv>20: sc-=5; warn.append(f"PE{pe:.1f}x 偏高")
        sc = max(0, min(100, sc))
        if   sc>=80: rt,lb="S","強烈推薦"
        elif sc>=65: rt,lb="A","建議買入"
        elif sc>=45: rt,lb="B","觀　望"
        else:        rt,lb="C","避　開"

        r52 = pr[-252:] if len(pr)>=252 else pr
        result = {
            "sid":sid,"name":nm(sid),"price":p,"prev":prev["close"],"chg":chg,
            "ma5":ma5,"ma20":ma20,"ma60":ma60,"ma200":ma200,
            "d5":d5,"d200":d200,
            "h52":round(max(r["high"] for r in r52),2),
            "l52":round(min(r["low"]  for r in r52),2),
            "vol":last["vol"],"last5":[r["close"] for r in pr[-5:]],
            "inst":inst,"fc":fc,"tc":tc,"dc":dc,
            "pe":pe,"pea":pea,"pbr":pbr,"rev_yoy":rev_yoy,"rev_mom":rev_mom,
            "tp":tp,"ts":ts,"tp_h":tp_h,"tp_l":tp_l,"tp_n":tp_n,
            "score":sc,"rating":rt,"label":lb,
            "pos":pos,"neg":neg,"warn":warn,
            "is_disposed":sid in disposed,
            "date":last["date"],
        }
        save_cache(sid, result)   # 存入持久快取
        return result, None
    except Exception as e:
        return None, str(e)

# ─────────────────────────────────────────────────────────────
# 籌碼掃描（全市場，免Token）
# ─────────────────────────────────────────────────────────────
def run_scanner():
    """
    全市場三策略籌碼掃描。
    回傳 (hot_list, trust_list, launch_list, inst_date)
    """
    with st.spinner("📡 取得全市場數據（TWSE + TPEx）..."):
        twse_p = fetch_twse_prices_all()
        twse_i = fetch_twse_institution_all()
        tpex_p = fetch_tpex_prices_all()
        tpex_i = fetch_tpex_institution_all()
        disposed = fetch_disposed_cached()

    # 合併
    prices = {**twse_p, **tpex_p}
    insts  = {**twse_i, **tpex_i}

    inst_date = date.today().strftime("%Y/%m/%d")
    hot = []; trust = []; launch = []

    for sid, inst in insts.items():
        if sid in disposed: continue
        f = inst.get("f",0); t = inst.get("t",0)
        pdata = prices.get(sid)
        if not pdata: continue
        vol   = pdata.get("volume",0) or 1
        price = pdata.get("price",0)
        iname = pdata.get("name","") or inst.get("name", nm(sid))
        chg   = pdata.get("chg_pct",0) or 0

        # ── 策略一：外資+投信同向，吸籌率≥5% ─────────────────
        if f > 0 and t > 0:
            ab = (f+t)/vol*100
            if ab >= 5:
                tier = "🔴極熱" if ab>=15 else "🟠熱門" if ab>=8 else "🟡升溫"
                hot.append({"sid":sid,"name":iname,"f":f,"t":t,"d":inst.get("d",0),
                            "vol":vol,"ab":round(ab,1),"tier":tier,
                            "price":price,"chg":chg})

        # ── 策略三（發動）：今日投信突破≥500張 ──────────────
        if t >= 500 and f >= -50:
            val_yi = round(t*1000*price/1e8, 2) if price else 0
            if val_yi >= 0.3:
                launch.append({"sid":sid,"name":iname,"t":t,"f":f,
                               "val_yi":val_yi,"price":price,"chg":chg})

    # 策略二：需要歷史數據（使用已分析的結果或略過）
    # 從已快取的個股結果中找投信連買的
    results = st.session_state.results
    for r in results:
        if r["is_disposed"]: continue
        inst_hist = r.get("inst",[])
        buy_days  = sum(1 for d in inst_hist if d["t"]>0)
        if buy_days >= 4 and (r.get("chg",0) or 0) < 7:
            trust.append({
                "sid": r["sid"],"name": r["name"],
                "buy_days":buy_days,
                "t_total":sum(d["t"] for d in inst_hist),
                "price":r["price"],"chg":r.get("chg",0),
            })

    hot.sort(key=lambda x: x["ab"], reverse=True)
    launch.sort(key=lambda x: (x["t"],x["val_yi"]), reverse=True)
    trust.sort(key=lambda x: x["buy_days"], reverse=True)

    return hot[:20], trust[:15], launch[:10], inst_date, len(prices), len(insts)

# ─────────────────────────────────────────────────────────────
# wiwynn HTML 卡片生成器
# ─────────────────────────────────────────────────────────────
WCSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f4f6f8;font-family:'Helvetica Neue',Arial,sans-serif;padding:12px 8px;color:#2c3e50}
.wrap{max-width:660px;margin:0 auto}
.hdr{background:#1a2332;border-radius:14px 14px 0 0;padding:18px 20px}
.hdr h1{font-size:19px;color:#fff;font-weight:600}
.hdr-sub{font-size:11px;color:#8fa3b8;margin-top:3px}
.rc{width:64px;height:64px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0}
.rc .lt{font-size:22px;font-weight:600;line-height:1}
.rc .lb{font-size:8px;margin-top:2px;letter-spacing:.05em}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}
.tag{font-size:10px;padding:2px 8px;border-radius:99px;font-weight:500}
.tag-g{background:#27ae6033;color:#27ae60;border:1px solid #27ae6055}
.tag-r{background:#e74c3c33;color:#e74c3c;border:1px solid #e74c3c55}
.tag-a{background:#f39c1233;color:#e67e22;border:1px solid #f39c1255}
.tag-p{background:#8e44ad33;color:#8e44ad;border:1px solid #8e44ad55}
.sbar{background:#fff;border-left:4px solid #27ae60;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:2px;display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:8px}
.sc p:first-child{font-size:10px;color:#777;text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px}
.sc p:last-child{font-size:17px;font-weight:700}
.up{color:#27ae60}.dn{color:#c0392b}.wn{color:#e67e22}
.card{background:#fff;border-radius:10px;padding:14px 16px;margin-bottom:9px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.ct{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:#666;margin-bottom:9px}
.row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f0f0f0;font-size:13px;gap:8px}
.row:last-child{border-bottom:none}
.rl{color:#777;flex-shrink:0}.rv{font-weight:500;text-align:right}
.rbar{height:10px;border-radius:5px;background:linear-gradient(90deg,#27ae60 0%,#f39c12 55%,#e74c3c 82%);position:relative;margin:10px 0 3px}
.rn{position:absolute;top:-3px;width:3px;height:16px;background:#1a2332;border-radius:2px}
.rsc{display:flex;justify-content:space-between;font-size:10px;color:#999}
.rfg{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:8px}
.rf{background:#f8f9fa;border-radius:6px;padding:6px 8px;border:1px solid #eee}
.rf p:first-child{font-size:10px;color:#777;margin-bottom:1px}
.rf p:last-child{font-size:12px;font-weight:500}
.cg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:8px 0}
.chip{border-radius:7px;padding:8px;text-align:center;border:1px solid}
.chip.buy{background:#eaf3de;border-color:#97c459}
.chip.sell{background:#fceaea;border-color:#f09595}
.chip.neut{background:#f8f9fa;border-color:#ddd}
.chip p:first-child{font-size:10px;color:#777;margin-bottom:1px}
.chip p:nth-child(2){font-size:14px;font-weight:600;margin-bottom:1px}
.chip p:last-child{font-size:10px;color:#777}
.ev{display:flex;gap:8px;padding:7px 0;border-bottom:1px solid #f0f0f0;font-size:12px}
.ev:last-child{border-bottom:none}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:3px}
.ev strong{display:block;font-size:12px;margin-bottom:1px;color:#1a2332}
.ev span{color:#555;line-height:1.5}
.sg{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}
.sb{background:#eaf3de;border-radius:7px;padding:8px 10px;font-size:11px;color:#27500A;border:1px solid #97c459;line-height:1.6}
.sr{background:#fceaea;border-radius:7px;padding:8px 10px;font-size:11px;color:#791F1F;border:1px solid #f09595;line-height:1.6}
.st{display:flex;gap:8px;padding:6px 0;border-bottom:1px solid #f0f0f0;font-size:12px;align-items:flex-start;line-height:1.6}
.st:last-child{border-bottom:none}
.si{font-size:14px;flex-shrink:0}
.box-w{background:#fef9ec;border-left:4px solid #f39c12;border-radius:0 6px 6px 0;padding:8px 11px;font-size:12px;color:#7d4e00;margin-top:8px;line-height:1.6}
.box-d{background:#fdf2f2;border-left:4px solid #e74c3c;border-radius:0 6px 6px 0;padding:8px 11px;font-size:12px;color:#7b1818;margin-top:7px;line-height:1.6}
.box-o{background:#f0f9f4;border-left:4px solid #27ae60;border-radius:0 6px 6px 0;padding:8px 11px;font-size:12px;color:#145a2c;margin-top:7px;line-height:1.6}
.verdict{border-radius:9px;padding:11px 14px;border:1px solid}
.vb{font-size:24px;font-weight:700}
.tp-wrap{background:#f0f0f0;border-radius:5px;height:11px;position:relative;margin:6px 0 3px;overflow:hidden}
.tp-fill{height:11px;border-radius:5px}
.tp-lbl{display:flex;justify-content:space-between;font-size:10px;color:#888}
.inst-tbl{width:100%;border-collapse:collapse;font-size:11px;margin-top:7px}
.inst-tbl th{background:#f4f6f8;color:#555;padding:4px 6px;font-weight:600;border-bottom:1px solid #ddd;text-align:right}
.inst-tbl th:first-child{text-align:left}
.inst-tbl td{padding:4px 6px;border-bottom:1px solid #f0f0f0;text-align:right}
.inst-tbl td:first-child{text-align:left;color:#555}
.footer{background:#f8f9fa;border-radius:0 0 11px 11px;padding:10px 14px;font-size:10px;color:#999;line-height:1.6;border-top:1px solid #eee}
"""

def _fv(v, u="", dig=2):
    if v is None: return "N/A"
    return f"{v:,.{dig}f}{u}"

def _cc(v): return "up" if v>=0 else "dn"

def build_wiwynn(r):
    """生成完整 wiwynn 格式 HTML。"""
    sid=r["sid"]; p=r["price"]; chg=r.get("chg",0) or 0
    d5=r.get("d5") or 0; d200=r.get("d200") or 0
    sc=r["score"]; rt=r["rating"]; lb=r["label"]
    fc=r["fc"]; tc=r["tc"]; dc=r["dc"]
    ma5=r["ma5"]; ma20=r["ma20"]
    inst=r.get("inst",[])
    tp=r.get("tp"); ts_=r.get("ts",""); tp_h=r.get("tp_h"); tp_l=r.get("tp_l"); tp_n=r.get("tp_n",0)
    pe=r.get("pe"); pea=r.get("pea"); pbr=r.get("pbr")
    rev_yoy=r.get("rev_yoy"); rev_mom=r.get("rev_mom")

    rc2=RC[rt]; lc=RL[rt]; sc2=RS[rt]
    vbg=VBG[rt]; vbc=VBC[rt]; vtc=VTC[rt]
    bclr="#27ae60" if sc>=65 else ("#f39c12" if sc>=45 else "#e74c3c")
    cc=_cc(chg)

    # 標籤
    tags=""
    if r["is_disposed"]: tags+='<span class="tag tag-r">🚨 處置股</span>'
    if tc>=5:   tags+=f'<span class="tag tag-g">投信連買{tc}日⭐</span>'
    elif tc>=1: tags+=f'<span class="tag tag-g">投信買超</span>'
    elif tc<=-3:tags+=f'<span class="tag tag-r">投信連賣{abs(tc)}日</span>'
    if fc>=3:   tags+=f'<span class="tag tag-g">外資連買{fc}日</span>'
    elif fc<=-3:tags+=f'<span class="tag tag-r">外資連賣{abs(fc)}日</span>'
    elif fc<0:  tags+='<span class="tag tag-a">⚠ 外資賣超</span>'
    if d5>8:    tags+=f'<span class="tag tag-r">乖離{d5:+.1f}%</span>'
    elif d5<-5: tags+=f'<span class="tag tag-g">回測{d5:+.1f}%</span>'
    if tp and p:
        up2=(tp-p)/p*100
        if up2>10: tags+=f'<span class="tag tag-p">目標+{up2:.0f}%</span>'
    if rev_yoy and rev_yoy>20: tags+=f'<span class="tag tag-g">YoY+{rev_yoy:.0f}%</span>'

    disposed_html=""
    if r["is_disposed"]:
        disposed_html="""<div style="background:#fff8e1;border:1px solid #ffc107;border-radius:8px;
padding:10px 13px;margin-bottom:9px;font-size:12px;color:#7d4e00">
⏱️ <strong>處置股警告：</strong>流動性極差，策略建議暫不操作，靜待出關後重新評估。</div>"""

    # 籌碼格
    def chip_html(label, net, con_d):
        cls="buy" if net>0 else ("sell" if net<0 else "neut")
        vc="up" if net>0 else ("dn" if net<0 else "")
        sign="+" if net>=0 else ""
        ct=(f"連買{con_d}日" if con_d>=2 else "今日買超" if con_d==1
            else "今日中性" if con_d==0
            else "今日賣超" if con_d==-1 else f"連賣{abs(con_d)}日")
        return (f'<div class="chip {cls}"><p>{label}</p>'
                f'<p class="{vc}">{sign}{net:,} 張</p><p>{ct}</p></div>')

    ft=inst[-1]["f"] if inst else 0
    tt=inst[-1]["t"] if inst else 0
    dt=inst[-1]["d"] if inst else 0
    tot=ft+tt+dt

    # 法人5日明細
    inst_rows=""
    for d2 in inst:
        ds=d2["date"][-5:].replace("-","/")
        fv2=d2["f"]; tv=d2["t"]; dv=d2["d"]; to2=fv2+tv+dv
        inst_rows+=f"""<tr>
<td>{ds}</td><td class="{_cc(fv2)}">{fv2:+,}</td>
<td class="{_cc(tv)}">{tv:+,}</td><td class="{_cc(dv)}">{dv:+,}</td>
<td class="{_cc(to2)}"><strong>{to2:+,}</strong></td></tr>"""

    # 近5日乖離趨勢
    last5=r.get("last5",[p])
    trend=""
    for i,c2 in enumerate(last5):
        d5v=round((c2-ma5)/ma5*100,1) if ma5 and ma5>0 else 0
        w=min(abs(d5v)*5,100)
        lbl2=f"T-{len(last5)-1-i}" if i<len(last5)-1 else "今日"
        fc2="trend-bar-fill-g"; vc2="#27ae60"
        if d5v<0: fc2="trend-bar-fill-r"; vc2="#c0392b"
        trend+=(f'<div style="display:flex;align-items:center;gap:5px;font-size:11px;margin-bottom:3px">'
                f'<span style="color:#aaa;width:28px">{lbl2}</span>'
                f'<div style="flex:1;background:#eee;border-radius:3px;height:5px;overflow:hidden">'
                f'<div style="height:5px;border-radius:3px;background:{vc2};width:{w}%"></div></div>'
                f'<span style="color:{vc2};width:55px;text-align:right">{d5v:+.1f}%</span></div>')

    # 目標價卡片
    tp_card=""
    if tp and p:
        up2=(tp-p)/p*100; exceed=up2<0
        bw=min(p/tp*100,100) if tp>0 else 50
        fill_c=("linear-gradient(90deg,#27ae60,#e74c3c)" if exceed
                else "linear-gradient(90deg,#27ae60,#2ecc71)")
        count_badge=(f'<span style="background:#edf4ff;color:#2980b9;border:1px solid #aec6ea;'
                     f'font-size:10px;padding:1px 7px;border-radius:99px;margin-left:5px">👥{tp_n}位</span>'
                     if tp_n>0 else "")
        range_bar=""
        if tp_h and tp_l and tp_h>tp_l:
            rng=tp_h-tp_l
            cp3=min(max((p-tp_l)/rng*100,0),100)
            mp3=min(max((tp-tp_l)/rng*100,0),100)
            range_bar=f"""
<div style="margin-top:10px">
<p style="font-size:10px;font-weight:600;color:#666;margin-bottom:5px">分析師目標區間</p>
<div style="position:relative;background:#f0f0f0;border-radius:5px;height:12px;margin-bottom:3px">
  <div style="position:absolute;left:{mp3:.0f}%;top:-3px;width:3px;height:18px;background:#2980b9;border-radius:2px;z-index:2"></div>
  <div style="position:absolute;left:{cp3:.0f}%;top:-3px;width:3px;height:18px;background:#1a2332;border-radius:2px;z-index:3"></div>
</div>
<div style="display:flex;justify-content:space-between;font-size:10px;color:#888">
  <span>低 {tp_l:,.0f}</span>
  <span style="color:#2980b9;font-weight:600">均 {tp:,.0f}</span>
  <span>高 {tp_h:,.0f}</span>
</div></div>"""
        upbox=(f'<div class="box-d" style="margin-top:7px">✗ 現價超越目標{abs(up2):.1f}%，安全邊際低。</div>'
               if exceed else
               f'<div class="box-o" style="margin-top:7px">✅ 距目標+{up2:.1f}%，具合理風險報酬比。</div>')
        tp_card=f"""
<div class="card">
  <p class="ct">💰 目標價分析{count_badge}</p>
  <div class="row"><span class="rl">來源</span><span class="rv" style="font-size:11px;color:#555">{ts_}</span></div>
  <div class="row"><span class="rl">分析師均值</span><span class="rv {'dn' if exceed else 'up'}" style="font-size:15px;font-weight:700">{tp:,.0f} 元</span></div>
  {"<div class='row'><span class='rl'>最高目標</span><span class='rv'>"+f"{tp_h:,.0f}元</span></div>" if tp_h else ""}
  {"<div class='row'><span class='rl'>最低目標</span><span class='rv'>"+f"{tp_l:,.0f}元</span></div>" if tp_l else ""}
  <div class="row"><span class="rl">vs 現價</span><span class="rv {'dn' if exceed else 'up'}"><strong>{up2:+.1f}%</strong></span></div>
  {range_bar}
  <div class="tp-wrap"><div class="tp-fill" style="width:{bw:.1f}%;background:{fill_c}"></div></div>
  <div class="tp-lbl"><span>0</span><span>現價{p:,.0f}</span><span>{tp:,.0f}</span></div>
  {upbox}
</div>"""

    # 估值
    mom_c=f"<div class='rf'><p>月營收MoM</p><p class='{_cc(rev_mom or 0)}'>{(rev_mom or 0):+.1f}%</p></div>" if rev_mom is not None else ""
    yoy_c=f"<div class='rf'><p>月營收YoY</p><p class='{_cc(rev_yoy or 0)}'>{(rev_yoy or 0):+.1f}%</p></div>" if rev_yoy is not None else ""
    pe_c = f"<div class='rf'><p>PE</p><p>{pe:.1f}x</p></div>" if pe else ""
    pea_c= f"<div class='rf'><p>年均PE</p><p>{pea:.1f}x</p></div>" if pea else ""
    pbr_c= f"<div class='rf'><p>PBR</p><p>{pbr:.2f}x</p></div>" if pbr else ""
    val_card=f"""
<div class="card">
  <p class="ct">📊 估值指標</p>
  <div class="rfg">{pe_c}{pea_c}{pbr_c}{mom_c}{yoy_c}</div>
</div>""" if any([pe,pea,pbr,rev_mom is not None,rev_yoy is not None]) else ""

    # 事件
    evs=[]
    if fc>=3 and tc>=3: evs.append(("#27ae60",f"外資+投信雙向認養（{fc}/{tc}日）","法人籌碼同向最強訊號，中線看多確立。"))
    elif fc>=2: evs.append(("#27ae60",f"外資連買{fc}日","外資持續進場，籌碼支撐明確。"))
    elif fc<=-3:evs.append(("#e74c3c",f"外資連賣{abs(fc)}日","外資持續調節，短線籌碼承壓。"))
    if tc>=5:   evs.append(("#27ae60",f"投信深度認養（連買{tc}日）","機構長期建倉，中線信心強。"))
    elif tc<=-3:evs.append(("#e74c3c",f"投信連賣{abs(tc)}日","機構謹慎，持續追蹤。"))
    if d5<-5:   evs.append(("#27ae60","回測5日線，良好進場點",f"5日乖離{d5:+.1f}%，技術面偏多。"))
    elif d5>10: evs.append(("#e74c3c","5日線乖離過高，追高風險大",f"乖離+{d5:.1f}%，建議等回測再進場。"))
    if rev_yoy and rev_yoy>20: evs.append(("#27ae60",f"月營收YoY+{rev_yoy:.1f}%，基本面強勁","年增率超20%，業績持續加速。"))
    if r["is_disposed"]: evs.append(("#e74c3c","⚠ 處置股警告","流動性極差，建議暫不操作。"))
    if not evs: evs.append(("#8fa3b8","目前無特殊事件","維持當前追蹤策略。"))
    ev_html="".join(f'<div class="ev"><div class="dot" style="background:{c}"></div><div><strong>{t}</strong><span>{d3}</span></div></div>' for c,t,d3 in evs[:4])

    # 策略
    stop=round(min(r.get("last5",[p]))*0.97,2)
    if d5<-3:   ea=f"{p:,.0f}元（現位回測進場）"
    elif d5<=3: ea=f"{(ma5 or p)*0.97:,.0f}元（回測5日線）"
    else:       ea=f"{(ma5 or p)*0.95:,.0f}元（等回測5日線）"
    tgt=(f"{tp:,.0f}元（{ts_}）" if tp else f"{p*1.10:,.0f}元（+10%估算）")

    # 風險
    risks=""
    if r["is_disposed"]: risks+='<div class="box-d">🚨 處置股：流動性極差，建議暫不操作。</div>'
    for n in r["neg"][:3]: risks+=f'<div class="box-d">✗ {n}</div>'
    for w in r["warn"][:2]:risks+=f'<div class="box-w">⚠ {w}</div>'
    if not risks: risks='<div class="box-o">✅ 目前無重大風險警示。</div>'

    today=date.today().strftime("%Y/%m/%d")
    chg_sign="+" if chg>=0 else ""
    return f"""<!DOCTYPE html><html lang="zh-TW"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{r['name']} {sid}</title><style>{WCSS}</style></head>
<body><div class="wrap">
<div class="hdr">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <h1>{r['name']} <span style="font-size:13px;font-weight:400;color:#8fa3b8">{sid}</span></h1>
      <p class="hdr-sub">{r.get('date',today)} | 收盤{p:,.2f}元 | 評分{sc}/100</p>
      <div class="tags">{tags}</div>
    </div>
    <div class="rc" style="background:{rc2}">
      <span class="lt" style="color:{lc}">{rt}</span>
      <span class="lb" style="color:{sc2}">{lb}</span>
    </div>
  </div>
</div>
<div class="sbar" style="border-left-color:{rc2}">
  <div class="sc"><p>昨收</p><p>{r.get('prev',0):,.2f}元</p></div>
  <div class="sc"><p>今收</p><p class="{cc}">{p:,.2f}元</p></div>
  <div class="sc"><p>漲跌</p><p class="{cc}">{chg_sign}{chg:.2f}%</p></div>
  <div class="sc"><p>MA5</p><p>{_fv(ma5,'元',0)}</p></div>
</div>
{disposed_html}
<div class="card">
  <p class="ct">📊 綜合決策評等（{sc}/100）</p>
  <div class="verdict" style="background:{vbg};border-color:{vbc}">
    <span class="vb" style="color:{vbc}">{rt}</span>
    <span style="font-size:14px;font-weight:600;color:{vbc};margin-left:8px">{lb}</span>
    <p style="margin-top:7px;font-size:12px;color:{vtc};line-height:1.7">
      {"<span class='up'>正：</span>"+"、".join(r["pos"][:2])+"<br>" if r["pos"] else ""}
      {"<span class='dn'>負：</span>"+"、".join(r["neg"][:2]) if r["neg"] else ""}
    </p>
  </div>
  <div class="box-w" style="margin-top:9px">
    ⚠ 升評條件：外資轉買連2日+5日乖離收斂至+3%以內<br>
    ⬇ 降評條件：外資連賣3日以上，或跌破月線（{_fv(ma20,'元',0)}）
  </div>
</div>
<div class="card">
  <p class="ct">🔍 技術面</p>
  <div style="display:flex;align-items:center;gap:15px;flex-wrap:wrap;margin-bottom:10px">
    <div><p style="font-size:34px;font-weight:700;color:{bclr};line-height:1">{sc}</p>
      <p style="font-size:11px;color:{bclr}">{"🟢低度" if sc>=65 else "🟡中度" if sc>=45 else "🔴高度"}風險</p></div>
    <div style="flex:1;min-width:160px">
      <div class="row"><span class="rl">5日線乖離</span><span class="rv {'up' if d5<=3 else 'dn'}"><strong>{d5:+.2f}%</strong></span></div>
      <div class="row"><span class="rl">月線乖離</span><span class="rv">{f"{dev_pct(p,ma20):+.2f}%" if ma20 else "N/A"}</span></div>
      <div class="row"><span class="rl">52W高/低</span><span class="rv">{_fv(r.get('h52'),'',0)}/{_fv(r.get('l52'),'',0)}</span></div>
      <div class="row"><span class="rl">成交量</span><span class="rv">{r.get('vol',0):,}張</span></div>
    </div>
  </div>
  <div style="background:#f8f9fa;border-radius:7px;padding:9px;border:1px solid #eee;margin-bottom:9px">
    <p style="font-size:10px;font-weight:600;color:#666;margin-bottom:7px">5日線乖離趨勢</p>
    {trend}
  </div>
  <div class="rbar"><div class="rn" style="left:{min(sc,99)}%"></div></div>
  <div class="rsc"><span>0安全</span><span>50中性</span><span>80極危</span><span>100</span></div>
  <div class="rfg">
    <div class="rf"><p>MA20</p><p>{_fv(ma20,'元',0)}</p></div>
    <div class="rf"><p>MA60</p><p>{_fv(r.get('ma60'),'元',0)}</p></div>
    <div class="rf"><p>MA200</p><p>{_fv(r.get('ma200'),'元',0)}</p></div>
    <div class="rf"><p>年線乖離</p><p class="{'dn' if (d200 or 0)>80 else ''}">{f"{d200:+.2f}%" if d200 else "N/A"}</p></div>
  </div>
</div>
<div class="card">
  <p class="ct">💼 籌碼面</p>
  <div class="cg">
    {chip_html("外資",ft,fc)}
    {chip_html("投信",tt,tc)}
    {chip_html("自營商",dt,dc)}
  </div>
  {"<div class='box-o'>✅ 外資投信同向買超</div>" if fc>0 and tc>0 else ""}
  {"<div class='box-d'>✗ 外資投信同向賣超</div>" if fc<0 and tc<0 else ""}
  {"<div class='box-w'>⚠ 外資投信方向分歧</div>" if (fc>0 and tc<0) or (fc<0 and tc>0) else ""}
  <table class="inst-tbl">
    <tr><th>日期</th><th>外資</th><th>投信</th><th>自營</th><th>合計</th></tr>
    {inst_rows}
  </table>
</div>
{tp_card}
{val_card}
<div class="card"><p class="ct">📅 事件更新</p>{ev_html}</div>
<div class="card">
  <p class="ct">🎯 操作策略</p>
  <div class="st"><span class="si">🟢</span><div><strong>積極進場：</strong>{ea}</div></div>
  <div class="st"><span class="si">🟡</span><div><strong>保守進場：</strong>{_fv(ma20,'元',0)}（月線支撐）</div></div>
  <div class="st"><span class="si">🔴</span><div><strong>短線停損：</strong>{stop:,.0f}元（近5日低-3%）</div></div>
  <div class="st"><span class="si">🎯</span><div><strong>目標：</strong>{tgt}</div></div>
  <div class="sg">
    <div class="sb"><strong>📈 多頭</strong><br>法人持續買超+技術面強勢</div>
    <div class="sr"><strong>📉 空頭</strong><br>外資連賣+跌破月線</div>
  </div>
</div>
<div class="card"><p class="ct">⚠️ 風險提示</p>{risks}</div>
<div class="footer">{r['name']}（{sid}）| {r.get('date',today)} | 評分{sc}/100 | {ts_}<br>
數據：FinMind API | 僅供參考，不構成投資建議</div>
</div></body></html>"""

def build_full_html(results):
    """多股票完整報告"""
    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    nav="".join(
        f'<a href="#s{r["sid"]}" style="display:inline-block;font-size:11px;padding:3px 9px;border-radius:14px;font-weight:600;text-decoration:none;margin:2px;background:{RC[r["rating"]]};color:white">'
        f'{r["name"]}</a>'
        for r in sorted(results,key=lambda x:x["score"],reverse=True))
    cards=""
    for r in sorted(results,key=lambda x:(x["is_disposed"],-x["score"])):
        inner=build_wiwynn(r)
        s=inner.find("<body>")+6; e=inner.find("</body>")
        cards+=f'<div id="s{r["sid"]}" style="scroll-margin-top:55px">{inner[s:e]}</div>'
    today=date.today().strftime("%Y/%m/%d %H:%M")
    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股分析 {today}</title><style>{WCSS}</style></head><body>
<div class="wrap">
<div style="background:#1a2332;border-radius:10px;padding:9px 13px;margin-bottom:10px;position:sticky;top:0;z-index:99">
  <div style="font-size:10px;color:#8fa3b8;margin-bottom:4px">📊 台股分析 {today} | S:{cnts['S']} A:{cnts['A']} B:{cnts['B']} C:{cnts['C']}</div>
  {nav}
</div>
{cards}
</div></body></html>"""

# ─────────────────────────────────────────────────────────────
# 頁面
# ─────────────────────────────────────────────────────────────
def tab_scanner():
    st.markdown("### 📡 籌碼掃描 — 全市場（上市 + 上櫃）")

    # 資訊列
    c1,c2,c3 = st.columns(3)
    c1.info("🆓 免費無需 Token，自動抓取")
    c2.info("⏱ 快取 4 小時，不重複爬蟲")
    c3.info("🔄 點按鈕可強制更新")

    if st.button("🔄 重新整理籌碼數據", use_container_width=True):
        fetch_twse_prices_all.clear()
        fetch_twse_institution_all.clear()
        fetch_tpex_prices_all.clear()
        fetch_tpex_institution_all.clear()
        st.rerun()

    hot, trust, launch, inst_date, n_price, n_inst = run_scanner()

    st.caption(f"資料日期：{inst_date} | 股價涵蓋：{n_price} 檔 | 法人數據：{n_inst} 檔")

    # ── 策略一：吸籌率 ────────────────────────────────────────
    n_hot=len(hot); n15=sum(1 for r in hot if r["ab"]>=15)
    n8 =sum(1 for r in hot if 8<=r["ab"]<15)
    nw =sum(1 for r in hot if r["ab"]<8)
    st.markdown(f"""
<div style="background:#fff;border-radius:10px;padding:13px 16px;margin-bottom:4px;border-left:4px solid #27ae60;box-shadow:0 1px 3px rgba(0,0,0,.07)">
  <div style="font-size:14px;font-weight:700;color:#1a2332;margin-bottom:6px">
    🔥 策略一：法人焦點熱門股
    <span style="background:#fdf2f2;color:#c0392b;border:1px solid #f09595;font-size:10px;padding:1px 7px;border-radius:99px;margin-left:5px">{n_hot} 檔</span>
  </div>
  <div style="font-size:12px;color:#555">外資+投信同向買超，吸籌率≥5% | 🔴極熱(≥15%): {n15}　🟠熱門(≥8%): {n8}　🟡升溫(≥5%): {nw}</div>
</div>""", unsafe_allow_html=True)

    if hot:
        df_hot = pd.DataFrame([{
            "熱度": r["tier"],
            "代號": r["sid"],
            "名稱": r["name"][:8],
            "收盤": r["price"],
            "漲跌%": f"{r['chg']:+.1f}%",
            "外資(張)": f"+{r['f']:,}",
            "投信(張)": f"+{r['t']:,}",
            "吸籌率": f"{r['ab']:.1f}%",
            "成交量": f"{r['vol']:,}",
        } for r in hot])
        st.dataframe(df_hot, use_container_width=True, hide_index=True, height=min(35*len(hot)+38,450))
    else:
        st.info("今日無外資+投信同向且吸籌率≥5%的個股（可能是假日或法人數據未更新）")

    st.markdown("---")

    # ── 策略三：主力首日發動 ──────────────────────────────────
    st.markdown(f"""
<div style="background:#fff;border-radius:10px;padding:13px 16px;margin-bottom:4px;border-left:4px solid #2980b9;box-shadow:0 1px 3px rgba(0,0,0,.07)">
  <div style="font-size:14px;font-weight:700;color:#1a2332;margin-bottom:4px">
    ⚡ 策略三：主力首日發動
    <span style="background:#edf4ff;color:#2980b9;border:1px solid #aec6ea;font-size:10px;padding:1px 7px;border-radius:99px;margin-left:5px">{len(launch)} 檔</span>
  </div>
  <div style="font-size:12px;color:#555">今日投信突買≥500張，買超金額≥0.3億</div>
</div>""", unsafe_allow_html=True)
    if launch:
        df_la = pd.DataFrame([{
            "代號": r["sid"],"名稱": r["name"][:8],
            "收盤": r["price"],"漲跌%": f"{r['chg']:+.1f}%",
            "今日投信(張)": f"+{r['t']:,}",
            "買超金額": f"{r['val_yi']:.2f}億",
            "外資": f"{r['f']:+,}張",
        } for r in launch])
        st.dataframe(df_la, use_container_width=True, hide_index=True)
    else:
        st.info("今日無投信突破500張的首日發動個股")

    st.markdown("---")

    # ── 策略二：投信佈局（需個股歷史數據）────────────────────
    st.markdown(f"""
<div style="background:#fff;border-radius:10px;padding:13px 16px;margin-bottom:4px;border-left:4px solid #8e44ad;box-shadow:0 1px 3px rgba(0,0,0,.07)">
  <div style="font-size:14px;font-weight:700;color:#1a2332;margin-bottom:4px">
    🕵️ 策略二：投信暗中佈局（需先分析個股）
    <span style="background:#f5eeff;color:#8e44ad;border:1px solid #d7bde2;font-size:10px;padding:1px 7px;border-radius:99px;margin-left:5px">{len(trust)} 檔</span>
  </div>
  <div style="font-size:12px;color:#555">5日內投信買超天數≥4，來自已分析的個股清單</div>
</div>""", unsafe_allow_html=True)
    if trust:
        df_tr = pd.DataFrame([{
            "代號": r["sid"],"名稱": r["name"][:8],
            "現價": r["price"],"漲跌%": f"{r.get('chg',0):+.1f}%",
            "5日買超天數": f"{r['buy_days']}/5天",
            "累計買超(張)": f"+{r['t_total']:,}",
        } for r in trust])
        st.dataframe(df_tr, use_container_width=True, hide_index=True)
    else:
        st.info("請先在「🔍 個股分析」頁分析你的追蹤清單，此策略將自動呈現結果")


def tab_analysis():
    token   = st.session_state.token
    sids    = [s.strip() for s in st.session_state.stock_list.split(",") if s.strip()]
    results = st.session_state.results

    st.markdown("""
<div style="background:linear-gradient(135deg,#1a2332,#2c3e50);border-radius:13px;
padding:15px 18px;margin-bottom:12px">
  <div style="font-size:19px;font-weight:800;color:#fff">📊 個股分析</div>
  <div style="font-size:11px;color:#8fa3b8;margin-top:3px">wiwynn 格式完整報告</div>
</div>""", unsafe_allow_html=True)

    if token:
        lr = st.session_state.last_run
        st.success(f"✅ Token 已設定 | 上次：{lr.strftime('%m/%d %H:%M') if lr else '尚未執行'} | {len(sids)}支")
    else:
        st.error("⚠️ 請到「⚙️ 設定」填入 FinMind Token")

    col1, col2 = st.columns([3,1])
    with col1:
        run = st.button("🔄 分析全部股票", disabled=not token, use_container_width=True)
    with col2:
        force = st.checkbox("強制重爬", value=False, help="忽略快取，重新抓取數據")

    # 嘗試載入持久快取
    if not results:
        cached_batch = load_results_cache()
        if cached_batch:
            st.session_state.results = cached_batch
            results = cached_batch
            st.info(f"📦 已從快取載入 {len(results)} 支股票分析結果（{CACHE_DIR}）")

    if run:
        errors = []
        with st.spinner("取得處置股清單..."):
            st.session_state.disposed = fetch_disposed_cached()

        all_res = []; bar = st.progress(0, "準備中...")
        for i, sid in enumerate(sids):
            bar.progress((i+1)/len(sids), text=f"分析 {nm(sid)}（{i+1}/{len(sids)}）")
            r, err = analyze(sid, token, st.session_state.disposed, force=force)
            if r:
                all_res.append(r)
            else:
                errors.append(f"{sid} {nm(sid)}：{err}")
            time.sleep(0.2)
        bar.empty()

        if all_res:
            sorted_res = sorted(all_res, key=lambda x: x["score"], reverse=True)
            st.session_state.results = sorted_res
            st.session_state.last_run = datetime.now()
            save_results_cache([r for r in sorted_res])   # 存持久快取
            st.success(f"✅ 完成！{len(all_res)} 支，已存快取")
        else:
            st.error("❌ 分析失敗，請確認 Token 是否正確")
        if errors:
            with st.expander(f"⚠️ {len(errors)} 支失敗"):
                for e in errors: st.write(e)
        st.rerun()

    if not results:
        st.info("👆 點「分析全部股票」按鈕，或等待自動載入快取")
        return

    # 評等統計
    from collections import Counter
    cnts = Counter(r["rating"] for r in results)
    c1,c2,c3,c4 = st.columns(4)
    for col,(rt,em,bg) in zip([c1,c2,c3,c4],[
        ("S","⭐","#d4edda"),("A","✅","#d4edda"),("B","👀","#fff3cd"),("C","❌","#f8d7da")]):
        col.markdown(
            f'<div style="background:{bg};border-radius:9px;padding:9px;text-align:center">'
            f'<div style="font-size:16px">{em}</div>'
            f'<div style="font-size:20px;font-weight:800;color:{RC[rt]}">{cnts.get(rt,0)}</div>'
            f'<div style="font-size:10px;color:#555">{rt}</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    # 下載
    full_html = build_full_html(results)
    st.download_button("📥 下載完整 HTML 報告",full_html,
                       f"portfolio_{date.today().strftime('%Y%m%d')}.html","text/html",
                       use_container_width=True)

    st.markdown("---")

    # 選擇個股查看
    sorted_r = sorted(results, key=lambda x: x["score"], reverse=True)
    opts = [f"{r['rating']} {r['name']}（{r['sid']}） — {r['score']}分 | {r['price']:,.0f}元 {r['chg']:+.1f}%"
            for r in sorted_r]
    sel = st.selectbox("🔍 選擇股票查看完整報告", range(len(opts)),
                       format_func=lambda i: opts[i])
    r_sel = sorted_r[sel]

    col_a, col_b = st.columns(2)
    with col_a:
        html = build_wiwynn(r_sel)
        st.download_button(f"📄 下載 {r_sel['name']} 個股報告", html,
                           f"{r_sel['sid']}_{date.today().strftime('%Y%m%d')}.html","text/html",
                           use_container_width=True)
    with col_b:
        if st.button(f"🔄 重新分析 {r_sel['name']}", use_container_width=True):
            with st.spinner("重新抓取數據..."):
                new_r, err = analyze(r_sel["sid"], token, st.session_state.disposed, force=True)
            if new_r:
                idx = next((i for i,x in enumerate(st.session_state.results) if x["sid"]==r_sel["sid"]), None)
                if idx is not None: st.session_state.results[idx] = new_r
                save_results_cache(st.session_state.results)
                st.success("✅ 已更新")
                st.rerun()
            else:
                st.error(f"❌ 失敗：{err}")

    components.html(html, height=2700, scrolling=True)


def tab_rank():
    st.markdown("### 🏆 今日評等排行")
    results = st.session_state.results
    if not results:
        st.info("請先在「📊 個股分析」頁執行分析")
        return
    df = pd.DataFrame([{
        "評等":r["rating"],"股票":f"{r['name']}({r['sid']})","分數":r["score"],
        "現價":r["price"],"漲跌%":f"{r['chg']:+.2f}%",
        "外資":f"{r['fc']:+d}日","投信":f"{r['tc']:+d}日",
        "目標":f"{r['tp']:,.0f}" if r.get("tp") else "-",
    } for r in results])
    st.dataframe(df, use_container_width=True, hide_index=True)
    buy2=[r for r in results if r["fc"]>0 and r["tc"]>0 and not r["is_disposed"]]
    if buy2:
        st.markdown("### ✅ 外資+投信同向買超")
        for r in sorted(buy2,key=lambda x:x["fc"]+x["tc"],reverse=True):
            chg=r["chg"] or 0; cc2="#27ae60" if chg>=0 else "#c0392b"
            st.markdown(
                f'<div style="background:#fff;border-left:4px solid #27ae60;border-radius:8px;'
                f'padding:9px 13px;margin:4px 0;border:1px solid #c3e6cb">'
                f'<strong style="color:#1a2332">{r["name"]}（{r["sid"]}）</strong> '
                f'<span style="color:{cc2}">{r["price"]:,.0f}元 {chg:+.1f}%</span> '
                f'外資<span style="color:#27ae60;font-weight:700">+{r["fc"]}日</span> '
                f'投信<span style="color:#27ae60;font-weight:700">+{r["tc"]}日</span>'
                f'</div>', unsafe_allow_html=True)


def tab_settings():
    st.markdown("### ⚙️ 系統設定與配置")
    with st.form("sf", clear_on_submit=False):
        st.markdown("**🔑 FinMind 官方 API Token**")
        token = st.text_input("Token", value=st.session_state.token, type="password",
                               placeholder="貼上你的 FinMind Token（僅個股分析需要）",
                               label_visibility="collapsed")
        st.markdown("**📋 自選股清單（逗號分隔，建議最多 15 支）**")
        sl = st.text_area("stocks", value=st.session_state.stock_list,
                          height=80, label_visibility="collapsed")
        ok = st.form_submit_button("💾 儲存設定並寫入快取", use_container_width=True)
    if ok:
        st.session_state.token = token.strip()
        st.session_state.stock_list = sl.strip()
        st.success("✅ 儲存完成！請切換到「📊 個股分析」開始分析。")
    st.markdown("---")
    # 快取管理
    st.markdown("**📦 快取管理**")
    cc1, cc2 = st.columns(2)
    with cc1:
        cached = load_results_cache()
        if cached:
            st.success(f"✅ 批次快取：{len(cached)} 支股票")
        else:
            st.info("無批次快取")
    with cc2:
        if st.button("🗑 清除所有快取", use_container_width=True):
            import shutil
            shutil.rmtree(CACHE_DIR, ignore_errors=True)
            os.makedirs(CACHE_DIR, exist_ok=True)
            fetch_twse_prices_all.clear()
            fetch_twse_institution_all.clear()
            fetch_tpex_prices_all.clear()
            fetch_tpex_institution_all.clear()
            st.session_state.results = []
            st.success("✅ 已清除，下次分析將重新抓取")
    st.markdown("---")
    st.markdown("""
**📌 取得 FinMind Token**
1. 前往 [finmindtrade.com](https://finmindtrade.com) 免費註冊
2. 登入後在帳號頁面複製 Token

**📱 加入 iPhone 主畫面**
Safari 開啟 → 分享📤 → 加入主畫面

**💡 籌碼掃描不需要 Token**，開啟即自動載入全市場數據！
    """)
    st.caption(f"快取路徑：{CACHE_DIR}")
    if st.session_state.token:
        st.success(f"Token 前8碼：{st.session_state.token[:8]}...")
    else:
        st.warning("尚未設定 Token（籌碼掃描功能仍可正常使用）")


# ─────────────────────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────────────────────
def main():
    # 第一頁為籌碼掃描（開啟即看到）
    t1, t2, t3, t4 = st.tabs(["📡 籌碼掃描", "🔍 個股分析", "🏆 排行榜", "⚙️ 設定"])
    with t1: tab_scanner()
    with t2: tab_analysis()
    with t3: tab_rank()
    with t4: tab_settings()


if __name__ == "__main__":
    main()
