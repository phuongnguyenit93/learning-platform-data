# 1.2 Relationship Between Application, JVM, JDK, Operating System, and Machine Resources

When a Java service is slow, hangs, consumes too much memory, or terminates unexpectedly, the sign visible in the application may originate from another layer. To diagnose accurately, you must understand that the application runs **inside a JVM**, the JVM is the execution component inside an **operating system process**, and that process competes for or is constrained by **CPU, memory, disk, network, and resource limits**. The **JDK** provides the toolset to build, launch, and observe that system.

Lesson objectives: distinguish the responsibilities of each layer; trace the path from Java code to machine resources; explain why metrics across layers are not necessarily equal; and know which layer to inspect before attributing the cause of an incident.

## 1. Layer Model and Dependency Direction

```text
External requests / users / other systems
                  |
                  v
JAVA APPLICATION: business code, frameworks, libraries, pools, queues
                  |
       runs inside a process containing
                  v
JVM: class loading, interpreter/JIT, heap/GC,
     runtime threads, JNI, JVM memory management
                  |
          uses system services
                  v
OPERATING SYSTEM: CPU scheduling, virtual memory, threads,
                  files, sockets, I/O, permissions and limits
                  |
      uses or allocates resources
                  v
PHYSICAL MACHINE / VM / CONTAINER: CPU, RAM, storage, network,
                                   quotas and shared resources

JDK: javac, java, jcmd, jfr, jstack, jmap, ...
  ├─ contains the runtime needed to run the application (including JVM)
  └─ provides external tools out-of-process to compile,
     launch, collect, and analyze evidence.
```

The diagram describes **runtime dependencies**, not that every block is a separate process. In the common case, the `java` command launches one operating system process containing the JVM and the application. The JVM also has native code and native libraries running inside the same process. The application can interact with the operating system through Java APIs or native/JNI code. Most JDK tools such as `jcmd` run as **separate tool processes**, connecting to the target JVM if permissions and attach capabilities allow.

| Layer | What It Owns or Determines | Typical Diagnostic Evidence |
| --- | --- | --- |
| Application | Request flow, algorithms, DB connections, thread pools, caches, retries, timeouts, application locks | Logs/tracing, latency, error rate, queued requests, pool sizes |
| JVM | Class loading, bytecode/JIT execution, heap, GC, metaspace, JIT code cache, various thread types | GC logs, JFR, thread dumps, heap metrics, JVM flags |
| JDK/toolchain | Compiler, launcher, bundled libraries/runtime, observation tools | `java -version`, `javac -version`, `jcmd`; actual running JDK version |
| Operating system | Process/PID, thread scheduling, virtual memory, file descriptors, sockets, filesystem, permissions | CPU by PID/TID, RSS, I/O, open file limits, kernel logs |
| Machine/VM/container | Available physical cores and RAM, shared resources, CPU quota, memory limits | CPU throttling, memory pressure, cgroup limits, I/O latency, host metrics |

**Inference rule:** observing a phenomenon in layer A alone is not enough to conclude the cause belongs to A. For example, an HTTP timeout can be caused by an application lock, a GC pause, CPU throttling, a slow DB query, or a dropped network connection.

## 2. From Source Code to Running Process: How Do JDK and JVM Differ?

Typical flow:

1. `javac` in the JDK compiles `.java` files into `.class` bytecode (or builds a JAR via a build tool).
2. The `java` command selects the runtime, creates a process, and starts the JVM; class loaders load the required classes.
3. The JVM verifies, links, and initializes classes on demand; executes bytecode with the interpreter and may compile hot paths into machine code via JIT. Not every method is always JIT-compiled.
4. At runtime, the JVM/application requests CPU, memory pages, threads, files, sockets, and I/O from the operating system. The operating system schedules and allocates those requests on hardware or virtualized infrastructure.
5. JDK tools can help observe the running process. They do not automatically fix business bugs or replace application metrics.

**Important distinctions:**

- **JVM** is the virtual machine that executes Java bytecode; HotSpot is one common implementation. JVM is not synonymous with the entire JDK.
- **JDK** is the development kit containing compilation tools and a suitable runtime to run programs. `javac` is not necessarily needed on production machines; minimal runtime images may omit `jcmd` or `javac`.
- **JRE** is a term for a Java runtime environment; historically there were standalone JRE distributions, but in modern diagnostics always verify the **actual runtime/JDK that the process is using**, rather than inferring from directory names or `JAVA_HOME`.
- Two machines with the same application code but different JVM versions, JVM configurations, operating systems, or resource quotas can exhibit different performance behavior. If bytecode was compiled for a newer Java version than the target runtime supports, `UnsupportedClassVersionError` may occur during class loading.

Running `java -version` in a shell reports the **`java` command found by that shell**, which may differ from the runtime of a service process started earlier. During an investigation, verify the executable path, command line, environment, and specific PID; do not use one terminal's output as definitive evidence for every JVM on the machine.

## 3. How Do Resources Flow Through the Layers?

### 3.1 CPU: Application Work, JVM Threads, and OS Scheduling

The application creates work; the JVM executes Java code, GC, and JIT; the operating system schedules threads onto CPUs. Therefore, high CPU in a Java process can come from:

- Business loops/computations, parsing/serialization, library code, or lock contention with spinning.
- JVM GC or JIT compiler threads, alongside application threads.
- A high number of runnable threads while CPU quota or allocated physical CPUs are low.

A Java **platform thread** typically maps to a native OS thread; the OS scheduler decides when that thread runs. **Virtual threads** (Java 21+) do not map 1:1 to OS threads: many virtual threads are scheduled by the JVM onto a pool of carrier platform threads. Do not infer the native thread count from the virtual thread count.

`Runtime.getRuntime().availableProcessors()` reflects the number of processors the JVM considers available to the process, which can be affected by CPU affinity, cgroup/container quotas, or `-XX:ActiveProcessorCount`; it does not automatically equal the host's total core count. Tools reporting "100% CPU" also require context: that could mean one core, one process, or a percentage of quota depending on how the tool normalizes it.

When latency increases, inspect concurrently: CPU per process/thread, permitted CPU count, CPU throttling, GC/JIT activity, and I/O wait time. A thread in `RUNNABLE` state in a Java thread dump does not prove it is occupying an entire CPU core at the exact moment of sampling.

### 3.2 Memory: Heap Is Only One Part of the Process

Do not equate `-Xmx` with "maximum RAM of the application." Areas to watch include:

| Concept | Meaning | How to Interpret in Diagnostics |
| --- | --- | --- |
| Java heap | Where most Java objects live; managed by GC | `-Xmx` is the maximum heap limit, not total process RAM |
| Metaspace | Class metadata in native memory | Can grow from class loading/class loaders; not part of the heap |
| Code cache | Machine code compiled by JIT and related metadata | Consumes memory outside the heap |
| Thread stacks | Native stacks for platform threads, per configuration/runtime | Many platform threads can increase native memory demand |
| Direct/native memory | E.g., direct buffers, JNI/native libraries, native allocations | Can cause memory pressure even when the heap still has room |
| Process RSS | Memory pages currently resident in RAM as accounted by the OS | Not synonymous with heap used, nor with total reserved memory |
| Container/host memory | Limits/quotas and memory accounted by the system | May include components such as page cache; accounting depends on OS/cgroup |

Easily confused quantities:

- **Used heap**: amount of objects/heap space currently in use as measured by JVM metrics at sampling time.
- **Committed heap**: amount of heap memory the JVM has committed from the OS; can be larger than used.
- **Max heap**: maximum limit the JVM plans for the heap; not the amount of RAM currently occupied.
- **Reserved virtual address space**: does not mean all of those bytes reside in RAM.
- **RSS**: OS-level metric for resident pages; may include mapped/shared regions and cannot be derived by simply adding up every JVM number.

For example: a container has a 512 MiB limit, and the JVM sets `-Xmx400m`. When heap, metaspace, code cache, native buffers, thread stacks, and system memory grow together, the container **can still exceed its limit** and the process can be killed even though the heap has not used all 400 MiB. This is why you must check both JVM heap **and** total memory usage / container limits.

Separate three cases:

1. `OutOfMemoryError: Java heap space`: the JVM cannot satisfy a heap allocation within current limits/GC behavior; investigate object retention, allocation rate, and heap sizing.
2. Native resource errors (such as `OutOfMemoryError: unable to create native thread` or direct buffer allocation failure): investigate native memory, thread count, and OS limits; do not blindly increase `-Xmx`.
3. Process terminated by OS/container via `SIGKILL`: the JVM may not have time to emit a Java exception or heap dump. Exit code 137 in many environments commonly indicates SIGKILL, **but does not by itself prove an OOM kill**; check kernel/cgroup/container events.

### 3.3 Files, Sockets, Network, and I/O

Java `Files`, `Socket`, JDBC drivers, NIO selectors, or logging libraries still ultimately depend on OS resources and external systems. Each open connection or file can consume a file descriptor/handle and buffers, while I/O latency is affected by disks, filesystems, network devices, DNS, target servers, and quotas.

When encountering "Too many open files," check the number of descriptors in use against the soft/hard limits of the **exact process**, along with resource-closing lifecycles. When DB connections are exhausted, distinguish an exhausted application pool from OS sockets, network ports, DB server latency, and timeouts. A "hung Java process" may simply be threads waiting on syscalls or responses from another service.

### 3.4 Containers and Hosts: Look at the Right Scope

Containers **share the kernel** with the host but can use namespaces and cgroups to isolate process identifiers and resource limits. Therefore:

- A PID seen inside a container can differ from the PID seen from the host. Always know which namespace a measurement command runs in.
- Host CPU/RAM metrics and container metrics are not directly interchangeable. A host having free RAM does not guarantee a container has not hit `memory.max`.
- On Linux cgroup v2, `memory.max` represents the memory limit (the string `max` means no limit is set at that file level), `memory.current` is the accounted usage, `memory.events` reports certain memory pressure/OOM events; `cpu.max` describes quota/period. Paths and mechanisms can differ in cgroup v1, other runtimes, or other operating systems.
- Many modern HotSpot builds are container-aware, but you must verify the actual JVM version, flags, and environment. Fixed configurations or flags can produce behavior different from expectations.

A sensible inspection order: **specific process → process's container/VM → host → dependent systems**. Do not blame the host if you only see container numbers, and vice versa.

## 4. Hands-On Observation on a Java Program

The following standalone example works on Java 17+ and only **reads metrics of the current JVM/process**; it does not stress CPU or intentionally exhaust memory. Save to `RuntimeLayersDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;

public class RuntimeLayersDemo {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("availableProcessors=" + runtime.availableProcessors());
        System.out.println("heap.used.bytes=" + heap.getUsed());
        System.out.println("heap.committed.bytes=" + heap.getCommitted());
        System.out.println("heap.max.bytes=" + heap.getMax());
        System.out.println("live.java.threads=" + threads.getThreadCount());
    }
}
```

Compile and run:

```bash
javac RuntimeLayersDemo.java
java -Xmx256m RuntimeLayersDemo
```

The program prints eight lines starting with `pid=`, `java.version=`, `os.name=`, `availableProcessors=`, `heap.used.bytes=`, `heap.committed.bytes=`, `heap.max.bytes=`, and `live.java.threads=`. **Exact values depend on the machine and JVM**, so do not assume a fixed stdout. On standard HotSpot, `heap.max.bytes` reflects the max heap decided by the JVM under `-Xmx256m`; the value may not equal a decimal "256 MB" number that a reader assumes. A `heap.max.bytes` value of `-1`, if seen with a corresponding implementation/pool type, means the maximum is undefined.

Interpreting the results:

- `pid` is the process identifier as seen by the runtime. In containers, reconcile namespaces when comparing with host tools.
- `java.version` identifies the runtime **actually executing the program**, which is more reliable than checking `java` version in another shell.
- `availableProcessors` is not a measure of actual CPU load; it is information the JVM uses to determine available processing resources.
- The three heap values give the JVM's view of the heap; they do not measure total native memory or RSS.
- `ThreadMXBean.getThreadCount()` reflects the number of live Java platform threads tracked by the MXBean; it does not replace counting all OS threads or virtual threads.

To correlate a longer-running JVM, observe a real service across multiple samples over time rather than a short command that exits too quickly to attach tools. Sample numbers are meaningful only when recorded with timestamp, PID, JVM version, and corresponding resource limits.

## 5. JDK and Operating System Tools Complement Each Other

Examples on Linux/HotSpot—replace `PID` with the PID of the **exact process**; commands depend on permissions, attachability, and environment. Do not run every command as a "recipe" before knowing which question needs an answer.

| Question | JVM/JDK Tool | OS / Container Tool |
| --- | --- | --- |
| Right Java process and startup arguments? | `jcmd -l`; `jcmd PID VM.command_line`; `jcmd PID VM.flags` | `ps -p PID -o pid,ppid,args`; inspect executable/container |
| What is the heap state? | `jcmd PID GC.heap_info`; JMX/MXBeans, GC logs | RSS and memory limit for comparison |
| Which threads are waiting/running? | `jcmd PID Thread.print`; JFR | `top -H -p PID` or `ps -L` to inspect native threads |
| Where is native memory used? | `jcmd PID VM.native_memory summary` **only useful when NMT is enabled at startup** | `/proc/PID/status`, `/proc/PID/smaps_rollup` when permitted |
| High CPU or throttled? | JFR CPU samples, GC/JIT events | CPU per PID/TID, cgroup `cpu.max` and throttling counters |
| Missing file descriptors, I/O bottleneck? | Application logs, stack traces, pool metrics | `/proc/PID/fd`, `lsof -p PID`, `ss`, disk/network metrics |

Example initial investigation commands:

```bash
java -version
jcmd -l
jcmd PID VM.command_line
jcmd PID VM.flags
jcmd PID GC.heap_info
jcmd PID Thread.print
ps -p PID -o pid,ppid,%cpu,%mem,rss,nlwp,args
```

**Tool limitations:** `jcmd` typically requires matching version/OS user permissions and attach mechanisms; minimal runtime images or processes in another container may lack it or disallow attach. NMT (`-XX:NativeMemoryTracking=summary` or `detail` where HotSpot supports it) adds overhead and must be enabled at startup to obtain its statistics. Do not describe "NMT not enabled" as "native memory equals 0." JFR can provide CPU, allocation, GC, and thread scheduling samples over a time window, but you must read the right event types and consider collection overhead.

On Windows, replace `/proc`/`ps` commands with Task Manager, Resource Monitor, Performance Monitor, or PowerShell `Get-Process`; the principle remains linking **the same PID, the same time window, and the same environment**. Do not apply Linux commands verbatim on Windows.

## 6. Cross-Layer Diagnostics: From Phenomenon to Evidence

A repeatable workflow:

1. **Identify:** record service, build, actual running runtime/JDK, PID, host/container, command line, timestamp, and symptom. Check error codes and impact scope.
2. **Measure at the application layer:** p50/p95/p99 latency, throughput, error rate, request queues, pools/DB connections, locks/waits, and logs/traces with correlation IDs.
3. **Measure the JVM over the same window:** heap used/committed/max, allocation/GC pauses, GC CPU, platform thread count, thread dumps/JFR when signals warrant.
4. **Measure OS/container/host:** CPU by PID/TID, throttling, RSS and memory limit, thread/FD counts, I/O wait, disk, network, OOM/kernel events. Compare using consistent units and timestamps.
5. **Form a falsifiable hypothesis:** what evidence supports it, what refutes it; vary load, configuration, or code in a safe environment; observe consequences. Avoid blindly increasing heap, thread pools, or retries.

Quick reasoning table:

| Symptom | Possibilities to Distinguish | Evidence to Separate Causes |
| --- | --- | --- |
| API timeouts, low CPU | Waiting on DB/network, locks, or exhausted pool; not necessarily a "slow" JVM | Traces, pool queues, thread dumps, socket/network and downstream latency |
| Slow API, high process CPU | Hot code, GC, JIT, busy loop | CPU samples/JFR, GC events, per-thread CPU by TID |
| Host CPU idle but service slow | CPU quota/throttling, I/O, locks, downstream | Cgroup CPU metrics, run queue, traces, and thread states |
| Heap used grows after multiple GCs | Long-lived retention/leak or intentional cache growth | GC trend, heap dump when appropriate, object graph, traffic |
| Container killed, no Java OOME | May have exceeded cgroup limit or received SIGKILL for another reason | Container termination reason, kernel/cgroup OOM events, memory.current/limit |
| `Too many open files` | FD leak, too many connections, or limit set too low | FD count by PID, `RLIMIT_NOFILE`, resource lifecycle |

### Example: Latency Increases Without Application Code Changes

Suppose a new deployment keeps the application unchanged, but reduces the container's CPU quota. Some requests begin timing out; the host still has idle CPU. Do not conclude "GC is broken" from the timeouts. Check: have CPU quota and throttling increased; did `availableProcessors`/JVM ergonomics change; what are GC and application CPU times; is the request queue backing up due to lower throughput? If metrics show throttling rising alongside worsening latency, that is **strong evidence for CPU limits**, to be confirmed with controlled quota or load testing. Never infer from a single CPU metric alone.

### Example: Normal Heap but Container OOM

Suppose heap used fluctuates between 200–300 MiB and shows no Java heap OOME, yet the pod reports `OOMKilled`. Investigation must combine memory limit, peak memory, native allocations, metaspace, direct buffers, thread stacks, page cache, and cgroup OOM events. Increasing `-Xmx` can cause the container limit to be hit sooner; shrinking heap may not solve it if consumption comes from native memory or page cache. The final decision must rely on the full memory budget and actual evidence.

## 7. Common Mistakes When Locating Causes

- **"JDK, JVM, and Java process are the same thing."** JDK is tools + runtime; JVM is the execution component; the OS process is the unit scheduled and accounted by the OS. Closely related, yet distinct roles.
- **"`-Xmx` equals total RAM used by Java."** The JVM also has metadata, code cache, stacks, and native allocations; containers/OS perform their own accounting.
- **"Heap still has free space so OOM cannot happen."** Native allocation, OS process limits, cgroup limits, or other failures can still occur.
- **"100% CPU means consuming the whole machine."** You must know the core count, how the tool computes percentages, CPU quota, and CPU affinity.
- **"A WAITING thread is a deadlock."** WAITING/TIMED_WAITING can be a normal state for pool threads; examine lock graphs, stacks, wait duration, and work progress.
- **"Same bytecode means identical performance."** JVM/JDK version, GC, flags, CPU architecture, kernel, container quotas, and system load all affect outcomes.
- **"Exit 137 is definitely OOM."** Typically indicates SIGKILL; system/container events are required to confirm the reason.
- **"One metric is enough to identify the culprit."** Every metric has scope, units, sampling intervals, and observation limits. Link at least one application symptom with matching JVM and OS evidence.

## 8. How to Self-Check Understanding of the Model

For a real Java service, ask yourself: (1) what are the exact PID and runtime? (2) how much CPU/RAM is **allocated/permitted** to the process/container versus the host? (3) how much heap is used, and what about non-heap areas and RSS? (4) are requests computing, waiting on JVM pauses, or waiting on I/O/downstream? (5) which two measurements from **two different layers** can confirm or refute the current hypothesis?

**Remember:** high-quality Java diagnostics begins by connecting the chain **application → JVM inside process → operating system → physical/virtual resources**, while using the **JDK as an observation toolkit**. Attribute a cause only after evidence across the relevant layers is consistent.