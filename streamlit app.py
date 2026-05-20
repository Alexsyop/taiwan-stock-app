"""
台股分析系統 — Streamlit App v4 wiwynn 版
分析結果完全套用 wiwynn_6669_report.html 模板格式
用 st.components.v1.html() 在 App 內嵌入完整報告
"""

import time, warnings
from datetime import date, datetime, timedelta
from collections import defaultdict

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
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

# ── 常數 ─────────────────────────────────────────────────────
API="https://api.finmindtrade.com/api/v4/data"
HDR={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"}
NAMES={
    "2330":"台積電","2454":"聯發科","6669":"緯穎","3661":"世芯-KY",
    "3034":"聯詠","3017":"奇鋐","3037":"欣興","6515":"穎威",
    "5274":"信驊","2313":"華通","3048":"益登","3231":"緯創",
    "2376":"技嘉","2317":"鴻海","2382":"廣達","2308":"台達電",
    "2603":"長榮","2609":"陽明","1513":"中興電","3293":"鈊象",
    "3529":"力旺","3665":"貿聯-KY","3167":"達亮","3081":"聯惠",
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

# ── API ───────────────────────────────────────────────────────
def apicall(ds,sid,start,tok):
    try:
        r=requests.get(API,headers=HDR,timeout=15,verify=False,
          params={"dataset":ds,"data_id":sid,"start_date":start,"token":tok})
        if r.status_code==200: return r.json().get("data",[])
    except Exception: pass
    return []

def get_price(sid,tok):
    s=(date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows=apicall("TaiwanStockPrice",sid,s,tok)
    recs=[{"date":r.get("date","")[:10],"close":ff(r.get("close",0)),
           "high":ff(r.get("max",r.get("high",0))),
           "low":ff(r.get("min",r.get("low",0))),
           "vol":fi(r.get("Trading_Volume",0))//1000}
          for r in rows if ff(r.get("close",0))>0]
    recs.sort(key=lambda x:x["date"])
    return recs

def get_inst(sid,tok):
    s=(date.today()-timedelta(days=35)).strftime("%Y-%m-%d")
    rows=apicall("TaiwanStockInstitutionalInvestorsBuySell",sid,s,tok)
    dm=defaultdict(lambda:{"f":0,"t":0,"d":0})
    for r in rows:
        n2=str(r.get("name",""))
        net=fi(r.get("buy",0))-fi(r.get("sell",0))
        d=r.get("date","")[:10]
        if "Foreign" in n2 or "外資" in n2: dm[d]["f"]+=net
        elif "Trust" in n2 or "投信" in n2: dm[d]["t"]+=net
        elif "Dealer" in n2 or "自營" in n2:dm[d]["d"]+=net
    return [{"date":d,"f":dm[d]["f"]//1000,"t":dm[d]["t"]//1000,"d":dm[d]["d"]//1000}
            for d in sorted(dm.keys())[-5:]]

def get_per(sid,tok):
    s=(date.today()-timedelta(days=400)).strftime("%Y-%m-%d")
    rows=apicall("TaiwanStockPER",sid,s,tok)
    recs=[{"pe":ff(r.get("PER",0)),"pbr":ff(r.get("PBR",0))}
          for r in rows if ff(r.get("PER",0))>0]
    return recs[-250:] if recs else []

def get_rev(sid,tok):
    s=(date.today()-timedelta(days=450)).strftime("%Y-%m-%d")
    rows=apicall("TaiwanStockMonthRevenue",sid,s,tok)
    recs=[{"rev":ff(r.get("revenue",0)),"yr":fi(r.get("revenue_year",0)),"mo":fi(r.get("revenue_month",0))}
          for r in rows if ff(r.get("revenue",0))>0]
    recs.sort(key=lambda x:(x["yr"],x["mo"]))
    return recs[-13:]

def get_disposed():
    d=set()
    try:
        r=requests.get("https://openapi.twse.com.tw/v1/announcement/punish",headers=HDR,timeout=8,verify=False)
        if r.status_code==200:
            for i in r.json():
                c=str(i.get("SecuritiesCode","")).strip()
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
        time.sleep(0.3)

        inst=get_inst(sid,tok)
        f_con=con([d["f"] for d in inst]); t_con=con([d["t"] for d in inst]); d_con=con([d["d"] for d in inst])
        time.sleep(0.3)

        per=get_per(sid,tok)
        pe=per[-1]["pe"] if per else None
        pe_avg=round(sum(r["pe"] for r in per)/len(per),1) if per else None
        pbr=per[-1]["pbr"] if per else None
        time.sleep(0.3)

        rev=get_rev(sid,tok)
        rev_yoy=None
        if len(rev)>=13:
            if rev[-13]["rev"]>0: rev_yoy=round((rev[-1]["rev"]-rev[-13]["rev"])/rev[-13]["rev"]*100,1)
        rev_mom=None
        if len(rev)>=2:
            if rev[-2]["rev"]>0: rev_mom=round((rev[-1]["rev"]-rev[-2]["rev"])/rev[-2]["rev"]*100,1)

        tp=None; ts="未取得"
        if pe_avg and pe and rev_yoy is not None and pe>0:
            yf=min(max(1+rev_yoy/100,0.7),1.8)
            tp=round(p*(pe_avg/pe)*yf,0); ts="PE均值×成長估算"

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
            "tp":tp,"ts":ts,"score":sc,"rating":rt,"label":lb,
            "pos":pos,"neg":neg,"warn":warn,
            "is_disposed":sid in disposed,"date":last["date"],
        }, None
    except Exception as e:
        return None, str(e)

# ================================================================
# ★ wiwynn HTML 報告生成器
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

def _chip_cls(v):
    if v>0: return "buy"
    if v<0: return "sell"
    return "neut"

def _chip_cc(v): return "up" if v>0 else ("dn" if v<0 else "")

def _con_txt(con_days):
    if con_days>=2:  return f"連買{con_days}日"
    if con_days==1:  return "今日買超"
    if con_days==0:  return "今日中性"
    if con_days>=-1: return "今日賣超"
    return f"連賣{abs(con_days)}日"

def _fv(v, unit="", dig=2):
    if v is None: return "N/A"
    return f"{v:,.{dig}f}{unit}"

def build_wiwynn_html(r):
    """生成完整 wiwynn 格式 HTML 報告（單一股票）。"""
    sid=r["sid"]; sname=r["name"]; rating=r["rating"]
    p=r["price"]; prev=r["prev"]; chg=r["chg"] or 0
    dev5=r.get("dev5") or 0; dev200=r.get("dev200") or 0
    sc=r["score"]; label=r["label"]
    f_con=r["f_con"]; t_con=r["t_con"]; d_con=r["d_con"]
    inst=r["inst"]; ma5=r["ma5"]; ma20=r["ma20"]
    tp=r["tp"]; ts_=r["ts"]
    pe=r["pe"]; pe_avg=r["pe_avg"]; pbr=r["pbr"]
    rev_yoy=r.get("rev_yoy"); rev_mom=r.get("rev_mom")

    rc=RC[rating]; lc=RL[rating]; sc2=RS[rating]
    vbg=VBG[rating]; vbc=VBC[rating]; vtc=VTC[rating]
    cc="up" if chg>=0 else "dn"
    bclr="#27ae60" if sc>=65 else ("#f39c12" if sc>=45 else "#e74c3c")

    # ── 標籤 ────────────────────────────────────────────────
    tags=""
    if r["is_disposed"]: tags+='<span class="tag tag-r">🚨 處置股</span>'
    if t_con>=5:   tags+=f'<span class="tag tag-g">投信連買{t_con}日 ⭐</span>'
    elif t_con>=1: tags+=f'<span class="tag tag-g">投信買超{t_con}日</span>'
    elif t_con<=-3:tags+=f'<span class="tag tag-r">投信連賣{abs(t_con)}日</span>'
    if f_con>=3:   tags+=f'<span class="tag tag-g">外資連買{f_con}日</span>'
    elif f_con<=-3:tags+=f'<span class="tag tag-r">外資連賣{abs(f_con)}日</span>'
    elif f_con<0:  tags+='<span class="tag tag-a">⚠ 外資今日賣超</span>'
    if dev5>8:     tags+=f'<span class="tag tag-r">⚠ 5日乖離{dev5:+.1f}%</span>'
    elif dev5<-5:  tags+=f'<span class="tag tag-g">5日回測{dev5:+.1f}%</span>'
    if tp and p:
        up2=(tp-p)/p*100
        if up2>10: tags+=f'<span class="tag tag-p">目標+{up2:.0f}%空間</span>'
    if rev_yoy and rev_yoy>20: tags+=f'<span class="tag tag-g">月營收YoY+{rev_yoy:.0f}%</span>'

    # ── 處置股警示 ───────────────────────────────────────────
    alert_html=""
    if r["is_disposed"]:
        alert_html="""
<div class="alert-timer">
  <div class="alert-icon">🚨</div>
  <div class="alert-text">
    <strong>處置股警告 — 流動性風險極高</strong>
    <span>目前每5~20分鐘才撮合一次，即便評分再高，<br>策略建議：暫不操作，靜待出關後再重新評估。</span>
  </div>
</div>"""

    # ── 決策評等卡片 ─────────────────────────────────────────
    pos_str = "、".join(r["pos"][:2]) if r["pos"] else ""
    neg_str = "、".join(r["neg"][:2]) if r["neg"] else ""
    upgrade_cond = f"外資轉買超連續2日 + 5日線乖離收斂至+3%以內"
    downgrade_cond= f"外資連賣超過3日，或跌破月線（{_fv(ma20,'元',0)}）收盤"
    if rating in ("S","A"):
        upgrade_cond = "三大法人持續同向買超，技術面維持強勢"
        downgrade_cond= f"外資轉賣超過3日，或月線（{_fv(ma20,'元',0)}）失守"

    verdict_card=f"""
<div class="card">
  <p class="card-title">📊 綜合決策評等（推薦分數 {sc}/100）</p>
  <div class="verdict" style="background:{vbg};border-color:{vbc}">
    <span class="verdict-big" style="color:{vbc}">{rating}</span>
    <span style="font-size:15px;font-weight:600;color:{vbc};margin-left:8px">{label}</span>
    <p style="margin-top:8px;font-size:13px;color:{vtc};line-height:1.7">
      {"<span class='up'>正面：</span>"+pos_str+"<br>" if pos_str else ""}
      {"<span class='dn'>負面：</span>"+neg_str if neg_str else ""}
    </p>
  </div>
  <div class="box-warn">
    ⚠ <strong>升降評觸發條件：</strong><br>
    升評：{upgrade_cond}<br>
    降評：{downgrade_cond}
  </div>
</div>"""

    # ── 技術面卡片 ───────────────────────────────────────────
    risk_label=("🟢 低度風險" if sc>=65 else "🟡 中度風險" if sc>=45 else "🔴 高度風險")
    # 近5日乖離趨勢條（從last5估算）
    last5=r.get("last5",[p])
    trend_rows=""
    for i,c in enumerate(last5):
        d5=round((c-ma5)/ma5*100,1) if ma5 and ma5>0 else 0
        w=min(abs(d5)*5,100)
        lbl2=f"T-{len(last5)-1-i}" if i<len(last5)-1 else "今日"
        fc="trend-bar-fill-g" if d5>=0 else "trend-bar-fill-r"
        vc="#27ae60" if d5>=0 else "#c0392b"
        trend_rows+=f"""
    <div class="trend-bar-row">
      <span class="trend-date">{lbl2}</span>
      <div class="trend-bar-bg"><div class="{fc}" style="width:{w}%"></div></div>
      <span style="font-size:11px;color:{vc};width:60px;text-align:right">{d5:+.1f}%</span>
    </div>"""

    tech_card=f"""
<div class="card">
  <p class="card-title">🔍 技術面 — 追高風險值 & 5日線乖離</p>
  <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;margin-bottom:12px">
    <div>
      <p style="font-size:36px;font-weight:700;color:{bclr};line-height:1">{sc}</p>
      <p style="font-size:11px;color:{bclr};font-weight:600">/ 100　{risk_label}</p>
    </div>
    <div style="flex:1;min-width:170px">
      <div class="row"><span class="row-l">今日收盤</span><span class="row-v">{p:,.2f} 元</span></div>
      <div class="row"><span class="row-l">5日均線</span><span class="row-v"><strong>{_fv(ma5,'元',2)}</strong></span></div>
      <div class="row"><span class="row-l">5日線乖離</span><span class="row-v {'up' if dev5<=3 else 'dn'}"><strong>{dev5:+.2f}%</strong></span></div>
      <div class="row"><span class="row-l">月線乖離</span><span class="row-v">{_fv(r.get('dev_ma20',dev(p,ma20)),'%',2,) if False else (f"{dev(p,ma20):+.2f}%" if ma20 and p else "N/A")}</span></div>
      <div class="row"><span class="row-l">年線乖離</span><span class="row-v {'dn' if dev200>80 else ''}">{f"{dev200:+.2f}%" if dev200 else "N/A"}</span></div>
      <div class="row"><span class="row-l">52週高/低</span><span class="row-v">{_fv(r.get('h52'),'',0)} / {_fv(r.get('l52'),'',0)} 元</span></div>
    </div>
  </div>
  <div style="background:#f8f9fa;border-radius:8px;padding:10px;border:1px solid #eee;margin-bottom:10px">
    <p style="font-size:10px;font-weight:600;color:#666;margin-bottom:8px;text-transform:uppercase">近5日 5日線乖離趨勢</p>
    {trend_rows}
  </div>
  <div class="risk-bar"><div class="risk-needle" style="left:{min(sc,99)}%"></div></div>
  <div class="risk-scale"><span>0 安全</span><span>50 中性</span><span>80 極危</span><span>100</span></div>
  <div class="rf-grid">
    <div class="rf"><p>MA20 月線</p><p>{_fv(ma20,'元',0)}</p></div>
    <div class="rf"><p>MA60 季線</p><p>{_fv(r.get('ma60'),'元',0)}</p></div>
    <div class="rf"><p>MA200 年線</p><p>{_fv(r.get('ma200'),'元',0)}</p></div>
    <div class="rf"><p>52週高點</p><p class="dn">{_fv(r.get('h52'),'元',0)}</p></div>
    <div class="rf"><p>52週低點</p><p class="up">{_fv(r.get('l52'),'元',0)}</p></div>
    <div class="rf"><p>成交量</p><p>{f"{r.get('vol',0):,} 張"}</p></div>
  </div>
</div>"""

    # ── 籌碼面卡片 ───────────────────────────────────────────
    ft=inst[-1]["f"] if inst else 0
    tt2=inst[-1]["t"] if inst else 0
    dt=inst[-1]["d"] if inst else 0
    tot=ft+tt2+dt
    prev_ft=inst[-2]["f"] if len(inst)>=2 else 0
    prev_tt=inst[-2]["t"] if len(inst)>=2 else 0
    prev_dt=inst[-2]["d"] if len(inst)>=2 else 0
    max_abs=max(abs(ft),abs(tt2),abs(prev_ft),abs(prev_tt),1)

    def tbar(label,curr,pv):
        w=min(abs(curr)/max_abs*100,100)
        c="#27ae60" if curr>=0 else "#c0392b"
        fc2="trend-bar-fill-g" if curr>=0 else "trend-bar-fill-r"
        return (f'<div class="trend-bar-row">'
                f'<span style="font-size:10px;color:#777;width:38px">{label}</span>'
                f'<div class="trend-bar-bg"><div style="height:5px;border-radius:3px;background:{c};width:{w}%"></div></div>'
                f'<span style="font-size:10px;color:{c};width:80px;text-align:right">{pv:+,}→{curr:+,}張</span></div>')

    # 5日明細表格
    inst_tbl_rows=""
    for d in inst:
        raw=d.get("date",""); 
        try: ds=datetime.strptime(raw,"%Y-%m-%d").strftime("%m/%d")
        except: ds=raw[-5:]
        fv2=d["f"]; tv=d["t"]; dv=d["d"]; to=fv2+tv+dv
        fc3="up" if fv2>=0 else "dn"; tc3="up" if tv>=0 else "dn"
        dc3="up" if dv>=0 else "dn"; toc="up" if to>=0 else "dn"
        inst_tbl_rows+=f"""
<tr>
  <td>{ds}</td>
  <td class="{fc3}">{fv2:+,}</td>
  <td class="{tc3}">{tv:+,}</td>
  <td class="{dc3}">{dv:+,}</td>
  <td class="{toc}"><strong>{to:+,}</strong></td>
</tr>"""

    chip_comment=""
    if ft>0 and tt2>0:   chip_comment="✅ 外資投信同向買超，無對作"
    elif ft<0 and tt2<0: chip_comment="✗ 外資投信同向賣超，籌碼惡化"
    elif (ft>0 and tt2<0) or (ft<0 and tt2>0): chip_comment="⚠ 外資投信方向分歧，對作中"

    chip_card=f"""
<div class="card">
  <p class="card-title">💼 籌碼面 — 三大法人動向</p>
  <div class="chip-grid">
    <div class="chip {_chip_cls(ft)}">
      <p>外資</p>
      <p class="{_chip_cc(ft)}">{("+" if ft>=0 else "")}{ft:,} 張</p>
      <p>{_con_txt(f_con)}</p>
    </div>
    <div class="chip {_chip_cls(tt2)}">
      <p>投信</p>
      <p class="{_chip_cc(tt2)}">{("+" if tt2>=0 else "")}{tt2:,} 張</p>
      <p>{_con_txt(t_con)}</p>
    </div>
    <div class="chip {_chip_cls(dt)}">
      <p>自營商</p>
      <p class="{_chip_cc(dt)}">{("+" if dt>=0 else "")}{dt:,} 張</p>
      <p>{_con_txt(d_con)}</p>
    </div>
  </div>
  <div class="trend-compare">
    <div class="trend-cell">
      <p class="trend-cell-title">📅 昨今比對（張）</p>
      {tbar("外資",ft,prev_ft)}
      {tbar("投信",tt2,prev_tt)}
      {tbar("自營",dt,prev_dt)}
    </div>
    <div class="trend-cell">
      <p class="trend-cell-title">📊 今日解讀</p>
      <p style="font-size:11px;color:#555;line-height:1.7">{chip_comment}<br>
      三大合計：<strong class="{'up' if tot>=0 else 'dn'}">{tot:+,} 張</strong></p>
    </div>
  </div>
  {"<div class='box-ok'>✅ "+"、".join(r['pos'][:1])+"</div>" if r["pos"] else ""}
  {"<div class='box-warn'>⚠ "+"、".join(r['warn'][:1])+"</div>" if r["warn"] else ""}
  {"<div class='box-danger'>✗ "+"、".join(r['neg'][:1])+"</div>" if r["neg"] else ""}
  <div style="margin-top:10px">
    <p style="font-size:10px;font-weight:600;color:#666;margin-bottom:6px;text-transform:uppercase">近5日明細（張）</p>
    <table class="inst-tbl">
      <tr><th>日期</th><th>外資</th><th>投信</th><th>自營</th><th>合計</th></tr>
      {inst_tbl_rows}
    </table>
  </div>
</div>"""

    # ── 目標價卡片 ───────────────────────────────────────────
    tp_card=""
    if tp and p:
        up2=(tp-p)/p*100
        exceed=up2<0
        bw=min(p/tp*100,100) if tp>0 else 50
        fill_c=("linear-gradient(90deg,#27ae60,#e74c3c)" if exceed
                else "linear-gradient(90deg,#27ae60,#2ecc71)")
        upbox=(f'<div class="box-danger" style="margin-top:8px">✗ 現價已超越目標{abs(up2):.1f}%，短線追高安全邊際低。</div>'
               if exceed else
               f'<div class="box-ok" style="margin-top:8px">✅ 距目標+{up2:.1f}%，具合理風險報酬比。</div>')
        tp_card=f"""
<div class="card">
  <p class="card-title">💰 目標價分析（{ts_}）</p>
  <div class="row"><span class="row-l">目標價</span><span class="row-v {'dn' if exceed else 'up'}">{tp:,.0f} 元</span></div>
  <div class="row"><span class="row-l">現價</span><span class="row-v">{p:,.0f} 元</span></div>
  <div class="row"><span class="row-l">空間</span><span class="row-v {'dn' if exceed else 'up'}">{up2:+.1f}%</span></div>
  {"<div class='row'><span class='row-l'>PE 均值</span><span class='row-v'>"+str(pe_avg)+"x</span></div>" if pe_avg else ""}
  {"<div class='row'><span class='row-l'>月營收YoY</span><span class='row-v "+(  "up" if (rev_yoy or 0)>=0 else "dn")+"'>"+f"{rev_yoy:+.1f}%</span></div>" if rev_yoy is not None else ""}
  <div class="tp-bar-wrap">
    <div class="tp-bar-fill" style="width:{bw:.1f}%;background:{fill_c}"></div>
  </div>
  <div class="tp-labels">
    <span>0</span>
    <span>現價{p:,.0f}（{bw:.0f}%）</span>
    <span>目標{tp:,.0f}</span>
  </div>
  {upbox}
</div>"""

    # ── 估值卡片 ─────────────────────────────────────────────
    val_card=""
    if pe or pbr:
        pe_vs=(round((pe-pe_avg)/pe_avg*100,1) if pe and pe_avg and pe_avg>0 else None)
        pc="#27ae60" if (pe_vs or 0)<0 else ("#e67e22" if (pe_vs or 0)<20 else "#c0392b")
        mom_cell=(f"<div class='rf'><p>月營收MoM</p><p class='{'up' if (rev_mom or 0)>=0 else 'dn'}'>{rev_mom:+.1f}%</p></div>"
              if rev_mom is not None else "")
    yoy_cell=(f"<div class='rf'><p>月營收YoY</p><p class='{'up' if (rev_yoy or 0)>=0 else 'dn'}'>{rev_yoy:+.1f}%</p></div>"
              if rev_yoy is not None else "")
    pe_cell  =f"<div class='rf'><p>本益比 PE</p><p style='color:{pc}'>{pe}x</p></div>" if pe else ""
    pavg_cell=f"<div class='rf'><p>近一年均PE</p><p>{pe_avg}x</p></div>" if pe_avg else ""
    pbr_cell =f"<div class='rf'><p>淨值比 PBR</p><p>{pbr}x</p></div>" if pbr else ""
    pvs_cell =(f"<div class='rf'><p>PE vs 均值</p><p style='color:{pc}'>{pe_vs:+.1f}%</p></div>"
               if pe_vs is not None else "")
    val_card=f"""
<div class="card">
  <p class="card-title">📊 估值指標</p>
  <div class="rf-grid">
    {pe_cell}{pavg_cell}{pbr_cell}{pvs_cell}{mom_cell}{yoy_cell}
  </div>
</div>"""

    # ── 事件更新（自動生成）────────────────────────────────────
    events=[]
    if f_con>=3 and t_con>=3:
        events.append(("#27ae60",f"外資+投信雙向認養（{f_con}/{t_con}日）",
                       "法人籌碼同向為近期最強正面訊號，中線看多確立，可積極布局。"))
    elif f_con>=2:
        events.append(("#27ae60",f"外資連買{f_con}日",
                       "外資持續買超，籌碼支撐明確，法人對後市持正向看法。"))
    elif f_con<=-3:
        events.append(("#e74c3c",f"外資連賣{abs(f_con)}日",
                       "外資持續調節，短線籌碼承壓，需觀察是否出現止賣跡象。"))
    if t_con>=5:
        events.append(("#27ae60",f"投信深度認養（連買{t_con}日）",
                       "投信長時間持續買超為強力護盤訊號，顯示機構對該股中線信心。"))
    elif t_con<=-3:
        events.append(("#e74c3c",f"投信連賣{abs(t_con)}日",
                       "投信持續調節，機構對該股看法偏謹慎，需密切追蹤。"))
    if dev5<-5:
        events.append(("#27ae60","股價回測5日線，形成良好進場點",
                       f"5日線乖離{dev5:+.1f}%，進入合理回測區，為技術面偏多進場訊號。"))
    elif dev5>10:
        events.append(("#e74c3c","5日線乖離過高，短線追高風險大",
                       f"乖離+{dev5:.1f}%，建議等待回測均線後再進場，現價追入性價比低。"))
    if rev_yoy and rev_yoy>20:
        events.append(("#27ae60",f"月營收 YoY+{rev_yoy:.1f}%，基本面動能強勁",
                       "年增率超過20%代表業績成長加速，基本面為股價提供長線支撐。"))
    if r["is_disposed"]:
        events.append(("#e74c3c","⚠ 處置股警告",
                       "處置期間流動性極差，每5~20分鐘才撮合。即便評分高，策略建議暫不操作，靜待出關。"))
    if not events:
        events.append(("#8fa3b8","目前無特殊事件觀察",
                       "維持現有追蹤，依三大法人動向調整持倉比例。"))
    ev_html="".join(
        f'<div class="ev"><div class="ev-dot" style="background:{c}"></div>'
        f'<div><strong>{t}</strong><span>{d2}</span></div></div>'
        for c,t,d2 in events[:4])

    events_card=f"""
<div class="card">
  <p class="card-title">📅 事件更新</p>
  {ev_html}
</div>"""

    # ── 操作策略 ─────────────────────────────────────────────
    last5v=r.get("last5",[p])
    stop=round(min(last5v)*0.97,2) if last5v else round(p*0.95,2)
    if dev5<-3:
        entry_a=f"{p:,.0f}元（現位即回測進場）"
        entry_b=f"{(ma20 or p*0.9):,.0f}元（月線支撐更保守）"
    elif dev5<=3:
        entry_a=f"{(ma5 or p)*0.97:,.0f}元（回測5日線）"
        entry_b=f"{(ma20 or p*0.93):,.0f}元（回測月線）"
    else:
        entry_a=f"{(ma5 or p)*0.95:,.0f}元（等待回測5日線{_fv(ma5,'元',0)}）"
        entry_b=f"{(ma20 or p*0.9):,.0f}元（月線更安全）"
    tgt_s=f"{tp:,.0f}元（{ts_}）" if tp else f"{p*1.10:,.0f}元（技術估算+10%）"
    tgt_l=f"{tp*1.15:,.0f}元（樂觀目標）" if tp else f"{p*1.20:,.0f}元（+20%估算）"
    bull_tgt=f"目標{tp:,.0f}元" if tp else f"{p*1.12:,.0f}元（+12%）"
    bear_tgt=f"月線{_fv(ma20,'元',0)}" if ma20 else "關鍵支撐失守"

    strat_card=f"""
<div class="card">
  <p class="card-title">🎯 操作策略</p>
  <div class="strat"><span class="strat-icon">🟢</span><div><strong>建議進場點（保守型）：</strong>{entry_b}</div></div>
  <div class="strat"><span class="strat-icon">🟡</span><div><strong>建議進場點（積極型）：</strong>{entry_a}</div></div>
  <div class="strat"><span class="strat-icon">🔴</span><div><strong>短線停損點：</strong>{stop:,.0f} 元（近5日低點 -3%）</div></div>
  <div class="strat"><span class="strat-icon">🎯</span><div><strong>短線目標：</strong>{tgt_s}</div></div>
  <div class="strat"><span class="strat-icon">🏁</span><div><strong>中長線目標：</strong>{tgt_l}</div></div>
  <div class="sc-grid">
    <div class="sc-bull"><strong>📈 多頭情境</strong><br>法人持續買超 + 技術面強勢 → {bull_tgt}，可升評</div>
    <div class="sc-bear"><strong>📉 空頭情境</strong><br>外資轉向賣超 + 跌破支撐 → {bear_tgt}，考慮降評</div>
  </div>
</div>"""

    # ── 風險提示 ─────────────────────────────────────────────
    risks=""
    if r["is_disposed"]:
        risks+=f'<div class="box-danger">🚨 <strong>處置股：</strong>流動性極差，處置期策略建議暫不操作。</div>'
    for n in r["neg"][:3]:
        risks+=f'<div class="box-danger">✗ <strong>{n}</strong></div>'
    for w in r["warn"][:2]:
        risks+=f'<div class="box-warn">⚠ {w}</div>'
    if not risks:
        risks='<div class="box-ok">✅ 目前無重大風險警示，維持當前評等。</div>'

    risk_card=f"""
<div class="card">
  <p class="card-title">⚠️ 風險提示</p>
  {risks}
</div>"""

    # ── 組合完整 HTML ─────────────────────────────────────────
    chg_sign="+" if chg>=0 else ""
    today=date.today().strftime("%Y/%m/%d")

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{sname} {sid} 分析報告</title>
<style>{WIWYNN_CSS}</style>
</head>
<body>
<div class="wrap">

<div class="hdr">
  <div class="hdr-top">
    <div>
      <h1>{sname} <span style="font-size:14px;font-weight:400;color:#8fa3b8">{sid}</span></h1>
      <p class="hdr-sub">台股　|　{today} 分析　|　收盤 {p:,.2f} 元　|　5日乖離 {dev5:+.1f}%</p>
      <div class="tags">{tags}</div>
    </div>
    <div class="rating-circle" style="background:{rc}">
      <span class="letter" style="color:{lc}">{rating}</span>
      <span class="lbl" style="color:{sc2}">{label}</span>
    </div>
  </div>
</div>

<div class="sum-bar" style="border-left-color:{rc}">
  <div class="sum-cell"><p>昨日收盤</p><p>{prev:,.2f} 元</p></div>
  <div class="sum-cell"><p>今日收盤</p><p class="{cc}">{p:,.2f} 元</p></div>
  <div class="sum-cell"><p>今日漲跌</p><p class="{cc}">{chg_sign}{chg:.2f}%</p></div>
  <div class="sum-cell"><p>5日均線</p><p>{_fv(ma5,'元',2)}</p></div>
</div>

{alert_html}
{verdict_card}
{tech_card}
{chip_card}
{tp_card}
{val_card}
{events_card}
{strat_card}
{risk_card}

<div class="footer">
  {sname}（{sid}）　|　{today}　|　評分 {sc}/100　|　目標價：{f"{tp:,.0f}元（{ts_}）" if tp else "未取得"}<br>
  數據來源：FinMind API　|　僅供參考，不構成投資建議。
</div>

</div>
</body>
</html>"""

def build_full_report_html(results):
    """生成完整多股票報告 HTML（導覽列 + 所有卡片）。"""
    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    nav="".join(
        f'<a href="#s{r["sid"]}" style="display:inline-block;font-size:11px;'
        f'padding:3px 9px;border-radius:16px;font-weight:600;text-decoration:none;margin:2px;'
        f'background:{RC[r["rating"]]};color:white">{r["name"]}</a>'
        for r in sorted(results,key=lambda x:x["score"],reverse=True))
    cards=""
    for r in sorted(results,key=lambda x:(x["is_disposed"],-x["score"])):
        inner=build_wiwynn_html(r)
        # 取 body 內容
        start=inner.find("<body>")+6; end=inner.find("</body>")
        body_content=inner[start:end]
        cards+=f'<div id="s{r["sid"]}" style="scroll-margin-top:60px">{body_content}</div>'
    today=date.today().strftime("%Y/%m/%d %H:%M")
    return f"""<!DOCTYPE html><html lang="zh-TW"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股分析報告 {today}</title><style>{WIWYNN_CSS}</style></head>
<body>
<div class="wrap">
<div style="background:#1a2332;border-radius:10px;padding:10px 14px;margin-bottom:12px;
  position:sticky;top:0;z-index:99">
  <div style="font-size:10px;color:#8fa3b8;margin-bottom:5px">
    📊 台股分析 {today}　S:{cnts['S']} A:{cnts['A']} B:{cnts['B']} C:{cnts['C']}
  </div>
  {nav}
</div>
{cards}
</div></body></html>"""

# ================================================================
# 頁面
# ================================================================
def tab_home():
    results=st.session_state.results
    token=st.session_state.token
    sids=[s.strip() for s in st.session_state.stock_list.split(",") if s.strip()]

    # 標題
    st.markdown("""
<div style="background:linear-gradient(135deg,#1a2332,#2c3e50);border-radius:14px;
  padding:16px 20px;margin-bottom:12px">
  <div style="font-size:20px;font-weight:800;color:#fff">📊 台股分析系統</div>
  <div style="font-size:11px;color:#8fa3b8;margin-top:3px">wiwynn 格式完整報告</div>
</div>""", unsafe_allow_html=True)

    if token:
        lr=st.session_state.last_run
        st.success(f"✅ Token 已設定 | 上次：{lr.strftime('%m/%d %H:%M') if lr else '尚未執行'} | {len(sids)}支")
    else:
        st.error("⚠️ 請到「⚙️ 設定」填入 FinMind Token")

    run=st.button("🔄 開始分析全部股票",disabled=not token,use_container_width=True)

    if run:
        errors=[]
        with st.spinner("取得處置股清單..."):
            st.session_state.disposed=get_disposed()
        all_res=[]; bar=st.progress(0,"準備中...")
        for i,sid in enumerate(sids):
            bar.progress((i+1)/len(sids),text=f"分析 {nm(sid)}（{i+1}/{len(sids)}）")
            r,err=analyze(sid,token,st.session_state.disposed)
            if r: all_res.append(r)
            else: errors.append(f"{sid}：{err}")
        bar.empty()
        if all_res:
            st.session_state.results=sorted(all_res,key=lambda x:x["score"],reverse=True)
            st.session_state.last_run=datetime.now()
            st.success(f"✅ 完成！{len(all_res)} 支股票")
        else:
            st.error("❌ 分析失敗，請確認 Token 是否正確")
        if errors:
            with st.expander(f"⚠️ {len(errors)} 支失敗"):
                for e in errors: st.write(e)
        st.rerun()

    if not results:
        st.info("👆 點「開始分析全部股票」按鈕")
        return

    # ── 評等統計 ────────────────────────────────────────────
    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    c1,c2,c3,c4=st.columns(4)
    for col,(rt,em,bg) in zip([c1,c2,c3,c4],[
        ("S","⭐","#d4edda"),("A","✅","#d4edda"),("B","👀","#fff3cd"),("C","❌","#f8d7da")
    ]):
        col.markdown(
            f'<div style="background:{bg};border-radius:9px;padding:9px;text-align:center">'
            f'<div style="font-size:17px">{em}</div>'
            f'<div style="font-size:20px;font-weight:800;color:{RC[rt]}">{cnts.get(rt,0)}</div>'
            f'<div style="font-size:10px;color:#555">{rt}</div></div>',
            unsafe_allow_html=True)

    st.markdown("---")

    # ── 全部報告下載 ────────────────────────────────────────
    full_html=build_full_report_html(results)
    dt=date.today().strftime("%Y%m%d")
    st.download_button(
        "📥 下載完整 HTML 報告（wiwynn 格式）",
        full_html,
        f"portfolio_{len(results)}stocks_{dt}.html",
        "text/html",
        use_container_width=True
    )

    st.markdown("---")

    # ── 選擇股票查看完整報告 ─────────────────────────────────
    sorted_r=sorted(results,key=lambda x:x["score"],reverse=True)
    opts=[f"{r['rating']} {r['name']}（{r['sid']}）— {r['score']}分 | {r['price']:,.0f}元 {r['chg']:+.1f}%"
          for r in sorted_r]
    sel=st.selectbox("🔍 選擇股票查看完整分析報告",range(len(opts)),
                     format_func=lambda i:opts[i])

    r_sel=sorted_r[sel]
    html=build_wiwynn_html(r_sel)

    # 個股下載
    st.download_button(
        f"📄 下載 {r_sel['name']} 個股報告",
        html,
        f"{r_sel['sid']}_{dt}.html",
        "text/html"
    )

    # wiwynn 格式報告嵌入顯示
    components.html(html, height=2600, scrolling=True)

def tab_rank():
    st.markdown("### 🏆 今日評等排行")
    results=st.session_state.results
    if not results: st.info("請先在「🏠 首頁」執行分析"); return
    df=pd.DataFrame([{
        "評等":r["rating"],"股票":f"{r['name']}({r['sid']})",
        "分數":r["score"],"現價":r["price"],
        "漲跌%":f"{r['chg']:+.2f}%","外資":f"{r['f_con']:+d}日","投信":f"{r['t_con']:+d}日",
        "目標":f"{r['tp']:,.0f}" if r["tp"] else "-"
    } for r in results])
    st.dataframe(df,use_container_width=True,hide_index=True)
    buy2=[r for r in results if r["f_con"]>0 and r["t_con"]>0 and not r["is_disposed"]]
    if buy2:
        st.markdown("### ✅ 外資+投信同向買超")
        for r in sorted(buy2,key=lambda x:x["f_con"]+x["t_con"],reverse=True):
            chg=r["chg"] or 0; cc2="#27ae60" if chg>=0 else "#c0392b"
            st.markdown(
                f'<div style="background:#fff;border-left:4px solid #27ae60;border-radius:8px;'
                f'padding:9px 13px;margin:5px 0;border:1px solid #c3e6cb">'
                f'<strong style="color:#1a2332">{r["name"]}（{r["sid"]}）</strong> '
                f'<span style="color:{cc2}">{r["price"]:,.0f}元 {chg:+.1f}%</span> '
                f'外資<span style="color:#27ae60;font-weight:700">+{r["f_con"]}日</span> '
                f'投信<span style="color:#27ae60;font-weight:700">+{r["t_con"]}日</span></div>',
                unsafe_allow_html=True)

def tab_scanner():
    st.markdown("### 📡 籌碼掃描")
    results=st.session_state.results
    if not results: st.info("請先在「🏠 首頁」執行分析"); return
    st.markdown("#### 🔥 法人焦點熱門股（吸籌率≥5%）")
    hot=[]
    for r in results:
        if r["is_disposed"] or not r["inst"]: continue
        ft=r["inst"][-1]["f"]; tt=r["inst"][-1]["t"]; vol=r.get("vol",0) or 1
        if ft>0 and tt>0 and (ft+tt)/vol*100>=5:
            hot.append({**r,"ab":round((ft+tt)/vol*100,1),"ft":ft,"tt":tt})
    hot.sort(key=lambda x:x["ab"],reverse=True)
    if hot:
        for r in hot[:10]:
            tier="🔴極熱" if r["ab"]>=15 else "🟠熱門" if r["ab"]>=8 else "🟡升溫"
            chg=r["chg"] or 0; cc2="#27ae60" if chg>=0 else "#c0392b"
            st.markdown(
                f'<div style="background:#fff;border-left:4px solid #27ae60;border-radius:8px;'
                f'padding:9px 13px;margin:5px 0;border:1px solid #c3e6cb">'
                f'<div style="display:flex;justify-content:space-between">'
                f'<strong style="color:#1a2332">{r["name"]}（{r["sid"]}）</strong>'
                f'<span style="color:#e67e22;font-weight:700">{tier} {r["ab"]}%</span></div>'
                f'<span style="font-size:13px;color:#1a1a2e">{r["price"]:,.0f}元 '
                f'<span style="color:{cc2}">{chg:+.1f}%</span> '
                f'外資<span style="color:#27ae60">+{r["ft"]:,}</span>張 '
                f'投信<span style="color:#27ae60">+{r["tt"]:,}</span>張</span></div>',
                unsafe_allow_html=True)
    else: st.info("今日無外資+投信同向且吸籌率≥5%個股")

def tab_settings():
    st.markdown("### ⚙️ 設定")
    with st.form("sf",clear_on_submit=False):
        st.markdown("**🔑 FinMind Token**")
        token=st.text_input("Token",value=st.session_state.token,type="password",
                             placeholder="貼上 FinMind Token...",label_visibility="collapsed")
        st.markdown("**📋 追蹤股票（逗號分隔，建議≤15支）**")
        sl=st.text_area("stocks",value=st.session_state.stock_list,height=80,label_visibility="collapsed")
        ok=st.form_submit_button("💾 儲存設定",use_container_width=True)
    if ok:
        st.session_state.token=token.strip()
        st.session_state.stock_list=sl.strip()
        st.success("✅ 儲存完成！請到「🏠 首頁」開始分析。")
    st.markdown("---")
    st.markdown("""
**📌 取得 FinMind Token（免費）**
1. 前往 [finmindtrade.com](https://finmindtrade.com)
2. 免費註冊，登入後在帳號頁取得 Token

**📱 加入 iPhone 主畫面**
Safari 開啟 → 分享📤 → 加入主畫面 → 新增
""")
    if st.session_state.token:
        st.success(f"✅ Token已設定（前8碼：{st.session_state.token[:8]}...）")
    else:
        st.warning("⚠️ 尚未設定Token")

def main():
    t1,t2,t3,t4=st.tabs(["🏠 首頁","🏆 排行","📡 掃描","⚙️ 設定"])
    with t1: tab_home()
    with t2: tab_rank()
    with t3: tab_scanner()
    with t4: tab_settings()

if __name__=="__main__": main()
