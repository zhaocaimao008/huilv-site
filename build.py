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
    if path in ("/about.html", "/contact.html"):
        return home + [("关于本站" if path == "/about.html" else "联系我们", path)]
    if parts[0] == "guide":
        if len(parts) == 1:
            return home + [("指南文章", path)]
        if len(parts) == 2:
            return home + [("指南文章", "/guide/"), (GUIDE_TITLES[parts[1]], path)]
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
<footer><nav><a href="/">首页</a><a href="/">汇率换算</a><a href="/fangdai/">房贷计算器</a><a href="/guide/">指南文章</a><a href="/about.html">关于本站</a><a href="/contact.html">联系我们</a><a href="/privacy/">隐私政策</a></nav>
<p>汇率数据来源:欧洲央行(ECB)参考汇率,每个工作日更新。房贷、个税计算结果按公开公式估算。本站所有数据仅供参考,不构成任何建议,实际以银行、税务机关为准。{network_html(cfg)}</p>
<p>© {dt.date.today().year} {esc(cfg["site_name"])}({esc(urllib.parse.urlparse(cfg["base_url"]).netloc)})版权所有。</p></footer>
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
    guide_links = "".join(
        f'<p><a href="/guide/{g["slug"]}/">{esc(g["title"])}</a><br><span class="muted">{esc(g["summary"])}</span></p>'
        for g in GUIDE_ARTICLES)
    body = f"""
<div class="card"><h1>今日汇率查询与换算</h1><p class="muted">数据日期 {dates[-1]},每个工作日自动更新。</p>
<table><tr><th>币种</th><th>1 单位兑{name(h)}</th><th>涨跌</th></tr>{rows}</table></div>
{ad_slot(cfg)}
<div class="card"><h2>实用计算器</h2><div class="links"><a href="/fangdai/">房贷计算器(等额本息/本金)</a><a href="/geshui/">工资个税计算器</a><a href="/nianzhongjiang/">年终奖个税计算器</a><a href="/cunkuan/">存款利息计算器</a><a href="/dingtou/">基金定投/复利计算器</a><a href="/tiqian/">提前还贷计算器</a><a href="/gongjijin/">公积金贷款计算器</a></div></div>
<div class="card"><h2>关于本站</h2>
<p>今日汇率换算(718168.com)是一个免费的在线金融工具站,主要做三件事:一是查询 14 种常用货币兑人民币的今日汇率并在线换算,数据来自欧洲央行参考汇率,每个工作日自动更新;二是提供房贷、公积金贷款、个税、年终奖个税、存款利息、定投复利、提前还贷等常用计算器,打开网页就能算,不用下载 App、不用注册;三是整理换汇、房贷、跨境收款方面的实用指南文章,帮你在动手花钱之前先把规则和费用弄明白。所有计算都在你的浏览器里完成,本站不收集你输入的金额。更详细的站点说明、数据来源和免责声明,见<a href="/about.html">关于本站</a>页。</p></div>
<div class="card"><h2>工具使用说明</h2>
<p>查汇率:在上方表格里找到目标币种,点进去能看到该货币对的在线换算器、近 30 日走势图、常用金额对照表和历史汇率,想反着换(比如林吉特换回人民币)页面里也有反向对照表。算贷款或个税:从「实用计算器」里选对应工具,填入金额、利率和年限即可,结果会即时算出月供、总利息等关键数字。要特别提醒的是:本站展示的是中间参考价,银行和兑换点的买入价、卖出价会在此基础上加减点差,实际成交以对方报价为准;换汇前建议先读一读指南里的《汇率是怎么定的》,把中间价、买入价、卖出价的区别弄清,比价时就不吃亏。</p></div>
<div class="card"><h2>实用指南</h2>
{guide_links}
<p><a href="/guide/">查看全部指南文章</a></p></div>
<div class="card"><h2>全部货币对</h2><div class="links">{allpairs}</div></div>"""
    return f"今日汇率查询 - 人民币汇率换算({dates[-1]})", f"实时查询美元、欧元、日元、港币等{len(cfg['currencies'])}种货币兑人民币汇率,提供在线换算与走势,每日自动更新。", body



# ---------- 指南文章与信息页 ----------

GUIDE_ARTICLES = [
    {
        "slug": "cny-myr-best-way",
        "title": "人民币换马来西亚林吉特怎样最划算",
        "summary": "银行、持牌兑换商、跨境汇款平台和到当地刷卡取现,四种渠道的真实成本对比,以及大额、小额的不同换法。",
        "desc": "人民币换马来西亚林吉特哪个渠道最划算?对比银行、持牌兑换商、跨境汇款平台和当地刷卡取现的点差与费用,给出按金额和用途选择的建议。",
        "body": """
<div class="card"><h2>先算清楚:换汇的真实成本是什么</h2>
<p>不管去马来西亚旅游、留学、置业还是做生意,换马币(马来西亚林吉特,代码 MYR)之前,先要明白一件事:换汇的成本不只是手续费,还包括汇率点差。同样换 1 万人民币,不同渠道最后到手的林吉特能差出几十甚至上百林吉特。判断哪个渠道划算,不要只看它宣传的"零手续费",而要把实际到手的林吉特金额,拿来和按当日中间价能换到的金额对比,差得越少越划算。本站的<a href="/cny-myr/">人民币兑林吉特汇率页</a>展示的就是中间参考价和换算器,先在那里把你的金额按中间价算一遍,心里有个"理想值",再去对比各家报价。</p></div>
<div class="card"><h2>渠道一:银行柜台与手机银行</h2>
<p>通过国内银行或马来西亚本地银行换汇,优点是安全、正规、适合大额,换汇记录完整,需要证明资金来源时拿得出手。缺点是点差通常不算小:人民币兑林吉特属于相对小众的货币对,不少银行不直接挂牌,而是先把人民币换成美元、再换成林吉特,多一次折算就多一层点差。操作之前,先在手机银行里看实际成交价(不是牌价表上的中间价),并问清有没有额外的电汇费、手续费。金额较大时,比如交学费、付房款定金,银行渠道仍是首选,贵一点买的是安全和可追溯。</p></div>
<div class="card"><h2>渠道二:持牌货币兑换商</h2>
<p>在吉隆坡市区,大型商场和华人聚居区里有不少持牌货币兑换商(Money Changer),它们的人民币兑林吉特点差经常比银行更小,现金当场点清、即时到手,换几千人民币的旅游现金很合适。注意事项有三点:一是只选有营业执照、明码标价的门店,进门先看报价屏;二是相邻几家报价也会有差别,顺路比两三家再换;三是大额现金随身有安全风险,携带超过海关规定额度的现金出入境还要依法申报,不要为了省一点点差去冒大风险。</p></div>
<div class="card"><h2>渠道三:跨境汇款与线上换汇平台</h2>
<p>如果钱不需要以现金形式出现,而是要从国内账户转到马来西亚账户(交学费、付房租、给家人汇生活费),可以考虑银行跨境汇款或持牌的线上跨境汇款平台。线上平台的报价通常更接近中间价,收费方式是"汇率加点 + 一笔固定费用",下单前就能看到最终到手金额,到账时间从几分钟到一两个工作日不等。银行电汇则胜在额度与合规记录,费用结构相对复杂一些,这类方式的详细对比可以看本站的<a href="/guide/cross-border-payment-compare/">跨境收款方式对比</a>。无论用哪一种方式,收款人的姓名拼写、账号和银行代码都要反复核对,填错退汇既慢又要扣费。</p></div>
<div class="card"><h2>渠道四:到了当地刷卡和取现</h2>
<p>人已经到了马来西亚,现金不够时可以直接刷卡,或用银联卡在 ATM 取林吉特,汇率按当日国际卡组织汇率结算,通常不差。要注意两个细节:一是 ATM 取现可能有发卡行的境外取现手续费,部分本地 ATM 还会加收一笔固定费用,取现前屏幕会提示金额,先看清再确认;二是刷卡时如果收银员或机器问你"以人民币还是林吉特结算",一定选林吉特结算,选人民币就是所谓的动态货币转换(DCC),它用的汇率往往明显吃亏。</p></div>
<div class="card"><h2>结论:按金额和用途选渠道</h2>
<p>小额旅游现金:到当地找持牌兑换商,或出发前在银行先换少量应急;中等金额、需要进银行账户的:优先比较线上跨境平台和手机银行的实际成交价;大额、涉及学费房款的:走银行正规渠道并保留全部凭证。另外,林吉特汇率每天都在动,金额较大的时候可以分两三次换,平摊波动。换汇的基本概念如果还不清楚,建议先读<a href="/guide/how-exchange-rate-works/">《汇率是怎么定的》</a>,再回来比价会更有数。</p></div>
<div class="card"><h2>常见问题</h2>
<p><b>人民币在马来西亚好换吗?</b><br>好换。吉隆坡等大城市的持牌兑换商普遍受理人民币,银行和机场也有兑换点,只是机场的点差通常最大,只建议在那里换少量应急。</p>
<p><b>换马币是提前在国内换好,还是到了再换?</b><br>两种都可以。国内银行的林吉特现钞不是每家网点都有备货,可能需要预约;到了吉隆坡市区再换,选择更多、点差往往更小。稳妥的做法是国内先换少量,其余到市区再换。</p></div>""",
    },
    {
        "slug": "how-exchange-rate-works",
        "title": "汇率是怎么定的:中间价、买入价、卖出价的区别",
        "summary": "中间价从哪来、银行的买入价和卖出价为什么永远不一样、现汇价为什么比现钞价好,一篇讲清。",
        "desc": "中间价、银行买入价、卖出价、现汇价和现钞价到底是什么意思?一篇讲清汇率的形成与点差,教你判断换汇报价贵不贵。",
        "body": """
<div class="card"><h2>汇率到底在说什么</h2>
<p>汇率就是两种货币之间的兑换比例。本站的写法是"1 单位外币 = 多少人民币",比如在<a href="/usd-cny/">美元兑人民币汇率页</a>看到 1 美元约等于 7.2 元人民币,意思就是拿 1 美元可以换到约 7.2 元人民币。国际上有直接标价和间接标价两种习惯,数字大小本身没有好坏之分,看的时候先确认"谁在前、谁在后",再去比较涨跌,就不会被小数点绕晕。做跨境生意、留学缴费的人,养成先确认标价方向的习惯,能避免最常见的算反事故。</p></div>
<div class="card"><h2>中间价:大家参考的那把"尺子"</h2>
<p>你在新闻里看到的"人民币对美元中间价",是中国外汇交易中心根据做市商报价计算、由中国人民银行授权公布的,工作日每天上午更新一次,是当天银行间外汇市场交易的参考基准。本站展示的则是欧洲央行(ECB)发布的参考汇率:欧洲央行每个工作日根据市场行情公布主要货币对欧元的参考价,我们再交叉计算出各货币兑人民币的价格。两种口径不同,数值接近但不会完全一样。中间价的作用是当一把"尺子":它本身一般不是你能成交的价格,而是用来判断某个报价到底贵还是便宜。</p></div>
<div class="card"><h2>买入价和卖出价:站在银行的角度看</h2>
<p>去银行换汇,牌价表上总有买入价、卖出价两列,很多人第一眼就糊涂。诀窍是:这两个价格都是站在银行角度说的。"买入价"是银行向你买入外币的价格——你拿着美元去换人民币,银行按买入价收;"卖出价"是银行卖出外币的价格——你拿人民币买美元,就按卖出价成交。买入价永远低于卖出价,中间的差额叫"点差",是银行做兑换生意的收入来源之一。所以在同一时刻,你换进和换出的价格天然不一样,这不是银行算错了,而是兑换这门生意的规则。</p></div>
<div class="card"><h2>现汇价和现钞价为什么不同</h2>
<p>仔细看牌价表,还会分成"现汇买入价"和"现钞买入价":账户里的外币(现汇)卖给银行,价格更好;拿着外币纸币(现钞)去卖,价格更低。原因很实际:纸币对银行来说有清点、保管、运输和回存境外的成本,而且外币现钞不能直接进入银行间市场流通。所以同样是 100 美元,放在账户里划转,比揣在兜里更"值钱"。出国回来剩下的外币硬币和小额纸币,很多银行干脆不收,也是同样的道理:处理成本比面值还高。</p></div>
<div class="card"><h2>为什么你实际换到的总比"汇率"差</h2>
<p>把上面几条连起来就明白了:新闻和本站给的是中间价,你实际成交用的是买入价或卖出价,中间隔着点差;如果是现钞,还要再让一层;通过平台换汇,可能再加一笔固定手续费。所以判断贵贱的正确姿势是:先在本站首页查中间价,再看对方的实际成交价,两者的差距在千分之几以内算很良心,差到百分之几,就值得多比几家了。想看某种货币最近是涨是跌,用各币种页面的近 30 日走势图,比单看某一天的价格靠谱得多。</p></div>
<div class="card"><h2>常见问题</h2>
<p><b>汇率涨了,是人民币升值还是贬值?</b><br>要看标价方式。按本站"1 美元 = X 人民币"的写法,X 变大说明同样 1 美元能换到更多人民币,是人民币相对贬值;X 变小,才是人民币升值。</p>
<p><b>为什么不同网站查到的汇率不一样?</b><br>数据源和更新时间不同:有的用央行中间价,有的用银行间市场实时价,有的直接用银行自己的牌价。相差零点几个百分点属于正常现象,先确认对方用的是哪种口径,再做比较。</p></div>""",
    },
    {
        "slug": "malaysia-mortgage-guide",
        "title": "马来西亚房贷怎么算:利率、成数与月供计算",
        "summary": "外国人买房的贷款成数、SBR 浮动利率结构、等额本息月供公式,加上印花税、律师费这些容易漏算的成本。",
        "desc": "在马来西亚买房贷款要先懂:外国人贷款成数、浮动利率(SBR)结构、等额本息月供公式、印花税和律师费等附加成本,以及申请注意事项。",
        "body": """
<div class="card"><h2>先弄清两个概念:成数和利率</h2>
<p>在马来西亚买房办贷款,先要分清"贷款成数"和"利率"两件事。成数指银行最多愿意借给你房价的几成:本地首套房买家常见可贷到九成,而外国买家的成数通常低不少,多数银行给到五至七成,具体看收入、签证类型和房产所在州的政策——也就是说,外国人买房要准备更多的首付现金。利率方面,马来西亚房贷以浮动利率为主流:实际利率 = 基准利率(各银行公布的标准化基准利率 SBR)+ 银行利差,基准会随马来西亚国家银行的隔夜政策利率(OPR)调整而动,所以月供在未来年份有可能随基准变化,这一点和国内的 LPR 加点形式颇为类似。</p></div>
<div class="card"><h2>月供怎么算:等额本息公式</h2>
<p>马来西亚房贷的月供算法,和国内通用的等额本息是同一套公式:每月还款额 = 贷款本金 × 月利率 × (1 + 月利率)^还款月数 ÷ [(1 + 月利率)^还款月数 − 1],其中月利率 = 年利率 ÷ 12。本站的<a href="/fangdai/">房贷计算器</a>用的就是这个公式:把你看中的房价、预计成数和银行给的利率填进去(贷款额按林吉特计、年限常见 30 至 35 年),先算出月供的量级,再判断压力大不大。注意浮动利率下算出的只是"当前利率下的月供",基准上调时月供会跟着变,做预算时最好按利率上浮 1 个百分点再测算一遍,留出安全垫。</p></div>
<div class="card"><h2>除了月供,还要准备哪些钱</h2>
<p>买房的一次性成本常被低估。除了首付,马来西亚购房通常还有:买卖合同与贷款合同的律师费、按阶梯计算的印花税(外国买家在部分州另有州政府批准费等安排)、房产估价费、土地局登记等杂费,再加上贷款期间银行一般会要求的房屋保险与抵押还款保险(MRTA / MLTA)。粗略的经验是,在首付之外再预留房价约 3%–5% 的现金来覆盖这些费用,比较稳妥;具体金额以律师的报价单为准,签字前逐项确认,别只盯着月供一个数字。</p></div>
<div class="card"><h2>申请流程和注意事项</h2>
<p>流程大致是:选房付定金 → 向银行提交贷款申请(需要护照、签证、收入证明与银行流水,先在马来西亚本地银行开好账户会方便很多)→ 银行批核并发出要约书 → 律师跟进合同与放款。几个容易踩的点:一是提前还款条款,各家对锁定期内罚息的规定不同,签约前问清;二是月供占收入的比例,银行审批时会看你的债务偿还比率(DSR),已有的其他贷款会影响批核额度;三是汇率风险——如果用人民币收入还林吉特月供,林吉特升值会直接抬高你的实际负担,可以用本站的<a href="/cny-myr/">人民币兑林吉特汇率页</a>长期跟踪走势,做到心里有数。最后提醒:本文是通用常识整理,各州政策与银行条款更新频繁,交易前请以执业律师和贷款银行的书面确认为准。</p></div>
<div class="card"><h2>常见问题</h2>
<p><b>外国人在马来西亚买房有最低价格门槛吗?</b><br>有。各州对外籍买家设有最低购房价格,多数州在 100 万林吉特上下,部分州或特定房产类型要求不同,并且需要州政府批准,买之前先让中介或律师确认目标房产是否符合条件。</p>
<p><b>马来西亚房贷可以提前还清吗?</b><br>一般可以,但不少贷款在最初几年设有锁定期,锁定期内提前结清或大额部分还款可能会收罚息,比例和年限各银行不同,签约时要在要约书里逐条看清。</p></div>""",
    },
    {
        "slug": "malaysia-travel-money",
        "title": "去马来西亚旅游换多少钱够用:现金与刷卡搭配",
        "summary": "按吉隆坡自由行的日均消费估预算,现金、刷卡、取现各占多少,以及机场别多换、刷卡别选人民币结算等避坑要点。",
        "desc": "去马来西亚旅游要带多少现金?按吉隆坡自由行的日均消费估算预算,给出现金、刷卡与 ATM 取现的搭配比例和避坑要点。",
        "body": """
<div class="card"><h2>先看消费场景:哪里必须用现金</h2>
<p>吉隆坡、槟城等大城市的商场、连锁餐厅和便利店,刷卡和扫码支付都很普及;但夜市、路边摊、老字号小吃店、部分出租车和城郊小店,仍然只收现金,或者扫码只认本地电子钱包。结论很简单:完全不带现金会寸步难行,带太多现金又不安全、还容易花不完。比较稳的搭配是:少量林吉特现金打底 + 一张可以境外使用的双币信用卡或银联卡 + 手机支付做备用,三者的大致比例如下文所说。</p></div>
<div class="card"><h2>先估预算:一天大概花多少</h2>
<p>以吉隆坡自由行为例(不含机票和酒店):吃小吃和本地餐馆、坐地铁轻轨,一天大约 80–150 林吉特可以过得不错;如果安排商场餐厅、景点门票和打车,一天 200–350 林吉特更现实;购物则另算。按天数乘好总预算之后,到本站的<a href="/cny-myr/">人民币兑林吉特汇率页</a>把林吉特总额换算成人民币,先对总账有概念;也可以直接看<a href="/cny-myr/1000/">1000 元人民币能换多少林吉特</a>这类金额页,快速建立直觉。预算里建议再加一成机动,遇到想吃的、想买的,不至于临时满街找 ATM。</p></div>
<div class="card"><h2>现金换多少、在哪里换</h2>
<p>经验做法是:按总预算的三分之一到一半准备现金,其余靠刷卡。以四天三晚的行程为例,现金带 600–1000 林吉特通常够用。另外还有两个常被忽略的现金场景:一是部分民宿和小型酒店入住时要收一笔现金押金,退房时返还,没现金会很被动;二是机场到市区的交通,如果坐巴士或在便利店给交通卡充值,小额现金最顺手。所以现金比例宁可略高一点,剩下的带回来再换掉,损失也有限。</p>
<p>换的地点很有讲究:机场兑换点最方便但点差最大,只换一两百林吉特应急即可;市区大型商场里的持牌兑换商价格好得多,适合在那里一次换齐,各渠道的详细对比见<a href="/guide/cny-myr-best-way/">《人民币换马来西亚林吉特怎样最划算》</a>。面额上多要一些 10、20、50 的小钞,100 的大钞在小摊经常找不开;硬币带回国基本换不掉,离境前优先把硬币花掉。</p></div>
<div class="card"><h2>刷卡和取现的注意事项</h2>
<p>刷卡时如果终端问你以人民币还是林吉特结算,选林吉特,让发卡行按国际卡组织的汇率换算,避免动态货币转换(DCC)那种明显偏高的汇率。银联卡在马来西亚主要银行的 ATM 上基本都能取林吉特,单笔和单日限额出发前在发卡行 App 里确认好,境外取现手续费也一并查清;取现时 ATM 若提示要加收一笔本地费用,先看清金额再决定是否继续。还有一条:出发前确认卡片的境外交易功能已经开通,或在银行 App 里做好境外用卡报备,免得第一笔消费就被风控拦下,站在收银台前尴尬。</p></div>
<div class="card"><h2>常见问题</h2>
<p><b>去马来西亚可以全程手机支付吗?</b><br>大城市的商场和连锁店基本没问题,但夜市、小吃摊和郊区仍然依赖现金或本地电子钱包,游客常用的境外支付工具在部分小店并不受理,带一些现金最稳妥。</p>
<p><b>林吉特没花完怎么办?</b><br>可以在回国前于机场或市区换回人民币,或者回国后在银行卖出;硬币银行一般不回收,建议在当地花掉。小额纸币留作下次旅行用也可以,林吉特是可自由兑换的货币,不必急着清零。</p></div>""",
    },
    {
        "slug": "cross-border-payment-compare",
        "title": "跨境收款方式对比:电汇、SWIFT 与第三方平台",
        "summary": "SWIFT 电汇的中间行扣费、SHA/OUR/BEN 的区别,对比第三方跨境收款平台的费率与到账时间,教你算净到手金额。",
        "desc": "跨境收款选 SWIFT 电汇还是第三方平台?对比两者的费用构成、中间行扣费、到账时间和适合人群,并教你计算净到手金额。",
        "body": """
<div class="card"><h2>场景不同,选法不同</h2>
<p>跨境收款常见于几种情况:在海外平台卖货的电商卖家、给境外客户提供服务的自由职业者、做外贸收客户货款的公司,以及在海外工作把收入汇回国内的个人。金额大小、收款频率和对方所在国家不同,最合适的方式也完全不同。下面把主流的两类方式——银行 SWIFT 电汇和第三方跨境收款平台——逐一拆开讲费用和速度,最后给一张对照表,方便你对号入座。</p></div>
<div class="card"><h2>方式一:银行 SWIFT 电汇</h2>
<p>SWIFT 电汇是最传统、覆盖面最广的方式:付款方在境外银行发起,资金经过一到数家中间行(代理行)转手,最终进入你的收款行账户。每多经手一家中间行,就可能被扣一笔中转费,常见每笔十几到几十美元,而且扣多少事先并不知道。费用承担方式有三种约定:SHA 是双方分担,中间费从本金中扣;OUR 是付款方全包,收款金额最可控但付款方成本最高;BEN 是收款方全担。到账时间一般 1–5 个工作日。SWIFT 的优点是正规、适合大额、凭证链完整;缺点是慢、费用不透明,小额收款时固定成本占比高得吓人。收款前务必向开户行问清你的 SWIFT Code、账户名英文拼写和收款路径要求,整套信息发给付款方,少走弯路。</p></div>
<div class="card"><h2>方式二:第三方跨境收款平台</h2>
<p>这类平台会为你开出多币种的海外本地收款账户,相当于在当地有一个"虚拟银行账号",客户用本地转账付款、免去国际电汇的层层中转,你再把余额结汇、提现到国内银行卡。费用多为按比例收取,常见在 1% 上下,部分平台有费率封顶或阶梯优惠,下单时页面会提前显示预计到手金额;到账速度通常比电汇快,快则当天、慢则两三天。这类方式适合电商平台回款、自由职业者定期收款这类"金额中等、频率较高"的场景。开通时需要完成企业或个人实名认证,并留意平台的提现限额、结汇额度和支持的币种与国家范围。</p></div>
<div class="card"><h2>对照表:一次看清差别</h2>
<div class="scroll"><table><tr><th>对比项</th><th>SWIFT 电汇</th><th>第三方平台</th></tr>
<tr><td>主要费用</td><td>汇出费 + 中间行扣费 + 入账费</td><td>按比例的服务费(下单时可预知)</td></tr>
<tr><td>到账时间</td><td>1–5 个工作日</td><td>当天至 3 个工作日</td></tr>
<tr><td>适合金额</td><td>大额、低频</td><td>中小额、高频</td></tr>
<tr><td>到手金额可预测性</td><td>较差(中间扣费不可见)</td><td>较好(下单即显示)</td></tr>
<tr><td>使用门槛</td><td>有银行账户即可</td><td>需在平台实名认证开户</td></tr></table></div>
<p class="muted">注:以上为一般情形的经验性对比,具体费率与时效以各银行、平台当期公示为准。</p></div>
<div class="card"><h2>算真实成本的方法</h2>
<p>比较任何收款方式,都不要只看对方宣传的费率,要算"净到手":先把应收的外币金额在本站按中间价换算成人民币,比如美元收款就用<a href="/usd-cny/">美元兑人民币汇率页</a>,得到理论最大值,再减去这种方式的全部费用和点差损失,剩下的才是真正进你口袋的钱。小额收款时,一笔 30 美元的固定扣费可能比 1% 的比例费贵得多;金额越大,比例费的权重越往上升。用这个办法把两种方式各算一遍,选哪家自然就清楚了。</p></div>
<div class="card"><h2>合规提醒</h2>
<p>跨境收款不是收到钱就完事:个人每年有等值 5 万美元的便利化结汇额度,超出额度或贸易性质的收款,需要按银行要求提供合同、发票等真实性材料;企业收款则要走对公账户并按外贸流程办理。无论用哪种方式,合同、发票、平台账单这些凭证都建议至少保存两年,需要的时候拿得出来,比省下一点手续费重要得多。本文只作常识梳理,具体业务请以开户银行和平台的最新规则为准。</p></div>
<div class="card"><h2>常见问题</h2>
<p><b>SWIFT 电汇到账为什么少了钱?</b><br>多半是被中间行扣了中转费:费用承担方式为 SHA 或 BEN 时,费用会直接从本金中扣除。下次可以请付款方选择 OUR 并写全收款信息,或者改走费用透明的平台。</p>
<p><b>第三方收款平台里的钱安全吗?</b><br>应选择持有相关支付牌照、运营时间较长的平台,完成实名认证并开启双重验证;大额资金到账后及时提现到自己的银行卡,不要让大额资金长期停留在平台账户里。</p></div>""",
    },
]

GUIDE_TITLES = {g["slug"]: g["title"] for g in GUIDE_ARTICLES}


def guide_index_page(cfg):
    cards = "".join(
        f'<div class="card"><h2><a href="/guide/{g["slug"]}/">{esc(g["title"])}</a></h2><p>{esc(g["summary"])}</p><p><a href="/guide/{g["slug"]}/">阅读全文</a></p></div>'
        for g in GUIDE_ARTICLES)
    body = f"""
<div class="card"><h1>实用指南</h1>
<p>换汇、买房贷款、出国旅游花钱、跨境做生意收款,这些事看起来简单,真动手时全是细节:点差怎么算、哪种渠道便宜、月供会不会随利率变、收款为什么少了一截。下面是我们围绕本站工具整理的原创指南,每篇都对应着站内能直接动手算的工具,建议先读文章弄清规则,再回到工具页动手算一遍。</p></div>
{cards}"""
    return "实用指南 - 换汇、房贷与跨境收款常识", "人民币换汇渠道对比、汇率基础知识、马来西亚房贷与旅游换钱、跨境收款方式对比等原创指南文章,配合本站换算器与计算器一起使用。", body


def guide_article_page(cfg, g):
    others = "".join(
        f'<p><a href="/guide/{o["slug"]}/">{esc(o["title"])}</a></p>'
        for o in GUIDE_ARTICLES if o["slug"] != g["slug"])
    body = f"""
<div class="card"><h1>{esc(g["title"])}</h1>
<p class="muted">分类:<a href="/guide/">实用指南</a> · 本站原创,内容仅供参考,不构成任何建议。</p>
<p>{esc(g["summary"])}</p></div>
{g["body"]}
<div class="card"><h2>更多指南</h2>
{others}
<p><a href="/guide/">查看全部指南文章</a></p></div>"""
    return g["title"], g["desc"], body


def about_page(cfg):
    body = """
<div class="card"><h1>关于本站</h1>
<p>今日汇率换算(718168.com)是一个免费的在线金融工具网站,站如其名,主要帮你解决三件事:查汇率、算贷款和税费、补常识。</p>
<p>第一,汇率查询与换算:本站提供美元、欧元、日元、港币、马来西亚林吉特等 14 种常用货币兑人民币的今日汇率、在线换算器、近 30 日走势图和常用金额对照表,覆盖全部 182 个货币对页面。第二,常用计算器:<a href="/fangdai/">房贷计算器</a>、<a href="/gongjijin/">公积金贷款计算器</a>、<a href="/geshui/">工资个税计算器</a>、<a href="/nianzhongjiang/">年终奖个税计算器</a>、<a href="/cunkuan/">存款利息计算器</a>、<a href="/dingtou/">定投复利计算器</a>和<a href="/tiqian/">提前还贷计算器</a>,所有计算都在你的浏览器本地完成,不用注册、不用下载 App。第三,实用指南:我们在<a href="/guide/">指南栏目</a>持续整理换汇渠道、房贷常识、旅游用钱和跨境收款方面的原创文章,帮你在花钱之前先把规则弄明白。</p></div>
<div class="card"><h2>数据来源与更新</h2>
<p>本站汇率数据来自欧洲央行(ECB)发布的参考汇率(通过 Frankfurter 公开接口获取),每个工作日自动更新一次;欧洲央行休市的日子,页面展示的是最近一个工作日的数据并标注日期。房贷、个税等计算器使用的利率与税率参数,取自公开的常见标准值并在相应页面中注明;政策调整后我们会跟随更新,但不能保证与你所在地区、所选银行的最新口径完全一致,请以官方发布为准。</p></div>
<div class="card"><h2>隐私与 Cookie</h2>
<p>本站是纯静态网站:你在计算器里输入的金额、利率等数字,只在你自己的浏览器里参与计算,不会上传、不会被保存,我们也无法看到。本站使用 Google AdSense 广告服务,Google 及其合作的第三方供应商可能会使用 Cookie,根据你此前访问本站或其他网站的情况投放广告;你可以在 Google 的广告设置页面选择停用个性化广告。本站的隐私政策页面见页脚链接。</p></div>
<div class="card"><h2>免责声明</h2>
<p>本站提供的汇率是中间参考价,不是任何银行或兑换机构的成交价格;计算器给出的结果按公开公式估算。所有数据与文章仅供一般信息参考,不构成投资、税务或法律方面的建议。涉及具体交易时,请以银行、兑换机构、税务机关及专业人士的书面确认为准;因使用本站信息产生的任何损失,本站不承担责任。</p></div>
<div class="card"><h2>联系我们</h2>
<p>发现数据错误、有想算但本站还没有的场景,或者有合作意向,欢迎通过<a href="/contact.html">联系页</a>的邮箱联系我们。</p></div>"""
    return "关于本站 - 今日汇率换算", "今日汇率换算(718168.com)的站点介绍:提供汇率查询换算、房贷个税等计算器与实用指南;含数据来源说明、隐私与 Cookie 说明和免责声明。", body


def contact_page(cfg):
    body = """
<div class="card"><h1>联系我们</h1>
<p>有任何问题或建议,欢迎发邮件联系我们:</p>
<p>邮箱:<a href="mailto:chatporttop@proton.me">chatporttop@proton.me</a></p>
<p>以下情况尤其欢迎来信:</p>
<ul>
<li>发现某个页面的汇率、计算结果或文章内容有错误;</li>
<li>你有想算但本站还没有的场景(某种贷款、某种税费),希望我们加上;</li>
<li>对指南文章的纠错与补充,或者内容合作意向。</li>
</ul>
<p class="muted">我们一般会在两个工作日内回复。来信时请尽量写清页面地址和问题描述,方便我们定位。本站不通过电话、微信等方式提供客服,也不会以任何名义向你收取费用或索要账户、密码,谨防冒充。</p>
<p>关于本站的数据来源与免责声明,见<a href="/about.html">关于本站</a>。</p></div>"""
    return "联系我们 - 今日汇率换算", "今日汇率换算(718168.com)联系方式:数据纠错、功能建议与内容合作,请发送邮件至 chatporttop@proton.me。", body


def write_file(cfg, path, page, urls):
    """生成根目录下的单文件页面(如 /about.html),走与 write() 相同的模板处理。"""
    title, desc, body = page
    prefix = urllib.parse.urlparse(cfg["base_url"]).path.rstrip("/")
    page_html = layout(cfg, title, desc, path, body, page_graphs(cfg, path, body)).replace('href="/', f'href="{prefix}/')
    (OUT / path.strip("/")).write_text(page_html, encoding="utf-8")
    urls.append(path)

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
    # 游戏:把仓库 game/ 目录原样复制到 dist/game/
    game_src = ROOT / "game"
    if game_src.is_dir():
        shutil.copytree(game_src, OUT / "game", dirs_exist_ok=True)
        urls.append("/game/")
    # 隐私政策页:把仓库 privacy/ 目录原样复制到 dist/privacy/
    privacy_src = ROOT / "privacy"
    if privacy_src.is_dir():
        shutil.copytree(privacy_src, OUT / "privacy", dirs_exist_ok=True)
        urls.append("/privacy/")
    write(cfg, "/", home_page(cfg, dates, rates), urls)
    for path, page in calc.pages(cfg, ad_slot(cfg)):
        write(cfg, path, page, urls)
    for path, page in finance.pages(cfg, ad_slot(cfg)):
        write(cfg, path, page, urls)
    write(cfg, "/guide/", guide_index_page(cfg), urls)
    for g in GUIDE_ARTICLES:
        write(cfg, f"/guide/{g['slug']}/", guide_article_page(cfg, g), urls)
    write_file(cfg, "/about.html", about_page(cfg), urls)
    write_file(cfg, "/contact.html", contact_page(cfg), urls)
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
