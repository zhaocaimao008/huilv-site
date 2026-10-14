#!/usr/bin/env python3
"""生成汇率换算静态网站。

用法:
    python3 build.py            # 从 Frankfurter(欧洲央行数据)抓取汇率并生成到 dist/
    python3 build.py --sample   # 用模拟数据生成(离线测试用)
"""
import datetime as dt
import html
import json
import math
import random
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import calc

ROOT = Path(__file__).parent
OUT = ROOT / "dist"
API = "https://api.frankfurter.dev/v1"

NAMES = {
    "CNY": ("人民币", "元"), "USD": ("美元", "美元"), "EUR": ("欧元", "欧元"),
    "JPY": ("日元", "日元"), "HKD": ("港币", "港元"), "GBP": ("英镑", "英镑"),
    "KRW": ("韩元", "韩元"), "AUD": ("澳元", "澳元"), "CAD": ("加元", "加元"),
    "SGD": ("新加坡元", "新元"), "THB": ("泰铢", "泰铢"), "MYR": ("马来西亚林吉特", "林吉特"),
    "CHF": ("瑞士法郎", "瑞郎"), "NZD": ("新西兰元", "纽元"),
}


def name(c):
    return NAMES.get(c, (c, c))[0]


# ---------- 数据 ----------

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "huilv-site/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def load_rates(cfg, sample=False):
    """返回 (日期列表, {日期: {币种: 1欧元可兑换数量}}),欧元自身为 1。"""
    cur = [c for c in cfg["currencies"] if c != "EUR"]
    end = dt.date.today()
    start = end - dt.timedelta(days=cfg["history_days"] + 10)
    if sample:
        base = {"CNY": 8.2, "USD": 1.15, "JPY": 170.0, "HKD": 8.95, "GBP": 0.86, "KRW": 1580.0,
                "AUD": 1.75, "CAD": 1.6, "SGD": 1.48, "THB": 37.5, "MYR": 4.9, "CHF": 0.93, "NZD": 1.95}
        rng = random.Random(42)
        series, d = {}, start
        while d <= end:
            if d.weekday() < 5:
                series[d.isoformat()] = {c: base.get(c, 1.0) * (1 + rng.uniform(-0.02, 0.02)) for c in cur}
            d += dt.timedelta(days=1)
    else:
        data = fetch_json(f"{API}/{start.isoformat()}..?base=EUR&symbols={','.join(cur)}")
        series = data["rates"]
        latest = fetch_json(f"{API}/latest?base=EUR&symbols={','.join(cur)}")
        series[latest["date"]] = latest["rates"]
    for day in series.values():
        day["EUR"] = 1.0
    dates = sorted(series)[-cfg["history_days"]:]
    return dates, {d: series[d] for d in dates}


def cross(day, a, b):
    """1 单位 a 可兑换多少 b。"""
    return day[b] / day[a]


# ---------- 格式化 ----------

def fmt(x):
    if x == 0:
        return "0"
    if abs(x) >= 100:
        return f"{x:,.2f}"
    if abs(x) >= 1:
        return f"{x:,.4f}"
    digits = 4 - int(math.floor(math.log10(abs(x))))
    return f"{x:.{digits}f}"


def fmt_amt(n):
    return f"{n:,}" if n < 10000 else (f"{n // 10000}万" if n % 10000 == 0 else f"{n:,}")


def esc(s):
    return html.escape(str(s))

def network_html(cfg):
    """页脚"更多实用工具":同系列网站互相链接(列表见 config.json 的 network)。"""
    sites = [s for s in cfg.get("network", []) if s["url"].rstrip("/") != cfg["base_url"].rstrip("/")]
    if not sites:
        return ""
    return "<br>更多实用工具:" + " · ".join(f'<a href="{esc(s["url"])}">{esc(s["name"])}</a>' for s in sites)



# ---------- 页面模板 ----------

CSS = """
:root{--bg:#f7f8fa;--card:#fff;--text:#1d2129;--muted:#6b7280;--line:#e5e7eb;--accent:#1f6feb;--up:#d93025;--down:#188038}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--text:#e6e8eb;--muted:#9aa1ac;--line:#2a2f3a;--accent:#58a6ff;--up:#ff7b72;--down:#3fb950}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header,main,footer{max-width:860px;margin:0 auto;padding:0 16px}
header{padding-top:16px}header .logo{font-weight:700;font-size:18px;color:var(--text)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:16px 0}
h1{font-size:24px;line-height:1.4;margin:8px 0;overflow-wrap:anywhere}h2{font-size:19px;margin:0 0 12px}
.big{font-size:30px;font-weight:700;margin:4px 0}.muted{color:var(--muted);font-size:14px}
.up{color:var(--up)}.down{color:var(--down)}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}td,th{padding:8px 6px;border-bottom:1px solid var(--line);text-align:right}td:first-child,th:first-child{text-align:left}
.conv{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.conv input{font-size:18px;padding:8px 10px;width:160px;max-width:38vw;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text)}
.links{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:15px}
svg{width:100%;height:auto}.ad{margin:16px 0;min-height:90px}
footer{padding:24px 16px;color:var(--muted);font-size:13px}
nav{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:15px;margin-top:6px}
.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}.form label{display:flex;flex-direction:column;font-size:14px;color:var(--muted)}
.form input,.form select{font-size:17px;padding:8px 10px;margin-top:4px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);width:100%}
.res{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:16px}.res div{background:var(--bg);border-radius:8px;padding:10px 12px}.res b{display:block;font-size:20px}
.scroll{overflow-x:auto}
"""


def layout(cfg, title, desc, path, body):
    url = cfg["base_url"].rstrip("/") + path
    ads = ""
    if cfg.get("adsense_client"):
        ads = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
               f'{esc(cfg["adsense_client"])}" crossorigin="anonymous"></script>')
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">{ads}
<style>{CSS}</style></head><body>
<header><a class="logo" href="/">{esc(cfg["site_name"])}</a>
<nav><a href="/">汇率换算</a><a href="/fangdai/">房贷计算器</a><a href="/geshui/">个税计算器</a><a href="/nianzhongjiang/">年终奖个税</a></nav></header>
<main>{body}</main>
<footer>汇率数据来源:欧洲央行(ECB)参考汇率,每个工作日更新。房贷、个税计算结果按公开公式估算。本站所有数据仅供参考,不构成任何建议,实际以银行、税务机关为准。{network_html(cfg)}</footer>
</body></html>"""


def ad_slot(cfg):
    if not cfg.get("adsense_client"):
        return ""
    return (f'<div class="ad"><ins class="adsbygoogle" style="display:block" data-ad-client="{esc(cfg["adsense_client"])}" '
            'data-ad-format="auto" data-full-width-responsive="true"></ins>'
            '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>')


def chart(values, dates):
    w, h, pad = 600, 180, 24
    lo, hi = min(values), max(values)
    span = (hi - lo) or hi or 1
    pts = []
    for i, v in enumerate(values):
        x = pad + i * (w - 2 * pad) / max(len(values) - 1, 1)
        y = h - pad - (v - lo) / span * (h - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="近{len(values)}个交易日走势">'
            f'<polyline fill="none" stroke="currentColor" stroke-width="2" points="{" ".join(pts)}" style="color:var(--accent)"/>'
            f'<text x="{pad}" y="14" font-size="12" fill="currentColor" opacity=".6">最高 {fmt(hi)}</text>'
            f'<text x="{pad}" y="{h - 4}" font-size="12" fill="currentColor" opacity=".6">最低 {fmt(lo)} · {dates[0]} 至 {dates[-1]}</text>'
            '</svg>')


def change_html(now, prev):
    pct = (now - prev) / prev * 100
    cls = "up" if pct > 0 else "down" if pct < 0 else ""
    return f'<span class="{cls}">{"+" if pct > 0 else ""}{pct:.2f}%</span>'


def pair_page(cfg, dates, rates, a, b):
    series = [cross(rates[d], a, b) for d in dates]
    now, prev = series[-1], series[-2] if len(series) > 1 else series[-1]
    na, nb = name(a), name(b)
    unit_b = NAMES.get(b, (b, b))[1]
    rows = "".join(f'<tr><td><a href="/{a.lower()}-{b.lower()}/{n}/">{fmt_amt(n)} {na}</a></td><td>{fmt(n * now)} {nb}</td></tr>'
                   if (cfg["home_currency"] in (a, b)) else
                   f'<tr><td>{fmt_amt(n)} {na}</td><td>{fmt(n * now)} {nb}</td></tr>'
                   for n in cfg["amounts"])
    rev = "".join(f'<tr><td>{fmt_amt(n)} {nb}</td><td>{fmt(n / now)} {na}</td></tr>' for n in cfg["amounts"])
    hist = "".join(f"<tr><td>{d}</td><td>{fmt(v)}</td></tr>" for d, v in list(zip(dates, series))[::-1][:10])
    hi, lo, avg = max(series), min(series), sum(series) / len(series)
    others = [c for c in cfg["currencies"] if c not in (a, b)]
    links = " ".join(f'<a href="/{a.lower()}-{c.lower()}/">{na}兑{name(c)}</a>' for c in others[:8])
    links += " " + " ".join(f'<a href="/{c.lower()}-{b.lower()}/">{name(c)}兑{nb}</a>' for c in others[:8])
    body = f"""
<div class="card"><h1>{na}兑{nb}汇率今日({a}/{b})</h1>
<div class="big">1 {na} = {fmt(now)} {nb}</div>
<div class="muted">更新日期 {dates[-1]} · 较上一交易日 {change_html(now, prev)} · 1 {nb} = {fmt(1 / now)} {na}</div></div>
{ad_slot(cfg)}
<div class="card"><h2>{na}{nb}换算器</h2><div class="conv">
<input id="ia" type="number" value="100" inputmode="decimal" aria-label="{na}金额"> {na} =
<input id="ib" type="number" inputmode="decimal" aria-label="{nb}金额"> {nb}</div>
<script>(function(){{var r={now!r},a=document.getElementById('ia'),b=document.getElementById('ib');
function f(v){{return +v.toPrecision(8)}}a.oninput=function(){{b.value=f(a.value*r)}};b.oninput=function(){{a.value=f(b.value/r)}};a.oninput();}})();</script></div>
<div class="card"><h2>近{len(series)}个交易日走势</h2>{chart(series, dates)}
<p class="muted">区间最高 {fmt(hi)},最低 {fmt(lo)},平均 {fmt(avg)}。当前汇率较区间均值{"高" if now >= avg else "低"} {abs(now - avg) / avg * 100:.2f}%。</p></div>
<div class="card"><h2>{na}换{nb}对照表</h2><table><tr><th>{na}</th><th>{nb}</th></tr>{rows}</table></div>
{ad_slot(cfg)}
<div class="card"><h2>{nb}换{na}对照表</h2><table><tr><th>{nb}</th><th>{na}</th></tr>{rev}</table></div>
<div class="card"><h2>历史汇率</h2><table><tr><th>日期</th><th>1 {na} 兑 {nb}</th></tr>{hist}</table></div>
<div class="card"><h2>常见问题</h2>
<p><b>今天1{na}等于多少{nb}?</b><br>按 {dates[-1]} 欧洲央行参考汇率,1 {na} 约等于 {fmt(now)} {unit_b},100 {na} 约等于 {fmt(100 * now)} {unit_b}。</p>
<p><b>{na}兑{nb}汇率是涨还是跌?</b><br>近{len(series)}个交易日,该汇率从 {fmt(series[0])} 变为 {fmt(now)},累计 {change_html(now, series[0])}。</p>
<p><b>为什么和银行报价不一样?</b><br>本站展示的是中间参考价,银行实际买入/卖出价会包含点差和手续费。</p></div>
<div class="card"><h2>相关汇率</h2><div class="links">{links}</div></div>"""
    title = f"{na}兑{nb}汇率今日 - 1{na}等于多少{nb}({dates[-1]})"
    desc = f"今日1{na}={fmt(now)}{nb}。提供{na}{nb}在线换算、对照表、近{len(series)}日走势与历史汇率,每日自动更新。"
    return title, desc, body


def amount_page(cfg, dates, rates, a, b, n):
    now = cross(rates[dates[-1]], a, b)
    na, nb = name(a), name(b)
    near = "".join(f'<tr><td><a href="/{a.lower()}-{b.lower()}/{m}/">{fmt_amt(m)} {na}</a></td><td>{fmt(m * now)} {nb}</td></tr>'
                   for m in cfg["amounts"])
    body = f"""
<div class="card"><h1>{fmt_amt(n)}{na}等于多少{nb}?</h1>
<div class="big">{fmt_amt(n)} {na} = {fmt(n * now)} {nb}</div>
<div class="muted">按 {dates[-1]} 汇率 1 {na} = {fmt(now)} {nb} 计算 · <a href="/{a.lower()}-{b.lower()}/">查看{na}兑{nb}走势与换算器</a></div></div>
{ad_slot(cfg)}
<div class="card"><h2>计算方法</h2><p>{fmt_amt(n)} × {fmt(now)} = {fmt(n * now)} {nb}。反过来,{fmt_amt(n)} {nb} ≈ {fmt(n / now)} {na}。</p></div>
<div class="card"><h2>其他金额</h2><table><tr><th>{na}</th><th>{nb}</th></tr>{near}</table></div>"""
    title = f"{fmt_amt(n)}{na}等于多少{nb} - 今日汇率换算({dates[-1]})"
    desc = f"{fmt_amt(n)}{na}今日约合{fmt(n * now)}{nb},按最新汇率1{na}={fmt(now)}{nb}计算,每日自动更新。"
    return title, desc, body


def home_page(cfg, dates, rates):
    h = cfg["home_currency"]
    day, prev = rates[dates[-1]], rates[dates[-2]] if len(dates) > 1 else rates[dates[-1]]
    rows = "".join(
        f'<tr><td><a href="/{c.lower()}-{h.lower()}/">{name(c)} {c}</a></td><td>{fmt(cross(day, c, h))}</td>'
        f'<td>{change_html(cross(day, c, h), cross(prev, c, h))}</td></tr>'
        for c in cfg["currencies"] if c != h)
    allpairs = " ".join(f'<a href="/{a.lower()}-{b.lower()}/">{name(a)}兑{name(b)}</a>'
                        for a in cfg["currencies"] for b in cfg["currencies"] if a != b)
    body = f"""
<div class="card"><h1>今日汇率查询与换算</h1><p class="muted">数据日期 {dates[-1]},每个工作日自动更新。</p>
<table><tr><th>币种</th><th>1 单位兑{name(h)}</th><th>涨跌</th></tr>{rows}</table></div>
{ad_slot(cfg)}
<div class="card"><h2>实用计算器</h2><div class="links"><a href="/fangdai/">房贷计算器(等额本息/本金)</a><a href="/geshui/">工资个税计算器</a><a href="/nianzhongjiang/">年终奖个税计算器</a></div></div>
<div class="card"><h2>全部货币对</h2><div class="links">{allpairs}</div></div>"""
    return f"今日汇率查询 - 人民币汇率换算({dates[-1]})", f"实时查询美元、欧元、日元、港币等{len(cfg['currencies'])}种货币兑人民币汇率,提供在线换算与走势,每日自动更新。", body


# ---------- 构建 ----------

def write(cfg, path, page, urls):
    title, desc, body = page
    f = OUT / path.strip("/") / "index.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    # 站点部署在子路径下(如 github.io/huilv-site)时,给站内链接加前缀
    prefix = urllib.parse.urlparse(cfg["base_url"]).path.rstrip("/")
    page_html = layout(cfg, title, desc, path, body).replace('href="/', f'href="{prefix}/')
    f.write_text(page_html, encoding="utf-8")
    urls.append(path)


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    dates, rates = load_rates(cfg, sample="--sample" in sys.argv)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    urls = []
    write(cfg, "/", home_page(cfg, dates, rates), urls)
    for path, page in calc.pages(cfg, ad_slot(cfg)):
        write(cfg, path, page, urls)
    cur, h = cfg["currencies"], cfg["home_currency"]
    for a in cur:
        for b in cur:
            if a == b:
                continue
            write(cfg, f"/{a.lower()}-{b.lower()}/", pair_page(cfg, dates, rates, a, b), urls)
            if h in (a, b):
                for n in cfg["amounts"]:
                    write(cfg, f"/{a.lower()}-{b.lower()}/{n}/", amount_page(cfg, dates, rates, a, b, n), urls)

    base = cfg["base_url"].rstrip("/")
    sm = "".join(f"<url><loc>{esc(base + u)}</loc><lastmod>{dates[-1]}</lastmod></url>" for u in urls)
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>',
        encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    if cfg.get("adsense_client"):
        pub = cfg["adsense_client"].replace("ca-", "")
        (OUT / "ads.txt").write_text(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    domain = base.split("://", 1)[-1]
    if domain and "/" not in domain and "example.com" not in domain and not domain.endswith("github.io"):
        (OUT / "CNAME").write_text(domain + "\n", encoding="utf-8")
    print(f"生成 {len(urls)} 个页面,数据日期 {dates[-1]}")


if __name__ == "__main__":
    main()
