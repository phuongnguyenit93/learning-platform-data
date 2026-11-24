# 8.9 Recognizing the limits of traditional thread dumps for virtual threads

**Java 21** made **virtual threads** a standard feature under **JEP 444**. They allow a **thread-per-task/request** model to scale to vast numbers of tasks waiting on I/O without creating a corresponding OS thread for each task. This is a major shift in how **thread dumps** must be read: a traditional dump clearly shows **platform threads / carrier threads**, yet **is not a complete inventory of virtual threads**. Therefore, when seeing a few dozen thread entries in jstack while the application has tens of thousands of waiting requests, do not rush to conclude those requests have finished or the JVM “has no threads”.

On **HotSpot/JDK 21**, distinguish:

- **jstack, jcmd Thread.print, ThreadMXBean.dumpAllThreads, Thread.getAllStackTraces**: traditional/management mechanisms focused on **platform threads**; do not use them to inventory all virtual threads.
- **jcmd PID Thread.dump_to_file**: a mechanism for exporting a **virtual-thread-aware thread dump**, supporting **text/plain** and **JSON**, letting you view stacks of many virtual threads in the same JVM, yet **lacking all lock/monitor/JNI/heap details** of traditional JDK 21 dumps and not replacing deadlock analysis.
- **JDK Flight Recorder (JFR)** together with **application tracing/metrics**: track events **occurring over time**, especially **pinning, start/end, submit failed**, rather than capturing only a single frame at investigation time.

This article restricts claims about pinning and dump formats to **Java 21**. Newer JDK releases can change synchronization mechanisms, lock detail levels, and diagnostic command syntax; **do not back-port JDK 25/26 behavior onto JDK 21**.

## 1. Learning objectives

After this lesson, you should be able to:

1. Explain **platform thread, virtual thread, carrier, mounting, and unmounting**.
2. Identify what information **jstack** or **Thread.print** provides, and why that list omits many virtual threads.
3. Understand accurately that **ThreadMXBean.getThreadCount(), getAllThreadIds(), dumpAllThreads(), and getThreadInfo()** support only **platform threads** in Java 21.
4. Use **jcmd PID Thread.dump_to_file** with **JSON** or **text** output to gather more virtual thread information, and verify actual support using **jcmd PID help**.
5. Distinguish **Java thread ID** from **OS native thread ID / nid**; never permanently bind a virtual thread to one carrier.
6. Know why a virtual-aware dump is not a **globally atomic snapshot** and lacks traditional dump lock/object monitor details on JDK 21.
7. Use **JFR jdk.VirtualThreadPinned** and **jdk.tracePinnedThreads** to diagnose **pinning** under Java 21 semantics.
8. Design evidence collection per scenario: waiting requests, carrier starvation, high CPU, pinning, or suspected deadlock.
9. Write and run a Java 21 example that self-verifies the limits of **ThreadMXBean**.
10. Report results without equating **platform thread** counts, **virtual thread** counts, and **request/task** counts.

## 2. Execution model: a virtual thread does not equal an OS thread

A **platform thread** is a **java.lang.Thread** object mapped one-to-one to an OS/native thread and typically retains that mapping throughout its lifetime.

A **virtual thread** is also a **java.lang.Thread** object, yet managed by the Java runtime; it has no dedicated OS/native thread for its entire lifetime. The JVM **mounts** a virtual thread onto a platform thread called a **carrier** while executing code. When encountering an operation that can suspend efficiently, such as runtime-supported blocking I/O, the virtual thread can **unmount**, freeing the carrier for another task. Later, the virtual thread may resume on **a different carrier**.

~~~text
At one point in time:
    Virtual thread A --mounted--> Carrier platform thread #1
    Virtual thread B --parked / unmounted--> Holds no OS thread
    Virtual thread C --mounted--> Carrier platform thread #2

At a later point in time:
    Virtual thread A --unmounted--> Holds no OS thread
    Virtual thread B --mounted--> Carrier platform thread #1
    Virtual thread C --mounted--> Carrier platform thread #3
~~~

This is a **conceptual model**, not a fixed mapping within a JVM run. A virtual thread does not own a fixed native **nid** like a platform thread. Observing a carrier at time t1 is not enough to assert it is running the same virtual thread at t2.

### 2.1. WAITING state does not prove an OS thread is held

Suppose a virtual thread calls **BlockingQueue.take()** and no item is available. It can park/unmount while **the carrier thread is released** to serve other work. Seeing a waiting virtual thread in a JSON dump does not let you infer the OS is also holding a native thread for that virtual thread.

Conversely, a carrier in **RUNNABLE** does not necessarily mean “a request is continuously burning CPU”; it might be running another virtual task, assisting the scheduler, or inside native code. Correlate **CPU per native thread**, **JFR**, request traces, scheduler state, and workload.

### 2.2. Virtual threads scale concurrency, not single-computation speed

The primary goal of virtual threads is **allowing many I/O-bound tasks to wait and resume concurrently**, not making CPU-bound computation run faster. If 10,000 requests wait on sockets while the JVM has 32 carriers, that can be normal operation; if 32 CPU-bound tasks run continuously on 8 cores, they still contend for CPU resources.

**Do not treat the virtual-thread-to-carrier ratio as proof of a leak or bottleneck**. Counts, states, completion rates, latency, and application concurrency policies provide the real context.

## 3. Why do traditional thread dumps have limits?

Traditional thread dumps were designed when **platform thread counts** were typically tens, hundreds, or a few thousand. They usually include stacks, Java/native thread identities, states, object monitors, lock information, and some JVM-internal data. With hundreds of thousands of virtual threads, printing a flat full list with every detail would be both **enormous** and mismatched with how the runtime manages virtual threads.

On JDK 21, tools and APIs do not share the same scope:

| Mechanism | What is visible on JDK 21? | Must not conclude |
| --- | --- | --- |
| **jstack PID** | Traditional thread dump view, mainly platform/carrier threads and matching lock/native data. | Not seeing thousands of virtual threads means they do not exist. |
| **jcmd PID Thread.print -l** | Traditional dump oriented toward platform threads, with VM-supported synchronization/lock details. | Do not treat as an inventory of all virtual threads/tasks. |
| **SIGQUIT / Ctrl+\** on Linux | Depending on JVM/terminal setup, can print traditional thread dumps to stderr/stdout. | Do not treat container log output as covering all virtual threads. |
| **Thread.getAllStackTraces()** | Stack map of **live platform threads** per Java 21 API. | Does not list parked virtual threads. |
| **ThreadMXBean.dumpAllThreads(...)** | **Live platform threads**, stacks, and supported synchronization details. | Does not comprehensively include virtual threads. |
| **ThreadMXBean.getThreadCount()** | Count of **live platform threads**. | Not the total of all Java Threads or concurrent requests. |
| **ps -L / top -H / /proc/PID/task** | Native/OS threads visible from Linux per namespace. | Not all virtual threads living on the heap. |
| **jcmd PID Thread.dump_to_file** | Dedicated dump to observe **platform + virtual threads** in text/JSON, implementation-dependent. | Lacks all object lock, JNI, heap, or deadlock details of legacy dumps. |
| **JFR** | Configured events recorded over time, including relevant virtual-thread events. | Does not automatically supply a full snapshot of every virtual thread predating enablement. |
| **Application metrics/tracing** | Active/queued task counts, request latency, span correlation per instrumentation. | Cannot replace JVM stacks when identifying which Java code is waiting. |

**Be careful with the phrase “all threads”.** Some older docs or help text say “all threads”, yet under Java 21 management semantics, **ThreadMXBean supports only platform threads**. Check the **command type** and API rather than reading one descriptive sentence and assuming all virtual threads are listed.

### 3.1. Traditional dumps remain very valuable

Do not discard **Thread.print** or **jstack**. They remain useful when:

- Investigating **deadlocks/monitor contention** among platform threads.
- Needing native thread IDs to correlate OS CPU or **perf**.
- Checking whether the carrier pool and JVM worker threads show CPU saturation or blocking in native calls.
- Needing **locked monitors, ownable synchronizers, JNI, or heap statistics** that JDK 21's virtual-aware dump does not provide.
- An application still uses many **platform threads** via libraries, GC, compilers, schedulers, or connectors.

**The right technique is complementary, not absolute replacement:** use traditional dumps for platform/native scope, and virtual-aware dumps/JFR/tracing for virtual-task scope.

## 4. ThreadMXBean: the clearest API evidence

According to **Java SE 21 ThreadMXBean**, the management interface targets platform threads; it **does not support monitoring/managing virtual threads**.

| Java API | JDK 21 scope |
| --- | --- |
| **ManagementFactory.getThreadMXBean().getThreadCount()** | Counts live platform threads. |
| **getPeakThreadCount()** | Peak platform threads, excluding virtual threads. |
| **getTotalStartedThreadCount()** | Total platform threads started since JVM startup. |
| **getAllThreadIds()** | IDs of live platform threads; ignores virtual threads. |
| **getThreadInfo(virtualThreadId)** | Returns **null** for a virtual thread ID (even while alive). |
| **dumpAllThreads(true, true)** | Live platform threads; does not expand into a virtual thread inventory. |
| **findDeadlockedThreads()** | Finds deadlock cycles within the API-supported platform thread scope. |
| **Thread.getAllStackTraces()** | Stack map of platform threads only. |

**Practical consequence:** after migrating request handlers to virtual threads, JVM dashboards often still show **thread counts of only tens or hundreds**. That may be accurate for a **platform thread gauge**, not a sign that request concurrency dropped correspondingly.

### 4.1. Do not conclude “no deadlock” from ThreadMXBean alone

If **findDeadlockedThreads()** returns null, it does not prove **all hangs, wait cycles, or dependency cycles among virtual threads** are absent. On JDK 21, this API is defined for platform threads, whereas an application-level hang can involve locks/queues/futures used by virtual threads.

Similarly, **Thread.dump_to_file** does not run a full deadlock detection algorithm across all virtual threads. When suspecting task deadlocks, analyze **waiting relationships, lock ownership, application-level correlation, and executor queues**, or choose more suitable tooling.

### 4.2. Java thread IDs differ from OS native thread IDs

**Thread.threadId()** is the Java Thread object's ID; the JDK may reuse it after a thread terminates. A virtual thread has its own Java ID yet **has no fixed native TID** as it unmounts/remounts.

In platform thread dump output, **nid=...** typically represents the native thread ID in hex on HotSpot. **Do not interpret a virtual thread's Thread.threadId() as an nid**, nor pass it as a PID to jcmd.

~~~text
java pid       : JVM process identity within a PID namespace
platform tid   : Java ID of a platform Thread
native nid     : native/OS thread ID of a platform thread
virtual tid    : Java ID of a Virtual Thread; has no fixed native nid
request ID     : business/tracing identity; not a thread ID
~~~

A single request can pass through multiple phases or logical operations, and a virtual thread can mount onto different carriers over time. Use **request/trace IDs and timestamps** when correlating behavior between the application layer and the JVM.

## 5. Thread.dump_to_file: the path for virtual threads

Oracle Java 21 documentation on virtual threads introduces **Thread.dump_to_file** with text and JSON output. On HotSpot JDK 21, verify first:

~~~bash
jcmd 12345 VM.version
jcmd 12345 help Thread.dump_to_file
~~~

**12345 is an illustrative PID.** The command may not exist on a non-HotSpot VM, a specific JDK build, or a runtime image lacking jcmd. **jcmd -l** may also omit JVMs inside isolated Docker containers; PIDs must be obtained from appropriate process/runtime discovery.

### 5.1. Exporting JSON

~~~bash
jcmd 12345 Thread.dump_to_file -format=json /diagnostics/vthreads-incident-001.json
~~~

The file is created by **the target JVM** inside its filesystem/mount namespace. With JSON, tools can parse **thread containers, thread identities, and stack traces** without regexing console lines; exact structure and field types can evolve across JDK versions.

**Do not hardcode a JDK 21 parser to handle every version**. For instance, JSON formats in later JDKs may alter the type of the **tid** field or how thread containers are represented. Parsers should check the actual format/schema and have tests for supported JDK builds.

### 5.2. Exporting text/plain

A way less sensitive to format-name variations is using the **default format** with a `.txt` extension:

~~~bash
jcmd 12345 Thread.dump_to_file /diagnostics/vthreads-incident-001.txt
~~~

The Java 21 guide also illustrates **-format=text**; however, in some HotSpot help/builds, the format name may be described as **plain** instead of **text**. Use **jcmd PID help Thread.dump_to_file from the exact target JVM** as authoritative; if text format is desired and the command defaults to plain, omitting `-format` as above is a simple choice.

**Do not confuse with shell redirection**:

~~~bash
jcmd 12345 Thread.print -l > ./platform-threads.txt
~~~

In the latter command, **>** is handled by the shell running **jcmd**; **./platform-threads.txt** is placed in the **shell's** current working directory, not an output path opened by the JVM. Meanwhile, **/diagnostics/...** in **Thread.dump_to_file** belongs to the **target JVM's** filesystem.

### 5.3. Limits of virtual-aware dumps in JDK 21

While more useful for observing virtual threads, this format in JDK 21 has limits:

1. **Omits object addresses and many monitor/lock details** shown by traditional dumps; thus it lacks data to build complete lock-ownership graphs as `jstack -l` typically does.
2. **Does not provide JNI statistics, heap statistics, or a fixed native-thread-to-virtual-thread mapping.**
3. **Not an atomic snapshot of all threads at the exact same nanosecond.** Java threads keep changing as data is collected; a virtual thread can finish mid-dump.
4. **Virtual-thread listing scope depends on implementation and how threads are organized/tracked.** The **HotSpotDiagnosticMXBean.dumpThreads** API in JDK 21 guarantees all platform threads and may include **some or all virtual threads**. Never treat line/thread counts in a file as an exact 100% live count across all deployments.
5. **Output can be huge** when a JVM has many virtual threads; generating and writing the file incurs CPU/I/O/memory cost and disk-full risk.
6. **Does not prove causality.** Seeing many stacks waiting on a method does not by itself tell you how long threads waited or whether it is causing saturation.

For this reason, during incidents capture **both traditional dumps and virtual-aware dumps** when questions involve native locks/carriers alongside virtual tasks. If the JDK has been upgraded beyond Java 21, re-read help/docs for that exact version before assuming the limits above.

## 6. A compilable Java 21 example: seeing the gap in legacy APIs

This program creates **6 virtual threads** using **Executors.newVirtualThreadPerTaskExecutor()** and holds them waiting on a **CountDownLatch** so a thread dump can be taken easily. The program also self-verifies that **ThreadMXBean.getThreadInfo(virtualThreadId)** does not return ThreadInfo for a virtual thread, and **Thread.getAllStackTraces()** does not contain them.

**File VirtualThreadVisibilityLab.java:**

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class VirtualThreadVisibilityLab {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(6);
        CountDownLatch release = new CountDownLatch(1);
        ConcurrentLinkedQueue<Thread> observed =
                new ConcurrentLinkedQueue<>();

        ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor();
        try {
            for (int i = 0; i < 6; i++) {
                executor.submit(() -> {
                    observed.add(Thread.currentThread());
                    ready.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            ready.await();
            Thread sample = observed.peek();
            ThreadMXBean bean =
                    ManagementFactory.getThreadMXBean();

            System.out.println("virtualTasks=6");
            System.out.println("sampleIsVirtual="
                    + sample.isVirtual());
            System.out.println("threadInfoIsNull="
                    + (bean.getThreadInfo(sample.threadId()) == null));
            System.out.println("legacyStackMapContainsSample="
                    + Thread.getAllStackTraces().containsKey(sample));
            System.out.println("platformThreadCount="
                    + bean.getThreadCount());
            System.out.println("pid="
                    + ProcessHandle.current().pid());
            System.out.println("captureWindowSeconds=45");

            Thread.sleep(45_000L);
        } finally {
            release.countDown();
            executor.close();
        }
        System.out.println("DONE");
    }
}
~~~

Compile and run with JDK 21:

~~~bash
javac --release 21 VirtualThreadVisibilityLab.java
java VirtualThreadVisibilityLab
~~~

**The first four lines have deterministic values per Java SE 21 under normal execution:**

~~~text
virtualTasks=6
sampleIsVirtual=true
threadInfoIsNull=true
legacyStackMapContainsSample=false
~~~

Next, **platformThreadCount=...** and **pid=...** have **JVM/OS-dependent** values, followed by **captureWindowSeconds=45**. At the end of the wait window (roughly 45 seconds), the program finishes with **DONE**. **There is no fixed PID or platform-thread count**, and actual timing can vary slightly due to scheduling.

**Why is this code safer than an unsynchronized demo?**

- **ready.await()** guarantees all 6 tasks have started and registered their thread objects before the program measures.
- **CountDownLatch.await()** lets the virtual threads wait cleanly; on HotSpot JDK 21, this wait can **unmount**, so it does not necessarily hold 6 carriers.
- **ConcurrentLinkedQueue** stores references to Thread objects to test the exact virtual ID without listing via MXBean.
- **finally** releases tasks on interrupts/errors and **executor.close()** waits for completion.
- **getThreadInfo** returning null follows the ThreadMXBean contract for virtual thread IDs, not because the program “dropped” tasks.

**Limitations:** the demo is not a load test and does not guarantee every dump implementation always emits exactly 6 virtual entries. It clearly illustrates that **legacy APIs cannot see existing virtual thread objects**.

### 6.1. Capturing both ways during the 45-second window

From a second terminal, **replace PID with the real number printed to stdout**. For example, assuming the JVM PID in the same environment is **24680**:

~~~bash
jcmd 24680 VM.version
jcmd 24680 help Thread.dump_to_file
jcmd 24680 Thread.print -l
jcmd 24680 Thread.dump_to_file -format=json /tmp/vt-lab-24680.json
~~~

**/tmp** is only for lab use where space/permissions allow; inside containers, the JVM's `/tmp` may differ from the shell's `/tmp`. For the JSON file, open it in the JVM's exact filesystem. For production apps, pick a provisioned diagnostic volume rather than writing large dumps into a small writable layer.

**Expected qualitative result:** Thread.print shows mostly platform/carrier threads; the JSON dump has virtual-thread visibility, usually showing the threads from the lab executor. Exact thread names, stacks, IDs, container hierarchy, and entry counts **depend on HotSpot build and timing**. If the command is missing or attach fails, do not claim Java 21 lacks virtual threads: verify VM vendor, PID, permissions, JDK tools, and actual version.

### 6.2. Reading a JSON dump methodically

Instead of just counting total entries, an analyst should look for:

1. **Process info and runtime version**: is this the exact JVM causing the incident?
2. **Thread containers/hierarchy** if supported by the format: in which executor or task group were virtual threads created?
3. **Thread names/IDs**: were helpful names configured or do only generic/default names appear?
4. **Groups of similar top stack frames**: are many tasks waiting on socket reads, queue takes, lock acquisition, sleep, or Future.get?
5. **Dump timestamps and matching request spans**: did the snapshot catch the latency-spike window?
6. **Missing data**: lock ownership/native details, event durations, and tasks finished before the snapshot; supplement with JFR and application telemetry.

**Do not assume a current JSON format always carries the same thread state or lock owner fields as JDK 25/26.** Build parsers against the format's version/spec rather than interpolating from one snapshot or a random JSON sample on the Internet.

## 7. When thread dumps lack data: combining observation sources

| Question | Preferred tool | Evidence to combine |
| --- | --- | --- |
| How many **platform/carrier threads**? | ThreadMXBean, jstack/Thread.print, OS threads | CPU, host/cgroup limits, JVM process identity. |
| How many **virtual tasks** are waiting? | Thread.dump_to_file, application active/queued metrics | Executor/task lifecycle, sampling, request tracing. |
| Why is a virtual task waiting? | Virtual-aware stacks, app logs/traces | Dependency latency, socket/DB pools, queue lengths. |
| Is **pinning** holding carriers while blocking? | JFR jdk.VirtualThreadPinned, tracePinnedThreads | Duration, stack site, traffic/concurrency, CPU. |
| Is a **native thread CPU-hot**? | OS top -H / perf paired with Thread.print | Native TID, carrier stacks, sampling profiler. |
| Suspected **deadlock** among tasks? | Lock graphs, application-level correlation, Thread.print for platform | Virtual-aware stacks, dependency/lock ownership outside JDK 21 dumps. |
| Errors submitting/unparking virtual threads? | JFR jdk.VirtualThreadSubmitFailed | Resource saturation, scheduler activity, errors. |
| Too many long-lived virtual threads? | Application metrics + repeated virtual-aware dumps | Request lifecycle, pool/connection resources, heap growth. |

**One snapshot does not tell the whole history.** Thread dumps describe threads at capture time; JFR describes events across a recording window; tracing connects business operations. Strong conclusions usually require at least two independent sources.

## 8. Pinning in Java 21: when a carrier is not released

In **JDK 21**'s virtual threads implementation, a virtual thread can become **pinned** to its carrier in certain situations, notably:

- The virtual thread executes a blocking operation **inside a synchronized block or synchronized method**.
- The virtual thread is inside a **native method or foreign function** and cannot unmount like standard Java blocking I/O.

**Pinning is not by itself a correctness bug.** It primarily degrades scalability when **frequent and long-lasting**: many carriers stay pinned during blocking operations, leaving the scheduler fewer carriers for other virtual threads.

~~~text
Normal operation on JDK 21:
Virtual A -- I/O block --> unmount; Carrier 1 free
Virtual B -- ready    --> mounts onto Carrier 1

When virtual C is pinned:
Virtual C -- blocking in synchronized --> Carrier 2 is held
Virtual D -- ready --> may have to wait for another carrier
~~~

Do not automatically conclude scheduler thread starvation from **a small carrier count**; examine **throughput, queues, latency, blocking durations**, and pinning evidence.

### 8.1. JFR VirtualThreadPinned

JDK 21 supports JFR events:

| JFR event | Meaning | Default per Oracle documentation |
| --- | --- | --- |
| **jdk.VirtualThreadStart** | Virtual thread started. | **Disabled** by default. |
| **jdk.VirtualThreadEnd** | Virtual thread ended. | **Disabled** by default. |
| **jdk.VirtualThreadPinned** | Virtual thread was pinned when a blocking operation exceeded threshold. | **Enabled** by default, threshold **20 ms**. |
| **jdk.VirtualThreadSubmitFailed** | Starting or unparking a virtual thread failed, usually resource-related. | **Enabled** by default. |

These defaults belong to **Oracle's JDK 21 guide**, not a guarantee that every independent recording/profile uses identical settings. Inspect event settings on the actual recording if needed.

Example finite-duration JFR recording (path is on the JVM's filesystem):

~~~bash
jcmd 24680 JFR.start \
  name=vt-triage \
  settings=profile \
  duration=60s \
  filename=/diagnostics/vt-triage.jfr
~~~

Use only with verified JVM PID, permissions, and operator review of disk/overhead. The recording may not write the final file until the configured duration finishes. **JFR.start** does not automatically enable **jdk.VirtualThreadStart/End**; if needed, enable those events explicitly via JMC or custom JFR settings.

Once the file is retrieved to a machine with the **jfr CLI**:

~~~bash
jfr print \
  --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed \
  /path/to/vt-triage.jfr
~~~

To include Start/End if they were enabled:

~~~bash
jfr print \
  --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed \
  /path/to/vt-triage.jfr
~~~

**/path/to/vt-triage.jfr** is the file on **the machine running jfr**, not automatically the JVM container path once copied. JFR data is recorded over time; it reveals **duration and stack events** better than a point-in-time dump, yet covers only events **enabled and exceeding thresholds**.

### 8.2. jdk.tracePinnedThreads for JDK 21

In JDK 21 HotSpot, you can use the startup property:

~~~bash
java -Djdk.tracePinnedThreads=full -jar application.jar
~~~

or **short** mode:

~~~bash
java -Djdk.tracePinnedThreads=short -jar application.jar
~~~

**application.jar** is only a deployment placeholder name, not a file created by this lesson. **full** prints detailed stacks when a virtual thread blocks while pinned; **short** prints more directly relevant frames. This is a **JDK 21** diagnostic aid typically configured at startup; it can generate heavy log output, so do not leave it enabled unconditionally in production.

**Do not infer “no tracePinnedThreads output” means zero pinning of any kind**. Threshold/event semantics, activity level, code paths, and tracing limitations all apply. Prefer JFR for duration/frequency statistics, paired with source code and workload analysis.

### 8.3. Illustrating a synchronized block that can cause pinning

**Illustrative snippet, not a standalone program**:

~~~java
synchronized (sharedLock) {
    // An I/O call that may block for a long time on JDK 21.
    callBlockingRemoteService();
}
~~~

If **callBlockingRemoteService()** causes a virtual thread to block inside synchronized on JDK 21, the carrier may be held. An appropriate adjustment where suitable is using **ReentrantLock** for the synchronized region, with **try/finally**:

~~~java
lock.lock();
try {
    callBlockingRemoteService();
} finally {
    lock.unlock();
}
~~~

**Do not blindly replace every synchronized with ReentrantLock as a fad**. The two mechanisms differ in semantics (fairness, conditions, lock ownership, monitor behavior); ensure correctness, test concurrency, measure before/after, and only refactor **long-blocking, high-frequency** regions.

**Version scope:** pinning around synchronized is an important characteristic in **Java 21**. Newer JDK releases modify virtual thread and synchronization behavior; if upgrading JDKs, read documentation for that exact version rather than carrying over JDK 21 pinning descriptions verbatim.

## 9. Snapshot blind spot: not knowing how long a thread has waited

Suppose a dump at 12:00 shows 4,000 virtual threads with top stack frames like:

~~~text
java.util.concurrent.CountDownLatch.await(...)
com.example.service.DownstreamClient.waitForResult(...)
com.example.service.RequestHandler.handle(...)
~~~

This is a **hypothetical sample**, not guaranteed real class/stack names. There are at least three distinct interpretations:

1. **High but healthy traffic**: many requests wait briefly while completion rate remains healthy.
2. **Slow upstream/downstream**: requests pile up due to DB/socket/remote APIs, raising latency.
3. **System failing to complete tasks**: latches/queues/futures are never released, and live task counts climb continuously.

**A single snapshot cannot distinguish all three cases.** You need to measure:

- Active request counts over time.
- Throughput and completion/failure rates.
- Waiting duration/histograms and timeout rates.
- Connection pools, queue depths, socket timeouts, and lock metrics.
- JFR events and second/third dumps.
- Application span IDs/logs tagged with instance/trace.

**Survivorship bias trap:** dumps observe threads **still alive at capture time**; completed tasks are not represented. Seeing a large WAITING group does not tell you its proportion of **all requests processed**. Likewise, a virtual thread stuck for several minutes has a much higher probability of appearing in every snapshot than a task living only a few milliseconds.

## 10. Arithmetic analysis example: never infer virtual counts from carrier counts

Suppose at one moment:

~~~text
Platform threads in ThreadMXBean : 48
Observed carrier threads         : 16
Live virtual threads per app metric: 12,000
Virtual threads in one dump file   : 11,760
~~~

These are **hypothetical numbers**, not real output. You **must not** compute:

~~~text
12,000 - 48 = 11,952 virtual threads missing from the JVM
~~~

because **ThreadMXBean counts and virtual task counts measure two different populations**; platform counts include JVM/GC/service threads, while virtual-aware dumps have different coverage and capture timing. Nor should you conclude the 240-thread gap between the metric and dump file is **240 “lost” threads**: tasks may have finished/started between samples, some virtual threads may be dumped differently, or the metric may define active tasks differently from live Thread objects.

An honest way to write the report:

~~~text
12:00:00.000Z app.activeTasks = 12,000 (per instrumentation)
12:00:00.200Z JVM platformThreadCount = 48
12:00:01.700Z dump file completed; parser read 11,760 virtual entries

Conclusion: Observation sources differ in scope and timestamp.
Compare definitions/coverage before claiming thread increases/decreases.
~~~

Do not use **12,000/16 = 750** as a universal alert threshold. One carrier can serve many virtual threads **over time**, rather than running 750 virtual threads simultaneously on a single OS thread.

## 11. Investigating high CPU: a hot carrier does not mean one fixed request

With traditional platform threads, operators commonly run:

~~~bash
top -H -p 24680
jcmd 24680 Thread.print -l
~~~

Then convert the native TID from decimal to hex to find **nid=...** in the dump. That remains useful for **platform threads/carriers**, yet cannot build a fixed **OS TID -> virtual thread** table.

**Reason:** a virtual thread can unmount and later resume on another carrier. When the CPU sample is taken, a carrier may be running one task; when the dump is captured, it may already be running a different task. Therefore, matching by TID seconds later can misattribute context.

When CPU is high:

1. Use **OS tools** to identify hot native carrier/platform threads.
2. Use a **sampling profiler/JFR ExecutionSample** (if configured compatibly with virtual threads) to collect stacks over time.
3. Take **Thread.print** when you need carrier/native states, and **Thread.dump_to_file** to see live virtual stacks.
4. Correlate **timestamps, thread names, trace IDs**, VM version, and workload.
5. If virtual tasks perform long CPU computation, virtual threads do not make that computation faster; investigate algorithms/CPU budgets, not just the scheduler.

**Never label “hot carrier thread = virtual thread X burned CPU for 5 minutes” without continuous sampling evidence.**

## 12. Questions that virtual-aware dumps still do not answer completely

### 12.1. Deadlocks and lock ownership

In **JDK 21**, virtual-aware dumps do not preserve enough monitor/lock details to completely replace **Thread.print -l** when analyzing lock ownership relationships. At the same time, **ThreadMXBean.findDeadlockedThreads()** has platform-only semantics. For deadlocks/wait cycles among virtual tasks, add **application-level lock/dependency graphs**, tracing, and supporting tools.

### 12.2. Thread-local context

Virtual threads support **ThreadLocal** and **InheritableThreadLocal**, yet can instantiate huge numbers of Thread objects. Dumps do not automatically list every ThreadLocal value or prove a context memory leak. If retention is suspected, inspect heap/allocations/lifecycles and redacted logs rather than trying to extract secrets from dumps.

### 12.3. Scheduler and queue status

A JSON file with many **waiting** stacks does not automatically tell you how many pending tasks the scheduler holds, queue backlog, or whether starvation exists. Java 21 must not be assumed to include every dedicated command/MXBean from newer JDKs, such as virtual-thread scheduler commands appearing in Java 25/26 docs. **Check jcmd PID help and documentation for the exact running JDK 21**, using framework metrics and JFR if commands are absent.

### 12.4. Blocking history and duration

A dump is an image of the capture window. **It does not directly measure** how many times a virtual thread parked, how long it was pinned, how many ms an I/O call took, or which request waited longest. JFR and application traces have duration/timestamp fields better suited to those questions when events are enabled.

### 12.5. Threads that exited before the dump

The absence of a thread entry in the file does not prove it **never existed**. A task can be created and finish between two samples. To count lifecycles, use **started/completed/active** metrics and controlled JFR Start/End events.

## 13. Collecting production evidence by intrusion level

When investigating a Java 21 application using virtual threads, do not immediately grab a multi-hundred-MB dump. Proceed purposefully:

**Phase A — Confirm target and context.**

- Identify Pod/container/service instance, full Java version, and VM implementation.
- Check the PID **in the namespace where jcmd runs**. A Java PID inside a container can differ from the host PID.
- Record workload: request rate, p95/p99 latency, active tasks, queues, CPU, memory, and downstream errors.
- Verify the runtime supports **Thread.dump_to_file** and the output target has permissions/disk space.

**Phase B — Gather lower-noise evidence.**

~~~bash
jcmd 24680 VM.version
jcmd 24680 help Thread.print
jcmd 24680 help Thread.dump_to_file
~~~

`help`/`VM.version` confirm tool capabilities. If the goal is only platform thread counts or current CPU, there is no need to dump all virtual threads to disk immediately.

**Phase C — When stacks are genuinely needed.**

~~~bash
jcmd 24680 Thread.print -l > ./platform-24680.txt
jcmd 24680 Thread.dump_to_file -format=json /diagnostics/virtual-24680.json
~~~

In the first command, the file goes to the **shell's** cwd; in the second, the file is created by the **JVM**. Never assume both appear on the same filesystem. Pick fresh filenames to avoid overwriting; check disk/ephemeral-storage and retrieval policies.

**Phase D — Collect over time when needed.**

If pinning/throttling/submit failures are suspected, plan a 30–120 second JFR recording or suitable window, checking enabled events/thresholds. Do not enable VirtualThreadStart/End broadly across millions of short-lived threads without measuring event overhead.

**Phase E — Verify and conclude.**

- Does the file exist and parse cleanly under the right version/tool?
- Are captures from the same instance, same workload, and properly timestamped?
- Which stack groups warrant investigation, and are they symptom or cause?
- Which lock/native/JFR duration/transaction IDs are still missing?
- Retrieve files/disable temporary debug configs and protect diagnostic data.

### 13.1. Do not take excessive consecutive thread dumps

Every dump has **stack-scanning/serialization and I/O cost**. With 100,000 virtual threads, a JSON file can be huge and cause disk pressure or JVM latency itself. Pick a sensible sample count, such as **two or three samples during an incident**, spaced far enough to see trends; **this is not a fixed cadence suitable for every system**.

Never run thread dumps in a 100 ms loop in production just to “watch in real time”. For continuous behavior, use metrics/JFR with clear sampling or event controls.

## 14. Docker/Kubernetes: file location, permissions, and secrets

Inside containers, three boundaries can differ:

| Boundary | Situation | How to handle |
| --- | --- | --- |
| **PID namespace** | JVM is PID 1 in container, host PID 48210. | Use the exact PID matching where jcmd runs; never add/subtract PIDs. |
| **Mount namespace** | JVM sees /diagnostics, host sees /srv/diag/app. | Pass **/diagnostics/...** to Thread.dump_to_file if that is the JVM's mount. |
| **Permissions** | jcmd runs as root while JVM runs as UID 10001. | The JVM needs write permission at the target path; shell privileges do not replace JVM privileges. |
| **Ephemeral/PVC storage** | Large dump fills writable layer/emptyDir. | Check df -h, df -i, quotas, ephemeral-storage, PVC limits, and retention. |
| **Logging/identity** | SIGQUIT dumps to container logs or files copied to a laptop. | Know where streams/files go; protect sensitive stack traces/metadata. |

Example when the image contains JDK tools and the JVM is confirmed as **PID 1 inside the container**:

~~~bash
docker exec java-service jcmd 1 VM.version
docker exec java-service jcmd 1 Thread.dump_to_file \
  -format=json /diagnostics/vthreads-incident.json
~~~

**The JVM is not always PID 1**: shells, tini, supervisors, or shareProcessNamespace can give Java another PID. In Kubernetes, target the exact container:

~~~bash
kubectl exec java-pod -c app -- jcmd 1 VM.version
kubectl exec java-pod -c app -- jcmd 1 Thread.dump_to_file \
  -format=json /diagnostics/vthreads-incident.json
~~~

Commands are conditional examples only; substitute real Pod/namespace/container/PID/path, verify the image has jcmd, matching JVM attach permissions, and a valid mount. **kubectl exec** does not make `/diagnostics` on your laptop become `/diagnostics` inside the JVM.

**Dump files can contain stacks, class/package names, paths, and request metadata**. Do not post to public channels, restrict read permissions, and delete per post-incident policy. After copying to an analysis workstation, verify file completeness, size/checksum, and local disk space.

## 15. Troubleshooting scenario: requests hang yet jstack shows only 40 threads

A Java 21 service using **Executors.newVirtualThreadPerTaskExecutor()** reports rising p99 and 8,000 active requests; **jstack** shows 40–60 threads, with many carriers in WAITING/RUNNABLE.

**First mistake:** concluding there are 8,000 tasks yet only 40 threads so the app “ran out of threads” or active-request metrics are wrong.

**Correct analysis:**

1. Checking **platform thread** counts via jstack/ThreadMXBean may show only 40–60—completely normal despite thousands of virtual threads.
2. Record active requests from app metrics, check queue depth/timeouts/completion rates: 8,000 is **task count**, not native-thread count.
3. Use **Thread.dump_to_file -format=json** to inspect live virtual stacks during the investigation window. Most may be waiting on **socket I/O**, queues, futures, or locks; do not assume entry count equals the exact 8,000 figure.
4. If a large group of stacks awaits DB connections, inspect **pool limits, DB latency, pending queues, and timeouts**. If a large group is pinned, use **JFR VirtualThreadPinned** to find sites and durations.
5. Supplement with **Thread.print -l** when carrier/native locks or platform-thread deadlocks matter; JDK 21 JSON dumps do not carry all that data.
6. After adjusting downstream/pool/concurrency behavior, re-measure **throughput, p99, active task count, and pinning event rate** under comparable load.

**Example evidence-based conclusion:** “Platform thread counts are stable; most virtual tasks are awaiting a slow dependency according to tracing and virtual-aware stacks; there is no evidence of carrier exhaustion yet.” This is much stronger than “the JVM has no threads”, because it respects the exact scope of each data source.

## 16. Comparison matrix: pinning, blocked I/O, and CPU

| Phenomenon | Traditional dump | Virtual-aware dump | Other critical sources |
| --- | --- | --- | --- |
| **10,000 requests waiting on sockets** | May show only carriers and system threads. | May show many virtual stacks waiting on I/O. | Active request metrics, socket/DB latency, timeout rates. |
| **Carrier pool held by pinned blocking** | Carrier/native stacks may show blocking calls. | Virtual stacks pinpoint current code area, lacking duration. | JFR VirtualThreadPinned, JDK 21 tracePinnedThreads. |
| **Many CPU-bound tasks** | Native CPU samples/Thread.print reflect carriers. | Virtual stacks at snapshot, does not measure per-task CPU over time. | JFR/sampling profiler, throughput, cgroup CPU throttling. |
| **Suspected virtual task deadlock** | Thread.print -l helps for platform locks but is incomplete. | Shows waiting stacks, lacks full JDK 21 lock ownership/deadlock detection. | App lock graphs, tracing, lock metrics, heap/JFR if needed. |
| **Request finishes too fast to appear in dump** | Missing from snapshot. | Also likely missing. | Start/end/latency metrics, JFR Start/End when enabled. |
| **JVM process cannot be attached to** | jstack/jcmd fails. | Also likely fails due to same attach mechanism. | Runtime permissions, container identity, pre-enabled logs/JFR. |

**Do not equate pinning with RUNNABLE.** A pinned virtual thread may be blocked inside synchronized/native code, holding its carrier; meanwhile, a CPU-bound virtual thread running continuously on a carrier is not necessarily pinning. Separate causes using events and stacks.

## 17. Exercises with answers

**Q1.** ThreadMXBean reports 64 threads, while the framework reports 20,000 active tasks using virtual threads. Do the two numbers contradict?

**Answer:** no. ThreadMXBean counts only live **platform threads** in Java 21; active task metrics belong to the application layer and can include many virtual threads.

**Q2.** jstack shows only ForkJoinPool carriers and a few worker threads. Can you conclude there are no waiting virtual threads?

**Answer:** no. Unmounted virtual threads do not have dedicated native stacks/OS threads to appear in traditional dumps. Use **Thread.dump_to_file** or appropriate metrics/tracing.

**Q3.** Thread.getAllStackTraces() omits a Thread object verified to have **isVirtual() == true**. Is this a bug?

**Answer:** no, that is Java SE 21 behavior by spec: the method returns stacks for live **platform threads** and excludes virtual threads.

**Q4.** ThreadMXBean.getThreadInfo(virtualId) returns null even though the virtual thread is alive. Why?

**Answer:** the interface supports only platform threads; null is the documented result for virtual thread IDs, not proof the thread died.

**Q5.** Using Thread.dump_to_file JSON you see 10,000 virtual entries. Can you state the JVM held exactly 10,000 virtual threads at one atomic point in time?

**Answer:** not necessarily. Account for implementation/coverage, collection duration, and threads changing mid-dump. Correlate app metrics and version details.

**Q6.** A JDK 21 JSON dump lacks monitor owners, so you conclude there is no lock contention. Is that right?

**Answer:** wrong. JDK 21 virtual-aware dumps do not carry the full monitor/lock details of traditional dumps. You need Thread.print -l, other JFR/monitoring, and application data.

**Q7.** A virtual thread ran on carrier TID=721 and later on TID=744. Did the JVM necessarily clone a new thread?

**Answer:** no. A virtual thread can unmount and remount on different carriers. Native TID is not an immutable identity for a virtual thread.

**Q8.** JFR shows zero VirtualThreadPinned events in one minute. Does that prove zero pinning occurred?

**Answer:** no. The event must be enabled and exceed the threshold (JDK 21 guide cites 20 ms default); short events or differing semantics are not captured. Check JFR settings/workload.

**Q9.** You see synchronized around a remote call and high latency with Java 21 virtual threads. Should you replace every synchronized in the app with ReentrantLock?

**Answer:** no. Investigate **long-blocking, frequent** hotspots using JFR/stacks; replace only appropriate sites after verifying semantics and testing concurrency.

**Q10.** Running jcmd from the host, Thread.dump_to_file outputs to `/diagnostics/vt.json` inside a container. Where do you look for the file?

**Answer:** the path is opened by **the target JVM** inside its mount namespace. Look inside the matching container/mount, rather than assuming `/diagnostics` on the host holds the same file.

**Q11.** Thread.print -l reveals platform lock owners. Can it completely replace JSON virtual-aware dumps?

**Answer:** no. They complement each other: traditional dumps excel at platform/native/lock details, while dump_to_file expands virtual thread visibility with fewer lock/JNI details on JDK 21.

**Q12.** VirtualThreadStart/End do not appear by default in JFR recordings. Does that mean JFR does not support virtual threads?

**Answer:** no. JFR supports those events, yet they are **disabled by default** per JDK 21 documentation; they can be enabled via custom settings/JMC when needed, keeping in mind event volume can be large.

## 18. Common mental traps and anti-patterns

1. **“One virtual thread = one OS native thread.”** False: runtime mounts/unmounts them onto carriers.
2. **“ThreadMXBean.getThreadCount counts every Java Thread.”** False in Java 21: it counts platform threads.
3. **“getAllStackTraces lists every live virtual thread.”** False by API contract.
4. **“Thread X missing from jstack means task X does not exist.”** False when tasks run on virtual threads.
5. **“Thread.print -l is a complete inventory of virtual threads.”** Incorrect.
6. **“Thread.dump_to_file includes full object locks/JNI/heap like Thread.print.”** Incorrect on JDK 21.
7. **“JSON thread dumps are atomic snapshots; entry count equals exact thread count.”** No such guarantee exists.
8. **“No deadlock report means all virtual dependencies are safe.”** Insufficient data.
9. **“Java Thread ID and Linux nid always map 1:1.”** False for virtual threads.
10. **“A hot carrier means one fixed virtual task ran on it all minute.”** Mounting shifts over time.
11. **“A WAITING virtual thread always holds an OS thread.”** It may have unmounted.
12. **“Pinning is always a bug and all synchronized must be deleted.”** No; it is mainly risky when blocking is long/frequent.
13. **“No VirtualThreadPinned events means zero pinning.”** Thresholds and configuration still apply.
14. **“Enabling VirtualThreadStart/End costs nothing.”** Volume can be huge with short-lived tasks.
15. **“One snapshot suffices to pinpoint latency root cause.”** Timelines/metrics are required.
16. **“Taking hundreds of thread dumps has no system impact.”** Overhead and disk/network risks exist.
17. **“Thread.dump_to_file writes to the jcmd caller's cwd.”** The target JVM creates the file.
18. **“No jcmd in the image means the JVM does not support virtual threads.”** Tooling availability differs from runtime capability.
19. **“A JDK 26 command will definitely work on JDK 21.”** False; check the target version.
20. **“activeTasks always equals live Java virtual thread count.”** Task lifecycles/instrumentation can differ.
21. **“Stable platform thread count means stable request concurrency.”** Measurement scopes differ.
22. **“Virtual threads make all CPU-bound operations faster.”** They increase blocking-I/O concurrency, not single-thread compute speed.
23. **“Container PID equals host PID.”** False across different PID namespaces.
24. **“Virtual threads cannot be debugged.”** You can use virtual-aware dumps, JFR, debuggers, metrics, and traces within proper scope.

## 19. Checklist before and after collecting evidence

| Question | Verification |
| --- | --- |
| What is the JDK/VM? | Full Java 21 version/vendor, HotSpot or other implementation. |
| Are virtual threads actually used? | Code/deployment flags, executor config, traces/metrics. |
| Are PID and namespace right? | Container/host context, VM.version, matching user/attach permissions. |
| Which group is ThreadMXBean counting? | Platform-only per Java SE 21. |
| Do you need native locks/carriers or virtual task stacks? | Choose Thread.print, Thread.dump_to_file, or both. |
| Is Thread.dump_to_file supported? | jcmd PID help Thread.dump_to_file on the exact target. |
| Is the file saved on the right filesystem? | Absolute path inside JVM, owner/quota/disk, mounts. |
| When was it captured? | Incident timestamps, workload baseline, appropriate sample count. |
| Are duration/history needed? | JFR events/thresholds and tracing alongside snapshots. |
| Is pinning suspected? | JDK 21 synchronized/native blocking; JFR VirtualThreadPinned. |
| Is deadlock suspected? | Account for missing lock details in JSON and ThreadMXBean; add graphs. |
| Does the data contain sensitive info? | Restrict permissions and retention for dumps/JFR. |
| Were diagnostic configs restored? | Stop/disable temporary recordings/logs, retrieve files safely. |

## References

- [Oracle Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): platform/virtual model, mounting, pinning, JFR events, Thread.dump_to_file.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): design rationale and limits of traditional thread dumps in Java 21.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform-only contract, getAllThreadIds, dumpAllThreads, and deadlock detection.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): isVirtual, threadId, getAllStackTraces.
- [Java SE 21 — Executors.newVirtualThreadPerTaskExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html#newVirtualThreadPerTaskExecutor()): virtual thread per task executor.
- [Java SE 21 — HotSpotDiagnosticMXBean.dumpThreads](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html#dumpThreads(java.lang.String,com.sun.management.HotSpotDiagnosticMXBean.ThreadDumpFormat)): platform and virtual thread scope, file output, and API limits.
- [JDK 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): VM.version, help, Thread.print, JFR.start, and attach requirements.
- [Oracle Java 21 — JFR Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): inspecting events in recording files.
- [Inside Java — Managing Throughput with Virtual Threads](https://inside.java/2024/02/04/sip094/): virtual thread dump/JFR examples and throughput observation.
- [Oracle Java SE 21 — Flight Recorder API Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.pdf): recording design, event settings, stacks, and observation overhead.

**Conclusion:** traditional thread dumps on Java 21 remain essential for investigating **platform threads, native TIDs, and lock-related evidence**, yet **must not be interpreted as a complete list of virtual threads**. When workloads use many virtual threads, use **Thread.dump_to_file**, JFR, and time-series task/request data; when suspecting pinning/deadlock/CPU, combine **Thread.print -l, OS profiling, and application evidence**. Only compare metrics with **matching definitions, the exact JVM, aligned timestamps, and known observation scope**.