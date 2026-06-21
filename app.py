#!/usr/bin/env python3
"""
美股監控 Web UI — Flask 後端（per-IP 使用者配置）
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from functools import wraps

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from authlib.integrations.flask_client import OAuth

try:
    import yfinance as yf
except ImportError:
    print("請先安裝: pip install yfinance flask")
    raise

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
oauth = OAuth(app)
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    client_kwargs={"scope": "openid email profile"},
)

# simple in-memory cache keyed by request path + query
_cache = {}
def cached(ttl_sec):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            key = request.path + "?" + request.query_string.decode("utf-8") if request.query_string else request.path
            now = datetime.now()
            if key in _cache and (now - _cache[key]["ts"]).total_seconds() < ttl_sec:
                return _cache[key]["data"]
            data = f(*a, **kw)
            _cache[key] = {"data": data, "ts": now}
            return data
        return wrapper
    return deco

ALERTS_FILE = "alerts.json"
CONFIG_FILE = "user_configs.json"

DEFAULT_SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "TSLA", "META", "AMD"
]

TW_DEFAULT_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2412",
    "2881", "2303", "2382", "2357", "3711"
]

TW_NAMES = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2308": "台達電", "2412": "中華電",
    "2881": "富邦金", "2882": "國泰金", "2303": "聯電", "2382": "廣達", "2357": "華碩",
    "3231": "緯創", "3711": "日月光", "2002": "中鋼", "1301": "台塑", "1326": "台化",
    "1216": "統一", "2353": "宏碁", "2376": "技嘉", "3037": "欣興", "3034": "聯詠",
    "2498": "宏達電", "3008": "大立光", "4904": "遠傳", "2886": "兆豐金", "2891": "中信金",
    "2885": "元大金", "2603": "長榮", "2618": "長榮航", "3443": "創意", "5269": "祥碩",
    "6669": "緯穎", "2301": "光寶科", "2345": "智邦", "2356": "英業達",
    "2409": "友達", "2449": "京元電子", "2451": "創見", "2542": "興富發",
}

DEFAULT_CONFIG = {
    "watchlist_us": DEFAULT_SYMBOLS,
    "watchlist_tw": TW_DEFAULT_SYMBOLS,
    "sidebar_width": 340,
    "refresh_interval": 30000,
    "chart_period": "1d",
    "chart_interval": "1m",
}


def get_client_ip():
    google_sub = session.get("user_sub")
    if google_sub:
        return "google_" + google_sub
    cid = request.headers.get("X-Client-Id")
    if cid:
        return cid
    if request.headers.get("X-Forwarded-For"):
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


# ── User Config ────────────────────────────────────────

def load_all_configs():
    if not Path(CONFIG_FILE).exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_all_configs(configs):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)


def get_user_config(market="us"):
    ip = get_client_ip()
    configs = load_all_configs()
    cfg = configs.get(ip, {})
    merged = {**DEFAULT_CONFIG, **cfg}
    wl_key = "watchlist_us" if market == "us" else "watchlist_tw"
    dflt = DEFAULT_SYMBOLS if market == "us" else TW_DEFAULT_SYMBOLS
    merged[wl_key] = list(dict.fromkeys(
        [s.upper() for s in merged.get(wl_key, dflt)]
    ))
    return merged, configs, ip, wl_key


def save_user_config(updates, market="us"):
    cfg, configs, ip, _ = get_user_config(market)
    cfg.update(updates)
    configs[ip] = cfg
    save_all_configs(configs)
    return cfg


# ── Alerts (global) ────────────────────────────────────

def load_alerts():
    if not Path(ALERTS_FILE).exists():
        return []
    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_alerts(alerts):
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


# ── utils ───────────────────────────────────────────────

def fmt_market_cap(v):
    if not v:
        return "N/A"
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    return f"${v:,.0f}"


def fmt_volume(v):
    if not v:
        return "N/A"
    if v >= 1e9:
        return f"{v/1e9:.2f}B"
    if v >= 1e6:
        return f"{v/1e6:.2f}M"
    if v >= 1e3:
        return f"{v/1e3:.1f}K"
    return str(int(v))


# ── Auth Routes ─────────────────────────────────────────

@app.route("/auth/login")
def auth_login():
    redirect_uri = url_for("auth_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route("/auth/callback")
def auth_callback():
    token = oauth.google.authorize_access_token()
    user = token.get("userinfo") or oauth.google.parse_id_token(token)
    session["user_sub"] = user["sub"]
    session["user_name"] = user.get("name", "")
    session["user_email"] = user.get("email", "")
    return redirect(url_for("index"))

@app.route("/auth/logout")
def auth_logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/api/me")
def api_me():
    return jsonify({
        "logged_in": "user_sub" in session,
        "name": session.get("user_name", ""),
        "email": session.get("user_email", ""),
    })

@app.route("/api/admin/users")
def api_admin_users():
    configs = load_all_configs()
    logged_in = [k for k in configs if k.startswith("google_")]
    return jsonify({
        "total_configs": len(configs),
        "logged_in_users": len(logged_in),
    })


# ── Routes ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── User Config API ─────────────────────────────────────

@app.route("/api/user-config", methods=["GET"])
def api_get_config():
    market = request.args.get("market", "us")
    cfg, _, ip, _ = get_user_config(market)
    return jsonify({"ip": ip, "config": cfg})


@app.route("/api/user-config", methods=["POST"])
def api_set_config():
    market = request.args.get("market", "us")
    body = request.get_json(silent=True) or {}
    cfg = save_user_config(body, market)
    return jsonify({"ok": True, "config": cfg})


# ── Watchlist API (per-IP, per-market) ─────────────────────

def _wl_for_market(market):
    return "watchlist_tw" if market == "tw" else "watchlist_us"

@app.route("/api/watchlist", methods=["GET"])
def api_watchlist():
    market = request.args.get("market", "us")
    cfg, _, _, _ = get_user_config(market)
    return jsonify(cfg[_wl_for_market(market)])


@app.route("/api/watchlist/add", methods=["POST"])
def api_watchlist_add():
    body = request.get_json()
    symbol = body.get("symbol", "").upper().strip()
    market = body.get("market", "us")
    if not symbol:
        return jsonify({"error": "missing symbol"}), 400
    wl_key = _wl_for_market(market)
    cfg, configs, ip, _ = get_user_config(market)
    symbols = cfg[wl_key]
    if symbol not in symbols:
        symbols.append(symbol)
    configs[ip] = {**cfg, wl_key: symbols}
    save_all_configs(configs)
    return jsonify({"ok": True, "watchlist": symbols})


@app.route("/api/watchlist/<symbol>", methods=["DELETE"])
def api_watchlist_delete(symbol):
    symbol = symbol.upper()
    market = request.args.get("market", "us")
    wl_key = _wl_for_market(market)
    cfg, configs, ip, _ = get_user_config(market)
    symbols = [s for s in cfg[wl_key] if s != symbol]
    configs[ip] = {**cfg, wl_key: symbols}
    save_all_configs(configs)
    return jsonify({"ok": True, "watchlist": symbols})


# ── Quotes ──────────────────────────────────────────────

def _fetch_quotes(symbols, market="us"):
    """Fetch quotes for a list of symbols. market='tw' appends .TW suffix."""
    results = []
    try:
        resolved = [s + ".TW" if market == "tw" else s for s in symbols]
        tickers = yf.Tickers(" ".join(resolved))
        for i, sym in enumerate(symbols):
            try:
                r_sym = resolved[i]
                t = tickers.tickers[r_sym]
                info = t.fast_info
                price = info.last_price or 0.0
                prev_close = info.previous_close or price
                change = price - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0.0
                target = None
                try:
                    target = t.info.get("targetMeanPrice") or t.info.get("targetMedianPrice")
                except Exception:
                    pass
                results.append({
                    "symbol": sym,
                    "name": TW_NAMES.get(sym, "") if market == "tw" else "",
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": fmt_volume(info.last_volume or 0) if market == "us" else info.last_volume or 0,
                    "high": round(info.day_high or 0, 2),
                    "low": round(info.day_low or 0, 2),
                    "market_cap": fmt_market_cap(info.market_cap or 0) if market == "us" else info.market_cap or 0,
                    "target_price": round(target, 2) if target else None,
                    "ok": True,
                })
            except Exception as e:
                results.append({"symbol": sym, "ok": False, "error": str(e)})
    except Exception as e:
        raise e
    return results

@app.route("/api/quotes")
@cached(15)
def api_quotes():
    market = request.args.get("market", "us")
    cfg, _, _, wl_key = get_user_config(market)
    symbols = cfg[wl_key]
    try:
        results = _fetch_quotes(symbols, market)
        return jsonify({
            "quotes": results,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Chart ───────────────────────────────────────────────

@app.route("/api/chart")
@cached(30)
def api_chart():
    symbol = request.args.get("symbol", "AAPL").upper()
    market = request.args.get("market", "us")
    period = request.args.get("period", "1mo")
    interval = request.args.get("interval", "1d")
    yf_sym = symbol + ".TW" if market == "tw" else symbol
    try:
        hist = yf.Ticker(yf_sym).history(
            period=period, interval=interval, prepost=True
        )
        if hist.empty:
            return jsonify({"error": "no data"}), 404
        return jsonify({
            "dates": [str(d)[:16] for d in hist.index],
            "closes": [round(float(c), 2) for c in hist["Close"]],
            "volumes": [int(v) for v in hist["Volume"]],
            "highs": [round(float(h), 2) for h in hist["High"]],
            "lows": [round(float(l), 2) for l in hist["Low"]],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Alerts (global) ─────────────────────────────────────

@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    return jsonify(load_alerts())


@app.route("/api/alerts", methods=["POST"])
def add_alert():
    body = request.get_json()
    symbol = body.get("symbol", "").upper()
    target = body.get("target")
    stoploss = body.get("stoploss")
    alerts = load_alerts()
    alerts = [a for a in alerts if a["symbol"] != symbol]
    alerts.append({
        "symbol": symbol,
        "target": float(target) if target else None,
        "stoploss": float(stoploss) if stoploss else None,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "triggered": False,
    })
    save_alerts(alerts)
    return jsonify({"ok": True})


@app.route("/api/alerts/<symbol>", methods=["DELETE"])
def delete_alert(symbol):
    alerts = [a for a in load_alerts() if a["symbol"] != symbol.upper()]
    save_alerts(alerts)
    return jsonify({"ok": True})


@app.route("/api/alerts/check", methods=["GET"])
def check_alerts():
    alerts = load_alerts()
    symbols = [a["symbol"] for a in alerts if not a.get("triggered")]
    if not symbols:
        return jsonify({"triggered": []})
    try:
        tickers = yf.Tickers(" ".join(symbols))
    except Exception:
        return jsonify({"triggered": []})
    triggered = []
    remaining = []
    for a in alerts:
        if a.get("triggered"):
            remaining.append(a)
            continue
        sym = a["symbol"]
        try:
            price = tickers.tickers[sym].fast_info.last_price or 0.0
        except Exception:
            remaining.append(a)
            continue
        reason = None
        if a["target"] and price >= a["target"]:
            reason = f"目標價 ${a['target']} 已達 (現價 ${price:.2f})"
        elif a["stoploss"] and price <= a["stoploss"]:
            reason = f"停損價 ${a['stoploss']} 已觸及 (現價 ${price:.2f})"
        if reason:
            a["triggered"] = True
            a["triggered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            a["price_at_trigger"] = round(price, 2)
            triggered.append({"symbol": sym, "reason": reason, **a})
        else:
            remaining.append(a)
    save_alerts(remaining + triggered)
    return jsonify({"triggered": triggered})


# ── Market Indices ─────────────────────────────────────

US_INDICES = [
    ("^GSPC", "S&P 500"), ("^IXIC", "NASDAQ"), ("^DJI", "DOW"),
    ("^SOX", "SOX"), ("^VIX", "VIX"), ("^RUT", "RUSSELL"),
]
TW_INDICES = [
    ("^TWII", "加權指數"), ("0050.TW", "台灣50"),
]
INDICES_PERIOD_MAP = {"1d": ("1d", "5m"), "5d": ("5d", "5m"), "1mo": ("1mo", "1d"), "3mo": ("3mo", "1d")}

@app.route("/api/indices")
@cached(60)
def api_indices():
    market = request.args.get("market", "us")
    period = request.args.get("period", "1mo")
    p, iv = INDICES_PERIOD_MAP.get(period, ("1mo", "1d"))
    symbols = TW_INDICES if market == "tw" else US_INDICES
    results = []
    for sym, label in symbols:
        try:
            hist = yf.Ticker(sym).history(period=p, interval=iv)
            if hist.empty:
                continue
            closes = [round(float(c), 2) for c in hist["Close"]]
            dates = [str(d)[:10] for d in hist.index]
            first = closes[0] if closes else 0
            last = closes[-1] if closes else 0
            change_pct = round((last - first) / first * 100, 2) if first else 0
            results.append({
                "symbol": sym,
                "label": label,
                "last": last,
                "change_pct": change_pct,
                "closes": closes,
                "dates": dates,
            })
        except Exception:
            continue
    return jsonify({"indices": results, "period": period})


# ── Economic Calendar ──────────────────────────────────

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def next_nth_weekday(year, month, nth, weekday):
    count = 0
    d = datetime(year, month, 1)
    while d.month == month:
        if d.weekday() == weekday:
            count += 1
            if count == nth:
                return d
        d += timedelta(days=1)
    return None

def next_weekday(d, wd):
    """Return next occurrence of weekday (0=Mon..6=Sun) on or after d."""
    days_ahead = wd - d.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)

def _build_calendar(events, today):
    out = []
    for ev in events:
        if ev["date_obj"]:
            days_diff = (ev["date_obj"] - today).days
            ev["date"] = ev["date_obj"].strftime("%b %d")
            if days_diff < 7:
                ev["days"] = f"{MONTHS[ev['date_obj'].month-1]} {ev['date_obj'].day}"
            else:
                ev["days"] = f"{MONTHS[ev['date_obj'].month-1]} {ev['date_obj'].day}"
                if ev["date_obj"].year > today.year:
                    ev["days"] += f" {ev['date_obj'].year}"
            ev["_sort"] = ev["date_obj"].strftime("%Y-%m-%d")
        else:
            ev["_sort"] = "9999-99-99"
        ev.pop("date_obj", None)
        out.append(ev)
    return sorted(out, key=lambda x: x.get("_sort", "9999-99-99"))

def _us_economic_calendar():
    today = datetime.now()
    y, m = today.year, today.month
    events = [
        {"date":"","time":"Ongoing","event":"Fed Interest Rate Decision (FOMC)","impact":"high",
         "industry":"Financials, USD, Bonds","note":"利率升降影響全市場流動性與資金成本","date_obj":None},
        {"date":"","time":"08:30","event":"Consumer Price Index (CPI) MoM","impact":"high",
         "industry":"All sectors, USD, Bonds","note":"衡量通膨核心指標，影響 Fed 利率決策","date_obj":None},
        {"date":"","time":"08:30","event":"Non-Farm Payrolls (NFP)","impact":"high",
         "industry":"All sectors, USD, Equities","note":"就業市場健康度風向球","date_obj":None},
        {"date":"","time":"08:30","event":"Producer Price Index (PPI) MoM","impact":"high",
         "industry":"Industrials, Energy, Materials","note":"生產端物價壓力","date_obj":None},
        {"date":"","time":"10:00","event":"ISM Manufacturing PMI","impact":"high",
         "industry":"Industrials, Tech, Materials","note":"製造業景氣榮枯分水嶺","date_obj":None},
        {"date":"","time":"10:00","event":"ISM Services PMI","impact":"high",
         "industry":"Consumer, Tech, Financials","note":"服務業景氣指標","date_obj":None},
        {"date":"","time":"08:30","event":"Retail Sales MoM","impact":"medium",
         "industry":"Consumer, Retail, E-commerce","note":"消費者支出動能","date_obj":None},
        {"date":"","time":"08:30","event":"Initial Jobless Claims","impact":"medium",
         "industry":"All sectors","note":"每週就業數據","date_obj":None},
        {"date":"","time":"08:30","event":"GDP (Annualized) QoQ","impact":"high",
         "industry":"All sectors, USD","note":"經濟成長綜合衡量指標","date_obj":None},
        {"date":"","time":"10:30","event":"EIA Crude Oil Inventories","impact":"medium",
         "industry":"Energy, Oil & Gas","note":"原油庫存","date_obj":None},
        {"date":"","time":"14:00","event":"Treasury 10-Year Note Auction","impact":"medium",
         "industry":"Bonds, Financials","note":"公債標售","date_obj":None},
        {"date":"","time":"08:30","event":"Building Permits MoM","impact":"low",
         "industry":"Housing, Construction","note":"住宅許可","date_obj":None},
        {"date":"","time":"10:00","event":"Consumer Sentiment (U.Mich)","impact":"low",
         "industry":"Consumer, Retail","note":"消費者信心","date_obj":None},
        {"date":"","time":"10:00","event":"JOLTS Job Openings","impact":"low",
         "industry":"All sectors","note":"勞動供需缺口","date_obj":None},
        {"date":"","time":"08:30","event":"Trade Balance","impact":"low",
         "industry":"USD, Multinationals","note":"貿易差額","date_obj":None},
    ]
    # NFP: first Friday
    d1 = next_nth_weekday(y, m, 1, 4)
    if d1 and d1 < today and m == today.month:
        d1 = next_nth_weekday(y, m+1 if m<12 else 1, 1, 4) or d1
    events[2]["date_obj"] = d1
    # CPI: day 14
    d2 = datetime(y, m, 14)
    if d2 < today and m == today.month:
        d2 = datetime(y, m+1 if m<12 else 1, 14)
        if m == 12: d2 = d2.replace(year=y+1)
    while d2.weekday() >= 5: d2 += timedelta(days=1)
    events[1]["date_obj"] = d2
    # PPI: day 12
    d3 = datetime(y, m, 12)
    if d3 < today and m == today.month:
        d3 = datetime(y, m+1 if m<12 else 1, 12)
        if m == 12: d3 = d3.replace(year=y+1)
    while d3.weekday() >= 5: d3 += timedelta(days=1)
    events[3]["date_obj"] = d3
    # FOMC: next month 15
    d4 = datetime(y, m+1 if m<12 else 1, 15)
    if m == 12: d4 = d4.replace(year=y+1)
    while d4.weekday() >= 5: d4 += timedelta(days=1)
    events[0]["date_obj"] = d4
    # ISM Mfg: day 1
    d5 = datetime(y, m, 1)
    if d5 < today and m == today.month:
        d5 = datetime(y, m+1 if m<12 else 1, 1)
        if m == 12: d5 = d5.replace(year=y+1)
    events[4]["date_obj"] = d5
    # ISM Services: day 3
    d6 = datetime(y, m, 3)
    if d6 < today and m == today.month:
        d6 = datetime(y, m+1 if m<12 else 1, 3)
        if m == 12: d6 = d6.replace(year=y+1)
    events[5]["date_obj"] = d6
    # Retail Sales: day 15
    d7 = datetime(y, m, 15)
    if d7 < today and m == today.month:
        d7 = datetime(y, m+1 if m<12 else 1, 15)
        if m == 12: d7 = d7.replace(year=y+1)
    while d7.weekday() >= 5: d7 += timedelta(days=1)
    events[6]["date_obj"] = d7
    # GDP: quarterly
    qm = None
    for q in [1,4,7,10]:
        d8 = datetime(y, q, 25)
        if d8 > today: qm = d8; break
    if not qm: qm = datetime(y+1, 1, 25)
    events[8]["date_obj"] = qm
    # Building Permits: day 20
    d9 = datetime(y, m, 20)
    if d9 < today and m == today.month:
        d9 = datetime(y, m+1 if m<12 else 1, 20)
        if m == 12: d9 = d9.replace(year=y+1)
    while d9.weekday() >= 5: d9 += timedelta(days=1)
    events[11]["date_obj"] = d9
    # Consumer Sentiment: 2nd Fri (day ~10)
    d10 = datetime(y, m, 10)
    if d10 < today and m == today.month:
        d10 = datetime(y, m+1 if m<12 else 1, 10)
        if m == 12: d10 = d10.replace(year=y+1)
    while d10.weekday() != 4: d10 += timedelta(days=1)
    events[12]["date_obj"] = d10
    # JOLTS: day 6
    d11 = datetime(y, m, 6)
    if d11 < today and m == today.month:
        d11 = datetime(y, m+1 if m<12 else 1, 6)
        if m == 12: d11 = d11.replace(year=y+1)
    while d11.weekday() >= 5: d11 += timedelta(days=1)
    events[13]["date_obj"] = d11
    # Trade Balance: day 5
    d12 = datetime(y, m, 5)
    if d12 < today and m == today.month:
        d12 = datetime(y, m+1 if m<12 else 1, 5)
        if m == 12: d12 = d12.replace(year=y+1)
    while d12.weekday() >= 5: d12 += timedelta(days=1)
    events[14]["date_obj"] = d12
    events[7]["date_obj"] = next_weekday(today, 3)  # Jobless Claims: Thu
    events[9]["date_obj"] = next_weekday(today, 2)   # EIA: Wed
    events[10]["date_obj"] = next_weekday(today, 0)  # Treasury: Mon
    return _build_calendar(events, today)

def _tw_economic_calendar():
    today = datetime.now()
    y, m = today.year, today.month
    events = [
        {"date":"","time":"16:00","event":"央行理監事會議 (利率決策)","impact":"high",
         "industry":"金融, 台幣, 債券","note":"每季一次 (3/6/9/12月)，影響利率與匯率","date_obj":None},
        {"date":"","time":"16:00","event":"CPI 消費者物價指數","impact":"high",
         "industry":"全市場, 央行","note":"每月 5-7 日發布，衡量通膨","date_obj":None},
        {"date":"","time":"16:00","event":"GDP 經濟成長率 (季)","impact":"high",
         "industry":"全市場, 台幣","note":"每季發布，綜合經濟衡量指標","date_obj":None},
        {"date":"","time":"16:00","event":"外銷訂單","impact":"medium",
         "industry":"製造業, 出口","note":"每月 20 日發布，出口領先指標","date_obj":None},
        {"date":"","time":"16:00","event":"工業生產指數","impact":"medium",
         "industry":"製造業, 工業","note":"每月 23 日發布，生產活動衡量","date_obj":None},
        {"date":"","time":"16:00","event":"失業率","impact":"medium",
         "industry":"全市場","note":"每月 22 日發布，勞動市場健康度","date_obj":None},
        {"date":"","time":"16:00","event":"進出口貿易統計","impact":"medium",
         "industry":"出口, 台幣","note":"每月 7-8 日發布，貿易表現","date_obj":None},
        {"date":"","time":"16:00","event":"M1B / M2 貨幣總計數","impact":"low",
         "industry":"金融, 台幣","note":"每月 25 日發布，市場資金水位","date_obj":None},
        {"date":"","time":"16:00","event":"景氣對策信號 (燈號)","impact":"low",
         "industry":"全市場","note":"每月 27 日發布，綜合景氣判斷","date_obj":None},
    ]
    def mday(dd):
        d = datetime(y, m, dd)
        if d < today and m == today.month:
            d = datetime(y, m+1 if m<12 else 1, dd)
            if m == 12: d = d.replace(year=y+1)
        return d
    # CPI: day 7
    events[1]["date_obj"] = mday(7)
    # Export Orders: day 20
    events[3]["date_obj"] = mday(20)
    # Industrial Production: day 23
    events[4]["date_obj"] = mday(23)
    # Unemployment: day 22
    events[5]["date_obj"] = mday(22)
    # Trade: day 8
    events[6]["date_obj"] = mday(8)
    # M1B/M2: day 25
    events[7]["date_obj"] = mday(25)
    # Economic monitoring: day 27
    events[8]["date_obj"] = mday(27)
    # Central bank: quarterly (3/6/9/12)
    q_months = [3, 6, 9, 12]
    qm = None
    for qm in [datetime(y, q, 15) for q in q_months]:
        if qm > today: break
    if qm and qm < today: qm = datetime(y+1, 3, 15)
    if not qm: qm = datetime(y+1, 3, 15)
    events[0]["date_obj"] = qm
    # GDP: quarterly (2/5/8/11 ~ day 25)
    for q in [2, 5, 8, 11]:
        dg = datetime(y, q, 25)
        if dg > today: break
    else:
        dg = datetime(y+1, 2, 25)
    events[2]["date_obj"] = dg
    return _build_calendar(events, today)

@app.route("/api/economic-calendar")
def api_economic_calendar():
    market = request.args.get("market", "us")
    if market == "tw":
        return jsonify(_tw_economic_calendar())
    return jsonify(_us_economic_calendar())


# ── run ─────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Stock Monitor started on port {port}")
    app.run(host="0.0.0.0", debug=False, port=port)
