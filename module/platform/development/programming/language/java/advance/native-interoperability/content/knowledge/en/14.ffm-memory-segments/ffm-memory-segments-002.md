# Address, Size, Scope, and Alignment of a MemorySegment

## 1. Lesson Objectives and Java Version

When working with native code or off-heap memory, a C pointer of type `void*` only tells you the address. It **does not self-describe** how long the memory region is, how long it remains valid, or whether it has sufficient alignment to read an `int`/`long` or a C struct. Out-of-bounds reads, use-after-`free` accesses, and reads from unaligned addresses are common sources of bugs in native code.

In the Foreign Function & Memory API (FFM), Java represents a memory region using **`java.lang.foreign.MemorySegment`**. A segment is not just a number holding an address; it is a **constrained view**. The four most important characteristics of a segment are:

1. **Address (`address`):** where does the memory region start in the segment's address model?
2. **Size (`byteSize`):** how many bytes maximum does this view allow accessing?
3. **Scope (`scope`):** are the memory region and access rights still valid or have they ended? Is it restricted by thread?
4. **Alignment (`maxByteAlignment` and `MemoryLayout.byteAlignment`):** is the accessed address compatible with the expected representation and read/write operation?

After completing this lesson, you should be able to explain the difference between **native and heap segments**, create segments with required size and alignment, use `asSlice` to restrict a view, read/write using `ValueLayout`, determine when access is blocked due to out-of-bounds/scope/thread/alignment, and avoid turning a native address into an unsafe pointer.

**Version requirements:** the examples use the standard `java.lang.foreign` API, finalized in **JDK 22** (JEP 454) and run on **JDK 22+**. JDK 17 has the Foreign Memory API in an *incubator* state with a different package/API; you cannot copy the code below directly to JDK 17 and just add an import. Examples operating on `Arena.allocate` and safe `MemorySegment.get/set` do not require `--enable-preview` on JDK 22+.

## 2. Visual Model: A Memory View with Four Constraints

Suppose an arena allocates 32 bytes, with an 8-byte alignment:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(32, 8);
    // Use the segment while the arena is open.
}
```

You can visualize it as:

```text
Native address: A (A is divisible by 8)
                  |
                  v
        +---------+-------------------------------------------+
        | byte 0  | byte 1 ...                ... byte 31    |
        +-----------------------------------------------------+
          <----------------- 32 bytes --------------------->

MemorySegment
  address()            = A             (address value depends on the run)
  byteSize()           = 32            (unit: bytes, not number of elements)
  scope()              = the arena's scope
  maxByteAlignment()   >= 8            (actual maximum alignment may be larger)
```

If you create a slice:

```java
MemorySegment slice = segment.asSlice(8, 8);
```

then the slice starts at `A + 8`, is only 8 bytes long, and **shares the backing memory and scope** with the original segment. A slice **does not allocate its own memory region** and **does not own a separate `free`**.

The four factors must be considered simultaneously:

| Factor | Main API | What is guaranteed or restricted |
| --- | --- | --- |
| Starting location | `segment.address()` | Returns a `long` value representing the address depending on the segment type |
| View size | `segment.byteSize()` | Accesses are checked within bounds `[0, byteSize)` |
| Lifecycle | `segment.scope()`, `scope().isAlive()` | Access is denied when the scope is no longer alive; the arena determines the native allocation lifecycle |
| Available alignment | `segment.maxByteAlignment()` | The maximum alignment level the segment supports; access must also satisfy the specific layout and offset |
| Thread permission | `segment.isAccessibleBy(thread)` | Indicates whether the thread matches the segment's confinement |
| Data type | `ValueLayout` / `MemoryLayout` | Interprets the number of bytes to read, byte order, alignment, field offset |

**Do not confuse:** `MemorySegment` is not an ordinary `byte[]` and is also not like an unbounded C pointer. The API's safe access methods perform the relevant checks before reading/writing.

## 3. Address: Native Segments Differ from Heap Segments

### 3.1. Native segment

A native segment created by `Arena.allocate` typically refers to **off-heap memory**. `segment.address()` is the starting address of the native memory region, represented as a `long`:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16, 8);
    long address = segment.address();

    System.out.println(segment.isNative()); // true
    System.out.println(address % 8 == 0);    // true
}
```

**Do not hardcode specific addresses in tests.** Address values vary by process, allocation, operating system, architecture, and ASLR. `address()` is usually an address in the **process's native address space**, not a guarantee of a fixed physical RAM address.

An address may still be a non-zero number **after the backing memory has been freed**. That `long` value does not own the resource, does not keep the scope alive, and does not by itself grant access. Reusing a raw address after closing the arena risks use-after-free.

### 3.2. Heap segment

`MemorySegment.ofArray` creates a segment backed by a primitive array in the Java heap:

```java
byte[] data = new byte[16];
MemorySegment heap = MemorySegment.ofArray(data);

System.out.println(heap.isNative()); // false
System.out.println(heap.address());  // 0
System.out.println(heap.byteSize()); // 16
```

The address `0` of the newly created heap segment does **not** mean it is a C `NULL` pointer. According to the API, a heap segment's address is a **virtualized offset within the backing storage**, not a machine address that can be passed directly to a C function. When taking `heap.asSlice(4, 8)`, the slice's `address()` reflects the corresponding offset in the backing storage.

The garbage collector may move the actual array in the Java heap; FFM hides that physical location and provides a view according to the heap segment model. Do not take `heap.address()` and cast it to a native pointer.

Segments created from arrays such as `int[]`, `long[]` also have `byteSize()` measured in **bytes**:

```java
MemorySegment ints = MemorySegment.ofArray(new int[5]);
System.out.println(ints.byteSize()); // 20: 5 ints, 4 bytes each
```

Heap segments have a scope that automatically keeps the backing array reachable consistent with the view's lifecycle; they are not native allocations owned by `Arena.ofConfined` and are not "freed" by closing an unrelated arena.

### 3.3. Address Does Not Imply Ownership or Bounds

FFM also has `MemorySegment.ofAddress(long)` to create a **0-byte native segment**, attached to the global scope. When its length is 0, any read with a positive size is caught by bounds checking.

`MemorySegment.NULL` is similarly a zero-length null address representation, **not a usable buffer**. `reinterpret(...)` can expand a view from a raw address, but it is a **restricted/unsafe** operation when assigning size or scope; if the address/size/lifecycle values are declared incorrectly, the initial guarantees are broken and it can crash the JVM or corrupt memory. This lesson does not use `reinterpret` to "bypass" checks.

**Practical rule of thumb:** keep the `MemorySegment` together with its scope for as long as possible; only pass raw addresses to native code when truly necessary, clearly understanding the ABI and which side owns freeing.

## 4. Size: byteSize Establishes Access Boundaries

### 4.1. byteSize Is Always Measured in Bytes

`segment.byteSize()` returns `long`, not `int` and not the number of elements. For example, for a 32-byte segment:

- Reading `JAVA_BYTE` (1 byte) at offset 31: may be valid.
- Reading `JAVA_INT` (4 bytes) at offset 28: right on the boundary **if alignment is valid**.
- Reading `JAVA_LONG` (8 bytes) at offset 24: right on the boundary **if alignment is valid**.
- Reading `JAVA_LONG` at offset 32: **out of bounds**, because it needs bytes 32…39 outside the view.

The logical boundary condition for an access with `offset` and `layout.byteSize()` is:

```text
offset >= 0
layout.byteSize() >= 0
layout.byteSize() <= segment.byteSize() - offset
```

The API performs checks to prevent out-of-bounds access, including cases where offset/size cannot be safely represented. Do not replace this with `offset + length <= byteSize` in Java code without controlling overflow.

### 4.2. The Offset of get/set Is a Byte Offset

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment s = arena.allocate(16, 8);

    s.set(ValueLayout.JAVA_INT, 0, 123);
    s.set(ValueLayout.JAVA_INT, 4, 456);

    System.out.println(s.get(ValueLayout.JAVA_INT, 0)); // 123
    System.out.println(s.get(ValueLayout.JAVA_INT, 4)); // 456
}
```

Here, the second parameter of `get/set` is a **byte offset**, not "the 0th/1st/2nd element". If you want an element index, `getAtIndex(ValueLayout.JAVA_INT, i)` multiplies `i` by the layout size, while still being subject to bounds and alignment checks.

Byte order also belongs to `ValueLayout`; for example, `JAVA_INT` uses native byte order, while `ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN)` interprets 4 bytes as big-endian. Byte order and alignment are **two different constraints**.

### 4.3. Slicing: Restricting the View Without Copying

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment whole = arena.allocate(32, 8);
    MemorySegment part = whole.asSlice(8, 8);

    part.set(ValueLayout.JAVA_INT, 0, 99);

    System.out.println(part.byteSize());                    // 8
    System.out.println(whole.get(ValueLayout.JAVA_INT, 8)); // 99
}
```

`part` and `whole` view the **same backing storage**. `part` starts at offset 8 of `whole`, but accesses on `part` use offsets **relative to part**: `part.get(..., 0)` is `whole.get(..., 8)`.

`asSlice` does not create a new arena or native allocation. The slice inherits the scope, liveness condition, and thread restrictions from the source. When the arena closes, both `part` and `whole` become inaccessible.

## 5. Scope: Temporal Boundaries and Thread Access Rights

### 5.1. What Is a Scope?

Every `MemorySegment` is attached to a `MemorySegment.Scope`, queried via:

```java
MemorySegment.Scope scope = segment.scope();
boolean alive = scope.isAlive();
```

`isAlive()` is the **current state** of the scope. When the scope of an explicitly closed arena is invalidated, the associated segments are no longer allowed to be accessed. Importantly: a single check `isAlive() == true` **cannot replace** the API's atomic/concurrency checks if another thread has permission to close the arena immediately afterward.

**Spatial safety** checks the address and `byteSize`; **temporal safety** checks whether the scope is still valid at the time of access. These are two independent layers of protection.

### 5.2. Four Common Arena Types

| Arena | Allocated memory lifecycle | Explicitly closed with `close()`? | Thread access rights |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Ends when the arena is closed | **Yes** | Only the thread that created the arena can access and close |
| `Arena.ofShared()` | Ends when the arena is closed | **Yes** | Multiple threads can access; requires lifecycle coordination/data synchronization |
| `Arena.ofAuto()` | GC-managed, reclamation time is unpredictable | **No**; calling close throws `UnsupportedOperationException` | No owner thread restriction |
| `Arena.global()` | No API-managed endpoint; backing allocation lives indefinitely | **No**; close is not supported | No owner thread restriction |

**Do not confuse `Arena.ofAuto` with "auto-close when leaving a Java scope".** It is merely a **GC-managed** lifetime, with no guaranteed resource reclamation deadline. For large native memory or resources that need timely release, prefer a closeable arena and `try-with-resources`.

`Arena.global()` is used when a region genuinely needs to live for the entire process; allocating arbitrarily with the global arena can keep native memory until the process exits.

### 5.3. Closing an Arena Invalidates All Segments Sharing Its Scope

```java
MemorySegment s;
try (Arena arena = Arena.ofConfined()) {
    s = arena.allocate(8, 8);
    s.set(ValueLayout.JAVA_LONG, 0, 10L);
    System.out.println(s.scope().isAlive()); // true
} // arena.close() is called automatically at the end of try-with-resources

System.out.println(s.scope().isAlive()); // false
s.get(ValueLayout.JAVA_LONG, 0);          // IllegalStateException
```

The snippet above **demonstrates an exception**, not an example that runs normally to the end. In the complete runnable program in section 7, this exception is caught with `catch` to demonstrate it.

**A very common point of confusion:** keeping the Java variable `s` does not keep the backing native allocation valid after `arena.close()`. The Java object representing the view may still be alive, while the native memory region has already been freed.

`Arena.close()` is **not idempotent**: if you try to close the same arena a second time after it has already been closed, the API throws `IllegalStateException`. This is intentional to detect lifecycle bugs; do not assume it behaves like every other wrapper's `close()`.

### 5.4. Thread Confinement Is Also Checked on Access

With `Arena.ofConfined()`, a thread that is not the owner cannot read/write a segment from that arena, even when `scope().isAlive()` is true. An access from the wrong thread may be rejected with `WrongThreadException`.

With `Arena.ofShared()`, multiple threads can access the segment, but it **does not automatically synchronize data**. The application must still resolve data races and avoid closing the arena while a thread is using the resource. A shared arena's `Arena.close()` may fail if there is concurrent access that cannot be safely closed.

You can check thread accessibility with `segment.isAccessibleBy(Thread.currentThread())`; this is an access permission check, **not** a guarantee that bytes are within bounds or that the layout is aligned.

## 6. Alignment: What Must the Address Be Divisible By?

### 6.1. Alignment Is Expressed in Bytes and Is Usually a Power of Two

`N`-byte alignment means the target address is divisible by `N`. For example:

| Illustrative address | Multiple of 2? | Multiple of 4? | Multiple of 8? |
| --- | --- | --- | --- |
| 1000 | Yes | Yes | Yes |
| 1004 | Yes | Yes | No |
| 1006 | Yes | No | No |
| 1007 | No | No | No |

To allocate a 32-byte region aligned to at least an 8-byte boundary:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment s = arena.allocate(32, 8);
    System.out.println(s.address() % 8 == 0); // true
}
```

`Arena.allocate(byteSize, byteAlignment)` requires an alignment that is **positive and a power of 2**. For example, `arena.allocate(32, 3)` throws `IllegalArgumentException`; `arena.allocate(32, 8)` is valid. The size `byteSize` and alignment are **two independent parameters**: allocating 32 bytes aligned to 8 does not mean every 8 bytes is an element.

### 6.2. maxByteAlignment Differs from the Allocation Alignment Request

`segment.maxByteAlignment()` returns the **maximum alignment that the segment supports**, derived from the segment's address and the type of backing storage; it is always a power of two.

Suppose an arena allocates with `byteAlignment = 8`:

- The API guarantees **at least** 8-byte alignment.
- `maxByteAlignment()` can be 8 or **larger** (for example, the address happens to be divisible by 16, 32…), so do not test `maxByteAlignment() == 8`.
- With `s.asSlice(1, 8)`, the slice's address is offset by 1 byte from the 8-aligned base. If the base is divisible by 8, a slice offset by 1 has `maxByteAlignment() == 1`.
- A slice at offset 8 can continue to be 8-aligned.

A quick condition to check whether a segment is compatible **right at its base** with a layout:

```java
boolean baseAcceptsLayout =
        segment.maxByteAlignment() >= layout.byteAlignment();
```

However, for an access at a non-zero `offset`, you must consider the **target address (`address + offset`)**, not just the base. The `segment.get(layout, offset)` API checks the alignment of the specific access as well.

### 6.3. Layout Specifies Size, Alignment, and Byte Order

`ValueLayout` describes how bytes are interpreted. Some common layouts:

| Layout | Size | Default alignment |
| --- | ---: | ---: |
| `ValueLayout.JAVA_BYTE` | 1 byte | 1 byte |
| `ValueLayout.JAVA_SHORT` | 2 bytes | 2 bytes |
| `ValueLayout.JAVA_INT` | 4 bytes | 4 bytes |
| `ValueLayout.JAVA_LONG` | 8 bytes | 8 bytes |
| `ValueLayout.JAVA_FLOAT` | 4 bytes | 4 bytes |
| `ValueLayout.JAVA_DOUBLE` | 8 bytes | 8 bytes |

Example of a native segment whose base is divisible by 8:

```java
MemorySegment s = arena.allocate(16, 8); // arena is created outside this snippet

s.set(ValueLayout.JAVA_LONG, 0, 11L); // valid alignment
s.set(ValueLayout.JAVA_INT, 8, 22);   // valid alignment
s.get(ValueLayout.JAVA_INT, 1);       // IllegalArgumentException (misaligned)
```

Offsets 0, 8, and 1 are all **within bounds** of the 16-byte segment considering the read lengths alone; however, offset 1 does not satisfy the 4-byte alignment for `JAVA_INT`. Therefore, **in-bounds does not imply aligned**.

### 6.4. Unaligned Layout: Can Be Allowed, But Must Be Intentional

JDK 22+ provides `ValueLayout.JAVA_INT_UNALIGNED`, `JAVA_LONG_UNALIGNED`, and similar layouts with `byteAlignment() == 1`.

```java
byte[] raw = new byte[16];
MemorySegment heap = MemorySegment.ofArray(raw);

// byte[] only supports maximum alignment 1.
int safe = heap.get(ValueLayout.JAVA_INT_UNALIGNED, 0);

// With default JAVA_INT (alignment 4), access on a heap byte[]
// will throw IllegalArgumentException.
```

When data is in a packed or network format, unaligned access can be useful; however, you must consider **endianness, ABI, performance, and portability**. An unaligned layout is not a way to "fix" an incorrect native struct declaration. Some atomic/VarHandle operations also require aligned addresses and cannot be arbitrarily used on unaligned regions.

**Important distinction:** `ValueLayout.JAVA_INT_UNALIGNED` changes the alignment constraint of the **read/write operation**, does not change the actual byte positions, does not automatically fix C struct packing, and does not reallocate memory.

### 6.5. Heap Alignment Depends on the Array Type

A heap segment having a virtualized address of `0` **does not mean every alignment is valid**. A heap segment's `maxByteAlignment()` also depends on the backing primitive array type:

- `MemorySegment.ofArray(new byte[16])` has max alignment 1.
- `MemorySegment.ofArray(new int[4])` typically has max alignment matching `ValueLayout.JAVA_INT`, i.e., 4.
- `MemorySegment.ofArray(new long[2])` has max alignment matching `ValueLayout.JAVA_LONG`, i.e., 8.

Do not use arithmetic division `heap.address() % 8 == 0` to conclude that a heap `byte[]` supports an 8-byte layout. For heap segments, `address()` is a virtualized offset; you must rely on **`maxByteAlignment()` and the layout**.

## 7. Runnable Java 22+ Example: Checking All 4 Properties

### 7.1. Create SegmentFacts.java

The program below operates on a 32-byte 8-aligned native segment, creates a slice, reads/writes primitive types, tests alignment and bounds errors, compares with a heap segment, and then checks the scope after closing the arena.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SegmentFacts {
    public static void main(String[] args) {
        MemorySegment segment;
        MemorySegment slice;

        try (Arena arena = Arena.ofConfined()) {
            segment = arena.allocate(32, 8);
            slice = segment.asSlice(8, 8);

            segment.set(ValueLayout.JAVA_LONG, 0, 0x0102030405060708L);
            slice.set(ValueLayout.JAVA_INT, 0, 123456);

            System.out.println("Native: " + segment.isNative());
            System.out.println("Size: " + segment.byteSize());
            System.out.println("Base aligned to 8: "
                    + (segment.address() % 8 == 0));
            System.out.println("Max alignment at least 8: "
                    + (segment.maxByteAlignment() >= 8));
            System.out.println("Scope alive: " + segment.scope().isAlive());
            System.out.println("Slice size: " + slice.byteSize());
            System.out.println("Slice address delta: "
                    + (slice.address() - segment.address()));

            System.out.println("Long at 0: "
                    + Long.toHexString(segment.get(ValueLayout.JAVA_LONG, 0)));
            System.out.println("Int at 8: "
                    + segment.get(ValueLayout.JAVA_INT, 8));

            try {
                segment.get(ValueLayout.JAVA_INT, 1);
            } catch (IllegalArgumentException expected) {
                System.out.println("Misaligned: blocked");
            }

            try {
                segment.get(ValueLayout.JAVA_LONG, 32);
            } catch (IndexOutOfBoundsException expected) {
                System.out.println("Out of bounds: blocked");
            }

            MemorySegment heap = MemorySegment.ofArray(new byte[16]);
            System.out.println("Heap native: " + heap.isNative());
            System.out.println("Heap base address: " + heap.address());
            System.out.println("Heap max alignment: "
                    + heap.maxByteAlignment());

            try {
                heap.get(ValueLayout.JAVA_INT, 0);
            } catch (IllegalArgumentException expected) {
                System.out.println("Heap aligned int: blocked");
            }
            System.out.println("Heap unaligned int: "
                    + heap.get(ValueLayout.JAVA_INT_UNALIGNED, 0));
        }

        System.out.println("Scope alive after close: "
                + segment.scope().isAlive());
        try {
            segment.get(ValueLayout.JAVA_LONG, 0);
        } catch (IllegalStateException expected) {
            System.out.println("After close: blocked");
        }
    }
}
```

**Run commands** (JDK 22+, no JNI library or C compiler needed):

```bash
javac SegmentFacts.java
java SegmentFacts
```

**Verified stdout on JDK 24 (without printing raw native address):**

```text
Native: true
Size: 32
Base aligned to 8: true
Max alignment at least 8: true
Scope alive: true
Slice size: 8
Slice address delta: 8
Long at 0: 102030405060708
Int at 8: 123456
Misaligned: blocked
Out of bounds: blocked
Heap native: false
Heap base address: 0
Heap max alignment: 1
Heap aligned int: blocked
Heap unaligned int: 0
Scope alive after close: false
After close: blocked
```

Reading each point:

1. `arena.allocate(32, 8)` creates a 32-byte off-heap segment, with base divisible by 8; `maxByteAlignment` may be >8, so it prints the "at least" condition.
2. `segment.asSlice(8, 8)` has `byteSize = 8` and an address 8 bytes from the base.
3. `slice.set(JAVA_INT, 0, ...)` writes at offset 8 of the parent, so `segment.get(JAVA_INT, 8)` sees `123456`.
4. `segment.get(JAVA_INT, 1)` is blocked by 4-byte alignment, even though offset 1 is still within the 32-byte view.
5. `segment.get(JAVA_LONG, 32)` exceeds the 32-byte limit and throws `IndexOutOfBoundsException`.
6. Heap `byte[]` has virtualized address 0 and max alignment 1; `JAVA_INT` is rejected, while `JAVA_INT_UNALIGNED` validly reads 4 zero bytes.
7. At the end of `try`, the arena closes; `scope().isAlive() == false` and reading again throws `IllegalStateException`.

Do not predict or compare **specific numeric native addresses** in tests: that is environment-dependent data. For the Java array `new byte[16]` in the example, a heap base address of 0 is part of the `ofArray` specification.

## 8. Standalone Example: Slice Losing Alignment and Thread Access Rights

Create **SegmentThreadFacts.java**:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SegmentThreadFacts {
    public static void main(String[] args) throws InterruptedException {
        try (Arena confined = Arena.ofConfined()) {
            MemorySegment seg = confined.allocate(16, 8);
            MemorySegment misaligned = seg.asSlice(1, 8);

            System.out.println("Slice max alignment: "
                    + misaligned.maxByteAlignment());

            try {
                misaligned.get(ValueLayout.JAVA_LONG, 0);
            } catch (IllegalArgumentException expected) {
                System.out.println("Slice aligned long: blocked");
            }

            Thread worker = new Thread(() -> {
                try {
                    seg.get(ValueLayout.JAVA_BYTE, 0);
                    System.out.println("Unexpected confinement success");
                } catch (WrongThreadException expected) {
                    System.out.println("Confined other thread: blocked");
                }
            });
            worker.start();
            worker.join();
        }

        try (Arena shared = Arena.ofShared()) {
            MemorySegment seg = shared.allocate(8);
            Thread worker = new Thread(() -> {
                seg.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);
                System.out.println("Shared other thread: "
                        + seg.get(ValueLayout.JAVA_BYTE, 0));
            });
            worker.start();
            worker.join();
        }
    }
}
```

**Run:**

```bash
javac SegmentThreadFacts.java
java SegmentThreadFacts
```

**Verified stdout on JDK 24:**

```text
Slice max alignment: 1
Slice aligned long: blocked
Confined other thread: blocked
Shared other thread: 7
```

Explaining the two different aspects:

- `misaligned` starts at base + 1, so its max alignment is 1. It is still **within the parent's 16-byte bounds**, and the scope is alive, but reading `JAVA_LONG` at offset 0 does not satisfy 8-byte alignment.
- With `Arena.ofConfined()`, the new thread does not have permission to access the segment of the thread that created the arena; `WrongThreadException` is caught. With `Arena.ofShared()`, the worker can read/write the segment; in the example, `join()` makes the main thread wait for the worker to finish **before the arena closes**.

`WrongThreadException` is a confinement error, not an alignment or out-of-bounds error. In practice, `Arena.ofShared` does not make all memory operations thread-safe; multiple workers writing to the same region need their own data synchronization rules.

## 9. C Struct Alignment: The Role of MemoryLayout

When working with C structs, the alignment of each field and the padding between fields are very important. Suppose the desired layout has:

- A 4-byte `int` at offset 0.
- 4 bytes of padding.
- An 8-byte `long` at offset 8.

We can describe **this specific memory layout** using `MemoryLayout` (this is an example layout with a fixed layout; it does not claim that C `long` is always 8 bytes on every ABI):

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public class StructFacts {
    public static void main(String[] args) {
        MemoryLayout layout = MemoryLayout.structLayout(
                ValueLayout.JAVA_INT.withName("code"),
                MemoryLayout.paddingLayout(4),
                ValueLayout.JAVA_LONG.withName("payload"));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment s = arena.allocate(layout);

            long codeOffset = layout.byteOffset(groupElement("code"));
            long payloadOffset = layout.byteOffset(groupElement("payload"));

            s.set(ValueLayout.JAVA_INT, codeOffset, 7);
            s.set(ValueLayout.JAVA_LONG, payloadOffset, 99L);

            System.out.println("Struct bytes: " + layout.byteSize());
            System.out.println("Struct alignment: " + layout.byteAlignment());
            System.out.println("Payload offset: " + payloadOffset);
            System.out.println("Allocated alignment OK: "
                    + (s.address() % layout.byteAlignment() == 0));
            System.out.println("Payload: "
                    + s.get(ValueLayout.JAVA_LONG, payloadOffset));
        }
    }
}
```

**Run:**

```bash
javac StructFacts.java
java StructFacts
```

**Verified stdout on JDK 24:**

```text
Struct bytes: 16
Struct alignment: 8
Payload offset: 8
Allocated alignment OK: true
Payload: 99
```

Two important points:

- `MemoryLayout.byteAlignment()` is the **layout's constraint**, whereas `MemorySegment.maxByteAlignment()` is the **segment's alignment capability**; `arena.allocate(layout)` creates a memory region that satisfies the given layout.
- `MemoryLayout.structLayout` does not automatically infer all padding from any given C ABI; in the example, `MemoryLayout.paddingLayout(4)` is **explicitly** specified. When interoperating with an actual C struct, you must match the **ABI, field width, packing, endianness, padding, and alignment** of the library and operating system. A C `long` does not always have the same size as a Java `long` on every ABI.

## 10. Distinguishing Failure Conditions on Access

A `segment.get(layout, offset)` call can fail due to **multiple independent causes**. Categorize them before fixing:

| Condition | Example | Common error |
| --- | --- | --- |
| Out of view bounds | 32-byte segment, reading `JAVA_LONG` at offset 32 | `IndexOutOfBoundsException` |
| Wrong alignment | 8-aligned base, reading `JAVA_INT` at offset 1 | `IllegalArgumentException` |
| Scope no longer alive | Reading a segment from `Arena.ofConfined` after the arena closes | `IllegalStateException` |
| Wrong owner thread | Another thread reading a segment of `Arena.ofConfined` | `WrongThreadException` |
| Writing to a read-only view | `segment.asReadOnly().set(...)` | `IllegalArgumentException` |
| Invalid allocation request | `arena.allocate(32, 3)` | `IllegalArgumentException` |
| Trying to close an already-closed arena | Second `arena.close()` | `IllegalStateException` |
| Trying to close a non-closeable arena | `Arena.ofAuto().close()`, `Arena.global().close()` | `UnsupportedOperationException` |

If multiple conditions fail at the same time, **do not rely on assumptions about the checking order** to guess the first exception type; each test example should intentionally create exactly one prominent error condition.

A useful way to think about safe access:

```text
segment.get(layout, offset)
       |
       +-- Scope alive?          --- no --> IllegalStateException
       |
       +-- Thread allowed to access? --- no --> WrongThreadException
       |
       +-- Offset + size within bounds? -- no --> IndexOutOfBoundsException
       |
       +-- Address properly aligned? --- no --> IllegalArgumentException
       |
       +-- Read data and interpret according to layout
```

The diagram above is a **mental model**, not a claim about the internal checking order of every JVM implementation. `set` operations also need to check whether the segment is read-only.

## 11. Common Pitfalls When Using MemorySegment with Native Code

### 11.1. Using a Raw Address Instead of the Segment

Do not write `long p = s.address()` and assume `p` remains valid after the arena closes. FFM only protects accesses performed **through a still-valid view**. When passing `p` through JNI or a C API outside FFM, bounds and scope checks are not automatically applied to that native pointer.

If a C library needs to retain the pointer after the Java method returns, ensure the arena and backing memory remain alive **long enough**, with a clear ownership/close mechanism and without closing while a native worker is still using it. `Arena.ofConfined()` is also unsuitable if another native worker needs to access the segment via the Java API from a different thread.

### 11.2. Confusing Scope with Size

A live scope **does not** allow access beyond `byteSize`. Conversely, a sufficiently long segment **does not** allow access after close. These two properties are separate. A slice usually has a smaller size than its parent but **shares the same lifetime**.

### 11.3. Confusing Address Alignment with Alignment at Every Offset

Even when `segment.maxByteAlignment() >= 8`, accessing at offset 1 with `JAVA_LONG` is still wrong. The target address formula of a native segment is **base + offset**, and it is the target address that must satisfy the layout alignment. The segment's `maxByteAlignment` at the base is necessary information, but not sufficient for every access offset.

### 11.4. Confusing a Heap Address of 0 with a Null Pointer

`MemorySegment.ofArray(new byte[16]).address() == 0` is the definition of a **virtualized offset**, not a sign of an empty array or freed memory. Check `isNative()` to know the segment's backing type; to interact with a C pointer, you cannot take `address()` of a heap segment and treat it as a malloc address.

### 11.5. Using an Unaligned Layout as a Way to Fix ABI

`ValueLayout.JAVA_INT_UNALIGNED` allows unaligned reads, but if the actual C struct layout has different padding or different field widths, it cannot "fix" the data structure. Define `MemoryLayout` matching the ABI before coding offsets; use an unaligned layout when the data is genuinely a packed representation and you understand the portability risks.

### 11.6. Choosing Arena.global for Every Allocation

The global arena has an unlimited lifetime according to the API, easily causing native memory not to be freed while the application runs. Use `Arena.ofConfined()` or `Arena.ofShared()` with `try-with-resources` when the resource has an endpoint; `Arena.ofAuto()` is only suitable when accepting that GC decides the reclamation time.

### 11.7. Using ofAddress + reinterpret to Bypass Safety

`MemorySegment.ofAddress(address)` creates a zero-length segment, which **has no read permission** unless its bounds are increased with a restricted API. `reinterpret` is a powerful but unsafe operation; if it receives an address not belonging to a valid region or declares the wrong size/scope, it can read/write outside the process's memory, causing data corruption or a JVM crash. Do not expand bounds just because you encountered `IndexOutOfBoundsException`.

### 11.8. Closing the Arena While a Native Callback Is Still Using the Data

A downcall/native function may hold a pointer while Java code tries to close the arena. Although FFM provides temporal safety checks for managed accesses, C code outside the protection system does not automatically have bounds/lifetime checks. **Do not transfer unclear ownership** to C and then close the arena early. Synchronize tasks and confirm the native call has completed before closing.

## 12. Process for Designing and Reviewing an API Using Segments

A reliable public API or JNI/FFM wrapper should answer these questions:

1. **Where does the memory live?** Native or Java heap? Is off-heap truly needed? Is there file mapping?
2. **Who allocates it?** `Arena.allocate`, a Java array, `MemorySegment.ofBuffer`, a mapped file, or another C library?
3. **What does the address mean?** A real native address in the process or a heap offset? Is it allowed to be passed to a native function?
4. **How many bytes long is the view?** Is it a slice? Reading/writing by byte offset or logical index?
5. **Which layout applies?** How wide is each value, what endianness, how many bytes of alignment, is there padding?
6. **Which arena manages the lifetime?** Confined, shared, auto, or global? Who closes it and when?
7. **Which thread accesses it?** Is it the right owner? If shared, is data synchronized between readers/writers?
8. **Is the raw address kept elsewhere?** If so, how is use after the arena closes prevented?
9. **Are error paths tested as well?** Bounds, misalignment, wrong thread, after close, read-only, constructor/allocator failures?
10. **Is native memory measured?** Heap metrics do not necessarily reflect all off-heap pressure; use appropriate profiling/observability tools.

### Quick Selection Table

| Scenario | Usually appropriate choice |
| --- | --- |
| Short-lived native buffer read/write in one thread | `Arena.ofConfined()` + `try-with-resources` |
| Multiple Java threads need to access a native region | `Arena.ofShared()` + data and lifecycle synchronization |
| Can accept GC managing reclamation timing | `Arena.ofAuto()` (no deadline) |
| Intentionally need an unlimited-lifetime region | `Arena.global()`, with resource lifetime warning |
| Only need a view of a Java primitive array | `MemorySegment.ofArray(...)` |
| Need a layout for a primitive value | `ValueLayout.JAVA_*` and `get/set` operations |
| Need to represent a struct and field offsets | `MemoryLayout.structLayout(...)`, compute offsets with layout paths |
| Need a subrange restricting access capability | `segment.asSlice(offset, size)` |
| Unaligned packed data | Intentional `*_UNALIGNED` layout, mind ABI and performance |

## 13. Self-Check Exercises

**Exercise 1.** A native segment has `address() = 1000` (hypothetical), `byteSize() = 16`, and an alive scope. Can you read `JAVA_LONG` at offset 8 and offset 12?

**Answer:** Offset 8 has address 1008, which is divisible by 8, and the data occupies bytes 8…15, so it is valid. Offset 12 only has bytes 12…15 (4 bytes) remaining, which is not enough for 8 bytes; moreover, address 1012 is not 8-aligned either. There are at least bounds and alignment errors; do not assume the exception order if both conditions are violated simultaneously.

**Exercise 2.** Does `arena.allocate(32, 8)` guarantee `maxByteAlignment() == 8`?

**Answer:** No. It guarantees the base is **at least 8-aligned**; the actual address may satisfy a larger alignment, making `maxByteAlignment` >8. Check `>= 8`.

**Exercise 3.** Why is `MemorySegment.ofArray(new byte[16]).address() == 0` not a native null pointer?

**Answer:** This is a heap segment; `address()` represents a **virtualized offset** within the backing array, not a RAM address that can be dereferenced by C. `isNative()` is false.

**Exercise 4.** Does `MemorySegment part = s.asSlice(1, 8)` allocate 8 additional bytes of its own and exist independently after `arena.close()`?

**Answer:** No. It shares the same backing storage and scope as `s`, only changing the base and view size. Offset 1 can also reduce the maximum alignment down to 1.

**Exercise 5.** After `arena.close()`, `segment.byteSize()` may still reflect the initial length. Does that mean the native memory region is still alive?

**Answer:** No. `byteSize` is view metadata; accessibility depends on `scope().isAlive()` and other checks. Reads/writes after close are rejected.

**Exercise 6.** A confined arena is created on the main thread and the segment is passed to a worker thread. The scope is still alive, so can the worker read `JAVA_BYTE`?

**Answer:** No. Confinement requires the owner thread. The API may throw `WrongThreadException`. Switch to `Arena.ofShared()` if cross-thread access is genuinely needed, and properly protect data/lifecycle.

**Exercise 7.** Why can `JAVA_INT_UNALIGNED` be read on a segment backed by `byte[]` while the default `JAVA_INT` is blocked?

**Answer:** `byte[]` supports maximum alignment 1, the default `JAVA_INT` requires 4, whereas `JAVA_INT_UNALIGNED` requires 1. Both occupy 4 bytes, but have different alignment constraints.

**Exercise 8.** Does `MemoryLayout.structLayout` automatically insert all padding like the OS C compiler?

**Answer:** You cannot assume that. You must describe padding/width/alignment according to the actual C ABI. For example, `paddingLayout(4)` is explicitly written to create offset 8 for `payload`.

**Exercise 9.** A segment has an alive scope, valid offset, and is aligned; is it safe for a native function to keep the raw pointer after Java closes the arena?

**Answer:** No. The constraints protecting access through a segment do not automatically transfer to a raw C pointer. You need ownership rules and must ensure the native consumer finishes before the backing memory is freed.

**Exercise 10.** Does using `Arena.ofAuto()` guarantee native resources are freed when the Java method finishes?

**Answer:** No. An auto arena is managed by GC, with no deadline; you need a confined/shared arena and `try-with-resources` if you want to close according to a specific scope.

## 14. Summary

- **`address()`** is the segment's address/offset, not by itself an indicator of ownership or validity; a native address differs from a heap virtualized address.
- **`byteSize()`** limits the number of bytes allowed to be read/written; a slice narrows the view and does not create new backing memory.
- **`scope()`** sets temporal boundaries; closing an arena makes segments in the same scope inaccessible, even if the Java object still exists.
- **`Arena.ofConfined`, `ofShared`, `ofAuto`, `global`** differ in close permissions and thread usage permissions.
- **`maxByteAlignment()`** describes the alignment the segment supports; **`MemoryLayout.byteAlignment()`** describes the alignment an access requires. The offset must also be compatible.
- **`ValueLayout.JAVA_INT_UNALIGNED`** allows reading packed bytes at alignment 1 but does not replace proper ABI design.
- Safe access simultaneously requires **in-bounds + alive scope + right thread + right alignment + appropriate write permission**.
- **Do not try to bypass limits** with raw pointers, `ofAddress`, or restricted `reinterpret` without verifying the size and lifecycle of the native memory.

## Official References

- [Java SE 22 API — java.lang.foreign.MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 24 API — MemorySegment (address, byteSize, maxByteAlignment, scope, slicing)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 24 API — Arena (confined/shared/auto/global)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 24 API — ValueLayout and unaligned value layouts](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Java SE 24 API — MemoryLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [JEP 454 — Foreign Function & Memory API (finalized in JDK 22)](https://openjdk.org/jeps/454)

**Key takeaway:** a `MemorySegment` is a **view with spatial bounds, temporal bounds, and alignment requirements**. Preserve all four characteristics when slicing, passing data to native code, and managing resource lifecycles.
