"""
台股分析系統 v6.2 — 最終完美修復版
修復項目：
  ① 拔除第 225 行引發當機的 circular import (from streamlit_app import...)
  ② 完整相容個股搜尋、Gemini 智慧財經行事曆、下市地雷股硬風控
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
# 擴充股票資料庫（支援中文搜尋）
# ─────────────────────────────────────────────────────────────
ALL_STOCKS = {
    # ── 上市 TWSE ────────────────────────────────────────────
    "2330":"台積電","2317":"鴻海","2454":"聯發科","2308":"台達電","2382":"廣達",
    "2303":"聯電","2327":"國巨","2357":"華碩","2379":"瑞昱","2376":"技嘉",
    "2313":"華通","2368":"金像電","2603":"長榮","2609":"陽明","2615":"萬海",
    "3711":"日月光投控","2412":"中華電","2886":"兆豐金","2881":"富邦金","2882":"國泰金",
    "2884":"玉山金","2891":"中信金","1301":"台塑","1303":"南亞","2002":"中鋼",
    "2408":"南亞科","2474":"可成","2385":"群光","3661":"世芯-KY","6669":"緯穎",
    "2353":"宏碁","2356":"英業達","3034":"聯詠","3037":"欣興","3231":"緯創",
    "1513":"中興電","2059":"川湖","2301":"光寶科","2337":"旺宏","2344":"華邦電",
    "2352":"佳世達","2371":"大同","2395":"研華","2401":"凌陽","2404":"漢唐",
    "2409":"友達","2414":"精技","2420":"新日興","2423":"固緯","2426":"鼎元",
    "2436":"偉詮電","2441":"超豐","2449":"京元電子","2451":"創見","2455":"全新",
    "2458":"義隆","2468":"華文網","2477":"美隆工","2481":"強茂","2485":"兆赫",
    "2489":"瑞軒","2492":"華新科","2498":"宏達電","2501":"國建","2504":"國產",
    "2511":"太子","2515":"中工","2520":"冠德","2527":"宏璟","2530":"華建",
    "2534":"宏盛","2535":"達欣工","2538":"基泰","2548":"華固","2603":"長榮",
    "2606":"裕民","2607":"榮運","2608":"嘉里大榮","2609":"陽明","2610":"華航",
    "2611":"志信","2615":"萬海","2618":"長榮航","2633":"台灣高鐵","2634":"漢翔",
    "2801":"彰銀","2809":"京城銀","2812":"台中銀","2823":"中壽","2832":"台產",
    "2834":"臺企銀","2836":"高雄銀","2838":"聯邦銀","2845":"遠東銀","2847":"大眾銀",
    "2850":"新產","2851":"中再保","2852":"第一保","2855":"統一證","2856":"元富證",
    "2880":"華南金","2881":"富邦金","2882":"國泰金","2883":"開發金","2884":"玉山金",
    "2885":"元大金","2886":"兆豐金","2887":"台新金","2888":"新光金","2889":"國票金",
    "2890":"永豐金","2891":"中信金","2892":"第一金","2897":"王道銀","2912":"統一超",
    "2915":"潤泰全","3008":"大立光","3009":"奇美實業","3010":"華立","3014":"聯陽",
    "3017":"奇鋐","3019":"亞光","3022":"威強電","3024":"憶聲","3025":"星通",
    "3026":"禾伸堂","3027":"盛達","3028":"增你強","3029":"零壹","3030":"德律",
    "3031":"佰鴻","3032":"偉訓","3034":"聯詠","3035":"智原","3036":"文曄",
    "3037":"欣興","3038":"全台晶像","3042":"晶技","3044":"健鼎","3047":"訊舟",
    "3048":"益登","3049":"和鑫","3050":"鈺德","3051":"力特","3052":"夆典",
    "3055":"蒙恬","3057":"喬鼎","3058":"立德","3060":"訊達","3062":"建漢",
    "3065":"大眾電腦","3068":"大倫","3078":"僑威","3079":"直得","3081":"聯惠",
    "3085":"比菲德","3086":"華義","3087":"百豐富","3088":"艾訊","3089":"億聯",
    "3090":"日月光半導體","3105":"穩懋","3231":"緯創","3293":"象","3305":"昇貿",
    "3406":"玉晶光","3443":"創意","3481":"群創","3491":"昇達科","3494":"誠研",
    "3504":"揚明光","3515":"華擎","3516":"三達電","3529":"力旺","3533":"嘉澤",
    "3545":"敦泰","3546":"宇峻奧汀","3549":"加高","3550":"樂士","3553":"廣穎",
    "3556":"禾瑞亞","3557":"嘉威","3558":"神準","3559":"全智科","3577":"中宇",
    "3583":"辛耘","3587":"閎康","3588":"通嘉","3592":"瑞鼎","3596":"智易",
    "3611":"鼎翰","3615":"安勤","3622":"洋基工程","3645":"達亮","3665":"貿聯-KY",
    "3673":"TPK","3688":"勝藍","3689":"全訊科技","3698":"隆達","3702":"大聯大",
    "3706":"神達","3711":"日月光投控","4938":"和碩","4939":"亞電","4966":"譜瑞-KY",
    "5347":"世界先進","5483":"中美晶","5604":"中連貨","5606":"台船","5608":"四維航",
    "5880":"合庫金","6008":"華立","6108":"競國","6116":"彩晶","6153":"嘉聯益",
    "6176":"瑞儀","6198":"凌群","6239":"力成","6271":"同欣電","6285":"啟碁",
    "6289":"華越","6290":"良維","6302":"詮欣","6303":"賜福","6306":"崑鼎",
    "6347":"聯策","6360":"先豐","6415":"矽力-KY","6488":"環球晶","6491":"沛爾",
    "6510":"精測","6515":"穎威","6526":"達發","6533":"晶心科","6541":"泰福-KY",
    "6546":"巨有科技","6582":"申豐","6598":"ABC-KY","6669":"緯穎","6683":"雍智科技",
    "6770":"力積電","8016":"旺貘","8046":"南電","8147":"正凌","8150":"南茂",
    "8163":"達方","8201":"大容","8210":"勁億","8213":"志超","8215":"明基材",
    "8222":"寶一","8261":"富鼎","8271":"宇瞻","8274":"華錄","8341":"日友",
    "8342":"益壽科技",
    # ── 上櫃 TPEx ─────────────────────────────────────────────
    "5274":"信驊","3017":"奇鋐","3048":"益登","3529":"力旺","3665":"貿聯-KY",
    "3167":"達亮","6510":"精測","3443":"創意","3035":"智原","4966":"譜瑞-KY",
    "6239":"力成","6488":"環球晶","6533":"晶心科","3293":"鈊象","3081":"聯惠",
    "8299":"群聯","5347":"世界先進","3533":"嘉澤","4958":"臻鼎-KY","5269":"祥碩",
    "6271":"同欣電","4919":"新唐","6526":"達發","4743":"合一","4968":"立積",
    "6230":"超豐","3550":"樂士","6285":"啟碁","5234":"達興材料","5245":"智晶",
    "5258":"全訊科","5269":"祥碩","5285":"界霖","5351":"鈺創","5371":"中光電",
    "5374":"精航","5381":"合正","5398":"力銘","5410":"國眾","5438":"東友",
    "5439":"中傳","5444":"全友","5457":"宣德","5464":"霖宏","5471":"松翰",
    "5478":"瑞祺電通","5481":"世基","5483":"中美晶","5490":"同亨","5498":"凱崴",
}

def nm(s): return ALL_STOCKS.get(s, s)

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"
GEMINI_MODEL = "gemini-2.0-flash"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
CACHE_DIR = "/tmp/tw_stock_v6"
os.makedirs(CACHE_DIR, exist_ok=True)

RC  = {"S":"#1a5c38","A":"#27ae60","B":"#854F0B","C":"#A32D2D"}
RL  = {"S":"#D0F0DC","A":"#D0F0DC","B":"#FAE0A8","C":"#F7C1C1"}
RS  = {"S":"#A8E6BB","A":"#A8E6BB","B":"#F5C842","C":"#F09595"}
VBG = {"S":"#1a3a27","A":"#1a3a27","B":"#3a2c0a","C":"#3a1a1a"}
VBC = {"S":"#27ae60","A":"#27ae60","B":"#f39c12","C":"#e74c3c"}
VTC = {"S":"#a8e6bb","A":"#a8e6bb","B":"#fae0a8","C":"#f7c1c1"}
NAMES = ALL_STOCKS  # alias

for k,v in [("token",""),("gemini_key",""),
            ("stock_list","2330,2454,6669,3661,3034,3017,3037,6515,5274,2376"),
            ("results",[]),("last_run",None),("disposed",set()),
            ("gemini_delisting",set()),("gemini_delisting_ts",None),
            ("cal_year",date.today().year),("cal_month",date.today().month),
            ("cal_events",[]),("cal_events_ts",None)]:
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
def last_trading_days(n=5):
    days=[]; d=date.today()
    while len(days)<n:
        if d.weekday()<5: days.append(d)
        d-=timedelta(days=1)
    return days

# ─────────────────────────────────────────────────────────────
# 股票搜尋
# ─────────────────────────────────────────────────────────────
def search_stocks(query):
    """依代號或中文名稱搜尋股票，回傳最多20筆"""
    q=query.strip()
    if not q: return []
    res=[]
    for code,name in ALL_STOCKS.items():
        if q in code or q in name:
            res.append((code,name))
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
        response=client.models.generate_content(model=GEMINI_MODEL,
            contents="列出目前台灣股市全額交割股和下市警告股的4位數股號，每行一個，只列代號不要名稱：")
        codes=set(re.findall(r'\b\d{4}\b',response.text))
        valid={c for c in codes if 1000<=int(c)<=9999}
        st.session_state.gemini_delisting=valid
        st.session_state.gemini_delisting_ts=datetime.now()
        return valid
    except Exception: return set()

# ─────────────────────────────────────────────────────────────
# ★ Gemini：財經事件行事曆
# ─────────────────────────────────────────────────────────────
def gemini_fetch_events(api_key, year, month):
    """
    用 Gemini 搜尋指定月份的重大財經事件。
    回傳 list of dict，每筆含 date/title/detail/category/impact/impact_zh/reason
    """
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

        prompt=f"""你是專業的財經事件分析師。請提供{year}年{month}月（以及{next_y}年{next_m}月上旬）的重大財經事件。

涵蓋以下類別：
1. 美國總體經濟：CPI、PPI、PCE、非農就業、GDP、Fed FOMC會議、零售銷售
2. 台灣財經：台灣央行理監事會議、重要企業財報（台積電/鴻海/聯發科等）、台灣GDP/CPI
3. 全球重大事件：G7/G20峰會、中美貿易談判、川習會、歐央行會議、BOJ會議
4. 美股科技財報：NVIDIA/Apple/Microsoft/Google/Meta/Amazon財報
5. 其他影響台股的大事

請以JSON陣列格式回傳（不要markdown，只要JSON）：
[
  {{
    "date": "{year}-{month:02d}-01",
    "title": "事件簡稱（15字內）",
    "detail": "詳細說明（60字內）",
    "category": "美國總經/台灣財經/全球事件/企業財報",
    "impact": "bullish/bearish/neutral",
    "impact_zh": "利多/利空/中性",
    "reason": "對台股影響說明（35字內）"
  }}
]

請列出20~40個事件，只回傳JSON陣列，不要有任何其他文字。"""

        response=client.models.generate_content(model=GEMINI_MODEL,contents=prompt)
        text=response.text.strip()
        text=re.sub(r'```json\s*','',text); text=re.sub(r'```\s*','',text)
        events=json.loads(text) if text.startswith('[') else json.loads(re.search(r'\[.*\]',text,re.DOTALL).group(0))

        validated=[]
        for ev in events:
            if not ev.get("date") or not ev.get("title"): continue
            ev["_month"]=cache_key
            ev.setdefault("impact","neutral")
            ev.setdefault("impact_zh","中性")
            ev.setdefault("category","其他")
            ev.setdefault("reason","")
            validated.append(ev)

        validated.sort(key=lambda x:x["date"])
        st.session_state.cal_events=validated
        st.session_state.cal_events_ts=datetime.now()
        return validated

    except Exception:
        return _default_events(year, month)

def _default_events(year, month):
    events=[
        {"date":f"{year}-{month:02d}-05","title":"美國非農就業","detail":"美國勞工部公布非農就業人口數據","category":"美國總經","impact":"neutral","impact_zh":"中性","reason":"若高於預期可能引發升息預期，利空科技股"},
        {"date":f"{year}-{month:02d}-10","title":"美國CPI通膨","detail":"美國消費者物價指數公布","category":"美國總經","impact":"bearish","impact_zh":"利空","reason":"通膨超預期將強化Fed維持高息立場，壓抑成長股"},
        {"date":f"{year}-{month:02d}-15","title":"台積電法說會","detail":"台積電季度財報及展望說明會","category":"企業財報","impact":"bullish","impact_zh":"利多","reason":"台積電財報是台股最重要風向球，展望佳帶動半導體族群"},
        {"date":f"{year}-{month:02d}-20","title":"Fed FOMC會議","detail":"聯準會利率決策會議，公布利率決策","category":"美國總經","impact":"neutral","impact_zh":"中性","reason":"市場最關注Fed利率走向，超預期鷹派為利空"},
        {"date":f"{year}-{month:02d}-25","title":"台灣央行理監事會","detail":"台灣央行利率決策會議","category":"台灣財經","impact":"neutral","impact_zh":"中性","reason":"央行政策影響台幣走勢與資金流向"},
    ]
    for e in events: e["_month"]=f"{year}-{month:02d}"
    return events

# ─────────────────────────────────────────────────────────────
# ★ 財經事件行事曆 HTML 生成器
# ─────────────────────────────────────────────────────────────
def build_calendar_html(events, year, month):
    from collections import defaultdict as _dd
    day_events = _dd(list)
    for ev in events:
        try:
            d = datetime.strptime(ev["date"], "%Y-%m-%d")
            if d.year == year and d.month == month:
                day_events[d.day].append(ev)
        except Exception:
            pass

    today = date.today()
    week_end = today + timedelta(days=7)
    week_events = []
    for ev in events:
        try:
            dw = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            if today <= dw <= week_end:
                week_events.append((dw, ev))
        except Exception:
            pass
    week_events.sort(key=lambda x: x[0])

    IC = {"bullish":"#27ae60","bearish":"#e74c3c","neutral":"#8fa3b8"}
    IB = {"bullish":"#1a3a27","bearish":"#3a1a1a","neutral":"#2c3e50"}
    IZ = {"bullish":"🟢利多","bearish":"🔴利空","neutral":"⚪中性"}
    CC = {"美國總經":"#2980b9","台灣財經":"#27ae60","全球事件":"#8e44ad","企業財報":"#e67e22","其他":"#7f8c8d"}

    first_wd, days_in_month = _cal.monthrange(year, month)

    cells = ""
    for _ in range(first_wd):
        cells += '<div class="cal-cell cal-empty"></div>'
    for day in range(1, days_in_month + 1):
        is_today = (today == date(year, month, day))
        tc = "cal-today" if is_today else ""
        td_html = '<div class="today-dot"></div>' if is_today else ""
        evs = day_events.get(day, [])
        pills = ""
        for ev in evs[:3]:
            imp = ev.get("impact","neutral")
            ic_val = IC.get(imp,"#8fa3b8")
            ibg_val = IB.get(imp,"#2c3e50")
            title_s = ev.get("title","")[:8]
            detail_s = ev.get("detail","")
            pills += (
                '<div class="cal-pill" style="background:' + ibg_val +
                ';border-left:2px solid ' + ic_val + ';color:' + ic_val +
                '" title="' + detail_s + '">' + title_s + '</div>'
            )
        if len(evs) > 3:
            pills += '<div class="cal-more">+' + str(len(evs)-3) + '</div>'
        cells += (
            '<div class="cal-cell ' + tc + '">' + td_html +
            '<div class="cal-day-num">' + str(day) + '</div>' + pills + '</div>'
        )
    total = first_wd + days_in_month
    for _ in range((7 - total % 7) % 7):
        cells += '<div class="cal-cell cal-empty"></div>'

    week_html = ""
    if week_events:
        for dw, ev in week_events:
            imp = ev.get("impact","neutral")
            ic_val = IC.get(imp,"#8fa3b8")
            ibg_val = IB.get(imp,"#2c3e50")
            iz_val = IZ.get(imp,"⚪中性")
            cat_c = CC.get(ev.get("category","其他"),"#7f8c8d")
            wd_zh = ["一","二","三","四","五","六","日"][dw.weekday()]
            today_mark = "📍今天 " if dw == today else ""
            rsn = ev.get("reason","")
            rh = '<div class="week-ev-reason">📊 台股影響：' + rsn + '</div>' if rsn else ""
            week_html += (
                '<div class="week-event" style="border-left:4px solid ' + ic_val +
                ';background:' + ibg_val + '">' +
                '<div class="week-ev-header">' +
                '<span class="week-date">' + today_mark + dw.strftime("%m/%d") + " 週" + wd_zh + '</span>' +
                '<span class="week-impact" style="background:' + ic_val + '22;color:' + ic_val +
                ';border:1px solid ' + ic_val + '55">' + iz_val + '</span>' +
                '<span class="week-cat" style="color:' + cat_c + '">' + ev.get("category","") + '</span></div>' +
                '<div class="week-ev-title">' + ev.get("title","") + '</div>' +
                '<div class="week-ev-detail">' + ev.get("detail","") + '</div>' +
                rh + '</div>'
            )
    else:
        week_html = '<div style="color:#8fa3b8;font-size:13px;padding:12px 0">本週無重大財經事件</div>'

    ev_list_html = ""
    for ev in sorted(events, key=lambda x: x["date"]):
        if not ev.get("date","").startswith(str(year) + "-" + f"{month:02d}"):
            continue
        imp = ev.get("impact","neutral")
        ic_val = IC.get(imp,"#8fa3b8")
        ibg_val = IB.get(imp,"#2c3e50")
        iz_val = IZ.get(imp,"⚪中性")
        ttl = ev.get("title",""); dtl = ev.get("detail",""); rsn = ev.get("reason","")
        rh = '<div style="font-size:10px;color:#7ec8e3;margin-top:2px">📊 ' + rsn + '</div>' if rsn else ""
        ev_list_html += (
            '<div class="ev-list-item">' +
            '<span class="ev-date-badge">' + ev["date"][5:] + '</span>' +
            '<span class="ev-impact-badge" style="background:' + ibg_val +
            ';color:' + ic_val + ';border:1px solid ' + ic_val + '44">' + iz_val + '</span>' +
            '<div><div style="font-size:12px;font-weight:600;color:#e8eaf0">' + ttl + '</div>' +
            '<div style="font-size:11px;color:#8fa3b8;margin-top:2px">' + dtl + '</div>' +
            rh + '</div>'</div>'
        )

    n_ev = len([e for e in events if e.get("date","").startswith(str(year) + "-" + f"{month:02d}")])
    bull = sum(1 for e in events if e.get("impact")=="bullish" and e.get("date","").startswith(str(year) + "-" + f"{month:02d}"))
    bear = sum(1 for e in events if e.get("impact")=="bearish" and e.get("date","").startswith(str(year) + "-" + f"{month:02d}"))
    month_zh = ["一","二","三","四","五","六","七","八","九","十","十一","十二"][month-1]

    cal_css = """
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

    return (
        "<!DOCTYPE html><html lang=\"zh-TW\"><head>"
        "<meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<style>" + cal_css + "</style></head><body><div class=\"cal-wrap\">"
        "<div class=\"cal-header\">"
        "<div><div class=\"cal-title\">📅 " + str(year) + "年" + month_zh + "月 財經行事曆</div>"
        "<div class=\"cal-subtitle\">重大事件 · 利多利空標示 · 本週提醒</div></div>"
        "<div><div class=\"cal-legend\">"
        "<span class=\"leg-item\"><span class=\"leg-dot\" style=\"background:#27ae60\"></span>利多</span>"
        "<span class=\"leg-item\"><span class=\"leg-dot\" style=\"background:#e74c3c\"></span>利空</span>"
        "<span class=\"leg-item\"><span class=\"leg-dot\" style=\"background:#8fa3b8\"></span>中性</span>"
        "</div><div style=\"font-size:10px;color:#8fa3b8;margin-top:5px\">共" + str(n_ev) + "個事件 | 利多" + str(bull) + " 利空" + str(bear) + "</div></div></div>"
        "<div class=\"weekday-row\">"
        "<div class=\"wd\">週一</div><div class=\"wd\">週二</div><div class=\"wd\">週三</div>"
        "<div class=\"wd\">週四</div><div class=\"wd\">週五</div>"
        "<div class=\"wd\" style=\"color:#e74c3c55\">週六</div>"
        "<div class=\"wd\" style=\"color:#e74c3c55\">週日</div></div>"
        "<div class=\"cal-grid\">" + cells + "</div>"
        "<div class=\"week-section\"><div class=\"week-title\">🔔 本週（7日內）重大事件提醒</div>"
        + week_html + "</div>"
        "<div class=\"events-section\">"
        "<div style=\"font-size:13px;font-weight:700;color:#fff;margin-bottom:9px\">📋 本月全部事件清單</div>"
        + ev_list_html + "</div>"
        "</div></body></html>"
    )


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
    out=set()
    try:
        r=requests.get("https://openapi.twse.com.tw/v1/announcement/changeTrading",headers=HDR,timeout=10,verify=False)
        if r.status_code==200:
            for item in r.json():
                c=str(item.get("SecuritiesCode","")).strip()
                if c: out.add(c)
    except Exception: pass
    return out

# ─────────────────────────────────────────────────────────────
# 全市場數據（修正版：自動找最近交易日）
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
def fetch_twse_institution_all():
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
def fetch_tpex_institution_all():
    out={}
    for trade_date in last_trading_days(5):
        date_str=trade_date.strftime("%Y/%m/%d")
        try:
            r=requests.get(f"https://www.tpex.org.tw/web/fund/tripleFund/index.php?l=zh-tw&o=json&d={date_str}",headers=HDR,timeout=20,verify=False)
            if r.status_code!=200: continue
            rows=r.json().get("aaData",r.json().get("data",[]))
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
# 量化評分（原始機制，不含AI）
# ─────────────────────────────────────────────────────────────
def calc_quant_score(p,d5,d200,fc,tc,pe,pea,rev_yoy,tp):
    sc=50; pos=[]; neg=[]; warn=[]
    if d5 is not None:
        if   d5<-5:  sc+=18;pos.append(f"5日線回測{d5:+.1f}%（良好進場）")
        elif d5<=2:  sc+=10;pos.append(f"5日乖離健康{d5:+.1f}%")
        elif d5<=8:  sc+=2; warn.append(f"5日乖離偏高{d5:+.1f}%")
        else:        sc-=10;neg.append(f"5日乖離過高{d5:+.1f}%，追高風險")
    if d200 and d200>50: sc-=8;warn.append(f"年線乖離偏高{d200:+.1f}%")
    if tp and p:
        up=(tp-p)/p*100
        if   up>20:  sc+=15;pos.append(f"距目標+{up:.1f}%空間")
        elif up>10:  sc+=8; pos.append(f"距目標+{up:.1f}%")
        elif up>0:   sc+=3
        elif up>-10: sc-=5; warn.append(f"現價略超目標{up:.1f}%")
        else:        sc-=12;neg.append(f"現價大幅超越目標{up:.1f}%")
    if rev_yoy is not None:
        if   rev_yoy>=20:sc+=8; pos.append(f"月營收YoY+{rev_yoy:.1f}%（高成長）")
        elif rev_yoy>=5: sc+=4; pos.append(f"月營收YoY+{rev_yoy:.1f}%")
        elif rev_yoy<0:  sc-=5; neg.append(f"月營收年減{rev_yoy:.1f}%")
    if   fc>=3:  sc+=12;pos.append(f"外資連買{fc}日")
    elif fc>=1:  sc+=5; pos.append("外資今日買超")
    elif fc<=-3: sc-=10;neg.append(f"外資連賣{abs(fc)}日")
    elif fc<0:   sc-=4; warn.append("外資今日賣超")
    if   tc>=5:  sc+=12;pos.append(f"投信連買{tc}日（深度認養）")
    elif tc>=3:  sc+=8; pos.append(f"投信連買{tc}日")
    elif tc>=1:  sc+=3; pos.append("投信今日買超")
    elif tc<=-3: sc-=10;neg.append(f"投信連賣{abs(tc)}日")
    elif tc<0:   sc-=4; warn.append("投信今日賣超")
    if fc>0 and tc>0:   sc+=5; pos.append("外資投信同向買超，無對作")
    elif fc<0 and tc<0: sc-=8; neg.append("外資投信同向賣超，籌碼惡化")
    if pe and pea and pea>0:
        pv=(pe-pea)/pea*100
        if   pv<-20:sc+=8; pos.append(f"PE{pe:.1f}x低估")
        elif pv<0:  sc+=4
        elif pv>20: sc-=5; warn.append(f"PE{pe:.1f}x偏高")
    sc=max(0,min(100,sc))
    if   sc>=80: rt,lb="S","強烈推薦"
    elif sc>=65: rt,lb="A","建議買入"
    elif sc>=45: rt,lb="B","觀　望"
    else:        rt,lb="C","避　開"
    return sc,rt,lb,pos,neg,warn

# ─────────────────────────────────────────────────────────────
# 主分析
# ─────────────────────────────────────────────────────────────
def analyze(sid,token,disposed,full_delivery,delisting,gemini_del,force=False):
    if not force:
        cached=load_cache(sid)
        if cached: return cached,None
    is_full_del=sid in full_delivery
    is_delisting=sid in delisting or sid in gemini_del
    is_disposed=sid in disposed
    is_hard_risk=is_full_del or is_delisting
    try:
        pr=get_price(sid,token)
        if not pr: return None,"無股價數據"
        cls=[r["close"] for r in pr]
        last=pr[-1]; prev=pr[-2] if len(pr)>=2 else last
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
        sc,rt,lb,pos,neg,warn=calc_quant_score(p,d5,d200,fc,tc,pe,pea,rev_yoy,tp)
        if is_hard_risk:
            rt="C"; lb="避　開"
            if is_full_del: neg.insert(0,"🚨 全額交割股：流動性極差，強制C評等")
            if is_delisting: neg.insert(0,"⚠️ 下市警告：面臨下市風險，強制C評等")
        if is_disposed and not is_hard_risk:
            sc=max(0,sc-10)
            if sc<45 and rt in ("S","A"): rt="B"; lb="觀　望"
            warn.insert(0,"⏱ 處置股：每5~20分鐘撮合，流動性受限")
        r52=pr[-252:] if len(pr)>=252 else pr
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
                "is_delisting":is_delisting,"is_hard_risk":is_hard_risk,"date":last["date"]}
        save_cache(sid,result); return result,None
    except Exception as e: return None,str(e)

# ─────────────────────────────────────────────────────────────
# 全市場掃描
# ─────────────────────────────────────────────────────────────
def run_scanner():
    twse_p=fetch_twse_prices_all(); twse_i=fetch_twse_institution_all()
    tpex_p=fetch_tpex_prices_all(); tpex_i=fetch_tpex_institution_all()
    disposed=fetch_disposed_cached(); full_del=fetch_full_delivery_cached()
    delisting=fetch_delisting_cached(); gemini_del=st.session_state.gemini_delisting
    hard_risk=full_del|delisting|gemini_del
    prices={**twse_p,**tpex_p}; insts={**twse_i,**tpex_i}
    hot=[]; launch=[]
    for sid,inst in insts.items():
        if sid in hard_risk: continue
        f=inst.get("f",0); t=inst.get("t",0)
        pdata=prices.get(sid)
        if not pdata: continue
        vol=pdata.get("volume",0) or 1; price=pdata.get("price",0)
        iname=pdata.get("name","") or inst.get("name",nm(sid))
        chg=pdata.get("chg_pct",0) or 0
        d_tag="⏱" if sid in disposed else ""
        if f>0 and t>0:
            ab=(f+t)/vol*100
            if ab>=5:
                tier="🔴極熱" if ab>=15 else "🟠熱門" if ab>=8 else "🟡資金升溫"
                hot.append({"sid":sid,"name":iname,"f":f,"t":t,"vol":vol,"ab":round(ab,1),"tier":tier,"price":price,"chg":chg,"tag":d_tag})
        if t>=500 and f>=-50:
            val_yi=round(t*1000*price/1e8,2) if price else 0
            if val_yi>=0.3:
                launch.append({"sid":sid,"name":iname,"t":t,"f":f,"val_yi":val_yi,"price":price,"chg":chg,"tag":d_tag})
    trust=[]
    for r in st.session_state.results:
        if r.get("is_hard_risk"): continue
        bd=sum(1 for d in r.get("inst",[]) if d["t"]>0)
        if bd>=4: trust.append({"sid":r["sid"],"name":r["name"],"buy_days":bd,"t_total":sum(d["t"] for d in r.get("inst",[])),  "price":r["price"],"chg":r.get("chg",0)})
    hot.sort(key=lambda x:x["ab"],reverse=True)
    launch.sort(key=lambda x:(x["t"],x["val_yi"]),reverse=True)
    trust.sort(key=lambda x:x["buy_days"],reverse=True)
    return hot[:20],trust[:15],launch[:10],date.today().strftime("%Y/%m/%d"),len(prices),len(insts)

# ─────────────────────────────────────────────────────────────
# wiwynn HTML（內建完整的卡片渲染）
# ─────────────────────────────────────────────────────────────
WCSS="""
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a2332;font-family:'Helvetica Neue',Arial,sans-serif;padding:10px 6px;color:#e8eaf0}
.wrap{max-width:660px;margin:0 auto}
.hdr{background:#0f1724;border-radius:14px 14px 0 0;padding:16px 18px}
.hdr h1{font-size:18px;color:#fff;font-weight:600}
.hdr-sub{font-size:11px;color:#8fa3b8;margin-top:3px}
.rc{width:60px;height:60px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0}
.rc .lt{font-size:20px;font-weight:600;line-height:1}
.rc .lb{font-size:8px;margin-top:2px}
.tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
.tag{font-size:10px;padding:2px 7px;border-radius:99px;font-weight:500}
.tag-g{background:#27ae6044;color:#4ecca3;border:1px solid #27ae6066}
.tag-r{background:#e74c3c44;color:#ff8080;border:1px solid #e74c3c66}
.tag-a{background:#f39c1244;color:#ffc107;border:1px solid #f39c1266}
.tag-p{background:#8e44ad44;color:#c39bd3;border:1px solid #8e44ad66}
.sbar{background:#2c3e50;border-left:4px solid #27ae60;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:2px;display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:8px}
.sc p:first-child{font-size:10px;color:#8fa3b8;text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px}
.sc p:last-child{font-size:16px;font-weight:700}
.up{color:#4ecca3}.dn{color:#ff6b6b}.wn{color:#ffc107}
.card{background:#2c3e50;border-radius:10px;padding:13px 15px;margin-bottom:8px;border:1px solid #3d5166}
.ct{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:#8fa3b8;margin-bottom:8px}
.row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #3d5166;font-size:13px;gap:8px}
.row:last-child{border-bottom:none}
.rl{color:#8fa3b8;flex-shrink:0}.rv{font-weight:500;text-align:right;color:#e8eaf0}
.rbar{height:9px;border-radius:5px;background:linear-gradient(90deg,#27ae60 0%,#f39c12 55%,#e74c3c 82%);position:relative;margin:9px 0 2px}
.rn{position:absolute;top:-3px;width:3px;height:15px;background:#fff;border-radius:2px}
.rsc{display:flex;justify-content:space-between;font-size:10px;color:#8fa3b8}
.rfg{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:7px}
.rf{background:#1a2332;border-radius:6px;padding:6px 8px;border:1px solid #3d5166}
.rf p:first-child{font-size:10px;color:#8fa3b8;margin-bottom:1px}
.rf p:last-child{font-size:12px;font-weight:500;color:#e8eaf0}
.cg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:8px 0}
.chip{border-radius:7px;padding:8px;text-align:center;border:1px solid}
.chip.buy{background:#1a3a27;border-color:#27ae60}
.chip.sell{background:#3a1a1a;border-color:#e74c3c}
.chip.neut{background:#2c3e50;border-color:#3d5166}
.chip p:first-child{font-size:10px;color:#8fa3b8;margin-bottom:1px}
.chip p:nth-child(2){font-size:14px;font-weight:600;margin-bottom:1px}
.chip p:last-child{font-size:10px;color:#8fa3b8}
.ev{display:flex;gap:8px;padding:7px 0;border-bottom:1px solid #3d5166;font-size:12px}
.ev:last-child{border-bottom:none}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:3px}
.ev strong{display:block;font-size:12px;margin-bottom:1px;color:#e8eaf0}
.ev span{color:#8fa3b8;line-height:1.5}
.sg{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}
.sb{background:#1a3a27;border-radius:7px;padding:8px 10px;font-size:11px;color:#4ecca3;border:1px solid #27ae60;line-height:1.6}
.sr{background:#3a1a1a;border-radius:7px;padding:8px 10px;font-size:11px;color:#ff8080;border:1px solid #e74c3c;line-height:1.6}
.st{display:flex;gap:8px;padding:6px 0;border-bottom:1px solid #3d5166;font-size:12px;align-items:flex-start;line-height:1.6;color:#e8eaf0}
.st:last-child{border-bottom:none}
.si{font-size:14px;flex-shrink:0}
.bw{background:#3a2c0a;border-left:4px solid #ffc107;border-radius:0 6px 6px 0;padding:8px 11px;font-size:12px;color:#ffc107;margin-top:8px;line-height:1.6}
.bd{background:#3a1a1a;border-left:4px solid #e74c3c;border-radius:0 6px 6px 0;padding:8px 11px;font-size:12px;color:#ff8080;margin-top:7px;line-height:1.6}
.bo{background:#1a3a27;border-left:4px solid #27ae60;border-radius:0 6px 6px 0;padding:8px 11px;font-size:12px;color:#4ecca3;margin-top:7px;line-height:1.6}
.hard-risk-banner{background:#3a0a0a;border:1px solid #e74c3c;border-radius:9px;padding:12px 15px;margin-bottom:9px}
.hard-risk-banner strong{display:block;font-size:14px;color:#ff8080;margin-bottom:4px}
.hard-risk-banner span{font-size:12px;color:#ffaaaa;line-height:1.6}
.verdict{border-radius:9px;padding:11px 14px;border:1px solid}
.vb{font-size:23px;font-weight:700}
.tp-wrap{background:#1a2332;border-radius:5px;height:10px;position:relative;margin:6px 0 3px;overflow:hidden}
.tp-fill{height:10px;border-radius:5px}
.tp-lbl{display:flex;justify-content:space-between;font-size:10px;color:#8fa3b8}
.inst-tbl{width:100%;border-collapse:collapse;font-size:11px;margin-top:7px}
.inst-tbl th{background:#1a2332;color:#8fa3b8;padding:4px 6px;font-weight:600;border-bottom:1px solid #3d5166;text-align:right}
.inst-tbl th:first-child{text-align:left}
.inst-tbl td{padding:4px 6px;border-bottom:1px solid #3d5166;text-align:right;color:#e8eaf0}
.inst-tbl td:first-child{text-align:left;color:#8fa3b8}
.footer{background:#0f1724;border-radius:0 0 11px 11px;padding:10px 14px;font-size:10px;color:#8fa3b8;line-height:1.6;border-top:1px solid #3d5166}
"""

def chip_html(label,net,con_d):
    cls="buy" if net>0 else ("sell" if net<0 else "neut")
    vc="up" if net>0 else ("dn" if net<0 else "")
    sign="+" if net>=0 else ""
    ct=(f"連買{con_d}日" if con_d>=2 else "今日買超" if con_d==1 else "今日中性" if con_d==0 else "今日賣超" if con_d==-1 else f"連賣{abs(con_d)}日")
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
    if tc>=5:   tags+=f'<span class="tag tag-g">投信連買{tc}日⭐</span>'
    elif tc>=1: tags+=f'<span class="tag tag-g">投信買超</span>'
    elif tc<=-3:tags+=f'<span class="tag tag-r">投信連賣{abs(tc)}日</span>'
    if fc>=3:   tags+=f'<span class="tag tag-g">外資連買{fc}日</span>'
    elif fc<=-3:tags+=f'<span class="tag tag-r">外資連賣{abs(fc)}日</span>'
    elif fc<0:  tags+='<span class="tag tag-a">外資賣超</span>'
    if tp and p:
        up2=(tp-p)/p*100
        if up2>10: tags+=f'<span class="tag tag-p">目標+{up2:.0f}%</span>'
    hard_banner=""
    if r.get("is_delisting"): hard_banner='<div class="hard-risk-banner"><strong>⚠️ 下市警告：強制 C 評等</strong><span>面臨下市風險，禁止操作，靜待後續公告。</span></div>'
    elif r.get("is_full_del"):hard_banner='<div class="hard-risk-banner"><strong>🚨 全額交割股：強制 C 評等</strong><span>流動性幾乎為零，嚴禁操作。</span></div>'
    ft=inst[-1]["f"] if inst else 0; tt=inst[-1]["t"] if inst else 0; dt=inst[-1]["d"] if inst else 0
    inst_rows=""
    for d2 in inst:
        ds=d2["date"][-5:].replace("-","/"); fv2=d2["f"]; tv=d2["t"]; dv=d2["d"]; to2=fv2+tv+dv
        inst_rows+=f"<tr><td>{ds}</td><td class='{ccc(fv2)}'>{fv2:+,}</td><td class='{ccc(tv)}'>{tv:+,}</td><td class='{ccc(dv)}'>{dv:+,}</td><td class='{ccc(to2)}'><strong>{to2:+,}</strong></td></tr>"
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
        cb=f'<span style="background:#1a2744;color:#7ec8e3;border:1px solid #2980b9;font-size:10px;padding:1px 7px;border-radius:99px;margin-left:5px">👥{tp_n}位</span>' if tp_n>0 else ""
        rng_bar=""
        if tp_h and tp_l and tp_h>tp_l:
            rng=tp_h-tp_l; cp3=min(max((p-tp_l)/rng*100,0),100); mp3=min(max((tp-tp_l)/rng*100,0),100)
            rng_bar=f'<div style="margin-top:9px"><p style="font-size:10px;font-weight:600;color:#8fa3b8;margin-bottom:5px">分析師目標區間</p><div style="position:relative;background:#1a2332;border-radius:5px;height:11px;margin-bottom:3px"><div style="position:absolute;left:{mp3:.0f}%;top:-3px;width:3px;height:17px;background:#5dade2;border-radius:2px;z-index:2"></div><div style="position:absolute;left:{cp3:.0f}%;top:-3px;width:3px;height:17px;background:#fff;border-radius:2px;z-index:3"></div></div><div style="display:flex;justify-content:space-between;font-size:10px;color:#8fa3b8"><span>低 {tp_l:,.0f}</span><span style="color:#5dade2;font-weight:600">均 {tp:,.0f}</span><span>高 {tp_h:,.0f}</span></div></div>'
        exc_cls="dn" if exceed else "up"
        upbox=f'<div class="bd" style="margin-top:7px">✗ 現價超越目標{abs(up2):.1f}%</div>' if exceed else f'<div class="bo" style="margin-top:7px">✅ 距目標+{up2:.1f}%，具合理風險報酬比</div>'
        _tp_hi = (f'<div class="row"><span class="rl">最高目標</span><span class="rv">{tp_h:,.0f}元</span></div>') if tp_h else ""
        _tp_lo = (f'<div class="row"><span class="rl">最低目標</span><span class="rv">{tp_l:,.0f}元</span></div>') if tp_l else ""
        tp_card=(
            f'<div class="card"><p class="ct">💰 目標價分析{cb}</p>'
            f'<div class="row"><span class="rl">來源</span><span class="rv" style="font-size:11px;color:#8fa3b8">{ts_}</span></div>'
            f'<div class="row"><span class="rl">分析師均值</span>'
            f'<span class="rv {exc_cls}" style="font-size:15px;font-weight:700">{tp:,.0f} 元</span></div>'
            + _tp_hi + _tp_lo +
            f'<div class="row"><span class="rl">vs 現價</span>'
            f'<span class="rv {exc_cls}"><strong>{up2:+.1f}%</strong></span></div>'
            f'{rng_bar}'
            f'<div class="tp-wrap"><div class="tp-fill" style="width:{bw:.1f}%;background:{fill_c}"></div></div>'
            f'<div class="tp-lbl"><span>0</span><span>現價{p:,.0f}</span><span>{tp:,.0f}</span></div>'
            f'{upbox}</div>'
        )
    mc=ccc(rm or 0); yc=ccc(ry or 0)
    m_c=f"<div class='rf'><p>月營收MoM</p><p class='{mc}'>{(rm or 0):+.1f}%</p></div>" if rm is not None else ""
    y_c=f"<div class='rf'><p>月營收YoY</p><p class='{yc}'>{(ry or 0):+.1f}%</p></div>" if ry is not None else ""
    p_c=f"<div class='rf'><p>PE</p><p>{pe:.1f}x</p></div>" if pe else ""
    pa_c=f"<div class='rf'><p>年均PE</p><p>{pea:.1f}x</p></div>" if pea else ""
    pb_c=f"<div class='rf'><p>PBR</p><p>{pbr:.2f}x</p></div>" if pbr else ""
    val_card=f"<div class='card'><p class='ct'>📊 估值指標</p><div class='rfg'>{p_c}{pa_c}{pb_c}{m_c}{y_c}</div></div>" if any([pe,pea,pbr,rm is not None,ry is not None]) else ""
    evs=[]
    if r.get("is_delisting"): evs.append(("#e74c3c","⚠️ 下市警告","TWSE/Gemini偵測：面臨下市風險，禁止操作。"))
    elif r.get("is_full_del"):evs.append(("#e74c3c","🚨 全額交割股","流動性幾乎為零，嚴禁操作。"))
    elif r.get("is_disposed"):evs.append(("#ffc107","⏱ 處置股","每5~20分鐘才撮合，流動性受限。"))
    if fc>=3 and tc>=3: evs.append(("#27ae60",f"外資+投信雙向認養（{fc}/{tc}日）","法人籌碼同向，中線多頭確立。"))
    elif fc>=2: evs.append(("#27ae60",f"外資連買{fc}日","外資持續進場，籌碼支撐明確。"))
    if tc>=5:   evs.append(("#27ae60",f"投信深度認養（連買{tc}日）","機構長期建倉，中線信心強。"))
    if d5<-5:   evs.append(("#27ae60","回測5日線進場點",f"5日乖離{d5:+.1f}%，偏多技術訊號。"))
    elif d5>10: evs.append(("#e74c3c","5日線乖離過高","追高風險，建議等回測。"))
    if ry and ry>20: evs.append(("#27ae60",f"月營收YoY+{ry:.1f}%","業績加速成長，基本面多頭。"))
    if not evs: evs.append(("#8fa3b8","目前無特殊事件","維持當前追蹤策略。"))
    ev_html="".join(f'<div class="ev"><div class="dot" style="background:{c}"></div><div><strong>{t}</strong><span>{d3}</span></div></div>' for c,t,d3 in evs[:4])
    stop=round(min(r.get("last5",[p]))*0.97,2)
    ea=(f"{p:,.0f}元（現位進場）" if d5<-3 else f"{(ma5 or p)*0.97:,.0f}元（回測5日線）" if d5<=3 else f"{(ma5 or p)*0.95:,.0f}元（等待回測）")
    tgt=f"{tp:,.0f}元（{ts_}）" if tp else f"{p*1.10:,.0f}元（+10%估算）"
    risks=""
    if r.get("is_delisting"): risks+='<div class="bd">⚠️ <strong>下市警告：</strong>禁止操作！</div>'
    if r.get("is_full_del"):  risks+='<div class="bd">🚨 <strong>全額交割股：</strong>嚴禁操作！</div>'
    if r.get("is_disposed"):  risks+='<div class="bw">⏱ <strong>處置股：</strong>暫不操作，靜待出關。</div>'
    for n in r["neg"][:3]: risks+=f'<div class="bd">✗ {n}</div>'
    for w in r["warn"][:2]:risks+=f'<div class="bw">⚠ {w}</div>'
    if not risks: risks='<div class="bo">✅ 目前無重大風險警示。</div>'
    today=date.today().strftime("%Y/%m/%d"); chg_sign="+" if chg>=0 else ""
    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{r['name']} {sid}</title><style>{WCSS}</style></head>
<body><div class="wrap">
<div class="hdr"><div style="display:flex;justify-content:space-between;align-items:flex-start">
<div><h1>{r['name']} <span style="font-size:13px;font-weight:400;color:#8fa3b8">{sid}</span></h1>
<p class="hdr-sub">{r.get('date',today)} | 收盤{p:,.2f}元 | 評分{sc}/100</p>
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
<p style="margin-top:7px;font-size:12px;color:{vtc};line-height:1.7">
{"<span style='color:#4ecca3'>正：</span>"+"、".join(r['pos'][:2])+"<br>" if r["pos"] else ""}
{"<span style='color:#ff6b6b'>負：</span>"+"、".join(r['neg'][:2]) if r["neg"] else ""}
</p></div>
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
<div class="card"><p class="ct">📅 事件更新</p>{ev_html}</div>
<div class="card"><p class="ct">🎯 操作策略</p>
<div class="st"><span class="si">🟢</span><div><strong>積極進場：</strong>{ea}</div></div>
<div class="st"><span class="si">🟡</span><div><strong>保守進場：</strong>{fv(ma20,'元',0)}（月線支撐）</div></div>
<div class="st"><span class="si">🔴</span><div><strong>短線停損：</strong>{stop:,.0f}元</div></div>
<div class="st"><span class="si">🎯</span><div><strong>目標：</strong>{tgt}</div></div>
<div class="sg"><div class="sb"><strong>📈 多頭</strong><br>法人持續買超+技術強勢</div>
<div class="sr"><strong>📉 空頭</strong><br>外資連賣+跌破月線</div></div></div>
<div class="card"><p class="ct">⚠️ 風險提示</p>{risks}</div>
<div class="footer">{r['name']}（{sid}）| {r.get('date',today)} | 評分{sc}/100（純量化）| {ts_}<br>數據：FinMind API | 僅供參考，不構成投資建議</div>
</div></body></html>"""

def build_full_html(results):
    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    nav="".join(f'<a href="#s{r["sid"]}" style="display:inline-block;font-size:11px;padding:3px 9px;border-radius:14px;font-weight:600;text-decoration:none;margin:2px;background:{RC[r["rating"]]};color:white">{r["name"]}</a>' for r in sorted(results,key=lambda x:x["score"],reverse=True))
    cards=""
    for r in sorted(results,key=lambda x:(x.get("is_disposed",False),-x["score"])):
        inner=build_wiwynn(r); s=inner.find("<body>")+6; e=inner.find("</body>")
        cards+=f'<div id="s{r["sid"]}" style="scroll-margin-top:55px">{inner[s:e]}</div>'
    today=date.today().strftime("%Y/%m/%d %H:%M")
    return f"""<!DOCTYPE html><html lang=\"zh-TW\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>台股分析 {today}</title><style>{WCSS}</style></head><body>
<div class="wrap"><div style="background:#0f1724;border-radius:10px;padding:9px 13px;margin-bottom:10px;position:sticky;top:0;z-index:99"><div style="font-size:10px;color:#8fa3b8;margin-bottom:4px">📊 台股分析 {today} | S:{cnts['S']} A:{cnts['A']} B:{cnts['B']} C:{cnts['C']}</div>{nav}</div>{cards}</div></body></html>"""

# ─────────────────────────────────────────────────────────────
# 頁面
# ─────────────────────────────────────────────────────────────
def tab_scanner():
    st.markdown("### 📡 籌碼掃描 — 全市場（上市＋上櫃，免Token）")
    c1,c2,c3=st.columns(3)
    c1.info("🆓 免費，無需 Token"); c2.info("⏱ 自動找最近交易日"); c3.info("🤖 Gemini偵測下市股")
    if st.button("🔄 重新整理全市場數據",use_container_width=True):
        for fn in [fetch_twse_prices_all,fetch_twse_institution_all,
                   fetch_tpex_prices_all,fetch_tpex_institution_all,
                   fetch_full_delivery_cached,fetch_delisting_cached]:
            fn.clear()
        st.session_state.gemini_delisting=set(); st.session_state.gemini_delisting_ts=None
        st.rerun()
    gkey=st.session_state.gemini_key
    if gkey:
        with st.spinner("🤖 Gemini 偵測下市風險股票..."): g_del=gemini_fetch_delisting(gkey)
        if g_del: st.warning(f"🤖 Gemini 偵測到 {len(g_del)} 支下市風險股：{', '.join(sorted(g_del)[:10])}")
    with st.spinner("📡 取得全市場數據..."): hot,trust,launch,inst_date,n_p,n_i=run_scanner()
    st.caption(f"資料：{inst_date} | 股價：{n_p} 檔 | 法人：{n_i} 檔")
    if n_i==0:
        st.error("⚠️ 法人數據暫無法取得（可能是假日或 TWSE 尚未更新，請下午3點後重試）")
        return
    st.markdown(f"#### 🔥 策略一：法人焦點熱門股（{len(hot)} 檔）")
    st.caption("外資+投信同向買超，吸籌率≥5%，已排除全額交割/下市警告股")
    if hot:
        df=pd.DataFrame([{"熱度":r["tier"],"代號":r["sid"],"名稱":r["name"][:8],"⚠":r["tag"],"收盤":r["price"],"漲跌%":f"{r['chg']:+.1f}%","外資(張)":f"+{r['f']:,}","投信(張)":f"+{r['t']:,}","吸籌率":f"{r['ab']:.1f}%"} for r in hot])
        st.dataframe(df,use_container_width=True,hide_index=True,height=min(35*len(hot)+40,460))
    else: st.info("今日無符合條件個股")
    st.markdown("---")
    st.markdown(f"#### ⚡ 策略三：主力首日發動（{len(launch)} 檔）")
    if launch:
        df=pd.DataFrame([{"代號":r["sid"],"名稱":r["name"][:8],"⚠":r["tag"],"收盤":r["price"],"漲跌%":f"{r['chg']:+.1f}%","今日投信":f"+{r['t']:,}張","金額":f"{r['val_yi']:.2f}億","外資":f"{r['f']:+,}張"} for r in launch])
        st.dataframe(df,use_container_width=True,hide_index=True)
    else: st.info("今日無投信突破500張的首日發動個股")
    st.markdown("---")
    st.markdown(f"#### 🕵️ 策略二：投信暗中佈局（{len(trust)} 檔）")
    if trust:
        df=pd.DataFrame([{"代號":r["sid"],"名稱":r["name"][:8],"現價":r["price"],"漲跌%":f"{r.get('chg',0):+.1f}%","5日買超天數":f"{r['buy_days']}/5天","累計(張)":f"+{r['t_total']:,}"} for r in trust])
        st.dataframe(df,use_container_width=True,hide_index=True)
    else: st.info("請先在「🔍 個股分析」執行分析，結果將自動出現在此")


def tab_analysis():
    token=st.session_state.token; gkey=st.session_state.gemini_key
    results=st.session_state.results

    st.markdown("### 🔍 個股分析")
    if token:
        lr=st.session_state.last_run
        st.success(f"✅ Token 已設定 | 上次：{lr.strftime('%m/%d %H:%M') if lr else '尚未執行'}")
    else:
        st.error("⚠️ 請到「⚙️ 設定」填入 FinMind Token")

    st.markdown("---")
    st.markdown("#### 🔍 搜尋股票（支援中文名稱 或 股號）")
    col_s1, col_s2 = st.columns([4,1])
    with col_s1:
        query=st.text_input("搜尋",placeholder="輸入股號（如 2330）或中文名稱（如 台積電）",label_visibility="collapsed")
    with col_s2:
        search_btn=st.button("搜尋",use_container_width=True,key="search_btn")

    if query:
        results_search=search_stocks(query)
        if results_search:
            opts_labels=[f"{c} {n}" for c,n in results_search]
            selected_idx=st.selectbox("搜尋結果（選擇後可加入清單或立即分析）",
                                       range(len(opts_labels)),
                                       format_func=lambda i:opts_labels[i],
                                       label_visibility="collapsed")
            sel_code,sel_name=results_search[selected_idx]
            ca,cb,cc=st.columns(3)
            with ca:
                if st.button(f"📊 立即分析 {sel_name}",use_container_width=True,disabled=not token):
                    disposed=fetch_disposed_cached(); full_del=fetch_full_delivery_cached()
                    delisting=fetch_delisting_cached(); gemini_del=st.session_state.gemini_delisting
                    with st.spinner(f"分析 {sel_name}（{sel_code}）..."):
                        r,err=analyze(sel_code,token,disposed,full_del,delisting,gemini_del,force=True)
                    if r:
                        idx2=next((i for i,x in enumerate(st.session_state.results) if x["sid"]==sel_code),None)
                        if idx2 is not None: st.session_state.results[idx2]=r
                        else: st.session_state.results=[r]+st.session_state.results
                        save_results_cache(st.session_state.results)
                        st.success(f"✅ {sel_name} 分析完成！評等 {r['rating']}（{r['score']}分）")
                        st.rerun()
                    else: st.error(f"❌ 失敗：{err}")
            with cb:
                if st.button(f"➕ 加入自選清單",use_container_width=True):
                    curr=st.session_state.stock_list
                    codes=[s.strip() for s in curr.split(",") if s.strip()]
                    if sel_code not in codes:
                        codes.insert(0,sel_code)
                        st.session_state.stock_list=",".join(codes)
                        st.success(f"✅ 已加入：{sel_code} {sel_name}")
                    else: st.info(f"已在清單中：{sel_code}")
            with cc:
                st.caption(f"代號：{sel_code} | 名稱：{sel_name}")
        else:
            st.warning(f"找不到「{query}」，請確認股號或名稱")

    st.markdown("---")

    sids=[s.strip() for s in st.session_state.stock_list.split(",") if s.strip()]
    st.markdown(f"**自選清單：{len(sids)} 支股票** — `{', '.join(sids[:5])}{'...' if len(sids)>5 else ''}`")
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
            r,err=analyze(sid,token,disposed,full_del,delisting,gemini_del,force=force)
            if r: all_res.append(r)
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
    opts=[f"{r['rating']} {r['name']}（{r['sid']}） — {r['score']}分 | {r['price']:,.0f}元 {r['chg']:+.1f}%" for r in sorted_r]
    sel=st.selectbox("🔍 選擇股票查看完整報告",range(len(opts)),format_func=lambda i:opts[i])
    r_sel=sorted_r[sel]
    ca,cb=st.columns(2)
    with ca:
        html=build_wiwynn(r_sel)
        st.download_button(f"📄 下載 {r_sel['name']} 報告",html,f"{r_sel['sid']}_{date.today().strftime('%Y%m%d')}.html","text/html",use_container_width=True)
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
    st.markdown("### 📅 財經行事曆")
    gkey=st.session_state.gemini_key

    c1,c2,c3,c4=st.columns([1,3,3,1])
    with c1:
        if st.button("◄",use_container_width=True):
            if st.session_state.cal_month==1:
                st.session_state.cal_month=12; st.session_state.cal_year-=1
            else: st.session_state.cal_month-=1
            st.session_state.cal_events=[]; st.session_state.cal_events_ts=None
            st.rerun()
    with c2:
        month_zh=["一","二","三","四","五","六","七","八","九","十","十一","十二"][st.session_state.cal_month-1]
        st.markdown(f'<div style="text-align:center;font-size:17px;font-weight:700;color:#fff;padding:8px">{st.session_state.cal_year}年{month_zh}月</div>',unsafe_allow_html=True)
    with c3:
        if not gkey:
            st.warning("設定 Gemini Key 以啟用 AI 搜尋")
        else:
            st.success("🤖 Gemini 搜尋已啟用")
    with c4:
        if st.button("►",use_container_width=True):
            if st.session_state.cal_month==12:
                st.session_state.cal_month=1; st.session_state.cal_year+=1
            else: st.session_state.cal_month+=1
            st.session_state.cal_events=[]; st.session_state.cal_events_ts=None
            st.rerun()

    c_refresh,c_today=st.columns(2)
    with c_refresh:
        if st.button("🔄 重新搜尋事件",use_container_width=True):
            st.session_state.cal_events=[]; st.session_state.cal_events_ts=None
            st.rerun()
    with c_today:
        if st.button("📅 回到本月",use_container_width=True):
            st.session_state.cal_year=date.today().year
            st.session_state.cal_month=date.today().month
            st.session_state.cal_events=[]; st.session_state.cal_events_ts=None
            st.rerun()

    with st.spinner("🤖 Gemini 搜尋財經事件..."):
        events=gemini_fetch_events(gkey,st.session_state.cal_year,st.session_state.cal_month)

    if not gkey:
        st.info("💡 未設定 Gemini API Key，顯示預設重要事件。設定後可獲得完整 AI 搜尋的財經行事曆。")

    bull_cnt=sum(1 for e in events if e.get("impact")=="bullish")
    bear_cnt=sum(1 for e in events if e.get("impact")=="bearish")
    neut_cnt=sum(1 for e in events if e.get("impact")=="neutral")
    co1,co2,co3,co4=st.columns(4)
    co1.metric("📋 總事件",len(events)); co2.metric("🟢 利多",bull_cnt)
    co3.metric("🔴 利空",bear_cnt); co4.metric("⚪ 中性",neut_cnt)

    cal_html=build_calendar_html(events,st.session_state.cal_year,st.session_state.cal_month)
    components.html(cal_html,height=1200,scrolling=True)


def tab_rank():
    st.markdown("### 🏆 今日評等排行")
    results=st.session_state.results
    if not results: st.info("請先在「🔍 個股分析」執行分析"); return
    df=pd.DataFrame([{"評等":r["rating"],"股票":f"{r['name']}({r['sid']})","分數":r["score"],
                      "現價":r["price"],"漲跌%":f"{r['chg']:+.2f}%",
                      "外資":f"{r['fc']:+d}日","投信":f"{r['tc']:+d}日",
                      "目標":f"{r['tp']:,.0f}" if r.get("tp") else "-",
                      "風控":("🚨全額交割" if r.get("is_full_del") else "⚠️下市" if r.get("is_delisting") else "⏱處置" if r.get("is_disposed") else "正常")} for r in results])
    st.dataframe(df,use_container_width=True,hide_index=True)
    buy2=[r for r in results if r["fc"]>0 and r["tc"]>0 and not r.get("is_hard_risk",False)]
    if buy2:
        st.markdown("### ✅ 外資+投信同向買超")
        for r in sorted(buy2,key=lambda x:x["fc"]+x["tc"],reverse=True):
            chg2=r["chg"] or 0
            st.markdown(f'<div style="background:#1a3a27;border-left:4px solid #27ae60;border-radius:8px;padding:9px 13px;margin:4px 0;border:1px solid #27ae60"><strong style="color:#e8eaf0">{r["name"]}（{r["sid"]}）</strong> <span style="color:{"#4ecca3" if chg2>=0 else "#ff6b6b"}">{r["price"]:,.0f}元 {chg2:+.1f}%</span> 外資<span style="color:#4ecca3;font-weight:700">+{r["fc"]}日</span> 投信<span style="color:#4ecca3;font-weight:700">+{r["tc"]}日</span></div>',unsafe_allow_html=True)


def tab_settings():
    st.markdown("### ⚙️ 設定")
    with st.form("sf",clear_on_submit=False):
        st.markdown("**🔑 FinMind Token**（個股分析需要）")
        token=st.text_input("t",value=st.session_state.token,type="password",placeholder="貼上 FinMind Token...",label_visibility="collapsed")
        st.markdown("**🤖 Gemini API Key**（下市偵測 + 財經行事曆，選填）")
        gkey=st.text_input("g",value=st.session_state.gemini_key,type="password",placeholder="貼上 Google Gemini API Key（AIza...）",label_visibility="collapsed")
        st.markdown("**📋 自選股清單**（逗號分隔，支援股號）")
        sl=st.text_area("s",value=st.session_state.stock_list,height=80,label_visibility="collapsed")
        ok=st.form_submit_button("💾 儲存設定",use_container_width=True)
    if ok:
        st.session_state.token=token.strip(); st.session_state.gemini_key=gkey.strip()
        st.session_state.stock_list=sl.strip(); st.success("✅ 儲存完成！")
    c1,c2=st.columns(2)
    with c1:
        st.success(f"FinMind：{st.session_state.token[:8]}...") if st.session_state.token else st.warning("未設定 FinMind Token")
    with c2:
        st.success(f"Gemini：{st.session_state.gemini_key[:8]}...") if st.session_state.gemini_key else st.info("Gemini 未設定（可選）")
    st.markdown("---")
    st.markdown("""
**📌 取得 FinMind Token（免費）**：[finmindtrade.com](https://finmindtrade.com)
**🤖 取得 Gemini API Key（免費）**：[aistudio.google.com/apikey](https://aistudio.google.com/apikey)
**Streamlit Cloud Secrets：**
```toml
FINMIND_TOKEN = "..."
GEMINI_API_KEY = "AIza..."
""")
cached=load_results_cache()
if cached: st.success(f"📦 快取：{len(cached)} 支股票")
if st.button("🗑 清除所有快取",use_container_width=True):
    import shutil
    shutil.rmtree(CACHE_DIR,ignore_errors=True); os.makedirs(CACHE_DIR,exist_ok=True)
    for fn in [fetch_twse_prices_all,fetch_twse_institution_all,fetch_tpex_prices_all,fetch_tpex_institution_all,fetch_disposed_cached,fetch_full_delivery_cached,fetch_delisting_cached]: fn.clear()
    st.session_state.results=[]; st.session_state.gemini_delisting=set()
    st.session_state.cal_events=[]; st.success("✅ 已清除")
def main():
    try:
        t1, t2, t3, t4, t5 = st.tabs(["📡 籌碼掃描", "🔍 個股分析", "📅 財經行事曆", "🏆 排行榜", "⚙️ 設定"])
        
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
        # 修正為 __name__
        st.error(f"App 啟動錯誤：{type(e).__name__}: {e}")
        st.exception(e)

# 修正為 __name__ == "__main__"
if __name__ == "__main__":
    main()
