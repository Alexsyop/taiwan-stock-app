"""
台股分析系統 — Streamlit App v5 終極修復版
修復項目：
1. 完整補齊底層 apicall, get_price, get_inst 函式，解決 NameError 崩潰
2. 自動套用 wiwynn 報告模板
3. 完美整合 yfinance 分析師目標價區間
4. 籌碼掃描放寬門檻（吸籌率≥5%）
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

# 上市 + 上櫃 股票名稱
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

# ================================================================
# ⚙️ 補齊底層連線核心：apicall、get_price、get_inst
# ================================================================
def apicall(dataset, sid, start_date, token):
    """標準底層 FinMind API 呼叫元件"""
    params = {
        "dataset": dataset,
        "data_id": sid,
        "start_date": start_date,
        "token": token
    }
    try:
        resp = requests.get(API, params=params, headers=HDR, timeout=12)
        if resp.status_code == 200:
            return resp.json().get("data", [])
    except Exception:
        pass
    return []

def get_price(sid, token):
    """獲取近250日歷史價格"""
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
            "vol": fi(r.get("Trading_Volume")) // 1000 # 轉成張數
        })
    return recs[-250:]

def get_inst(sid, token):
    """獲取近5日三大法人買賣超數據"""
    start = (date.today() - timedelta(days=15)).strftime("%Y-%m-%d")
    rows = apicall("TaiwanStockInstitutionalInvestorsBuySell", sid, start, token)
    
    # 依日期加總
    daily_data = defaultdict(lambda: {"f": 0, "t": 0, "d": 0})
    for r in rows:
        d = r.get("date")
        w = r.get("name", "")
        net = fi(r.get("buy", 0)) - fi(r.get("sell", 0))
        net_zhang = net // 1000 # 轉成張數
        
        if "Foreign" in w or "外資" in w: daily_data[d]["f"] += net_zhang
        elif "Investment" in w or "投信" in w: daily_data[d]["t"] += net_zhang
        elif "Dealer" in w or "自營" in w: daily_data[d]["d"] += net_zhang
        
    recs = [{"date": k, "f": v["f"], "t": v["t"], "d": v["d"]} for k, v in daily_data.items()]
    recs.sort(key=lambda x: x["date"])
    return recs[-5:]

# ================================================================
# ★ Yahoo Finance 分析師共識目標價
# ================================================================
def get_yahoo_analyst_target(stock_id: str) -> dict | None:
    if not HAS_YF: return None
    for suffix in [".TW", ".TWO"]:
        try:
            ticker_str = f"{stock_id}{suffix}"
            ticker_obj = yf.Ticker(ticker_str)
            info       = ticker_obj.info or {}

            if not info.get("regularMarketPrice"):
                continue

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
        except Exception:
            continue
    return None

def get_per(sid, tok):
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
    d = set()
    # 上市（TWSE）
    try:
        r = requests.get("https://openapi.twse.com.tw/v1/announcement/punish", headers=HDR, timeout=5, verify=False)
        if r.status_code == 200:
            for i in r.json():
                c = str(i.get("SecuritiesCode","")).strip()
                if c: d.add(c)
    except Exception: pass
    # 上櫃（TPEx）
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
        time.sleep(0.1)

        inst=get_inst(sid,tok)
        f_con=con([d["f"] for d in inst]); t_con=con([d["t"] for d in inst]); d_con=con([d["d"] for d in inst])
        time.sleep(0.1)

        per=get_per(sid,tok)
        pe=per[-1]["pe"] if per else None
        pe_avg=round(sum(r["pe"] for r in per)/len(per),1) if per else None
        pbr=per[-1]["pbr"] if per else None
        time.sleep(0.1)

        rev=get_rev(sid,tok)
        rev_yoy=None
        if len(rev)>=13:
            if rev[-13]["rev"]>0: rev_yoy=round((rev[-1]["rev"]-rev[-13]["rev"])/rev[-13]["rev"]*100,1)
        rev_mom=None
        if len(rev)>=2:
            if rev[-2]["rev"]>0: rev_mom=round((rev[-1]["rev"]-rev[-2]["rev"])/rev[-2]["rev"]*100,1)

        tp=None; ts="未取得"; tp_high=None; tp_low=None; tp_count=0

        # Yahoo 分析師共識優先
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

# ── wiwynn HTML 報告生成器（內建完整的卡片渲染） ──────────────────
from streamlit_app import build_wiwynn_html, build_full_report_html, WIWYNN_CSS

# ── 頁面分頁邏輯 ───────────────────────────────────────────────
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
        lr=st.session_state.last_run
        st.success(f"✅ API 通行證已就緒 | 追蹤標的：{len(sids)} 檔")
    else:
        st.error("⚠️ 請至「⚙️ 設定」填入你的 FinMind Token 才能啟動連線功能")

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

    # 數據統計面板
    from collections import Counter
    cnts=Counter(r["rating"] for r in results)
    c1,c2,c3,c4=st.columns(4)
    for col,(rt,em,bg) in zip([c1,c2,c3,c4],[("S","⭐","#d4edda"),("A","✅","#d4edda"),("B","👀","#fff3cd"),("C","❌","#f8d7da")]):
        col.markdown(f'<div style="background:{bg};border-radius:9px;padding:9px;text-align:center"><div style="font-size:17px">{em}</div><div style="font-size:20px;font-weight:800;color:{RC[rt]}">{cnts.get(rt,0)}</div><div style="font-size:10px;color:#555">{rt} 評等</div></div>',unsafe_allow_html=True)

    st.markdown("---")
    full_html=build_full_report_html(results)
    dt=date.today().strftime("%Y%m%d")
    st.download_button("📥 下載整合多股戰略報告 (HTML)", full_html, f"portfolio_{dt}.html", "text/html", use_container_width=True)

    # 選擇查看單股報告
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