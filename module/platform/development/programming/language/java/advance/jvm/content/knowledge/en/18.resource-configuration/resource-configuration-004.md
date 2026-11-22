# -Xss, Thread Count, and Off-Heap Memory Budget

## 1. The Problem: How Much Memory Does the JVM Still Need When the Heap Is Limited?

A Java server configuration might set `-Xmx512m` in a container limited to 1 GiB, yet still be killed by the operating system for running out of memory; or encounter `java.lang.OutOfMemoryError: unable to create native thread` even though the **heap used** chart is low. There is no contradiction in the cause: **the Java heap is only one part of process memory**, while **each platform/native thread** requires a stack and many other resources.

This topic belongs to the **Resource Configuration** group in the JVM: one must understand the relationship between `-Xss`, the number of platform threads, stack reservations/commit, OS/cgroup limits, and headroom for **non-heap/native** memory, rather than just lowering `-Xmx` or increasing `-Xss` by guesswork.

Let us separate four questions:

1. **Stack depth:** how much stack does a thread need to execute Java/native calls safely? This relates to `StackOverflowError` and call chain structure.
2. **Number of concurrently live threads:** how many **platform/native threads** are created by the application and the JVM, including GC/JIT/runtime threads?
3. **Off-heap memory:** how much do metaspace, JIT code cache, direct buffers, GC bookkeeping, thread stacks, JNI/native allocations, and mapped memory use?
4. **Execution limits:** how much resident/committed memory, native threads, PIDs/tasks, and CPU does the OS/cgroup allow?

**There is no general exact formula “native memory = number of threads × `-Xss`”.** This is only one component **estimating the stack reservation scale**; actual committed/resident stack pages and other native memory must be measured on a real JVM/OS.

## 2. Distinguishing JVM Stack, Java Heap, and OS/Native Stack

### 2.1. Java Heap

Regular Java objects and arrays reside in the heap managed by the JVM/GC. The flags:

- `-Xms`: initial Java heap size.
- `-Xmx`: maximum Java heap size.
- `-Xmx` does **not** limit total RSS or process committed memory.

Therefore, `-Xmx512m` does not mean “Java can only use 512 MiB of RAM”.

### 2.2. Logical JVM Stack

Each **Java execution thread** has a logical call stack containing frames of method calls, locals, operand stack at the JVM bytecode level, and return/exception handling information. When `a()` calls `b()` and then `c()`, the stack grows with call depth; when calls return, frames that are no longer needed are removed from the active call chain.

`StackOverflowError` is an error when the JVM cannot satisfy a request for additional stack according to runtime limits. It does **not** mean the Java heap has exhausted `Xmx`.

### 2.3. Native Stack of a Platform Thread

On HotSpot, a **platform thread** usually corresponds to an OS/native thread. The OS needs a native stack, thread ID, scheduling state, and TLS/allocator/runtime resources. HotSpot may reserve a virtual address region for the native stack; which pages are actually **committed** or **resident** depends on the OS and how the thread uses the stack.

~~~text
Java process
├── Java Heap          (-Xms, -Xmx)
├── Metaspace/Class metadata
├── JIT code cache
├── GC and JVM internal/native structures
├── Direct/native buffers, JNI, third-party allocations
├── Thread 1 (platform / OS) ── native stack 1
├── Thread 2 (platform / OS) ── native stack 2
├── ...
└── JVM service, GC and compiler native threads
~~~

The stack is a per-**OS thread** resource in the platform threads model. A pool of 500 workers blocked on I/O but still alive can continue holding **native stack reservations** for 500 threads, even though most are not running on the CPU.

### 2.4. Virtual Threads Are a Different Case (Java 21+)

Since Java 21, **virtual threads** have logical Java call stacks but do not require each VT to hold a separate OS/native stack for its entire lifetime. When a blocking operation supports **unmounting**, HotSpot can store continuation/stack chunks on the heap and reuse the **carrier platform thread**.

**This does not turn stack memory into 0**: each VT still has heap objects, stack chunks/locals, and live references; carriers and GC/JIT/native threads still use native stacks. Java 17 code runs **platform threads** in the lab; `Thread.ofVirtual()` only has a standard API starting in Java 21.

**Scope conclusion:** The formula `number of threads × -Xss` is a rough model for **platform thread stacks** and must not be multiplied by the total number of virtual threads.

## 3. What Is `-Xss`, Its Units, and Defaults?

According to the Oracle JDK 17 Java launcher documentation, `-Xss` **sets the thread stack size**. A number of bytes or suffixes `k`, `m`, `g` can be used:

~~~bash
java -Xss256k -cp . StackDepthDemo
java -Xss512k -cp . StackDepthDemo
java -Xss1m   -cp . StackDepthDemo
~~~

The examples use Java 17+ on a **supported HotSpot/OS**. The VM may reject values that are too small, round to alignment/pages, or apply platform constraints. There is no single portable minimum applicable to every JVM/OS/architecture.

**Some Oracle JDK 17 defaults noted in documentation:**

| Platform | Reference default example |
| --- | --- |
| Linux/x64 64-bit | 1,024 KiB |
| macOS 64-bit | 1,024 KiB |
| Oracle Solaris 64-bit | 1,024 KiB |
| Windows | Depends on virtual memory/platform |

These are **values in Oracle's Java 17 documentation**, not mandatory values for every build at all times. Check the actual JVM with flags and NMT when making capacity decisions.

`-XX:ThreadStackSize=` is a related HotSpot flag, but **the base unit of the flag is kilobytes**, unlike the byte-based notation of `-Xss`. Avoid confusing `-XX:ThreadStackSize=512` with 512 bytes; also avoid using both flags overlappingly without reason.

### `-Xss` Is Not a Live Memory Threshold

A platform thread configured with a nominal 512 KiB stack **does not necessarily increase RSS by exactly 512 KiB at creation time**. The OS may reserve address space, commit/touch pages as the stack grows, and have guard/shadow pages, alignment, and other metadata. The native stack limit is also affected by JVM internals and OS mapping policies.

**Distinguish clearly:**

- **Nominal/configured stack size:** input to the VM to configure the thread stack.
- **Reserved:** virtual address range set aside in advance, which may be larger than the number of bytes touched.
- **Committed:** memory committed according to OS/JVM tracking.
- **Resident (RSS/Working Set):** pages actually resident according to OS accounting.
- **Guard/yellow/red/shadow pages:** protection and safety regions when the stack nears its limit, computed in an implementation-specific way.

Do not expect **NMT `Thread stack reserved`** to equal exactly `N_workers × Xss` because the category also includes the main thread, GC/JIT/service threads, and OS/VM overhead; the actual size may be rounded.

## 4. Impact on `StackOverflowError`

With deeply nested calls or recursion, stack frames accumulate on the thread stack. Reducing `-Xss` reduces the per-platform-thread stack budget in many situations, so it **can cause `StackOverflowError` to occur at a smaller depth**.

For example:

~~~text
-Xss256k → less stack space per platform thread
-Xss512k → middle level
-Xss1m   → larger stack budget

There is no fixed factor to convert this value into a number of method frames.
~~~

The size of a frame depends on Java bytecode, JVM interpreter vs JIT compiled code, inlining, locals, native transitions, architecture, debug flags, and optimizations. The same code can produce **different maximum depths** between JDK 17 and a newer JDK, or between cold and warm JIT states.

### Stack Overflow Differs from Out-of-Memory Caused by Thread Creation

| Phenomenon | Symptom | Investigation direction |
| --- | --- | --- |
| `StackOverflowError` | Call chain too deep / recursive bug; adding stack frame fails | Stack trace, recursion/base condition, per-thread stack config |
| `OutOfMemoryError: Java heap space` | Java object allocation fails | Heap live set, `-Xmx`, GC, allocations/retention |
| `OutOfMemoryError: Metaspace` | Insufficient class metadata/metaspace | Classloaders, generated classes, metaspace cap |
| `OutOfMemoryError: unable to create native thread` | JVM/OS cannot create a new OS thread | Native memory, OS thread/PID quota, `pids.max`, `ulimit`, thread leaks |
| Container `OOMKilled` | Kernel/cgroup kills process; may have no Java exception | cgroup memory.current/events, RSS/anonymous/file charges |
| Direct buffer allocation failure | Native/direct buffer memory budget/cap or pressure | Buffer pool/JNI/MaxDirectMemorySize/OS counters |

`unable to create native thread` is **not necessarily only due to running out of RAM**: the OS may block it because of **per-user process/thread limit, cgroup pids controller, global threads-max, security controls**, or resource reservation, even when plenty of heap remains.

## 5. Runnable Java 17: Stack Limits and Recursion

Create the file **`StackDepthDemo.java`**:

~~~java
public final class StackDepthDemo {
    private static volatile int depthReached;

    static void dive(int depth) {
        depthReached = depth;
        dive(depth + 1);
    }

    public static void main(String[] args) {
        try {
            dive(1);
        } catch (StackOverflowError expected) {
            System.out.println("caughtStackOverflow=true");
            System.out.println("depthPositive=" + (depthReached > 0));
        }
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 StackDepthDemo.java
java -Xss256k StackDepthDemo
java -Xss1m StackDepthDemo
~~~

**Verified stdout compiled/run on JDK 24 Windows for both configurations:**

~~~text
caughtStackOverflow=true
depthPositive=true
~~~

The program does not print a specific depth because it depends on the VM build, platform, JIT state, and stack frames. The `volatile` field stores the depth reached, but this experiment is **not** an exact stack byte usage measurement tool.

**Run only in a controlled lab manner**; do not catch `StackOverflowError` and continue serving production requests as a stable handling strategy. The remaining stack at the time of the error may be very small; deep handling/logging or creating a recursive error handler may fail again.

### Why Is Increasing `-Xss` Indefinitely Not Recommended?

If a method has a recursive bug with no base case, increasing `-Xss` only delays the error, wastes address space, and can degrade the ability to create many platform threads. The optimal fix is usually to **fix the recursion** or switch to iteration/an explicit work stack when appropriate. Increasing stack size should be based on **tested valid depth** and the real native memory budget.

## 6. How Does Platform Thread Count Affect Native Memory?

A **simple estimation** model:

\[
S_{\text{reserved, approx}} \approx N_{\text{platform}} \times S_{\text{per-thread nominal}}
\]

Where `N_platform` is the total number of platform/native threads corresponding to **not only application worker threads**; `S_per-thread nominal` may differ for JVM runtime/GC/compiler threads, the main thread, or threads created by native libraries.

This is **not an exact equation for RSS or NMT Thread committed**. For headroom, one can build an upper-bound style budget using the expected maximum number of threads multiplied by stack size, plus overheads, but it must be **re-measured** because each OS handles reservation/commit differently.

### Illustrative Hand-Calculation Example

An application has **400 platform workers**, each configured with a nominal `-Xss512k`:

- Nominal worker stacks portion: `400 × 512 KiB = 204,800 KiB = 200 MiB` of **configured stack region scale**.
- If replaced with `-Xss1m`, the nominal portion is `400 MiB`.
- The nominal difference is about `200 MiB`, which can be important for **virtual address reservations**, OS thread creation, and committed memory headroom in high stack usage situations.
- Do **not** claim that 400 waiting workers occupy exactly 200 MiB of RSS; RSS cannot be calculated by this multiplication alone.

In addition to the 400 workers, there are the main thread, ForkJoinPool workers, HTTP/JDBC pool/platform scheduler threads, GC workers, JIT compiler threads, JVM service threads, and JNI threads. The OS thread count must be measured from a real process.

### Pool Sizing Before Stack Tuning

In many backends, instead of lowering `-Xss` too far to fit 5,000 workers, one should ask:

- Why must there be **5,000 platform threads**? Is there a thread leak or an unbounded pool?
- Is the work mostly waiting on I/O or running on CPU?
- Does the downstream DB only allow 50 connections or does it have larger capacity?
- Can a bounded executor/queue, backpressure, or asynchronous APIs be used?
- If the application upgrades to Java 21+, would virtual threads be useful, and are heap/DB limits still sufficient?

`-Xss` is part of the problem, not a magic trick that makes native threads consume zero memory.

## 7. Runnable Java 17: Keeping Eight Platform Threads Alive Concurrently

Create the file **`ThreadStackBudgetDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public final class ThreadStackBudgetDemo {
    public static void main(String[] args) throws Exception {
        int workers = 8;
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> threads = new ArrayList<>();

        for (int i = 0; i < workers; i++) {
            Thread t = new Thread(() -> {
                ready.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }, "budget-worker-" + i);
            t.start();
            threads.add(t);
        }

        ready.await();
        System.out.println("workersReady=" + workers);

        long pauseMs = Long.getLong("demo.pauseMs", 0L);
        if (pauseMs > 0) {
            System.out.println("inspectionWindowMs=" + pauseMs);
            Thread.sleep(pauseMs);
        }

        release.countDown();
        for (Thread t : threads) t.join();
        System.out.println("workersJoined=" + threads.size());
        System.out.println("allTerminated=" +
                threads.stream().noneMatch(Thread::isAlive));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 ThreadStackBudgetDemo.java
java -Xss512k ThreadStackBudgetDemo
~~~

**Exact stdout of a default run without setting `demo.pauseMs`:**

~~~text
workersReady=8
workersJoined=8
allTerminated=true
~~~

The eight `new Thread` instances are **platform threads** on Java 17; all reach `CountDownLatch.await()` and wait for main to release them. The program does not intentionally create thousands of threads and has no infinite loop.

`CountDownLatch` provides a clear verification milestone: `workersReady=8` guarantees all eight have reached the wait point before main continues. It does not prove the OS thread count of the entire JVM is eight.

### Creating a Window to Measure NMT/OS on the Same JVM

~~~bash
java -Xss512k -Xms64m -Xmx128m \
  -XX:NativeMemoryTracking=summary \
  -Ddemo.pauseMs=10000 ThreadStackBudgetDemo
~~~

On PowerShell:

~~~powershell
java -Xss512k -Xms64m -Xmx128m -XX:NativeMemoryTracking=summary -Ddemo.pauseMs=10000 ThreadStackBudgetDemo
~~~

During the 10 seconds after `workersReady=8`, in another terminal find the **actual PID** and take a snapshot:

~~~text
jcmd
jcmd PID VM.native_memory summary scale=KB
jcmd PID Thread.print
jcmd PID VM.flags
~~~

`PID` is a placeholder to be replaced with the actual process ID. `Thread.print` can print stacks/metadata of Java/platform threads, suitable for Java 17; review security policies when saving thread dumps. NMT must be **enabled from JVM startup** to work.

### Actual Measurement Results from One Run

On **JDK 24 Windows**, Java 17 source target, with the process started with `-Xss512k -Xms64m -Xmx128m` and creating eight waiting workers, one snapshot gave:

~~~text
NMT Total: reserved=1607709KB, committed=169577KB
NMT Java Heap: reserved=131072KB, committed=67584KB
NMT Thread: reserved=17997KB, committed=1333KB
NMT stack: reserved=17920KB, committed=1256KB
OS native thread count: 30
OS WorkingSet64: 40738816 bytes
~~~

The figures above were collected from **a running process** using `jcmd` and Windows `Get-Process`, not from Java stdout output. In that same process, the Java source printed `workersReady=8`, `inspectionWindowMs=5000`, then `workersJoined=8`, `allTerminated=true`.

**How to read it:**

1. The OS had **30 native threads**, including the eight app workers **and** JVM/JIT/GC/runtime/native threads.
2. NMT `Thread reserved 17997 KiB` does not equal `8 × 512 KiB` because the JVM has other threads, rounding, and stack/VM structures.
3. Stack `reserved 17920 KiB` is much larger than stack `committed 1256 KiB`: **do not treat reserved as resident RAM**.
4. NMT `Total committed 169577 KiB` **includes Java Heap committed**; do not add 67584 KiB on top.
5. Windows Working Set 40,738,816 bytes reflects process resident pages at the snapshot, **not** NMT committed.
6. The measurements are for **one specific run/JDK/OS** and do not predict exact stack usage on Linux or a Java 17 runtime.

The learning point is **measurement sources and scope**, not claiming “each worker always needs 512 KiB committed” or “HotSpot always has exactly 30 native threads”.

## 8. Native Memory Beyond the Stack: What Must Not Be Overlooked?

To configure resources for a server, budget must be allocated for regions other than `Java Heap`:

| Component | How it is affected | Observation tools |
| --- | --- | --- |
| **Metaspace / class metadata** | Number of classes, classloaders, dynamic proxies, class generation | NMT `Class`, JMX memory pools |
| **Compressed class space** | Large reserved address space may have small commit | NMT `Class` reserved/committed |
| **JIT code cache** | Native compiled code, compiler tiers, warm-up | NMT `Code`, `jcmd Compiler.codecache` if supported |
| **GC structures** | Collector, heap region sizes, remembered sets, concurrency | NMT `GC`, GC logs |
| **Native thread stacks** | Platform thread count, configured stack sizes, call depth | NMT `Thread` stack reserved/committed, OS thread count |
| **DirectByteBuffer / NIO** | Direct buffer allocations and lifetimes | `BufferPoolMXBean`, OS/native tools |
| **JNI/JNA/native libs** | `malloc`, native caches, 3rd-party clients | OS/native allocation profilers; NMT may miss these |
| **Mapped files, shared libs** | File mappings and physical residency | Linux `/proc/PID/smaps_rollup`, PSS; Windows process counters |
| **JVM internal/runtime** | Symbol tables, compiler arenas, service allocations | NMT categories by JDK |
| **OS/container memory charges** | File cache, kernel memory, sidecars/child processes | cgroup `memory.stat`, `memory.current` |

**NMT is not all native memory of every library**. Oracle JDK 17 explicitly notes that NMT primarily tracks HotSpot VM internal allocations and does not fully cover third-party native memory. Therefore, heap + NMT still does not necessarily describe total RSS/cgroup usage.

### Configuring Limits for Several Separate Regions

~~~bash
java -Xms256m -Xmx512m \
  -Xss512k \
  -XX:MaxDirectMemorySize=128m \
  -XX:MaxMetaspaceSize=128m \
  -XX:ReservedCodeCacheSize=64m \
  -jar service.jar
~~~

These values are **only intentional examples**, not “the best set of flags”. `service.jar` must be a real application artifact. Note:

- `MaxDirectMemorySize` limits part of the JVM's direct-buffer allocation mechanism; it does **not** limit all JNI/native `malloc`.
- `MaxMetaspaceSize` can cause `OutOfMemoryError: Metaspace` if too low; it does not turn all class-loading memory into a perfect RSS cap.
- `ReservedCodeCacheSize` limits code cache capacity per the VM and can affect compiled code/JIT if insufficient; it is **not all compiler native memory**.
- `-Xmx`/`-Xss` do not control the OS page cache or all thread/process resources.
- These maximums do not guarantee each subsystem **uses up** that value; at the same time, there is other overhead **outside these maximums**.

**A better approach:** set budgets on paper, measure real NMT/OS under the same workload, and then adjust while accounting for headroom.

## 9. Memory Budget: Rough Calculation to Avoid OOM

Suppose a container has a **1 GiB = 1,024 MiB memory limit**, running one main JVM. An **illustrative allocation for experimentation**, not a real measurement:

| Budget group | Assumed MiB | Meaning |
| --- | ---: | --- |
| Java heap maximum | 512 | `-Xmx512m` |
| Direct-buffer allowance | 128 | Example NIO pool cap, does not cover all JNI |
| Metaspace allowance | 128 | Allocated for classes/metadata per VM |
| Code cache allowance | 64 | Reserve for compiled code |
| 100 nominal platform stacks × 512 KiB | 50 | **Reservation scale**, not fixed resident RAM |
| Other GC/VM/JNI/runtime/OS headroom | 80 | Estimated combined reserve |
| **Conservative total budget** | **962** | Assumed total, **not measured RSS** |
| **Remaining under 1,024 MiB** | **62** | Headroom per the assumed table |

**Important interpretation:**

- `100 × 512 KiB = 50 MiB` is a **nominal stack-space budget**, not automatically 50 MiB of RSS.
- Allowances **can overlap when taking actual numbers from NMT/JMX**; this table is an **upper-bound style plan by separately defined resource groups**, not a sum of tool counters.
- 62 MiB of headroom as in the example can be **too thin** when the app has many JNI libs, sidecars, peak memory, or part of the budget is off. One must also measure peak, steady state, startup spikes, OS/cgroup file cache, and margin of error.
- If you set `Xmx=900 MiB` inside a 1 GiB limit, the risk of OOMKilled is very concerning even when average heap is low.
- **Do not use the table to predict exact maximum thread count**. Collect native thread count, NMT Thread reserved/committed, RSS, and container memory under real load.

### Model-Style Formula for Headroom

One can write a budgeting expression (not a measurement identity):

\[
B_{\text{available}} = L_{\text{container}} - H_{\text{planned}} - N_{\text{planned}} - O_{\text{headroom}}
\]

Where `H_planned` is the heap allowance, `N_planned` is the **non-overlapping off-heap allowances as defined by the plan**, and `O_headroom` reserves for the operating system, runtime/third-party allocations, and peaks. If allowances are taken from NMT `Total`, which **already includes Java Heap**, one must **not** add heap again.

To make production decisions, **compare the table against peak `memory.current`/`memory.peak`, RSS/PSS, and NMT** rather than looking only at configured limits.

## 10. Where Can Thread Count Limits Come From?

The number of platform threads is not determined by a single portable `MaxThreads` flag in Java 17. Common limit sources:

1. **OS/process/thread quota**: each OS thread is a scheduling entity requiring kernel resources.
2. **Linux per-user limit** (`ulimit -u` and effective RLIMIT_NPROC depending on permissions/user namespaces).
3. **Linux system-wide** thread/pid limits (`/proc/sys/kernel/threads-max`, `pid_max`, and other limits).
4. **Cgroup pids controller** (`pids.max`, `pids.current`, `pids.events`), limiting tasks/PIDs in the cgroup.
5. **Native address space / memory commit**: many stacks/reservations and thread resources can fail even when heap has free space.
6. **CPU/scheduler overhead**: too many runnable threads cause context-switching/lock contention that degrades latency.
7. **Native library/runtime constraints**, such as JNI clients or internal pool sizes.

OS limits vary across Linux/Windows, container orchestration, architecture, and security. `ulimit -u` is **not necessarily the only effective limit**; the cgroup PID controller can also block first.

### Cgroup PID Differs from Container Memory

A container with low `memory.current` where `pids.current` is already close to `pids.max` can **fail to create new native threads**, even though RAM is still available. Conversely, a very large `pids.max` does not guarantee enough memory for all thread stacks.

Differential diagnosis:

~~~bash
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
cat /sys/fs/cgroup/pids.events
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
~~~

The paths are examples for **cgroup v2 mounted there**; for cgroup v1 or a different container mount namespace, the actual cgroup must be identified. `pids.max` may be `max` (no hard limit under that mechanism). `pids.current` counts tasks in the cgroup per kernel rules, not Java application worker threads.

Do not confuse a container CPU limit with a native thread count limit: a **low CPU quota** causes many runnable threads to contend for CPU, but does not directly define the maximum number of PIDs.

## 11. Observing on Linux and Windows

### 11.1. Linux: Thread Count + Process Memory

~~~bash
ps -o pid,nlwp,rss,vsz,comm -p PID
ps -L -p PID -o pid,lwp,stat,comm
cat /proc/PID/status
cat /proc/PID/smaps_rollup
~~~

In the commands above, replace **PID** with the actual process ID.

- `NLWP`: OS lightweight threads of the process at measurement time; **not just the eight workers**.
- `ps -L`: lists native/lightweight threads.
- `VmRSS`/`Rss`: resident footprint per OS.
- `VmSize`/`VSZ`: process address space mappings/reservations.
- `smaps_rollup`: RSS/PSS/private/shared memory breakdown, depending on kernel/permissions.
- Do not subtract heap used from RSS and call the difference “thread stacks”; there are many other native sources.

### 11.2. Windows PowerShell

~~~powershell
Get-Process -Id 12345 |
    Select-Object Id,
        @{Name='NativeThreads';Expression={$_.Threads.Count}},
        WorkingSet64, PrivateMemorySize64, VirtualMemorySize64
~~~

`12345` is only an **example PID** and must be replaced with the right process number. Windows `WorkingSet64`, `PrivateMemorySize64`, and `VirtualMemorySize64` have different meanings. Do not treat `VirtualMemorySize64` as resident RAM and do not treat `PrivateMemorySize64` as a synonym for Linux RSS.

### 11.3. JDK/HotSpot Tools

~~~text
jcmd
jcmd PID Thread.print
jcmd PID VM.native_memory summary scale=KB
jcmd PID VM.flags
jcmd PID GC.heap_info
~~~

All commands use the **actual PID** in the same OS/container PID namespace and require attach permissions. The `jcmd PID ...` commands are **shell instructions** after replacing PID, not Java source syntax.

`Thread.print` displays JVM-recognized Java/native thread stacks; use it to detect threads in WAITING/BLOCKED/RUNNABLE, pool growth, and repeated thread names. However, a thread dump is a **state snapshot**, not a measurement of each stack's RSS.

### 11.4. Java ThreadMXBean

Java 17 provides `ManagementFactory.getThreadMXBean()` and `getThreadCount()`, `getPeakThreadCount()`, `getTotalStartedThreadCount()`:

- Gives you JVM-level metrics on live threads, peak live threads, and cumulative started count.
- Not an exact 1:1 match for OS `NLWP` because the JVM also has service/native threads not exposed by the bean in the same scope.
- `getTotalStartedThreadCount()` is **not** the number of live threads: it accumulates the number of threads started since JVM initialization.
- On Java 21+ with virtual threads, legacy `ThreadMXBean` views do not by default fully count VTs by number of Java tasks; virtual-thread-aware tools are needed.

**Cross-check the OS count with JVM thread counts**, rather than expecting them to be equal.

## 12. NMT: Reserved/Committed and the Stack Line

HotSpot Native Memory Tracking can be enabled at startup:

~~~bash
java -XX:NativeMemoryTracking=summary \
  -Xss512k -Xms64m -Xmx128m ThreadStackBudgetDemo
~~~

While the process is alive, print `jcmd PID VM.native_memory summary scale=KB`. Part of the output typically has the structure:

~~~text
- Thread (reserved=..., committed=...)
    (thread #...)
    (stack: reserved=..., committed=...)
    (malloc=... #...)
    (arena=... #...)
~~~

**The numbers are placeholders describing the NMT format**, not the actual output of a specific JVM. The `Thread` category can include thread data structures, stacks, arenas, and metadata. “Thread stack reserved” and “Thread stack committed” are not synonymous.

### NMT Total Already Includes Java Heap

Example NMT:

~~~text
Total: reserved=..., committed=...
- Java Heap (reserved=..., committed=...)
- Thread (reserved=..., committed=...)
- Class (reserved=..., committed=...)
- Code (reserved=..., committed=...)
- GC (reserved=..., committed=...)
~~~

**Do not calculate** `Total committed + Java Heap committed` as process memory: heap is **already included in NMT total**.

NMT does **not** track all memory allocated by JNI/third-party native libraries, and reserved/committed differs from OS RSS. Cross-checking NMT against OS mappings is necessary if a native leak is suspected.

### Baseline/Diff When Pool Threads Increase

A baseline can be taken after the app is ready:

~~~text
jcmd PID VM.native_memory baseline
jcmd PID VM.native_memory summary.diff scale=KB
~~~

When increasing pool size under a controlled workload, check whether the `Thread` category increases and by how many native threads/stack reservations. However, if GC/compiler/class loading also changes, an NMT delta does not isolate thread stacks alone. **OS thread count, app thread metrics, named thread dumps, and workload timeline** are needed.

## 13. Safe Experiment to Measure the Impact of `-Xss`

Instead of trying to “create threads until the JVM dies”, use a lab with **a small, fixed number of workers**:

1. Choose 2 configurations `-Xss512k` and `-Xss1m` on the same JDK/OS.
2. Keep `Xms/Xmx`, collector, app binary, worker count (=8 in the example), and workload identical.
3. Enable NMT summary **for both runs**, not enabled on one run and disabled on the other.
4. Start a fresh JVM process for each run and keep `demo.pauseMs` identical.
5. Capture NMT `Thread reserved/committed`, OS native thread count, RSS/Working Set, and process VSZ.
6. Repeat several times; avoid using a single run to conclude exact bytes.
7. Combine with `StackDepthDemo` to show the effect of stack limit on call depth, without assigning a linear conversion depth=stack size.
8. Only use measurement results after verifying PID/time/OS/JDK flags.

**Intentionally spawning hundreds of thousands of platform threads until the OS refuses is a dangerous experiment** on a machine running services; do not perform it on a shared/dev host. Use low limits in an isolated test environment and cap the workers.

### Why Not Use `-Xss` to Reduce Heap?

Reducing stack size only changes part of the **native/OS thread stack budget**. It does not shrink Java heap object retention, direct-buffer allocations, metaspace, code cache, or sidecar cgroup memory. Identify the **real bottleneck** before changing flags.

## 14. Many Wrong Answers When Tuning Thread Stacks

### 14.1. “If the container is 1 GiB, just set `-Xmx1g`”

Wrong: the entire process also has non-heap/native memory, stacks, GC/code cache, and file mappings; it can get OOMKilled. Leave **enough measured headroom**, rather than using nearly 100% of the memory limit for heap max alone.

### 14.2. “If the heap still has 50% free, the JVM cannot fail to create threads due to memory/threads”

Incomplete: native threads are limited by OS memory/address space/PID quotas, not just free heap. Even lowering `-Xmx` does not guarantee resolving a `pids.max` limit.

### 14.3. “`-Xss512k` means each platform thread is using exactly 512 KiB of RAM”

Wrong: that is the configured stack size, not the per-thread RSS value. Inspect NMT reserved/committed and OS resident metrics separately.

### 14.4. “The smaller `-Xss` is, the better, because more workers can be created”

Wrong: some valid call chains, recursion, frameworks, and native transitions may need a deep stack. Too small a setting may be rejected by the VM or cause `StackOverflowError`.

### 14.5. “The larger `-Xss` is, the faster Java methods run”

Wrong: increasing stack capacity does not by default improve throughput. It can increase memory reservations and reduce the number of feasible native threads. Measure real performance/stack depth.

### 14.6. “`-Xss` = maximum number of threads”

Wrong: there is no exact calculation without knowing OS quotas, committed/resident native memory, process limits, JVM service threads, and memory headroom.

### 14.7. “`-XX:MaxDirectMemorySize` caps every native allocation”

Wrong: only part of the direct buffer mechanism is covered; JNI libraries can have native allocations outside it.

### 14.8. “If NMT Thread reserved is 20 MiB, process RSS increases by exactly 20 MiB”

Wrong: reservation is not resident memory. Conversely, other untracked native allocations can increase RSS while the Thread category stays unchanged.

### 14.9. “Every thread in the JVM is created by the application thread pool”

Wrong: there are also JVM runtime, compiler, GC, management, and native library threads. OS thread count is usually greater than the number of app-created workers.

### 14.10. “Java 21 virtual threads use a separate `-Xss` native stack per task”

Wrong: virtual threads have stack chunks/continuations on the heap and are mounted onto carriers; they do not use a native stack per VT for their entire lifetime.

### 14.11. “Cgroup memory OOM and pids OOM are the same thing”

Wrong: the memory controller and pids controller have different counters/events/limits. Inspect them separately.

### 14.12. “`ThreadMXBean.getTotalStartedThreadCount()` equals current live threads”

Wrong: cumulative started count differs from live count. Compare multiple metrics to detect churn/leaks.

## 15. Checklist Before Adjusting `-Xss` or Worker Thread Count

- [ ] Identify JVM vendor/version/build, OS/architecture, collector, and cgroup/container.
- [ ] Record effective `-Xss`, `-Xms`, `-Xmx`, metaspace/direct/code cache flags.
- [ ] Identify platform threads vs virtual threads (if Java 21+).
- [ ] Measure OS native thread count, peak thread count, and Java thread names/pools.
- [ ] Check for thread leaks, unbounded executors, blocking I/O, and backpressure.
- [ ] Check valid thread stack depth and cases of recursion/large call chains.
- [ ] Do not reduce stack below what the VM/platform accepts.
- [ ] Measure NMT Thread reserved **and** committed, without confusing them with RSS.
- [ ] Measure process RSS/PSS/Working Set with the same timestamp and PID.
- [ ] Measure container memory.current/peak/stat/events and pids.current/max/events.
- [ ] Check metaspace, GC, code cache, direct buffers, and JNI native memory.
- [ ] Reserve headroom for startup spikes, peak workloads, and shared/kernel charges.
- [ ] Record specific errors: StackOverflowError, unable to create native thread, heap/metaspace OOME, cgroup OOMKilled.
- [ ] Test under a production-like CPU quota; many runnable threads still have scheduler cost.
- [ ] Run multiple trials, evaluating p99/p99.9 latency/throughput and error rate.
- [ ] Do not stress to exhaustion on production/shared hosts.
- [ ] After tuning, re-verify service quality and resilience.

## 16. Self-Check Questions and Answers

1. What does `-Xss` configure? **Thread stack size**, subject to VM/OS rounding/limits.
2. Does `-Xmx512m` limit total RSS under 512 MiB? **No**.
3. What is the configured stack scale for 100 workers with nominal `-Xss512k`? **50 MiB**, not a guaranteed 50 MiB resident.
4. If a JVM has eight workers, does the OS only have eight threads? **No**, there are also VM/GC/JIT/service threads.
5. Does NMT Thread reserved = NMT Thread committed? **No**.
6. Is NMT Thread reserved 18 MiB equal to 18 MiB of resident physical RAM? **No**.
7. Can `-Xss256k` cause StackOverflowError earlier than `-Xss1m`? **Yes**, depending on call frames/JIT/VM.
8. Does StackOverflowError mean heap OOME? **No**.
9. Is `unable to create native thread` only caused by running out of RAM? **No**, also OS/cgroup PID/thread limits.
10. Is `pids.max` the same as `memory.max`? **No**, they are two different controllers/limits.
11. Is `ThreadMXBean.getTotalStartedThreadCount()` the current live threads? **No**.
12. Does `-XX:MaxDirectMemorySize` limit all JNI `malloc`? **No**.
13. Does NMT total include Java Heap? **Yes**; do not add heap again.
14. Does NMT completely see third-party native allocations? **No**.
15. Does cgroup memory.current equal JVM RSS? **Not necessarily**, cgroup includes cache/kernel/other processes.
16. Does `-XX:ThreadStackSize=512` mean 512 bytes? **No**, the HotSpot flag's base unit is KiB.
17. Do virtual threads have a fixed separate native stack per VT? **No**.
18. Does one million virtual threads mean zero memory used? **False**, there are objects, stack chunks, locals, and payloads.
19. Can shrinking a worker pool reduce the native stack budget? **Yes**, if it reduces the number of live platform threads.
20. Does a thread in WAITING automatically release its native stack like an exited thread? **No**, under the platform threads model.
21. Does an increasing NMT summary.diff by itself prove a thread leak? **No**, it must be correlated with thread count/pool/workload.
22. Should one create threads until the process crashes on a shared machine? **No**.
23. Should both reserved and committed be checked when reading NMT? **Yes**.
24. What should `-Xss` decisions be based on? **Valid call stack depth, OS limits, native memory, thread count, and measurements**.

## 17. Official Documentation Sources

- Oracle Java SE 17, **`java` command**, `-Xss`, `-XX:ThreadStackSize`, `-Xms`, `-Xmx`, direct/memory flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17, **Native Memory Tracking**: https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html
- Oracle JDK 17, **Diagnostic Tools / NMT categories**: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Oracle JDK 17, **`jcmd`**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Java SE 17, **`Thread`** constructor and platform-thread lifecycle: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17, **`ThreadMXBean`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 17, **`MemoryMXBean`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Java Virtual Machine Specification 17, **JVM Stacks (§2.5.2)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.2
- Oracle Java SE 21, **Virtual Threads** (difference in carrier native stacks): https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Linux kernel, **cgroup v2 pids controller**: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#pid
- Linux kernel, **cgroup v2 memory controller**: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory

**Conclusion:** `-Xss` controls **the stack budget of a single platform thread**, while the number of platform threads determines the total scale of stack reservations; both must be considered together with heap, metaspace, code cache, direct/native allocations, and OS/container limits. **Reserved, committed, and RSS are three different quantities**. When encountering StackOverflowError, check call depth; when unable to create a native thread, check both native memory and PID/thread quotas; when OOMKilled, check cgroup/RSS and off-heap memory. Reliable tuning uses **NMT + OS thread counts + JMX/GC + cgroup counters** under real workload, not inferring from `Xmx` or `N × Xss` alone.
