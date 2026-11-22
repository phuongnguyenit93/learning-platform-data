# Do Not Assume NIO or Memory Mapping Is Always Faster

## 1. Foundational Mindset: An API Is Not a Speed Promise

When working with **large files** in Java, you often hear claims like:

- "`FileChannel` belongs to NIO, so it is always faster than `FileInputStream`."
- "`MappedByteBuffer` maps the file into memory, so it has almost zero I/O cost."
- "`transferTo()` is always zero-copy, so it is definitely fastest."
- "Direct `ByteBuffer` is always better than heap `ByteBuffer`."
- "For large files, just map the whole file into RAM."

**None of these statements is true under all conditions.** Java APIs provide **different access models and optimization capabilities**. Actual performance depends on workload, OS, filesystem, hardware, caching, read pattern, block size, initialization overhead, available memory, CPU, JVM settings, and how the program measures.

At least three independent questions must be evaluated:

1. **Is it functionally correct?** After copying, is the data complete, byte-accurate, free of trailing truncation, and properly handling EOF/partial reads/writes?
2. **How does it use resources?** Heap, native memory, page cache, file descriptors, CPU, syscall counts, GC pressure, page faults, disk I/O?
3. **Under what conditions is it fast?** Small or large files, sequential or random reads, single-pass or repeated reads, warm or cold cache, single-threaded or multi-threaded, SSD or network filesystem?

**Lesson takeaway:** choose the right approach based on data characteristics and controlled measurements. Do not replace a stream loop with NIO/mmap merely because the API name sounds more "modern".

## 2. Distinguishing Java I/O, NIO, and Memory Mapping

Java has multiple I/O APIs coexisting side by side, with no absolute "old slow / new fast" boundary:

| Approach | Representative APIs | Typical Mechanism | Common Strengths |
| --- | --- | --- | --- |
| Sequential stream | `InputStream`, `OutputStream` | Sequential byte read/write | Simplicity, pipeline composition, easy data bounding |
| Buffered stream | `BufferedInputStream`, `BufferedOutputStream` | Application buffer around a stream | Cuts small I/O calls, sequential processing |
| Files utilities | `Files.copy`, `Files.newInputStream` | Implementation picks mechanism | Concise code, clear copy intent |
| NIO channel | `FileChannel` | Read/write with `ByteBuffer`, positional I/O | Offset access, scattering/gathering, channel transfers |
| Channel transfer | `FileChannel.transferTo`/`transferFrom` | Opportunity for optimized transfer | Moving bytes between channels, may avoid intermediate copies |
| Memory-mapped file | `FileChannel.map` → `MappedByteBuffer` | Maps file region into virtual address space | Accessing many offsets via `get/put`, random reads |
| Asynchronous file | `AsynchronousFileChannel` | I/O modeled via completion/Future | Asynchronous application structure |

**NIO** is the name of an API family (*New I/O*), not a compression algorithm, buffer type, or guarantee of fewer syscalls on every JVM. Similarly, "mmap" is a virtual-memory mapping technique: **it does not mean the entire file is loaded into RAM**.

A program using `FileChannel` can still perform **blocking file I/O**. `FileChannel` is not a `SelectableChannel` and cannot be registered with a `Selector` like a `SocketChannel`. Never confuse NIO file channels with non-blocking sockets.

## 3. Mechanisms Related to Performance

### 3.1. Application Buffering and Per-Call Cost

If reading byte-by-byte with:

```java
int value;
while ((value = input.read()) != -1) {
    output.write(value);
}
```

then when streams are unbuffered, calls across Java/OS layers can become massive. One optimization step often more effective than immediately switching APIs is **reading in chunks**:

```java
byte[] buffer = new byte[64 * 1024];
int n;
while ((n = input.read(buffer)) != -1) {
    if (n == 0) {
        continue; // Needs a no-progress policy depending on source.
    }
    output.write(buffer, 0, n);
}
```

Both snippets are illustrative only; input/output declarations, stream ownership, and I/O error handling are needed. With a standard `InputStream` and positive length, `read` normally returns a positive count or `-1`; if an unusual source repeatedly returns 0, the loop above would busy-spin and requires different handling.

**Chunked reading** usually reduces overhead compared to byte-by-byte reads, yet the word "usually" matters: optimal chunk size must still be measured and depends on the underlying API/buffer layers.

### 3.2. The OS Page Cache

For regular files, the OS typically caches file pages in the **page cache**. Consequently:

- The first read (*cold-ish*) may have to wait for storage.
- Subsequent reads (*warm*) may serve most bytes from system RAM.
- Two programs using different APIs run back-to-back on the same file may experience **different** cache states.
- Files larger than cache capacity and competing workloads can swing results dramatically.

`Files.readAllBytes`, `FileChannel.read`, and `MappedByteBuffer.get` can all benefit from the page cache. Mapping **does not eliminate** the cost of bringing pages from storage into cache. It changes how data is accessed, not the physical limits of SSDs/HDDs/networks.

### 3.3. System Calls, Memory Copies, and Page Faults

A `FileChannel.read(ByteBuffer)` may issue an OS call and copy bytes into the target buffer. Memory mapping lets a program read the mapped region with memory operations once mapping is established. However, mapping can incur **page faults**, page setup and management overhead, TLB pressure, map/unmap overhead, virtual address space pressure, and cache interactions.

Reducing copy counts **does not guarantee lower total cost** if you transfer a small block once and discard the mapping. For repeated random accesses across already-cached pages, mapping can shine; for a single sequential scan, buffered streams or channels often achieve high throughput with less complexity.

### 3.4. Allocation and GC Costs

`ByteBuffer.allocate(n)` creates a heap buffer; `ByteBuffer.allocateDirect(n)` creates a direct buffer with backing memory outside the Java heap. Direct buffers can help some native I/O paths, yet:

- Direct buffer allocation/reclamation has overhead.
- Native memory does not appear in full on heap charts.
- Creating many short-lived direct buffers can cause resource pressure.
- Some operations still require copies or creating views depending on the API.
- There is no contract saying "direct is always faster than heap".

**Never allocate a new buffer on every iteration of a copy loop if you can reuse one with a clear lifecycle.**

## 4. Performance Depends on Workload

A sensible selection starts by describing the workload:

| Workload | Reasonable Candidates to Test | Premature Conclusions to Avoid |
| --- | --- | --- |
| Few-KiB file, read once | `Files.readAllBytes` (if bounded), buffered stream | Mapping is definitely fastest |
| Very large file, sequential read | Buffered stream, `FileChannel` + buffer, `Files.copy` | NIO always beats buffered streams |
| Copy whole file | `Files.copy`, `transferTo`/`transferFrom`, buffered copy | `transferTo` is always zero-copy |
| Random access across many offsets | Positional `FileChannel.read`, memory mapping | Mmap is always better than positional read |
| Repeated access to a small region | App-level cache, buffer reuse, small-region mmap | Mapping the whole file is optimal |
| Read once and discard | Fixed-buffer streaming | Always mmap and leave to GC |
| Many small files | Simple stream/`Files`; measure open overhead | API optimal on one huge file stays optimal |
| Unknown input size | Streaming + byte limit | `readAllBytes` then check size |
| File rotated, truncated, or rewritten | Regular channel read/write with clear state | Mapping is safe against any resize |

These suggestions are only to build a **list of benchmark candidates**, not a speed ranking.

## 5. Buffered Streams: A Simple Yet Strong Baseline

A straightforward design to copy a file:

```java
try (InputStream input = new BufferedInputStream(
         Files.newInputStream(source), 64 * 1024);
     OutputStream output = new BufferedOutputStream(
         Files.newOutputStream(target), 64 * 1024)) {

    byte[] buffer = new byte[64 * 1024];
    int read;
    while ((read = input.read(buffer)) != -1) {
        output.write(buffer, 0, read);
    }
}
```

This is an illustrative snippet assuming valid `Path` `source`/`target` and required imports. `close()` on buffered output flushes remaining buffered bytes per contract; errors during close still need handling. Some buffer arrangements may **double-buffer**—for instance, having both `BufferedInputStream` and a 64 KiB read array—yet remain an easy baseline to implement. You can also test `Files.newInputStream` + a large array directly to check whether the buffered wrapper helps your specific workload.

### When Streams Are a Good Choice

- Data is processed **sequentially**, needing no seeking.
- Large or unbounded input: you want to cap memory via a fixed buffer.
- Data flows through pipelines for compression, checksumming, parsing, or encryption.
- Broad compatibility, simple code, and easy maintenance are desired.

### When Streams Are Not Enough

- You need to read/write at absolute offsets without changing file position.
- You need to operate on large slices or multiple positions in the same file.
- There is an opportunity to optimize byte transfers between two channels.
- You need features like `FileLock`, `force`, or scattering/gathering.

Even when requirements lead to NIO, you must still weigh **total cost** rather than treating NIO as proof of speed.

## 6. `FileChannel` and `ByteBuffer`: Flexibility Is Not Free

`FileChannel` supports typical overloads:

```java
int read(ByteBuffer dst) throws IOException;
int read(ByteBuffer dst, long position) throws IOException;
int write(ByteBuffer src) throws IOException;
int write(ByteBuffer src, long position) throws IOException;
long position() throws IOException;
FileChannel position(long newPosition) throws IOException;
```

These are abbreviated API signatures for illustration, not a complete class.

`read` and `write` can complete **partially**; never assume `read` fills `ByteBuffer` or `write` consumes all `remaining()` under all circumstances. With positional I/O, the `position` parameter is an **absolute file offset**; overloads taking an offset argument **do not modify `channel.position()`**, though they still advance `ByteBuffer.position()` by the actual bytes transferred.

Channel copy pattern:

```java
ByteBuffer buffer = ByteBuffer.allocate(64 * 1024);

while (true) {
    buffer.clear();
    int n = sourceChannel.read(buffer);
    if (n == -1) {
        break;
    }
    if (n == 0) {
        throw new IOException("Read made no progress");
    }

    buffer.flip();
    while (buffer.hasRemaining()) {
        int written = targetChannel.write(buffer);
        if (written == 0) {
            throw new IOException("Write made no progress");
        }
    }
}
```

This is an illustrative snippet assuming open file channels and imports. It handles **partial writes**, an important correctness factor. For ordinary blocking files, zero progress is normally exceptional; exact policies depend on channel type.

Adding buffer layers does not guarantee high speed: choosing too small a buffer incurs many calls; choosing too large increases allocation cost and affects cache/memory. Sizes like `4 KiB`, `64 KiB`, or `1 MiB` are all just **measurement candidates**, not universal numbers.

## 7. `FileChannel.transferTo` and `transferFrom`: Optimizable, Not Guaranteed Zero-Copy

`FileChannel.transferTo(long position, long count, WritableByteChannel target)` transfers a region of data from the source file to the target channel.

Potential advantage: implementations can use native mechanisms to minimize intermediate steps between files and sockets or supported channels. However, the Javadoc states explicitly that transferred bytes **may be fewer than `count`**, and depending on system/channel type, implementations **may not transfer everything or may impose specific limits**.

Correct pattern when copying an entire file:

```java
long size = source.size();
long copied = 0;

while (copied < size) {
    long n = source.transferTo(
            copied, size - copied, destination);

    if (n <= 0) {
        throw new IOException("transferTo made no progress");
    }
    copied += n;
}
```

This snippet requires declaring `source` as `FileChannel` and `destination` as `WritableByteChannel`. When 0 is returned, **never spin endlessly**. Depending on the API and device, you can fall back to buffer-based copying, await readiness, or fail; the example throws an exception so partial-copy bugs aren't masked.

**What you must not infer:**

- There is no guarantee **every `transferTo` call is zero-copy**.
- "Zero-copy" does not mean zero CPU, zero storage I/O, or no kernel memory involvement.
- There is no guarantee requesting `count` transfers all `count` bytes in one call.
- Changing OS, JDK, filesystem, destination type, or file size can change optimal paths.
- Copying from a file to **another file** and transferring from a file to a **socket** follow different kernel paths; never lump them into one unlabeled benchmark.

If the system needs to copy files by `Path` without per-byte processing, **`Files.copy`** is also a strong candidate. Its implementation may pick dedicated optimizations, so avoid forcing every case through hand-written `transferTo` code.

## 8. Runnable Java 17 Example: Three Copy Approaches, Same Data

This example copies an 8 KiB file using three techniques:

1. Buffered stream.
2. `FileChannel` + `ByteBuffer`.
3. `FileChannel.transferTo`.

It **does not print timings** because fixed stdout here verifies correctness. One small run on a cached file is not a valid benchmark.

**File `CopyStrategiesDemo.java`:**

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
import java.util.Arrays;

public class CopyStrategiesDemo {
    static void bufferedCopy(Path source, Path target)
            throws IOException {
        try (InputStream input = new BufferedInputStream(
                Files.newInputStream(source));
             OutputStream output = new BufferedOutputStream(
                Files.newOutputStream(target))) {
            byte[] bytes = new byte[4096];
            int n;
            while ((n = input.read(bytes)) != -1) {
                output.write(bytes, 0, n);
            }
        }
    }

    static void channelCopy(Path source, Path target)
            throws IOException {
        try (FileChannel input = FileChannel.open(
                    source, StandardOpenOption.READ);
             FileChannel output = FileChannel.open(
                    target, StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
            ByteBuffer buffer = ByteBuffer.allocate(4096);
            while (true) {
                buffer.clear();
                int n = input.read(buffer);
                if (n == -1) {
                    break;
                }
                if (n == 0) {
                    throw new IOException("No read progress");
                }
                buffer.flip();
                while (buffer.hasRemaining()) {
                    if (output.write(buffer) == 0) {
                        throw new IOException("No write progress");
                    }
                }
            }
        }
    }

    static void transferCopy(Path source, Path target)
            throws IOException {
        try (FileChannel input = FileChannel.open(
                    source, StandardOpenOption.READ);
             FileChannel output = FileChannel.open(
                    target, StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
            long size = input.size();
            long copied = 0;
            while (copied < size) {
                long n = input.transferTo(
                        copied, size - copied, output);
                if (n <= 0) {
                    throw new IOException("No transfer progress");
                }
                copied += n;
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("copy-demo-");
        Path source = directory.resolve("source.bin");
        Path a = directory.resolve("buffered.bin");
        Path b = directory.resolve("channel.bin");
        Path c = directory.resolve("transfer.bin");

        try {
            byte[] data = new byte[8192];
            for (int i = 0; i < data.length; i++) {
                data[i] = (byte) (i % 251);
            }
            Files.write(source, data);

            bufferedCopy(source, a);
            channelCopy(source, b);
            transferCopy(source, c);

            System.out.println("Buffered correct: "
                    + (Files.mismatch(source, a) == -1));
            System.out.println("Channel correct: "
                    + (Files.mismatch(source, b) == -1));
            System.out.println("Transfer correct: "
                    + (Files.mismatch(source, c) == -1));
            System.out.println("Original size: " + Files.size(source));
        } finally {
            Files.deleteIfExists(c);
            Files.deleteIfExists(b);
            Files.deleteIfExists(a);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run:

```bash
javac CopyStrategiesDemo.java
java CopyStrategiesDemo
```

**Stdout when I/O succeeds:**

```text
Buffered correct: true
Channel correct: true
Transfer correct: true
Original size: 8192
```

`Files.mismatch` (available since Java 12) returns `-1` if two files are byte-identical. This check verifies **output**, without proving which method is faster.

### Example Analysis

- The source file is generated with 8,192 deterministic bytes, independent of network data.
- Buffered copy reads/writes in 4,096-byte chunks.
- Channel copy follows the exact `clear → read → flip → write all remaining` cycle.
- Transfer copy loops with `copied` so nothing is dropped if `transferTo` returns less than `count`.
- Target files have distinct names; code does not overwrite the source.
- `try-with-resources` closes all handles before deleting temporary files.

**If scaled to a very large file:** calling `Files.mismatch` reads files again to compare, changing cache state. When measuring throughput, separate **copy time** from **verification time** (or report both clearly), and ensure approaches are compared under **identical input conditions**. Each run may require resetting target files, cache policies, and storage state.

## 9. What Memory Mapping Is — and What It Is Not

`FileChannel.map` maps a file region into the process's virtual memory, returning a `MappedByteBuffer` (common API on Java 17):

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY,
        offset,
        length);
```

This is an illustrative snippet; `channel` must be open in an appropriate mode, with valid `offset`/`length`. Once mapped, `get(index)`/`getInt(index)` can access positions inside the mapped region without calling `channel.read` for each element.

**However, mapping does NOT mean:**

- The entire file was loaded into RAM the moment `map()` returned.
- Accessing the first byte cannot incur a page fault.
- Data always stays in CPU caches.
- Kernel, OS, or filesystem are no longer involved.
- Errors never happen if another process truncates the file.
- An explicit synchronous unmap API exists on Java 17 `MappedByteBuffer`.
- It is always faster than `FileChannel.read`, even for small files opened, read once, and closed.

### When Is Mapping Worth Considering?

- Accessing different file regions **repeatedly** by offset.
- Lookup tables or binary data structures with easily computed record addresses.
- Many random reads over a sufficiently long-lived mapped region.
- Data naturally treated as an **in-memory byte region** with clear indices and formats.

### When Should You Consider Avoiding It?

- Very small files, opened and read once.
- Files needing immediate replacement/truncation/deletion where cross-OS portability matters.
- Sequential pipelines already achieving satisfactory throughput.
- Applications creating/destroying thousands of short-lived mappings.
- Input data whose size may be unexpectedly altered by another process.
- Environments with tight limits on address space, native memory, or mapping counts.

**Map to fit the workload, not as a "turbo mode" for all I/O.**

## 10. Virtual Address Space, RAM, and Page Faults Are Three Different Things

When mmap-ing a file, the process receives a **virtual address mapping** to access file pages. Having a wide region mapped does not mean that many bytes were copied onto the Java heap or sit resident in RAM.

Distinguish:

| Concept | Meaning |
| --- | --- |
| Java heap | Holds objects, arrays, and some metadata managed by GC |
| Virtual address space | Process address space where mappings place access windows |
| Resident memory | Physical memory pages currently resident, OS-dependent |
| Page cache | OS cache for file pages |
| Page fault | Accessing a page not yet ready in mapping or needing setup/read from storage |
| MappedByteBuffer | Java view over a mapped file region, bounded by `int` indexing |
| File descriptor/channel | I/O resource opening the file; closing channel does not necessarily unmap created regions |

Speed varies depending on whether data is already in the page cache. Random reads via mapping can trigger uneven page faults; sequential reads via buffered streams let the OS recognize patterns cleanly and use prefetch/read-ahead. For another workload, mapping can cut overhead of many small positional reads.

**Measure CPU, page faults, and I/O latency**, not merely theoretical bytes read.

## 11. Java 17 Example: Random Access with Both FileChannel and mmap Works Correctly

The following example creates a binary file of four big-endian integers and reads the third one (index 2) via:

1. `FileChannel.read(dst, offset)` from an absolute position.
2. `MappedByteBuffer.getInt(index)` from a read-only mapping.

Goal: prove **result equivalence** on this data and distinguish state models. No claim is made about which is faster from a few bytes.

**File `RandomAccessStrategiesDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class RandomAccessStrategiesDemo {
    static int readIntAt(FileChannel channel, long offset)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(Integer.BYTES);
        buffer.order(ByteOrder.BIG_ENDIAN);

        int received = 0;
        while (buffer.hasRemaining()) {
            int n = channel.read(buffer, offset + received);
            if (n == -1) {
                throw new IOException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("No progress");
            }
            received += n;
        }

        buffer.flip();
        return buffer.getInt();
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("random-access-", ".bin");
        file.toFile().deleteOnExit();

        ByteBuffer source = ByteBuffer.allocate(4 * Integer.BYTES);
        source.order(ByteOrder.BIG_ENDIAN);
        source.putInt(10).putInt(20).putInt(30).putInt(40);
        Files.write(file, source.array());

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ)) {

            channel.position(1);
            int positional = readIntAt(channel, 2L * Integer.BYTES);

            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_ONLY, 0, channel.size());
            mapped.order(ByteOrder.BIG_ENDIAN);
            int viaMap = mapped.getInt(2 * Integer.BYTES);

            System.out.println("FileChannel: " + positional);
            System.out.println("MappedByteBuffer: " + viaMap);
            System.out.println("Same value: "
                    + (positional == viaMap));
            System.out.println("Channel position: "
                    + channel.position());
        }
    }
}
```

Compile/run on JDK 17+:

```bash
javac RandomAccessStrategiesDemo.java
java RandomAccessStrategiesDemo
```

**Stdout when I/O succeeds:**

```text
FileChannel: 30
MappedByteBuffer: 30
Same value: true
Channel position: 1
```

**Explanation:**

- The third integer sits from offset 8 to offset 11 (each `int` is 4 bytes).
- `readIntAt` loops until all 4 bytes are read using `offset + received`; the positional read overload leaves `channel.position()` untouched.
- `mapped.getInt(8)` is an absolute access inside the mapped buffer; no `channel.read` call is needed for `getInt`.
- Before reading, the channel was set to `position(1)`, and neither read alters that value.
- Both return 30, yet **do not infer equivalent or superior performance** from correctness alone.

**Lifecycle note:** the example uses `deleteOnExit()` instead of deleting the temp file right after creating a mapped buffer, because on some platforms a live mapping can interfere with deletion/renaming. `deleteOnExit` is also only a best-effort cleanup on JVM exit, not guaranteed in every crash scenario; long-running applications need proper lifecycle management policies.

### Byte Order Matters

`MappedByteBuffer` and `ByteBuffer` have a `ByteOrder`. For big-endian formatted data, configure/interpret it consistently. With mismatched endianness, two readers can return different numbers even though both read identical bytes. Never use buggy parser results to judge API speed.

## 12. Specific Limits of `MappedByteBuffer` in Java 17

`MappedByteBuffer` extends `ByteBuffer`, whose `capacity`, `position`, and `limit` are represented as `int`. Therefore, **a single mapping returning `MappedByteBuffer` cannot arbitrarily span an entire multi-terabyte file**. Java SE 17 `FileChannel.map` binds `size` to buffer limits; in practice each mapped region is capped around `Integer.MAX_VALUE` bytes.

**To process files larger than one buffer's limit**, partition into *windows*:

```text
10 GiB File
   |
   +-- map window #1 (e.g., 256 MiB)
   +-- map window #2 (256 MiB)
   +-- ...
   +-- map window N (trailing slice)
```

Yet mapping many windows carries creation/management overhead; never assume **more mappings is faster**. Systems may cap mapping counts, file descriptors, or address space, especially in 32-bit environments or restricted containers.

### Cleanup/Unmap Is Not Determined by `FileChannel.close()`

With the traditional `FileChannel.map(MapMode, long, long)` API in Java 17:

- A mapping can remain valid **after `FileChannel` closes**.
- `MappedByteBuffer` exposes no standard public `close()`/`unmap()`.
- Unmap timing depends on memory/GC lifecycle, not `clear()` or `force()`.
- Renaming/deleting/truncating a currently mapped file can behave differently across OSes and filesystems.

This directly impacts benchmarks and production systems: if each benchmark pass maps a new region without controlling old mapping lifetimes, tests can accumulate resources and become unfair.

**Version note:** Starting in Java 22, the standard API adds `FileChannel.map(..., Arena)` returning a `MemorySegment`, allowing deterministic lifecycle management via a closeable arena. That is a **different API** and does not give Java 17 `MappedByteBuffer` a `close()` method. When Java 17 compatibility is required, do not use Java 22-only overloads.

## 13. How Can Memory Mapping Make Work Slower?

Some counter-intuitive scenarios:

### 13.1. A Small File Read Once

Mapping setup, page faults, and cleanup overhead can outweigh saving a few `read` calls. A single `Files.readAllBytes` or buffered stream can be simpler and faster in concrete tests.

### 13.2. Very Large Sequential Reads

The OS can perform effective read-ahead for sequential read calls. Memory mapping can also be pattern-optimized, yet it incurs page faults and depends on how CPU/OS handles accesses. There is no universal winner.

### 13.3. Many Short-Lived Mappings

Instead of reusing one long-lived mapping, constantly mapping/unmapping incurs metadata and native memory overhead. With the legacy API, unmap timing also depends on GC. Hence an "open → map → read 1 byte → discard mapping" pattern is rarely optimal.

### 13.4. Files Frequently Truncated or Rotated

Keeping a mapping alive while a file resizes can render parts of the region invalid; failure behavior can be OS-dependent. For rotating logs, temp files, or frequently deleted spools, buffered `FileChannel`/stream reads can have far simpler lifecycles.

### 13.5. Memory Pressure and Resource Contention

Mapping does not copy the whole file onto the heap, yet it can increase pressure on address space, page tables, and caches. On multi-service hosts, one mmap workload can evict another service's cache or suffer far more page faults than expected.

**Evaluating performance means looking beyond one task's elapsed time to its impact on the whole system.**

## 14. `Files.copy`: Do Not Overlook the High-Level API

If the goal is simply copying a file:

```java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

`Files.copy` is usually simpler than writing manual `read`/`write` loops, stating intent clearly and supporting appropriate options. Implementations can exploit filesystem/provider optimizations.

**However**:

- Never assume every provider implements copying identically.
- `COPY_ATTRIBUTES` and `REPLACE_EXISTING` govern metadata/name-collision behavior, not speed guarantees.
- Never accept benchmark results without verifying target validity.
- Metadata, permission, and symlink copying differ by API/option and filesystem.
- Some copy operations can fail midway; business code must handle cleanup/rollback.

For data requiring inspection/checksumming or transformation, chunked streaming can be clearer. For ordinary whole-file copying, **include `Files.copy` among your benchmark candidates**.

## 15. How to Design a Fair Benchmark

### 15.1. Define the Question Before Measuring

Example of a meaningful question:

> "On this SSD, for a 4 GiB file read sequentially into a checksum, how does throughput compare across a 64 KiB buffered stream, 64 KiB `FileChannel`, and 256 MiB windowed mapping under warm cache and cold cache?"

An unclear question:

> "Is NIO faster than IO?"

The second question omits workload, hardware, sizes, cache state, test conditions, and success criteria.

### 15.2. Control Influencing Variables

| Variable | Why Control It |
| --- | --- |
| JVM/JDK and flags | JIT, GC, and runtime implementations may differ |
| OS, filesystem, storage | Affects native I/O paths, page cache, throughput |
| File size and data layout | Small/large files, compressibility, and file sparsity differ |
| Access pattern | Sequential vs. random, read/write ratio |
| Warm/cold cache | OS page cache can dominate measurements |
| Iterations and warmup | JIT/GC/OS scheduler introduce noise |
| Concurrency | I/O queue depth, contention, and memory pressure |
| Buffer size and allocation | Can turn results from API effect into block-size differences |
| Copy destination | Same SSD volume, cross-volume, socket, network mount |
| Write durability | `force/fsync` dramatically alters latency |
| Verification and setup | Consumes CPU/I/O; separate from primary operation timing |
| Error/partial I/O handling | Broken code that runs fast is not a win |

When measuring, vary **one design dimension** within a comparison group (e.g., change I/O mechanism while keeping block size and input identical), then test other dimensions separately. Comparing a byte-by-byte stream against a `FileChannel` with a 1 MiB buffer and concluding "NIO is faster" compares **two algorithms with wildly different operation counts**, failing to isolate the API's effect.

### 15.3. Warmup and Execution Order

The first few benchmark iterations may include:
- Class loading and JVM/JIT initialization.
- Buffer allocation, opening files, and metadata creation.
- File pages not yet in cache.
- Background processes and GC.

If you always run Stream first and Mmap second, Mmap can enjoy the cache warmed by Stream. If you always reverse it, the first runner suffers. Therefore, **alternate/swap execution order, repeat many passes, and report the result distribution**. When benchmarking cold cache, use only methods that genuinely control cache state and document how it was done; reading a file under a new name does not guarantee cold data to the OS.

**Never drop host-wide caches on a live service environment** just to get pretty benchmark numbers: it disrupts other tasks and misrepresents real workloads.

### 15.4. Separate Throughput and Latency

One method may achieve high **MB/s throughput** copying huge files yet poor **latency per lookup** if it maps/unmaps on every call. Another may optimize random access once mapped yet fare poorly on cold startups.

Useful metrics:

- Total copy or scan time, in ms/s.
- Throughput in MiB/s: `bytes / elapsedSeconds / 2^20`.
- Per-operation latency, median, p95, p99 where applicable.
- User/system CPU, page faults, syscall counts, context switches.
- GC pauses/allocation rate, direct/native memory, resident memory.
- Actual disk reads/writes, IOPS, filesystem cache hit/miss if measurable.
- Error rate, partial transfer count, setup/cleanup duration.

Never claim "3× faster" without repeated measurements, test conditions, and correctness checks.

## 16. A Simple Timing Snippet — For Exploration Only, Not Conclusions

`System.nanoTime()` is suitable for measuring elapsed intervals inside the JVM, not calendar time-of-day. A very simple timing helper:

```java
long start = System.nanoTime();
copyOperation.run();
long elapsedNanos = System.nanoTime() - start;

double millis = elapsedNanos / 1_000_000.0;
System.out.printf("Elapsed: %.3f ms%n", millis);
```

This is a **non-standalone illustrative snippet**, assuming `copyOperation` is an already-declared task. The `Elapsed` number is **not fixed** and must never be treated as a promised result.

If writing a simple harness yourself:

1. Prepare inputs outside the timed region.
2. Ensure every alternative performs **the exact same work**.
3. Include or exclude setup/allocation/open/close **according to the measurement goal**; if two approaches are compared end-to-end in production, include their overheads.
4. Avoid printing logs inside the timed region.
5. Verify data after each run (can be outside timing).
6. Run multiple rounds, alternate ordering, and report median/dispersion.
7. Watch cache/GC/paging to explain outliers.
8. Scope conclusions strictly to the measured configuration; avoid overgeneralization.

JMH (Java Microbenchmark Harness) is valuable for pure CPU/JIT code; yet for file I/O, JMH **does not control the OS page cache, storage hardware, filesystem, or resource contention**. Design I/O benchmarks at the system level, optionally combining profiling tools like JFR, `jcmd`, and OS counters.

## 17. A More Useful Test Plan Than Saying "NIO Is Faster"

Build a measurement matrix instead of picking just 2 APIs:

| Workload | Data Size | Pattern | Candidates |
| --- | --- | --- | --- |
| Very small | 1–16 KiB | Whole-file copy | `Files.copy`, buffered stream, channel |
| Medium | 1–32 MiB | Sequential copy | buffered stream, channel, transferTo |
| Large | 1–8 GiB | Sequential copy | buffer/transferTo/Files.copy |
| Random lookup | 1 GiB | 8-byte records | positional FileChannel, windowed mmap |
| Repeated access | 256 MiB | Hot random reads | channel with managed cache, mmap |
| Many small files | 10,000 files | Open+read+close | Files/stream, channel |
| Transform on read | Arbitrary | Hash/parse | streaming buffer, buffered channel |

**Test warm and cold-ish separately**, and for large files have a strategy preventing the benchmark from turning into a memory-cache test (e.g., datasets too small relative to RAM produce fake "disk throughput" numbers).

Each workload needs its own metric: files/s for many small files, MiB/s for sequential copy, p95 latency for random lookups, memory/time-to-cleanup for short-lived mappings.

## 18. Factors That Can Skew Benchmarks

### 18.1. Running Faster by Not Reading Enough Bytes

A `FileChannel.read(buffer)` call can return fewer bytes than `remaining()`. If code fails to loop and processes only the initial bytes, it runs faster simply by **dropping data**. Likewise, `transferTo` can transfer partially; code without a loop may return fast before the target file is complete.

Always verify byte counts and checksum/`Files.mismatch` after running.

### 18.2. Changing Speed by Accidentally Changing Buffer Size

`BufferedInputStream` with its default buffer, `FileChannel` with a 1 MiB direct buffer, and full-file mmap have very different footprints. To attribute gains to an API, control—or at minimum report—buffer sizes and allocation reuse.

### 18.3. Mixing Hot and Cold Caches

An approach run second benefits from the one run first. Never use a single run to represent an entire system.

### 18.4. Excluding Setup in a Biased Way

If mapping is created outside the timer while the stream must open the file inside the timer, the test favors mmap. Conversely, if the real application reuses a mapping for hours, a **steady-state measurement excluding startup** is justified. The issue is not absolute right/wrong, but **defining the question clearly** and measuring startup/end-to-end too if needed.

### 18.5. Treating `write()` as Durability

When `write` returns, data typically enters OS caches or queues, not necessarily durable storage media. `FileChannel.force(...)` or `MappedByteBuffer.force()` may be necessary depending on durability requirements.

If option A calls `force` and option B does not, you cannot conclude B is "faster" for the same data safety guarantee. Compare under equal durability and error policies.

### 18.6. Native Memory Not Fully Visible in Heap Metrics

Mmap and direct buffers can consume native memory/virtual addresses or add page cache pressure without showing up directly in `Runtime.totalMemory()-freeMemory()`. Track RSS/process memory, Native Memory Tracking where suitable, OS mapping stats, and page faults.

### 18.7. Compressed, Sparse, or Copy-on-Write Files

Some filesystems support compression, sparse files, or *reflink/copy-on-write*. A copy command can be fast because the filesystem optimizes metadata/copy semantics rather than transferring every byte through storage. That is valuable in real workloads, yet must be noted clearly because it does not prove that Java API is equally fast on every filesystem.

## 19. Correctness Issues Specific to Mapping

### 19.1. When a File Is Truncated While a Mapped Buffer Is Alive

If a file is resized or truncated while the program accesses a mapping, part of the mapped region can become invalid. Access behavior then has OS-dependent aspects. Never assume `mapped.get(index)` always yields a valid byte merely because `index < mapped.capacity()`.

When another writer exists, use proper coordination, snapshots, or versioning/locking policies; mapping does not lock file contents automatically.

### 19.2. `force()` Is Not `unmap()`

`MappedByteBuffer.force()` requests flushing mapping changes (under applicable conditions) per contract—it does not release the mapping. `clear()` only resets buffer `position`/`limit`. `FileChannel.close()` closes the channel without guaranteeing legacy mappings are unmapped.

Lifecycle confusion can block file deletion on some OSes, leak virtual address resources in long-running processes, and make short benchmarks unrepresentative of production.

### 19.3. Mapping Does Not Provide Arbitrary Atomic Updates

Writing a multi-field structure through a mapped buffer does not automatically form an atomic transaction. A reader in another process can observe half-updated state without a coordination protocol. For sensitive data files or strict consistency, use locking, versioning, checksums, journaling, or transactional storage.

Never choose mmap solely to "write faster" while ignoring consistency.

## 20. Choosing Buffer Size by Measurement and Memory Limits

Every buffer impacts:

- **Per-read/write overhead:** small buffers can increase call counts.
- **Heap/native allocation:** large buffers consume more resources.
- **CPU cache locality:** patterns can affect cache efficiency.
- **Concurrency:** if each connection/task holds its own buffer, buffer size multiplies by concurrency.
- **Latency:** overly large buffers can raise processing latency in some pipelines.
- **I/O scheduler/readahead:** OS and devices behave differently.

Simple budget example: if 200 tasks each hold one 1 MiB buffer, buffers alone take about **200 MiB**. With two buffers per task, roughly 400 MiB, before parsers and other objects. `ByteBuffer.allocateDirect` does not make memory free just because it sits off-heap.

**Techniques worth considering:** bounded buffer pools, buffer reuse, bounded concurrency, admission control, chunked streaming; combined with GC/native memory measurement.

## 21. Input Limits and Resistance to Resource Exhaustion

Good performance is not merely copying fast under normal conditions. Large or untrusted inputs also require:

1. **Byte limits** before and during reads — never trust metadata alone.
2. **Timeouts/deadlines** to prevent stalled threads or ultra-slow clients.
3. **Temp file size and disk quotas** when copying/decompressing to disk.
4. **Concurrency and queue limits** to avoid allocating thousands of huge buffers.
5. **Rollback mechanisms** when copies fail midway.
6. **Integrity verification and publication** after full data arrives.
7. **Decompression expansion limits** if sources are ZIP/GZIP.

`Files.readAllBytes` is convenient yet allocates memory proportional to file size; never run it on unbounded inputs before checking limits. With memory mapping, never view an mmap-ed file as "using zero RAM": it still participates in page cache, RSS, address-space management, and page faults.

Sometimes an approach slightly slower in average benchmarks yet **stable, easy to clean up, and memory-bounded** suits production far better than one achieving high peak throughput at the risk of unbounded resource growth.

## 22. Common Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| "NIO is always faster than IO." | The API does not dictate all costs | Benchmark by workload |
| "mmap reads from RAM, never touching disk." | Page faults may fetch data from storage | Account for page cache, warm/cold |
| "transferTo is always zero-copy." | Implementations/paths/targets vary | Measure by OS/channel, handle partials |
| "One transferTo copies all `count` bytes." | It can transfer fewer than requested | Loop accumulating bytes |
| "One FileChannel.write sends the whole buffer." | Partial writes can happen | Loop on `hasRemaining()` |
| "Switching heap ByteBuffer to direct is always faster." | Allocation/native memory carry costs | Measure, reuse, bound memory |
| "Mmap for tiny files will be faster." | Setup/mapping/page faults can dominate | Test buffered/Files baseline |
| "Map an entire multi-TB file into one Java 17 buffer." | `ByteBuffer` uses `int` indexing | Windowed mapping or another API |
| "Closing the channel unmaps." | Legacy mappings have their own lifetime | Manage mapping lifecycle |
| "`mapped.force()` releases the mapping." | Force is persistence, not release | Separate flush from unmap |
| "Second file running faster proves better API." | Second pass may hit warm cache | Alternate runs, control cache |
| "Measuring once and printing one millisecond value is conclusive." | JIT/GC/OS noise | Warmup, repeat samples, statistics |
| "No need to verify outputs during benchmarks." | Incomplete code looks fast | Verify byte counts/hash/mismatch |
| "Checking Java heap alone is enough." | Native mappings/buffers use other memory | Monitor RSS/page faults/native |
| "Benchmark skips cleanup while production does it." | Measuring a different workload | Report both steady-state and end-to-end |
| "Returning from write guarantees durability." | Cache/flush semantics differ | Compare at equal force/durability levels |
| "Just mmap files being continuously written/truncated." | Invalid mapping / OS-specific risks | Coordinate writers, snapshot, or normal I/O |
| "A 1 MiB buffer suits every workload." | Overhead/memory/concurrency differ | Sweep buffer sizes |

## 23. Practice Exercises

### Exercise 1: One-time 4 KiB file copy

You are copying a 4 KiB file and must write exact bytes. Should you open a `MappedByteBuffer` by default?

**Hint:** start with `Files.copy` or a buffered stream and measure if there is a clear optimization need. For small files, mapping setup overhead can be substantial relative to data transferred. Do not claim mmap is always slow; just avoid choosing it blindly.

### Exercise 2: Checking `transferTo` output

A call `source.transferTo(0, 10_000, target)` returns `4096`. Does the target file already have all 10,000 bytes?

**No.** Only 4,096 bytes were reported transferred in that call. You must continue from offset 4,096 for the remaining 5,904 bytes, check progress/errors, and verify the target.

### Exercise 3: Cache skewing conclusions

You run a buffered stream first, then run mapping next and observe mapping is much faster. Can you conclude mapping is better?

**No.** The first stream run may have warmed the file in the OS page cache, or JIT/CPU/storage states differed. Repeat, reverse order, control cache, and report conditions.

### Exercise 4: Random lookups on a large file

An application reads an 8-byte record at 100,000 random offsets of a large data file repeatedly. Which candidates are worth benchmarking?

**Positional `FileChannel.read` and memory mapping** are both worth testing, possibly adding application-level caching. Mapping can reduce repeated `read` call overhead yet may increase page faults/cache pressure. Decide via measurements on the real workload.

### Exercise 5: Closing the channel after mapping

`FileChannel.close()` was called after creating a read-only map on Java 17. Can you guarantee the file can be deleted immediately on every OS?

**No.** Legacy `MappedByteBuffer` has an independent mapping lifecycle, and Windows plus some environments can restrict deleting/renaming mapped files. Cleanup design must not rely on false portability assumptions.

### Exercise 6: "Faster" because of skipping fsync

Two file-writing approaches: A calls `force(true)` after writing, B does not. B finishes sooner. Can you conclude B is optimal for the same durability requirement?

**No.** Both approaches implement **different data synchronization guarantees**. Compare under the same durability contract.

### Exercise 7: Is FileChannel non-blocking like SocketChannel?

**No.** `FileChannel` is a file channel with normal `read/write` operations and lacks `configureBlocking(false)`/`Selector` like network `SelectableChannel`s. NIO does not mean non-blocking for every channel.

### Exercise 8: Same throughput, different RAM

A 64 KiB stream-copy and `Files.readAllBytes` on a 3 GiB file yield similar throughput on a test machine. Which approach usually controls memory more easily?

**Streaming with a bounded buffer**, because `readAllBytes` attempts to create a single array holding the entire file—which may fail to allocate and consumes huge heap; stream-copy avoids keeping all input bytes in one array. You still must control outputs and intermediate data.

## 24. Decision Checklist for Real Projects

**Before optimizing:**

- Describe the workload: file size, file count, sequential/random, read/write, single-pass or repeated, concurrency.
- Define correctness: byte counts, integrity, EOF, partial reads, cleanup, and data durability.
- Define constraints: RAM, address space, file descriptors, latency SLO, platform/JDK.
- Pick a simple baseline: `Files.copy`, buffered streams, or `Files.newInputStream`.

**When testing NIO and mmap:**

- For channels: use sensible buffers, handle partial I/O, avoid reallocating per iteration.
- For transfers: check actual bytes transferred, provide fallback/error on no progress.
- For mmap: account for setup cost, page faults, unmap lifecycle, truncation/renaming, window size.
- Compare under identical input and durability policies.
- Measure total time, throughput, latency, CPU, heap/native memory, and page cache/paging.

**When reporting results:**

- Record JDK version, OS, filesystem, hardware, file sizes, cache state, and buffer sizes.
- Publish iteration counts, warmup method, and statistical summaries.
- Separate cold/warm and steady-state/end-to-end where appropriate.
- Verify all approaches produce identical outputs.
- Recommend an approach as "faster" **only for the measured workload**, never elevating it to a universal law.

## 25. Summary

There is no single permanent winner among **Buffered I/O**, **FileChannel**, **`transferTo`**, **`Files.copy`**, and **`MappedByteBuffer`**.

- **Buffered streams** are simple, fit sequential workloads, and can be very efficient.
- **FileChannel** excels for positional I/O and `ByteBuffer` workflows; it is not guaranteed faster merely for belonging to NIO.
- **`transferTo`/`transferFrom`** open opportunities to optimize data movement; always handle partial transfers and never assume guaranteed zero-copy.
- **Memory mapping** can be convenient, especially for repeated random access, yet carries page faults, metadata, native resources, and mapping lifecycle management costs.
- **Page cache, filesystem, OS, JVM, and workload** are the real governing variables; warm/cold conditions matter.
- **Controlled benchmarks + correctness verification** are the basis for choosing—not API names or single-run timings.

**Practical rule:** start with a **correct, understandable, and bounded** solution, locate bottlenecks through measurement, and add complexity only when gains are proven while preserving stability, portability, and maintainability.

**Java SE 17 Documentation:**

1. [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html) — `read/write`, positional I/O, `transferTo`, `transferFrom`, `map`, `force`.
2. [MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html) — mapping semantics, `load/isLoaded/force`.
3. [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html) — heap/direct buffers, `position/limit`.
4. [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `copy`, `newInputStream`, `mismatch`.
5. [BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html) and [BufferedOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html).
