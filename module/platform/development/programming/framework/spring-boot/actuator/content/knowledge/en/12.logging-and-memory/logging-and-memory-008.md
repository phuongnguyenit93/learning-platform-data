# Evaluating CPU, Memory, Disk Space, and Time Costs of Creating Dumps

## 1. A Dump Is a Diagnostic Operation with Cost

When an application slows down or shows signs of a memory leak, a dump preserves state for later analysis. However, to produce that evidence, the JVM must perform extra work directly inside the process serving users.

Understand the two common types in Spring Boot Actuator properly:

- **Thread dump** records call stacks, states, and lock info of threads observed by the tool.
- **Heap dump** records objects and reference relationships in the Java heap to analyze retained memory.

A thread dump fits the question "what are threads doing and where are they waiting?". A heap dump fits the question "which objects are retaining memory and via which reference paths?". A heap dump is not a full copy of every memory region in the process; it does not replace diagnosing native memory, direct buffers, or overall OS state.

With Actuator, `threaddump` can return JSON or plain text; `heapdump` returns binary data, usually needing to be saved to a file for analysis. Heap dump format depends on the JVM: HotSpot uses HPROF, OpenJ9 uses PHD. The coding exercise below targets **HotSpot, Java 17 or later**, using JDK 21 for baseline measurements. [Spring Boot 3.3: Thread Dump](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/threaddump.html), [Heap Dump](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html).

In this lesson, **garbage collection (GC)** is the work the JVM performs to reclaim memory from objects no longer needed. A **safepoint** is a coordination point where the JVM can perform certain operations with threads in a consistent state; depending on the operation, application threads may be paused to finish that work. Do not equate every safepoint with a GC event.

The goal is not to find a universal number like "a dump always takes 2 seconds". The goal is to know **what to measure, which resources to budget for, and when the cost exceeds the application's tolerance**.

## 2. Separating Four Cost Dimensions and Three Time Intervals

### 2.1. CPU, RAM, Disk, and Time Do Not Substitute for One Another

| Metric | Question to answer |
| --- | --- |
| CPU | How much extra processing time does the JVM spend traversing objects, collecting stacks, running GC, formatting, or compressing data? |
| Memory | While creating and streaming the dump, what extra memory does the process/container need beyond serving business traffic? |
| Disk | Where is the file created, how many bytes does it occupy, how many concurrent copies exist, and is enough room left for other operations? |
| Time | How long does the diagnostic work run, and during which interval are business requests impacted? |

A single dump might not raise average CPU much yet still cause severe slowdowns because the application pauses for an interval or I/O saturates. Conversely, CPU across multiple JVM threads can spike sharply over a fairly short wall-clock window.

### 2.2. Distinguishing Creation Time, Download Time, and Disruption Time

With a flow that writes a heap dump to a file and then downloads it via HTTP, visualize:

```text
Receive request
    -> authenticate / wait for coordination
    -> JVM creates dump file
    -> application reads file and streams response
    -> client saves file
```

There are three different measurements:

1. **Dump creation time**: from when the JVM starts the operation until the file finishes being written under the mechanism in use.
2. **Request completion time**: includes dump creation, network transfer, and client-side writing.
3. **Business impact time**: JVM pause duration, latency spike, request timeouts, queue buildup, and subsequent recovery time.

Do not take curl's runtime as the JVM pause duration. Do not take GC time alone as the entire dump creation time.

If the client times out after 30 seconds, that only proves the client stopped waiting. It does not prove work inside the JVM was canceled; inspect server state before thinking about another attempt.

## 3. CPU Cost: Understanding What the JVM Is Doing

### 3.1. Heap Dump

To write a heap dump, the JVM must traverse object structures, collect relevant metadata, and write their representations. If requested to record only reachable objects, the work may include a major garbage collection before writing.

In HotSpot, the `live=true` parameter of `HotSpotDiagnosticMXBean.dumpHeap` means writing only objects still reachable from other objects. Do not interpret `live` as "live dump with zero disruption". [JDK 21: HotSpotDiagnosticMXBean.dumpHeap](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html#dumpHeap(java.lang.String,boolean)).

JDK 21 `jcmd` documentation classifies `GC.heap_dump` as high-impact, depending on heap size and contents; the command requests a Full GC unless `-all` is used. This is tool guidance, not a promise of a fixed pause duration across every JVM. [JDK 21: jcmd GC.heap_dump](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

Factors to record in test results include:

- JVM version, vendor, and garbage collector.
- Heap in use, object count, and object graph structure.
- Whether only reachable objects or uncollected objects are also recorded.
- Actual allocated CPU, container CPU limits, and background load.
- File write speed, memory pressure, and compression if supported by the mechanism in use.

Switching to include uncollected objects can reduce some prior collection work, yet makes the data larger and still requires traversing/writing the heap. Do not conclude `live=false` means "zero JVM pause" or always cheaper in total cost. Do not apply HotSpot flags to OpenJ9 without verifying support.

### 3.2. Thread Dump

A thread dump does not snapshot every object on the heap, so it usually costs less than a heap dump on the same application. Nevertheless, collecting many stack traces and lock details, building the result, and converting it to JSON/text still consumes CPU and memory.

Cost grows with the number of collected threads, stack depth, and synchronization info recorded. Taking thread dumps continuously on an application with very many threads can become a load source itself.

In Spring Boot 3.3.0, `ThreadDumpEndpoint` uses `ThreadMXBean.dumpAllThreads(true, true)`. On JDK 21, `ThreadMXBean` observes **platform threads**, not virtual threads. Therefore, applications using virtual threads must check appropriate collection tools; a result with few threads does not prove the overall system has few tasks. [ThreadDumpEndpoint 3.3.0 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/management/ThreadDumpEndpoint.java), [JDK 21: ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

### 3.3. CPU Time Differs from Wall-Clock Time

Suppose an operation takes 4 seconds on the wall clock while threads in the process consume a combined 9 seconds of CPU. The two numbers do not contradict: multiple threads can run concurrently across multiple cores.

Conversely, an operation taking 20 seconds while CPU time rises very little may be waiting on I/O, throttled by CPU limits, or waiting for coordination with other threads.

To read measurements accurately, know whether the tool reports CPU per single core, across the whole host, or relative to container quota. Sparse CPU sampling can miss short spikes; process CPU time also includes background and business work running concurrently, not just the dump operation.

## 4. Memory Cost: Free Heap Alone Does Not Guarantee Safety

### 4.1. File Size Does Not Equal Extra RAM Needed

These metrics are distinct:

- `-Xmx`: Java heap limit.
- Heap used: measurement of the heap region at observation time.
- Process resident memory or memory billed to the container.
- Heap dump size on disk.
- Memory required by the dump analysis tool afterward.

An HPROF file is not a byte-for-byte copy of the entire `-Xmx` region. Selected objects, record framing, and metadata make file size differ from heap metrics. Do not adopt a rule like "dump always equals heap used" or "dump definitely never exceeds Xmx" to size capacity.

A mechanism that writes to a file and streams it does not require allocating an extra Java heap equal to the whole file either. That still does not make RAM cost zero: the JVM, I/O classes, thread dump results, network buffers, and intermediate layers all consume resources.

### 4.2. Looking at Process and Container Level

Beyond the Java heap are metaspace, code cache, thread stacks, direct buffers, and other native regions. On memory-constrained systems, monitor memory actually accounted by the OS/container, along with headroom for growing load.

Files placed on `tmpfs` consume memory even though the path looks like a regular disk directory. In Kubernetes, data in an `emptyDir` with `medium: Memory` counts toward memory usage rather than normal local storage. Writing a large heap dump there can push a container to its memory limit. [Kubernetes: managing resources and memory-backed emptyDir](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

With disk-backed filesystems, OS page cache and cgroup accounting must also be considered. Do not arbitrarily add RSS and page cache and treat it as exact container memory; pick one consistent accounting model for your environment.

### 4.3. Do Not Use Two Data Points to Assert Peak RAM

Heap before and after a dump can drop because of GC. That does not prove there was no memory spike during the dump or that the application suffered no impact.

To evaluate headroom, collect a dense time series across the whole test window: heap, process/container memory, GC, and I/O activity. If only before/after measurements exist, explicitly document that limitation.

The analysis machine has its own budget: the tool may build indexes and consume substantial extra RAM/disk. Do not open a large dump directly inside the same container experiencing memory pressure.

## 5. Disk Cost: Accounting for Write Location and Coexisting Copies

### 5.1. Files May Exist on Both Server and Client Sides

In Spring Boot 3.3.0's HotSpot branch, the endpoint creates a temporary file and returns a resource for streaming; the file is deleted when the read stream closes per the resource mechanism. It also holds a lock around the dump creation phase. [HeapDumpWebEndpoint 3.3.0 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/management/HeapDumpWebEndpoint.java).

Consequences to verify on your actual deployed version:

- A file exists on the server before reaching the client.
- A slow client can prolong how long the server-side file remains on disk.
- A dump-creation lock does not equal a cap on total files across all active downloads.
- Transfer errors, deletion errors, or abnormal process termination require a file cleanup procedure; do not rely on assuming cleanup always completes.

In this HotSpot branch, the temporary file is created via Java's temp directory mechanism, typically tied to `java.io.tmpdir`. Do not assume setting `-XX:HeapDumpPath` for `OutOfMemoryError` dumps automatically changes where the Actuator endpoint stores files. Those are two separate dump paths.

If you wish to specify a custom temp directory at startup, check mounts, write permissions, quotas, and impact on other components sharing that directory. On OpenJ9, check the PHD creation mechanism and location separately; do not infer from the HotSpot branch.

### 5.2. A Capacity Budgeting Formula

Use variables for the same filesystem:

```text
D_plan  = planned dump size based on equivalent testing
N       = maximum number of dump files coexisting on that filesystem
G       = headroom for logs and other data growing during the operation window
R       = minimum free space to keep for operations

Free_needed = N * D_plan + G + R
```

This is a planning calculation, not an exact HPROF size prediction formula.

Hypothetical example:

| Component | Value |
| --- | --- |
| One planned dump | 3 GiB |
| Potential growth of logs/other data | 1 GiB |
| Reserve free space to keep | 2 GiB |
| Currently free space | 8 GiB |

If only one file coexists, you need `3 + 1 + 2 = 6 GiB`: passes the set space condition. If two files coexist, you need `2 * 3 + 1 + 2 = 9 GiB`: fails.

Passing the disk check **does not mean the whole operation is safe**: CPU, RAM, and latency must still be evaluated separately.

Use exact units: `1 GiB = 1024 MiB`; do not mix decimal GB with GiB and treat divisions as exact. Check available space for the exact process account, quotas, file limits, inodes if applicable, and temporary space on proxies/intermediaries.

### 5.3. Compression and Retaining Multiple Copies Add Cost

Post-creation compression can reduce bytes transferred, yet consumes CPU, time, and may require extra disk space while the original and compressed files coexist. It does not erase the cost of creating the uncompressed dump beforehand.

If a tool has a direct compressed-write mode, evaluate that mode's speed and CPU separately. Do not assume Actuator 3.3 supports every compression option of `jcmd`.

## 6. Estimating Time with a Bounded Model

Suppose we plan for a **3 GiB = 3,072 MiB** file, measured effective write speed is **150 MiB/s**, and effective download link speed is **40 MiB/s**:

```text
Write phase:    3072 / 150 = 20.48 seconds
Transfer phase: 3072 / 40  = 76.8 seconds
```

The two numbers only show an I/O budget. They exclude heap traversal cost, GC, JVM coordination wait, authentication, proxies, or load variance.

During transfer, server reading, network, and client writing can run as a continuous pipeline. Speed is bounded by the slowest stage; do not blindly add all three durations for the same byte stream.

In mechanisms that finish creating the file before streaming, creation and download occur sequentially. Even so, do not add file-write time a second time if measured creation time already includes it.

Write speed while page cache is free can exceed the device's sustained rate. Software-level write completion is also not automatically a guarantee that data has been durably synced to storage hardware.

To pick an operational window, test with realistic heap, object types, load, resource limits, and storage devices; record the variance range rather than only the fastest run.

## 7. Small Java Experiment: Measuring Dump Creation Directly in the JVM

The following program creates a heap dump of **the test JVM itself**. It holds eight arrays of 1 MiB each; max heap is capped at 64 MiB via the launch command.

Run in a separate test directory with no real data. Dump files can contain data present in the JVM, so keep appropriate access permissions even in experiments. The program refuses to write if the target file already exists; use a fresh directory per run.

Save the code as `DumpCostProbe.java`:

```java
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class DumpCostProbe {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        Path output = Path.of("dump-cost-lab.hprof").toAbsolutePath();
        if (Files.exists(output)) {
            throw new IllegalStateException("Output already exists; use a fresh lab directory");
        }

        for (int i = 0; i < 8; i++) {
            byte[] block = new byte[1024 * 1024];
            Arrays.fill(block, (byte) i);
            RETAINED.add(block);
        }

        var memory = ManagementFactory.getMemoryMXBean();
        var os = (OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
        var diagnostic = ManagementFactory.getPlatformMXBean(HotSpotDiagnosticMXBean.class);
        long heapBefore = memory.getHeapMemoryUsage().getUsed();
        long cpuBefore = os.getProcessCpuTime();
        long started = System.nanoTime();

        diagnostic.dumpHeap(output.toString(), true);

        long elapsed = System.nanoTime() - started;
        long cpuAfter = os.getProcessCpuTime();
        long heapAfter = memory.getHeapMemoryUsage().getUsed();

        System.out.printf(Locale.ROOT, "wall.ms=%.3f%n", elapsed / 1_000_000.0);
        if (cpuBefore >= 0 && cpuAfter >= cpuBefore) {
            System.out.printf(Locale.ROOT, "process.cpu.ms=%.3f%n",
                    (cpuAfter - cpuBefore) / 1_000_000.0);
        } else {
            System.out.println("process.cpu.ms=unavailable");
        }
        System.out.println("heap.before.bytes=" + heapBefore);
        System.out.println("heap.after.bytes=" + heapAfter);
        System.out.println("dump.bytes=" + Files.size(output));
        System.out.println("retained.blocks=" + RETAINED.size());
    }
}
```

Compile and run with HotSpot JDK 17 or later:

```bash
javac --release 17 -encoding UTF-8 DumpCostProbe.java
java -Xms32m -Xmx64m "-Xlog:gc*,safepoint:file=dump-cost-gc.log:time,uptime,level,tags" DumpCostProbe
```

A verification run on HotSpot JDK 21 on Windows, using G1 and the heap bounds above, produced this stdout:

```text
wall.ms=7.565
process.cpu.ms=15.625
heap.before.bytes=17432576
heap.after.bytes=17419544
dump.bytes=11400364
retained.blocks=8
```

**These are measurements from a single run, not fixed arithmetic constants.** Duration, heap usage, and file size vary by JVM, GC, machine, and run. `retained.blocks=8` reflects the number of arrays intentionally held by the program.

How to read the results:

- `wall.ms` measures the `dumpHeap` call, excluding HTTP streaming or file analysis.
- `process.cpu.ms` is the process-wide CPU time delta over the measurement window; timer resolution can be coarse for a test lasting only a few milliseconds.
- `heap.before.bytes` and `heap.after.bytes` are two point measurements, not peak RAM during the operation.
- `dump.bytes` is the created file size, not extra RAM allocated.
- Eight 1 MiB arrays does not mean the file is only 8 MiB: the JVM holds other objects and the dump format has its own structure.

In this run, the GC log recorded a `Pause Full (Heap Dump Initiated GC)` lasting about **1.445 ms** and a `HeapDumper` safepoint totaling about **6.763 ms**. That illustrates why looking only at GC time misses other parts of the operation's duration. Do not extrapolate these numbers to multi-GiB heaps.

The program does not measure peak RSS, generate HTTP load, or simulate container quotas. For production assessment, use out-of-process measurements and representative load; do not push array sizes near the limit just to force a bigger number.

## 8. Measuring the Full Actuator Path Without Confusing Network Time

The template below targets **an enabled, exposed, and access-controlled endpoint** with valid HTTPS. Replace the example URL with an identified test system and use an authorized identity. This operation creates a new dump, rather than reading a static pre-existing file.

```bash
curl --user dump-operator --fail \
  --connect-timeout 5 --max-time 180 \
  --dump-header heap-case-001.headers \
  --output heap-case-001.hprof \
  --write-out 'http=%{http_code} start=%{time_starttransfer}s total=%{time_total}s bytes=%{size_download} speed=%{speed_download}B/s\n' \
  https://ops.example.test/actuator/heapdump
```

In Windows PowerShell, use `curl.exe` and put the command on one line if your shell does not support Bash line continuations. Supplying only the username prompts curl for the password instead of putting credentials directly in the command.

Curl figures to correlate with server metrics:

| Measurement | Interpretation |
| --- | --- |
| `http_code` | HTTP outcome; must confirm success before treating the file as a complete heap dump |
| `time_starttransfer` | Time to first response byte, including prior stages; not dump creation time alone |
| `time_total` | Total client-side duration, including both creation and download on this path |
| `size_download` | Downloaded bytes; does not prove format or completeness on its own |
| `speed_download` | Client-side average speed; not a pure network benchmark while creation/wait time is included |

The 180-second mark is an illustrative client wait limit, not a cancellation timeout for JVM work. Do not enable automatic retries that trigger repeated dumps on timeouts or connection errors.

During measurement, correlate on **the exact instance**:

- CPU time/utilization and CPU throttling events.
- Heap, process/container memory, and GC/safepoint metrics.
- Free space where files are created, I/O rate, and device queue depth.
- p95/p99 latency (95th/99th percentile), error rate, throughput, and business queue length.
- Signs of process restarts, OOM, or failed health checks.

If the downloaded file is incomplete or fails to open in a tool, inspect operation state and server-side files first; do not immediately trigger another new dump.

For thread dumps, use a request with `Accept: text/plain` or JSON as needed, save the output, and measure similarly. Do not assume it creates a huge server-side temporary file like a heap dump; yet collection, formatting, transfer, and storage still have cost.

## 9. Decision-Making Before, During, and After the Operation

### Before Creating

Define the diagnostic question before choosing the tool. If lock contention is suspected, a huge heap dump may not answer it; if you need the reference chain holding a set of objects, a thread dump lacks the evidence.

Pick a specific instance, record its version and relevant config, check CPU/RAM/disk budgets, and define how impact will be observed. For multi-instance services, consider shedding load or taking that instance out of rotation if operational procedures allow.

Set success criteria and stop-triggering conditions: disk headroom, latency tolerance, number of dumps retained, owner, and retention period. Thresholds should come from service requirements and testing, not a generic "safe" percentage.

### While Creating

Execute only the planned number of captures. Do not use dumps as a periodic health check; a single HTTP GET can still trigger very heavy work.

If metrics degrade, stop creating additional dumps and apply prepared load-shedding/mitigation plans. Do not claim closing curl safely cancels a running heap dump. Terminating the whole JVM has its own consequences and is not the default cancel button for a diagnostic action.

Watch shared resources too: writing a dump on the same device as a database or critical logs can impact other processes even if application CPU barely rises.

### After Creating

Verify HTTP status or call outcome, size, ability to open in a format-compatible tool, and instance/timestamp provenance. Store observation metrics alongside so analysts know under what conditions the dump was taken.

Move the file to a controlled analysis location, verify temp-file cleanup, and confirm reclaimed disk space. A successful download does not end storage costs or data-exposure risk: downloads, compressed archives, and analysis indexes all need explicit lifecycles.

## 10. Common Misleading Conclusions

| Claim | More accurate assessment |
| --- | --- |
| "There is free heap, so a dump has no impact" | Account for pauses, CPU, native memory, container limits, and I/O |
| "A 2 GiB file means exactly 2 GiB extra RAM is needed" | Distinguish file format, streaming mechanism, and actual memory |
| "Xmx is the guaranteed maximum disk space needed" | Budget via testing with headroom; do not treat Xmx as a format cap |
| "Thread dumps are always free" | Measure by thread count, stack depth, lock info, and frequency |
| "GC was only 100 ms, so users were impacted for only 100 ms" | Correlate full safepoints, I/O, and business recovery time |
| "Client timeout means the dump stopped" | Check the server; do not automatically fire more requests |
| "Only one dump runs at a time, so only one file exists" | Account for ongoing downloads holding files and other instances |
| "Switching to live=false eliminates pauses" | Object selection mode is not a non-disruption guarantee |
| "One laptop test suffices to predict production" | Representative workload, JVM, quotas, and storage are required |

## 11. Self-Check Practice

1. With a 3 GiB planned dump, 1 GiB growth headroom, 2 GiB minimum free reserve, and 8 GiB currently free, why does holding two concurrent dumps exceed the budget?
2. If a 3 GiB file downloads at an effective 40 MiB/s, roughly how long does the transfer portion take? Which costs are excluded from that number?
3. Why is `heap.after.bytes` being smaller than `heap.before.bytes` insufficient to conclude the operation caused no memory pressure?
4. Run the program in a fresh directory, keeping stdout and the GC log. Separate GC time, safepoint time, and call duration; explicitly note unmeasured figures.
5. When a heap dump request times out, what must be verified before making the next attempt?

Cross-check: item 1 needs `9 GiB`, exceeding `8 GiB`; item 2 is roughly `76.8 seconds` for transfer alone under the assumption. A complete evaluation must connect resource consumption, file storage location, and impact on business work rather than recording only download completion time.
