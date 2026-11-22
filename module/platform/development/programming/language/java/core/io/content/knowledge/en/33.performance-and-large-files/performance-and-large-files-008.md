# Effects of OS Caching When Benchmarking Java I/O

When measuring large-file read/write performance in Java, results can vary several-fold without **changing a single line of code**. The cause often does not lie solely in `FileInputStream`, `BufferedInputStream`, `FileChannel`, or `MappedByteBuffer`, but also in the **OS page cache**, readahead, write-back mechanisms, storage device caches, activity from other processes, and memory state at the time of measurement.

For example, reading a 2 GiB file from an SSD on the first pass may depend on how much data must actually be fetched from the device. If the data already resides in OS RAM, a subsequent read mainly copies data from the page cache to the application. Comparing those two passes and claiming “API A is faster than API B” is wrong if they were not measured under **comparable cache conditions**.

This lesson focuses on how OS caching skews benchmarks, distinguishing **cold-cache** from **warm-cache**, characteristics of read/write measurements, designing Java I/O experiments, and interpreting results without mistaking RAM access speed for device throughput.

## 1. Where Does the Page Cache Sit in the I/O Path?

On a typical operating system, reading a file on a filesystem may traverse these layers:

```text
Java application
   |
   | FileInputStream / FileChannel.read / Files.read...
   v
Kernel filesystem interface
   |
   v
OS page cache (RAM caching file data pages)
   |                         \
   | cache hit                 \ cache miss
   |                            v
   |                      File system + block I/O
   |                            |
   |                            v
   |                      Storage device (SSD/HDD)
   |                            |
   +<---------------------------+
   |
   v
ByteBuffer / byte[] / application
```

This is a **conceptual** model, not a fixed path for every filesystem, OS, or provider. The OS may cache metadata, perform readahead, copy or map pages, and coalesce I/O requests; SSD/HDD devices also have their own internal caches.

The **page cache** is RAM utilized by the OS to hold file data pages. When a read needs pages already present in cache (*cache hit*), the kernel can serve them without re-reading all data from the storage device. When the needed pages are absent (*cache miss*), the system must fetch data from lower layers, which is usually slower and more variable.

Two concepts to distinguish:

- **Java application cache:** `byte[]`, `ByteBuffer`, `BufferedInputStream`, custom caches, or library caches. Data lives by JVM/application rules.
- **OS cache:** typically managed by the kernel and shared across processes. Closing `FileChannel` or recreating Java objects does not mean the kernel evicted the file's pages from cache.

Reading a file, closing the stream, and opening a new stream to the same file can still **read from the kernel cache**. Thus, “creating a new `FileChannel` for each benchmark pass” does not guarantee every pass starts cold.

## 2. Cold Cache and Warm Cache Are Different Problems

| Situation | Practical meaning | What is being measured? |
| --- | --- | --- |
| **Cold-ish read** | Most needed data is not yet in the page cache | Reads may incur device, metadata, and readahead costs |
| **Warm read** | Most data is already in the page cache | Kernel/cache cost, data copying, Java processing, memory bandwidth |
| **Mixed read** | Some pages hit cache, some must be fetched | Mix may differ from pass to pass |
| **Working set larger than available cache RAM** | Eviction/cache thrashing may occur | Dominated by I/O stream, RAM size, and competing workloads |
| **Multiple processes reading the same file** | One process warms cache for another | Depends on overall system activity, not just one JVM |

“Cold” must be defined **by data scope and system state**. A file never opened by the program itself is not guaranteed cold: antivirus software, indexers, other processes, or the command that created the file may have placed its pages into cache.

Conversely, “warm” does not guarantee every byte stays in RAM forever. The kernel can reclaim pages at any time to free RAM for other tasks. If a file is large or the machine is under memory pressure, even a second read can suffer many cache misses.

**Never treat one cold measurement and one warm measurement as comparable samples when comparing libraries or APIs.** If production repeatedly reads the same files, warm-cache performance may be the right target. If production scans new files after startup or datasets larger than RAM, test cold/mixed-cache and real storage throughput.

## 3. Why Is the First Read Not Guaranteed Cold?

A sequence that sounds logical:

```java
Files.write(file, testData);
long first = timeRead(file);
long second = timeRead(file);
```

still does not produce a true **cold versus warm** comparison. Because `Files.write()` just wrote `testData`, many OSes retain newly written pages in the page cache. Even though `first` is the application's first **read**, the data may **already be warm from the write**.

Other reasons the first read is not cold:

1. The file was created, copied, or checksummed right before the benchmark.
2. Another process recently read the file, populating the shared cache.
3. The OS performs readahead: during a sequential read, **later** pages may be prefetched before code calls `read()` at those offsets.
4. Filesystem metadata/inode/dentry caches or storage device caches affect timing even when data pages are not warm.
5. The benchmark framework ran warm-up iterations, inadvertently warming the very data intended for a cold test.
6. A new container or JVM shares the same kernel with prior workloads; starting a new container **does not clear the kernel cache**.

Therefore, an initial measurement should only be called the **first measured pass** unless there is proof that the working set started under controlled cache conditions.

## 4. BufferedInputStream Is Not the Page Cache

`BufferedInputStream` holds a Java-side buffer, reducing calls down to the underlying `InputStream` when the application reads byte by byte or in tiny slices. `FileChannel.read(ByteBuffer)` can read a large block in one call. Yet **both are still typically served through the kernel's page cache** when reading files on a default filesystem.

Example:

```java
try (InputStream input = new BufferedInputStream(
        Files.newInputStream(file), 64 * 1024)) {
    int value;
    while ((value = input.read()) != -1) {
        consume(value); // Illustrative business method.
    }
}
```

This snippet is **not a standalone program**: it requires declaring `file` and `consume`, importing `java.io.*`, `java.nio.file.*`, and handling `IOException`. It illustrates an application-layer buffer, not bypassing kernel caching.

Adding another buffer layer **does not always make a program faster**. If the application already reads blocks into a `byte[65536]`, wrapping with `BufferedInputStream` may yield no commensurate benefit. If the application calls `read()` byte by byte, buffering can cut overhead. Conclusions require measuring with **comparable buffer sizes, page cache states, workloads, and processing logic**.

### Direct ByteBuffer Does Not Automatically Bypass the OS Cache

`ByteBuffer.allocateDirect()` creates a direct buffer outside the heap; it can reduce copy costs along some native I/O and JVM paths. However, **a direct buffer is not Linux `O_DIRECT`**, does not guarantee bypassing the OS page cache, and does not guarantee “zero-copy” in every scenario.

Comparing heap `ByteBuffer` and direct `ByteBuffer` requires separating allocation cost, reuse, copy count, cache hit rate, and device read cost. Without controlling page cache state, concluding “direct is faster than disk” may simply be measuring cache/memory rather than the drive.

## 5. Sequential Reads, Random Reads, and Read-Ahead

Operating systems typically optimize sequential reads with **readahead**: upon detecting a suitable access pattern, the kernel can prefetch blocks not yet requested. Thus, two benchmarks reading the same total bytes in different orders can produce vastly different results:

- **Sequential scan:** proceeds from start to end with relatively large blocks and high locality. Readahead can hide device latency.
- **Random access:** jumps across widely scattered offsets with low locality. Can reduce readahead effectiveness and trigger many small I/Os.
- **Repeated hot small region:** repeatedly reads the first few MiB of a multi-GiB file. Data may sit completely in RAM even when the total file exceeds RAM.
- **Many-file metadata walk:** reads attributes and opens thousands of small files. Metadata caches, path lookup, and syscall counts can outweigh data throughput.
- **Mixed read/write:** real workloads combine writes, re-reads, RAM contention, and background writeback; cannot be inferred directly from a sequential read-only benchmark.

To test I/O behavior for large files, define the **working set** as the bytes actually touched within the measurement window, not merely file length on disk. A 100 GiB file where a test touches only 4 MiB has an entirely different accessed working set from scanning the full 100 GiB.

For random reads, also fix the seed/rule generating offsets so two strategies hit identical data blocks. If each run uses arbitrary differing offsets, cache hit rates cannot be compared directly.

## 6. Write-Back Cache: “Finished” Writing Does Not Mean Data Is Durable

When `FileChannel.write()` or `Files.write()` returns successfully, many filesystems have accepted data into OS buffers/caches. That **does not prove the bytes reached durable storage**. The kernel can **write-back** modified pages (*dirty pages*) to the device later.

Consequently, a naive write benchmark may primarily measure how fast bytes copy into the page cache and finish before the kernel completes writing to the device. Reporting that number as “SSD write throughput” easily exaggerates performance.

| Measurement type | What is measured | What is not necessarily measured |
| --- | --- | --- |
| `write()` until buffer drained | Time for OS to accept bytes from application | Whether data is stable on the device |
| `Files.write(...)` then close stream | Completion of API write path and close | Power-loss durability across all filesystems |
| `FileChannel.force(false)` | Request to sync content (and metadata needed to retrieve it) per API contract | Does not directly mean caches were cleared |
| `FileChannel.force(true)` | Request to sync content and related metadata | Does not make the file cold for the next read |
| `StandardOpenOption.SYNC/DSYNC` | Alters sync policy when opening a file for writing | Not free in latency or identical across all filesystems |

`FileChannel.force(true)` requests **flushing updates to the device within the API's guaranteed scope**, not clearing the page cache. Across different storage/provider types, actual guarantees and costs vary. Calling `force` does not promise syncing all directory changes, renames, or device states across every power-loss scenario.

To benchmark **durable writes**, state explicitly whether `force()`/close timing is included, whether `SYNC/DSYNC` is used, whether the file existed or was newly created, byte count, and error handling. To benchmark API **write acceptance**, you may omit `force`, provided you label the metric accurately.

## 7. MappedByteBuffer and Memory Mapping Are Also Affected by Caching

`FileChannel.map()` maps a file region into the process address space; reading from `MappedByteBuffer` can trigger a **page fault** when the corresponding page is not yet available. Subsequent accesses can use the already mapped/cached pages.

Common measurement mistakes:

1. Mapping the file outside the timer and timing only page reads for memory mapping, while timing file open and buffer allocation inside the timer for `FileChannel.read()`.
2. One benchmark calls `mapped.load()` before measuring while the other lacks equivalent data warm-up.
3. Measuring one mapping pass cold and another warm without stating cache state.
4. Treating `MappedByteBuffer.isLoaded()` as definitive proof that **all pages always reside in RAM**. The API is only advisory; the OS can change residency right after the check.
5. Calling `mapped.force()` and assuming the mapping was evicted from cache. `force()` on a mapped buffer aims to **synchronize changes**, not evict pages.

Mapping has its own traits: page faults, page granularity, random access behavior, and mapping management overhead. Benchmarks must include mapping time if real workloads pay that cost and compare under equal cache states.

**Mapping is not zero-cost I/O.** For huge files, you must also consider mapped region size, address space limits, available memory, mapping lifecycle, and files being modified/truncated while mapped.

## 8. Complete Java 17+ Example: Measuring Multiple Read Passes Without Calling the First Pass Cold

The example below:

- Creates an **8 MiB** temporary file containing deterministic bytes (without touching user files).
- Writes using `FileChannel` and calls `force(true)` to illustrate the difference between content sync and cache eviction.
- Reads the same file sequentially **four times**, opening a new `FileChannel` each pass and reading through a 64 KiB `ByteBuffer`.
- Times each pass with `System.nanoTime()`, calculates MiB/s throughput, and prints it to **stderr** since timings are machine-dependent.
- Verifies total bytes and checksums across passes and prints **deterministic** verification results on **stdout**.

**This is a warm-up/cache observation demo, not a controlled cold-cache test and not proof of which I/O API is faster.**

Create **`OsCacheBenchmarkDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class OsCacheBenchmarkDemo {
    private static final int BLOCK = 64 * 1024;
    private static final int BLOCKS = 128; // 8 MiB.
    private static final int PASSES = 4;

    private OsCacheBenchmarkDemo() {}

    private record Result(long bytes, long checksum, long elapsedNs) {}

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("os-cache-benchmark-", ".bin");
        try {
            generate(path);

            Result[] results = new Result[PASSES];
            for (int i = 0; i < PASSES; i++) {
                results[i] = readAndMeasure(path);
                double seconds = results[i].elapsedNs() / 1_000_000_000.0;
                double mibPerSecond =
                        (results[i].bytes() / (1024.0 * 1024.0))
                        / Math.max(seconds, 1e-9);
                System.err.printf(
                        "pass=%d elapsed=%.3f ms throughput=%.1f MiB/s%n",
                        i + 1, results[i].elapsedNs() / 1_000_000.0,
                        mibPerSecond);
            }

            boolean sameBytes = true;
            boolean sameChecksum = true;
            for (Result result : results) {
                sameBytes &= result.bytes() == BLOCKS * (long) BLOCK;
                sameChecksum &=
                        result.checksum() == results[0].checksum();
            }

            System.out.println("file bytes=" + Files.size(path));
            System.out.println("all passes have full size=" + sameBytes);
            System.out.println("all passes have same checksum="
                    + sameChecksum);
        } finally {
            Files.deleteIfExists(path);
        }
    }

    private static void generate(Path path) throws IOException {
        byte[] bytes = new byte[BLOCK];
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] = (byte) (i & 0xff);
        }

        try (FileChannel out = FileChannel.open(path,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING)) {
            ByteBuffer source = ByteBuffer.wrap(bytes);
            for (int block = 0; block < BLOCKS; block++) {
                source.rewind();
                while (source.hasRemaining()) {
                    if (out.write(source) <= 0) {
                        throw new IOException("No write progress");
                    }
                }
            }
            out.force(true); // Sync request, DOES NOT evict page cache.
        }
    }

    private static Result readAndMeasure(Path path) throws IOException {
        ByteBuffer data = ByteBuffer.allocate(BLOCK);
        try (FileChannel in = FileChannel.open(
                path, StandardOpenOption.READ)) {
            long bytes = 0;
            long checksum = 0;
            long started = System.nanoTime();

            while (true) {
                data.clear();
                int n = in.read(data);
                if (n < 0) {
                    break;
                }
                if (n == 0) {
                    throw new IOException("No read progress");
                }

                bytes += n;
                data.flip();
                while (data.hasRemaining()) {
                    checksum += data.get() & 0xff;
                }
            }

            return new Result(
                    bytes, checksum, System.nanoTime() - started);
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac OsCacheBenchmarkDemo.java
java OsCacheBenchmarkDemo
```

**Stdout** when file creation and reads succeed:

```text
file bytes=8388608
all passes have full size=true
all passes have same checksum=true
```

**Stderr** will contain four lines `pass=1` through `pass=4`, each showing milliseconds and throughput computed from actual timings; **there is no fixed time or MiB/s value**. When run in a terminal, stderr output may interleave with stdout.

### What Does the Demo Prove and Not Prove?

1. `Files.createTempFile()` creates a new file; `generate()` writes exactly 128 blocks × 65,536 bytes = 8,388,608 bytes. Each block follows a byte pattern from 0 to 255.
2. `out.force(true)` requests synchronization before read measurements; however, the newly written data **may still sit in the page cache**. `pass=1` **must not be called cold**.
3. Each `readAndMeasure()` opens a new channel without asking the OS to evict recently read pages from cache. Thus multiple passes may be served from RAM.
4. The `read()` loop reads blocks up to 64 KiB; the checksum ensures contents are actually consumed instead of merely opening and closing the file.
5. Elapsed time includes `FileChannel.read()`, `ByteBuffer` operations, and checksum additions, while **excluding** buffer allocation, channel open/close, and file generation time. Hence it **does not measure device throughput in isolation**.
6. Stdout confirms every pass read the full file with matching checksums. Reading identical data does not tell you what percentage of each pass hit the page cache.

To compare different APIs, enforce identical data generation, cache state, byte counts, verification level, timer boundaries, and repetition counts. Longer measurements, reporting medians/p95/distributions, and observing disk I/O are more informative than an 8 MiB pass.

## 9. Designing Fair Benchmarks with Cache State in Mind

### Step 1: Define the Question to Answer

Two goals often differ:

**A. Real users repeatedly read a working set of cached files:** Measure a warm-cache workload since it reflects reality. Do not try to eliminate the page cache if production always benefits from it.

**B. The system processes many new/large files exceeding memory and causing disk I/O:** Construct datasets and access cycles that exercise cold/mixed caching, monitor storage metrics outside the JVM, and document reproducibility limits.

Never title a benchmark “measuring disk performance” when it just re-reads one small buffer from RAM.

### Step 2: Control the Working Set

Document:

- Total dataset size touched (not just one file's name/size).
- Physical RAM, available RAM, memory pressure, and cache capacity during measurement.
- File and filesystem type: local SSD/HDD, network share, tmpfs, virtual filesystem; if testing on **tmpfs/RAM disk**, data already lives in RAM and cannot be extrapolated to SSD/HDD.
- Sequential vs. random, block size, thread count, concurrency level, and interval between passes.
- Whether any file was freshly created/copied/written/checksummed, warming the cache right before measuring.
- Whether other workloads compete for RAM or disk concurrently.

A dataset **larger than RAM** lowers page cache hit likelihood in many cases, yet does not guarantee completely cold reads. The OS can still cache frequently touched regions, metadata, or optimize access paths. Do not state “file > RAM ⇒ guaranteed no caching” as a law.

### Step 3: Purpose-Built Warm-Up

For warm-cache benchmarks:

1. Run enough initial iterations for JIT/JVM, class loading, and I/O data to stabilize.
2. Separate warm-up measurements from main measurements.
3. Run multiple measured passes, compute distributions, and verify checksums/byte counts.
4. For A/B comparisons, alternate execution order (e.g., ABBA or randomized) to avoid always letting B ride on A's warm cache.

For **cold-cache**: warming Java code may still be needed, but warm-ups must not read the exact dataset that must remain cold for measurement. You can warm JIT on a separate equivalent dataset without touching the primary measurement set. Even then, shared caches and non-JVM activity must be monitored.

### Step 4: Separate Java Measurements from Storage Device Measurements

Alongside `System.nanoTime()`, gather appropriate OS-level metrics:

| Metric group | Why it helps |
| --- | --- |
| Total bytes read/written by application | Verifies equivalent workload volume |
| Actual disk I/O bytes, request count, queue, latency | Distinguishes device throughput from page-cache hits |
| Page faults / major faults (when relevant) | Indicates memory-mapping and page-access behavior |
| User/system CPU, context switches | Shows if benchmark is bottlenecked by Java parsing/copying/syscalls |
| Page cache/reclaim/memory pressure | Explains why passes exhibit differing cache hit rates |
| Dirty pages and writeback activity | Distinguishes writing to RAM from writing to device |
| Per-process vs. system-wide I/O | Avoids blaming disk I/O from another process on the benchmark |

These metrics do not always map each Java page-cache hit to one simple number. On Linux, system monitors like `iostat`, `pidstat`, `vmstat`, and `perf` (if available and permitted) can help; on Windows/macOS use equivalent tools. Record tools, OS version, and collection methods.

## 10. Can Java “Clear the Page Cache” for Cold Tests?

**Standard Java provides no portable API to clear the OS page cache for a file or the whole machine.** `FileChannel.close()`, `FileChannel.force()`, `Files.delete()`, `MappedByteBuffer.force()`, and `ByteBuffer.allocateDirect()` are not equivalent to dropping the kernel cache.

Some OSes expose native tools or hints to influence the page cache, but they:

- Differ across Linux, Windows, macOS, and filesystems.
- May require administrative privileges or kernel/filesystem support.
- Can affect the entire host, disrupting other processes, altering test conditions, and causing unwanted interference.
- Do not guarantee absolute cold state due to device caches, metadata, readahead, or other workloads.

**Never run crude host-wide page-cache drops on shared or production environments just for benchmark numbers.** If controlled cold tests are needed, use an isolated test machine, managed data/devices, and documented setup/monitoring procedures; any native actions must be approved by system owners.

One way to reduce cache reuse is testing across a sufficiently large set of files read in a controlled pattern, varying data order, and monitoring real disk I/O. Even so, call it a **cache-mitigated/mixed-cache test** unless cold conditions are verified.

## 11. Java Benchmark Biases That Often Accompany Page Cache Effects

Page cache is not the only factor. When numbers swing widely, also check:

| Bias | Example | Mitigation |
| --- | --- | --- |
| **JIT warmup** | First pass includes class loading/JIT compilation | Warm up code separately from cold dataset if needed |
| **GC/heap pressure** | Using `Files.readAllBytes()` on huge files into arrays | Pick appropriate read chunks, log GC/heap, keep tests fair |
| **Buffer allocation** | A calls `allocateDirect()` inside timer, B reuses heap buffer outside | Include or exclude allocation identically |
| **Checksum/parsing** | Every byte processed by CPU, masking I/O differences | Measure both full workload and minimal read path separately |
| **JVM/OS background load** | Antivirus, indexing, cron backups, other builds/tests | Isolate test window and record noise |
| **Thermal/power behavior** | CPU/SSD throttling, laptop power modes | Record power state, temperature, and steady conditions |
| **File allocation/compression** | Sparse files, filesystem compression, deduplication, all-zero data | Use realistic data; document filesystem features |
| **Disk cache/device cache** | First pass hits SSD controller cache | Do not treat page cache as the only cache layer |
| **Small sample** | Reading 100 KiB and extrapolating GiB/s | Increase data volume, report variance and error bounds |
| **Measurement scope** | A times `open()`, B does not | Align timer boundaries |
| **Contention** | Multiple benchmark threads reading the same file | Control concurrency and shared bandwidth |
| **Mixing A/B states** | Running A first to warm the file, then B | Alternate order or place both in equivalent states |

For I/O or buffer microbenchmarks, **JMH** can manage warm-up/measurement/forks and avoid many JIT pitfalls. However, **JMH does not reset the page cache or turn storage benchmarks into cold-cache tests**; environment and working set must be controlled outside the harness.

### Do Not Treat Speed Exceeding Disk Specs as Proof of a “Broken Benchmark”

If a workload is completely warm, observed throughput can exceed an SSD's nominal read speed several times over because most bytes come from RAM. That **can be valid for a warm-cache benchmark**. The mistake is interpreting that number as physical SSD bandwidth or using it to predict an application frequently reading cold data.

### Throughput and Latency Do Not Replace Each Other

Throughput can be computed as `MiB/s = bytes / (1024×1024) / seconds`. Yet per-operation latency and percentiles remain essential when workloads consist of many small requests. A system with high sequential read throughput can still have terrible p99 due to major page faults, long queues, or writeback contention.

## 12. Annotated Example of an A/B Experiment Design

Suppose you want to compare `Files.newInputStream()` + byte array against `FileChannel.read(ByteBuffer)`:

**Unfair:**

```text
A: read file X right after machine boot
B: re-read file X right after A
Conclusion: B is always faster than A.
```

A suffers more misses than B and may also pay JIT startup costs. The data does not prove API B is better.

**A sounder design:**

1. State the question: **warm-cache** sequential read speed or cold/mixed-cache? Publish results only for the controlled condition.
2. Use the same file, byte range, reasonable block size, and checksum/processing.
3. Warm up Java code and data according to the goal; if cold/mixed, prepare separate datasets and external control procedures outside the JVM.
4. Run multiple passes in alternating order, e.g. A→B→B→A, never letting one API always go first.
5. Record bytes, duration, throughput, CPU, disk I/O, GC, and test conditions; report median and distribution rather than best speed alone.
6. Check whether cache state drifted between passes, consider dropping noisy runs, and publish outlier rejection criteria before running.
7. If production uses multiple clients, also benchmark contention, file sizes, and concurrency resembling production.

Never change API, buffer size, random vs. sequential pattern, thread count, and flush timing all in one experiment and attribute the entire difference to the API.

## 13. Common Mistakes and Fixes

| Misconception / mistake | Consequence | Right approach |
| --- | --- | --- |
| Calling the first read cold just because it is Java's first read | File may already be warm from creation/copying | Label as first measured pass, control data, measure disk I/O |
| Closing `FileChannel` and thinking cache was cleared | Next read is still served from RAM by the kernel | Separate channel lifecycle from page cache |
| Calling `force(true)` and trusting the next read is cold | Force has no eviction semantics | Use force only when measuring sync/durability |
| Using `allocateDirect()` to bypass the page cache | Direct buffers are not `O_DIRECT` | Measure copy/alloc separately, state cache path |
| Running A then B on the same file | B usually enjoys warm cache from A | Alternate order or separate cache states |
| Timing only `write()` and reporting durable disk write throughput | Measures mostly write-back buffering | Report write acceptance or include `force()` as appropriate |
| Creating the test file right before a “cold read” | Data may be retained in page cache | Use dedicated cold setup and verify with metrics |
| Reading a few MiB and extrapolating to multi-GiB files | Small working set fits in RAM | Measure with a production-sized working set |
| Calling `MappedByteBuffer.load()` for only one strategy | Unfair warm-up advantage | Keep warm-up scope equivalent |
| Using JMH assuming cache resets per fork | Forking the JVM does not reset kernel cache | Control cache outside JMH |
| Not reading fully / skipping content verification | Approaches do unequal amounts of work | Count bytes, use checksums or appropriate blackholes |
| Using compressed/sparse/all-zero files unlike production | Distorts filesystem/storage speed | Generate realistic workload data |
| Reporting only one best MiB/s figure | Hides variance, cold/warm state, and noise | Report distribution and environment configuration |
| Dropping page cache across an active shared host | Disrupts other workloads and skews readings | Use an isolated test host and approved procedures |

## 14. Checklist for a Reproducible Benchmark Report

A trustworthy file read/write report should answer:

1. **Goal:** Sequential read, random read, metadata, or durable write? Testing API or device?
2. **Dataset:** Total bytes actually read/written, file count, per-file size, entropy/compression level, newly created or pre-existing files.
3. **Cache condition:** Warm, verified cold, or mixed/unknown? How was the state prepared and verified?
4. **Environment:** OS/kernel, JVM/vendor/version, CPU, RAM, filesystem, storage device, container/VM or bare metal.
5. **Java config:** API, heap/direct buffer, block size, thread count, GC/heap size, open/close handling.
6. **Timer:** Does it include open, allocation, read/write, parsing/checksum, force, close, and cleanup?
7. **Methodology:** Warm-up pass count, measured pass count, A/B ordering alternation, random access seed.
8. **Metrics:** Bytes, MiB/s, latency, median/p95, GC/CPU, disk I/O, memory, and variance.
9. **Correctness:** Checksum/byte-count checks, EOF handling, partial read/write handling, `IOException` handling.
10. **Limitations:** Uncontrolled assumptions, device caches, or background tasks that could cause variance.
11. **Test safety:** Never drop caches on production hosts; never run destructive benchmarks on real data.
12. **Interpretation:** Scope conclusions to the measured workload and cache state; do not generalize into an absolute speed of “Java I/O.”

**Remember:** The OS page cache can turn a file-read test into a RAM-access measurement, while write-back can let a write test finish before data rests durably on the device. **Closing files, calling `force()`, starting a new JVM/container, or using direct `ByteBuffer` does not clear the page cache.** Sound benchmarks define cold/warm goals, control working sets, run fair multi-pass comparisons, verify byte volumes, and cross-check OS-level I/O counters before concluding anything about file or device performance.