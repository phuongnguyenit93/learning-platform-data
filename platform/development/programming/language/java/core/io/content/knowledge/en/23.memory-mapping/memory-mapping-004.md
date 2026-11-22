# Reading and Writing Data Through Mapped Memory (Java NIO.2)

## 1. Problem and Objectives

When processing large binary files, Java offers two common approaches:

1. Reading/writing bytes via `FileChannel.read(ByteBuffer)` and `FileChannel.write(ByteBuffer)`. The program prepares its own buffer, invokes I/O, and handles the actual byte count transferred.
2. **Memory-mapped files**: using `FileChannel.map(...)` to map a **byte region in a file** into a `MappedByteBuffer`. The program accesses this region via `get`, `put`, and `ByteBuffer` methods, while the OS manages the mapping between virtual memory and file data pages.

The mapped memory remains backed by a real file, though the application operates through buffer indices. Mapping **does not mean the entire file is immediately loaded onto the Java heap**, nor does it mean every byte edit is durably written to the device immediately after each `put`.

```text
FileChannel ── map(mode, fileOffset, length) ──▶ MappedByteBuffer
    │                                             │
    │                                       get / put / getInt / putLong ...
    │                                             │
    └── file on filesystem ◀── OS page cache / memory mapping
```

**Objectives:** create mappings properly; read/write data through `MappedByteBuffer`; distinguish `READ_ONLY`, `READ_WRITE`, and `PRIVATE`; master `position`, `limit`, and buffer byte indices vs. file offsets; understand `force()`, size constraints, performance, concurrency, and resource lifecycles.

## 2. From `FileChannel` to `MappedByteBuffer`

Core API:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        fileOffset,
        length
);
```

This is an illustrative snippet inside a method where `channel` is an appropriately opened `FileChannel` with `IOException` handled.

The three parameters mean:

- `mode`: permissions and write behavior of the mapped region.
- `fileOffset`: starting position **in bytes within the file**; type `long`, must be non-negative.
- `length`: length of the **mapped region in bytes**; type `long` in the call signature, though for the overload returning `MappedByteBuffer`, the map size must not exceed `Integer.MAX_VALUE`. It must be non-negative.

If mapping from offset 100 with length 50:

```text
File:           byte 0 ... byte 99 | byte 100 ........ byte 149 | byte 150 ...
                                            ↑                   ↑
Mapped buffer:                            index 0 ...       index 49
Initial buffer.position(): 0
Initial buffer.limit():    50
buffer.capacity():         50
```

**Formula:** `fileOffset + bufferIndex` is the corresponding byte position in the file, provided the file region is not altered by another actor. `buffer.get(0)` reads the byte at `fileOffset`, not byte 0 of the entire file if `fileOffset != 0`.

Upon successful return, the buffer has `position=0`, `limit=capacity=length`, and an undefined `mark`. `MappedByteBuffer` is a **direct byte buffer**; its data is tied to the mapping, with no accessible Java `byte[]` like a heap `ByteBuffer.allocate(...)`.

Note that calling `map` creates a mapped address region. It is not equivalent to `Files.readAllBytes`, which allocates a Java array holding all read bytes.

## 3. The Three Mapping Modes: Write Permissions and File Relationship

`FileChannel.MapMode` defines three standard modes:

| Mode | Channel open requirement | Modifiable via buffer? | Are changes written back to file? |
|---|---|---|---|
| `READ_ONLY` | Requires `READ` permission | **No**; `put` throws `ReadOnlyBufferException` | No modifications via this view |
| `READ_WRITE` | Requires both `READ` and `WRITE` | **Yes** | Changes are propagated to the file per OS mechanics; timing is not deterministic by default |
| `PRIVATE` | Requires both `READ` and `WRITE` | **Yes** | **No**; copy-on-write creates a private copy for modified parts, without writing those changes back to the file |

Example opening a channel with explicit permissions:

```java
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path file = Path.of("records.bin");

try (FileChannel channel = FileChannel.open(
        file,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    // Choose the appropriate mode and map a segment within the file.
    // If the file does not exist, opening fails; this example assumes it already exists.
}
```

`READ_ONLY` can be mapped using a channel opened with `READ` only. `READ_WRITE` and `PRIVATE` require a channel opened for **both reading and writing** per the `FileChannel.map` contract, even though `PRIVATE` does not write edited bytes back to the file. Missing permissions may trigger `NonReadableChannelException` or `NonWritableChannelException`.

### 3.1. `READ_ONLY`: reading data and blocking writes through the mapping

```java
try (FileChannel channel = FileChannel.open(file,
        StandardOpenOption.READ)) {
    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_ONLY, 0, channel.size());

    byte first = mapped.get(0); // If the region has at least one byte.
    // mapped.put(0, (byte) 7): ReadOnlyBufferException.
}
```

This is an illustrative snippet with full imports and `file` pointing to a readable, non-empty file. `mapped.isReadOnly()` alone indicates permissions on the **view**, without rendering the file data immutable: another process can still alter the file. Whether external changes appear immediately in the mapped region depends on the operating system and is left open by the API.

### 3.2. `READ_WRITE`: editing bytes directly on the mapped region

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, 4);

mapped.put(0, (byte) 'J');  // Writes at the start of the region.
mapped.put(1, (byte) 'a');
mapped.put(2, (byte) 'v');
mapped.put(3, (byte) 'a');
mapped.force();              // Requests writing modified pages to the device.
```

This illustrative snippet assumes `channel` has both read/write permissions and the file already contains at least 4 bytes. `put(index, value)` is an **absolute** access, so it does not advance `position`. `MappedByteBuffer.force()` is designed to request pushing changes of a `READ_WRITE` mapping to the storage device; durability details are explained later.

### 3.3. `PRIVATE`: copy-on-write, not `READ_ONLY`

```java
MappedByteBuffer privateView = channel.map(
        FileChannel.MapMode.PRIVATE, 0, 4);

privateView.put(0, (byte) 'X'); // Valid on a writable view.
```

Data modified through `privateView` is stored privately via copy-on-write, **not propagated back to the file**, and not visible to other programs mapping the same file via their own mappings. This is not a way to create a **full independent copy of the entire file upon calling map**; the OS may create private copies only for modified pages. Do not use this mode if the goal is saving edits to the file.

Across different modes or mappings created by other programs, do not guess the exact moment modified bytes become visible: Java's contract leaves many details to the OS.

## 4. Preparing File Size Before Mapping

When mapping for reading, you must know what region exists. `channel.size()` returns the current size, though another process could alter the file between measuring and accessing it.

**Important:** the `FileChannel.map` contract does not clearly define behavior if the requested region **does not lie completely within the current file size**; do not rely on `map` automatically extending a file without a preparation step.

For predictable demo behavior, create content first:

```java
byte[] bytes = "HELLO".getBytes(StandardCharsets.US_ASCII);

try (FileChannel channel = FileChannel.open(
        file,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    ByteBuffer source = ByteBuffer.wrap(bytes);
    while (source.hasRemaining()) {
        channel.write(source);
    }

    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, bytes.length);
}
```

This illustrative snippet requires importing `java.nio.ByteBuffer`, `java.nio.MappedByteBuffer`, `java.nio.charset.StandardCharsets` along with the classes/channel above, and a method handling `IOException`. Use the `while (source.hasRemaining())` loop because `FileChannel.write` **does not guarantee** writing all remaining bytes in a single call.

If your use case requires a fixed-size binary file before mapping, you can use `FileChannel.position(...)` and write a byte at the end, or create a file of the desired size using appropriate filesystem APIs. `FileChannel.truncate(newSize)` **only truncates when the current size is larger**; if `newSize` exceeds the file size, `truncate` **does not extend the file**.

### 4.1. How long can a single mapping be?

For the `FileChannel.map(MapMode, long, long)` overload returning `MappedByteBuffer` in Java 17/21, `length <= Integer.MAX_VALUE`. A file can exceed this limit, but **a single mapping buffer** still uses `int` indices.

To handle very large files, design **windowed mapping**:

```java
long fileSize = channel.size();
long windowSize = 64L * 1024 * 1024; // 64 MiB, illustrative.

for (long offset = 0; offset < fileSize; offset += windowSize) {
    long length = Math.min(windowSize, fileSize - offset);
    MappedByteBuffer window = channel.map(
            FileChannel.MapMode.READ_ONLY, offset, length);

    while (window.hasRemaining()) {
        byte value = window.get();
        // Process each byte per specific requirements.
    }
}
```

This is an **illustrative algorithm snippet**, assuming `channel` is open for reading, the file is not modified concurrently, and `// Process` is replaced with business logic. Do not retain an unbounded number of created mappings: views can remain alive via references in the system. The `windowSize` parameter is not the OS page size, merely an example of choosing a window smaller than the API limit. If data consists of records that may straddle window boundaries, retain the incomplete bytes and process them in the next window; do not assume every window holds an exact integer number of records.

## 5. Reading/Writing Like a `ByteBuffer`

`MappedByteBuffer` extends `ByteBuffer`, so many familiar rules apply:

- `capacity`: total byte count of the mapping, fixed for that buffer.
- `limit`: current access bound, initially equal to capacity.
- `position`: where the next relative `get()` or `put(byte)` reads/writes; initially 0.
- `remaining() = limit - position`.
- `get(index)` and `put(index, value)`: **absolute**, leaving `position` unchanged.
- `get()` and `put(value)`: **relative**, advancing `position`.
- `duplicate()` and `slice()`: create views sharing the same data but with independent cursors.
- `clear()`, `flip()`, `rewind()`: primarily manage cursor/limit, **without erasing bytes from the mapping**.

Example of a 6-byte mapped region:

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, 6);

mapped.put(0, (byte) 'A'); // position stays 0.
mapped.position(1);
mapped.put((byte) 'B');    // Writes at index 1; position becomes 2.
byte first = mapped.get(0); // Reads index 0; position stays 2.
```

These lines are illustrative inside a method with a read/write channel and a file of at least 6 bytes. If you call `mapped.flip()` after a series of absolute `put(index, value)` edits while `position` is still 0, `flip()` sets `limit` to 0 and leaves zero elements for subsequent relative reads. With fixed-offset accesses, calling `flip()` is unnecessary compared to filling a `ByteBuffer` to pass to a channel.

### 5.1. `slice()` shares the same data

```java
MappedByteBuffer base = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, 8);
base.position(2);
base.limit(6);
ByteBuffer slice = base.slice();

slice.put(0, (byte) 99); // Modifies byte at index 2 in base.
```

This illustrative snippet requires importing `ByteBuffer` and `MappedByteBuffer`; `base` is valid when the file is at least 8 bytes. `slice` has `position=0, limit=capacity=4`; index 0 of `slice` maps to index 2 of `base`. Since Java 17, `slice(index, length)` operations can select a region directly by index.

**Do not treat `slice` or `duplicate` as content copies.** Having separate cursors does not mean they hold separate bytes. When an independent snapshot is required, copy bytes into a new array or `ByteBuffer` and consider consistency if the file is modified concurrently.

### 5.2. Reading integers depends on `ByteOrder`

Methods `getInt`, `putInt`, `getLong`, and `putLong` operate on multiple bytes and require matching the byte order in the file format.

```java
mapped.order(ByteOrder.LITTLE_ENDIAN);
mapped.putInt(0, 0x01020304);
System.out.printf("%02X %02X %02X %02X%n",
        mapped.get(0) & 0xFF,
        mapped.get(1) & 0xFF,
        mapped.get(2) & 0xFF,
        mapped.get(3) & 0xFF);
```

This illustrative snippet assumes a `READ_WRITE` mapping at least 4 bytes long and imports `java.nio.ByteOrder`. Byte output in `LITTLE_ENDIAN`:

```text
04 03 02 01
```

If you read a little-endian file without setting the byte order, `getInt()` will produce the wrong value. A new `ByteBuffer` uses **BIG_ENDIAN** by default. Do not equate mapping a file with automatically detecting endianness from the data format.

## 6. Complete Java 17+ Example: Writing and Re-reading a Mapped File

The following example uses fixed ASCII content to clearly distinguish **byte positions** from characters. It creates a temporary file, writes `HELLO`, maps `READ_WRITE`, modifies bytes via both absolute and relative accesses, tests `READ_ONLY` and `PRIVATE`, and reads back the bytes stored in the file.

**File:** `MappedIoDemo.java`

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedIoDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-io-", ".bin");

        // The mapping may hold resource handles after FileChannel closes.
        // Best-effort cleanup of the temporary file when the JVM exits.
        file.toFile().deleteOnExit();

        byte[] initial = "HELLO".getBytes(StandardCharsets.US_ASCII);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            ByteBuffer source = ByteBuffer.wrap(initial);
            while (source.hasRemaining()) {
                channel.write(source);
            }

            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, initial.length);

            System.out.println("map size: " + mapped.capacity());
            System.out.println("first byte: " + (char) mapped.get(0));

            mapped.put(0, (byte) 'h'); // H -> h, position unchanged.

            ByteBuffer alias = mapped.duplicate();
            alias.put(1, (byte) 'I');  // E -> I in shared storage.

            mapped.position(2);
            mapped.put((byte) 'y');   // L -> y, position advances to 3.

            System.out.println("position: " + mapped.position());
            System.out.println("alias change: "
                    + (char) mapped.get(1));

            // READ_WRITE: request pushing modified bytes to the device.
            mapped.force();

            MappedByteBuffer readOnly = channel.map(
                    FileChannel.MapMode.READ_ONLY, 0, initial.length);
            System.out.println("read only: " + readOnly.isReadOnly());

            try {
                readOnly.put(0, (byte) 'X');
            } catch (ReadOnlyBufferException ex) {
                System.out.println("read-only write blocked");
            }

            MappedByteBuffer privateMap = channel.map(
                    FileChannel.MapMode.PRIVATE, 0, initial.length);
            privateMap.put(0, (byte) 'P');
            System.out.println("private first: "
                    + (char) privateMap.get(0));
        }

        // Read via regular file API after forcing the mapping.
        // PRIVATE writing 'P' does not alter the corresponding byte in the file.
        System.out.println("file content: "
                + Files.readString(file, StandardCharsets.US_ASCII));
    }
}
```

Compile and run with JDK 17+:

```bash
javac MappedIoDemo.java
java MappedIoDemo
```

**Expected stdout on a normal filesystem supporting memory mapping:**

```text
map size: 5
first byte: H
position: 3
alias change: I
read only: true
read-only write blocked
private first: P
file content: hIyLO
```

Explanation:

1. Five bytes are fully written to the file before mapping so range `0..4` lies entirely within the existing file.
2. The new `MappedByteBuffer` has `capacity=5`; `get(0)` sees `H`.
3. `put(0, 'h')` is absolute; `alias.put(1, 'I')` alters byte index 1 in the **same memory region**, even though `alias` has its own position.
4. `mapped.position(2); mapped.put('y')` modifies byte index 2 and advances position to 3. The three edits yield bytes `hIyLO`.
5. `mapped.force()` requests writing changes from the `READ_WRITE` mapping.
6. The `READ_ONLY` mapping allows reads but rejects `put`.
7. The `PRIVATE` mapping allows editing the view to `P...`, but **does not write** `'P'` to the file. Thus the final file read prints `hIyLO`.

The example intentionally uses single-byte-per-character ASCII bytes. In practice, when a file uses UTF-8, a Unicode code point can occupy multiple bytes; do not write `mapped.put(index, (byte) someChar)` expecting to validly write Vietnamese characters or emoji. Encode the full string with `CharsetEncoder` or `getBytes(StandardCharsets.UTF_8)`, then write the exact byte count and region size.

Calling `deleteOnExit()` is only **best-effort** temporary cleanup: some operating systems hold files/mappings while the JVM is alive or restrict deletion; do not turn it into a promise that the OS mapping was released immediately after `channel.close()`.

## 7. Reading UTF-8 Text via Mapping

A mapped buffer holds bytes; to read text, you must **decode with a charset**, rather than casting each byte to `char`.

Example of an existing UTF-8 file, reading the whole file when its size **does not exceed a single mapping limit**:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedUtf8Reader {
    public static String read(Path file) throws IOException {
        try (FileChannel ch = FileChannel.open(
                file, StandardOpenOption.READ)) {

            long size = ch.size();
            if (size > Integer.MAX_VALUE) {
                throw new IOException("File too large for one mapping");
            }

            MappedByteBuffer data = ch.map(
                    FileChannel.MapMode.READ_ONLY, 0, size);

            return StandardCharsets.UTF_8.decode(data).toString();
        }
    }
}
```

This is a compilable helper (`MappedUtf8Reader.java`) with no `main` and no stdout output. `StandardCharsets.UTF_8.decode(data)` is a convenience method decoding into a `CharBuffer`; on invalid input, its error handling may substitute replacement characters per the `Charset` contract. If your logic must **reject invalid UTF-8**, use `CharsetDecoder` with `onMalformedInput(CodingErrorAction.REPORT)` and controlled decoding. Because the output returns a `String`, this helper still requires enough RAM for the result, even though byte reading is mapped without copying the whole file into an intermediate `byte[]`.

**Do not** split UTF-8 into arbitrary windows and decode each window independently: a multi-byte sequence can be split across two windows. To process large text in segments, carry decoder state across windows, pass incomplete trailing boundary bytes to the next window, and handle end-of-input/flush per `CharsetDecoder` rules. If you only need sequential text processing, `BufferedReader` or `Channels.newReader` is usually simpler.

## 8. What Do `force()`, `load()`, and `isLoaded()` Do?

### 8.1. `MappedByteBuffer.force()`: requesting writeback of modified regions

`mapped.force()` acts on the byte region of a `READ_WRITE` mapping. In Java 17+, an overload exists:

```java
mapped.force();           // Entire mapped region.
mapped.force(0, 1024);    // Region starting at index 0, length 1024 bytes.
```

The second line is valid only when `mapped.capacity() >= 1024`; both are illustrative code. Indices of `force(index, length)` are within the **mapped buffer**, not whole-file absolute offsets. The implementation may write bytes outside the specified range due to OS block/page granularity.

By contract: if the file resides on a **local storage device**, after `force()` returns successfully, modifications to the `READ_WRITE` mapped region have been written to the device; for non-local devices, no equivalent guarantee exists. `force()` on a `READ_ONLY` or `PRIVATE` mapping **does not** persist edits to the file. `force()` may throw `UncheckedIOException` if a write error occurs.

Do not confuse `mapped.force()` with `channel.force(metaData)`:

| API | Applies to | Primary meaning |
|---|---|---|
| `MappedByteBuffer.force()` | Bytes in the mapping | Requests flushing mapping changes to the device per API conditions |
| `MappedByteBuffer.force(index, length)` | A segment of the mapping | Forces a relative byte slice within the mapping |
| `FileChannel.force(boolean metaData)` | Content updated via the channel; depending on `metaData`, may include metadata | Guarantees per the `FileChannel` contract for file modifications made via the channel |

If writes occur through both `FileChannel.write` and a mapping, read both contracts and establish proper durability conditions for your filesystem and environment. Do not equate flushing a buffer with multi-file transactions or crash-consistency guarantees for multi-step data structures.

### 8.2. `load()` is an effort to preload pages, not `force()`

`mapped.load()` asks the JVM/OS to try bringing mapped data pages into physical memory in advance to reduce page faults during subsequent access.

`mapped.isLoaded()` returns a **hint** indicating whether the pages are resident:

- `true` means it is highly likely the data is resident, **not guaranteed forever**.
- `false` **does not prove** all pages have been evicted from RAM.
- The OS can change residency status right after the call.

Example:

```java
mapped.load();
boolean probablyResident = mapped.isLoaded();
```

This is an illustrative snippet with a valid `mapped` buffer. Do not use `isLoaded()` as a correctness condition or assert "all bytes are definitely in RAM." `load()` can trigger I/O and page faults; only call it before access if benchmarks show it helps.

## 9. Mapping a File Region and Processing Binary Records

Suppose a fixed 12-byte record format consists of:

```text
Relative offset    Size       Field
0                  4 bytes    id (int, LITTLE_ENDIAN)
4                  8 bytes    timestamp (long, LITTLE_ENDIAN)
```

Reading a record via a mapped buffer:

```java
static long readTimestamp(MappedByteBuffer mapped, int recordIndex) {
    final int recordSize = Integer.BYTES + Long.BYTES;
    int base = Math.multiplyExact(recordIndex, recordSize);
    return mapped.getLong(base + Integer.BYTES);
}
```

This is an illustrative snippet inside a class importing `MappedByteBuffer`; the caller must set `mapped.order(ByteOrder.LITTLE_ENDIAN)` and validate `recordIndex` as well as region bounds before calling. `Math.multiplyExact` detects integer overflow when computing offsets, though if the result exceeds `limit`, the operation can still throw `IndexOutOfBoundsException`. Reading a `long` may not be atomic if the file is modified concurrently by another actor.

Distinguish clearly:

- **File offset**: `long`, applied when calling `map`.
- **Buffer index**: `int`, starting from 0 of the mapping.
- **Record offset**: measured in bytes, not field count.
- **Byte order**: on-disk data must have a defined layout matching the `ByteOrder` configured when reading/writing.

If the file is a structured log, beyond `id` and `timestamp` you may also need magic headers, version, length, checksums, commit state, and partial-record handling. Memory mapping only provides byte access; it **does not itself provide** record framing or transactional mechanisms.

## 10. Differences Between `map` and Regular `read`/`write`

| Criterion | `FileChannel.read/write` | `FileChannel.map` |
|---|---|---|
| Access model | Transfers bytes through `ByteBuffer` on I/O calls | Maps file, then accesses bytes via `MappedByteBuffer` |
| Setup cost | Typically small for short sequential I/O | Establishing mappings has overhead; not necessarily good for small files |
| Random access | Positional `read/write` can be used | Convenient via `get(index)` and `put(index, value)` |
| Memory | Explicitly managed buffers | Uses virtual address space and OS pages; does not automatically bring entire file onto Java heap |
| Very large files | Easy to process in read/write chunks | Single mapping limited to `Integer.MAX_VALUE` bytes; typically requires multiple windows |
| Sync & durability | Manage writes and `FileChannel.force` | Manage mappings and `MappedByteBuffer.force` |
| Lifecycle | Closing channel ends channel I/O | Closing channel **does not** automatically destroy the mapping immediately |
| Concurrent changes | Consistency still must be designed | Mapping is sensitive to unexpected external edits; many behaviors are OS-dependent |

Choosing mmap is often helpful when data is large, randomly accessed repeatedly, or naturally viewed as an indexed byte structure. For small text files, single-pass operations, or sequential I/O, `Files.readString`, `BufferedInputStream`, or `FileChannel.read` can be simpler and just as efficient. Measure performance on real workloads instead of treating mmap as always "zero-copy" in the sense of having zero copies or page faults.

## 11. Concurrency, File Modification, and Subtle Risks

### 11.1. A mapped region is not an immutable snapshot

If another process modifies file contents, the mapping may observe changes at OS-dependent times. There is no general guarantee that reading multiple fields forms a logically consistent snapshot. Another thread mutating the same mapped buffer can also introduce data races.

To share data across multiple threads or processes:

- Design an update protocol: e.g., versions, commit states, locks, or appropriate memory-visibility mechanisms.
- Use proper synchronization; merely calling `getInt`/`putInt` on a buffer does not make a multi-field structure an atomic transaction.
- When coordinating across processes, study `FileLock` and OS/filesystem guarantees; locks also have limitations and do not replace format consistency checks.
- Do not mix `READ_WRITE` and `PRIVATE` expecting those views to observe all changes identically.

### 11.2. Do not resize a file underneath an active mapping

Java documentation warns that mapped buffer contents can become **inaccessible** if the file is truncated. Accessing an invalidated region can throw an unspecified exception. Behavior when changing file length or content after mapping is also OS-dependent.

Rule: when using mmap on mutable files, protect file lifecycle and length via ownership/locking policies or versioned formats; avoid `truncate` on files with active mapped access. Never use `catch (RuntimeException)` and silently treat corrupted bytes as valid values.

### 11.3. Mapping does not manage transactions on its own

Suppose a record contains `balance`, `version`, and `checksum`. Writing fields sequentially into a mapping can be observed by another reader **mid-update**. `force()` helps flush modified bytes to the device under contract conditions, but **does not** turn a sequence of edits into an atomic transaction and provides no rollback.

If crash consistency is needed, design update ordering, journaling/WAL, checksums, commit markers, double buffering, or other suitable durability mechanisms. Mmap is a **way to access** bytes in a file, not a transaction manager.

### 11.4. Does a read-only buffer still see file changes?

`READ_ONLY` only forbids writing **through that buffer**. If another actor updates the file on disk, some OSes may reflect those changes into the mapping; Java guarantees neither the timing nor the occurrence of visibility. Therefore, `READ_ONLY` is not a data snapshot and does not replace a private copy when immutability is required.

## 12. Mapping Lifecycle and Releasing Mappings

A difference from regular `FileChannel`: the mapped region represented by `MappedByteBuffer` can remain valid **after the channel used to create it has been closed**. By the Java API, the mapping and buffer remain valid until the buffer is reclaimed by the garbage collector.

```java
MappedByteBuffer mapped;
try (FileChannel ch = FileChannel.open(
        file, StandardOpenOption.READ)) {
    mapped = ch.map(FileChannel.MapMode.READ_ONLY, 0, ch.size());
}
// FileChannel is closed, mapped can still be used per mapping contract.
// However, the map depends on the validity of the underlying file region.
```

This illustrative snippet assumes `file` is valid, the method handles `IOException`, and the file is not adversely altered by another actor. **Do not** infer that closing the channel unmaps, frees virtual address space, or immediately allows deleting the file on every OS.

On Windows in particular, a mapped file can be difficult to delete or rename while the OS still holds the mapping. `MappedByteBuffer` in Java 17/21 **has no public `close()` method** to proactively unmap like `FileChannel.close()`. Attempting to invoke internal JDK APIs to force unmapping depends heavily on JDK version/module access and should not be done by default.

For temporary files, consider designs that do not retain mapping references too long, use best-effort cleanup, and accept that waiting for mapping release may be needed. For applications requiring exact unmap lifecycle control, evaluate official memory-segment APIs suited to your Java version instead of relying on internal cleaners; this article focuses on the widely supported Java 17+ `MappedByteBuffer` API.

### 12.1. Why can't or shouldn't you micromanage the page cache?

The operating system decides when mapped data is paged into RAM and when it is evicted. `load()` is only an attempt, and `isLoaded()` is a hint. Java's `System.gc()` is not the right mechanism to control caching or guarantee immediate unmapping; programs must not depend on GC running at deterministic times.

## 13. Errors and Exceptions to Know

| Situation | Common symptom | How to handle |
|---|---|---|
| `map` with negative offset/size or oversized length | `IllegalArgumentException` | Validate indices/sizes; use windowed mappings |
| Choosing `READ_ONLY` on a channel not open for reading | `NonReadableChannelException` | Open channel with proper permissions |
| Choosing `READ_WRITE` or `PRIVATE` missing read/write permission | `NonReadableChannelException` / `NonWritableChannelException` | Open channel with both `READ` and `WRITE` |
| Writing to a `READ_ONLY` view | `ReadOnlyBufferException` | Use `READ_WRITE` if persistence is intended; check policy |
| `get`/`put` past buffer bounds | `IndexOutOfBoundsException`, `BufferUnderflowException`, or `BufferOverflowException` depending on operation | Check `position`/`limit`/`remaining` and input data |
| I/O failure opening or creating mapping | `IOException` | Check permissions, file state, capacity, and provider |
| `force()` encounters a write error | `UncheckedIOException` | Handle persistence failure; never assume bytes were saved |
| File truncated while mapping is still in use | Unspecified access behavior, may throw exception | Design ownership and avoid resizing files in use |
| Deleting/renaming a mapped file fails | Depends on OS and mapping handle | Manage lifecycle; avoid assuming `close(channel)` = unmap |
| Checking `isLoaded() == false` | Insufficient proof bytes are not in RAM | Do not use this hint for correctness decisions |

Exceptions like `NonReadableChannelException` / `NonWritableChannelException` are unchecked; `IOException` is checked, while errors accessing mapped memory when a file is unexpectedly altered may not match a fixed subtype. Do not collapse all failures into "file does not exist."

## 14. Common Mistakes When Reading/Writing via Mapped Buffers

1. **Assuming `map` immediately reads the whole file onto the heap.** It sets up a mapping; the OS decides page loading.
2. **Assuming `READ_WRITE` means durable writes right after `put`.** File propagation timing may be unspecified; when persistence is needed, use `force` under its contract conditions.
3. **Using `PRIVATE` to edit a file.** This mode is copy-on-write and does not propagate edits back to the file.
4. **Calling `put` on `READ_ONLY`.** Results in `ReadOnlyBufferException`.
5. **Mapping beyond the current file size** expecting the OS to expand it automatically. Behavior past the file extent is not guaranteed by the contract.
6. **Using `truncate(larger)` to grow a file.** `truncate` does not increase size when the target size exceeds the current size.
7. **Mapping an entire file larger than 2 GiB with a single `MappedByteBuffer`.** This overload limits size to `<= Integer.MAX_VALUE`; use windows.
8. **Confusing file offset with mapped index.** Mapping index 0 corresponds to the offset passed to `map`, not necessarily byte 0 of the file.
9. **Confusing `get(index)` with `get()`.** Absolute access leaves `position` unchanged, whereas relative access increments it.
10. **Calling `flip` after only absolute `put` calls**, setting `limit` to 0 if `position` never moved and causing subsequent reads to fail.
11. **Ignoring `ByteOrder` when writing binary structs.** `getInt`/`putLong` follow the buffer's byte order; it must match the file format.
12. **Casting each UTF-8 byte to `char`.** Unicode code points can take multiple bytes; use a charset decoder.
13. **Treating `READ_ONLY` as an immutable snapshot.** File contents can still change concurrently.
14. **Assuming `force()` creates a transaction** or makes multiple updates atomic. No automatic transaction mechanism exists.
15. **Relying on `isLoaded()` for correctness.** It is only a hint, not a guarantee.
16. **Thinking closing `FileChannel` immediately releases the mapping.** Mappings have an independent lifecycle tied to GC.
17. **Retaining many small mappings without managing references.** Consumes address space and OS resources, and can block file deletion.
18. **Resizing a mapped file** without coordinating threads/processes. Can invalidate mapped access regions.
19. **Equating memory mapping with "always faster."** Mapping has setup costs and page faults; performance depends on size and access patterns.
20. **Mixing multiple writers on the same file without a protocol.** Can corrupt consistency even if each individual `put` is valid.

## 15. Self-Check Questions

**1.** What are the initial `capacity` and `position` of the buffer returned by `FileChannel.map(READ_ONLY, 100, 20)`?  
**Answer:** `capacity = 20`, `position = 0`; `mapped.get(0)` corresponds to the byte at file offset 100.

**2.** Why does choosing `PRIVATE` still require write permission on the channel?  
**Answer:** The `FileChannel.map` contract requires a readable and writable channel for both `READ_WRITE` and `PRIVATE`, even though bytes modified in `PRIVATE` are not written back to the file.

**3.** Can you map 3 GiB with Java 17's overload returning `MappedByteBuffer`?  
**Answer:** No; `length` is bounded by `<= Integer.MAX_VALUE`. You must map in windows and handle boundaries.

**4.** Does `mapped.put(0, (byte) 7)` advance `position` from 0 to 1?  
**No.** That is an absolute put. Only relative `mapped.put((byte) 7)` advances `position`.

**5.** When using `READ_WRITE`, what is the purpose of calling `mapped.force()`?  
**Answer:** To request writing mapping modifications to the device; the specific guarantee applies when the file resides on a local device, whereas other systems may not offer the same commitment.

**6.** If `mapped.isLoaded()` returns `false`, is it guaranteed the data is not in RAM?  
**No.** The API only returns a hint; `false` does not prove the opposite.

**7.** Does closing `FileChannel` immediately invalidate every `MappedByteBuffer` created from it?  
**No.** Mappings have an independent lifecycle; conversely, truncating the file can break mapping accessibility.

**8.** Why can't `mapped.force()` replace a multi-field transaction mechanism?  
**Because** `force` pertains to flushing bytes to the device and does not guarantee a group of updates is atomic or supports rollback.

**9.** If `putInt(0, 0x01020304)` is written in little-endian, what are the bytes at indices 0..3?  
**Answer:** `04 03 02 01`.

**10.** Given a UTF-8 Vietnamese text file, can you print `(char) mapped.get(i)` for each byte to get valid text?  
**No.** You need a UTF-8 decoder and must preserve decoding state across byte boundaries, especially for multi-byte characters.

## 16. Key Takeaways and References

**Core principle:** `FileChannel.map` lets you view a file byte region as an indexed `MappedByteBuffer`. `READ_ONLY` is for reading; `READ_WRITE` is for edits propagated to the file; `PRIVATE` is for copy-on-write edits not propagated to the file. Control offsets, mapping sizes, byte order, permissions, `force()`, and mapping lifecycles carefully. Memory mapping improves convenience for certain random-access workloads but does not replace synchronization, transaction, or data-validation mechanisms.

Official Java SE 21 documentation sources:

- `FileChannel.map` and `FileChannel.MapMode` modes: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- `MappedByteBuffer` (`force`, `load`, `isLoaded`, lifecycle): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/MappedByteBuffer.html
- `ByteBuffer` (numeric reads/writes, views, `ByteOrder`): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- `StandardCharsets` and `CharsetDecoder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html and https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
