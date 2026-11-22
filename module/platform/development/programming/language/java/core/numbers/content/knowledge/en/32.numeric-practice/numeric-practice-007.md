# Designing Decimal Calculations with MathContext and RoundingMode in Java

A quoting, tax, discount, or pro-rata allocation system often uses `BigDecimal` to preserve exact decimal values. However, **using BigDecimal does not automatically make all results and rounding rules business-correct**: division may lack a finite decimal representation; operations may produce more digits than desired; the same dataset may yield different totals if rounded at different steps.

This practice guides you in designing a clear calculation policy through three components:

- **Value and representation:** `BigDecimal` stores an unscaled integer (`unscaledValue`) and a `scale`.
- **Precision during calculation:** `MathContext` defines `precision` (significant digits) and the `RoundingMode` used when digits must be dropped.
- **Unit-level result rounding:** `setScale(...)` and a `RoundingMode` policy specify the number of digits after the decimal point when finalizing a value.

The goal is not to pick one "best rounding mode for every system." The goal is to **create concrete rules that are easy to test and consistent with the business contract**.

## 1. The BigDecimal Decimal Model

The value is represented by the formula:

~~~text
numericValue = unscaledValue × 10^(-scale)
~~~

Examples:

| String passed to constructor | `unscaledValue()` | `scale()` | `precision()` |
|---|---:|---:|---:|
| `"12"` | 12 | 0 | 2 |
| `"12.00"` | 1200 | 2 | 4 |
| `"0.00123"` | 123 | 5 | 3 |
| `"123.456"` | 123456 | 3 | 6 |
| `"1E+3"` | 1 | -3 | 1 |

**`scale`** counts the decimal point position in the representation; it can be negative. **`precision`** counts the total number of digits in the `unscaledValue` integer, excluding the minus sign and leading zeros not part of the representation. Thus `precision = 4` does not mean "four digits after the decimal point," and `scale = 2` does not mean the number is computed with exactly two significant digits.

`BigDecimal` is immutable: operations return a new result object; calling `setScale` does not mutate the original object. Always assign or return the result if you want to use it in the next step.

Initialize from a decimal string:

~~~java
BigDecimal rate = new BigDecimal("0.075");
BigDecimal amount = new BigDecimal("123.45");
~~~

Avoid `new BigDecimal(0.1)` when you intend exact decimal 0.1, because the `double` constructor takes the **binary value** currently represented, which can differ from the decimal string the author expects. Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` if the data source is appropriate.

## 2. What Is MathContext?

`java.math.MathContext` is an immutable object holding two decisions:

1. `precision` — maximum number of **significant digits** for the result of an operation using the context, if precision is greater than 0;
2. `roundingMode` — how discarded digits must be handled when the result cannot be kept exact within that precision.

Create a context:

~~~java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext work = new MathContext(4, RoundingMode.HALF_EVEN);
~~~

`precision = 4` states that the rounded result of an operation using the context will have at most four significant digits. It does **not** say the result will always have four digits after the decimal point.

`MathContext` only takes effect when **passed to an operation with a matching overload**, such as `a.add(b, work)`, `a.multiply(b, work)`, `a.divide(b, work)`, `a.round(work)`. Creating a `MathContext work` variable and then calling `a.add(b)` does not automatically apply that context to the addition.

Example:

~~~java
BigDecimal a = new BigDecimal("123.456");
BigDecimal b = new BigDecimal("0.789");
MathContext work = new MathContext(4, RoundingMode.HALF_EVEN);

System.out.println(a.add(b));       // 124.245
System.out.println(a.add(b, work)); // 124.2
~~~

The exact result `124.245` has six significant digits; with a four-digit context, the result is `124.2`. The `0.045` part was rounded **during the operation using the context**. If you store this result and continue calculating, the discarded information does not magically reappear.

## 3. Core Difference: precision vs. scale

| Question | Suitable API | Meaning |
|---|---|---|
| "Keep at most 6 significant digits in the calculation result?" | `new MathContext(6, roundingMode)` | Limits **precision** during calculation |
| "Final result has exactly 2 digits after the decimal point?" | `setScale(2, roundingMode)` | Sets **scale** of the final representation |
| "Divide 1/3 and take 6 significant digits?" | `divide(divisor, mc6)` | `0.333333` |
| "Divide 1/3 and finalize to 2 decimal places?" | `divide(divisor, 2, roundingMode)` | `0.33` |
| "Lose zero significant digits?" | `MathContext.UNLIMITED` or omit context when operation has exact finite result | Result must be exact; non-terminating division throws an error |

An important example about magnitude:

~~~java
BigDecimal x = new BigDecimal("12345");
System.out.println(x.round(new MathContext(3, RoundingMode.HALF_UP)));
// 1.23E+4

System.out.println(x.setScale(2));
// 12345.00
~~~

The first result rounds to **three significant digits** (the value changes from 12345 to 12300). The second result preserves the **value 12345** while representing it with two digits after the decimal point. These are two different tasks.

Do not use `new MathContext(2)` to represent "money with two fractional digits." And do not assume `setScale(2)` alone is enough to control errors in intermediate divisions/values without analyzing the algorithm.

## 4. RoundingModes to Know

`java.math.RoundingMode` is an enum; use its enum constants instead of the obsolete `int`-typed `BigDecimal.ROUND_*` constants.

| Mode | Rule when non-zero digits must be discarded | How to understand |
|---|---|---|
| `UP` | Increase magnitude away from 0 | Whether positive or negative |
| `DOWN` | Toward 0 | Truncates discarded digits in magnitude |
| `CEILING` | Toward +∞ | For negative numbers, becomes less negative |
| `FLOOR` | Toward -∞ | For negative numbers, becomes more negative |
| `HALF_UP` | To nearest; ties round away from 0 | The .5 rounding commonly taught in school |
| `HALF_DOWN` | To nearest; ties round toward 0 | Differs only on exact midpoints |
| `HALF_EVEN` | To nearest; ties pick the even retained digit | Reduces bias across chains of roundings |
| `UNNECESSARY` | No significant digits may be discarded | Throws `ArithmeticException` if rounding is required |

Positive and negative example:

~~~java
BigDecimal positive = new BigDecimal("2.345");
BigDecimal negative = new BigDecimal("-2.345");

System.out.println(positive.setScale(2, RoundingMode.HALF_UP));   // 2.35
System.out.println(positive.setScale(2, RoundingMode.HALF_EVEN)); // 2.34
System.out.println(negative.setScale(2, RoundingMode.HALF_UP));   // -2.35
~~~

Here the second retained digit of `2.34` is 4 (even); at the exact midpoint `2.345`, `HALF_EVEN` picks `2.34`, while `HALF_UP` picks `2.35`. For `-2.345`, `HALF_UP` rounds **away from 0**, producing `-2.35`, not `-2.34`.

For `2.355` at scale 2, `HALF_EVEN` picks `2.36` because digit 6 is even. `HALF_EVEN` does not mean "always round down at .5," but rather the rule of choosing the even digit **only in exact tie cases between two choices**.

Do not automatically choose `HALF_EVEN` merely because of the term "banker's rounding"; tax, currency, discount, and reporting rules may mandate a different mode depending on the system, country, or contract.

## 5. Why Is MathContext Not a Global Setting?

Each `BigDecimal` operation has overloads **with or without `MathContext`**:

~~~java
BigDecimal exact = a.multiply(b);
BigDecimal rounded = a.multiply(b, work);
~~~

`exact` holds the exact multiplication result (if resources and representation allow), while `rounded` may have dropped digits per the context. Only a single `work` parameter is passed to the multiplication; it is not permanently attached to `a`, `b`, or the JVM.

When designing a sequence of operations, choose consistently:

- **Need full exactness before the finalization point:** prefer exact operators for operations with finite representations, and apply rounding only at defined boundaries.
- **Need to cap precision at each step** (simulating a decimal arithmetic standard or controlling complexity): pass `MathContext` into each operation per policy, accepting that intermediate rounding alters values.
- **Involves non-terminating division:** choose explicit scale and rounding or a `MathContext` with finite precision; do not expect the JVM to guess a policy.

Example:

~~~java
BigDecimal left = new BigDecimal("123.456");
BigDecimal right = new BigDecimal("0.789");
MathContext work = new MathContext(4, RoundingMode.HALF_EVEN);

System.out.println(left.multiply(right));       // 97.406784
System.out.println(left.multiply(right, work)); // 97.41
~~~

Once multiplication has returned `97.41`, calling `setScale(6)` only creates `97.410000`; it **does not** recover the `0.003216` lost in the previous rounding.

## 6. Division: Where Strategy Must Be Decided Most Clearly

The division `1 / 3` has an infinite decimal representation. `BigDecimal` does not silently pick a digit count by default:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException: non-terminating decimal expansion
~~~

Main options:

~~~java
// 6 significant digits:
BigDecimal withContext = one.divide(
        three, new MathContext(6, RoundingMode.HALF_EVEN)
); // 0.333333

// Fixed 2 digits after decimal point:
BigDecimal fixedScale = one.divide(
        three, 2, RoundingMode.HALF_UP
); // 0.33
~~~

| Overload | Result rule | When to use |
|---|---|---|
| `divide(divisor)` | Must be exact; non-terminating division errors | Quotient must be exact and is known to terminate |
| `divide(divisor, mathContext)` | Limits significant digits | Approximate calculation with specified precision |
| `divide(divisor, newScale, roundingMode)` | Sets the result's scale | Finalize ratio/unit to an exact number of decimal places |
| `divide(divisor, roundingMode)` | Uses the **dividend's** scale for the result | Easily causes surprises if input scales are not normalized |

**Avoid the `RoundingMode`-only overload if the dividend's scale is not part of the policy.** For example:

~~~java
BigDecimal divisor = new BigDecimal("3");
System.out.println(new BigDecimal("2.0").divide(divisor, RoundingMode.HALF_UP));
// 0.7
System.out.println(new BigDecimal("2.00").divide(divisor, RoundingMode.HALF_UP));
// 0.67
~~~

Both dividends have the same numeric value 2 yet different scales, causing the two divisions to use different result scales. Therefore, an API designed for a system must specify **exactness, precision, or scale** via business parameters rather than implicitly relying on how strings were entered.

Division by 0 is always invalid, even with a context; handle `ArithmeticException`/validate the divisor per contract.

## 7. MathContext.UNLIMITED and RoundingMode.UNNECESSARY

`MathContext.UNLIMITED` has `precision = 0`; operations with precision 0 require an **exact result**, and `RoundingMode` plays no rounding role when precision is 0. `MathContext.UNLIMITED` has a default rounding mode, yet does not turn `1/3` into a finite decimal.

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// Both throw ArithmeticException:
one.divide(three);
one.divide(three, MathContext.UNLIMITED);
~~~

`UNNECESSARY` is different: it is an **assertion that rounding is not permitted**, usable both with finite-precision contexts and with `setScale`.

~~~java
BigDecimal ok = new BigDecimal("2.340");
System.out.println(ok.setScale(2, RoundingMode.UNNECESSARY)); // 2.34

// Throws ArithmeticException: loses digit 5:
new BigDecimal("2.345").setScale(2, RoundingMode.UNNECESSARY);

// Throws ArithmeticException: needs precision > 3 to preserve exact value:
new BigDecimal("2.345").round(
        new MathContext(3, RoundingMode.UNNECESSARY));
~~~

Use `UNNECESSARY` at data boundaries when **policy requires exactness** and you want to detect non-conforming inputs instead of silently rounding. For instance, monetary inputs restricted to at most 2 decimal places can be checked with `setScale(2, RoundingMode.UNNECESSARY)` to reject `"12.345"` if that is the rule.

`UNNECESSARY` does not mean "never throw an exception" or "just log"; it **intentionally makes the operation fail** if any non-zero significant digit would be discarded.

## 8. Rounding Boundary: Per Line or Final Total?

Decimal calculations depend not only on rounding mode but also on **when rounding happens**. Consider three identical items `1.005` and a `HALF_UP` policy to 2 decimal places:

**Approach A: round each item then sum**

~~~java
BigDecimal each = new BigDecimal("1.005")
        .setScale(2, RoundingMode.HALF_UP); // 1.01
BigDecimal totalA = each.multiply(new BigDecimal("3"));
// 3.03
~~~

**Approach B: sum first then round total**

~~~java
BigDecimal exactTotal = new BigDecimal("1.005")
        .multiply(new BigDecimal("3"));     // 3.015
BigDecimal totalB = exactTotal.setScale(2, RoundingMode.HALF_UP);
// 3.02
~~~

Both numbers are valid **under two different finalization rules**; they are not equivalent. A difference of `0.01` appears despite identical inputs, identical `BigDecimal` type, identical `RoundingMode.HALF_UP`, and identical target scale.

Design must specify:

- Finalize rounding **on each invoice line** then compute the sum?
- Or keep intermediate values exact and **round once when finalizing the total**?
- Is tax applied per line or on the post-discount total?
- How are remainders allocated if the total must equal the sum of finalized line items?
- When refunds or negative adjustments occur, are the mode and operation order applied consistently?

Do not move where rounding happens just to make a test pass: that change can break balances or the business contract.

## 9. Standalone Java 17 Program and Verified Output

Create the file `DecimalDesignDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class DecimalDesignDemo {
    private static final MathContext WORK =
            new MathContext(4, RoundingMode.HALF_EVEN);
    private static final int MONEY_SCALE = 2;
    private static final RoundingMode MONEY_ROUND = RoundingMode.HALF_UP;

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("123.456");
        BigDecimal b = new BigDecimal("0.789");
        System.out.println("exact add = " + a.add(b));
        System.out.println("context add = " + a.add(b, WORK));
        System.out.println("exact multiply = " + a.multiply(b));
        System.out.println("context multiply = " + a.multiply(b, WORK));
        System.out.println("prec and scale = "
                + a.precision() + " / " + a.scale());

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");
        System.out.println("division context = "
                + one.divide(three,
                        new MathContext(6, RoundingMode.HALF_EVEN)));
        System.out.println("division fixed scale = "
                + one.divide(three, MONEY_SCALE, MONEY_ROUND));

        BigDecimal halfUp = new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal halfEven = new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN);
        System.out.println("half up / even = " + halfUp + " / " + halfEven);
        System.out.println("negative half up = "
                + new BigDecimal("-2.345")
                        .setScale(2, RoundingMode.HALF_UP));
        System.out.println("round precision = "
                + new BigDecimal("999.9")
                        .round(new MathContext(3, RoundingMode.HALF_UP)));
        System.out.println("money 12345.00 = "
                + new BigDecimal("12345").setScale(2));

        BigDecimal x = new BigDecimal("1.005");
        BigDecimal each = x.setScale(2, MONEY_ROUND)
                .multiply(new BigDecimal("3"));
        BigDecimal end = x.multiply(new BigDecimal("3"))
                .setScale(2, MONEY_ROUND);
        System.out.println("round each = " + each);
        System.out.println("round at end = " + end);

        try {
            one.divide(three);
        } catch (ArithmeticException ex) {
            System.out.println("unlimited divide = ArithmeticException");
        }
        try {
            new BigDecimal("2.345")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("unnecessary scale = ArithmeticException");
        }
        try {
            new BigDecimal("2.345").round(
                    new MathContext(3, RoundingMode.UNNECESSARY));
        } catch (ArithmeticException ex) {
            System.out.println("unnecessary precision = ArithmeticException");
        }
        System.out.println("exact scale = "
                + new BigDecimal("2.340")
                        .setScale(2, RoundingMode.UNNECESSARY));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 DecimalDesignDemo.java
java DecimalDesignDemo
~~~

Verified output:

~~~text
exact add = 124.245
context add = 124.2
exact multiply = 97.406784
context multiply = 97.41
prec and scale = 6 / 3
division context = 0.333333
division fixed scale = 0.33
half up / even = 2.35 / 2.34
negative half up = -2.35
round precision = 1.00E+3
money 12345.00 = 12345.00
round each = 3.03
round at end = 3.02
unlimited divide = ArithmeticException
unnecessary scale = ArithmeticException
unnecessary precision = ArithmeticException
exact scale = 2.34
~~~

Notice the line `round precision = 1.00E+3`: when `999.9` is rounded to three significant digits, rounding carries into the thousands place. `MathContext` does not force output formatting like `1000.00` or preserve the original scale.

In the program, `WORK` is an **illustrative** policy for the exercise, not a recommendation that every monetary system should use 4 significant digits. `MONEY_SCALE = 2` is also an exercise assumption, not a default applicable to every currency in the world.

## 10. Designing a Business-Aligned Decimal Processing Flow

An auditable workflow separates four stages:

~~~text
Validated decimal input
        |
        v
Original BigDecimal value + unit + metadata
        |
        v
Operations with published precision/rounding rules
        |
        v
Finalization point: setScale or divide with fixed scale
        |
        +---> Finalized value stored/exported in machine-readable form
        |
        +---> Display string per locale and UI formatting
~~~

**Step 1 — Identify the unit:** is `12.34` 12.34 VND, 12.34 USD, or a rate of 12.34%? A decimal number carries no unit; store the unit alongside the data or inside a domain type.

**Step 2 — Define input precision:** how many fractional digits at most may be entered, what are the magnitude limits, are exponential notation, negative numbers, and zero accepted?

**Step 3 — Define operation policy:** if only exact addition/multiplication is performed on finite data within resource limits, per-operation rounding may be unnecessary. If non-terminating division occurs, choose context/scale and rounding. For algorithms simulating fixed precision, pass `MathContext` consistently through the required steps.

**Step 4 — Define finalization timing:** one transaction may require rounding each line before summing; another algorithm may require exact summation then rounding the result. Encode this in code and tests.

**Step 5 — Separate storage and display:** `toPlainString()`, `toString()`, `DecimalFormat`, and `setScale()` serve different purposes. String formatting may pick commas, dots, and currency symbols by locale, yet formatting solely for display **does not alter the underlying BigDecimal value**.

A policy object helps prevent calculations from using ad-hoc modes everywhere:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class DecimalPolicy {
    private final int scale;
    private final RoundingMode rounding;

    public DecimalPolicy(int scale, RoundingMode rounding) {
        this.scale = scale;
        this.rounding = java.util.Objects.requireNonNull(rounding);
    }

    public BigDecimal finish(BigDecimal value) {
        return java.util.Objects.requireNonNull(value)
                .setScale(scale, rounding);
    }
}
~~~

This snippet is a **standalone class that compiles when saved to `DecimalPolicy.java`**, though it has no `main`; it demonstrates where to encapsulate the finalization policy. For a real application, validate `scale` against rules, units, and resource limits, and add tests for negative numbers, ties, and out-of-range values.

## 11. MathContext Does Not Automatically Enforce Decimal Places for Money

`MathContext.DECIMAL32`, `DECIMAL64`, and `DECIMAL128` have precisions **7, 16, 34** respectively and `RoundingMode.HALF_EVEN`. These are convenient precision presets, not currency rules.

~~~java
MathContext a = MathContext.DECIMAL32;  // precision 7
MathContext b = MathContext.DECIMAL64;  // precision 16
MathContext c = MathContext.DECIMAL128; // precision 34
~~~

Using `DECIMAL64` does not mean results always have **two digits after the decimal point**, nor does it enforce full physical IEEE decimal64 exponent/scale limits. `BigDecimal` with a context has matching precision without binding scale/exponent sets identically to the IEEE format.

For a currency with a two-decimal-place finalization policy, apply `setScale(2, mode)` at the appropriate boundary or store integer minor units if the workflow suits it. Do not use precision-2 context, precision-16 context, or "DECIMAL64" as a synonym for `scale = 2`.

If the requirement is a **percentage** with 6 significant digits, you can use a precision-6 context and convert units per contract; do not treat 0.075, 7.5%, and 7.5 as the same number without explicit rules.

## 12. Early Rounding and Double Rounding

Rounding is not necessarily distributive or associative like exact arithmetic. A particularly dangerous case is **rounding a result and then rounding it again at another scale**.

Consider `2.345` with `HALF_UP`:
- Directly calling `setScale(1, HALF_UP)` gives `2.3`, because the second digit is 4;
- Calling `setScale(2, HALF_UP)` first gives `2.35`, and then `setScale(1, HALF_UP)` again produces `2.4`.

~~~java
BigDecimal x = new BigDecimal("2.345");
BigDecimal direct = x.setScale(1, RoundingMode.HALF_UP);
BigDecimal twice = x.setScale(2, RoundingMode.HALF_UP)
                    .setScale(1, RoundingMode.HALF_UP);

System.out.println(direct); // 2.3
System.out.println(twice);  // 2.4
~~~

This is **double rounding**: the final result can change when rounding through an intermediate precision/scale. Therefore, if an application requires finalizing once at scale 1, do not arbitrarily insert a `setScale(2)` step just to "normalize formatting."

This also happens when a pipeline uses `MathContext` in earlier operations and then `setScale` at the end: two roundings can produce a different result than exact computation followed by one finalization. There is no universal strategy — computing with bounded precision may be a strict requirement. What matters is **knowing exactly which step alters the value** and writing tests matching the processing order.

## 13. BigDecimal.equals(), compareTo(), and Post-Operation Scale

Two `BigDecimal` instances can have equal numeric values while having different representations:

~~~java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.compareTo(y) == 0); // true
System.out.println(x.equals(y));         // false
~~~

`compareTo()` orders **by numeric value**; `equals()` also checks `scale`. Thus a `setScale(2)` step can change `equals()` results without changing numeric comparisons. When using instances as `HashMap` keys or `HashSet` elements, clearly decide whether identity includes scale.

`stripTrailingZeros()` removes trailing zeros without changing numeric value, though it can produce a negative scale:

~~~java
BigDecimal amount = new BigDecimal("1000.00");
System.out.println(amount.stripTrailingZeros()); // 1E+3
~~~

If storage policy requires `"1000.00"`, do not call `stripTrailingZeros` as a mandatory formatting step. `MathContext`, `setScale`, `stripTrailingZeros`, and `toPlainString()` serve distinct roles.

## 14. Exception Checking and Input Limits

A sound design handles errors proactively instead of catching every `ArithmeticException` and returning 0:

| Scenario | Reasonable response |
|---|---|
| Division by 0 | Reject divisor 0; report business-domain error |
| Exact `divide` but non-terminating result | Require precision/scale + rounding policy, or reject if exactness is mandatory |
| `setScale(2, UNNECESSARY)` would drop non-zero digits | Reject data not conforming to agreed scale |
| `new MathContext(-1, mode)` | `IllegalArgumentException`, as precision cannot be negative |
| Oversized input digit counts | Validate length/value to prevent excessive CPU and memory usage |
| Result exceeds database DECIMAL schema | Validate before saving; do not rely on the database to round per your policy |
| Converting `BigDecimal` to `int`/`long` | Use `intValueExact()`/`longValueExact()` if losing fractional parts or overflow is disallowed |

`BigDecimal` conceptually supports arbitrary precision, yet remains constrained by machine resources, the `int` range of `scale`, and library limits. An extreme exponent input, gigantic decimal string, or `toPlainString()` on a huge exponent can consume substantial memory. Validating data bounds is no less important than choosing a rounding mode.

Do not catch `ArithmeticException` and return `BigDecimal.ZERO` generically: it hides division by zero, misconfigured rounding policies, and invalid inputs, producing silent wrong results that are hard to audit.

## 15. Essential Tests for a Decimal Policy

A test suite should include at least these groups:

1. **Midpoint (tie):** `2.345` at scale 2 yields `HALF_UP = 2.35`, `HALF_EVEN = 2.34`.
2. **Negative numbers:** `-2.345` with `HALF_UP` and modes directed toward ±∞.
3. **Non-terminating division:** `1 / 3` must use context/scale; test the exception when using the exact overload.
4. **Terminating division:** `1 / 8 = 0.125` needs no rounding when keeping exact results.
5. **Per-line vs. total rounding:** `1.005 × 3` yields `3.03` or `3.02` depending on policy.
6. **Result scale:** `setScale(2)` gives `12345.00`, whereas precision 3 turns 12345 into `1.23E+4`.
7. **Mandatory no-data-loss:** `UNNECESSARY` rejects `2.345` when scale 2 is required, yet allows `2.340` to become `2.34`.
8. **Conversion overflow and storage limits:** check `longValueExact()` when converting to minor units.
9. **Immutability of initial value:** because `BigDecimal` is immutable, computations/formatting do not mutate the original instance.
10. **Input policy:** reject out-of-contract formats/values before calculating and storing.

At the application level, test both **numeric value** and, when needed, **scale**:

~~~java
BigDecimal actual = new BigDecimal("2.340").setScale(2);
BigDecimal expected = new BigDecimal("2.34");

System.out.println(actual.equals(expected));     // true
System.out.println(actual.compareTo(expected));  // 0
~~~

Do not write a test that only compares UI strings when the feature needs to verify numeric values; conversely, if the contract requires exactly two digits after the decimal point, check `scale()` or appropriate output formatting as well.

## 16. Self-Practice Exercises

### Exercise 1 — precision or scale?

Given `x = new BigDecimal("98765.4321")`, you want to:
- (A) keep four significant digits;
- (B) keep two digits after the decimal point.

**Guided answer:** (A) calls `x.round(new MathContext(4, policy))`; (B) calls `x.setScale(2, policy)`. These are not two ways of writing the same result. With `HALF_UP`, (A) is `9.877E+4`, whereas (B) is `98765.43`. Choose the policy before implementing.

### Exercise 2 — per-line finalization

Three unit prices are all `1.005` currency units and a two-decimal-place total must be output. State two valid results under two different policies.

**Answer:** Round each line with `HALF_UP`: `1.01 × 3 = 3.03`. Sum first then round the total: `3.015 → 3.02`. The exact rule required by business logic must be documented.

### Exercise 3 — divide() throws an error

`new BigDecimal("1").divide(new BigDecimal("3"))` throws an exception even though it is not dividing by 0. Why?

**Answer:** Because `1/3` has an infinite decimal expansion, exact division cannot return a finite `BigDecimal`. You must specify precision/scale and rounding, or reject the operation if absolute exactness is required.

### Exercise 4 — MathContext.UNLIMITED

Does `MathContext.UNLIMITED` automatically make `1/3` a finite number?

**Answer:** No. `precision = 0` requires exact calculation without rounding; a division with an infinite decimal result throws `ArithmeticException`.

### Exercise 5 — ROUND_UNNECESSARY

Between `new BigDecimal("7.500")` and `new BigDecimal("7.505")`, which value can be converted to scale 2 using `RoundingMode.UNNECESSARY`?

**Answer:** `7.500 → 7.50` exactly; `7.505` cannot preserve its value at scale 2, so it throws an exception.

### Exercise 6 — double rounding

Suppose the final requirement is one decimal place, rounding `HALF_UP`. Compare:
- `new BigDecimal("2.345").setScale(1, HALF_UP)`;
- `new BigDecimal("2.345").setScale(2, HALF_UP).setScale(1, HALF_UP)`.

**Answer:** Directly gives `2.3`; going through the intermediate step gives `2.4`. Do not add intermediate rounding steps unless required by the contract.

## 17. Production Checklist

Before applying `MathContext` and `RoundingMode` in real business logic, confirm:

- Inputs are exact decimals from strings, integers of the smallest unit, or sources with a clear contract—never silently passing through `double` unintentionally.
- Units, input precision, finalization scale, and magnitude bounds are all defined.
- Operations requiring finite precision receive `MathContext` per the calculation plan, not confused with scale.
- Division specifies explicit scale/precision, mode, and divisor-0 handling rules.
- You know clearly when to calculate exactly and when to round; no accidental "round every step" loops appear.
- Choosing `HALF_UP`, `HALF_EVEN`, `CEILING`, `FLOOR`, or `UNNECESSARY` is justified by business rules and tested with negative numbers and ties.
- Finalized data is stored matching the schema and units; UI formatting is a separate responsibility.
- Where zero digit loss must be proven, use `UNNECESSARY` and handle errors rather than silently rounding.
- Tests cover precision vs. scale, per-line vs. final-total rounding, and double rounding.
- All public APIs and stored fields use a consistent policy, avoiding "different defaults everywhere" that skews numbers.

## 18. References

- [BigDecimal — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `precision`, `scale`, preferred scales, `add`, `multiply`, `divide`, `setScale`, `round`, `stripTrailingZeros`.
- [MathContext — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): `precision`, `roundingMode`, `UNLIMITED`, `DECIMAL32`, `DECIMAL64`, `DECIMAL128`.
- [RoundingMode — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): the eight rounding policies and midpoint handling examples.
