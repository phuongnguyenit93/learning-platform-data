# 10.4. Limitations of ThreadMXBean and Platform-Thread-Only Observability Tools

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **platform threads**, **virtual threads**, and **carrier threads** when reading JVM observability metrics.
- Explain why `ThreadMXBean`, JMX, and several traditional thread APIs/tools do not expose all virtual threads.
- Avoid drawing wrong conclusions about request counts, hangs, CPU usage, or deadlocks from platform-thread-only metrics.
- Select thread dumps, JDK Flight Recorder (JFR), application metrics, and tools according to JDK version when investigating systems using virtual threads.

**Version scope:** Virtual threads became permanent in **Java 21**. The primary APIs and examples below run on Java 21+. Diagnostic utilities introduced in newer JDKs are marked separately.

## 1. Origin of the Observability Limitation

A **platform thread** typically maps one-to-one to an operating system thread (OS thread). A **virtual thread** is still a `java.lang.Thread` object with its own ID, yet the JVM schedules it onto platform threads called **carriers**. When a virtual thread performs a compatible blocking operation, it can suspend (*unmount*) so the carrier can serve another virtual thread, then resume (*mount*) on a carrier when ready.

Three distinct quantities must be separated:

1. **Platform thread count:** OS/JVM threads, including carriers and many other platform threads.
2. **Live virtual thread count:** logical tasks currently running or waiting; this number can be very large.
3. **Busy carrier count:** platform threads currently used to run virtual threads; this does not reflect every unmounted virtual thread.

For example, a service may have tens of thousands of virtual threads waiting on I/O while `ThreadMXBean.getThreadCount()` returns only a few dozen. This can be completely normal: the count **includes only platform threads**. Never conclude that the service has only a few dozen active requests.

Virtual threads do not make a CPU computation run faster. Their primary value is increasing concurrency for tasks that frequently wait on I/O.

## 2. The Actual Contract of ThreadMXBean

`java.lang.management.ThreadMXBean` is obtained via `ManagementFactory.getThreadMXBean()` or the JMX ObjectName `java.lang:type=Threading`. According to the Java 21 Javadoc, this MXBean supports monitoring and management of **platform threads only**; virtual threads are outside its scope.

| Method Group | What the Data Reflects | What Must Not Be Inferred |
|---|---|---|
| `getThreadCount()`, `getPeakThreadCount()`, `getDaemonThreadCount()` | Current, peak, and daemon **platform thread** counts | Not virtual thread or request counts |
| `getTotalStartedThreadCount()` | Total platform threads created and started | Does not reflect virtual threads created |
| `getAllThreadIds()` | IDs of live platform threads | Does not list virtual thread IDs |
| `getThreadInfo(id)`, `getThreadInfo(ids, ...)` | `ThreadInfo` for platform threads | Returns `null` for a virtual thread ID; dead or nonexistent threads can also yield `null` |
| `dumpAllThreads(...)` | Stacks and synchronization info of platform threads | The word "All" does not mean it includes all virtual threads |
| `getThreadCpuTime(id)`, `getThreadUserTime(id)` | CPU time of a platform thread if supported/enabled | Returns `-1` for a virtual thread ID, which does not mean 0 CPU used |
| `getCurrentThreadCpuTime()`, `getCurrentThreadUserTime()` | CPU time of the current thread if it is a platform thread | Calling from a virtual thread does not return that virtual thread's own CPU time (typically `-1` if the JVM supports measurement) |
| `findMonitorDeadlockedThreads()`, `findDeadlockedThreads()` | Deadlock cycles among platform threads for API-supported lock types | **Does not detect** cycles involving virtual threads |

Important details to understand:

- `ThreadInfo` is a `ThreadMXBean` snapshot model, not a record of every Java `Thread`.
- `isThreadCpuTimeSupported()` and `isThreadCpuTimeEnabled()` describe CPU measurement capability/state for **platform threads** only. Enabling them does not add virtual thread support to the API.
- Depending on the JVM and method, lack of CPU measurement support can throw `UnsupportedOperationException`; invalid or inapplicable data can return `-1`. Check both capability support and the returned value.
- `findDeadlockedThreads() == null` means only "no cycle found **within the API's scope**," not proof that no virtual thread is stuck.
- Reading a **carrier's** CPU or stack is not reading the historical CPU or stack of a specific virtual thread that the carrier once ran. A virtual thread can switch carriers and unmount while waiting.

## 3. Java 21+ Example: A Live Virtual Thread "Absent" from the MXBean

We create one platform thread and one virtual thread, both waiting on a `CountDownLatch`. `ready` confirms both tasks have started; `release` keeps them alive until measurements complete.

Create the file **`ThreadMxBeanScopeDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public class ThreadMxBeanScopeDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Runnable work = () -> {
            ready.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread platform = Thread.ofPlatform().name("platform-demo").start(work);
        Thread virtual = Thread.ofVirtual().name("virtual-demo").start(work);

        try {
            ready.await();
            ThreadMXBean bean = ManagementFactory.getThreadMXBean();
            long[] ids = bean.getAllThreadIds();

            System.out.println("platform.isVirtual=" + platform.isVirtual());
            System.out.println("virtual.isVirtual=" + virtual.isVirtual());
            System.out.println("MXBean has platform="
                    + Arrays.stream(ids).anyMatch(id -> id == platform.threadId()));
            System.out.println("MXBean has virtual="
                    + Arrays.stream(ids).anyMatch(id -> id == virtual.threadId()));
            System.out.println("ThreadInfo(platform) != null="
                    + (bean.getThreadInfo(platform.threadId()) != null));
            System.out.println("ThreadInfo(virtual) == null="
                    + (bean.getThreadInfo(virtual.threadId()) == null));
            System.out.println("getAllStackTraces has virtual="
                    + Thread.getAllStackTraces().containsKey(virtual));
        } finally {
            release.countDown();
            platform.join();
            virtual.join();
        }
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac ThreadMxBeanScopeDemo.java
java ThreadMxBeanScopeDemo
```

Exact output of the example:

```text
platform.isVirtual=false
virtual.isVirtual=true
MXBean has platform=true
MXBean has virtual=false
ThreadInfo(platform) != null=true
ThreadInfo(virtual) == null=true
getAllStackTraces has virtual=false
```

**Explanation:** both `Thread` instances are alive. `ThreadMXBean` sees the platform thread, but does not list the virtual thread's ID and does not return a `ThreadInfo` for the virtual thread. The last line confirms `Thread.getAllStackTraces()` also lists only platform threads. "Absent from the list" reflects an **API limitation**, not an unstarted or dead thread.

If you already hold a reference to a specific virtual thread, `virtual.getStackTrace()` can inspect its stack while it is alive. That method **does not** provide a way to enumerate all virtual threads in the JVM, and its result is a point-in-time snapshot.

## 4. Which Tools See Only Platform Threads vs. Support Virtual Threads?

| API / Tool | Observation Scope | Appropriate Use |
|---|---|---|
| JMX `java.lang:type=Threading`, dashboards pulling from `ThreadMXBean` | Platform threads per the Java API contract | Name metrics `platform_threads`; do not label them total requests or total logical threads |
| `Thread.getAllStackTraces()`, `Thread.activeCount()`, `Thread.enumerate()`, `ThreadGroup.activeCount()/enumerate()` | Legacy enumeration mechanisms that exclude virtual threads | Use to find platform threads, not to count virtual threads |
| OS tools like `top -H`, `ps -L`, and native thread views | OS threads/carriers; do not list individual virtual threads | Inspect CPU load and OS thread counts, then correlate with JVM/application data |
| Traditional HotSpot thread dumps, `jstack`, `jcmd <PID> Thread.print` | Primarily platform threads; depending on version may show some **mounted** virtual threads, but does not cover unmounted ones | Analyze carrier, native frames, platform stacks, and locks |
| `jcmd <PID> Thread.dump_to_file` on supporting JDKs | Dump designed to observe virtual threads, outputting text/JSON | Prefer when virtual thread stacks are needed; verify actual coverage/detail per JDK |
| JDK Flight Recorder (JFR), JDK Mission Control | Events for virtual thread lifecycle, pinning, or scheduling failures | Investigate along a timeline alongside dumps and metrics |

**Note:** `Thread.dump_to_file` and traditional HotSpot dumps are not identical. Java 21 documentation notes that `Thread.dump_to_file` can display virtual threads while omitting some object address, lock, JNI, and heap details compared to traditional dumps. JDK releases evolve presentation and coverage, so never infer "not in a dump file" as "does not exist." Check `java -version` and `jcmd <PID> help` before diagnosing.

## 5. Diagnosing a System Using Virtual Threads

### 5.1. Waiting/Hanging Tasks: Take a Virtual-Thread-Aware Dump

On JDK 21+ supporting the command and with proper JVM access permissions:

```bash
jcmd -l
jcmd <PID> Thread.dump_to_file -format=text threads.txt
jcmd <PID> Thread.dump_to_file -format=json threads.json
```

Replace `<PID>` with the real PID. The two dump commands represent **two format choices**; you do not have to run both. Text is quick to read; JSON suits analysis tools. Look for thread names, states, and stacks at I/O waits, locks, or dependencies. If your JDK version does not include sufficient lock details in this dump type, supplement it with traditional dumps, JFR, and application data.

Virtual thread names should reflect the type of work (e.g., an `http-request-` prefix), and logs/traces should include a business correlation ID. Thread IDs cannot replace request/trace IDs, especially when work spans multiple services.

### 5.2. Time-Based Issues: JFR

Relevant JFR events include:

- `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd`: start and end events. **Disabled by default** on JDK 21; enable deliberately because systems can create vast numbers of virtual threads.
- `jdk.VirtualThreadPinned`: reports pinning exceeding a configurable threshold; the JDK 21 default threshold is **20 ms**. Pinning mechanics change in some newer JDK releases, so check your version.
- `jdk.VirtualThreadSubmitFailed`: failure to start or reschedule a virtual thread, potentially tied to resource exhaustion.

Once `recording.jfr` has been captured, run:

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

An event only appears if the recording configuration captures it; **zero events** does not prove no problem exists. Correlate with latency, timeouts, I/O, connection pools, and downstream errors.

### 5.3. Adding Task and Scheduler Metrics

When an application handles requests with virtual threads, measure **task lifecycle** metrics: in-flight requests/tasks (incremented at start, decremented in `finally`), start/completion rates, p95/p99 latency, errors, timeouts, I/O wait levels, and connection pool usage. Those numbers answer "how much work is active" far better than `ThreadMXBean.getThreadCount()`.

**Since JDK 24:** `jdk.management.VirtualThreadSchedulerMXBean` and the `jcmd Thread.vthread_scheduler` and `Thread.vthread_pollers` commands were introduced to inspect the scheduler and I/O pollers. The MXBean exposes **estimates** such as mounted virtual threads, queued virtual threads, pool size, and parallelism. They are **not** a total live virtual thread counter and are unavailable in Java 21. Do not put these APIs/commands into programs that must compile on JDK 21.

## 6. Real-World Scenarios and How to Reason About Them

**A. `threadCount = 45` yet several thousand requests are waiting.**  
Wrong conclusion: "only 45 requests are active." `threadCount` includes only platform threads; cross-check in-flight request metrics, I/O, and virtual-thread-aware dumps/JFR.

**B. `getThreadInfo(virtualId) == null`.**  
Wrong conclusion: "the virtual thread is dead." The API returns `null` for a virtual thread ID even while the thread is alive. If you hold a `Thread` reference, check `isAlive()`/`getState()`; to inspect the whole JVM, use virtual-thread-aware tools.

**C. `getThreadCpuTime(virtualId) == -1`.**  
Wrong conclusion: "the thread used 0 ns of CPU." `-1` means valid data is unavailable through this API. Use JVM/process CPU or a virtual-thread-aware profiler; do not attribute an entire carrier's CPU to a single virtual thread.

**D. `findDeadlockedThreads()` returns `null` yet the service is hung.**  
Wrong conclusion: "definitely no deadlock." The API ignores cycles involving virtual threads. Investigate cross-dependencies, lock/I/O wait points, timeouts, JFR, and dumps; lock detail depends on the JDK version.

**E. `jstack` does not show an unmounted virtual thread.**  
Wrong conclusion: "the task does not exist." A waiting virtual thread may not occupy any carrier. Use virtual-thread-aware dumps/JFR, logs, and corresponding traces.

## 7. Monitoring Design Checklist

1. Clearly label **what is being counted**. Metrics from `ThreadMXBean` are platform-thread metrics.
2. Check the **JDK version** and actual command/API capabilities, especially the scheduler MXBean added in JDK 24.
3. Distinguish **0**, **`-1` / `null`**, and **out of API scope**.
4. Track in-flight tasks, latency, timeouts, errors, and downstream waits at the application layer.
5. Combine carrier stacks/CPU with virtual-thread dumps, JFR, and correlation IDs.
6. Collect enough data to diagnose, while weighing the overhead of large dumps and JFR start/end events at very high task rates.

### Self-Check Questions

- Why can `getThreadCount()` be very small compared to the number of virtual threads waiting on I/O?
- Why is `getThreadInfo(virtualId) == null` insufficient to conclude a virtual thread has terminated?
- Why does `getThreadCpuTime(virtualId) == -1` not mean 0 CPU usage?
- Why does a "no deadlocks" result from `ThreadMXBean` not rule out deadlocks involving virtual threads?
- When traditional thread dumps and virtual-thread-aware dumps differ, what metrics/JFR events should you combine with them?

## Official Documentation

- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform-thread-only contract.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `isVirtual()`, `threadId()`, `getAllStackTraces()`.
- [Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): carriers, JFR, thread dumps.
- [Java SE 24 — VirtualThreadSchedulerMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html): scheduler capabilities introduced in Java 24.
