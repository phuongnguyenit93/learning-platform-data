# jcmd Thread.print, jstack, and ThreadMXBean: Thread Diagnostics in Java

> Scope: Java SE/JDK 17+, focusing on observing JVM concurrency using thread dumps and the `java.lang.management` API. Commands and sample outputs are verified with OpenJDK 21. Content covers general Java concurrency only; Spring is not used.

## 1. Lesson Objectives

When a Java application is slow, hangs, or exhibits abnormal CPU usage, the question to answer is not just "how many threads are there?" but also:

- Which threads are executing code, waiting on a lock, waiting for a signal, sleeping, or waiting on I/O?
- Are two or more threads holding each other's locks, resulting in a **deadlock**?
- Is **lock contention** degrading throughput even without a deadlock?
- Which wait locations recur across snapshots taken at different times?
- How can you collect evidence without modifying code or restarting the application?

Three tools address different needs:

| Tool | Usage | Best Suited For |
| --- | --- | --- |
| **`jcmd <pid> Thread.print`** | JDK tool that sends a diagnostic command to a running JVM | Taking thread dumps externally; optional lock and extended information |
| **`jstack -l <pid>`** | JDK tool for capturing stack traces and lock information | Quick dump collection or cross-checking with `jcmd` |
| **`ThreadMXBean`** | Java API `ManagementFactory.getThreadMXBean()` | In-process inspection, automatic deadlock detection, and retrieving thread count/CPU/contended time if supported by the JVM |

**A thread dump is a point-in-time snapshot**, not a complete history. Do not conclude a root cause from a single thread in `WAITING` or `BLOCKED` state: combine stacks, lock owners, progression across multiple samples, execution time, system load, and logs.

## 2. Starting with the PID and JDK Environment

These tools are included in the **JDK** distribution. Open a terminal with `java`, `jcmd`, and `jstack` on your `PATH`, or invoke them directly from the JDK's `bin` directory.

```bash
java -version
jcmd -l
```

`jcmd -l` typically prints the PID and main class/JAR of discoverable JVMs. Once you have identified the right process:

```bash
jcmd <pid> VM.version
jcmd <pid> help
jcmd <pid> help Thread.print
```

In the example commands, **replace `<pid>` with the actual PID**, such as `jcmd 12345 Thread.print`. `<pid>` is a placeholder; do not type the angle brackets literally into the shell.

Operational notes:

1. Run the tool on the **same machine or same PID environment** as the JVM. With containers, the PID inside the container and the PID on the host may differ; `jcmd -l` from the host does not always list JVMs inside containers. You may need to enter the target container or namespace to diagnose.
2. Attaching is subject to OS access permissions. `jcmd` normally requires the same effective user/group as the target Java process; hardened environments may restrict attach.
3. Use an appropriate JDK, ideally the same Java version or one compatible with the running JVM; diagnostic commands and flags can differ across versions or JVM vendors.
4. `jcmd -l` not finding an application **does not prove** the application has stopped. Verify the PID using OS process management tools; check containers, permissions, and attach configuration.
5. Thread dumps can contain thread names, class/method names, and business execution paths. Store logs/dumps in a protected location; consider redacting sensitive data when sharing.

## 3. `jcmd Thread.print`: Taking a Thread Snapshot

Practical syntax with HotSpot/OpenJDK 21:

```bash
jcmd <pid> Thread.print
jcmd <pid> Thread.print -l
jcmd <pid> Thread.print -e
jcmd <pid> Thread.print -l -e
```

Diagnostic command options:

- **`-l`**: includes information about `java.util.concurrent` locks (ownable synchronizers), useful for `ReentrantLock` and certain other lock mechanisms.
- **`-e`**: prints extended thread information if supported by the implementation.
- **`help Thread.print`**: queries the target JVM for the exact options available.

Example saving a snapshot via redirection:

```bash
jcmd 12345 Thread.print -l -e > thread-dump-1.txt
```

`12345` is only an illustrative PID. The file is created in the shell's current working directory, not in the JVM's directory by default. On machines where error output also needs to be preserved, check terminal messages and the exit code; if attach or permissions fail, the file may not contain a valid dump.

`Thread.print` incurs diagnostic overhead proportional to the number of threads and the amount of metadata collected; JDK documentation classifies its impact as **Medium**, varying with thread count. Avoid invoking it continuously at very high frequency on JVMs with a very large number of threads, especially under resource saturation.

### 3.1. What Does a Thread Dump Show?

A simplified illustrative thread dump entry looks like this:

```text
"worker-A" #31 ... java.lang.Thread.State: BLOCKED (on object monitor)
    at example.Worker.process(Worker.java:42)
    - waiting to lock <0x00000007ab...> (a java.lang.Object)
    at example.Worker.run(Worker.java:18)

"worker-B" #32 ... java.lang.Thread.State: TIMED_WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.parkNanos(...)
```

This is a **format illustration**, not stdout from the program in Section 7; thread names, lock addresses, `nid`, line numbers, and JVM formatting may differ.

Components to read:

- **Thread name**: set by the JVM/framework or application; meaningful naming speeds up diagnostics.
- **Thread state**: Java state at the sampling instant, not CPU percentage or severity.
- **Stack frames**: current method and call chain; look for where application code begins and the call that is waiting.
- **`waiting to lock` / `parking to wait for`**: the object/lock the thread is waiting on.
- **`locked` / `Locked ownable synchronizers`**: locks currently held by the thread, if provided by the dump and JVM.
- **`nid` information**: native thread ID, typically shown in hex on HotSpot; useful when correlating with CPU-consuming threads in OS tools. **Do not confuse** `nid` with the Java thread ID or the process PID.

Do not assume a `RUNNABLE` thread is heavily using CPU. Depending on the native API and implementation, `RUNNABLE` can also be observed while a thread is in an I/O operation or system call.

### 3.2. Collecting Multiple Snapshots to Observe Progression

If a request appears hung, take 2–3 dumps a few seconds apart (interval depending on load and expected processing time). Compare **the same thread or the same worker group**:

- Do the stack and lock owner remain unchanged?
- Is the thread consistently waiting on the same monitor/lock?
- Is the number of waiting threads increasing while threads doing actual work decrease?
- Is a deadlock listed by the dump, or is a lock wait cycle visible through owner IDs?
- Do threads move across frames between samples?

Three identical dumps are a signal to investigate, **not automatic proof of a deadlock**: a thread waiting on a queue when there is no work can be completely normal.

## 4. `jstack`: Standalone Stack Dump Tool

With JDK 21:

```bash
jstack <pid>
jstack -l <pid>
jstack -l 12345 > jstack-1.txt
```

`-l` enables **long listing** to print additional lock information; useful when correlating threads with `java.util.concurrent.locks`. `jstack` typically reports deadlock information if it detects a matching lock cycle.

JDK 21 documentation marks the `jstack` command as **experimental/unsupported**; in operations, prefer `jcmd Thread.print` when possible because it is the officially documented and more broadly supported diagnostic command path on HotSpot. Only use options listed in `jstack -help` for the installed version: do not assume legacy options such as `-F` or `-m` are available in every JDK.

### 4.1. Comparing `jcmd` and `jstack`

| Aspect | `jcmd Thread.print` | `jstack` |
| --- | --- | --- |
| Purpose | Diagnostic command sent to a running JVM | Capture Java stacks of a JVM process |
| Lock flags on JDK 21 | `-l`; add `-e` for extended information | `-l` |
| Extensibility | `jcmd` provides many other diagnostic commands | Focused on thread stacks |
| Version/syntax | Check `jcmd <pid> help Thread.print` | Check `jstack -help` |
| When scripting | Text output can be redirected and parsed carefully | Can also be redirected, though format is not a stable machine API |

Do not build production parsers that depend on fixed column counts or a single regex for a dump: format, native IDs, headers, lock footers, and virtual thread information may change across JDK versions.

## 5. `ThreadMXBean`: Gathering Evidence Directly in Code

Java SE provides the `java.lang.management.ThreadMXBean` interface in the **`java.management`** module. Access the JVM's thread management singleton:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

This snippet belongs **inside** an appropriate Java class/method, not as a standalone program with `main`. `ThreadMXBean` lets you inspect **platform threads** and their corresponding management states.

### 5.1. Key APIs to Know

| API | Meaning | Limitations to Keep in Mind |
| --- | --- | --- |
| `getThreadCount()` | Current number of live platform threads | Instantaneous snapshot; excludes virtual threads on JDK 21 |
| `getPeakThreadCount()` | Peak number of platform threads since startup/reset | Does not reflect historical peak before reset |
| `getTotalStartedThreadCount()` | Total platform threads started | Cumulative value, not current thread count |
| `getAllThreadIds()` | Java IDs of live platform threads | A thread may terminate before `ThreadInfo` is fetched |
| `getThreadInfo(ids, depth)` | State, lock owner, and stack up to `depth` frames | An element may be `null` if the thread has already terminated |
| `dumpAllThreads(monitors, synchronizers)` | Snapshot of stacks and locks for platform threads | Check monitor/synchronizer support; incurs overhead |
| `findMonitorDeadlockedThreads()` | Finds deadlock cycles caused by **object monitors** (`synchronized`) | Does not detect `ReentrantLock`-only deadlocks |
| `findDeadlockedThreads()` | Finds deadlock cycles across monitors **and ownable synchronizers** | JVM must support synchronizer monitoring |
| `getThreadCpuTime(id)` | Cumulative CPU nanoseconds for a platform thread | Requires capability enabled; may return `-1` |
| `isThreadContentionMonitoringSupported()` | Does the JVM support measuring blocked/waited time? | Supported does not mean enabled |

`findMonitorDeadlockedThreads()` **only** detects monitor cycles. `findDeadlockedThreads()` has broader coverage, but cannot detect every kind of application "hang": network waits, flags that are never set, waiting on futures, starvation, or logical dependencies not modeled by monitor/ownable synchronizer ownership.

### 5.2. Safe Snapshot Example

The following is illustrative logic **inside a Java method**:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();

ThreadInfo[] threads = bean.dumpAllThreads(monitors, synchronizers);
for (ThreadInfo info : threads) {
    if (info == null) continue;
    System.out.printf("%s [%s] owner=%s%n",
            info.getThreadName(),
            info.getThreadState(),
            info.getLockOwnerName());
}
```

You must import `java.lang.management.ThreadInfo` and `ThreadMXBean`. Only enable lock metadata collection when the JVM reports support to avoid `UnsupportedOperationException`. Printed values depend on the live process, so there is **no fixed stdout** for this snippet.

### 5.3. Retrieving CPU Time and Contention Time

```java
if (bean.isThreadCpuTimeSupported() && !bean.isThreadCpuTimeEnabled()) {
    bean.setThreadCpuTimeEnabled(true);
}
long cpuNanos = bean.isThreadCpuTimeSupported()
        ? bean.getThreadCpuTime(threadId) : -1L;
```

The snippet above only illustrates usage in a context with `bean` and `threadId`; it is not a standalone program. Enabling CPU time can be resource-intensive and may be denied in restricted environments; handle errors and configuration accordingly. `-1` can mean measurement is disabled, the thread has terminated/is invalid, or it is unsupported for that thread type. CPU time measures *CPU usage time*, not wall-clock time. To determine CPU growth, take two samples for the **same thread ID** and compare the delta when both samples are valid.

To analyze blocked/waited time using `ThreadInfo`, check `isThreadContentionMonitoringSupported()`, and enable `setThreadContentionMonitoringEnabled(true)` only when needed. This feature is usually off by default and has overhead. `getBlockedTime()` / `getWaitedTime()` may return `-1` when monitoring is not enabled; `getBlockedCount()` and `getWaitedCount()` must be interpreted according to the Java API definition—do not infer "total wait time" from wait counts.

## 6. Analyzing Thread States, Lock Owners, and Real-World Scenarios

### 6.1. Distinguishing Thread States

| `Thread.State` | Meaning at Sampling Time | Careful Interpretation |
| --- | --- | --- |
| `NEW` | Not yet `start()`ed | Not included in common **live threads** dump listings |
| `RUNNABLE` | Potentially running or ready to run in the JVM | Does not prove the thread is consuming 100% CPU |
| `BLOCKED` | Waiting to enter a `synchronized` **intrinsic monitor** | Check `waiting to lock`, lock owner, stack, and wait duration |
| `WAITING` | Waiting without a timeout; e.g., `Object.wait()`, `Thread.join()`, `LockSupport.park()` | Idle thread pool workers waiting on a queue can wait a long time and still be normal |
| `TIMED_WAITING` | Waiting with a time limit; e.g., `sleep()`, `wait(timeout)`, timed park | Not automatically an error; could be backoff or a periodic timer |
| `TERMINATED` | Completed | Usually absent from live thread dumps |

**`BLOCKED`** in Java thread state only relates to waiting on an intrinsic monitor; a `ReentrantLock.lock()` can show `WAITING` or `TIMED_WAITING` via `LockSupport.park` under contention. Therefore, do not search only for the word "BLOCKED" and conclude there is no lock contention.

### 6.2. How Deadlock Differs from Contention and Starvation

- **Deadlock:** a lock wait cycle—for example, A holds lock 1 and waits for lock 2, while B holds lock 2 and waits for lock 1. Neither thread can proceed without external release/cancellation; with `synchronized` in the example below, there is no automatic timeout.
- **Contention:** multiple threads want the same resource, but the owner continues working and periodically releases the lock. It can cause severe slowdowns, yet **is not a deadlock**.
- **Starvation:** tasks are not scheduled/allocated enough resources, possibly due to an exhausted worker pool, priorities, or long-running work monopolizing resources. Starvation can still occur when `findDeadlockedThreads()` returns `null`.
- **Blocking I/O:** threads waiting on sockets/files or downstream services. Stacks may be inside I/O APIs; check downstream latency and timeouts rather than assuming a monitor issue.
- **Livelock:** multiple threads keep changing state and consuming CPU without making progress toward a result. A single point-in-time dump may not clearly reveal the issue; multiple samples and business progress metrics are needed.

### 6.3. Reading Lock Ownership

With `ThreadInfo`:

- `getLockName()` indicates the lock object being waited on, if any.
- `getLockOwnerName()` / `getLockOwnerId()` describe the thread holding the lock, when this information is available.
- `getLockedMonitors()` returns the set of object monitors currently held by the thread (when requested and supported by the JVM).
- `getLockedSynchronizers()` returns the set of ownable synchronizers currently held by the thread (when requested and supported).

Look for an **ownership chain**: A waits for a lock held by B; B waits for a lock held by C; C waits for a lock held by A. If there is a cycle, verify with `findDeadlockedThreads()` or the dump's deadlock footer. Thread names are just labels; **Java thread IDs** distinguish threads with duplicate names; native IDs and Java IDs use different numbering systems.

## 7. Java 17+ Hands-On Lab: Creating a Deadlock and Inspecting with All Three Tools

The program below creates **two platform daemon threads** that intentionally acquire two monitors in opposite order. Two `CountDownLatch` instances? Not needed: a single `BOTH_LOCKED` latch ensures both threads have acquired their first lock before attempting to acquire the second. `ThreadMXBean` detects the deadlock cycle; the program pauses at `System.in.read()` so you can run `jcmd` and `jstack` in another terminal.

> The deadlock here is **intentionally created in a lab**. Do not copy opposite lock ordering into real application code. The threads are marked daemon so the JVM can exit when you press Enter.

Save to **`ThreadDumpLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.CountDownLatch;

public class ThreadDumpLab {
    private static final Object LEFT = new Object();
    private static final Object RIGHT = new Object();
    private static final CountDownLatch BOTH_LOCKED = new CountDownLatch(2);

    private static void awaitPeer() {
        BOTH_LOCKED.countDown();
        try {
            BOTH_LOCKED.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static Thread newWorker(String name, Object first, Object second) {
        Thread worker = new Thread(() -> {
            synchronized (first) {
                awaitPeer();
                synchronized (second) {
                    // Unreachable when both threads hold locks in opposite order.
                }
            }
        }, name);
        worker.setDaemon(true);
        return worker;
    }

    public static void main(String[] args) throws Exception {
        Thread left = newWorker("demo-left-first", LEFT, RIGHT);
        Thread right = newWorker("demo-right-first", RIGHT, LEFT);
        left.start();
        right.start();

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long[] ids = null;
        for (int attempt = 0; attempt < 100; attempt++) {
            ids = bean.findMonitorDeadlockedThreads();
            if (ids != null) break;
            Thread.sleep(50);
        }
        if (ids == null) throw new IllegalStateException("No deadlock detected");

        ThreadInfo[] infos = bean.getThreadInfo(ids, 10);
        Arrays.sort(infos, Comparator.comparing(ThreadInfo::getThreadName));
        System.out.println("deadlock found: " + infos.length);
        for (ThreadInfo info : infos) {
            System.out.println(info.getThreadName() + ": "
                    + info.getThreadState() + ", waits for " + info.getLockOwnerName());
        }
        System.out.println("Press Enter to exit...");
        System.in.read();
    }
}
```

Compile and run (Terminal A):

```bash
javac ThreadDumpLab.java
java ThreadDumpLab
```

Stdout on OpenJDK 21 (compiled and run):

```text
deadlock found: 2
demo-left-first: BLOCKED, waits for demo-right-first
demo-right-first: BLOCKED, waits for demo-left-first
Press Enter to exit...
```

The program is now **waiting for Enter**. Open Terminal B to find the PID and capture dumps:

```bash
jcmd -l
jcmd <pid> Thread.print -l -e > jcmd-threads.txt
jstack -l <pid> > jstack-threads.txt
```

Substitute the PID of `ThreadDumpLab` for `<pid>`. Search for `demo-left-first`, `demo-right-first`, `BLOCKED`, and the **Java-level deadlock** section at the end of the dump. On OpenJDK 21, both commands were verified to return exit code 0 and contain both thread names along with the `Found one Java-level deadlock` report. Lock addresses, IDs, and stack line numbers vary per run and are therefore not shown as fixed stdout.

**Step-by-step explanation:**

1. `left` enters `synchronized(LEFT)`, and `right` enters `synchronized(RIGHT)`.
2. Each thread decrements `BOTH_LOCKED` and waits until **both** hold their first lock; this is why the example does not rely on `Thread.sleep()` to "hope a deadlock happens."
3. Once the latch reaches 0, `left` tries to acquire `RIGHT` held by `right`; `right` tries to acquire `LEFT` held by `left`.
4. Both threads become `BLOCKED`. `findMonitorDeadlockedThreads()` returns the Java IDs of the monitor cycle; `getThreadInfo(ids, 10)` provides the state and lock owner of those threads.
5. The `ThreadInfo` array is sorted by name before printing so stdout is deterministic; PID/native IDs still vary.
6. Both threads are daemons, so pressing Enter lets `main` exit and the JVM terminate even though they are still deadlocked. This **does not fix the deadlock**; it only ends the lab process.

Although `findMonitorDeadlockedThreads` polls for up to roughly 5 seconds, the loop duration is not a universal wait bound for all environments. On heavily loaded machines or JVMs that do not support attach/monitoring as expected, check for errors rather than assuming identical output.

### 7.1. Analyzing Differences Between the API and Dumps

- **`ThreadMXBean`** lets the program read Java thread IDs and answer deadlock questions programmatically.
- **`jcmd`** lets operators inspect an application that has no built-in collection code. It prints stacks of observable JVM threads; do not confuse native IDs with `ThreadInfo.getThreadId()`.
- **`jstack`** is an additional option for cross-checking; on JDK 21 it also reports the example's deadlock.
- All three reflect the **current JVM state**, not terminated threads or full history. For transient outages, multiple samples or a time-series recording mechanism are required.

## 8. Common Troubleshooting Workflows

### 8.1. Application Hangs Without Returning a Result

1. Verify the **correct JVM** (PID, main class, uptime, version, and container).
2. Capture `jcmd <pid> Thread.print -l -e` and save it with a timestamp; if needed, repeat for several snapshots spaced at an appropriate interval.
3. Look for the deadlock footer, `BLOCKED` threads, and owner chains. If there is no deadlock, inspect `WAITING`, `TIMED_WAITING`, pool queues, and wait points such as `Future.get`, `CountDownLatch.await`, `Object.wait`, and `LockSupport.park`.
4. Correlate with application logs, deadlines, counters, or request IDs. Many threads waiting on an empty queue is often normal; an executor whose workers are all waiting on `Future.get()` for tasks submitted **to that same pool** can be starvation.
5. Fix the root cause: lock acquisition order, reducing lock hold time, separating pools for dependent tasks, adding proper timeouts/cancellation, or reducing the number of workers competing for a resource.

### 8.2. High CPU

A single thread dump does not rank CPU usage. Use OS tools to identify CPU-consuming native threads, convert the TID to match HotSpot's `nid` format when correlating; or enable/read `ThreadMXBean.getThreadCpuTime(id)` if supported by the JVM and track the **delta** across multiple samples. Look for loops/busy-spinning in stacks and use a CPU profiler/JFR when appropriate.

Do not confuse a `RUNNABLE` thread with a CPU core at 100%, nor treat `Thread.State.BLOCKED` as "high CPU." Thread state reflects synchronization status at a single point in time.

### 8.3. Throughput Drop or Thread Pool Exhaustion

If many threads keep the same stacks at queue/future/lock wait points, check:

- Is a contended resource causing many workers to wait?
- Is a pool submitting work to **itself** while waiting on results from tasks not yet scheduled?
- Is slow I/O or downstream throttling keeping workers busy waiting?
- Are there too many threads causing context switching, or too few workers for the workload characteristics?

Combine dumps with **active worker** counts, queue length, rejection count, task completion rate, and queue wait time. Thread dumps show *where threads are waiting*; metrics show *the magnitude of impact and trends over time*.

## 9. Limitations and Caveats on Modern Java

### 9.1. Virtual Threads on Java 21

Standard `ThreadMXBean` in Java SE 21 monitors **platform threads** and does **not** provide a full listing or state of virtual threads. Therefore:

- `getThreadCount()` does not count total virtual threads.
- `getAllThreadIds()`, `getThreadInfo(...)`, and `dumpAllThreads(...)` do not provide full inspection of virtual threads.
- Both `find...DeadlockedThreads()` methods do not detect cycles involving virtual threads in Java 21.

Similarly, **do not assume** every JDK's `jcmd Thread.print`/`jstack` will display all existing virtual threads. Check your JDK version and virtual-thread diagnostics support; when incidents involve virtual threads, you may need JFR or specialized thread dump formats/tools supported by your JVM. Do not conclude "no virtual threads are waiting" simply because they do not appear in a particular dump format.

### 9.2. Overhead, Snapshots, and Sensitive Data

- Capturing full stacks and lock metadata has a cost that grows with thread count; collect moderately.
- Thread IDs and stacks are **snapshots**: a thread can terminate between fetching its ID and querying its info, resulting in a `null` `ThreadInfo` element.
- Enable contention monitoring or CPU time monitoring only when needed, and evaluate the cost in production-like environments.
- Dumps can expose worker names, package names, and business flow structures. Apply appropriate access controls, retention, and data handling.
- Attach tools may be unavailable due to containers, permissions, or JVM flags; an attach failure does not prove whether a deadlock exists.

### 9.3. Do Not Turn Diagnostic APIs into Synchronization Mechanisms

Do not use `getThreadState()`, `getThreadCount()`, `getThreadInfo()`, or `blockedTime` statistics to decide lock ownership, business progression, or whether a task has "completed." This is monitoring data subject to races and overhead. Synchronization logic must rely on proper primitives such as `synchronized`, `Lock`, `CountDownLatch`, `CompletableFuture`, `volatile`, or other concurrency primitives.

## 10. Common Mistakes and Fixes

| Mistake | Why Is It Wrong? | Fix |
| --- | --- | --- |
| Treating every `WAITING` thread as hung | Idle workers normally wait on a queue/condition | Inspect frames, owner, and business progress |
| Searching only for `BLOCKED` to find all lock contention | `ReentrantLock` can wait via `park` | Combine lock metadata, `-l`, and stack traces |
| Assuming `findDeadlockedThreads() == null` means no issue | It only detects certain lock cycles | Check for starvation, livelock, I/O, and virtual threads |
| Using a single dump to conclude CPU hotspots | Dumps do not measure cumulative CPU | Compare CPU deltas; use a profiler/JFR |
| Comparing Java thread IDs directly with `nid` | They are two different ID spaces | Convert native TIDs properly; verify JVM version |
| Assuming `getThreadInfo` is always non-null | Threads can terminate between reads | Check for `null` |
| Leaving contention metrics enabled long-term without measuring overhead | Tracking incurs runtime cost | Enable only for targeted observation |
| Overwriting dump files when taking multiple samples | Loses evidence over time | Write separate files with timestamps and context |
| Assuming `jcmd -l` sees JVMs in other containers | PID namespaces may differ | Verify PIDs in the target namespace |
| Assuming all virtual threads appear in `ThreadMXBean` on JDK 21 | Standard API only supports platform threads | Use virtual-thread diagnostic tools supported by your JVM version |

## 11. Check Your Understanding

Practice in order:

1. Create and run `ThreadDumpLab.java`. Explain why a single `CountDownLatch` is sufficient to make the deadlock happen consistently.
2. Use `jcmd -l` to identify the right PID, then save one dump with `Thread.print -l -e` and one with `jstack -l`. Locate both thread names and the deadlock footer.
3. Rename the two threads in code and run again. The thread names in the output change; explain why Java IDs, native IDs, and lock addresses still should not be treated as fixed data.
4. Modify both workers to acquire the monitors in the **same order**, then remove the diagnostic pause. Confirm no deadlock cycle occurs and explain why enforcing a consistent lock order prevents wait cycles.
5. Write a helper method using `ThreadMXBean` that checks synchronizer usage support and prints owner info for selected threads. Handle the case where a thread terminates between sampling steps.
6. Explain why `getThreadCount()` on JDK 21 cannot be used to count virtual threads, and why a single dump is not enough to prove starvation is absent.

## 12. Key Takeaways

- **`jcmd Thread.print`** is the primary way to capture thread dumps from outside the JVM, with `-l` and `-e` flags on JDK 21.
- **`jstack -l`** provides stacks and lock info; check support for your JDK version.
- **`ThreadMXBean`** provides an in-process API to query platform threads, capability-gated CPU/contended times, and two forms of deadlock checks.
- **Deadlock** is a wait cycle, **contention** is competition that can still make progress, and **starvation** is insufficient resource allocation; do not equate them by a single thread state name.
- Base conclusions on **multiple snapshots + lock ownership + metrics + business progress**, never on a single stack frame alone.

Official references:

- [The jcmd Command — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [The jstack Command — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html)
- [ThreadMXBean — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadInfo — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [Diagnostic Tools — Java SE 21 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
