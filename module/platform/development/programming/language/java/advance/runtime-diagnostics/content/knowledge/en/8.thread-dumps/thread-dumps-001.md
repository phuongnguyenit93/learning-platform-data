# 8.1 What a thread dump captures as a snapshot and what cannot be inferred from a single snapshot

> **Java Advance – runtime-diagnostics** · **8. Thread dumps**

## 1. A thread dump is a snapshot, not a recording of the entire execution

When a Java service hangs, experiences slow requests, has high CPU usage, or its pool stops accepting work, a **thread dump** is one of the fastest sources of evidence. A thread dump can show which threads currently exist, their JVM-observed states, a partial or full **call stack** at the time of collection, and — depending on the tool, VM, and options — monitor lock information, ownable synchronizers, lock owners, deadlocks, or additional metadata.

However, a dump **is not a video recording of execution**. It cannot tell you how long a thread has been in that state, what steps it went through beforehand, when it will exit, how much CPU it consumed over a historical window, or what event *caused* the failure. If a snapshot shows a thread in *WAITING*, that could be a **pool worker resting by design**, or it could be an application that has not received a required signal; a single snapshot usually cannot distinguish between the two.

Therefore, the central question of this lesson is:

> **What are we justified in concluding directly from a single thread dump snapshot, and what remains only a hypothesis requiring further evidence?**

After this lesson, you should be able to:

1. Explain the capture timing, collection scope, and meaning of Java Thread.State.
2. Read thread names, stack frames, lock identities/owners, monitors, and ownable synchronizers in common outputs.
3. Distinguish *RUNNABLE* from “consuming CPU”, *WAITING* from “hung”, and *BLOCKED* from “all kinds of waiting”.
4. Recognize signs worth investigating for contention/deadlock without inferring a root cause from a single state alone.
5. Know why a single dump **cannot** establish duration, frequency, progression over time, CPU profile, throughput, p95/p99, or causality.
6. Use consecutive snapshots, JVM metrics, OS metrics, app logs, traces, and JFR to verify hypotheses.
7. Understand the observability limits of platform threads versus virtual threads across different JDKs.
8. Practice a Java 17+ example that prints a ThreadInfo snapshot with verifiable states.

## 2. What does a thread dump show?

Each tool and JVM implementation can produce a different format. On HotSpot, typical information includes:

| Component | Directly observable | What **cannot be inferred automatically** |
| --- | --- | --- |
| Thread name | Name at the time of the snapshot, e.g., *http-nio-worker-42* | That the name always uniquely represents a request or its actual role |
| Thread ID/metadata | One or more IDs, priority, daemon status, OS native ID if supported by the format | That all IDs share the same namespace or can be compared directly across JVMs |
| Java Thread.State | *RUNNABLE*, *BLOCKED*, *WAITING*, *TIMED_WAITING*… | How long the state has been maintained or whether the thread is “good/bad” |
| Stack frames | Methods, classes, and sometimes files/lines currently on the stack | Full call history, all exceptions that occurred, or the time spent in each frame |
| Monitor info | Monitors currently held or awaited if supported by the tool | Who held the lock in the **past**, historical contention level, or whether the lock is buggy |
| Ownable synchronizers | Certain locks from *java.util.concurrent* when captured with appropriate options | All wait conditions and all synchronization locks in the system |
| Deadlock report | Lock cycles **detected by the algorithm/tool** | Absence of application-level deadlocks/livelocks or other distributed deadlocks |
| Capture time | Capture timestamp/VM version/PID, if recorded by output or external metadata | That all threads were captured at the exact same nanosecond or what happened beforehand |
| Native state/top frame | May suggest waiting on I/O, a native call, or a CPU hotspot | Actual CPU utilization percentage over a longer window |

You must verify **whether the tool actually outputs each field**. Not every file named *thread-dump.txt* contains lock owners, Java states, JNI frames, or all virtual threads. API documentation, JVM version, and the capture command are just as important as the file contents.

### 2.1 A snapshot is not necessarily JVM-wide atomic

A thread dump produced by some traditional HotSpot mechanisms may involve processing at a VM safepoint, whereas the *Thread.dump_to_file* format for virtual threads on JDK 21 is documented as **not globally consistent at a single point in time**. It collects multiple threads through a traversal process; threads may be created, change state, or terminate during collection.

Even if a collection mechanism is more consistent, it still represents only **a single observation**. There is no before/after history from a single file alone. During diagnosis, you must record both the **capture start/end timestamps if available**, the JVM instance, the tool/version, and the capture method.

## 3. How to read a typical thread dump excerpt

This is **illustrative data**, not a fixed output across all JDKs and not production evidence:

~~~text
"checkout-worker-42" #42 prio=5 os_prio=0 tid=0x00007f0011223300 nid=0x2a
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.Inventory.reserve(Inventory.java:73)
    - waiting to lock <0x000000071234abcd> (a java.lang.Object)
    at com.example.CheckoutService.placeOrder(CheckoutService.java:120)

"pool-worker-7" #51 prio=5 os_prio=0 tid=0x00007f0011224400 nid=0x33
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
    at java.util.concurrent.LinkedBlockingQueue.take(LinkedBlockingQueue.java:...)

"timer-1" #60 prio=5 os_prio=0 tid=0x00007f0011225500 nid=0x3c
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
    at com.example.RetryTicker.pause(RetryTicker.java:18)
~~~

### 3.1 Thread name is not request ID

A worker typically processes many requests over its lifecycle. A name like *checkout-worker-42* may have been assigned when the thread was created, while which request it is currently running can only be known with additional context from thread-locals, logs, tracing, or properly designed instrumentation. Thread names can also be changed or duplicated.

Do not treat *checkout-worker-42* as request number 42. If you need to correlate with requestId/traceId, generate correlation IDs in application logging/tracing according to policy; a thread dump usually **does not inherently contain** business IDs.

### 3.2 tid, nid, Java thread ID, and PID are different identifiers

In some HotSpot outputs:

- **tid=0x...** may be an internal VM pointer/thread identifier, **not necessarily Thread.getId()**.
- **nid=0x...** is typically the OS native thread ID, represented in hex; when correlating with OS tools, you must understand the namespace/format.
- **#42** in the thread header must likewise not be assumed to be a PID or request ID.
- **PID** is the JVM process; many native threads belong to the same PID, and a PID inside a container may differ from the host PID.

Formats vary by JDK/OS/tool. Only convert a native ID to decimal when you are certain that field is the **nid of the right OS thread**. A Java virtual thread does not have a fixed one-to-one mapping to a native OS thread, because it can be mounted/unmounted across carrier threads.

### 3.3 A stack frame is a position on the stack, not a timestamp

A frame such as:

~~~text
at com.example.Inventory.reserve(Inventory.java:73)
~~~

shows that this method segment was on the stack at the time of capture. It does **not** say that an error just occurred at line 73, that the thread stayed at line 73 for 30 seconds, that the code uses high CPU, or that the frame created a lock. The frames below it show the call chain, not the time spent in each frame.

Frames may be truncated due to depth limits, JIT/inlining optimizations, native calls, collection tools, or missing debug line numbers. **Unknown Source** does not by itself indicate buggy code; the build may simply lack line metadata.

### 3.4 waiting to lock and locked are not the same

- **waiting to lock**: the thread is currently waiting to acquire an object monitor to enter *synchronized*.
- **locked**: the thread is holding the corresponding monitor at the observed stack location.
- The **Locked ownable synchronizers** list (when present) relates to lock types such as *ReentrantLock*, and is not identical to all *synchronized monitors*.
- *parking to wait for* commonly appears with *LockSupport* and *java.util.concurrent* constructs; you must understand the queue/condition context.

A thread can be in *WAITING (parking)* on a thread pool queue and be completely healthy; having no work to do is normal. To claim “lock contention is causing request delay,” you need to prove that workers are waiting on a **lock on the request path**, at a significant wait ratio, and overlapping in time with the incident.

## 4. The six Java Thread.State values and interpretation limits

The following states are **JVM states** according to the *java.lang.Thread.State* API, not directly OS scheduler states. In dumps of **live** threads, *NEW* and *TERMINATED* usually do not appear as ordinary live threads because they have not started or have already finished.

| State | Standard meaning | Common situations | **Must not be concluded from state alone** |
| --- | --- | --- | --- |
| **NEW** | Thread has been created but not yet started | Newly created Thread object | That this thread is in the live dump list; thread leak |
| **RUNNABLE** | Thread is runnable in the JVM, including cases waiting for OS resources | Running Java code, native I/O, thread ready for CPU | “Consuming 100% CPU” |
| **BLOCKED** | Waiting for an **object monitor** to enter/re-enter *synchronized* | Another thread is holding the same monitor | “Guaranteed deadlock” or “all lock waits are BLOCKED” |
| **WAITING** | Waiting without a specified timeout | *Object.wait()*, *Thread.join()*, *LockSupport.park()*, queue take | “Permanently hung” |
| **TIMED_WAITING** | Waiting with a time limit | *Thread.sleep()*, timed wait/join/park | “Timeout has occurred” or “doing nothing useful” |
| **TERMINATED** | Thread has completed | Thread object after finishing | That a full running stack can be read from a live dump |

### 4.1 RUNNABLE **does not equal** consuming CPU

A thread in *RUNNABLE* may be:

- Executing Java bytecode/JIT-compiled code.
- Waiting to be scheduled onto a CPU by the OS.
- In a native I/O call where the JVM state still reports RUNNABLE (for example, certain forms of socket/native polling).
- In a loop actually consuming CPU.

If there are 50 RUNNABLE threads in a snapshot, that **does not prove** the process is using 50 cores or 5000% CPU. To find CPU hotspots, you need **OS per-thread CPU deltas** (matching the right native ID), **JFR execution samples**, async-profiler, or time-correlated metrics. The count of *RUNNABLE* threads is a clue to prioritize investigation, not a CPU measurement.

Even seeing a frame inside a computation method in a single snapshot is not sufficient proof that it is a hotspot. It may appear simply because sampling caught the thread passing through that method for a few microseconds.

### 4.2 BLOCKED only describes monitor acquisition

*BLOCKED* means waiting for an object monitor associated with *synchronized*. A thread contending for a *java.util.concurrent.locks.ReentrantLock* may be in **WAITING/parking**, not necessarily *BLOCKED*, because the locking mechanisms differ.

Example:

~~~java
// Illustrative snippet, not standalone.
synchronized (sharedMonitor) {
    // Another thread wanting to enter synchronized(sharedMonitor)
    // may appear as BLOCKED.
}
~~~

It is worth investigating if multiple request threads are *BLOCKED* on the same monitor: who holds that monitor, whether the holder is performing long I/O or waiting on another lock, how consistently it repeats across captures, and whether these threads are on the request critical path.

**A single BLOCKED snapshot has no duration.** Two threads merely entering a monitor in the exact microsecond of capture can show BLOCKED even in a healthy system.

### 4.3 WAITING can be a completely normal “idle” state

Pool workers commonly wait for tasks in *BlockingQueue.take()* or *LockSupport.park()*. A thread *WAITING* on a queue has not necessarily lost a signal. If the queue is empty, that is the intended design behavior.

Conversely, a critical thread waiting indefinitely on *CountDownLatch.await()* may be a symptom if the event releasing the latch never arrives; however, the dump **does not say who is supposed to call countDown**, whether a signal was forgotten, or how long it has been waiting. You need to inspect the code, application logs, and history.

### 4.4 TIMED_WAITING does not equate to a timeout

*Thread.sleep(1000)* puts a thread into *TIMED_WAITING* for the sleep interval; this current state does not tell you how long it has already slept. For network waits with timeouts, you need to examine the specific logic and traces to know whether a timeout has occurred or is still pending.

Do not assume every sleeping thread is useless. Timers, backoff, retry schedulers, or heartbeats may be waiting on schedule. A thread sleeping at the moment of capture may run continuously during other intervals.

### 4.5 Java states are not equivalent to OS states

Java Thread.State does not directly provide:

- Exact OS scheduling state.
- Percentage of CPU used.
- I/O latency level or network packet state.
- Memory allocation rate of the thread.
- Historical distribution of runnable/waiting time.

You need OS tools/JFR/metrics if you want this data. Some HotSpot dumps include extra fields like *cpu=...* or *elapsed=...* in the header, but **that is data provided by the specific version and tool**, not a guaranteed property of Java Thread.State. If you see *cpu=*, check its unit and meaning; cumulative CPU time **is not instantaneous CPU%**.

## 5. What can a thread dump reliably suggest?

You must separate **observation** (evidence) from **hypothesis** (hypothesis) and **causal conclusion**.

| Data in a single dump | Acceptable statement | Inference beyond the evidence |
| --- | --- | --- |
| Thread A is currently BLOCKED on monitor X | At the time of observation, A was waiting for monitor X | A has been waiting for X for minutes |
| Thread B currently holds monitor X | Tool recorded B as owning X | B has held X since the start of the incident or refuses to release it |
| A is WAITING at queue take | A is waiting for a task/condition according to the stack | The pool is deadlocked |
| Multiple workers share the same stack frame | Multiple threads were caught on the same code path | That method is a CPU hotspot |
| A thread is RUNNABLE in socket read | JVM reports RUNNABLE and the stack relates to I/O | The thread is burning CPU |
| Stack is at *Thread.sleep* | Thread was in a timed sleep at capture time | The thread timed out or slept too long |
| Output reports **Found one Java-level deadlock** | Tool detected a deadlock cycle within its detector's capability | This is the only synchronization problem in the process |
| Dump reports no deadlock | Detector did not find a cycle within its supported scope | There is no lock starvation/livelock/distributed deadlock |
| ThreadInfo lock owner is “main” | Monitor was held by main when observed | main is the root cause of production latency |
| Thread X is not seen | X was not within scope/at capture time or had already finished | X never existed or the request never ran |
| 500 threads are present | At least this many threads exist in the output scope | 500 requests are being processed concurrently |
| Thread name contains “payment” | That name was assigned to the thread | The frame definitely belongs to a specific customer's payment request |

**From a single snapshot, reliable conclusions must use time-anchored language:** “At the time of capture, these workers were…” rather than “the service always…”, “for the past several minutes…”, or “because of…, therefore…”.

## 6. Deadlock, contention, starvation, and livelock: why not equate them?

### 6.1 Deadlock is a cyclic relationship, not just having BLOCKED threads

A typical **monitor deadlock**:

~~~text
Thread A holds monitor X, waiting for monitor Y
Thread B holds monitor Y, waiting for monitor X
                        |
                        v
               mutual waiting cycle
~~~

If the tool has a **deadlock detector** and prints a cycle notice, that is strong evidence of a deadlock within the detector's scope. If you only see two isolated BLOCKED threads without an owner/graph, you cannot yet assert a deadlock.

**Not seeing a deadlock report does not rule out all deadlocks.** The detector may only check monitors/ownable synchronizers inside the JVM; it does not recognize “waiting for a response from service B while B waits for service A”, condition/latch protocols that do not form a lock cycle, thread starvation, or virtual-thread-related deadlocks depending on the API/version.

### 6.2 Contention can be normal

Contention occurs when multiple threads compete for a single resource. A brief *synchronized* block may occasionally cause threads to be BLOCKED very briefly without affecting the service. You need to look at:

- How many threads are affected?
- How long and at what rate do they wait?
- Does it repeat on the same lock across snapshots?
- What is the owner doing while holding the lock?
- Do request latency, queue length, and throughput fluctuate at the same time?

A single snapshot showing *BLOCKED* is a **signal**, not a measurement of contention over time.

### 6.3 Starvation can occur without a lock cycle

**Thread pool starvation**: all workers are busy/waiting on subtasks, so the queue is not processed. A dump may show workers at *Future.get()* or queues/conditions, which is not yet sufficient proof. You need queue depth, active thread count, task submission/completion rates, and code dependencies between tasks.

**Livelock**: threads continuously change state/stay active without making business progress. A dump may show RUNNABLE; you need multiple samples + progress counters/traces to establish “activity without progress”.

### 6.4 “No Java-level deadlock found” does not mean “not hung”

An application can hang due to:

- Deadlocks in a database/distributed resource outside the JVM.
- Socket reads without timeouts.
- A task depending on a callback that never fires.
- A thread pool having no available workers due to nested blocking.
- Exhaustion of a connection pool or semaphore permits.
- The JVM/OS experiencing CPU throttling or resource starvation.

These cases do not necessarily create a monitor cycle detected by the deadlock detector. Do not stop investigating based solely on a line saying “No deadlocks found”.

## 7. Questions over time that a single snapshot **cannot** answer

### 7.1 No “how long has it been waiting” from pure state/stack

A *WAITING* line only describes **currently waiting**. Even if thread names are identical, without independent timing information you do not know when it started waiting. An *elapsed* field in the header of some HotSpot builds typically reflects thread lifetime, **not time spent in the current state**.

If you see a thread has been alive for 3 hours and is currently BLOCKED, you must not say “it has been BLOCKED for 3 hours”. The thread might have entered BLOCKED 1 ms before capture.

### 7.2 No “how many times” from a single stack

A snapshot caught at *cache.get()* does not tell you whether the method was called 10 times or 10 million times. It contains no frequency, throughput, invocation counter, or time series. JFR method profiling, application metrics, and sampling profilers are better suited for determining execution time distribution.

### 7.3 No p95/p99 or latency distribution

A thread dump shows thread states, not a histogram of request durations. To know p99 latency, you need recordings of request timings and percentile calculations over a sufficiently large sample window. *300 threads WAITING* cannot be converted into p99 = 300 ms.

### 7.4 Does not by itself prove a function uses high CPU

A “hot” stack frame in a snapshot can be due to:

- A method that genuinely runs for a long time.
- A method that runs very fast but happened to be caught at capture time.
- The thread waiting on native I/O.
- A worker running a task unrelated to the symptom.

You should use **multiple methodical stack samples**, JFR execution sampling, async-profiler, or OS CPU deltas. Be careful about sampling bias and stack collection overhead.

### 7.5 Does not prove causality

If thread A is waiting on lock X and request B is slow, the dump does not by itself prove X caused B to be slow. You need correlation by thread/request/task, timestamps, lock owner, and controls. Correlation between a capture and an incident can also happen simply because you only took the dump after the incident began.

### 7.6 Cannot measure what finished before capture

A thread/task/exception that completed right before capture will usually no longer have an active stack in the dump. Not seeing it does not prove it never ran. A new thread may appear right after capture. When an incident is a transient 50 ms spike, a snapshot taken afterward may look completely normal.

### 7.7 Does not confirm all threads on every JDK

The ability to list **platform threads**, **virtual threads**, native threads, or JVM internal threads varies by tool/version. Some traditional dumps do not include all unmounted virtual threads. Do not take the “Threads:” count from a tool and equate it with the total number of Java tasks or total OS threads.

## 8. Collecting a thread dump: prerequisites, tools, and impact

A valid diagnosis begins by identifying **the exact target JVM**: PID in the right namespace, executing user, JDK/tool version, timestamp, and instance. Do not test commands against an unfamiliar PID.

### 8.1 jcmd commands for HotSpot platform threads

On a host/container that has the right JVM, JDK tools, and sufficient attach permissions:

~~~bash
jcmd -l
jcmd <PID> help Thread.print
jcmd <PID> Thread.print
~~~

Replace *<PID>* with the verified process ID; this text is a documentation placeholder, not shell syntax to run verbatim. In Docker/Kubernetes, the PID seen from the host may differ from the PID inside the container; *jcmd -l* also has discoverability limits across process namespaces. Do not conclude the JVM is dead just because the PID does not appear in `jcmd -l` output.

On HotSpot JDK 17/21 builds that support the option, when ownable synchronizer information is needed:

~~~bash
jcmd <PID> Thread.print -l
~~~

If extended information is desired and confirmed by the target VM's command help:

~~~bash
jcmd <PID> Thread.print -e
~~~

**Do not assume every JDK has the same options/format.** Run *jcmd <PID> help Thread.print* first. The jcmd documentation rates Thread.print as having **medium** impact, depending on thread count; for a JVM with very many threads, output can be huge and cause overhead/latency impact during an incident. Do not put dump collection in a tight loop every few milliseconds.

### 8.2 jstack and control-break

On compatible JDKs/VMs, *jstack <PID>* is another way to collect thread stacks. On Linux HotSpot, a QUIT signal or Control+\ at the console can request a thread dump to be printed to the JVM output stream; on Windows, some environments support Control+Break. These methods depend on OS, version, permissions, and how the container/log pipeline captures stdout/stderr.

**Use only through authorized procedures:** signals can generate huge output, may be handled differently by container/logging configurations, and some JVMs have specific policies. Do not confuse **kill -QUIT** with **kill -KILL**: a KILL signal can terminate the process and destroy evidence; never use it to “try getting a thread dump”.

### 8.3 Collecting with ThreadMXBean

In a Java program, the standard API can retrieve *ThreadInfo*, stacks, and lock metadata according to supported capabilities. The following example is only an **illustrative snippet**:

~~~java
java.lang.management.ThreadMXBean bean =
        java.lang.management.ManagementFactory.getThreadMXBean();

java.lang.management.ThreadInfo[] infos =
        bean.dumpAllThreads(false, false);
~~~

On Java 17, this is a way to collect live platform threads in the current JVM, **not an automatic remote client**. It can be accessed over securely configured JMX, but you must understand permissions, connections, and capabilities.

Calling *dumpAllThreads(true, true)* requires support indicated by *isObjectMonitorUsageSupported()* and *isSynchronizerUsageSupported()*; do not assume every VM supports all lock details. Enabling contention timing is a separate operation from reading a snapshot and can incur overhead.

### 8.4 Saving output and metadata

With *Thread.print*, you can redirect stdout of **the caller-side jcmd command** to a file:

~~~bash
jcmd <PID> Thread.print -l > thread-01.txt
~~~

For diagnostic commands that write files **on the target JVM side**, paths are resolved in that JVM's filesystem/namespace, not necessarily the cwd of the calling terminal. Do not guess file paths inside containers; verify path, permissions, and disk space.

A thread dump file may contain thread names, paths, classes, stack frames, hostnames, lock details, or information useful to an attacker. Store it in a protected location, redact sensitive data before sharing, and define retention rules.

### 8.5 When attach fails

Do not jump straight from “jcmd failed” to “JVM deadlocked”. Attach can fail due to:

- Wrong PID or process restart.
- JDK/jcmd missing in a minimal image.
- Different effective user/group or OS permissions.
- Different PID/mount namespace in a container.
- Attach mechanism disabled or incompatible VM implementation.
- JVM too busy or attach channel not responding in time.

In that case, use already-enabled telemetry/logs/JFR, authorized OS diagnostic methods, or your platform team's support channel. Do not arbitrarily chmod */tmp*, enable privileged containers, or open up JMX permissions just to get a dump.

## 9. Virtual threads from Java 21+: do not treat traditional dumps as the whole picture

**The Java 17 example later in this lesson uses platform threads.** Java 21 made virtual threads an official feature; this is an important point to pay attention to when applying snapshot concepts to newer applications.

A virtual thread is a Java thread managed by the JVM that can **mount** onto a carrier platform thread and **unmount** when waiting. Many virtual threads do not correspond to the number of native OS threads. If you only count carrier threads in a traditional dump, you may miss a large number of waiting logical tasks.

According to JDK 21 documentation:

- Traditional *Thread.print* is not a complete tool for describing all virtual threads.
- **jcmd Thread.dump_to_file** can capture text/JSON dumps with broader virtual-thread coverage; its contents and format **differ** from traditional dumps and do not contain all object-address/monitor/native/heap details.
- This dump format is not a globally consistent atomic snapshot of all virtual threads and does not automatically perform all deadlock detection.
- **ThreadMXBean.dumpAllThreads()** in the management API on JDKs supporting virtual threads describes **platform threads**, and is not guaranteed to include all virtual threads.
- If investigating virtual-thread pinning, scheduler starvation, socket I/O, or JVM-level events, JFR and tools supporting virtual threads may be more useful.

On JDK 21 and compatible tools, check syntax first:

~~~bash
jcmd <PID> help Thread.dump_to_file
~~~

Example per the **Oracle JDK 21 virtual threads guide**, where the file path is on the target JVM side:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json threads.json
~~~

**Version caveat:** other JDK versions may accept different option/format names (for example, *plain* instead of *text* in later documentation). Run *help* on the actual VM; do not copy commands verbatim between JDK 17, 21, and newer JDKs without checking. **JDK 17 does not have standard virtual threads**, and you should not expect Thread.dump_to_file to always exist there.

A virtual-thread dump lacking monitor details does not mean the application does not use monitors. A platform-thread dump not showing waiting virtual threads does not mean they have finished. **Observation scope is part of the evidence**.

## 10. Java 17+ Lab: creating a BLOCKED, WAITING, TIMED_WAITING snapshot

This lab creates three **platform threads** in controlled states, then uses **ThreadMXBean.getThreadInfo()** to capture a point-in-time snapshot. The goal is to observe technically accurate *state + lock owner*, not to create an actual deadlock.

- Thread *demo-blocked* tries to enter synchronized on *MONITOR*, while main intentionally holds the monitor at snapshot time.
- Thread *demo-waiting* waits on a *CountDownLatch* that has not yet been released.
- Thread *demo-sleeping* runs *Thread.sleep(60_000)* (long enough to capture the snapshot).
- Main verifies the states, reads ThreadInfo, prints the states, and then **releases everything** in *finally*.

Create file **ThreadSnapshotDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public final class ThreadSnapshotDemo {
    private static final Object MONITOR = new Object();
    private static final CountDownLatch RELEASE = new CountDownLatch(1);

    public static void main(String[] args) throws Exception {
        Thread waiting = new Thread(() -> {
            try {
                RELEASE.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-waiting");

        Thread sleeping = new Thread(() -> {
            try {
                Thread.sleep(60_000L);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-sleeping");

        Thread blocked = new Thread(() -> {
            synchronized (MONITOR) {
                // Only enters here after main releases MONITOR.
            }
        }, "demo-blocked");

        try {
            waiting.start();
            sleeping.start();
            awaitState(waiting, Thread.State.WAITING);
            awaitState(sleeping, Thread.State.TIMED_WAITING);

            synchronized (MONITOR) {
                blocked.start();
                awaitState(blocked, Thread.State.BLOCKED);

                ThreadMXBean mx = ManagementFactory.getThreadMXBean();
                long[] ids = {blocked.getId(), waiting.getId(), sleeping.getId()};
                ThreadInfo[] infos = mx.getThreadInfo(ids, 8);

                for (ThreadInfo info : infos) {
                    if (info == null) {
                        throw new IllegalStateException("Thread ended too soon");
                    }
                    System.out.println(info.getThreadName() + "=" + info.getThreadState());
                }
                System.out.println("blockedOwnerIsMain="
                        + Thread.currentThread().getName().equals(
                                infos[0].getLockOwnerName()));
                System.out.println("blockedHasLockName="
                        + (infos[0].getLockName() != null));
            }
        } finally {
            RELEASE.countDown();
            sleeping.interrupt();
            for (Thread thread : new Thread[] {blocked, waiting, sleeping}) {
                if (thread.getState() != Thread.State.NEW) {
                    thread.join(2_000L);
                }
            }
        }
    }

    private static void awaitState(Thread thread, Thread.State desired)
            throws InterruptedException {
        for (int attempt = 0; attempt < 200; attempt++) {
            if (thread.getState() == desired) {
                return;
            }
            Thread.sleep(10L);
        }
        throw new IllegalStateException("Did not reach " + desired
                + ": " + thread.getState());
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 ThreadSnapshotDemo.java
java ThreadSnapshotDemo
~~~

**Program stdout tested on HotSpot JDK:**

~~~text
demo-blocked=BLOCKED
demo-waiting=WAITING
demo-sleeping=TIMED_WAITING
blockedOwnerIsMain=true
blockedHasLockName=true
~~~

These are 5 lines of **stdout from the program**; some newer JDKs may emit separate compiler warnings because *Thread.getId()* has been replaced/deprecated in newer versions, but Java 17 compiles cleanly. Runtime scheduling/timing can vary, so the *awaitState* method checks within a bounded window to avoid assuming a single short sleep is enough.

### 10.1 Why does the demo prove the lock owner?

Main holds *MONITOR* when starting thread *demo-blocked*; that thread tries to enter the same monitor, so it becomes *BLOCKED*. *ThreadMXBean.getThreadInfo(ids, 8)* returns a **ThreadInfo snapshot**; the *getLockOwnerName()* field shows main holding the monitor and *getLockName()* has a non-null value. When main exits the synchronized block, the monitor is released and the blocked thread can proceed.

If the demo did not keep main inside synchronized at snapshot time, the *BLOCKED* state could have disappeared before measurement. This is a small example of the nature that **a snapshot does not record past states**.

### 10.2 Why is waiting not a deadlock?

Thread *demo-waiting* is waiting on *CountDownLatch*. Main releases the latch with *RELEASE.countDown()* in finally; that is a clear forward-progress path. Looking only at a dump mid-execution, you see WAITING, but you cannot tell whether main will release it moments later.

Similarly, *demo-sleeping* is in TIMED_WAITING with a long duration; at the end of the program main interrupts it so it does not wait the full 60 seconds. A *TIMED_WAITING* line does not prove the program has a timeout bug.

### 10.3 Why shouldn't this be called a deadlock?

At the time the snapshot is taken, main **holds the monitor** and **is taking the snapshot**; it is not waiting on any monitor owned by demo-blocked. There is no *A waiting on B, B waiting on A* cycle. The blocked thread has an exit path when main leaves the synchronized block. Seeing only *demo-blocked=BLOCKED* and concluding “deadlock” is an invalid inference.

### 10.4 How to extend the lab if needed (not for production)

You can take two snapshots at different times in the **lab** to observe states changing after main releases the monitor. However, continuous capturing can affect scheduling, nor does it turn a thread dump into a proper profiler. Keep the test small, limit the number of threads, and ensure all threads are cleaned up.

## 11. Snapshot series: moving from a single snapshot to trend evidence

A useful approach is to collect **several** timestamped dumps while the symptom is occurring, for example three to five snapshots spaced a few seconds apart **if impact and load permit**. This is an exploratory guideline, not a “rule requiring exactly 3 snapshots 5 seconds apart”. The interval must match the symptom duration, tool overhead, and traffic.

Tabulation example:

| UTC Time | Thread identity | State | Top frames | Lock/owner | Notes |
| --- | --- | --- | --- | --- | --- |
| 10:00:00 | pool-worker-7 | BLOCKED | Inventory.reserve | monitor X / worker-1 | Snapshot 1 |
| 10:00:05 | pool-worker-7 | BLOCKED | Inventory.reserve | monitor X / worker-1 | Snapshot 2 |
| 10:00:10 | pool-worker-7 | RUNNABLE | Checkout.reply | — | Snapshot 3 |

**Correct interpretation:** three snapshots support the hypothesis that worker-7 was affected by lock X during the symptomatic window and subsequently progressed. However, you **cannot measure the exact total BLOCKED duration as 10 seconds**: the thread may have briefly changed state and returned between captures.

When comparing snapshots, you must match the **same process instance and thread identity**, not just the thread name. Thread IDs can be reused across lifecycles, PIDs reset after restarts, and thread pools can recreate workers with the same name. If dumps come from multiple pods/JVMs, never merge frames and owner IDs as if they belonged to one shared lock graph.

### 11.1 Investigation workflow from symptom to conclusion

1. **Lock incident scope:** service, pod/host, PID/JVM start time, timestamp, load, route, error/latency metrics.
2. **Take initial sample:** supported tool, proper attach permissions, save metadata, and consider overhead.
3. **Group threads:** request workers, timers, pool helpers, GC/JIT/internal, event-loop, virtual threads (if JVM supports them).
4. **Examine state + stack + owner:** prioritize threads related to the symptom; do not be misled by normally sleeping threads.
5. **Inspect relationships:** if BLOCKED, find the owner and the owner's stack; if parked, find the condition/queue and the signaling code.
6. **Take controlled follow-up snapshots:** compare stack signatures, lock identities, states, and signs of progress; do not hammer an overloaded JVM.
7. **Correlate other sources:** JFR execution/thread park/monitor events, per-thread OS CPU, GC pauses, app logs/traces, queue/dependency metrics.
8. **State hypotheses and confidence level:** distinguish what was observed vs what is inferred; propose falsifiable checks.
9. **Choose low-impact actions:** verify before/after, restrict dump access permissions and retention.

### 11.2 Even with multiple snapshots, do not idolize them

Even three snapshots with the same stack do not prove a thread is **never progressing**. It could be looping through a fast piece of code many times. To prove lack of business progress, compare **progress counters**, queue completions, span timings, logs, or corresponding data states.

To identify CPU hotspots, statistical sampling over a sufficient window or JFR/async-profiler is usually more reliable than counting a few thread-dump lines; they provide methodology and sample weighting, though bias/overhead must still be considered.

## 12. Combining thread dumps with other evidence sources

| Question to answer | Thread dump contribution | Sources to combine |
| --- | --- | --- |
| Where is a slow request stuck? | Worker call stack, state, lock/park hints | TraceId, request logs, dependency timings |
| Is there monitor contention? | BLOCKED, waiting to lock, owner | Repeated snapshots, JFR monitor-enter events, latency |
| Which thread is causing high process CPU? | Stack clue at capture time | OS per-thread CPU delta, JFR/profiler |
| Is there a deadlock? | Lock graph/detector within supported scope | ThreadMXBean deadlock detection, code lock order, logs |
| Thread pool starvation? | Workers collectively on blocking calls | Active/queue/complete rates, pool config, traces |
| Did a GC pause cause a p99 spike? | May lack info or only show VM threads | GC Unified Logging/JFR, pause histogram, metrics |
| Is a native socket waiting? | Top frames/native state hints | Network spans, socket states, dependency metrics |
| Memory leak? | Stacks are usually insufficient to establish object retention | Heap usage trend, JFR allocation, controlled heap dump |
| Did a failed request already finish? | Usually no longer has that task's stack | Application error logs, traces, exceptions |
| Virtual thread pinning/stall? | Depends on dump virtual-thread coverage | Virtual-thread-specific dump, JFR pinning/scheduler events |
| Has an operation waited 30 seconds? | Snapshot may show it waiting | Timestamps in app logs, spans, JFR duration |

Do not demand that a single thread dump contain the entire observability context. A good result is a **concrete piece of evidence** that supports or rules out a hypothesis.

## 13. Four before–after interpretation scenarios

### Scenario A – 40 HTTP workers WAITING in pool

**Single snapshot:** many workers have frame *LinkedBlockingQueue.take()* and state WAITING.

**Invalid inference:** “40 workers are deadlocked”.

**Correct reading:** the threads are waiting for tasks; this can be completely normal if the queue is empty. Check request rate, queue depth, active threads, completed tasks, and thread naming. Only if requests are not being processed despite tasks being enqueued should you inspect pool configuration, wake-up conditions, and submission behavior.

### Scenario B – 20 threads BLOCKED on the same monitor

**Single snapshot:** request workers all show *waiting to lock <X>*; another thread shows *locked <X>*.

**Invalid inference:** “This same lock definitely causes every 2-second p99 spike”.

**Correct reading:** there is a sign of contention at capture time. Check where the owner is on its stack, whether I/O is called inside the synchronized block, whether these workers correspond to the slow route, and whether contention persists across subsequent snapshots or JFR monitor events.

**Possible post-verification conclusion:** “In the 10:00:00 and 10:00:05 snapshots, multiple checkout workers waited on monitor X; the owner executed a network call inside the critical section; traces show latency increased during the same period. This is strong evidence to measure duration/review the code path.” Still avoid asserting an exact BLOCKED duration unless measured.

### Scenario C – Process CPU 300%, one RUNNABLE in JSON parser

**Single snapshot:** one worker is RUNNABLE with a JSON parser stack.

**Invalid inference:** “The JSON parser is using 300% CPU”.

**Correct reading:** a single RUNNABLE Java thread cannot immediately be blamed for the entire process's CPU. CPU may be consumed by other threads, GC/JIT/native code, or scheduling. You must inspect per-thread CPU time by delta, JFR samples/profiler in the same window, and map native thread IDs carefully.

If multiple execution samples hit the same frame with significant weight and matching CPU deltas, the hotspot hypothesis gains further evidence.

### Scenario D – Service times out on payment, dump only has TIMED_WAITING timers

**Single snapshot:** timer threads sleeping on schedule; no payment workers seen.

**Invalid inference:** “Payment requests are not running or everything is completely fine”.

**Correct reading:** the request may have timed out/finished before capture, or ran on virtual threads outside the dump's coverage. You need app logs, tracing, dependency metrics, and captures taken during the actual incident window. Not every thread dump is suitable for diagnosing a spike that has already passed.

## 14. How to write an evidence-based report

A report section should follow **facts → hypotheses → tests → limitations**.

**Good example:**

> At 10:01:20 UTC on checkout JVM pod-4, a snapshot from jcmd Thread.print -l showed 18 request workers in BLOCKED at Inventory.reserve waiting together on monitor X. An inventory-maintainer thread was recorded holding X with its stack in an external-call method. This is a sign of monitor contention while request latency is elevated. Lock hold duration and whether this is the p99 root cause are not yet known. We will correlate 2 additional timestamped snapshots, trace spans, and JFR monitor-enter durations within the incident window.

**Example to avoid writing:**

> The thread dump proves inventory-maintainer held the lock for 10 minutes causing the entire API to hang because it is RUNNABLE, definitely requiring a JVM restart.

The latter example goes beyond what a single snapshot can support: it lacks duration, lacks temporal progression, and has not checked snapshot coverage or alternative causes.

Minimum metadata template to store alongside a dump:

~~~text
Incident:
Service/version:
Host / pod / container:
JVM PID and JVM start time:
JDK version / VM implementation:
Capture command and tool version:
Timestamp with timezone:
Capture file/format/location:
Thread count and known coverage caveats:
Observed states/stack signatures/locks:
Related app metrics/logs/traces:
Hypotheses and evidence level:
Next safe validation:
Data classification/retention:
~~~

Do not store credentials or customer details in reports. If production stack traces must be shared, enforce access controls and redaction.

## 15. Most frequently repeated analysis mistakes

| Misconception | Why it is wrong | Correct interpretation/next step |
| --- | --- | --- |
| “RUNNABLE = 100% CPU” | RUNNABLE is a JVM state, may be waiting on OS/I/O | Use per-thread CPU delta/JFR |
| “WAITING = hung thread” | Queue workers normally wait for work | Check frame, queue state, and progress |
| “TIMED_WAITING = timeout occurred” | Merely waiting with a time limit | Check deadline and application result |
| “BLOCKED = deadlock” | Monitor wait can be brief; deadlock requires a cycle | Find owner/graph, multiple samples, detector |
| “ReentrantLock contention is always BLOCKED” | Contended LockSupport/Condition can be WAITING | Look at stack and ownable synchronizers |
| “Thread alive for 2 hours so BLOCKED 2 hours” | Thread age differs from state duration | Need timing/profiling/time series |
| “No deadlock report = no deadlock” | Detector has limits and other deadlock types exist | Analyze dependencies and tool coverage |
| “Same stack seen 3 times = no progress” | Thread may loop through that stack multiple times | Compare progress counters/traces/events |
| “No request thread seen = request never ran” | Task may have finished, switched workers/virtual threads | App traces, right time window, dump type |
| “One frame in JSON parser = CPU hotspot” | No distribution or CPU duration | Profiler/JFR and OS CPU |
| “nid is Java Thread.getId” | Native/Java IDs have different namespaces | Check tool/version and mapping |
| “Each thread name maps to one request” | Workers usually handle multiple requests | Trace/context correlation |
| “Dump is an atomic JVM-wide snapshot” | Some capture mechanisms are non-atomic and take time | Record method and capture window |
| “A dump always includes all virtual threads” | Tool and JDK determine coverage | Verify Thread.dump_to_file/JFR |
| “No deep stack means code did not call that function” | Stack may be truncated/optimized/native frame | Check depth, symbol/debug metadata |
| “Many threads means many active requests” | Pool helpers, GC/JIT/internal, idle workers also appear | Classify roles and metrics |
| “With a thread dump, restarting is the obvious fix” | Snapshot is only evidence; restart destroys state | Form hypothesis, evaluate impact |
| “Thread.print has no impact on the service” | Very large dumps have overhead/I/O | Capture selectively, avoid tight loops |
| “No lock shown means no lock exists” | Tool/format may omit locked synchronizers | Enable appropriate options, understand coverage |

## 16. Self-check questions with answers

### 1. Does a RUNNABLE thread mean it is continuously using a CPU core?

**No.** This is a Java state; the thread may not have been scheduled onto CPU by the scheduler, may be in native I/O, or may only be transiently passing through Java code. CPU time/rate must be measured from time-based counters or a profiler.

### 2. A thread pool has 100 threads WAITING in LinkedBlockingQueue.take: incident or normal?

**Cannot conclude yet.** If there are no pending tasks, this can be normal idle behavior. If the queue has a backlog with no workers processing it, you need to inspect queue/pool metrics and thread lifecycle.

### 3. Does having one BLOCKED thread mean there is a deadlock?

**No.** A thread waiting for a monitor whose owner is using it legitimately can proceed as soon as the monitor is released. Deadlock requires a wait cycle or specific stuck condition backed by evidence.

### 4. Why can contended ReentrantLock show WAITING?

Because many synchronization paths are built on *AbstractQueuedSynchronizer/LockSupport.park*, rather than Java object monitors used by *synchronized*. The BLOCKED enum describes waiting on a monitor, and does not cover all synchronization primitives.

### 5. A header has *elapsed=3600s* and state BLOCKED; can you conclude it waited for the lock for one hour?

**No.** *Elapsed* in that form is typically thread lifetime reported by the VM, not the time it has spent in the BLOCKED state. For timing, you need instrumentation or historical tracking.

### 6. Three snapshots 5 seconds apart all show the same stack; can you measure 10 seconds blocked?

**Not accurately.** These are three observation points; the thread may have left and returned to the same stack between measurements. You can only say “observed in that state at three timestamps”, and combine other sources to estimate duration.

### 7. Does seeing no deadlock report rule out mutual calls between two microservices?

**No.** The JVM lock detector does not automatically detect dependency cycles across network/service boundaries. You need distributed tracing, queue/dependency logs, and protocol design review.

### 8. A stack trace has a socket read frame in RUNNABLE; does that prove CPU is consumed by socket read?

**No.** A thread may be waiting on I/O inside a native method while Java Thread.State remains RUNNABLE. Check network timings and OS thread CPU.

### 9. Why do virtual threads require attention to dump type?

Because virtual threads do not map one-to-one with OS threads and can unmount. Traditional dumps focusing on platform/carrier threads may miss waiting virtual threads; JDK 21 provides *Thread.dump_to_file* supporting a different scope, though with its own limitations.

### 10. If a thread is no longer in a new dump, did it complete successfully?

**Not certain.** It could have terminated with an exception, been replaced by another thread, been omitted by dump coverage, or the process may have restarted. You need app logs/traces/task completion evidence.

### 11. Can a thread dump calculate p99 request latency?

**No.** A dump is a snapshot of stacks/states, not a set of duration measurements. Use metrics or tracing with a sufficient sample window.

### 12. When is a lock graph in a dump strong evidence?

When the dump has **reliable owner/waiter identities**, multiple threads wait on the relevant lock, or the detector reports a **deadlock cycle** within its supported scope. To confirm lock contention as the root cause of latency, you still need to correlate timing, requests, and persistence/frequency.

### 13. Why aren't two threads with the same top frame necessarily doing the same work?

The same method can be called by different requests/tasks, in different states, or both may simply be at a shared queue wait. You need context from thread names, full stacks, traces, and queue/task identities.

### 14. When capturing a dump from a production service, what should be prioritized first?

Verify **the right JVM**, permissions/tools, cost, and security; capture a snapshot with metadata, then evaluate whether more samples or other sources are needed. Do not generate continuous dumps or restart without assessing impact.

## 17. Official reference documentation

- **Java SE 17 – Thread.State**, contract of the 6 JVM states: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- **Java SE 17 – ThreadMXBean**, ThreadInfo, lock monitoring, and deadlock detection: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Java SE 17 – ThreadInfo**, Thread State, lock owner, stack: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- **Oracle JDK 21 – jcmd**, *Thread.print* options and impact: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **Oracle JDK 17 – Diagnostic Tools**, thread dumps, jstack, signals, and lock support: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- **Oracle JDK 17 – Troubleshoot Process Hangs and Loops**, explaining deadlock/monitor waiting: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-process-hangs-and-loops.html
- **Oracle JDK 21 – Virtual Threads**, tools for creating virtual-thread dumps: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html

Dump syntax, headers, virtual-thread coverage scope, lock details, cost, and consistency **depend on the tool and JVM version**. When using them in a real incident, check the documentation and *help* from the running JDK.

## Key Takeaways

**A thread dump is evidence of location and state at one or a few points in time, not complete historical evidence or a full root cause.** A snapshot can show where threads currently are, their Java states, stack frames, and sometimes locks/owners; by itself it **cannot** measure duration, CPU percentage, throughput, p99, occurrence counts, all virtual threads, or causality.

The right approach is **state observations clearly → propose hypotheses → take additional properly scoped samples → correlate CPU/JFR/GC/app metrics/logs/traces → verify → only then conclude**.