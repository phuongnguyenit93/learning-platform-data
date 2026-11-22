# BigDecimal.divide: Choosing scale, RoundingMode, or MathContext in Java

Decimal division does not always produce a terminating decimal result. For example, \(1/8=0.125\) has an exact decimal representation, whereas \(1/3=0.3333\ldots\) continues infinitely. With `java.math.BigDecimal`, **how you call `divide` determines when rounding is allowed, the scale of the result, and the allowed precision**.

Java has several overloads of `divide`, with the four most important ones when learning being:

```java
BigDecimal a = BigDecimal.ONE;
BigDecimal b = BigDecimal.valueOf(3);

// a.divide(b);                            // exact; 1/3 causes ArithmeticException
BigDecimal x = a.divide(b, 2, RoundingMode.HALF_UP); // 0.33, scale 2
BigDecimal y = a.divide(b, RoundingMode.HALF_UP);    // 0, scale of a is 0
BigDecimal z = a.divide(b, new MathContext(3, RoundingMode.HALF_UP)); // 0.333
```

Short snippets in this lesson assume `import java.math.BigDecimal;`, `MathContext`, and `RoundingMode` and are placed inside a method/JShell. A complete, runnable Java 17+ program is in Section 12.

**General rule:** Choose the overload according to the **result contract**: whether you need exactness without rounding, a number of digits **after the decimal point**, to preserve the **dividend's scale**, or a number of **significant digits**.

## 1. Foundations: value, scale, and precision of BigDecimal

`BigDecimal` models a decimal number using:

\[
\text{value}=\text{unscaledValue}\times10^{-\text{scale}}
\]

For example, `new BigDecimal("12.3400")` has unscaled value `123400`, scale 4, and precision 6. Two quantities are easily confused:

- **Scale**: the decimal position in the representation. When non-negative, it is usually the number of digits after the decimal point; **scale can also be negative**.
- **Precision**: the total number of significant digits in the decimal form of the unscaled value, not the number of digits after the decimal point.

```java
BigDecimal number = new BigDecimal("12.3400");

System.out.println(number.unscaledValue()); // 123400
System.out.println(number.scale());         // 4
System.out.println(number.precision());     // 6
```

In division, **scale and precision are two different kinds of constraints**. A requirement to “keep two decimal places” typically needs `scale = 2`; whereas a requirement to “keep three significant digits” typically needs `MathContext(3, mode)`.

`BigDecimal` is **immutable**: `divide` returns a new value without modifying the dividend or divisor.

## 2. Overview of Important Overloads

| Call form | Result rule | When to choose |
| --- | --- | --- |
| `a.divide(b)` | **Exact** quotient; non-terminating decimal expansions are rejected | When math guarantees the division has a terminating decimal form |
| `a.divide(b, scale, mode)` | Quotient with **specified scale**, rounded with mode if needed | Money, measurement units, values needing a fixed number of decimal places |
| `a.divide(b, mode)` | Quotient with **scale equal to `a.scale()`**, rounded if needed | When intentionally maintaining the dividend's scale |
| `a.divide(b, context)` | Rounded according to **precision** and `RoundingMode` of `MathContext` | Calculations with a budget of significant digits |

There are also legacy overloads taking `int roundingMode` / legacy constants; they should not be used in new code. The constants in `RoundingMode` provide a type-safe API and avoid magic numbers.

**Key takeaway:** `divide(b, RoundingMode.HALF_UP)` **does not implicitly choose scale = 2**. It uses **`a`'s scale**. If `a == BigDecimal.ONE`, its scale is 0, so `1/3` can become **`0`**. This is an especially dangerous bug when developers assume mode only decides the last digit without paying attention to scale.

## 3. When to Use `divide(divisor)` Instead of Rounding Overloads?

`divide(divisor)` requires an **exact decimal quotient**. For example, `BigDecimal.ONE.divide(new BigDecimal("8"))` returns `0.125`, while dividing by `3` throws `ArithmeticException` because the quotient has infinitely many digits. After reducing the fraction, the quotient terminates only when the denominator consists of prime factors 2 and 5; the mechanism and proof belong to the lesson *Exact divide and non-terminating repeating decimals*.

Here, what needs to be decided is the **output policy**: if business requirements demand exactness, accept the result or report an error; if rounding is allowed, explicitly specify scale or precision in the corresponding overload. The preferred scale of exact divide is `a.scale() - b.scale()`, though the actual scale may be larger to represent the entire quotient.

## 4. divide(divisor, scale, RoundingMode): Setting an Exact Scale

This is the direct choice if the result needs **N digits after the decimal point**:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);

BigDecimal rounded2 =
        one.divide(three, 2, RoundingMode.HALF_UP);
BigDecimal rounded5 =
        one.divide(three, 5, RoundingMode.HALF_UP);

System.out.println(rounded2); // 0.33
System.out.println(rounded5); // 0.33333
```

Each parameter:

- `divisor`: the divisor, must not be zero.
- `scale`: requested scale of the **quotient**, of type `int`; can be 0 or negative.
- `roundingMode`: how to choose a value with that scale if the exact quotient does not fit the representation.

Even when the quotient is **already terminating**, forcing a smaller scale can require rounding:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = BigDecimal.valueOf(8);

System.out.println(one.divide(eight, 2, RoundingMode.HALF_UP));   // 0.13
System.out.println(one.divide(eight, 2, RoundingMode.HALF_EVEN)); // 0.12
```

`1/8 = 0.125` is a midpoint when rounding to two digits after the decimal point. `HALF_UP` chooses 0.13; `HALF_EVEN` chooses 0.12 because the last digit is 2 (even).

### Scale 0 and Negative Scale

```java
System.out.println(
        BigDecimal.ONE.divide(BigDecimal.valueOf(3),
                0, RoundingMode.HALF_UP)); // 0

System.out.println(
        new BigDecimal("123").divide(BigDecimal.ONE,
                -1, RoundingMode.HALF_UP)); // 1.2E+2
```

Scale 0 produces a quotient in whole units; scale -1 produces a value in multiples of 10. `new BigDecimal("123") / 1` is exactly 123, but requesting scale -1 causes the result to be rounded to 120 and may be printed in scientific notation `1.2E+2`.

**Do not use `setScale` without thinking about rounding:** if you need to reduce scale and significant digits are lost, `setScale(newScale)` without a mode can throw `ArithmeticException`. A divide overload with a mode establishes the policy explicitly from the start.

## 5. divide(divisor, RoundingMode): Taking Scale from the Dividend

This is an easily misunderstood overload:

```java
BigDecimal a = new BigDecimal("1.00");
BigDecimal b = BigDecimal.valueOf(3);

System.out.println(a.divide(b, RoundingMode.HALF_UP)); // 0.33
```

`a.scale() == 2`, so the quotient is rounded to scale 2. But when `a` is created from `BigDecimal.ONE`:

```java
BigDecimal a = BigDecimal.ONE; // scale = 0
BigDecimal b = BigDecimal.valueOf(3);

System.out.println(a.divide(b, RoundingMode.HALF_UP)); // 0
```

Both calls use **the same mathematical division 1/3 and the same rounding mode**, yet differ in the dividend's scale. Hence they produce different results.

Another dangerous scenario:

```java
BigDecimal amount = new BigDecimal("100");   // scale 0
BigDecimal factor = new BigDecimal("3");
BigDecimal result = amount.divide(factor, RoundingMode.HALF_UP);
// result == 33, not 33.33
```

If the contract requires 2 digits after the decimal point, explicitly specify **`divide(factor, 2, RoundingMode.HALF_UP)`**. Do not use the 2-argument overload and rely on the input's scale happening to be 2.

## 6. divide(divisor, MathContext): Limiting Significant Digits

`MathContext` holds:

- `precision`: number of significant digits to keep (`0` denotes unlimited).
- `roundingMode`: rounding rule when precision is insufficient.

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);
BigDecimal result = one.divide(three, mc);

System.out.println(result); // 0.333
```

**Do not equate `precision = 3` with `scale = 3`**. Applying the same context to a large quotient:

```java
BigDecimal big = new BigDecimal("12345");
BigDecimal seven = BigDecimal.valueOf(7);
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

System.out.println(big.divide(seven, mc)); // 1.76E+3
```

The mathematical quotient is approximately 1763.571..., rounded to **three significant digits** as 1760, printed `1.76E+3`. The result's scale is **-1**, not 3.

Comparing the same problem with `scale = 2`:

```java
BigDecimal a = new BigDecimal("123.45");
BigDecimal b = BigDecimal.valueOf(2);

System.out.println(
        a.divide(b, 2, RoundingMode.HALF_UP)); // 61.73

System.out.println(
        a.divide(b, new MathContext(2, RoundingMode.HALF_UP))); // 62
```

`123.45/2 = 61.725`, so:

- **Scale 2** → 61.73 (two digits after the decimal point).
- **Precision 2** → 62 (two significant digits).

### MathContext.UNLIMITED and precision = 0

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = BigDecimal.valueOf(8);

System.out.println(
        one.divide(eight, MathContext.UNLIMITED)); // 0.125
```

`MathContext.UNLIMITED` sets precision to 0; for divide, it requests an **exact** quotient, similar to `divide(divisor)` in normal cases. It does **not** mean computing arbitrarily many digits of `1/3` without memory limits.

```java
// one.divide(BigDecimal.valueOf(3), MathContext.UNLIMITED);
// -> ArithmeticException, because 1/3 has a non-terminating decimal
```

If you set a finite precision with `RoundingMode.UNNECESSARY` and the quotient requires rounding, Java may also throw `ArithmeticException`. You must choose a mode that permits rounding when the problem calls for an approximation.

## 7. RoundingMode: Distinguishing Midpoints, Signs, and Rounding Directions

`RoundingMode` decides how to handle digits when truncation is forced; it does **not** decide at which step rounding should occur.

| Mode | Meaning | `+1/8` at scale 2 | `-1/8` at scale 2 |
| --- | --- | --- | --- |
| `UP` | Away from zero if any part is discarded | `0.13` | `-0.13` |
| `DOWN` | Toward zero | `0.12` | `-0.12` |
| `CEILING` | Toward positive infinity | `0.13` | `-0.12` |
| `FLOOR` | Toward negative infinity | `0.12` | `-0.13` |
| `HALF_UP` | At midpoint, away from zero | `0.13` | `-0.13` |
| `HALF_DOWN` | At midpoint, toward zero | `0.12` | `-0.12` |
| `HALF_EVEN` | At midpoint, choose even last digit | `0.12` | `-0.12` |
| `UNNECESSARY` | Lossy rounding disallowed | `ArithmeticException` | `ArithmeticException` |

Examples:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = BigDecimal.valueOf(8);

System.out.println(
        one.divide(eight, 2, RoundingMode.HALF_UP));   // 0.13
System.out.println(
        one.divide(eight, 2, RoundingMode.HALF_EVEN)); // 0.12
System.out.println(
        one.negate().divide(eight, 2, RoundingMode.HALF_UP)); // -0.13
```

Do not assume `HALF_UP` is right for every currency problem or `HALF_EVEN` is right for every statistical calculation. Follow the contract of your system, industry, or output format.

### When You Want to Prevent Silent Rounding

```java
try {
    BigDecimal exactTwoPlaces = BigDecimal.ONE.divide(
            BigDecimal.valueOf(3), 2, RoundingMode.UNNECESSARY);
} catch (ArithmeticException ex) {
    // 1/3 cannot be stored exactly at scale 2
}
```

`UNNECESSARY` is a tool to **detect when rounding is required**. It can also be appropriate when the contract requires rejecting a transaction rather than truncating data.

## 8. Dividing by 0: Unlike `double` Division

A `BigDecimal` has no special `NaN` or `Infinity` values. With `BigDecimal.divide`, a divisor equal to 0 causes **`ArithmeticException`**:

```java
BigDecimal a = BigDecimal.ONE;
BigDecimal zero = BigDecimal.ZERO;

// a.divide(zero, 2, RoundingMode.HALF_UP);
// -> ArithmeticException: Division by zero
```

Unlike primitive `double`:

```java
System.out.println(1.0 / 0.0); // Infinity
System.out.println(0.0 / 0.0); // NaN
```

Do not write code using `BigDecimal` expecting `divide` to return Infinity. In Java, there must be a **division-by-zero handling contract**, such as validating inputs upfront and providing a business error message.

```java
static BigDecimal safeDivide(BigDecimal a, BigDecimal b,
                             int scale, RoundingMode mode) {
    if (b.signum() == 0) {
        throw new IllegalArgumentException("Divisor must be nonzero");
    }
    return a.divide(b, scale, mode);
}
```

This is an illustrative helper that needs to be placed **inside a class**, not a standalone program. `signum() == 0` checks for zero by value, including `0.00` with nonzero scale. You can validate null via `Objects.requireNonNull` if inputs may be null.

**Do not catch all `ArithmeticException` instances and treat them as division by 0**. With exact divide overloads or `UNNECESSARY`, the exception can also occur because the quotient cannot be represented exactly at the requested precision/scale.

## 9. Exact Division Does Not Always Keep the Desired Scale

When dividing a value with trailing zeros, results from different overloads can differ in **scale** even though their **mathematical values are equal**:

```java
BigDecimal a = new BigDecimal("2.000");
BigDecimal b = new BigDecimal("4");

BigDecimal exact = a.divide(b);                    // 0.500
BigDecimal sameScale = a.divide(b, RoundingMode.HALF_UP); // 0.500
BigDecimal scale2 = a.divide(b, 2, RoundingMode.HALF_UP); // 0.50
```

One issue is that `BigDecimal.equals` compares **value and scale**, whereas `compareTo` only compares **numeric value**:

```java
System.out.println(new BigDecimal("0.50")
        .equals(new BigDecimal("0.500")));    // false
System.out.println(new BigDecimal("0.50")
        .compareTo(new BigDecimal("0.500"))); // 0
```

If using `HashSet<BigDecimal>` or `HashMap<BigDecimal, ...>`, different scales can turn into **two distinct keys**. You should not ignore scale after division, especially when the system uses decimals to represent measurement units, ratios, or rounding rules.

A consistent approach for data settled at scale 2 is to **specify scale 2 directly in the divide call**, rather than relying on `a`'s incidental scale.

## 10. Choosing Working Precision and Result Settlement Timing

A multi-step algorithm often requires a **working precision** higher than the recorded data precision. Examples include splitting into thirds, accumulating sums, multiplying rates, or allocating costs.

Do not automatically round to two decimal places after every operation simply because the final target has two digits. Results can depend on where you round.

Suppose two exact components are both `0.015`:

```text
Round each component with HALF_UP at scale 2:
0.015 -> 0.02
0.015 -> 0.02
Total = 0.04

Sum then round the total:
0.015 + 0.015 = 0.030
0.030 -> 0.03
Total = 0.03
```

**Both can be correct under different contracts**:

- If each component is an independent transaction line that must be settled to two digits, the correct total may be 0.04.
- If the inputs are intermediate components of a single amount to be settled once, the result may be 0.03.

In a BigDecimal pipeline, you should determine upfront: whether inputs are exact or approximate decimals; whether rounding happens at unit price, line item, or total; what scale to keep; rounding mode; how to handle remainders; and how to store settled values.

### MathContext Precision Does Not Replace a Scale Contract

```java
MathContext working = new MathContext(12, RoundingMode.HALF_EVEN);
BigDecimal approximateRatio =
        BigDecimal.ONE.divide(BigDecimal.valueOf(7), working);
// Has 12 significant digits; result does not default to scale 2.

BigDecimal committed =
        approximateRatio.setScale(2, RoundingMode.HALF_UP);
// Must be an explicit decision that this is the settlement step at scale 2.
```

Do not assume `MathContext` can “make every division exact”: it is an **approximation with limited significant digits** when the decimal quotient is non-terminating. When you must preserve the original fraction exactly, a numerator/denominator pair or a dedicated rational type may be more suitable than forcing every result into a finite BigDecimal.

## 11. Related APIs to Know Without Confusing Them with Rounded Divide

`BigDecimal` also provides:

- `divideToIntegralValue(divisor)`: returns the integer part of the quotient rounded toward 0, represented as a BigDecimal.
- `remainder(divisor)`: returns the remainder according to BigDecimal rules; not the primitive `%` operator applied to objects.
- `divideAndRemainder(divisor)`: obtains both the integral quotient and the remainder simultaneously.

For example:

```java
BigDecimal ten = new BigDecimal("10");
BigDecimal three = new BigDecimal("3");

System.out.println(ten.divideToIntegralValue(three)); // 3
System.out.println(ten.remainder(three));             // 1
```

**Do not carelessly use `divideToIntegralValue` in place of `divide(..., 0, mode)`**: the former truncates toward 0, whereas divide with scale 0 can round according to a mode such as `HALF_UP` or `CEILING`.

If the goal is displaying two digits, using `String.format("%.2f", someDouble)` is also **not equivalent** to exact BigDecimal division followed by settlement under the business `RoundingMode`. String formatting is merely a text presentation step and may carry the limitations of the input type.

## 12. Standalone Runnable Java 17+ Program

Create file **`BigDecimalDivideDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalDivideDemo {
    static void showError(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=NOT_THROWN");
        } catch (ArithmeticException ex) {
            System.out.println(label + "=ArithmeticException");
        }
    }

    public static void main(String[] args) {
        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = BigDecimal.valueOf(3);
        BigDecimal eight = BigDecimal.valueOf(8);

        System.out.println("exactOneOverEight=" + one.divide(eight));
        showError("exactOneOverThree", () -> one.divide(three));
        System.out.println("scaleTwo=" +
                one.divide(three, 2, RoundingMode.HALF_UP));
        System.out.println("scaleFive=" +
                one.divide(three, 5, RoundingMode.HALF_UP));
        System.out.println("scaleZero=" +
                one.divide(three, 0, RoundingMode.HALF_UP));
        System.out.println("scaleMinusOne=" +
                new BigDecimal("123").divide(
                        BigDecimal.ONE, -1, RoundingMode.HALF_UP));

        System.out.println("implicitScaleZero=" +
                one.divide(three, RoundingMode.HALF_UP));
        System.out.println("implicitScaleTwo=" +
                new BigDecimal("1.00").divide(
                        three, RoundingMode.HALF_UP));
        System.out.println("sameScaleResult=" +
                new BigDecimal("2.000").divide(
                        new BigDecimal("4"), RoundingMode.HALF_EVEN));

        MathContext mc3 = new MathContext(3, RoundingMode.HALF_UP);
        System.out.println("contextThree=" + one.divide(three, mc3));
        System.out.println("contextBig=" +
                new BigDecimal("12345").divide(
                        new BigDecimal("7"), mc3));
        System.out.println("unlimitedExact=" +
                one.divide(eight, MathContext.UNLIMITED));
        showError("unlimitedRecurring",
                () -> one.divide(three, MathContext.UNLIMITED));

        BigDecimal a = new BigDecimal("123.45");
        BigDecimal two = BigDecimal.valueOf(2);
        System.out.println("scaleVersusPrecisionScale=" +
                a.divide(two, 2, RoundingMode.HALF_UP));
        System.out.println("scaleVersusPrecisionContext=" +
                a.divide(two, new MathContext(
                        2, RoundingMode.HALF_UP)));

        System.out.println("tieHalfUp=" +
                one.divide(eight, 2, RoundingMode.HALF_UP));
        System.out.println("tieHalfEven=" +
                one.divide(eight, 2, RoundingMode.HALF_EVEN));
        System.out.println("negativeHalfUp=" +
                one.negate().divide(
                        eight, 2, RoundingMode.HALF_UP));
        System.out.println("negativeHalfEven=" +
                one.negate().divide(
                        eight, 2, RoundingMode.HALF_EVEN));

        showError("unnecessaryRecurring",
                () -> one.divide(
                        three, 2, RoundingMode.UNNECESSARY));
        showError("divideByZero",
                () -> one.divide(
                        BigDecimal.ZERO, 2, RoundingMode.HALF_UP));

        BigDecimal exactWithScale = new BigDecimal("1.00")
                .divide(new BigDecimal("8.0"));
        System.out.println("exactPreferredScaleValue=" +
                exactWithScale.toPlainString());
        System.out.println("exactPreferredScaleActual=" +
                exactWithScale.scale());

        BigDecimal forty = new BigDecimal("40");
        System.out.println("terminatingThreeOverForty=" +
                new BigDecimal("3").divide(forty));

        BigDecimal small = new BigDecimal("0.015");
        BigDecimal settledEach =
                small.setScale(2, RoundingMode.HALF_UP);
        System.out.println("roundedEachThenSum=" +
                settledEach.add(settledEach));
        System.out.println("sumThenRound=" +
                small.add(small).setScale(
                        2, RoundingMode.HALF_UP));

        System.out.println("divideIntegral=" +
                BigDecimal.TEN.divideToIntegralValue(three));
        System.out.println("remainder=" +
                BigDecimal.TEN.remainder(three));

        System.out.println("primitiveDoubleZero=" + (1.0 / 0.0));
        System.out.println("oneUnchanged=" + one);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac BigDecimalDivideDemo.java
java BigDecimalDivideDemo
```

**Expected stdout:**

```text
exactOneOverEight=0.125
exactOneOverThree=ArithmeticException
scaleTwo=0.33
scaleFive=0.33333
scaleZero=0
scaleMinusOne=1.2E+2
implicitScaleZero=0
implicitScaleTwo=0.33
sameScaleResult=0.500
contextThree=0.333
contextBig=1.76E+3
unlimitedExact=0.125
unlimitedRecurring=ArithmeticException
scaleVersusPrecisionScale=61.73
scaleVersusPrecisionContext=62
tieHalfUp=0.13
tieHalfEven=0.12
negativeHalfUp=-0.13
negativeHalfEven=-0.12
unnecessaryRecurring=ArithmeticException
divideByZero=ArithmeticException
exactPreferredScaleValue=0.125
exactPreferredScaleActual=3
terminatingThreeOverForty=0.075
roundedEachThenSum=0.04
sumThenRound=0.03
divideIntegral=3
remainder=1
primitiveDoubleZero=Infinity
oneUnchanged=1
```

The output shows:

- `exactOneOverEight` succeeds while `exactOneOverThree` throws an exception.
- `implicitScaleZero=0` and `implicitScaleTwo=0.33` come from **different dividend scales**, even though both are 1/3.
- `scaleVersusPrecisionScale=61.73` differs from `scaleVersusPrecisionContext=62` because one limits **scale** while the other limits **significant digits**.
- `tieHalfUp=0.13` and `tieHalfEven=0.12` demonstrate midpoint rounding policies.
- `exactPreferredScaleActual=3` proves exact quotient scale can be **larger than the preferred scale**.
- `roundedEachThenSum=0.04` differs from `sumThenRound=0.03` due to **settlement timing** rather than a BigDecimal bug.

## 13. Common Mistakes and How to Avoid Them

| Misconception or practice | Reality |
| --- | --- |
| “`divide(b)` always picks a reasonable number of digits automatically.” | No: non-terminating decimals cause `ArithmeticException`. |
| “`divide(b, HALF_UP)` defaults to rounding to two decimal places.” | No: it keeps the dividend's scale. |
| “`scale = 2` and `MathContext(2)` are the same.” | No: one is two digits after the decimal point, the other is two significant digits. |
| “`MathContext.UNLIMITED` automatically represents infinite 1/3.” | No: non-terminating division still throws an exception. |
| “`RoundingMode.UNNECESSARY` is always safe for division.” | No: if rounding is required, `ArithmeticException` occurs. |
| “Every `ArithmeticException` from divide means division by 0.” | No: it can also mean a non-terminating decimal quotient or not fitting precision/scale. |
| “`BigDecimal.divide` returns Infinity like `double`.” | No: BigDecimal has no NaN/Infinity. |
| “RoundingMode.HALF_EVEN always differs from HALF_UP.” | It only differs at certain midpoints depending on the last digit; many inputs give the same result. |
| “Exact division guarantees the result has the preferred scale.” | Preferred scale is only a preference; an exact result may need a larger scale. |
| “Results compare `equals` when numerically equal.” | `equals` also compares scale; `compareTo` compares numeric value only. |
| “Using BigDecimal created from `new BigDecimal(0.1)` fixes source errors.” | No: that is the exact representation of the binary `double` approximation. |
| “You can safely round after every step.” | Information can be lost; the contract dictates when settlement is needed. |

Checklist before each `divide`:

1. **Is the divisor nonzero?** Check `divisor.signum() != 0`, including representations like `0.00`.
2. **Could the quotient have a non-terminating decimal?** If yes, choose scale/precision and a mode permitting rounding, or reject the operation.
3. **Does the target require a fixed scale or significant digits?** Choose `divide(b, scale, mode)` or `divide(b, MathContext)` accordingly.
4. **Do you truly want to keep the dividend's scale?** Only if that is the case, choose `divide(b, mode)`.
5. **Which RoundingMode is specified by the contract?** Verify behavior at midpoints, negative numbers, independent transactions, and exact quotients that do not fit the width.
6. **Are internal calculations and settlement separated?** Round only at meaningful boundaries, not arbitrarily at every step.
7. **How must the output be stored/compared?** Distinguish `compareTo` and `equals` because scales can differ.
8. **Is exception handling clear?** Separate division by zero, non-terminating decimals, and `UNNECESSARY` before reporting the appropriate error.
9. **Could the result become too large or resource-intensive?** Set precision, scale, and input length limits per application policy.
10. **Have negative numbers, zero, midpoints, and negative scales been tested?** These cases usually catch bugs earliest.

**Conclusion:** `BigDecimal.divide` has multiple overloads because no single rounding policy fits every situation. `divide(divisor)` demands **exactness**; `divide(divisor, scale, mode)` chooses a **specific scale**; `divide(divisor, mode)` takes the **dividend's scale**; and `divide(divisor, MathContext)` limits **significant digits**. Choose an overload based on data requirements and the rounding contract, not on a hunch that a mode or digit count “looks like enough”.

API documentation: [Oracle Java 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html), and [MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html).