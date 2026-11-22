# StructLayout, UnionLayout, and SequenceLayout Representing C Structures

## Lesson Objectives

When interoperating between Java and C/C++ using the Foreign Function & Memory API (FFM), data often resides in a native memory region rather than a Java object. **MemorySegment** provides a bounded view over a memory region; **MemoryLayout** describes **how the bytes of the memory region are arranged**. The three central layouts for representing C structures are:

- **StructLayout** — sequential fields, modeling a C **struct**.
- **UnionLayout** — fields starting at the same offset and sharing bytes, modeling a C **union**.
- **SequenceLayout** — elements of the same layout laid out contiguously, modeling a C array **T[N]**.

After this lesson, you will be able to build layouts from a C header, calculate **byteSize**, **byteAlignment**, **byteOffset**, understand padding and stride, access nested members via **VarHandle**, verify against **sizeof/offsetof** of a C compiler, and recognize where to handle ABI, endianness, packed structs, pointers, and native memory lifecycle.

**Version:** Java programs using the **java.lang.foreign** package were standardized in **JDK 22** (JEP 454). Run with JDK 22+; the API in JDK 17 is incubator and in JDK 21 is preview, so the statements below cannot be used verbatim. Examples describing the C ABI are stated under specific conditions; it is not claimed that a single size or alignment applies to every CPU/OS/compiler.

## 1. Layout is a description; segment is the memory

~~~text
MemorySegment:
+------+------+------+------+------+------+------+------+
| byte | byte | byte | byte | byte | byte | byte | ...  |
+------+------+------+------+------+------+------+------+
             ^
             |
         MemoryLayout
         /    |      \
       struct union   sequence
   sequential       repeated
           overlapping
~~~

**MemoryLayout** does not allocate data on its own and does not copy bytes on its own. It only holds rules for position, size, and alignment. **MemorySegment** represents the actual byte region, with access bounds and lifetime. For native memory, **Arena** typically manages allocation and deallocation.

A typical workflow:

1. Define the layout from C types and ABI.
2. Check **layout.byteSize()**, **layout.byteAlignment()**, and field offsets.
3. Allocate memory using **arena.allocate(layout)** or receive a segment created elsewhere.
4. Obtain a **VarHandle** from a layout path.
5. Read/write data while the segment is alive, with proper alignment, bounds, and thread.

Layout types:

| Type | Interpretation | Size rule |
| --- | --- | --- |
| **ValueLayout** | Scalars such as int, float, byte, address | According to carrier/layout |
| **PaddingLayout** | Padding byte region | Specified number of bytes |
| **StructLayout** | Group of sequential members | Sum of byteSize of declared members |
| **UnionLayout** | Group of overlapping members | Max byteSize of members |
| **SequenceLayout** | Repetition of an element layout | Count × element byteSize |

Both StructLayout and UnionLayout are **GroupLayout**; members can be value layouts or nested layouts. SequenceLayout can contain a struct; a struct can contain a sequence/union; a union can contain a struct.

### A simple value layout

**File OneInt.java:**

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class OneInt {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment memory =
                    arena.allocate(ValueLayout.JAVA_INT);
            memory.set(ValueLayout.JAVA_INT, 0, 123);
            System.out.println("bytes = " + memory.byteSize());
            System.out.println("value = "
                    + memory.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

Run:

~~~bash
javac OneInt.java
java OneInt
~~~

Stdout:

~~~text
bytes = 4
value = 123
~~~

**ValueLayout.JAVA_INT** is fixed at 4 bytes according to Java; do not assume C long or size_t is also 4 bytes.

## 2. StructLayout: sequential members and padding must be explicit

C:

~~~c
struct Header {
    unsigned char tag;
    int value;
};
~~~

If the C ABI has 1-byte char, 4-byte int, and int requires alignment 4, a typical compiler lays out:

~~~text
Byte offset   0   1   2   3   4   5   6   7
             +---+---+---+---+---------------+
             |tag|pad|pad|pad|  int value    |
             +---+---+---+---+---------------+

offsetof(tag) = 0
offsetof(value) = 4
sizeof(Header) = 8
_Alignof(Header) = 4
~~~

**MemoryLayout.structLayout does not insert padding automatically.** This form is incorrect:

~~~java
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withName("value")
);
~~~

Because int is placed immediately after the tag byte, i.e., at offset 1, whereas JAVA_INT requires alignment 4. Creating this layout is rejected with **IllegalArgumentException** instead of automatically shifting int to offset 4.

Layout matching the assumed ABI:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

StructLayout HEADER = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value")
).withName("Header");
~~~

This is a declaration fragment, which needs to be placed inside a Java field or method. **HEADER.byteSize() == 8**, **HEADER.byteAlignment() == 4**. Padding is declared with **paddingLayout(3)**: the unit is bytes, not bits.

### Tail padding

C:

~~~c
struct Event {
    int code;
    unsigned char type;
};
~~~

In an ABI that aligns int to 4 bytes, code occupies offsets 0..3, type is at offset 4, but **sizeof(Event)** can be 8 rather than 5. The compiler adds 3 bytes of **tail padding** so that each **Event** element in an array starts aligned.

Corresponding Java layout:

~~~java
StructLayout EVENT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("code"),
        ValueLayout.JAVA_BYTE.withName("type"),
        MemoryLayout.paddingLayout(3)
);
~~~

Omitting tail padding causes the stride of a struct array to be wrong, or causes SequenceLayout to be rejected because **element byteSize** is not divisible by alignment.

**Conclusion:** you must check padding **between members** and **at the end of the struct** using the C compiler; do not just sum the field widths.

### Packed struct

Some compilers support packed structs, placing int directly at offset 1. A 5-byte layout can be described with:

~~~java
StructLayout PACKED = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withByteAlignment(1).withName("value")
);
~~~

**PACKED.byteSize()==5**, **PACKED.byteAlignment()==1**. This is the layout for a packed ABI *if the C compiler actually uses matching packing*, not the default way to write it. Merely calling **withByteAlignment(1)** on the group while keeping an int member that requires alignment 4 does not make that member valid at offset 1. You must specify the member's alignment properly or keep padding according to the actual ABI.

## 3. UnionLayout: multiple fields overlapping on the same byte region

C:

~~~c
union Number {
    int count;
    float ratio;
};
~~~

If int and float are both 4 bytes/alignment 4:

~~~text
Byte offset     0     1     2     3
               +-----+-----+-----+-----+
count          |   32-bit integer     |
               +-----+-----+-----+-----+
ratio          |    32-bit float      |
               +-----+-----+-----+-----+
               Same location, not two separate regions
~~~

Java:

~~~java
UnionLayout NUMBER = MemoryLayout.unionLayout(
        ValueLayout.JAVA_INT.withName("count"),
        ValueLayout.JAVA_FLOAT.withName("ratio")
).withName("Number");
~~~

Result: **NUMBER.byteSize() == 4**, **NUMBER.byteAlignment() == 4**. Do not add the two members to get 8 bytes. Both **count** and **ratio** start at offset 0.

When writing to the union through the int view and reading through the float view, Java is interpreting the **same bit pattern** under two different types, not performing a numeric conversion. For example, the bit pattern **0x3f800000** of IEEE-754 float **1.0f**:

~~~java
// Fragment: countH and ratioH both originate from the NUMBER layout.
countH.set(segment, 0L, 0x3f800000);
float ratio = (float) ratioH.get(segment, 0L);
// ratio has value 1.0f.
~~~

What is important when modeling C is the **active member**: native code usually has a tag/discriminator indicating when count or ratio is meaningful. A Java layout does not automatically track the active member, and reading a C union member other than the one just written has its own C language/ABI rules. Do not assume this is a portable numeric conversion.

### Union with array

~~~c
union Word {
    int32_t value;
    unsigned char bytes[4];
};
~~~

Java:

~~~java
UnionLayout WORD = MemoryLayout.unionLayout(
        ValueLayout.JAVA_INT.withName("value"),
        MemoryLayout.sequenceLayout(4, ValueLayout.JAVA_BYTE)
                .withName("bytes")
).withName("Word");
~~~

The two members overlap the same four bytes. Whether reading **bytes[0]** gives the high or low byte of value depends on **endianness**, not on the layout name.

### Union size and tail padding

**unionLayout** takes the largest size among the members. However, C **sizeof(union)** can also be rounded up to match alignment when the union is used inside an array/another struct. If the largest member does not give a size that is a multiple of alignment, you must model tail padding explicitly, such as adding a padding member of sufficient size after verifying the ABI. **withByteAlignment** does not add bytes automatically.

## 4. SequenceLayout: C array with fixed stride

C:

~~~c
int32_t samples[5];
~~~

Java:

~~~java
SequenceLayout SAMPLES =
        MemoryLayout.sequenceLayout(5, ValueLayout.JAVA_INT)
                .withName("samples");
~~~

- **elementCount() == 5**.
- **elementLayout().byteSize() == 4**.
- **byteSize() == 20**.
- **byteAlignment() == 4**.
- Element offsets: **0, 4, 8, 12, 16** bytes.

~~~text
element index    0        1        2        3        4
byte offset      0        4        8       12       16
              +--------+--------+--------+--------+--------+
              | int[0] | int[1] | int[2] | int[3] | int[4] |
              +--------+--------+--------+--------+--------+
~~~

**Stride = elementLayout.byteSize()**, not a value Java computes from C sizeof on its own. Therefore, if the element is a struct, you must include **tail padding** matching the C ABI in the StructLayout before building the SequenceLayout.

### Array of structs

~~~c
struct Point {
    int32_t x;
    int32_t y;
};
struct Point points[3];
~~~

Java:

~~~java
StructLayout POINT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
).withName("Point");

SequenceLayout POINTS = MemoryLayout.sequenceLayout(3, POINT)
        .withName("points");
~~~

Point is 8 bytes; POINTS is 24 bytes, with Points starting at bytes 0, 8, and 16. Field **points[1].y** starts at offset **8 + 4 = 12**.

The count of a SequenceLayout cannot be negative; multiplying element count by element byteSize must not overflow. A layout with count **0** is valid for certain dynamic array cases, but does not itself allocate runtime elements.

## 5. Combining all three layouts: a C Table with Row and Payload

Consider C11:

~~~c
#include <stdint.h>

typedef union {
    int32_t count;
    float ratio;
} Payload;

typedef struct {
    uint8_t kind;
    Payload payload;
} Row;

typedef struct {
    int32_t length;
    Row rows[3];
} Table;
~~~

Assume **uint8_t=1 byte**, **int32_t=4 bytes**, **float=4 bytes**, **Payload size/alignment=4**. A common C compiler will lay out:

~~~text
Table, 28 bytes:
  0..3     length
  4..11    rows[0]
  12..19   rows[1]
  20..27   rows[2]

Row, 8 bytes:
  +0       kind
  +1..3    padding
  +4..7    payload union

Payload, 4 bytes:
  +0..3    count or ratio (same bytes)
~~~

Java FFM:

~~~java
UnionLayout PAYLOAD = MemoryLayout.unionLayout(
        ValueLayout.JAVA_INT.withName("count"),
        ValueLayout.JAVA_FLOAT.withName("ratio")
).withName("payload");

StructLayout ROW = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        PAYLOAD
).withName("Row");

SequenceLayout ROWS = MemoryLayout.sequenceLayout(3, ROW)
        .withName("rows");

StructLayout TABLE = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("length"),
        ROWS
).withName("Table");
~~~

The declaration fragments above will be used in the full example in section 7.

| Field | Offset from start of Table |
| --- | ---: |
| length | 0 |
| rows[0].kind | 4 |
| rows[0].payload.count | 8 |
| rows[0].payload.ratio | 8 |
| rows[1].kind | 12 |
| rows[1].payload.count | 16 |
| rows[2].payload.ratio | 24 |

Total size **4 + 3×8 = 28**, alignment 4. Offset **rows[1].payload.count = 4 + 1×8 + 4 = 16**.

## 6. Finding members using layout paths and VarHandle

To access a field inside a struct/union/sequence, use **MemoryLayout.PathElement**.

- **groupElement("name")**: selects the group member tagged with **withName("name")**.
- **groupElement(index)**: selects the member by order, including padding layouts.
- **sequenceElement(1)**: selects a specific sequence element (index 1).
- **sequenceElement()**: open path; when using VarHandle, the index number is passed at invocation time.

### Computing byteOffset

~~~java
import static java.lang.foreign.MemoryLayout.PathElement.*;

long lengthOffset = TABLE.byteOffset(
        groupElement("length"));

long row1CountOffset = TABLE.byteOffset(
        groupElement("rows"),
        sequenceElement(1),
        groupElement("payload"),
        groupElement("count"));
~~~

**lengthOffset=0**, **row1CountOffset=16**. The **byteOffset** call only computes the offset from the layout; it does not read memory.

### Creating VarHandle

~~~java
VarHandle lengthH = TABLE.varHandle(
        groupElement("length"));

VarHandle countH = TABLE.varHandle(
        groupElement("rows"), sequenceElement(),
        groupElement("payload"), groupElement("count"));
~~~

**lengthH** has coordinates **(MemorySegment, long baseOffset)**. **countH** has coordinates **(MemorySegment, long baseOffset, long sequenceIndex)**. When calling set, pass the value at the end:

~~~java
lengthH.set(memory, 0L, 3);
countH.set(memory, 0L, 1L, 42);

int length = (int) lengthH.get(memory, 0L);
int secondCount = (int) countH.get(memory, 0L, 1L);
~~~

This is a fragment requiring **TABLE**, **MemorySegment memory**, and importing **VarHandle**. Base offset **0L** means the segment starts at the beginning of Table. For a segment containing multiple sequential structures, a different base offset can be used when bounds/alignment are valid.

Only a VarHandle whose path ends at a **ValueLayout** has a scalar carrier. Passing the wrong carrier type, number of coordinates, or coordinate order can cause **WrongMethodTypeException**. **JAVA_BYTE** takes byte, **JAVA_INT** takes int, **JAVA_FLOAT** takes float.

## 7. Runnable program: StructLayout + UnionLayout + SequenceLayout

### File LayoutCompositionDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.UnionLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;
import static java.lang.foreign.MemoryLayout.PathElement.sequenceElement;

public class LayoutCompositionDemo {
    static final UnionLayout PAYLOAD = MemoryLayout.unionLayout(
            ValueLayout.JAVA_INT.withName("count"),
            ValueLayout.JAVA_FLOAT.withName("ratio")
    ).withName("payload");

    static final StructLayout ROW = MemoryLayout.structLayout(
            ValueLayout.JAVA_BYTE.withName("kind"),
            MemoryLayout.paddingLayout(3),
            PAYLOAD
    ).withName("Row");

    static final SequenceLayout ROWS =
            MemoryLayout.sequenceLayout(3, ROW).withName("rows");

    static final StructLayout TABLE = MemoryLayout.structLayout(
            ValueLayout.JAVA_INT.withName("length"),
            ROWS
    ).withName("Table");

    static final VarHandle LENGTH =
            TABLE.varHandle(groupElement("length"));
    static final VarHandle KIND =
            TABLE.varHandle(groupElement("rows"),
                    sequenceElement(), groupElement("kind"));
    static final VarHandle COUNT =
            TABLE.varHandle(groupElement("rows"),
                    sequenceElement(), groupElement("payload"),
                    groupElement("count"));
    static final VarHandle RATIO =
            TABLE.varHandle(groupElement("rows"),
                    sequenceElement(), groupElement("payload"),
                    groupElement("ratio"));

    public static void main(String[] args) {
        System.out.println("row size = " + ROW.byteSize());
        System.out.println("row alignment = " + ROW.byteAlignment());
        System.out.println("table size = " + TABLE.byteSize());
        System.out.println("table alignment = " + TABLE.byteAlignment());

        long payloadOffset = ROW.byteOffset(
                groupElement("payload"));
        long secondCountOffset = TABLE.byteOffset(
                groupElement("rows"),
                sequenceElement(1),
                groupElement("payload"),
                groupElement("count"));

        System.out.println("row payload offset = " + payloadOffset);
        System.out.println("row[1] count offset = " + secondCountOffset);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment table = arena.allocate(TABLE);

            LENGTH.set(table, 0L, 3);

            KIND.set(table, 0L, 0L, (byte) 1);
            COUNT.set(table, 0L, 0L, 99);

            KIND.set(table, 0L, 1L, (byte) 2);
            RATIO.set(table, 0L, 1L, 1.5f);

            KIND.set(table, 0L, 2L, (byte) 1);
            COUNT.set(table, 0L, 2L, 5);

            System.out.println("length = "
                    + (int) LENGTH.get(table, 0L));
            System.out.println("row 0 count = "
                    + (int) COUNT.get(table, 0L, 0L));
            System.out.println("row 1 ratio = "
                    + (float) RATIO.get(table, 0L, 1L));
            System.out.println("row 2 count = "
                    + (int) COUNT.get(table, 0L, 2L));

            // IEEE-754 bit pattern of float 1.0f.
            COUNT.set(table, 0L, 2L, 0x3f800000);
            System.out.println("row 2 float view = "
                    + (float) RATIO.get(table, 0L, 2L));
        }
    }
}
~~~

Compile/run with JDK 22+ (no preview flags needed for these APIs):

~~~bash
javac LayoutCompositionDemo.java
java LayoutCompositionDemo
~~~

Stdout:

~~~text
row size = 8
row alignment = 4
table size = 28
table alignment = 4
row payload offset = 4
row[1] count offset = 16
length = 3
row 0 count = 99
row 1 ratio = 1.5
row 2 count = 5
row 2 float view = 1.0
~~~

**Result analysis:**

- **ROW** consists of 1 byte kind, 3 bytes padding, and 4 bytes union: size 8, alignment 4.
- **ROWS** contains 3 ROWs: size 24; **TABLE** contains length 4 + ROWS 24: size 28.
- **row[1].payload.count** has offset 4 + 8 + 4 = 16.
- **COUNT** and **RATIO** read the same bytes. Writing 0x3f800000 and then reading as Java float gives the value 1.0f.
- **Arena.ofConfined** keeps the native allocation alive within try-with-resources; when the block ends, the memory is freed. Layout does not itself change the segment's lifetime.

The example only manipulates memory using Java FFM; no separate native library is required. To use this layout to call a real C library, you must **verify ABI matching**, not just trust the output of the Java program.

## 8. Verifying size, alignment, and offset with a C compiler

Same layout in C, write a standalone C11 program:

### File check_layout.c

~~~c
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef union {
    int32_t count;
    float ratio;
} Payload;

typedef struct {
    uint8_t kind;
    Payload payload;
} Row;

typedef struct {
    int32_t length;
    Row rows[3];
} Table;

int main(void) {
    printf("Payload: size=%zu align=%zu\n",
           sizeof(Payload), _Alignof(Payload));

    printf("Row: size=%zu align=%zu payload=%zu\n",
           sizeof(Row), _Alignof(Row),
           offsetof(Row, payload));

    printf("Table: size=%zu align=%zu rows=%zu\n",
           sizeof(Table), _Alignof(Table),
           offsetof(Table, rows));

    printf("row[1].payload.count offset=%zu\n",
           offsetof(Table, rows)
             + sizeof(Row)
             + offsetof(Row, payload)
             + offsetof(Payload, count));

    return 0;
}
~~~

Compile/run on Linux with a C11 compiler:

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic check_layout.c -o check_layout
./check_layout
~~~

On a typical x86-64 ABI, when Payload/Row/Table meet the assumptions:

~~~text
Payload: size=4 align=4
Row: size=8 align=4 payload=4
Table: size=28 align=4 rows=4
row[1].payload.count offset=16
~~~

This is **ABI-conditional output**, not guaranteed for every compiler, architecture, or packing flag. If C returns different numbers from the Java layout, you must fix the layout, build conditions, or ABI mapping.

You can place **_Static_assert** in the native library to catch ABI changes:

~~~c
/* C11 fragment placed after the declared typedefs. */
_Static_assert(sizeof(Row) == 8, "Row size changed");
_Static_assert(offsetof(Row, payload) == 4,
               "payload offset changed");
_Static_assert(sizeof(Table) == 28, "Table size changed");
~~~

Testing with an actual C compiler is very important because Java does not automatically know which packing, anonymous members, or typedefs the C compiler used when building the native library.

## 9. Why is padding essential for struct arrays?

Try a struct with 5 bytes of data but alignment 4:

~~~c
struct Tail {
    int32_t number;
    unsigned char state;
};
~~~

A typical x86-64 C compiler places number at offsets 0..3, state at offset 4, and then adds 3 bytes of tail padding, making **sizeof(Tail)=8**. An array **Tail[2]** has its second element starting at offset 8. If Java describes only size 5, it will calculate the wrong stride.

Java program demonstrating the alignment rule when creating StructLayout:

### File PaddingCheck.java

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

public class PaddingCheck {
    public static void main(String[] args) {
        try {
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_BYTE,
                    ValueLayout.JAVA_INT);
            System.out.println("unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("misaligned struct rejected");
        }

        StructLayout padded = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE,
                MemoryLayout.paddingLayout(3),
                ValueLayout.JAVA_INT);

        System.out.println("padded size = " + padded.byteSize());
        System.out.println("padded alignment = "
                + padded.byteAlignment());
    }
}
~~~

Save **PaddingCheck.java**, run:

~~~bash
javac PaddingCheck.java
java PaddingCheck
~~~

Stdout:

~~~text
misaligned struct rejected
padded size = 8
padded alignment = 4
~~~

Do not lower alignment on your own to avoid the exception if native does not use a packed struct: that only makes Java accept a potentially wrong layout.

## 10. Mapping C types by ABI: JAVA_LONG is not always C long

C has different data models depending on the operating system:

| C scalar | Notes |
| --- | --- |
| **char** | One C byte; signedness of plain char is implementation-defined |
| **short** | Usually 2 bytes |
| **int** | Usually 4 bytes; Java int is fixed at 4 bytes |
| **long** | Linux x64 LP64 is usually 8 bytes; Windows x64 LLP64 is usually 4 bytes |
| **long long** | Usually 8 bytes |
| **size_t** | Depends on address width/data model |
| **void*** | Address, not the pointed-to data |
| **float/double** | Need to check size, alignment, representation |

Example:

~~~c
struct NativeCounter {
    long count;
    void *data;
};
~~~

Do not assume **JAVA_LONG** is equivalent to C long on Windows x64. FFM **Linker.nativeLinker().canonicalLayouts()** provides scalar type mappings according to the native ABI.

~~~java
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.util.Map;

Map<String, MemoryLayout> canonical =
        Linker.nativeLinker().canonicalLayouts();

MemoryLayout cInt = canonical.get("int");
MemoryLayout cLong = canonical.get("long");
MemoryLayout cSizeT = canonical.get("size_t");
MemoryLayout cPointer = canonical.get("void*");
~~~

This is a fragment, not a standalone program; some linker operations may require native-access configuration depending on the JDK. Do not force a canonical layout to a fixed Java carrier type without verification. The native linker typically guarantees the canonical types **bool, char, short, int, long, long long, float, double, size_t, wchar_t, void***.

**Canonical layouts do not automatically generate padding for structs and unions.** You must inspect the compiler/ABI and synthesize the layout properly. For C aggregates passed **by value** via downcalls, the FunctionDescriptor must also be valid for the calling convention and ABI rules; a layout that reads bytes correctly is not enough to guarantee passing a struct by value is portable.

## 11. Pointer members differ from inline arrays

C:

~~~c
struct BufferPointer {
    int32_t length;
    unsigned char *data;
};

struct BufferInline {
    int32_t length;
    unsigned char data[16];
};
~~~

**BufferPointer.data** is an address value, requiring an **AddressLayout** according to the native pointer ABI. It does not contain the bytes of the target data region inside the struct itself. **BufferInline.data** is 16 bytes residing directly inside the struct, requiring a **SequenceLayout**.

| C Member | How to model | Actual content |
| --- | --- | --- |
| **char *p** | AddressLayout | An address to another region |
| **char p[16]** | sequenceLayout(16, JAVA_BYTE) | 16 inline bytes |
| **struct Row *rows** | AddressLayout, optionally with target layout | Pointer to Row |
| **struct Row rows[3]** | sequenceLayout(3, ROW) | Three inline Rows |

A pointer read from native may be null, dangling, or have unknown bounds; do not dereference untrusted addresses. Having a target layout does not automatically guarantee that the target memory is still alive or has enough bytes.

## 12. Flexible array member with runtime element count

C99 allows:

~~~c
struct Packet {
    int32_t length;
    uint8_t payload[];
};
~~~

The length of payload depends on the allocated instance. You can describe the fixed part and an empty sequence member:

~~~java
StructLayout PACKET = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("length"),
        MemoryLayout.sequenceLayout(0, ValueLayout.JAVA_BYTE)
                .withName("payload")
);
~~~

**sequenceLayout(0, ...)** has size 0; it does not hold runtime data. When receiving an actual segment, you must read length, validate the data, and then create a valid view:

~~~java
long start = PACKET.byteOffset(
        MemoryLayout.PathElement.groupElement("payload"));
long length = Integer.toUnsignedLong(rawLength);

if (start > segment.byteSize()
        || length > segment.byteSize() - start) {
    throw new IllegalArgumentException("invalid payload length");
}

MemorySegment data = segment.asSlice(start, length);
~~~

The snippet above is a fragment, assuming **rawLength** has already been read from the header and **segment** contains the allocated memory region. Checking by subtraction helps avoid overflow from adding offset + length. The C standard also has special padding rules around flexible array members; if you need to map against a real C header, verify **offsetof(payload)** rather than just guessing.

For a struct array whose length is determined at runtime, **MemoryLayout.arrayElementVarHandle(...)** can access elements based on the stride of the element layout without declaring a fixed SequenceLayout count. It is still subject to the bounds of MemorySegment.

## 13. Byte order, unsigned values, and C bitfields

### Endianness

Java **ValueLayout.JAVA_INT** uses the native byte order. If the bytes are a fixed big-endian protocol, you need a layout with an explicit byte order:

~~~java
import java.nio.ByteOrder;
import java.lang.foreign.ValueLayout;

ValueLayout.OfInt NETWORK_INT =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
~~~

This is a fragment. For internal C structs of a native library in the same process, native order according to the ABI is usually used; do not switch to big-endian unless the data definition requires it.

### Unsigned C

Java byte/short/int/long are signed; C also has unsigned. When C stores **uint32_t**, the 4-byte layout of Java int can still represent the bits, but convert to **long** to handle the unsigned value:

~~~java
int raw = -1;  // bit pattern 0xFFFFFFFF
long value = Integer.toUnsignedLong(raw);
System.out.println(value); // 4294967295
~~~

This is a fragment. Do not choose an 8-byte layout just because you want to represent positive uint32_t: C actually only stores 4 bytes.

### Bitfield/enum

C bitfields have allocation/bit-order rules that depend on the compiler and ABI, and cannot be described accurately as ordinary fields in MemoryLayout. C enums also have an underlying type that may depend on compiler flags. Use generated bindings or store verified underlying storage units and process them with masks/shifts; do not assume each bitfield is an independent JAVA_INT.

### Union and reinterpretation

A C union has a tag indicating the active member. A Java **VarHandle** can view bytes under multiple value layouts, but that **does not perform numeric conversion automatically** and does not make all C union type-punning portable.

## 14. Access permissions and lifetime are not in StructLayout

Layout describes byte arrangement, whereas **MemorySegment** enforces:

- **Bounds:** does the segment have enough bytes for the field? Otherwise **IndexOutOfBoundsException**.
- **Alignment:** does the root/member address match byteAlignment? Otherwise potentially **IllegalArgumentException**.
- **Read-only:** cannot set through a read-only segment.
- **Liveness:** once the arena is closed, the native segment is no longer valid, usually **IllegalStateException**.
- **Thread confinement:** a segment from **Arena.ofConfined()** is only for the owner thread; another thread can cause **WrongThreadException**.

**Arena.ofShared()** allows access from multiple threads but does not automatically guarantee data is race-free. Synchronization/happens-before is needed when multiple threads read/write the backing memory concurrently.

You can obtain the offset of a nested layout and call **MemorySegment.asSlice** to pass the exact sub-region to another component. A slice shares bytes with the original segment and does not have an independent allocation or lifetime; a slice must not be used after the owning arena has closed.

## 15. When to use jextract or automated ABI testing?

For a real C header with many typedefs, nested structs, pointers, unions, anonymous members, special alignments, or by-value function signatures, writing all offsets by hand can cause hard-to-detect bugs. Recommended workflow:

1. Identify the exact C header and compiler flags used by the native library.
2. Measure **sizeof**, **_Alignof**, **offsetof** using a C compiler with the same ABI.
3. Query canonical scalar layouts instead of hard-coding variable types.
4. Insert explicit padding, including tail padding.
5. Check byteSize, byteAlignment, byteOffset on the Java side.
6. Test VarHandle and segment on the same dataset with expected values.
7. Run native integration tests on each supported platform.
8. For complex headers, prefer **jextract** to generate FFM bindings and compare output against C measurements.

There is no way for a Java layout to automatically know whether the C compiler enabled packed mode or changed the underlying enum size.

## 16. Common mistakes table

| Mistake | Consequence | Fix |
| --- | --- | --- |
| StructLayout adds padding automatically | Wrong offset or layout creation fails | Add paddingLayout according to ABI |
| Forgetting tail padding | Wrong stride of struct array | Compare sizeof and byteSize |
| Union has two separate regions | Writing one member changes bytes of the other | Use tag, understand overlapping storage |
| Summing sizes of union members | Wrong size | Use max member size, consider ABI rounding |
| Sequence is like Java object array | Wrong storage model | Sequence represents contiguous bytes |
| Using element index as byte offset | Reading wrong position | Compute stride or use VarHandle path |
| groupElement(index) skips padding | Selects wrong member | Use groupElement(name) when possible |
| Always mapping C long to JAVA_LONG | Wrong on Windows LLP64 | canonical layouts + C verification |
| Ignoring pack and ABI | C offset differs from Java | Check compiler flags |
| Reading pointer as inline bytes | Wrong memory/bounds | Use AddressLayout |
| Selecting group instead of ValueLayout in varHandle | No scalar carrier | Path to value or use slice |
| Using after Arena.close() | Accessing expired memory | Manage arena lifecycle |
| Using confined segment on another thread | WrongThreadException | Correct owner thread or shared arena |
| Not testing offsetof | Java runs on its own but C mismatches | Verify with native compiler |
| Using pointer FunctionDescriptor for C by-value struct | Wrong calling convention | ABI-compatible group layout |

## 17. Questions and exercises

**Question 1.** A C struct has a char then an int; why is Java **structLayout(JAVA_BYTE, JAVA_INT)** invalid when int alignment is 4?

**Answer:** Int is at offset 1. StructLayout does not add padding automatically; you must insert 3 bytes or describe a packed ABI matching reality.

**Question 2.** What is the size of a Union consisting of JAVA_INT and JAVA_FLOAT?

**Answer:** 4 bytes and both members have offset 0; do not add them to 8.

**Question 3.** A Sequence consists of 3 Points of size 8. What are the element offsets and total byteSize?

**Answer:** 0, 8, 16; total 24 bytes.

**Question 4.** In the sample Table, at what offset is **rows[2].payload.ratio**?

**Answer:** **4 + 2×8 + 4 = 24** bytes from the start of Table.

**Question 5.** Why does a C struct of int + char usually have size 8 even though total data is only 5 bytes?

**Answer:** Tail padding so that sizeof is a multiple of the struct's alignment, ensuring array stride.

**Question 6.** Can C long on Windows x64 use JAVA_LONG without checking?

**Answer:** No. LLP64 usually has 4-byte C long and 8-byte Java long; use the proper ABI mapping.

**Question 7.** If Java reads the union ratio after C just wrote count, will it get count converted to a float?

**Answer:** No. Java reads the same bit pattern under the float layout; it is not a numeric conversion.

**Question 8.** Does **AddressLayout** for a pointer itself represent the bytes of the pointed-to object?

**Answer:** No. It only describes the address; bounds/lifetime and target data need a separate contract.

**Exercise A:** Change ROW from **kind, padding(3), PAYLOAD** to **PAYLOAD, kind, padding(3)**. Calculate offset of kind (4), payload (0), size (8), alignment (4).

**Exercise B:** Use **MemoryLayout.sequenceLayout(10, ROW)**; calculate the payload offset of Row index 7: **7×8+4=60**.

**Exercise C:** In C, add **_Static_assert(offsetof(Row,payload)==4)** and try a packed compiler mode. Explain when the assert fails.

**Exercise D:** Create a union of int32 and 4 bytes; write the number 0x01020304, observe the byte order, and explain the machine's byte order.

## References

- Java SE 22 — **MemoryLayout**, structLayout, unionLayout, sequenceLayout, paddingLayout, and layout paths: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html
- Java SE 22 — **StructLayout**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/StructLayout.html
- Java SE 22 — **UnionLayout**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/UnionLayout.html
- Java SE 22 — **SequenceLayout**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SequenceLayout.html
- Java SE 22 — **Linker** and C ABI canonical layouts: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
- Oracle Java 22 — **Memory Layouts and Structured Access**: https://docs.oracle.com/en/java/javase/22/core/memory-layouts-and-structured-access.html
- OpenJDK **JEP 454: Foreign Function & Memory API**: https://openjdk.org/jeps/454

**Conclusion:** **StructLayout lays out members sequentially and requires explicit padding; UnionLayout overlaps members; SequenceLayout repeats elements with stride = element byteSize**. When mapping to real C, you must match ABI, sizeof, offsetof, alignment, scalar types, byte order, and lifetime; just having the right layout names is not enough to guarantee interoperability.
