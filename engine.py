"""Stress-test simulation engine: loan schedule, repayment waterfall, historical and Monte Carlo runs.

Pure NumPy/pandas with no UI imports, so the same code can sit behind Streamlit,
an HTTP API or a batch job. All randomness comes from generators created per call;
nothing touches NumPy's global random state, which keeps concurrent runs independent.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SALARY, DIVIDEND, BUFFER, SELL = "salary", "dividend", "buffer", "sell"
SOURCES = (SALARY, DIVIDEND, BUFFER, SELL)

# Annual price returns (%) used to extend a start month whose real history is shorter than the loan.
SCENARIOS = {
    "crash_2008": (-45, 78, 10, 5, 15, 2, 8),
    "lost_decade": (-10, -5, -5, 2, 0, -2, 4, 3),
    "ai_bubble": (25, -30, -10, 2, 2, 2, 4),
}

# What the no-loan comparison portfolio invests each month.
DCA_MATCH_OUT_OF_POCKET = "match"  # the cash the leveraged strategy actually took from salary
DCA_FULL_PAYMENT = "full"          # the whole scheduled loan payment, regardless of the salary cap

JOB_LOSS_NONE, JOB_LOSS_MANUAL, JOB_LOSS_RANDOM = "none", "manual", "random"

_SPLICE_SEED = 20240601
_HIST_JOB_LOSS_SEED = 13572468


@dataclass(frozen=True)
class JobLossParams:
    mode: str = JOB_LOSS_NONE
    unemployed_salary: float = 0.0
    # manual window (1-based start month)
    start_month: int = 0
    duration_months: int = 0
    # random two-state model
    annual_prob: float = 0.0
    mean_duration: float = 5.0
    distribution: str = "lognormal"  # or "poisson"
    duration_sigma: float = 0.6
    crash_linked: bool = False
    crash_threshold: float = 0.15
    crash_extra_low: float = 0.08
    crash_extra_high: float = 0.12


@dataclass(frozen=True)
class SimParams:
    principal: float
    annual_rate_pct: float
    total_months: int
    grace_months: int = 0
    rate_shock_year: int = 0
    rate_shock_delta_pct: float = 0.0
    buffer_months: int = 0

    reinvest: bool = True
    reinvest_ratio_b: float = 0.0
    source_order: tuple = SOURCES
    fee: float = 0.001425
    salary_cap: float = 0.0
    job_loss: JobLossParams = field(default_factory=JobLossParams)
    haircut_trigger: float = 1.0
    haircut_penalty: float = 0.0

    future_annual_returns: tuple = SCENARIOS["crash_2008"]
    base_div_yield: float = 0.06
    div_beta: float = 0.5
    structural_discount_pct: float = 0.0
    vol_drag: bool = True
    swan_month: int = 0
    swan_drop: float = 0.0

    mc_paths: int = 2000
    block_size: int = 12
    seed: int | None = None
    dca_mode: str = DCA_MATCH_OUT_OF_POCKET


@dataclass(frozen=True)
class LoanSchedule:
    payments: np.ndarray       # amount due each month
    monthly_rates: np.ndarray  # interest rate applied each month
    start_balance: np.ndarray  # principal outstanding before the month's payment
    end_balance: np.ndarray    # principal outstanding after it


@dataclass
class PathResults:
    ruined: np.ndarray
    lev_final: np.ndarray
    dca_final: np.ndarray
    ledger: dict | None = None  # per-month arrays of shape (months, paths) when record=True


@dataclass
class EngineResults:
    hist: pd.DataFrame
    mc: pd.DataFrame
    trace: pd.DataFrame
    schedule: LoanSchedule
    buffer_cash: float
    block_size: int
    mc_ok: bool
    vol_drag: float
    beta_b: float
    job_loss_any_rate: float
    job_loss_avg_months: float


def parse_annual_returns(text):
    """Parse "5, 10, -20" into a tuple of annual returns in percent."""
    try:
        values = tuple(float(x.strip()) for x in str(text).split(",") if x.strip())
    except ValueError:
        raise ValueError("年度報酬率必須是用逗號分開的數字，例如「5, 10, -20」。") from None
    if not values:
        raise ValueError("請至少輸入一個年度報酬率。")
    if any((not np.isfinite(v)) or v <= -100 for v in values):
        raise ValueError("年度報酬率必須大於 -100%。")
    return values


def build_loan_schedule(principal, annual_rate_pct, total_months, grace_months=0,
                        shock_year=0, shock_delta_pct=0.0):
    """Month-by-month payment schedule.

    Interest-only during the grace period, level amortisation afterwards. From the first
    month of `shock_year` the rate rises by `shock_delta_pct` and the payment is recomputed
    on the outstanding balance over the remaining term (the term itself does not change).
    """
    if total_months < 1:
        raise ValueError("貸款期數至少需要 1 個月。")
    if not 0 <= grace_months < total_months:
        raise ValueError("寬限期必須短於貸款總年限。")

    def amort_pmt(balance, r_m, n_left):
        if n_left <= 0:
            return balance * (1 + r_m)
        if r_m <= 0:
            return balance / n_left
        return balance * r_m / (1 - (1 + r_m) ** -n_left)

    shock_idx = (shock_year - 1) * 12 if shock_year > 0 else None
    payments = np.zeros(total_months)
    rates = np.zeros(total_months)
    start_bal = np.zeros(total_months)
    end_bal = np.zeros(total_months)

    bal = float(principal)
    r_m = (annual_rate_pct / 100) / 12
    pmt_amort = amort_pmt(bal, r_m, total_months - grace_months)

    for t in range(total_months):
        if shock_idx is not None and t == shock_idx:
            r_m = ((annual_rate_pct + shock_delta_pct) / 100) / 12
            if t >= grace_months:
                pmt_amort = amort_pmt(bal, r_m, total_months - t)

        rates[t] = r_m
        start_bal[t] = bal
        interest = bal * r_m

        if t < grace_months:
            pmt, principal_paid = interest, 0.0
        else:
            if t == grace_months and (shock_idx is None or t != shock_idx):
                pmt_amort = amort_pmt(bal, r_m, total_months - grace_months)
            pmt = pmt_amort
            principal_paid = max(0.0, pmt - interest)

        payments[t] = pmt
        bal = max(0.0, bal - principal_paid)
        end_bal[t] = bal

    return LoanSchedule(payments, rates, start_bal, end_bal)


def buffer_cash_for(schedule, grace_months, buffer_months, principal):
    """Cash set aside at entry: `buffer_months` of the post-grace payment, capped at the loan itself."""
    idx = grace_months if grace_months < len(schedule.payments) else -1
    return float(min(schedule.payments[idx] * buffer_months, principal))


def salary_cap_schedule(salary_cap, job_loss, total_months):
    """Per-month salary support before any random job loss is applied."""
    caps = np.full(total_months, float(salary_cap))
    if job_loss.mode == JOB_LOSS_MANUAL and job_loss.duration_months > 0:
        start = max(job_loss.start_month - 1, 0)
        caps[start:min(start + job_loss.duration_months, total_months)] = float(job_loss.unemployed_salary)
    return caps


def _unique_order(order):
    seen, result = set(), []
    for src in order:
        if src not in SOURCES:
            raise ValueError(f"未知的還款資金來源：{src}")
        if src not in seen:
            seen.add(src)
            result.append(src)
    return result


def simulate_paths(ret_a, ret_b, div_yield_a, price_a0, price_b0, payments, principal, buffer_cash,
                   fee, reinvest, ratio_b, order, salary_cap, haircut_trigger=1.0, haircut_penalty=0.0,
                   dca_mode=DCA_MATCH_OUT_OF_POCKET, record=False):
    """Run the leveraged strategy and its no-loan comparison over every path at once.

    Return/yield matrices are (months, paths); `salary_cap` has the same shape. Each month the
    payment is collected from `order` in turn; a path that cannot cover it is ruined for good
    and its final value is zero. With `record=True` the per-month ledger is returned as well.
    """
    if dca_mode not in (DCA_MATCH_OUT_OF_POCKET, DCA_FULL_PAYMENT):
        raise ValueError(f"未知的 DCA 對照模式：{dca_mode}")
    order = _unique_order(order)
    months, n_paths = ret_a.shape

    prices_a = np.array(price_a0, dtype=float)
    prices_b = np.array(price_b0, dtype=float)
    shares_a = (principal - buffer_cash) / prices_a
    shares_b = np.zeros(n_paths)
    div_pools = np.zeros(n_paths)
    buf_vals = np.full(n_paths, float(buffer_cash))
    is_ruined = np.zeros(n_paths, dtype=bool)

    dca_shares_a = np.zeros(n_paths)
    dca_shares_b = np.zeros(n_paths)
    dca_div_pools = np.zeros(n_paths)

    ledger = {k: [] for k in (
        "from_dividend", "from_buffer", "from_sell", "from_salary", "defaulted",
        "shares_a", "shares_b", "lev_value", "dca_value", "dca_contribution")} if record else None

    def lev_value():
        value = shares_a * prices_a * (1 - fee) + div_pools + buf_vals
        return value + shares_b * prices_b * (1 - fee) if reinvest else value

    def dca_value():
        value = dca_shares_a * prices_a * (1 - fee) + dca_div_pools
        return value + dca_shares_b * prices_b * (1 - fee) if reinvest else value

    for i in range(months):
        pmt = float(payments[i])
        ret_a_i = ret_a[i, :]
        prices_a = prices_a * (1 + ret_a_i)
        prices_b = prices_b * (1 + ret_b[i, :])
        div_y = div_yield_a[i, :]

        current_div = shares_a * prices_a * div_y
        with np.errstate(divide='ignore', invalid='ignore'):
            if reinvest:
                shares_b = shares_b + np.where(prices_b > 0, (current_div * ratio_b * (1 - fee)) / prices_b, 0.0)
                shares_a = shares_a + np.where(prices_a > 0, (current_div * (1 - ratio_b) * (1 - fee)) / prices_a, 0.0)
            else:
                div_pools = div_pools + current_div

        sell_cost = np.full(n_paths, fee, dtype=float)
        if haircut_penalty > 0:
            sell_cost = np.where(ret_a_i < -haircut_trigger, np.minimum(0.99, fee + haircut_penalty), fee)

        rem = np.where(is_ruined, 0.0, pmt)
        used = {src: np.zeros(n_paths) for src in SOURCES}
        for src in order:
            if src == DIVIDEND:
                pay = np.minimum(div_pools, rem)
                div_pools = div_pools - pay
            elif src == BUFFER:
                pay = np.minimum(buf_vals, rem)
                buf_vals = buf_vals - pay
            elif src == SELL:
                pay = np.minimum(np.maximum(shares_a * prices_a * (1 - sell_cost), 0.0), rem)
                with np.errstate(divide='ignore', invalid='ignore'):
                    shares_a = shares_a - np.where(prices_a > 0, (pay / (1 - sell_cost)) / prices_a, 0.0)
            else:
                pay = np.minimum(np.maximum(salary_cap[i, :], 0.0), rem)
            used[src] = pay
            rem = rem - pay

        defaulted = (rem > 1e-5) & (~is_ruined)

        if dca_mode == DCA_FULL_PAYMENT:
            contribution = np.full(n_paths, pmt)
        else:
            # A path that already went bust no longer pays anything; its comparison portfolio
            # keeps investing what salary could have covered.
            contribution = np.where(is_ruined, np.minimum(pmt, np.maximum(salary_cap[i, :], 0.0)), used[SALARY])
        is_ruined = is_ruined | defaulted

        dca_divs = dca_shares_a * prices_a * div_y
        with np.errstate(divide='ignore', invalid='ignore'):
            if reinvest:
                dca_shares_b = dca_shares_b + np.where(prices_b > 0, (dca_divs * ratio_b * (1 - fee)) / prices_b, 0.0)
                dca_shares_a = dca_shares_a + np.where(
                    prices_a > 0, ((dca_divs * (1 - ratio_b) + contribution) * (1 - fee)) / prices_a, 0.0)
            else:
                dca_div_pools = dca_div_pools + dca_divs
                dca_shares_a = dca_shares_a + np.where(
                    prices_a > 0, ((contribution + dca_div_pools) * (1 - fee)) / prices_a, 0.0)
                dca_div_pools = np.zeros(n_paths)

        if record:
            ledger["from_dividend"].append(used[DIVIDEND])
            ledger["from_buffer"].append(used[BUFFER])
            ledger["from_sell"].append(used[SELL])
            ledger["from_salary"].append(used[SALARY])
            ledger["defaulted"].append(defaulted)
            ledger["shares_a"].append(shares_a)
            ledger["shares_b"].append(shares_b)
            ledger["lev_value"].append(lev_value())
            ledger["dca_value"].append(dca_value())
            ledger["dca_contribution"].append(contribution)

    lev_final = lev_value()
    lev_final[is_ruined] = 0
    if record:
        ledger = {k: np.array(v) for k, v in ledger.items()}
    return PathResults(is_ruined, lev_final, dca_value(), ledger)


def dividend_model_yields(price_path, p_init, base_ann_yield, beta):
    """Dividend-beta model: payout scales with cumulative return, floored at 10% of the base amount."""
    base_div_amt = p_init * base_ann_yield / 12.0
    cum_ret = (price_path / p_init) - 1.0
    div_amt = np.maximum(base_div_amt * 0.1, base_div_amt * (1 + cum_ret * beta))
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(price_path > 0, div_amt / price_path, 0.0)


def simulate_unemployment(ret_paths, full_salary, job_loss, rng):
    """Per-month, per-path salary cap under a two-state (employed/unemployed) random model.

    Each month an employed path loses its job with the monthly equivalent of `annual_prob`;
    when `crash_linked`, a month falling more than `crash_threshold` adds a further annual
    probability drawn from U(crash_extra_low, crash_extra_high). Spell length is lognormal or
    Poisson with the given mean, at least one month. Re-employed paths can lose the job again.
    """
    months, n_paths = ret_paths.shape
    annual_prob = job_loss.annual_prob
    monthly_base = 1.0 - (1.0 - annual_prob) ** (1.0 / 12.0) if annual_prob > 0 else 0.0
    caps = np.full((months, n_paths), float(full_salary))
    is_unemp = np.zeros(n_paths, dtype=bool)
    remaining = np.zeros(n_paths, dtype=int)

    def draw_duration(n):
        if job_loss.distribution == "poisson":
            d = rng.poisson(max(job_loss.mean_duration, 1e-9), size=n)
        else:
            sigma = max(0.05, job_loss.duration_sigma)
            mu = np.log(max(job_loss.mean_duration, 1e-9)) - 0.5 * sigma ** 2
            d = rng.lognormal(mu, sigma, size=n)
        return np.maximum(1, np.round(d).astype(int))

    for i in range(months):
        p_loss = np.full(n_paths, monthly_base)
        if job_loss.crash_linked:
            crashed = ret_paths[i, :] < -job_loss.crash_threshold
            extra_ann = rng.uniform(job_loss.crash_extra_low, job_loss.crash_extra_high, size=n_paths)
            extra_monthly = 1.0 - (1.0 - extra_ann) ** (1.0 / 12.0)
            p_loss = np.where(crashed, np.minimum(0.99, monthly_base + extra_monthly), monthly_base)

        new_loss = (~is_unemp) & (rng.random(n_paths) < p_loss)
        if new_loss.any():
            remaining[new_loss] = draw_duration(int(new_loss.sum()))
            is_unemp[new_loss] = True

        caps[i, is_unemp] = float(job_loss.unemployed_salary)

        remaining[is_unemp] -= 1
        re_employed = is_unemp & (remaining <= 0)
        is_unemp[re_employed] = False
        remaining[re_employed] = 0

    return caps


def _future_monthly_returns(annual_returns, months):
    monthly = []
    for ar in annual_returns:
        monthly.extend([(1 + ar / 100.0) ** (1 / 12) - 1] * 12)
    while len(monthly) < months:
        monthly.extend(monthly[-12:])
    return np.array(monthly)


def _inject_swan(ret_a, ret_b, month, drop, beta_b, has_b):
    """One-off crash in a given month; the second asset is hit beta times as hard.

    Returns are floored at -100% so a price can reach zero but never turn negative.
    """
    if drop > 0 and 1 <= month <= ret_a.shape[0]:
        m = month - 1
        ret_a[m, :] = np.maximum(ret_a[m, :] - drop, -1.0)
        if has_b:
            ret_b[m, :] = np.maximum(ret_b[m, :] - drop * beta_b, -1.0)


def _build_trace(df, anchor_idx, schedule, ledger):
    months = len(schedule.payments)
    defaulted = ledger["defaulted"][:, 0]
    last = int(np.argmax(defaulted)) + 1 if defaulted.any() else months
    n_hist = len(df)
    dates, projected = [], []
    for i in range(last):
        if anchor_idx + i < n_hist:
            dates.append(df.index[anchor_idx + i])
            projected.append(False)
        else:
            dates.append(df.index[-1] + pd.DateOffset(months=anchor_idx + i - n_hist + 1))
            projected.append(True)
    return pd.DataFrame({
        "month": np.arange(1, last + 1),
        "date": dates,
        "projected": projected,
        "lev_value": np.maximum(ledger["lev_value"][:last, 0], 0),
        "dca_value": np.maximum(ledger["dca_value"][:last, 0], 0),
        "loan_balance": schedule.end_balance[:last],
        "annual_rate_pct": schedule.monthly_rates[:last] * 12 * 100,
        "defaulted": defaulted[:last],
        "payment": schedule.payments[:last],
        "from_dividend": ledger["from_dividend"][:last, 0],
        "from_buffer": ledger["from_buffer"][:last, 0],
        "from_sell": ledger["from_sell"][:last, 0],
        "from_salary": ledger["from_salary"][:last, 0],
        "dca_contribution": ledger["dca_contribution"][:last, 0],
        "shares_a": ledger["shares_a"][:last, 0],
        "shares_b": ledger["shares_b"][:last, 0],
    })


def run(df, params, anchor_idx):
    """Run both engines on aligned monthly data.

    `df` comes from market_data.align_months: columns Close_A, Price_Return_A, Div_Yield_A and,
    when a second asset is held, the same with suffix _B. Returns the rolling-history results
    (one row per start month), the Monte Carlo results (one row per path, anchored on the price
    at `anchor_idx`) and the month-by-month ledger of the start month `anchor_idx`.
    """
    p = params
    months = p.total_months
    n_hist = len(df)
    if n_hist < 1:
        raise ValueError("沒有可回測的月份。")
    if not 0 <= anchor_idx < n_hist:
        raise ValueError("進場月份超出資料範圍。")

    has_b = p.reinvest and "Close_B" in df.columns
    ratio_b = p.reinvest_ratio_b if has_b else 0.0
    schedule = build_loan_schedule(p.principal, p.annual_rate_pct, months, p.grace_months,
                                   p.rate_shock_year, p.rate_shock_delta_pct)
    buffer_cash = buffer_cash_for(schedule, p.grace_months, p.buffer_months, p.principal)
    base_caps = salary_cap_schedule(p.salary_cap, p.job_loss, months)
    random_job_loss = p.job_loss.mode == JOB_LOSS_RANDOM
    m_disc = p.structural_discount_pct / 100.0 / 12.0
    future = _future_monthly_returns(p.future_annual_returns, months)

    hist_ret_a = df["Price_Return_A"].to_numpy(dtype=float)
    hist_div_a = df["Div_Yield_A"].to_numpy(dtype=float)
    close_a = df["Close_A"].to_numpy(dtype=float)
    hist_ret_b = df["Price_Return_B"].to_numpy(dtype=float) if has_b else None
    close_b = df["Close_B"].to_numpy(dtype=float) if has_b else np.ones(n_hist)

    # Second asset modelled on the first (r_B = alpha + beta * r_A + noise) wherever it must be synthesised.
    beta_b, alpha_b, resid_std_b, sigma_a = 1.0, 0.0, 0.0, 0.0
    if n_hist > 1:
        sigma_a = float(np.std(hist_ret_a, ddof=1))
        if has_b:
            cov = np.cov(hist_ret_a, hist_ret_b)
            if cov[0, 0] > 0:
                beta_b = cov[0, 1] / cov[0, 0]
                alpha_b = hist_ret_b.mean() - beta_b * hist_ret_a.mean()
                resid_std_b = float(np.std(hist_ret_b - (alpha_b + beta_b * hist_ret_a), ddof=1))

    # Real history already contains a leveraged ETF's volatility decay; only synthetic months need it.
    vol_drag = 0.5 * (beta_b * sigma_a) ** 2 if (p.vol_drag and has_b) else 0.0

    # --- Rolling history: every month is a start; shortfalls are filled with the scenario ---
    splice_rng = np.random.RandomState(_SPLICE_SEED)
    ret_a_hist = np.zeros((months, n_hist))
    ret_b_hist = np.zeros((months, n_hist))
    div_a_hist = np.zeros((months, n_hist))
    win_lens = np.minimum(months, n_hist - np.arange(n_hist))

    for i in range(n_hist):
        win = int(win_lens[i])
        fut = months - win
        ret_a_hist[:win, i] = hist_ret_a[i:i + win] - m_disc
        div_a_hist[:win, i] = hist_div_a[i:i + win]
        if has_b:
            ret_b_hist[:win, i] = hist_ret_b[i:i + win] - m_disc
        if fut > 0:
            mr = future[:fut] - m_disc
            ret_a_hist[win:, i] = mr
            if has_b:
                noise = splice_rng.normal(0, resid_std_b, size=fut) if resid_std_b > 0 else 0.0
                ret_b_hist[win:, i] = alpha_b + mr * beta_b + noise - vol_drag
            p_end = close_a[i + win - 1]
            path = np.cumprod(np.concatenate(([p_end], 1 + mr)))
            p_prev, p_next = path[:-1], path[1:]
            base_div = p_end * p.base_div_yield / 12.0
            div_amt = np.maximum(base_div * 0.1, base_div * (1 + ((p_next / p_end) - 1) * p.div_beta))
            with np.errstate(divide='ignore', invalid='ignore'):
                div_a_hist[win:, i] = np.where(p_prev > 0, div_amt / p_prev, 0.0)

    _inject_swan(ret_a_hist, ret_b_hist, p.swan_month, p.swan_drop, beta_b, has_b)

    if random_job_loss:
        caps_hist = simulate_unemployment(ret_a_hist, p.salary_cap, p.job_loss,
                                          np.random.RandomState(_HIST_JOB_LOSS_SEED))
    else:
        caps_hist = np.repeat(base_caps.reshape(-1, 1), n_hist, axis=1)

    common = dict(payments=schedule.payments, principal=p.principal, buffer_cash=buffer_cash, fee=p.fee,
                  reinvest=p.reinvest, ratio_b=ratio_b, order=p.source_order,
                  haircut_trigger=p.haircut_trigger, haircut_penalty=p.haircut_penalty, dca_mode=p.dca_mode)

    hist = simulate_paths(ret_a_hist, ret_b_hist, div_a_hist, close_a, close_b, salary_cap=caps_hist, **common)
    df_hist = pd.DataFrame({
        "Start_Date": df.index, "Is_Ruined": hist.ruined, "Is_Spliced": win_lens < months,
        "Lev_Final": hist.lev_final, "DCA_Final": hist.dca_final,
        "Lev_Win": (~hist.ruined) & (hist.lev_final > hist.dca_final),
    })

    # The ledger is the same simulation restricted to one start month, so it cannot drift from the summary.
    col = slice(anchor_idx, anchor_idx + 1)
    one = simulate_paths(ret_a_hist[:, col], ret_b_hist[:, col], div_a_hist[:, col], close_a[col], close_b[col],
                         salary_cap=caps_hist[:, col], record=True, **common)
    trace = _build_trace(df, anchor_idx, schedule, one.ledger)

    # --- Monte Carlo: block bootstrap of real monthly returns, anchored on the chosen month's price ---
    block = int(max(1, min(p.block_size, n_hist)))
    mc_ok = n_hist >= 2
    any_rate, avg_months = 0.0, 0.0
    if mc_ok:
        rng = np.random.RandomState(p.seed)
        n_paths = int(p.mc_paths)
        blocks_needed = (months // block) + 1
        starts = rng.randint(0, n_hist - block + 1, size=(blocks_needed, n_paths))
        idx = (starts[:, None, :] + np.arange(block)[None, :, None]).reshape(-1, n_paths)[:months, :]

        ret_a_mc = hist_ret_a[idx] - m_disc
        ret_b_mc = hist_ret_b[idx] - m_disc if has_b else np.zeros((months, n_paths))
        _inject_swan(ret_a_mc, ret_b_mc, p.swan_month, p.swan_drop, beta_b, has_b)

        p_a0 = close_a[anchor_idx]
        p_b0 = close_b[anchor_idx]
        div_a_mc = dividend_model_yields(p_a0 * np.cumprod(1 + ret_a_mc, axis=0), p_a0, p.base_div_yield, p.div_beta)

        if random_job_loss:
            job_rng = np.random.RandomState(None if p.seed is None else p.seed + 1)
            caps_mc = simulate_unemployment(ret_a_mc, p.salary_cap, p.job_loss, job_rng)
            unemployed = caps_mc < p.salary_cap
            any_rate = float(unemployed.any(axis=0).mean())
            avg_months = float(unemployed.sum(axis=0).mean())
        else:
            caps_mc = np.repeat(base_caps.reshape(-1, 1), n_paths, axis=1)

        mc = simulate_paths(ret_a_mc, ret_b_mc, div_a_mc, np.full(n_paths, p_a0), np.full(n_paths, p_b0),
                            salary_cap=caps_mc, **common)
        df_mc = pd.DataFrame({
            "Is_Ruined": mc.ruined, "Lev_Final": mc.lev_final, "DCA_Final": mc.dca_final,
            "Lev_Win": (~mc.ruined) & (mc.lev_final > mc.dca_final),
        })
    else:
        df_mc = pd.DataFrame(columns=["Is_Ruined", "Lev_Final", "DCA_Final", "Lev_Win"])

    return EngineResults(hist=df_hist, mc=df_mc, trace=trace, schedule=schedule, buffer_cash=buffer_cash,
                         block_size=block, mc_ok=mc_ok, vol_drag=float(vol_drag), beta_b=float(beta_b),
                         job_loss_any_rate=any_rate, job_loss_avg_months=avg_months)
