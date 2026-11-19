"""English text of the "How it works" page. The Chinese text is in pages/1_Model_Details.py, section by section.

`render()` draws everything below the page title. Keep the two files in the same order: test_i18n.py compares
how many headings, tables and formulas each one draws.
"""
import pandas as pd
import streamlit as st

from i18n import t
from version import DISCLAIMER


def render():
    # ------------------------------------------------------------------
    st.header("1. What is this tool calculating?")
    st.markdown(r"""
A traditional backtest asks one thing: **"If I buy and hold, how much do I end up with?"**

This tool asks a more realistic question: **"If the money was borrowed, and you must pay the loan every month, can the strategy survive the payments?"**

So it tracks two lines at the same time:

- **The asset side**: how much your stocks or ETFs are worth, and how much dividend you received.
- **The debt side**: how much you must pay the bank each month.

If in any month you can't come up with the money for the loan payment (every source of money is used up and you are still short), the strategy counts as a **default**.
""")

    st.info("**In plain words**: this is not just a return calculation. It simulates whether someone who borrows to invest gets crushed by the monthly payments along the way.")

    # ------------------------------------------------------------------
    st.header("2. How much is the monthly loan payment? (the \"Loan\" section in the sidebar)")

    st.subheader("The usual case: equal payments of principal and interest")
    st.markdown(r"""
Say you borrow principal $L$ at an annual rate $R$. The monthly rate is then $r = R / 12$.
You repay over $N$ months in total. The fixed monthly payment (PMT) uses the standard mortgage formula:
""")
    st.latex(r"PMT = L \times \frac{r(1+r)^{N}}{(1+r)^{N} - 1}")
    st.markdown("This amount stays the same every month. Early payments are mostly interest, and the principal is paid down slowly later.")

    st.subheader("Interest-only period: only interest for the first years")
    st.markdown(r"""
If you use an interest-only period, you pay only the interest for the first $g$ months:
""")
    st.latex(r"PMT_{\text{interest-only}} = L \times r")
    st.markdown(r"""
When the interest-only period ends (after month $g$), the remaining principal must be repaid in a shorter time $(N-g)$,
so the monthly payment **jumps suddenly**. This is why "Monthly payment at first" and "Monthly payment after interest-only period" on the main page often differ a lot. In real life, this jump easily catches people off guard.

The interest-only period must be shorter than the loan term (5 years at most). Personal loans usually have no interest-only period, so it is off by default for them. You can switch it on yourself if you need it.
""")

    st.subheader("Rate hike (the \"Simulate a rate hike\" switch)")
    st.markdown(r"""
When you turn on the rate hike, the tool raises the rate in the year you choose. It then recalculates the monthly payment from **the principal still left**, over **the remaining term**, at the new rate. The term stays the same, but the monthly payment gets higher.
""")

    st.subheader("Variable rate (the \"Variable rate: the rate can change every year\" switch)")
    st.markdown(r"""
Most home and personal loans have a variable rate. When you turn it on, you can set how much the rate changes each year from year 2 (in percentage points, positive or negative, and the changes add up). For example, "0.25, 0.25, 0.125":

| Loan year | Year 1 | Year 2 | Year 3 | Year 4 onward |
|---|---|---|---|---|
| Compared with the contract rate | No change | +0.25 | +0.50 | +0.625 |

Each time the rate changes, the monthly payment is recalculated with the same method as above: remaining principal, remaining months, new rate. The rate never goes below 0.

**Monte Carlo can also add random rate changes.** Nobody knows future rates, so you can set a "yearly random change (standard deviation)" $\sigma$.
At the start of each loan year, each simulated path draws one more change on top of your scheduled changes. The draw has an average of 0 and a standard deviation of $\sigma$, and the changes add up year after year.
So each path has its own rate path and its own monthly payments. The longer the term, the further the rate can drift (after $k$ years the standard deviation is about $\sigma\sqrt{k}$).
The historical backtest column is a fixed analysis. It uses only your scheduled path and adds no random changes.
""")

    # ------------------------------------------------------------------
    st.header("3. How are dividends calculated? (the \"Future dividends\" section in the sidebar)")
    st.markdown(r"""
Traditional backtests often roll dividends in automatically. In real life, dividends are cash paid out one payment at a time, and **they are usually larger in good times and shrink in bad times**.

The tool uses a simple model to capture this. Let the base monthly dividend be $D_0$ (converted from the yearly dividend rate you set). Let the market's cumulative gain or loss from the start until now be $\text{cumulative return}$. The dividend actually paid is:
""")
    st.latex(r"D_t = \max\Big(\,0.1 \times D_0,\;\; D_0 \times (1 + \text{cumulative return} \times \beta_{\text{div}})\,\Big)")
    st.markdown(r"""
- $\beta_{\text{div}}$ is the main page setting "**How closely dividends follow the market**". At 0, the dividend never moves. At 1, it follows the market closely.
- The $\max(\dots, 0.1 \times D_0)$ part is a **floor**: even when the market falls to the bottom, a company still pays at least 10% of the base amount and doesn't stop completely.
""")

    st.subheader("Where is this model used?")
    st.markdown(r"""
Dividends come from one of three sources, depending on the case:

| Case | Where the dividend comes from |
|---|---|
| In the historical backtest, months with real data | The **dividend actually paid** that month |
| In the historical backtest, the "assumed future" after the real data ends | The **dividend model** above (with the dividend rate you set) |
| Monte Carlo | By default, the **dividend actually paid**: when a month's price move is drawn, that month's dividend comes with it. You can switch to the dividend model under "Advanced" in the sidebar |

Monte Carlo uses the actual dividends by default because it recombines history. This way, the dividend lands in the same month where the price drops because of the ex-dividend date.
An ETF that pays no dividends doesn't get any from nowhere, and the dividend level follows the ETF's own record.
The cost is that it fully trusts the historical data: if the data source is missing a period's dividends ("Data used" on the main page lists such cases), that period counts as having no dividends, and the result is on the cautious side.
""")

    st.subheader("How often are dividends paid? (the \"How often future dividends are paid\" setting)")
    st.markdown(r"""
The dividend model gives "how much to pay in an average month". In real life, most ETFs pay quarterly, twice a year or yearly, so the tool groups the amount into a few payments.
For example, with quarterly payments, one payment is made every three months (the amount of three months), and the two months in between pay nothing. The total paid per year stays about the same. The differences are:

- **Months with no dividend** must be covered by other sources, so cash flow is tighter;
- **A single larger payment** is more likely to pass the NT\$20,000 threshold for the NHI supplementary premium (see "Taxes and fees" below).

By default, the tool judges the frequency from how often this ETF actually paid over the last three years. This affects only dividends made by the model. In months with real data, the real payment dates and amounts are always used.
""")

    # ------------------------------------------------------------------
    st.header("4. Where does each monthly payment come from?")
    st.markdown(r"""
Each month when the loan payment is due, the tool uses the sources below in the order you set, until the month's payment is covered:

1. **Saved dividends**: dividend cash that has built up and not been spent yet.
2. **Cash buffer**: the spare cash you set aside at the start.
3. **Sell main ETF**: sell the stock you bought with the loan for cash (this costs trading fees, and in a crash you may also take a fire-sale loss, see the next section).
4. **Sell second ETF**: sell the second ETF you bought with dividends. This source exists only if you chose "Reinvest dividends" and entered a second ETF.
5. **Salary (out of pocket)**: you pay from your own salary, up to a monthly limit.

Each source can be placed in the order only once. To skip a source, set the extra choices to "(Not used)".

If every source in the order is used up and you are still short, that month you **can't pay the loan → default**.
A source that is not in the order is never used. For example, if you set the second ETF to "(Not used)", you still default when the other sources run out, even if you hold the second ETF.
By default the second ETF is last, which means "you default only after everything that can be sold has been sold".
""")

    st.caption("If the second ETF falls to zero (for example a leveraged ETF in an extreme crash), you can no longer buy it. The part of the dividends meant for it buys the main ETF instead.")

    st.warning("**Important**: if you put \"Salary (out of pocket)\" in the order and set its limit very high, you will almost never default, because your salary always covers the gap. To really test whether \"the strategy itself\" holds up, lower the salary limit, or leave salary out of the order.")

    # ------------------------------------------------------------------
    st.header("5. Loss when you must sell fast in a crash (the \"Fire-sale loss in a crash\" setting)")
    st.markdown(r"""
Normally, selling shares costs only a small trading fee. But when the market falls hard and everyone is selling, you may only get a worse price. This is called a **liquidity discount**.

When a month's fall is bigger than the threshold you set, the tool adds an extra discount loss to the cost of selling shares in that month. If you are $S$ short of the loan payment this month, the market value of shares you actually have to sell is:
""")
    st.latex(r"\text{market value to sell} = \frac{S}{1 - (\text{fee} + \text{extra discount})}")
    st.markdown("The bigger the discount, the more shares you must sell to raise the same money, and the more it hurts your assets.\n\nThe trading fee is also charged once when you first buy shares with the loan.")

    # ------------------------------------------------------------------
    st.header("6. What if the second ETF has no real data? (the \"Volatility decay of leveraged ETFs\" setting)")
    st.markdown(r"""
The second ETF (for example a 2x ETF) has two kinds of months with no real returns: **before it was listed**, and the **assumed future** beyond the historical data.
For these months the tool estimates it from the main ETF's moves. First it estimates the second ETF's sensitivity $\beta$ to the main ETF from the months where both have data
(when the main ETF rises 1%, by how many % the second ETF rises on average). Then:
""")
    st.latex(r"r_B = (1 + r_A)^{\beta} \times e^{-\frac{1}{2}\beta(\beta-1)\sigma_A^{2}} - 1 + \varepsilon")
    st.markdown(r"""
- $(1+r_A)^{\beta}$ is the **compounding effect**: a daily-reset leveraged ETF gains more than "$\beta$ times" in a long run of rises, and loses less in a long run of falls
  (if the main ETF falls 20% in a month, a 2x ETF falls 36%, not 40%).
- $e^{-\frac{1}{2}\beta(\beta-1)\sigma_A^2}$ is the **volatility decay**: what is quietly lost when the market goes up and down. $\sigma_A$ is the volatility of the main ETF's monthly returns.
  When the main ETF is flat in a month, the second ETF loses exactly this amount.
- $\varepsilon$ is a random error. Its size comes from how widely the two ETFs' relationship varies in the overlap period.

This is the standard approximation in the leveraged-ETF literature. Both effects must be included together: subtracting the decay without the compounding would understate the result twice.
When you turn off the switch on the main page, the tool uses the simplest form, $r_B = \beta \times r_A + \varepsilon$.
""")
    st.info("**No extrapolation of excess return**: in the overlap period, the second ETF may actually have beaten \"main ETF × β\" for a long time (for example a 2x ETF in recent years). "
            "The tool doesn't assume this advantage continues into months with no data. In that period it only follows the main ETF. This is a cautious assumption that suits a stress test.")
    st.warning("This formula is used only for \"months with no real data\". Months with real data always use the real return, which already includes compounding and decay, so nothing is counted twice.")

    # ------------------------------------------------------------------
    st.header("7. How do the historical backtest and Monte Carlo differ?")
    st.markdown(r"""
The tool uses two methods to judge risk, and shows the results side by side:
""")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🅰 Historical backtest")
        st.markdown(r"""
    **The idea: "Test what really happened in the past."**

    Every month in history is treated as a start month, as if "you started then": **you buy at that month's price, and the first payment is due the next month**. After that, the real market plays out.
    If the history after a start month is too short (it doesn't cover your whole loan term), the missing future is filled in with the **scenario** you chose (for example the 2008 replay).

    This is a **fixed "what if" analysis**. The only exception is when "random job loss" is on: each start month is simulated with many job-loss timings,
    and that month's chance of default is the average of those results, so it doesn't depend on a single draw.
    """)
    with col2:
        st.markdown("#### 🅱 Monte Carlo simulation")
        st.markdown(r"""
    **The idea: "Shuffle history and recombine it to see what else could happen."**

    The tool draws "pieces" of historical returns at random and joins them into thousands of possible futures, then counts how many of them default.
    Each month that is drawn brings its price move and the dividend actually paid that month together.

    Drawing pieces (instead of single months) **keeps the way moves follow each other**, because in real life a crash usually means several falling months in a row, and months are not independent.
    A piece can start at any month. When the draw reaches the last month of history, it wraps around to the first month, so every month has the same chance of being drawn.

    It uses the whole history, **and doesn't depend on the month you pick for the month-by-month detail on the main page**. By default the random draws are fixed, so the same settings give the same results.
    When you turn off "Same random draws every run", each recalculation draws new samples and the numbers move a little. The main page shows the range of the sampling error.
    """)

    st.markdown(r"""
> **Why two methods?** One answers "**what happens if one specific scenario occurs?**" and the other answers "**taking all possibilities together, how likely is a default?**". They complement each other, but their baselines differ, so don't mix the two numbers up directly.
""")

    # ------------------------------------------------------------------
    st.header("8. How is the comparison with DCA made?")
    st.markdown(r"""
In every simulated path, the tool also runs a comparison group at the same time: **dollar-cost averaging (DCA)**:

- **Leveraged strategy**: borrow a large sum at the start and invest all of it, then carry the loan payments every month.
- **DCA**: don't borrow at the start. Instead, each month, use "the money that would have gone to the loan payment from your salary" to buy shares directly.

The only difference is that the leveraged strategy **holds the whole principal from the start**. So this comparison is really asking: "Putting in a lot at once versus buying slowly in steps: which is better?"

To make the comparison fair, **both sides must pay the same amount out of their own pockets**. Under "Advanced" in the sidebar you can choose how the comparison group invests:

- **Same out-of-pocket amount as the leveraged side (standard)**: the DCA side invests exactly what the leveraged strategy actually paid from salary that month.
  If that month's loan payment was covered by dividends, the cash buffer or selling shares, that part is not your own money, so the DCA side invests nothing for it.
  After the leveraged strategy defaults, it stops paying, while the DCA side keeps investing the smaller of "the payment due" and "the salary limit" each month.
- **Invest the full payment every month (old method)**: the DCA side invests the full payment due every month, whatever the salary limit is.
  When the payment due is far above the salary limit (for example a monthly payment of NT\$67,000 and a salary limit of NT\$25,000), the DCA side invests much more principal than the leveraged side pays out of pocket,
  and the comparison is unfavorable to the leveraged strategy.
""")
    st.warning("**A note on reading it**: in a market that rises over the long run, \"putting in a lot at the start\" usually wins, because the money compounds from an earlier date. So if you see the leveraged strategy beat DCA by a wide margin, remember that a large part of it is because the backtest period happened to be a bull market. It doesn't mean borrowing to invest always wins.")

    # ------------------------------------------------------------------
    st.header("9. Taxes and fees")
    st.markdown(r"""
The "Taxes and fees" section on the main page uses the current Taiwan rules by default, for both the leveraged strategy and the DCA comparison:

| Item | How it is calculated | Standard |
|---|---|---|
| Trading fee | Charged on both buying and selling, including the final settlement at the end | 0.1425% |
| Securities transaction tax | Only when selling, charged on top of the fee | 0.1% (ETFs; 0.3% for single stocks) |
| NHI supplementary premium (Taiwan's National Health Insurance) | When the dividend income in one payment reaches NT\$20,000, 2.11% of the whole amount is deducted | On |
| Dividend income tax | At each payment, deducted at the net rate "income tax bracket − 8.5% credit" | 12% bracket, 3.5% net rate |
| Loan setup fee | Deducted once from the borrowed money when the loan is paid out | NT\$0 |

A few simplifications:

- **Income tax is deducted when the dividend is received.** In real life it is paid in May of the next year, so cash flow is a little on the cautious side. The 5% bracket actually gets a refund, which is counted as 0 here. The NT\$80,000 credit limit per household is not applied. The 40% bracket uses separate taxation at 28%.
- **By default, all dividends are treated as dividend income.** ETF payouts often include capital gains and income equalization, which have no income tax or supplementary premium. You can lower "Share of the dividend that counts as dividend income" for this.
- **The supplementary premium threshold is checked for each payment.** A large position bought with a loan usually passes it on every payment. The DCA position builds up slowly, and early payments are below NT\$20,000, so they are not charged. This difference between the two approaches really exists in real life.
- Dividends of the second ETF are not calculated (see section 6; leveraged ETFs usually pay none).
""")

    # ------------------------------------------------------------------
    st.header("10. How is the market data handled?")
    st.markdown(r"""
The quality of the results depends on the data. Before calculating, the tool does the following, and lists what it did at the top of the results on the main page:

- **Repair stock splits that were not adjusted.** For some Taiwan ETFs, the data source adjusted splits for only part of the history, or not at all, and the data keeps a false one-day drop of -75% or -95%.
  If a day's price jump is an exact whole-number multiple (1-for-4, 1-for-22, 7-for-1, …), and the source has no split record for the ticker at all, the tool converts the prices before the seam to the same basis.
  Tickers where the source provides split records (most US stocks) are not changed, because in that case the large drop is more likely to be real.
- **Fix dividend units.** The source adjusts prices and dividends back to different dates, so a few dividends near the seam may still be in the amount before the split, and the yield suddenly becomes several times larger.
  The tool finds the cut-off point that makes the yield most consistent across years and converts accordingly. If the years next to the cut-off have unusually large or small dividends, this judgment can be off by a year or two.
- **Flag unusual values.** A one-day move far larger than the ETF's normal volatility, a monthly dividend of more than 15% of the price, or a long blank at the start of the dividend record are all listed.
  The tool can't tell whether it is a data error or a real extreme market, so it **only flags it and doesn't change it**.
- **Dividends count in the ex-dividend month.** Each month's price is taken on the payment day (or the first trading day after it). A dividend is counted in the period where "the price already reflects the ex-dividend date",
  which is the first monthly price on or after the ex-dividend date, not simply the calendar month it falls in.
- **History before listing can be filled by a stand-in.** When the main ETF was listed only recently, you can set a similar ETF that was listed earlier. For the months before the main ETF was listed, the stand-in's actual price moves and dividends are used directly.
  This is only an approximation: the stand-in is not the same product, and the main page shows the correlation over their overlap period to help you judge.
- **Recent saved copies are used first.** Data fetched less than a day and a half ago is reused, and common tickers are also updated automatically once a day, so the tool doesn't have to fetch from the data source every time.
  "Data used" on the main page lists when each ticker's data was fetched. For the latest data, press "Reload market data" in the sidebar.
- **An older saved copy is used when the source is down.** When the data source can't be reached for now, the tool uses the latest saved copy it has, and the main page shows a warning with the date of the saved copy.
""")
    st.warning("All of this handling is inference from patterns in the data, not official adjusted data. Before an important decision, compare the fixes listed on the main page with a source you trust.")

    # ------------------------------------------------------------------
    st.header("11. How is the safety limit found?")
    st.markdown(r"""
The safety limit answers two questions: with your other settings unchanged, what is the most you can borrow, and the least you must be able to pay out of pocket each month, so that the Monte Carlo chance of default stays within the limit you choose (1%, 5% or 10%).

- **The search "halves the range"**: it first tries both ends of the search range, then keeps cutting the range in half. A dozen or so tries are enough, so it doesn't have to try every amount.
  The loan amount is tried from NT\$100,000 up to 10 times the current loan (at most NT\$100 million), in steps of NT\$100,000. The monthly out-of-pocket limit is tried from 0 to NT\$500,000 in steps of NT\$1,000.
  When there is a loan setup fee, the loan amount is tried from the first multiple of NT\$100,000 above the fee.
- **Every try uses the same set of random futures**, so the more you borrow, the chance of default only stays the same or rises. It doesn't go up and down because of sampling luck.
  This is also true when "Same random draws every run" is off: the tool always uses one fixed set of draws, so its numbers may differ slightly from the chance of default at the top of the main page.
- **The default-risk map** changes the loan amount and the monthly out-of-pocket limit to 0.5 to 2 times the current values (when the monthly out-of-pocket limit is 0, it uses NT\$0 to NT\$50,000 instead) and lists the chance of default for every combination.
- When "Salary (out of pocket)" is not in the repayment order, the monthly out-of-pocket amount doesn't change the result, so "least you must pay in each month" is not calculated.
""")
    st.warning("The safety limit is an estimate built from recombined market history. The real future can be worse than history. Borrowing right up to the limit leaves no margin at all.")

    # ------------------------------------------------------------------
    st.header("12. How much can a personal loan be? (the personal-loan fields in the \"Loan\" section of the sidebar)")
    st.markdown(r"""
This section applies only to a "Personal loan". A home-equity loan is secured by your home and is not bound by these rules, and the sidebar doesn't show these fields for it.

**First, work out your average monthly income.** Average monthly income is your yearly income divided by 12. Yearly income includes the year-end bonus and profit share. For example, for a yearly income of NT\$720,000, the average monthly income is NT\$60,000.

**The legal limit: the Financial Supervisory Commission's 22-times rule.** The Financial Supervisory Commission (FSC) says that a person's unsecured debt across all financial institutions can't add up to more than 22 times average monthly income. People in the trade call this DBR22. No matter how good your credit is or how many assets you have, you can't go over it. The calculation is:

Legal limit = average monthly income × 22 − existing unsecured debt (at least 0)

**What is unsecured debt?** It is borrowing that is not secured by something such as a house or car. Count the following:

- Other personal loans
- Credit-card balances due, unpaid installments, revolving interest
- Cash advances
- Cash cards
- Student loans you have started repaying

Don't count the following:

- Mortgages and home-equity loans
- Secured car loans
- Margin loans on stocks
- Broker margin financing

**Typical approval: what a bank may actually lend you (estimate).** A bank doesn't lend up to the legal limit. We couldn't find a published approval multiple from any bank. Online articles mostly say 15 to 18 times, and the claims differ. So this number is an estimate, and you can change it. The standard value is 20 times, which is more optimistic than what is said online. To be more cautious, lower it.

Typical approval = average monthly income × approval multiple − existing unsecured debt (at least 0, and not above the product maximum)

**Product maximum.** Every personal-loan product at every bank has a maximum amount. The standard is NT\$5 million, a number common at large private banks. State-owned banks commonly offer NT\$3 million. Professional-worker programs can reach NT\$10 to 12 million.

**Borrowing limit.** The borrowing limit is the smaller of the legal limit and the product maximum.
""")
    st.table(pd.DataFrame(
        [["NT$50,000", "20", "NT$1.1 million", "NT$1 million", "NT$1.1 million"],
         ["NT$100,000", "16", "NT$2.2 million", "NT$1.6 million", "NT$2.2 million"],
         ["NT$500,000", "20", "NT$11 million", "NT$5 million", "NT$5 million"],
         ["NT$50,000 (existing unsecured debt NT$500,000)", "20", "NT$600,000", "NT$500,000", "NT$600,000"]],
        columns=["Average monthly income", "Approval multiple", "Legal limit", "Typical approval (estimate)", "Borrowing limit"]))
    st.markdown(r"""
**What happens if the loan amount you enter is above the borrowing limit?** The tool calculates with the borrowing limit instead, and tells you at the top of the results. If you choose "Use the estimated approvable amount", the loan amount is the typical approval amount.

**What happens if you enter 0 for average monthly income?** The tool doesn't check the limit, and the results are the same as when this feature didn't exist.

**The tool also reminds you of three things.**

- Payment ratio: the monthly payment after the interest-only period ÷ average monthly income. Above one third, it says "high". Above 70%, it says "most banks may decline". This counts only this new loan, not the monthly payments on your other loans.
- Yearly income under NT\$300,000: for most banks, the minimum yearly income to apply is NT\$300,000.
- According to news reports: from 2026-10-31, if you state "investing" as the purpose of a personal loan, the bank must first get your consent before it can look up your brokerage borrowing (for example margin loans). If you don't consent, the loan can't be made.

**What this tool does not check.** Age, years of service, occupation, the number of credit-bureau inquiries and your total debt-to-asset ratio all affect a bank's approval. The tool doesn't check any of these.

**Sources.** The sources were checked on 2026-11-17.

- FSC rule (the scope of DBR22 and which debts count): the FSC's notice in its shared regulation system. The regulation website could not be opened at the time, so the content of the rule comes from a summary in search results, not from the original text.
- Product maximum, yearly income threshold and payment ratio: the product pages on the banks' websites.
- Approval multiple: no primary source exists, only claims in online articles.
- The new rule from 2026-10-31: according to news reports. The original FSC press release was not obtained.
""")
    st.warning("Bank conditions change often. What you can actually borrow is decided by the bank's own approval.")
    st.caption("The credit limit is an estimate. Bank conditions change often. The bank's own approval is what counts.")

    st.markdown("---")
    st.caption(t(DISCLAIMER))
