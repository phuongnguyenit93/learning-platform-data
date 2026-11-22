# Creating a VarHandle for Repeatedly Accessed Fields and Elements

## 1. The problem: one layout, thousands of reads and writes

In Java Native Interoperability, especially the **Foreign Function & Memory API (FFM)**, we often receive a native memory region containing structured data: a C `struct`, an array of records, a matrix, or a multi-field buffer. A manual offset read can look simple:

~~~java
// Illustration: each record consists of two ints (x, y), each int takes 4 bytes.
int x = segment.get(ValueLayout.JAVA_INT, i * 8L);
int y = segment.get(ValueLayout.JAVA_INT, i * 8L + 4L);
~~~

However, this approach requires the reader to manually keep **offset, alignment, stride, and data type** in sync. When the record structure changes, a constant `8` or `4` can become wrong. If multiple methods repeat the same access, the addressing logic is duplicated in many places.

**`MemoryLayout.varHandle(...)`** solves this problem: describe the structure **once** using a `MemoryLayout`, specify the **path to the field** using `PathElement`, and then create a **`java.lang.invoke.VarHandle`** to read/write that field repeatedly across different `MemorySegment`s.

For an array of records, `PathElement.sequenceElement()` leaves the **index open at access time**. A single VarHandle can access record 0, record 1, record 2, and so on without recreating the handle in every loop iteration.

~~~text
MemoryLayout describes the structure
        |
        | varHandle(layout path)
        v
VarHandle (created once, with explicit carrier + coordinates)
        |
        +---- get(segment, baseOffset, index)
        +---- set(segment, baseOffset, index, value)
        +---- get(otherSegment, baseOffset, index)
        |
        v
On each use: JVM calculates offset from layout,
checks bounds/lifetime/alignment, and accesses data
~~~

This lesson targets **JDK 22+**, when the FFM API in `java.lang.foreign` became officially stable (JEP 454). The examples only manipulate memory in Java, requiring no C compiler or `--enable-native-access`. On JDK 17, FFM was still in incubator and will **not** compile with the imports/signatures below.

### Learning objectives

- Understand the relationship between `MemoryLayout`, `PathElement`, `MemorySegment`, and `VarHandle`.
- Create handles for a **field** of a `structLayout`, an **element** of a `sequenceLayout`, and a field of each record in an array.
- Distinguish between **fixed paths** and **open paths**; pass the `long` coordinates correctly.
- Write **runnable Java 22+** examples, along with `javac`/`java` commands and deterministic stdout.
- Use `arrayElementVarHandle` for record arrays whose length is determined at runtime, without creating a layout per size.
- Know when to use `byteOffset`, `ValueLayout.varHandle()`, `asSlice`, or `MethodHandles.insertCoordinates`.
- Understand boundary, alignment, scope/thread, and memory ordering checks, and why handles should be cached for reuse.

## 2. Concepts to distinguish

| Component | Role | Example |
| --- | --- | --- |
| `MemoryLayout` | Describes the **shape and byte layout** of data | `structLayout(...)`, `sequenceLayout(...)` |
| `ValueLayout` | A value with a carrier type, size, alignment, and byte order | `ValueLayout.JAVA_INT` (4 bytes, carrier `int`) |
| `MemoryLayout.PathElement` | A step in the path from the root layout to a sub-layout | `groupElement("x")`, `sequenceElement()` |
| `VarHandle` | Strongly typed handle to read/write **a field or a family of positions** | `X.get(segment, 0L, 2L)` |
| `MemorySegment` | View over a memory region with size and scope/lifetime | `arena.allocate(layout)` |
| `Arena` | Allocates and manages the lifecycle of native segments | `Arena.ofConfined()` |

**A VarHandle does not own memory.** It describes *how to access* a position computed from a layout. The `MemorySegment` argument in each `get`/`set` call selects the **specific memory region** to operate on. One handle can be reused for many segments containing the same format.

**A Layout is not memory either.** The line `MemoryLayout.structLayout(...)` only creates structural metadata; only when `arena.allocate(layout)` or another API allocates/provides a `MemorySegment` are there bytes to read/write.

**Do not confuse with VarHandles for Java fields.** `java.lang.invoke.VarHandle` also accesses fields of Java objects or elements of Java arrays. In this lesson, the VarHandle is **derived from an FFM memory layout**, and the first coordinate is always a `MemorySegment`.

### 2.1. Why use a layout instead of calculating offsets manually?

Suppose we have a record:

~~~c
/* Illustrative struct on the native side */
struct Point {
    int32_t x;
    int32_t y;
};
~~~

Assuming a C ABI where `int32_t` takes 4 bytes and the struct has two consecutive fields, the corresponding layout is:

~~~java
StructLayout POINT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));
~~~

`POINT.byteSize()` equals `8`, `POINT.byteOffset(groupElement("x"))` equals `0`, and `POINT.byteOffset(groupElement("y"))` equals `4`. If padding or a new field is added later, update the **layout in one place**; the VarHandles created from the new layout will select the corresponding offsets automatically.

**ABI note:** `MemoryLayout.structLayout` **does not automatically insert padding** according to the C compiler. Java code must accurately describe the actual layout from the C header/ABI, including padding and alignment (see Section 9). Do not assume that matching field names alone guarantees compatibility with every C build.

## 3. Mechanism of `MemoryLayout.varHandle(PathElement...)`

Core API:

~~~java
VarHandle handle = someLayout.varHandle(pathElements...);
~~~

The path must select a final **`ValueLayout`**; if it selects an entire struct or sequence instead of a single value, `varHandle` cannot create the desired value-access handle.

### 3.1. Field in a struct

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

MemoryLayout layout = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        ValueLayout.JAVA_INT.withName("score"));

VarHandle idHandle = layout.varHandle(
        PathElement.groupElement("id"));

VarHandle scoreHandle = layout.varHandle(
        PathElement.groupElement("score"));
~~~

This is a code snippet **placed inside a method**, not a standalone file. `withName("id")` attaches a name to the **member layout**, allowing `groupElement("id")` to find the right field.

The created VarHandle has **carrier type** `int` and two **coordinate types**:

~~~text
(MemorySegment, long) -> int

get(segment, baseOffset)             -> int
set(segment, baseOffset, intValue)    -> void
~~~

`baseOffset` is the offset **in bytes** from the start of the segment; if the data starts at the first byte, pass `0L`. Even when a field has a static offset such as `score` at byte `4`, you **still pass `baseOffset`**; the handle adds the field offset to the base.

### 3.2. Array element: open sequence path

~~~java
SequenceLayout values = MemoryLayout.sequenceLayout(
        4, ValueLayout.JAVA_INT);

VarHandle elementHandle = values.varHandle(
        PathElement.sequenceElement());
~~~

This is a code snippet requiring `SequenceLayout` and `VarHandle` imports; it does not run standalone.

`sequenceElement()` **does not select a specific element** when creating the handle. It creates an *open path element*, so each `get`/`set` call takes an additional **`long` coordinate** for the index:

~~~text
(MemorySegment, long, long) -> int

elementHandle.get(segment, baseOffset, index)
elementHandle.set(segment, baseOffset, index, value)
~~~

For example, `elementHandle.get(segment, 0L, 2L)` accesses element 2 (0-based). The index is not a byte offset. The JVM uses the element layout's size to compute the stride.

### 3.3. Fixed element: closed sequence path

~~~java
VarHandle thirdElement = values.varHandle(
        PathElement.sequenceElement(2));
~~~

Here, element position 2 is **fixed when the handle is created**, so there is **no** `index` coordinate at call time:

~~~text
(MemorySegment, long) -> int

thirdElement.get(segment, 0L)
thirdElement.set(segment, 0L, 99)
~~~

Do not accidentally call `thirdElement.get(segment, 0L, 2L)` as with an open path; the handle's coordinate types have changed.

### 3.4. Two consecutive path elements

To select field `y` in element `i` of a `sequenceLayout` consisting of multiple `Point` structs:

~~~java
VarHandle y = pointsLayout.varHandle(
        PathElement.sequenceElement(),
        PathElement.groupElement("y"));
~~~

The path is read **from outside to inside**:

1. The `sequenceElement()` step goes to a **Point struct with an unspecified index**.
2. The `groupElement("y")` step goes to the **value layout of field y**.
3. On `get`/`set`, pass `MemorySegment`, **byte base offset**, **long index**, and then (if writing) the `int` value.

One handle can be used across multiple loops and multiple segments with a matching layout.

## 4. Runnable Example #1: field VarHandle for a struct

Create the file **`EmployeeLayoutDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

public final class EmployeeLayoutDemo {
    private static final StructLayout EMPLOYEE =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("id"),
                    ValueLayout.JAVA_INT.withName("score"));

    // Declare and reuse; do not create a handle on every access.
    private static final VarHandle ID = EMPLOYEE.varHandle(
            PathElement.groupElement("id"));
    private static final VarHandle SCORE = EMPLOYEE.varHandle(
            PathElement.groupElement("score"));

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = arena.allocate(EMPLOYEE);

            ID.set(record, 0L, 7);
            SCORE.set(record, 0L, 90);

            int oldScore = (int) SCORE.get(record, 0L);
            SCORE.set(record, 0L, oldScore + 5);

            int id = (int) ID.get(record, 0L);
            int score = (int) SCORE.get(record, 0L);

            System.out.println("id=" + id);
            System.out.println("score=" + score);
            System.out.println("bytes=" + EMPLOYEE.byteSize());
            System.out.println("score offset=" + EMPLOYEE.byteOffset(
                    PathElement.groupElement("score")));
        }
    }
}
~~~

Compile/run with **JDK 22 or later**:

~~~bash
javac EmployeeLayoutDemo.java
java EmployeeLayoutDemo
~~~

Stdout:

~~~text
id=7
score=95
bytes=8
score offset=4
~~~

**Why the output is correct:**

- Two consecutive `JAVA_INT`s, each field 4 bytes, layout 8 bytes.
- `ID` selects the field at offset 0; `SCORE` selects offset 4.
- `SCORE` is read, 5 is added, and written back, resulting in 95.
- `arena.allocate(EMPLOYEE)` allocates the exact size/alignment; when the `try` block ends, the native segment becomes invalid.

Here `get` always requires an **`(int)` cast** because `VarHandle.get` is a signature-polymorphic API. `set` takes `int` and a `long` offset. Omitting the cast, passing an `int` index when the handle expects `long`, or choosing a mismatched carrier can trigger `WrongMethodTypeException`. Check `VarHandle.varType()` and `coordinateTypes()` when debugging.

## 5. Runnable Example #2: multiple records, one pair of VarHandles

Create a **sequence layout of three Points** once, each Point having two integer fields `x` and `y`. We create `X` and `Y` **once**; each loop iteration only changes the `index` coordinate.

### 5.1. File `PointsVarHandleDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

public final class PointsVarHandleDemo {
    private static final StructLayout POINT =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("x"),
                    ValueLayout.JAVA_INT.withName("y"));

    private static final SequenceLayout POINTS =
            MemoryLayout.sequenceLayout(3, POINT);

    private static final VarHandle X = POINTS.varHandle(
            PathElement.sequenceElement(),
            PathElement.groupElement("x"));

    private static final VarHandle Y = POINTS.varHandle(
            PathElement.sequenceElement(),
            PathElement.groupElement("y"));

    private static final VarHandle SECOND_Y = POINTS.varHandle(
            PathElement.sequenceElement(1),
            PathElement.groupElement("y"));

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment memory = arena.allocate(POINTS);

            for (long i = 0; i < POINTS.elementCount(); i++) {
                int x = (int) (i + 1);
                int y = x * 10;
                X.set(memory, 0L, i, x);
                Y.set(memory, 0L, i, y);
            }

            for (long i = 0; i < POINTS.elementCount(); i++) {
                int x = (int) X.get(memory, 0L, i);
                int y = (int) Y.get(memory, 0L, i);
                System.out.println(
                        "point[" + i + "]=(" + x + "," + y + ")");
            }

            System.out.println("bytes=" + POINTS.byteSize());
            System.out.println(
                    "second y=" + (int) SECOND_Y.get(memory, 0L));
            System.out.println(
                    "second y offset=" + POINTS.byteOffset(
                            PathElement.sequenceElement(1),
                            PathElement.groupElement("y")));
        }
    }
}
~~~

### 5.2. Compile and run

~~~bash
javac PointsVarHandleDemo.java
java PointsVarHandleDemo
~~~

Stdout:

~~~text
point[0]=(1,10)
point[1]=(2,20)
point[2]=(3,30)
bytes=24
second y=20
second y offset=12
~~~

**Byte layout explanation:**

~~~text
POINT struct: 8 bytes
  x: offset 0, int = 4 bytes
  y: offset 4, int = 4 bytes

POINTS sequence: 3 * 8 = 24 bytes

Index | x offset | y offset
  0   |     0    |     4
  1   |     8    |    12
  2   |    16    |    20
~~~

`X.set(memory, 0L, i, x)` selects `0 + i*8 + 0`. `Y.set(memory, 0L, i, y)` selects `0 + i*8 + 4`. You do **not** need to multiply `i * 8` in Java code using the handle.

**Two ways to select field `y` of record 1:**

- `Y.get(memory, 0L, 1L)`: **open path**, index is passed at access time.
- `SECOND_Y.get(memory, 0L)`: **closed path**, index was fixed when creating the handle.

`POINTS.byteOffset(sequenceElement(1), groupElement("y"))` returns **12** because this path contains only static indices. When you need dynamic offsets for multiple indices, use `byteOffsetHandle(...)` or a VarHandle with an open path; do not call `byteOffset` with an open path expecting it to accept a loop index automatically.

### 5.3. Benefits when processing thousands of elements

In a large loop, constants `POINTS`, `X`, and `Y` should be `static final` (or at least created **outside the loop**). Each iteration only:

1. Computes `i` from the algorithm.
2. Calls `get`/`set` with the same handle.
3. Lets the JVM apply the correct stride and offset from the layout while checking bounds/lifetime.

VarHandles **can be well-optimized by the JIT** in many scenarios, though there is no guarantee they are always faster than `MemorySegment.get`/`set`. Benchmark with JMH and real workloads; the primary benefit first and foremost is **type safety, layout correctness, and maintainability**.

## 6. When the element count is only known at runtime: `arrayElementVarHandle`

`MemoryLayout.sequenceLayout(count, POINT)` works well when **count is available at layout creation time**. However, if you receive an array of records from native code whose count varies continuously, you do not need to create a new sequence layout for every count.

API:

~~~java
VarHandle x = POINT.arrayElementVarHandle(
        PathElement.groupElement("x"));
~~~

It creates a VarHandle that accesses a **contiguous array of elements**, each having layout `POINT`. The handle has coordinates:

~~~text
(MemorySegment, long baseOffset, long elementIndex) -> int
~~~

The key difference: `arrayElementVarHandle` adds an **index coordinate** for the records themselves, even though the root layout is just **a single POINT struct**. The path `groupElement("x")` selects a field **inside one Point**.

### 6.1. Runnable file `VariablePointsDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

public final class VariablePointsDemo {
    private static final StructLayout POINT =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("x"),
                    ValueLayout.JAVA_INT.withName("y"));

    private static final VarHandle X =
            POINT.arrayElementVarHandle(
                    PathElement.groupElement("x"));

    private static final VarHandle Y =
            POINT.arrayElementVarHandle(
                    PathElement.groupElement("y"));

    public static void main(String[] args) {
        final int count = 4;  // May come from runtime input/metadata.

        try (Arena arena = Arena.ofConfined()) {
            long bytes = Math.multiplyExact(
                    POINT.byteSize(), (long) count);

            MemorySegment records = arena.allocate(
                    bytes, POINT.byteAlignment());

            for (long i = 0; i < count; i++) {
                X.set(records, 0L, i, (int) (10 * i));
                Y.set(records, 0L, i, (int) (100 * i));
            }

            long sumX = 0;
            for (long i = 0; i < count; i++) {
                int x = (int) X.get(records, 0L, i);
                int y = (int) Y.get(records, 0L, i);
                sumX += x;
                System.out.println(
                        "item[" + i + "]=" + x + "," + y);
            }
            System.out.println("sumX=" + sumX);
        }
    }
}
~~~

Compile/run:

~~~bash
javac VariablePointsDemo.java
java VariablePointsDemo
~~~

Stdout:

~~~text
item[0]=0,0
item[1]=10,100
item[2]=20,200
item[3]=30,300
sumX=60
~~~

**Why is `arrayElementVarHandle` suitable for long loops?**

- No need to create `sequenceLayout(4, POINT)` if the number of records is only known at runtime.
- One pair of handles `X` and `Y` works for **many different buffers**, as long as the actual memory is laid out like `POINT`.
- The JVM computes the byte offset using `POINT.byteSize()` (here 8), avoiding explicit multiplication in every read/write statement.
- `records.byteSize()` bounds the actual bytes: passing an index whose access exceeds the segment throws **`IndexOutOfBoundsException`**. Application code must still validate count, allocation size, inputs, and integer overflow before calling native code.
- `Math.multiplyExact` rejects overflow when computing total bytes, rather than silently allocating a wrongly sized region.

**Distinguishing the two API groups:**

| API | Root layout | Dynamic coordinates |
| --- | --- | --- |
| `POINTS.varHandle(sequenceElement(), groupElement("x"))` | **SequenceLayout** describing N records | One `long` for sequence index |
| `POINT.arrayElementVarHandle(groupElement("x"))` | **StructLayout** describing one record | One `long` for index of consecutive records |
| `POINT.varHandle(groupElement("x"))` | **StructLayout** describing one record | No index; only base offset |

With `arrayElementVarHandle`, the index is accepted against the **physical bounds** of the segment rather than having a fixed element count from a `SequenceLayout`. A larger segment can hold many records; accessing an index that is **logically** invalid yet still within the buffer is still an application bug, so keep `count` metadata and validate it yourself.

## 7. Multiple nesting levels: struct containing a sequence and 2D sequence

A layout path can traverse multiple levels. That is where VarHandle saves the most offset additions.

### 7.1. Field inside a struct containing a sequence

For example, a record consisting of `header` and `measurements[3]`:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

MemoryLayout packet = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("type"),
        MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT)
                .withName("measurements"));

VarHandle type = packet.varHandle(
        PathElement.groupElement("type"));

VarHandle measure = packet.varHandle(
        PathElement.groupElement("measurements"),
        PathElement.sequenceElement());
~~~

This is a **snippet placed inside a method**, not standalone source. `type` has coordinates `(MemorySegment, long)`; `measure` has `(MemorySegment, long, long)`. When calling `measure.get(segment, 0L, 2L)`, the handle automatically adds the offset of the `measurements` field in `packet` to the stride of the 2nd element.

With `type` at offset 0 and `measurements` at offset 4, each int 4 bytes, the offset of `measurements[2]` is `4 + 2*4 = 12`. You do not need to add these constants manually when using `measure`.

### 7.2. Two-dimensional matrix

~~~java
MemoryLayout matrix = MemoryLayout.sequenceLayout(
        2, MemoryLayout.sequenceLayout(
                3, ValueLayout.JAVA_INT));

VarHandle cell = matrix.varHandle(
        PathElement.sequenceElement(),
        PathElement.sequenceElement());
~~~

This is also a snippet requiring imports for `MemoryLayout`, `ValueLayout`, `VarHandle`, and `PathElement`.

Coordinate signature:

~~~text
(MemorySegment segment, long baseOffset, long row, long col)
    -> int

cell.set(segment, 0L, 1L, 2L, 99)
cell.get(segment, 0L, 1L, 2L)  -> 99
~~~

Note that both `row` and `col` are **`long`** in the VarHandle call. With 2 rows × 3 columns and 4 bytes per int, offset `[1][2]` is `(1*3 + 2)*4 = 20`. The layout avoids manual formulas at call sites.

### 7.3. Field names and member indices

`PathElement.groupElement("name")` relies on `withName("name")` on the member layout. If a group member has no name, `groupElement(long index)` can be used to select by position, though it becomes brittle if the struct changes.

`PathElement.sequenceElement(long index)` fixes the index at handle creation time. `PathElement.sequenceElement()` leaves the index dynamic. `PathElement.sequenceElement(start, step)` represents an open path that transforms positions by a stride; common cases only need the no-argument form.

If a path cannot find a name, exceeds a fixed sequence's bounds, or does not end at a value layout, **`varHandle(...)` may throw `IllegalArgumentException` immediately upon handle creation**. This is distinct from runtime read/write errors.

## 8. `ValueLayout.varHandle()`: accessing primitives by byte offset

Nested layouts are not always needed. When a buffer is just a contiguous array of integers, you can create a handle directly from a value layout:

~~~java
VarHandle intAtOffset = ValueLayout.JAVA_INT.varHandle();

// An int at byte offset 8:
int x = (int) intAtOffset.get(segment, 8L);

// Write an int at byte offset 12:
intAtOffset.set(segment, 12L, 123);
~~~

This is a snippet, not standalone runnable code; import `ValueLayout`/`VarHandle`, and `segment` must be valid, large enough, and aligned.

`ValueLayout.JAVA_INT.varHandle()` returns a handle with coordinates **`(MemorySegment, long)`**, meaning **byte offset**, not element index. If you need element indexing:

- Compute `byteOffset = i * Integer.BYTES` with overflow checking.
- Or use `ValueLayout.JAVA_INT.arrayElementVarHandle()` to take an additional index and compute stride from the layout automatically.
- Or use `MemorySegment.getAtIndex(ValueLayout.JAVA_INT, i)` if you do not need to cache a separate handle.

**Simple rule:** `ValueLayout.varHandle()` for flat data by byte offset; `MemoryLayout.varHandle(path...)` for fields/elements with a structural path; `arrayElementVarHandle` for multiple consecutive records following a record layout.

## 9. Alignment, padding, and C ABI

To read native data correctly, the Java layout must match the C side's **size, offset, alignment, and endianness**. VarHandle gets metadata from the layout; it cannot automatically detect how many padding bytes a C struct actually has.

C example:

~~~c
#include <stdint.h>

struct Tagged {
    uint8_t kind;
    int32_t value;
};
~~~

With a common ABI aligning `int32_t` on a 4-byte boundary, the C compiler places:

~~~text
byte 0: kind (1 byte)
byte 1..3: padding
byte 4..7: value (4 bytes)
sizeof(struct Tagged) = 8
~~~

Java description:

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

StructLayout TAGGED = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value"));

VarHandle VALUE = TAGGED.varHandle(
        PathElement.groupElement("value"));
~~~

**`paddingLayout(3)` is measured in BYTES on JDK 22.** In JDK 22's `structLayout`, the JVM **does not automatically insert padding**. If padding is omitted, offset 1 does not satisfy `JAVA_INT`'s alignment of 4, and creating the struct layout may be rejected with `IllegalArgumentException`.

When mapping from a C library with a different ABI, check `sizeof`, `offsetof`, compiler flags, and actual packing. For instance, `#pragma pack` or a packed network protocol may require a `ValueLayout` with weaker alignment, such as `JAVA_INT_UNALIGNED` or `withByteAlignment(1)`, along with the appropriate byte order via `withOrder(ByteOrder.LITTLE_ENDIAN/BIG_ENDIAN)`. **Do not arbitrarily change alignment to "dodge an exception"** if the native build does not actually have that layout.

Arrays of C structs can also have **tail padding** according to the ABI. When using `arrayElementVarHandle`, the stride is **`POINT.byteSize()`**, so any trailing record padding must be described accurately. Do not guess the stride by summing payload field sizes if the ABI may add padding.

## 10. `byteOffset`, `byteOffsetHandle`, `asSlice`, and VarHandle

The same layout path can be used to create several kinds of operations:

| API | Returns | Use when |
| --- | --- | --- |
| `layout.byteOffset(fixedPath...)` | A `long` offset in bytes | Need a **static offset**, e.g., field `y` in record 1 |
| `layout.byteOffsetHandle(openPath...)` | `MethodHandle` computing offset from dynamic coordinates | Need to **compute the byte offset** of an element rather than read/write it |
| `layout.varHandle(path...)` | `VarHandle` reading/writing the selected value | Repeatedly accessing a field/element |
| `layout.sliceHandle(path...)` | `MethodHandle` creating a view/slice at the path | Need a child `MemorySegment` for further processing |
| `segment.asSlice(offset, size)` | `MemorySegment` view sharing backing memory | Already have a specific offset/size and want to operate on a sub-region |

Example of a static path:

~~~java
long yOffset = POINTS.byteOffset(
        PathElement.sequenceElement(1),
        PathElement.groupElement("y"));
~~~

The result is `12` for an 8-byte Point. If you need the offset of record `i`, you can use a pre-created `byteOffsetHandle`; for normal value access, a **VarHandle with an open sequence path** is more convenient because you do not need to compute the offset into a variable and then call `segment.get`.

### 10.1. Fixing the base offset with `MethodHandles.insertCoordinates`

A VarHandle from a layout always has a `baseOffset` coordinate, even though many applications only use `0L`. You can create an adapter to shorten the call.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

// Assume X is a VarHandle with coordinates:
// (MemorySegment segment, long baseOffset, long index).
VarHandle xAtBaseZero =
        MethodHandles.insertCoordinates(X, 1, 0L);

// The adapter has two remaining coordinates: (MemorySegment, long index).
xAtBaseZero.set(memory, 2L, 123);
int x = (int) xAtBaseZero.get(memory, 2L);
~~~

This is an **illustrative snippet**, requiring variables `X` and `memory` created as in Section 5. Position `1` in `insertCoordinates` refers to the **`baseOffset`** coordinate; `0L` is the value to bind. After adapting, you no longer pass the base offset.

An adapter is suitable when:

- Every access has the same base offset.
- You want a shorter API and less risk of passing `0L` in the wrong position.
- Both the handle and the adapter are cached for reuse, not created per loop iteration.

Do not confuse `MethodHandle` (an operation represented by a callable signature) with `VarHandle` (reading/writing a variable with multiple access modes). `MethodHandles` provides adapters for VarHandles.

## 11. VarHandle and concurrent access: not every operation is atomic

VarHandle supports multiple **access modes**:

- `get` / `set`: ordinary (*plain*) read/write, with weak memory ordering constraints.
- `getOpaque` / `setOpaque`: opaque access.
- `getAcquire` / `setRelease`: acquire/release ordering.
- `getVolatile` / `setVolatile`: volatile ordering.
- `compareAndSet`, `getAndAdd`, `getAndSet`, etc.: atomic update operations when supported by the data type, alignment, and implementation.

**Not every access mode is available for every layout/type.** The specification places restrictions on unaligned layouts, primitive carriers, and access sizes. For example, atomic updates on a properly aligned `int` may be supported, whereas an unaligned layout may disallow certain atomic modes. Use `handle.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` to check capabilities when supporting multiple environments.

### 11.1. Runnable example: multithreaded counter with an aligned VarHandle

File **`AtomicSegmentCounter.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

public final class AtomicSegmentCounter {
    private static final VarHandle COUNTER =
            ValueLayout.JAVA_INT.varHandle();

    public static void main(String[] args)
            throws InterruptedException {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment memory = arena.allocate(
                    ValueLayout.JAVA_INT);

            COUNTER.setVolatile(memory, 0L, 0);

            Runnable increment = () -> {
                for (int i = 0; i < 1_000; i++) {
                    // Get the old value; the increment is atomic.
                    int old = (int) COUNTER.getAndAdd(
                            memory, 0L, 1);
                }
            };

            Thread first = new Thread(increment);
            Thread second = new Thread(increment);

            first.start();
            second.start();

            first.join();
            second.join();

            int result = (int) COUNTER.getVolatile(memory, 0L);
            System.out.println("count=" + result);
        }
    }
}
~~~

Compile/run on **JDK 22+**:

~~~bash
javac AtomicSegmentCounter.java
java AtomicSegmentCounter
~~~

Stdout:

~~~text
count=2000
~~~

Because `ValueLayout.JAVA_INT` has suitable alignment for `int` access, `getAndAdd` performs an atomic update; two threads each increment 1,000 times, so the deterministic result is 2,000. `Arena.ofShared()` allows threads to access the same segment; `join` ensures both finish **before** the arena closes and before `main` reads the result.

**Distinguish two kinds of safety:**

- `Arena.ofShared()`: the segment **can be accessed from multiple threads**; it does not automatically make `x = x + 1` atomic.
- `VarHandle.getAndAdd`: the value update operation itself is atomic with the appropriate access mode, but it does not manage the **lifecycle** of the memory.

A separate `get` + `set` is not equivalent to `getAndAdd` in a multithreaded environment. For layouts requiring packed/unaligned data, check supported access modes and choose proper synchronization or data representation rather than forcing an unsupported atomic mode.

## 12. Memory safety when reusing handles

The same VarHandle can outlive many arenas and segments because it **only holds access information**. That does not keep an old segment valid:

~~~java
// Idea inside a method: HANDLE is pre-created from a layout.
MemorySegment expired;

try (Arena arena = Arena.ofConfined()) {
    expired = arena.allocate(ValueLayout.JAVA_INT);
    // HANDLE.set(expired, 0L, 42);
}

// Arena is closed. Using HANDLE on expired is still invalid.
// HANDLE.get(expired, 0L) -> IllegalStateException.
~~~

This is an illustration of lifetime, not standalone source. The VarHandle remains reusable with **new live segments** that have a matching layout/size.

Error classes to distinguish:

| Issue | Common symptom | Handling principle |
| --- | --- | --- |
| Access past `segment.byteSize()` | `IndexOutOfBoundsException` | Check count, stride, base offset, segment size |
| Using segment after `Arena.close()` | `IllegalStateException` | Do not let segment escape scope; use try-with-resources |
| Using confined segment from another thread | `WrongThreadException` | Access only from owner thread or use a shared arena |
| Offset/address fails alignment | `IllegalArgumentException` | Fix layout/alignment, padding, or actual offset |
| Writing to a read-only segment | `IllegalArgumentException` | Write only to writable segments |
| Wrong carrier/coordinate types in `get`/`set` | `WrongMethodTypeException` | Check `varType()`/`coordinateTypes()`; use `long` for index/offset |
| Unsupported access mode | `UnsupportedOperationException` | Check `isAccessModeSupported` and alignment/carrier |
| Invalid layout path at handle creation | `IllegalArgumentException` | Select a valid group/sequence path to a value layout |
| Segment has bytes but different structure than expected | **May read wrong values without throwing an exception** | Verify ABI, byte order, stride, padding, and schema |

**Important:** A VarHandle **cannot automatically detect** "whether this buffer holds record type A or type B". If both have enough bytes and alignment, it will still read according to layout A that you declared. **Carrier type safety and boundary safety do not replace layout/ABI correctness**.

### 12.1. Raw native pointers still need separate ownership

FFM `MemorySegment` has temporal safety in Java. However, if a C program stores the segment's raw address in a global variable and accesses it after the arena closes, the JVM cannot automatically protect C from a dangling pointer. Native call design must ensure:

1. The segment stays alive throughout the native call/work.
2. If C retains the pointer for async use, the owner must keep the arena alive until C confirms it is no longer used.
3. Do not close a shared arena while a thread/native call is still processing the memory.
4. When copying results to another arena, perform the copy **while both scopes are still alive**; do not merely reassign a Java reference.

## 13. Designing APIs to reuse VarHandles cleanly

A good pattern is to keep the **layout and handles together in one place**, such as a codec class.

~~~java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.invoke.VarHandle;

public final class PointCodec {
    private static final StructLayout LAYOUT =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("x"),
                    ValueLayout.JAVA_INT.withName("y"));

    private static final VarHandle X =
            LAYOUT.varHandle(PathElement.groupElement("x"));

    private static final VarHandle Y =
            LAYOUT.varHandle(PathElement.groupElement("y"));

    private PointCodec() {
    }

    public static long byteSize() {
        return LAYOUT.byteSize();
    }

    public static int x(MemorySegment segment) {
        return (int) X.get(segment, 0L);
    }

    public static int y(MemorySegment segment) {
        return (int) Y.get(segment, 0L);
    }

    public static void set(MemorySegment segment, int x, int y) {
        X.set(segment, 0L, x);
        Y.set(segment, 0L, y);
    }

    public static MemoryLayout layout() {
        return LAYOUT;
    }
}
~~~

This is a **valid Java file** without a `main` method; it can be compiled with `javac PointCodec.java` and used as a library in application code. A caller can do:

~~~java
// Illustration inside a method; import Arena, MemorySegment.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment p = arena.allocate(PointCodec.layout());
    PointCodec.set(p, 3, 4);
    System.out.println(PointCodec.x(p) + PointCodec.y(p)); // 7
}
~~~

**Why is this design maintainable?** All paths, offsets, and carrier types live together with `LAYOUT`. Callers do not need to know that field `y` is at byte 4. When the schema changes, inspect and update the codec instead of hunting for byte-offset additions across the application.

Keep `MemoryLayout` and `VarHandle` as **`static final`** when the layout is fixed. For layouts determined by runtime negotiation, create handles **once per schema version** and cache them by appropriate metadata; do not reuse an old schema's handle on a new schema's buffer.

### 13.1. Should `Arena` be coupled into the codec?

Not by default. A codec specifies **how to access data**, while an arena specifies **who owns it and when to free it**. Separating them allows one codec to be used for:

- Native memory in a per-request confined arena.
- Shared arena for data across multiple threads.
- Heap segment backed by a Java array (if appropriate).
- Buffers passed from a foreign function, with proper lifetime.

Do not close an arena inside the codec if the caller still uses the segment. Also do not keep a global arena just to "keep a VarHandle alive"; a VarHandle does not need a live arena to exist.

## 14. Debugging: check types and coordinates before fixing offsets

When a `get`/`set` call throws `WrongMethodTypeException`, print the handle's signature **outside the hot loop**:

~~~java
System.out.println(X.varType());
System.out.println(X.coordinateTypes());
~~~

For handle `X` in `PointsVarHandleDemo`:

~~~text
int
[interface java.lang.foreign.MemorySegment, long, long]
~~~

This illustrates the **printed format of Java Reflection Class/List in JDK 22**, used for diagnosis; it is not the stdout of the main demo.

Typical mistakes:

- Calling `X.get(segment, 0, 2)` with `int` literals when the handle requires `long`. Use `0L` and `2L` or cast `(long)i`.
- Using `(long) X.get(...)` for a handle with carrier `int`; the expected return type does not match the carrier. Retrieve `(int) X.get(...)` and widen to `long` in Java if needed.
- Trying to call `X.get(segment, 2L)` when `X` still expects both base offset and index.
- Using index `i` when the record layout has different padding from the C ABI, causing values to "step by the wrong stride" without throwing an exception.
- Calling `varHandle(groupElement("name"))` on a field without `withName`.
- Creating a path pointing only to a `StructLayout` or `SequenceLayout` and expecting it to read a scalar; you must select further down to a value field.
- Accessing a Java `int[]` with an FFM VarHandle created from a native struct memory layout without checking assumptions about backing memory/byte order.

A quick check:

~~~text
1) handle.varType()       -> is the data int/long/float/...?
2) handle.coordinateTypes() -> how many arguments are needed, in what order?
3) layout.byteSize()      -> does the buffer have enough bytes?
4) layout.byteAlignment() -> do the buffer/offset have the right alignment?
5) segment.scope().isAlive() -> is the scope still alive?
6) segment.isReadOnly()   -> is writing allowed?
7) do field name / index / byte order / padding match the native ABI?
~~~

This is a **checklist**, not a single combined API call. With a shared arena, the result of `isAlive()` is a snapshot at the moment of checking and does not replace synchronization with a thread that may close the arena.

## 15. Wrong vs. right for repeated access

### Error-prone way: computing offsets manually in every loop

~~~java
// Illustration: Point is 8 bytes, field y is at offset 4.
for (long i = 0; i < count; i++) {
    long offset = i * 8 + 4;
    int y = segment.get(ValueLayout.JAVA_INT, offset);
    consume(y);
}
~~~

This is an illustrative snippet; `consume` is an application method, not standalone source. The problem is that constants `8`/`4` are repeated throughout the code and easily break when the layout changes.

### Better way: create a handle once and use an index

~~~java
VarHandle Y = POINT.arrayElementVarHandle(
        PathElement.groupElement("y"));

// Created outside the loop.
for (long i = 0; i < count; i++) {
    int y = (int) Y.get(segment, 0L, i);
    consume(y);
}
~~~

This is also an illustrative snippet, assuming `POINT`, `segment`, and `consume` are already defined. Advantage: **the schema determines the stride and offset**. If the layout changes, update the layout once.

### When reading only one value, is a VarHandle strictly necessary?

No. `segment.get(ValueLayout.JAVA_INT, knownOffset)` is a short, clear API if the offset/type are already confirmed and the code does not need to process many records/fields. Use a VarHandle when:

- The same field or element must be accessed **many times**.
- Data is nested and manual offset calculation is error-prone.
- You want to encapsulate the layout into a codec.
- You need an access mode such as `getVolatile`, `compareAndSet`, or `getAndAdd` with appropriate alignment/carrier constraints.

VarHandle is a tool to **describe how to access**, not a mandatory rule for every byte.

## 16. Practice questions and answers

**Question 1.** `POINTS` is `sequenceLayout(3, POINT)`, and `POINT` consists of `int x` and `int y`. Why does `POINTS.varHandle(sequenceElement(), groupElement("y"))` require passing both `0L` and `index`?  
**Answer:** The handle takes `baseOffset` to locate the data region within the segment, and `index` because `sequenceElement()` is an open path. Field `y` has offset 4 inside each `Point`.

**Question 2.** How does choosing `sequenceElement(1)` instead of `sequenceElement()` differ?  
**Answer:** Fixed index 1 is encoded when creating the handle; no index is passed anymore. An open path requires a `long index` on `get`/`set`.

**Question 3.** Why does `POINTS.byteOffset(sequenceElement(1), groupElement("y"))` equal `12`?  
**Answer:** Record 1 starts at `1*8 = 8`, field `y` is at `+4`, totaling 12 bytes.

**Question 4.** An array of records has a count known only when calling native code. Which API should you choose?  
**Answer:** Consider `POINT.arrayElementVarHandle(groupElement("x"))`. The handle automatically uses the stride of one `POINT` record, a dynamic index, and the physical bounds of the segment.

**Question 5.** Does `POINT.arrayElementVarHandle(groupElement("x"))` automatically know the logical count of the C data?  
**Answer:** No. It knows the stride from the layout, while the count is provided by application metadata. Ensure the count and segment size match; do not assume how many elements a buffer holds solely from the handle.

**Question 6.** What is `varType()` of a VarHandle created for `JAVA_INT`?  
**Answer:** `int.class`. `get` is typically cast to `int` at the call site; offset/index coordinates require `long` according to the handle type.

**Question 7.** Why can using a `StructLayout` without padding for `char kind; int value;` fail?  
**Answer:** `structLayout` does not automatically align fields. If `value` must be 4-byte aligned yet is at offset 1, the layout is invalid; describe padding accurately according to the C ABI.

**Question 8.** Is it safe to use `Arena.ofConfined()` for a segment and then use a static VarHandle to read from another thread?  
**Answer:** No. The handle can be shared, but **the segment/scope is thread-confined**; accessing from a non-owner thread can throw `WrongThreadException`.

**Question 9.** Can the same VarHandle be reused on a new segment after the old arena has closed?  
**Answer:** Yes, if the new segment is alive and has a matching layout, alignment, and size. The handle does not own/keep alive the backing memory of the old segment.

**Question 10.** Two threads both write `counter = counter + 1` via `get`/`set` on a shared arena. Will the result always equal the total number of increments?  
**Answer:** No. Two separate operations are not an atomic update. With an aligned int and a supported mode, `getAndAdd` is the atomic choice, combined with proper ownership/closing.

**Question 11.** If a `MemorySegment` contains enough bytes but a handle is used for a struct with the wrong ABI, will the JVM always report an error?  
**Answer:** No. If offsets remain within bounds and satisfy alignment, Java may read a wrong value without throwing an exception. Verify `sizeof`, `offsetof`, field types, and byte order.

**Question 12.** What difference does `MethodHandles.insertCoordinates(X, 1, 0L)` make for handle `X` with coordinates `(MemorySegment, long, long)`?  
**Answer:** It fixes `baseOffset` to `0L`, leaving the adapter with only `(MemorySegment, long index)`; suitable when all accesses start from the beginning of the segment.

## 17. Official references

- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): `varHandle`, `arrayElementVarHandle`, layout paths, `byteOffset`, bound/alignment checks.
- [Oracle Java SE 22 — Memory Layouts and Structured Access](https://docs.oracle.com/en/java/javase/22/core/memory-layouts-and-structured-access.html): official example creating VarHandles for a `sequenceLayout` of `x/y` points.
- [Oracle Java SE 22 — MemoryLayout.PathElement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.PathElement.html): group/sequence selectors, open and fixed paths.
- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): carrier, byte alignment/order, and `ValueLayout.varHandle()`.
- [Oracle Java SE 22 — VarHandle](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/VarHandle.html): coordinate types, signature-polymorphic calls, access modes, and atomicity.
- [Oracle Java SE 22 — MethodHandles](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandles.html): `insertCoordinates` and VarHandle adapters.
- [Oracle Java SE 22 — Arena and MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): native allocations, scope, confinement, and lifetime.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM standardization in JDK 22 and motivation for native interoperability.

**Summary:** Create an **ABI-accurate layout** first; from the layout, select a **field or element by path**, create a **VarHandle once**, and then pass `MemorySegment`, `baseOffset`, and the corresponding **`long index`** values when accessing repeatedly. For record arrays of runtime length, use `arrayElementVarHandle`. Handles avoid recalculating offsets and centralize the schema, but **do not replace** checking ownership, scope, threads, bounds, memory ordering, and the contract with native code.
