# Naming Fields and Finding Offsets with MemoryLayout.PathElement

## 1. Practical Problem: At Which Byte Does a Field in a Native Structure Reside?

When exchanging data with a C/C++ library through the **Foreign Function & Memory API (FFM)**, Java needs to know the exact **byte position** of each field in a native structure. Those positions are not always the sum of the byte sizes visible in the declaration: the C compiler may insert **padding** to satisfy **alignment**; a field may also be located inside a nested struct or an array of structs.

With FFM finalized in **JDK 22+** (`java.lang.foreign`), `MemoryLayout` is the data schema, and **`MemoryLayout.PathElement`** is a component of a *structure path* used to:
- select a field by **name** or by **member index**;
- traverse nested structs, unions, and sequences/arrays;
- compute a fixed **byte offset** using `byteOffset(...)`;
- create a **`MethodHandle` for dynamic offset calculation** using `byteOffsetHandle(...)`;
- obtain a sub-layout using `select(...)`, or create a **`VarHandle`** to read/write the selected field.

This lesson focuses on **naming fields and finding offsets with `MemoryLayout.PathElement`** in the context of **Data Layout**. `Arena` and `MemorySegment` are only used to verify offsets with real Java accesses. There is no need to write JNI glue code or call native C functions to run the main practice lesson.

**Version requirement:** The complete sample compiles with `javac --release 22` and runs on JDK 22+; tested on JDK 24. Do not use this source as-is on JDK 17: FFM in JDK 17 is an incubator API with different packages and signatures. Code snippets explicitly marked as *fragment* are illustrative examples inside a valid method/block, not standalone files.

After completing this lesson, you will be able to explain:
1. `withName("field")` attaches a name to a **layout**, without creating a Java field or allocating memory.
2. `groupElement("name")` selects a field of a group; `sequenceElement(index)` selects an array element.
3. Why a field's offset may differ from the size of the preceding fields.
4. How to find the offset of a field nested inside structs and arrays using **a single path**.
5. How to distinguish `byteOffset`, `select`, `byteOffsetHandle`, and `varHandle`, especially **fixed** versus **open sequence paths**.
6. Typical errors: missing/wrong name, wrong index number, confusing byte offset with array index, omitting the base offset when using handles, wrong padding/ABI, and using a segment after the arena is closed.

## 2. Foundation: MemoryLayout Describes Bytes, Not Values

`MemoryLayout` represents an immutable data structure. Some commonly used factories:

~~~java
// Java JDK 22+ fragments, placed inside a valid method/block.
MemoryLayout oneInt = ValueLayout.JAVA_INT; // 4 bytes.
MemoryLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));
MemoryLayout threePoints = MemoryLayout.sequenceLayout(3, point);
~~~

| Layout Type | Meaning | Next Path Element That Can Be Used |
|---|---|---|
| `ValueLayout` | A single primitive/address value: int, byte, long, pointer... | Usually the endpoint when using `varHandle` |
| `StructLayout` | Sequential members with byte offsets | `groupElement("name")` or `groupElement(index)` |
| `UnionLayout` | Members overlapping at the same starting position | `groupElement(...)`; member offsets usually start at 0 |
| `SequenceLayout` | N contiguous elements, each with the same layout | `sequenceElement(index)` or `sequenceElement()` |
| `PaddingLayout` | Skipped bytes to satisfy layout requirements | Not a business field to be read/written |

A layout such as `point` above holds a **two-field schema** but does not hold any specific x/y coordinates. To have bytes, Java must be allocated a `MemorySegment` with compatible capacity and alignment:

~~~java
// Fragment, requires import java.lang.foreign.*.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment pointBytes = arena.allocate(point);
    // With this segment, Java now has real memory to write x/y.
}
~~~

Keep three questions separate:
- **Layout**: “how *should* the data *be interpreted*?”
- **PathElement**: “from the root layout, *which branch should be followed* to select the field?”
- **Segment**: “*in which real memory region* is the data read/written, and is it still alive?”

`MemoryLayout.byteSize()`, `byteAlignment()`, and `byteOffset(...)` let you reason about the schema **without allocating memory**. Calculating an offset does not create a native pointer by itself.

## 3. Naming Fields Properly: withName and name

Attach a name right when creating a member layout:

~~~java
MemoryLayout person = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        ValueLayout.JAVA_LONG.withName("score"));
~~~

`withName("id")` creates **a new layout with a name**. It **does not mutate** the Java variable holding the old layout and **does not add a Java class field**. The underlying data type remains `ValueLayout.JAVA_INT`; the name is metadata so `PathElement.groupElement("id")` can find the right member by name.

~~~java
// Conceptually standalone fragment.
MemoryLayout unnamed = ValueLayout.JAVA_INT;
MemoryLayout named = unnamed.withName("count");

System.out.println(unnamed.name().isPresent()); // false
System.out.println(named.name().orElseThrow());  // count
~~~

`MemoryLayout.name()` returns `Optional<String>`, because **not every layout has a name**. Padding layouts and unnamed root layouts may have no name metadata.

### Naming Nested Groups and Sequences

~~~java
MemoryLayout header = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("count"))
        .withName("header");

MemoryLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y"));

MemoryLayout record = MemoryLayout.structLayout(
        header,
        MemoryLayout.sequenceLayout(3, point).withName("points"),
        ValueLayout.JAVA_INT.withName("checksum"));
~~~

In the root `record`:
- `header` is a group **named "header"**, containing fields named "kind"/"count".
- `points` is a **sequence named "points"**, where each element is a `point`-type group with fields "x"/"y".
- `checksum` is a field at the root.
- The 3-byte padding in `header` is a member layout to push the `count` field to offset 4; it is **not** a named data field.

**Good practice:** choose names that are **unique within each group** and follow the C header/ABI schema. Two different groups can share the same field name (for example `header.count` and `footer.count`) because the path distinguishes them via the parent group name. If duplicate names are placed in **the same group**, lookup by name becomes hard to read/maintain; do not rely on an implicit selection to disambiguate.

### Layout Name ≠ C Symbol ≠ Java Reflection

`withName("count")` is the name of **a member in the memory layout**, not:
- Java reflection `Class.getDeclaredField("count")`;
- an exported symbol name used by `SymbolLookup`;
- a C/JNI variable name that can be automatically looked up from a header;
- a guarantee that the real C compiler places the field at the offset Java expects.

Naming is the first step toward **clear structural calculation**. Matching the native ABI still requires verifying `sizeof`/`offsetof`, alignment, byte order, and compiler packing.

## 4. MemoryLayout.PathElement: Steps in the Layout Tree

`MemoryLayout.PathElement` is a nested interface of `MemoryLayout`. A path consists of one or more **path elements**, applied sequentially from the root to the target field.

| `PathElement` Factory | Used When Current Layout Is | Meaning |
|---|---|---|
| `groupElement("name")` | `StructLayout` or `UnionLayout` | Selects a member in the group by name |
| `groupElement(long index)` | `StructLayout` or `UnionLayout` | Selects a member by position, **zero-based** |
| `sequenceElement(long index)` | `SequenceLayout` | Selects an array element at a **fixed** index |
| `sequenceElement()` | `SequenceLayout` | Selects an unspecified element: **open path**, index passed when using the handle |
| `sequenceElement(long start, long step)` | `SequenceLayout` | A form of **open path** for an index sequence by formula; use only when you understand the stride |
| `dereferenceElement()` | `AddressLayout` with a target layout | Follows the pointer through the target layout; must ensure pointer/memory validity |

This lesson uses the first four factories; `dereferenceElement()` is an advanced topic because it deals with pointer targets and native memory lifetime. Do **not** confuse `groupElement(index)` with `sequenceElement(index)`:
- Group index is **the member position in a struct/union**, including padding layouts.
- Sequence index is **the element position in an array**, where each element has a stride equal to the element layout's size.

### Paths Always Go from Outside In

Suppose you want the `y` field of element `points[2]` in `record`. The sequence:

~~~text
record (struct)
  |
  +-- groupElement("points") --> points (sequence of 3 point structs)
                                  |
                                  +-- sequenceElement(2) --> point #2 (struct)
                                                               |
                                                               +-- groupElement("y") --> int32
~~~

Java syntax:

~~~java
// Fragment: record is the MemoryLayout in section 3.
long offset = record.byteOffset(
        MemoryLayout.PathElement.groupElement("points"),
        MemoryLayout.PathElement.sequenceElement(2),
        MemoryLayout.PathElement.groupElement("y"));
~~~

Swapping two steps is wrong: after selecting `groupElement("points")`, the current layout is a **sequence**, so you cannot call `groupElement("y")` directly yet. You must select **a sequence element** first, and then enter the "y" member of the element struct.

### Concise Import Syntax

If you have the following import at the top of the Java file:

~~~java
import static java.lang.foreign.MemoryLayout.PathElement.*;
~~~

then you can write `groupElement("points")`, `sequenceElement(2)`, `groupElement("y")` without repeating the class name. This is only a static import of the **factory methods**; it does not change semantics.

## 5. Read the Byte Map Before Coding: Record Example with header and points

With the same root layout from section 3:

~~~text
Record (36 bytes, illustrating int32 align=4)
Offset (byte)       Data                 Size
0                   header.kind          1
1..3                padding              3
4..7                header.count         4
8..11               points[0].x          4
12..15              points[0].y          4
16..19              points[1].x          4
20..23              points[1].y          4
24..27              points[2].x          4
28..31              points[2].y          4
32..35              checksum             4
~~~

From this:

| Path from Root | Offset in Bytes | Interpretation |
|---|---:|---|
| `groupElement("header")` | 0 | Header starts right at the beginning of record |
| `groupElement("header"), groupElement("kind")` | 0 | First byte |
| `groupElement("header"), groupElement("count")` | 4 | Skips kind (1) + padding (3) |
| `groupElement("points")` | 8 | Array starts after the 8-byte header |
| `groupElement("points"), sequenceElement(0), groupElement("x")` | 8 | Element 0 starts at 8 |
| `groupElement("points"), sequenceElement(0), groupElement("y")` | 12 | y of element 0 |
| `groupElement("points"), sequenceElement(1), groupElement("y")` | 20 | 8 + 1×8 + 4 |
| `groupElement("points"), sequenceElement(2), groupElement("y")` | 28 | 8 + 2×8 + 4 |
| `groupElement("checksum")` | 32 | After three Points, each Point 8 bytes |

Formula in a layout with a fixed-size array:

\[
\operatorname{offset}(\mathrm{points}[i].y)
  = \operatorname{offset}(\mathrm{points}) + i \cdot \operatorname{sizeof}(\mathrm{Point}) + \operatorname{offset}(\mathrm{Point.y})
  = 8 + 8i + 4.
\]

With `i=2`, the result is **28**. However, **do not hardcode 8 and 4** when `PathElement` is available: the design becomes brittle if you add a field to header, change the Point layout, update padding, or switch ABI.

### Why Not Naively Add Up Type Sizes?

If you omit `MemoryLayout.paddingLayout(3)` in header, `count` is not at offset 4. On JDK 22+, `structLayout` **does not automatically insert padding** for field alignment; a structure with misaligned fields may be rejected when creating the layout. Manually describing a native struct requires understanding **size, alignment, packing, and tail padding** of the actual ABI, not just looking at the C declaration and concatenating fields.

A C struct with `uint8_t kind` and `int32_t count` fields typically has `count` placed at offset 4 by the C compiler, but **do not generalize that to every compiler/flag/platform**. When connecting to real native code, verify with C `offsetof`, `sizeof`, and `_Alignof` instead of treating this table as a cross-ABI truth.

## 6. byteOffset(...): Finding a Fixed Position Without Allocation

`record.byteOffset(path...)` returns a **`long`**, which is the byte offset **relative to byte 0 of the root layout itself**. It is not a raw address/pointer and does not reference where memory is allocated.

~~~java
// Fragments: record is the defined MemoryLayout.
long countOffset = record.byteOffset(
        groupElement("header"), groupElement("count"));  // 4

long firstYOffset = record.byteOffset(
        groupElement("points"), sequenceElement(0),
        groupElement("y"));                              // 12

long thirdYOffset = record.byteOffset(
        groupElement("points"), sequenceElement(2),
        groupElement("y"));                              // 28

long checksumOffset = record.byteOffset(
        groupElement("checksum"));                      // 32
~~~

**Important condition:** `byteOffset` requires a path that identifies **an exact single position**. Therefore:
- `sequenceElement(2)` is a **fixed/bound path element**, usable to query the offset of element 2.
- `sequenceElement()` is an **open path element**, with no known index yet; it **must not** be passed directly to `byteOffset(...)`. The API throws `IllegalArgumentException`.
- `dereferenceElement()` has its target at wherever the runtime pointer points; `byteOffset(...)` cannot be used for paths containing a dereference element.

Do not confuse them:

~~~java
long bad = record.byteOffset(
        groupElement("points"),
        sequenceElement(),
        groupElement("y")); // Wrong: open sequence path, throws IllegalArgumentException.
~~~

Use `byteOffsetHandle(...)` if you want to compute offsets for **multiple different indices at runtime**, instead of calling `byteOffset` with an “unbound” index.

### A Sublayout's Offset Differs from a Field's Offset from the Root

~~~java
MemoryLayout header = record.select(groupElement("header"));
long countInsideHeader = header.byteOffset(groupElement("count")); // 4

long countInsideRecord = record.byteOffset(
        groupElement("header"), groupElement("count"));           // 4
~~~

In this example, `header` is at byte 0, so both numbers are 4. If `header` started at byte 16 in a larger root, the offset relative to **header** would still be 4, while the offset relative to **root** would be 20. Therefore, **always be explicit about the root layout** and avoid accidentally adding an offset that was already computed from the root a second time.

## 7. select(...): Selecting a Field's Layout Type, Not Querying an Element Position

`select(PathElement...)` returns the **`MemoryLayout` of the selected field**, allowing you to inspect `name()`, `byteSize()`, `byteAlignment()`, or use it as type information. It does **not** return a byte offset.

Example:

~~~java
MemoryLayout selected = record.select(
        groupElement("points"),
        sequenceElement(),
        groupElement("y"));

System.out.println(selected.name().orElse("<unnamed>")); // y
System.out.println(selected.byteSize());                 // 4
~~~

**An often-overlooked detail to remember:** in JDK 22+:
- `select(...)` allows an **open sequence element** (`sequenceElement()`) to obtain the *element layout* in general, regardless of index.
- `select(...)` **does not allow a fixed-index sequence path** such as `sequenceElement(1)`. Using it throws `IllegalArgumentException`, because *selecting a layout type* does not need to bind an element index.
- `select(...)` also rejects dereference paths.

This looks like the opposite of `byteOffset(...)`, but it makes complete sense when separating the needs:

| What You Want to Know | API | Example Sequence Selection |
|---|---|---|
| **At which byte does the field of element 2 reside?** | `byteOffset(...)` | `sequenceElement(2)` |
| **What layout does field y of every element belong to?** | `select(...)` | `sequenceElement()` |
| **Compute offset by an index passed at runtime?** | `byteOffsetHandle(...)` | `sequenceElement()` |
| **Read/write y of runtime element i?** | `varHandle(...)` | `sequenceElement()` |

**Do not write `select(...sequenceElement(2)...)` and then report “PathElement is broken”;** choose `sequenceElement()` when querying a layout, or switch to `byteOffset` when querying a fixed element's position.

## 8. byteOffsetHandle(...): Dynamic Offsets with Base and Index

When a loop needs the offset of `points[i].y` for many `i`, `byteOffsetHandle(...)` creates a `java.lang.invoke.MethodHandle` that accepts `long` parameters at runtime.

~~~java
import java.lang.invoke.MethodHandle;
// record is the root MemoryLayout; with static import PathElement.*.
MethodHandle yOffset = record.byteOffsetHandle(
        groupElement("points"),
        sequenceElement(),
        groupElement("y"));
~~~

**Important signature:** the returned handle always has:
1. **A first `long` parameter as the base offset**.
2. **One additional `long` parameter for each open path element** in the order they appear in the path.
3. **Return type `long`**, which is the offset in bytes.

In the example with exactly **one open sequence element**, the method handle has the corresponding Java method type **`(long base, long index)long`**:

~~~java
long a = (long) yOffset.invokeExact(0L, 0L);  // 12
long b = (long) yOffset.invokeExact(0L, 1L);  // 20
long c = (long) yOffset.invokeExact(0L, 2L);  // 28

long shifted = (long) yOffset.invokeExact(100L, 2L); // 128
~~~

The `base` parameter lets you reuse the layout in a buffer containing multiple records, or compute from a different starting position. However, the base offset **does not by itself prove the memory region has enough data** — this is offset arithmetic; when reading/writing on a `MemorySegment`, bounds/lifetime must be respected.

### Two Open Sequences

If a layout has two nested sequences, such as a 2×3 matrix of `JAVA_INT`:

~~~java
MemoryLayout matrix = MemoryLayout.sequenceLayout(
        2, MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT));
MethodHandle cellOffset = matrix.byteOffsetHandle(
        sequenceElement(), sequenceElement());
long addressWithinMatrix =
        (long) cellOffset.invokeExact(0L, 1L, 2L); // (1*3 + 2)*4 = 20
~~~

This handle has **three `long` inputs**: base, outer index, inner index. The index order corresponds to **the order of open elements in the path**, not arbitrary variable names. When using `invokeExact`, both the argument count and primitive types must **match the method type exactly**; passing `int` instead of `long` can lead to `WrongMethodTypeException`.

### How byteOffsetHandle Differs from byteOffset

For a fixed path, `byteOffset` immediately computes a `long` number; no handle is needed. For an open path, `byteOffsetHandle` lets you defer the index until runtime. Create the handle once and reuse it inside loops; avoid rebuilding layouts/paths every time just to read a field.

## 9. varHandle(...): Using PathElement to Read/Write Real Data

`MemoryLayout.varHandle(path...)` only creates a VarHandle when the path selects an appropriate **ValueLayout**. If the path ends at an entire struct or sequence, Java cannot be assumed to have a primitive carrier for that whole block.

To access `count` and `points[i].y`:

~~~java
import java.lang.invoke.VarHandle;

VarHandle count = record.varHandle(
        groupElement("header"), groupElement("count"));

VarHandle y = record.varHandle(
        groupElement("points"), sequenceElement(),
        groupElement("y"));
~~~

- `count` has coordinates **`(MemorySegment, long base)`**, carrier `int`.
- `y` has coordinates **`(MemorySegment, long base, long index)`**, carrier `int`.
- `long base` is a mandatory coordinate in the JDK 22 API; it is not automatically omitted just because you always use offset 0.
- You can use `VarHandle.toMethodHandle(...)` and adapters when composition is needed, but this lesson uses simple `get/set`.

Reading/writing inside an arena:

~~~java
// Fragment: recordLayout is the layout, arena is alive, segment has the right capacity.
MemorySegment memory = arena.allocate(record);

count.set(memory, 0L, 3);          // Set header.count = 3.
y.set(memory, 0L, 0L, 11);         // points[0].y = 11.
y.set(memory, 0L, 1L, 22);         // points[1].y = 22.
y.set(memory, 0L, 2L, 33);         // points[2].y = 33.

int value = (int) y.get(memory, 0L, 2L); // 33
~~~

The `0L` argument is the base offset, and `2L` is the index of the open sequence path. If you write `y.get(memory, 2L)`, you are **not** selecting element 2: the call is missing a coordinate and can cause `WrongMethodTypeException`. If you use `byteOffset(...)` to get the fixed offset of `points[2].y`, you can read it with `memory.get(ValueLayout.JAVA_INT, offset)`, whereas when already using a VarHandle, the path is clearer for looping code.

### From Layout to Offset and Then Reading with MemorySegment.get

The two access approaches are equivalent in position:

~~~java
long off = record.byteOffset(
        groupElement("points"), sequenceElement(2), groupElement("y"));
int fromOffset = memory.get(ValueLayout.JAVA_INT, off);

VarHandle pointY = record.varHandle(
        groupElement("points"), sequenceElement(), groupElement("y"));
int fromHandle = (int) pointY.get(memory, 0L, 2L);
~~~

If the layout/byte order/type are identical and memory is valid, both values are `points[2].y`. `byteOffset` gives a byte offset number; `varHandle` combines layout, path, carrier, and offset arithmetic into an operational view.

### Access Must Be Valid Across Multiple Dimensions

A VarHandle from `MemoryLayout` must still obey:
- **spatial bounds** of the `MemorySegment`;
- **temporal lifetime** of the arena;
- **thread confinement** or sharing rules;
- **alignment** of the layout/address being accessed;
- read/write permissions of the segment.

A “syntactically valid” layout path does not magically make memory larger, and a Java VarHandle does not prevent other C code from using a bad pointer.

## 10. Complete Program (JDK 22+): Fixed Offsets, Dynamic Offsets, Names, and Errors

The program below is a **standalone compilable/runnable** Java file using only unrestricted FFM memory APIs without native downcalls. No C compiler, JNI headers, `System.loadLibrary`, or `--enable-native-access` is needed for the operations used.

### 10.1. Create the file LayoutPathLesson.java

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;
import java.util.Arrays;

import static java.lang.foreign.MemoryLayout.PathElement.*;

public final class LayoutPathLesson {
    private static final MemoryLayout POINT = MemoryLayout.structLayout(
            ValueLayout.JAVA_INT.withName("x"),
            ValueLayout.JAVA_INT.withName("y"));

    private static final MemoryLayout HEADER = MemoryLayout.structLayout(
            ValueLayout.JAVA_BYTE.withName("kind"),
            MemoryLayout.paddingLayout(3),
            ValueLayout.JAVA_INT.withName("count")).withName("header");

    private static final MemoryLayout RECORD = MemoryLayout.structLayout(
            HEADER,
            MemoryLayout.sequenceLayout(3, POINT).withName("points"),
            ValueLayout.JAVA_INT.withName("checksum"));

    public static void main(String[] args) throws Throwable {
        long countOffset = RECORD.byteOffset(
                groupElement("header"), groupElement("count"));
        long firstYOffset = RECORD.byteOffset(
                groupElement("points"), sequenceElement(0), groupElement("y"));
        long thirdYOffset = RECORD.byteOffset(
                groupElement("points"), sequenceElement(2), groupElement("y"));
        long checksumOffset = RECORD.byteOffset(groupElement("checksum"));

        MethodHandle offset = RECORD.byteOffsetHandle(
                groupElement("points"), sequenceElement(), groupElement("y"));
        long computedThirdYOffset = (long) offset.invokeExact(0L, 2L);
        if (computedThirdYOffset != thirdYOffset) {
            throw new AssertionError("Offset mismatch");
        }

        VarHandle count = RECORD.varHandle(
                groupElement("header"), groupElement("count"));
        VarHandle y = RECORD.varHandle(
                groupElement("points"), sequenceElement(), groupElement("y"));

        System.out.println("recordBytes=" + RECORD.byteSize());
        System.out.println("countOffset=" + countOffset);
        System.out.println("firstYOffset=" + firstYOffset);
        System.out.println("thirdYOffset=" + thirdYOffset);
        System.out.println("checksumOffset=" + checksumOffset);

        MemorySegment expired;
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = arena.allocate(RECORD);
            record.set(ValueLayout.JAVA_BYTE, 0L, (byte) 7);
            count.set(record, 0L, 3);
            y.set(record, 0L, 0L, 11);
            y.set(record, 0L, 1L, 22);
            y.set(record, 0L, 2L, 33);
            record.set(ValueLayout.JAVA_INT, checksumOffset, 66);

            int[] ys = {
                    (int) y.get(record, 0L, 0L),
                    (int) y.get(record, 0L, 1L),
                    (int) y.get(record, 0L, 2L)
            };
            System.out.println("kind=" + record.get(ValueLayout.JAVA_BYTE, 0L));
            System.out.println("count=" + count.get(record, 0L));
            System.out.println("pointsY=" + Arrays.toString(ys));
            System.out.println("checksum=" + record.get(
                    ValueLayout.JAVA_INT, checksumOffset));

            MemoryLayout selected = RECORD.select(
                    groupElement("points"),
                    sequenceElement(),
                    groupElement("y"));
            System.out.println("selected=" + selected.name().orElse("<unnamed>")
                    + ":" + selected.byteSize());

            try {
                RECORD.byteOffset(
                        groupElement("points"),
                        sequenceElement(),
                        groupElement("y"));
                throw new AssertionError("Expected open-path error");
            } catch (IllegalArgumentException expected) {
                System.out.println("openPathOffset=IllegalArgumentException");
            }

            try {
                RECORD.select(
                        groupElement("points"),
                        sequenceElement(1),
                        groupElement("y"));
                throw new AssertionError("Expected fixed-select error");
            } catch (IllegalArgumentException expected) {
                System.out.println("fixedIndexSelect=IllegalArgumentException");
            }

            try {
                RECORD.byteOffset(groupElement("missing"));
                throw new AssertionError("Expected missing-field error");
            } catch (IllegalArgumentException expected) {
                System.out.println("missingName=IllegalArgumentException");
            }

            expired = record;
        }

        try {
            count.get(expired, 0L);
            throw new AssertionError("Expected closed-arena failure");
        } catch (IllegalStateException expected) {
            System.out.println("afterClose=IllegalStateException");
        }

        System.out.println("RESULT: PASS");
    }
}
~~~

**This is complete code**, with no package. Keep the class name `LayoutPathLesson` and file `LayoutPathLesson.java` as-is; `POINT/HEADER/RECORD` are immutable and reusable layout descriptions.

### 10.2. Compile and Run

**Linux/macOS (shell):**

~~~sh
mkdir -p out
javac --release 22 -d out LayoutPathLesson.java
java -cp out LayoutPathLesson
~~~

**Windows (PowerShell):**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 22 -d out LayoutPathLesson.java
java -cp out LayoutPathLesson
~~~

**Windows CMD** (in a directory without `out` yet):

~~~bat
mkdir out
javac --release 22 -d out LayoutPathLesson.java
java -cp out LayoutPathLesson
~~~

If `out` already exists, you do not need to recreate it. The example only uses native memory allocation via `Arena` and normal layout access; `--enable-preview` is **not needed** since FFM was finalized in JDK 22, and `--enable-native-access` is **not needed** because there are no restricted downcalls or library loading. Those flags have different purposes in lessons on calling native functions.

### 10.3. Exact Verified Stdout

~~~text
recordBytes=36
countOffset=4
firstYOffset=12
thirdYOffset=28
checksumOffset=32
kind=7
count=3
pointsY=[11, 22, 33]
checksum=66
selected=y:4
openPathOffset=IllegalArgumentException
fixedIndexSelect=IllegalArgumentException
missingName=IllegalArgumentException
afterClose=IllegalStateException
RESULT: PASS
~~~

The output was verified using **JDK 24 on Windows x64**, with `javac --release 22` followed by `java -cp out LayoutPathLesson`. The numeric lines depend only on the chosen layout; they do not depend on raw native addresses, hash codes, or GC timing.

### 10.4. Reading the Results by Responsibility

- `recordBytes=36`: one 8-byte Header + three Points × 8 bytes + 4-byte checksum.
- `countOffset=4`: the `count` field follows the 1-byte `kind` and 3-byte padding.
- `firstYOffset=12` and `thirdYOffset=28`: `points` starts at byte 8, Point has stride 8, and field `y` has offset 4 inside Point.
- `computedThirdYOffset` is checked using `byteOffsetHandle`; if it does not equal the fixed offset, the code throws an `AssertionError` before printing `PASS`.
- `pointsY=[11, 22, 33]` confirms the open-sequence VarHandle reads each element accurately with the right number of coordinates.
- `selected=y:4` demonstrates `select` picks **the layout of field y** with name `y` and size 4.
- The three `IllegalArgumentException` lines are **intentional** error cases, not broken tests: an open path is invalid for `byteOffset`; a bound index is invalid for `select`; and a non-existent field name.
- `afterClose=IllegalStateException` is an intentional attempt to access via VarHandle after the arena has closed; it proves a valid layout **does not** bypass memory lifetime.

## 11. Mapping to a Real C Struct: PathElement Does Not Understand the ABI on Its Own

Java `structLayout` describes **the bytes you specify**. If a native library has a C struct:

~~~c
/* C declaration: verify the ABI before sharing memory with Java. */
#include <stdint.h>

struct Header {
    uint8_t kind;
    int32_t count;
};
struct Point {
    int32_t x;
    int32_t y;
};
struct Record {
    struct Header header;
    struct Point points[3];
    int32_t checksum;
};
~~~

On a **common ABI** with alignment 4 for `int32_t`, the C compiler typically produces:

~~~text
sizeof(Header) = 8
offsetof(Header, count) = 4
sizeof(Point) = 8
offsetof(Point, y) = 4
offsetof(Record, points) = 8
offsetof(Record, checksum) = 32
sizeof(Record) = 36
~~~

These are **values that must be confirmed on the actual compiler/architecture**, not defaults across every C implementation. You can add compile-time assertions in a C file to verify:

~~~c
/* C fragment must be placed with the struct declarations above. */
#include <stddef.h>

_Static_assert(sizeof(struct Header) == 8, "Header ABI mismatch");
_Static_assert(offsetof(struct Header, count) == 4, "count offset");
_Static_assert(sizeof(struct Point) == 8, "Point ABI mismatch");
_Static_assert(offsetof(struct Point, y) == 4, "y offset");
_Static_assert(offsetof(struct Record, points) == 8, "points offset");
_Static_assert(offsetof(struct Record, checksum) == 32, "checksum offset");
_Static_assert(sizeof(struct Record) == 36, "Record ABI mismatch");
~~~

If the C compiler rejects an assertion, the Java `MemoryLayout` **does not match** the native layout in that environment. Do not remove the assertion just to make the build pass; investigate packing/alignment/compiler options, adjust the layout to match the ABI, and re-test.

**An easily forgotten detail:** a C struct may have **tail padding** so that the total struct size is a multiple of its largest alignment; `MemoryLayout.structLayout` does not automatically add trailing padding the way a C compiler does in every case. When describing an array of structs, a wrong stride due to missing tail padding will shift every element from index 1 onward, even if element 0's fields look right. Test both `sizeof(Record)` and the second element's offset, not just the first field.

### Differences Between StructLayout and UnionLayout Offsets

With a struct, members are laid out sequentially and padding can increase offsets. With a C union, multiple members share **the same starting position**, so `MemoryLayout.unionLayout(...)` typically gives member offsets of **0**. `groupElement("field")` still selects the member by name; however, a field's byte offset is not necessarily unique to member identity. Do not apply struct cumulative offset formulas to unions.

## 12. Advanced Path Forms: Named Groups, Indexed Members, Nested Arrays, Pointers

### 12.1. groupElement(index) Counts Member Layouts, Including Padding

With `header`:

~~~java
MemoryLayout header = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("count"));
~~~

Member index 0 is `kind`, index 1 is **padding**, and index 2 is `count`. Therefore:

~~~java
long byIndex = header.byteOffset(groupElement(2));       // 4
long byName = header.byteOffset(groupElement("count"));  // 4
~~~

If a member is later added before `count`, index 2 can change while the path by name is **more stable**. In production code, use names for semantic fields and use indices when a layout is unnamed or when you genuinely need positional group processing.

### 12.2. Nested Sequences: Matrix

~~~java
MemoryLayout matrix = MemoryLayout.sequenceLayout(
        2, MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT));

long off = matrix.byteOffset(
        sequenceElement(1),
        sequenceElement(2)); // 20
~~~

Here, outer index 1 selects the 2nd row, inner index 2 selects the 3rd column, and each `JAVA_INT` is 4 bytes. Offset formula: `(1 * 3 + 2) * 4 = 20`. For indices unknown ahead of time, use **two** `sequenceElement()` calls in `byteOffsetHandle` or `varHandle`, then pass two `long` indices in order.

### 12.3. arrayElementVarHandle for Runtime-Sized Arrays

Sometimes a C declaration contains `Point points[]` (a flexible array member), whose element count is only known at runtime. In that case, you can obtain a `VarHandle` for **a single Point layout** and ask it to stride by Point's size using `arrayElementVarHandle`:

~~~java
// Fragment, point is MemoryLayout struct {int x; int y}.
VarHandle xs = point.arrayElementVarHandle(groupElement("x"));
// Coordinates: MemorySegment, long base, long elementIndex.
// The actual buffer must be large enough to hold contiguous Points.
int x2 = (int) xs.get(pointsMemory, 0L, 2L);
~~~

This is **not** an example of automatically allocating a runtime element count; `pointsMemory` must be a valid `MemorySegment` with appropriate bounds and alignment, provided with the right size by the caller or native API. For variable-length C arrays, you must obtain the element count or buffer length from the C contract, not dereference arbitrarily just because the handle accepts an index.

### 12.4. dereferenceElement for C Pointer Fields

If a struct has a pointer field (`ValueLayout.ADDRESS.withTargetLayout(...)`), `PathElement.dereferenceElement()` can build a path that goes **through the address stored in that field** to the target layout to create a VarHandle. This is fundamentally different from a nested struct that is **embedded directly**:
- Embedded struct: byte offset can be computed by summing offsets in the layout.
- Pointer to struct: the target address is only known from **the pointer value in memory at runtime**; the target cannot be assumed to sit immediately after the root's pointer field.

`byteOffset(...)` and `select(...)` do not accept paths with a dereference element in the JDK 22 API. When doing pointer dereferencing via a VarHandle, the native target memory must still be alive and have a valid target layout; a bad pointer or size can crash the JVM. For computing offsets of embedded structs and arrays, **`dereferenceElement()` is not needed**.

## 13. Error Types and How to Fix Them

| Symptom | Common Cause | Solution |
|---|---|---|
| `IllegalArgumentException` on `groupElement("foo")` | Root/current group has no member named `foo` | Check `withName` names and path order; the field may be in a child group |
| `IllegalArgumentException` when using `groupElement` after a sequence | Sequence element not selected yet | Insert `sequenceElement(...)` before `groupElement` |
| `IllegalArgumentException` from `byteOffset` with `sequenceElement()` | Chose an **open path** for an API requiring a fixed offset | Use `sequenceElement(index)` or `byteOffsetHandle` |
| `IllegalArgumentException` from `select` with `sequenceElement(2)` | `select` does not accept a **bound sequence index** | Use `sequenceElement()` to select the layout type |
| `IllegalArgumentException` when `varHandle` selects a whole group | Path result is not a `ValueLayout` | Drill down to a primitive field or use slice/layout APIs |
| `WrongMethodTypeException` on `invokeExact` | Wrong number/type of method handle arguments | Check `handle.type()`: base `long` + one `long` per open path |
| `WrongMethodTypeException` on `VarHandle.get/set` | Forgot base offset or dynamic sequence index | For one open index, use `get(seg, 0L, i)` |
| Wrong offset result | Ignored C padding/tail padding, confused bytes and elements | Cross-check `sizeof`, `offsetof`, `byteSize`, and byte map |
| `IndexOutOfBoundsException` | Offset/index leads to access outside the segment | Check segment size, value layout size, offset, and capacity |
| `IllegalArgumentException` due to alignment | Memory address/offset does not meet layout alignment | Allocate properly or describe packed layout matching the ABI |
| `WrongThreadException` | Used a confined arena segment from another thread | Stay on the owner thread; if sharing is needed, use a shared arena + synchronization |
| `IllegalStateException` after `Arena.close()` | Segment is no longer alive | Do not use views/VarHandles after close; adjust ownership |
| Java reads C struct incorrectly without throwing an exception | Wrong native layout, endianness, or value type | Compare C ABI/byte order and run real tests with a C fixture |
| `package java.lang.foreign does not exist` | Using a JDK older than 22 or incompatible compile target | Use JDK 22+; 17/21 have different APIs/flags |

**Path errors and memory errors are two separate layers.** A path may be valid while the segment is already closed, or a path may have a valid offset on the layout while the C library's ABI differs. Test both layers; do not conclude “the offset is right” just because no Java exception was thrown.

## 14. Practical API Design: Constants for Layouts, Stable Paths for Fields

A large binding typically places layouts in a single class and computes offsets/handles once:

~~~java
// Design fragment, not a standalone class.
static final MemoryLayout RECORD_LAYOUT = ...;  // Fully declared.
static final long COUNT_OFFSET = RECORD_LAYOUT.byteOffset(
        groupElement("header"), groupElement("count"));
static final VarHandle POINT_Y = RECORD_LAYOUT.varHandle(
        groupElement("points"), sequenceElement(), groupElement("y"));
~~~

Benefits:
- No repeating manual offset calculations across multiple files.
- Name-based paths enable controlled field layout refactoring.
- Reading the code immediately shows whether a value is a **byte offset** or a **sequence index**.
- Offset constants and varhandles are tested against the same source layout.
- Avoids recreating handles in hot loops, reducing unnecessary setup overhead.

If multiple C ABI versions exist, do not assume one `RECORD_LAYOUT` works on every platform. You can design a factory that takes an **ABI contract** (header version, struct size/alignment, feature flags), validates `sizeof/offsetof` during integration, and only issues handles once the layout is validated.

### Validate Layouts at Startup

Instead of waiting until processing the millionth record, check:

~~~java
// Fragment used in initialization/validation.
if (RECORD_LAYOUT.byteSize() != 36) {
    throw new IllegalStateException("Unexpected Record layout size");
}
long y2 = RECORD_LAYOUT.byteOffset(
        groupElement("points"), sequenceElement(2), groupElement("y"));
if (y2 != 28) {
    throw new IllegalStateException("Unexpected points[2].y offset");
}
~~~

These two assertions **only apply to the sample layout and assumed ABI of this lesson**. In production, expected values must come from the supported C ABI/header; do not hardcode “36 and 28” if the library has multiple variants.

### Thread-Safe Layouts Do Not Mean Thread-Safe Segments

`MemoryLayout` is designed to be immutable and can be shared as constants. However, if two Java threads concurrently read/write **the same native memory** through the same VarHandle, proper memory model/synchronization is still required. `Arena.ofShared()` does not add a mutex automatically. Do not equate a **reusable layout definition** with **mutable memory content**.

## 15. Self-Practice Exercises (With Solutions)

### Exercise 1. Choose the Right Path

Given the Record in this lesson, you want the offset of field `header.count` from the root.

A. `groupElement("count")`  
B. `groupElement("header"), groupElement("count")`  
C. `sequenceElement(0), groupElement("count")`

**Answer B.** `count` is not a direct member of `record`; you must go through the `header` group. The offset from the root is 4 bytes.

### Exercise 2. Compute the Offset of points[1].x by Hand

`points` starts at byte 8; each Point is 8 bytes, and `x` is at offset 0 inside Point. Thus `points[1].x` = `8 + 1 * 8 + 0 = 16`.

Code:

~~~java
long x1 = record.byteOffset(
        groupElement("points"), sequenceElement(1), groupElement("x"));
System.out.println(x1); // 16
~~~

### Exercise 3. Why Do These Two Paths Behave Differently?

~~~java
record.byteOffset(
    groupElement("points"), sequenceElement(1), groupElement("y"));
record.select(
    groupElement("points"), sequenceElement(1), groupElement("y"));
~~~

**Answer:** `byteOffset` is valid and returns 20; `select` rejects a fixed-index sequence path in JDK 22+ and throws `IllegalArgumentException`. To select the `y` layout type, replace `sequenceElement(1)` with `sequenceElement()` in the `select` call.

### Exercise 4. How Many Arguments Does the Dynamic Offset Handle Accept?

~~~java
MethodHandle off = record.byteOffsetHandle(
        groupElement("points"), sequenceElement(), groupElement("y"));
~~~

**Answer:** two `long`s: one base offset and one sequence index; the return type is `long`. With base 0 and index 2, the result is 28. Calling `off.invokeExact(2L)` will not match the method type.

### Exercise 5. Why Can Using groupElement(2) Be Risky When Modifying a Struct?

Because it only means “the third member in the group”; if you add/remove/move padding or a preceding member, the index changes. `groupElement("count")` expresses intent better and does not depend on member position, though you still must verify the ABI whenever changing the layout.

### Exercise 6. Fix the Missing-Coordinate Error

~~~java
// Wrong: y is a VarHandle with an open sequence path.
int v = (int) y.get(segment, 2L);
~~~

**Answer:** you must pass both the base offset **and** the index: `int v = (int) y.get(segment, 0L, 2L);`. Otherwise, it is a VarHandle method-type error, not “index 2 is too large”.

### Exercise 7. Distinguish Field Names from Symbol Names

Does `ValueLayout.JAVA_INT.withName("checksum")` allow `SymbolLookup.find("checksum")` to automatically find a C variable of the same name?

**Answer:** No. `withName` is MemoryLayout metadata, whereas SymbolLookup looks up native exported symbols in a library/loader. They belong to two different namespaces/capabilities.

### Exercise 8. When to Use arrayElementVarHandle Instead of sequenceElement()?

When the native data is an array of elements whose count is decided at runtime and you already have a valid buffer size, `point.arrayElementVarHandle(groupElement("x"))` can stride by the size of Point without pre-creating a `sequenceLayout(N, point)` with a fixed N. Bounds checks, ownership, and a valid ABI are still required.

## 16. Acceptance Checklist for the Naming and Offset Model

- [ ] Use **JDK 22+** for the finalized `java.lang.foreign` API in the example; compile with `--release 22` if targeting baseline 22.
- [ ] Every business field of `StructLayout/UnionLayout` is clearly named with `withName`; do not rely on ambiguous duplicate names.
- [ ] Track the root layout when computing offsets; do not add offsets computed from different roots twice.
- [ ] Use `groupElement("name")` for groups and `sequenceElement(index)` for arrays, in the right tree order.
- [ ] Include padding matching the C ABI: size, alignment, offsets, tail padding, and element stride.
- [ ] `byteOffset` uses a fixed path; do not pass an open path.
- [ ] `select` uses an open sequence path when selecting an element layout; do not pass a fixed index.
- [ ] `byteOffsetHandle` accepts a `long` base offset and one `long` for each open sequence element.
- [ ] `varHandle` drills down to a value layout, passing `MemorySegment`, base offset, and the exact number of runtime indices.
- [ ] `MemorySegment` has sufficient bytes, alignment, a live scope, and an allowed thread; do not treat a layout path as a bounds-relaxation mechanism.
- [ ] Test intentional error cases: missing field, mixing up fixed/open paths, wrong VarHandle arguments, closed arena.
- [ ] If mapping to real C: use `sizeof/offsetof`/compiler ABI checks rather than guessing the layout.
- [ ] Share only immutable layouts/handles where appropriate; synchronization for mutable memory must still be designed separately.
- [ ] Offset constants and handles have tests verified on the target OSes/architectures.

## 17. Summary and References

**Field names** are attached via `withName("field")` on member layouts; **paths** are built by `MemoryLayout.PathElement` from `groupElement` and `sequenceElement`; **offsets** are computed by `byteOffset` or `byteOffsetHandle`; **data access** is performed by `varHandle` and `MemorySegment` within the lifetime of an `Arena`. Naming keeps code stable, but **does not guarantee ABI correctness by itself**: padding, alignment, byte order, bounds, and native ownership still require verification.

Remember the distinction table:

| Need | API to Choose |
|---|---|
| Name a field | `ValueLayout.withName("field")` or `MemoryLayout.withName(...)` |
| Get offset of a fixed field | `root.byteOffset(groupElement(...), ...)` |
| Get offset of an array field at a specific index | `sequenceElement(index)` in `byteOffset(...)` |
| Select the layout type of a field in an array | `root.select(..., sequenceElement(), ...)` |
| Compute offset at runtime with an index | `root.byteOffsetHandle(..., sequenceElement(), ...)` |
| Read/write a field in a segment by index | `root.varHandle(..., sequenceElement(), ...)` |
| Access a dynamic-length array unknown when creating the layout | `elementLayout.arrayElementVarHandle(...)`, with native buffer checks |

Official documentation for the API in JDK 22+:
- [JEP 454: Foreign Function & Memory API (finalized in JDK 22)](https://openjdk.org/jeps/454)
- [Oracle JDK 22 — MemoryLayout, layout paths, open path elements, and methods](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle JDK 22 — MemoryLayout.PathElement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.PathElement.html)
- [Oracle JDK 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle JDK 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Oracle JDK 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)

When porting code to a newer JDK, check the Javadoc of **the exact runtime in use**; when exchanging data with C, check **the compiler's actual C ABI**. An offset that “looks reasonable” yet is off by 1–4 bytes can cause data corruption that is much harder to detect than a clear Java exception.