# ValueLayout in Java FFM: carrier type, size, and data alignment

When Java reads/writes an off-heap memory region or passes arguments to a C function via the Foreign Function & Memory API (FFM), the question is not just "does this value have type `int`?". You also need to know **how many bytes are required to represent it**, **which addresses are allowed to place that value**, **what the byte order is**, and **which Java type appears on the caller side**. `java.lang.foreign.ValueLayout` describes those exact characteristics.

This article belongs to the **Data Layout** group of Java Native Interoperability. The focus is on three properties:

- `carrier()`: the **Java type** used to carry a value across the FFM API, for example `int.class`, `double.class`, or `MemorySegment.class`.
- `byteSize()`: the **number of bytes** of a value according to the layout; not the number of elements, number of bits, or the size of a Java object.
- `byteAlignment()`: the **address/offset alignment constraint in bytes**, for example a 4-byte integer is accessed at an address that is a multiple of 4 when using `ValueLayout.JAVA_INT`.

The article additionally covers `order()`, `withOrder(...)`, `withByteAlignment(...)`, the `JAVA_*` layouts, `ADDRESS`, how to read/write `MemorySegment`, `VarHandle`, C structs with padding, ABI-based C type mapping, and common mistakes. There is **one complete Java example that runs on JDK 22+ without writing C**, and **one standalone C11 program** to compare struct layout according to a real compiler.

> **Version scope:** `java.lang.foreign.ValueLayout` became a standard API starting in **JDK 22** (JEP 454). Java 21 has a preview FFM version; Java 17 uses a different incubator API. Do not take the `java.lang.foreign.*` code here and run it as-is on JDK 17/21. The Java code in the practice section requires JDK 22 or later.

## 1. Where does ValueLayout sit in the FFM model?

~~~text
Java value (int, long, double, MemorySegment...)
                    |
                    | ValueLayout:
                    |   carrier()
                    |   byteSize()
                    |   byteAlignment()
                    |   order()
                    v
MemorySegment + byte offset -----------------> native/heap memory bytes
                    |
                    | MemoryLayout:
                    |   structLayout(...)
                    |   sequenceLayout(...)
                    |   unionLayout(...)
                    |   paddingLayout(...)
                    v
       Composite layout describing struct, array, union

Linker + FunctionDescriptor (if calling a C function)
                    |
                    | C ABI, not just Java carrier
                    v
               Native function
~~~

`MemorySegment` represents a **contiguous memory region with a size and lifetime**, such as a region allocated by `Arena.ofConfined()` or a view over a Java array. By itself, it does not declare "four bytes starting at offset 8 are an int or a float". You provide a `ValueLayout` to read/write with the exact desired representation:

~~~java
// Illustrative Java snippet, assuming the segment is alive,
// has at least 12 writable bytes, and offset 8 has sufficient alignment.
segment.set(ValueLayout.JAVA_INT, 8, 42);
int value = segment.get(ValueLayout.JAVA_INT, 8);
~~~

With `JAVA_INT`: carrier `int`, size 4 bytes, alignment 4 bytes. The Java API checks bounds, scope state, thread access, and alignment according to the layout. If you replace `JAVA_INT` with `JAVA_FLOAT` at the same memory region, you are **interpreting the same bytes as a different type**, not "casting" a Java `int` to `float`.

`ValueLayout` is a **value describing data**, not a memory region. Creating a layout does not allocate memory and does not create a C object. `MemoryLayout` is the parent type; besides scalar values there are `SequenceLayout`, `StructLayout`, `UnionLayout`, and `PaddingLayout`. `ValueLayout` is a branch dedicated to scalar/address values that have a corresponding Java carrier.

## 2. Three core properties: carrier, size, and alignment

Suppose:

~~~java
ValueLayout.OfInt layout = ValueLayout.JAVA_INT;

Class<?> type = layout.carrier(); // int.class
long size = layout.byteSize();    // 4 bytes
long align = layout.byteAlignment(); // 4 bytes
~~~

This is an illustrative Java snippet; the standalone runnable example is in section 10.

### 2.1. `carrier()` is a Java type, not a "C type name"

`carrier()` returns the `Class<?>` of the type that Java will receive/pass when using the layout. With `JAVA_INT`, the carrier is `int.class`, so `MemorySegment.get(ValueLayout.JAVA_INT, offset)` returns `int` and `set(..., intValue)` accepts `int`. With `JAVA_DOUBLE`, the carrier is `double.class`. With `ValueLayout.ADDRESS`, the carrier is `MemorySegment.class`: a native address is represented on the Java side as a segment/address object, **not** an arbitrary `long` or `Object`.

This distinction is especially important when creating an FFM `FunctionDescriptor`: the `ValueLayout`s in the descriptor affect the Java `MethodHandle` type of the downcall/upcall. If you describe C `int32_t` with `JAVA_LONG` (carrier `long`, width 8 bytes) instead of a suitable 4-byte layout, you can produce a **wrong ABI** even if the C function name is right.

**The carrier is a Java type**, which does not imply signedness, the size of C `long` across all OSes, bitfield semantics, nullable contract, or Unicode encoding. Those factors must be determined from the C header, ABI, and protocol documentation.

### 2.2. `byteSize()` is the representation width of **one** value

`JAVA_INT.byteSize() == 4` means one value uses four bytes; `JAVA_LONG.byteSize() == 8` means eight bytes. With `ADDRESS`, the width depends on the platform's native pointer size, typically 4 bytes on 32-bit targets or 8 bytes on 64-bit targets.

If a native array has 100 `int32_t` elements and each element corresponds to `JAVA_INT`, the amount of data is `100 * JAVA_INT.byteSize()` = 400 bytes, **not** 100 bytes. When multiplying count by size, check for overflow if count comes from large or untrusted input.

`byteSize()` says nothing about the byte count of a Java `Integer` object or JVM metadata, nor does it grant permission to measure a Java `int[]` directly with a C pointer. Java heap objects/arrays have a JVM-managed layout and are completely different from raw native memory.

### 2.3. `byteAlignment()` constrains access addresses

An alignment of 4 means the access region of a value must start at an **address divisible by 4**; the offset must also combine with the actual alignment of the base address. With `JAVA_INT`, offsets 0, 4, 8... in a **segment with suitable base alignment** are valid; offset 1 is invalid for aligned int access.

Alignment is a power of 2, not necessarily equal to `byteSize()`. Specifically, according to the **JDK 22** documentation, `JAVA_LONG` and `JAVA_DOUBLE` always have a size of 8 bytes, but the alignment of these two constants can be 4 bytes on 32-bit platforms and 8 bytes on 64-bit platforms. Do not infer `byteAlignment() == byteSize()` for every `ValueLayout`.

You can request adjusting the constraint with `withByteAlignment(long)`; this **creates a new layout**, it does not make the CPU automatically fix the alignment of a pointer. If the C ABI/struct requires alignment 8, you must ensure the memory region/offset matches, not just change a number in the description.

## 3. Built-in ValueLayouts in JDK 22

The constants in `ValueLayout` use `JAVA_*` names because their carrier and size are defined according to Java types. Common values:

| Constant | `carrier()` | `byteSize()` | Alignment in JDK 22 |
| --- | --- | ---: | --- |
| `JAVA_BOOLEAN` | `boolean.class` | 1 | 1 |
| `JAVA_BYTE` | `byte.class` | 1 | 1 |
| `JAVA_CHAR` | `char.class` | 2 | 2 |
| `JAVA_SHORT` | `short.class` | 2 | 2 |
| `JAVA_INT` | `int.class` | 4 | 4 |
| `JAVA_LONG` | `long.class` | 8 | Native address dependent: typically 4 or 8 |
| `JAVA_FLOAT` | `float.class` | 4 | 4 |
| `JAVA_DOUBLE` | `double.class` | 8 | Native address dependent: typically 4 or 8 |
| `ADDRESS` | `MemorySegment.class` | Pointer size: typically 4/8 | Pointer dependent: typically 4/8 |

Do not treat this table as a direct mapping table for **every C type**. For example:

- Java `char` is **a 16-bit UTF-16 code unit**, not by default equal to C `char` (usually 1 byte) or `wchar_t` (platform-dependent size).
- Java `boolean` has a 1-byte `ValueLayout.JAVA_BOOLEAN` in the API, but C `bool`/`_Bool` should be matched against the **canonical layout of the target linker ABI**, not guessed from the name.
- C `long` is usually 64-bit on Linux x64 (LP64) but **32-bit on Windows x64 (LLP64)**. Java `long` always has a 64-bit carrier; `JAVA_LONG` is not an automatic mapping for every C `long`.
- C `size_t` and pointer types depend on the architecture; a Java `int` cannot hold all 64-bit unsigned values without a handling policy.
- Unsigned C integers usually use the **same storage layout size** as their signed counterparts, but Java code must interpret the unsigned value range itself, mask/convert, or use a wider type when needed.

The constants `JAVA_CHAR_UNALIGNED`, `JAVA_SHORT_UNALIGNED`, `JAVA_INT_UNALIGNED`, `JAVA_LONG_UNALIGNED`, `JAVA_FLOAT_UNALIGNED`, `JAVA_DOUBLE_UNALIGNED`, and `ADDRESS_UNALIGNED` also exist. They reduce the alignment constraint to 1 byte, **without changing the carrier or size**. Use them only when the data representation genuinely has weak alignment or is packed; unaligned access can have lower performance or be non-portable when interacting with native ABIs.

### 3.1. Why can't you just look at the Java type?

Just seeing Java `long` and putting `JAVA_LONG` is not enough. There are at least three layers:

1. **Java carrier:** when reading or invoking `MethodHandle`, the Java side uses `long.class` or `int.class`.
2. **Memory layout:** how many bytes a value spans, in what byte order, and at what alignment.
3. **Target ABI:** which C function/struct on which OS/compiler/CPU dictates width, padding, register passing, return strategy, and calling convention.

FFM describes a lot of information in Java, but you still have to read the C header (or use a binding generator like jextract when appropriate) and verify against the compiler for the right target. "Java int and C int are both 4 bytes" is common on JDK-supported ABIs, but it is not a license to ignore the library's ABI contract.

## 4. Endianness: `order()` and `withOrder(...)`

A 32-bit value `0x01020304` consists of four bytes. In **big-endian**, the order from low address to high address is `01 02 03 04`; in **little-endian**, it is `04 03 02 01`. `ValueLayout` has `order()` to describe byte order; by default the `JAVA_*` constants use `ByteOrder.nativeOrder()`.

~~~java
ValueLayout.OfInt bigEndian =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

// Illustrative snippet: buffer has >= 4 bytes and alignment >= 4.
buffer.set(bigEndian, 0, 0x01020304);
~~~

`withOrder(...)` returns a new layout, **without altering the contents of an existing segment**. When you use a different layout to read the same four bytes, the numeric result can differ. The change is in how data is **interpreted/stored**, not a `Integer.reverseBytes(...)` cast at the Java object level.

Do not mix network protocol byte order (typically big-endian) with the native order of the C ABI. For fixed-format binary files, use `withOrder(ByteOrder.BIG_ENDIAN/LITTLE_ENDIAN)` according to the file spec. For native structs exchanged through the local linker, use native order/canonical layouts and follow the target ABI.

For single-byte layouts like `JAVA_BYTE`, changing endianness makes no difference to the byte order of an individual value. For multi-byte scalars, it matters a great deal.

## 5. `withByteAlignment(...)`, unaligned layouts, and alignment errors

A layout has three pieces of information that developers easily conflate: **byteSize**, **byteAlignment**, and **base address + offset**. A 12-byte segment does not mean every offset from 0 to 8 is valid for reading a 4-byte `JAVA_INT`:

~~~java
// Example snippet: arena is alive, raw is allocated with base alignment 4.
MemorySegment raw = arena.allocate(12, 4);

raw.set(ValueLayout.JAVA_INT_UNALIGNED, 1, 123);
int value = raw.get(ValueLayout.JAVA_INT_UNALIGNED, 1); // Valid

// raw.get(ValueLayout.JAVA_INT, 1) will hit an alignment error.
~~~

`JAVA_INT_UNALIGNED` still has size 4 and carrier `int.class` but alignment 1, so the byte range 1–4 is valid in terms of **layout constraint**. `JAVA_INT` has alignment 4; when base is 4-byte aligned and offset = 1, accessing with that layout throws `IllegalArgumentException`.

If offset = 9 on a 12-byte segment, even using an unaligned layout cannot read a 4-byte int: the range 9..12 goes out of bounds; FFM reports `IndexOutOfBoundsException`. **Reducing alignment does not expand memory region size.**

`withByteAlignment(3)` is invalid because the constraint must be a power of 2; values like 1, 2, 4, 8 are syntactically valid candidates, but must match the data and ABI. `withByteAlignment(1)` is equivalent to the corresponding `*_UNALIGNED` constants when keeping the other properties the same.

**Do not use unaligned layouts to mask struct errors:** if a C struct has compiler-inserted padding, trying to read a member at offset 1 with `JAVA_INT_UNALIGNED` may "read" some bytes, but that is **not** the right C field. You must fix the struct's layout diagram and offsets, not merely relax the constraint.

## 6. Reading/writing MemorySegment by byte offset or element index

There are two styles:

~~~java
// Illustrative snippet: numbers holds at least 3 ints,
// base has proper alignment, and arena is not closed.
numbers.set(ValueLayout.JAVA_INT, 0, 7);
numbers.set(ValueLayout.JAVA_INT, 4, 8);
numbers.set(ValueLayout.JAVA_INT, 8, 9);

int secondByByteOffset =
        numbers.get(ValueLayout.JAVA_INT, 4);       // 8
int secondByElementIndex =
        numbers.getAtIndex(ValueLayout.JAVA_INT, 1); // 8
~~~

`get(layout, offset)` and `set(layout, offset, value)` take a **byte offset**. `getAtIndex(layout, index)` and `setAtIndex(layout, index, value)` take an **element index**, automatically scaling by `layout.byteSize()`. If you use `index=4` for a four-element int array, the second style asks for the fifth element and can go out of bounds; the first style simply points to byte 4 (the second element).

For a sequence whose stride differs from field size (for example a struct with padding), do **not** assume index×size of a field is the record's stride. Use a proper `SequenceLayout`/`StructLayout` or offsets computed from the full record layout.

### 6.1. ValueLayout creates a VarHandle with explicit carrier and offset

~~~java
VarHandle intHandle = ValueLayout.JAVA_INT.varHandle();

// Coordinate types of this VarHandle: (MemorySegment, long).
intHandle.set(numbers, 4L, 456);
int received = (int) intHandle.get(numbers, 4L);
~~~

The returned `VarHandle` has **value type** equal to the carrier (`int.class`) and **coordinates** equal to segment + `long` byte offset. It enforces alignment constraints and scope/bounds checks just like layout-based segment access. This is not a "direct raw pointer bypassing checks".

`MemoryLayout.varHandle(PathElement...)` also exists to access fields in a struct/sequence via a **layout path**, instead of manually adding magic offsets. In the case of a single scalar, `ValueLayout.varHandle()` is simple and avoids building unnecessary paths. When moving to structs, also see `byteOffset(...)` in section 8.

### 6.2. Choosing between `get/set` and `VarHandle`

- **Reading/writing individual simple scalars:** `segment.get(layout, byteOffset)` and `segment.set(...)` are easy to read.
- **Code reusing a layout/field many times:** `VarHandle` can be kept as metadata and used to access many segments of the same shape; do not keep it together with a closed segment and misuse the scope.
- **Struct/sequence with path:** `MemoryLayout.varHandle(...)` or `byteOffset(...)` makes code less dependent on hard-coded offsets.
- **Concurrent/atomic access:** do not assume a valid layout automatically guarantees synchronization. Use access modes supported by VarHandle and synchronize properly per contract; unaligned or composite operations do not automatically have atomic semantics.

## 7. ValueLayout does not automatically generate padding in C structs

This is a major trap of data layout. Consider the C11 struct:

~~~c
#include <stdint.h>

struct Record {
    uint8_t tag;
    int32_t value;
};
~~~

On common ABIs where `int32_t` has alignment 4, the compiler places:

~~~text
byte offset:    0   1   2   3   4   5   6   7
contents:      tag pad pad pad [   value      ]
field size:      1     +3          +4
struct size:                       8 bytes
struct align:                      4 bytes
~~~

It must not be described by:

~~~java
// WRONG for the common struct above: missing padding.
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withName("value"));
~~~

In JDK 22, `MemoryLayout.structLayout(...)` **does not automatically insert padding**. Moreover, the `JAVA_INT` field needs to start at a 4-aligned offset; placing it immediately after one byte usually causes the factory method to reject the misaligned layout, rather than "silently fixing it into a C struct".

Explicitly padded description:

~~~java
MemoryLayout RECORD = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value")
);
~~~

Properties of this layout:

- `RECORD.byteSize() == 8`: sum 1 + 3 + 4.
- `RECORD.byteAlignment() == 4`: largest among the member alignments.
- `RECORD.byteOffset(PathElement.groupElement("tag")) == 0`.
- `RECORD.byteOffset(PathElement.groupElement("value")) == 4`.

`MemoryLayout.paddingLayout(3)` occupies three bytes **carrying no data field**. Padding is not a value you need to copy/compute; when serializing and comparing records, padding may contain uninitialized bytes or differ across compilers/processes. Do not send extra padding bytes out over a public protocol unless explicitly specified.

**Tail padding:** A C struct may have bytes appended by the compiler at the end so that the size of each element in an array of structs respects alignment. The Java layout must declare a trailing size/stride matching C `sizeof(struct)`. For example, a struct with `int32_t` then `uint8_t` may need three padding bytes at the end on a 4-aligned ABI. Do not think only about padding *between* fields.

### 7.1. How to verify layout from the C compiler

For real C headers, use `sizeof`, `_Alignof`, and `offsetof` (C11) to compare with Java `byteSize/byteAlignment/byteOffset`; do not rely on guesswork. `#pragma pack`, `__attribute__((packed))`, compiler flags, and OS ABI can change field placement; **the FFM layout must match the linked binary**, not just an initial mental picture.

A runnable C program to measure the struct is in section 12. For complex cases, a binding generator like `jextract` can reduce manual layout entry errors, but you still must review ownership, API version, and ABI.

## 8. Using ValueLayout in SequenceLayout and GroupLayout

`ValueLayout`s are the building blocks of composite memory layouts.

### 8.1. Contiguous array of three int32s

~~~java
// Illustrative Java snippet:
MemoryLayout THREE_INTS =
        MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT);

System.out.println(THREE_INTS.byteSize());      // 12
System.out.println(THREE_INTS.byteAlignment()); // 4
~~~

Size is 3×4=12 bytes; alignment is the alignment of the element layout. `Arena.allocate(THREE_INTS)` can create a segment with the right size/alignment, and then `getAtIndex(JAVA_INT, i)` accesses the elements contiguously.

Distinguish this from a **pointer to a C array**: ValueLayout does not know whether a C pointer actually has at least three elements. `ValueLayout.ADDRESS` only describes **the address value**; the bounds of the region it points to must be proven/established separately, not inferred from "an 8-byte address".

### 8.2. Struct and union

- `MemoryLayout.structLayout(...)` places fields contiguously according to the layouts you provide; padding must be added to match the C ABI.
- `MemoryLayout.unionLayout(...)` lets members share the same starting point; the size of the union is the largest size among the member layouts. The C compiler may add tail alignment/padding; verify with the target.
- `MemoryLayout.paddingLayout(n)` represents a gap skipped when reading values.
- `MemoryLayout.PathElement.groupElement("fieldName")` lets you obtain `byteOffset(...)` or create a var handle to a named field.

When a C function receives a **struct by value**, do not just remember field offsets: the ABI also decides how to pass/receive the struct via registers/stack, and the layout must satisfy the linker's conditions. A struct you can read from a `MemorySegment` is not guaranteed to be a valid descriptor for passing by value if size/alignment/padding do not match the target. Use `Linker.canonicalLayouts()` for C scalars and compare `sizeof/offsetof` for C groups.

## 9. How does ValueLayout relate to Linker, FunctionDescriptor, and C ABI?

A C function declaration:

~~~c
#include <stdint.h>

/* Example C ABI, not a JNI entry point */
int32_t twice_i32(int32_t input);
~~~

Can be described in terms of return/argument layouts in FFM by:

~~~java
// Illustrative snippet: creates descriptor, does not lookup or call native function yet.
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, // C int32_t return
        ValueLayout.JAVA_INT  // C int32_t input
);
~~~

When `Linker.downcallHandle(...)` creates a `MethodHandle` based on the function descriptor, ValueLayout contributes to determining the **Java carrier** and **ABI signature**. For the descriptor above, the int carrier is suitable for both positions. But if the C function takes `long` instead of `int32_t`, you must not blindly keep `JAVA_INT` or blindly switch to `JAVA_LONG` without checking the platform.

The FFM native linker provides:

~~~java
// Illustrative snippet running on JDK 22+, not a full program.
MemoryLayout cLong =
        Linker.nativeLinker().canonicalLayouts().get("long");
MemoryLayout cSizeT =
        Linker.nativeLinker().canonicalLayouts().get("size_t");
~~~

`canonicalLayouts()` returns mappings for C types supported by the ABI. For example, on Linux x64, C `long` usually corresponds to `JAVA_LONG`; on Windows x64, it usually corresponds to `JAVA_INT`. `size_t` is usually 64-bit on 64-bit and 32-bit on 32-bit. When an exact mapping is needed, look it up via the native linker and C header instead of duplicating assumptions across all targets.

**Native access permission note:** creating a layout/reading a memory segment with a valid scope does not mean performing a foreign function call. **Restricted operations** such as `Linker.downcallHandle`, `SymbolLookup.libraryLookup`, `Linker.upcallStub` typically require `--enable-native-access` for the calling module according to JDK policy. The main example in section 10 does not call external libraries or restricted downcalls; therefore, granting native access is not needed just to run `MemorySegment` read/write operations allocated by `Arena`.

### 9.1. Why is a pointer not `JAVA_LONG`?

On a 64-bit JVM, `ADDRESS.byteSize()` is usually 8, and `JAVA_LONG.byteSize()` is also 8. **Equal size does not mean the same ABI semantics.** `ADDRESS.carrier()` is `MemorySegment.class`, whereas `JAVA_LONG.carrier()` is `long.class`. A `FunctionDescriptor` for a C pointer must use `ADDRESS`, not `JAVA_LONG` just because the size happens to be the same on one target.

On 32-bit targets, a pointer is 4 bytes while Java `long` is still 8 bytes: this mistake also gets the size wrong. `AddressLayout` also supports attaching a target layout when you want to describe a pointer to a region of a known shape; however, a target layout does not allocate memory or prove the C-side pointer is still alive. If C returns an address, Java must handle ownership, nullability, access bounds, and native lifetime accordingly.

## 10. Full Java 22+ example: measuring layouts, writing bytes, and checking alignment

Create **a single file** `ValueLayoutDemo.java` in an empty directory, with no package declaration. There is no accompanying C code or native library; this example demonstrates the exact layout-description/memory functionality of `ValueLayout`.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;
import java.nio.ByteOrder;

public final class ValueLayoutDemo {
    public static void main(String[] args) {
        ValueLayout.OfInt nativeInt = ValueLayout.JAVA_INT;
        ValueLayout.OfInt bigEndian =
                ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

        System.out.println("carrier=" +
                nativeInt.carrier().getSimpleName());
        System.out.println("size=" + nativeInt.byteSize());
        System.out.println("alignment=" + nativeInt.byteAlignment());
        System.out.println("nativeOrder=" +
                (nativeInt.order() == ByteOrder.nativeOrder()));
        System.out.println("addressCarrier=" +
                ValueLayout.ADDRESS.carrier().getSimpleName());

        MemoryLayout recordLayout = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("tag"),
                MemoryLayout.paddingLayout(3),
                ValueLayout.JAVA_INT.withName("value")
        );
        long tagOffset = recordLayout.byteOffset(
                PathElement.groupElement("tag"));
        long valueOffset = recordLayout.byteOffset(
                PathElement.groupElement("value"));

        System.out.println("recordSize=" + recordLayout.byteSize());
        System.out.println("recordAlignment=" +
                recordLayout.byteAlignment());
        System.out.println("tagOffset=" + tagOffset);
        System.out.println("valueOffset=" + valueOffset);

        MemorySegment closedLater;
        try (Arena arena = Arena.ofConfined()) {
            // Allocate with proper base alignment 4, enough for 8 bytes.
            MemorySegment numbers = arena.allocate(8, 4);
            closedLater = numbers;

            // Regardless of native little/big endian,
            // the BIG_ENDIAN layout writes exactly 01 02 03 04.
            numbers.set(bigEndian, 0, 0x01020304);
            String bytes = String.format("%02X %02X %02X %02X",
                    numbers.get(ValueLayout.JAVA_BYTE, 0) & 0xFF,
                    numbers.get(ValueLayout.JAVA_BYTE, 1) & 0xFF,
                    numbers.get(ValueLayout.JAVA_BYTE, 2) & 0xFF,
                    numbers.get(ValueLayout.JAVA_BYTE, 3) & 0xFF);
            System.out.println("bigEndianBytes=" + bytes);

            numbers.set(nativeInt, 4, 123);
            System.out.println("getAtByte4=" +
                    numbers.get(nativeInt, 4));
            System.out.println("getAtIndex1=" +
                    numbers.getAtIndex(nativeInt, 1));

            VarHandle intHandle = nativeInt.varHandle();
            intHandle.set(numbers, 4L, 456);
            System.out.println("varHandle=" +
                    (int) intHandle.get(numbers, 4L));

            MemorySegment record = arena.allocate(recordLayout);
            record.set(ValueLayout.JAVA_BYTE, tagOffset, (byte) 7);
            record.set(nativeInt, valueOffset, 77);
            System.out.println("recordTag=" +
                    record.get(ValueLayout.JAVA_BYTE, tagOffset));
            System.out.println("recordValue=" +
                    record.get(nativeInt, valueOffset));

            MemorySegment raw = arena.allocate(12, 4);
            raw.set(ValueLayout.JAVA_INT_UNALIGNED, 1, 1234);
            System.out.println("unalignedRead=" +
                    raw.get(ValueLayout.JAVA_INT_UNALIGNED, 1));

            try {
                raw.get(nativeInt, 1); // Offset 1 violates alignment 4.
                System.out.println("alignmentRejected=false");
            } catch (IllegalArgumentException expected) {
                System.out.println("alignmentRejected=true");
            }

            try {
                raw.get(nativeInt, 12); // Starts at last byte + 1.
                System.out.println("boundsRejected=false");
            } catch (IndexOutOfBoundsException expected) {
                System.out.println("boundsRejected=true");
            }
        }

        try {
            closedLater.get(ValueLayout.JAVA_INT, 0);
            System.out.println("closedRejected=false");
        } catch (IllegalStateException expected) {
            System.out.println("closedRejected=true");
        }
    }
}
~~~

### 10.1. Compile and run commands

JDK 22 or later:

~~~sh
javac ValueLayoutDemo.java
java ValueLayoutDemo
~~~

Windows Command Prompt or PowerShell also uses those exact two commands. Confirm the JDK version first:

~~~sh
java -version
javac -version
~~~

**Do not add `--enable-preview`**: `java.lang.foreign` is an official API starting in JDK 22. The example makes no downcalls/upcalls, so it also does not need the `--enable-native-access` flag just to use `Arena` and `MemorySegment`. If you add restricted native operations later, you must configure native-access for the right module/JDK.

### 10.2. Expected stdout

~~~text
carrier=int
size=4
alignment=4
nativeOrder=true
addressCarrier=MemorySegment
recordSize=8
recordAlignment=4
tagOffset=0
valueOffset=4
bigEndianBytes=01 02 03 04
getAtByte4=123
getAtIndex1=123
varHandle=456
recordTag=7
recordValue=77
unalignedRead=1234
alignmentRejected=true
boundsRejected=true
closedRejected=true
~~~

The output is designed to be independent of CPU endianness: `ByteOrder.BIG_ENDIAN` fixes how the four bytes are written, while `nativeOrder=true` only checks that the standard layout uses the host's byte order. `ValueLayout.ADDRESS.byteSize()` or `JAVA_LONG.byteAlignment()` are not printed as constants in stdout because those properties are platform-dependent.

**What has been proven?**

1. `nativeInt.carrier()` is the Java primitive `int.class`, size 4, alignment 4.
2. Reading by byte offset 4 or element index 1 both fetch the second int element, but the input numbers for the two APIs have **different units**.
3. `VarHandle` carries the Java carrier and byte-offset coordinate; it is reused to read/write into the segment.
4. `Record` needs three explicit padding bytes so the `value` field sits at offset 4 and total size is 8.
5. On the same `raw` region, the unaligned layout allows offset 1 while the default layout rejects this offset.
6. The bounds check prevents reading four bytes starting at offset 12 of a 12-byte segment.
7. Once `Arena.ofConfined()` is closed, the segment becomes invalid; subsequent Java operations are rejected rather than silently reading freed memory.

**Limitation of the example:** FFM checks accesses *from Java*; the example does not prove a C function receiving a wrong pointer is safe. The example also does not measure the C compiler's ABI by itself. The next section shows how to verify C layout if interacting with a real library is needed.

## 11. Reading results in the right units: byte, bit, element, and pointer

Ask these questions before every `segment.get/set`:

- **Offset or index?** `get(JAVA_INT, 4)` reads at byte offset 4; `getAtIndex(JAVA_INT, 4)` reads from byte offset 16.
- **Byte size?** `JAVA_DOUBLE.byteSize() == 8` means eight bytes of the segment are needed, not eight Java elements.
- **Alignment?** Does it start at an address/offset that is a multiple of `byteAlignment()` when the layout requires it; is the segment base properly aligned?
- **Byte order?** Native order or a protocol specifying BIG_ENDIAN/LITTLE_ENDIAN?
- **Signedness?** `JAVA_BYTE`'s Java `byte` carrier is signed; C `uint8_t` has range 0..255, requiring `value & 0xFF` when interpreting as unsigned.
- **Address?** If reading `ADDRESS`, the Java value is a `MemorySegment` representing a pointer; do not assume it has the size of the pointee region or an independent lifetime.
- **Lifetime?** Is the Arena still open? Is this an allowed thread for accessing a confined segment?
- **Ownership?** Is the segment owned by the arena or pointing into a C malloc buffer? `Arena.close()` can only automatically manage resources belonging to its scope; it does not automatically call C `free` for every returned pointer.

A very common off-by-one/unit mistake is computing `byteOffset = elementIndex + JAVA_INT.byteSize()` instead of `elementIndex * JAVA_INT.byteSize()`; this error is even harder to spot when arrays are small. For structured data, use layout path/array element offset helpers instead of manual formulas whenever possible.

## 12. Standalone C11 program to verify actual size/alignment

When mapping C data, ask the compiler: `sizeof`, `_Alignof`, and `offsetof` are concrete verification tools on the target OS/platform.

Create `layout_contract.c`:

~~~c
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

struct Record {
    uint8_t tag;
    int32_t value;
};

int main(void) {
    printf("int32Size=%zu\n", sizeof(int32_t));
    printf("recordSize=%zu\n", sizeof(struct Record));
    printf("recordAlign=%zu\n", (size_t)_Alignof(struct Record));
    printf("tagOffset=%zu\n", offsetof(struct Record, tag));
    printf("valueOffset=%zu\n", offsetof(struct Record, value));
    return 0;
}
~~~

Linux/macOS using a C11-capable compiler:

~~~sh
cc -std=c11 -Wall -Wextra -Wpedantic layout_contract.c -o layout_contract
./layout_contract
~~~

Windows with MSVC supporting C11, run from Developer Command Prompt:

~~~bat
cl /nologo /std:c11 /W4 layout_contract.c
layout_contract.exe
~~~

On common x86_64/arm64 ABIs, stdout is typically:

~~~text
int32Size=4
recordSize=8
recordAlign=4
tagOffset=0
valueOffset=4
~~~

This is the **expected result on common ABIs**, not a guarantee across every compiler, packed setting, or architecture. `int32_t`, if present, is exactly 32 bits, but alignment of composite types needs to be confirmed with the program above. If C output differs from `recordLayout.byteSize()/byteAlignment()/byteOffset(...)` in Java, do not pass the struct between the two sides until the description is adjusted properly.

This C file runs **standalone**, requires no JNI/FFM, and builds no shared library. It only measures the C ABI layout. The Java sample in section 10 also runs standalone, without loading `layout_contract`. The two programs serve two separate verification tasks.

### 12.1. When do you have to check tail padding?

A C struct of the form:

~~~c
struct Packet {
    int32_t id;
    uint8_t flag;
};
~~~

On a 4-aligned ABI, `id` is at offset 0 (4 bytes), `flag` is at offset 4 (1 byte), and there are usually **3 bytes of tail padding** so that `sizeof(struct Packet) == 8`. If the Java layout only adds 4+1=5 bytes, when putting multiple records into a C array, the stride will be wrong. A layout describing the full 8 bytes (including trailing padding) is needed, then verify `sizeof` with the compiler of the real binary.

With `#pragma pack(1)` or a struct with a C compiler extension, alignment/offset can differ. Do not assign `*_UNALIGNED` out of habit: packed representation must be confirmed from the C target and running native library.

## 13. Common mistakes and fixes

| Symptom / anti-pattern | Real problem | Fix |
| --- | --- | --- |
| `carrier() == int.class` so assuming `C long` is also 4 bytes | Java carrier does not define C ABI | Use `Linker.canonicalLayouts()` and header/compiler |
| Assuming `JAVA_LONG.byteAlignment()` is always 8 | In JDK 22, alignment also depends on platform | Read `byteAlignment()` on the target JVM |
| Seeing `JAVA_INT.byteSize()==4` and reading at byte offset 1 | Violates default alignment of 4 | Use an aligned offset or unaligned layout if data is truly packed |
| `withByteAlignment(1)` "fixes" struct data missing padding | Does not change field offsets to match C ABI | Add padding/describe struct accurately |
| `withOrder(BIG_ENDIAN)` expecting buffer to convert previously written bytes | Layout only specifies encoding at access time | Read/write again with the layout having the right order per protocol |
| `getAtIndex(JAVA_INT, 4)` mistaken for byte 4 | Element index, not byte offset | Use `get(JAVA_INT, 4)` if you want offset 4 |
| Using `JAVA_CHAR` for UTF-8 C `char*` | Java char is 16-bit; C char is usually 8-bit | Represent byte buffer and encoding with explicit length |
| Using `JAVA_LONG` for C pointer because both are 8 bytes on x64 | Pointer carrier and ABI differ from long | Use `ValueLayout.ADDRESS` |
| Describing `structLayout(BYTE, INT)` without padding | Factory does not auto-align fields | Add `paddingLayout(...)` per `offsetof` |
| Describing C `long` on Windows x64 with `JAVA_LONG` | Windows LLP64 C long is 32-bit | Get canonical `"long"`/ABI header |
| Using the right layout after `Arena` is closed | Memory segment is no longer alive | Ensure owner/lifetime and access within scope |
| Reading a confined segment from another thread | Invalid thread access | Read on owner thread, or use an appropriate arena |
| C keeps a pointer after Java closes the arena | Native use-after-free | Stop native users before closing arena |
| C calls `free` on memory owned by a Java Arena | Two owners freeing competitively | Clearly define who allocates/who frees; no double-free |
| Describing `ValueLayout.ADDRESS` and dereferencing any address | Pointer does not prove region size/lifetime | Validate bounds/ownership before accessing pointee |
| Assuming FFM makes all C code memory-safe | Java-side bounds do not protect arbitrary C | Tests, sanitizers, ABI verification, API contract |

### 13.1. Two errors that must be clearly distinguished

**Alignment error:** the access still fits within the segment by byte count, but starts at a position that does not satisfy `layout.byteAlignment()`. FFM Java access may throw `IllegalArgumentException`. Do not use an unchecked native pointer to "dodge" the alignment check when the data is not actually unaligned-safe.

**Bounds error:** the read requires going beyond `segment.byteSize()`, even if the offset is aligned. FFM Java access throws `IndexOutOfBoundsException`. Switching to `JAVA_INT_UNALIGNED` **does not** fix an out-of-bounds error.

An error when the arena is closed is a **scope/lifetime error** (typically `IllegalStateException`), while accessing a confined segment from the wrong thread may throw `WrongThreadException`. These four error categories reflect **four independent conditions** that must be ensured.

## 14. Practice exercises with answers and verification criteria

1. **Units:** A segment has 16 bytes. At what byte offset does `getAtIndex(JAVA_INT, 2)` start? Answer: `2*4=8`; requires bytes 8..11 and proper alignment.
2. **Type:** What is `ValueLayout.ADDRESS.carrier()`? Answer: `MemorySegment.class`, not `long.class`, even when pointers are 8 bytes wide.
3. **Order:** Write `0x01020304` using `JAVA_INT.withOrder(BIG_ENDIAN)`. What are the first four bytes? Answer: `01 02 03 04`.
4. **Alignment:** Use `JAVA_INT` at byte offset 2 on a 4-aligned base segment. Is it valid? No; aligned int access requires an offset matching alignment 4.
5. **Unaligned:** Use `JAVA_INT_UNALIGNED` at offset 2 with a 4-byte segment. Is it valid? No; even with alignment 1, it needs bytes 2..5, which is out of bounds.
6. **Struct:** A C struct contains `uint8_t kind; int32_t value;` under a 4-aligned ABI. What is the offset of field `value`? Typically 4; verify with `offsetof`.
7. **Tail padding:** A C struct contains `int32_t id; uint8_t flag;` under a 4-aligned ABI. Why is `sizeof` usually 8 instead of 5? So that the stride of array elements remains 4-aligned.
8. **C long:** Why not use Java `JAVA_LONG` for C `long` on every OS? Because C `long` is typically 32 bits wide on Windows x64 but 64 bits on Linux x64.
9. **Lifetime:** Use `Arena.ofConfined()` and keep `MemorySegment` after try-with-resources; can it be read? No; the scope is closed.
10. **FFM function:** What layout describes C `int32_t calculate(int32_t)` for parameter/return? `JAVA_INT` when the ABI defines the type as exact int32_t and the layout is compatible; if using C `long`, check canonical mapping.
11. **Signedness:** C `uint8_t` holding 255 read into Java `byte` becomes what value? The bit pattern is `0xFF`, Java `byte` interprets it as -1; `b & 0xFF` gives 255.
12. **Unknown pointer:** C returns `void *`; what Java carrier does FFM `ADDRESS` return, and why can't you automatically read 100 bytes? `MemorySegment`; the pointer value does not prove region extent/ownership, so a separate native contract is needed.

Answers must be checked against **units**, **layout**, **ABI**, and **lifetime**, not just byte counts. Questions about structs and C types are conditional on the target ABI, because a portable Java wrapper must work with real binaries, not single-OS assumptions.

## 15. Checklist before using ValueLayout in a project

- **Version:** Does the JDK baseline have standard `java.lang.foreign.ValueLayout` (JDK 22+)? If Java 17/21, have incubator/preview examples been separated for the right version?
- **Carrier:** Is `carrier()` the right Java primitive or `MemorySegment` for a pointer? Does the MethodHandle type match?
- **Size:** `byteSize()` reflects the byte count of **one** value; have counts been converted to byte size safely with overflow handling?
- **Alignment:** Do the base segment and every byte offset satisfy `byteAlignment()`? Is `*_UNALIGNED` being abused to hide a wrong layout?
- **Byte order:** Is the data native ABI or a network/file format? Does `order()`/`withOrder(...)` match?
- **Composite:** Has `structLayout` added the necessary padding/tail padding? Does `byteOffset(...)` match real `offsetof`?
- **Pointer:** `ADDRESS` is not confused with `JAVA_LONG`; are nullability/size/ownership of the pointee clearly defined?
- **C ABI:** For `long`, `size_t`, `wchar_t`, `bool`, structs/callbacks, have canonical layouts and the target header/compiler been checked?
- **Lifetime:** Is the Arena still alive during reads/writes/downcalls? Is native code holding a pointer after the arena closes?
- **Thread:** Does a confined/shared arena suit the caller threads? Are there no accesses from the wrong thread?
- **Safety:** Are misalignment, out-of-bounds, closed-scope, wrong-endianness, unsigned values, and packed struct data tested?
- **Native access:** If adding `Linker.downcallHandle`, `SymbolLookup.libraryLookup`, or `upcallStub`, has native access permission been granted to the right module per JDK deployment?
- **Build/verify:** Has the real Java demo been run on the target JDK, C `sizeof/alignof/offsetof` compared, and the native library checked for the right OS/CPU/ABI?

**Conclusion:** `ValueLayout` is not just a "data type name". It binds a **Java carrier** to a **byte width**, **alignment constraint**, and **byte order** so FFM can read/write structured memory. When going down to the C ABI, you also must compare against **how the real compiler lays out data** and manage the **lifetime** of the memory region. Distinguishing these layers prevents wrong offsets, wrong carrier types, wrong padding, wrong endianness, and many hard-to-diagnose crashes.

### Official references (JDK 22)

- Oracle, [`ValueLayout` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): `carrier`, `order`, `JAVA_*` constants, `ADDRESS`, and platform-dependent alignment.
- Oracle, [`MemoryLayout` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): `byteSize`, `byteAlignment`, `structLayout`, `paddingLayout`, `sequenceLayout`, `byteOffset`, var handles.
- Oracle, [`MemorySegment` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `get/set`, `getAtIndex/setAtIndex`, bounds, alignment, scope, and thread checks.
- Oracle, [`Arena` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): allocating memory with proper layout/alignment and scope lifetime.
- Oracle, [`Linker` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): C ABI mappings, `canonicalLayouts`, `FunctionDescriptor`, downcall/upcall.
- OpenJDK, [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM finalized in JDK 22.