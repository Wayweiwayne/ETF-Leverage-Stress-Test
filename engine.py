"""Stress-test simulation engine: loan schedule, repayment waterfall, historical and Monte Carlo runs.

Pure NumPy/pandas with no UI imports, so the same code can sit behind Streamlit,
an HTTP API or a batch job. All randomness comes from generators created per call;
nothing touches NumPy's global random state, which keeps concurrent runs independent.
"""
import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

SALARY, DIVIDEND, BUFFER, SELL, SELL_B = "salary", "dividend", "buffer", "sell", "sell_b"
# SELL liquidates the main asset, SELL_B the second one that reinvested dividends bought.
SOURCES = (SALARY, DIVIDEND, BUFFER, SELL, SELL_B)

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

# Where Monte Carlo dividends come from.
MC_DIVIDENDS_HISTORY = "history"  # the dividend actually paid in each resampled month
MC_DIVIDENDS_MODEL = "model"      # the assumed future yield (base_div_yield, div_beta)

_SPLICE_SEED = 20240601
_BACKFILL_SEED = 20240602
_HIST_JOB_LOSS_SEED = 13572468
# With random job loss every start month is simulated under several unemployment draws.
_HIST_MAX_PATHS = 10_000
_HIST_MAX_REPLICATES = 100
# Fewer overlapping months than this is too little to estimate how the second asset follows the first.
_MIN_OVERLAP_FOR_BETA = 12
# Seed for the safety-limit searches when none is set: every evaluation must draw the same paths.
_SOLVE_SEED = 42
_SOLVE_FIELDS = ("principal", "salary_cap")


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
    mc_dividends: str = MC_DIVIDENDS_HISTORY

    # Floating rate: change in the annual rate, in percentage points, at the start of loan year 2, 3, ...
    rate_path_pct: tuple = ()
    # Monte Carlo only: standard deviation of a further random change each year, in percentage points.
    rate_volatility_pct: float = 0.0

    # Taxes and fees. All zero by default; a front end supplies the rates of its jurisdiction.
    sell_tax: float = 0.0                 # securities transaction tax on every sale
    dividend_tax_rate: float = 0.0        # net income tax on dividends
    nhi_rate: float = 0.0                 # health-insurance levy on a single payout ...
    nhi_threshold: float = 20_000.0       # ... of at least this much
    dividend_taxable_share: float = 1.0   # part of a payout that counts as dividend income
    loan_fee: float = 0.0                 # one-off fee taken out of the loan proceeds

    # Modelled dividends are paid every this many months; 0 means as often as the asset's record shows.
    dividend_interval_months: int = 1


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
    ruin_month: np.ndarray      # month in which the payment was missed, 0 if never
    out_of_pocket: np.ndarray   # salary paid in over the whole term
    dca_invested: np.ndarray    # what the comparison portfolio put in
    ledger: dict | None = None  # per-month arrays of shape (months, paths) when record=True
    value_quantiles: dict | None = None  # per-month quantiles across paths when `quantiles` is given
    flows: dict | None = None   # per-month salary and comparison contributions when keep_flows=True


@dataclass
class EngineResults:
    hist: pd.DataFrame          # one row per entry month
    mc: pd.DataFrame            # one row per Monte Carlo path
    schedule: LoanSchedule
    buffer_cash: float
    block_size: int
    mc_ok: bool
    vol_drag: float             # monthly volatility decay applied to modelled second-asset returns
    beta_b: float
    job_loss_any_rate: float
    job_loss_avg_months: float
    mc_dividend_yield: float    # average annual dividend yield across the Monte Carlo paths
    dividend_interval: int      # months between modelled payouts actually used
    mc_final_rate_p5: float     # annual loan rate (%) in the last month across Monte Carlo paths
    mc_final_rate_p95: float
    hist_replicates: int        # unemployment draws per entry month (1 unless job loss is random)
    modelled_b_months: int      # historical months in which the second asset had to be modelled
    trace: pd.DataFrame | None = None  # month-by-month ledger of one entry month
    mc_fan: pd.DataFrame | None = None  # per-month range of net worth across the Monte Carlo paths


@dataclass
class _Market:
    n: int
    ret_a: np.ndarray
    div_a: np.ndarray
    close_a: np.ndarray
    synthetic_a: np.ndarray
    has_b: bool
    ret_b: np.ndarray
    close_b: np.ndarray
    modelled_b_months: int
    beta_b: float
    resid_std_b: float
    decay: float
    dividend_interval: int


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


def parse_rate_path(text):
    """Parse "0.25, 0.25, -0.125" into yearly rate changes in percentage points."""
    try:
        values = tuple(float(x.strip()) for x in str(text).split(",") if x.strip())
    except ValueError:
        raise ValueError("每年利率變動必須是用逗號分開的數字，例如「0.25, 0.25, -0.125」。") from None
    if any((not np.isfinite(v)) or abs(v) > 10 for v in values):
        raise ValueError("每年利率變動必須介於 -10 與 10 個百分點之間。")
    return values


def annual_rate_path(annual_rate_pct, total_months, shock_year=0, shock_delta_pct=0.0, rate_path_pct=()):
    """The loan's annual rate in percent for every month.

    A one-off shock applies from the first month of `shock_year`. `rate_path_pct[k]` is a further
    change at the start of loan year k + 2 (the first year's rate is the contract rate); once the
    list runs out the rate stays where it is. The rate never goes below zero.
    """
    rates = np.full(total_months, float(annual_rate_pct))
    if shock_year > 0:
        rates[(shock_year - 1) * 12:] += shock_delta_pct
    for k, delta in enumerate(rate_path_pct):
        rates[(k + 1) * 12:] += delta
    return np.maximum(rates, 0.0)


def schedule_from_rates(principal, annual_rates_pct, grace_months):
    """Payment schedule for a rate that may change month by month.

    `annual_rates_pct` has shape (months,) or (months, paths). Interest-only during the grace
    period; afterwards each month's payment is the level payment that clears the outstanding
    balance over the remaining term at that month's rate. With an unchanged rate that is the
    ordinary fixed instalment; when the rate moves the instalment is re-set and the term stays.
    """
    rates = np.asarray(annual_rates_pct, dtype=float) / 100 / 12
    months = rates.shape[0]
    payments, start_bal, end_bal = np.zeros_like(rates), np.zeros_like(rates), np.zeros_like(rates)
    bal = np.full(rates.shape[1:], float(principal))
    for t in range(months):
        r = rates[t]
        start_bal[t] = bal
        interest = bal * r
        if t < grace_months:
            pmt, principal_paid = interest, 0.0
        else:
            n_left = months - t
            with np.errstate(divide='ignore', invalid='ignore'):
                pmt = np.where(r > 0, bal * r / (1 - (1 + r) ** -n_left), bal / n_left)
            principal_paid = np.maximum(pmt - interest, 0.0)
        payments[t] = pmt
        bal = np.maximum(bal - principal_paid, 0.0)
        end_bal[t] = bal
    return LoanSchedule(payments, rates, start_bal, end_bal)


def build_loan_schedule(principal, annual_rate_pct, total_months, grace_months=0,
                        shock_year=0, shock_delta_pct=0.0, rate_path_pct=()):
    """Month-by-month payment schedule.

    Interest-only during the grace period, level amortisation afterwards. Whenever the rate
    changes (see annual_rate_path) the payment is recomputed on the outstanding balance over
    the remaining term; the term itself does not change.
    """
    if total_months < 1:
        raise ValueError("貸款期數至少需要 1 個月。")
    if not 0 <= grace_months < total_months:
        raise ValueError("寬限期必須短於貸款總年限。")
    rates = annual_rate_path(annual_rate_pct, total_months, shock_year, shock_delta_pct, rate_path_pct)
    return schedule_from_rates(principal, rates, grace_months)


def monte_carlo_rate_paths(p, rng, n_paths):
    """Annual loan rate (%) per month for the Monte Carlo: the set path plus a random walk.

    Each loan year after the first, every path's rate moves by a further normal draw with
    standard deviation `rate_volatility_pct`; the moves accumulate. Without volatility this is
    just the deterministic path, returned with shape (months,).
    """
    base = annual_rate_path(p.annual_rate_pct, p.total_months, p.rate_shock_year, p.rate_shock_delta_pct,
                            p.rate_path_pct)
    if p.rate_volatility_pct <= 0:
        return base
    years = -(-p.total_months // 12)
    moves = rng.normal(0.0, p.rate_volatility_pct, size=(years, n_paths))
    moves[0] = 0.0
    drift = np.repeat(np.cumsum(moves, axis=0), 12, axis=0)[:p.total_months]
    return np.maximum(base[:, None] + drift, 0.0)


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
                   dca_mode=DCA_MATCH_OUT_OF_POCKET, record=False, sell_tax=0.0, dividend_tax_rate=0.0,
                   nhi_rate=0.0, nhi_threshold=0.0, dividend_taxable_share=1.0, loan_fee=0.0,
                   quantiles=None, keep_flows=False):
    """Run the leveraged strategy and its no-loan comparison over every path at once.

    Return/yield matrices are (months, paths); `salary_cap` has the same shape. A month's
    dividend yield is the cash paid per share as a fraction of the previous month's price. Each
    month the payment is collected from `order` in turn; a path that cannot cover it from the
    sources listed is ruined for good and its final value is zero, whatever it still holds in
    sources left out of `order`. A forced sale in a crash month costs extra for either asset.

    `payments` is (months,) or, when each path has its own loan rate, (months, paths). Every sale
    pays `fee` plus `sell_tax`. Each dividend payout loses `dividend_tax_rate` of its taxable share,
    plus `nhi_rate` of it when that share reaches `nhi_threshold`; the comparison portfolio is taxed
    by the same rules on its own, smaller payouts. With `record=True` the per-month ledger is
    returned as well. `quantiles` asks for those quantiles of net worth across paths in every
    month (a ruined path counts as zero), and `keep_flows` for each month's salary payment and
    comparison contribution per path.
    """
    if dca_mode not in (DCA_MATCH_OUT_OF_POCKET, DCA_FULL_PAYMENT):
        raise ValueError(f"未知的 DCA 對照模式：{dca_mode}")
    order = _unique_order(order)
    months, n_paths = ret_a.shape

    prices_a = np.array(price_a0, dtype=float)
    prices_b = np.array(price_b0, dtype=float)
    shares_a = (principal - buffer_cash - loan_fee) * (1 - fee) / prices_a
    exit_cost = fee + sell_tax
    shares_b = np.zeros(n_paths)
    div_pools = np.zeros(n_paths)
    buf_vals = np.full(n_paths, float(buffer_cash))
    is_ruined = np.zeros(n_paths, dtype=bool)
    ruin_month = np.zeros(n_paths, dtype=int)
    out_of_pocket = np.zeros(n_paths)
    dca_invested = np.zeros(n_paths)
    spread = {"lev": [], "dca": [], "alive": []} if quantiles is not None else None
    flows = {"salary": [], "dca": []} if keep_flows else None

    dca_shares_a = np.zeros(n_paths)
    dca_shares_b = np.zeros(n_paths)
    dca_div_pools = np.zeros(n_paths)

    ledger = {k: [] for k in (
        "from_dividend", "from_buffer", "from_sell", "from_sell_b", "from_salary", "defaulted",
        "shares_a", "shares_b", "lev_value", "dca_value", "dca_contribution", "dividend_tax")} if record else None

    def lev_value():
        value = shares_a * prices_a * (1 - exit_cost) + div_pools + buf_vals
        return value + shares_b * prices_b * (1 - exit_cost) if reinvest else value

    def dca_value():
        value = dca_shares_a * prices_a * (1 - exit_cost) + dca_div_pools
        return value + dca_shares_b * prices_b * (1 - exit_cost) if reinvest else value

    def dividend_levy(gross):
        taxable = gross * dividend_taxable_share
        return taxable * dividend_tax_rate + np.where(taxable >= nhi_threshold, taxable * nhi_rate, 0.0)

    for i in range(months):
        pmt = payments[i]
        ret_a_i = ret_a[i, :]
        prev_a = prices_a
        prices_a = prices_a * (1 + ret_a_i)
        prices_b = prices_b * (1 + ret_b[i, :])
        div_per_share = prev_a * div_yield_a[i, :]

        gross_div = shares_a * div_per_share
        levy = dividend_levy(gross_div)
        current_div = gross_div - levy
        # A second asset that has gone to zero can no longer be bought; its share of the dividend buys the first.
        share_to_b = np.where(prices_b > 0, ratio_b, 0.0)
        with np.errstate(divide='ignore', invalid='ignore'):
            if reinvest:
                shares_b = shares_b + np.where(prices_b > 0, (current_div * share_to_b * (1 - fee)) / prices_b, 0.0)
                shares_a = shares_a + np.where(prices_a > 0, (current_div * (1 - share_to_b) * (1 - fee)) / prices_a, 0.0)
            else:
                div_pools = div_pools + current_div

        sell_cost = np.full(n_paths, exit_cost, dtype=float)
        if haircut_penalty > 0:
            sell_cost = np.where(ret_a_i < -haircut_trigger, np.minimum(0.99, exit_cost + haircut_penalty), exit_cost)

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
            elif src == SELL_B:
                pay = np.minimum(np.maximum(shares_b * prices_b * (1 - sell_cost), 0.0), rem)
                with np.errstate(divide='ignore', invalid='ignore'):
                    shares_b = shares_b - np.where(prices_b > 0, (pay / (1 - sell_cost)) / prices_b, 0.0)
            else:
                pay = np.minimum(np.maximum(salary_cap[i, :], 0.0), rem)
            used[src] = pay
            rem = rem - pay

        defaulted = (rem > 1e-5) & (~is_ruined)

        if dca_mode == DCA_FULL_PAYMENT:
            contribution = np.broadcast_to(np.asarray(pmt, dtype=float), (n_paths,)).copy()
        else:
            # A path that already went bust no longer pays anything; its comparison portfolio
            # keeps investing what salary could have covered.
            contribution = np.where(is_ruined, np.minimum(pmt, np.maximum(salary_cap[i, :], 0.0)), used[SALARY])
        is_ruined = is_ruined | defaulted
        ruin_month[defaulted] = i + 1
        out_of_pocket = out_of_pocket + used[SALARY]
        dca_invested = dca_invested + contribution

        dca_gross = dca_shares_a * div_per_share
        dca_divs = dca_gross - dividend_levy(dca_gross)
        with np.errstate(divide='ignore', invalid='ignore'):
            if reinvest:
                dca_shares_b = dca_shares_b + np.where(prices_b > 0, (dca_divs * share_to_b * (1 - fee)) / prices_b, 0.0)
                dca_shares_a = dca_shares_a + np.where(
                    prices_a > 0, ((dca_divs * (1 - share_to_b) + contribution) * (1 - fee)) / prices_a, 0.0)
            else:
                dca_div_pools = dca_div_pools + dca_divs
                dca_shares_a = dca_shares_a + np.where(
                    prices_a > 0, ((contribution + dca_div_pools) * (1 - fee)) / prices_a, 0.0)
                dca_div_pools = np.zeros(n_paths)

        if spread is not None:
            spread["lev"].append(np.quantile(np.where(is_ruined, 0.0, lev_value()), quantiles))
            spread["dca"].append(np.quantile(dca_value(), quantiles))
            spread["alive"].append(1.0 - is_ruined.mean())
        if keep_flows:
            flows["salary"].append(used[SALARY])
            flows["dca"].append(contribution)
        if record:
            ledger["from_dividend"].append(used[DIVIDEND])
            ledger["from_buffer"].append(used[BUFFER])
            ledger["from_sell"].append(used[SELL])
            ledger["from_sell_b"].append(used[SELL_B])
            ledger["from_salary"].append(used[SALARY])
            ledger["defaulted"].append(defaulted)
            ledger["shares_a"].append(shares_a)
            ledger["shares_b"].append(shares_b)
            ledger["lev_value"].append(lev_value())
            ledger["dca_value"].append(dca_value())
            ledger["dca_contribution"].append(contribution)
            ledger["dividend_tax"].append(levy)

    lev_final = lev_value()
    lev_final[is_ruined] = 0
    if record:
        ledger = {k: np.array(v) for k, v in ledger.items()}
    if spread is not None:
        spread = {k: np.array(v) for k, v in spread.items()}
    if keep_flows:
        flows = {k: np.array(v) for k, v in flows.items()}
    return PathResults(is_ruined, lev_final, dca_value(), ruin_month, out_of_pocket, dca_invested,
                       ledger, spread, flows)


def annual_irr(paid_in, final_value, iterations=40):
    """Money-weighted annual return for every path.

    `paid_in` (months, paths) is what went in at the end of each month and `final_value` what
    was there at the end of the last one. The result is the constant yearly return that turns
    the former into the latter: NaN where nothing was paid in, -1 where nothing was left.
    """
    paid_in = np.asarray(paid_in, dtype=float)
    final_value = np.asarray(final_value, dtype=float)
    months, n_paths = paid_in.shape
    t = np.arange(1, months + 1)[:, None]
    lo, hi = np.full(n_paths, -0.99), np.full(n_paths, 1.0)       # monthly rate
    for _ in range(iterations):
        mid = (lo + hi) / 2
        log_growth = np.log1p(mid)
        npv = final_value * np.exp(-months * log_growth) - (paid_in * np.exp(-t * log_growth[None, :])).sum(axis=0)
        lo, hi = np.where(npv > 0, mid, lo), np.where(npv > 0, hi, mid)
    annual = (1 + (lo + hi) / 2) ** 12 - 1
    annual = np.where(final_value <= 0, -1.0, annual)
    return np.where(paid_in.sum(axis=0) <= 0, np.nan, annual)


FAN_QUANTILES = (0.05, 0.25, 0.50, 0.75, 0.95)


def lump_dividends(monthly_amounts, interval):
    """Turn an even monthly payout into one every `interval` months (months run along axis 0).

    A payout month pays `interval` times its monthly amount and the months in between pay nothing,
    so the annual total is about the same while the cash arrives in fewer, larger pieces.
    """
    if interval <= 1:
        return monthly_amounts
    out = np.zeros_like(monthly_amounts)
    paying = (np.arange(monthly_amounts.shape[0]) + 1) % interval == 0
    out[paying] = monthly_amounts[paying] * interval
    return out


def infer_dividend_interval(div_yields, window=36):
    """Months between payouts suggested by the latest record: 1, 3, 6 or 12."""
    recent = np.asarray(div_yields)[-window:]
    payouts = int((recent > 0).sum())
    if payouts == 0:
        return 1
    gap = len(recent) / payouts
    return min((1, 3, 6, 12), key=lambda k: abs(np.log(k / gap)))


def dividend_model_yields(price_path, p_init, base_ann_yield, beta, interval=1):
    """Dividend-beta model: payout scales with cumulative return, floored at 10% of the base amount.

    Returned as a fraction of the previous month's price, the convention simulate_paths expects.
    """
    base_div_amt = p_init * base_ann_yield / 12.0
    cum_ret = (price_path / p_init) - 1.0
    div_amt = lump_dividends(np.maximum(base_div_amt * 0.1, base_div_amt * (1 + cum_ret * beta)), interval)
    previous = np.concatenate((np.full_like(price_path[:1], p_init), price_path[:-1]), axis=0)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(previous > 0, div_amt / previous, 0.0)


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


def validate_params(p):
    """Reject settings the simulation cannot give a meaningful answer for."""
    def need(ok, message):
        if not ok:
            raise ValueError(message)

    finite = np.isfinite
    need(finite(p.principal) and p.principal > 0, "貸款本金必須大於 0。")
    need(finite(p.annual_rate_pct) and p.annual_rate_pct >= 0, "貸款利率不可為負。")
    need(p.annual_rate_pct + p.rate_shock_delta_pct >= 0, "升息後的利率不可為負。")
    need(int(p.total_months) == p.total_months and p.total_months >= 1, "貸款期數至少需要 1 個月。")
    need(0 <= p.grace_months < p.total_months, "寬限期必須短於貸款總年限。")
    need(p.rate_shock_year >= 0 and p.buffer_months >= 0, "升息年份與緩衝月數不可為負。")
    need(0 <= p.reinvest_ratio_b <= 1, "配息投入第二標的的比例必須介於 0 與 1。")
    need(0 <= p.fee < 1, "手續費必須介於 0 與 100% 之間。")
    need(finite(p.salary_cap) and p.salary_cap >= 0, "每月薪水補貼上限不可為負。")
    need(0 <= p.haircut_penalty < 1 and p.haircut_trigger >= 0, "賤賣折價設定超出範圍。")
    need(0 <= p.swan_drop <= 1 and p.swan_month >= 0, "黑天鵝跌幅必須介於 0 與 100% 之間。")
    need(p.base_div_yield >= 0 and p.div_beta >= 0, "股息率與股息連動程度不可為負。")
    need(len(p.future_annual_returns) >= 1 and all(finite(r) and r > -100 for r in p.future_annual_returns),
         "未來情境的年度報酬率必須大於 -100%。")
    need(1 <= p.mc_paths <= 100_000, "蒙地卡羅次數必須介於 1 與 100,000。")
    need(p.block_size >= 1, "區塊長度至少 1 個月。")
    need(p.dca_mode in (DCA_MATCH_OUT_OF_POCKET, DCA_FULL_PAYMENT), f"未知的 DCA 對照模式：{p.dca_mode}")
    need(p.mc_dividends in (MC_DIVIDENDS_HISTORY, MC_DIVIDENDS_MODEL), f"未知的蒙地卡羅配息來源：{p.mc_dividends}")
    need(all(finite(d) and abs(d) <= 10 for d in p.rate_path_pct), "每年利率變動必須介於 -10 與 10 個百分點之間。")
    need(finite(p.rate_volatility_pct) and 0 <= p.rate_volatility_pct <= 5, "利率隨機波動必須介於 0 與 5 個百分點。")
    need(0 <= p.sell_tax < 1 and p.fee + p.sell_tax < 1, "賣出的稅費合計必須低於 100%。")
    need(0 <= p.dividend_tax_rate <= 1 and 0 <= p.nhi_rate <= 1 and p.dividend_tax_rate + p.nhi_rate <= 1,
         "股利的稅率與補充保費費率必須介於 0 與 100%，合計不可超過 100%。")
    need(p.nhi_threshold >= 0 and 0 <= p.dividend_taxable_share <= 1, "補充保費門檻或股利所得比例超出範圍。")
    need(finite(p.loan_fee) and 0 <= p.loan_fee < p.principal, "貸款開辦費必須小於貸款本金。")
    need(p.dividend_interval_months in (0, 1, 3, 6, 12), "配息頻率必須是每 1、3、6 或 12 個月（或 0 代表依歷史判斷）。")
    _unique_order(p.source_order)
    job = p.job_loss
    need(job.mode in (JOB_LOSS_NONE, JOB_LOSS_MANUAL, JOB_LOSS_RANDOM), f"未知的失業模型：{job.mode}")
    need(job.unemployed_salary >= 0, "失業期間的薪水支援不可為負。")
    if job.mode == JOB_LOSS_RANDOM:
        need(0 <= job.annual_prob <= 1, "年失業機率必須介於 0 與 1。")
        need(job.mean_duration > 0, "平均失業月數必須大於 0。")
        need(job.distribution in ("lognormal", "poisson"), f"未知的失業時間分佈：{job.distribution}")
        need(0 <= job.crash_extra_low <= job.crash_extra_high <= 1, "崩盤時額外失業機率的範圍不正確。")


def bootstrap_indices(rng, n, block, months, n_paths):
    """Row indices for a circular block bootstrap, shape (months, n_paths).

    Blocks may start anywhere and wrap from the last month back to the first, so every month
    of the record is equally likely to be drawn. Without wrapping, the first and last months
    would appear less often than the rest.
    """
    blocks_needed = -(-months // block)
    starts = rng.randint(0, n, size=(blocks_needed, n_paths))
    idx = (starts[:, None, :] + np.arange(block)[None, :, None]) % n
    return idx.reshape(-1, n_paths)[:months, :]


def monte_carlo_inputs(m, p, rng):
    """Resampled returns and dividend yields for every Monte Carlo path, each of shape (months, paths).

    A resampled month brings its price return, the second asset's return and, unless the
    assumed-yield model is chosen, the dividend actually paid that month. Drawing them together
    keeps a payout next to the ex-dividend price drop it caused, and gives an asset that never
    paid anything no dividends.
    """
    months, n_paths = p.total_months, int(p.mc_paths)
    m_disc = p.structural_discount_pct / 100.0 / 12.0
    idx = bootstrap_indices(rng, m.n, int(max(1, min(p.block_size, m.n))), months, n_paths)
    ret_a = m.ret_a[idx] - m_disc
    ret_b = m.ret_b[idx] - m_disc if m.has_b else np.zeros((months, n_paths))
    _inject_swan(ret_a, ret_b, p.swan_month, p.swan_drop, m.beta_b, m.has_b)
    if p.mc_dividends == MC_DIVIDENDS_HISTORY:
        div_a = m.div_a[idx]
    else:
        div_a = dividend_model_yields(np.cumprod(1 + ret_a, axis=0), 1.0, p.base_div_yield, p.div_beta,
                                      m.dividend_interval)
    return ret_a, ret_b, div_a


def _future_monthly_returns(annual_returns, months):
    if len(annual_returns) == 0:
        raise ValueError("請至少輸入一個年度報酬率。")
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


def modelled_second_asset_return(ret_a, noise, beta, decay, compounding):
    """Second-asset return for a month in which it has no real data.

    It follows the main asset with sensitivity `beta` and carries no excess return of its own:
    whatever it out- or under-performed by in the sample is not projected. With `compounding`
    the month is treated the way a daily-rebalanced leveraged fund behaves, (1 + r)^beta less
    the volatility decay beta*(beta-1)/2 * variance; without it the return is simply beta * r.
    """
    if compounding:
        base = np.maximum(1 + ret_a, 1e-9) ** beta * np.exp(-decay) - 1
    else:
        base = beta * ret_a
    return np.clip(base + noise, -1.0, 10.0)


def _prepare_market(df, p):
    n = len(df)
    if n < 1:
        raise ValueError("沒有可回測的月份。")
    ret_a = df["Price_Return_A"].to_numpy(dtype=float)
    div_a = df["Div_Yield_A"].to_numpy(dtype=float)
    close_a = df["Close_A"].to_numpy(dtype=float)
    synthetic_a = (df["Synthetic_A"].to_numpy(dtype=bool) if "Synthetic_A" in df.columns
                   else np.zeros(n, dtype=bool))

    has_b = bool(p.reinvest and "Close_B" in df.columns and df["Price_Return_B"].notna().any())
    ret_b, close_b = np.zeros(n), np.ones(n)
    beta_b, resid_std_b, decay, modelled = 1.0, 0.0, 0.0, 0
    if has_b:
        ret_b = df["Price_Return_B"].to_numpy(dtype=float).copy()
        close_b = df["Close_B"].to_numpy(dtype=float).copy()
        real = ~np.isnan(ret_b)
        if real.sum() >= _MIN_OVERLAP_FOR_BETA:
            cov = np.cov(ret_a[real], ret_b[real])
            if cov[0, 0] > 0:
                beta_b = float(cov[0, 1] / cov[0, 0])
                alpha = ret_b[real].mean() - beta_b * ret_a[real].mean()
                resid_std_b = float(np.std(ret_b[real] - (alpha + beta_b * ret_a[real]), ddof=1))
        sigma_a = float(np.std(ret_a, ddof=1)) if n > 1 else 0.0
        if p.vol_drag:
            decay = max(0.0, 0.5 * beta_b * (beta_b - 1)) * sigma_a ** 2
        missing = ~real
        modelled = int(missing.sum())
        if modelled:
            rng = np.random.RandomState(_BACKFILL_SEED)
            noise = rng.normal(0, resid_std_b, size=modelled) if resid_std_b > 0 else 0.0
            ret_b[missing] = modelled_second_asset_return(ret_a[missing], noise, beta_b, decay, p.vol_drag)
            close_b[missing] = close_b[real][0]  # only relative moves matter; any positive level will do
    interval = p.dividend_interval_months or infer_dividend_interval(div_a)
    return _Market(n, ret_a, div_a, close_a, synthetic_a, has_b, ret_b, close_b, modelled,
                   beta_b, resid_std_b, decay, int(interval))


def _history_paths(m, p):
    """Return, yield and cap inputs for every entry month.

    Entering in month i means buying at that month's price; the first payment falls due one
    month later, so the path uses the returns of months i+1 onwards. Whatever the real record
    cannot cover is filled with the scenario.
    """
    months, n = p.total_months, m.n
    m_disc = p.structural_discount_pct / 100.0 / 12.0
    future = _future_monthly_returns(p.future_annual_returns, months)
    splice_rng = np.random.RandomState(_SPLICE_SEED)

    ret_a = np.zeros((months, n))
    ret_b = np.zeros((months, n))
    div_a = np.zeros((months, n))
    win_lens = np.minimum(months, n - 1 - np.arange(n))

    for i in range(n):
        win = int(win_lens[i])
        fut = months - win
        rows = slice(i + 1, i + 1 + win)
        ret_a[:win, i] = m.ret_a[rows] - m_disc
        div_a[:win, i] = m.div_a[rows]
        if m.has_b:
            ret_b[:win, i] = m.ret_b[rows] - m_disc
        if fut > 0:
            mr = future[:fut] - m_disc
            ret_a[win:, i] = mr
            if m.has_b:
                noise = splice_rng.normal(0, m.resid_std_b, size=fut) if m.resid_std_b > 0 else 0.0
                ret_b[win:, i] = modelled_second_asset_return(mr, noise, m.beta_b, m.decay, p.vol_drag)
            p_end = m.close_a[i + win]
            path = np.cumprod(np.concatenate(([p_end], 1 + mr)))
            p_prev, p_next = path[:-1], path[1:]
            base_div = p_end * p.base_div_yield / 12.0
            div_amt = np.maximum(base_div * 0.1, base_div * (1 + ((p_next / p_end) - 1) * p.div_beta))
            div_amt = lump_dividends(div_amt, m.dividend_interval)
            with np.errstate(divide='ignore', invalid='ignore'):
                div_a[win:, i] = np.where(p_prev > 0, div_amt / p_prev, 0.0)

    _inject_swan(ret_a, ret_b, p.swan_month, p.swan_drop, m.beta_b, m.has_b)

    # An entry month counts as backfilled when it, or any real month it relies on, uses proxy data.
    synthetic_before = np.concatenate(([0], np.cumsum(m.synthetic_a)))
    backfilled = (synthetic_before[np.arange(n) + win_lens + 1] - synthetic_before[np.arange(n)]) > 0
    return ret_a, ret_b, div_a, win_lens, backfilled


def _history_caps(ret_a_hist, p):
    """Salary caps for every entry month, repeated over several unemployment draws when random."""
    months, n = ret_a_hist.shape
    if p.job_loss.mode != JOB_LOSS_RANDOM:
        base = salary_cap_schedule(p.salary_cap, p.job_loss, months)
        return np.repeat(base.reshape(-1, 1), n, axis=1), 1
    replicates = int(np.clip(_HIST_MAX_PATHS // n, 1, _HIST_MAX_REPLICATES))
    caps = simulate_unemployment(np.tile(ret_a_hist, (1, replicates)), p.salary_cap, p.job_loss,
                                 np.random.RandomState(_HIST_JOB_LOSS_SEED))
    return caps, replicates


def _common_args(p, schedule, buffer_cash, ratio_b):
    return dict(payments=schedule.payments, principal=p.principal, buffer_cash=buffer_cash, fee=p.fee,
                reinvest=p.reinvest, ratio_b=ratio_b, order=p.source_order,
                haircut_trigger=p.haircut_trigger, haircut_penalty=p.haircut_penalty, dca_mode=p.dca_mode,
                sell_tax=p.sell_tax, dividend_tax_rate=p.dividend_tax_rate, nhi_rate=p.nhi_rate,
                nhi_threshold=p.nhi_threshold, dividend_taxable_share=p.dividend_taxable_share,
                loan_fee=p.loan_fee)


def _setup(df, p):
    validate_params(p)
    market = _prepare_market(df, p)
    schedule = build_loan_schedule(p.principal, p.annual_rate_pct, p.total_months, p.grace_months,
                                   p.rate_shock_year, p.rate_shock_delta_pct, p.rate_path_pct)
    # The fee comes out of the proceeds first; the buffer can take at most what is left.
    buffer_cash = min(buffer_cash_for(schedule, p.grace_months, p.buffer_months, p.principal),
                      p.principal - p.loan_fee)
    ratio_b = p.reinvest_ratio_b if market.has_b else 0.0
    return market, schedule, _common_args(p, schedule, buffer_cash, ratio_b), buffer_cash


def _monte_carlo(m, p, schedule, common, detail):
    """Block-bootstrap Monte Carlo over every path; needs at least two months of data.

    `detail` adds the per-month net-worth range and the cash flows run_summary reports; whether
    a path is ruined does not depend on it. Returns the PathResults, the share of paths that were
    ever unemployed, the average months unemployed, the average annual dividend yield and the
    5th and 95th percentile of the final annual loan rate.
    """
    months, n_paths = p.total_months, int(p.mc_paths)
    any_rate, avg_months = 0.0, 0.0
    ret_a_mc, ret_b_mc, div_a_mc = monte_carlo_inputs(m, p, np.random.RandomState(p.seed))
    mc_dividend_yield = float(div_a_mc.mean() * 12)

    if p.job_loss.mode == JOB_LOSS_RANDOM:
        job_rng = np.random.RandomState(None if p.seed is None else p.seed + 1)
        caps_mc = simulate_unemployment(ret_a_mc, p.salary_cap, p.job_loss, job_rng)
        unemployed = caps_mc < p.salary_cap
        any_rate = float(unemployed.any(axis=0).mean())
        avg_months = float(unemployed.sum(axis=0).mean())
    else:
        base = salary_cap_schedule(p.salary_cap, p.job_loss, months)
        caps_mc = np.repeat(base.reshape(-1, 1), n_paths, axis=1)

    # Each path may carry its own loan rate, hence its own payments.
    rate_rng = np.random.RandomState(None if p.seed is None else p.seed + 2)
    rates_mc = monte_carlo_rate_paths(p, rate_rng, n_paths)
    final_rates = np.atleast_1d(rates_mc[-1])
    rate_p5, rate_p95 = (float(np.percentile(final_rates, q)) for q in (5, 95))
    payments_mc = (schedule_from_rates(p.principal, rates_mc, p.grace_months).payments
                   if rates_mc.ndim == 2 else schedule.payments)

    # Only relative price moves matter, so every path starts from a price of 1.
    mc = simulate_paths(ret_a_mc, ret_b_mc, div_a_mc, np.ones(n_paths), np.ones(n_paths),
                        salary_cap=caps_mc, quantiles=FAN_QUANTILES if detail else None, keep_flows=detail,
                        **{**common, "payments": payments_mc})
    return mc, any_rate, avg_months, mc_dividend_yield, rate_p5, rate_p95


def run_summary(df, params):
    """Run both engines on aligned monthly data (see market_data.align_months).

    Rolling history: one row per entry month. Monte Carlo: one row per path; it resamples the
    whole record and does not depend on any particular entry month.
    """
    p = params
    m, schedule, common, buffer_cash = _setup(df, p)
    months, n = p.total_months, m.n

    # --- Rolling history ---
    ret_a_hist, ret_b_hist, div_a_hist, win_lens, backfilled = _history_paths(m, p)
    caps_hist, reps = _history_caps(ret_a_hist, p)
    tile = (lambda x: np.tile(x, (1, reps))) if reps > 1 else (lambda x: x)
    hist = simulate_paths(tile(ret_a_hist), tile(ret_b_hist), tile(div_a_hist),
                          np.tile(m.close_a, reps), np.tile(m.close_b, reps), salary_cap=caps_hist, **common)
    ruined = hist.ruined.reshape(reps, n)
    lev = hist.lev_final.reshape(reps, n)
    dca = hist.dca_final.reshape(reps, n)
    alive = (~ruined).any(axis=0)
    survivors = np.full(n, np.nan)
    survivors[alive] = np.nanmedian(np.where(ruined, np.nan, lev)[:, alive], axis=0)
    ruin_prob = ruined.mean(axis=0)
    df_hist = pd.DataFrame({
        "Start_Date": df.index,
        "Ruin_Prob": ruin_prob,
        "Is_Ruined": ruin_prob > 0.5,
        "Is_Spliced": win_lens < months,
        "Is_Backfilled": backfilled,
        "Lev_Final": np.median(lev, axis=0),
        "Lev_Final_Survivors": survivors,
        "DCA_Final": np.median(dca, axis=0),
        "Lev_Win": ((~ruined) & (lev > dca)).mean(axis=0),
    })

    # --- Monte Carlo: block bootstrap of the monthly record ---
    block = int(max(1, min(p.block_size, n)))
    mc_ok = n >= 2
    any_rate, avg_months, mc_dividend_yield = 0.0, 0.0, 0.0
    rate_p5 = rate_p95 = float(schedule.monthly_rates[-1] * 12 * 100)
    if mc_ok:
        mc, any_rate, avg_months, mc_dividend_yield, rate_p5, rate_p95 = _monte_carlo(
            m, p, schedule, common, detail=True)
        df_mc = pd.DataFrame({
            "Is_Ruined": mc.ruined, "Lev_Final": mc.lev_final, "DCA_Final": mc.dca_final,
            "Lev_Win": (~mc.ruined) & (mc.lev_final > mc.dca_final), "Ruin_Month": mc.ruin_month,
            "Out_Of_Pocket": mc.out_of_pocket, "DCA_Invested": mc.dca_invested,
            "Lev_IRR": annual_irr(mc.flows["salary"], mc.lev_final),
            "DCA_IRR": annual_irr(mc.flows["dca"], mc.dca_final),
        })
        names = [f"p{round(q * 100)}" for q in FAN_QUANTILES]
        mc_fan = pd.DataFrame(mc.value_quantiles["lev"], columns=[f"lev_{n}" for n in names])
        mc_fan[[f"dca_{n}" for n in names]] = mc.value_quantiles["dca"]
        mc_fan.insert(0, "month", np.arange(1, months + 1))
        mc_fan["alive"] = mc.value_quantiles["alive"]
        mc_fan["loan_balance"] = schedule.end_balance
    else:
        df_mc = pd.DataFrame(columns=["Is_Ruined", "Lev_Final", "DCA_Final", "Lev_Win", "Ruin_Month",
                                      "Out_Of_Pocket", "DCA_Invested", "Lev_IRR", "DCA_IRR"])
        mc_fan = None

    return EngineResults(hist=df_hist, mc=df_mc, schedule=schedule, buffer_cash=buffer_cash,
                         block_size=block, mc_ok=mc_ok, vol_drag=float(m.decay), beta_b=float(m.beta_b),
                         job_loss_any_rate=any_rate, job_loss_avg_months=avg_months,
                         mc_dividend_yield=mc_dividend_yield, dividend_interval=m.dividend_interval,
                         mc_final_rate_p5=rate_p5, mc_final_rate_p95=rate_p95,
                         hist_replicates=reps, modelled_b_months=m.modelled_b_months, mc_fan=mc_fan)


def run_trace(df, params, anchor_idx):
    """Month-by-month ledger for one entry month.

    It reruns the very simulation behind that month's row in the rolling-history results, so the
    two cannot drift apart. Row k is the k-th month after entry. With random job loss it shows the
    first of that month's unemployment draws.
    """
    p = params
    m, schedule, common, _ = _setup(df, p)
    if not 0 <= anchor_idx < m.n:
        raise ValueError("進場月份超出資料範圍。")
    ret_a_hist, ret_b_hist, div_a_hist, _, _ = _history_paths(m, p)
    caps_hist, _ = _history_caps(ret_a_hist, p)
    col = slice(anchor_idx, anchor_idx + 1)
    one = simulate_paths(ret_a_hist[:, col], ret_b_hist[:, col], div_a_hist[:, col], m.close_a[col],
                         m.close_b[col], salary_cap=caps_hist[:, col], record=True, **common)
    ledger = one.ledger

    months = p.total_months
    defaulted = ledger["defaulted"][:, 0]
    last = int(np.argmax(defaulted)) + 1 if defaulted.any() else months
    dates, projected = [], []
    for k in range(1, last + 1):
        row = anchor_idx + k
        if row < m.n:
            dates.append(df.index[row])
            projected.append(False)
        else:
            dates.append(df.index[-1] + pd.DateOffset(months=row - m.n + 1))
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
        "from_sell_b": ledger["from_sell_b"][:last, 0],
        "dividend_tax": ledger["dividend_tax"][:last, 0],
        "from_salary": ledger["from_salary"][:last, 0],
        "dca_contribution": ledger["dca_contribution"][:last, 0],
        "shares_a": ledger["shares_a"][:last, 0],
        "shares_b": ledger["shares_b"][:last, 0],
    })


def run(df, params, anchor_idx):
    """Both engines plus the ledger of entry month `anchor_idx`, in one call."""
    result = run_summary(df, params)
    result.trace = run_trace(df, params, anchor_idx)
    return result


@dataclass(frozen=True)
class SolveResult:
    field: str           # "principal" or "salary_cap"
    value: float | None  # the limit found, lo + k*step or hi; None when nothing in the range meets the target
    ruin_rate: float     # Monte Carlo ruin rate at `value`; with no value, at the end closest to the target
    target: float        # highest acceptable ruin rate
    status: str          # "ok", "all_meet" (the whole range meets it) or "none_meet" (none of it does)
    evaluations: int     # Monte Carlo runs actually made


def _solve_seed(params):
    return _SOLVE_SEED if params.seed is None else params.seed


def _require_monte_carlo(df):
    if len(df) < 2:
        raise ValueError("資料至少需要 2 個月才能跑蒙地卡羅模擬。")


def _mc_ruin_rate(df, p):
    """Share of Monte Carlo paths ruined, exactly as run_summary would report it, without the rolling history."""
    m, schedule, common, _ = _setup(df, p)
    return float(_monte_carlo(m, p, schedule, common, detail=False)[0].ruined.mean())


def solve_for(df, params, field, target_ruin, lo, hi, step):
    """Safety limit of one setting: the Monte Carlo ruin rate must stay at or below `target_ruin`.

    `field="principal"` finds the largest loan, `field="salary_cap"` the smallest monthly
    out-of-pocket cap, among lo, lo + step, lo + 2*step, ... up to hi, and hi itself when it is
    not on that grid. Every other setting comes from `params`. Every evaluation draws the same
    paths (seed 42 when `params.seed` is None), so the ruin rate moves with the setting alone.

    The search is a bisection that takes the ruin rate as never falling with a bigger loan and
    never rising with a higher cap. The health-levy threshold can break that by a hair; the edge
    found is then a point where the rate crosses the target, not necessarily the last one, and
    the rate reported is always one actually simulated. It runs at most
    max(2, ceil(log2((hi - lo) / step)) + 3) simulations, and exactly one when lo == hi.
    """
    if field not in _SOLVE_FIELDS:
        raise ValueError(f"求解項目必須是 principal（貸款本金）或 salary_cap（每月自掏上限），收到：{field!r}")
    if not 0 < target_ruin < 1:
        raise ValueError("目標破產率必須介於 0 與 1 之間（不含 0 與 1）。")
    if not all(np.isfinite(v) for v in (lo, hi, step)):
        raise ValueError("搜尋範圍與間距必須是有限的數字。")
    if lo > hi:
        raise ValueError("搜尋下限不可大於上限。")
    if step <= 0:
        raise ValueError("搜尋間距必須大於 0。")
    if lo < 0:
        raise ValueError("搜尋下限不可為負。")
    if field == "principal" and lo == 0:
        raise ValueError("貸款本金的搜尋下限必須大於 0。")
    _require_monte_carlo(df)

    # Grid points lo + k*step up to hi; when hi is off the grid it is one extra point past the last.
    top = int(math.floor((hi - lo) / step + 1e-9))
    on_grid = math.isclose(lo + top * step, hi, rel_tol=1e-12, abs_tol=1e-9 * step)
    last = top if on_grid else top + 1
    base = replace(params, seed=_solve_seed(params))
    rates = {}

    def value(k):
        return float(hi) if k == last else float(lo + k * step)

    def meets(k):
        if k not in rates:
            rates[k] = _mc_ruin_rate(df, replace(base, **{field: value(k)}))
        return rates[k] <= target_ruin

    def result(k, status):
        return SolveResult(field, None if status == "none_meet" else value(k), rates[k], float(target_ruin),
                           status, len(rates))

    if field == "principal":
        if meets(last):
            return result(last, "all_meet")
        if not meets(0):
            return result(0, "none_meet")
        good, bad = 0, last
    else:
        if meets(0):
            return result(0, "all_meet")
        if not meets(last):
            return result(last, "none_meet")
        good, bad = last, 0
    while abs(good - bad) > 1:
        mid = (good + bad) // 2
        if meets(mid):
            good = mid
        else:
            bad = mid
    return result(good, "ok")


def sensitivity_grid(df, params, principals, salary_caps, mc_paths=1000):
    """Monte Carlo ruin rate for every pair of loan principal (rows) and monthly out-of-pocket cap (columns).

    Rows and columns keep the order given, repeated values included. Every other setting comes
    from `params`, with `mc_paths` paths, and every cell draws the same paths (seed 42 when
    `params.seed` is None).
    """
    principals, salary_caps = list(principals), list(salary_caps)
    if not principals or not salary_caps:
        raise ValueError("貸款本金與每月自掏上限都至少要有一個值。")
    if not all(np.isfinite(v) and v > 0 for v in principals):
        raise ValueError("熱圖的貸款本金必須大於 0。")
    if not all(np.isfinite(v) and v >= 0 for v in salary_caps):
        raise ValueError("熱圖的每月自掏上限不可為負。")
    _require_monte_carlo(df)
    base = replace(params, seed=_solve_seed(params), mc_paths=mc_paths)
    rates = [[_mc_ruin_rate(df, replace(base, principal=pr, salary_cap=cap)) for cap in salary_caps]
             for pr in principals]
    return pd.DataFrame(rates, index=principals, columns=salary_caps, dtype=float)
