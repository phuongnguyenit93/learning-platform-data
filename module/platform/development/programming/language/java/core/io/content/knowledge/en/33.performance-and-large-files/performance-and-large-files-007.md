# Measuring Throughput, Latency, and Memory Usage When Processing I/O and Large Files in Java

## 1. Why Must You Measure All Three Metric Groups?

Optimizing large-file processing cannot rely on a single "runs fast" number. The same program can achieve high throughput while making individual requests wait too long, or read very fast because it consumes excessive RAM. Three metric groups should be tracked together:

- **Throughput:** amount of data or completed operations per unit time; for example, `MiB/s`, `MB/s`, or `operations/s`.
- **Latency:** time to complete **a clearly defined operation**; for example, a single `InputStream.read(...)`, reading an entire file, or an upload request. You must examine the latency distribution, especially `p95`/`p99`, not just the mean.
- **Memory usage:** memory occupied by the program while working, including Java heap, direct buffers, mapped memory, native memory, and process-level memory; distinguish measurement scopes to avoid drawing wrong conclusions.

In Java I/O, results are also affected by buffer size, OS page cache state, SSD/HDD/network filesystem characteristics, concurrent thread count, GC, and library behavior. This article focuses on **how to measure accurately**, how to interpret results, and how to choose appropriate solutions in Java 17+.

## 2. Define Metrics Before Starting the Clock

### 2.1. Throughput: Bytes Over Real Elapsed Time

If `B` bytes are read/written successfully over measurement interval `T` seconds:

\[
\text{Throughput (MiB/s)}=\frac{B}{1024^2 \times T}
\]

For example, reading `512 MiB` in `4 s` yields an average throughput of `128 MiB/s`. If decimal MB is needed, `1 MB = 1\,000\,000 bytes`; `1 MiB = 1\,048\,576 bytes`. **State units explicitly** when comparing against measurement tools or hardware specifications.

Two forms of throughput can answer different questions:

- **Data throughput:** `MiB/s` is meaningful for copying, reading/writing files, or bulk transfers.
- **Operation throughput:** `ops/s` is meaningful for many small operations. A system at `10\,000 ops/s` with 100 bytes per operation moves far less data than one at `500 ops/s` with 1 MiB per operation.

When measuring file reads, count **actual bytes returned** by `read`, not buffer size multiplied by call count; a `read(byte[])` call can return fewer bytes than the buffer size. For parallel reads, total throughput is **the sum of completed bytes across all workers divided by the same wall-clock interval**; never sum throughput values measured over different intervals.

### 2.2. Latency: Define the Boundaries of an Operation

Latency = end time − start time of an operation. In I/O there are at least three valid scopes:

| Scope | How to Measure | Interpretation |
| --- | --- | --- |
| A single `read(...)` call | `nanoTime()` before and after the call | API call latency; may receive bytes from a buffer |
| One file processing pass | Start at file open until close/read completion | End-to-end latency for that job |
| One system request | From request arrival to response return | Includes queuing, parsing, business logic, I/O, and scheduling |

Never take the p95 of individual `read` calls and label it "p95 file processing"; hundreds of `read` calls may compose **one** file processing pass.

Common percentiles:

- `p50` (median): roughly at least 50% of samples have latency no greater than this value.
- `p95`: roughly 95% of samples have latency no greater than this value.
- `p99`: roughly 99% of samples have latency no greater than this value.

For percentiles to be reliable, sample count must be sufficiently large and all samples must share the same operation definition. With only a few samples, `p99` virtually just reflects the maximum. Also report sample size, iteration count, mean/median, min/max when helpful, and variance across runs.

### 2.3. Using `System.nanoTime()` for Elapsed Time

`System.nanoTime()` is designed to compute elapsed time intervals within the same JVM run, not a wall-clock calendar timestamp. Example:

~~~java
long start = System.nanoTime();
long transferred = doRead(); // Illustrative snippet: doRead() is application-provided.
long elapsedNanos = System.nanoTime() - start;

double elapsedSeconds = elapsedNanos / 1_000_000_000.0;
double mibPerSecond = (transferred / (1024.0 * 1024.0))
        / elapsedSeconds;
~~~

This is an **illustrative snippet** inside a method, not a complete program: `doRead()` must be implemented and return actual bytes read. In real code, guard against near-zero intervals, run multiple iterations, and never optimize based on one noisy measurement. Never use `System.currentTimeMillis()` to benchmark short code: the wall clock can be adjusted and its resolution is often unsuitable.

## 3. Java 17+ Experiment: Measuring Throughput, p50/p95/p99, and Heap Snapshots

The following example:

1. Creates a **32 MiB test file** before timing starts.
2. Reads the file using `BufferedInputStream` and a 64 KiB application buffer.
3. Runs 2 warm-up passes, **excluding warm-up results from statistics**.
4. Runs 5 measured passes, summing bytes and time to compute data throughput.
5. Records the latency of each `read(byte[])`, sorts samples, and computes `p50/p95/p99`.
6. Takes two Java heap snapshots before/after the measured phase, explicitly noting they are **not peak heap**.

Create `IoMetricsDemo.java`:

~~~java
import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class IoMetricsDemo {
    private static final int BUFFER_BYTES = 64 * 1024;
    private static final long FILE_BYTES = 32L * 1024 * 1024;
    private static final int WARMUP = 2;
    private static final int MEASURED = 5;

    private record Trial(long bytes, long elapsedNanos, long readCalls) {}

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-metrics-", ".bin");
        try {
            prepareFile(file);

            for (int i = 0; i < WARMUP; i++) {
                readOnce(file, null);
            }

            long heapBefore = usedHeapBytes();
            long totalBytes = 0;
            long totalNanos = 0;
            long totalCalls = 0;
            List<Long> callLatencies = new ArrayList<>();

            for (int i = 0; i < MEASURED; i++) {
                Trial trial = readOnce(file, callLatencies);
                totalBytes += trial.bytes();
                totalNanos += trial.elapsedNanos();
                totalCalls += trial.readCalls();
            }
            long heapAfter = usedHeapBytes();

            callLatencies.sort(Long::compareTo);
            double seconds = totalNanos / 1_000_000_000.0;
            double mib = totalBytes / (1024.0 * 1024.0);

            System.out.println("File bytes: " + Files.size(file));
            System.out.println("Measured passes: " + MEASURED);
            System.out.println("Total read bytes: " + totalBytes);
            System.out.println("Read calls: " + totalCalls);
            System.out.printf(Locale.ROOT,
                    "Throughput: %.2f MiB/s%n", mib / seconds);
            System.out.printf(Locale.ROOT,
                    "read() p50/p95/p99: %.3f / %.3f / %.3f ms%n",
                    percentile(callLatencies, 0.50) / 1_000_000.0,
                    percentile(callLatencies, 0.95) / 1_000_000.0,
                    percentile(callLatencies, 0.99) / 1_000_000.0);
            System.out.println("Heap before (bytes): " + heapBefore);
            System.out.println("Heap after  (bytes): " + heapAfter);
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static void prepareFile(Path file) throws IOException {
        byte[] block = new byte[BUFFER_BYTES];
        Arrays.fill(block, (byte) 0x5A);
        try (OutputStream out = Files.newOutputStream(file,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING)) {
            long written = 0;
            while (written < FILE_BYTES) {
                int n = (int) Math.min(block.length, FILE_BYTES - written);
                out.write(block, 0, n);
                written += n;
            }
        }
    }

    private static Trial readOnce(Path file, List<Long> samples)
            throws IOException {
        byte[] buffer = new byte[BUFFER_BYTES];
        long bytes = 0;
        long calls = 0;
        long start = System.nanoTime();

        try (InputStream in = new BufferedInputStream(
                Files.newInputStream(file), BUFFER_BYTES)) {
            while (true) {
                long before = System.nanoTime();
                int n = in.read(buffer);
                long after = System.nanoTime();
                if (n == -1) {
                    break;
                }
                if (n == 0) {
                    continue;
                }
                bytes += n;
                calls++;
                if (samples != null) {
                    samples.add(after - before);
                }
            }
        }

        return new Trial(bytes, System.nanoTime() - start, calls);
    }

    private static long percentile(List<Long> sorted, double fraction) {
        int index = (int) Math.ceil(fraction * sorted.size()) - 1;
        return sorted.get(Math.max(0, index));
    }

    private static long usedHeapBytes() {
        return ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
    }
}
~~~

Run commands on JDK 17+:

~~~bash
javac IoMetricsDemo.java
java IoMetricsDemo
~~~

**The first three lines are deterministic** upon successful completion (using the sizes chosen in code):

~~~text
File bytes: 33554432
Measured passes: 5
Total read bytes: 167772160
~~~

The lines `Read calls`, `Throughput`, `read() p50/p95/p99`, and `Heap before/after` all **depend on machine, JVM, OS, cache state, and system load**; there is no fixed numeric stdout for them. These lines always use the exact labels and units shown in the code, while values come from an actual run.

### 3.1. Why Does the Code Measure This Way?

- **Create data before measuring:** excludes test-file write time from read throughput.
- **Warm-up:** reduces noise from class loading, JIT compilation, and partially unstable state. Two passes suffice for an educational example, not for claiming a representative benchmark.
- **Count actual bytes:** `bytes` increments by `n` returned from `read`, never assuming 64 KiB is received every time.
- **Compute throughput from total bytes / total elapsed:** sums durations across measured runs, avoiding taking a simple arithmetic mean of throughputs over unequal durations.
- **Per-call latency:** `callLatencies` measures successful `read` calls, excluding the final `read` returning `-1`. Percentiles use the *nearest-rank* rule with 0-based indexing.
- **Two clock windows:** latency covers only executing the `read` call; throughput includes opening/closing the stream, looping, and recording samples per read. Because the two metrics cover different scopes, do not expect summing call latencies to match total elapsed time.
- **Memory snapshots:** `MemoryMXBean` returns `heap.used` at two points; values can rise or fall due to GC and other allocations. The difference `after - before` is **neither** total bytes allocated **nor** peak heap.

### 3.2. Important Limitations of This Example Itself

The demo measures latency and inserts each sample into an `ArrayList<Long>`, incurring **observer overhead**: boxing `Long`, calling `nanoTime()`, storing samples, and GC can slow throughput. For serious measurements, run **one low-instrumentation throughput pass** and **one sampled latency pass**, then compare. You can replace the boxed list with a pre-allocated `long[]`, though clock overhead still remains.

Furthermore, reading the same 32 MiB file 5 times likely runs primarily from the **OS page cache**, not cold physical SSD/HDD throughput. Thus results reflect **this example's specific configuration and workload**, not drive datasheet specs.

## 4. Measuring End-to-End Latency and File Writing Scenarios

For a requirement like "read a full file and return data", measure a window spanning the entire corresponding path:

~~~java
long startedAt = System.nanoTime();
long count = 0;
try (InputStream in = Files.newInputStream(path)) {
    byte[] chunk = new byte[64 * 1024];
    int n;
    while ((n = in.read(chunk)) != -1) {
        count += n;
        // If business logic parses/transforms, place it here to measure end-to-end.
    }
}
long elapsed = System.nanoTime() - startedAt;
~~~

This is a **snippet inside a method** with a `Path path` variable and `IOException` handling; not a standalone class. `elapsed` covers opening, reading to EOF, closing the file, and in-loop processing.

Measuring **writes** has multiple distinct completion layers:

1. `OutputStream.write(...)` returns: bytes were handed to the corresponding buffer/provider layers; does not yet mean data resides durably on the device.
2. `flush()` on a buffered stream: pushes data out of the application buffer to the layer below; not equivalent to a durable commit on disk.
3. `FileChannel.force(true)` or `FileDescriptor.sync()`: requests pushing appropriate changes down to the storage device per API/OS contract, subject to device and filesystem caveats.

If a benchmark claims to measure **durable write latency**, it must include `force`/`sync` inside the latency boundary. Measuring only buffered `write` throughput and comparing it against another solution running `fsync` per transaction yields an unfair conclusion.

Example **illustrating boundary placement** when using `FileChannel`:

~~~java
long start = System.nanoTime();
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    ByteBuffer data = ByteBuffer.wrap(payload);
    while (data.hasRemaining()) {
        channel.write(data);
    }
    channel.force(true);
}
long durableWriteNanos = System.nanoTime() - start;
~~~

Variables `path` (`Path`) and `payload` (`byte[]`) are passed from calling code. Requires importing `java.nio.ByteBuffer`, `java.nio.channels.FileChannel`, and `java.nio.file.StandardOpenOption`. This is an illustrative snippet in a method handling `IOException`. `channel.write` can write fewer bytes than `ByteBuffer.remaining()`, hence the `while (data.hasRemaining())` loop.

## 5. Measuring Memory: Java Heap Does Not Represent All RAM

### 5.1. Memory Scopes That Must Be Distinguished

| Metric | Meaning | Typical Observation Method |
| --- | --- | --- |
| `heap.used` | Bytes currently used in Java heap per JVM reporting | `MemoryMXBean`, JFR, GC logs |
| `heap.committed` | Memory committed by the JVM for heap | `MemoryUsage.getCommitted()` |
| `heap.max` | Heap limit, may be "undefined" depending on pool/JVM | `MemoryUsage.getMax()`, configuration-dependent |
| Direct buffer pool | Memory tied to `ByteBuffer.allocateDirect` managed by pool | `BufferPoolMXBean` named `direct` |
| Mapped buffer pool | Count/size of tracked mapped buffers | `BufferPoolMXBean` named `mapped` / active pool |
| Other native memory | Thread stacks, metadata, code cache, JVM/library native regions | Native Memory Tracking/JFR/OS by source |
| RSS / working set | Physical memory pages currently resident for the process per OS | OS process monitoring tools |
| OS page cache | File cache pages retained by OS, able to serve I/O without disk reads | OS statistics, not Java heap |

**Never blindly add** `heap.used + direct pool + RSS`: RSS already includes resident portions of heap/native memory, so summing double-counts. `heap.committed` also differs from actual resident physical pages. File-backed mappings also interact uniquely with the page cache.

### 5.2. Two Large-File Processing Strategies with Different Memory Footprints

**Reading the entire file:**

~~~java
byte[] all = Files.readAllBytes(path);
process(all); // process is an application method; this snippet is not standalone.
~~~

`readAllBytes` requires an array holding the file contents on the heap and may incur extra temporary arrays/JVM overhead depending on implementation. For very large files, it can hit `OutOfMemoryError` or Java array size limits. Suitable when files are small, within memory limits, and genuinely need full in-memory retention.

**Streaming chunk by chunk:**

~~~java
try (InputStream in = Files.newInputStream(path)) {
    byte[] chunk = new byte[64 * 1024];
    int n;
    while ((n = in.read(chunk)) != -1) {
        process(chunk, n); // Application processes the n valid bytes immediately.
    }
}
~~~

Both snippets above are **illustrative code** inside methods with `Path path` and an appropriate `process` function, not standalone programs. Streaming can keep heap working set close to the buffer size if `process` does not accumulate data. If `process` appends every chunk to a `List` or builds a huge `String`, **streaming no longer guarantees a low footprint**.

### 5.3. Tracking Direct/Mapped Buffers with `BufferPoolMXBean`

Standalone program `BufferPoolDemo.java`:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;

public class BufferPoolDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(8 * 1024 * 1024);
        System.out.println("Direct: " + buffer.isDirect());

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            if (pool.getName().equals("direct")
                    || pool.getName().equals("mapped")) {
                System.out.printf(
                        "%s: count=%d, used=%d, capacity=%d%n",
                        pool.getName(),
                        pool.getCount(),
                        pool.getMemoryUsed(),
                        pool.getTotalCapacity());
            }
        }
    }
}
~~~

~~~bash
javac BufferPoolDemo.java
java BufferPoolDemo
~~~

Deterministic first line:

```text
Direct: true
```

Remaining lines print buffer count, estimated pool-managed memory bytes, and total capacity. **Exact numbers vary across JDKs/environments and timing**; do not treat them as total native memory. `BufferPoolMXBean` may also return undefined values for some properties/scenarios; available pool names depend on the JVM. Direct buffer deallocation normally relies on lifecycle management and GC; never assume a local variable leaving scope immediately frees native memory.

### 5.4. How to Measure Peak Memory More Accurately

Two before/after snapshots like in `IoMetricsDemo` can **miss memory peaks in between**. For long-running applications or heavy allocation loads:

- Sample `heap.used` repeatedly throughout the run along with timestamps and load levels; the maximum in that series is a **sampled peak**, not an absolute peak if spikes occurred between samples.
- Use **JDK Flight Recorder (JFR)** or profiling tools to observe allocations, heap, GC pauses, and execution. Allocation rate (bytes allocated per second) differs from retained live heap.
- Use `jcmd <pid> GC.heap_info` or JVM/JMX metrics depending on runtime to inspect heap state at invocation time.
- To understand JVM-internal native usage, enable **Native Memory Tracking** at startup (`-XX:NativeMemoryTracking=summary`) and run `jcmd <pid> VM.native_memory summary`; NMT carries overhead and does not cover all external memory allocated arbitrarily by native libraries.
- Use OS tools for **RSS/working set**, page cache, I/O bytes, and page faults; never infer total process RAM from `-Xmx` alone.

`jcmd` commands require matching process/JDK and appropriate process permissions. Without enabling NMT at startup, the summary command will not provide the same detailed breakdown.

## 6. Avoiding Skewed Benchmarks from Cache, Warm-Up, and Test Configuration

### 6.1. Cold Cache vs. Warm Cache

Reading the same file multiple times can shift from disk-backed I/O to reading from the **OS page cache**. Warm-cache results remain useful if production workloads truly perform repeated reads, yet do not use them to represent cold device read speeds. "Closing the stream" or `FileChannel.force(...)` does not clear the page cache.

Good practice is to explicitly report:

- Fresh files versus repeated files, file size relative to RAM, and whether the same offsets are re-read.
- Storage device and local/network filesystem, cgroup/container limits, and background load.
- First-run results versus subsequent runs; if measuring cold cache is necessary, use **cache-control methods appropriate to the OS/test setup**, only with authorization and without disrupting shared systems.
- Sequential versus random reads; access patterns can drastically change throughput due to read-ahead and seeks.

### 6.2. Warm-Up and JIT/GC

The JVM needs time for class loading and optimizing compilation; GC and schedulers can introduce spikes. Run a dedicated warm-up, multiple independent measurement runs, report median/tail across runs, and keep JVM settings consistent. Never call `System.gc()` repeatedly to "stabilize" benchmarks: it is not guaranteed to act as desired and distorts real execution conditions.

For CPU microbenchmarks or very short API calls, use **JMH** with explicitly configured forks/warm-up/measurement iterations. For real I/O, JMH still cannot control disks, filesystem caches, networks, durable writes, or request distributions on its own; design the workload and infrastructure harness accordingly. Do not let the measurement harness allocate so heavily that you benchmark GC instead of I/O.

### 6.3. Keep Workloads Fair

When comparing `Files.readAllBytes`, `BufferedInputStream`, `FileChannel`, or `MappedByteBuffer`:

1. Ensure identical data, total size, cache conditions, and measurement harness.
2. Separate read-only, write-only, read+parse, copy, checksum, and durable write.
3. Verify **data correctness** or byte counts to avoid benchmarking an implementation that drops work.
4. Control buffer sizes, thread counts, concurrent operations, and open/close policies.
5. Alternate run order appropriately; if A always runs before B, cache/JIT advantages may skew toward B.
6. Monitor CPU, GC, I/O wait, page faults, heap, direct memory, and RSS alongside to explain throughput/latency.

No API is "fastest" across every workload. `Files.readAllBytes` can be fast and convenient for small files while raising peak heap; `FileChannel` and streaming generally suit large files; memory mapping helps certain random-access patterns yet requires accounting for page faults, mapping lifetimes, and virtual address space.

## 7. Combining Throughput, Latency, and Memory for Diagnosis

| Observation | Testable Hypothesis | Next Measurement |
| --- | --- | --- |
| High throughput, sharp `p99` spike | Queuing, GC, thread/lock contention, I/O jitter | Request-level p99, queue wait, GC pauses, I/O latency |
| Throughput stalls as concurrency grows | Device saturated, contention, scheduling overhead | Disk utilization, CPU, context switches, queue depth |
| Throughput rises yet RSS climbs fast | Direct/mapped buffers, page cache, native allocations | Buffer pools, NMT, RSS, heap snapshots |
| Heap grows linearly with file size | `readAllBytes`, accumulating records/byte arrays, retained refs | Heap allocations and retained objects |
| Heap flat yet process uses huge RAM | Direct/native memory/threads/mappings | BufferPoolMXBean, NMT, RSS |
| First pass slow, subsequent passes fast | Page cache or warm-up | Compare cold/warm, observe disk read bytes |
| `write` fast yet data not durable | Measuring before `flush/force/sync` | Measure completion time after force/sync |
| `p50` healthy yet `p99` awful | Tail skewed by a few slow requests | Sufficiently large histogram, trace slowest samples, stage-by-stage timing |

Rows represent **hypotheses to verify**; one symptom can have multiple causes. For instance, slowness from a network filesystem can drop throughput while heap stays flat. Plotting metrics on a shared timeline is usually far more effective than reading isolated snapshots.

## 8. Writing a Reproducible Benchmark Report

Example report structure (this is a **template for recording results**, not actual benchmark numbers):

| Item | Information to Record |
| --- | --- |
| Goal | Sequential large-file read, or processing an upload request |
| Latency scope | Single `read` / single file / single request |
| Data size and pattern | File size, chunk size, sequential/random, compressed or not |
| Runtime | JDK version, heap flags, GC, worker count |
| Machine and I/O | CPU, RAM, disk/network filesystem, OS, page cache |
| Methodology | Warm-up runs, measured runs, sample count, percentile method |
| Throughput | MiB/s and total bytes/duration |
| Latency | p50/p95/p99, ms or µs units, explicit measurement level |
| Memory | heap used/committed/sampled peak, direct pool, RSS, allocation rate |
| Reliability | Variance, cache conditions, limitations, and observer overhead |

When optimizing, preserve the **pre-change baseline**, then run the exact same workload on the new version. Document trade-offs too: raising buffer size from 8 KiB to 256 KiB may boost throughput on one machine yet consume more RAM per concurrent connection or hurt performance via GC/cache pressure at another scale.

## 9. Self-Check Questions

**Q1.** A program reads 200 MiB in 2.5 seconds. What is the throughput?

**Answer:** `200 / 2.5 = 80 MiB/s`. The unit is MiB/s when input is in MiB; converting to MB/s requires unit conversion before dividing.

**Q2.** Can you take the p95 of individual `read` calls and call it the p95 "upload request time"?

**Answer:** No. Request latency can include queuing, multiple reads/writes, processing, and response sending. Measure end-to-end across the request if that is the SLA being evaluated.

**Q3.** Both before and after heap snapshots show 70 MiB. Can you conclude peak heap was only 70 MiB?

**Answer:** No. Heavy allocations and GC collections may have occurred between snapshots, or spikes occurred between samples; use continuous sampling/JFR/profiler. Direct memory and RSS also sit outside `heap.used`.

**Q4.** Why can reading a 32 MiB file 5 times yield higher throughput than the first read of a brand-new file?

**Answer:** OS page cache, readahead, JVM warm-up, and other factors. Once file pages are resident in RAM, measurements no longer reflect pure cold disk speed.

**Q5.** Why is `flush()` on a buffered stream insufficient to declare "data written durably"?

**Answer:** `flush` primarily pushes data out of the stream layer's buffer to the layer below. Durability may require `FileChannel.force` or `FileDescriptor.sync`, subject to device/OS limits and business requirements.

**Q6.** If throughput increases by 20% while request p99 triples and RSS exceeds the container limit, is the solution better?

**Answer:** Not conclusively. You must evaluate latency SLAs, memory budgets, target load, and operational cost together. If latency/RAM requirements are violated, higher throughput does not equal a successful optimization.

## 10. Practical Summary

1. **State clearly what operation is measured and in which units.** `MiB/s`, `ops/s`, `p95 read()`, and `p95 request` mean different things.
2. **Count only completed work and bytes actually transferred.** Use `System.nanoTime()` for elapsed intervals, and count bytes from actual `read`/`write` return values.
3. **Measure simultaneously while understanding metric sources:** Java heap, direct/mapped, native, and RSS are distinct slices; snapshots are not peaks.
4. **Isolate workload from noise:** file preparation, cache, warm-up, JIT, GC, instrumentation, and durability all influence measurements.
5. **Compare under controlled conditions, multiple runs, tail percentiles, and recorded environment settings.** Reliable results are ones others can reproduce and explain.

With large files, the most trustworthy optimization process starts by benchmarking the real workload, pinpointing the bottleneck, and only changing buffers/APIs/concurrency when measurements prove the change satisfies speed, latency, and memory goals simultaneously.
