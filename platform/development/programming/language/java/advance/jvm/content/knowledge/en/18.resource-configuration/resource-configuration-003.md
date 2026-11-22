# `-Xms` and `-Xmx`: Initial and Maximum Heap Size and Trade-off Costs

**`-Xms`** and **`-Xmx`** are two JVM parameters commonly used to size the **Java heap**, where many application objects/arrays are allocated and managed by the garbage collector (GC). They answer **two different questions**:

- **`-Xms<size>`:** the **initial** heap that HotSpot prepares/manages at startup; related to memory commitment level and the ability to expand/shrink the heap afterward.
- **`-Xmx<size>`:** the **maximum limit** of the Java heap that the JVM is allowed to use, not the amount of heap actually used and certainly **not the total RAM limit** of the process.

Example:

```bash
java -Xms256m -Xmx1g -jar application.jar
```

Requests the JVM to start with a heap near 256 MiB and allows the heap to grow up to about 1 GiB, depending on rounding, memory regions, collector, and how the runtime reports size. **Do not interpret** this command as "the application immediately allocates 256 MiB of objects" or "the process never uses more than 1 GiB of RAM".

This article belongs to the **resource configuration** group in Java/JVM: the focus is on accurately understanding the concepts and observed trade-offs between **startup, pause/latency stability, GC frequency, memory footprint, container OOM, and headroom for native memory**. Examples run with Java 17+; `-XX` flags and ergonomics details mentioned are primarily for the **HotSpot JVM**.

## 1. Quick Identification: Two Flags but Four Size Layers

A heap can have multiple measurements at the same time:

| Concept | Name in Java Management API | Meaning |
| --- | --- | --- |
| **Initial** | `MemoryUsage.getInit()` | Initial capacity the JVM requests for heap management; may be undefined |
| **Used** | `MemoryUsage.getUsed()` | Memory currently used in the heap area according to the VM management view |
| **Committed** | `MemoryUsage.getCommitted()` | Capacity that the VM is guaranteed to be able to use for this area |
| **Max** | `MemoryUsage.getMax()` | Maximum limit usable for the heap, which may be undefined in some memory pools/VMs |

**`-Xms` is close to Initial**, **`-Xmx` is close to Max**. However, the numbers returned by the API may be **adjusted for alignment/GC region size**, and do not always match the command line string byte-for-byte. See `java.lang.management.MemoryUsage` to understand the API contract.

Commonly observed relationship on the Java heap:

```text
0 ≤ used ≤ committed ≤ max       (when max is defined)

               Max heap (-Xmx)
┌────────────────────────────────────────────────┐
│        Committed (committed by VM)             │
│  ┌──────────────────────────────────────────┐  │
│  │       Used (object/heap occupancy)       │  │
│  │  ┌───────────────────────────────┐       │  │
│  │  │ Live objects + allocations    │       │  │
│  │  └───────────────────────────────┘       │  │
│  │                  committed - used       │  │
│  └──────────────────────────────────────────┘  │
│              max - committed                   │
└────────────────────────────────────────────────┘
```

The diagram is **not to scale**. With collectors that have specific heap address-space mappings and different pools, details of `reserved`, `committed`, or how virtual memory is reported differ. However, the basic distinction **initial/used/committed/max** is essential to grasp.

### Commonly Confused Terms

- **Heap used:** VM metric for heap objects and used regions.
- **Resident Set Size (RSS):** number of physical memory pages of the **entire process** currently resident according to OS statistics, which may include heap, native memory, code, stacks, file mappings...
- **Virtual memory reserved:** virtual address space reserved by the VM, which does not mean all of it has physical RAM backing.
- **Container memory usage:** cgroup metric that may include components other than process RSS, such as page cache; see the metric definition.

**Do not treat `heap used`, `heap committed`, `RSS`, and `container memory.current` as different names for the same number.**

## 2. Basic Syntax and Understanding Units

Common ways to write them:

```bash
java -Xms128m -Xmx512m Main
java -Xms1g -Xmx4g Main
java -Xmx1024m Main
```

In HotSpot sizing flags, the suffixes `k`, `m`, `g` usually correspond to multiples of **1024**; the `java` documentation for the exact release is the authoritative source for syntax and valid limits. For operational interfaces, it is best to state **MiB/GiB** clearly instead of using "MB/GB" inconsistently.

| Option | Goal |
| --- | --- |
| `-Xms128m` | Requests an initial heap near 128 MiB |
| `-Xmx512m` | Maximum heap limit near 512 MiB |
| `-Xms1g -Xmx1g` | Requests equal initial and maximum: "fixed-size heap policy" in common usage |
| Only `-Xmx512m` | Max heap is specified; initial heap is determined by VM ergonomics/other flags |
| Neither specified | JVM calculates sizing based on memory, collector, JVM/version/container ergonomics |

**Validity rule:** Initial heap must not be greater than maximum heap; the configuration `-Xms2g -Xmx1g` will cause a startup error on HotSpot rather than automatically swapping the values for you.

### Command Placement Before Application Entrypoint

```bash
java -Xms128m -Xmx512m -jar app.jar
```

Correct when `app.jar` has a Main-Class manifest and corresponding build. JVM options go **before** `-jar`/main class. For example:

```bash
java -jar app.jar -Xmx512m
```

is not equivalent: `-Xmx512m` is then typically passed as an **application argument**, no longer a launcher JVM option. With many scripts/container wrappers, check the command line of the **actual process**, because configurations thought to have been passed may be stripped or placed in the wrong position.

## 3. "Initial" Is Not "Used"

If you run:

```bash
java -Xms256m -Xmx1g MyApp
```

when the process just starts, the application may only have a few tens of MiB of live objects. **Heap committed** may already be near the initial setting; **heap used** is much lower. The collector may GC/adjust the committed heap as workload increases or decreases according to policy.

An accurate way to state this:

> "`-Xms256m` requests the initial heap size and governs HotSpot's heap commitment/adjustment behavior; it does not instantiate 256 MiB of business objects and does not mean the application needs that much live data."

This is especially important in environments with **many JVM processes**: if initial heap is set too high for hundreds of processes, the aggregate committed/resident footprint can exhaust machine resources, even if each service only holds a small live set.

### Reserved, Committed, and Actual Physical Pages

HotSpot may **reserve** a large virtual address space for the maximum heap, and then **commit** on demand. The OS and page allocator decide backing memory/physical pages, which may be lazy-faulted. Therefore:

- Reserving virtual address space does not mean RSS grows to Xmx.
- Committing does not necessarily mean all pages are **touched** immediately at startup on every platform/collector.
- `-XX:+AlwaysPreTouch` (if supported by the HotSpot build) can touch committed heap pages at startup, shifting part of the page fault cost from runtime to startup.
- Large pages, GC, and OS mapping policies can change the details.

**Do not use `-Xms` as a tool to "set an exact number of GB of RSS"**; you must measure RSS/container metrics from the OS and heap data from the JVM.

## 4. "Maximum" Is Not "Process Memory Limit"

The Java heap is only one part of the JVM process. Model:

```text
CONTAINER / PROCESS MEMORY BUDGET
├─ Java heap (usually bounded by -Xmx)
├─ Metaspace and class metadata
├─ Code cache / JIT compiled machine code
├─ Thread stacks
├─ Direct ByteBuffers, NIO/native allocations
├─ GC metadata, remembered sets, marking structures
├─ JVM runtime internal native data
├─ Native libraries, JNI, libc arenas, TLS, mmap
├─ Process executable / shared libraries / stacks
└─ Related OS/cgroup accounting items
```

If the container limit is **1 GiB** and you set `-Xmx1g`, **total process memory can easily exceed 1 GiB** when adding non-heap. The kernel/container runtime may **OOM-kill the process** even though the JVM has not thrown `OutOfMemoryError: Java heap space`.

### Example Budget for Planning

Suppose the container memory limit is **1024 MiB**. You try `-Xmx512m`, leaving **512 MiB nominal headroom** for native/JVM/OS-related overhead.

**This is an initial allocation, not a mandatory default ratio.** A service with 1,000 threads, many direct buffers, or JNI may need more headroom. A small service with few threads and simple dependencies may use a different heap fraction, but all must be measured.

You need to monitor **peak RSS/cgroup usage**, not just heap after GC. If measurement shows non-heap peaks at 450 MiB and heap is near 512 MiB, the total can approach the 1024 MiB limit; not even counting all overhead/uncertainty. Leave a safety margin for bursts and diagnostic operations.

## 5. What Does Increasing `-Xmx` Provide?

Increasing maximum heap can help:

- Reduce the frequency of collections due to lack of heap space.
- Allow the app to handle a **larger live set**.
- Provide headroom for allocation bursts and GC concurrency phases.
- Reduce the risk of `OutOfMemoryError: Java heap space` if the real cause is heap pressure.
- Increase throughput in some workloads by reducing GC/expansion work.

In return, however:

- It can increase memory footprint and increase RAM contention with other processes.
- With some collectors/workloads, collection cycles or **tail latency** may vary with capacity and live data; there is no universal rule "double the heap → double the pause".
- If pre-touch/fixed large heap is enabled, startup may be heavier.
- Larger GC logs/heap dumps; diagnostics consume more resources.
- If the JVM process is in a small container, it is more prone to being OOMKilled due to insufficient native headroom.
- **Memory leaks are not fixed**: increasing heap only delays the time until out-of-memory.

### When Does Increasing `-Xmx` Actually Make Sense?

If you see many collections under load while after-GC live heap still has the space needed for the application, or GC repeatedly reclaims too little space because the heap is small, increasing max heap **may** be an option. However, you must distinguish:

- **Healthy allocation churn:** many short-lived objects; the collector handles it and SLOs are met.
- **Large legitimate live set:** data that genuinely needs to be retained is larger than the budget.
- **Memory leak/unbounded retention:** references are not released according to lifecycle; increasing Xmx only delays the failure.
- **Non-heap OOM:** metaspace/direct buffers/native threads; increasing Xmx does not solve it and may further reduce headroom.

**Do not choose Xmx by feeling "the machine has 16 GB RAM so allocate all 16 GB".** Look at the cgroup limit and the entire process/system budget.

## 6. What Are the Pros and Cons of Decreasing `-Xmx`?

Decreasing maximum heap can:

- Reduce the Java heap memory upper bound per JVM.
- Allow running more instances on the same node if non-heap fits.
- Cause GC to start collecting earlier; sometimes reducing retained/old-generation scan work in certain cases.
- Expose unbounded retention faster in test environments.

However, it can also:

- Increase GC frequency and GC CPU.
- Increase allocation stalls, promotion failures, evacuation failures, or Full GC depending on the collector.
- Lead to `OutOfMemoryError: Java heap space` when live data/allocations no longer fit.
- Reduce throughput and increase tail latency because the collector lacks headroom.
- Increase CPU/energy due to collecting too frequently.

**Do not assume by default** that decreasing Xmx always improves p99 because "GC has less memory to scan". A space-starved collector can struggle heavily, making p99 worse.

### A Better Rule of Thumb

**Xmx must be large enough to hold the live set plus headroom for allocations and GC activity** of the running **collector/workload**. Required capacity is not just the live objects in a single heap dump.

## 7. Small `-Xms`: Lighter Startup, Runtime May Have to Expand Heap

If initial heap is lower than max:

```bash
java -Xms64m -Xmx512m MyApp
```

The VM can start with a smaller committed heap, then **increase committed heap** as allocation demand grows (subject to collector constraints). Trade-offs:

**Potential pros:**

- Holds fewer resources initially if the workload is cold/light.
- May suit CLIs, short-lived batch jobs, serverless, or many JVMs on one node.
- Allows the VM to scale/return unused memory if the collector/VM supports it.

**Potential costs:**

- Heap expansion/commit can cause overhead/latency.
- Small initial heap can cause many collections during startup/warm-up.
- The JVM may have to commit/touch pages as allocation increases.
- Startup benchmarks may look faster, but the **first useful request** or the first few minutes may be worse.

**Important:** there is no guarantee that "small -Xms always has fast startup" or "large -Xms always reduces GC". Class loading, framework initialization, compiler activity, page faults, and filesystem cache also have an impact.

### What to Base Initial Heap Selection On?

If startup genuinely needs to load a few hundred MiB of objects, too small an Xms can lead to churn/expansion. If a service only has a 50 MiB live heap but Xms is set to multiple GiB, it may hold unnecessary footprint. Measure **startup class loading/allocation**, **initial GC logs**, **container RSS**, and latency to decide.

## 8. `-Xms` Equal to `-Xmx`: Fixed-Size Heap Policy

Common configuration:

```bash
java -Xms512m -Xmx512m MyApp
```

Possible benefits:

- Reduces some overhead from heap resizing/committing at runtime.
- Can make runtime behavior more stable in workloads with a relatively fixed footprint.
- Easier to predict the Java heap upper bound; eliminates one variable when benchmarking.
- With **ZGC**, when Xms = Xmx, the empty heap uncommit mechanism is disabled according to the documented semantics.

Trade-offs:

- The JVM may **commit** a lot of memory from startup even if the workload does not use it yet.
- If combined with `-XX:+AlwaysPreTouch`, it can **touch** a large heap region at startup and significantly increase startup latency/RSS.
- Does not return much heap memory to the OS in some collectors/modes.
- On a node running multiple services, overall memory pressure may worsen.
- A fixed-size **heap** does not make the entire JVM process memory fixed-size.

### Three Statements to Distinguish

1. **`Xms = Xmx`**: requests equal initial/maximum heap.
2. **`AlwaysPreTouch`**: requests the JVM to touch committed heap pages before allocating them to the Java application (if supported).
3. **`RSS equals Xmx`**: **cannot be inferred** from the two above alone without considering the OS, GC, memory mappings, and actual measurement.

Avoid the statement "Xms=Xmx will immediately occupy all 4 GB of physical RAM" as a law for every collector/OS. Replace it with actual observed `committed`, `used`, and RSS numbers.

## 9. G1, Parallel, Serial, ZGC: Same Flags but Different Behavior

`-Xms`/`-Xmx` set overall limits, **they do not choose the collector**. GC is chosen by JVM ergonomics or another option, such as `-XX:+UseG1GC` on HotSpot.

| Collector | Concerns when choosing heap |
| --- | --- |
| **Serial GC** | Single GC worker, STW; large heap/large live set can cause significant pauses depending on workload |
| **Parallel GC** | Throughput-oriented; heap size affects GC frequency, promotion, and pause/throughput trade-off |
| **G1 GC** | Partitions heap into regions; Xmx affects number/size of regions and space budgets; pause target is a goal, not a guaranteed deadline |
| **ZGC** | Concurrent low-pause collector; needs enough headroom for allocation rate to avoid stalls, has uncommit when Xms < Xmx |
| **Shenandoah (if build supports)** | Concurrent collection, needs conditions/space for concurrent work; flags and availability depend on release |

**There is no "optimal 2g Xmx for every GC"**. When switching GC, keep heap/CPU/workload constant to compare before changing 5 other parameters at the same time.

### G1 and Ergonomics

- G1 has region-based young/old generations; many operations depend on live set/allocations, not just Xmx.
- Heap region sizing and collector heuristics may change when maximum heap changes.
- A larger Xmx allows fewer GC cycles in some cases, but can also change heap layout/footprint.
- **`-XX:MaxGCPauseMillis` is a soft goal**, not a promise that pauses are always below the threshold.

### ZGC and `-Xms`

On HotSpot JDK 17 ZGC supported by platform, documentation describes a mechanism to **uncommit unused heap pages**, but it does not uncommit below Xms. If **Xms = Xmx**, uncommit is disabled under that configuration; if Xms is smaller, ZGC can return infrequently used memory after a delay.

Example:

```bash
java -XX:+UseZGC -Xms128m -Xmx1g MyApp
```

This is only an **illustrative command for HotSpot JDK/OS/architecture supporting ZGC**; some collectors/releases have different lower bounds or availability. The heap size in the example is **not a production recommendation**.

Other flags:

```text
-XX:+ZUncommit
-XX:-ZUncommit
-XX:ZUncommitDelay=300
-XX:SoftMaxHeapSize=512m
```

`SoftMaxHeapSize` is a **soft target** for ZGC in supported versions; it does not replace the hard max `-Xmx` and can be exceeded when the JVM needs memory to avoid stalls/OOM. **Do not assume** this meaning and these flags apply identically to Serial/Parallel/G1.

## 10. Container-Aware Heap Sizing and RAM Percentages

HotSpot JDK 17 commonly has container resource limit awareness via `UseContainerSupport`, but you must check the patch version, cgroup version, and actual runtime. If Xmx is not explicitly set, the VM may use memory ergonomics based on the amount of RAM the JVM detects.

Some HotSpot options:

| Flag | Meaning |
| --- | --- |
| `-XX:MaxRAMPercentage=...` | Uses a percentage of available RAM according to VM logic to calculate maximum heap if there is no explicit Xmx |
| `-XX:InitialRAMPercentage=...` | Calculates initial heap as a percentage of RAM when there is no explicit Xms |
| `-XX:MinRAMPercentage=...` | **Misleading name**: mainly participates in max-heap ergonomics on small RAM configurations, not simply "minimum heap percentage" |
| `-XX:+UseContainerSupport` | Allows the JVM to use container constraint information when supported |
| `-XX:ActiveProcessorCount=...` | Overrides the number of processors the VM considers active; affects other GC/JIT ergonomics besides heap |

Example in a suitable environment/container:

```bash
java -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 -jar app.jar
```

This does not mean the heap is guaranteed to be exactly 10%/60% down to the byte due to alignment and heuristics. The numbers **10%/60% are illustrative only**, not a universal optimal choice for every service.

### Explicit Flags Usually Take Precedence

When `-Xmx512m` is already used, do not expect `-XX:MaxRAMPercentage=60` to still pull Xmx up to 60% of RAM. On HotSpot, **explicit Xmx usually has precedence** over the default ergonomic percentage. Same for Xms versus initial percentage; check `PrintFlagsFinal` to verify the final values.

### Container Request vs. Container Limit

- Kubernetes **memory request** is for scheduling/corresponding guarantees, not necessarily the memory limit the JVM uses to calculate max.
- **Memory limit** is enforced by cgroup and can lead to OOMKilled if the process/cgroup exceeds it.
- If a container **has no memory limit**, the JVM may calculate based on the host/node or another policy; do not assume it will divide node RAM evenly among pods.
- Record container `requests`, `limits`, and JVM effective flags in reports.

**Practice:** measure the container's real memory usage and headroom instead of assuming "60% heap means 40% is enough for all native overhead".

## 11. Commands to Inspect the Real JVM and Effective Heap

### Identify the Runtime

```bash
java -version
java --version
```

Note the **JDK major/update/build, vendor, and VM implementation**. With OpenJ9 or Native Image, flags/diagnostics may differ; this article primarily discusses HotSpot.

### Print Flags on HotSpot

```bash
java -Xms128m -Xmx512m -XX:+PrintFlagsFinal -version
```

Look for names like `InitialHeapSize`, `MaxHeapSize`, `MinHeapSize`, and flags related to GC. Output includes many flags, usually in bytes. Look at **effective values** rather than just inferring from the command line.

Note that `MinHeapSize` is an internal/tuning value in HotSpot, **not to be mechanically equated** with all heap-shrinking conditions of every collector/JVM port.

### Check Container Support

```bash
java -XshowSettings:system -version
```

On HotSpot JDK 17 supporting this option, output can describe provider/container constraints, CPUs, and memory. Printing format/labels vary by build; if the VM does not support it, read the exact `java --help-extra` or the distribution's documentation.

## 12. Java 17+ Runnable: Observing Initial, Used, Committed, and Max

Create file **`HeapSizingDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.ArrayList;
import java.util.List;

public final class HeapSizingDemo {
    private static final int BLOCK_SIZE = 128 * 1024;

    public static void main(String[] args) {
        if (args.length != 0) {
            throw new IllegalArgumentException("No arguments expected");
        }

        MemoryUsage before = ManagementFactory
                .getMemoryMXBean()
                .getHeapMemoryUsage();

        List<byte[]> retained = new ArrayList<>();
        int checksum = 0;

        for (int i = 0; i < 64; i++) {
            byte[] block = new byte[BLOCK_SIZE];
            block[0] = (byte) i;
            retained.add(block);
            checksum += Byte.toUnsignedInt(block[0]);
        }

        MemoryUsage after = ManagementFactory
                .getMemoryMXBean()
                .getHeapMemoryUsage();

        System.out.println("arrays: " + retained.size());
        System.out.println("payload bytes: "
                + (retained.size() * BLOCK_SIZE));
        System.out.println("checksum: " + checksum);
        System.out.println("first: "
                + Byte.toUnsignedInt(retained.get(0)[0]));
        System.out.println("last: "
                + Byte.toUnsignedInt(retained.get(63)[0]));
        System.out.println("done");

        // These numbers INTENTIONALLY vary by collector/JVM/run.
        System.err.println("heap init (bytes): " + after.getInit());
        System.err.println("heap max (bytes): " + after.getMax());
        System.err.println("heap used before (bytes): "
                + before.getUsed());
        System.err.println("heap committed before (bytes): "
                + before.getCommitted());
        System.err.println("heap used after (bytes): "
                + after.getUsed());
        System.err.println("heap committed after (bytes): "
                + after.getCommitted());
    }
}
```

Compile with JDK 17+:

```bash
javac -encoding UTF-8 HeapSizingDemo.java
```

Run on HotSpot with **two separate configurations**:

```bash
java -Xms32m -Xmx128m HeapSizingDemo
java -Xms128m -Xmx128m HeapSizingDemo
```

**Functional standard output of both normal runs:**

```text
arrays: 64
payload bytes: 8388608
checksum: 2016
first: 0
last: 63
done
```

**Standard error has no fixed numeric values.** Example only to understand the format:

```text
heap init (bytes): [value from VM]
heap max (bytes): [value from VM]
heap used before (bytes): [runtime value]
heap committed before (bytes): [runtime value]
heap used after (bytes): [runtime value]
heap committed after (bytes): [runtime value]
```

This is **not literal stderr**: the bracketed strings are descriptions of the numbers actually printed by the API. Data depends on VM, collector, alignment, background GC, and collection timing.

### Deterministic Calculation Check

- Each array has `128 × 1024 = 131072` bytes.
- There are `64` arrays, totaling **8,388,608 bytes** of payload.
- The first byte of the `i`-th array is assigned `i` for `i=0..63`, without overflow; sum `0+1+...+63 = 63×64/2 = 2016`.
- First element is `0`, last element is `63`.
- `retained` is still used after the loop, so references are kept until the explicit reads.

**No need for `System.gc()`** to observe heap sizing. GC algorithms and background activity may cause `used after` not to increase by exactly 8,388,608 bytes compared to `used before`; there are also headers, metadata, other allocations, and GC events.

### What to Compare?

With `-Xms32m -Xmx128m`, expect *initial heap* to be smaller than the `-Xms128m -Xmx128m` configuration. **Do not expect stdout to change:** the same code/inputs must produce the same computation results. Read `heap init`, `heap committed`, and `heap max`, and then if you want to compare footprint, measure **RSS/container memory** from the OS outside the program.

Because the program is fast, do not conclude "configuration B has faster startup time" just by using a stopwatch twice. Measure multiple process launches and a defined startup marker.

## 13. Lab 2: Creating Controlled Heap Pressure

To see how maximum heap can become a limit, write **`HeapPressureDemo.java`**. This sample bounds the number of blocks, without needing to OOM the application to demonstrate heap pressure.

```java
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;

public final class HeapPressureDemo {
    public static void main(String[] args) {
        List<byte[]> blocks = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 32; i++) {
            byte[] data = new byte[256 * 1024];
            data[0] = (byte) (i + 1);
            blocks.add(data);
            checksum += Byte.toUnsignedInt(data[0]);
        }

        System.out.println("blocks: " + blocks.size());
        System.out.println("payload bytes: "
                + (blocks.size() * 256 * 1024));
        System.out.println("checksum: " + checksum);

        long max = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getMax();
        System.err.println("heap max bytes (dynamic): " + max);
    }
}
```

Commands:

```bash
javac -encoding UTF-8 HeapPressureDemo.java
java -Xms32m -Xmx64m HeapPressureDemo
java -Xms64m -Xmx128m HeapPressureDemo
```

**Functional standard output if the process completes normally:**

```text
blocks: 32
payload bytes: 8388608
checksum: 528
```

Explanation: `32 × 256 × 1024 = 8,388,608` bytes; first byte values from `1` to `32` sum to `32×33/2 = 528`. This is **retained payload**, not the total memory the JVM actually uses.

**Do not intentionally cause OOM on a shared machine**. If OOME testing is needed, use an isolated, resource-limited, monitored environment separated from production traffic. Do not create unbounded loops just to wait for a crash.

### Observe GC Instead of Guessing

With HotSpot:

```bash
java -Xms32m -Xmx64m -Xlog:gc*=info HeapPressureDemo
java -Xms64m -Xmx128m -Xlog:gc*=info HeapPressureDemo
```

GC logs have different formats/durations depending on collector/JDK/hardware; **there is no fixed expected log**. Because the demo is short and retention is only a few MiB, **you may not see any collection event**. That does not make the demo wrong.

## 14. Reading GC Logs to Understand Heap Sizing

On HotSpot JDK 17:

```bash
java -Xms128m -Xmx512m -Xlog:gc*=info:file=gc.log:uptime,level,tags -jar app.jar
```

Note that `app.jar` must be a real application with a main manifest. The log may contain information about heap before/after collection, collectors, regions, promotion, pauses, and concurrent phases.

### Table of Metrics to Observe

| Metric | What might an increase/decrease indicate? | What NOT to conclude |
| --- | --- | --- |
| **Heap used before GC** | Allocation pressure/amount of data before collection | Not automatically the live set |
| **Heap used after GC** | Still-retained data and heap structure after collection | A single event is not yet proof of a leak |
| **GC pause duration** | STW delay in that event | Not total request latency |
| **GC frequency** | Number of collections per time or per requests | Many young GCs are not always bad |
| **Allocation rate** | Bytes allocated per second | Not live heap growth |
| **Promotion/old occupancy** | Objects moving across generations, old region pressure | Not automatically a leak |
| **Committed heap trend** | JVM increasing/decreasing committed capacity | Not equal to RSS on every collector |
| **Full GC / evacuation failure** | Sign of memory pressure or collector-specific event | Not enough to blame small Xms while ignoring live-set |

You need to combine **timestamp + workload + app latency + CPU/container memory**. For example, reducing the number of GC events by increasing Xmx is not enough if p99 latency does not improve or memory footprint exceeds limits.

### Do Not Use Mean GC Pause Instead of p99

A few long pauses can worsen tail latency even if the mean is low. Report the **distribution** of request latency and GC pauses, grounded in time alignment between request spans and GC events.

## 15. Observing a Running Process with `jcmd` and JMX

On HotSpot, attach tools are supported:

```bash
jcmd -l
jcmd PID VM.flags
jcmd PID VM.command_line
jcmd PID GC.heap_info
jcmd PID VM.native_memory summary
```

`PID` is a placeholder for the actual process ID. `VM.native_memory summary` requires **Native Memory Tracking** to be enabled from startup to have useful data:

```bash
java -XX:NativeMemoryTracking=summary -Xms128m -Xmx512m -jar app.jar
```

**NMT note:** statistics cover internal HotSpot/JDK scope, not all memory the OS may account for; do not assume `NMT total = RSS`. Enabling NMT has overhead and usually cannot be fully activated retroactively if the JVM did not enable it from start.

### Why Is JMX Useful?

`MemoryMXBean.getHeapMemoryUsage()` allows the application/monitoring to track `init/used/committed/max` over time, rather than inferring from a launch command from hours ago. A heap can grow/shrink depending on collector and config; you need to look at the **trend** rather than just a snapshot.

### JVM Flags Have Multiple Sources

Flags can come from:

- Command line passed by wrapper/script.
- `JAVA_TOOL_OPTIONS` or `JDK_JAVA_OPTIONS`.
- Container entrypoint and orchestrator.
- Tooling such as build runners/app servers.
- JVM ergonomics when flags are not explicitly set.

Save the **effective JVM command line/flags** from the process; do not just look at deployment YAML and assume the VM definitely received the exact same flags.

## 16. `AlwaysPreTouch`: Shifting Some Cost to Startup

On supported HotSpot:

```bash
java -Xms512m -Xmx512m -XX:+AlwaysPreTouch -jar app.jar
```

`AlwaysPreTouch` tells the VM to touch heap pages at startup after commit. This can:

- Increase startup duration and initial RSS level.
- Reduce some page faults/touch work during serving time.
- Help detect memory allocation/commit problems at the startup stage.
- Put RAM pressure earlier on small containers or systems crowded with JVM processes.

**Does not guarantee** always reducing tail latency; if the workload is small and the JVM barely touches the heap, pre-touching many pages may just be wasted work. If pre-touch is enabled but Xms is very small, only the initial committed heap may be prepared according to config; do not assume all of Xmx has been touched.

### A Meaningful Test

Compare:

```bash
java -Xms512m -Xmx512m -XX:-AlwaysPreTouch -jar app.jar
java -Xms512m -Xmx512m -XX:+AlwaysPreTouch -jar app.jar
```

Change only **one flag**, measure **startup, RSS, CPU page faults, first-request latency, and steady-state**. Draw conclusions within the scope of the OS/collector/kernel in use.

## 17. Is `-Xms` Equal to Xmx Necessary for Low Latency?

Not every low-latency service needs a fixed heap. Consider:

- **Stable workload, sufficient memory:** fixed heap can reduce resize overhead and provide better predictability.
- **Periodic/mostly idle workload:** expandable/shrinkable heap can reduce footprint when idle, if supported by the collector.
- **Serverless/cold-start:** large initial heap + pre-touch can worsen startup.
- **Small container memory:** reserving too large a fixed heap can cause OOMKilled even when used Java objects are not high.
- **ZGC:** uncommit has commit/uncommit cost; latency needs to be weighed against the ability to return pages to the OS.
- **Batch jobs:** time from launch to final result differs from long-running server p99 goals.

**A usually sound strategy:** start with safe default/ergonomic sizing, measure allocation/live set/GC/latency, then optimize with controlled comparisons. Do not copy a "Xms=Xmx is always best" rule from a benchmark with a different workload.

## 18. How to Choose Xmx Based on Live Set and Budget

### Step 1 — Measure Live Set

Observe **used after representative collections** across different load phases, heap histograms/heap dumps when needed, object retention, and allocation rate.

A snapshot right after startup is not representative of peak traffic; after a full/business cycle it can be very different.

### Step 2 — Measure Allocation Bursts

A service may have a 200 MiB live set but create 300 MiB of short-lived buffers during a peak window. Do not set `Xmx=220m` just because "live objects are about 200 MiB". The collector needs space for allocations and collection/evacuation operations.

### Step 3 — Leave Headroom for GC

Different collectors need space for copying, old-gen pressure, concurrent allocations, and marking/relocation. There is no single formula `Xmx = live × 1.2` that works for all G1/ZGC/Parallel workloads.

### Step 4 — Account for Native Memory

Threads, metaspace, code cache, direct buffers, and JNI can take up significant memory. Set Xmx lower than the container limit, accounting for peak native usage and cgroup overhead.

### Step 5 — Test a Few Configurations and Compare

A/B example:

```text
A: -Xms128m -Xmx512m
B: -Xms256m -Xmx512m
C: -Xms512m -Xmx512m
D: -Xms128m -Xmx768m

Each run keeps JDK, collector, workload, CPU/cgroup limits
equivalent, and reports actual metrics.
```

The numbers are **test scenarios**, not universal recommendations. Compare A/B/C to isolate the effect of **Xms**, compare A/D to isolate the effect of **Xmx**. Avoid changing both collector and Xms/Xmx and then guessing which caused the speedup.

## 19. Common Errors and How to Diagnose Them

### 19.1. `OutOfMemoryError: Java heap space`

Usually means the Java heap can no longer satisfy an allocation after necessary measures. Checklist:

- Is effective Xmx as expected?
- Are heap live set and retained paths growing?
- Are there unbounded caches, queues, collections, or large arrays?
- Is there an allocation burst incompatible with the limit?
- Do GC logs show promotion/evacuation pressure or Full GC?
- Is changing heap really a sustainable fix?

Do not increase Xmx indefinitely to hide a leak. Heap dumps may contain secrets, requiring proper permissions/safe handling.

### 19.2. `OutOfMemoryError: GC overhead limit exceeded`

Can appear in applicable collectors/configs when the JVM spends too much time in GC while reclaiming too little heap. The message is not a universal definition for every GC; you must read the logs and the collector in use. Simply increasing Xmx may mask symptoms if retention is not fixed.

### 19.3. Container `OOMKilled` / exit 137

The process may be terminated by the OS/cgroup before the JVM **has a chance** to throw `Java heap space`. Signs:

- Pod `Last State: OOMKilled`.
- Container memory peak near limit.
- JVM heap used has not reached Xmx.
- High RSS/native memory, or cgroup metrics include page cache.

**You must investigate the process/container memory budget**, not just the Java heap. Exit code 137 can also be caused by SIGKILL for other reasons; use pod events/OS logs to verify OOM rather than inferring from 137 alone.

### 19.4. `OutOfMemoryError: Metaspace`

Metaspace is non-heap. Larger Xmx will not solve it automatically; it may reduce headroom for metaspace. Inspect class loading/class loaders, maximum metaspace if configured, and retention.

### 19.5. `OutOfMemoryError: Direct buffer memory`

Direct buffers typically use memory outside the Java heap (native backing), even though the wrapper object remains on the heap. Inspect `MaxDirectMemorySize`/NIO usage and lifecycle. Changing Xmx may affect ergonomic default/direct buffer budget in some HotSpot releases, but does not replace analyzing native allocations.

### 19.6. `unable to create native thread`

May have exhausted process/thread resources, address space/stack memory, OS limits, or cgroup PID limits. Increasing Xmx may leave even less memory for native threads. Reduce leaked threads/thread pool size or adjust resources based on evidence.

### 19.7. "Heap committed is high but used is low"

Do not automatically conclude a memory leak. Committed capacity may be retained for future allocations or due to Xms/fixed heap policy. Compare **after-GC used trend**, retained objects, and actual native/OS footprint.

### 19.8. "Increased Xmx but the application is still slow"

Xmx does not cure:

- Lock contention.
- Database/network I/O.
- CPU throttling.
- Memory leak.
- Over-allocation causing GC CPU even with plenty of heap.
- Slow startup class loading/JIT when heap is not the bottleneck.

Use JFR, request tracing, profilers, and appropriate metrics to distinguish.

## 20. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "`-Xms` is the amount of objects already used." | Xms sets initial heap, not current used |
| "`-Xmx` is the maximum RAM of the JVM process." | Xmx is Java heap maximum; there is still non-heap/native |
| "Setting Xmx 2 GiB means the JVM uses 2 GiB right at startup." | It may only reserve/commit a portion depending on settings |
| "`-Xms=Xmx` definitely makes RSS equal to Xmx immediately." | Must consider commit/touch/OS/GC mapping |
| "Heap used, committed, RSS are all the same." | Different metrics and accounting scopes |
| "If heap is large enough, it cannot be OOMKilled." | Native/cgroup memory can still exceed the limit |
| "The larger Xmx is, the shorter pauses always are." | GC frequency/pauses/CPU trade-off depends on the collector |
| "The smaller Xmx is, the lower CPU always is." | GC pressure can increase |
| "Same Xmx means same GC behavior." | GC, Xms, live set, CPU, and VM ergonomics still differ |
| "Small Xms always has good startup." | Allocation/heap expansions can cause overhead |
| "Large Xms is always good for throughput." | Footprint/startup/memory contention can worsen |
| "`AlwaysPreTouch` always reduces latency." | May only increase startup and RSS if unnecessary |
| "Volatile/heap size are directly related." | Memory synchronization/JMM differs from heap capacity |
| "`MaxRAMPercentage` still overrides explicit Xmx." | Explicit heap sizing usually has precedence in HotSpot |
| "`MinRAMPercentage` is the initial/minimum heap %." | It participates in maximum ergonomic sizing for low memory |
| "Kubernetes request is the cgroup memory limit." | Requests are for scheduling; limits are the enforced cap |
| "`-Xmx` can be passed after `-jar`." | After `-jar` are application arguments |
| "`System.gc()` is a reliable way to measure Xms/Xmx." | GC scheduling does not reflect true heap sizing and has overhead |
| "OOMKilled 137 is definitely a heap OOME." | Could be native/cgroup/signal; verify events |
| "Used increasing continuously for a while is definitely a memory leak." | GC may not have run yet or live workload legitimately increased |
| "Heap dumps do not need security." | May contain secrets/PII/session state |
| "A single startup measurement can pick optimal Xms." | Requires multiple runs, equivalent workload/GC/CPU |
| "One standard Xmx/container ratio for all applications." | Native footprint and workload vary greatly |

## 21. Self-Check Exercises with Answers

**Exercise 1.** Does `-Xms256m -Xmx1g` mean the application pre-creates 256 MiB of business objects?  
**Answer:** No. Xms controls initial heap sizing, while used objects depend on execution.

**Exercise 2.** Does `-Xmx1g` limit the total process RSS?  
**Answer:** No. Metaspace, code cache, thread stacks, direct buffers, and native memory lie outside the heap.

**Exercise 3.** Is committed heap being larger than used heap abnormal?  
**Answer:** No. Committed capacity can hold free space for subsequent allocations.

**Exercise 4.** Why not set Xmx equal to the container limit?  
**Answer:** Because the process also has non-heap/native/OS-accounted memory, risking cgroup OOM.

**Exercise 5.** Is `-Xms2g -Xmx1g` valid?  
**Answer:** No on HotSpot; initial must not exceed max heap.

**Exercise 6.** Does `-Xms1g -Xmx1g` guarantee 1 GiB of OS RSS right at startup?  
**Answer:** No. Commit, touch, and OS mapping differ; it must be measured.

**Exercise 7.** Which phase does `-XX:+AlwaysPreTouch` primarily affect?  
**Answer:** Touches committed heap pages at startup, increasing upfront cost and potentially reducing page-fault work when used later.

**Exercise 8.** If Xmx is increased, will a memory leak go away?  
**Answer:** No. If there is unbounded retention, the leak still exists, usually just delaying OOM.

**Exercise 9.** What can increasing Xms while keeping Xmx constant improve?  
**Answer:** Reduces the need for heap expansion/initial pressure in some workloads, at the cost of footprint/startup cost.

**Exercise 10.** Can decreasing Xmx increase GC frequency?  
**Answer:** Yes; the degree depends on live set, allocations, collector, and heuristics.

**Exercise 11.** Does `MaxRAMPercentage` apply when an explicit `-Xmx` has been passed on HotSpot?  
**Answer:** Usually it no longer determines Xmx; the explicit max heap option takes precedence.

**Exercise 12.** Is `MinRAMPercentage` the minimum percentage of initial heap?  
**Answer:** No. It relates to maximum heap ergonomics on small-RAM systems.

**Exercise 13.** Does `java -jar app.jar -Xmx512m` actually configure the heap?  
**Answer:** Usually no; that is an application argument due to its position after `-jar`.

**Exercise 14.** In `HeapSizingDemo`, how many bytes are the payload arrays in total?  
**Answer:** **8,388,608 bytes**, because 64 × 128 KiB.

**Exercise 15.** What is the checksum of `HeapSizingDemo`?  
**Answer:** **2016**, the sum of 0..63.

**Exercise 16.** Do two different Xms configurations change the logical stdout of the demo?  
**Answer:** No when running successfully; timing and runtime heap metrics may differ.

**Exercise 17.** How many arrays and what checksum does `HeapPressureDemo` retain?  
**Answer:** **32 arrays**, checksum **528**.

**Exercise 18.** Can ZGC on JDK 17 return unused heap pages to the OS?  
**Answer:** Yes on supported builds, per `ZUncommit`; it does not uncommit below Xms.

**Exercise 19.** With ZGC, how does Xms=Xmx affect uncommit?  
**Answer:** Disables the ability to return unused heap to the OS under ZGC's uncommit mechanism.

**Exercise 20.** Is `SoftMaxHeapSize` a hard limit?  
**Answer:** No. A soft target can be exceeded when needed, whereas Xmx is the hard maximum heap.

**Exercise 21.** A pod was OOMKilled, but heap used had not reached Xmx. What should you inspect?  
**Answer:** RSS/cgroup memory, native/metaspace/direct/threads, GC/native allocations, pod/OS events.

**Exercise 22.** Does G1 guarantee keeping every pause below `MaxGCPauseMillis`?  
**Answer:** No. It is an ergonomic target, not a hard deadline.

**Exercise 23.** Does a measurement of heap used increasing over 5 minutes prove a leak?  
**Answer:** No; you need live-set/retained-path trends across collections and equivalent workloads.

**Exercise 24.** If startup is the primary KPI, what disadvantage can fixed large Xms + AlwaysPreTouch cause?  
**Answer:** Increases startup work/memory commitment and early RSS, especially when workload is light.

**Exercise 25.** You want to change Xmx from 512m to 768m; keep Xms or change both?  
**Answer:** To isolate Xmx impact, first keep Xms, collector, workload, and CPU/memory budget similar; check container headroom then A/B test.

## 22. Responsible Heap Tuning Checklist

- [ ] Correctly identify HotSpot/JVM implementation, vendor, JDK version/build.
- [ ] Know **actually effective** Xms, Xmx (not just in YAML).
- [ ] Distinguish initial, used, committed, max, virtual reserve, RSS, and cgroup usage.
- [ ] Checked container memory **limits** and CPU quotas?
- [ ] Accounted for non-heap: metaspace, code cache, direct buffers, thread stacks, JNI, GC metadata?
- [ ] Have a baseline live set across multiple workload phases, especially peak traffic?
- [ ] Measured allocation rate and headroom for bursts/collector?
- [ ] Know which GC is in use (Serial/Parallel/G1/ZGC/...)?
- [ ] Have logs of GC events/pauses, heap occupancy before/after GC?
- [ ] Evaluated p99 latency, throughput, and error rates?
- [ ] Tested changing Xms **separately** from Xmx to isolate impact?
- [ ] Tested changing Xmx **separately** from GC choice?
- [ ] Tested startup with/without AlwaysPreTouch when KPI requires it?
- [ ] If fixed heap, checked idle memory/host density?
- [ ] If Xmx is large near the memory limit, tested native headroom and peak cgroup memory?
- [ ] If OOMKilled, checked Kubernetes events/cgroup/OS logs?
- [ ] If heap OOME, checked retained-path evidence and application object lifecycles?
- [ ] Have a security/retention policy when dumping heap/collecting diagnostic artifacts?
- [ ] Have multiple A/B runs with the same inputs/JDK/container constraints?
- [ ] Have rollback criteria for sizing changes if p99 or memory worsens?

## 23. Summary and Decision Rules

```text
- Xms = initial heap sizing
- Xmx = maximum Java heap sizing
- used ≠ committed ≠ reserved ≠ RSS ≠ cgroup usage

Setting Xms low:
  may lighten footprint/startup
  but the VM may resize/commit more when load increases

Setting Xms high or Xms=Xmx:
  may reduce resizing/churn
  but keeps a larger footprint, especially with pre-touch

Setting Xmx too low:
  frequent GC / allocation stalls / heap OOME

Setting Xmx too high near RAM/container cap:
  insufficient native headroom / OOMKilled / memory contention

Goal:
  enough heap for live data + allocation bursts + GC
  and enough native/container headroom for the process
```

**There is no best heap size in every case.** A good value is determined by workload, GC, startup/latency SLOs, native footprint, and OS/container resource management capabilities. Start from a grounded setting, measure properly named quantities, change **one variable at a time**, and only keep changes when the benefit is strong enough without worsening OOM/latency risk.

### References

1. **Oracle JDK 17 — `java` command, `-Xms` / `-Xmx` / `AlwaysPreTouch` / RAM percentages:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
2. **Oracle JDK 17 — Garbage Collection Tuning Guide:** https://docs.oracle.com/en/java/javase/17/gctuning/
3. **Oracle JDK 17 — Z Garbage Collector, heap sizing and uncommit:** https://docs.oracle.com/en/java/javase/17/gctuning/z-garbage-collector1.html
4. **Java SE 17 — `MemoryUsage` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html
5. **Java SE 17 — `MemoryMXBean` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
6. **Oracle JDK 17 — `jcmd` diagnostic command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
7. **Oracle JDK 17 — Native Memory Tracking:** https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html
8. **Inside Java — How ZGC allocates memory for Java heap (2025):** https://inside.java/2025/04/17/zgc-deep-dive/
9. **Inside Java — ZGC `SoftMaxHeapSize`:** https://inside.java/2020/07/02/zgc-softmaxheapsize/
10. **Red Hat — Java 17 container awareness and RAM percentage flags:** https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness
11. **AWS — JVM memory/CPU/container recommendations (2026):** https://aws.amazon.com/blogs/containers/jvm-memory-cpu-and-classpath-best-practices-for-java-containers-on-aws/

**Core takeaway:** `-Xms` determines the starting point of the heap, `-Xmx` determines the hard ceiling of the Java heap; they tune the balance of **resizing/GC/startup/footprint**, but do not replace measuring **used vs committed vs RSS** and reserving memory for the entire JVM process.