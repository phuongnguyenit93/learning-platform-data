# Negative Numbers with Division, Remainder, and Rounding in Java

## 1. Why Are Negative Numbers a Mandatory Test Case?

With positive numbers, many ways of dividing and rounding happen to produce the same result. Once negative numbers appear, previously hidden differences become clear:

- Integer division `/` in Java **truncates toward zero**, rather than rounding down toward negative infinity.
- The remainder operator `%` is **remainder**, not necessarily a non-negative modulo; when nonzero, it has the **same sign as the dividend**.
- `Math.floorDiv` and `Math.floorMod` apply division toward **negative infinity**, which helps compute periodic cycles with a positive modulus.
- Rounding `UP`/`DOWN` differs from `CEILING`/`FLOOR`. For negative numbers, the word “up” does not always mean “arithmetically larger”.
- `Math.round` and `BigDecimal.setScale(..., HALF_UP)` **do not use the same rule at negative midpoints**.

If software handles account balances, dates before a reference epoch, circular indices, negative temperatures, refunds, negative profits, or negative offsets, choosing the wrong operation can introduce bugs that are hard to notice in a test suite with only positive inputs.

This lesson belongs to **Testing and Diagnostics**: besides explaining formulas, each section shows how to construct counterexamples, compute expected results, and verify behavior in Java 17+.

## 2. Integer Division in Java: Truncation Toward Zero

The `/` operator with two integral operands (`int`, `long`, and types promoted to `int`) yields an **integer quotient truncated toward zero**. For negative numbers, this is not always the floor value.

```java
System.out.println( 7 /  3); //  2
System.out.println(-7 /  3); // -2
System.out.println( 7 / -3); // -2
System.out.println(-7 / -3); //  2
```

Key example: real division `-7 / 3 = -2.333...`, yet Java integer division produces `-2`, not `-3`.

| Expression | Real quotient | Java `int / int` | `floor(real quotient)` |
| --- | ---: | ---: | ---: |
| `7 / 3` | approx. 2.333 | 2 | 2 |
| `-7 / 3` | approx. -2.333 | -2 | -3 |
| `7 / -3` | approx. -2.333 | -2 | -3 |
| `-7 / -3` | approx. 2.333 | 2 | 2 |

Because operators have overloads by data type, `-7 / 3` and `-7.0 / 3` are also not equivalent:

```java
System.out.println(-7 / 3);     // -2
System.out.println(-7.0 / 3);   // -2.3333333333333335
```

The first diagnostic question is: **Are the operands integers or floating-point numbers?** If a real quotient is required, use the appropriate numeric type or arithmetic method and do not accidentally perform integer division before casting.

## 3. The `%` Operator Is Remainder, Not Non-Negative Modulo

For ordinary integer operands and a nonzero denominator, Java determines `q = a / b` by truncating the quotient toward 0, then:

```text
r = a - q * b
a = q * b + r
```

The `a % b` operator returns `r`. When `r != 0`, the sign of `r` matches the sign of **`a` (the dividend)**, not the sign of `b`.

```java
System.out.println( 7 %  3); //  1
System.out.println(-7 %  3); // -1
System.out.println( 7 % -3); //  1
System.out.println(-7 % -3); // -1
```

Checking the identity with `a = -7`, `b = 3`:

```text
q = -7 / 3 = -2
r = -7 % 3 = -1
q*b + r = (-2)*3 + (-1) = -7
```

In many mathematical texts, **modulo with a positive modulus** is conventionally defined in `[0, m)`. Thus `-7 mod 3` is often written as `2`; Java's `-7 % 3` is `-1`. The two operations serve different division conventions.

This causes a common bug:

```java
int size = 5;
int previous = -1;
int index = previous % size; // -1, cannot be used as an index!
```

If business logic needs a circular index in `[0, size)`, do not use `%` directly when `previous` can be negative. Use `Math.floorMod(previous, size)` after checking `size > 0`.

## 4. `Math.floorDiv` and `Math.floorMod`: Floor Division

Java provides `Math.floorDiv(int, int)` / `Math.floorDiv(long, long)` and `Math.floorMod(...)`. They use the **floored quotient** instead of the quotient truncated toward zero.

```java
System.out.println(Math.floorDiv(-7, 3));  // -3
System.out.println(Math.floorMod(-7, 3));  //  2
System.out.println(Math.floorDiv(7, -3));  // -3
System.out.println(Math.floorMod(7, -3));  // -2
System.out.println(Math.floorDiv(-7, -3)); //  2
System.out.println(Math.floorMod(-7, -3)); // -1
```

The values satisfy the identity:

```text
a = floorDiv(a,b) * b + floorMod(a,b)
```

with a special note for integer overflow in `MIN_VALUE / -1` discussed in section 10.

| `a` | `b` | `a / b` | `a % b` | `floorDiv(a,b)` | `floorMod(a,b)` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 3 | 2 | 1 | 2 | 1 |
| -7 | 3 | -2 | -1 | -3 | 2 |
| 7 | -3 | -2 | 1 | -3 | -2 |
| -7 | -3 | 2 | -1 | 2 | -1 |
| -6 | 3 | -2 | 0 | -2 | 0 |

**For `b > 0`, `floorMod(a,b)` is always in `[0,b)`.** When `b < 0`, a nonzero result has the sign of `b`, meaning it can be negative. Therefore, if you need a **non-negative** modulo, you must ensure the modulus is **positive**, rather than merely replacing `%` with `floorMod` and skipping validation.

### Scenario 1: Circular Indexing

```java
int numberOfSlots = 7;
int previousSlot = Math.floorMod(-1, numberOfSlots);
System.out.println(previousSlot); // 6
```

`-1` can represent stepping backward one position before index 0. The result 6 is valid in an array of length 7.

### Scenario 2: Partitioning into Time Intervals

Suppose you compute a millisecond offset relative to an epoch, where negative means before the epoch. With each bucket having length `1_000 ms`:

```java
long offsetMillis = -1L;
long bucket = Math.floorDiv(offsetMillis, 1_000L);
long withinBucket = Math.floorMod(offsetMillis, 1_000L);

System.out.println(bucket);       // -1
System.out.println(withinBucket); // 999
```

This is an example of time bucketing: an offset of `-1 ms` falls in time bucket `-1` at position `999 ms` inside that bucket. Using `/` and `%` would give bucket 0 and position -1, violating the convention of partitioning into `[k*1000, (k+1)*1000)`.

## 5. Distinguishing Four Rounding Directions with Negative Numbers

`java.math.RoundingMode` defines policies applied to `BigDecimal`. The most easily misunderstood names are:

| Mode | Rule | Example rounding `-1.26` to 1 decimal place |
| --- | --- | --- |
| `DOWN` | **Toward 0**: discard digits beyond scale | `-1.2` |
| `UP` | **Away from 0** if discarded part is nonzero | `-1.3` |
| `CEILING` | Toward **positive infinity** | `-1.2` |
| `FLOOR` | Toward **negative infinity** | `-1.3` |

For the positive number `1.26`, `UP` and `CEILING` both give `1.3`; `DOWN` and `FLOOR` both give `1.2`. **For negative numbers, these two pairs split**. This is why you must test both positive and negative numbers when writing a shared rounding function.

```java
BigDecimal x = new BigDecimal("-1.26");
System.out.println(x.setScale(1, RoundingMode.DOWN));    // -1.2
System.out.println(x.setScale(1, RoundingMode.UP));      // -1.3
System.out.println(x.setScale(1, RoundingMode.CEILING)); // -1.2
System.out.println(x.setScale(1, RoundingMode.FLOOR));   // -1.3
```

Standalone `BigDecimal` snippets in this lesson require `import java.math.BigDecimal;` and `import java.math.RoundingMode;`; they illustrate statements inside a method body. Section 11 provides a complete Java class that compiles and runs standalone.

### HALF Modes Have Specific Rules at Exact Midpoints

For `-1.25` rounded to 1 decimal place, the two nearest results are `-1.2` and `-1.3`. The original value lies squarely at the midpoint:

- `HALF_UP`: at an exact midpoint, choose **away from 0** → `-1.3`.
- `HALF_DOWN`: at an exact midpoint, choose **toward 0** → `-1.2`.
- `HALF_EVEN`: at an exact midpoint, choose the kept digit in the last place to be **even** → `-1.2` (digit 2 is even).

```java
BigDecimal x = new BigDecimal("-1.25");
System.out.println(x.setScale(1, RoundingMode.HALF_UP));   // -1.3
System.out.println(x.setScale(1, RoundingMode.HALF_DOWN)); // -1.2
System.out.println(x.setScale(1, RoundingMode.HALF_EVEN)); // -1.2
```

Do not interpret `HALF_UP` as “go toward positive infinity at .5”. In `BigDecimal`, for negative numbers, `HALF_UP` at a midpoint **goes away from 0**. If a tax, fee, or refund requirement involves rounding, the policy must be specified by mode name and boundary of application, rather than simply writing “round up”.

## 6. `Math.round`, `floor`, `ceil`, `rint`: Different from `BigDecimal` Rounding

`java.lang.Math` provides operations on `float`/`double`:

- `Math.floor(x)`: largest integer **not greater than** `x`, returned as `double`.
- `Math.ceil(x)`: smallest integer **not less than** `x`, returned as `double`.
- `Math.round(double)`: returns `long`, choosing the nearest integer; exact midpoints round toward **positive infinity** (corresponding to `floor(x + 0.5)` for ordinary finite inputs).
- `Math.round(float)`: similar, but returns `int`.
- `Math.rint(x)`: returns an integral `double` in the mathematical sense; at exact midpoints chooses the **even** integer.

Testing negative values:

```java
System.out.println(Math.floor(-1.5)); // -2.0
System.out.println(Math.ceil(-1.5));  // -1.0
System.out.println(Math.round(-1.5)); // -1
System.out.println(Math.round(-2.5)); // -2
System.out.println(Math.rint(-1.5));  // -2.0
System.out.println(Math.rint(-2.5));  // -2.0
```

Because `Math.round(-1.5)` gives `-1`, it **differs** from `BigDecimal("-1.5").setScale(0, HALF_UP)` which gives `-2`:

```java
System.out.println(Math.round(-1.5)); // -1
System.out.println(new BigDecimal("-1.5")
        .setScale(0, RoundingMode.HALF_UP)); // -2
```

Note: `Math.round` on `NaN` and ±`Infinity` has special handling and is not an arbitrary exact conversion; floating-point numbers can also hold `-0.0`. Do not define a contract for sensitive data with a bare phrase like “round to nearest” without specifying midpoint rules, return type, range, and special inputs.

### API Selection Rules

- Want to **compute index/bucket division** with integer multiples and negative numbers: `floorDiv`/`floorMod`.
- Want to **round a double value** to an integer using Java's `round` rule: `Math.round`.
- Want an **explicit decimal policy** for scale and rounding: `BigDecimal.setScale(scale, mode)`.
- Want to **format output** with a fixed number of decimal places: compute and round according to the policy first, then use `toPlainString()` or a locale-aware formatter.

## 7. Division and Remainder with `BigDecimal`

`BigDecimal` does not use `/` or `%` operators. It provides methods with their own contracts:

| Method | Meaning |
| --- | --- |
| `divide(divisor)` | **Exact** division if a finite decimal representation exists; if non-terminating like 1/3, may throw `ArithmeticException`. |
| `divide(divisor, scale, roundingMode)` | Divides and returns a result with the requested scale, applying the mode when needed. |
| `divideToIntegralValue(divisor)` | Takes the **integer part of the quotient toward 0**, not floor for negative numbers. |
| `remainder(divisor)` | Computes remainder using the quotient truncated toward 0; differs from non-negative modulo. |
| `divideAndRemainder(divisor)` | Returns an array containing the integral quotient and remainder under the same convention. |

```java
BigDecimal a = new BigDecimal("-7");
BigDecimal b = new BigDecimal("3");

System.out.println(a.divideToIntegralValue(b)); // -2
System.out.println(a.remainder(b));             // -1
System.out.println(a.divide(b, 2, RoundingMode.HALF_UP)); // -2.33
```

With `BigDecimal.divideToIntegralValue`, the quotient's `scale` representation can depend on the inputs and operation; examine numerical value and representation contracts separately. Calling `remainder` with a negative dividend can return a negative value, because it is **not the same as `Math.floorMod`**.

If an application truly requires **non-negative modulo on decimals with a positive modulus**, you can normalize the remainder:

```java
static BigDecimal positiveModulo(BigDecimal value, BigDecimal modulus) {
    if (modulus.signum() <= 0) {
        throw new IllegalArgumentException("modulus must be positive");
    }
    BigDecimal rem = value.remainder(modulus);
    return rem.signum() < 0 ? rem.add(modulus) : rem;
}
```

This is an **illustrative method**, to be placed in a Java class. For example, `positiveModulo(new BigDecimal("-7.5"), new BigDecimal("3"))` gives `1.5`. `Math.floorMod` is not applicable because that API accepts only primitive integers.

### `BigDecimal` Division Can Also Lose Precision According to Rounding Mode

`-7 / 3` is a non-terminating decimal. The operation:

```java
BigDecimal q = new BigDecimal("-7")
        .divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP);
System.out.println(q); // -2.33
```

is rounded to two decimal places. This is **intentional rounding**, not equivalent to integer division `-7 / 3 = -2`. If dropping digits is not allowed, `RoundingMode.UNNECESSARY` helps detect values not representable at the requested scale by throwing `ArithmeticException`.

With `BigDecimal`, do not use `new BigDecimal(0.1)` if you expect exact decimal `0.1`; construct from a string or an exact decimal source. Whether the original data is negative or positive, an input `double` error is not automatically repaired by a subsequent `setScale`.

## 8. Negative Rounding Rules in Business Logic

There is no single rounding policy right for every problem. You must clarify:

1. **What does a signed coordinate/value mean?** Negative balance, displacement, refund, debt, error offset, or days before an epoch?
2. **How do you want to partition the number line?** For `[kL, (k+1)L)` buckets, use `floorDiv`; to drop the fractional part of an index toward 0, use `/`.
3. **Should the remainder keep the dividend's sign or lie in a non-negative range?** `%` and `floorMod` differ for negative inputs.
4. **Which rounding direction?** Toward 0 (`DOWN`), away from 0 (`UP`), positive infinity (`CEILING`), negative infinity (`FLOOR`), or nearest with a midpoint rule?
5. **At which boundary is rounding applied?** Per line item, per transaction, final total, or only when formatting output?
6. **What precision must be preserved?** Exact decimal, approximate measurement, or floating-point arithmetic per standard?

For example: a refund amount of `-1.25` rounded to one decimal place. If the rule is “round to nearest, midpoint away from 0”, `HALF_UP` yields `-1.3`; if the rule is “round to nearest, midpoint to even”, `HALF_EVEN` yields `-1.2`. A difference of `0.1` can have accounting significance. Do not guess from the name “HALF_UP” and skip testing actual negative cases.

For monetary amounts, the final scale and mode must be specified by currency, regulation, or business contract. Do not assume two decimal places apply to every currency. For measurements, display rounding does not reduce the physical error of the measurement.

## 9. Bugs Easily Hidden by Positive-Only Tests

### Bug A — Negative Circular Index

```java
int size = 5;
int result = -1 % size; // -1
// accessing array[result] may throw ArrayIndexOutOfBoundsException
int fixed = Math.floorMod(-1, size); // 4
```

**Required tests:** `-1`, `-size`, `-size-1`, `0`, `size-1`, `size`, and `size+1`, while also validating `size > 0`.

### Bug B — Using `/` Instead of `floorDiv` for Pre-Epoch Times

```java
System.out.println(-1 / 1000);                 // 0
System.out.println(Math.floorDiv(-1, 1000));   // -1
```

If code partitions into 1000-unit buckets starting at 0, the bucket for `-1` should be `-1` rather than bucket 0. For real-world dates/times, prefer `java.time` when business logic involves time zones, calendars, and DST rules; the example here addresses only arithmetic partitioning.

### Bug C — Confusing `HALF_UP` with `Math.round`

```java
System.out.println(Math.round(-1.5)); // -1
System.out.println(new BigDecimal("-1.5")
        .setScale(0, RoundingMode.HALF_UP)); // -2
```

They differ at negative midpoints. Read the actual requirement instead of swapping APIs under the belief that two “rounding” calls are equivalent.

### Bug D — Reusing a Negative Modulus

```java
System.out.println(Math.floorMod(-7, 3));  //  2
System.out.println(Math.floorMod(-7, -3)); // -1
```

If the target is an index from 0 to `size - 1`, you must check `size > 0`. A `floorMod` call that is valid in Java can still violate the business domain when the modulus is negative.

### Bug E — Negative Sign Disappears After Rounding to 0

```java
BigDecimal small = new BigDecimal("-0.004");
System.out.println(small.setScale(2, RoundingMode.HALF_UP)); // 0.00
```

That is numerical value 0 at scale 2, not proof that the input was positive. If business logic needs to preserve the **original sign** or distinguish “negative but rounded to 0”, store that information separately; `BigDecimal` does not store negative zero as a distinct signed value. Conversely, `double` has `-0.0` under IEEE 754, so comparison and serialization logic must be explicitly designed if dependent on zero's sign.

## 10. Dangerous Edges: Division by 0, Overflow, `MIN_VALUE`, and Floating-Point

### 10.1. Integer Division by 0

Dividing or taking the remainder by 0 on `int` and `long` both throw `ArithmeticException` at runtime:

```java
int zero = 0;
// System.out.println(7 / zero); // ArithmeticException: / by zero
// System.out.println(7 % zero); // ArithmeticException: / by zero
```

`Math.floorDiv` and `Math.floorMod` also do not accept a 0 divisor. Validate before dividing, especially when the modulus is a collection size or user-supplied bucket length.

### 10.2. The `Integer.MIN_VALUE / -1` Case

`Integer.MIN_VALUE` is `-2147483648`. The mathematical quotient when dividing by `-1` is `2147483648`, which exceeds the `int` range. In Java, this special integer division **does not throw an exception**; it returns `Integer.MIN_VALUE` due to overflow. `Math.floorDiv` does not automatically fix type bounds:

```java
int min = Integer.MIN_VALUE;
System.out.println(min / -1);             // -2147483648
System.out.println(min % -1);             // 0
System.out.println(Math.floorDiv(min, -1)); // -2147483648
System.out.println(Math.floorMod(min, -1)); // 0
```

If you need the exact mathematical quotient, **widen the type before dividing**:

```java
long exact = (long) Integer.MIN_VALUE / -1L;
System.out.println(exact); // 2147483648
```

With `Long.MIN_VALUE / -1L`, even `long` cannot hold the quotient; consider `BigInteger` or an explicit overflow check. Do not accidentally call `Math.abs(Integer.MIN_VALUE)` to make a modulus positive: the returned value remains negative because the mathematical absolute value exceeds the `int` range.

### 10.3. Floating-Point `/` and `%` Are Not Like Integers

`double` division by 0 does not follow the same exception rule as integers: under IEEE 754, `1.0 / 0.0` is positive infinity, while `0.0 / 0.0` is `NaN`. The `%` operator with floating-point operands follows Java's remainder rule, not `Math.floorMod`, and not `Math.IEEEremainder`:

```java
System.out.println(-7.5 % 3.0); // -1.5
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(0.0 / 0.0);  // NaN
```

In real numeric processing, explicitly specify whether `NaN`/infinity is allowed, rules for converting to decimal, and binary representation errors for values not exact in `double`. Do not create a non-negative modulo for floating-point numbers by arbitrarily casting `(int) (a % b)`: conversion drops the fractional part and can be completely wrong for large ranges.

## 11. Complete Java 17+ Example with Deterministic Stdout

Save the following program into **`NegativeArithmeticDemo.java`**. It is locale-independent and prints only predictable results.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class NegativeArithmeticDemo {

    static BigDecimal positiveModulo(BigDecimal value,
                                     BigDecimal modulus) {
        if (modulus.signum() <= 0) {
            throw new IllegalArgumentException("modulus must be > 0");
        }
        BigDecimal rem = value.remainder(modulus);
        return rem.signum() < 0 ? rem.add(modulus) : rem;
    }

    public static void main(String[] args) {
        System.out.println("-7 / 3 = " + (-7 / 3));
        System.out.println("-7 % 3 = " + (-7 % 3));
        System.out.println("7 / -3 = " + (7 / -3));
        System.out.println("7 % -3 = " + (7 % -3));
        System.out.println("-7 / -3 = " + (-7 / -3));
        System.out.println("-7 % -3 = " + (-7 % -3));

        System.out.println("floorDiv(-7, 3) = "
                + Math.floorDiv(-7, 3));
        System.out.println("floorMod(-7, 3) = "
                + Math.floorMod(-7, 3));
        System.out.println("floorDiv(7, -3) = "
                + Math.floorDiv(7, -3));
        System.out.println("floorMod(7, -3) = "
                + Math.floorMod(7, -3));
        System.out.println("ring previous = "
                + Math.floorMod(-1, 5));

        System.out.println("round(-1.5) = " + Math.round(-1.5));
        System.out.println("round(-2.5) = " + Math.round(-2.5));
        System.out.println("floor(-1.5) = " + Math.floor(-1.5));
        System.out.println("ceil(-1.5) = " + Math.ceil(-1.5));
        System.out.println("rint(-1.5) = " + Math.rint(-1.5));

        BigDecimal negative = new BigDecimal("-1.25");
        System.out.println("HALF_UP = "
                + negative.setScale(1, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN = "
                + negative.setScale(1, RoundingMode.HALF_EVEN));
        System.out.println("DOWN = "
                + negative.setScale(1, RoundingMode.DOWN));
        System.out.println("UP = "
                + negative.setScale(1, RoundingMode.UP));
        System.out.println("FLOOR = "
                + negative.setScale(1, RoundingMode.FLOOR));
        System.out.println("CEILING = "
                + negative.setScale(1, RoundingMode.CEILING));

        BigDecimal a = new BigDecimal("-7");
        BigDecimal b = new BigDecimal("3");
        System.out.println("decimal quotient = "
                + a.divideToIntegralValue(b));
        System.out.println("decimal remainder = " + a.remainder(b));
        System.out.println("decimal division = "
                + a.divide(b, 2, RoundingMode.HALF_UP));
        System.out.println("positive decimal modulo = "
                + positiveModulo(new BigDecimal("-7.5"), b));

        System.out.println("MIN / -1 = "
                + (Integer.MIN_VALUE / -1));
        System.out.println("wide MIN / -1 = "
                + ((long) Integer.MIN_VALUE / -1L));
    }
}
```

Run with JDK 17 or later, in the directory containing the file:

```bash
javac NegativeArithmeticDemo.java
java NegativeArithmeticDemo
```

Expected output:

```text
-7 / 3 = -2
-7 % 3 = -1
7 / -3 = -2
7 % -3 = 1
-7 / -3 = 2
-7 % -3 = -1
floorDiv(-7, 3) = -3
floorMod(-7, 3) = 2
floorDiv(7, -3) = -3
floorMod(7, -3) = -2
ring previous = 4
round(-1.5) = -1
round(-2.5) = -2
floor(-1.5) = -2.0
ceil(-1.5) = -1.0
rint(-1.5) = -2.0
HALF_UP = -1.3
HALF_EVEN = -1.2
DOWN = -1.2
UP = -1.3
FLOOR = -1.3
CEILING = -1.2
decimal quotient = -2
decimal remainder = -1
decimal division = -2.33
positive decimal modulo = 1.5
MIN / -1 = -2147483648
wide MIN / -1 = 2147483648
```

Observe four groups of results:

1. `/` and `%` follow **truncation toward zero**, so `-7 / 3 = -2` and `-7 % 3 = -1`.
2. `floorDiv` and `floorMod` both use the floored quotient, so `-7` divided into buckets of size 3 gives quotient `-3` and remainder `2`.
3. `Math.round(-1.5)` returns `-1` while decimal `HALF_UP` at a negative midpoint rounds away from 0 to `-2` at scale 0; the program shows the corresponding difference at scale 1 for `-1.25`.
4. `Integer.MIN_VALUE / -1` does not throw an exception even though the mathematical quotient exceeds `int`; widen the type before dividing to get the exact quotient.

## 12. Writing Diagnostic Property Tests Instead of Checking Just a Few Examples

Beyond fixed-output tests, you can write **invariant** checks across many pairs of numbers:

- For `b != 0` and avoiding the special division overflow case, `a == (a / b) * b + (a % b)`.
- For `b > 0`, `Math.floorMod(a, b)` always satisfies `0 <= r < b`.
- For `b > 0` and `a < 0` not divisible by `b`, the floor quotient is 1 less than the truncated quotient.
- For `BigDecimal`, verify that `divideToIntegralValue` and `remainder` reconstruct `a` in **numerical value**, using `compareTo() == 0` instead of `equals()` if scales may differ.
- For `RoundingMode`, compare negative and positive inputs at `±1.25`, `±1.26`, and around 0.

A standalone test suite requiring no external libraries, named **`SignedDivisionChecks.java`**:

```java
public class SignedDivisionChecks {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        int cases = 0;
        for (int a = -20; a <= 20; a++) {
            for (int b = -7; b <= 7; b++) {
                if (b == 0) {
                    continue;
                }

                int quotient = a / b;
                int remainder = a % b;
                int floorQuotient = Math.floorDiv(a, b);
                int floorRemainder = Math.floorMod(a, b);

                check(a == quotient * b + remainder,
                        "Truncating identity failed");
                check(a == floorQuotient * b + floorRemainder,
                        "Floor identity failed");
                check(remainder == 0 ||
                        Integer.signum(remainder) == Integer.signum(a),
                        "Remainder sign failed");
                check(floorRemainder == 0 ||
                        Integer.signum(floorRemainder) == Integer.signum(b),
                        "Floor remainder sign failed");

                if (b > 0) {
                    check(floorRemainder >= 0 && floorRemainder < b,
                            "Nonnegative modulo range failed");
                }
                cases++;
            }
        }
        System.out.println("checked cases = " + cases);
        System.out.println("all properties passed");
    }
}
```

Run:

```bash
javac SignedDivisionChecks.java
java SignedDivisionChecks
```

Output:

```text
checked cases = 574
all properties passed
```

Here there are 41 values of `a` from `-20` to `20` and 14 nonzero values of `b` from `-7` to `7`: `41 × 14 = 574` pairs. The small range avoids overflow in the product `quotient * b`; if writing a property test over the full `int` range, you must separately handle `Integer.MIN_VALUE / -1` and overflow in the verification arithmetic, for example with `long` or `BigInteger`.

This test does not replace business-specification testing. It only verifies the arithmetic rules that the program relies upon.

## 13. Minimum Test Matrix for Negative Numbers

A good test suite must slice across **dividend sign**, **divisor sign**, **exact divisibility vs remainder**, **exact rounding midpoints**, and **boundary values**:

| Group | Suggested input | Objective |
| --- | --- | --- |
| Positive division | `7 / 3`, `7 % 3` | Baseline comparison point. |
| Negative dividend | `-7 / 3`, `-7 % 3` | Distinguish trunc and floor, negative remainder. |
| Negative divisor | `7 / -3`, `7 % -3` | Check quotient and remainder signs. |
| Both negative | `-7 / -3`, `-7 % -3` | Do not assume remainder has the divisor's sign. |
| Divisible | `-6 / 3`, `-6 % 3` | Remainder equals 0. |
| Near 0 | `-1 / 3`, `-1 % 3` | Detect wrong bucket near origin. |
| Circular modulo | `-1`, `-5`, `-6` with modulus 5 | Keep index within `[0, 5)`. |
| Negative modulus | `floorMod(-7, -3)` | Do not assume modulo is always non-negative. |
| Negative midpoint | `-1.25` to scale 1, `-1.5` to integer | Distinguish HALF_UP, HALF_EVEN, Math.round. |
| Small negative fraction | `-0.004` to scale 2 | Rounding to zero and preserving original sign. |
| Zero divisor | `7 / 0`, `floorMod(7,0)` | Intentional error handling. |
| Integer division overflow | `Integer.MIN_VALUE / -1` | Detect mathematical quotient out of range. |
| Non-terminating decimal | `-7 / 3` in BigDecimal | Choose scale and rounding mode explicitly. |
| Special floating point | `-0.0`, `NaN`, ±`Infinity` | Define input/output data policy. |

### Roadmap for Diagnosing Real-World Bugs

When logs reveal an “unexpected” negative result:

1. **Record the numeric type** of every operand: `int`, `long`, `double`, `BigDecimal`?
2. **Record the expected quotient rule**: truncate toward 0 or floor toward negative infinity?
3. **Record the expected remainder constraint**: can it be negative, must the modulus always be positive?
4. **Record the rounding policy**: scale, mode, and when it is applied.
5. **Reproduce with the smallest case**: `-7 / 3`, `-1 % 5`, `-1.25`.
6. **Check boundary values**: division by 0, overflow, negative zero, decimal/floating-point precision.
7. **Add a regression test** from the reproduced case so future code changes do not reintroduce the bug.

If replacing `%` with `floorMod`, test both old positive data, new negative data, and every path where the modulus is 0 or negative. If replacing `Math.round` with `BigDecimal.setScale`, test midpoint policies and conversions before treating it as a “behavior-preserving” refactor.

## 14. Common Misconceptions

1. **“`-7 / 3` is `-3`.”** False for Java `int` division; the result is `-2`. `Math.floorDiv(-7,3)` is `-3`.
2. **“`a % b` is always non-negative.”** False when `a` is negative. `-7 % 3 == -1`.
3. **“`Math.floorMod` is always positive.”** Not true when the divisor is negative; `floorMod(7,-3) == -2`.
4. **“`Math.round` is equivalent to `HALF_UP`.”** Not at negative midpoints; `round(-1.5) == -1` whereas decimal `HALF_UP` to integer is `-2`.
5. **“`UP` means larger on the number line.”** No. `RoundingMode.UP` means **away from 0**; for negative numbers it can make the number **more negative**.
6. **“`DOWN` means toward negative infinity.”** No. `DOWN` is **toward 0**; `FLOOR` is toward negative infinity.
7. **“`BigDecimal.remainder` is non-negative modulo.”** False; with a negative dividend, the remainder can be negative.
8. **“Integer division always detects overflow.”** False at `MIN_VALUE / -1`.
9. **“Every division by 0 in Java throws an exception.”** False for `double`/`float` in IEEE 754 cases such as `1.0/0.0`.
10. **“You can use `Math.abs(size)` to ensure a positive modulus.”** Dangerous for `Integer.MIN_VALUE`/`Long.MIN_VALUE`; validate the domain and handle boundary exceptions.
11. **“A few positive tests prove modulo works properly.”** No. Negative tests are what typically expose differences between trunc and floor.
12. **“Scale and rounding mode only affect display.”** No. Applying them to intermediate values in a formula can change the final result.

## 15. Self-Check Questions

**Question 1.** What does Java return for `-8 / 3` and `-8 % 3`?

**Answer:** `-2` and `-2` because the integer quotient is truncated toward 0: `-8 = (-2)*3 + (-2)`.

**Question 2.** What are `Math.floorDiv(-8, 3)` and `Math.floorMod(-8, 3)`?

**Answer:** `-3` and `1` because `-8 = (-3)*3 + 1`.

**Question 3.** When the modulus is `5`, why is index `-1 % 5` wrong for an array?

**Answer:** It is `-1`. `Math.floorMod(-1,5)` gives `4`, an index in `[0,5)`.

**Question 4.** Is `Math.floorMod(8, -3)` non-negative?

**Answer:** No; the result is `-1` because the floor quotient is `-3` and `8 = (-3)*(-3) + (-1)`. With a negative modulus, the floor remainder can be negative.

**Question 5.** For `BigDecimal("-1.25")`, what do you get when rounding to one decimal place with `HALF_UP` and `HALF_EVEN`?

**Answer:** `-1.3` and `-1.2`.

**Question 6.** Why is `Math.round(-2.5)` equal to `-2`?

**Answer:** `Math.round` resolves midpoints toward positive infinity; between `-3` and `-2` it chooses `-2`.

**Question 7.** What are `Math.floor(-1.2)` and `BigDecimal("-1.2").setScale(0, DOWN)`?

**Answer:** `Math.floor(-1.2) == -2.0`, whereas `DOWN` toward 0 gives `-1`.

**Question 8.** For `BigDecimal("-7")` divided by `BigDecimal("3")`, what are `divideToIntegralValue` and `remainder`?

**Answer:** Numerically `-2` and `-1`. They use the quotient truncated toward 0, not the floor quotient.

**Question 9.** Why is `Integer.MIN_VALUE / -1` dangerous even though the divisor is nonzero?

**Answer:** The mathematical quotient `2147483648` is outside the `int` range; Java division returns `Integer.MIN_VALUE` due to overflow. Widen the type before dividing or check explicitly.

**Question 10.** To test a rounding function used for negative numbers, which test groups are mandatory?

**Answer:** Positive/negative, near 0, exact midpoint and just on both sides of the midpoint, multiple rounding modes, overly large/small values, and rounding order in the pipeline.

## 16. Java 17 API References

- [Java Language Specification `15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17): rules for `/`, `%` on integral and floating-point types, division by 0, and overflow.
- [Java SE 17 — Math.floorDiv, floorMod, round](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): floor division, modulo, rounding, and boundary behavior.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): definitions of `UP`, `DOWN`, `CEILING`, `FLOOR`, and `HALF_*` modes.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `divide`, `divideToIntegralValue`, `remainder`, `setScale`, and `MathContext`.

**Takeaway:** With negative numbers, first choose the **quotient semantics** (trunc or floor), then choose the **remainder convention** (`%` or `floorMod` with positive modulus), and only then choose the **rounding rule** for decimals. Do not treat `Math.round`, `RoundingMode.HALF_UP`, `Math.floorDiv`, and `BigDecimal.remainder` as interchangeable alternatives. Small counterexamples like `-7 / 3`, `-1 % 5`, and `-1.25` will catch most mistakes very early.