# `BigDecimal.ulp()` in Java: Unit in the Last Place

## 1. What Is `ulp`?

`BigDecimal` represents decimal numbers with arbitrary precision, yet each object has a specific **scale**. When you need to know the value of one unit at the *last decimal place in the current representation*, use the method:

```java
public BigDecimal ulp()
```

**ULP** stands for *unit in the last place*. For `BigDecimal`, the result is a positive `BigDecimal` having the same `scale` as the receiver object. Its arithmetic value is always equal to:

\[
\operatorname{ulp}(x)=10^{-x.\operatorname{scale}()}
\]

For example, `123.45` has `scale = 2` so `ulp() = 0.01`; `123.4500` has `scale = 4` so `ulp() = 0.0001`. They are equal in **arithmetic value**, yet the last digit of the two representations sits at two different decimal places.

**Distinguish this from the start:** `ulp()` reports the unit at the last digit position **currently stored**. It does not measure calculation error on its own, does not round, and does not determine the accuracy required by business logic.

## 2. Why Does `scale` Determine `ulp`?

Every `BigDecimal` has the components:
- `unscaledValue()` is the integer part without a decimal point (type `BigInteger`).
- `scale()` is the integer describing the decimal point position.
- `precision()` is the number of digits of the unscaled integer part; the precision of 0 is 1.

Representation formula:

\[
x = \operatorname{unscaledValue}(x) \times 10^{-\operatorname{scale}(x)}
\]

For example, `new BigDecimal("123.4500")` has unscaled value `1234500`, `scale = 4`, `precision = 7`. If you increment the unscaled part from 1234500 to 1234501 while keeping scale fixed, the value increases by 0.0001, which equals `ulp()`.

Do not confuse **scale** (decimal point position) with **precision** (number of significant digits of the unscaled part). `ulp()` depends on **scale**, not directly on precision:

| String constructing `BigDecimal` | `scale()` | `precision()` | `ulp()` |
| --- | ---: | ---: | ---: |
| `"123.45"` | 2 | 5 | `0.01` |
| `"123.4500"` | 4 | 7 | `0.0001` |
| `"1"` | 0 | 1 | `1` |
| `"0.00"` | 2 | 1 | `0.01` |
| `"-7.20"` | 2 | 3 | `0.01` |
| `"6E+2"` | -2 | 1 | `1E+2` |

Scale can be **negative**: `6E+2` represents 600 with unscaled part 6, `scale = -2`, so ulp equals 100. Thus, `ulp()` is not necessarily less than 1.

## 3. Java-Specified Behavior

- The method returns **`BigDecimal`**, not `double`, and the result is always positive.
- The result keeps the **exact same scale** as the receiver value. Its value is equivalent to `BigDecimal.valueOf(1L, x.scale())` in both arithmetic value and scale.
- For zero, ulp is still 1 at that zero's own scale; there is no exception where `ulp() = 0`.
- `ulp()` **does not accept `MathContext`**, does not modify the original value, and is not a rounding operation. `BigDecimal` is immutable.

The zeros below are arithmetically equal yet return different results:

```java
new BigDecimal("0").ulp();      // 1, scale = 0
new BigDecimal("0.00").ulp();   // 0.01, scale = 2
new BigDecimal("0E+2").ulp();   // 1E+2, scale = -2
```

Java specifies the ulp of a nonzero value as the unit in the last digit of its representation and the ulp of zero as one unit with the same scale. Do not interpret `ulp()` as the absolute gap between two nearest `BigDecimal` numbers: `BigDecimal` is not bound to a fixed binary floating-point format.

## 4. Complete Java 17 Program

Save file **`BigDecimalUlpDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalUlpDemo {
    public static void main(String[] args) {
        show("A", new BigDecimal("123.45"));
        show("B", new BigDecimal("123.4500"));
        show("C", new BigDecimal("-7.20"));
        show("D", new BigDecimal("0.00"));
        show("E", new BigDecimal("6E+2"));

        BigDecimal rounded = new BigDecimal("123.456")
                .round(new MathContext(4, RoundingMode.HALF_UP));
        show("Rounded", rounded);

        BigDecimal original = new BigDecimal("100.00");
        show("Original", original);
        show("Normalized", original.stripTrailingZeros());
    }

    private static void show(String label, BigDecimal number) {
        BigDecimal unit = number.ulp();
        System.out.println(label + ": value=" + number
                + ", scale=" + number.scale()
                + ", ulp=" + unit
                + ", ulpScale=" + unit.scale());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac BigDecimalUlpDemo.java
java BigDecimalUlpDemo
```

**Exact output** (program compiled with `javac --release 17` and verified by running):

```text
A: value=123.45, scale=2, ulp=0.01, ulpScale=2
B: value=123.4500, scale=4, ulp=0.0001, ulpScale=4
C: value=-7.20, scale=2, ulp=0.01, ulpScale=2
D: value=0.00, scale=2, ulp=0.01, ulpScale=2
E: value=6E+2, scale=-2, ulp=1E+2, ulpScale=-2
Rounded: value=123.5, scale=1, ulp=0.1, ulpScale=1
Original: value=100.00, scale=2, ulp=0.01, ulpScale=2
Normalized: value=1E+2, scale=-2, ulp=1E+2, ulpScale=-2
```

Output explanation:
1. `A` and `B` have the same value 123.45, yet `B` has two extra fractional zeros so its ulp is 100 times smaller.
2. `C` is negative yet its ulp is positive. The sign of the number does not determine ulp.
3. `D` is zero, still carrying scale 2 and ulp 0.01.
4. `E` has negative scale so ulp is 100 (printed in scientific notation `1E+2`).
5. `Rounded` uses 4 significant digits, rounding to 123.5, scale 1, ulp 0.1.
6. `Normalized` strips trailing zeros from 100.00, replacing scale 2 with -2; the value remains 100 while ulp changes from 0.01 to 100.

## 5. Relationship with Rounding and Representation Changes

### 5.1. `setScale` Can Change Both `ulp` and Value

`setScale(newScale, roundingMode)` returns a representation with the requested scale. When decreasing scale, if significant digits must be discarded, `RoundingMode` determines how to round:

```java
BigDecimal original = new BigDecimal("1.236");
BigDecimal rounded = original.setScale(2, RoundingMode.HALF_UP);
// original = 1.236; original.ulp() = 0.001
// rounded  = 1.24;  rounded.ulp()  = 0.01
```

ULP increases from 0.001 to 0.01 because scale decreased. The **actual error** of the rounding is `|1.24 - 1.236| = 0.004`, not 0.01. To measure error, compare against the exact reference value (if available).

Increasing scale also changes ulp **even without changing arithmetic value**:

```java
BigDecimal x = new BigDecimal("2.5");
BigDecimal y = x.setScale(3);
// x = 2.5   -> ulp = 0.1
// y = 2.500 -> ulp = 0.001
// x.compareTo(y) == 0
```

### 5.2. `MathContext`: Precision Is Not Scale

`MathContext(4, RoundingMode.HALF_UP)` requests at most 4 significant digits when performing an operation with the context. It does not promise that every result's ulp will be 0.0001. Consider the following example (illustrative snippet placed inside a runnable Java method with `java.math.*` or corresponding classes imported):

```java
BigDecimal a = new BigDecimal("123.456")
        .round(new MathContext(4, RoundingMode.HALF_UP));
// a = 123.5; scale = 1; ulp = 0.1

BigDecimal b = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        new MathContext(4, RoundingMode.HALF_UP));
// b = 0.3333; scale = 4; ulp = 0.0001
```

Same precision 4 yet different ulps because the **actual scales** of the results differ. A `MathContext` only applies to the operation you pass it to (or when calling `round(mc)`); it does not automatically alter all `BigDecimal` objects.

### 5.3. `stripTrailingZeros` Can Change `ulp` Dramatically

`stripTrailingZeros()` preserves arithmetic value while removing trailing zeros from the representation, sometimes creating a negative scale:

```java
BigDecimal x = new BigDecimal("100.00");
BigDecimal y = x.stripTrailingZeros();
// x.compareTo(y) == 0        // true: same arithmetic value
// x.equals(y)                // false: different scale
// x.ulp().equals(y.ulp())    // false: 0.01 differs from 1E+2
```

For zero, `stripTrailingZeros()` returns `BigDecimal.ZERO` at scale 0. Thus `new BigDecimal("0.000").ulp()` is 0.001, whereas the ulp of the normalized result is 1.

If the number of decimal digits carries business meaning (such as prices published to 2 decimal places), think carefully before calling `stripTrailingZeros()`.

## 6. Practical Applications

**Inspecting representation granularity:** `new BigDecimal("19.990").ulp()` returns 0.001, showing the last decimal place currently present in the object. It does not tell you what the smallest currency unit is.

**Monitoring data processing pipelines:** log `value`, `scale()`, and `ulp()` before/after `setScale()`, `round()`, or `stripTrailingZeros()` to detect which step alters granularity.

**Analyzing results from `MathContext` calculations:** `ulp()` helps show the last decimal place retained after the operation. However, when evaluating algorithm accuracy, you also need an error definition and reference values.

Example where business logic requires monetary amounts to have 2 decimal places:

```java
BigDecimal amount = new BigDecimal("19.995");
BigDecimal payable = amount.setScale(2, RoundingMode.HALF_UP);
// payable = 20.00; payable.ulp() = 0.01
```

`setScale(2, HALF_UP)` itself enforces the rounding rule; `ulp()` merely describes the resulting representation. ULP does not by itself define currency rules, comparison thresholds, or acceptable error tolerances.

## 7. Comparison with Related APIs

| API / concept | Function | Pitfall |
| --- | --- | --- |
| `x.ulp()` | Unit at the last digit according to `x`'s scale | Does not measure calculation error. |
| `x.scale()` | Decimal point position | Can be negative, 0, or positive. |
| `x.precision()` | Number of digits in the unscaled part | Not synonymous with digits after the decimal point. |
| `x.setScale(...)` | Sets scale, may round | Can change arithmetic value. |
| `x.round(mc)` | Rounds to significant digits | Result scale depends on magnitude. |
| `x.stripTrailingZeros()` | Removes excess zeros in representation | Can change scale/ulp even when arithmetic is unchanged. |
| `Math.ulp(double)` | Representation step of binary floating-point `double` | Different base and semantics from `BigDecimal.ulp()`. |

`Math.ulp(1.0)` for `double` is approximately `2.22e-16`, whereas `new BigDecimal("1.0").ulp()` equals `0.1`. Do not substitute the results of these two APIs directly for each other.

## 8. Common Mistakes

1. **Treating ulp as error:** `ulp() = 0.01` does not prove a calculation is off by 0.01 or at most 0.005. Compute error from the operations, rounding rules, and reference values.
2. **Assuming equal value implies equal ulp:** `1.0` and `1.000` have the same arithmetic value yet different scales. Check `scale()`.
3. **Using precision to infer ulp:** `precision = 4` can still yield ulp 0.1 or 0.0001. Check the scale of the result itself.
4. **Overlooking zero or negative scale:** `0.00` has ulp 0.01; `6E+2` has ulp 100.
5. **Calling `stripTrailingZeros` and expecting ulp to stay unchanged:** scale can shift from positive to negative. Do not strip zeros that have business significance.
6. **Initializing with `double` unexpectedly:** `new BigDecimal(0.1)` represents the exact binary value of `double 0.1`, not exact decimal 0.1, so scale/ulp can be surprising. When explicit decimal data is available, prefer `new BigDecimal("0.1")` or consider `BigDecimal.valueOf(0.1)`.
7. **Using ulp as a global epsilon for comparison:** scale can have zeros added or stripped without changing arithmetic. Tolerance thresholds must be specified by the problem.

## 9. Knowledge Self-Check

**Question 1.** What is `new BigDecimal("0.0000").ulp()`?  
**Answer:** 0.0001 because scale equals 4, even though the value is 0.

**Question 2.** Why does `new BigDecimal("5.00").ulp()` differ from `new BigDecimal("5").ulp()`?  
**Answer:** the first object has scale 2 so ulp is 0.01; the second has scale 0 so ulp is 1.

**Question 3.** `new BigDecimal("600.0").stripTrailingZeros()` can become `6E+2`. What are the ULP before and after?  
**Answer:** before is 0.1 (scale 1), after is `1E+2` (scale -2); the arithmetic value remains 600.

**Question 4.** Can you infer from `ulp() = 0.01` that a division's error is at most 0.005?  
**Answer:** no. ULP describes the position of the last digit, whereas error bounds depend on the algorithm and rounding rules.

## 10. Takeaways

- For every `BigDecimal x`, **`x.ulp()` has value `10^(-x.scale())` and the same scale as `x`**.
- Scale is a property of **representation**, so objects with the same arithmetic value can have different ulps.
- `ulp()` helps explain data and operation results. Controlling accuracy requires explicit rounding policies and error definitions.

Official documentation: [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) and [Java SE 17 — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html).