# MathContext in Java: precision and RoundingMode

## 1. The Problem MathContext Solves

When performing calculations with `BigDecimal`, there are two independent questions:

- **How many significant digits should be kept?** For example, the result of the division `1 / 3` cannot be fully represented by a finite decimal number, so a precision level must be decided.
- **If digits must be discarded, which rule should be used for rounding?** For `2.5`, it can be rounded to `2` or `3`, depending on the rule.

`java.math.MathContext` encapsulates both decisions into an immutable object:

```java
MathContext context = new MathContext(5, RoundingMode.HALF_EVEN);
```

Here, `precision = 5` is **the maximum of five significant digits of the result**; `RoundingMode.HALF_EVEN` decides how the discarded digits are handled. `MathContext` is passed into `BigDecimal` operations or the `round` method to limit the precision of the result. `MathContext` does not describe the number of digits after the decimal point and is not automatically applied to every operation.

Examples:

| Original number | `MathContext(3, HALF_UP)` | Explanation |
|---|---|---|
| `12345.67` | `1.23E+4` (value `12300`) | Keep three significant digits: 1, 2, 3; the next digit is 4 |
| `12.345` | `12.3` | Keep three digits 1, 2, 3; the next digit is 4 |
| `0.0012345` | `0.00123` | Leading zeros before 1 do not occupy significant digits |
| `9.999` | `10.0` | Rounding carries into a higher place, yet still has three significant digits |

To understand the results correctly, it is necessary to distinguish **value**, **precision**, and **scale**.

## 2. How Does BigDecimal's Precision Differ from Scale?

`BigDecimal` describes a decimal number through an *unscaled value* and a *scale*: mathematically,

```text
value = unscaledValue × 10^(-scale)
```

- `BigDecimal.precision()`: the number of digits in the unscaled value (*unscaled value*), excluding the negative sign; trailing zeros in the representation may still be counted.
- `BigDecimal.scale()`: the number of digits shifted to the right of the decimal point according to the object's representation; scale can be 0 or negative.
- `MathContext.getPrecision()`: the **maximum** number of significant digits used when an operation with a context produces a result; this is not a fixed property of every `BigDecimal` involved.

| Value created from string | `precision()` | `scale()` | Meaning |
|---|---:|---:|---|
| `"123.4500"` | 7 | 4 | Four digits after the decimal point, including two trailing zeros |
| `"0.00123"` | 3 | 5 | Three significant digits, five digits after the decimal point |
| `"100.00"` | 5 | 2 | The representation still keeps two trailing zeros |
| `"1E+3"` | 1 | -3 | Value equals `1000`, negative scale |

Example of two completely different operations:

```java
BigDecimal x = new BigDecimal("12.345");

BigDecimal byPrecision = x.round(
    new MathContext(4, RoundingMode.HALF_UP)
); // 12.35: at most 4 significant digits

BigDecimal byScale = x.setScale(4, RoundingMode.HALF_UP);
// 12.3450: exactly 4 digits after the decimal point
```

**Selection rule:** use `MathContext` to control significant digits in operations; use `setScale` to control the number of decimal places of output or units of measurement/currency. A single problem may need both, at different steps.

## 3. Creating a MathContext and Choosing Precision

```java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext a = new MathContext(6);
// precision = 6, default mode is HALF_UP

MathContext b = new MathContext(6, RoundingMode.HALF_EVEN);
// precision = 6, mode HALF_EVEN

int digits = b.getPrecision();               // 6
RoundingMode mode = b.getRoundingMode();     // HALF_EVEN

MathContext unlimited = MathContext.UNLIMITED;
```

`MathContext` is immutable: there is no operation to change `precision` or `roundingMode` in place. The same context can be reused across multiple operations. A negative precision is invalid; a precision of `0` means **unlimited significant digits**.

Java provides several predefined contexts:

| Constant | Precision | RoundingMode |
|---|---:|---|
| `MathContext.UNLIMITED` | 0 | `HALF_UP` (usually not used because there is no precision-based rounding) |
| `MathContext.DECIMAL32` | 7 | `HALF_EVEN` |
| `MathContext.DECIMAL64` | 16 | `HALF_EVEN` |
| `MathContext.DECIMAL128` | 34 | `HALF_EVEN` |

The names `DECIMAL32/64/128` suggest the IEEE 754 decimal formats, but choosing a constant does not mean `BigDecimal` turns into a binary floating-point type like `float`/`double`. The context only specifies precision and rounding for the operations to which it is applied.

**Note on `UNLIMITED`:** "unlimited precision" does not mean "every division succeeds". `1 / 8` has a finite decimal representation, whereas `1 / 3` has an infinite expansion; `BigDecimal.divide(divisor)` or `divide(divisor, MathContext.UNLIMITED)` will throw `ArithmeticException` for a division that cannot be represented with exact finite digits. The rounding mode in `UNLIMITED` does not solve this issue.

## 4. RoundingModes and Their Meaning with Negative Numbers

The modes belong to the `java.math.RoundingMode` enum, independent of `MathContext` and also usable with `setScale` and `divide`.

| Mode | Rule | `2.5` → integer | `-2.5` → integer |
|---|---|---:|---:|
| `UP` | Discard remainder **away from 0** | `3` | `-3` |
| `DOWN` | Discard remainder **toward 0** | `2` | `-2` |
| `CEILING` | Toward **+∞** | `3` | `-2` |
| `FLOOR` | Toward **−∞** | `2` | `-3` |
| `HALF_UP` | Nearest; if equidistant, **away from 0** | `3` | `-3` |
| `HALF_DOWN` | Nearest; if equidistant, **toward 0** | `2` | `-2` |
| `HALF_EVEN` | Nearest; if equidistant, the last retained digit is **even** | `2` | `-2` |
| `UNNECESSARY` | Forbids inexact rounding; throws if forced to drop a non-zero digit | error | error |

In the table, "→ integer" is equivalent to `new BigDecimal("2.5").setScale(0, mode)` and the analogous calculation with negative numbers.

With the three `HALF_*` modes, most values that do not lie exactly at the midpoint give the same nearest result. The clearest difference lies in *tie* cases:

```text
2.5 → HALF_UP: 3     HALF_DOWN: 2     HALF_EVEN: 2
3.5 → HALF_UP: 4     HALF_DOWN: 3     HALF_EVEN: 4
2.25 (1 digit after decimal point) → HALF_EVEN: 2.2
2.35 (1 digit after decimal point) → HALF_EVEN: 2.4
```

With `HALF_EVEN`, "even" refers to **the last remaining digit**, not checking whether the entire rounded number is an even integer. It helps reduce accumulated bias when there are many symmetric roundings, but it is not a mandatory rule for every business case. `HALF_UP` is also not "always round up": `2.41` rounded to an integer is still `2`.

`UP` differs from `CEILING` on negative numbers; `DOWN` differs from `FLOOR` on negative numbers. Do not infer a mode from its English name alone while ignoring direction on the number line.

## 5. Where Does MathContext Apply in BigDecimal?

Typical usages:

```java
MathContext mc = new MathContext(4, RoundingMode.HALF_EVEN);

BigDecimal value = new BigDecimal("123.456");
BigDecimal rounded = value.round(mc);

BigDecimal sum = value.add(new BigDecimal("7.89"), mc);
BigDecimal difference = value.subtract(new BigDecimal("7.89"), mc);
BigDecimal product = value.multiply(new BigDecimal("7.89"), mc);
BigDecimal quotient = value.divide(new BigDecimal("7.89"), mc);

BigDecimal constructed = new BigDecimal("123.456", mc);
```

These methods return a new `BigDecimal`; `BigDecimal` is immutable. If you want to keep the result, you must assign it to a variable, for example `value = value.round(mc)`; calling `value.round(mc);` alone will not modify `value`.

In particular, **a context does not automatically propagate**. For example:

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal a = new BigDecimal("10.1234");
BigDecimal b = new BigDecimal("1.2345");

BigDecimal exactSum = a.add(b);       // 11.3579
BigDecimal roundedSum = a.add(b, mc); // 11.4
```

Creating `a`, `b`, or calling an operation with `mc` does not create a "global precision" for subsequent operations. You must pass the context explicitly at the steps where you want to limit digits.

### Division: a Special Error-Prone Case

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");
BigDecimal eight = new BigDecimal("8");

BigDecimal exact = one.divide(eight); // 0.125
BigDecimal approximate = one.divide(
    three, new MathContext(4, RoundingMode.HALF_UP)
); // 0.3333

// one.divide(three) throws ArithmeticException because 1/3 is non-terminating.
```

There are two common APIs, serving two different needs:

- `a.divide(b, mc)` requests a result by **number of significant digits** (`mc.precision`).
- `a.divide(b, scale, roundingMode)` requests a result by **number of digits after the decimal point** (`scale`).

For example `1 / 3`: precision 4 gives `0.3333`; scale 2 gives `0.33`. However, for `12345 / 7`, precision 2 and scale 2 produce results with very different levels of detail.

Even when passing a context, `RoundingMode.UNNECESSARY` can still cause a calculation to throw `ArithmeticException` if the exact result requires more digits than the precision allows.

## 6. Complete, Runnable Java 17+ Example

Create the file `MathContextDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class MathContextDemo {
    public static void main(String[] args) {
        MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

        BigDecimal amount = new BigDecimal("12345.67");
        BigDecimal rounded = amount.round(mc);
        BigDecimal third = BigDecimal.ONE.divide(new BigDecimal("3"), mc);
        BigDecimal exact = BigDecimal.ONE.divide(new BigDecimal("8"));
        BigDecimal scaled = new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN);

        System.out.println("precision=" + mc.getPrecision()
                + ", rounding=" + mc.getRoundingMode());
        System.out.println("rounded=" + rounded.toPlainString());
        System.out.println("1/3=" + third.toPlainString());
        System.out.println("1/8=" + exact.toPlainString());
        System.out.println("scale=" + scaled.toPlainString());

        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException ex) {
            System.out.println("1/3 exact: ArithmeticException");
        }
    }
}
```

Compile and run:

```bash
javac MathContextDemo.java
java MathContextDemo
```

Exact output:

```text
precision=3, rounding=HALF_UP
rounded=12300
1/3=0.333
1/8=0.125
scale=2.34
1/3 exact: ArithmeticException
```

Explanation: `amount` is reduced to three significant digits so it has the value `12300`; `toPlainString()` displays the plain form instead of the exponential notation that may appear in `toString()`. `1/3` is approximated under the context; `1/8` can be represented exactly. `2.345` rounded with `HALF_EVEN` to two digits after the decimal point becomes `2.34` because the hundredths digit being kept is 4 (even). Finally, the division `1/3` without a context throws an exception as caught.

## 7. Rounding Order Affects the Result

Using a context early loses digits before subsequent steps. In a long calculation chain, this can produce **double rounding** and accumulated error.

```java
BigDecimal x = new BigDecimal("1.249");
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

BigDecimal viaTwoSteps = x.round(mc)
        .setScale(1, RoundingMode.HALF_UP); // 1.3

BigDecimal direct = x.setScale(1, RoundingMode.HALF_UP); // 1.2
```

Why? The first step turns `1.249` → `1.25`; the second step hits an exact midpoint so `1.25` → `1.3`. Meanwhile, rounding `1.249` directly to one digit after the decimal point gives `1.2`.

When a problem needs to aggregate multiple items, determine **when rounding occurs** according to the specification. If rounding every operation is not mandatory, it is usually better to maintain enough digits in intermediate steps and then perform rounding once at the specified point. When an approximation is needed for non-terminating division, choose a sufficiently large precision (possibly adding *guard digits*) and evaluate the error, rather than defaulting to a very low context for every step.

There is no single `MathContext` that is right for every data domain. Financial precision, measurement, statistics, trading, and tax rounding can each have different rules.

## 8. Business Example: Rounding Monetary Amount at the Final Calculation Step

Suppose an illustrative problem requires tax to be rounded to two decimal places using `HALF_UP` (this is only a hypothetical rule for the example, not a statement of actual tax regulations):

```java
BigDecimal subtotal = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.0825");

BigDecimal tax = subtotal.multiply(rate)
        .setScale(2, RoundingMode.HALF_UP);
BigDecimal total = subtotal.add(tax);

System.out.println("tax=" + tax.toPlainString());     // tax=1.65
System.out.println("total=" + total.toPlainString()); // total=21.64
```

`19.99 × 0.0825 = 1.649175` exactly before becoming `1.65`. If business logic requires rounding amounts per line item before summing, the result may differ from rounding after summing the entire invoice. This rule must be defined at the business level; `MathContext` does not choose it automatically.

When division produces a ratio or unit price that needs approximation, you can define a context for the intermediate step:

```java
MathContext working = new MathContext(16, RoundingMode.HALF_EVEN);

BigDecimal totalAmount = new BigDecimal("100.00");
BigDecimal units = new BigDecimal("3");
BigDecimal approximateUnitPrice = totalAmount.divide(units, working);

BigDecimal displayPrice = approximateUnitPrice
        .setScale(2, RoundingMode.HALF_UP);
// approximateUnitPrice ~= 33.33333333333333; displayPrice = 33.33
```

In a real system, intermediate precision must be chosen based on input magnitude, number of operations, and error requirements. Precision 16 here is only an example.

## 9. Initializing BigDecimal Properly so Precision Is Meaningful

`BigDecimal` can accurately store decimal digits entered as strings. Avoid passing a `double` literal directly into the constructor when you want a human-written decimal number:

```java
BigDecimal recommended = new BigDecimal("0.1");
BigDecimal alternative = BigDecimal.valueOf(0.1);
BigDecimal surprising = new BigDecimal(0.1);
```

`recommended` and `alternative` have the decimal value `0.1`. The object `surprising` holds the **exact converted value of the binary `double`**, which is not exactly equal to `0.1`; rounding it with `MathContext` may hide the source of error, but does not remove its cause. For monetary data or measurement data requiring controlled decimal representation, prefer string inputs or parsing decimal strings with a clear contract.

Display also needs consideration: `toString()` may use scientific notation; `toPlainString()` does not use scientific notation; `setScale(2, ...)` guarantees exactly two decimal places in the numeric representation used for display. Output requirements should not be inferred from `MathContext.precision` alone.

## 10. Common Mistakes and How to Verify

| Mistake | Consequence | Correct approach |
|---|---|---|
| Interpreting `precision = 2` as two digits after the decimal point | `123.45` can become `1.2E+2` | Use `setScale(2, mode)` when two decimal places are needed |
| Dividing `1 / 3` without rounding | `ArithmeticException` | Use `divide` with an appropriate context or scale and rounding |
| Thinking `UNLIMITED` can divide any numbers | Non-terminating decimal division still errors | Determine allowed error and set a finite context |
| Using `HALF_UP` when business rules require `HALF_EVEN` | Different results on ties | Put the mode in the specification and tests |
| Confusing `UP` with `CEILING`, `DOWN` with `FLOOR` | Wrong rounding with negative numbers | Test both positive and negative numbers |
| Calling `x.round(mc)` without assigning the result | `x` keeps its old value | Assign `x = x.round(mc)` if needed |
| Applying too low a context on every operation | Drift across steps, double rounding | Define rounding points; keep intermediate precision large enough |
| Creating numbers with `new BigDecimal(0.1)` | Carries binary representation error | Use `"0.1"` or `BigDecimal.valueOf(0.1)` |
| Using `equals` to compare decimal values with different scales | `1.0` differs from `1.00` with `equals` | Use `compareTo(...) == 0` when only numeric value matters; use `equals` when scale also matters |
| Choosing rounding arbitrarily for money/tax | May violate business requirements | Explicitly state operation type, rounding step, scale, and rounding mode |

To detect unintended rounding in calculations that require absolute exactness, use `RoundingMode.UNNECESSARY` as a check:

```java
new BigDecimal("12.340").setScale(2, RoundingMode.UNNECESSARY);
// Succeeds: only removes a zero without changing the value.

new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY);
// Throws ArithmeticException because it must drop the non-zero digit 5.
```

When displaying or checking outputs in tests, prefer intentional comparisons: use `compareTo` for mathematical value, and also check `scale` or strings when formatting is part of the contract. `round(mc)` does not guarantee automatic scale normalization: a result that already meets precision may keep trailing zeros.

## 11. Self-Check Exercises

1. What value does `new BigDecimal("0.009876").round(new MathContext(2, HALF_UP))` get?
2. How do `new BigDecimal("-2.1").setScale(0, CEILING)` and the same operation with `FLOOR` differ?
3. Why is `new BigDecimal("100.00").precision()` equal to 5, while `new BigDecimal("1E+2").precision()` is equal to 1 even though they have the same value?
4. A report table needs exactly three digits after the decimal point: should you only use `MathContext(3)` or `setScale(3, mode)`?
5. The division `2 / 7` is required to have four significant digits: which `BigDecimal` call is appropriate?

Answers and reasoning:

1. `0.0099`: the two significant digits are 9 and 8; the next digit is 7 so 8 rounds up to 9.
2. `CEILING` gives `-2` (toward +∞), `FLOOR` gives `-3` (toward −∞).
3. `precision()` is based on the unscaled representation: `100.00` has five digits, `1E+2` has one; the same mathematical value does not force the same precision/scale.
4. Use `setScale(3, mode)`, because the goal is the decimal point position, not total significant digits.
5. For example `BigDecimal.valueOf(2).divide(BigDecimal.valueOf(7), new MathContext(4, RoundingMode.HALF_UP))`, resulting in `0.2857`.

**Takeaway:** `MathContext = (precision, RoundingMode)` controls **the number of significant digits and the rounding rule of the result of an operation using the context**. `setScale` controls **the decimal place position**. Choose the precision level, rounding mode, and timing of application according to the calculation's requirements; with `BigDecimal`, every operation must be called explicitly.
