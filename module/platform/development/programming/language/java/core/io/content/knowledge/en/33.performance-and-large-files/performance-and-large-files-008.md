# The Impact of OS Cache on Java I/O Benchmarks

When measuring large-file read/write performance in Java, results can differ by several times even **without changing a single line of code**. The cause often lies not only in `FileInputStream`, `BufferedInputStream`, `FileChannel`, or `MappedByteBuffer`, but also in the **OS page cache**, readahead, write-back mechanisms, storage device caches, background processes, and memory state at measurement time.

For example, reading a 2 GiB file from an SSD the first time may depend on how much data must actually be fetched from the device. If the data already resides in OS RAM, a subsequent read primarily transfers data from the page cache to the application. Comparing those two runs and declaring "API A is faster than API B" is wrong if they were not measured under **equivalent cache conditions**.

This lesson focuses on how OS caching skews benchmarks, distinguishing **cold-cache** from **warm-cache**, read vs. write measurement characteristics, how to design Java I/O experiments, and how to interpret results without mistaking RAM access speed for storage device throughput.

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

This is a **conceptual model**, not a fixed path for every filesystem, OS, or provider. The OS may cache metadata, perform readahead, copy or map pages, and coalesce I/O requests; SSD/HDD hardware also has its own internal caches.

The **page cache** is RAM used by the OS to store file data pages. When a read needs pages already in cache (*cache hit*), the kernel can serve them without re-reading everything from the storage device. When the needed pages are absent (*cache miss*), the system must fetch them from lower layers, which is typically slower and more variable.

Distinguish two concepts:

- **Java application cache:** `byte[]`, `ByteBuffer`, `BufferedInputStream`, custom caches, or library caches. Data lives according to JVM/application rules.
- **OS cache:** typically managed by the kernel and shared across processes. Closing `FileChannel` or recreating Java objects does not mean the kernel evicted those file pages from cache.

After reading a file and closing the stream, opening a new stream to the same file can still **read from the kernel cache**. Hence "creating a new `FileChannel` for each benchmark run" is not a way to ensure every run starts cold.

## 2. Cold Cache and Warm Cache Are Different Problems

| Scenario | Practical Meaning | What Does It Measure? |
| --- | --- | --- |
| **Cold-ish read** | Most needed data is not yet in the page cache | Reads may incur device, metadata, and readahead costs |
| **Warm read** | Most data is already in the page cache | Kernel/cache cost, data copying, Java processing, memory bandwidth |
| **Mixed read** | Some pages hit cache, some must be fetched | The mix may vary between runs |
| **Working set larger than available cache RAM** | Eviction/cache thrashing may occur | Dominated by I/O stream, RAM size, and competing workloads |
| **Multiple processes reading the same file** | One process warms cache for another | Depends on system-wide activity, not one JVM alone |

The term "cold" must be defined **by data scope and system state**. A file never opened by your own program is not necessarily cold: antivirus, indexers, other processes, or the command that created the file earlier may have brought its pages into cache.

Conversely, "warm" does not mean every byte stays in RAM forever. The kernel may reclaim pages at any time to allocate RAM to other work. If a file is large or the host faces memory pressure, a second read can still suffer many cache misses.

**Never treat one cold measurement and one warm measurement as equivalent samples to compare libraries or APIs.** If production reads the same files repeatedly, warm-cache performance may be the right metric. If production scans fresh files after boot or reads datasets exceeding RAM, test cold/mixed-cache and real storage throughput.

## 3. Why Isn't the First Read Necessarily Cold?

A seemingly reasonable workflow:

```java
Files.write(file, testData);
long first = timeRead(file);
long second = timeRead(file);
```

yet it does not produce a true **cold versus warm** comparison. When `Files.write()` just wrote `testData`, many operating systems retain the written pages in the page cache. Even though `first` is the application's first **read**, the data may **already be warm from the write**.

Other reasons the first read is not cold:

1. The file was created, copied, or checksummed right before the benchmark.
2. Another process recently read the file, populating the shared cache.
3. OS readahead: during sequential reading, **upcoming** pages may be prefetched before your code calls `read()` at those offsets.
4. Filesystem metadata/inode/dentry caches or storage device caches affect timing even when data pages are not warm.
5. The benchmark framework ran warm-up iterations, accidentally warming the exact data meant for the cold test.
6. A new container or JVM shares the same kernel as earlier workloads; starting a fresh container **does not clear the kernel cache**.

Therefore, initial measurement results should only be called the **first measured pass**, unless there is proof that the working set began under controlled cache conditions.

## 4. BufferedInputStream Is Not the Page Cache

`BufferedInputStream` maintains a Java-side buffer to cut down calls to the underlying `InputStream` when reading byte-by-byte or in small chunks. `FileChannel.read(ByteBuffer)` can read a large block in a single call. However, **both are still normally served through the kernel page cache** when reading files on standard filesystems.

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

This snippet is **not a standalone program**: it needs `file` and `consume` defined, imports `java.io.*`, `java.nio.file.*`, and `IOException` handling. It illustrates application-tier buffering, not proof that the kernel skips caching the file.

Adding a buffer layer **does not always make a program faster**. If the application already reads blocks into `byte[65536]`, wrapping with `BufferedInputStream` may yield little net benefit. If the application calls byte-by-byte `read()`, buffering can cut overhead. To conclude, measure with **matching buffer size, page cache state, workload, and processing logic**.

### Direct ByteBuffer Does Not Bypass the OS Cache Automatically

`ByteBuffer.allocateDirect()` allocates a direct buffer in off-heap memory; it can reduce copy costs across some native I/O paths and the JVM. However, **a direct buffer is not Linux `O_DIRECT`**, does not guarantee bypassing the OS page cache, and does not guarantee "zero-copy" in every situation.

Comparing heap `ByteBuffer` and direct `ByteBuffer` requires separating allocation cost, reuse, copy count, cache hit rate, and device read cost. Without controlling the page cache, concluding "direct is faster than the disk" easily mistakes cache/memory measurement for storage hardware speed.

## 5. Sequential Reads, Random Reads, and Read-Ahead

Operating systems commonly optimize sequential reads with **readahead**: when detecting a sequential access pattern, the kernel can prefetch blocks not yet requested. Thus two benchmarks reading the same total volume in different orders can yield vastly different results:

- **Sequential scan:** Proceeds from start to end of file, relatively large blocks, high locality. Readahead can hide device latency.
- **Random access:** Jumps across widely distributed offsets, low locality. Can defeat readahead and trigger many small I/Os.
- **Repeated hot small region:** Continuously reads the first few MiB of a multi-GiB file. Data can fit completely in RAM even when total file size exceeds RAM.
- **Many-file metadata walk:** Opens and reads attributes of thousands of small files. Metadata/path caching and syscall counts can outweigh data throughput.
- **Mixed read/write:** Real workloads involve writing, re-reading, RAM contention, and background writeback; they cannot be extrapolated directly from a sequential read-only benchmark.

To test I/O behavior for large files, define the **working set** as the bytes actually touched during the measurement window—not merely how large the file is on disk. A 100 GiB file where a test touches only 4 MiB has a completely different access working set than scanning all 100 GiB.

For random reads, also fix the seed/offset-generation rule so both read strategies hit the same data blocks. If each run picks arbitrary offsets, cache hit rates cannot be compared directly.

## 6. Write-Back Cache: "Done" Writing Does Not Mean Data Is Durable

When `FileChannel.write()` or `Files.write()` returns successfully, many filesystems have accepted the data into OS buffers/caches. That **does not prove bytes reached durable storage media**. The kernel may **write back** modified pages (*dirty pages*) to the device later.

Hence a simple write benchmark may mostly measure the speed of copying bytes into the page cache, finishing before the kernel finishes writing to the device. Reporting that number as "SSD write throughput" easily exaggerates hardware speed.

| Measurement Type | What It Measures | What It Does Not Guarantee |
| --- | --- | --- |
| `write()` until buffer drains | Time until OS accepts bytes from application | Data persisted safely on device |
| `Files.write(...)` then close stream | API-level write path and close completion | Power-loss durability across every filesystem |
| `FileChannel.force(false)` | Requests syncing content (and metadata needed to retrieve content) per API contract | Does not directly mean cache was cleared |
| `FileChannel.force(true)` | Requests syncing content and relevant metadata | Does not make the file cold for the next read |
| `StandardOpenOption.SYNC/DSYNC` | Alters sync policy when opening file for writing | Not free in latency or identical across all filesystems |

`FileChannel.force(true)` requests **flushing updates to the device within the API's contract**, not clearing the page cache. Across different storage/providers, actual guarantees and costs can differ. Calling `force` does not promise syncing all directory updates, renames, or devices under every power-loss scenario.

To benchmark **durable writes**, state explicitly whether `force()`/close is timed, whether `SYNC/DSYNC` is used, whether the file already existed or was newly created, byte counts, and error handling. To benchmark API **write acceptance**, you may omit `force`, provided you label the metric accurately.

## 7. MappedByteBuffer and Memory-Mapped Files Are Also Affected by Cache

`FileChannel.map()` can map a file region into the process's address space; reading from `MappedByteBuffer` can trigger a **page fault** when the corresponding page is not yet available. Subsequent accesses may use already mapped/cached pages.

Common measurement mistakes:

1. Mapping the file outside the timer and timing page reads for memory-mapped I/O, while timing file open and buffer allocation inside the timer for `FileChannel.read()`.
2. One benchmark calls `mapped.load()` before timing, while the competing benchmark does not warm equivalent data.
3. Measuring one mapping run cold and another mapping run warm without reporting state.
4. Treating `MappedByteBuffer.isLoaded()` as an exact verifier that **all pages stay in RAM**. The API is advisory only; the OS can change residency right after the check.
5. Calling `mapped.force()` and assuming the mapping was evicted from cache. `force()` on a mapped buffer is for **flushing modifications**, not eviction.

Memory mapping has distinct traits: page faults, page granularity, random access, and mapping management overhead. Benchmarks must include mapping time if the real workload pays it, and compare under equal cache conditions.

**Mapping is not zero-cost I/O.** For massive files, also consider mapped region size, address space limits, available memory, mapping lifetimes, and concurrent file modification/truncation while mapped.

## 8. Complete Java 17+ Example: Measuring Multiple Read Passes Without Calling the First Pass Cold

The following example:

- Creates an **8 MiB** temporary file with deterministic byte data (never touching user files).
- Writes via `FileChannel` and calls `force(true)` to illustrate the difference between content sync and cache eviction.
- Sequentially reads the same file **four times**, each time opening a fresh `FileChannel` and reading via a 64 KiB `ByteBuffer`.
- Times each pass with `System.nanoTime()`, computes throughput in MiB/s, and prints to **stderr** since timings depend on the host machine.
- Verifies total bytes and checksum across all passes, printing **deterministic** results to **stdout**.

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

Compile and run on JDK 17 or higher:

```bash
javac OsCacheBenchmarkDemo.java
java OsCacheBenchmarkDemo
```

**Stdout** when the file is created and read successfully:

```text
file bytes=8388608
all passes have full size=true
all passes have same checksum=true
```

**Stderr** will contain four lines `pass=1` through `pass=4`, each showing milliseconds and throughput computed from actual measurements; **there are no fixed timing or MiB/s values**. When run from a terminal, stderr may interleave with stdout.

### What Does the Demo Prove and What Does It Not Prove?

1. `Files.createTempFile()` creates a new file; `generate()` writes exactly 128 blocks × 65,536 bytes = 8,388,608 bytes. Each block follows a pattern from 0 to 255.
2. `out.force(true)` requests sync before read measurements; however, the newly written data **may still reside in the page cache**. `pass=1` **must not be called cold**.
3. Each `readAndMeasure()` opens a fresh channel without telling the OS to evict just-read pages from cache. Thus multiple passes may be served from RAM.
4. The `read()` loop reads chunks up to 64 KiB; the checksum ensures contents are genuinely consumed rather than merely opening and closing the file.
5. Elapsed time includes `FileChannel.read()`, `ByteBuffer` operations, and checksum accumulation, yet **excludes** buffer allocation, channel open/close, and file creation time. Thus it **does not isolate device throughput**.
6. The stdout lines verify every pass read the full file with identical checksums. Identical read data does not indicate what percentage of each pass hit the page cache.

To compare other APIs, apply the exact same data generation, cache state, byte volume, verification level, timed boundaries, and iteration counts. Running longer measurements, reporting median/p95/distributions, and observing disk I/O are more informative than an 8 MiB pass.

## 9. Designing Fair Benchmarks with Cache State in Mind

### Step 1: Identify the Question You Want to Answer

Two goals commonly differ:

**A. Real users repeatedly read a set of files already sitting in cache:** Measure a warm-cache workload because it reflects reality. Do not try to eliminate the page cache if production always benefits from caching.

**B. The system must process many new/large files exceeding memory and hitting disk I/O:** Construct datasets and access cycles to measure corresponding cold/mixed-cache behavior, monitor storage metrics outside the JVM, and document reproducibility limits.

Never title a test "measuring disk performance" when it only re-reads a small buffer repeatedly from RAM.

### Step 2: Control the Working Set

Record:

- Total size of the dataset touched (not just one file's name/size).
- Physical RAM, available RAM, memory pressure, and cache capacity during the run.
- File and filesystem type: local SSD/HDD, network share, tmpfs, virtual filesystem; if testing on **tmpfs/RAM disk**, data already lives in RAM and cannot generalize to SSD/HDD.
- Sequential vs. random, block size, thread count, concurrency, and interval between passes.
- Whether any files were recently created/copied/written/checksummed, warming the cache before measurement.
- Whether other workloads simultaneously consume RAM or disk.

A dataset **larger than RAM** lowers page cache hit rates in many cases, yet does not guarantee completely cold reads. The OS may still cache repeatedly touched regions, cache metadata, or optimize access paths. Never state "file > RAM ⇒ guaranteed no cache" as an absolute law.

### Step 3: Purposeful Warm-Up

For warm-cache benchmarks:

1. Run enough initial passes so JIT/JVM, class loading, and I/O data stabilize.
2. Exclude warm-up timings from primary statistics.
3. Run multiple measured passes, compute distributions, and check checksums/byte counts.
4. When comparing A/B, vary execution order (e.g., ABBA or randomized) to avoid always letting B benefit from A's cache.

For **cold-cache**: Java code warm-up may still be necessary, yet warm-up must not read the exact file set meant to stay cold for measurement. You can warm JIT using a separate equivalent dataset without touching the primary test set. Even then, shared caches and non-JVM activity must be monitored.

### Step 4: Distinguish Java Measurements from Storage Device Measurements

Alongside `System.nanoTime()`, collect appropriate OS-level metrics:

| Metric Group | Why It Helps |
| --- | --- |
| Total application bytes read/written | Verifies equivalent work performed |
| Actual disk I/O bytes, request counts, queues, latency | Distinguishes hardware throughput from page cache hits |
| Page faults / major faults (when relevant) | Hints at memory mapping and page access behavior |
| CPU user/system, context switches | Shows if Java parsing/copy/syscalls bottleneck the run |
| Page cache/reclaim/memory pressure | Explains why passes exhibit different cache hit rates |
| Dirty pages and writeback activity | Distinguishes writing to RAM from writing to device |
| Per-process vs. system-wide I/O | Avoids attributing another process's disk I/O to your benchmark |

These metrics do not always map each Java page cache hit to one simple number. On Linux, system monitors like `iostat`, `pidstat`, `vmstat`, and `perf` can be used (where available and permitted); on Windows/macOS use equivalent tooling. Document the tools, OS version, and collection method.

## 10. Can You "Clear the Page Cache" for Cold Tests from Java?

**Standard Java provides no portable API to clear the OS page cache for a file or an entire host.** `FileChannel.close()`, `FileChannel.force()`, `Files.delete()`, `MappedByteBuffer.force()`, and `ByteBuffer.allocateDirect()` are not equivalent to evicting the kernel cache.

Some operating systems offer native tools/hints to influence the page cache, yet they:

- Differ across Linux, Windows, macOS, and filesystems.
- May require administrative privileges or kernel/filesystem support.
- Can affect the entire host, disrupting other processes, altering test conditions, and causing unintended outages.
- Do not guarantee absolute cold state due to device caches, metadata, readahead, or other workloads.

**Never run crude host-wide page-cache drops on shared or production environments just to generate benchmark numbers.** If controlled cold testing is required, use an isolated test machine, managed data/devices, and documented setup/monitoring procedures; native actions must be approved by system owners.

One way to reduce cache reuse is testing across a sufficiently large file set read in a designed pattern, varying data order and observing real disk I/O. Even then, label it a **cache-mitigated/mixed-cache test** unless cold conditions are verified.

## 11. Java Benchmark Biases That Commonly Accompany Page Caching

Page caching is not the only factor. When numbers swing widely, also check:

| Bias | Example | Mitigation |
| --- | --- | --- |
| **JIT warmup** | First run incurs class loading/JIT compilation | Warm up code separately from cold dataset if needed |
| **GC/heap pressure** | `Files.readAllBytes()` turns a huge file into an array | Pick appropriate chunking, record GC/heap, keep tests fair |
| **Buffer allocation** | A calls `allocateDirect()` inside timer, B reuses heap buffer outside | Standardize whether allocation is inside or outside timing |
| **Checksum/parsing** | Every byte uses CPU, masking I/O differences | Measure both total workload and minimal read path separately |
| **JVM/OS background load** | Antivirus, indexing, backup cron, other builds/tests | Isolate test windows, record noise |
| **Thermal/power behavior** | CPU/SSD throttling, laptop battery profiles | Record power state, thermals, and steady conditions |
| **File allocation/compression** | Sparse files, filesystem compression, deduplication, all-zero data | Use realistic data patterns; note filesystem features |
| **Disk/device cache** | First pass hits SSD controller cache | Do not treat page cache as the only cache layer |
| **Small sample** | Reading 100 KiB and extrapolating GiB/s | Increase data volume, report variance and error bounds |
| **Measurement scope** | A times `open()`, B does not | Align timer boundaries identically |
| **Contention** | Multiple benchmark threads reading the same file | Control concurrency and shared bandwidth |
| **Mixed A/B state** | Running A first to warm the file, then B | Alternate order or put both in equivalent states |

For microbenchmarking I/O helpers or buffers, **JMH** can manage warm-up/measurement/forks and prevent many JIT pitfalls. However, **JMH does not reset the page cache or turn a storage benchmark into a cold-cache test**; configure environment/working sets outside the harness.

### Do Not Use Speed Exceeding Disk Specs as Proof of a "Broken Benchmark"

If a workload is fully warm, observed throughput can exceed nominal SSD read speed multiple times because most bytes come from RAM. That **can be accurate for a warm-cache benchmark**. The mistake is interpreting that result as physical SSD bandwidth or using it to predict an application frequently reading cold data.

### Throughput and Latency Do Not Replace Each Other

Throughput can be computed via `MiB/s = bytes / (1024×1024) / seconds`. Yet per-operation latency and percentiles are still needed when workloads consist of many small requests. A system with high sequential file throughput can still suffer terrible p99 latency due to major page faults, deep queues, or writeback contention.

## 12. Annotated A/B Experiment Design Example

Suppose you want to compare `Files.newInputStream()` + a byte array against `FileChannel.read(ByteBuffer)`:

**Unfair:**

```text
A: read file X immediately after machine boot
B: re-read file X after A
Conclusion: B is always faster than A.
```

A suffers more misses than B and may pay initial JIT compilation. The data does not prove API B is better.

**Better design:**

1. State the question: sequential read speed under **warm-cache** or cold/mixed-cache? Publish results only for the controlled condition.
2. Choose identical files, byte ranges, sensible block sizes, and checksum/processing logic.
3. Warm up Java code and data per goal; if testing cold/mixed, design separate datasets and external control procedures.
4. Run multiple iterations with alternating order—such as A→B→B→A—never letting one API always run first.
5. Record bytes, duration, throughput, CPU, disk I/O, GC, and test conditions; report median and distribution instead of just best speed.
6. Check whether cache state drifted across iterations; consider outlier rules defined prior to execution.
7. When production serves multiple clients, additionally benchmark contention, realistic file sizes, and concurrency.

Never change API, buffer size, random/sequential access, thread count, and flush timing all in one experiment and attribute the entire difference to the API.

## 13. Common Mistakes and Fixes

| Misconception / Error | Consequence | Right Approach |
| --- | --- | --- |
| Calling the first read "cold" because it is Java's first read | File may already be warm from creation/copy | Label as first measured pass, control data, and measure disk I/O |
| Closing `FileChannel` and thinking cache cleared | Subsequent reads still served from RAM by kernel | Separate channel lifecycle from page cache |
| Calling `force(true)` and believing the next read is cold | Force has no eviction semantics | Use force only when measuring sync/durability |
| Using `allocateDirect()` to skip page cache | Direct buffer is not O_DIRECT | Measure copy/alloc separately, document cache path |
| Running A first, then B on the same file | B routinely benefits from A's warm cache | Alternate order or separate cache states |
| Timing only `write()` and publishing durable disk throughput | Mostly measures write-back buffering | Report write acceptance or include `force()` as appropriate |
| Creating test file right before a "cold read" | Data may remain in the page cache | Use dedicated cold setup and verify with metrics |
| Reading a few MiB and extrapolating to multi-GiB files | Small working set fits in RAM | Measure with production-sized working sets |
| Calling `MappedByteBuffer.load()` for only one strategy | Unfair warm-up advantage | Keep warm-up scope equivalent |
| Using JMH and assuming cache resets per fork | Forking the JVM does not reset kernel cache | Control cache outside JMH |
| Not reading completely / not verifying contents | Competing approaches do unequal work | Count bytes, use checksums or proper blackholes |
| Using compressed/sparse/all-zero files unlike production | Distorts filesystem/storage speed | Generate realistic workload data |
| Publishing only one pretty peak MiB/s number | Hides variance, cold/warm state, and noise | Report distribution and environment configuration |
| Trying to drop page cache on a live shared host | Disrupts other workloads and skews measurements | Use an isolated test environment with approved procedures |

## 14. Reproducible Benchmark Reporting Checklist

A credible file read/write report should answer:

1. **Goal:** Sequential read, random read, metadata, or durable write? Testing an API or storage hardware?
2. **Dataset:** Total bytes actually read/written, file count, size per file, entropy/compressibility, freshly created or pre-existing files.
3. **Cache condition:** Warm, verified cold, or mixed/unknown? How was the state prepared and verified?
4. **Environment:** OS/kernel, JDK/vendor/version, CPU, RAM, filesystem, storage device, container/VM or bare metal.
5. **Java configuration:** API, heap/direct buffer, block size, thread count, GC/heap size, file open/close strategy.
6. **Timer:** Does it include open, allocation, read/write, parsing/checksum, force, close, and cleanup?
7. **Methodology:** Warm-up pass count, measured pass count, A/B ordering scheme, random access seed.
8. **Metrics:** Bytes, MiB/s, latency, median/p95, GC/CPU, disk I/O, memory, and variance.
9. **Correctness:** Checksum/byte-count verification, EOF handling, partial reads/writes, `IOException` handling.
10. **Limitations:** Uncontrolled assumptions, device caches, or background tasks that could sway results.
11. **Test safety:** Never drop caches host-wide in production; never run destructive benchmarks on real data.
12. **Interpretation:** Scope conclusions to the measured workload and cache state; never generalize into an absolute speed for "Java I/O".

**Key Takeaway:** The OS page cache can turn a file read test into a RAM access measurement, while write-back caching can let a write test finish before data reaches durable storage. **Closing a file, calling `force()`, launching a new JVM/container, or using a direct `ByteBuffer` does not clear the page cache.** Sound benchmarking defines cold/warm goals, controls working sets, runs fair multi-pass comparisons, verifies byte counts, and cross-checks OS-level I/O metrics before drawing conclusions about file or hardware performance.
