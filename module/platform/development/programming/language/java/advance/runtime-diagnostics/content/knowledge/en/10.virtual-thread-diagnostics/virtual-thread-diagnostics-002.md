# 10.2. Why Platform Thread Count Does Not Represent Total Virtual Threads

In earlier Java applications, operators often took the thread count from `ThreadMXBean`, JConsole, `top -H`, or a thread dump and inferred concurrency from it: "The JVM only has 80 threads, so there must only be around 80 tasks running or waiting." That inference is **false** when an application uses **virtual threads**.

A JVM can have **thousands of live virtual threads, mostly waiting on I/O**, while needing only a relatively small number of **platform carrier threads** to execute Java code when virtual threads become ready to run. Conversely, the platform thread count also includes HTTP workers, JVM service threads, and other threads—not every platform thread is a carrier. Therefore, **there is no simple formula to convert "number of platform threads" into "total number of virtual threads."**

This lesson belongs to **10. Virtual thread** and focuses directly on the question: **why does counting platform threads fail to reflect total virtual threads, and how should you observe both thread types to diagnose accurately?**

> **Version requirement:** Virtual threads became a permanent feature in **JDK 21 (JEP 444)**. The `Thread.ofVirtual()`, `Thread.isVirtual()`, and `Executors.newVirtualThreadPerTaskExecutor()` APIs in this lesson require **JDK 21+** and **do not compile on Java 17**. Java 19/20 offered virtual threads as a preview under different conditions; do not treat them as Java 17 APIs.

## 1. Two Types of Java Threads, Two Management Models

Starting in Java 21, a `java.lang.Thread` object can be either a **platform thread** or a **virtual thread**.

| Aspect | Platform thread | Virtual thread |
| --- | --- | --- |
| Java unit | A `Thread` | A `Thread`, still possessing identity/stack/exception |
| OS mapping | Typically bound to one OS thread for its entire lifetime | Does **not** hold a fixed OS thread for its entire lifetime |
| Who schedules it? | The OS schedules the OS thread | The JVM schedules the virtual thread onto a platform **carrier**; the OS schedules the carrier |
| When waiting on JDK-supported I/O | The platform/OS thread may have to wait | The JVM typically **suspends/unmounts** the virtual thread, freeing the carrier |
| Creation/stack cost | Relatively high, OS stack/native resources | Lighter, stack can grow/shrink as needed |
| Best suited for | Diverse tasks, threads that must be long-lived | Very large numbers of concurrent tasks, mostly **waiting on I/O** |
| Typical counts | Practically limited by OS threads and resources | Can be many times larger than the platform thread count |
| Ability to increase CPU | Does not increase core count | Does **not** make CPU work faster or create more cores |

A virtual thread is not a "fake thread" in program semantics. It is a real `Thread` in Java: it has `Thread.currentThread()`, interrupts, `join`, `ThreadLocal`, stack traces, an uncaught exception handler, and standard synchronization rules. The primary difference lies in **how the JVM binds that execution to OS threads**.

### 1.1. Platform Threads: Typically One Java Thread Maps to One OS Thread

Traditional example:

~~~java
Thread platform = Thread.ofPlatform()
        .name("platform-worker")
        .start(() -> doWork());
~~~

This is an **illustrative snippet, not a standalone program**; `doWork()` represents application logic. While `platform-worker` exists, it typically occupies an OS thread; when making blocking I/O calls, that thread may be put to wait by the OS, yet the underlying OS thread remains bound to the platform thread.

A thread pool backed by platform threads can keep many workers waiting for tasks. A pool size of 100 does not mean 100 requests are being actively processed successfully: some may be idle, some blocked, and some running.

### 1.2. Virtual Threads: One Java Thread Is Not One OS Thread

Java 21 example:

~~~java
Thread virtual = Thread.ofVirtual()
        .name("request-42")
        .start(() -> doWork());
~~~

Also an illustrative snippet; JDK 21+ is required for `Thread.ofVirtual()`. A virtual thread can be **mounted** onto a carrier platform thread when it needs to execute, then **unmounted** when waiting on a runtime-supported operation so the carrier can switch to another virtual thread.

`Thread.currentThread()` inside a virtual thread returns **that virtual thread**, not the carrier. Java code generally **has no standard API to ask "who is my current carrier thread?"**; do not attempt to equate a virtual-thread ID with an OS/native thread ID.

## 2. Mount, Unmount, and Carrier: The Core Reason Counts Diverge

Conceptual model:

~~~text
JVM logical work:
  VT-1  ─── run ─── wait HTTP ─────────── resume ── finish
  VT-2  ── run ─── wait DB ──────────────────────── resume
  VT-3  ───────────── run ─── wait queue ────────── resume
  VT-4  ───────────────────── run ─── done
  ...
  VT-1000 ── wait I/O / timer / signal

JVM scheduler:
  carrier-P1 ── VT-1 ── VT-3 ── VT-41 ── ...
  carrier-P2 ── VT-2 ── VT-4 ── VT-19 ── ...
  carrier-P3 ── VT-8 ── VT-7 ── VT-55 ── ...
  ...

Operating system:
  carrier-P* are OS threads scheduled by the OS onto CPU cores
~~~

This diagram is **illustrative** and does not assert that a virtual thread has fixed affinity to a carrier. A virtual thread can run on **different carriers across different scheduling turns**. A carrier can serve **many** virtual threads over time.

**Mount:** The JVM attaches the execution of a ready virtual thread to a carrier. Java code then runs on the OS thread backing that carrier.

**Unmount:** When the virtual thread performs a blocking operation that supports suspension, the JVM saves the relevant execution state and detaches the carrier so the carrier can run another virtual thread. Once the wait condition completes, the virtual thread returns to a schedulable state.

**A parked/waiting virtual thread is still alive:** it may not be finished yet, waiting on a socket, `CountDownLatch`, sleep, or I/O, yet **it does not occupy a carrier for the entire wait** if that operation supports unmounting and is not pinned.

Therefore, at the same instant you can have:
- 2,000 virtual threads alive according to application logic;
- most of them waiting on remote I/O;
- a few dozen platform threads in the JVM, including carriers and many other purpose-built threads;
- only a small number of virtual threads actively executing code at any single moment.

This is **not a real-world measurement**, and there is no default ratio like "1 platform = 100 virtual"; the ratio varies with load, JDK, OS, wait patterns, scheduler, resources, configuration, and application code.

### 2.1. Why "Waiting Virtual Threads" Do Not Increment OS Thread Count One-for-One

With traditional platform threads, each waiting thread typically still holds a corresponding OS thread. With virtual threads, a runtime-supported I/O or timer wait can **unmount** the virtual thread, allowing the underlying OS thread to serve other work. Many virtual threads are "alive," yet they **do not simultaneously occupy OS threads**.

Not every wait unmounts automatically. Scenarios involving **pinning**, native/foreign blocking, incompatible libraries, or CPU-bound code can keep a carrier occupied for a long time, reducing scalability. See Section 9 for JDK version considerations.

### 2.2. Why Carrier Count Also Does Not Equal RUNNABLE Virtual Threads

The scheduler has its own parallelism policy, processor count, and current state. The number of actively running carriers can be smaller than the number of ready virtual threads because CPU cores are finite. The platform thread count observed at the OS level also includes compiler/GC/JVM service/background threads and application-owned platform threads.

You cannot take the platform thread count and:
- subtract a few JVM threads to get the carrier count;
- multiply by a constant factor to estimate virtual thread count;
- treat carrier count as the number of in-flight requests;
- infer from carrier count that no queuing or blocking is happening.

**Carrier count, live virtual count, in-flight task count, and core count are distinct quantities.**

## 3. Four Counts That Are Commonly Conflated

| Metric | Question It Answers | Limitations |
| --- | --- | --- |
| **Live platform threads** | How many platform threads does the JVM currently have? | Excludes virtual threads |
| **Live virtual threads** | How many virtual `Thread` instances have not yet terminated at measurement time? | Does not necessarily equal running requests, CPU-bound work, or mounted threads |
| **Active/in-flight tasks or requests** | How many business units of work are incomplete? | One request may use multiple tasks/threads, or none of its own |
| **OS native threads** | How many threads does the kernel have for the process? | Does not list unmounted virtual threads as OS threads |
| **Carrier pool size/parallelism** | How many carriers does the scheduler have or target for parallel execution? | Does not count total virtual threads and depends on version/config |

### 3.1. An Arithmetic Example Showing Why Conversion Fails

Consider an **illustrative** scenario:
- 1,000 requests have started, each using one virtual thread.
- 950 virtual threads are waiting on I/O/timers; the remaining 50 are ready or executing.
- The JVM has 24 platform threads (including carriers, GC/compiler, and background threads).

You **cannot** conclude there are 24 virtual threads, nor multiply 24 by a constant to get 1,000. As old requests finish and new ones arrive, the virtual thread count changes independently of the platform thread count over time.

Even if `platform_count=24` across two snapshots, virtual count can swing from 100 to 5,000 and back to 200 without a proportional jump in OS thread count. That can be completely normal for an I/O-bound workload. Conversely, if 5,000 virtual threads are all stuck waiting on an unresponsive dependency, the system can be **severely stalled** despite few carriers and low CPU.

### 3.2. Total "Started Since Startup" Differs from "Currently Live"

- **Started total** is a cumulative counter that only increases.
- **Live** is the count currently existing/unterminated, which rises and falls.
- **Runnable/scheduled** is the count ready or actively running per the scheduler.
- **Mounted** is the count attached to a carrier at a given instant.
- **Blocked/waiting** is a waiting state; it may be unmounted or pinned.

If a service handles 1 million requests/day, total started virtual threads may be 1 million, while live count at any snapshot is only a few thousand. Do not mix **total started** with **current live** when comparing charts.

## 4. Critical Blind Spot of `ThreadMXBean`

The **Java SE 21** specification explicitly states that `java.lang.management.ThreadMXBean` manages and monitors **platform threads**, and does **not** support monitoring or managing virtual threads. This holds true even when code creates vast numbers of virtual threads.

| Java Management API | Meaning in Java 21+ | Counts/Lists Virtual Threads? |
| --- | --- | --- |
| `getThreadCount()` | Current number of **live platform threads** | **No** |
| `getPeakThreadCount()` | Peak number of live platform threads | **No** |
| `getTotalStartedThreadCount()` | Total platform threads started since JVM launch | **No** |
| `getDaemonThreadCount()` | Live daemon **platform threads** | **No** |
| `getAllThreadIds()` | IDs of live **platform threads** | **No** |
| `dumpAllThreads(...)` | Stacks and lock info of **platform threads** | **No** |
| `getThreadInfo(virtualId)` | Looks up `ThreadInfo` by Java ID | **`null`** for a virtual thread |
| `findDeadlockedThreads()` | Finds deadlock cycles among platform threads/synchronizers supported by the API | **Does not** cover all virtual-thread deadlocks |

This is not an MXBean bug or a sign that virtual threads failed to start. It is the **official scope of the API**. Consequently, a "JVM Thread Count" chart in a metrics system backed by `java.lang:type=Threading` usually reflects **platform threads**; knowing total virtual threads or requests requires separate instrumentation.

### 4.1. Illustrative Code for Naming Metrics Accurately

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

int platformLive = bean.getThreadCount();
int platformPeak = bean.getPeakThreadCount();
long platformStarted = bean.getTotalStartedThreadCount();
~~~

This is an **illustrative** snippet requiring `java.lang.management.ManagementFactory` and `ThreadMXBean` imports, not a standalone Java file. Naming the variable `platformLive` instead of `allThreads` prevents scope confusion.

If you hold a reference to a live virtual thread `vt`:

~~~java
boolean isVirtual = vt.isVirtual();
long javaId = vt.threadId();
ThreadInfo missingFromMxBean = bean.getThreadInfo(javaId);
// missingFromMxBean == null for a virtual thread per the Java 21 contract.
~~~

This is also an illustrative snippet requiring `java.lang.management.ThreadInfo` and a `vt` variable. Note that `getThreadInfo(id) == null` can also occur if a platform thread has already died or the ID does not exist; you **cannot** use `null` alone to conclude an unknown ID is a virtual thread. In the example, we hold the `vt` reference and verify `vt.isVirtual()`.

### 4.2. `ThreadGroup.activeCount()` Does Not Solve This Either

In Java 21, virtual threads belong to a special thread group, yet **they are not counted by `ThreadGroup.activeCount()` and are not enumerated by `ThreadGroup.enumerate()`**. Thus, legacy tricks like `Thread.activeCount()` or `ThreadGroup.enumerate` do not act as a JVM-wide virtual thread counter.

**Do not infer virtual thread count** from:
- `ThreadMXBean.getThreadCount()`;
- `Thread.activeCount()`/`ThreadGroup.activeCount()`;
- `ThreadGroup.enumerate(...)`;
- `ps -L`/`top -H` or OS thread listings;
- traditional platform-only thread dumps.

Every tool has its own scope; a metric that excludes virtual threads should never be named `total_java_threads`.

## 5. Standalone Java 21+ Program: 200 Virtual Threads vs. Platform Count

This program intentionally spawns **200 virtual threads**; each thread signals that it has started and then **waits on a `CountDownLatch`** so it remains alive while `main` samples the counts. They do not spin in a hot CPU loop, nor do they manually create 200 platform threads.

Meanwhile:
- `Thread.isVirtual()` confirms each thread is virtual.
- `Thread.isAlive()` confirms the count of virtual threads in the set **referenced by the demo**.
- `ThreadMXBean.getThreadInfo(vt.threadId())` formally verifies that virtual threads **have no ThreadInfo via the MXBean**.
- `ThreadMXBean.getThreadCount()` measures the **number of platform threads**, printed to **stderr** because the value depends on the JVM/OS.
- Finally, `release.countDown()` lets the threads exit; `main` calls `join` to clean up.

**This only counts the 200 virtual threads created by the program itself**, not an API for enumerating every virtual thread across an entire production JVM.

Save the file **`VirtualVsPlatformCountDemo.java`**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class VirtualVsPlatformCountDemo {
    private static final int TASKS = 200;

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        int platformBefore = bean.getThreadCount();

        CountDownLatch started = new CountDownLatch(TASKS);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> virtuals = new ArrayList<>(TASKS);

        try {
            for (int i = 0; i < TASKS; i++) {
                Thread vt = Thread.ofVirtual()
                        .name("demo-vt-" + i)
                        .start(() -> {
                            started.countDown();
                            try {
                                release.await();
                            } catch (InterruptedException ex) {
                                Thread.currentThread().interrupt();
                            }
                        });
                virtuals.add(vt);
            }

            if (!started.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Not all virtual threads started");
            }

            long alive = virtuals.stream()
                    .filter(Thread::isAlive).count();
            boolean allVirtual = virtuals.stream()
                    .allMatch(Thread::isVirtual);
            long exposedViaMxBean = virtuals.stream()
                    .filter(t -> bean.getThreadInfo(t.threadId()) != null)
                    .count();

            System.out.println("virtual_started=" + TASKS);
            System.out.println("virtual_alive=" + alive);
            System.out.println("all_virtual=" + allVirtual);
            System.out.println(
                    "virtual_entries_in_thread_mxbean=" + exposedViaMxBean);

            // Dynamic numbers: carrier and platform counts vary by runtime.
            int platformDuring = bean.getThreadCount();
            System.err.printf(
                    "platform_before=%d platform_during=%d%n",
                    platformBefore, platformDuring);
        } finally {
            release.countDown();
            for (Thread vt : virtuals) {
                vt.join();
            }
        }
    }
}
~~~

Compile and run with **JDK 21 or later**:

~~~bash
java -version
javac VirtualVsPlatformCountDemo.java
java VirtualVsPlatformCountDemo
~~~

**Exact stdout when the program succeeds under normal scheduling conditions:**

~~~text
virtual_started=200
virtual_alive=200
all_virtual=true
virtual_entries_in_thread_mxbean=0
~~~

**Stderr contains one line with environment-dependent numbers**, for example **illustrative, not fixed values**:

~~~text
platform_before=7 platform_during=15
~~~

You may observe higher or lower numbers; you neither need nor should force `7` or `15`. The OS/JVM may have different GC/compiler/background threads, and the scheduler may vary carrier counts. The lines across stdout and stderr may also interleave differently in your terminal.

**Result explanation:**
1. `started.await(...)` only returns cleanly once all 200 virtual threads have executed up to `started.countDown()`. They cannot finish before `main` releases the latch (barring unusual external intervention).
2. Because `release` has not been triggered yet, all 200 threads remain alive; `all_virtual=true` because they were created with `Thread.ofVirtual()`.
3. `virtual_entries_in_thread_mxbean=0` is **by Java 21 API design**: `ThreadMXBean` does not manage virtual threads, even though those threads are alive and have Java thread IDs.
4. `platform_during` is a snapshot of **live platform threads**; it does not mean "only this many requests exist" or "200 virtual threads were converted into this many OS threads."
5. `release.countDown()` and `join()` ensure no virtual threads are left dangling after the demo finishes.

**Limits and safety:** the example creates a bounded 200 tasks and does not put heavy pressure on heap or CPU. If the JVM is so overloaded that it cannot start all virtual threads within 15 seconds, it throws an exception instead of printing those four lines. `join()` waits for virtual threads to finish; for a demo merely waiting on a released latch, this is valid cleanup. Production code should not spawn and retain millions of virtual threads carelessly, because **every virtual thread still consumes heap/stack/context and downstream work still consumes real resources**.

### 5.1. Why Only Count `virtuals.size()` in the Demo?

An application creates virtual threads, yet there is no `ThreadMXBean` equivalent API to enumerate them all. Keeping a `List<Thread>` for 200 tasks is strictly for **demo purposes** and would otherwise retain references longer than necessary. In production, do not retain references to every virtual thread just to maintain a counter; use **application metrics** incremented/decremented across the lifecycle, or JFR/diagnostic snapshots when investigating.

### 5.2. Creating One Virtual Thread per Task with an Executor

More idiomatic usage for Java 21 workloads:

~~~java
try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {
    var future = executor.submit(() ->
            Thread.currentThread().isVirtual());
    System.out.println(future.get()); // true on Java 21+
}
~~~

This is an **illustrative snippet inside a method declaring `throws Exception`**, not a standalone program. Each task is executed by this executor on **a new virtual thread**, not on a "reusable pool of 200 virtual threads." `try-with-resources` closes the executor and awaits tasks per the Java 21 contract; avoid creating a new executor per request in production when lifecycle can be managed centrally.

**Virtual threads are not a resource to be pooled like platform threads.** If you need to cap excessive concurrent DB calls, place the limit on **DB/HTTP/resource concurrency** (connection pools, semaphores, rate limits, bulkheads), rather than pooling virtual threads to throttle virtual thread count and turning them into an artificial bottleneck.

## 6. Why Traditional Thread Dumps Appear to Miss Virtual Threads

Observability tools have a "scope," just like metrics. On JDKs with virtual threads:

| Observation Source | What Is Visible? | What Not to Infer |
| --- | --- | --- |
| `ThreadMXBean.dumpAllThreads(...)` | Platform threads | That this is all virtual + platform threads |
| `jcmd PID Thread.print` / traditional HotSpot dump | Platform threads; on newer JDKs may show **mounted virtual threads** | That all unmounted/waiting virtual threads are listed |
| `jcmd PID Thread.dump_to_file -format=json FILE` | Dump supporting **both virtual and platform threads** | That it is a continuous counter or an atomic snapshot |
| `jcmd PID Thread.dump_to_file -format=text FILE` | Text dump supporting both kinds | That it has all native/monitor details of a traditional dump |
| `ps -L`, `top -H`, OS task list | Native/OS threads | That there is one OS thread per virtual thread |
| JFR virtual-thread events | Lifecycle and events supported per config/JDK | That every event is always enabled, complete, or free |
| App/trace metrics | Live/in-flight requests/tasks instrumented by the app | That they match 1:1 with every virtual thread in the JVM |

**Starting in JDK 21**, `jcmd` provides the `Thread.dump_to_file` command to generate text/JSON dumps containing virtual threads. This dump has different fields from traditional HotSpot dumps; lock/monitor details and output formatting **vary across JDK releases**. Never take a single `Thread.print` output and declare "there are only N Java threads."

Examples (PID and file paths are **illustrative values**; valid attach permissions and writable destination paths are required):

~~~bash
jcmd -l
jcmd 12345 help Thread.dump_to_file
jcmd 12345 Thread.dump_to_file -format=json /tmp/threads.json
jcmd 12345 Thread.dump_to_file -format=text /tmp/threads.txt
~~~

On Windows, adjust the paths accordingly. `Thread.dump_to_file` can write very large files when tens of thousands of virtual threads are alive; ensure sufficient disk space, non-public paths, retention policies, and frequency controls. If the command is missing, verify the actual **JDK/tool version** via `jcmd 12345 help` rather than guessing command names.

**Note on version differences:** on JDK 21, traditional `Thread.print` is not a reliable way to list all virtual threads; newer JDKs may display **mounted** virtual threads in HotSpot dumps. Still, **unmounted virtual threads** cannot be inferred or counted from OS/carrier thread lists alone.

### 6.1. When Should You Read a JSON Dump?

With virtual-thread-per-task, a JSON dump helps you:
- group by thread names/stacks and business call paths;
- spot many virtual threads waiting on the same dependency/queue;
- identify patterns of stalled work;
- correlate timestamps and trace IDs from logs;
- separate I/O pressure from scheduling/pinning pressure.

**Do not use a single snapshot to declare a deadlock**, and do not assume every virtual thread in the snapshot is burning CPU. Large dumps carry collection and processing costs; prefer generating them only with a clear diagnostic goal.

## 7. Proper Instrumentation: Measure Virtual Tasks Instead of Platform Threads

### 7.1. Name Metrics After What They Actually Measure

A sound dashboard should separate these groups:

| Suggested Metric | Meaning | Source |
| --- | --- | --- |
| `jvm.platform.threads.live` | Live platform threads | `ThreadMXBean.getThreadCount()` |
| `app.virtual.tasks.started_total` | Virtual tasks started (cumulative) | Counter at the application boundary |
| `app.virtual.tasks.completed_total` | Virtual tasks finished | Counter incremented in `finally` |
| `app.virtual.tasks.inflight` | Virtual tasks started but not yet finished | Lifecycle gauge/counter |
| `app.requests.inflight` | Incomplete business requests | Request lifecycle instrumentation |
| `app.requests.duration`, `timeout_total` | True latency and failures | Server/application telemetry |
| `dependency.connections.active/pending` | DB/HTTP resource pressure | Driver/client/pool metrics |
| `process.cpu`, `container.memory`, `gc.pauses` | Physical resources | JVM/OS/container metrics |

The names in this table are **recommendations**, not auto-generated metrics built into every framework. Distinguish tasks from requests: one request may spawn multiple virtual tasks, or one virtual thread may execute multiple steps within a request. With a per-task executor, counting **at submission**, **at start**, and **at completion** can differ; define the contract clearly.

### 7.2. Example of Instrumenting Task Lifecycle

The snippet below is **illustrative**, assuming `executor`, `Runnable work`, `LongAdder started/completed`, and `AtomicInteger inflight`:

~~~java
executor.submit(() -> {
    started.increment();
    inflight.incrementAndGet();
    try {
        work.run();
    } finally {
        completed.increment();
        inflight.decrementAndGet();
    }
});
~~~

When the executor creates **one new virtual thread per task**, this counter measures work that has **started running**, not tasks newly submitted that have not yet entered `Runnable`. It also excludes virtual threads spawned by other libraries outside this wrapper. If a task is rejected before `Runnable` executes, `started` does not increment; `submitted/rejected` metrics must be measured separately at the submission boundary.

**Measurement principles:**
- Cumulative started/completed counters differ from a current in-flight gauge; never merge them.
- Increment `inflight` before entering `try/finally` and decrement it in `finally` even if an exception or cancellation occurs inside `Runnable`.
- If the JVM process is killed, in-memory counters and `finally` cleanup do not persist final state; metrics require a suitable collection pipeline.
- Keep label cardinality bounded by service/route/outcome; never put every `threadId` or `requestId` into a metric label.

### 7.3. There Is No Automatic "JVM-Wide Virtual Thread Count" from `ThreadMXBean`

If you need total live virtual threads **at a point in time**, practical options are:
- application-level instrumentation (when you control creation sites);
- deliberately configured JFR lifecycle events when broader visibility is required;
- `Thread.dump_to_file` snapshots during investigations;
- scheduler management tools/APIs or telemetry supporting your **exact JDK version**.

Never maintain a thread registry holding strong references forever just to count threads: it wastes heap and blocks GC. Likewise, avoid logging every virtual-thread start/end under heavy load when metrics suffice, as millions of log events can become a bottleneck themselves.

## 8. When OS Metrics and Java Metrics Seem to "Contradict" Each Other

### Scenario A — Low CPU, 10,000 In-Flight Virtual Tasks

If many virtual threads are waiting on a remote API, CPU can remain low and platform thread count small. Yet the system may still be **experiencing a latency incident**: in-flight requests, timeouts, pending connections, and memory all climb. Diagnose with traces and dependency metrics, not just CPU and platform counts.

### Scenario B — Only 32 Platform Threads Yet High Throughput

With workloads full of short I/O waits, carriers are reused across many virtual threads, so throughput can be high even when platform count is far smaller than concurrency. That is a scalability benefit, not "the JVM forgetting to count requests."

### Scenario C — 2,000 RUNNABLE Virtual Threads and 100% CPU

Virtual threads **do not automatically speed up CPU-bound tasks**. With a finite number of cores, many ready virtual threads contend for the scheduler and CPU; you need to bound CPU-work concurrency, optimize algorithms, and use a profiler/JFR. Creating more virtual threads does not create more CPU cores.

### Scenario D — Virtual Count Grows Forever While Platform Count Stays Flat

This could be a **resource leak or liveness issue**: vast numbers of virtual threads waiting on a response with no timeout, a connection pool, or a latch that never completes. A flat platform count does not prove the application is healthy; inspect request age, dependency timeouts, in-flight virtual tasks, memory, and virtual stack dumps.

### Scenario E — Platform Count Rises Under Higher Load

This does not mean there is one platform thread per virtual thread. The scheduler may adjust carrier availability, or the runtime may have other platform threads for GC, JIT, networking, and application code. Examine foundations, thread names, stacks, and version before concluding pinning or misconfiguration.

### Scenario F — `ThreadMXBean.dumpAllThreads` Shows Few Threads, `Thread.dump_to_file` Is Huge

This is **consistent with the specification**: the MXBean returns only platform threads, whereas the virtual-thread-aware dump also lists live virtual threads. Compare **the same PID, start time, and snapshot window** rather than assuming one tool is broken because the numbers differ.

## 9. Pinning and Changes Across JDK Versions

**Pinning** occurs when a virtual thread cannot unmount from its carrier during a specific blocking operation. This can hurt scalability because the carrier remains occupied while the virtual thread waits.

**JDK 21–23:** Java 21 documentation highlights notable pinning scenarios:
- A virtual thread performs a blocking operation while inside a `synchronized` block or method.
- A virtual thread is inside a native or foreign function call.

This **does not corrupt program results**, but if many virtual threads pin carriers for long durations, usable carriers shrink and other tasks slow down.

**From JDK 24 (JEP 491):** monitor handling was improved so **virtual threads can unmount when blocking inside synchronized code**, eliminating the common Java-monitor cause of pinning. **Native/foreign blocking still requires inspection**, and exact behavior depends on the JDK build. Therefore, do not unconditionally repeat the advice "every `synchronized` pins virtual threads" for JDK 24+.

| Version | Key Points to Remember |
| --- | --- |
| Java 17 | No permanent virtual threads API yet |
| Java 19/20 | Virtual threads in preview (not enabled by default like JDK 21) |
| Java 21 | Virtual threads finalized; monitor pinning can affect unmounting |
| Java 24+ | JEP 491 improves `synchronized` so it does not pin under the old mechanism; still check native/foreign code and runtime |
| Newer releases | Dump/JFR/scheduler diagnostic tools may evolve; read docs for your exact version |

### 9.1. Signs Suggesting Pinning or Scheduler Pressure

- Poor throughput despite a large number of virtual threads.
- Many virtual threads sharing stacks inside a native/blocking path.
- Traces showing slow dependencies; CPU is not high yet carriers remain held.
- Relevant JFR events, such as `jdk.VirtualThreadPinned` exceeding the configured threshold on JDK 21, or `jdk.VirtualThreadSubmitFailed`.
- Certain `jcmd` diagnostics for virtual-thread schedulers/pollers are only available on specific JDKs; check via `jcmd PID help` rather than assuming JDK 21 has every newer command.

**Do not treat the absence of pinned events as proof that no problem exists**: events must be supported and enabled, thresholds must fit, and saturation can come from CPU, DB connections, bad timeouts, or memory unrelated to pinning.

### 9.2. Virtual Threads Do Not Eliminate All Resource Constraints

Even though virtual threads are cheaper than OS threads:
- Each virtual thread still uses heap and holds a stack/context/`ThreadLocal`.
- High concurrency can create **thousands of pending DB connections**, overwhelming downstream systems.
- Native calls, version-dependent monitors, JDBC drivers, or frameworks may introduce their own bottlenecks.
- CPU-bound code does not speed up merely by adding more virtual threads.
- Concurrency still requires **backpressure/rate limits/bulkheads** at actual resources.

**Do not pool virtual threads to "curb virtual thread count"**: if the goal is capping concurrent DB transactions at 50, bound DB/transaction concurrency via a semaphore or connection pool instead of keeping only 50 virtual workers. Virtual-thread-per-task is designed to create a fresh thread per unit of work.

## 10. JFR and Virtual-Thread Lifecycle Traces

Java Flight Recorder (JFR) provides events for virtual threads; on JDK 21, Oracle documentation describes:
- `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd`: lifecycle events, **disabled by default**.
- `jdk.VirtualThreadPinned`: signals pinning exceeding the configured threshold, defaulting to 20 ms in JDK 21 docs.
- `jdk.VirtualThreadSubmitFailed`: the JVM could not properly schedule/start/unpark a virtual thread due to resource constraints.

Configuration and availability vary by version. Once events are recorded:

~~~bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
~~~

`recording.jfr` is an already-captured file, **not created by this command itself**. Do not enable all start/end events under massive production traffic without accounting for event volume and overhead; prefer targeted diagnostics with appropriate sampling and retention.

**Data scope:** JFR start/end events show lifecycle activity, not necessarily an exact "live gauge" if the recording started after virtual threads were already alive or if events were dropped/sampled. If you need an accurate live count for a business scope, instrument creation and completion boundaries ahead of time.

## 11. Common Mistakes When Counting Platform vs. Virtual Threads

1. **"`ThreadMXBean.getThreadCount()` counts all Java threads."** On Java 21+, it counts only platform threads.
2. **"`getPeakThreadCount()` gives the peak virtual thread count."** That is still peak **platform** threads.
3. **"`getTotalStartedThreadCount()` includes created virtual threads."** No; it is cumulative **platform** threads started.
4. **"`getAllThreadIds()` lists every `Thread` object."** Virtual IDs are excluded from the MXBean result.
5. **"`getThreadInfo(id)==null` proves the thread does not exist."** It could be the ID of a living virtual thread.
6. **"`Thread.activeCount()`/`ThreadGroup.enumerate()` are more complete than the MXBean."** Neither provides the total virtual thread count.
7. **"The OS shows 32 threads, so there are only 32 concurrent requests."** Thousands of virtual tasks may be alive and waiting on I/O.
8. **"10,000 virtual threads require 10,000 CPU cores."** Waiting on I/O does not consume CPU continuously, though CPU work remains bounded by core count.
9. **"1 virtual thread stays pinned to 1 carrier."** The JVM can remount it onto a different carrier and maintains no affinity.
10. **"A virtual thread waiting on I/O always releases its carrier."** Not unconditionally; check pinning, native operations, and JDK support.
11. **"`Thread.print` shows few virtual threads, so the app isn't creating any."** Traditional dumps have a different scope from `Thread.dump_to_file`.
12. **"A single virtual count snapshot equals throughput."** Live count, total started, active tasks, and completed requests are distinct metrics.
13. **"Rising platform count proves a virtual thread leak."** Platform growth can come from other sources; attribute properly.
14. **"Flat platform count means no leak."** Virtual threads can pile up on waits, latches, or futures.
15. **"Virtual threads are free threads."** They consume heap/stack, allocations, context, and downstream resources.
16. **"Because JDK 21 `synchronized` pins, JDK 24+ behaves identically."** JEP 491 changed that mechanism.
17. **"Enabling JFR VirtualThreadStart/End for every request has zero cost."** Event volume is huge and needs a policy.
18. **"Thread ID can be used as an unbounded metric label."** Every task gets a new ID, causing cardinality explosion.
19. **"Few carriers means the scheduler is healthy."** Latency, CPU starvation, pinning, or downstream overload can still occur.
20. **"Increasing virtual count scales throughput infinitely."** Throughput remains bounded by CPU, network, DB, rate limits, and backpressure.

## 12. Investigating Properly When Two Tools Disagree on Thread Counts

Suppose a dashboard reports `jvm_threads_live=38`, while the application reports `virtual_tasks_inflight=4800`:

**Step 1 — Verify the source of both metrics.** If `jvm_threads_live` uses `ThreadMXBean.getThreadCount`, its name should accurately reflect **platform** scope. `virtual_tasks_inflight` may count application tasks rather than every virtual thread.

**Step 2 — Verify the JVM and version.** Java 17 has no permanent virtual-thread APIs, whereas Java 21+ does; check the JVM vendor and build. Dump formats and pinning behavior differ across JDKs.

**Step 3 — Identify the workload.** Are the 4,800 tasks waiting on DB/HTTP, doing CPU work, or stuck on a latch/future? How many requests have already missed deadlines? If most are legitimately waiting on I/O and healthy, a large virtual count can be normal.

**Step 4 — Gather metrics from the same time window.** Platform live (MXBean), app in-flight, pending DB connections, request p99, throughput, error rate, GC/heap, and CPU. Do not compare a "peak" against an instantaneous snapshot.

**Step 5 — Capture a virtual-thread-aware dump if needed.** Run `jcmd PID Thread.dump_to_file -format=json` with the right JDK, a safe path, and sufficient disk space. Group by stack/dependency rather than reading a huge file line-by-line by eye.

**Step 6 — Check scheduler/pinning for your version.** Use JFR and commands supported by your runtime, per-thread OS CPU, pool saturation, and native blocking. Do not blame every symptom on carrier count.

**Step 7 — Locate the business bottleneck.** Metrics and traces show whether requests are completing or stalled. A virtual thread waiting 1 ms in I/O is normal; 4,800 virtual threads waiting 60 seconds on a future that never completes is an incident.

**Step 8 — Fix the root cause.** Improve deadlines/cancellation, bound resource concurrency, fix blocking/native paths, shrink `ThreadLocal` payloads, and resolve connection pool leaks. Do not try to make virtual count "match" platform count via scheduler settings.

**Step 9 — Measure after the fix.** Request throughput, p95/p99, in-flight count, oldest wait age, memory/CPU, and error rate are the primary targets; total virtual threads do not need to equal total platform threads.

### Evidence and Confidence Table

| Observation | What You Can Conclude | What You Cannot Yet Conclude |
| --- | --- | --- |
| MXBean reports 40 platform threads; app has 2,000 virtual tasks | The two sources measure different scopes | That 1,960 virtual threads are "missing" |
| OS shows 30 native threads | The process has roughly that many OS threads at the snapshot | That there are only 30 logical Java threads |
| Virtual dump shows 5,000 waiting | Many logical threads are alive and waiting | Definitely deadlocked or definitely healthy |
| Virtual in-flight rises, completions stall | Work shows signs of failing to make progress | That the root cause is solely carrier shortage |
| CPU 100%, many virtual tasks ready | CPU may be the bottleneck | That raising virtual thread count will speed things up |
| JFR pinned event appears on JDK 21 | Pinning exceeded the threshold under recording settings | That all slowness is caused by pinning |
| JDK 24+ synchronized waits | JEP 491 mechanism differs from JDK 21 | That all native blocking is safe and never pins |

## 13. Implementation and Monitoring Checklist

**When developing applications:**
- [ ] Use JDK 21+ for stable virtual thread APIs; check library and framework compatibility.
- [ ] Use virtual threads for wait-heavy tasks, especially synchronous I/O; do not expect them to accelerate CPU-bound work.
- [ ] Use `Thread.ofVirtual()` or `Executors.newVirtualThreadPerTaskExecutor()` with a clean lifecycle.
- [ ] Do not pool virtual threads like platform threads; bound concurrency at real resources.
- [ ] Set timeouts, cancellation, backpressure, and error handling on waits.
- [ ] Avoid storing large `ThreadLocal` payloads across millions of virtual threads.
- [ ] Read pinning guidance matching JDK 21 vs. 24+; do not impose outdated advice on newer versions.

**When designing observability:**
- [ ] Name `ThreadMXBean` metrics `platform_thread_count` (or similar platform-specific names).
- [ ] Instrument virtual tasks started/completed/inflight with accurate lifecycle hooks.
- [ ] Distinguish tasks started, submitted, currently alive, and business requests in-flight.
- [ ] Collect latency, timeouts, backlog, downstream saturation, and CPU/GC/memory alongside thread metrics.
- [ ] Use JFR events or `Thread.dump_to_file` when virtual-thread visibility is needed.
- [ ] Bound metric label cardinality and dump/JFR file sizes.
- [ ] Never use OS thread lists, `ThreadGroup.activeCount`, or `ThreadMXBean.dumpAllThreads` as total virtual thread counts.
- [ ] Ensure logs/traces carry a correlation ID linking each virtual task to business context.
- [ ] Verify which JDK diagnostics are actually supported before adding commands to playbooks.

**When a "JVM thread count" chart looks low:**
- [ ] Is the source MXBean/platform-only or app-specific virtual metrics?
- [ ] How many virtual tasks are alive and how many requests are in-flight?
- [ ] Are most virtual threads waiting on healthy I/O or overdue dependencies?
- [ ] Are completed requests rising and is p99 within SLO?
- [ ] Are platform/CPU/GC/native resources saturated?
- [ ] Is there pinning/native blocking or queue saturation on that JDK version?

**Final takeaway:** A platform thread is typically an OS execution unit; a virtual thread is a **JVM-managed unit of concurrent work** that can mount and unmount across many carriers. `ThreadMXBean` and OS tools **count platform/native threads**, not all logical virtual threads. Therefore, **platform thread count does not represent total virtual threads**—you must track application virtual tasks, business progress, and resource metrics separately, and rely on virtual-aware dumps and JFR when investigating.

### Official References

1. Oracle Java SE 21, *Virtual Threads*: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
2. Oracle Java SE 21, *ThreadMXBean*: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html
3. Oracle Java SE 21, *ThreadGroup*: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadGroup.html
4. Oracle JDK 21, *jcmd*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
5. Oracle JDK 24, *Significant Changes in JDK 24* (JEP 491): https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html
6. OpenJDK, *JEP 444: Virtual Threads*: https://openjdk.org/jeps/444
7. OpenJDK, *JEP 491: Synchronize Virtual Threads without Pinning*: https://openjdk.org/jeps/491

Numbers in the comparison examples and stderr are marked **illustrative**, not guarantees across all OS/JVM combinations. Always check the JDK version and metric scope before drawing conclusions from thread counts.