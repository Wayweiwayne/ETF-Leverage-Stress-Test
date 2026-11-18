"""How much an unsecured personal loan can be, from income and existing debt. No Streamlit here.

Amounts are in units of 10,000 (萬), as the sidebar takes them; the page converts to dollars.
All sentences live here so the page, the report and the tests read the same words.
"""
from dataclasses import dataclass

DBR_MULTIPLE = 22               # FSC rule: unsecured debt may not exceed 22 months of income
DEFAULT_INCOME, DEFAULT_DEBT, DEFAULT_MULTIPLE, DEFAULT_PRODUCT_MAX = 5.0, 0.0, 20, 500
MULTIPLE_RANGE = (10, 22)
MIN_YEARLY_INCOME = 30          # 萬; the usual application threshold
DEFAULT_PRINCIPAL = {"credit": 100, "mortgage": 300}
LOAN_STEP = {"credit": 10, "mortgage": 50}
RATIO_HIGH, RATIO_DECLINE = 1 / 3, 0.70
LMODE_OPTIONS = ("自己輸入", "用估計的可核貸金額")

HELP_INCOME = ("你每個月平均賺多少。算法：年收入（含年終獎金、分紅）÷ 12。例如年收入 72 萬，就填 6。"
               "填 0 代表不檢查信貸額度。")
HELP_DEBT = ("你現在欠的、沒有拿房子或車子抵押的錢，全部加起來。要算：信用卡未繳的錢和分期、循環利息、預借現金、"
             "現金卡、其他信貸、已經開始還的學貸。不用算：房貸、有抵押的車貸、股票質借、券商融資。")
HELP_MULTIPLE = ("銀行實際肯借你幾倍的月收入，沒有公開的數字，所以這是估計。依網路文章（不是銀行公布的），"
                 "多在 15～18 倍，預設的 20 比較樂觀。想保守一點，可以調低。法規最高是 22 倍。")
HELP_PRODUCT_MAX = "一個信貸產品最多借多少。大型民營銀行常見 500 萬，公股銀行常見 300 萬。專業人士專案可到 1,000～1,200 萬。"
HELP_LMODE = ("自己輸入：本金照你填的算。用估計的可核貸金額：本金直接用下面算出來的一般可核貸金額，不能自己改。")
HELP_LOAN = {"credit": "你打算借多少錢來投資。例如填 100 就是借 100 萬。",
             "mortgage": "你打算借多少錢來投資。例如填 300 就是借 300 萬。"}
HELP_LOAN_ESTIMATED = "目前用的是估計的可核貸金額，要自己填請把上面改成「自己輸入」。"
EXPANDER = "額度檢查的細項（估計）"
LABELS = {"inc": "平均月收入 (萬)", "udebt": "既有無擔保債務 (萬)", "mult": "核貸倍數（估計）(倍)",
          "pmax": "產品最高額度 (萬)", "lmode": "貸款金額怎麼決定"}

L02 = "⚠️ 超過可借上限 {cap} 萬。計算時會改用 {cap} 萬。"
L04 = "可借上限 {cap} 萬｜一般可核貸約 {z} 萬（估計）"
L07 = "年收入約 {yearly} 萬，未滿 30 萬。多數銀行的信貸申辦門檻是年收入 30 萬。"
L08 = "你的既有無擔保債務 {d} 萬，已經用完法規上限（平均月收入 {inc} 萬 × 22 ＝ {gross} 萬）。依規定，不能再借信貸。"
L08_ERROR = "信貸額度：既有無擔保債務已用完法規上限，無法再借"
L09 = "用估計的可核貸金額算出來是 0 萬，無法計算。請改成「自己輸入」，或調高核貸倍數。"
L09_ERROR = "信貸額度：用估計的可核貸金額算出來是 0 萬，無法計算"
L11 = "填平均月收入可以檢查信貸額度。"
L12 = ("依新聞報導：2026-10-31 起，信貸的資金用途如果寫「投資理財」，銀行要先經你同意，才能查詢你在券商的借貸"
       "（例如融資）。你不同意，就辦不成。")
CLOSING = "信貸額度是估計。各銀行條件常變動，以銀行核定為準。"
NOT_CHECKED = "未檢查（沒有填平均月收入）"
HEAT_CELL = "超限"
HEAT_NOTE = "灰底「超限」的格子：貸款本金超過可借上限 {cap} 萬，銀行不會核貸，所以不計算。"
HEAT_HOVER = "貸款本金 {y} 超過可借上限 {cap} 萬，無法計算"
SAFE_SENTENCE = "以目前其他設定，就算借到可借上限 **{cap} 萬**，破產機率也只有 {r}，仍在 {t} 以下（你目前設定 {cur} 萬）。"
SAFE_VALUE = "{cap} 萬（可借上限）"


def wan_text(value):
    """An amount in 萬 as `110`, `5.5` or `1,100` (one decimal at most, no trailing zero)."""
    text = f"{round(float(value) + 0.0, 1):,.1f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def wan(value):
    return f"{wan_text(value)} 萬"


@dataclass(frozen=True)
class Credit:
    """Limits for one set of inputs (all in 萬)."""
    income: float
    debt: float
    multiple: float
    product_max: float

    @property
    def gross(self):
        """22 times income, before existing debt."""
        return self.income * DBR_MULTIPLE

    @property
    def regulatory(self):
        return max(0.0, self.gross - self.debt)

    @property
    def approvable(self):
        """Typical approval (an estimate): the multiple, not the legal 22, capped by the product."""
        return max(0.0, min(self.income * self.multiple - self.debt, self.product_max))

    @property
    def cap(self):
        return min(self.regulatory, self.product_max)

    @property
    def capped_by_product(self):
        return self.product_max < self.regulatory


def assess(income, debt=DEFAULT_DEBT, multiple=DEFAULT_MULTIPLE, product_max=DEFAULT_PRODUCT_MAX):
    """The limits for an income above zero, or None when no income was given (no check)."""
    if not income or income <= 0:
        return None
    return Credit(float(income), float(debt), float(multiple), float(product_max))


def adopted_principal(credit, entered, estimated=False):
    """The loan actually simulated, in 萬: the estimate, or the input held down to the cap."""
    if credit is None:
        return float(entered)
    if estimated:
        return credit.approvable
    return min(float(entered), credit.cap)


def is_legacy_link(settings):
    """A V39 link: it names a loan amount but no income, and the loan is a personal loan.

    Such a link must give V39's numbers, so its income counts as 0 (no check).
    """
    if "loan" not in settings or "inc" in settings:
        return False
    try:
        return int(float(settings.get("type", "1"))) != 0
    except (ValueError, TypeError, OverflowError):
        return True


def monthly_ratio(payment, income):
    """Monthly payment after the grace period as a share of average monthly income (in dollars / 萬)."""
    return payment / (income * 10_000)


# ---- sentences ----

def summary(credit):
    """L-03."""
    text = (f"依平均月收入 {wan_text(credit.income)} 萬：法規上限 {wan(credit.regulatory)}、"
            f"一般可核貸約 {wan(credit.approvable)}（估計）、產品最高額度 {wan(credit.product_max)}。"
            f"你的可借上限是 {wan(credit.cap)}。")
    if credit.debt > 0:
        text += f"已扣掉既有無擔保債務 {wan(credit.debt)}。"
    return text


def clamp_notice(credit, entered):
    """L-01a / L-01b (without the warning sign): the input was held down to the cap."""
    if credit.capped_by_product:
        return (f"你輸入 {wan(entered)}，但產品最高額度是 {wan(credit.product_max)}。"
                f"以下結果以 {wan(credit.product_max)}計算。")
    return (f"你輸入 {wan(entered)}，但依規定（平均月收入的 22 倍，扣掉既有無擔保債務）最多只能借 {wan(credit.cap)}。"
            f"以下結果以 {wan(credit.cap)}計算。")


def ratio_notice(ratio, payment):
    """L-05 / L-06 (without the warning sign), or None when the ratio is fine."""
    if ratio <= RATIO_HIGH:
        return None
    head = f"寬限期後每月應繳 ${int(round(payment)):,}，是平均月收入的 {ratio * 100:.1f}%。"
    tail = "這裡只算這筆新貸款，沒有算你其他貸款的月付。"
    if ratio > RATIO_DECLINE:
        return head + "多數銀行可能婉拒。有銀行規定每月還款不能超過月收入的 70%。" + tail
    return head + "月付比偏高。部分銀行的產品條件寫，每月還款不能超過月收入的三分之一。" + tail


def income_notice(credit):
    """L-07 (without the warning sign), or None when income is at least the threshold."""
    if credit.income * 12 >= MIN_YEARLY_INCOME:
        return None
    return L07.format(yearly=wan_text(credit.income * 12))


def above_estimate_notice(credit, principal):
    """L-10: the input is above the typical approval but still within the cap."""
    if credit.approvable < principal <= credit.cap:
        return f"你輸入的 {wan(principal)}，高過一般可核貸的估計 {wan(credit.approvable)}。銀行可能只核給較低的額度。"
    return None


def exhausted_notice(credit):
    """L-08 when the cap is 0."""
    return L08.format(d=wan_text(credit.debt), inc=wan_text(credit.income), gross=wan_text(credit.gross))


def switch_toast(type_name, principal, rate, years, grace_years):
    """L-16."""
    grace = f"寬限期 {grace_years} 年" if grace_years else "無寬限期"
    return f"已換成{type_name}的預設值：本金 {principal} 萬、年利率 {rate:g}%、{years} 年、{grace}。"
