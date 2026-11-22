# Limitations of ThreadMXBean and How to Use jcmd Thread.dump_to_file to Observe Virtual Threads

## 1. Why does checking threads the old way easily lead to wrong conclusions?

Since Java 21, a **virtual thread** is a `java.lang.Thread` managed by the JVM. It is well suited for many concurrent tasks that have to wait on I/O; the JVM can suspend a virtual thread and use the platform thread (carrier) to run other work. An application may have thousands of virtual threads active while having relatively few platform threads.

Therefore, checking a value such as `ManagementFactory.getThreadMXBean().getThreadCount()` and concluding that “the application only has a few dozen threads” **does not reflect the total number of virtual threads**. This API is defined to manage **platform threads**, not virtual threads. To see the stacks of virtual threads at a point in time, use a diagnostic tool that supports them, such as `jcmd <PID> Thread.dump_to_file`.

The scope of this article is Java SE/JDK in general. The examples use **JDK 21+** and run without any framework.

## 2. Understanding the boundary: platform thread, carrier, and virtual thread

- **Platform thread**: a Java thread bound to an operating system thread. `ThreadMXBean` focuses on monitoring this group.
- **Virtual thread**: a lightweight Java thread scheduled by the JVM. A waiting task may temporarily not occupy a carrier.
- **Carrier thread**: the platform thread that the scheduler is using to run a virtual thread while it is mounted. One carrier can serve many virtual threads sequentially, so **there is no 1:1 ratio**.

For example: an application has 4,000 virtual threads waiting on I/O operations. `ThreadMXBean.getThreadCount()` may still report only a small number of platform threads. The two values measure **two different things**; a small value from `ThreadMXBean` does not prove that the application has no task backlog.

```text
                Java process (JVM)
┌───────────────────────────────────────────────┐
│  Virtual threads (logical work)               │
│  VT-1  ─── waiting for I/O                     │
│  VT-2  ─── waiting for I/O                     │
│  VT-3  ─── running                             │
│  VT-4  ─── runnable                            │
│  ...                                          │
│                     │                         │
│           JVM scheduler/carriers              │
│                     ▼                         │
│  Platform threads (OS threads)                 │
│  carrier-A, carrier-B, main, GC/JVM threads... │
└───────────────────────────────────────────────┘
  ThreadMXBean       → platform threads
  jcmd dump_to_file  → platform + virtual threads
```

The diagram above only illustrates the difference in observation scope; it does not depict a fixed number of carriers or guarantee how the JVM schedules a specific task.

## 3. What does ThreadMXBean support, and where are its limits?

`java.lang.management.ThreadMXBean` is obtained via `ManagementFactory.getThreadMXBean()` (or JMX with ObjectName `java.lang:type=Threading`). As of Java SE 21, this interface **does not support monitoring/managing virtual threads**.

| Method | Value in an application with virtual threads |
| --- | --- |
| `getThreadCount()` | Number of live **platform threads**; does not include virtual threads |
| `getPeakThreadCount()` | Peak number of platform threads, not the peak number of virtual threads |
| `getTotalStartedThreadCount()` | Total number of platform threads ever started, excluding virtual threads |
| `getAllThreadIds()` | IDs of live platform threads; does not list virtual thread IDs |
| `dumpAllThreads(...)` | `ThreadInfo`/stacks of platform threads; does not dump all virtual threads |
| `getThreadInfo(virtualThreadId)` | Returns `null` for a virtual thread ID, even while that virtual thread is alive |
| `findDeadlockedThreads()` / `findMonitorDeadlockedThreads()` | Detects deadlock cycles within platform threads; does not detect cycles involving virtual threads |
| `getThreadCpuTime(id)` | CPU-time API for managing platform threads; not for measuring per-virtual-thread CPU time |

Some common mistakes:

- Setting a “total thread count” alert on `getThreadCount()` and assuming it already counts all virtual threads.
- Calling `dumpAllThreads(true, true)` and treating it as a complete snapshot of all concurrent work.
- Looking for a virtual thread in `getAllThreadIds()` and inferring that the thread has not been created because its ID is missing.
- Using `Thread.getAllStackTraces()` to list all virtual threads: since JDK 21, this API also returns only platform threads.
- Seeing many carriers and assuming there are that many virtual threads, or seeing few carriers and assuming there are few requests.

**`ThreadMXBean` is still useful** for inspecting platform threads, related synchronization info, and trends in carrier/OS thread counts, but its scope must be clearly labeled on dashboards. If you need the number of running tasks, I/O-waiting tasks, processing times, and application timeouts, add metrics at the task-processing layer. Do not try to infer the number of virtual threads solely from the platform-thread count.

## 4. Hands-on: a Java 21 program with 12 waiting virtual threads

The following example keeps 12 virtual threads alive while you run `jcmd` from another terminal window. To make them easy to find in the dump, all virtual threads have names starting with `demo-vt-`. The program prints the JVM's PID, compares against `ThreadMXBean`, and stays alive for about 90 seconds.

Create the file `VirtualThreadDumpDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class VirtualThreadDumpDemo {
    private static final int WORKERS = 12;

    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> workers = new ArrayList<>();

        for (int i = 0; i < WORKERS; i++) {
            Thread thread = Thread.ofVirtual()
                    .name("demo-vt-" + i)
                    .start(() -> {
                        ready.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    });
            workers.add(thread);
        }

        // All virtual threads have reached the ready point.
        ready.await();

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long sampleVirtualThreadId = workers.get(0).threadId();
        boolean listed = Arrays.stream(bean.getAllThreadIds())
                .anyMatch(id -> id == sampleVirtualThreadId);

        System.out.println("virtualThreadsStarted=" + WORKERS);
        System.out.println("sampleVirtualThreadListedByMXBean=" + listed);
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("platformThreadsByMXBean=" + bean.getThreadCount());
        System.out.println("Run jcmd in another terminal within 90 seconds");

        try {
            Thread.sleep(90_000);
        } finally {
            // Allow virtual threads to finish and avoid leaking work in the example.
            release.countDown();
            for (Thread thread : workers) {
                thread.join();
            }
        }
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac VirtualThreadDumpDemo.java
java VirtualThreadDumpDemo
```

Example initial output (the PID and platform thread count are **not fixed**):

```text
virtualThreadsStarted=12
sampleVirtualThreadListedByMXBean=false
pid=<actual PID printed by the program>
platformThreadsByMXBean=<number varies by JVM/environment>
Run jcmd in another terminal within 90 seconds
```

Why is `false` the expected result? `workers.get(0)` is a live virtual thread, but `ThreadMXBean.getAllThreadIds()` by specification only lists platform threads. `getThreadCount()` can also vary depending on JVM/scheduler activity; there is no single absolute value that applies to all machines. The `CountDownLatch.await()` call gives each virtual thread task a clear waiting stack in the dump.

Practice tip: open two terminals, run the program in the first terminal, and use the PID printed by the program in the second terminal. If the 90 seconds expire, re-run the program and grab the new PID. Do not use the PID of the `jcmd` process instead of the application PID.

## 5. Using jcmd Thread.dump_to_file step by step

`jcmd` is a utility bundled with the **JDK** that sends diagnostic commands to a running JVM. The `Thread.dump_to_file` command writes a thread dump to a file, including **platform threads and virtual threads**. Compared to `ThreadMXBean.dumpAllThreads()`, this is the appropriate tool for observing many virtual threads, including virtual threads blocked waiting on work.

### Step 1: identify the right JVM and access permissions

Run from another terminal on the same machine/environment that can attach to the Java process:

```bash
jcmd -l
```

This command is useful for listing Java processes visible from `jcmd`'s environment. In a container or for a JVM not visible in `jcmd -l`, use the PID printed by `ProcessHandle.current().pid()`, `ps`, or the corresponding process tool. Do not assume the PID on the host is the same as the PID inside a container with a different PID namespace.

Usual prerequisites: the `jcmd` tool must be compatible with the target JVM, the user must have sufficient permissions to attach, the JVM must not be shutting down, and the Attach API must not be disabled by configuration. Check available diagnostic commands for the **target JVM**:

```bash
jcmd 12345 help
jcmd 12345 help Thread.dump_to_file
```

Replace **12345** with the actual PID. Syntax, options, and formats may differ across JDK versions; the authoritative source when operating is the `help` output of the running JVM.

### Step 2: generate a JSON dump

On Linux/macOS, choose an **absolute path** on a filesystem where the target Java process has write permission:

```bash
jcmd 12345 Thread.dump_to_file -format=json /tmp/virtual-threads-12345.json
```

On Windows, use an existing writable directory, such as `C:\temp`:

```powershell
jcmd 12345 Thread.dump_to_file -format=json C:\temp\virtual-threads-12345.json
```

These are **command templates**: replace the PID and path to match your environment. The path is used by the target JVM to write the file, so running `jcmd` on the host outside a container does not automatically place the dump on the host filesystem. For containers, run `jcmd` inside the same container/namespace or copy the dump file out using container management tools after creation.

Use a new filename for each dump to avoid file-already-exists errors. Some versions support `-overwrite`/`-overwrite=true`; check with `jcmd <PID> help Thread.dump_to_file` and only use it when you intend to replace an old file.

### Step 3: generate a plain-text dump

When `-format` is omitted, the default format is usually **plain text** according to the `help` of JVMs that support the command:

```bash
jcmd 12345 Thread.dump_to_file /tmp/virtual-threads-12345.txt
```

Oracle's Virtual Threads guide for Java 21 also illustrates `-format=text`. Documentation for newer JDKs may describe the plain format name as `plain`. To avoid depending on version-specific naming, prefer **`-format=json`** when processing with tools, or use the default text format after checking `help` on the target JVM.

### Step 4: inspect the result

A JSON thread dump typically has a root `threadDump` object, process/timestamp information, and thread containers data. Entries are grouped by thread container; the structure and fields may change across JDK versions. For the example above, search for the string `demo-vt-` and stacks containing `CountDownLatch.await`.

```bash
# Linux/macOS: filter only to locate entries in the JSON;
# do not use grep as a structured JSON parser.
grep -n "demo-vt-" /tmp/virtual-threads-12345.json
```

Example filtering with PowerShell on Windows:

```powershell
Select-String -Path C:\temp\virtual-threads-12345.json -Pattern 'demo-vt-'
```

When you need to count or group threads by name or stack, use a **JSON parser** that matches the structure of the actual dump rather than assuming “one thread per JSON line”. Reading the dump file directly in an editor is also helpful when diagnosing a moderate number of threads.

## 6. How to read a virtual thread dump to answer practical questions

Use a single dump as a **point-in-time snapshot**. A dump can show which stack a virtual thread is on and what operation it is waiting on; it does not by itself tell you how long it has been waiting, the root cause, or what happened earlier.

| Observation | Possible meaning | What to verify next |
| --- | --- | --- |
| Many `demo-vt-*` waiting on `CountDownLatch.await` | Matches the experiment intentionally holding threads | Do they disappear after `release.countDown()`? |
| Many virtual threads waiting on a connection pool or semaphore | Bottleneck on access to a bounded resource | Pool max/active/pending, timeouts, resource hold time |
| Many stacks waiting on network I/O | Downstream service responding slowly or many in-flight calls | Timeouts, latency, error rate of the external service |
| Many stacks repeated at a lock/synchronization point | Possible contention or suboptimal lock design | Lock ownership path, lock hold time, state across multiple dumps |
| Low platform thread count while the dump has many virtual threads | `ThreadMXBean` is measuring a different set | Count and measure tasks in the application, observe arrival/completion rates |

Practical workflow:

1. Record the specific symptom: slow requests, timeouts, high resource usage, or lack of progress.
2. Confirm the PID, JDK version, capture timestamp, and sensitive-data policy for stack traces.
3. Take a dump with `Thread.dump_to_file`; if the issue persists, take several dumps spaced reasonably apart to compare whether stacks are making progress.
4. Group by thread name, prominent stack paths, and waiting state; correlate with I/O, connection pool, queue, and log metrics.
5. Identify which resource is bottlenecked, and check concurrency limits, timeouts, resource closing, and input rate before changing configuration.

**Interpreting waiting states accurately:** a virtual thread waiting on I/O does not necessarily consume a carrier for the entire wait duration. Waiting can be normal behavior in an I/O-heavy workload. The real problem is continuously growing queues, worsening latency, unreleased resources, or work no longer completing.

## 7. Comparison with Thread.print, jstack, and in-code APIs

`Thread.print` and `jstack` are traditionally useful for investigating platform threads, native frames, and JVM/monitor-related issues. However, especially in JDK 21, do not expect a **traditional thread dump** from them to list all unmounted virtual threads. The Oracle-documented way to inspect virtual threads is `jcmd Thread.dump_to_file`.

| Tool | When to use | Limitations to remember |
| --- | --- | --- |
| `ThreadMXBean` | Monitoring platform thread count, platform thread stacks/synchronization, and JMX metrics | Excludes virtual threads |
| `Thread.getAllStackTraces()` | Platform thread stacks via Java API | Does not cover all virtual threads |
| `jcmd <PID> Thread.print` | Traditional dump; supplementary platform thread/JVM info | Does not replace a full virtual thread dump; visibility varies by JDK |
| `jcmd <PID> Thread.dump_to_file` | Snapshot of platform + virtual threads, text/JSON output | Lacks full traditional metadata such as object addresses, native/JNI/heap; lock info support varies by version |
| JDK Flight Recorder (JFR) | Analyzing events, durations, latency/pinning causes | Requires configuring a recording and the relevant events |
| Application-emitted metrics | Counting tasks, latency, timeouts, queues, resource usage | Instrumentation must be placed on the right business flows and resources |

Do not conclude that `ThreadMXBean.findDeadlockedThreads() == null` proves **there are no deadlocks** in an application using virtual threads: it is only designed for platform thread deadlock cycles. To identify multi-lock/resource interaction issues, analyze stacks, state changes across multiple points in time, and business control flow.

## 8. Long-term observability: JFR, application metrics, and scheduler (JDK 24+)

Thread dumps help answer **“what is happening right now?”**; JFR and metrics help answer **“how long has it been happening, how often, and what is the trend?”**.

On Java 21, JFR provides events such as:

- `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd`: virtual thread lifecycle; **disabled by default** to avoid overhead when thread counts are very high.
- `jdk.VirtualThreadPinned`: event when a virtual thread is pinned longer than the configured threshold; according to the Java 21 guide, this event is enabled by default with a 20 ms threshold.
- `jdk.VirtualThreadSubmitFailed`: failure to submit/unpark a virtual thread, possibly due to resource issues.

You can configure a recording as needed, then read the relevant events from `recording.jfr`:

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

`recording.jfr` must be a file already written by a JFR recording; the command above **only reads**, it does not start a recording. Specific settings/events should be verified for the JDK version in use.

Starting in **JDK 24**, the JDK adds `jdk.management.VirtualThreadSchedulerMXBean`, which provides scheduler metrics such as target parallelism, the number of carrier platform threads in the scheduler, and the number of virtual threads queued waiting to be scheduled (values may be estimates). This is a **different MXBean** from `java.lang.management.ThreadMXBean`, and **is not available on JDK 21**.

Example of obtaining the bean on **JDK 24+** (illustrative snippet, requires an environment with the `jdk.management` module):

```java
import java.lang.management.ManagementFactory;
import jdk.management.VirtualThreadSchedulerMXBean;

VirtualThreadSchedulerMXBean scheduler =
        ManagementFactory.getPlatformMXBean(VirtualThreadSchedulerMXBean.class);

if (scheduler != null) {
    System.out.println("parallelism=" + scheduler.getParallelism());
    System.out.println("carrierPoolSize=" + scheduler.getPoolSize());
    System.out.println("queuedVirtualThreads~=" + scheduler.getQueuedVirtualThreadCount());
}
```

The above is a **snippet**, not a complete Java class; `jdk.management.VirtualThreadSchedulerMXBean` is only available starting in JDK 24. `getQueuedVirtualThreadCount()` reflects virtual threads waiting on the **scheduler**, which is not the same as the number of tasks waiting on a connection pool, semaphore, or I/O result. Do not use it as the total number of virtual threads existing in the process.

At the application layer, you should have clear measurements:

- Number of virtual-thread tasks started/completed/cancelled, in-flight task count, and wait times.
- Error rates, external I/O timeouts, and active/idle/waiting counts of connection pools.
- Queue/admission backlog and number of requests rejected under overload.
- CPU, memory, GC, and separate platform-thread/carrier metrics.

When diagnosing issues, use JFR or appropriate profiling tools alongside dumps/metrics instead of looking only at `getThreadCount()`.

## 9. Common mistakes and how to self-check

**Not seeing a virtual thread in `ThreadMXBean` → concluding the thread is dead.** Check `Thread.isVirtual()` and `Thread.isAlive()` when you have a reference to the thread; use `jcmd Thread.dump_to_file` to inspect its stack. `ThreadMXBean` omits virtual threads by design.

**Dump does not contain `demo-vt-*` names.** Check that the process is still alive, the PID is correct, the dump was taken before the threads finished, and the right Java 21+ program is running. Retry while the virtual threads are waiting on `CountDownLatch`.

**Using `jcmd` in the wrong environment/container.** Check attach permissions, PID namespace, the file path from the target JVM's perspective, write permissions, and the account running the tool. Check `jcmd <PID> help Thread.dump_to_file`. If the process disallows attach, diagnose using the active JVM/container management mechanism.

**Assuming the dump file contains all traditional metadata.** The dump format optimized for virtual threads does not provide every piece of information such as object addresses, JNI, or heap; lock information varies by JDK. Combine with `Thread.print`/JFR/metrics when those views are needed.

**Counting occurrences of the word “virtual” in the file as the exact thread count.** A stack or metadata block may contain the keyword multiple times. Parse thread entries according to the actual format or measure in-flight counts in the application.

**Taking one dump and concluding there is a deadlock/leak.** A single snapshot does not show trends. Compare multiple dumps and pool/queue data; identify which resource is not being released and which tasks are not making progress.

**Enabling all JFR start/end events under very heavy load without consideration.** Virtual thread lifecycle events can occur at very high frequency. Configure events, recording duration, and recording size according to your investigation goals.

## 10. Verification exercises

1. Run `VirtualThreadDumpDemo.java` and verify the two guaranteed lines: `virtualThreadsStarted=12` and `sampleVirtualThreadListedByMXBean=false`.
2. Use the PID printed by the program to run `jcmd <PID> help Thread.dump_to_file`, then export a JSON dump.
3. Find `demo-vt-0`, the stack waiting on `CountDownLatch.await`, and confirm it is a virtual thread in the dump.
4. Wait for the example to finish, run it again, and take a dump after changing `WORKERS` from 12 to 100. Compare the number of virtual threads found with `getThreadCount()`; do not expect the platform-thread count to grow linearly.
5. Explain why `ThreadMXBean` is still useful for monitoring platform threads, and which tools to use to diagnose virtual threads along with I/O bottlenecks.

## Summary

- `ThreadMXBean` only manages **platform threads**; `getThreadCount()`, `getAllThreadIds()`, and `dumpAllThreads()` do not provide the total count or full stacks of virtual threads.
- `jcmd <PID> Thread.dump_to_file -format=json <absolute-file>` is the standard way since JDK 21 to generate a thread dump containing both **platform and virtual threads**.
- A dump is a **snapshot**. Analyze stacks with timestamps and combine with metrics/JFR to draw conclusions about contention, I/O, deadlocks, or overload.
- `jdk.management.VirtualThreadSchedulerMXBean` since JDK 24 has scheduler scope; it is **not** a full replacement for `ThreadMXBean` and does not measure all live virtual threads.

## Official documentation

1. [Java SE 21 — ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform thread scope limits, `getThreadInfo`, `getAllThreadIds`, and deadlock detection.
2. [Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): thread dumps via `jcmd`, carriers, debugging, and JFR.
3. [Java SE 22 — jcmd command](https://docs.oracle.com/en/java/javase/22/docs/specs/man/jcmd.html): how to use diagnostic commands and `Thread.dump_to_file` parameters.
4. [Java SE 24 — VirtualThreadSchedulerMXBean API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html): additional scheduler metrics introduced in JDK 24.
