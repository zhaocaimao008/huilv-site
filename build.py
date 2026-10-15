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
import re
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import calc
import finance

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


def json_ld(obj):
    """序列化 JSON-LD,并避免 </script> 提前结束标签。"""
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def ld_scripts(graphs):
    return "\n".join(f'<script type="application/ld+json">{json_ld(g)}</script>' for g in graphs)


def og_tags(cfg, title, desc, url):
    return (
        f'<meta property="og:title" content="{esc(title)}">\n'
        f'<meta property="og:description" content="{esc(desc)}">\n'
        f'<meta property="og:url" content="{esc(url)}">\n'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:site_name" content="{esc(cfg["site_name"])}">\n'
        f'<meta property="og:locale" content="zh_CN">'
    )


def home_graphs(cfg):
    url = cfg["base_url"].rstrip("/") + "/"
    name = cfg["site_name"]
    return [
        {"@context": "https://schema.org", "@type": "WebSite", "name": name, "url": url, "inLanguage": "zh-CN"},
        {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": name,
            "url": url,
            "applicationCategory": "FinanceApplication",
            "operatingSystem": "All",
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "CNY"},
            "inLanguage": "zh-CN",
        },
    ]


def breadcrumb_graph(cfg, items):
    base = cfg["base_url"].rstrip("/")
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": label, "item": base + href}
            for i, (label, href) in enumerate(items, 1)
        ],
    }


_TAG_RE = re.compile(r"<[^>]+>")
_FAQ_BLOCK_RE = re.compile(r"<h2>常见问题</h2>(.*?)</div>", re.S)
_FAQ_QA_RE = re.compile(r"<p><b>(.*?)</b><br>(.*?)</p>", re.S)


def visible_text(s):
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub("", s))).strip()


def extract_faqs(body):
    """只从页面上已经写出来的「常见问题」提取问答,供 FAQPage 使用。"""
    block = _FAQ_BLOCK_RE.search(body)
    if not block:
        return []
    return [(visible_text(q), visible_text(a)) for q, a in _FAQ_QA_RE.findall(block.group(1))]


def faq_graph(faqs):
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ],
    }


def breadcrumb_items(path):
    """内页面包屑。名称与导航、栏目内链一致,不在页面上另画一条导航。"""
    if path == "/":
        return []
    home = [("首页", "/")]
    pair = re.fullmatch(r"/([a-z]{3})-([a-z]{3})/", path)
    if pair:
        a, b = pair.group(1).upper(), pair.group(2).upper()
        return home + [(f"{name(a)}兑{name(b)}", path)]
    amt = re.fullmatch(r"/([a-z]{3})-([a-z]{3})/(\d+)/", path)
    if amt:
        a, b, n = amt.group(1).upper(), amt.group(2).upper(), int(amt.group(3))
        parent = f"/{amt.group(1)}-{amt.group(2)}/"
        return home + [
            (f"{name(a)}兑{name(b)}", parent),
            (f"{fmt_amt(n)}{name(a)}等于多少{name(b)}", path),
        ]
    sections = {
        "fangdai": "房贷计算器",
        "geshui": "个税计算器",
        "nianzhongjiang": "年终奖个税",
        "cunkuan": "存款利息",
        "dingtou": "定投复利",
        "tiqian": "提前还贷",
        "gongjijin": "公积金贷款",
    }
    parts = path.strip("/").split("/")
    if len(parts) == 1 and parts[0] in sections:
        return home + [(sections[parts[0]], path)]
    if len(parts) == 2 and parts[0] in sections:
        return home + [(sections[parts[0]], f"/{parts[0]}/"), (leaf_name(parts[0], parts[1]), path)]
    raise ValueError(f"无法生成面包屑: {path}")


def leaf_name(section, slug):
    if section == "fangdai":
        a, y = re.fullmatch(r"(\d+)wan-(\d+)nian", slug).groups()
        return f"{a}万{y}年"
    if section == "geshui":
        return f"月薪{fmt_amt(int(slug))}"
    if section == "nianzhongjiang":
        return f"年终奖{fmt_amt(int(slug))}"
    if section == "cunkuan":
        a, y = re.fullmatch(r"(\d+)wan-(\d+)nian", slug).groups()
        return f"{a}万存{y}年"
    if section == "dingtou":
        m, y = re.fullmatch(r"(\d+)-(\d+)nian", slug).groups()
        return f"每月{m}元定投{y}年"
    if section == "tiqian":
        a, k, x = re.fullmatch(r"(\d+)wan-(\d+)nian-(\d+)wan", slug).groups()
        return f"{a}万还了{k}年提前还{x}万"
    if section == "gongjijin":
        a, y = re.fullmatch(r"(\d+)wan-(\d+)nian", slug).groups()
        return f"公积金贷{a}万{y}年"
    raise ValueError(slug)


def page_graphs(cfg, path, body):
    graphs = home_graphs(cfg) if path == "/" else [breadcrumb_graph(cfg, breadcrumb_items(path))]
    faqs = extract_faqs(body)
    if faqs:
        graphs.append(faq_graph(faqs))
    return graphs


def layout(cfg, title, desc, path, body, graphs=None):
    url = cfg["base_url"].rstrip("/") + path
    ads = ""
    if cfg.get("adsense_client"):
        ads = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
               f'{esc(cfg["adsense_client"])}" crossorigin="anonymous"></script>')
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
{og_tags(cfg, title, desc, url)}
{ld_scripts(graphs or [])}
{ads}
<style>{CSS}</style></head><body>
<header><a class="logo" href="/">{esc(cfg["site_name"])}</a>
<nav><a href="/">汇率换算</a><a href="/fangdai/">房贷计算器</a><a href="/geshui/">个税计算器</a><a href="/nianzhongjiang/">年终奖个税</a><a href="/cunkuan/">存款利息</a><a href="/dingtou/">定投复利</a><a href="/tiqian/">提前还贷</a><a href="/gongjijin/">公积金贷款</a></nav></header>
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


# 货币对页开头的一段说明。马币、人民币以及少数高频交叉盘手写;
# 其余货币对用各自的用途说明拼成不同的段落,避免 182 页只替换数字。
PAIR_INTRO = {
    ("MYR", "CNY"): "马来西亚林吉特兑人民币,也就是马币兑人民币,是在马来西亚拿林吉特工资、再汇回国内的人最常查的一对。国内银行多写「林吉特」,口语里叫马币或令吉,货币代码都是 MYR。今天 1 林吉特约合 {rate} 元,100 林吉特约合 {r100} 元。本页是中间参考价,银行现钞和电汇都会有点差。",
    ("CNY", "MYR"): "人民币换马币,适合去马来西亚旅游、探亲,或从国内往马来西亚账户汇款之前先估算。林吉特是马来西亚的法定货币,1 林吉特等于 100 仙。按 {date} 的参考价,1 元约合 {rate} 林吉特,1000 元约合 {r1000} 林吉特。机场兑换通常比这个中间价贵,可以拿它和找换店牌价对照。",
    ("SGD", "MYR"): "新加坡元兑马来西亚林吉特,就是新币兑马币,新马两地过关、购物和汇款都会用到。两边相邻,很多人手上同时有新币和马币。今天 1 新元约合 {rate} 林吉特,100 新元约合 {r100} 林吉特。过关前先用中间价估一笔开销,到现场再按牌价决定换多少现金。",
    ("MYR", "SGD"): "马币换新加坡元,常见于从马来西亚去新加坡上班、购物或交学费。1 林吉特通常换不到 1 新元,同一笔开销用马币折算会显得更多,这是币值不同,不是标价错误。今天 1 林吉特约合 {rate} 新元,1000 林吉特约合 {r1000} 新元。工资发林吉特、开销在新加坡时,可以用这页看每月大约折合多少新元。",
    ("USD", "MYR"): "美元兑马币,用来估算美元账户、海淘,或外币卡在马来西亚消费时会变成多少林吉特。马来西亚不少跨境报价先标美元,付款再按当天汇率折算。今天 1 美元约合 {rate} 林吉特,100 美元约合 {r100} 林吉特。支付工具上的汇率多半已经含手续费,可以和这个中间价比一比。",
    ("MYR", "USD"): "马币兑美元,适合把林吉特收入换成美元,或看看一笔马币存款目前大约值多少美元。今天 1 林吉特约合 {rate} 美元,1000 林吉特约合 {r1000} 美元,反过来 1 美元约合 {rev} 林吉特。跨境转账用的是银行买入价或卖出价,会偏离本页的参考中间价。",
    ("EUR", "MYR"): "欧元兑马币,方便从欧洲汇钱到马来西亚,或欧洲游客估算在马来西亚的花费。本站汇率以欧元为计价基础,再交叉算出其他货币。今天 1 欧元约合 {rate} 林吉特,100 欧元约合 {r100} 林吉特。欧元现钞在马来西亚不如美元好换,金额大时更适合电汇。",
    ("MYR", "EUR"): "马币换欧元,多用于从马来西亚汇往欧洲,或去欧元区旅行前估预算。1 林吉特换成欧元是一个小于 1 的数,核对时别看错小数点。今天 1 林吉特约合 {rate} 欧元,1000 林吉特约合 {r1000} 欧元。出发前再对一次银行卖出价,中间价不含点差。",
    ("JPY", "MYR"): "日元兑马币时,日元面额很大,同样一笔钱用日元写出来位数会多很多。从日本汇到马来西亚,或在马来西亚花日元,建议直接看 10000 日元。今天 10000 日元约合 {r10000} 林吉特,1 日元约合 {rate} 林吉特。日元报价通常不带小数,林吉特则算到仙。",
    ("MYR", "JPY"): "马币换日元,常见于从马来西亚去日本旅游前换现钞或估算刷卡账单。1 林吉特能换到的日元远多于 1,对照表上的数字比较长是正常的。今天 1 林吉特约合 {rate} 日元,100 林吉特约合 {r100} 日元。日本不少小店仍收现金,可以按天数用这页估一个总额。",
    ("HKD", "MYR"): "港币兑马币,适合香港和马来西亚之间的汇款、旅游和购物。港币对美元有联系汇率,对林吉特则会跟着美元兑马币一起变动。今天 1 港元约合 {rate} 林吉特,1000 港元约合 {r1000} 林吉特。换的时候分清现钞和电汇,两种牌价不一样。",
    ("MYR", "HKD"): "马币换港币,用来估算从马来西亚汇到香港,或在香港消费时林吉特大约值多少港元。1 林吉特和 1 港元不是 1 比 1。今天 1 林吉特约合 {rate} 港元,100 林吉特约合 {r100} 港元。港币主要在香港使用,带回马来西亚一般还要再换成林吉特。",
    ("GBP", "MYR"): "英镑兑马币,多用于英国留学的学费和生活费换算成林吉特,或英国游客估算马币现金。英镑币值较高,1 英镑换成林吉特的数字通常比较大。今天 1 英镑约合 {rate} 林吉特,100 英镑约合 {r100} 林吉特。学校若以英镑报价,实际成本要看付款当天的银行卖出价。",
    ("MYR", "GBP"): "马币换英镑,适合在马来西亚准备英国留学费用,或向英国账户汇款前先算林吉特成本。1 林吉特换成英镑是一个较小的小数。今天 1 林吉特约合 {rate} 英镑,10000 林吉特约合 {r10000} 英镑。金额大时电汇通常比机场现钞更接近中间价。",
    ("KRW", "MYR"): "韩元兑马币时不要被位数吓到:韩元面额大,几千韩元才相当于几林吉特。从韩国汇款或在马来西亚花韩元,直接看 10000 韩元更清楚。今天 10000 韩元约合 {r10000} 林吉特,1 韩元约合 {rate} 林吉特。找换时按林吉特总价确认,避免少看一个零。",
    ("MYR", "KRW"): "马币换韩元,常见于从马来西亚去韩国旅游。1 林吉特能换到的韩元远多于 1,对照表要看完整位数。今天 1 林吉特约合 {rate} 韩元,100 林吉特约合 {r100} 韩元。韩国部分市场和交通仍用现金,出发前按这页估一个韩元总额即可。",
    ("AUD", "MYR"): "澳元兑马币,用来把澳大利亚的学费、工资或汇款折成林吉特。澳元的 $ 符号不是美元,也不是新元。今天 1 澳元约合 {rate} 林吉特,100 澳元约合 {r100} 林吉特。比较银行报价时,先确认牌价写的是澳元(AUD)。",
    ("MYR", "AUD"): "马币换澳元,适合准备去澳大利亚留学,或把林吉特汇到澳洲账户之前估算。今天 1 林吉特约合 {rate} 澳元,1000 林吉特约合 {r1000} 澳元。澳洲当地消费用澳元,这页的中间价可以用来对照学校和银行给出的汇率。",
    ("CAD", "MYR"): "加元兑马币,用于把加拿大的学费或工资换算成林吉特。加元也常写成 $,和美元不是同一种货币。今天 1 加元约合 {rate} 林吉特,100 加元约合 {r100} 林吉特。汇到马来西亚时,到账林吉特以银行当天买入价为准。",
    ("MYR", "CAD"): "马币换加元,用来估算从马来西亚汇往加拿大要准备多少林吉特。今天 1 林吉特约合 {rate} 加元,1000 林吉特约合 {r1000} 加元。办理时向银行说明是加元(CAD),避免被做成美元。金额较大时优先看电汇价。",
    ("THB", "MYR"): "泰铢兑马币,是马来西亚和泰国之间短途旅行最常用的换算。两边是邻国,陆路过关时经常要换现钞。今天 1 泰铢约合 {rate} 林吉特,1000 泰铢约合 {r1000} 林吉特。泰国小店更认泰铢现金,可以按这页先换几天的量。",
    ("MYR", "THB"): "马币换泰铢,适合从马来西亚去泰国之前估算要带多少现金。1 林吉特换成泰铢通常大于 1,所以泰铢数字会多一些。今天 1 林吉特约合 {rate} 泰铢,100 林吉特约合 {r100} 泰铢。过关找换和市区找换差价不小,先用中间价心里有个数。",
    ("CHF", "MYR"): "瑞士法郎兑马币时,1 瑞郎对应的林吉特通常比较多,因为瑞郎币值高。从瑞士汇到马来西亚,或把瑞郎账单折成马币,都可以先看这页。今天 1 瑞郎约合 {rate} 林吉特,100 瑞郎约合 {r100} 林吉特。瑞郎现钞在马来西亚不好换,汇款比带现钞现实。",
    ("MYR", "CHF"): "马币换瑞士法郎,多用于去瑞士旅行或向瑞士付款前估算林吉特成本。1 林吉特换成瑞郎是一个较小的数。今天 1 林吉特约合 {rate} 瑞郎,1000 林吉特约合 {r1000} 瑞郎。瑞士物价高,用马币做总预算时建议在中间价之外再留一点给定点差。",
    ("NZD", "MYR"): "新西兰元兑马币,用来把新西兰的学费或生活费折成林吉特。纽元的 $ 符号容易和美元、澳元混淆,换汇时要说清是 NZD。今天 1 纽元约合 {rate} 林吉特,100 纽元约合 {r100} 林吉特。汇到马来西亚的到账金额以银行当天牌价为准。",
    ("MYR", "NZD"): "马币换新西兰元,适合准备新西兰费用时先算需要多少林吉特。今天 1 林吉特约合 {rate} 纽元,1000 林吉特约合 {r1000} 纽元。和澳元、美元相比,纽元是另一种货币,向银行说清要换的是新西兰元。",
    ("USD", "CNY"): "美元兑人民币是国内查得最多的汇率,留学、海淘、外贸和出境都会用到。今天 1 美元约合 {rate} 元,100 美元约合 {r100} 元。银行美元现汇和现钞价格不同,本页是欧洲央行参考中间价,用来对照,不是某一家银行的牌价。",
    ("CNY", "USD"): "人民币换美元,适合出境前估算换汇成本,或把人民币收入折成美元。今天 1 元约合 {rate} 美元,1000 元约合 {r1000} 美元,也就是 1 美元约合 {rev} 元。购汇、现钞和电汇的价格都不一样,办理时以银行当天牌价为准。",
    ("EUR", "CNY"): "欧元兑人民币,用于欧洲旅行、欧元区学费和欧元账户换算。今天 1 欧元约合 {rate} 元,100 欧元约合 {r100} 元。欧元现钞在欧元区各国通用。这页由欧洲央行参考汇率交叉计算,每个工作日更新。",
    ("CNY", "EUR"): "人民币换欧元,可以在去欧洲之前先算 1000 元大约能换多少欧元。今天 1 元约合 {rate} 欧元,1000 元约合 {r1000} 欧元,1 欧元反过来约合 {rev} 元。欧洲很多地方刷卡方便,现金可以少换,用这页留个预算即可。",
    ("JPY", "CNY"): "日元兑人民币时,1 日元只值几分钱,看 10000 日元更有感觉。今天 10000 日元约合 {r10000} 元,1 日元约合 {rate} 元。去日本旅游或代购以日元标价时,先换成人民币再比较价格。",
    ("CNY", "JPY"): "人民币换日元,是赴日旅游最需要的换算。今天 1 元约合 {rate} 日元,1000 元约合 {r1000} 日元。日元通常不写小数,可以把结果四舍五入到整数再对照找换店。交通卡和便利店支出多,现金不用一次换满。",
    ("HKD", "CNY"): "港币兑人民币,用于深港往来、在香港消费后折回人民币,以及港币汇款。港币联系汇率使它大体跟着美元兑人民币走。今天 1 港元约合 {rate} 元,1000 港元约合 {r1000} 元。现钞和电汇牌价不同,这页是中间参考价。",
    ("CNY", "HKD"): "人民币换港币,适合去香港前估算购物和餐饮预算。今天 1 元约合 {rate} 港元,1000 元约合 {r1000} 港元。香港刷卡和电子支付很普遍,现钞按这页少换一部分即可。",
    ("GBP", "CNY"): "英镑兑人民币,常见于英国留学的学费和生活费。英镑币值通常高于美元,1 英镑换成人民币往往更多。今天 1 英镑约合 {rate} 元,100 英镑约合 {r100} 元。学校以英镑报价时,用付款当天的银行卖出价才是实际人民币成本。",
    ("CNY", "GBP"): "人民币换英镑,用来准备英国生活费,或把英镑账单折成人民币。今天 1 元约合 {rate} 英镑,1 英镑约合 {rev} 元。金额大的时候电汇比现钞更接近中间价,可以拿这页和银行牌价对比。",
    ("KRW", "CNY"): "韩元兑人民币,1 韩元不到 1 分钱,看 10000 韩元才比较直观。今天 10000 韩元约合 {r10000} 元,1 韩元约合 {rate} 元。韩国购物或旅游以韩元标价时,先折成人民币再决定。",
    ("CNY", "KRW"): "人民币换韩元,适合赴韩旅游前估算现金。今天 1 元约合 {rate} 韩元,100 元约合 {r100} 韩元。韩元位数多,换完按总金额再确认一次,避免少看或多看一个零。",
    ("AUD", "CNY"): "澳元兑人民币,用于澳大利亚留学、工资和生活费换算。澳元的 $ 不是美元。今天 1 澳元约合 {rate} 元,100 澳元约合 {r100} 元。看报价时先确认货币代码是 AUD。",
    ("CNY", "AUD"): "人民币换澳元,可以在交澳洲学费或付澳洲账单前先算人民币成本。今天 1 元约合 {rate} 澳元,1000 元约合 {r1000} 澳元。大额汇款看电汇价,这页给出的是不含点差的参考中间价。",
    ("CAD", "CNY"): "加元兑人民币,常见于加拿大留学费用和当地收入换回国内。加元也写成 $,不要按美元心算。今天 1 加元约合 {rate} 元,100 加元约合 {r100} 元。",
    ("CNY", "CAD"): "人民币换加元,用来估算去加拿大的预算,或给加拿大账户汇款。今天 1 元约合 {rate} 加元,1 加元约合 {rev} 元。办理时说明是加元(CAD),避免被做成美元。",
    ("SGD", "CNY"): "新加坡元兑人民币,是把新币工资、学费和生活费换回人民币时要看的汇率。今天 1 新元约合 {rate} 元,100 新元约合 {r100} 元。新元对人民币没有固定挂钩,汇款当天以银行牌价为准。",
    ("CNY", "SGD"): "人民币换新币,适合去新加坡旅游、探亲或交学费之前估算。今天 1 元约合 {rate} 新元,1000 元约合 {r1000} 新元。新加坡电子支付很普及,现钞可以少换,用这页先做预算。",
    ("THB", "CNY"): "泰铢兑人民币,用于把泰国旅行花费折回人民币,以及把泰铢现钞换回国内。今天 1 泰铢约合 {rate} 元,1000 泰铢约合 {r1000} 元。泰国小店和市场更认现金,可以按天数用这页估一个泰铢总额。",
    ("CNY", "THB"): "人民币换泰铢,是去泰国之前最实用的计算。今天 1 元约合 {rate} 泰铢,100 元约合 {r100} 泰铢。机场兑换方便但往往更贵,可以先用中间价做预算,再到市区比较牌价。",
    ("CHF", "CNY"): "瑞士法郎兑人民币,瑞郎币值高,少量瑞郎就对应一笔不小的人民币。今天 1 瑞郎约合 {rate} 元,100 瑞郎约合 {r100} 元。瑞士消费贵,用人民币做预算时按这页计算后再留一点余量。",
    ("CNY", "CHF"): "人民币换瑞士法郎,适合去瑞士旅行或支付瑞士账单前估算。今天 1 元约合 {rate} 瑞郎,1 瑞郎约合 {rev} 元。瑞郎现钞面值大,小额现金不必换太多。",
    ("NZD", "CNY"): "新西兰元兑人民币,用于新西兰留学学费和生活费折算。纽元符号也是 $,和美元、澳元不同。今天 1 纽元约合 {rate} 元,100 纽元约合 {r100} 元。",
    ("CNY", "NZD"): "人民币换新西兰元,可以在准备新西兰费用时先算人民币成本。今天 1 元约合 {rate} 纽元,1000 元约合 {r1000} 纽元。汇款币种选 NZD,不要选成澳元或美元。",
    ("USD", "EUR"): "美元兑欧元是国际汇市最常被引用的一对,也是欧美之间汇款、学费和货款的计价基准之一。今天 1 美元约合 {rate} 欧元,100 美元约合 {r100} 欧元。银行买入价和卖出价会分布在这个中间价两侧。",
    ("EUR", "USD"): "欧元兑美元,用于把欧元收入或欧洲账单折成美元。今天 1 欧元约合 {rate} 美元,100 欧元约合 {r100} 美元。本站其他货币对都由欧元交叉计算,这一对可以直接对照欧洲央行公布的美元汇率。",
    ("USD", "HKD"): "美元兑港币受联系汇率约束,1 美元长期大约在 7.75 到 7.85 港元之间,波动比其他货币小。今天 1 美元约合 {rate} 港元,100 美元约合 {r100} 港元。若看到明显偏离这个区间的牌价,先确认是不是含了较高手续费。",
    ("HKD", "USD"): "港币兑美元同样受联系汇率影响,1 港元大约是 1 美元的八分之一附近。今天 1 港元约合 {rate} 美元,1000 港元约合 {r1000} 美元。换美元现钞和电汇的价格不同,这页只给中间参考价。",
    ("USD", "JPY"): "美元兑日元是亚洲时段最活跃的汇率之一,日元数字通常远大于美元。今天 1 美元约合 {rate} 日元,100 美元约合 {r100} 日元。看新闻里的「美元日元」时,说的就是 1 美元兑换多少日元。",
    ("JPY", "USD"): "日元兑美元时,1 日元只值美元的一小部分,估算请看 10000 日元。今天 10000 日元约合 {r10000} 美元,1 日元约合 {rate} 美元。把日元汇成美元,银行会再扣一点差。",
    ("USD", "SGD"): "美元兑新加坡元,用于新币和美元之间的汇款、学费和投资换算。今天 1 美元约合 {rate} 新元,100 美元约合 {r100} 新元。新加坡的银行牌价通常直接挂美元,可以和这个中间价比较点差。",
    ("SGD", "USD"): "新加坡元兑美元,适合把新币收入换成美元,或估算美元账单要付多少新币。今天 1 新元约合 {rate} 美元,1000 新元约合 {r1000} 美元。新元不是盯住美元的,数字每天都会变。",
    ("EUR", "GBP"): "欧元兑英镑,用于英国和欧元区之间的旅行、学费和货款。今天 1 欧元约合 {rate} 英镑,100 欧元约合 {r100} 英镑。英国不使用欧元,在英国消费要换成英镑。",
    ("GBP", "EUR"): "英镑兑欧元,是从英国去欧洲大陆之前要看的汇率。今天 1 英镑约合 {rate} 欧元,100 英镑约合 {r100} 欧元。欧元区各国都收欧元,换一次就能在多个国家使用。",
    ("HKD", "SGD"): "港币兑新加坡元,适合香港和新加坡之间的旅行、汇款和购物。今天 1 港元约合 {rate} 新元,1000 港元约合 {r1000} 新元。两地都通行电子支付,现钞按这页少换一部分即可。",
    ("SGD", "HKD"): "新加坡元兑港币,用来估算在香港消费时新币大约值多少港元。今天 1 新元约合 {rate} 港元,100 新元约合 {r100} 港元。若银行没有直接牌价,往往会经美元折算,多一层点差。",
    ("SGD", "THB"): "新加坡元兑泰铢,是从新加坡去泰国玩之前的换算。今天 1 新元约合 {rate} 泰铢,100 新元约合 {r100} 泰铢。泰国小店更认泰铢现金,可以用这页先估几天的量,不够再换。",
    ("THB", "SGD"): "泰铢兑新加坡元,用于从泰国回到新加坡后把剩余泰铢折成新币,或比较两边物价。今天 1 泰铢约合 {rate} 新元,1000 泰铢约合 {r1000} 新元。泰铢换成新元的数字较小,核对时看清小数点。",
}


HOLD = {
    "CNY": "国内收款和日常开销",
    "USD": "跨境结算、留学缴费和保留美元",
    "EUR": "欧元区旅行和欧洲账单",
    "JPY": "日本旅游现金和日元汇款",
    "HKD": "在香港消费和港币汇款",
    "GBP": "英国学费和生活费",
    "KRW": "韩国旅游和韩元标价购物",
    "AUD": "澳大利亚学费和当地开销",
    "CAD": "加拿大学费和当地开销",
    "SGD": "在新加坡消费和新币收入",
    "THB": "泰国旅行时的泰铢现金",
    "MYR": "马来西亚的工资、物价和汇款",
    "CHF": "瑞士旅行和瑞郎账单",
    "NZD": "新西兰学费和当地开销",
}

FACTS = {
    "CNY": "人民币按元计算即可,没有需要另外换算的辅币单位。",
    "USD": "美元是很多银行牌价的桥梁货币,现汇和现钞往往不是同一个价。",
    "EUR": "欧元现钞在欧元区通用,本站其他汇率也是相对欧元交叉算出的。",
    "JPY": "日元最小单位就是 1 日元,换算结果可以四舍五入到整数再用。",
    "HKD": "港币对美元有联系汇率,对其他货币则会跟着美元一起波动。",
    "GBP": "英镑 1 镑等于 100 便士,币值通常高于等面额的美元。",
    "KRW": "韩元数值很大,对比时看 1000 或 10000 韩元,避免数错零。",
    "AUD": "澳元常以 $ 标价,和美元、加元、新西兰元不是同一种货币。",
    "CAD": "加元也使用 $ 符号,换汇时要确认是 CAD 而不是美元。",
    "SGD": "新加坡元是新加坡的法定货币,和新马过关、在坡消费直接相关。",
    "THB": "泰铢现金在泰国小店更常用,不能默认到处都能刷卡。",
    "MYR": "马来西亚林吉特俗称马币,1 林吉特等于 100 仙。",
    "CHF": "瑞士法郎币值高,少量瑞郎就对应一笔不小的其他货币。",
    "NZD": "新西兰元的符号也是 $,不要和澳元或美元混用。",
}


def pair_intro(a, b, now, date):
    ctx = {
        "date": date,
        "rate": fmt(now),
        "r100": fmt(100 * now),
        "r1000": fmt(1000 * now),
        "r10000": fmt(10000 * now),
        "rev": fmt(1 / now),
    }
    custom = PAIR_INTRO.get((a, b))
    if custom:
        return custom.format(**ctx)
    return generated_pair_intro(a, b, now, ctx)


def generated_pair_intro(a, b, now, ctx):
    na, nb = name(a), name(b)
    if now >= 1:
        scale = f"1 {na}今天大约能换 {ctx['rate']} {nb},多于 1 {nb}。"
    elif now >= 0.01:
        scale = f"1 {na}今天大约换 {ctx['rate']} {nb},不到 1 {nb},看结果时注意小数点。"
    else:
        scale = f"1 {na}只约合 {ctx['rate']} {nb},数字很小,估算时直接看 100 {na}(约 {ctx['r100']} {nb})更直观。"
    use = f"把{na}换成{nb},多半是为了{HOLD[b]}。{na}本身多用于{HOLD[a]}。"
    if a != "USD" and b != "USD":
        bridge = f"不少银行不直接挂{na}兑{nb},而是经美元折算,多一次兑换就多一层点差。"
    else:
        bridge = f"银行会分开标{na}的买入价和卖出价,两边都偏离这个中间价。"
    close = f"100 {na}约合 {ctx['r100']} {nb},反过来 1 {nb}约合 {ctx['rev']} {na}。"
    n = (ord(a[0]) + ord(b[-1])) % 3
    if n == 0:
        return scale + FACTS[a] + use + close
    if n == 1:
        return use + scale + FACTS[b] + bridge
    return scale + FACTS[b] + bridge + close


def pair_page(cfg, dates, rates, a, b):
    series = [cross(rates[d], a, b) for d in dates]
    now, prev = series[-1], series[-2] if len(series) > 1 else series[-1]
    na, nb = name(a), name(b)
    unit_b = NAMES.get(b, (b, b))[1]
    intro = pair_intro(a, b, now, dates[-1])
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
<div class="muted">更新日期 {dates[-1]} · 较上一交易日 {change_html(now, prev)} · 1 {nb} = {fmt(1 / now)} {na}</div>
<p>{esc(intro)}</p></div>
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
<div class="card"><h2>实用计算器</h2><div class="links"><a href="/fangdai/">房贷计算器(等额本息/本金)</a><a href="/geshui/">工资个税计算器</a><a href="/nianzhongjiang/">年终奖个税计算器</a><a href="/cunkuan/">存款利息计算器</a><a href="/dingtou/">基金定投/复利计算器</a><a href="/tiqian/">提前还贷计算器</a><a href="/gongjijin/">公积金贷款计算器</a></div></div>
<div class="card"><h2>全部货币对</h2><div class="links">{allpairs}</div></div>"""
    return f"今日汇率查询 - 人民币汇率换算({dates[-1]})", f"实时查询美元、欧元、日元、港币等{len(cfg['currencies'])}种货币兑人民币汇率,提供在线换算与走势,每日自动更新。", body


# ---------- 构建 ----------

def write(cfg, path, page, urls):
    title, desc, body = page
    f = OUT / path.strip("/") / "index.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    # 站点部署在子路径下(如 github.io/huilv-site)时,给站内链接加前缀
    prefix = urllib.parse.urlparse(cfg["base_url"]).path.rstrip("/")
    page_html = layout(cfg, title, desc, path, body, page_graphs(cfg, path, body)).replace('href="/', f'href="{prefix}/')
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
    for path, page in finance.pages(cfg, ad_slot(cfg)):
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
