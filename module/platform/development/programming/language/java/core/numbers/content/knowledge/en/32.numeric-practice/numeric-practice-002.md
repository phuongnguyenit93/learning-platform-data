# Building Overflow-Checked Size Calculations in Java

## 1. Practice Objectives

When calculating memory, file, image, buffer, or storage page sizes, a simple expression like `width * height * bytesPerPixel` can experience **integer overflow** even when all input arguments are individually valid.

Example:

```java
int width = 70_000;
int height = 70_000;

int wrong = width * height; // 605032704, not 4900000000
```

The correct result is **4,900,000,000**, exceeding `Integer.MAX_VALUE = 2,147,483,647`. Java does not automatically throw an exception for standard `int` multiplication: bits exceeding the range are discarded according to Java integer rules, leading to an incorrect result while the program can still continue running.

In size calculation tasks, this bug is especially dangerous: allocating an undersized buffer, miscalculating offsets, record counts, or data limits. The goal of this lesson is to build a calculation that is **clear in units, validates preconditions, detects overflow directly at the operation, rounds safely, and does not allocate beyond actual capacity**.

After this lesson, you will:
- Use `Math.multiplyExact`, `Math.addExact`, `Math.subtractExact`, and `Math.toIntExact` in the right places.
- Distinguish widening types **before** multiplication from assigning an already-overflowed result to `long`.
- Compute bytes per row, aligned stride, total capacity, and required allocation pages.
- Distinguish **arithmetic overflow**, **invalid input data**, and **insufficient physical resources**.
- Test normal cases, `int`/`long` boundaries, zero, negative numbers, and problems exceeding `long` with `BigInteger`.

## 2. Problem Statement: Computing Size by Units

Suppose an image has:
- `rows`: number of rows.
- `columns`: number of pixels per row.
- `bytesPerPixel`: bytes per pixel.
- `alignment`: byte alignment level for each row.

Without alignment, total bytes are:

```text
rawRowBytes = columns × bytesPerPixel
totalBytes  = rows × rawRowBytes
```

If row stride must be a multiple of `alignment`:

```text
remainder  = rawRowBytes % alignment
padding    = (remainder == 0) ? 0 : alignment - remainder
stride     = rawRowBytes + padding
totalBytes = rows × stride
```

You must check `alignment > 0`, `rows >= 0`, `columns >= 0`, and `bytesPerPixel >= 0` or `> 0` depending on business rules. You may require positive image dimensions, though the general examples in this lesson **allow 0-byte regions** to represent empty buffers.

Example: an image with 2 rows, 3 columns, 3 bytes/pixel, alignment 4:
- Raw: `3 × 3 = 9` bytes/row.
- Remainder 9 % 4 = 1; requires 3 bytes of padding.
- Stride: 12 bytes/row.
- Total: `2 × 12 = 24` bytes.

Key point: **every multiplication/addition that can exceed limits must be checked at the moment it executes**, including adding padding even when the first multiplication was valid.

## 3. How Does Integer Overflow Work?

`int` is 32-bit signed, from `-2^31` to `2^31 - 1`. `long` is 64-bit signed, from `-2^63` to `2^63 - 1`.

In Java, standard integer addition/subtraction/multiplication executes at the width of the computation type. When out of range, the result wraps modulo 2^32 or 2^64 (without automatically throwing an exception).

```java
int a = 70_000;
int b = 70_000;

int incorrect = a * b;       // 605032704
long stillWrong = a * b;     // 605032704L: already overflowed before assignment!
long correct = (long) a * b; // 4900000000L: widen before multiplication
```

Making an operand `long` before multiplication matters more than the result variable's type. In addition:

```java
long checked = Math.multiplyExact((long) a, b); // 4900000000L
// Math.multiplyExact(a, b) selects the int overload and throws ArithmeticException.
```

This is the difference between **widening the range** and **overflow checking**:
- Converting an operand from `int` to `long` can avoid `int` overflow, but `long` multiplication can still overflow.
- `Math.multiplyExact(long, long)` detects `long` overflow by throwing `ArithmeticException`.
- `Math.multiplyExact(int, int)` throws if the result cannot fit in `int`.

Choose the overload intentionally based on the **desired return type and result range**.

## 4. Overflow-Checking APIs in Java 17

| API | Purpose | When out of range |
| --- | --- | --- |
| `Math.addExact(int,int)` / `Math.addExact(long,long)` | Checked addition | `ArithmeticException` |
| `Math.subtractExact(...)` | Checked subtraction | `ArithmeticException` |
| `Math.multiplyExact(...)` | Checked multiplication | `ArithmeticException` |
| `Math.incrementExact(...)` / `Math.decrementExact(...)` | Increment/decrement by 1 | `ArithmeticException` |
| `Math.negateExact(...)` | Negation | `ArithmeticException` when negating MIN value |
| `Math.toIntExact(long)` | Checked narrowing from `long` to `int` | `ArithmeticException` |

Some examples:

```java
long bytes = Math.multiplyExact(4_000L, 3_000L);
bytes = Math.multiplyExact(bytes, 4L);   // 48000000
long withHeader = Math.addExact(bytes, 128L);
long remaining = Math.subtractExact(withHeader, 128L);

int acceptableLength = Math.toIntExact(4_096L); // 4096
// Math.toIntExact(2_147_483_648L) throws ArithmeticException.
```

**Do not confuse `Math.toIntExact` with `(int) x`**: casting `(int)` only keeps the low bits and can return a completely different number. You must check **business validity** separately: `Math.toIntExact(-1L)` still returns `-1` because -1 is within the `int` range, whereas a negative array length is invalid.

If a calculation requires multiple steps, every step with overflow risk must be protected. Only checking the final result with `if (result < 0)` is **not enough**: an overflowed result can still be positive, as `70_000 × 70_000` demonstrated.

## 5. API Design: Valid Values and Exceptions

A size-calculation API should separate two categories of errors:

1. **Arguments violating rules**: negative values, zero divisor/alignment; typically throw `IllegalArgumentException` with a message naming the parameter.
2. **Operation meaningful semantically but exceeding type range**: throw `ArithmeticException` via `Math.*Exact`.

Example method to calculate data bytes:

```java
static long elementBytes(long count, long bytesPerElement) {
    if (count < 0 || bytesPerElement < 0) {
        throw new IllegalArgumentException("dimensions must be >= 0");
    }
    return Math.multiplyExact(count, bytesPerElement);
}
```

This is an **illustrative method snippet** and must be placed inside a class. With `elementBytes(70_000,70_000)`, the result is `4_900_000_000L`. With `elementBytes(Long.MAX_VALUE,2)`, the multiplication exceeds `long` and throws `ArithmeticException`.

Choosing to allow `count = 0` and `bytesPerElement = 0` is part of the problem's contract. If "each element must occupy positive bytes," check `bytesPerElement > 0` instead of allowing 0. What matters is never silently clamping input values to 0 or a maximum limit without the caller knowing.

## 6. Aligning Sizes Without Overflowing Intermediate Addition

A commonly seen formula:

```java
// Counterexample: raw + alignment - 1 can overflow.
long stride = ((raw + alignment - 1) / alignment) * alignment;
```

Even when the row size fits in `long`, the expression `raw + alignment - 1` can overflow; multiplying by `alignment` in the last step can also overflow.

A safe approach for `raw >= 0` and `alignment > 0` is computing the remainder:

```java
static long alignUp(long raw, long alignment) {
    if (raw < 0 || alignment <= 0) {
        throw new IllegalArgumentException("invalid size or alignment");
    }
    long remainder = raw % alignment;
    long padding = remainder == 0 ? 0 : alignment - remainder;
    return Math.addExact(raw, padding);
}
```

When `remainder != 0`, `padding` is in `1..alignment-1`. The final `Math.addExact` detects when **there is no longer enough `long` range for the aligned size**. There is no need to assume `alignment` is always a power of two; the algorithm above works for any positive alignment.

Examples:
- `alignUp(9,4) = 12`.
- `alignUp(12,4) = 12`.
- `alignUp(0,4) = 0`.
- `alignUp(Long.MAX_VALUE-2,8)` throws `ArithmeticException` because the next aligned size exceeds `Long.MAX_VALUE`.

Only use the bitwise technique `(value + alignment - 1) & -alignment` if you have mandated power-of-two alignment, validated the range, and handled overflow. It is not an automatically safe general solution.

## 7. Rounding Page Counts Using Division and Remainder

If `bytes` bytes need to be split into pages of `pageSize` bytes, the page count is **ceil(bytes/pageSize)**. For two non-negative numbers and `pageSize > 0`, you can compute:

```java
static long pageCount(long bytes, long pageSize) {
    if (bytes < 0 || pageSize <= 0) {
        throw new IllegalArgumentException("invalid page arguments");
    }
    long whole = bytes / pageSize;
    return bytes % pageSize == 0 ? whole : Math.addExact(whole, 1);
}
```

Avoid `(bytes + pageSize - 1) / pageSize` if addition can overflow. With `bytes = Long.MAX_VALUE` and `pageSize = Long.MAX_VALUE`, the quotient-remainder formula returns 1, whereas adding first can overflow.

Examples:
- 0 bytes / 4096-byte page → 0 pages.
- 4096 bytes / 4096-byte page → 1 page.
- 4097 bytes / 4096-byte page → 2 pages.
- 48,000,000 bytes / 4096-byte page → 11,719 pages.

With money, page size, batching, or other algorithms, **rounding up** and **aligning to a multiple** are related but distinct requirements: page count is a **quantity**, whereas aligned stride is a **byte count**.

## 8. Standalone Java 17 Program: Checked Size Calculator

Create the file **`CheckedSizeDemo.java`**:

```java
import java.math.BigInteger;

public class CheckedSizeDemo {
    static long nonNegative(long value, String name) {
        if (value < 0) throw new IllegalArgumentException(name + " must be >= 0");
        return value;
    }

    static long elementBytes(long count, long bytesPerElement) {
        nonNegative(count, "count");
        nonNegative(bytesPerElement, "bytesPerElement");
        return Math.multiplyExact(count, bytesPerElement);
    }

    static long alignedRowBytes(long columns, long bytesPerPixel, long alignment) {
        nonNegative(columns, "columns");
        nonNegative(bytesPerPixel, "bytesPerPixel");
        if (alignment <= 0) throw new IllegalArgumentException("alignment must be > 0");
        long raw = Math.multiplyExact(columns, bytesPerPixel);
        long remainder = raw % alignment;
        long padding = remainder == 0 ? 0 : alignment - remainder;
        return Math.addExact(raw, padding);
    }

    static long gridBytes(long rows, long columns, long bytesPerPixel, long alignment) {
        nonNegative(rows, "rows");
        long stride = alignedRowBytes(columns, bytesPerPixel, alignment);
        return Math.multiplyExact(rows, stride);
    }

    static long pageCount(long bytes, long pageBytes) {
        nonNegative(bytes, "bytes");
        if (pageBytes <= 0) throw new IllegalArgumentException("pageBytes must be > 0");
        long wholePages = bytes / pageBytes;
        return bytes % pageBytes == 0 ? wholePages : Math.addExact(wholePages, 1);
    }

    static int arrayLength(long requestedLength) {
        nonNegative(requestedLength, "requestedLength");
        return Math.toIntExact(requestedLength);
    }

    static void expectedError(String label, Class<? extends Throwable> expected,
                              Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected " + expected.getSimpleName() + ": " + label);
        } catch (Throwable failure) {
            if (!expected.isInstance(failure)) throw failure;
            System.out.println(label + "=" + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        int incorrect = 70_000 * 70_000;
        System.out.println("uncheckedInt=" + incorrect);
        System.out.println("wideProduct=" + elementBytes(70_000, 70_000));
        System.out.println("rowStride=" + alignedRowBytes(3, 3, 4));
        System.out.println("smallGrid=" + gridBytes(2, 3, 3, 4));
        long imageBytes = gridBytes(3_000, 4_000, 4, 64);
        System.out.println("imageBytes=" + imageBytes);
        System.out.println("pages=" + pageCount(imageBytes, 4_096));
        System.out.println("zeroPages=" + pageCount(0, 4_096));
        System.out.println("maxPages=" + pageCount(Long.MAX_VALUE, Long.MAX_VALUE));
        System.out.println("arrayLength=" + arrayLength(4_096));

        expectedError("intOverflow", ArithmeticException.class,
                () -> Math.multiplyExact(70_000, 70_000));
        expectedError("longOverflow", ArithmeticException.class,
                () -> elementBytes(Long.MAX_VALUE, 2));
        expectedError("alignmentOverflow", ArithmeticException.class,
                () -> alignedRowBytes(Long.MAX_VALUE - 2, 1, 8));
        expectedError("negativeCount", IllegalArgumentException.class,
                () -> elementBytes(-1, 8));
        expectedError("zeroAlignment", IllegalArgumentException.class,
                () -> alignedRowBytes(3, 4, 0));
        expectedError("arrayLengthOverflow", ArithmeticException.class,
                () -> arrayLength(2_147_483_648L));

        BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE).multiply(BigInteger.valueOf(8));
        System.out.println("hugeBytes=" + huge);
        expectedError("bigIntegerToLong", ArithmeticException.class, huge::longValueExact);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac CheckedSizeDemo.java
java CheckedSizeDemo
```

Result **actually verified** when compiling with `javac --release 17`:

```text
uncheckedInt=605032704
wideProduct=4900000000
rowStride=12
smallGrid=24
imageBytes=48000000
pages=11719
zeroPages=0
maxPages=1
arrayLength=4096
intOverflow=ArithmeticException
longOverflow=ArithmeticException
alignmentOverflow=ArithmeticException
negativeCount=IllegalArgumentException
zeroAlignment=IllegalArgumentException
arrayLengthOverflow=ArithmeticException
hugeBytes=73786976294838206456
bigIntegerToLong=ArithmeticException
```

**Important verifications:**

1. `uncheckedInt` is an example of a number that is **wrong due to overflow without reporting an error**; `Math.multiplyExact` with the `int` overload reports the error clearly.
2. `wideProduct` is multiplication in `long`, yielding 4,900,000,000.
3. `rowStride=12` is row bytes after padding; `smallGrid=24` is two rows.
4. `imageBytes=48000000`: `4000 × 4 = 16000` bytes/row, already divisible by alignment 64; multiplying by 3000 rows gives 48,000,000 bytes.
5. `pages=11719` proves ceiling calculation using division and remainder, avoiding the overflow-prone `pageSize-1` addition.
6. `maxPages=1` handles upper-bound `long` inputs without overflowing.
7. The lines named `*Overflow` and input errors prove the API **throws the right exception type** instead of returning negative/wrong size values.
8. `hugeBytes` exceeds `long` range and is computed with `BigInteger`; converting to `long` with `longValueExact()` reports the error properly.

The `expectedError` function is only for testing. In real applications, you can use JUnit's `assertThrows` instead of writing a custom helper. Because this function only executes operations expected to throw, it is not used to swallow unexpected errors; exceptions of the wrong type are still rethrown.

## 9. Distinguishing Bytes, Elements, and Row Counts

One of the non-overflow bugs that is just as dangerous is mixing up units:

```text
count           : number of elements
bytesPerElement : bytes/element
totalBytes      : bytes
rowStride       : bytes/row
pageSize        : bytes/page
pageCount       : number of pages
```

If a size is `long bytes = 4_000_000_000L`, you **cannot** simply do `new int[4_000_000_000]`. `int[]` takes an `int` **element count**, not a byte count. For an `int[]` array, the bytes for element data are typically `4 × count` (excluding object overhead and other memory requirements).

To convert a byte requirement to an element count, you must define a policy:
- If the requirement must be divisible by the size per element, check `bytes % bytesPerElement == 0` then divide.
- If allocating one extra partial element is acceptable, use the safe ceiling rule.
- Finally check whether the element count fits in the `int` range.

The example below is an **illustrative method snippet**, without needing real allocation:

```java
static int exactElementCount(long totalBytes, long bytesPerElement) {
    if (totalBytes < 0 || bytesPerElement <= 0) {
        throw new IllegalArgumentException("invalid byte arguments");
    }
    if (totalBytes % bytesPerElement != 0) {
        throw new IllegalArgumentException("not divisible");
    }
    return Math.toIntExact(totalBytes / bytesPerElement);
}
```

Checking `Math.toIntExact` only confirms the `int` range. The JVM may have an **actual array limit lower than `Integer.MAX_VALUE`**, and allocation also depends on available heap space. Do not use `Math.toIntExact` as a guarantee that "allocation will always succeed."

## 10. BigInteger When Size Requirements Exceed Long.MAX_VALUE

If you only need to **estimate, report, or compute very large logical capacities**, `long` being insufficient is not necessarily invalid data. `BigInteger` represents integers whose magnitude is not limited by 64 bits (still subject to memory resources):

```java
BigInteger a = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger size = a.multiply(BigInteger.valueOf(8));
System.out.println(size); // 73786976294838206456
```

`BigInteger.multiply()` does not encounter 64-bit overflow. However, `BigInteger` does not automatically enable you to allocate an array as large as that result. Clearly separate:
- **Theoretical size**: can be computed accurately using `BigInteger`.
- **Size representable in long**: use `big.longValueExact()`; if out of range, throws `ArithmeticException`.
- **Valid size for an allocation API**: may require `int`, application thresholds, and actual JVM/resource limits.

Do not use `big.longValue()` when a lossless conversion is required: it can truncate the high bits of the value. Use `longValueExact()` to detect when it cannot be represented.

## 11. Error Policies: Fail Fast, Cap, and Chunk

When calculating sizes, there are three approaches depending on your goal:

**1. Fail fast on overflow.** `Math.*Exact` is a good default choice if a wrong value could corrupt addresses, buffers, offsets, or safety checks. Throw an error instead of silently wrapping around.

**2. Cap by resource budget.** Alongside overflow checks, check business limits, such as `requestedBytes <= maxAllowedBytes`. This limit must be an explicit configuration and applied before attempting allocation. Do not automatically "clamp" a 10 GB request down to 100 MB while still acting as if all 10 GB were allocated.

**3. Split data into chunks.** When the total size is logically valid but a single array/buffer cannot be created, split it into safely sized chunks, tracking total processed bytes with `long` or `BigInteger` as appropriate. You must verify the offset math and remaining amount at each step.

One thing never to confuse: **integer overflow checking** only answers "can this count be accurately represented in this type?". It **does not guarantee** the JVM has enough heap, native memory, disk space, or quota to execute.

## 12. Test Plan: Boundary Cases and Invariants

### 12.1. Test table

| Input/property | Expected result |
| --- | --- |
| `elementBytes(0, 4)` | `0` |
| `elementBytes(1, 4)` | `4` |
| `elementBytes(70_000, 70_000)` | `4_900_000_000L` |
| `elementBytes(Long.MAX_VALUE, 1)` | `Long.MAX_VALUE` |
| `elementBytes(Long.MAX_VALUE, 2)` | `ArithmeticException` |
| `elementBytes(-1, 4)` | `IllegalArgumentException` |
| `alignedRowBytes(3, 3, 4)` | `12` |
| `alignedRowBytes(3, 3, 1)` | `9` |
| `alignedRowBytes(3, 3, 0)` | `IllegalArgumentException` |
| `alignedRowBytes(Long.MAX_VALUE-2, 1, 8)` | `ArithmeticException` |
| `pageCount(0,4096)` | `0` |
| `pageCount(4096,4096)` | `1` |
| `pageCount(4097,4096)` | `2` |
| `pageCount(Long.MAX_VALUE, Long.MAX_VALUE)` | `1` |
| `arrayLength(2_147_483_648L)` | `ArithmeticException` |

Test overflow by **expecting an exception**, not just checking that the result is negative. Also test cases where the sum remains positive after wrapping.

### 12.2. Useful invariants

For `rows, columns, bytesPerPixel >= 0`, `alignment > 0`, and assuming no overflow:

- `stride >= rawRowBytes`.
- `stride % alignment == 0`.
- `0 <= stride - rawRowBytes < alignment`.
- `totalBytes == rows × stride` mathematically exact.
- `pageCount(bytes, pageSize) × pageSize >= bytes` **mathematically**; if multiplying in `long` for a test, the product itself can overflow. Use `BigInteger` or verify using division/remainder.
- For `bytes > 0`, `pageCount(bytes, pageSize) >= 1`.
- If `bytes` increases while `pageSize` is fixed, `pageCount` must not decrease.

Automated tests can randomly generate parameters **within the valid domain**, compute the reference result with `BigInteger`, and verify that:
1. when the reference value is within `0..Long.MAX_VALUE`, the `long` function returns the same value;
2. when it exceeds the `long` range, the function throws `ArithmeticException`;
3. when arguments are negative or divisor/alignment is non-positive, the function throws `IllegalArgumentException`.

Separate invalid-input tests from overflow tests to avoid asserting the wrong error type.

## 13. Common Mistakes and How to Fix Them

### Mistake 1: Multiplying ints before assigning to long

```java
int width = 70_000, height = 70_000;

long wrong = width * height;        // wrong due to int overflow
long correct = (long) width * height; // right within long range
long checked = Math.multiplyExact((long) width, height);
```

### Mistake 2: Only checking for a negative result

```java
int size = width * height;
if (size < 0) {
    // Does not catch all overflow cases!
}
```

For example, `70_000 × 70_000` overflows to the positive number 605,032,704. You must check the operation instead of inferring from the sign of the result.

### Mistake 3: Using addition before division for ceiling

```java
// Overflow risk:
long pages = (bytes + pageSize - 1) / pageSize;
```

Fix using division and remainder, with non-negative byte and positive pageSize constraints.

### Mistake 4: Aligning without checking padding addition

```java
long stride = raw + padding; // can overflow long
```

Fix to `Math.addExact(raw, padding)` after ensuring padding is valid.

### Mistake 5: Using toIntExact and assuming any array can be allocated

`Math.toIntExact(long)` only guarantees a lossless type conversion. The JVM and heap have their own limits. You need appropriate allocation/chunk thresholds and out-of-memory handling according to system architecture.

### Mistake 6: Mixing up KB, KiB, MB, MiB units

- `1 KB = 1000 bytes`.
- `1 KiB = 1024 bytes`.
- `1 MB = 1,000,000 bytes`.
- `1 MiB = 1,048,576 bytes`.

Do not compare a byte value against "MB" without specifying decimal/binary convention. Better to include units in variable names like `fileBytes`, `pageBytes`, `maxBytes` and define the convention in documentation.

### Mistake 7: Assuming exact multiplication means valid size

`Math.multiplyExact(-2, 4)` returns -8 **without overflowing**, yet a negative size is invalid. You must validate inputs **before or alongside** the calculation.

### Mistake 8: Converting BigInteger to long without checking

`BigInteger.longValue()` can truncate data; `longValueExact()` throws an error when it does not fit in `long`.

### Mistake 9: Correct final total but overflowing intermediate multiplication

If a calculation has multiple steps, an intermediate value can exceed the range even if the result is later divided back down. If exact operations on large intermediate values are required, use `BigInteger` for that stage or apply an algebraic transformation with a proof to avoid overflow.

### Mistake 10: Silently swallowing ArithmeticException

If `Math.*Exact` throws an error, returning `0` instead can lead to **under-allocating** and data corruption. Only use a fallback if the business contract clearly defines it and callers can distinguish the error from an actual 0 size.

## 14. Practice Exercises

**Exercise 1.** Calculate pixel size for 70,000 × 70,000, at 4 bytes per pixel. Why is `(long)(70_000 * 70_000 * 4)` wrong?  
**Answer:** the expression inside the cast is evaluated as `int` and already overflowed. Use `Math.multiplyExact(Math.multiplyExact(70_000L, 70_000L), 4L)` → 19,600,000,000 bytes, or an equivalent checked approach.

**Exercise 2.** With a raw row of 13 bytes and alignment 8, what are padding/stride?  
**Answer:** 13 % 8 = 5, padding = 3, stride = 16.

**Exercise 3.** Why is `(Long.MAX_VALUE + 4) / 4` not a safe way to compute page count?  
**Answer:** the `long` addition overflows before division. Use quotient and remainder.

**Exercise 4.** If you need to allocate 3,000,000,000 elements in an `int[]`, how does `Math.toIntExact(3_000_000_000L)` behave?  
**Answer:** throws `ArithmeticException` because the element count does not fit in `int`. Even an element count that fits in `int` might still fail to allocate.

**Exercise 5.** When needing to represent a size of 8 × `Long.MAX_VALUE`, which numeric type is suitable for computing the theoretical value?  
**Answer:** `BigInteger`. It computes the exact value 73,786,976,294,838,206,456; it cannot be converted to `long` via `longValueExact()`.

**Exercise 6.** Write a method to compute `totalBytes = rows × alignedRowBytes(columns,bpp,alignment)`; what do you do to prevent silent overflow?  
**Answer:** check that rows/columns/bpp are non-negative and alignment is positive; use `Math.multiplyExact(columns,bpp)`, compute padding via remainder, `Math.addExact(raw,padding)`, and then `Math.multiplyExact(rows,stride)`.

## 15. Production Checklist

1. Do all parameters have clear **units** and valid ranges?
2. Do `+`, `-`, `*` operations on sizes/offsets use exact arithmetic or a provably safe method?
3. If there is `int` multiplication, was the operand converted to `long` **before** multiplication?
4. Is there division/ceiling rounding? Have you avoided `bytes + pageSize - 1`?
5. Does alignment check for overflow at the padding addition step?
6. Have you distinguished logical sizes `long/BigInteger` from array length `int` and physical resources?
7. Does every narrowing conversion use `Math.toIntExact` or an equivalent checked alternative?
8. When a request exceeds the budget, does it fail transparently or split into chunks rather than under-allocating?
9. Do tests cover 0, negative, boundary, overflow producing positive values, and alignment overflow cases?
10. Have you verified that computing the right byte count **does not mean** allocation will always succeed?

## 16. Conclusion

- Use **`Math.multiplyExact`, `Math.addExact`, and `Math.toIntExact`** to detect overflow and data loss when calculating sizes.
- With standard integers, **assigning an overflowed `int` result to `long` does not fix the calculation**; you must widen the type beforehand.
- For aligned sizes, calculate padding from the remainder and add with `Math.addExact`; for page counts, use quotient and remainder instead of adding `pageSize-1`.
- Validate **negative arguments, units, and resource thresholds** alongside arithmetic checks.
- When the theoretical result exceeds `long`, use `BigInteger`; if an API requires `long` or `int`, convert via `*ValueExact` methods or `Math.toIntExact` to detect unrepresentable values.
- A **correct** count does not guarantee **sufficient** memory/disk; both layers of checks are required in a safe system.

Official Java SE 17 documentation:
- [`Math` — multiplyExact, addExact, subtractExact, toIntExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
- [`BigInteger` — multiply, longValueExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)
- [`ArithmeticException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArithmeticException.html)
- [`IllegalArgumentException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html)
