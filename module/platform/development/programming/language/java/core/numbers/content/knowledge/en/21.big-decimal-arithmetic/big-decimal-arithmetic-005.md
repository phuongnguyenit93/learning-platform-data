# `BigDecimal.pow()` and `BigDecimal.sqrt()` at Required Precision

## 1. Lesson Goals

When working with decimals that require control over significant digits, Java provides `BigDecimal` together with `MathContext`. The two main operations in this lesson are integer exponentiation `pow(int, MathContext)` and square root `sqrt(MathContext)`. You need to understand clearly when a result is exact, when a result is rounded, how to choose an appropriate precision, and the cases where the API rejects a calculation.

Important calls:

```java
BigDecimal power = base.pow(exponent, context);
BigDecimal root = value.sqrt(context);
```

`BigDecimal` can store decimal numbers with arbitrary precision, yet the square root of 2 or the reciprocal of 3 cannot be represented exactly by a finite sequence of decimal digits. Therefore, choosing precision and rounding rules is part of the computational requirement, not merely a display option.

## 2. Distinguishing `precision` and `scale`

`BigDecimal` represents the value `unscaledValue × 10^(-scale)`:

- **`precision`**: the number of significant digits of the decimal value, counted from the first nonzero digit. Precision in `MathContext` sets a limit on the number of significant digits *of the operation result*.
- **`scale`**: the number of digits to the right of the decimal point in the representation when scale is non-negative; scale can also be negative. `12.3400` has `precision() == 6` and `scale() == 4`.
- **`RoundingMode`**: the rule for handling discarded digits. `HALF_EVEN` rounds to the nearest value and picks an even last digit at an exact midpoint; `HALF_UP` rounds away from 0 at midpoints; `UNNECESSARY` requires that the result need no rounding.
- **`MathContext`**: holds precision and rounding mode. `new MathContext(8, RoundingMode.HALF_EVEN)` means *8 significant digits*, not *8 digits after the decimal point*.

Standalone example inside a Java method with `java.math.*` imported:

```java
BigDecimal value = new BigDecimal("12345.678");
MathContext mc4 = new MathContext(4, RoundingMode.HALF_EVEN);

System.out.println(value.round(mc4).toPlainString()); // 12350
System.out.println(value.setScale(4, RoundingMode.HALF_EVEN)
        .toPlainString());                              // 12345.6780
```

The first statement rounds to 4 significant digits; the second sets exact 4 digits after the decimal point. Adding trailing zeros can increase an object's `precision()`, yet it does not increase the arithmetic accuracy already computed.

Initialize from strings like `new BigDecimal("0.1")` to preserve the desired decimal value. `new BigDecimal(0.1)` preserves the exact binary `double` value that was previously approximated. If a source value is already a `double`, `BigDecimal.valueOf(double)` is usually more suitable than the `double` constructor, though it cannot recover digits already lost at the source.

## 3. Computing `pow`: Integer Exponents

### 3.1. `pow(int n)` Returns an Exact Result

```java
BigDecimal exact = new BigDecimal("1.2345").pow(3);
// 1.881365963625
```

In Java 17, `pow(n)` accepts integer exponents from **0 to 999_999_999**, and returns an exact result with unlimited precision. The API specifies that `BigDecimal.ZERO.pow(0)` returns `BigDecimal.ONE`. Even when an exponent is within the valid range, the calculation can produce a huge result and consume significant memory/time; do not use this indiscriminately for large exponents.

`pow` has no overload taking a `BigDecimal` as a fractional exponent. Writing `pow(1 / 2)` is wrong when wanting a root, because `1 / 2` in Java is integer division evaluating to `0`. Use `sqrt(mc)` for square roots.

### 3.2. `pow(int n, MathContext mc)` Returns a Result at Given Precision

```java
MathContext mc6 = new MathContext(6, RoundingMode.HALF_EVEN);
BigDecimal rounded = new BigDecimal("1.2345").pow(3, mc6);
// 1.88137: six significant digits
```

When `mc`'s precision is **positive**, this overload also permits **negative integer exponents**: `new BigDecimal("2").pow(-3, mc6)` evaluates to `0.125`. Negative exponents represent the reciprocal of a positive power and may require rounding. Base `0` with a negative exponent is invalid.

Constraints from the Java 17 `BigDecimal` contract:

| Case | Result |
| --- | --- |
| `x.pow(0)` or `x.pow(0, mc)` | Equals `1`, even when `x` equals `0`. |
| `x.pow(n)` with `n < 0` | Throws `ArithmeticException`. |
| `x.pow(n, mc)` with `n < 0` and `mc.precision > 0` | Computes reciprocal to precision; base must be nonzero. |
| `abs(n) > 999_999_999` | Throws `ArithmeticException`. |
| `mc.precision == 0` and `n < 0` | Throws `ArithmeticException`. |
| `mc.precision > 0` but number of decimal digits of `abs(n)` exceeds precision | Throws `ArithmeticException`, e.g., `pow(123, new MathContext(2))`. |
| Rounding needed when mode is `UNNECESSARY` | Throws `ArithmeticException`. |

**Algorithmic accuracy:** `pow(n, mc)` uses an internal exponentiation algorithm with extra working digits. Java 17 specifies that the result generally lies within **two ulps** of the exact value at the chosen precision (`ulp` is the unit in the last place). You must not claim `pow(n, mc)` always matches `pow(n).round(mc)` digit-for-digit in every case. When you strictly need the result of rounding *once* on the exact value and the exponent is small enough, you can compute `pow(n)` then `round(mc)`, accepting higher memory/time cost.

If the `pow` result will participate in further operations, consider computing with an intermediate precision higher than the output precision. Rounding after each step can lose important digits, especially when subtracting two nearly equal values.

## 4. Computing `sqrt(MathContext)` at Required Precision

`BigDecimal.sqrt(MathContext)` has existed since **Java 9**, so it works in Java 17+.

```java
MathContext mc8 = new MathContext(8, RoundingMode.HALF_EVEN);
BigDecimal root = new BigDecimal("2").sqrt(mc8);
// 1.4142136: eight significant digits
```

Watch out for these scenarios:

1. **Negative input:** `new BigDecimal("-4").sqrt(mc8)` throws `ArithmeticException`. `BigDecimal` does not return `NaN`.
2. **Exact root:** `new BigDecimal("9").sqrt(mc8)` returns value `3`. An exact result may use fewer significant digits than the given precision.
3. **Irrational root:** the square root of `2` has a non-terminating decimal expansion. To get a finite result, pass a `MathContext` with positive precision and an appropriate rounding mode.
4. **`MathContext.UNLIMITED`:** precision equal to `0` requests an exact result. `sqrt(4)` succeeds whereas `sqrt(2)` throws `ArithmeticException`, because there is no exact finite decimal representation.
5. **`RoundingMode.UNNECESSARY`:** requires the result to be exact within the allowed precision; throws `ArithmeticException` if rounding is needed.
6. **Preferred scale:** the preferred scale of the root is `value.scale() / 2` (integer division). The actual scale may differ due to representation/rounding rules. Do not treat scale as precision, and do not expect trailing zeros to always be preserved.

Per the Java 17 specification, `sqrt(mc)`'s result is within one `ulp` of the exact square root at that precision; with `HALF_UP`, `HALF_DOWN`, or `HALF_EVEN`, the error is within **half an ulp**. This is a property of calculation by significant digits, different from requiring a specific number of digits after the decimal point.

**Avoid going through `double`:**

```java
// Not equivalent to sqrt(mc) with decimal policy:
BigDecimal unsafe = new BigDecimal(Math.sqrt(2.0));
```

`Math.sqrt` uses `double` with a finite number of bits. Passing through `double` can lose information, overflow, or round according to a policy different from `MathContext`; if controlled decimal arithmetic is required, keep the entire calculation in `BigDecimal`.

## 5. Complete Java 17+ Program, Compile and Run

Save file **`PrecisionPowSqrtDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionPowSqrtDemo {
    public static void main(String[] args) {
        BigDecimal base = new BigDecimal("1.2345");
        MathContext mc6 = new MathContext(6, RoundingMode.HALF_EVEN);
        MathContext mc8 = new MathContext(8, RoundingMode.HALF_EVEN);

        System.out.println("pow exact = "
                + base.pow(3).toPlainString());
        System.out.println("pow precision 6 = "
                + base.pow(3, mc6).toPlainString());
        System.out.println("sqrt(2) precision 8 = "
                + new BigDecimal("2").sqrt(mc8).toPlainString());
        System.out.println("2^-3 precision 8 = "
                + new BigDecimal("2").pow(-3, mc8).toPlainString());
        System.out.println("sqrt(9) precision 8 = "
                + new BigDecimal("9").sqrt(mc8).toPlainString());
    }
}
```

Run in the directory containing the file, with JDK 17 or later:

```bash
javac PrecisionPowSqrtDemo.java
java PrecisionPowSqrtDemo
```

Stdout:

```text
pow exact = 1.881365963625
pow precision 6 = 1.88137
sqrt(2) precision 8 = 1.4142136
2^-3 precision 8 = 0.125
sqrt(9) precision 8 = 3
```

`toPlainString()` only formats the string without scientific notation when possible; it does not alter the value, re-round, or increase precision. The results above use string inputs so they do not carry `double` binary error.

## 6. Decimal Places Requirement: When to Use `setScale`

If the requirement is **6 significant digits**, pass `MathContext(6, ...)`. If the requirement is **6 digits after the decimal point**, you need to compute with sufficiently high working precision, then convert the result to scale 6:

```java
// Place inside main; import java.math.* at top of file.
int decimalPlaces = 6;
MathContext work = new MathContext(20, RoundingMode.HALF_EVEN);
BigDecimal unformatted = new BigDecimal("2").sqrt(work);
BigDecimal display = unformatted.setScale(decimalPlaces, RoundingMode.HALF_EVEN);
System.out.println(display.toPlainString()); // 1.414214
```

For the square root of 2 example, precision 20 provides more than enough digits to print 6 decimal places. **There is no universal formula “precision = decimal places + 2” for all values**: very large/small results, complex calculations, and values near rounding boundaries must be evaluated individually.

Rounding twice (*double rounding*) can lead to a final result that does not match rounding the exact mathematical value directly. If business requirements demand a result accurate to N decimal places, you must determine the error budget, increase working precision accordingly, and test near-threshold cases. For finance, business scale/rounding rules must be stated explicitly; MathContext does not inherently know currency rules.

For example, to display a fixed number of decimal places, you can choose `setScale(2, RoundingMode.HALF_EVEN)` after computing; if only comparing arithmetic values, you can keep the original `BigDecimal` and avoid premature formatting.

## 7. Exceptions and Input Validation

Operations can throw `ArithmeticException` if the domain is invalid, the precision requirement cannot be met, or `UNNECESSARY` forbids rounding. Example (inside a method, with `java.math.*` imported):

```java
MathContext mc = new MathContext(8, RoundingMode.HALF_EVEN);

try {
    new BigDecimal("-4").sqrt(mc);
} catch (ArithmeticException ex) {
    System.out.println("No real square root for negative numbers");
}
try {
    new BigDecimal("2").sqrt(MathContext.UNLIMITED);
} catch (ArithmeticException ex) {
    System.out.println("sqrt(2) cannot be represented with finite exactness");
}
try {
    new BigDecimal("2").pow(-1);
} catch (ArithmeticException ex) {
    System.out.println("Negative pow requires MathContext with positive precision");
}
```

If precision comes from user input, validate `precision > 0` for these approximate calculations; `new MathContext(-1)` throws `IllegalArgumentException`, while `new MathContext(0)` represents unlimited. For `pow`, check the exponent value, the number of digits in the exponent relative to precision, and a base of 0 when the exponent is negative.

You can encapsulate a consistent policy with the following class, saved separately as **`DecimalMath.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.Objects;

public final class DecimalMath {
    private DecimalMath() {}

    public static BigDecimal pow(BigDecimal base, int exponent, int precision) {
        Objects.requireNonNull(base, "base");
        if (precision <= 0) {
            throw new IllegalArgumentException("precision must be > 0");
        }
        MathContext mc = new MathContext(precision, RoundingMode.HALF_EVEN);
        return base.pow(exponent, mc);
    }

    public static BigDecimal sqrt(BigDecimal value, int precision) {
        Objects.requireNonNull(value, "value");
        if (precision <= 0) {
            throw new IllegalArgumentException("precision must be > 0");
        }
        MathContext mc = new MathContext(precision, RoundingMode.HALF_EVEN);
        return value.sqrt(mc);
    }
}
```

This class chooses `HALF_EVEN` as the default policy *for the example*. Real applications should allow choosing the mode per business requirements. If the base/exponent or radicand is invalid, the exception from `BigDecimal` will propagate to the caller to handle. Do not catch all `ArithmeticException` instances and silently return `BigDecimal.ZERO`, because that turns errors into wrong data.

## 8. Common Mistakes to Avoid

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking `precision = 8` means 8 digits after the decimal point | Precision counts significant digits | Separate MathContext for calculation and setScale for display |
| Using `pow(-2)` without MathContext | Exact overload does not accept negative exponents | Use `pow(-2, mc)` with positive precision |
| Using `sqrt(MathContext.UNLIMITED)` for numbers without a finite decimal root | Exact result cannot be represented | Use positive precision and a rounding mode |
| Using `pow(n)` for very large n when only a rounded result is needed | Creating the exact result consumes too many resources | Prefer `pow(n, mc)` when API error bounds are acceptable |
| Using `Math.pow` / `Math.sqrt` via `double` | Does not preserve decimal arithmetic per MathContext | Compute directly with `BigDecimal` |
| Comparing `BigDecimal` with `equals` when scales differ | `1.0` does not `equals` `1.00` even though arithmetically equal | Use `compareTo(...) == 0` when checking value only |
| Rounding to final precision at every calculation step | Accumulates intermediate error | Choose high enough working precision, round at appropriate boundaries |
| Using `new BigDecimal(0.1)` | Receives the exact value of the approximated `double` | Initialize from string or `BigDecimal.valueOf` |

## 9. Self-Practice and Verification

1. What exact result does `new BigDecimal("12.345").pow(2)` produce? What is it when rounded with `new MathContext(4, HALF_EVEN)`?
2. Why does `sqrt(4)` work with `MathContext.UNLIMITED`, whereas `sqrt(2)` does not?
3. Compute `new BigDecimal("10").pow(-2, new MathContext(5, HALF_EVEN))`; try removing `MathContext` and explain.
4. Design a way to display `sqrt(2)` with exactly two digits after the decimal point, distinguishing calculation precision from output scale.

Reference answers: (1) exact is `152.399025`, after rounding to four significant digits it is `152.4`; (2) the square root of 2 has an infinite decimal representation; (3) `0.01`, while `pow(-2)` without MathContext throws an exception; (4) compute `sqrt` with a MathContext of sufficient precision, then `setScale(2, HALF_EVEN)` gives `1.41`.

In practice, define **calculation precision**, **rounding mode**, and **output result scale** as three distinct requirements. `pow` handles exact or approximate integer powers; `sqrt` handles non-negative square roots at the chosen precision. For formulas requiring tight error bounds, verify algorithm limits and test at rounding boundaries.

Official API reference: [Java SE 17 — `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) (`pow(int)`, `pow(int, MathContext)`, `sqrt(MathContext)`).