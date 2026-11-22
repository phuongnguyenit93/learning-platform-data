# `BigDecimal`: Multi-Step Calculations and Choosing When to Round

## 1. The Problem: Same Operations, Different Final Results

In workflows multiplying unit price by quantity, applying discounts, calculating taxes, converting currencies, splitting payments, or computing multi-period interest, **when to round is a business rule**. Rounding every intermediate result versus rounding only the final total are two different policies, even when both use `BigDecimal`, the same scale, and the same `RoundingMode`.

Suppose there are three items, each with an original value of `0.335`, needing two digits after the decimal point with `HALF_UP`:

- **Settle each item then sum:** `0.335 → 0.34`; total `0.34 × 3 = 1.02`.
- **Sum raw values then settle:** `0.335 × 3 = 1.005`; total `1.005 → 1.01`.

The `0.01` difference is not a Java bug. You must determine whether money is recorded per line item, per invoice total, or per defined tax/interest base. The goal of this lesson is to know how to **preserve precision when needed**, **round at the right boundaries**, **choose appropriate precision/scale/mode**, and **reconcile totals after allocation**.

## 2. Scale, Precision, MathContext, and Exactness

`BigDecimal` represents a number as `unscaledValue × 10^(-scale)`. For `new BigDecimal("123.450")`, `scale() == 3` and `precision() == 6`.

| Component | Meaning | Example |
|---|---|---|
| `scale` | Number of digits to the right of the decimal point; can be negative | `123.450` has scale 3 |
| `precision` | Total number of significant digits of the value | `123.450` has precision 6 |
| `setScale(2, mode)` | Settles to two decimal places; may round | `123.456 → 123.46` with `HALF_UP` |
| `round(new MathContext(5, mode))` | Settles to at most five significant digits | `1234.56789 → 1234.6` with `HALF_EVEN` |

`new MathContext(5)` **does not mean five digits after the decimal point**. MathContext controls result precision; `setScale` controls result scale.

Overloads of `add`, `subtract`, and `multiply` **without passing a MathContext** generally preserve the exact mathematical result in decimal representation, within resource limits and supported scale range. For `multiply`, the result scale is generally the sum of the two operands' scales; for `add`/`subtract`, scale is generally the larger scale of the two operands. This does not mean the result is already settled to the currency unit.

**Initializing decimal data properly:**

~~~java
BigDecimal unitPrice = new BigDecimal("19.995");
BigDecimal discountRate = new BigDecimal("0.075");
BigDecimal quantity = BigDecimal.valueOf(3L);
~~~

Avoid `new BigDecimal(0.1)` if you intend exact decimal `0.1`: `double` already holds a binary approximation. `BigDecimal.valueOf(0.1)` takes the decimal representation from `Double.toString` and is usually preferable to the `double` constructor, yet it **cannot recover errors introduced by `double` arithmetic prior to conversion**. For money and fixed rates, prefer `String`, integer minor units, or properly parsed decimal data.

`BigDecimal` is immutable: `a.add(b)`, `a.setScale(...)`, and `a.round(...)` return new results without modifying `a`. You must assign and use the return value.

## 3. Multi-Step Example: Rounding at the End vs. Rounding Each Item

Suppose unit price is `19.995`, quantity is `3`, discount is `7.5%`, and tax is `8%` on the discounted value. The final payable amount is settled to two decimal places using `HALF_UP`. This is an **illustrative model**, not establishing tax or pricing policy for any country.

**A — settle only the final total:**

1. Gross: `19.995 × 3 = 59.985`.
2. Discount: `59.985 × 0.075 = 4.498875`.
3. Taxable amount: `59.985 - 4.498875 = 55.486125`.
4. Tax: `55.486125 × 0.08 = 4.43889000`.
5. Unrounded total `55.486125 + 4.43889000 = 59.92501500`, rounded to **59.93**.

**B — settle unit price and items as recorded:**

1. Unit price `19.995 → 20.00`; gross `20.00 × 3 = 60.00`.
2. Discount `60.00 × 0.075 = 4.50000 → 4.50`.
3. Taxable amount `60.00 - 4.50 = 55.50`.
4. Tax `55.50 × 0.08 = 4.4400 → 4.44`.
5. Settled total **59.94**.

The two approaches differ by `0.01`. If unit price input is required to have two digits, that is a validation/settlement policy on unit price, not to be confused with arbitrary rounding in the processing layer.

### Complete Java 17+ Program

Save as `RoundingPipelineDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RoundingPipelineDemo {
    private static final RoundingMode MODE = RoundingMode.HALF_UP;

    private static BigDecimal money(BigDecimal value) {
        return value.setScale(2, MODE);
    }

    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.995");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal discountRate = new BigDecimal("0.075");
        BigDecimal taxRate = new BigDecimal("0.08");

        // A: Use exact intermediate values, settle the final total.
        BigDecimal gross = unitPrice.multiply(quantity);
        BigDecimal discount = gross.multiply(discountRate);
        BigDecimal taxable = gross.subtract(discount);
        BigDecimal tax = taxable.multiply(taxRate);
        BigDecimal finalOnly = money(taxable.add(tax));

        // B: Settle unit price, discount, and tax at each step.
        BigDecimal grossEarly = money(unitPrice).multiply(quantity);
        BigDecimal discountEarly = money(grossEarly.multiply(discountRate));
        BigDecimal taxableEarly = grossEarly.subtract(discountEarly);
        BigDecimal taxEarly = money(taxableEarly.multiply(taxRate));
        BigDecimal eachStep = money(taxableEarly.add(taxEarly));

        System.out.println("final only = " + finalOnly);
        System.out.println("each step  = " + eachStep);
        System.out.println("difference = " + eachStep.subtract(finalOnly));
    }
}
~~~

Compile and run:

~~~bash
javac RoundingPipelineDemo.java
java RoundingPipelineDemo
~~~

Stdout:

~~~text
final only = 59.93
each step  = 59.94
difference = 0.01
~~~

The `money` helper represents **settling a monetary amount**. Do not add `setScale(2, ...)` at an intermediate step merely because the final output is money. Every settlement point must be specified in the business specification.

## 4. Deciding When to Round by Business Boundaries

| Practical step | Question to answer | Impact |
|---|---|---|
| Multiplying unit price by quantity | How many digits may unit price have? Settle before or after multiplying? | Rounding unit price can amplify differences by quantity |
| Computing multi-line invoices | Is the sum of settled lines or the sum of raw values the base? | Sum of displayed lines may differ from calculated total |
| Discounts/taxes | Settled per line, per tax type, or per whole invoice? | Affects tax base and final result |
| Multi-period interest | Is prior interest capitalized immediately or kept unsettled? | Affects compounding and reconciliation |
| Foreign currency conversion | Exchange rate precision and settlement timing in target currency? | Discrepancies when exchange rates are rounded early |
| Money allocation | What is the smallest transferable/bookable unit? | Remainder must be allocated so parts sum to the total to split |
| Reporting display | Is rounding for display only, or was that figure posted to the ledger? | Display formatting must not silently alter transaction data |

A clear design separates **input → unsettled calculation → settlement/posting point → display**. A posted monetary amount typically continues into subsequent flows using its **settled value** if the contract/ledger requires it; keeping raw figures for auditing does not mean using raw figures instead of posted ones. Conversely, reports formatting numbers for readability should not silently round and write back to the source.

You should separately document unit price scale, rate scale, internal division precision, settlement scale, and display scale. They do not have to be identical. For tax/interest laws, follow applicable regulations; there is no single mode right for all domains.

## 5. Double Rounding: Rounding Twice Can Differ from Rounding Once

~~~java
BigDecimal x = new BigDecimal("2.345");
BigDecimal twice = x.setScale(2, RoundingMode.HALF_UP)
                    .setScale(1, RoundingMode.HALF_UP);
BigDecimal once = x.setScale(1, RoundingMode.HALF_UP);

System.out.println(twice); // 2.4
System.out.println(once);  // 2.3
~~~

Rounding twice: `2.345 → 2.35 → 2.4`. Rounding directly to one digit: `2.345 → 2.3`. There is no law saying `round(round(x))` always equals `round(x)` when the two policies/scales differ. Rounding before multiplication also loses information: `19.995` becomes `20.00`, multiplied by `3` becomes `60.00`, which cannot recover `59.985`.

**Solution:** keep intermediate numbers accurate enough and settle only at designated boundaries; if two settlements are genuinely required, treat them as two distinct settled transactions rather than trying to “compensate-round” to mimic single-step rounding.

## 6. Division: Mandatory Handling of Non-Terminating Cases

`BigDecimal.divide(divisor)` without a rounding mode succeeds only when the quotient has a terminating decimal representation. For example, `1 / 8 = 0.125` succeeds, whereas `1 / 3` has an infinite expansion and throws `ArithmeticException`. Dividing by 0 also throws `ArithmeticException`.

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException due to non-terminating quotient.

BigDecimal byScale = one.divide(three, 6, RoundingMode.HALF_EVEN);
BigDecimal byPrecision = one.divide(
        three, new MathContext(6, RoundingMode.HALF_EVEN));

System.out.println(byScale);     // 0.333333
System.out.println(byPrecision); // 0.333333
~~~

These two results match **specifically for 1/3**. Scale 6 means six digits after the decimal point; precision 6 means six significant digits. For instance, the quotient of `12345/7` will have different representations under the two rules.

Be careful with the overload `divide(BigDecimal divisor, RoundingMode mode)`: it takes the **result scale from the dividend's scale**. This is an easily overlooked bug:

~~~java
System.out.println(new BigDecimal("1")
        .divide(new BigDecimal("3"), RoundingMode.HALF_UP)); // 0
System.out.println(new BigDecimal("1.00")
        .divide(new BigDecimal("3"), RoundingMode.HALF_UP)); // 0.33
~~~

When you need a fixed scale, use `divide(divisor, scale, mode)`; when you need significant digits, use `divide(divisor, mc)`. `MathContext.UNLIMITED` has precision 0, requesting exact arithmetic, and **cannot turn 1/3 into a terminating quotient**. Do not pick an arbitrary precision and claim you have an absolutely exact mathematical result.

## 7. Per-Step `MathContext` Differs from Settling the Final Total

A `MathContext` with finite precision rounds **the result of each method passed that context**. For example:

~~~java
BigDecimal x = new BigDecimal("1234.56789");
System.out.println(x.round(new MathContext(5, RoundingMode.HALF_EVEN)));
System.out.println(x.setScale(2, RoundingMode.HALF_EVEN));
~~~

Stdout:

~~~text
1234.6
1234.57
~~~

Therefore, `a.multiply(b, mc).divide(c, mc).add(d, mc)` can round at three steps. It does not mean computing three exact steps and rounding once. When rounding at every step, changing addition/grouping order can also change the result.

Selection guidelines:

1. For finite decimal `add`, `subtract`, and `multiply`, keep exact results if business logic and resources allow.
2. For non-terminating division, square roots, or iterative algorithms, choose working precision based on target output accuracy and error accumulation.
3. Keep guard digits if many steps remain. **No fixed number of guard digits guarantees exactness for all formulas**.
4. Only settle with `setScale` at defined boundaries. If business rules require settling per period or per item, perform those exact settlements.
5. To guarantee a maximum error bound, analyze the formula and calculation order rather than guessing a large precision by gut feel.

A single round-to-nearest operation to scale 2 has a maximum absolute error of `0.005` units relative to **the value immediately before that rounding**. If you round `n` lines and then sum, discrepancies can accumulate; subsequent multiplications/divisions can transform the error further. Do not apply a single-step bound to an entire pipeline without analyzing downstream steps.

## 8. Choosing `RoundingMode`, Including Negative Numbers

| Mode | Rounding direction | Scale 2 example |
|---|---|---|
| `HALF_UP` | Nearest, midpoint away from 0 | `2.345 → 2.35`; `-2.345 → -2.35` |
| `HALF_EVEN` | Nearest, midpoint keeps even last digit | `2.345 → 2.34`; `2.355 → 2.36` |
| `DOWN` | Toward 0 (does not always mean smaller) | `-2.349 → -2.34` |
| `UP` | Away from 0 if any digit is discarded | `-2.341 → -2.35` |
| `FLOOR` | Toward negative infinity | `-2.341 → -2.35` |
| `CEILING` | Toward positive infinity | `-2.341 → -2.34` |
| `UNNECESSARY` | Forbids lossy rounding; throws if needed | `2.340 → 2.34`, `2.345 → error` |

`HALF_EVEN` can reduce bias when rounding many values that land on midpoints; `HALF_UP` is familiar in many currency rules. Yet both **must follow the defined policy**, not be inferred from a single example. Especially test negative numbers and credit memos/refunds because `DOWN` and `FLOOR` differ.

`UNNECESSARY` is a way to check that a number is already valid at the required scale:

~~~java
new BigDecimal("12.340").setScale(2, RoundingMode.UNNECESSARY); // 12.34
// new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException because scale cannot be reduced while preserving value.
~~~

## 9. Allocating Remainders When Splitting a Settled Amount

If you must split `1.00` among three people, `1.00 / 3` settles to `0.33`; multiplying back by three gives only `0.99`. To make **the sum of shares equal the total to distribute**, you need a remainder allocation rule, such as taking the base share using `DOWN` and distributing leftover cents in a deterministic order.

The Java 17+ program below applies to **non-negative amounts with at most two decimal places** and a positive recipient count; save as `AllocationDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

public class AllocationDemo {
    static List<BigDecimal> allocate(BigDecimal amount, int recipients) {
        if (recipients <= 0 || amount.signum() < 0) {
            throw new IllegalArgumentException("recipients > 0, amount >= 0");
        }
        BigDecimal total = amount.setScale(2, RoundingMode.UNNECESSARY);
        BigDecimal divisor = BigDecimal.valueOf(recipients);
        BigDecimal base = total.divide(divisor, 2, RoundingMode.DOWN);
        int extraCents = total.subtract(base.multiply(divisor))
                .movePointRight(2).intValueExact();

        List<BigDecimal> shares = new ArrayList<>();
        for (int i = 0; i < recipients; i++) {
            shares.add(i < extraCents
                    ? base.add(new BigDecimal("0.01"))
                    : base);
        }
        return shares;
    }

    public static void main(String[] args) {
        List<BigDecimal> shares = allocate(new BigDecimal("1.00"), 3);
        BigDecimal sum = shares.stream()
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println(shares);
        System.out.println(sum);
    }
}
~~~

Compile with `javac AllocationDemo.java`, run `java AllocationDemo`:

~~~text
[0.34, 0.33, 0.33]
1.00
~~~

The rule above gives the extra cent to the first recipient. In real business logic, ordering may require fairness over time, weighted splitting, persisting allocation plans, handling negative amounts/refunds, and scales other than 2 depending on currency. The invariant to uphold is **the sum of allocated shares equals the settled total exactly**.

## 10. Organizing a Clear, Auditable Pipeline

Specify before writing formulas:

- **Inputs:** currency, unit price precision, exchange/tax rate scale, decimal storage format, pre-rounding constraints.
- **Calculation order:** which base discounts/taxes/fees apply to, line-level vs. total-level calculation, interest periods, required precision for multiplications/divisions.
- **Settlement boundaries:** where settlement is mandatory, exact scale and mode for each item type; whether settled values feed into the next step.
- **Reconciliation:** whether displayed line totals must match the document total, and which line records remainders or adjustments.
- **Audit trail:** retain inputs, rates, rounding policy, and rule version; do not accidentally use `double` as an intermediate.
- **Display:** formatting for viewing must not silently overwrite settled values.

Variable names should express semantics: `rawSubtotal`, `postedDiscount`, `taxableAmount`, `postedTax`, `settlementTotal`. Helper functions like `roundTaxLine(...)` or `roundSettlement(...)` convey intent much better than an arbitrary `setScale(2, HALF_UP)`. When rules are unclear, align with business stakeholders; do not choose the variant that “looks nicer”.

**Comparison note:** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` returns `false` due to different scales, whereas `compareTo(...) == 0` is `true` because numeric values are equal. When checking calculated monetary amounts, consider `compareTo`; when checking exact representation/scale compliance, check scale separately or use `equals` per contract.

## 11. Testing Boundaries and Invariants

1. **Midpoints and signs:** test `2.345`, `2.355`, `-2.345`, `0.005`, `0.0049` with business mode/scale.
2. **Settlement points:** three items of `0.335` lead to `1.02` per item or `1.01` at total. The discount/tax example above must produce `59.93` or `59.94` per policy.
3. **Double rounding:** `2.345 → 2.35 → 2.4` differs from `2.345 → 2.3`; catches refactors that misplace `setScale`.
4. **Division:** exact `1/3` must error; scale/context division produces specified output; division by 0 must error.
5. **Allocation:** test `1.00 / 3`, `0.01 / 3`, `0.00 / 3`, and large totals; each share has valid scale, sum of shares equals pre-split total.
6. **Boundary data:** negative values, refunds, 0 tax rate, 100% discount, long iterative calculations, foreign currencies with minor digits other than 2.
7. **Storage invariants:** verify settled numbers are fed as inputs at the right boundaries, distinguishing value comparison from scale comparison.

Example checking the result of the first program after `finalOnly` is computed:

~~~java
if (finalOnly.compareTo(new BigDecimal("59.93")) != 0) {
    throw new AssertionError("Incorrect final rounding policy");
}
~~~

Testing only an input where two approaches happen to agree is not enough to prove the rounding boundary is right. Actively pick test data that causes the two rounding strategies to diverge so tests catch a misplaced `setScale`.

## 12. Common Mistakes and Exercises

**Mistakes to avoid:** settling every multiplication because “money has two decimal places”; confusing `MathContext(2)` with `setScale(2)`; forgetting `divide` can throw on infinite quotients; calling `divide(divisor, mode)` while overlooking the dividend's scale; rounding twice across service/DTO layers; using `double` for rates without control; assuming the sum of rounded parts always equals the rounded sum; confusing `DOWN` with `FLOOR` for negative numbers; using `equals` when only arithmetic equality is needed.

**Self-practice:**

1. Four amounts of `0.125`, `HALF_UP`, scale 2: what is the result if settled individually then summed? If raw values are summed then settled?
2. Why does `new BigDecimal("1").divide(new BigDecimal("8"))` succeed while `1/3` can throw an error?
3. For `5.55`, are `round(new MathContext(2, HALF_EVEN))` and `setScale(2, HALF_EVEN)` the same?
4. How do you allocate `0.02` among three people so the sum is still exactly two cents?

**Answers:** (1) `0.13 × 4 = 0.52`; summing first gives `0.125 × 4 = 0.500 → 0.50`. (2) `1/8 = 0.125` is terminating, `1/3` is non-terminating. (3) No: the results are `5.6` and `5.55` respectively. (4) With a deterministic ordering, it can be `[0.01, 0.01, 0.00]`.

### Checklist Before Deploying a Pipeline

Which values must be strictly exact? Which steps need approximation, and what scale or precision suffices? Where are the business settlement points, which mode applies, and how are negative numbers handled? Are settled values used in subsequent steps? Does the sum after allocation match the amount to record? Are there tests distinguishing per-item settlement from total settlement?

### Authoritative References

- Java SE 17, `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17, `MathContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html
- Java SE 17, `RoundingMode`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html

**Principle:** clarify which numbers are still intermediate values, which are already settled, and *why they are settled*; only then apply `setScale`, `MathContext`, and `RoundingMode` at those exact boundaries.