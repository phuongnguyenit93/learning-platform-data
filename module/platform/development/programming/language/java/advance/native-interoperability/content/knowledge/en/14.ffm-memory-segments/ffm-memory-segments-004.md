# Distinguishing Byte Offset from Element Index in MemorySegment's getAtIndex and setAtIndex

## 1. The Problem: A Number Can Be a Byte Offset or an Element Index

When working with memory through the **Foreign Function & Memory API (FFM API)**, `MemorySegment` represents **a contiguous region of memory whose size is measured in bytes**. You can access that region using a layout that describes the data type, width, byte order, and alignment requirements. Two groups of methods look quite similar, but **the unit of the position parameter is different**:

- `segment.get(layout, offset)` and `segment.set(layout, offset, value)`: `offset` is the **number of bytes** from the start of the **current segment**.
- `segment.getAtIndex(layout, index)` and `segment.setAtIndex(layout, index, value)`: `index` is the **logical element index**. The JVM multiplies this index by `layout.byteSize()` to derive the byte position.

This is a common source of “reading the wrong element” or “data misalignment” bugs when Java code uses native memory.

**Core formula:**

```text
byteOffset = index × layout.byteSize()

segment.getAtIndex(layout, index)
    corresponds in position to:
segment.get(layout, byteOffset)

segment.setAtIndex(layout, index, value)
    corresponds in position to:
segment.set(layout, byteOffset, value)
```

This correspondence only makes sense when both accesses are valid according to the segment's **size, alignment, lifetime, and access permissions**. An arbitrary multiplication will not bypass the API's safety constraints.

Example with `ValueLayout.JAVA_INT` (a Java `int` value is **4 bytes** wide):

```text
             byte offset in segment
              0         4         8        12        16
              │         │         │         │         │
              ▼         ▼         ▼         ▼         │
            ┌─────────┬─────────┬─────────┬─────────┐  │
            │ int[0]  │ int[1]  │ int[2]  │ int[3]  │  │
            │ 10      │ 20      │ 30      │ 40      │  │
            └─────────┴─────────┴─────────┴─────────┘  │
            index 0   index 1   index 2   index 3       │
                                                        │
                                             byte 16 = end of region
```

In this 16-byte region:

- `getAtIndex(JAVA_INT, 2)` reads `int[2]` at **byte offset 8**, returning `30`.
- `get(JAVA_INT, 8)` also reads that element, returning `30`.
- `get(JAVA_INT, 2)` **does not mean** the 2nd element: it is an `int` access at **byte offset 2**, which may violate 4-byte alignment and throw an exception.
- `getAtIndex(JAVA_INT, 8)` attempts to read at **byte offset 32**; for a 16-byte segment, it will go out of bounds.

Key point: the same number `2` or `8`, but **the unit understood by the API** determines the memory region accessed.

> **API Version:** Examples in this article use `java.lang.foreign.MemorySegment`, `Arena`, and `ValueLayout` from **JDK 22 and later**, when the FFM API became a final standard API. JDK 21 uses a preview API; JDK 17–19 have incubator/preview APIs with different packages or call signatures. Do not copy the examples verbatim into Java 17 and expect them to compile without modifying the API. This article prioritizes code that runs reliably on JDK 22+ rather than forcing the use of older APIs.

## 2. Two Coordinate Systems: Byte Offset and Logical Element Index

### 2.1. Byte Offset: Measuring Distance in Bytes

A `MemorySegment` has a `byteSize()`, for example `16L`. When calling:

```java
int value = segment.get(ValueLayout.JAVA_INT, 8L);
```

The JVM understands:

1. Start from the beginning of the segment.
2. Move **8 bytes**.
3. Read **4 bytes** according to the type, byte order, and alignment of `ValueLayout.JAVA_INT`.
4. Return a Java `int`.

Similarly:

```java
segment.set(ValueLayout.JAVA_INT, 12L, 44);
```

writes an `int` into **bytes 12..15** of the segment. There is no implicit multiplication by `4` for the `12L` argument.

It is necessary to distinguish between **starting position** and **data width**: `offset = 12`, `layout.byteSize() = 4` means the read/write region spans from byte 12 to just before byte 16; the offset itself is not the length being accessed.

### 2.2. Element Index: Counting by the Width of ValueLayout

When calling:

```java
int value = segment.getAtIndex(ValueLayout.JAVA_INT, 2L);
```

The JVM understands:

```text
layout.byteSize() = 4
index             = 2
byte offset       = 2 × 4 = 8
```

The result is the same as `get(JAVA_INT, 8L)` in the same memory state. Similarly, `setAtIndex(JAVA_INT, 3L, 44)` writes to byte offset `12L`.

**Do not manually multiply the index and then pass it to `getAtIndex`:**

```java
long index = 2L;
long byteOffset = Math.multiplyExact(
        index, ValueLayout.JAVA_INT.byteSize());

// CORRECT: the argument is index (2), the JVM multiplies by 4 itself.
int a = segment.getAtIndex(ValueLayout.JAVA_INT, index);

// CORRECT: the argument is the offset already calculated in bytes (8).
int b = segment.get(ValueLayout.JAVA_INT, byteOffset);

// WRONG INTENT: 8 is interpreted as index, the JVM multiplies by 4 again.
// int wrong = segment.getAtIndex(ValueLayout.JAVA_INT, byteOffset);
```

This is an **illustrative fragment**, where `segment` is a `MemorySegment` that is large enough, still alive, and has appropriate alignment; a complete program appears in section 5.

### 2.3. Why Is the Layout in the Calculation?

`getAtIndex` does not have a fixed “element size” for the segment. The same segment can be viewed through many different layouts:

| Layout | `layout.byteSize()` | `getAtIndex(layout, 3)` reads at byte offset |
| --- | ---: | ---: |
| `ValueLayout.JAVA_BYTE` | 1 | 3 |
| `ValueLayout.JAVA_SHORT` | 2 | 6 |
| `ValueLayout.JAVA_INT` | 4 | 12 |
| `ValueLayout.JAVA_FLOAT` | 4 | 12 |
| `ValueLayout.JAVA_LONG` | 8 | 24 |
| `ValueLayout.JAVA_DOUBLE` | 8 | 24 |

The `byteSize()` values above are the values of **Java primitive layouts**. For `ValueLayout.ADDRESS`, the address width may depend on the ABI/platform; do not assume it is always 8 bytes. If using a layout customized with `withOrder` or `withByteAlignment`, **the width must still be obtained from `layout.byteSize()`** instead of hard-coding.

A segment is just a region of bytes; it **does not know on its own** whether you intend to represent `int[]`, `short[]`, a C struct, or a sequence of pixels. The layout is the contract for interpreting those bytes.

## 3. API Comparison Table and Equivalent Scenarios

| Task | Byte-based API | Element-based API |
| --- | --- | --- |
| Read the 0th int | `get(JAVA_INT, 0)` | `getAtIndex(JAVA_INT, 0)` |
| Read the 1st int | `get(JAVA_INT, 4)` | `getAtIndex(JAVA_INT, 1)` |
| Read the 2nd int | `get(JAVA_INT, 8)` | `getAtIndex(JAVA_INT, 2)` |
| Write the 3rd int = 44 | `set(JAVA_INT, 12, 44)` | `setAtIndex(JAVA_INT, 3, 44)` |
| Read the 2nd long | `get(JAVA_LONG, 16)` | `getAtIndex(JAVA_LONG, 2)` |
| Write the 3rd byte | `set(JAVA_BYTE, 3, value)` | `setAtIndex(JAVA_BYTE, 3, value)` |

Full names of the APIs belonging to `MemorySegment`:

```java
// Example overloads for Java int.
int get(ValueLayout.OfInt layout, long offset);
void set(ValueLayout.OfInt layout, long offset, int value);

int getAtIndex(ValueLayout.OfInt layout, long index);
void setAtIndex(ValueLayout.OfInt layout, long index, int value);
```

The four lines above are **signatures for reading and understanding the API**, not declarations to place in your Java program (they are existing methods on `MemorySegment`). `getAtIndex`/`setAtIndex` have similar overloads for `byte`, `short`, `char`, `long`, `float`, `double`, `boolean`, and address layouts.

**An easy trap to fall into:** `getAtIndex(layout, index)` does not accept a base byte offset parameter. When there is a header at the beginning of the segment, you must create a slice from where the header ends, or manually calculate the exact byte offset and call `get`/`set`. Do not use `index + headerBytes` hoping the API understands the header in byte units.

## 4. How to Quickly Choose the API

**Use `getAtIndex`/`setAtIndex` when** the data is a sequence of equal-sized, contiguous elements described by the **same `ValueLayout`**:

```java
for (long index = 0; index < count; index++) {
    segment.setAtIndex(ValueLayout.JAVA_INT, index, (int)index);
}
```

Here `count` is the **number of ints**, not the number of bytes. If the segment has `count * JAVA_INT.byteSize()` bytes and appropriate alignment, each iteration accesses exactly one element.

**Use byte-based `get`/`set` when** the position comes from:

- A field offset in a C struct or file format.
- A header length or offset measured in bytes from a protocol.
- The position of an element in a record that has a **stride different from** `layout.byteSize()`.
- Needing to access a heterogeneous memory region consisting of interleaved `byte`, `int`, and `long` fields.
- A slice whose starting position is determined in bytes.

Example: in a 12-byte-long record, the `int score` field is at byte offset 8 of each record. The score of the 3rd record (index 2) is at byte offset `2 * 12 + 8 = 32`. Calling `getAtIndex(JAVA_INT, 2)` will read offset `8` — **not** byte 32. Section 8/9 will analyze structs and stride in detail.

## 5. Runnable Java 22+ Example: Same Data, Two Ways of Addressing

The following program creates a **16-byte native segment**, stores 4 consecutive `int` values, and then demonstrates how to read/write by index and by byte offset. The example allocates memory itself, requiring no C JNI or external libraries.

### 5.1. File `ByteOffsetVsIndex.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ByteOffsetVsIndex {
    public static void main(String[] args) {
        var intLayout = ValueLayout.JAVA_INT;
        long elementBytes = intLayout.byteSize(); // 4 bytes
        int count = 4;

        try (Arena arena = Arena.ofConfined()) {
            // 4 int elements = 16 bytes; request appropriate alignment.
            MemorySegment segment = arena.allocate(
                    Math.multiplyExact((long) count, elementBytes),
                    intLayout.byteAlignment());

            for (int i = 0; i < count; i++) {
                segment.setAtIndex(intLayout, i, (i + 1) * 10);
            }

            System.out.println("element bytes: " + elementBytes);
            System.out.println("segment bytes: " + segment.byteSize());

            // Two paths accessing the same element int[1].
            System.out.println(
                    "index 1: " + segment.getAtIndex(intLayout, 1));
            System.out.println(
                    "byte 4: " + segment.get(intLayout, 4));

            // Two paths accessing the same element int[2].
            System.out.println(
                    "index 2: " + segment.getAtIndex(intLayout, 2));
            System.out.println(
                    "byte 8: " + segment.get(intLayout, 8));

            // setAtIndex multiplies index=2 by 4 bytes automatically.
            segment.setAtIndex(intLayout, 2, 99);
            System.out.println(
                    "after setAtIndex(2): " + segment.get(intLayout, 8));

            // set takes a byte position, not a logical index.
            segment.set(intLayout, 12, 44);
            System.out.println(
                    "after set(byte 12): " +
                    segment.getAtIndex(intLayout, 3));

            // Slice has its own coordinate system, starting from byte 4.
            MemorySegment slice = segment.asSlice(4, 8);
            System.out.println(
                    "slice index 0: " + slice.getAtIndex(intLayout, 0));
            System.out.println(
                    "slice index 1: " + slice.getAtIndex(intLayout, 1));

            // 16 bytes is only enough for 4 ints (index 0..3).
            try {
                segment.getAtIndex(intLayout, 4);
            } catch (IndexOutOfBoundsException ex) {
                System.out.println("index 4: out of bounds");
            }

            // Native segment is allocated 4-byte aligned;
            // offset 3 does not satisfy 4-byte alignment.
            try {
                segment.get(intLayout, 3);
            } catch (IllegalArgumentException ex) {
                System.out.println("byte 3: misaligned");
            }
        }
    }
}
```

**This file is a standalone Java program.** `Arena.ofConfined()` only allows the thread owning the arena to access the segment; the entire program runs in a single thread. `try-with-resources` closes the arena upon exiting the block, freeing the native memory.

Commands with **JDK 22 or newer**:

```bash
javac ByteOffsetVsIndex.java
java ByteOffsetVsIndex
```

No `--enable-preview` is needed for the standard FFM API starting from JDK 22. Pure `MemorySegment`/`Arena`/`ValueLayout` operations in this example also do not require calling a restricted native linker or loading a JNI library.

**Expected stdout:**

```text
element bytes: 4
segment bytes: 16
index 1: 20
byte 4: 20
index 2: 30
byte 8: 30
after setAtIndex(2): 99
after set(byte 12): 44
slice index 0: 20
slice index 1: 99
index 4: out of bounds
byte 3: misaligned
```

### 5.2. Output Explanation

- `intLayout.byteSize()` returns `4`, `segment.byteSize()` returns `16`.
- `getAtIndex(intLayout, 1)` → byte offset `4`. Same result as `get(intLayout, 4)`.
- `getAtIndex(intLayout, 2)` → byte offset `8`. Same result as `get(intLayout, 8)`.
- `setAtIndex(intLayout, 2, 99)` writes to bytes 8..11; `get(intLayout, 8)` reads back `99`.
- `set(intLayout, 12, 44)` writes to bytes 12..15; `getAtIndex(intLayout, 3)` reads back `44`.
- `asSlice(4, 8)` creates an 8-byte view starting from byte offset 4 of the original segment. In the slice, **index 0** is the 1st int of the original segment (`20`), and **index 1** is the 2nd int after modification (`99`).
- `getAtIndex(intLayout, 4)` corresponds to byte offset 16 and needs 4 more bytes to read; the 16-byte region is not enough, so `IndexOutOfBoundsException` occurs.
- `get(intLayout, 3)` is within bounds if only checking 3+4 ≤ 16, but is **not properly aligned** for `JAVA_INT` at offset 3; the access is rejected with `IllegalArgumentException`.

The example uses `JAVA_INT` to avoid endianness dependency in stdout: values are **written and read back with the same layout**. If the layout byte order is changed between writing and reading, the value may differ (section 10).

## 6. Bounds Checking: byteSize Is Not the Element Count

`segment.byteSize()` returns the number of **bytes**, not the number of `int`, `long`, or records in the segment.

If a segment contains **N** uniform elements, each **S** bytes wide, the minimum total capacity is:

```text
requiredBytes = N × S
validIndices  = 0, 1, 2, ..., N - 1
elementOffset = index × S
```

With 4-byte `JAVA_INT` and `segment.byteSize() == 16`, there are only **4 whole elements**, valid indices `0..3`.

If the segment is 18 bytes and each element is 4 bytes, the segment can hold **4 whole elements**, with 2 bytes remaining. Do not round up to 5 elements to read/write the 5th `int`.

### 6.1. Conditions for Byte-Based Access

For `get(layout, offset)` or `set(layout, offset, value)`, when `layout.byteSize() = S` and `segment.byteSize() = B`, the following must hold:

```text
0 <= offset
offset + S <= B
```

In other words, an access starting at offset `B - S` is the **last possible point** to read/write an element of width `S` bytes. In manual checks, use `offset <= B - S` after ensuring the numbers are non-negative to avoid overflow in addition.

If using `getAtIndex(layout, index)`:

```text
0 <= index
index * S + S <= B
```

The API checks the multiplication and bounds. If `index * S` overflows `long`, the javadoc specifies `IndexOutOfBoundsException` rather than allowing wrap-around to an unsafe address.

### 6.2. A Helper to Convert Index to Byte Offset

When code needs to convert units to coordinate with a field offset or protocol, allow catching multiplication overflow errors:

```java
static long toByteOffset(long index, long elementBytes) {
    if (index < 0 || elementBytes <= 0) {
        throw new IllegalArgumentException(
                "index must be non-negative and size positive");
    }
    return Math.multiplyExact(index, elementBytes);
}
```

This is a **static method fragment** (not a standalone program). `Math.multiplyExact` throws `ArithmeticException` if the result exceeds the `long` limit; after computing, you must still check that there are enough bytes from the offset to the end of the segment. `getAtIndex` has its own overflow/bounds checks, but **does not replace** the application's element/record count validation logic.

You can get the number of **whole** elements with:

```java
long wholeElements = segment.byteSize() / intLayout.byteSize();
```

The statement above assumes `segment` and `intLayout` are already declared. When the data has a header, padding, or a stride different from `layout.byteSize()`, division is only a theoretical count according to the layout, **not automatic proof that it is the business record count**.

## 7. Alignment: A Valid Index Is Not Enough to Access

**Alignment** is a constraint on the starting address of the read/write region, measured in bytes, not element count. `ValueLayout.JAVA_INT` has:

```text
byteSize()      = 4
byteAlignment() = 4
```

With a native memory segment whose starting address is 4-byte aligned:

- `get(JAVA_INT, 0)` is valid in terms of alignment.
- `get(JAVA_INT, 4)`, `get(JAVA_INT, 8)` are also valid.
- `get(JAVA_INT, 3)` is **not** 4-byte aligned.
- `getAtIndex(JAVA_INT, 1)` uses byte offset 4, so it is properly aligned.

Creating a memory region with sufficient alignment:

```java
try (Arena arena = Arena.ofConfined()) {
    var i32 = ValueLayout.JAVA_INT;
    MemorySegment ints =
            arena.allocate(4L * i32.byteSize(),
                           i32.byteAlignment());
    ints.setAtIndex(i32, 0, 123);
}
```

This is a **Java fragment runnable in a method context**. Calling `Arena.allocate(byteSize, byteAlignment)` guarantees the allocated address satisfies the layout's alignment requirement; allocating only `4 * 4` bytes without considering alignment may not be sufficient if you are reading a memory region **not belonging to the arena** with different address constraints.

### 7.1. Unaligned Layouts Do Not Change the Meaning of Index

`ValueLayout.JAVA_INT_UNALIGNED` is a layout that reads/writes a 4-byte `int` but only requires 1-byte alignment:

```java
var unaligned = ValueLayout.JAVA_INT_UNALIGNED;

// Position is still measured in BYTES:
int a = segment.get(unaligned, 3);

// getAtIndex still multiplies by 4 automatically:
int b = segment.getAtIndex(unaligned, 3); // Byte offset 12
```

This is a **fragment**, assuming the segment is large enough, still alive, and not restricted in permissions. The two statements access two different positions, **even when alignment is relaxed**. Do not equate “unaligned” with “index is a byte offset”.

A common example is `MemorySegment.ofArray(new byte[16])`: a heap segment from `byte[]` has a maximum alignment of 1 byte. Therefore, using the `JAVA_INT` layout (alignment 4) on it may be rejected **even at byte offset 0**. If the data actually resides in a `byte[]` and an `int` must be read, use `JAVA_INT_UNALIGNED` and the right byte order to read, or choose a segment backed by a different array type with appropriate alignment. **Relaxing alignment should be based on the format/ABI and performance/portability considerations**, not used as a fix for every memory error.

### 7.2. Alignment Greater Than byteSize: A Special Case of AtIndex

Javadoc states `getAtIndex`/`setAtIndex` may throw `IllegalArgumentException` if:

```text
layout.byteAlignment() > layout.byteSize()
```

For example, a layout describing a 4-byte `int` but requiring 8-byte alignment has `byteAlignment = 8 > byteSize = 4`. `AtIndex` uses a stride of 4, so it is **not an appropriate choice** for elements spaced 8 bytes apart. You need to handle the stride using **byte offsets** and call `get(layout, byteOffset)`/`set(layout, byteOffset, value)` on a segment with sufficient alignment.

Note: `withByteAlignment` does not increase `byteSize()`. This is an important difference between **data width**, **alignment requirement**, and **stride** between records.

## 8. Header, Slice, and Base Offset: Coordinates Relative to Which Segment?

`getAtIndex` always computes the index from **the start of the segment on which you call the method**. It does not know how many bytes after a header the actual data begins.

Suppose a protocol has an 8-byte header, followed by 3 Java `int` values (12 bytes). Total `20 bytes`:

```text
Base segment (20 bytes):
offset 0..7  = header
offset 8..11 = value[0]
offset 12..15= value[1]
offset 16..19= value[2]
```

If you call `base.getAtIndex(JAVA_INT, 1)`, the API reads **byte offset 4**, which is still inside the header, not `value[1]`.

There are two correct ways:

**Method A — Compute the offset in bytes:**

```java
long headerBytes = 8;
long index = 1;
long offset = Math.addExact(
        headerBytes,
        Math.multiplyExact(index, ValueLayout.JAVA_INT.byteSize()));

int value = base.get(ValueLayout.JAVA_INT, offset); // offset = 12
```

**Method B — Create a slice after the header, then use index:**

```java
MemorySegment values = base.asSlice(8, 12);

int value = values.getAtIndex(ValueLayout.JAVA_INT, 1);
// index 1 in slice -> byte offset 4 in slice
// i.e., byte offset 12 in base.
```

Both are **fragments**, assuming `base` has been allocated with at least 20 bytes and appropriate address/access alignment. `asSlice(offset, length)` uses **byte** units for both `offset` and `length`. A slice does not copy data; it creates a **view** into the same memory region. Therefore, writing through the slice is reflected on the base, and vice versa, within the lifetime limits of the segment.

After slicing:

- `slice.byteSize()` is **12 bytes**, not 20.
- `slice.getAtIndex(JAVA_INT, 0)` corresponds to `base.get(JAVA_INT, 8)`.
- `slice.getAtIndex(JAVA_INT, 1)` corresponds to `base.get(JAVA_INT, 12)`.
- `slice.getAtIndex(JAVA_INT, 3)` exceeds the 12-byte bounds of the slice.

**Do not take a global byte offset and pass it to `getAtIndex` on a slice.** The coordinate system has changed: the offset must be relative to the **target segment**, and the index is further scaled by the layout from the start of that target segment.

### 8.1. Slicing Can Cause Alignment Errors

If the base is 4-byte aligned, but the slice starts at **byte offset 1**, the starting address of the slice is shifted by 1 byte from 4-byte alignment. Then `slice.getAtIndex(JAVA_INT, 0)` may be invalid in terms of alignment, even though index is 0 and `byteSize` is sufficient.

An intentional way to access byte-misaligned data is to use `JAVA_INT_UNALIGNED` *if the format truly permits it*; whereas for structs designed to be aligned, the right solution is usually to adjust the field position or layout rather than removing the alignment constraint.

## 9. When Data Is a Struct/Record: Record Index Differs from Primitive Index

`getAtIndex(ValueLayout.JAVA_INT, i)` always computes `i * 4`. But in an array of C records, each record may contain **multiple fields and padding**:

```text
struct Example { int id; int score; }   // illustrating two 4-byte ints
record[0]  bytes 0..7:  id at 0, score at 4
record[1]  bytes 8..15: id at 8, score at 12
record[2]  bytes 16..23: id at 16, score at 20
```

For a two-`int` struct with a known 8-byte layout and no padding:

```text
recordStride   = 8 bytes
scoreOffset    = 4 bytes
score[2]       = 2 * 8 + 4 = 20 bytes

getAtIndex(JAVA_INT, 2)
  = byte offset 8   (id of record[1])
  NOT score of record[2].
```

To read a field of the `i`-th record, the correct formula is:

```text
recordBase = i * recordLayout.byteSize()
fieldByteOffset = recordLayout.byteOffset(pathToField)
absoluteOffset = recordBase + fieldByteOffset

segment.get(fieldValueLayout, absoluteOffset)
```

**Standalone Java 22+ code** clearly demonstrating the difference:

### 9.1. File `StructStrideDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class StructStrideDemo {
    public static void main(String[] args) {
        var intLayout = ValueLayout.JAVA_INT;

        var recordLayout = MemoryLayout.structLayout(
                intLayout.withName("id"),
                intLayout.withName("score"));

        long stride = recordLayout.byteSize(); // 8
        long scoreOffset = recordLayout.byteOffset(
                MemoryLayout.PathElement.groupElement("score")); // 4

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment records = arena.allocate(
                    Math.multiplyExact(3L, stride),
                    recordLayout.byteAlignment());

            for (int i = 0; i < 3; i++) {
                long recordBase = Math.multiplyExact((long)i, stride);
                records.set(intLayout, recordBase, 100 + i);
                records.set(intLayout, recordBase + scoreOffset, 900 + i);
            }

            // index=2 here is a primitive-int index -> byte 8.
            System.out.println(
                    "wrong record interpretation: " +
                    records.getAtIndex(intLayout, 2));

            // Correct: score of record[2] -> byte 2*8+4=20.
            long scoreByteOffset = 2L * stride + scoreOffset;
            System.out.println(
                    "score of record 2: " +
                    records.get(intLayout, scoreByteOffset));

            System.out.println("record stride: " + stride);
            System.out.println("score byte offset: " + scoreByteOffset);
        }
    }
}
```

Commands:

```bash
javac StructStrideDemo.java
java StructStrideDemo
```

**Expected stdout:**

```text
wrong record interpretation: 101
score of record 2: 902
record stride: 8
score byte offset: 20
```

Because record 1 starts at byte 8, `getAtIndex(JAVA_INT, 2)` reads `id = 101` of record 1, not `score = 902` of record 2. This is a logic bug that **does not necessarily throw an exception**: the access may still be within bounds and properly aligned, yet return the **wrong valid data**.

The struct above uses exactly two adjacent Java `int`s to keep the example simple. When mapping a real C struct, you must consider the **ABI**, padding between fields, total size, alignment, and actual C types. Do not deduce `sizeof(struct)` simply by manually summing field sizes if the ABI has padding. Describe it accurately using `MemoryLayout.structLayout` and `MemoryLayout.paddingLayout` when needed, or use a layout agreed upon by both native and Java code.

### 9.2. An Array-of-Structs Does Not Mean a Contiguous Sequence of Business Ints

A way to avoid confusion is to use:

- `recordLayout.byteSize()` to compute the **stride between records**.
- `recordLayout.byteOffset(...)` to find the **offset of a field within a record**.
- `segment.get(fieldLayout, absoluteByteOffset)` to read a field by **byte**.
- `segment.getAtIndex(primitiveLayout, i)` **only when** the data is truly a contiguous sequence of primitives spaced by `primitiveLayout.byteSize()`.

If a record has an `int value` field every 16 bytes, `getAtIndex(JAVA_INT, i)` does not represent record index `i`; you must use `base + i * 16 + valueFieldOffset`. Any offset multiplication/addition from external data must be checked for overflow and bounds.

## 10. Byte Order Is a Different Issue from Offset

**Byte order (endianness)** determines how 4 bytes are assembled into an `int`; **offset/index** determines which byte to start from. These are two independent axes.

`ValueLayout.JAVA_INT` uses `ByteOrder.nativeOrder()`. If a file/protocol requires **big-endian** or **little-endian**, create the corresponding layout:

```java
import java.nio.ByteOrder;

// Fragments:
var big = ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
var little = ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);

// Both are still 4 bytes wide and getAtIndex(..., 2)
// both start at byte offset 8.
int x = segment.getAtIndex(big, 2);
int y = segment.getAtIndex(little, 2);
```

This is a **fragment**, requiring the `segment` variable and `ValueLayout` import in a real program. `x` and `y` may differ because of different byte order interpretation, but the starting position is still byte offset `2 × 4 = 8`.

**Do not use changing endianness to fix a position offset bug.** If you read the wrong field due to confusing record stride or header bytes, changing `withOrder` only transforms values from the wrong bytes; it does not fix the offset.

## 11. Exceptions and Safety Checks

Common errors in FFM access:

| Scenario | Common symptom | Cause and handling |
| --- | --- | --- |
| `getAtIndex(JAVA_INT, 4)` on 16 bytes | `IndexOutOfBoundsException` | Index 4 corresponds to byte 16, no 4 bytes left to read |
| `get(JAVA_INT, -4)` | `IndexOutOfBoundsException` | Negative byte offset |
| `getAtIndex(JAVA_INT, -1)` | `IndexOutOfBoundsException` | Negative element index |
| Index × layout size overflows `long` | `IndexOutOfBoundsException` | API checks overflow; do not compute manually with unchecked multiplication |
| `get(JAVA_INT, 3)` on 4-byte aligned segment | `IllegalArgumentException` | Byte position does not satisfy alignment |
| `getAtIndex` with `layout.byteAlignment() > layout.byteSize()` | `IllegalArgumentException` | AtIndex does not match the layout's stride/alignment |
| `set` on read-only segment | `IllegalArgumentException` | Segment does not allow writing |
| Using segment from a closed arena | `IllegalStateException` | Backing memory lifetime has ended |
| Accessing confined segment from another thread | `WrongThreadException` | Segment is not accessible from the current thread |
| Reading within bounds but wrong value | Possibly **no exception** | Confusing byte offset, index, struct stride, endianness, or field layout |

Javadoc defines specific exceptions per overload and segment state. If multiple constraints are violated simultaneously, do not write code that depends on the VM's check order, such as an access that is both out of bounds and misaligned. Validate **both bounds and alignment** thoroughly according to the data format.

### 11.1. Segment Liveness Is a Condition Independent of Index

`Arena` manages the lifetime of native segments. Example:

```java
MemorySegment segment;
try (Arena arena = Arena.ofConfined()) {
    segment = arena.allocate(
            ValueLayout.JAVA_INT.byteSize(),
            ValueLayout.JAVA_INT.byteAlignment());
    segment.setAtIndex(ValueLayout.JAVA_INT, 0, 7);
}

// Wrong: arena is closed, native memory region is no longer valid.
// int value = segment.getAtIndex(ValueLayout.JAVA_INT, 0);
```

This is a **fragment**; do not use `segment` after `arena.close()`. Index `0` is still theoretically within range, but the lifetime is no longer valid: a call may throw `IllegalStateException`. Having valid bounds does not allow using a closed memory region.

### 11.2. Do Heap Segments and Native Segments Have Different Units?

No. Both use byte offsets for `get`/`set` and layout-scaled element indices for `getAtIndex`/`setAtIndex`.

Example with a Java `int[]` array:

```java
MemorySegment heap = MemorySegment.ofArray(
        new int[] {10, 20, 30});

System.out.println(
        heap.getAtIndex(ValueLayout.JAVA_INT, 1)); // 20

System.out.println(
        heap.get(ValueLayout.JAVA_INT, 4)); // 20
```

This is a **fragment** with `MemorySegment` and `ValueLayout` imported. It uses a heap segment backed by `int[]`, which has sufficient alignment for `JAVA_INT`. Do not infer from this example that `MemorySegment.ofArray(new byte[12])` also supports `JAVA_INT` alignment of 4; the maximum alignment of a heap segment depends on the primitive array type.

## 12. Common Real-World Mistakes and How to Fix Them

### Mistake 1 — Passing an element index to a byte-offset API

```java
long elementIndex = 3;

// WRONG INTENT: 3 is a byte offset, not the 3rd index.
// int result = segment.get(ValueLayout.JAVA_INT, elementIndex);

// CORRECT:
int result = segment.getAtIndex(ValueLayout.JAVA_INT, elementIndex);
```

With a 4-byte layout, offset 3 is usually misaligned. If an unaligned layout is used, the bug may **go undetected** and return wrong data.

### Mistake 2 — Multiplying by 4 and passing to getAtIndex

```java
long elementIndex = 3;
long byteOffset = elementIndex * ValueLayout.JAVA_INT.byteSize();

// WRONG: passing byteOffset=12 as element index → accesses byte 48.
// int wrong = segment.getAtIndex(ValueLayout.JAVA_INT, byteOffset);

// CORRECT: each API receives the right unit.
int a = segment.getAtIndex(ValueLayout.JAVA_INT, elementIndex);
int b = segment.get(ValueLayout.JAVA_INT, byteOffset);
```

### Mistake 3 — Using segment.byteSize as the element count

```java
long byteCount = segment.byteSize();
long elementCount = byteCount / ValueLayout.JAVA_INT.byteSize();

// WRONG: looping i < byteCount for getAtIndex(JAVA_INT,i).
// CORRECT when data is a contiguous sequence of ints:
for (long i = 0; i < elementCount; i++) {
    int value = segment.getAtIndex(ValueLayout.JAVA_INT, i);
    // ... process value ...
}
```

This is a **fragment**; if the segment contains a header or trailing bytes, you must subtract the data range and/or create a slice before counting.

### Mistake 4 — Confusing struct index with field index

In `struct { int id; int score; }` (8 bytes), record index 2 needs byte offset `16` for `id` and `20` for `score`, not `getAtIndex(JAVA_INT, 2)` or `getAtIndex(JAVA_INT, 5)` by an arbitrary “field position” if the layout has padding. Obtain the stride and field offset from the actual layout.

### Mistake 5 — Ignoring byte order or alignment of native data

The FFM API checks alignment/bounds, but **does not know** whether your file protocol/C ABI is correct. Verify the standard layout of external data, use `withOrder` when needed, and ensure field offsets are accurate.

### Mistake 6 — Using a layout of the wrong size

If a segment contains 4 `short` elements (each 2 bytes), `getAtIndex(JAVA_INT, 1)` starts at byte 4 and reads 4 bytes, i.e., combining two `short`s; that is a completely different interpretation. `getAtIndex` does not infer the real data type from memory. The layout must accurately reflect the data contract.

## 13. API Design Patterns to Avoid Unit Confusion

One way to reduce bugs is to **include the unit in variable names**:

```java
long elementIndex = 3;
long elementByteSize = ValueLayout.JAVA_INT.byteSize();
long byteOffset = Math.multiplyExact(
        elementIndex, elementByteSize);

int valueByIndex = segment.getAtIndex(
        ValueLayout.JAVA_INT, elementIndex);
int valueByBytes = segment.get(
        ValueLayout.JAVA_INT, byteOffset);
```

Prefer:

- `byteOffset`, `headerBytes`, `recordStrideBytes` for all **byte** values.
- `elementIndex`, `recordIndex`, `elementCount` for all **index / element count** values.
- `layout.byteSize()` instead of writing `4` or `8` directly throughout the code.
- `Math.multiplyExact`/`Math.addExact` if manual offset calculation from large inputs is needed.
- `asSlice(headerBytes, payloadByteCount)` to remove the header from the coordinate system before using `getAtIndex`.
- Testing **at least three positions**: index 0, the last valid index, and the first out-of-bounds index.

When building an API wrapper, you can keep a `getElement(long elementIndex)` method externally and only convert at the lower layer. Avoid an ambiguous variable named `offset` that is sometimes used as bytes and sometimes as an index.

## 14. Self-Check Questions (with Answers)

**Question 1.** A 32-byte-long segment contains `long`s, each `long` is 8 bytes. What byte offset does `getAtIndex(JAVA_LONG, 2)` use?  
**Answer:** `2 × 8 = 16` bytes. Equivalent to `get(JAVA_LONG, 16)` if alignment/lifetime are valid.

**Question 2.** Does `set(JAVA_INT, 2, 99)` mean writing element `int[2]`?  
**Answer:** No. It requests writing an `int` starting at **byte offset 2**, which is usually misaligned. To write element at index 2, use `setAtIndex(JAVA_INT, 2, 99)` or `set(JAVA_INT, 8, 99)`.

**Question 3.** Does `getAtIndex(JAVA_INT, 8)` read the 8th byte?  
**Answer:** No. It reads an `int` starting at byte `8 × 4 = 32` of the segment.

**Question 4.** An 18-byte segment stores contiguous `int`s. How many complete `int`s can be read?  
**Answer:** `⌊18/4⌋ = 4`, indices `0..3`, with 2 bytes left over. Alignment/lifetime must also be ensured.

**Question 5.** At which byte of `base` does `base.asSlice(8, 12).getAtIndex(JAVA_INT, 1)` start reading?  
**Answer:** Byte `8 + 1 × 4 = 12` of `base`. The argument `1` is the index counted from the start of the slice.

**Question 6.** If a layout has `byteSize = 4` but `byteAlignment = 8`, does `getAtIndex` always use stride 8?  
**Answer:** No. Index scaling still follows `byteSize = 4`, and the API may throw `IllegalArgumentException` because `byteAlignment > byteSize`. For data spaced 8 bytes apart, compute byte offsets and use `get`/`set`.

**Question 7.** A record has a 24-byte stride, and the `price` field starts after 16 bytes. Where is `price` of record index 3 located?  
**Answer:** `3 × 24 + 16 = 88` bytes from the start of the record table (if there is no header). Do not use `getAtIndex(JAVA_LONG, 3)` if `price` is 8 bytes, because it only reads from byte `24`.

**Question 8.** If two calls have the same byte offset but use `JAVA_INT` and `JAVA_INT.withOrder(BIG_ENDIAN)`, are the results guaranteed to be equal?  
**Answer:** No, the data bytes are interpreted according to different byte orders. Byte offset/index determines **position**, while layout determines **interpretation**.

**Question 9.** The byte offset is valid, but the arena is closed: can it still be read?  
**Answer:** No. `MemorySegment` is also constrained by lifetime, thread accessibility, and read/write permissions, not just bounds.

## 15. Quick Conclusion

- **`get(layout, offset)` / `set(layout, offset, value)`:** the position parameter is a **byte offset**.
- **`getAtIndex(layout, index)` / `setAtIndex(layout, index, value)`:** the position parameter is a **logical element index**, and the JVM multiplies by `layout.byteSize()` automatically.
- **`byteOffset = index × layout.byteSize()`**, but **do not multiply twice** and do not treat `segment.byteSize()` as the element count.
- **`asSlice` takes byte offsets and creates a new coordinate system**; indices in the slice are counted from the start of the slice.
- **Structs/records have their own stride and field offsets**; `getAtIndex(JAVA_INT, recordIndex)` does not understand the record structure automatically.
- **Bounds, alignment, byte order, lifetime, and access permissions** are independent rules; a mathematically valid position can still be invalid or read wrong data.
- **The FFM API in `java.lang.foreign` is a final standard API starting from JDK 22**; use JDK 22+ to compile/run the examples in this article.

### Official Documentation

- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `get`/`set`/`getAtIndex`/`setAtIndex` signatures, index scaling formula, bounds, alignment, and lifetime rules.
- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): `byteSize()`, `byteAlignment()`, `withOrder`, `JAVA_INT`/`JAVA_INT_UNALIGNED`.
- [Oracle Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html): how to allocate native segments using `Arena` and how to access layouts by element.
- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): `byteOffset`, group/sequence layouts, and layout paths for structs.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): finalized API in JDK 22, FFM scope, and rationale for replacing legacy native-memory mechanisms.
