# Checking Bounds Before Allocating or Computing Sizes in Java

A size that looks valid when stored in an `int` can still become **a negative number, a number that is too small, or far beyond the memory budget** after multiplication or addition. Because Java decides the computation type from operand types, the failure often happens **before** the allocation statement:

```java
int elements = 1_000_000_000;
int bytesPerElement = 8;

int wrongBytes = elements * bytesPerElement;  // -589934592 (int overflow)
long exactBytes = (long) elements * bytesPerElement; // 8000000000
```

The mathematical product is 8,000,000,000 bytes, exceeding `Integer.MAX_VALUE`. `int * int` keeps the result only in a 32-bit range, so `wrongBytes` becomes `-589934592`. If a budget check uses the already-overflowed value, the application may **falsely accept it, allocate the wrong size, or throw a late exception**.

This lesson focuses on how to compute required sizes accurately, check bounds, and only then convert types or allocate—especially for **arrays, buffers, binary data, strings, and length metadata received externally**.

## 1. Why Do Size Calculations Easily Overflow?

The following expressions look simple, yet all carry risk:

- `count * bytesPerItem`: computing payload capacity from item count and per-item size.
- `headerBytes + payloadBytes`: computing total packet size.
- `offset + length`: determining the end position of an array or buffer slice.
- `capacity * growthFactor`: growing a data structure's capacity.
- `rows * columns` or `width * height * channels`: computing element count of a matrix/image.
- `(count + pageSize - 1) / pageSize`: rounding page count up; the addition can overflow before division.

`int` operands may all be valid and non-negative while **the intermediate result no longer fits in `int`**. Likewise, two valid `long` values can still yield a product exceeding `Long.MAX_VALUE`.

| Expression | Problem | Approach |
| --- | --- | --- |
| `int bytes = count * 8` | `int` overflow before checking | `long bytes = (long) count * 8` or `Math.multiplyExact` |
| `long bytes = count * 8`, where `count` is `int` | Multiplication is still `int` | Promote an operand **before** `*` |
| `int total = header + payload` | Sum can overflow | Compute in `long` or use `Math.addExact` |
| `int end = offset + length` | End position can overflow | Check via safe subtraction after verifying non-negativity |
| `int newCapacity = capacity * 2` | Doubling can wrap around to negative | Check before multiplying, cap growth limit |
| `(int) largeCount` | Narrowing `long` can drop high bits | Check range or use `Math.toIntExact` |

**Do not check only the final result** if an integer operator overflowed beforehand. Once bits are lost, a condition like `if (size <= maxBytes)` cannot restore the true size.

## 2. Validating Inputs and the "Compute Wide, Check, Then Narrow" Rule

A safe workflow consists of these steps:

1. **Clarify units and semantics**: `count` is number of elements, `bytesPerElement` is bytes per element, `maxBytes` is payload budget; never compare bytes against element counts.
2. **Validate input preconditions**: element count and offset are non-negative; unit size is positive; business limits are valid. Data from files, networks, or users must be treated as untrusted.
3. **Compute in an appropriate type and detect overflow**: widen to `long` **before an `int` operation that risks overflowing**, or use `Math.multiplyExact` / `Math.addExact`. If `long` is still insufficient, bound the domain upfront or compute with `BigInteger`.
4. **Check independent thresholds**: element count limit, payload capacity, single-allocation limit, total memory in use, and application configuration limits.
5. **Convert to the target API type after checking**: most array/`ByteBuffer` lengths take `int`; use `Math.toIntExact` when taking a `long` size that must fit within `int`.
6. **Allocate and handle resource failures**: a valid size does not guarantee the JVM has enough heap or can allocate a single large contiguous block.

For example, the right rule to compute the payload of a `long[]` with `n` elements is checking the product `n * Long.BYTES` in `long` against the budget **before** calling `new long[length]`. `Long.BYTES` equals 8; payload budget here excludes array overhead, alignment, or the cost of other objects.

### Promote before multiplying, do not cast an already-overflowed result

```java
int elements = 1_000_000_000;

long wrong = (long) (elements * 8);  // -589934592
long right = (long) elements * 8;    // 8000000000
```

In `wrong`, `int * int` already overflowed before the cast. In `right`, the `elements` operand is widened first, so `long * int` computes in `long`. Still, `long` can overflow with very large inputs; therefore **type promotion and bounds checking are two complementary requirements**.

## 3. Checking Overflow with `Math` APIs

### `Math.multiplyExact` and `Math.addExact`

`Math.multiplyExact` has `int` and `long` overloads; they throw `ArithmeticException` if the result exceeds the corresponding type's range:

```java
int count = 1_000_000_000;

// Math.multiplyExact(count, 8); // throws ArithmeticException: exceeds int
long payload = Math.multiplyExact((long) count, 8L); // 8000000000

long header = 128L;
long packetSize = Math.addExact(header, payload);    // 8000000128
```

If both arguments to `Math.multiplyExact` are `int`, the check runs **in the `int` range**. To get a `long` product, convert one operand to `long` before the call.

In particular, **do not write**:

```java
long wrong = Math.addExact((long) (count * 8), 128L);
```

Because `count * 8` already overflowed inside the parentheses. `Math.addExact` only checks the **addition** of its received inputs; it does not know the prior multiplication already failed.

### `Math.toIntExact`

APIs like `new byte[length]`, `ByteBuffer.allocate(capacity)`, and array indices require `int`. When you hold a `long length`, `Math.toIntExact(length)` throws `ArithmeticException` if the value is not representable in `int`:

```java
long elementCount = (long) Integer.MAX_VALUE + 1L;
// int unsafe = (int) elementCount;   // Can wrap around
// int safe = Math.toIntExact(elementCount); // Throws ArithmeticException
```

**The `int` limit is only a necessary condition.** An array with length near `Integer.MAX_VALUE` can exceed the JVM's practical array-size limit or run out of memory. Do not treat `Math.toIntExact` as proof that allocation will succeed.

### `BigInteger` when calculations exceed `long`

If `long * long` multiplication can exceed 64 bits yet must be computed accurately to **compare against a quota**, `BigInteger` avoids overflow:

```java
import java.math.BigInteger;

// Illustrative code snippet inside a method:
long rows = 5_000_000_000L;
long cols = 5_000_000_000L;
BigInteger cells = BigInteger.valueOf(rows)
        .multiply(BigInteger.valueOf(cols));
boolean tooLarge = cells.compareTo(BigInteger.valueOf(1_000_000L)) > 0;
// tooLarge = true
```

Check quantity conditions directly against configured limits whenever possible to avoid unnecessary calculations on untrusted data.

## 4. Array and Buffer Limits in Java

Java requires **a single array dimension's length to be a non-negative `int`**:

```java
int n = 8;
long[] values = new long[n];  // Primitive array with 8 elements
```

Notes:

- `new int[-1]` with a negative length throws `NegativeArraySizeException` at runtime.
- A non-negative size that is too large can cause `OutOfMemoryError`; the JVM also has a practical maximum array length, so do not assume you can allocate exactly `Integer.MAX_VALUE` elements.
- Even when theoretical payload fits the budget, **object headers, alignment, memory currently in use, object references, collections, and current heap state** all affect allocation feasibility.
- `ByteBuffer.allocate(int capacity)` creates a heap buffer, while `ByteBuffer.allocateDirect(int capacity)` requests direct memory; they have different resource constraints. Negative capacity is invalid and must be rejected beforehand. Both still use `int` for capacity.
- A `byte[]` with `n` elements means `n` bytes of data; for `long[]`, raw payload is `n * 8` bytes. For `Object[]` or object graphs, you cannot assume a fixed cost from element count alone because memory for references and referenced objects depends on the JVM and data structure.
- For strings, **character count is not synonymous with encoded byte count**: `String.length()` counts UTF-16 code units; UTF-8 has variable length. If a limit is measured in bytes for sending/writing data, compute it from the encoding output or an API providing actual byte size.
- `int[][]` is an **array of references to individual row arrays**; check row count, column count, total elements, and multi-array overhead, not just `rows * columns`.

`OutOfMemoryError` reflects a resource failure and **must not be used as a normal size-validation mechanism**. Applications must set proactive thresholds prior to allocation, while still acknowledging allocation can fail under memory pressure.

## 5. Checking `offset + length` Without Overflowing

Working with an array or buffer slice typically involves three values: `offset`, `length`, and `capacity`. The validity condition is:

\[
0 \leq offset,\quad 0 \leq length,\quad offset + length \leq capacity.
\]

Writing `offset + length <= capacity` directly can be dangerous if `int` addition overflows. For example, an `offset` near `Integer.MAX_VALUE` and a positive `length` turn the sum negative, causing an invalid condition to pass.

After verifying all are non-negative, use subtraction:

```java
static boolean validSlice(int offset, int length, int capacity) {
    return offset >= 0
            && length >= 0
            && capacity >= 0
            && offset <= capacity
            && length <= capacity - offset;
}
```

This is an illustrative method snippet, not a standalone class. Because Java evaluates `&&` sequentially and short-circuits when an earlier condition is false, `capacity - offset` runs only after `0 <= offset <= capacity` is known, so it cannot overflow. When working with built-in Java APIs, you can also use `Objects.checkFromIndexSize(fromIndex, size, length)` to validate index slices; it throws `IndexOutOfBoundsException` when invalid.

For required size additions such as `header + payload`, use `Math.addExact` instead of assuming signed integer results will not overflow.

## 6. Java 17+ Program Checking Bounds Before Allocating

The example below uses an **application element limit** and a **payload budget**. Both limits must be chosen realistically, not taken from untrusted values. The program allocates only a small array for illustration; oversized cases are checked arithmetically **without attempting to create huge arrays**.

Save to `AllocationBoundsDemo.java`:

```java
public class AllocationBoundsDemo {
    private static int checkedLength(
            long elements,
            long bytesPerElement,
            long maxElements,
            long maxPayloadBytes) {

        if (elements < 0 || bytesPerElement <= 0
                || maxElements < 0 || maxPayloadBytes < 0) {
            throw new IllegalArgumentException("invalid length or limits");
        }
        if (elements > maxElements) {
            throw new IllegalArgumentException("element limit exceeded");
        }

        long payloadBytes = Math.multiplyExact(elements, bytesPerElement);
        if (payloadBytes > maxPayloadBytes) {
            throw new IllegalArgumentException("payload budget exceeded");
        }

        return Math.toIntExact(elements);
    }

    private static boolean validSlice(int offset, int length, int capacity) {
        return offset >= 0 && length >= 0 && capacity >= 0
                && offset <= capacity && length <= capacity - offset;
    }

    public static void main(String[] args) {
        int elements = 1_000_000_000;
        System.out.println("unchecked int bytes: " + (elements * 8));
        System.out.println("exact long bytes: "
                + Math.multiplyExact((long) elements, 8));

        try {
            Math.multiplyExact(elements, 8);
        } catch (ArithmeticException e) {
            System.out.println("int product overflow detected");
        }

        int length = checkedLength(8, 8, 1_000, 1_024);
        long[] values = new long[length];
        System.out.println("allocated array length: " + values.length);

        try {
            checkedLength(200, 8, 1_000, 1_024);
        } catch (IllegalArgumentException e) {
            System.out.println("budget rejection: " + e.getMessage());
        }

        try {
            checkedLength(-1, 8, 1_000, 1_024);
        } catch (IllegalArgumentException e) {
            System.out.println("negative length rejected");
        }

        try {
            Math.multiplyExact(Long.MAX_VALUE, 2L);
        } catch (ArithmeticException e) {
            System.out.println("long product overflow detected");
        }

        try {
            Math.toIntExact((long) Integer.MAX_VALUE + 1L);
        } catch (ArithmeticException e) {
            System.out.println("array index range exceeded");
        }

        System.out.println("valid slice: " + validSlice(8, 4, 16));
        System.out.println("invalid slice: "
                + validSlice(Integer.MAX_VALUE - 1, 10, Integer.MAX_VALUE));

        try {
            int negative = -1;
            int[] unused = new int[negative];
        } catch (NegativeArraySizeException e) {
            System.out.println("negative array size exception");
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac AllocationBoundsDemo.java
java AllocationBoundsDemo
```

Stdout output:

```text
unchecked int bytes: -589934592
exact long bytes: 8000000000
int product overflow detected
allocated array length: 8
budget rejection: payload budget exceeded
negative length rejected
long product overflow detected
array index range exceeded
valid slice: true
invalid slice: false
negative array size exception
```

**Explanation of the checks:**

- The `int` product overflows to negative despite valid inputs; `long` computes the 8-billion value.
- `Math.multiplyExact(int, int)` reports overflow. `Math.multiplyExact(long, long)` also reports an error when the product exceeds `long`.
- `checkedLength` rejects negative counts, element counts exceeding quota, and payloads exceeding budget; `Math.toIntExact` ensures the result is representable as an `int`.
- With the illustrative limits of 1,000 elements and 1,024 payload bytes, 8 `long` elements use 64 payload bytes so allocating the small array is permitted. 200 elements require 1,600 payload bytes and are rejected.
- `validSlice` accepts slice `[8, 12)` within capacity 16, while rejecting a slice near `Integer.MAX_VALUE` even though direct addition would overflow.
- A negative length makes `new int[negative]` throw `NegativeArraySizeException`; real applications should block this condition **before** calling `new`.

This helper is a simple model for **a single `long[]` array**. In deployment, add policy thresholds suited to your application, check total budget across multiple allocations, and account for actual overhead bytes. Do not treat `maxPayloadBytes` as guaranteed free heap bytes.

## 7. Bounds-Checking Patterns for Common Scenarios

### Case A: Reading the length of a binary message

Suppose a packet has `headerBytes` and `itemCount` data items, each of fixed length `itemBytes`. The workflow should be:

1. Bound `itemCount` from input to the allowed range, verifying it is non-negative.
2. Compute `payload = Math.multiplyExact((long) itemCount, itemBytes)` after confirming each item size is valid.
3. Compute `packetBytes = Math.addExact(headerBytes, payload)`.
4. Compare `packetBytes` against the configured packet limit and the amount of data actually supplied.
5. Only after validation, convert types for an API requiring `int` and allocate the buffer.

Do not trust a length field just because it fits inside an `int`. A length field can be **valid on its own**, yet cause overflow when multiplied by unit size or added to a header.

### Case B: Multi-dimensional data tables / images

An image has `height` rows, `width` columns, and `channels` channels. If each sample takes one byte, sample count is `height * width * channels`. You should check:

- `height`, `width`, and `channels` are positive and within format limits.
- Intermediate products do not overflow; use `Math.multiplyExact` in `long` from the start.
- Total bytes stay within quota.
- The target array/buffer type supports the element count and JVM limits; one giant array may be unsuitable, requiring splitting into smaller chunks if the application permits.

If image data has strides, padding, or nested structures, `height * width * channels` is only a raw payload estimate; allocation math must match the actual layout.

### Case C: Growing capacity

A storage structure might try `newCapacity = oldCapacity * 2`. When `oldCapacity` is large, `int` multiplication easily overflows. Cap the maximum target and check before multiplying:

```java
int oldCapacity = 800;
int maximum = 1_000;
int newCapacity = oldCapacity > maximum / 2
        ? maximum
        : oldCapacity * 2; // 1000, does not exceed maximum
```

This example applies **when `oldCapacity >= 0` and `maximum > 0` have already been verified**. A real growth strategy must ensure `newCapacity >= minRequiredCapacity`; if that cannot be satisfied, reject the request. Do not automatically treat clamping to `maximum` as success if the data still needs more than `maximum`.

### Case D: Pagination and chunking

With `count >= 0` and `pageSize > 0`, the common formula `(count + pageSize - 1) / pageSize` can overflow when `count` is near `Integer.MAX_VALUE`. Replace it with:

```java
int count = Integer.MAX_VALUE;
int pageSize = 1000;
int pages = count / pageSize + (count % pageSize == 0 ? 0 : 1);
```

This avoids adding before dividing and keeps the page count within `int` when `count` is non-negative and `pageSize` is positive. For `long` counts or very large pagination requirements, evaluate the bounds of that range separately.

## 8. Failure Classes to Distinguish

| Issue | Example | How to Handle |
| --- | --- | --- |
| **Arithmetic overflow** | `int count * 8` returns a negative number | Promote before the operation, `Math.multiplyExact` |
| **Lossy narrowing** | `(int) longLength` with a very large length | Range check, `Math.toIntExact` |
| **Negative length** | `new byte[-1]` | Validate input; `NegativeArraySizeException` is a symptom |
| **Exceeding JVM limit / out of memory** | `new long[veryLarge]` | Practical quotas, streaming/chunking design; never rely on `OutOfMemoryError` for validation |
| **Unit mismatch** | Comparing `elementCount` against a byte-based quota | State byte/element/character explicitly and convert units properly |
| **Broken slice check** | `offset + length <= capacity` after sum overflows | Check non-negativity then use `length <= capacity - offset` |
| **Cumulative quota exceeded** | Many small arrays coexisting | Track total usage, concurrency limits, and memory pressure |
| **Trusting client-supplied length fields** | File/network reports an oversized length | Check quota before reading everything and before allocating |

## 9. Common Misconceptions

1. **"If all operands are non-negative, the size is non-negative too."** False: `int` multiplication/addition can overflow into a negative value.
2. **"The target is `long`, so `int * int` automatically uses 64 bits."** False: convert an operand to `long` **before multiplying**.
3. **"`(long) (count * unitSize)` fixes overflow."** False: the `int` multiplication has already occurred.
4. **"`Math.multiplyExact(count, 8)` automatically returns `long` if the result is large."** False: the `(int, int)` overload throws when exceeding `int`; to get `long`, promote an operand.
5. **"With `long`, overflow is impossible."** False: `long * long` can still exceed 64 bits.
6. **"If `Math.toIntExact` succeeds, allocation will succeed."** False: JVM limits, heap, pressure, layout, and quotas still apply.
7. **"`new byte[negativeSize]` automatically produces an empty array."** False: it throws `NegativeArraySizeException`.
8. **"`offset + length <= capacity` is safe for all integers."** False: addition can overflow; check via subtraction after verifying non-negativity.
9. **"Limiting payload bytes is enough to bound heap usage."** False: headers, alignment, object graphs, references, and concurrent allocations also consume memory.
10. **"`String.length()` is the UTF-8 byte count."** False: `String.length()` counts UTF-16 code units; encoded byte length varies by content.
11. **"Catching `OutOfMemoryError` is enough for validation."** False: by then the JVM may already be critically starved of resources; **check, cap, and stream** from the start.
12. **"You only need to check once at allocation time."** Insufficient: growth addition/multiplication formulas and holding multiple concurrent allocations also need bounds.

## 10. Self-Check

- **Does `int count = 1_000_000_000; long bytes = count * 8;` equal 8 billion?** No. `int` multiplication overflows before assignment. Write `(long) count * 8` or `Math.multiplyExact((long) count, 8L)`.
- **Can every valid `long` convert to a valid `int`?** No; `Math.toIntExact` throws an error when the value lies outside the 32-bit range.
- **What does `Math.multiplyExact(Long.MAX_VALUE, 2L)` do?** Throws `ArithmeticException` because the product exceeds the `long` range.
- **Why is checking `offset <= capacity` and `length <= capacity - offset` better than adding directly?** Under proper non-negativity preconditions, it never computes a sum that could overflow.
- **What is the theoretical payload of 200 `long` elements?** `200 * 8 = 1600` bytes, excluding array overhead.
- **What if the byte quota is 1024 and 1600 payload bytes are needed?** Reject **before allocating**; do not wait for `OutOfMemoryError`.
- **Why isn't `Integer.MAX_VALUE` a guaranteed allocatable array limit?** Allocatable size also depends on the JVM, available memory, and overhead; application limits usually need to be smaller.

**Remember:** When computing sizes, **validate inputs → compute in a wide-enough type and check overflow → compare against quota → convert to the API type → only then allocate**. Never use an already-overflowed size to judge safety. `long` avoids many `int` overflows, while `Math.*Exact`, application limits, and resource checks manage the cases where even `long` is not enough.
