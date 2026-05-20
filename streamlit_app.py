"""
台股分析系統 — Streamlit App v6 終極修復版
修復項目：
1. 完整補齊底層 apicall, get_price, get_inst 函式，解決 NameError
2. 接回遺失的 build_wiwynn_html、build_full_report_html 函式，消滅 ImportError
3. 完美整合 yfinance 分析師目標價區間與籌碼掃描（吸籌率≥5%）
"""

import time, warnings
from datetime import date, datetime, timedelta
from collections import defaultdict

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import requests

# Fix-4：yfinance（分析師目標價）
try:
    import yfinance as yf
    import numpy as _np
    HAS_YF = True
except ImportError:
    HAS_YF = False

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

# ── 精簡 CSS（只控制 Streamlit 框架，報告內用 wiwynn 樣式）──
st.markdown("""
<style>
[data-testid="stAppViewContainer"]{ background:#f4f6f8!important; }
[data-testid="stHeader"],#MainMenu,footer{ display:none!important; }
.block-container{ padding:.5rem .6rem 1rem!important; max-width:720px; margin:0 auto; }
.stTabs [data-baseweb="tab-list"]{
  background:#1a2332!important; border-radius:12px; padding:5px; gap:3px;
}
.stTabs [data-baseweb="tab"]{ color:#8fa3b8!important; font-size:13px; font-weight:600; border-radius:8px; padding:7px 2px; }
.stTabs [aria-selected="true"]{ background:#27ae60!important; color:#fff!important; }
.stButton>button{
  background:#27ae60!important; color:#fff!important; border:none!important;
  border-radius:10px!important; font-size:15px!important; font-weight:700!important; width:100%;
}
.stButton>button:disabled{ background:#ccc!important; }
</style>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────
for k,v in [("results",[]),("last_run",None),("disposed",set()),
            ("token",""),("stock_list","2330,2454,6669,3661,3034,3017,3037,6515,5274,2376"),
            ("sel_idx",0)]:
    if k not in st.session_state: st.session_state[k]=v

if not st.session_state.token:
    try:
        t=st.secrets.get("FINMIND_TOKEN","")
        if t: st.session_state.token=t
    except Exception: pass

# ── 常數與設定 ─────────────────────────────────────────────────
API="https://api.finmindtrade.com/api/v4/data"
HDR={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"}

NAMES={
    "2330":"台積電","2317":"鴻海","2454":"聯發科","2308":"台達電",
    "2382":"廣達","2303":"聯電","2327":"國巨","2357":"華碩",
    "2379":"瑞昱","2376":"技嘉","2313":"華通","2368":"金像電",
    "2603":"長榮","2609":"陽明","2615":"萬海","2886":"兆豐金",
    "2881":"富邦金","2882":"國泰金","2884":"玉山金","2891":"中信金",
    "1301":"台塑","1303":"南亞","1326":"台化","2002":"中鋼",
    "2412":"中華電","4904":"遠傳","3711":"日月光投控",
    "2408":"南亞科","2474":"可成","2385":"群光",
    "3661":"世芯-KY","6669":"緯穎","2353":"宏碁","2356":"英業達",
    "3034":"聯詠","3037":"欣興","3231":"緯創","1513":"中興電",
    "3293":"鈊象","3017":"奇鋐","6515":"穎威","5274":"信驊",
}

RC={"S":"#1a5c38","A":"#27ae60","B":"#854F0B","C":"#A32D2D"}
RL={"S":"#D0F0DC","A":"#D0F0DC","B":"#FAE0A8","C":"#F7C1C1"}
RS={"S":"#A8E6BB","A":"#A8E6BB","B":"#F5C842","C":"#F09595"}
VBG={"S":"#f0f9f4","A":"#f0f9f4","B":"#fef9ec","C":"#fdf2f2"}
VBC={"S":"#27ae60","A":"#27ae60","B":"#f39c12","C":"#e74c3c"}
VTC={"S":"#145a2c","A":"#145a2c","B":"#5a3e00","C":"#7b1818"}

def nm(s): return NAMES.get(s,s)

# ── 工具 ─────────────────────────────────────────────────────
def fi(s,d=0):
    try: return int(str(s).replace(",","").strip())
    except: return d
def ff(s,d=0.0):
    try: return float(str(s).replace(",","").strip())
    except: return d
def ma(cls,n): return round(sum(cls[-n:])/n,2) if len(cls)>=n else None
def dev(p,m): return round((p-m)/m*100,2) if p and m and m>0 else None

def con(series):
    if not series: return 0
    last=series[-1]
    if last==0: return 0
    d=1 if last>0 else -1; c=0
    for v in reversed(series):
        if (v>0 and d==1) or (v<0 and d==-1): c+=1
        else: break
    return c*d

# ── 補齊底層連線核心 ───────────────────────────────────────────
def apicall(dataset, sid, start_date, token):
    params = {"dataset": dataset, "data_id": sid, "start_date": start_date, "token": token}
    try:
        resp = requests.get(API, params=params, headers=HDR, timeout=12)
        if resp.status_code == 200: return resp.json().get("data", [])
    except Exception: pass
    return []

def get_price(sid, token):
    start = (date.today() - timedelta(days=400)).strftime("%Y-%m-%d")
    rows = apicall("TaiwanStockPrice", sid, start, token)
    recs = []
    for r in rows:
        recs.append({
            "date": r.get("date"),
            "open": ff(r.get("open")),
            "high": ff(r.get("max")),
            "low": ff(r.get("min")),
            "close": ff(r.get("close")),
            "vol": fi(r.get("Trading_Volume")) // 1000
        })
    return recs[-250:]

def get_inst(sid, token):
    start = (date.today() - timedelta(days=15)).strftime("%Y-%m-%d")
    rows = apicall("TaiwanStockInstitutionalInvestorsBuySell", sid, start, token)
    daily_data = defaultdict(lambda: {"f": 0, "t": 0, "d": 0})
    for r in rows:
        d = r.get("date")
        w = r.get("name", "")
        net = fi(r.get("buy", 0)) - fi(r.get("sell", 0))
        net_zhang = net // 1000
        if "Foreign" in w or "外資" in w: daily_data[d]["f"] += net_zhang
        elif "Investment" in w or "投信" in w: daily_data[d]["t"] += net_zhang
        elif "Dealer" in w or "自營" in w: daily_data[d]["d"] += net_zhang
    recs = [{"date": k, "f": v["f"], "t": v["t"], "d": v["d"]} for k, v in daily_data.items()]
    recs.sort(key=lambda x: x["date"])
    return recs[-5:]

# ── Yahoo Finance 分析師共識目標價 ──────────────────────────────
def get_yahoo_analyst_target(stock_id: str) -> dict:
    if not HAS_YF: return None
    for suffix in [".TW", ".TWO"]:
        try:
            ticker_str = f"{stock_id}{suffix}"
            ticker_obj = yf.Ticker(ticker_str)
            info       = ticker_obj.info or {}
            if not info.get("regularMarketPrice"): continue

            mean_price = info.get("targetMeanPrice")
            high_price = info.get("targetHighPrice")
            low_price  = info.get("targetLowPrice")
            count      = info.get("numberOfAnalystOpinions")

            if mean_price and not _np.isnan(mean_price) and float(mean_price) > 0:
                n = int(count) if count else 0
                return {
                    "target": round(float(mean_price), 2),
                    "high":   round(float(high_price), 2) if high_price and not _np.isnan(high_price) else None,
                    "low":    round(float(low_price),  2) if low_price  and not _np.isnan(low_price)  else None,
                    "count":  n,
                    "logic":  f"Yahoo Finance 分析師共識目標價（{n} 位分析師平均）",
                    "source": "yahoo_analyst",
                }
        except Exception: continue
    return None

def get_per(sid, tok):
    s=(date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows=apicall("TaiwanStockPER",sid,s,tok)
    recs=[{"pe":ff(r.get("PER",0)),"pbr":ff(r.get("PBR",0))} for r in rows if ff(r.get("PER",0))>0]
    return recs[-250:] if recs else []

def get_rev(sid,tok):
    s=(date.today()-timedelta(days=450)).strftime("%Y-%m-%d")
    rows=apicall("TaiwanStockMonthRevenue",sid,s,tok)
    recs=[{"rev":ff(r.get("revenue",0)),"yr":fi(r.get("revenue_year",0)),"mo":fi(r.get("revenue_month",0))} for r in rows if ff(r.get("revenue",0))>0]
    recs.sort(key=lambda x:(x["yr"],x["mo"]))
    return recs[-13:]

def get_disposed():
    d = set()
    try:
        r = requests.get("https://openapi.twse.com.tw/v1/announcement/punish", headers=HDR, timeout=5, verify=False)
        if r.status_code == 200:
            for i in r.json():
                c = str(i.get("SecuritiesCode","")).strip()
                if c: d.add(c)
    except Exception: pass
    try:
        r2 = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_announcement_punish", headers=HDR, timeout=5, verify=False)
        if r2.status_code == 200:
            for i in r2.json():
                c = str(i.get("SecuritiesCode", i.get("code",""))).strip()
                if c: d.add(c)
    except Exception: pass
    return d

# ── 分析引擎 ─────────────────────────────────────────────────
def analyze(sid,tok,disposed):
    try:
        pr=get_price(sid,tok)
        if not pr: return None,"無股價數據"
        cls=[r["close"] for r in pr]
        last=pr[-1]; prev=pr[-2] if len(pr)>=2 else last
        p=last["close"]
        chg=round((p-prev["close"])/prev["close"]*100,2) if prev["close"] else 0
        ma5=ma(cls,5); ma20=ma(cls,20); ma60=ma(cls,60); ma200=ma(cls,200)
        dev5=dev(p,ma5); dev200=dev(p,ma200)

        inst=get_inst(sid,tok)
        f_con=con([d["f"] for d in inst]); t_con=con([d["t"] for d in inst]); d_con=con([d["d"] for d in inst])

        per=get_per(sid,tok)
        pe=per[-1]["pe"] if per else None
        pe_avg=round(sum(r["pe"] for r in per)/len(per),1) if per else None
        pbr=per[-1]["pbr"] if per else None

        rev=get_rev(sid,tok)
        rev_yoy=None
        if len(rev)>=13:
            if rev[-13]["rev"]>0: rev_yoy=round((rev[-1]["rev"]-rev[-13]["rev"])/rev[-13]["rev"]*100,1)
        rev_mom=None
        if len(rev)>=2:
            if rev[-2]["rev"]>0: rev_mom=round((rev[-1]["rev"]-rev[-2]["rev"])/rev[-2]["rev"]*100,1)

        tp=None; ts="未取得"; tp_high=None; tp_low=None; tp_count=0

        yahoo_tp = get_yahoo_analyst_target(sid)
        if yahoo_tp:
            tp       = yahoo_tp["target"]
            tp_high  = yahoo_tp["high"]
            tp_low   = yahoo_tp["low"]
            tp_count = yahoo_tp["count"]
            ts       = yahoo_tp["logic"]
        elif pe_avg and pe and rev_yoy is not None and pe > 0:
            yoy_f = min(max(1 + rev_yoy / 100, 0.7), 1.8)
            tp    = round(p * (pe_avg / pe) * yoy_f, 0)
            ts    = "PE均值×成長估算（備用）"

        sc=50; pos=[]; neg=[]; warn=[]
        if dev5 is not None:
            if   dev5<-5:  sc+=18;pos.append(f"5日線回測{dev5:+.1f}%（良好進場）")
            elif dev5<=2:  sc+=10;pos.append(f"5日線乖離健康（{dev5:+.1f}%）")
            elif dev5<=8:  sc+=2; warn.append(f"5日線乖離偏高（{dev5:+.1f}%）")
            else:          sc-=10;neg.append(f"5日線乖離過高（{dev5:+.1f}%），追高風險")
        if dev200 and dev200>50: sc-=8;warn.append(f"年線乖離偏高（{dev200:+.1f}%）")
        if tp and p:
            up=(tp-p)/p*100
            if   up>20:  sc+=15;pos.append(f"距目標價+{up:.1f}%空間")
            elif up>10:  sc+=8; pos.append(f"距目標價+{up:.1f}%")
            elif up>0:   sc+=3
            elif up>-10: sc-=5; warn.append(f"現價略超目標（{up:.1f}%）")
            else:        sc-=12;neg.append(f"現價大幅超越目標（{up:.1f}%）")
        if rev_yoy is not None:
            if   rev_yoy>=20: sc+=8;pos.append(f"月營收YoY+{rev_yoy:.1f}%（高成長）")
            elif rev_yoy>=5:  sc+=4;pos.append(f"月營收YoY+{rev_yoy:.1f}%")
            elif rev_yoy<0:   sc-=5;neg.append(f"月營收年減YoY{rev_yoy:.1f}%")
        if   f_con>=3: sc+=12;pos.append(f"外資連買{f_con}日")
        elif f_con>=1: sc+=5; pos.append("外資今日買超")
        elif f_con<=-3:sc-=10;neg.append(f"外資連賣{abs(f_con)}日")
        elif f_con<0:  sc-=4; warn.append("外資今日賣超")
        if   t_con>=5: sc+=12;pos.append(f"投信連買{t_con}日（深度認養）")
        elif t_con>=3: sc+=8; pos.append(f"投信連買{t_con}日")
        elif t_con>=1: sc+=3; pos.append("投信今日買超")
        elif t_con<=-3:sc-=10;neg.append(f"投信連賣{abs(t_con)}日")
        elif t_con<0:  sc-=4; warn.append("投信今日賣超")
        if f_con>0 and t_con>0:   sc+=5;pos.append("外資投信同向買超，無對作")
        elif f_con<0 and t_con<0: sc-=8;neg.append("外資投信同向賣超，籌碼惡化")
        if pe and pe_avg and pe_avg>0:
            pv=(pe-pe_avg)/pe_avg*100
            if   pv<-20:sc+=8; pos.append(f"PE{pe:.1f}x低於均值，低估訊號")
            elif pv<0:  sc+=4
            elif pv>20: sc-=5; warn.append(f"PE{pe:.1f}x偏高，估值偏貴")
        sc=max(0,min(100,sc))
        if   sc>=80: rt,lb="S","強烈推薦"
        elif sc>=65: rt,lb="A","建議買入"
        elif sc>=45: rt,lb="B","觀　　望"
        else:        rt,lb="C","避　　開"
        r52=pr[-252:] if len(pr)>=252 else pr
        return {
            "sid":sid,"name":nm(sid),"price":p,"prev":prev["close"],"chg":chg,
            "ma5":ma5,"ma20":ma20,"ma60":ma60,"ma200":ma200,
            "dev5":dev5,"dev200":dev200,
            "h52":round(max(r["high"] for r in r52),2),
            "l52":round(min(r["low"]  for r in r52),2),
            "vol":last["vol"],"last5":[r["close"] for r in pr[-5:]],
            "inst":inst,"f_con":f_con,"t_con":t_con,"d_con":d_con,
            "pe":pe,"pe_avg":pe_avg,"pbr":pbr,"rev_yoy":rev_yoy,"rev_mom":rev_mom,
            "tp":tp,"ts":ts,
            "tp_high":tp_high, "tp_low":tp_low, "tp_count":tp_count,
            "score":sc,"rating":rt,"label":lb,
            "pos":pos,"neg":neg,"warn":warn,
            "is_disposed":sid in disposed,"date":last["date"],
        }, None
    except Exception as e:
        return None, str(e)

# ================================================================
# 🏛️ 接回完整 wiwynn 樣式卡片渲染與 HTML 模板生成引擎
# ================================================================
WIWYNN_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f4f6f8;font-family:'Helvetica Neue',Arial,sans-serif;padding:16px 8px;color:#2c3e50}
.wrap{max-width:660px;margin:0 auto}
.hdr{background:#1a2332;border-radius:14px 14px 0 0;padding:20px 22px}
.hdr-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
.hdr h1{font-size:20px;color:#fff;font-weight:600}
.hdr-sub{font-size:11px;color:#8fa3b8;margin-top:3px}
.rating-circle{width:68px;height:68px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0}
.rating-circle .letter{font-size:24px;font-weight:600;line-height:1}
.rating-circle .lbl{font-size:8px;margin-top:2px;letter-spacing:.05em}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}
.tag{font-size:10px;padding:2px 8px;border-radius:99px;font-weight:500}
.tag-g{background:#27ae6033;color:#27ae60;border:1px solid #27ae6055}
.tag-r{background:#e74c3c33;color:#e74c3c;border:1px solid #e74c3c55}
.tag-a{background:#f39c1233;color:#e67e22;border:1px solid #f39c1255}
.tag-p{background:#8e44ad33;color:#8e44ad;border:1px solid #8e44ad55}
.sum-bar{background:#fff;border-left:4px solid #e67e22;border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:2px;display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px}
.sum-cell p:first-child{font-size:10px;color:#777;text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px}
.sum-cell p:last-child{font-size:18px;font-weight:700}
.up{color:#27ae60}.dn{color:#c0392b}.wn{color:#e67e22}
.card{background:#fff;border-radius:10px;padding:15px 18px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.card-title{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:#666;margin-bottom:10px}
.row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f0f0;font-size:13px;gap:10px}
.row:last-child{border-bottom:none}
.row-l{color:#777;flex-shrink:0}.row-v{font-weight:500;text-align:right}
.risk-bar{height:10px;border-radius:5px;background:linear-gradient(90deg,#27ae60 0%,#f39c12 55%,#e74c3c 82%);position:relative;margin:10px 0 3px}
.risk-needle{position:absolute;top:-3px;width:3px;height:16px;background:#1a2332;border-radius:2px}
.risk-scale{display:flex;justify-content:space-between;font-size:10px;color:#999}
.rf-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:9px}
.rf{background:#f8f9fa;border-radius:7px;padding:7px 9px;border:1px solid #eee}
.rf p:first-child{font-size:10px;color:#777;margin-bottom:1px}
.rf p:last-child{font-size:12px;font-weight:500}
.chip-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:7px;margin:9px 0}
.chip{border-radius:8px;padding:9px;text-align:center;border:1px solid}
.chip.buy{background:#eaf3de;border-color:#97c459}
.chip.sell{background:#fceaea;border-color:#f09595}
.chip.neut{background:#f8f9fa;border-color:#ddd}
.chip p:first-child{font-size:10px;color:#777;margin-bottom:2px}
.chip p:nth-child(2){font-size:14px;font-weight:600;margin-bottom:2px}
.chip p:last-child{font-size:10px;color:#777}
.ev{display:flex;gap:9px;padding:8px 0;border-bottom:1px solid #f0f0f0;font-size:12px}
.ev:last-child{border-bottom:none}
.ev-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:3px}
.ev strong{display:block;font-size:12px;margin-bottom:1px;color:#1a2332}
.ev span{color:#555;line-height:1.5}
.sc-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:9px}
.sc-bull{background:#eaf3de;border-radius:8px;padding:9px 11px;font-size:11px;color:#27500A;border:1px solid #97c459;line-height:1.6}
.sc-bear{background:#fceaea;border-radius:8px;padding:9px 11px;font-size:11px;color:#791F1F;border:1px solid #f09595;line-height:1.6}
.strat{display:flex;gap:9px;padding:7px 0;border-bottom:1px solid #f0f0f0;font-size:12px;align-items:flex-start;line-height:1.6}
.strat:last-child{border-bottom:none}
.strat-icon{font-size:14px;flex-shrink:0}
.box-warn{background:#fef9ec;border-left:4px solid #f39c12;border-radius:0 6px 6px 0;padding:9px 12px;font-size:12px;color:#7d4e00;margin-top:8px;line-height:1.6}
.box-danger{background:#fdf2f2;border-left:4px solid #e74c3c;border-radius:0 6px 6px 0;padding:9px 12px;font-size:12px;color:#7b1818;margin-top:7px;line-height:1.6}
.box-ok{background:#f0f9f4;border-left:4px solid #27ae60;border-radius:0 6px 6px 0;padding:9px 12px;font-size:12px;color:#145a2c;margin-top:7px;line-height:1.6}
.verdict{border-radius:10px;padding:12px 15px;border:1px solid}
.verdict-big{font-size:26px;font-weight:700}
.trend-compare{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:9px}
.trend-cell{background:#f8f9fa;border-radius:7px;padding:9px 11px;border:1px solid #eee}
.trend-cell-title{font-size:10px;color:#777;margin-bottom:5px;font-weight:500}
.trend-bar-row{display:flex;align-items:center;gap:5px;font-size:11px;margin-bottom:3px}
.trend-bar-bg{flex:1;background:#eee;border-radius:3px;height:5px;overflow:hidden}
.trend-bar-fill-g{height:5px;border-radius:3px;background:#27ae60}
.trend-bar-fill-r{height:5px;border-radius:3px;background:#e74c3c}
.trend-date{color:#aaa;width:28px;flex-shrink:0;font-size:10px}
.tp-bar-wrap{background:#f0f0f0;border-radius:6px;height:12px;position:relative;margin:7px 0 3px;overflow:hidden}
.tp-bar-fill{height:12px;border-radius:6px}
.tp-labels{display:flex;justify-content:space-between;font-size:10px;color:#888}
.alert-timer{background:#fff8e1;border:1px solid #ffc107;border-radius:9px;padding:11px 14px;margin-bottom:10px;display:flex;align-items:center;gap:11px}
.alert-icon{font-size:22px;flex-shrink:0}
.alert-text strong{display:block;font-size:13px;color:#7d4e00;margin-bottom:2px}
.alert-text span{font-size:11px;color:#a06a00;line-height:1.5}
.inst-tbl{width:100%;border-collapse:collapse;font-size:11px;margin-top:8px}
.inst-tbl th{background:#f4f6f8;color:#555;padding:5px 7px;font-weight:600;border-bottom:1px solid #ddd;text-align:right}
.inst-tbl th:first-child{text-align:left}
.inst-tbl td{padding:5px 7px;border-bottom:1px solid #f0f0f0;text-align:right}
.inst-tbl td:first-child{text-align:left;color:#555}
.footer{background:#f8f9fa;border-radius:0 0 12px 12px;padding:11px 16px;font-size:10px;color:#999;line-height:1.6;border-top:1px solid #eee}
"""

def _chip_cls(v): return "buy" if v>0 else ("sell" if v<0 else "neut")
def _chip_cc(v): return "up" if v>0 else ("dn" if v<0 else "")
def _fv(v, unit="", dig=2): return "N/A" if v is None else f"{v:,.{dig}f}{unit}"

def build_wiwynn_html(r):
    sid=r["sid"]; sname=r["name"]; rating=r["rating"]
    p=r["price"]; prev=r["prev"]; chg=r["chg"] or 0
    dev5=r.get("dev5") or 0; dev200=r.get("dev200") or 0
    sc=r["score"]; label=r["label"]
    f_con=r["f_con"]; t_con=r["t_con"]; d_con=r["d_con"]
    inst=r["inst"]; ma5=r["ma5"]; ma20=r["ma20"]
    tp=r["tp"]; ts_=r["ts"]
    tp_high=r.get("tp_high"); tp_low=r.get("tp_low"); tp_count=r.get("tp_count",0)
    pe=r["pe"]; pe_avg=r["pe_avg"]; pbr=r["pbr"]
    rev_yoy=r.get("rev_yoy"); rev_mom=r.get("rev_mom")

    rc=RC[rating]; lc=RL[rating]; sc2=RS[rating]
    vbg=VBG[rating]; vbc=VBC[rating]; vtc=VTC[rating]
    cc="up" if chg>=0 else "dn"
    bclr="#27ae60" if sc>=65 else ("#f39c12" if sc>=45 else "#e74c3c")

    tags=""
    if r["is_disposed"]: tags+='<span class="tag tag-r">🚨 處置股</span>'
    if t_con>=5:   tags+=f'<span class="tag tag-g">投信連買{t_con}日 ⭐</span>'
    elif t_con>=1: tags+=f'<span class="tag tag-g">投信買超{t_con}日</span>'
    elif t_con<=-3:tags+=f'<span class="tag tag-r">投信連賣{abs(t_con)}日</span>'
    if f_con>=3:   tags+=f'<span class="tag tag-g">外資連買{f_con}日</span>'
    elif f_con<=-3:tags+=f'<span class="tag tag-r">外資連賣{abs(f_con)}日</span>'
    if tp and p:
        up2=(tp-p)/p*100
        if up2>10: tags+=f'<span class="tag tag-p">目標+{up2:.0f}%空間</span>'

    alert_html=""
    if r["is_disposed"]:
        alert_html="""<div class="alert-timer"><div class="alert-icon">🚨</div><div class="alert-text"><strong>處置股警告 — 流動性風險極高</strong><span>目前每5~20分鐘才撮合一次，風控考量策略建議：暫不操作，靜待出關。</span></div></div>"""

    pos_str = "、".join(r["pos"][:2]) if r["pos"] else ""
    neg_str = "、".join(r["neg"][:2]) if r["neg"] else ""
    upgrade_cond = "三大法人持續同向大額買超，短線重回多頭軌道" if rating in ("S","A") else "外資轉買超連續2日 + 5日線乖離收斂至合理區"
    downgrade_cond= f"跌破月線（{_fv(ma20,'元',0)}）收盤，或外資轉連賣3日以上"

    verdict_card=f"""<div class="card"><p class="card-title"> Bars 綜合決策評等（推薦分數 {sc}/100）</p><div class="verdict" style="background:{vbg};border-color:{vbc}"><span class="verdict-big" style="color:{vbc}">{rating}</span><span style="font-size:15px;font-weight:600;color:{vbc};margin-left:8px">{label}</span><p style="margin-top:8px;font-size:13px;color:{vtc};line-height:1.7">{"<span class='up'>正面：</span>"+pos_str+"<br>" if pos_str else ""}{"<span class='dn'>負面：</span>"+neg_str if neg_str else ""}</p></div><div class="box-warn">⚠ <strong>升降評重要觸發條件：</strong><br>升評：{upgrade_cond}<br>降評：{downgrade_cond}</div></div>"""

    last5=r.get("last5",[p])
    trend_rows=""
    for i,c in enumerate(last5):
        d5=round((c-ma5)/ma5*100,1) if ma5 and ma5>0 else 0
        w=min(abs(d5)*5,100)
        lbl2="今日" if i==len(last5)-1 else f"T-{len(last5)-1-i}"
        fc="trend-bar-fill-g" if d5>=0 else "trend-bar-fill-r"
        trend_rows+=f"""<div class="trend-bar-row"><span class="trend-date">{lbl2}</span><div class="trend-bar-bg"><div class="{fc}" style="width:{w}%"></div></div><span style="font-size:11px;color:{( '#27ae60' if d5>=0 else '#c0392b')};width:60px;text-align:right">{d5:+.1f}%</span></div>"""

    risk_label=("🟢 低度風險" if sc>=65 else "🟡 中度風險" if sc>=45 else "🔴 高度風險")
    tech_card=f"""<div class="card"><p class="card-title">🔍 技術面指標儀表板</p><div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;margin-bottom:12px"><div><p style="font-size:36px;font-weight:700;color:{bclr};line-height:1">{sc}</p><p style="font-size:11px;color:{bclr};font-weight:600">/ 100　{risk_label}</p></div><div style="flex:1;min-width:170px"><div class="row"><span class="row-l">今日收盤</span><span class="row-v">{p:,.2f} 元</span></div><div class="row"><span class="row-l">5日均線</span><span class="row-v"><strong>{_fv(ma5,'元',2)}</strong></span></div><div class="row"><span class="row-l">5日線乖離</span><span class="row-v"><strong>{dev5:+.2f}%</strong></span></div><div class="row"><span class="row-l">月線乖離</span><span class="row-v">{(f"{dev(p,ma20):+.2f}%" if ma20 else "N/A")}</span></div></div></div><div style="background:#f8f9fa;border-radius:8px;padding:10px;border:1px solid #eee;margin-bottom:10px"><p style="font-size:10px;font-weight:600;color:#666;margin-bottom:8px;text-transform:uppercase">近5日 5日線乖離趨勢</p>{trend_rows}</div><div class="risk-bar"><div class="risk-needle" style="left:{min(sc,99)}%"></div></div><div class="rf-grid"><div class="rf"><p>MA20 月線</p><p>{_fv(ma20,'元',0)}</p></div><div class="rf"><p>52週高點</p><p class="dn">{_fv(r.get('h52'),'元',0)}</p></div><div class="rf"><p>52週低點</p><p class="up">{_fv(r.get('l52'),'元',0)}</p></div><div class="rf"><p>今日成交量</p><p>{f"{r.get('vol',0):,} 張"}</p></div></div></div>"""

    ft=inst[-1]["f"] if inst else 0
    tt2=inst[-1]["t"] if inst else 0
    dt=inst[-1]["d"] if inst else 0
    tot=ft+tt2+dt
    inst_tbl_rows=""
    for d in inst:
        raw=d.get("date","")
        ds=raw[-5:]
        to=d["f"]+d["t"]+d["d"]
        inst_tbl_rows+=f"""<tr><td>{ds}</td><td class="{'up' if d['f']>=0 else 'dn'}">{d['f']:+,}</td><td class="{'up' if d['t']>=0 else 'dn'}">{d['t']:+,}</td><td class="{'up' if d['d']>=0 else 'dn'}">{d['d']:+,}</td><td class="{'up' if to>=0 else 'dn'}"><strong>{to:+,}</strong></td></tr>"""

    chip_card=f"""<div class="card"><p class="card-title">💼 籌碼面 — 三大法人動向</p><div class="chip-grid"><div class="chip {_chip_cls(ft)}"><p>外資</p><p class="{_chip_cc(ft)}">{ft:+,} 張</p></div><div class="chip {_chip_cls(tt2)}"><p>投信</p><p class="{_chip_cc(tt2)}">{tt2:+,} 張</p></div><div class="chip {_chip_cls(dt)}"><p>自營商</p><p class="{_chip_cc(dt)}">{dt:+,} 張</p></div></div><p style="font-size:11px;color:#555;margin-bottom:10px">三大法人今日合計買賣超：<strong class="{'up' if tot>=0 else 'dn'}">{tot:+,} 張</strong></p><table class="inst-tbl"><tr><th>日期</th><th>外資</th><th>投信</th><th>自營</th><th>合計</th></tr>{inst_tbl_rows}</table></div>"""

    tp_card=""
    if tp and p:
        up2=(tp-p)/p*100
        exceed=up2<0
        bw=min(p/tp*100,100) if tp>0 else 50
        range_bar=""
        if tp_high and tp_low and tp_high > tp_low:
            curr_pct=min(max((p-tp_low)/(tp_high-tp_low)*100,0),100)
            mean_pct=min(max((tp-tp_low)/(tp_high-tp_low)*100,0),100)
            range_bar=f"""<div style="margin-top:10px"><p style="font-size:10px;font-weight:600;color:#666;margin-bottom:6px">分析師目標價區間（低/均/高）</p><div style="position:relative;background:#f0f0f0;border-radius:6px;height:14px;margin-bottom:4px"><div style="position:absolute;left:{mean_pct:.0f}%;top:-4px;width:3px;height:22px;background:#2980b9;z-index:2"></div><div style="position:absolute;left:{curr_pct:.0f}%;top:-4px;width:3px;height:22px;background:#1a2332;z-index:3"></div></div><div style="display:flex;justify-content:space-between;font-size:10px;color:#888"><span>低 {tp_low:,.0f}</span><span style="color:#2980b9;font-weight:600">均 {tp:,.0f}</span><span>高 {tp_high:,.0f}</span></div></div>"""

        tp_card=f"""<div class="card"><p class="card-title">💰 估值與法人目標價預估</p><div class="row"><span class="row-l">估值邏輯</span><span class="row-v">{ts_}</span></div><div class="row"><span class="row-l">法人平均目標價</span><span class="row-v up" style="font-size:15px;font-weight:700">{tp:,.0f} 元</span></div><div class="row"><span class="row-l">現價與目標價空間</span><span class="row-v {'up' if not exceed else 'dn'}"><strong>{up2:+.1f}%</strong></span></div>{range_bar}</div>"""

    val_card=f"""<div class="card"><p class="card-title">📊 財報基本面估值</p><div class="rf-grid"><div class="rf"><p>本益比 PE</p><p>{_fv(pe,'x',1)}</p></div><div class="rf"><p>近一年平均 PE</p><p>{_fv(pe_avg,'x',1)}</p></div><div class="rf"><p>淨值比 PBR</p><p>{_fv(pbr,'x',1)}</p></div><div class="rf"><p>月營收 YoY</p><p class="{'up' if (rev_yoy or 0)>=0 else 'dn'}">{_fv(rev_yoy,'%',1)}</p></div></div></div>"""

    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8"><style>{WIWYNN_CSS}</style></head><body><div class="wrap"><div class="hdr"><div class="hdr-top"><div><h1>{sname} <span style="font-size:14px;font-weight:400;color:#8fa3b8">{sid}</span></h1><p class="hdr-sub">台股 | 收盤 {p:,.2f} 元 | 5日乖離 {dev5:+.1f}%</p><div class="tags">{tags}</div></div><div class="rating-circle" style="background:{rc}"><span class="letter" style="color:#fff">{rating}</span><span class="lbl" style="color:#fff">{label}</span></div></div></div><div class="sum-bar" style="border-left-color:{rc}"><div class="sum-cell"><p>昨日收盤</p><p>{prev:,.2f} 元</p></div><div class="sum-cell"><p>今日收盤</p><p class="{cc}">{p:,.2f} 元</p></div><div class="sum-cell"><p>今日漲跌</p><p class="{cc}">{chg:+.2f}%</p></div><div class="sum-cell"><p>5日均線</p><p>{_fv(ma5,'元',2)}</p></div></div>{alert_html}{verdict_card}{tech_card}{chip_card}{tp_card}{val_card}</div></body></html>"""

def build_full_report_html(results):
    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    nav="".join(f'<a href="#s{r["sid"]}" style="display:inline-block;font-size:11px;padding:3px 9px;border-radius:16px;font-weight:600;text-decoration:none;margin:2px;background:{RC[r["rating"]]};color:white">{r["name"]}</a>' for r in sorted(results,key=lambda x:x["score"],reverse=True))
    cards=""
    for r in sorted(results,key=lambda x:(x["is_disposed"],-x["score"])):
        inner=build_wiwynn_html(r)
        start=inner.find("<body>")+6; end=inner.find("</body>")
        cards+=f'<div id="s{r["sid"]}" style="scroll-margin-top:60px">{inner[start:end]}</div>'
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>{WIWYNN_CSS}</style></head><body><div class="wrap"><div style="background:#1a2332;border-radius:10px;padding:10px 14px;margin-bottom:12px;position:sticky;top:0;z-index:99"><div style="font-size:10px;color:#8fa3b8;margin-bottom:5px">📊 投資組合診斷面板</div>{nav}</div>{cards}</div></body></html>"""

# ================================================================
# ── Streamlit 網頁分頁配置 ──────────────────────────────────────
# ================================================================
def tab_home():
    results=st.session_state.results
    token=st.session_state.token
    sids=[s.strip() for s in st.session_state.stock_list.split(",") if s.strip()]

    st.markdown("""
<div style="background:linear-gradient(135deg,#1a2332,#2c3e50);border-radius:14px;padding:16px 20px;margin-bottom:12px">
  <div style="font-size:20px;font-weight:800;color:#fff">📊 台股大數據智慧分析系統</div>
  <div style="font-size:11px;color:#8fa3b8;margin-top:3px">wiwynn 格式完整視覺化報告</div>
</div>""", unsafe_allow_html=True)

    if token:
        st.success(f"✅ API 通行證已就緒 | 追蹤標的：{len(sids)} 檔")
    else:
        st.error("⚠️ 請至「⚙️ 系統設定」填入你的 FinMind Token 才能啟動連線功能")

    run=st.button("🔄 開始分析全部股票",disabled=not token,use_container_width=True)

    if run:
        errors=[]
        with st.spinner("取得最新上市櫃處置股風控清單..."):
            st.session_state.disposed=get_disposed()
        all_res=[]; bar=st.progress(0,"啟動雷達中...")
        for i,sid in enumerate(sids):
            bar.progress((i+1)/len(sids),text=f"多維度體檢 {nm(sid)}（{i+1}/{len(sids)}）")
            r,err=analyze(sid,token,st.session_state.disposed)
            if r: all_res.append(r)
            else: errors.append(f"{sid}：{err}")
        bar.empty()
        if all_res:
            st.session_state.results=sorted(all_res,key=lambda x:x["score"],reverse=True)
            st.session_state.last_run=datetime.now()
            st.success(f"✨ 全數掃描完畢！共跑通 {len(all_res)} 檔股票")
        else:
            st.error("❌ 連線異常，請確認 Token 填寫是否正確。")
        if errors:
            with st.expander(f"⚠️ 診斷回報：{len(errors)} 支標的略過"):
                for e in errors: st.write(e)
        st.rerun()

    if not results:
        st.info("👆 請點擊上方「開始分析全部股票」按鈕下載即時財報數據")
        return

    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    c1,c2,c3,c4=st.columns(4)
    for col,(rt,em,bg) in zip([c1,c2,c3,c4],[("S","⭐","#d4edda"),("A","✅","#d4edda"),("B","👀","#fff3cd"),("C","❌","#f8d7da")]):
        col.markdown(f'<div style="background:{bg};border-radius:9px;padding:9px;text-align:center"><div style="font-size:17px">{em}</div><div style="font-size:20px;font-weight:800;color:{RC[rt]}">{cnts.get(rt,0)}</div><div style="font-size:10px;color:#555">{rt} 評等</div></div>',unsafe_allow_html=True)

    st.markdown("---")
    full_html=build_full_report_html(results)
    dt=date.today().strftime("%Y%m%d")
    st.download_button("📥 下載整合多股戰略報告 (HTML)", full_html, f"portfolio_{dt}.html", "text/html", use_container_width=True)

    sorted_r=sorted(results,key=lambda x:x["score"],reverse=True)
    opts=[f"[{r['rating']}] {r['name']}({r['sid']}) — {r['score']}分" for r in sorted_r]
    sel=st.selectbox("🔍 切換個股儀表板",range(len(opts)),format_func=lambda i:opts[i])

    r_sel=sorted_r[sel]
    html=build_wiwynn_html(r_sel)
    components.html(html, height=1800, scrolling=True)

def tab_rank():
    st.markdown("### 🏆 個股戰力綜合評等排行")
    results=st.session_state.results
    if not results: st.info("請先在「🏠 首頁」執行大數據掃描"); return
    df=pd.DataFrame([{
        "評等":r["rating"],"股票":f"{r['name']}({r['sid']})","分數":r["score"],"收盤價":r["price"],
        "今日漲跌":f"{r['chg']:+.2f}%","外資連動":f"{r['f_con']:+d}日","投信連動":f"{r['t_con']:+d}日",
        "目標價":f"{r['tp']:,.0f}" if r["tp"] else "估算中"
    } for r in results])
    st.dataframe(df,use_container_width=True,hide_index=True)

def tab_scanner():
    st.markdown("### 📡 籌碼面智慧濾網掃描")
    results=st.session_state.results
    if not results: st.info("請先在「🏠 首頁」執行大數據掃描"); return
    
    st.markdown("#### 🔥 法人焦點熱門股（資金聚集度 ≥ 5%）")
    hot=[]
    for r in results:
        if r["is_disposed"] or not r["inst"]: continue
        ft=r["inst"][-1]["f"]; tt=r["inst"][-1]["t"]; vol=r.get("vol",0) or 1
        absorb_rate = (ft+tt)/vol*100
        if ft>0 and tt>0 and absorb_rate>=5:
            hot.append({**r,"ab":round(absorb_rate,1),"ft":ft,"tt":tt})
            
    hot.sort(key=lambda x:x["ab"],reverse=True)
    if hot:
        for r in hot[:10]:
            tier="🔴極度火熱" if r["ab"]>=15 else "🟠高度熱門" if r["ab"]>=8 else "🟡資金升溫"
            chg=r["chg"] or 0; cc2="#27ae60" if chg>=0 else "#c0392b"
            st.markdown(f'<div style="background:#fff;border-left:4px solid #27ae60;border-radius:8px;padding:9px 13px;margin:5px 0;border:1px solid #c3e6cb"><div style="display:flex;justify-content:space-between"><strong style="color:#1a2332">{r["name"]}（{r["sid"]}）</strong><span style="color:#e67e22;font-weight:700">{tier} ({r["ab"]}%)</span></div><span style="font-size:13px;color:#555">{r["price"]:,.0f}元 <span style="color:{cc2}">{chg:+.1f}%</span> | 外資買超：{r["ft"]:,}張 | 投信買超：{r["tt"]:,}張</span></div>',unsafe_allow_html=True)
    else: 
        st.info("今日盤後暫無符合外資與投信聯手強吸籌（≥5%）之標的")

def tab_settings():
    st.markdown("### ⚙️ 系統核心配置")
    with st.form("sf",clear_on_submit=False):
        st.markdown("**🔑 FinMind 官方 API 金鑰**")
        token=st.text_input("Token",value=st.session_state.token,type="password",placeholder="請在此處輸入你的超長 Token 密鑰...",label_visibility="collapsed")
        st.markdown("**📋 監控自選股清單（以半形逗號分隔）**")
        sl=st.text_area("stocks",value=st.session_state.stock_list,height=80,label_visibility="collapsed")
        ok=st.form_submit_button("💾 儲存設定並寫入快取",use_container_width=True)
    if ok:
        st.session_state.token=token.strip()
        st.session_state.stock_list=sl.strip()
        st.success("儲存設定成功！請切換至「🏠 首頁」點擊按鈕開始分析。")

def main():
    t1,t2,t3,t4=st.tabs(["🏠 首頁","🏆 綜合排行","📡 籌碼掃描","⚙️ 系統設定"])
    with t1: tab_home()
    with t2: tab_rank()
    with t3: tab_scanner()
    with t4: tab_settings()

if __name__=="__main__": 
    main()