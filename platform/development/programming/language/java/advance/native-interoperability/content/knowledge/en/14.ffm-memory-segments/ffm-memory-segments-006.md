# MemorySegment: copying, filling, mismatching, and converting to Java arrays

## 1. Objectives and Java version

**`MemorySegment`** in the Foreign Function & Memory API (FFM) describes a contiguous memory region with an explicit length; that region can belong to the **Java heap** (heap segment) or be **native/off-heap memory** (native segment). When you need to process binary data or transfer data between Java and native code, four groups of operations are especially useful:

1. **Copying**: `copyFrom`, and overloads of `MemorySegment.copy`.
2. **Filling data**: `fill(byte)`, filling the entire region or a slice (`asSlice`).
3. **Comparing content**: `mismatch` to find the first differing **byte** position.
4. **Converting data back to a Java array**: `toArray(ValueLayout...)` or copying directly into an existing array.

This lesson belongs to the **MemorySegment** group of *Java Advance - native-interoperability*. Although placed alongside JNI topics, these `MemorySegment` operations belong to the **FFM API**, **not** JNI's `Get<Type>ArrayElements` functions. You can practice them using Java alone, without writing C.

**Version requirement:** use **JDK 22 or later**, with the stable API in the `java.lang.foreign` package under JEP 454. Java 17 does not have this standard stable API; Java versions prior to JDK 22 used incubator/preview APIs with different names or syntax. The runnable sample code below intentionally targets **Java 22+**, and does not claim to compile on JDK 17. The allocation, copy, fill, mismatch, and toArray operations in the examples **do not require `--enable-preview` or loading a native library**.

### 1.1. Quick operations table

| Need | API | Result |
| --- | --- | --- |
| Create a view over an existing Java array | `MemorySegment.ofArray(array)` | **Shares the backing storage** of the primitive array |
| Allocate native memory | `arena.allocate(bytes)` | Off-heap segment, lives with the `Arena` |
| Copy entire source from offset 0 into destination | `dest.copyFrom(src)` | Returns `dest`; dest must be large enough |
| Copy a range of bytes | `MemorySegment.copy(src, srcOffset, dst, dstOffset, bytes)` | Copies exact `bytes` bytes |
| Copy elements with a layout | `MemorySegment.copy(src, srcLayout, srcOffset, dst, dstLayout, dstOffset, count)` | Copies `count` elements; can swap byte order |
| Fill every byte in a segment | `segment.fill((byte) 0)` | Returns the segment itself; data changes in place |
| Compare data | `left.mismatch(right)` | Offset of the first differing byte, or `-1` |
| Copy entire segment to a `byte[]` array | `segment.toArray(ValueLayout.JAVA_BYTE)` | **New**, independent Java array |
| Copy entire segment to an `int[]` array | `segment.toArray(ValueLayout.JAVA_INT)` | **New** Java array, size must be valid |
| Copy part of a segment to an existing array | `MemorySegment.copy(segment, layout, offset, array, index, count)` | Writes into the passed array itself |
| Copy from an array into a segment | `MemorySegment.copy(array, index, segment, layout, offset, count)` | Writes into the destination segment |

In the table, **segment offsets are measured in bytes (`long`)**; **Java array indices are measured in elements (`int`)**. This is a very common source of bugs.

## 2. Understanding memory, size, and lifecycle properly

### 2.1. Heap segments can share a Java array

```java
int[] numbers = {10, 20, 30};
MemorySegment heap = MemorySegment.ofArray(numbers);

heap.setAtIndex(ValueLayout.JAVA_INT, 1, 99);
System.out.println(java.util.Arrays.toString(numbers));
// [10, 99, 30]
```

**`MemorySegment.ofArray(numbers)` does not copy data.** It creates a segment **backed by** the `numbers` array. Changes to data through the segment are reflected in the array and vice versa. This segment has an automatic scope that keeps the backing array accessible and is allowed to be used from different threads, though concurrent access must still be properly synchronized.

**Therefore:**

- `MemorySegment.ofArray(original)` creates a **view that shares data**.
- `segment.toArray(ValueLayout.JAVA_INT)` creates an **independent array by copying**.
- `dest.copyFrom(source)` performs a **copy**; source and destination remain separate regions if they do not share a common backing.
- `segment.asSlice(...)` creates a **view/slice** over an existing region; **no copy**.

If your API requires a "snapshot that does not change when the source data is modified", you need a **real copy**, not just creating `ofArray` or `asSlice`.

### 2.2. Native segments and `Arena`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(32);
    System.out.println(block.byteSize()); // 32
}
// After the arena is closed, block must no longer be accessed.
```

`Arena.ofConfined()` creates a scope in which only the **owning thread** is allowed to access the segment; `try-with-resources` automatically closes the arena and frees the native memory upon exiting the block. Do not return a native segment outside and use it after the arena is closed. `Arena.ofShared()` is suitable for multi-threaded access, but **does not automatically make a program thread-safe**. Every segment lifecycle needs a clear owner.

**`byteSize()` always returns the number of bytes**, not the number of logical elements. For example:

- `MemorySegment.ofArray(new byte[6]).byteSize()` = `6`.
- `MemorySegment.ofArray(new int[6]).byteSize()` = `24` because an `int` takes 4 bytes.
- A 24-byte native segment can hold 6 `int` values or 24 `byte` values depending on the `ValueLayout` used to interpret it.

All `get`, `set`, `copy`, and `toArray` accesses must satisfy the **bounds, live scope, and thread access permission** constraints.

### 2.3. `ValueLayout` helps interpret the content

`MemorySegment` manages a **byte region**. To know whether a group of bytes represents an `int`, `long`, or `double`, you provide a `ValueLayout`:

| Layout | Java carrier | Typically specified size |
| --- | --- | --- |
| `ValueLayout.JAVA_BYTE` | `byte` | 1 byte |
| `ValueLayout.JAVA_SHORT` | `short` | 2 bytes |
| `ValueLayout.JAVA_CHAR` | `char` | 2 bytes |
| `ValueLayout.JAVA_INT` | `int` | 4 bytes |
| `ValueLayout.JAVA_FLOAT` | `float` | 4 bytes |
| `ValueLayout.JAVA_LONG` | `long` | 8 bytes |
| `ValueLayout.JAVA_DOUBLE` | `double` | 8 bytes |

A `ValueLayout` also carries **alignment** and **byte order** information. `JAVA_INT` represents the `int` type with the platform's default byte order. If data comes from a file/network/native API with a fixed byte order, you must specify the appropriate `withOrder(ByteOrder.BIG_ENDIAN)` or `LITTLE_ENDIAN`.

## 3. Copying an entire region with `copyFrom`

The simple way when the destination is already large enough:

```java
byte[] input = {1, 2, 3, 4};
MemorySegment heap = MemorySegment.ofArray(input);

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeData = arena.allocate(4);
    nativeData.copyFrom(heap);

    System.out.println(
            java.util.Arrays.toString(
                    nativeData.toArray(ValueLayout.JAVA_BYTE)));
    // [1, 2, 3, 4]
}
```

Syntax: **`destination.copyFrom(source)`**. This method copies all `source.byteSize()` bytes, starting at offset `0` into destination starting at offset `0`. It returns destination itself so you can write `destination.copyFrom(source).asSlice(...)` if desired.

**Conditions:** `destination.byteSize() >= source.byteSize()`, destination is writable, both segments are alive, and the current thread has access permission. If destination is **larger**, `copyFrom` **only copies the source's byte count**; the extra bytes in destination are not modified per the copy contract. If destination is too small, an `IndexOutOfBoundsException` will be thrown.

Do not mistake "copyFrom" for "reassigning a reference variable"; the data is copied to the destination region. Modifying the source array after copying does not automatically change the native buffer **if the two regions do not share backing storage**.

### 3.1. If you only need to copy a portion

Instead of copying the entire source, use `MemorySegment.copy` and compute offsets explicitly:

```java
// Snippet placed within live source/destination scope.
MemorySegment.copy(source, 2L, destination, 5L, 3L);
```

This means **3 bytes** starting at byte offset 2 of `source` are copied into byte offset 5 of `destination`. The call does not resize either segment. You must ensure that the ranges `[2, 5)` and `[5, 8)` both lie within their respective bounds.

You can also create slices:

```java
destination.asSlice(5L, 3L).copyFrom(source.asSlice(2L, 3L));
```

`asSlice(offset, length)` creates a view without copying. When the data is already bounded by the slice, `copyFrom` operates on the exact slice region; you do not need to add the offset again.

## 4. `fill(byte)`: filling data by **byte**, not by element

```java
MemorySegment segment = MemorySegment.ofArray(
        new byte[]{10, 20, 30, 40, 50});

segment.asSlice(1, 3).fill((byte) 7);

System.out.println(java.util.Arrays.toString(
        segment.toArray(ValueLayout.JAVA_BYTE)));
// [10, 7, 7, 7, 50]
```

Here `asSlice(1, 3)` represents three bytes at offsets 1, 2, 3 in the original segment. `fill((byte)7)` writes the value 7 to **each byte** of that slice. The two bytes outside the slice remain unchanged.

### 4.1. Zero-filling commonly used when initializing/resetting a buffer

```java
segment.fill((byte) 0);
```

This call writes `0` across the entire region of the referenced segment, provided the segment is writable, its scope is alive, and the thread has permission. For native memory from a JDK 22 arena, newly allocated regions are **zero-initialized**, but `fill((byte)0)` is still useful when **reusing** a buffer or when wanting to reset a slice after data has changed.

### 4.2. Warning when filling a segment containing `int[]`

If a segment contains 3 `int` values, do not interpret:

```java
int[] values = {10, 20, 30};
MemorySegment.ofArray(values).fill((byte) 1);
```

as "set every `int` to 1". The call writes **byte `0x01` into every byte position**; each `int` consists of four `01` bytes, so the value becomes `0x01010101` = **16843009**.

To set **each `int` element = 1**:

```java
MemorySegment ints = MemorySegment.ofArray(new int[3]);
for (long i = 0; i < 3; i++) {
    ints.setAtIndex(ValueLayout.JAVA_INT, i, 1);
}
```

To bulk-fill structured values into native memory, consider using `setAtIndex` with a layout or copying from a pre-filled array. `fill` is ideal for resetting/filling a **byte pattern**; it does not understand arithmetic types stored in the data.

### 4.3. Why isn't `fill` suitable for every situation?

- There is no guarantee that bytes are written in a **specific observable order** while filling; do not use it as a multi-thread synchronization primitive.
- Using it on a read-only segment throws `IllegalArgumentException`.
- Using it on a segment belonging to a closed arena throws `IllegalStateException`.
- Using it from a thread that does not own a confined arena throws `WrongThreadException`.

If you need atomic writes, ordering, or data structures shared across threads, you must design synchronization separately; `fill` is only a memory-content operation.

## 5. `mismatch`: finding the first differing byte

`MemorySegment.mismatch` compares **content**, not identity/reference or address. The commonly used form:

```java
long difference = left.mismatch(right);
```

Results:

- `-1` if **all bytes and lengths** of both segments are identical.
- An integer `>= 0` which is the **byte offset** of the first difference.
- If one segment is a **proper prefix** of the other, the result is the **byte length of the shorter segment**. In this case, the two regions have identical leading bytes but do not have the same length.
- It does not return an `int`/`double` element index; you must convert it if needed.

Example:

```java
MemorySegment a = MemorySegment.ofArray(new byte[]{1, 2, 3});
MemorySegment b = MemorySegment.ofArray(new byte[]{1, 2, 9});
MemorySegment c = MemorySegment.ofArray(new byte[]{1, 2});

System.out.println(a.mismatch(a)); // -1
System.out.println(a.mismatch(b)); // 2
System.out.println(a.mismatch(c)); // 2: c is a prefix of a
```

**Do not confuse `mismatch` with `equals`:** `equals` checks equivalence of segment objects according to `MemorySegment` rules, and is not the recommended API for determining whether two byte regions have the same content. To compare bytes, use `mismatch`.

### 5.1. Comparing a sub-region

There are two ways:

**Approach A — comparing slices**:

```java
long mismatch = left.asSlice(10, 4)
                    .mismatch(right.asSlice(20, 4));
```

The result is the position **relative to the start of the two slices**, in the range 0..3 or `-1`. If you need the absolute offset in `left` when there is a difference, add `10` to the result **only when `mismatch >= 0`**.

**Approach B — static method with ranges**:

```java
long mismatch = MemorySegment.mismatch(
        left, 10, 14,
        right, 20, 24);
```

The ranges have the form **`[fromOffset, toOffset)`**, where the **end offset is exclusive**. In the example both compare 4 bytes; the result is also computed **relative to the start of the selected region**, not the absolute offset of the entire segment.

### 5.2. Be careful when checking numeric data

Because it compares **bytes**, two numerically equal values can be treated as different if their byte order or encoding differs. `mismatch` does not automatically endian-swap, convert `int` types, or canonicalize `NaN`. If you want to compare **logical values** rather than bytes, you must read using the same layout/endianness and compare the Java values; whereas if you want to verify **wire-format/binary-format**, comparing bytes is the exact goal.

For large arrays, `mismatch` is useful for finding the first differing offset when validating copy/serialization; it does not create a copy of the data and does not return a complete list of all differing offsets.

## 6. `toArray`: converting an entire segment to a new Java array

When you need to return native data to ordinary Java code:

```java
byte[] bytes = segment.toArray(ValueLayout.JAVA_BYTE);
int[] ints   = segment.toArray(ValueLayout.JAVA_INT);
long[] longs = segment.toArray(ValueLayout.JAVA_LONG);
```

These are **three independent example choices**, each layout requiring the segment to have matching content; you cannot always read the same buffer with every layout. `toArray` creates **a new array**, copying the content through the provided layout.

### 6.1. Choosing a layout to determine the array type

| Calling `toArray` | Result type | Requirement |
| --- | --- | --- |
| `toArray(ValueLayout.JAVA_BYTE)` | `byte[]` | One element per byte |
| `toArray(ValueLayout.JAVA_CHAR)` | `char[]` | Byte count divisible by 2 |
| `toArray(ValueLayout.JAVA_SHORT)` | `short[]` | Byte count divisible by 2 |
| `toArray(ValueLayout.JAVA_INT)` | `int[]` | Byte count divisible by 4 |
| `toArray(ValueLayout.JAVA_FLOAT)` | `float[]` | Byte count divisible by 4 |
| `toArray(ValueLayout.JAVA_LONG)` | `long[]` | Byte count divisible by 8 |
| `toArray(ValueLayout.JAVA_DOUBLE)` | `double[]` | Byte count divisible by 8 |

`byteSize() / layout.byteSize()` must fit within a Java array length (`Integer.MAX_VALUE`), and the access must be valid. For multi-byte data, the layout's byte order participates in interpreting the data; if the layout's byte order differs from native byte order, `toArray` performs a byte-order swap per element as described in the API documentation.

**There is no `toArray(ValueLayout.JAVA_BOOLEAN)` among Java 22's `toArray` overloads.** Array bulk-copy overloads also support `byte[]`, `char[]`, `short[]`, `int[]`, `float[]`, `long[]`, `double[]`, and do not support `Object[]` or `String[]`. For data representing booleans or structs, define an encoding convention and convert to the required Java objects yourself.

### 6.2. `toArray` does not share the same data region

```java
MemorySegment nativeSegment = /* live native segment */;
int[] snapshot = nativeSegment.toArray(ValueLayout.JAVA_INT);

snapshot[0] = 500;
// There is no guarantee this change will be written back to nativeSegment.
```

This illustrative snippet **is not standalone** because it requires an existing `nativeSegment` with a valid size. The resulting array is a **copy**; modifying `snapshot` will not automatically write to the original region. To write back, you need `MemorySegment.copy` from the array into the segment or a `setAtIndex` loop.

### 6.3. When only a part is needed, avoid creating an overly large array

`toArray` copies the **entire** segment. For very large data, take a slice or copy directly into a small array:

```java
byte[] header = segment.asSlice(0, 16)
                       .toArray(ValueLayout.JAVA_BYTE);
```

Before using, ensure `segment.byteSize() >= 16`. If the data has billions of bytes, creating a huge Java array may be impractical or exceed limits; the API does not automatically paginate/chunk for you. You can iterate over slices with a validated size limit.

## 7. Runnable example — part 1: copy, fill, mismatch, and `byte[]`

Create the file **`SegmentBulkDemo.java`** (no package declaration). This is a **standalone** Java program using JDK 22+; no C/JNI required.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public final class SegmentBulkDemo {
    private SegmentBulkDemo() {}

    public static void main(String[] args) {
        byte[] source = {1, 2, 3, 4, 5, 6};
        MemorySegment heap = MemorySegment.ofArray(source);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment nativeData = arena.allocate(source.length);

            // 1. Copy heap -> native. Two independent storage regions.
            nativeData.copyFrom(heap);
            System.out.println("copy = " +
                    Arrays.toString(nativeData.toArray(ValueLayout.JAVA_BYTE)));

            source[0] = 99;
            System.out.println("native[0] = " +
                    nativeData.get(ValueLayout.JAVA_BYTE, 0));

            // 2. Fill three bytes in slice [1, 4).
            nativeData.asSlice(1, 3).fill((byte) 9);
            System.out.println("filled = " +
                    Arrays.toString(nativeData.toArray(ValueLayout.JAVA_BYTE)));

            // 3. Mismatch returns the first differing byte position.
            MemorySegment clone = arena.allocate(nativeData.byteSize());
            clone.copyFrom(nativeData);
            System.out.println("equal mismatch = " + nativeData.mismatch(clone));

            clone.set(ValueLayout.JAVA_BYTE, 3, (byte) 8);
            System.out.println("changed mismatch = " + nativeData.mismatch(clone));

            // 4. toArray always creates a new Java array.
            byte[] javaCopy = nativeData.toArray(ValueLayout.JAVA_BYTE);
            javaCopy[0] = 77;
            System.out.println("native after array edit = " +
                    nativeData.get(ValueLayout.JAVA_BYTE, 0));
            System.out.println("java copy = " + Arrays.toString(javaCopy));

            // 5. Copy a range from the segment into an existing Java array.
            byte[] picked = new byte[3];
            MemorySegment.copy(
                    nativeData, ValueLayout.JAVA_BYTE, 2,
                    picked, 0, picked.length);
            System.out.println("picked = " + Arrays.toString(picked));

            // 6. Copy back from a Java array into a position in the segment.
            byte[] patch = {7, 8};
            MemorySegment.copy(
                    patch, 0,
                    nativeData, ValueLayout.JAVA_BYTE, 4, patch.length);
            System.out.println("patched = " +
                    Arrays.toString(nativeData.toArray(ValueLayout.JAVA_BYTE)));

            // 7. ofArray shares data with the backing array.
            heap.set(ValueLayout.JAVA_BYTE, 1, (byte) 42);
            System.out.println("source = " + Arrays.toString(source));
        }
    }
}
```

### 7.1. Compile/run

Use JDK 22 or later and run from the directory containing the file:

```bash
javac SegmentBulkDemo.java
java SegmentBulkDemo
```

No `--enable-preview` needed with JDK 22+; no `System.loadLibrary` needed. The application only manipulates `MemorySegment` through the FFM Java API.

### 7.2. Exact stdout

```text
copy = [1, 2, 3, 4, 5, 6]
native[0] = 1
filled = [1, 9, 9, 9, 5, 6]
equal mismatch = -1
changed mismatch = 3
native after array edit = 1
java copy = [77, 9, 9, 9, 5, 6]
picked = [9, 9, 5]
patched = [1, 9, 9, 9, 7, 8]
source = [99, 42, 3, 4, 5, 6]
```

**Step-by-step explanation:**

1. `copyFrom` transfers data from the `source` array into the native block. Modifying `source[0]=99` afterward does not modify `nativeData`, so `native[0]=1`.
2. `asSlice(1,3).fill((byte)9)` only modifies the three bytes at offsets 1, 2, 3; the last two bytes and the first byte remain unchanged.
3. `clone.copyFrom(nativeData)` produces identical content so `mismatch=-1`. Changing byte 3 of clone to 8 makes `mismatch=3`.
4. `toArray` creates a new array: modifying `javaCopy[0]=77` does not affect nativeData.
5. `MemorySegment.copy(..., offset=2, ..., length=3)` extracts bytes 2, 3, 4 as `[9,9,5]`.
6. The array→segment overload writes `[7,8]` into byte offsets 4,5 of nativeData.
7. `heap` is a view over the `source` array itself, so modifying via `heap.set` sets `source[1]=42`, alongside `source[0]=99` which was modified directly.

When `try` finishes, the arena closes and the native blocks are no longer valid. The `source` and `javaCopy` arrays remain ordinary Java heap arrays, independent of the arena's lifecycle.

## 8. Runnable example — part 2: converting `int[]`, offsets, and layouts

A common mistake is using `byteSize()` as the number of `int`s, or writing `dstOffset=1` when wanting to start at the second `int` element. The following code practices copying **with a layout** to avoid confusion.

Create the file **`SegmentIntDemo.java`**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public final class SegmentIntDemo {
    private SegmentIntDemo() {}

    public static void main(String[] args) {
        int[] values = {10, 20, 30, 40};

        long intBytes = ValueLayout.JAVA_INT.byteSize();
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment nativeInts = arena.allocate(
                    values.length * intBytes,
                    ValueLayout.JAVA_INT.byteAlignment());

            // Element count = 4, not 16.
            MemorySegment.copy(
                    values, 0,
                    nativeInts, ValueLayout.JAVA_INT, 0, values.length);

            // Modify element at index=1 in native memory.
            nativeInts.setAtIndex(ValueLayout.JAVA_INT, 1, 99);

            int[] exported = nativeInts.toArray(ValueLayout.JAVA_INT);
            System.out.println("native ints = " + Arrays.toString(exported));
            System.out.println("original ints = " + Arrays.toString(values));

            // Start from byte offset = 1 * 4, take 2 elements.
            int[] middle = new int[2];
            MemorySegment.copy(
                    nativeInts, ValueLayout.JAVA_INT, intBytes,
                    middle, 0, middle.length);
            System.out.println("middle = " + Arrays.toString(middle));

            // ofArray is a view: modifying the heap segment changes values.
            MemorySegment heapView = MemorySegment.ofArray(values);
            heapView.setAtIndex(ValueLayout.JAVA_INT, 0, -1);
            System.out.println("heap-backed ints = " +
                    Arrays.toString(values));
        }
    }
}
```

Run commands:

```bash
javac SegmentIntDemo.java
java SegmentIntDemo
```

Exact stdout:

```text
native ints = [10, 99, 30, 40]
original ints = [10, 20, 30, 40]
middle = [99, 30]
heap-backed ints = [-1, 20, 30, 40]
```

**Why this is correct:** `values.length=4` elements, each `int` has a size of 4 bytes, so the native segment needs 16 bytes. `setAtIndex(JAVA_INT,1,99)` is equivalent to writing an `int` at byte offset 4, while `MemorySegment.copy` with an array uses `elementCount` as the number of elements and the segment's `dstOffset/srcOffset` in bytes.

When `nativeInts.toArray(JAVA_INT)` creates `exported`, it is an independent copy, so `values` has not changed to `99`. Only when `heapView.setAtIndex(...)` is called is the `values` array modified directly through the heap-backed segment.

### 8.1. Do not force every byte buffer into `int[]`

With `byteSize() = 6`, calling `toArray(ValueLayout.JAVA_INT)` cannot divide evenly into 4-byte elements and will fail (per Javadoc, `IllegalStateException` if the data cannot be converted to an array of that type). How to handle it: validate `size % layout.byteSize() == 0` or take a slice of valid length, then use the right layout.

If a segment is very large such that `byteSize()/layout.byteSize() > Integer.MAX_VALUE`, a single ordinary Java array cannot represent all elements at once. You need to split into batches/chunks.

### 8.2. `setAtIndex` and `getAtIndex` help reduce offset bugs

Compare:

```java
int second = nativeInts.get(ValueLayout.JAVA_INT, 4L);
int alsoSecond = nativeInts.getAtIndex(ValueLayout.JAVA_INT, 1L);
```

This is an **illustrative snippet** when `nativeInts` already has 8 bytes or more and proper alignment. Both statements point to the second `int` element if `JAVA_INT.byteSize()=4`. `getAtIndex` multiplies the index by the layout size; when processing arrays of equal-sized elements it is easier to read than computing offsets manually.

## 9. Safe copying when source and destination overlap

`MemorySegment.copy` supports overlapping regions with semantics similar to **memmove**: when the source and destination regions overlap in a way the API recognizes, the result is as if copied through a temporary buffer, rather than naively overwriting unread data. Standalone Java 22+ example:

```java
import java.lang.foreign.MemorySegment;
import java.util.Arrays;

public class SegmentOverlapDemo {
    public static void main(String[] args) {
        byte[] bytes = {1, 2, 3, 4, 5};
        MemorySegment view = MemorySegment.ofArray(bytes);

        MemorySegment.copy(view, 0, view, 1, 4);

        System.out.println(Arrays.toString(bytes));
    }
}
```

Compile/run:

```bash
javac SegmentOverlapDemo.java
java SegmentOverlapDemo
```

Output:

```text
[1, 1, 2, 3, 4]
```

In this call the source byte region is `[0,4)` and the destination region is `[1,5)` of the **same backing array**. `copy` does not turn the array into `[1,1,1,1,1]` like a buggy sequential copy loop would.

**Important limitation:** if two segments **are not recognized as overlapping** yet refer to overlapping physical memory regions via **different addresses** (for example mapping the same file in an unusual way), the Javadoc states the result of bulk copy is **undefined**. Do not turn normal overlap guarantees into a promise for all aliasing through native addresses.

## 10. Element-wise copying, byte order, and numeric data

For multi-byte numeric data, there are two important copy styles:

**A. Raw byte copy**:

```java
MemorySegment.copy(src, 0, dst, 0, 16);
```

Copies **16 bytes** verbatim, without interpreting the content. Byte N goes to byte N. Suitable when you need to preserve the exact **binary representation**.

**B. Layout-based copy**:

```java
MemorySegment.copy(
        src, ValueLayout.JAVA_INT, 0,
        dst, ValueLayout.JAVA_INT, 0,
        4);
```

Copies **4 `int` elements**, 4 bytes each, 16 bytes total. There is an overload accepting source and destination layouts; if the two layouts have the same size but **different byte orders**, the API can **byte-swap per element** during the copy. The source/destination layouts must have the same `byteSize` and must respect the alignment of each side.

Conceptual example when importing big-endian network data into a native-order buffer:

```java
import java.nio.ByteOrder;

var networkInt = ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
var localInt = ValueLayout.JAVA_INT.withOrder(ByteOrder.nativeOrder());

MemorySegment.copy(
        networkBuffer, networkInt, 0,
        localBuffer, localInt, 0,
        count);
```

**This is an illustrative snippet, not a standalone runnable file**: `networkBuffer` and `localBuffer` must be live/properly sized/properly aligned MemorySegments, and `count` is the number of elements. Layout-based copying preserves the numeric meaning of `int` across two byte orders, whereas raw byte copying preserves the byte sequence in memory.

**Endianness and alignment are two separate properties:**

- `withOrder` adjusts how byte order is interpreted; **it does not change the size** of an `int`.
- `byteAlignment` sets the alignment constraint; a heap segment backed by `byte[]` does not by default have sufficient alignment for `JAVA_INT`.
- When you need to access an `int` from a `byte[]` at an unaligned position, use `ValueLayout.JAVA_INT_UNALIGNED` or a layout with suitably lowered alignment, and still compute offsets accurately.
- `toArray(ValueLayout.JAVA_INT.withOrder(...))` uses the layout to interpret data into `int` values before placing them into the Java array.

## 11. `MemorySegment.ofArray`, `MemorySegment.copy`, and `toArray`: differences in ownership

Consider these three lines (using a `byte[] original` and a live `nativeBuffer` segment):

```java
MemorySegment heapView = MemorySegment.ofArray(original);
nativeBuffer.copyFrom(heapView);
byte[] independent = nativeBuffer.toArray(ValueLayout.JAVA_BYTE);
```

- **`heapView`** shares backing with `original`. Modifying data through the view modifies `original`.
- **`nativeBuffer`** is a separate region if allocated independently in an arena. After `copyFrom`, its content equals original at the time of copy, but it **does not automatically stay in sync** with original.
- **`independent`** is a new `byte[]` from `toArray`. Modifying it does not change `nativeBuffer`.

Diagram:

```text
Java byte[] original
          ^
          | SHARES (no copy)
          v
MemorySegment.ofArray(original)
          |
          | copyFrom (actual byte copy)
          v
    nativeBuffer (off-heap)
          |
          | toArray(JAVA_BYTE) (actual byte copy)
          v
 Java byte[] independent
```

**Common mistake:** using `MemorySegment.ofArray(array)` and calling it "an array copied out to native memory". Incorrect: the segment is still backed by the Java array. To get independent native memory, allocate via an arena and then copy.

Conversely, sometimes **you don't need to copy**: if you only need to fill/checksum data in an existing Java array, creating a heap view with `ofArray` may be the better choice; keep scope and thread safety in mind.

## 12. Other common conversion APIs

### 12.1. Copying directly from a segment into an existing Java array

```java
byte[] output = new byte[8];
MemorySegment.copy(segment, ValueLayout.JAVA_BYTE,
                   4L, output, 0, output.length);
```

This example assumes `segment` is alive and has at least 12 bytes. It **does not create a new array** inside the copy API; the caller already allocated `output`. The parameter `srcOffset=4L` is a **byte offset**; `dstIndex=0` is an **array element index**; `elementCount=8`.

**Why this is useful:** you want to reuse Java arrays in a system processing many batches to reduce object creation/heap garbage. However, copying still has the cost of transferring bytes between the two regions.

### 12.2. Copying from a Java array into a native segment

```java
int[] source = {10, 20, 30};
MemorySegment.copy(source, 0, nativeInts,
                   ValueLayout.JAVA_INT, 0L, source.length);
```

This snippet assumes `nativeInts` has at least 12 bytes, proper alignment, and is writable. The array index (`0`) is in **`int` element** units, whereas the segment offset (`0L`) is measured in bytes. `MemorySegment.copy` has an overload accepting `Object` for the array, but checks the carrier: do not pass a `double[]` with a `JAVA_INT` layout.

### 12.3. Copying to a slice / reading a slice

```java
MemorySegment header = entireSegment.asSlice(0, 16);
byte[] bytes = header.toArray(ValueLayout.JAVA_BYTE);
```

`header` is a **view**, `bytes` is a **copy**. After obtaining `bytes`, the Java data exists independently of the lifetime of the native `entireSegment`. However, `header` is still bound by the scope and thread confinement of the source region.

### 12.4. `asByteBuffer` when NIO is needed

`MemorySegment.asByteBuffer()` creates a `ByteBuffer` view of the segment, suitable when integrating with libraries that only accept NIO buffers. This is **not** `toArray`, and the byte buffer's sharing/access to memory must obey the segment's scope and bounds. If you need an **independent Java array**, prefer `toArray` or direct copying.

For very large segments, `ByteBuffer` has an `int`-based index limit; do not assume an entire native segment with `byteSize > Integer.MAX_VALUE` can be mapped into a single `ByteBuffer`.

## 13. Common boundary errors and exceptions

| Situation | Common error type | Explanation |
| --- | --- | --- |
| `dest.copyFrom(src)` when dest is smaller than src | `IndexOutOfBoundsException` | Not enough space to hold all source bytes |
| Copy with `srcOffset < 0` or out of bounds | `IndexOutOfBoundsException` | Invalid source range |
| `fill` or copy into a read-only view | `IllegalArgumentException` | Writing to destination is not permitted |
| Operating on a segment after its arena is closed | `IllegalStateException` | Scope is no longer alive |
| Another worker reads/writes a segment from `Arena.ofConfined()` | `WrongThreadException` | Thread confinement violated |
| `toArray(JAVA_INT)` on a 6-byte segment | `IllegalStateException` | Size is not divisible by 4 |
| `toArray` produces too many elements | `IllegalStateException` | Cannot be represented by a valid Java array |
| Typed `MemorySegment.copy` with layouts of different sizes | `IllegalArgumentException` | Requires two layouts with the same element size |
| Copying `double[]` with `JAVA_INT` | `IllegalArgumentException` | Carrier/layout does not match array type |
| Writing `JAVA_INT` into a heap segment backed by `byte[]` with insufficient alignment | `IllegalArgumentException` | Layout/offset incompatible with alignment |
| `mismatch` using range `[from,to)` exceeding byteSize | `IndexOutOfBoundsException` | Region bounds violated |

There may also be errors related to `null`, byte count overflow, native allocation, or environment configuration. Check **size, offset, layout, scope, and read-only** status before calling. Do not catch every `RuntimeException` and ignore it to let the program continue with untrusted data.

### 13.1. Checking before copying from an untrusted source

A typical helper:

```java
static void copyChecked(MemorySegment src,
                        long srcOffset,
                        MemorySegment dst,
                        long dstOffset,
                        long bytes) {
    if (bytes < 0 || srcOffset < 0 || dstOffset < 0
            || srcOffset > src.byteSize() - bytes
            || dstOffset > dst.byteSize() - bytes) {
        throw new IndexOutOfBoundsException("Invalid copy range");
    }
    MemorySegment.copy(src, srcOffset, dst, dstOffset, bytes);
}
```

This is a **method snippet**, which needs to be placed in a class that imports `java.lang.foreign.MemorySegment`. Checking in the form `offset > size - length` helps avoid `offset + length` addition that could overflow. However, this helper **does not replace** FFM's checks: destination could be read-only, or a segment could be dead or confined.

For element-wise copying, use `Math.multiplyExact(elementCount, layout.byteSize())` or compare bounds using careful division to avoid overflow when computing byte sizes.

### 13.2. Do not forget to close the arena

```java
MemorySegment leaked;
try (Arena arena = Arena.ofConfined()) {
    leaked = arena.allocate(8);
}
// Do not use leaked after this point.
```

This snippet illustrates a lifecycle bug: `leaked` is just an object representing the segment, with no guarantee that the backing memory is still valid. The right way is to perform `toArray` **inside the try**, then return an independent Java array to the caller:

```java
static byte[] readResult() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment block = arena.allocate(8);
        block.fill((byte) 5);
        return block.toArray(ValueLayout.JAVA_BYTE);
    }
}
```

This is an **illustrative method**, placed in a class with imports `Arena`, `MemorySegment`, `ValueLayout`. Upon return, the `byte[]` array has already been copied and does not depend on the `arena` closing afterward.

## 14. Performance and API choices

### 14.1. Copy or view?

- `ofArray`/`asSlice`: **view**, usually does not copy content and is suitable when you need to read/write directly on a shared backing; aliasing and thread safety must be controlled.
- `copyFrom`/`copy`: **copy**, has a cost proportional to the amount of data, but separates backing if the target is an independently allocated region.
- `toArray`: **copy + allocate a new Java array**, easy to use but increases GC pressure if called repeatedly with large data.
- `MemorySegment.copy(..., array, ...)`: copies into a **caller-managed Java array**, useful when you want to reuse buffers.

**Do not treat `copy` as zero-copy**, even though FFM internally optimizes bulk copy instructions. Conversely, a view does not mean zero cost: managing scope, alignment, access, and synchronization can still matter.

### 14.2. Prefer bulk operations when appropriate

Instead of calling `get(JAVA_BYTE, i)` and `set(JAVA_BYTE, i)` in a loop millions of times just to transfer raw bytes, prefer `copyFrom` or `MemorySegment.copy` for large ranges. Use `fill` to fill a byte pattern, `mismatch` to find differing bytes, and `toArray` when you truly need an independent Java array.

However, if you need to interpret elements, perform arithmetic, or change structure, you still have to use the right `ValueLayout` and may need a loop or copying by element layout.

### 14.3. Chunking for very large data

A Java `byte[]` has its size limited by `int`, while `MemorySegment.byteSize()` is `long`. For a very large native segment, do not try to call `toArray` for the whole thing if it exceeds the limit. You can process in chunks:

```java
// Illustration when src is a live MemorySegment.
long position = 0L;
final int chunkSize = 64 * 1024;

while (position < src.byteSize()) {
    int count = (int) Math.min(
            (long) chunkSize, src.byteSize() - position);
    byte[] chunk = src.asSlice(position, count)
                      .toArray(ValueLayout.JAVA_BYTE);
    // Send chunk to the Java code that needs to process it, then continue looping.
    position += count;
}
```

This is a **snippet**, without a standalone `src` variable. You need to design the consumer clearly, avoiding accumulating all `chunk`s in RAM if the goal is streaming. Also do not use a segment whose scope has already closed.

### 14.4. Thread safety

`Arena.ofShared()` allows multiple threads to **access** a segment, but **does not automatically provide a protocol to prevent data races** when two threads write/run `fill` or `copy` concurrently on overlapping ranges. Use non-overlapping data partitioning, locks, or appropriate memory ordering. `mismatch` reads bytes at a point in time without an atomic snapshot guarantee if another thread is modifying the same region.

## 15. Before–after scenarios

### A. Receiving a native payload and bringing it back to Java

**Before:** returning a `MemorySegment` from an arena that closes right after the call; Java code using it afterward gets `IllegalStateException`.

**After:** before the arena closes, create `byte[] result = segment.toArray(JAVA_BYTE)` and return the Java array. Accept one copy for simple ownership.

### B. Reusing a native buffer

**Before:** looping byte by byte and writing zero to reset.

**After:** `buffer.fill((byte)0)`, or `buffer.asSlice(headerBytes, payloadBytes).fill((byte)0)` if you only want to reset the payload. Remember this is byte filling, not the value of individual struct fields.

### C. Detecting content corruption during copy

**Before:** comparing the addresses of two segments or using `==` and concluding the contents differ.

**After:** `long firstDiff = expected.mismatch(actual)`. If `-1`, the byte sequences and sizes are equal. If `>= 0`, report the first differing byte offset, and then you can extract a slice for debugging.

### D. Processing a region in the middle of a large record

**Before:** calling `toArray` on the entire 100 MB just to get a 32-byte sub-header.

**After:** `segment.asSlice(headerOffset, 32).toArray(JAVA_BYTE)` or copy directly into an existing `byte[32]`. Ensure bounds are checked.

### E. Writing an `int[]` array into a native buffer

**Before:** taking `values.length=100` and allocating 100 bytes, then copying 100 `int` numbers → wrong size.

**After:** allocate `100 * JAVA_INT.byteSize() = 400` bytes with proper alignment, use typed `MemorySegment.copy(values, 0, native, JAVA_INT, 0, values.length)`; when receiving back, `native.toArray(JAVA_INT)` creates a new int array.

## 16. Self-practice questions

**1. Does `fill((byte)1)` on a segment containing `int[]` fill each `int` with 1?** No. It fills each byte with 01; an `int` consisting of four 01 bytes becomes `0x01010101`.

**2. Does `MemorySegment.ofArray(byte[])` copy data?** No. It creates a heap segment backed by that same array. Modifications through the segment can be observed immediately in the array.

**3. Does `toArray(JAVA_BYTE)` return a view with the same backing?** No. It creates and returns a **new Java byte array** by copying.

**4. What does `left.mismatch(right) == -1` mean?** The two byte sequences compare equal and have the same length. If one side is only a proper prefix of the other, the result is the length of the shorter side, not `-1`.

**5. What are offsets in `MemorySegment.copy` measured in?** Segment offsets are in **bytes**; Java array indices are in **elements**; `elementCount` of typed copy is **number of elements**.

**6. Does `copyFrom` for a destination smaller than the source automatically expand the destination?** No. It fails due to insufficient space.

**7. Does `Arena.ofConfined()` allow another thread to access the native segment?** No. The exact owner thread is required; if truly sharing, consider a shared arena and proper data synchronization.

**8. Can `toArray(JAVA_INT)` be called on a 6-byte segment?** No. The segment must have a length divisible by 4 and a valid element count.

**9. Does `MemorySegment.copy` support overlap between two slices of the same backing?** Yes, with semantics similar to copying via a temporary buffer for recognized overlaps. Do not extrapolate to unusual physical aliasing through different addresses.

**10. When code runs on JDK 17, can the JDK 22 `java.lang.foreign.MemorySegment` examples be copied verbatim?** No. JDK 22+ is required to use the stable FFM API shown here.

## 17. Checklist when using MemorySegment in projects

1. Choose **JDK 22+** for code using stable `java.lang.foreign`; do not mix in old incubator/preview examples.
2. Check **heap view (`ofArray`) vs native allocation (`Arena`)** and data ownership.
3. Do not confuse **`byteSize`/byte offset** with **element count/Java array index**.
4. For `fill`, remember **a single byte value is repeated**, not per-element `int/long` assignment.
5. For `copyFrom`, ensure destination is large enough; for `copy`, check all offsets/lengths and write permissions.
6. For typed copy or `toArray`, use `ValueLayout` with the right type, size, alignment, and endianness.
7. `mismatch` compares **bytes**, returning the first differing **byte offset** or `-1`; also check the case where one region is a prefix.
8. When independent Java data is needed, use `toArray` or copy into an existing array; `asSlice`/`ofArray` are not copies.
9. Close `Arena` at the right time, do not leave segments artificially alive after memory is invalid; avoid passing confined segments across threads.
10. For large data, design **chunking**; avoid allocating huge arrays and redundant copies.
11. For shared memory, have a separate synchronization strategy; copy/fill/mismatch are not atomic transactions by themselves.
12. Test results, boundary cases, endianness, and scope/thread/read-only errors, rather than only benchmarking the happy path.

## Official sources

- [Java SE 22 — `MemorySegment` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `copy`, `copyFrom`, `fill`, `mismatch`, `toArray`, `ofArray`, `asSlice`, and error conditions.
- [Java SE 22 — `Arena` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): native memory allocation, lifetime scope, and confined/shared arenas.
- [Java SE 22 — `ValueLayout` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): primitive carriers, byteSize, byteOrder, and alignment.
- [Oracle — Foreign Function & Memory API Guide (JDK 22)](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): FFM practices, heap/native segments, and memory arenas.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): the FFM API standardized in JDK 22.