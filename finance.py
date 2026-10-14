"""金融计算器:定期存款利息、基金定投/复利、提前还贷、公积金贷款。

pages(cfg, ad) 依次产出 (路径, (标题, 描述, 正文)),由 build.py 写入 dist/。
利率均为页面可修改的示例值,在 config.json 的 finance 中设置。
"""
import math

from calc import bx, bj, bx_schedule, money, mortgage_form, yuan

DISCLAIMER = '<p class="muted">计算结果仅供参考,实际以银行、公积金中心或产品合同为准。本站不提供任何投资建议。</p>'


def wan(n):
    return f"{n:g}万"


# ---------- 定期存款 ----------

DEPOSIT_JS = """<script>(function(){var $=function(i){return document.getElementById(i)},f=function(x){return x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})};
function run(){var P=+$('d-p').value*10000,r=+$('d-r').value/100,y=+$('d-y').value;if(!(P>0&&y>0))return;var i=P*r*y;
$('d-out').innerHTML='<div>到期利息<b>'+f(i)+'</b></div><div>本息合计<b>'+f(P+i)+'</b></div><div>平均每月利息<b>'+f(i/y/12)+'</b></div>'}
['d-p','d-r','d-y'].forEach(function(i){$(i).oninput=run});run();})();</script>"""


def deposit_form(p, y, r):
    opts = "".join(f'<option value="{v}"{" selected" if v == y else ""}>{v}年</option>' for v in (0.25, 0.5, 1, 2, 3, 5))
    return f"""<div class="card"><h2>定期存款利息计算器</h2><div class="form">
<label>存款金额(万元)<input id="d-p" type="number" inputmode="decimal" value="{p:g}"></label>
<label>存期<select id="d-y">{opts.replace('value="0.25"', 'value="0.25"').replace('>0.25年<', '>3个月<').replace('>0.5年<', '>6个月<')}</select></label>
<label>年利率(%)<input id="d-r" type="number" inputmode="decimal" step="0.01" value="{r}"></label>
</div><div class="res" id="d-out"></div>{DEPOSIT_JS}</div>"""


def deposit_hub(cfg, ad):
    fc = cfg["finance"]
    links = "".join(f'<a href="/cunkuan/{p:g}wan-{y}nian/">{wan(p)}存{y}年</a>' for p in fc["deposit_amounts_wan"] for y in fc["deposit_years"])
    body = f"""<div class="card"><h1>存款利息计算器(定期、整存整取)</h1>
<p class="muted">输入存款金额、存期和年利率,算出到期利息和本息合计。定期存款按单利计算:利息 = 本金 × 年利率 × 存期(年)。</p></div>
{deposit_form(10, 3, fc["deposit_default_rate"])}{ad}
<div class="card"><h2>常见存款利息速查</h2><div class="links">{links}</div>{DISCLAIMER}</div>"""
    return ("存款利息计算器2026 - 定期存款利息怎么算", "在线定期存款利息计算器,输入本金、存期、年利率,计算到期利息和本息合计,附常见金额利息速查。", body)


def deposit_page(cfg, ad, p, y):
    fc = cfg["finance"]
    P, r = p * 10000, fc["deposit_default_rate"]
    interest = P * r / 100 * y
    rows = "".join(f"<tr><td>{rate}%</td><td>{money(P * rate / 100 * y)}</td><td>{money(P + P * rate / 100 * y)}</td><td>{money(P * rate / 100 / 12)}</td></tr>"
                   for rate in fc["deposit_rates"])
    years = "".join(f"<tr><td>{yy}年</td><td>{money(P * r / 100 * yy)}</td><td>{money(P + P * r / 100 * yy)}</td></tr>" for yy in (1, 2, 3, 5))
    other = "".join(f'<a href="/cunkuan/{q:g}wan-{y}nian/">{wan(q)}存{y}年</a>' for q in fc["deposit_amounts_wan"] if q != p)
    body = f"""<div class="card"><h1>{wan(p)}存{y}年定期利息多少?</h1>
<div class="big">利息 {money(interest)} 元</div>
<p class="muted">按年利率 {r}% 计算 · 到期本息合计 {money(P + interest)} 元 · 计算方法:{P:,.0f} × {r}% × {y} = {money(interest)}</p></div>
{ad}
<div class="card"><h2>不同利率下的利息</h2><div class="scroll"><table><tr><th>年利率</th><th>{y}年总利息</th><th>本息合计</th><th>每月利息</th></tr>{rows}</table></div>
<p class="muted">各银行、各期限的存款利率不同,大型银行一般低于中小银行,请以存款银行公布的利率为准。</p></div>
<div class="card"><h2>{wan(p)}存不同年限(年利率 {r}%)</h2><table><tr><th>存期</th><th>利息</th><th>本息合计</th></tr>{years}</table></div>
{deposit_form(p, y, r)}
<div class="card"><h2>常见问题</h2><p><b>定期存款利息怎么算?</b><br>整存整取定期存款按单利计算,到期一次性支付:利息 = 本金 × 年利率 × 存期。例如 {wan(p)}元按 {r}% 存 {y} 年,利息为 {money(interest)} 元。</p>
<p><b>提前支取有利息吗?</b><br>定期存款提前支取的部分,一般按支取当天的活期利率计息,利息会少很多。</p>{DISCLAIMER}</div>
<div class="card"><h2>其他金额</h2><div class="links">{other}</div></div>"""
    return (f"{wan(p)}存{y}年定期利息多少 - {wan(p)}存款利息计算(2026)",
            f"{wan(p)}元存{y}年定期,按年利率{r}%计算利息{money(interest)}元,本息合计{money(P + interest)}元。附不同利率利息对照表。", body)


# ---------- 定投 / 复利 ----------

def dingtou_fv(m, years, rate):
    """每月月末投入 m 元,年化收益 rate%,按月复利,返回期末总资产。"""
    i, n = rate / 1200, years * 12
    return m * n if i == 0 else m * ((1 + i) ** n - 1) / i


INVEST_JS = """<script>(function(){var $=function(i){return document.getElementById(i)},f=function(x){return x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})};
function run(){var a=+$('v-a').value||0,m=+$('v-m').value||0,y=+$('v-y').value,i=+$('v-r').value/1200,n=y*12;if(!(n>0))return;
var g=Math.pow(1+i,n),fv=a*g+(i?m*(g-1)/i:m*n),c=a+m*n;
$('v-out').innerHTML='<div>期末总资产<b>'+f(fv)+'</b></div><div>累计投入<b>'+f(c)+'</b></div><div>收益<b>'+f(fv-c)+'</b></div>'}
['v-a','v-m','v-y','v-r'].forEach(function(i){$(i).oninput=run});run();})();</script>"""


def invest_form(a, m, y, r):
    return f"""<div class="card"><h2>定投 / 复利计算器</h2><div class="form">
<label>初始投入(元)<input id="v-a" type="number" inputmode="decimal" value="{a}"></label>
<label>每月定投(元)<input id="v-m" type="number" inputmode="decimal" value="{m}"></label>
<label>投资年限<input id="v-y" type="number" inputmode="decimal" value="{y}"></label>
<label>假设年化收益率(%)<input id="v-r" type="number" inputmode="decimal" step="0.1" value="{r}"></label>
</div><div class="res" id="v-out"></div>{INVEST_JS}
<p class="muted">按月复利、每月月末投入计算。收益率为假设值,基金、股票等投资的实际收益有波动,可能亏损。</p></div>"""


def invest_hub(cfg, ad):
    fc = cfg["finance"]
    links = "".join(f'<a href="/dingtou/{m}-{y}nian/">每月{m}元定投{y}年</a>' for m in fc["dingtou_monthly"] for y in fc["dingtou_years"])
    body = f"""<div class="card"><h1>基金定投计算器 / 复利计算器</h1>
<p class="muted">输入每月定投金额、年限和假设年化收益率,计算期末总资产和收益;也可以只填初始投入,当作一次性投资的复利计算器。</p></div>
{invest_form(0, 1000, 10, fc["dingtou_rates"][1])}{ad}
<div class="card"><h2>复利公式</h2><p>一次性投入:期末金额 = 本金 × (1 + 月收益率)<sup>月数</sup>。</p>
<p>每月定投:期末金额 = 每月金额 × [(1 + 月收益率)<sup>月数</sup> − 1] ÷ 月收益率。月收益率 = 年化收益率 ÷ 12。</p></div>
<div class="card"><h2>定投收益速查</h2><div class="links">{links}</div>{DISCLAIMER}</div>"""
    return ("基金定投计算器 - 复利计算器(每月定投收益计算)", "在线基金定投收益计算器和复利计算器,输入每月定投金额、年限、年化收益率,计算期末资产和收益。", body)


def invest_page(cfg, ad, m, y):
    fc = cfg["finance"]
    cost = m * 12 * y
    rows = "".join(f"<tr><td>{r}%</td><td>{money(dingtou_fv(m, y, r))}</td><td>{money(dingtou_fv(m, y, r) - cost)}</td></tr>" for r in fc["dingtou_rates"])
    mid = fc["dingtou_rates"][1]
    fv = dingtou_fv(m, y, mid)
    yearly = "".join(f"<tr><td>第{k}年</td><td>{money(m * 12 * k)}</td><td>{money(dingtou_fv(m, k, mid))}</td></tr>" for k in range(1, y + 1) if k <= 5 or k % 5 == 0)
    other = "".join(f'<a href="/dingtou/{mm}-{yy}nian/">每月{mm}元定投{yy}年</a>' for mm in fc["dingtou_monthly"] for yy in fc["dingtou_years"] if (mm, yy) != (m, y))
    body = f"""<div class="card"><h1>每月定投{m}元,{y}年后有多少钱?</h1>
<div class="big">约 {money(fv)} 元</div>
<p class="muted">假设年化收益 {mid}%、按月复利 · 累计投入 {money(cost)} 元 · 收益 {money(fv - cost)} 元</p></div>
{ad}
<div class="card"><h2>不同收益率下的结果</h2><table><tr><th>假设年化收益</th><th>期末总资产</th><th>收益</th></tr>{rows}</table>
<p class="muted">收益率只是假设。基金、股票等投资收益不固定,历史收益不代表未来,可能亏损本金。</p></div>
<div class="card"><h2>逐年资产变化(年化 {mid}%)</h2><table><tr><th>年份</th><th>累计投入</th><th>总资产</th></tr>{yearly}</table></div>
{invest_form(0, m, y, mid)}{DISCLAIMER}
<div class="card"><h2>其他定投组合</h2><div class="links">{other}</div></div>"""
    return (f"每月定投{m}元{y}年后有多少钱 - 定投收益计算",
            f"每月定投{m}元,坚持{y}年累计投入{money(cost)}元,假设年化{mid}%约有{money(fv)}元。附不同收益率对照表和逐年资产变化。", body)


# ---------- 提前还贷 ----------

def prepay(P, years, rate, paid_years, x):
    """等额本息贷款在第 paid_years 年末提前还 x 元。返回 dict。"""
    i, n, k = rate / 1200, years * 12, paid_years * 12
    m, _ = bx(P, years, rate)
    bal = P * (1 + i) ** k - m * ((1 + i) ** k - 1) / i
    left = n - k
    old_interest = m * left - bal
    nb = bal - x
    # 方案一:月供不变,缩短期限
    months, b, interest1 = 0, nb, 0.0
    while b > 1e-6:
        it = b * i
        pay = min(m, b + it)
        interest1 += it
        b -= pay - it
        months += 1
    # 方案二:期限不变,减少月供
    m2 = nb * i * (1 + i) ** left / ((1 + i) ** left - 1)
    interest2 = m2 * left - nb
    return {"m": m, "bal": bal, "old": old_interest, "months1": months, "save1": old_interest - interest1,
            "m2": m2, "save2": old_interest - interest2}


PREPAY_JS = """<script>(function(){var $=function(i){return document.getElementById(i)},f=function(x){return x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})};
function run(){var P=+$('p-a').value*1e4,n=+$('p-y').value*12,i=+$('p-r').value/1200,k=+$('p-k').value*12,x=+$('p-x').value*1e4;
if(!(P>0&&n>k&&i>0&&x>0))return;var m=P*i*Math.pow(1+i,n)/(Math.pow(1+i,n)-1),b=P*Math.pow(1+i,k)-m*(Math.pow(1+i,k)-1)/i,L=n-k,old=m*L-b,nb=b-x;
if(nb<=0){$('p-out').innerHTML='<div>剩余本金<b>'+f(b)+'</b></div><div>可一次还清,节省利息<b>'+f(old)+'</b></div>';return}
var c=0,t=nb,it1=0;while(t>1e-6&&c<1200){var it=t*i,p=Math.min(m,t+it);it1+=it;t-=p-it;c++}
var m2=nb*i*Math.pow(1+i,L)/(Math.pow(1+i,L)-1),it2=m2*L-nb;
$('p-out').innerHTML='<div>当前剩余本金<b>'+f(b)+'</b></div><div>月供不变,缩短期限<b>省 '+f(old-it1)+'</b>提前 '+(L-c)+' 个月还清</div><div>期限不变,减少月供<b>省 '+f(old-it2)+'</b>月供变为 '+f(m2)+'</div>'}
['p-a','p-y','p-r','p-k','p-x'].forEach(function(i){$(i).oninput=run});run();})();</script>"""


def prepay_form(a, y, r, k, x):
    return f"""<div class="card"><h2>提前还贷计算器(等额本息)</h2><div class="form">
<label>贷款总额(万元)<input id="p-a" type="number" inputmode="decimal" value="{a}"></label>
<label>贷款年限<input id="p-y" type="number" inputmode="decimal" value="{y}"></label>
<label>年利率(%)<input id="p-r" type="number" inputmode="decimal" step="0.01" value="{r}"></label>
<label>已还年数<input id="p-k" type="number" inputmode="decimal" value="{k}"></label>
<label>提前还款(万元)<input id="p-x" type="number" inputmode="decimal" value="{x}"></label>
</div><div class="res" id="p-out"></div>{PREPAY_JS}</div>"""


def prepay_hub(cfg, ad):
    fc, r = cfg["finance"], cfg["mortgage"]["default_rate"]
    links = "".join(f'<a href="/tiqian/{a}wan-{k}nian-{x}wan/">{a}万贷款还了{k}年提前还{x}万</a>'
                    for a in fc["prepay_loans_wan"] for k in fc["prepay_paid_years"] for x in fc["prepay_amounts_wan"])
    body = f"""<div class="card"><h1>提前还贷计算器 - 提前还款能省多少利息</h1>
<p class="muted">比较"月供不变、缩短期限"和"期限不变、减少月供"两种方式各能省多少利息。</p></div>
{prepay_form(100, 30, r, 5, 20)}{ad}
<div class="card"><h2>两种方式怎么选?</h2><p><b>缩短期限</b>省的利息更多,但月供不变,适合收入稳定、希望早点还清的人。</p>
<p><b>减少月供</b>省的利息较少,但每月压力变小,适合想降低月供、留出现金流的人。</p>
<p>提前还款前,建议先向贷款银行确认是否需要预约、有没有违约金。</p></div>
<div class="card"><h2>常见情况速查</h2><div class="links">{links}</div>{DISCLAIMER}</div>"""
    return ("提前还贷计算器 - 提前还款省多少利息(缩短年限还是减少月供)", "提前还贷计算器,输入贷款金额、利率、已还年数和提前还款金额,对比缩短期限和减少月供两种方式能节省多少利息。", body)


def prepay_page(cfg, ad, a, k, x):
    years, r = cfg["finance"]["prepay_loan_years"], cfg["mortgage"]["default_rate"]
    d = prepay(a * 10000, years, r, k, x * 10000)
    left = years * 12 - k * 12
    body = f"""<div class="card"><h1>房贷{a}万{years}年,还了{k}年提前还{x}万能省多少利息?</h1>
<div class="big">最多省 {money(d["save1"])} 元</div>
<p class="muted">等额本息、年利率 {r}% · 原月供 {money(d["m"])} 元 · 第 {k} 年末剩余本金 {money(d["bal"])} 元</p></div>
{ad}
<div class="card"><h2>两种提前还款方式对比</h2><table><tr><th>方式</th><th>节省利息</th><th>还款变化</th></tr>
<tr><td>月供不变,缩短期限</td><td>{money(d["save1"])}</td><td>剩余 {d["months1"]} 个月还清,提前 {left - d["months1"]} 个月</td></tr>
<tr><td>期限不变,减少月供</td><td>{money(d["save2"])}</td><td>月供从 {money(d["m"])} 降到 {money(d["m2"])}</td></tr></table>
<p class="muted">不提前还款的话,剩余 {left} 个月还要付利息 {money(d["old"])} 元。</p></div>
{prepay_form(a, years, r, k, x)}{DISCLAIMER}
<div class="card"><h2>相关计算</h2><div class="links"><a href="/tiqian/">提前还贷计算器</a><a href="/fangdai/{a}wan-{years}nian/">{a}万{years}年月供</a></div></div>"""
    return (f"房贷{a}万还了{k}年提前还{x}万省多少利息 - 提前还贷计算",
            f"{a}万{years}年房贷(年利率{r}%)还款{k}年后提前还{x}万:缩短期限省利息{money(d['save1'])}元,减少月供省{money(d['save2'])}元。", body)


# ---------- 公积金贷款 ----------

def gjj_rate(cfg, years):
    fc = cfg["finance"]
    return fc["gjj_rate_over5"] if years > 5 else fc["gjj_rate_5"]


def gjj_hub(cfg, ad):
    fc = cfg["finance"]
    links = "".join(f'<a href="/gongjijin/{a}wan-{y}nian/">公积金贷{a}万{y}年</a>' for a in fc["gjj_amounts_wan"] for y in fc["gjj_years"])
    body = f"""<div class="card"><h1>公积金贷款计算器</h1>
<p class="muted">首套房公积金贷款利率示例:5 年以下(含){fc["gjj_rate_5"]}%,5 年以上 {fc["gjj_rate_over5"]}%({fc["gjj_rate_note"]})。可在计算器中修改为实际利率。</p></div>
{mortgage_form(60, 30, fc["gjj_rate_over5"])}{ad}
<div class="card"><h2>公积金贷款月供速查</h2><div class="links">{links}</div>{DISCLAIMER}</div>"""
    return ("公积金贷款计算器2026 - 公积金贷款月供计算", "公积金贷款计算器,按首套公积金贷款利率计算月供、总利息和还款总额,支持等额本息和等额本金。", body)


def gjj_page(cfg, ad, a, y):
    fc, cr = cfg["finance"], cfg["mortgage"]["default_rate"]
    r = gjj_rate(cfg, y)
    P = a * 10000
    m, it = bx(P, y, r)
    first, last, dec, it2 = bj(P, y, r)
    cm, cit = bx(P, y, cr)
    other = "".join(f'<a href="/gongjijin/{aa}wan-{y}nian/">{aa}万{y}年</a>' for aa in fc["gjj_amounts_wan"] if aa != a)
    body = f"""<div class="card"><h1>公积金贷款{a}万{y}年月供多少?</h1>
<div class="big">等额本息月供 {money(m)} 元</div>
<p class="muted">按公积金贷款年利率 {r}% 计算({fc["gjj_rate_note"]}) · 等额本金首月 {money(first)} 元,每月递减 {money(dec)} 元</p></div>
{ad}
<div class="card"><h2>还款方式对比</h2><table><tr><th>项目</th><th>等额本息</th><th>等额本金</th></tr>
<tr><td>首月月供</td><td>{money(m)}</td><td>{money(first)}</td></tr><tr><td>支付利息</td><td>{money(it)}</td><td>{money(it2)}</td></tr>
<tr><td>还款总额</td><td>{money(P + it)}</td><td>{money(P + it2)}</td></tr></table></div>
<div class="card"><h2>公积金贷款和商业贷款对比</h2><table><tr><th>项目</th><th>公积金({r}%)</th><th>商贷({cr}%)</th></tr>
<tr><td>月供</td><td>{money(m)}</td><td>{money(cm)}</td></tr><tr><td>总利息</td><td>{money(it)}</td><td>{money(cit)}</td></tr></table>
<p class="muted">同样贷 {a} 万 {y} 年,公积金贷款比商业贷款少付利息 {money(cit - it)} 元(商贷利率为示例)。</p></div>
{mortgage_form(a, y, r)}{DISCLAIMER}
<div class="card"><h2>其他金额</h2><div class="links">{other}</div></div>"""
    return (f"公积金贷款{a}万{y}年月供多少 - 等额本息{money(m)}元",
            f"公积金贷款{a}万元{y}年,按年利率{r}%计算等额本息月供{money(m)}元,总利息{money(it)}元;等额本金首月{money(first)}元。附与商贷对比。", body)


HUBS = [("/cunkuan/", "存款利息计算"), ("/dingtou/", "定投/复利计算"), ("/tiqian/", "提前还贷计算"), ("/gongjijin/", "公积金贷款计算")]


def pages(cfg, ad):
    fc = cfg["finance"]
    yield "/cunkuan/", deposit_hub(cfg, ad)
    for p in fc["deposit_amounts_wan"]:
        for y in fc["deposit_years"]:
            yield f"/cunkuan/{p:g}wan-{y}nian/", deposit_page(cfg, ad, p, y)
    yield "/dingtou/", invest_hub(cfg, ad)
    for m in fc["dingtou_monthly"]:
        for y in fc["dingtou_years"]:
            yield f"/dingtou/{m}-{y}nian/", invest_page(cfg, ad, m, y)
    yield "/tiqian/", prepay_hub(cfg, ad)
    for a in fc["prepay_loans_wan"]:
        for k in fc["prepay_paid_years"]:
            for x in fc["prepay_amounts_wan"]:
                yield f"/tiqian/{a}wan-{k}nian-{x}wan/", prepay_page(cfg, ad, a, k, x)
    yield "/gongjijin/", gjj_hub(cfg, ad)
    for a in fc["gjj_amounts_wan"]:
        for y in fc["gjj_years"]:
            yield f"/gongjijin/{a}wan-{y}nian/", gjj_page(cfg, ad, a, y)
