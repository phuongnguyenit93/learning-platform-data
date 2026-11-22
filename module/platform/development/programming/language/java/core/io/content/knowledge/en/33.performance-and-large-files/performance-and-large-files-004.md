# Comparing Buffered Streams, Files.copy, and FileChannel for Large Files

## 1. The Problem to Solve

Copying a file seems simple: read bytes from a source and write bytes to a target. However, with files of hundreds of MB, multiple GB, or a continuous data stream, API choice affects **code complexity, Java memory allocation, number of I/O calls, ability to leverage OS optimizations, correctness under errors, and testing strategy**.

In Java 17+, three common approach groups exist:

1. **Buffered streams:** `BufferedInputStream` + `BufferedOutputStream`, reading/writing in byte blocks.
2. **High-level API:** `Files.copy(...)`, asking Java/the provider to copy a file or stream according to option policies.
3. **NIO channel:** `FileChannel`, with `read`/`write` via `ByteBuffer`, or `transferTo`/`transferFrom` to request direct byte transfer between channels.

The most important point:

> **No single API is always the fastest in every environment.** `Files.copy` is usually the first choice for simple file copying; buffered streams fit when byte-stream processing or data transformation is needed; `FileChannel` is useful when offsets, range transfers, case-specific I/O tuning, and progress control are required. Actual performance must be measured on the specific files, device, OS, provider, and workload.

This lesson focuses on **verbatim binary data copying**. If the goal is charset conversion or line-by-line text processing, use `Reader`/`Writer` and design encoding explicitly; do not turn binary bytes into `String` to copy them.

### 1.1. General Data Flow

```text
Approach A — buffered streams:
Disk/FileSystem → InputStream → [byte buffer] → application code
                                → [byte buffer] → OutputStream → Disk/FileSystem

Approach B — Files.copy:
Source Path ───── Files.copy(source, target, options) ─────→ Target Path
                   provider decides the implementation mechanism

Approach C — FileChannel:
Source FileChannel → transferTo / transferFrom → Target Channel
       or
Source FileChannel → ByteBuffer → Target FileChannel
```

These diagrams describe **API layers**, not a promise about how many RAM copies, syscalls, or DMA transfers happen underneath. Even mechanisms called “zero-copy” are subject to OS, filesystem, provider, device, and target channel conditions.

## 2. Quick Comparison Table

| Criterion | BufferedInputStream/BufferedOutputStream | `Files.copy` | `FileChannel` |
|---|---|---|---|
| Abstraction level | Byte stream read/write | High-level file/path or one-sided stream copy | Byte channel access with position, size, transfer |
| Code required | `read/write` loop and EOF handling | Usually a single call | Transfer loop or `ByteBuffer` read/write |
| Application memory | Temporary array/buffer of fixed size | Decided by implementation; does not require caller to hold entire file | A reusable `ByteBuffer`, or transfer with provider/OS-chosen buffering |
| Offset control | Must skip/position through an appropriate source API | No offset parameter on `Files.copy(Path,Path)` | Explicit via `position` and positional `read/write`/`transferTo` |
| Copy one file to another | Possible, but more code | **Default to consider first** | Possible, useful when fine-grained control is needed |
| Copy a file slice | Possible, but must bound manually | Not the goal of the Path→Path overload | Convenient with `transferTo(start,count,...)` |
| Native transfer/zero-copy | No guarantee of eliminating user-buffer copies | Depends on provider/implementation | `transferTo` may use OS-optimized mechanisms, **not guaranteed** |
| File attributes | Handle metadata manually | Supports `COPY_ATTRIBUTES` when supported | Does not copy metadata just by transferring content |
| Very large files | Block-based, no need to hold full file | Designed for regular file copying | `size` and offsets use `long`; loop handles partial transfers |
| Error handling/cleanup | Full manual control | Concise, though a partial target may still remain on failure | Must track transferred bytes and stop on no progress |
| Power-loss durability | Not guaranteed automatically | Not guaranteed automatically | Not guaranteed automatically; `FileChannel.force` has its own scope |

**Choose the API by requirements first, optimize later.** Copying a 3 MB image differs from streaming slices of a multi-hundred-GB log to a socket, or cloning thousands of small files with metadata.

## 3. Buffered Streams: Block Reading and Writing

### 3.1. How They Work

Byte-by-byte `InputStream.read()` can make a program pay many transitions across I/O layers. `BufferedInputStream` gathers reads into an internal buffer; `BufferedOutputStream` batches small writes before passing them to the underlying stream.

A block copy does not need to read the entire file:

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

This is a **snippet inside a method handling `IOException`**, assuming `source` and `target` are resolved `Path`s, with imports for `java.io.*`, `java.nio.file.Files`, and `StandardOpenOption`. It illustrates the main control flow; the complete example is in Section 7.

Meaning:

- `chunk` is a caller-allocated buffer created once, 64 KiB in size.
- `read(chunk)` returns the **actual** number of bytes read, not necessarily 64 KiB.
- `-1` marks EOF; when `n` bytes are read, only `chunk[0..n-1]` is valid for that pass.
- `out.write(chunk,0,n)` writes the exact number of bytes read; omitting `n` can repeat stale bytes from the previous iteration at the end.
- `try-with-resources` closes streams even on error; closing the buffered output flushes remaining bytes from the Java buffer before closing the underlying output.
- `CREATE_NEW` prevents accidentally overwriting an existing target path; if the target exists, opening fails per contract.

### 3.2. Both Buffered Streams and the Passed Array Can Act as Buffers

In this example there are **three levels** involving memory:

1. Internal buffer of `BufferedInputStream`.
2. Application-reused 64 KiB `byte[] chunk` array.
3. Internal buffer of `BufferedOutputStream`.

Because the application already reads and writes in 64 KiB blocks, wrapping with two `Buffered*Stream`s sometimes **provides no clear benefit** over `Files.newInputStream`/`newOutputStream` with the same large array. Buffered wrappers are especially helpful when upper-level code calls `read/write` many times with small amounts.

Do not conclude “more buffer layers means faster.” Extra memory, additional copies across layers, and flush patterns can alter performance. **Benchmark both with and without wrappers** if throughput optimization is the goal.

### 3.3. Choosing Buffer Size

Values like 8 KiB, 32 KiB, 64 KiB, 256 KiB, or 1 MiB are only **benchmark candidates**, not universal answers. Too small a buffer tends to increase I/O calls; too large a buffer can increase footprint, cache/memory pressure, and bytes allocated per worker.

With a copy loop, application-held memory is **O(B)** where B is buffer size, while file size can exceed RAM. If 100 concurrent workers each hold a 1 MiB array, the temporary arrays alone take about 100 MiB, excluding other buffers, queues, and runtime overhead.

Note that `InputStream.read(byte[])` returns partial data depending on source state. Never assume one read corresponds to one file block, one record, or one TCP message.

### 3.4. `flush()`, `close()`, and Durability

`out.flush()` requests pushing buffered bytes down to the underlying output layer. `close()` on a buffered output handles flushing and then closes the underlying stream. However:

- `flush()` **does not mean** the data has been fsynced to the device.
- `close()` **does not by itself guarantee** file safety after power loss on every filesystem.
- If strong durability is required, you must design explicit sync/force steps and usually a safe target-file publishing mechanism.
- If an `IOException` occurs mid-way, the target file may already contain **partial** content and must not be treated as a complete copy.

Data may be 100% read successfully while writing to the target fails or the disk fills up; code must still let the exception propagate and handle target state.

## 4. `Files.copy`: The Direct Way for File Copy Operations

### 4.1. Path → Path Overloads

Simple example:

```java
Path source = Path.of("data.bin");
Path target = Path.of("backup.bin");

Files.copy(source, target);
```

This is an illustrative snippet inside a method handling `IOException` with `Path`/`Files` imported. By contract, if `target` already exists, it throws `FileAlreadyExistsException` by default. To explicitly allow replacement:

```java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

`REPLACE_EXISTING` changes the policy when the target already exists; it does **not** make the entire copy atomic. To preserve metadata when supported:

```java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);
```

These snippets sit inside a method handling `IOException`, using `java.nio.file.*` types. `COPY_ATTRIBUTES` requests copying file attributes, though which attributes are copied and their precision depend on the filesystem/provider. Do not assume all ACLs, owners, extended attributes, and timestamps are preserved identically on every OS.

**Major advantage:** concise, readable code, fewer chances for loop/EOF bugs, and it lets the provider optimize the copy path. For a normal file copy, this is usually the API to try first.

### 4.2. Do Not Infer the Implementation of `Files.copy`

Calling `Files.copy(Path,Path)` **does not promise** that Java always uses:

- A specific `BufferedInputStream`;
- A fixed-size buffer;
- A specific `sendfile` / `copy_file_range` syscall;
- Zero-copy in all cases;
- The same optimization strategy across OSes/JDKs/providers.

`Files.copy` defines **API-level behavior**, while the execution mechanism depends on the implementation, file type, permissions, filesystem, and environment. Performance claims must be tied to the JDK version and platform measured.

### 4.3. `Files.copy` Is Not an Atomic Transaction

Java documentation does not guarantee the overall copy operation is atomic. When an I/O error occurs, the target file may exist with incomplete data. Do not write directly to a critical target path and assume readers will never observe a half-written version.

A common pattern when updating a critical file:

```text
source
  │
  └── Files.copy(...) → staging file in the same directory as target
                              │
                              ├── verify length/checksum/conditions
                              ├── sync staging file if durability is required
                              └── publish via atomic rename if supported
                                           │
                                           └── sync directory per platform if crash durability is needed
```

Distinguish clearly: `Files.copy` does not automatically execute all these steps. `Files.move(..., ATOMIC_MOVE)` has its own contract for an atomic move when supported; it does **not automatically mean** the directory entry is durable across power loss. Replacing an existing target with `ATOMIC_MOVE` is also implementation-dependent and must not be assumed identical across all providers.

### 4.4. Overloads Involving InputStream and OutputStream

`Files` also provides two convenient overloads:

```java
long n1 = Files.copy(inputStream, target,
        StandardCopyOption.REPLACE_EXISTING);

long n2 = Files.copy(source, outputStream);
```

The snippet above is **illustrative**, with open `inputStream`/`outputStream`, `Path` `source`/`target`, and caller handling `IOException`. Both overloads return a `long` representing the number of bytes copied.

Differences from Path→Path:

- `Files.copy(InputStream, Path, ...)` reads from a stream and creates/writes the target.
- `Files.copy(Path, OutputStream)` reads the file and pushes bytes to the output stream.
- Neither overload **automatically closes caller-passed streams**; the owner must manage `close`/`flush`.
- `Files.copy(Path,Path,...)` returns the **target `Path`**, not a byte count. If you need the byte count, check `Files.size` before/after or copy via an API returning bytes per contract.
- Despite sharing the name `copy`, options and attribute semantics differ by overload; read the signature you actually call.

Do not pass `COPY_ATTRIBUTES` to the `InputStream→Path` overload as if it supported copying metadata from a stream that has no path or equivalent file attributes.

## 5. `FileChannel`: Processing with `ByteBuffer`

`FileChannel` belongs to Java NIO, providing file position, size, random access, and transfer operations. It fits when slice copying or integration with channel pipelines is needed.

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

This is an **illustrative snippet inside a method handling `IOException`**, with valid `source`/`target` and imports `FileChannel`, `ByteBuffer`, `StandardOpenOption`. To guard against an unusual provider where `read`/`write` reports prolonged zero progress, production code should track byte counts and apply a retry/break policy rather than an infinite busy loop.

**Mandatory ByteBuffer rules:**

1. Initially `position=0`, `limit=capacity`, ready to receive bytes.
2. `in.read(buffer)` places bytes from `position` up to `limit`; `position` advances by the amount read.
3. `buffer.flip()` sets `limit` to the written position and resets `position` to 0 for draining bytes.
4. `out.write(buffer)` can write **fewer** than the remaining bytes; use `while(buffer.hasRemaining())`.
5. `buffer.clear()` prepares the buffer for the next round; it **does not wipe physical bytes** in the buffer, only resets cursors.

Omitting `flip()` can write stale bytes or the wrong region. Forgetting `clear()` leaves the buffer with no space to read into. Calling `out.write(buffer)` once and assuming all `remaining()` bytes were written can truncate the target file.

### 5.2. Is `allocateDirect` Always Better Than `allocate`?

No. `ByteBuffer.allocateDirect(n)` uses a region of direct memory, which can be convenient for native channel I/O; `ByteBuffer.allocate(n)` uses a regular heap buffer. The performance difference depends on transfer size, JDK, GC, CPU, OS, and memory pressure.

Direct buffers have their own allocation cost and lifecycle, not “free RAM.” **Allocate once and reuse** in the copy loop instead of calling `allocateDirect` on every iteration. For very small jobs, a heap buffer may be simpler and fast enough.

### 5.3. The Loop Must Handle Partial Writes

`FileChannel.write(ByteBuffer)` returns the actual number of bytes written. Even on a synchronous file channel, the contract does not promise all `remaining()` bytes are written in a single call. Therefore:

```java
while (buffer.hasRemaining()) {
    int n = targetChannel.write(buffer);
    if (n <= 0) {
        throw new IOException("Target did not make progress");
    }
}
```

This illustrative snippet assumes `targetChannel` is open for writing and `buffer` holds bytes to send. If a real environment legitimately requires tolerating temporary `n=0`, design explicit retry/backoff/timeout logic; do not spin indefinitely.

## 6. `FileChannel.transferTo` and `transferFrom`

### 6.1. `transferTo(position,count,target)`

Example:

```java
long copied = sourceChannel.transferTo(
        offset, requestedBytes, targetChannel);
```

This is a snippet with `sourceChannel` of type `FileChannel` opened for reading and a valid `WritableByteChannel` `targetChannel`. Meaning:

- `offset` is the **byte position in the source file**, of type `long`.
- `requestedBytes` is the **maximum bytes desired to transfer** in this call, of type `long`.
- Result `copied` is the **actual bytes transferred** in that call, which may be less than requested.
- The **source `FileChannel`'s file position** is not modified by `transferTo` because the offset is passed explicitly.
- If the target channel has a position, bytes are written starting at the **target's current position**, which advances accordingly.

**Never assume** a single `transferTo(0, source.size(), target)` always transfers the entire file. The provider/OS may cap per-call size, the target may not accept everything, or conditions may cause the method to return 0.

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

This is an **illustrative snippet inside a method**; `sourceChannel` and `targetChannel` are already open. It detects and fails when transfer makes no progress; depending on the use case, you can fall back to `read`/`write` for the remainder.

### 6.3. Why Might It Return 0 or Fewer Bytes?

Several situations:

- The requested region reaches EOF; if offset math is wrong, no bytes remain to transfer.
- The target channel cannot accept more bytes immediately (especially a non-blocking target).
- The native transfer mechanism is capped by the OS or provider.
- The source file was resized during the copy.
- Any implementation limit causing bytes per call to be smaller than requested.

Handling it cannot simply be `while(n==0) continue` forever. You can fall back to `FileChannel.read(ByteBuffer,offset)` followed by `target.write(ByteBuffer)` with progress checks, or fail clearly for the caller to handle.

### 6.4. `transferFrom` Transfers in the Opposite Direction

```java
long n = targetFileChannel.transferFrom(
        readableSourceChannel, fileOffset, maxBytes);
```

This snippet assumes `targetFileChannel` is a `FileChannel` open for writing and `readableSourceChannel` is a `ReadableByteChannel`. `transferFrom` transfers bytes from the **source** into the target `FileChannel` starting at the specified offset.

Note how position behavior differs from `transferTo`:

- `transferFrom` passes the **target file's position** explicitly; the target `FileChannel`'s current position does not change.
- If the source channel has a position, the source position advances as bytes are read.
- The actual return value may also be less than `maxBytes`; you still need a loop and progress handling.
- A socket/pipe source differs from a file with its own readiness and EOF semantics; file-to-file assumptions cannot all be copied blindly to non-blocking networking.

### 6.5. “Zero-Copy” Is a Possibility, Not an API Guarantee

On specific OS/file/channel combinations, `transferTo` can use a native path that reduces copies through user space or reduces syscalls. However, the Java API **does not promise that every `transferTo` will always be zero-copy**.

Do not infer:

- That no data is copied in RAM/OS.
- That the page cache is bypassed.
- That there is zero CPU overhead or context switching.
- That it is guaranteed faster than buffered streams for small files.
- That it has identical semantics on Windows, Linux, macOS, and network filesystems.

Allowing `FileChannel` providers to optimize is a **potential advantage**. To confirm real gains, measure on your actual deployment combination.

## 7. Runnable Java 17+ Example: Three Copy Approaches and Byte Verification

The standalone example below:

- Creates an isolated directory and a source file of **131,075 bytes** (intentionally not divisible by 64 KiB).
- Copies via buffered streams.
- Copies via `Files.copy(Path,Path)`.
- Copies via `FileChannel.transferTo`, with fallback to `read/write(ByteBuffer)` if transfer makes no progress.
- Compares bytes with `Files.mismatch` (Java 12+, thus available in Java 17+).
- Cleans up only its own example files without touching user files.

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
                // read the remaining region using positional read.
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

- Uses **deterministic** byte data instead of `Random` so stdout and comparisons are reproducible.
- `131_075` is not divisible by `65_536`; the final read has only 3 bytes after two full blocks, testing that the code does not write extra bytes.
- `CREATE_NEW` requires the target file not to exist and prevents unintentional overwrites.
- `Files.copy` is called without options because the target is a new path.
- `Files.mismatch(a,b)` returns `-1` when all bytes and lengths match; it verifies the file copy **at the time of reading**, not as a hash or power-loss durability certificate.
- The channel method initializes `position=0` and transfers until `size`. If `transferTo` makes no progress, it uses positional `read` into a reused direct buffer and writes all bytes to the target `FileChannel`.
- Because no other thread modifies source/target in the demo, tracking `position` and file size is stable. **In systems with concurrent writers**, a dedicated snapshot or stability mechanism is required.
- `finally` cleans up only files inside the **demo-created temporary directory**. If an earlier step fails, cleanup itself can throw `IOException`; in real applications, define a logging/retention policy for failed files depending on recovery needs.

### 7.2. Why Not Print “Benchmark” Milliseconds?

Copy speed is affected by page cache, filesystem state, and machine load. Printing `System.nanoTime()` once and declaring “API X is fastest” is not a universally meaningful conclusion. This example deliberately verifies only **correctness** via byte counts and `Files.mismatch`. Performance measurement is explained separately below.

### 7.3. Why Does the Channel Fallback Not Call `read`/`write` Concurrently with an In-Flight Transfer?

`FileChannel.transferTo` is synchronous with respect to this call: it has already returned the transferred byte count (or 0) before fallback begins. In the demo there is no pending async transfer holding the buffer; fallback reads from the remaining `position` and writes to the current output.

**Prerequisite:** neither source nor target is modified by another thread, and the output channel is newly opened at position 0. If you adapt `transferTo` to a non-blocking socket, you must add dedicated readiness/backpressure handling rather than copying this file-to-file fallback loop verbatim.

## 8. Files Larger Than 2 GiB: Use `long`, Process in Parts

Very large files cannot be held in a single `byte[]` exceeding JVM array length limits, and `ByteBuffer` uses `int` for `capacity`/`position`. However, `FileChannel.size()`, positional offsets, and `transferTo`/`transferFrom` parameters use `long`.

Therefore:

- Never cast `channel.size()` to `int` when a file may exceed 2 GiB.
- Do not use `Files.readAllBytes` just to copy a tens-of-GB file: it can fail from array limits or heap exhaustion.
- Use a bounded buffer and a loop so memory does not grow with file size.
- Compute offsets using `long`, and watch for overflow when adding `position + n`.
- Avoid `(int)(size - position)` when remaining bytes may exceed `Integer.MAX_VALUE`. Cast only after clamping with `Math.min(remaining, (long) buffer.capacity())`.
- With `transferTo`, do not assume “`count` is `long` so the OS transfers terabytes in one syscall”; you must still loop by the actual returned value.

### 8.1. Splitting the Copy into Logically Sized Segments

For example, to cap each transfer request at 64 MiB:

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

This is an **illustrative snippet inside a method**, with two open channels. 64 MiB is a reference size, not a mandatory Java limit. If the source changes concurrently, `size` may no longer reflect the true end of file, so decide whether to copy an **initial snapshot** or track changes via an explicit protocol.

### 8.2. Copying a Region of a File

`FileChannel` is convenient when only bytes `[start,start+length)` are needed:

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

This is a snippet inside a method, assuming the requested byte range exists completely in the source and the target is at the right position. If the file is shorter than `start+length`, do not treat a short copy as success; check `size`/source integrity appropriately and handle EOF.

### 8.3. With Multi-File Copying, Metadata and Directory Trees Also Matter

`Files.copy` from one `Path` to another **does not recursively copy an entire directory tree with its contents** when `source` is a directory; when copying a directory, it only creates/copies the directory entry or attributes per contract, while inner entries must be handled separately. Copying a tree requires traversal, symlink/cycle handling, file permissions, metadata, and per-file error handling.

Also do not mistake a single `Files.copy` call for an incremental backup solution: it does not compute diffs, versions, deduplication, historical checksums, or tree-wide transactions.

## 9. Performance: Reading Measurements Properly

### 9.1. Throughput and Latency Measure Different Aspects

- **Throughput:** bytes copied successfully per second, e.g. MiB/s.
- **Latency:** time from starting a copy until the API completes for a file.
- **Tail latency:** p95/p99 across many files/jobs, critical for request-serving systems.
- **Memory footprint:** heap/direct memory/temporary buffers per operation.
- **CPU utilization:** CPU consumed during copying.
- **Syscall count/context switching:** sometimes clarifies the benefit of buffering/transfer.
- **Durability time:** if `force`/sync is required, measure that part too, not just time for bytes to enter cache.

An API with high throughput on one 20 GB file may perform poorly on millions of 1 KiB files due to open/close overhead, metadata lookups, and scheduling. Conversely, `Files.copy` may already exploit provider optimizations such that a hand-written loop is no faster.

### 9.2. Memory and I/O Call Frequency

A `read(chunk)` loop with `chunk.length = B` needs about `ceil(fileSize/B)` reads when each read is full, **but actual calls can be higher** due to partial reads. Write counts also depend on partial writes and buffering.

Illustrative calculation: a 1 GiB file with 64 KiB blocks corresponds to 16,384 blocks if all blocks except possibly the last are full. This is only a **chunk count estimate**, not the exact OS syscall count, because buffering layers, providers, and native transfers may behave differently.

The key point is **never calling byte-by-byte `read()`/`write()`** when copying large files unless specifically required; design an appropriate buffer strategy and measure.

### 9.3. Page Cache Easily Skews Benchmarks

On a typical filesystem, the OS has a page cache and read-ahead. If you run:

```text
Pass 1: buffered copy
Pass 2: Files.copy
Pass 3: FileChannel
```

then passes 2 and 3 may benefit from source data already residing in cache, leading to a biased conclusion that “the later approach is faster.”

Confounding factors:

- Warm/cold OS and JVM caches.
- Antivirus/indexing/background I/O.
- SSD/HDD/NVMe, network mounts, filesystem compression/deduplication.
- Intra-filesystem copy capability vs copying across two devices.
- Direct buffer allocation and GC.
- File size/count, buffer size, and concurrent worker count.
- Sync/durability options and true device speed.
- Sparse files, symlinks, and file attributes.

### 9.4. A More Meaningful Benchmarking Process

1. **Define the workload:** small files, 100 MB, 5 GB; single file or many files; same-volume or cross-volume copy; sequential or chunked.
2. **Enforce identical semantics:** all three approaches copy identical bytes and handle overwrite/attributes/flushing identically if those are part of the requirements.
3. **Warm-up:** run multiple iterations for JIT and system stabilization; do not treat the first run as the final verdict.
4. **Vary execution order:** alternate strategies to reduce cache bias.
5. **Repeat many samples:** take median and distribution, and record JDK/OS/filesystem/media details.
6. **Verify correctness:** check size, `Files.mismatch`, or checksums in appropriate tests. Never report throughput of an incomplete copy.
7. **Separate copy time from verify time:** re-reading the whole file for `mismatch` has a cost; report the two metrics separately.
8. **Measure memory/CPU when needed:** use a profiler, JFR, or appropriate OS tools rather than `nanoTime` alone.
9. **Test failure scenarios:** disk full, permission errors, existing target, deleted/modified source, disconnected network filesystem.
10. **Scope conclusions explicitly:** “on this test machine and file type,” rather than claiming an API is fastest across all JVMs.

`System.nanoTime()` is suitable for measuring a single elapsed interval in a controlled test; for very short microbenchmarks, use a framework like JMH and watch out for OS I/O effects because JMH does not eliminate cache or device factors.

### 9.5. Simple Measurement Pattern, Not Claiming a Standard Benchmark

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

This is an **illustrative snippet** inside a method handling `IOException`; `source`/`destination` are `Path`s and `destination` does not exist yet. It has no fixed stdout, excludes file verification, and does not guarantee durable storage. Do not extrapolate one MiB/s figure from this snippet to other environments.

## 10. Correctness: How to Verify a Copy?

A “successful” file copy must clearly define what is preserved:

| Requirement | How to verify |
|---|---|
| Exact byte contents | `Files.mismatch(source,target)==-1` when neither changes during the check |
| Matching size | `Files.size(source)==Files.size(target)`, necessary but insufficient |
| Modified time, permissions, owner | Read `BasicFileAttributes` or appropriate view; copy metadata separately |
| Do not overwrite existing data | `CREATE_NEW` or default `Files.copy` when target already exists |
| Allow intentional overwrite | `REPLACE_EXISTING` for `Files.copy` or corresponding open options |
| Crash durability | Design `force`/sync, staging, and publish per OS/filesystem |
| Copy from a consistent version | Snapshots, lock/protocol, version/checksum, or equivalent storage mechanism |
| Path security | Validate/canonicalize across trust boundaries, handle symlinks and permissions |

`Files.mismatch` returns the **first differing byte position** or `-1` if there is no difference; if file sizes differ, it returns the first position where the shorter file runs out of bytes. It is not a cryptographic hash algorithm and does not detect or resolve races when source/target can be modified concurrently.

### 10.1. Why Is Matching Size Not Enough?

Two 1 MB files can differ in every single byte. If you only check `Files.size`, bugs that copy out of order, write stale data, or shift offsets go unnoticed. `mismatch` or a suitable checksum helps verify content in tests.

Conversely, if metadata matters, identical bytes still do not guarantee the target file has the right permissions, attributes, or link semantics.

## 11. Files Being Modified During a Copy

None of the three approaches automatically creates a **transactional snapshot** of a source file being edited by another writer.

Suppose:

```text
T0: source.bin = version A
T1: copy reads first half of version A
T2: another writer modifies second half to version B
T3: copy reads second half of version B
T4: target may be a mix of A/B
```

Even if `Files.copy` succeeds, target data may not correspond to any single logical point in time. When consistency matters:

- Stop writers or use a lock/protocol across **cooperating** parties.
- Use filesystem/storage snapshots if available and verified.
- Design copies from versioned **immutable files**; write a new version separately and publish a pointer afterward.
- Record a checksum/version on release and validate after copying; re-check the source if policy requires.
- Do not assume `FileLock` provides complete transactions across all processes or filesystems; semantics depend on OS/provider.

### 11.1. A Byte-Stream Copy Knows Nothing About Application File Structure

For database files, WALs, multi-file logs, or structures updated in multiple steps, simply copying bytes while the service is running can produce a logically corrupt snapshot. Use the storage system's official backup/snapshot API or an application-consistent backup procedure rather than copying live files without understanding their format.

## 12. Overwrite, Symlinks, and Metadata

### 12.1. Copying a New File Differs from Updating an Existing One

`Files.copy(source,target)` by default does not replace an existing target. `Files.copy(source,target,REPLACE_EXISTING)` requests replacing the target if allowed. However, replacing the target is **not an atomic publish**; readers can see an inconsistent state while copying is in progress or if it fails.

When copying via buffered streams/channels, open options mean:

- `CREATE_NEW`: create new and fail if the file already exists.
- `CREATE`: create if absent; does not imply truncation without the corresponding option.
- `TRUNCATE_EXISTING`: truncate if opened for writing and the file exists per contract.
- `APPEND`: append to the end, **not an overwrite copy from the start**.

Use the appropriate policy; do not inadvertently combine `APPEND` with a verbatim copy into a fresh file.

### 12.2. Symlinks and Paths

With `Files.copy(Path,Path)`, if `source` is a symbolic link, the default typically **follows the link** and copies the referenced target's contents; `LinkOption.NOFOLLOW_LINKS` can be used to copy the link itself per the provider's contract.

```java
Files.copy(
        source,
        target,
        LinkOption.NOFOLLOW_LINKS);
```

This is an illustrative snippet inside a method handling `IOException`; creating/copying symlinks and permission support depend on the filesystem/provider. If paths are user-supplied and the program runs with elevated privileges, check for path traversal, symlink races, and allowed directories before operating. A separate `Files.exists` check before writing is **not** an absolute race barrier; use atomic creation options and appropriate OS policies when needed.

### 12.3. Copying Attributes and Permissions

`StandardCopyOption.COPY_ATTRIBUTES` applies to the `Files.copy(Path,Path)` overload; which attributes are preserved depends on the provider and filesystem. Between certain sources and targets, permissions, owner, ACLs, extended attributes, timestamp precision, or creation time may differ.

When building backups, metadata is sometimes as important as content; inventory required attributes and verify after copying. Do not benchmark a content-only copy against one that also copies permissions/metadata without explicitly noting the difference.

## 13. File Durability After Copying

**“The method returned successfully” does not automatically mean “the file survives power loss.”** Filesystems and OSes can buffer data. APIs:

- `BufferedOutputStream.flush()`: pushes bytes from the Java buffer to the underlying stream; does not imply `fsync`.
- `Files.copy`: not a durability sync command with a universal contract across all devices.
- `FileChannel.force(false)`: requests flushing content changes within API scope.
- `FileChannel.force(true)`: requests flushing both content and metadata within API scope; stronger guarantee on local storage under contract conditions.
- `Files.move(...,ATOMIC_MOVE)`: when supported, covers atomicity of the move operation, **distinct from** crash durability.
- Syncing the parent directory entry after rename: OS/provider-dependent and may require platform APIs outside portable Java SE.

If a copy will replace a critical configuration file, a design often looks like:

```text
create temporary file in the same directory
        │
        ▼
copy all bytes to staging
        │
        ▼
verify copy (size/checksum/schema)
        │
        ▼
force/sync staging when durability is required
        │
        ▼
atomic rename if supported by provider
        │
        ▼
sync directory per platform contract if crash consistency is needed
        │
        ▼
confirm commit only at the level actually guaranteed
```

Do not assume `FileChannel.force(true)` on staging before rename also syncs the **directory entry after rename**. For critical data, maintain a backup/recovery policy and test failure modes on real storage.

## 14. Error Handling and Cleanup When Copying Fails

Situations to account for:

| Situation | Risk | How to handle |
|---|---|---|
| Source missing | `NoSuchFileException` or `IOException` | Do not create a fake empty copy as success |
| Target exists | `FileAlreadyExistsException` under default/`CREATE_NEW` | Choose explicitly whether to overwrite |
| Disk full/quota | Target may be partially written | Clean up staging/target per policy; do not publish |
| Permission denied | Cannot open/write file | Check permissions, return clear error |
| Source file resized | Short copy or mixed versions | Lock/snapshot/immutable versions |
| `transferTo` returns 0 with bytes left | Non-advancing loop, spin risk | Fall back or fail |
| Partial `write(ByteBuffer)` | Data truncation | Loop until `remaining()` is exhausted |
| Source/target are the same file | Can overwrite/truncate source | Validate identity; avoid copying onto source |
| Cross-volume/FS I/O | Different speed and semantics | Benchmark and verify correctness on actual pair |
| Process killed abruptly | Incomplete copy | Copy to staging, recovery state, and cleanup |

If copying to a temporary file fails, do not rename the temp file to target. Cleanup depends on business rules: you can delete staging immediately, or retain a partial copy to resume with checksum/chunk-map verification. Never mark a target file as “completed” merely because it exists.

### 14.1. Timeouts and Copy Cancellation

For large files or copies over a network filesystem, an operation can take a long time. A hand-written buffered stream/channel loop can check a stop flag between chunks, though blocking I/O calls may not return immediately when the flag changes.

High-level `Files.copy` does not directly provide a per-block progress callback on the Path→Path overload. If UI progress or per-block cancellation is required, managing chunks and byte counts directly via streams or channels can be more suitable.

Never report “100%” progress before `flush`/`close`/verify per your product's completion definition. Under durability requirements, “bytes transferred” and “durable commit” are two different milestones.

### 14.2. Logs and Metrics

For large copy jobs, record:

- Verified source size, job name, or safe ID.
- Bytes transferred, duration, and measured throughput with environment labels.
- Actual API/strategy used and whether fallback occurred.
- Error classification: permissions, disk full, source truncated, target stalled, checksum mismatch.
- Status: `STARTED` / `COPYING` / `VERIFYING` / `COMMITTED` / `FAILED`.

Do not log raw sensitive file contents or paths containing tokens/secrets unnecessarily. At the moment `COMMITTED` is logged, the conditions “copied / verified / synced / published” must be recorded accurately.

## 15. Which API Should You Use in Each Scenario?

### Case A: Copy a regular file

```java
Files.copy(source, target);
```

Prefer this for brevity, clarity of intent, and straightforward option handling. Switch to a manual loop only when behavior is needed that the high-level API does not offer or a credible benchmark proves a benefit.

### Case B: Save an InputStream received from another API to a file

```java
long bytes = Files.copy(
        inputStream,
        target,
        StandardCopyOption.REPLACE_EXISTING);
```

When the stream belongs to the caller, the caller must close it per ownership contract. For untrusted sources, **cap received bytes** using a wrapper/loop with a hard limit; a direct copy call does not enforce an application-desired quota by itself.

### Case C: Need per-chunk processing (checksum/progress/cancel)

Use a stream loop or `FileChannel.read/write` to count bytes, update checksums, and check stop flags at clear points. When transforming content, buffered streams per chunk can be easier to follow. `FileChannel` helps if random access or positional I/O is also needed.

### Case D: Need to copy a slice of a very large file

Use `FileChannel.transferTo(start,length,target)` with a loop handling partial transfers; or positional reads/writes via `ByteBuffer` if native transfer is unsuitable. Ensure offsets are `long` and do not exceed verified file size.

### Case E: Optimize transferring bytes from a file to a socket

`FileChannel.transferTo` can exploit an optimized path from a file to a suitable `WritableByteChannel`, though for non-blocking sockets you must manage readiness/backpressure and partial or 0 transfers. Do not blindly apply a file-to-file loop that assumes writes always advance onto a socket.

### Case F: Backup with metadata and crash consistency

No single call among the three provides complete backup semantics on its own. You need metadata inventory, logical snapshots, staging/verification, durability, and filesystem-aware atomic publishing, plus a recovery policy.

## 16. Common Mistakes

1. **`Files.readAllBytes` on a multi-GB file just to copy it.** Can exceed array/heap limits.
2. **Byte-by-byte unbuffered `read`/`write`** in a large loop. Increases overhead; use chunks.
3. **Assuming `read(chunk)` always fills the array.** Must use the returned `n`.
4. **Calling `out.write(chunk)` on the final pass even when fewer bytes were read.** Can write stale data.
5. **Forgetting `close`/`try-with-resources`.** Leaks file descriptors and skips flushing.
6. **Assuming `flush` equals `fsync`.** There is no such durability guarantee.
7. **Calling `Files.copy` onto an existing target without an overwrite policy.** Can throw `FileAlreadyExistsException`.
8. **Using `REPLACE_EXISTING` and thinking the copy is atomic.** The replace option does not turn copy into a transaction.
9. **Assuming `COPY_ATTRIBUTES` preserves all ACLs/metadata on all filesystems.** Providers have limits.
10. **Assuming `Files.copy` is always zero-copy.** The specific implementation decides.
11. **Assuming `FileChannel.transferTo` is always zero-copy.** The Java API makes no such promise.
12. **Calling `transferTo` once and thinking the whole file was copied.** Partial transfers can happen.
13. **Spinning indefinitely when `transferTo` returns 0.** Must handle progress/fallback/failure.
14. **Confusing file offset with `ByteBuffer.position`.** They are distinct positions; `transferTo` takes a positional source offset.
15. **Using `int` for multi-GB file sizes/offsets.** Overflows and copies wrong regions.
16. **Casting remaining size to `int` before clamping.** Can become negative or wrong.
17. **Forgetting `flip()` after channel read.** Buffer is not ready for writing.
18. **Forgetting `clear()` after consuming bytes.** Next iteration lacks space to read.
19. **Assuming a single `FileChannel.write` writes all `remaining()`.** Partial writes can occur.
20. **Allocating a new direct `ByteBuffer` on every chunk.** Unnecessarily increases cost and resource pressure.
21. **Benchmarking once in a fixed order.** Easily distorted by cache and background load.
22. **Comparing a raw byte copy against one that also copies attributes/`force` and declaring one faster.** Different semantics make the comparison unfair.
23. **Including verification in one method's timing but not the other's.** Biases throughput results.
24. **Thinking equal file sizes mean equal bytes.** Need `Files.mismatch` or proper content verification.
25. **Thinking `Files.mismatch==-1` proves durability.** It only compares bytes at read time.
26. **Copying a concurrently modified file and assuming a consistent snapshot.** Can mix versions.
27. **Copying directly into a critical file without handling partial failures.** Use staging/verify/publish per policy.
28. **Forgetting symbolic links** during tree copies or with untrusted input paths.
29. **Thinking `Files.copy` recursively copies an entire directory tree.** It does not copy all child entries automatically.
30. **Using `APPEND` when intending the target to equal the source.** Produces wrong content.
31. **Copying source onto itself with `TRUNCATE_EXISTING`.** Risk of data loss.
32. **Treating “method returned” as “durably written to disk.”** Needs explicit `force`/sync when durability is required.
33. **Believing `FileChannel` is always faster than buffered streams for small files.** Open, transfer, and caching costs can reverse expectations.
34. **Failing to define ownership of `InputStream`/`OutputStream` passed to APIs.** Risks premature close or leaks.
35. **Not bounding bytes from a user-controlled `InputStream`.** Can exhaust disk/quota.
36. **Assuming JVM/GC cleans up temp files when a job fails.** Explicit cleanup/recovery is needed.

## 17. Self-Check Questions

**Question 1.** For simply copying one file on the same machine without needing offsets, progress, or transformations, which API should you consider first?  
**Answer:** `Files.copy(source,target)` because it is clear and concise. Benchmark if performance has special requirements.

**Question 2.** One call to `in.read(chunk)` returns 123 bytes, with `chunk.length=65536`. How much should you write?  
**Answer:** `out.write(chunk,0,123)`, not the entire array.

**Question 3.** Is `FileChannel.transferTo(0,size,target)` returning less than `size` a Java bug?  
**No.** The API permits partial transfers; you must loop by the actual bytes transferred.

**Question 4.** If `transferTo` returns 0 while bytes remain to copy, what should you do?  
**Answer:** Do not spin indefinitely. Check the cause, fall back via `ByteBuffer`, or fail/wait for readiness depending on the target type.

**Question 5.** For a 5 GiB file, can you cast `channel.size()` to `int`?  
**No.** Size and offsets require `long`; bound the buffer separately using `int`.

**Question 6.** Does `Files.copy(Path,Path)` return a `long` byte count?  
**No.** It returns the target `Path`. The overloads from `InputStream` or to `OutputStream` return a `long` byte count.

**Question 7.** Does `BufferedInputStream` always speed things up when code already reads into a 1 MiB array?  
**Not guaranteed.** Extra buffering may be redundant; measure the actual workload.

**Question 8.** Does `Files.copy(source,target,COPY_ATTRIBUTES)` copy all extended attributes/ACLs on every OS?  
**No.** Support and metadata fidelity depend on the provider and filesystem.

**Question 9.** Is `Files.copy(source,target,REPLACE_EXISTING)` atomic?  
**Not guaranteed.** Copying can be a multi-step operation and leave a partial target on failure.

**Question 10.** What does `Files.mismatch(source,target)==-1` prove?  
**Answer:** Both files had identical bytes at the time of comparison per the API; it does not prove crash durability or snapshot consistency if a file was modified concurrently.

**Question 11.** Why can fixed-order copy benchmarks be unfair?  
**Because** page cache, JIT, background activity, and storage state change between runs, making results order-dependent.

**Question 12.** Is `FileChannel.transferTo` guaranteed to avoid all OS copies?  
**No.** Native/zero-copy is a potential optimization, not a portable API guarantee.

**Question 13.** After calling `BufferedOutputStream.flush()`, is the file guaranteed to have all bytes intact after a power loss?  
**No.** Java-layer flushing does not mean storage durability; appropriate sync/force is required.

**Question 14.** If `source` changes during a copy, does `Files.copy` yield a single consistent snapshot version?  
**No general guarantee.** You need filesystem snapshots, immutable files, or a coordination protocol.

**Question 15.** When you need to copy the contents of a directory along with subdirectories, is a single `Files.copy(dir,dest)` call enough?  
**No.** You must walk the tree and handle each entry, symlinks, attributes, and errors.

**Question 16.** Does positional `FileChannel.transferTo` alter the source `FileChannel`'s position?  
**No.** The source offset is passed in, so source position stays unchanged; if the target has a position, it advances by the bytes written.

## 18. Summary and Official Documentation

**Decision summary:**

```text
Need to copy an entire file?
    ├── Yes, no progress/chunk transformation needed
    │       └── Try Files.copy(Path,Path,options) first
    └── Need a custom pipeline?
            ├── Only have InputStream/OutputStream or per-chunk processing
            │       └── Buffered streams with a reusable byte array
            └── Need offsets/random access/channel-to-channel transfer
                    └── FileChannel + partial transfer loop
                              │
                              └── Measure real workload before choosing optimizations
```

Regardless of approach, remember: **do not load huge files into the heap just to copy them; check the actual transferred byte count; ensure resources are closed; recognize partial copies; distinguish copied bytes, verified bytes, and durably written bytes.**

Official Java SE 21 documentation:

- `Files.copy` and overloads/semantics: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- `StandardCopyOption` and `LinkOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html and https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html
- `StandardOpenOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html
- `FileChannel` — `read`, `write`, `transferTo`, `transferFrom`, `size`, `force`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- `ByteBuffer` — `flip`, `clear`, `remaining`, and direct buffers: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- `BufferedInputStream` / `BufferedOutputStream`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedInputStream.html and https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedOutputStream.html
- `Files.mismatch` — byte-by-byte content comparison: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#mismatch(java.nio.file.Path,java.nio.file.Path)
