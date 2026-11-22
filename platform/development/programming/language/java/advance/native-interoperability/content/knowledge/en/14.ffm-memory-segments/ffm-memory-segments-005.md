# Creating asSlice Slices and Data-Sharing Relationship with the Root Segment

## Lesson Objectives

**MemorySegment.asSlice(...)** creates a **slice**: a new **MemorySegment** object representing **a subrange** within the same memory region already managed by the root segment. This is a **non-copying view**. When both views allow writing, modifying the same location through one view will be seen by the other view, provided access permissions, lifetime, and synchronization rules are satisfied.

After this lesson, you can:

1. Distinguish **root segment**, **slice**, **backing memory**, and **independent copy**.
2. Use the overloads **asSlice(offset)**, **asSlice(offset, byteSize)**, **asSlice(offset, byteSize, byteAlignment)**, and **asSlice(offset, MemoryLayout)** with the correct **byte** unit.
3. Accurately calculate the corresponding positions between slice and root, including **nested slices**.
4. Explain why modifying through a slice affects the root segment, heap array, or native memory region.
5. Distinguish spatial bounds, alignment, read-only, thread confinement, and the lifetime of **Arena**.
6. Design handling for packets, records, header/payload regions, or native data without causing out-of-bounds, use-after-close, or data race errors.

**Version:** Complete examples use **java.lang.foreign.MemorySegment** and **Arena** on **JDK 22+**, where the Foreign Function & Memory (FFM) API has been finalized (JEP 454). JDK 17 uses a different **incubator** API; JDK 21 uses a **preview** API and may require preview flags, so **do not** copy the programs below verbatim to JDK 17/21. The illustrative code below compiles with Java 22 or later **without needing --enable-preview** for the memory operations used.

## 1. What does MemorySegment represent?

A **MemorySegment** is a bounded view over a contiguous region of bytes. It has characteristics to remember:

| Characteristic | Meaning for asSlice |
| --- | --- |
| **Backing memory** | The actual bytes being represented, in Java heap or native memory |
| **address()** | Logical address/offset of the segment; a slice starts at the root address plus offset |
| **byteSize()** | Number of **bytes** the view allows accessing; a slice has its own size |
| **scope()** | Lifetime scope: a slice uses the **same scope** as the root segment |
| **isReadOnly()** | Read-only state: a slice of a read-only view remains read-only |
| **isAccessibleBy(thread)** | Which thread can access: a slice does not relax thread constraints |
| **isNative()** | Whether it represents native memory; slicing does not turn heap into native or vice versa |

A **heap segment** can be created with **MemorySegment.ofArray(byte[])**, **ofArray(int[])**, and corresponding overloads: it is backed by a Java array. A **native segment** can be allocated by **Arena.allocate(...)**: it represents memory outside the Java heap. Both can be divided into multiple slices; the **zero-copy** semantics, byte bounds, and binding to backing memory are similar.

A **MemorySegment object** is not the memory region itself. When calling **asSlice**, you create an object describing a different range over the **same bytes**, rather than creating an independent allocation.

## 2. Visualizing a slice on a 10-byte region

Suppose the root segment has **byteSize() == 10** and we call:

~~~java
MemorySegment slice = root.asSlice(3, 4);
~~~

Visualizing the offsets:

~~~text
root (10 bytes):
root offset    0  1  2 |3  4  5  6| 7  8  9
              ----------+-----------+---------
backing data   A  B  C |D  E  F  G| H  I  J
                        ^           ^
                      slice       end-exclusive

slice (4 bytes):
slice offset             0  1  2  3
backing data             D  E  F  G

root offset = 3 + slice offset
~~~

**root[3]** and **slice[0]** point to the **same byte**. If **slice[1]** is modified, that is byte **root[4]**. If **root[6]** is modified, reading **slice[3]** will see the new value.

What is changed by **asSlice(3, 4)** is the **accessible range**: the slice only sees 4 bytes (root offsets 3–6). No new 4-byte data array is copied from root.

Three things must not be confused:

- A **new view** does not mean a **new memory region**.
- **Slice offsets** start again from **0**, not from **3**.
- **Slice bounds** do not change the **size or contents** of root; root still contains all 10 bytes.

## 3. asSlice overloads and size calculation

In JDK 22+, the key forms are:

~~~java
MemorySegment tail = root.asSlice(offset);
MemorySegment part = root.asSlice(offset, newSize);
MemorySegment aligned = root.asSlice(offset, newSize, byteAlignment);
MemorySegment typed = root.asSlice(offset, layout);
~~~

| Overload | Meaning |
| --- | --- |
| **asSlice(long offset)** | View from **offset** to the end of the segment. Size = **root.byteSize() - offset** |
| **asSlice(long offset, long newSize)** | View starting at **offset**, **newSize bytes** long |
| **asSlice(long offset, long newSize, long byteAlignment)** | Creates a view with the specified alignment constraint, while checking that the starting address matches |
| **asSlice(long offset, MemoryLayout layout)** | Size = **layout.byteSize()**, alignment = **layout.byteAlignment()** |

The parameters **offset**, **newSize**, **byteAlignment** are all in **byte** units, not Java element counts, int counts, or indices in an object array. With **ValueLayout.JAVA_INT**, an **int** value takes **4 bytes**; to start at the 2nd int element (0-based), the offset is **8**, not **2**.

The basic conditions for **asSlice(offset, newSize)** on a segment of **N** bytes are:

~~~text
0 <= offset <= N
0 <= newSize <= N - offset
~~~

In words: **offset is non-negative**, **newSize is non-negative**, and **the end of the slice must not exceed the end of the source segment**. Violations can cause **IndexOutOfBoundsException**. The formula **newSize <= N - offset** also helps avoid adding two large numbers that could easily overflow in application-written validation checks.

**Special valid boundary:**

~~~java
MemorySegment empty = root.asSlice(root.byteSize(), 0);
~~~

This is a **0-byte slice** at the end of root, creating a valid view, but you cannot read a byte at offset 0. **root.asSlice(root.byteSize())** also yields an empty slice. This case is useful when representing data with no payload; it should not be treated as an arbitrary dereferenceable pointer.

For the alignment form:

- **byteAlignment** must be a power of 2 and greater than 0; invalid values cause **IllegalArgumentException**.
- The starting address **root.address() + offset** must satisfy the alignment, otherwise **IllegalArgumentException** may occur.
- The **asSlice(offset, layout)** form is equivalent to requiring both **layout.byteSize()** and **layout.byteAlignment()**.
- The two-parameter form **asSlice(offset, newSize)** does not imply all read types are aligned; the **get/set** step with **ValueLayout** still checks the corresponding alignment.

Do not arbitrarily set byteAlignment to the packet size; alignment is a requirement on the **starting address**, not a constraint on how many bytes long the slice is.

## 4. Runnable example 1: heap slice and Java array sharing the same data

### File SliceHeapDemo.java

~~~java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public class SliceHeapDemo {
    public static void main(String[] args) {
        byte[] bytes = {10, 20, 30, 40, 50, 60};

        // Segment covering the entire Java byte[].
        MemorySegment root = MemorySegment.ofArray(bytes);

        // Slice from byte index 2, taking 3 bytes (indices 2, 3, 4).
        MemorySegment middle = root.asSlice(2, 3);

        System.out.println("root size: " + root.byteSize());
        System.out.println("slice size: " + middle.byteSize());
        System.out.println("slice[0] first: "
                + middle.get(ValueLayout.JAVA_BYTE, 0));

        // Write via slice; the original array changes immediately.
        middle.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);
        System.out.println("after slice write: "
                + Arrays.toString(bytes));

        // Write via root; the slice sees the change at the corresponding position.
        root.set(ValueLayout.JAVA_BYTE, 4, (byte) 77);
        System.out.println("slice[2] after root write: "
                + middle.get(ValueLayout.JAVA_BYTE, 2));

        // Nested slice inside middle: root indices 3 and 4.
        MemorySegment nested = middle.asSlice(1, 2);
        nested.set(ValueLayout.JAVA_BYTE, 0, (byte) 88);
        System.out.println("after nested write: "
                + Arrays.toString(bytes));

        // Read-only slice still sees the data, but disallows writing through this view.
        MemorySegment readOnly = middle.asReadOnly();
        System.out.println("read-only slice: " + readOnly.isReadOnly());
        System.out.println("read-only value: "
                + readOnly.get(ValueLayout.JAVA_BYTE, 0));

        try {
            readOnly.set(ValueLayout.JAVA_BYTE, 0, (byte) 1);
        } catch (IllegalArgumentException expected) {
            System.out.println("read-only write rejected");
        }
    }
}
~~~

Compile and run on **JDK 22+**:

~~~bash
javac SliceHeapDemo.java
java SliceHeapDemo
~~~

Stdout:

~~~text
root size: 6
slice size: 3
slice[0] first: 30
after slice write: [10, 20, 99, 40, 50, 60]
slice[2] after root write: 77
after nested write: [10, 20, 99, 88, 77, 60]
read-only slice: true
read-only value: 99
read-only write rejected
~~~

**Explanation of each value:**

- **root** has 6 bytes because the initial **byte[]** contains 6 elements, 1 byte each.
- **middle = root.asSlice(2, 3)** covers three positions **root[2]**, **root[3]**, **root[4]**. Therefore **middle[0]** is initially **30**.
- **middle.set(..., 0, 99)** writes directly to **bytes[2]**. No **copyBack**, **commit**, or separate data synchronization step is needed to update the original array in the same thread.
- **root.set(..., 4, 77)** makes **middle.get(..., 2)** read **77** because both views point to the 4th byte.
- **nested = middle.asSlice(1, 2)** starts from **root[3]**. Writing to **nested[0]** sets **bytes[3] = 88**.
- **middle.asReadOnly()** creates a read-only view of the same memory region. It does not create an immutable copy: the data can continue to change if there is another writable view such as **root**.
- Writing through the read-only view throws an exception; the program properly catches **IllegalArgumentException** from the **set** method for a read-only segment.

The example uses **heap memory** so there is no need to close an **Arena**. The Java array and all its slices are managed by the Java heap/GC lifecycle. Do not use **MemorySegment.address()** of a heap segment as a C address to pass directly to native code.

## 5. Offset mapping table: from root to slice and nested slice

Suppose:

~~~java
MemorySegment a = root.asSlice(100, 40);
MemorySegment b = a.asSlice(12, 20);
MemorySegment c = b.asSlice(5, 4);
~~~

Then the starting offsets of the views, relative to root, are:

| View | Start relative to root | byteSize() | Root byte range |
| --- | ---: | ---: | --- |
| **root** | 0 | at least 140 | Entire root |
| **a** | 100 | 40 | 100 to 139 |
| **b** | 112 | 20 | 112 to 131 |
| **c** | 117 | 4 | 117 to 120 |

For example, **c.get(ValueLayout.JAVA_BYTE, 2)** corresponds to byte **root[119]** because:

~~~text
absoluteOffset = offset(a in root)
               + offset(b in a)
               + offset(c in b)
               + read offset in c

               = 100 + 12 + 5 + 2
               = 119
~~~

This is an **illustrative code/assumption snippet**, not standalone compilable because **root** has not been created large enough yet. All offset calculation values here are in **byte** units; use **long** for offsets and sizes when calling the API.

**Key takeaway:** after obtaining a slice, all **get/set** calls are based on **the relative coordinates of the current view**. If you are at **c**, you only pass offset **2**, not the root offset **119**. Passing a root offset into a slice is a common mistake leading to **IndexOutOfBoundsException**.

## 6. Slices enforce their own bounds: bounds checking

If **middle.byteSize() == 3**, the valid byte addresses in middle are **0**, **1**, **2**. You are not allowed to go past middle's bounds just because root still has enough bytes.

~~~java
MemorySegment root = MemorySegment.ofArray(
        new byte[] {10, 20, 30, 40, 50, 60});
MemorySegment slice = root.asSlice(2, 3);

// Valid: gets the last byte of the slice, i.e., root offset 4.
byte last = slice.get(ValueLayout.JAVA_BYTE, 2);

// Invalid: slice offset 3 is outside the slice (even though root has offset 5).
byte invalid = slice.get(ValueLayout.JAVA_BYTE, 3);
~~~

This is a **fragment intentionally illustrating an erroneous operation**; the last line will throw **IndexOutOfBoundsException** and is not a program designed to run to completion. To test intentionally:

~~~java
try {
    slice.get(ValueLayout.JAVA_BYTE, 3);
} catch (IndexOutOfBoundsException expected) {
    System.out.println("slice bounds enforced");
}
~~~

Reason: **asSlice** creates a sub-access contract. Header-processing code given only the header slice can avoid accidentally reading into the payload if all operations stay within the slice's access API.

Checked constraints:

1. **Constraint when creating slice**: offset/size must lie within the input segment.
2. **Constraint when reading/writing**: the entire region occupied by **ValueLayout** must lie within the slice. Reading **JAVA_INT** requires 4 full bytes starting from the access offset.
3. **Alignment constraint**: the access address matches the layout (covered in section 10).
4. **Lifetime/thread/read-only constraints**: cannot be bypassed by creating a smaller slice.

**asSlice is not a range-expanding operation.** If you need to access bytes outside the slice, the code owning the backing memory must provide an appropriate view, rather than trying to resize it with unsafe tricks.

## 7. Runnable example 2: native memory and Arena lifecycle

The difference between a heap slice and a native slice is not in data sharing: **both share backing storage**. The difference lies in the ownership and lifetime of the native memory region.

### File SliceNativeDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SliceNativeDemo {
    public static void main(String[] args) {
        MemorySegment escapedSlice;

        try (Arena arena = Arena.ofConfined()) {
            // 4 int values, 4 bytes each: 16 bytes.
            // Ensure base address is aligned for JAVA_INT.
            MemorySegment root = arena.allocate(
                    16, ValueLayout.JAVA_INT.byteAlignment());

            MemorySegment secondAndThird = root.asSlice(4, 8);

            // root offset 4 is the second int.
            root.set(ValueLayout.JAVA_INT, 4, 100);
            System.out.println("slice[0] = "
                    + secondAndThird.get(ValueLayout.JAVA_INT, 0));

            // slice offset 4 maps to root offset 8.
            secondAndThird.set(ValueLayout.JAVA_INT, 4, 777);
            System.out.println("root offset 8 = "
                    + root.get(ValueLayout.JAVA_INT, 8));

            System.out.println("slice size = "
                    + secondAndThird.byteSize());

            // Keep Java reference only to demonstrate error after close.
            escapedSlice = secondAndThird;
        }

        // Arena is closed; native memory is no longer alive.
        try {
            escapedSlice.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("access after arena close rejected");
        }
    }
}
~~~

Compile/run:

~~~bash
javac SliceNativeDemo.java
java SliceNativeDemo
~~~

Stdout when executed on JDK 22+:

~~~text
slice[0] = 100
root offset 8 = 777
slice size = 8
access after arena close rejected
~~~

Explanation:

- **Arena.ofConfined()** has an explicit lifecycle and allows access from the owning thread.
- **arena.allocate(16, 4)** allocates 16 native bytes with 4-byte alignment.
- **root.asSlice(4, 8)** is a view over bytes **4..11**. It **does not** create a second allocation.
- **secondAndThird.get(JAVA_INT, 0)** reads from **root offset 4** and gets **100**.
- **secondAndThird.set(JAVA_INT, 4, 777)** writes to **root offset 8**.
- At the end of **try-with-resources**, **arena.close()** expires the scope and frees the native memory owned by the arena. **Both root and all slices** are no longer permitted to be accessed.
- **escapedSlice** is just a Java reference to an expired view; still holding the reference does not keep the arena's native memory valid.

**There is no slice.close() operation.** Resources are managed by the arena/scope. Slicing a native segment **does not** grant separate ownership to the slice recipient, nor does it defer the arena's close deadline.

## 8. Scope: slice and root share the same lifetime

Suppose root is allocated in an arena with scope **S**:

~~~text
Arena scope S (alive)
    |
    +-- root: native memory [0, N)
    |      |
    |      +-- slice A: [20, 40)
    |      |
    |      +-- slice B: [40, 60)
    |               |
    |               +-- nested slice C
    |
    +-- all belong to the same scope S

arena.close()
    |
    +-- S is no longer alive
    +-- root, A, B, C are all disallowed from access
~~~

In JDK 22, **root.scope()** and **slice.scope()** are bound to the same source scope. This is the condition that prevents views from using a native allocation after it has been freed. If a native API requires a pointer to remain alive after your method returns, **do not** create a slice, close the arena, and hand that slice to the caller; you must design ownership, reference storage, and close timing from the start.

Some common arenas:

| Arena | Lifecycle/access contract | Consequence for slices |
| --- | --- | --- |
| **Arena.ofConfined()** | Scope managed by owner thread, explicitly closed | Slices have the same owner-thread restriction |
| **Arena.ofShared()** | Scope usable from multiple threads, explicitly closed | Slices accessible from multiple threads, but data still must be synchronized |
| **Arena.ofAuto()** | Scope automatically managed by GC | Slices do not have an explicit close point like confined/shared |
| **Arena.global()** | Global scope, not explicitly closed | Slices have global scope; use cautiously for long-lived resources |

Regardless of arena type, **asSlice does not change the lifecycle nature of the backing memory**. A heap segment from **MemorySegment.ofArray(...)** is not freed by **Arena.close()**; Java arrays are managed by GC.

## 9. Thread confinement: sharing data does not mean cross-thread use is allowed

On native memory belonging to **Arena.ofConfined()**, the access scope is restricted by the owning thread. A slice is not allowed to "escape" that restriction.

### Runnable example: another thread is rejected

**File SliceThreadDemo.java:**

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SliceThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment root = arena.allocate(8, 1);
            MemorySegment slice = root.asSlice(2, 3);

            Thread other = new Thread(() -> {
                try {
                    slice.get(ValueLayout.JAVA_BYTE, 0);
                } catch (WrongThreadException expected) {
                    System.out.println("confined slice rejects other thread");
                }
            });

            other.start();
            other.join();

            // Owner thread can still access.
            slice.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);
            System.out.println("root[2] = "
                    + root.get(ValueLayout.JAVA_BYTE, 2));
        }
    }
}
~~~

Compile/run on JDK 22+:

~~~bash
javac SliceThreadDemo.java
java SliceThreadDemo
~~~

Stdout:

~~~text
confined slice rejects other thread
root[2] = 7
~~~

**WrongThreadException** belongs to **java.lang**, implicitly imported like other classes in java.lang. It differs from **IndexOutOfBoundsException** and **IllegalStateException**: the issue is not out-of-bounds or a closed arena, but that the current thread does not have permission to access the segment.

If multiple threads truly need to access native memory together, use **Arena.ofShared()** and define how read/write operations are coordinated. **Shared scope allows access** but does not automatically guarantee **atomicity, ordering, or absence of data races**.

Conceptual example:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment root = arena.allocate(8, 1);
    MemorySegment slice = root.asSlice(2, 1);

    Thread worker = new Thread(() ->
            slice.set(ValueLayout.JAVA_BYTE, 0, (byte) 12));

    worker.start();
    worker.join();

    System.out.println(root.get(ValueLayout.JAVA_BYTE, 2)); // 12
}
~~~

This is a **fragment** placed inside a method that allows **throws InterruptedException**. **Thread.join()** ensures the worker has finished before the owner reads the result. In an application with multiple threads accessing concurrently, proper synchronization (locks/VarHandle or appropriate primitives) must be in place, rather than relying solely on using **asSlice**.

## 10. Alignment: asSlice does not make an arbitrary address valid

Slicing can produce a starting address unsuitable for a multi-byte data type. For example, **ValueLayout.JAVA_INT** requires the alignment specified by the layout (typically 4 bytes). The **asSlice(offset, size)** form only selects a byte range; reading/writing an **int** with the layout can fail if the address is unaligned.

### Illustrative fragment on 4-byte aligned native memory

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment root = arena.allocate(16, 4);

    // Base + 4 is 4-byte aligned: valid.
    MemorySegment aligned = root.asSlice(4, 8, 4);
    aligned.set(ValueLayout.JAVA_INT, 0, 123);

    // The 2-parameter form can create a view starting at byte 1.
    MemorySegment unaligned = root.asSlice(1, 8);

    // Reading int at address base+1 violates JAVA_INT alignment.
    try {
        unaligned.get(ValueLayout.JAVA_INT, 0);
    } catch (IllegalArgumentException expected) {
        System.out.println("misaligned int access rejected");
    }

    // Overload with alignment 4 checks immediately when creating the slice.
    try {
        root.asSlice(1, 8, 4);
    } catch (IllegalArgumentException expected) {
        System.out.println("misaligned slice rejected");
    }
}
~~~

This is a valid **fragment** when **Arena**, **MemorySegment**, **ValueLayout** are imported and run inside a Java method; there is no standalone **main** here. The root address is 4-aligned by the arena, so root+1 is definitely not 4-aligned. **byteAlignment** is not a parameter to "force the JVM to move" the slice's address. If the original position does not meet alignment, the API reports an error instead of copying data into a new buffer for proper alignment.

For heap segments, alignment depends on the backing array type and the alignment limits the runtime can guarantee. For example, a **byte[]** does not necessarily support reading **JAVA_LONG** with alignment 8 at any arbitrary offset. Do not use multi-byte structures and overly strict layouts on a heap byte[] without verifying the alignment contract; use an aligned native allocation or an appropriate layout.

**The MemoryLayout form** is convenient when splitting records:

~~~java
import java.lang.foreign.MemoryLayout;

MemoryLayout twoInts = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("first"),
        ValueLayout.JAVA_INT.withName("second"));

// root is a sufficiently large native segment with offset 8 aligned to twoInts.
// Creates a view with size and alignment matching the layout.
MemorySegment record = root.asSlice(8, twoInts);
~~~

This is a **fragment**: **root** is allocated elsewhere and must have appropriate size/alignment. **asSlice(offset, layout)** does not automatically deserialize the record and does not allocate a Java object holding the fields; it only creates a view with size/alignment according to the layout. Reading fields still requires **get**, **VarHandle**, or appropriate accessors.

## 11. Read-only: slice inherits write permissions, does not freeze backing memory

When calling:

~~~java
MemorySegment readOnlyParent = root.asReadOnly();
MemorySegment child = readOnlyParent.asSlice(2, 4);
~~~

**child.isReadOnly()** returns **true**. Calling **child.set(...)** will be rejected. However, read-only is a **property of the view**, not a command making the underlying bytes absolutely immutable. If **root** is still writable, code with access to **root** can continue modifying that memory region; the read-only view will **observe** the new data when reading again.

A short example:

~~~java
byte[] bytes = {1, 2, 3, 4};
MemorySegment root = MemorySegment.ofArray(bytes);
MemorySegment readOnly = root.asReadOnly().asSlice(1, 2);

System.out.println(readOnly.get(ValueLayout.JAVA_BYTE, 0)); // 2
root.set(ValueLayout.JAVA_BYTE, 1, (byte) 9);
System.out.println(readOnly.get(ValueLayout.JAVA_BYTE, 0)); // 9
~~~

This is a **fragment** requiring imports for **MemorySegment**, **ValueLayout** and placement inside a Java method. It demonstrates precisely two properties: **cannot write via readOnly**, yet **data is shared**.

If an application needs to guarantee that one party cannot affect data used by another party, providing only a read-only view **is not sufficient when the other party still holds a writable alias**. You must control all references/permissions, or use an independent non-aliased copy.

## 12. asSlice vs. copyFrom, MemorySegment.copy, and Arrays.copyOfRange

**asSlice**: creates a view, does not copy data, same backing memory.

**MemorySegment.copy**, **copyFrom**: performs an operation that **copies bytes** from a source region to a destination region. Whether the destination is independent depends on whether you allocate source and destination to alias each other; to get an **independent** copy, a **different** backing memory allocation is needed.

**Arrays.copyOfRange**: copies part of a Java array into a new Java array.

Runnable example on heap:

### File SliceVsCopyDemo.java

~~~java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public class SliceVsCopyDemo {
    public static void main(String[] args) {
        byte[] source = {5, 10, 15, 20, 25};
        MemorySegment root = MemorySegment.ofArray(source);

        MemorySegment view = root.asSlice(1, 3);
        byte[] independent = Arrays.copyOfRange(source, 1, 4);

        view.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);

        System.out.println("source: " + Arrays.toString(source));
        System.out.println("copy:   " + Arrays.toString(independent));
        System.out.println("view[0]: "
                + view.get(ValueLayout.JAVA_BYTE, 0));

        independent[1] = 77;
        System.out.println("after changing copy: "
                + Arrays.toString(source));
    }
}
~~~

Compile/run:

~~~bash
javac SliceVsCopyDemo.java
java SliceVsCopyDemo
~~~

Stdout:

~~~text
source: [5, 99, 15, 20, 25]
copy:   [10, 15, 20]
view[0]: 99
after changing copy: [5, 99, 15, 20, 25]
~~~

Reason: **view** aliases **source**'s data, while **independent** is a new array. Modifying **independent[1]** does not change source.

With native segments, you can allocate an independent region and copy:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment original = arena.allocate(8, 1);
    original.set(ValueLayout.JAVA_BYTE, 2, (byte) 11);

    MemorySegment view = original.asSlice(2, 3);

    MemorySegment separate = arena.allocate(view.byteSize(), 1);
    separate.copyFrom(view);

    view.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);

    System.out.println(original.get(ValueLayout.JAVA_BYTE, 2)); // 99
    System.out.println(separate.get(ValueLayout.JAVA_BYTE, 0)); // 11
}
~~~

This is a **fragment** needing FFM imports. **separate** is allocated in the same arena but in a **different backing region**, so it does not alias **original**. Being in the same arena only affects lifecycle, not meaning all allocations in the same arena share bytes. Both allocations are still freed when the arena closes.

**Cost comparison:** a slice is typically metadata/view creation, avoiding content copying; an independent copy pays allocation and copying costs, but in return reduces aliasing and helps control data. Decisions should be based on ownership, concurrency, lifetime, and measured performance; do not choose zero-copy at the expense of safety.

## 13. asSlice and ByteBuffer: two views on the same bytes

The **MemorySegment.asByteBuffer()** API can create a **ByteBuffer view** of the region represented by the segment (must satisfy the API's size and access state conditions). That ByteBuffer also **does not automatically copy** data. When modifying bytes via the buffer, the segment sees them, and vice versa.

Idea:

~~~java
import java.nio.ByteBuffer;

MemorySegment root = MemorySegment.ofArray(new byte[] {1, 2, 3, 4});
MemorySegment slice = root.asSlice(1, 2);
ByteBuffer buffer = slice.asByteBuffer();

buffer.put(0, (byte) 99);
System.out.println(root.get(ValueLayout.JAVA_BYTE, 1)); // 99

root.set(ValueLayout.JAVA_BYTE, 2, (byte) 88);
System.out.println(buffer.get(1)); // 88
~~~

This is a **fragment** requiring imports for **MemorySegment**, **ValueLayout**, **ByteBuffer**; the comments describe the output when run inside a Java method. Offset position **0** of **buffer** corresponds to offset **0** of **slice**, not offset **0** of root.

For an arena's native backing memory, the **ByteBuffer view** is also subject to the lifetime/thread constraints of the backing segment; keeping the ByteBuffer after the arena closes does not keep the memory alive. For a read-only MemorySegment, the corresponding buffer must also obey read-only constraints.

Difference: **ByteBuffer** maintains its own **position**, **limit**, **mark**, and has its own **slice()** API. Do not confuse **ByteBuffer.slice()** with **MemorySegment.asSlice()** even though both can create views over the same memory. Absolute operations **get(index)**/**put(index,value)** make the example easy to check offsets without being affected by position.

## 14. Using slice to split a message's header and payload

A real-world application receiving a buffer may consist of a **4-byte header** followed by a **payload** region. Instead of passing the entire root to the payload-handling function, we pass a slice restricted to the exact range.

Runnable Java 22+ example on heap:

### File PacketSlices.java

~~~java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public class PacketSlices {
    private static void uppercaseAscii(MemorySegment payload) {
        for (long i = 0; i < payload.byteSize(); i++) {
            byte value = payload.get(ValueLayout.JAVA_BYTE, i);
            if (value >= 'a' && value <= 'z') {
                payload.set(ValueLayout.JAVA_BYTE, i,
                        (byte) (value - 'a' + 'A'));
            }
        }
    }

    public static void main(String[] args) {
        byte[] bytes = {1, 0, 0, 3, 'c', 'a', 't'};
        MemorySegment packet = MemorySegment.ofArray(bytes);

        MemorySegment header = packet.asSlice(0, 4);
        MemorySegment payload = packet.asSlice(4);

        System.out.println("header bytes: " + header.byteSize());
        System.out.println("payload bytes: " + payload.byteSize());

        uppercaseAscii(payload);

        System.out.println("packet: " + Arrays.toString(bytes));
        System.out.println("payload text: "
                + (char) payload.get(ValueLayout.JAVA_BYTE, 0)
                + (char) payload.get(ValueLayout.JAVA_BYTE, 1)
                + (char) payload.get(ValueLayout.JAVA_BYTE, 2));
    }
}
~~~

Compile/run:

~~~bash
javac PacketSlices.java
java PacketSlices
~~~

Stdout:

~~~text
header bytes: 4
payload bytes: 3
packet: [1, 0, 0, 3, 67, 65, 84]
payload text: CAT
~~~

Explanation: the first four bytes are left untouched, and the three ASCII bytes of the payload change from **c a t** to **C A T**. The original array changes at offsets **4, 5, 6**; no data is copied to another array.

The example only illustrates splitting **known** regions; it does not decode a real header, does not validate a payload length provided by an untrusted source, and does not replace a full protocol parser. With real input, you must validate header size, length fields, and total bounds before creating a slice.

A function can safely create a slice from a packet-provided length:

~~~java
static MemorySegment payloadView(
        MemorySegment whole, long headerBytes, long payloadBytes) {
    if (headerBytes < 0 || payloadBytes < 0
            || headerBytes > whole.byteSize()
            || payloadBytes > whole.byteSize() - headerBytes) {
        throw new IllegalArgumentException("invalid packet lengths");
    }
    return whole.asSlice(headerBytes, payloadBytes);
}
~~~

This is a **fragment** needing **MemorySegment** import. The condition **payloadBytes > whole.byteSize() - headerBytes** avoids the addition **headerBytes + payloadBytes** which could overflow. The returned slice still aliases root; if you want the data to be immutable for the recipient, consider creating an independent copy.

## 15. Slices are independent in bounds, but not independent in ownership

When sharing a MemorySegment across multiple functions or components, three responsibilities should be distinguished:

**Backing memory ownership:** who allocates and who is allowed to close the arena? A slice only borrows a view; it does not have the right to arbitrarily close the resource or hold it indefinitely.

**Allowed access range:** a function that only processes the payload should receive the payload slice; it does not need the entire root. This reduces the risk of accidentally accessing the header/trailer through the provided view itself.

**Write permission and result publication timing:** a writable slice aliases all data in its range. If processing code can fail after partial writes, the backing memory may already have changed; **asSlice does not provide rollback**. You can use a read-only view for code that does not need to write, or copy into a separate buffer before committing the result.

A cleaner API design:

~~~java
// Receives only the region to read; unaware of the rest of root.
static int checksum(MemorySegment payload) {
    int sum = 0;
    for (long i = 0; i < payload.byteSize(); i++) {
        sum += Byte.toUnsignedInt(
                payload.get(ValueLayout.JAVA_BYTE, i));
    }
    return sum;
}
~~~

This is a **fragment** needing **MemorySegment**, **ValueLayout** imports. The **int sum** type can overflow for very long arrays; if a business checksum requires no overflow or a specific modulo, choose an appropriate algorithm/data type. The snippet primarily illustrates the contract of accepting a subview.

Accepting a slice instead of root does not create a *complete security sandbox*: if the component still holds a reference to root or another alias, it can still access a wider region. However, an input-bounded API makes the design easier to understand and verify.

## 16. Overlapping slices: two overlapping views can affect each other

Two slices **do not need to have the same offset** to share some bytes. For example:

~~~text
root offsets:  0  1  2  3  4  5  6  7  8
slice A:          [1  2  3  4]
slice B:                [3  4  5  6]
overlap:                 3  4
~~~

If **A = root.asSlice(1, 4)** and **B = root.asSlice(3, 4)**, the overlapping region is **root offsets 3 and 4**. Modifying **A[2]** corresponds to **root[3]**; **B[0]** sees that value.

Test snippet:

~~~java
byte[] data = {0, 1, 2, 3, 4, 5, 6};
MemorySegment root = MemorySegment.ofArray(data);
MemorySegment a = root.asSlice(1, 4);
MemorySegment b = root.asSlice(3, 4);

a.set(ValueLayout.JAVA_BYTE, 2, (byte) 99);

System.out.println(b.get(ValueLayout.JAVA_BYTE, 0)); // 99
~~~

This is a **fragment** needing corresponding imports. If multiple threads write to overlapping slices, they cannot be treated as independent regions. You need to divide responsibility by **byte range**, apply synchronization, or allocate separately if independence is required. **Non-overlapping** slices in the same arena can reduce content contention but still share the same lifecycle and thread-access restrictions.

## 17. Common mistakes when applying asSlice

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Thinking asSlice creates a new copy | Writing through slice unexpectedly alters root | Use a new allocation/array and copy data if separation is needed |
| Using int element count as offset | Slicing at wrong byte position; reading wrong data or misaligned | Compute **elementIndex * layout.byteSize()** with overflow check |
| Passing root offset to **slice.get** | Out of bounds because slice starts at offset 0 | Compute offset relative to the slice |
| Believing slice can read because root still has bytes | Causes **IndexOutOfBoundsException** | Check **slice.byteSize()** and layout width |
| Assuming **asSlice(offset,size)** handles alignment automatically | Multi-byte **get/set** may throw **IllegalArgumentException** | Align allocation and offset; choose appropriate layout |
| Using slice after **Arena.close()** | **IllegalStateException** or access rejected | Keep arena alive throughout view usage |
| Passing slice from confined arena across threads | **WrongThreadException** | Use owner thread or shared arena with synchronization |
| Keeping a writable alias when immutable data is desired | Read-only view still sees data modified from another alias | Control ownership or create a copy |
| Skipping synchronization because of shared arena | Data race, inconsistent observed state | Design appropriate happens-before/locking/VarHandle |
| Treating slice as a freeable C pointer | Wrong native memory ownership | Close arena per contract, do not manually free a slice's pointer |
| Reading **JAVA_INT** from a heap byte[] without considering alignment | Access may be rejected | Use appropriate layout and backing |
| Passing view across API and implicitly closing arena too early | Recipient holds dangling view | Document ownership, lifetime, and API scope clearly |

## 18. Design checklist when passing slices across modules

Before handing a MemorySegment slice to other code, clearly state:

1. **Memory source:** heap array, native allocation, memory-mapped file, or direct buffer?
2. **Byte range:** how many bytes from root does it start, how many bytes long is it, is zero-length allowed?
3. **Alignment and layout:** what alignment does each field need? Which endianness if reading multiple bytes?
4. **Write permission:** read-only view or writable view? Are there other aliases that can still write?
5. **Lifetime:** which arena owns it, who is allowed to call **close()**, is it guaranteed to live through callbacks/asynchronous tasks?
6. **Thread access:** confined, shared, heap, or global? Is there a corresponding synchronization mechanism?
7. **Copy or alias:** does the caller accept mutating root? Is a copy needed for a stable snapshot?
8. **Length validation:** are offset/size coming from untrusted data validated before creating the view?

Example contract that can be written next to a method:

~~~java
/*
 * payload: view aliasing caller's backing memory.
 * Caller must keep scope alive throughout the call.
 * Function only reads bytes in [0, payload.byteSize()).
 * Does not retain reference after returning.
 * Does not require use from another thread.
 */
static long sumUnsignedBytes(MemorySegment payload) {
    long sum = 0;
    for (long i = 0; i < payload.byteSize(); i++) {
        sum += Byte.toUnsignedInt(
                payload.get(ValueLayout.JAVA_BYTE, i));
    }
    return sum;
}
~~~

This is a **fragment**; in a real application, conditions for oversized data/overflow must be added if the sum result is a business-critical factor. Writing the contract clearly helps callers avoid closing the Arena while an asynchronous task still holds the view.

## 19. Self-check questions and exercises

**Question 1.** Root is **16 bytes** long. What size and offset range does **root.asSlice(5, 6)** have?

**Answer:** **byteSize() = 6**, representing bytes **root[5]..root[10]**. Valid offsets in the slice are **0..5**.

**Question 2.** If **root.asSlice(5,6).asSlice(2,3)**, which root offset does offset **1** in the final slice correspond to?

**Answer:** **5 + 2 + 1 = 8**. All offsets are added at each view level.

**Question 3.** A slice has size 4 bytes and root has size 100 bytes. Can you read 8 bytes with **ValueLayout.JAVA_LONG** at offset 0 of the slice?

**Answer:** **No**. The slice only allows 4 bytes; an 8-byte access exceeds the slice's bounds even though root has plenty of data.

**Question 4.** If code writes **slice.set(JAVA_BYTE,0,7)**, can root see that value?

**Answer:** **Yes**, if slice/root share backing memory, are alive, writable, and have access permission. Reading root at the corresponding offset will get the new value according to appropriate synchronization rules.

**Question 5.** Two slices are created from the same arena but from **two independent arena.allocate calls**; are they guaranteed to share bytes?

**Answer:** **No**. Sharing an arena only means sharing the lifetime management scope; two separate allocations still have separate backing regions.

**Question 6.** Why does keeping a **slice** in a Java field not prevent errors after closing **Arena.ofConfined()**?

**Answer:** The field holds a reference to the view, not extending the lifetime of the native allocation that has been freed. Access operations after close are rejected.

**Question 7.** Does a read-only slice automatically guarantee that the underlying data never changes?

**Answer:** **No**. It forbids writing through the read-only view, not forbidding another writable alias from modifying the backing memory.

**Question 8.** Using **asSlice(3, 8, 4)** on a native root whose starting address is a multiple of 4: what is the result?

**Answer:** Cannot create an aligned view at offset 3 with alignment 4 because address base+3 is not aligned; the API throws **IllegalArgumentException**.

**Question 9.** A native root is created with **Arena.ofConfined()** and then a slice is passed to another thread. Can this be solved by calling **asSlice** again on the receiving thread?

**Answer:** **No**. Slices inherit scope/thread restrictions; use the owner thread or design with **Arena.ofShared()** and synchronization.

**Exercise A:** Replace **root.asSlice(2,3)** in the heap example with **root.asSlice(2)**. Predict **byteSize()** and valid offsets; run to verify. Expected result: **byteSize() == 4**, offsets **0..3**.

**Exercise B:** Create two views **root.asSlice(1,3)** and **root.asSlice(2,3)**. Write to the first view at offset 1; predict the corresponding offset in the second view. Result: shared byte at **root[2]**, which is offset **0** of the second view.

**Exercise C:** In the native demo, replace **root.asSlice(4,8)** with **root.asSlice(4,12)** on the 16-byte root; verify this is a valid slice, yet accessing from offset **12** with **JAVA_INT** is still rejected because it is outside the allocated part. Result: **asSlice(4,12)** is valid, **get(JAVA_INT,12)** needs 4 bytes outside the view so it throws **IndexOutOfBoundsException**.

**Exercise D:** Create an independent 3-byte copy of a view and then modify the view. Print both to explain why the copy retains the old values.

## Official References

- Java SE 22 API — **MemorySegment**, including **asSlice**, **byteSize**, **scope**, **isReadOnly**, **get/set**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html
- Java SE 22 API — **Arena** and confined/shared/auto/global scopes: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html
- Java SE 22 API — **ValueLayout** and byte alignment: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html
- Dev.java — **Access Off-Heap or On-Heap Memory with Memory Segments**: https://dev.java/learn/api/io/ffm/access-memory/
- OpenJDK **JEP 454: Foreign Function & Memory API** (finalized in JDK 22): https://openjdk.org/jeps/454

**Remember:** **asSlice creates a view, not a copy**. The slice and root segment share backing memory, so reads/writes reflect on the same bytes. A slice **narrows bounds**, but **does not create a new lifetime, new thread permission, new write permission, or new synchronization guarantee**. To get independent data, you must allocate separate backing memory and copy; to handle native memory safely, you must respect arena, offset, layout, and ownership.