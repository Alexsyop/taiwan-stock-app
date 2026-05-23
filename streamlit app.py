"""
台股分析系統 v6.2 — 修正版（完整可執行）
修正：
  - fetch_disposed_cached 加回 @st.cache_data 裝飾器
  - tab_rank 顏色 f-string 預計算（Python 3.9+ 相容）
  - tp_card 反斜線問題（預計算 _tp_hi/_tp_lo）
  - 所有 .clear() 呼叫只對有快取的函式
"""
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
p,span,label,li,td,th,div{color:#e8eaf0}
strong{color:#fff}
h1,h2,h3,h4{color:#fff!important}
[data-testid="stMarkdownContainer"] *{color:#e8eaf0!important}
.stTabs [data-baseweb="tab-list"]{background:#0f1724!important;border-radius:12px;padding:5px;gap:2px}
.stTabs [data-baseweb="tab"]{color:#8fa3b8!important;font-size:12px;font-weight:600;border-radius:8px;padding:7px 1px}
.stTabs [aria-selected="true"]{background:#27ae60!important;color:#fff!important}
.stTabs [data-baseweb="tab-panel"]{background:transparent!important}
.stButton>button{background:#27ae60!important;color:#fff!important;border:none!important;border-radius:10px!important;font-size:14px!important;font-weight:700!important;width:100%}
.stButton>button:disabled{background:#444!important;color:#888!important}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{background:#2c3e50!important;color:#fff!important;border:1px solid #3d5166!important}
[data-testid="stTextInput"] label,[data-testid="stTextArea"] label{color:#8fa3b8!important}
[data-testid="stSelectbox"] *{color:#e8eaf0!important}
[data-testid="stSelectbox"]>div>div{background:#2c3e50!important;border:1px solid #3d5166!important}
[data-testid="stCheckbox"] label{color:#e8eaf0!important}
[data-testid="stDataFrame"]{background:#2c3e50!important;border-radius:8px}
[data-testid="stDataFrame"] *{color:#e8eaf0!important}
</style>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 擴充股票資料庫
# ─────────────────────────────────────────────────────────────
ALL_STOCKS = {
    "2330":"台積電","2317":"鴻海","2454":"聯發科","2308":"台達電","2382":"廣達",
    "2303":"聯電","2327":"國巨","2357":"華碩","2379":"瑞昱","2376":"技嘉",
    "2313":"華通","2368":"金像電","2603":"長榮","2609":"陽明","2615":"萬海",
    "3711":"日月光投控","2412":"中華電","2886":"兆豐金","2881":"富邦金","2882":"國泰金",
    "2884":"玉山金","2891":"中信金","1301":"台塑","1303":"南亞","2002":"中鋼",
    "2408":"南亞科","2474":"可成","2385":"群光","3661":"世芯-KY","6669":"緯穎",
    "2353":"宏碁","2356":"英業達","3034":"聯詠","3037":"欣興","3231":"緯創",
    "1513":"中興電","2059":"川湖","2301":"光寶科","2337":"旺宏","2344":"華邦電",
    "2352":"佳世達","2371":"大同","2395":"研華","2409":"友達","2474":"可成",
    "2498":"宏達電","2603":"長榮","2606":"裕民","2609":"陽明","2610":"華航",
    "2615":"萬海","2618":"長榮航","2633":"台灣高鐵","2801":"彰銀","2880":"華南金",
    "2882":"國泰金","2883":"開發金","2885":"元大金","2887":"台新金","2890":"永豐金",
    "2892":"第一金","2912":"統一超","3008":"大立光","3017":"奇鋐","3034":"聯詠",
    "3035":"智原","3036":"文曄","3037":"欣興","3044":"健鼎","3048":"益登",
    "3081":"聯惠","3105":"穩懋","3231":"緯創","3293":"鈊象","3406":"玉晶光",
    "3443":"創意","3481":"群創","3529":"力旺","3533":"嘉澤","3550":"樂士",
    "3583":"辛耘","3587":"閎康","3645":"達亮","3665":"貿聯-KY","3698":"隆達",
    "3702":"大聯大","3706":"神達","3711":"日月光投控","4938":"和碩","4966":"譜瑞-KY",
    "5347":"世界先進","5483":"中美晶","5880":"合庫金","6239":"力成","6271":"同欣電",
    "6285":"啟碁","6415":"矽力-KY","6488":"環球晶","6510":"精測","6515":"穎威",
    "6526":"達發","6533":"晶心科","6669":"緯穎","6770":"力積電","8046":"南電",
    "8150":"南茂","8299":"群聯","5274":"信驊","4919":"新唐","4958":"臻鼎-KY",
    "4966":"譜瑞-KY","4968":"立積","5269":"祥碩","5347":"世界先進","5371":"中光電",
    "5438":"東友","5471":"松翰","5274":"信驊","3167":"達亮",
}
# nm() 已在上方 SECTOR_MAP 區塊中定義

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"
GEMINI_MODEL = "gemini-2.0-flash"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CACHE_DIR = "/tmp/tw_stock_v6"
os.makedirs(CACHE_DIR, exist_ok=True)

RC  = {"S":"#1a5c38","A":"#27ae60","B":"#854F0B","C":"#A32D2D"}
RL  = {"S":"#D0F0DC","A":"#D0F0DC","B":"#FAE0A8","C":"#F7C1C1"}
RS  = {"S":"#A8E6BB","A":"#A8E6BB","B":"#F5C842","C":"#F09595"}
VBG = {"S":"#1a3a27","A":"#1a3a27","B":"#3a2c0a","C":"#3a1a1a"}
VBC = {"S":"#27ae60","A":"#27ae60","B":"#f39c12","C":"#e74c3c"}
VTC = {"S":"#a8e6bb","A":"#a8e6bb","B":"#fae0a8","C":"#f7c1c1"}
NAMES = ALL_STOCKS

# ─────────────────────────────────────────────────────────────
# 產業分類（籌碼掃描使用）
# ─────────────────────────────────────────────────────────────
SECTOR_MAP = {
    "💎 半導體/晶圓製造": {
        "stocks": ["2330","2303","5347","6770","2408","5483"],
        "desc": "台積電、聯電、世界先進、力積電"
    },
    "🔵 IC設計": {
        "stocks": ["2454","3034","3661","5274","6415","4966","4919","5269","4968","3443","3035","6526","3529","3105","6533","3588"],
        "desc": "聯發科、聯詠、世芯、信驊、矽力、創意、智原"
    },
    "🤖 AI伺服器/雲端": {
        "stocks": ["6669","2382","3231","2356","4938","2317"],
        "desc": "緯穎、廣達、緯創、英業達、和碩"
    },
    "🌡️ 散熱/機殼/連接器": {
        "stocks": ["3017","3533","3665","3048","2059","3587"],
        "desc": "奇鋐、嘉澤、貿聯-KY、益登、川湖、閎康"
    },
    "🟤 PCB/ABF載板": {
        "stocks": ["3037","8046","4958","3044","2313","2368"],
        "desc": "欣興、南電、臻鼎-KY、健鼎、華通、金像電"
    },
    "📦 封裝測試": {
        "stocks": ["3711","6239","2449","6271","6510","6488"],
        "desc": "日月光、力成、京元電子、同欣電、精測、環球晶"
    },
    "💾 記憶體/存儲": {
        "stocks": ["2408","8299","2451","5274","3293"],
        "desc": "南亞科、群聯、創見、信驊、鈊象"
    },
    "📡 網通/電子零組件": {
        "stocks": ["6285","2301","2379","2376","3702","2327"],
        "desc": "啟碁、光寶科、瑞昱、技嘉、大聯大、國巨"
    },
    "⚡ 電源/被動元件": {
        "stocks": ["2308","2327","3577","2395"],
        "desc": "台達電、國巨、中宇、研華"
    },
    "🏦 金融/銀行": {
        "stocks": ["2881","2882","2884","2886","2891","5880","2892","2885"],
        "desc": "富邦金、國泰金、玉山金、兆豐金、中信金"
    },
    "🚢 航運/物流": {
        "stocks": ["2603","2609","2615","2610","2618"],
        "desc": "長榮、陽明、萬海、華航、長榮航"
    },
    "🔋 電動車/綠能": {
        "stocks": ["6488","2308","6415","3698"],
        "desc": "環球晶、台達電、矽力-KY、隆達"
    },
}

# 動態股票名稱快取（從市場數據更新，補全 ALL_STOCKS 沒有的股票名稱）
_MARKET_NAMES = {}

def nm(s):
    """取得股票中文名稱（ALL_STOCKS > 市場數據 > 股號本身）"""
    return ALL_STOCKS.get(s) or _MARKET_NAMES.get(s) or s

def update_names_from_market(prices_dict):
    """從 TWSE/TPEx 市場數據更新名稱快取"""
    global _MARKET_NAMES
    for sid, data in prices_dict.items():
        n = data.get("name","")
        if n and len(n) > 0 and sid not in ALL_STOCKS:
            _MARKET_NAMES[sid] = n


for k,v in [("token",""),("gemini_key",""),
            ("stock_list","2330,2454,6669,3661,3034,3017,3037,6515,5274,2376"),
            ("results",[]),("last_run",None),("disposed",set()),
            ("gemini_delisting",set()),("gemini_delisting_ts",None),
            ("cal_year",date.today().year),("cal_month",date.today().month),
            ("cal_events",[]),("cal_events_ts",None),("scanner_sector",None)]:
    if k not in st.session_state: st.session_state[k] = v

if not st.session_state.token:
    try:
        t=st.secrets.get("FINMIND_TOKEN","")
        if t: st.session_state.token=t
    except Exception: pass
if not st.session_state.gemini_key:
    try:
        g=st.secrets.get("GEMINI_API_KEY","")
        if g: st.session_state.gemini_key=g
    except Exception: pass

# ── 工具 ─────────────────────────────────────────────────────
def fi(s,d=0):
    try: return int(str(s).replace(",","").replace(" ","").strip())
    except: return d
def ff(s,d=0.0):
    try: return float(str(s).replace(",","").replace(" ","").strip())
    except: return d
def parse_tw(s):
    if not s or str(s).strip() in ("--","","-"): return 0
    try: return int(str(s).replace(",","").replace(" ","").strip())
    except: return 0
def ma_n(cls,n): return round(sum(cls[-n:])/n,2) if len(cls)>=n else None
def dev_pct(p,m): return round((p-m)/m*100,2) if p and m and m>0 else None
def con_days(series):
    if not series: return 0
    last=series[-1]
    if last==0: return 0
    d=1 if last>0 else -1; c=0
    for v in reversed(series):
        if (v>0 and d==1) or (v<0 and d==-1): c+=1
        else: break
    return c*d
def fv(v,u="",dig=2):
    if v is None: return "N/A"
    return f"{v:,.{dig}f}{u}"
def ccc(v): return "up" if v>=0 else "dn"
def get_institution_query_date():
    """
    法人數據查詢日期（台灣時間 UTC+8）：
    - 下午 5 點前：TWSE 盤後數據尚未公布 → 查昨日
    - 下午 5 點後：可查當日盤後數據
    週末/假日自動回退到最近交易日。
    """
    now_tw = datetime.utcnow() + timedelta(hours=8)
    if now_tw.hour < 17:
        target = now_tw.date() - timedelta(days=1)
    else:
        target = now_tw.date()
    while target.weekday() >= 5:
        target -= timedelta(days=1)
    return target

def get_institution_query_date_str():
    """回傳 YYYYMMDD 字串，供快取 key 使用"""
    return get_institution_query_date().strftime("%Y%m%d")

def last_trading_days(n=5):
    """從法人查詢日往前取 n 個交易日（備用）"""
    days=[]; d=get_institution_query_date()
    while len(days)<n:
        if d.weekday()<5: days.append(d)
        d-=timedelta(days=1)
    return days

def search_stocks(query):
    q=query.strip()
    if not q: return []
    res=[(code,name) for code,name in ALL_STOCKS.items() if q in code or q in name]
    res.sort(key=lambda x:(0 if x[0]==q else 1 if x[0].startswith(q) else 2 if q in x[0] else 3))
    return res[:20]

# ── 持久快取 ──────────────────────────────────────────────────
def cache_path(sid): return os.path.join(CACHE_DIR,f"{sid}.json")
def save_cache(sid,data):
    try:
        with open(cache_path(sid),"w",encoding="utf-8") as f:
            json.dump({"ts":datetime.now().isoformat(),"data":data},f,ensure_ascii=False)
    except Exception: pass
def load_cache(sid,max_hours=4):
    p=cache_path(sid)
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
    p=os.path.join(CACHE_DIR,"batch.json")
    if not os.path.exists(p): return None
    try:
        with open(p,encoding="utf-8") as f: obj=json.load(f)
        if datetime.now()-datetime.fromisoformat(obj["ts"])<timedelta(hours=4):
            return obj["results"]
    except Exception: pass
    return None

# ─────────────────────────────────────────────────────────────
# Gemini：下市偵測
# ─────────────────────────────────────────────────────────────
def gemini_fetch_delisting(api_key):
    if not api_key: return set()
    ts=st.session_state.gemini_delisting_ts
    if ts and (datetime.now()-ts).seconds<21600 and st.session_state.gemini_delisting:
        return st.session_state.gemini_delisting
    try:
        from google import genai
        client=genai.Client(api_key=api_key)
        delist_prompt = (
            "請列出目前台灣股市中以下類型的股票代號（4位數字），每行一個，只列代號：\n"
            "1. 全額交割股（需全額繳款，流動性極差）\n"
            "2. 面臨強制下市或已公告退市計畫的股票\n"
            "3. 股價較52週高點下跌超過85%且面臨退市風險的股票\n"
            "4. 淨值為負或連續虧損已達下市標準的股票\n"
            "5. 已被台灣證交所或櫃買中心列入注意/警示/變更交易方式的股票\n"
            "若不確定請勿列出。"
        )
        response=client.models.generate_content(model=GEMINI_MODEL, contents=delist_prompt)
        codes=set(re.findall(r'\b\d{4}\b',response.text))
        valid={c for c in codes if 1000<=int(c)<=9999}
        st.session_state.gemini_delisting=valid
        st.session_state.gemini_delisting_ts=datetime.now()
        return valid
    except Exception: return set()

# ─────────────────────────────────────────────────────────────
# Gemini：財經事件行事曆
# ─────────────────────────────────────────────────────────────
def gemini_fetch_events(api_key, year, month):
    if not api_key:
        return _default_events(year, month)
    cache_key=f"{year}-{month:02d}"
    ts=st.session_state.cal_events_ts
    if (ts and (datetime.now()-ts).seconds<21600
            and st.session_state.cal_events
            and st.session_state.cal_events[0].get("_month")==cache_key):
        return st.session_state.cal_events
    try:
        from google import genai
        client=genai.Client(api_key=api_key)
        next_m=month%12+1; next_y=year+(1 if month==12 else 0)
        prompt = (
            f"你是專業的財經分析師。請搜尋並提供{year}年{month}月（延伸至{next_y}年{next_m}月上旬）的所有重大財經事件。\n\n"
            "【必須涵蓋的類別】\n"
            "1. 美國總體經濟：CPI、PPI、PCE、非農就業、GDP、Fed FOMC利率決策（每年8次）、零售銷售、ISM PMI\n"
            "2. 美股重要財報（季報）：\n"
            "   - 輝達 NVIDIA（財報月：2/5/8/11月）\n"
            "   - 蘋果 Apple（財報月：1/5/8/10月）\n"
            "   - 微軟 Microsoft（財報月：1/4/7/10月）\n"
            "   - Google Alphabet（財報月：1/4/7/10月）\n"
            "   - Meta（財報月：1/4/7/10月）\n"
            "   - 亞馬遜 Amazon（財報月：2/5/8/10月）\n"
            "   - 特斯拉 Tesla（財報月：1/4/7/10月）\n"
            "   - 超微 AMD、博通 Broadcom、高通 Qualcomm\n"
            "3. 台灣財經：台灣央行理監事會議（3/6/9/12月）、台積電法說會、鴻海/聯發科財報、台灣CPI/GDP\n"
            "4. 全球重大事件：\n"
            "   - G7/G20/APEC峰會、WTO會議、達沃斯論壇\n"
            "   - 川習會（川普與習近平會面）、中美貿易談判、關稅政策\n"
            "   - 歐央行ECB、日本央行BOJ、英國央行BOE利率決策\n"
            "   - 台美貿易協議、半導體出口管制相關\n"
            "5. 科技大會：輝達GTC、蘋果WWDC/秋季發表會、CES科技展、Computex台北電腦展\n\n"
            f"請以JSON陣列回傳（不要markdown、不要其他文字），日期格式 YYYY-MM-DD，月份 {year}-{month:02d}：\n"
            "[{\"date\":\"YYYY-MM-DD\",\"title\":\"事件簡稱15字以內\",\"detail\":\"詳細說明60字以內\","
            "\"category\":\"美國總經/台灣財經/全球事件/企業財報/科技大會\","
            "\"impact\":\"bullish/bearish/neutral\",\"impact_zh\":\"利多/利空/中性\","
            "\"reason\":\"對台灣科技股或大盤影響35字以內\"}]\n\n"
            f"目標：列出{year}年{month}月所有重要事件（30~50個），必須包含 Fed FOMC、CPI、非農就業、重要財報。只回傳JSON陣列。"
        )
        response=client.models.generate_content(model=GEMINI_MODEL,contents=prompt)
        text=response.text.strip()
        text=re.sub(r'```json\s*','',text); text=re.sub(r'```\s*','',text)
        if text.startswith('['):
            events=json.loads(text)
        else:
            m2=re.search(r'\[.*\]',text,re.DOTALL)
            events=json.loads(m2.group(0)) if m2 else []
        validated=[]
        for ev in events:
            if not ev.get("date") or not ev.get("title"): continue
            ev["_month"]=cache_key
            ev.setdefault("impact","neutral"); ev.setdefault("impact_zh","中性")
            ev.setdefault("category","其他"); ev.setdefault("reason","")
            validated.append(ev)
        validated.sort(key=lambda x:x["date"])
        st.session_state.cal_events=validated
        st.session_state.cal_events_ts=datetime.now()
        return validated
    except Exception:
        return _default_events(year, month)

def _default_events(year, month):
    """當 Gemini 未設定時的預設重要事件（美股財報 + 台灣百大企業財報 + 主要財經數據）"""
    pfx = f"{year}-{month:02d}"
    # 美股財報月份
    us_earnings = {
        1:  ["Apple","Microsoft","Google","Meta","Tesla"],
        2:  ["NVIDIA","Amazon"],
        4:  ["Apple","Microsoft","Google","Meta","Tesla","AMD"],
        5:  ["NVIDIA"],
        7:  ["Apple","Microsoft","Google","Meta","Tesla","AMD"],
        8:  ["NVIDIA","Amazon"],
        10: ["Apple","Microsoft","Google","Meta","Tesla"],
        11: ["NVIDIA"],
    }
    # 台灣企業財報季：Q1截止5/15，Q2截止8/14，Q3截止11/14，全年截止3/31
    tw_quarterly = {
        3:  [("03-31","台灣上市公司全年財報截止","全體上市公司","neutral")],
        4:  [("04-15","台積電Q1法說會","台積電(2330)","bullish"),
             ("04-20","聯發科Q1財報","聯發科(2454)","neutral"),
             ("04-25","鴻海Q1財報","鴻海(2317)","neutral")],
        5:  [("05-15","台灣Q1財報截止","所有上市公司Q1季報截止","neutral"),
             ("05-20","聯電/日月光Q1財報","聯電(2303)、日月光(3711)","neutral")],
        7:  [("07-15","台積電Q2法說會","台積電(2330)，AI需求展望最受關注","bullish"),
             ("07-20","聯發科Q2財報","聯發科(2454)","neutral"),
             ("07-25","鴻海Q2財報","鴻海(2317)","neutral")],
        8:  [("08-14","台灣Q2財報截止","所有上市公司Q2季報截止","neutral"),
             ("08-15","廣達/緯創Q2財報","廣達(2382)、緯創(3231) AI伺服器展望","bullish")],
        10: [("10-15","台積電Q3法說會","台積電(2330)，全年展望最關鍵","bullish"),
             ("10-20","聯發科Q3財報","聯發科(2454)","neutral"),
             ("10-22","鴻海Q3財報","鴻海(2317)","neutral"),
             ("10-28","日月光Q3財報","日月光(3711) AI封測需求","neutral")],
        11: [("11-14","台灣Q3財報截止","所有上市公司Q3季報截止","neutral"),
             ("11-15","聯電/欣興Q3財報","聯電(2303)、欣興(3037)載板需求","neutral")],
        1:  [("01-15","台積電Q4法說會","台積電(2330)，CoWoS/先進封裝展望","bullish"),
             ("01-20","聯發科Q4財報","聯發科(2454) 天璣旗艦晶片展望","bullish"),
             ("01-25","緯穎/廣達Q4財報","緯穎(6669)、廣達(2382) AI伺服器","bullish")],
    }
    # 根據月份判斷哪些財報會在本月公布
    q_earnings = us_earnings
    is_earning_month = month in q_earnings
    events = [
        {"date":f"{pfx}-05","title":"美國非農就業",
         "detail":"美國勞工部公布非農就業人口，市場最重要就業指標",
         "category":"美國總經","impact":"neutral","impact_zh":"中性",
         "reason":"若大幅高於預期將強化升息預期，壓抑台股科技族群"},
        {"date":f"{pfx}-10","title":"美國CPI通膨",
         "detail":"美國消費者物價指數，Fed 利率決策最關鍵指標",
         "category":"美國總經","impact":"bearish","impact_zh":"利空",
         "reason":"通膨超預期 → Fed 維持高息 → 壓抑成長股，台積電/輝達概念股承壓"},
        {"date":f"{pfx}-12","title":"美國PPI生產者物價",
         "detail":"生產者物價指數，通膨先行指標",
         "category":"美國總經","impact":"neutral","impact_zh":"中性",
         "reason":"影響後續CPI走向，間接影響Fed政策預期"},
        {"date":f"{pfx}-15","title":"台積電法說會",
         "detail":"台積電季度財報及展望，全球半導體業風向球",
         "category":"企業財報","impact":"bullish","impact_zh":"利多",
         "reason":"台積電展望直接影響整體台股與全球AI供應鏈股"},
        {"date":f"{pfx}-20","title":"Fed FOMC 利率決策",
         "detail":"聯準會利率決策會議，公布利率決定與聲明",
         "category":"美國總經","impact":"neutral","impact_zh":"中性",
         "reason":"利率決策是全球資金流向最重要風向球，鷹派利空"},
        {"date":f"{pfx}-21","title":"台灣央行理監事會",
         "detail":"台灣央行季度利率決策，影響台幣走勢",
         "category":"台灣財經","impact":"neutral","impact_zh":"中性",
         "reason":"台幣升值有利進口商，貶值有利出口（台積電等）"},
        {"date":f"{pfx}-25","title":"美國GDP初值",
         "detail":"美國季度GDP成長率初步估計值",
         "category":"美國總經","impact":"bullish","impact_zh":"利多",
         "reason":"GDP強勁代表企業獲利基礎穩固，有利科技股評價"},
        {"date":f"{pfx}-28","title":"美國PCE物價指數",
         "detail":"Fed最看重的通膨指標，個人消費支出物價",
         "category":"美國總經","impact":"neutral","impact_zh":"中性",
         "reason":"PCE是Fed制定利率政策的核心參考數據"},
    ]
    # 美股財報月份
    is_us_earning_month = month in us_earnings
    if is_us_earning_month:
        companies = us_earnings[month]
        for i, co in enumerate(companies):
            impact = "bullish" if co in ["NVIDIA","Apple"] else "neutral"
            events.append({
                "date":f"{pfx}-{min(15+i*2, 28):02d}",
                "title":f"{co} 財報公布",
                "detail":f"{co} 季度財報及下季展望，市場高度關注",
                "category":"企業財報",
                "impact":impact,"impact_zh":"利多" if impact=="bullish" else "中性",
                "reason":f"{co}財報影響AI/半導體族群，直接帶動台積電/日月光等供應鏈"
            })
    # 台灣上市公司財報事件
    if month in tw_quarterly:
        for date_suffix, title, detail, impact in tw_quarterly[month]:
            events.append({
                "date":f"{year}-{date_suffix}",
                "title":title,
                "detail":detail,
                "category":"台灣財報",
                "impact":impact,
                "impact_zh":"利多" if impact=="bullish" else "利空" if impact=="bearish" else "中性",
                "reason":"台灣龍頭企業財報展望直接影響大盤及相關供應鏈走勢"
            })
    # ── 台灣固定截止日 ─────────────────────────────────────────
    if month in TW_DEADLINES:
        day, title, detail = TW_DEADLINES[month]
        events.append({
            "date": f"{pfx}-{day:02d}",
            "title": title,
            "detail": detail,
            "category": "台灣財經",
            "impact": "neutral",
            "impact_zh": "中性",
            "reason": "財報截止前，財報優於預期者股價走強，財報地雷則急跌"
        })

    # 月營收（每月10日）
    events.append({
        "date": f"{pfx}-10",
        "title": "台灣月營收公布",
        "detail": "全台上市上櫃公司公布上個月月營收，是台股最重要先行指標",
        "category": "台灣財經",
        "impact": "neutral",
        "impact_zh": "中性",
        "reason": "月營收YoY/MoM優於預期者飆漲，弱於預期者下殺，科技股影響最大"
    })

    # 台積電法說會
    if month in TSMC_MONTHS:
        events.append({
            "date": f"{pfx}-18",
            "title": "台積電法說會",
            "detail": f"台積電{['一','二','三','四','五','六','七','八','九','十','十一','十二'][month-1]}月季度業績說明會，全球半導體業風向球",
            "category": "企業財報",
            "impact": "bullish",
            "impact_zh": "利多",
            "reason": "台積電展望直接牽動整體台股與AI供應鏈族群，是全年最重要的單一事件"
        })

    # 聯發科法說會
    if month in MTEK_MONTHS:
        events.append({
            "date": f"{pfx}-12",
            "title": "聯發科法說會",
            "detail": "聯發科季度業績說明會，IC設計族群景氣指標",
            "category": "企業財報",
            "impact": "bullish",
            "impact_zh": "利多",
            "reason": "聯發科展望影響IC設計族群（聯詠、瑞昱等），連動智慧手機與AIoT景氣"
        })

    # 鴻海/台系EMS法說
    if month in FOX_MONTHS:
        events.append({
            "date": f"{pfx}-20",
            "title": "鴻海/台系EMS法說",
            "detail": "鴻海、廣達、緯創等EMS廠季度法說，AI伺服器訂單動向",
            "category": "企業財報",
            "impact": "bullish",
            "impact_zh": "利多",
            "reason": "AI伺服器訂單能見度決定整體ODM族群走勢"
        })

    for e in events:
        e["_month"] = f"{year}-{month:02d}"
    return events

# ─────────────────────────────────────────────────────────────
# 財經行事曆 HTML 生成器
# ─────────────────────────────────────────────────────────────
def build_calendar_html(events, year, month):
    from collections import defaultdict as _dd
    day_events=_dd(list)
    for ev in events:
        try:
            d=datetime.strptime(ev["date"],"%Y-%m-%d")
            if d.year==year and d.month==month: day_events[d.day].append(ev)
        except Exception: pass

    today=date.today(); week_end=today+timedelta(days=7)
    week_events=[]
    for ev in events:
        try:
            dw=datetime.strptime(ev["date"],"%Y-%m-%d").date()
            if today<=dw<=week_end: week_events.append((dw,ev))
        except Exception: pass
    week_events.sort(key=lambda x:x[0])

    IC={"bullish":"#27ae60","bearish":"#e74c3c","neutral":"#8fa3b8"}
    IB={"bullish":"#1a3a27","bearish":"#3a1a1a","neutral":"#2c3e50"}
    IZ={"bullish":"🟢利多","bearish":"🔴利空","neutral":"⚪中性"}
    CC={"美國總經":"#2980b9","台灣財經":"#27ae60","全球事件":"#8e44ad","企業財報":"#e67e22","其他":"#7f8c8d"}

    first_wd,days_in_month=_cal.monthrange(year,month)
    cells=""
    for _ in range(first_wd): cells+='<div class="cal-cell cal-empty"></div>'
    for day in range(1,days_in_month+1):
        is_today=(today==date(year,month,day))
        tc="cal-today" if is_today else ""
        td='<div class="today-dot"></div>' if is_today else ""
        evs=day_events.get(day,[])
        pills=""
        for ev in evs[:3]:
            imp=ev.get("impact","neutral")
            ic=IC.get(imp,"#8fa3b8"); ibg=IB.get(imp,"#2c3e50")
            t2=ev.get("title","")[:8]; dt=ev.get("detail","")
            pills+=('<div class="cal-pill" style="background:'+ibg+
                    ';border-left:2px solid '+ic+';color:'+ic+
                    '" title="'+dt+'">'+t2+'</div>')
        if len(evs)>3: pills+='<div class="cal-more">+'+str(len(evs)-3)+'</div>'
        cells+=('<div class="cal-cell '+tc+'">'+td+
                '<div class="cal-day-num">'+str(day)+'</div>'+pills+'</div>')
    total=first_wd+days_in_month
    for _ in range((7-total%7)%7): cells+='<div class="cal-cell cal-empty"></div>'

    week_html=""
    if week_events:
        for dw,ev in week_events:
            imp=ev.get("impact","neutral")
            ic=IC.get(imp,"#8fa3b8"); ibg=IB.get(imp,"#2c3e50"); iz=IZ.get(imp,"⚪中性")
            cat_c=CC.get(ev.get("category","其他"),"#7f8c8d")
            wd_zh=["一","二","三","四","五","六","日"][dw.weekday()]
            tmk="📍今天 " if dw==today else ""
            rsn=ev.get("reason","")
            rh='<div class="week-ev-reason">📊 台股影響：'+rsn+'</div>' if rsn else ""
            week_html+=(
                '<div class="week-event" style="border-left:4px solid '+ic+';background:'+ibg+'">'+
                '<div class="week-ev-header">'+
                '<span class="week-date">'+tmk+dw.strftime("%m/%d")+' 週'+wd_zh+'</span>'+
                '<span class="week-impact" style="background:'+ic+'22;color:'+ic+
                ';border:1px solid '+ic+'55">'+iz+'</span>'+
                '<span class="week-cat" style="color:'+cat_c+'">'+ev.get("category","")+'</span></div>'+
                '<div class="week-ev-title">'+ev.get("title","")+'</div>'+
                '<div class="week-ev-detail">'+ev.get("detail","")+'</div>'+rh+'</div>')
    else:
        week_html='<div style="color:#8fa3b8;font-size:13px;padding:12px 0">本週無重大財經事件</div>'

    ev_list=""
    pfx_str=str(year)+"-"+f"{month:02d}"
    for ev in sorted(events,key=lambda x:x["date"]):
        if not ev.get("date","").startswith(pfx_str): continue
        imp=ev.get("impact","neutral")
        ic=IC.get(imp,"#8fa3b8"); ibg=IB.get(imp,"#2c3e50"); iz=IZ.get(imp,"⚪中性")
        ttl=ev.get("title",""); dtl=ev.get("detail",""); rsn=ev.get("reason","")
        rh='<div style="font-size:10px;color:#7ec8e3;margin-top:2px">📊 '+rsn+'</div>' if rsn else ""
        ev_list+=('<div class="ev-list-item">'+
                  '<span class="ev-date-badge">'+ev["date"][5:]+'</span>'+
                  '<span class="ev-impact-badge" style="background:'+ibg+';color:'+ic+
                  ';border:1px solid '+ic+'44">'+iz+'</span>'+
                  '<div><div style="font-size:12px;font-weight:600;color:#e8eaf0">'+ttl+'</div>'+
                  '<div style="font-size:11px;color:#8fa3b8;margin-top:2px">'+dtl+'</div>'+rh+'</div></div>')

    n_ev=len([e for e in events if e.get("date","").startswith(pfx_str)])
    bull=sum(1 for e in events if e.get("impact")=="bullish" and e.get("date","").startswith(pfx_str))
    bear=sum(1 for e in events if e.get("impact")=="bearish" and e.get("date","").startswith(pfx_str))
    mzh=["一","二","三","四","五","六","七","八","九","十","十一","十二"][month-1]
    cal_css="""
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a2332;color:#e8eaf0;font-family:'Helvetica Neue',Arial,sans-serif;padding:0}
.cal-wrap{max-width:800px;margin:0 auto;padding:10px}
.cal-header{display:flex;align-items:center;justify-content:space-between;background:#0f1724;border-radius:12px;padding:14px 20px;margin-bottom:12px}
.cal-title{font-size:20px;font-weight:700;color:#fff}
.cal-subtitle{font-size:11px;color:#8fa3b8;margin-top:3px}
.cal-legend{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px}
.leg-item{font-size:10px;display:flex;align-items:center;gap:4px;color:#8fa3b8}
.leg-dot{width:8px;height:8px;border-radius:50%}
.weekday-row{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin-bottom:2px}
.wd{text-align:center;font-size:10px;font-weight:600;color:#8fa3b8;padding:5px 0;background:#2c3e50;border-radius:4px}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.cal-cell{background:#2c3e50;border-radius:6px;padding:5px;min-height:75px;border:1px solid #3d5166;position:relative}
.cal-cell:hover{border-color:#5d7a99;background:#364d66}
.cal-today{border-color:#27ae60!important;background:#1a3a27!important}
.cal-empty{background:#1a2332;border:1px solid transparent}
.today-dot{width:6px;height:6px;background:#27ae60;border-radius:50%;position:absolute;top:4px;right:4px}
.cal-day-num{font-size:13px;font-weight:700;color:#e8eaf0;margin-bottom:3px}
.cal-pill{font-size:9px;padding:2px 4px;border-radius:3px;margin-bottom:2px;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:default}
.cal-more{font-size:9px;color:#8fa3b8;text-align:right}
.week-section{background:#0f1724;border-radius:12px;padding:14px 18px;margin-top:12px}
.week-title{font-size:14px;font-weight:700;color:#fff;margin-bottom:10px}
.week-event{border-radius:8px;padding:10px 13px;margin-bottom:8px;border:1px solid transparent}
.week-ev-header{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px}
.week-date{font-size:12px;font-weight:700;color:#e8eaf0}
.week-impact{font-size:10px;padding:2px 7px;border-radius:99px;font-weight:600}
.week-cat{font-size:10px;font-weight:500}
.week-ev-title{font-size:14px;font-weight:700;color:#fff;margin-bottom:3px}
.week-ev-detail{font-size:12px;color:#8fa3b8;line-height:1.5;margin-bottom:3px}
.week-ev-reason{font-size:11px;color:#7ec8e3;line-height:1.5}
.events-section{background:#0f1724;border-radius:12px;padding:14px 18px;margin-top:12px}
.ev-list-item{display:flex;gap:10px;padding:7px 0;border-bottom:1px solid #2c3e50;font-size:12px;align-items:flex-start}
.ev-list-item:last-child{border-bottom:none}
.ev-date-badge{background:#2c3e50;border-radius:5px;padding:3px 7px;font-size:11px;font-weight:600;color:#e8eaf0;white-space:nowrap;flex-shrink:0}
.ev-impact-badge{font-size:10px;padding:2px 6px;border-radius:99px;font-weight:600;white-space:nowrap;flex-shrink:0}
"""
    return ("<!DOCTYPE html><html lang=\"zh-TW\"><head>"
            "<meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<style>"+cal_css+"</style></head><body><div class=\"cal-wrap\">"
            "<div class=\"cal-header\"><div>"
            "<div class=\"cal-title\">📅 "+str(year)+"年"+mzh+"月 財經行事曆</div>"
            "<div class=\"cal-subtitle\">重大事件 · 利多利空標示 · 本週提醒</div></div>"
            "<div><div class=\"cal-legend\">"
            "<span class=\"leg-item\"><span class=\"leg-dot\" style=\"background:#27ae60\"></span>利多</span>"
            "<span class=\"leg-item\"><span class=\"leg-dot\" style=\"background:#e74c3c\"></span>利空</span>"
            "<span class=\"leg-item\"><span class=\"leg-dot\" style=\"background:#8fa3b8\"></span>中性</span>"
            "</div><div style=\"font-size:10px;color:#8fa3b8;margin-top:5px\">共"+str(n_ev)+"個事件 | 利多"+str(bull)+" 利空"+str(bear)+"</div>"
            "</div></div>"
            "<div class=\"weekday-row\">"
            "<div class=\"wd\">週一</div><div class=\"wd\">週二</div><div class=\"wd\">週三</div>"
            "<div class=\"wd\">週四</div><div class=\"wd\">週五</div>"
            "<div class=\"wd\" style=\"color:#e74c3c55\">週六</div>"
            "<div class=\"wd\" style=\"color:#e74c3c55\">週日</div></div>"
            "<div class=\"cal-grid\">"+cells+"</div>"
            "<div class=\"week-section\"><div class=\"week-title\">🔔 本週（7日內）重大事件提醒</div>"
            +week_html+"</div>"
            "<div class=\"events-section\">"
            "<div style=\"font-size:13px;font-weight:700;color:#fff;margin-bottom:9px\">📋 本月全部事件清單</div>"
            +ev_list+"</div>"
            "</div></body></html>")

# ─────────────────────────────────────────────────────────────
# 硬風控 API（修正：fetch_disposed_cached 加回 @st.cache_data）
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_disposed_cached():
    disposed=set()
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
    out=set()
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
    """
    下市/全額交割/注意股票清單（多端點整合）。
    包含：changeTrading、fullCash、punish 以及 TWSE 注意/處置公告。
    """
    out = set()
    urls = [
        "https://openapi.twse.com.tw/v1/announcement/changeTrading",
        "https://openapi.twse.com.tw/v1/announcement/fullCash",
        # 注意股票（異常交易、大量停損等）
        "https://openapi.twse.com.tw/v1/announcement/attention",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HDR, timeout=10, verify=False)
            if r.status_code == 200:
                for item in r.json():
                    c = str(item.get("SecuritiesCode", item.get("Code",""))).strip()
                    if c: out.add(c)
        except Exception:
            pass
    # TPEx
    try:
        r2 = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_announcement_changeTrading",
            headers=HDR, timeout=10, verify=False)
        if r2.status_code == 200:
            for item in r2.json():
                c = str(item.get("SecuritiesCode","")).strip()
                if c: out.add(c)
    except Exception:
        pass
    return out

# ─────────────────────────────────────────────────────────────
# 全市場數據（自動找最近交易日）
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=14400)
def fetch_twse_prices_all():
    out={}
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
def fetch_twse_institution_all(query_date_str=""):
    """query_date_str 作為快取 key，確保換日/換時段能取新數據"""
    out={}
    for trade_date in last_trading_days(5):
        date_str=trade_date.strftime("%Y%m%d")
        for url in [f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL",
                    f"https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALL"]:
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
                               "d":parse_tw(row[14])//1000 if len(row)>14 else 0,
                               "name":str(row[1]).strip() if len(row)>1 else ""}
                if len(out)>100: return out
            except Exception: continue
        if len(out)>100: break
    return out

@st.cache_data(ttl=14400)
def fetch_tpex_prices_all():
    out={}
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
def fetch_tpex_institution_all(query_date_str=""):
    """query_date_str 作為快取 key"""
    out={}
    for trade_date in last_trading_days(5):
        date_str=trade_date.strftime("%Y/%m/%d")
        try:
            r=requests.get(f"https://www.tpex.org.tw/web/fund/tripleFund/index.php?l=zh-tw&o=json&d={date_str}",headers=HDR,timeout=20,verify=False)
            if r.status_code!=200: continue
            d=r.json(); rows=d.get("aaData",d.get("data",[]))
            if not rows or len(rows)<5: continue
            for row in rows:
                if len(row)<7: continue
                sid=str(row[0]).strip()
                if not sid.isdigit(): continue
                out[sid]={"f":parse_tw(row[3])//1000,"t":parse_tw(row[6])//1000,
                           "d":parse_tw(row[18])//1000 if len(row)>18 else 0,"name":str(row[1]).strip()}
            if len(out)>50: return out
        except Exception: continue
    return out

# ─────────────────────────────────────────────────────────────
# 個股 API
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def _api(dataset,sid,start,token):
    try:
        r=requests.get(FINMIND_API,headers=HDR,timeout=15,verify=False,
          params={"dataset":dataset,"data_id":sid,"start_date":start,"token":token})
        if r.status_code==200: return r.json().get("data",[])
    except Exception: pass
    return []

def get_price(sid,token):
    s=(date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows=_api("TaiwanStockPrice",sid,s,token)
    recs=[{"date":r.get("date","")[:10],"close":ff(r.get("close",0)),
           "high":ff(r.get("max",r.get("high",0))),"low":ff(r.get("min",r.get("low",0))),
           "vol":fi(r.get("Trading_Volume",0))//1000}
          for r in rows if ff(r.get("close",0))>0]
    recs.sort(key=lambda x:x["date"]); return recs

def get_inst(sid,token):
    s=(date.today()-timedelta(days=35)).strftime("%Y-%m-%d")
    rows=_api("TaiwanStockInstitutionalInvestorsBuySell",sid,s,token)
    dm=defaultdict(lambda:{"f":0,"t":0,"d":0})
    for r in rows:
        n2=str(r.get("name","")); net=fi(r.get("buy",0))-fi(r.get("sell",0))
        d=r.get("date","")[:10]
        if "Foreign" in n2 or "外資" in n2: dm[d]["f"]+=net
        elif "Trust" in n2 or "投信" in n2: dm[d]["t"]+=net
        elif "Dealer" in n2 or "自營" in n2:dm[d]["d"]+=net
    return [{"date":d,"f":dm[d]["f"]//1000,"t":dm[d]["t"]//1000,"d":dm[d]["d"]//1000}
            for d in sorted(dm.keys())[-5:]]

def get_per(sid,token):
    s=(date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows=_api("TaiwanStockPER",sid,s,token)
    return [{"pe":ff(r.get("PER",0)),"pbr":ff(r.get("PBR",0))} for r in rows if ff(r.get("PER",0))>0][-250:]

def get_rev(sid,token):
    s=(date.today()-timedelta(days=450)).strftime("%Y-%m-%d")
    rows=_api("TaiwanStockMonthRevenue",sid,s,token)
    recs=[{"rev":ff(r.get("revenue",0)),"yr":fi(r.get("revenue_year",0)),"mo":fi(r.get("revenue_month",0))}
          for r in rows if ff(r.get("revenue",0))>0]
    recs.sort(key=lambda x:(x["yr"],x["mo"])); return recs[-13:]

def get_yahoo_target(sid):
    try:
        import yfinance as yf
        import pandas as _pd
    except ImportError: return None
    for suffix in [".TW",".TWO"]:
        try:
            info=yf.Ticker(f"{sid}{suffix}").info or {}
            if not info.get("regularMarketPrice"): continue
            mean=info.get("targetMeanPrice")
            if mean and not _pd.isna(mean) and float(mean)>0:
                count=info.get("numberOfAnalystOpinions")
                hi=info.get("targetHighPrice"); lo=info.get("targetLowPrice")
                return {"target":round(float(mean),2),
                        "high":round(float(hi),2) if hi and not _pd.isna(hi) else None,
                        "low":round(float(lo),2) if lo and not _pd.isna(lo) else None,
                        "count":int(count) if count else 0,
                        "source":f"Yahoo共識（{int(count or 0)}位分析師）"}
        except Exception: continue
    return None

# ─────────────────────────────────────────────────────────────
# 量化評分（原始機制）
# ─────────────────────────────────────────────────────────────
def calc_quant_score(p, d5, d200, fc, tc, pe, pea, rev_yoy, tp,
                     tp_h=None, ma20=None, ma60=None, rev_mom=None, inst=None):
    """
    評分系統 v2.0（針對高成長科技股優化）
    ─────────────────────────────────────
    ① 技術面：5日乖離加趨勢濾網（月線/季線）
    ② 目標價：以最高分析師目標為基準，超越均值不扣分
    ③ 基本面：YoY + MoM 雙軌，捕捉庫存去化訊號
    ④ 籌碼面：連買/連賣天數 + 異常爆量否決條件
    ⑤ S級防禦：80+分需有法人買超或營收正向支撐
    """
    sc = 50; pos = []; neg = []; warn = []; _dtl = [('起始分數', 0, 50)]

    # ── ① 技術面：5日線乖離 + 趨勢濾網 ─────────────────────────
    if d5 is not None:
        if d5 < -5:
            # 趨勢濾網：確認未在空頭趨勢中接刀
            above_ma20 = (p >= ma20) if (ma20 and ma20 > 0) else True
            above_ma60 = (p >= ma60) if (ma60 and ma60 > 0) else True
            if above_ma20:
                sc += 18; pos.append(f"5日線回測{d5:+.1f}%（守月線，良好進場點）")
            elif above_ma60:
                sc += 8; pos.append(f"5日線回測{d5:+.1f}%（跌破月線但守季線，謹慎進場）")
                warn.append("已跌破月線，需確認量縮止跌再考慮進場，避免接刀")
            else:
                sc -= 5; neg.append(f"5日乖離{d5:+.1f}%且跌破月線季線，空頭趨勢接刀高風險")
        elif d5 <= 2:
            sc += 10; pos.append(f"5日乖離健康{d5:+.1f}%"); _dtl.append((f"5日乖離{d5:+.1f}%健康", 10, max(0,min(100,sc))))
        elif d5 <= 8:
            sc += 2; warn.append(f"5日乖離偏高{d5:+.1f}%，稍注意追高風險")
        else:
            sc -= 10; neg.append(f"5日乖離過高{d5:+.1f}%，追高風險（若因當日急漲所致，建議等乖離收斂）")

    # ── ① 技術面：年線乖離（成長股放寬）──────────────────────
    if d200 and d200 > 80:
        sc -= 5; warn.append(f"年線乖離偏高{d200:+.1f}%（半導體牛市可接受，請搭配基本面確認）")
    elif d200 and d200 > 50:
        sc -= 2; warn.append(f"年線乖離稍高{d200:+.1f}%"); _dtl.append((f"年線乖離{d200:+.1f}%稍高", -2, max(0,min(100,sc))))

    # ── ② 目標價：以「最高分析師目標」為加分基準 ───────────────
    # 超越均值目標不扣分（分析師均值可能落後市場），超越最高目標才給小懲罰
    ref_tp = tp_h if (tp_h and tp_h > 0) else tp  # 優先使用最高目標
    if ref_tp and p and ref_tp > 0:
        up = (ref_tp - p) / p * 100
        if up > 30:
            sc += 15; pos.append(f"距最高分析師目標+{up:.1f}%，上漲空間充裕")
        elif up > 15:
            sc += 10; pos.append(f"距最高分析師目標+{up:.1f}%")
        elif up > 5:
            sc += 5; pos.append(f"距最高分析師目標+{up:.1f}%")
        elif up >= 0:
            sc += 2
        elif up > -20:
            warn.append(f"現價接近最高分析師目標（超出{abs(up):.1f}%），估值偏高，注意下檔風險")
        else:
            sc -= 5; neg.append(f"現價大幅超越最高分析師目標{abs(up):.1f}%，估值顯著偏高")

    # ── ③ 基本面：月營收 YoY + MoM 雙軌 ─────────────────────────
    # MoM 翻正 = 庫存去化末段早期訊號
    mom_pos = (rev_mom is not None and rev_mom > 0)
    if rev_yoy is not None:
        if rev_yoy >= 20:
            sc += 8; pos.append(f"月營收YoY+{rev_yoy:.1f}%（高成長）")
            if mom_pos: sc += 2; pos.append(f"MoM+{rev_mom:.1f}%雙軌加速成長")
        elif rev_yoy >= 5:
            sc += 4; pos.append(f"月營收YoY+{rev_yoy:.1f}%")
            if mom_pos: sc += 1
        elif rev_yoy >= 0:
            if mom_pos: sc += 2; pos.append(f"月營收持平，MoM+{rev_mom:.1f}%顯示止跌回升")
        elif rev_yoy >= -15:
            # 輕度衰退，MoM 翻正是關鍵早期訊號
            if mom_pos:
                sc += 1; warn.append(f"YoY{rev_yoy:.1f}%仍負，但MoM+{rev_mom:.1f}%，可能為庫存去化末段初期復甦")
            else:
                sc -= 3; neg.append(f"月營收年減{rev_yoy:.1f}%")
        else:
            # 重度衰退
            if mom_pos:
                sc -= 4; neg.append(f"月營收重度衰退YoY{rev_yoy:.1f}%（MoM+{rev_mom:.1f}%翻正，待觀察持續性）")
            else:
                sc -= 8; neg.append(f"月營收大幅年減{rev_yoy:.1f}%")

    # ── ③ 基本面：PE 估值 ────────────────────────────────────────
    if pe and pea and pea > 0:
        pv = (pe - pea) / pea * 100
        if pv < -20: sc += 8; pos.append(f"PE{pe:.1f}x相對低估（低於自身均值{abs(pv):.0f}%）")
        elif pv < 0: sc += 4
        elif pv > 30: sc -= 5; warn.append(f"PE{pe:.1f}x明顯偏高（較自身均值高{pv:.0f}%）")

    # ── ④ 籌碼面：外資 + 異常爆量否決條件 ───────────────────────
    # 偵測「連買後單日倒貨」的假籌碼現象
    f_veto = False; t_veto = False
    if inst and len(inst) >= 2:
        f_vals = [abs(d.get("f", 0)) for d in inst]
        t_vals = [abs(d.get("t", 0)) for d in inst]
        f_5avg = sum(f_vals[:-1]) / max(len(f_vals) - 1, 1)
        t_5avg = sum(t_vals[:-1]) / max(len(t_vals) - 1, 1)
        # 今日外資大量賣超（超過過去5日均量2倍）且前期有買入
        if inst[-1].get("f", 0) < 0 and f_5avg > 0 and abs(inst[-1]["f"]) > f_5avg * 2:
            f_veto = True
            warn.append(f"⚠️ 外資今日賣超{inst[-1]['f']:,}張（超過近期均量{f_5avg:.0f}張的2倍），連買紀錄可靠性存疑，疑似假籌碼")
        if inst[-1].get("t", 0) < 0 and t_5avg > 0 and abs(inst[-1]["t"]) > t_5avg * 2:
            t_veto = True
            warn.append(f"⚠️ 投信今日賣超{inst[-1]['t']:,}張（超過近期均量{t_5avg:.0f}張的2倍），疑似連買後倒貨")

    # 外資評分
    if f_veto:
        sc -= 8; neg.append("外資異常爆量出貨，疑似連買後倒貨（否決連買加分）")
    elif fc >= 3:
        sc += 12; pos.append(f"外資連買{fc}日")
    elif fc >= 1:
        sc += 5; pos.append("外資今日買超")
    elif fc <= -3:
        sc -= 10; neg.append(f"外資連賣{abs(fc)}日")
    elif fc < 0:
        sc -= 4; warn.append("外資今日賣超")

    # 投信評分
    if t_veto:
        sc -= 8; neg.append("投信異常爆量出貨，疑似連買後倒貨（否決連買加分）")
    elif tc >= 5:
        sc += 12; pos.append(f"投信連買{tc}日（深度認養）")
    elif tc >= 3:
        sc += 8; pos.append(f"投信連買{tc}日")
    elif tc >= 1:
        sc += 3; pos.append("投信今日買超")
    elif tc <= -3:
        sc -= 10; neg.append(f"投信連賣{abs(tc)}日")
    elif tc < 0:
        sc -= 4; warn.append("投信今日賣超")

    # 同向獎懲
    if fc > 0 and tc > 0 and not f_veto and not t_veto:
        sc += 5; pos.append("外資投信同向買超，無對作")
    elif fc < 0 and tc < 0:
        sc -= 8; neg.append("外資投信同向賣超，籌碼惡化")

    sc = max(0, min(100, sc))

    # ── ⑤ 評等 + S 級防禦條件 ─────────────────────────────────────
    if sc >= 80:
        # S 級必要防禦：法人至少一方買超 OR 營收正向，否則降為 A
        inst_ok = (fc > 0 and not f_veto) or (tc > 0 and not t_veto)
        rev_ok = (rev_yoy is not None and rev_yoy >= 0) or mom_pos
        if inst_ok or rev_ok:
            rt, lb = "S", "強烈推薦"
        else:
            rt, lb = "A", "建議買入"
            warn.append("⚠️ 達S級分數，但法人籌碼與營收均無正向支撐，保守評為A級（防止純技術超跌錯誤評S）")
    elif sc >= 65:
        rt, lb = "A", "建議買入"
    elif sc >= 45:
        rt, lb = "B", "觀　望"
    else:
        rt, lb = "C", "避　開"

    return sc, rt, lb, pos, neg, warn, _dtl

# ─────────────────────────────────────────────────────────────
# 主分析
# ─────────────────────────────────────────────────────────────
def analyze(sid,token,disposed,full_delivery,delisting,gemini_del,force=False):
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
        pe=per[-1]["pe"] if per else None
        pea=round(sum(r["pe"] for r in per)/len(per),1) if per else None
        pbr=per[-1]["pbr"] if per else None
        time.sleep(0.3)
        rev=get_rev(sid,token)
        rev_yoy=None
        if len(rev)>=13 and rev[-13]["rev"]>0: rev_yoy=round((rev[-1]["rev"]-rev[-13]["rev"])/rev[-13]["rev"]*100,1)
        rev_mom=None
        if len(rev)>=2 and rev[-2]["rev"]>0: rev_mom=round((rev[-1]["rev"]-rev[-2]["rev"])/rev[-2]["rev"]*100,1)
        tp=None; ts="未取得"; tp_h=None; tp_l=None; tp_n=0
        ya=get_yahoo_target(sid)
        if ya: tp=ya["target"]; tp_h=ya["high"]; tp_l=ya["low"]; tp_n=ya["count"]; ts=ya["source"]
        elif pea and pe and rev_yoy is not None and pe>0:
            tp=round(p*(pea/pe)*min(max(1+rev_yoy/100,0.7),1.8),0); ts="PE均值×成長估算"
        sc,rt,lb,pos,neg,warn,_dtl=calc_quant_score(
            p, d5, d200, fc, tc, pe, pea, rev_yoy, tp,
            tp_h=tp_h, ma20=ma20, ma60=ma60, rev_mom=rev_mom, inst=inst)

        # ── 極端跌幅硬風控（疑似下市風險）──────────────────────
        # 若股價較 52 週高點下跌超過 80%，強制降為 C 評等
        r52=pr[-252:] if len(pr)>=252 else pr
        if r52 and len(r52) > 0:
            high_52w = max(ri["high"] for ri in r52)
            if high_52w > 0 and p > 0:
                decline_pct = (high_52w - p) / high_52w * 100
                if decline_pct >= 80:
                    is_hard_risk = True
                    is_delisting = True
                    neg.insert(0, f"🚨 52W高點{high_52w:,.0f}元→現{p:,.0f}元，跌幅{decline_pct:.0f}%，疑似下市/地雷股，強制C評等")
                    warn.insert(0, "此股票技術面顯示極端異常跌幅，可能面臨退市風險，請勿操作")

        if is_hard_risk:
            rt="C"; lb="避　開"
            sc = min(sc, 20)
            if is_full_del: neg.insert(0,"🚨 全額交割股：流動性極差，強制C評等")
            if is_delisting and not any("52W" in n for n in neg): neg.insert(0,"⚠️ 下市警告：面臨下市風險，強制C評等")
        if is_disposed and not is_hard_risk:
            # 強勢飆股例外：高成長+法人強力認養的處置股可能是主升段
            rev_strong = ((rev_yoy is not None and rev_yoy >= 10) or
                          (rev_mom is not None and rev_mom > 5))
            inst_strong = (fc >= 3 or tc >= 3)
            if rev_strong and inst_strong:
                sc = max(0, sc - 3)  # 僅輕罰3分（高成長飆股可能因漲停遭處置）
                warn.insert(0, "⏱ 處置股（因強勢漲停遭處置，法人籌碼+營收仍強，酌減懲罰為-3分）")
            else:
                sc = max(0, sc - 10)
                if sc < 45 and rt in ("S", "A"): rt = "B"; lb = "觀　望"
                warn.insert(0, "⏱ 處置股：每5~20分鐘撮合，流動性受限")
        result={"sid":sid,"name":nm(sid),"price":p,"prev":prev["close"],"chg":chg,
                "ma5":ma5,"ma20":ma20,"ma60":ma60,"ma200":ma200,"d5":d5,"d200":d200,
                "h52":round(max(r["high"] for r in r52),2),
                "l52":round(min(r["low"] for r in r52),2),
                "vol":last["vol"],"last5":[r["close"] for r in pr[-5:]],
                "inst":inst,"fc":fc,"tc":tc,"dc":dc,
                "pe":pe,"pea":pea,"pbr":pbr,"rev_yoy":rev_yoy,"rev_mom":rev_mom,
                "tp":tp,"ts":ts,"tp_h":tp_h,"tp_l":tp_l,"tp_n":tp_n,
                "score":sc,"rating":rt,"label":lb,"pos":pos,"neg":neg,"warn":warn,
                "is_disposed":is_disposed,"is_full_del":is_full_del,
                "is_delisting":is_delisting,"is_hard_risk":is_hard_risk,"date":last["date"],
                "score_detail":_dtl}
        save_cache(sid,result); return result,None
    except Exception as e: return None,str(e)

# ─────────────────────────────────────────────────────────────
# 全市場掃描
# ─────────────────────────────────────────────────────────────
def chip_html(label,net,con_d):
    cls="buy" if net>0 else ("sell" if net<0 else "neut")
    vc="up" if net>0 else ("dn" if net<0 else "")
    sign="+" if net>=0 else ""
    ct=(f"連買{con_d}日" if con_d>=2 else "今日買超" if con_d==1 else
        "今日中性" if con_d==0 else "今日賣超" if con_d==-1 else f"連賣{abs(con_d)}日")
    return f'<div class="chip {cls}"><p>{label}</p><p class="{vc}">{sign}{net:,}張</p><p>{ct}</p></div>'

def build_wiwynn(r):
    sid=r["sid"]; p=r["price"]; chg=r.get("chg",0) or 0
    d5=r.get("d5") or 0; d200=r.get("d200") or 0
    sc=r["score"]; rt=r["rating"]; lb=r["label"]
    fc=r["fc"]; tc=r["tc"]; dc=r["dc"]
    ma5=r["ma5"]; ma20=r["ma20"]
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
    if tp and p:
        up2=(tp-p)/p*100
        if up2>10: tags+=f'<span class="tag tag-p">目標+{up2:.0f}%</span>'
    hard_banner=""
    if r.get("is_delisting"):
        hard_banner='<div class="hard-risk-banner"><strong>⚠️ 下市警告：強制 C 評等</strong><span>面臨下市風險，禁止操作。</span></div>'
    elif r.get("is_full_del"):
        hard_banner='<div class="hard-risk-banner"><strong>🚨 全額交割股：強制 C 評等</strong><span>流動性幾乎為零，嚴禁操作。</span></div>'
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
        up2=(tp-p)/p*100; exceed=up2<0
        bw=min(p/tp*100,100) if tp>0 else 50
        fill_c="linear-gradient(90deg,#27ae60,#e74c3c)" if exceed else "linear-gradient(90deg,#27ae60,#4ecca3)"
        cb=(f'<span style="background:#1a2744;color:#7ec8e3;border:1px solid #2980b9;'
            f'font-size:10px;padding:1px 7px;border-radius:99px;margin-left:5px">👥{tp_n}位</span>') if tp_n>0 else ""
        rng_bar=""
        if tp_h and tp_l and tp_h>tp_l:
            rng=tp_h-tp_l
            cp3=min(max((p-tp_l)/rng*100,0),100)   # 現價位置
            mp3=min(max((tp-tp_l)/rng*100,0),100)  # 均值位置
            rng_bar=(
                f'<div style="margin-top:9px">'
                f'<p style="font-size:10px;font-weight:600;color:#8fa3b8;margin-bottom:5px">'
                f'分析師目標區間（⭐ 評分以最高目標 {tp_h:,.0f} 元為基準）</p>'
                f'<div style="position:relative;border-radius:5px;height:11px;margin-bottom:5px;'
                f'background:linear-gradient(90deg,#27ae60 0%,#f39c12 55%,#e74c3c 100%)">'
                f'<div style="position:absolute;left:{mp3:.0f}%;top:-4px;width:3px;height:19px;'
                f'background:#5dade2;border-radius:2px;z-index:2"></div>'
                f'<div style="position:absolute;left:{cp3:.0f}%;top:-4px;width:3px;height:19px;'
                f'background:#fff;border-radius:2px;z-index:3"></div></div>'
                f'<div style="display:flex;justify-content:space-between;font-size:10px">'
                f'<span style="color:#27ae60;font-weight:600">低 {tp_l:,.0f}</span>'
                f'<span style="color:#5dade2">均 {tp:,.0f} | 現價 {p:,.0f}</span>'
                f'<span style="color:#e67e22;font-weight:700">高⭐ {tp_h:,.0f}</span>'
                f'</div></div>'
            )
        # 評分基準：最高目標（tp_h），顯示：超越均值不顯示警告
        ref_tp = tp_h if (tp_h and tp_h > 0) else tp
        up_to_high = (ref_tp - p) / p * 100 if ref_tp and ref_tp > 0 else 0
        up_to_avg  = (tp - p) / p * 100 if tp and tp > 0 else 0
        exceed_high = up_to_high < 0
        exceed_avg  = up_to_avg < 0
        exc_cls = "dn" if exceed_high else "up"
        if exceed_high:
            upbox = f'<div class="bd" style="margin-top:7px">⚠️ 現價已超越最高分析師目標{abs(up_to_high):.1f}%，估值顯著偏高</div>'
        elif exceed_avg:
            upbox = f'<div class="bw" style="margin-top:7px">🟡 現價超越均值目標（超{abs(up_to_avg):.1f}%），但距最高目標仍有+{up_to_high:.1f}%空間</div>'
        else:
            upbox = f'<div class="bo" style="margin-top:7px">✅ 距最高分析師目標+{up_to_high:.1f}%（評分以最高目標為基準），風險報酬比良好</div>'
        # 預計算：避免 Python < 3.12 f-string 反斜線問題
        _tp_hi=(f'<div class="row"><span class="rl">最高目標</span>'
                f'<span class="rv">{tp_h:,.0f}元</span></div>') if tp_h else ""
        _tp_lo=(f'<div class="row"><span class="rl">最低目標</span>'
                f'<span class="rv">{tp_l:,.0f}元</span></div>') if tp_l else ""
        tp_card=(f'<div class="card"><p class="ct">💰 目標價分析{cb}</p>'
                 f'<div class="row"><span class="rl">來源</span>'
                 f'<span class="rv" style="font-size:11px;color:#8fa3b8">{ts_}</span></div>'
                 f'<div class="row"><span class="rl">分析師均值</span>'
                 f'<span class="rv {exc_cls}" style="font-size:15px;font-weight:700">{tp:,.0f} 元</span></div>'
                 +_tp_hi+_tp_lo+
                 f'<div class="row"><span class="rl">vs 現價（均值）</span>'
                 f'<span class="rv" style="color:{'"#ff6b6b"' if exceed_avg else '"#4ecca3"'}">{up_to_avg:+.1f}%</span></div>'
                 f'<div class="row"><span class="rl">vs 現價（最高⭐）</span>'
                 f'<span class="rv {exc_cls}"><strong>{up_to_high:+.1f}%</strong></span></div>'
                 f'{rng_bar}'
                 f'<div class="tp-wrap"><div class="tp-fill" style="width:{bw:.1f}%;background:{fill_c}"></div></div>'
                 f'<div class="tp-lbl"><span>0</span><span>現價{p:,.0f}</span><span>{tp:,.0f}</span></div>'
                 f'{upbox}</div>')
    mc=ccc(rm or 0); yc=ccc(ry or 0)
    m_c=f"<div class='rf'><p>月營收MoM</p><p class='{mc}'>{(rm or 0):+.1f}%</p></div>" if rm is not None else ""
    y_c=f"<div class='rf'><p>月營收YoY</p><p class='{yc}'>{(ry or 0):+.1f}%</p></div>" if ry is not None else ""
    p_c=f"<div class='rf'><p>PE</p><p>{pe:.1f}x</p></div>" if pe else ""
    pa_c=f"<div class='rf'><p>年均PE</p><p>{pea:.1f}x</p></div>" if pea else ""
    pb_c=f"<div class='rf'><p>PBR</p><p>{pbr:.2f}x</p></div>" if pbr else ""
    val_card=(f"<div class='card'><p class='ct'>📊 估值指標</p><div class='rfg'>{p_c}{pa_c}{pb_c}{m_c}{y_c}</div></div>"
              if any([pe,pea,pbr,rm is not None,ry is not None]) else "")
    evs=[]
    if r.get("is_delisting"):    evs.append(("#e74c3c","⚠️ 下市警告","TWSE/Gemini偵測：面臨下市風險，禁止操作。"))
    elif r.get("is_full_del"):   evs.append(("#e74c3c","🚨 全額交割股","流動性幾乎為零，嚴禁操作。"))
    elif r.get("is_disposed"):   evs.append(("#ffc107","⏱ 處置股","每5~20分鐘才撮合，流動性受限。"))
    if fc>=3 and tc>=3:          evs.append(("#27ae60",f"外資+投信雙向認養（{fc}/{tc}日）","法人籌碼同向，中線多頭確立。"))
    elif fc>=2:                  evs.append(("#27ae60",f"外資連買{fc}日","外資持續進場，籌碼支撐明確。"))
    if tc>=5:                    evs.append(("#27ae60",f"投信深度認養（連買{tc}日）","機構長期建倉，中線信心強。"))
    if d5<-5:                    evs.append(("#27ae60","回測5日線進場點",f"5日乖離{d5:+.1f}%，偏多技術訊號。"))
    elif d5>10:                  evs.append(("#e74c3c","5日線乖離過高","追高風險，建議等回測。"))
    if ry and ry>20:             evs.append(("#27ae60",f"月營收YoY+{ry:.1f}%","業績加速成長，基本面多頭。"))
    if not evs:                  evs.append(("#8fa3b8","目前無特殊事件","維持當前追蹤策略。"))
    ev_html="".join(f'<div class="ev"><div class="dot" style="background:{c}"></div><div><strong>{t}</strong><span>{d3}</span></div></div>' for c,t,d3 in evs[:4])
    stop=round(min(r.get("last5",[p]))*0.97,2)
    ea=(f"{p:,.0f}元（現位進場）" if d5<-3 else
        f"{(ma5 or p)*0.97:,.0f}元（回測5日線）" if d5<=3 else
        f"{(ma5 or p)*0.95:,.0f}元（等待回測）")
    tgt=f"{tp:,.0f}元（{ts_}）" if tp else f"{p*1.10:,.0f}元（+10%估算）"
    risks=""
    if r.get("is_delisting"): risks+='<div class="bd">⚠️ <strong>下市警告：</strong>禁止操作！</div>'
    if r.get("is_full_del"):  risks+='<div class="bd">🚨 <strong>全額交割股：</strong>嚴禁操作！</div>'
    if r.get("is_disposed"):  risks+='<div class="bw">⏱ <strong>處置股：</strong>暫不操作，靜待出關。</div>'
    for n in r["neg"][:3]: risks+=f'<div class="bd">✗ {n}</div>'
    for w in r["warn"][:2]:risks+=f'<div class="bw">⚠ {w}</div>'
    if not risks: risks='<div class="bo">✅ 目前無重大風險警示。</div>'
    today_s=date.today().strftime("%Y/%m/%d"); chg_sign="+" if chg>=0 else ""
    # 正負面訊號（預計算避免 f-string 巢狀）
    pos_html=""
    if r["pos"]: pos_html="<span style='color:#4ecca3'>正：</span>"+"、".join(r['pos'][:2])+"<br>"
    neg_html=""
    if r["neg"]: neg_html="<span style='color:#ff6b6b'>負：</span>"+"、".join(r['neg'][:2])
    # ── 評分明細表格生成 ────────────────────────────────────────
    score_detail_rows = ""
    running = 50
    score_detail_rows += (
        f'<tr style="border-bottom:1px solid #2c3e50">' +
        f'<td style="padding:3px 6px;color:#8fa3b8">起始分數</td>' +
        f'<td style="text-align:right;padding:3px 6px;color:#e8eaf0">—</td>' +
        f'<td style="text-align:right;padding:3px 6px;color:#e8eaf0">50</td></tr>'
    )
    _detail_list = r.get("score_detail", [])
    for item_name, item_delta, item_total in _detail_list:
        if item_delta == 0: continue
        d_color = "#4ecca3" if item_delta > 0 else "#ff6b6b"
        d_sign  = "+" if item_delta > 0 else ""
        score_detail_rows += (
            f'<tr style="border-bottom:1px solid #2c3e50">' +
            f'<td style="padding:3px 6px;color:#e8eaf0">{item_name}</td>' +
            f'<td style="text-align:right;padding:3px 6px;color:{d_color};font-weight:600">{d_sign}{item_delta}</td>' +
            f'<td style="text-align:right;padding:3px 6px;color:#e8eaf0">{item_total}</td></tr>'
        )
    # 加入 pos/neg 未在 detail 中的項目（補充說明）
    all_factors = [name for name,_,_ in _detail_list]
    if not _detail_list:  # 若無明細（老版快取），用正負面清單代替
        for p_item in r.get("pos",[]):
            score_detail_rows += (
                f'<tr style="border-bottom:1px solid #2c3e50">' +
                f'<td style="padding:3px 6px;color:#4ecca3">✅ {p_item[:30]}</td>' +
                f'<td colspan="2" style="text-align:right;padding:3px 6px;color:#4ecca3">正向</td></tr>'
            )
        for n_item in r.get("neg",[]):
            score_detail_rows += (
                f'<tr style="border-bottom:1px solid #2c3e50">' +
                f'<td style="padding:3px 6px;color:#ff6b6b">❌ {n_item[:30]}</td>' +
                f'<td colspan="2" style="text-align:right;padding:3px 6px;color:#ff6b6b">負向</td></tr>'
            )
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
<div class="rsc"><span>0安全</span><span>50中性</span><span>80極危</span><span>100</span></div>
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
<div class="card"><p class="ct">📊 評分明細（各項貢獻）</p><div style="font-size:11px;color:#8fa3b8;margin-bottom:8px">起始50分，以下為各因素加減分明細</div><table style="width:100%;border-collapse:collapse;font-size:11px"><tr style="border-bottom:1px solid #3d5166"><th style="text-align:left;color:#8fa3b8;padding:3px 4px">因素</th><th style="text-align:right;color:#8fa3b8;padding:3px 4px">貢獻</th><th style="text-align:right;color:#8fa3b8;padding:3px 4px">累計</th></tr>{score_detail_rows}<tr style="border-top:2px solid #5d7a99;font-weight:700"><td style="padding:5px 4px;color:#e8eaf0">總分</td><td></td><td style="text-align:right;padding:5px 4px;font-size:14px;color:{vbc}">{sc}/100</td></tr></table></div><div class="card"><p class="ct">📅 事件更新</p>{ev_html}</div>
<div class="card"><p class="ct">🎯 操作策略</p>
<div class="st"><span class="si">🟢</span><div><strong>積極進場：</strong>{ea}</div></div>
<div class="st"><span class="si">🟡</span><div><strong>保守進場：</strong>{fv(ma20,'元',0)}（月線支撐）</div></div>
<div class="st"><span class="si">🔴</span><div><strong>短線停損：</strong>{stop:,.0f}元</div></div>
<div class="st"><span class="si">🎯</span><div><strong>目標：</strong>{tgt}</div></div>
<div class="sg"><div class="sb"><strong>📈 多頭</strong><br>法人持續買超+技術強勢</div>
<div class="sr"><strong>📉 空頭</strong><br>外資連賣+跌破月線</div></div></div>
<div class="card"><p class="ct">⚠️ 風險提示</p>{risks}</div>
<div class="footer">{r['name']}（{sid}）| {r.get('date',today_s)} | 評分{sc}/100（純量化）| {ts_}<br>數據：FinMind API | 僅供參考，不構成投資建議</div>
</div></body></html>"""

def build_full_html(results):
    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    nav="".join(f'<a href="#s{r["sid"]}" style="display:inline-block;font-size:11px;padding:3px 9px;border-radius:14px;font-weight:600;text-decoration:none;margin:2px;background:{RC[r["rating"]]};color:white">{r["name"]}</a>'
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

# ─────────────────────────────────────────────────────────────
# 頁面
# ─────────────────────────────────────────────────────────────

import json as _json

# ─────────────────────────────────────────────────────────────
# 籌碼掃描輔助函式（四層架構）
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=14400)
def fetch_twse_industry_map():
    """TWSE 股票→產業 對應（BWIBBU_ALL，含產業名稱）"""
    out = {}
    try:
        r = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
            headers=HDR, timeout=20, verify=False)
        if r.status_code == 200:
            for item in r.json():
                code = str(item.get("Code","")).strip()
                ind  = str(item.get("Industry","")).strip()
                if code and ind:
                    out[code] = ind
    except Exception:
        pass
    return out

@st.cache_data(ttl=14400)
def fetch_tpex_industry_map():
    """TPEx 股票→產業 對應"""
    out = {}
    try:
        r = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_listed_companies",
            headers=HDR, timeout=20, verify=False)
        if r.status_code == 200:
            for item in r.json():
                code = str(item.get("SecuritiesCompanyCode","")).strip()
                ind  = str(item.get("Industry","")).strip()
                if code and ind:
                    out[code] = ind
    except Exception:
        pass
    return out

def compute_industry_stats(ind_map, prices, insts, hard_risk):
    """計算各產業統計：漲跌幅、成交量、法人淨買"""
    from collections import defaultdict as _dd
    bucket = _dd(list)
    for code, ind in ind_map.items():
        if code in hard_risk:
            continue
        p = prices.get(code)
        if p and p.get("price", 0) > 0:
            inst = insts.get(code, {})
            bucket[ind].append({
                "code":  code,
                "name":  nm(code),
                "price": p["price"],
                "chg":   p.get("chg_pct", 0) or 0,
                "vol":   p.get("volume", 0) or 0,
                "f":     inst.get("f", 0) or 0,
                "t":     inst.get("t", 0) or 0,
            })

    stats = []
    total_vol_all = sum(s["vol"] for stocks in bucket.values() for s in stocks) or 1
    for ind_name, stocks in bucket.items():
        if not stocks:
            continue
        total_vol = sum(s["vol"] for s in stocks)
        avg_chg   = round(sum(s["chg"] for s in stocks) / len(stocks), 2)
        net_inst  = sum(s["f"] + s["t"] for s in stocks)
        up_cnt    = sum(1 for s in stocks if s["chg"] > 0)
        dn_cnt    = sum(1 for s in stocks if s["chg"] < 0)
        weight_pct = round(total_vol / total_vol_all * 100, 2)

        # 比重差（相對加權）：做為資金集中度指標
        exp_weight = round(100 / max(len(bucket), 1), 2)
        weight_diff = round(weight_pct - exp_weight, 2)

        stats.append({
            "name":       ind_name,
            "count":      len(stocks),
            "avg_chg":    avg_chg,
            "total_vol":  total_vol,
            "weight_pct": weight_pct,
            "weight_diff": weight_diff,
            "net_inst":   net_inst,
            "up":         up_cnt,
            "dn":         dn_cnt,
            "stocks":     sorted(stocks, key=lambda x: x["chg"], reverse=True),
        })
    return stats


def build_treemap_html(stocks, title="熱力圖"):
    """產業個股熱力圖（台股慣例：紅漲綠跌）"""
    if not stocks:
        return "<body style='background:#1a2332;color:#e8eaf0;padding:20px'>無數據</body>"

    def chg_color(chg):
        if chg >= 9:  return "#8b0000"
        if chg >= 6:  return "#c0392b"
        if chg >= 3:  return "#e74c3c"
        if chg >= 1:  return "#ff6b6b"
        if chg > 0:   return "#ff9999"
        if chg == 0:  return "#2d3436"
        if chg > -1:  return "#aaffaa"
        if chg > -3:  return "#55efc4"
        if chg > -6:  return "#27ae60"
        if chg > -9:  return "#1e8449"
        return "#145a32"

    js_data = []
    for s in stocks:
        js_data.append({
            "name":  s.get("name", s.get("code", "")),
            "code":  s.get("code", ""),
            "price": s.get("price", 0),
            "chg":   round(s.get("chg", 0), 2),
            "vol":   max(s.get("vol", 1), 1),
            "color": chg_color(s.get("chg", 0)),
        })

    data_json = _json.dumps(js_data, ensure_ascii=False)

    return f"""<!DOCTYPE html><html lang="zh-TW"><head>
<meta charset="UTF-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#1a2332;font-family:'Helvetica Neue',Arial,sans-serif}}
#title{{color:#e8eaf0;font-size:14px;font-weight:700;padding:8px 12px}}
#treemap{{position:relative;width:100%;height:460px;overflow:hidden}}
.cell{{position:absolute;display:flex;flex-direction:column;align-items:center;justify-content:center;
        border:1px solid #1a2332;border-radius:3px;cursor:default;overflow:hidden;
        transition:opacity .15s}}
.cell:hover{{opacity:.85;z-index:10}}
.cell .nm{{font-size:12px;font-weight:700;color:#fff;text-shadow:1px 1px 2px rgba(0,0,0,.9);
           white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:95%}}
.cell .pct{{font-size:11px;color:#fff;text-shadow:1px 1px 2px rgba(0,0,0,.9)}}
.cell .px{{font-size:10px;color:rgba(255,255,255,.75)}}
.legend{{display:flex;flex-direction:column;align-items:center;padding:6px 0}}
.lg-bar{{width:280px;height:12px;border-radius:6px;
          background:linear-gradient(90deg,#145a32,#27ae60,#2d3436,#e74c3c,#8b0000)}}
.lg-lbl{{display:flex;justify-content:space-between;width:280px;font-size:10px;color:#8fa3b8;margin-top:2px}}
</style></head>
<body>
<div id="title">🌡️ {title} — 方塊大小 = 成交量，顏色 = 漲跌幅（🔴漲 🟢跌）</div>
<div id="treemap"></div>
<div class="legend">
<div class="lg-bar"></div>
<div class="lg-lbl"><span>-10%+</span><span>-5%</span><span>平盤</span><span>+5%</span><span>+10%+</span></div>
</div>
<script>
const DATA = {data_json};
const cont = document.getElementById('treemap');

function layout(items, x, y, w, h) {{
    const total = items.reduce((s,d)=>s+d.vol,0)||1;
    const cells = [];
    let cx=x, cy=y, rw=w, rh=h;
    let row=[], rv=0;

    function place(row, rv, px, py, pw, ph) {{
        const short=Math.min(pw,ph);
        const side=rv/total*(pw*ph)/short;
        let ox=px,oy=py;
        for(const r of row) {{
            const f=r.vol/rv;
            if(pw<=ph) {{
                cells.push({{...r,x:ox,y:oy,w:side,h:f*short}});
                oy+=f*short;
            }} else {{
                cells.push({{...r,x:ox,y:oy,w:f*side,h:short}});
                ox+=f*side;
            }}
        }}
        return side;
    }}

    for(let i=0;i<items.length;i++) {{
        const d=items[i];
        const test=[...row,d];
        const tv=rv+d.vol;
        const short=Math.min(rw,rh);
        const side=tv/total*(rw*rh)/short;
        const bestAsp=test.reduce((max,r)=>{{
            const f=r.vol/tv;
            const rlen=f*(rw<=rh?rh:rw)*short/side;
            return Math.max(max,Math.max(side/rlen,rlen/side));
        }},0);

        if(!row.length||bestAsp<(row.reduce((max,r)=>{{
            const f=r.vol/rv;
            const sh=Math.min(rw,rh);
            const sd=rv/total*(rw*rh)/sh;
            const rl=f*(rw<=rh?rh:rw)*sh/sd;
            return Math.max(max,Math.max(sd/rl,rl/sd));
        }},0)||Infinity)) {{
            row.push(d); rv+=d.vol;
        }} else {{
            const side=place(row,rv,cx,cy,rw,rh);
            if(rw<=rh) {{ cy+=side; rh-=side; }} else {{ cx+=side; rw-=side; }}
            row=[d]; rv=d.vol;
        }}
        if(i===items.length-1 && row.length) place(row,rv,cx,cy,rw,rh);
    }}
    return cells;
}}

function render() {{
    const W=cont.offsetWidth||800, H=460;
    const sorted=[...DATA].sort((a,b)=>b.vol-a.vol);
    const cells=layout(sorted,0,0,W,H);
    cont.innerHTML='';
    cells.forEach(c=>{{
        const div=document.createElement('div');
        div.className='cell';
        div.style.left=Math.round(c.x+1)+'px';
        div.style.top=Math.round(c.y+1)+'px';
        div.style.width=Math.max(Math.round(c.w-2),2)+'px';
        div.style.height=Math.max(Math.round(c.h-2),2)+'px';
        div.style.background=c.color;
        div.title=c.name+' '+c.code+'\n'+c.price+'元 '+(c.chg>=0?'+':'')+c.chg+'%';
        const sign=c.chg>=0?'+':'';
        if(c.w>50&&c.h>35) {{
            div.innerHTML=(c.w>70&&c.h>50?`<div class="nm">${{c.name}}</div>`:'') +
                `<div class="pct">${{sign}}${{c.chg.toFixed(1)}}%</div>` +
                (c.h>65?`<div class="px">${{c.price}}元</div>`:'');
        }}
        cont.appendChild(div);
    }});
}}
render();
window.addEventListener('resize',render);
</script></body></html>"""


def _scanner_layer1_2(stats, view_key):
    """第一層 + 第二層：產業總覽 + 完整清單"""
    if not stats:
        st.warning("無法計算產業數據，請確認股價數據已載入")
        return

    # ── 第一層：強勢 / 弱勢 並排 ─────────────────────────────
    st.markdown("#### 📊 今日產業透視總覽")
    st.caption("左：強勢族群（漲幅前5）｜右：弱勢族群（跌幅前5）")

    sorted_asc  = sorted(stats, key=lambda x: x["avg_chg"])
    sorted_desc = sorted(stats, key=lambda x: x["avg_chg"], reverse=True)
    top5 = sorted_desc[:5]
    bot5 = sorted_asc[:5]

    c_l, c_r = st.columns(2)
    with c_l:
        st.markdown("**🔴 強勢族群（今日漲幅）**")
        for s in top5:
            chg = s["avg_chg"]
            bar_w = min(int(abs(chg) / 10 * 100), 100)
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                f'<span style="width:80px;font-size:12px;color:#e8eaf0;font-weight:600">{s["name"][:6]}</span>'
                f'<div style="flex:1;background:#2c3e50;border-radius:3px;height:18px;position:relative">'
                f'<div style="width:{bar_w}%;height:100%;background:#e74c3c;border-radius:3px"></div>'
                f'<span style="position:absolute;right:4px;top:1px;font-size:11px;color:#fff;font-weight:700">'
                f'+{chg:.2f}%</span></div>'
                f'<span style="font-size:10px;color:#8fa3b8;width:40px;text-align:right">{s["weight_pct"]:.1f}%</span>'
                f'</div>', unsafe_allow_html=True)
    with c_r:
        st.markdown("**🟢 弱勢族群（今日跌幅）**")
        for s in bot5:
            chg = s["avg_chg"]
            bar_w = min(int(abs(chg) / 10 * 100), 100)
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                f'<span style="width:80px;font-size:12px;color:#e8eaf0;font-weight:600">{s["name"][:6]}</span>'
                f'<div style="flex:1;background:#2c3e50;border-radius:3px;height:18px;position:relative">'
                f'<div style="width:{bar_w}%;height:100%;background:#27ae60;border-radius:3px"></div>'
                f'<span style="position:absolute;right:4px;top:1px;font-size:11px;color:#fff;font-weight:700">'
                f'{chg:.2f}%</span></div>'
                f'<span style="font-size:10px;color:#8fa3b8;width:40px;text-align:right">{s["weight_pct"]:.1f}%</span>'
                f'</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── 第二層：完整清單 + 排序 ─────────────────────────────
    st.markdown("#### 📋 所有產業詳細清單")
    sort_opt = st.radio("排序方式", ["漲幅", "跌幅", "成交比重", "比重差", "法人買超"],
                        horizontal=True, label_visibility="collapsed", key=f"sort_{view_key}")

    sort_map = {
        "漲幅":   lambda x: -x["avg_chg"],
        "跌幅":   lambda x:  x["avg_chg"],
        "成交比重": lambda x: -x["weight_pct"],
        "比重差":  lambda x: -x["weight_diff"],
        "法人買超": lambda x: -x["net_inst"],
    }
    sorted_stats = sorted(stats, key=sort_map[sort_opt])
    max_chg = max(abs(s["avg_chg"]) for s in sorted_stats) or 1
    max_wt  = max(s["weight_pct"] for s in sorted_stats) or 1

    for s in sorted_stats:
        chg = s["avg_chg"]
        chg_c = "#e74c3c" if chg > 0 else ("#27ae60" if chg < 0 else "#8fa3b8")
        chg_sign = "+" if chg > 0 else ""
        bar_w_chg = int(abs(chg) / max_chg * 100)
        bar_w_wt  = int(s["weight_pct"] / max_wt * 100)
        inst_c = "#e74c3c" if s["net_inst"] > 0 else ("#27ae60" if s["net_inst"] < 0 else "#8fa3b8")
        inst_sign = "+" if s["net_inst"] >= 0 else ""

        c1, c2, c3 = st.columns([3, 4, 1])
        with c1:
            st.markdown(
                f'<div style="font-size:13px;font-weight:700;color:#e8eaf0">{s["name"]}</div>'
                f'<div style="font-size:10px;color:#8fa3b8">↑{s["up"]} ↓{s["dn"]} 共{s["count"]}支</div>',
                unsafe_allow_html=True)
        with c2:
            diff_c = "#e74c3c" if s["weight_diff"] > 0 else "#27ae60"
            diff_sign = "+" if s["weight_diff"] >= 0 else ""
            st.markdown(
                f'<div style="margin-bottom:3px">'
                f'<span style="color:{chg_c};font-weight:700;font-size:14px">{chg_sign}{chg:.2f}%</span>'
                f'<span style="color:#8fa3b8;font-size:10px;margin-left:8px">'
                f'比重 {s["weight_pct"]:.1f}%（{diff_sign}{s["weight_diff"]:.1f}%）</span>'
                f'</div>'
                f'<div style="background:#2c3e50;border-radius:3px;height:6px;margin-bottom:2px">'
                f'<div style="width:{bar_w_chg}%;height:6px;background:{chg_c};border-radius:3px"></div></div>'
                f'<div style="background:#2c3e50;border-radius:3px;height:4px">'
                f'<div style="width:{bar_w_wt}%;height:4px;background:#5d7a99;border-radius:3px"></div></div>',
                unsafe_allow_html=True)
        with c3:
            st.markdown(
                f'<div style="font-size:11px;color:{inst_c};text-align:right">'
                f'{inst_sign}{s["net_inst"]:,}</div>'
                f'<div style="font-size:9px;color:#8fa3b8;text-align:right">法人張</div>',
                unsafe_allow_html=True)
            if st.button("→", key=f"into_{view_key}_{s['name']}", help=f"查看{s['name']}個股"):
                st.session_state.scanner_sector = s["name"]
                st.session_state.scanner_heatmap = False
                st.rerun()
        st.divider()


def _scanner_layer3_4(sector_name, stats, prices, insts):
    """第三層（個股清單）+ 第四層（熱力圖）"""
    s_data = next((s for s in stats if s["name"] == sector_name), None)
    if not s_data:
        st.warning(f"找不到 {sector_name} 的數據")
        return

    # 返回按鈕
    c_b, c_t = st.columns([1, 5])
    with c_b:
        if st.button("⬅ 返回", use_container_width=True, key="back_to_list"):
            st.session_state.scanner_sector = None
            st.rerun()
    with c_t:
        st.markdown(f"### {sector_name}")
        avg_chg = s_data["avg_chg"]
        chg_c = "#e74c3c" if avg_chg > 0 else ("#27ae60" if avg_chg < 0 else "#8fa3b8")
        sign = "+" if avg_chg >= 0 else ""
        st.markdown(
            f'<span style="color:{chg_c};font-size:18px;font-weight:700">{sign}{avg_chg:.2f}%</span>'
            f'<span style="color:#8fa3b8;font-size:12px;margin-left:8px">'
            f'共{s_data["count"]}支 ↑{s_data["up"]} ↓{s_data["dn"]} '
            f'法人{s_data["net_inst"]:+,}張 比重{s_data["weight_pct"]:.1f}%</span>',
            unsafe_allow_html=True)

    # 清單 / 熱力圖 切換
    tab_list, tab_heat = st.tabs(["📋 清單模式", "🌡️ 熱力圖"])

    with tab_list:
        stocks = s_data["stocks"]
        if stocks:
            rows = []
            for s in stocks:
                chg = s["chg"]
                rows.append({
                    "代號": s["code"],
                    "名稱": s["name"],
                    "成交價": s["price"],
                    "漲跌%": round(chg, 2),
                    "總量(張)": s["vol"],
                    "外資(張)": s["f"],
                    "投信(張)": s["t"],
                    "法人合計": s["f"] + s["t"],
                })
            rows.sort(key=lambda x: x["漲跌%"], reverse=True)
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("此產業今日無數據")

    with tab_heat:
        stocks = s_data["stocks"]
        if stocks:
            heat_html = build_treemap_html(stocks, f"{sector_name} 熱力圖")
            components.html(heat_html, height=560, scrolling=False)
        else:
            st.info("此產業今日無數據")


def tab_scanner():
    """籌碼掃描 — 四層產業分析"""
    st.markdown("### 📡 籌碼掃描 — 產業透視")

    # 重新整理按鈕
    col_r, col_b = st.columns([3, 1])
    with col_r:
        if st.button("🔄 重新整理全市場數據", use_container_width=True, key="scanner_refresh"):
            for fn in [fetch_twse_prices_all, fetch_twse_institution_all,
                       fetch_tpex_prices_all, fetch_tpex_institution_all,
                       fetch_twse_industry_map, fetch_tpex_industry_map,
                       fetch_disposed_cached, fetch_full_delivery_cached, fetch_delisting_cached]:
                fn.clear()
            st.session_state.gemini_delisting = set()
            st.session_state.gemini_delisting_ts = None
            st.session_state.scanner_sector = None
            st.rerun()
    with col_b:
        if st.session_state.get("scanner_sector"):
            if st.button("⬅ 返回列表", use_container_width=True, key="scanner_back_top"):
                st.session_state.scanner_sector = None
                st.rerun()

    # 取得市場數據
    _qdate = get_institution_query_date_str()
    with st.spinner("📡 取得全市場數據..."):
        twse_p = fetch_twse_prices_all()
        tpex_p = fetch_tpex_prices_all()
        prices  = {**twse_p, **tpex_p}
        update_names_from_market(prices)
        twse_i  = fetch_twse_institution_all(_qdate)
        tpex_i  = fetch_tpex_institution_all(_qdate)
        insts   = {**twse_i, **tpex_i}
        disposed = fetch_disposed_cached()
        full_del = fetch_full_delivery_cached()
        delist   = fetch_delisting_cached()
        hard_risk = full_del | delist | st.session_state.gemini_delisting

    # Gemini 下市偵測
    gkey = st.session_state.gemini_key
    if gkey:
        with st.spinner("🤖 偵測下市風險股..."):
            g_del = gemini_fetch_delisting(gkey)
        if g_del:
            st.warning(f"🤖 Gemini 偵測到 {len(g_del)} 支下市風險股：{', '.join(sorted(g_del)[:8])}")
        hard_risk = hard_risk | g_del

    # 時間說明
    now_tw = datetime.utcnow() + timedelta(hours=8)
    inst_date = get_institution_query_date()
    time_note = "（昨日盤後）" if now_tw.hour < 17 else "（今日盤後）"
    inst_note = f"法人：{len(insts)} 檔" if insts else "法人：今日未取得"
    st.caption(f"股價：{len(prices)} 檔 | {inst_note} | {inst_date.strftime('%Y/%m/%d')} {time_note}")

    if not prices:
        st.error("⚠️ 無法取得股價數據，請重新整理")
        return

    # ── 三個主頁籤 ─────────────────────────────────────────────
    t_listed, t_otc, t_custom = st.tabs(["📈 上市（TWSE官方分類）", "📊 上櫃（TPEx官方分類）", "🔍 細產業（自選分類）"])

    # ── 上市（TWSE 官方產業分類）────────────────────────────────
    with t_listed:
        if not st.session_state.get("scanner_sector"):
            with st.spinner("載入 TWSE 產業分類..."):
                ind_map = fetch_twse_industry_map()
            if ind_map:
                stats = compute_industry_stats(ind_map, twse_p, twse_i, hard_risk)
                _scanner_layer1_2(stats, "listed")
            else:
                st.warning("TWSE 產業分類數據暫無法取得，請稍後重試")
        else:
            with st.spinner("載入產業數據..."):
                ind_map = fetch_twse_industry_map()
                stats = compute_industry_stats(ind_map, twse_p, twse_i, hard_risk)
            _scanner_layer3_4(st.session_state.scanner_sector, stats, twse_p, twse_i)

    # ── 上櫃（TPEx 官方產業分類）────────────────────────────────
    with t_otc:
        if not st.session_state.get("scanner_sector"):
            with st.spinner("載入 TPEx 產業分類..."):
                tpex_ind_map = fetch_tpex_industry_map()
            if tpex_ind_map:
                stats_tpex = compute_industry_stats(tpex_ind_map, tpex_p, tpex_i, hard_risk)
                _scanner_layer1_2(stats_tpex, "otc")
            else:
                st.warning("TPEx 產業分類數據暫無法取得，顯示細產業分類")
                # 降級：用 SECTOR_MAP 但只取上櫃股
                _sector_stats = compute_sector_analysis_custom(tpex_p, tpex_i, hard_risk)
                _scanner_layer1_2(_sector_stats, "otc_fallback")
        else:
            with st.spinner("載入產業數據..."):
                tpex_ind_map = fetch_tpex_industry_map()
                stats_tpex = compute_industry_stats(tpex_ind_map, tpex_p, tpex_i, hard_risk)
            _scanner_layer3_4(st.session_state.scanner_sector, stats_tpex, tpex_p, tpex_i)

    # ── 細產業（自選 SECTOR_MAP 分類）───────────────────────────
    with t_custom:
        if not st.session_state.get("scanner_sector"):
            custom_stats = compute_sector_analysis_custom(prices, insts, hard_risk)
            _scanner_layer1_2(custom_stats, "custom")
        else:
            custom_stats = compute_sector_analysis_custom(prices, insts, hard_risk)
            _scanner_layer3_4(st.session_state.scanner_sector, custom_stats, prices, insts)


def compute_sector_analysis_custom(prices, insts, hard_risk):
    """用自定義 SECTOR_MAP 計算產業統計（細產業模式）"""
    stats = []
    total_vol_all = sum(p.get("volume", 0) or 0 for p in prices.values()) or 1
    for sec_name, info in SECTOR_MAP.items():
        stocks = []
        for code in info.get("stocks", []):
            if code in hard_risk:
                continue
            p = prices.get(code)
            if p and p.get("price", 0) > 0:
                inst = insts.get(code, {})
                stocks.append({
                    "code":  code,
                    "name":  nm(code),
                    "price": p["price"],
                    "chg":   p.get("chg_pct", 0) or 0,
                    "vol":   p.get("volume", 0) or 0,
                    "f":     inst.get("f", 0) or 0,
                    "t":     inst.get("t", 0) or 0,
                })
        if not stocks:
            continue
        total_vol = sum(s["vol"] for s in stocks)
        avg_chg   = round(sum(s["chg"] for s in stocks) / len(stocks), 2)
        net_inst  = sum(s["f"] + s["t"] for s in stocks)
        up_cnt    = sum(1 for s in stocks if s["chg"] > 0)
        dn_cnt    = sum(1 for s in stocks if s["chg"] < 0)
        weight_pct  = round(total_vol / total_vol_all * 100, 2)
        exp_weight  = round(100 / max(len(SECTOR_MAP), 1), 2)
        weight_diff = round(weight_pct - exp_weight, 2)
        stats.append({
            "name":       sec_name,
            "count":      len(stocks),
            "avg_chg":    avg_chg,
            "total_vol":  total_vol,
            "weight_pct": weight_pct,
            "weight_diff": weight_diff,
            "net_inst":   net_inst,
            "up":         up_cnt,
            "dn":         dn_cnt,
            "stocks":     sorted(stocks, key=lambda x: x["chg"], reverse=True),
        })
    return stats


def tab_analysis():
    token=st.session_state.token; gkey=st.session_state.gemini_key
    results=st.session_state.results
    st.markdown("### 🔍 個股分析")
    if token:
        lr=st.session_state.last_run
        st.success(f"✅ Token 已設定 | 上次：{lr.strftime('%m/%d %H:%M') if lr else '尚未執行'}")
    else:
        st.error("⚠️ 請到「⚙️ 設定」填入 FinMind Token")

    # 股票搜尋
    st.markdown("---")
    st.markdown("#### 🔍 搜尋股票（支援中文名稱 或 股號）")
    c_s1,c_s2=st.columns([4,1])
    with c_s1:
        query=st.text_input("搜尋",placeholder="輸入股號（如 2330）或中文名稱（如 台積電）",label_visibility="collapsed")
    with c_s2:
        st.button("搜尋",use_container_width=True,key="search_btn")
    if query:
        res_s=search_stocks(query)
        if res_s:
            opts=[f"{c} {n}" for c,n in res_s]
            sel_i=st.selectbox("搜尋結果",range(len(opts)),format_func=lambda i:opts[i],label_visibility="collapsed")
            sel_code,sel_name=res_s[sel_i]
            ca,cb,cc2=st.columns(3)
            with ca:
                if st.button(f"📊 立即分析 {sel_name}",use_container_width=True,disabled=not token):
                    disposed=fetch_disposed_cached(); full_del=fetch_full_delivery_cached()
                    delisting=fetch_delisting_cached(); gemini_del=st.session_state.gemini_delisting
                    with st.spinner(f"分析 {sel_name}（{sel_code}）..."):
                        r2,err=analyze(sel_code,token,disposed,full_del,delisting,gemini_del,force=True)
                    if r2:
                        idx2=next((i for i,x in enumerate(st.session_state.results) if x["sid"]==sel_code),None)
                        if idx2 is not None: st.session_state.results[idx2]=r2
                        else: st.session_state.results=[r2]+st.session_state.results
                        save_results_cache(st.session_state.results)
                        st.success(f"✅ {sel_name} 完成！評等 {r2['rating']}（{r2['score']}分）")
                        st.rerun()
                    else: st.error(f"❌ 失敗：{err}")
            with cb:
                if st.button("➕ 加入自選清單",use_container_width=True):
                    codes=[s.strip() for s in st.session_state.stock_list.split(",") if s.strip()]
                    if sel_code not in codes:
                        codes.insert(0,sel_code); st.session_state.stock_list=",".join(codes)
                        st.success(f"✅ 已加入：{sel_code} {sel_name}")
                    else: st.info(f"已在清單中：{sel_code}")
            with cc2: st.caption(f"代號：{sel_code} | 名稱：{sel_name}")
        else: st.warning(f"找不到「{query}」，請確認股號或名稱")

    st.markdown("---")
    sids=[s.strip() for s in st.session_state.stock_list.split(",") if s.strip()]
    st.markdown(f"**自選清單：{len(sids)} 支** — `{', '.join(sids[:5])}{'...' if len(sids)>5 else ''}`")
    c1,c2=st.columns([3,1])
    with c1: run=st.button("🔄 分析全部自選股",disabled=not token,use_container_width=True)
    with c2: force=st.checkbox("強制重爬",value=False)

    if not results:
        cached=load_results_cache()
        if cached:
            st.session_state.results=cached; results=cached
            st.info(f"📦 已載入快取：{len(results)} 支")

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
            save_results_cache(st.session_state.results); st.success(f"✅ 完成！{len(all_res)} 支，已存快取")
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
                       f"portfolio_{date.today().strftime('%Y%m%d')}.html","text/html",
                       use_container_width=True)
    st.markdown("---")
    sorted_r=sorted(results,key=lambda x:x["score"],reverse=True)
    opts=[f"{r['rating']} {r['name']}（{r['sid']}） — {r['score']}分 | {r['price']:,.0f}元 {r['chg']:+.1f}%"
          for r in sorted_r]
    sel=st.selectbox("🔍 選擇股票查看完整報告",range(len(opts)),format_func=lambda i:opts[i])
    r_sel=sorted_r[sel]
    ca,cb=st.columns(2)
    with ca:
        html=build_wiwynn(r_sel)
        st.download_button(f"📄 下載 {r_sel['name']} 報告",html,
                           f"{r_sel['sid']}_{date.today().strftime('%Y%m%d')}.html","text/html",
                           use_container_width=True)
    with cb:
        if st.button(f"🔄 重新分析 {r_sel['name']}",use_container_width=True):
            disposed=fetch_disposed_cached(); full_del=fetch_full_delivery_cached()
            delisting=fetch_delisting_cached(); gemini_del=st.session_state.gemini_delisting
            with st.spinner("重新抓取..."): new_r,err=analyze(r_sel["sid"],token,disposed,full_del,delisting,gemini_del,force=True)
            if new_r:
                idx=next((i for i,x in enumerate(st.session_state.results) if x["sid"]==r_sel["sid"]),None)
                if idx is not None: st.session_state.results[idx]=new_r
                save_results_cache(st.session_state.results); st.success("✅ 已更新"); st.rerun()
            else: st.error(f"❌ {err}")
    components.html(html,height=2700,scrolling=True)


def tab_calendar():
    """財經行事曆（Gemini 驅動 + 台灣財報截止日）"""
    st.markdown("### 📅 財經行事曆")
    gkey = st.session_state.gemini_key

    # ── 月份導覽（避免 if/else 單行寫法）──────────────────────
    c1, c2, c3, c4 = st.columns([1, 3, 3, 1])
    with c1:
        if st.button("◄", use_container_width=True, key="cal_prev"):
            if st.session_state.cal_month == 1:
                st.session_state.cal_month = 12
                st.session_state.cal_year -= 1
            else:
                st.session_state.cal_month -= 1
            st.session_state.cal_events = []
            st.session_state.cal_events_ts = None
            st.rerun()
    with c2:
        mzh_list = ["一","二","三","四","五","六","七","八","九","十","十一","十二"]
        mzh = mzh_list[st.session_state.cal_month - 1]
        st.markdown(
            f'<div style="text-align:center;font-size:17px;font-weight:700;color:#fff;padding:8px">' +
            f'{st.session_state.cal_year}年{mzh}月</div>',
            unsafe_allow_html=True)
    with c3:
        if gkey:
            st.success("🤖 Gemini 搜尋已啟用")
        else:
            st.warning("設定 Gemini Key 以啟用 AI 搜尋")
    with c4:
        if st.button("►", use_container_width=True, key="cal_next"):
            if st.session_state.cal_month == 12:
                st.session_state.cal_month = 1
                st.session_state.cal_year += 1
            else:
                st.session_state.cal_month += 1
            st.session_state.cal_events = []
            st.session_state.cal_events_ts = None
            st.rerun()

    c_r, c_t = st.columns(2)
    with c_r:
        if st.button("🔄 重新搜尋事件", use_container_width=True, key="cal_refresh"):
            st.session_state.cal_events = []
            st.session_state.cal_events_ts = None
            st.rerun()
    with c_t:
        if st.button("📅 回到本月", use_container_width=True, key="cal_today"):
            st.session_state.cal_year = date.today().year
            st.session_state.cal_month = date.today().month
            st.session_state.cal_events = []
            st.session_state.cal_events_ts = None
            st.rerun()

    # ── 取得事件（含錯誤保護）──────────────────────────────────
    events = []
    try:
        with st.spinner("🤖 搜尋財經事件..."):
            events = gemini_fetch_events(gkey, st.session_state.cal_year, st.session_state.cal_month)
    except Exception as err:
        st.warning(f"事件載入失敗：{err}，顯示預設事件")
        try:
            events = _default_events(st.session_state.cal_year, st.session_state.cal_month)
        except Exception:
            events = []

    if not events:
        st.error("事件清單為空，請重新搜尋")
        return

    if not gkey:
        st.info("💡 未設定 Gemini API Key，顯示預設重要事件（含台灣財報截止日）。設定後可獲得完整 AI 行事曆。")

    # ── 統計 ─────────────────────────────────────────────────
    bull_cnt = sum(1 for e in events if e.get("impact") == "bullish")
    bear_cnt = sum(1 for e in events if e.get("impact") == "bearish")
    co1, co2, co3, co4 = st.columns(4)
    co1.metric("📋 總事件", len(events))
    co2.metric("🟢 利多", bull_cnt)
    co3.metric("🔴 利空", bear_cnt)
    co4.metric("⚪ 中性", len(events) - bull_cnt - bear_cnt)

    # ── 月曆 HTML ─────────────────────────────────────────────
    try:
        cal_html = build_calendar_html(events, st.session_state.cal_year, st.session_state.cal_month)
        components.html(cal_html, height=1250, scrolling=True)
    except Exception as err:
        st.error(f"月曆渲染失敗：{err}")
        # 降級顯示：純文字清單
        st.markdown("### 📋 本月事件清單")
        pfx = f"{st.session_state.cal_year}-{st.session_state.cal_month:02d}"
        ev_this_month = [e for e in events if e.get("date","").startswith(pfx)]
        for e in sorted(ev_this_month, key=lambda x: x.get("date","")):
            icon = "🟢" if e.get("impact") == "bullish" else ("🔴" if e.get("impact") == "bearish" else "⚪")
            st.markdown(f"**{e.get('date','')[5:]} {icon} {e.get('title','')}** — {e.get('detail','')}")


def tab_rank():
    st.markdown("### 🏆 今日評等排行")
    results=st.session_state.results
    if not results: st.info("請先在「🔍 個股分析」執行分析"); return
    df=pd.DataFrame([{"評等":r["rating"],"股票":f"{r['name']}({r['sid']})","分數":r["score"],
                      "現價":r["price"],"漲跌%":f"{r['chg']:+.2f}%",
                      "外資":f"{r['fc']:+d}日","投信":f"{r['tc']:+d}日",
                      "目標":f"{r['tp']:,.0f}" if r.get("tp") else "-",
                      "風控":("🚨全額交割" if r.get("is_full_del") else
                              "⚠️下市" if r.get("is_delisting") else
                              "⏱處置" if r.get("is_disposed") else "正常")} for r in results])
    st.dataframe(df,use_container_width=True,hide_index=True)
    buy2=[r for r in results if r["fc"]>0 and r["tc"]>0 and not r.get("is_hard_risk",False)]
    if buy2:
        st.markdown("### ✅ 外資+投信同向買超")
        for r in sorted(buy2,key=lambda x:x["fc"]+x["tc"],reverse=True):
            chg2=r["chg"] or 0
            # 預計算顏色（避免 Python < 3.12 f-string 限制）
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
        token=st.text_input("t",value=st.session_state.token,type="password",
                             placeholder="貼上 FinMind Token...",label_visibility="collapsed")
        st.markdown("**🤖 Gemini API Key**（下市偵測 + 財經行事曆，選填）")
        gkey=st.text_input("g",value=st.session_state.gemini_key,type="password",
                            placeholder="貼上 Google Gemini API Key（AIza...）",label_visibility="collapsed")
        st.markdown("**📋 自選股清單**（逗號分隔）")
        sl=st.text_area("s",value=st.session_state.stock_list,height=80,label_visibility="collapsed")
        ok=st.form_submit_button("💾 儲存設定",use_container_width=True)
    if ok:
        st.session_state.token=token.strip(); st.session_state.gemini_key=gkey.strip()
        st.session_state.stock_list=sl.strip(); st.success("✅ 儲存完成！")
    c1,c2=st.columns(2)
    with c1:
        if st.session_state.token:
            st.success(f"FinMind：{st.session_state.token[:8]}...")
        else:
            st.warning("未設定 FinMind Token")
    with c2:
        if st.session_state.gemini_key:
            st.success(f"Gemini：{st.session_state.gemini_key[:8]}...")
        else:
            st.info("Gemini 未設定（可選）")
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
    if st.button("🗑 清除所有快取",use_container_width=True):
        import shutil
        shutil.rmtree(CACHE_DIR,ignore_errors=True); os.makedirs(CACHE_DIR,exist_ok=True)
        # 只對有 @st.cache_data 的函式呼叫 .clear()
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
            except Exception as e: st.error(f"錯誤：{e}"); st.exception(e)
        with t2:
            try: tab_analysis()
            except Exception as e: st.error(f"錯誤：{e}"); st.exception(e)
        with t3:
            try: tab_calendar()
            except Exception as e: st.error(f"錯誤：{e}"); st.exception(e)
        with t4:
            try: tab_rank()
            except Exception as e: st.error(f"錯誤：{e}"); st.exception(e)
        with t5:
            try: tab_settings()
            except Exception as e: st.error(f"錯誤：{e}"); st.exception(e)
    except Exception as e:
        st.error(f"App 啟動錯誤：{type(e).__name__}: {e}")
        st.exception(e)

if __name__=="__main__": main()
