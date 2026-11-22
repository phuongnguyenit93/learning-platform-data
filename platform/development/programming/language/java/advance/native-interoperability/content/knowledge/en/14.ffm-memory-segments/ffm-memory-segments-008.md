# Creating a MemorySegment from an Array or ByteBuffer and Understanding Backing Storage Lifetime

In the Foreign Function & Memory API (FFM), `MemorySegment` describes a **contiguous memory region with a defined size, access permissions, and lifetime**. Many FFM examples use `Arena.allocate(...)` to allocate native memory, but not every segment needs to be allocated manually. Java allows creating **zero-copy views** from a primitive array using `MemorySegment.ofArray(...)` or from a `java.nio.Buffer` using `MemorySegment.ofBuffer(...)`.

The tricky part is not just the syntax: the created segment **does not inherently own a copy of the data**. It references existing backing memory. That backing storage can be on the **Java heap**, in a **direct ByteBuffer** managed by the JVM/cleaner, or in a **native allocation scoped by an Arena**. Each case has its own lifecycle; turning an object into a `MemorySegment` **does not arbitrarily transfer ownership**.

This article uses the stable API from **JDK 22 onwards** (FFM finalized in JEP 454), clarifying byte mapping, aliasing, position/limit, read-only, GC reachability, `Arena`, thread confinement, common mistakes, and a runnable Java example.

## 1. Mental model: the segment is a view, the backing storage holds the bytes

Imagine a memory region consisting of four bytes:

```text
Backing storage
index:      0       1       2       3
bytes:     [10]    [20]    [30]    [40]
              \       |       /
               \      |      /
              MemorySegment view
              address + bounds + scope
```

A `MemorySegment` stores/models:

- **Accessible byte region:** `byteSize()` and offsets, with bounds checking (spatial bounds).
- **Memory source:** `isNative()` distinguishes native/off-heap segments from heap segments.
- **Writability:** `isReadOnly()` and methods to create read-only views.
- **Lifetime:** `scope()` describes when access remains valid (temporal bounds).
- **Thread constraint:** a segment may only be accessible by the owner thread of `Arena.ofConfined()`.
- **Typed read/write operations:** `get(ValueLayout.JAVA_BYTE, offset)`, `set(...)`, `getAtIndex(...)`, etc.

Two segments can differ in their **visible range** while pointing to the same backing bytes; writing through one view will show up in the other view. That is **aliasing**. On the other hand, calling `toArray(...)` or `MemorySegment.copy(...)` actually **copies data**, creating a different ownership relationship.

Do not confuse a segment with a raw C pointer: the `address()` of a heap segment is **not** a native address that can be arbitrarily passed to C. The Java GC can move arrays; FFM hides this detail through heap segment representation and access control mechanisms. For a native segment, the address is a native address, but it must still obey lifetime and bounds.

## 2. `MemorySegment.ofArray(...)`: view over a Java array

The API supports the following primitive arrays:

```java
MemorySegment.ofArray(byte[]);
MemorySegment.ofArray(char[]);
MemorySegment.ofArray(short[]);
MemorySegment.ofArray(int[]);
MemorySegment.ofArray(long[]);
MemorySegment.ofArray(float[]);
MemorySegment.ofArray(double[]);
```

This is an **illustrative list of overload signatures**, not standalone runnable Java code. There is no direct overload for `boolean[]`, `Object[]`, or `String[]`; you cannot assume every Java array can be used as a byte block in FFM.

A small example:

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

byte[] bytes = {10, 20, 30, 40};
MemorySegment segment = MemorySegment.ofArray(bytes);

System.out.println(segment.byteSize());                 // 4
System.out.println(segment.isNative());                 // false
System.out.println(segment.get(ValueLayout.JAVA_BYTE, 1)); // 20

segment.set(ValueLayout.JAVA_BYTE, 1, (byte) 21);
System.out.println(bytes[1]);                           // 21
```

This is a **snippet inside a Java method**, not a complete file. It demonstrates that `ofArray` **does not copy**: changes through the segment directly update the original array, and subsequent changes to `bytes[i]` will be read through the segment.

With `int[]`, each element has four bytes:

```java
int[] numbers = {100, 200};
MemorySegment ints = MemorySegment.ofArray(numbers);

System.out.println(ints.byteSize()); // 8
ints.setAtIndex(ValueLayout.JAVA_INT, 1, 250);
System.out.println(numbers[1]);     // 250
```

Here `getAtIndex/setAtIndex` take an **element index according to ValueLayout** (for example `JAVA_INT` has a width of 4 bytes), whereas `get/set` take a **byte offset**. Do not use `segment.get(JAVA_INT, 1)` to read element `numbers[1]`: a 1-byte offset is the wrong position and may violate alignment.

### 2.1. Scope of a Java array

`MemorySegment.ofArray(array)` returns a **heap segment** with an **automatic scope** that keeps the backing array reachable. As long as the segment or its related views remain reachable, the JVM must not collect the backing array because it is still needed for permitted accesses. The segment can be accessed from multiple threads according to its scope, but it **does not automatically guarantee data thread-safety**: if two threads write to the same element unsynchronized, there is still a data race.

There is no `arena.close()` operation to free the bytes of an array wrapped by `ofArray`: the array belongs to the Java heap and is managed by the garbage collector. Calling `DeleteLocalRef` in JNI, `free` in C, or trying to manually trigger a cleaner is not how heap segments are managed here.

### 2.2. `heapBase()` and `address()`

`heapBase()` indicates the Java object that is the heap backing when the API permits; for a writable segment from `byte[]`, you can get back the exact original array. When a segment is read-only, `heapBase()` may return `Optional.empty()` even though the segment is still on the heap. Therefore, **do not use `heapBase().isPresent()` as a universal way to distinguish heap vs. native**; use `isNative()`.

A heap segment created directly with `ofArray` typically has `address() == 0`, but that is **not a NULL native pointer** and not a stable physical address. For a slice of a heap segment, the address represents a relative offset to the heap base. Do not store the `address()` of a heap segment as a C pointer or a handle with an independent lifetime.

## 3. `MemorySegment.ofBuffer(...)`: view over the remaining part of a Buffer

API signature:

```java
static MemorySegment ofBuffer(java.nio.Buffer buffer)
```

`Buffer` includes `ByteBuffer` and typed buffers such as `IntBuffer`, `CharBuffer`. `ofBuffer` does not simply take the entire capacity of the buffer. According to the API, the segment represents **the range from `position()` (inclusive) to `limit()` (exclusive)** at the time the view is created.

For `ByteBuffer`, position/limit count bytes. For `IntBuffer`, they count int elements and the segment has a byte length corresponding to the number of elements multiplied by the size of each element. You must always know which buffer type you are working with.

### 3.1. Heap ByteBuffer example: zero-copy, respects position/limit

```java
byte[] bytes = {10, 20, 30, 40};
ByteBuffer buffer = ByteBuffer.wrap(bytes);
buffer.position(1);
buffer.limit(3);

MemorySegment window = MemorySegment.ofBuffer(buffer);

System.out.println(window.byteSize());                    // 2
System.out.println(window.get(ValueLayout.JAVA_BYTE, 0)); // 20

window.set(ValueLayout.JAVA_BYTE, 1, (byte) 31);
System.out.println(bytes[2]);                             // 31
```

Snippet inside a Java method that already has `java.nio.ByteBuffer` and FFM imports.

Exact byte mapping:

```text
Original array: [10] [20] [30] [40]
Index:           0    1    2    3
ByteBuffer: position=1, limit=3
View segment:         [20] [30]
View offset:            0    1
                        |
segment.set(offset=1, 31) -> array[2] = 31
```

`window.byteSize() == buffer.remaining() == 2` in this `ByteBuffer` case. Offset 0 of the segment corresponds to **position 1 of the buffer**, not necessarily index 0 in the array.

Creating a segment does not cause the buffer to automatically `flip()`, `clear()`, or change its cursor. Changing `buffer.position(...)` **after creation** also does not change the view range already recorded by the segment; if you want a different range, create a new segment from the new buffer state.

### 3.2. `ByteBuffer.allocate(...)` and `ByteBuffer.wrap(...)`

These two methods create/wrap a **heap buffer**. When the backing storage is actually backed by a primitive array, `MemorySegment.ofBuffer(buffer)` creates a **heap segment** with the same backing storage; it does not move memory to native.

`ByteBuffer.wrap(bytes, start, length)` has position and limit set as requested; do not confuse the `start` parameter with a direct offset in the segment. The least error-prone way is to create the buffer, check `position/limit/remaining`, then create the segment and access offsets starting from **0**.

A heap buffer can be a read-only view; `hasArray()` does not always return true even if it internally still has a backing array. Conversely, some heap `Buffer`s are genuinely **not backed by an array** (for example `CharBuffer.wrap(CharSequence)`), and `MemorySegment.ofBuffer` may throw `IllegalArgumentException` according to the Javadoc. Do not treat every `Buffer` object as always convertible to a segment.

### 3.3. Read-only must be preserved

```java
ByteBuffer readOnly = ByteBuffer.wrap(new byte[] {1, 2})
                                .asReadOnlyBuffer();
MemorySegment segment = MemorySegment.ofBuffer(readOnly);

System.out.println(segment.isReadOnly()); // true
```

Converting via `ofBuffer` **does not strip read-only permission**. Attempting `segment.set(...)` on a read-only segment will fail (the FFM API uses `IllegalArgumentException` when writing to a read-only segment); whereas `ByteBuffer.put(...)` on a read-only buffer uses NIO's own exception. Do not use one view to try to bypass the access permissions of another view.

## 4. Direct ByteBuffer: still aliases, but memory resides outside the Java heap

`ByteBuffer.allocateDirect(n)` allocates a **direct buffer**, typically holding bytes in native/off-heap memory. `MemorySegment.ofBuffer(direct)` returns a **native segment**:

```java
ByteBuffer direct = ByteBuffer.allocateDirect(4);
direct.put(1, (byte) 7);
direct.position(1);
direct.limit(3);

MemorySegment segment = MemorySegment.ofBuffer(direct);
System.out.println(segment.isNative());                 // true
System.out.println(segment.byteSize());                 // 2
System.out.println(segment.get(ValueLayout.JAVA_BYTE, 0)); // 7

segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 9);
System.out.println(direct.get(1));                      // 9
```

The code is a snippet inside a method. The native segment here is still just a **view of the backing memory belonging to the direct buffer**. There is no second FFM native allocation and no `free()` call needed for `segment`.

### 4.1. Who owns the lifetime of a direct buffer?

If a direct buffer is created in the standard way such as `allocateDirect`, its native backing memory is managed according to a lifecycle determined by the JVM/implementation, usually via reachability/cleaner and without a deterministic reclamation point chosen by the caller.

**The `ofBuffer` specification explicitly states:** when the buffer is not derived directly from `MemorySegment.asByteBuffer()` of an existing scope, the segment receives an **automatic scope that keeps the buffer reachable**. Thus, a segment or its slice remaining reachable will keep the backing direct buffer reachable and prevent the memory managed by the buffer from being deallocated prematurely just because the original `ByteBuffer` variable left the Java scope.

That does **not** allow manually calling native `free(address)`, `Unsafe.freeMemory`, or manually triggering a cleaner on the direct buffer. Out-of-contract deallocation operations can leave a dangling pointer while the `MemorySegment` is still alive. An automatic scope cannot protect against another native library **actively** freeing the memory region from outside the JVM.

Do not try `System.gc()` to "prove" that the segment retains memory: the GC is under no obligation to collect at the exact time you request. Test behavior via valid accesses while the object is still reachable and via explicit scope contracts, not via expectations about memory collection schedules.

### 4.2. Mapped ByteBuffer and resources outside the JVM

If the `Buffer` is a mapped buffer, `MemorySegment.ofBuffer` can yield a mapped native segment according to the backing memory's properties. Do not treat every direct buffer as a file mapping, and do not close the file/mapping or perform manual unmapping while code is still using the view.

With a memory-mapped file created by FFM's `FileChannel.map(..., Arena)`, the arena can own the mapping lifetime; with NIO `MappedByteBuffer`, the lifecycle usually depends on reference cleanup/implementation. Distinguishing **who allocates/maps** and **who has the right to close** is a mandatory requirement in the contract.

## 5. Subtle case: buffer originating from `MemorySegment.asByteBuffer()`

This is the decisive distinction in this article regarding lifetime.

Suppose an arena is used to allocate native memory and then converted to an NIO buffer:

```java
MemorySegment viewOutside;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment owner = arena.allocate(8);
    owner.set(ValueLayout.JAVA_BYTE, 0, (byte) 55);

    ByteBuffer nioView = owner.asByteBuffer();
    viewOutside = MemorySegment.ofBuffer(nioView);

    System.out.println(
        viewOutside.get(ValueLayout.JAVA_BYTE, 0)); // 55
}

// Arena is closed. Both owner and viewOutside
// are bound to the arena's lifetime.
try {
    viewOutside.get(ValueLayout.JAVA_BYTE, 0);
} catch (IllegalStateException expected) {
    System.out.println("closed-scope");
}
```

Snippet inside a method with imports `Arena`, `MemorySegment`, `ValueLayout`, `ByteBuffer`.

**Rule from Javadoc:** if a buffer is created from `asByteBuffer()` of a segment with scope `S`, the segment recreated by `ofBuffer(buffer)` **is attached to the same scope `S`**. Exiting `try (Arena ...)` closes `Arena.ofConfined()`, causing the backing native allocation to be freed; keeping `nioView` or `viewOutside` in Java **does not extend the lifetime**.

Therefore:

- `ByteBuffer.allocateDirect(...) → MemorySegment.ofBuffer(...)`: a buffer managed by the JVM under an automatic scope keeping the buffer reachable.
- `Arena.allocate(...) → asByteBuffer() → MemorySegment.ofBuffer(...)`: the buffer/segment views **borrow** the arena's lifetime; closing the arena is the invalidation point for all views.

Both are native segments and usually have `isNative() == true`. **You cannot infer lifetime solely from `isNative()`**. You must trace the origin of the backing storage.

### 5.1. `asByteBuffer()` does not transfer ownership

`MemorySegment.asByteBuffer()` creates an NIO view over the same bytes. It **does not copy**, does not create a new arena, and does not change to the lifetime of `ByteBuffer.allocateDirect`.

A `ByteBuffer` returned from `asByteBuffer()` typically has:

- `position = 0`.
- `limit = capacity = segment.byteSize()`.
- The same read-only property as the segment.
- Direct if the segment is native.
- Initial byte order is `BIG_ENDIAN` (according to `asByteBuffer` Javadoc), which can be changed by calling `order(...)`.

If the segment is larger than `Integer.MAX_VALUE` or cannot be represented as a ByteBuffer, `asByteBuffer()` may throw `UnsupportedOperationException`. A segment can support sizes larger than the `int` limit of an NIO buffer; **do not force every large memory-mapped workload through ByteBuffer**.

### 5.2. Closing the arena also invalidates the NIO buffer

When a `ByteBuffer` comes from an arena segment, using it after the arena is closed may throw `IllegalStateException`. If the arena is confined, accessing it from another thread may throw `WrongThreadException`.

Do not try to take a view from a segment and export it as an API returning a "live forever" `ByteBuffer` if the arena is about to close:

```java
// Anti-pattern: returns a view over a region that will be closed before the caller uses it.
static ByteBuffer invalidView() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(16).asByteBuffer();
    }
}
```

This is an **anti-pattern that compiles** but returns a view that cannot be safely used after the method exits. The right way is to lift ownership of the arena to the caller, or copy the bytes before closing.

## 6. Lifetime table: the origin of the view determines ownership

| How the segment is created | Memory type | Primary scope/lifetime | Who frees the backing storage? |
| --- | --- | --- | --- |
| `MemorySegment.ofArray(byte[])` | Heap | Automatic scope keeping array reachable, multi-thread access | Java GC, no manual close |
| `MemorySegment.ofBuffer(ByteBuffer.allocate(n))` | Heap | Automatic scope keeping backing buffer/array reachable | Java GC |
| `MemorySegment.ofBuffer(ByteBuffer.wrap(array))` | Heap | Automatic scope keeping backing buffer/array reachable | Java GC |
| `MemorySegment.ofBuffer(ByteBuffer.allocateDirect(n))` | Native | Automatic scope keeping direct buffer reachable | Direct buffer's JVM/allocator per contract |
| `MemorySegment.ofBuffer(arenaSegment.asByteBuffer())` | Native (if arena is native) | **The exact scope of `arenaSegment`** | Arena owner closes at the right time |
| `arena.allocate(bytes)` | Native | Scope of `Arena.ofConfined/ofShared/ofAuto/...` | Arena/cleaner per arena kind |
| `segment.asSlice(offset, length)` | Same as original segment | Inherited scope/lifetime | Owner of the original backing storage |
| `segment.asReadOnly()` | Same as original segment | Inherited scope/lifetime, only removes write permission | Owner of the original backing storage |
| `segment.toArray(ValueLayout.JAVA_BYTE)` | **New** Java array | New array no longer aliases the original segment | Java GC for the new array |

Note: `Arena.ofAuto()` is an automatic scope managed by reachability, not explicitly closed; `Arena.global()` has no active close point; `Arena.ofConfined()` and `Arena.ofShared()` are closeable arenas. This section only uses common arena types; API callers must consult the Javadoc of the JDK version they are running.

Do not "double close" a native allocation when multiple views reference it. A segment slice is not the separate owner of an allocation. If a library needs independent ownership, explicitly define a transfer or allocate/copy new data.

## 7. Distinguishing *alias/view* from *copy/snapshot*

An operation that preserves the backing storage:

```java
byte[] original = {1, 2, 3, 4};
MemorySegment all = MemorySegment.ofArray(original);
MemorySegment slice = all.asSlice(1, 2);

slice.set(ValueLayout.JAVA_BYTE, 0, (byte) 9);
System.out.println(original[1]); // 9
```

`asSlice(1, 2)` creates no allocation: the slice has `byteSize() == 2`, and offset 0 of the slice corresponds to index 1 of the array. Changes through the slice are observed through `all`, `original`, and any other view of that region.

Conversely, creating a snapshot:

```java
byte[] snapshot = slice.toArray(ValueLayout.JAVA_BYTE);
slice.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);

System.out.println(snapshot[0]); // 9 (independent copy)
System.out.println(original[1]); // 7 (original region)
```

These are two snippets **inside a method**; the second snippet assumes `slice` and `original` already exist from the first snippet.

Another way to copy to a separate native region:

```java
try (Arena destinationArena = Arena.ofConfined()) {
    MemorySegment destination = destinationArena.allocate(
        slice.byteSize());
    MemorySegment.copy(slice, 0, destination, 0, slice.byteSize());

    // destination has its own backing allocation:
    // modifying slice does not automatically modify destination.
}
```

The last snippet illustrates code when `slice` is valid and not read-only; the copied region has the lifetime of `destinationArena`. If the result needs to live outside the block, do not return `destination` while still closing the arena; you can return a `byte[]` copy or transfer arena ownership to the caller.

### 7.1. When should you copy instead of using a view?

Copying has allocation and memory bandwidth costs, but is useful when:

1. Data must live **longer than the original arena**, for example a result returned from an API outside `try-with-resources`.
2. Caller/callee need **independent ownership**, not wanting changes on one side to immediately appear on the other.
3. The buffer is reused for receiving the next packet, while an async task still needs the old snapshot.
4. Data travels between threads without synchronization mechanisms or without wanting to retain a backing direct buffer for long.
5. Native data is unsafe to reference after a callback, or a C library only guarantees the pointer for a short time.

Do not copy just to conveniently change Java types when zero-copy sharing is permitted by the lifetime contract; but do not optimize with zero-copy if it forces retaining a very large allocation longer than necessary.

## 8. Byte offsets, alignment, and byte order

FFM reads/writes through a specific `ValueLayout`:

```java
segment.get(ValueLayout.JAVA_BYTE, 0);
segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);

segment.get(ValueLayout.JAVA_INT, 0);
segment.setAtIndex(ValueLayout.JAVA_INT, 1, 42);
```

These illustrative lines require a `segment` that is large enough and properly aligned. Rules:

- `get/set(layout, offset)` uses a **byte offset**.
- `getAtIndex/setAtIndex(layout, index)` uses a **logical index**, where the actual offset is multiplied by `layout.byteSize()`.
- `ValueLayout.JAVA_INT` requires four bytes for an `int` value, with corresponding alignment. If a buffer window starts at an odd byte offset, an int operation at the start of the view may **fail alignment**; use a byte layout or an appropriate unaligned layout when data is packed per contract.
- `ValueLayout.JAVA_INT` uses **native byte order**. `ByteBuffer.order()` may be big-endian or little-endian; changing the ByteBuffer's byte order **does not automatically change ValueLayout**. To decode binary data the same way, specify `ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN)` or the order required by the protocol.
- A heap array `int[]` is not an arbitrarily formatted `byte[]`: when creating a segment from `int[]`, compatible layout/bounds/alignment must be used.

Example of reading little-endian data from a buffer window (code placed inside a method):

```java
ByteBuffer b = ByteBuffer.allocate(4);
b.put(0, (byte) 0x04);
b.put(1, (byte) 0x03);
b.put(2, (byte) 0x02);
b.put(3, (byte) 0x01);

MemorySegment s = MemorySegment.ofBuffer(b);
int n = s.get(
    ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.LITTLE_ENDIAN),
    0);
System.out.println(n); // 16909060 (0x01020304)
```

Here `JAVA_INT_UNALIGNED` allows packed regions that are not always int-aligned (even though the example buffer has offset 0), and `withOrder` makes the result independent of CPU endianness. Also import `java.nio.ByteOrder`. For real binary protocols, you also need to define signedness, magic/version, length, checksum, and bounds checks.

## 9. Complete Java 22+ program: testing aliasing, bounds, and lifetime

The following example **requires no JNI or C library**; it only uses the stable `java.lang.foreign` API. The printed values are deterministic, not relying on native addresses or GC timing.

### 9.1. File `SegmentBackingDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;

public final class SegmentBackingDemo {
    public static void main(String[] args) {
        // 1. ofArray: heap memory, zero-copy alias.
        byte[] bytes = {10, 20, 30, 40};
        MemorySegment fromArray = MemorySegment.ofArray(bytes);

        System.out.println("array-native=" + fromArray.isNative());

        fromArray.set(ValueLayout.JAVA_BYTE, 1, (byte) 21);
        System.out.println("array-second=" + bytes[1]);

        // 2. ofBuffer on a heap ByteBuffer only views position..limit.
        ByteBuffer heapBuffer = ByteBuffer.wrap(bytes);
        heapBuffer.position(1);
        heapBuffer.limit(3);

        MemorySegment window = MemorySegment.ofBuffer(heapBuffer);
        System.out.println("window-size=" + window.byteSize());
        System.out.println(
            "window-first=" + window.get(ValueLayout.JAVA_BYTE, 0));

        window.set(ValueLayout.JAVA_BYTE, 1, (byte) 31);
        System.out.println("array-third=" + bytes[2]);
        System.out.println(
            "buffer-cursor=" + heapBuffer.position()
                + "/" + heapBuffer.limit());

        // 3. Typed primitive array; int index is multiplied by 4 bytes.
        int[] numbers = {100, 200};
        MemorySegment intSegment = MemorySegment.ofArray(numbers);
        intSegment.setAtIndex(ValueLayout.JAVA_INT, 1, 250);
        System.out.println("ints-bytes=" + intSegment.byteSize());
        System.out.println("ints-second=" + numbers[1]);

        // 4. Direct ByteBuffer: native memory, still zero-copy.
        ByteBuffer direct = ByteBuffer.allocateDirect(4);
        direct.put(1, (byte) 7);
        direct.position(1);
        direct.limit(3);

        MemorySegment directWindow = MemorySegment.ofBuffer(direct);
        System.out.println("direct-native=" + directWindow.isNative());
        System.out.println("direct-size=" + directWindow.byteSize());

        directWindow.set(ValueLayout.JAVA_BYTE, 0, (byte) 9);
        System.out.println("direct-at-one=" + direct.get(1));

        // 5. Read-only permission is inherited.
        ByteBuffer readOnly =
            ByteBuffer.wrap(new byte[] {1, 2}).asReadOnlyBuffer();
        MemorySegment readOnlySegment = MemorySegment.ofBuffer(readOnly);
        System.out.println("read-only=" + readOnlySegment.isReadOnly());

        // 6. A ByteBuffer from an Arena does not outlive the Arena.
        MemorySegment viewFromArenaBuffer;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment allocated = arena.allocate(2);
            allocated.set(ValueLayout.JAVA_BYTE, 0, (byte) 55);

            ByteBuffer nioView = allocated.asByteBuffer();
            viewFromArenaBuffer = MemorySegment.ofBuffer(nioView);

            System.out.println(
                "arena-value="
                    + viewFromArenaBuffer.get(ValueLayout.JAVA_BYTE, 0));
        }

        System.out.println(
            "arena-scope-alive="
                + viewFromArenaBuffer.scope().isAlive());

        try {
            viewFromArenaBuffer.get(ValueLayout.JAVA_BYTE, 0);
            System.out.println("unexpected-access");
        } catch (IllegalStateException expected) {
            System.out.println("after-close=IllegalStateException");
        }
    }
}
```

**Explanation in order of output:**

1. `array-native=false`: `ofArray(byte[])` is a heap segment.
2. `array-second=21`: the segment modifies the source array itself.
3. `window-size=2` and `window-first=21`: `position=1, limit=3` creates a view of exactly two bytes, and offset 0 of the view points to element `array[1]`.
4. `array-third=31`: writing offset 1 of the view affects `array[2]`.
5. `buffer-cursor=1/3`: creating/using a segment does not automatically change the position and limit of the original buffer.
6. `ints-bytes=8`, `ints-second=250`: an array of two `int`s has eight bytes; `setAtIndex` updates the second element.
7. `direct-native=true` and `direct-size=2`: a direct buffer yields a native segment, but only has a two-byte view in the range position..limit.
8. `direct-at-one=9`: the segment and direct buffer share the same backing allocation.
9. `read-only=true`: read-only is preserved.
10. `arena-value=55`: the NIO view from the arena is still readable before closing.
11. `arena-scope-alive=false` and `after-close=IllegalStateException`: the view segment created back from the buffer shares the same lifetime as the original arena.

### 9.2. Compiling and running

Use **JDK 22 or later**. The FFM API in JDK 21 was still in preview and had different usage rules; this article does not target JDK 17 or Java 21 preview.

```bash
javac SegmentBackingDemo.java
java SegmentBackingDemo
```

**Exact stdout of the program:**

```text
array-native=false
array-second=21
window-size=2
window-first=21
array-third=31
buffer-cursor=1/3
ints-bytes=8
ints-second=250
direct-native=true
direct-size=2
direct-at-one=9
read-only=true
arena-value=55
arena-scope-alive=false
after-close=IllegalStateException
```

This example **does not call foreign functions**, does not `reinterpret` addresses, and does not use restricted linker APIs; therefore, with standard JDK 22, **you do not need `--enable-preview`** to compile or run. If you deploy an FFM program that calls restricted native access APIs, you must configure native access permissions according to the actual JDK/module.

### 9.3. Why not print addresses or force GC?

We do not print `segment.address()` or `ByteBuffer` raw pointers because they depend on the JVM, ASLR, OS, and each run. Nor do we force `System.gc()` to test direct buffer lifetime: whether GC runs at that moment or not is not a Java contract.

In contrast, `Arena.ofConfined()` has a deterministic close point. This allows testing **scope-bound lifetime** reliably, without guessing when a cleaner will reclaim memory.

## 10. Lifetime: how does automatic scope differ from explicit close?

FFM provides scopes to attach *temporal bounds* to access permissions. However, **not every scope allows the caller to close it**.

### 10.1. Automatic scope of arrays/direct buffers

When creating a segment from an array or a standard NIO direct buffer, FFM uses an automatic scope to keep the backing object reachable. It has no close method for you to manually "free early" the buffer's memory.

This is **reachability-based** management, not a "10-second TTL". Memory only becomes eligible for reclamation when no related references remain and the runtime decides to perform cleanup. A `MemorySegment`, `asSlice`, or view remaining reachable can prolong the retention of the backing direct buffer. In systems reading large files/sockets, keeping such segment views in a cache for a long time can prolong the **native memory footprint**.

### 10.2. Confined/shared arena: caller owns the close point

`Arena.ofConfined()` and `Arena.ofShared()` create closeable arenas. Native memory allocated in those arenas is invalidated after closing. The segment's scope is still used to check liveness and thread accessibility.

- `Arena.ofConfined()`: only the owner thread may access/close; other threads may receive `WrongThreadException` on access.
- `Arena.ofShared()`: multiple threads may access, and it can be closed per arena rules; however, synchronization is still required when sharing mutable data.
- `Arena.ofAuto()`: automatic memory management, no active close; cleanup timing depends on reachability.
- `Arena.global()`: global lifetime, no manual close; avoid uncontrolled allocations if resource limits are desired.

Do not send a segment from a confined arena to another worker thread and expect it to be usable just because the Java object is still reachable. Reachability and thread confinement are **two independent checks**.

### 10.3. Checking `scope().isAlive()` does not make access permanently safe

You can observe:

```java
boolean alive = segment.scope().isAlive();
boolean allowed = segment.isAccessibleBy(Thread.currentThread());
```

This is code inside a method that already has a valid `segment`.

However, both checks are **point-in-time** observations. With a shared arena, another thread may start closing the arena right after you check. FFM itself performs temporal/spatial bounds checks on every operation; do not use `isAlive()` as a long-term lifetime certificate. In concurrent APIs, an explicit ownership and shutdown protocol is needed.

## 11. Native interop: a heap view does not automatically become a C pointer

The appearance of `MemorySegment` in FFM does not mean every backing storage has a valid native address.

### 11.1. Heap array

`MemorySegment.ofArray(byte[])` is on the Java heap. GC can move the object, and the segment does not turn the array into a stable malloc region. You must **not** take `heap.address()` and use it as the C address of `byte[0]`. When a C API requires a native pointer to a stable buffer, the common safe choice is:

1. Allocate off-heap via `Arena.allocate(n)` matching the lifecycle.
2. Copy bytes from the heap segment to the native segment with `MemorySegment.copy(...)`.
3. Call the native function while the arena is alive and synchronize access permissions.
4. Copy results back when required by the contract.
5. Close the arena once no native code holds the pointer.

Some FFM linker options have special support for heap segments under specific conditions; do not extrapolate these exceptions into permission to pass any heap address to a native library.

### 11.2. Direct buffer

A direct buffer is backed by native memory, but the native library needs a contract regarding **byte count, alignment, read-only, ownership, and pointer retention duration**. When native code only reads/writes **synchronously during the call**, a live view may be suitable. If native code **stores the pointer for use after the function returns**, keeping a temporary Java object on the current stack is not enough: there must be an owner ensuring the backing memory stays alive until the native async operation completes.

Do not freely `free()` an address obtained from a direct buffer unless the API owning the allocation explicitly requires it. A standard direct buffer is not synonymous with a C `malloc` owned by the caller.

### 11.3. Arena-backed ByteBuffer

If a native callback receives a `ByteBuffer` from a segment allocated by an arena, that region becomes invalid when the arena closes, **even if the buffer or a new segment created from it is still held in a Java field**. When passing an API across multiple layers, also pass the **ownership/lifetime contract**, not just returning a `ByteBuffer` or `MemorySegment`.

A common design pattern is an `AutoCloseable` owner object holding both the `Arena` and `MemorySegment`, or performing a copy at the boundary if the caller cannot hold the arena.

## 12. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking `ofArray` copies data | It creates a view over the original array | If a snapshot is needed, use `toArray` or `copy` |
| Thinking `ofBuffer` always views the entire capacity | The API takes `position..limit` | Check `remaining()`; set the cursor before wrapping |
| Thinking `segment offset=0` is always `array[0]` | The buffer may have a position/array offset | Map view offsets according to the buffer window |
| Changing buffer position and expecting an already-created segment to change range | The segment keeps the view determined at creation | Create a new segment when you want a different window |
| Thinking `isNative() == true` means memory is owned by an arena | Direct ByteBuffers are also typically native | Trace the origin of the backing storage |
| Closing the arena and keeping `asByteBuffer()` | The view does not extend the arena lifetime | Keep the arena alive or copy before closing |
| Using `System.gc()` to actively release direct memory | GC has no caller-controlled deadline | Manage resources/lifetimes explicitly, reduce reference retention |
| Treating `heapBase().isEmpty()` as meaning native | A read-only heap segment may hide heapBase | Use `isNative()` |
| Using `address()` of a heap segment as a C pointer | A heap address is not a native address | Copy/design the FFM call appropriately |
| Calling `set(JAVA_INT, 1, x)` to write the second int | The offset is in **bytes**, not an index | `setAtIndex(JAVA_INT, 1, x)` or `offset=4` |
| Mixing `ByteBuffer.order()` with `ValueLayout.JAVA_INT` arbitrarily | The two APIs have separate byte orders | Configure `ValueLayout.withOrder(...)` |
| Accessing an int at a view starting at an odd byte | May violate alignment | Choose an appropriate unaligned layout or copy/align |
| Treating a read-only buffer as a writable segment | Read-only is inherited | Write to a writable copy if needed |
| Accessing `Arena.ofConfined` from another thread | Thread confinement | Use the owner thread or a shared arena per contract |
| Trusting `isAlive()` as a guarantee for the entire future | The scope may be closed after the check | Synchronization and ownership protocol |
| Manually freeing memory of `ByteBuffer.allocateDirect` | Double-free/dangling view | Let the JVM owner manage it per contract |
| Manually mapping/unmapping externally while an FFM view exists | Lifetime is no longer controlled by the segment | Centralize ownership and release per contract |
| Passing a raw pointer from a heap array to C | GC can move heap objects | Use FFM/native allocation properly |
| Using `ByteBuffer` for a segment larger than 2 GiB | NIO buffer index/capacity is int-limited | Access the segment directly using long offsets |

## 13. Test cases and how to observe

To verify code you write, you should have the following tests:

1. **Heap alias:** create a `byte[]`, wrap with `ofArray`, write through the segment, compare bytes in the array. Reverse direction: update the array and read back through the segment.
2. **Buffer window:** set `position=2`, `limit=5` on a six-byte buffer; the segment must have `byteSize=3`. Offset 0 of the segment must be the original byte at position 2.
3. **Cursor snapshot:** after creating the segment, change position/limit of the original buffer; the segment does not automatically change its existing view.
4. **Direct alias:** `allocateDirect` → `ofBuffer` → write from segment → read back via `ByteBuffer.get(index)`.
5. **Read-only:** create `asReadOnlyBuffer`; `ofBuffer` must preserve read-only and block writes.
6. **Unbacked heap Buffer:** with `CharBuffer.wrap("abc")`, verify `ofBuffer` may throw `IllegalArgumentException` due to having no array backing per Javadoc; do not assume success for every Buffer.
7. **Arena lifetime:** `arena.allocate → asByteBuffer → ofBuffer`; access before close succeeds, after close throws `IllegalStateException`.
8. **Thread confinement:** a segment from `Arena.ofConfined` accessed on the wrong thread must fail appropriately; write a deterministic test with thread join and exception capture. Do not substitute with race-prone `Thread.sleep`.
9. **Snapshot:** `toArray(JAVA_BYTE)` before modifying the view; the snapshot must retain the old values.
10. **Bounds:** reading at an offset exceeding `byteSize()` must throw `IndexOutOfBoundsException`, even if the original backing array still has bytes outside the window.
11. **Alignment:** test a packed byte protocol reading an int with an aligned layout and verify `IllegalArgumentException` at an unaligned offset; use an unaligned layout if the contract permits.
12. **Endian:** use a fixed byte pattern, verify `withOrder(LITTLE_ENDIAN)` on big- or little-endian JVMs against expected results.
13. **Liveness and reachability:** use lifetimes guaranteed by Arena/scope for deterministic tests; do not write tests depending on `System.gc()` reclaiming a direct buffer immediately.
14. **Native async:** if a foreign call stores a pointer, verify data ownership and that cleanup only happens after callback/completion, including timeouts.
15. **Performance:** measure throughput and native memory footprint of zero-copy views vs. snapshots at realistic sizes, rather than assuming zero-copy is always better.

A small assertion test without JUnit (placed inside a method with `byte[] bytes`):

```java
MemorySegment s = MemorySegment.ofArray(bytes);
int previous = Byte.toUnsignedInt(s.get(ValueLayout.JAVA_BYTE, 0));
byte[] clone = s.toArray(ValueLayout.JAVA_BYTE);
s.set(ValueLayout.JAVA_BYTE, 0, (byte) (previous + 1));
if (clone[0] == bytes[0]) {
    throw new AssertionError("Expected independent snapshot");
}
```

This is an **illustrative test snippet**; since byte values can wrap when incremented, the conclusion here relies only on the snapshot retaining the old value, without assuming the incremented value stays within the signed byte range. In production, use JUnit and explicit test fixtures.

## 14. Design checklist and takeaways

Before returning a `MemorySegment` from an API or passing it to another layer:

- Was the segment created with `ofArray`, `ofBuffer`, `Arena.allocate`, or `asSlice`?
- Is the backing storage Java heap, a JVM-managed direct ByteBuffer, a file mapping, or an arena/native library allocation?
- Is there a **copy** or just an **alias view**? If an alias, which side can mutate the bytes?
- Did `ofBuffer` capture the exact `position..limit` range? Which byte in backing storage does offset 0 correspond to?
- Is the segment read-only? Does the layout use the protocol's correct byte alignment and byte order?
- Is `scope()` automatic or arena-bound? Who keeps the backing object reachable or who keeps the arena alive?
- If closing the arena, can ByteBuffer views or segments recreated from them escape outside?
- Is a shared or confined arena being used? Could it be accessed from another thread or race with close?
- Does any native code retain the pointer across calls? If so, which owner ensures the memory stays alive?
- Are you relying on `address()` of a heap segment or GC timing as a native lifetime guarantee?
- If data needs to live independently, has a snapshot/copy been created and is there a close contract for the new allocation?
- Have tests proven aliasing, copying, read-only, bounds, liveness, and thread confinement behave as expected?

**Conclusion:** `MemorySegment.ofArray(array)` and `MemorySegment.ofBuffer(buffer)` primarily create **safe access windows into existing memory**. `ofArray` keeps the Java array reachable. `ofBuffer` on a standard buffer uses an automatic scope keeping the buffer reachable, but if the buffer originates from `segment.asByteBuffer()`, the new segment **inherits the scope of the original segment**. Trace the **allocation source, scope, and actual close point**, rather than guessing lifetime from the Java type or from `isNative()`.

### Official references

- [Java SE 22 — MemorySegment API: ofArray, ofBuffer, scope, asByteBuffer, toArray](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 22 — Arena: confined/shared/automatic and temporal safety](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 22 — ValueLayout, alignment, and byte order](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Java SE 22 — MemorySegment.Scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (final)](https://openjdk.org/jeps/454)
- [Java SE 22 — ByteBuffer API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/ByteBuffer.html)
