# Do Not Equate Right Shift with Division on Negative Numbers in Java

In Java, **signed integer right shift** (`>>`) and **integer division** (`/`) can yield two different results when the dividend is negative. The difference comes from **rounding rules**, not from writing the two operations in two different ways. You must also distinguish unsigned right shift (`>>>`), because it changes how the sign bit is handled as well.

This lesson belongs to the topic **Bits and Unsigned Numbers**. After studying it, you should know when to use `/`, `>>`, and `>>>`; be able to explain results for negative numbers yourself; and avoid mechanically replacing division with bit shifting.

## 1. Three Operations with Three Meanings

- `x / d` where `x` and `d` are integer types (`int` or `long`): Java performs **integer division, truncating toward 0**. For example, `-3 / 2` yields `-1`, because the mathematical quotient is `-1.5` and is truncated toward `-1`. The sign of the remainder (`%`) follows the dividend's sign: `-3 % 2 == -1`.
- `x >> k`: **arithmetic right shift**, where vacated bits on the left are filled with the sign bit (0 for non-negative numbers, 1 for negative numbers). For `int` and `0 <= k <= 30`, the result is equivalent to **rounding toward negative infinity** of `x / 2^k` mathematically: `floor(x / 2^k)`.
- `x >>> k`: **logical/unsigned right shift**, always filling `0` bits from the left. For negative numbers, the result is typically a very large positive integer when viewed as `int`; this operation is not equivalent to signed division.

Key point: `/` rounds toward **0**, whereas `>>` on a negative number with a nonzero remainder rounds toward **negative infinity**.

| Value `x` | `k` | Mathematical quotient `x / 2^k` | `x / (1 << k)` | `x >> k` |
| ---: | ---: | ---: | ---: | ---: |
| 7 | 1 | 3.5 | 3 | 3 |
| -8 | 2 | -2 | -2 | -2 |
| -7 | 2 | -1.75 | -1 | -2 |
| -3 | 1 | -1.5 | -1 | -2 |
| -1 | 1 | -0.5 | 0 | -1 |

The table uses type `int`, `k` from 0 to 30, and positive divisor `1 << k`. The two operations always match in this range only when `x >= 0` or when `x` is negative and **divisible by `2^k`**. They differ by 1 for negative numbers that are not evenly divisible.

## 2. Why Does `-3 >> 1` Equal `-2`?

`int` has 32 bits and represents negative integers in two's complement. The bit pattern of `-3` is:

~~~text
-3 (int)       = 11111111 11111111 11111111 11111101 = 0xFFFFFFFD
-3 >> 1        = 11111111 11111111 11111111 11111110 = 0xFFFFFFFE = -2
-3 >>> 1       = 01111111 11111111 11111111 11111110 = 0x7FFFFFFE = 2147483646
-3 / 2         = -1                                      = 0xFFFFFFFF
~~~

With `>>`, the leftmost `1` bit is replicated, preserving the negative sign. The lowest bit is dropped, so `-3` turns into `-2`. In `-3 / 2`, Java computes the quotient `-1.5` and drops the fractional part toward 0, producing `-1`; division is not defined as "shift bits and drop the last bit".

With `>>>`, a `0` bit is inserted on the left. This matches the meaning of **shifting a 32-bit pattern as an unsigned number**: `0xFFFFFFFD` is interpreted as `4294967293` in the unsigned 32-bit range, and integer division by 2 yields `2147483646`. However, an `int` variable in Java **remains a signed type**; to inspect the original unsigned value, use `Integer.toUnsignedLong(-3)`.

## 3. Standalone Runnable Java 17+ Example

Save with exact filename `ShiftVsDivision.java`:

~~~java
public class ShiftVsDivision {
    public static void main(String[] args) {
        printCase(-3, 1);
        printCase(-8, 2);
        printCase(-7, 2);
        printCase(7, 1);
        printCase(-1, 1);

        System.out.println("Math.floorDiv(-3, 2) = "
                + Math.floorDiv(-3, 2));
        System.out.println("-3 >>> 1 = " + (-3 >>> 1));
        System.out.println("-3 unsigned = "
                + Integer.toUnsignedLong(-3));
    }

    private static void printCase(int x, int k) {
        if (k < 0 || k > 30) {
            throw new IllegalArgumentException("k must be from 0 to 30");
        }
        int divisor = 1 << k;
        System.out.println("x=" + x + ", k=" + k
                + ": /=" + (x / divisor)
                + ", >>=" + (x >> k));
    }
}
~~~

Compile and run:

~~~bash
javac ShiftVsDivision.java
java ShiftVsDivision
~~~

Exact output:

~~~text
x=-3, k=1: /=-1, >>=-2
x=-8, k=2: /=-2, >>=-2
x=-7, k=2: /=-1, >>=-2
x=7, k=1: /=3, >>=3
x=-1, k=1: /=0, >>=-1
Math.floorDiv(-3, 2) = -2
-3 >>> 1 = 2147483646
-3 unsigned = 4294967293
~~~

Observe the rows for `-3`, `-7`, and `-1`: integer division and right shift differ. The `-8` row shows that when a negative number is **evenly divisible** by a power of 2, the results still match. The `7` row illustrates the positive case.

## 4. Choosing the Operator According to Intended Semantics

**Case A — you want integer division quotient per Java's rules:** use `/`.

~~~java
int quantity = -7;
int result = quantity / 4; // -1: rounds toward 0
~~~

Do not replace this with `quantity >> 2`: the shift produces `-2`. This can be a subtle bug if testing only uses positive numbers or evenly divisible negative numbers.

**Case B — you want floor rounding when dividing by a power of 2:** use `Math.floorDiv(x, divisor)` to express intent clearly, or `x >> k` if you are genuinely doing bit-level math and understand the constraints on `k`.

~~~java
int x = -7;
int floorByApi = Math.floorDiv(x, 4); // -2
int floorByBits = x >> 2;             // -2
~~~

`Math.floorDiv` also works with positive divisors other than 2, 4, 8, ...; `>>` only corresponds to division by powers of 2. In `floor(x / 2^k)`, `floor` denotes mathematical floor rounding, **not** Java integer division.

**Case C — you are manipulating bit patterns or want unsigned shifting:** use `>>>` when you need `0` filled from the left; if you want to treat an `int` value as unsigned 32-bit, use APIs that clearly express unsigned semantics.

~~~java
int bits = -3; // 0xFFFFFFFD
int shifted = bits >>> 1;                // 2147483646
long unsigned = Integer.toUnsignedLong(bits); // 4294967293
int quotient = Integer.divideUnsigned(bits, 2); // 2147483646
~~~

`>>>` is useful when extracting bit fields, processing masks, handling binary data, or implementing an algorithm that explicitly uses unsigned representation. Do not use `>>>` to replace `/` on signed negative numbers.

## 5. Limits Easily Overlooked

1. **Shift counts are masked to the data type's width.** For `int`, Java uses only the low 5 bits of the shift count (`k & 31`); for `long`, the low 6 bits (`k & 63`). Thus `x >> 32` is actually the same as `x >> 0` when `x` is `int`; it does not represent division by `2^32`. Similarly `1L >> 64` is the same as `1L >> 0`.
2. **Avoid writing `1 << 31` as a positive `int` divisor.** That value is `Integer.MIN_VALUE` (`-2147483648`), because the sign bit is set. The pattern `x / (1 << k)` in the table only uses `0 <= k <= 30`. If you must work with larger powers of 2, consider `long` or another suitable representation before dividing.
3. **`byte` and `short` are promoted to `int` before shifting.** For example, if `byte b = -3`, then `b >>> 1` operates on the sign-extended 32-bit `int`, yielding `2147483646`, rather than shifting only the 8-bit pattern `0xFD`. If you need to handle an unsigned byte, convert with `b & 0xFF` before shifting.
4. **`long` follows the same rounding difference.** `-3L / 2L` gives `-1L`, whereas `-3L >> 1` gives `-2L`. `long` shift counts use a 64-bit mask rather than 32-bit.
5. **Do not assume "shift is always faster than division" and swap operators manually.** Two expressions must have identical semantics for *all* valid inputs before optimizing; the compiler/JIT can choose an appropriate lowering automatically while still preserving `/` rounding. Substituting the wrong operation is a correctness bug, regardless of performance.
6. **Test negative values near 0 and odd negative numbers.** `-1 / 2 == 0` whereas `-1 >> 1 == -1` is the smallest test revealing the difference; include `-3`, `-7`, and evenly divisible negative numbers like `-8`.

For a positive representable power-of-2 divisor `2^k`, remember this summary:

~~~text
x / (2^k)  = truncateTowardZero(x / 2^k)
x >> k     = floor(x / 2^k)
~~~

For `x < 0` with a nonzero remainder, `x >> k` is **exactly 1 less than the integer division result**. For `x >= 0` or evenly divisible negative numbers, they coincide. That is why bit shifting cannot serve as a drop-in replacement for division in signed integer logic.

## 6. Self-Check

Predict before running Java:

- What are `-9 / 4` and `-9 >> 2`, respectively?
- Are `-12 / 4` and `-12 >> 2` equal?
- What is `-1 >>> 1` for type `int`, and why is it not the result of `-1 / 2`?

**Answers:** `-9 / 4 == -2`, `-9 >> 2 == -3`; both expressions with `-12` equal `-3` because it is divisible by 4; `-1 >>> 1 == 2147483647` because `-1` has all `1` bits and `>>>` inserts `0` at the front, whereas `-1 / 2 == 0`.

When reading existing code, immediately identify the intent: **signed division**, **floor rounding**, or **unsigned bit-pattern shifting**. Choose the operator matching that intent, especially when input data may be negative.