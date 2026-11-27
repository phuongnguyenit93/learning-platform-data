# Testing Boundary Calculations and Avoiding Associativity Assumptions in Java 17

Java's floating-point types are convenient for scientific computing, measurement, graphics, and many engineering problems. However, floating-point numbers cannot store every decimal number exactly. Each operation can round the result to a representable value, and that error can accumulate or alter outcomes near a threshold.

Therefore, when writing and testing Java 17 programs, do not test only a few typical values. You must consider **input domain boundaries**, **representable values adjacent to thresholds**, **overflow/underflow**, **NaN and infinity**, and especially **never assume floating-point operations are associative like mathematical real arithmetic**.

## 1. How Do double and float Represent Numbers?

Java has two common primitive floating-point types:

| Type | Size | Approximate Precision | Magnitude Range |
| --- | ---: | ---: | --- |
| float | 32 bits | about 6–7 significant decimal digits | about 1.4 × 10⁻⁴⁵ to 3.4 × 10³⁸ |
| double | 64 bits | about 15–16 significant decimal digits | about 4.9 × 10⁻³²⁴ to 1.8 × 10³⁰⁸ |

Both types follow the IEEE 754 binary floating-point format. A value is encoded with a sign, exponent, and significand (significant fraction part). Binary exactly represents fractions whose denominators are powers of 2, such as 0.5, 0.25, and 0.125. Fractions like 0.1 or 0.2 have repeating binary expansions and must be rounded to the nearest storable value.

Example:

~~~java
double result = 0.1 + 0.2;
System.out.println(result);
System.out.println(result == 0.3);
~~~

Typical output:

~~~text
0.30000000000000004
false
~~~

This is not a Java-specific bug. The stored double values are close to 0.1 and 0.2; addition runs on those rounded binary values, and the result is rounded again. The stored result therefore does not necessarily equal the representation of the literal 0.3.

### Uneven Precision Across the Range

The spacing between two adjacent representable double numbers depends on the magnitude of the number. Near 1.0, spacing is on the order of 10⁻¹⁶; near 10¹⁶, spacing is much larger. Thus no single absolute error threshold fits all values.

An example showing integer precision limits when converting to double:

~~~java
double a = 9_007_199_254_740_992d; // 2^53
double b = 9_007_199_254_740_993d; // 2^53 + 1

System.out.println(a == b); // true
~~~

Double can represent every integer exactly in the range -2⁵³ to 2⁵³. Outside this range, not every consecutive integer has a distinct representation. For float, the corresponding limit is 2²⁴. If an application needs large integer IDs, counts, or money in smallest units, use long/BigInteger or an appropriate decimal type instead of converting to double.

## 2. Why Must You Not Assume Associativity?

In real arithmetic, addition is associative:

\[
(a+b)+c = a+(b+c)
\]

However, floating-point addition must round after each operation. Parenthesization changes rounding order, so the two sides can differ.

Example:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
System.out.println(left == right); // false
~~~

Explanation:

1. On the left side, a + b cancels to 0, then adding c gives 1.
2. On the right side, b + c must round. Because c is too small relative to b's magnitude, the result rounds to b. Then a + b cancels to 0.

Similarly, floating-point multiplication can also be non-associative due to rounding and overflow/underflow. Algebraic transformations such as regrouping, distributing, or simplifying expressions must be evaluated for precision and value range, not based solely on real algebra.

### Evaluation Order in Java

Java expressions follow language-defined operator precedence and associativity. Additions of the same precedence group left-to-right:

~~~java
double result = a + b + c;
~~~

This expression is grouped as:

~~~java
double result = (a + b) + c;
~~~

Do not arbitrarily rewrite it to a + (b + c) assuming the result will remain the same. Starting in Java 17, Java's floating-point operations have strict semantics under JEP 306; that ensures operation behavior is consistent with the specification, yet **does not make floating-point numbers absolutely exact and does not create associativity**.

### Impact on Streams and Parallel Processing

A reduction such as double summation is not strictly associative in floating-point arithmetic. If data is split into different chunks and summed per chunk, ordering and grouping can change the result in the lowest bits. This is especially notable in parallel reductions, where data partitions may be combined in varying structures.

Do not use the double result of a reduction as an exact comparison key if business logic requires strictly stable results. If evaluation order matters, define the ordering and summation algorithm; if exact decimal currency calculation is needed, choose a decimal representation or integers in the smallest unit.

## 3. Floating-Point Scenarios to Test at Boundaries

Floating-point testing must cover regions where behavior can change. For a threshold T, do not test just an arbitrary smaller and larger value; test **the value immediately before T, exactly T, and immediately after T** in the representable domain.

| Boundary Category | Examples to Consider | Potential Issues |
| --- | --- | --- |
| Near 0 | +0.0, -0.0, smallest subnormal, small positive/negative values near 0 | Division by zero, underflow, signed zero |
| Business thresholds | immediately below, equal to, and immediately above threshold | `<` vs `<=`, rounding flipping branches |
| Small numbers | Double.MIN_VALUE, Double.MIN_NORMAL | Subnormals, underflow, loss of relative precision |
| Large numbers | Double.MAX_VALUE and adjacent values | Overflow to infinity |
| Non-finite | NaN, positive/negative infinity | Comparisons, validation, data serialization |
| Accumulated values | sum of many large and small numbers | Loss of significant digits, cancellation |
| Type conversions | large long to double, double to int | Precision loss or clamping/truncation |
| Decimal data | 0.1, 0.2, 0.3, and monetary values | Cannot compare with exact equality |

### Testing Tightly Around a Threshold Using Math.nextDown and Math.nextUp

Java provides:

- Math.nextDown(x): the representable floating-point number immediately preceding x toward negative infinity.
- Math.nextUp(x): the representable floating-point number immediately following x toward positive infinity.
- Math.ulp(x): the spacing of one unit in the last place at magnitude x.
- Math.nextAfter(start, direction): steps to the next representable value in the specified direction.

Example:

~~~java
double limit = 100.0;

double justBelow = Math.nextDown(limit);
double exact = limit;
double justAbove = Math.nextUp(limit);

System.out.println(justBelow < limit); // true
System.out.println(exact == limit);    // true
System.out.println(justAbove > limit); // true
System.out.println(Math.ulp(limit));
~~~

This is a way to construct exact test inputs around a double boundary without guessing an arbitrary epsilon. For a business rule such as score must be less than 100, these three cases clearly determine boundary behavior.

### Testing Closed and Open Intervals

Suppose valid scores lie in the closed interval [0, 100]:

~~~java
static boolean isValidScore(double score) {
    return Double.isFinite(score) && score >= 0.0 && score <= 100.0;
}
~~~

Boundary-adjacent cases:

~~~java
double min = 0.0;
double max = 100.0;

System.out.println(isValidScore(Math.nextDown(min))); // false
System.out.println(isValidScore(min));                // true
System.out.println(isValidScore(Math.nextUp(min)));   // true
System.out.println(isValidScore(Math.nextDown(max))); // true
System.out.println(isValidScore(max));                // true
System.out.println(isValidScore(Math.nextUp(max)));   // false
~~~

If the domain is the open interval (0, 100), the condition must use score > 0 and score < 100. The test suite must reflect the exact contract, not guess from UI wording.

## 4. Testing Overflow and Underflow

### Overflow

When a result exceeds the finite representable magnitude, a floating-point operation can produce positive infinity or negative infinity:

~~~java
double large = Double.MAX_VALUE;
double overflow = large * 2.0;

System.out.println(overflow);                // Infinity
System.out.println(Double.isInfinite(overflow)); // true
System.out.println(Double.isFinite(overflow));   // false
~~~

There is no automatic ArithmeticException as in some checked integer operations. If the business domain does not allow infinity, check the result:

~~~java
static double multiplyFinite(double a, double b) {
    double result = a * b;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("Floating-point result is not finite");
    }
    return result;
}
~~~

Note: checking finite inputs and checking finite results are two separate steps. Two finite inputs can still produce overflow.

### Underflow and Subnormals

When result magnitude is very small, the result can drop into the subnormal (denormal) range to preserve magnitudes below the normal limit, or eventually round to zero.

Important constants:

| Constant | Meaning |
| --- | --- |
| Double.MIN_VALUE | Smallest positive non-zero double; this is the smallest subnormal |
| Double.MIN_NORMAL | Smallest positive normal double |
| Double.MAX_VALUE | Largest positive finite double |
| Float.MIN_VALUE | Smallest positive non-zero float |
| Float.MIN_NORMAL | Smallest positive normal float |

The name MIN_VALUE is easy to misunderstand: it is **not the most negative number**, nor the smallest magnitude in the normal range. For double, Double.MIN_VALUE is approximately 4.9 × 10⁻³²⁴; Double.MIN_NORMAL is approximately 2.2 × 10⁻³⁰⁸.

~~~java
double smallest = Double.MIN_VALUE;
double underflow = smallest / 2.0;

System.out.println(smallest > 0.0);   // true
System.out.println(underflow == 0.0); // true
~~~

Underflow is not necessarily an error. In some algorithms, tiny values can be ignored; in others, losing them can corrupt results. Choose thresholds, precision, and algorithms based on domain requirements.

## 5. NaN, Infinity, and Signed Zero

### NaN

NaN (Not a Number) can arise from indeterminate real operations, such as 0.0 / 0.0 or the square root of a negative number via Math.sqrt:

~~~java
double nan = 0.0 / 0.0;

System.out.println(Double.isNaN(nan)); // true
System.out.println(nan == nan);        // false
System.out.println(nan < 1.0);         // false
System.out.println(nan > 1.0);         // false
System.out.println(nan != 1.0);        // true
~~~

All relational comparisons with NaN such as <, <=, >, >= evaluate to false; == with NaN is also false, even against itself. Therefore, validating data with score < 0 || score > 100 **does not filter out NaN**: both sides evaluate to false and the program may mistakenly conclude the value is valid. Use Double.isNaN or Double.isFinite when the domain disallows NaN.

### Infinity

With double operations:

~~~java
System.out.println(1.0 / 0.0);   // Infinity
System.out.println(-1.0 / 0.0);  // -Infinity
System.out.println(1.0 / -0.0);  // -Infinity
~~~

Floating-point division by zero is unlike integer division by zero: integer division throws ArithmeticException, whereas double division can produce infinity or NaN per IEEE 754 rules.

If an API only accepts finite values, use Double.isFinite(x) rather than checking only x != Double.POSITIVE_INFINITY, because the latter misses negative infinity and NaN.

### Positive Zero and Negative Zero

IEEE 754 has both +0.0 and -0.0:

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);            // Infinity
System.out.println(1.0 / negativeZero);           // -Infinity
~~~

The == comparison treats both zeros as equal, yet the sign can affect certain operations and representations. If a domain needs to distinguish the sign of zero (e.g., specialized numerical algorithms), inspect the sign bit or use Double.compare in an appropriate context. Do not use == to assert two values share the same bit pattern.

## 6. Comparing Floating-Point Numbers: Do Not Use an Arbitrary Epsilon

Exact equality comparison:

~~~java
if (actual == expected) {
    // ...
}
~~~

is only appropriate when both values are expected to share the same representation, or the operation contractually guarantees an exact result. For results computed from multiple floating-point operations, exact comparison is usually too strict.

A common approach is comparing with a tolerance:

~~~java
Math.abs(actual - expected) <= tolerance
~~~

However, a fixed absolute tolerance does not suit all magnitudes. An error of 1e-9 may be huge when expected is near 0, yet far too small when expected is around 1e12.

### Combining Absolute and Relative Tolerance

A widely used criterion:

\[
|a-b| \leq \max(\varepsilon_{abs}, \varepsilon_{rel}\cdot\max(|a|,|b|))
\]

Where:

- absolute epsilon controls error near zero.
- relative epsilon scales with the magnitude of the two values.
- Thresholds must derive from algorithm requirements and allowable error, not a single constant applied across every domain.

Example implementation:

~~~java
static boolean nearlyEqual(
        double a,
        double b,
        double absoluteTolerance,
        double relativeTolerance) {

    if (absoluteTolerance < 0.0
            || relativeTolerance < 0.0
            || relativeTolerance > 1.0) {
        throw new IllegalArgumentException("Invalid tolerance");
    }

    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }

    if (a == b) {
        // Includes identical infinities and +0.0 vs -0.0.
        return true;
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    double allowed = Math.max(
            absoluteTolerance,
            relativeTolerance * scale);

    return difference <= allowed;
}
~~~

This function adopts the conventions that NaN equals nothing, two infinities of the same sign are equal, and +0.0/-0.0 are numerically equivalent. Those choices must match the problem's contract. If signed zero must be distinguished or NaN compared bitwise, use a different comparison API.

A practical tolerance must be determined from:

1. Data units and magnitude.
2. Number of operations and expected accumulated error.
3. Accuracy requirements of the business logic or algorithm.
4. Impact of error on threshold decisions.

### Math.ulp Is Not a Universal Epsilon

Math.ulp(x) returns the distance between x and the next representable floating-point number larger in magnitude/representation at that position. It is useful for understanding spacing at a specific value, not as a universal error threshold for every algorithm.

Example:

~~~java
System.out.println(Math.ulp(1.0));
System.out.println(Math.ulp(1.0e16));
System.out.println(Math.ulp(0.0));
~~~

Spacing grows with magnitude. An error of a few ULPs may suit a specific numerical algorithm, yet is not automatically valid for every measurement or business rule.

## 7. When Should You Use BigDecimal Instead of double?

If exact decimal numbers must follow strict business rules—such as money, invoice rates, or values requiring rounding to a specific number of decimal places—BigDecimal is generally better suited than double.

~~~java
double floatingTotal = 0.1 + 0.2;

java.math.BigDecimal decimalTotal =
        new java.math.BigDecimal("0.1")
                .add(new java.math.BigDecimal("0.2"));

System.out.println(floatingTotal); // 0.30000000000000004
System.out.println(decimalTotal);  // 0.3
~~~

### Avoid new BigDecimal(double) for Decimal Inputs

~~~java
System.out.println(new java.math.BigDecimal(0.1));
System.out.println(java.math.BigDecimal.valueOf(0.1));
System.out.println(new java.math.BigDecimal("0.1"));
~~~

- The double constructor converts the exact binary double value to BigDecimal, often producing a long unexpected digit string.
- BigDecimal.valueOf(double) relies on the canonical decimal representation of Double.toString.
- The String constructor is the clear choice when the data source is already a decimal string, such as JSON requests parsed under a decimal contract.

If the input source is already a double, BigDecimal.valueOf can match the decimal meaning represented by double's canonical string, though it cannot recover original decimal information lost when parsing into double.

### BigDecimal Still Requires Scale and Rounding Policies

BigDecimal represents decimals exactly, yet divisions with infinite decimal expansions (e.g., 1 divided by 3) require specifying scale and RoundingMode:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal result = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        2,
        RoundingMode.HALF_UP);

System.out.println(result); // 0.33
~~~

Additionally:

- BigDecimal.equals compares both value and scale; 2.0 and 2.00 are not equals.
- BigDecimal.compareTo compares numeric value; 2.0 and 2.00 have compareTo equal to 0.
- Do not choose a rounding mode merely for convenience; monetary rounding rules must follow business contracts and applicable regulations.
- For money, integers in the smallest unit can be used if the domain fixes scale clearly; for multiple currencies with differing decimal places, apply rules per Currency/unit.

## 8. Summing Many Numbers and Accumulated Error

When summing many numbers of vastly different magnitudes, small numbers can be lost when added to a large running total. Example:

~~~java
double total = 1.0e16;
total += 1.0;
total -= 1.0e16;

System.out.println(total); // 0.0
~~~

The value 1.0 can be rounded away when added to 1e16; subsequent subtraction cannot recover it.

### Ordering Additions

For some datasets, adding smaller values first before adding into a large total can reduce loss:

~~~java
double smallFirst = (1.0 + 1.0) + 1.0e16;
double largeFirst = (1.0e16 + 1.0) + 1.0;

System.out.println(smallFirst);
System.out.println(largeFirst);
~~~

This is not a general rule guaranteeing exact results for every dataset. Reordering can change outputs and sometimes adds cost; use it only when the algorithm and contract permit.

### Kahan Compensated Summation

When summing many double values, Kahan's algorithm maintains a compensation variable to recover part of the lost error:

~~~java
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
~~~

Kahan summation can improve accuracy across many sequence summations, yet it does not make double addition associative or guarantee exact results. For special sequences, extreme magnitude differences, or overflow, evaluate suitable algorithms; Neumaier summation or specialized methods may fit better.

### Math.fma

Java provides Math.fma(a, b, c) to compute a × b + c with a single final rounding instead of rounding the product and then rounding the sum:

~~~java
double a = 1.0000000000000002;
double b = 1.0000000000000002;
double c = -1.0000000000000004;

double separate = a * b + c;
double fused = Math.fma(a, b, c);

System.out.println(separate);
System.out.println(fused);
~~~

Math.fma can produce a different result from separate multiplication and addition. This is defined behavior, not a bug. Only substitute FMA when the algorithm requires fused multiply-add semantics and has been analyzed; it does not make all algebraically equivalent expressions bit-equivalent.

## 9. Boundary Testing with JUnit 5

Floating-point tests must clearly specify validity criteria, acceptable error, and boundary values. Example class:

~~~java
public final class ScoreValidator {
    private ScoreValidator() {}

    public static boolean isValid(double score) {
        return Double.isFinite(score)
                && score >= 0.0
                && score <= 100.0;
    }
}
~~~

JUnit Jupiter test:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ScoreValidatorTest {
    @Test
    void acceptsBothInclusiveBoundaries() {
        assertTrue(ScoreValidator.isValid(0.0));
        assertTrue(ScoreValidator.isValid(100.0));
    }

    @Test
    void rejectsValuesImmediatelyOutsideBoundaries() {
        assertFalse(ScoreValidator.isValid(Math.nextDown(0.0)));
        assertFalse(ScoreValidator.isValid(Math.nextUp(100.0)));
    }

    @Test
    void acceptsValuesImmediatelyInsideBoundaries() {
        assertTrue(ScoreValidator.isValid(Math.nextUp(0.0)));
        assertTrue(ScoreValidator.isValid(Math.nextDown(100.0)));
    }

    @Test
    void rejectsNonFiniteValues() {
        assertFalse(ScoreValidator.isValid(Double.NaN));
        assertFalse(ScoreValidator.isValid(Double.POSITIVE_INFINITY));
        assertFalse(ScoreValidator.isValid(Double.NEGATIVE_INFINITY));
    }
}
~~~

When testing an approximate calculation, JUnit 5 provides an overload with a delta:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

assertEquals(0.3, 0.1 + 0.2, 1.0e-12);
~~~

The delta in a test must come from requirements and calculation scale. Do not use an overly wide delta that lets tests accept wrong results; nor use an overly narrow delta that makes tests depend on error irrelevant to the business domain.

### Testing Non-Associativity

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FloatingPointTest {
    @Test
    void additionCanDependOnGrouping() {
        double a = 1.0e16;
        double b = -1.0e16;
        double c = 1.0;

        double left = (a + b) + c;
        double right = a + (b + c);

        assertEquals(1.0, left);
        assertEquals(0.0, right);
        assertNotEquals(left, right);
    }

    @Test
    void decimalFractionsAreNotAlwaysExactlyRepresentable() {
        assertNotEquals(0.3, 0.1 + 0.2);
        assertEquals(0.3, 0.1 + 0.2, 1.0e-12);
    }
}
~~~

The first test is not meant to encourage code that depends on specific outcomes of every calculation, but to demonstrate that **changing grouping can change the result**. For real algorithms, test output properties, maximum error, and extreme cases rather than merely repeating illustrative examples.

## 10. Numeric Conversions Between double and Other Types

Converting from double to int or long does not round like Math.round. Casting floating-point to integer truncates the fractional part toward 0, with clamping rules for overly large values and specific handling for NaN:

~~~java
System.out.println((int) 3.9);                 // 3
System.out.println((int) -3.9);                // -3
System.out.println((int) Double.NaN);          // 0
System.out.println((int) Double.POSITIVE_INFINITY); // Integer.MAX_VALUE
~~~

If business rules require rounding, choose Math.round, Math.floor, Math.ceil, or BigDecimal.setScale with an appropriate RoundingMode. Do not use casting as a substitute for an undefined rounding rule.

Additionally, when converting long to double, integers beyond the contiguous exact range may be rounded. When converting double to long, the fractional part is discarded and out-of-range values may saturate according to Java's conversion rules. If data represents IDs, codes, quantities, or exact integers, keep an appropriate integer type throughout the system.

## 11. Checklist of Cases to Include in a Test Suite

| Test Goal | Suggested Inputs | What to Assert |
| --- | --- | --- |
| Exactly at threshold | T | Inclusive/exclusive condition |
| Immediately below threshold | Math.nextDown(T) | Below-threshold branch |
| Immediately above threshold | Math.nextUp(T) | Above-threshold branch |
| Zero values | +0.0 and -0.0 | Signed zero rules |
| Smallest positive number | Double.MIN_VALUE | Subnormal behavior |
| Normal boundary | Double.MIN_NORMAL and adjacent values | Normal/subnormal transition |
| Finite boundary | Double.MAX_VALUE and overflowing operations | Finite/infinite result |
| NaN | Double.NaN | Validation and comparison |
| Infinity | Both infinity signs | Validation and handling branches |
| Common decimal values | 0.1, 0.2, 0.3 | Tolerance-based comparison |
| Summing mixed magnitudes | Very large numbers mixed with small numbers | Accumulated error |
| Regrouping | (a + b) + c and a + (b + c) | Do not assume identical results |
| Type conversion | Large long, out-of-range double | Precision loss, truncation/saturation |

Not every floating-point function requires all of these cases. Select based on the input domain and operations performed. For example, a function accepting a finite percentage in [0, 1] needs threshold, NaN, infinity, and boundary-adjacent tests; a long-running sensor summation algorithm also needs attention to accumulated error and summation order.

## 12. Design and Testing Principles for Floating-Point Numbers

When working with float/double on Java 17:

1. Clearly define the valid domain and inclusive/exclusive thresholds.
2. Use Math.nextDown/nextUp to generate representable values on both sides of a threshold.
3. Explicitly check for NaN and infinity if the domain accepts only finite numbers.
4. Never assume addition or multiplication is associative; changing order can change results.
5. Choose tolerances based on magnitude, units, and algorithmic error; do not use a global epsilon.
6. Use BigDecimal or integers in the smallest unit when exact decimal rules are required.
7. Use compensated summation or specialized algorithms if accumulating many values causes significant error.
8. Test valid data, boundary-adjacent values, and non-finite data; do not test only typical examples.

Floating-point numbers are very useful, yet they follow finite-representation and rounding rules. A good test suite actively verifies those rules. Understanding representation boundaries and avoiding associativity assumptions makes Java 17 programs far less vulnerable to small discrepancies that can have major consequences in real-world calculations.
