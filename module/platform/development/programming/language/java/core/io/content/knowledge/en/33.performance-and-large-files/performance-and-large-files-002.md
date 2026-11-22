# Choosing Buffer Size by Measurement in Java I/O and Large File Processing

## 1. Why Is There No Universal Optimal Buffer Size?

When reading and writing large files, a Java program may use `InputStream`, `BufferedInputStream`, `BufferedOutputStream`, `FileChannel`, and `ByteBuffer`. Buffer size is the number of bytes that can be accumulated or transferred in one operation round. It affects **I/O call count**, **CPU**, **throughput**, **latency**, **heap/direct memory**, and the ability to serve many concurrent tasks.

A buffer that is too small easily increases overhead because the program must perform many read/write rounds. However, **increasing the buffer endlessly does not mean speed increases endlessly**: once the storage device, operating system, cache, or CPU hits a bottleneck, a larger buffer may yield virtually no throughput gain while consuming extra RAM.

Therefore, the right answer to "should I use 4 KiB, 8 KiB, 64 KiB, 256 KiB, or 1 MiB?" is **choose by measuring on the real workload**. There is no single fixed number applicable across SSD/HDD, NFS, few-kilobyte files, or multi-hundred-gigabyte files.

This article belongs to **Java Core I/O → Performance and Large Files**. The content guides you through defining measurement variables, designing benchmarks, distinguishing heap/direct buffers, running Java 17+ programs, analyzing saturation points, and selecting a size that balances performance and resources.

## 2. Mechanism: How Does Buffer Size Affect I/O Call Count?

Suppose you need to sequentially read a file of exactly 1 GiB (1,073,741,824 bytes). **If every read completely fills the buffer**, the theoretical number of reads is:

| Buffer | Full-buffer reads for 1 GiB |
| ---: | ---: |
| 4 KiB | 262,144 |
| 8 KiB | 131,072 |
| 16 KiB | 65,536 |
| 64 KiB | 16,384 |
| 256 KiB | 4,096 |
| 1 MiB | 1,024 |

General formula:

```text
estimatedCalls = ceil(fileBytes / bufferCapacity)
```

This is **not the actual syscall count guaranteed by the API**: a `read()` call can receive fewer bytes than requested, and some stream layers or filesystem providers may perform multiple operations under the hood. If a 64 KiB buffer still has room but `read()` returns only 1 KiB, that call is completely valid.

With `FileChannel.read(ByteBuffer)`, a basic pattern is:

```java
ByteBuffer buffer = ByteBuffer.allocate(64 * 1024);

try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    while (true) {
        buffer.clear();
        int n = channel.read(buffer);

        if (n == -1) break;
        if (n == 0) continue;

        buffer.flip();
        while (buffer.hasRemaining()) {
            byte value = buffer.get();
            // Process byte from the current read round.
        }
    }
}
```

This is an **in-method snippet**, requiring `import java.nio.*`, `import java.nio.channels.FileChannel`, `import java.nio.file.*`, a `path` variable, and `IOException` handling. It illustrates proper reading, not a benchmark. If a channel can repeatedly return `0`, do not use a `continue` loop without an appropriate wait mechanism. For a file channel reading into a buffer with remaining space, a `0` result is normally not an infinite loop state.

`clear()` **only resets** `position=0`, `limit=capacity`, without erasing old data. `flip()` bounds the readable range to the exact newly received bytes; the parser must not read the entire backing array and accidentally consume bytes from the previous round.

### 2.1. When Small Buffers Cause Overhead

- More Java method calls and potentially more native I/O operations.
- More frequent `position`, `limit`, loop branch management, or parser/decoder invocations.
- If the application flushes or writes overly small blocks, synchronization/flush costs can be high.
- For connections with latency or servers handling many requests, increased processing rounds degrade throughput/CPU.

### 2.2. When Large Buffers Yield Diminishing Returns

- Disk, OS cache, or parser CPU may already be the bottleneck.
- Many concurrent requests holding large buffers cause heap/direct-memory pressure.
- Copying, decoding, checksumming, or business logic may outweigh the benefit of fewer read rounds.
- If the application layer tries to fill the buffer before processing, **time-to-first-result** can increase—do not confuse this with default behavior of every `read()`: Java does not always wait for a buffer to fill.
- Files smaller than the buffer may not benefit from increasing buffer size.

From this emerges the principle: **find the performance saturation point, then prefer the smaller, stable configuration**.

## 3. Buffer Types to Distinguish

### 3.1. Heap ByteBuffer

```java
ByteBuffer buffer = ByteBuffer.allocate(64 * 1024);
```

A heap buffer stores bytes on the Java heap, has a backing array, and is often convenient for code working with `byte[]`. Allocating many new buffers can create extra objects and GC pressure.

For streaming file reads, **reusing a single buffer** outside the loop is usually more important than debating 64 KiB versus 128 KiB.

### 3.2. Direct ByteBuffer

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);
```

A direct buffer typically uses memory outside the Java heap. According to `ByteBuffer` documentation, the JVM makes a **best effort** to perform native I/O directly to avoid some intermediate copies. That **does not guarantee** direct is always faster than heap.

Characteristics to measure:

- Allocation/deallocation cost for direct buffers is usually higher than non-direct.
- Direct memory capacity is still a real resource, subject to quotas and `OutOfMemoryError` risk.
- `buffer.array()` cannot be assumed to work on a direct buffer.
- `clear()` does not free or zero out the memory region.
- Creating a direct buffer once and reusing it is a very different choice from creating a direct buffer per request.

If you need to compare heap and direct, **keep all other parameters identical**: same file, size, access pattern, thread count, warm-up, and byte-processing logic.

### 3.3. BufferedInputStream/BufferedOutputStream

```java
try (InputStream in = new BufferedInputStream(
        Files.newInputStream(path), 64 * 1024)) {
    // Read file via InputStream API.
}
```

This snippet requires importing `java.io.*`, `java.nio.file.*`, plus a `path` variable.

`BufferedInputStream` is useful when the application performs many small reads, especially byte-by-byte or very short blocks. However, if the application already reads large blocks using `FileInputStream.read(byte[])`, adding a wrapper with a smaller buffer **does not guarantee** higher throughput. The code path of each overload, copy costs, and actual data determine the outcome.

You must distinguish **the wrapper's buffer**, **the `byte[]` used by the application**, **the OS page cache**, and **the device buffer**. They exist at different layers.

### 3.4. Memory-Mapped Files and transferTo

`FileChannel.map()` with `MappedByteBuffer` changes the access mechanism into a mapped memory region; `FileChannel.transferTo()` can optimize byte transfers between channels. They are **not simply picking a different buffer size** inside a `read()` loop. If the task is actually file copying or random access, benchmark mapping/transfer as separate alternatives producing the same business output.

## 4. Choose Measurement Goals Before Writing Code

A backup application may treat **throughput** as the top metric; a request-serving application may consider **p99 latency** and memory per connection more critical.

| Metric | Meaning | How to Observe |
| --- | --- | --- |
| Throughput | Total MiB processed per second | Measure actual bytes received / time |
| Per-file latency | Time to complete one file | Statistics: median, p95/p99 |
| CPU | Processing, copy, parser, checksum | Observe CPU utilization/profiler |
| GC | Allocations and pauses from heap buffers/objects | JFR, GC logs, profiler |
| Direct memory | Live native/direct buffer memory | JVM quotas, native memory/profiler |
| I/O calls | Actual read/write call count | Code instrumentation or system tracer |
| Peak concurrency | Concurrent requests holding buffers | Counters/quotas |
| Correctness | Byte count and contents are truly accurate | Byte count, checksum/hash, tests |

Throughput formula:

```text
MiB/s = bytesProcessed / (1024 × 1024) / seconds
```

**MiB** (2²⁰ bytes) differs from **MB** (10⁶ bytes). When comparing result tables, always state the exact unit and never use assumed byte counts when partial reads/writes occur in reality.

Before running, ask yourself:

- Reading, writing, copying, parsing, or decompressing?
- Local SSD, HDD, NFS, network share, or data already in cache?
- Are typical files 1 KiB, 32 MiB, 10 GiB, or mixed?
- Single job or thousands of concurrent jobs?
- Is `force()/fsync` needed on write to meet durability requirements?
- Can the data change between measurement runs?
- Should we prioritize throughput, latency, or RAM limits?

## 5. Buffer Size Range to Explore

A helpful initial test sweep:

```text
4 KiB → 16 KiB → 64 KiB → 256 KiB → 1 MiB
```

This is a **candidate sequence**, not a recommendation that 1 MiB is always best. Stepping coarsely finds the improvement region quickly; afterward, you can test 32, 96, 128, or 192 KiB around the saturation point.

**Do not pick a value solely because it was largest in a single benchmark**. If 64 KiB reaches 95% of peak performance and 1 MiB is only slightly ahead within margin of error, 64 KiB may be the better decision because it consumes less memory and scales more easily to many tasks.

The 95% threshold is only an example of a **project selection criterion**, not a law of the JVM.

## 6. Runnable Java 17+: Benchmark Reading a File with Multiple Buffer Sizes

The following program creates a **16 MiB** temporary file, then measures sequential scans using `FileChannel.read(ByteBuffer)` with heap and direct buffers. Each configuration runs two warm-up rounds and five measured samples; the median is chosen to reduce outlier impact.

**Measurement design:**

1. Write the fixture **outside** the timed region.
2. Open the channel and allocate the buffer **before** starting `nanoTime()`, to isolate read-loop time.
3. Reuse the buffer throughout a run.
4. Every run reads all the way to EOF, verifying total bytes equal `FILE_BYTES`.
5. Do not parse bytes, only count bytes returned by `read()`; this benchmarks **data reading**, not business processing.
6. Do not force-evict the OS page cache; subsequent runs may primarily measure warm-cache.

Create `BufferSizeBenchmark.java`:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.Locale;

public class BufferSizeBenchmark {
    private static final int FILE_BYTES = 16 * 1024 * 1024;
    private static final int WARMUP = 2;
    private static final int SAMPLES = 5;
    private static final int[] CAPACITIES = {
        4 * 1024, 16 * 1024, 64 * 1024,
        256 * 1024, 1024 * 1024
    };

    private static void createFixture(Path file) throws IOException {
        byte[] block = new byte[8192];
        for (int i = 0; i < block.length; i++) {
            block[i] = (byte) (i & 0xff);
        }

        try (OutputStream out = Files.newOutputStream(file)) {
            int remaining = FILE_BYTES;
            while (remaining > 0) {
                int n = Math.min(remaining, block.length);
                out.write(block, 0, n);
                remaining -= n;
            }
        }
    }

    private static long oneRun(
            Path file, int capacity, boolean direct) throws IOException {

        ByteBuffer buffer = direct
                ? ByteBuffer.allocateDirect(capacity)
                : ByteBuffer.allocate(capacity);

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ)) {

            long bytesRead = 0;
            long started = System.nanoTime();

            while (true) {
                buffer.clear();
                int n = channel.read(buffer);

                if (n == -1) {
                    break;
                }
                if (n == 0) {
                    throw new IOException(
                            "No progress with nonempty buffer");
                }
                bytesRead += n;
            }

            long elapsed = System.nanoTime() - started;
            if (bytesRead != FILE_BYTES) {
                throw new IOException("Read " + bytesRead
                        + " instead of " + FILE_BYTES);
            }
            return elapsed;
        }
    }

    private static void measure(
            Path file, int capacity, boolean direct) throws IOException {

        for (int i = 0; i < WARMUP; i++) {
            oneRun(file, capacity, direct);
        }

        long[] times = new long[SAMPLES];
        for (int i = 0; i < times.length; i++) {
            times[i] = oneRun(file, capacity, direct);
        }

        Arrays.sort(times);
        long medianNs = times[times.length / 2];
        double elapsedSeconds = medianNs / 1_000_000_000.0;
        double throughputMiB = (FILE_BYTES / 1_048_576.0)
                / elapsedSeconds;
        double millis = medianNs / 1_000_000.0;

        System.out.printf(Locale.ROOT,
                "%-6s %5d KiB: median %.3f ms; %.2f MiB/s%n",
                direct ? "direct" : "heap",
                capacity / 1024, millis, throughputMiB);
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("buffer-benchmark-", ".dat");
        try {
            createFixture(file);
            System.out.println("Fixture bytes: " + Files.size(file));

            for (boolean direct : new boolean[] {false, true}) {
                for (int capacity : CAPACITIES) {
                    measure(file, capacity, direct);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run:

```bash
javac BufferSizeBenchmark.java
java BufferSizeBenchmark
```

The **fixed first line of output** when the temporary file is written and readable:

```text
Fixture bytes: 16777216
```

Afterward, the program prints ten lines—one for each heap/direct configuration and size of 4, 16, 64, 256, 1024 KiB. **Timing and MiB/s numbers vary by host machine**, so there is no fixed numeric stdout reliable enough to copy into documentation. The output format is:

```text
heap       4 KiB: median <time> ms; <throughput> MiB/s
...
direct  1024 KiB: median <time> ms; <throughput> MiB/s
```

The `<...>` placeholders and `...` line above represent positions of **actual measured values**, not literal output or pre-measured results. Do not present fabricated numbers as real benchmarks.

### 6.1. Program Analysis

- `createFixture()` writes in 8 KiB blocks to create a 16 MiB file without needing a `byte[]` as large as the file.
- `oneRun()` allocates a `ByteBuffer` before timing starts, then opens `FileChannel` in `try-with-resources`.
- `buffer.clear()` opens the receive range from `position=0` to `capacity`. Because the test **only counts bytes** and does not process the read content, `flip()` is unnecessary between iterations.
- `read()` returns actual bytes transferred, `-1` means EOF; the code rejects `0` when a file channel and non-empty buffer make no progress, preventing an infinite busy loop in the demo.
- `bytesRead` accumulates **the return value of each read**, rather than estimating from capacity. The post-loop check catches truncated or modified fixtures.
- Each configuration has warm-up and measured samples. Sorting and taking the middle element is a simple median calculation for five samples.
- `System.nanoTime()` is an elapsed-time clock, not a wall-clock for date/time.
- Total throughput measures **bytes flowing through FileChannel inside the timed loop**, excluding file creation, ByteBuffer allocation, opening/closing channels, or data parsing.

**This is neither an end-to-end benchmark nor a cold-disk benchmark.** It illustrates a methodology for choosing configurations. If production continuously allocates buffers per request, run an additional experiment capturing allocation and lifecycle costs.

### 6.2. Why Is This Example Not Enough to Publish a Ranking?

- Execution order is heap first, direct second. The latter group may benefit from a warmer page cache; serious experiments should reverse or randomize order.
- A 16 MiB file can fit entirely in the OS page cache. High numbers do not prove the physical disk reaches that speed.
- The `read` loop does not parse content, nor measure CPU for CSV/JSON/UTF-8 processing or copying data to output.
- The buffer is allocated before the timer; direct allocation cost is excluded from elapsed time.
- Small sample size, thermal/CPU conditions, and background processes can introduce noise.
- `FileChannel` is reopened per run, yet that **does not clear the OS page cache**.

When results show small differences, repeat measurements with randomized order, larger files, and identical JVM/OS configurations. For production decisions, benchmark the **exact** read and processing path actually executed.

## 7. How to Pick from a Measurement Table: The Saturation Point

Suppose **for illustration only** a system produces the following table (not actual results of the program above):

| Buffer | Hypothetical Throughput | Buffer memory / 1 task |
| ---: | ---: | ---: |
| 4 KiB | 320 MiB/s | 4 KiB |
| 16 KiB | 760 MiB/s | 16 KiB |
| 64 KiB | 940 MiB/s | 64 KiB |
| 256 KiB | 970 MiB/s | 256 KiB |
| 1 MiB | 973 MiB/s | 1 MiB |

From 4 KiB to 16 KiB increases significantly; from 64 KiB to 1 MiB only gains about 3.5% in the hypothetical table while consuming 16 times as much buffer memory. If benchmark variance is already near 5%, there is insufficient evidence that 1 MiB is genuinely faster.

**Evidence-based decision process:**

1. Eliminate values that fail correctness, cause overload, waste RAM, or worsen p99 latency.
2. Find the smallest size meeting the performance target—for example, within 95% of the best observed throughput.
3. If the difference falls within noise, measure more instead of declaring a "winner".
4. If one configuration is faster yet consumes far more memory, evaluate it in the context of **concurrent tasks**.
5. Lock in the value and re-benchmark with production file sizes, concurrency, and environment.

**The "95%" value is an applicable project selection threshold, not a Java constant.** For latency-sensitive tasks, select based on p95/p99 and minimum throughput rather than maximizing MB/s alone.

## 8. Memory, GC, and Concurrent Tasks

If each task holds its own buffer:

```text
estimatedBufferMemory = activeOperations × bufferCapacity
```

Example with 512 concurrent jobs:

| Buffer per job | Total byte region before overhead |
| ---: | ---: |
| 8 KiB | 4 MiB |
| 64 KiB | 32 MiB |
| 256 KiB | 128 MiB |
| 1 MiB | 512 MiB |

This is only the buffer total, **excluding** object headers, queues, file descriptors, TLS, page cache, parser objects, class metadata, and native resources.

With heap buffers, frequent allocations can create GC pressure. With direct buffers, memory usage may not appear fully in heap metrics, so native/direct memory must be monitored separately.

**Never share a single buffer across multiple threads writing concurrently without synchronization.** `ByteBuffer` holds non-thread-safe `position/limit` state. If using a buffer pool, guarantee a buffer has only one owner at any moment, returning it to the pool only after I/O finishes and the consumer is done processing.

### 8.1. Buffers and In-Flight Limits

When a server handles many uploads/downloads or asynchronous file requests, simply increasing buffer size without bounding active operations can exhaust resources.

A balanced design may combine:

- A 64 KiB or 128 KiB buffer per job (validated by measurement).
- A maximum number of in-flight jobs via `Semaphore`/bounded queue.
- Pending byte quotas on input and output.
- Limits on open file handles/sockets.
- Backpressure if the consumer cannot keep up.

In multi-request systems, **the optimal buffer size for a single job** may not be the optimal value for **the entire service**.

## 9. File Reading Differs from File Copying

Benchmarking `FileChannel.read(buffer)` does not replace a **copy** benchmark, because copying must also write to the destination.

Snippet for copying across two channels:

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);

while (true) {
    buffer.clear();
    int n = source.read(buffer);
    if (n == -1) {
        break;
    }
    if (n == 0) {
        continue;
    }

    buffer.flip();
    while (buffer.hasRemaining()) {
        destination.write(buffer);
    }
}
```

This snippet illustrates code inside a method with already-open `FileChannel source` and `FileChannel destination`. For channels that can repeatedly return `0`, an appropriate wait/limit mechanism is required to avoid a busy loop. **Partial writes** are normal: a single `write()` call may consume fewer bytes than remain in the buffer. Never call `clear()` immediately while unsent/unwritten bytes remain.

For file copy workloads, also benchmark `FileChannel.transferTo`/`transferFrom` within provider limits and actual transferred counts. Direct transfer can outperform manual buffer copying, though it must not be assumed blindly.

### 9.1. File Writing and Durability

A successful `write()` call may only mean data was accepted into I/O/cache layers, without proving the data resides durably on the storage device.

If business logic requires durability, define a `FileChannel.force(true)` policy or equivalent sync mechanism per the API contract and measure them **fairly**. Never compare a measurement calling `force()` after every block against one without `force()` and blame the buffer size.

For newly written files, space allocation, filesystem journaling, metadata updates, and storage caches can dominate over buffer size.

## 10. Text/JSON/CSV Processing Workloads

If the real task is reading CSV, logs, JSON Lines, or UTF-8 data:

- Buffer size affects byte-fetching rounds, yet the parser still has to handle delimiters, quotes, escapes, and multi-byte characters.
- A UTF-8 character can span a buffer boundary; an appropriate streaming decoder is needed.
- `BufferedReader.readLine()` has its own internal buffering logic; results from a `FileChannel.read` loop cannot be applied directly to it.
- If code retains every line in a `List<String>`, heap may be dominated by parsed data rather than the read buffer.
- Parsing/validation/checksumming can become the bottleneck once I/O is fast enough.

When measuring a real parser, timing must include **reading, decoding, parsing, and consuming data** per actual requirements. Run both an end-to-end measurement and a read-only measurement to know whether you are optimizing the right place.

## 11. A Reliable Benchmarking Process

1. **Define the question**: looking for a size that boosts throughput, lowers latency, or reduces RAM pressure?
2. **Choose representative data**: production-like file sizes, formats, and file counts.
3. **Define cache conditions**: warm-cache, cold-ish, or controlled test environment; never claim cold cache just because you reopened a stream.
4. **Warm up the JVM**: startup, class loading/JIT, run multiple iterations before measured rounds.
5. **Test multiple sizes**: e.g., 4/16/64/256/1024 KiB.
6. **Vary order**: randomize configuration order across iterations to reduce cache bias and temporal drift.
7. **Measure multiple samples**: median, distribution, min/max, p95/p99 when sample count suffices; never take only a single best run.
8. **Measure heap and direct separately**: require identical workloads, allocation policies, and explicit quotas.
9. **Observe resources**: CPU, GC, heap, native/direct memory, queue length, I/O counters.
10. **Verify correctness**: accurate byte counts, checksum/hash, or parser outputs; a benchmark that corrupts data is worthless.
11. **Measure end-to-end**: if business logic requires parsing, copying, compression, or `force`, include them in the application experiment.
12. **Record metadata**: JDK vendor/version, JVM flags, OS, filesystem, CPU, RAM, device, file sizes, concurrency, and cache settings.
13. **Commit to a budgeted choice**: pick the smallest size satisfying throughput/latency and resource targets.
14. **Repeat when the environment changes**: JDK upgrades, SSD changes, higher concurrency, or parser changes can shift the optimum.

### 11.1. Warm-Cache vs. Cold-Cache

The operating system maintains a page cache. After the first read, a file is often cached so subsequent passes can be faster regardless of buffer size.

- **Warm-cache tests** help inspect the path cost from cache to application.
- **Cold-storage tests** measure storage device impact, but cache must be controlled using methods appropriate for the test environment.
- Simply calling `FileChannel.close()` and reopening **does not clear the OS page cache**.
- Files larger than RAM can limit full caching, yet do not guarantee every byte of a pass is "cold".

Never run cache-dropping commands or arbitrarily tune production systems solely to generate benchmark numbers.

### 11.2. JIT, CPU, and GC

Use `System.nanoTime()` to measure elapsed intervals, not wall-clock time-of-day. JIT compilation, CPU governors, thermal throttling, background processes, and schedulers can all affect measurements.

Java Flight Recorder (JFR), JDK Mission Control, or an appropriate profiler helps inspect allocations, CPU hotspots, and GC pauses. Never conclude direct buffers are faster if other variables changed between two test runs.

### 11.3. Is JMH Enough?

JMH (Java Microbenchmark Harness) is valuable for measuring **in-JVM computation** with warm-ups, forks, and microbenchmark controls. However, filesystem I/O also depends on the OS page cache, storage, network, and the running host. Using JMH **does not automatically turn** a cached-file measurement into a cold-disk benchmark or production performance validation.

Combine microbenchmarks for parsers/codecs with integrated I/O measurements under realistic load.

## 12. Network Buffer Size Is Not TCP Packet Size

With `SocketChannel` and `AsynchronousSocketChannel`, buffers need to balance:

- Protocol message/frame sizes.
- Number of clients/connections.
- Inbound/outbound queues and backpressure.
- Partial reads/writes, `read()==0`, and `read()==-1`.
- Response latency, selector/completion callback frequency.
- TLS/encoding overhead when a security layer is present.
- Memory quotas if each connection holds a buffer.

Do not take MTU or a single TCP segment as a "mandatory buffer size". `ByteBuffer.capacity()` and `SO_RCVBUF`/`SO_SNDBUF` live at different layers.

If a server has 20,000 connections and allocates 1 MiB per connection, buffers alone can reach roughly 19.5 GiB. That can be a major issue even if a single-threaded file benchmark showed 1 MiB was slightly faster.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Choosing 1 MiB because "bigger is faster" | Wastes RAM without guaranteed speedup | Measure multiple sizes and saturation point |
| Running only one benchmark iteration | JIT/cache/scheduler noise | Warm-up, repeat samples, vary order |
| Using overly small files | Mostly measures cache/other overhead | Representative dataset |
| Reopening channel and calling it cold-cache | OS cache still holds data | Explicitly document warm-cache/cold-storage conditions |
| Comparing heap vs. direct while changing workload | Cannot isolate the cause of difference | Change only one variable at a time |
| Allocating direct buffers inside the read loop | Native memory & allocation cost | Reuse buffers, enforce quotas |
| Looking only at throughput | Can degrade p99 or GC | Measure latency/memory/CPU together |
| Treating `buffer.array()` as all read data | Includes stale bytes and data past limit | `flip()` then use `remaining()` |
| Treating `read()==0` as EOF | Drops data / closes early | EOF is `-1` |
| Calling `clear()` before writing all bytes | Loses pending state | Loop `hasRemaining()` or await writability |
| Casting `(int) fileSize` to allocate a buffer | Overflow on large files | Use fixed buffer, `long` for fileSize/offset |
| Measuring reads to infer CSV parser speed | Ignores CPU decode/parse/alloc | Benchmark end-to-end |
| Measuring writes without `force` and claiming durability | Does not measure durability contract | Define flush/force policy |
| Seeing a 1% difference and declaring victory | Likely within noise | Measure distributions, repeat runs |
| Ignoring buffers × concurrency | Exhausts heap/direct memory under load | Quotas and backpressure |

## 14. Practice and Solutions

**Q1.** For a 1 GiB file, what are the theoretical numbers of *full-buffer* reads with a 4 KiB buffer and a 64 KiB buffer?

**Answer:** 262,144 and 16,384, a 16× difference. Actual syscalls may differ because individual reads can be short.

**Q2.** Why is a 256 KiB buffer unlikely to be four times faster than a 64 KiB buffer?

**Answer:** Overhead decreases non-linearly; storage device, page cache, CPU, and parser may already be saturated.

**Q3.** Does `ByteBuffer.allocateDirect()` always consume less RAM than `allocate()`?

**Answer:** No. It may use native/direct memory outside the heap, which still occupies system resources and has its own quota.

**Q4.** After five reads of the same file, the sixth run is very fast. Is that guaranteed to be the real SSD speed?

**Answer:** No. The OS page cache can serve many bytes from RAM; measurement conditions must be understood.

**Q5.** 512 concurrent operations, 1 MiB buffer per operation. What is the total buffer byte footprint?

**Answer:** 512 MiB, excluding overhead. With 64 KiB, it is only 32 MiB.

**Q6.** Why did the byte-counting benchmark example omit `flip()`?

**Answer:** Because it does not read content out of the ByteBuffer after `FileChannel.read`, only reading the returned byte count. Code that actually parses bytes must call `flip()` before consuming.

**Q7.** The buffer is allocated before `System.nanoTime()`. Does the benchmark measure allocation cost?

**Answer:** No. To evaluate a workload that continuously creates buffers, a second experiment covering allocation and GC/native memory is needed.

**Q8.** If throughput between 64 KiB and 1 MiB differs by 2%, while measurement variance is around ±5%, what should you do?

**Answer:** Do not claim 1 MiB is definitively faster. Measure more, reduce noise, and consider using the less RAM-hungry buffer.

**Q9.** Why is `hasRemaining()` needed when writing through a channel?

**Answer:** `write()` can consume only part of the data. If bytes remain in the buffer, you must continue/wait rather than calling `clear()` prematurely.

**Q10.** Can a read-only file benchmark determine the best buffer for a JSON Lines parser?

**Answer:** Not enough. A parser also decodes, allocates objects, handles boundaries, and consumes CPU/GC; you must benchmark the actual business flow.

## 15. Production Readiness Checklist

1. Identified the read/write/copy/parse workload and target metrics?
2. Tested at least one systematic range of sizes?
3. Distinguished heap/direct/wrapper/mapped/transfer?
4. Used warm-up, multiple samples, and randomized ordering to avoid bias?
5. Documented page cache state and storage characteristics?
6. Verified accuracy of byte counts, payload, and EOF/partial writes?
7. Calculated `bufferSize × maxConcurrentOperations` and other queues?
8. Measured throughput **and** latency/GC/memory at expected load?
9. Selected size based on saturation point alongside memory budget?
10. Saved benchmark results and conditions to re-measure upon JDK/hardware upgrades?

**Key Takeaway:** Do not choose the largest buffer; choose **a buffer that is large enough**, proven by representative measurements and fitting your resource budget. For large files, a moderately sized reused buffer with proper `read()/write()` loops is usually a better starting point than trying to allocate memory matching the entire file.

## References

- Java SE 17 — `ByteBuffer` (heap/direct, allocation cost and native I/O): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 — `FileChannel` (`read`, `write`, `force`, `map`, `transferTo`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 — `ReadableByteChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadableByteChannel.html
- Java SE 17 — `BufferedInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html
- Java SE 17 — `BufferedOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html
- Java SE 17 — `Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- OpenJDK JMH — Java Microbenchmark Harness: https://openjdk.org/projects/code-tools/jmh/
