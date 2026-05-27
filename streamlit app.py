"""台股分析系統 v6.3 — 完整可執行版"""
import os, json, re, time, calendar as _cal, warnings
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

st.set_page_config(page_title="📊 台股分析", page_icon="📊",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""<style>
[data-testid="stHeader"],#MainMenu,footer{display:none!important}
.block-container{padding:.5rem .8rem 1rem!important;max-width:820px;margin:0 auto}
p,span,label,li,td,th,div{color:#e8eaf0}strong{color:#fff}h1,h2,h3,h4{color:#fff!important}
[data-testid="stMarkdownContainer"] *{color:#e8eaf0!important}
.stTabs [data-baseweb="tab-list"]{background:#0f1724!important;border-radius:12px;padding:5px;gap:2px}
.stTabs [data-baseweb="tab"]{color:#8fa3b8!important;font-size:12px;font-weight:600;border-radius:8px;padding:7px 1px}
.stTabs [aria-selected="true"]{background:#27ae60!important;color:#fff!important}
.stTabs [data-baseweb="tab-panel"]{background:transparent!important}
.stButton>button{background:#27ae60!important;color:#fff!important;border:none!important;border-radius:10px!important;font-size:14px!important;font-weight:700!important;width:100%}
.stButton>button:disabled{background:#444!important;color:#888!important}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{background:#2c3e50!important;color:#fff!important;border:1px solid #3d5166!important}
[data-testid="stSelectbox"] *{color:#e8eaf0!important}
[data-testid="stSelectbox"]>div>div{background:#2c3e50!important;border:1px solid #3d5166!important}
[data-testid="stDataFrame"]{background:#2c3e50!important;border-radius:8px}
[data-testid="stDataFrame"] *{color:#e8eaf0!important}
</style>""", unsafe_allow_html=True)

# ── 股票資料庫 ────────────────────────────────────────────────
ALL_STOCKS = {
    "2330":"台積電","2317":"鴻海","2454":"聯發科","2308":"台達電","2382":"廣達",
    "2303":"聯電","2327":"國巨","2357":"華碩","2379":"瑞昱","2376":"技嘉",
    "2313":"華通","2368":"金像電","2603":"長榮","2609":"陽明","2615":"萬海",
    "3711":"日月光投控","2412":"中華電","2886":"兆豐金","2881":"富邦金","2882":"國泰金",
    "2884":"玉山金","2891":"中信金","1301":"台塑","1303":"南亞","2002":"中鋼",
    "2408":"南亞科","2474":"可成","2385":"群光","3661":"世芯-KY","6669":"緯穎",
    "2353":"宏碁","2356":"英業達","3034":"聯詠","3037":"欣興","3231":"緯創",
    "1513":"中興電","2059":"川湖","2301":"光寶科","2337":"旺宏","2344":"華邦電",
    "2352":"佳世達","2371":"大同","2395":"研華","2409":"友達","2498":"宏達電",
    "2603":"長榮","2606":"裕民","2609":"陽明","2610":"華航","2615":"萬海",
    "2618":"長榮航","2633":"台灣高鐵","2880":"華南金","2883":"開發金","2885":"元大金",
    "2887":"台新金","2890":"永豐金","2892":"第一金","2912":"統一超","3008":"大立光",
    "3017":"奇鋐","3035":"智原","3036":"文曄","3044":"健鼎","3048":"益登",
    "3081":"聯惠","3105":"穩懋","3293":"鈊象","3406":"玉晶光","3443":"創意",
    "3481":"群創","3529":"力旺","3533":"嘉澤","3550":"樂士","3583":"辛耘",
    "3587":"閎康","3645":"達亮","3665":"貿聯-KY","3698":"隆達","3702":"大聯大",
    "3706":"神達","4938":"和碩","4966":"譜瑞-KY","5347":"世界先進","5483":"中美晶",
    "5880":"合庫金","6239":"力成","6271":"同欣電","6285":"啟碁","6415":"矽力-KY",
    "6488":"環球晶","6510":"精測","6515":"穎威","6526":"達發","6533":"晶心科",
    "6670":"復盛應用","6669":"緯穎","6770":"力積電","8046":"南電","8150":"南茂",
    "8299":"群聯","5274":"信驊","4919":"新唐","4958":"臻鼎-KY","4968":"立積",
    "5269":"祥碩","3592":"瑞鼎","3596":"智易","6526":"達發","6533":"晶心科",
}

_MARKET_NAMES: dict = {}

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"
GEMINI_MODEL = "gemini-2.0-flash"
HDR = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CACHE_DIR = "/tmp/tw_stock_v63"
os.makedirs(CACHE_DIR, exist_ok=True)

RC  = {"S":"#1a5c38","A":"#27ae60","B":"#854F0B","C":"#A32D2D"}
RL  = {"S":"#D0F0DC","A":"#D0F0DC","B":"#FAE0A8","C":"#F7C1C1"}
RS  = {"S":"#A8E6BB","A":"#A8E6BB","B":"#F5C842","C":"#F09595"}
VBG = {"S":"#1a3a27","A":"#1a3a27","B":"#3a2c0a","C":"#3a1a1a"}
VBC = {"S":"#27ae60","A":"#27ae60","B":"#f39c12","C":"#e74c3c"}
VTC = {"S":"#a8e6bb","A":"#a8e6bb","B":"#fae0a8","C":"#f7c1c1"}

# ── Session state ─────────────────────────────────────────────
_SS_DEFAULTS = [
    ("token",""), ("gemini_key",""),
    ("stock_list","2330,6669,3037,6515,1432,2059,2376,2454,3017,3034,3293,3529,7769,8027"),
    ("results",[]), ("last_run",None), ("disposed",set()),
    ("gemini_delisting",set()), ("gemini_delisting_ts",None),
    ("cal_year",date.today().year), ("cal_month",date.today().month),
    ("cal_events",[]), ("cal_events_ts",None),
    ("scanner_sector",None),
]
for _k, _v in _SS_DEFAULTS:
    if _k not in st.session_state:
        st.session_state[_k] = _v

if not st.session_state.token:
    try:
        t = st.secrets.get("FINMIND_TOKEN","")
        if t: st.session_state.token = t
    except Exception: pass
if not st.session_state.gemini_key:
    try:
        g = st.secrets.get("GEMINI_API_KEY","")
        if g: st.session_state.gemini_key = g
    except Exception: pass

# ── 工具函式 ──────────────────────────────────────────────────
def fi(s, d=0):
    try: return int(str(s).replace(",","").replace(" ","").strip())
    except: return d

def ff(s, d=0.0):
    try: return float(str(s).replace(",","").replace(" ","").strip())
    except: return d

def parse_tw(s):
    if not s or str(s).strip() in ("--","","-"): return 0
    try: return int(str(s).replace(",","").replace(" ","").strip())
    except: return 0

def ma_n(cls, n): return round(sum(cls[-n:])/n, 2) if len(cls)>=n else None
def dev_pct(p, m): return round((p-m)/m*100, 2) if p and m and m>0 else None
def ccc(v): return "up" if v>=0 else "dn"
def fv(v, u="", dig=2):
    if v is None: return "N/A"
    return f"{v:,.{dig}f}{u}"

def con_days(series):
    if not series: return 0
    last = series[-1]
    if last == 0: return 0
    d = 1 if last>0 else -1; c = 0
    for v in reversed(series):
        if (v>0 and d==1) or (v<0 and d==-1): c+=1
        else: break
    return c*d

@st.cache_data(ttl=86400)          # 每日更新一次
def fetch_all_stock_names(token: str = "") -> dict:
    """
    全市場股票名稱字典（上市 + 上櫃 + 興櫃），快取 24 小時。

    查詢優先順序：
    1. FinMind TaiwanStockInfo（最完整，含興櫃；需要 Token）
    2. Fallback：TWSE / TPEx OpenAPI（免費，不需要 Token）

    過濾規則（去除權證 / 牛熊證）：
    - 4 位代號：全部保留（一般股票）
    - 5 位代號以 "00" 開頭：保留（ETF，如 00878, 00929）
    - 6 位代號以 "00" 開頭：保留（ETF，如 006205）
    - 長度 ≥ 6 且不以 "00" 開頭：直接跳過（權證 / 牛熊，如 707769）
    """
    names: dict = dict(ALL_STOCKS)   # 先載入硬編碼庫

    def _add(code: str, name: str) -> None:
        """套用過濾規則後寫入字典"""
        code = str(code).strip(); name = str(name).strip()
        if not code or not name:
            return
        # ── 權證過濾器 ───────────────────────────────────────────
        if len(code) >= 6 and not code.startswith("00"):
            return          # 跳過權證 / 牛熊（如 707769, 030705）
        # ────────────────────────────────────────────────────────
        names[code] = name

    finmind_ok = False

    # ══════════════════════════════════════════════════════════════
    # 1. 主要來源：FinMind TaiwanStockInfo（含上市/上櫃/興櫃）
    # ══════════════════════════════════════════════════════════════
    if token:
        try:
            r = requests.get(
                FINMIND_API,
                params={"dataset": "TaiwanStockInfo", "token": token},
                headers=HDR, timeout=30, verify=False
            )
            if r.status_code == 200:
                payload = r.json()
                data = payload.get("data", [])
                if data:
                    for item in data:
                        _add(item.get("stock_id", ""), item.get("stock_name", ""))
                    finmind_ok = True
        except Exception:
            pass

    if finmind_ok:
        return names   # FinMind 成功，直接回傳（含完整興櫃）

    # ══════════════════════════════════════════════════════════════
    # 2. Fallback：TWSE / TPEx OpenAPI
    # ══════════════════════════════════════════════════════════════

    # ── 上市（TWSE）：每日行情（含名稱）────────────────────────
    try:
        r = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            headers=HDR, timeout=25, verify=False)
        if r.status_code == 200:
            for item in r.json():
                _add(item.get("Code",""), item.get("Name",""))
    except Exception:
        pass

    # ── 上市（TWSE）：公司基本資料 ──────────────────────────────
    try:
        r = requests.get(
            "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            headers=HDR, timeout=25, verify=False)
        if r.status_code == 200:
            for item in r.json():
                _add(item.get("公司代號",""), item.get("公司簡稱",""))
    except Exception:
        pass

    # ── 上市（TWSE）：BWIBBU_ALL 補充 ───────────────────────────
    try:
        r = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
            headers=HDR, timeout=25, verify=False)
        if r.status_code == 200:
            for item in r.json():
                _add(item.get("Code",""), item.get("Name",""))
    except Exception:
        pass

    # ── 上櫃（TPEx）：每日收盤 ──────────────────────────────────
    try:
        r = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            headers=HDR, timeout=25, verify=False)
        if r.status_code == 200:
            for item in r.json():
                _add(item.get("SecuritiesCompanyCode",""), item.get("CompanyName",""))
    except Exception:
        pass

    # ── 上櫃（TPEx）：公司清單 ──────────────────────────────────
    try:
        r = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_listed_companies",
            headers=HDR, timeout=25, verify=False)
        if r.status_code == 200:
            for item in r.json():
                _add(item.get("SecuritiesCompanyCode",""), item.get("CompanyName",""))
    except Exception:
        pass

    # ── 興櫃（TPEx Emerging）──────────────────────────────────────
    for esm_url in [
        "https://www.tpex.org.tw/openapi/v1/tpex_esm_daily_close_quotes",
        "https://www.tpex.org.tw/openapi/v1/tpex_esm_list",
    ]:
        try:
            r = requests.get(esm_url, headers=HDR, timeout=20, verify=False)
            if r.status_code == 200:
                for item in r.json():
                    code = item.get("SecuritiesCompanyCode", item.get("code",""))
                    name = item.get("CompanyName", item.get("name",""))
                    _add(code, name)
        except Exception:
            continue

    return names


def nm(sid: str) -> str:
    """
    取得股票中文名稱，查詢優先順序：
    1. ALL_STOCKS（硬編碼，速度最快）
    2. _MARKET_NAMES（執行期動態快取）
    3. fetch_all_stock_names()（全市場 API，帶 st.cache_data）
    4. fallback 回傳股號本身（絕不顯示 "7769 7769"）
    """
    # 快速路徑 1：硬編碼字典
    if sid in ALL_STOCKS:
        return ALL_STOCKS[sid]
    # 快速路徑 2：動態快取
    if sid in _MARKET_NAMES:
        return _MARKET_NAMES[sid]
    # 路徑 3：全市場快取（第一次略慢，之後 O(1)）
    try:
        _token = st.session_state.get("token", "") if hasattr(st, "session_state") else ""
        all_names = fetch_all_stock_names(_token)
        if sid in all_names:
            _MARKET_NAMES[sid] = all_names[sid]   # 寫入動態快取，下次更快
            return all_names[sid]
    except Exception:
        pass
    # Fallback：回傳股號（不會出現「7769 7769」）
    return sid


def update_market_names(prices_dict: dict) -> None:
    """從市場價格數據批次更新 _MARKET_NAMES 動態快取"""
    global _MARKET_NAMES
    for sid, data in prices_dict.items():
        n = data.get("name", "")
        if n:
            _MARKET_NAMES[sid] = n

def last_trading_days(n=5):
    now_tw = datetime.utcnow() + timedelta(hours=8)
    start = (now_tw.date() - timedelta(days=1)) if now_tw.hour<17 else now_tw.date()
    days = []; d = start
    while len(days)<n:
        if d.weekday()<5: days.append(d)
        d -= timedelta(days=1)
    return days

def get_inst_date_str():
    now_tw = datetime.utcnow() + timedelta(hours=8)
    d = (now_tw.date()-timedelta(days=1)) if now_tw.hour<17 else now_tw.date()
    while d.weekday()>=5: d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

def search_stocks(query: str) -> list:
    """
    搜尋全市場股票（上市+上櫃+興櫃）。
    優先使用 fetch_all_stock_names()，確保興櫃也能找到。
    """
    q = query.strip()
    if not q:
        return []

    # 取得全市場名稱字典（帶快取，第一次略慢）
    try:
        _token = st.session_state.get("token", "") if hasattr(st, "session_state") else ""
        universe = fetch_all_stock_names(_token)
    except Exception:
        # 若 Streamlit context 尚未就緒，退化到本地字典
        universe = {**ALL_STOCKS, **_MARKET_NAMES}

    # 比對股號或名稱片段
    seen: set = set()
    res: list = []
    for code, name in universe.items():
        if q in code or q in name:
            if code not in seen:
                seen.add(code)
                res.append((code, name))

    # 排序：完全符合股號 > 股號前綴 > 股號包含 > 名稱包含
    def rank(item):
        c, n = item
        if c == q:          return 0
        if c.startswith(q): return 1
        if q in c:          return 2
        return 3

    res.sort(key=rank)
    return res[:25]

# ── 持久快取 ──────────────────────────────────────────────────
def cache_path(sid): return os.path.join(CACHE_DIR, f"{sid}.json")
def save_cache(sid, data):
    try:
        with open(cache_path(sid),"w",encoding="utf-8") as f:
            json.dump({"ts":datetime.now().isoformat(),"data":data},f,ensure_ascii=False)
    except Exception: pass
def load_cache(sid, max_hours=4):
    p = cache_path(sid)
    if not os.path.exists(p): return None
    try:
        with open(p,encoding="utf-8") as f: obj=json.load(f)
        if datetime.now()-datetime.fromisoformat(obj["ts"])<timedelta(hours=max_hours):
            return obj["data"]
    except Exception: pass
    return None
def save_results_cache(results):
    try:
        with open(os.path.join(CACHE_DIR,"batch.json"),"w",encoding="utf-8") as f:
            json.dump({"ts":datetime.now().isoformat(),"results":results},f,ensure_ascii=False)
    except Exception: pass
def load_results_cache():
    p = os.path.join(CACHE_DIR,"batch.json")
    if not os.path.exists(p): return None
    try:
        with open(p,encoding="utf-8") as f: obj=json.load(f)
        if datetime.now()-datetime.fromisoformat(obj["ts"])<timedelta(hours=4):
            return obj["results"]
    except Exception: pass
    return None

# ── Gemini 下市偵測 ───────────────────────────────────────────
def gemini_fetch_delisting(api_key):
    if not api_key: return set()
    ts = st.session_state.gemini_delisting_ts
    if ts and (datetime.now()-ts).seconds<21600 and st.session_state.gemini_delisting:
        return st.session_state.gemini_delisting
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = ("請列出台灣股市全額交割股和下市警告股的4位數股號，每行一個，只列代號：\n"
                  "1.全額交割股 2.面臨下市股 3.注意/警示股票")
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        codes = set(re.findall(r'\b\d{4}\b', response.text))
        valid = {c for c in codes if 1000<=int(c)<=9999}
        st.session_state.gemini_delisting = valid
        st.session_state.gemini_delisting_ts = datetime.now()
        return valid
    except Exception: return set()

# ── Gemini 財經事件 ───────────────────────────────────────────
def gemini_fetch_events(api_key, year, month):
    if not api_key:
        return _default_events(year, month)
    cache_key = f"{year}-{month:02d}"
    ts = st.session_state.cal_events_ts
    if (ts and (datetime.now()-ts).seconds<21600
            and st.session_state.cal_events
            and st.session_state.cal_events[0].get("_month")==cache_key):
        return st.session_state.cal_events
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        next_m = month%12+1; next_y = year+(1 if month==12 else 0)
        prompt = (
            f"你是財經分析師，提供{year}年{month}月（延伸至{next_y}年{next_m}月上旬）重大財經事件。\n"
            "必須涵蓋：1.美國CPI/非農/Fed FOMC 2.NVIDIA/Apple/Microsoft/Google/Meta/Amazon財報 "
            "3.台積電法說會(1/4/7/10月) 4.聯發科法說會(2/5/8/11月) 5.台灣央行(3/6/9/12月) "
            "6.G7/G20/川習會 7.ECB/BOJ利率決策 8.台灣月營收(每月10日)\n"
            "以JSON陣列回傳（不要markdown）："
            "[{\"date\":\"YYYY-MM-DD\",\"title\":\"15字內\",\"detail\":\"60字內\"，"
            "\"category\":\"美國總經/台灣財經/全球事件/企業財報/科技大會\","
            "\"impact\":\"bullish/bearish/neutral\",\"impact_zh\":\"利多/利空/中性\"，"
            "\"reason\":\"對台股影響35字內\"}]\n"
            f"目標30~50個事件，{year}年{month}月份，只回傳JSON。"
        )
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = response.text.strip()
        text = re.sub(r'```json\s*','',text); text = re.sub(r'```\s*','',text)
        events = json.loads(text) if text.startswith('[') else json.loads(re.search(r'\[.*\]',text,re.DOTALL).group(0))
        validated = []
        for ev in events:
            if not ev.get("date") or not ev.get("title"): continue
            ev["_month"] = cache_key
            ev.setdefault("impact","neutral"); ev.setdefault("impact_zh","中性")
            ev.setdefault("category","其他"); ev.setdefault("reason","")
            validated.append(ev)
        validated.sort(key=lambda x:x["date"])
        st.session_state.cal_events = validated
        st.session_state.cal_events_ts = datetime.now()
        return validated
    except Exception:
        return _default_events(year, month)

def _default_events(year, month):
    pfx = f"{year}-{month:02d}"
    TW_DEADLINES = {3:(31,"台灣全年報截止"),5:(15,"台灣Q1季報截止"),8:(14,"台灣Q2半年報截止"),11:(14,"台灣Q3季報截止")}
    TSMC_M = {1,4,7,10}; MTEK_M = {2,5,8,11}; FOX_M = {3,6,9,12}
    mzh = ["一","二","三","四","五","六","七","八","九","十","十一","十二"][month-1]
    events = [
        {"date":f"{pfx}-05","title":"美國非農就業","detail":"美國勞工部公布非農就業人口",
         "category":"美國總經","impact":"neutral","impact_zh":"中性","reason":"高於預期引發升息預期，利空科技股"},
        {"date":f"{pfx}-10","title":"美國CPI通膨","detail":"美國消費者物價指數公布",
         "category":"美國總經","impact":"bearish","impact_zh":"利空","reason":"通膨超預期壓抑Fed降息空間"},
        {"date":f"{pfx}-10","title":"台灣月營收公布","detail":"上市上櫃公司公布上月月營收",
         "category":"台灣財經","impact":"neutral","impact_zh":"中性","reason":"月營收YoY/MoM是台股最重要先行指標"},
        {"date":f"{pfx}-20","title":"Fed FOMC利率決策","detail":"聯準會利率決策與聲明",
         "category":"美國總經","impact":"neutral","impact_zh":"中性","reason":"利率走向是全球資金流向最重要指標"},
        {"date":f"{pfx}-28","title":"美國PCE物價指數","detail":"Fed最重視的通膨指標",
         "category":"美國總經","impact":"neutral","impact_zh":"中性","reason":"PCE是Fed制定利率政策核心參考"},
    ]
    if month in TW_DEADLINES:
        day, title = TW_DEADLINES[month]
        events.append({"date":f"{pfx}-{day:02d}","title":title,
                        "detail":"台灣上市上櫃公司財報截止日","category":"台灣財經",
                        "impact":"neutral","impact_zh":"中性","reason":"財報截止前後個股財報漲跌分化"})
    if month in TSMC_M:
        events.append({"date":f"{pfx}-18","title":"台積電法說會",
                        "detail":f"台積電{mzh}月季度業績說明會","category":"企業財報",
                        "impact":"bullish","impact_zh":"利多","reason":"台積電法說是台股最重要風向球"})
    if month in MTEK_M:
        events.append({"date":f"{pfx}-12","title":"聯發科法說會",
                        "detail":"聯發科季度業績說明會","category":"企業財報",
                        "impact":"bullish","impact_zh":"利多","reason":"聯發科展望影響IC設計族群走勢"})
    if month in FOX_M:
        events.append({"date":f"{pfx}-20","title":"鴻海/廣達法說","detail":"鴻海廣達緯創等EMS廠法說",
                        "category":"企業財報","impact":"bullish","impact_zh":"利多","reason":"AI伺服器訂單動向決定ODM族群走勢"})
    events.append({"date":f"{pfx}-21","title":"台灣央行理監事會",
                    "detail":"台灣央行季度利率決策","category":"台灣財經",
                    "impact":"neutral","impact_zh":"中性","reason":"台幣走勢影響科技股匯兌損益"})
    for e in events: e["_month"] = f"{year}-{month:02d}"
    events.sort(key=lambda x:x["date"])
    return events

# ── 行事曆 HTML ───────────────────────────────────────────────
def build_calendar_html(events, year, month):
    from collections import defaultdict as _dd
    day_ev = _dd(list)
    for ev in events:
        try:
            d = datetime.strptime(ev["date"],"%Y-%m-%d")
            if d.year==year and d.month==month: day_ev[d.day].append(ev)
        except Exception: pass
    today = date.today(); week_end = today+timedelta(days=7)
    week_evs = []
    for ev in events:
        try:
            dw = datetime.strptime(ev["date"],"%Y-%m-%d").date()
            if today<=dw<=week_end: week_evs.append((dw,ev))
        except Exception: pass
    week_evs.sort(key=lambda x:x[0])
    IC={"bullish":"#27ae60","bearish":"#e74c3c","neutral":"#8fa3b8"}
    IB={"bullish":"#1a3a27","bearish":"#3a1a1a","neutral":"#2c3e50"}
    IZ={"bullish":"🟢利多","bearish":"🔴利空","neutral":"⚪中性"}
    first_wd,days_in_month = _cal.monthrange(year,month)
    cells = ""
    for _ in range(first_wd): cells += '<div class="cc ce"></div>'
    for day in range(1,days_in_month+1):
        is_today = (today==date(year,month,day))
        tc = "ct" if is_today else ""
        td = '<div class="td"></div>' if is_today else ""
        evs = day_ev.get(day,[])
        pills = ""
        for ev in evs[:3]:
            imp=ev.get("impact","neutral"); ic=IC.get(imp,"#8fa3b8"); ibg=IB.get(imp,"#2c3e50")
            t2=ev.get("title","")[:8]; dt=ev.get("detail","")
            pills+='<div class="cp" style="background:'+ibg+';border-left:2px solid '+ic+';color:'+ic+'" title="'+dt+'">'+t2+'</div>'
        if len(evs)>3: pills+='<div class="cm">+'+str(len(evs)-3)+'</div>'
        cells+='<div class="cc '+tc+'">'+td+'<div class="cdn">'+str(day)+'</div>'+pills+'</div>'
    for _ in range((7-((first_wd+days_in_month)%7))%7): cells+='<div class="cc ce"></div>'
    w_html = ""
    if week_evs:
        for dw,ev in week_evs:
            imp=ev.get("impact","neutral"); ic=IC.get(imp,"#8fa3b8"); ibg=IB.get(imp,"#2c3e50"); iz=IZ.get(imp,"⚪中性")
            wd_zh=["一","二","三","四","五","六","日"][dw.weekday()]
            tmk="📍今天 " if dw==today else ""
            rsn=ev.get("reason",""); rh='<div class="wer">📊 '+rsn+'</div>' if rsn else ""
            w_html+=('<div class="we" style="border-left:4px solid '+ic+';background:'+ibg+'">'
                     +'<div class="weh"><span class="wed">'+tmk+dw.strftime("%m/%d")+' 週'+wd_zh+'</span>'
                     +'<span class="wei" style="background:'+ic+'22;color:'+ic+';border:1px solid '+ic+'55">'+iz+'</span></div>'
                     +'<div class="wet">'+ev.get("title","")+'</div>'
                     +'<div class="wede">'+ev.get("detail","")+'</div>'+rh+'</div>')
    else: w_html='<div style="color:#8fa3b8;font-size:13px;padding:12px 0">本週無重大財經事件</div>'
    ev_list=""
    pfx_str=f"{year}-{month:02d}"
    for ev in sorted(events,key=lambda x:x["date"]):
        if not ev.get("date","").startswith(pfx_str): continue
        imp=ev.get("impact","neutral"); ic=IC.get(imp,"#8fa3b8"); ibg=IB.get(imp,"#2c3e50"); iz=IZ.get(imp,"⚪中性")
        ttl=ev.get("title",""); dtl=ev.get("detail",""); rsn=ev.get("reason","")
        rh='<div style="font-size:10px;color:#7ec8e3;margin-top:2px">📊 '+rsn+'</div>' if rsn else ""
        ev_list+=('<div class="eli"><span class="edb">'+ev["date"][5:]+'</span>'
                  +'<span class="eib" style="background:'+ibg+';color:'+ic+';border:1px solid '+ic+'44">'+iz+'</span>'
                  +'<div><div style="font-size:12px;font-weight:600;color:#e8eaf0">'+ttl+'</div>'
                  +'<div style="font-size:11px;color:#8fa3b8;margin-top:2px">'+dtl+'</div>'+rh+'</div></div>')
    n_ev=len([e for e in events if e.get("date","").startswith(pfx_str)])
    mzh2=["一","二","三","四","五","六","七","八","九","十","十一","十二"][month-1]
    css="""*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a2332;color:#e8eaf0;font-family:'Helvetica Neue',Arial,sans-serif}
.cw{max-width:800px;margin:0 auto;padding:10px}
.ch{background:#0f1724;border-radius:12px;padding:14px 20px;margin-bottom:12px}
.ctit{font-size:20px;font-weight:700;color:#fff}.csub{font-size:11px;color:#8fa3b8;margin-top:3px}
.wr{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin-bottom:2px}
.wh{text-align:center;font-size:10px;font-weight:600;color:#8fa3b8;padding:5px 0;background:#2c3e50;border-radius:4px}
.cg{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.cc{background:#2c3e50;border-radius:6px;padding:5px;min-height:75px;border:1px solid #3d5166;position:relative}
.cc:hover{border-color:#5d7a99;background:#364d66}
.ct{border-color:#27ae60!important;background:#1a3a27!important}
.ce{background:#1a2332;border:1px solid transparent}
.td{width:6px;height:6px;background:#27ae60;border-radius:50%;position:absolute;top:4px;right:4px}
.cdn{font-size:13px;font-weight:700;color:#e8eaf0;margin-bottom:3px}
.cp{font-size:9px;padding:2px 4px;border-radius:3px;margin-bottom:2px;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:default}
.cm{font-size:9px;color:#8fa3b8;text-align:right}
.ws{background:#0f1724;border-radius:12px;padding:14px 18px;margin-top:12px}
.wtit{font-size:14px;font-weight:700;color:#fff;margin-bottom:10px}
.we{border-radius:8px;padding:10px 13px;margin-bottom:8px;border:1px solid transparent}
.weh{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px}
.wed{font-size:12px;font-weight:700;color:#e8eaf0}
.wei{font-size:10px;padding:2px 7px;border-radius:99px;font-weight:600}
.wet{font-size:14px;font-weight:700;color:#fff;margin-bottom:3px}
.wede{font-size:12px;color:#8fa3b8;line-height:1.5;margin-bottom:3px}
.wer{font-size:11px;color:#7ec8e3;line-height:1.5}
.es{background:#0f1724;border-radius:12px;padding:14px 18px;margin-top:12px}
.eli{display:flex;gap:10px;padding:7px 0;border-bottom:1px solid #2c3e50;font-size:12px;align-items:flex-start}
.eli:last-child{border-bottom:none}
.edb{background:#2c3e50;border-radius:5px;padding:3px 7px;font-size:11px;font-weight:600;color:#e8eaf0;white-space:nowrap;flex-shrink:0}
.eib{font-size:10px;padding:2px 6px;border-radius:99px;font-weight:600;white-space:nowrap;flex-shrink:0}"""
    return ("<!DOCTYPE html><html lang=\"zh-TW\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<style>"+css+"</style></head><body><div class=\"cw\">"
            "<div class=\"ch\"><div class=\"ctit\">📅 "+str(year)+"年"+mzh2+"月 財經行事曆</div>"
            "<div class=\"csub\">共"+str(n_ev)+"個事件 | 🟢利多 🔴利空 ⚪中性</div></div>"
            "<div class=\"wr\">"
            "<div class=\"wh\">週一</div><div class=\"wh\">週二</div><div class=\"wh\">週三</div>"
            "<div class=\"wh\">週四</div><div class=\"wh\">週五</div>"
            "<div class=\"wh\" style=\"color:#e74c3c55\">週六</div>"
            "<div class=\"wh\" style=\"color:#e74c3c55\">週日</div></div>"
            "<div class=\"cg\">"+cells+"</div>"
            "<div class=\"ws\"><div class=\"wtit\">🔔 本週（7日內）重大事件提醒</div>"+w_html+"</div>"
            "<div class=\"es\"><div style=\"font-size:13px;font-weight:700;color:#fff;margin-bottom:9px\">📋 本月全部事件清單</div>"+ev_list+"</div>"
            "</div></body></html>")

# ── 風控 API ─────────────────────────────────────────────────

# ── 官方產業分類快取 ──────────────────────────────────────────
@st.cache_data(ttl=86400)
def fetch_official_sectors(token: str = "") -> dict:
    mapping = {}

    def clean_name(name):
        return name.replace("工業", "").replace("業", "") if len(name) > 2 else name

    # 1. 優先使用 FinMind（最穩定，且包含興櫃產業）
    if token:
        try:
            r = requests.get(
                FINMIND_API,
                params={"dataset": "TaiwanStockInfo", "token": token},
                headers=HDR, timeout=25, verify=False)
            if r.status_code == 200:
                for item in r.json().get("data", []):
                    code = str(item.get("stock_id", "")).strip()
                    ind  = str(item.get("industry_category", "")).strip()
                    if code and ind and ind not in ("None", ""):
                        mapping[code] = clean_name(ind)
        except Exception:
            pass

    if mapping:
        return mapping  # FinMind 成功則直接回傳

    # 2. Fallback：TWSE
    try:
        r = requests.get(
            "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            headers=HDR, timeout=25, verify=False)
        if r.status_code == 200:
            for item in r.json():
                code = str(item.get("公司代號", "")).strip()
                ind  = str(item.get("產業類別", "")).strip()
                if code and ind:
                    mapping[code] = clean_name(ind)
    except Exception:
        pass

    # 3. Fallback：TPEx
    try:
        r = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_listed_companies",
            headers=HDR, timeout=25, verify=False)
        if r.status_code == 200:
            for item in r.json():
                code = str(item.get("SecuritiesCompanyCode", "")).strip()
                ind  = str(item.get("Industry", "")).strip()
                if code and ind:
                    mapping[code] = clean_name(ind)
    except Exception:
        pass

    return mapping


@st.cache_data(ttl=3600)
def fetch_disposed_cached():
    disposed = set()
    for url in ["https://openapi.twse.com.tw/v1/announcement/punish",
                "https://www.tpex.org.tw/openapi/v1/tpex_announcement_punish"]:
        try:
            r=requests.get(url,headers=HDR,timeout=10,verify=False)
            if r.status_code==200:
                for item in r.json():
                    c=str(item.get("SecuritiesCode",item.get("code",""))).strip()
                    if c: disposed.add(c)
        except Exception: pass
    return disposed

@st.cache_data(ttl=3600)
def fetch_full_delivery_cached():
    out = set()
    try:
        r=requests.get("https://openapi.twse.com.tw/v1/announcement/fullCash",headers=HDR,timeout=10,verify=False)
        if r.status_code==200:
            for item in r.json():
                c=str(item.get("SecuritiesCode",item.get("Code",""))).strip()
                if c: out.add(c)
    except Exception: pass
    return out

@st.cache_data(ttl=3600)
def fetch_delisting_cached():
    out = set()
    for url in ["https://openapi.twse.com.tw/v1/announcement/changeTrading",
                "https://openapi.twse.com.tw/v1/announcement/fullCash",
                "https://openapi.twse.com.tw/v1/announcement/attention"]:
        try:
            r=requests.get(url,headers=HDR,timeout=10,verify=False)
            if r.status_code==200:
                for item in r.json():
                    c=str(item.get("SecuritiesCode",item.get("Code",""))).strip()
                    if c: out.add(c)
        except Exception: pass
    return out

# ── 全市場數據 ────────────────────────────────────────────────
@st.cache_data(ttl=14400)
def fetch_twse_prices_all():
    out = {}
    try:
        r=requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",headers=HDR,timeout=20,verify=False)
        if r.status_code==200:
            for item in r.json():
                sid=str(item.get("Code","")).strip()
                if not sid or not sid.isdigit(): continue
                p=ff(str(item.get("ClosingPrice","0")).replace(",",""))
                v=fi(str(item.get("TradeVolume","0")).replace(",",""))
                chg=ff(str(item.get("Change","")).replace("+","").replace(",",""))
                prev=p-chg if p else None; cp=round(chg/prev*100,2) if prev and prev>0 else 0.0
                if p>0 and v>0:
                    out[sid]={"price":p,"volume":v,"chg_pct":cp,"name":str(item.get("Name","")).strip()}
    except Exception: pass
    return out

@st.cache_data(ttl=14400)
def fetch_twse_institution_all(qdate=""):
    out = {}
    for trade_date in last_trading_days(5):
        ds = trade_date.strftime("%Y%m%d")
        for url in [f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={ds}&selectType=ALL",
                    f"https://www.twse.com.tw/fund/T86?response=json&date={ds}&selectType=ALL"]:
            try:
                r=requests.get(url,headers=HDR,timeout=20,verify=False)
                if r.status_code!=200: continue
                d=r.json()
                if d.get("stat","") not in ("OK","ok"): continue
                rows=d.get("data",d.get("Data",[]))
                if not rows or len(rows)<5: continue
                for row in rows:
                    if len(row)<11: continue
                    sid=str(row[0]).strip()
                    if not sid.isdigit(): continue
                    out[sid]={"f":parse_tw(row[7])//1000,"t":parse_tw(row[10])//1000,
                               "d":parse_tw(row[14])//1000 if len(row)>14 else 0}
                if len(out)>100: return out
            except Exception: continue
        if len(out)>100: break
    return out

@st.cache_data(ttl=14400)
def fetch_tpex_prices_all():
    out = {}
    try:
        r=requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",headers=HDR,timeout=20,verify=False)
        if r.status_code==200:
            for item in r.json():
                sid=str(item.get("SecuritiesCompanyCode","")).strip()
                if not sid or not sid.isdigit(): continue
                p=ff(str(item.get("Close","0")).replace(",",""))
                v=fi(str(item.get("TradingShares","0")).replace(",",""))//1000
                chg=ff(str(item.get("Change","0")).replace(",",""))
                prev=p-chg if p else None; cp=round(chg/prev*100,2) if prev and prev>0 else 0.0
                if p>0: out[sid]={"price":p,"volume":v,"chg_pct":cp,"name":str(item.get("CompanyName","")).strip()}
    except Exception: pass
    return out

@st.cache_data(ttl=14400)
def fetch_tpex_institution_all(qdate=""):
    out = {}
    for trade_date in last_trading_days(5):
        ds = trade_date.strftime("%Y/%m/%d")
        try:
            r=requests.get(f"https://www.tpex.org.tw/web/fund/tripleFund/index.php?l=zh-tw&o=json&d={ds}",headers=HDR,timeout=20,verify=False)
            if r.status_code!=200: continue
            d=r.json(); rows=d.get("aaData",d.get("data",[]))
            if not rows or len(rows)<5: continue
            for row in rows:
                if len(row)<7: continue
                sid=str(row[0]).strip()
                if not sid.isdigit(): continue
                out[sid]={"f":parse_tw(row[3])//1000,"t":parse_tw(row[6])//1000,
                           "d":parse_tw(row[18])//1000 if len(row)>18 else 0}
            if len(out)>50: return out
        except Exception: continue
    return out

# ── 個股 API ──────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def _api(dataset, sid, start, token):
    try:
        r=requests.get(FINMIND_API,headers=HDR,timeout=15,verify=False,
          params={"dataset":dataset,"data_id":sid,"start_date":start,"token":token})
        if r.status_code==200: return r.json().get("data",[])
    except Exception: pass
    return []

def get_price(sid, token):
    s = (date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows = _api("TaiwanStockPrice",sid,s,token)
    recs = [{"date":r.get("date","")[:10],"close":ff(r.get("close",0)),
             "high":ff(r.get("max",r.get("high",0))),"low":ff(r.get("min",r.get("low",0))),
             "vol":fi(r.get("Trading_Volume",0))//1000}
            for r in rows if ff(r.get("close",0))>0]
    recs.sort(key=lambda x:x["date"]); return recs

def get_inst(sid, token):
    s = (date.today()-timedelta(days=35)).strftime("%Y-%m-%d")
    rows = _api("TaiwanStockInstitutionalInvestorsBuySell",sid,s,token)
    dm = defaultdict(lambda:{"f":0,"t":0,"d":0})
    for r in rows:
        n2=str(r.get("name","")); net=fi(r.get("buy",0))-fi(r.get("sell",0)); d=r.get("date","")[:10]
        if "Foreign" in n2 or "外資" in n2: dm[d]["f"]+=net
        elif "Trust" in n2 or "投信" in n2: dm[d]["t"]+=net
        elif "Dealer" in n2 or "自營" in n2: dm[d]["d"]+=net
    return [{"date":d,"f":dm[d]["f"]//1000,"t":dm[d]["t"]//1000,"d":dm[d]["d"]//1000}
            for d in sorted(dm.keys())[-5:]]

def get_per(sid, token):
    s = (date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows = _api("TaiwanStockPER",sid,s,token)
    return [{"pe":ff(r.get("PER",0)),"pbr":ff(r.get("PBR",0))} for r in rows if ff(r.get("PER",0))>0][-250:]

def get_rev(sid, token):
    s = (date.today()-timedelta(days=450)).strftime("%Y-%m-%d")
    rows = _api("TaiwanStockMonthRevenue",sid,s,token)
    recs = [{"rev":ff(r.get("revenue",0)),"yr":fi(r.get("revenue_year",0)),"mo":fi(r.get("revenue_month",0))}
            for r in rows if ff(r.get("revenue",0))>0]
    recs.sort(key=lambda x:(x["yr"],x["mo"])); return recs[-13:]

def get_yahoo_target(sid):
    try:
        import yfinance as yf, pandas as _pd
    except ImportError: return None
    for suffix in [".TW",".TWO"]:
        try:
            info = yf.Ticker(f"{sid}{suffix}").info or {}
            if not info.get("regularMarketPrice"): continue
            mean = info.get("targetMeanPrice")
            if mean and not _pd.isna(mean) and float(mean)>0:
                count=info.get("numberOfAnalystOpinions"); hi=info.get("targetHighPrice"); lo=info.get("targetLowPrice")
                return {"target":round(float(mean),2),
                        "high":round(float(hi),2) if hi and not _pd.isna(hi) else None,
                        "low":round(float(lo),2) if lo and not _pd.isna(lo) else None,
                        "count":int(count) if count else 0,
                        "source":f"Yahoo共識（{int(count or 0)}位分析師）"}
        except Exception: continue
    return None

# ── 評分系統 v2.0 ─────────────────────────────────────────────

@st.cache_data(ttl=14400)
def get_finmind_target(sid: str, token: str):
    """
    從 FinMind TaiwanStockRecommend 取得法人目標價共識。
    4 小時快取，避免重複 API 呼叫。
    """
    if not token or not sid:
        return None
    try:
        start = (date.today() - timedelta(days=120)).strftime("%Y-%m-%d")
        r = requests.get(
            FINMIND_API,
            params={"dataset": "TaiwanStockRecommend",
                    "data_id": sid, "start_date": start, "token": token},
            headers=HDR, timeout=15, verify=False)
        if r.status_code != 200:
            return None
        data = r.json().get("data", [])
        if not data:
            return None
        targets = []
        for item in data:
            for key in ("target_price", "TargetPrice", "targetPrice", "target"):
                val = item.get(key)
                if val and float(val) > 0:
                    targets.append(float(val))
                    break
        if not targets:
            return None
        mean_tp = round(sum(targets) / len(targets), 0)
        return {
            "target": mean_tp,
            "high":   round(max(targets), 0),
            "low":    round(min(targets), 0),
            "count":  len(targets),
            "source": "FinMind法人共識（" + str(len(targets)) + "筆）",
        }
    except Exception as ex:
        print("【DEBUG】FinMind目標價失敗 " + sid + ": " + str(ex))
        return None

def get_web_target(sid: str):
    """
    從 Goodinfo / MoneydJ 網頁抓取分析師目標價。
    不需要 Token，每次即時抓取（已在 analyze 的檔案快取保護）。
    """
    web_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9",
        "Referer": "https://goodinfo.tw/",
    }
    # ── 嘗試 Goodinfo 券商評等/目標價 ─────────────────────────
    try:
        url = "https://goodinfo.tw/tw/StockBuySellFromBroker.aspx?STOCK_ID=" + sid
        r = requests.get(url, headers=web_headers, timeout=10, verify=False)
        if r.status_code == 200:
            text = r.text
            # 搜尋目標價數字（通常格式：目標價 XXX 元 或 Target XXX）
            patterns = [
                r"目標價[\s:：]*([0-9,]+(?:\.[0-9]+)?)",
                r"Target[\s:：]*([0-9,]+(?:\.[0-9]+)?)",
                r"TP[\s:：=]*([0-9,]+(?:\.[0-9]+)?)",
            ]
            found = []
            for pat in patterns:
                for m in re.finditer(pat, text):
                    val = float(m.group(1).replace(",", ""))
                    if 10 < val < 100000:
                        found.append(val)
            if found:
                mean_tp = round(sum(found) / len(found), 0)
                return {
                    "target": mean_tp,
                    "high":   round(max(found), 0),
                    "low":    round(min(found), 0),
                    "count":  len(found),
                    "source": "Goodinfo券商目標價（" + str(len(found)) + "筆）",
                }
    except Exception:
        pass
    # ── 嘗試 MoneydJ 股票分析 ──────────────────────────────────
    try:
        url = "https://www.moneydj.com/us/sta/staqad01.djhtm?A=" + sid
        r = requests.get(url, headers={**web_headers, "Referer": "https://www.moneydj.com/"},
                         timeout=10, verify=False)
        if r.status_code == 200:
            text = r.text
            patterns = [
                r"目標價[\s:：]*([0-9,]+(?:\.[0-9]+)?)",
                r"合理價[\s:：]*([0-9,]+(?:\.[0-9]+)?)",
            ]
            found = []
            for pat in patterns:
                for m in re.finditer(pat, text):
                    val = float(m.group(1).replace(",", ""))
                    if 10 < val < 100000:
                        found.append(val)
            if found:
                mean_tp = round(sum(found) / len(found), 0)
                return {
                    "target": mean_tp,
                    "high":   round(max(found), 0),
                    "low":    round(min(found), 0),
                    "count":  len(found),
                    "source": "MoneydJ目標價（" + str(len(found)) + "筆）",
                }
    except Exception:
        pass
    return None

def get_gemini_target(sid: str, name: str, price: float, gkey: str):
    """
    Gemini + Google Search 搜尋近期法人分析師目標價。
    回傳 target/high/low/source（含個別券商細節）與 details 列表。
    """
    if not gkey or not sid:
        return None
    try:
        from google import genai
        client = genai.Client(api_key=gkey)
        price_str = str(int(price))
        # 重點搜尋網站：鉅亨網、CMoney、富果直送、法說會記錄
        prompt = (
            "你是專業台灣股票研究助理，請用 Google Search 搜尋以下股票的"
            "最新法人分析師目標價（2025年或2026年資料）。\n"
            "股票：" + name + "（台股代號 " + sid + "），目前股價約 " + price_str + " 元。\n\n"
            "【第一步】請優先搜尋以下台灣財經網站的最新報導：\n"
            "- 鉅亨網 (anue.com.tw)：搜尋 \"" + name + " " + sid + " 目標價\"\n"
            "- CMoney (cmoney.tw)：搜尋 \"" + name + " 外資目標價 調升\"\n"
            "- 富果直送 Fugle (fugle.tw)：搜尋法說會記錄或目標價\n"
            "- 財報狗 (statementdog.com)：搜尋最新財報與法人預估\n"
            "- 經濟日報 (money.udn.com)：搜尋法說會展望或券商報告\n\n"
            "【第二步】搜尋以下券商對此股的研究報告與目標價：\n"
            "外資：大和資本(Daiwa)、大摩(Morgan Stanley)、高盛(Goldman Sachs)、"
            "花旗(Citi)、瑞銀(UBS)、麥格理(Macquarie)、巴克萊(Barclays)、"
            "匯豐(HSBC)、野村(Nomura)、JP摩根(JPMorgan)\n"
            "本土：元大、凱基、富邦、統一、永豐金、國泰、兆豐、玉山\n\n"
            "【重要規則】\n"
            "1. 優先使用 2025年 或 2026年 的最新資料（特別是法說會後調升）。\n"
            "2. 只取研究報告裡的「目標價/TP」，不要用現股價當目標價。\n"
            "3. 若法說會後有集體調升目標價，請標註日期。\n"
            "4. 若找到多筆，全部列出，並標明來源網站。\n"
            "5. 只回傳 JSON，不含 markdown、不含說明文字。\n\n"
            "JSON 格式範例（請完整填入）：\n"
            "{\n"
            "  \"results\": [\n"
            "    {\"broker\":\"大和資本(Daiwa)\",\"target\":422,\"rating\":\"買進\",\"date\":\"2026-05\"},\n"
            "    {\"broker\":\"摩根士丹利(Morgan Stanley)\",\"target\":390,\"rating\":\"買進\",\"date\":\"2026-05\"},\n"
            "    {\"broker\":\"元大\",\"target\":380,\"rating\":\"買進\",\"date\":\"2026-04\"}\n"
            "  ]\n"
            "}\n"
            "若搜尋後真的完全找不到任何目標價，才回傳 {\"results\": []}"
        )
        response = None
        try:
            from google.genai import types
            cfg = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())])
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt, config=cfg)
        except Exception:
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt)
        if not response or not getattr(response, "text", None):
            return None
        # 清除 markdown 格式
        text = re.sub(r"```[a-z]*", "", response.text)
        text = re.sub(r"```", "", text).strip()
        # 多重策略解析 JSON（應對 Gemini 各種回傳格式）
        data = None
        # 策略①：直接解析整段文字
        try:
            data = json.loads(text)
        except Exception:
            pass
        # 策略②：用堆疊法找最外層 JSON 物件（支援嵌套）
        if not data:
            try:
                stack = 0; start = -1
                for ci, ch in enumerate(text):
                    if ch == "{":
                        if stack == 0: start = ci
                        stack += 1
                    elif ch == "}":
                        stack -= 1
                        if stack == 0 and start >= 0:
                            data = json.loads(text[start:ci+1])
                            break
            except Exception:
                pass
        # 策略③：找所有 {...} 區塊逐一嘗試
        if not data:
            for mo in re.finditer(r"\{[^{}]+\}", text):
                try:
                    data = json.loads(mo.group())
                    if data: break
                except Exception:
                    continue
        if not data:
            print("【DEBUG】Gemini回傳無法解析JSON " + sid + ": " + text[:200])
            return None
        results = data.get("results", [])
        # 相容性：若頂層直接是目標價欄位（非 results 包裝）
        if not results and data.get("mean_target"):
            mean_raw = data.get("mean_target")
            if mean_raw and float(mean_raw) > 0:
                results = [{"broker": data.get("source","Gemini"),
                            "target": float(mean_raw),
                            "rating": "", "date": ""}]
        if not results:
            print("【DEBUG】Gemini結果 results 為空 " + sid)
            return None
        # 過濾合理目標價（不超過現價5倍、不低於1/5）
        valid = []
        for item in results:
            tp_val = item.get("target")
            if tp_val and float(tp_val) > 0:
                tp_f = float(tp_val)
                if price <= 0 or (tp_f <= price * 5 and tp_f >= price * 0.2):
                    valid.append(item)
        if not valid:
            print("【DEBUG】Gemini目標價全部不合理，捨棄 " + sid)
            return None
        targets = [float(v["target"]) for v in valid]
        mean_tp = round(sum(targets) / len(targets), 0)
        high_tp = round(max(targets), 0)
        low_tp  = round(min(targets), 0)
        # 組成可讀來源字串：「高盛 900元、花旗 850元」
        src_parts = []
        for v in valid:
            broker = v.get("broker", "未知")
            t_str  = str(int(float(v.get("target", 0)))) + "元"
            dt     = v.get("date", "")
            rating = v.get("rating", "")
            part   = broker + " " + t_str
            if rating:
                part += " (" + rating + ")"
            if dt:
                part += " [" + dt + "]"
            src_parts.append(part)
        source_str = "、".join(src_parts)
        return {
            "target":  mean_tp,
            "high":    high_tp,
            "low":     low_tp,
            "count":   len(valid),
            "source":  "Gemini搜尋 | " + source_str,
            "details": valid,
        }
    except Exception as ex:
        print("【DEBUG】Gemini目標價失敗 " + sid + ": " + str(ex))
        return None

def calc_quant_score(p, d5, d200, fc, tc, pe, pea, rev_yoy, tp,
                     tp_h=None, ma20=None, ma60=None, rev_mom=None, inst=None):
    sc=50; pos=[]; neg=[]; warn=[]
    # 技術面：d5 + 趨勢濾網
    if d5 is not None:
        if d5<-5:
            above_ma20=(p>=ma20) if (ma20 and ma20>0) else True
            above_ma60=(p>=ma60) if (ma60 and ma60>0) else True
            if above_ma20:   sc+=18; pos.append(f"5日線回測{d5:+.1f}%（守月線）")
            elif above_ma60: sc+=8;  pos.append(f"5日線回測{d5:+.1f}%（守季線）"); warn.append("跌破月線，謹慎操作")
            else:            sc-=5;  neg.append(f"5日乖離{d5:+.1f}%且跌破月線季線，接刀高風險")
        elif d5<=2: sc+=10; pos.append(f"5日乖離健康{d5:+.1f}%")
        elif d5<=8: sc+=2;  warn.append(f"5日乖離偏高{d5:+.1f}%")
        else:       sc-=10; neg.append(f"5日乖離過高{d5:+.1f}%，追高風險")
    if d200 and d200>80: sc-=5; warn.append(f"年線乖離偏高{d200:+.1f}%（成長股可接受，搭配基本面）")
    elif d200 and d200>50: sc-=2; warn.append(f"年線乖離稍高{d200:+.1f}%")
    # 目標價：以最高目標為基準，超均值不扣分
    ref_tp = tp_h if (tp_h and tp_h>0) else tp
    if ref_tp and p and ref_tp>0:
        up=(ref_tp-p)/p*100
        if   up>30: sc+=15; pos.append(f"距最高目標+{up:.1f}%，空間充裕")
        elif up>15: sc+=10; pos.append(f"距最高目標+{up:.1f}%")
        elif up>5:  sc+=5;  pos.append(f"距最高目標+{up:.1f}%")
        elif up>=0: sc+=2
        elif up>-20: warn.append(f"現價超最高目標{abs(up):.1f}%，估值偏高")
        else:        sc-=5;  neg.append(f"現價大幅超最高目標{abs(up):.1f}%")
    # 基本面：YoY + MoM
    mom_pos = (rev_mom is not None and rev_mom>0)
    if rev_yoy is not None:
        if   rev_yoy>=20: sc+=8; pos.append(f"月營收YoY+{rev_yoy:.1f}%（高成長）"); sc+=2 if mom_pos else 0
        elif rev_yoy>=5:  sc+=4; pos.append(f"月營收YoY+{rev_yoy:.1f}%"); sc+=1 if mom_pos else 0
        elif rev_yoy>=0:
            if mom_pos: sc+=2; pos.append(f"月營收持平，MoM+{rev_mom:.1f}%回升")
        elif rev_yoy>=-15:
            if mom_pos: sc+=1; warn.append(f"YoY{rev_yoy:.1f}%負，MoM+{rev_mom:.1f}%，可能庫存去化末段")
            else:       sc-=3; neg.append(f"月營收年減{rev_yoy:.1f}%")
        else:
            if mom_pos: sc-=4; neg.append(f"月營收重度衰退YoY{rev_yoy:.1f}%（MoM翻正，待觀察）")
            else:       sc-=8; neg.append(f"月營收大幅年減{rev_yoy:.1f}%")
    if pe and pea and pea>0:
        pv=(pe-pea)/pea*100
        if   pv<-20: sc+=8; pos.append(f"PE{pe:.1f}x低估")
        elif pv<0:   sc+=4
        elif pv>30:  sc-=5; warn.append(f"PE{pe:.1f}x偏高（較均值高{pv:.0f}%）")
    # 籌碼面：外資/投信 + 爆量否決
    f_veto=False; t_veto=False
    if inst and len(inst)>=2:
        f_vals=[abs(d.get("f",0)) for d in inst]; t_vals=[abs(d.get("t",0)) for d in inst]
        f5avg=sum(f_vals[:-1])/max(len(f_vals)-1,1); t5avg=sum(t_vals[:-1])/max(len(t_vals)-1,1)
        if inst[-1].get("f",0)<0 and f5avg>0 and abs(inst[-1]["f"])>f5avg*2:
            f_veto=True; warn.append(f"⚠️ 外資今日賣超{inst[-1]['f']:,}張超過近期均量2倍，疑假籌碼")
        if inst[-1].get("t",0)<0 and t5avg>0 and abs(inst[-1]["t"])>t5avg*2:
            t_veto=True; warn.append(f"⚠️ 投信今日賣超{inst[-1]['t']:,}張超過近期均量2倍，疑假籌碼")
    if f_veto:       sc-=8; neg.append("外資異常爆量出貨，否決連買加分")
    elif fc>=3:      sc+=12; pos.append(f"外資連買{fc}日")
    elif fc>=1:      sc+=5;  pos.append("外資今日買超")
    elif fc<=-3:     sc-=10; neg.append(f"外資連賣{abs(fc)}日")
    elif fc<0:       sc-=4;  warn.append("外資今日賣超")
    if t_veto:       sc-=8; neg.append("投信異常爆量出貨，否決連買加分")
    elif tc>=5:      sc+=12; pos.append(f"投信連買{tc}日（深度認養）")
    elif tc>=3:      sc+=8;  pos.append(f"投信連買{tc}日")
    elif tc>=1:      sc+=3;  pos.append("投信今日買超")
    elif tc<=-3:     sc-=10; neg.append(f"投信連賣{abs(tc)}日")
    elif tc<0:       sc-=4;  warn.append("投信今日賣超")
    if fc>0 and tc>0 and not f_veto and not t_veto: sc+=5; pos.append("外資投信同向買超")
    elif fc<0 and tc<0: sc-=8; neg.append("外資投信同向賣超")
    sc=max(0,min(100,sc))
    # 評等 + S 級防禦
    if sc>=80:
        inst_ok=(fc>0 and not f_veto) or (tc>0 and not t_veto)
        rev_ok=(rev_yoy is not None and rev_yoy>=0) or mom_pos
        if inst_ok or rev_ok: rt,lb="S","強烈推薦"
        else: rt,lb="A","建議買入"; warn.append("⚠️ 達S級分數但法人與營收均無正向支撐，保守評A")
    elif sc>=65: rt,lb="A","建議買入"
    elif sc>=45: rt,lb="B","觀　望"
    else:        rt,lb="C","避　開"
    return sc,rt,lb,pos,neg,warn

# ── 主分析函式 ────────────────────────────────────────────────
def analyze(sid, token, disposed, full_delivery, delisting, gemini_del, force=False):
    if not force:
        cached=load_cache(sid)
        if cached: return cached,None
    is_full_del=sid in full_delivery; is_delisting=sid in delisting or sid in gemini_del
    is_disposed=sid in disposed; is_hard_risk=is_full_del or is_delisting
    try:
        pr=get_price(sid,token)
        if not pr: return None,"無股價數據"
        cls=[r["close"] for r in pr]; last=pr[-1]; prev=pr[-2] if len(pr)>=2 else last
        p=last["close"]; chg=round((p-prev["close"])/prev["close"]*100,2) if prev["close"] else 0
        ma5=ma_n(cls,5); ma20=ma_n(cls,20); ma60=ma_n(cls,60); ma200=ma_n(cls,200)
        d5=dev_pct(p,ma5); d200=dev_pct(p,ma200)
        time.sleep(0.3)
        inst=get_inst(sid,token)
        fc=con_days([d["f"] for d in inst]); tc=con_days([d["t"] for d in inst]); dc=con_days([d["d"] for d in inst])
        time.sleep(0.3)
        per=get_per(sid,token)
        pe=per[-1]["pe"] if per else None; pea=round(sum(r["pe"] for r in per)/len(per),1) if per else None; pbr=per[-1]["pbr"] if per else None
        time.sleep(0.3)
        rev=get_rev(sid,token); rev_yoy=None; rev_mom=None
        if len(rev)>=13 and rev[-13]["rev"]>0: rev_yoy=round((rev[-1]["rev"]-rev[-13]["rev"])/rev[-13]["rev"]*100,1)
        if len(rev)>=2 and rev[-2]["rev"]>0:   rev_mom=round((rev[-1]["rev"]-rev[-2]["rev"])/rev[-2]["rev"]*100,1)
        tp=None; ts="未取得"; tp_h=None; tp_l=None; tp_n=0; _tp_details=[]
        # ── 目標價四段備援：Yahoo → FinMind → 網頁抓取 → Gemini → PE估算 ──
        ya = get_yahoo_target(sid)
        if ya:
            tp=ya["target"]; tp_h=ya["high"]; tp_l=ya["low"]; tp_n=ya["count"]; ts=ya["source"]
        else:
            # ① FinMind 法人共識（需要 Token）
            if token:
                fa = get_finmind_target(sid, token)
                if fa:
                    tp=fa["target"]; tp_h=fa["high"]; tp_l=fa["low"]; tp_n=fa["count"]; ts=fa["source"]
            # ② 網頁抓取（Goodinfo / MoneydJ，不需 Token）
            if not tp:
                wa = get_web_target(sid)
                if wa:
                    tp=wa["target"]; tp_h=wa["high"]; tp_l=wa["low"]; tp_n=wa["count"]; ts=wa["source"]
            # ③ Gemini 搜尋（需要 Gemini Key）
            if not tp:
                _gkey = st.session_state.get("gemini_key", "")
                if _gkey:
                    time.sleep(0.5)
                    ga = get_gemini_target(sid, nm(sid), p, _gkey)
                    if ga:
                        tp=ga["target"]; tp_h=ga["high"]; tp_l=ga["low"]; tp_n=ga["count"]; ts=ga["source"]
                    _tp_details=ga.get("details",[])
            # ④ PE均值×成長估算（最後備援）
            if not tp and pea and pe and rev_yoy is not None and pe>0:
                tp=round(p*(pea/pe)*min(max(1+rev_yoy/100,0.7),1.8),0); ts="PE均值×成長估算"
        sc,rt,lb,pos,neg,warn=calc_quant_score(p,d5,d200,fc,tc,pe,pea,rev_yoy,tp,
                                                tp_h=tp_h,ma20=ma20,ma60=ma60,rev_mom=rev_mom,inst=inst)
        r52=pr[-252:] if len(pr)>=252 else pr
        if r52:
            high_52w=max(ri["high"] for ri in r52)
            if high_52w>0 and p>0:
                dec=(high_52w-p)/high_52w*100
                if dec>=80:
                    is_hard_risk=True; is_delisting=True; sc=min(sc,20); rt="C"; lb="避　開"
                    neg.insert(0,f"🚨 52W高點{high_52w:,.0f}→現{p:,.0f}，跌幅{dec:.0f}%，疑似下市/地雷股")
        if is_hard_risk:
            rt="C"; lb="避　開"; sc=min(sc,20)
            if is_full_del: neg.insert(0,"🚨 全額交割股：強制C")
            if is_delisting and not any("52W" in n for n in neg): neg.insert(0,"⚠️ 下市警告：強制C")
        if is_disposed and not is_hard_risk:
            rev_strong=(rev_yoy is not None and rev_yoy>=10) or (rev_mom is not None and rev_mom>5)
            inst_strong=(fc>=3 or tc>=3)
            if rev_strong and inst_strong: sc=max(0,sc-3); warn.insert(0,"⏱ 處置股（強勢飆股，酌減-3）")
            else:
                sc=max(0,sc-10)
                if sc<45 and rt in ("S","A"): rt="B"; lb="觀　望"
                warn.insert(0,"⏱ 處置股：每5~20分鐘撮合，流動性受限")
        result={"sid":sid,"name":nm(sid),"price":p,"prev":prev["close"],"chg":chg,
                "ma5":ma5,"ma20":ma20,"ma60":ma60,"ma200":ma200,"d5":d5,"d200":d200,
                "h52":round(max(r["high"] for r in r52),2),"l52":round(min(r["low"] for r in r52),2),
                "vol":last["vol"],"last5":[r["close"] for r in pr[-5:]],
                "inst":inst,"fc":fc,"tc":tc,"dc":dc,
                "pe":pe,"pea":pea,"pbr":pbr,"rev_yoy":rev_yoy,"rev_mom":rev_mom,
                "tp":tp,"ts":ts,"tp_h":tp_h,"tp_l":tp_l,"tp_n":tp_n,
                "score":sc,"rating":rt,"label":lb,"pos":pos,"neg":neg,"warn":warn,
                "is_disposed":is_disposed,"is_full_del":is_full_del,
                "is_delisting":is_delisting,"is_hard_risk":is_hard_risk,"date":last["date"],"tp_details":_tp_details}
        save_cache(sid,result); return result,None
    except Exception as e: return None,str(e)

def ma_n(cls,n): return round(sum(cls[-n:])/n,2) if len(cls)>=n else None

WCSS="""*{box-sizing:border-box;margin:0;padding:0}body{background:#1a2332;font-family:'Helvetica Neue',Arial,sans-serif;padding:10px 6px;color:#e8eaf0}.wrap{max-width:660px;margin:0 auto}.hdr{background:#0f1724;border-radius:14px 14px 0 0;padding:16px 18px}.hdr h1{font-size:18px;color:#fff;font-weight:600}.hdr-sub{font-size:11px;color:#8fa3b8;margin-top:3px}.rc{width:60px;height:60px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0}.rc .lt{font-size:20px;font-weight:600;line-height:1}.rc .lb{font-size:8px;margin-top:2px}.tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}.tag{font-size:10px;padding:2px 7px;border-radius:99px;font-weight:500}.tag-g{background:#27ae6044;color:#4ecca3;border:1px solid #27ae6066}.tag-r{background:#e74c3c44;color:#ff8080;border:1px solid #e74c3c66}.tag-a{background:#f39c1244;color:#ffc107;border:1px solid #f39c1266}.tag-p{background:#8e44ad44;color:#c39bd3;border:1px solid #8e44ad66}.sbar{background:#2c3e50;border-left:4px solid #27ae60;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:2px;display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:8px}.sc p:first-child{font-size:10px;color:#8fa3b8;text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px}.sc p:last-child{font-size:16px;font-weight:700}.up{color:#4ecca3}.dn{color:#ff6b6b}.card{background:#2c3e50;border-radius:10px;padding:13px 15px;margin-bottom:8px;border:1px solid #3d5166}.ct{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:#8fa3b8;margin-bottom:8px}.row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #3d5166;font-size:13px;gap:8px}.row:last-child{border-bottom:none}.rl{color:#8fa3b8;flex-shrink:0}.rv{font-weight:500;text-align:right;color:#e8eaf0}.rbar{height:9px;border-radius:5px;background:linear-gradient(90deg,#e74c3c 0%,#f39c12 55%,#27ae60 82%);position:relative;margin:9px 0 2px}.rn{position:absolute;top:-3px;width:3px;height:15px;background:#fff;border-radius:2px}.rsc{display:flex;justify-content:space-between;font-size:10px;color:#8fa3b8}.rfg{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:7px}.rf{background:#1a2332;border-radius:6px;padding:6px 8px;border:1px solid #3d5166}.rf p:first-child{font-size:10px;color:#8fa3b8;margin-bottom:1px}.rf p:last-child{font-size:12px;font-weight:500;color:#e8eaf0}.cg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:8px 0}.chip{border-radius:7px;padding:8px;text-align:center;border:1px solid}.chip.buy{background:#1a3a27;border-color:#27ae60}.chip.sell{background:#3a1a1a;border-color:#e74c3c}.chip.neut{background:#2c3e50;border-color:#3d5166}.chip p:first-child{font-size:10px;color:#8fa3b8;margin-bottom:1px}.chip p:nth-child(2){font-size:14px;font-weight:600;margin-bottom:1px}.chip p:last-child{font-size:10px;color:#8fa3b8}.ev{display:flex;gap:8px;padding:7px 0;border-bottom:1px solid #3d5166;font-size:12px}.ev:last-child{border-bottom:none}.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:3px}.ev strong{display:block;font-size:12px;margin-bottom:1px;color:#e8eaf0}.ev span{color:#8fa3b8;line-height:1.5}.sg{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}.sb{background:#1a3a27;border-radius:7px;padding:8px 10px;font-size:11px;color:#4ecca3;border:1px solid #27ae60;line-height:1.6}.sr{background:#3a1a1a;border-radius:7px;padding:8px 10px;font-size:11px;color:#ff8080;border:1px solid #e74c3c;line-height:1.6}.st{display:flex;gap:8px;padding:6px 0;border-bottom:1px solid #3d5166;font-size:12px;align-items:flex-start;line-height:1.6;color:#e8eaf0}.st:last-child{border-bottom:none}.si{font-size:14px;flex-shrink:0}.bw{background:#3a2c0a;border-left:4px solid #ffc107;border-radius:0 6px 6px 0;padding:8px 11px;font-size:12px;color:#ffc107;margin-top:8px;line-height:1.6}.bd{background:#3a1a1a;border-left:4px solid #e74c3c;border-radius:0 6px 6px 0;padding:8px 11px;font-size:12px;color:#ff8080;margin-top:7px;line-height:1.6}.bo{background:#1a3a27;border-left:4px solid #27ae60;border-radius:0 6px 6px 0;padding:8px 11px;font-size:12px;color:#4ecca3;margin-top:7px;line-height:1.6}.hard-risk-banner{background:#3a0a0a;border:1px solid #e74c3c;border-radius:9px;padding:12px 15px;margin-bottom:9px}.hard-risk-banner strong{display:block;font-size:14px;color:#ff8080;margin-bottom:4px}.hard-risk-banner span{font-size:12px;color:#ffaaaa;line-height:1.6}.verdict{border-radius:9px;padding:11px 14px;border:1px solid}.vb{font-size:23px;font-weight:700}.tp-wrap{background:#1a2332;border-radius:5px;height:10px;position:relative;margin:6px 0 3px;overflow:hidden}.tp-fill{height:10px;border-radius:5px}.tp-lbl{display:flex;justify-content:space-between;font-size:10px;color:#8fa3b8}.inst-tbl{width:100%;border-collapse:collapse;font-size:11px;margin-top:7px}.inst-tbl th{background:#1a2332;color:#8fa3b8;padding:4px 6px;font-weight:600;border-bottom:1px solid #3d5166;text-align:right}.inst-tbl th:first-child{text-align:left}.inst-tbl td{padding:4px 6px;border-bottom:1px solid #3d5166;text-align:right;color:#e8eaf0}.inst-tbl td:first-child{text-align:left;color:#8fa3b8}.footer{background:#0f1724;border-radius:0 0 11px 11px;padding:10px 14px;font-size:10px;color:#8fa3b8;line-height:1.6;border-top:1px solid #3d5166}"""

def chip_html(label, net, con_d):
    cls="buy" if net>0 else ("sell" if net<0 else "neut")
    vc="up" if net>0 else ("dn" if net<0 else "")
    sign="+" if net>=0 else ""
    ct=(f"連買{con_d}日" if con_d>=2 else "今日買超" if con_d==1 else "今日中性" if con_d==0 else "今日賣超" if con_d==-1 else f"連賣{abs(con_d)}日")
    return f'<div class="chip {cls}"><p>{label}</p><p class="{vc}">{sign}{net:,}張</p><p>{ct}</p></div>'

def build_wiwynn(r):
    sid=r["sid"]; p=r["price"]; chg=r.get("chg",0) or 0
    d5=r.get("d5") or 0; d200=r.get("d200") or 0
    sc=r["score"]; rt=r["rating"]; lb=r["label"]
    fc=r["fc"]; tc=r["tc"]; dc=r["dc"]; ma5=r["ma5"]; ma20=r["ma20"]
    inst=r.get("inst",[]); tp=r.get("tp"); ts_=r.get("ts","")
    tp_h=r.get("tp_h"); tp_l=r.get("tp_l"); tp_n=r.get("tp_n",0)
    pe=r.get("pe"); pea=r.get("pea"); pbr=r.get("pbr")
    ry=r.get("rev_yoy"); rm=r.get("rev_mom")
    rc2=RC[rt]; lc=RL[rt]; sc2=RS[rt]; vbg=VBG[rt]; vbc=VBC[rt]; vtc=VTC[rt]
    bclr="#27ae60" if sc>=65 else ("#f39c12" if sc>=45 else "#e74c3c")
    cc2=ccc(chg); d5_cls="up" if d5<=3 else "dn"
    d200_cls="dn" if (d200 or 0)>80 else ""; d200_str=f"{d200:+.2f}%" if d200 else "N/A"
    tags=""
    if r.get("is_delisting"): tags+='<span class="tag tag-r">⚠️ 下市警告</span>'
    if r.get("is_full_del"):  tags+='<span class="tag tag-r">🚨 全額交割</span>'
    if r.get("is_disposed"):  tags+='<span class="tag tag-a">⏱ 處置股</span>'
    if tc>=5:    tags+=f'<span class="tag tag-g">投信連買{tc}日⭐</span>'
    elif tc>=1:  tags+=f'<span class="tag tag-g">投信買超</span>'
    elif tc<=-3: tags+=f'<span class="tag tag-r">投信連賣{abs(tc)}日</span>'
    if fc>=3:    tags+=f'<span class="tag tag-g">外資連買{fc}日</span>'
    elif fc<=-3: tags+=f'<span class="tag tag-r">外資連賣{abs(fc)}日</span>'
    elif fc<0:   tags+='<span class="tag tag-a">外資賣超</span>'
    if tp and tp_h and p:
        up2=(tp_h-p)/p*100
        if up2>10: tags+=f'<span class="tag tag-p">最高目標+{up2:.0f}%</span>'
    hard_banner=""
    if r.get("is_delisting"):   hard_banner='<div class="hard-risk-banner"><strong>⚠️ 下市警告：強制 C 評等</strong><span>面臨下市風險，禁止操作。</span></div>'
    elif r.get("is_full_del"):  hard_banner='<div class="hard-risk-banner"><strong>🚨 全額交割股：強制 C 評等</strong><span>流動性幾乎為零，嚴禁操作。</span></div>'
    ft=inst[-1]["f"] if inst else 0; tt=inst[-1]["t"] if inst else 0; dt=inst[-1]["d"] if inst else 0
    inst_rows=""
    for d2 in inst:
        ds=d2["date"][-5:].replace("-","/"); fv2=d2["f"]; tv=d2["t"]; dv=d2["d"]; to2=fv2+tv+dv
        inst_rows+=(f"<tr><td>{ds}</td><td class='{ccc(fv2)}'>{fv2:+,}</td>"
                    f"<td class='{ccc(tv)}'>{tv:+,}</td><td class='{ccc(dv)}'>{dv:+,}</td>"
                    f"<td class='{ccc(to2)}'><strong>{to2:+,}</strong></td></tr>")
    last5=r.get("last5",[p]); trend=""
    for i,c2 in enumerate(last5):
        dv2=round((c2-ma5)/ma5*100,1) if ma5 and ma5>0 else 0
        w=min(abs(dv2)*5,100); lbl2=f"T-{len(last5)-1-i}" if i<len(last5)-1 else "今日"
        vc2="#4ecca3" if dv2>=0 else "#ff6b6b"
        trend+=(f'<div style="display:flex;align-items:center;gap:5px;font-size:11px;margin-bottom:3px">'
                f'<span style="color:#8fa3b8;width:28px">{lbl2}</span>'
                f'<div style="flex:1;background:#1a2332;border-radius:3px;height:5px;overflow:hidden">'
                f'<div style="height:5px;border-radius:3px;background:{vc2};width:{w}%"></div></div>'
                f'<span style="color:{vc2};width:55px;text-align:right">{dv2:+.1f}%</span></div>')
    tp_card=""
    if tp and p:
        ref_tp=tp_h if (tp_h and tp_h>0) else tp
        up_to_high=(ref_tp-p)/p*100 if ref_tp and ref_tp>0 else 0
        up_to_avg=(tp-p)/p*100 if tp and tp>0 else 0
        exceed_high=up_to_high<0; exceed_avg=up_to_avg<0
        exc_cls="dn" if exceed_high else "up"
        bw2=min(p/ref_tp*100,100) if ref_tp and ref_tp>0 else 50
        fill_c="linear-gradient(90deg,#27ae60,#e74c3c)" if exceed_high else "linear-gradient(90deg,#27ae60,#4ecca3)"
        cb=(f'<span style="background:#1a2744;color:#7ec8e3;border:1px solid #2980b9;'
            f'font-size:10px;padding:1px 7px;border-radius:99px;margin-left:5px">👥{tp_n}位</span>') if tp_n>0 else ""
        _tp_hi=(f'<div class="row"><span class="rl">最高目標⭐</span>'
                f'<span class="rv up" style="font-weight:700">{tp_h:,.0f}元</span></div>') if tp_h else ""
        _tp_lo=(f'<div class="row"><span class="rl">最低目標</span>'
                f'<span class="rv">{tp_l:,.0f}元</span></div>') if tp_l else ""
        rng_bar=""
        if tp_h and tp_l and tp_h>tp_l:
            rng=tp_h-tp_l; cp3=min(max((p-tp_l)/rng*100,0),100); mp3=min(max((tp-tp_l)/rng*100,0),100)
            rng_bar=(f'<div style="margin-top:9px"><p style="font-size:10px;font-weight:600;color:#8fa3b8;margin-bottom:5px">'
                     f'分析師目標區間（⭐ 最高目標為評分基準）</p>'
                     f'<div style="position:relative;border-radius:5px;height:11px;margin-bottom:5px;'
                     f'background:linear-gradient(90deg,#27ae60 0%,#f39c12 55%,#e74c3c 100%)">'
                     f'<div style="position:absolute;left:{mp3:.0f}%;top:-4px;width:3px;height:19px;background:#5dade2;border-radius:2px;z-index:2"></div>'
                     f'<div style="position:absolute;left:{cp3:.0f}%;top:-4px;width:3px;height:19px;background:#fff;border-radius:2px;z-index:3"></div></div>'
                     f'<div style="display:flex;justify-content:space-between;font-size:10px">'
                     f'<span style="color:#27ae60">低 {tp_l:,.0f}</span>'
                     f'<span style="color:#5dade2">均 {tp:,.0f} | 現價 {p:,.0f}</span>'
                     f'<span style="color:#e67e22;font-weight:700">高⭐ {tp_h:,.0f}</span></div></div>')
        if exceed_high:
            upbox=f'<div class="bd" style="margin-top:7px">⚠️ 現價已超越最高分析師目標{abs(up_to_high):.1f}%</div>'
        elif exceed_avg:
            upbox=f'<div class="bw" style="margin-top:7px">🟡 現價超均值但距最高目標+{up_to_high:.1f}%</div>'
        else:
            upbox=f'<div class="bo" style="margin-top:7px">✅ 距最高分析師目標+{up_to_high:.1f}%，風險報酬比良好</div>'
        # ── 個別券商報告明細（Gemini 搜尋結果）────────────────
        # ── 個別券商報告明細（含完整防呆）────────────────────
        _raw_details = r.get('tp_details', None)
        tp_details = _raw_details if isinstance(_raw_details, list) else []
        detail_rows = ''
        if tp_details:
            detail_rows += '<div style="margin-top:9px;border-top:1px solid #3d5166;padding-top:8px">'
            detail_rows += '<p style="font-size:10px;font-weight:600;color:#8fa3b8;margin-bottom:6px">📋 各券商研究報告</p>'
            for d in tp_details:
                if not isinstance(d, dict):
                    continue
                try:
                    broker = str(d.get('broker') or '未知')
                    t_raw  = d.get('target', 0)
                    t_val  = float(t_raw) if t_raw else 0.0
                    rating = str(d.get('rating') or '')
                    dt     = str(d.get('date') or '')
                    t_clr  = '#4ecca3' if t_val >= p else '#ff6b6b'
                    rat_html = ('<span style="font-size:9px;background:#27ae6033;color:#4ecca3;'
                                'padding:1px 5px;border-radius:99px;margin-left:4px">' + rating + '</span>') if rating else ''
                    dt_html  = ('<span style="font-size:9px;color:#8fa3b8;margin-left:4px">' + dt + '</span>') if dt else ''
                    detail_rows += ('<div style="display:flex;justify-content:space-between;'
                                    'align-items:center;padding:4px 0;border-bottom:1px solid #2c3e50">'
                                    '<span style="font-size:11px;color:#e8eaf0">' + broker + rat_html + dt_html + '</span>'
                                    '<span style="font-size:12px;font-weight:700;color:' + t_clr + '">' + str(int(t_val)) + ' 元</span>'
                                    '</div>')
                except Exception:
                    continue
            detail_rows += '</div>'
        tp_card=(f'<div class="card"><p class="ct">💰 目標價分析{cb}</p>'
                 f'<div class="row"><span class="rl">來源</span><span class="rv" style="font-size:11px;color:#8fa3b8">{ts_}</span></div>'
                 f'<div class="row"><span class="rl">分析師均值</span><span class="rv {exc_cls}" style="font-size:15px;font-weight:700">{tp:,.0f} 元</span></div>'
                 +_tp_hi+_tp_lo+
                 f'<div class="row"><span class="rl">vs 現價（均值）</span><span class="rv" style="color:{"#ff6b6b" if exceed_avg else "#4ecca3"}">{up_to_avg:+.1f}%</span></div>'
                 f'<div class="row"><span class="rl">vs 現價（最高⭐）</span><span class="rv {exc_cls}"><strong>{up_to_high:+.1f}%</strong></span></div>'
                 +rng_bar+upbox+detail_rows+f'</div>')
    mc=ccc(rm or 0); yc=ccc(ry or 0)
    m_c=f"<div class='rf'><p>月營收MoM</p><p class='{mc}'>{(rm or 0):+.1f}%</p></div>" if rm is not None else ""
    y_c=f"<div class='rf'><p>月營收YoY</p><p class='{yc}'>{(ry or 0):+.1f}%</p></div>" if ry is not None else ""
    p_c=f"<div class='rf'><p>PE</p><p>{pe:.1f}x</p></div>" if pe else ""
    pa_c=f"<div class='rf'><p>年均PE</p><p>{pea:.1f}x</p></div>" if pea else ""
    pb_c=f"<div class='rf'><p>PBR</p><p>{pbr:.2f}x</p></div>" if pbr else ""
    val_card=(f"<div class='card'><p class='ct'>📊 估值指標</p><div class='rfg'>{p_c}{pa_c}{pb_c}{m_c}{y_c}</div></div>"
              if any([pe,pea,pbr,rm is not None,ry is not None]) else "")
    evs=[]
    if r.get("is_delisting"):   evs.append(("#e74c3c","⚠️ 下市警告","面臨下市風險，禁止操作"))
    elif r.get("is_full_del"):  evs.append(("#e74c3c","🚨 全額交割股","流動性幾乎為零，嚴禁操作"))
    elif r.get("is_disposed"):  evs.append(("#ffc107","⏱ 處置股","每5~20分鐘才撮合，流動性受限"))
    if fc>=3 and tc>=3:         evs.append(("#27ae60",f"外資+投信雙向認養（{fc}/{tc}日）","法人籌碼同向，中線多頭確立"))
    elif fc>=2:                 evs.append(("#27ae60",f"外資連買{fc}日","外資持續進場，籌碼支撐明確"))
    if tc>=5:                   evs.append(("#27ae60",f"投信深度認養（連買{tc}日）","機構長期建倉，中線信心強"))
    if d5<-5:                   evs.append(("#27ae60","回測5日線進場點",f"5日乖離{d5:+.1f}%，偏多技術訊號"))
    elif d5>10:                 evs.append(("#e74c3c","5日線乖離過高","追高風險，建議等回測"))
    if ry and ry>20:            evs.append(("#27ae60",f"月營收YoY+{ry:.1f}%","業績加速成長，基本面多頭"))
    if not evs:                 evs.append(("#8fa3b8","目前無特殊事件","維持當前追蹤策略"))
    ev_html="".join(f'<div class="ev"><div class="dot" style="background:{c}"></div><div><strong>{t}</strong><span>{d3}</span></div></div>' for c,t,d3 in evs[:4])
    stop=round(min(r.get("last5",[p]))*0.97,2)
    ea=(f"{p:,.0f}元（現位進場）" if d5<-3 else f"{(ma5 or p)*0.97:,.0f}元（回測5日線）" if d5<=3 else f"{(ma5 or p)*0.95:,.0f}元（等待回測）")
    tgt=(f"{tp:,.0f}元（{ts_}）") if tp else f"{p*1.10:,.0f}元（+10%估算）"
    risks=""
    if r.get("is_delisting"): risks+='<div class="bd">⚠️ <strong>下市警告：</strong>禁止操作！</div>'
    if r.get("is_full_del"):  risks+='<div class="bd">🚨 <strong>全額交割股：</strong>嚴禁操作！</div>'
    if r.get("is_disposed"):  risks+='<div class="bw">⏱ <strong>處置股：</strong>暫不操作，靜待出關。</div>'
    for n in r["neg"][:3]: risks+=f'<div class="bd">✗ {n}</div>'
    for w in r["warn"][:2]:risks+=f'<div class="bw">⚠ {w}</div>'
    if not risks: risks='<div class="bo">✅ 目前無重大風險警示。</div>'
    today_s=date.today().strftime("%Y/%m/%d"); chg_sign="+" if chg>=0 else ""
    pos_html=""
    if r["pos"]: pos_html="<span style='color:#4ecca3'>正：</span>"+"、".join(r["pos"][:2])+"<br>"
    neg_html=""
    if r["neg"]: neg_html="<span style='color:#ff6b6b'>負：</span>"+"、".join(r["neg"][:2])
    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{r['name']} {sid}</title><style>{WCSS}</style></head>
<body><div class="wrap">
<div class="hdr"><div style="display:flex;justify-content:space-between;align-items:flex-start">
<div><h1>{r['name']} <span style="font-size:13px;font-weight:400;color:#8fa3b8">{sid}</span></h1>
<p class="hdr-sub">{r.get('date',today_s)} | 收盤{p:,.2f}元 | 評分{sc}/100</p>
<div class="tags">{tags}</div></div>
<div class="rc" style="background:{rc2}"><span class="lt" style="color:{lc}">{rt}</span><span class="lb" style="color:{sc2}">{lb}</span></div>
</div></div>
<div class="sbar" style="border-left-color:{rc2}">
<div class="sc"><p>昨收</p><p>{r.get('prev',0):,.2f}元</p></div>
<div class="sc"><p>今收</p><p class="{cc2}">{p:,.2f}元</p></div>
<div class="sc"><p>漲跌</p><p class="{cc2}">{chg_sign}{chg:.2f}%</p></div>
<div class="sc"><p>MA5</p><p>{fv(ma5,'元',0)}</p></div>
</div>{hard_banner}
<div class="card"><p class="ct">📊 綜合決策評等（{sc}/100）</p>
<div class="verdict" style="background:{vbg};border-color:{vbc}">
<span class="vb" style="color:{vbc}">{rt}</span>
<span style="font-size:14px;font-weight:600;color:{vbc};margin-left:8px">{lb}</span>
<p style="margin-top:7px;font-size:12px;color:{vtc};line-height:1.7">{pos_html}{neg_html}</p>
</div>
<div class="bw" style="margin-top:9px">⚠ 升評：外資轉買2日+5日乖離收斂<br>⬇ 降評：外資連賣3日或跌破月線{fv(ma20,'元',0)}</div>
</div>
<div class="card"><p class="ct">🔍 技術面</p>
<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:9px">
<div><p style="font-size:32px;font-weight:700;color:{bclr};line-height:1">{sc}</p>
<p style="font-size:11px;color:{bclr}">{"🟢低度" if sc>=65 else "🟡中度" if sc>=45 else "🔴高度"}風險</p></div>
<div style="flex:1;min-width:160px">
<div class="row"><span class="rl">5日線乖離</span><span class="rv {d5_cls}"><strong>{d5:+.2f}%</strong></span></div>
<div class="row"><span class="rl">月線乖離</span><span class="rv">{f"{dev_pct(p,ma20):+.2f}%" if ma20 else "N/A"}</span></div>
<div class="row"><span class="rl">年線乖離</span><span class="rv {d200_cls}">{d200_str}</span></div>
<div class="row"><span class="rl">52W高/低</span><span class="rv">{fv(r.get('h52'),'',0)}/{fv(r.get('l52'),'',0)}</span></div>
</div></div>
<div style="background:#1a2332;border-radius:7px;padding:9px;border:1px solid #3d5166;margin-bottom:9px">
<p style="font-size:10px;font-weight:600;color:#8fa3b8;margin-bottom:7px">5日線乖離趨勢</p>{trend}
</div>
<div class="rbar"><div class="rn" style="left:{min(sc,99)}%"></div></div>
<div class="rsc"><span>0極危</span><span>50中性</span><span>80安全</span><span>100</span></div>
<div class="rfg">
<div class="rf"><p>MA20</p><p>{fv(ma20,'元',0)}</p></div>
<div class="rf"><p>MA60</p><p>{fv(r.get('ma60'),'元',0)}</p></div>
<div class="rf"><p>MA200</p><p>{fv(r.get('ma200'),'元',0)}</p></div>
<div class="rf"><p>成交量</p><p>{r.get('vol',0):,}張</p></div>
</div></div>
<div class="card"><p class="ct">💼 籌碼面</p>
<div class="cg">{chip_html("外資",ft,fc)}{chip_html("投信",tt,tc)}{chip_html("自營商",dt,dc)}</div>
{"<div class='bo'>✅ 外資投信同向買超</div>" if fc>0 and tc>0 else ""}
{"<div class='bd'>✗ 外資投信同向賣超</div>" if fc<0 and tc<0 else ""}
{"<div class='bw'>⚠ 外資投信方向分歧</div>" if (fc>0 and tc<0) or (fc<0 and tc>0) else ""}
<table class="inst-tbl"><tr><th>日期</th><th>外資</th><th>投信</th><th>自營</th><th>合計</th></tr>{inst_rows}</table>
</div>
{tp_card}{val_card}
<div class="card"><p class="ct">📅 事件更新</p>{ev_html}</div>
<div class="card"><p class="ct">🎯 操作策略</p>
<div class="st"><span class="si">🟢</span><div><strong>積極進場：</strong>{ea}</div></div>
<div class="st"><span class="si">🟡</span><div><strong>保守進場：</strong>{fv(ma20,'元',0)}（月線支撐）</div></div>
<div class="st"><span class="si">🔴</span><div><strong>短線停損：</strong>{stop:,.0f}元</div></div>
<div class="st"><span class="si">🎯</span><div><strong>目標：</strong>{tgt}</div></div>
<div class="sg"><div class="sb"><strong>📈 多頭</strong><br>法人持續買超+技術強勢</div>
<div class="sr"><strong>📉 空頭</strong><br>外資連賣+跌破月線</div></div></div>
<div class="card"><p class="ct">⚠️ 風險提示</p>{risks}</div>
<div class="footer">{r['name']}（{sid}）| {r.get('date',today_s)} | 評分{sc}/100（純量化v2.0）| {ts_}<br>數據：FinMind API | 僅供參考，不構成投資建議</div>
</div></body></html>"""

def build_full_html(results):
    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    nav="".join(
        f'<a href="#s{r["sid"]}" style="display:inline-block;font-size:11px;padding:3px 9px;'
        f'border-radius:14px;font-weight:600;text-decoration:none;margin:2px;'
        f'background:{RC[r["rating"]]};color:white">{r["name"]}</a>'
        for r in sorted(results,key=lambda x:x["score"],reverse=True))
    cards=""
    for r in sorted(results,key=lambda x:(x.get("is_disposed",False),-x["score"])):
        inner=build_wiwynn(r); s=inner.find("<body>")+6; e=inner.find("</body>")
        cards+=f'<div id="s{r["sid"]}" style="scroll-margin-top:55px">{inner[s:e]}</div>'
    today_s=date.today().strftime("%Y/%m/%d %H:%M")
    return (f'<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>台股分析 {today_s}</title><style>{WCSS}</style></head><body>'
            f'<div class="wrap"><div style="background:#0f1724;border-radius:10px;padding:9px 13px;margin-bottom:10px;position:sticky;top:0;z-index:99">'
            f'<div style="font-size:10px;color:#8fa3b8;margin-bottom:4px">📊 台股分析 {today_s} | S:{cnts["S"]} A:{cnts["A"]} B:{cnts["B"]} C:{cnts["C"]}</div>'
            f'{nav}</div>{cards}</div></body></html>')

# ── 籌碼掃描：産業分析 ────────────────────────────────────────
def compute_sector_stats(prices: dict, insts: dict,
                          hard_risk: set, sector_mapping: dict) -> list:
    """
    依官方產業分類動態分群，統計各產業漲跌、成交量、法人買賣。
    sector_mapping：{ "股號": "官方產業名稱" }（from fetch_official_sectors()）
    查無分類的股票一律歸入「其他」，確保全市場覆蓋。
    """
    from collections import defaultdict as _dd

    total_vol = sum(p.get("volume", 0) or 0 for p in prices.values()) or 1
    bucket: dict = _dd(list)

    # ── 動態分群：遍歷所有有報價的股票 ───────────────────────
    for code, p in prices.items():
        if code in hard_risk:
            continue
        if not p or p.get("price", 0) <= 0:
            continue
        sector = sector_mapping.get(code, "") or "其他"
        inst = insts.get(code, {})
        bucket[sector].append({
            "code":  code,
            "name":  nm(code),
            "price": p["price"],
            "chg":   p.get("chg_pct", 0) or 0,
            "vol":   p.get("volume",  0) or 0,
            "f":     inst.get("f", 0) or 0,
            "t":     inst.get("t", 0) or 0,
        })

    # ── 彙整統計 ─────────────────────────────────────────────
    stats = []
    for sec_name, stocks in bucket.items():
        if not stocks:
            continue
        total_v  = sum(s["vol"] for s in stocks)
        avg_chg  = round(sum(s["chg"] for s in stocks) / len(stocks), 2)
        net_inst = sum(s["f"] + s["t"] for s in stocks)
        up  = sum(1 for s in stocks if s["chg"] > 0)
        dn  = sum(1 for s in stocks if s["chg"] < 0)
        stats.append({
            "name":      sec_name,
            "desc":      f"{len(stocks)} 支成份股",
            "count":     len(stocks),
            "avg_chg":   avg_chg,
            "total_vol": total_v,
            "weight":    round(total_v / total_vol * 100, 2),
            "net_inst":  net_inst,
            "up":        up,
            "dn":        dn,
            "stocks":    sorted(stocks, key=lambda x: x["chg"], reverse=True),
        })

    return stats

def build_treemap_html(stocks, title):
    """
    專業熱力圖：Squarify 演算法 + Top20/其他合併 + 成交值/量切換。
    台股慣例：🔴漲 🟢跌。只動此函式，其他程式碼不變。
    """
    if not stocks:
        return "<body style='background:#1a2332;color:#e8eaf0;padding:20px'>無數據</body>"

    js_data = json.dumps([{
        "name":  s.get("name", s.get("code", "")),
        "code":  s.get("code", ""),
        "price": s.get("price", 0),
        "chg":   round(s.get("chg", 0), 2),
        "vol":   max(s.get("vol", 1), 1),
    } for s in stocks], ensure_ascii=False)

    title_esc = title.replace('"', '&quot;')

    CSS = (
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{background:#1a2332;font-family:'Helvetica Neue',Arial,sans-serif}"
        "#hdr{display:flex;align-items:center;gap:8px;padding:8px 12px;"
        "     flex-wrap:wrap;border-bottom:1px solid #2c3e50}"
        "#ti{color:#e8eaf0;font-size:13px;font-weight:700;flex-shrink:0}"
        ".tb{background:#2c3e50;border:1px solid #3d5166;color:#8fa3b8;"
        "    padding:3px 13px;border-radius:99px;cursor:pointer;font-size:12px;transition:all .15s}"
        ".tb.on{background:#27ae60;border-color:#27ae60;color:#fff;font-weight:600}"
        "#hint{font-size:11px;color:#8fa3b8;margin-left:auto}"
        "#tm{position:relative;width:100%;height:450px;overflow:hidden;background:#1a2332}"
        ".c{position:absolute;display:flex;flex-direction:column;align-items:center;"
        "   justify-content:center;border:1px solid #1a2332;border-radius:3px;"
        "   overflow:hidden;cursor:default;transition:opacity .12s}"
        ".c:hover{opacity:.82;z-index:10}"
        ".c .cn{font-size:12px;font-weight:700;color:#fff;"
        "       text-shadow:1px 1px 2px rgba(0,0,0,.9);"
        "       white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:94%}"
        ".c .cp{font-size:11px;color:#fff;text-shadow:1px 1px 2px rgba(0,0,0,.9)}"
        ".c .cx{font-size:10px;color:rgba(255,255,255,.72)}"
        ".lg{display:flex;flex-direction:column;align-items:center;padding:5px 0}"
        ".lb{width:280px;height:10px;border-radius:6px;"
        "    background:linear-gradient(90deg,#145a32,#27ae60,#2d3436,#e74c3c,#8b0000)}"
        ".ll{display:flex;justify-content:space-between;width:280px;"
        "    font-size:10px;color:#8fa3b8;margin-top:2px}"
    )

    # JS 以字串拼接，避免 Python f-string 與 JS 大括號衝突
    JS = (
        "const RAW=" + js_data + ";\n"
        "let MODE='amt';\n"
        "const DATA=RAW.map(d=>Object.assign({},d,{amt:Math.round(d.price*d.vol)}));\n"
        "\n"
        "function getColor(c){\n"
        "  if(c>=9)return'#8b0000';\n"
        "  if(c>=6)return'#c0392b';\n"
        "  if(c>=3)return'#e74c3c';\n"
        "  if(c>=1)return'#ff6b6b';\n"
        "  if(c>0) return'#ff9999';\n"
        "  if(c===0)return'#2d3436';\n"
        "  if(c>-1)return'#aaffaa';\n"
        "  if(c>-3)return'#55efc4';\n"
        "  if(c>-6)return'#27ae60';\n"
        "  if(c>-9)return'#1e8449';\n"
        "  return'#145a32';\n"
        "}\n"
        "\n"
        "// ── Top20 + 其他合併 ────────────────────────────────\n"
        "function getTop20(items,wk){\n"
        "  const sorted=[...items].sort((a,b)=>b[wk]-a[wk]);\n"
        "  const top=sorted.slice(0,20);\n"
        "  const rest=sorted.slice(20);\n"
        "  if(rest.length>0){\n"
        "    const totalW=rest.reduce((s,d)=>s+d[wk],0)||1;\n"
        "    const avgChg=rest.reduce((s,d)=>s+d.chg*d[wk],0)/totalW;\n"
        "    top.push({name:'其他',code:'OTHER',price:0,chg:avgChg,\n"
        "      vol:rest.reduce((s,d)=>s+d.vol,0),\n"
        "      amt:rest.reduce((s,d)=>s+d.amt,0),isOther:true});\n"
        "  }\n"
        "  return top;\n"
        "}\n"
        "\n"
        "// ── Squarify 演算法（防麵條方塊） ───────────────────\n"
        "function worstAR(row,rowSum,shortSide){\n"
        "  const rowLen=rowSum/shortSide;\n"
        "  let worst=0;\n"
        "  for(const d of row){\n"
        "    const item=rowSum>0?(d.sw/rowSum)*shortSide:0;\n"
        "    if(item<=0)continue;\n"
        "    const ar=Math.max(rowLen/item,item/rowLen);\n"
        "    if(ar>worst)worst=ar;\n"
        "  }\n"
        "  return worst;\n"
        "}\n"
        "\n"
        "function squarify(items,x,y,w,h){\n"
        "  const nodes=[];\n"
        "  if(!items.length||w<1||h<1)return nodes;\n"
        "  let rem=[...items],rx=x,ry=y,rw=w,rh=h;\n"
        "  while(rem.length>0&&rw>0.5&&rh>0.5){\n"
        "    const isVert=rw>=rh;\n"
        "    const shortSide=Math.min(rw,rh);\n"
        "    let row=[rem[0]],rowSum=rem[0].sw;\n"
        "    for(let i=1;i<rem.length;i++){\n"
        "      const d=rem[i];\n"
        "      const newSum=rowSum+d.sw;\n"
        "      const curr=worstAR(row,rowSum,shortSide);\n"
        "      const next=worstAR([...row,d],newSum,shortSide);\n"
        "      if(next<=curr){row.push(d);rowSum=newSum;}\n"
        "      else break;\n"
        "    }\n"
        "    const rowLen=rowSum/shortSide;\n"
        "    let off=isVert?ry:rx;\n"
        "    for(const d of row){\n"
        "      const frac=d.sw/rowSum;\n"
        "      const cs=frac*shortSide;\n"
        "      if(isVert)\n"
        "        nodes.push(Object.assign({},d,{x:rx,y:off,w:rowLen,h:cs}));\n"
        "      else\n"
        "        nodes.push(Object.assign({},d,{x:off,y:ry,w:cs,h:rowLen}));\n"
        "      off+=cs;\n"
        "    }\n"
        "    rem=rem.slice(row.length);\n"
        "    if(isVert){rx+=rowLen;rw-=rowLen;}\n"
        "    else{ry+=rowLen;rh-=rowLen;}\n"
        "  }\n"
        "  return nodes;\n"
        "}\n"
        "\n"
        "// ── 渲染 ─────────────────────────────────────────────\n"
        "function render(){\n"
        "  const ct=document.getElementById('tm');\n"
        "  const W=ct.offsetWidth||800,H=450;\n"
        "  const top=getTop20(DATA,MODE);\n"
        "  const totalW=top.reduce((s,d)=>s+d[MODE],0)||1;\n"
        "  const scale=(W*H)/totalW;\n"
        "  const scaled=top.map(d=>Object.assign({},d,{sw:d[MODE]*scale}));\n"
        "  const cells=squarify(scaled,0,0,W,H);\n"
        "  ct.innerHTML='';\n"
        "  cells.forEach(function(c){\n"
        "    if(c.w<1||c.h<1)return;\n"
        "    const div=document.createElement('div');\n"
        "    div.className='c';\n"
        "    const bg=c.isOther?'#2d3436':getColor(c.chg);\n"
        "    div.style.left=Math.round(c.x+0.5)+'px';\n"
        "    div.style.top=Math.round(c.y+0.5)+'px';\n"
        "    div.style.width=Math.max(Math.round(c.w-1),1)+'px';\n"
        "    div.style.height=Math.max(Math.round(c.h-1),1)+'px';\n"
        "    div.style.background=bg;\n"
        "    const sign=c.chg>=0?'+':'';\n"
        "    div.title=c.name+' '+c.code+'\\n'+c.price+'元 '+sign+c.chg.toFixed(2)+'%';\n"
        "    if(c.w>38&&c.h>26){\n"
        "      let inner='';\n"
        "      if(c.w>56&&c.h>42)inner+='<div class=\"cn\">'+c.name+'</div>';\n"
        "      inner+='<div class=\"cp\">'+sign+c.chg.toFixed(1)+'%</div>';\n"
        "      if(c.h>58&&c.price)inner+='<div class=\"cx\">'+c.price+'元</div>';\n"
        "      div.innerHTML=inner;\n"
        "    }\n"
        "    ct.appendChild(div);\n"
        "  });\n"
        "}\n"
        "\n"
        "function sw(m){\n"
        "  MODE=m;\n"
        "  document.getElementById('b-amt').className='tb'+(m==='amt'?' on':'');\n"
        "  document.getElementById('b-vol').className='tb'+(m==='vol'?' on':'');\n"
        "  document.getElementById('hint').textContent=\n"
        "    m==='amt'?'方塊大小=成交值，\U0001f534漲\U0001f7e2跌':'方塊大小=成交量，\U0001f534漲\U0001f7e2跌';\n"
        "  render();\n"
        "}\n"
        "\n"
        "render();\n"
        "window.addEventListener('resize',render);\n"
    )

    return (
        "<!DOCTYPE html><html lang=\"zh-TW\"><head>"
        "<meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<style>" + CSS + "</style></head><body>"
        "<div id=\"hdr\">"
        "  <div id=\"ti\">\U0001f321\ufe0f " + title_esc + "</div>"
        "  <button class=\"tb on\" id=\"b-amt\" onclick=\"sw('amt')\">成交值</button>"
        "  <button class=\"tb\" id=\"b-vol\" onclick=\"sw('vol')\">成交量</button>"
        "  <span id=\"hint\">方塊大小=成交值，\U0001f534漲\U0001f7e2跌</span>"
        "</div>"
        "<div id=\"tm\"></div>"
        "<div class=\"lg\">"
        "  <div class=\"lb\"></div>"
        "  <div class=\"ll\">"
        "    <span>-10%+</span><span>-5%</span><span>平盤</span>"
        "    <span>+5%</span><span>+10%+</span>"
        "  </div>"
        "</div>"
        "<script>" + JS + "</script>"
        "</body></html>"
    )


def tab_scanner():
    st.markdown("### 📡 籌碼掃描 — 產業透視")
    c_r,c_b=st.columns([3,1])
    with c_r:
        if st.button("🔄 重新整理全市場數據",use_container_width=True,key="scn_refresh"):
            for fn in [fetch_twse_prices_all, fetch_twse_institution_all,
                       fetch_tpex_prices_all,  fetch_tpex_institution_all,
                       fetch_disposed_cached,  fetch_full_delivery_cached,
                       fetch_delisting_cached, fetch_official_sectors]:
                fn.clear()
            st.session_state.gemini_delisting=set(); st.session_state.gemini_delisting_ts=None
            st.session_state.scanner_sector=None; st.rerun()
    with c_b:
        if st.session_state.get("scanner_sector"):
            if st.button("⬅ 返回列表",use_container_width=True,key="scn_back"):
                st.session_state.scanner_sector=None; st.rerun()
    qdate=get_inst_date_str()
    with st.spinner("📡 取得全市場數據 + 官方產業分類..."):
        twse_p = fetch_twse_prices_all()
        tpex_p = fetch_tpex_prices_all()
        prices = {**twse_p, **tpex_p}
        update_market_names(prices)
        twse_i = fetch_twse_institution_all(qdate)
        tpex_i = fetch_tpex_institution_all(qdate)
        insts  = {**twse_i, **tpex_i}
        disposed  = fetch_disposed_cached()
        full_del  = fetch_full_delivery_cached()
        delist    = fetch_delisting_cached()
        hard_risk = full_del | delist | st.session_state.gemini_delisting
        # ── 官方產業分類（24 小時快取，幾乎不消耗時間）────────
        token = st.session_state.get("token", "")
        sector_mapping = fetch_official_sectors(token)
    gkey=st.session_state.gemini_key
    if gkey:
        with st.spinner("🤖 偵測下市風險股..."):
            g_del=gemini_fetch_delisting(gkey)
        if g_del: st.warning(f"🤖 Gemini 偵測 {len(g_del)} 支下市風險股：{', '.join(sorted(g_del)[:8])}")
        hard_risk=hard_risk|g_del
    now_tw=datetime.utcnow()+timedelta(hours=8)
    inst_date=get_institution_query_date_str() if False else (now_tw.date()-timedelta(days=1) if now_tw.hour<17 else now_tw.date())
    time_note="（昨日盤後）" if now_tw.hour<17 else "（今日盤後）"
    inst_note=f"法人：{len(insts)} 檔" if insts else "法人：今日未取得"
    sec_note = f"產業：{len(sector_mapping)} 種官方分類" if sector_mapping else "產業分類：載入中"
    st.caption(f"股價：{len(prices)} 檔 | {inst_note} | {sec_note} | {time_note}")
    if not prices: st.error("⚠️ 無法取得股價數據"); return
    if not sector_mapping:
        st.warning("⚠️ 無法取得產業分類資料，請確認網路或 FinMind Token 設定，稍後再試。")

    stats = compute_sector_stats(prices, insts, hard_risk, sector_mapping)
    if not st.session_state.get("scanner_sector"):
        # ── 第一層：強勢/弱勢概覽 ─────────────────────────────
        sorted_desc=sorted(stats,key=lambda x:x["avg_chg"],reverse=True)
        sorted_asc=sorted(stats,key=lambda x:x["avg_chg"])
        st.markdown("#### 📊 今日產業透視總覽")
        c_l,c_r=st.columns(2)
        with c_l:
            st.markdown("**🔴 強勢族群（漲幅前5）**")
            for s in sorted_desc[:5]:
                chg=s["avg_chg"]; bar_w=min(int(abs(chg)/10*100),100)
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">'
                    f'<span style="width:75px;font-size:12px;color:#e8eaf0;font-weight:600">{s["name"][:6]}</span>'
                    f'<div style="flex:1;background:#2c3e50;border-radius:3px;height:18px;position:relative">'
                    f'<div style="width:{bar_w}%;height:100%;background:#e74c3c;border-radius:3px"></div>'
                    f'<span style="position:absolute;right:4px;top:1px;font-size:11px;color:#fff;font-weight:700">+{chg:.2f}%</span></div>'
                    f'<span style="font-size:10px;color:#8fa3b8;width:38px;text-align:right">{s["weight"]:.1f}%</span>'
                    f'</div>',unsafe_allow_html=True)
        with c_r:
            st.markdown("**🟢 弱勢族群（跌幅前5）**")
            for s in sorted_asc[:5]:
                chg=s["avg_chg"]; bar_w=min(int(abs(chg)/10*100),100)
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">'
                    f'<span style="width:75px;font-size:12px;color:#e8eaf0;font-weight:600">{s["name"][:6]}</span>'
                    f'<div style="flex:1;background:#2c3e50;border-radius:3px;height:18px;position:relative">'
                    f'<div style="width:{bar_w}%;height:100%;background:#27ae60;border-radius:3px"></div>'
                    f'<span style="position:absolute;right:4px;top:1px;font-size:11px;color:#fff;font-weight:700">{chg:.2f}%</span></div>'
                    f'<span style="font-size:10px;color:#8fa3b8;width:38px;text-align:right">{s["weight"]:.1f}%</span>'
                    f'</div>',unsafe_allow_html=True)
        st.markdown("---")
        # ── 第二層：完整清單 + 排序 ───────────────────────────
        st.markdown("#### 📋 所有產業詳細清單")
        sort_k=st.radio("排序方式",["漲幅","跌幅","成交比重","法人買超"],horizontal=True,label_visibility="collapsed",key="scn_sort")
        sk_map={"漲幅":lambda x:-x["avg_chg"],"跌幅":lambda x:x["avg_chg"],"成交比重":lambda x:-x["weight"],"法人買超":lambda x:-x["net_inst"]}
        for s in sorted(stats,key=sk_map[sort_k]):
            chg=s["avg_chg"]; chg_c="#e74c3c" if chg>0 else ("#27ae60" if chg<0 else "#8fa3b8")
            chg_sign="+" if chg>=0 else ""
            bar_w=min(int(abs(chg)/10*100),100)
            inst_c="#e74c3c" if s["net_inst"]>0 else ("#27ae60" if s["net_inst"]<0 else "#8fa3b8")
            c1,c2,c3=st.columns([3,4,1])
            with c1:
                st.markdown(f'<div style="font-size:13px;font-weight:700;color:#e8eaf0">{s["name"]}</div>'
                            f'<div style="font-size:10px;color:#8fa3b8">{s["desc"]} | ↑{s["up"]} ↓{s["dn"]} 共{s["count"]}支</div>',
                            unsafe_allow_html=True)
            with c2:
                st.markdown(
                    f'<div style="margin-bottom:3px"><span style="color:{chg_c};font-weight:700;font-size:14px">{chg_sign}{chg:.2f}%</span>'
                    f'<span style="color:#8fa3b8;font-size:10px;margin-left:8px">成交比重 {s["weight"]:.1f}%</span></div>'
                    f'<div style="background:#2c3e50;border-radius:3px;height:6px">'
                    f'<div style="width:{bar_w}%;height:6px;background:{chg_c};border-radius:3px"></div></div>',
                    unsafe_allow_html=True)
            with c3:
                st.markdown(f'<div style="font-size:11px;color:{inst_c};text-align:right">{s["net_inst"]:+,}</div>'
                            f'<div style="font-size:9px;color:#8fa3b8;text-align:right">法人張</div>',
                            unsafe_allow_html=True)
                if st.button("→",key=f"into_{s['name']}",help=f"查看{s['name']}個股"):
                    st.session_state.scanner_sector=s["name"]; st.rerun()
            st.divider()
    else:
        # ── 第三層 + 第四層：個股清單 + 熱力圖 ───────────────
        sec_name=st.session_state.scanner_sector
        s_data=next((s for s in stats if s["name"]==sec_name),None)
        if not s_data: st.warning(f"找不到 {sec_name} 的數據"); return
        c_b2,c_t2=st.columns([1,5])
        with c_b2:
            if st.button("⬅ 返回",use_container_width=True,key="scn_back2"):
                st.session_state.scanner_sector=None; st.rerun()
        with c_t2:
            chg=s_data["avg_chg"]; chg_c="#e74c3c" if chg>0 else "#27ae60"
            sign="+" if chg>=0 else ""
            st.markdown(f"### {sec_name}")
            st.markdown(f'<span style="color:{chg_c};font-size:18px;font-weight:700">{sign}{chg:.2f}%</span>'
                        f'<span style="color:#8fa3b8;font-size:12px;margin-left:8px">'
                        f'共{s_data["count"]}支 ↑{s_data["up"]} ↓{s_data["dn"]} 法人{s_data["net_inst"]:+,}張</span>',
                        unsafe_allow_html=True)
        tab_list,tab_heat=st.tabs(["📋 清單模式","🌡️ 熱力圖"])
        with tab_list:
            rows=[{"代號":s["code"],"名稱":s["name"],"收盤(元)":s["price"],
                   "漲跌%":round(s["chg"],2),"總量(張)":s["vol"],"外資(張)":s["f"],"投信(張)":s["t"],"法人合計":s["f"]+s["t"]}
                  for s in s_data["stocks"]]
            if rows:
                rows.sort(key=lambda x:x["漲跌%"],reverse=True)
                st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
                avg_chg2=round(sum(r["漲跌%"] for r in rows)/len(rows),2)
                up_cnt=sum(1 for r in rows if r["漲跌%"]>0)
                cc1,cc2,cc3=st.columns(3)
                cc1.metric("平均漲跌",f"{'+' if avg_chg2>=0 else ''}{avg_chg2:.1f}%")
                cc2.metric("法人合計",f"{s_data['net_inst']:+,}張" if s_data["net_inst"] else "未取得")
                cc3.metric("上漲/下跌",f"{up_cnt}/{len(rows)-up_cnt}")
            else: st.info("此產業今日無數據")
        with tab_heat:
            if s_data["stocks"]:
                heat_html=build_treemap_html(s_data["stocks"],f"{sec_name} 熱力圖")
                components.html(heat_html,height=560,scrolling=False)
            else: st.info("此產業今日無數據")

def tab_analysis():
    token=st.session_state.token; gkey=st.session_state.gemini_key; results=st.session_state.results
    st.markdown("### 🔍 個股分析")
    if token:
        lr=st.session_state.last_run
        st.success(f"✅ Token 已設定 | 上次：{lr.strftime('%m/%d %H:%M') if lr else '尚未執行'}")
    else:
        st.error("⚠️ 請到「⚙️ 設定」填入 FinMind Token")
    st.markdown("---")
    st.markdown("#### 🔍 搜尋股票（中文名稱 或 股號）")
    c_s1,c_s2=st.columns([4,1])
    with c_s1:
        query=st.text_input("搜尋",placeholder="輸入股號（如 2330）或中文名稱（如 台積電）",label_visibility="collapsed",key="ana_search")
    with c_s2:
        st.button("搜尋",use_container_width=True,key="ana_search_btn")
    if query:
        res_s=search_stocks(query)
        if res_s:
            opts=[f"{c} {n}" for c,n in res_s]
            sel_i=st.selectbox("搜尋結果",range(len(opts)),format_func=lambda i:opts[i],label_visibility="collapsed",key="ana_sel")
            sel_code,sel_name=res_s[sel_i]
            ca,cb,cc2=st.columns(3)
            with ca:
                if st.button(f"📊 立即分析 {sel_name}",use_container_width=True,disabled=not token,key="ana_now"):
                    disposed=fetch_disposed_cached(); full_del=fetch_full_delivery_cached()
                    delisting=fetch_delisting_cached(); gemini_del=st.session_state.gemini_delisting
                    with st.spinner(f"分析 {sel_name}（{sel_code}）..."):
                        r2,err=analyze(sel_code,token,disposed,full_del,delisting,gemini_del,force=True)
                    if r2:
                        idx2=next((i for i,x in enumerate(st.session_state.results) if x["sid"]==sel_code),None)
                        if idx2 is not None: st.session_state.results[idx2]=r2
                        else: st.session_state.results=[r2]+st.session_state.results
                        save_results_cache(st.session_state.results)
                        st.success(f"✅ {sel_name} 完成！評等 {r2['rating']}（{r2['score']}分）"); st.rerun()
                    else: st.error(f"❌ 失敗：{err}")
            with cb:
                if st.button("➕ 加入自選清單",use_container_width=True,key="ana_add"):
                    codes=[s.strip() for s in st.session_state.stock_list.split(",") if s.strip()]
                    if sel_code not in codes:
                        codes.insert(0,sel_code); st.session_state.stock_list=",".join(codes)
                        st.success(f"✅ 已加入：{sel_code} {sel_name}")
                    else: st.info(f"已在清單中：{sel_code}")
            with cc2: st.caption(f"代號：{sel_code} | 名稱：{sel_name}")
        else: st.warning(f"找不到「{query}」")
    st.markdown("---")
    sids=[s.strip() for s in st.session_state.stock_list.split(",") if s.strip()]
    st.markdown(f"**自選清單：{len(sids)} 支** — `{', '.join(sids[:5])}{'...' if len(sids)>5 else ''}`")
    c1,c2=st.columns([3,1])
    with c1: run=st.button("🔄 分析全部自選股",disabled=not token,use_container_width=True,key="ana_run")
    with c2: force=st.checkbox("強制重爬",value=False,key="ana_force")
    if not results:
        cached=load_results_cache()
        if cached: st.session_state.results=cached; results=cached; st.info(f"📦 已載入快取：{len(results)} 支")
    if run:
        errors=[]
        with st.spinner("取得風控清單..."):
            disposed=fetch_disposed_cached(); full_del=fetch_full_delivery_cached()
            delisting=fetch_delisting_cached(); st.session_state.disposed=disposed
            if gkey:
                with st.spinner("🤖 Gemini 偵測下市股..."): gemini_del=gemini_fetch_delisting(gkey)
                if gemini_del: st.info(f"🤖 Gemini 偵測到 {len(gemini_del)} 支下市風險股")
            else: gemini_del=set()
        all_res=[]; bar=st.progress(0,"準備中...")
        for i,sid in enumerate(sids):
            bar.progress((i+1)/len(sids),text=f"分析 {nm(sid)}（{i+1}/{len(sids)}）")
            r2,err=analyze(sid,token,disposed,full_del,delisting,gemini_del,force=force)
            if r2: all_res.append(r2)
            else: errors.append(f"{sid}：{err}")
            time.sleep(0.2)
        bar.empty()
        if all_res:
            st.session_state.results=sorted(all_res,key=lambda x:x["score"],reverse=True)
            st.session_state.last_run=datetime.now()
            save_results_cache(st.session_state.results); st.success(f"✅ 完成！{len(all_res)} 支")
        else: st.error("❌ 分析失敗，請確認 Token")
        if errors:
            with st.expander(f"⚠️ {len(errors)} 支失敗"): [st.write(e) for e in errors]
        st.rerun()
    if not results: st.info("👆 點「分析全部自選股」或搜尋個別股票"); return
    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    c1,c2,c3,c4=st.columns(4)
    for col,(rt,em) in zip([c1,c2,c3,c4],[("S","⭐"),("A","✅"),("B","👀"),("C","❌")]):
        col.metric(f"{em} {rt}",cnts.get(rt,0))
    full_html=build_full_html(results)
    st.download_button("📥 下載完整 HTML 報告",full_html,
                       f"portfolio_{date.today().strftime('%Y%m%d')}.html","text/html",use_container_width=True)
    st.markdown("---")
    sorted_r=sorted(results,key=lambda x:x["score"],reverse=True)
    opts2=[f"{r['rating']} {r['name']}（{r['sid']}） — {r['score']}分 | {r['price']:,.0f}元 {r['chg']:+.1f}%" for r in sorted_r]
    sel=st.selectbox("🔍 選擇股票查看完整報告",range(len(opts2)),format_func=lambda i:opts2[i],key="ana_view")
    r_sel=sorted_r[sel]
    ca,cb=st.columns(2)
    with ca:
        html=build_wiwynn(r_sel)
        st.download_button(f"📄 下載 {r_sel['name']} 報告",html,
                           f"{r_sel['sid']}_{date.today().strftime('%Y%m%d')}.html","text/html",use_container_width=True)
    with cb:
        if st.button(f"🔄 重新分析 {r_sel['name']}",use_container_width=True,key="ana_rerun"):
            disposed=fetch_disposed_cached(); full_del=fetch_full_delivery_cached()
            delisting=fetch_delisting_cached(); gemini_del=st.session_state.gemini_delisting
            with st.spinner("重新抓取..."):
                new_r,err=analyze(r_sel["sid"],token,disposed,full_del,delisting,gemini_del,force=True)
            if new_r:
                idx=next((i for i,x in enumerate(st.session_state.results) if x["sid"]==r_sel["sid"]),None)
                if idx is not None: st.session_state.results[idx]=new_r
                save_results_cache(st.session_state.results); st.success("✅ 已更新"); st.rerun()
            else: st.error(f"❌ {err}")
    components.html(html,height=2700,scrolling=True)

def tab_calendar():
    st.markdown("### 📅 財經行事曆")
    gkey=st.session_state.gemini_key
    c1,c2,c3,c4=st.columns([1,3,3,1])
    with c1:
        if st.button("◄",use_container_width=True,key="cal_prev"):
            if st.session_state.cal_month==1:
                st.session_state.cal_month=12; st.session_state.cal_year-=1
            else: st.session_state.cal_month-=1
            st.session_state.cal_events=[]; st.session_state.cal_events_ts=None; st.rerun()
    with c2:
        mzh_l=["一","二","三","四","五","六","七","八","九","十","十一","十二"]
        mzh=mzh_l[st.session_state.cal_month-1]
        st.markdown(f'<div style="text-align:center;font-size:17px;font-weight:700;color:#fff;padding:8px">{st.session_state.cal_year}年{mzh}月</div>',unsafe_allow_html=True)
    with c3:
        if gkey: st.success("🤖 Gemini 搜尋已啟用")
        else:    st.warning("設定 Gemini Key 以啟用 AI 搜尋")
    with c4:
        if st.button("►",use_container_width=True,key="cal_next"):
            if st.session_state.cal_month==12:
                st.session_state.cal_month=1; st.session_state.cal_year+=1
            else: st.session_state.cal_month+=1
            st.session_state.cal_events=[]; st.session_state.cal_events_ts=None; st.rerun()
    c_r,c_t=st.columns(2)
    with c_r:
        if st.button("🔄 重新搜尋事件",use_container_width=True,key="cal_refresh"):
            st.session_state.cal_events=[]; st.session_state.cal_events_ts=None; st.rerun()
    with c_t:
        if st.button("📅 回到本月",use_container_width=True,key="cal_today"):
            st.session_state.cal_year=date.today().year; st.session_state.cal_month=date.today().month
            st.session_state.cal_events=[]; st.session_state.cal_events_ts=None; st.rerun()
    events=[]
    try:
        with st.spinner("搜尋財經事件..."):
            events=gemini_fetch_events(gkey,st.session_state.cal_year,st.session_state.cal_month)
    except Exception as e:
        st.warning(f"事件載入失敗：{e}，顯示預設事件")
        try: events=_default_events(st.session_state.cal_year,st.session_state.cal_month)
        except Exception: events=[]
    if not events: st.error("事件清單為空，請重新搜尋"); return
    if not gkey: st.info("💡 未設定 Gemini API Key，顯示預設重要事件（含台灣財報截止日）")
    bull_cnt=sum(1 for e in events if e.get("impact")=="bullish")
    bear_cnt=sum(1 for e in events if e.get("impact")=="bearish")
    co1,co2,co3,co4=st.columns(4)
    co1.metric("📋 總事件",len(events)); co2.metric("🟢 利多",bull_cnt)
    co3.metric("🔴 利空",bear_cnt); co4.metric("⚪ 中性",len(events)-bull_cnt-bear_cnt)
    try:
        cal_html=build_calendar_html(events,st.session_state.cal_year,st.session_state.cal_month)
        components.html(cal_html,height=1250,scrolling=True)
    except Exception as e:
        st.error(f"月曆渲染失敗：{e}")
        pfx=f"{st.session_state.cal_year}-{st.session_state.cal_month:02d}"
        for ev in sorted([e for e in events if e.get("date","").startswith(pfx)],key=lambda x:x.get("date","")):
            icon="🟢" if ev.get("impact")=="bullish" else ("🔴" if ev.get("impact")=="bearish" else "⚪")
            st.markdown(f"**{ev.get('date','')[5:]} {icon} {ev.get('title','')}** — {ev.get('detail','')}")

def tab_rank():
    st.markdown("### 🏆 今日評等排行")
    results=st.session_state.results
    if not results: st.info("請先在「🔍 個股分析」執行分析"); return
    df=pd.DataFrame([{"評等":r["rating"],"股票":f"{r['name']}({r['sid']})","分數":r["score"],
                      "現價":r["price"],"漲跌%":f"{r['chg']:+.2f}%",
                      "外資":f"{r['fc']:+d}日","投信":f"{r['tc']:+d}日",
                      "目標":f"{r['tp']:,.0f}" if r.get("tp") else "-",
                      "風控":("🚨全額交割" if r.get("is_full_del") else "⚠️下市" if r.get("is_delisting") else "⏱處置" if r.get("is_disposed") else "正常")}
                     for r in results])
    st.dataframe(df,use_container_width=True,hide_index=True)
    buy2=[r for r in results if r["fc"]>0 and r["tc"]>0 and not r.get("is_hard_risk",False)]
    if buy2:
        st.markdown("### ✅ 外資+投信同向買超")
        for r in sorted(buy2,key=lambda x:x["fc"]+x["tc"],reverse=True):
            chg2=r["chg"] or 0
            chg2_color="#4ecca3" if chg2>=0 else "#ff6b6b"
            st.markdown(
                f'<div style="background:#1a3a27;border-left:4px solid #27ae60;border-radius:8px;'
                f'padding:9px 13px;margin:4px 0;border:1px solid #27ae60">'
                f'<strong style="color:#e8eaf0">{r["name"]}（{r["sid"]}）</strong> '
                f'<span style="color:{chg2_color}">{r["price"]:,.0f}元 {chg2:+.1f}%</span> '
                f'外資<span style="color:#4ecca3;font-weight:700">+{r["fc"]}日</span> '
                f'投信<span style="color:#4ecca3;font-weight:700">+{r["tc"]}日</span></div>',
                unsafe_allow_html=True)

def tab_settings():
    st.markdown("### ⚙️ 設定")
    with st.form("sf",clear_on_submit=False):
        st.markdown("**🔑 FinMind Token**（個股分析需要）")
        token=st.text_input("t",value=st.session_state.token,type="password",placeholder="貼上 FinMind Token...",label_visibility="collapsed")
        st.markdown("**🤖 Gemini API Key**（下市偵測 + 財經行事曆，選填）")
        gkey=st.text_input("g",value=st.session_state.gemini_key,type="password",placeholder="貼上 Google Gemini API Key（AIza...）",label_visibility="collapsed")
        st.markdown("**📋 自選股清單**（逗號分隔）")
        sl=st.text_area("s",value=st.session_state.stock_list,height=80,label_visibility="collapsed")
        ok=st.form_submit_button("💾 儲存設定",use_container_width=True)
    if ok:
        st.session_state.token=token.strip(); st.session_state.gemini_key=gkey.strip()
        st.session_state.stock_list=sl.strip(); st.success("✅ 儲存完成！")
    c1,c2=st.columns(2)
    with c1:
        if st.session_state.token: st.success(f"FinMind：{st.session_state.token[:8]}...")
        else: st.warning("未設定 FinMind Token")
    with c2:
        if st.session_state.gemini_key: st.success(f"Gemini：{st.session_state.gemini_key[:8]}...")
        else: st.info("Gemini 未設定（可選）")
    st.markdown("---")
    st.markdown("""
**📌 取得 FinMind Token（免費）**：[finmindtrade.com](https://finmindtrade.com)
**🤖 取得 Gemini API Key（免費）**：[aistudio.google.com/apikey](https://aistudio.google.com/apikey)
**Streamlit Cloud Secrets：**
```toml
FINMIND_TOKEN = "..."
GEMINI_API_KEY = "AIza..."
```
    """)
    cached=load_results_cache()
    if cached: st.success(f"📦 快取：{len(cached)} 支股票")
    if st.button("🗑 清除所有快取",use_container_width=True,key="clear_cache"):
        import shutil
        shutil.rmtree(CACHE_DIR,ignore_errors=True); os.makedirs(CACHE_DIR,exist_ok=True)
        for fn in [fetch_twse_prices_all,fetch_twse_institution_all,
                   fetch_tpex_prices_all,fetch_tpex_institution_all,
                   fetch_disposed_cached,fetch_full_delivery_cached,fetch_delisting_cached,_api]:
            fn.clear()
        st.session_state.results=[]; st.session_state.gemini_delisting=set()
        st.session_state.cal_events=[]; st.success("✅ 已清除")

def main():
    try:
        t1,t2,t3,t4,t5=st.tabs(["📡 籌碼掃描","🔍 個股分析","📅 財經行事曆","🏆 排行榜","⚙️ 設定"])
        with t1:
            try: tab_scanner()
            except Exception as e: st.error(f"籌碼掃描錯誤：{e}"); st.exception(e)
        with t2:
            try: tab_analysis()
            except Exception as e: st.error(f"個股分析錯誤：{e}"); st.exception(e)
        with t3:
            try: tab_calendar()
            except Exception as e: st.error(f"財經行事曆錯誤：{e}"); st.exception(e)
        with t4:
            try: tab_rank()
            except Exception as e: st.error(f"排行榜錯誤：{e}"); st.exception(e)
        with t5:
            try: tab_settings()
            except Exception as e: st.error(f"設定錯誤：{e}"); st.exception(e)
    except Exception as e:
        st.error(f"App 啟動錯誤：{type(e).__name__}: {e}"); st.exception(e)

if __name__=="__main__": main()
