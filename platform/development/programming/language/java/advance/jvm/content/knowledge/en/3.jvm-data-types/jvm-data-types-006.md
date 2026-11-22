# IEEE 754 Floating-Point Numbers in the JVM: NaN, Infinity, Signed Zero, and Consistency

## Learning Objectives

Java's `float` and `double` types do not store every real number in the mathematical sense. They store a finite set of **binary floating-point values** along with special values according to the IEEE 754 model. After this lesson, you can:

- Explain the structure, precision, and value range of `float`/`double` according to IEEE 754.
- Predict results when operations produce **NaN**, **positive/negative infinity**, and **signed zero** (`+0.0`, `-0.0`).
- Distinguish arithmetic comparison `==` from `Double.equals`, `Double.compare`, and bit comparison; understand the impact on collections.
- Understand rounding, overflow, underflow, reproducibility of Java 17+ operations, and practical limits of consistency.
- Write programs that validate numeric data, choose appropriate comparisons/operations, and avoid bugs when transmitting data or handling financial calculations.

## 1. Java's Two Floating-Point Types and the IEEE 754 Model

Java has two primitive floating-point types:

| Property | `float` | `double` |
| --- | --- | --- |
| IEEE 754 format | binary32 | binary64 |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Encoded exponent bits | 8 | 11 |
| Stored significand bits (fraction) | 23 | 52 |
| Significand precision with implicit bit for normal numbers | 24 bits | 53 bits |
| Approximate significant decimal digits | about 6–9 depending on representation purpose | about 15–17 depending on representation purpose |
| Smallest positive normal value | `Float.MIN_NORMAL` | `Double.MIN_NORMAL` |
| Smallest positive non-zero value (subnormal) | `Float.MIN_VALUE` | `Double.MIN_VALUE` |
| Largest finite positive value | `Float.MAX_VALUE` | `Double.MAX_VALUE` |

In Java, the literal `1.25` is `double` by default, while `1.25f` is `float`. Use `double` when there is no clear reason to need the precision/storage space of `float`; do **not** assume that `double` computes every decimal value exactly.

For **normal** and non-zero numbers, the binary value is interpreted in the form:

~~~text
(-1)^sign × (1.fraction) × 2^(storedExponent - bias)
~~~

Where `bias` is 127 for binary32 and 1023 for binary64. The leading `1` bit of the significand in a normal number is implicit and therefore not stored directly.

Special cases by exponent/fraction bits:

| Exponent bits | Fraction bits | Meaning |
| --- | --- | --- |
| Not all 0s and not all 1s | Any | Finite normal number |
| All 0s | All 0s | Zero; the **sign bit** distinguishes `+0.0` and `-0.0` |
| All 0s | Has a 1 bit | **Subnormal** number, allowing magnitude to gradually approach 0 |
| All 1s | All 0s | Infinity `+Infinity` or `-Infinity` according to the sign bit |
| All 1s | Has a 1 bit | **NaN** (*Not a Number*) |

In Java's constant naming, `Double.MIN_VALUE` is **not** the smallest finite negative number; it is the **smallest positive non-zero number**, in the subnormal range. To get the negative number with the largest finite absolute value, use `-Double.MAX_VALUE`.

### Why can decimal representation be inaccurate?

The decimal fraction `0.1` has an infinite binary expansion and cannot be encoded exactly in finite-bit binary64. Therefore:

~~~java
double result = 0.1 + 0.2;
System.out.println(result);        // 0.30000000000000004
System.out.println(result == 0.3); // false
~~~

This is an **illustrative snippet placed inside a Java method**. Two different rounded representations are involved: the sum of the number close to `0.1` and the number close to `0.2` does not match the bit pattern of the literal `0.3`. For floating-point data, tiny representation errors can accumulate across many operations; you should not use `==` to ask whether two approximate results are "close enough" according to business requirements.

## 2. NaN: A Result That Cannot Be Represented as a Number

**NaN** stands for *Not a Number*. It can appear in operations that do not have a defined real/infinite numeric value, such as:

~~~java
double a = 0.0 / 0.0;                         // NaN
double b = Double.POSITIVE_INFINITY
         - Double.POSITIVE_INFINITY;         // NaN
double c = 0.0 * Double.POSITIVE_INFINITY;   // NaN
double d = Math.sqrt(-1.0);                   // NaN
~~~

That is an **illustrative snippet**, not a standalone class. There is no `ArithmeticException` merely because a `double` operation divides by 0. This differs from integer division, for example `int x = 1 / 0;` causes an error due to division by zero (with a constant expression like that, the compiler may accept it and throw when evaluated).

### How does NaN propagate?

For most standard floating-point operations, if one operand is NaN, the result is also NaN, for example `Double.NaN + 1.0`, `Double.NaN * 2.0`, and `Double.NaN / 3.0`. Specific APIs may define custom NaN handling, so you should read the method's contract rather than assuming every library function behaves like arithmetic operators.

**NaN is "unordered" when compared using operators:** `NaN == NaN` returns `false`, even for the same variable; `NaN != NaN` returns `true`. Any ordering comparison using `<`, `<=`, `>`, `>=` with at least one NaN returns `false`.

| Expression | Result |
| --- | --- |
| `Double.NaN == Double.NaN` | `false` |
| `Double.NaN != Double.NaN` | `true` |
| `Double.NaN < 1.0` | `false` |
| `Double.NaN >= 1.0` | `false` |
| `Double.isNaN(Double.NaN)` | `true` |
| `Double.isFinite(Double.NaN)` | `false` |

A logic trap: with NaN, the condition `!(x >= y)` is **not equivalent** to `x < y`. If `x` is NaN, `x >= y` is `false`, so negating it yields `true`, whereas `x < y` is still `false`. Do not write range validation using two branches `x < min` and `x > max` while forgetting NaN: both will be `false`, letting NaN slip through. Check finiteness first.

**Use APIs instead of comparing with NaN:**

~~~java
if (Double.isNaN(value)) {
    // Handle undefined measurement.
}

if (!Double.isFinite(value)) {
    // Exclude both NaN and both infinities when business logic requires a finite number.
}
~~~

The two snippets above illustrate check conditions, not standalone programs.

## 3. Positive/Negative Infinity and Overflow

IEEE 754 has two infinity values: `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY` (similarly for `Float`).

Some scenarios:

| Floating-point operation | Result |
| --- | --- |
| `1.0 / 0.0` | `Infinity` |
| `-1.0 / 0.0` | `-Infinity` |
| `Double.MAX_VALUE * 2.0` | `Infinity` (overflow) |
| `1.0 / Double.POSITIVE_INFINITY` | `0.0` |
| `Double.POSITIVE_INFINITY + 3.0` | `Infinity` |
| `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` |
| `0.0 * Double.POSITIVE_INFINITY` | `NaN` |

**Overflow** when a mathematically finite result exceeds the format threshold can produce infinity (depending on sign and rounding rules). **Infinity is not the same as the largest finite value**: `Double.MAX_VALUE` is still finite; `Double.isFinite(Double.POSITIVE_INFINITY)` is `false`.

`Infinity` and `-Infinity` participate in arithmetic ordering: `Double.POSITIVE_INFINITY > Double.MAX_VALUE` is `true`; `Double.NEGATIVE_INFINITY < -Double.MAX_VALUE` is `true`. Any such comparison expression must still consider the possibility of NaN appearing, because NaN has no place in the ordering of `<` and `>` operators.

**Do not use infinity arbitrarily as a sentinel value.** In some algorithms, infinity has a clear meaning, such as an initially unknown distance; however, feeding infinity into sums, averages, or normalization operations can produce NaN. You must explicitly document the rule for handling "no data" instead of conflating NaN, infinity, and `null`.

## 4. Signed Zero: `+0.0` and `-0.0`

With `float`/`double`, the **two forms of zero** have equal numeric value when using the `==` operator:

~~~java
System.out.println(0.0 == -0.0);  // true
System.out.println(0.0 < -0.0);   // false
System.out.println(1.0 / 0.0);    // Infinity
System.out.println(1.0 / -0.0);   // -Infinity
~~~

This is an illustrative snippet inside a method; a complete runnable program appears below.

IEEE 754 preserves a sign bit on zero so that information about the direction of a value is retained in operations such as division, multiplication, and certain functions. For example, `-0.0` can arise from a negative number too small to represent being rounded to 0; the result of `1.0 / -0.0` still carries the negative sign.

Some useful rules:

- Multiplying or dividing with zero can propagate the sign according to the sign rules of the operation; `-1.0 * 0.0` yields `-0.0`.
- The result of adding/subtracting zero also depends on rounding rules; you cannot assume "whenever there is a negative zero operand, the result is always negative zero." For example, `-0.0 + 0.0` yields `+0.0` in standard rounding mode.
- `Math.min(-0.0, +0.0)` returns `-0.0` and `Math.max(-0.0, +0.0)` returns `+0.0`.
- The two zeros have different bit patterns; `Double.doubleToRawLongBits(-0.0)` has the sign bit set, whereas `Double.doubleToRawLongBits(+0.0)` does not.
- For many problems, distinguishing the sign of zero is unnecessary; for numerical computing, ordering rules, bit testing, or serialization, the difference can be very important.

**Do not use `x == 0.0` to check the sign of zero.** Check the bits if you need to accurately distinguish `-0.0` and `+0.0`:

~~~java
boolean isNegativeZero = Double.doubleToRawLongBits(x)
        == Double.doubleToRawLongBits(-0.0d);
~~~

This is an illustrative snippet using a variable `x` of type `double`. Note that this test only returns `true` for **exact negative zero**, not for all negative numbers; nor does it replace a NaN check.

## 5. Three Different Relations: Operators, Wrappers, and Bit Patterns

A confusion that causes collection bugs: **primitive `double` using `==` has different rules from `Double.equals` and `Double.compare`**.

### A. Numeric comparison using operators `==` and `<`

- `+0.0 == -0.0` is `true`.
- `NaN == NaN` is `false`.
- NaN is neither less than, greater than, nor equal to any value, including NaN.
- Because NaN breaks the reflexivity of `==`, this operator **does not form an equivalence relation** over the entire set of `double`.

Suitable for arithmetic comparisons, but usually **not suitable** for directly modeling the `equals` contract in object/collection types.

### B. `Double.equals` and `Double.compare`

The `Double` wrapper defines different semantics so that `equals` is reflexive and `compare` forms a total order:

| Comparison | Result |
| --- | --- |
| `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` | `true` |
| `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` | `false` |
| `Double.compare(-0.0, +0.0) < 0` | `true` |
| `Double.compare(Double.NaN, Double.NaN) == 0` | `true` |
| `Double.compare(Double.NaN, Double.POSITIVE_INFINITY) > 0` | `true` |

The ordering established by `Double.compare` has the form:

~~~text
-Infinity < finite negative numbers < -0.0 < +0.0
          < finite positive numbers < +Infinity < NaN
~~~

All NaNs are treated as equal by `Double.compare` for comparison purposes. This rule aligns with `Double.equals` and supports `HashSet<Double>`, `HashMap<Double, ...>`, `TreeSet<Double>`, `TreeMap<Double, ...>` structures without violating standard equals/ordering contracts.

Consequence: a `HashSet<Double>` can contain **both `-0.0` and `+0.0`** as two distinct elements, whereas adding multiple different NaNs will be treated as the same element according to `Double.equals`.

### C. Exact bit comparison

The API `Double.doubleToRawLongBits(x)` returns the *raw* representation bits of `double`. The API `Double.doubleToLongBits(x)` **normalizes all NaNs to a canonical NaN bit pattern** before returning the `long` value.

| Purpose | Appropriate API |
| --- | --- |
| Check if a value is NaN? | `Double.isNaN(x)` |
| Check if a value is finite? | `Double.isFinite(x)` |
| Compare/key with consistent wrapper semantics | `Double.equals`, `Double.compare` |
| Distinguish `-0.0` from `+0.0` by bits | `Double.doubleToRawLongBits(x)` |
| Preserve/inspect NaN payload at bit level when possible | `Double.doubleToRawLongBits(x)` |
| Treat all NaNs as one canonical representation | `Double.doubleToLongBits(x)` |

IEEE 754 allows **multiple NaN bit patterns** with different payloads. Java operations generally treat them as a single generic NaN value. You must not assume operations will preserve the payload; in particular, a **signaling NaN** may be converted to a quiet NaN on some architectures, even when passed through bit-conversion APIs. For `float`, the corresponding APIs are `Float.floatToRawIntBits` and `Float.floatToIntBits`.

## 6. Runnable Java 17+ Example and Verified Output

Create the file **`Ieee754Demo.java`** (the filename must match the `public class`):

~~~java
public class Ieee754Demo {
    public static void main(String[] args) {
        double nan = 0.0 / 0.0;
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = -1.0 / 0.0;
        double positiveZero = +0.0;
        double negativeZero = -0.0;

        System.out.println("nan=" + Double.isNaN(nan));
        System.out.println("nanSelfEquals=" + (nan == nan));
        System.out.println("nanSelfNotEquals=" + (nan != nan));
        System.out.println("positiveInfinity=" + positiveInfinity);
        System.out.println("negativeInfinity=" + negativeInfinity);
        System.out.println("infinityIsFinite=" + Double.isFinite(positiveInfinity));
        System.out.println("signedZerosEqual=" + (positiveZero == negativeZero));
        System.out.println("positiveZeroReciprocal=" + (1.0 / positiveZero));
        System.out.println("negativeZeroReciprocal=" + (1.0 / negativeZero));
        System.out.println("boxedZerosEqual=" +
                Double.valueOf(positiveZero).equals(Double.valueOf(negativeZero)));
        System.out.println("negativeZeroBeforePositiveZero=" +
                (Double.compare(negativeZero, positiveZero) < 0));
        System.out.println("boxedNaNsEqual=" +
                Double.valueOf(nan).equals(Double.valueOf(Double.NaN)));
        System.out.println("nanAfterInfinity=" +
                (Double.compare(nan, positiveInfinity) > 0));
        System.out.println("overflow=" + (Double.MAX_VALUE * 2.0));
        System.out.println("halfSmallestSubnormal=" + (Double.MIN_VALUE / 2.0));
        System.out.println("decimalSum=" + (0.1 + 0.2));
        System.out.println("decimalEqual=" + (0.1 + 0.2 == 0.3));
    }
}
~~~

Compile and run (using JDK 17 or newer):

~~~bash
javac Ieee754Demo.java
java Ieee754Demo
~~~

**Exact stdout:**

~~~text
nan=true
nanSelfEquals=false
nanSelfNotEquals=true
positiveInfinity=Infinity
negativeInfinity=-Infinity
infinityIsFinite=false
signedZerosEqual=true
positiveZeroReciprocal=Infinity
negativeZeroReciprocal=-Infinity
boxedZerosEqual=false
negativeZeroBeforePositiveZero=true
boxedNaNsEqual=true
nanAfterInfinity=true
overflow=Infinity
halfSmallestSubnormal=0.0
decimalSum=0.30000000000000004
decimalEqual=false
~~~

Explanation of potentially surprising lines:

1. `0.0 / 0.0` produces NaN, yet `nan == nan` is still `false` due to operator rules.
2. Dividing by `+0.0` and `-0.0` yields two infinities of opposite signs.
3. `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` returns `false`, even though the `==` operator returns `true`.
4. `Double.compare` places negative zero before positive zero and NaN even after positive infinity.
5. Multiplying beyond the finite range produces infinity; dividing `Double.MIN_VALUE` in half is rounded to `+0.0` because the exact value lies halfway between 0 and the smallest positive subnormal number, following the round-to-nearest, *ties to even* rule.
6. `0.1 + 0.2` demonstrates binary error; the literal `0.3` does not have the same binary64 result after rounding.

**Example scope:** the lines above intentionally have no user input or parallel computation, so the order and stdout are deterministic in Java 17+. The code requires no libraries outside Java SE.

## 7. Rounding, Overflow, Underflow, and Subnormal Numbers

**Rounding:** many arithmetic operations on floating-point numbers produce a real result that may not lie in the set of representable values. The JVM must round to return a `float` or `double`. Java 17+ arithmetic operators use the round-to-nearest, *ties to even* rule for the operations covered by the specification. This does not mean every library function is automatically computed with infinite precision before rounding; functions such as `sin` or `log` have their own accuracy contracts.

**Overflow:** an absolute result too large for the finite range can lead to infinity.

**Underflow:** an absolute magnitude too small can lead to **subnormal** numbers and eventually to `+0.0` or `-0.0`. The *gradual underflow* mechanism avoids immediately rounding every value smaller than `MIN_NORMAL` to 0.

**Precision:** `float` has 24 effective significand bits, `double` has 53 bits. Increasing precision from `float` to `double` can help reduce error, but **does not turn operations into infinite-precision real arithmetic**.

An easy-to-test example of the spacing between representable values:

~~~java
System.out.println(Math.nextUp(1.0) > 1.0); // true
System.out.println(1.0 + Math.ulp(1.0) > 1.0); // true
~~~

This is an illustrative snippet inside a Java method. `Math.ulp(x)` returns the width of the unit in the last place according to the Java specification; `Math.nextUp(x)` moves to the next floating-point value in the increasing direction. **ULP depends on the magnitude of x**, not a single global epsilon constant for the entire domain.

### Impact of operation order

Floating-point addition is generally **not associative** like ideal real-number addition, due to rounding at each step. For example, in `double`:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

In the second expression, `b + c` loses `1.0` because the magnitude difference is too large; different grouping orders lead to different results. Therefore, changing the order of addition, splitting tasks in parallel, or changing how reductions are performed can change the last bits of the result even though every individual operation complies with IEEE 754. You cannot equate "consistency" with "results invariant under every operation order."

Some problems requiring higher accuracy can use compensated summation algorithms such as Kahan summation, pairwise summation, high-precision arithmetic, or accumulating in a deterministic order. The choice depends on error and performance requirements; there is no single solution applicable to all applications.

## 8. Consistency Across JVMs and the Role of `strictfp`

In Java versions prior to 17, floating-point semantics historically allowed some intermediate results to use an **extended exponent range** in non-strict contexts. Starting with **Java 17**, JEP 306 restores **always-strict floating-point semantics**: Java floating-point operations follow strict rules according to the specification, and `strictfp` is no longer needed to achieve these semantics.

- The `float`/`double` types are tied to IEEE 754 binary32/binary64 formats, including special values and subnormals.
- Java 17+ floating-point expressions are always subject to strict rules, reducing differences of the "wider intermediate exponent" kind across platforms/JVMs.
- The `strictfp` keyword may still be encountered in legacy code, but in Java 17+ it **no longer has any effect to make operations stricter** and may trigger a compiler warning as unnecessary.
- The compiler and JVM may optimize within the bounds permitted by Java rules; they must not arbitrarily reorder expressions if doing so changes observable results in ways the specification does not allow.

**Distinguish two layers of consistency:**

1. **Basic operator semantics per JLS/JVMS:** given the same program, the same data, and the same evaluation order, strictly specified operations produce results according to Java rules, rather than depending on the JVM arbitrarily keeping intermediate values in excess precision.
2. **Whole-application reproducibility:** can still differ due to parallel computation order, input data, dependencies, versions, and mathematical function contracts. Do not promise bit-for-bit reproducibility for *every* function and environment just because `double` is used.

### `Math`, `StrictMath`, `Math.fma`, and Remainder

- Many `Math` operations have specified accuracy bounds (for example in ULP units), but not all transcendental functions guarantee identical bits across all implementations and versions. When reproducible results are needed for appropriately specified functions, check the specific contract of `StrictMath`.
- `Math.fma(a, b, c)` computes a **fused** multiply-add with a single final rounding according to the FMA contract. `a * b + c` is a two-operation expression, usually rounding after multiplication and then after addition; they **can differ**. Do not treat this as an IEEE 754 bug.
- Java's `%` operator on `float`/`double` uses **truncation-style remainder** rules, which is not identical to IEEE 754 remainder that picks the nearest quotient. When you need the IEEE 754 remainder as defined by the method, use `Math.IEEEremainder(x, y)`.
- Type conversions and library methods must be evaluated according to their specifications. For example, casting from `double` to `int` converts NaN to `0`, while numbers too large in the positive/negative direction may be clamped to `Integer.MAX_VALUE`/`Integer.MIN_VALUE`; do not assume it throws an exception on invalid data.

## 9. Choosing Comparison Operations by Purpose

### Validating input data

If the business domain only allows finite numbers:

~~~java
static double requireFinite(double x) {
    if (!Double.isFinite(x)) {
        throw new IllegalArgumentException("Expected a finite number");
    }
    return x;
}
~~~

This is an **illustrative method**, which must be placed in a class when run. `Double.isFinite` excludes both NaN and both infinities, but **accepts `-0.0` and `+0.0`**. If negative zero has a distinct meaning in the system, it must be handled separately using bit APIs or intentional normalization.

### Comparing two approximate results

If calculations have error and the business logic defines an acceptance threshold, you should define an **absolute tolerance** and/or **relative tolerance** according to the value domain, instead of using a single arbitrary `EPSILON` for all cases:

~~~java
static boolean approximatelyEqual(
        double a, double b, double absTol, double relTol) {

    if (absTol < 0 || relTol < 0 ||
            !Double.isFinite(absTol) || !Double.isFinite(relTol)) {
        throw new IllegalArgumentException("Invalid tolerances");
    }
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true; // Including both infinities of the same sign and both zeros.
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double distance = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return distance <= Math.max(absTol, relTol * scale);
}
~~~

This is an **illustrative method**, not a standalone program. The formula is only a starting point for standard numerical problems: the subtraction `a - b` can overflow even when both `a` and `b` are finite; choose tolerances and robust algorithms according to the problem domain. Do not automatically use "approximately equal" for `equals` or `HashMap` keys because approximate equality is generally **not transitive**.

### Sorting floating-point numbers

If you need to sort `Double`, use `Double.compare` or `Comparator.naturalOrder()` for a total order, keeping in mind that NaN is last and negative zero/positive zero are distinguished. If the business logic wants NaN first or treats both zeros as equal, define custom rules **consistent with the equals/ordering of the structure being used**; do not arbitrarily swap comparators and then assume `TreeSet` and `HashSet` have the same semantics.

### Monetary or decimal calculations matching business expectations

Use `BigDecimal` (with explicit scale and `RoundingMode`) for cases requiring exactness in base 10, such as monetary prices:

~~~java
import java.math.BigDecimal;

BigDecimal first = new BigDecimal("0.1");
BigDecimal second = new BigDecimal("0.2");
System.out.println(first.add(second)); // 0.3
~~~

This is an illustrative snippet inside a Java method (requires the import). Avoid `new BigDecimal(0.1)` if you want the exact **decimal value 0.1**: the constructor taking `double` preserves the approximate binary value passed in. `BigDecimal.valueOf(0.1)` uses the string form of `double` and is often more convenient, but when you have native decimal input, creating from a **decimal string** is clearest.

## 10. Bugs and Real-World Scenarios

| Scenario | Typical mistake | How to handle |
| --- | --- | --- |
| Result `0.1 + 0.2` does not equal literal `0.3` | Using `==` for approximate decimal results | Define domain-specific tolerance or use `BigDecimal` for exact decimals |
| Validate `x >= min` and `x <= max` | Not excluding NaN; some negated forms easily miss NaN | `Double.isFinite(x)` before range checks |
| Dividing `double` by 0 | Expecting `ArithmeticException` like `int` division | Validate denominator/business domain and handle NaN/infinity |
| Very large numbers become `Infinity` | Assuming all `double` results are finite | Check `Double.isFinite` and design overflow controls |
| Very small values become `0.0` | Assuming every non-zero number is preserved after operations | Understand subnormals, underflow, and precision limits |
| Two `Double`s holding `-0.0` and `+0.0` in a `HashSet` | Assuming wrapper `equals` is equivalent to the `==` operator | Choose clear data types and normalization rules |
| Custom comparator using `a < b ? -1 : a > b ? 1 : 0` | NaN becomes "equal" to every number via the last branch | Use `Double.compare(a,b)` when a total order is needed |
| Numeric results across parallel tasks differ in last digits | Assuming floating-point addition is associative | Control aggregation order or use stable summation algorithms |
| Passing NaN/infinity over JSON or database | Assuming all external data formats support special IEEE values | Check schema/protocol, validate, and encode per contract |
| Tests comparing raw NaN payloads across all architectures | Assuming NaN payloads are preserved across all operations | Only require raw bits when API/transport guarantees them; treat NaN semantically if appropriate |

### Meaningful testing suggestions

For functions taking `double`, test suites should include **positive/negative finite numbers**, `+0.0`, `-0.0`, `Double.MIN_VALUE`, `Double.MIN_NORMAL`, `Double.MAX_VALUE`, `Double.NaN`, `Double.POSITIVE_INFINITY`, and `Double.NEGATIVE_INFINITY`. For accumulation algorithms, test sequences with large magnitude differences and different addition orders. For serialization, verify whether external format contracts accept or reject special floating-point values as expected.

## 11. Self-Check Questions

**Question 1.** Why is `Double.NaN == Double.NaN` `false`, whereas `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` is `true`?

**Answer:** The `==` operator on primitives uses IEEE 754's numeric comparison relation, in which NaN is unordered; the wrapper `Double.equals` uses a representational equivalence relation, normalizing NaNs into the same class for the `equals` contract.

**Question 2.** `+0.0 == -0.0` is `true`, so are `1.0 / +0.0` and `1.0 / -0.0` equal?

**Answer:** No. The results are `+Infinity` and `-Infinity`. Signed zeros differ in representation even though they are considered equal by `==`.

**Question 3.** When is `Double.isNaN(x)` insufficient to guard a function that only accepts finite numbers?

**Answer:** When the input is `Infinity` or `-Infinity`; these two values are not NaN. Use `Double.isFinite(x)`.

**Question 4.** Why does `(a + b) + c` sometimes differ from `a + (b + c)` even though Java 17+ has always-strict floating-point semantics?

**Answer:** Each addition can round to a representable value. Changing the grouping order changes the rounding steps; strict semantics guarantee the rules for executing operations, not turning floating-point arithmetic into an associative operation.

**Question 5.** With `Double.compare`, what are the positions of NaN and the two zeros?

**Answer:** `-0.0` is less than `+0.0`, and NaN is placed **greater than every other number**, including positive infinity.

**Question 6.** Is `Double.MIN_VALUE` the smallest negative value?

**Answer:** No. It is the **smallest positive non-zero value** in subnormal form. The finite negative value farthest from 0 in absolute value is `-Double.MAX_VALUE`.

**Question 7.** If you need to add money `0.1` and `0.2` to get exact `0.3` in base 10, what should you use?

**Answer:** Use `BigDecimal` created from the strings `"0.1"` and `"0.2"` or an exact decimal source, along with rounding/scale rules designed for the business domain.

## 12. Mind Map

~~~text
float   = IEEE 754 binary32  → 1 sign + 8 exponent + 23 fraction
double  = IEEE 754 binary64  → 1 sign + 11 exponent + 52 fraction

Values:   finite | subnormal | +0.0 / -0.0 | ±Infinity | NaN

Operator == : +0.0 == -0.0       ; NaN != NaN
Double.equals/compare: distinguishes ±0.0 ; groups all NaNs into the same class
Raw bits   : can observe the sign of 0 and NaN payload
isFinite   : excludes NaN and ±Infinity

Java 17+ is always strict, but changing addition order can still change the result.
~~~

**Key takeaway:** IEEE 754 floating-point numbers are not mathematical real numbers with infinite precision. **NaN** represents undefined results, **infinity** handles magnitudes exceeding limits and certain special operations, **±0.0** retains sign information; to achieve consistency, you must choose the right comparison semantics, know rounding rules, and control operation order/range.

## Authoritative References

- [Java Language Specification 21 — §4.2.3 Floating-Point Types and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).
- [Java Language Specification 21 — §15.4 Floating-point Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.4).
- [Java SE 21 API — java.lang.Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html).
- [OpenJDK JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306).
