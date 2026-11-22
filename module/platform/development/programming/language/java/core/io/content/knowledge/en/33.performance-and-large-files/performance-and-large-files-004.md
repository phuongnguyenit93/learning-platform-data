# Comparing Buffered Streams, Files.copy, and FileChannel for Large File Processing

## 1. The Problem to Solve

Copying a file seems simple: read bytes from a source and write bytes to a target. However, for files of hundreds of MB, multiple GB, or a continuously active data stream, API choice affects **code complexity, Java memory allocation, I/O call count, ability to leverage OS optimizations, correctness on failure, and how you test**.

In Java 17+, three groups of approaches are commonly used:

1. **Buffered streams:** `BufferedInputStream` + `BufferedOutputStream`, reading/writing in byte chunks.
2. **High-level API:** `Files.copy(...)`, instructing Java/the provider to copy a file or stream according to option policies.
3. **NIO channel:** `FileChannel`, using `read`/`write` with `ByteBuffer`, or `transferTo`/`transferFrom` to request direct byte transfers between channels.

The most important point:

> **No single API is always fastest in every environment.** `Files.copy` is usually the first choice for simple file copying; buffered streams fit when you need byte stream processing/data transformation; `FileChannel` is useful when you need offsets, range transfers, case-specific I/O optimizations, and progress control. Actual performance must be measured on your specific files, devices, OS, provider, and workload.

This article focuses on **verbatim binary data copying**. If the goal is charset conversion or line-by-line text processing, use `Reader`/`Writer` and a dedicated encoding design; do not convert binary bytes into Strings just to copy them.

### 1.1. High-Level Data Flow

```text
Approach A — buffered streams:
Disk/FileSystem → InputStream → [byte buffer] → application code
                                → [byte buffer] → OutputStream → Disk/FileSystem

Approach B — Files.copy:
Source Path ───── Files.copy(source, target, options) ─────→ Target Path
                    provider may choose implementation mechanism

Approach C — FileChannel:
Source FileChannel → transferTo / transferFrom → Target Channel
       or
Source FileChannel → ByteBuffer → Target FileChannel
```

These diagrams describe **API layers**, not a promise of how many RAM copies, syscalls, or DMA transfers happen underneath. Even mechanisms called "zero-copy" are subject to OS, filesystem, provider, device, and target channel conditions.

## 2. Quick Comparison Table

| Criterion | BufferedInputStream/BufferedOutputStream | `Files.copy` | `FileChannel` |
|---|---|---|---|
| Abstraction level | Byte stream read/write | High-level file/path or single-ended stream copy | Channel byte access with position, size, transfer |
| Code to write | `read/write` loop and EOF handling | Usually a single call | Transfer loop or ByteBuffer read/write loop |
| Application memory | Fixed-size temp array/buffer | Decided by implementation; does not require caller to hold entire file | A reused `ByteBuffer`, or transfer with provider/OS-chosen buffers |
| Offset control | Must skip/position via appropriate source API | No offset parameter for `Files.copy(Path,Path)` | Explicit via `position` and positional `read/write`/`transferTo` |
| Copy file to file | Possible, though more code | **Default to consider first** | Possible, useful when fine-grained control is needed |
| Copy a file slice | Possible, must bound manually | Not the goal of the Path→Path overload | Convenient via `transferTo(start,count,...)` |
| Native transfer/zero-copy | No guarantee of eliminating user-buffer copies | Depends on provider/implementation | `transferTo` may use OS optimization, **not guaranteed** |
| File attributes | Handle metadata manually | Supports `COPY_ATTRIBUTES` when supported | Does not copy metadata merely by transferring content |
| Very large files | Chunked processing, no need to hold full file | Designed for ordinary file copying | `size` and offset use `long`; loop handles partial transfers |
| Error handling/cleanup | Full manual control | Concise, yet partial target can still exist on failure | Must track transferred bytes and stop on no progress |
| Power-loss durability | Not guaranteed automatically | Not guaranteed automatically | Not guaranteed automatically; `FileChannel.force` has its own scope |

**Choose the API by requirements first, optimize later.** Copying a 3 MB image differs from streaming slices of a multi-hundred-GB log to a socket, or cloning thousands of small files with metadata.

## 3. Buffered Streams: Reading and Writing in Chunks

### 3.1. How It Works

Calling `InputStream.read()` byte-by-byte can cause many transitions across I/O layers. `BufferedInputStream` batches read data into an internal buffer; `BufferedOutputStream` batches small writes before passing them to the underlying stream.

A chunked copy without reading the whole file:

```java
try (InputStream in = new BufferedInputStream(Files.newInputStream(source));
     OutputStream out = new BufferedOutputStream(
             Files.newOutputStream(
                     target,
                     StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE))) {

    byte[] chunk = new byte[64 * 1024];
    int n;

    while ((n = in.read(chunk)) != -1) {
        out.write(chunk, 0, n);
    }
}
```

This is an **in-method snippet handling `IOException`**, assuming `source` and `target` are resolved `Path`s, with imports `java.io.*`, `java.nio.file.Files`, and `StandardOpenOption`. It illustrates the main control flow; the complete example appears in Section 7.

Meaning:

- `chunk` is a 64 KiB buffer allocated once by the caller.
- `read(chunk)` returns the **actual** number of bytes read, not necessarily 64 KiB.
- `-1` denotes EOF; when `n` bytes are read, only `chunk[0..n-1]` are valid for that round.
- `out.write(chunk,0,n)` writes the exact byte count read; omitting `n` can duplicate trailing data from the previous round.
- `try-with-resources` closes the streams even on error; closing the buffered output flushes remaining bytes from the Java buffer before closing the underlying output.
- `CREATE_NEW` prevents accidentally overwriting an existing target path; if the target exists, opening fails per contract.

### 3.2. Both Buffered Streams and the Passed Array Can Act as Buffers

In the example, there are **three levels** involving memory:

1. Internal buffer of `BufferedInputStream`.
2. The 64 KiB `byte[] chunk` array reused by the application.
3. Internal buffer of `BufferedOutputStream`.

Because the application already reads and writes in 64 KiB chunks, wrapping with two `Buffered*Stream`s sometimes **brings no clear benefit** over `Files.newInputStream`/`newOutputStream` with the same large array. Buffered wrappers are especially helpful when upstream logic calls `read/write` many times with small blocks.

Do not conclude "more buffer layers means faster". Extra memory, extra copies across layers, and flush patterns can alter performance. **Benchmark both with and without wrappers** if optimizing throughput is the goal.

### 3.3. Choosing Buffer Size

Values like 8 KiB, 32 KiB, 64 KiB, 256 KiB, or 1 MiB are only **benchmark candidates**, not universal answers. Too small a buffer typically increases I/O call counts; too large a buffer can increase memory footprint, cache/memory pressure, and per-worker allocations.

In a copy loop, application-held buffer memory is **O(B)** where B is buffer size, while file size can exceed RAM. If 100 concurrent workers each hold a 1 MiB array, temporary arrays alone consume around 100 MiB excluding buffers, queues, and runtime overhead.

Note that `InputStream.read(byte[])` returns partial data depending on source state. Never assume a single read corresponds to one file block, one record, or one TCP message.

### 3.4. `flush()`, `close()`, and Durability

`out.flush()` requests pushing buffered bytes down to the underlying output layer. `close()` on buffered output flushes and then closes the underlying stream. However:

- `flush()` **does not mean** data is fsynced to the device.
- `close()` **does not automatically guarantee** the file survives power loss on every filesystem.
- If strong durability is needed, you must design explicit sync/force and usually safe target publication.
- If an `IOException` occurs midway, the target file may already contain **partial** content and must not be treated as a complete copy.

Data might have been read 100% accurately yet writing to target failed or the disk filled up; code must still propagate the exception and handle target state.

## 4. `Files.copy`: Direct Approach for File Copy Operations

### 4.1. Path → Path Overloads

Simple example:

```java
Path source = Path.of("data.bin");
Path target = Path.of("backup.bin");

Files.copy(source, target);
```

This is an illustrative snippet inside a method handling `IOException` with `Path`/`Files` imported. By contract, if `target` already exists, it defaults to throwing `FileAlreadyExistsException`. To explicitly permit replacement:

```java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

`REPLACE_EXISTING` changes the policy when target exists; it **does not** make the entire copy atomic. To also preserve metadata when supported:

```java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);
```

These snippets sit inside a method handling `IOException`, using `java.nio.file.*` types. `COPY_ATTRIBUTES` requests copying file attributes, yet which attributes are copied and their precision depend on the filesystem/provider. Never assume all ACLs, owners, extended attributes, and timestamps are preserved identically across every OS.

**Major advantage:** short, readable code, fewer chances of loop/EOF bugs, and lets the provider optimize the copy path. If you simply need to copy a normal file, this is usually the first API to try.

### 4.2. Do Not Assume the Implementation of `Files.copy`

Calling `Files.copy(Path,Path)` **does not promise** that Java always uses:

- A specific `BufferedInputStream`;
- A fixed-size buffer;
- A specific `sendfile` / `copy_file_range` syscall;
- Zero-copy in every case;
- The same optimization strategy across OSes/JDKs/providers.

`Files.copy` defines **API-level behavior**, whereas execution depends on implementation, file type, permissions, filesystem, and environment. Performance observations must be tied to the tested JDK version and platform.

### 4.3. `Files.copy` Is Not an Atomic Transaction

Java documentation does not guarantee the overall copy operation executes atomically. When an I/O error occurs, the target file may exist with incomplete data. Do not copy directly to a critical target path and assume readers will never see an in-progress version.

A common pattern when updating a critical file:

```text
source
  │
  └── Files.copy(...) → staging file in the same directory as target
                              │
                              ├── verify length/checksum/conditions
                              ├── sync staging file if durability required
                              └── publish via atomic rename if supported
                                           │
                                           └── sync directory per platform if crash durability needed
```

Distinguish clearly: `Files.copy` does not automatically execute all these steps. `Files.move(..., ATOMIC_MOVE)` only carries a specific contract for atomic move when supported; it **does not automatically mean** the directory entry is durable after power loss. Replacing an existing target with `ATOMIC_MOVE` also depends on implementation and must not be assumed identical across providers.

### 4.4. Overloads Involving InputStream and OutputStream

`Files` also provides two convenient overloads:

```java
long n1 = Files.copy(inputStream, target,
        StandardCopyOption.REPLACE_EXISTING);

long n2 = Files.copy(source, outputStream);
```

This snippet is **illustrative** with open `inputStream`/`outputStream`, `Path` `source`/`target`, and caller handling `IOException`. Both overloads return a `long` count of copied bytes.

Differences from Path→Path:

- `Files.copy(InputStream, Path, ...)` reads from the stream and creates/writes target.
- `Files.copy(Path, OutputStream)` reads the file and writes bytes to the output stream.
- Both overloads **do not close the caller-supplied stream**; the owner must manage `close`/`flush`.
- `Files.copy(Path,Path,...)` returns the **target `Path`**, not a byte count. If you need byte count, use `Files.size` before/after or copy through an API returning byte count per contract.
- Though sharing the name `copy`, options and attribute semantics differ by overload; check the exact signature you invoke.

Never try passing `COPY_ATTRIBUTES` to the `InputStream→Path` overload as if it could copy file metadata from a stream that has no path or equivalent file attributes.

## 5. `FileChannel`: Processing with `ByteBuffer`

`FileChannel` belongs to Java NIO, providing file position, size, random access, and transfer operations. It fits when copying ranges or integrating with channel pipelines.

### 5.1. Manual Copy with `read`/`write`

A channel copy loop can look like:

```java
try (FileChannel in = FileChannel.open(source, StandardOpenOption.READ);
     FileChannel out = FileChannel.open(target,
             StandardOpenOption.CREATE_NEW,
             StandardOpenOption.WRITE)) {

    ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);

    while (in.read(buffer) != -1) {
        buffer.flip();
        while (buffer.hasRemaining()) {
            out.write(buffer);
        }
        buffer.clear();
    }
}
```

This is an **illustrative snippet in a method handling `IOException`**, with valid `source`/`target` and imports `FileChannel`, `ByteBuffer`, `StandardOpenOption`. To guard against unusual providers where a `read`/`write` round reports prolonged zero progress, production code should track byte counts and apply a retry/break policy instead of spinning endlessly.

**Mandatory ByteBuffer rules:**

1. Initially `position=0`, `limit=capacity`, ready to receive bytes.
2. `in.read(buffer)` places bytes into the region from position to limit; position advances by the amount read.
3. `buffer.flip()` sets limit to the written position and resets position to 0 for draining bytes.
4. `out.write(buffer)` can write **fewer** than remaining bytes; use `while(buffer.hasRemaining())`.
5. `buffer.clear()` prepares the buffer for a new round; **does not erase physical bytes** in the buffer, only resets cursors.

Omitting `flip()` can write stale bytes or the wrong range. Forgetting `clear()` leaves the buffer with no write space. Calling `out.write(buffer)` only once and assuming all `remaining()` bytes were written can truncate the target file.

### 5.2. Is `allocateDirect` Always Better Than `allocate`?

No. `ByteBuffer.allocateDirect(n)` uses a direct memory region, which can be convenient for native channel I/O; `ByteBuffer.allocate(n)` uses a standard heap buffer. Performance differences depend on transfer size, JDK, GC, CPU, OS, and memory pressure.

Direct buffers have their own allocation cost and lifecycle—they are not "free RAM". **Allocate once and reuse** across the copy loop rather than calling `allocateDirect` on every iteration. For very small jobs, a heap buffer may be simpler and fast enough.

### 5.3. Loops Must Handle Partial Writes

`FileChannel.write(ByteBuffer)` returns the actual number of bytes written. Even for synchronous file channels, the contract does not promise all `remaining()` bytes are written in one call. Therefore:

```java
while (buffer.hasRemaining()) {
    int n = targetChannel.write(buffer);
    if (n <= 0) {
        throw new IOException("Target did not make progress");
    }
}
```

This illustrative snippet assumes `targetChannel` is open for writing and `buffer` holds bytes to send. If a real environment requires tolerating temporary `n=0`, design explicit retry/backoff/timeout logic; never spin endlessly.

## 6. `FileChannel.transferTo` and `transferFrom`

### 6.1. `transferTo(position,count,target)`

Example:

```java
long copied = sourceChannel.transferTo(
        offset, requestedBytes, targetChannel);
```

This is a snippet with `sourceChannel` of type `FileChannel` open for reading and a valid `WritableByteChannel targetChannel`. Meaning:

- `offset` is the **byte position in the source file**, of type `long`.
- `requestedBytes` is the **maximum bytes to transfer** in this call, of type `long`.
- `copied` is the **actual bytes transferred** in that round, which may be less than requested.
- The file position of the **source FileChannel** is not modified by `transferTo` because the offset is passed explicitly.
- If the target channel tracks a position, bytes are written starting at the **target's** current position, and the target position advances accordingly.

**Never conclude** that one call `transferTo(0, source.size(), target)` always transfers the whole file. The provider/OS may cap single-call transfer size, the target may not accept everything, or conditions may cause the method to return 0.

### 6.2. Loop for Large Files

Common pattern:

```java
long size = sourceChannel.size();
long position = 0L;

while (position < size) {
    long n = sourceChannel.transferTo(
            position, size - position, targetChannel);

    if (n <= 0) {
        // Must not spin the exact same loop forever.
        throw new IOException(
                "No progress at file offset " + position);
    }

    position += n;
}
```

This snippet is **illustrative inside a method**; `sourceChannel` and `targetChannel` are already open. It detects and fails when transfer makes no progress; depending on the use case, you may fall back to a read/write approach for the remainder.

### 6.3. Why Might It Return 0 or Fewer Bytes?

Several situations:

- Requested region reaches EOF; if offset is miscalculated, no bytes remain to transfer.
- Target channel cannot accept more bytes right now (especially non-blocking targets).
- Native transfer mechanism is capped by the OS or provider.
- Source file changed size mid-copy.
- Any implementation limit causing bytes transferred per call to be fewer than requested.

Handling this cannot just be `while(n==0) continue` forever. You can fall back to `FileChannel.read(ByteBuffer,offset)` followed by `target.write(ByteBuffer)` with progress control, or fail explicitly for the caller to handle.

### 6.4. `transferFrom` Transfers in the Opposite Direction

```java
long n = targetFileChannel.transferFrom(
        readableSourceChannel, fileOffset, maxBytes);
```

This snippet assumes `targetFileChannel` is a `FileChannel` open for writing and `readableSourceChannel` is a `ReadableByteChannel`. `transferFrom` transfers bytes from the **source** into the target `FileChannel` starting at the specified offset.

Note position behavior differs from `transferTo`:

- `transferFrom` passes the **target file's position** explicitly; the current position of the target `FileChannel` does not change.
- If the source channel tracks position, source position can advance as bytes are read.
- Actual result can also be less than `maxBytes`; you still must plan a loop and progress handling.
- A socket/pipe source differs from a file, having its own readiness and EOF semantics; file-to-file assumptions cannot be applied blindly to non-blocking networking.

### 6.5. "Zero-Copy" Is a Capability, Not an API Guarantee

On specific OS/file/channel combinations, `transferTo` can use a native transfer path reducing data copies through user space or syscall counts. However, the Java API **does not guarantee that every `transferTo` will always be zero-copy**.

Do not assume:

- Definitely no data is copied in RAM/OS.
- Definitely no page cache is used.
- Definitely no CPU overhead or context switches occur.
- Definitely faster than buffered streams for small files.
- Definitely identical semantics on Windows, Linux, macOS, and network filesystems.

That `FileChannel` lets providers implement optimizations is a **potential advantage**. To confirm real effectiveness, measure on the actual deployment combination.

## 7. Runnable Java 17+ Example: Three Copy Approaches and Byte Verification

The following standalone example:

- Creates a dedicated directory and a source file of **131,075 bytes** (intentionally not divisible by 64 KiB).
- Copies using buffered streams.
- Copies using `Files.copy(Path,Path)`.
- Copies using `FileChannel.transferTo`, with fallback to `read/write(ByteBuffer)` if transfer makes no progress.
- Compares bytes via `Files.mismatch` (Java 12+, available in Java 17+).
- Cleans up its own files without touching user files.

**File:** `CopyStrategiesDemo.java`

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.stream.Stream;

public class CopyStrategiesDemo {

    private static long copyBuffered(Path source, Path target)
            throws IOException {

        long bytesCopied = 0;

        try (InputStream in = new BufferedInputStream(
                    Files.newInputStream(source));
             OutputStream out = new BufferedOutputStream(
                    Files.newOutputStream(
                            target,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE))) {

            byte[] chunk = new byte[64 * 1024];
            int n;

            while ((n = in.read(chunk)) != -1) {
                out.write(chunk, 0, n);
                bytesCopied += n;
            }
        }

        return bytesCopied;
    }

    private static long copyWithChannel(Path source, Path target)
            throws IOException {

        try (FileChannel in = FileChannel.open(
                    source, StandardOpenOption.READ);
             FileChannel out = FileChannel.open(
                    target,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {

            long size = in.size();
            long position = 0L;
            ByteBuffer fallback = ByteBuffer.allocateDirect(64 * 1024);

            while (position < size) {
                long moved = in.transferTo(
                        position, size - position, out);

                if (moved > 0) {
                    position += moved;
                    continue;
                }

                // Native transfer made no progress:
                // read the exact remaining slice using positional read.
                fallback.clear();
                fallback.limit((int) Math.min(
                        (long) fallback.capacity(),
                        size - position));

                int read = in.read(fallback, position);
                if (read <= 0) {
                    throw new IOException(
                            "Cannot make progress at " + position);
                }

                fallback.flip();

                while (fallback.hasRemaining()) {
                    int written = out.write(fallback);

                    if (written <= 0) {
                        throw new IOException("Target stalled");
                    }
                }

                position += read;
            }

            return position;
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory(
                "copy-strategies-");

        try {
            Path source = directory.resolve("source.bin");

            byte[] data = new byte[131_075];
            for (int i = 0; i < data.length; i++) {
                data[i] = (byte) (i * 31 + 7);
            }

            Files.write(source, data);

            Path buffered = directory.resolve("buffered.bin");
            Path filesCopy = directory.resolve("files-copy.bin");
            Path channel = directory.resolve("channel.bin");

            System.out.println(
                    "source bytes: " + Files.size(source));

            System.out.println(
                    "buffered bytes: "
                    + copyBuffered(source, buffered));

            Files.copy(source, filesCopy);

            System.out.println(
                    "Files.copy equal: "
                    + (Files.mismatch(source, filesCopy) == -1));

            System.out.println(
                    "channel bytes: "
                    + copyWithChannel(source, channel));

            boolean same =
                    Files.mismatch(source, buffered) == -1
                    && Files.mismatch(source, filesCopy) == -1
                    && Files.mismatch(source, channel) == -1;

            System.out.println("all equal: " + same);

        } finally {
            // Only clean up files created inside the demo directory.
            try (Stream<Path> entries = Files.list(directory)) {
                for (Path entry : entries.toList()) {
                    Files.deleteIfExists(entry);
                }
            }
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run on JDK 17+:

```bash
javac CopyStrategiesDemo.java
java CopyStrategiesDemo
```

**Expected stdout when a normal filesystem operates properly:**

```text
source bytes: 131075
buffered bytes: 131075
Files.copy equal: true
channel bytes: 131075
all equal: true
```

### 7.1. Explaining Choices in the Demo

- Uses **deterministic** byte data instead of Random so stdout/comparisons are reproducible.
- `131_075` is not divisible by `65_536`; the final read has only 3 bytes after two full blocks, testing that code does not write extra stale bytes.
- `CREATE_NEW` requires the target file not to exist and prevents accidental overwriting.
- `Files.copy` is called without options because the target is a new path.
- `Files.mismatch(a,b)` returns `-1` when all bytes and lengths match; useful for verifying copied files **at read time**, not a hash or proof of survival after power loss.
- The channel helper initializes `position=0` and transfers until reaching `size`. If `transferTo` makes no progress, it uses positional `read` into a reused direct buffer and writes all bytes to the target `FileChannel`.
- Since no other thread modifies source/target in the demo, tracking `position` and file size is stable. **In systems with concurrent writers**, separate snapshot/stability guarantees are needed.
- `finally` cleans up only files inside **the demo-created temporary directory**. If an earlier step fails, cleanup itself might throw IOException; real applications need logging/retention policies for failed files depending on recovery needs.

### 7.2. Why Not Print "Benchmark" Milliseconds?

Copy speed is affected by page cache, filesystem state, and machine load. Printing `System.nanoTime()` once and labeling "API X is fastest" is not a universally valid conclusion. The example intentionally verifies only **correctness** via byte counts and `Files.mismatch`. Performance measurement is explained separately below.

### 7.3. Why Doesn't the Channel Fallback Call `read`/`write` Concurrently with an Active Transfer?

`FileChannel.transferTo` is synchronous for this call: it has already returned the transferred byte count (or 0) before fallback begins. In the demo, no pending asynchronous transfer holds the buffer; fallback reads from the exact remaining `position` and sends to the current output.

**Prerequisite:** neither source nor target is modified by another thread, and the output channel is newly opened at position 0. If using `transferTo` to a non-blocking socket, you must add dedicated readiness/backpressure handling rather than copying this file-to-file fallback loop verbatim.

## 8. Files Larger Than 2 GiB: Use `long`, Process in Parts

Very large files cannot be represented by a single `byte[]` exceeding JVM array length limits, and `ByteBuffer` uses `int` for `capacity`/`position`. However, `FileChannel.size()`, positional offsets, and `transferTo`/`transferFrom` parameters use `long`.

Therefore:

- Never cast `channel.size()` to `int` when a file can exceed 2 GiB.
- Never call `Files.readAllBytes` just to copy a multi-gigabyte file: it can fail from array limits or heap exhaustion.
- Use a bounded buffer and a loop so memory does not grow with file size.
- Compute offsets in `long`, checking for overflow when adding `position + n`.
- Avoid casting `(int)(size - position)` if the remainder can exceed `Integer.MAX_VALUE`. Only cast after clamping with `Math.min(remaining, (long) buffer.capacity())`.
- With `transferTo`, do not assume "a `long` count means the OS transfers terabytes in one syscall"; always loop on the actual returned value.

### 8.1. Splitting a Copy into Logically Sized Segments

For example, capping each transfer request at 64 MiB:

```java
long offset = 0L;
long size = sourceChannel.size();
long maxChunk = 64L * 1024 * 1024;

while (offset < size) {
    long requested = Math.min(maxChunk, size - offset);
    long n = sourceChannel.transferTo(
            offset, requested, targetChannel);

    if (n <= 0) {
        throw new IOException("No transfer progress at " + offset);
    }

    offset += n;
}
```

This is an **illustrative in-method snippet**, with two already-open channels. 64 MiB is a reference size, not a mandatory Java limit. If the source changes concurrently, `size` may no longer reflect the true end of file, so decide whether to copy an **initial snapshot** or follow changes via a dedicated protocol.

### 8.2. Copying a Region of a File

`FileChannel` is convenient when you only need bytes `[start, start+length)`:

```java
long start = 1_048_576L;
long length = 4_194_304L;
long copied = 0L;

while (copied < length) {
    long n = sourceChannel.transferTo(
            start + copied,
            length - copied,
            targetChannel);

    if (n <= 0) {
        throw new IOException("Could not copy requested region");
    }

    copied += n;
}
```

This is an in-method snippet assuming the requested byte region exists completely in source and target is at the right position. If the file is smaller than `start+length`, never treat a short copy as success; verify `size`/source integrity appropriately and handle EOF.

### 8.3. When Copying Many Files, Metadata and Directory Trees Also Matter

`Files.copy` from one Path to another **does not recursively copy an entire directory tree with contents** if source is a directory; when copying a directory, behavior only creates/copies the directory entry or attributes per contract, while inner entries must be handled separately. Copying a tree requires traversal logic, symlink/cycle handling, file permissions, metadata, and per-file error handling.

Also never mistake one `Files.copy` call for an incremental backup solution: it does not compute diffs, versions, deduplication, historical checksums, or tree-wide transactions.

## 9. Performance: Reading Measurements Properly

### 9.1. Throughput and Latency Measure Different Dimensions

- **Throughput:** bytes copied successfully per second, e.g., MiB/s.
- **Latency:** time from starting a copy until the API completes for one file.
- **Tail latency:** p95/p99 across many files/jobs, critical for request-serving systems.
- **Memory footprint:** heap/direct memory/temporary buffers per operation.
- **CPU utilization:** CPU consumed during copying.
- **Syscall count/context switching:** sometimes clarifies the benefit of buffering/transfers.
- **Durability time:** if `force`/sync is required, measure that part too—not just time to write into cache.

An API with high throughput on one 20 GB file may perform poorly on millions of 1 KiB files due to open/close overhead, metadata lookups, and scheduling. Conversely, `Files.copy` may already exploit provider optimizations that a hand-written loop cannot beat.

### 9.2. Memory and I/O Call Frequency

A `read(chunk)` loop with `chunk.length = B` needs roughly `ceil(fileSize/B)` reads if every read is full, **but in practice may need more** due to partial reads. Write counts likewise depend on partial writes and buffering.

Illustrative calculation: a 1 GiB file with 64 KiB chunks corresponds to 16,384 chunks if all except possibly the last are full. This is only an **estimated chunk count**, not the exact OS syscall count, because buffering layers, providers, and native transfers may behave differently.

What matters is **never calling byte-by-byte `read()`/`write()`** when copying large files unless specifically required; plan an appropriate buffer strategy and measure.

### 9.3. Page Cache Makes Benchmarks Easy to Misread

On a typical filesystem, the OS has a page cache and read-ahead. If you run:

```text
Run 1: buffered copy
Run 2: Files.copy
Run 3: FileChannel
```

then runs 2 and 3 may benefit from source data already sitting in cache, leading to a biased conclusion that "later approaches are faster".

Confounding factors:

- Warm/cold cache of the OS and JVM.
- Antivirus/indexing/background I/O.
- SSD/HDD/NVMe, network mounts, filesystem compression/deduplication.
- Intra-filesystem copy capability versus copying across two devices.
- Direct buffer allocation and GC.
- File size/count, buffer size, concurrent worker count.
- Sync/durability options and true device speed.
- Sparse files, symlinks, and file attributes.

### 9.4. A More Meaningful Benchmarking Process

1. **Define the workload:** small files, 100 MB, 5 GB; single file or many files; same volume or cross-volume; sequential or chunked.
2. **Define identical semantics:** all three approaches copy identical bytes and handle overwrite/attributes/flush identically when required.
3. **Warm-up:** run multiple iterations for JIT and system stability; never treat the first run as the final result.
4. **Vary execution order:** alternate strategies to mitigate cache effects.
5. **Repeat multiple samples:** take median and distribution, recording JDK/OS/filesystem/media details.
6. **Verify correctness:** size, `Files.mismatch`, or checksum in appropriate tests. Never report throughput of a copy missing bytes.
7. **Separate copy time from verify time:** re-reading the entire file for `mismatch` has cost; report both metrics separately.
8. **Measure memory/CPU when needed:** use a profiler, JFR, or appropriate OS tools, not just `nanoTime`.
9. **Test failure scenarios:** disk full, permission errors, existing target, source deleted/modified, disconnected network filesystem.
10. **Scope conclusions accurately:** "on this test machine and file type", never claiming one API is fastest for every JVM.

`System.nanoTime()` is suitable for measuring a single interval in a controlled test; for very short microbenchmarks, use a framework like JMH and watch out for OS I/O effects since JMH does not eliminate cache/device factors.

### 9.5. Simple Measurement Snippet, Not Claiming a Standard Benchmark

```java
long startNanos = System.nanoTime();

Files.copy(source, destination);

long elapsedNanos = System.nanoTime() - startNanos;
long byteCount = Files.size(destination);

double seconds = elapsedNanos / 1_000_000_000.0;
double mibPerSecond = seconds > 0
        ? (byteCount / 1_048_576.0) / seconds
        : Double.POSITIVE_INFINITY;
```

This is an **illustrative snippet** inside a method handling `IOException`; `source`/`destination` are `Path`s, and destination does not exist yet. It has no fixed stdout, excludes verification, and does not prove durable persistence. Never extrapolate a single MiB/s number from this snippet to another environment.

## 10. Correctness: How Do You Verify a Copy?

A "successful" file copy must clearly define what is preserved:

| Requirement | How to Verify |
|---|---|
| Exact byte contents | `Files.mismatch(source,target)==-1` when neither changes during inspection |
| Equal size | `Files.size(source)==Files.size(target)`, necessary but not sufficient |
| Modification time, permissions, owner | Read `BasicFileAttributes` or appropriate view; copy metadata explicitly |
| No overwriting existing data | `CREATE_NEW` or default `Files.copy` when target exists |
| Intentional overwrite allowed | `REPLACE_EXISTING` for `Files.copy` or corresponding open options |
| Crash durability | Design `force`/sync, staging, and publish per OS/filesystem |
| Copy from a consistent version | Snapshots, lock/protocol, version/checksum, or equivalent storage mechanism |
| Path security | Validate/canonicalize at trust boundaries, handle symlinks and permissions |

`Files.mismatch` returns **the position of the first differing byte** or `-1` if identical; if file sizes differ, it returns the first position where the shorter file has no more bytes. It is not a cryptographic hash and does not detect or resolve races when source/target can be modified concurrently.

### 10.1. Why Is Equal Size Not Enough?

Two 1 MB files can differ in every single byte. Checking only `Files.size` misses out-of-order copying, stale buffer writes, or offset bugs. `mismatch` or an appropriate checksum verifies contents in tests.

Conversely, if a file has critical metadata, matching bytes alone do not guarantee the target has the right permissions, attributes, or link semantics.

## 11. Files Being Modified Mid-Copy

None of the three approaches automatically creates a **transactional snapshot** of a source file being edited by another writer.

Suppose:

```text
T0: source.bin = version A
T1: copy reads first half of version A
T2: another writer modifies second half to version B
T3: copy reads second half of version B
T4: target may be a mix of A/B
```

Even when `Files.copy` succeeds, target data might not correspond to any single logical point in time. When consistency matters:

- Pause the writer or use a locking/coordination protocol among **cooperating** parties.
- Use filesystem/storage snapshots if available and verified.
- Design copies from versioned **immutable files**; write new versions separately and publish pointers afterward.
- Record checksum/version on publication and validate after copying; re-check source if policy requires.
- Never assume `FileLock` provides full transactions across all processes or on every filesystem; semantics vary by OS/provider.

### 11.1. A Byte-Stream Copy Knows Nothing About Business File Structure

For database files, WALs, multi-file logs, or structures updated in multiple steps, simply copying bytes while the service runs can yield an inconsistent logical snapshot. Use the official backup/snapshot API of that storage engine or an application-consistent backup procedure instead of blindly copying live-mutating files.

## 12. Overwrite, Symlinks, and Metadata

### 12.1. Copying a New File Differs from Updating an Existing File

`Files.copy(source,target)` by default does not replace an existing target. `Files.copy(source,target,REPLACE_EXISTING)` requests replacing target if permitted. However, replacing target **is not atomic publication**; readers may observe inconsistent states while copying is in progress or fails.

When copying via buffered streams/channels, open options:

- `CREATE_NEW`: create new and fail if file already exists.
- `CREATE`: create if absent; does not imply truncate without the corresponding option.
- `TRUNCATE_EXISTING`: truncate when opened for writing and file exists per contract.
- `APPEND`: append to end, **not overwrite copy from the start**.

Apply appropriate policies; never combine `APPEND` carelessly with copying verbatim into an empty file.

### 12.2. Symlinks and Paths

With `Files.copy(Path,Path)`, if source is a symbolic link, default behavior usually **follows the link** and copies the referenced target's contents; `LinkOption.NOFOLLOW_LINKS` can be used to copy the link itself per provider contract.

```java
Files.copy(
        source,
        target,
        LinkOption.NOFOLLOW_LINKS);
```

This is an illustrative snippet in a method handling `IOException`; symlink creation/copying behavior and permission support depend on filesystem/provider. If paths are user-supplied and the program holds elevated privileges, validate against path traversal, symlink races, and allowed directories before operating. Checking `Files.exists` followed by a separate write **is not** a complete race barrier; use atomic creation options and appropriate OS policies when needed.

### 12.3. Copying Attributes and Permissions

`StandardCopyOption.COPY_ATTRIBUTES` applies to the `Files.copy(Path,Path)` overload; preserved attributes depend on provider and filesystem. Across some source/target pairs, permissions, owner, ACLs, extended attributes, timestamp precision, or creation time may differ.

When doing backups, metadata can be as critical as content; list mandatory attributes and verify after copying. Never benchmark a content-only copy and compare it against one that also copies permissions/metadata without explicitly noting the difference.

## 13. File Durability After Copying

**"Method returned successfully" does not automatically mean "the file survives power loss".** Filesystems and OSes can buffer data. APIs:

- `BufferedOutputStream.flush()`: pushes bytes from the Java buffer to the underlying stream; does not fsync by default.
- `Files.copy`: not a durability sync command with a universal contract across all devices.
- `FileChannel.force(false)`: requests flushing content changes within API scope.
- `FileChannel.force(true)`: requests flushing content and metadata within API scope; stronger guarantee on local storage devices subject to contract conditions.
- `Files.move(...,ATOMIC_MOVE)`: when supported, guarantees atomicity of the move operation, **not** crash durability.
- Syncing the parent directory entry after rename: OS/provider-dependent and may require platform APIs beyond portable Java SE.

If a copy will replace a critical configuration file, the design typically looks like:

```text
create temp file in the same directory
        │
        ▼
copy all bytes into staging
        │
        ▼
verify copy (size/checksum/schema)
        │
        ▼
force/sync staging when durability required
        │
        ▼
atomic rename if provider supports it
        │
        ▼
sync directory per platform contract if crash consistency needed
        │
        ▼
only confirm commit at the level truly guaranteed
```

Do not assume `FileChannel.force(true)` on staging before rename also syncs **the directory entry after rename**. For critical data, establish backup/recovery policies and test failure modes on real storage.

## 14. Error Handling and Cleanup When Copy Fails

Situations to plan for:

| Situation | Risk | Handling Approach |
|---|---|---|
| Source missing | `NoSuchFileException` or IOException | Never create a dummy empty copy claiming success |
| Target already exists | `FileAlreadyExistsException` under default/CREATE_NEW | Decide overwrite policy explicitly |
| Disk full/quota | Target may be partially written | Clean up staging/target per policy, do not publish |
| Permission denied | Cannot open/write file | Check permissions, return clear error |
| Source file changes size | Short copy or mixed versions | Locks/snapshots/immutable versions |
| `transferTo` returns 0 with bytes left | Non-advancing loop, spin risk | Fall back or fail |
| `write(ByteBuffer)` writes partially | Data truncation | Loop until `remaining()` is empty |
| Source and target are same file | Can overwrite/truncate source itself | Validate identity; avoid copying onto source |
| Cross-volume/FS I/O | Different speed and semantics | Benchmark/verify correctness on real target pair |
| Process killed abruptly | Incomplete file | Copy to staging, recovery state, and cleanup |

If copying to a temp file fails, never rename the temp file to target. Cleanup depends on business rules: either delete staging immediately, or retain partial copy for resume with checksum/chunk-map validation. Never mark a target file "completed" merely because it exists.

### 14.1. Timeouts and Cancelling a Copy

For huge files or copies over network filesystems, an operation can take a long time. Hand-written buffered stream/channel loops can check a cancellation flag between chunks, though blocking I/O calls might not return immediately when the flag changes.

High-level `Files.copy` does not directly provide per-block progress callbacks on the Path→Path overload. If you need UI progress or per-chunk cancellation, managing chunks/byte counts manually via streams/channels may fit better.

Never report "100%" progress before flush/close/verify per your product's definition of completion. Where durability is required, "bytes transferred" and "commit durable" are two separate milestones.

### 14.2. Logging and Metrics

For large copy jobs, record:

- Verified source size, job name, or safe ID.
- Bytes transferred, duration, measured throughput with environment labels.
- Actual API/strategy used and whether fallback occurred.
- Error classification: permissions, disk full, source truncated, target stalled, checksum mismatch.
- State: STARTED / COPYING / VERIFYING / COMMITTED / FAILED.

Do not log sensitive file contents verbatim or paths containing tokens/secrets unnecessarily. At the moment COMMITTED is logged, the conditions "copied / verified / synced / published" must be accurately established.

## 15. Which API Should You Use in Each Scenario?

### Case A: Copying an ordinary file

```java
Files.copy(source, target);
```

Prefer this because it is concise, clear in intent, and handles options cleanly. Only switch to a manual loop when you need behavior the high-level API lacks or reliable benchmarks prove a benefit.

### Case B: Saving an InputStream from another API into a file

```java
long bytes = Files.copy(
        inputStream,
        target,
        StandardCopyOption.REPLACE_EXISTING);
```

When the stream belongs to the caller, the caller must close it per ownership contract. For untrusted sources, **cap received bytes** with a wrapper/loop enforcing a hard cap; a direct copy call does not automatically impose application quotas.

### Case C: Need per-chunk processing (checksum/progress/cancel)

Use a stream loop or `FileChannel.read/write` to track bytes, update checksums, and check cancellation flags at clean boundaries. When modifying contents, buffered streams per chunk can be easier to follow. `FileChannel` helps if random access or positional I/O is also needed.

### Case D: Need to copy a slice of a very large file

Use `FileChannel.transferTo(start,length,target)` with a loop handling partial transfers; or positional reads/writes via ByteBuffer if native transfer does not fit. Ensure offsets are `long` and do not exceed verified file size.

### Case E: Optimizing byte transfer from a file to a socket

`FileChannel.transferTo` can exploit optimized paths from a file to a suitable `WritableByteChannel`, yet with non-blocking sockets you must manage readiness/backpressure and partial or 0 transfers. Never copy a file-to-file loop that assumes writes always advance onto a socket without proper control.

### Case F: Backup with metadata and crash consistency

No single call among the three approaches carries full backup semantics on its own. Inventory metadata, logical snapshots, staging/verification, durability, and atomic publication per filesystem, plus recovery policies.

## 16. Common Mistakes

1. **Calling `Files.readAllBytes` on multi-GB files just to copy.** Can exceed array/heap limits.
2. **Byte-by-byte unbuffered I/O** in large loops. Adds heavy overhead; use chunks.
3. **Assuming `read(chunk)` always fills the array.** Must use returned `n`.
4. **Writing `out.write(chunk)` on the final round even when fewer bytes were read.** Can append stale data.
5. **Forgetting `close`/`try-with-resources`.** Leaks file descriptors and skips flushes.
6. **Assuming `flush` equals fsync.** No such durability guarantee exists.
7. **Calling `Files.copy` onto an existing target without an overwrite policy.** Can throw `FileAlreadyExistsException`.
8. **Using `REPLACE_EXISTING` and thinking the copy is atomic.** Replace option does not make a copy transactional.
9. **Assuming `COPY_ATTRIBUTES` preserves all ACLs/metadata on all filesystems.** Providers have limits.
10. **Assuming `Files.copy` is always zero-copy.** The concrete implementation decides.
11. **Assuming `FileChannel.transferTo` is always zero-copy.** Java API makes no such promise.
12. **Calling `transferTo` once and assuming the whole file was copied.** Partial transfers can occur.
13. **Spinning endlessly when `transferTo` returns 0.** Must handle progress/fallback/failure.
14. **Confusing file offset with `ByteBuffer.position`.** They are distinct positions; `transferTo` takes a positional source offset.
15. **Using `int` for multi-GB file sizes/offsets.** Overflows and copies wrong regions.
16. **Casting remaining size to `int` before clamping.** Can become negative or wrong.
17. **Forgetting `flip()` after channel read.** Buffer is not ready for writing.
18. **Forgetting `clear()` after consuming bytes.** Next iteration lacks receive space.
19. **Assuming a single `FileChannel.write` writes all `remaining()`.** Partial writes can occur.
20. **Allocating a new direct ByteBuffer on every chunk.** Adds unnecessary cost/resource usage.
21. **Benchmarking once in a fixed order.** Easily distorted by cache and background load.
22. **Comparing raw byte copy against copying attributes + force and declaring a winner.** Different semantics make the comparison unfair.
23. **Including verification in one timing but not another.** Skews throughput results.
24. **Thinking equal file size means identical bytes.** Need `Files.mismatch` or proper content verification.
25. **Thinking `Files.mismatch==-1` proves durability.** It only compares bytes at read time.
26. **Copying a concurrently modified file and assuming a consistent snapshot.** Can mix versions.
27. **Copying directly over critical files without handling partial failure.** Use staging/verify/publish per policy.
28. **Forgetting to handle symbolic links** in tree copies or untrusted input paths.
29. **Thinking `Files.copy` recursively copies an entire directory tree.** It does not copy child entries automatically.
30. **Using `APPEND` when intending the target to equal the source.** Produces corrupted content.
31. **Copying source onto itself with `TRUNCATE_EXISTING`.** Risks data loss.
32. **Treating "method returned" = "durably written to disk".** Need explicit force/sync when durability is required.
33. **Assuming `FileChannel` is always faster than buffered streams for small files.** Open, transfer, and caching costs can flip results.
34. **Failing to define ownership of InputStream/OutputStream passed to APIs.** Easy to close prematurely or leak.
35. **Not bounding bytes from user-controlled InputStreams.** Can exhaust disk/quotas.
36. **Assuming JVM/GC cleans up temp files on job failure.** Explicit cleanup/recovery is required.

## 17. Self-Check Questions

**Q1.** Simply copying one file on the same machine, needing no offset/progress/transformation—which API should you consider first?  
**Answer:** `Files.copy(source,target)` because it is clear and concise. Benchmark if performance has strict requirements.

**Q2.** One round of `in.read(chunk)` returns 123 bytes, `chunk.length=65536`. How much should you write?  
**Answer:** `out.write(chunk,0,123)`, not the entire array.

**Q3.** Is `FileChannel.transferTo(0,size,target)` returning less than `size` a Java bug?  
**No.** The API permits partial transfers; you must loop using actual bytes transferred.

**Q4.** If `transferTo` returns 0 when bytes still remain to copy, what should you do?  
**Answer:** Do not spin forever. Inspect the cause, fall back via ByteBuffer, or fail/wait for readiness depending on target type.

**Q5.** For a 5 GiB file, can you cast `channel.size()` to `int`?  
**No.** Size and offsets require `long`; bound the buffer separately with an `int`.

**Q6.** Does `Files.copy(Path,Path)` return a `long` byte count?  
**No.** It returns the target `Path`. The overloads from InputStream or to OutputStream return `long` byte counts.

**Q7.** Does `BufferedInputStream` always speed up code that already reads a 1 MiB array manually?  
**Not guaranteed.** Extra buffering can be redundant; measure on the real workload.

**Q8.** Does `Files.copy(source,target,COPY_ATTRIBUTES)` copy all extended attributes/ACLs on every OS?  
**No.** Support and metadata precision depend on the provider and filesystem.

**Q9.** Is `Files.copy(source,target,REPLACE_EXISTING)` atomic?  
**Not guaranteed.** Copying can be multi-step and leave a partial target on failure.

**Q10.** What does `Files.mismatch(source,target)==-1` prove?  
**Answer:** Both files have identical bytes at the time compared per the API; it does not prove crash durability or snapshot consistency if files change concurrently.

**Q11.** Why can fixed-order copy benchmarks be unfair?  
**Because** page cache, JIT, background activity, and storage state change between runs, making results order-dependent.

**Q12.** Is `FileChannel.transferTo` required to avoid all copies in the OS?  
**No.** Native/zero-copy is a possible optimization, not a portable API guarantee.

**Q13.** After calling `BufferedOutputStream.flush()`, is the file guaranteed to have all bytes after a power outage?  
**No.** Java-layer flushing does not mean storage durability; appropriate sync/force is needed.

**Q14.** If source changes mid-copy, does `Files.copy` yield a single consistent snapshot version?  
**No general guarantee.** You need filesystem snapshots, immutable files, or a coordination protocol.

**Q15.** To copy a directory's contents along with its subdirectories, is calling `Files.copy(dir,dest)` once enough?  
**No.** You must traverse the tree and handle each entry, symlinks, attributes, and errors.

**Q16.** Does positional `FileChannel.transferTo` modify the source `FileChannel`'s position?  
**No.** The source offset is passed explicitly, leaving source position unchanged; if target tracks position, its position advances by written bytes.

## 18. Takeaways and Official Documentation

**Decision summary:**

```text
Need to copy an entire file?
    ├── Yes, no progress/chunk transformation needed
    │       └── Try Files.copy(Path,Path,options) first
    └── Need a custom pipeline?
            ├── Only have InputStream/OutputStream or per-chunk processing
            │       └── Buffered streams with a reused byte array
            └── Need offsets/random access/channel-to-channel transfer
                    └── FileChannel + partial-transfer loop
                              │
                              └── Measure real workload before choosing optimizations
```

Whichever approach you choose, remember: **never load a huge file onto the heap just to copy it; check actual transferred byte counts; ensure resource cleanup; recognize partial copies; and distinguish bytes copied, bytes verified, and bytes durably persisted.**

Official Java SE 21 documentation:

- `Files.copy` and overloads/semantics: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- `StandardCopyOption` and `LinkOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html and https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html
- `StandardOpenOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html
- `FileChannel` — `read`, `write`, `transferTo`, `transferFrom`, `size`, `force`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- `ByteBuffer` — `flip`, `clear`, `remaining`, and direct buffers: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- `BufferedInputStream` / `BufferedOutputStream`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedInputStream.html and https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedOutputStream.html
- `Files.mismatch` — byte-by-byte content comparison: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#mismatch(java.nio.file.Path,java.nio.file.Path)
