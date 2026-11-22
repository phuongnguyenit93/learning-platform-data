# Aggregating BigDecimal With reduce and Explicit Rounding Rules

In the **Numeric Aggregation Accuracy** chapter of the **Java Stream API**, summing money, taxes, fees, or decimal numbers requiring high accuracy demands more than a call to `sum()`. With `BigDecimal` data, we typically use `map` to produce the terms to sum and `reduce` to aggregate them. The most important decision is **at which step to round, to how many digits, and with which rounding mode**.

This lesson builds a declarative pipeline with verifiable results: adding `BigDecimal` values **exactly throughout aggregation**, then rounding at a clearly defined **business boundary**. It also explains why rounding inside an accumulator can break *associativity* and produce different results when changing grouping or switching to a parallel stream.

## 1. Why Not Sum Money With double?

`double` represents numbers in IEEE 754 binary floating-point format. Many decimal numbers such as `0.1` have no finite binary representation, so some additions produce representation errors:

~~~java
double a = 0.1;
double b = 0.2;

System.out.println(a + b); // 0.30000000000000004
~~~

`BigDecimal` represents a number using an **unscaled integer value (*unscaled value*)** and a **scale**. When constructed from a decimal string, the value matches the exact digits provided:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
~~~

When initializing financial data, prefer:

- `new BigDecimal("19.995")` if the value comes from text, JSON, or a source with defined decimal digits.
- `BigDecimal.valueOf(42L)` if an integer value is used as a quantity or monetary amount.
- `BigDecimal.valueOf(0.1)` when forced to convert an existing `double`: it relies on `double`'s canonical decimal string representation, yet **cannot recover information already lost** in earlier floating-point operations.

Avoid `new BigDecimal(0.1)` when the goal is the exact decimal `0.1`, because that constructor takes the raw binary approximation of the `double`:

~~~java
System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625

System.out.println(new BigDecimal("0.1")); // 0.1
~~~

`BigDecimal` avoids representation error **if the inputs are already exact**. It does not choose a rounding policy on its own, eliminate input errors, or pick the right currency unit automatically.

## 2. Basic Pipeline: map Then reduce

Suppose each invoice line has a quantity and a unit price. The exact line amount is:

\[
\text{line total} = \text{unit price} \times \text{quantity}
\]

The sum before rounding is:

\[
S = \sum_{i=1}^{n} p_i q_i
\]

In the Stream API, that is the pipeline:

~~~java
import java.math.BigDecimal;
import java.util.List;

record Line(long quantity, BigDecimal unitPrice) {}

List<Line> lines = List.of(
        new Line(2, new BigDecimal("12.345")),
        new Line(1, new BigDecimal("3.210"))
);

BigDecimal exactTotal = lines.stream()
        .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(exactTotal); // 27.900
~~~

Explanation:

1. `lines.stream()` creates the source from the collection.
2. `map` turns each `Line` into a `BigDecimal` representing that line's amount.
3. `reduce(BigDecimal.ZERO, BigDecimal::add)` uses **0 as the identity** and `add` to combine the amounts.
4. `exactTotal` holds the exact result according to the input values, **with no rounding policy applied yet**.

The sum in the example is `2 × 12.345 + 3.210 = 27.900`. `multiply` and `add` **without passing a `MathContext`** perform exact decimal arithmetic; the resulting scale is preserved according to `BigDecimal`'s rules.

Choosing `BigDecimal.ZERO` as the identity lets an empty Stream return `0` instead of needing to handle `Optional.empty()`. Some systems then normalize to two decimal places:

~~~java
import java.math.RoundingMode;

BigDecimal payable = exactTotal.setScale(2, RoundingMode.HALF_UP);
System.out.println(payable); // 27.90
~~~

This makes the two steps explicit: **compute the exact sum** and **round for payment/display**.

## 3. Define the Rounding Policy Before Writing reduce

There is no single rounding rule that fits every country, currency, or business domain. Before writing code, define everything clearly:

| Question | Example decision | Why it matters |
| --- | --- | --- |
| **Target unit and scale** | Two decimal places for an illustrative monetary amount | Scale determines the smallest unit the result will represent. |
| **Rounding mode** | `RoundingMode.HALF_UP` or `HALF_EVEN` | Two rules can yield different results at an exact midpoint. |
| **Rounding point** | Per line, per tax item, per invoice, or after grouping | Summing then rounding does not always equal rounding parts then summing. |
| **Input data** | Unit prices may have 3–4 decimal places | Precision must not be silently truncated before computing. |
| **Data grouping** | Totals by customer, invoice, or transaction date | You must know when each group is allowed to be rounded. |
| **Negative amounts and refunds** | Refunds, downward adjustments | Rounding rules must apply consistently to negative numbers too. |

Illustrative policy example:

> Sum all charges occurring in **one invoice** exactly, then round the invoice total to **2 decimal places** using `RoundingMode.HALF_UP`. Negative amounts are added as negative numbers. Do not round individual lines before summing.

This rule is an **exercise assumption**, not a legal standard for every currency or invoice. In a real application, the policy must come from business requirements, contracts, accounting/tax regulations, or the integration specification in use.

## 4. Complete Example: Rounding After reduce

Three line items each worth `0.005` clearly demonstrate the difference between rounding points.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

public class InvoiceReductionDemo {
    record Line(String sku, long quantity, BigDecimal unitPrice) {}

    private static final int MONEY_SCALE = 2;
    private static final RoundingMode MONEY_ROUNDING = RoundingMode.HALF_UP;

    static BigDecimal exactSubtotal(List<Line> lines) {
        return lines.stream()
                .map(line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    static BigDecimal payable(List<Line> lines) {
        return exactSubtotal(lines).setScale(
                MONEY_SCALE, MONEY_ROUNDING);
    }

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new Line("A", 1, new BigDecimal("0.005")),
                new Line("B", 1, new BigDecimal("0.005")),
                new Line("C", 1, new BigDecimal("0.005"))
        );

        System.out.println(exactSubtotal(lines)); // 0.015
        System.out.println(payable(lines));        // 0.02

        BigDecimal roundedPerLine = lines.stream()
                .map(line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity()))
                        .setScale(MONEY_SCALE, MONEY_ROUNDING))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        System.out.println(roundedPerLine); // 0.03
    }
}
~~~

Where they differ:

~~~text
Add exactly, then round:
  0.005 + 0.005 + 0.005 = 0.015
  0.015 -> 0.02 (HALF_UP, 2 decimal places)

Round each line, then add:
  0.005 -> 0.01
  0.005 -> 0.01
  0.005 -> 0.01
  Sum = 0.03
~~~

**Both calculations can be valid under different business policies.** They are not equivalent and must be chosen deliberately. If the specification requires rounding each line before summing, express that in `map` and test that rule. If it requires rounding at the invoice level, keep lines exact until after `reduce`.

Note: `setScale(2, ...)` does not make the prior calculation any more accurate. It specifies **how to convert** the exact value to a result with two decimal places.

## 5. Comparing Common RoundingMode Values

With `setScale(2, mode)`, two decimal digits are retained, while the remainder determines whether the last digit changes.

| Original value | `HALF_UP` | `HALF_EVEN` | `DOWN` | `UP` |
| --- | ---: | ---: | ---: | ---: |
| `2.344` | 2.34 | 2.34 | 2.34 | 2.35 |
| `2.345` | 2.35 | 2.34 | 2.34 | 2.35 |
| `2.355` | 2.36 | 2.36 | 2.35 | 2.36 |
| `-2.345` | -2.35 | -2.34 | -2.34 | -2.35 |

Meaning:

- `HALF_UP`: rounds toward nearest neighbor; if equidistant, rounds **away from 0**.
- `HALF_EVEN`: rounds toward nearest neighbor; if equidistant, chooses the result whose **last retained digit is even** (*banker's rounding*).
- `DOWN`: rounds toward **0**; not synonymous with always rounding downward on the number line.
- `UP`: rounds **away from 0**.
- `CEILING`: toward positive infinity; `FLOOR`: toward negative infinity. Distinguish carefully from `UP`/`DOWN` when handling negative numbers.
- `UNNECESSARY`: rejects operations requiring rounding by throwing `ArithmeticException`.

`HALF_EVEN` is often chosen to reduce rounding bias across many roundings, yet that **does not replace choosing the right rounding point**. If a contract specifies `HALF_UP`, never switch to `HALF_EVEN` just because the other option is common in another system.

## 6. Why Should You Not Round Inside the Accumulator?

A snippet that looks short yet is easy to get wrong:

~~~java
BigDecimal total = values.stream()
        .reduce(BigDecimal.ZERO,
                (sum, value) -> sum.add(value)
                        .setScale(2, RoundingMode.HALF_UP));
~~~

Each time an element is added, the accumulator discards remainder digits before reading the next element. The result can depend on **how elements are grouped**. This is especially dangerous when calling `parallel()`, because the operation used in a reduction must satisfy associativity so work can be split and merged.

Consider an operator that rounds to an integer:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.function.BinaryOperator;

BinaryOperator<BigDecimal> roundedAdd =
        (x, y) -> x.add(y).setScale(0, RoundingMode.HALF_UP);

BigDecimal a = new BigDecimal("0.4");
BigDecimal b = new BigDecimal("0.4");
BigDecimal c = new BigDecimal("0.7");

BigDecimal left = roundedAdd.apply(roundedAdd.apply(a, b), c);
BigDecimal right = roundedAdd.apply(a, roundedAdd.apply(b, c));

System.out.println(left);  // 2
System.out.println(right); // 1
~~~

We get:

~~~text
(a ⊕ b) ⊕ c = round(round(0.4 + 0.4) + 0.7)
              = round(1 + 0.7) = 2

a ⊕ (b ⊕ c) = round(0.4 + round(0.4 + 0.7))
              = round(0.4 + 1) = 1
~~~

Since `left != right`, `roundedAdd` is **not associative**. Moreover, if `identity` is `BigDecimal.ZERO`, adding and rounding no longer preserves every input value: `roundedAdd.apply(BigDecimal.ZERO, new BigDecimal("0.4"))` returns `0` instead of `0.4`. Thus it fails the contract of a reduction with an identity for unrounded values.

By contrast, `BigDecimal::add` **without passing `MathContext`** is exact decimal addition and is suitable for aggregating across arbitrary groupings, as long as inputs can be processed validly:

~~~java
BigDecimal exact = values.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal rounded = exact.setScale(2, RoundingMode.HALF_UP);
~~~

This produces a numerical result independent of how elements are partitioned into groups. Whether a parallel stream is faster still needs separate measurement; on small datasets, overhead can outweigh the benefit.

### When Business Rules Mandate Rounding Each Entry

Sometimes business rules stipulate that each entry is rounded when booked and subsequent steps must sum the **finalized entries**. In that case, transform each element according to the finalized rule before reducing:

~~~java
BigDecimal sumOfBookedAmounts = values.stream()
        .map(value -> value.setScale(2, RoundingMode.HALF_UP))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Now each element already has its own business-finalized value. `reduce` still uses exact addition over the already-rounded values; this can run in parallel faithfully under addition's properties. It differs from rounding the **running cumulative sum** after every addition.

## 7. MathContext Is Not a Decimal-Places Policy

`MathContext` controls **precision** (number of significant digits), along with a `RoundingMode`. It differs from `setScale`, which controls the number of digits **after the decimal point**.

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal value = new BigDecimal("123.456");

System.out.println(
        value.round(new MathContext(4, RoundingMode.HALF_UP))
); // 123.5: four significant digits

System.out.println(
        value.setScale(4, RoundingMode.HALF_UP)
); // 123.4560: four digits after the decimal point
~~~

For monetary calculations requiring two digits after the decimal point, `setScale(2, roundingMode)` usually expresses the requirement accurately, unlike `new MathContext(2, ...)`.

Also distinguish:

~~~java
BigDecimal a = new BigDecimal("1234.56");
BigDecimal b = new BigDecimal("0.78");

// Exact addition:
BigDecimal exact = a.add(b); // 1235.34

// Limited-precision addition: may round during the addition itself.
BigDecimal approximate = a.add(
        b, new MathContext(5, RoundingMode.HALF_UP)
); // 1235.3
~~~

When calling `add(b, mathContext)` on each `reduce` step, intermediate rounding error appears inside the addition itself. It can break associativity and create discrepancies across execution strategies. For the rule **add exactly then round once**, do not pass `MathContext` into the accumulator.

If a specialized algorithm must compute with finite precision, explicitly design error bounds, combining rules, and execution order; do not assume parallel `reduce` will always yield identical results.

## 8. Division and Ratios: Choosing a Dedicated Rounding Point

`add` and `multiply` without `MathContext` operate exactly on finite decimal values. Conversely, division can produce non-terminating decimal expansions, such as `1 / 3`.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException because the result is non-terminating.
BigDecimal ratio = one.divide(three, 4, RoundingMode.HALF_EVEN);

System.out.println(ratio); // 0.3333
~~~

When ratios are needed, distinguish **internal precision** from the **final monetary scale**. For example, tax calculated as 7.5% of a pre-tax subtotal:

~~~java
BigDecimal subtotal = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.075");

BigDecimal exactTax = subtotal.multiply(taxRate); // 1.49925
BigDecimal tax = exactTax.setScale(2, RoundingMode.HALF_UP);

System.out.println(tax); // 1.50
~~~

Here multiplication retains full fractional precision, and the invoice-level tax rounding rule is applied afterward. Another system might specify per-line tax rounding or rounding at a different step. That policy must be documented and tested separately.

When computing an average, sum exactly first, then divide with the agreed scale and rounding mode:

~~~java
import java.util.List;

List<BigDecimal> prices = List.of(
        new BigDecimal("10.00"),
        new BigDecimal("10.01"),
        new BigDecimal("10.02")
);

BigDecimal total = prices.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal average = total.divide(
        BigDecimal.valueOf(prices.size()), 2, RoundingMode.HALF_UP);

System.out.println(average); // 10.01
~~~

Handle empty lists before dividing to avoid division by zero. `Collectors.averagingDouble` is not suitable if business rules require preserving exact `BigDecimal`-based results.

## 9. Two-Argument, One-Argument, and Three-Argument reduce

### 9.1. With Identity: `reduce(BigDecimal.ZERO, BigDecimal::add)`

~~~java
BigDecimal total = prices.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

- Returns `BigDecimal` directly.
- On an empty Stream, returns `BigDecimal.ZERO`.
- Uses the proper additive identity and exact addition to support splitting and merging elements.

### 9.2. Without Identity: `reduce(BigDecimal::add)`

~~~java
import java.util.Optional;

Optional<BigDecimal> maybeTotal = prices.stream()
        .reduce(BigDecimal::add);

BigDecimal totalOrZero = maybeTotal.orElse(BigDecimal.ZERO);
~~~

This overload returns `Optional<BigDecimal>` because the Stream may be empty. It fits when **“no data”** must be distinguished from **“a sum of 0”**. Choosing between the two depends on the application contract.

### 9.3. Three Arguments: identity, accumulator, combiner

Signature form:

~~~java
<U> U reduce(
        U identity,
        java.util.function.BiFunction<U, ? super T, U> accumulator,
        java.util.function.BinaryOperator<U> combiner)
~~~

For example, when the Stream source consists of `Line` objects and the reduction result is `BigDecimal`:

~~~java
BigDecimal total = lines.parallelStream()
        .reduce(
                BigDecimal.ZERO,
                (sum, line) -> sum.add(
                        line.unitPrice().multiply(
                                BigDecimal.valueOf(line.quantity()))),
                BigDecimal::add
        );

BigDecimal payable = total.setScale(2, RoundingMode.HALF_UP);
~~~

The accumulator adds a line's amount to the intermediate result; the combiner adds two intermediate sums exactly. Both preserve the identity and required associativity. However, this example is often easier to read by separating `map` and `reduce`:

~~~java
BigDecimal total = lines.parallelStream()
        .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

**Avoid using a `BigDecimal[]`, `AtomicReference<BigDecimal>`, or a shared mutable accumulator** to sum inside `forEach` on a parallel stream. `BigDecimal` is immutable; using `reduce` with exact addition aligns much better with combining results across multiple tasks.

## 10. Aggregating by Group Before Rounding

For reports by invoice, account, or customer, distinguish **per-group** totals from the **overall** total. If the business rule says “round per invoice”, group by invoice, sum exactly within each group, and then round each total.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Charge(String invoiceId, BigDecimal amount) {}

List<Charge> charges = List.of(
        new Charge("INV-1", new BigDecimal("0.005")),
        new Charge("INV-1", new BigDecimal("0.005")),
        new Charge("INV-2", new BigDecimal("0.005"))
);

Map<String, BigDecimal> exactByInvoice = charges.stream()
        .collect(Collectors.groupingBy(
                Charge::invoiceId,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        Charge::amount,
                        BigDecimal::add
                )
        ));

Map<String, BigDecimal> roundedByInvoice = exactByInvoice.entrySet()
        .stream()
        .collect(Collectors.toMap(
                entry -> entry.getKey(),
                entry -> entry.getValue()
                        .setScale(2, RoundingMode.HALF_UP)
        ));

System.out.println(roundedByInvoice.get("INV-1")); // 0.01
System.out.println(roundedByInvoice.get("INV-2")); // 0.01
~~~

The sum of amounts **after finalizing each invoice** is `0.01 + 0.01 = 0.02`. If you added **all charges before rounding** and rounded once, `0.015` would also become `0.02` in this example. Those two numbers happen to match here, yet the methods are not equivalent in general. To see the difference, consider three invoices, each with one `0.005` charge:

~~~text
Round each invoice:  0.01 + 0.01 + 0.01 = 0.03
Add all then round:  round(0.005 + 0.005 + 0.005) = 0.02
~~~

**Group boundaries are part of the rounding policy.** Never “optimize” by merging groups into one sum before rounding if the contract requires finalizing each group separately.

If an invoice has no charges, `groupingBy` on a Stream of `Charge` will not generate a key for that invoice. Use the master list of invoices to fill in `0.00` as required, or aggregate directly over each invoice object.

## 11. BigDecimal Immutability, Scale, and Comparisons

### 11.1. add Does Not Mutate the Original Object

~~~java
BigDecimal total = BigDecimal.ZERO;
total.add(new BigDecimal("10.50"));

System.out.println(total); // 0
~~~

`BigDecimal` is immutable. `add` returns a new result object; calling it does not modify `total`. The right way:

~~~java
total = total.add(new BigDecimal("10.50"));
System.out.println(total); // 10.50
~~~

That is also why `reduce(BigDecimal.ZERO, BigDecimal::add)` needs no shared mutable sum variable.

### 11.2. equals Considers Both Value and Scale

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));           // false
System.out.println(a.compareTo(b) == 0);   // true
~~~

`equals` requires both value and scale to match. `compareTo` orders by numeric value, so those two numbers are considered equal. In tests for monetary totals, if the contract requires an exact two-digit scale, check scale as well or normalize first:

~~~java
BigDecimal actual = new BigDecimal("2.0")
        .setScale(2, RoundingMode.UNNECESSARY);

System.out.println(actual.equals(new BigDecimal("2.00"))); // true
~~~

`RoundingMode.UNNECESSARY` rejects data that would lose nonzero digits to reach the new scale:

~~~java
new BigDecimal("2.001")
        .setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: rounding necessary
~~~

This mode is useful to **verify** that an amount is already stored in the smallest business-allowed unit rather than silently rounding it.

### 11.3. Input Scale Does Not Always Match Sum Scale

~~~java
BigDecimal total = new BigDecimal("1.2")
        .add(new BigDecimal("2.345"));

System.out.println(total);         // 3.545
System.out.println(total.scale()); // 3
~~~

When formatting for payment, call `setScale` at the appropriate business step. Do not rely on the apparent decimal places of input values to assume the sum already satisfies the rounding policy.

## 12. Data Validation and Real-World Risks

| Risk | Consequence | Mitigation |
| --- | --- | --- |
| Initializing money with `new BigDecimal(double)` | Carries `double`'s binary approximation | Accept exact decimal strings; use `BigDecimal.valueOf` if converting from an existing `double`. |
| Calling `doubleValue()` before `reduce` | Loses decimal accuracy | Keep monetary data as `BigDecimal` throughout every monetary calculation. |
| Rounding after every `add` | Result depends on grouping order, wrong in parallel | Add exactly first; round once at the business boundary. |
| Using `MathContext(2, ...)` to represent two decimal places | Confuses precision with scale | Use `setScale(2, mode)` at the right point. |
| No rounding mode when dividing non-terminating decimals | `ArithmeticException` | Specify scale, mode, or precision per business rules. |
| Assuming `BigDecimal.equals` checks numeric equality | `2.0` and `2.00` are treated as unequal | Use `compareTo` for value comparison, or normalize scale when required by contract. |
| `null` values in the source | `NullPointerException` in `add` or `multiply` | Validate input data; decide to reject, default to 0, or filter by explicit policy. |
| Sharing a mutable variable in a parallel stream | Race conditions, unstable results | Use a stateless reduction with contract-compliant accumulator/combiner. |
| Rounding per invoice yet summing multiple invoices before rounding | Incorrect total at the accounting boundary | Group and round each invoice separately before summing finalized amounts. |
| Very large datasets or quantities | Increased CPU, memory, and latency cost | Assess magnitude, choose suitable batching/grouping, control resources, and benchmark. |

For pipelines reading from databases, files, or APIs, never assume input data is always complete, ordered, and normalized. A `Stream` traverses data from its source; lambdas should avoid mutating the source during traversal. When an accounting snapshot is needed, ensure inputs remain stable for the duration of the aggregation.

## 13. Reproducible Testing of Rounding Policies

Put edge cases into standalone test cases. Below is the expected-results table when the policy is **exact sum, final rounding with `setScale(2, HALF_UP)`**:

| Input data | Exact sum | Rounded result |
| --- | ---: | ---: |
| `0.005`, `0.005`, `0.005` | 0.015 | 0.02 |
| `2.345` | 2.345 | 2.35 |
| `-2.345` | -2.345 | -2.35 |
| `10.001`, `-10.001` | 0.000 | 0.00 |
| No elements | 0 | 0.00 |
| `1.20`, `2.30` | 3.50 | 3.50 |

A small pure method that is easy to test:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Collection;

static BigDecimal sumAsMoney(Collection<BigDecimal> amounts) {
    BigDecimal exact = amounts.stream()
            .reduce(BigDecimal.ZERO, BigDecimal::add);

    return exact.setScale(2, RoundingMode.HALF_UP);
}
~~~

Tests can compare `BigDecimal` using `equals` when **scale is also part of the contract**:

~~~java
import java.util.List;

BigDecimal result = sumAsMoney(List.of(
        new BigDecimal("0.005"),
        new BigDecimal("0.005"),
        new BigDecimal("0.005")
));

if (!result.equals(new BigDecimal("0.02"))) {
    throw new AssertionError("Expected 0.02 but got " + result);
}
~~~

Do not test only “clean” values like `10.00 + 20.00`; exact midpoints, negative values, empty lists, and multiple groups are what reveal rounding-policy bugs.

## 14. Self-Check Exercises

**Exercise 1.** Predict both results when using `HALF_UP` with scale 2:

~~~java
List<BigDecimal> amounts = List.of(
        new BigDecimal("0.005"),
        new BigDecimal("0.005"),
        new BigDecimal("0.005")
);

BigDecimal a = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add)
        .setScale(2, RoundingMode.HALF_UP);

BigDecimal b = amounts.stream()
        .map(x -> x.setScale(2, RoundingMode.HALF_UP))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

**Answer:** `a = 0.02` and `b = 0.03`. Rounding each line independently then adding is not equivalent to summing everything exactly and rounding once.

**Exercise 2.** Why should the accumulator below not be used with `parallelStream()`?

~~~java
BigDecimal result = amounts.parallelStream()
        .reduce(BigDecimal.ZERO, (sum, x) ->
                sum.add(x).setScale(2, RoundingMode.HALF_UP));
~~~

**Answer:** The combining function rounds at every step, breaking associativity and the identity property for unrounded values. Parallel reduction can group elements differently from sequential iteration, altering the result. Replace it with `reduce(BigDecimal.ZERO, BigDecimal::add)` and apply `setScale(...)` to the final sum.

**Exercise 3.** Do the two expressions below produce the same result?

~~~java
BigDecimal x = new BigDecimal("123.456");

BigDecimal a = x.setScale(2, RoundingMode.HALF_UP);
BigDecimal b = x.round(new MathContext(2, RoundingMode.HALF_UP));
~~~

**Answer:** No. `a = 123.46` keeps two digits after the decimal point; `b = 1.2E+2` (numeric value 120) keeps two significant digits. Precision and scale measure two different properties.

**Exercise 4.** Choose a proper way to handle an input containing `1/3`.

**Answer:** Define a division and rounding rule, such as `BigDecimal.ONE.divide(new BigDecimal("3"), 4, RoundingMode.HALF_EVEN)` yielding `0.3333`. Do not call the no-rounding `divide` on a non-terminating decimal quotient, because it throws `ArithmeticException`.

**Exercise 5.** A company must round **each invoice** before summing total revenue. Can you sum all line items across all invoices and round once?

**Answer:** No. Group by invoice ID, compute the exact sum within each group, round each group's sum, and only then add the finalized results. **Invoice-level** rounding differs from **company-wide** rounding.

## 15. Key Takeaways

- Construct `BigDecimal` from exact decimal inputs, typically strings, when aggregating money or values requiring explicit decimal results.
- The default pattern for exact addition is `stream.map(...).reduce(BigDecimal.ZERO, BigDecimal::add)`.
- Apply `setScale(scale, roundingMode)` only at the specified **business finalization point**. Keep per-line, per-invoice, and full-report rounding distinct.
- Do not round inside an accumulator or combiner if you want reduction to preserve associativity and remain safe for grouping/parallelism.
- `MathContext` controls **significant digits**; `setScale` controls digits **after the decimal point**.
- Use `compareTo` for numeric equality; use `equals` when both scale and value must match. Handle empty sources, negative values, `null`, and non-terminating division explicitly.

**Main idea:** When aggregating `BigDecimal` with `reduce`, **define the rounding policy first, sum exactly inside the pipeline, and round at the right business boundary**. This keeps results explainable, testable, and compliant with the properties required for declarative processing or parallel streams.
