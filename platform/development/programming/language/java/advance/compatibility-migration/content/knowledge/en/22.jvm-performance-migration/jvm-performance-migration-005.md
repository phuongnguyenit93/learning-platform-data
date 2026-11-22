# Detecting CPU, Memory, and Cgroup Limits in Containers

## 1. Why do containers change how the JVM detects resources?

When a Java application runs directly on a physical machine or virtual machine, the JVM typically observes the resources provided by the operating system to the process. Inside a container, the Java process still shares the host kernel but is placed inside isolation and resource management mechanisms, most notably **Linux control groups (cgroups)**.

This creates two very different layers of information:

- **Host resources**: the number of logical CPUs and total RAM of the node/host.
- **Container effective resources**: the allowed CPU allocation, CPU time quota, allowed CPU set, memory limits, and cgroup constraints.

For example, a Kubernetes node has 32 logical CPUs and 128 GiB of RAM, while the container running Java is configured with a limit of 2 CPUs and 2 GiB of RAM. If the JVM chooses the number of GC threads, JIT compiler threads, or heap size as if it had 32 CPUs and 128 GiB of RAM, the application can experience excessive memory growth, CPU contention, throttling, or termination by the system for exceeding container limits.

During **Java Advance Compatibility Migration**, this is especially important because cgroup detection support and JVM ergonomics rules have evolved across JDK versions and patches. Upgrading the JDK, changing the JDK vendor, changing the Linux distribution, or moving from cgroups v1 to v2 can change the values the JVM auto-detects even when application source code has not changed.

Lesson objectives:

1. Understand the CPU and memory metrics applied to containers by Linux cgroups.
2. Distinguish hard limits, relative priority scheduling mechanisms, and host resource information.
3. Understand JVM container awareness and the Runtime.availableProcessors and Runtime.maxMemory metrics.
4. Know how to observe cgroups v1/v2, CPU throttling, and container OOM events.
5. Configure heap, native memory, and thread pools based on actual workload rather than extrapolating from a single RAM number.
6. Test behavior on Docker/Kubernetes and supported JDK versions.
7. Establish a compatibility baseline to detect performance and resource-limit regressions after migration.

## 2. Concepts: CPU, quota, cpuset, and memory limit

### 2.1. Host logical CPUs

A machine may be recognized by the operating system as having N logical processors. These logical CPUs do not necessarily correspond to N physical cores, nor does it mean a container is allowed to use all N CPUs.

In Linux, commands such as nproc or lscpu can display different views of CPUs; some tools may account for affinity/cgroup depending on version. When investigating, always record the exact source of the metric.

### 2.2. CPU quota

**CPU quota** limits the total CPU time a process group can consume within one scheduling period.

For example, a quota of 150,000 microseconds in a 100,000-microsecond period corresponds to a budget of roughly **1.5 CPUs** of total compute time. This is not 1.5 dedicated physical cores.

When a workload consumes all of its quota before the period ends, the cgroup can undergo **CPU throttling** until the next period, increasing latency even when the host still has idle CPU cores.

### 2.3. Cpuset and CPU affinity

**Cpuset** restricts the logical CPUs on which processes are permitted to run. For example, a container might only be permitted to run on CPU 4 and CPU 5, corresponding to a set of two logical CPUs.

Cpuset and quota are two distinct constraints:

- Cpuset of 4 CPUs, quota equivalent to 1 CPU: processes can be scheduled on CPUs within that set, but total CPU time is limited to about 1 CPU.
- Cpuset of 2 CPUs, unlimited quota: processes cannot actually run on more than 2 logical CPUs concurrently, even if the host has many other CPUs.

Beyond cpuset, process affinity can also be altered by other mechanisms. When checking effective CPUs, inspect the policy as a whole.

### 2.4. CPU weight or shares

CPU shares (cgroups v1) and CPU weight (cgroups v2) generally reflect **relative priority when CPU resources are under contention**. They are not a hard cap equivalent to quota.

For example, two cgroups with different weights can divide CPU time proportionally when contending with each other; if the host is idle, a cgroup with lower weight can still consume more CPU than its contended share, provided other limits allow it.

Therefore, do not equate a Kubernetes CPU request with a CPU limit. Requests typically relate to scheduling and guaranteed allocation; limits may be enforced via CPU quota when that mechanism is configured.

### 2.5. Memory limit

A memory cgroup can set an upper bound on the amount of memory charged to the group. This limit is not just the Java heap: it covers memory pages accounted to the cgroup by the system, including multiple kinds of process memory and certain kernel/page cache resources depending on mechanism and kernel.

Java heap is a major part, but it is **not the entire memory consumed by the JVM process**. Setting Xmx equal to the container memory limit is usually unsafe because non-heap/native memory also exists.

## 3. What are cgroups and why are there two versions?

Linux cgroups group processes and manage/observe resources such as CPU, memory, pids, and I/O. Container runtimes use cgroups alongside namespaces, filesystems, and other mechanisms to implement process isolation and resource controls.

Two commonly encountered generations:

- **cgroups v1**: controllers such as cpu, cpuacct, cpuset, and memory can use different hierarchies/mounts, with separate configuration files.
- **cgroups v2**: a unified hierarchy, new file API, and new representations such as cpu.max, cpu.weight, memory.max, and memory.current.

A machine may use v1, v2, or a hybrid configuration in specific system setups. Modern containers commonly use v2, though you should not assume every environment is identical.

### 3.1. Quick comparison of key files

| Purpose | cgroups v1 | cgroups v2 |
|---|---|---|
| CPU quota | cpu.cfs_quota_us | cpu.max |
| CPU period | cpu.cfs_period_us | Second field of cpu.max |
| Relative CPU priority | cpu.shares | cpu.weight |
| CPU throttling | cpu.stat | cpu.stat |
| CPU affinity/cpuset | cpuset.cpus and kernel-dependent effective files | cpuset.cpus, cpuset.cpus.effective |
| Memory hard limit | memory.limit_in_bytes | memory.max |
| Current memory usage | memory.usage_in_bytes | memory.current |
| Memory soft/high boundary | v1-specific mechanisms, depending on controller/kernel | memory.high |
| Memory events/OOM | memory.failcnt, memory.oom_control, and other sources | memory.events |
| Swap-related limits | memsw files when enabled | memory.swap.max, memory.swap.current |
| PIDs limit | pids.max | pids.max |

In v1, file names depend on where each controller is mounted. Not every container exposes these files directly under /sys/fs/cgroup/memory or /sys/fs/cgroup/cpu. Always inspect actual mount information and cgroup membership.

### 3.2. Detecting cgroups inside a Linux container

Example inspection commands:

~~~bash
cat /proc/self/cgroup
cat /proc/self/mountinfo
ls /sys/fs/cgroup
~~~

With unified cgroups v2, /proc/self/cgroup usually has an entry like:

~~~text
0::/some/container/path
~~~

and the cgroup filesystem can expose files such as cpu.max and memory.max. However, the actual layout varies by runtime, delegation, and mount namespace.

With cgroups v1, /proc/self/cgroup usually has multiple lines per controller. Do not rely on a single rigid regex across all Docker, containerd, Kubernetes, or systemd versions.

### 3.3. Limits can be inherited from parent cgroups

In a hierarchy, a process can be constrained by its own cgroup or by an ancestor. For instance, a container may sit inside a pod or slice that already has a lower limit. Reading only a single memory.max file at what you assume is the container path can miss the effective constraint.

If a child cgroup shows max while a parent cgroup is capped, usable resources remain constrained by the ancestor. The JVM and diagnostic tools can also differ across versions in how they resolve effective limits.

When JVM output does not match the direct file, inspect the full cgroup path, hierarchy, and limits at the pod, node, and systemd levels.

## 4. CPU quota on cgroups v1

In cgroups v1, the scheduler CPU controller typically uses:

- cpu.cfs_quota_us: maximum CPU time in microseconds permitted in one period.
- cpu.cfs_period_us: period length, in microseconds.

Example:

~~~text
cpu.cfs_quota_us  = 150000
cpu.cfs_period_us = 100000
~~~

The quota/period ratio is:

~~~text
150000 / 100000 = 1.5 CPU
~~~

This is a time-based CPU capacity estimate, not a statement that the JVM will report exactly Runtime.availableProcessors() = 1.5. That Java method returns an integer, and how fractional quotas are rounded or combined with cpuset depends on the JDK and active constraints.

When no quota applies, the v1 quota file commonly holds a special value such as -1; verify against the kernel and controller in use.

### 4.1. CFS throttling

Example /sys/fs/cgroup/cpu/cpu.stat in a v1 environment:

~~~text
nr_periods 10000
nr_throttled 3600
throttled_time 78000000000
~~~

These numbers are illustrative examples, not measurements from a real system.

In cgroups v1, throttled_time is typically expressed in nanoseconds. An increasing nr_throttled indicates that periods occurred in which the cgroup was throttled. Do not compute an exact capacity-loss percentage from nr_throttled / nr_periods alone; also examine throttled duration, workload pattern, and CPU scheduling history.

When a Java application exhibits sharp latency spikes under high load while host CPU utilization appears "far from full," quota throttling is a primary suspect to investigate.

## 5. CPU quota and weight on cgroups v2

In cgroups v2, quota and period are represented in the single file cpu.max:

~~~text
150000 100000
~~~

This means a quota of 150,000 microseconds per 100,000-microsecond period, equivalent to about 1.5 CPUs.

If no quota is set, the value may be:

~~~text
max 100000
~~~

In this case cpu.max imposes no hard quota on that cgroup, though cpuset, ancestor cgroups, and other policies can still restrict effective CPU capacity.

Example:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.weight
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
~~~

These paths are directly accessible only when the container's layout and mount namespace expose the files there.

### 5.1. CPU weight is not a hard quota

cpu.weight is cgroups v2's relative scheduling weight. If no CPU limit is set and weight is low, a workload can still consume substantial CPU when the node is idle. Therefore:

- Do not infer a CPU limit by dividing cpu.weight by a constant and treating it as fixed cores.
- Do not treat a Kubernetes CPU request as though it were an enforced quota.
- Test in environments with contention, quotas, and cpusets representative of production.

Some older JDKs computed CPU counts from CPU shares/weight using their own policies. Newer releases and patches may behave differently; during migration, measure Runtime.availableProcessors() on the exact target JDK rather than relying on general assumptions.

### 5.2. Throttling on cgroups v2

cpu.stat can contain fields such as:

~~~text
usage_usec 12000000
user_usec 9000000
system_usec 3000000
nr_periods 15000
nr_throttled 4300
throttled_usec 2200000
~~~

The values above are examples only. Field names may depend on kernel and controller; when CPU bandwidth control is active, nr_throttled and throttled_usec help evaluate throttling severity.

If quota bottlenecks CPU-heavy requests, increasing thread pool size does not create additional CPU time. In fact, it can worsen context switching, queueing, and stack memory usage across more threads.

## 6. Effective CPUs detected by the JVM

In Java, a foundational metric is:

~~~java
int processors = Runtime.getRuntime().availableProcessors();
~~~

This number is determined by the JVM from available CPU information and policies per its implementation; in container-aware JVMs, it may be influenced by cgroup quota/cpuset and JVM options.

It is **not necessarily the host's physical CPU count**, nor is it a guarantee of throughput matching that count.

### 6.1. Fractional CPU quotas and integer counts

Suppose a container has a quota equivalent to 0.5 CPU. Runtime.availableProcessors() still returns a positive integer—it cannot return 0.5. A thread pool sized from availableProcessors may still create at least one worker, yet the scheduler will still throttle once quota runs out.

For a 1.5 CPU quota, the JVM selects an integer according to its policy and other active constraints. Do not depend on a fixed rounding rule without checking the JDK vendor and release.

### 6.2. How CPU quota affects JVM ergonomics

The effective processor count can influence:

- GC thread counts in certain collectors and GC phases.
- JIT compiler thread counts or optimization policies.
- Certain defaults of ForkJoinPool.commonPool and parallel streams.
- Libraries and frameworks that size default thread pools via Runtime.availableProcessors().
- Decisions regarding concurrent phases, workload sizing, and parallelism.

Not every thread pool derives from availableProcessors; many libraries have separate configuration or fixed thread counts. Inspect each component individually when diagnosing performance regressions.

### 6.3. The -XX:ActiveProcessorCount option

When you need to pin how the JVM sees processor count for ergonomic decisions:

~~~bash
java -XX:ActiveProcessorCount=2 -jar application.jar
~~~

This option can override the processor count reported by the JVM for many runtime purposes, depending on the HotSpot/JDK in use. However, **it does not change the kernel CPU quota** and does not grant additional CPU resources to the container.

If the kernel grants only 0.5 CPU and you set ActiveProcessorCount=8, the process does not receive 7.5 more real CPUs; the JVM and libraries may spawn more workers and suffer heavier throttling.

Use overrides intentionally only with benchmark evidence and clear understanding of impacts on GC, ForkJoinPool, and thread pools. Never use the flag to mask a misconfigured cgroup.

## 7. Kubernetes CPU requests and limits

In Kubernetes, resource requests and limits serve distinct roles:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-cgroup-demo
spec:
  containers:
    - name: app
      image: example/java-app:1.0
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
        limits:
          cpu: "1500m"
          memory: "1Gi"
~~~

This is an illustrative manifest; example/java-app:1.0 is a placeholder, not a prebuilt image.

Interpretation:

- requests.cpu = 500m corresponds to 0.5 CPU used for cluster scheduling and resource reservation decisions.
- limits.cpu = 1500m corresponds to 1.5 CPUs under normal CPU limiting; on Linux it is typically enforced via CPU controller quota when enabled.
- requests.memory = 512Mi helps the scheduler account for required memory capacity.
- limits.memory = 1Gi establishes the container's memory limit per runtime/kubelet policy.

**A request is not a hard cap**. If only a CPU request is set without a CPU limit, effective CPU time can depend on node contention, shares/weight, affinity, and cluster policy.

### 7.1. Kubernetes CPU throttling

When a container with a CPU limit exceeds its quota in a period, it can be throttled. This can cause:

- Increased P95/P99 request latency.
- Slower GC pauses and slower concurrent GC progress.
- Slower queue drainage by event loops, executors, and background jobs.
- Health check timeouts or probe failures under load.

Track metrics from cgroup/container monitoring such as throttled periods, throttled time, and CPU usage, then correlate them with request latency and application saturation.

### 7.2. CPU requests do not equal JVM performance

Suppose:

~~~text
requests.cpu = 250m
limits.cpu   = 2
~~~

The JVM may detect processor count based on quota, cpuset, and JDK policy rather than necessarily treating 250m as a fixed CPU count. Under node contention, CPU shares/weight can still affect resource competition.

Accordingly, concurrency tuning should be driven by **actual CPU time, throttling, queue depth, and latency**, not solely by a requests.cpu value in YAML.

## 8. Memory cgroup v1

In cgroups v1, two commonly seen files are:

~~~text
memory.limit_in_bytes
memory.usage_in_bytes
~~~

These files may live under the corresponding memory controller mount, such as /sys/fs/cgroup/memory in some environments.

Example:

~~~bash
cat /sys/fs/cgroup/memory/memory.limit_in_bytes
cat /sys/fs/cgroup/memory/memory.usage_in_bytes
cat /sys/fs/cgroup/memory/memory.failcnt
~~~

Paths and accessibility depend on the container runtime and kernel.

### 8.1. A huge value does not mean the container has huge RAM

In cgroups v1, when a memory limit is not normally constrained, the limit file may hold an enormous numeric sentinel representing effectively unlimited memory. Never treat that number as real physical RAM for sizing Xmx.

When the JVM reads container limits, it must distinguish valid limits from values indicating unlimited memory, and may compare against physical memory or ancestor limits depending on implementation.

### 8.2. Cgroup memory does not equal Java heap

memory.usage_in_bytes reflects memory usage accounted by the memory controller, not Runtime.totalMemory or Runtime.maxMemory.

Inside a container, memory can include:

- Java heap committed/resident pages.
- Metaspace, class metadata, and code cache.
- Thread stacks and runtime native allocations.
- DirectByteBuffer, memory-mapped files, and native libraries.
- GC native structures and JIT/compiler memory.
- Page cache and other memory charges per kernel/controller accounting.

Therefore, an application whose heap has only used 700 MiB can still be OOM-killed if the memory limit is 1 GiB and the remaining components exceed the remaining budget.

## 9. Memory cgroup v2

In cgroups v2, important files include:

~~~text
memory.max
memory.current
memory.high
memory.events
memory.stat
memory.swap.max
memory.swap.current
~~~

Example:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.high
cat /sys/fs/cgroup/memory.events
~~~

### 9.1. memory.max

memory.max is the cgroup's hard limit according to the controller. If the file contains:

~~~text
1073741824
~~~

that level corresponds to 1 GiB in this example. If it contains:

~~~text
max
~~~

it means no hard limit is set on that cgroup; ancestor limits and other constraints can still apply.

### 9.2. memory.current

memory.current reflects memory usage currently charged to the cgroup. It is not the sum of live Java heap objects. A change in base image, kernel, or page cache can alter memory.current even when Java heap usage is similar.

### 9.3. memory.high

memory.high is a throttling threshold: when the cgroup exceeds it, the kernel can apply memory reclaim and throttling to reduce memory pressure. It does not carry the same semantics as memory.max.

Thus, rising latency due to memory delays even before an OOM kill can still trace back to memory.high, reclaim, or host/ancestor pressure.

### 9.4. memory.events

This file can contain fields such as:

~~~text
low 0
high 120
max 24
oom 3
oom_kill 2
oom_group_kill 0
~~~

The values are examples. high/max/oom/oom_kill are controller events with distinct meanings; during OOM investigations, correlate timestamps, pod status, kernel/container runtime logs, and JVM metrics.

Do not assume every Java OutOfMemoryError must increment oom_kill: Java can throw OutOfMemoryError on its own due to heap limits or another memory region before the kernel kills the process.

## 10. How does the JVM detect container resources?

In JVMs implementing container awareness, the JVM can use cgroup information instead of looking only at total host RAM and CPUs. On modern HotSpot builds, the option:

~~~text
-XX:+UseContainerSupport
~~~

is typically enabled by default on supporting JDK releases. Across older JDKs and update releases, container/cgroup support history varies, and vendors may backport fixes.

**Do not write overly simplistic rules** such as "all Java 8 versions lack container awareness" or "every Java 11 handles cgroups v2 completely." Actual capability depends on:

- JDK major version, update level, vendor, and backports.
- Linux kernel, container runtime, and cgroups v1 vs. v2.
- Enabled or disabled flags.
- Mount namespace configuration and cgroup hierarchy.
- Bug fixes shipped in each specific update release.

During migration, always verify using the exact JDK binary packaged in the container or deployed to runtime.

### 10.1. What does container support affect?

Several values and ergonomic choices can be affected:

- Active processor count.
- How the JVM determines baseline RAM for ergonomic heap sizing.
- Default GC thread counts and certain other thread counts.
- GC and heap decisions across combinations of JDK and flags.
- Certain JVM runtime APIs and metrics.

JVM container awareness does not mean every Java library reads cgroup memory the same way the JVM does; a library might read /proc/meminfo, inspect separate files, or make host-based assumptions.

### 10.2. The -XX:-UseContainerSupport option

Some HotSpot JDKs allow disabling container awareness:

~~~bash
java -XX:-UseContainerSupport -jar application.jar
~~~

Doing so causes the JVM to fall back toward host-oriented resource detection and flag defaults. This is **not a standard fix** for container performance issues; disabling awareness can cause heap and parallelism defaults to be sized far above container limits.

Use it only in controlled diagnostic experiments to isolate root cause, documenting exact JDK and flags. Do not apply it unconditionally in production.

## 11. JVM heap and memory limit: two different numbers

The Java heap stores objects managed by Java. Commonly referenced settings include:

- Xms: initial heap capacity configuration.
- Xmx: maximum heap size.
- MaxRAMPercentage: fraction of baseline RAM used to calculate ergonomic maximum heap when no explicit Xmx is given.
- InitialRAMPercentage: fraction used to calculate initial heap in applicable configurations.
- MinRAMPercentage: an ergonomics option targeting small-memory environments; its name can mislead readers into thinking it sets a hard minimum heap.

These percentages follow each JVM version's specific algorithm, thresholds, and limits; do not assume every JDK uses the same default percentages.

### 11.1. 1 GiB limit example

Suppose a container has a 1 GiB memory limit. If a container-aware JVM uses 1 GiB as the basis for MaxRAMPercentage and is configured with:

~~~bash
java -XX:MaxRAMPercentage=65.0 -jar application.jar
~~~

then 65% of 1 GiB works out theoretically to roughly 665.6 MiB. The actual maximum heap size may be rounded or adjusted by JVM ergonomics and other flags.

The remaining memory must accommodate:

- Metaspace.
- Code cache.
- Thread stacks.
- Direct/native buffers.
- GC runtime structures.
- Native libraries and agents.
- Other allocations charged to the memory cgroup.

Do not treat the remaining 35% as "guaranteed slack." Actual headroom needs depend on workload, thread count, I/O buffers, class metadata, and kernel-accounted memory.

### 11.2. -Xmx has its own precedence and semantics

If configured with:

~~~bash
java -Xms256m -Xmx768m -jar application.jar
~~~

then explicit Xmx determines maximum Java heap within applicable JVM options. In that case, MaxRAMPercentage is generally no longer used to select maximum heap for that process.

Crucially, setting Xmx to 768 MiB in a 1 GiB container **does not guarantee safety**. Native memory plus other memory charges can push cgroup usage past 1 GiB.

### 11.3. Do not size heap from host RAM when the container is constrained

If a host has 64 GiB and the container has 1 GiB, a non-container-aware JVM may size ergonomic heap against host RAM. The application can then be OOM-killed by the kernel before Java heap even reaches the JVM's chosen maximum.

With a container-aware JDK, container-limit-based heap sizing is much more sensible, yet you still must leave headroom for non-heap memory. Never expect the JVM to automatically account for every native allocator and application memory consumer.

## 12. Total non-heap JVM memory

A simple capacity breakdown:

~~~text
Container memory limit
       │
       ├── Java heap committed/resident
       ├── Metaspace + class metadata
       ├── Code cache/JIT compiler
       ├── Thread stacks
       ├── Direct/off-heap buffers
       ├── JVM/GC native structures
       ├── JNI/JNA/FFM libraries and allocations
       ├── TLS/native compression/IO allocators
       └── Page cache and related kernel charges
~~~

This diagram shows components that can affect memory accounting, not an exact additive equation across separately read metrics. Some items already appear in RSS or are accounted differently depending on kernel behavior; avoid double-counting numbers across JVM NMT, process RSS, and cgroup usage.

### 12.1. Metaspace

Metaspace primarily stores class metadata and can grow with class loading, dynamic proxies, application reloads, or classloader leaks.

If a framework upgrade increases the number of loaded classes, native memory can rise even when heap settings stay unchanged.

### 12.2. Thread stacks

Each JVM/OS thread carries a stack and associated structures. Applications creating thousands of platform threads can consume substantial memory outside the Java heap.

The Xss flag controls stack size within applicable limits, though lowering Xss arbitrarily can trigger StackOverflowError; raising thread counts increases not just CPU contention but also memory consumption.

Virtual threads have a different stack model from platform threads, yet they still carry memory, scheduling, and carrier-thread overhead; never assume unlimited virtual threads are free.

### 12.3. Direct buffers and native libraries

Networking frameworks can use direct memory. Native libraries or FFM/JNI can allocate memory invisible to JVM heap metrics.

In some HotSpot scenarios, -XX:MaxDirectMemorySize bounds certain JVM-managed direct buffer allocations, but it is not a hard cap on **every** native malloc or JNI allocation.

If your system uses Netty, Arrow, native database drivers, or memory-mapped data, consult each dependency's specific memory management documentation.

### 12.4. Cgroup usage vs. process RSS

Process RSS offers one view of a process's resident pages; cgroup memory.current reflects usage accounted by the memory controller, which can include page cache and kernel memory. Thus the two numbers need not match.

When investigating OOMs, review all of:

- JVM heap used/committed/max.
- Native Memory Tracking if available.
- Process RSS and memory maps.
- Cgroup memory.current/events and memory.stat.
- Pod/container memory metrics from monitoring systems.

Do not simply sum RSS across multiple processes and assume it equals memory.current, because shared pages and controller accounting follow distinct rules.

## 13. Distinguishing Java OutOfMemoryError from container OOM kill

These two events differ in both consequence and diagnostic evidence.

### 13.1. OutOfMemoryError inside the JVM

Example:

~~~text
java.lang.OutOfMemoryError: Java heap space
~~~

This is an exception thrown by the JVM when it cannot allocate in Java heap given limits and GC conditions. Depending on process setup and flags, logs or a heap dump may be generated. Other OutOfMemoryError variants involve native threads, metaspace, or direct buffers.

You cannot conclude that all OutOfMemoryError occurrences are caused by a cgroup hard memory limit.

### 13.2. Container OOM kill

If the cgroup memory limit is breached and the kernel invokes the OOM killer, the Java process can be terminated by a signal without any Java exception or complete heap dump.

In Kubernetes, container status may report:

~~~text
Reason: OOMKilled
Exit code: 137
~~~

Exit code 137 typically corresponds to termination via SIGKILL under standard exit-code conventions, yet **not every exit 137 proves OOM**. Correlate container reason, kernel events/logs, memory.events, and event timeline to confirm.

### 13.3. Branching investigation flow

~~~text
Application stops / restarts
             │
             ▼
    Java OutOfMemoryError?
        │             │
       Yes            No
        │             │
        ▼             ▼
Check heap/        Check container status,
metaspace/native   OOMKilled, signal, cgroup events
        │             │
        └──────┬──────┘
               ▼
       Compare pre-incident memory
       metrics and limits
               │
               ▼
       Choose fix for the root cause
~~~

If native memory causes a cgroup OOM, shrinking the heap may create temporary headroom without fixing a native leak. Conversely, if the heap is too small and causes GC thrashing or OutOfMemoryError, increasing Xmx may be necessary—but is safe only when total container memory budget suffices.

## 14. JVM observation tools

### 14.1. From the Java API

A self-contained example:

~~~java
public final class ResourceSnapshot {
    private static double mib(long bytes) {
        return bytes / 1024.0 / 1024.0;
    }

    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();

        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("os.name=" +
                System.getProperty("os.name"));
        System.out.println("os.arch=" +
                System.getProperty("os.arch"));
        System.out.println("availableProcessors=" +
                runtime.availableProcessors());
        System.out.printf("heap.max.MiB=%.1f%n",
                mib(runtime.maxMemory()));
        System.out.printf("heap.committed.MiB=%.1f%n",
                mib(runtime.totalMemory()));
        System.out.printf("heap.freeWithinCommitted.MiB=%.1f%n",
                mib(runtime.freeMemory()));
    }
}
~~~

Meaning of the output fields:

- availableProcessors: effective processor count as determined by the JVM.
- maxMemory: maximum heap limit reported by Runtime, not the container memory limit.
- totalMemory: heap currently allocated/committed by the JVM per Runtime semantics.
- freeMemory: free space inside the currently committed heap, not free RAM in the container.

To retrieve heap used/committed/max through management APIs, you can use java.lang.management.MemoryMXBean; those metrics still do not capture full native memory or cgroup limits.

### 14.2. -XshowSettings:system

On JDKs supporting this option, you can run:

~~~bash
java -XshowSettings:system -version
~~~

Output may contain container/cgroup metrics such as provider, memory limit, and effective CPU count. Formatting, output fields, and availability vary across JDK releases and vendors, so verify against the JDK you deploy.

If a JVM does not recognize the option, do not infer that the kernel lacks cgroups; the JDK build simply may not provide that reporting flag.

### 14.3. JVM unified logging

On supporting HotSpot JDKs:

~~~bash
java -Xlog:os+container=trace -version
~~~

These logs show how the JVM detects cgroups, quota, cpuset, and memory limits. Supported tags and levels vary by JDK update; check java -Xlog:help or your chosen runtime's documentation to verify.

When enabling trace logging in production, manage log volume and avoid exposing unnecessary host metadata.

### 14.4. jcmd

On a JDK that includes jcmd with appropriate attach permissions:

~~~bash
jcmd
jcmd <pid> VM.flags
jcmd <pid> VM.info
~~~

These commands inspect active JVM flags, JVM info, and relevant implementation details. Not all commands succeed in minimal containers or environments restricting attach; minimal JRE runtime images may omit jcmd altogether.

### 14.5. Native Memory Tracking

If your HotSpot JDK supports Native Memory Tracking (NMT), launch with:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Then run:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT categorizes native memory tracked by HotSpot, though it carries overhead and **does not cover allocations performed by external native libraries**. Never use NMT total as a sole substitute for cgroup memory.current or process RSS.

Some runtime flags and NMT modes must be configured at JVM startup; do not assume every setting can be enabled dynamically later.

## 15. Docker: minimal experiment

You can compare JVM behavior inside an organization-approved Linux JDK image, for instance an illustrative image:

~~~bash
docker run --rm --cpus=1.5 --memory=1g eclipse-temurin:21-jdk \
    java -XshowSettings:system -version
~~~

The goal is to observe the JDK inside a container with explicit CPU quota and memory limit. This command assumes the Docker host/runtime supports these flags and a suitable image version; this does not represent observed command output.

### 15.1. Comparing unlimited and limited runs

Example:

~~~bash
docker run --rm eclipse-temurin:21-jdk java -version

docker run --rm --cpus=1 --memory=512m \
    eclipse-temurin:21-jdk \
    java -XshowSettings:system -version
~~~

Omitting explicit flags on the first docker run does not guarantee the container gets all host resources: parent cgroup policies, the Docker Desktop VM, runtime defaults, and platform quotas still apply.

### 15.2. Inspecting cgroups inside a container

~~~bash
docker run --rm --cpus=1.5 --memory=1g \
    --entrypoint sh eclipse-temurin:21-jdk \
    -c 'cat /proc/self/cgroup; ls /sys/fs/cgroup'
~~~

If the image includes a shell and basic utilities, this shows which cgroup layout is mounted. Minimal or distroless images may lack sh, cat, and ls; use an appropriate debug image or collect metrics from within the application.

### 15.3. Sizing Xmx inside a container

Example:

~~~bash
docker run --rm --memory=1g eclipse-temurin:21-jdk \
    java -XX:MaxRAMPercentage=60.0 -XshowSettings:vm -version
~~~

The goal is to see the JVM's ergonomic heap sizing under a 1 GiB limit. Do not treat 60% as optimal for every workload; perform dedicated benchmarking, native headroom sizing, and capacity planning.

### 15.4. Docker Desktop, VM, and host OS

On Windows and macOS, Docker Desktop typically runs Linux containers inside a VM or virtualization layer. The container's Linux kernel and cgroups live inside that Linux environment, which does not equal the total RAM and CPUs of the desktop host.

When comparing observations:

- Check Docker Desktop VM resource limits.
- Check container --cpus and --memory settings.
- Inspect the JDK inside the Linux image, not the external Windows/macOS JDK.
- Never compare host lscpu directly against container Runtime.availableProcessors while ignoring the VM and cgroup layers.

## 16. Kubernetes: observing from Pod to node

### 16.1. Checking requests and limits

~~~bash
kubectl describe pod <pod-name> -n <namespace>
kubectl get pod <pod-name> -n <namespace> -o yaml
~~~

Replace placeholders with real environment values. Only operate in permitted clusters and test namespaces.

Verify:

- Requests and limits in the Pod spec.
- LimitRange/ResourceQuota if enforced by the cluster.
- RuntimeClass, CPU manager policy, or relevant cpuset assignments.
- Pod QoS class and container state.
- Container image tag/digest and JDK vendor/version.

### 16.2. Inspecting actual usage

~~~bash
kubectl top pod <pod-name> -n <namespace> --containers
~~~

This requires working metrics infrastructure. The output shows point-in-time or windowed CPU/memory usage; it is not a replacement for cgroup quotas, JVM heap metrics, or OOM root-cause analysis.

### 16.3. Checking OOMs and restarts

~~~bash
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
~~~

--previous returns data only if the runtime retains logs from the terminated container. If the kernel killed the process, Java logs may cut off abruptly without an OutOfMemoryError.

Check:

- Last State / Reason / Exit Code.
- Events in the namespace/pod.
- Cgroup memory.events or container runtime metrics.
- Node pressure, eviction, and deployment rollout events.

Kubernetes eviction due to node memory pressure differs from a container hitting its cgroup hard memory limit; never lump every pod restart under "Java OOM."

## 17. CPU throttling and GC latency

CPU quota does not merely throttle application worker threads. GC, JIT compilation, and runtime background tasks need CPU time too.

Example:

~~~text
Container has a low CPU limit
        │
        ▼
Application + GC + JIT contend for quota
        │
        ▼
Quota exhausted within period
        │
        ▼
CPU throttling
        │
        ▼
Response latency rises, queues fill up
        │
        ▼
Timeouts/retries add even more load
~~~

The result can be a feedback loop: throttling slows request handling, retries amplify incoming traffic, thread pools build backlogs, and memory pressure increases.

### 17.1. Metrics to correlate

- Container CPU usage and limit/quota.
- Cgroup nr_throttled and throttled time.
- JVM GC pause time and throughput.
- JVM compiler activity if relevant.
- Application request rate, latency p95/p99, and error rate.
- Executor queue length, active threads, and saturation.
- Memory.current and Java heap usage.

Do not conclude "GC regressed" solely because pause or latency increased on a new JDK; CPU quota or availableProcessors may have changed at the same time.

### 17.2. Evaluation approach

1. Identify effective quota/cpuset and effective processor count.
2. Replay the same representative workload and dataset against baseline and target JDKs.
3. Record throttling and GC metrics over the same time window.
4. Vary one control variable at a time: CPU limit, pool size, GC settings, or JDK.
5. Inspect throughput, latency, error rate, and memory headroom.

Raising the CPU limit can alleviate throttling if quota is genuinely the bottleneck, provided cluster capacity and cost permit. Changing ActiveProcessorCount adjusts only JVM ergonomics and grants no additional CPU entitlement.

## 18. Commonly relevant JVM options

| JVM option | Typical meaning | Risk if misused |
|---|---|---|
| -XX:+UseContainerSupport | JVM inspects container/cgroup info where supported by implementation. | Not guaranteed on all older JDKs; semantics vary by version. |
| -XX:-UseContainerSupport | Disables container awareness on JDKs supporting the flag. | JVM may size from host resources and exceed container limits. |
| -XX:ActiveProcessorCount=N | Overrides processor count used by the JVM for certain decisions. | Setting too high boosts parallelism/throttling without adding real CPU. |
| -XX:MaxRAMPercentage=P | Controls ergonomic maximum heap as a percentage of baseline RAM. | Setting P too high starves native headroom. |
| -XX:InitialRAMPercentage=P | Controls ergonomic initial heap percentage in applicable configs. | Overly large initial heap hurts startup or footprint fit. |
| -XmxSIZE | Sets explicit maximum heap size. | Setting equal to memory limit risks container OOM kill. |
| -XmsSIZE | Sets initial heap size. | Overly large Xms increases initial footprint. |
| -XssSIZE | Sets stack size for platform threads where applicable. | Too low causes stack overflow; too high inflates memory usage. |
| -XX:MaxDirectMemorySize=SIZE | Caps certain direct buffer allocations per implementation. | Does not block all native allocations. |
| -XX:NativeMemoryTracking=summary | Enables HotSpot native memory accounting at summary level. | Adds overhead; excludes allocations from external native libraries. |

Not every HotSpot flag exists or carries identical semantics across all JDKs and vendors. When running OpenJ9 or other JVMs, consult their respective documentation instead of assuming HotSpot -XX: flags apply.

### 18.1. An experimental starting configuration, not a production default

~~~bash
java \
    -XX:MaxRAMPercentage=60.0 \
    -XX:ActiveProcessorCount=2 \
    -jar application.jar
~~~

This example sets an ergonomic heap percentage and processor count for controlled benchmarking. It should not be copied verbatim to 512 MiB, 1 GiB, or 16 GiB containers without measuring native memory and CPU quota.

### 18.2. Do not naively add up limits

Suppose:

~~~text
memory limit   = 1024 MiB
Xmx            = 700 MiB
MaxDirectMemory= 256 MiB
~~~

You cannot assume the remaining 68 MiB will always cover the rest of the JVM. Beyond heap and direct buffers lie Metaspace, thread stacks, code cache, native libraries, GC overhead, page cache, and other charges. Conversely, a maximum reserve need not be fully resident at every instant.

Base sizing on **peak resident/cgroup usage** under realistic workloads, leaving headroom for load spikes.

## 19. Identifying changes during JDK upgrades

A Java migration often changes multiple layers together:

~~~text
Baseline JDK / cgroups v1 / old image
             │
             ▼
Target JDK / cgroups v2 / new image
             │
             ▼
Different JVM ergonomics and runtime observations
~~~

If you upgrade the JDK while simultaneously switching node OS or cgroup hierarchy, it becomes hard to attribute behavioral differences to the JDK alone.

### 19.1. Questions to answer before migration

1. What are the before/after runtime JDK version, update, and vendor?
2. Is the Linux container using cgroups v1 or v2?
3. Does the target JDK support that cgroups mode in the chosen implementation?
4. In which cgroup are limits actually enforced, and are ancestor limits active?
5. What is Runtime.availableProcessors() before and after?
6. What are effective Runtime.maxMemory() and Xmx before and after?
7. Did any JVM flags, GC algorithm, or thread pool settings change?
8. How do CPU throttling and memory events compare before and after?
9. Did off-heap, native, or agent footprint increase alongside framework upgrades?
10. Did container image, OS kernel, or libc change?

### 19.2. Identical settings can still behave differently

Suppose both images specify:

~~~text
CPU limit    : 1500m
Memory limit : 1Gi
~~~

yet an older JVM failed to detect cgroups v2 accurately while the target JVM succeeds. Effective processor count or ergonomic heap can change even without a single change in YAML.

This is not necessarily a regression in the new JDK; the new JDK may simply be honoring limits more accurately. Re-evaluate GC, thread pools, and memory budgeting against actual available resources.

## 20. Resource testing matrix in CI

A test matrix should cover:

| Scenario | CPU limit/cpuset | Memory limit | What to observe |
|---|---|---|---|
| Container without explicit hard limit | No explicit limit | No explicit limit | How does the JVM interpret host/ancestor constraints? |
| Fractional CPU | 500m | 1Gi | availableProcessors, throttling, latency. |
| CPU 1.5 | 1500m | 1Gi | CPU quota, GC threads, request throughput. |
| Narrow cpuset | 2 logical CPUs | 1Gi | Does the JVM respect affinity/cpuset accurately? |
| Small memory | 1 CPU | 512Mi | Heap size, native memory, startup, and OOM risk. |
| Large memory | 2 CPUs | 4Gi | Heap ergonomics, GC, and memory headroom. |
| Cgroups v1 | Per environment | Per environment | Controller files and JVM detection. |
| Cgroups v2 | Per environment | Per environment | cpu.max/memory.max and JVM detection. |

These cells illustrate test design; not every CI runner allows switching cgroup versions dynamically. Pre-provisioned nodes, VMs, or dedicated container environments may be needed.

### 20.1. Evidence to record per test run

Record at minimum:

- JDK vendor, version, update, and JVM flags.
- Kernel, container runtime, and cgroups version.
- Container image digest and node architecture.
- CPU request/limit, cpuset, cpu.max, or CFS quota/period.
- memory.max or memory.limit_in_bytes and relevant ancestor limits.
- JVM availableProcessors, heap max/committed, and GC configuration.
- Throughput, latency, CPU throttling, and memory.current/events.
- Test dataset, concurrency, duration, and results.

Do not archive secrets or full environment variables. Record only needed metadata and strip sensitive values.

### 20.2. Load-test scenarios

Simply starting the JVM and printing Runtime.maxMemory does not validate capacity:

1. Run a light workload to confirm startup.
2. Run load representative of production.
3. Run peak or soak tests when warranted.
4. Measure GC, off-heap, RSS, throttling, and OOM events.
5. Exercise failure paths such as retry storms or large batches.

Memory leaks or CPU throttling may emerge only after sustained load. Keep startup checks, stress runs, and production observations clearly separated in records.

## 21. Autoscaling and resource policy risks

Kubernetes Horizontal Pod Autoscaler or similar autoscalers can scale on CPU utilization, custom metrics, and target settings. Changing CPU requests alters request-relative CPU utilization even when absolute CPU usage has not changed.

Example:

~~~text
CPU usage observed = 400m
CPU request old    = 400m → 100% of request
CPU request new    = 800m → 50% of request
~~~

This shows how percentages shift when HPA computes utilization relative to requests; real autoscaling also depends on metric availability, tolerance, windows, and policy setup.

Consequently, changing requests.cpu just to "fix JVM availableProcessors" can alter scheduling and autoscaling, not merely thread pools. Coordinate with the platform team when adjusting resource policy.

### 21.1. Memory limits, OOM, and autoscaling

Adding replicas does not solve a per-JVM memory leak. If every container hits a workload or heap peak past its hard limit, individual replicas can still be OOM-killed.

Conversely, increasing the memory limit can prompt the JVM to choose a larger heap under MaxRAMPercentage, changing GC footprint and scheduling. Whenever Kubernetes resources change, re-verify ergonomic heap size rather than assuming Xmx stayed constant.

## 22. Sample investigation scenarios

### 22.1. Newer Java shows higher CPU utilization and lower throughput

Symptoms:

~~~text
Host: 32 CPUs
Container CPU limit: 1 CPU
New JDK: Runtime.availableProcessors=1
Application: p99 latency increases under high load
~~~

Steps:

1. Check actual cpu.max or quota/period.
2. Read cpu.stat to confirm throttling.
3. Compare baseline and target JDKs, GC logs, and thread pool settings.
4. Check request rate, retry behavior, and saturation.
5. If quota is the bottleneck, evaluate increasing the CPU limit or optimizing workload/concurrency.

Never default to setting ActiveProcessorCount=32 just to make the JDK look like the host; quota still grants only about 1 CPU worth of total time.

### 22.2. JVM heap is not full yet container is OOMKilled

Suppose:

~~~text
Container memory limit: 1024 MiB
Java heap used peak:     550 MiB
Container memory peak:  1024+ MiB
Outcome:                OOMKilled
~~~

These figures illustrate only one possible cause.

Investigate:

- Committed and maximum heap, not just heap used.
- Native Memory Tracking if supported.
- Thread counts/stacks.
- Direct/off-heap buffers and JNI/native libraries.
- Cgroup memory.stat and container memory metrics.
- Page cache or file mappings.

If off-heap or natively allocated memory is the major driver, tuning Java heap alone may fail to resolve the root cause.

### 22.3. Upgrading JDK on a cgroups v2 node changes heap size

An application previously ran on an older runtime with a 2 GiB container limit, while the JVM saw a 64 GiB host. After upgrading the JDK, the JVM detects 2 GiB more accurately and ergonomic Xmx drops noticeably.

This can:

- Lower the risk of container OOM kills.
- Increase GC frequency if the workload previously relied on heap larger than the true container limit.
- Require selecting an Xmx suited to native memory headroom.

Inspect actual JDK and container specs and run load tests rather than hastily disabling UseContainerSupport to revert to old behavior.

### 22.4. CPU request increases while CPU quota stays unchanged

Container:

~~~text
requests.cpu: 250m → 500m
limits.cpu  : 1000m (unchanged)
~~~

Hard CPU quota may remain equivalent to 1 CPU. However, relative scheduling weight, Kubernetes scheduling, or HPA behavior can change. JVM availableProcessors may also depend on the JDK's container accounting implementation.

To determine true impact, measure quota, shares/weight, active processors, throttling, and scaling behavior together.

## 23. Common misconceptions

| Misconception | Why it is wrong | How to handle it |
|---|---|---|
| Container sees 64 host CPUs so JVM gets 64 CPUs. | Cgroup quota/cpuset may restrict it. | Read cgroups and availableProcessors on the real JVM. |
| CPU requests equal CPU limits. | Requests are not hard quotas; limits can use quotas. | Separate scheduling/weight from quota. |
| CPU weight 100 equals 1 core. | Weight is relative priority, not a fixed core equivalent. | Evaluate quota/cpuset and contention. |
| availableProcessors=2 means 2 dedicated CPUs. | It is a number the JVM uses for ergonomics, not a CPU reservation. | Measure usage/throttling and host scheduling. |
| ActiveProcessorCount=8 adds CPU to a 1-CPU container. | The flag does not alter kernel quota. | Choose concurrency according to real capacity. |
| Xmx of 1 GiB is safe in a 1 GiB container. | The JVM also consumes native/non-heap and other accounted memory. | Reserve headroom and measure peak usage. |
| Runtime.freeMemory is free container RAM. | It represents free space inside currently allocated heap. | Check cgroup memory.current and OS metrics. |
| Java OutOfMemoryError and OOMKilled are the same thing. | A JVM exception differs from a kernel/container kill. | Classify using logs, status, and cgroup events. |
| memory.max=max means no limits exist anywhere. | Ancestor cgroups or node limits may still apply. | Inspect the hierarchy and effective constraints. |
| With cgroups v2, every JDK supports it identically. | JDK updates, vendors, and backports differ. | Verify with the actual JDK binary. |
| All Linux containers place files at the same paths. | Mount namespaces and cgroup layouts vary. | Read /proc/self/cgroup and mountinfo. |
| Heap max represents total RSS. | Native memory, direct buffers, and page cache are excluded. | Combine heap, NMT, RSS, and cgroup metrics. |
| CPU throttling affects only business threads. | GC, JIT, and runtime threads also need CPU. | Correlate GC/latency with cgroup cpu.stat. |
| HPA automatically fixes per-container memory leaks. | Scaling out does not eliminate leaks inside each replica. | Investigate memory profiles and fix the leak. |
| Running fine in local Docker means production Kubernetes behaves identically. | Kernel, cgroups, VM, and limits differ. | Test against the target topology and resource policy. |

## 24. Container JVM migration workflow

### Step 1 — Collect baseline

Record JDK vendor/version/update, JVM flags, Gradle/runtime artifact, image digest, host/kernel, cgroups version, and resource requests/limits. Capture availableProcessors, Xmx, CPU quota/cpuset, and memory limits.

### Step 2 — Verify effective cgroups

Read /proc/self/cgroup and mountinfo. For v1, inspect quota/period and memory.limit_in_bytes; for v2, inspect cpu.max, cpuset.cpus.effective, memory.max, and memory.events. Check ancestor limits as needed.

### Step 3 — Confirm JVM container awareness

Inspect java -XshowSettings:system, -Xlog:os+container=trace, or another diagnostic method supported by your JDK. Do not assume all JDK vendors or updates share identical behavior.

### Step 4 — Determine heap/native budget

Choose Xmx/MaxRAMPercentage appropriate to the memory limit and peak native footprint. Measure GC, thread stacks, direct buffers, Metaspace, and cgroup memory usage.

### Step 5 — Evaluate CPU ergonomics

Inspect availableProcessors, GC thread counts, ForkJoinPool, executor pools, and CPU throttling. Do not tune ActiveProcessorCount based solely on host CPUs.

### Step 6 — Run baseline and target with identical workload

Keep dataset, concurrency, requests/limits, image topology, and resource metrics as consistent as possible. If switching cgroups v1 to v2 simultaneously, document this as an independent variable.

### Step 7 — Adjust one variable at a time

If regression occurs, change only one parameter group per iteration: JDK, heap percentage/Xmx, CPU limit, thread pool, or GC. Save before/after results to avoid confusing correlation with causation.

### Step 8 — Test failures and limits

Run peak-load workloads and verify there are no unexpected OOMKilled events; inspect throttling, timeouts, queue backlogs, GC pauses, and memory.events.

### Step 9 — Deploy with monitoring

Roll out via canary or production-like staging, monitoring latency, GC, heap/native memory, cgroup memory, CPU throttle, pod restarts, OOMKilled, and HPA behavior.

### Step 10 — Publish operational baseline

Document JVM flags, supported JDK runtime, resource requests/limits, native headroom, metrics, and rollback conditions for each workload type.

## 25. Post-migration resource report template

A report may record:

~~~text
Service:
Artifact / image digest:
JDK vendor + version + update:
OS/kernel/container runtime:
cgroups mode: v1 / v2 / mixed

Kubernetes/Docker configuration:
  CPU request:
  CPU limit:
  Cpuset / affinity:
  Memory request:
  Memory limit:
  Swap configuration:

Effective controller observations:
  cpu quota / period:
  cpu weight/shares:
  cpuset effective:
  memory hard limit:
  memory current/peak:
  throttling counters:
  OOM/memory.events:

JVM observations:
  availableProcessors:
  UseContainerSupport:
  ActiveProcessorCount override:
  Xms:
  Xmx / Runtime.maxMemory:
  MaxRAMPercentage:
  GC and thread configuration:
  Heap used/committed:
  Native memory estimate:

Load-test evidence:
  workload / concurrency / duration:
  throughput:
  p95/p99 latency:
  GC metrics:
  CPU throttling:
  OOM / restarts:
  pass/fail and open risks:
~~~

This is a structural template for recording real project measurements. Do not fill in hypothetical results as though CI/production had been tested. Protect sensitive configuration details per organizational policy.

## 26. Conclusion

Inside a container, **effective JVM CPU and memory are not simply host CPU and RAM**. Cgroups v1/v2 enforce CPU quota, cpuset, shares/weight, memory hard/high limits, and distinct accounting rules. JVM container awareness lets supporting HotSpot releases inspect this information for processor counts and ergonomic heap/GC decisions, though support still depends on JDK vendor, update, kernel, and runtime.

To upgrade Java safely, distinguish CPU requests from hard limits and check throttling rather than CPU usage alone; distinguish Java heap from total container memory; recognize that OutOfMemoryError differs from OOMKilled; and measure JVM flags, Runtime.availableProcessors, Runtime.maxMemory, and cgroup files directly in the deployment environment.

**Do not treat a single processor count or a fixed MaxRAMPercentage as a universal formula for every container.** Controlled migration requires a JDK–cgroups–CPU–memory test matrix, benchmarks and integration tests with representative load, measurement of peak native memory, GC, and latency, and documentation of the actually supported runtime configuration. When this evidence is stored alongside artifacts and deployment policies, teams can move JDKs or containers without inadvertently changing throughput, OOM behavior, or service quality.
