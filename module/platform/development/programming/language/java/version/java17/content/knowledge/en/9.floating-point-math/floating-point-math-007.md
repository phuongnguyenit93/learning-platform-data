# Math, StrictMath, and Reproducibility Requirements in Java 17

> **Topic:** Java 17  
> **Chapter:** Floating-Point Numbers  
> **Goal:** Understand floating-point operations in Java 17, distinguish the roles of `Math` and `StrictMath`, choose the right API when results must be reproducible across environments, and recognize the limits of reproducibility in real-world applications.

## 1. Why Can the Same Formula Produce Different Results?

In Java, `double` and `float` represent real numbers using binary floating-point format. Many familiar decimal numbers cannot be represented exactly with a finite number of bits. Example:

```java
double value = 0.1 + 0.2;
System.out.println(value);
```

Typical output:

```text
0.30000000000000004
```

This is not a Java-specific bug. `0.1` and `0.2` are approximated in binary; addition operates on those floating-point values, so the result is not necessarily the exact decimal `0.3`.

Beyond representation error, a program may also care about whether **the same inputs produce the exact same numeric results** when run across different machines, operating systems, or runtimes. Java provides two distinct groups of mechanisms:

- **Language floating-point operation semantics:** specifies how `+`, `-`, `*`, `/`, type conversions, and `float`/`double` expressions are evaluated.
- **Library mathematical functions:** such as `sin`, `cos`, `log`, `pow`, `sqrt`, and `exp`, provided by `Math` and `StrictMath`.

Starting in Java 17, the language's floating-point operations returned to **always-strict** mode. However, that does not mean every function in `Math` must return the exact same bits on every platform. When strict cross-environment reproducibility of math functions is needed, you must also understand the contract of `StrictMath`.

## 2. Three Concepts Not to Confuse

| Concept | Scope | Meaning |
|---|---|---|
| IEEE 754 and `float`/`double` types | Number representation and operations | Defines how finite numbers, infinity, NaN, signed zero, and rounding rules are encoded |
| Java 17 always-strict floating-point | Language floating-point expressions | No longer any platform-dependent extended evaluation mode; expression results follow Java floating-point semantics |
| `Math` / `StrictMath` | Library mathematical functions | Provides mathematical functions; guarantees on accuracy and reproducibility depend on each class/method specification |

**Important point:** `strictfp` and `StrictMath` are not the same concept.

- `strictfp` is a modifier related to floating-point operation semantics for a class, interface, or method. Since Java 17, always-strict semantics apply by default, so this modifier no longer makes any practical difference.
- `StrictMath` is a library class containing mathematical methods. It remains relevant when a program needs results from functions specified with algorithms designed for cross-platform reproducibility.

For example, putting `strictfp` on a method that calls `Math.sin(x)` does not turn `Math.sin` into `StrictMath.sin`. If the requirement is trigonometric results under a reproducibility contract, you must choose the corresponding API.

## 3. Floating-Point Operations in Java 17: Always-Strict

### 3.1. Before Java 17 and Since Java 17

In earlier versions of Java, default semantics allowed some intermediate calculations to use an extended value set on supporting hardware. The `strictfp` modifier was used when a program wanted to restrict calculations to strict semantics.

JEP 306 restored **always-strict** semantics starting in Java 17:

- All floating-point expressions in Java 17 use strict semantics per the specification.
- There is no need to add `strictfp` to require `float`/`double` calculations to behave consistently according to the language.
- `strictfp` may still appear in source code for compatibility, but it no longer changes calculation behavior; the compiler may warn that this modifier is unnecessary.

Example:

```java
public class FloatingPointDemo {
    static double calculate(double a, double b, double c) {
        return a * b + c;
    }

    public static void main(String[] args) {
        System.out.println(calculate(0.1, 0.2, 0.3));
    }
}
```

In Java 17, the expression `a * b + c` is evaluated under Java's standard floating-point semantics. The program does not need `strictfp` on the class or method to eliminate extended intermediate evaluations.

### 3.2. Always-Strict Does Not Make Decimal Numbers Absolutely Exact

Always-strict ensures calculation semantics per the specification, **it does not eliminate binary representation error**:

```java
double x = 0.1;
double y = 0.2;

System.out.println(x + y);             // 0.30000000000000004
System.out.println((x + y) == 0.3);    // false
```

This result is normal behavior. Using `strictfp`, `Math`, or `StrictMath` does not turn `double` into an exact decimal type.

### 3.3. When Does `strictfp` Still Appear?

You may encounter legacy code:

```java
strictfp class Geometry {
    strictfp double area(double radius) {
        return Math.PI * radius * radius;
    }
}
```

In Java 17, `strictfp` is no longer needed to guarantee always-strict floating-point operations. During maintenance, you can remove this modifier per project policy after reviewing compatibility requirements and coding conventions. There is no need to add `strictfp` to new Java 17 classes hoping to get identical results between Intel and ARM machines.

## 4. How Do `Math` and `StrictMath` Differ?

Both are utility classes with `static` methods providing operations such as:

```java
double root = Math.sqrt(2.0);
double sine = Math.sin(Math.PI / 6);
double logarithm = Math.log(10.0);
```

Corresponding methods also exist in `StrictMath`:

```java
double root = StrictMath.sqrt(2.0);
double sine = StrictMath.sin(StrictMath.PI / 6);
double logarithm = StrictMath.log(10.0);
```

The main difference lies in **result guarantees and implementation optimization freedom**.

| Criterion | `Math` | `StrictMath` |
|---|---|---|
| Purpose | Convenient math functions, allowing platform-specific optimizations | Math functions prioritizing reproducible results per specification |
| Results of functions specified for reproducibility | Not every method is guaranteed to be bit-for-bit identical across all platforms | Methods specified using fdlibm algorithms must return corresponding identical results across compliant implementations |
| Optimization | May use native libraries, hardware instructions, or runtime-optimized implementations | Functions with reproducibility requirements use the specified algorithm instead of arbitrarily picking another native implementation |
| When to consider | Performance, general computation, when bit-for-bit cross-platform equality for every function is not needed | When math function results must be strictly reproducible across environments |
| Does it eliminate floating-point error? | No | No |

`Math` is usually a good default choice for general applications. `StrictMath` is suitable when product specifications, tests, or algorithms require math function results to be reproducible across multiple platforms.

### 4.1. Why Can `Math` Produce Different Results?

A function like `sin(x)` is not simply a single basic floating-point operation. A runtime may implement it using various approximation algorithms, system libraries, or specialized instructions. Implementations must adhere to the API's accuracy requirements, yet the `Math` specification does not require every function to return the exact same bit sequence on every platform.

Therefore, two machines can:

- Receive the exact same input `double` value.
- Both run Java 17.
- Both call `Math.sin(x)`.
- Yet obtain final results differing in one or more low-order bits, within the bounds allowed by the method contract.

Do not conclude that every machine is guaranteed to differ; many runtimes may return identical results. The point to remember is that **there is no universal bit-for-bit guarantee for every `Math` function just because Java 17 has always-strict floating-point**.

### 4.2. `StrictMath` and fdlibm

`StrictMath` is designed to support program portability. For designated functions, the specification is based on algorithms from **fdlibm** (*Freely Distributable Math Library*) so Java implementations produce consistent results.

This is useful when:

- Mathematical results are persisted into data and need to be compared again on another machine.
- Nodes in a distributed system must compute the exact same algorithmic value.
- Test suites require deterministic results across multiple operating systems/architectures.
- A scientific application needs a clearly specified library function and computation behavior rather than relying on platform-specific implementations.

Do not interpret this as "every `StrictMath` method is mathematically exact". It is a **reproducibility contract for floating-point computation**, which still involves rounding error relative to true real values.

## 5. Examples of Choosing `Math` vs. `StrictMath`

### 5.1. General Computation

If a program simply needs to compute a diagonal length for display:

```java
double diagonal(double width, double height) {
    return Math.sqrt(width * width + height * height);
}
```

`Math.sqrt` has a very strict accuracy contract and is the natural choice. For other functions, review each method's specification and application requirements; not every problem needs to force all calls to `StrictMath`.

### 5.2. Requiring Reproducible Trigonometric Results

If a program needs to compute the same trigonometric value across multiple machines and wants to rely on the library's reproducibility guarantee:

```java
static double projectedX(double radius, double angle) {
    return radius * StrictMath.cos(angle);
}
```

In the project, document why `StrictMath` is chosen here. Do not switch back and forth between `Math.cos` and `StrictMath.cos` within the same pipeline without reason, as reproducibility requirements must be managed as part of the computation contract.

### 5.3. Same Function, Switching Namespace

```java
double a = Math.sin(1.2345);
double b = StrictMath.sin(1.2345);

System.out.println(a);
System.out.println(b);
System.out.println(Double.doubleToLongBits(a));
System.out.println(Double.doubleToLongBits(b));
```

Do not write tests assuming `a` and `b` must differ. An implementation may return the exact same value. What matters is the **API contract**: `StrictMath` provides the reproducibility guarantee for specified methods; `Math` allows more optimal implementations within its accuracy bounds.

## 6. Precision: ULP, Error, and Comparing Floating-Point Numbers

### 6.1. What Is a ULP?

**ULP** (*unit in the last place*) is the spacing between two adjacent representable floating-point values in the region under consideration. Specifications for math functions often express accuracy in ULPs relative to the exact mathematical result.

Conceptual examples:

- A result off by one ULP means it is one representable step away from the exact rounded value at that magnitude.
- A ULP is not a fixed constant for all values; spacing between `double` numbers changes with the exponent.
- "Within one ULP" does not mean mathematically exact, nor does it mean any application can use `==` to compare nearby results.

The `Math` and `StrictMath` APIs state accuracy and monotonicity requirements in each method's documentation and class overview. When a calculation is critical, check the specific contract of that function rather than relying solely on the class name.

### 6.2. Do Not Compare Floating-Point Numbers with `==` for Approximate Equality

Example:

```java
double a = 0.1 + 0.2;
double b = 0.3;

if (a == b) {
    System.out.println("Equal");
} else {
    System.out.println("Different");
}
```

If business rules accept a small error, you can use a threshold:

```java
static boolean nearlyEqual(double a, double b, double epsilon) {
    return Math.abs(a - b) <= epsilon;
}
```

However, `epsilon` must derive from the value domain and business requirements. A fixed threshold like `1e-9` might suit one problem while being too tight or too loose for another.

For very large or very small values, consider relative comparison:

```java
static boolean approximatelyEqual(
        double a, double b, double absoluteTolerance, double relativeTolerance) {

    if (Double.doubleToLongBits(a) == Double.doubleToLongBits(b)) {
        return true;
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= Math.max(
            absoluteTolerance,
            relativeTolerance * scale);
}
```

The function above illustrates a combined absolute/relative tolerance strategy. In real applications, pick tolerances matching units, data ranges, and NaN/infinity rules; do not copy constants without understanding requirements.

### 6.3. `NaN`, Infinity, and Signed Zero

Floating-point operations have special values:

```java
double nan = Double.NaN;
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeZero = -0.0;

System.out.println(Double.isNaN(nan));                    // true
System.out.println(Double.isInfinite(positiveInfinity)); // true
System.out.println(negativeZero == 0.0);                 // true
System.out.println(Double.doubleToRawLongBits(-0.0));
```

Rules to remember:

- `NaN == NaN` is `false`; use `Double.isNaN(value)` to check.
- `+0.0 == -0.0` is `true`, even though the two values have different sign bits.
- Floating-point division by `0.0` can produce infinity or NaN rather than throwing `ArithmeticException` like integer division.
- When verifying bit-for-bit reproducible results, define policies for NaN, signed zero, and bit canonicalization.

`Double.doubleToLongBits` canonicalizes NaN representations into a standard NaN form; `Double.doubleToRawLongBits` preserves any NaN payload bits. The two methods serve different purposes when inspecting bits.

## 7. Always-Strict Basic Operations Do Not Mean `Math` Functions Are Always Reproducible

Distinguish a basic expression:

```java
double product = a * b;
double sum = product + c;
```

from a library call:

```java
double result = Math.sin(a);
```

The expression `a * b + c` is governed by Java 17's always-strict semantics. The call `Math.sin` is also governed by the accuracy contract and optimization rights of the `Math.sin` method.

Therefore, when reading a requirement that "the same inputs must produce the same result", clarify:

1. Does the requirement apply to `+ - * /` operations or to trigonometric/logarithmic functions?
2. Do we need numeric results per Java's specification, or identical result bits on every platform?
3. Are we comparing a single function's output, or an entire workflow involving operation ordering, input data, and rounding rules?
4. Do results need to remain unchanged across library versions, algorithms, or input data?

Choosing `StrictMath` addresses the math function contract it provides, but it does not automatically make an entire application reproducible.

## 8. `Math.fma`: One Operation, One Rounding

Java provides `Math.fma(a, b, c)` (*fused multiply-add*):

```java
double result = Math.fma(a, b, c);
```

It computes the product `a * b` and adds `c` with **a single final rounding**, as defined by fused multiply-add. The standard expression:

```java
double result = a * b + c;
```

can round after the multiplication and round again after the addition. Thus the two approaches do not necessarily yield the same result bits.

Example illustrating the semantic difference:

```java
static double ordinary(double a, double b, double c) {
    return a * b + c;
}

static double fused(double a, double b, double c) {
    return Math.fma(a, b, c);
}
```

Do not arbitrarily replace one approach with the other if the result is already part of a protocol, golden-file test, or numerical model. If an algorithm requires fused multiply-add, call `Math.fma` explicitly (or `StrictMath.fma` when matching the required library contract) so the intent is clear in code.

`fma` is not a free way to "increase precision for every calculation": it changes rounding rules relative to two separate operations, and can therefore produce results different from legacy code. Use it when the algorithm calls for a fused operation or after evaluating its numerical impact.

## 9. When Exact Decimal Arithmetic Is Needed: Use `BigDecimal`

`Math` and `StrictMath` operate on floating-point types. If the business requirement is exact decimal numbers, such as money or rates needing published rounding rules, `BigDecimal` is usually the better choice.

### 9.1. Avoid Creating `BigDecimal` from `double` Literals

Avoid:

```java
BigDecimal wrong = new BigDecimal(0.1);
System.out.println(wrong);
```

This constructor receives **the approximated binary `double` value**, then represents that binary value exactly as a long decimal.

Prefer a string:

```java
BigDecimal amount = new BigDecimal("0.1");
```

Or when you genuinely have a `double` and want the short decimal value returned by `Double.toString`:

```java
BigDecimal amount = BigDecimal.valueOf(0.1);
```

For monetary data, accept input as strings or appropriate decimal types and explicitly define scale and rounding mode.

### 9.2. Specifying the Rounding Rule

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.995");
BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 20.00
```

Here, the rounding rule is an explicit part of business logic. `BigDecimal` does not decide monetary rules on its own; the program must still choose the appropriate `RoundingMode` and scale.

### 9.3. `Math.round` Does Not Replace `BigDecimal.setScale`

`Math.round(double)` returns a `long` integer according to the method's rules. It is not a general tool for rounding money to two decimal places:

```java
double amount = 19.995;
long whole = Math.round(amount);
```

If two decimal places are needed, multiplying by 100, calling `Math.round`, and dividing back can introduce representation issues and obscures the rounding policy. Use `BigDecimal` with a chosen rounding mode.

## 10. Reproducing Results Across Multiple Machines in Applications

Choosing `StrictMath` is a helpful step, yet an application's overall output depends on many other factors.

### 10.1. Fixing Inputs and Evaluation Order

For example, the sum of a set of floating-point numbers can depend on addition order due to non-associativity of floating-point addition:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double first = (a + b) + c;
double second = a + (b + c);

System.out.println(first);  // 1.0
System.out.println(second); // May be 0.0
```

In floating point, `(a + b) + c` is not guaranteed to equal `a + (b + c)`. If a sum is computed over a collection whose iteration order is unspecified, the result can vary across data sources or collection implementations.

When reproducibility is needed:

- Specify the order of input elements.
- Use an addition algorithm with a well-defined order.
- Do not rely on iteration order not guaranteed by the API.
- Consider compensated summation (*compensated summation*, such as Kahan summation) if the goal is reducing error; this algorithm does not replace fixing input order.

### 10.2. Fixing Random Number Generation

`Math.random()` is not suitable if you need to replay a computation session identically. If you want a repeatable pseudo-random sequence, use a generator with a specified algorithm and seed:

```java
import java.util.Random;

Random firstRun = new Random(12345L);
Random replay = new Random(12345L);

for (int i = 0; i < 5; i++) {
    System.out.println(firstRun.nextInt() == replay.nextInt());
}
```

With `java.util.Random`, the same seed and the same sequence of calls produce the same sequence of outputs per the class contract. However:

- If call order differs due to concurrency, values assigned to each task can differ.
- Different generators (`SplittableRandom`, generators in `java.util.random`) have different contracts/algorithms.
- Do not use `Random` for cryptographic purposes; use `SecureRandom` when a secure random source is needed, accepting that it is not meant to produce replayable sequences from a seed like simulation generators.

### 10.3. Fixing Non-Arithmetic Factors

A program can use `StrictMath` and still fail to reproduce outputs if it depends on:

- Current time, timezone, and calendar rules.
- Locale, number formatting, and decimal separators.
- Default charset when reading/writing files.
- Data ordering from databases or APIs.
- Environment variables, configuration, and library versions.
- Thread scheduling, parallel task completion order, and race conditions.
- Application algorithm version, input data, and rounding policy.

Therefore, reproducibility requires a clear **computation profile**: inputs, Java version, algorithm, libraries, data ordering, rounding rules, and output formatting.

### 10.4. Distinguishing Reproducibility Within Java vs. Across Languages

`StrictMath` helps Java implementations align results per the method's contract. It does not automatically guarantee that a program written in C, Python, JavaScript, or running on a GPU will produce the exact same result bits when calling a similarly named math function. Each language/runtime may have:

- Different data types and intermediate precisions.
- Different rounding rules.
- Different math libraries and algorithms.
- Different handling of NaN, signed zero, or exceptions.

If results must match across multiple languages, define a shared numerical protocol (type widths, rounding modes, specific functions, algorithm versions, and serialization representation), then cross-test implementations.

## 11. How to Meaningfully Test Reproducibility

### 11.1. Numeric Equality vs. Bitwise Equality

Two different checks:

```java
static boolean sameNumericValue(double a, double b) {
    return a == b;
}

static boolean sameBits(double a, double b) {
    return Double.doubleToLongBits(a) == Double.doubleToLongBits(b);
}
```

- `==` treats `+0.0` and `-0.0` as equal; NaN is unequal to itself.
- `Double.doubleToLongBits` distinguishes signed zero while canonicalizing NaN into a standard form.
- `Double.doubleToRawLongBits` inspects raw bits, including NaN payload.

Choose the check matching your requirement. Do not label a test "bit-for-bit" if it only uses `==`.

### 11.2. Printing Bits for Diagnostics

```java
static String bits(double value) {
    return String.format(
            "%016X",
            Double.doubleToLongBits(value));
}

public static void main(String[] args) {
    double value = StrictMath.sin(1.2345);
    System.out.println(value);
    System.out.println(bits(value));
}
```

The hex string makes bit-level differences visible. When comparing results across two machines, record inputs, runtime version, platform, invoked method, and any NaN normalization applied.

### 11.3. Do Not Rely Only on a Few Easy Examples

A good numerical test suite should cover:

- Normal values across multiple orders of magnitude.
- Very small/near-zero values and very large/near-overflow values.
- Negative values, signed zero, NaN, and infinity if permitted by the method.
- Domain boundary points (e.g., near extrema or asymptotes).
- Invalid inputs and the application's error-handling policy.
- Cases where ULP errors are significant to business decisions.

For math functions, distinguish testing **accuracy** from testing **reproducibility**. Identical results across machines do not prove closeness to the exact mathematical value; a small error also does not automatically prove bitwise identity across all machines.

## 12. Comprehensive Example: Coordinate Service Requiring Reproducibility

Suppose a service computes coordinates from radius and angle, with results logged and reconciled across nodes. If the specification requires trigonometric functions with reproducible results in Java, you can write:

```java
public final class CoordinateCalculator {
    private CoordinateCalculator() { }

    public record Point(double x, double y) { }

    public static Point fromPolar(double radius, double angleRadians) {
        if (!Double.isFinite(radius) || radius < 0.0) {
            throw new IllegalArgumentException("radius must be finite and >= 0");
        }
        if (!Double.isFinite(angleRadians)) {
            throw new IllegalArgumentException("angle must be finite");
        }

        double x = radius * StrictMath.cos(angleRadians);
        double y = radius * StrictMath.sin(angleRadians);
        return new Point(x, y);
    }

    public static void main(String[] args) {
        Point point = fromPolar(10.0, StrictMath.PI / 6.0);
        System.out.println(point);
    }
}
```

This design makes clear:

1. Inputs are validated before calculation.
2. `StrictMath` is explicitly selected for both trigonometric functions.
3. Multiplication remains a floating-point operation under Java 17's always-strict semantics.
4. Results are still `double`, so rounding error remains; they are not infinitely exact geometric values.
5. When reading/writing results, specify the format and serialization method rather than relying on locale or default formatting.

If the service needs to store coordinates to a fixed number of decimal places, add a quantization/rounding step according to an agreed policy. Do not use `String.format` with the default locale as a protocol format.

## 13. Choosing APIs by Requirement

| Requirement | Recommended Choice |
|---|---|
| General `double` math without bit-for-bit requirements for every function | Use `Math` and adhere to API accuracy bounds |
| Reproducible math function results per Java spec across implementations | Use the appropriate `StrictMath` methods |
| Ensure Java 17 floating-point operations do not rely on extended-exponent value sets | Guaranteed by default via always-strict; no need to add `strictfp` |
| Monetary or decimal calculations needing defined rounding | Use `BigDecimal` and appropriate `RoundingMode` |
| Compute fused multiply-add with exactly one rounding | Use `Math.fma` or corresponding API as required |
| Approximate floating-point comparison | Build tolerances based on data domain and units |
| Replay pseudo-random sequences | Choose a generator with an appropriate contract, fix seed and call order |
| Reproducibility across an entire distributed pipeline | Specify inputs, ordering, versions, algorithms, environment, and serialization |

Do not replace all `Math` usage with `StrictMath` merely because the word "Strict" sounds safer. The choice must stem from the required contract and the specific methods used.

## 14. Common Misconceptions

| Misconception | Reality |
|---|---|
| Java 17 always-strict means all `Math` calculations are bit-identical on every machine | Always-strict applies to language FP expressions; `Math` functions have their own contracts |
| `strictfp` and `StrictMath` are the same | One is a language modifier, the other is a library class |
| `StrictMath` is always mathematically exact | It provides a reproducibility contract for specified methods, yet still has floating-point error |
| `Math` is always faster than `StrictMath` | No absolute performance guarantee; depends on method, JVM, CPU, and implementation |
| Switching `Math` to `StrictMath` makes the entire application reproducible | Evaluation order, data, concurrency, randomness, rounding, and serialization can still vary |
| `double` can store every decimal number exactly | Many decimal fractions lack exact binary representations |
| `==` is good for comparing all floating-point results | Distinguish exact equality, tolerance, and bitwise equality |
| `BigDecimal(double)` recovers the original decimal number | It represents the exact approximated `double` value; use strings or `BigDecimal.valueOf` as appropriate |
| Adding `strictfp` in Java 17 makes `Math.sin` behave like `StrictMath.sin` | No; choose the library method according to your requirements |

## 15. Practice Exercises

### Exercise 1 — Distinguishing Operation Semantics and Library Functions

Given two snippets:

```java
double a = 0.1 + 0.2;
double b = Math.sin(1.0);
```

Explain which part is governed by Java 17's always-strict floating-point semantics and which part is governed by the `Math` library contract.

**Hint:** The addition in `a` is a language FP expression; the `Math.sin` call in `b` is a library function with its own accuracy/implementation specification. `strictfp` does not turn a `Math.sin` call into `StrictMath.sin`.

### Exercise 2 — Choosing a Function for a Reproducibility Requirement

An application running on multiple machine types needs to compute `sin(angle)` and persist results for comparison across Java nodes.

- Should you consider `Math.sin` or `StrictMath.sin`?
- Why is choosing `StrictMath` still not enough to guarantee the entire workflow produces identical outputs?

**Guided Answer:** Choose `StrictMath.sin` if the requirement is reproducible trigonometric function results under Java's contract. At the same time, fix inputs, evaluation order, logic version, rounding policy, NaN/signed zero handling, and serialization.

### Exercise 3 — Comparing Floating-Point Numbers

Write a method comparing two `double` numbers using an absolute tolerance, then explain why the same tolerance cannot be chosen for every value range.

**Hint:**

```java
static boolean close(double a, double b, double epsilon) {
    return Double.isFinite(a)
            && Double.isFinite(b)
            && Math.abs(a - b) <= epsilon;
}
```

This is only a simple policy; decide separately for NaN, infinity, signed zero, and magnitude ranges.

### Exercise 4 — Choosing `BigDecimal` for Money

Explain the difference between:

```java
new BigDecimal(0.1)
new BigDecimal("0.1")
BigDecimal.valueOf(0.1)
```

**Guided Answer:** The `double` constructor converts the exact stored binary value; the string constructor parses the specified decimal representation; `valueOf` uses the canonical string representation of `double`. For monetary data, prefer obtaining decimal values from an appropriate source and specifying scale/rounding mode.

### Exercise 5 — Reproducing the Sum of a Set of Numbers

Suppose a service sums values in a `HashSet<Double>`. Why does using `StrictMath` for individual calculations not automatically guarantee the final sum is identical?

**Guided Answer:** `HashSet` iteration order is not a business-guaranteed order; floating-point addition is non-associative, so addition order can change the result. You must fix data ordering and the summation algorithm.

## 16. Official Documentation for Reference

- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): floating-point semantics change starting in Java 17.
- [Java Language Specification 17 — `15.4 FP-strict Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): definition of FP-strict expressions in Java 17.
- [Java Language Specification 17 — `4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): `float`, `double` types and floating-point values.
- [Java SE 17 API — `Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): accuracy, monotonicity, implementation optimization freedom, and mathematical methods.
- [Java SE 17 API — `StrictMath`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): functions specified to support reproducible cross-platform results.
- [Java SE 17 API — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): arbitrary-precision decimal numbers and rounding rules.

**Key takeaway:** Java 17 already enforces always-strict semantics for language floating-point operations. `Math` allows implementation optimizations within its accuracy contract; `StrictMath` is the choice when reproducible math function results are needed under its specification. To reproduce an entire application, you must also control inputs, calculation order, algorithms, rounding, randomness, and data environment.
