# Allocating Memory and Reading/Writing by ValueLayout and Byte Offset

> **Topic:** Java Advance → Native Interoperability → MemorySegment. This lesson guides you on how to create a memory region using the Foreign Function & Memory API (FFM), read/write Java values via `ValueLayout` at a specific **byte offset**, and explains endianness, alignment, memory bounds, and the `Arena` lifecycle. Examples use **JDK 22+**, because the FFM API became a standard feature in Java 22 (JEP 454). Java 17 does not have the stable `java.lang.foreign` API used here.

## 1. Understanding the Three Components Correctly: Memory Region, Layout, Byte Offset

In regular Java, `int[]` manages `int` elements. When interacting with C/C++, native libraries, a memory-mapped file region, or a binary protocol, we often have to work with **contiguous bytes** and know exactly where each field starts.

FFM divides responsibilities into three concepts:

1. **`MemorySegment`**: a safe, bounds-checked *view* over a contiguous memory region. It knows how many bytes long the region is (`byteSize()`), whether it is still valid, and which thread is allowed to access it. The memory region can reside off-heap or be backed by a Java array.
2. **`ValueLayout`**: describes how many bytes a single value occupies, alignment requirements, byte order (endianness), and the Java data type when reading/writing; for example, `JAVA_INT` is a four-byte `int` value.
3. **`long offset`** in `segment.get(layout, offset)` and `segment.set(layout, offset, value)`: **the number of bytes from the start of the segment**, starting at 0; this is not an `int[]` element index.

Overview diagram:

```text
Arena (manages lifetime, allocation)
  |
  +-- allocate(24, 8) --> 24-byte MemorySegment
                           byte offset:
                           0   1   2   3   4   5   6   7
                           +---+---+---+---+---+---+---+---+ ...
                           |       int #1  |       int #2  |
                           +---+---+---+---+---+---+---+---+ ...
                           |               |
                     get(JAVA_INT, 0)  get(JAVA_INT, 4)

ValueLayout.JAVA_INT: size=4 bytes, typical alignment=4 bytes
                  ^
                  | used to interpret 4 bytes starting at the chosen offset
```

**Key point:** `ValueLayout` **does not hold data**; it only describes how to access it. `MemorySegment` **does not inherently know** whether the bytes at offset 8 are a `long`, an `int`, or UTF-8; the caller decides via the layout. The same four bytes can yield different results if you change the type, byte order, or offset.

## 2. Quick Start: Creating a Segment and Reading/Writing Two Integers

Java 22+ program:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class FirstSegment {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(8, 4);

            // 8 bytes, each int is 4 bytes long.
            segment.set(ValueLayout.JAVA_INT, 0, 100);
            segment.set(ValueLayout.JAVA_INT, 4, 200);

            System.out.println("size = " + segment.byteSize());
            System.out.println("first = " +
                    segment.get(ValueLayout.JAVA_INT, 0));
            System.out.println("second = " +
                    segment.get(ValueLayout.JAVA_INT, 4));
        } // Arena closes, native memory region is freed.
    }
}
```

Save as **`FirstSegment.java`** and run:

```bash
javac FirstSegment.java
java FirstSegment
```

**stdout:**

```text
size = 8
first = 100
second = 200
```

This is a complete program using JDK 22+'s `java.lang.foreign`; **no C compiler, JNI library, or `--enable-preview` is required**. The example only performs native memory allocation and Java memory access, without performing a *restricted downcall*. For other FFM operations (especially native linker/restricted APIs), native access permission may be required depending on the JDK version.

Why are the offsets 0 and 4? A Java `int` is **32 bits = 4 bytes**. `set(JAVA_INT, 0, 100)` writes four bytes at `[0,4)`; `set(JAVA_INT, 4, 200)` writes four bytes at `[4,8)`. Using offset 1 or 5 with the standard `JAVA_INT` layout can also violate alignment requirements.

## 3. Arena Allocating Native Memory: Size, Alignment, and Lifetime

### `Arena.ofConfined()` and `allocate`

`Arena` is the object that manages the lifecycle and allocation of **off-heap/native memory**. Basic usage:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment bytes = arena.allocate(24, 8);
    // byteSize = 24; starting address has 8-byte alignment.
}
```

This is an **illustrative snippet**, assuming `import java.lang.foreign.*;`. Both parameters of `allocate(24, 8)` are in **bytes**:

- `24`: allocates **24 bytes** that can be read/written in the segment.
- `8`: requires the starting address to be aligned to an **8-byte multiple**.
- Size is not an element count; `arena.allocate(6, 4)` does **not** automatically allocate six `int`s.
- `byteAlignment` must be a **positive power of two**. Size must not be negative; invalid arguments throw `IllegalArgumentException`.
- The contents of newly allocated native segments via built-in arenas are **zero-initialized**. However, it is still good practice to write the values for every field required by the contract, avoiding reliance on padding bytes or future assumptions in other contexts.

Two common ways:

```java
// Allocate by size and alignment in bytes.
MemorySegment raw = arena.allocate(16, 8);

// Allocate by a layout: size/alignment taken from the layout.
MemorySegment oneLong = arena.allocate(ValueLayout.JAVA_LONG);

// Allocate for 10 elements, each following the int layout.
MemorySegment tenInts = arena.allocate(ValueLayout.JAVA_INT, 10);
```

This is an illustrative snippet **inside a scope where `arena` is alive**. `arena.allocate(ValueLayout.JAVA_INT, 10)` guarantees enough space for 10 `int` values with the corresponding alignment; you should not manually write `10 * 4` when you already have a layout and want to use the API according to the data representation.

### Scope Managing Access After `close()`

`Arena.ofConfined()` allows accessing allocated segments only on the **thread that created the Arena**. When `try-with-resources` ends, the arena is closed; all segments and slices based on that allocation **become invalid**. Calling `get/set` after closing throws `IllegalStateException` instead of becoming a C pointer that can be used arbitrarily.

Arena types to know:

| Arena | Manually closed? | Which threads can access? | Suitable for |
|---|---|---|---|
| `Arena.ofConfined()` | Yes; owner thread closes | Owner thread only | Linear code, single-threaded access, small experiments |
| `Arena.ofShared()` | Yes | Multiple threads, with proper synchronization | Shared native buffers with a clear lifecycle |
| `Arena.ofAuto()` | No | Multiple threads; GC manages lifetime | When deterministic deallocation is not needed |
| `Arena.global()` | No | Multiple threads; lives very long | Data that truly needs process/JVM-wide lifetime; avoid overuse |

**Not synonymous:** a shared arena allows multiple threads to **access a segment**, but it does **not** automatically make read-write operations atomic or algorithmically thread-safe. Additional synchronization is needed when there is concurrent mutation. Global/auto arenas are not default replacements for `try-with-resources` because reclamation timing is hard to control.

## 4. ValueLayout Describes Value, Size, Byte Order, and Alignment

Some built-in layouts in `java.lang.foreign.ValueLayout`:

| Java Layout | `get` return type / `set` parameter | Byte size | Notes |
|---|---|---:|---|
| `ValueLayout.JAVA_BYTE` | `byte` | 1 | No byte order issue |
| `ValueLayout.JAVA_BOOLEAN` | `boolean` | 1 | Do not automatically assume it matches C `bool` in every ABI |
| `ValueLayout.JAVA_CHAR` | `char` | 2 | UTF-16 code unit; not a UTF-8 byte |
| `ValueLayout.JAVA_SHORT` | `short` | 2 | 16-bit signed integer |
| `ValueLayout.JAVA_INT` | `int` | 4 | 32-bit signed integer |
| `ValueLayout.JAVA_LONG` | `long` | 8 | 64-bit signed integer |
| `ValueLayout.JAVA_FLOAT` | `float` | 4 | Floating-point |
| `ValueLayout.JAVA_DOUBLE` | `double` | 8 | Floating-point |
| `ValueLayout.ADDRESS` | `MemorySegment` (address) | Platform-dependent | Used for native pointers; not a regular byte integer |

Layouts can be immutably customized (returning a **new** layout) using:

- `layout.withOrder(ByteOrder.LITTLE_ENDIAN)` or `withOrder(ByteOrder.BIG_ENDIAN)`: byte ordering of multi-byte values.
- `layout.withByteAlignment(1)`: lowers the byte alignment requirement of a layout (for unaligned cases, you must know the memory format well).
- `layout.withName("field")`: attaches a name to the layout, useful with `structLayout` and `byteOffset(...)`.
- `layout.byteSize()`, `layout.byteAlignment()`, `layout.order()`: inspects the current contract.

Example:

```java
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

ValueLayout.OfInt intLE =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);

System.out.println(intLE.byteSize());       // 4
System.out.println(intLE.byteAlignment());  // Usually 4
System.out.println(intLE.order());          // LITTLE_ENDIAN
```

This is an **illustrative snippet**, not a standalone runnable file. `ValueLayout.JAVA_INT` defaults to the platform's byte order; **do not assume every machine is little-endian**. When defining a file/packet/binary protocol format, you should explicitly choose the byte order so data is consistent across all platforms.

**ABI Warning:** `JAVA_LONG` corresponds to an **8-byte** Java `long`, which is not inherently synonymous with C `long` on Windows/Linux. If interacting directly with a C struct, you must check size/alignment/packing according to the **specific ABI**, not guess from the Java type name.

## 5. `get/set` Uses Byte Offset; `getAtIndex/setAtIndex` Uses Element Index

The following two API pairs look similar, but their units are **completely different**:

```java
segment.set(ValueLayout.JAVA_INT, 8, 30);
int a = segment.get(ValueLayout.JAVA_INT, 8);

segment.setAtIndex(ValueLayout.JAVA_INT, 2, 30);
int b = segment.getAtIndex(ValueLayout.JAVA_INT, 2);
```

This is an **illustrative snippet** assuming the segment has at least 12 bytes, sufficient alignment, and is still alive.

- `get(layout, offset)`: `offset = 8` means the **8th** byte from the start of the segment.
- `getAtIndex(layout, index)`: `index = 2` means the **2nd** element (0-based), actual byte offset = `2 * layout.byteSize()` = `2 * 4 = 8`.
- `getAtIndex` does **not** create a Java array and does not increase the segment size. It only changes the unit of the access parameter.
- For an 8-byte layout, `getAtIndex(JAVA_LONG, 2)` starts at byte **16**, whereas `get(JAVA_LONG, 2)` starts at byte **2** (usually misaligned).

Table for a 16-byte segment holding four `int`s:

| `int` index | Byte offset (`index × 4`) | Accessed byte range |
|---:|---:|---|
| 0 | 0 | 0–3 |
| 1 | 4 | 4–7 |
| 2 | 8 | 8–11 |
| 3 | 12 | 12–15 |
| 4 | 16 | **Out of bounds**: requires bytes 16–19 |

For `long`/`double`, each element is 8 bytes. A 16-byte segment holds **two** 8-byte elements at offsets 0 and 8, **not** 16 `long` elements.

### Bounds-Check Formula

Given a segment with `N = segment.byteSize()`, and a layout with `S = layout.byteSize()`. An access starting at byte offset `O` is valid with respect to bounds only if:

```text
0 <= O  and  S <= N - O
```

Using `S <= N - O` after checking `O >= 0` avoids overflow in `O + S`. The API already checks bounds, but if computing offsets from untrusted input, you should check **before multiplying/adding**:

```java
long offset = Math.multiplyExact(index, layout.byteSize());
// Math.multiplyExact detects overflow instead of wrapping to a wrong offset.
```

This is an illustrative Java formula where `index` and `layout` are already declared, and `layout.byteSize()` returns `long`. For an element-count index, you must check `index >= 0`, element count, and appropriate alignment.

## 6. Complete Program: Writing 24 Bytes, Reading Back, and Testing Errors

The example below uses **explicit byte orders**, so the hex byte output is stable on both little-endian and big-endian machines. A 24-byte segment is allocated with alignment 8.

**File `SegmentOffsetsDemo.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

public class SegmentOffsetsDemo {
    public static void main(String[] args) {
        var intLE = ValueLayout.JAVA_INT.withOrder(
                ByteOrder.LITTLE_ENDIAN);
        var longBE = ValueLayout.JAVA_LONG.withOrder(
                ByteOrder.BIG_ENDIAN);

        MemorySegment savedView;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(24, 8);
            savedView = segment;

            // bytes 0..3, 4..7: two little-endian ints.
            segment.set(intLE, 0, 0x12345678);
            segment.set(intLE, 4, -7);

            // bytes 8..15: one big-endian long.
            segment.set(longBE, 8, 0x0102030405060708L);

            // byte 16: one byte value, no byte order.
            segment.set(ValueLayout.JAVA_BYTE, 16, (byte) 0x7F);

            // bytes 20..23: one little-endian int.
            segment.set(intLE, 20, 99);

            System.out.println("size=" + segment.byteSize());
            System.out.printf("int@0=0x%08X%n",
                    segment.get(intLE, 0));
            System.out.println("int@4=" + segment.get(intLE, 4));
            System.out.printf("long@8=0x%016X%n",
                    segment.get(longBE, 8));
            System.out.printf("byte@16=0x%02X%n",
                    Byte.toUnsignedInt(
                            segment.get(ValueLayout.JAVA_BYTE, 16)));

            // index = 1 => byte offset = 1 * 4 = 4.
            System.out.println("atIndex[1]=" +
                    segment.getAtIndex(intLE, 1));

            // Slice rooted at byte 8 of parent.
            MemorySegment slice = segment.asSlice(8, 8);
            System.out.printf("slice long@0=0x%016X%n",
                    slice.get(longBE, 0));

            StringBuilder hex = new StringBuilder();
            for (long offset = 0; offset < segment.byteSize();
                    offset++) {
                if (offset != 0) {
                    hex.append(' ');
                }
                int unsignedByte = Byte.toUnsignedInt(
                        segment.get(ValueLayout.JAVA_BYTE, offset));
                hex.append("%02X".formatted(unsignedByte));
            }
            System.out.println("raw=" + hex);

            try {
                segment.get(intLE, 2);
            } catch (IllegalArgumentException e) {
                System.out.println(
                        "misaligned=IllegalArgumentException");
            }

            try {
                segment.get(intLE, 24);
            } catch (IndexOutOfBoundsException e) {
                System.out.println(
                        "oob=IndexOutOfBoundsException");
            }

            try {
                segment.asReadOnly().set(intLE, 0, 1);
            } catch (IllegalArgumentException e) {
                System.out.println(
                        "readonly=IllegalArgumentException");
            }
        }

        // savedView references the same memory whose lifetime has ended.
        try {
            savedView.get(intLE, 0);
        } catch (IllegalStateException e) {
            System.out.println(
                    "afterClose=IllegalStateException");
        }
    }
}
```

Compile and run with JDK 22+:

```bash
javac -encoding UTF-8 SegmentOffsetsDemo.java
java SegmentOffsetsDemo
```

**Full stdout (verified on JDK 24):**

```text
size=24
int@0=0x12345678
int@4=-7
long@8=0x0102030405060708
byte@16=0x7F
atIndex[1]=-7
slice long@0=0x0102030405060708
raw=78 56 34 12 F9 FF FF FF 01 02 03 04 05 06 07 08 7F 00 00 00 63 00 00 00
misaligned=IllegalArgumentException
oob=IndexOutOfBoundsException
readonly=IllegalArgumentException
afterClose=IllegalStateException
```

### Explaining the Output Lines

- `size=24`: `byteSize()` returns the number of **bytes**, not the number of `int`s.
- `0x12345678` is written in little-endian as bytes `78 56 34 12` at offsets 0–3.
- `-7` has 32-bit two's complement representation `0xFFFFFFF9`, so the four little-endian bytes are `F9 FF FF FF` at offsets 4–7.
- `0x0102030405060708L` is written in big-endian as `01 02 03 04 05 06 07 08` at offsets 8–15.
- Byte `7F` is at offset 16; the three bytes 17–19 remain `00` because a new allocation is zero-initialized.
- The value `99 = 0x63` written at offset 20 becomes `63 00 00 00`.
- `getAtIndex(intLE, 1)` reads byte offset 4 and returns `-7`.
- `asSlice(8, 8)` creates an 8-byte **view** of the original region: byte offset 0 of the slice corresponds to byte offset 8 of the parent.
- The exceptions demonstrate that alignment, bounds, read-only, and arena lifetime are checked **before** an invalid access occurs.

Memory diagram after the `set` calls:

```text
offset  [00][01][02][03]  [04][05][06][07]
bytes    78  56  34  12    F9  FF  FF  FF
         little-endian int   -7 little-endian

offset  [08][09][10][11][12][13][14][15]
bytes    01  02  03  04  05  06  07  08
         big-endian long

offset  [16][17][18][19]  [20][21][22][23]
bytes    7F  00  00  00    63  00  00  00
         byte + zero        int 99 little-endian
```

This is memory **whose type is interpreted by the caller at read/write time**. The segment itself does not store metadata like "offset 8 is a long" in the native bytes.

## 7. Byte Order: Reading the Right Value and Avoiding Host Dependency

**Endianness** is the byte ordering of multi-byte values:

| Value `int 0x12345678` | Bytes at offsets 0, 1, 2, 3 |
|---|---|
| Big-endian | `12 34 56 78` |
| Little-endian | `78 56 34 12` |

With `ValueLayout.JAVA_INT`, the default byte order uses the **platform's native byte order**. If fixed binary interoperability is required, declare:

```java
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

ValueLayout.OfInt intBE =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
ValueLayout.OfInt intLE =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);
```

This is a declaration snippet. A `withOrder` layout **does not convert the entire segment**; it only changes how **one specific get/set call** interprets/writes the bytes at the offset. Given the same four bytes `78 56 34 12`, reading with `intLE` returns `0x12345678` while reading with `intBE` returns `0x78563412`.

Also, do not misunderstand endianness as "the order of array elements". Elements are still at offsets 0, 4, 8, ...; byte order only affects the arrangement **within a single multi-byte value**.

**For C structs or files:** choose the byte order according to the actual C ABI or wire format specification; do not assume all files are little-endian or all C types have the same sizes. A 16-bit Java `char` is not an 8-bit C `char`; use `JAVA_BYTE` for raw bytes and a charset encoder/decoder if text is needed.

## 8. Alignment and Unaligned Access

**Alignment** is an access address constraint, distinct from bounds. For example:

- A segment allocated with `arena.allocate(24, 8)` has an 8-byte aligned base address.
- `ValueLayout.JAVA_INT` typically has a natural alignment of 4 bytes.
- Accessing an int at offsets **0, 4, 8, ...** is valid; offset **2** can violate alignment even though `2 + 4 <= 24` is still within the memory region.
- `get(intLE, 2)` in the demo throws `IllegalArgumentException` because the offset is incompatible with the layout's alignment.

**If a binary protocol is designed as *packed***, a multi-byte value may appear at an unaligned position. You can declare a layout with smaller alignment when truly needed:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class UnalignedRead {
    public static void main(String[] args) {
        var intUnaligned =
                ValueLayout.JAVA_INT.withByteAlignment(1);
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(8, 4);
            segment.set(intUnaligned, 1, 0x01020304);
            System.out.printf("0x%08X%n",
                    segment.get(intUnaligned, 1));
        }
    }
}
```

Compiling/running `javac UnalignedRead.java` and `java UnalignedRead` outputs:

```text
0x01020304
```

`withByteAlignment(1)` makes the layout allow access at any byte offset in terms of alignment; it does **not** expand the memory region and does **not** change the byte order. Unaligned accesses may have different performance/implementation characteristics and are not a good default choice for native structs with explicit alignment.

When working with a slice, alignment is checked against the **effective address** of the access, not just the offset relative to the slice. A slice starting at byte 1 can cause a `JAVA_INT` access at slice offset 0 to be misaligned. Consider the base address, slice offset, and layout together.

## 9. Slice: Sub-regions Still Share the Same Backing Memory

`asSlice(offset, length)` does not allocate a new native memory region. It creates a **view** over the corresponding part of the original segment:

```java
// Inside a live Arena, same thread:
MemorySegment whole = arena.allocate(16, 4);
MemorySegment secondInt = whole.asSlice(4, 4);

secondInt.set(ValueLayout.JAVA_INT, 0, 55);
System.out.println(whole.get(ValueLayout.JAVA_INT, 4)); // 55
```

This is an **illustrative snippet**, assuming `arena` is already initialized. Byte offset 0 of `secondInt` is byte offset 4 of `whole`. Both share the same backing allocation and the same lifetime.

Consequences:

1. Writing to the slice is observable through the parent (and vice versa).
2. The slice has its own bounds: `secondInt.get(JAVA_INT, 4)` will exceed the 4-byte slice, even though the parent still has data at offset 8.
3. Closing the Arena invalidates both the parent and all slices; a slice does not extend lifetime beyond `arena.close()`.
4. `asReadOnly()` creates a read-only view; it does not copy and does not make the backing memory globally read-only: if another writable view exists, it can still write.
5. If you want an **immutable snapshot**, you must allocate/copy to a separate buffer, not just use `asReadOnly`.

Slices are very useful for packet headers, records, or fixed-size binary fields: pass the sub-segment to a handler function to reduce the risk of accidentally accessing other bytes. However, the caller must still ensure the owner Arena has not closed while the sub-segment is in use.

## 10. Accessing an Array of Values by Index Without Confusing Units

For repeated `int` data, using `getAtIndex`/`setAtIndex` makes code more readable and avoids manually calculating the offset every time:

**File `IntArraySegment.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class IntArraySegment {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment =
                    arena.allocate(ValueLayout.JAVA_INT, 3);

            segment.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
            segment.setAtIndex(ValueLayout.JAVA_INT, 1, 20);
            segment.setAtIndex(ValueLayout.JAVA_INT, 2, 30);

            System.out.println("bytes=" + segment.byteSize());
            System.out.println("index2=" +
                    segment.getAtIndex(ValueLayout.JAVA_INT, 2));
            System.out.println("offset8=" +
                    segment.get(ValueLayout.JAVA_INT, 8));
        }
    }
}
```

Running `javac IntArraySegment.java` then `java IntArraySegment`:

```text
bytes=12
index2=30
offset8=30
```

Explanation:

- `allocate(JAVA_INT, 3)` creates **12 bytes**, enough for three 4-byte values.
- `getAtIndex(JAVA_INT, 2)` and `get(JAVA_INT, 8)` both point to byte offset `2 × 4 = 8`.
- `get(JAVA_INT, 2)` does **not** access the second element; it accesses starting at byte 2 and may fail alignment.
- `getAtIndex(JAVA_INT, 3)` throws `IndexOutOfBoundsException`: index 3 requires accessing bytes 12–15, while the segment only has bytes 0–11.

In loops with untrusted input, use `Math.multiplyExact` or `getAtIndex` instead of multiplying large numbers without overflow checks. `long` indices and `long` byte offsets still do not mean "infinite memory": every access must lie within `segment.byteSize()`.

## 11. Struct Layout: Computing Offsets from Layout Instead of Hard-Coding

When interacting with records consisting of fields of different sizes, hand-written fixed offsets easily get **padding** between fields wrong. FFM provides `MemoryLayout.structLayout` to describe the layout and `byteOffset(PathElement...)` to find the offset by field name.

Suppose a record format (explicitly **defined by the application**, not claimed to match the C ABI of every operating system):

```text
byte 0..3    : int id       (4 bytes)
byte 4..5    : short flags  (2 bytes)
byte 6..7    : padding      (2 bytes)
byte 8..15   : long count   (8 bytes)
Total        : 16 bytes
```

**File `StructOffsets.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class StructOffsets {
    public static void main(String[] args) {
        MemoryLayout record = MemoryLayout.structLayout(
                ValueLayout.JAVA_INT.withName("id"),
                ValueLayout.JAVA_SHORT.withName("flags"),
                MemoryLayout.paddingLayout(2),
                ValueLayout.JAVA_LONG.withName("count")
        );

        long idOffset = record.byteOffset(groupElement("id"));
        long flagsOffset = record.byteOffset(groupElement("flags"));
        long countOffset = record.byteOffset(groupElement("count"));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(record);

            segment.set(ValueLayout.JAVA_INT, idOffset, 42);
            segment.set(ValueLayout.JAVA_SHORT, flagsOffset, (short) 7);
            segment.set(ValueLayout.JAVA_LONG, countOffset, 1_000L);

            System.out.println("size=" + record.byteSize()
                    + " offsets=" + idOffset + ","
                    + flagsOffset + "," + countOffset);

            System.out.println("id=" +
                    segment.get(ValueLayout.JAVA_INT, idOffset)
                    + " flags=" +
                    segment.get(ValueLayout.JAVA_SHORT, flagsOffset)
                    + " count=" +
                    segment.get(ValueLayout.JAVA_LONG, countOffset));
        }
    }
}
```

Compile/run:

```bash
javac StructOffsets.java
java StructOffsets
```

**stdout:**

```text
size=16 offsets=0,4,8
id=42 flags=7 count=1000
```

Points to remember:

- `structLayout` describes the declared fields and padding bytes; do not assume it always inserts padding automatically like a C compiler. In the example, we **explicitly wrote** `paddingLayout(2)`.
- `record.byteOffset(groupElement("count"))` returns **8 bytes**, not the 8th field.
- `arena.allocate(record)` uses the record's size and alignment when allocating; this is better than counting manually and allocating the wrong amount.
- `ValueLayout.withName` helps name fields in the layout, though the names do not exist in the native byte buffer itself.
- When exact sharing with a native C struct is needed, you must verify `sizeof`, `offsetof`, ABI packing/alignment, and the corresponding C types on the target toolchain. The example above is an **explicitly defined layout**, not a portability guarantee for every C `struct`.

You can use `MemoryLayout.sequenceLayout` and layout paths if you need complex field arrays, or var handles created from layouts for repeated field access. However, for a foundational lesson, `byteOffset` plus `segment.get/set` is intuitive and easy to verify.

## 12. Error Conditions: Bounds, Alignment, Read-Only, Scope, Thread

FFM guards against several common mistakes with runtime checks. Key exceptions:

| Condition | Example | Typical result |
|---|---|---|
| Negative byte offset or access beyond segment | `segment.get(JAVA_INT, -1)`; for a 24-byte segment, `get(JAVA_INT, 24)` | `IndexOutOfBoundsException` |
| Offset does not satisfy layout alignment | `segment.get(JAVA_INT, 2)` with a sufficiently aligned native base | `IllegalArgumentException` |
| Writing through a read-only segment | `segment.asReadOnly().set(JAVA_INT, 0, 1)` | `IllegalArgumentException` |
| Accessing segment after `Arena.close()` | `savedView.get(JAVA_INT, 0)` | `IllegalStateException` |
| Confined arena/segment accessed from another thread | Worker thread calls `get` on a segment managed by thread A's confined arena | `WrongThreadException` |
| `Arena.allocate` with negative size or invalid alignment | `arena.allocate(-1, 4)`; `arena.allocate(8, 3)` | `IllegalArgumentException` |
| Attempting to close an already closed Arena | Calling `close()` twice on a manually closeable arena | `IllegalStateException` |
| Shared data race despite valid bounds | Multiple threads writing the same bytes without synchronization | No guaranteed exception; potential data race/logic bug |

**Do not use exceptions as an offset measurement tool**: check size/layout/offset against the contract beforehand; catching exceptions in the demo helps visualize the protection boundaries, not design an efficient binary parser.

### About Thread Confinement

`Arena.ofConfined()` only allows the thread that created the arena to access the associated segments. If multiple threads are truly needed, consider `Arena.ofShared()` and manage concurrent operations:

```java
// Illustrative snippet, not a full multithreaded application.
try (Arena arena = Arena.ofShared()) {
    MemorySegment segment = arena.allocate(8, 8);
    // This view can be passed to another thread.
    // Must ensure the other thread finishes using it before arena.close().
    // Must synchronize if multiple threads read/write the same location.
}
```

**A shared arena does not turn `segment.set` and `segment.get` into a synchronization protocol.** If atomic/volatile access between threads is needed, use an appropriate var handle and memory-ordering guarantees, or explicit locking. Do not close a shared arena while a background worker still intends to use the memory region. When passing native addresses to C, be even more careful: C holding a pointer after the arena closes can cause a use-after-free **outside** the protection of the Java API.

## 13. Connecting This to Native Interoperability

When Java calls a C function with a buffer/struct, Java and C must agree on **a binary contract**:

1. **Size**: total bytes, size of each field, and element count (these are distinct).
2. **Alignment**: whether field start positions meet native ABI requirements; whether there is padding or packing.
3. **Byte order**: native order or protocol-defined order, avoiding data corruption on another machine.
4. **Mutability**: is C allowed to write or only read? Using a read-only view in Java does not automatically prevent a native pointer from being written to improperly.
5. **Lifetime**: the Arena/segment must stay alive for the entire duration the native function or callback uses the pointer. Do not send a segment to a native worker and close the arena before the worker finishes.
6. **Thread-safety**: if Java and C access the same memory region concurrently, what is the synchronization contract?
7. **Ownership**: who allocates, and who is responsible for closing the Arena or calling `free` if the C library owns the allocation?

For example, with a native SDK that has a function taking `int32_t*` to write 10 elements, Java can allocate a segment using `JAVA_INT` and provide the pointer via an FFM downcall; **but only when** the C ABI, lifetime, and callback contract match. Do not assume `JAVA_INT` matches `C long` or an unverified packed struct.

For **file/wire formats** requiring little-endian, use `withOrder(LITTLE_ENDIAN)`. For **C ABI**, native endianness is typically used, though you must still verify the layout on the target system. `ValueLayout.JAVA_INT` and `ValueLayout.JAVA_LONG` are Java primitive layouts; they do not automatically define every native ABI type.

### When to Use `ByteBuffer` vs. `MemorySegment`?

`ByteBuffer` also allows `getInt(index)`/`putInt(index)` with a byte index; however, it has its own position/limit and ByteOrder. `MemorySegment` has `long byteSize`, Arena-based lifecycle, thread-access constraints, and layout integration for FFM. Neither permits invalid byte offsets/alignment. If you already have a `ByteBuffer` from a Java API, there is no need to switch to FFM just to read a few bytes; if you need native downcalls, structs, and clear ownership, `MemorySegment` is the right abstraction.

## 14. Checklist and Reinforcement Exercises

### Checklist Before Every `get/set`

- [ ] JDK ≥22; import `java.lang.foreign.` properly, do not accidentally use old preview/incubator APIs.
- [ ] Arena and segment are still alive; use `try-with-resources` when deterministic lifetime is needed.
- [ ] Segment is long enough in bytes; do not confuse element count with byte count.
- [ ] Layout matches the Java type, size, alignment, and byte order defined by the contract.
- [ ] Offset of `get/set` is a **byte offset**; index of `getAtIndex/setAtIndex` is an **element index**.
- [ ] The value to read/write fits completely within `[0, segment.byteSize())`.
- [ ] The effective address satisfies `layout.byteAlignment()`, unless intentionally using an unaligned layout.
- [ ] Do not write through a read-only view; do not keep a slice alive longer than its owner Arena.
- [ ] If multiple threads access it, use an appropriate Arena and have synchronization/lifecycle barriers in place.
- [ ] If passing down to C, verify ABI, byte order, struct padding, ownership, and deallocation timing.

### Exercise 1 — Byte Offset

Given a 24-byte segment, call `segment.set(ValueLayout.JAVA_LONG, 8, 123L)`. Which bytes are accessed?

**Answer:** starting at byte offset **8**, 8 bytes are written, which is the byte range **8–15** (or interval `[8,16)`). The layout must still satisfy alignment and the segment must still be alive.

### Exercise 2 — Elements and Bytes

Given `arena.allocate(ValueLayout.JAVA_INT, 5)`. What is `byteSize()`, the byte offset of `getAtIndex(JAVA_INT, 3)`, and the first out-of-bounds index?

**Answer:** `byteSize() = 20`, element at index 3 is at byte offset **12**; index **5** is the first index beyond the segment (for non-negative indices).

### Exercise 3 — Endianness

What four bytes does `set(JAVA_INT.withOrder(LITTLE_ENDIAN), 0, 0x01020304)` write?

**Answer:** `04 03 02 01`. Reading back with BIG_ENDIAN at offset 0 returns `0x04030201`, not `0x01020304`.

### Exercise 4 — Alignment

A segment is allocated with alignment 8, and you need to write an `int` at offset 2 of a packed format. Why might `set(JAVA_INT, 2, ...)` fail? What should you do?

**Answer:** The int layout typically requires alignment 4, so offset 2 is invalid even though it is within bounds. Use `JAVA_INT.withByteAlignment(1)` **if** the format truly allows unaligned fields, or move the field to a properly aligned offset.

### Exercise 5 — Slice and Arena

A method returns `segment.asSlice(4, 4)` from inside `try (Arena arena = Arena.ofConfined())`, and then the caller uses the slice after the method returns. Is this valid?

**Answer:** No. The slice shares the same backing memory and Arena scope. When the `try` block ends, the arena closes, and the slice becomes invalid; `get` will throw `IllegalStateException`. You must design an owner lifetime that extends appropriately or copy the data to a live region.

### Exercise 6 — Struct

A record consists of `int id` (4 bytes), `short status` (2 bytes), 2 bytes of padding, and `long version` (8 bytes). What is the total byte size and the offset of `version`?

**Answer:** Total **16 bytes**, `version` starts at byte offset **8**. Using `structLayout` with `paddingLayout(2)` and `byteOffset(groupElement("version"))` is less error-prone than hard-coding.

### Exercise 7 — Bug in Code

Evaluate:

```java
// Illustrative snippet with a unit mistake.
MemorySegment segment = arena.allocate(4, 4);
segment.set(ValueLayout.JAVA_INT, 1, 42);
```

**Answer:** `allocate(4,4)` creates 4 bytes, enough for **one int at offset 0**. Writing at offset **1** requires bytes 1–4, which is out of bounds (and usually misaligned). Fix it to `set(JAVA_INT, 0, 42)`. If the goal is the second element, you must allocate at least 8 bytes and write at offset 4 or use `setAtIndex(JAVA_INT, 1, 42)`.

## 15. Summary and Official Documentation

When allocating and accessing native memory with FFM, remember:

- **Arena allocates and manages lifetime**: `arena.allocate(bytes, alignment)`, `try-with-resources` closes the memory region at the right time.
- **MemorySegment is a bounded view**: `byteSize()`, `get/set`, `asSlice`, `asReadOnly`; does not automatically store field type information.
- **ValueLayout determines how a value is read/written**: `JAVA_INT`, `JAVA_LONG`, `withOrder`, `withByteAlignment`, `byteSize`, and `byteAlignment`.
- **Byte offset differs from element index**: `get(JAVA_INT, 8)` is equivalent in position to `getAtIndex(JAVA_INT, 2)`.
- **Minimum safety rules**: bounds + alignment + live scope + valid thread + correct byte order/ABI.
- **For interop**: write exact bytes with a clear contract for lifetime, ownership, and packing, rather than assuming Java primitive layouts automatically match every C structure.

Official documentation for reference:

- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)
- [Oracle Java SE 22 — `java.lang.foreign` package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Oracle Java SE 25 — `MemorySegment`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Oracle Java SE 25 — `Arena`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [Oracle Java SE 25 — `ValueLayout`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle Java SE 25 — `MemoryLayout` and `byteOffset`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle Java SE 25 — `SegmentAllocator`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SegmentAllocator.html)
