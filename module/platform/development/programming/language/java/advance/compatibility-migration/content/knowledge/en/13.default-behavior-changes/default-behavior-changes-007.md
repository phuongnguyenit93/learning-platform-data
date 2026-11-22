# Floating-point arithmetic and assumptions about numeric results

## 1. Why is numeric computation a risk during Java migration?

During a **Java Advance Compatibility Migration**, an application may compile and start up successfully on a new JDK yet still return numeric values that differ from the old environment. This is especially noticeable in scoring, interest calculation, statistics, signal processing, optimization, graphics, simulation, data analytics, machine learning, or business rules using float and double.

Several real-world changes often raise questions:

- A calculation result differs by a few units in the last decimal digit after upgrading the JDK or changing CPUs.
- A unit test comparing two doubles with equality suddenly fails when switching algorithms, upgrading a framework, or enabling parallel computation.
- A monetary total computed from double values does not match the expected sum under decimal rules.
- Data containing NaN, Infinity, or -0.0 is processed, rounded, sorted, or serialized differently than expected.
- Adding Math.fma, loop optimizations, or changing summation order alters the trailing bits of the result.
- A mathematical function from Math is expected to always produce bit-identical results across every JDK version and architecture.

The core issue is: **floating-point numbers are not infinite-precision real numbers**, and not every evaluation representing the same algebraic formula yields the same result bits. Migration must distinguish changes caused by language/JVM specifications from changes caused by evaluation order, algorithms, data, libraries, runtime, and environment.

This lesson focuses on understanding and controlling assumptions about numeric results when upgrading Java, changing compilers, switching build/runtime environments, or upgrading numerical libraries.

## 2. Two primitive floating-point types in Java

Java has two primitive types representing binary floating-point numbers:

| Type | Size | Typical representable precision | Notes |
|---|---:|---|---|
| float | 32 bits | Roughly 6–7 significant decimal digits | Uses less memory, accumulates error more easily in many problems. |
| double | 64 bits | Roughly 15–17 significant decimal digits | Commonly used by default for real-number calculations. |

Both float and double are based on the IEEE 754 binary floating-point model, with a sign bit, exponent, and significand. The representable value set is finite, with limits on range, precision, and special values. Most ordinary decimal numbers do not have an exact finite binary representation.

Example:

~~~java
public final class FloatingPointExample {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;
        double sum = a + b;

        System.out.println(sum);          // Typically prints 0.30000000000000004
        System.out.println(sum == 0.3);   // false
    }
}
~~~

The values 0.1 and 0.2 are the closest binary approximations representable as double. When added and rounded according to floating-point rules, the result does not necessarily match the representation of the literal 0.3.

This is not a bug specific to any JDK. It is a fundamental consequence of binary floating-point arithmetic; changing the runtime will not make those values exact decimals.

### 2.1. Distinguishing ideal value, represented value, and display string

When analyzing results, separate three layers:

1. **Ideal mathematical value:** the real number described by the formula, such as 0.1 + 0.2 = 0.3.
2. **Stored floating-point value:** the IEEE 754 approximation after operations round.
3. **Printed or transmitted string:** the output of Double.toString, String.format, DecimalFormat, or a serializer.

Changing the display format can alter output without changing the underlying double bits. Conversely, two doubles with different bits can round to print the same string when digit count is limited.

When investigating a regression, do not rely solely on screenshots or displayed strings. Know whether you are comparing the **internal value**, **bit representation**, or **output format**.

### 2.2. Inspecting the bits of a double value

~~~java
double value = 0.1 + 0.2;

long bits = Double.doubleToRawLongBits(value);
System.out.println(Double.toHexString(value));
System.out.printf("bits = 0x%016x%n", bits);
~~~

Double.toHexString expresses a floating-point value in hexadecimal form suitable for comparison. Double.doubleToRawLongBits reveals the actual bit pattern, which is useful when checking for bit-level differences.

Note: Double.doubleToLongBits canonicalizes some NaN representations; Double.doubleToRawLongBits preserves the raw NaN bit pattern. Choose the right method if the goal is comparing NaN payloads.

## 3. Rounding rules and accumulated error

Floating-point operations are not performed on infinite-precision real numbers. Every result must be represented within the value set of float or double.

In normal arithmetic, an ideal result that cannot be represented exactly is rounded to the nearest representable value under the applicable rule. Java defines floating-point operation behavior based on the language's IEEE 754 semantics.

Repeated addition example:

~~~java
double total = 0.0;

for (int i = 0; i < 10; i++) {
    total += 0.1;
}

System.out.println(total);
System.out.println(total == 1.0);
~~~

Mathematically the sum is 1.0, yet repeated additions can accumulate rounding error; the result need not match the double literal 1.0 bit-for-bit.

### 3.1. Absolute error and relative error

Given expected value x and actual value y, two metrics are commonly used:

- Absolute error: |x - y|.
- Relative error: |x - y| / |x| when |x| is non-zero and this comparison makes sense.

The two measures serve different situations. Absolute error is sensible near 0; relative error is useful when value magnitudes vary widely. A single fixed epsilon cannot be used across all data domains.

For example, an absolute error of 0.000001 may be acceptable when the result is around 1000000, but huge for an expected result of 0.00000001. Conversely, a relative error check can be inappropriate at 0.

### 3.2. What is ULP?

ULP (unit in the last place) is the resolution spacing of a floating-point representation at a particular value magnitude. Java provides Math.ulp(float) and Math.ulp(double) to inspect ULP.

~~~java
double a = 1.0;
double b = 1.0e16;

System.out.println(Math.ulp(a));
System.out.println(Math.ulp(b));
~~~

ULP near large values differs significantly from ULP near 1.0. Therefore, do not expect calculations at every scale to retain the same number of accurate decimal places.

ULP is useful for testing numerical functions and assessing representation-level deviations, but it is **not** a single universal tolerance applicable to every business calculation.

## 4. Evaluation order and non-associativity

For mathematical real numbers, addition and multiplication are associative. With float/double, rounding after each operation means algebraically equivalent rearrangements can yield different results.

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);   // 1.0
System.out.println(right);  // 0.0
~~~

Explanation:

- In the left branch, a + b equals 0.0, then adding c yields 1.0.
- In the right branch, c is too small relative to the magnitude of b at double precision, so b + c can round back to b; when added to a, the result is 0.0.

This leads to practical consequences:

- Changing the iteration order of a dataset can alter its sum.
- Using HashMap/HashSet or changing data partitioning can alter accumulation order.
- Switching from a sequential stream to a parallel stream can change the summation tree.
- Optimizing an algorithm from pairwise sequential addition to grouped summation can change results.
- Differing bits do not automatically mean the new code is wrong; evaluate deviations against problem requirements.

### 4.1. Parallel streams and reductions

Example:

~~~java
double total = values.parallelStream()
        .mapToDouble(Double::doubleValue)
        .sum();
~~~

Mathematically, the elements are summed. However, summation may be split into multiple groups to optimize performance and accuracy, so do not assume the result matches a left-to-right loop bit-for-bit.

Even with sequential streams, the implementation of sum operations may use a different accumulation algorithm than a manual loop. The Java sum API has its own contracts; a migration should not rely on internal summation order if it is not part of the guaranteed contract.

If a problem requires bit-for-bit reproducibility, control the order, algorithm, partitioning, dataset, compiler/runtime, and environment. If only threshold-based accuracy is required, establish appropriate tolerances and test boundary cases.

### 4.2. Example of reducing error with compensated summation

A technique such as Kahan summation can reduce error when summing many values:

~~~java
public static double kahanSum(double[] values) {
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
~~~

This technique does not turn double into exact real numbers and does not guarantee complete independence from input ordering. It is an algorithmic choice to evaluate against data characteristics, not a cure-all for Java compatibility issues.

## 5. Java before and after JDK 17: strictfp and JEP 306

An important migration aspect is how floating-point representation and evaluation rules changed over Java's history.

In Java versions prior to JDK 17, the specification permitted **non-strict** floating-point expressions to use extended exponent value sets under certain conditions. The strictfp keyword requested strict floating-point semantics per that era's specification.

Starting in **Java 17**, **JEP 306 — Restore Always-Strict Floating-Point Semantics** restored Java to an always-strict model for relevant floating-point operations. strictfp no longer makes any difference in computational semantics; depending on the compiler, a warning may appear stating that the modifier is unnecessary.

Legacy code example:

~~~java
public strictfp class LegacyNumericalEngine {
    public double calculate(double a, double b) {
        return a * b + 1.0;
    }
}
~~~

In Java 17+, keeping strictfp to preserve legacy source usually produces the same operation results as removing the modifier under the always-strict model. However, do not infer that **every calculation on every runtime is bit-identical** solely because JEP 306 exists.

### 5.1. What does JEP 306 solve?

JEP 306 clarifies and unifies floating-point operation semantics across the language and JVM, eliminating the historical leeway related to extended exponent value sets.

JEP 306 does **not** automatically:

- Make double addition associative like ideal real numbers.
- Represent 0.1 or arbitrary decimals exactly in binary.
- Make all complex Math functions produce identical bits across every implementation.
- Make an algorithm whose reduction order changed yield the same result as the old version.
- Convert monetary calculations from double to exact decimals.
- Guarantee that native/JNI or GPU libraries follow the same rules as pure Java code.

When comparing Java 8/11 with Java 17/21, clearly document which differences stem from Java semantics, which from algorithms/libraries, and which from CPU or runtime configuration.

### 5.2. strictfp in legacy code

In projects upgrading the JDK, you may encounter strictfp on legacy classes, interfaces, or methods. There is no need to remove the modifier just to fix a numeric result bug before identifying its cause. On the other hand, do not scatter strictfp everywhere hoping every computation will become completely deterministic.

If the organization must support both older and newer JDKs, define the compilation release target, test matrix, and numeric compatibility commitments. Once the new branch targets Java 17+ exclusively, simplifying the modifier can be considered in a separate change with corresponding regression testing.

## 6. Math, StrictMath, and complex calculations

Java has two important math utility classes:

- java.lang.Math provides many mathematical functions with accuracy/behavior requirements per the API documentation. Some methods may be platform-optimized or use intrinsics.
- java.lang.StrictMath provides methods specified to support stronger reproducibility for methods within its defined scope, generally relying on more tightly specified algorithms.

For complex functions such as trigonometry, exponentials, or logarithms, do not assume Math.sin, Math.cos, or Math.exp always produce the exact same bits across every Java version, CPU, and implementation. Read each method's specific guarantees, particularly ULP bounds, semi-monotonicity, and special cases.

Example:

~~~java
double x = 0.7;
double a = Math.sin(x);
double b = StrictMath.sin(x);

System.out.println(a);
System.out.println(b);
System.out.println(Double.doubleToRawLongBits(a)
                   == Double.doubleToRawLongBits(b));
~~~

The bit comparison result depends on the method and actual implementation. A tiny difference between two values is not automatically a bug; check against the application's accuracy requirements and calculation scope.

### 6.1. When to consider StrictMath?

StrictMath is worth considering when strong reproducibility constraints are needed for the corresponding math functions, such as in simulations or cross-environment result verification. Still, you need to:

1. Check the API guarantees and documentation version for each method used.
2. Test on the JDKs, CPUs, and environments actually supported.
3. Ensure inputs, operation ordering, and computations outside those methods do not change.
4. Evaluate performance and compatibility with the application's mathematical model.

StrictMath does not replace BigDecimal and does not solve decimal data issues in financial business logic.

### 6.2. Math.fma changes expression rounding rules

FMA (fused multiply-add) computes a × b + c in a single operation with one rounding step for the combined result, instead of rounding a × b first and then rounding the sum.

~~~java
double traditional = a * b + c;
double fused = Math.fma(a, b, c);
~~~

The two results can differ in bits. FMA often improves accuracy for certain calculations, yet a migration replacing a * b + c with Math.fma(a, b, c) is still a **numerical algorithm change** that requires testing.

Conversely, do not assume an arbitrary a * b + c expression in Java will automatically carry single-rounding semantics equivalent to Math.fma. When the contract requires FMA, explicitly call the FMA API.

## 7. NaN, infinity, and signed zero

IEEE 754 includes special values that much business code does not anticipate:

- NaN (Not a Number), which can arise from an indeterminate operation like 0.0 / 0.0.
- Positive Infinity and Negative Infinity, e.g., dividing a non-zero value by 0.0 or overflowing.
- +0.0 and -0.0, which compare equal under the == operator yet can lead to different results in certain operations.
- Very small subnormal values, representing numbers near 0 with reduced precision.

Example:

~~~java
double nan = 0.0 / 0.0;
double positiveInfinity = 1.0 / 0.0;
double negativeZero = -0.0;

System.out.println(Double.isNaN(nan));           // true
System.out.println(Double.isInfinite(positiveInfinity)); // true
System.out.println(0.0 == negativeZero);         // true
System.out.println(1.0 / 0.0);                   // Infinity
System.out.println(1.0 / negativeZero);          // -Infinity
~~~

### 7.1. NaN is not equal to itself via the == operator

~~~java
double value = Double.NaN;

System.out.println(value == value);       // false
System.out.println(value != value);       // true
System.out.println(Double.isNaN(value));  // true
~~~

Relational comparisons with NaN such as <, <=, >, and >= return false. Therefore, a range check like:

~~~java
if (value < minimum || value > maximum) {
    throw new IllegalArgumentException("Out of range");
}
~~~

is insufficient to block NaN: both comparisons evaluate to false. If the data domain accepts only finite numbers, check explicitly:

~~~java
if (!Double.isFinite(value)
        || value < minimum
        || value > maximum) {
    throw new IllegalArgumentException("Non-finite or out of range");
}
~~~

Double.isFinite is provided in modern Java releases; when supporting older Java versions, choose an API matching the project's minimum Java level.

### 7.2. -0.0 is not always equivalent to +0.0

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero);     // true
System.out.println(Double.compare(positiveZero, negativeZero)); // non-zero
System.out.println(1.0 / positiveZero);               // Infinity
System.out.println(1.0 / negativeZero);               // -Infinity
~~~

Specifically:

- The == operator treats +0.0 and -0.0 as equal.
- Double.compare establishes a total ordering that distinguishes signed zeros.
- Double.equals also distinguishes +0.0 and -0.0 by bit pattern as specified for boxed Double.
- Division can yield +Infinity or -Infinity depending on the zero's sign.

Thus, switching from primitive comparison to boxed Double, comparators, Map keys, or sorting can change how signed zero or NaN is handled.

### 7.3. Boxed Double and collections

Mathematical equivalence does not mean equivalence when used as an object key.

~~~java
Set<Double> values = new HashSet<>();
values.add(0.0);
values.add(-0.0);

System.out.println(values.size()); // 2 per Double's equals/hashCode
~~~

The example above requires importing java.util.Set and java.util.HashSet when placed in a complete Java file. In applications with aggregations or cache keys derived from Double, decide whether to normalize -0.0 to +0.0 and how to handle NaN before storing.

Do not fix issues by using == in one place and Double.equals in another without defining unified data semantics.

## 8. Overflow, underflow, and range limits

double has a large but finite range. Calculations exceeding the limit can produce Infinity; very small values can round to 0.0 or subnormal values.

~~~java
double overflow = Double.MAX_VALUE * 2.0;
double underflow = Double.MIN_VALUE / 2.0;

System.out.println(overflow);  // Infinity
System.out.println(underflow); // 0.0
~~~

Note that Double.MIN_VALUE is the smallest positive double greater than 0, **not the most negative value**.

When migrating JDKs or changing algorithms, check problems with values near boundaries:

- Multiplying or adding many large values.
- Dividing by values near 0 or signed zero.
- Unit conversions creating very large or very small factors.
- Normalization and percentages when the sum is 0.
- exp/log or trigonometric functions in numerically sensitive regions.
- Loop convergence conditions when step size becomes smaller than ULP.

An algorithm can avoid throwing an exception while still producing Infinity or NaN that propagates through subsequent steps. For critical business calculation paths, enforce valid domain checks and monitor non-finite results.

## 9. Type conversion and rounding

### 9.1. Casting double to int/long

Casting from double to an integral type is not equivalent to decimal rounding for business needs.

~~~java
double value = 7.9;

int truncated = (int) value;           // 7
long rounded = Math.round(value);      // 8
~~~

Java defines floating-point to integer conversion behavior, including handling of NaN and out-of-range values; casting does not throw ArithmeticException just because a number exceeds the target type's range. If business logic requires overflow detection, check explicitly before converting.

### 9.2. Math.round, floor, ceil, and rint

The following functions are not interchangeable:

| Function | Basic meaning |
|---|---|
| Math.floor(x) | Largest integral value not exceeding x, represented as floating point. |
| Math.ceil(x) | Smallest integral value not less than x, represented as floating point. |
| Math.rint(x) | Closest integral value as double, using ties-to-even rounding. |
| Math.round(x) | Rounds to an integral type per its own specification, differing from rint at half-way ties. |
| BigDecimal.setScale(scale, mode) | Decimal rounding with the specified scale and rounding mode. |

Example:

~~~java
double x = 2.5;
double y = -2.5;

System.out.println(Math.rint(x));  // 2.0 (ties to even)
System.out.println(Math.round(x)); // 3
System.out.println(Math.round(y)); // -2
~~~

For x = -2.5, Math.round and "round half away from zero" do not behave identically. If a system computes money or ranking tiers, specify the exact rounding rule rather than just writing "round to nearest".

### 9.3. Displayed decimal numbers

A double result can be formatted using Locale, DecimalFormat, or String.format:

~~~java
System.out.printf(Locale.ROOT, "%.2f%n", value);
~~~

This example requires importing java.util.Locale. Without specifying a locale, the decimal separator, grouping separator, or output text may depend on the environment's default locale.

Formatting to two decimal places does not change the stored double value. If data is sent to another service, define which result is serialized: the raw number, the formatted string, or a BigDecimal rounded according to business rules.

## 10. Why should double not be used for currency?

Finance typically requires exact decimal representation, specific rounding rules, and auditability. Because float/double are binary, they may fail to represent 0.01, 0.1, or tax rates as exact decimals.

Example:

~~~java
double unitPrice = 0.10;
double tax = 0.20;
double total = unitPrice + tax;

System.out.println(total);
~~~

For currency, consider:

1. **long in the smallest unit** (minor units) such as cents when range, currency, and rounding rules permit.
2. **BigDecimal** when exact decimals, rates, explicit scale, and explicit rounding rules are needed.

Not every BigDecimal operation is automatically well-defined; division can yield a repeating infinite decimal, so specify scale or a MathContext.

### 10.1. Creating BigDecimal properly

~~~java
import java.math.BigDecimal;

public final class MoneyExample {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("0.10");
        BigDecimal b = new BigDecimal("0.20");
        BigDecimal sum = a.add(b);

        System.out.println(sum); // 0.30
    }
}
~~~

Use a decimal string or BigDecimal.valueOf(double) when the input's meaning is understood. Avoid:

~~~java
BigDecimal a = new BigDecimal(0.1);
~~~

The constructor above preserves the binary value of double 0.1 converted into the exact decimal representation of that approximation; it does **not** create the exact decimal 0.1 as usually intended.

Conversely:

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(0.1);
~~~

Both approaches above are generally appropriate when modeling the decimal value 0.1, because valueOf uses the canonical string representation of double. However, if the input source was already rounded across a chain of double calculations, converting to BigDecimal afterward **cannot recover lost precision**.

### 10.2. BigDecimal rounding rules

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal subtotal = new BigDecimal("10.005");
BigDecimal rounded = subtotal.setScale(2, RoundingMode.HALF_EVEN);

System.out.println(rounded);
~~~

RoundingMode.HALF_EVEN is a popular choice in certain financial problems, but not the right default for every tax, fee, or accounting rule. The rule must come from the business contract.

Division:

~~~java
BigDecimal quotient = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_UP);
~~~

Dividing BigDecimal.ONE by 3 without specifying rounding can throw ArithmeticException due to a non-terminating decimal expansion. Choose a scale/precision policy suited to the problem domain.

### 10.3. BigDecimal equals and compareTo

~~~java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));       // false
System.out.println(x.compareTo(y) == 0); // true
~~~

BigDecimal.equals considers scale, whereas compareTo compares numeric value. When using them as Map keys or Set elements, understand equals/hashCode semantics. Migrating from double to BigDecimal can introduce new differences in comparison and hashing beyond merely fixing binary error.

## 11. Sort order, grouping, and keys in numeric data

An application's results can change after migration due to sorting algorithms or data structures, not only arithmetic operations.

For example, a system computes a sum per group and then sums the groups:

~~~text
Same input values
       │
       ├─ Group by HashMap ──> iterate groups ──> sum
       │
       └─ Sort by key ──> sum sequentially
~~~

If the order in which values are summed changes, the double total can differ in its trailing digits. Library version updates, key partitioning, or worker count changes can alter results without directly changing the addition operation.

Several points to note:

- HashMap does not guarantee a fixed iteration order as a contract.
- Parallel reductions can group additions in multiple ways.
- Double.compare has specific rules for NaN and signed zero.
- Primitive == and Double.equals do not share the same semantics for NaN, +0.0, and -0.0.
- Sorting before summing can sometimes affect accumulated error and performance.

If strong reproducibility is required, specify input order, partitioning, and the summation algorithm; do not rely on arbitrary collection ordering.

## 12. Serialization and API contracts containing numbers

In distributed services, numeric result bugs often surface at data boundaries:

- JSON contains numbers that consumers may parse into double, decimal, or integer with different limits.
- Many serializers do not directly support NaN/Infinity as valid JSON numbers.
- A -0.0 value may be formatted or serialized differently than expected depending on library and configuration.
- A large integer JSON number can exceed the integer precision exactly representable as a double in JavaScript clients.
- XML, CSV, and database drivers have their own rules for scale, rounding, and special values.
- BigDecimal may be emitted as a string or JSON number depending on configuration, causing type mismatches with clients.

Do not assume a numeric value sent over HTTP and returned preserves the exact double bits. The contract should state data types, units, precision/scale, handling of null or non-finite values, and round-trip rules.

For example, a financial API contract may use decimal strings:

~~~json
{
  "currency": "USD",
  "amount": "123.45"
}
~~~

This approach requires consumers to parse cleanly and understand it is a decimal string. If the legacy system returned a JSON number, switching to a string is a breaking wire contract change requiring versioning and a migration guide; do not change it unilaterally just to improve precision.

### 12.1. Round-trip verification

For critical data fields, test:

1. Java object → serializer → payload.
2. Payload → parser of the consumer or external application.
3. Compare per the **contract**: decimal number, double bits, scale, or rounded value depending on data type.
4. Boundary values: 0, -0.0, very large, very small, high-digit-count numbers, null, and NaN/Infinity where allowed.

If the contract forbids NaN/Infinity, reject them or apply explicit error rules rather than silently converting them to null or undocumented strings.

## 13. Designing tests for numeric results during migration

No single assertion method fits every float/double value. Categorize assertions by requirement.

### 13.1. When exact bit-level comparison is required

Some cases require verifying binary serialization, hash formatting, deterministic algorithms, or bitwise reproducibility:

~~~java
long expectedBits = Double.doubleToRawLongBits(expected);
long actualBits = Double.doubleToRawLongBits(actual);

if (expectedBits != actualBits) {
    throw new AssertionError("Different floating-point bits");
}
~~~

Notes:

- Raw-bit comparison distinguishes +0.0/-0.0.
- It also distinguishes NaN payloads with different bit patterns.
- This is a strict condition; use it only when the contract truly requires bitwise equality.

If comparing under Double.equals or Double.compare semantics, use those exact semantics instead of substituting raw-bit equality.

### 13.2. When tolerance-based comparison is required

A common strategy combines absolute and relative tolerances:

~~~java
public static boolean closeEnough(
        double expected,
        double actual,
        double absTolerance,
        double relTolerance) {

    if (Double.doubleToLongBits(expected)
            == Double.doubleToLongBits(actual)) {
        return true;
    }

    if (!Double.isFinite(expected)
            || !Double.isFinite(actual)) {
        return false;
    }

    double difference = Math.abs(expected - actual);
    double scale = Math.max(Math.abs(expected), Math.abs(actual));

    return difference <= absTolerance
            || difference <= relTolerance * scale;
}
~~~

This helper illustrates finite-number comparison for suitable requirements; in real use, choose absTolerance and relTolerance per the business domain, guard against negative/NaN tolerance arguments, and evaluate overflow of intermediate calculations. Whether expected/actual NaN should be considered equal must also be decided explicitly in the test contract.

If a test framework provides assertEquals(expected, actual, delta), it can be used for problems where an absolute tolerance is appropriate. Do not set delta excessively large just to make every regression test pass.

### 13.3. Invariant-based testing

For algorithms not requiring identical bits, checking invariants is more meaningful than only comparing raw outputs:

- Probabilities lie within [0, 1] in valid cases.
- Proportions sum close to 1 within an appropriate tolerance.
- Values are non-negative where business rules require, with defined exceptions.
- Functions preserve monotonicity or ordering where appropriate for the input domain.
- Normalized outputs have a norm close to 1.
- Maximum deviation stays below the scientific/business threshold.
- No NaN or Infinity appears in outputs forbidden by the contract.

If an algorithm is numerically sensitive, include tests for ill-conditioned regions such as subtracting nearly equal numbers, values near overflow, many iterations, or data spanning wide magnitudes.

### 13.4. Golden tests require understanding the baseline

A common migration practice is running the same data on the old and new JDKs and saving the results as a baseline.

However, "old JDK output" is not automatically absolute truth. If the old output contained a numeric bug or relied on an unguaranteed ordering, freezing the old bits could lock in undesirable behavior forever. Specify clearly:

1. Does the problem require bitwise compatibility or numeric tolerance?
2. Can the reference result be computed using a more reliable method?
3. Are inputs, seeds, locale, timezone, thread count, and runtime configurations equivalent?
4. Have math libraries, solvers, vectorization, or GPUs changed?
5. Have tolerances been approved by business/technical owners?

## 14. Empirical verification when upgrading the JDK

A data verification workflow can be run across at least two environments:

~~~text
Controlled artifact / commit
                 │
        ┌────────┴─────────┐
        ▼                  ▼
   Baseline JDK        Target JDK
        │                  │
        ▼                  ▼
 Input dataset       Same dataset
        │                  │
        ▼                  ▼
 Output + metrics   Output + metrics
        └────────┬─────────┘
                 ▼
     Compare per contract
       (bits/tolerance/
        domain invariants)
                 │
                 ▼
      Classify changes
~~~

Information to record with each run:

| Information | Why it is needed |
|---|---|
| Full JDK version, vendor, OS, CPU/architecture | Helps explain implementation/environment differences. |
| Commit and artifact checksum | Ensures the exact same code version is being compared. |
| Dependency lock/BOM or resolved graph | Avoids misattributing regressions caused by library changes. |
| Input dataset and seed | Allows reproduction when algorithms use randomized data. |
| Thread count, parallelism, batch size | Reduction order or distributed processing may differ. |
| Locale, timezone, and output formatting | Distinguishes numeric changes from string formatting changes. |
| Tolerance and assertion type | Ensures pass/fail conclusions are meaningful. |
| Total cases, maximum deviation, non-finite count | Provides a broader view than a single sample value. |

### 14.1. Classifying discrepancies

| Observation | Possible cause | Next step |
|---|---|---|
| Differs by a few ULPs in Math.sin/Math.exp | Different implementation/numeric optimization or function usage. | Check Math/StrictMath contracts, accuracy, and test with thresholds. |
| Sum differs when parallel is enabled | Different summation order/grouping. | Standardize algorithm or accept deviation within bounds. |
| Large discrepancy on small input | Catastrophic cancellation, division near 0, or unstable algorithm. | Check numerical conditioning, choose a better formula/precision. |
| NaN appears after changes | Invalid input, 0/0, or function domain out of range. | Add validation, trace NaN origin, define error contract. |
| Infinity appears | Overflow, division by 0, exp exceeding limits, or accumulation. | Check value ranges and add error handling/input constraints. |
| Same number but different string | Locale, formatter, serializer, or formatting rule changed. | Compare bits/values before formatting and inspect the wire contract. |
| Monetary amount off by one cent | Using double, different rounding point, or different RoundingMode. | Use BigDecimal/minor units and specify where rounding occurs. |
| Output matches in unit tests but differs in production | Non-equivalent input sources, CPU, concurrency, native libraries, or deployment. | Cross-check environments, checksums, and actual data. |

### 14.2. Do not treat JVM flags as a magic fix

When discrepancies appear, do not broadly apply legacy or poorly understood JVM flags hoping to "restore Java 8 results". Some optimization flags affect only performance or are no longer supported.

Identify the specific operation, Java release semantics, JIT/native dependencies, numerical sensitivity, and business requirements before changing runtime configuration. Any compiler/JVM flag changes must be recorded in the baseline and tested across all supported environments.

## 15. Designing numerically stable algorithms

When source code must be modified rather than only adjusting tests, prioritize mathematically grounded approaches:

### 15.1. Avoid subtracting nearly equal numbers when an alternative formula exists

When two large, nearly equal values are subtracted, significant digits can be lost. This phenomenon is called *cancellation*.

For instance, a formula may be algebraically correct yet unstable for certain inputs. Analyze the numeric domain and find an equivalent expression designed to reduce precision loss.

APIs like Math.log1p(x) and Math.expm1(x) exist to help with certain small-input cases where computing log(1+x) or exp(x)-1 directly can be less accurate. They are not mandatory replacements in every scenario; verify the domain and error bounds.

### 15.2. Specify rounding at business boundaries

In price calculations, if business rules require rounding after each invoice line, you cannot arbitrarily sum everything first and round only at the end. Conversely, rounding too early can also accumulate discrepancies.

Explicitly specify:

- Unit of measure.
- Precision and scale for each step.
- RoundingMode.
- Timing of rounding before/after taxes, fees, and allocations.
- How remainders are handled when splitting a total across multiple items.
- Rules for reconciling component sums with the grand total.

This is part of the behavioral contract. Switching types from double to BigDecimal does not guarantee old results remain identical; the project may need to communicate a business-behavior change.

### 15.3. Choose data types by requirements, not merely by habit

| Problem | Type/approach typically worth considering |
|---|---|
| Scientific simulation tolerating bounded error | double, stable algorithm, defined tolerances. |
| Sensor data or graphics focused on memory/throughput | float if the error margin is acceptable. |
| Money with fixed minor units | long with overflow checks where needed. |
| Taxes, interest, decimal accounting | BigDecimal with explicit MathContext/RoundingMode. |
| Metrics aggregated over millions of samples | Stable summation algorithm, defined processing order, and tolerance tests. |
| Data requiring bitwise reproducibility | Control algorithm, ordering, bit representation, and certified environment. |

There is no single choice optimal for accuracy, speed, memory, and reproducibility simultaneously. Decisions must rely on requirements and actual measurements.

## 16. Migration when replacing math and data-processing libraries

A JDK upgrade often coincides with upgrading Apache Commons Math, statistics libraries, JSON parsers, data-processing engines, or native code. Changes in numeric outputs may come from dependencies rather than the JDK itself.

Changes to isolate:

- Library algorithm/function versions.
- Convergence rules and stopping criteria.
- Summation/accumulation methods or iteration order.
- Serialization formats.
- Default precision/rounding levels.
- JNI/BLAS/native libraries, CPU architecture, or vectorization capabilities.
- Policies for NaN, Infinity, and missing data.

When multiple changes occur together, construct a controlled test matrix, for example:

| Code / library | Old JDK | Target JDK | Purpose |
|---|---|---|---|
| Current baseline | Run | Run if compatible | Observe impact of changing only the runtime. |
| New library | Run if supported | Run | Observe impact from changing dependencies. |
| Modified algorithm | Run if supported | Run | Verify behavior after code changes. |

Not every combination must build/run; mark incompatible cells clearly. Crucially, avoid blaming every discrepancy on "the new Java" when code, dependencies, and pipelines changed simultaneously.

## 17. Observing numeric metrics in production

After rollout, monitor metrics reflecting the reliability of numeric results, rather than only checking whether exceptions occurred.

Examples:

- Rate of non-finite outputs when the contract permits only finite numbers.
- Count of outputs exceeding the valid range.
- Number of mismatches against a reference source or legacy system within a safe reconciliation window.
- Maximum deviation and p95/p99 of deviation by data domain.
- Monetary total discrepancy in minor units or count of cases needing rounding adjustment.
- Convergence time and algorithm non-convergence rate.
- Number of records failing serialization due to NaN/Infinity.

When comparing two business-logic implementations, do not execute two side-effecting writes just to compare outputs. Use normalized data, read-only modes, or safely designed shadow computation.

Some numeric anomalies can be hidden by formatters or dashboards that round numbers. When investigating, store metrics with sufficient precision alongside appropriate request IDs/traces, without logging secrets or sensitive data.

## 18. Numeric compatibility policy template

When a critical module undergoes a JDK upgrade, an explicit policy can be documented:

~~~text
Module: Pricing and Risk Calculation

Input contract:
- Only accept finite doubles within the defined range.
- NaN and Infinity are rejected at the API boundary.

Calculation contract:
- Monetary values are represented using decimal or minor units.
- RoundingMode and rounding positions are specified in business rules.
- Reductions use a defined algorithm and ordering.

Output contract:
- Monetary fields use documented scale/units.
- Analytical fields use appropriate absolute/relative tolerances.
- JSON does not contain NaN/Infinity.

Migration acceptance:
- Regression datasets run on the baseline JDK and the target JDK.
- Bitwise contracts (if any) are verified separately.
- Other numeric deviations must remain within approved thresholds.
- Boundary cases for overflow/underflow/NaN are tested.

Operational evidence:
- Record the JDK, dependencies, CPU, dataset, and algorithm version.
- Monitor mismatches and numeric anomalies after rollout.
~~~

This is a process template, not default thresholds for every project. Each module must define its own requirements: some problems tolerate small errors, some financial problems require exact cent-level matches, and some protocols require preserving bit patterns.

## 19. Common false assumptions

| Assumption | Why it is wrong or incomplete | Approach |
|---|---|---|
| "0.1 + 0.2 always equals 0.3 in double." | Many decimals are not represented exactly in binary floating point. | Compare per contract and use decimal types when needed. |
| "Changing parentheses does not change the result." | Floating-point operations are not associative like real numbers. | Control ordering and test numeric tolerances. |
| "Math is always bit-identical on every JVM." | Some functions allow error bounds and differ across implementations. | Check API contracts, test, and consider StrictMath when appropriate. |
| "strictfp will fix all discrepancies in Java 17/21." | JEP 306 already enforces always-strict semantics; discrepancies have other causes. | Analyze algorithms, Math functions, and the environment. |
| "Parallel summation equals sequential summation." | Reduction trees and summation order may differ. | Choose specific algorithms and reproducibility requirements. |
| "NaN is caught by x < min or x > max." | Relational comparisons with NaN all evaluate to false. | Check Double.isFinite or isNaN first. |
| "0.0 and -0.0 are always identical." | Signed zero affects bits, compare, and division. | Define a handling policy for signed zero. |
| "Double.equals and == are completely equivalent." | NaN and signed zero have different semantics between wrapper and primitive. | Choose comparator/equals according to the contract. |
| "BigDecimal is automatically exact when created from double." | new BigDecimal(double) retains the binary approximation of the input. | Construct from a decimal string or valueOf when appropriate. |
| "BigDecimal.equals is numeric comparison." | equals checks scale; compareTo does not consider scale that way. | Distinguish representation identity from numeric equality. |
| "Printing 2 digits means the data is rounded." | Formatting does not modify the stored value. | Round at the business step or store as decimal. |
| "A single fixed epsilon works for every calculation." | Magnitude and numerical sensitivity vary across data domains. | Pick absolute/relative or ULP thresholds per problem. |
| "No exception means the calculation is right." | Overflow can yield Infinity; indeterminate operations can yield NaN. | Verify domains and invariants. |
| "Any difference on the new JDK is a JDK bug." | Dependencies, data, evaluation order, formatters, or native stacks may differ. | Isolate variables and run controlled experiments. |

## 20. Workflow for resolving a numeric result regression

When a different result appears after migration:

1. **Record the symptom:** input, expected/actual values, JDK versions, absolute/relative deviation, formatted output, and raw bits if needed.
2. **Identify the contract:** does it require bitwise equality, tolerance, exact decimals, or invariants?
3. **Isolate change scope:** JDK, libraries, compiler, CPU, data, concurrency, locale, formatter, and deployment.
4. **Create a minimal reproduction:** code snippet/dataset sufficient to reproduce the discrepancy without the entire system.
5. **Check special values:** NaN, Infinity, signed zero, overflow/underflow, subnormals.
6. **Check evaluation order:** reduction, parallelism, iteration order, FMA, and rounding boundaries.
7. **Check math libraries:** Math/StrictMath, native libraries, algorithm versions.
8. **Evaluate solutions:** fix formulas, use stable algorithms, change data types, or adjust the test strategy to match the contract.
9. **Run regression and integration tests:** on the baseline environment and target JDK, with boundary datasets.
10. **Make rollout decision:** update the numeric compatibility policy, metrics, rollback plan, and docs if business outputs changed.

If a discrepancy is found in monetary/tax calculations or external interface data, do not unilaterally "loosen tolerance" just to make tests pass. A business review and migration plan are needed because tiny discrepancies can accumulate or cause reconciliation mismatches.

## 21. Conclusion

When upgrading the JDK, floating-point computation must be evaluated against **IEEE 754 semantics, representation precision, operation ordering, Math/StrictMath functions, strictfp, and the execution environment**. Java 17 with JEP 306 restored always-strict semantics for floating-point operations, yet it does not turn double into exact decimals or eliminate differences caused by algorithms, parallelization, and libraries.

A safe migration strategy must distinguish ideal real-number results from floating-point bits and serialized strings; explicitly define requirements for bitwise equality, tolerances, or decimal exactness; check NaN/Infinity/-0.0 and overflow/underflow; and use BigDecimal or minor units when the contract requires exact decimals. Evidence should be gathered from identical datasets, artifacts, JDKs, and controlled dependencies, combining regression tests, invariants, and production monitoring.

**The goal is not to force every calculation on the new JDK to emit the exact same digit string as the old JDK at all costs, but to ensure results satisfy the defined numeric contract, differences are explainable, and deployment rests on verifiable evidence.**