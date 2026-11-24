# 6.7 OperatingSystemMXBean: CPU load, CPU time, and environment memory

A Java service may report soaring latency while heap still has plenty of room, a pod may experience CPU throttling even when %CPU looks modest, or a JVM may get OOMKilled while `MemoryMXBean` shows heap never reached `-Xmx`. To distinguish these phenomena, you must observe **the resources of the execution environment and the entire JVM process**, not just Java objects on the heap.

`OperatingSystemMXBean` supplies basic info such as available CPUs and load average; on JDK 17, the `com.sun.management.OperatingSystemMXBean` extension provides **CPU load, process CPU time, RAM/swap, and virtual memory**. However, the data depends on the operating system, JDK implementation, container/cgroup, and sampling instant. A value of `0.75` does not say the whole system is "75% busy because of Java"; a value of `-1` usually means **unsupported or no sample yet**, not negative CPU load.

**Lesson objectives:** obtain the right bean, read the right units/scopes, compute CPU utilization from two CPU time samples, distinguish load average from CPU%, separate environment memory from Java heap and RSS, verify container limits, and combine metrics into evidence for JVM incidents.

## 1. Two interfaces with the same name but different scopes

Java 17 has two related interfaces:

1. **Standard API:** `java.lang.management.OperatingSystemMXBean`, in the `java.management` module. It provides `getName()`, `getArch()`, `getVersion()`, `getAvailableProcessors()`, `getSystemLoadAverage()`, and `getObjectName()`.
2. **JDK extension:** `com.sun.management.OperatingSystemMXBean`, in the `jdk.management` module, extending the standard interface and adding CPU/physical memory/swap/virtual memory metrics. This is a JDK-specific API, not guaranteed on every Java implementation or minimal runtime image.

Obtain the standard interface from the **current** JVM:

```java
java.lang.management.OperatingSystemMXBean standard =
        java.lang.management.ManagementFactory
                .getOperatingSystemMXBean();
```

When extended metrics are needed, check the implementation rather than casting blindly:

```java
if (standard instanceof com.sun.management.OperatingSystemMXBean extended) {
    // Can read getCpuLoad(), getProcessCpuTime(), getTotalMemorySize(), ...
} else {
    // This JVM/runtime does not provide the expected extension.
}
```

The two snippets above illustrate code inside a method, not a complete program. On a standard HotSpot/OpenJDK 17 build, the returned object typically implements the extended interface; however, code may run on another runtime or a custom `jlink` image, so a fallback is essential.

### 1.1. ObjectName when reading via JMX

In the platform MBeanServer, the operating-system bean has the standard name:

```text
java.lang:type=OperatingSystem
```

`standard.getObjectName()` returns this `ObjectName`. Remote access via JMX requires a connection to the **right JVM** and appropriate permissions; the bean's metadata reflects the environment seen by that JVM, not automatically the entire cluster.

### 1.2. Question → measurement method map

| Question | Method/source | Scope and limitations |
| --- | --- | --- |
| How many CPUs does the JVM see? | `getAvailableProcessors()` | Processors available to the JVM, not necessarily physical host cores |
| Does the machine/environment have a large run queue? | `getSystemLoadAverage()` | Roughly one-minute load average; not %CPU |
| How much CPU is the environment using recently? | Extended `getCpuLoad()` | Ratio in `[0,1]` of the operating environment; may return negative |
| How much CPU is the Java process itself using recently? | Extended `getProcessCpuLoad()` | Ratio in `[0,1]`, including application threads and internal JVM threads |
| What is the JVM's cumulative CPU time? | Extended `getProcessCpuTime()` | **CPU nanoseconds**, not wall elapsed time or UTC timestamp |
| How much total/free memory does the environment report? | Extended `getTotalMemorySize()` / `getFreeMemorySize()` | **Bytes**, may be container-aware depending on JDK/platform |
| How much total/free swap? | Extended `getTotalSwapSpaceSize()` / `getFreeSwapSpaceSize()` | **Bytes**, policy and support depend on OS/cgroup |
| Committed virtual memory of the process? | Extended `getCommittedVirtualMemorySize()` | **Bytes**, not RSS/heap; may return `-1` |
| Actual Java heap used? | `MemoryMXBean`, `MemoryPoolMXBean` | **Not** the primary job of OperatingSystemMXBean |
| Was the container CPU-throttled or OOMKilled? | Cgroup/Kubernetes/OS metrics, runtime events | Cannot confirm root cause from OperatingSystemMXBean alone |

## 2. Standard interface: OS identity, available processors, and load average

### 2.1. OS name, architecture, and version

- `getName()` matches the `os.name` system property.
- `getArch()` matches `os.arch`.
- `getVersion()` matches `os.version`.

Strings vary across Linux, Windows, macOS, VM/container builds, JDK vendors, or virtualization environments. `os.arch` describes the architecture reported by the JVM, and does not replace verifying native library ABI/CPU architecture when encountering `UnsatisfiedLinkError`.

Do not use `getName()` to guess how much RAM an OS has, or `getVersion()` to infer the Linux kernel inside a container without cross-checking process/host metadata.

### 2.2. `getAvailableProcessors()` and what "available" means

`getAvailableProcessors()` returns an `int`, **at least 1**, equivalent to `Runtime.getRuntime().availableProcessors()`. It represents the number of processors the JVM can use **from the JVM's perspective**, not an absolute count of physical cores on the machine. The value can change while the JVM is running.

Factors that can affect it:

- OS CPU affinity/cpuset and resources assigned to the process;
- container CPU quotas and cgroups, plus the JDK's container-detection capability;
- the `-XX:ActiveProcessorCount` flag on HotSpot;
- differences across JDK versions and effective CPU count algorithms.

For example, a node has 32 logical CPUs while a container is capped at 2 CPUs; JDK 17 recognizing the cgroup properly can report `getAvailableProcessors() == 2`. Another runtime or `-XX:-UseContainerSupport` might cause the JVM to report the host count. **Do not assume** fractional CPU limits (like `500m`) are always represented accurately as an integer by this API: `getAvailableProcessors()` is inherently an `int`.

This value is useful for evaluating default parallelism, thread pools, and GC behavior, yet does not directly represent **CPU usage** or reveal CPU throttling.

### 2.3. `getSystemLoadAverage()` is not CPU %

`getSystemLoadAverage()` returns a `double` describing the **system load average over roughly the last minute** per the OS calculation: the average number of runnable/waiting entities. If unavailable on the platform, the method returns a **negative number**.

Example on a machine with 4 logical CPUs:

- Load average `0.5`: relatively few runnable entities on average.
- Load average `4.0`: roughly equal to available CPUs under a simplified model.
- Load average `8.0`: many entities may be waiting for CPU, though this does not prove CPU% is always 100%.

Load average is **not bounded to `[0,1]`**, has no % unit, and OS formulas can include different states. On Linux, load average is also influenced by tasks in uninterruptible sleep (often I/O-related); thus high load does not automatically prove CPU is the bottleneck.

If `getSystemLoadAverage() == -1` or another negative number, record "unavailable"; **do not convert it to 0**. Inside a container, verify whether load average reflects the host or another scope per your JDK/OS; never divide load average by pod CPU count to claim an exact CPU ratio.

### 2.4. Java 17+ sample program using standard APIs

Save the file **`StandardOsProbe.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;

public class StandardOsProbe {
    public static void main(String[] args) {
        OperatingSystemMXBean os =
                ManagementFactory.getOperatingSystemMXBean();

        double average = os.getSystemLoadAverage();

        System.out.println("objectName=" + os.getObjectName());
        System.out.println("osName=" + os.getName());
        System.out.println("osArch=" + os.getArch());
        System.out.println("osVersion=" + os.getVersion());
        System.out.println("availableProcessors="
                + os.getAvailableProcessors());
        System.out.println("loadAverageAvailable=" + (average >= 0));
    }
}
```

Compile/run:

```bash
javac StandardOsProbe.java
java StandardOsProbe
```

**Output depends on OS/JDK/container**; illustrative example (not fixed stdout):

```text
objectName=java.lang:type=OperatingSystem
osName=Linux
osArch=amd64
osVersion=6.x
availableProcessors=2
loadAverageAvailable=true
```

The string `osVersion=6.x` is merely an illustrative placeholder, not a literal version expected to appear. On another environment `loadAverageAvailable=false` is valid. When feeding data into a metrics system, keep the floating-point value, unit, timestamp, and instance label—do not log only a boolean.

## 3. The `com.sun.management.OperatingSystemMXBean` extension in JDK 17

In JDK 17, the extension in `jdk.management` provides these method groups:

| Group | Method | Unit | Special values |
| --- | --- | --- | --- |
| Recent CPU | `getCpuLoad()` | Fraction in `[0,1]` | Negative when unavailable |
| Recent JVM CPU | `getProcessCpuLoad()` | Fraction in `[0,1]` | Negative when unavailable |
| JVM CPU time | `getProcessCpuTime()` | Nanoseconds | `-1` when unsupported |
| Total/free memory | `getTotalMemorySize()` / `getFreeMemorySize()` | Bytes | Check scope and validity |
| Total/free swap | `getTotalSwapSpaceSize()` / `getFreeSwapSpaceSize()` | Bytes | Swap may not exist |
| Committed virtual memory | `getCommittedVirtualMemorySize()` | Bytes | `-1` when unsupported |

`getSystemCpuLoad()`, `getTotalPhysicalMemorySize()`, and `getFreePhysicalMemorySize()` are older names, **deprecated since Java 14**. On Java 17, prefer `getCpuLoad()`, `getTotalMemorySize()`, and `getFreeMemorySize()` respectively. The older names are not a reason to rewrite working code upon upgrading JDK, yet new code should use the current names.

**Notably:** `getCpuLoad()` refers to the **operating environment**, which may be the host, a virtualized environment, or container-managed depending on the implementation. Do not call it "process CPU" — the process has its own `getProcessCpuLoad()` method.

### 3.1. Checking support capability

With `ManagementFactory.getOperatingSystemMXBean()`, use `instanceof` as follows:

```java
java.lang.management.OperatingSystemMXBean standard =
        java.lang.management.ManagementFactory
                .getOperatingSystemMXBean();

if (standard instanceof com.sun.management.OperatingSystemMXBean os) {
    double processLoad = os.getProcessCpuLoad();
    if (processLoad >= 0.0) {
        // Convert to percentage: processLoad * 100.0.
    } else {
        // Recent CPU load is currently unavailable.
    }
}
```

This is a snippet placed inside a method. **Do not** cast `(com.sun.management.OperatingSystemMXBean) standard` unconditionally in a library intended to support multiple JVMs/vendors. `com.sun.management` is available on common JDKs, yet is not part of the standard interface contract.

### 3.2. `getCpuLoad()`: recent CPU usage of the environment

`getCpuLoad()` returns a ratio in `[0.0, 1.0]` for *recent* CPU usage in the operating environment. Per the contract:

- `0.0` indicates all CPUs were idle during the observed interval;
- `1.0` indicates all CPUs were active for the entire observed interval;
- values between 0 and 1 represent intermediate utilization;
- **a negative value** = recent CPU usage is not yet available or unsupported, not "negative CPU".

For example, `0.82` can be displayed as `82%` **operating-environment CPU usage**. It does not imply all 82% came from the Java process, nor does it necessarily match the host monitoring system's scope: cgroups and how the implementation reads CPU counters can differ.

"Recent" does not automatically mean a **1-minute window** like load average. Window size, sample update cadence, and smoothing depend on the implementation. When read immediately after startup, negative or unstable values can appear; preserve the sentinel instead of forcing it to 0%.

### 3.3. `getProcessCpuLoad()`: recent CPU share used by the JVM

`getProcessCpuLoad()` also returns `[0,1]` or a negative value when unavailable. It focuses on the **JVM process**, including:

- Java application threads;
- JVM internal/GC/JIT/runtime threads;
- native operations executing inside the process.

For instance, `getCpuLoad() = 0.90` and `getProcessCpuLoad() = 0.10` may suggest the environment is busy while the Java process uses only a small slice. To conclude "CPU is consumed by other processes", cross-check OS/container process metrics and verify both measurements share the same timestamp and scope. If the JVM is the only process in a container yet the two numbers differ, that can result from sampling windows, CPU quotas, throttling, or implementation details—do not infer hidden processes.

Never add `getProcessCpuLoad()` and `getCpuLoad()` together, because the process is normally already included in total environment CPU. Never subtract them to compute exact "other processes" load without understanding the samples and denominators.

### 3.4. Table distinguishing easily confused metrics

| Metric | Unit | Window/type | Can exceed 1? | Purpose |
| --- | --- | --- | --- | --- |
| `getSystemLoadAverage()` | Average runnable entities | ~1 minute, OS-specific | **Yes** | Indicator of run queue / pressure |
| `getCpuLoad()` | Environment CPU fraction | Recent, implementation-specific | No when valid | Evaluate CPU busyness of the operating environment |
| `getProcessCpuLoad()` | JVM process CPU fraction | Recent, implementation-specific | No when valid | Evaluate CPU share used by the JVM |
| `getProcessCpuTime()` | Cumulative CPU nanoseconds | Since process start | **Yes, grows continuously** | Compute average CPU cores across two samples |

Thus "load = 4.2" can be a valid load average, yet **is not** 420% CPU load. If a dashboard mixes two metrics under one `cpu_load` label without declaring source/unit, bottleneck conclusions will be wrong.

## 4. `getProcessCpuTime()`: CPU time clock, not wall time

### 4.1. What is cumulative CPU time?

`getProcessCpuTime()` returns total **CPU time of the JVM process** in nanoseconds; returns `-1` if unsupported on the platform. Java 17 documentation notes the value has **nanosecond precision, though not necessarily nanosecond accuracy**.

CPU time differs from:

- **Wall elapsed time**: real time elapsed between two points (`System.nanoTime()` or a suitable clock).
- **Uptime**: time since the JVM/process started.
- **CPU load**: activity ratio over an observation window.
- **Unix timestamp**: absolute UTC instant; CPU time cannot be turned into a timestamp by adding it to an epoch.

If four CPU cores concurrently execute four JVM threads for 1 wall-clock second, the process can accumulate roughly **4 CPU-seconds** (4 billion CPU nanoseconds), even though wall elapsed time was only 1 second. Hence CPU time can advance faster than wall time; that is not a bug.

### 4.2. Taking **two samples** to compute core-equivalent utilization

Let:

- `cpu0`, `cpu1`: two readings of `getProcessCpuTime()`, in **ns**;
- `wall0`, `wall1`: two readings of `System.nanoTime()`, in **ns**;
- `N`: effective CPU count used as denominator, explicitly defined for the measurement goal.

When `cpu0/cpu1 >= 0`, from the same JVM lifetime, and `wall1 > wall0`:

```text
deltaCpuNs  = cpu1 - cpu0
deltaWallNs = wall1 - wall0

averageCpuCores = deltaCpuNs / deltaWallNs
normalizedCpuFraction = averageCpuCores / N
normalizedCpuPercent = 100 * normalizedCpuFraction
```

**Hypothetical example:** over 2 seconds of wall time, the process consumes 2 additional seconds of CPU time. It used **1 core-equivalent** on average. Taking `N=4`, normalized utilization is **25%**; if the effective limit allows only 2 cores, the same work is **50%** under that denominator.

This is an **estimate**, not `getProcessCpuLoad()` guaranteed to use this exact formula on every JDK. `getProcessCpuLoad()` has an implementation-defined window and normalization. When cross-checking, align core count definitions, cgroup quotas/CPU throttling, interval, and time origin.

### 4.3. Practical measurement caveats

- Space the two samples far enough apart for counters to accumulate meaningful data (a few seconds as a rough guide, depending on load/resolution); do not spam every few microseconds.
- Do not compute if any CPU time is `< 0` or goes backward; that can indicate unavailable, sampling failure, or accidentally stitching across processes.
- Do not use `System.currentTimeMillis()` as an elapsed clock when clock steps/slewing must be avoided; `System.nanoTime()` fits differences within the same JVM.
- `getAvailableProcessors()` can change at runtime. If CPU count/cgroup quota changes between two samples, flag **configuration changed** instead of blindly dividing by the final value.
- Reading CPU time and wall time is not truly simultaneous, introducing error. For very short latency/CPU targets, use JFR/profilers or suitable OS counters.
- Do not clamp computed results into `[0,1]` before inspecting; unusually high values may reveal a wrong denominator, wrong unit, or unsynchronized snapshots.

### 4.4. Java 17+ program with exact stdout to verify the math

Save the file **`CpuTimeMathDemo.java`**:

```java
import java.util.Locale;

public class CpuTimeMathDemo {
    public static void main(String[] args) {
        long startWallNs = 1_000_000_000L;
        long endWallNs = 3_000_000_000L;
        long startCpuNs = 4_000_000_000L;
        long endCpuNs = 6_000_000_000L;
        int effectiveCpus = 4;

        long elapsedNs = endWallNs - startWallNs;
        long cpuUsedNs = endCpuNs - startCpuNs;

        double averageCores = (double) cpuUsedNs / elapsedNs;
        double normalizedPercent =
                100.0 * averageCores / effectiveCpus;

        System.out.println("wall_ms=" + elapsedNs / 1_000_000);
        System.out.println("cpu_ms=" + cpuUsedNs / 1_000_000);
        System.out.printf(Locale.ROOT, "average_cores=%.2f%n",
                averageCores);
        System.out.printf(Locale.ROOT, "cpu_percent_of_4=%.2f%%%n",
                normalizedPercent);
    }
}
```

Compile/run with Java 17+:

```bash
javac CpuTimeMathDemo.java
java CpuTimeMathDemo
```

**Exact stdout:**

```text
wall_ms=2000
cpu_ms=2000
average_cores=1.00
cpu_percent_of_4=25.00%
```

The program uses fixed numbers to verify the arithmetic, **not measuring the machine's real CPU**. Changing `effectiveCpus = 2` while keeping the counters yields `50.00%`. When applying this to production metrics, document where your CPU count comes from and as of when.

## 5. Reading real CPU with a standalone Java 17+ program

The next example reads the standard interface, then the extension (when present), and avoids printing negative CPU values as negative percentages.

Save the file **`OsMetricsSnapshot.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;
import java.util.Locale;

public class OsMetricsSnapshot {
    private static String percent(double fraction) {
        if (!Double.isFinite(fraction) || fraction < 0.0) {
            return "unavailable";
        }
        return String.format(Locale.ROOT, "%.1f%%",
                fraction * 100.0);
    }

    private static String bytes(long value) {
        return value < 0 ? "unavailable" : value + " bytes";
    }

    public static void main(String[] args) {
        OperatingSystemMXBean standard =
                ManagementFactory.getOperatingSystemMXBean();

        System.out.println("mxbean=" + standard.getObjectName());
        System.out.println("os=" + standard.getName());
        System.out.println("availableProcessors="
                + standard.getAvailableProcessors());

        double loadAverage = standard.getSystemLoadAverage();
        System.out.println("loadAverage1m="
                + (loadAverage < 0 ? "unavailable" : loadAverage));

        if (standard instanceof com.sun.management.OperatingSystemMXBean os) {
            System.out.println("environmentCpu="
                    + percent(os.getCpuLoad()));
            System.out.println("processCpu="
                    + percent(os.getProcessCpuLoad()));
            System.out.println("processCpuTimeNs="
                    + (os.getProcessCpuTime() < 0
                            ? "unavailable" : os.getProcessCpuTime()));
            System.out.println("totalMemory="
                    + bytes(os.getTotalMemorySize()));
            System.out.println("freeMemory="
                    + bytes(os.getFreeMemorySize()));
            System.out.println("totalSwap="
                    + bytes(os.getTotalSwapSpaceSize()));
            System.out.println("freeSwap="
                    + bytes(os.getFreeSwapSpaceSize()));
            System.out.println("committedVirtualMemory="
                    + bytes(os.getCommittedVirtualMemorySize()));
        } else {
            System.out.println("jdkExtension=unavailable");
        }
    }
}
```

Compile/run on a JDK 17 with the `jdk.management` module:

```bash
javac --add-modules jdk.management OsMetricsSnapshot.java
java --add-modules jdk.management OsMetricsSnapshot
```

**Output is live data, not fixed**. Example of the format on a JDK with the extension:

```text
mxbean=java.lang:type=OperatingSystem
os=Linux
availableProcessors=2
loadAverage1m=1.75
environmentCpu=62.0%
processCpu=48.0%
processCpuTimeNs=3456000000
totalMemory=2147483648 bytes
freeMemory=1342177280 bytes
totalSwap=0 bytes
freeSwap=0 bytes
committedVirtualMemory=1073741824 bytes
```

These are strictly **hypothetical numbers** illustrating format; do not expect them as exact output on any machine. An initial run may print `environmentCpu=unavailable`, `processCpu=unavailable`, or values shifting between lines due to differing read timestamps.

**Demo limitation:** `getProcessCpuTime()` is called twice in the ternary expression, so the printed value may be read at a different instant than the check; it remains a valid observation if supported. In serious monitoring systems, read **each counter once into a local variable** per snapshot and attach a timestamp. The program is kept simple to illustrate the API, without pretending the metrics are captured atomically.

### 5.1. One valid sample is still not a trend

`getCpuLoad()` and `getProcessCpuLoad()` report "recent usage"; process CPU time is a **cumulative counter**; free RAM is a **gauge**. To analyze change:

- Collect samples at an appropriate cadence (e.g., every few seconds depending on load and overhead).
- Attach UTC timestamp, instance/PID + JVM start, container ID, and JDK version as needed.
- Record negative numbers distinctly as unavailable/null; never turn them into 0.
- For CPU time, compute **deltas** within the same JVM instance; start a fresh series on process restart.
- Measurements of the same metric across a denominator/cgroup limit change must be annotated with the configuration boundary.

Never compare a CPU percentage at time A with a RAM figure at time B and claim causation if windows differ.

## 6. Environment memory is not Java heap

### 6.1. `getTotalMemorySize()` and `getFreeMemorySize()`

The extension returns:

- `getTotalMemorySize()`: total memory reported by the **operating environment**, in **bytes**.
- `getFreeMemorySize()`: free memory remaining in the operating environment, in **bytes**.

On OpenJDK 17 running in a Linux container with recognized cgroups, the numbers may reflect **container** resources rather than full host physical RAM. On other JVMs, other OSes, or with container support disabled, they may reflect the host/virtualized environment. Always include JDK/cgroup metadata when interpreting.

**Do not assume `total - free` equals the JVM's RSS.** That difference can include other processes' memory, kernel/cache/cgroup accounting depending on the platform. "Free" does not mean "reclaimable/available memory" like Linux's `MemAvailable`; terminology and accounting rules belong to the operating system.

If `total=2 GiB` and `free=0.5 GiB`, you can only say the environment reports **1.5 GiB not in the free state according to that metric**—you cannot conclude the Java heap is using 1.5 GiB.

### 6.2. `getTotalSwapSpaceSize()` and `getFreeSwapSpaceSize()`

Swap provides backing store for inactive memory pages in configurations that support it. These two methods return total/free swap **bytes** visible to the environment.

- `totalSwap=0` can be completely valid on containers without swap.
- `freeSwap < totalSwap` indicates some swap is used per the source's definition.
- Heavy swap usage does not by itself prove a Java heap leak; paging/OS pressure may be present.
- Swap may be independently capped or disabled at the container/cgroup level.

If latency spikes abnormally while swap usage rises, inspect page faults, paging I/O, kernel memory pressure, and container settings. Do not blame latency solely on swap before ruling out CPU throttling, GC pauses, or application I/O.

### 6.3. `getCommittedVirtualMemorySize()` differs from heap, RSS, and RAM

This method returns total **committed virtual memory** guaranteed available to the process per platform definition, in bytes; returns `-1` when unsupported. It is **not**:

- currently used Java heap (`MemoryMXBean.getHeapMemoryUsage().getUsed()`);
- heap max (`-Xmx`);
- RSS resident pages currently in RAM;
- directly equivalent to cgroup memory usage;
- OS total physical memory.

On Linux, virtual address space/commit, resident memory, and cgroup accounting differ significantly. A Java process can **reserve** large address regions for heap, metaspace, stacks, direct buffers, or mapped files without all of them being resident. Therefore, do not plot `getCommittedVirtualMemorySize()` as "JVM memory used" without stating its exact meaning.

### 6.4. Map of memory layers

```text
Host physical memory (RAM)
  ├── OS kernel + page cache + other processes
  └── Container/cgroup memory accounting (if present)
        └── JVM process resident/native memory
              ├── Java heap (objects)
              ├── Metaspace / class metadata
              ├── Thread stacks
              ├── Direct/mapped buffers
              ├── JIT code cache
              ├── GC/JVM native structures
              ├── JNI/native allocations
              └── Shared libraries and mapped pages
```

This is a **conceptual diagram**; not all regions add together without overlap or always belong to the same cgroup accounting bucket. OperatingSystemMXBean's role is providing the OS/environment perspective; `MemoryMXBean`, `MemoryPoolMXBean`, buffer-pool MXBeans, HotSpot Native Memory Tracking, OS `/proc/<pid>/status`/`smaps`, and cgroup metrics complement it with heap, native, RSS, and quota views.

### 6.5. Memory arithmetic example with fixed numbers

Suppose environment total memory is `2 GiB = 2,147,483,648 bytes` and free memory is `512 MiB = 536,870,912 bytes`:

```text
total_memory = 2147483648 bytes
free_memory  =  536870912 bytes
non_free     = 1610612736 bytes  (= 1536 MiB, or 1.5 GiB)
```

The `non_free` value is solely **the difference of two environment gauges** at the same checkpoint; it cannot be relabeled `jvm_heap_used` or `jvm_rss`.

In practice, the two methods may be read at slightly different instants. When computing a derived gauge, take samples closely together, account for skew, and remember the figures do not form an atomic snapshot.

## 7. Containers, Kubernetes, and resource limits

### 7.1. Container-awareness in JDK 17

JDK 17 HotSpot/OpenJDK generally supports Linux container detection (cgroups v1/v2) and uses appropriate cgroup limits for certain CPU/RAM calculations. However, **do not assert every JDK 17 build or vendor reads identical values**: updates/vendors may change detection logic and cgroup configuration matters too.

Items to verify:

- JDK vendor and update/build; HotSpot vs. another implementation;
- cgroup v1 vs. v2, and the exact cgroup path of that container;
- CPU quota/period, cpuset/affinity, and Kubernetes CPU limits;
- memory limit, swap limit, and container usage accounting;
- `-XX:+UseContainerSupport` or `-XX:-UseContainerSupport` (when supported);
- `-XX:ActiveProcessorCount=N` if set;
- resource requests and limits actually enforced by the orchestrator.

**Requests do not equal limits.** Kubernetes CPU/memory *requests* govern scheduling and related policies; *limits* can trigger cgroup CPU throttling or memory OOM termination. Many clusters apply default LimitRanges or admission policies, so "the manifest specifies no limit" does not guarantee the container is unlimited.

### 7.2. Why "2 CPUs" does not mean 2 dedicated physical CPUs

A container capped at 2 CPUs typically gets an **equivalent CPU time budget** or affinity/cpuset; it is not necessarily pinned to 2 unshared physical cores. A process can see `getAvailableProcessors()=2` yet still suffer throttling if it exhausts its quota within a CFS period; meanwhile, CPU load over a larger window can appear low due to throttled intervals.

`getAvailableProcessors()` is an integer the JVM uses to pick default parallelism, **not a metric proving absence of throttling**. When latency rises, check cgroup `cpu.stat`, CPU throttled periods/time, node CPU contention, GC/JIT state, and scheduler behavior. You cannot confirm throttling from `getProcessCpuLoad()` alone.

### 7.3. Useful read-only diagnostic commands

On an authorized host/tooling environment:

```bash
# Launch a test Java process to see which resources the JDK detects.
java -XshowSettings:system -version

# HotSpot details of the target JVM, if jcmd and permissions are available.
jcmd 12345 VM.version
jcmd 12345 VM.info
jcmd 12345 VM.flags

# To inspect detailed container-detection output on
# ONE controlled test process without altering the production JVM:
java '-Xlog:os+container=debug' -version
```

`12345` is an illustrative PID. `java -XshowSettings:system -version` spawns a **new** JVM, so it only reflects that command's JDK/environment; it **does not prove** the production process has the same image, cgroup, or flags. `jcmd VM.info` can output extensive metadata—check impact and control where it is stored. On Windows/macOS or runtimes lacking `-XshowSettings:system`, output differs.

With Linux cgroup v2, files such as `cpu.max`, `cpu.stat`, `memory.max`, `memory.current`, and `memory.events` help cross-check quotas, usage, throttling, and OOM events. Under cgroup v1 filenames differ. Read **the exact cgroup membership of the target process**, rather than grabbing a root cgroup file and assuming it belongs to the pod.

### 7.4. Discrepancies between host and container

A dashboard may report 20% host CPU usage while pod CPU is near 100% of **its allocated limit**. There is no contradiction if the two metrics use different denominators. Similarly, 100 GiB free on the host does not stop a pod from hitting a 1 GiB memory limit.

When reporting, always state:

- `scope = host / node / container / JVM process`;
- CPU denominator = host logical CPUs, quota cores, cpuset CPUs, or JVM availableProcessors;
- memory unit = bytes/MiB/GiB and which limit applies;
- JDK build and cgroup version;
- time window/scrape interval;
- unavailable sentinels and uncertainties.

## 8. Using OperatingSystemMXBean via JMX

### 8.1. Platform MBeanServer within the same JVM

Attributes can be queried through the standard management server. Standalone Java 17+ example requiring no extension:

Save the file **`OsJmxLocalDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class OsJmxLocalDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name =
                new ObjectName("java.lang:type=OperatingSystem");

        Object processors =
                server.getAttribute(name, "AvailableProcessors");
        Object osName = server.getAttribute(name, "Name");

        System.out.println("registered="
                + server.isRegistered(name));
        System.out.println("processorsIsInteger="
                + (processors instanceof Integer));
        System.out.println("nameIsString="
                + (osName instanceof String));
    }
}
```

Compile/run:

```bash
javac OsJmxLocalDemo.java
java OsJmxLocalDemo
```

**Exact stdout** on JDK 17 with the standard platform MBeanServer:

```text
registered=true
processorsIsInteger=true
nameIsString=true
```

This example reads attributes **inside the current JVM**. With extensions, JMX may expose extra attributes on the corresponding MBean, though the exact attribute list depends on the implementation. When connecting from a management process to another JVM, use an authenticated `MBeanServerConnection` and verify server identity.

### 8.2. Remote JMX and security

Remote JMX connections allow collecting CPU/memory snapshots without changing application code, yet an unguarded setup can leak system metadata or open dangerous administrative access paths.

- Enable only under approved procedures and permissions.
- Enforce authentication, TLS/network policies, or secure management channels.
- Never expose management ports to the public Internet.
- Never read `java.lang:type=OperatingSystem` from JVM A and label the metrics as pod B.
- Use a reasonable sampling interval; `getSystemLoadAverage()` is inherently a hint, and recent CPU load does not need ultra-high-frequency polling.

Not every JVM/JDK image exposes identical extended attributes; collectors must distinguish `unsupported` from zero.

## 9. Correlating CPU, memory, threads, and GC with evidence

### 9.1. When process CPU is high

If `getProcessCpuLoad()` rises alongside latency:

1. Verify scope (process/container) and timestamp.
2. Check environment load `getCpuLoad()`, effective CPUs, and CPU quota.
3. Measure `getProcessCpuTime()` across two snapshots to get CPU-seconds/second.
4. Check `ThreadMXBean` per-thread CPU time (if supported, enabled, and permitted) or JFR/profilers to find hotspots.
5. Inspect GC/JIT/compilation/native threads since process CPU includes JVM internals.
6. Check throttling, scheduler, and traffic: do not blame application logic solely because process CPU is high.

A CPU-intensive request can drive high process load even with a small thread count. Conversely, thousands of blocked threads can cause high latency while process CPU remains low.

### 9.2. When environment CPU is high while process CPU is low

If environment CPU is near 95% while JVM process CPU is near 5%, the primary possibility is **load from other workloads**, though you must verify both metrics share the same scope and window. If the JVM runs in its own container, discrepancies can reflect host/container accounting, node CPU contention, or counter update lag. Combine OS process metrics, cgroup metrics, and CPU usage of neighboring pods.

In particular, never jump to "there is a rogue process/miner" from a single pair of numbers.

### 9.3. When CPU is low yet latency is high

Possible causes include:

- Network/disk/database I/O waits, lock contention, or parking/blocking;
- CPU throttling starving the process of CPU time within its quota window;
- GC stop-the-world pauses, safepoints, or native blocking;
- downstream timeouts and queueing elsewhere;
- deadlocks or thread starvation.

Use thread dumps, `ThreadMXBean`, JFR, GC logs, tracing, request metrics, and OS I/O stats. Low CPU does not mean the JVM is "healthy".

### 9.4. When a container is OOMKilled while heap still has headroom

OS/cgroup memory limits usually cover many regions beyond the Java heap: direct buffers, metaspace, thread stacks, JIT code cache, GC/native/JNI memory, mapped pages, and some kernel/cache accounting. Heap `used` may sit below `-Xmx` while **cgroup `memory.current` still hits `memory.max`**, causing an OS-level OOM kill.

Investigation requires:

- container memory limit/current usage and `memory.events`/OOMKilled reason;
- `MemoryMXBean` heap and non-heap; `MemoryPoolMXBean` if needed;
- buffer pools, thread counts/stacks, and JVM Native Memory Tracking if enabled;
- process RSS/`/proc/<pid>/status`/`smaps` if permitted;
- GC logs/JFR output if available;
- checking whether the cgroup metric behind `getTotalMemorySize()` reflects the actual limit.

Never use `getTotalMemorySize() - getFreeMemorySize()` as "JVM native memory leak"; its scope is the environment, not solely the process.

### 9.5. Quick decision table

| Observation | Likely direction | Next verification step |
| --- | --- | --- |
| High `processCpuLoad`, rapidly rising `cpuTime` | JVM using heavy CPU | JFR/profiler, thread CPU, GC/JIT, quota |
| High `cpuLoad`, low `processCpuLoad` | Environment busier than the JVM | Host/cgroup/process metrics, scope |
| High load average, modest CPU load | Run queue/I/O or window difference | Run queue, I/O wait, OS-specific load semantics |
| Low CPU, high p99 | Waiting, lock/I/O, throttling, or pauses | Thread dump, tracing, GC log, cpu.stat |
| Low free memory, steady heap | Off-heap usage or other workloads | RSS, cgroup accounting, native memory |
| `getProcessCpuTime()=-1` | Unsupported counter | Skip delta calculation; use another metric |
| `getSystemLoadAverage()<0` | Load average unavailable | Alternative OS metrics; never report 0 |
| JVM sees 1 CPU, host has 64 | Cgroup/affinity/flags or JDK detection | `-XshowSettings:system`, `VM.info`, quota, `ActiveProcessorCount` |

## 10. Incident analysis examples with synthetic data

### Scenario A — CPU throttling driving up p99

Suppose pod `checkout-1` exhibits:

```text
node logical CPUs              = 32
container CPU limit            = 1 CPU
JVM getAvailableProcessors()   = 1
JVM getProcessCpuLoad()        = 0.95
JVM getCpuLoad()               = 0.97
p99 latency                    = rose from 80 ms to 900 ms
cgroup cpu.stat nr_throttled   = climbing continuously
```

This is a **simulated example**, not real output. The figures suggest the process is saturating its allocated CPU budget and being throttled. To conclude, compare throttled period/time ratios over the window, request volume, GC pauses, and thread CPU. Do not conclude a CPU bottleneck from `getProcessCpuLoad()=0.95` alone without quota/throttling evidence.

### Scenario B — Busy host, low JVM CPU usage

Suppose:

```text
operating-environment CPU load = 0.88
JVM process CPU load           = 0.08
JVM process CPU time delta     = 0.8 CPU-second / 10 seconds wall
JVM availableProcessors        = 2
```

The CPU time delta corresponds to **0.08 core-equivalent**, or roughly **4% of two cores**, not necessarily matching the hypothetical 8% `getProcessCpuLoad()` because sampling windows/denominators can differ. This also shows why you **should not equate** a manual delta formula with the "recent usage" method unless window and definition match. Verify neighboring workloads, cgroup scope, and collection timing.

### Scenario C — OOMKilled while Java heap still has plenty of headroom

```text
container memory.max          = 1 GiB
MemoryMXBean heap used        = 300 MiB
MemoryMXBean heap max         = 600 MiB
container memory.current      = near 1 GiB
container restart reason      = OOMKilled
```

Heap at `300 MiB` does not contradict the container hitting `1 GiB`. The gap can include native allocations, stacks, direct buffers, file cache/mapped memory, or other cgroup charges. Collect NMT/OS RSS/buffer-pool/thread metrics before concluding a memory leak. Check `-Xmx`, max direct memory, thread count, and container limit together.

### Scenario D — High load average where GC is not the cause

A Linux node has load average `12`, while the JVM has `getAvailableProcessors()=4` and only 10% process CPU during rising I/O latency. Part of the load average may stem from I/O-waiting tasks or node-wide contention; check run queue, iowait, disk/network latency, thread stacks, and other processes. Never deduce that 12/4 = 300% CPU or that adding GC threads is the right fix.

## 11. Telemetry design from MXBeans

### 11.1. Fields and units to record

A metric/snapshot event should include:

- `observed_at_utc`: UTC timestamp at sampling;
- `service`, `instance`, `jvm_pid`, and `jvm_start_time` to distinguish process lifetimes;
- `os_name`, `os_arch`, `jdk_version`, `available_processors`;
- `system_load_average_1m` (numeric, null when unavailable);
- `environment_cpu_load_fraction`, `process_cpu_load_fraction` (numeric `[0,1]` or null);
- `process_cpu_time_ns` (monotonic-like counter within one process; null when unsupported);
- `total_memory_bytes`, `free_memory_bytes`, `total_swap_bytes`, `free_swap_bytes`;
- `committed_virtual_memory_bytes` (never substitute for RSS);
- `resource_scope` (host/container/unknown), `cpu_limit_cores`, and `memory_limit_bytes` when evidenced;
- `source_api`/JDK vendor/build when comparing across deployments.

Keep units explicit in field names to avoid confusing milliseconds with nanoseconds, bytes with MiB, or fractions with %. When a metric is unavailable, store null and a separate reason; never coerce negative sentinels to 0 (0 CPU usage is a valid measurement).

### 11.2. Distinguishing gauges, counters, and rates

| Metric type | Examples | How to use |
| --- | --- | --- |
| Gauge | `getProcessCpuLoad()`, `getFreeMemorySize()` | Read value at sample time; verify scope/window |
| Cumulative counter | `getProcessCpuTime()` | Compute deltas/rates between samples of the same JVM; restarts reset |
| OS hint/average | `getSystemLoadAverage()` | Track queue pressure trends; never convert to %CPU |
| Configuration gauge | `getAvailableProcessors()`, `getTotalMemorySize()` | Track quota/config changes and context; does not directly measure usage |

Prometheus/Grafana can smooth or distort curves via scrape intervals and query windows. Apply exact labels and units in dashboards; never display `processCpuTimeNs` as "CPU percent" before applying a proper derivative and denominator.

### 11.3. Choosing an appropriate sampling interval

`getSystemLoadAverage()` is inherently roughly a one-minute average; polling every 10 ms will not produce a "10 ms load average". `getCpuLoad()` and `getProcessCpuLoad()` update per implementation mechanics; polling too fast can return stale/repeated values or unavailable. In production, collect metrics on your platform's standard cadence (typically a few seconds or more, per SLO) while balancing metric/label cardinality.

When investigating a spike lasting tens of milliseconds, use JFR/profilers/CPU sampling rather than cranking MXBean polling frequency endlessly.

## 12. Common mistakes when reading OperatingSystemMXBean

1. **Importing the wrong interface with the same name.** `java.lang.management` does not declare `getCpuLoad()` or `getProcessCpuTime()`; the `com.sun.management` extension does.
2. **Casting to the extension without checking.** Another JVM may lack support and raise `ClassCastException` or module resolution errors.
3. **Confusing load average with CPU utilization.** Load average can exceed 1 and is not a percentage.
4. **Reading negative CPU load as "-100%" or 0%.** Negative numbers are unavailable sentinels.
5. **Confusing process CPU time (ns) with uptime/wall time (ms).** CPU time can grow faster than wall time on multicore systems.
6. **Computing deltas across two process lifetimes.** Counters reset on restart; PID/name may be reused.
7. **Failing to normalize by a meaningful CPU count.** A 64-core host differs from a 1-CPU container quota; comparing percentages with mismatched denominators misleads.
8. **Confusing `getCpuLoad()` with `getProcessCpuLoad()`.** One scopes the environment, the other the JVM process.
9. **Assuming nanosecond accuracy from CPU time.** The API specifies precision, not matching accuracy.
10. **Equating environment free memory with free heap.** Heap is only part of the JVM process.
11. **Using committed virtual memory as RSS.** Virtual commit is not resident physical memory.
12. **Not knowing whether the JDK is container-aware.** Cgroup v1/v2, JDK updates/vendors, and flags change scope.
13. **Assuming low CPU load rules out throttling.** Check cgroup counters and sampling intervals.
14. **Assuming free host RAM means a container cannot OOM.** Pod memory limits can be far smaller than host RAM.
15. **Inferring a trend from one snapshot.** CPU time requires two samples; recent CPU load and load average use different windows.
16. **Reading metrics after OS/JVM configuration changed without marking the timestamp.** Available processors or memory limits may shift.
17. **Running `java -version` on a debug machine to infer the production JVM's cgroup.** That is a different process.
18. **Opening unauthenticated JMX to "take a quick reading".** Metadata can be sensitive and management endpoints expand attack surface.
19. **Creating excessive label cardinality from PID or request ID on every metric.** Track instance/JVM lifecycles cleanly.
20. **Treating platform-specific APIs as guaranteed stable across every Java distribution.** Check availability and build fallbacks.

## 13. Checklist before concluding a CPU/memory bottleneck

- [ ] Using the standard interface or the extension? Checked module/implementation?
- [ ] Recorded all units: fraction, CPU nanoseconds, bytes, load average?
- [ ] Marked every negative sentinel as unavailable instead of converting to 0?
- [ ] Distinguished operating-environment CPU from JVM-process CPU?
- [ ] Distinguished "recent usage" from one-minute load average?
- [ ] Computed CPU time deltas from **two samples of the same JVM** with a proper wall elapsed clock?
- [ ] Verified CPU denominator against quota/affinity/availableProcessors and timestamp?
- [ ] Accounted for cgroup v1/v2, JDK vendor/update, `UseContainerSupport`, and `ActiveProcessorCount`?
- [ ] Clarified which host/container total/free memory represents, without confusing it with heap/RSS?
- [ ] Cross-checked swap, `memory.current`/`max`, kernel accounting, or OOM events when needed?
- [ ] When CPU/latency rose, cross-checked GC, thread stacks/JFR, I/O, and CPU throttling?
- [ ] Attached UTC sample time, PID/start, container/node, and telemetry source?
- [ ] Avoided exposing JMX or internal operational data without authorization?
- [ ] Conclusions separate **what the API measured** from **hypotheses** needing further proof?

## 14. Self-check exercises

**Exercise 1 — CPU normalization.** Over 5 wall-clock seconds, `getProcessCpuTime()` increases by 15 billion CPU nanoseconds. Compute average core-equivalents and the ratio for `N=6`. Answer: `15 / 5 = 3` cores on average, or **50% of 6 cores**. If the container actually grants only 3 CPU cores, the same work equals 100% under that denominator; always state the source of N.

**Exercise 2 — Unavailable.** A JVM returns `getSystemLoadAverage()=-1` and `getProcessCpuLoad()=-1` on its first few reads. Can you conclude load is 0? **No.** Record unavailable, check OS/JDK, and use other metrics if needed.

**Exercise 3 — Memory.** Container limit is 1024 MiB, heap used is 250 MiB, yet the pod was OOMKilled. Is this plausible? **Yes.** Heap is only part of container accounting; investigate native memory, thread stacks, direct buffers, metaspace, file cache, cgroup events, and actual RSS.

**Exercise 4 — Scope.** Host CPU is 30%, while pod JVM process CPU is 90% on another dashboard. Do the two numbers contradict? **Not necessarily.** The dashboards may normalize by 32 host cores vs. 2 pod cores and use different sampling windows; compare metric definitions and time intervals.

**Exercise 5 — Load average.** `getSystemLoadAverage()=6.0` on a 4-CPU node, `getCpuLoad()=0.35`. Can you state CPU is 150% busy? **No.** Load average is the average number of runnable entities over roughly one minute per the OS, while CPU load is recent CPU fraction; gather I/O/runqueue evidence.

## References

- Oracle Java SE 17, [`java.lang.management.OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): OS identity, available processors, load average, and negative sentinels.
- Oracle Java SE 17, [`com.sun.management.OperatingSystemMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): `getCpuLoad`, `getProcessCpuLoad`, `getProcessCpuTime`, memory/swap, and virtual memory; names deprecated since Java 14.
- Oracle Java SE 17, [`ManagementFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): obtaining platform MXBeans and MBeanServer.
- Oracle Java SE 17, [`MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html), [`ThreadMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): isolating heap and CPU/thread diagnostics from the environment.
- Oracle Java SE 17, [`jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html), [`java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): verifying VM settings, container support, and startup options.
- Red Hat Developer, [Java 17: What’s new in OpenJDK's container awareness](https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness): cgroups, `UseContainerSupport`, `ActiveProcessorCount`, and environment scope.
- Linux kernel documentation, [Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.stat`, `cpu.max`, `memory.current`, `memory.max`, `memory.events`.

**Conclusion:** `OperatingSystemMXBean` is the bridge from Java to OS/container resource context. Reading it accurately requires recording **scope + unit + sample timestamp + JVM identity + cgroup limits**. Only after correlating those with process CPU time, heap/RSS, CPU throttling, threads, JFR, and container events do you have solid grounds to conclude environment CPU or memory caused an incident.