# 3.7 Comparing CPU, Memory, and Resource Limits Seen by the JVM with the Deployment Environment

## Learning Objectives

When a Java service runs smoothly on a developer machine yet slows down, runs out of memory, or exits unexpectedly inside a container, the first question is not necessarily “which line of code is buggy?”. You need to determine **which resources the deployment environment allows the process to use**, **which limits the OS/container is actually enforcing**, and **how the JVM detected, configured, and used those resources**.

After this lesson, you will be able to:

- Distinguish **host/node**, **pod/container**, **process**, and **JVM** resources; avoid confusing requests/limits with resources guaranteed to the JVM.
- Explain CPU quotas, CPU affinity/cpuset, processor count seen by the JVM, CPU throttling, and effects on GC, thread pools, or throughput.
- Distinguish **container memory limit** from **maximum Java heap**, committed/used heap, native memory, thread stacks, direct buffers, metaspace, and page cache.
- Read and compare information from **deployment specs**, **cgroups**, **JVM runtime/flags**, and **metrics over the same time window**.
- Analyze scenarios involving CPU throttling, Java `OutOfMemoryError`, kernel OOM kills, and PID/file descriptor limits without jumping to premature root-cause conclusions.
- Write an evidence-backed diagnostic report stating data sources, timestamps, configuration discrepancies, and inference limits.

## 1. Four Resource Views to Cross-Check

In Java deployments, “the machine has 16 CPUs and 64 GiB RAM” **does not** guarantee the JVM is allowed to use all of that. A container can be capped at 1.5 CPUs and 1 GiB RAM; the JVM may see a different processor count than physical CPUs, while heap is set smaller than the memory limit.

| Observation layer | What exists at this layer? | Where can it be read? | What you must not infer |
| --- | --- | --- | --- |
| **Host/node** | Logical CPUs, RAM, kernel, machine resource pressure, other workloads on the same node | OS/node metrics, host info | All CPU/RAM on the node belongs to the container |
| **Orchestrator/deployment** | CPU/memory **requests and limits**, replica count, image, config, and operational policies | Kubernetes Pod/Deployment spec, Docker/VM config | “Request = limit” or “declared spec = actual limit at all times” |
| **Container/process** | cgroup CPU quota, cpuset, memory limit/current, PID limit, file descriptors, process RSS, CPU usage/throttling | `/sys/fs/cgroup`, `/proc`, container/runtime metrics | cgroup memory usage equals Java heap; CPU quota equals dedicated cores |
| **JVM** | `availableProcessors()`, max/committed/used heap, GC threads, JVM flags, native allocations, thread count | Java APIs, `java -XshowSettings`, `jcmd`, JFR, GC logs | Whatever the JVM sees equals what the system is actively consuming |

The right reasoning path looks like this:

```text
Host/node capacity
    |
    v
Deployment: CPU/memory requests & limits, replicas, placement
    |
    v
Kernel/container: cgroup, cpuset, affinity, PID/FD constraints
    |
    v
JVM: resource detection + startup flags + memory allocation
    |
    v
Actual process usage, GC/threads, latency, errors, OOM/throttling
```

**Note:** this is a conceptual model. Limits may be inherited from a parent cgroup; multiple containers in the same pod have separate limits; in a VM environment without Kubernetes, the orchestration layer may correspond to hypervisor or systemd configuration. During investigations, always record **the exact container hosting the Java process** and **the same observation timestamp**.

## 2. CPU: Execution Time Limits Differ from Processor Count

### 2.1 Physical CPUs, Logical CPUs, Quotas, and cpuset

Frequently confused quantities:

- **Host logical CPUs:** number of logical processors visible to the OS on the host. This is total node capacity, not necessarily dedicated to the container.
- **CPU request** in Kubernetes: CPU amount used for scheduling/relative guarantees under contention; e.g. `500m` corresponds to requesting 0.5 CPU. A request by itself is not a hard ceiling on CPU time.
- **CPU limit:** CPU time allowed for consumption under a quota mechanism when a limit is set; for example, `1500m` means an average equivalent of 1.5 CPUs per enforcement period, **not** 1.5 exclusive physical cores.
- **CPU quota/period** (Linux cgroups): CPU time budget per period. In cgroup v2, `cpu.max` typically takes the form `quota period` in microseconds, or `max period` if no quota is set at that level.
- **cpuset/affinity:** set of logical CPUs on which the process/threads are permitted to run. It can be narrower than host resources and combine with quotas.
- **`Runtime.availableProcessors()`:** **integer** processor count reported by the JVM to the program; this value is affected by container detection, affinity, JDK version, flags, and sometimes updates when the environment changes.

Suppose Linux cgroup v2 has:

```text
cpu.max = 150000 100000
```

Converting the average limit:

```text
150000 microseconds CPU / 100000 microseconds period
= 1.5 CPU-equivalents
```

This means the container can run across multiple logical CPUs (subject to affinity/cpuset), yet total consumed CPU time is enforced by quota. Once the budget within a period runs out, threads can be **throttled** until the next period. Because `availableProcessors()` only returns an integer and also depends on detection policies, **you must not assume** it will necessarily return `1` or `2` simply from dividing 1.5.

The case:

```text
cpu.max = max 100000
```

only indicates **no quota limit is set by `cpu.max` itself on that cgroup**. It does not rule out limits from a parent cgroup, affinity/cpuset, CPU shares/weight, or competing load on the node.

### 2.2 What Behavior Does the JVM's CPU View Affect?

The processor count detected by the JVM can be used by the runtime and libraries to choose default parallelism, such as sizing or strategies for certain thread pools and GC/JIT thread counts. However:

- The number of created threads **does not equal** allocated CPUs.
- A 64-worker pool on a low-quota container can increase contention, context switching, or queueing; yet if most workers are waiting on I/O, you cannot conclude 64 workers is automatically excessive.
- CPU throttling can raise wall-clock latency even when an algorithm consumes the same amount of CPU time.
- With `-XX:ActiveProcessorCount=N`, the JVM can use that override for the processor count it reports and related heuristics. This flag **does not increase** the real CPU quota enforced by the kernel.
- CPU utilization reported by the JVM, container, node, and monitoring platform may use **different denominators** (one core, whole node, quota, request...), so “100% CPU” must always be paired with its metric definition.

In common JDK 17 HotSpot builds on Linux, container support is typically enabled by default, though how cgroup v1/v2 and quota/cpuset are parsed can vary by JDK/vendor/patch or flags. Confirm **the running JDK build** and what **the process itself detected**; do not infer solely from another version's documentation.

### 2.3 Signs of CPU Throttling

In cgroup v2, `cpu.stat` can contain counters like `nr_periods`, `nr_throttled`, and `throttled_usec` (plus other kernel-dependent fields). You must observe **counter deltas over the same window** as latency/throughput rather than reading a cumulative counter once and drawing conclusions.

Example: while offered load remains steady, `nr_throttled` climbs sharply, completed throughput plateaus, and backlog plus p99 rise. That **supports the hypothesis** that quota throttling is creating a bottleneck. Cross-check CPU usage, runnable threads, downstream waits, GC, and onset time; a non-zero throttling counter alone does not prove root cause.

## 3. Memory: Container Memory Limit Is Not Java Heap Size

### 3.1 Memory Breakdown of a JVM Process

In Java, `-Xmx` or `Runtime.maxMemory()` mainly refers to **the maximum limit of the Java heap**. The process has many other memory consumers:

| Component | Role and examples | Why it matters |
| --- | --- | --- |
| **Java heap** | Objects and arrays managed by GC | Bounded by `-Xmx` or automatic heap sizing; can cause `OutOfMemoryError: Java heap space` |
| **Metaspace** | Class and classloader metadata | Can grow when loading many classes; resides outside the heap limit |
| **Thread stacks** | Stacks of platform threads, call frames | Many platform threads can exert native memory pressure; size depends on OS/JVM/flags |
| **Code cache/JIT** | JIT-compiled machine code and related metadata | Consumes resources outside the Java heap |
| **Direct/off-heap buffers** | `ByteBuffer.allocateDirect`, certain networking/storage libraries | Not counted in heap used, yet still consumes real memory |
| **GC/JVM native structures** | GC metadata, bookkeeping, compiler/runtime allocations | A small heap does not mean small total process memory |
| **Native/JNI/library allocations** | Native libraries, OS allocators | May not be fully reflected by heap or NMT metrics |
| **Memory-mapped files & page cache** | Mapped pages, filesystem cache accounted by the kernel | Can contribute to cgroup memory accounting; distinct from heap objects |

Suppose a container has a **1 GiB** memory limit and the JVM is configured with `-Xmx768m`. The **256 MiB** difference is not “guaranteed free memory”: metaspace, stacks, direct buffers, JIT, native libraries, page cache, and helper processes also need RAM. Under a given workload, kernel-accounted cgroup memory can hit the limit **even before heap approaches `-Xmx`**.

Conversely, `heap used` rising before a GC does not by itself prove a leak: GC may reclaim most objects. Track post-GC trends, allocation rates, retained references, and load context.

### 3.2 Three Easily Confused Concepts on `Runtime`

Java provides:

```java
Runtime rt = Runtime.getRuntime();
int processors = rt.availableProcessors();
long heapMaxBytes = rt.maxMemory();
long heapCommittedBytes = rt.totalMemory();
long freeWithinCommittedBytes = rt.freeMemory();
long approximateUsedHeapBytes = heapCommittedBytes - freeWithinCommittedBytes;
```

Explanation:

- `availableProcessors()`: processor count exposed by the JVM to the program, not current CPU usage.
- `maxMemory()`: maximum heap ceiling the JVM attempts to use; **not** total container RAM or RSS.
- `totalMemory()`: amount of heap currently allocated/committed by the JVM for its use; not total node memory.
- `freeMemory()`: free space **within the committed heap**, not free OS/container RAM.
- `totalMemory() - freeMemory()`: approximate used heap at read time; values can change concurrently with GC and allocation.

Meanwhile, in Linux cgroup v2:

- `memory.max`: hard memory limit on that cgroup, or `max` if unlimited at that level.
- `memory.current`: memory currently accounted by the kernel to the cgroup, which can include multiple memory types/page cache; **does not equal** Java heap used.
- `memory.high`: cgroup-level pressure/reclaim threshold when configured, distinct from the hard cap `memory.max`.
- `memory.events`: counters such as `high`, `max`, `oom`, `oom_kill`; inspect deltas over time windows and cgroup scope.

Metrics such as `RSS`, container memory working set, `memory.current`, heap committed, and heap used **do not share the same definition**. Before adding or subtracting them, verify which pages each metric counts, its scope (process/container/pod), and whether cache is included.

### 3.3 JVM `OutOfMemoryError` Differs from Kernel OOM Kill

| Symptom | Initial interpretation | Evidence to cross-check |
| --- | --- | --- |
| `java.lang.OutOfMemoryError: Java heap space` | JVM could not satisfy a heap allocation under current constraints | Heap usage, GC logs, `-Xmx`, allocations/retained objects, stack trace |
| `OutOfMemoryError: Metaspace` | Unable to satisfy class metadata in metaspace | Class loading/classloaders, metaspace metrics, flags, native memory |
| `OutOfMemoryError: unable to create native thread` | Could not create a new platform thread; may involve native memory, PID/thread limits, or OS resources | Thread count, stack size, `pids.max/current`, process limits, memory |
| Container `OOMKilled` | Kernel/cgroup killed a process when hitting memory limits; process can vanish abruptly | Pod/container termination reason, exit status, `memory.events`, memory.current/peak metrics, container logs |
| Exit code `137` | Usually indicates process received `SIGKILL` (128 + 9) | Verify who sent `SIGKILL`; **do not** use exit code 137 alone to assert OOM |

A kernel kill may give the JVM no chance to print `OutOfMemoryError` or write a heap dump. Conversely, an `OutOfMemoryError` thrown by the JVM does not necessarily trigger a kernel kill. This distinction is critical when classifying root cause and selecting how to gather evidence.

### 3.4 Automatic Heap Sizing and Flags

In a container-aware JVM, when `-Xmx` is **not** specified, the JVM may use heuristics such as `-XX:MaxRAMPercentage` to choose a heap limit based on detected memory. Percentages, caps, and rounding can depend on JDK/vendor/workload. When `-Xmx` is explicitly configured, inspect the process's **effective flags** rather than assuming default ratios.

Startup example:

```bash
java -Xmx768m -jar app.jar
```

This targets a heap ceiling around 768 MiB; it **does not** place a 768 MiB hard limit on the entire process. If the container only has 1 GiB, you must leave headroom for non-heap/native memory and other OS-accounted consumers. How much headroom is needed depends on thread count, direct buffers, GC/JIT, libraries, memory-mapped files, sidecar/cgroup boundaries, and load characteristics—**there is no single ratio valid for every service**.

## 4. Kubernetes: Requests/Limits vs. Runtime Reality

Suppose a Java container has the following resource spec:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1500m"
    memory: "1Gi"
```

Typical interpretation on Kubernetes/Linux:

- **CPU request 500m:** input for the scheduler to place the workload and share resources under contention. Not “the JVM only sees 0.5 CPU”.
- **CPU limit 1500m:** typically enforced as an average quota of 1.5 CPU-equivalents; when CPU demand exceeds budget, the container can be throttled. Concurrent logical CPUs allowed also depend on cpuset/affinity.
- **Memory request 512Mi:** scheduling input and part of resource management decisions; not a hard memory cap.
- **Memory limit 1Gi:** memory constraint on the container; exceeding it can trigger an OOM kill. The memory limit cannot be compared directly against Java heap used.
- **Other containers in the same pod:** sidecars have their own requests/limits. When checking Java's resources, identify the exact container name and inherited/effective limits; never confuse whole-pod memory with an individual JVM.

Deployment specs declare **intent**; active cgroups reveal **runtime enforcement**; JVM APIs and effective flags show **how the JVM perceived those limits**; metrics show **how the app consumed resources over the observation window**.

A change in autoscaling, sidecars, JDK patch, node placement, or cgroup policy can alter behavior even when application code and `-Xmx` remain unchanged.

## 5. Collecting Evidence from the Right Java Process

The commands below are **Linux/cgroup v2 and JDK 17+ examples**, meant to be run in the right environment/container with read permissions. On Windows, macOS, cgroup v1, or other container runtimes, system files/commands differ. On minimal images, a container may lack a shell, `cat`, `ps`, or `jcmd`; collect via corresponding runtime tools or an authorized diagnostic environment.

### 5.1 Step 1 — Confirm Deployment and Configured Limits

On Kubernetes, first inspect configuration and live state of **the exact container**:

```bash
kubectl -n "$NAMESPACE" get pod "$POD" -o yaml
kubectl -n "$NAMESPACE" describe pod "$POD"
kubectl -n "$NAMESPACE" top pod "$POD" --containers
```

Here `NAMESPACE` and `POD` are shell variables set for the investigated workload. `top` depends on Metrics Server; its output follows the observability system's semantics and **does not** replace reading cgroups/JVM. From the pod description, check **requests/limits, image, container name, restart count, termination reason, node**, and timestamps. Often you also need to inspect the Deployment/ReplicaSet and rollout revisions to confirm which deployment version the running process belongs to.

Do not deduce resources solely from Git manifests: a live pod might carry a spec from another rollout, or cluster policies may inject defaults/limits or mutate specs before pod creation.

### 5.2 Step 2 — Read Active Kernel Limits

Inside **the exact Linux container using cgroup v2**, useful files include:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/pids.max
cat /sys/fs/cgroup/pids.current
```

Save **raw output** and timestamps, especially `cpu.stat` and `memory.events` at two or more timestamps to compute counter deltas.

Depending on the system, `/sys/fs/cgroup` may not follow this cgroup v2 layout. Read `/proc/self/cgroup` and mount info to identify the active controller/hierarchy. Under **cgroup v1**, CPU quota usually appears in `cpu.cfs_quota_us`/`cpu.cfs_period_us`, and memory limit in `memory.limit_in_bytes`; mount paths can differ and very large numbers may represent “unlimited”. Never conclude “the container has no limit” just because a v2 path does not exist.

If the container is constrained by a **parent cgroup** or OS-level affinity, a single file in the current directory may not reveal all effective constraints. Check mount scope and hierarchy accordingly.

### 5.3 Step 3 — Read What the JVM Sees

At startup, JDK 17+ typically supports:

```bash
java -version
java -XshowSettings:system -version
java -XshowSettings:vm -version
java -XX:+PrintFlagsFinal -version
```

Note: this is the output of **a new JVM** launched by the command, which can differ from the application process due to flags, container context, classpath, and environment. Use it to inspect **environment defaults**; to verify the running app, collect **effective arguments and JVM flags from the exact PID**. On platforms without system container metrics support, `-XshowSettings:system` may omit container details.

When `jcmd` is present in the JDK and can attach to the target Java process:

```bash
jcmd -l
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" GC.heap_info
```

`PID` must be the actual Java process (in a container it may be PID 1, though not always). Attach depends on user permissions, process namespace, JVM flags, and presence of JDK tools. `jcmd -l` does not necessarily see JVMs outside the current namespace.

When investigating native memory and **Native Memory Tracking (NMT) was enabled at JVM startup**, you can run:

```bash
jcmd "$PID" VM.native_memory summary
```

Example enabling NMT in **a run prepared for diagnostics**:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

NMT has overhead and does not cover every allocation from third-party native libraries. If not enabled at startup, `VM.native_memory summary` may simply report that NMT is disabled. Do not interpret “low NMT” as “RSS/container memory is definitely low”.

When investigating GC/CPU/container detection, you can plan GC logs or JFR with appropriate settings. Some Linux JDK/HotSpot builds support startup logging such as:

```bash
java -Xlog:os+container=debug -jar app.jar
```

This launches **a new process with extra instrumentation**; it does not attach to an already running JVM. Exact detail level and supported tags must be verified on the actual JDK/vendor used.

### 5.4 Step 4 — Compare at the Same Time and Scope

At minimum, fill out a table like this:

| Attribute | Deployment | cgroup/OS | JVM | Findings to clarify |
| --- | --- | --- | --- | --- |
| CPU | Request 500m; limit 1500m | `cpu.max=150000 100000`; cpuset and throttling delta | `availableProcessors()`, `ActiveProcessorCount`, GC/thread config | Does the JVM reflect effective CPU per version/flags? Is throttling occurring during slowdowns? |
| Memory | Request 512Mi; limit 1Gi | `memory.max=1073741824`, `memory.current`, `memory.events` | `-Xmx`, max/used heap, metaspace, native/direct, stacks | Do off-heap memory and cgroup accounting explain memory pressure/kills? |
| PID/threads | Runtime limits if any | `pids.max/current`, process limits | Thread count, thread dumps | Are thread creation failures linked to PID or native memory limits? |
| Process file descriptors | OS/container limits | `/proc/<pid>/limits`, FD usage | Sockets/files, errors | Is the `nofile` limit hit or are descriptors leaking? |

**This is an illustrative table**, not output from a real cluster. Only mark “matches”, “mismatches”, or “insufficient data” after verifying measurement scope and timestamps.

## 6. Runnable Java 17+ Example: Separating Quota Math from Live JVM Observation

To avoid machine-dependent instability, the example has two modes:

1. `fixture`: computes from **hypothetical cgroup v2 strings**, printing **completely deterministic** output to verify conversion logic.
2. No arguments: prints **live JVM values** and raw cgroup files if readable; output varies by OS, JDK, container, and startup flags.

Create the file `JvmResourceViewDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class JvmResourceViewDemo {
    private static final long MIB = 1024L * 1024L;

    static String cpuLimit(String raw) {
        String[] fields = raw.trim().split("\\s+");
        if (fields.length != 2) {
            throw new IllegalArgumentException("cpu.max requires two fields");
        }
        if (fields[0].equals("max")) {
            return "unlimited by cpu.max";
        }
        long quota = Long.parseLong(fields[0]);
        long period = Long.parseLong(fields[1]);
        if (quota <= 0 || period <= 0) {
            throw new IllegalArgumentException("invalid cpu.max values");
        }
        return String.format(Locale.ROOT, "%.2f CPU-equivalents",
                (double) quota / period);
    }

    static String memoryLimit(String raw) {
        String value = raw.trim();
        if (value.equals("max")) {
            return "unlimited by memory.max";
        }
        long bytes = Long.parseLong(value);
        if (bytes <= 0) {
            throw new IllegalArgumentException("invalid memory.max value");
        }
        return (bytes / MIB) + " MiB";
    }

    static String readIfPossible(String filename) {
        try {
            return Files.readString(Path.of(filename)).trim();
        } catch (IOException | SecurityException e) {
            return "not available";
        }
    }

    public static void main(String[] args) {
        if (args.length == 1 && args[0].equals("fixture")) {
            System.out.println("cpu.max 150000 100000 -> "
                    + cpuLimit("150000 100000"));
            System.out.println("cpu.max max 100000 -> "
                    + cpuLimit("max 100000"));
            System.out.println("memory.max 1073741824 -> "
                    + memoryLimit("1073741824"));
            System.out.println("memory.max max -> "
                    + memoryLimit("max"));
            return;
        }
        if (args.length != 0) {
            throw new IllegalArgumentException("use no args or fixture");
        }

        Runtime runtime = Runtime.getRuntime();
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("availableProcessors="
                + runtime.availableProcessors());
        System.out.println("heap.max.MiB=" + runtime.maxMemory() / MIB);
        System.out.println("heap.committed.MiB=" + runtime.totalMemory() / MIB);
        System.out.println("heap.used.approx.MiB="
                + (runtime.totalMemory() - runtime.freeMemory()) / MIB);
        System.out.println("cgroup.v2.cpu.max="
                + readIfPossible("/sys/fs/cgroup/cpu.max"));
        System.out.println("cgroup.v2.memory.max="
                + readIfPossible("/sys/fs/cgroup/memory.max"));
    }
}
```

Compile with JDK 17 or newer:

```bash
javac JvmResourceViewDemo.java
java JvmResourceViewDemo fixture
```

**Exact** stdout in `fixture` mode:

```text
cpu.max 150000 100000 -> 1.50 CPU-equivalents
cpu.max max 100000 -> unlimited by cpu.max
memory.max 1073741824 -> 1024 MiB
memory.max max -> unlimited by memory.max
```

Now run:

```bash
java JvmResourceViewDemo
```

This mode prints `pid`, `availableProcessors`, approximate heap max/committed/used, and raw contents of **the two cgroup v2 paths** if present. **There is no fixed stdout** for this mode since every value depends on environment/execution conditions; `not available` only means Java could not read that path, not that no limit exists.

To observe the effect of heap configuration in a **new** JVM:

```bash
java -Xmx256m JvmResourceViewDemo
```

Here `heap.max.MiB` will usually be close to the requested heap value per VM rules, though do not assume it equals **exactly** 256 across all JDKs. Likewise, `availableProcessors` can differ across hosts/containers/JDKs.

**What this demo code does not do:** it does not auto-detect cgroup v1, traverse full hierarchies/cpuset, calculate RSS/native usage, fetch Kubernetes specs, verify whether the JVM exhausted its quota, or measure performance. It is an **initial cross-check tool**, to be combined with metrics/cgroups/JVM flags and the exact PID in real investigations.

## 7. Real-World Scenario Analysis: When Numbers Diverge, What Do You Ask?

### 7.1 “The Node Has 16 CPUs, Yet the JVM Reports Only 2”

This is not necessarily a bug. Check:

1. Container CPU limit, quota/period; process cpuset and CPU affinity.
2. `-XX:ActiveProcessorCount` and `-XX:+UseContainerSupport`/detection-related flags.
3. Exact JDK/vendor/patch, PID namespace/cgroup.
4. CPU throttling and whether the workload is under sufficient load.

If the deployment limit corresponds to 1.5 CPUs, `availableProcessors=2` **can** be consistent with how the JVM reports an integer; do not draw exact conclusions from two numbers alone. If the JVM reports 16 while the workload is throttled under a 1.5 quota, check overrides/container detection; thread/GC heuristics may diverge from expectations.

**Action:** compare effective limits, runtime detection, and symptoms before altering flags or pool sizes. Changing `ActiveProcessorCount` only alters how many processors the JVM sees—it does not make the kernel raise the CPU budget.

### 7.2 “Heap Wasn't Full, Yet the Pod Still Got OOMKilled”

Illustrative example: container memory limit 1 GiB, `-Xmx768m`, measured heap used 600 MiB; then the container gets killed. Causes can include metaspace, direct buffers, thread stacks, GC/JIT native structures, mmap/page cache, or a memory spike between sampling intervals.

Verification steps:

- Inspect termination reason `OOMKilled`, exit status, and timestamp of **that specific container**; check memory events/usage on the right cgroup.
- Check peak/working-set/RSS along with sampling scope and frequency; never compute free RAM from `heap.max - heap.used`.
- Collect heap, metaspace, direct buffers, thread counts, and native info; NMT helps if enabled at startup and its scope is understood.
- Check changes in payload, concurrency, thread pools, caches, direct memory, or sidecars/helper processes.
- Evaluate headroom and intervene based on mechanism; raising `-Xmx` while keeping the container cap fixed can make things **worse** by shrinking native headroom.

You do not need a `java.lang.OutOfMemoryError` in logs to confirm a kernel OOM kill. Conversely, do not treat every exit 137 as proof of OOM without termination reason/cgroup evidence.

### 7.3 “JVM CPU Usage Is Low, Yet Latency Keeps Rising”

Process CPU can be low because most threads are waiting on DB/network/locks. Or CPU is being throttled, the CPU% metric uses a different denominator, or the sampling window is too coarse.

Investigate by aligning **client latency, throughput, in-flight/queue depth, process/container CPU usage, cpu.stat deltas, thread dumps/JFR, and downstream timings** over the same time window. CPU usage being below 100% of the node does not prove the container still has CPU budget.

### 7.4 “Unable to Create Threads Even Though Heap Has Free Space”

`unable to create native thread` can occur when PID/thread limits, native memory, or process limits are hit. Check:

- Number of live platform threads and growth over time.
- `pids.max`, `pids.current`; `ulimit`, `/proc/<pid>/limits`.
- Thread stack size and memory accounting; thread pools/concurrency settings.
- Whether there is a thread leak or long-blocking tasks.

Do not reflexively increase `-Xmx`: a larger heap can further shrink headroom for native allocations. With virtual threads (if used on a supporting JDK), distinguish virtual thread count from platform/carrier thread count; do not assume 1:1 native stack cost per virtual thread.

### 7.5 “Same Java Image, Yet One Cluster Processes Faster Than Another”

Possible differences include node/CPU architecture, JDK vendor/patch build, CPU request/limit and cpuset, memory limits, GC flags, autoscaling, dependency latency, payload/data distribution, noisy neighbors, kernel/cgroup version, and observability configuration. Record **both declared and measured effective configurations** in both environments. An identical image does not prove identical runtime conditions.

## 8. Repeatable Diagnostic Workflow

### Step 1 — Scope the Symptom and Exact Process

Record service, instance/pod, container, PID, image digest, JDK vendor/patch, JVM startup flags, timestamp with timezone, and anomaly type: timeouts, p99 spike, OOM kill, JVM `OutOfMemoryError`, thread creation failure, or slow CPU-bound workload.

### Step 2 — Confirm the Effective Deployment Spec

Read CPU/memory requests/limits of the right container, replica count, node placement, and restart/exit reason. Compare the live pod's spec rather than just old config files.

### Step 3 — Collect cgroup and OS Constraints

Read `cpu.max`, cpuset, `cpu.stat`, `memory.max/current/events`, `pids.max/current` (or cgroup v1/OS equivalents). Check inherited limits, affinity, and whether the container sees the right paths. Save raw values.

### Step 4 — Collect JVM Effective Settings and Metrics

Capture `availableProcessors()`, `-Xmx`/effective max heap, heap committed/used, GC/thread/native allocations, and JVM arguments. When needed, use GC logs/JFR/NMT/stack traces. Collect from **the exact JVM/PID** with timestamps.

### Step 5 — Align Metrics to the Same Boundary and Window

Compare **per-process**, **per-container**, **per-pod**, and **per-node** from matching sources; e.g., container memory differs from heap. Measure CPU throttling and memory event deltas over the window when p95/p99 or errors changed. Place workload (RPS/concurrency/mix/payload) next to resource metrics.

### Step 6 — Formulate and Test Hypotheses

Example:

```text
Hypothesis:
Low CPU limit causes throttling during peak, driving up p99.

Required evidence:
- offered/received/completed load measured;
- actual cpu.max = suspected quota;
- cpu.stat nr_throttled/throttled_usec increase in the same window as p99;
- no other dependency/queue/GC explains the whole phenomenon.

Controlled test:
- keep workload and data equivalent;
- change only quota in a test environment when appropriate;
- re-measure p99, throughput, throttling, and CPU cost.

Limitations:
- one p99 drop does not prove causality in every environment.
```

Similarly, a native-memory OOM hypothesis requires matching memory accounting, heap/native data, and events; a thread leak hypothesis requires evidence of growing/unreleased thread counts and PID limits. Never assert causality solely because two metrics rise together.

### Step 7 — Conclude and Hand Off

Distinguish conclusions that are **confirmed**, **supported but needing verification**, and **insufficient data**. Document scope, resource budgets, risks, remediations, verification criteria, and post-change monitoring.

## 9. Comparison Report Template

```text
ISSUE
- Symptom, impact, timestamp, and timezone:
- Service, image digest, container, pod/node, PID:
- Java vendor/version/patch and command line:
- Workload: offered/received/completed RPS, concurrency, data:

DEPLOYMENT (exact container)
- CPU request / limit:
- Memory request / limit:
- Pod/container restarts, termination reason:
- Config, replica count, node placement:

KERNEL / OS
- cgroup version, scope/path, ancestor constraints:
- cpu.max, cpuset/affinity:
- cpu.stat counters/deltas in the same window:
- memory.max/current/events, RSS/working-set:
- pids.max/current and process limits if relevant:

JVM
- availableProcessors, ActiveProcessorCount/UseContainerSupport:
- Heap max/committed/used, -Xms/-Xmx/MaxRAMPercentage:
- Metaspace/direct/native/thread and GC evidence:
- JFR/GC/thread dumps/metrics (IDs and timestamps):

ANALYSIS
- Match/mismatch across deployment, cgroup, JVM:
- Hypothesis, mechanism, supporting/refuting evidence:
- Test results under equivalent workload:
- Measurement scope differences and uncontrolled factors:

CONCLUSION
- Confirmed / supported / insufficient data:
- Applicability scope and limitations:
- Proposed actions, owner, verification criteria:
```

In a formal report, replace placeholders with **real measurements and timestamps**, never turning illustrative numbers into system data. A good comparison table makes it immediately clear why “the node still has RAM” can coexist with a container OOM, or why `availableProcessors()` does not equal host CPU count.

## 10. Common Mistakes

1. **Treating `freeMemory()` as remaining container RAM.** It is free space within the committed heap; inspect cgroup/OS memory separately.
2. **Comparing `-Xmx` directly against the memory limit and assuming safety.** Native/off-heap, stacks, metaspace, JIT, page cache, and other overhead still apply.
3. **Reading host CPUs and assuming the JVM can use all of them.** Quotas, cpuset, affinity, container support, and overrides can restrict it.
4. **Assuming CPU request is a hard cap.** Requests mainly guide scheduling/sharing; CPU limits typically become enforced quotas.
5. **Treating `availableProcessors()` as currently used CPUs.** It is the processor count reported by the JVM, not usage or dedicated physical cores.
6. **Seeing `cpu.max=max` and concluding unlimited CPU.** Cpuset, parent cgroups, affinity, or competing load may still constrain execution.
7. **Reading `nr_throttled` or `oom_kill` once and inferring a new incident.** Those are cumulative counters; you need deltas and the right time window.
8. **Confusing `OOMKilled` with `OutOfMemoryError`.** One comes from the kernel/cgroup, the other is a Java exception/error; evidence-gathering methods differ.
9. **Using `java -XshowSettings` on a new JVM to judge a running app.** Different startup flags/PID/namespace can produce different results.
10. **Attributing all cgroup memory usage to the heap.** Cgroup accounting differs in scope and definition from heap used or NMT.
11. **Ignoring cgroup version and parent hierarchy.** Paths/controllers or inherited limits can differ; a missing v2 file does not mean unlimited.
12. **Raising `ActiveProcessorCount` or heap to “unlock” kernel resources.** JVM flags do not grant more CPU quota or container memory limit.
13. **Measuring layers at different times.** A GC cycle, traffic burst, or restart can skew numbers dramatically; keep timestamps and run IDs aligned.
14. **Locking in root cause from a single correlation.** CPU throttling, GC pauses, DB waits, and latency can rise together; verify mechanisms and competing hypotheses.
15. **Changing multiple settings at once.** You cannot tell which change drove an improvement without controlled isolation.

## 11. Knowledge Self-Check

1. A node has 32 logical CPUs, and a container sets a 1500m CPU limit. Why can `Runtime.availableProcessors()` be less than 32 without indicating a JVM bug?
2. Given `cpu.max=150000 100000`, explain 1.5 CPU-equivalents and why it is **not** equivalent to 1.5 dedicated cores.
3. Java has `-Xmx768m` and a container memory limit of 1Gi. The pod gets `OOMKilled` when the latest measured heap used was only 500MiB. List at least five other memory consumers to check.
4. What do `Runtime.totalMemory()` and `Runtime.freeMemory()` measure? Can you use them to calculate available memory on the node?
5. `cpu.max` shows `max 100000`. Which limits could still prevent Java from using all host CPUs?
6. A thread pool cannot create new threads even though the GC heap has free space. How would you cross-check `pids.max/current`, native memory, and thread counts?
7. Why can the exact same application image and JDK major version yield different `availableProcessors`, max heap, or throughput across two clusters?
8. A monitoring dashboard reports “100% CPU”, the JVM reports 4 processors, and cgroups grant 2 CPU-equivalents. Which denominators and flags must you verify before concluding?
9. `java -XshowSettings:vm -version` run inside a container gives max heap A, while the running app uses max heap B. Why can the two differ?
10. What in a report is sufficient to distinguish “confirmed cgroup OOM kill” from “suspected memory pressure” or “Java threw OutOfMemoryError”?

**Key takeaway:** When diagnosing Java, always compare **declared resources → kernel-enforced limits → JVM-detected/configured resources → actual usage under the same workload and time window**. CPU quota differs from processor count, Java heap differs from total container memory, and evidence from one layer cannot automatically substitute for another layer.