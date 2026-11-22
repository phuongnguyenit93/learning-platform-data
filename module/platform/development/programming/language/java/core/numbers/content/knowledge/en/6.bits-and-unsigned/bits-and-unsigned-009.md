# `bitCount`, Leading Zeros, Trailing Zeros, and One-Bit Helpers in Java

## 1. Objectives and Bit Model

In Java, `int` is always **32 bits** and `long` is always **64 bits** (`Integer.SIZE == 32`, `Long.SIZE == 64`). Bitwise operations process **fixed-width bit patterns**, even when the value is interpreted as a negative number in two's complement representation. Utility methods on `Integer` and `Long` help count `1` bits, find positions of `1` bits, or isolate the highest/lowest `1` bit without manually shifting through every position.

For example, the number `40` has binary form `101000`. Viewed as an `int`, it has **26 leading `0` bits on the left**, followed by `101000`; the two `1` bits sit at positions 5 and 3 (indexed from right to left, starting at 0). Therefore:

- `Integer.bitCount(40)` returns `2`.
- `Integer.numberOfLeadingZeros(40)` returns `26`.
- `Integer.numberOfTrailingZeros(40)` returns `3`.
- `Integer.highestOneBit(40)` returns `32` (`1` bit at position 5).
- `Integer.lowestOneBit(40)` returns `8` (`1` bit at position 3).

The methods below are `static`, do not mutate their arguments, and do not depend on whether you print values in decimal, hexadecimal, or binary.

## 2. API Overview

| `Integer` (`int`, 32-bit) | `Long` (`long`, 64-bit) | Meaning |
| --- | --- | --- |
| `Integer.bitCount(x)` | `Long.bitCount(x)` | Number of `1` bits (population count, **popcount**) across the full bit pattern. |
| `Integer.numberOfLeadingZeros(x)` | `Long.numberOfLeadingZeros(x)` | Number of consecutive `0` bits **from the highest bit** down to before the first `1` bit. |
| `Integer.numberOfTrailingZeros(x)` | `Long.numberOfTrailingZeros(x)` | Number of consecutive `0` bits **from the lowest bit** up to before the first `1` bit. |
| `Integer.highestOneBit(x)` | `Long.highestOneBit(x)` | Value keeping only the **highest `1` bit**; all other bits are `0`. |
| `Integer.lowestOneBit(x)` | `Long.lowestOneBit(x)` | Value keeping only the **lowest `1` bit**; all other bits are `0`. |

The count results are always `int`, even for `Long`. The two methods `highestOneBit`/`lowestOneBit` return the same type as their input (`int` or `long`). There is no `-1` sentinel to indicate no `1` bit was found: the two *one-bit* methods return `0`; the two zero-counting methods return the **bit width** when the input is `0`.

### Boundary Cases to Remember

| `int` Input | `bitCount` | Leading zeros | Trailing zeros | `highestOneBit` | `lowestOneBit` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0` | 0 | 32 | 32 | 0 | 0 |
| `40` (`0b101000`) | 2 | 26 | 3 | 32 | 8 |
| `-1` (32 `1` bits) | 32 | 0 | 0 | `Integer.MIN_VALUE` | 1 |
| `Integer.MIN_VALUE` (only sign bit is `1`) | 1 | 0 | 31 | `Integer.MIN_VALUE` | `Integer.MIN_VALUE` |

For `long`, replace width `32` with `64`. For instance, `Long.numberOfTrailingZeros(0L) == 64`, `Long.bitCount(-1L) == 64`, and `Long.highestOneBit(-1L) == Long.MIN_VALUE`.

## 3. `bitCount`: Counting `1` Bits

`Integer.bitCount(x)` and `Long.bitCount(x)` return the number of `1` bits across all 32/64 bits. This method does **not** count occurrences of the digit `1` in a decimal string, nor does it count the number of bits needed to represent the number's magnitude.

```java
int a = 0b1010_0101; // Four 1 bits
int count = Integer.bitCount(a); // 4
long b = 0b1_0000_0000L;
int longCount = Long.bitCount(b); // 1
```

Negative numbers must be evaluated in two's complement: `Integer.bitCount(-1) == 32`, and `Long.bitCount(-1L) == 64`. This is useful when working with bit flags, bitmaps, bitsets packed into integers, or Hamming distance: `Integer.bitCount(a ^ b)` is the number of bit positions that differ between two `int` patterns.

For example, if `permissions` is a set of flags and `mask` specifies the permissions to inspect, `Integer.bitCount(permissions & mask)` counts how many permissions are enabled **within `mask`**. For applications needing bitsets larger than 64 bits, `java.util.BitSet` is a better fit; `BitSet.cardinality()` counts the `1` bits in that set.

## 4. Leading Zeros: Counting `0` Bits from the High End

`numberOfLeadingZeros(x)` starts from the highest bit (bit 31 of `int`, bit 63 of `long`) and counts up to the first `1` bit. If a positive number has its highest `1` bit at position `p`, then:

- For `int`: `p = 31 - Integer.numberOfLeadingZeros(x)` when `x != 0`.
- For `long`: `p = 63 - Long.numberOfLeadingZeros(x)` when `x != 0`.

For `x > 0`, the minimum number of bits needed to represent the unsigned binary form is `Integer.SIZE - Integer.numberOfLeadingZeros(x)`. For example, `40` needs 6 bits (`101000`), so `32 - 26 = 6`.

For `x == 0`, Java returns `32` or `64` because all bits are `0`; you must handle `0` separately if the problem requires the position of a `1` bit. For negative numbers, the highest sign bit is always `1`, so the number of leading zeros is **0**, regardless of how large or small the absolute value is.

```java
int x = 40;
int highestSetIndex = x == 0
        ? -1
        : Integer.SIZE - 1 - Integer.numberOfLeadingZeros(x);
// highestSetIndex == 5
```

Using `-1` in the snippet above is an **application-chosen convention** for the case with no `1` bits, not a value returned directly by `numberOfLeadingZeros`.

## 5. Trailing Zeros: Counting `0` Bits from the Low End

`numberOfTrailingZeros(x)` counts consecutive `0` bits from the lowest bit (bit 0) up to before the first `1` bit. When `x != 0`, the result is the **index of the lowest `1` bit**:

```java
int mask = 0b0010_1000; // 40
int lowestSetIndex = Integer.numberOfTrailingZeros(mask); // 3
```

A nonzero integer is divisible by `2^k` if and only if at least the lowest `k` bits are `0`. Thus trailing zeros indicate the number of factors of 2 in a nonzero integer's bit representation (for instance, `40 = 5 × 2^3`, so it has 3 trailing `0` bits). This formula also holds for negative numbers when operating on bit patterns, though it should not be used to infer sign.

`Integer.numberOfTrailingZeros(0) == 32`, `Long.numberOfTrailingZeros(0L) == 64`. These are valid API sentinels: do not pass `32` directly into `1 << index` expecting to create a bit at position 32.

When iterating over active bits, trailing zeros immediately find the lowest bit index; you can then clear that bit and continue until the bit pattern becomes `0`.

## 6. `highestOneBit` and `lowestOneBit`: Creating a Single-Bit Mask

These two methods return a **one-hot mask**: only the highest or lowest `1` bit is retained.

```java
int x = 0b0010_1000;          // 40
int high = Integer.highestOneBit(x); // 0b0010_0000 = 32
int low  = Integer.lowestOneBit(x);  // 0b0000_1000 = 8
```

If `x == 0`, both return `0`. If `x` is negative, the methods still inspect the entire 32/64-bit pattern without ignoring the sign bit. Therefore:

```java
int highNegative = Integer.highestOneBit(-1);
// Integer.MIN_VALUE, i.e., 0x80000000, displayed as int is -2147483648

long highNegativeLong = Long.highestOneBit(-1L);
// Long.MIN_VALUE, i.e., 0x8000000000000000
```

**How the result is read depends on signed/unsigned interpretation.** The sign bit at position 31 represents the mask `0x80000000`; when printed as `int`, the value is negative, whereas when printed as an unsigned integer it is `2147483648`:

```java
String unsignedText =
        Integer.toUnsignedString(Integer.highestOneBit(-1));
// "2147483648"
```

For **positive** `x`, `highestOneBit(x)` is the largest power of 2 not exceeding `x`; `lowestOneBit(x)` is the power of 2 corresponding to the lowest `1` bit. Do not equate `highestOneBit` with rounding up to a power of 2: for example, `highestOneBit(40) == 32`, whereas the next power of 2 is `64`.

Two equivalent bit transformations can be recognized when operating on two's complement patterns:

- `x & -x` isolates the lowest `1` bit, equivalent to `lowestOneBit(x)`.
- `x & (x - 1)` **clears** the lowest `1` bit, which is not equivalent to `lowestOneBit(x)`.

Subtraction by one and negation here use fixed-width Java integers. In application code, the clearly named JDK methods are usually easier to read and less error-prone.

## 7. Complete, Runnable Java 17 Example

Save as **`BitHelpersDemo.java`**:

```java
public class BitHelpersDemo {
    public static void main(String[] args) {
        int x = 0b0010_1000; // 40: 1 bits at positions 5 and 3

        System.out.println("bitCount(40) = " + Integer.bitCount(x));
        System.out.println("leadingZeros(40) = "
                + Integer.numberOfLeadingZeros(x));
        System.out.println("trailingZeros(40) = "
                + Integer.numberOfTrailingZeros(x));
        System.out.println("highestOneBit(40) = "
                + Integer.highestOneBit(x));
        System.out.println("lowestOneBit(40) = "
                + Integer.lowestOneBit(x));

        System.out.println("leadingZeros(0) = "
                + Integer.numberOfLeadingZeros(0));
        System.out.println("trailingZeros(0) = "
                + Integer.numberOfTrailingZeros(0));
        System.out.println("bitCount(-1) = "
                + Integer.bitCount(-1));
        System.out.println("highestOneBit(-1), signed = "
                + Integer.highestOneBit(-1));
        System.out.println("highestOneBit(-1), unsigned = "
                + Integer.toUnsignedString(Integer.highestOneBit(-1)));

        long large = 1L << 40;
        System.out.println("Long.bitCount(2^40) = "
                + Long.bitCount(large));
        System.out.println("Long.leadingZeros(2^40) = "
                + Long.numberOfLeadingZeros(large));
        System.out.println("Long.trailingZeros(2^40) = "
                + Long.numberOfTrailingZeros(large));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac BitHelpersDemo.java
java BitHelpersDemo
```

Exact output:

```text
bitCount(40) = 2
leadingZeros(40) = 26
trailingZeros(40) = 3
highestOneBit(40) = 32
lowestOneBit(40) = 8
leadingZeros(0) = 32
trailingZeros(0) = 32
bitCount(-1) = 32
highestOneBit(-1), signed = -2147483648
highestOneBit(-1), unsigned = 2147483648
Long.bitCount(2^40) = 1
Long.leadingZeros(2^40) = 23
Long.trailingZeros(2^40) = 40
```

Explanation of `1L << 40`: the `L` suffix ensures the shift is performed on 64-bit `long`. The result has a single `1` bit at position 40, leaving 40 `0` bits on the right, 23 `0` bits on the left, and one `1` bit in total.

## 8. Application: Iterating Quickly Over Active Bit Flags

Suppose each bit represents an enabled feature. The pattern `0b101010` has `1` bits at positions 1, 3, and 5. You can use `numberOfTrailingZeros` to find the index and then clear that lowest `1` bit with `mask &= mask - 1`.

Save as **`ActiveBitsDemo.java`**:

```java
public class ActiveBitsDemo {
    public static void main(String[] args) {
        int mask = 0b101010;

        while (mask != 0) {
            int index = Integer.numberOfTrailingZeros(mask);
            System.out.println("Set bit: " + index);
            mask &= mask - 1;
        }
    }
}
```

```bash
javac ActiveBitsDemo.java
java ActiveBitsDemo
```

```text
Set bit: 1
Set bit: 3
Set bit: 5
```

The loop executes once per `1` bit, i.e., `Integer.bitCount(initialMask)` iterations. Even if `mask` has its sign bit set, this approach still handles position 31; the `mask != 0` condition checks the **bit pattern**, without requiring the value to be positive. To test a specific bit:

```java
int flags = 0b101010;
int index = 3;
boolean enabled = (flags & (1 << index)) != 0; // true
```

Here `index` must be in `0..31` for `int`; for `long`, use `1L << index` and restrict to `0..63`.

## 9. Several Useful Usage Patterns

### Checking whether a bit pattern has exactly one `1` bit

```java
static boolean hasExactlyOneBitSet(int x) {
    return Integer.bitCount(x) == 1;
}
```

This method also treats `Integer.MIN_VALUE` as having a single `1` bit. If the goal is to check whether a **positive integer** is a power of 2, add the condition `x > 0`:

```java
static boolean isPositivePowerOfTwo(int x) {
    return x > 0 && Integer.bitCount(x) == 1;
}
```

Alternatively, use `x > 0 && (x & (x - 1)) == 0`. The `x > 0` condition avoids mistaking `0` and the negative number with only the sign bit set. For `long`, replace `Integer.bitCount` with `Long.bitCount`.

### Getting the highest and lowest set bit index

```java
static int highestSetBitIndex(int x) {
    return x == 0 ? -1
            : Integer.SIZE - 1 - Integer.numberOfLeadingZeros(x);
}

static int lowestSetBitIndex(int x) {
    return x == 0 ? -1 : Integer.numberOfTrailingZeros(x);
}
```

These methods return `-1` for `0` by custom convention. They also work for negative `int` values because the index refers to **the position within the bit pattern**. For example, `highestSetBitIndex(Integer.MIN_VALUE) == 31`.

### Counting differing bits between two numbers

```java
int a = 0b1010;
int b = 0b0011;
int hammingDistance = Integer.bitCount(a ^ b); // 2
```

XOR produces a `1` bit at positions that differ; `bitCount` counts them. This is a 32-bit comparison (or 64-bit with `Long.bitCount`), including for negative numbers.

## 10. Notes and Common Pitfalls

1. **Forgetting fixed bit width.** `bitCount(-1)` is `32`/`64`, not `1`, because `-1` in two's complement has all `1` bits.
2. **Overlooking `0`.** `numberOfLeadingZeros(0)` and `numberOfTrailingZeros(0)` return `Integer.SIZE`/`Long.SIZE`; meanwhile `highestOneBit(0)` and `lowestOneBit(0)` both return `0`. Handle `0` before computing a bit index or shifting `1` by the result.
3. **Confusing index with mask.** `numberOfTrailingZeros(40)` is the **position** `3`; `lowestOneBit(40)` is the **mask value** `8`. Similarly, `highestOneBit(40)` is `32`, while the highest set bit index is `5`.
4. **Misunderstanding the sign of `highestOneBit` on negative numbers.** The method can return `Integer.MIN_VALUE` or `Long.MIN_VALUE`; the sign bit is still an ordinary `1` bit when manipulating bits. Use `Integer.toUnsignedString`/`Long.toUnsignedString` if you need unsigned display.
5. **Using shift operators with the wrong type or out-of-bounds index.** `1 << 40` runs on `int` and Java uses only the low 5 bits of the shift count, so it does not create a bit at position 40. Use `1L << 40` for `long`; constrain shift indices to `0..31`/`0..63` as needed.
6. **Forgetting operator precedence.** Write `(x & (x - 1)) == 0` and `(flags & (1 << index)) != 0` with explicit parentheses.
7. **Using the bit trick on 0 when checking powers of 2.** `(0 & (0 - 1)) == 0` is true, yet `0` is not a power of 2. You must check `x > 0` when testing positive integers.
8. **Confusing leading/trailing zeros with the start/end of a string.** `Integer.toBinaryString(40)` returns `"101000"` (without padding the 26 leading zeros). `numberOfLeadingZeros` still counts across all 32 bits.

These methods clearly express bit operations and are typically well optimized by the JVM, sometimes via dedicated machine instructions; do not assume a fixed speed across all platforms or replace them with manual loops without benchmarking.

## 11. Self-Check

1. For `0b1001_0000` (`144`), what is `bitCount`? What is `numberOfTrailingZeros`? What are `highestOneBit` and `lowestOneBit`?
2. Why is `Integer.numberOfLeadingZeros(-8)` equal to `0`, even though `Integer.toBinaryString(-8)` is 32 characters long?
3. Why is `Integer.bitCount(Integer.MIN_VALUE) == 1` yet `Integer.MIN_VALUE` is not a **positive** power of 2?
4. What happens if you accidentally compute `1 << Integer.numberOfTrailingZeros(0)`?

**Answers:** (1) `2`, `4`, `128`, and `16`, respectively. (2) The sign bit (bit 31) of every negative `int` is 1, so there are no leading `0` bits. (3) Only the sign bit is set, so the value is interpreted as negative. (4) Shifting `1 << 32` on `int` is equivalent to `1 << 0`, giving `1`, because Java uses only the low 5 bits of the shift count; that is why `0` must be handled beforehand.

**Remember:** `bitCount` returns the **count of `1` bits**; leading/trailing zeros return the **number of consecutive `0` bits from either end of the bit pattern**; `highestOneBit`/`lowestOneBit` return a **mask with a single `1` bit** or `0`. Always distinguish whether a result is a *count*, a *position*, or a *mask*, and check for `0` before deriving a bit index.