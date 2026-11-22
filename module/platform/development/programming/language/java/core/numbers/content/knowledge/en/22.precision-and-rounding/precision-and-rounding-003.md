# Precision of 0 Is Not Scale of 0 in Java BigDecimal

When working with exact decimal numbers using `BigDecimal`, the two terms **precision** and **scale** describe two different aspects. In particular, **`MathContext` with `precision = 0` means unlimited significant digits during calculation**, and definitely does not mean the result has `scale = 0` (no digits after the decimal point).

## 1. Distinguishing Three Easily Confused Quantities

A `BigDecimal` represents a value by the formula:

```text
value = unscaledValue × 10^(-scale)
```

- **`BigDecimal.precision()`**: the number of digits in the unsigned integer coefficient (`unscaledValue`), excluding leading zeros. The number 0 has a precision of **1**. Trailing zeros in the coefficient are still counted when represented with their corresponding scale.
- **`BigDecimal.scale()`**: the negated exponent of 10 in the representation above. For numbers in normal form, a positive scale is typically the number of digits after the decimal point; a scale of 0 is an integer in the current representation; a negative scale is also valid.
- **`MathContext.getPrecision()`**: the maximum number of significant digits that an operation applying `MathContext` will retain when rounding. Specifically, the value **0** is the signal for *unlimited precision*: no precision limit is applied. It is not an actual `BigDecimal` precision of 0.

Examples:

| Initialized value | `precision()` | `scale()` | Explanation |
|---|---:|---:|---|
| `new BigDecimal("123.4500")` | 7 | 4 | The unscaled integer is `1234500`, with 7 digits. |
| `new BigDecimal("0.0012300")` | 5 | 7 | The coefficient `12300` has 5 digits, scale is 7. |
| `new BigDecimal("1000")` | 4 | 0 | Value has a scale 0 representation, though precision is 4. |
| `new BigDecimal("1E+3")` | 1 | -3 | Same numerical value 1000, but different representation. |
| `new BigDecimal("0.00")` | 1 | 2 | Value equal to 0 has precision 1, still keeps scale 2. |

**Remember:** precision describes **significant digits**, while scale describes **the position of the decimal point in the representation**. The two quantities are not two names for the same metric.

## 2. How Does a `MathContext` with Precision Equal to 0 Behave?

`MathContext` defines precision and `RoundingMode` for `BigDecimal` operations that accept a context argument:

```java
MathContext unlimited = MathContext.UNLIMITED;
MathContext alsoUnlimited = new MathContext(0, RoundingMode.DOWN);

System.out.println(unlimited.getPrecision());     // 0
System.out.println(alsoUnlimited.getPrecision());  // 0
```

Both contexts above **do not round merely due to a significant-digit limit**, regardless of the configured rounding mode. `MathContext.UNLIMITED` has `precision = 0` and `RoundingMode.HALF_UP`; this rounding mode does not turn it into a precision-limiting context.

For example, rounding with an unlimited context does not change the source number:

```java
BigDecimal x = new BigDecimal("1234.567");
BigDecimal y = x.round(MathContext.UNLIMITED);
// y = 1234.567; y.precision() = 7; y.scale() = 3
```

However, **unlimited does not mean every operation always returns a result successfully**:

- Addition, subtraction, and multiplication can represent finite decimal results exactly, subject to resource limits and the scale range supported by `BigDecimal`.
- Division with an infinite repeating decimal result, such as `1 / 3`, cannot be represented exactly by a finite `BigDecimal`. With `MathContext.UNLIMITED` or `new MathContext(0, ...)`, `divide` will throw `ArithmeticException` because there is no finite precision to round to.
- Division by 0 still throws an exception. Unlimited precision does not remove mathematical error conditions.
- **There is no rule guaranteeing that scale stays unchanged** during calculation. The scale of the result also depends on the operation, the operands' scales, and the exact representation of the result.

For example, `new BigDecimal("1.20").add(new BigDecimal("3.4"), MathContext.UNLIMITED)` gives `4.60` (scale 2), while the corresponding multiplication gives `4.080` (scale 3). An unlimited context does not reduce either result to scale 0.

## 3. What Does `setScale(0)` Act On?

`setScale(0, roundingMode)` requires **a result with scale equal to 0**. If the fractional part is non-zero, Java must apply the provided rounding mode:

```java
BigDecimal x = new BigDecimal("1234.567");

BigDecimal a = x.setScale(0, RoundingMode.HALF_UP); // 1235
BigDecimal b = x.setScale(2, RoundingMode.HALF_UP); // 1234.57
```

- `a.scale() == 0`, yet `a.precision() == 4`. Scale 0 does not make precision 0.
- `b.scale() == 2` because there are exactly two digits after the decimal point in the representation.
- `x.setScale(0)` (without `RoundingMode`) succeeds only if the scale can be changed **exactly**, such as `1234.000` to `1234`; with `1234.567` it throws `ArithmeticException` because rounding is required.
- `RoundingMode.UNNECESSARY` means "information loss is not allowed": if changing the scale requires rounding, an exception is thrown.

`BigDecimal` is immutable: `setScale`, `round`, and arithmetic operations return a result object; they do not silently mutate the source variable's value.

## 4. `round(MathContext)` Differs from `setScale`

With the same number:

| Operation | Result value | Precision | Scale | Applied constraint |
|---|---|---:|---:|---|
| `new BigDecimal("1234.567")` | `1234.567` | 7 | 3 | Original representation |
| `x.round(MathContext.UNLIMITED)` | `1234.567` | 7 | 3 | Unlimited significant digits |
| `x.round(new MathContext(3, HALF_UP))` | `1.23E+3` | 3 | -1 | 3 significant digits |
| `x.setScale(0, HALF_UP)` | `1235` | 4 | 0 | 0 digits after decimal point |

In the table, `HALF_UP` is `RoundingMode.HALF_UP`.

Observe the precision 3 row: `1.23E+3` has the numeric value **1230**, differing from **1235** of `setScale(0, HALF_UP)`. Rounding to 3 significant digits means rounding to the tens place in this case; the resulting scale is even **negative**. Therefore, replacing `setScale(0, ...)` with `round(new MathContext(0, ...))` is a fundamental error regarding the requirement.

One subtlety: if precision-based rounding causes the coefficient to be normalized, the result may switch to scientific notation. `toPlainString()` can be used when a plain decimal display is needed, but it only changes **how it is displayed**, not setting scale to 0 or altering the rounding rule.

## 5. Standalone Runnable Java 17+ Example

Save the file `PrecisionZeroVsScaleZero.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionZeroVsScaleZero {
    private static void show(String label, BigDecimal value) {
        System.out.println(label + ": " + value
                + " | precision=" + value.precision()
                + " | scale=" + value.scale());
    }

    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234.567");
        MathContext unlimited = new MathContext(0, RoundingMode.DOWN);

        show("source", value);
        show("MathContext(0)", value.round(unlimited));
        show("setScale(0)", value.setScale(0, RoundingMode.HALF_UP));
        show("MathContext(3)",
                value.round(new MathContext(3, RoundingMode.HALF_UP)));

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");
        show("zero 0.00", new BigDecimal("0.00"));
        show("zero 0", BigDecimal.ZERO);

        System.out.println("1 / 8 unlimited: "
                + one.divide(new BigDecimal("8"), MathContext.UNLIMITED));

        try {
            System.out.println("1 / 3 unlimited: "
                    + one.divide(three, MathContext.UNLIMITED));
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 unlimited: ArithmeticException");
        }

        System.out.println("1 / 3 precision=4: "
                + one.divide(three,
                        new MathContext(4, RoundingMode.HALF_UP)));
        System.out.println("1 / 3 scale=2: "
                + one.divide(three, 2, RoundingMode.HALF_UP));
    }
}
```

Compile and run:

```bash
javac PrecisionZeroVsScaleZero.java
java PrecisionZeroVsScaleZero
```

Standard output:

```text
source: 1234.567 | precision=7 | scale=3
MathContext(0): 1234.567 | precision=7 | scale=3
setScale(0): 1235 | precision=4 | scale=0
MathContext(3): 1.23E+3 | precision=3 | scale=-1
zero 0.00: 0.00 | precision=1 | scale=2
zero 0: 0 | precision=1 | scale=0
1 / 8 unlimited: 0.125
1 / 3 unlimited: ArithmeticException
1 / 3 precision=4: 0.3333
1 / 3 scale=2: 0.33
```

In the program, `new MathContext(0, RoundingMode.DOWN)` does not truncate `1234.567` down to an integer; `setScale(0, HALF_UP)` is what actually sets the scale to 0. Furthermore, finite precision 4 lets `1 / 3` return `0.3333`, whereas fixed scale 2 gives `0.33`.

## 6. Choosing the Right Tool for Each Requirement

| Real-world task | Approach |
|---|---|
| Need exact calculations without actively limiting significant digits | Use exact operations or `MathContext.UNLIMITED`; explicitly handle infinite repeating division cases. |
| Need finite significant digits for measurement/approximation algorithms | Use `MathContext(p, RoundingMode)` with `p > 0`; keep rounding rules consistent across the chain of operations. |
| Need exactly 2 decimal places for a monetary value or specified output | Use `setScale(2, RoundingMode...)` per business rules; do not use precision 2 as a substitute. |
| Need to round to integer units | Use `setScale(0, RoundingMode...)` and verify the result. |
| Need to ensure an operation must not lose digits | Use `UNNECESSARY` mode for operations that might require rounding and handle `ArithmeticException`. |

Currency example: `new BigDecimal("12.345").setScale(2, RoundingMode.HALF_UP)` gives `12.35`. Conversely, `round(new MathContext(2, RoundingMode.HALF_UP))` gives `12`: this is **two significant digits**, not two digits after the decimal point.

When creating a `BigDecimal` from decimal numbers, prefer the string constructor or `BigDecimal.valueOf(double)` depending on the input data. `new BigDecimal(0.1)` retains the true binary value of `double`, so it can carry an unexpectedly long sequence of decimal digits; this issue is independent of whether the context precision is 0 or not.

## 7. Common Pitfalls

1. **Mistaking `MathContext`'s `precision = 0` for "result has no digits".** The 0 convention in a context means unlimited; `BigDecimal.precision()` of the number 0 is still 1.
2. **Thinking unlimited precision means scale equals 0.** The scale of `new BigDecimal("1.2300")` is 4 even though `round(MathContext.UNLIMITED)` preserves that representation.
3. **Thinking unlimited precision automatically handles infinite division.** `1 / 3` needs a finite precision or a scale with `RoundingMode` when an approximate result is desired.
4. **Mixing up rounding by significant digits with rounding by decimal places.** `MathContext(3)` differs from `setScale(3)`. You must choose based on the unit of measure or business rule.
5. **Using `equals` to compare numeric values when scales differ.** `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` returns `false`, because `equals` checks scale as well; `compareTo` returns 0 because the numeric values are equal.
6. **Assuming scale is always non-negative or always preserved.** For example, `new BigDecimal("1000").stripTrailingZeros()` can become `1E+3` with scale -3. `stripTrailingZeros()` only normalizes the representation; it does not mean "round to integer".
7. **Calling `setScale` and forgetting to assign the result.** With an immutable type, you must use `result = value.setScale(...)` or use the returned value directly.

## 8. Self-Check

- What is `new MathContext(0, RoundingMode.HALF_EVEN).getPrecision()` equal to? **0**, indicating unlimited precision.
- Does `new BigDecimal("7.000").setScale(0, RoundingMode.UNNECESSARY)` succeed? **Yes**, yielding `7` because all discarded digits are 0.
- What about `new BigDecimal("7.001").setScale(0, RoundingMode.UNNECESSARY)`? **Throws `ArithmeticException`**, because rounding is required.
- What is `new BigDecimal("0.00").scale()` equal to? **2**; while `precision()` is **1**.
- Does `new BigDecimal("1000").round(new MathContext(2, RoundingMode.HALF_UP))` have scale equal to 0? **Not necessarily**: the result is `1.0E+3`, precision 2, scale -2.

**Rule of thumb:** to limit *how many significant digits*, use `MathContext` with positive precision; to limit *how many digits after the decimal point*, use `setScale`. A `MathContext` precision value of **0** only removes the precision limit, not setting scale to 0.
