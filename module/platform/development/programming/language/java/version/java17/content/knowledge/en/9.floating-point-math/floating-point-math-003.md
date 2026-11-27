# Precision Limits in Addition, Multiplication, and Division of Floating-Point Numbers in Java 17

In Java, floating-point types like `float` and `double` store values in binary floating-point form (*binary floating-point*). They offer a very wide representable range and fast computation, but **cannot represent every decimal number exactly**. Consequently, the result of addition, multiplication, or division can deviate slightly from the expected mathematical result.

A familiar example:

```java
double result = 0.1 + 0.2;
System.out.println(result);
System.out.println(result == 0.3);
```

Typical output:

```text
0.30000000000000004
false
```

This is not a random Java bug. It stems from how binary floating-point numbers represent values and round results. Understanding this mechanism lets you choose the right data type, compare floating-point values sensibly, and use `BigDecimal` when a problem requires exact decimal arithmetic.

## 1. How Does Java Represent Floating-Point Numbers?

Java has two common primitive floating-point types:

| Type | Format | Binary Precision | Typical Decimal Precision |
| --- | --- | ---: | ---: |
| `float` | IEEE 754 binary32 | 24-bit significand (including implicit bit for normal numbers) | About 6–9 significant digits |
| `double` | IEEE 754 binary64 | 53-bit significand (including implicit bit for normal numbers) | About 15–17 significant digits |

In Java:

- A decimal literal like `1.25` defaults to type `double`.
- Add the suffix `f` or `F` to create a `float` literal, such as `1.25f`.
- The suffix `d` or `D` can be used to explicitly specify `double`, though it is usually unnecessary.
- `double` is typically the default choice for floating-point calculations unless stated otherwise.

A floating-point value is represented approximately in the form:

\[
(-1)^{sign} \times significand \times 2^{exponent}
\]

The significand has a finite number of bits. Therefore, only fractions representable as a finite sum of powers of 2 have a finite binary representation. Fractions like \(1/2\), \(1/4\), \(3/8\) are represented exactly; fractions like \(1/10\), \(1/5\), \(1/3\) have infinite binary sequences and must be rounded.

### 1.1. Why Is 0.1 Not Represented Exactly?

In base 10, `0.1` has a finite representation. In binary, however, that value repeats infinitely, much like \(1/3\) appears as `0.3333...` in decimal.

The machine only has a finite number of bits to store the significand, so it must pick the nearest representable binary value. When read back or printed, Java converts that value into the shortest decimal string distinguishable from adjacent floating-point values.

Example:

```java
public class FloatingPointRepresentation {
    public static void main(String[] args) {
        double value = 0.1;
        System.out.printf("Default: %.17f%n", value);
        System.out.printf("Sum:     %.17f%n", 0.1 + 0.2);

        float floatValue = 0.1f;
        System.out.printf("float:   %.9f%n", floatValue);
    }
}
```

Illustrative output:

```text
Default: 0.10000000000000000
Sum:     0.30000000000000004
float:   0.100000001
```

Printing with a fixed number of digits after the decimal point is specified by `printf`. It helps make the error visible; it does not mean the variable `value` actually holds the printed decimal string.

### 1.2. Large Integers Can Also Lose Precision When Converted to double

`double` has 53 bits of significand precision. Thus, every consecutive integer is represented exactly up to \(2^{53}\); beyond that mark, the spacing between representable values exceeds 1.

Example:

```java
public class IntegerPrecision {
    public static void main(String[] args) {
        double value = 9_007_199_254_740_992d; // 2^53

        System.out.println(value);
        System.out.println(value + 1.0);
        System.out.println(value == value + 1.0);
    }
}
```

Output:

```text
9.007199254740992E15
9.007199254740992E15
true
```

The integer \(2^{53}+1\) cannot be represented exactly by `double`. If you need to store large integers, consider `long` or `BigInteger` depending on range. Converting a large integer to `double` just for calculation can lose units.

## 2. Addition: Errors Can Accumulate or Lose Small Parts

When adding two floating-point numbers, the mathematical result is usually rounded to the nearest representable `float` or `double`. Small errors from each addition can accumulate when repeated many times.

### 2.1. Repeated Addition Does Not Necessarily Equal Multiplication

Example:

```java
public class RepeatedAddition {
    public static void main(String[] args) {
        double sum = 0.0;

        for (int i = 0; i < 10; i++) {
            sum += 0.1;
        }

        System.out.printf("%.17f%n", sum);
        System.out.println(sum == 1.0);
    }
}
```

Output may show:

```text
0.99999999999999990
false
```

Each addition rounds to a representable value. Small errors across multiple steps can cause the final result to differ from the exact mathematical value.

### 2.2. Adding a Very Small Number to a Very Large Number

Suppose:

```java
double large = 1e16;
double small = 1.0;

System.out.println(large + small == large);
```

The result is `true` in binary64. At magnitude \(10^{16}\), the gap between representable `double` values is already greater than 1; adding 1 does not change the value after rounding.

This phenomenon is often called **absorption**: the small contribution is absorbed when added to a large value.

### 2.3. Floating-Point Addition Is Not Strictly Associative

In mathematics:

\[
(a+b)+c = a+(b+c)
\]

With floating-point numbers, however, because each step can round, two ways of grouping addition can yield different results:

```java
public class AdditionOrder {
    public static void main(String[] args) {
        double a = 1e16;
        double b = -1e16;
        double c = 1.0;

        System.out.println((a + b) + c);
        System.out.println(a + (b + c));
    }
}
```

Illustrative output:

```text
1.0
0.0
```

In the second expression, `b + c` loses the `1.0` part because it is too small relative to the magnitude of `b`. Adding `a` afterward produces 0.

Therefore, **do not arbitrarily change the grouping order of floating-point operations** assuming two expressions are always equivalent. Refactoring or optimizing expressions can alter floating-point results.

### 2.4. Summing Many Values: Error Compensation Technique

When needing to sum a large number of floating-point values, Kahan's algorithm (*compensated summation*) can reduce some errors caused by losing small parts:

```java
static double kahanSum(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;

    for (double value : values) {
        double adjusted = value - compensation;
        double next = sum + adjusted;
        compensation = (next - sum) - adjusted;
        sum = next;
    }

    return sum;
}
```

The `compensation` variable tracks the error lost during the previous addition to compensate in the next step. This technique is useful for certain accumulations, though it **does not turn `double` into an exact number** and does not replace choosing an algorithm suited to the data.

## 3. Multiplication: Results May Require More Bits Than Can Be Stored

Multiplying two finitely representable numbers can produce a result requiring more significand bits than the target type can hold. The result must be rounded.

Example:

```java
public class MultiplicationPrecision {
    public static void main(String[] args) {
        double result = 0.1 * 0.1;
        System.out.printf("%.18f%n", result);
    }
}
```

Typical displayed output is:

```text
0.010000000000000002
```

The mathematical value is \(0.1 \times 0.1 = 0.01\), yet both operands were represented approximately; multiplication and the rounding step introduce further deviation.

### 3.1. Overflow (*overflow*)

If the result has a magnitude exceeding the finite range of the type, the value can become positive or negative infinity.

```java
public class FloatingOverflow {
    public static void main(String[] args) {
        double value = Double.MAX_VALUE;
        double result = value * 2.0;

        System.out.println(result);
        System.out.println(Double.isInfinite(result));
    }
}
```

Output:

```text
Infinity
true
```

For floating-point numbers, overflow normally does not throw `ArithmeticException` like integer division by 0; the result can be `Infinity`. If infinite values are invalid in your domain, check using `Double.isFinite(value)` or `Float.isFinite(value)` and handle accordingly.

### 3.2. Multiplying by Very Small Numbers and Underflow

Conversely, if the result's magnitude is too small for the representable range, the result may approach 0. This is **underflow**.

IEEE 754 has a region of subnormal numbers (*subnormal numbers*) to represent very small positive values just below the smallest normal value. While within this region, relative precision gradually decreases. If smaller than representable, the result may round to 0.

Example:

```java
public class FloatingUnderflow {
    public static void main(String[] args) {
        double smallestPositive = Double.MIN_VALUE;

        System.out.println(smallestPositive);
        System.out.println(smallestPositive / 2.0);
        System.out.println(smallestPositive / 2.0 == 0.0);
    }
}
```

`Double.MIN_VALUE` is the smallest positive non-zero value representable by `double` (a subnormal number). Dividing it by 2 can round to 0.

### 3.3. Integer Overflow and Floating-Point Overflow Differ

| Operation | Result When Exceeding Range |
| --- | --- |
| `int` or `long` addition/multiplication exceeding range | Overflows in signed integer representation; normally does not throw an exception automatically. |
| `float` or `double` exceeding finite range | Can yield `Infinity` or `-Infinity`. |
| `Math.addExact` / `Math.multiplyExact` with integers exceeding range | Throws `ArithmeticException`. |

If business logic requires detecting integer overflow, use the appropriate `Math.*Exact` methods rather than letting values wrap around silently.

## 4. Division: Repeating Decimals and Division by Zero

Many division results lack a finite binary representation. Example:

```java
public class DivisionPrecision {
    public static void main(String[] args) {
        double oneThird = 1.0 / 3.0;
        double oneTenth = 1.0 / 10.0;

        System.out.printf("%.17f%n", oneThird);
        System.out.printf("%.17f%n", oneTenth);
    }
}
```

Illustrative output:

```text
0.33333333333333330
0.10000000000000001
```

These are the nearest representable floating-point values, not infinite decimal fractions stored in full.

### 4.1. Integer Division and Floating-Point Division Behave Differently

```java
System.out.println(1 / 2);       // 0
System.out.println(1.0 / 2.0);   // 0.5
```

`1 / 2` is integer division; the fractional part is discarded. When at least one operand is floating-point, division proceeds as floating-point division and the result can retain an approximate fractional part.

### 4.2. Dividing Floating-Point Numbers by Zero

For `float` and `double`, division by zero follows floating-point rules:

```java
public class FloatingDivisionByZero {
    public static void main(String[] args) {
        System.out.println(1.0 / 0.0);
        System.out.println(-1.0 / 0.0);
        System.out.println(0.0 / 0.0);

        System.out.println(Double.isInfinite(1.0 / 0.0));
        System.out.println(Double.isNaN(0.0 / 0.0));
    }
}
```

Output:

```text
Infinity
-Infinity
NaN
true
true
```

Meanwhile, dividing an integer by zero:

```java
int result = 1 / 0; // Throws ArithmeticException at runtime.
```

Do not apply integer division rules to floating-point division.

### 4.3. NaN and Infinity Affect Comparisons

`NaN` (*Not a Number*) indicates a result that is not a finite real number, such as `0.0 / 0.0`. Comparison operators have special behavior:

```java
double value = Double.NaN;

System.out.println(value == value); // false
System.out.println(value != value); // true
System.out.println(value < 1.0);    // false
System.out.println(value > 1.0);    // false
System.out.println(Double.isNaN(value)); // true
```

Therefore, do not check for NaN using `value == Double.NaN`. Use `Double.isNaN(value)` or `Float.isNaN(value)`.

If you need to reject both infinity and NaN:

```java
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Value must be finite");
}
```

## 5. Signed Zero in Floating-Point

IEEE 754 has both `+0.0` and `-0.0`. In standard Java comparisons:

```java
System.out.println(+0.0 == -0.0); // true
```

However, the sign of zero can affect certain calculations:

```java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

Consequently, if an application needs to distinguish the two forms of zero, it cannot rely solely on the `==` operator. You can use `Double.doubleToRawLongBits(value)` or `Double.compare(a, b)` depending on the comparison goal.

In most general business logic, the two zeros are treated as equal. Yet in some scientific, geometric, or sign-sensitive calculations, the sign of zero can carry meaningful information.

## 6. Why Should You Avoid Comparing Floating-Point Results with `==`?

If two values are computed via different sequences of operations, rounding errors can cause them to diverge even if mathematically you expect them to be equal.

Example:

```java
double a = 0.1 + 0.2;
double b = 0.3;

System.out.println(a == b); // false
```

A common approach is comparing with a **tolerance** (*tolerance*):

\[
|a-b| \le \varepsilon
\]

Where \(\varepsilon\) is the maximum error the application accepts.

### 6.1. Absolute Tolerance

```java
static boolean nearlyEqualAbsolute(
        double a, double b, double tolerance) {
    if (a == b) {
        return true;
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    return Math.abs(a - b) <= tolerance;
}
```

Example:

```java
double a = 0.1 + 0.2;
double b = 0.3;

System.out.println(nearlyEqualAbsolute(a, b, 1e-12)); // true
```

Absolute tolerance is suitable when the data domain has a relatively stable scale, such as coordinates in meters within a known range.

### 6.2. Relative Tolerance Combined with Absolute Tolerance

If data magnitudes vary widely, using only an absolute tolerance may be inappropriate. You can combine them:

\[
|a-b| \le \max(\varepsilon_{abs},
              \varepsilon_{rel}\times\max(|a|,|b|))
\]

Example:

```java
static boolean nearlyEqual(
        double a,
        double b,
        double absoluteTolerance,
        double relativeTolerance) {

    if (absoluteTolerance < 0 || relativeTolerance < 0) {
        throw new IllegalArgumentException("Tolerance must be non-negative");
    }

    if (a == b) {
        return true; // Includes two signed zeros and identical infinities.
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    double tolerance = Math.max(
            absoluteTolerance,
            relativeTolerance * scale);

    return difference <= tolerance;
}
```

No single `epsilon` fits every problem. Tolerance must derive from units, magnitude, input precision, and business requirements. Picking an arbitrary constant and using it for every comparison can mask bugs or reject valid results.

### 6.3. When Is Exact Comparison Still Appropriate?

`==` remains appropriate in certain cases:

- Comparing sentinel values or constants intentionally designed by the application.
- Not suitable for checking `NaN`; `isNaN` must be used.
- Comparing values copied intact without undergoing arithmetic.
- Comparing integers or data types that have exact representations within the value range.

For computed floating-point numbers, clearly define what "equal" means in the problem instead of defaulting to `==`.

## 7. `BigDecimal`: When Exact Decimal Arithmetic Is Needed

`BigDecimal` belongs to `java.math` and represents decimal numbers using an arbitrary-length unscaled integer combined with a scale. It is suitable for problems where decimal rules and rounding must be controlled, such as:

- Money and invoices.
- Taxes, discounts, and interest rates under business rules.
- Measured values or ratios requiring a specific number of decimal digits.
- Data interchange where decimal representation must remain stable.

### 7.1. Creating BigDecimal from a String

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
```

The string `"0.1"` represents the exact decimal 0.1. `BigDecimal` addition is exact unless rounding is requested via `MathContext`.

### 7.2. Why Should You Avoid new BigDecimal(double)?

Do not write:

```java
BigDecimal value = new BigDecimal(0.1);
System.out.println(value);
```

Because `0.1` has already been represented approximately as a `double` before being passed to the constructor. `BigDecimal(double)` creates the exact decimal value corresponding to that binary `double` value, so the result has many digits:

```text
0.1000000000000000055511151231257827021181583404541015625
```

Prefer:

```java
new BigDecimal("0.1")
```

Or when you already have a `double` value and want to convert using the canonical decimal string produced by `Double.toString`:

```java
BigDecimal.valueOf(0.1)
```

`BigDecimal.valueOf(double)` is generally preferable to `new BigDecimal(double)` in this case, but it **cannot recover precision lost earlier** if the `double` is the result of multiple error-prone calculations.

### 7.3. Addition, Subtraction, and Multiplication

```java
import java.math.BigDecimal;

BigDecimal price = new BigDecimal("19.90");
BigDecimal quantity = new BigDecimal("3");
BigDecimal discount = new BigDecimal("5.00");

BigDecimal subtotal = price.multiply(quantity);
BigDecimal total = subtotal.subtract(discount);

System.out.println(subtotal); // 59.70
System.out.println(total);    // 54.70
```

Operations return new `BigDecimal` objects. `BigDecimal` is immutable, so to keep the result, you must reassign it:

```java
BigDecimal amount = new BigDecimal("10.00");
amount.add(new BigDecimal("2.00")); // Result is ignored.
amount = amount.add(new BigDecimal("2.00"));
```

### 7.4. Division and Rounding Rules

Decimal division can produce an infinite number of digits. For example, \(1/3 = 0.3333...\). Therefore:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal result = one.divide(three); // ArithmeticException
```

If the quotient has a non-terminating decimal expansion, `divide(divisor)` cannot produce a finite exact result and throws `ArithmeticException`.

You need to specify scale and `RoundingMode`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        2,
        RoundingMode.HALF_UP);

System.out.println(result); // 0.33
```

Or use `MathContext` to specify precision by **number of significant digits**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext context = new MathContext(6, RoundingMode.HALF_EVEN);
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"), context);

System.out.println(result); // 0.333333
```

Distinguish:

| Specification | Meaning |
| --- | --- |
| `divide(divisor, 2, mode)` | Result has scale 2, i.e., 2 digits after the decimal point. |
| `divide(divisor, new MathContext(6, mode))` | Result is rounded to 6 significant digits. |
| `setScale(2, mode)` | Normalizes the current value to scale 2 using the chosen rounding rule. |

### 7.5. Common Rounding Modes

`RoundingMode` provides explicit rounding rules:

| Mode | General Meaning |
| --- | --- |
| `UP` | Round away from 0 if any non-zero remainder must be dropped. |
| `DOWN` | Discard remainder toward 0. |
| `CEILING` | Round toward positive infinity. |
| `FLOOR` | Round toward negative infinity. |
| `HALF_UP` | Nearest neighbor; on a tie between two values, round away from 0. |
| `HALF_DOWN` | Nearest neighbor; on a tie, round toward 0. |
| `HALF_EVEN` | Nearest neighbor; on a tie, choose the even last digit. |
| `UNNECESSARY` | Require no rounding to occur; throw an exception if rounding is needed. |

Example:

```java
BigDecimal amount = new BigDecimal("2.345");

System.out.println(amount.setScale(2, RoundingMode.HALF_UP));   // 2.35
System.out.println(amount.setScale(2, RoundingMode.HALF_EVEN)); // 2.34
```

With `HALF_EVEN`, a tie halfway between two choices rounds toward the result with an even last digit. In this example, 2.34 has last digit 4, so it is chosen.

There is no single right rounding mode for every application. Apply rules according to business contracts, accounting standards, or system requirements.

### 7.6. equals and compareTo of BigDecimal

Two `BigDecimal` values with the same numeric value but different scales may not be equal under `equals`:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));      // false
System.out.println(a.compareTo(b));   // 0
```

- `equals` considers both value and scale.
- `compareTo` compares numeric value; returns 0 when two numbers are numerically equal.

When checking whether two monetary amounts have the same value, `compareTo(...) == 0` is usually more appropriate than `equals` when scales may differ. However, if scale is part of the data contract, you must preserve that distinction intentionally.

## 8. Choosing Data Types Based on the Problem

| Need | Usually Appropriate Choice | Notes |
| --- | --- | --- |
| Scientific computation, graphics, simulation, coordinates | `double` | Accept floating-point error and define tolerances. |
| Floating-point data needing memory savings or API compatibility requiring float | `float` | Lower precision than `double`. |
| Money, invoices, decimal ratios with clear rules | `BigDecimal` | Use strings when constructing from decimal data; specify scale and rounding mode. |
| Integer quantities, smallest monetary units | `long` | Check for overflow risk; `Math.*Exact` can be used. |
| Integers exceeding `long` range | `BigInteger` | Suitable for large integers depending on performance needs. |

### 8.1. Using long to Store the Smallest Unit

For certain monetary systems or domains with a fixed smallest unit, integers can be stored:

```java
long amountInCents = 1_999; // 19.99 assuming a convention of 100 cents = 1 unit
long feeInCents = 250;

long totalInCents = Math.addExact(amountInCents, feeInCents);
System.out.println(totalInCents);
```

This approach avoids binary errors when operations align with the smallest unit. However, you must account for the fractional digits of each currency, how ratios/divisions are handled, and overflow checks. Not every business domain has only two decimal places.

### 8.2. Example Calculating Money with BigDecimal

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyCalculation {
    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.90");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal taxRate = new BigDecimal("0.10");

        BigDecimal subtotal = unitPrice.multiply(quantity);
        BigDecimal tax = subtotal.multiply(taxRate)
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.add(tax);

        System.out.println("Subtotal: " + subtotal);
        System.out.println("Tax:      " + tax);
        System.out.println("Total:    " + total);
    }
}
```

Output:

```text
Subtotal: 59.70
Tax:      5.97
Total:    65.67
```

In real applications, you must determine **when rounding occurs**: rounding tax per line item versus on the invoice total can produce different results. BigDecimal helps execute the chosen rule accurately, but it does not decide the business rule itself.

## 9. Java 17 and Floating-Point Operation Consistency

Java 17 uses *always-strict* floating-point semantics under JEP 306. Floating-point expressions follow the strict rules of Java/IEEE 754, rather than potentially using an extended intermediate value set as in some legacy modes.

This means:

- Results of basic operations are well-defined and consistent across compliant Java platforms.
- Starting in Java 17, the `strictfp` keyword is no longer needed to enforce strict semantics for floating-point operations.
- **Always-strict does not eliminate representation errors.** `0.1` still lacks a finite binary representation; addition and multiplication still round to the format.
- Consistency of basic operations does not mean every algorithm or math function delivers absolute accuracy in all situations.

In other words, Java 17 makes floating-point execution rules clearer and more consistent, but developers must still design appropriate representations, calculations, and comparisons.

## 10. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `0.1 + 0.2 != 0.3` | Decimals lack finite binary representations | Use tolerance for floating-point comparison or `BigDecimal` for exact decimals. |
| Repeated addition drifts | Accumulated rounding error | Consider compensated summation, addition grouping, or an appropriate representation. |
| Adding 1 to a very large number yields no change | Gap between representable `double` values exceeds 1 | Use `long`/`BigInteger` if exact integers are needed. |
| Multiplication yields `Infinity` | Overflow | Validate value range and `Double.isFinite`; design input limits. |
| Small values become 0 | Underflow and rounding | Evaluate scale, units, and required data types. |
| Dividing `double` by 0 yields `Infinity` or `NaN` | IEEE 754 rules | Validate denominator and finite results per business rules. |
| `new BigDecimal(0.1)` has many strange digits | Constructor received an already-approximated double | Create from string or use `BigDecimal.valueOf` when appropriate. |
| `BigDecimal.divide` throws `ArithmeticException` | Quotient has non-terminating decimal expansion without rounding specified | Specify scale and `RoundingMode` or `MathContext`. |
| `BigDecimal.equals` returns false for `2.0` and `2.00` | Scales differ | Use `compareTo` when comparing numeric values. |

## 11. Self-Check Questions

**1. Why does `0.1 + 0.2` not necessarily equal `0.3` in Java?**  
Because `float` and `double` use finite binary representation; 0.1 and 0.2 lack finite binary representations and must be rounded.

**2. How many bits of significand precision does `double` have?**  
53 bits, including the implicit bit for normal numbers. Typical decimal precision is about 15–17 significant digits.

**3. Why can the order of adding floating-point numbers change the result?**  
Each operation can round. If a very small number is added to a very large number first, the small part may be lost.

**4. What can multiplying `Double.MAX_VALUE` by 2 produce?**  
`Infinity` due to overflow, rather than automatically throwing `ArithmeticException`.

**5. How do `1.0 / 0.0` and `1 / 0` differ?**  
Floating-point division returns infinity; integer division by 0 throws `ArithmeticException`.

**6. Should you compare two double calculation results using `==`?**  
You should not do so by default for computed results. Choose a tolerance suited to the problem domain or use an exact representation if needed.

**7. Which type should be preferred when calculating money?**  
Typically `BigDecimal` with specified scale/rounding rules, or integers in the smallest unit if appropriate for the business model.

**8. Why does `new BigDecimal(0.1)` not create the exact decimal `0.1`?**  
Because `0.1` is converted into an approximate double value before the constructor receives it. Use `new BigDecimal("0.1")` to create the exact intended decimal value.

**9. What does `BigDecimal.divide` require when the result is a non-terminating decimal?**  
Specify scale and `RoundingMode`, or a `MathContext`, to define precision and rounding.

**10. Does Java 17 still need `strictfp` to ensure basic operations follow strict semantics?**  
No. Java 17 applies always-strict semantics for floating-point; this does not remove inherent representation errors.

## Official References

- [Java Language Specification, Java SE 17 — `4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): formats, ranges, and values of `float`/`double`.
- [Java Language Specification, Java SE 17 — `15.4 FP-strict Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): evaluation rules for floating-point expressions.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): always-strict floating-point semantics starting in Java 17.
- [Java SE 17 API — `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): exact decimal numbers, operations, scale, `MathContext`, and rounding.
- [Java SE 17 API — `java.math.RoundingMode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): rounding rules.
- [Java SE 17 API — `java.lang.Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): constants, finiteness checks, NaN, infinity, and bit conversions.
