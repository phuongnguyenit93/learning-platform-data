# Using `BigInteger` or Reference Calculations to Detect Overflow in Java

## 1. Why Must We Test for Overflow?

In Java, `int` and `long` are fixed-width signed integers:

| Type | Width | Minimum value | Maximum value |
| --- | ---: | ---: | ---: |
| `int` | 32 bit | `-2147483648` | `2147483647` |
| `long` | 64 bit | `-9223372036854775808` | `9223372036854775807` |

Ordinary integer addition, subtraction, and multiplication **do not throw an exception on overflow**. The result simply retains the low-order bits within the corresponding width and is interpreted as a two's-complement signed integer. Example:

~~~java
int x = Integer.MAX_VALUE;
int wrapped = x + 1; // -2147483648, no exception
~~~

The true mathematical result must be `2147483648`, one greater than `Integer.MAX_VALUE`. If an application checks only “no exception was thrown”, bugs can slip into item counts, total revenue in minor units, timestamps, memory limits, array sizes, or comparison logic.

**Core testing strategy:** compute the same operation using a representation with a large enough range as a **reference result (oracle)**, such as `BigInteger`, then compare that result against the target type's value range. For operations running in production, `Math.addExact`, `subtractExact`, `multiplyExact`, and other exact-check APIs detect overflow on the spot.

There are two separate questions:

1. **What is the true mathematical result?** Use `BigInteger`, or arithmetic in a wider type when certainty suffices.
2. **Can the result be represented exactly in `int` or `long`?** Compare against `MIN_VALUE`/`MAX_VALUE`, or use `intValueExact()`, `longValueExact()`, and the `Math.*Exact` functions.

Never immediately use an already-overflowed result as the reference answer, because not enough information remains to know the original mathematical value.

## 2. Integer Overflow Mechanics: Two's Complement and Representable Range

For an `n`-bit signed integer, the value range is:

\[
-2^{n-1} \le x \le 2^{n-1}-1.
\]

When ordinary integer addition, subtraction, or multiplication exceeds the range, Java keeps the portion fitting in 32/64 bits. You can picture the result taken modulo \(2^n\), then reinterpreted as signed.

Example `Integer.MAX_VALUE + 1`:

- Mathematical result: `2147483648 = 2^31`.
- 32-bit `int` representation has the sign bit set and remaining bits 0.
- Resulting Java `int`: `-2147483648`, i.e., `Integer.MIN_VALUE`.

For `Long.MAX_VALUE * 2`:

- Mathematical result: `18446744073709551614`.
- Ordinary `long` result: `-2`.

**No automatic overflow flag is returned by `+`, `-`, `*`.** If the application must reject overflow, actively use an exact API or check with an oracle.

This behavior is **defined by Java**, not undefined behavior. However, a deterministic result does not make it right for business requirements.

### 2.1. Do Not Confuse Overflow with Floating-Point Precision Loss

`float` and `double` follow IEEE 754 floating-point arithmetic. Exceeding limits can lead to `Infinity`, while many non-overflowing operations still round due to finite precision. This topic focuses on **`int`/`long` overflow**, with `BigInteger` as the oracle for exact integer arithmetic. Do not apply the same byte-for-byte comparison to floating-point numbers when the contract permits approximate error.

`BigDecimal` can be helpful for exact decimal arithmetic, yet when the testing target is `int`/`long` integer operations, `BigInteger` directly expresses integer results and is usually a clearer oracle.

## 3. `BigInteger` as an Independent Oracle

`BigInteger` (`java.math` package) represents integers with arbitrary precision up to machine resource limits, not restricted to 32 or 64 bits.

~~~java
import java.math.BigInteger;

long a = Long.MAX_VALUE;
long b = 2L;

long actual = a * b; // -2, overflowed long result
BigInteger expected = BigInteger.valueOf(a)
        .multiply(BigInteger.valueOf(b));
// 18446744073709551614: exact mathematical result
~~~

`BigInteger` is immutable. Operations such as `add`, `subtract`, `multiply`, `divide`, `remainder`, `pow`, and `shiftLeft` return new result objects. Thus reference calculations do not suffer `int`/`long` overflow within memory and resource constraints.

**Critical pitfall:** you must convert the **original operands** to `BigInteger` *before* computing:

~~~java
long a = Long.MAX_VALUE;
long b = 2L;

BigInteger wrongOracle = BigInteger.valueOf(a * b);
// -2: long multiplication already overflowed before BigInteger appeared!

BigInteger correctOracle = BigInteger.valueOf(a)
        .multiply(BigInteger.valueOf(b));
// 18446744073709551614
~~~

Similarly, `BigInteger.valueOf((long) (intA + intB))` is **unsafe** if the `int` addition was already performed before casting.

### 3.1. Checking Whether the Oracle Fits in `long`/`int`

~~~java
BigInteger exact = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);

boolean fitsLong =
        exact.compareTo(BigInteger.valueOf(Long.MIN_VALUE)) >= 0
        && exact.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) <= 0;
// false
~~~

For `int`, replace the bounds with `Integer.MIN_VALUE` and `Integer.MAX_VALUE`. This is a mathematically exact check that does not rely on an already-overflowed primitive result.

There is a shorter option:

~~~java
try {
    long exactLong = exact.longValueExact();
} catch (ArithmeticException ex) {
    // Value is outside the long range
}
~~~

`BigInteger`'s `intValueExact()` and `longValueExact()` throw `ArithmeticException` when the value cannot be represented exactly in the target type.

**Do not use** `exact.longValue()` or `exact.intValue()` as an overflow check: conversion methods without `Exact` can discard high-order bits and return an altered value.

## 4. `Math.*Exact` APIs Detect Overflow at the Operation

Java provides checking methods when an exact `int`/`long` result is required:

| Need | API | When out of range |
| --- | --- | --- |
| Addition | `Math.addExact(a, b)` | Throws `ArithmeticException` |
| Subtraction | `Math.subtractExact(a, b)` | Throws `ArithmeticException` |
| Multiplication | `Math.multiplyExact(a, b)` | Throws `ArithmeticException` |
| Negation | `Math.negateExact(value)` | Throws `ArithmeticException` |
| Increment/decrement by 1 | `Math.incrementExact(value)`, `Math.decrementExact(value)` | Throws `ArithmeticException` |
| Absolute value of `int`/`long` | `Math.absExact(value)` | Throws at the respective MIN value |
| Narrow `long` to `int` | `Math.toIntExact(value)` | Throws if outside int range |

Overloads and specific methods must be chosen with matching types. For example, `Math.addExact(int,int)` returns `int`, whereas `Math.addExact(long,long)` returns `long`. When both operands are `int` and a `long` result is desired, you can intentionally widen at least one operand **before adding**.

~~~java
int left = Integer.MAX_VALUE;
int right = 1;

long correct = (long) left + right;  // 2147483648
long wrong = (long) (left + right);  // -2147483648

// If the result must be int:
try {
    int checked = Math.addExact(left, right);
} catch (ArithmeticException ex) {
    // Exceeds int range, handle error per business contract
}
~~~

In `wrong`, parentheses force `int` addition first before casting to `long`, so it cannot “repair” the overflow that already happened. In `correct`, the left operand becomes `long` before addition, so addition runs in 64-bit range.

With two `long` operands, widening to `long` again does nothing. Use `Math.*Exact` or `BigInteger` to compute results larger than 64-bit range.

### 4.1. How `BigInteger` and `Math.*Exact` Complement Each Other

- **In application logic:** use `Math.*Exact` if overflow is an error that must be caught as soon as the operation executes.
- **In tests:** use an independent `BigInteger` to verify that the operation returns the exact value when in range and reports an error when out of range.
- **When valid data can genuinely exceed `long`:** use `BigInteger` in the data/result model instead of catching an error and continuing to store into `long`.
- **When a fallback such as saturating arithmetic is required:** explicitly define the contract returning `MIN_VALUE`/`MAX_VALUE`, then verify against an oracle. Do not call that exact arithmetic.

A test that merely calls `Math.addExact` and trusts it can be helpful to verify which API the application chose. Yet independent verification with `BigInteger` catches bugs in picking the wrong overload, casting in the wrong order, or inconsistent boundary handling.

## 5. Special Operations That Are Easy to Miss

### 5.1. `MIN_VALUE / -1` Division

In Java, integer division has one special overflow case:

~~~java
long wrapped = Long.MIN_VALUE / -1L;
// -9223372036854775808: does not throw ArithmeticException
~~~

The true mathematical result is `9223372036854775808`, **larger than `Long.MAX_VALUE`**. Likewise, `Integer.MIN_VALUE / -1` returns `Integer.MIN_VALUE`.

`Math.addExact` or `multiplyExact` do not cover division. In Java 17, you can check this exceptional case with a guard:

~~~java
static long divideChecked(long dividend, long divisor) {
    if (divisor == 0L) {
        throw new ArithmeticException("/ by zero");
    }
    if (dividend == Long.MIN_VALUE && divisor == -1L) {
        throw new ArithmeticException("long division overflow");
    }
    return dividend / divisor;
}
~~~

This is an illustrative method inside a class; if using `BigInteger.divide` as an oracle, remember that `BigInteger.divide` also rejects division by 0. Ordinary integer division **truncates the remainder toward 0**, rather than dividing to a real result and rounding with a decimal rounding mode.

### 5.2. Negation and Absolute Value of the Minimum Value

~~~java
int x = Integer.MIN_VALUE;

int negated = -x;         // still Integer.MIN_VALUE
int magnitude = Math.abs(x); // still Integer.MIN_VALUE
~~~

Reason: `2147483648` is not within the positive `int` range. To reject this case, use `Math.negateExact(x)` and `Math.absExact(x)` (Java 17+). If you only need the magnitude and accept `long`, use:

~~~java
long exactAbs = Math.abs((long) Integer.MIN_VALUE);
// 2147483648
~~~

Casting to `long` must occur **before** taking the absolute value. `Math.abs(Integer.MIN_VALUE)` can return a negative number, so never treat `Math.abs` as proof that a value is guaranteed non-negative.

### 5.3. Multiplication, Squaring, and Intermediate Expressions

~~~java
int x = 50_000;

long wrongSquare = x * x;         // -1794967296 then widened to long
long correctSquare = (long) x * x; // 2500000000
~~~

For multiplying two `int`s, `Math.multiplyFull(x, x)` returns the full `long` result in Java 17. For `long` multiplication, the result can exceed 64 bits; `BigInteger.valueOf(a).multiply(BigInteger.valueOf(b))` is an appropriate oracle.

`BigInteger` has `shiftLeft` for checking shifts that must preserve all bits. Meanwhile, the primitive `<<` operator always keeps the type's width and can discard high-order bits; do not rely on `Math.addExact` to detect bit loss in shifts.

### 5.4. Accumulation in Loops and Streams

~~~java
int sum = 0;
for (int value : values) {
    sum = Math.addExact(sum, value);
}
~~~

The snippet above sits inside a method with variable `int[] values`. It detects overflow at **each accumulation step**.

An independent oracle can use:

~~~java
BigInteger reference = BigInteger.ZERO;
for (int value : values) {
    reference = reference.add(BigInteger.valueOf(value));
}
~~~

Distinguish two goals:

- If the requirement is “no intermediate addition may overflow”, step-by-step checked arithmetic fits.
- If the requirement is only “the **final mathematical sum** fits in `int`”, `int` accumulation might overflow partway and then return to a valid value when negative numbers cancel it out. The `BigInteger` oracle still knows the true final sum. Depending on the contract, one rule can be stricter than the other.

For example, the array `{Integer.MAX_VALUE, 1, -1}` has a final mathematical sum equal to `Integer.MAX_VALUE`, yet step-by-step checked addition fails at the second element. Clarify whether the application must prevent overflow **at every step** or only prove the range of the **final result**.

`IntStream.sum()` returns `int` and can overflow. `mapToLong(x -> x).sum()` increases range for `int` sources, yet very large sums can still exceed `long`. If an arbitrary mathematical sum is needed, accumulate with `BigInteger`.

## 6. Complete Java 17+ Example: Comparing Results Against an Oracle

Create file `OverflowOracleDemo.java`:

~~~java
import java.math.BigInteger;
import java.util.Random;

public class OverflowOracleDemo {
    private static final BigInteger LONG_MIN =
            BigInteger.valueOf(Long.MIN_VALUE);
    private static final BigInteger LONG_MAX =
            BigInteger.valueOf(Long.MAX_VALUE);

    private static boolean fitsLong(BigInteger value) {
        return value.compareTo(LONG_MIN) >= 0
                && value.compareTo(LONG_MAX) <= 0;
    }

    private static void verifyRandomAdd() {
        Random rng = new Random(2026L);

        for (int i = 0; i < 10_000; i++) {
            long left = rng.nextLong();
            long right = rng.nextLong();
            BigInteger oracle = BigInteger.valueOf(left)
                    .add(BigInteger.valueOf(right));
            boolean fits = fitsLong(oracle);

            try {
                long got = Math.addExact(left, right);
                if (!fits || !BigInteger.valueOf(got).equals(oracle)) {
                    throw new AssertionError("undetected overflow");
                }
            } catch (ArithmeticException ex) {
                if (fits) {
                    throw new AssertionError("false overflow");
                }
            }
        }

        System.out.println("random additions: 10000 PASS");
    }

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;

        System.out.println("int wrapped: " + (max + 1));
        System.out.println("int oracle: "
                + BigInteger.valueOf(max).add(BigInteger.ONE));

        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException ex) {
            System.out.println("Math.addExact: ArithmeticException");
        }

        System.out.println("widen after: " + (long) (max + 1));
        System.out.println("widen before: " + ((long) max + 1));

        long top = Long.MAX_VALUE;
        System.out.println("long wrapped multiply: " + (top * 2));
        System.out.println("long oracle multiply: "
                + BigInteger.valueOf(top).multiply(BigInteger.TWO));

        try {
            Math.multiplyExact(top, 2L);
        } catch (ArithmeticException ex) {
            System.out.println("Math.multiplyExact: ArithmeticException");
        }

        System.out.println("long MIN / -1: "
                + (Long.MIN_VALUE / -1L));
        System.out.println("BigInteger MIN / -1: "
                + BigInteger.valueOf(Long.MIN_VALUE).negate());

        verifyRandomAdd();
    }
}
~~~

Compile and run:

~~~bash
javac OverflowOracleDemo.java
java OverflowOracleDemo
~~~

Output:

~~~text
int wrapped: -2147483648
int oracle: 2147483648
Math.addExact: ArithmeticException
widen after: -2147483648
widen before: 2147483648
long wrapped multiply: -2
long oracle multiply: 18446744073709551614
Math.multiplyExact: ArithmeticException
long MIN / -1: -9223372036854775808
BigInteger MIN / -1: 9223372036854775808
random additions: 10000 PASS
~~~

How to read the output:

- `int wrapped` is the overflowed primitive result; `int oracle` gives the true mathematical result.
- `Math.addExact` detects overflow instead of returning a wrong number.
- `widen after` performs widening **after** `int` addition, so it is too late; `widen before` converts one operand to `long` before computing.
- `long wrapped multiply` equals `-2` even though the true result is a huge positive number.
- `Long.MIN_VALUE / -1` proves integer division has a special overflow case that ordinary division does not report.
- `verifyRandomAdd` generates 10,000 `long` pairs from a fixed seed. For each pair, the `BigInteger` oracle decides whether the result fits in `long`; the test requires `Math.addExact` to return the exact number when it fits and throw when out of range. `PASS` prints only after the entire loop finishes with zero assertion failures.

This is a **logic-testing demonstration program**, not a speed benchmark. `BigInteger` typically costs more resources than primitives, yet in tests it prioritizes accuracy and oracle independence.

## 7. Boundary Testing First, Then Random Testing

Random testing is helpful, yet it does not replace boundary testing. Overflow-inducing values cluster at the edges of ranges; a test suite should start with deterministic expected cases.

| Expression | Mathematical result | Ordinary `int`/`long` | Expectation with exact checks |
| --- | --- | --- | --- |
| `Integer.MAX_VALUE + 1` | `2147483648` | `Integer.MIN_VALUE` | `Math.addExact` throws |
| `Integer.MIN_VALUE - 1` | `-2147483649` | `Integer.MAX_VALUE` | `Math.subtractExact` throws |
| `50_000 * 50_000` when both are `int` | `2500000000` | `-1794967296` | `Math.multiplyExact(int,int)` throws |
| `Long.MAX_VALUE + 1L` | `9223372036854775808` | `Long.MIN_VALUE` | `Math.addExact(long,long)` throws |
| `Long.MAX_VALUE * 2L` | `18446744073709551614` | `-2` | `Math.multiplyExact(long,long)` throws |
| `-Integer.MIN_VALUE` | `2147483648` | `Integer.MIN_VALUE` | `Math.negateExact` throws |
| `Long.MIN_VALUE / -1L` | `9223372036854775808` | `Long.MIN_VALUE` | Must handle special case or check via oracle |
| `Integer.MAX_VALUE + 0` | `2147483647` | Correct | `Math.addExact` returns result |
| `Long.MIN_VALUE * 1L` | `Long.MIN_VALUE` | Correct | `Math.multiplyExact` returns result |

Also test pairs combining `MIN_VALUE`, `MAX_VALUE`, `-1`, `0`, `1`, `2`, near-boundary numbers, symmetric negative/positive values, and large numbers. For division, distinguish **division by 0** and **`MIN_VALUE / -1` overflow**, because these are two different failure conditions.

### 7.1. Using Property-Based Testing with `BigInteger`

A useful *property* for an overflow-checking `long` addition function:

> For all `a` and `b`, let `BigInteger.valueOf(a).add(BigInteger.valueOf(b))` be the oracle. If the oracle lies within `Long.MIN_VALUE..Long.MAX_VALUE`, the function must return the exact oracle; if outside, the function must report overflow per contract.

Apply the same approach to subtraction/multiplication. You can generate inputs with `Random` using a fixed seed as in the sample program to reproduce failures. Better yet, combine with a manually curated boundary set; random `long` pairs can trigger addition overflow yet easily miss critical cases like `MIN_VALUE / -1` unless explicitly constructed.

If using a property-testing library, each failed trial should log operands, operation, oracle value, and exception to make reproduction easy. *Shrinking* helps find simpler counterexamples, yet does not diminish the value of explicit boundary testing.

### 7.2. Define the Contract Before Testing

Not every application should throw an error when exceeding a range:

- **Checked arithmetic:** overflow is an error; use `Math.*Exact` and expect `ArithmeticException`.
- **Intentional wraparound:** some hash/bit-manipulation algorithms specify arithmetic modulo \(2^{32}\) or \(2^{64}\); an oracle is still useful, yet compare **low-order bits** per specification instead of always expecting an error.
- **Saturating arithmetic:** clamp results at min/max; the oracle computes before clamping and then checks the final result.
- **Arbitrary precision:** keep values in `BigInteger` or an appropriate type rather than casting back to `long`.

Comparing `long actual` with `BigInteger.longValue()` checks only the low-order bits and **fails to detect overflow** if exact arithmetic is required. That comparison is valid only when the contract truly specifies modulo/wraparound semantics.

## 8. Detecting Overflow During Casting and Multi-Step Aggregations

### 8.1. Casting `long` to `int`

~~~java
long input = 2_147_483_648L;

int silent = (int) input; // -2147483648, drops high bits

try {
    int checked = Math.toIntExact(input);
} catch (ArithmeticException ex) {
    // input is outside the int range
}
~~~

`Math.toIntExact` only checks the **`long` → `int` conversion**. If the result already overflowed earlier while computed in `long`, it cannot recover the original value.

`BigInteger.intValueExact()` also detects values outside the `int` range:

~~~java
BigInteger large = BigInteger.valueOf(Integer.MAX_VALUE)
        .add(BigInteger.ONE);

large.intValue();      // -2147483648: bit loss
large.intValueExact(); // ArithmeticException
~~~

### 8.2. Where to Locate Bugs in a Calculation Chain

A diagnostic workflow can follow these steps:

1. **Identify the type of each operand at the moment the operation runs**: two `int`s added before assignment to `long` still add as `int`.
2. **Capture the original operands before the suspect operation**, not just the output value after it has overflowed.
3. **Compute an oracle with `BigInteger` on the original operands**, independent of the production code under test.
4. **Compare against target type bounds** and locate the first step that exceeds range.
5. **Replace operators with exact APIs or change the type model** if the contract requires rejecting overflow.
6. **Add a regression test** with the failing numbers and near-boundary values.

Be careful when debugging via logs: if logs print only a wrapped `sum`, seeing a negative number can mislead you into thinking the source data was negative. Logging original operands and unit/range semantics helps trace back to the root cause.

### 8.3. Size and Index Calculations

A classic buggy example is:

~~~java
int mid = (left + right) / 2;
~~~

When `left` and `right` are very large `int` indices, the addition can overflow even when the mathematical midpoint is valid. With `0 <= left <= right`, the expression:

~~~java
int mid = left + (right - left) / 2;
~~~

avoids adding two large indices directly when that precondition holds. Yet **do not apply this formula outside that precondition** because `right - left` can also overflow when indices have unusual signs. If you need to support all `int` values, widen to `long` first:

~~~java
long midWide = ((long) left + (long) right) / 2;
~~~

The result of dividing by two and rounding can differ when negative numbers are involved, so redefine the midpoint contract when no longer using non-negative indices. Fixing overflow must go hand in hand with preserving **computational semantics**.

## 9. Common Mistakes When Building Reference Calculations

1. **Converting to `BigInteger` after overflow already occurred:** `BigInteger.valueOf(a * b)` is no longer an oracle for the exact product if `a * b` executed in `long`.
2. **Converting back to `long`/`int` after calculation without `Exact`:** `big.longValue()` and `big.intValue()` can lose high-order bits.
3. **Assuming any addition can be fixed by a trailing cast:** `(long)(a + b)` computes `a + b` as `int` before casting.
4. **Testing only positive numbers:** negatives below `MIN_VALUE` also overflow, and negating or taking the absolute value of `MIN_VALUE` is a special case.
5. **Overlooking `MIN_VALUE / -1` division:** the primitive result overflows without throwing an exception.
6. **Confusing overflow with `float`/`double` rounding:** `BigInteger` oracles apply to exact integer arithmetic; floating-point needs appropriate testing strategies and tolerances.
7. **Reusing the formula under test as the oracle:** both sides share the same bug and fail together. Separate the reference calculation path using an independent wide/exact type.
8. **Random testing without boundary cases:** the probability of hitting `Integer.MIN_VALUE`, `Long.MAX_VALUE`, or special combinations can be tiny.
9. **Checking only the final result when the contract forbids intermediate overflow:** the final sum might land back in range after intermediate step sums exceeded it.
10. **Reporting an error after already using the corrupted value:** check for overflow where the value is produced, before using it as an index, size, limit, or payment.
11. **Switching to `BigInteger` everywhere in production unintentionally:** evaluate performance/memory and interoperability. If data ranges must always fit in `long`, exact arithmetic is usually simpler.
12. **Misbelieving `BigInteger` has absolutely no practical limits:** it has no 32/64-bit mathematical limit, yet memory, array sizes, and computation time remain finite.

## 10. Self-Check

**Question 1.** Why can `long result = Integer.MAX_VALUE + 1;` receive a negative number?

**Answer:** Both operands are added as `int` before assignment to `long`. Addition overflows first and only then widens. Write `(long) Integer.MAX_VALUE + 1` so addition executes in `long`.

**Question 2.** Is `BigInteger.valueOf(Long.MAX_VALUE * 2L)` a valid oracle?

**Answer:** No. `long` multiplication already overflowed to `-2` before conversion. The right oracle is `BigInteger.valueOf(Long.MAX_VALUE).multiply(BigInteger.TWO)`.

**Question 3.** When does `Math.addExact(a, b)` return a number, and when does it throw?

**Answer:** It returns the exact result if within the range of the invoked overload's type; it throws `ArithmeticException` if the addition exceeds that range.

**Question 4.** Does `Long.MIN_VALUE / -1L` throw an exception?

**Answer:** No; the `long` division operator returns `Long.MIN_VALUE`. The mathematical result exceeds `Long.MAX_VALUE`, so guard this case or use `BigInteger` if exact calculation is required.

**Question 5.** Can `BigInteger.longValue()` be used to detect a number too large for `long`?

**Answer:** No. Use `longValueExact()` or compare against both bounds to detect overflow; `longValue()` can drop high-order bits.

**Question 6.** What is the final mathematical sum of `{Integer.MAX_VALUE, 1, -1}`, and why might a test using `Math.addExact` fail?

**Answer:** The final exact sum is `Integer.MAX_VALUE`, yet the intermediate sum after the second element exceeds `int` range. A test rejecting any intermediate overflow fails right at that step; a test checking only the final mathematical sum needs a different oracle.

**Question 7.** If the requirement is truly arithmetic modulo \(2^{32}\), what should the oracle do?

**Answer:** Compute the exact integer result with `BigInteger`, then extract the low 32 bits per contract. When the contract intentionally specifies wraparound, having `Math.addExact` throw is not necessarily the desired behavior.

## 11. Official Documentation

- [`BigInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): arbitrary-precision integers, `valueOf`, `add`, `multiply`, `intValueExact`, `longValueExact`.
- [`Math` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `subtractExact`, `multiplyExact`, `absExact`, `negateExact`, `toIntExact`.
- [Java Language Specification 17, Integer Operations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html): integer operator semantics, conversions, arithmetic operators, and special division cases.
- [`Integer` and `Long` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): integral type bounds; see also [`Long`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html).

**Takeaway:** When testing `int`/`long` overflow, construct the reference result using `BigInteger` **before computing**, verify target type bounds, and compare expected vs actual behavior. In production logic, use `Math.*Exact` when overflow must fail immediately; when valid values exceed 64 bits, keep `BigInteger` rather than casting to primitives. Test boundary values, `MIN_VALUE / -1` division, and “cast after operation” bugs to avoid silent inaccuracies.