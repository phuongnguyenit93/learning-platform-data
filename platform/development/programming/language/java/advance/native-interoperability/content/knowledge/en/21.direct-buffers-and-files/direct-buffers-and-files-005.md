# Mapping a File to a MemorySegment with FileChannel and Arena in Java FFM

A **memory-mapped file** is a technique where the operating system maps a byte region of a file into the process's address space. Instead of calling `FileChannel.read(...)` and copying chunks into a `ByteBuffer`, the program can **access the file's bytes through mapped memory**; the operating system coordinates memory pages, the page cache, page faults, and writing data back to storage. Since **JDK 22**, Java provides the overload `FileChannel.map(FileChannel.MapMode mode, long offset, long size, Arena arena)` which returns a **`java.lang.foreign.MemorySegment`**, combining the benefits of mapping with **spatial bounds and lifetime managed by `Arena`**.

A key point to understand correctly: **`FileChannel` and `Arena` have different lifecycles**. Closing `FileChannel` after a successful mapping **does not automatically invalidate the mapped segment**; whereas closing a closeable `Arena` that owns the mapping allows the JVM to reclaim/unmap the mapped region and subsequent accesses are rejected. `MemorySegment.force()` has the semantics of synchronizing changes for a **`READ_WRITE`** mapping, but **does not turn file I/O into an atomic transaction**. If the file is truncated or modified by another process while mapped, even though the segment still has the right size/scope, the memory region may become inaccessible.

This lesson belongs to the **Buffers and Files** group in the Java Advance — native-interoperability module. We clarify the API, the three `MapMode`s, byte-based offset/size, mapped segment methods, the role of `Arena`, error handling, and safety with multiple threads/processes. There is a **complete Java 22+ program** that creates a temporary file, maps it `READ_WRITE`, modifies data after closing the channel, calls `force()`, tests `READ_ONLY`/`PRIVATE`, checks the error after `arena.close()`, along with `javac`/`java` commands and deterministic stdout.

> **Version scope:** `java.lang.foreign` became a standard API in **Java 22** (JEP 454). Java 17 has the FFM incubator, and Java 21 still uses FFM preview which differs from the final version. Do not compile this example as-is with Java 17/21. Using only `FileChannel.map(..., Arena)` and `MemorySegment.get/set/force` **does not require `--enable-native-access`** like restricted operations used to call C functions via `Linker`. If you add `Linker.downcallHandle`, `SymbolLookup.libraryLookup`, or `reinterpret`, you must check/grant the corresponding native access permission.

## 1. The nature of memory mapping: bytes, not Java objects

In traditional I/O:

~~~text
File on storage -> kernel/page cache -> read(...) -> ByteBuffer/byte[]
                                                  -> Java processing
~~~

When using mapping:

~~~text
File on storage
      |
      | OS maps region [offset, offset+size)
      v
Virtual memory in process <---- page cache / page faults
      |
      | FileChannel.map(mode, offset, size, arena)
      v
MemorySegment: virtual address + byteSize + scope + access rules
      |
      +-- get(ValueLayout.JAVA_BYTE, byteOffset)
      +-- set(ValueLayout.JAVA_BYTE, byteOffset, value)
      +-- asSlice(...) / asByteBuffer()
      +-- force() / load() / isLoaded() / unload()
      |
      v
Arena.close() -> invalidates mapped segment; unmaps memory region
~~~

`FileChannel.map(...)` does not turn file data into Java `String`, `int[]`, `struct` objects, or an auto-decoding collection. A file only has a **sequence of bytes**. How you group and interpret bytes is the application's responsibility:

- Binary record with a 4-byte integer: use `ValueLayout.JAVA_INT` or a layout with a `ByteOrder` matching the **file format**, do not assume native order is correct by default.
- UTF-8 text: read as a byte sequence and decode using a charset/decoder, do not treat each byte as a Java `char`.
- Header containing magic/version/length: validate before reading the data section at offsets with overflow checks.
- File containing records with padding/alignment: you need to describe the field layout accurately; offsets in the file might not be aligned to `JAVA_INT`, in which case use an unaligned layout **only if the format actually allows it**.

Mapping is often beneficial for random, repeated access on a large file; it does not mean the entire file is already in RAM. Page faults can trigger I/O at any time, and mapped bytes can also be cached or evicted depending on OS policy.

## 2. Key JDK 22 API: `FileChannel.map(..., Arena)`

Signature:

~~~java
// Illustrative API signature, not a standalone Java program:
MemorySegment FileChannel.map(
        FileChannel.MapMode mode, long offset, long size, Arena arena)
        throws IOException;
~~~

Basic usage:

~~~java
// Illustrative Java snippet: file exists, read channel is valid,
// segment/arena are only used while the scope is alive.
try (Arena arena = Arena.ofConfined();
     FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    long size = channel.size();
    MemorySegment mapped = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, size, arena);
    // Read bytes in [0, size), do not write to a READ_ONLY mapping.
}
~~~

The four arguments each have a specific meaning:

| Argument | Unit/contract | What to check |
| --- | --- | --- |
| `mode` | `READ_ONLY`, `READ_WRITE`, `PRIVATE` | Must be compatible with channel open permissions |
| `offset` | `long` byte offset in the **file** | Non-negative, calculation does not overflow; not automatically a record index |
| `size` | `long` number of **mapped bytes** | Non-negative; `offset + size` does not overflow; file region is proven valid |
| `arena` | Owner of the mapping scope | Still alive, valid thread access; released when a closeable arena is closed |

Returns:

- A **mapped native `MemorySegment`** with `mapped.isMapped()==true` and `mapped.byteSize()==size`.
- The segment has bounds: `get/set` take byte offsets relative to the **start of the mapped region**, not relative to the start of the entire file.
- When `mode==READ_ONLY`, `mapped.isReadOnly()==true` and Java `set` calls are rejected.
- The mapping's lifetime is tied to the arena, not directly to calling `FileChannel.close()` after mapping.
- This `FileChannel.map` differs from the **three-parameter** overload `map(MapMode,long,long)` which returns a **`MappedByteBuffer`**.

Do not confuse `offset` with the channel's relative position. `map` takes an **absolute position** in the file; you should not assume it advances `channel.position()` like a `read(ByteBuffer)` call at the current position.

### 2.1. Mapping byte origin and segment byte origin

Suppose a file is 1,024 bytes long. You call:

~~~java
// Illustrative snippet: file>=1024 bytes; arena is alive.
MemorySegment window = channel.map(
        FileChannel.MapMode.READ_ONLY, 100, 40, arena);
~~~

Then:

~~~text
File:     byte 0 ................... byte 100 ........ byte 139 ... byte 1023
                                       |                 |
                                       +--- 40 bytes ---+
                                               |
Segment: byte 0 ............................. byte 39
~~~

`window.get(JAVA_BYTE, 0)` reads **file byte 100**; `window.get(JAVA_BYTE,39)` reads **file byte 139**. `window.get(JAVA_BYTE,40)` is out of bounds of the segment and must not be read. If you want to map the 5th record, you must calculate the **byte offset** from the format: `recordIndex * recordStride` with an overflow check before passing it to `map`.

With a 0-byte mapping, you get an empty view; do not attempt to read element 0. For portable code, empty files are usually handled with a separate branch rather than asking the OS to map 0 bytes and assuming that mapping behavior is identical across all providers.

### 2.2. Differences from `MappedByteBuffer`

| Feature | Classic `MappedByteBuffer` | JDK 22+ `MemorySegment` mapping |
| --- | --- | --- |
| Created via | `channel.map(mode,position,size)` | `channel.map(mode,offset,size,arena)` |
| Return type | `MappedByteBuffer` | `MemorySegment` |
| Data range per object | Buffer capacity constrained by `int` | Mapping `size` uses `long`; still subject to OS/VM resources |
| Mapping cleanup | Typically relies on GC/Cleaner or runtime mechanism | **`Arena.close()`** with a closeable arena |
| Access methods | `buffer.get/put(...)` and buffer position/limit | `segment.get/set(ValueLayout, byteOffset)` |
| Lifetime check | Reachable buffer does not guarantee deterministic close | `Arena` scope checks access lifetime |
| Slicing | `slice/duplicate` per ByteBuffer | `asSlice(...)` using long byte offsets |
| Converting to ByteBuffer | Not needed | `segment.asByteBuffer()` with corresponding ByteBuffer limits |

**`MemorySegment` can represent a region larger than a `ByteBuffer`'s index limit**, but that does not mean a huge file can be mapped successfully on every OS or every JVM. Virtual address space, file system, mapped region, and OS quota limits still apply. If converting a very large mapped segment into a `ByteBuffer`, consider the `int` capacity limit and split it into chunks.

## 3. Three `FileChannel.MapMode`s and their effect on the file

| MapMode | Required permissions on FileChannel | Can Java write through the segment? | Are writes reflected in the file? |
| --- | --- | --- | --- |
| **`READ_ONLY`** | Opened with `READ` | **No** | No modifications from this mapping |
| **`READ_WRITE`** | Opened with **`READ` and `WRITE`** | Yes | Changes are eventually propagated to the file; call `mapped.force()` when a flush commitment is needed |
| **`PRIVATE`** | Opened with **`READ` and `WRITE`** | Yes (private copy-on-write copy) | Changes in a private mapping are **not** propagated to the file |

### 3.1. `READ_ONLY`

~~~java
// Illustrative Java snippet:
try (Arena arena = Arena.ofConfined();
     FileChannel channel = FileChannel.open(file, StandardOpenOption.READ)) {
    MemorySegment segment = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, channel.size(), arena);
    System.out.println(segment.isReadOnly()); // true
    // segment.set(ValueLayout.JAVA_BYTE, 0, (byte)7) is rejected.
}
~~~

With `MemorySegment.set(...)` on a read-only segment, the API may throw `IllegalArgumentException`. Do not interpret `READ_ONLY` as "readable from any thread": if the arena is confined, only the arena's owner thread may access it. Read-only is about **permission to modify bytes**, while thread confinement is a separate **lifetime/ownership constraint**.

### 3.2. `READ_WRITE`

~~~java
// Illustrative Java snippet:
try (Arena arena = Arena.ofConfined();
     FileChannel channel = FileChannel.open(
             file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    MemorySegment segment = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, channel.size(), arena);
    segment.set(ValueLayout.JAVA_BYTE, 0, (byte)42);
    segment.force(); // Request synchronizing mapping changes to storage.
}
~~~

`segment.force()` on a `READ_WRITE` mapping has flush semantics; according to the JDK 22 documentation, for a file descriptor on **local storage**, when it returns normally, changes made to the mapped segment are guaranteed by contract to have been written to the storage device. For a network/remote device, the documentation **does not guarantee** the same. Calling `force` **does not turn multiple writes into a transaction** or guarantee concurrent consistency when another application is modifying the same file.

### 3.3. `PRIVATE`: copy-on-write

`PRIVATE` lets you experiment with modifying bytes in a private view. Changes are **not** pushed back to the file and should not be used as a shared data update mechanism. `mapped.force()` has no effect on a private mapping according to the specification. Note: copy-on-write **does not mean a stable snapshot version** when other processes are modifying the file; observed consistency depends on the OS.

The hands-on example will write byte 77 into a PRIVATE mapping at offset 0, read 77 within that mapping, yet byte 0 in the file after closing will still be 10.

## 4. Lifecycle: closing the channel vs. closing the arena

Two independent resources:

~~~text
FileChannel [OPEN] ------ map(...) --------> MemorySegment [ALIVE]
    |                                           |
    | FileChannel.close()                       | can still get/set/force
    v                                           |
  [CLOSED]                                      |
                                                | Arena.close()
                                                v
                                          [SCOPE DEAD/UNMAPPED]
                                                |
                                                +-> get/set rejected
~~~

`FileChannel` controls the I/O API and the file handle. Once mapping completes, the file is mapped by the OS into memory; the `FileChannel.map(...,Arena)` documentation defines the lifetime of the **mapped segment** by the arena. Therefore **do not treat `channel.close()` as an unmap command**. Conversely, **`arena.close()`** does not force-close a `FileChannel` you are still keeping open: close both according to their respective ownership.

### 4.1. `Arena.ofConfined()`

- A single thread owns the arena and its associated mapped segments.
- Suitable for a map/read/modify/flush/close workflow with a clear lifecycle.
- Use `try-with-resources` so `close()` runs even when a Java exception occurs.
- Accessing a confined segment from another thread may throw `WrongThreadException`.
- Once the arena is closed, `MemorySegment.get/set` on that segment typically throws `IllegalStateException`.
- Avoid letting a segment or slice escape a method if the owner arena has already been closed.

### 4.2. `Arena.ofShared()`

- Allows access from multiple threads when the application genuinely needs to split work.
- **Does not** automatically synchronize concurrent writes; the caller needs a valid locking/atomic strategy.
- `Arena.close()` may need to wait for in-flight accesses to complete according to the scope protocol; you should stop accepting new work, wait for in-flight work, and then close.
- File mapping across processes and threads has complex page-cache/coherence implications. File locks and Java thread locks solve different problems and do not replace each other.

### 4.3. `Arena.ofAuto()` and `Arena.global()`

- `Arena.ofAuto()` has a GC-managed lifetime; cleanup timing is non-deterministic, making it hard to use for files that need timely unmapping.
- `Arena.global()` is a scope that lives until the JVM exits and cannot be closed; avoid using it for temporary mappings or many large mappings that need to be released.
- **Recommendation:** short/medium-lived mappings with a clear application lifecycle should use a closeable arena, especially when you need to delete/rename files on operating systems that restrict operations on still-mapped files.

### 4.4. `asSlice` does not detach from the owner

~~~java
// Illustrative Java snippet: mapped size >= 64 bytes, arena alive.
MemorySegment header = mapped.asSlice(0, 16);
MemorySegment payload = mapped.asSlice(16, 48);
~~~

`header` and `payload` share the same backing mapping/scope. `asSlice` only narrows spatial bounds; it **does not create a separate copy** and does not own a new mapping. When the parent arena closes, the slices also become invalid. Do not use `asSlice` to "keep a mapping alive" after the owner closes.

## 5. Reading/writing with ValueLayout: byte order, alignment, and bounds

`MemorySegment.get(ValueLayout, offset)` takes a **byte offset** from the start of the segment. It is not an `int` array index. For binary files, the layout should follow the **format**:

~~~java
// Illustrative snippet for a big-endian format:
// file has at least 8 bytes and the region is valid.
ValueLayout.OfInt bigEndianInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
int magic = mapped.get(bigEndianInt, 0);
int length = mapped.get(bigEndianInt, 4);
~~~

If an integer is at byte offset 1 of the file, `JAVA_INT` has a native 4-byte alignment constraint and may be rejected. If the format is intentionally packed, use `JAVA_INT_UNALIGNED.withOrder(...)`, **after** proving that bytes 1..4 are genuinely an int in the format and are within bounds.

~~~java
// File contains a big-endian int32 at byte offset 1, not 4-byte aligned.
ValueLayout.OfInt packedInt =
        ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.BIG_ENDIAN);
int number = mapped.get(packedInt, 1);
~~~

Notes:

1. A layout's `byteSize()` is the size of **one value**. `JAVA_INT.byteSize() == 4`; reading at offset 7 in a size-8 segment goes out of bounds.
2. `getAtIndex(JAVA_INT,i)` uses an **element index** (scaled by size), unlike `get(JAVA_INT,byteOffset)`.
3. `MemorySegment` protects Java accesses regarding bounds/scope/threads, but if the backing file is truncated **while the segment is still open**, the OS can make part of the mapping inaccessible; you cannot use Java's bounds checker to prove that an external process hasn't modified the file.
4. `ByteOrder.nativeOrder()` is appropriate for some native ABIs, but file formats using fixed BIG/LITTLE endianness must be decoded strictly per specification, regardless of CPU.
5. When reading a length from file metadata, you must check for negative values, maximums, overflow, and offset before reading the payload; never use any untrusted length from a file to create a slice without verifying it first.

## 6. Complete Java 22+ example, no JNI/C compiler required

This example creates a **temporary file**, pre-writes eight bytes, maps it `READ_WRITE`, closes the channel **before** operating further on the mapping, modifies a byte, and calls `force()`. It then re-opens it `READ_ONLY` and `PRIVATE` to verify access permissions/copy-on-write semantics. Finally, it closes the arena and proves the segment can no longer be accessed.

The source file is named **`FileMappingDemo.java`**, with no `package`. The program uses `Files.createTempFile` and deletes the file in `finally`, so it won't overwrite any of your working files. Verification operations use bytes so stdout does not depend on host endianness or alignment.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FileMappingDemo {
    private FileMappingDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("ffm-mapped-", ".bin");

        try {
            Files.write(file, new byte[] {
                    10, 20, 30, 40, 50, 60, 70, 80
            });

            // Declared outside try to demonstrate rejected access after close.
            MemorySegment mapped;

            try (Arena arena = Arena.ofConfined()) {
                try (FileChannel channel = FileChannel.open(
                        file,
                        StandardOpenOption.READ,
                        StandardOpenOption.WRITE)) {

                    mapped = channel.map(
                            FileChannel.MapMode.READ_WRITE,
                            0, channel.size(), arena);

                    System.out.println("mapped=" + mapped.isMapped());
                    System.out.println("size=" + mapped.byteSize());
                    System.out.println("readOnly=" + mapped.isReadOnly());
                    System.out.println("initialByte1=" +
                            (mapped.get(ValueLayout.JAVA_BYTE, 1) & 0xFF));
                } // Only FileChannel is closed; arena remains open.

                System.out.println("afterChannelClose=" +
                        (mapped.get(ValueLayout.JAVA_BYTE, 1) & 0xFF));

                mapped.set(ValueLayout.JAVA_BYTE, 1, (byte) 99);

                // Sub-segment from file byte2..byte4: 30+40+50.
                MemorySegment slice = mapped.asSlice(2, 3);
                long sum = 0;
                for (long i = 0; i < slice.byteSize(); ++i) {
                    sum += slice.get(ValueLayout.JAVA_BYTE, i) & 0xFF;
                }
                System.out.println("sliceSum=" + sum);

                mapped.force();
                System.out.println("updatedByte1=" +
                        (mapped.get(ValueLayout.JAVA_BYTE, 1) & 0xFF));
            } // Arena closes: mapping is no longer valid.

            try {
                mapped.get(ValueLayout.JAVA_BYTE, 0);
                System.out.println("closedRejected=false");
            } catch (IllegalStateException expected) {
                System.out.println("closedRejected=true");
            }

            System.out.println("fileByte1=" +
                    (Files.readAllBytes(file)[1] & 0xFF));

            // READ_ONLY: Java cannot write through the segment.
            try (Arena arena = Arena.ofConfined();
                 FileChannel channel = FileChannel.open(
                         file, StandardOpenOption.READ)) {

                MemorySegment readOnly = channel.map(
                        FileChannel.MapMode.READ_ONLY,
                        0, channel.size(), arena);

                System.out.println("readonly=" + readOnly.isReadOnly());

                try {
                    readOnly.set(
                            ValueLayout.JAVA_BYTE, 0, (byte) 1);
                    System.out.println("readonlyWriteRejected=false");
                } catch (IllegalArgumentException expected) {
                    System.out.println("readonlyWriteRejected=true");
                }
            }

            // PRIVATE: changes stay in the copy-on-write view,
            // NOT written to the file.
            try (Arena arena = Arena.ofConfined();
                 FileChannel channel = FileChannel.open(
                         file,
                         StandardOpenOption.READ,
                         StandardOpenOption.WRITE)) {

                MemorySegment privateMap = channel.map(
                        FileChannel.MapMode.PRIVATE,
                        0, channel.size(), arena);

                privateMap.set(
                        ValueLayout.JAVA_BYTE, 0, (byte) 77);
                System.out.println("privateValue=" +
                        (privateMap.get(ValueLayout.JAVA_BYTE, 0) & 0xFF));
                privateMap.force(); // Does not persist PRIVATE changes.
            }

            System.out.println("fileByte0=" +
                    (Files.readAllBytes(file)[0] & 0xFF));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

### 6.1. Compiling and running

From the directory containing `FileMappingDemo.java`, JDK 22+ is required:

~~~sh
java -version
javac -version
javac FileMappingDemo.java
java FileMappingDemo
~~~

Windows Command Prompt or PowerShell also uses `javac FileMappingDemo.java` and `java FileMappingDemo`. **No `javac -h`, `jni.h`, C compiler, native library, or `--enable-preview` is needed**. The program does not use `Linker.downcallHandle` and does not call restricted FFM native-function APIs; therefore `--enable-native-access=ALL-UNNAMED` is not required just to map a file into a `MemorySegment`.

### 6.2. Expected stdout

~~~text
mapped=true
size=8
readOnly=false
initialByte1=20
afterChannelClose=20
sliceSum=120
updatedByte1=99
closedRejected=true
fileByte1=99
readonly=true
readonlyWriteRejected=true
privateValue=77
fileByte0=10
~~~

Step-by-step audit:

- The initial temporary file contains bytes `10,20,30,40,50,60,70,80` (8 bytes). `map(READ_WRITE,0,8,arena)` returns a mapped segment of size 8.
- Initial byte at index 1 = 20; closing `FileChannel` does not destroy the mapping because the arena is still alive, so reading after `channel.close()` still yields 20.
- Writing byte at index 1 = 99; the slice starting at index 2 of length 3 has sum 30+40+50=120.
- `mapped.force()` synchronizes changes; after closing the arena, reading the file back gives byte at index 1 = 99.
- Accessing through `mapped` after closing the arena throws `IllegalStateException`, which Java catches and prints true.
- The `READ_ONLY` mapping has `isReadOnly()==true`; attempting `set` throws `IllegalArgumentException`.
- The `PRIVATE` mapping writes byte 0 as 77 **in its private view**, but file byte 0 remains 10 after the scope.
- The temporary file is deleted in `finally` once mappings/channels are closed, without needing to know the temp file's name.

This output is derived from the source logic and API contracts on JDK 22+ when the file system/map mode is supported. It is not yet a result verified by running on an actual OS/JDK; if the file system does not support mapping or an I/O error occurs, the program may throw instead of printing completely. The example avoids printing `isLoaded()` because that is an OS-dependent hint, not a deterministic true/false value.

### 6.3. Why doesn't the example use `FileChannel.force(true)`?

`FileChannel.force(boolean metaData)` is the **channel** flush API; `MemorySegment.force()` is the API associated with a **mapped segment**. Both aim to push writes down to storage in their appropriate contexts, but they differ in target object and contract details. After `FileChannel` is closed, if you want to flush bytes just modified through a `READ_WRITE` mapping, you can still call `mapped.force()` while the arena is alive. Do not assume `FileChannel.close()` is a data synchronization operation equivalent to `mapped.force()`.

## 7. Specialized methods of a mapped MemorySegment

| Method | Role | Limitations |
| --- | --- | --- |
| `isMapped()` | Distinguishes a mapped segment from a regular native segment | Boolean describing segment kind; does not prove the file hasn't been truncated |
| `isNative()` | Confirms the segment is backed outside the Java heap | A mapped segment is a native segment, but not every native segment is mapped |
| `isReadOnly()` | Checks if the view disallows Java writes | Only indicates Java write access permission through the view |
| `byteSize()` | Number of bytes in the mapped region | Does not mean the data is currently resident in RAM |
| `get/set(...)` | Reads/writes individual values by layout | Bounds, scope, thread, alignment; file can be modified externally |
| `asSlice(offset,size)` | Splits a view by byte offsets | Still shares the same backing mapping/arena |
| `asByteBuffer()` | Creates a ByteBuffer view for legacy NIO APIs | `int` capacity limit; shares corresponding lifetime and readonly semantics |
| `force()` | Writes changes of a `READ_WRITE` mapping to storage | No effect on `READ_ONLY`/`PRIVATE`; remote FS lacks the same guarantee |
| `load()` | Best-effort loading of mapped pages into physical memory | May cause page faults/I/O; does not pin pages permanently |
| `isLoaded()` | Hint about the residency level of mapped pages | true/false is not a long-term guarantee |
| `unload()` | Best-effort hint for the OS to evict contents from physical memory | Does **not** unmap, does not invalidate the segment |

`load()`, `isLoaded()`, and `unload()` only work on mapped segments; on non-mapped segments, they may throw `UnsupportedOperationException`. `unload()` is not equivalent to `Arena.close()`: after `unload`, you still have a valid mapped segment and the next read may page-fault to reload data. **Only scope/arena close ends the lifetime according to the example's protocol.**

### 7.1. `force()` is not a transaction/lock

Suppose you update 100 bytes at two different locations and then call `force`. If another reader concurrently reads the file, it does not automatically see both updates in an atomic snapshot. `force` also does not resolve issues where the file is truncated or other processes write into the mapped region. If the application requires atomicity for a record update, you must design a protocol: journal/WAL, versioned records, checksums, file locks/coordination, or a write-rename strategy suitable for the filesystem.

### 7.2. `isLoaded()` is not an accurate RAM meter

A `true` value indicates that most of the content is likely resident at the time of the query; the OS may page it out immediately afterward. `false` does not prove the next read will definitely perform I/O; systems have multiple cache layers. You should not write unit tests with `assert(isLoaded())` after `load()` or use it as a criterion for "mapping succeeded."

## 8. Checking offset, size, file length, and overflow

`map` takes `offset` and `size` as `long`. The JDK 22 contract requires:

~~~text
offset >= 0
size   >= 0
offset + size does not overflow long
channel has permissions compatible with MapMode
arena is alive and the thread is allowed to use it
~~~

Beyond API requirements, applications should require **the mapped region to lie within the file's current size** when intending to read an unmodified file:

~~~java
// Illustrative snippet checking a region [offset,offset+size)
// against fileSize from channel.size().
static void checkRegion(long fileSize, long offset, long size) {
    if (offset < 0 || size < 0 ||
            offset > fileSize || size > fileSize - offset) {
        throw new IllegalArgumentException("invalid file region");
    }
}
~~~

Checking `size > fileSize - offset` avoids adding `offset+size` before validation, preventing overflow. An empty region `offset==fileSize,size==0` is arithmetically valid as a slice; for empty files, handle them without reading elements and verify whether the provider/OS supports creating a 0-byte mapping if you actually call the API.

### 8.1. Common pitfall: mapping past EOF and relying on auto-extension

The `map` overload has several OS/file-provider-dependent details; the documentation warns that behavior when the mapped region is not completely within the file lacks a desirable portable contract. Do not map to a position beyond the file size and expect the file to always auto-extend "correctly and safely." If you want a file of a specific size, **proactively create/set the size using valid I/O**, verify the size, and then map. Do not call `FileChannel.truncate(newLargerSize)` to extend it: by contract, `truncate` does not increase the file size if the argument is larger than the current size.

A standard way to create a fixed-size data file is to write enough bytes per the format, use `FileChannel.write(...)` at the appropriate position (checking the number of bytes actually written), or use a resize operation supported by the file provider; check `channel.size()` before mapping. In the demo, `Files.write` creates exactly eight bytes, so we do not rely on extension semantics beyond EOF.

### 8.2. Splitting large files into mapping windows

For multi-GB files, creating one large mapping may be reasonable on a 64-bit JVM, or it may fail due to address space or mapping resource limits. A simple management approach is to map in windows:

~~~java
// Illustrative Java snippet, not a standalone program:
long fileSize = channel.size();
long windowSize = 64L * 1024L * 1024L; // 64 MiB
for (long offset = 0; offset < fileSize; ) {
    long n = Math.min(windowSize, fileSize - offset);
    try (Arena windowArena = Arena.ofConfined()) {
        MemorySegment window = channel.map(
                FileChannel.MapMode.READ_ONLY, offset, n, windowArena);
        // Process [offset, offset+n) then stop using window.
    }
    offset += n; // n>0 when offset<fileSize and windowSize>0.
}
~~~

In binary formats where a record spans the boundary between two windows, you must preserve the overlap/partial record by design. Do not assume you can advance `offset` by any arbitrary number without accounting for record alignment, UTF-8 encoding split-points, or checksum regions. With concurrent processing, do not share a confined `windowArena` across threads; use a separate arena per thread or a shared arena with synchronization.

## 9. File modified, truncated, replaced, or deleted while still mapped

This is the most dangerous part of memory mapping. A mapped segment with `byteSize()==N` and an alive scope **only proves that Java accesses are within the described region**. It does not prove that the backing file on storage still has N bytes or that the OS still allows access to the entire mapping.

The JDK 22 `FileChannel.map(...,Arena)` documentation states clearly:

- The contents of a mapped segment **may change at any time** if the corresponding file is modified by another program; when changes become visible is **OS-dependent**, with no cross-process consistency guarantee.
- All or part of a mapped region **may become inaccessible** if the backing file is truncated.
- When accessing an invalidated region, an **unspecified exception** may occur at the time of access or later. You cannot rely on a fixed Java exception type for recovery.
- Therefore, you should have a protocol to prevent size/backing file modifications by other programs while the mapping is in use.

On Unix-like OSes, file truncation can cause accessing a nonexistent page to trigger a signal like `SIGBUS`, though it is **not** guaranteed that every JVM/OS will always produce the exact same signal. An OS-level mapping error can be more severe than a Java `IndexOutOfBoundsException`, so do not intentionally write tests that dereference a truncated region just to "see what error happens."

### 9.1. Safe strategies for concurrent file ownership

- Use immutable files for the duration of reader mappings; create a new file and switch pointers/names via a protocol when a version update is needed.
- For mutable files, establish writer/reader coordination and avoid truncating while mapped readers are active.
- If cross-process locking is needed, study `FileChannel.lock`/`tryLock` and filesystem/platform semantics, but remember **file locks usually belong to the JVM/process** and do not automatically protect accesses between Java threads within the same JVM.
- A good shutdown order: stop creating new readers/writers → wait for in-flight memory accesses → flush if `READ_WRITE` → close arena/unmap → close channel (if still open) → rename/truncate/delete per workflow.
- Check I/O errors and ensure lock release even on exceptions. Each file system has its own quirks; mapped files on a network share carry higher consistency risks than on a local disk.

### 9.2. Deleting files differs on Windows and Unix

Mapped regions can hold OS handles/section objects even after `FileChannel` is closed. Some file systems/OSes (especially Windows) restrict deleting/renaming a file while a mapping still exists, whereas Unix may allow unlinking the filename while the mapping continues to access the backing object. Do not design an API assuming every platform allows immediate deletion of a mapped file. **Deterministically closing the Arena** before deleting temporary files is a more portable choice than waiting for `MappedByteBuffer` GC.

## 10. Memory mapping and performance: when is it beneficial?

Memory mapping is not the default answer for every file.

| Workload | Is mapping usually helpful? | Reason/consideration |
| --- | --- | --- |
| Large file, repeated random reads | Usually yes | OS page cache and address-based access |
| Reading only a few-KB header | Probably not | Mapping/page-fault overhead may exceed `Files.readAllBytes` |
| Single-pass sequential processing | Depends on workload | `FileChannel.read` with a large buffer can be just as simple/fast |
| Many records needing views by byte offsets | Yes | `MemorySegment.asSlice` and layout-based access |
| Multi-GB data > ByteBuffer capacity | Possibly yes | `MemorySegment` uses long; still depends on virtual memory/OS |
| File frequently truncated/rewritten | High risk | Segments may lose backing/cross-process coherence |
| Private mapping for temporary edits | Yes | `PRIVATE` copy-on-write, does not persist |
| Need transaction/power-loss atomicity | Insufficient | `force` does not replace WAL/transaction protocols |
| Multiple threads modifying records concurrently | Needs extra design | Arena/shared access ≠ lock/atomicity |

Access time can be dominated by page faults, storage latency, paging pressure, block size, and access pattern rather than the overhead of calling `get`. On some OSes, creating a mapping for a very small file can cost more than `read`. Measure with **actual benchmarks** using representative file sizes, warm/cold caches, random/sequential patterns, concurrent access, flush costs, and cleanup/unmap.

`load()` can help reduce faults in some scenarios, but it can also waste RAM or block on I/O; `isLoaded()` only gives a hint. Do not pre-load multiple GBs if the application only needs a few records.

## 11. Common error patterns and diagnostics

| Anti-pattern | Problem | Fix |
| --- | --- | --- |
| Using three-parameter `FileChannel.map(mode,pos,size)` expecting a `MemorySegment` | Old overload returns `MappedByteBuffer` | Use the **four**-parameter overload with `Arena` (JDK 22+) |
| Running `java.lang.foreign` code on JDK 17 | Java 17 only has a different incubator API | Use JDK 22+ for final source |
| Using `READ_WRITE` when channel is only opened `READ` | Lacks corresponding write permission | Open `READ` + `WRITE`, otherwise `NonWritableChannelException` may occur |
| Using `READ_ONLY` then calling `set` | Read-only segment | Only read, or map `READ_WRITE` if permitted |
| Using `PRIVATE` expecting the file to be updated | Copy-on-write does not persist | Use `READ_WRITE` and `force` |
| Assuming `channel.close()` invalidates `mapped` | Mapping lives by the arena | Stop users and call `arena.close()` |
| Assuming `arena.close()` automatically calls `FileChannel.close()` | Two separate resource owners | Close both channel and arena |
| Reading after `arena.close()` | Segment scope is closed | Return a copy outside the scope if data is needed later |
| Using `Arena.ofConfined()` across another thread | Wrong-thread access | Use owner thread or `Arena.ofShared()` with synchronization |
| Calling `unload()` to release the mapping | `unload` is only best-effort for pages | Use `arena.close()` to unmap |
| Treating `isLoaded()==true` as the entire file being "pinned" | OS can page out at any time | Treat it only as a hint |
| Calling `force` and thinking you have a transaction | Flush ≠ atomicity/locking | Add journal/version/checksum protocol |
| Mapping past EOF and expecting the file to auto-grow | Behavior depends on OS/provider | Write/resize file first, verify size |
| Calling `truncate(larger)` to increase file size | `truncate` does not auto-extend | Use write/resize supported by the provider |
| Truncating the file while another thread reads the mapping | Mapped region becomes inaccessible | Freeze size or stop/unmap first |
| Reading `JAVA_INT` at byte offset 1 | Misalignment if format is packed | Use `JAVA_INT_UNALIGNED` matching the format |
| Reading a network-order file with native-order | Wrong byte order | Use `withOrder(BIG_ENDIAN)`/format layout |
| Wrong unit: record offset instead of byte | Mapping or accessing wrong position | `recordIndex*stride` with overflow checks |
| Calling `asSlice` and keeping it after scope | Slice shares lifetime with parent | Copy bytes if it needs to live longer |
| Assuming a mapped segment has a 2 GB max | Confused with ByteBuffer overload | Segment API size is `long`; still check OS limits |
| Assuming mapping is always faster than file read | Different overhead/IO patterns | Benchmark the actual workload |
| Deleting a mapped temp file before closing Arena on Windows | OS file handle/mapping still held | Unmap first, then delete |

### 11.1. Common exception groups

- `IllegalArgumentException`: invalid `offset`/`size` or addition overflow when creating the mapping; or writing to a read-only segment; or alignment-incompatible layout.
- `IndexOutOfBoundsException`: `get/set` at an offset exceeding `mapped.byteSize()`.
- `IllegalStateException`: using a segment whose arena is closed, or mapping with a non-alive arena.
- `WrongThreadException`: using a confined arena/segment from a non-owning thread.
- `NonReadableChannelException`/`NonWritableChannelException`: channel lacks permissions matching `MapMode`.
- `UnsupportedOperationException`: provider does not support mapping/mode; `force/load` on a non-mapped segment may also be rejected.
- `IOException`/`UncheckedIOException`: I/O error during map or force/flush.
- **Mapped backing inaccessible** due to file truncation: the specification allows an **unspecified** error on access, without promising an easily catchable and recoverable exception.

Distinguish Java bounds/scope errors from backing file errors: even if you prove every offset is valid, external file mutation can still break accessibility at the OS layer.

## 12. Designing a wrapper that properly owns the mapping

A production application should have an owner object:

~~~text
MappedFile (AutoCloseable)
  |
  +-- FileChannel channel (opened per mode)
  +-- Arena arena = Arena.ofConfined()/ofShared()
  +-- MemorySegment region = channel.map(...,arena)
  +-- fixed file size/version contract
  +-- active-access counter/lock if multi-threaded
  |
  +-- read/write methods check owner state
  +-- flush() calls region.force() when READ_WRITE
  +-- close():
        stop accepting new readers/writers
        wait for in-flight accesses
        flush if durability required
        arena.close() (unmap)
        channel.close()
~~~

This is an **API diagram**, not full Java source. If the wrapper serves multiple threads, `Arena.ofConfined()` is unsuitable if other threads access it directly. With `Arena.ofShared()`, simply creating a shared scope does not make accesses atomic; use synchronization or an immutable design and ensure `close` does not race with an ongoing access.

`AutoCloseable` rules:

- Only one owner has the right to close the mapping arena; avoid double-close.
- Do not expose raw `MemorySegment` externally unless the caller agrees to the scope and respects lifetime control.
- `close()` should be idempotent on the wrapper, which does not mean `Arena.close()` can be called arbitrarily multiple times.
- If flush fails, report the error to the caller while still handling resource cleanup in `finally`. Do not silently swallow errors because the data write may not be durable.
- If you want to copy data for the caller to keep after close, copy it to a `byte[]` or a segment with a different scope **before** closing the owner.
- Clearly define interactions with file locks, internal JVM locks, and shared memory across processes; do not use `force()` as a synchronization primitive.

## 13. Exercises with short answers

1. What segment size does `FileChannel.map(READ_ONLY,100,20,arena)` return? **20 bytes**. Which file byte does `segment.get(JAVA_BYTE,0)` read? **byte 100**.
2. Closing the channel without closing the arena: is the mapped segment still usable? **Yes**, if the backing file is still valid, the scope is alive, and the caller is on the right thread.
3. Closing `Arena.ofConfined()` and then calling `get`: which exception is typically thrown? **IllegalStateException**.
4. Can `Arena.ofConfined()` be used from another worker thread? **No**, unless the access is performed on the owner thread; if multi-threading is needed, design with `Arena.ofShared()`/locking.
5. Mapping `READ_ONLY` with a `READ` channel and then calling `set`: is this valid? **No**; the segment is read-only.
6. Which options must the channel be opened with for a `READ_WRITE` mapping? **READ + WRITE**.
7. Mapping `PRIVATE`, writing byte 99, then calling `force`: does the file byte change? **No** from private writes under the copy-on-write contract.
8. Does `mapped.isLoaded()==true` guarantee no page fault on the next read? **No**, it is only a hint.
9. Does `mapped.unload()` unmap and cause `get` to be rejected? **No**; it is only a best-effort hint for OS resident pages.
10. For a 100-byte file, is mapping `offset=90,size=20` a valid read request within the file? **No**: it exceeds EOF. The application should reject it even if the provider might behave differently.
11. For a 100-byte file, is `offset=100,size=0` an arithmetically valid slice? **Yes**; however, do not access any elements and check support for empty mappings.
12. Is `offset=Long.MAX_VALUE-3,size=8` allowed? **No** because addition overflows; check `size > fileSize-offset` once bounds are known.
13. Why might `mapped.get(JAVA_INT,1)` fail even though the file has 100 bytes? **Alignment** or packed format; choose the right layout.
14. If two processes modify the backing file concurrently, does `MemorySegment` guarantee a consistent snapshot? **No**, timing/coherence is OS-dependent.
15. When needing to delete a temp file on Windows, what should be closed first? **Arena/unmap and FileChannel**.
16. Can a 6 GB file use a single `MappedByteBuffer` with a 6 GB capacity? **No** with the traditional ByteBuffer overload; use MemorySegment `long` size if the platform supports it, or multiple windows.

## 14. Checklist for implementing file mapping to MemorySegment

- [ ] **JDK:** Building/running on Java 22+ for the final `FileChannel.map(MapMode,long,long,Arena)`?
- [ ] **Right overload:** Four parameters with `Arena` returning `MemorySegment`, not confused with `MappedByteBuffer`?
- [ ] **Mode:** `READ_ONLY/READ_WRITE/PRIVATE` matches channel permissions and the required persistence semantics?
- [ ] **Region:** `offset`/`size` calculated in **bytes**, non-negative, no overflow; region does not exceed file size per application contract?
- [ ] **Empty:** If the file/slice is empty, handled separately without dereferencing element 0?
- [ ] **Owner:** Closing both `FileChannel` and `Arena`; not relying on GC or `channel.close()` to unmap?
- [ ] **Scope:** All views/slices/ByteBuffers are not used after `Arena.close()`?
- [ ] **Threads:** Confined/shared arena is appropriate and there are no close-while-access races?
- [ ] **Formats:** Reading/writing `ValueLayout` with correct size, alignment, byte order, and file version; not treating file bytes as Java objects?
- [ ] **Durability:** Calling `force()` for `READ_WRITE` when flush is needed; understanding remote FS, transaction, and crash consistency limits?
- [ ] **Private:** Not relying on `PRIVATE` to persist; aware it is copy-on-write?
- [ ] **Resident:** `load/isLoaded/unload` are only best-effort/hints, not page pinning or unmapping?
- [ ] **Backing file:** Protocol in place to prevent external truncate/rename/delete while mapping is active?
- [ ] **Large files:** Accounted for virtual address space, OS quota, windowing, record splitting, and ByteBuffer `int` limits?
- [ ] **Error handling:** Catching the right groups: `IOException`, permission/mode, scope, thread, bounds, and unsupported provider; not relying on a fixed exception when the file is truncated?
- [ ] **Verification:** Ran integration tests on the actual OS/filesystem, covering READ_ONLY, READ_WRITE+force, PRIVATE, channel.close-before-arena.close, scope-after-close, and file cleanup?

**Conclusion:** With JDK 22+, `FileChannel.map(MapMode,offset,size,Arena)` connects a **file** to a **MemorySegment** under an application-controlled scope. `FileChannel` provides I/O permissions; `MapMode` determines read/write/copy-on-write; `MemorySegment` carries spatial bounds and the access API; `Arena` governs the mapping's lifetime. A proper design combines all four, uses `force` when durability is required, and prevents external file mutation or concurrency from corrupting the backing region.

### Official references

- Oracle, [Java 22 FileChannel](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html): `map(MapMode,long,long,Arena)` overload from JDK 22, mode permissions, lifecycle, backing file modifications, and errors.
- Oracle, [Java 22 FileChannel.MapMode](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html): `READ_ONLY`, `READ_WRITE`, `PRIVATE`.
- Oracle, [Java 22 MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `isMapped`, `force`, `load`, `isLoaded`, `unload`, `get/set`, `asSlice`, and scope checks.
- Oracle, [Java 22 Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared/auto/global arenas, scope lifetime.
- Oracle, [Java 22 ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): byte size, alignment, byte order when reading/writing binary data.
- OpenJDK, [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): final FFM in JDK 22 and the memory segments model.
- Oracle, [Java 22 StandardOpenOption](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/file/StandardOpenOption.html): `READ`/`WRITE`, creating/opening files.