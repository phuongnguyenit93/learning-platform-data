# Do Not Assume NIO or Memory Mapping Is Always Faster

## 1. Core Mindset: An API Is Not a Speed Promise

When working with **large files** in Java, you often hear claims like:

- “`FileChannel` is part of NIO, so it is always faster than `FileInputStream`.”
- “`MappedByteBuffer` maps the file into memory, so it has almost zero I/O cost.”
- “`transferTo()` is always zero-copy, so it is guaranteed fastest.”
- “Direct `ByteBuffer` is always better than heap `ByteBuffer`.”
- “For large files, just map the whole file into RAM.”

**None of these statements holds under all conditions.** Java APIs offer **different access models and optimization opportunities**. Real-world performance depends on workload, OS, filesystem, device, caching, read pattern, block size, startup cost, available memory, CPU, JVM settings, and how the program measures.

You must evaluate at least three independent questions:

1. **Is it functionally correct?** After copying, is the data complete, byte-identical, not missing the tail, and handling EOF/partial reads/writes properly?
2. **How does it use resources?** Heap, native memory, page cache, file descriptors, CPU, syscall count, GC pressure, page faults, disk I/O?
3. **Under what conditions is it fast?** Small or large files, sequential or random reads, one-off or repeated reads, warm or cold cache, single or multiple threads, SSD or network filesystem?

**Lesson takeaway:** choose the right approach based on data characteristics and controlled measurements. Do not replace a stream loop with NIO/mmap just because the API name sounds more “modern.”

## 2. Distinguishing Java I/O, NIO, and Memory Mapping

Java has multiple I/O APIs coexisting without an absolute “old slow / new fast” divide:

| Approach | Representative APIs | Typical mechanism | Common strengths |
| --- | --- | --- | --- |
| Sequential stream | `InputStream`, `OutputStream` | Read/write bytes sequentially | Simple, pipeline processing, easy data bounding |
| Buffered stream | `BufferedInputStream`, `BufferedOutputStream` | Application buffer around stream | Reduces small I/O call overhead, sequential processing |
| Files utilities | `Files.copy`, `Files.newInputStream` | Implementation picks mechanism | Concise code, expresses copy intent clearly |
| NIO channel | `FileChannel` | Read/write with `ByteBuffer`, positional I/O | Offset access, scattering/gathering, channel transfers |
| Channel transfer | `FileChannel.transferTo`/`transferFrom` | Opportunity for optimized transfer | Moves data between channels, may avoid intermediate copies |
| Memory-mapped file | `FileChannel.map` → `MappedByteBuffer` | Maps file region into address space | Multi-location access via `get/put`, random reads |
| Asynchronous file | `AsynchronousFileChannel` | I/O expressed via completion/`Future` | Asynchronous application structuring |

**NIO** is the name of an API group (*New I/O*), not a compression algorithm, a buffer type, or a guarantee of fewer syscalls on every JVM. Likewise, “mmap” is a virtual memory mapping technique: **it does not mean the entire file is already loaded into RAM**.

A program using `FileChannel` may still perform **blocking file I/O**. `FileChannel` is not a `SelectableChannel` and cannot be registered with a `Selector` like a `SocketChannel`. Do not confuse NIO file channels with non-blocking sockets.

## 3. Mechanisms Related to Performance

### 3.1. Application Buffers and Per-Call Overhead

If you read byte by byte using:

```java
int value;
while ((value = input.read()) != -1) {
    output.write(value);
}
```

then when the stream is not appropriately buffered, calls crossing Java/OS layers can be huge. An optimization step often more effective than immediately switching APIs is **block reading**:

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

Both snippets are illustrative only; you must declare input/output, manage stream ownership, and handle I/O errors. For standard `InputStream` with positive length, `read` normally returns a positive count or `-1`; if an unusual source keeps returning 0, the loop above will busy-spin and requires different handling.

**Block reading** usually cuts overhead compared to byte-by-byte reading, yet the word “usually” matters: optimal block size must still be measured and depends on the underlying API/buffer layers.

### 3.2. The OS Page Cache

For regular files, the OS typically caches file page data in the **page cache**. Therefore:

- The first read (*cold-ish*) may have to wait for storage.
- Subsequent reads (*warm*) can fetch most bytes from system RAM.
- Two programs using different APIs run consecutively on the same file can see **different** cache states.
- Files larger than cache capacity and competing workloads can swing results dramatically.

`Files.readAllBytes`, `FileChannel.read`, and `MappedByteBuffer.get` can all benefit from the page cache. Mapping **does not eliminate** the cost of bringing pages from storage into cache. It changes how data is accessed, not the physical limits of SSDs, HDDs, or networks.

### 3.3. System Calls, Memory Copies, and Page Faults

A `FileChannel.read(ByteBuffer)` may go through an OS call and copy bytes into the corresponding buffer. Memory mapping lets the program read the mapped region via memory operations once the mapping is established. However, mapping can incur **page faults**, mapping setup and page management costs, TLB pressure, map/unmap overhead, virtual address pressure, and cache interactions.

Reducing copy count **does not guarantee lower total cost** if you transfer one small chunk and tear down the mapping. For repeated random accesses on already-cached pages, mapping can be advantageous; for a single sequential scan, buffered streams or channels often achieve high throughput with less complexity.

### 3.4. Allocation and GC Overhead

`ByteBuffer.allocate(n)` creates a heap buffer; `ByteBuffer.allocateDirect(n)` creates a direct buffer with backing memory outside the Java heap. Direct buffers can suit certain native I/O paths, yet:

- Allocating/reclaiming direct buffers has cost.
- Native memory is not fully visible in heap charts.
- Creating many short-lived direct buffers can cause resource pressure.
- Some operations still require copies or creating views depending on APIs.
- There is no contract that “direct is always faster than heap.”

**Do not repeatedly allocate new buffers inside a copy loop if a buffer with a clear lifecycle can be reused.**

## 4. Performance Depends on the Workload

A sensible selection starts by describing the workload first:

| Workload | Reasonable candidates to test | Do not jump to conclusions |
| --- | --- | --- |
| Multi-KiB file, single read | `Files.readAllBytes` (if bounded), buffered stream | Mapping is definitely fast |
| Very large file, sequential read | Buffered stream, `FileChannel` + buffer, `Files.copy` | NIO definitely beats buffered streams |
| Copy an entire file | `Files.copy`, `transferTo`/`transferFrom`, buffered copy | `transferTo` is always zero-copy |
| Random access across many offsets | Positional `FileChannel.read`, memory mapping | Mmap always beats positional reads |
| Repeated access to a small region | Application cache, buffer reuse, small-region mmap | Mapping the whole file is optimal |
| Read once and discard file | Fixed-buffer streaming | Always map then let GC collect |
| Many small files | Simple `Files`/streams; measure file open overhead | An API optimal for one huge file stays optimal |
| Unknown data size | Streaming + byte limit | `readAllBytes` then check size afterward |
| File rotated, truncated, or written concurrently | Regular read/write channel with clear state | Mapping is safe against all size changes |

These suggestions only form a **list of benchmark candidates**, not a speed ranking.

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

This is an illustrative snippet, assuming `source`/`target` are valid `Path`s and required classes are imported. `close()` on buffered output flushes remaining buffered bytes per contract; errors during close still need handling. Some application buffer layouts can have **redundant buffering layers**, e.g. both `BufferedInputStream` and a 64 KiB read array, yet it remains an easy baseline to implement. You can try `Files.newInputStream` + a large array directly to see if the buffered wrapper helps in your specific workload.

### When Streams Are a Good Choice

- Data is processed **sequentially**, without needing seeks.
- Input is large or unbounded: you want memory bounded by a fixed buffer.
- Data flows through pipelines for compression, checksums, parsing, or encryption.
- Broad compatibility and simple, maintainable code are priorities.

### When Streams Are Not Enough

- You need to read/write at absolute offsets without changing file position.
- You need to operate on large ranges or multiple positions of the same file.
- There is an opportunity to optimize byte transfers between two channels.
- You need features like `FileLock`, `force`, or scattering/gathering.

Even when requirements lead to NIO, evaluate **total cost** rather than treating it as automatic proof of speed.

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

These are abridged API signatures for illustration, not a complete class.

`read` and `write` can complete **partially**; never assume `read` fills `ByteBuffer` or `write` drains all `remaining()` bytes in all situations. With positional I/O, the `position` parameter is an **absolute file offset**; overloads taking an offset **do not modify `channel.position()`**, though they still advance `ByteBuffer.position()` by the actual bytes transferred.

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

This is an illustrative snippet, assuming open file channels and imports. It handles **partial writes**, a critical correctness factor. For normal files in blocking mode, zero progress is abnormal; exact policy depends on channel type.

Adding another buffer layer does not guarantee high speed: too small a buffer incurs many calls; too large a buffer raises allocation cost and hurts cache/memory. Sizes like `4 KiB`, `64 KiB`, or `1 MiB` are only **measurement candidates**, not universal constants.

## 7. `FileChannel.transferTo` and `transferFrom`: Optimizable, Not Guaranteed Zero-Copy

`FileChannel.transferTo(long position, long count, WritableByteChannel target)` transfers a data range from the source file to a target channel.

Potential advantage: implementations can use native mechanisms to reduce intermediate steps when moving data between files and sockets or between supported channels. However, the Javadoc explicitly notes transferred bytes **may be fewer than `count`**, and depending on system/channel type, implementations **may fail to transfer everything or impose specific caps**.

Proper pattern when copying the entire file:

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

This snippet requires declaring `source` as `FileChannel` and `destination` as `WritableByteChannel`. Upon seeing 0, **do not spin forever**. Depending on API and device, switch to a buffer-based fallback, wait for readiness, or throw an error; this example throws an exception to avoid masking an incomplete copy.

**Do not infer:**

- There is any guarantee **every `transferTo` call is zero-copy**.
- “Zero-copy” means zero CPU, zero storage I/O, or no kernel memory involvement.
- Passing `count` guarantees transferring all `count` bytes in one call.
- Changing OS, JDK, filesystem, target type, or file size keeps the same optimal path.
- Copying from a file to **another file** and sending from a file to a **socket** use identical kernel paths; do not lump them into one unnamed benchmark.

If the system needs to copy files by `Path` without inspecting bytes, **`Files.copy`** is also a strong candidate. Its implementation can choose its own optimizations, so do not force everything through hand-written `transferTo` code.

## 8. Runnable Java 17 Example: Three Copy Approaches, Same Data

This example copies an 8 KiB file using three techniques:

1. Buffered stream.
2. `FileChannel` + `ByteBuffer`.
3. `FileChannel.transferTo`.

It **does not print timings** because deterministic stdout here serves to check correctness. A single small run on a cached file does not make a benchmark.

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

**Stdout under successful I/O conditions:**

```text
Buffered correct: true
Channel correct: true
Transfer correct: true
Original size: 8192
```

`Files.mismatch` (since Java 12) returns `-1` if two files are byte-identical. This check verifies **outputs**, not which method is faster.

### Example Breakdown

- Source file is generated with 8,192 deterministic bytes, independent of network data.
- Buffered copy reads/writes in 4,096-byte blocks.
- Channel copy follows the proper `clear → read → flip → drain remaining` cycle.
- Transfer copy uses a loop with `copied` so nothing is skipped if `transferTo` returns less than `count`.
- Target files have distinct names; code does not overwrite source.
- `try-with-resources` closes all handles before deleting temp files.

**If scaled to a very large file:** calling `Files.mismatch` reads the files to compare them, altering cache state. When measuring throughput, separate **copy time** from **verification time** (or report both clearly), and ensure approaches are compared under **identical input conditions**. Each run may require resetting target files, cache policy, and storage state.

## 9. What Memory Mapping Is — and What It Is Not

`FileChannel.map` maps a file region into the process's virtual memory, returning a `MappedByteBuffer` (the common API on Java 17):

```java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_ONLY,
        offset,
        length);
```

This is an illustrative snippet; `channel` must be opened in a compatible mode, and `offset`/`length` must be valid. Once mapped, `get(index)`/`getInt(index)` can access positions in the mapped region without calling `channel.read` for each element.

**However, mapping does not mean:**

- The entire file is loaded into RAM the moment `map()` returns.
- Accessing the first byte cannot incur a page fault.
- Data always stays in CPU cache.
- Kernel, OS, or filesystem are no longer involved.
- Errors never happen if another process truncates the file.
- A synchronous explicit unmap API exists on Java 17 `MappedByteBuffer`.
- It is always faster than `FileChannel.read`, even for small files opened, read once, and closed.

### When Is Mapping Worth Considering?

- Accessing different regions of a file **repeatedly** by offset.
- Lookup tables or binary data structures with easily computed record addresses.
- Many random reads over a mapping with a sufficiently long lifetime.
- Data that fits being viewed as a **memory byte region** with clear indices and format.

### When Should You Consider Avoiding It?

- Very small files opened and read once.
- Files needing immediate replacement/truncation/deletion where cross-OS portability matters.
- Sequential pipelines already achieving suitable throughput.
- Applications creating/destroying thousands of short-lived mappings.
- Input data whose size may be altered unexpectedly by another process.
- Environments with tight address space, native memory, or mapping count limits.

**Map to fit the workload; it is not a “turbo mode” for all I/O.**

## 10. Virtual Address Space, RAM, and Page Faults Are Three Different Things

When mmapping a file, the process gets a **virtual address mapping** to access file pages. Having a wide mapped region does not mean that many bytes were copied into the Java heap or are all resident in RAM.

Distinguish:

| Concept | Meaning |
| --- | --- |
| Java heap | Where objects, arrays, and part of GC-managed metadata live |
| Virtual address space | Process address space where the mapping places an access window |
| Resident memory | Physical memory pages currently resident, OS-dependent |
| Page cache | OS cache for file pages |
| Page fault | Accessing a page not yet ready in the mapping or needing mapping setup/storage fetch |
| `MappedByteBuffer` | Java view onto the mapped file region, constrained by `int` indexing |
| File descriptor/channel | I/O resource for opening the file; closing the channel does not necessarily unmap created regions |

Speed varies depending on whether data is already in the page cache. Random reads through a mapping can trigger erratic page faults; sequential reads through buffered streams let the OS recognize the pattern well and apply prefetch/read-ahead. In another workload, mapping can cut the overhead of many tiny positional `read` calls.

**Measure CPU, page faults, and I/O latency**, not just theoretical bytes read.

## 11. Java 17 Example: Random Access via FileChannel and Mmap Are Both Correct

The example below creates a binary file of four big-endian integers and reads the third integer (index 2) using:

1. `FileChannel.read(dst, offset)` from an absolute position.
2. `MappedByteBuffer.getInt(index)` from a read-only mapping.

Goal: demonstrate **result equivalence** on this data and distinguish state models. No claim is made about which is faster from a few bytes.

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
- `readIntAt` loops until all 4 bytes are read using `offset + received`; the positional read overload does not change `channel.position()`.
- `mapped.getInt(8)` is an absolute access inside the mapped buffer; no `channel.read` call is needed for `getInt`.
- Before the reads, the channel was set to `position(1)`, and neither read alters this value.
- Both return 30, yet **correctness alone implies neither equal performance nor superiority**.

**Lifecycle note:** the example uses `deleteOnExit()` instead of deleting the temp file immediately after creating a mapped buffer, because on some platforms live mappings affect delete/rename operations. `deleteOnExit` is also only a best-effort cleanup on JVM exit and does not guarantee file deletion in all scenarios; long-running applications need an explicit lifecycle management policy.

### Byte Order Matters

`MappedByteBuffer` and `ByteBuffer` have a `ByteOrder`. For big-endian formatted data, configure/interpret consistently. With mismatched endianness, two reads can return different values even though both read the exact same bytes. Never use buggy parser results to conclude which API is fast or slow.

## 12. Specific Limits of `MappedByteBuffer` on Java 17

`MappedByteBuffer` extends `ByteBuffer`, whose `capacity`, `position`, and `limit` are represented as `int`. Therefore, **a single mapping returning `MappedByteBuffer` cannot arbitrarily span a multi-terabyte file**. Java SE 17 `FileChannel.map` bounds `size` by buffer limits; practically, each mapped region is capped at up to `Integer.MAX_VALUE` bytes.

**To process a file larger than one buffer's limit**, split it into windows:

```text
10 GiB File
   |
   +-- map window #1 (e.g. 256 MiB)
   +-- map window #2 (256 MiB)
   +-- ...
   +-- map window N (final part)
```

Yet mapping many windows carries creation/management costs; never assume **more mappings is faster**. The system may cap mapping counts, file descriptors, or address space, especially in 32-bit environments or constrained containers.

### Cleanup/Unmap Is Not Determined by `FileChannel.close()`

With the traditional Java 17 `FileChannel.map(MapMode, long, long)` API:

- The mapping may remain valid **after `FileChannel` is closed**.
- `MappedByteBuffer` does not expose a standard public `close()`/`unmap()`.
- Unmap timing depends on memory/GC lifecycle, not `clear()` or `force()`.
- Renaming/deleting/truncating an actively mapped file behaves differently across OSes and filesystems.

This directly impacts benchmarks and production systems: if each benchmark pass maps a new region without controlling old mapping lifetimes, measurements can accumulate resources and become unfair.

**Version note:** Starting in Java 22, standard APIs added `FileChannel.map(..., Arena)` returning `MemorySegment`, enabling lifecycle management through a closeable arena. That is a **different API** and does not give Java 17 `MappedByteBuffer` a `close()` method. When Java 17 compatibility is required, do not use Java 22-only overloads.

## 13. How Can Memory Mapping Make Work Slower?

Several counter-intuitive scenarios:

### 13.1. A Small File Read Once

Mapping setup, page faults, and cleanup costs can exceed the savings from fewer `read` calls. A single `Files.readAllBytes` or buffered stream can be simpler and faster in that specific test.

### 13.2. Very Large Sequential Reads

The OS can perform effective read-ahead for sequential read calls. Memory mapping can also be optimized depending on pattern, yet incurs page faults and depends on how CPU/OS handle accesses. There is no fixed winner.

### 13.3. Many Short-Lived Mappings

Instead of reusing a long-lived mapping, constantly mapping and unmapping incurs metadata and native memory overhead. With the legacy API, unmap timing also depends on GC. Thus “open → map → read 1 byte → drop mapping” is rarely optimal.

### 13.4. Files Frequently Truncated or Rotated

Keeping a mapping alive while a file changes size can make parts of the region inaccessible; failure behavior can be OS-dependent. For rotated logs, temp files, or spools deleted frequently, buffered `FileChannel`/reads can be easier to manage.

### 13.5. Memory Pressure and Resource Contention

Mapping does not copy the whole file onto the heap, yet can increase pressure on address space, page tables, and caches. On multi-service hosts, an mmap workload may evict another service's cache or suffer more page faults itself than expected.

**Performance evaluation looks not only at one task's duration, but also its impact on the whole system.**

## 14. `Files.copy`: Do Not Overlook the High-Level API

If the goal is simply copying a file:

```java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

`Files.copy` is usually simpler than writing multiple `read`/`write` loops, with clear intent and appropriate option support. Implementations can leverage filesystem/provider-based optimizations.

**However**:

- Do not assume all providers handle copying identically.
- `COPY_ATTRIBUTES` and `REPLACE_EXISTING` govern metadata and name-collision behavior, not speed guarantees.
- Never count benchmark results without verifying the target file is valid.
- Copying metadata, permissions, and symlinks differs by API/options and filesystem.
- Copy operations can fail mid-way; business code must decide cleanup/rollback.

For data requiring inspection/checksums or transformation, streaming chunks yourself can be clearer. For ordinary full-file copies, **include `Files.copy` in your list of candidates to measure**.

## 15. How to Design a Fair Benchmark

### 15.1. Define the Question Before Measuring

Example of a meaningful question:

> “On this SSD, with a 4 GiB file read sequentially into a checksum, how do throughput of a 64 KiB buffered stream, 64 KiB `FileChannel`, and 256 MiB windowed mapping compare under warm cache and cold cache?”

An unclear question:

> “Is NIO faster than IO?”

The second lacks workload, device, size, cache state, test conditions, and success criteria.

### 15.2. Control Influencing Variables

| Variable | Why it must be controlled |
| --- | --- |
| JVM/JDK and flags | JIT, GC, and runtime implementations can differ |
| OS, filesystem, storage | Affects native I/O paths, page cache, throughput |
| File size and data distribution | Small/large files, compression, and file sparsity differ |
| Access pattern | Sequential vs. random, read/write ratio |
| Warm/cold cache | OS page cache can dominate results |
| Repetitions and warmup | JIT/GC/OS scheduler introduce noise |
| Concurrency | I/O queue depth, contention, and memory pressure |
| Buffer size and allocation | Can turn API differences into block-size differences |
| Copy target | Same SSD volume, cross-volume, socket, network mount |
| Write durability | `force/fsync` dramatically changes latency |
| Verification and setup | Costs CPU/I/O; isolate from core operation timing |
| Error/partial I/O handling | Broken fast code is not a win |

When measuring, vary **only one design dimension** within a comparison group (e.g. switch I/O mechanism while keeping block size and inputs equivalent), then test other dimensions separately. Comparing a byte-by-byte stream against a 1 MiB `FileChannel` and concluding “NIO is faster” compares **two algorithms with different operation counts**, failing to isolate the API's effect.

### 15.3. Warmup and Execution Order

The first few benchmark runs may include:
- Class loading and JVM/JIT initialization.
- Buffer allocation, file opening, and metadata creation.
- File pages not yet in cache.
- Background processes and GC.

If you always run Stream first and Mmap second, Mmap may enjoy cache warmed by Stream. If you always invert it, whichever runs first takes the hit. **Alternate/rotate execution order, repeat many passes, and report result distributions.** When benchmarking cold cache, only use methods that truly control cache state and document how; reading a file under a new name does not guarantee cold data at the OS level.

**Never drop caches system-wide on an active service environment** just to get clean numbers: it disrupts other workloads and does not reflect real production conditions.

### 15.4. Separate Throughput and Latency

One approach may achieve high **MB/s throughput** copying big files yet have poor **per-lookup latency** if it maps/unmaps every time. Another may optimize random lookups once mapped yet perform poorly on cold startup.

Useful metrics:

- Total copy or scan duration, in ms/s.
- Throughput in MiB/s: `bytes / elapsedSeconds / 2^20`.
- Per-operation latency, median, p95, p99 when appropriate.
- User/system CPU, page faults, syscall counts, context switches.
- GC pauses/allocation rate, direct/native memory, resident memory.
- Actual disk reads/writes, IOPS, filesystem cache hits/misses if measurable.
- Error rate, partial transfer count, setup/cleanup time.

Never claim “3× faster” without repeated runs, test conditions, and correctness checks.

## 16. A Simple Timing Snippet — Exploratory Only, Not Proof

`System.nanoTime()` is suitable for measuring elapsed intervals inside the JVM, not wall-clock dates/times. A very simple timing helper:

```java
long start = System.nanoTime();
copyOperation.run();
long elapsedNanos = System.nanoTime() - start;

double millis = elapsedNanos / 1_000_000.0;
System.out.printf("Elapsed: %.3f ms%n", millis);
```

This is a **non-standalone illustrative snippet**, assuming `copyOperation` is a declared task. The `Elapsed` number is **not fixed** and must never be treated as a guaranteed outcome.

If writing a simple benchmark yourself:

1. Create inputs outside the timed region.
2. Keep every approach doing the **exact same work**.
3. Place setup/allocation/open/close inside or outside the timer **according to your goal**; if comparing end-to-end in production, include their overhead.
4. Avoid logging inside the timed section.
5. After each pass, verify data (outside the timer if appropriate).
6. Run multiple passes, interleave order, and compute medians/dispersion.
7. Monitor cache/GC/paging to explain outliers.
8. Conclude only for the measured configuration; avoid overgeneralizing.

JMH (Java Microbenchmark Harness) is very helpful for pure CPU/JIT code; yet for file I/O, JMH **does not automatically control OS page cache, devices, filesystems, or resource contention**. System-level I/O benchmarks are needed, optionally paired with profiling tools like JFR, `jcmd`, and OS counters.

## 17. A More Useful Testing Approach Than “Is NIO Faster?”

Set up a test matrix instead of picking only 2 APIs:

| Workload | Data size | Pattern | Candidates |
| --- | --- | --- | --- |
| Very small | 1–16 KiB | Full file copy | `Files.copy`, buffered stream, channel |
| Medium | 1–32 MiB | Sequential copy | buffered stream, channel, `transferTo` |
| Large | 1–8 GiB | Sequential copy | buffer/`transferTo`/`Files.copy` |
| Random lookup | 1 GiB | 8-byte records | positional `FileChannel`, mmap windows |
| Repeated access | 256 MiB | Hot random reads | channel with managed cache, mmap |
| Many small files | 10,000 files | Open+read+close | `Files`/stream, channel |
| Transformed reads | Arbitrary | Hash/parse | streaming buffer, channel with buffer |

**Test warm and cold-ish separately**, and for large files ensure the benchmark does not silently degrade into a RAM-cache test (e.g., datasets too small relative to RAM can produce misleading “disk throughput” numbers).

Each workload needs its own metric: files/s for many small files, MiB/s for sequential copies, p95 latency for random lookups, memory/cleanup time for short-lived mappings.

## 18. Factors That Can Skew Benchmarks

### 18.1. Running Faster by Reading Too Few Bytes

A `FileChannel.read(buffer)` call can return fewer bytes than `remaining()`. If code omits the loop and processes only the initial bytes, it runs faster simply by **skipping data**. Likewise, `transferTo` can transfer partially; non-looping code returns early before the target file is complete.

Always verify byte counts and checksums/`Files.mismatch` after running.

### 18.2. Changing Speed by Accidentally Changing Buffer Size

`BufferedInputStream` with a default buffer, `FileChannel` with a 1 MiB direct buffer, and full-file mmap have very different footprints. To attribute gains to an API, control or at least clearly report buffer sizes and allocation reuse.

### 18.3. Mixing Hot and Cold Caches

An approach run second benefits from the one run first. Never use a single run to represent an entire system.

### 18.4. Biased Exclusion of Setup

If the mapping is created outside the timer while the stream must open the file inside the timer, the test can bias toward mmap. Conversely, if the real application reuses a mapping for hours, a **steady-state measurement excluding startup** is justified. It is not absolute right/wrong, but about **defining the question clearly** and measuring startup/end-to-end as well if needed.

### 18.5. Counting `write()` as Durability

When `write` returns, data typically sits in OS caches or queues, not necessarily on durable storage. `FileChannel.force(...)` or `MappedByteBuffer.force()` may be needed depending on durability requirements.

If approach A calls `force` and B does not, you cannot declare B “faster” for the same data safety level. Compare at equal durability and error-handling guarantees.

### 18.6. Native Memory Not Fully Visible in Heap Metrics

Mmap and direct buffers can consume native memory/virtual addresses or add page cache pressure without appearing directly in `Runtime.totalMemory()-freeMemory()`. Track RSS/process memory, Native Memory Tracking when appropriate, OS mapping stats, and page faults.

### 18.7. Compressed, Sparse, or Copy-on-Write Files

Some filesystems support compression, sparse files, or *reflink/copy-on-write*. A copy may finish fast because the filesystem optimizes metadata/copy semantics rather than transferring every byte through storage. That has real workload value, yet must be documented since it does not prove the Java API is equally fast on every filesystem.

## 19. Mapping-Specific Correctness Issues

### 19.1. When a File Is Truncated While a Mapped Buffer Is Alive

If a file is resized or truncated while the program accesses a mapping, part of the mapped region can become invalid. Access behavior then has OS-dependent aspects. Do not assume `mapped.get(index)` always yields a valid byte merely because `index < mapped.capacity()`.

When other writers exist, coordinate via snapshots, versioning, or locking; mapping does not automatically lock file contents.

### 19.2. `force()` Is Not `unmap()`

`MappedByteBuffer.force()` requests flushing mapped changes (under suitable conditions) per contract; it does not release the mapping. `clear()` only resets buffer `position`/`limit`. `FileChannel.close()` closes the channel without guaranteeing legacy mappings are unmapped.

Lifecycle confusion can cause file-deletion issues on some OSes, leak virtual address space in long-running processes, and make short benchmarks unrepresentative of production.

### 19.3. Mapping Does Not Provide Arbitrary Atomic Updates

Writing a multi-field structure through a mapped buffer does not create an atomic transaction. Readers in another process can observe half-updated state without a coordination protocol. For sensitive data or consistency-critical files, use locking, versioning, checksums, journaling, or transactional storage.

Never pick mmap just to “write faster” while ignoring consistency.

## 20. Choosing Buffer Sizes from Measurements and Memory Limits

Every buffer affects:

- **Per-read/write overhead**: small buffers can trigger many calls.
- **Heap/native allocation**: larger buffers consume more resources.
- **CPU cache locality**: patterns can impact cache efficiency.
- **Concurrency**: if each connection/task holds its own buffer, buffer size multiplies by concurrency.
- **Latency**: overly large buffers can raise processing latency in some pipelines.
- **I/O scheduler/readahead**: OS and devices behave differently.

Simple budget math: if 200 tasks each hold a 1 MiB buffer, buffers alone take roughly **200 MiB**. With two buffers per task, roughly 400 MiB, excluding parsers and other objects. `ByteBuffer.allocateDirect` does not make resources free just by living off-heap.

**Techniques to consider:** bounded buffer pools, buffer reuse, bounded concurrency, admission control, and chunked streaming; combined with GC/native memory measurements.

## 21. Input Bounds and Protection Against Resource Exhaustion

Good performance is not just copying fast under normal conditions. Large or untrusted inputs also require:

1. **Byte limits** before and during reading — do not trust metadata alone.
2. **Timeouts/deadlines** to prevent hung threads or ultra-slow senders.
3. **Temp file size and disk quotas** when copying/extracting to disk.
4. **Concurrency and queue bounds** to avoid creating thousands of huge buffers.
5. **Rollback mechanisms** when a copy fails to complete.
6. **Integrity checks and publishing** once data is complete.
7. **Post-decompression limits** if sources are ZIP/GZIP.

`Files.readAllBytes` is convenient yet allocates memory proportional to file size; never run it on unbounded input and check size afterward. With memory mapping, never think mmapped files “use no RAM”: they still participate in page cache, RSS, address-space management, and page faults.

Often an approach with slightly lower average benchmark speed that is **stable, easy to clean up, and memory-bounded** suits production better than one hitting high peak throughput at the risk of uncontrolled resource growth.

## 22. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| “NIO is always faster than IO.” | The API alone does not dictate all costs | Benchmark by workload |
| “mmap reads from RAM, not disk.” | Page faults may still fetch data from storage | Account for page cache, warm/cold |
| “`transferTo` is always zero-copy.” | Implementation/path/target may differ | Measure by OS/channel, handle partial |
| “One `transferTo` copies the full `count`.” | Can transfer fewer bytes than requested | Loop accumulating bytes |
| “One `FileChannel.write` sends the whole buffer.” | Partial writes can happen | Loop on `hasRemaining()` |
| “Switching heap `ByteBuffer` to direct is always faster.” | Allocation/native memory has cost | Measure, reuse, bound memory |
| “Mmap for small files will be faster.” | Setup/map/page faults can dominate | Try buffered/`Files` baseline |
| “Map an entire multi-TB file into one Java 17 buffer.” | `ByteBuffer` uses `int` indexing | Split into windows or use another API |
| “Closing the channel unmaps.” | Legacy mappings have independent lifecycles | Manage mapping lifecycles |
| “`mapped.force()` frees the mapping.” | Force is persistence, not release | Distinguish flush from unmap |
| “Second file measuring faster proves an API is better.” | Second run may hit a warm cache | Interleave order, control cache |
| “Measuring once and printing one millisecond value proves it.” | JIT/GC/OS noise | Warm up, repeat passes, use statistics |
| “Skipping verification during benchmarks.” | Buggy incomplete code looks fast | Check byte count/hash/mismatch |
| “Checking Java heap alone is enough.” | Native mappings/buffers use other resources | Track RSS/page faults/native |
| “Benchmark excludes cleanup while production pays it.” | Measures a different workload | Report both steady-state and end-to-end |
| “`write` finished means guaranteed durable.” | Cache/flush semantics differ | Compare at equal force/durability |
| “Always mmap files being written/truncated constantly.” | Invalid mapping/OS-dependent failure risk | Coordinate writers, snapshot, or regular I/O |
| “A 1 MiB buffer is best for every workload.” | Overhead/memory/concurrency differ | Sweep buffer sizes |

## 23. Practice Exercises

### Exercise 1: Single 4 KiB File Copy

You are copying a 4 KiB file whose output must be byte-exact. Should you open a `MappedByteBuffer` by default?

**Hint:** start with `Files.copy` or a buffered stream and measure if there is a clear need to optimize. For small files, mapping setup overhead can be significant relative to transferred data. Do not claim mmap is always slow; just do not default to it.

### Exercise 2: Checking `transferTo` Output

A call `source.transferTo(0, 10_000, target)` returns `4096`. Does the target file have all 10,000 bytes yet?

**Not yet.** Only 4,096 bytes were reported transferred in that call. You must continue from offset 4,096 for the remaining 5,904 bytes, check progress/errors, and verify the target.

### Exercise 3: Cache Skewing Conclusions

You run buffered streams first, then mapping next and observe mapping is much faster. Can you conclude mapping is better?

**No.** The first stream may have warmed the file in the OS page cache, or JIT/CPU/storage states differed. Repeat, invert order, control caches, and report conditions.

### Exercise 4: Random Lookup on a Large File

An application reads an 8-byte record at 100,000 random offsets in a large data file repeatedly. Which candidates are worth benchmarking?

**Both positional `FileChannel.read` and memory mapping** are worth testing, potentially with application-level caching. Mapping can cut repeated `read` call overhead while possibly raising page faults/cache pressure. Decide based on measurements under your actual workload.

### Exercise 5: Closing Channel After Map

`FileChannel.close()` was called after creating a read-only mapping on Java 17. Can you guarantee the file can be deleted immediately on every OS?

**No.** Legacy `MappedByteBuffer` has an independent mapping lifecycle, and Windows plus certain environments may restrict deleting/renaming actively mapped files. Cleanup logic must not rely on flawed portability assumptions.

### Exercise 6: “Faster” by Skipping Fsync

Two file write approaches: A calls `force(true)` after writing, B does not. B finishes sooner. Can you conclude B is optimal for the same durability requirement?

**No.** The two approaches provide **different levels of data synchronization guarantees**. Compare under the same durability contract.

### Exercise 7: Is FileChannel Non-Blocking Like SocketChannel?

**No.** `FileChannel` is a file channel with normal `read/write` operations and has no `configureBlocking(false)`/`Selector` support like network `SelectableChannel`s. NIO does not mean non-blocking for every channel.

### Exercise 8: Same Throughput, Different RAM

64 KiB buffered stream-copy and `Files.readAllBytes` on a 3 GiB file achieve similar throughput on a test machine. Which approach usually keeps memory easier to control?

**Streaming with bounded buffers**, because `readAllBytes` tries to allocate an array holding the entire file, which may fail to allocate and consumes huge heap; stream-copy never holds all input bytes in one array. You must still bound outputs and intermediate data.

## 24. Real-Project Decision Checklist

**Before optimizing:**

- Describe the workload: file sizes, file counts, sequential/random, read/write, one-off or repeated, concurrency.
- Define correctness: byte counts, integrity, EOF, partial reads, cleanup, and data durability.
- Identify constraints: RAM, address space, file descriptors, latency SLOs, platform/JDK.
- Choose a simple baseline: `Files.copy`, buffered streams, or `Files.newInputStream`.

**When testing NIO and mmap:**

- For channels: use sensible buffers, handle partial I/O, avoid reallocating per pass.
- For transfers: check actual transferred bytes, implement fallback/error on zero progress.
- For mmap: include setup cost, page faults, unmap lifecycle, truncate/rename behavior, and window sizes.
- Compare with identical inputs and durability policies.
- Measure total time, throughput, latency, CPU, heap/native memory, and page cache/paging.

**When reporting results:**

- Record JDK version, OS, filesystem, device, file size, cache state, and buffer size.
- Disclose run counts, warm-up methodology, and summary statistics.
- Separate cold/warm and steady-state/end-to-end when appropriate.
- Verify all approaches yield identical outputs.
- Recommend an option as “faster” **only for the measured workload**, without turning it into a universal law.

## 25. Summary

No single choice always wins among **Buffered I/O**, **FileChannel**, **`transferTo`**, **`Files.copy`**, and **`MappedByteBuffer`**.

- **Buffered streams** are simple, fit sequential access, and can be very effective.
- **FileChannel** is useful for positional I/O and `ByteBuffer` operations; being NIO does not guarantee it is faster.
- **`transferTo`/`transferFrom`** open opportunities to optimize data movement; handle partial transfers and do not assume zero-copy always happens.
- **Memory mapping** can be convenient, especially for repeated random access, yet introduces page faults, metadata, native resource costs, and mapping lifecycles to manage.
- **Page cache, filesystem, OS, JVM, and workload** are the true governing variables; warm/cold conditions matter.
- **Controlled benchmarking + correctness verification** form the basis of selection, not API names or single-run timings.

**Practical rule:** start with a **correct, understandable, and bounded** solution, find bottlenecks through measurement, and only increase complexity when gains are provable while still meeting stability, portability, and maintainability goals.

**Java SE 17 Documentation:**

1. [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html) — `read/write`, positional I/O, `transferTo`, `transferFrom`, `map`, `force`.
2. [MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html) — mapping semantics, `load/isLoaded/force`.
3. [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html) — heap/direct buffers, `position/limit`.
4. [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `copy`, `newInputStream`, `mismatch`.
5. [BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html) and [BufferedOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html).
