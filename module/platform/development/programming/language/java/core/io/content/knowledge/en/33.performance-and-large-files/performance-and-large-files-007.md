# Measuring Throughput, Latency, and Memory Usage When Processing I/O and Large Files in Java

## 1. Why Must We Measure All Three Metric Groups?

Optimizing large-file processing cannot rely on a single “runs fast” number. The same program can achieve high throughput while making individual requests wait too long, or read very quickly by consuming too much RAM. Three groups of metrics must be tracked together:

- **Throughput:** amount of data or number of operations completed per unit time; for example `MiB/s`, `MB/s`, or `operations/s`.
- **Latency:** time to complete **one well-defined operation**; for example each `InputStream.read(...)`, each full file read, or each upload request. You must inspect the latency distribution, especially `p95`/`p99`, not just the average.
- **Memory usage:** memory occupied by the program while working, including Java heap, direct buffers, mapped memory, native memory, and process-level memory; distinguish measurement scopes to avoid wrong conclusions.

In Java I/O, results are also influenced by buffer size, OS page cache state, SSD/HDD/network filesystem characteristics, concurrent thread count, GC, and library behavior. This lesson focuses on **how to measure properly**, how to interpret results, and how to choose appropriate solutions in Java 17+.

## 2. Define Metrics Before Starting the Clock

### 2.1. Throughput: Bytes Over Real Time

If `B` bytes are read/written successfully during a measurement window of `T` seconds:

\[
\text{Throughput (MiB/s)}=\frac{B}{1024^2 \times T}
\]

For example, reading `512 MiB` in `4 s` gives an average throughput of `128 MiB/s`. If decimal MB is needed, `1 MB = 1\,000\,000 bytes`; `1 MiB = 1\,048\,576 bytes`. **State units clearly** when comparing against measurement tools or device specs.

Two forms of throughput can answer different questions:

- **Data throughput:** `MiB/s` is meaningful for copying, reading/writing files, or large data transfers.
- **Operation throughput:** `ops/s` is meaningful for many small operations. A system doing `10\,000 ops/s` of 100 bytes each moves less data than one doing `500 ops/s` of 1 MiB each.

When measuring file reads, count the **actual bytes returned** by `read`, not buffer size multiplied by call count; a `read(byte[])` call can return fewer bytes than the buffer. For parallel reads, total throughput is **total completed bytes across all workers divided by the same elapsed wall time**; do not sum throughput values measured over different intervals.

### 2.2. Latency: Define the Boundaries of One Operation

Latency = end timestamp − start timestamp of an operation. In I/O there are at least three valid scopes:

| Scope | How to measure | Interpretation |
| --- | --- | --- |
| One `read(...)` call | `nanoTime()` before and after the call | API call latency, which may receive bytes from a buffer |
| One file processing pass | From opening the file to closing/finishing reading | End-to-end latency of that job |
| One system request | From request arrival to response delivery | Includes queuing, parsing, business logic, I/O, and scheduling |

Do not take the p95 of individual `read` calls and call it “file processing p95”; hundreds of `read` operations can make up **one** file processing pass.

Commonly used percentiles:

- `p50` (median): at least roughly 50% of samples have latency no greater than this value.
- `p95`: roughly 95% of samples have latency no greater than this value.
- `p99`: roughly 99% of samples have latency no greater than this value.

For reliable percentiles, you need enough samples with identical operation definitions. With only a few samples, `p99` practically reflects just the maximum. Also report sample size, iteration count, mean/median, min/max when useful, and run-to-run variance.

### 2.3. Using `System.nanoTime()` to Measure Elapsed Time

`System.nanoTime()` is designed for measuring elapsed time differences within the same JVM process, not wall-clock calendar timestamps. Example:

~~~java
long start = System.nanoTime();
long transferred = doRead(); // Illustrative snippet: doRead() is an application-supplied method.
long elapsedNanos = System.nanoTime() - start;

double elapsedSeconds = elapsedNanos / 1_000_000_000.0;
double mibPerSecond = (transferred / (1024.0 * 1024.0))
        / elapsedSeconds;
~~~

This is an **illustrative snippet** inside a method, not a complete program: `doRead()` must be implemented and return actual bytes read. In real code, guard against tiny measured durations, measure multiple passes, and do not optimize based on a single noisy reading. Never use `System.currentTimeMillis()` to benchmark short code: wall clocks can jump and resolution is often unsuitable.

## 3. Java 17+ Experiment: Measuring Throughput, p50/p95/p99, and Heap Snapshots

The example below:

1. Creates a **32 MiB test file** before measurement begins.
2. Reads the file with `BufferedInputStream` and a 64 KiB application buffer.
3. Runs 2 warm-up passes, **excluding warm-up results from statistics**.
4. Runs 5 measured passes, summing bytes and elapsed time to compute data throughput.
5. Records latency of each `read(byte[])`, sorts, and computes `p50/p95/p99`.
6. Takes two Java heap snapshots before and after the measured phase, explicitly noting they are **not peak heap**.

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

**The first three lines are deterministic** upon completion (sizes chosen in code):

~~~text
File bytes: 33554432
Measured passes: 5
Total read bytes: 167772160
~~~

`Read calls`, `Throughput`, `read() p50/p95/p99`, and `Heap before/after` all **depend on machine, JVM, OS, cache state, and system load**; there is no fixed numeric stdout for them. These lines always use the exact labels and units in the code, while values come from an actual run.

### 3.1. Why Does the Code Measure This Way?

- **Prepare data beforehand:** test file write time is excluded from read throughput.
- **Warm-up:** reduces effects of class loading, JIT compilation, and unsettled state. Two passes suffice for a learning demo, not for claiming a representative benchmark.
- **Count actual bytes:** `bytes` increments by the `n` returned by `read`, without assuming every call yields 64 KiB.
- **Compute throughput from total bytes / total elapsed:** sums durations across measured passes, avoiding naive arithmetic averages of per-pass throughputs with differing durations.
- **Per-call latency:** `callLatencies` times successful `read` calls, excluding the final `read` returning `-1`. Percentiles use the *nearest-rank* rule with 0-based indexing.
- **Two clock windows:** latency covers only executing the `read` call; throughput includes opening/closing the stream, looping, and storing samples on each read. Since the two metrics have different scopes, do not expect the sum of call latencies to equal total elapsed time.
- **Memory snapshots:** `MemoryMXBean` returns `heap.used` at two instants; values can rise or fall due to GC and other allocations. The `after - before` difference is **not** total allocated bytes and **not** peak heap.

### 3.2. Important Limitations of the Demo Itself

The demo measures latency while appending every sample to `ArrayList<Long>`, incurring **observer overhead**: `Long` boxing, `nanoTime()` calls, sample storage, and GC can lower throughput. For serious measurements, run **one throughput pass with minimal instrumentation** and **one latency pass with sampling**, then compare results. You can replace the boxed list with a pre-allocated `long[]`, though clock overhead still remains.

Furthermore, 5 reads of the same 32 MiB file likely run mainly from the **OS page cache**, not cold physical SSD/HDD throughput. Thus results reflect **the specific configuration and workload of the demo**, not advertised drive specifications.

## 4. Measuring End-to-End Latency and File Write Scenarios

For a requirement like “read an entire file and return data,” measure a window enclosing the full corresponding path:

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

This is a **snippet placed inside a method** with `Path path` and `IOException` handling; not a standalone class. `elapsed` covers opening, reading to EOF, closing the file, and loop processing.

Measuring **writes** involves distinct completion layers:

1. `OutputStream.write(...)` returns: bytes were handed to the corresponding buffer/provider layers; not yet guaranteed durable on the device.
2. Buffered stream `flush()`: pushes data out of the application buffer to the next layer; not equivalent to durable storage on disk.
3. `FileChannel.force(true)` or `FileDescriptor.sync()`: requests pushing appropriate changes down to the storage device per the API/OS contract, with device and filesystem caveats.

If a benchmark claims to measure **durable write latency**, it must include `force`/`sync` inside the latency boundary. Comparing buffered `write` throughput against another solution calling `fsync` per transaction leads to an unfair conclusion.

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

Variables `path` (`Path`) and `payload` (`byte[]`) are passed by the caller. Requires importing `java.nio.ByteBuffer`, `java.nio.channels.FileChannel`, and `java.nio.file.StandardOpenOption`. This is an illustrative snippet inside a method handling `IOException`. `channel.write` can write fewer bytes than `ByteBuffer.remaining()`, hence `while (data.hasRemaining())`.

## 5. Measuring Memory: Java Heap Does Not Represent All RAM

### 5.1. Memory Scopes That Must Be Distinguished

| Metric | Meaning | Typical observation tool |
| --- | --- | --- |
| `heap.used` | Bytes currently used in the Java heap per JVM accounting | `MemoryMXBean`, JFR, GC logs |
| `heap.committed` | Memory committed by the JVM for the heap | `MemoryUsage.getCommitted()` |
| `heap.max` | Heap limit, which may be “undefined” depending on pool/JVM | `MemoryUsage.getMax()`, depending on config |
| Direct buffer pool | Memory tied to `ByteBuffer.allocateDirect` managed by the pool | `BufferPoolMXBean` named `direct` |
| Mapped buffer pool | Count/size of tracked mapped buffers | `BufferPoolMXBean` named `mapped` / available pools |
| Other native memory | Thread stacks, metadata, code cache, JVM/library native regions | Native Memory Tracking/JFR/OS depending on source |
| RSS / working set | Physical memory pages currently resident for the process per OS | OS process monitoring tools |
| OS page cache | File cache pages held by the OS, able to serve I/O without disk reads | OS statistics, not Java heap |

**Never blindly sum** `heap.used + direct pool + RSS`: RSS already includes resident portions of heap/native memory, so summing double-counts. `heap.committed` differs from actual resident physical pages. File-backed mappings also have their own relationship with the page cache.

### 5.2. Two Large-File Processing Strategies with Different Memory Footprints

**Reading the entire file:**

~~~java
byte[] all = Files.readAllBytes(path);
process(all); // process is an application method; this snippet is not standalone.
~~~

`readAllBytes` requires an array holding the file contents on the heap, potentially incurring extra temporary arrays/JVM overhead depending on implementation. For very large files, it can trigger `OutOfMemoryError` or hit Java array size limits. Suitable when files are small, within memory limits, and genuinely need full in-memory materialization.

**Chunked streaming read:**

~~~java
try (InputStream in = Files.newInputStream(path)) {
    byte[] chunk = new byte[64 * 1024];
    int n;
    while ((n = in.read(chunk)) != -1) {
        process(chunk, n); // Application immediately processes n valid bytes.
    }
}
~~~

Both snippets are **illustrative code** inside a method with `Path path` and an appropriate `process` method, not standalone programs. Streaming can keep the heap working set close to the buffer size if `process` does not accumulate data. If `process` appends every chunk into a `List` or builds a huge `String`, **streaming no longer guarantees a low footprint**.

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

First line is deterministic:

~~~text
Direct: true
~~~

Remaining lines print buffer count, estimated pool-managed memory bytes, and total capacity. **Exact numbers vary across JDKs/environments and timing**; do not treat them as all native memory. `BufferPoolMXBean` can also return undefined values for some attributes/cases; available pool names depend on the JVM. Releasing direct buffers usually depends on lifecycle management and GC; do not assume a local object leaving scope immediately frees native memory.

### 5.4. How to Measure Peak Memory More Accurately

Two before/after snapshots like in `IoMetricsDemo` can **miss memory spikes in between**. For long-running applications or heavy allocation pressure:

- Sample `heap.used` repeatedly throughout the run with timestamps and load levels; the max across samples is only a **sampled peak**, not absolute if spikes occur between samples.
- Use **JDK Flight Recorder (JFR)** or profiling tools to observe allocations, heap, GC pauses, and execution behavior. Allocation rate (bytes allocated per second) differs from retained heap.
- Use `jcmd <pid> GC.heap_info` or JVM/JMX metrics depending on runtime to inspect heap state at invocation time.
- To understand JVM-internal native usage, enable **Native Memory Tracking** at startup (`-XX:NativeMemoryTracking=summary`) and run `jcmd <pid> VM.native_memory summary`; NMT has overhead and does not cover all external memory managed arbitrarily by native libraries.
- Use OS tools for **RSS/working set**, page cache, I/O bytes, and page faults; do not infer total process RAM from `-Xmx` alone.

`jcmd` commands must run against a matching process/JDK with appropriate permissions. If NMT was not enabled at startup, the summary command will not provide the same detailed information as an NMT-enabled session.

## 6. Avoiding Biased Benchmarks from Cache, Warm-Up, and Measurement Setup

### 6.1. Cold Cache and Warm Cache

Reading the same file multiple times can transition from disk-backed I/O to reading from the **OS page cache**. Warm-cache results remain useful if real production workloads perform repeated reads, yet must not represent reading fresh files from the device. “Closing a stream” or `FileChannel.force(...)` does not evict the page cache.

Good practice is to report clearly:

- Fresh vs. repeated files, file size relative to RAM, and whether identical offsets are re-read.
- Local/network device and filesystem, cgroup/container limits, and background load.
- First-run results vs. subsequent passes; if cold-cache testing is needed, use an **OS/test-appropriate cache control method**, only when authorized and without disrupting shared systems.
- Sequential vs. random reads; access patterns can shift throughput dramatically via read-ahead and seeks.

### 6.2. Warm-Up and JIT/GC

The JVM needs time for class loading and optimizing compilation; GC and the scheduler can introduce spikes. Run dedicated warm-ups, multiple independent measured passes, report medians/tails across runs, and keep JVM settings consistent. Never call `System.gc()` repeatedly to “stabilize” a benchmark: it is not guaranteed to behave as desired and distorts real conditions.

For CPU microbenchmarks or ultra-short APIs, use **JMH** with explicit fork/warm-up/measurement settings. For real I/O, JMH still cannot control disks, filesystem caches, networks, durable writes, or request distributions on its own; design the workload and infrastructure tier accordingly. Avoid letting the measurement harness allocate so much that you measure GC instead of I/O.

### 6.3. Keep Workloads Fair

When comparing `Files.readAllBytes`, `BufferedInputStream`, `FileChannel`, or `MappedByteBuffer`:

1. Ensure identical data, total size, cache conditions, and measurement harness.
2. Distinguish read-only, write-only, read+parse, copy, checksum, and durable write.
3. Verify **data correctness** or byte count to avoid benchmarking incomplete/skipped work.
4. Control buffer size, thread count, concurrency, and open/close policies.
5. Run multiple passes in an alternating order; always testing A before B can hand cache/JIT advantages to B.
6. Monitor CPU, GC, I/O wait, page faults, heap, direct memory, and RSS in parallel to explain throughput/latency.

No API is “fastest” across all workloads. `Files.readAllBytes` can be fast and convenient for small files while raising peak heap; `FileChannel` and streaming generally suit large files; memory mapping helps in some random-access patterns yet requires accounting for page faults, mapping lifetime, and virtual address space.

## 7. Combining Throughput, Latency, and Memory for Diagnosis

| Observation | Testable hypothesis | Next measurement |
| --- | --- | --- |
| High throughput, sharp `p99` spike | Queuing, GC, thread/lock contention, I/O jitter | Request-level p99, queue wait, GC pauses, I/O latency |
| Throughput stalls as concurrency increases | Device saturated, contention, scheduling overhead | Disk utilization, CPU, context switches, queue depth |
| Throughput rises while RSS climbs fast | Direct/mapped buffers, page cache, native allocations | Buffer pools, NMT, RSS, heap snapshots |
| Heap grows linearly with file size | `readAllBytes`, accumulating records/byte arrays, retained refs | Heap allocations and retained objects |
| Heap stable yet process uses lots of RAM | Direct memory/native/threads/mappings | `BufferPoolMXBean`, NMT, RSS |
| First pass slow, later passes fast | Page cache or warm-up | Compare cold/warm, observe disk read bytes |
| `write` fast yet data not durable | Measuring before `flush/force/sync` | Measure completion time after force/sync |
| `p50` steady yet `p99` terrible | Tail skewed by a few slow requests | Larger-sample histogram, trace slowest samples, stage timing |

Each row is only a **hypothesis to verify**; one symptom can have multiple causes. For instance, slowness on a network filesystem can reduce throughput while heap stays flat. Aligning metrics on the same timeline usually beats reading isolated snapshots.

## 8. Writing a Reproducible Benchmark Report

Example report structure (this is a **template for recording results**, not real benchmark numbers):

| Item | Information to record |
| --- | --- |
| Goal | Sequential large-file read, or handling an upload request |
| Latency scope | One `read` / one file / one request |
| Data size and pattern | File size, chunk size, sequential/random, compressed or not |
| Runtime | JDK version, heap flags, GC, worker count |
| Machine and I/O | CPU, RAM, disk/network filesystem, OS, page cache |
| Methodology | Warm-up passes, measured passes, sample count, percentile method |
| Throughput | MiB/s and total bytes/elapsed time |
| Latency | p50/p95/p99, ms or µs units, explicit measurement scope |
| Memory | Heap used/committed/sampled peak, direct pool, RSS, allocation rate |
| Reliability | Variance, cache conditions, limitations, and observer overhead |

When optimizing, preserve the **pre-change baseline**, then run the exact same workload on the new version. Record trade-off impacts as well: raising buffers from 8 KiB to 256 KiB may boost throughput on one host yet consume more RAM per concurrent connection, or slow down due to GC/cache pressure at another scale.

## 9. Self-Check Questions

**Question 1.** A program reads 200 MiB in 2.5 seconds. What is its throughput?

**Answer:** `200 / 2.5 = 80 MiB/s`. The unit is MiB/s if the input is in MiB; converting to MB/s requires unit conversion first.

**Question 2.** Can you take the p95 of individual `read` calls and call it the p95 “upload request duration”?

**Answer:** No. Request latency can include queuing, multiple reads/writes, processing, and response sending. Measure from start to end of the request if that is the SLA being evaluated.

**Question 3.** Both before and after heap snapshots show 70 MiB. Can you conclude peak heap was only 70 MiB?

**Answer:** No. Heavy allocation and GC collection could have occurred between snapshots, or spikes may happen between samples; continuous sampling/JFR/profiling is needed. Direct memory and RSS also lie outside `heap.used`.

**Question 4.** Why can 5 passes over a 32 MiB file achieve higher throughput than the very first read of a fresh file?

**Answer:** OS page cache, readahead, JVM warm-up, and other factors. Once file buffers are resident in RAM, results no longer measure raw cold disk speed.

**Question 5.** Why is `flush()` on a buffered stream insufficient to claim “data written durably”?

**Answer:** `flush` primarily pushes data from the stream layer's buffer down to the underlying layer. Durability may require `FileChannel.force` or `FileDescriptor.sync`, factoring in device/OS limits and business requirements.

**Question 6.** If throughput increases by 20% while request p99 triples and RSS exceeds container limits, is the solution better?

**Answer:** Cannot conclude so. Evaluate latency SLAs, memory budget, target load, and operational cost together. Violating latency/RAM requirements means higher throughput does not equate to successful optimization.

## 10. Practical Summary

1. **State clearly what operation is measured and in what unit.** `MiB/s`, `ops/s`, `p95 read()`, and `p95 request` mean different things.
2. **Count only completed work and actually transferred data.** Use `System.nanoTime()` for elapsed time, and sum bytes from `read`/`write` return values properly.
3. **Measure concurrently while understanding metric sources:** Java heap, direct/mapped, native, and RSS are distinct slices; snapshots are not peaks.
4. **Separate workload from noise:** test-file setup, caching, warm-up, JIT, GC, instrumentation, and durability all influence readings.
5. **Compare controlled runs, multiple passes, tail percentiles, and environment conditions.** Credible results are ones others can reproduce and explain.

For large files, the most reliable optimization path usually starts by benchmarking realistic workloads, identifying the bottleneck, and changing buffers/APIs/concurrency only when measurements prove the change satisfies speed, latency, and memory goals simultaneously.
