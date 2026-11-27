# Always-Strict Floating-Point Semantics Since Java 17

## 1. Why Does Java 17 Re-emphasize Floating-Point Semantics?

Java has two primitive floating-point types:

- `float`: represents single-precision floating-point numbers, commonly known as binary32.
- `double`: represents double-precision floating-point numbers, commonly known as binary64.

Operations on `float` and `double` follow Java's floating-point arithmetic rules and IEEE 754. However, during a historical period of Java, the language allowed **certain non-strict floating-point expressions** to use an extended-exponent value set for intermediate results on platforms with hardware support. This could cause the same sequence of operations to produce different intermediate results across platforms.

Starting in **Java 17**, always-strict floating-point semantics apply to all floating-point expressions. This change is described in **JEP 306 — Restore Always-Strict Floating-Point Semantics**.

What needs to be understood accurately:

- Java 17 gives basic floating-point operations consistent evaluation rules, regardless of whether a method or class is declared `strictfp`.
- Intermediate results are evaluated according to the corresponding `float` or `double` value set, rather than using an extended-exponent value set as in some historical cases.
- This change **does not turn floating-point numbers into exact decimal numbers**.
- Representation errors, rounding, overflow, underflow, `NaN`, infinity, and signed zero still exist.
- Mathematical functions such as `Math.sin()` and `Math.log()` have their own contracts; you should not infer that JEP 306 makes every library function produce bit-for-bit identical results on every platform.

This is important knowledge when reading legacy code, upgrading the JDK, designing scientific/financial calculations, and analyzing result differences across environments.

## 2. Floating-Point Numbers in Java: `float` and `double`

### 2.1. Two Primitive Floating-Point Types

| Type | IEEE 754 Format | Width | Significand Precision | Common Uses |
|---|---|---:|---:|---|
| `float` | binary32 | 32 bits | 24 bits, including the implicit bit for normal numbers | Graphics data, large numeric datasets needing memory savings, protocols requiring float |
| `double` | binary64 | 64 bits | 53 bits, including the implicit bit for normal numbers | General floating-point computation, simulation, measurement |

A floating-point literal without a suffix normally has type `double`. To specify `float`, add the suffix `f` or `F`:

~~~java
float ratio = 0.25f;
double distance = 12.75;
double scientific = 6.022e23;
~~~

If you write:

~~~java
float ratio = 0.25; // Invalid without casting or adding the f suffix
~~~

then the literal `0.25` has type `double` and does not automatically narrow to `float`. Write `0.25f` or cast intentionally.

### 2.2. Conceptual Structure of IEEE 754

A binary32 or binary64 value consists of:

- **Sign bit:** the sign of the number.
- **Exponent:** an exponent encoded in biased form (biased exponent).
- **Fraction/significand:** the significant bits of the mantissa/significand.

A normal number is commonly understood in the form:

\[
x = (-1)^s \times 1.f \times 2^{e-bias}
\]

Where `s` is the sign bit, `f` is the fraction part, and `e` is the encoded exponent. This formula helps illustrate why a decimal number cannot always be represented exactly in binary.

Not every value is a normal number. IEEE 754 also includes:

- **Subnormal numbers:** represent very small numbers near 0 with gradually decreasing precision.
- **Positive/negative infinity:** results exceeding the finite range or from special operations.
- **NaN (Not a Number):** represents a result that is not a normal real number.
- **Positive zero and negative zero:** two zero representations with different sign bits.

Java provides `Float` and `Double` with constants and methods to identify these cases.

### 2.3. Not Every Decimal Number Has a Finite Binary Representation

A familiar example:

~~~java
double value = 0.1 + 0.2;
System.out.println(value);          // typically prints 0.30000000000000004
System.out.println(value == 0.3);   // false
~~~

The cause is not that Java 17 adds incorrectly. The values `0.1`, `0.2`, and `0.3` do not have exact finite binary representations in binary64. When converting from decimal literals to `double`, each value is rounded to the nearest binary64 value. The subsequent addition follows floating-point arithmetic rules, and its result is also rounded.

**Strict semantics guarantee consistent evaluation rules; they do not eliminate errors inherent to the format.**

## 3. Strict Floating-Point Semantics Before and From Java 17

### 3.1. Historical Context

In early versions of Java, floating-point expressions were evaluated using strict semantics. Starting in Java 1.2, Java allowed certain non-strict expressions to use an *extended-exponent value set* where supported by the platform.

An extended-exponent value set keeps the corresponding significand precision while allowing a wider exponent range than standard `float` or `double`. This could reduce temporary overflow/underflow in an intermediate calculation, but it also created the possibility of different results across platforms.

From Java 1.2 until before Java 17:

- Expressions in a strict context had to follow the standard value set.
- The `strictfp` keyword could be used to require strict semantics for a class, interface, or method according to that version's rules.
- Non-strict expressions could be evaluated with an extended value set in some environments.

Starting in Java 17:

- All floating-point expressions are strict.
- There is no longer an execution difference between strict and non-strict contexts for floating-point expressions.
- `strictfp` is no longer needed to achieve strict semantics; the keyword is retained for source compatibility with legacy code, but it no longer makes any behavioral difference.

### 3.2. Why Did Non-Strict Semantics Exist?

Some older processors, particularly architectures using floating-point registers with a wider exponent range than the `double` format stored in memory, could keep intermediate results in registers with a wider range. This sometimes improved practical accuracy or avoided temporary overflow.

However, it also meant:

- Results depended on the CPU architecture and how the JVM used registers.
- Storing an intermediate variable to memory could round it to `double`, whereas keeping it in a register could preserve an extended value.
- The same piece of code could produce different results when changing platforms or optimization strategies.

JEP 306 chose consistency and predictability as the default across all modern platforms.

### 3.3. Practical Implications of the Change

With Java 17, developers do not need to annotate every class or method to require `float`/`double` operations to follow strict semantics. Source code can express computation intent without depending on where `strictfp` is placed.

This is useful for:

- **Reproducibility of basic operations:** the same inputs and the same sequence of basic operations have deterministic rounding rules.
- **Cross-environment portability:** reduces discrepancies caused by extended-exponent evaluation.
- **Simpler code reading:** no need to decide where `strictfp` is required.
- **Maintaining legacy code:** understanding why `strictfp` appears and why it is no longer necessary when compiling/running on Java 17.

You should not assume that every Java 17 application will automatically produce identical results for every numeric task on every machine. Native libraries, mathematical functions, parallel algorithms, operation ordering, input data, and other non-deterministic sources can still affect the overall result.

## 4. `strictfp` in Java 17

### 4.1. Before Java 17, What Was `strictfp` Used For?

Before Java 17, `strictfp` was used to require floating-point expressions in the corresponding scope to use strict semantics. Historical example:

~~~java
public strictfp class LegacyCalculator {
    public static double calculate(double a, double b, double c) {
        return a * b + c;
    }
}
~~~

Or on a method:

~~~java
public class LegacyCalculator {
    public strictfp double calculate(double a, double b) {
        return a / b;
    }
}
~~~

The goal was to avoid results that depended on the extended value set of non-strict expressions on supported platforms.

### 4.2. Starting in Java 17, `strictfp` No Longer Changes Semantics

Starting in Java 17, all floating-point expressions are already strict. Therefore:

~~~java
public class Calculator {
    public double calculate(double a, double b, double c) {
        return a * b + c;
    }
}
~~~

already has strict semantics without needing the modifier.

Code containing `strictfp` is still accepted in Java 17 for source compatibility, but the modifier no longer makes any difference in how floating-point expressions are evaluated. The `javac` compiler may emit a warning for this modifier:

~~~text
as of release 17, all floating-point expressions are evaluated strictly
and 'strictfp' is not required
~~~

The warning message wording may vary slightly depending on the JDK/compiler version.

### 4.3. Should You Remove `strictfp` from the Codebase?

If a project sets Java 17 as its baseline, you can consider removing redundant modifiers for cleaner code. However:

- This is a code cleanup change, not a prerequisite for operations to be strict on Java 17.
- If the same source tree still needs to compile/run on older JDKs, you must consider the actual baseline and compatibility targets.
- Do not remove them in bulk without understanding the project's build configuration, release target, and runtime environments.
- Do not use `strictfp` as a workaround for decimal rounding errors; it does not make `0.1 + 0.2` equal exactly `0.3`.

## 5. How Does Java 17 Evaluate Floating-Point Operations?

### 5.1. Basic Operations

Common floating-point operations:

- Addition: `+`
- Subtraction: `-`
- Multiplication: `*`
- Division: `/`
- Remainder: `%`
- Negation: unary `-`
- Numeric type conversions: casts and numeric promotion rules

With Java 17, expressions containing `float`/`double` are evaluated under strict semantics. Intermediate values are not arbitrarily kept in an extended-exponent value set as under historical non-strict rules.

Example:

~~~java
double a = 1.0;
double b = 3.0;
double result = a / b;

System.out.println(result);
~~~

The result is the nearest binary64 value according to the division rounding rule. No finite `double` represents (1/3) exactly, so the result remains an approximation.

### 5.2. Rounding After Calculation Steps

Suppose:

~~~java
double a = 1.0;
double b = 1.0 + Math.scalb(1.0, -27);
double c = 1.0 - Math.scalb(1.0, -27);

double separate = b * c - a;
double fused = Math.fma(b, c, -a);
~~~

The calculation `b * c - a` performs a multiplication followed by a subtraction. Under strict semantics, the multiplication result is rounded to the `double` format before performing the subsequent subtraction.

`Math.fma(b, c, -a)` represents a **fused multiply-add** operation: computing the product and sum as a single combined operation, rounding only once at the final result. Therefore, the result of `Math.fma` can differ from `b * c + (-a)`, even though the mathematical formulas look identical on the surface.

FMA is an operation requested explicitly through the API; strict semantics do not mean the JVM is free to replace every `a * b + c` sequence with FMA, because doing so could change rounding outcomes.

### 5.3. Example Demonstrating Two Roundings vs. One Rounding

~~~java
public class FmaExample {
    public static void main(String[] args) {
        double a = 1.0 + Math.scalb(1.0, -27);
        double b = 1.0 - Math.scalb(1.0, -27);
        double c = -1.0;

        double separate = a * b + c;
        double fused = Math.fma(a, b, c);

        System.out.println("Separate: " + separate);
        System.out.println("Fused:    " + fused);
    }
}
~~~

With the values above, the exact product of the two operands is (1 - 2^{-54}). The separate multiplication is rounded to `1.0` in binary64; subtracting `1.0` then yields `0.0`. FMA retains the exact product internally within the combined operation before rounding, thus producing a non-zero result.

This is not a bug in strict semantics. The two snippets **define two different sequences of operations** with respect to rounding. Choose FMA when the algorithm requires fused behavior and has been designed and tested for it.

## 6. Strict Does Not Mean Absolutely Exact

### 6.1. Representation Error

~~~java
double x = 0.1;
System.out.printf("%.20f%n", x);
~~~

The displayed value reveals a binary approximation. `double` has about 15–17 significant decimal digits in many cases, but not every decimal number is represented exactly.

### 6.2. Accumulated Error

~~~java
double sum = 0.0;
for (int i = 0; i < 10_000; i++) {
    sum += 0.1;
}
System.out.println(sum);
~~~

Each addition may round; small errors can accumulate. Strict semantics ensure each step is evaluated consistently, but they do not eliminate algorithmic error.

When adding many numbers with large differences in magnitude, the order of addition can affect the result. If high accuracy is required, consider compensated summation algorithms (such as Kahan summation), intentionally changing the addition order, or using an appropriate numeric type.

### 6.3. Overflow and Underflow

~~~java
double huge = Double.MAX_VALUE;
double overflow = huge * 2.0;

double tiny = Double.MIN_VALUE;
double underflow = tiny / 2.0;

System.out.println(overflow);  // Infinity
System.out.println(underflow); // May round to 0.0
~~~

`Double.MAX_VALUE` is the largest finite `double` value; multiplying beyond the range produces infinity. `Double.MIN_VALUE` is the smallest positive non-zero subnormal `double` value, not the smallest negative number and not the smallest magnitude of a normal number. Dividing it by 2 may round to zero.

Always check if an algorithm cannot accept non-finite results:

~~~java
if (!Double.isFinite(result)) {
    throw new ArithmeticException("Result is not finite");
}
~~~

### 6.4. NaN and Infinity

Java provides:

~~~java
double notANumber = Double.NaN;
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;

System.out.println(Double.isNaN(notANumber));       // true
System.out.println(Double.isInfinite(positiveInfinity)); // true
System.out.println(Double.isFinite(1.25));          // true
~~~

Some rules to remember:

- `NaN == NaN` is `false`.
- `NaN != NaN` is `true`.
- Comparisons `<`, `<=`, `>`, `>=` with NaN are all `false`.
- `Double.isNaN(value)` is the explicit way to check for NaN.
- `Double.isFinite(value)` returns false for NaN and both infinities.
- Operations producing infinity or NaN still follow IEEE 754 rules; strictness does not automatically turn them into exceptions.

Example:

~~~java
double invalid = 0.0 / 0.0;
double infinity = 1.0 / 0.0;

System.out.println(Double.isNaN(invalid)); // true
System.out.println(Double.isInfinite(infinity)); // true
~~~

You should not rely on `value == Double.NaN` to check for NaN.

### 6.5. Positive Zero and Negative Zero

IEEE 754 has both `+0.0` and `-0.0`:

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);            // Infinity
System.out.println(1.0 / negativeZero);            // -Infinity
System.out.println(Double.compare(negativeZero, positiveZero)); // -1
~~~

Comparison with the `==` operator treats these two zeros as equal, but the sign of zero can affect the result of subsequent operations. `Double.compare` distinguishes `-0.0` and `+0.0` according to its defined ordering.

This is an important detail when dealing with geometric algorithms, scientific computing, or directional calculations.

## 7. Strict Operations vs. Functions in `Math`/`StrictMath`

### 7.1. Do Not Equate Basic Operations with Mathematical Functions

JEP 306 addresses **floating-point expression evaluation semantics**. That does not mean every method in `Math` becomes a strict operation like `+`, `*`, or `/`.

For example:

- `Math.sqrt(x)`
- `Math.sin(x)`
- `Math.log(x)`
- `Math.pow(x, y)`

are defined by their own API contracts. These methods have accuracy and result-property requirements, but `Math` may use platform-optimized implementations within the bounds permitted by the specification.

### 7.2. When to Use `Math`, When to Consider `StrictMath`?

| API | Purpose |
|---|---|
| `Math` | High-performance math functions whose implementations may leverage platform optimizations within API-specified accuracy bounds |
| `StrictMath` | Functions specified to produce consistent results across platforms using defined algorithms (historically fdlibm-based) |
| `Math.fma` | Explicit fused multiply-add operation, single rounding for the combined operation |

If the requirement is that **math function results must be consistently reproducible across multiple platforms**, consider `StrictMath` and the specification of the particular method. If the requirement is performance and accuracy within the API bounds, `Math` is typically the standard choice.

Do not replace all `Math` calls with `StrictMath` out of habit. Base the decision on the application's accuracy contract, reproducibility needs, and performance requirements.

### 7.3. An Application Can Still Be Non-Deterministic Even on Java 17

Sources of differences can come from:

- Different addition/multiplication ordering in parallel algorithms.
- Different input data or different input ordering.
- Math functions whose contracts permit differing implementations.
- Native code or external non-JVM libraries.
- Using `float` in one place and `double` in another.
- Rounding at type-conversion or serialization/deserialization boundaries.

Strict semantics address an important source of inconsistency in basic operations; they do not replace deterministic design for the entire pipeline.

## 8. When Should You Avoid `float`/`double` for Money?

### 8.1. Binary Floating Point Does Not Represent Every Decimal Number Exactly

Monetary values typically need to adhere to the smallest currency unit, rounding rules, and number of decimal places for the currency. `double` is suitable for many scientific calculations, but it does not automatically guarantee exact financial decimal arithmetic according to business rules.

Example:

~~~java
double price = 0.1;
double quantity = 3;
double total = price * quantity;

System.out.println(total); // May be an approximate value
~~~

### 8.2. Use `BigDecimal` When Exact Decimal Arithmetic Is Contractually Required

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal unitPrice = new BigDecimal("0.10");
BigDecimal quantity = new BigDecimal("3");

BigDecimal total = unitPrice.multiply(quantity);
BigDecimal rounded = total.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 0.30
~~~

You should initialize `BigDecimal` from a **decimal string** or from an integer source with clear meaning:

~~~java
BigDecimal correct = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal convenient = BigDecimal.valueOf(0.1);
~~~

- `new BigDecimal("0.1")` represents the exact decimal value 0.1.
- `new BigDecimal(0.1)` converts the existing binary64 value into the exact decimal value of that binary representation, which typically contains many unexpected digits.
- `BigDecimal.valueOf(0.1)` uses the canonical decimal representation from `Double.toString`, which is generally more convenient if the initial input is already a `double`. However, it is best not to pass through `double` if the source data is inherently exact decimal values.

`BigDecimal` is not a primitive type and has higher overhead than `double`; use it when the business contract requires exact decimal arithmetic and clear scale/rounding rules.

### 8.3. Use Integers for the Smallest Unit When Appropriate

Another option is storing money as integers in the smallest unit:

~~~java
long amountInCents = 1_250_000L;
long taxInCents = 100_000L;
long totalInCents = Math.addExact(amountInCents, taxInCents);
~~~

This approach avoids binary floating-point errors when all values can be represented in a fixed smallest unit. Primitive overflow must be controlled; methods like `Math.addExact` and `Math.multiplyExact` can detect overflow.

## 9. Testing and Debugging Floating-Point Calculations

### 9.1. Avoid Mechanical Exact Equality Comparisons

For approximate results, instead of:

~~~java
if (actual == expected) {
    // ...
}
~~~

you can use an allowed tolerance:

~~~java
static boolean nearlyEqual(double actual, double expected, double epsilon) {
    return Math.abs(actual - expected) <= epsilon;
}
~~~

However, `epsilon` must fit the **scale and value domain**. A single absolute epsilon is not appropriate for every problem, especially when values are near 0 or differ greatly in magnitude.

A comparison combining absolute and relative tolerance:

~~~java
static boolean nearlyEqual(
        double actual,
        double expected,
        double absoluteTolerance,
        double relativeTolerance
) {
    if (Double.doubleToLongBits(actual) ==
            Double.doubleToLongBits(expected)) {
        return true;
    }

    if (!Double.isFinite(actual) || !Double.isFinite(expected)) {
        return false;
    }

    double difference = Math.abs(actual - expected);
    double scale = Math.max(Math.abs(actual), Math.abs(expected));

    return difference <= Math.max(
            absoluteTolerance,
            relativeTolerance * scale
    );
}
~~~

This is only a utility pattern; tolerances must be chosen based on algorithmic error and units of measurement. If you need to distinguish `+0.0` from `-0.0`, or handle NaN/infinity under specific rules, you need to add an explicit policy.

### 9.2. Print Values and Bit Representations When Investigating

~~~java
double value = 0.1;

System.out.println(value);
System.out.println(Double.toHexString(value));
System.out.println(Long.toBinaryString(
        Double.doubleToRawLongBits(value)
));
~~~

`Double.toHexString` is useful for inspecting the binary64 representation in hexadecimal format. `doubleToRawLongBits` provides the bit pattern, including any NaN payload if low-level inspection is needed.

For `float`, corresponding APIs exist in `Float`, such as `Float.toHexString` and `Float.floatToRawIntBits`.

### 9.3. Testing Edge Cases

A floating-point test suite should consider:

- Normal finite values.
- `0.0` and `-0.0`.
- `Float.MIN_VALUE`/`Double.MIN_VALUE` and subnormal values.
- `Float.MAX_VALUE`/`Double.MAX_VALUE`.
- Overflow and underflow.
- `NaN`, positive infinity, negative infinity.
- Values near rounding thresholds.
- Inputs differing in magnitude by many orders.

Java 17 ensures consistent semantics for basic operations, but tests still need to reflect the business contract and acceptable precision.

## 10. Impact on Projects When Upgrading to Java 17

### 10.1. Auditing `strictfp` in Legacy Code

When migrating a project from Java 8 or Java 11 to Java 17, you may encounter declarations such as:

~~~java
public strictfp class ScientificService {
    public strictfp double compute(double input) {
        return input * input;
    }
}
~~~

On Java 17, these modifiers are no longer needed to require strict evaluation. You may keep them during the upgrade phase to minimize diffs, then consider removing them in a separate cleanup change if the project baseline is Java 17.

Do not conclude that all old and new floating-point results are guaranteed to be identical. If the code previously ran on a platform/JVM that used extended-exponent evaluation in non-strict expressions, intermediate results may change when running under Java 17's always-strict semantics.

### 10.2. Evaluating Tests That Depend on Bitwise Results

If a project compares `double` results by bit pattern or exact snapshots, determine:

- Which specification are the expected results based on?
- Did the legacy code use `strictfp`?
- Which architecture did the runtime previously run on?
- Does the calculation use native libraries or `Math` methods?
- Were operation order, JIT, or dependencies changed alongside the JDK upgrade?

Only change expected values when justified by the specification or algorithm; do not update snapshots just to make tests pass.

### 10.3. No Need to Replace Every `double` Operation with `BigDecimal`

Java 17 does not require converting all `double` usage to `BigDecimal`. Categorize by contract:

| Business Domain | Usually Appropriate Choice |
|---|---|
| Graphics, simulation, statistics, measurement accepting error | `double`/`float` and suitable algorithms |
| Currency, tax, rates with specific decimal rules | `BigDecimal` or integer smallest unit |
| Integer counters, discrete quantities | `int`/`long`, consider overflow checks |
| External APIs sending decimal numbers | Identify schema, precision, scale, and parsing strategy before choosing a type |

Strict semantics solve floating-point evaluation consistency, while choosing the data type remains a domain design responsibility.

## 11. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| “Java 17 strict means there are no more floating-point errors.” | Rounding and representation errors still exist; strict only standardizes evaluation rules. |
| “`strictfp` is required to get standard results on Java 17.” | All expressions are already strict; the modifier no longer changes semantics. |
| “`strictfp` has been removed from Java syntax.” | The keyword is retained for source compatibility, though it is no longer needed. |
| “Every function in `Math` gives bit-for-bit identical results on every platform thanks to JEP 306.” | JEP 306 primarily standardizes floating-point expressions; math functions have their own API contracts. |
| “Strict allows the JVM to automatically replace `a*b+c` with FMA.” | FMA is a combined operation with a single rounding; use `Math.fma` explicitly when you want those semantics. |
| “`double` is always more accurate than `float`, so use it for money.” | `double` has higher binary precision, but still does not represent all decimal numbers exactly. |
| “Double overflow automatically throws an exception.” | Many operations produce `Infinity` or `NaN`; check explicitly if the domain does not allow them. |
| “`Double.MIN_VALUE` is the smallest negative number.” | It is the smallest positive non-zero subnormal value. |
| “NaN can be checked with `x == Double.NaN`.” | You must use `Double.isNaN(x)`. |
| “Strict semantics make the entire application deterministic.” | Algorithm order, libraries, native code, data, and math functions can still affect results. |

## 12. Practice Exercises

### Exercise 1 — Observing Representation Error

Write a program:

~~~java
double a = 0.1;
double b = 0.2;
double c = a + b;

System.out.println(c);
System.out.println(c == 0.3);
System.out.println(Double.toHexString(a));
System.out.println(Double.toHexString(b));
System.out.println(Double.toHexString(c));
~~~

Explain why Java 17 strict still yields a result not equal to exact `0.3`. Distinguish representation error from discrepancies caused by historical non-strict semantics.

### Exercise 2 — Checking `strictfp`

Declare two classes: one with `strictfp`, and one without. Compile on JDK 17 and observe any warnings (if emitted). Explain why both classes have the same floating-point evaluation semantics on Java 17 and what `strictfp` meant in older versions.

### Exercise 3 — Distinguishing Multiply-Add and FMA

Use:

~~~java
double a = 1.0 + Math.scalb(1.0, -27);
double b = 1.0 - Math.scalb(1.0, -27);
double c = -1.0;

System.out.println(a * b + c);
System.out.println(Math.fma(a, b, c));
~~~

Explain why the two results differ. Clearly indicate where rounding occurs in the separate operations and in FMA.

### Exercise 4 — Handling Non-Finite Values

Write a method that takes two `double`s, performs division, and returns the result or reports an error if:

- The denominator equals positive/negative zero.
- The result is not finite.
- Inputs are NaN or infinity.

Define a policy for signed zero and NaN. Do not rely solely on division to infer all valid input cases.

### Exercise 5 — Choosing a Type for a Pricing Problem

An order has unit price 0.10 and quantity 3. Write two approaches:

1. Calculate using `double` and observe the result.
2. Calculate using `BigDecimal` constructed from a string, then apply appropriate scale/rounding.

Explain which representation accurately reflects the monetary contract and why Java 17 strict does not make the first approach decimally exact.

### Exercise 6 — Summing with Accumulated Error

Compare the sum of 10,000 additions of `0.1` using:

- Sequential addition with `double`.
- A compensated summation algorithm such as Kahan summation.
- `BigDecimal` when exact decimal addition is required.

Contrast numeric error benefits with performance cost and data type choices.

## 13. Self-Check Questions

1. Which IEEE 754 formats do `float` and `double` correspond to?
2. What role did the extended-exponent value set play before Java 17?
3. What does JEP 306 change in floating-point semantics?
4. Why do floating-point expressions in Java 17 not need `strictfp`?
5. Has the `strictfp` keyword been completely removed from the syntax?
6. Does strict semantics make `0.1 + 0.2 == 0.3` evaluate to true?
7. Why can `Math.fma(a, b, c)` differ from `a * b + c`?
8. What is the difference between basic operations and `Math.sin`/`StrictMath.sin`?
9. How do overflow and underflow of `double` typically manifest?
10. How do you check for NaN, infinity, and finite values?
11. Why is `+0.0 == -0.0` true, yet dividing by each value can produce infinities of opposite signs?
12. When should you use `BigDecimal` or integers instead of `double`?
13. Does JEP 306 guarantee an entire application is deterministic across all systems?
14. When upgrading to Java 17, which calculations or tests should be checked for dependence on legacy floating-point semantics?

## 14. References

- [OpenJDK JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): describes the change standardized in Java 17 and the historical background of strict/non-strict floating point.
- [Java Language Specification, Java SE 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): floating-point types, formats, and values.
- [Java Language Specification, Java SE 17 — Floating-Point Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): strict semantics of floating-point expressions.
- [Java SE 17 API — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): mathematical functions, `fma`, and API contracts.
- [Java SE 17 API — StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): mathematical functions specified for consistent cross-platform results.
- [Java SE 17 API — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): constants and inspection methods for binary64 values.
- [Java SE 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): arbitrary-precision decimal arithmetic and scale/rounding rules.

Java 17 makes floating-point operations always evaluate under strict semantics, eliminating historical differences from extended-exponent evaluation. When applying this, separate **consistency of calculation rules** from **precision of formats and algorithms**: strictness does not turn binary floating point into exact decimal numbers, does not eliminate NaN/infinity, and does not automatically decide domain rounding policies.
