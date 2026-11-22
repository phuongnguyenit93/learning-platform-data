# Why Is `0.1` Usually Not Represented Exactly in Java?

## 1. The Phenomenon: Simple-Looking Numbers Producing Strange Results

In Java, the following familiar operations can be surprising:

```java
double a = 0.1;
double b = 0.2;
double sum = a + b;

System.out.println(a);          // 0.1
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
```

This is **not Java computing randomly**. The `float` and `double` types store real numbers using a **finite binary floating-point representation**, typically following the IEEE 754 standard. Some decimal fractions, including `0.1`, **do not have a finite binary representation**, so they must be rounded to the nearest representable value.

Key points:

- `0.1` is written exactly in **decimal**, but is not necessarily stored exactly in `double`.
- Approximation error usually appears **as soon as the literal is converted to a floating-point value**, even before addition.
- Subsequently, each floating-point operation may require rounding again. Hence `0.1 + 0.2` does not necessarily match the bit pattern of the literal `0.3`.
- `System.out.println(0.1)` printing `0.1` **does not prove that the internally stored bits equal mathematical one-tenth**.

Learning to distinguish **mathematical value**, **stored binary value**, and **printed decimal string** is the key to understanding this issue.

## 2. Fractions in Binary Differ from Fractions in Decimal

In decimal, each digit after the point corresponds to a negative power of 10:

```text
0.1 (base 10) = 1 × 10^-1 = 1/10
0.25          = 2 × 10^-1 + 5 × 10^-2
              = 25/100 = 1/4
```

In binary, the digits after the point correspond to negative powers of 2:

```text
0.1₂   = 1 × 2^-1 = 1/2  = 0.5₁₀
0.01₂  = 1 × 2^-2 = 1/4  = 0.25₁₀
0.001₂ = 1 × 2^-3 = 1/8  = 0.125₁₀
0.11₂  = 1/2 + 1/4       = 0.75₁₀
```

A rational fraction in lowest terms `p/q` (with `q > 0`) has a **finite binary** representation if and only if the denominator `q` is a power of 2, such as `1`, `2`, `4`, `8`, `16`, ...

| Decimal Value | Reduced Fraction | Has Finite Binary Representation? | Example Representation |
| --- | --- | --- | --- |
| `0.5` | `1/2` | Yes | `0.1₂` |
| `0.25` | `1/4` | Yes | `0.01₂` |
| `0.125` | `1/8` | Yes | `0.001₂` |
| `0.375` | `3/8` | Yes | `0.011₂` |
| `0.1` | `1/10` | No | Infinite repeating |
| `0.2` | `1/5` | No | Infinite repeating |
| `0.3` | `3/10` | No | Infinite repeating |

Why is `0.1` special? Because `1/10 = 1/(2 × 5)`. After reduction, the denominator still contains a **factor of 5**, which cannot become a pure power of 2. Therefore, there exists **no finite sequence of binary digits** that represents `1/10` exactly.

This rule is a property of number bases, **not specific to Java**. Similarly, `1/3` is written as infinite `0.33333...` in decimal; `1/10` is written as an infinite sequence in binary.

## 3. How Does the Binary Representation of `0.1` Repeat Infinitely?

Repeatedly multiply the fractional part by 2 to extract each bit after the point:

| Step | Fractional part × 2 | Integer bit | Remaining fractional part |
| --- | --- | ---: | --- |
| 1 | 0.1 × 2 = 0.2 | 0 | 0.2 |
| 2 | 0.2 × 2 = 0.4 | 0 | 0.4 |
| 3 | 0.4 × 2 = 0.8 | 0 | 0.8 |
| 4 | 0.8 × 2 = 1.6 | 1 | 0.6 |
| 5 | 0.6 × 2 = 1.2 | 1 | 0.2 |
| 6 | 0.2 × 2 = 0.4 | 0 | 0.4 |
| 7 | 0.4 × 2 = 0.8 | 0 | 0.8 |
| 8 | 0.8 × 2 = 1.6 | 1 | 0.6 |

From the remainder `0.2`, the steps repeat as before. Thus:

```text
0.1₁₀ = 0.000110011001100110011001100110011...₂
        0.00011(0011)(0011)(0011)...₂
```

This is an **infinite** sequence; `float` or `double` cannot store infinitely many bits. The machine must choose a finite binary number **closest to `0.1`** within the value set representable by that type.

You should not assume Java “truncates arbitrarily after a few bits.” Floating-point representation uses a deterministic rounding rule; under the default rounding mode, the nearest representable value is chosen with a tie-breaking rule (*round to nearest, ties to even*).

## 4. How Do `float` and `double` Store Bits?

In Java, `float` corresponds to the 32-bit binary format and `double` corresponds to the 64-bit binary format. For finite normal numbers (*normal*), the value is represented by sign, significand, and base-2 exponent.

| Component | `float` / binary32 | `double` / binary64 |
| --- | ---: | ---: |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Exponent field bits | 8 | 11 |
| Stored fraction bits | 23 | 52 |
| Significand precision (including implicit `1` bit of normal numbers) | 24 bits | 53 bits |
| Approximate significant decimal digits | 6–9 | 15–17 |

Note: **53 bits of `double`** does not mean “53 decimal digits.” It consists of 53 **significant binary digits**. The exponent determines magnitude; the number of significand bits determines the ability to distinguish closely spaced numbers.

`double` has more bits than `float`, so it approximates `0.1` **more accurately**, yet **still does not equal `1/10` exactly**.

### The `double` Value Actually Stored

For the `double` literal `0.1` in Java:

```text
Hexadecimal floating-point form:
0x1.999999999999ap-4

Exact value of that bit pattern:
3602879701896397 / 36028797018963968

Written in unrounded decimal:
0.1000000000000000055511151231257827021181583404541015625
```

The fraction above is **slightly larger than `1/10`**. This is not “an error introduced by `println`”; it is the true numeric value of the stored bit pattern. Default display formatting is shorter for readability.

Meanwhile, the `float` literal `0.1f` is approximately:

```text
0.100000001490116119384765625
```

`float` has fewer precision bits, so its representation error can be larger than `double`'s.

## 5. Why Does Java Still Print `0.1` Instead of the Entire Long Sequence?

```java
double x = 0.1;
System.out.println(x);              // 0.1
System.out.println(Double.toHexString(x)); // 0x1.999999999999ap-4
```

`Double.toString` (used when `println` converts a `double` to a string) chooses a short decimal representation matching Java's formatting rules that can be converted back to the **exact same `double` value**. The string `"0.1"` is sufficient to reconstruct the rounded `double` bit pattern, so there is no need to print every decimal digit of the exact base-10 conversion of that binary fraction.

Three concepts must be kept separate:

1. **Literal in source code:** `0.1` is a decimal notation targeting the mathematical value one-tenth.
2. **Stored floating-point value:** the 64-bit binary number closest to one-tenth, though not equal to it.
3. **Printed string:** typically the short string `"0.1"` for human readability and for round-tripping back to the exact same bit pattern.

To see the full decimal number corresponding to the stored value, you can use `new BigDecimal(x).toPlainString()`. However, this only **exposes the existing binary approximation**; it does not fix it into mathematical `0.1`.

## 6. Why Does `0.1 + 0.2 == 0.3` Return `false`?

```java
System.out.println(0.1 + 0.2);      // 0.30000000000000004
System.out.println(0.3);            // 0.3
System.out.println(0.1 + 0.2 == 0.3); // false
```

There are **two kinds of rounding** to note:

1. The literals `0.1`, `0.2`, and `0.3` are each converted to binary numbers near the intended decimal values.
2. Adding two represented `double` values also produces a result rounded to the nearest `double` bit pattern.

The stored result of `0.1 + 0.2` is the `double` value **immediately greater** than the `double` value of the literal `0.3`. The `==` operator compares **two floating-point values**, not whether two expressions are “equal by decimal intent.”

Therefore, you should not say “Java thinks `0.1 + 0.2` is a different mathematical number from `0.3`.” Mathematical addition is still exact at `0.3`; it is the **approximation and rounding within the representable number set** that makes the computed result differ.

A helpful notation:

```text
Ideal value:  0.1 + 0.2 = 0.3
double value: fl(fl(0.1) + fl(0.2)) ≠ fl(0.3)
```

Where `fl(x)` denotes rounding a mathematical number to a representable `double` value.

## 7. When Can a Number Be Stored Exactly?

**Not all decimal numbers are distorted.** Fractions whose reduced denominator is a power of 2 can have a finite binary representation, for example:

```java
System.out.println(0.5 + 0.25 == 0.75); // true
System.out.println(0.125 + 0.25 == 0.375); // true
```

These values have short binary representations, and the example operations also yield exact representable results. However, **“having a finite binary representation” is not enough to guarantee every value is stored exactly at fixed precision**: if more than 24 or 53 significand bits are needed, the number will still round.

Example with integers:

```java
long a = 9_007_199_254_740_992L; // 2^53.
long b = 9_007_199_254_740_993L; // 2^53 + 1.

System.out.println((double) a == (double) b); // true
```

Both are **integers** and of course have finite binary representations, yet `double` cannot distinguish them at this magnitude: `2^53 + 1` rounds to `2^53`. This shows that “can the number be written finitely in base 2?” differs from “does a 64-bit format have **enough precision bits** for that number?”.

**General rule:** to be represented exactly in a floating-point type, a number must both fit base-2 structure and have a significand and exponent within the format's limits.

## 8. Practical Impact: Comparison, Accumulation, and Loop Conditions

### 8.1. Exact Equality Comparison Against Computed Results

```java
double total = 0.1 + 0.2;

if (total == 0.3) {
    System.out.println("equal");
} else {
    System.out.println("different");
}
// The "different" branch runs.
```

Using `==` is completely appropriate when you **intentionally compare stored value patterns** (such as comparing with the exact same stored value, or comparing small integers converted without loss). For floating-point calculation results, however, `==` usually cannot substitute for the domain notion of “close enough to be considered equal.”

An approximate comparison technique:

```java
double a = 0.1 + 0.2;
double b = 0.3;
double tolerance = 1e-12;

boolean nearlyEqual = Math.abs(a - b) <= tolerance;
System.out.println(nearlyEqual); // true
```

**No single fixed `tolerance` fits all cases.** The threshold must come from the units, value range, and acceptable error of the problem. For very large or very small numbers, an absolute tolerance combined with a relative tolerance may be needed; for `NaN`, infinity, and values near 0, specific handling must also be defined.

If a problem requires comparison **exact to every decimal digit** (such as monetary amounts), merely increasing `tolerance` does not guarantee business correctness. In that case, choose an exact decimal representation from the start.

### 8.2. Repeated Addition and Accumulated Error

```java
double total = 0.0;
for (int i = 0; i < 10; i++) {
    total += 0.1;
}
System.out.println(total); // 0.9999999999999999
```

Because each addition can round, small errors can accumulate or cancel out depending on the data and order of operations. Do not assume that adding `0.1` ten times in a loop **always** equals `1.0` in `double`.

For large quantities of real numbers in science or statistics, more stable summation algorithms can be considered (such as compensated/Kahan summation or appropriate summation APIs), but those algorithms **reduce error**; they do not change the fact that `0.1` has no exact finite binary representation.

### 8.3. Loop Bounds and Conditions

```java
double x = 0.0;
while (x < 1.0) {
    x += 0.1;
}
```

This example merely illustrates a design trap: looping by adding a floating-point step can cause the iteration count to differ from ideal decimal arithmetic. You should normally **loop with an integer counter** and compute the corresponding value:

```java
for (int i = 0; i <= 10; i++) {
    double x = i / 10.0;
    // Use x in your problem.
}
```

Looping with an integer counter controls the **number of iterations**; it does not make every `i / 10.0` an exact decimal representation.

## 9. When Exact Decimal Calculation Is Needed: Using `BigDecimal` Properly

For money, taxes, interest rates with decimal rounding rules, or data requiring exact decimal digits, Java provides `java.math.BigDecimal`. It represents a value using an **unscaled integer value and a decimal scale**, so it can represent `0.1`, `0.2`, and `0.3` **exactly** when created as decimals from the start.

### Creating from Decimal Strings

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal expected = new BigDecimal("0.3");

BigDecimal sum = a.add(b);
System.out.println(sum);                   // 0.3
System.out.println(sum.equals(expected));  // true
```

This is exact decimal addition on the chosen input values. `BigDecimal` is **immutable**; the `add` method returns a new result object.

### Avoiding the `new BigDecimal(0.1)` Trap

```java
BigDecimal fromLiteral = new BigDecimal(0.1);
BigDecimal fromString = new BigDecimal("0.1");

System.out.println(fromLiteral.equals(fromString)); // false
System.out.println(fromLiteral.toPlainString());
// 0.1000000000000000055511151231257827021181583404541015625
```

The `new BigDecimal(double)` constructor stores **the exact rounded `double` value**, not the decimal value “originally in the coder's head.” Hence it exposes the long decimal sequence from the binary representation.

Use `new BigDecimal("0.1")` when input is specified by decimal digits. If you must convert a `double` to `BigDecimal` using the short decimal string representing that `double`, use `BigDecimal.valueOf(0.1)`:

```java
System.out.println(BigDecimal.valueOf(0.1)); // 0.1
```

Distinction: `BigDecimal.valueOf(double)` relies on converting `double` to its decimal string. It **cannot recover lost input information or errors** if you already performed `double` calculations before converting:

```java
System.out.println(BigDecimal.valueOf(0.1 + 0.2)); // 0.30000000000000004
```

Therefore, if you want exact decimal calculations, construct `BigDecimal` **before computing**, typically from validated strings or from integers with an explicit scale.

### `BigDecimal` Has Its Own Rules Too

- `BigDecimal("0.1").add(BigDecimal("0.2"))` as shorthand illustration is not valid Java syntax: you must use `new BigDecimal("0.1")` for each operand.
- Do not use `+`, `-`, `*` operators on `BigDecimal` objects; use `add`, `subtract`, `multiply`.
- Decimal division can produce an infinite expansion: for instance, `BigDecimal.ONE.divide(new BigDecimal("3"))` can throw `ArithmeticException` if no rounding context is specified. When needed, use `MathContext` or `divide(divisor, scale, RoundingMode)`.
- `equals` on `BigDecimal` checks both **value and scale**: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false`; `compareTo` returns `0` if you only need numeric value comparison.

**Design note:** `BigDecimal` fits exact decimal arithmetic, though it has object/computation overhead and requires explicit scale/rounding rules. For embedded, financial, or fixed two-decimal currency applications, **integers in the smallest unit** (such as cents) are also a strong option if value ranges are defined and integer overflow is prevented.

## 10. Do Not Confuse This with Other `float`/`double` Issues

Floating-point numbers also have `NaN`, `Infinity`, `-Infinity`, subnormals, and the two zero bit patterns `+0.0`/`-0.0`. These concepts are important, yet **not the direct cause** of the `0.1 + 0.2` phenomenon.

For the `0.1` representation issue, remember the differences among:

- **Representation error:** the literal `0.1` has no finite binary representation, so the floating-point type stores the closest value.
- **Operation rounding error:** during addition, multiplication, or division, the mathematical result may also be unrepresentable and require rounding.
- **Conversion error:** when converting `double → float` or large integers to a floating-point type, additional precision can be lost.
- **String printing rules:** `println` typically picks a short string that round-trips accurately, rather than printing the full exact decimal value of the bits.

Converting `float` to `double` **after the value has already been rounded** does not restore the original value either:

```java
float a = 0.1f;
double promoted = a;
System.out.println(promoted); // 0.10000000149011612
```

A widening conversion preserves the **actual `float` value already stored**. It does not substitute the `double` value closest to `0.1`.

## 11. Complete, Runnable Java 17+ Example

Create the file **`WhyPointOneIsApproximate.java`**:

```java
import java.math.BigDecimal;

public class WhyPointOneIsApproximate {
    public static void main(String[] args) {
        double oneTenth = 0.1;
        double sum = 0.1 + 0.2;

        System.out.println("0.1 printed = " + oneTenth);
        System.out.println("0.1 hex = " + Double.toHexString(oneTenth));
        System.out.println("0.1 exact decimal = "
                + new BigDecimal(oneTenth).toPlainString());
        System.out.println("0.1 + 0.2 = " + sum);
        System.out.println("sum == 0.3 = " + (sum == 0.3));
        System.out.println("near 0.3 = "
                + (Math.abs(sum - 0.3) < 1e-12));

        float asFloat = 0.1f;
        double expandedFloat = asFloat;
        System.out.println("float 0.1 widened = " + expandedFloat);

        double total = 0.0;
        for (int i = 0; i < 10; i++) {
            total += 0.1;
        }
        System.out.println("0.1 added ten times = " + total);

        BigDecimal decimalSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("BigDecimal sum = " + decimalSum);
        System.out.println("BigDecimal.valueOf(0.1) = "
                + BigDecimal.valueOf(0.1));
        System.out.println("BigDecimal.valueOf(double sum) = "
                + BigDecimal.valueOf(sum));

        System.out.println("exact binary double equals decimal BigDecimal = "
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));

        System.out.println("1.0 equals 1.00 with BigDecimal = "
                + new BigDecimal("1.0").equals(new BigDecimal("1.00")));
        System.out.println("1.0 compares numerically to 1.00 = "
                + new BigDecimal("1.0").compareTo(new BigDecimal("1.00")));
    }
}
```

Compile and run:

```bash
javac WhyPointOneIsApproximate.java
java WhyPointOneIsApproximate
```

Output:

```text
0.1 printed = 0.1
0.1 hex = 0x1.999999999999ap-4
0.1 exact decimal = 0.1000000000000000055511151231257827021181583404541015625
0.1 + 0.2 = 0.30000000000000004
sum == 0.3 = false
near 0.3 = true
float 0.1 widened = 0.10000000149011612
0.1 added ten times = 0.9999999999999999
BigDecimal sum = 0.3
BigDecimal.valueOf(0.1) = 0.1
BigDecimal.valueOf(double sum) = 0.30000000000000004
exact binary double equals decimal BigDecimal = false
1.0 equals 1.00 with BigDecimal = false
1.0 compares numerically to 1.00 = 0
```

The example above tests three different layers: **stored value**, **operation behavior**, and **how results are formatted as strings**. In particular, `new BigDecimal(0.1)` and `new BigDecimal("0.1")` differ because they are constructed from **two fundamentally different input values**.

## 12. Common Mistakes and Correct Ways of Thinking

| Misconception | Correct Explanation |
| --- | --- |
| “The machine stores 0.1 accurately; only addition causes errors.” | The literal `0.1` is already rounded when converted to `float`/`double`. |
| “`println(0.1)` prints 0.1, so the stored value must equal one-tenth.” | The short display string is not the full decimal expansion of the stored bits. |
| “`double` has 64 bits so it holds every decimal fraction accurately.” | The bit count is finite and uses base 2; `1/10` has an infinite binary expansion. |
| “Upgrading from `float` to `double` erases all errors.” | `double` provides a better approximation; already-rounded `float` data does not revert to the original value. |
| “No decimal fraction can be represented accurately.” | `0.5`, `0.25`, and `0.125` have finite binary representations and are stored accurately when within range and precision. |
| “`0.1 + 0.2 == 0.3` must always be true because math says so.” | The Java expression operates on approximated `double` values and then compares them. |
| “Using `new BigDecimal(0.1)` yields exact decimal 0.1.” | It preserves the already-approximated `double` value; use the string `"0.1"` for decimal data. |
| “Just make epsilon huge so every comparison passes.” | A large threshold can treat genuinely different values as equal; it must be based on domain precision. |
| “`BigDecimal` requires no thought about rounding.” | Infinite decimal divisions still require choosing a `MathContext`/`RoundingMode`. |

**Remember:** `0.1 = 1/10` has no finite binary representation because its reduced denominator contains a factor of 5. `float` and `double` can only store the **closest approximation** in finite bits; subsequent operations may round again. Use `double` when the problem tolerates floating-point error and manage comparisons appropriately; use `BigDecimal` **constructed from strings or controlled decimal inputs** when exact decimal values must be preserved.

**References:** [Java Language Specification §4.2.3 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3); [JLS §15.4 — FP-strict Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.4); [Java SE 21 Double API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html); [Java SE 21 BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).