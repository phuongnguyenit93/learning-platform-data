# Reading Nested Structs and Arrays of Structs Using Layout Paths

## 1. The problem: going from a C struct to Java memory

In Java/native interoperability programming, data is often not as simple as an `int` or a `byte[]` array. A C library may return a **struct containing a struct**, an **array of structs**, or a **struct containing an array of structs**. To read these fields correctly in Java, you need to know the **size, order, alignment, and offset** of each element in memory.

Starting from **JDK 22**, the Foreign Function & Memory API (FFM, package `java.lang.foreign`) provides a way to describe and access such data:

- `MemoryLayout`: describes the shape and size of a memory region.
- `StructLayout`: fields laid out sequentially, according to the declaration order and padding you describe.
- `SequenceLayout`: identical elements repeated into a sequence.
- `ValueLayout`: leaf data types (for example `JAVA_INT`, `JAVA_LONG`).
- `MemoryLayout.PathElement`: steps for **following a layout path** to a nested field.
- `varHandle(...)`: creates a `VarHandle` to read/write a primitive field at the selected position.
- `byteOffset(...)` and `byteOffsetHandle(...)`: computes the position **in bytes** of a field or element.
- `select(...)` and `sliceHandle(...)`: selects a sub-layout or a view over a sub-region of memory.

**Goal of this lesson:** read `records[1].vertices[2].y` in memory **without manually adding "magic" offsets**; at the same time, understand when a path has fixed indices, when dynamic indices need to be passed, and why padding/ABI matters.

### 1.1. Version scope and differences from JNI

The APIs here are **stable FFM from JDK 22** (JEP 454). Therefore, examples using `java.lang.foreign.MemoryLayout`, `MemorySegment`, `Arena`, `ValueLayout`, and `java.lang.invoke.VarHandle` will **compile with JDK 22+**, not pure Java 17 compatible code. On older JDKs there were incubator/preview versions with different syntax; do not mix old code with the APIs here.

The lesson demonstrates with native memory allocated by Java and a C `struct` used as an equivalent model; **no C compilation or JNI calls are needed** to run the Java examples. If you use a layout to read memory returned from a real C library, you must **verify the ABI** on the target OS, CPU, and compiler, and not assume that all C structs have the same padding.

## 2. A visual example: struct in struct, array of structs in struct

Consider a C struct using explicitly sized integer types:

```c
#include <stdint.h>

typedef struct {
    int32_t x;
    int32_t y;
} Point;

typedef struct {
    int32_t id;
    Point origin;
    Point vertices[3];
} Record;

/* A memory region may hold Record records[2]; */
```

In C, the syntax:

```c
records[1].vertices[2].y
```

means:

1. Start at the **`records` array**.
2. Select the **second `Record`** (`[1]`).
3. Select the **`vertices`** field of the Record.
4. Select the **third `Point`** (`[2]`) in vertices.
5. Select the primitive field **`y`** in that Point.

We want to model this exact path in FFM without counting offsets by hand on every read.

### 2.1. Expected layout diagram

Assume the target ABI places `int32_t` at 4 bytes, 4-byte aligned, and the example fields do not introduce extra padding:

```text
Point (8 bytes):
  +0   x: int32 (4)
  +4   y: int32 (4)

Record (36 bytes):
  +0   id: int32 (4)
  +4   origin: Point (8)
       +4  origin.x
       +8  origin.y
  +12  vertices: Point[3] (24)
       +12 vertices[0].x
       +16 vertices[0].y
       +20 vertices[1].x
       +24 vertices[1].y
       +28 vertices[2].x
       +32 vertices[2].y

records = Record[2] (72 bytes):
  record[0]: base +0
  record[1]: base +36

records[1].vertices[2].y:
  36 + 12 + 2 * 8 + 4 = 68 bytes
```

These numbers are **merely the result for the described layout**; FFM can compute them so the code does not have to manually add `36 + 12 + 16 + 4`.

### 2.2. Modeling with Java MemoryLayout

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

StructLayout point = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
);

StructLayout record = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        point.withName("origin"),
        MemoryLayout.sequenceLayout(3, point).withName("vertices")
);

SequenceLayout records = MemoryLayout.sequenceLayout(2, record);
```

This is an **illustrative snippet inside a Java class or method**, not yet a file with `main`; the full runnable program is in section 7.

Two important details:

- `withName("x")`, `withName("vertices")` assign names so `groupElement("...")` can find the field. Names live in the layout's metadata and **are not copied into memory**.
- `sequenceLayout(2, record)` describes **2 Record elements**. `sequenceLayout(3, point)` describes **3 Point elements** inside each Record. Two sequence levels will produce **two dynamic indices** when using an open path.

## 3. How do the three layout groups and PathElement work?

A layout path is a sequence of steps going from the outermost layout to a child element. The steps can be:

| PathElement | Which layout is it used on? | Meaning |
| --- | --- | --- |
| `groupElement("name")` | `StructLayout` or `UnionLayout` | Selects the field in the group named `name` |
| `groupElement(index)` | `GroupLayout` | Selects the field by index in the member layout list |
| `sequenceElement(index)` | `SequenceLayout` | Selects an element with a **fixed index** |
| `sequenceElement()` | `SequenceLayout` | Selects an element with a **dynamic index** — an *open path element* |
| `sequenceElement(start, step)` | `SequenceLayout` | Selects elements via a dynamic index following the progression `start + i * step` |
| `dereferenceElement()` | `AddressLayout` with a target layout | Follows a pointer to the target layout (advanced scope) |

`groupElement` selects a **member of a struct/union**; `sequenceElement` selects an **element in a sequence**. They **are not interchangeable**. If you are at a `StructLayout` and call `sequenceElement`, the path is invalid. If you are at a `SequenceLayout` and call `groupElement("x")` before selecting an element, that is also invalid.

### 3.1. Path for a nested field

`records[1].vertices[2].y` corresponds to:

```java
import static java.lang.foreign.MemoryLayout.PathElement.*;

long offset = records.byteOffset(
        sequenceElement(1),
        groupElement("vertices"),
        sequenceElement(2),
        groupElement("y")
);
// offset = 68
```

This is a **snippet**, requiring the `records` variable from section 2 to already exist. The arguments are in order **from outside to inside**.

- `sequenceElement(1)` selects the second Record.
- `groupElement("vertices")` selects the Point sequence of that Record.
- `sequenceElement(2)` selects the third Point.
- `groupElement("y")` selects the second int of the Point.

The result of `byteOffset` is **the number of bytes** from the root of `records`, not an element index and not an absolute address.

### 3.2. Why must paths have names?

`groupElement("origin")` looks up the field named `origin`. If a layout is declared as:

```java
MemoryLayout.structLayout(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT
);
```

then there is no name `x` or `y` to look up; you either need to assign `withName` or use `groupElement(index)`. Selecting by name is easier to maintain when adding padding or changing field order, but it **does not replace** describing the ABI accurately.

### 3.3. Selecting only a sub-layout, without reading data yet

`select` returns the **sub-layout definition**, without accessing memory:

```java
MemoryLayout yLayout = records.select(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);

System.out.println(yLayout.byteSize()); // 4
```

Here two open `sequenceElement()` calls are used, yet `select` still selects the leaf layout type, because all corresponding elements have the same `Point` structure. The result of `select` is the `int` layout, not yet the value `y` of any Record.

## 4. Fixed paths and open paths

### 4.1. Fixed paths

If all sequence indices are known in advance:

```java
long fixed = records.byteOffset(
        sequenceElement(1),
        groupElement("vertices"),
        sequenceElement(2),
        groupElement("y")
);
```

FFM can immediately compute it into a concrete `long` (**68** in the example). No additional indices need to be passed at read time.

### 4.2. Open paths

When processing every Record and every Point, you cannot write a fixed field offset for all of them. Use two open steps:

```java
VarHandle vertexY = records.varHandle(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);
```

`vertexY` has the access coordinates:

```text
(MemorySegment segment, long baseOffset,
 long recordIndex, long vertexIndex) -> int
```

To read `record[1].vertices[2].y`:

```java
int y = (int) vertexY.get(segment, 0L, 1L, 2L);
```

Note that **the `baseOffset` coordinate is always `long`**, even when 0; the two sequence indices are also `long`. The example uses `0L, 1L, 2L` rather than casually using `int` literals in the strongly typed signature of `VarHandle`.

### 4.3. Counting the coordinates of a VarHandle

| Path | Number of open `sequenceElement()` | Read/write coordinates (excluding `set` value) |
| --- | ---: | --- |
| `record.varHandle(groupElement("id"))` | 0 | `segment, baseOffset` |
| `records.varHandle(sequenceElement(), groupElement("id"))` | 1 | `segment, baseOffset, recordIndex` |
| `records.varHandle(sequenceElement(), groupElement("origin"), groupElement("x"))` | 1 | `segment, baseOffset, recordIndex` |
| `records.varHandle(sequenceElement(), groupElement("vertices"), sequenceElement(), groupElement("y"))` | 2 | `segment, baseOffset, recordIndex, vertexIndex` |
| `records.varHandle(sequenceElement(1), groupElement("vertices"), sequenceElement(2), groupElement("y"))` | 0 | `segment, baseOffset` |

For `VarHandle.set`, add **one final argument** which is the value matching the type of the selected `ValueLayout`: for example `int` for `JAVA_INT`.

### 4.4. Do not call `byteOffset` with an open path

**Incorrect** example:

```java
// Wrong: byteOffset requires a fixed offset.
long offset = records.byteOffset(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);
```

Because the record and vertex indices are missing, `byteOffset` has no single constant offset to return; the API will reject paths with open path elements. If you need a dynamic offset without computing it manually, use **`byteOffsetHandle`**:

```java
import java.lang.invoke.MethodHandle;

MethodHandle offsetHandle = records.byteOffsetHandle(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);

long offset = (long) offsetHandle.invokeExact(0L, 1L, 2L);
// 68
```

This is a snippet placed in a method **declaring `throws Throwable`** or handling the exception appropriately. The `MethodHandle` has a signature taking `baseOffset` and two dynamic indices, returning `long`; `invokeExact` requires exact types at the call site.

## 5. A path to a leaf field vs. a path to an entire struct

### 5.1. `varHandle` only targets a ValueLayout

Valid example:

```java
VarHandle originX = records.varHandle(
        sequenceElement(),
        groupElement("origin"),
        groupElement("x")
);
```

It ends at field `x`, which is `ValueLayout.JAVA_INT`. `VarHandle.get` reads out an `int`.

If the path ends at **the entire `origin`, which is a `StructLayout`**, calling `varHandle` is invalid because the selected layout is not a `ValueLayout`. To get the sub-layout, use `select`; to get a **sub-region of memory**, you can use `asSlice` or **`sliceHandle`**.

### 5.2. Selecting a sub-struct using offset and slice

```java
long originOffset = records.byteOffset(
        sequenceElement(1),
        groupElement("origin")
);
MemorySegment originView = segment.asSlice(
        originOffset, point.byteSize()
);
```

`originView` has **8 bytes** describing the Point of the second Record. This is a **view over the same backing memory**, not a copy. You can read `originView` using a `VarHandle` created from `point`:

```java
VarHandle pointX = point.varHandle(groupElement("x"));
int x = (int) pointX.get(originView, 0L);
// 30 in the full runnable example in section 7
```

Later observations depend on the memory still being alive; do not keep `originView` to access after the `Arena` owning the original segment has been closed.

### 5.3. `sliceHandle` for a sub-struct with open indices

If you need to obtain multiple `Point`s in the array:

```java
MethodHandle pointSlice = records.sliceHandle(
        sequenceElement(),
        groupElement("vertices"),
        sequenceElement()
);

MemorySegment onePoint = (MemorySegment) pointSlice.invokeExact(
        segment, 0L, 1L, 2L);
```

This snippet is called inside a `throws Throwable` method, requiring `records`/`segment` to be declared. `onePoint` is a view of length **`point.byteSize()`**, corresponding to `records[1].vertices[2]`, and shares backing with the original segment. The sub-element is not copied automatically.

## 6. Why must alignment and padding be accounted for?

C structs often have **padding** to satisfy field and struct alignment. `MemoryLayout.structLayout` **does not automatically insert padding** like a C compiler. The Java layout must describe the exact real bytes in the C ABI.

### 6.1. C struct with padding

A C example:

```c
#include <stdint.h>

typedef struct {
    uint8_t  kind;
    int32_t  value;
} Entry;
```

On a common ABI where `int32_t` is 4-byte aligned:

```text
offset 0: kind       (1 byte)
offset 1..3: padding (3 bytes)
offset 4..7: value   (4 bytes)
sizeof(Entry) = 8 bytes
```

To match on that system, explicitly describe the padding:

```java
StructLayout entry = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value")
);
```

Selecting `groupElement("value")` will give offset **4**, and `Entry` elements in an array have stride **8**.

**Compatibility warning:** `uint8_t`/`int32_t` have explicit byte sizes, but **alignment and padding are governed by the C ABI/compiler**. Before accessing real C data, check with `sizeof`, `alignof`, `offsetof`, or headers/layouts generated by a reliable tool (for example `jextract` if appropriate). Do not claim that every ABI has Entry size = 8.

### 6.2. Invalid order case

Example:

```java
// Padding is not added automatically.
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withName("count")
);
```

Because `count` is placed at byte offset 1 while `JAVA_INT` requires alignment 4, constructing the layout may be rejected. Fix it with `paddingLayout(3)` **if that is the actual layout**, or use a `ValueLayout` with relaxed alignment **if the ABI is truly packed**. Do not make a packed layout just to avoid an exception if the C side still uses natural alignment.

### 6.3. Struct padding affects stride

`MemoryLayout.sequenceLayout(n, structLayout)` uses `structLayout.byteSize()` as the **stride** of the elements. If you forget trailing padding at the end of a struct, the second element starts at the wrong offset and every field of `array[1]` onward may be read incorrectly. You must verify **the entire `sizeof(struct)`**, not just `offsetof` of the first few fields.

For the `Record` example containing only `int32_t`/`Point`, on the assumed ABI `sizeof(Point)=8`, `sizeof(Record)=36`, so the stride steps match. With `char`, `double`, bit fields, packed structs, or unions, more careful ABI analysis is needed.

## 7. Runnable Java 22+ program: reading both nested struct and array of structs

This is a standalone example, using the exact `Point` and `Record` structures from section 2, and **without using JNI**. Data is allocated off-heap using `Arena.ofConfined()`, written, and then read using var handles with **layout paths**.

### 7.1. File `NestedLayoutDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.*;

public final class NestedLayoutDemo {
    private static final StructLayout POINT = MemoryLayout.structLayout(
            ValueLayout.JAVA_INT.withName("x"),
            ValueLayout.JAVA_INT.withName("y")
    );

    private static final StructLayout RECORD = MemoryLayout.structLayout(
            ValueLayout.JAVA_INT.withName("id"),
            POINT.withName("origin"),
            MemoryLayout.sequenceLayout(3, POINT).withName("vertices")
    );

    private static final SequenceLayout RECORDS =
            MemoryLayout.sequenceLayout(2, RECORD);

    // One open sequence index: which Record number?
    private static final VarHandle ID = RECORDS.varHandle(
            sequenceElement(), groupElement("id")
    );
    private static final VarHandle ORIGIN_X = RECORDS.varHandle(
            sequenceElement(),
            groupElement("origin"),
            groupElement("x")
    );
    private static final VarHandle ORIGIN_Y = RECORDS.varHandle(
            sequenceElement(),
            groupElement("origin"),
            groupElement("y")
    );

    // Two open indices: which Record? which Vertex?
    private static final VarHandle VERTEX_X = RECORDS.varHandle(
            sequenceElement(),
            groupElement("vertices"),
            sequenceElement(),
            groupElement("x")
    );
    private static final VarHandle VERTEX_Y = RECORDS.varHandle(
            sequenceElement(),
            groupElement("vertices"),
            sequenceElement(),
            groupElement("y")
    );

    private NestedLayoutDemo() {}

    public static void main(String[] args) throws Throwable {
        System.out.println("pointBytes=" + POINT.byteSize());
        System.out.println("recordBytes=" + RECORD.byteSize());
        System.out.println("arrayBytes=" + RECORDS.byteSize());

        // Fixed offsets, computed from the root layout.
        long originY = RECORD.byteOffset(
                groupElement("origin"), groupElement("y")
        );
        long lastY = RECORDS.byteOffset(
                sequenceElement(1),
                groupElement("vertices"),
                sequenceElement(2),
                groupElement("y")
        );
        System.out.println("offset origin.y=" + originY);
        System.out.println("offset records[1].vertices[2].y=" + lastY);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(RECORDS);

            for (long i = 0; i < 2; i++) {
                int id = (i == 0) ? 101 : 202;
                int baseX = (i == 0) ? 10 : 30;
                int baseY = (i == 0) ? 20 : 40;

                ID.set(data, 0L, i, id);
                ORIGIN_X.set(data, 0L, i, baseX);
                ORIGIN_Y.set(data, 0L, i, baseY);

                for (long j = 0; j < 3; j++) {
                    VERTEX_X.set(data, 0L, i, j, baseX + (int) j + 1);
                    VERTEX_Y.set(data, 0L, i, j, baseY + (int) j + 1);
                }
            }

            for (long i = 0; i < 2; i++) {
                int id = (int) ID.get(data, 0L, i);
                int ox = (int) ORIGIN_X.get(data, 0L, i);
                int oy = (int) ORIGIN_Y.get(data, 0L, i);
                int vx = (int) VERTEX_X.get(data, 0L, i, 2L);
                int vy = (int) VERTEX_Y.get(data, 0L, i, 2L);
                System.out.println("row[" + i + "] id=" + id
                        + " origin=(" + ox + "," + oy + ")"
                        + " last=(" + vx + "," + vy + ")");
            }

            int openValue = (int) VERTEX_Y.get(data, 0L, 1L, 2L);

            // Same field, but Record/Vertex indices are fixed.
            VarHandle fixedY = RECORDS.varHandle(
                    sequenceElement(1),
                    groupElement("vertices"),
                    sequenceElement(2),
                    groupElement("y")
            );
            int fixedValue = (int) fixedY.get(data, 0L);

            MethodHandle dynamicOffset = RECORDS.byteOffsetHandle(
                    sequenceElement(),
                    groupElement("vertices"),
                    sequenceElement(),
                    groupElement("y")
            );
            long computed = (long) dynamicOffset.invokeExact(
                    0L, 1L, 2L);

            System.out.println("openY=" + openValue);
            System.out.println("fixedY=" + fixedValue);
            System.out.println("dynamicOffset=" + computed);

            MemoryLayout selected = RECORDS.select(
                    sequenceElement(),
                    groupElement("vertices"),
                    sequenceElement(),
                    groupElement("y")
            );
            System.out.println("selectedBytes=" + selected.byteSize());

            // Take a view of the second Record, then use a local path.
            long record1Offset = RECORDS.byteOffset(
                    sequenceElement(1));
            MemorySegment record1 = data.asSlice(
                    record1Offset, RECORD.byteSize());
            VarHandle localOriginX = RECORD.varHandle(
                    groupElement("origin"),
                    groupElement("x")
            );
            System.out.println("sliceOriginX="
                    + (int) localOriginX.get(record1, 0L));
        }
    }
}
```

The `VarHandle`s are used as `static final` constants so the path does not have to be rebuilt for each loop iteration. `RECORDS.varHandle(...)` returns an "access recipe" rather than storing a pointer to `data` itself. When calling `get`/`set`, you pass a **live segment**, the **base offset**, and the corresponding **open indices**.

### 7.2. Compiling/running on JDK 22+

Place the file in the working directory:

```bash
javac NestedLayoutDemo.java
java NestedLayoutDemo
```

`--enable-preview`, `--enable-native-access`, or a native compiler are not needed for this code. `MemoryLayout`, `Arena`, and `MemorySegment` are stable from JDK 22; if the compiler reports `package java.lang.foreign does not exist`, verify that `javac -version` and `java -version` are both using a supported JDK.

### 7.3. Exact stdout output

```text
pointBytes=8
recordBytes=36
arrayBytes=72
offset origin.y=8
offset records[1].vertices[2].y=68
row[0] id=101 origin=(10,20) last=(13,23)
row[1] id=202 origin=(30,40) last=(33,43)
openY=43
fixedY=43
dynamicOffset=68
selectedBytes=4
sliceOriginX=30
```

### 7.4. Why is the output like this?

- `Point` has two `JAVA_INT`s, each field 4 bytes → **8 bytes**.
- `Record` contains `id` 4 + `origin` 8 + `vertices` (3 × 8) 24 → **36 bytes**.
- `RECORDS` has two Records → **72 bytes**.
- `origin.y` in a Record sits after `id` (4 bytes) and `origin.x` (4 bytes) → **offset 8**.
- `records[1]` starts at byte 36. `vertices` is at offset 12 in Record; the third Point has offset 2×8; `y` has offset 4 → **68**.
- For the second Record, `baseX=30`, `baseY=40`; the third vertex contains `x=33`, `y=43`.
- `VERTEX_Y` (open path) and `fixedY` (fixed path) select the same location, so both return `43`.
- `byteOffsetHandle` takes dynamic indices and produces offset `68`.
- `select` finds `ValueLayout.JAVA_INT` with `byteSize=4`, without accessing data.
- `asSlice` from the second Record's offset creates a 36-byte view. Reading `origin.x` with a path starting from `RECORD` returns `30`.

**Distinction:** `records[1]` is an **element index**, whereas `68` is a **byte offset**. You do not need to compute byte 68 manually in application code if you always use paths/VarHandles.

## 8. Second program: struct with padding and array of structs

This section is **another standalone example** to clarify why `groupElement("value")` must account for padding and why an array of structs has stride equal to `sizeof(struct)`.

### 8.1. File `PaddedStructArrayDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SequenceLayout;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

import static java.lang.foreign.MemoryLayout.PathElement.*;

public final class PaddedStructArrayDemo {
    private PaddedStructArrayDemo() {}

    public static void main(String[] args) {
        StructLayout entry = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("kind"),
                MemoryLayout.paddingLayout(3),
                ValueLayout.JAVA_INT.withName("value")
        );
        SequenceLayout entries = MemoryLayout.sequenceLayout(2, entry);

        VarHandle kind = entries.varHandle(
                sequenceElement(), groupElement("kind")
        );
        VarHandle value = entries.varHandle(
                sequenceElement(), groupElement("value")
        );

        System.out.println("entryBytes=" + entry.byteSize());
        System.out.println("valueOffset="
                + entry.byteOffset(groupElement("value")));
        System.out.println("entries[1].valueOffset="
                + entries.byteOffset(
                        sequenceElement(1), groupElement("value")));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment memory = arena.allocate(entries);

            kind.set(memory, 0L, 0L, (byte) 7);
            value.set(memory, 0L, 0L, 1234);
            kind.set(memory, 0L, 1L, (byte) 8);
            value.set(memory, 0L, 1L, 5678);

            for (long i = 0; i < 2; i++) {
                byte k = (byte) kind.get(memory, 0L, i);
                int v = (int) value.get(memory, 0L, i);
                System.out.println("entry[" + i + "]=(" + k + "," + v + ")");
            }
        }
    }
}
```

Run:

```bash
javac PaddedStructArrayDemo.java
java PaddedStructArrayDemo
```

Stdout:

```text
entryBytes=8
valueOffset=4
entries[1].valueOffset=12
entry[0]=(7,1234)
entry[1]=(8,5678)
```

Because `paddingLayout(3)` pads three bytes after `kind`, `value` is at offset 4. Each Entry is 8 bytes long, so `entries[1].value` is at byte **8 + 4 = 12**. If you omit the padding and pick offset 1 in the layout, it will not reflect the sample ABI; the layout may even be rejected due to incompatible alignment.

## 9. Declaring and reading multi-level nested arrays

Two sequence levels **do not necessarily** have to be separated by a struct. For example, a table of 2 rows, each row containing 3 Points:

```java
SequenceLayout grid = MemoryLayout.sequenceLayout(
        2,
        MemoryLayout.sequenceLayout(3, point)
);

VarHandle yHandle = grid.varHandle(
        sequenceElement(), // row
        sequenceElement(), // column
        groupElement("y")
);

int y = (int) yHandle.get(segment, 0L, 1L, 2L);
```

This is **illustrative code**, with `point` being the layout from section 2 and `segment` already allocated with at least `grid.byteSize()` bytes, live/properly aligned. The path is:

```text
grid[row=1][column=2].y
       |        |     |
  sequence   sequence  group
```

Two open `sequenceElement()` steps correspond to **two `long` coordinates** in the exact order they appear. If you swap `rowIndex` and `columnIndex`, the code may read the wrong position or go out of bounds.

With a **struct containing an array of structs**:

```java
VarHandle vertexY = record.varHandle(
        groupElement("vertices"),
        sequenceElement(),
        groupElement("y")
);
int y = (int) vertexY.get(recordSegment, 0L, 2L);
```

Because the root is **one Record** (not all of `records`), there is only **one** open sequence index. If you replace the root with `RECORDS`, you must prepend `sequenceElement()` at the beginning and pass an additional Record index.

## 10. Root layout, base offset, and how to reuse handles

A `VarHandle` created from a layout contains enough information to **compute the relative offset** of the selected field. However, it does not know which memory region you are operating on until a `MemorySegment` is passed in.

### 10.1. Why is there always a `baseOffset`?

According to the JDK 22 specification, `varHandle(PathElement...)` takes:

```text
MemorySegment, long baseOffset, [long dynamicSequenceIndices...]
```

For example, using `RECORD` as the root, but reading the second Record located inside a buffer containing two Records:

```java
VarHandle id = record.varHandle(groupElement("id"));

long record1Offset = record.byteSize();  // 36
int record1Id = (int) id.get(fullSegment, record1Offset);
```

This is a **snippet** with `record`/`fullSegment` already declared. Because `id` is only a field within a single Record, you pass base offset 36 to read the second Record. Another way is to take `fullSegment.asSlice(36,36)` and then call `id.get(slice, 0L)`.

### 10.2. Should VarHandles be cached?

Yes. If the layout does not change, defining:

```java
static final VarHandle FIELD = LAYOUT.varHandle(
        sequenceElement(), groupElement("field")
);
```

in a class with the corresponding `LAYOUT` is usually easier to maintain than rebuilding the layout path for every element of a loop. If the layout schema changes, you need to recreate the handle with the new schema; you cannot keep the old handle and assume the offsets stay unchanged.

### 10.3. `byteOffsetHandle` does not dereference pointers

`byteOffsetHandle` computes the offset from the **root layout within the same contiguous memory region**, not a dereference operation to follow a C pointer. If a struct contains `T* ptr`, the step `groupElement("ptr")` selects an **address** (AddressLayout), not a struct `T` located inline at that offset. To traverse into the pointed-to region, you need to describe a target layout and use `dereferenceElement()` in supported APIs; that is an operation that **reads an address and another memory region**, with additional lifetime and safety constraints. Do not add an inline struct offset and assume it is equivalent to pointer dereferencing.

## 11. Variable element counts: when `sequenceLayout(n,...)` is not enough

`sequenceLayout(n, element)` is suitable when the number of elements **is known in advance**. But real native data is sometimes:

```c
typedef struct {
    int32_t count;
    Point points[];
} Packet;
```

Here `points[]` is a C99 **flexible array member**; its length is not fixed at schema creation time. You cannot assume `sequenceLayout(100, point)` if `count` may differ from 100.

JDK 22 provides `MemoryLayout.arrayElementVarHandle(...)` to access a **contiguous array of an element layout**, with a loop index not fixed by an outer `SequenceLayout`.

Conceptual example (assuming an ABI-correct `StructLayout point` already exists):

```java
VarHandle xOfPoint = point.arrayElementVarHandle(
        groupElement("x")
);

long pointsOffset = packetLayout.byteOffset(
        groupElement("points")
);

// Within the packet region with enough backing memory for n Points.
for (long i = 0; i < n; i++) {
    int x = (int) xOfPoint.get(packetSegment, pointsOffset, i);
}
```

This is **not a standalone program**: `packetLayout`, `packetSegment`, and `n` must be prepared properly as a struct header plus data region; `pointsOffset` must be verified against the ABI and have sufficient backing length.

The VarHandle on `point` has the signature:

```text
(MemorySegment segment, long baseOffset, long arrayIndex) -> int
```

Unlike `sequenceElement()` on `sequenceLayout(3, point)`, the index in `arrayElementVarHandle` is used to stride by the **size of the entire `point` layout**, not constrained by a fixed count inside a `SequenceLayout`.

**Safety warning:** if `count` comes from native input/file/network, validate `count >= 0` and that `pointsOffset + count * point.byteSize()` does not overflow and does not exceed `packetSegment.byteSize()`. If you have not verified that the backing memory is large enough or if the pointer region is invalid, do not dereference it. Do not ignore thread ownership/scope just because the handle lets you compute an index.

### 11.1. When to use PathElement and when to use arrayElementVarHandle?

| Case | Reasonable API | Notes |
| --- | --- | --- |
| Fixed `Record[2]` | `sequenceLayout(2, Record)` + `sequenceElement()` | Layout describes the entire array |
| Fixed `Record.vertices[3]` | `groupElement("vertices"), sequenceElement()` | Enter the field, then select an element |
| Array of Points with runtime-determined count | `point.arrayElementVarHandle(...)` | Uses index stride by `point.byteSize()` |
| Header with C flexible array member | Header layout + offset + `arrayElementVarHandle` | Compute buffer size from validated count |
| C pointer field `Point*` | `AddressLayout`/target + controlled dereference | Different from an inline array |

## 12. Reading data from a real native library: verifying schema and lifetime

The Java exercise creates Java-owned memory; when reading a native `struct` provided by C/C++, you must additionally consider:

### 12.1. Sizes and offsets from the real ABI

Knowing only the C typedef is not enough. Factors that affect it:

- Compiler/ABI and architecture (x86_64, AArch64, Windows ABI...).
- `sizeof` and `alignof` of each type, padding rules.
- `#pragma pack`, packed attributes, and other alignment requirements.
- Byte order (`endianness`) and number representation rules.
- `union`: multiple members **share the same offset**, unlike sequential `struct`s.
- Pointers, bit fields, and flexible array members require special handling.

If the Java layout describes the stride of Record incorrectly, `records[0]` may still read fine while `records[1]` starts at the wrong offset — a particularly hard bug to detect.

In real interop implementations, cross-check `sizeof(Record)` and `offsetof(Record, vertices)`, `offsetof(Point, y)`; you can use tools like `jextract` on the target-appropriate header. For the example in section 7, all parameters are determined by **the Java layout itself**, so the output can be predicted accurately.

### 12.2. The segment must point to valid memory

`MemorySegment` only allows access within **spatial bounds**, **live scope**, and **thread access permissions**. A layout-correct offset does not turn an arbitrary native address into safe memory. Do not use `MemorySegment.ofAddress` with untrusted addresses, do not expand a segment unboundedly, and do not read after the C library has freed the memory.

`Arena.ofConfined()` example:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(recordsLayout);
    // Structured access within this scope.
}
// After close, the native segment must not be reused.
```

This is an **illustrative snippet**, with `recordsLayout` being a valid layout. If you need multi-threading, you can use `Arena.ofShared()` but must design synchronization; a shared scope does not automatically guarantee prevention of data races.

### 12.3. Reading data with a layout without name metadata in memory

Field names `x`, `y`, `origin` are Java metadata for layout paths. C memory does not contain these name strings. Therefore `groupElement("y")` **does not search for the letter "y" in the bytes**; it reads the offset defined in the layout. If the C schema changes, the Java code needs a new layout with the right sizes/order.

## 13. Common mistakes

| Mistake | What happens? | How to fix |
| --- | --- | --- |
| Using `groupElement("y")` directly on a `SequenceLayout` | Path does not match layout kind | Select an element with `sequenceElement(...)` first |
| Using `sequenceElement(...)` on a `StructLayout` | Invalid path | Select the sequence field with `groupElement("vertices")` |
| Missing `withName("origin")` | Lookup by name cannot find the field | Name the member or use an index |
| Calling `varHandle` to an entire `StructLayout` | Selected layout is not a `ValueLayout` | Use `select`, `asSlice`, or `sliceHandle` |
| Calling `byteOffset` with an open `sequenceElement()` | No fixed offset | Use `sequenceElement(index)` or `byteOffsetHandle` |
| Confusing `0L` base offset with record index | Reads wrong element/`WrongMethodTypeException` | Pass coordinates in order `segment, base, indices` |
| Using `1` (int) where VarHandle expects `long` | Signature mismatch at call site | Use `1L` or cast `(long)i` |
| Swapping two sequence indices | Gets wrong vertex/record | Follow PathElement order from outside to inside |
| Multiplying index by 4 manually when handle already knows stride | Offset is computed twice | Pass the **index**, let the handle compute the offset |
| Omitting C struct padding | Wrong offset/stride, especially second array element | Compare `sizeof/offsetof` per ABI |
| Choosing `JAVA_INT` for a C field not 4 bytes wide | Reads wrong carrier/bytes | Choose the `ValueLayout` matching the C type |
| Using a field-matching layout on a segment whose arena was closed | `IllegalStateException` | Keep the arena alive across all accesses |
| Accessing a confined segment from another thread | `WrongThreadException` | Use the owner thread or an appropriate shared arena |
| Index exceeds segment bounds | `IndexOutOfBoundsException` or wrong logical access | Check both count and byteSize |
| Using `get` on handle but casting to wrong type | `ClassCastException`/`WrongMethodTypeException` | Check the carrier of the selected `ValueLayout` |
| Selecting a C pointer field but treating it as a nested inline struct | Data is not at the same location | Use proper address target/dereference |
| Treating `sliceHandle` as copying data | Aliasing remains; changing original region affects slice | If a snapshot is needed, copy to another region |

### 13.1. Invalid path at handle creation time

Incorrect example:

```java
// records is a SequenceLayout, not yet inside Record/Point.
VarHandle bad = records.varHandle(groupElement("y"));
```

The fix is to start with `sequenceElement()`, then select the corresponding `groupElement` for each sub-struct. Most **path shape** errors occur right when creating the layout/handle, whereas index, scope, read-only, or alignment errors occur at access time.

### 13.2. An open path is not a license for arbitrary indices

For a sequence with a finite number of elements, loops must still keep indices within logical bounds. In addition to the API checking the byte bounds of the segment, you should check the **sequence element count** to prevent offset calculations from drifting into another region while still staying within a larger segment, especially when there are multiple nested layouts and a base offset is used. Do not expect every `VarHandle.get` call to understand the semantic "vertexIndex must be less than 3" if the actual memory contains other bytes.

### 13.3. Ignoring byte order

`ValueLayout.JAVA_INT` describes a 4-byte `int` with the layout's byte order. When reading data from a file/network, choose `withOrder(ByteOrder.BIG_ENDIAN)` or `LITTLE_ENDIAN` as required by the protocol. A layout path only computes the **position**; it does not automatically fix **how bytes are interpreted**.

## 14. Performance and maintainability

**Prefer creating layouts and handles once.** For a stable schema, cache `StructLayout`, `SequenceLayout`, and `VarHandle` as `static final`. Layout objects are immutable and can be reused in many places; meanwhile `MemorySegment` remains subject to the lifetime, ownership, and thread access limits of its underlying memory region.

**Use paths instead of manual offsets** when a schema has multiple levels. A structural change can alter the offsets of many fields; if hard-coded numbers like 12, 36, 68 remain in application code, discrepancies easily slip past review. When accessing by path, updating the layout updates offset calculations based on the schema.

**ABI verification is still required.** Paths help avoid addition/subtraction mistakes once the layout is right; they **do not automatically detect** whether a real C header differs from the Java schema.

**Avoid unintended copies.** `asSlice`/`sliceHandle` create views over the same memory region; reading with `VarHandle` does not automatically copy a struct into a Java object. If you need to transfer data into an independent Java class, read the fields by path and construct a record/POJO or copy into a Java array according to application rules.

## 15. Application scenarios

### A. Array of sensor positions

A C library returns `Point readings[100]`. Create `sequenceLayout(100, POINT)` and then `varHandle(sequenceElement(), groupElement("x"))`, reading with `handle.get(memory, 0L, (long)i)`. No need to build 100 different handles.

### B. A struct containing metadata and a sequence of points

A library returns `Record` with `id`, `origin`, and `vertices`. Create a `StructLayout` nesting `Point` and `SequenceLayout`, then use `groupElement("vertices"), sequenceElement(), groupElement("y")`. Prepend `sequenceElement()` at the start if there is an outer **`Record[]` array**.

### C. Multiple records from a network/binary file

If the data format is **fixed** and has no native pointers, you can build a `MemoryLayout` matching the file's endianness/schema, then use `MemorySegment.ofArray(byte[])` or a native segment with sufficient scope to read. Check checksums/bounds first, and avoid reading an unvalidated array count.

### D. C headers changing between SDK versions

Do not keep hard-coded offsets; manage schemas per library version. Verify `sizeof/offsetof` for the exact version. If the compiler adds padding or changes packing, update the layout, not just indices in Java.

### E. Results needing to be returned as Java objects

FFM layout paths read primitives efficiently; however, a Java DTO like `record Point(int x,int y)` has its own lifecycle, garbage collection, and immutability. Read with `VarHandle` and then **build a Java record** if the caller wants independent ownership, instead of storing a `MemorySegment` that might expire with the arena.

## 16. Self-check questions

**1. Why does `records[1].vertices[2].y` need two `sequenceElement` steps?** Because there are two array levels: `Record[]` on the outside and `Point[]` inside a Record. Each open step produces one `long` index coordinate.

**2. What is the difference between `sequenceElement(2)` and `sequenceElement()`?** One selects the fixed third element when creating the path; the other lets the caller pass the index at `get/set` time.

**3. Can `byteOffset` be used with an open path?** No. Use a fixed index or `byteOffsetHandle` to pass dynamic indices.

**4. Can you call `records.varHandle(sequenceElement(), groupElement("origin"))` to get the entire Point struct?** No. `origin` is a StructLayout, not a ValueLayout; use `select`/`sliceHandle`/`asSlice`.

**5. In the `Record` example, what byte offset is `records[1].vertices[2].y` at?** **68** from the start of `Record[2]`, per `36 + 12 + 2×8 + 4`.

**6. What happens if `groupElement("x")` cannot find the field?** The path is invalid, and the API throws an error when creating the path/handle; you must name the layout with `withName` or select the right member.

**7. Why does JDK 22 need `paddingLayout` when describing a C struct?** `structLayout` does not insert padding automatically. To match offsets/stride with the C ABI, you must explicitly describe the padding bytes.

**8. Does `sliceHandle` create a copy of Point?** No. It gives a view over a sub-region of the original segment, so it obeys the corresponding scope and backing.

**9. When should `arrayElementVarHandle` be considered?** When the number of elements in a native array is only determined at runtime and is not encoded as a fixed-length `SequenceLayout`.

**10. What does `VarHandle.get(segment,0L,1L,2L)` mean in the example?** `segment` is the memory region, `0L` is the base offset, `1L` selects the second Record, `2L` selects the third vertex; the result is the value of the selected field, `43` in the sample data.

## 17. Checklist before reading nested struct data

1. Confirm you are using the **JDK 22+ FFM API**; do not mix earlier preview/incubator code.
2. Accurately describe `ValueLayout`, `StructLayout`, `SequenceLayout`, `withName` names, and padding.
3. Verify `sizeof`, `alignof`, `offsetof` on the target C ABI if the data is real native data.
4. Order `groupElement`/`sequenceElement` along the path **outside → inside**; choose the right step kind for the layout kind.
5. If a **fixed offset** is needed, use `byteOffset` with fixed sequence indices.
6. If **reading/writing a leaf field** is needed, use `varHandle`; remember the right number of `long` coordinates and Java carrier.
7. If a **dynamic offset** is needed, use `byteOffsetHandle`; if a **sub-struct region** is needed, use `sliceHandle` or `asSlice`.
8. If there is an **array of unknown count**, use `arrayElementVarHandle` and verify the data region size.
9. Check logical indices, `byteSize`, alignment, endianness, live scope, and thread ownership.
10. Do not confuse a view with a copy; do not use a segment after its arena closes or a pointer after its native owner frees it.
11. Cache layouts/handles when the schema is stable; write integration tests checking offsets and sample values.
12. When data needs to live long-term as Java objects, convert it into Java structures with independent ownership.

## Official references

- [Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): layout paths, `select`, `byteOffset`, `byteOffsetHandle`, `varHandle`, `arrayElementVarHandle`, and `sliceHandle`.
- [Java SE 22 — MemoryLayout.PathElement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.PathElement.html): `groupElement`, `sequenceElement`, and `dereferenceElement`.
- [Oracle Java SE 22 — Memory Layouts and Structured Access](https://docs.oracle.com/en/java/javase/22/core/memory-layouts-and-structured-access.html): official guide on structs, sequences, and dynamic coordinate VarHandles.
- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): access bounds and memory checking rules.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): native allocation and scope lifecycle.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM becoming a stable API in JDK 22.