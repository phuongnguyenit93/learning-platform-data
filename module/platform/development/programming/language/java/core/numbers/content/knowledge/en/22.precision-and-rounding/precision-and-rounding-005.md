# CEILING and FLOOR: Rounding Toward Positive and Negative Infinity in Java

## 1. Goal and Context

When working with real or decimal numbers, "rounding" does not always mean finding the nearest integer. Sometimes the business requirement is **to pick the smallest value not lower than the original number** or **to pick the largest value not exceeding the original number**. Those are the two rounding directions **CEILING** (toward positive infinity) and **FLOOR** (toward negative infinity).

After this lesson, you will be able to:

- Explain accurately both rounding directions on the number line, including with negative numbers.
- Use `Math.ceil(double)` and `Math.floor(double)` to round to an integer value as a `double`.
- Use `BigDecimal.setScale(..., RoundingMode.CEILING/FLOOR)` to keep the desired number of decimal places.
- Distinguish `Math.ceilDiv` and `Math.floorDiv` from integer division `/`; pick the right API for pagination and index-bucketing problems.
- Recognize misconceptions regarding negative signs, binary floating-point numbers, return types, and edge cases.

## 2. Exact Definition

For a finite real number `x`:

- **Ceiling**: `ceil(x)` is **the smallest integer greater than or equal to `x`**. On the number line, the result heads toward **+∞**.
- **Floor**: `floor(x)` is **the largest integer less than or equal to `x`**. On the number line, the result heads toward **−∞**.

Mathematically, they satisfy:

```text
floor(x) <= x <= ceil(x)

Example on the number line:
...  -4     -3     -2     -1      0      1      2      3 ...
         ^ -2.7 lies between -3 and -2
           floor(-2.7) = -3      ceil(-2.7) = -2
```

Results with representative examples:

| x | CEILING | FLOOR | Explanation |
|---:|---:|---:|---|
| `2.7` | `3` | `2` | `3` is toward +∞, `2` is toward −∞ |
| `2.0` | `2` | `2` | Already an integer, so kept unchanged |
| `-2.7` | `-2` | `-3` | `-2` is greater than `-2.7`; `-3` is smaller |
| `-2.0` | `-2` | `-2` | Already an integer, so kept unchanged |
| `0.2` | `1` | `0` | Two different directions |
| `-0.2` | `0`* | `-1` | *With `double`, `Math.ceil(-0.2)` produces `-0.0` |

**Most common misconception:** "CEILING always increases the absolute value" is false. For `-2.7`, moving toward +∞ means moving **right** to `-2`, so the absolute value decreases. "FLOOR drops the fractional part" is also false for negative numbers: dropping the fractional part of `-2.7` gives `-2`, whereas `floor(-2.7) = -3`.

## 3. Rounding to an Integer Using `Math.ceil` and `Math.floor`

Java provides two static functions:

```java
public static double Math.ceil(double a);
public static double Math.floor(double a);
```

Both take a `double` and **return a `double`**, even though for normal finite inputs the resulting value equals a mathematical integer. This does **not** mean the result automatically becomes an `int` or `long`.

The following standalone program runs on Java 17+:

**File `CeilingFloorDemo.java`**

```java
import java.util.Locale;

public class CeilingFloorDemo {
    public static void main(String[] args) {
        double[] values = {2.7, 2.0, -2.7, -2.0, -0.25, 0.0, -0.0};

        for (double x : values) {
            System.out.printf(
                    Locale.ROOT,
                    "x=%s | ceil=%s | floor=%s%n",
                    x, Math.ceil(x), Math.floor(x));
        }
    }
}
```

Compile and run:

```bash
javac CeilingFloorDemo.java
java CeilingFloorDemo
```

Output:

```text
x=2.7 | ceil=3.0 | floor=2.0
x=2.0 | ceil=2.0 | floor=2.0
x=-2.7 | ceil=-2.0 | floor=-3.0
x=-2.0 | ceil=-2.0 | floor=-2.0
x=-0.25 | ceil=-0.0 | floor=-1.0
x=0.0 | ceil=0.0 | floor=0.0
x=-0.0 | ceil=-0.0 | floor=-0.0
```

Two notable characteristics:

1. `Math.ceil` is not "always add one": if `x` is already an integer, it stays unchanged.
2. IEEE 754 has two representations of zero: `+0.0` and `-0.0`. They compare equal with `==`, but have different sign bits; `Math.ceil(-0.25)` produces `-0.0`, not `+0.0`.

### Floating-Point Edge Cases

Per the API contract:

- For `Double.NaN`, both functions return `NaN`.
- For `Double.POSITIVE_INFINITY` or `Double.NEGATIVE_INFINITY`, they return that same infinity value.
- For `+0.0` or `-0.0`, the sign of zero is preserved.
- If the input is already a mathematically integer `double` value, it returns itself.
- Many very large `double` numbers can no longer represent any fractional part; rounding cannot recover digits that were already lost earlier.

A separate check:

```java
public class SpecialValues {
    public static void main(String[] args) {
        System.out.println(Math.ceil(Double.NaN));
        System.out.println(Math.floor(Double.POSITIVE_INFINITY));
        System.out.println(Math.ceil(Double.NEGATIVE_INFINITY));
        System.out.println(Double.doubleToRawLongBits(Math.ceil(-0.25))
                == Double.doubleToRawLongBits(-0.0));
    }
}
```

```bash
javac SpecialValues.java
java SpecialValues
```

```text
NaN
Infinity
-Infinity
true
```

## 4. Distinguishing from `Math.round`, Casting, and Rounding by Magnitude

These four operations answer different questions:

| Operation | `2.7` | `-2.7` | Meaning |
|---|---:|---:|---|
| `Math.ceil(x)` | `3.0` | `-2.0` | Smallest integer ≥ x |
| `Math.floor(x)` | `2.0` | `-3.0` | Largest integer ≤ x |
| `Math.round(x)` | `3` | `-3` | Nearest integer; equidistant ties choose +∞ |
| `(int) x` | `2` | `-2` | Truncates fractional part, toward 0, with type conversion rules |

An example highlighting the difference on negative numbers:

```java
public class RoundingComparison {
    public static void main(String[] args) {
        double x = -2.3;
        System.out.println(Math.ceil(x));
        System.out.println(Math.floor(x));
        System.out.println(Math.round(x));
        System.out.println((int) x);
    }
}
```

```bash
javac RoundingComparison.java
java RoundingComparison
```

```text
-2.0
-3.0
-2
-2
```

For `-2.3`, CEILING is `-2.0`, FLOOR is `-3.0`; `Math.round` picks the nearest integer `-2`; casting truncates the fractional part to `-2`. Matching results in this example do not mean the operations are equivalent.

**Note when casting results to integer types:** Converting `double` to `int` or `long` can lose range and special information. Java converts `NaN` to `0`, and out-of-range values saturate to the bounds of the target type. Therefore, if an integer is needed for storage, check `Double.isFinite(x)`, value range, and required rules before casting. Do not use casting as a way to validate input data.

## 5. Rounding at Decimal Places: `BigDecimal` and `RoundingMode`

`Math.ceil`/`Math.floor` round to an integer value. If you need to round to **2 digits after the decimal point**, **tens**, or any `scale`, use `BigDecimal.setScale(int, RoundingMode)`:

- `RoundingMode.CEILING`: picks the nearest representable value toward **+∞** when discarding digits.
- `RoundingMode.FLOOR`: picks the nearest representable value toward **−∞** when discarding digits.

At `scale = 2`, valid points are spaced `0.01` apart; at `scale = 0`, valid points are integers; at `scale = -1`, valid points are multiples of 10. Both modes apply consistently whether the number is positive or negative.

| Original value | Scale | CEILING | FLOOR |
|---:|---:|---:|---:|
| `12.341` | 2 | `12.35` | `12.34` |
| `-12.341` | 2 | `-12.34` | `-12.35` |
| `12.300` | 2 | `12.30` | `12.30` |
| `121` | −1 | `130` | `120` |
| `-121` | −1 | `-120` | `-130` |

Standalone program:

**File `DecimalCeilingFloor.java`**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalCeilingFloor {
    public static void main(String[] args) {
        for (String input : new String[]{"12.341", "-12.341"}) {
            BigDecimal value = new BigDecimal(input);
            BigDecimal ceiling = value.setScale(2, RoundingMode.CEILING);
            BigDecimal floor = value.setScale(2, RoundingMode.FLOOR);

            System.out.println(input + " -> CEILING=" + ceiling
                    + ", FLOOR=" + floor);
        }

        BigDecimal value = new BigDecimal("-121");
        System.out.println("To tens: CEILING="
                + value.setScale(-1, RoundingMode.CEILING).toPlainString()
                + ", FLOOR="
                + value.setScale(-1, RoundingMode.FLOOR).toPlainString());
    }
}
```

```bash
javac DecimalCeilingFloor.java
java DecimalCeilingFloor
```

```text
12.341 -> CEILING=12.35, FLOOR=12.34
-12.341 -> CEILING=-12.34, FLOOR=-12.35
To tens: CEILING=-120, FLOOR=-130
```

### Things to Remember with `BigDecimal`

1. **Construct from decimal strings:** prefer `new BigDecimal("12.341")` or validated string inputs. `new BigDecimal(0.1)` introduces the inexact binary representation of `double`, which can alter results at rounding boundaries. If starting from a `double` and accepting the decimal representation from `Double.toString`, `BigDecimal.valueOf(double)` is usually more suitable than the `double` constructor.
2. **`BigDecimal` is immutable:** `setScale` returns a new value; assign the result. The original does not mutate on its own.
3. **`scale` differs from `precision`:** `setScale(2, ...)` keeps 2 digits *after the decimal point*, not 2 significant digits. `MathContext` manages precision (number of significant digits), which can take the same rounding mode but solves a different problem.
4. **`CEILING` differs from `UP` and `FLOOR` differs from `DOWN`:** `UP` moves **away from 0**; `DOWN` moves **toward 0**. For example, rounding `-1.231` to scale 2: CEILING = `-1.23`, FLOOR = `-1.24`, UP = `-1.24`, DOWN = `-1.23`.
5. **Values equal to 0:** `BigDecimal` does not have a way to store `-0.0` like IEEE 754. `new BigDecimal("-0.001").setScale(2, RoundingMode.CEILING)` gives `0.00`.

## 6. Directed Integer Division: `Math.ceilDiv` and `Math.floorDiv`

If a problem starts with **two integers**, there is no need to convert to `double` to divide and then call `Math.ceil`/`Math.floor`. Java has:

- `Math.floorDiv(a, b)`: integer quotient rounded toward −∞ (available since Java 8 for `int`/`int`).
- `Math.ceilDiv(a, b)`: integer quotient rounded toward +∞ (available since Java 18).
- Integer division `a / b`: drops the fractional part of the quotient, truncating toward 0.

Comparison across signs:

| a | b | `a / b` | `Math.ceilDiv(a,b)` | `Math.floorDiv(a,b)` |
|---:|---:|---:|---:|---:|
| 8 | 3 | 2 | 3 | 2 |
| −8 | 3 | −2 | −2 | −3 |
| 8 | −3 | −2 | −2 | −3 |
| −8 | −3 | 2 | 3 | 2 |
| 9 | 3 | 3 | 3 | 3 |

The following program requires **Java 18+** (Java 21 recommended):

**File `IntegerCeilingFloor.java`**

```java
public class IntegerCeilingFloor {
    public static void main(String[] args) {
        int[][] samples = {{8, 3}, {-8, 3}, {8, -3}, {-8, -3}};

        for (int[] sample : samples) {
            int a = sample[0];
            int b = sample[1];
            System.out.println(a + "/" + b + ": trunc=" + (a / b)
                    + ", ceil=" + Math.ceilDiv(a, b)
                    + ", floor=" + Math.floorDiv(a, b));
        }
    }
}
```

```bash
javac IntegerCeilingFloor.java
java IntegerCeilingFloor
```

```text
8/3: trunc=2, ceil=3, floor=2
-8/3: trunc=-2, ceil=-2, floor=-3
8/-3: trunc=-2, ceil=-2, floor=-3
-8/-3: trunc=2, ceil=3, floor=2
```

**Limits to check:** division by `0` throws `ArithmeticException`. With `Integer.MIN_VALUE / -1` (or `Long.MIN_VALUE / -1`), the mathematical quotient exceeds the integer type's range: standard `ceilDiv`/`floorDiv` overloads have special overflow behavior. If overflow detection is required, use `Math.ceilDivExact`/`Math.floorDivExact` (Java 18+) or pick a safer type/algorithm. Do not mechanically do `Math.ceil((double) a / b)` and cast to int: converting to `double` can lose precision on large integers.

### When to Use `ceilMod` and `floorMod`?

Since Java 18, `Math.ceilMod(a,b)` pairs with `ceilDiv(a,b)`; `Math.floorMod(a,b)` pairs with `floorDiv(a,b)`. They satisfy the arithmetic identities within the corresponding `int`/`long` domain (subject to Java integer rules):

```text
a = ceilDiv(a,b) * b + ceilMod(a,b)
a = floorDiv(a,b) * b + floorMod(a,b)
```

With `a = -8`, `b = 3`: `floorDiv = -3`, `floorMod = 1`; `ceilDiv = -2`, `ceilMod = -2`. The remainder operator `%` corresponding to truncation toward 0 gives `-8 % 3 = -2` and cannot replace `floorMod` in problems requiring a non-negative modulo index when `b > 0`.

## 7. Practical Applications

### 7.1. Minimum Pages to Hold All Records

Given `totalItems >= 0` records, each page holding at most `pageSize > 0`. The required number of pages is the ceiling of the quotient. With Java 18+:

```java
public class PaginationExample {
    public static int pageCount(int totalItems, int pageSize) {
        if (totalItems < 0 || pageSize <= 0) {
            throw new IllegalArgumentException("Invalid pagination arguments");
        }
        return Math.ceilDiv(totalItems, pageSize);
    }

    public static void main(String[] args) {
        System.out.println(pageCount(21, 10));
        System.out.println(pageCount(20, 10));
        System.out.println(pageCount(0, 10));
    }
}
```

```bash
javac PaginationExample.java
java PaginationExample
```

```text
3
2
0
```

Reason: 21 items occupy 2 full pages and 1 partial page; round up so no item is left out. For large data exceeding `int`, consider the `long` overload.

### 7.2. Bucketing When Indices Can Be Negative

Suppose a time axis is partitioned into buckets of width 60 units, centered at origin 0. Index `-1` belongs to bucket `[-60, 0)`, so the bucket ID should be `-1`, not `0`:

```java
System.out.println(-1 / 60);                 // 0: truncates toward 0
System.out.println(Math.floorDiv(-1, 60));   // -1: proper bucket [-60, 0)
System.out.println(Math.floorDiv(61, 60));   // 1: proper bucket [60, 120)
```

This is an **illustrative code snippet**; place it inside a method (such as `main`) to run. `Math.floorDiv` is useful when grouping integers both before and after the 0 mark.

### 7.3. Rounding Rules for Currency or Weight Units

If a policy requires choosing **a payment amount not lower than the calculated amount**, you can use `RoundingMode.CEILING` at the specified `scale`. If required to choose **an amount not exceeding the value**, use `RoundingMode.FLOOR`. For negative values, the result still always follows the exact direction on the number line. Before applying in a real system, clearly specify rules for refunds, negative amounts, currency units, and business regulations; do not vaguely infer "always round money up".

## 8. Common Mistakes and How to Avoid Them

| Mistake | Why it is wrong | Correct approach |
|---|---|---|
| Thinking `ceil(-2.7) == -3` | Confusing +∞ direction with away from 0 | `Math.ceil(-2.7) == -2.0` |
| Thinking `floor(-2.7) == -2` | Confusing with fractional truncation | `Math.floor(-2.7) == -3.0` |
| Using `(int) (a / b)` to compute page count | Integer division already drops remainder | `Math.ceilDiv(a,b)` for `a >= 0, b > 0` |
| Using `Math.ceil(x * 100) / 100` for all monetary amounts | `double` multiplication/division has binary error | Use `BigDecimal` from an exact decimal source and `setScale(2, mode)` |
| Confusing `CEILING` with `UP` | For negative numbers, moving toward +∞ moves closer to 0 | Choose according to "toward +∞" vs "away from 0" |
| Forgetting the return type of `Math.ceil` | Result is `double`, may have NaN/infinity/−0.0 | Keep `double` or validate before converting types |
| Forgetting to check `pageSize > 0` | Integer division by zero throws an error | Validate inputs before `ceilDiv` |
| Believing `Math.ceil` fixes pre-existing error | Precision may already be lost when creating `double` | Use `BigDecimal`/the right data type from the source |

**Self-check tip:** For finite values with meaningful results, CEILING must never be less than the input; FLOOR must never be greater than the input. Floating-point NaN comparisons must be handled separately because all order comparisons with `NaN` return `false`.

## 9. Self-Check Exercises with Solutions

1. What are `Math.ceil(-4.01)` and `Math.floor(-4.01)`?  
   **Answer:** `-4.0` and `-5.0`. CEILING goes toward +∞, FLOOR goes toward −∞.
2. What do `new BigDecimal("-5.301").setScale(2, RoundingMode.CEILING)` and `FLOOR` return?  
   **Answer:** `-5.30` and `-5.31`. The spacing of values at scale 2 is 0.01.
3. There are 31 records, at most 10 per page. How many pages are needed?  
   **Answer:** `Math.ceilDiv(31, 10) == 4` (Java 18+).
4. Why is `Math.floorDiv(-1, 10) == -1` while `-1 / 10 == 0`?  
   **Answer:** The first takes the floor of the quotient `-0.1`, while the second truncates the quotient toward 0.
5. Is `Math.ceil(-0.25) == 0.0` true?  
   **Answer:** True when compared with `==`, though the result is represented as `-0.0`, differing in sign bit from `+0.0`.

## 10. Takeaway and References

Start from **the direction of the result on the number line**, then pick the API by data type:

- Real numbers needing rounding to an integer value as `double`: `Math.ceil` or `Math.floor`.
- Decimal numbers needing control over digits after the decimal point, especially exact base-10 values: `BigDecimal.setScale(scale, RoundingMode.CEILING/FLOOR)`.
- Quotient of two integers: `Math.ceilDiv` or `Math.floorDiv` (check Java version, zero cases, and overflow).

Official API documentation:

- [Java 21 — `java.lang.Math`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [Java 21 — `java.math.RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
- [Java 21 — `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
