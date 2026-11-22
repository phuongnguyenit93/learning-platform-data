# `BigDecimal.add`, `subtract`, `multiply`, and Result Scale in Java

## 1. The Problem: Why Does the Number of Decimal Places Differ for the Same Operation?

In Java, `BigDecimal` represents a decimal number using a `BigInteger` **unscaled value** and an `int` **scale**. When adding, subtracting, or multiplying, Java both computes the **mathematical value** and determines the **scale of the result** according to the API contract.

For example:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.20");  // scale 2
BigDecimal b = new BigDecimal("3.004"); // scale 3

System.out.println(a.add(b));      // 4.204
System.out.println(a.subtract(b)); // -1.804
System.out.println(a.multiply(b)); // 3.60480
```

What is notable is:

- The sum `4.204` has **scale = 3**.
- The difference `-1.804` has **scale = 3**.
- The product `3.60480` has **scale = 5**.

For **exact operations without passing a `MathContext`**:

| Operation | Preferred scale of the result |
| --- | --- |
| `a.add(b)` | `max(a.scale(), b.scale())` |
| `a.subtract(b)` | `max(a.scale(), b.scale())` |
| `a.multiply(b)` | `a.scale() + b.scale()` |

For the three operations presented, this formula describes the *preferred scale* during exact computation according to the `BigDecimal` specification. When using a `MathContext` with a precision limit, rounding and result representation may **change the final scale**. In addition, scale has an `int` limit, so operations on extreme scales may require exception handling.

**The most important point:** scale is a **decimal representation** property, not the amount of “absolute accuracy” of a measurement. A result with many trailing zeros does not mean the source data has become more accurate physically or from a business standpoint.

## 2. Reviewing the `unscaled × 10^-scale` Model

A `BigDecimal` value is defined by:

\[
\text{value}=\text{unscaledValue}\times10^{-\text{scale}}.
\]

For example:

```java
BigDecimal x = new BigDecimal("12.340");

System.out.println(x.unscaledValue()); // 12340
System.out.println(x.scale());         // 3
System.out.println(x.precision());     // 5
```

The mathematical value is:

\[
12340\times 10^{-3}=12.340.
\]

`precision()` counts the digits of the unscaled value (when unscaled is 0, precision is 1). `scale()` determines the position of the decimal point. The two concepts are not interchangeable.

Some examples:

| String | Unscaled value | Scale | Precision | Numeric value |
| --- | ---: | ---: | ---: | --- |
| `"1.20"` | `120` | 2 | 3 | 1.2 |
| `"3.004"` | `3004` | 3 | 4 | 3.004 |
| `"0.10"` | `10` | 2 | 2 | 0.1 |
| `"0.2"` | `2` | 1 | 1 | 0.2 |
| `"1000"` | `1000` | 0 | 4 | 1000 |
| `"1E+3"` | `1` | -3 | 1 | 1000 |
| `"0.00"` | `0` | 2 | 1 | 0 |

`scale` can be negative. With `new BigDecimal("1E+3")`, unscaled is 1, scale is -3:

\[
1\times10^{-(-3)}=1000.
\]

Therefore, you cannot infer scale simply by “counting digits after the dot” for all string forms, especially when scientific notation is used or after `stripTrailingZeros()`.

### Immutability of `BigDecimal`

`BigDecimal` objects are **immutable**:

```java
BigDecimal balance = new BigDecimal("1.20");
balance.add(new BigDecimal("3.00")); // Result is not retained

System.out.println(balance); // 1.20
```

To update the variable:

```java
balance = balance.add(new BigDecimal("3.00"));
System.out.println(balance); // 4.20
```

The method returns a `BigDecimal` representing the result; it does not modify the original object. This holds for `add`, `subtract`, `multiply`, `setScale`, and other transformations as well.

## 3. `add`: Exact Addition and Taking the Larger Scale

Important signatures:

```java
BigDecimal add(BigDecimal augend)
BigDecimal add(BigDecimal augend, MathContext mc)
```

When **no `MathContext` is provided**, exact addition has the preferred scale:

\[
s_{\text{sum}}=\max(s_a,s_b).
\]

Reason: to add two decimal numbers with two different decimal point positions, both can be represented at the **same larger scale** (the same smaller unit), and then their unscaled values are added.

For example:

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("3.004");

BigDecimal sum = a.add(b);
System.out.println(sum);         // 4.204
System.out.println(sum.scale()); // 3
```

Breakdown:

\[
1.20=120\times10^{-2}=1200\times10^{-3}
\]

\[
3.004=3004\times10^{-3}.
\]

Because `max(2,3)=3`, the sum is:

\[
(1200+3004)\times10^{-3}
=4204\times10^{-3}
=4.204.
\]

### Trailing Zeros Are Preserved When Required by Scale

```java
BigDecimal left = new BigDecimal("0.10");
BigDecimal right = new BigDecimal("0.2");

BigDecimal sum = left.add(right);

System.out.println(sum);         // 0.30
System.out.println(sum.scale()); // 2
```

Mathematically `0.3 = 0.30`, but the `BigDecimal` from exact addition has scale 2 because the operand `"0.10"` has scale 2.

If you need the result displayed as `"0.30"` for a two-decimal-place format, scale 2 can be useful. However, this is an **arithmetic operation rule**, not proof that the original measurement was accurate to the hundredths place.

### Adding a Zero Does Not Necessarily Keep the Other Number's Scale

```java
BigDecimal x = new BigDecimal("12.3"); // scale 1
BigDecimal zero = new BigDecimal("0.000"); // scale 3

BigDecimal result = x.add(zero);
System.out.println(result);         // 12.300
System.out.println(result.scale()); // 3
```

Although the mathematical value does not change, the scale increases from 1 to 3. You should not assume “adding 0 always leaves the object/scale unchanged”; the rules of addition still apply.

## 4. `subtract`: Exact Subtraction Also Takes the Larger Scale

Main signatures:

```java
BigDecimal subtract(BigDecimal subtrahend)
BigDecimal subtract(BigDecimal subtrahend, MathContext mc)
```

Without passing a context:

\[
s_{\text{difference}}=\max(s_a,s_b).
\]

For example:

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("3.004");

BigDecimal difference = a.subtract(b);

System.out.println(difference);         // -1.804
System.out.println(difference.scale()); // 3
```

The mechanism is still aligning the unscaled values to the same scale:

\[
(1200-3004)\times10^{-3}=-1804\times10^{-3}=-1.804.
\]

### A Negative Result Does Not Make the Scale “Negative”

```java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.2");

BigDecimal result = a.subtract(b);
System.out.println(result);         // -0.10
System.out.println(result.scale()); // 2
```

**The negative sign of the value** and **the sign of the scale** are two different things. The result `-0.10` is a negative number with a **positive** scale of 2.

### When Subtraction Produces Zero

```java
BigDecimal a = new BigDecimal("2.00");
BigDecimal b = new BigDecimal("-2.00");

BigDecimal sum = a.add(b);
System.out.println(sum);         // 0.00
System.out.println(sum.scale()); // 2
```

Similarly with `new BigDecimal("2.00").subtract(new BigDecimal("2.00"))`, the exact result has value zero and scale 2.

`BigDecimal` does not have two distinct signed zero values (positive/negative zero) like `double`. However, two zeros with different scales still differ under `equals`, even though `compareTo` considers them numerically equal.

## 5. `multiply`: Exact Multiplication and Adding Scales

Signatures:

```java
BigDecimal multiply(BigDecimal multiplicand)
BigDecimal multiply(BigDecimal multiplicand, MathContext mc)
```

Without a context, given:

\[
a=u_a\times10^{-s_a},\qquad
b=u_b\times10^{-s_b}
\]

then:

\[
ab=(u_a u_b)\times10^{-(s_a+s_b)}.
\]

Therefore:

\[
s_{\text{product}}=s_a+s_b.
\]

For example:

```java
BigDecimal a = new BigDecimal("1.20");  // scale 2
BigDecimal b = new BigDecimal("3.004"); // scale 3

BigDecimal result = a.multiply(b);

System.out.println(result);         // 3.60480
System.out.println(result.scale()); // 5
```

The unscaled values are 120 and 3004. Multiplying them gives 360480, and the total scale is `2+3=5`, so:

\[
360480\times10^{-5}=3.60480.
\]

The last trailing zero is not a calculation bug. Trailing zeros appear because exact multiplication **sets the preferred scale to the sum of the scales**.

### A Clearer Example of Trailing Zeros

```java
BigDecimal x = new BigDecimal("1.20");
BigDecimal y = new BigDecimal("3.0");

BigDecimal product = x.multiply(y);

System.out.println(product);         // 3.600
System.out.println(product.scale()); // 3
```

The mathematical value is `3.6`, but the scale is 3 because `2+1=3`. If the goal is to display money with two decimal places, you can apply `setScale(2, ...)` at the appropriate business boundary; do not assume the product's scale always equals the required number of output digits.

### Multiplying by Zero

```java
BigDecimal a = new BigDecimal("1.0");  // scale 1
BigDecimal zero = new BigDecimal("0.00"); // scale 2

BigDecimal product = a.multiply(zero);

System.out.println(product);         // 0.000
System.out.println(product.scale()); // 3
```

**A value of 0** does not automatically turn the scale into 0. Exact multiplication still follows the sum of scales in this common scenario.

### Increasing Result Digits Does Not Mean Input Precision Was Wrong

With `1.20 × 3.004`, the product has a six-digit unscaled value (`360480`) and precision 6. These are **digits of the result representation**, not a scientific guarantee that all six digits are reliable if both inputs were measurements with error.

## 6. Negative Scale: Addition/Subtraction and Multiplication Still Follow the Formulas

A `BigDecimal` can have a negative scale when created from a power-of-10 form:

```java
BigDecimal thousand = new BigDecimal("1E+3"); // scale -3
BigDecimal amount = new BigDecimal("2.50");   // scale 2
```

### Addition and Subtraction with Negative Scale

```java
BigDecimal sum = thousand.add(amount);
BigDecimal difference = thousand.subtract(amount);

System.out.println(sum);             // 1002.50
System.out.println(sum.scale());     // 2
System.out.println(difference);      // 997.50
System.out.println(difference.scale()); // 2
```

The preferred scale is `max(-3,2)=2`. For exact addition/subtraction, `1E+3` is aligned to scale 2, corresponding to the unscaled value `100000`.

### Multiplication with Negative Scale

```java
BigDecimal product = thousand.multiply(amount);

System.out.println(product);         // 2.50E+3
System.out.println(product.scale()); // -1
System.out.println(product.toPlainString()); // 2500
```

The total scale equals `-3+2=-1`. The unscaled value of the product is `1×250=250`, so:

\[
250\times10^{-(-1)}=2500.
\]

`toString()` may print scientific notation `2.50E+3`, while `toPlainString()` prints `2500`. When parsing the plain string `"2500"` back, the scale will typically be 0, **no longer -1**. If scale must be preserved across serialization, format choice is part of the data contract.

### `stripTrailingZeros()` Can Also Produce a Negative Scale

```java
BigDecimal raw = new BigDecimal("1000.00");
BigDecimal normalized = raw.stripTrailingZeros();

System.out.println(normalized);         // 1E+3
System.out.println(normalized.scale()); // -3
```

`stripTrailingZeros()` preserves the mathematical value but changes the scale. Do not normalize monetary amounts or measurements like this when scale or trailing zeros carry reporting significance.

## 7. `MathContext`: Do the Scale Rules Still Hold Completely?

There are overloads of `add`, `subtract`, and `multiply` that accept `java.math.MathContext`:

```java
BigDecimal result = a.add(b, mc);
BigDecimal difference = a.subtract(b, mc);
BigDecimal product = a.multiply(b, mc);
```

`MathContext` consists of:

- **Precision**: the limit on the number of significant digits of the result (not the number of decimal places).
- **RoundingMode**: the rounding rule when the number of significant digits must be reduced.

When using a `MathContext` with finite precision, Java may round the exact result, leading to an actual scale **different from the original preferred scale**.

For example:

```java
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("3.004");

MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

System.out.println(a.add(b, mc));      // 4.20
System.out.println(a.subtract(b, mc)); // -1.80
System.out.println(a.multiply(b, mc)); // 3.60
```

Comparison table:

| Operation | Without context | Exact scale | With `MathContext(3, HALF_UP)` | Scale after rounding |
| --- | --- | ---: | --- | ---: |
| `1.20 + 3.004` | `4.204` | 3 | `4.20` | 2 |
| `1.20 - 3.004` | `-1.804` | 3 | `-1.80` | 2 |
| `1.20 × 3.004` | `3.60480` | 5 | `3.60` | 2 |

This difference is **by API design**, not Java performing addition/subtraction/multiplication incorrectly. When the context limits the result to three significant digits, trailing digits are rounded according to `RoundingMode`.

### When Rounding Causes a Carry

```java
BigDecimal left = new BigDecimal("999.9");
BigDecimal right = new BigDecimal("0.2");

BigDecimal rounded = left.add(
        right, new MathContext(3, RoundingMode.HALF_UP));

System.out.println(rounded);             // 1.00E+3
System.out.println(rounded.precision()); // 3
System.out.println(rounded.scale());     // -1
```

The exact mathematical sum is `1000.1`. With three significant digits, it rounds to the value 1000 represented as `1.00E+3`, scale -1. When a carry occurs, scale can change significantly, including becoming negative.

### `MathContext.UNLIMITED`

`MathContext.UNLIMITED` has `getPrecision() == 0`; here 0 means **no precision limit imposed by the context**, not “the precision of a BigDecimal is 0”.

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("3.004");

System.out.println(a.add(b, MathContext.UNLIMITED)); // 4.204
System.out.println(a.multiply(b, MathContext.UNLIMITED)); // 3.60480
```

For the three operations add/subtract/multiply, an unlimited context does not require truncating digits; however, it is still subject to resource limits and representational scale limits. Division, on the other hand, can produce a non-terminating decimal expansion like `1/3`, requiring an appropriate rounding contract; do not infer that `MathContext.UNLIMITED` always makes division return a finite-digit result.

### Result Precision Does Not Necessarily Equal the Number Set in the Context

`new MathContext(6)` means **at most** six significant digits; if the natural result has only three significant digits, Java does not always pad it to six. Conversely, an unscaled number with many digits can be shortened considerably due to rounding.

Do not take `MathContext.getPrecision()` and assume it will equal `result.precision()` for every calculation.

## 8. `setScale` Is a Result Normalization Step, Not a Replacement for MathContext

If you need to display or store a number with **exactly two decimal places**, use `setScale` after defining the business policy:

```java
import java.math.RoundingMode;

BigDecimal exact = new BigDecimal("1.20")
        .add(new BigDecimal("3.004"));

BigDecimal display = exact.setScale(2, RoundingMode.HALF_UP);

System.out.println(exact);   // 4.204
System.out.println(display); // 4.20
```

- Exact `add` returns `4.204` with scale 3.
- `setScale(2, HALF_UP)` returns `4.20` with scale 2.

Because a digit is dropped, the two mathematical values differ (`4.204` and `4.20`); this is explicitly specified rounding, not faulty addition.

### When to Use `RoundingMode.UNNECESSARY`?

If reducing scale must not lose information:

```java
BigDecimal a = new BigDecimal("1.2300");
System.out.println(
        a.setScale(2, RoundingMode.UNNECESSARY)); // 1.23
```

Here only trailing zeros are removed, so no rounding of the mathematical value is needed. In contrast:

```java
BigDecimal x = new BigDecimal("1.234");
// x.setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: non-zero digit 4 must be discarded
```

Use `UNNECESSARY` when you want to **detect** a violation of the resolution requirement instead of silently rounding. For financial systems, fees, taxes, payments, or measurements, `RoundingMode` must follow relevant business policies and regulations; do not assume `HALF_UP` is right for every case.

### Round at Each Step or at the Final Step?

This is an important decision:

```java
BigDecimal sum = a.add(b);         // Keep the exact sum
BigDecimal result = sum.setScale(2, RoundingMode.HALF_UP);
```

In many problems, computing exactly first and rounding at the output/storage boundary is appropriate. However, some business contracts require rounding each invoice line item before summing. The two approaches **can yield different results**.

For example:

- Two amounts of `0.005` rounded with `HALF_UP` **per item** to two digits: `0.01 + 0.01 = 0.02`.
- If **added first**: `0.005 + 0.005 = 0.010`, then rounded to two digits: `0.01`.

There is no single rule for all systems. You must specify the smallest unit, rounding timing, precision, and tie-breaking behavior.

## 9. Scale and Equality: `equals` Differs from `compareTo`

Because scale is part of `BigDecimal`'s representation, two objects with the **same numeric value** may not be equal according to `equals`:

```java
BigDecimal a = new BigDecimal("2.0");  // scale 1
BigDecimal b = new BigDecimal("2.00"); // scale 2

System.out.println(a.equals(b));     // false
System.out.println(a.compareTo(b));  // 0
```

`equals` requires both value and scale to match; `compareTo` checks mathematical value ordering and ignores trailing zeros.

Consequences:

- `HashSet<BigDecimal>` / `HashMap<BigDecimal, ...>` use `equals` and `hashCode`, so they can treat `2.0` and `2.00` as **two different keys**.
- `TreeSet<BigDecimal>` / `TreeMap<BigDecimal, ...>` rely on natural `compareTo` ordering, so they typically treat them as **the same key in terms of ordering**.
- `setScale` or `stripTrailingZeros` can change the result of `equals` even though arithmetic value is unchanged.

If scale is important information (for example, fixed at 2 decimal digits), preserve scale and use `equals` as required by the schema. If you only want to determine whether two numbers represent the same mathematical value, use `compareTo(...) == 0` or establish an appropriate canonicalization rule.

### Multiplication Results and Collection Keys

```java
BigDecimal p = new BigDecimal("1.20")
        .multiply(new BigDecimal("3.0")); // 3.600, scale 3
BigDecimal q = new BigDecimal("3.60");     // 3.60, scale 2

System.out.println(p.equals(q));    // false
System.out.println(p.compareTo(q)); // 0
```

If you use `p` as a `HashMap` key and then query with `q`, not finding the key is **correct according to `equals`**, not a hashmap bug. Choose a scale/canonicalization rule at the appropriate boundary.

## 10. Edge Cases to Check

### 10.1. Exponential Notation Inputs

`new BigDecimal("1E+3")` has scale -3; adding `2.50` gives scale 2, multiplying by `2.50` gives scale -1. Do not enforce that `scale` is always non-negative in validation code, and do not assume total scale during multiplication equals the number of digits after the dot in display form.

### 10.2. Zero Results

`0.00` and `0.000` are equal under `compareTo` but differ under `equals`; exact operations still have a preferred scale. When you need to preserve the source resolution rule, do not automatically replace every zero with `BigDecimal.ZERO` which has scale 0.

### 10.3. `int` Scale Limits

`scale()` is an `int`. If the sum of scales during multiplication exceeds the `int` range, or an operation adjusts scale out of range, Java may throw `ArithmeticException`. Certain details for zero results and context-based methods are handled specifically per the API contract; do not invent a modulo formula or try to cast around that limit.

Data constructed from extreme exponents can trigger expensive scale alignment, allocation, or computation. For untrusted input, limit the number of digits, exponents, precision, and workload.

### 10.4. Sign of Zero

`BigDecimal` does not have distinct `+0.0` and `-0.0` IEEE 754 representations like `double`. Entering `new BigDecimal("-0.00")` represents zero with scale 2; addition/subtraction/multiplication follow value 0 and scale. If a literal negative sign in the input has reporting meaning, the raw input string must be kept separately.

### 10.5. Inputs from `double` May Have Already Lost Source Decimal Accuracy

```java
BigDecimal good = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);

System.out.println(good); // 0.1
System.out.println(fromDouble);
// 0.1000000000000000055511151231257827021181583404541015625
```

`new BigDecimal(double)` represents the exact binary value already held by the `double`, not the decimal string the user entered. For business decimals, prefer `new BigDecimal(String)`; `BigDecimal.valueOf(double)` uses the decimal form from `Double.toString`, but also cannot recover errors already introduced earlier in a `double` pipeline.

If you want exact calculations with `BigDecimal`, **do not pass data through `double` first** and hope add/multiply will automatically fix lost precision.

## 11. Complete Java 17 Demo

Save the file `BigDecimalOperationsScaleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalOperationsScaleDemo {

    static void show(String label, BigDecimal x) {
        System.out.println(label + " = " + x
                + " | scale=" + x.scale()
                + " | precision=" + x.precision());
    }

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.20");
        BigDecimal b = new BigDecimal("3.004");

        show("add", a.add(b));
        show("subtract", a.subtract(b));
        show("multiply", a.multiply(b));

        BigDecimal x = new BigDecimal("0.10");
        BigDecimal y = new BigDecimal("0.2");

        show("decimal add", x.add(y));
        show("decimal subtract", x.subtract(y));
        show("decimal multiply", x.multiply(y));

        BigDecimal thousand = new BigDecimal("1E+3");
        BigDecimal small = new BigDecimal("2.50");

        show("negative-scale add", thousand.add(small));
        show("negative-scale multiply", thousand.multiply(small));

        show("zero add", new BigDecimal("2.00")
                .add(new BigDecimal("-2.00")));
        show("zero multiply", new BigDecimal("1.0")
                .multiply(new BigDecimal("0.00")));

        MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

        show("context add", a.add(b, mc));
        show("context subtract", a.subtract(b, mc));
        show("context multiply", a.multiply(b, mc));
        show("context carry", new BigDecimal("999.9")
                .add(new BigDecimal("0.2"), mc));

        show("setScale2", a.add(b)
                .setScale(2, RoundingMode.HALF_UP));

        BigDecimal p = new BigDecimal("1.20")
                .multiply(new BigDecimal("3.0"));
        BigDecimal q = new BigDecimal("3.60");

        System.out.println("equals 3.600 / 3.60 = "
                + p.equals(q));
        System.out.println("compare 3.600 / 3.60 = "
                + p.compareTo(q));
    }
}
```

Compile/run:

```bash
javac BigDecimalOperationsScaleDemo.java
java BigDecimalOperationsScaleDemo
```

Output on Java 17:

```text
add = 4.204 | scale=3 | precision=4
subtract = -1.804 | scale=3 | precision=4
multiply = 3.60480 | scale=5 | precision=6
decimal add = 0.30 | scale=2 | precision=2
decimal subtract = -0.10 | scale=2 | precision=2
decimal multiply = 0.020 | scale=3 | precision=2
negative-scale add = 1002.50 | scale=2 | precision=6
negative-scale multiply = 2.50E+3 | scale=-1 | precision=3
zero add = 0.00 | scale=2 | precision=1
zero multiply = 0.000 | scale=3 | precision=1
context add = 4.20 | scale=2 | precision=3
context subtract = -1.80 | scale=2 | precision=3
context multiply = 3.60 | scale=2 | precision=3
context carry = 1.00E+3 | scale=-1 | precision=3
setScale2 = 4.20 | scale=2 | precision=3
equals 3.600 / 3.60 = false
compare 3.600 / 3.60 = 0
```

The output helps distinguish:

- **Exact operations without a context** choose scale based on operand scales.
- `MathContext` can round digits and change scale.
- `setScale` expresses the number of decimal places required by a schema.
- Two results with the same mathematical value can still differ under `equals` because of scale.

## 12. Common Mistakes

| Mistake | What happens | Proper approach |
| --- | --- | --- |
| Adding two `BigDecimal` values and expecting the first operand's scale to remain | Exact result uses `max(scaleA,scaleB)` | Check `result.scale()`; normalize when needed |
| Thinking the product's scale is also `max(scaleA,scaleB)` | Exact multiplication uses **sum of scales** | `scaleA + scaleB` |
| Expecting `1.20 * 3.0` to print `3.6` | Scale 3 gives `3.600` | Choose `setScale`/formatter according to business logic |
| Calling `a.add(b);` without assigning | Object `a` is immutable | `a = a.add(b);` if you want to update the variable |
| Treating MathContext precision 2 as scale 2 | Precision counts significant digits | `setScale(2, roundingMode)` for two decimal places |
| Thinking context does not affect scale | Rounding can change scale | Check value, precision, and scale |
| Using `RoundingMode.UNNECESSARY` when rounding is needed | Throws `ArithmeticException` | Choose a rounding policy or reject the data |
| Rounding each term vs. after summing without considering the difference | Two calculation flows can give different results | Specify rounding timing clearly |
| `p.equals(q)` to check same mathematical value | Two values with different scales are not equal | `p.compareTo(q) == 0` if comparing value only |
| Normalizing with `stripTrailingZeros` everywhere | Can lose trailing zeros / produce negative scale | Normalize only when the contract allows |
| Thinking zero's scale is always 0 | `0.000` has scale 3 | Preserve scale per schema or policy |
| Assuming scale cannot be negative | Form `"1E+3"` has scale -3 | Use the `unscaled × 10^-scale` model properly |
| Using `double` then `new BigDecimal(double)` | Introduces binary error into decimal arithmetic | Parse decimal source from strings |
| Keeping exact add/subtract/multiply results and assuming they fit all displays | Mathematical scale does not automatically match reporting scale | Format per system units and requirements |
| Believing `BigDecimal` results cannot cause resource errors | Excessive scale/precision can exceed limits | Validate input size and range |

## 13. Exercises with Answers

**Exercise 1.** Compute the value and scale of `new BigDecimal("1.20").add(new BigDecimal("3.004"))`.

**Answer:** `4.204`, scale 3 because `max(2,3)=3`.

**Exercise 2.** With the same two operands above, what are the results of `subtract` and `multiply`?

**Answer:** `subtract = -1.804` (scale 3); `multiply = 3.60480` (scale 5 because `2+3=5`).

**Exercise 3.** Why does `"0.10" + "0.2"` produce `"0.30"` instead of printing `"0.3"`?

**Answer:** Exact addition has a preferred scale of 2 because the first operand has scale 2. The two strings have the same numeric value, but their `BigDecimal` representations have different scales.

**Exercise 4.** What is the scale of `new BigDecimal("1E+3").multiply(new BigDecimal("2.50"))`?

**Answer:** Scale -1, because `-3+2=-1`. The mathematical value is 2500, and `toString()` may print `"2.50E+3"`.

**Exercise 5.** Why can `new BigDecimal("1.0").multiply(new BigDecimal("0.00"))` print `"0.000"`?

**Answer:** Even though the product is 0, exact multiplication preserves the sum of scales `1+2=3`.

**Exercise 6.** If an application requires the sum to be displayed with exactly two decimal digits, which method expresses this more clearly: `new MathContext(2)` or `setScale(2, HALF_UP)`?

**Answer:** `setScale(2, HALF_UP)` specifies exactly two decimal places; `MathContext(2)` limits total significant digits to two, not two digits after the decimal point.

**Exercise 7.** Why can `a.add(b, new MathContext(3, HALF_UP))` return `4.20` instead of `4.204`?

**Answer:** MathContext allows at most three significant digits, causing the exact sum to be rounded; the final scale changes from 3 to 2.

**Exercise 8.** What is `BigDecimal("3.600").equals(BigDecimal("3.60"))`? What does `compareTo` give?

**Answer:** `equals` is `false` because the scales are 3 and 2 respectively; `compareTo` is 0 because they have the same mathematical value.

**Exercise 9.** Give a scenario where rounding each line item then summing differs from summing first then rounding.

**Answer:** Two lines of `0.005`: rounding each line with `HALF_UP` to two decimal places gives `0.01+0.01=0.02`; summing exactly first gives `0.010`, and rounding to two decimal places gives `0.01`. You must follow the business rule.

**Exercise 10.** Given `BigDecimal a = new BigDecimal("10.00"); a.subtract(BigDecimal.ONE);`, what is the value of `a` afterward if the result is not assigned?

**Answer:** `10.00`. `BigDecimal` is immutable, so calling `subtract` and ignoring the return value does not change `a`.

**Summary:** In **exact operations without passing a context**, `add` and `subtract` choose the larger scale of the two operands, and `multiply` adds the two scales. These are **result representation** rules; if a `MathContext` is added, the result may round and change scale. `setScale` serves fixed-decimal-place requirements, while `compareTo` and `equals` have different meanings when scales differ. Preserve immutability, accurate decimal source data, and choose a rounding policy before applying it to business logic.