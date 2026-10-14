"""房贷计算器、个税计算器、年终奖个税页面。

pages(cfg, ad) 依次产出 (路径, (标题, 描述, 正文)),由 build.py 写入 dist/。
"""
import json
import math

INF = math.inf

# 综合所得年度税率表(也用于工资薪金累计预扣法):(应纳税所得额上限, 税率, 速算扣除数)
ANNUAL = [(36000, .03, 0), (144000, .10, 2520), (300000, .20, 16920), (420000, .25, 31920),
          (660000, .30, 52920), (960000, .35, 85920), (INF, .45, 181920)]
# 按月换算后的税率表(全年一次性奖金单独计税使用)
MONTHLY = [(3000, .03, 0), (12000, .10, 210), (25000, .20, 1410), (35000, .25, 2660),
           (55000, .30, 4410), (80000, .35, 7160), (INF, .45, 15160)]
BASIC = 5000  # 每月基本减除费用


def money(x):
    return f"{x:,.2f}"


def yuan(n):
    return f"{n // 10000}万" if n >= 10000 and n % 10000 == 0 else f"{n:,}"


def bracket_rows(table):
    out = []
    for i, (top, r, q) in enumerate(table):
        if i == 0:
            label = f"不超过{yuan(top)}"
        elif top == INF:
            label = f"超过{yuan(table[i - 1][0])}"
        else:
            label = f"超过{yuan(table[i - 1][0])}至{yuan(top)}"
        out.append(f"<tr><td>{label}</td><td>{int(round(r * 100))}%</td><td>{q:,}</td></tr>")
    return "".join(out)


# ---------- 房贷 ----------

def bx(P, years, rate):
    """等额本息:返回 (月供, 总利息)。"""
    n, r = years * 12, rate / 1200
    m = P / n if r == 0 else P * r * (1 + r) ** n / ((1 + r) ** n - 1)
    return m, m * n - P


def bj(P, years, rate):
    """等额本金:返回 (首月月供, 末月月供, 每月递减, 总利息)。"""
    n, r = years * 12, rate / 1200
    return P / n + P * r, P / n * (1 + r), P / n * r, P * r * (n + 1) / 2


def bx_schedule(P, years, rate):
    """等额本息逐年:[(第几年, 当年还本金, 当年还利息, 年末剩余本金)]。"""
    n, r = years * 12, rate / 1200
    m, _ = bx(P, years, rate)
    bal, rows = P, []
    for y in range(1, years + 1):
        pi = pp = 0.0
        for _ in range(12):
            i = bal * r
            pi += i
            pp += m - i
            bal -= m - i
        rows.append((y, pp, pi, max(bal, 0)))
    return rows


MORTGAGE_JS = """<script>(function(){
var $=function(i){return document.getElementById(i)},f=function(x){return x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})};
function run(){var P=+$('m-amt').value*10000,n=+$('m-yr').value*12,r=+$('m-rate').value/1200,o='';
if(!(P>0&&n>0)){return}
if($('m-way').value==='bx'){var m=r?P*r*Math.pow(1+r,n)/(Math.pow(1+r,n)-1):P/n;
o='<div>每月月供<b>'+f(m)+'</b></div><div>支付利息<b>'+f(m*n-P)+'</b></div><div>还款总额<b>'+f(m*n)+'</b></div>';}
else{var a=P/n+P*r,b=P/n*(1+r),i=P*r*(n+1)/2;
o='<div>首月月供<b>'+f(a)+'</b></div><div>每月递减<b>'+f(P/n*r)+'</b></div><div>末月月供<b>'+f(b)+'</b></div><div>支付利息<b>'+f(i)+'</b></div><div>还款总额<b>'+f(P+i)+'</b></div>';}
$('m-out').innerHTML=o;}
['m-amt','m-yr','m-rate','m-way'].forEach(function(i){$(i).oninput=run});run();})();</script>"""


def mortgage_form(amt, years, rate):
    opts = "".join(f'<option value="{y}"{" selected" if y == years else ""}>{y}年</option>' for y in range(1, 31))
    return f"""<div class="card"><h2>房贷计算器</h2><div class="form">
<label>贷款金额(万元)<input id="m-amt" type="number" inputmode="decimal" value="{amt}"></label>
<label>贷款年限<select id="m-yr">{opts}</select></label>
<label>年利率(%)<input id="m-rate" type="number" inputmode="decimal" step="0.01" value="{rate}"></label>
<label>还款方式<select id="m-way"><option value="bx">等额本息</option><option value="bj">等额本金</option></select></label>
</div><div class="res" id="m-out"></div>{MORTGAGE_JS}</div>"""


def mortgage_hub(cfg, ad):
    mc = cfg["mortgage"]
    links = "".join(f'<a href="/fangdai/{a}wan-{y}nian/">{a}万{y}年</a>' for a in mc["amounts_wan"] for y in mc["years"])
    body = f"""<div class="card"><h1>房贷计算器(等额本息/等额本金)</h1>
<p class="muted">输入贷款金额、年限和利率,立即算出月供、总利息和还款总额。利率可按你的贷款合同自行修改。</p></div>
{mortgage_form(100, 30, mc["default_rate"])}{ad}
<div class="card"><h2>等额本息和等额本金怎么选?</h2>
<p><b>等额本息</b>:每月还款金额固定,前期月供压力小,但总利息更多,适合收入稳定、希望每月支出固定的人。</p>
<p><b>等额本金</b>:每月归还相同本金,利息逐月减少,首月月供最高、之后逐月递减,总利息更少,适合前期收入较高或计划提前还款的人。</p></div>
<div class="card"><h2>常见贷款月供速查</h2><div class="links">{links}</div></div>"""
    return ("房贷计算器2026 - 等额本息等额本金月供计算",
            "免费在线房贷计算器,支持等额本息、等额本金两种还款方式,输入贷款金额、年限、利率即可算出月供、总利息和还款总额。", body)


def mortgage_page(cfg, ad, amt, years):
    mc = cfg["mortgage"]
    P, rate = amt * 10000, mc["default_rate"]
    m, it = bx(P, years, rate)
    a, b, dec, it2 = bj(P, years, rate)
    rows = "".join(
        f"<tr><td>{r}%</td><td>{money(bx(P, years, r)[0])}</td><td>{money(bx(P, years, r)[1])}</td>"
        f"<td>{money(bj(P, years, r)[0])}</td><td>{money(bj(P, years, r)[3])}</td></tr>" for r in mc["rates"])
    sched = "".join(f"<tr><td>第{y}年</td><td>{money(pp)}</td><td>{money(pi)}</td><td>{money(bal)}</td></tr>"
                    for y, pp, pi, bal in bx_schedule(P, years, rate))
    other_y = "".join(f'<a href="/fangdai/{amt}wan-{y}nian/">{amt}万{y}年</a>' for y in mc["years"] if y != years)
    other_a = "".join(f'<a href="/fangdai/{x}wan-{years}nian/">{x}万{years}年</a>' for x in mc["amounts_wan"] if x != amt)
    body = f"""<div class="card"><h1>贷款{amt}万{years}年月供多少?</h1>
<div class="big">等额本息月供 {money(m)} 元</div>
<p class="muted">按年利率 {rate}% 计算 · 等额本金首月 {money(a)} 元,之后每月减少 {money(dec)} 元</p></div>
{ad}
<div class="card"><h2>两种还款方式对比(年利率 {rate}%)</h2><table>
<tr><th>项目</th><th>等额本息</th><th>等额本金</th></tr>
<tr><td>首月月供</td><td>{money(m)}</td><td>{money(a)}</td></tr>
<tr><td>末月月供</td><td>{money(m)}</td><td>{money(b)}</td></tr>
<tr><td>支付利息</td><td>{money(it)}</td><td>{money(it2)}</td></tr>
<tr><td>还款总额</td><td>{money(P + it)}</td><td>{money(P + it2)}</td></tr></table>
<p class="muted">等额本金比等额本息少付利息 {money(it - it2)} 元,但首月多还 {money(a - m)} 元。</p></div>
<div class="card"><h2>不同利率下的月供</h2><div class="scroll"><table>
<tr><th>年利率</th><th>等额本息月供</th><th>等额本息总利息</th><th>等额本金首月</th><th>等额本金总利息</th></tr>{rows}</table></div>
<p class="muted">利率每变动 0.5 个百分点,月供和总利息都会明显变化,实际利率以贷款合同为准。</p></div>
{mortgage_form(amt, years, rate)}
{ad}
<div class="card"><h2>等额本息逐年还款明细(年利率 {rate}%)</h2><div class="scroll"><table>
<tr><th>年份</th><th>归还本金</th><th>支付利息</th><th>剩余本金</th></tr>{sched}</table></div></div>
<div class="card"><h2>相关计算</h2><div class="links">{other_y}</div><div class="links" style="margin-top:8px">{other_a}</div></div>"""
    return (f"贷款{amt}万{years}年月供多少 - 等额本息{money(m)}元(利率{rate}%)",
            f"房贷{amt}万元{years}年,按年利率{rate}%计算,等额本息月供{money(m)}元,总利息{money(it)}元;等额本金首月{money(a)}元。附不同利率对比和逐年还款明细。",
            body)


# ---------- 个税 ----------

def tax_by(table, x):
    if x <= 0:
        return 0.0, 0.0
    for top, rate, quick in table:
        if x <= top:
            return x * rate - quick, rate
    raise ValueError(x)


def insurance(cfg, salary):
    t = cfg["tax"]
    return min(salary, t["insurance_base_cap"]) * (t["social_rate"] + t["fund_rate"])


def withholding(salary, ins, special):
    """累计预扣法:返回 [(月份, 当月预扣税, 当月税后)] 和全年税额。"""
    rows, prev = [], 0.0
    for k in range(1, 13):
        cum, _ = tax_by(ANNUAL, k * (salary - ins - special - BASIC))
        rows.append((k, cum - prev, salary - ins - (cum - prev)))
        prev = cum
    return rows, prev


TAX_JS = """<script>(function(){
var T=__T__,$=function(i){return document.getElementById(i)},f=function(x){return x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})};
function tax(x){if(x<=0)return 0;for(var i=0;i<T.length;i++){if(T[i][0]===null||x<=T[i][0])return x*T[i][1]-T[i][2]}}
function run(){var s=+$('t-s').value,ins=$('t-i').value===''?Math.min(s,__CAP__)*__R__:+$('t-i').value,sp=+$('t-d').value||0,prev=0,rows='';
if(!(s>0))return;
for(var k=1;k<=12;k++){var c=tax(k*(s-ins-sp-5000)),t=c-prev;prev=c;rows+='<tr><td>'+k+'月</td><td>'+f(t)+'</td><td>'+f(s-ins-t)+'</td></tr>'}
$('t-out').innerHTML='<div>全年个税<b>'+f(prev)+'</b></div><div>月均税后<b>'+f(s-ins-prev/12)+'</b></div><div>每月五险一金<b>'+f(ins)+'</b></div>';
$('t-tb').innerHTML='<tr><th>月份</th><th>预扣个税</th><th>到手工资</th></tr>'+rows;}
['t-s','t-i','t-d'].forEach(function(i){$(i).oninput=run});run();})();</script>"""


def tax_form(cfg, salary):
    t = cfg["tax"]
    js = (TAX_JS.replace("__T__", json.dumps([[None if top == INF else top, r, q] for top, r, q in ANNUAL]))
          .replace("__CAP__", str(t["insurance_base_cap"])).replace("__R__", str(t["social_rate"] + t["fund_rate"])))
    return f"""<div class="card"><h2>工资个税计算器</h2><div class="form">
<label>税前月薪(元)<input id="t-s" type="number" inputmode="decimal" value="{salary}"></label>
<label>每月五险一金(元,留空自动估算)<input id="t-i" type="number" inputmode="decimal" placeholder="自动估算"></label>
<label>每月专项附加扣除(元)<input id="t-d" type="number" inputmode="decimal" value="0"></label>
</div><div class="res" id="t-out"></div><div class="scroll" style="margin-top:12px"><table id="t-tb"></table></div>{js}</div>"""


def tax_note(cfg):
    t = cfg["tax"]
    return (f"五险一金按月薪的 {(t['social_rate'] + t['fund_rate']) * 100:.1f}% 估算"
            f"(社保个人 {t['social_rate'] * 100:.1f}% + 公积金 {t['fund_rate'] * 100:.0f}%),"
            f"缴费基数上限按 {t['insurance_base_cap']:,} 元估算,各城市实际基数和比例不同。")


def tax_hub(cfg, ad):
    links = "".join(f'<a href="/geshui/{s}/">月薪{yuan(s)}</a>' for s in cfg["tax"]["salaries"])
    rows = bracket_rows(ANNUAL)
    body = f"""<div class="card"><h1>个税计算器2026(工资薪金累计预扣)</h1>
<p class="muted">按现行个人所得税法和累计预扣法计算每月预扣个税和到手工资。{tax_note(cfg)}可手动填写实际金额。</p></div>
{tax_form(cfg, 10000)}{ad}
<div class="card"><h2>个人所得税税率表(综合所得,按年)</h2><table><tr><th>全年应纳税所得额</th><th>税率</th><th>速算扣除数</th></tr>{rows}</table>
<p class="muted">应纳税所得额 = 年收入 − 6万元基本减除费用 − 五险一金 − 专项附加扣除。</p></div>
<div class="card"><h2>为什么下半年工资到手变少了?</h2><p>工资个税采用累计预扣法:每月按"截至当月的累计收入"适用税率。随着累计所得超过 3.6 万、14.4 万等档位,当月税率会跳到 10%、20%,所以下半年预扣的税往往更多,到手工资变少。全年总税额不变。</p></div>
<div class="card"><h2>月薪个税速查</h2><div class="links">{links}</div></div>"""
    return ("个税计算器2026 - 工资到手多少,每月个税怎么算",
            "2026个人所得税计算器,按累计预扣法算出每月个税和到手工资,支持五险一金、专项附加扣除,附个税税率表。", body)


def tax_page(cfg, ad, salary):
    ins = insurance(cfg, salary)
    rows, total = withholding(salary, ins, 0)
    tb = "".join(f"<tr><td>{k}月</td><td>{money(t)}</td><td>{money(n)}</td></tr>" for k, t, n in rows)
    sp = "".join(f"<tr><td>{d:,} 元/月</td><td>{money(withholding(salary, ins, d)[1])}</td>"
                 f"<td>{money(total - withholding(salary, ins, d)[1])}</td></tr>" for d in (1000, 2000, 3000, 5000))
    taxable = max(salary * 12 - ins * 12 - BASIC * 12, 0)
    _, rate = tax_by(ANNUAL, taxable)
    salaries = cfg["tax"]["salaries"]
    i = salaries.index(salary)
    near = "".join(f'<a href="/geshui/{s}/">月薪{yuan(s)}</a>' for s in salaries[max(0, i - 4):i + 5] if s != salary)
    body = f"""<div class="card"><h1>月薪{yuan(salary)}扣多少税?到手多少?</h1>
<div class="big">全年个税 {money(total)} 元</div>
<p class="muted">月均到手约 {money(salary - ins - total / 12)} 元 · 每月五险一金约 {money(ins)} 元 · 全年最高适用税率 {int(rate * 100)}%</p></div>
{ad}
<div class="card"><h2>每月预扣个税和到手工资(无专项附加扣除)</h2><table><tr><th>月份</th><th>预扣个税</th><th>到手工资</th></tr>{tb}</table>
<p class="muted">{tax_note(cfg)}</p></div>
<div class="card"><h2>有专项附加扣除能省多少税?</h2><table><tr><th>专项附加扣除</th><th>全年个税</th><th>比不扣除少交</th></tr>{sp}</table>
<p class="muted">专项附加扣除包括子女教育、3岁以下婴幼儿照护、继续教育、住房贷款利息或住房租金、赡养老人、大病医疗,可在个人所得税 App 中填报。</p></div>
{tax_form(cfg, salary)}{ad}
<div class="card"><h2>其他月薪</h2><div class="links">{near}</div></div>"""
    return (f"月薪{yuan(salary)}扣多少税 - 到手工资计算(2026)",
            f"税前月薪{yuan(salary)}元,五险一金约{money(ins)}元,全年个税约{money(total)}元,月均到手约{money(salary - ins - total / 12)}元。附每月预扣明细。",
            body)


# ---------- 年终奖 ----------

def bonus_tax(b):
    """单独计税:按 奖金÷12 确定税率,税额 = 奖金 × 税率 − 速算扣除数。"""
    if b <= 0:
        return 0.0, 0.0
    m = b / 12
    _, rate, quick = next(row for row in MONTHLY if m <= row[0])
    return b * rate - quick, rate


def traps():
    """年终奖"多发反而少拿"区间:[(起点, 终点)]。"""
    out = []
    for top, _, _ in MONTHLY[:-1]:
        t = top * 12
        net = t - bonus_tax(t)[0]
        _, r2 = bonus_tax(t + 1)
        q2 = next(q for tp, r, q in MONTHLY if r == r2)
        out.append((t, (net - q2) / (1 - r2)))
    return out


BONUS_JS = """<script>(function(){
var T=__T__,$=function(i){return document.getElementById(i)},f=function(x){return x.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})};
function run(){var b=+$('b-a').value;if(!(b>0))return;var m=b/12,t=0,r=0;
for(var i=0;i<T.length;i++){if(T[i][0]===null||m<=T[i][0]){r=T[i][1];t=b*r-T[i][2];break}}
$('b-out').innerHTML='<div>应缴个税<b>'+f(t)+'</b></div><div>税后到手<b>'+f(b-t)+'</b></div><div>适用税率<b>'+Math.round(r*100)+'%</b></div>';}
$('b-a').oninput=run;run();})();</script>"""


def bonus_form(amount):
    js = BONUS_JS.replace("__T__", json.dumps([[None if top == INF else top, r, q] for top, r, q in MONTHLY]))
    return f"""<div class="card"><h2>年终奖个税计算器(单独计税)</h2><div class="form">
<label>年终奖金额(元)<input id="b-a" type="number" inputmode="decimal" value="{amount}"></label>
</div><div class="res" id="b-out"></div>{js}</div>"""


def trap_table():
    rows = "".join(f"<tr><td>{money(a)} ~ {money(b)}</td></tr>" for a, b in traps())
    return f"""<div class="card"><h2>年终奖"雷区":多发反而少拿</h2>
<p>单独计税时,年终奖除以 12 后一旦跨过税率档位,整笔奖金都按更高税率计税。因此在下列区间内,税前多发的钱还不够多交的税,<b>税后反而比档位起点更少</b>:</p>
<table><tr><th>年终奖区间(元)</th></tr>{rows}</table>
<p class="muted">例如年终奖 36,000 元税后 34,920 元,而 36,001 元时税额跳到 3,390.10 元,税后只有 32,610.90 元。</p></div>"""


def bonus_hub(cfg, ad):
    links = "".join(f'<a href="/nianzhongjiang/{b}/">年终奖{yuan(b)}</a>' for b in cfg["bonus"]["amounts"])
    rows = bracket_rows(MONTHLY)
    body = f"""<div class="card"><h1>年终奖个税计算器2026</h1>
<p class="muted">全年一次性奖金可选择单独计税:奖金 ÷ 12 找对应税率,应纳税额 = 奖金 × 税率 − 速算扣除数。该政策执行至 2027 年 12 月 31 日。</p></div>
{bonus_form(50000)}{ad}
<div class="card"><h2>年终奖单独计税税率表(按月换算)</h2><table><tr><th>奖金÷12 后的金额</th><th>税率</th><th>速算扣除数</th></tr>{rows}</table></div>
{trap_table()}
<div class="card"><h2>单独计税还是并入综合所得?</h2><p>如果全年工资扣除后的应纳税所得额很低(甚至不足 6 万元减除额),把年终奖并入综合所得往往更省税;工资较高时,单独计税通常更划算。每年汇算时可在个人所得税 App 中比较两种方式后选择。</p></div>
<div class="card"><h2>年终奖个税速查</h2><div class="links">{links}</div></div>"""
    return ("年终奖个税计算器2026 - 年终奖扣多少税",
            "年终奖个税计算器,按全年一次性奖金单独计税办法算出应缴个税和税后到手金额,附税率表和年终奖雷区。", body)


def bonus_page(cfg, ad, amount):
    tax, rate = bonus_tax(amount)
    amounts = cfg["bonus"]["amounts"]
    rows = "".join(f'<tr><td><a href="/nianzhongjiang/{b}/">{yuan(b)}</a></td><td>{money(bonus_tax(b)[0])}</td><td>{money(b - bonus_tax(b)[0])}</td></tr>'
                   for b in amounts)
    trap = next(((a, b) for a, b in traps() if a < amount < b), None)
    warn = (f'<p class="up"><b>注意:</b>{yuan(amount)} 元落在年终奖雷区({money(trap[0])} ~ {money(trap[1])})内,'
            f'税后到手比年终奖 {money(trap[0])} 元时还少 {money(trap[0] - bonus_tax(trap[0])[0] - (amount - tax))} 元。</p>') if trap else ""
    body = f"""<div class="card"><h1>年终奖{yuan(amount)}扣多少税?</h1>
<div class="big">应缴个税 {money(tax)} 元</div>
<p class="muted">税后到手 {money(amount - tax)} 元 · 适用税率 {int(rate * 100)}% · 按单独计税办法计算</p>{warn}</div>
{ad}
<div class="card"><h2>计算过程</h2><p>{yuan(amount)} ÷ 12 = {money(amount / 12)} 元,对应月度税率表税率 {int(rate * 100)}%。<br>
应纳税额 = {amount:,} × {int(rate * 100)}% − {amount * rate - tax:,.0f}(速算扣除数) = {money(tax)} 元。</p></div>
{bonus_form(amount)}
<div class="card"><h2>不同年终奖金额个税对照</h2><table><tr><th>年终奖</th><th>个税</th><th>税后</th></tr>{rows}</table></div>
{trap_table()}"""
    return (f"年终奖{yuan(amount)}扣多少税 - 税后到手{money(amount - tax)}元(2026)",
            f"年终奖{yuan(amount)}元按单独计税,适用税率{int(rate * 100)}%,应缴个税{money(tax)}元,税后到手{money(amount - tax)}元。",
            body)


def pages(cfg, ad):
    yield "/fangdai/", mortgage_hub(cfg, ad)
    for a in cfg["mortgage"]["amounts_wan"]:
        for y in cfg["mortgage"]["years"]:
            yield f"/fangdai/{a}wan-{y}nian/", mortgage_page(cfg, ad, a, y)
    yield "/geshui/", tax_hub(cfg, ad)
    for s in cfg["tax"]["salaries"]:
        yield f"/geshui/{s}/", tax_page(cfg, ad, s)
    yield "/nianzhongjiang/", bonus_hub(cfg, ad)
    for b in cfg["bonus"]["amounts"]:
        yield f"/nianzhongjiang/{b}/", bonus_page(cfg, ad, b)
