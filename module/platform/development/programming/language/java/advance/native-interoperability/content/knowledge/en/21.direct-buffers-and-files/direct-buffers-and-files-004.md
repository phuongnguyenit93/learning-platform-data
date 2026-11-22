# Converting Between ByteBuffer and MemorySegment Without Assuming a Copy

> **Context:** Java Advance → Native Interoperability → Buffers and Files. This article explains the bidirectional conversion `ByteBuffer ↔ MemorySegment` in the Foreign Function & Memory API (FFM) using `MemorySegment.ofBuffer(...)` and `segment.asByteBuffer()`. Core focus: **these are *views* sharing the same backing memory, not data-copying operations**; you must manage byte range, byte order, write permissions, heap/direct backing, lifetime, and threads. Examples use **JDK 22+**, the finalized FFM version per JEP 454.

## 1. One Memory Region, Multiple Views: Conversion Does Not Mean Copy

Java NIO's `ByteBuffer` provides byte read/write operations with `position`, `limit`, `capacity`, and `ByteOrder` properties. FFM's `MemorySegment` provides a view with `long byteSize()`, accesses based on `ValueLayout`, scope/lifetime, and thread constraints.

It is possible to have **two different Java objects** looking at **the same region of bytes**:

```text
                     backing memory
             byte 0   byte 1   byte 2   byte 3 ...
                |        |        |        |
                +--------+--------+--------+-----
                      ^         ^
                      |         |
   ByteBuffer ------------------------> put/get(relative/absolute)
                      |
   MemorySegment ---------------------> get/set(ValueLayout,byteOffset)

   Both views reference the same data; NO copy is automatically created.
```

If you write through view A and then read through view B **on the same bytes, within a valid lifetime, and with proper synchronization**, B will see the content just written. You do not need to wait for a `flush` or `sync` operation to "push data from buffer to segment" in normal heap/direct cases.

However, there are three **distinct** kinds of actions to separate:

1. **Creating a view:** `MemorySegment.ofBuffer(buffer)`, `segment.asByteBuffer()`, `buffer.duplicate()`, `buffer.slice()`, and `segment.asSlice(...)` generally **do not copy payload bytes**; they create new metadata/views over the backing storage.
2. **Creating a new allocation:** `ByteBuffer.allocate(1024)`, `ByteBuffer.allocateDirect(1024)`, `arena.allocate(1024)` create storage regions. Creating new memory **does not mean** data has been copied from the old region.
3. **Explicit copying:** `destinationSegment.copyFrom(sourceSegment)`, `MemorySegment.copy(...)`, `ByteBuffer.put(otherBuffer)`, or `System.arraycopy(...)` transfer **byte contents** to another destination. Only that creates an independent snapshot if the destination does not alias the source.

**Do not guess by class name** that `ByteBuffer` always uses the heap or `MemorySegment` always uses native memory. Both can be heap-backed or native/direct-backed depending on how they were created.

## 2. The Two Main Conversion APIs and Their Contracts

| Direction | API | Copies data? | Visible region | Who manages backing memory? |
|---|---|---|---|---|
| `ByteBuffer/Buffer → MemorySegment` | `MemorySegment.ofBuffer(buffer)` | **No** | From `buffer.position()` (inclusive) to `buffer.limit()` (exclusive) at call time | Original owner of the buffer; scope matching the source |
| `MemorySegment → ByteBuffer` | `segment.asByteBuffer()` | **No** | Exact `segment.byteSize()`, if representable as a ByteBuffer | Original owner of the segment/Arena |
| `MemorySegment → MemorySegment` | `segment.asSlice(offset,size)` | **No** | A sub-window of bytes | Same scope/owner as the segment |
| `ByteBuffer → ByteBuffer` | `buffer.slice()` / `duplicate()` | **No** | Slice: remaining; duplicate: full view with independent state | Same backing storage |
| `MemorySegment → independent buffer` | New allocation + `copyFrom` | **Yes, when copy is called** | According to the size you choose | Owner of the new allocation |

Not every combination can be converted in both directions. In particular, `asByteBuffer()` cannot return a ByteBuffer if the segment is larger than `Integer.MAX_VALUE` bytes or if a heap segment does not have a suitable backing type (for example, an `int[]`). That is a representation/backing-type limitation, not evidence that the runtime will automatically copy to "force a conversion".

### Key Method Names

```java
import java.lang.foreign.MemorySegment;
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.allocate(16);

MemorySegment segment = MemorySegment.ofBuffer(buffer);
ByteBuffer view = segment.asByteBuffer();
```

This is a code snippet that can be used inside `main`, without having a `main` itself. The two conversions do not create a copy of the 16 bytes; `buffer`, `segment`, and `view` all touch the original storage region.

## 3. `MemorySegment.ofBuffer` Captures the Exact `[position, limit)` Range

`ByteBuffer` has three indices (measured in bytes):

- `capacity`: total capacity of the backing region that the buffer describes.
- `limit`: the **exclusive** end position of the current valid region.
- `position`: the relative position used for `get/put` calls **without an explicit index**.

When calling `MemorySegment.ofBuffer(buffer)`, the new segment:

- Starts at the **byte corresponding to `position`** of the buffer at conversion time.
- Ends at the **byte immediately before `limit`**; `segment.byteSize() == buffer.remaining()` at creation time.
- Treats **offset 0 of the segment** as the byte at the **old `position` index** of the buffer.
- Does not automatically increment/decrement `buffer.position()`, `buffer.limit()`, or copy content.
- Retains the selected byte window; modifying `position/limit` of the buffer **afterward** does not shift the already created segment.

Illustration:

```text
ByteBuffer capacity=8, position=2, limit=6
index:         0     1  |  2     3     4     5  |  6     7
bytes:       [  ]  [  ] | [A]   [B]   [C]   [D] | [  ]   [  ]
                         ^                    ^
                  segment offset 0      segment offset 3

MemorySegment.ofBuffer(buffer) --> byteSize()=6-2=4

segment.get(JAVA_BYTE, 0) <=> buffer.get(2)
segment.get(JAVA_BYTE, 1) <=> buffer.get(3)
segment.get(JAVA_BYTE, 3) <=> buffer.get(5)
segment.get(JAVA_BYTE, 4) --> outside segment
```

**Byte offset units are directly accurate only for ByteBuffer.** `MemorySegment.ofBuffer(Buffer)` can also accept `IntBuffer`/`ShortBuffer` etc.; in that case, the buffer's `position/limit` are in units of **typed buffer elements**, while `segment.byteSize()` is still measured in **bytes**. Details in section 11.

### `Buffer.clear()` Does Not Zero Bytes and Does Not Change the Old View

`buffer.clear()` resets the buffer's position/limit/mark, **without zeroing the contents**. A segment already created from `[2,6)` still sees the region corresponding to bytes 2–5; it **does not** expand with the new limit. If you want a different window, call `ofBuffer` again after reconfiguring the buffer, or create an appropriate `asSlice`.

## 4. Complete Program 1 — Heap ByteBuffer and Bidirectional Aliasing

**File `SharedHeapViewsDemo.java`, JDK 22+:**

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;

public final class SharedHeapViewsDemo {
    public static void main(String[] args) {
        ByteBuffer source = ByteBuffer.allocate(8);
        source.position(2);
        source.limit(6);

        MemorySegment segment = MemorySegment.ofBuffer(source);
        // 4-byte segment, segment[0] coincides with source[2].

        segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 77);
        source.put(3, (byte) 41); // Absolute put, does not change position.

        ByteBuffer newView = segment.asByteBuffer();
        newView.put(2, (byte) 9); // source[4] also changes.

        System.out.println("segmentBytes=" + segment.byteSize());
        System.out.println("segmentNative=" + segment.isNative());
        System.out.println("source[2]=" + source.get(2));
        System.out.println("segment[1]=" +
                segment.get(ValueLayout.JAVA_BYTE, 1));
        System.out.println("source[4]=" + source.get(4));
        System.out.println("sourcePosition=" + source.position()
                + " limit=" + source.limit());
        System.out.println("viewPosition=" + newView.position()
                + " limit=" + newView.limit()
                + " capacity=" + newView.capacity()
                + " direct=" + newView.isDirect());

        source.clear();
        System.out.println("afterClearBytes=" + segment.byteSize());
    }
}
```

Run:

```bash
javac -encoding UTF-8 SharedHeapViewsDemo.java
java SharedHeapViewsDemo
```

**Expected output (key operations verified on JDK 24):**

```text
segmentBytes=4
segmentNative=false
source[2]=77
segment[1]=41
source[4]=9
sourcePosition=2 limit=6
viewPosition=0 limit=4 capacity=4 direct=false
afterClearBytes=4
```

Explanation:

- `source` was created with `ByteBuffer.allocate`, so its backing is a Java heap `byte[]`.
- `MemorySegment.ofBuffer(source)` creates a heap segment `isNative()==false`, containing **four bytes** from `source[2]` to `source[5]`.
- `segment.set(JAVA_BYTE,0,77)` is immediately visible through `source.get(2)`.
- `source.put(3,41)` is immediately visible through `segment.get(JAVA_BYTE,1)`.
- `newView.put(2,9)` writes to byte offset 2 of the window, equivalent to source index 4.
- `source`'s position/limit remain 2/6, while `newView` has position 0, limit/capacity 4.
- `source.clear()` changes **buffer metadata**, not causing `segment.byteSize()` to change from 4 to 8.

This example proves two things simultaneously: **no payload copy** and **position/limit state is not shared state**. Two views sharing backing memory still have their own separate read/write cursor positions.

## 5. `asByteBuffer()`: New View, Position 0, Default BIG_ENDIAN Order

According to `MemorySegment.asByteBuffer()`, if the conversion succeeds, the resulting ByteBuffer:

- `position() == 0`.
- `limit() == capacity() == (int)segment.byteSize()`.
- `isReadOnly()` equals the segment's read-only state.
- `isDirect() == true` if the segment is a native segment; an appropriate heap segment gives a heap view.
- **`order() == ByteOrder.BIG_ENDIAN`** initially, even if the layout or original ByteBuffer used a different order.
- The lifetime and thread access permissions of the ByteBuffer view are bound by the **scope of the original segment**.

`asByteBuffer` does not cause the segment to "convert to heap" or "create a direct copy". When the parent is native memory, the ByteBuffer view is direct; when the parent is a heap byte array, the view is heap. There is no implicit copying of data between them.

**Important about byte order:** `MemorySegment` does not carry a "default order" field that transfers to ByteBuffer. When accessing multiple bytes with `ValueLayout.JAVA_INT`, the layout determines the byte order. `ByteBuffer.getInt/putInt` depends on `buffer.order()`. You must configure both sides to the same wire format:

```java
// Illustrative snippet, assuming segment contains at least 4 bytes.
ByteBuffer view = segment.asByteBuffer();
view.order(java.nio.ByteOrder.LITTLE_ENDIAN);

var intLE = java.lang.foreign.ValueLayout.JAVA_INT
        .withOrder(java.nio.ByteOrder.LITTLE_ENDIAN);

// Also use withByteAlignment(1) when backed by heap byte[]
// and the data layout allows unaligned access.
```

Do not call `view.getInt(0)` with the default BIG_ENDIAN and compare it with `segment.get(JAVA_INT.withOrder(LITTLE_ENDIAN),0)` and conclude "bad copy". They may be interpreting **the same four bytes in two different orders**.

## 6. Complete Program 2 — Native Arena → ByteBuffer → MemorySegment

In the reverse direction, Arena allocates off-heap memory, `asByteBuffer()` gives a Java NIO view, and `ofBuffer(...)` recreates a segment over the **same allocation**.

**File `NativeRoundTripDemo.java`, JDK 22+:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class NativeRoundTripDemo {
    public static void main(String[] args) {
        ByteBuffer escapedView;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment nativeMemory = arena.allocate(8, 8);
            ByteBuffer view = nativeMemory.asByteBuffer();
            escapedView = view;

            // ByteBuffer view initially uses BIG_ENDIAN.
            view.putInt(0, 0x01020304);

            // ofBuffer(view) does not allocate/copy new data.
            MemorySegment roundTrip = MemorySegment.ofBuffer(view);

            System.out.println("direct=" + view.isDirect());
            System.out.println("native=" + roundTrip.isNative());
            System.out.println("sameScope=" +
                    (roundTrip.scope() == nativeMemory.scope()));

            System.out.printf("intBE=0x%08X%n",
                    nativeMemory.get(
                            ValueLayout.JAVA_INT.withOrder(
                                    ByteOrder.BIG_ENDIAN), 0));

            roundTrip.set(ValueLayout.JAVA_BYTE, 4, (byte) 88);
            System.out.println("view[4]=" + view.get(4));
        }

        // Must not use a ByteBuffer pointing to a closed Arena.
        try {
            escapedView.get(0);
        } catch (IllegalStateException expected) {
            System.out.println(
                    "afterClose=IllegalStateException");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 NativeRoundTripDemo.java
java NativeRoundTripDemo
```

**stdout:**

```text
direct=true
native=true
sameScope=true
intBE=0x01020304
view[4]=88
afterClose=IllegalStateException
```

Points to note:

1. `Arena.ofConfined()` creates off-heap memory; `nativeMemory.asByteBuffer()` returns a **direct ByteBuffer**, without copying to the Java heap.
2. `MemorySegment.ofBuffer(view)` on a ByteBuffer created from a segment with scope `S` **inherits the same scope `S`**, rather than creating a new independent lifetime.
3. `roundTrip.set(JAVA_BYTE,4,88)` appears immediately at `view.get(4)`. This is proof of shared backing.
4. When `arena.close()` runs, the allocation is no longer valid; the ByteBuffer may still have a Java reference, but Java byte-access through it throws `IllegalStateException`. **Holding the ByteBuffer object does not keep the Arena allocation alive after close**.
5. If accessed from another thread when the Arena is confined, the ByteBuffer view is also subject to thread confinement (typically `WrongThreadException`); `isDirect()==true` does not mean "anyone can access it".

**Do not manually call a cleaner/direct-buffer free** on `view`. Arena is the owner of the allocation; freeing outside the Arena and then letting the Arena close can cause double-free/use-after-free. If you need native memory that lives across multiple threads, design with `Arena.ofShared()` and an appropriate shutdown barrier.

## 7. ByteOrder and Alignment: The Same Bytes Can Still Be Read as Different Numbers

A subtle bug: two views can point to the same bytes yet **interpret** `int`/`short` values differently. Besides endianness, there is alignment: a heap buffer backed by `byte[]` does not guarantee the natural alignment of 4 for `ValueLayout.JAVA_INT`.

### 7.1. Default Order of a New ByteBuffer

Suppose four bytes are:

```text
byte[0..3] = 44 33 22 11

LITTLE_ENDIAN  int = 0x11223344
BIG_ENDIAN     int = 0x44332211
```

`ByteBuffer.allocate(8).order(LITTLE_ENDIAN)` may write `0x11223344` as `44 33 22 11`. But `MemorySegment.ofBuffer(...).asByteBuffer()` gives a new ByteBuffer that defaults to **BIG_ENDIAN**. `newView.getInt(0)` will read `0x44332211` until `newView.order(LITTLE_ENDIAN)` is called.

### 7.2. The maxByteAlignment Issue of Heap `byte[]`

`MemorySegment.ofBuffer(ByteBuffer.allocate(...))` returns a **heap segment** backed by `byte[]`. Because the guaranteed alignment for a `byte` element is only 1 byte, `segment.maxByteAlignment()` can be **1**. On JDK 24 tested, calling:

```java
// Illustrative snippet from a heap ByteBuffer.
segment.get(ValueLayout.JAVA_INT, 0);
```

can throw `IllegalArgumentException` **right at offset 0**, even though there are ≥4 bytes remaining. This is an alignment issue of the **backing heap type**, not bounds and unrelated to copying.

If the format genuinely stores ints without requiring native alignment, use an **unaligned** layout:

```java
var intLE = ValueLayout.JAVA_INT
        .withOrder(ByteOrder.LITTLE_ENDIAN)
        .withByteAlignment(1);
int value = segment.get(intLE, 0);
```

The snippet assumes imports and the `segment` variable are present. `withByteAlignment(1)` expresses unaligned access by contract, **does not change bytes**, does not copy, and does not enlarge the memory region. For native structs that genuinely require 4-byte alignment, you must allocate/lay them out according to the ABI; **do not** lower alignment just to dodge an exception.

## 8. Complete Program 3 — Distinguishing Shared View and Snapshot Copy

This program demonstrates both **explicit copying** (`copyFrom`) and **explicit byte order**, along with the heap-byte alignment warning.

**File `CopyAndOrderDemo.java`, JDK 22+:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class CopyAndOrderDemo {
    public static void main(String[] args) {
        ByteBuffer source =
                ByteBuffer.wrap(new byte[]{10, 20, 30, 40, 50});
        source.position(1);
        source.limit(4);

        // View of 3 bytes: 20,30,40. No copy.
        MemorySegment live = MemorySegment.ofBuffer(source);

        try (Arena arena = Arena.ofConfined()) {
            // NEWLY allocates storage and explicitly copies bytes.
            MemorySegment snapshot = arena.allocate(live.byteSize());
            snapshot.copyFrom(live);

            live.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);
            System.out.println("source=" + source.get(1)
                    + " copied=" +
                    snapshot.get(ValueLayout.JAVA_BYTE, 0)
                    + " length=" + snapshot.byteSize());
        }

        ByteBuffer little = ByteBuffer.allocate(8)
                .order(ByteOrder.LITTLE_ENDIAN);
        little.putInt(0, 0x11223344);
        little.position(0);
        little.limit(4);

        MemorySegment asSegment = MemorySegment.ofBuffer(little);

        var intLE = ValueLayout.JAVA_INT
                .withOrder(ByteOrder.LITTLE_ENDIAN)
                .withByteAlignment(1);

        System.out.println("heapMaxAlignment=" +
                asSegment.maxByteAlignment());
        System.out.printf("segmentLE=0x%08X%n",
                asSegment.get(intLE, 0));

        ByteBuffer anotherView = asSegment.asByteBuffer();
        System.out.printf("viewDefault=0x%08X%n",
                anotherView.getInt(0));

        anotherView.order(ByteOrder.LITTLE_ENDIAN);
        System.out.printf("viewLE=0x%08X%n",
                anotherView.getInt(0));
    }
}
```

Run:

```bash
javac -encoding UTF-8 CopyAndOrderDemo.java
java CopyAndOrderDemo
```

**stdout (equivalent behavior verified on JDK 24):**

```text
source=99 copied=20 length=3
heapMaxAlignment=1
segmentLE=0x11223344
viewDefault=0x44332211
viewLE=0x11223344
```

Why did `snapshot` keep the value 20 while `source` became 99? `copyFrom` **copied the contents** into a new native allocation. `source` and `live` share bytes from the heap array; `snapshot` is an independent copy. That is the difference between `copyFrom` and view-conversion APIs.

Why do `segmentLE` and `viewDefault` differ? They read **the same 4 bytes**, but the `intLE` layout specifies LITTLE_ENDIAN, whereas a new ByteBuffer defaults to BIG_ENDIAN. After `anotherView.order(LITTLE_ENDIAN)`, they match.

**Guarantees and limits:** `heapMaxAlignment=1` is a result consistent with heap `byte[]` alignment guarantees; do not generalize it to "every MemorySegment has alignment 1". With a native allocation `arena.allocate(8,8)`, a `JAVA_INT` layout with alignment 4 is normally valid at offset 0. Multi-byte reads/writes must consider **both the type and alignment of the backing region**.

## 9. Heap, Direct, Mapped, and Typed Buffers Are Not the Same

| Creation source | Backing storage | `MemorySegment.ofBuffer` | `segment.asByteBuffer` |
|---|---|---|---|
| `ByteBuffer.allocate(n)` | Heap `byte[]` | Heap segment, **no copy** | Heap ByteBuffer view if size is valid |
| `ByteBuffer.wrap(byte[])` | Provided heap `byte[]` | Heap segment, **no copy** | Heap ByteBuffer view if size is valid |
| `ByteBuffer.allocateDirect(n)` | Native/direct memory | Native segment, **no copy** | Direct ByteBuffer view |
| `arena.allocate(n)` | Native memory owned by Arena | Can call `segment.asByteBuffer()` directly | Direct ByteBuffer sharing Arena scope |
| `MappedByteBuffer` from `FileChannel.map` | File-mapped native memory | Native segment with shared backing | Can create ByteBuffer view if size fits; does not copy mapping |
| `MemorySegment.ofArray(byte[])` | Heap `byte[]` | No need for `ofBuffer` to get a segment | ByteBuffer view can be created |
| `MemorySegment.ofArray(int[])` | Heap `int[]` | Segment exists | **`asByteBuffer` is not supported** for non-`byte[]` heap backing |
| `IntBuffer.wrap(int[])` | Heap `int[]` | `ofBuffer` can create a segment with size in bytes | Do not assume `asByteBuffer` is possible |
| `CharBuffer.wrap(CharSequence)` not backed by array | A kind of CharSequence view | `ofBuffer` may throw `IllegalArgumentException` | No guarantee of conversion |

**Important:** `Buffer.hasArray()==false` does not prove "no shared memory". A direct ByteBuffer typically does not expose a Java array yet still shares native backing with a MemorySegment. A read-only heap buffer may also disallow public array access while still having backing bytes.

Do not infer a native pointer from a heap segment. `segment.isNative()==false` means the backing is on the Java heap; the Java GC may move it and it must not be treated as an arbitrary stable `void*`. In native interoperability, use APIs that require the proper kind/pointer contract; when genuine native memory is needed, create a direct buffer or Arena segment, and **copy data intentionally** if the original source is on the heap.

## 10. Typed Buffers and the `asByteBuffer` Limitation: A Memorable Counterexample

`MemorySegment.ofBuffer` accepts a `java.nio.Buffer`, not just `ByteBuffer`. For example, `IntBuffer` has `position`/`limit` **measured in number of ints**, not bytes.

**File `TypedBufferEdgeDemo.java`, JDK 22+:**

```java
import java.lang.foreign.MemorySegment;
import java.nio.IntBuffer;

public final class TypedBufferEdgeDemo {
    public static void main(String[] args) {
        IntBuffer ints = IntBuffer.wrap(new int[]{10, 20, 30});
        ints.position(1);
        ints.limit(3);

        MemorySegment segment = MemorySegment.ofBuffer(ints);
        System.out.println("segmentBytes=" + segment.byteSize());
        System.out.println("native=" + segment.isNative());

        try {
            segment.asByteBuffer();
        } catch (UnsupportedOperationException expected) {
            System.out.println(
                    "asByteBuffer=UnsupportedOperationException");
        }
    }
}
```

Run:

```bash
javac TypedBufferEdgeDemo.java
java TypedBufferEdgeDemo
```

**stdout:**

```text
segmentBytes=8
native=false
asByteBuffer=UnsupportedOperationException
```

The remaining two `int`s (`20,30`) occupy `2 × 4 = 8` bytes. FFM can create a heap segment over the storage of `int[]`, but `asByteBuffer` does not support converting a heap segment backed by a non-byte array into a `ByteBuffer`. It **does not automatically copy or reinterpret it differently** to bypass that limitation.

If you truly need independent bytes, **choose an encoding/endianness**, allocate a `byte[]` or Arena segment, and write each `int`/copy the data per the contract. Do not force an `int[]` into a `byte[]` by casting or assuming endianness/representation.

### Typed Buffers from Direct Memory

An `IntBuffer` can be a **view of a direct ByteBuffer**, not necessarily backed by `int[]`. When `ofBuffer` returns a native segment, `asByteBuffer` may represent it within size limits. Check `segment.isNative()` and the API contract instead of making an absolute rule that "every IntBuffer fails".

## 11. Position and Offset: Two Easily Confused Coordinate Systems

`ByteBuffer` has **relative operations** and **absolute operations**:

```java
// Illustrative snippet: buffer has enough bytes.
byte a = buffer.get();      // Reads at position then increments position.
byte b = buffer.get(3);     // Reads at absolute index 3; position stays unchanged.
buffer.put((byte) 7);       // Writes at position then increments position.
buffer.put(3, (byte) 7);    // Writes at absolute index 3; position stays unchanged.
```

`MemorySegment` accesses by **byte offset** from the start of the view:

```java
// Illustrative snippet: segment >= 4 bytes.
byte x = segment.get(ValueLayout.JAVA_BYTE, 0);
segment.set(ValueLayout.JAVA_BYTE, 3, (byte) 7);
```

There is no mutable `position` in MemorySegment. If a "cursor" is needed, the caller maintains an offset variable itself or uses a ByteBuffer view with relative `get/put`. When creating a segment from a ByteBuffer, byte offset 0 of the segment is the **buffer's position at conversion time**; when creating a ByteBuffer from a segment, the new ByteBuffer's position is always 0.

**Index example diagram:**

```text
ByteBuffer       capacity=10, position=4, limit=9
buffer index     0 1 2 3 | 4 5 6 7 8 | 9
segment offset           | 0 1 2 3 4 |
segment.byteSize=5

ByteBuffer original.get(4)  = segment.get(JAVA_BYTE,0)
ByteBuffer original.get(8)  = segment.get(JAVA_BYTE,4)
ByteBuffer original.get(9)  is not in the segment.
```

If the original buffer is a `slice` or a `duplicate` with its own `arrayOffset`, do not manually index into the underlying array while ignoring the slice offset. Use the view APIs because they already store the correct mapping to the backing region.

### Buffer Slice Differs from Segment Slice, Yet Neither Copies

`ByteBuffer.slice()` returns a new buffer with position 0, limit/capacity equal to the remaining of the original buffer, and the same backing storage. `MemorySegment.asSlice(start,length)` returns a new segment with byteSize=length, the parent's scope, and the same backing storage. Both are views, not snapshots.

Be careful with `ByteBuffer.duplicate()`: it keeps the same backing content, but position/limit/mark are **independent**; changing a byte will appear through both, while moving one buffer's position does not automatically move the other's.

## 12. Read-Only: Write Restriction on the View, Not an Immutable Snapshot

Reading the same backing memory while having different write permissions is normal:

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;

ByteBuffer writable = ByteBuffer.wrap(new byte[]{1, 2, 3});
ByteBuffer readOnlyBuffer = writable.asReadOnlyBuffer();

MemorySegment readOnlySegment =
        MemorySegment.ofBuffer(readOnlyBuffer);

System.out.println(readOnlySegment.isReadOnly()); // true

ByteBuffer anotherView = readOnlySegment.asByteBuffer();
System.out.println(anotherView.isReadOnly());      // true

// readOnlySegment.set(JAVA_BYTE, 0, (byte)9):
// IllegalArgumentException because the segment is read-only.
// anotherView.put(0, (byte)9):
// java.nio.ReadOnlyBufferException.
```

This is a study snippet; add `main` if you want to run it. There are two points often overlooked:

- `ofBuffer` preserves the **read-only** property from the original buffer. `asByteBuffer` preserves the read-only property of the segment.
- **A read-only view is not an immutable snapshot.** If another writable alias to the same backing memory still exists (like `writable` in the snippet), that alias can still modify the bytes and the read-only view will observe the changes.

If you need a fixed record for caching, digital signing, or CRC verification across unsynchronized threads, a plain read-only view is **not enough**: you must copy to separate storage and prevent other owners from modifying it, or apply appropriate synchronization.

## 13. Scope and Ownership: Lifetime Follows the Origin of Memory

There are two common paths to distinguish.

### 13.1. Original `ByteBuffer` Does Not Originate from `MemorySegment.asByteBuffer()`

Example:

```java
ByteBuffer direct = ByteBuffer.allocateDirect(1024);
MemorySegment segment = MemorySegment.ofBuffer(direct);
```

`ofBuffer` creates a **native segment view** with an **automatic scope** that keeps `direct` reachable. This prevents the original ByteBuffer's backing memory from being reclaimed by GC **as long as the segment or its slices remain reachable**. However, that **does not** grant manual `arena.close()` authority, because this is not an allocation created by your Arena.

Do not call `free`, `Unsafe.invokeCleaner`, or an arbitrary SDK deallocator on the direct buffer's address. The memory still belongs to the original owner (typically the JVM/direct-buffer mechanism); freeing it yourself and continuing to use the segment or buffer can create a dangling view.

### 13.2. `ByteBuffer` Created from an Arena Segment

`arena.allocate(...).asByteBuffer()` creates a view within the Arena's scope; calling `MemorySegment.ofBuffer(view)` again **inherits the same scope**, without creating an independent owner to "extend" the lifetime.

```text
Arena.ofConfined() -> allocate() -> MemorySegment M
                       |
                       +-- M.asByteBuffer() -> ByteBuffer B
                                                |
                                                +-- ofBuffer(B) -> MemorySegment N
Arena.close() -> M, B, and N can no longer access the allocation.
```

Holding a reference to B/N **does not prevent the owner from calling `arena.close()`**. This is why the test in `NativeRoundTripDemo` throws `IllegalStateException` after the Arena closes.

### 13.3. Thread Confinement Also Propagates to the Buffer View

`Arena.ofConfined()` allows only the owner thread to access the memory. If you create `ByteBuffer view = segment.asByteBuffer()` and send the view to another thread, Java NIO access is also subject to the corresponding constraint and may throw `WrongThreadException`. With a shared arena, multiple threads can access it, but **data races remain the application's responsibility**.

Some asynchronous I/O APIs may run reads/writes on a thread incompatible with a confined scope. According to the JDK docs, for a ByteBuffer created from a **thread-confined segment**, the exception behavior of some asynchronous I/O channels may be unspecified. When passing a view to an executor/I/O subsystem, consider `Arena.ofShared()` with a clear owner lifecycle.

## 14. File Mapping: Converting Views Does Not Mean Copying the Entire File

For large files, Java NIO supports `MappedByteBuffer` and FFM supports `MemorySegment` directly over mapped files. Mapping allows accessing file data via virtual memory; the OS still performs page faults/caching and manages dirty pages, so the term "zero-copy view" **does not** mean "all I/O has no copying/kernel work/page faults".

Two approaches:

### 14.1. NIO Maps First, Then Creates a MemorySegment View

```java
// Illustrative snippet, channel already opened READ/WRITE; size > 0
// and <= Integer.MAX_VALUE for MappedByteBuffer.
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, size);

MemorySegment mappedView = MemorySegment.ofBuffer(mapped);
mappedView.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);

// mapped and mappedView share the same mapped region.
// Call mapped.force() when you need to request writing data back to storage.
mapped.force();
```

This is a snippet; it requires imports `java.nio.MappedByteBuffer`, `java.nio.channels.FileChannel`, `java.lang.foreign.*`. **There is no copying of the entire file** in `ofBuffer`. The mapping lifetime in the NIO branch is tied to the source `MappedByteBuffer`/GC, and must not be assumed to be closable via a self-created Arena afterward.

### 14.2. FFM Maps First, Then Creates a ByteBuffer View

Since JDK 22, `FileChannel.map(mode, offset, size, arena)` can return a `MemorySegment` of the file-mapped region:

```java
// Illustrative snippet inside a method that throws IOException;
// file exists, opened READ/WRITE, and size is suitable.
try (FileChannel channel = FileChannel.open(
            path, StandardOpenOption.READ,
            StandardOpenOption.WRITE);
     Arena arena = Arena.ofConfined()) {

    MemorySegment mapped = channel.map(
            FileChannel.MapMode.READ_WRITE,
            0L, channel.size(), arena);

    // Only use asByteBuffer if mapped.byteSize() <= Integer.MAX_VALUE.
    ByteBuffer view = mapped.asByteBuffer();
    view.put(0, (byte) 42);

    // Proactively request persisting dirty mapped bytes when appropriate.
    mapped.force();
} // Closing arena -> unmaps the mapped region per FFM contract.
```

This is a snippet, assuming `FileChannel`, `Path`/`StandardOpenOption`, `Arena`, `MemorySegment`, `ByteBuffer` are imported. `MappedSegment.force()` is not a mandatory step for Java to see changes through the two views on the same map; it serves **persistence** of the mapped file per the OS/file system contract.

**Caution:** a file can be truncated by another process, or map mode/permissions may be unsuitable; a mapped region can lose accessibility. Mapping does not automatically create a consistent snapshot of the file. When content can change concurrently, file locks/protocols/checksums are needed depending on the design.

### 14.3. File Regions Larger Than 2 GiB

`FileChannel.map(MapMode,long,long,Arena)` can return a segment whose size is represented as a `long`, supporting targets larger than the ByteBuffer limit in environments that allow it. However, `mapped.asByteBuffer()` **cannot** represent > `Integer.MAX_VALUE` bytes. Work with `mapped.asSlice(offset, length)` for each smaller window, or use FFM access directly. Ensure every window stays within bounds and within the Arena lifetime.

## 15. The 2 GiB Limit and Specific Conversion Errors

`ByteBuffer` uses `int` for `capacity()`, `limit()`, and `position()`; `MemorySegment` uses `long` for `byteSize()`. Therefore:

```java
// Do not run with a huge segment just to test.
// A hypothetical segment with byteSize() > Integer.MAX_VALUE:
segment.asByteBuffer(); // UnsupportedOperationException
```

The runtime will not implicitly copy 2+ GiB into multiple buffers or "truncate to 2 GiB" for you. To use NIO, split into slices whose sizes are within the limit, then process each window with offsets calculated as `long`.

Common error/condition table:

| Situation | Result/Risk | How to handle |
|---|---|---|
| `segment.byteSize() > Integer.MAX_VALUE` | `asByteBuffer` throws `UnsupportedOperationException` | Use FFM directly or slice into valid-sized windows |
| Heap segment backed by `int[]` | `asByteBuffer` is not supported | Explicitly convert data to `byte[]`/native allocation |
| `CharBuffer.wrap(CharSequence)` not backed by array | `ofBuffer` may throw `IllegalArgumentException` | Materialize to an array/ByteBuffer explicitly |
| Confined segment used from another thread | `WrongThreadException` | Same thread or use shared arena with proper lifetime |
| Arena already closed | `IllegalStateException` when accessing view | Do not let view escape owner lifetime |
| `segment.asReadOnly()` then calling `set` | `IllegalArgumentException` | Need writable view/owner per contract |
| Read-only ByteBuffer then calling `put` | `ReadOnlyBufferException` | Do not strip read-only; create owned mutable copy if needed |
| Buffer view reads `int` differently from Segment view | Different byte order/alignment | Choose `order` and `ValueLayout` matching the schema |
| Buffer is `clear/flip`ped after `ofBuffer` | Old segment still views the old byte window | Create a new segment view if a new region is wanted |
| Using `ByteBuffer.get()` as equivalent to `segment.get(JAVA_BYTE,0)` | Relative get changes position, while segment offset 0 is fixed | Use absolute index or manage cursor explicitly |
| Creating snapshot with `duplicate()/slice()/asByteBuffer` | Still aliases backing, no copy | Allocate new destination and `copyFrom` |
| Passing heap view directly as native pointer | No stable address like native memory | Follow Linker contract; use direct/Arena and copy when needed |
| Java GC manages direct buffer but app calls manual free | Possible dangling view/double-free | Let the proper owner manage it; do not cross-clean/free |

## 16. Concurrency and Memory Visibility: Zero-Copy Does Not Automatically Make It Thread-Safe

Two views over the same backing memory create **aliasing**. Within a single thread, writing and then reading through another view will see the new bytes. But if threads A and B access the same bytes concurrently **without synchronization**, the program may have a data race or lack the visibility guarantees the author expects.

Example of a flawed assumption:

```java
// PSEUDOCODE: Not a standalone runnable program.
// producer:
while (...) {
    segment.set(ValueLayout.JAVA_INT_UNALIGNED, 0, nextValue++);
}

// consumer on another thread:
while (...) {
    int n = buffer.getInt(0); // No happens-before.
}
```

You cannot rely on `segment` and `buffer` sharing the same backing to treat read/write operations as atomic, ordered, or properly visible in order. Additionally, the example may require matching byte order, alignment, and a scope accessible from both threads.

Solutions depending on the problem:

- Use a shared **lock** and lifecycle owner for both ByteBuffer/MemorySegment paths.
- Use `VarHandle` for fields with explicit access modes/ordering, while satisfying required alignment.
- Use a producer-consumer queue, `CompletableFuture`, or synchronization before/after buffer handoff.
- With native code or memory-mapped files shared between processes, understand memory ordering and protocols at both the native/OS boundary; Java monitors only synchronize Java threads per their contract and do not automatically apply to external devices.
- With `Arena.ofShared()`, threads are allowed to access the same region, but closing must happen after workers/callbacks have stopped; a shared arena **is not** locks or an atomic memory model.

**A position variable should not be used as a synchronizer.** ByteBuffer position/limit is mutable state belonging to each buffer and does not protect concurrency by itself. Two ByteBuffer views can have different positions over the same data; ownership/lifetime and visibility issues still remain.

## 17. Connecting with JNI/FFM Native Interoperability

Being able to convert ByteBuffer ↔ MemorySegment **does not** mean you already have a safe native allocation for C to hold a pointer to. Distinguish the source:

### Heap Buffer

`ByteBuffer.allocate(n)` is typically backed by a Java `byte[]`. `MemorySegment.ofBuffer(buffer)` returns a heap segment, `isNative()==false`. The garbage collector may move the underlying heap storage. Do not take `segment.address()` and pass it to native C as a stable physical address pointer; in a heap segment, address means an offset/abstract value, not a raw C pointer that can be arbitrarily dereferenced.

If a native API requires a pointer to a buffer per contract, consider:

- `ByteBuffer.allocateDirect(n)` to create direct/native backing that JNI `GetDirectBufferAddress` can access when the buffer is suitable.
- `Arena.allocate(n)` to allocate memory with an explicit lifetime; pass `MemorySegment` per the FFM downcall descriptor `ADDRESS` and only when allowed by the API/Linker, while still alive and within bounds.
- Explicit copying from heap to native allocation, and from native to heap when needed. This is an **intentional copy path**, which can be more correct and safer than zero-copy when native holds the buffer long-term or processes asynchronously.

### Direct Buffer or Arena-Owned Native Segment

When `MemorySegment.ofBuffer(ByteBuffer.allocateDirect(n))` returns a native segment, the conversion does not create a new data region; however, the **JVM/direct buffer** remains the owner of the backing memory. Do not call C `free` on that address, nor assign a new arena owner to free it.

When `Arena.allocate(n).asByteBuffer()` creates a direct view, **Arena** owns the backing. Do not use the view after `arena.close()`; if a native callback/worker holds the address, you must stop/drain/join before closing the Arena.

### JNI `NewDirectByteBuffer`

JNI can create a ByteBuffer view over a `void*` memory region allocated by an SDK (`NewDirectByteBuffer`). `MemorySegment.ofBuffer(...)` continues to create a view, **without transferring ownership**. The SDK must still free with its proper deallocator **after** all Java views and native consumers stop using that region. Merely holding the Java ByteBuffer object does not automatically extend the lifetime of the SDK allocation if the SDK has already freed the pointer externally.

**Identification rule:** conversion preserves **same backing bytes**, but does not automatically promise ownership, copying, pinning, retaining, native-pointer validity, or thread safety. All of these come from the **API that originally created the backing memory**.

## 18. Testing to Prove Presence/Absence of Copying

Instead of guessing via `==`/`equals`, you can test aliasing in a controlled way:

1. Create a buffer with easily observable data, set position/limit to create a window not starting at 0.
2. Convert to a segment using `ofBuffer`; check `byteSize==remaining` at creation time.
3. Write through segment offset 0, read through the original buffer at the old position index. A changed value proves shared backing.
4. Write through the original buffer at an absolute index, read through the corresponding segment offset.
5. Create `segment.asByteBuffer`, verify view position is 0 and limit/capacity equal segment size.
6. Change source `position/limit/clear`; verify the segment window does not automatically resize.
7. Allocate another destination memory, call `copyFrom`, then mutate source; verify destination is unchanged.
8. Check native vs heap via `segment.isNative()` and `buffer.isDirect()`.
9. Check byte order on both sides with an asymmetric hex number (`0x11223344`).
10. Check bounds, read-only, and lifetime after arena close.
11. For typed buffers, verify `IntBuffer.wrap(int[])` yields a segment with the right byte size, though `asByteBuffer` may not be supported.
12. For file mapping, test flush/persistence using the official mapping API; do not equate file persistence with a shared in-memory view.

**Do not use native addresses printed to logs as sole proof.** The same address could be a freed and reallocated region, or a heap address with a different meaning. Symmetric mutate/read within a safe scope is the most direct test for shared backing, though it is not a proof that the system is free of data races or lifetime bugs.

### Measuring Performance Responsibly

View conversion usually avoids copying large payloads, but that does not make it **always faster** in every workload. Access patterns, endian transforms, heap/direct cost, page faults, alignment, bounds checks, CPU cache, GC pressure, and whether native I/O requires its own copy all affect performance. If choosing zero-copy for performance, use JMH/microbenchmarks with warmup and test end-to-end throughput; do not use a single `System.nanoTime` for general conclusions.

## 19. Exercises with Answers

**Exercise 1 — remaining.** A ByteBuffer has capacity 12, position 3, limit 9. What is `MemorySegment.ofBuffer(buffer).byteSize()`, and which buffer index does segment offset 0 correspond to?

**Answer:** `9 - 3 = 6` bytes; segment offset 0 corresponds to buffer **index 3**. Indices 9–11 are not in the segment view even though they belong to the buffer's capacity.

**Exercise 2 — independent cursor.** Create `MemorySegment segment = ofBuffer(buffer)`; then call `buffer.clear()`. Does the segment automatically expand to the full capacity?

**Answer:** No. `clear()` only changes the buffer's position/limit/mark; the segment region is determined at the time of `ofBuffer`, and backing bytes remain shared.

**Exercise 3 — alias vs copy.** `MemorySegment s = ofBuffer(b); ByteBuffer c = s.asByteBuffer();`. Does writing `c.put(0,(byte)9)` create an independent version of the data?

**Answer:** No. `s` and `c` are both views sharing the same backing. If writable and alive, the corresponding byte in `b` changes. For a snapshot, you need a separate allocation and `copyFrom`/put.

**Exercise 4 — byte order.** Original ByteBuffer has order LITTLE_ENDIAN, containing bytes `44 33 22 11`. Call `ofBuffer` then `asByteBuffer` and `getInt(0)` immediately. What value?

**Answer:** The new view has default **BIG_ENDIAN** order, so it returns `0x44332211`. After `order(LITTLE_ENDIAN)`, it returns `0x11223344`. No data is copied; only the interpretation changes.

**Exercise 5 — alignment.** A heap ByteBuffer backed by byte[] contains 4 bytes of an int. `segment.get(ValueLayout.JAVA_INT,0)` throws `IllegalArgumentException` even though byteSize≥4. Why and how to fix?

**Answer:** A heap segment from byte[] has a maximum guaranteed alignment of 1; the natural int layout typically requires 4. Use `JAVA_INT.withByteAlignment(1)` with the appropriate byte order **if the schema allows unaligned ints**, or use a native allocation with proper alignment.

**Exercise 6 — Arena lifetime.** Create `ByteBuffer view = arena.allocate(16).asByteBuffer()`, return the view from a method, then close the Arena. The caller still holds the view; can it continue reading?

**Answer:** No. The ByteBuffer inherits the Arena scope; accessing after close throws `IllegalStateException`. Holding a ByteBuffer reference does not extend a closed scoped allocation.

**Exercise 7 — direct buffer.** `ByteBuffer b = ByteBuffer.allocateDirect(100)`; `MemorySegment s = ofBuffer(b)`. Do you need `arena.allocate(100)` and `copyFrom` just to get a native segment?

**Answer:** No, converting from a direct buffer already creates a native segment view over the same backing memory. **However**, if you want a different ownership/lifetime, you must design and allocate/copy explicitly; do not call `free` on the direct buffer.

**Exercise 8 — typed buffer.** `IntBuffer.wrap(new int[]{10,20,30})` has position 1/limit 3. How many bytes does `MemorySegment.ofBuffer(ints)` have, and is `asByteBuffer()` guaranteed to succeed?

**Answer:** 2 ints × 4 = **8 bytes**; not guaranteed. If heap-backed by `int[]`, `asByteBuffer()` throws `UnsupportedOperationException`. It does not automatically convert an int array to a byte array.

**Exercise 9 — 3 GiB file.** An FFM mapped segment has byteSize > Integer.MAX_VALUE. Can you call `asByteBuffer()` to get a single ByteBuffer covering the entire file?

**Answer:** No. `ByteBuffer` has a size limit from `int`. Use FFM direct access or small `asSlice`s that fit within the ByteBuffer limit, with proper bounds and scope.

**Exercise 10 — two threads.** Producer writes to MemorySegment, consumer reads via ByteBuffer sharing backing in a shared arena. Can all synchronization be omitted because there is no copy?

**Answer:** No. The two views alias the data but do not automatically establish happens-before, atomicity, or race protection. You must have appropriate synchronization/VarHandle/queue and ensure the Arena remains alive.

**Exercise 11 — read-only.** `MemorySegment.ofBuffer(readOnlyByteBuffer)` then `asByteBuffer()`. Is the resulting view writable? Is the data permanently immutable?

**Answer:** The resulting view is also **read-only**, but the backing memory can change if a valid writable alias exists. A read-only view is not equivalent to an immutable snapshot.

**Exercise 12 — ownership.** A native SDK creates a `void*`, then JNI creates a DirectByteBuffer view; Java converts it onward to a MemorySegment. Who calls free?

**Answer:** According to the **SDK's allocator contract**. JNI/NewDirectByteBuffer and `ofBuffer` only create views; they do not transfer free authority. You must wait for all Java/native users to finish before the SDK owner releases it.

## 20. Checklist and Official Documentation

Before using `ByteBuffer ↔ MemorySegment` in a native/file I/O system:

- [ ] Identified the **backing memory source**: Java heap byte[], direct/native, Arena, SDK, or file mapping.
- [ ] Understood that `ofBuffer` takes **position/limit at conversion time**, not the full capacity.
- [ ] Understood that `asByteBuffer` returns position 0, limit/capacity equal to segment size.
- [ ] Noted that **there is no payload copy** in conversion; if a snapshot is needed, allocate new memory and `copyFrom`.
- [ ] Checked the **byte order** of the new ByteBuffer (BIG_ENDIAN) against ValueLayout/format.
- [ ] Checked **byte alignment**; with heap byte[], consider unaligned layout when the contract allows.
- [ ] Verified segment size **≤ Integer.MAX_VALUE** and suitable backing before `asByteBuffer`.
- [ ] Checked read-only/write-permissions and whether a writable alias exists.
- [ ] Checked **scope/lifetime**: direct buffer automatic scope or closeable Arena?
- [ ] If from Arena, the Java ByteBuffer view must not outlive `arena.close()`.
- [ ] If processing across multiple threads, chose an appropriate scope and added synchronization.
- [ ] If native C holds the pointer, identified **owner, release API, stop/join barrier**.
- [ ] If file mapping, distinguished **shared memory visibility** from **persistence/force**.
- [ ] Tests proving aliasing, independent snapshot, bounds, endianness, and lifetime all pass.

**Conclusion:** `MemorySegment.ofBuffer` and `MemorySegment.asByteBuffer` are **view conversions**. They allow accessing the same byte region together without creating hidden copies. For that exact reason, code must explicitly manage **offsets, endianness, alignment, write permissions, scope, and ownership**. **A zero-copy view is a data-sharing mechanism, not a safety guarantee or a copying strategy.**

### Official Documentation

- [JEP 454 — Foreign Function & Memory API finalized in Java 22](https://openjdk.org/jeps/454)
- [Java SE 25 — MemorySegment: `ofBuffer`, `asByteBuffer`, scope, alignment, slices, copy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 25 — ByteBuffer: position/limit, direct, slice/duplicate, byte order](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 25 — Buffer: position, limit, capacity](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/Buffer.html)
- [Java SE 25 — Arena: confined/shared/auto and close](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 25 — ValueLayout and alignment](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Java SE 25 — FileChannel.map: MappedByteBuffer and MemorySegment with Arena](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/FileChannel.html)
- [Java SE 25 — MappedByteBuffer.force](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/MappedByteBuffer.html)
