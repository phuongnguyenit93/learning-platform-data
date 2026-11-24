# 6.3 MemoryMXBean, MemoryPoolMXBean, and the meaning of used, committed, max, init

## Learning objectives

When diagnosing a Java runtime, a dashboard may display **heap used = 600 MiB**, **heap committed = 768 MiB**, and **heap max = 1 GiB**. These seemingly simple numbers are often misread as "Java has occupied 768 MiB of physical RAM", "exactly 424 MiB is guaranteed to be allocatable", or "heap growth means a memory leak". In reality, the Java Management API provides **snapshots of memory domains managed by the JVM**, not the operating system's entire allocation table.

This lesson focuses on two standard MXBeans in the `java.management` module:

- **`MemoryMXBean`:** an overall view of **Java heap** and **non-heap** memory reported by the JVM.
- **`MemoryPoolMXBean`:** a per-**memory-pool** view provided by the JVM (e.g., collector heap regions, Metaspace, or code cache in some HotSpot configurations).
- **`MemoryUsage`:** a snapshot object carrying the four numbers `init`, `used`, `committed`, and `max` in **bytes**.

After this lesson, you will be able to accurately distinguish the four fields, select appropriate measurement patterns and monitoring ratios, read per-pool data, understand peak/collection usage and thresholds, write Java 17+ programs using MXBeans, and **avoid confusing Java heap with RSS/native memory or concluding a leak from a single snapshot**.

> Scope: Java SE 17+ APIs and illustrative behavior on HotSpot/JDK 21. Pool names, pool counts, limits, and feature support levels may vary across JVMs/GCs/vendors. Measured values must come from **the exact JVM experiencing the incident**.

## 1. Three observation layers: JVM, pool, and snapshot

### 1.1 MemoryMXBean — the heap and non-heap picture

Obtain the bean for the **current JVM** via:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memory.getHeapMemoryUsage();
MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();
```

This is an **illustrative code snippet placed inside a class/method**, not a standalone program. `getHeapMemoryUsage()` returns the heap snapshot, and `getNonHeapMemoryUsage()` returns the JVM-managed non-heap snapshot. The two snapshots are taken in **two separate calls**, so they are not guaranteed to be atomic with respect to each other.

Java heap typically holds application objects/arrays and is managed by the garbage collector. Non-heap holds JVM-managed regions outside the heap, such as class/method metadata and JIT-compiled code regions, depending on the implementation. **Non-heap MXBean does not mean all native memory/RSS** of the process, and does not fully represent thread stacks, JNI allocations, native `malloc`, all memory mappings, or all off-heap buffers.

### 1.2 MemoryPoolMXBean — looking at the parts

`ManagementFactory.getMemoryPoolMXBeans()` returns the list of memory pools currently managed by the JVM. A pool has:

- `getName()`: VM-assigned pool name.
- `getType()`: `MemoryType.HEAP` or `MemoryType.NON_HEAP`.
- `getUsage()`: current `MemoryUsage` snapshot; **may be null** if the pool is no longer valid or the VM cannot obtain it.
- `getPeakUsage()`: snapshot of peak usage over time tracked by the VM.
- `getCollectionUsage()`: usage after the most recent GC reclamation effort that the pool supports tracking; **may be null**.
- `isValid()`: whether the pool still exists in the JVM's memory management system.
- `getMemoryManagerNames()`: names of the associated memory managers, not a list of threads.
- Threshold capabilities: `isUsageThresholdSupported()` and `isCollectionUsageThresholdSupported()`.

**Do not hard-code pool counts or pool names** as part of the Java API contract. On HotSpot with G1, you *might* see names like `G1 Eden Space`, `G1 Survivor Space`, `G1 Old Gen`, `Metaspace`, `Compressed Class Space`, or `CodeHeap` regions. With ZGC, Serial GC, another HotSpot release, or OpenJ9, partitioning, names, `max` values, and detailed semantics may differ.

### 1.3 MemoryUsage — four numbers from one snapshot

`MemoryUsage` is a value object describing memory state at a point in time in **bytes**, not a time series and not self-explanatory as to cause. For any `MemoryUsage u`:

```java
long init = u.getInit();
long used = u.getUsed();
long committed = u.getCommitted();
long max = u.getMax();
```

The `init` and `max` fields are allowed to be `-1`, meaning **"undefined"**, not 0 or "unlimited". `used` and `committed` are always non-negative per the `MemoryUsage` contract. When `max` is defined, the invariants are:

```text
0 <= used <= committed
if max != -1: committed <= max
init >= 0 or init == -1
max >= 0 or max == -1
```

**There is no invariant `init <= committed`**: the JVM can shrink committed memory below `init` over time. Nor is there a rule `init <= used`; `used` can be very low right after startup or GC. These are crucial distinctions when designing automated checks or reading metric tables.

## 2. Exact meanings of init, used, committed, and max

| Field | Method | Explanation | What **must not** be inferred |
| --- | --- | --- | --- |
| **init** | `getInit()` | Initial memory the JVM requests from the OS to manage this memory region at startup; **may be -1** | Not necessarily permanently retained RAM, does not have to equal current committed, does not have to equal used |
| **used** | `getUsed()` | Bytes of memory currently used in the measured region; for a GC pool, may include unreachable objects not yet reclaimed | Not strictly "live objects", not RSS, and does not prove a leak |
| **committed** | `getCommitted()` | Bytes of memory **guaranteed available for the JVM to use** within the measured region/pool; can grow or shrink | Not resident bytes in OS RAM; not always allocated objects |
| **max** | `getMax()` | Maximum limit reported for memory management of that region, **if defined** | Not the machine's available RAM, not committed memory; `-1` does not mean "unlimited" |

All four fields share the **same scope**: overall heap, overall non-heap, or **one** specific pool. You cannot directly compare Metaspace `used` against heap `max` to compute a percentage and conclude Metaspace is overloaded.

### 2.1 Used: currently in use, not necessarily alive after GC

For Java heap, `used` can rise rapidly as objects are created; after a GC cycle it can drop. In a **garbage-collected memory pool**, the `MemoryPoolMXBean` specification notes that `getUsage()` may count both **reachable and unreachable** objects still occupying memory before reclamation. Therefore:

- Heap `used` rising for a minute is **insufficient evidence of a leak**.
- `used` dropping after GC **does not prove there is no leak**; a slowly growing set of retained objects may still exist.
- High heap `used` with normal throughput/pauses/latency may simply be a deliberate GC trade-off.
- Low heap `used` **does not rule out** an `OutOfMemoryError` involving metaspace, direct buffers, native memory, thread creation, container memory limits, or allocating an object too large for available contiguous space.

### 2.2 Committed: guaranteed to the JVM, not RSS

`committed` is the memory capacity the JVM already has ready for use in that scope. Visualize:

```text
+----------------------- max (if known) ------------------------+
|      used       | free within committed |    uncommitted     |
+----------------- committed ------------------+---------------+
```

This is a conceptual model; the regions are not necessarily contiguous in virtual address space. As `used` approaches `committed`, the JVM **may** expand `committed` if headroom remains below `max` and OS resources allow; it may also trigger GC or fail allocation. When workload decreases, the JVM/GC **may** release memory and `committed` decreases.

Do not treat `committed - used` as the number of bytes the application can allocate "guaranteed not to fail": Java object layout, GC reserves, fragmentation, thread scheduling, safepoints, generational regions, native overhead, and OS/container state make that inference unsafe.

Nor is `committed` **synonymous with resident set size (RSS)**. OS RSS typically counts resident memory pages, including Java heap, thread stacks, JIT code, native allocations, shared mappings, etc., and page accounting may differ; `MemoryMXBean` does not cover all of them.

### 2.3 Max: usable ceiling, not a guaranteed allocation

If `max = 1 GiB` and `committed = 512 MiB`, then 1 GiB does not mean the JVM is occupying 1 GiB of RAM. The gap from 512 MiB to 1 GiB **has not been guaranteed by the JVM**; insufficient virtual memory, container limits, or native headroom can still cause allocation failure before `used` reaches `max`.

If `max == -1`:

- Record `undefined` or `unknown`; **do not compute** `used / max`.
- Do not interpret it as `0`, `Long.MAX_VALUE`, or unlimited.
- Some pools, especially non-heap pools, do not advertise a meaningful limit in `MemoryUsage` even though the runtime/OS still imposes practical constraints.

`max` may change under VM memory management mechanisms when defined. Hence values should be stored with timestamp, JDK/GC, and flags, rather than assumed constant across every JVM.

### 2.4 Init: starting point, not the current threshold

`init` describes the initial memory the VM requested when initializing management of that region. For heap, it may relate to `-Xms`, yet **you cannot infer every pool has `init` equal to a fixed fraction of `-Xms`**. The JVM can expand/shrink `committed`, and `init` may be undefined for a pool.

Consider three points in time:

| Illustrative snapshot | init | used | committed | max |
| --- | ---: | ---: | ---: | ---: |
| After startup | 256 MiB | 100 MiB | 256 MiB | 1,024 MiB |
| During load burst | 256 MiB | 650 MiB | 768 MiB | 1,024 MiB |
| After idle period | 256 MiB | 80 MiB | 192 MiB | 1,024 MiB |

These are **hypothetical numbers valid under the contract**, not a prediction that HotSpot will always shrink down to 192 MiB in any configuration. The table illustrates that `init` stays constant while `used` and `committed` vary; `committed` **can be smaller than `init`**.

## 3. Computing ratios correctly: each denominator tells a different story

Suppose a heap snapshot has:

```text
init      = 256 MiB
used      = 256 MiB
committed = 512 MiB
max       = 1,024 MiB
```

We have:

- **Used/committed** = `256 / 512 = 50%`: utilization relative to memory already guaranteed by the VM for that scope.
- **Used/max** = `256 / 1,024 = 25%`: utilization relative to the advertised maximum limit.
- **Committed/max** = `512 / 1,024 = 50%`: committed capacity relative to the ceiling of the same scope.
- **Committed - used** = `256 MiB`: theoretical difference between committed capacity and `used` at the snapshot.
- **Max - used** = `768 MiB`: arithmetic headroom up to `max`; **does not guarantee** all corresponding allocations will succeed.

The key point: the same JVM can be at **50% of committed yet only 25% of max**. A dashboard displaying a generic label "heap usage = 50%" without stating whether the denominator is **committed or max** will mislead capacity planning.

### 3.1 Formulas and preconditions

```text
utilization_committed = used / committed          (if committed > 0)
utilization_max       = used / max                (if max > 0)
commitment_ratio      = committed / max           (if max > 0)
committed_free_bytes  = committed - used
uncommitted_headroom  = max - committed           (if max >= 0)
```

If `committed == 0`, do not divide. If `max == -1`, **there is no meaningful used/max ratio**. Ratios must carry matching `pool/type`, instance, and timestamp; never divide instance A's numerator by instance B's denominator.

### 3.2 MiB, MB, and bytes

The API returns `long` in **bytes**, not KB/MB. For operational monitoring, standardize consistently:

- `1 MiB = 1,048,576 bytes` (binary).
- `1 MB = 1,000,000 bytes` (decimal).
- `-Xmx1g` and `-Xmx1024m` commonly use power-of-two units in the launcher/JVM; verify syntax for your VM/version.
- `-1` is an API sentinel, **not -1 bytes of real memory**.

A common display bug: computing `used / 1024 / 1024` and labeling it `MB`, when the unit of that conversion is actually **MiB**. The ~4.86% difference between MB and MiB can cause alerts to misfire near thresholds.

### 3.3 When max belongs to multiple pools

A JVM may report different `getMax()` values for Eden/Survivor/Old; they reflect GC partitioning, and pool limits may represent potential capacity rather than independent fixed regions. **Do not sum pool `max` values into heap `max`** as if every pool could reach its max independently. Likewise, summing `used` across pools read sequentially can differ slightly from `MemoryMXBean.getHeapMemoryUsage().getUsed()` because GC/allocations occur during reading.

Choose **overall heap** when you need heap capacity; choose **pools** when you need to see what is occupying space or creating pressure in a region, and note that readings are non-atomic.

## 4. Heap, non-heap, memory pools, and native memory: do not add them wrongly

### 4.1 Heap memory

Heap is the area for many Java objects/arrays, typically managed by GC. `MemoryMXBean.getHeapMemoryUsage()` provides a way to track current heap status. It is neither a "retained objects counter" nor the state of all process memory.

Interpreting common patterns:

- **Used rises before GC, drops after GC:** often normal allocation churn.
- **Committed rises and stays high:** the JVM expanded heap capacity for load, which does not mean objects are filling it all.
- **Post-GC `used` rises across consecutive GCs under comparable workload:** worth investigating retention, caches, class loaders, and lifecycles, though **not by itself proof of a leak**.
- **Heap max smaller than node RAM:** may be due to `-Xmx`, ergonomics, container limits, or other JVM defaults; read startup VM flags and resource limits rather than inferring from OS RAM.

### 4.2 Non-heap memory

`getNonHeapMemoryUsage()` reflects VM-managed non-heap areas. On HotSpot, pools like Metaspace and Code Cache may appear. However, native process memory has many sources outside this measurement:

- Native libraries / JNI allocations.
- Thread stacks and internal VM allocations.
- Direct/mapped buffers and memory-mapped files.
- GC bookkeeping and JIT compiler native allocations.
- C runtime/allocator memory and shared library mappings.

There is no rule `heap.used + nonHeap.used == RSS`. A gap **is not automatically a memory leak**; it can stem from different measurement scopes, reserved/committed/RSS semantics, and non-simultaneous snapshot timestamps.

To measure **direct/mapped buffer pools** in the Java Management API, also check `java.lang.management.BufferPoolMXBean` (e.g., `direct`/`mapped` pools if provided by the VM). That is a **different MXBean type**, not a `MemoryPoolMXBean` with `MemoryType.NON_HEAP`. Buffer pool metrics likewise do not replace tracking all native allocations.

### 4.3 Metaspace, Code Cache, and non-heap memory errors

An `OutOfMemoryError: Metaspace` can occur while heap `used/max` is still low. A failure to create new threads may stem from process/OS/native stack limits or container policies; increasing `-Xmx` can make total memory pressure even tighter. Likewise, errors in direct buffers or native allocations are not necessarily solved by increasing heap.

When diagnosing:

1. Read the **exception message** and JVM/GC version.
2. Cross-check `MemoryMXBean` heap/non-heap and each relevant `MemoryPoolMXBean`.
3. Cross-check **OS RSS/container memory**, process thread count, buffer pools, GC logs/JFR, and (if enabled at startup) Native Memory Tracking.
4. Check the **actual limits** for heap/Metaspace/native, including virtual memory usage and container constraints.
5. Do not tweak runtime flags merely because one snapshot looks high; identify cause, trend, and impact first.

## 5. Reading MemoryPoolMXBean properly

### 5.1 Each pool has its own type and name

`MemoryPoolMXBean.getType()` returns `MemoryType.HEAP` or `MemoryType.NON_HEAP`. Pool names label observations **for that JVM**, not a fixed Java SE catalog. Different implementations or collectors may add, omit, or change pools during the process lifecycle; `isValid()` checks whether a pool still exists.

Example table **illustrative, not fixed output**:

| Hypothetical pool | Type | Practical interpretation |
| --- | --- | --- |
| G1 Eden Space | HEAP | Region holding many new allocations; `used` typically fluctuates with GC cycles |
| G1 Survivor Space | HEAP | Region holding objects surviving some GC cycles, depending on G1 |
| G1 Old Gen | HEAP | Many long-lived objects; tracking after-GC usage helps evaluate retention |
| Metaspace | NON_HEAP | Class/method metadata; watch class loader lifecycles |
| CodeHeap 'non-profiled nmethods' | NON_HEAP | Part of HotSpot's code cache storing compiled code |
| Compressed Class Space | NON_HEAP | Class metadata region when the VM uses compressed class pointers |

Not every JVM is required to have all rows or the same names. `CodeHeap` regions may have different names with segmented code cache. Avoid hard-coding names as the sole filter across all dashboards. When querying across collectors, normalize by **type + pool name + VM/version** and maintain an explicit mapping strategy.

### 5.2 Current usage, peak usage, and collection usage differ

| Pool API | Question answered | Notes |
| --- | --- | --- |
| `getUsage()` | What is the pool's estimated current usage? | Snapshot; may include uncollected unreachable objects |
| `getPeakUsage()` | What peak has the VM recorded since startup/reset? | Not an average and not a 5-minute dashboard window peak, unless reset points are designed |
| `getCollectionUsage()` | After the most recent GC with data for this pool, what was usage? | May be `null`; may be "stale" if no suitable GC has run |
| `resetPeakUsage()` | Resets peak statistics | **Mutates bean state**; do not call in read-only monitoring |
| `isValid()` | Is the pool still valid? | Needed when the JVM changes memory pools |

**Peak** can remain very high from a spike that already ended. A UI showing a high peak does not mean current `used` is high. A graph polling `getPeakUsage().getUsed()` every 10 seconds normally **never decreases** until reset/restart; alerting on it for "current memory pressure" can produce false positives. Display current and peak as **two separate series**.

**Collection usage** is often analytically valuable when you want to see how many objects still occupy memory after a VM-recorded GC reclamation. However:

- It can be null if the VM/pool does not support it.
- The timestamp of the "most recent collection" need not match your scrape timestamp.
- A pool may be managed concurrently by the collector, with no crisp "after GC" point to measure.
- `getCollectionUsage()` **does not trigger a GC**; do not treat it as a "force JVM cleanup" button.

### 5.3 Relationship with MemoryMXBean

`MemoryMXBean` reports overall heap/non-heap. The pool list adds detail, yet summing pool values **is not a consistent transaction**. Pool A's and Pool B's snapshots are taken at two instants in a running JVM, and allocation/GC may occur in between.

For overall heap capacity, take **`MemoryMXBean.getHeapMemoryUsage()`** as the primary signal. If summing pools, state clearly that it is an estimate from separate samples and can differ; a dashboard showing a few MiB discrepancy does not by itself indicate an MXBean bug.

### 5.4 A pool having max = -1 while overall heap has a max

This can happen. A pool's `max` is **the limit advertised by that pool**, not a mandatory slice of total heap max. A pool may resize dynamically with GC, so the VM cannot or chooses not to publish a meaningful local max. Do not substitute `getHeapMemoryUsage().getMax()` when `getMax() == -1`, as the two scopes differ.

If you want to alert on a pool, base thresholds on **usage, after-GC trend, and pool/collector characteristics**, rather than forcing `used/max` onto every pool.

## 6. Complete Java 17+ example: reading overall and per-pool usage

Create the file **`MemoryMxBeanLab.java`**. The program is **read-only**: it does not trigger GC, set thresholds, or reset peaks. To avoid fabricating real byte counts from an unmeasured machine, it prints four lines **completely deterministically** from a simulated `MemoryUsage`, then prints the real values of the running JVM.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.util.Comparator;
import java.util.Locale;

public final class MemoryMxBeanLab {
    private static String display(long value) {
        return value == -1L ? "undefined" : Long.toString(value);
    }

    private static void printUsage(String scope, MemoryUsage usage) {
        if (usage == null) {
            System.out.println(scope + " unavailable");
            return;
        }

        System.out.printf(Locale.ROOT,
                "%s used=%d committed=%d max=%s init=%s%n",
                scope,
                usage.getUsed(),
                usage.getCommitted(),
                display(usage.getMax()),
                display(usage.getInit()));
    }

    public static void main(String[] args) {
        // Simulated data to verify the contract, not obtained from the JVM.
        MemoryUsage sample = new MemoryUsage(-1L, 256L, 512L, -1L);
        System.out.println("sample.used=" + sample.getUsed());
        System.out.println("sample.committed=" + sample.getCommitted());
        System.out.println("sample.max=" + display(sample.getMax()));
        System.out.println("sample.used<=committed=" +
                (sample.getUsed() <= sample.getCommitted()));

        // From here on is data from the actual JVM running the program.
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        printUsage("heap", memory.getHeapMemoryUsage());
        printUsage("nonheap", memory.getNonHeapMemoryUsage());

        ManagementFactory.getMemoryPoolMXBeans().stream()
                .sorted(Comparator.comparing(MemoryPoolMXBean::getName))
                .forEach(pool -> {
                    System.out.println("pool.name=" + pool.getName()
                            + " type=" + pool.getType()
                            + " valid=" + pool.isValid());
                    printUsage("  current", pool.getUsage());
                    printUsage("  peak", pool.getPeakUsage());
                    printUsage("  afterCollection", pool.getCollectionUsage());
                    System.out.println("  usageThresholdSupported=" +
                            pool.isUsageThresholdSupported());
                    System.out.println("  collectionThresholdSupported=" +
                            pool.isCollectionUsageThresholdSupported());
                });
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac MemoryMxBeanLab.java
java -Xms64m -Xmx256m MemoryMxBeanLab
```

**First four stdout lines are exact and machine-independent:**

```text
sample.used=256
sample.committed=512
sample.max=undefined
sample.used<=committed=true
```

The remaining lines **have no fixed stdout**: byte counts, pool names, peak, collection usage, threshold support, and even the GC used depend on JVM, vendor, version, workload, and run time. A formatting illustration, **not expected output**:

```text
heap used=<actual-bytes> committed=<actual-bytes> max=<bytes-or-undefined> init=<bytes-or-undefined>
```

Replace the placeholder text with real captured output; do not copy angle brackets or placeholder words as run results.

### 6.1 Why is the simulated sample useful?

The constructor `new MemoryUsage(-1L, 256L, 512L, -1L)` is valid because:

- `init = -1`: the VM does not publish an initial value.
- `max = -1`: limit is undefined.
- `used = 256` and `committed = 512` are non-negative and `used <= committed`.

Trying `new MemoryUsage(0, 513, 512, 1024)` throws `IllegalArgumentException` because `used > committed`. This is a property of the `MemoryUsage` object enforced by the API, **not a way to detect a memory leak**.

### 6.2 Why not print a "usage percentage" unconditionally?

The lab intentionally prints **raw values**. When computing ratios in a monitoring system, you must check `max > 0` or `committed > 0`. The case `max = -1` is not 0 and must not be divided by; if pools/GC change or pool names collide across instances, handle scope and identity first.

A percentage helper can be used only when the denominator is valid:

```java
// Additional snippet inside a class, not a standalone program.
static double usagePercent(long used, long capacity) {
    return capacity > 0 ? (100.0 * used / capacity) : Double.NaN;
}
```

`Double.NaN` represents an **undefined** ratio for the presentation layer to handle. You do not necessarily want to emit `NaN` into every metrics backend time series; when no denominator exists, many systems are better off **not emitting the ratio** or marking it unavailable.

### 6.3 Why is this reading a "sample JVM", not production yet?

Running the program creates **a new JVM**. It does not describe the service JVM experiencing an incident. To monitor production, you must:

- Instrument **the actual service process** to read MXBeans or use a properly authorized JMX/management endpoint.
- Tag data with application/build, host/container, PID, JVM start time, and UTC timestamp.
- Compare snapshots within **the same process** and comparable workload; do not treat output from a lab JVM as production output.
- Avoid exposing bean dumps containing sensitive paths, system properties, JVM command lines, or module names when enabling remote JMX.

## 7. Tracking changes over time: avoid concluding from a single snapshot

A single `MemoryUsage` carries neither a timestamp nor history. When collecting multiple samples, the observability system must attach:

- `capturedAtUtc`: timestamp when the JVM/collector recorded the data.
- `instance/processStart`: exact JVM identity to avoid stitching across restarts.
- `scope`: `heap`, `nonheap`, or pool name/type.
- `usedBytes, committedBytes, maxBytes, initBytes`: raw bytes; flag sentinel values.
- `gcName, javaVersion, relevantFlags` if comparing across GCs/JDKs.
- Polling interval length, missed samples, exporter lags, and retention limits.

### 7.1 Example of a normal allocation cycle

Suppose a service has max 1 GiB and is observed at closely spaced times:

| Time | Heap used | Heap committed | Reasonable interpretation |
| --- | ---: | ---: | --- |
| T0 | 250 MiB | 512 MiB | JVM has room within committed |
| T1 | 460 MiB | 512 MiB | Many objects allocated; not yet known if reachable |
| T2 | 610 MiB | 768 MiB | Heap can expand committed and use more memory |
| T3 after GC | 290 MiB | 768 MiB | Many objects reclaimed; committed need not shrink immediately |
| T4 much later | 280 MiB | 512 MiB | JVM may shrink committed if GC/policy permits |

The numbers are **hypothetical**. This is one plausible behavior, not a mandatory curve for every collector. What matters is **correlating with GC/events/workload**: looking only at T2 could lead to a false leak report.

### 7.2 Post-GC `used` rising: when is it suspicious?

For heap, a series of points **after effective reclaiming GCs** under similar load and state is usually more informative than watching raw `used` alone. If the post-GC floor rises across multiple cycles, that is a signal to inspect retained objects, caches, references, classloaders, or workload shifts.

However, "after GC" is collector-dependent: many GCs run concurrently/incrementally, and some pools have `getCollectionUsage() == null`. Do not label every sample after seeing a "GC" log line as full live heap. Cross-check GC event types, collection scopes, and timestamps.

### 7.3 Sampling interval affects conclusions

If heap has 2-second spikes while a dashboard scrapes every 30 seconds, the `used` gauge may miss the peaks. A pool's `getPeakUsage()` may preserve a peak from **the entire JVM lifetime** (or since reset), not necessarily a peak inside the 30-second window. To study short-lived allocation pressure, add JFR allocation/GC events, appropriate histograms/metrics, and a sampling interval fine enough to capture the phenomenon.

Do not "fix" discrepancies by forcing GC on every scrape: `System.gc()`/`MemoryMXBean.gc()` is not a passive read tool, can hurt latency, and distorts the workload under investigation.

## 8. Peak usage and collection usage: when to use them?

### 8.1 Peak is a watermark over time since reset

`pool.getPeakUsage()` returns the peak `MemoryUsage` tracked by the VM. Per the API, the peak value is maintained since JVM startup or since `resetPeakUsage()` was called. Use it to detect whether the JVM ever hit high usage, especially helpful for spikes that sparse polling might miss.

Limitations:

- The peak may have occurred before the incident and still remain recorded.
- Resetting the peak is a **diagnostic-state-mutating action** that can affect other people's dashboards.
- Peaks across different pools are not guaranteed to have occurred at the same instant.
- Peak usage differs from p95/p99 or a high-water mark over an arbitrary time-series database window.

If you need a "peak over the last 5 minutes" on a dashboard, store raw `used` samples at sufficient resolution and compute max-over-time in the backend, noting the resolution. Do not confuse it with the peak since JVM startup.

### 8.2 Collection usage means "after the most recent reclamation"

`pool.getCollectionUsage()` returns usage after the VM most recently tried to reclaim unused objects in the pool. If unsupported, it returns **null**. Thus some pools (e.g., pools holding long-lived objects under a GC with clear collection points) can signal **the objects still occupying space after GC**.

Do not misunderstand:

- "Collection usage" does not equal "exact live object graph".
- Some concurrent GCs do not provide clear collection points for threshold/collection usage to operate.
- `getCollectionUsage()` can be a stale snapshot if no suitable GC has run yet.
- Collection usage and current usage are not read atomically at the same instant.

When suspecting a leak, combine collection usage with a class histogram/controlled heap dump or JFR allocation, and do not substitute a single snapshot for a rising history.

## 9. Usage threshold and collection usage threshold

`MemoryPoolMXBean` supports two types of thresholds **depending on pool capability**, not guaranteed on every VM. `MemoryMXBean` can emit notifications when a pool exceeds a VM-detected threshold.

### 9.1 Usage threshold

A pool may support `isUsageThresholdSupported()`. If so, `setUsageThreshold(long bytes)` sets the threshold, but this is a **JVM monitoring-configuration-mutating action**, not a read-only operation. A positive threshold enables checking; 0 disables it. Checking happens when the VM sees fit, **with no guarantee of immediate notification at the exact byte the threshold is crossed**.

`getUsageThresholdCount()` is the number of times the JVM **detected the threshold was exceeded** under threshold semantics; not the number of allocations or GCs. `isUsageThresholdExceeded()` reflects whether usage is currently over the threshold as supported by the JVM. Check `isUsageThresholdSupported()` before calling related APIs, as some APIs can throw `UnsupportedOperationException` if unsupported.

### 9.2 Collection usage threshold

`isCollectionUsageThresholdSupported()` indicates whether a pool supports a threshold **after a collection operation**. This is particularly suitable when you want to alert only if memory remains high after GC, avoiding false alarms from brief pre-GC spikes.

If supported, `setCollectionUsageThreshold(long bytes)` configures the collection threshold; this also mutates state. When the VM detects after an appropriate GC that usage meets/exceeds the threshold, it can increment the counter and emit a notification via `MemoryMXBean`. Pools without clear collection points may **not support** this threshold.

Do not treat the notification count as the number of "leaks" or GCs. A notification means **the JVM detected a configured threshold crossing**, depending on check timing and usage dropping then rising again. Continuously staying above threshold does not require repeated infinite notifications.

### 9.3 Notifications from MemoryMXBean

`MemoryMXBean` can emit `MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED` or `MEMORY_COLLECTION_THRESHOLD_EXCEEDED` when the corresponding pool supports it and a threshold is set. Notifications belong to the JMX mechanism and typically contain pool name, usage snapshot, and count, not events about which specific object caused pressure.

Distinguish two kinds of operations:

- **Reading/monitoring:** calling `getUsage()`, `getPeakUsage()`, checking support flags; normally appropriate during a diagnostic session.
- **Control:** calling `setUsageThreshold`, `setCollectionUsageThreshold`, `resetPeakUsage`, or `MemoryMXBean.gc()`; requires clear purpose, authorization, agreement, and impact assessment.

Do not create examples that arbitrarily set thresholds in production, as that can break pre-configured alerting policies. In read-only exercises, printing the `...Supported` flags is enough to know whether such a mechanism can be built later.

## 10. Complementary JVM commands when MXBeans are not enough

MXBeans are useful for the current state of memory management; to explain **why** `used`/`committed` changed, additional sources are needed. The examples below target HotSpot JDK 21, with PID **12345 purely hypothetical**:

```bash
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 JFR.check
```

- `VM.version`: identify the exact JVM/version.
- `VM.flags`: inspect effective JVM flags related to heap/GC. Do not infer solely from `-Xmx` in manifests.
- `GC.heap_info`: obtain GC-dependent heap information; same scope, though structure need not match MXBean metrics identically.
- `JFR.check`: inspect running JFR recordings without starting one.

When **deep diagnostics** are needed, GC logs/JFR events help identify GC cycles, pauses, and allocations; heap dumps/class histograms can analyze object types/references but carry high cost/impact and may contain sensitive data. Do not trigger a heap dump just to verify a `used` number.

### 10.1 NMT vs. MemoryMXBean

Native Memory Tracking (NMT) on HotSpot tracks many internal JVM allocations. To use `jcmd PID VM.native_memory summary`, NMT normally must be enabled at **startup** (e.g., `-XX:NativeMemoryTracking=summary`) because an off state cannot be switched to summary/detail on a running process. NMT reports reserved/committed columns by category, differing from `MemoryUsage`.

NMT still does not cover all native memory from third-party libraries; NMT totals need not equal RSS either. Do not use the formula `RSS = heap.used + nonheap.used + NMT.total`: the measurement sources have different scopes and many areas **overlap**.

### 10.2 BufferPoolMXBean vs. MemoryPoolMXBean

`BufferPoolMXBean` provides info such as `getName()`, `getCount()`, `getTotalCapacity()`, and `getMemoryUsed()` for VM-supported buffer pools. Example:

```java
// Illustrative snippet inside a method, not a standalone program.
for (java.lang.management.BufferPoolMXBean p :
        java.lang.management.ManagementFactory.getPlatformMXBeans(
                java.lang.management.BufferPoolMXBean.class)) {
    System.out.println(p.getName() + " buffers=" + p.getCount()
            + " capacityBytes=" + p.getTotalCapacity()
            + " memoryUsedBytes=" + p.getMemoryUsed());
}
```

This dataset is useful when direct/mapped buffers drive memory growth outside the Java heap. It **does not share the four-field `init/used/committed/max` contract of `MemoryUsage`**, and `getMemoryUsed()` can also return -1 when the VM lacks a suitable estimate. Use it to supplement, not replace, heap/pool or OS metrics.

## 11. Common diagnostic scenarios

### Scenario A — Heap used near max, committed still below max

Hypothetical snapshot example:

```text
heap.used      = 750 MiB
heap.committed = 800 MiB
heap.max       = 1,024 MiB
```

`used/committed ≈ 93.75%`, `used/max ≈ 73.24%`. The JVM **may** still have room to expand `committed` toward `max`, though that does not guarantee allocation will succeed. Examine GC frequency/pauses, allocation rate, CPU, container memory limits, and `committed` fluctuations. If right after an appropriate GC `used` drops to 320 MiB, it may be a workload spike; if the post-GC floor climbs over comparable load, investigate retained references.

Do not fire a "heap near OOM" alert solely from high `used/committed` while `used/max` is still low without checking GC behavior; conversely, do not treat low `used/max` as guaranteed safety.

### Scenario B — Committed increases while used is nearly flat

The JVM may have expanded capacity anticipating load, retained it to avoid frequent memory commit/uncommit churn, or adjusted pool structures. This **is not automatically a leak** since retained objects have not clearly grown. Check committed/max, GC policy, heap flags, OS RSS, and container memory behavior. In memory-constrained systems, high `committed` can raise overall pressure even when `used` is low; yet `committed` itself does not equal resident pages used.

### Scenario C — Heap looks normal, yet container RSS keeps rising

First, **do not subtract** heap/non-heap `used` to claim the gap is an "untracked memory leak". Check:

- `getNonHeapMemoryUsage()` and pools like Metaspace/Code Cache.
- `BufferPoolMXBean` for direct/mapped buffers if present.
- Thread count, stack sizes, native libraries, mapped files, and OS indicators.
- NMT if enabled from startup, keeping its coverage limits in mind.
- Container memory limit, memory pressure, and page cache/accounting per the host's measurement system.

Conclusions must state the source and scope clearly. There may be a native memory issue invisible to heap MXBeans.

### Scenario D — After deployment, the Metaspace pool grows

Class loading/JIT during warm-up can legitimately raise non-heap usage. If Metaspace `used` keeps climbing on every module reload or new class loader creation without dropping over multiple cycles, inspect class loader retention, dynamic proxies, reflection/generated classes, deployment strategy, and JFR/VM classloader diagnostics. Do not apply a fixed threshold like "Metaspace > X MiB = leak" across every application.

### Scenario E — Pool max = -1, alert shows 100% or negative numbers

This is a logic bug caused by turning the sentinel into a denominator. Right inside the exporter:

```text
if max <= 0:
    export maxBytes as unavailable/undefined
    do NOT calculate used / max
else:
    calculate used / max
```

This is **pseudocode**, not Java. If the backend does not handle missing values well, split out a `hasDefinedMax` metric or attach metadata; do not fake `max = 1` or `0`. Fix queries/dashboards so pools with undefined max are excluded from ratios.

### Scenario F — Seeing sustained high peak after a brief spike

`getPeakUsage()` is not "current used". If a dashboard plots `peak.used` labeled "current memory used", readers will think the JVM is still high. Separate the two series and note that peak is since startup/reset, while current comes from `getUsage()`. For a 5-minute peak, store raw time series at sufficient resolution and compute max over the window.

### Scenario G — After GC, collection usage remains high

If the pool supports `getCollectionUsage()` and an appropriate GC event occurred, this can signal many objects continuing to occupy the pool. However, compare workloads, collector semantics, GC timing, request rates, and background jobs. Do not immediately conclude "leak proven"; it could be a legitimate live cache, retained session/batch state, or a stale snapshot.

## 12. Designing metrics and dashboards for MXBeans

One standardized convention (names are **suggestions**, not mandatory Prometheus/OTel metric names) is:

| Suggested series | Scope/labels | Value |
| --- | --- | --- |
| `jvm_memory_used_bytes` | `area=heap/nonheap`, instance | `MemoryMXBean` `used` |
| `jvm_memory_committed_bytes` | area, instance | `committed` |
| `jvm_memory_max_bytes` | area, instance, only when defined | `max` |
| `jvm_memory_init_bytes` | area, instance, only when defined | `init` |
| `jvm_memory_pool_used_bytes` | pool, type, instance | `MemoryPoolMXBean.getUsage().getUsed()` if non-null |
| `jvm_memory_pool_peak_used_bytes` | pool, type, instance | `getPeakUsage().getUsed()` |
| `jvm_memory_pool_after_gc_used_bytes` | pool, type, instance | `getCollectionUsage().getUsed()` when supported and available |

In systems using Micrometer, OpenTelemetry, or JMX exporter, **actual metric names and semantics may differ**; always check exporter configuration, units, labels, and missing-data conventions rather than assuming from names alone.

### 12.1 Every panel must state scope and denominator

- Total heap: used bytes, committed bytes, and max bytes (if available) on the same chart or correlated charts.
- Heap pressure: `used/max` when `max > 0`; state the denominator clearly and tune alerts to the workload.
- Capacity commitment: `committed/max` when defined; helpful to see how far the JVM expanded the heap.
- Memory pools: one line/legend per pool, with type and GC/vendor context; do not combine pools with different semantics into an unclear "heap ratio".
- Native process memory: RSS/container usage **from OS/agent** in a separate panel; do not add to MXBean numbers.

### 12.2 Missing data, negative sentinels, and exporter bugs

For undefined `init/max`, mark **unavailable** instead of converting to 0 and computing percentages. Never plot `-1` on a chart as negative memory. If `getUsage() == null` or a pool is no longer valid, the exporter must omit/mark the corresponding series, **never report `used=0`** because 0 is a semantically different observation.

When a process restarts, peak/threshold counters reset with the VM; separate the new series from historical data. `instance`/`processStartTime` labels or resource identity prevent stitching two JVMs together as one.

### 12.3 Collection frequency and precision

MXBeans reflect snapshots. Polling every 30 seconds can miss short spikes between polls; polling every millisecond adds overhead and can still miss memory peaks when GC runs concurrently. Pick the interval based on SLA, incident duration, and series cardinality; use GC logs/JFR events for detailed timelines.

Especially for memory pools with many objects and implementation-specific expensive usage calculations, continuous reading can raise overhead. The `MemoryPoolMXBean` documentation describes `getUsage()` as lightweight **in most cases**, yet some pools have costly calculations; measure in practice and do not assume every getter is always O(1).

### 12.4 Do not jump from metric correlation to causation

For instance, heap `used` and latency rising together could come from allocation pressure, GC, contention, a batch job, downstream backlog, or simply higher traffic. To conclude, correlate GC pauses, thread states, throughput, allocation samples, error traces, and rollout times. MXBeans are one piece of evidence, not a profiler or object graph.

## 13. Collection workflow for incidents

### Step 1: Anchor the exact JVM and timestamp

Record service, environment, host/container, PID, process start time, JDK version/vendor, GC, heap options, and UTC timestamp. Do not measure a demo Java process and extrapolate to a production JVM.

### Step 2: Capture totals first

Read `heap` and `nonheap` from `MemoryMXBean`, including **all four raw byte fields**. Check `used <= committed` and `max == -1`. If ratios look wrong, check units and denominators.

### Step 3: Inspect pools to locate pressured areas

Read `getMemoryPoolMXBeans()`, names/types, and current `getUsage()`. Use `getPeakUsage()` when watermark history is needed, and `getCollectionUsage()` if supported and available; distinguish types. Do not mutate thresholds/peaks during a read-only pass.

### Step 4: Compare across checkpoints and correlate

Keep at least a baseline window, an incident window, and a recovery window; record GC events and application throughput/request mix. Compute `used/max` only with a defined same-scope max; do not sum all pool maxes.

### Step 5: Escalate tools by symptom

If heap retention is suspected, use controlled allocation profiling/heap analysis; if RSS far exceeds heap metrics, add buffer pools, OS/process/container metrics, and NMT if enabled; if Metaspace grows, inspect class loading/classloaders. Assess impact before using heap dumps, forced GC, or heavy tools.

### Step 6: Report conclusions with explicit bounds

Example report structure:

```text
At 10:22:14 UTC, JVM service A (PID..., start time...)
  heap.used      = 256 MiB
  heap.committed = 512 MiB
  heap.max       = 1024 MiB
  used/max       = 25%
  used/committed = 50%

Relevant pool:
  name = <name-from-JVM>, type = HEAP
  current.used = <value>, afterCollection.used = <value-if-available>

Observations:
  used climbed during load bursts, with/without GC in the measured window.
Insufficient evidence for:
  leak, cause of RSS, code locations holding references.
Next steps:
  check JFR/GC logs, workload, and heap analysis if needed.
```

The numbers are **hypothetical ratio illustrations**, not production data. Only conclude what was measured in the right environment and timeframe.

## 14. Common confusions

| Misconception | More accurate statement |
| --- | --- |
| "`used` is the exact size of live objects after GC." | May include unreachable objects prior to reclamation; check GC/collection context. |
| "`committed` is the physical RAM the process is using." | It is capacity guaranteed to the VM, not RSS/working set. |
| "`max` is the bytes the OS has already allocated to the JVM." | Maximum limit, not committed memory or physical RAM. |
| "`max = -1` means unlimited." | It only means the limit is **undefined** per the API. |
| "`init` always equals `committed`." | `committed` can grow/shrink; even drop below `init` after shrinking. |
| "`used/max` and `used/committed` are the same." | Two denominators answer two different questions. |
| "Pool maxes can be summed into total heap max." | GC can allocate flexibly; pool maxes need not be independent. |
| "Sum of `used` across all pools always equals MemoryMXBean's `used`." | Snapshots are not atomically consistent and scope/timing may differ. |
| "Every JVM has Eden/Survivor/Old/Metaspace with the same names." | Depends on GC, implementation, vendor/version. |
| "Non-heap `used` + heap `used` equals RSS." | Does not capture all native/off-heap/mappings/OS accounting. |
| "`getCollectionUsage()` is always available and reflects the latest GC right at scrape time." | May be null or reflect the most recent applicable collection prior to that. |
| "`getPeakUsage()` is the peak of the last 5 minutes." | It is the VM-tracked peak since startup/reset, not a dashboard window. |
| "`resetPeakUsage()` is read-only." | It mutates statistic state. |
| "`setUsageThreshold()` can be used to read the default threshold." | It is a setter mutating the threshold; check support and getter first. |
| "Threshold notifications arrive instantaneously on every crossing." | The JVM checks at suitable mechanisms/times; not a per-byte sensor. |
| "Slow GC certainly means a memory leak." | GC pressure has many causes; correlate allocation, retained usage, and workload. |
| "Heap `used` below `max` proves OOM is impossible." | OOM can still happen from native/metaspace/direct/container limits or failed allocations. |

## 15. Self-check questions and answers

**Q1.** A snapshot has `used=400 MiB`, `committed=800 MiB`, `max=1,600 MiB`. What are the used/committed and used/max ratios?

**Answer:** used/committed = **50%**; used/max = **25%**. Both are valid within the same scope, yet carry different meanings.

**Q2.** A pool reports `init=256 MiB`, `committed=192 MiB`. Does this violate the contract?

**Answer:** No. `committed` is allowed to shrink below `init` when the JVM returns memory over time. The key invariants are `used <= committed`, and `committed <= max` when `max` is defined.

**Q3.** `getMax() == -1`, and a dashboard computes `used / -1` yielding a negative percentage. How should this be handled?

**Answer:** Mark it **undefined** and skip the ratio calculation; `-1` is an undefined sentinel, not negative or infinite capacity.

**Q4.** Heap `used` rises from 200 MiB to 650 MiB and drops back to 220 MiB after GC. Can you conclude there is a leak?

**Answer:** No. This pattern fits allocation churn. You must observe multiple cycles, collection usage (if available), workload, and retained references to evaluate a leak.

**Q5.** `MemoryPoolMXBean.getCollectionUsage()` returns null. May you emit value 0 to avoid chart gaps?

**Answer:** No. Null means no data/unsupported, distinct from an actual measured usage of 0. Record unavailable and rely on current usage and other sources.

**Q6.** Heap max is 1 GiB, Metaspace pool max is -1. Should you use 1 GiB as Metaspace's max?

**Answer:** No. Those are two different scopes; an undefined Metaspace max cannot be replaced with heap max.

**Q7.** A JVM has heap used 500 MiB while container RSS is 1.1 GiB. Is there a "600 MiB leak"?

**Answer:** Not proven. RSS includes various native/stack/mappings/resident heap regions and different accounting. Measure non-heap, buffer pools, NMT if enabled, and OS/container memory before concluding.

**Q8.** Why does a pool's `getPeakUsage()` remain high after current `used` drops?

**Answer:** Peak is the JVM's high-water mark since startup/reset; it is not cleared when GC reduces current usage. They are two separate metrics.

**Q9.** Can `MemoryMXBean.gc()` be called every 10 seconds to get "accurate after-GC usage"?

**Answer:** Not advisable. It is an operation requesting GC, **not read-only**, and can affect latency/throughput and distort the phenomenon. Use GC events/collection usage data when appropriate.

**Q10.** Why record the GC/JDK name when comparing memory pools across two environments?

**Answer:** Structure, pool names, region division, `max`, and collection/threshold support levels can differ. A chart mapping by hard-coded names can produce misleading comparisons.

## 16. End-of-lesson checklist

- Verify **exact JVM, PID/start time, JDK/GC**.
- Read **`MemoryMXBean` for heap and non-heap**, **`MemoryPoolMXBean` for pools**, and state the scope of each number.
- Keep **bytes** at the source; convert to MiB/MB with clear labels.
- Always enforce `used <= committed`, and `committed <= max` **only when max is defined**; `init` is not a current limit.
- Handle `init/max == -1` and `getUsage()/getCollectionUsage() == null` properly as **unknown/unavailable**.
- Distinguish **current, peak, and after-GC**; never mix them on the same series.
- Do not infer `heap + nonheap = RSS`, do not sum pool maxes, and do not conclude a leak from one snapshot.
- Compute ratios only with a positive denominator, same scope, and same instance.
- When suspecting a memory issue, correlate **workload, GC, RSS, NMT, buffer pools**, and deeper targeted tools while controlling overhead.
- Maintain secure access if using remote JMX, and never invoke setters/forced GC in a read-only collection pass.

**Conclusion:** `used` is current usage, `committed` is capacity guaranteed to the JVM, `max` is the advertised limit if present, and `init` is the initial value if present. To measure accurately you must understand **units, scope, timing, pool types, and GC semantics**. MXBeans surface signals and trends; conclusions about memory leaks/OOM require further evidence on allocation, retention, and resource limits.

### Official references

- [Java SE 21 — MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html): meaning of the four fields, -1 sentinel, used/committed/max invariants, and constructor validation.
- [Java SE 21 — MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap usage, notifications, and memory management scope.
- [Java SE 21 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): current/peak/collection usage, pool type/name, thresholds, and support flags.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): obtaining platform MXBeans from the JVM.
- [Java SE 21 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): direct/mapped buffer pool statistics and how they differ from MemoryPoolMXBean.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): VM/GC diagnostic commands and preconditions on a target JVM.