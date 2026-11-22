# Cgroups, CPU, and Available Memory in the Target Environment

CRaC (Coordinated Restore at Checkpoint) makes it possible to restore a Java process from a previously prepared state. However, a successful restore does not depend only on the checkpoint image and the JDK. The process must also run in an environment with suitable resources: allowed CPUs, CPU time limits, memory, swap, process/thread counts, and limits imposed by the container or orchestrator.

On Linux, cgroups (control groups) are the kernel mechanism used to track and limit the resources of a group of processes. Container runtimes and Kubernetes typically use cgroups to enforce CPU limits, memory limits, and several other constraints. Modern JVMs can detect some container limits to adjust the heap, the number of processors visible to the JVM, and runtime decisions. However, how this detection behaves depends on the JDK, vendor, version, and configuration.

When creating a checkpoint in a source environment and then restoring it in a target environment, CPU and memory limits can differ. The JVM has already started and made ergonomics decisions before the checkpoint; you should not assume all of those decisions will be recalculated as in a fresh startup. If the target environment is smaller, the process may suffer throttling, insufficient GC time, native memory exhaustion, or termination by the cgroup OOM killer. If the target environment is larger, the maximum heap and already created thread pools may still retain their previous sizes.

Therefore, it is necessary to inspect the actual cgroups limits at the restore location, compare them against the JVM configuration and application footprint, and test under the exact resource limits planned for deployment.

## 1. Cgroups and Container Resource Limits

Cgroups are a Linux kernel mechanism for organizing processes into groups and applying resource accounting or limits. A container is usually placed in a cgroup or a branch of the cgroup tree. Controllers can manage:

- CPU: allocated CPU time, priority weights, and the set of CPUs allowed to run on.
- Memory: amount of memory used, reclaim thresholds, and maximum limits.
- PIDs: number of processes/threads that can exist in the group.
- I/O: bandwidth or number of I/O operations depending on the controller and kernel.
- Cpuset: CPUs or NUMA nodes that processes are allowed to use.

A cgroup is not a virtual machine with dedicated physical CPU and RAM. It is a kernel mechanism that controls and accounts for processes in a shared system. Two containers can share physical CPUs, while each container has its own quota, weight, or cpuset.

In a container environment, seeing the host's CPU count does not mean the process is allowed to use all of those CPUs. Similarly, the machine's total RAM is not the memory the container is permitted to use.

## 2. Cgroups v1 and Cgroups v2

Linux has two generations of cgroups:

- **cgroups v1:** Controllers can be mounted in separate hierarchies. CPU, memory, and cpuset can reside at different mount points.
- **cgroups v2:** Uses a unified hierarchy with controllers enabled per subtree. Control files have more standardized names and semantics.

A system may use v1, v2, or a hybrid configuration depending on the kernel and runtime. Do not assume every Linux machine has the same paths or the same files.

| Topic | cgroups v1 | cgroups v2 |
|---|---|---|
| CPU quota | cpu.cfs_quota_us, cpu.cfs_period_us | cpu.max |
| CPU weight/share | cpu.shares | cpu.weight |
| CPU set | cpuset.cpus, may need to check effective set | cpuset.cpus.effective along with cpuset files |
| CPU statistics | cpu.stat | cpu.stat |
| Memory current | memory.usage_in_bytes | memory.current |
| Memory limit | memory.limit_in_bytes | memory.max |
| Memory high/reclaim boundary | Depends on controller and kernel, no exact equivalent interface | memory.high |
| Memory events | memory.failcnt, some event files depending on kernel | memory.events, memory.events.local |
| Memory + swap | memory.memsw.* if enabled | memory.swap.max, memory.swap.current |

Files may not appear if a controller is not enabled, the kernel does not support it, or the container namespace exposes only part of the hierarchy. Determine the cgroup version and actual path before reading values.

## 3. Identifying the Cgroup of a Running Process

Do not simply read a file under /sys/fs/cgroup and conclude that it is the process's limit. In a nested hierarchy, limits on an ancestor can apply to the container even if the child cgroup sets no limit of its own. The container runtime may also mount a cgroup namespace that makes the visible path differ from the host.

Start with:

~~~bash
cat /proc/self/cgroup
cat /proc/self/mountinfo
~~~

/proc/self/cgroup shows which cgroup path the current process belongs to. /proc/self/mountinfo shows where the cgroup filesystem is mounted and which mount root is visible. From these two pieces of information, identify the exact directory containing the controller files.

You can also inspect:

~~~bash
mount | grep cgroup
findmnt -t cgroup,cgroup2
~~~

In cgroups v2, a line in /proc/self/cgroup typically has the form 0::/some/path. If cgroup2 is mounted at /sys/fs/cgroup, the process path may lie beneath that mount point. However, inside a cgroup namespace, a process may see its own cgroup as root /; therefore, cross-check the mount root in mountinfo.

In cgroups v1, each controller may have a different path and mount point. For example, the CPU controller and memory controller might not reside in the same directory.

## 4. CPU Quota, Period, and CPU Capacity

CPU quota limits the total CPU time a cgroup is allowed to use within a period. With cgroups v1, quota and period are typically located in:

- cpu.cfs_quota_us
- cpu.cfs_period_us

With cgroups v2, both values are typically located in cpu.max with the format:

~~~text
<quota> <period>
~~~

For example:

~~~text
50000 100000
~~~

This means the cgroup can use at most 50,000 microseconds of CPU in each 100,000-microsecond period. The equivalent ratio is an average of 0.5 CPU time according to that quota. A value of max 100000 means no CPU quota is set on the current cgroup; it may still be limited by an ancestor or cpuset.

Another example:

~~~text
200000 100000
~~~

This is equivalent to at most about two CPUs of time per period, provided the cgroup has enough allowed CPUs and is not limited by an ancestor.

The quota/period ratio is not a number of dedicated physical cores for the container. It is an aggregate CPU time limit. A container with a quota equivalent to 1.5 CPUs can run concurrently on multiple cores during part of a period and then be throttled once it exhausts the quota.

## 5. Cpuset and Allowed CPUs

Quota is not the only factor determining CPU capacity. Cpuset restricts the set of CPUs on which processes can run.

In cgroups v2, inspect the files cpuset.cpus and cpuset.cpus.effective. The actual path depends on the cgroup directory. cpuset.cpus.effective reflects the effective CPU set the cgroup can use after considering hierarchy constraints. In cgroups v1, you may encounter cpuset.cpus and related files.

Example value:

~~~text
2-5
~~~

This indicates that logical CPUs with IDs 2, 3, 4, and 5 are in the cpuset. If the quota is only equivalent to one CPU, being allowed to run on four CPUs does not mean being able to use all four CPUs continuously.

A process's CPU capacity must be evaluated by considering all of the following together:

- CPU quota on the current cgroup.
- Quotas on ancestor cgroups.
- Effective cpuset.
- Actual CPUs available on the host.
- Contention with other workloads.
- CPU weight/share when contention occurs.

You cannot take nproc or the host CPU count in isolation and use it as the optimal worker limit.

## 6. CPU Weight and Shares Are Not Hard Limits

cpu.weight in cgroups v2 and cpu.shares in cgroups v1 represent relative weights when multiple cgroups contend for CPU. They are not the same as CPU quota.

For example, two containers both have no quota but have different weights. When CPU is idle, both can use plenty of CPU. When the host is overloaded, the cgroup with the higher weight can receive a larger share of CPU according to the kernel's distribution mechanism.

| Mechanism | Effect | Does it set a hard CPU ceiling? |
|---|---|---|
| CPU quota | Limits CPU time per period | Yes |
| Cpuset | Restricts allowed logical CPUs | Restricts CPU set, not time quota |
| CPU weight/share | Relative weight during contention | No |
| Kubernetes CPU request | Information for scheduling and corresponding allocation configuration | Not a CPU limit |
| Kubernetes CPU limit | Usually enforced by the runtime using quota | Yes, depending on runtime/kernel configuration |

CPU request and CPU limit in Kubernetes serve different roles. Request affects scheduling and certain resource allocation decisions; it does not mean the container always gets exclusive use of that number of CPUs. Limit is usually enforced using CPU quota. Check the actual cgroup instead of just reading YAML.

## 7. CPU Throttling and Impact on Java

When a cgroup uses up its quota within a period, the kernel can throttle tasks until the next period. The process remains alive but cannot run on the CPU for part of the time.

In cgroups v2, cpu.stat typically provides metrics such as:

- usage_usec: CPU time used.
- user_usec: CPU time in user mode.
- system_usec: CPU time in kernel mode.
- nr_periods: number of quota periods.
- nr_throttled: number of throttled periods.
- throttled_usec: total time throttled.

Field names and sets may vary by kernel. Use them to observe throttling trends rather than inferring exact latencies from a single reading.

CPU throttling affects Java applications in several ways:

- Request threads process more slowly and p95/p99 latency increases.
- The Garbage Collector gets less CPU time to complete its work.
- The JIT compiler and class loading can take longer.
- Executor queues grow because workers cannot keep up.
- Schedulers and heartbeats may be delayed.
- Threads renewing leases, running health checks, or handling service discovery may not execute at the expected time.
- Operations with short timeouts may fail even when external dependencies are healthy.

After restore, if the CPU quota is lower than in the checkpoint creation environment, the application may take longer to reach readiness. A thread pool created with a large size based on the CPU count at the source can create too many runnable threads relative to the actual CPU time at the target.

## 8. How Does the JVM Detect Container CPUs?

HotSpot on modern versions has container awareness on Linux. Depending on the version, the JVM can inspect cgroup CPU quota, cpuset, and container information to decide the number of available processors for certain ergonomics calculations.

Several points need to be distinguished:

- Runtime.getRuntime().availableProcessors() returns the number of processors the JVM reports as available to the application.
- The host CPU count from nproc, lscpu, or /proc/cpuinfo may be larger than the processor count the JVM detects.
- Fractional quotas such as 0.5 CPU are not necessarily represented directly as half a processor in an API returning an integer.
- Rounding behavior and how quota/cpuset are evaluated depend on the JDK version and implementation.
- CPU weight/share is not necessarily treated as a processor count.
- The -XX:ActiveProcessorCount=N flag can override the number of processors the JVM uses for ergonomics on JDKs that support this flag.

On modern HotSpot, container support is usually enabled by default on Linux, but this should be verified with the exact JDK. Older Java versions or other distributions may behave differently.

You can check with:

~~~bash
java -XshowSettings:system -version
~~~

Depending on the JDK, this command displays the system/container information detected by the JVM. You can enable container logging at startup if the JVM build supports the corresponding tag:

~~~bash
java -Xlog:os+container=trace -version
~~~

Check the JDK documentation if this unified logging tag or option is not supported. Inside an application, you can log:

~~~java
public final class RuntimeCapacity {
    public static void logCapacity() {
        Runtime runtime = Runtime.getRuntime();

        System.out.println("availableProcessors="
                + runtime.availableProcessors());
        System.out.println("maxHeapBytes="
                + runtime.maxMemory());
        System.out.println("totalHeapBytes="
                + runtime.totalMemory());
        System.out.println("freeHeapBytes="
                + runtime.freeMemory());
    }
}
~~~

This shows what the JVM sees; it does not replace reading the cgroup. maxMemory() reflects the JVM's maximum heap, not the container's total memory limit.

## 9. ActiveProcessorCount and CPU-Dependent Decisions

Many JVM components use the processor count to choose concurrency levels:

- The Garbage Collector chooses the number of GC workers.
- ForkJoinPool can use the processor count to compute its default parallelism.
- Some frameworks or libraries automatically choose thread pool sizes.
- The JIT and runtime tasks adjust concurrency levels.
- Applications may compute worker counts based on availableProcessors().

If the JVM sees too many CPUs compared to the actual quota, the application may create more threads than the CPU time can sustain. This increases context switching, lock contention, stack memory, and queueing. If the JVM sees too few CPUs, throughput may be low even when the target environment has more CPUs.

The -XX:ActiveProcessorCount=N flag can help set the number of processors the JVM uses for ergonomics decisions, but it does not change the cgroup's CPU quota. Setting a value higher than the actual limit does not create extra CPU time; setting it too low can unnecessarily reduce parallelism.

For example:

~~~bash
java -XX:ActiveProcessorCount=2 -jar app.jar
~~~

Use this flag only after measuring and verifying. If the CPU quota varies by workload or environment, consider configuring it per deployment rather than hardcoding a single global value.

## 10. Memory Cgroup: current, high, and max

Cgroups v2 provides commonly used memory files:

- memory.current: current amount of memory accounted to the cgroup.
- memory.max: hard limit; max means no limit is set at this level.
- memory.high: pressure/reclaim threshold; when exceeded, the kernel can trigger reclaim/throttling to reduce usage.
- memory.events: event counters such as high, max, oom, and oom_kill depending on the kernel.
- memory.stat: breakdown of memory usage categories.
- memory.swap.current and memory.swap.max: swap status and limit if the controller is enabled.

For example:

~~~text
memory.current = 805306368
memory.high    = 1073741824
memory.max     = 1610612736
~~~

This can be interpreted as the cgroup currently using about 768 MiB, with a high threshold of 1 GiB and a hard max of 1.5 GiB. Actual values must be converted to the proper units; the files usually express values in bytes.

memory.high is not the same as a hard limit. When high is exceeded, the kernel can reclaim memory and slow down the process. memory.max is the cgroup's hard limit; if enough memory cannot be reclaimed, the kernel may trigger OOM handling.

In cgroups v1, common files are memory.usage_in_bytes, memory.limit_in_bytes, memory.failcnt, and several memory.stat fields. Exact names and behavior depend on the kernel.

## 11. Memory Limits Can Reside in Ancestor Cgroups

A container may not have memory.max set on its child cgroup yet still be subject to a limit from a parent. For example, a Pod cgroup or systemd slice can limit the total memory of multiple containers or processes.

Therefore, limits must be checked along the entire ancestor path. The effective limit is the strictest limit applied across the hierarchy levels, along with other runtime/host limits. You should not conclude that max in a file at a child cgroup means the process has no memory limit.

In Kubernetes, it is necessary to understand limits at the container and pod levels depending on the version/runtime/configuration. A sidecar may share a limit at a higher level or have its own limit. Inspect both the orchestrator configuration and the cgroup to which the process actually belongs.

## 12. Types of JVM Memory That Count Toward the Container Limit

A cgroup's memory limit is not solely for the Java heap. A Java process can use:

- **Java heap:** Java objects and application data.
- **Metaspace:** Class metadata.
- **Code cache:** Machine code compiled by the JIT.
- **Thread stacks:** Platform thread stacks and related native regions.
- **Direct buffers:** Off-heap buffers, commonly used for I/O.
- **JNI/native libraries:** Memory allocated by native libraries.
- **GC structures:** Region metadata, remembered sets, mark bitmaps, and collector structures.
- **JVM internal memory:** Compiler, symbol tables, class metadata, and other runtime structures.
- **Native allocator and libc:** Memory allocated by malloc or library allocators.
- **Memory mapping:** File mappings and mmap regions.
- **Page cache and kernel-accounted memory:** Certain types of file cache, socket buffers, and kernel memory may be charged to the cgroup depending on the controller/kernel.

Therefore, -Xmx should not equal the entire memory.max. If the heap consumes the whole cgroup limit, the process still needs memory for the native runtime, threads, direct buffers, GC, and other components. The cgroup OOM killer can terminate the process before the JVM throws OutOfMemoryError: Java heap space.

A conceptual budget model:

~~~text
Cgroup memory limit
  |
  +-- Java heap
  +-- Metaspace and class metadata
  +-- JIT code cache
  +-- Thread stacks
  +-- Direct buffers
  +-- GC/JVM native structures
  +-- JNI / native libraries
  +-- Memory mapping / file cache / kernel accounting
  +-- Headroom for load fluctuations
~~~

Components do not necessarily add linearly or get measured identically across all kernels. Use cgroup memory metrics and JVM tools to measure under realistic workloads.

## 13. How the JVM Chooses Maximum Heap from Container Memory

HotSpot can use container memory to calculate heap ergonomics at startup. Common flags:

- -Xms: initial/minimum heap according to JVM configuration.
- -Xmx: maximum heap.
- -XX:InitialRAMPercentage: percentage of JVM-detected memory used to compute the initial heap where applicable.
- -XX:MaxRAMPercentage: maximum percentage of memory used by the JVM to compute the maximum heap.
- -XX:MaxRAM: maximum RAM value the JVM uses as the ergonomics baseline where supported.

Example configuration:

~~~bash
java -XX:MaxRAMPercentage=60 -XX:InitialRAMPercentage=25 -jar app.jar
~~~

These percentages are only examples. There is no single percentage that fits every application. Headroom must be left for native memory, thread stacks, direct buffers, metaspace, GC, and other cgroup memory.

If a fixed -Xmx is used, that value may exceed the target environment's memory limit. If MaxRAMPercentage is used, the JVM calculates based on the memory it detects at the time ergonomics are applied. Exact behavior depends on the JDK and other flags.

Specifically with CRaC, the process has already started before the checkpoint. Do not assume the JVM will recalculate all heap ergonomics as in a fresh startup when restoring into a cgroup with a different memory limit. The maximum heap and many runtime settings were already established when the JVM started. Verify the behavior of the specific CRaC JDK and design the checkpoint within a resource envelope compatible with the restore environment.

## 14. Why Restoring Into a Smaller Memory Limit Can Fail

Suppose an application is warmed up in a container with a 4 GiB memory limit and a 2.5 GiB maximum heap. The checkpoint image may reflect a heap already using 1.8 GiB, along with native memory, thread stacks, and page cache.

If restored into a container with only 2 GiB:

- Current heap plus native memory may exceed the limit as soon as the process resumes.
- The JVM may need to allocate additional memory for GC, JIT, or threads.
- The kernel may aggressively reclaim memory when memory.high is exceeded.
- If enough cannot be reclaimed, the cgroup OOM killer may terminate the process.
- The application may be killed without a Java heap OutOfMemoryError.
- Readiness may not complete due to CPU/memory pressure.

Even when current heap usage is lower than -Xmx, total process memory can still exceed the cgroup limit. -Xmx is a heap limit, not a guarantee of maximum total RSS.

Restoring into a larger memory limit generally carries less risk of OOM, but it does not automatically increase the maximum heap of an already started JVM. To take advantage of a larger limit, the checkpoint must be created from a JVM started with appropriate ergonomics or a runtime designed with supported adjustment capabilities.

## 15. Memory Pressure, Reclaim, and OOM Events

With cgroups v2, memory.events can provide occurrence counts for several events. Example fields may include:

~~~text
low 0
high 12
max 3
oom 1
oom_kill 1
~~~

General meaning:

- low: events related to the low protection threshold.
- high: number of times the high threshold was exceeded and handled by memory pressure mechanisms.
- max: number of times usage approached/exceeded the hard max.
- oom: number of times the cgroup entered OOM handling.
- oom_kill: number of processes terminated by the OOM killer.

Field sets and details depend on the kernel. memory.events.local, if present, reflects events only at the current cgroup; memory.events may aggregate from descendants under v2 semantics.

When investigating a slow or killed restore, read the event counters before and after testing. Looking only at free -m inside a container may not accurately reflect cgroup limits or memory pressure.

## 16. Direct Memory and MaxDirectMemorySize

Many networking and I/O libraries use direct ByteBuffers to reduce copying between the heap and native I/O. Direct memory does not live in the Java heap in the usual sense, yet it still consumes process and cgroup memory.

The flag:

~~~bash
-XX:MaxDirectMemorySize=512m
~~~

can limit the total direct buffer memory managed by the JVM through the corresponding mechanism. If not explicitly set, the default depends on the JVM implementation and ergonomics. Some native allocations do not go through the direct buffer pool and are not bounded by this flag.

At restore time, existing direct buffers and native allocations must be counted toward the footprint. If the application allocates many new direct buffers right after restore, memory usage can spike rapidly. Monitor the direct buffer pool via MXBeans or JMX while comparing against memory.current.

Example reading the direct buffer pool:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

public final class BufferMetrics {
    public static void logDirectBuffers() {
        for (BufferPoolMXBean pool
                : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            if ("direct".equals(pool.getName())) {
                System.out.println("directBufferCount=" + pool.getCount());
                System.out.println("directBufferUsedBytes=" + pool.getMemoryUsed());
                System.out.println("directBufferCapacityBytes=" + pool.getTotalCapacity());
            }
        }
    }
}
~~~

MXBean provides a view of the JVM-managed buffer pool; it does not measure all native memory. Combine it with Native Memory Tracking and cgroup metrics.

## 17. Thread Count, Stack Memory, and PIDs Limit

Each platform thread typically requires native stack memory. The stack size depends on the JVM, OS, architecture, and -Xss. Creating too many threads increases memory usage and can hit the process/thread count limit.

Cgroups can enforce the PIDs controller:

- cgroups v2: pids.current, pids.max, pids.events.
- cgroups v1: typically pids.current, pids.max, pids.events if the controller is enabled.

A Java process creating a new thread also consumes a PID slot under kernel accounting rules. If pids.max is too low, thread creation can fail even when heap space is available.

With CRaC, thread pools may already have been created in the source environment. If the application starts with many processors and creates many workers, restoring into an environment with lower PIDs or memory limits can cause pressure. New threads needed after restore may fail to be created.

Monitor:

- Number of live platform threads.
- Number of threads in executors and queues.
- Thread stack size.
- pids.current and pids.max.
- unable to create native thread errors.
- Native memory and cgroup memory current.

Do not attempt to fix thread errors merely by increasing the heap. Thread creation failures are usually related to native memory, PIDs limits, OS limits, or stack allocation.

## 18. Kubernetes Requests, Limits, and QoS

In Kubernetes, container resources are typically declared in resources.requests and resources.limits.

For example:

~~~yaml
resources:
  requests:
    cpu: "1"
    memory: "2Gi"
  limits:
    cpu: "2"
    memory: "3Gi"
~~~

In this example:

- CPU request is 1 core-equivalent, used for scheduling and corresponding allocation.
- CPU limit is 2 core-equivalent, usually enforced via quota.
- Memory request is 2 GiB, used for scheduling.
- Memory limit is 3 GiB, usually applied as the cgroup memory limit.

A request is not a hard guarantee that the container will always receive that exact amount of CPU time when the node is overloaded. Nor is a memory request a hard ceiling. It is the memory limit that typically triggers OOM enforcement.

A Pod's QoS class is determined from requests/limits according to Kubernetes rules. QoS affects eviction order in certain node pressure situations, but it does not replace reading the container's cgroup limit.

When restoring a checkpoint, identify what resource requests/limits the checkpoint was created with and what configuration the target Pod/container has. A manifest with the same image but different resources can produce significantly different runtime behavior.

## 19. CPU and Memory Differences Between Source and Target Environments

An application may be warmed up on a build or staging machine with generous CPU and memory, and then restored into a production container with a lower quota. Common differences include:

| Property | Source environment | Target environment | Risk |
|---|---|---|---|
| CPU quota | 4 CPUs | 1 CPU | Throttling, slow readiness |
| Cpuset | 0-7 | 2-3 | Narrower CPU set |
| JVM availableProcessors | 4 | JVM already started with 4 | Thread pool/GC concurrency may be too high |
| Memory max | 8 GiB | 2 GiB | OOM or memory reclaim |
| Heap max | 5 GiB | JVM already configured with 5 GiB | Heap ceiling exceeds cgroup limit |
| PIDs max | 4096 | 512 | New thread creation fails |
| Direct memory | 1 GiB used | Small headroom | Native memory pressure |
| CPU weight | High | Low | Slow during node contention |

Do not assume restore will automatically adjust all values to match the target cgroup. Some resources may be updated or re-checked by the runtime/integration; ergonomics decisions made at startup may still remain. You must test the actual behavior of the CRaC JDK and libraries.

## 20. Designing a Resource Envelope for a Checkpoint Image

A checkpoint image should be created in an environment whose resource envelope is compatible with the restore target. A resource envelope is the set of resource limits and conditions an application needs to operate properly, for example:

- Minimum CPU quota and suitable cpuset.
- Sufficient memory limit for heap and native memory.
- Sufficient PIDs limit for thread pools and the runtime.
- Access permissions to cgroup and required kernel interfaces.
- External dependencies reachable after restore.
- I/O and network limits appropriate for the workload.

One strategy is to create the checkpoint in the same container resource profile as the target environment. If a single checkpoint must be used across multiple instance types, design for the smallest supported profile and test both larger and smaller profiles.

Do not create an image with a very large warmed-up heap and then restore it into a small container simply because heap occupancy at checkpoint time is low. The JVM may still need native memory, GC metadata, and headroom once execution resumes.

## 21. Choosing Heap and Native Memory Budgets

An initial budgeting approach:

~~~text
Container memory limit
  = heap budget
  + metaspace/code cache
  + thread stacks
  + direct buffers
  + GC/JVM native memory
  + JNI/native libraries
  + kernel/file cache accounting
  + safety headroom
~~~

There is no fixed ratio for all applications. Measure:

- Committed and used heap after warm-up.
- Peak heap under representative load.
- Metaspace and code cache.
- Direct buffer usage.
- Thread count and stack footprint.
- Native memory tracking categories.
- Cgroup memory.current and memory.stat.
- Memory events during load and restore.

Native Memory Tracking (NMT) can be enabled when launching the JVM:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Then use jcmd to inspect the summary if tools and runtime permissions allow:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT has overhead and only tracks allocations within the JVM scope supported by NMT; it is not a measurement of total cgroup memory. Use it alongside cgroup metrics to understand off-heap/native memory that the JVM does not account for.

## 22. Configuring the JVM for Containers

Example of a launch command with explicit configuration:

~~~bash
java \
  -XX:MaxRAMPercentage=55 \
  -XX:InitialRAMPercentage=20 \
  -XX:MaxDirectMemorySize=384m \
  -XX:ActiveProcessorCount=2 \
  -jar app.jar
~~~

This is an illustrative configuration, not a default recommendation. Before using it:

- Confirm the JDK supports these flags.
- Measure the actual memory footprint.
- Ensure the heap does not consume the entire memory limit.
- Determine an appropriate processor count relative to quota and cpuset.
- Measure thread count, direct buffers, and native allocations.
- Check cgroup ancestor limits.
- Test peak load and restore.

If -Xmx is set directly, that value usually takes precedence over percentage-based maximum heap calculation. Inspect all flags to understand which values the JVM actually uses. Do not simultaneously set conflicting flags and reason from only a single property.

## 23. Diagnosing Cgroups from Inside a Container

With cgroups v2, once the corresponding mount root and path have been identified, example commands might be:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.high
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
~~~

The paths above are only common examples when the container sees its cgroup at the mount root. In a nested hierarchy, combine the cgroup path from /proc/self/cgroup with the appropriate mount root; check ancestors to find the effective limit.

With cgroups v1, files may reside on separate mounts, for example:

~~~bash
cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us
cat /sys/fs/cgroup/cpu/cpu.cfs_period_us
cat /sys/fs/cgroup/cpu/cpu.shares
cat /sys/fs/cgroup/memory/memory.usage_in_bytes
cat /sys/fs/cgroup/memory/memory.limit_in_bytes
cat /sys/fs/cgroup/memory/memory.failcnt
~~~

Do not run the sample paths verbatim if the system mounts them differently. First determine controller mount points from mountinfo.

## 24. Measuring JVM CPU and Memory Alongside Cgroup Metrics

Combine JVM metrics with kernel metrics:

| Source | Data | Question answered |
|---|---|---|
| Runtime.availableProcessors() | Processor count visible to the JVM | How many processors is the JVM using for ergonomics? |
| JVM flags | Heap, GC, processor override, direct memory | How is the JVM configured? |
| jcmd VM.native_memory | Native allocations within NMT scope | Which category is native memory growing in? |
| Heap MXBeans / GC logs | Heap used/committed, pauses, allocation | Is the heap approaching its limit? |
| BufferPoolMXBean | Direct/mapped buffers | How much memory do I/O buffers consume? |
| ThreadMXBean / thread dump | Thread count and stack traces | Are threads growing or stuck? |
| cpu.stat | Usage and throttling | Is the cgroup being throttled? |
| memory.current, memory.stat | Memory usage and breakdown | Where is cgroup memory increasing? |
| memory.events | High/max/OOM counters | Are there memory pressure or OOM events? |
| pids.current | Process/thread count by cgroup | Is it approaching the PIDs limit? |

Capture metrics at at least four points in time: after startup, after warm-up, right before checkpoint, and after restore once under load. If possible, also record the peak during representative load.

## 25. Workflow for Preparing Checkpoint and Restore With Resource Limits

A deployment workflow should include:

1. Determine the target environment's resource profile: CPU quota, cpuset, memory max/high, swap, PIDs, and ancestor limits.
2. Choose a CRaC JDK and JVM flags suited to that profile.
3. Launch the application in an environment with equivalent or proven-compatible limits.
4. Let Spring/frameworks and dependencies complete warm-up.
5. Measure heap, native memory, direct buffers, thread count, and cgroup usage.
6. Stop ingress and background work before checkpoint according to the application lifecycle.
7. Create the checkpoint and store it with metadata about the JDK build, flags, cgroup profile, and image version.
8. Restore in the target environment with the expected limits.
9. Re-measure cgroup and JVM metrics, checking throttling, memory pressure, and PIDs.
10. Run a health check representative of real workload behavior.
11. Open readiness only when dependencies and resource budgets are sufficient to serve.
12. Run verification load to confirm there are no OOMs, sustained throttling, or uncontrolled queue growth.

If the restore target has fewer resources than the validated profile, treat it as a configuration change requiring separate testing. Do not use a single checkpoint image across all resource tiers without measuring.

## 26. Kubernetes Deployment Example

The following example illustrates a container with separate requests/limits:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: crac-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: crac-service
  template:
    metadata:
      labels:
        app: crac-service
    spec:
      containers:
        - name: app
          image: example/crac-service:latest
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "2"
              memory: "3Gi"
~~~

This is only a structural example. Real configuration also depends on the checkpoint/restore integration, runtime class, checkpoint storage volume, security context, and JDK requirements. Requests/limits should be chosen based on measurements of the application.

When comparing the checkpoint creation environment and the restore environment, inspect the Pod spec, container spec, the process's cgroup, and node/parent limits. Do not infer actual resources solely from the YAML file because admission policies, LimitRange, the runtime, and ancestor cgroups can affect the final configuration.

## 27. Readiness When CPU or Memory Is Insufficient

After restore, the process may remain alive yet lack sufficient capacity to serve. For example:

- Memory pressure slows down every request.
- CPU throttling causes health checks to time out.
- The thread pool already has many workers, while the PIDs limit prevents creating additional threads.
- GC runs continuously because the heap is nearly exhausted.
- Direct buffer allocation fails.
- Executor queues grow faster than processing throughput.
- Background refreshes or lease renewals are delayed due to lack of CPU.

Readiness should not check only whether the process is still alive. Essential components and minimum processing capability must be verified. However, the health check should also avoid generating heavy load or business side effects.

Operational thresholds can be used for CPU throttling, memory headroom, GC pauses, executor queues, and PIDs usage. Thresholds should be based on measured baselines. If the resource budget is insufficient, the instance should remain unready or be replaced with a suitable profile instead of accepting traffic and failing en masse.

## 28. Common Mistakes

**Using host CPU count as container CPU capacity.** The JVM may be constrained by quota or cpuset. Check the cgroup and availableProcessors().

**Confusing CPU request with CPU limit.** Request is for scheduling; limit is the hard quota typically enforced. Read the actual cgroup.

**Reading only cpu.max in the child cgroup.** Ancestors may enforce a stricter quota. Inspect the entire hierarchy.

**Assuming cpu.weight is a core count.** Weight is a relative share during contention, not a CPU quota.

**Setting ActiveProcessorCount higher than the CPU quota.** This flag does not create additional CPU time. It can cause excessive concurrency and thread counts.

**Setting Xmx equal to memory.max.** Heap is not all of process memory. Leave budget for native memory, threads, direct buffers, GC, and kernel accounting.

**Assuming MaxRAMPercentage will automatically recalculate after restore.** The JVM has already started and may retain ergonomics decisions from the source. Verify the specific CRaC JDK.

**Checking only heap usage.** A cgroup can OOM due to native memory or page cache even when heap space remains. Monitor memory.current and memory.events.

**Ignoring pids.max.** Thread creation can fail even when memory is sufficient. Monitor PIDs and thread counts.

**Checkpointing on a large machine and restoring into a small container without testing.** Maximum heap, thread pools, and native footprint can exceed the target's capacity. Build a compatible resource profile and test it.

**Checking only immediately after restore.** Increasing load can push memory and CPU past thresholds after warm-up. Run representative workloads and monitor peaks.

## 29. Cgroups, CPU, and Memory Compatibility Checklist

- [ ] Have you identified whether the process belongs to cgroups v1 or v2?
- [ ] Have you determined the exact cgroup path and mount root from /proc/self/cgroup and mountinfo?
- [ ] Have you checked CPU quotas on both the current cgroup and ancestors?
- [ ] Have you checked the effective cpuset?
- [ ] Have you distinguished between quota, weight/share, and Kubernetes request/limit?
- [ ] Have you inspected CPU throttling statistics?
- [ ] Have you verified Runtime.availableProcessors() and JVM container awareness?
- [ ] Is ActiveProcessorCount appropriate for the quota and workload?
- [ ] Have you checked memory.current, memory.high, memory.max, and ancestor limits?
- [ ] Have you inspected memory.events to detect pressure/OOM?
- [ ] Does the heap budget leave enough room for native memory, direct buffers, metaspace, code cache, and thread stacks?
- [ ] Have you checked direct memory and Native Memory Tracking yet?
- [ ] Have you checked pids.current and pids.max?
- [ ] Is the checkpoint creation resource profile compatible with the target environment?
- [ ] Have you measured CPU, memory, GC, threads, and readiness before and after restore?
- [ ] Have you run representative load under the exact cgroup limits of the target environment?

## Conclusion

Cgroups determine the resource limits a process can actually use inside a container. CPU quota, cpuset, and CPU weight have different meanings; memory high and memory max are also two distinct thresholds. The JVM can detect certain container limits at startup, but behavior depends on the JDK and you should not assume every ergonomics decision will be recalculated upon restore.

For a checkpoint image to run reliably in the target environment, measure the actual resource envelope, choose heap and native memory budgets with headroom, set concurrency appropriately for the CPU quota, check the PIDs limit, and monitor throttling/OOM events. Create the checkpoint in a profile compatible with the restore location, then test restoring and running representative load under the exact cgroups limits. Only when the JVM, application, and entire container have sufficient CPU, memory, and thread capacity can a restore transition into a stably serving ready instance.
