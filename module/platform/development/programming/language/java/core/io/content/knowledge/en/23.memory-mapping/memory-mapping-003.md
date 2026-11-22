# Region Mapping and Buffer Size Limits in Java NIO.2

## 1. The Problem: Very Large Files vs. `int`-Sized `MappedByteBuffer`

In Java NIO.2, `FileChannel.map(MapMode mode, long position, long size)` maps **a contiguous region of a file** into the process's address space and returns a `MappedByteBuffer`. The application reads and writes bytes through the `ByteBuffer` API without calling `channel.read`/`write` for each slice of data.

However, two very different sizes are involved:

- **File positions** use `long`, allowing offsets larger than 2 GiB when supported by the file and filesystem.
- **The size of a single mapped region** passed to `map(..., size)` is non-negative and **no greater than `Integer.MAX_VALUE`** (2,147,483,647 bytes), because `MappedByteBuffer.capacity()`, `position()`, `limit()`, and `get(int)` all use `int` indices.

Therefore, **you cannot use a single `MappedByteBuffer` to map an entire file larger than this limit**. The common solution is to **map one smaller region (window/chunk) at a time**, each with a `long` offset and a length fitting within `int`.

Goals after this lesson:

1. Understand `MappedByteBuffer`'s limit and avoid confusing it with a file-size limit.
2. Design a windowed `FileChannel.map` loop that neither skips nor double-reads bytes.
3. Convert accurately between **absolute file offsets (`long`)** and **local mapping indices (`int`)**.
4. Handle trailing file segments smaller than a window, records spanning boundaries, resource limits, and mapping lifecycles.
5. Know when to use mapping versus `FileChannel.read`/`transferTo`.

## 2. How Mapping a File into Memory Works

The operating system manages a mapping from a virtual address range of the process to file contents. Depending on the OS and access timing, memory pages may be loaded from the file via page faults, kept in cache, or evicted to secondary storage.

```text
Large file on disk (long offsets):
0                                                                fileSize
|--------------------|--------------------|--------------------|--------|
      window 0             window 1             window 2           tail

FileChannel.map(READ_ONLY, offset, length)
                       |
                       v
MappedByteBuffer (int indices):
0                                     length
|------------------------------------------|
      get(0), get(1), ... get(length - 1)
```

A newly created `MappedByteBuffer` from `FileChannel.map` has `position=0`, `limit=capacity=size`, and an undefined mark. From the buffer's perspective, index `0` corresponds to **the first byte of the mapped region**, i.e., the file offset equal to the `position` passed to `map`.

**Mapping 256 MiB does not mean the JVM immediately allocates a 256 MiB `byte[]` on the heap.** `MappedByteBuffer` is a direct byte buffer backed by the OS memory-mapping mechanism; virtual address space and physical pages remain bounded, and accesses can still trigger I/O or errors. Do not infer that mapping "uses zero RAM" or is always faster than traditional reading.

## 3. What Does the `Integer.MAX_VALUE` Limit Mean?

```java
FileChannel channel = /* an open FileChannel */;
long fileSize = channel.size();    // long, may be > 2 GiB
long offset = 3_000_000_000L;     // May be a valid position in a large file
long length = 64L * 1024 * 1024; // A 64 MiB window

MappedByteBuffer mapped =
        channel.map(FileChannel.MapMode.READ_ONLY, offset, length);
```

This is an **illustrative snippet inside a method**, which succeeds only if the channel is readable, the file contains the entire mapped region, and the OS has sufficient resources. Do not treat `/* ... */` literally as a standalone program.

`FileChannel.map` accepts `long` for `position`/`size`, yet **the contract still requires `size <= Integer.MAX_VALUE`**. A large `offset` is not an issue in itself; the constraint is the size of **a single mapping**.

| Quantity | Numeric type | Range / meaning |
| --- | --- | --- |
| `channel.size()` | `long` | Current file size; the file can exceed 2 GiB |
| `map(..., position, size)` | `long` for both arguments | `position >= 0`, `0 <= size <= Integer.MAX_VALUE` |
| `mapped.capacity()` | `int` | Number of bytes belonging to **one** mapping |
| `mapped.position()`, `limit()`, `remaining()` | `int` | Local state/bounds of the mapping |
| `mapped.get(index)` | `int` | Index relative to the start of the mapping, not the whole file |
| `offset + mappedIndex` | `long` after widening | Logical position in the file |

**Do not cast `fileSize` from `long` to `int`** to call `map`. For files larger than 2 GiB, casting can overflow or produce a negative value. Likewise, do not allocate a Java array as large as the whole file: Java arrays use `int` indices, and both heap memory and GC have their own limits.

## 4. Windowed Mapping Algorithm

Suppose `fileSize=10` bytes, and we choose `windowSize=4`:

```text
File offsets:  0 1 2 3 | 4 5 6 7 | 8 9
              A B C D | E F G H | I J
Window 1:     [0, 4)  length 4
Window 2:     [4, 8)  length 4
Window 3:     [8,10)  length 2
```

Per-iteration formula:

```text
offset = 0
while offset < fileSize:
    remainingInFile = fileSize - offset
    length = min(windowSize, remainingInFile)
    map(file, offset, length)
    process exactly length bytes
    offset = offset + length
```

Three critical requirements:

- **No lost bytes:** start the next window at exactly `offset + length`, rather than adding a fixed stride when the final window is shorter.
- **No mapping past EOF:** always choose `length <= fileSize - offset`. Reading past the end of a file does not have semantics like automatically reading zero bytes; Java does not guarantee behavior when mapping beyond the file's extent.
- **No integer overflow:** if you ensure `0 <= offset <= fileSize` and `length <= fileSize - offset`, updating `offset += length` will not exceed `fileSize`. Avoid checking `offset + windowSize` when values could approach `Long.MAX_VALUE`.

For an empty file (`fileSize==0`), the loop performs no mappings. If the configured window size is `0` or negative, reject it before looping to avoid an infinite loop with no progress.

## 5. Runnable Java 17+ Example: Three Windows over a 10-Byte File

The following example creates a temporary file containing `ABCDEFGHIJ`, reads it with mappings up to 4 bytes long, then changes byte `F` to `f` via a writable mapping and calls `force()`.

Create `MappedWindowsDemo.java`:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedWindowsDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-windows-", ".dat");

        // Demo uses a temp file. Requests deletion when the JVM exits;
        // actual deletion may depend on the OS if the mapped region is still held.
        file.toFile().deleteOnExit();
        Files.write(file, "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII));

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

            long fileSize = channel.size();
            long windowSize = 4L;

            for (long offset = 0; offset < fileSize;) {
                long length = Math.min(windowSize, fileSize - offset);
                MappedByteBuffer window = channel.map(
                        FileChannel.MapMode.READ_ONLY, offset, length);

                byte[] bytes = new byte[window.remaining()];
                window.get(bytes);

                System.out.printf("range=[%d,%d), data=%s%n",
                        offset, offset + length,
                        new String(bytes, StandardCharsets.US_ASCII));

                offset += length;
            }

            // File offsets 4..7 contain E F G H.
            MappedByteBuffer writable = channel.map(
                    FileChannel.MapMode.READ_WRITE, 4L, 4L);
            writable.put(1, (byte) 'f'); // index 1 in window = file offset 5
            writable.force();

            System.out.println("after edit: "
                    + Files.readString(file, StandardCharsets.US_ASCII));
        }
    }
}
```

Compile and run on JDK 17+:

```bash
javac MappedWindowsDemo.java
java MappedWindowsDemo
```

Expected stdout on a normal filesystem with no external actor modifying the file:

```text
range=[0,4), data=ABCD
range=[4,8), data=EFGH
range=[8,10), data=IJ
after edit: ABCDEfGHIJ
```

**Detailed explanation:**

1. The first window has `offset=0, length=4`, so `window.get(0)` (before `get(bytes)`) corresponds to byte `A` at file offset 0.
2. The second window has `offset=4, length=4`: local indices 0..3 correspond to file positions 4..7, i.e., `EFGH`.
3. The final window has two bytes left: `Math.min(4, 10 - 8) = 2`. Do not attempt to map 4 bytes starting at offset 8, as that would go past the end of the file.
4. Writable mapping at offset 4, length 4: `put(1, 'f')` modifies **the byte at file offset `4 + 1 = 5`**, not the byte at file offset 1.
5. `writable.force()` requests flushing writable mapping changes to the storage device per the API contract (guarantees depend on device type). Re-reading the file yields `ABCDEfGHIJ`.

The example creates a temporary file and registers `deleteOnExit()`; it avoids printing the random path to keep stdout stable. Note that on some operating systems, especially Windows, a mapping can retain resources/file locks until the buffer is garbage collected, restricting file deletion; `deleteOnExit` is also not a guarantee of safe or immediate deletion.

## 6. Pattern for Processing Files Larger Than 2 GiB Without Large Array Allocations

A method that processes a file byte-by-byte using fixed windows:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class WindowedScan {
    // Choose a window smaller than the Integer.MAX_VALUE limit.
    private static final long WINDOW_BYTES = 256L * 1024 * 1024;

    public static long checksum(Path path) throws IOException {
        long sum = 0;

        try (FileChannel channel = FileChannel.open(
                path, StandardOpenOption.READ)) {

            long fileSize = channel.size();
            for (long offset = 0; offset < fileSize;) {
                long mappedSize = Math.min(
                        WINDOW_BYTES, fileSize - offset);

                MappedByteBuffer chunk = channel.map(
                        FileChannel.MapMode.READ_ONLY, offset, mappedSize);

                while (chunk.hasRemaining()) {
                    sum += Byte.toUnsignedInt(chunk.get());
                }
                offset += mappedSize;
            }
        }

        return sum;
    }
}
```

This is a **valid, compilable Java class** (it has no `main`; call `WindowedScan.checksum(path)` from an application or test). The `sum` total is the sum of byte values 0..255 modulo `long` overflow for huge datasets; it is only an illustrative statistic, **not a cryptographic checksum** or secure file-integrity verifier. The 256 MiB window is just a sample choice; the right size depends on the OS, 32/64-bit architecture, live mapping count, file characteristics, and computation.

The key point is that only **the length of each `chunk`** needs to fit in `int`; `offset` and `fileSize` remain `long`. No whole-file transfer into a `byte[]` is performed.

`FileChannel.map` does not require all windows to have the same size. The tail of the file may be much shorter. If the file continues to be written to or is truncated by another process during scanning, the initial size snapshot may no longer hold; this pattern assumes the file does not change while being read.

## 7. Computing Absolute Offsets and Indices Within Each Window

Suppose you want to access the byte at absolute file position `absoluteOffset`:

```text
windowStart = floor(absoluteOffset / windowSize) * windowSize
indexInWindow = absoluteOffset - windowStart
byte = mappedWindow.get((int) indexInWindow)
```

If `windowSize=4` and you need to read file offset 9:

```text
windowStart = (9 / 4) * 4 = 8
indexInWindow = 9 - 8 = 1
mapping for [8,10) -> get(1) fetches 'J'
```

Perform arithmetic in `long` before narrowing the index to `int`. Only cast after verifying `0 <= indexInWindow < mappedWindow.limit()`. Never pass `absoluteOffset` directly to `mapped.get(int)`: that is a file position, not a mapping index.

When a window is created on demand (not fixed-grid), the calculation is simpler:

```java
long localOffset = absoluteOffset - windowStart;

if (localOffset < 0 || localOffset >= window.limit()) {
    throw new IndexOutOfBoundsException("Outside current window");
}
byte value = window.get(Math.toIntExact(localOffset));
```

The snippet above is illustrative, assuming `window` and `windowStart` are the current mapping and its starting offset. `Math.toIntExact` detects out-of-range conversions instead of silently overflowing. Store `windowStart` alongside `MappedByteBuffer` in application logic if random access is needed.

## 8. Window Boundaries: Records Can Span Two Mappings

A subtle bug occurs when reading structured data: **mapping boundaries do not necessarily align with record boundaries**.

For example, a file consists of 6-byte records, while the window is only 4 bytes:

```text
File offsets:     0 1 2 3 | 4 5 6 7 | 8 9 10 11
Record 1:         [----------- 6 bytes -------]
Record 2:                     [----------- 6 bytes -------]
Windows:         [4 bytes]  [4 bytes]   [4 bytes]
```

If each mapping simply calls `getInt()` or decodes a struct without checking `remaining()`, data near the end of a window can throw `BufferUnderflowException` even though the file **still has bytes in the next window**.

There are three common strategies:

1. **Align windows to fixed record sizes.** If each record is exactly 16 bytes, choose `windowSize` divisible by 16 and map whole-record regions; handle any trailing remainder separately. Ensure the starting offset of the structure is also aligned appropriately.
2. **Carry-over remaining bytes.** Copy the few leftover bytes at the end of a window into a small auxiliary buffer, then combine them with the opening bytes of the next window before parsing. This suits formats with headers or variable-length records.
3. **Overlapping windows.** Each window can overlap by a few bytes from the adjacent region to ensure complete records can be read, while defining strict ownership rules for each pass so you **never double-count or double-write bytes**.

For instance, if a 4-byte integer starts at file offset 3, only one byte remains inside window `[0,4)`; `getInt(3)` is invalid. You must fetch the remaining three bytes from window `[4,8)` or adopt a different design strategy. Do not try to increase `limit` beyond `capacity` to "extend" a mapping; that is impossible.

### 8.1. UTF-8, Characters, and Window Boundaries

If a file contains UTF-8 text, a Unicode character can be encoded in 2–4 bytes and straddle two windows. Directly calling `new String(bytesOfOneWindow, UTF_8)` per window **can corrupt characters at the boundary**. Carry incomplete UTF-8 bytes over to the next window, or use `CharsetDecoder` in streaming mode while preserving decoder state and handling `CoderResult.UNDERFLOW` properly.

The same applies to multi-byte delimiters, length headers, checksums, and binary structures: **mappings split by physical byte size; parsers split by semantic boundaries**. The two must be coordinated.

## 9. How Large Should the Window Size Be?

No single size works best for every system. Choosing `64 MiB`, `128 MiB`, or `256 MiB` can be reasonable for initial testing, but you must measure with real data and your target environment.

Factors that matter:

| Factor | Impact |
| --- | --- |
| API limit | Each mapping has a maximum size of `Integer.MAX_VALUE`; pick smaller for headroom |
| Address space | 32-bit processes exhaust virtual address space much sooner than 64-bit |
| Live mapping count | Many simultaneously live windows increase address-space and OS resource pressure |
| Access pattern | Sequential reads, random access, and record updates have different characteristics |
| Record size | Aligning boundaries reduces carry-over logic and mapping frequency |
| Storage characteristics | SSD/HDD, network filesystem, page cache, latency, throughput |
| File mutability | Mapping a file truncated externally carries more risk than reading a static file |
| Data durability | `READ_WRITE` mappings need an appropriate force/persistence strategy |

**Too small:** creates many mappings, increasing overhead and window-management iterations. **Too large:** increases address-space pressure, mapping cost, page-fault footprint, and mapping lifetimes. Memory-mapped I/O is not always faster than `FileChannel.read`, especially for small files or simple linear read paths.

For `WINDOW_BYTES`, implementations should validate `1 <= WINDOW_BYTES <= Integer.MAX_VALUE` up front. Avoid using the exact maximum as an unvarying default, particularly in cross-platform deployments.

## 10. The Three Mapping Modes and Data Mutation

`FileChannel.MapMode` provides the primary options:

| Mode | Channel open condition | Can call `put`? | Writes changes to underlying file? |
| --- | --- | --- | --- |
| `READ_ONLY` | Open for reading | No; throws `ReadOnlyBufferException` | No |
| `READ_WRITE` | Open for reading **and** writing | Yes | Changes propagate to the file, with OS-dependent timing; `force()` may be used |
| `PRIVATE` | Open for reading **and** writing | Yes, via copy-on-write | Changes in the private space **do not** propagate to the underlying file |

`PRIVATE` creates copies only as needed (per-page copy-on-write) and **does not substitute** for `READ_WRITE` mode when the goal is modifying the file. Calling `force()` on a non-`READ_WRITE` mapping may have no effect.

When working with multiple writable windows, watch out for overlapping windows mapped to the same file and concurrent updates. Do not assume all threads/processes observe changes in a particular order; design explicit synchronization and file consistency mechanisms.

## 11. `force()`, `load()`, and `isLoaded()` Are Not the Same Function

Three common `MappedByteBuffer` methods:

- **`force()`**: for `READ_WRITE` mappings, requests pushing performed changes to the storage device. For files on local devices, the API commits that changes are written upon completion; for non-local devices, this guarantee is weaker. The method can throw `UncheckedIOException` if an I/O error occurs while flushing.
- **`force(index, length)`**: specifies a sub-region of the buffer to flush; `index` and `length` are **local indices**, not absolute file offsets. The system may write extra data outside the specified range due to device block sizes.
- **`load()`**: attempts to load mapping contents into physical memory; this is **best-effort**, may cause page faults/I/O, and does not mean data stays in RAM permanently.
- **`isLoaded()`**: returns a hint as to whether the pages are likely already in RAM; a `true` result **is not a guarantee** for subsequent reads.

With writable windows, you can call `force()` on each window after finishing edits, or apply a batched synchronization policy depending on durability needs. `channel.force(true)` is a separate `FileChannel` operation; do not unconditionally equate it with `mapped.force()` in scope or timing.

## 12. Mapping Lifecycle Differs from `FileChannel` Lifecycle

A crucial point: **closing `FileChannel` does not automatically invalidate any `MappedByteBuffer` obtained from that channel**. By API contract, the mapping remains valid until the buffer itself is garbage-collected. Java 17 does not provide a standard public `MappedByteBuffer.unmap()`.

```java
MappedByteBuffer mapped;
try (FileChannel ch = FileChannel.open(file, StandardOpenOption.READ)) {
    mapped = ch.map(FileChannel.MapMode.READ_ONLY, 0L, 1024L);
}
// Channel is closed; the mapping may still remain valid.
byte first = mapped.get(0);
```

This is an illustrative snippet, assuming `file` is declared and contains at least 1024 bytes; place the code inside a method handling `IOException`. Do not try to drive unmapping using `System.gc()`: the JVM does not guarantee timely GC execution.

**Consequences for windowed mapping:**

- Do not keep all windows in a `List<MappedByteBuffer>` unless truly necessary. For large files, doing so can retain hundreds of mappings and substantial OS resources.
- Once finished processing a region, drop the reference if it is no longer needed. Releasing the mapping remains managed by JVM/GC; you cannot assert it is unmapped the instant a variable leaves scope.
- When deleting, replacing, or renaming a mapped file, Windows and certain providers may report errors while a mapping still holds resources. Design lifecycle management, test on the target OS, and handle failures.
- When explicit mapping lifecycle control is required, evaluate newer APIs in the corresponding JDK; for example, Java 22+ includes the Foreign Function & Memory API with `MemorySegment`, though signatures and support depend on the JDK version. This article uses the stable Java 17+ `MappedByteBuffer` API.

## 13. File Modified or Truncated While Mapped

Memory mapping is stable only when file conditions are also stable. The Java API notes that behavior when a mapping requests a region beyond the file, or when file size/content changes after mapping, **is partly OS-dependent and not fully specified**.

Keep in mind:

1. If another process **truncates the file** shorter than the mapped region, part of the mapping can become inaccessible. Consequences can include exceptions or OS-level errors; do not assume zero bytes will be returned automatically.
2. If the file **grows in size**, an existing `MappedByteBuffer` does not automatically increase its `capacity`. You must create a new mapping for the additional region if application logic supports it.
3. `channel.size()` at the start of a scan loop is only a snapshot at that instant. If the file changes concurrently, observed data may be inconsistent.
4. Use file locks or application-level coordination when workflows require a stable snapshot; do not assume file locks protect data identically across all providers or operating systems.
5. Do not map a huge region past EOF expecting `READ_WRITE` will always allocate accessible contents. Some implementations allow mapping beyond EOF, yet **content and bounds beyond the existing file have unguaranteed behavior**; to grow a file, design a resizing strategy and verify afterward.

In production systems, particularly with sensitive data or strict consistency requirements, immutable or versioned files greatly reduce risks during windowed scanning.

## 14. Common API and Design Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| `channel.map(READ_ONLY, 0, channel.size())` on a >2 GiB file | A single mapping exceeds `Integer.MAX_VALUE` | Split into windows smaller than the limit |
| Casting `long fileSize` down to `int` | Prone to overflow/truncation | Keep `long` for offset, fileSize, and window math |
| Mapping the last window with `windowSize` | Exceeds EOF | `min(windowSize, fileSize - offset)` |
| `offset += windowSize` regardless of trailing region | Easy to miscalculate offset or skip/corrupt logic | Advance by the actual `mappedSize` |
| Calling `mapped.get((int) absoluteOffset)` | Buffer index is local, not a file offset | `(int)(absoluteOffset - windowStart)` after bounds check |
| Setting `windowSize=0` | Loop makes no progress | Validate configuration values up front |
| Calling `getInt()` with fewer than 4 bytes left in mapping | `BufferUnderflowException` even though file has more bytes | Align windows to records or use carry-over |
| Decoding each UTF-8 region with `new String` | Can split multi-byte characters | Streaming decoder / carry-over |
| Mapping thousands of windows and keeping all references | Mapping resources / virtual address usage grows | Process sequentially, manage lifetimes, measure load |
| Calling `force()` and assuming durability on every network FS | Guarantees vary by device/provider | Design durability for the actual environment |
| `channel.close()` then assuming mapping is unmapped | Mapping has an independent lifecycle | Do not assume immediate unmapping |
| Truncating a file while mappings are active | Mapping can lose validity | Coordinate resizing with readers/writers |
| Assuming mapping is always faster than `read()` | Page faults/mapping overhead can be high | Benchmark for your sizes and access patterns |

### Common Exceptions

- `IllegalArgumentException`: negative offset, negative or out-of-range size, or another `map` precondition violated.
- `NonReadableChannelException`: attempting a `READ_ONLY` map on a channel not open for reading.
- `NonWritableChannelException`: attempting `READ_WRITE`/`PRIVATE` without write (and read) permissions.
- `ReadOnlyBufferException`: attempting `put` on a `READ_ONLY` mapped buffer.
- `IOException`: I/O error while creating a mapping or operating on the channel.
- `IndexOutOfBoundsException`/`BufferUnderflowException`: accessing an index or reading past a window's `limit`.

Do not lump everything together as "file too large." Log operation type, file size, offset, mapped size, mode, and channel state to diagnose the actual cause.

## 15. Windowed Mapping vs. `FileChannel.read()`

Memory mapping is useful for frequent random reads over large files or manipulating many bytes without making separate system calls for each step. Yet `FileChannel.read(buffer, offset)` remains a great option for sequential scans or when you want direct control over buffer sizes and resource lifetimes:

| Criterion | Windowed `MappedByteBuffer` | `FileChannel.read(ByteBuffer, long)` |
| --- | --- | --- |
| Content access | `get/put` on mapped memory | Read data into a buffer |
| Operation limit | One mapping at most `Integer.MAX_VALUE` bytes | A `ByteBuffer` also uses `int` capacity; loop multiple reads |
| File position | `long` offset in `map` | `long` offset in `read` |
| Overhead | Mapping setup, page faults, virtual address space | Read/syscall cost, copying data into buffer |
| Lifecycle | Mapping can outlive `channel.close()` | Read buffer can be reused; creates no file mapping |
| File modified/truncated | OS-dependent risks accessing mapped region | Subsequent reads return new byte counts, EOF, or `IOException` |
| Suitability | Random access / large-block scans depending on workload | Sequential streams/scans, block parsers, easily controlled lifetime |

There is no rule that "files over 2 GiB must be memory-mapped." Large files can also be processed via `FileChannel.read` looping with a modest buffer. If you only need to copy a file to another channel, consider `transferTo`/`transferFrom` and track actual bytes transferred instead of mapping and copying manually.

## 16. Exercises and Solutions

**Exercise 1.** A file is 10 bytes long, with window size 4. What intervals should be mapped?

**Answer:** `[0,4)`, `[4,8)`, `[8,10)`; 4, 4, and 2 bytes respectively. Do not map `[8,12)`.

**Exercise 2.** Can a 5 GiB file be processed with Java 17 `MappedByteBuffer`?

**Answer:** Yes. Do not create a single 5 GiB mapping; split it into multiple mappings, e.g., 256 MiB per window. File offsets and `fileSize` use `long`.

**Exercise 3.** Mapping `map(READ_ONLY, 1_000L, 100L)`. Which index corresponds to the byte at file offset 1,037?

**Answer:** `1037 - 1000 = 37`. Call `mapped.get(37)`.

**Exercise 4.** Why cannot `mapped.getInt(98)` be used on a 100-byte region to read 4 bytes?

**Answer:** Only two bytes remain at indices 98 and 99. You must read the rest from the next mapping or map a region containing all 4 bytes; absolute `getInt(98)` cannot exceed `limit=100`.

**Exercise 5.** Can you call `mapped.put(0, (byte)42)` on a `READ_ONLY` mapping?

**Answer:** No; it throws `ReadOnlyBufferException`. To modify file data, open the channel with read/write permissions and map `READ_WRITE`.

**Exercise 6.** Does closing `FileChannel` immediately release mapped memory?

**Answer:** Not guaranteed. `MappedByteBuffer` and its mapping can persist until the buffer is garbage-collected.

**Exercise 7.** Is splitting UTF-8 across 64 MiB mappings and calling `new String` independently on each region always correct?

**Answer:** No. Bytes of a single character can straddle two regions; use a streaming `CharsetDecoder` or carry over leftover bytes.

**Exercise 8.** When a file size exceeds `Integer.MAX_VALUE`, should you write `int length = (int) channel.size()`?

**Answer:** No. The cast can overflow and produce a wrong value; `channel.size()` must stay `long`, and only the bounded window length can be safely converted to `int`.

## 17. Safe Implementation Checklist

1. Open `FileChannel` with permissions matching `MapMode`.
2. Read `fileSize` into a `long` variable; determine whether the file can change concurrently.
3. Choose a positive `windowSize` not exceeding `Integer.MAX_VALUE`, and validate configuration.
4. Iterate `offset` from 0 while `offset < fileSize`.
5. Compute `length = Math.min(windowSize, fileSize - offset)` using `long` arithmetic.
6. Call `map(mode, offset, length)`, handle `limit/capacity` properly, and convert `absoluteOffset - offset` to a local index.
7. If the parser handles multi-byte records or UTF-8, handle boundary-spanning data.
8. For writes, establish `READ_WRITE` mode, `force()` policy, locking, and crash consistency.
9. Avoid retaining too many mappings and avoid assuming `close()` unmaps immediately; test on your actual Windows/Linux runtime environment.
10. Benchmark against `FileChannel.read`/other I/O before claiming mapping is faster.

## API Documentation

- Java SE 21 — `FileChannel.map(MapMode,long,long)`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 21 — `MappedByteBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/MappedByteBuffer.html
- Java SE 21 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 21 — `FileChannel.MapMode`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html
