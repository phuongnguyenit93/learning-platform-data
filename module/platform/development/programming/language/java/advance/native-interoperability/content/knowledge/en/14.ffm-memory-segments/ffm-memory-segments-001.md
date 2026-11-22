# MemorySegment: Distinguishing Heap, Off-Heap, and File-Mapped Memory Regions

## Objectives

In the Foreign Function & Memory API (FFM), `MemorySegment` represents **a contiguous region of memory with a size, access bounds, and a lifecycle**. The same `MemorySegment` type can wrap three very different situations:

1. **Heap-backed memory**: the data actually resides in the Java heap, such as the memory region of a `byte[]` or `int[]`.
2. **Allocated native/off-heap memory**: a memory region outside the Java heap, typically allocated by an `Arena` which also determines when it is freed.
3. **Memory-mapped file**: a virtual address region of the process mapped to file contents by the operating system; in FFM, this is **a kind of native/off-heap segment**, not a third type completely separate from native memory.

This lesson helps you answer: where the data resides, who owns the memory, what closing the `Arena` affects, when changes are reflected to the file, whether data must be copied, what the safety limits are, and which type to choose for Java data, JNI/FFM, or large file processing.

> **Java Version:** The `java.lang.foreign.MemorySegment`, `Arena`, `ValueLayout`, and `FileChannel.map(..., Arena)` examples in this lesson use the **stable FFM API from JDK 22** (JEP 454). Do not compile these examples directly on JDK 17: in JDK 17, FFM was still an incubator API with different packages and signatures. The examples below use JDK 22+ without `--enable-preview`. If you are still using Java 17, `ByteBuffer`/`MappedByteBuffer` are related APIs, though not completely equivalent to the stable `MemorySegment`.

## 1. Mental Model: Three Ways to Create, Two Kinds of Backing Memory

~~~text
                  Java code
                      |
                MemorySegment
                      |
        +-------------+----------------------+
        |                                    |
        v                                    v
  HEAP SEGMENT                         NATIVE SEGMENT
  backed by Java array                 outside the Java heap
        |                                    |
        |                         +----------+--------------+
        |                         |                         |
        v                         v                         v
  MemorySegment.ofArray(...)  Arena.allocate(...)     FileChannel.map(..., Arena)
  [1, 2, 3, 4]               new native memory         file-mapped address region
  GC manages Java array      Arena manages lifetime    Arena manages mapping
~~~

**Exact classification point:** `MemorySegment` has **heap segments** and **native segments**. A `Mapped segment` is a **special native segment** capable of synchronizing contents with a file. A mapped segment still returns `isNative() == true`, as well as `isMapped() == true`.

If you call a mapped file a "third kind of memory" for ease of learning, understand that it is **a way of creating/using a native segment**, not an independent branch separate from off-heap at the API level.

### Quick Comparison Matrix

| Criterion | Heap-backed segment | Allocated native segment | File-mapped segment |
|---|---|---|---|
| Typical creation | `MemorySegment.ofArray(array)` | `arena.allocate(bytes, alignment)` | `channel.map(mode, offset, size, arena)` |
| Backing storage | Primitive array on the Java heap | Native memory outside the Java heap | Mapping from a file region into the process address space |
| `isNative()` | `false` | `true` | `true` |
| `isMapped()` | `false` | `false` | `true` |
| Who manages the primary lifecycle? | JVM/GC manages the backing array | `Arena` and its corresponding scope | `Arena` manages the mapping; OS manages page/file I/O |
| Does closing `Arena` free it? | `ofArray` does not belong to that arena | Closing confined/shared arena → invalidates and frees | Closing confined/shared arena → invalidates and unmaps |
| Does writing mutate the Java array? | Yes, because it shares the backing array | No, unless explicitly copied | No, unless another shared source is involved |
| Is writing directly tied to a file? | No | No | Yes, depending on `MapMode`; `force()` for read-write mapping |
| Access from another thread | `ofArray` is accessible from multiple threads, but data synchronization is needed | Depends on arena type | Depends on arena and file modification policy |
| Notable risks | GC/object retention, backing array alignment | Leaks, use-after-close, wrong-thread usage, native memory pressure | Mapping lifetime, I/O, file truncation, concurrent external changes |

Do not use this table to infer that heap is always faster or mapped is always fastest. Performance depends on size, access patterns, page faults, cache, GC, allocation cost, number of copies, and the OS.

## 2. MemorySegment Is a Safety-Checked *View*, Not Just an Address

Every `MemorySegment` has these important properties:

- **Byte size:** `segment.byteSize()` is the number of **bytes** the segment represents, not the number of Java elements.
- **Spatial bounds:** accesses at offsets outside the described region are checked. For example, an 8-byte region cannot read a 4-byte `int` at offset 6.
- **Temporal bounds:** a segment has a `scope()` that controls its lifetime. If a native arena closes, the segment and its slices are no longer permitted to be accessed.
- **Thread access:** some arenas, especially `Arena.ofConfined()`, restrict access to the **owning thread**.
- **Read-only flag:** `isReadOnly()`/`asReadOnly()` and file mapping modes can cause write operations to be rejected.
- **Backing category:** `isNative()` and `isMapped()` allow distinguishing heap segments from native ones, and mapped segments from allocated native ones.

Example of using a layout to read:

~~~java
int value = segment.get(ValueLayout.JAVA_INT, 0L);
~~~

This is an **illustrative snippet**, assuming a `segment` variable already exists and the segment has at least four bytes, is properly aligned for `JAVA_INT`, is alive, and is permitted to be accessed by the current thread. The `0L` parameter is the **byte offset**. `ValueLayout` tells the JVM the data type, size, byte order, and alignment requirements.

**Do not confuse the following concepts:**

- `MemorySegment` is a **Java object** on the heap describing a memory region.
- `segment.isNative()` refers to the **backing storage** of the memory region, not that the segment object itself lives off-heap.
- `segment.address()` is not a usable C pointer in all cases. For a heap-backed array, the address is virtualized (for example, an `ofArray` segment has address 0), not a fixed address of the Java object when GC moves it.
- `MemorySegment` does not mean every C pointer is automatically safe. Native regions "borrowed" via raw addresses, aliases, or freed by a third party outside the `Arena` can violate lifetime assumptions.

## 3. Heap Segment: MemorySegment.ofArray

### Creation and Relationship with Java Arrays

~~~java
byte[] bytes = {1, 2, 3, 4};
MemorySegment heap = MemorySegment.ofArray(bytes);

System.out.println(heap.isNative()); // false
System.out.println(heap.isMapped()); // false

heap.set(ValueLayout.JAVA_BYTE, 1L, (byte) 99);
System.out.println(bytes[1]);        // 99
~~~

This is a **Java snippet that can be inserted into a method** on JDK 22+ with imports `java.lang.foreign.MemorySegment` and `java.lang.foreign.ValueLayout`. `heap` and `bytes` reference the **same backing region**; `set` through the segment directly modifies the corresponding element of the Java array. No new copy is made just because you called `ofArray`.

If Java modifies `bytes[0]`, a subsequent `heap.get(ValueLayout.JAVA_BYTE, 0L)` sees the new value (subject to visibility/happens-before rules if multiple threads are involved). If the heap segment has a slice, the slice also accesses the same backing array.

### Does a Heap Segment Need to Be Closed Explicitly?

No. `MemorySegment.ofArray(byte[])` creates a segment with an **automatic scope** that keeps the backing array reachable. There is no separate `Arena.ofConfined()` for you to `close()` in order to free the Java array. GC decides when to reclaim the Java heap object once it is no longer reachable; holding a `MemorySegment` that references the backing array can also keep the array alive.

Conversely, if you create a native segment using `arena.allocate`, closing the arena explicitly makes the segment invalid. **Do not apply the native segment "try-with-resources arena" rule to `ofArray` as if it manages the Java array.**

### Length in Bytes, Not Number of Elements

~~~java
int[] values = {11, 22, 33};
MemorySegment ints = MemorySegment.ofArray(values);
System.out.println(ints.byteSize()); // 12
~~~

A Java `int` is 4 bytes; three elements correspond to 12 bytes of backing memory. To read the second element, use:

~~~java
int second = ints.getAtIndex(ValueLayout.JAVA_INT, 1);
~~~

These are JDK 22+ Java snippets; `getAtIndex` takes an **element index according to the layout**, unlike `get(layout, byteOffset)`. With the `JAVA_INT` layout, index 1 corresponds to byte offset 4. Do not use `get(JAVA_INT, 1L)` intending to read `values[1]`; that is byte offset 1 and may also have wrong alignment.

### Alignment Limits on the Heap

Memory backed by `byte[]` only guarantees alignment corresponding to byte elements. Therefore:

~~~java
MemorySegment bytesSegment = MemorySegment.ofArray(new byte[8]);
// bytesSegment.get(ValueLayout.JAVA_INT, 0L); // May be rejected due to alignment.
int n = bytesSegment.get(ValueLayout.JAVA_INT_UNALIGNED, 0L);
~~~

The snippet above illustrates reading the first four bytes using an **unaligned layout**. This is not a requirement to "fix byte order" with an unaligned layout; if you need a fixed file/network format, you must also choose the appropriate `withOrder(ByteOrder.BIG_ENDIAN)` or `LITTLE_ENDIAN`. `int[]` and `long[]` arrays have different alignment limits; do not take the alignment capability of one backing type and assume it for all heap arrays.

### When to Use a Heap Segment?

- The source data is already in a Java array and needs to be accessed via the `MemorySegment` API.
- You want to integrate algorithms using `get`/`set`/`MemoryLayout` without copying data out of the array.
- The data size is moderate, its lifecycle fits GC, and JNI/FFM code does not require a native address for that input.
- You want to avoid managing explicit native allocation when unnecessary.

**Warning:** A "heap segment" does not automatically make a Java array's address stable to pass to arbitrary C code. The JVM may move the array during GC; FFM has specific rules for passing heap segments to downcalls, and the native linker/ABI cannot always treat a heap segment like a native pointer. When C requires a stable buffer for the duration of a call, consider a native segment and copy the data in a controlled manner.

## 4. Native/Off-Heap Segment: Arena.allocate

### Allocation with an Explicit Lifecycle

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeBytes = arena.allocate(16);
    nativeBytes.set(ValueLayout.JAVA_BYTE, 0L, (byte) 7);
    System.out.println(nativeBytes.get(ValueLayout.JAVA_BYTE, 0L)); // 7
} // arena.close(): native region can no longer be used.
~~~

This is a JDK 22+ Java snippet with imports `java.lang.foreign.Arena`, `MemorySegment`, and `ValueLayout`.

`Arena.ofConfined()` creates an arena that only allows the **owner thread** to access it. `arena.allocate(16)` requests a 16-byte native region described by `MemorySegment`. When `try-with-resources` exits normally or via an exception, `Arena.close()` is called; the regions managed by the arena become invalid. If you retain `nativeBytes` or a slice and access it after close, the API throws an error instead of silently using freed memory.

**Do not misunderstand:** `Arena` manages the lifetime of the native regions it has allocated/mapped into its scope; it is not responsible for freeing arbitrary pointers from `malloc` in other C libraries. Closing an arena does not replace `free`/destructors of a native SDK if you manage pointers outside the arena yourself.

### Which Arena Is Appropriate?

| Arena | Lifetime and Access Rights | Recommendation |
|---|---|---|
| `Arena.ofConfined()` | Single-thread owner; explicit close | Suitable for single-threaded calls/algorithms with a clear `try` scope |
| `Arena.ofShared()` | Accessible from multiple threads; explicit close | When data sharing is needed, still requires access synchronization and close coordination |
| `Arena.ofAuto()` | Lifetime managed automatically by GC, no deterministic cleanup time | When non-deterministic cleanup and unpredictable memory pressure are acceptable |
| `Arena.global()` | Unbounded lifetime; regions allocated from here are never automatically deallocated | Only use for architectures needing process-wide lifetime; beware of leaks |

With `ofShared`, allowing multiple threads to **access** does not automatically make read/write operations **synchronized**. The application must still handle data races, memory ordering, ownership, and preventing close while threads are still using the memory region.

With `ofConfined`, accessing from another thread may throw `WrongThreadException`. Do not pass the segment to a thread executor thinking it is just a thread-safe byte array.

### Alignment and Native Data Layout

Native code often requires the alignment of a C struct or primitive type. Specify it explicitly when allocating:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment oneLong = arena.allocate(
            ValueLayout.JAVA_LONG.byteSize(),
            ValueLayout.JAVA_LONG.byteAlignment());

    oneLong.set(ValueLayout.JAVA_LONG, 0L, 123456789L);
}
~~~

`ValueLayout.JAVA_LONG` describes the 8-byte Java `long` primitive; when interoperating with C `long`, **do not assume they have the same width on every ABI** (C `long` can be 32-bit on Windows x64). When interfacing with native structs, build a `MemoryLayout` matching the actual ABI and use appropriate C layouts if provided by the API/linker.

### Off-Heap Does Not Mean "Free from GC"

The backing data lies outside the Java heap, but the segment object, metadata, and wrappers still reside on the heap. Native memory still consumes process/OS resources and can count toward container limits. Do not allocate a large arena and forget to close it just because "the JVM doesn't see it." A program can still suffer native memory exhaustion even when the Java heap has plenty of space left.

A native segment is not automatically tied to a file; after writing `nativeBytes.set(...)`, closing the arena **frees the backing memory** rather than saving the values to persistent storage.

## 5. Memory-Mapped File: Native Segment Backed by a File

### Creating a Mapping with FileChannel.map(..., Arena)

JDK 22 provides the overload:

~~~java
MemorySegment mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0L,     // file offset, in bytes
        size,   // number of bytes to map
        arena); // scope/lifetime of the mapping
~~~

This is a **code snippet** inside a Java method that has already opened `FileChannel channel`, has a valid `long size`, and a live `Arena arena`. The API maps a region of the file into the process's virtual address space and returns a `MemorySegment`. `mapped.isNative()` is `true`, and `mapped.isMapped()` is also `true`.

**Do not equate file-mapped with "the entire file has been read into RAM."** The operating system manages virtual memory mapping, faulting/loading pages as needed; data may reside in the page cache or on the storage device. `mapped.byteSize()` describes the size of the mapped region in the **address space**, not proof that those bytes are resident in RAM.

### MapMode Modes

| MapMode | Read | Write via segment | Relationship with original file |
|---|---|---|---|
| `READ_ONLY` | Yes | No: read-only segment | Not used to update file contents |
| `READ_WRITE` | Yes | Yes | Changes may be synchronized by the OS with the backing file; `force()` requests writing to storage per spec |
| `PRIVATE` | Yes | Yes | Copy-on-write, private changes are not propagated back to the original file per contract |

These modes are not database transaction isolation levels. `READ_WRITE` does not lock the file from other programs, does not create atomic transactions, and does not exclude external writers.

### `force()`, `load()`, `unload()`, and `isLoaded()`

These APIs apply to **mapped segments**:

- `mapped.force()` requests writing changes belonging to a read-write mapping to storage. For local storage, the specification provides stronger guarantees; for remote devices, guarantees may differ. `force()` may throw `UncheckedIOException` if flushing fails.
- `mapped.load()` attempts to load pages into memory. This is **best effort**, not a guarantee to lock data in RAM.
- `mapped.isLoaded()` gives a hint about residency, not proof of durability or a snapshot.
- `mapped.unload()` attempts to evict pages from resident memory; it does not destroy the mapping and does not replace `Arena.close()`.
- For non-mapped segments, methods dedicated to mapped segments may throw `UnsupportedOperationException`; check `isMapped()` before using them.

`force()` also **does not replace** closing the mapping/arena. A mapped region can remain active after `force()`; when the program no longer uses it, close the arena that created the mapping to end its lifetime.

### FileChannel.close() vs. Arena.close()

In the example, `FileChannel` manages the channel descriptor, while `Arena` manages the lifetime of the segment/mapping. Closing the file channel **must not be used instead of closing the arena** to declare the mapped segment invalid. Closing the arena is the explicit operation that ends the scope of the mapped segment managed by that arena.

More importantly, if the **file is truncated or modified** by another thread/process while still mapped, the mapped region may change or become inaccessible. The specification notes that access errors may not resemble normal Java bounds checks. Do not treat `MemorySegment` as an absolute protection layer against external-to-JVM modifications to the backing file.

### When to Use a Mapped Segment?

- Reading/writing large files with random access and wanting to avoid some intermediate copies through standard I/O.
- Needing to share contents via the OS memory-mapping mechanism between processes in a controlled manner.
- Processing structured data from a file where layout/byte order can be accurately described.
- Accepting management of mapping lifetime, I/O errors, page faults, and file/OS synchronization.

Do not use mmap just because a file is "big": for sequential streams, `FileChannel.read`, `BufferedInputStream`, or bulk I/O can be simpler and more efficient; always benchmark real workloads.

## 6. Complete JDK 22+ Example: Seeing All Three Cases Together

The Java program below **does not require a native C library**: it uses FFM to manipulate heap, allocated native memory, and a mapped file. It creates a temporary file, writes a value to the mapping, calls `force()`, and then reads the file contents back after closing the arena. It also attempts to access the allocated native segment after its lifetime has ended.

### 6.1. File: `MemoryKindsDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

import static java.nio.file.StandardOpenOption.READ;
import static java.nio.file.StandardOpenOption.WRITE;

public final class MemoryKindsDemo {

    public static void main(String[] args) throws Exception {
        // 1. Heap: segment and byte[] share the same backing array.
        byte[] array = {1, 2, 3, 4};
        MemorySegment heap = MemorySegment.ofArray(array);
        heap.set(ValueLayout.JAVA_BYTE, 1L, (byte) 9);

        System.out.println("heap: native=" + heap.isNative()
                + ", mapped=" + heap.isMapped()
                + ", array[1]=" + array[1]);

        // 2. Temporary file with deterministic content, not relying on an existing file.
        Path file = Files.createTempFile("ffm-memory-kinds-", ".bin");
        try {
            Files.write(file, new byte[] {10, 20, 30, 40});
            MemorySegment oldNative;

            try (Arena arena = Arena.ofConfined()) {

                // 3. Off-heap allocation, no file backing.
                MemorySegment nativeBytes = arena.allocate(4);
                oldNative = nativeBytes;
                nativeBytes.set(ValueLayout.JAVA_BYTE, 0L, (byte) 77);

                System.out.println("native: native=" + nativeBytes.isNative()
                        + ", mapped=" + nativeBytes.isMapped()
                        + ", byte[0]="
                        + nativeBytes.get(ValueLayout.JAVA_BYTE, 0L));

                // 4. File-backed mapping with the same arena.
                try (FileChannel channel = FileChannel.open(file, READ, WRITE)) {
                    MemorySegment mapped = channel.map(
                            FileChannel.MapMode.READ_WRITE,
                            0L,
                            4L,
                            arena);

                    mapped.set(ValueLayout.JAVA_BYTE, 1L, (byte) 99);
                    mapped.force();

                    System.out.println("mapped: native=" + mapped.isNative()
                            + ", mapped=" + mapped.isMapped()
                            + ", byte[1]="
                            + mapped.get(ValueLayout.JAVA_BYTE, 1L));
                }

            } // Closing arena: native allocation and mapping become invalid.

            System.out.println(
                    "file=" + Arrays.toString(Files.readAllBytes(file)));

            try {
                oldNative.get(ValueLayout.JAVA_BYTE, 0L);
                System.out.println("unexpected access");
            } catch (IllegalStateException expected) {
                System.out.println("afterClose=IllegalStateException");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

All bytes in the example are in the range 0–127 so that `Arrays.toString(byte[])` prints positive values for easy comparison; for bytes above 127, Java `byte` is signed and is printed as a negative number.

### 6.2. Compile/Run Commands

Verify you are using JDK 22 or newer:

~~~bash
java -version
javac -version
javac MemoryKindsDemo.java
java MemoryKindsDemo
~~~

`--enable-preview` is not needed for stable FFM on JDK 22. If `javac` reports that the `java.lang.foreign` package does not exist, you are likely using an older JDK or a mismatched toolchain; verify that `java` and `javac` actually point to the right JDK.

### 6.3. Expected Stdout

On a JDK 22+ that supports `FileChannel.map(..., Arena)` and where temporary files work normally:

~~~text
heap: native=false, mapped=false, array[1]=9
native: native=true, mapped=false, byte[0]=77
mapped: native=true, mapped=true, byte[1]=99
file=[10, 99, 30, 40]
afterClose=IllegalStateException
~~~

**Why does the output look like this?**

1. `MemorySegment.ofArray(array)` does not create a copy; writing at offset 1 of the heap segment modifies `array[1]` from 2 to 9.
2. `arena.allocate(4)` returns a native segment. `nativeBytes.set` writes to the off-heap allocation, affecting neither the Java array nor the file.
3. `FileChannel.map` creates a mapped segment with `isNative()==true` **and** `isMapped()==true`. The command writes byte 99 at offset 1 and then calls `force()`.
4. Reading the file back yields `[10, 99, 30, 40]`: the file remains intact at positions 0, 2, and 3; only position 1 was changed. The randomly generated temporary filename **does not appear** in stdout, so the output remains deterministic.
5. After exiting `try (Arena ...)`, `oldNative` is still a Java reference to the **segment object**, but the scope has been closed; the `get` call throws `IllegalStateException`. Holding a Java reference **does not keep native backing memory alive** after an explicit close.

If the system does not support mapping for this overload, or cannot create/write temporary files, the example may throw `IOException`/`UnsupportedOperationException`. In that case, do not assume the output above occurs on every filesystem or provider; the lines above are the result in a supported environment per the JDK contract.

### 6.4. An Important Detail: Closing the Channel Before the Arena

In the sample code, the closing order is:

~~~text
Create file
  |
  +-- Arena.ofConfined()
        |
        +-- allocate native
        |
        +-- FileChannel.open(...)
              |
              +-- map(..., arena)
              +-- mapped.set(...), mapped.force()
              |
              +-- channel.close()
        |
        +-- arena.close() -> invalidates native and mapped
  |
  +-- Files.readAllBytes(file)
  +-- Files.deleteIfExists(file)
~~~

Closing `FileChannel` ends channel I/O, while `Arena` controls the lifetime of the mapped memory segment. `force` is called before both close to explicitly express the persist request. For temporary files on Windows, ensure the mapping has been released before deleting the file to avoid file-in-use errors.

## 7. Slicing, Copying, and Aliasing

A `MemorySegment` can be sliced:

~~~java
MemorySegment whole = MemorySegment.ofArray(new byte[] {1, 2, 3, 4});
MemorySegment middle = whole.asSlice(1L, 2L);

middle.set(ValueLayout.JAVA_BYTE, 0L, (byte) 88);

System.out.println(whole.get(ValueLayout.JAVA_BYTE, 1L)); // 88
~~~

The Java snippet above can run in a JDK 22+ method. `asSlice` creates a **view**, not a copy; `middle[0]` is the same byte as `whole[1]`. The slice has smaller bounds but still uses the same scope/lifetime of the backing memory. This holds true for heap, native allocation, and mapped segments.

Conversely, `MemorySegment.copy(src, srcOffset, dst, dstOffset, byteCount)` **copies data** between two segments, for the specified number of bytes. Do not assume copy is zero-copy or an alias; the two data-receiving regions can be separate.

| Operation | Creates a data copy? | Lifetime relationship |
|---|---|---|
| `MemorySegment.ofArray(existingArray)` | Does not copy backing array | Scope keeps backing array reachable |
| `segment.asSlice(offset, size)` | Does not copy | Shares scope and backing storage |
| `MemorySegment.copy(...)` | Yes, copies bytes by region | Each source/destination keeps its own scope |
| `Arena.allocate(bytes)` | Creates a new native allocation | Managed by arena |
| `FileChannel.map(...)` | Creates mapping, does not force reading whole file into heap | Mapping managed by arena |
| `Files.readAllBytes(path)` | Creates a Java `byte[]` containing file data | Java heap/GC manages the array |

A file-mapped segment is a memory region shared with the backing file (per MapMode), but it is not necessarily a physical region holding the entire file in RAM. The mapping technique often helps **avoid copying data into a Java byte[]** for certain workloads; it does not mean all data or page faults are "zero cost."

## 8. Bounds, Alignment, Byte Order, and Read-Only

### 8.1. Byte Offset Must Be Within Bounds

With an eight-byte segment:

~~~java
MemorySegment eight = MemorySegment.ofArray(new byte[8]);

// Read four bytes at offset 0: use unaligned layout suitable for byte[].
int first = eight.get(ValueLayout.JAVA_INT_UNALIGNED, 0L);

// eight.get(ValueLayout.JAVA_INT_UNALIGNED, 6L);
// Will be rejected: requires four bytes, but only two bytes remain.
~~~

At offset 6, accessing four bytes exceeds `byteSize()=8`; `MemorySegment` checks bounds according to the layout's size. A slice's bounds can be smaller than the original segment, so an offset valid on `whole` may still be invalid on `slice`.

### 8.2. Byte Order Differs from File Endianness

`ValueLayout` carries byte order. When processing a file/wire format that specifies **big-endian**, declare it explicitly:

~~~java
import java.nio.ByteOrder;

// Place inside a method that already has an appropriate segment variable with enough bytes.
var beInt = ValueLayout.JAVA_INT_UNALIGNED
        .withOrder(ByteOrder.BIG_ENDIAN);
int n = segment.get(beInt, 0L);
~~~

This is a **code snippet**, not a standalone program. Use `JAVA_INT_UNALIGNED` when the region has an alignment requirement of 1; `withOrder` adjusts the byte order without changing the byte size of `int`. Do not rely solely on CPU endianness when the file format specifies one explicitly.

### 8.3. Read-Only Actually Blocks Writes

~~~java
MemorySegment readonly = MemorySegment.ofArray(new byte[4])
        .asReadOnly();

// readonly.set(ValueLayout.JAVA_BYTE, 0L, (byte) 1);
// Invalid: readonly segment rejects writes.
~~~

This snippet is illustrative. Calling `asReadOnly` creates a **read-only view** and does not mean the backing array is frozen: if the caller still holds the original `byte[]` or another mutable segment, that caller can still write data. To make data immutable at the application layer, you must control those aliases and other writers.

Mapped `READ_ONLY` cannot be written to either. Mapped `PRIVATE` can be written to in its copy-on-write view, but **must not be expected to persist** to the backing file via `force()`.

## 9. Lifetime, Thread Confinement, and Errors After Close

### 9.1. Slice Lifetime Inherits from the Arena

~~~java
MemorySegment alias;
try (Arena arena = Arena.ofConfined()) {
    MemorySegment root = arena.allocate(8);
    alias = root.asSlice(2, 4);
} // Scopes of both root and alias become invalid.

// alias.get(ValueLayout.JAVA_BYTE, 0);
// Throws IllegalStateException because the arena is closed.
~~~

This is a code snippet inside a method. `MemorySegment` checks *temporal bounds* on every access. A slice does not extend the lifetime of a native allocation. You must keep the arena alive for the entire duration the segment/slice is needed.

### 9.2. A Shared Arena Does Not Handle Races Automatically

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment shared = arena.allocate(1024);
    // Multiple threads can access shared, but the application
    // must control data synchronization and close relative to in-flight accesses.
}
~~~

`ofShared` solves cross-thread access permission at the scope level; it **does not** make every `get`/`set` on the same byte a transaction or automatically guarantee memory ordering. If multiple threads modify the same state, use a synchronization protocol or atomic access via an appropriate VarHandle layout.

Even though the API prevents some close races, you must still determine which thread owns the arena and when work completes. Do not pass a segment to an asynchronous task and then close the arena immediately on the calling thread before the task finishes.

### 9.3. Wrong Thread and Wrong Lifetime Are Two Different Errors

- `WrongThreadException`: accessing a segment from a thread not permitted by the scope/arena, such as an `ofConfined` segment from another thread.
- `IllegalStateException`: accessing a region whose scope has been closed, even though the Java object still exists.
- `IndexOutOfBoundsException`: offset/size is not within bounds.
- `IllegalArgumentException`: may occur when violating alignment or attempting to write to a read-only segment, depending on the access API.
- For mapped files, off-heap I/O errors can also surface via `UncheckedIOException` or when the backing file is modified/truncated.

Java exceptions here are how FFM checks accesses within the scope that **the JVM can control**. One should not conclude that every external C pointer or file map is immune to memory corruption if other native code frees the backing storage itself.

## 10. Relationship with JNI, Native Libraries, and ByteBuffer

### 10.1. JNI Does Not Automatically Treat a Java Heap Segment as an Arbitrary C Pointer

A C function taking `void*` needs a valid native address and a clear lifetime. `MemorySegment.ofArray` does not guarantee a stable Java array address to be stored by a native library. When passing data via an FFM downcall/JNI to a function with a native pointer contract, choose the right segment kind, layout, and lifetime; typically a **native segment** for buffers requiring an off-heap address.

Conceptual workflow example:

~~~text
Java byte[] source data
      |
      +-- MemorySegment.ofArray(array) (no copy)
      |
      +-- MemorySegment.copy(...) or controlled set(...)
                  |
                  v
            Native MemorySegment (arena)
                  |
                  v
         Foreign downcall / JNI bridge
                  |
                  v
         native code uses buffer while arena is alive
~~~

This is an **illustrative** model, not a claim that every native function requires a copy. The optimal way to pass data depends on the ABI, FFM API, data type, restrictions, and how the native code uses the buffer.

In particular: do not call `segment.address()` on a heap segment and cast it into the array's address in C. With `ofArray`, the virtualized address in `MemorySegment` is not a physical pointer for native code to retain.

### 10.2. ByteBuffer: Heap, Direct, and Mapped

Concepts that existed before FFM:

- `ByteBuffer.allocate(n)`: buffer with backing storage on the Java heap.
- `ByteBuffer.allocateDirect(n)`: direct buffer, typically using native/off-heap storage.
- `FileChannel.map(mode, pos, len)`: returns `MappedByteBuffer`, typically a native mapping managed by the OS.

FFM can bridge with buffers using `MemorySegment.ofBuffer(buffer)` or obtain a `ByteBuffer` view via `segment.asByteBuffer()` under API-permitted conditions. **Do not** infer that every ByteBuffer wrapper has the same lifetime as an Arena: a self-allocated direct buffer, a legacy mapped ByteBuffer, and an Arena-managed MemorySegment have different cleanup contracts.

A useful limit: `MemorySegment.asByteBuffer()` requires the segment's size to be no larger than `Integer.MAX_VALUE` and its backing to be compatible; a `MemorySegment` can describe a region larger than what a ByteBuffer can represent. For heap segments backed by arrays other than `byte[]`, `asByteBuffer` may not be supported.

### 10.3. What About Java 17?

Java 17 **does not have** the stable `java.lang.foreign.MemorySegment` API. You can learn the concepts using `ByteBuffer` and `MappedByteBuffer`, or use the incubator API according to that version's documentation, but do not copy JDK 22 examples verbatim and run them with `javac 17`.

A standalone Java 17 example of **heap buffer vs direct buffer**:

~~~java
import java.nio.ByteBuffer;

public class BufferKinds17 {
    public static void main(String[] args) {
        ByteBuffer heap = ByteBuffer.allocate(4);
        ByteBuffer direct = ByteBuffer.allocateDirect(4);

        heap.put(0, (byte) 11);
        direct.put(0, (byte) 22);

        System.out.println("heapDirect=" + heap.isDirect());
        System.out.println("nativeDirect=" + direct.isDirect());
        System.out.println("heap0=" + heap.get(0));
        System.out.println("native0=" + direct.get(0));
    }
}
~~~

Run on JDK 17:

~~~bash
javac BufferKinds17.java
java BufferKinds17
~~~

Stdout:

~~~text
heapDirect=false
nativeDirect=true
heap0=11
native0=22
~~~

This snippet shows the difference in the legacy ByteBuffer API, and **does not** prove that a direct buffer is identical to `Arena.allocate`. Legacy direct/mapped buffer resources have lifetimes tied to their own management mechanisms; therefore, the main lesson uses JDK 22 stable FFM to explain `MemorySegment` and `Arena`.

## 11. Costs, Limits, and Practical Choices

### 11.1. When to Choose Heap?

Choose `MemorySegment.ofArray` when the data naturally already resides in a Java array or the Java heap can manage that size well. Avoid allocating off-heap and copying just because "native is always faster": extra copying, arena bookkeeping, and native memory pressure can make the solution more complex without improving performance.

### 11.2. When to Choose Native Allocation?

Choose `Arena.allocate` when:

- You need a native buffer to exchange data with a compatible C library/ABI.
- You need to control alignment and lifetime via `Arena`.
- You want to manage memory pressure outside the Java heap and accept explicit closing.
- You have multiple regions with the same lifetime that can be grouped into one arena.

Do not allocate from `Arena.global()` for every short-lived request; regions from the global arena are not deallocated during the process lifetime and can leak. For requests with clear boundaries, `Arena.ofConfined()` + `try-with-resources` is usually easiest to control.

### 11.3. When to Choose a Mapped File?

Choose mapping when the data is a file, the workload suits random access or OS-level sharing, and you can manage external file updates, sizes, I/O failures, and flushing. Do not rely on mapping to guarantee durable transactions like a database; `force()` does not solve business synchronization between multiple writers.

### 11.4. What Benchmarks Must Measure

If comparing performance, measure separately:

- **Create/allocate/map** and **close/unmap** time.
- First-access cost (page faults) and repeated access (warm cache).
- Throughput for sequential reads, random reads, small writes, and bulk writes.
- Number of data copies between Java arrays/native buffers/files.
- Memory footprint: Java heap, native allocations, mapped virtual size, resident pages, and page cache.
- Impact of `force()` on latency and actual storage (local/remote).
- GC rate and total end-to-end processing time, not just a microbenchmark of a single `get` call.

A mapped segment with a very large `byteSize()` does not necessarily equate to using the same number of bytes of resident RAM. Conversely, off-heap memory consumes system resources even though it is not counted as Java heap objects.

## 12. Common Mistakes

| Mistake | Why It Is Wrong | Correct Approach |
|---|---|---|
| Treating mapped files as a "non-off-heap" kind | `isNative()==true` for mapped segments | Understand mapped as a subtype of native segment |
| `MemorySegment.ofArray` copies the Java array | It wraps the existing backing array | Recognize aliasing; use `MemorySegment.copy` if a copy is needed |
| Computing offset by element when using `get(layout, offset)` | The offset of `get/set` is in **bytes** | Use `getAtIndex` or multiply by the exact layout size |
| Using `JAVA_INT` on a segment from `byte[]` without considering alignment | Heap segments have alignment limits based on the backing array | Use an unaligned layout or an appropriate backing type |
| Closing the arena and continuing to use the segment/slice | The scope has become invalid | Keep the arena alive throughout the operations; do not keep raw pointers after close |
| Assuming mapped data is always already in RAM | The OS manages page residency lazily | Measure page faults; `isLoaded` is only a hint |
| Expecting `arena.close()` to write allocated native data to a file | Native allocations have no file backing | Perform explicit file I/O or mapped `READ_WRITE` + `force()` |
| Expecting `mapped.force()` to be a database transaction | Flush does not automatically control concurrency/atomicity | Use an application-level transaction/locking protocol |
| Assuming mapped `PRIVATE` writes back to the file | Private mapping uses copy-on-write | Use `READ_WRITE` and a flush policy when persistence is needed |
| Closing the channel and thinking it invalidated the mapped segment | Segment lifetime is tied to the arena | Close the corresponding arena |
| Modifying/truncating the file while still mapped | The OS may invalidate the mapping or cause unexpected changes | Coordinate file lifecycle and external writers |
| Using `Arena.ofConfined` and then passing the segment to a worker thread | Violates thread confinement | Use an appropriate arena and synchronization protocol |
| Using `Arena.ofAuto` for resources that need immediate release | GC timing is non-deterministic | Use confined/shared + explicit close |
| Assuming `MemorySegment.address()` on heap is a C pointer | Heap backing has a virtualized address and GC can move it | Do not cast heap addresses yourself; follow the FFM ABI |
| Assuming mapped `byteSize()` is the amount of resident RAM | Mapped size describes the address region | Distinguish virtual mapping, resident pages, and file size |
| Expecting `java.lang.foreign` to run directly on Java 17 | Stable API since 22 | Use JDK 22+ or separate corresponding code for JDK 17 |

## 13. Scenarios and Exercises

### Scenario A — Reading a Very Large File

An application analyzes a file of tens of GB by offset. If using `Files.readAllBytes`, you need a huge Java array (even exceeding array limits on many JVMs). A mapped `MemorySegment` allows mapping a file region and accessing by `long` offset, but you must check memory address space, file size, lifetime, and page fault behavior. Not every file is suitable for mmap: for linear streams, `FileChannel`/buffered I/O may be a better choice.

**Question:** does mapping a 10 GB file mean immediately allocating 10 GB of Java heap? **No.** A mapped segment describes a file region in the virtual address space and does not create a Java `byte[10GB]`.

### Scenario B — Passing a C Struct

A native C library takes a pointer to a struct with specific field alignment. `MemorySegment.ofArray(byte[])` may not satisfy native address, alignment, or expected ABI requirements. Use `Arena.allocate(layout)` with a `MemoryLayout` matching the ABI and manage the lifetime until the C function completes. Do not assume C `long` equals Java `long` on all platforms.

**Question:** does the JVM GC automatically deallocate a closed `Arena.ofConfined`? **No need.** Closing the arena is a deterministic action that ends the lifetime and frees the backing region managed by the arena.

### Scenario C — Updating a Mapped File

A process maps a file `READ_WRITE`, modifies bytes, and calls `mapped.force()`. Afterward, another process can still modify the same file; `force()` does not forbid that. File locking or an application protocol is needed if serialized writes are required.

**Question:** does using `MapMode.PRIVATE` write to the original file? **No, per the copy-on-write contract.** Changes in a private mapping are not used as a way to persist to the original file.

### Exercise 1 — Predict Aliasing

~~~java
byte[] a = {4, 5, 6};
MemorySegment s = MemorySegment.ofArray(a);
s.set(ValueLayout.JAVA_BYTE, 0L, (byte) 11);
System.out.println(a[0]);
~~~

**Answer:** `11`, because `s` directly accesses the backing array `a`.

### Exercise 2 — Identify Mapped

With `FileChannel.map(READ_WRITE, 0, 100, arena)`, what do `isNative()` and `isMapped()` return? **Both `true`.** With `arena.allocate(100)`, `isNative()==true` and `isMapped()==false`.

### Exercise 3 — Arena Scope

A `MemorySegment` obtained from `Arena.ofConfined` is kept in a field after `arena.close()`. Is a subsequent `get` call valid? **No**, it will undergo temporal bounds checking and throw `IllegalStateException`, even though the segment's Java object is still referenced.

### Exercise 4 — Thread

Thread T1 creates a confined arena and allocates a segment. T2 calls `segment.get(...)` while the arena is still alive. Is this allowed? **No**, due to thread confinement; expect `WrongThreadException`. If sharing is desired, you need the appropriate arena choice, synchronization, and coordinated lifecycle.

### Exercise 5 — force

`force()` is called on a read-only mapping. Is this an operation that writes new data to the file? **No.** On read-only/private mappings, `force` may have no effect of writing to the file. With `READ_WRITE` on local storage, `force()` is the mechanism to request flushing changes per the API contract.

### Exercise 6 — Choose a Solution

You need an API to exchange a 4 KiB buffer with a native C function, process it, and release the resource immediately. **Suggestion:** `try (Arena arena = Arena.ofConfined())` and allocate with the right layout/alignment; do not use the global arena. If the source data is on the Java heap, copy/transfer as required by the API so the native buffer's lifetime is controlled.

## 14. Review Checklist Before Using MemorySegment

1. **JDK:** are you using the stable `java.lang.foreign` of JDK 22+ or confusing it with an older JDK's incubator API?
2. **Backing source:** from a Java array, native allocation, or file mapping?
3. **Kind:** do you understand `isNative` and `isMapped` (mapped ⇒ native)?
4. **Byte size and offset:** are all `get`/`set` calls within `byteSize()` and with the right layout alignment?
5. **Endianness and layout:** do they match the file format/native ABI rather than accidentally depending on the CPU?
6. **Aliasing:** `ofArray`/`asSlice` are views of the same backing; if a separate copy is needed, has it been done properly?
7. **Ownership:** who holds the arena, who closes it, and when? Are there any accesses after the scope is closed?
8. **Thread:** is confined/shared/auto/global appropriate for the usage? Are there concurrent read/write/close races?
9. **Native calls:** if passed to C, does the pointer match the ABI and stay alive for the entire duration of use?
10. **Mapped file:** how are file mapping mode, file size, external truncation/writers, flush, exceptions, and close managed?
11. **Performance:** have the number of copies, page faults, RSS/native pressure, and file size been measured on real workloads?
12. **Cleanup:** does `try-with-resources` close the channel/arena in the right order? Are temporary files only deleted after the mapping ends?

## Official References

- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): heap/native, `isNative`/`isMapped`, `get`/`set`, alignment, slicing, mapped `force`.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): `ofConfined`, `ofShared`, `ofAuto`, `global`, scope, and lifetime.
- [Java SE 22 — FileChannel](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html): `map(MapMode, long, long, Arena)` and file/mapping notes.
- [Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): size, byte order, and alignment.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM becomes a standard API in JDK 22.

## Takeaways

**Distinguish the backing storage before choosing an API:**

- **Heap segment:** `MemorySegment.ofArray(...)` wraps a Java array, shares data with the array, and lets GC manage the backing array.
- **Allocated native segment:** `Arena.allocate(...)` requests a new off-heap memory region, not automatically linked to a file; its lifetime depends on the arena.
- **Mapped file segment:** `FileChannel.map(..., arena)` creates a **special native segment** attached to a file, with `isMapped()==true`; `MapMode` and `force()` control how the file is updated, while the arena controls the mapping's lifecycle.

`MemorySegment` provides **bounds**, **scope lifetime**, and **thread access** checks, but it does not replace ownership design, synchronization, or mechanisms to protect against files or other native code modifying the backing storage. Choose the right backing source, keep the arena alive long enough, check layouts, and close resources explicitly.
