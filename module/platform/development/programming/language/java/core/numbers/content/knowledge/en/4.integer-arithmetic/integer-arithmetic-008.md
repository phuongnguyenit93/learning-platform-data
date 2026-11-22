# `Math.floorDiv`, `Math.floorMod`, and Differences from `/` and `%` in Java

For positive integers, both ways of computing quotients and remainders usually yield the same result:

```java
System.out.println(7 / 3);                 // 2
System.out.println(7 % 3);                 // 1
System.out.println(Math.floorDiv(7, 3));   // 2
System.out.println(Math.floorMod(7, 3));   // 1
```

However, when **negative numbers** are involved, the results differ. Java defines `/` on integers as **truncating division** (rounding the quotient toward zero), whereas `Math.floorDiv` rounds the quotient **down toward negative infinity** (*floor division*). Correspondingly, `%` is the **remainder** under truncating division, whereas `Math.floorMod` computes the remainder under floor division.

The most important example:

```java
System.out.println(-7 / 3);                 // -2
System.out.println(-7 % 3);                 // -1
System.out.println(Math.floorDiv(-7, 3));   // -3
System.out.println(Math.floorMod(-7, 3));   // 2
```

If a problem handles circular indices, time-interval bucketing, grid cell coordinates, or negative numbers, confusing `%` and `floorMod` can cause logic bugs even though the program compiles cleanly.

## 1. Distinguishing "Truncating Division" and "Floor Division"

Given two integers `x` and `y`, with `y != 0`:

- `x / y` computes the integer quotient by **discarding the fractional part toward zero**.
- `Math.floorDiv(x, y)` computes the quotient by **rounding down to the greatest integer less than or equal to the mathematical quotient**.

For example, the mathematical quotient of `-7 / 3` is approximately `-2.333…`. Rounding **toward 0** gives `-2`; rounding **down toward negative infinity** gives `-3`.

| `x` | `y` | Mathematical quotient | `x / y` | `Math.floorDiv(x, y)` |
| ---: | ---: | ---: | ---: | ---: |
| 7 | 3 | 2.333… | 2 | 2 |
| −7 | 3 | −2.333… | −2 | −3 |
| 7 | −3 | −2.333… | −2 | −3 |
| −7 | −3 | 2.333… | 2 | 2 |
| −6 | 3 | −2 | −2 | −2 |
| −1 | 3 | −0.333… | 0 | −1 |

**When division is exact**, both approaches produce the same quotient. **When there is a remainder and the two operands have opposite signs**, `floorDiv` is strictly one less than `/`. When both operands have the same sign, the quotient is non-negative, so truncating toward zero matches rounding down. This holds for integers in normal representable ranges, except for the `MIN_VALUE / -1` overflow case noted separately in section 6.

Java performs `int` and `long` division entirely using integers. There is no need—and it is usually inadvisable—to convert to `double` and call `Math.floor`: for `long` values larger than `2^53`, `double` can lose precision, corrupting quotients and bucket boundaries.

## 2. Distinguishing `%` and `Math.floorMod`

The remainder is defined alongside **how the quotient is rounded**.

With Java's standard division:

```text
q = x / y
r = x % y
x = q * y + r
```

With floor division:

```text
q = Math.floorDiv(x, y)
r = Math.floorMod(x, y)
x = q * y + r
```

The identities above describe the arithmetic relationship between quotient and remainder. When computing `q * y` yourself using `int`/`long`, note that multiplication can overflow in boundary cases; do not use this recomputation as an unchecked replacement for `floorMod`. The `MIN_VALUE / -1` case also has its own quotient overflow exception.

### Full Results Table with Negative Signs

| `x` | `y` | `x / y` | `x % y` | `floorDiv(x,y)` | `floorMod(x,y)` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 3 | 2 | 1 | 2 | 1 |
| −7 | 3 | −2 | −1 | −3 | 2 |
| 7 | −3 | −2 | 1 | −3 | −2 |
| −7 | −3 | 2 | −1 | 2 | −1 |
| −6 | 3 | −2 | 0 | −2 | 0 |
| −1 | 3 | 0 | −1 | −1 | 2 |

Note the two sign rules:

1. `x % y` has the **same sign as the dividend `x`**, or is `0`. Thus `-7 % 3` equals `-1`, not `2`.
2. `Math.floorMod(x, y)` has the **same sign as the divisor `y`**, or is `0`. Thus `Math.floorMod(-7, 3)` equals `2`, while `Math.floorMod(7, -3)` equals `-2`.

In particular, when **`y > 0`**, `Math.floorMod(x, y)` always lies in the range **`0 <= r < y`**, even when `x` is negative. This is the property usually desired for circular indices or non-negative modular grouping.

When **`y < 0`**, `floorMod` satisfies **`y < r <= 0`**. Do not call `floorMod` "always non-negative" without ensuring a **positive divisor**.

### Verifying the Formula with Negative Numbers

With `x = -7`, `y = 3`:

- Standard division: `q = -2` and `r = -1`, so `-7 = (-2) * 3 + (-1)`.
- Floor division: `q = -3` and `r = 2`, so `-7 = (-3) * 3 + 2`.

With `x = 7`, `y = -3`:

- Standard division: `q = -2` and `r = 1`, so `7 = (-2) * (-3) + 1`.
- Floor division: `q = -3` and `r = -2`, so `7 = (-3) * (-3) + (-2)`.

Both models are internally consistent; the difference lies in **the rule for choosing the quotient** and consequently **the rule for choosing the remainder**.

## 3. Mechanism Creating the Difference

For integers `x` and `y` excluding division by zero:

- If division is **exact**, both models give the same quotient and remainder `0`.
- If division **has a remainder and both operands share the same sign**, the mathematical quotient is positive, so truncating toward zero is the same as rounding down; the two models coincide.
- If division **has a remainder and the two operands have opposite signs**, the mathematical quotient is negative with a fractional part. `/` rounds up toward zero, while `floorDiv` takes the value one unit smaller; `floorMod` adjusts the remainder accordingly by the divisor.

Let `q0 = x / y` and `r0 = x % y`. When `r0 != 0` and `x`, `y` have opposite signs, this can be described mathematically as:

```text
qFloor = q0 - 1
rFloor = r0 + y
```

Otherwise, `qFloor = q0` and `rFloor = r0`. This explains the mechanism, not a recommendation to hand-roll floor division everywhere: Java provides `Math.floorDiv`/`Math.floorMod`, which are clearer and handle integer edge cases.

**Note on division:** with integers, `-1 / 3` is `0`, not `-0.333…`. Java does not keep fractional parts in an `int` result. Writing `-1.0 / 3` makes it floating-point and yields approximately `-0.333…`; `Math.floorDiv` is only for integer types, not `double`.

## 4. `Math.floorDiv` and `Math.floorMod` API

Common overloads in `java.lang.Math` include:

```java
int q1 = Math.floorDiv(-7, 3);
long q2 = Math.floorDiv(-7L, 3L);
long q3 = Math.floorDiv(-7L, 3);

int r1 = Math.floorMod(-7, 3);
long r2 = Math.floorMod(-7L, 3L);
int r3 = Math.floorMod(-7L, 3);
```

The return type of `floorDiv(long, int)` is `long`, whereas the return type of `floorMod(long, int)` is `int` because the magnitude of the remainder is always smaller than the magnitude of the divisor. The `int,int` overloads return `int` and `long,long` return `long`.

**There are no equivalent overloads for `float` and `double`.** To work with floating-point numbers, specify the appropriate floating-point rounding/remainder rules (e.g., `Math.floor` or `Math.IEEEremainder` have different rules). Do not mechanically apply integer rules to floating-point numbers that carry representation error.

`floorDiv` and `floorMod` have existed since Java 8, so they work on Java 17+. They do not mutate input variables: they return new values, just like arithmetic operators.

### Divisor Equal to 0

`/`, `%`, `Math.floorDiv`, and `Math.floorMod` on integer types all throw `ArithmeticException` if the **divisor is 0**:

```java
int size = 0;
// int invalid = 10 % size;            // Throws ArithmeticException at runtime.
// int alsoInvalid = Math.floorMod(10, size); // Also throws ArithmeticException.
```

Never call modulo with an empty collection size or zero bucket count. If `y` comes from outside, check `y != 0` first, and for problems requiring a non-negative remainder, enforce the stronger check `y > 0`.

## 5. Application 1: Circular Indexing and Non-Negative Modulo

Suppose we want to step backward one position in a 5-element ring. Valid indices are `0, 1, 2, 3, 4`. Stepping backward from position `0` must wrap to `4`.

```java
int capacity = 5;
int current = 0;

int wrong = (current - 1) % capacity;            // -1: not a valid index.
int correct = Math.floorMod(current - 1, capacity); // 4.
```

Reason: `%` preserves the sign of the dividend `-1`. Meanwhile, `Math.floorMod(-1, 5)` normalizes into `[0, 4]`.

For counters that can go negative or logical positions needing mapping to a circular index, the necessary condition is a **positive divisor**:

```java
static int wrapIndex(long logicalIndex, int capacity) {
    if (capacity <= 0) {
        throw new IllegalArgumentException("capacity must be positive");
    }
    return Math.floorMod(logicalIndex, capacity);
}
```

This is an illustrative method snippet, not a standalone program. The `Math.floorMod(long, int)` overload returns `int`, making it handy when the logical index uses `long` while the array/buffer has an `int capacity`.

With `capacity = 5`, `wrapIndex(-1, 5)` returns `4`; `wrapIndex(5, 5)` returns `0`; `wrapIndex(-6, 5)` returns `4`. Circular indexing is a **modulo mapping**. It does not prevent race conditions or control overwriting in a multithreaded ring buffer.

**Another mistake:** using `Math.abs(index % capacity)` to avoid negative numbers. With `index = -1` and `capacity = 5`, this yields `1`, whereas the true circular index is `4`. Moreover, `Math.abs(Integer.MIN_VALUE)` stays negative due to overflow. Use `floorMod` when a non-negative remainder is needed.

## 6. Application 2: Interval Grouping, Bucketing, and Negative Time

Suppose a timeline is measured in integer seconds relative to epoch `0`. Each bucket is 60 seconds wide, and timestamps **before** `0` must be bucketed.

For timestamp `t = -1`:

```java
long t = -1L;
long bucketWrong = t / 60;                  // 0: truncates toward 0.
long bucketCorrect = Math.floorDiv(t, 60);  // -1: bucket [-60, -1].
int secondsIntoBucket = Math.floorMod(t, 60); // 59.
```

Under the floor bucket model:

```text
t = bucketIndex * 60 + offset
-1 = (-1) * 60 + 59
```

That is, timestamp `−1` lies in the bucket starting at `−60` with an offset of `59` seconds. Using `t / 60` places `−1` into bucket `0`, which breaks fixed intervals of the form `[k*60, (k+1)*60)`.

Several examples with 60-second buckets:

| `t` (seconds) | `t / 60` | `floorDiv(t,60)` | `t % 60` | `floorMod(t,60)` |
| ---: | ---: | ---: | ---: | ---: |
| 61 | 1 | 1 | 1 | 1 |
| 60 | 1 | 1 | 0 | 0 |
| 0 | 0 | 0 | 0 | 0 |
| −1 | 0 | −1 | −1 | 59 |
| −60 | −1 | −1 | 0 | 0 |
| −61 | −1 | −2 | −1 | 59 |

This rule fits partitioning negative coordinates into grid cells, grouping integers into fixed-width bands, or bucketing relative timestamps (once the data domain and reference frame are defined). For real-world time data, also watch milliseconds/nanoseconds units, time zones, calendars, and time boundaries; `floorDiv` only solves **integer division**, not all time-domain business logic.

### Grid Coordinates That Can Be Negative

Suppose each cell is 10 units wide. Coordinate `x = -1` should fall in the cell from `−10` to `−1`:

```java
int cellWidth = 10;
int coordinate = -1;
int cellNumber = Math.floorDiv(coordinate, cellWidth); // -1
int offset = Math.floorMod(coordinate, cellWidth);     // 9
```

Using `coordinate / cellWidth` would assign cell `0`, creating distortion at negative coordinates. This is a common bug when partitioning a coordinate space centered at `0`.

## 7. Important Edge Case: Overflow of Minimum Integer Divided by `−1`

Java has a special case: `Integer.MIN_VALUE` equals `-2147483648`, while the positive number `2147483648` **does not fit in `int`**. Therefore:

```java
int min = Integer.MIN_VALUE;
System.out.println(min / -1);                 // -2147483648
System.out.println(Math.floorDiv(min, -1));   // -2147483648
System.out.println(min % -1);                 // 0
System.out.println(Math.floorMod(min, -1));   // 0
```

Mathematically, the exact quotient should be `2147483648`. Java returns `Integer.MIN_VALUE` because integer division encounters **overflow**; no exception is thrown in this case. `Math.floorDiv` does not automatically detect that overflow either. Likewise, `Long.MIN_VALUE / -1L` and `Math.floorDiv(Long.MIN_VALUE, -1L)` return `Long.MIN_VALUE`.

This **does not invalidate the floor rule** in normal ranges. It reminds us that even `floorDiv` returns a finite `int`/`long` value, so the operation can lose the mathematical result when exceeding the representable range.

If business logic must compute the exact quotient in this case, widen **before dividing**:

```java
long exactIntQuotient = (long) Integer.MIN_VALUE / -1;
// exactIntQuotient = 2147483648L.
```

If `long` operands can encounter `Long.MIN_VALUE / -1L` and an exact integer result larger than `long` is needed, consider `BigInteger` (with zero-divisor validation) or explicitly guard for the overflow condition.

Other key pairs to remember:

- For both `x % y` and `floorMod(x, y)`, an **exact** division by `y` always has remainder `0` (when `y != 0`).
- With a positive divisor, `floorMod(Integer.MIN_VALUE, 3)` is still a value in `0..2`; there is no need to take the absolute value of large negative numbers.
- If `y = Integer.MIN_VALUE`, the divisor is negative; the `floorMod` result can be negative. Never call `Math.abs(y)` to "turn it into a positive modulus", because `Math.abs(Integer.MIN_VALUE)` overflows.

## 8. Avoiding Confusion with "Modulo" and Other APIs' Operations

In mathematics, "positive modulo" is often used to pick a representative of a congruence class in `0..m-1` for `m > 0`. In Java, `%` is the **remainder** from truncating division; it can be negative. `Math.floorMod(x, m)` with `m > 0` matches the non-negative modulo representative.

Some documentation informally calls `a % b` "modulo". When reading, check examples with negative numbers and the API contract before inferring which operation is used.

### Relation to `BigInteger`

`BigInteger.divide`/`remainder` apply truncating quotient and matching remainder rules. `BigInteger.mod(m)` returns a non-negative result but requires `m` to be **positive**; if the modulus is non-positive, it throws `ArithmeticException`. It does not fully replace `Math.floorMod` for negative-divisor cases.

```java
// Illustrative snippet where java.math.BigInteger is imported:
BigInteger x = BigInteger.valueOf(-7);
System.out.println(x.remainder(BigInteger.valueOf(3))); // -1
System.out.println(x.mod(BigInteger.valueOf(3)));       // 2
```

If an integer range larger than `long` is needed, choose `BigInteger`; do not pass a very large `long` through `double` to attempt floor rounding.

## 9. Standalone Java 17+ Example

Create a file `FloorArithmeticDemo.java`:

```java
public class FloorArithmeticDemo {
    public static void main(String[] args) {
        int[][] pairs = {
                {7, 3}, {-7, 3}, {7, -3},
                {-7, -3}, {-6, 3}, {-1, 3}
        };

        for (int[] pair : pairs) {
            int x = pair[0];
            int y = pair[1];
            System.out.println(
                    "x=" + x + ", y=" + y
                            + " | /=" + (x / y)
                            + ", %=" + (x % y)
                            + ", floorDiv=" + Math.floorDiv(x, y)
                            + ", floorMod=" + Math.floorMod(x, y));
        }

        System.out.println("Circular index (-1, 5): " + Math.floorMod(-1, 5));
        System.out.println(
                "Bucket for -1 sec: q=" + Math.floorDiv(-1, 60)
                        + ", offset=" + Math.floorMod(-1, 60));

        int min = Integer.MIN_VALUE;
        System.out.println("MIN / -1: " + (min / -1));
        System.out.println("MIN floorDiv -1: " + Math.floorDiv(min, -1));
        System.out.println("MIN floorMod -1: " + Math.floorMod(min, -1));

        int modFromLong = Math.floorMod(-7L, 3);
        System.out.println("Long dividend, int divisor: " + modFromLong);

        try {
            Math.floorMod(10, 0);
        } catch (ArithmeticException ex) {
            System.out.println("Division by zero: ArithmeticException");
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac FloorArithmeticDemo.java
java FloorArithmeticDemo
```

Stdout:

```text
x=7, y=3 | /=2, %=1, floorDiv=2, floorMod=1
x=-7, y=3 | /=-2, %=-1, floorDiv=-3, floorMod=2
x=7, y=-3 | /=-2, %=1, floorDiv=-3, floorMod=-2
x=-7, y=-3 | /=2, %=-1, floorDiv=2, floorMod=-1
x=-6, y=3 | /=-2, %=0, floorDiv=-2, floorMod=0
x=-1, y=3 | /=0, %=-1, floorDiv=-1, floorMod=2
Circular index (-1, 5): 4
Bucket for -1 sec: q=-1, offset=59
MIN / -1: -2147483648
MIN floorDiv -1: -2147483648
MIN floorMod -1: 0
Long dividend, int divisor: 2
Division by zero: ArithmeticException
```

The program demonstrates all four sign combinations of the two operands, exact division, dividends near zero, mapping negative indices onto a ring, and negative bucketing. It also verifies overflow at `Integer.MIN_VALUE / -1` and the exception when the divisor is `0`.

## 10. Process for Choosing Operators in Real Problems

| Requirement | Preference | Reason |
| --- | --- | --- |
| Integer division wanting quotient **truncated toward zero** | `/` | Matches Java's default integer division semantics |
| Remainder under truncating division; sign matches dividend | `%` | Use when the contract requires Java remainder |
| Partitioning into integer buckets/grid cells, possibly containing negative values | `Math.floorDiv` | Group boundaries consistent with floor rounding |
| Mapping a negative index into `0..size−1` with `size>0` | `Math.floorMod(index, size)` | Non-negative remainder when modulus is positive |
| Getting a non-negative offset within a positive-width bucket | `Math.floorMod(value, width)` | Offset lies in `[0,width)` |
| Operation may exceed `int`/`long` range | Check range, widen type beforehand, `BigInteger` if needed | `floorDiv` is also bound by the return type's range |
| Divisor may be `0` or size non-positive | Validate input and raise a clear error | Prevents unexpected `ArithmeticException` and out-of-contract modulo results |

### Common Mistakes

1. **Assuming `%` always yields a non-negative number.** `-7 % 3` is `-1`. Use `floorMod` with a positive modulus when `0..m-1` is needed.
2. **Assuming `floorMod` is always non-negative for any divisor.** `Math.floorMod(7, -3)` equals `-2`. Check `m > 0` when an index is needed.
3. **Computing `Math.abs(x % m)` to fix negative indices.** Values usually wrap in the wrong direction, and `Math.abs(MIN_VALUE)` can still overflow.
4. **Using `/` to bucket negative coordinates/timestamps.** `-1 / 60` equals `0`, whereas `floorDiv(-1,60)` equals `−1`.
5. **Computing floor manually via `Math.floor((double)x / y)` for any `long`.** Converting to `double` can lose precision, especially for very large numbers.
6. **Forgetting the `MIN_VALUE / -1` case.** `floorDiv` does not automatically detect this integer overflow; if the exact mathematical quotient is needed, widen the type or use `BigInteger`.
7. **Calling modulo with size `0`.** Both `%` and `floorMod` throw `ArithmeticException`. Enforce a positive size condition beforehand.

### Self-Check

1. Compute `-8 / 3`, `-8 % 3`, `Math.floorDiv(-8,3)`, and `Math.floorMod(-8,3)`. Why do the two quotients and two remainders differ?
2. For `Math.floorMod(8,-3)`, is the result non-negative? Which property of the divisor determines the remainder's sign?
3. A ring buffer has 7 elements; the logical position is `−2`. How do `-2 % 7` and `Math.floorMod(-2,7)` differ?
4. A timestamp has value `−61` seconds, bucket width `60`. Why must the bucket be `−2` under the floor method?
5. Does `Math.floorDiv(Integer.MIN_VALUE,-1)` return the exact mathematical quotient? How do you handle it when the problem needs `2147483648`?
6. Do `/`, `%`, and the two floor methods throw a divide-by-zero exception on integer types?

**Key Takeaway:** `/` and `%` are integer division/remainder **truncating the quotient toward zero**. `Math.floorDiv` and `Math.floorMod` use **floor rounding of the quotient**. With a positive modulus, `floorMod` maps any integer—including negative ones—into a non-negative remainder range; with a negative divisor, floor remainder can be negative. Choose the division rule according to the problem semantics and check for division by zero, integer type ranges, and overflow cases.