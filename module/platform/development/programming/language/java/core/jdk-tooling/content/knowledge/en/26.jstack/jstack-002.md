# Thread Dumps and JVM Diagnostics with jstack

## 1. What Is a Thread Dump?

A **thread dump** is a snapshot of the state of all threads in a JVM process at a specific point in time. It typically includes each thread's name, state, stack trace, and information about monitors or locks that the thread is holding or waiting to acquire.

Thread dumps help investigate:

- Applications that are slow to respond or hung.
- Threads that are `BLOCKED` waiting for a monitor.
- Deadlocks between two or more threads.
- A thread consuming high CPU or running in a tight loop.
- Exhausted thread pools, growing queues, or requests that never complete.
- Bottlenecks when accessing databases, networks, files, or external services.
- Synchronization issues in applications using platform threads or virtual threads.

A thread dump only reflects a single point in time. A single snapshot may not be enough to determine the root cause; you should compare multiple snapshots alongside CPU usage, logs, metrics, and real-time data.

## 2. What Is jstack and When Should You Use It?

`jstack` is a command-line tool in the JDK that attaches to a running JVM and prints stack traces of Java threads and certain internal VM threads. The tool also performs deadlock detection.

In JDK 24, the syntax displayed by `jstack -h` is:

```text
Usage:
    jstack [-l][-e] <pid>

Options:
    -l  long listing. Prints additional information about locks
    -e  extended listing. Prints additional information about threads
    -? -h --help -help to print this help message
```

`jstack` is useful when you need to quickly capture a thread dump from a process with a known PID, especially when the application is hung or has no interactive console.

However, Oracle marks `jstack` as an experimental/unsupported tool and recommends using `jcmd` for modern JVM diagnostics because it offers more functionality and lower overhead. You should know how to use `jstack` since it still appears in many operational runbooks, but prefer `jcmd Thread.print` when supported by the running JDK.

Reference: [Oracle Java SE 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html).

## 3. Preparation Before Capturing a Thread Dump

Before attaching to the JVM, identify the exact process and environment:

1. Identify the hostname or container running the application.
2. Identify the current PID; do not use an old PID from a previous restart.
3. Identify the running JDK/JVM vendor and version.
4. Use an account with permission to access the process; on many operating systems, the diagnostic account needs the same effective user/group as the account running the JVM.
5. Choose a directory to store the dump that has sufficient disk space and write permissions.
6. Record the timestamp, symptoms, and affected requests or jobs.

You can use `jps -l` to find JVMs in the same environment:

```bash
jps -l
```

If the process is running inside Docker or Kubernetes, run the tool inside the container/pod or identify the PID according to the corresponding process namespace. The PID seen from the host may differ from the PID inside the container.

If multiple JDKs are installed, use the `jstack` or `jcmd` tool from the JDK matching the running runtime. Check the tool versions:

```bash
jstack -h
jcmd -h
java -version
```

Do not treat the absence of a process in `jps` output as proof that the JVM has stopped; verify using the process manager or OS tools if needed.

## 4. Capturing a Thread Dump with jstack

Basic syntax:

```bash
jstack <PID>
```

Example:

```bash
jstack 18420
```

This command attaches to the JVM with PID 18420 and prints the thread dump to the terminal's standard output.

To include additional lock information:

```bash
jstack -l 18420
```

The `-l` option instructs the tool to look for ownable synchronizers and print additional information about locks in `java.util.concurrent.locks`. Without `-l`, the thread dump still includes monitor information, but lacks full ownable synchronizer details.

To view extended thread information:

```bash
jstack -e 18420
```

On JDK 24, `-e` can include fields such as CPU time, elapsed time, allocated memory, and the number of defined classes, depending on JVM capabilities.

You can combine both options:

```bash
jstack -l -e 18420
```

Always run `jstack -h` on the exact JDK you are using to confirm supported options. Do not copy options from older JDK documentation to a newer JDK without verifying them first.

## 5. Saving a Thread Dump to a File

By default, `jstack` prints output to stdout. You can redirect it to a file for comparison and analysis:

Linux/macOS:

```bash
jstack -l <PID> > thread-dump-01.txt 2>&1
```

Windows PowerShell:

```powershell
jstack -l <PID> | Out-File -Encoding utf8 thread-dump-01.txt
```

Name files by service, timestamp, and sequence number for easy correlation, for example:

```text
orders-api_2026-11-10_191500_dump-01.txt
orders-api_2026-11-10_191510_dump-02.txt
orders-api_2026-11-10_191520_dump-03.txt
```

Capture at least three snapshots during an investigation when symptoms are recurring or changing over time. An interval of 5–10 seconds is a practical starting point; adjust based on how fast the incident evolves and the attach overhead. Avoid running the command continuously at high frequency on an already overloaded system.

A thread dump may contain thread names, class names, package names, paths, and internal architectural details. Store and share it according to your organization's security policies.

## 6. Using jcmd Thread.print as the Preferred Option

`jcmd` is the recommended multi-purpose diagnostic tool for modern JVMs. First, list the processes:

```bash
jcmd -l
```

Capture a thread dump:

```bash
jcmd <PID> Thread.print
```

Print additional lock information:

```bash
jcmd <PID> Thread.print -l
```

Print extended thread information:

```bash
jcmd <PID> Thread.print -e
```

Before using a diagnostic command, you can query the target JVM for supported syntax:

```bash
jcmd <PID> help Thread.print
```

In JDK 24, `Thread.print` has an impact rating of Medium, and its cost depends on the number of threads. For applications with a very large number of threads, monitor execution time and impact during capture.

You can save a thread dump to a file using `Thread.dump_to_file`:

```bash
jcmd <PID> Thread.dump_to_file -format=plain thread-dump.txt
```

Or use JSON for automated analysis tools:

```bash
jcmd <PID> Thread.dump_to_file -format=json thread-dump.json
```

The `-overwrite` option allows overwriting an existing file. Only use it when overwriting is explicitly intended; otherwise, choose a new filename to preserve evidence from previous captures.

## 7. Reading the Structure of a Thread Dump

A thread dump typically has a header describing the timestamp and JVM, followed by entries for each thread.

Abbreviated example:

```text
2026-11-10 19:15:00
Full thread dump OpenJDK 64-Bit Server VM (24.0.2+12 mixed mode):

"blocked-worker" #18 prio=5 os_prio=0 tid=0x000001 nid=0x42 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.OrderService.reserve(OrderService.java:84)
    at com.example.OrderController.submit(OrderController.java:51)
    - waiting to lock <0x00000001> (a java.lang.Object)

"lock-owner" #17 prio=5 os_prio=0 tid=0x000002 nid=0x41 waiting on condition
   java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.CountDownLatch.await(CountDownLatch.java:230)
    at com.example.OrderService.holdReservation(OrderService.java:112)
```

This is an illustrative example of the structure, not a fixed output format for a specific JVM.

Common fields:

| Field | Meaning |
|---|---|
| Quoted name | Thread name assigned by the application or JVM |
| `#18` | Java-level thread ID in the dump |
| `daemon` | Daemon thread; does not keep the JVM alive on its own once all non-daemon threads finish |
| `prio` | Thread priority |
| `tid` | Address of the thread structure in the JVM |
| `nid` | Native thread ID assigned by the operating system |
| `java.lang.Thread.State` | Java thread state |
| `at ...` | A frame in the stack trace, typically including class, method, and file/line number |
| `- locked <...>` | Object monitor currently held by the thread |
| `- waiting to lock <...>` | Monitor the thread is waiting to acquire to enter a synchronized block/method |

`tid` and `nid` are diagnostic fields. Do not confuse `nid` with the Java thread ID; on some operating systems, you can use the native thread ID to correlate with OS-level tools.

Stack traces are read from top to bottom: the top frame is usually the thread's current or waiting location, and subsequent frames show the call path that led there. If classes are compiled with line numbers (the default), line numbers help locate the exact source code.

## 8. Understanding Thread States

States in `java.lang.Thread.State`:

| State | Meaning | Common Indicators |
|---|---|---|
| `NEW` | Thread has been created but not yet started | No execution stack |
| `RUNNABLE` | Thread is executing in the JVM or ready to run | Stack may be in Java or native code |
| `BLOCKED` | Thread is waiting to acquire an intrinsic monitor | `waiting to lock`, `on object monitor` |
| `WAITING` | Thread is waiting indefinitely for an action from another thread | `Object.wait`, `LockSupport.park`, `CountDownLatch.await`, `join` without timeout |
| `TIMED_WAITING` | Thread is waiting for a specified period | `Thread.sleep`, `wait(timeout)`, `parkNanos`, `join(timeout)` |
| `TERMINATED` | Thread has finished execution | No longer an active thread |

Common misconceptions:

- `RUNNABLE` does not necessarily mean the thread is actively consuming CPU. It may be in a native call or waiting on I/O at the OS level.
- `BLOCKED` is the state of waiting for an intrinsic monitor, typically when entering a `synchronized` block or method.
- `WAITING` and `TIMED_WAITING` are not automatically errors. Worker threads waiting on a queue or background threads waiting for a signal are normal behavior.
- `WAITING` caused by `LockSupport.park` is often associated with `ReentrantLock`, `Condition`, `ForkJoinPool`, or other concurrency utilities.
- You cannot conclude a deadlock solely from the number of `BLOCKED` threads; you must inspect which thread holds each lock, which thread is waiting, and the dependency chain.

When investigating high CPU, look for `RUNNABLE` threads with the same stack trace across multiple snapshots and correlate them with process CPU usage. When investigating latency, look for threads repeatedly stuck on the same lock, I/O call, queue wait, or database driver.

## 9. Analyzing Monitors and Locks

A crucial part of a thread dump is the relationship between threads and locks.

Common lines:

```text
- locked <0x00000001> (a java.lang.Object)
- waiting to lock <0x00000002> (a java.lang.Object)
- waiting on <0x00000003> (a java.lang.Object)
- parking to wait for <0x00000004> (a java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject)
```

How to read them:

- `locked`: the thread currently owns this monitor.
- `waiting to lock`: the thread cannot enter a synchronized block/method because another thread holds the monitor.
- `waiting on`: the thread is waiting on a monitor, typically via `Object.wait()`. When calling `wait`, the thread releases the monitor and only resumes after being notified/unparked by the corresponding mechanism and reacquiring the lock.
- `parking to wait for`: the thread is parked waiting for a synchronizer or signal.

If multiple threads are waiting on the same lock:

1. Find the `waiting to lock` or `parking` lines.
2. Find the thread that owns the lock or synchronizer.
3. Inspect the lock owner's stack trace to see what work it is performing.
4. Check whether the lock is held for too long or if I/O is being performed inside a synchronized region.
5. Compare multiple dumps to determine whether the contention is persistent or just brief.

For `ReentrantLock` or locks in `java.util.concurrent`, use `jstack -l` or `jcmd Thread.print -l` to get additional ownable synchronizer information.

## 10. Detecting Deadlocks

A deadlock occurs when a group of threads wait on each other in a circular dependency, preventing any thread in the cycle from making progress.

Logical example:

- Thread A holds Lock 1 and waits for Lock 2.
- Thread B holds Lock 2 and waits for Lock 1.
- A cannot proceed until B releases Lock 2.
- B cannot proceed until A releases Lock 1.

A deadlock report section might look like this:

```text
Found one Java-level deadlock:
=============================
"worker-A":
  waiting to lock monitor <0x00000001>,
  which is held by "worker-B"
"worker-B":
  waiting to lock monitor <0x00000002>,
  which is held by "worker-A"

Found 1 deadlock.
```

This is an illustrative example. Actual output will contain specific monitor IDs, object types, and stack traces.

When you see a deadlock report:

1. Identify all threads in the cycle.
2. Match the lock each thread holds with the lock it is waiting for.
3. Locate the source code positions in the stack traces.
4. Check the lock acquisition order across different code paths.
5. Fix the issue by enforcing a consistent lock acquisition order, shrinking critical sections, or using an appropriate concurrency design.
6. Re-run concurrency tests and verify with a new thread dump.

The JVM can detect many Java-level deadlocks involving monitors and recognized synchronizers. The absence of a deadlock report does not prove the system is free of liveness issues: a thread can still wait forever on an unreleased latch, an incomplete future, an undelivered message, or a hung I/O operation.

## 11. Diagnosing Hung or Slow-Responding Applications

A useful workflow is to capture multiple dumps instead of just one:

```bash
jcmd <PID> Thread.print -l > dump-01.txt
jcmd <PID> Thread.print -l > dump-02.txt
jcmd <PID> Thread.print -l > dump-03.txt
```

Run the commands at short intervals, such as 5–10 seconds apart, then compare the same threads across each file.

Common patterns:

| Pattern Across Multiple Dumps | Likely Area to Investigate |
|---|---|
| A `RUNNABLE` thread keeps the same stack and CPU rises | Infinite/tight loop, heavy computation, hot retry, or processing excessive data |
| Many `BLOCKED` threads waiting on the same monitor | Lock contention or a critical section held too long |
| Many threads waiting on the same JDBC/socket read | Slow database or external service, pool exhaustion, or network issue |
| Many workers `WAITING` on a queue | Empty queue may be normal; if requests are piling up, check producer/consumer and worker pool |
| Threads `TIMED_WAITING` in sleep | Possibly polling, backoff, or scheduled execution; check frequency and wait duration |
| Main thread waiting on `Future.get()` | Find the corresponding task and the thread executing it |
| All request threads waiting on a connection pool | Check pool size, connection leaks, long transactions, and query duration |

For a `RUNNABLE` thread with an unchanged stack, Oracle recommends capturing additional dumps to determine whether the thread is looping continuously. If it remains unclear, you can use `jhsdb jstack --mixed` to inspect native frames where appropriate.

Do not attribute every `RUNNABLE` state to a CPU spike. Combine thread dumps with process CPU, native stacks, logs, and metrics to confirm.

## 12. Capturing a Thread Dump Without Console Access

If the application runs in the background or console output is redirected, you can use `jstack` or `jcmd`.

On Linux, HotSpot supports sending `SIGQUIT` to ask the JVM to print a thread dump to the process's standard output:

```bash
kill -QUIT <PID>
```

On Windows, in the application's console, you can press `Ctrl+Break` to ask HotSpot to print a thread dump.

Sending this signal does not terminate the application. However, you need to know where the service's stdout/stderr is routed to find the log file containing the dump. Never use `kill -9` or `SIGKILL` to capture a thread dump; that signal terminates the process immediately without giving the JVM a chance to print diagnostic data.

If the service is managed by systemd or Windows Service, identify the service's log destination before sending the signal. For containerized applications, check logs via the container runtime or orchestrator.

## 13. Thread Dumps with Virtual Threads on Java 21+

Starting in Java 21, virtual threads are managed by the JVM scheduler rather than being permanently bound to a single OS thread for their entire lifetime. A JVM can have a very large number of virtual threads.

This affects how thread dumps are read:

- Platform threads correspond to OS threads and typically appear in traditional dumps.
- Virtual threads can unmount from their carrier thread when waiting on blocking I/O; the carrier thread can then run another virtual thread.
- Traditional dumps and virtual-thread-oriented dumps may surface different aspects of execution.
- Do not infer the concurrency level of an application using virtual threads solely from the number of platform threads.

In JDK 24, you can generate a virtual thread dump with:

```bash
jcmd <PID> Thread.dump_to_file -format=plain virtual-threads.txt
jcmd <PID> Thread.dump_to_file -format=json virtual-threads.json
```

According to Java SE 24 documentation, this dump lists virtual threads blocked in network I/O and virtual threads created via `ExecutorService`. It does not include object addresses, locks, JNI statistics, heap statistics, and certain other details found in traditional thread dumps. Therefore, consult the documentation for your exact JDK version instead of assuming one dump format covers all virtual threads.

You can also inspect the scheduler and I/O pollers:

```bash
jcmd <PID> Thread.vthread_scheduler
jcmd <PID> Thread.vthread_pollers
```

To investigate virtual threads pinned to carrier threads or prolonged concurrency issues, JDK Flight Recorder provides events such as:

- `jdk.VirtualThreadStart`
- `jdk.VirtualThreadEnd`
- `jdk.VirtualThreadPinned`
- `jdk.VirtualThreadSubmitFailed`

Available events and default configurations depend on the JDK version. Use JFR/JDK Mission Control to analyze event sequences over time; a thread dump is only a snapshot.

Reference: [Oracle Java SE 24 — Virtual Threads](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html).

## 14. Using jhsdb When You Need Native Stacks or Core Dumps

If a Java thread dump does not explain a thread's state, you may need to inspect native frames or analyze a core dump.

For a running process, `jhsdb jstack` can produce a mixed stack containing both Java frames and native C/C++ frames:

```bash
jhsdb jstack --mixed --pid <PID>
```

For a core file:

```bash
jhsdb jstack --exe <path-to-java> --core <core-file>
```

Mixed stacks help reveal when a thread is inside JNI, a native library, or an internal HotSpot function. For example, a native stack might show a thread waiting on a condition variable or attempting to enter a monitor.

`jhsdb` uses the Serviceability Agent and attaches differently from `jcmd`. It is a deep diagnostic tool; prefer core dumps or staging environments whenever possible, and carefully review OS/JDK documentation before attaching to production.

Do not use `jhsdb` as a routine dump command in place of `jcmd Thread.print`.

## 15. Practical Example: Creating Threads in Multiple States

The Java 17+ example below creates four threads to observe different states:

- `lock-owner`: holds a monitor and waits for a signal, in the `WAITING` state.
- `blocked-worker`: waits to enter `lock-owner`'s monitor, in the `BLOCKED` state.
- `waiting-worker`: waits on an unreleased latch, in the `WAITING` state.
- `timed-worker`: sleeps for a duration, in the `TIMED_WAITING` state.

Create `ThreadDumpDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadDumpDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ownerHasLock = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                ownerHasLock.countDown();
                await(releaseOwner);
            }
        }, "lock-owner");

        Thread blocked = new Thread(() -> {
            try {
                ownerHasLock.await();
                synchronized (LOCK) {
                    // Runs after lock-owner releases LOCK.
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "blocked-worker");

        Thread waiting = new Thread(
            () -> await(neverReleased), "waiting-worker");

        Thread timed = new Thread(
            () -> sleep(120_000), "timed-worker");

        owner.start();
        ownerHasLock.await();
        blocked.start();
        waiting.start();
        timed.start();

        long deadline =
            System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

        while (blocked.getState() != Thread.State.BLOCKED
                && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }

        if (blocked.getState() != Thread.State.BLOCKED) {
            throw new IllegalStateException(
                "blocked-worker did not reach BLOCKED");
        }

        System.out.println("READY");

        try {
            Thread.sleep(120_000);
        } finally {
            releaseOwner.countDown();
            neverReleased.countDown();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
```

Compile and run:

```bash
javac ThreadDumpDemo.java
java ThreadDumpDemo
```

Stdout:

```text
READY
```

The program keeps the threads in the target states for up to about two minutes. Open a second terminal and find the PID:

```bash
jps -l
```

Then capture the dump:

```bash
jstack -l <PID>
```

Or use the recommended command:

```bash
jcmd <PID> Thread.print -l
```

Look for the threads `lock-owner`, `blocked-worker`, `waiting-worker`, and `timed-worker`. Specific stack frames and states are runtime data, so frame positions and ID values will vary between runs.

When the demo period ends, the program releases the latches to unblock the waiting threads and exits normally.

## 16. Common Errors When Running jstack

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `jstack` is not recognized | `PATH` does not include `JDK/bin`, or only a stripped-down runtime is installed | Check `JAVA_HOME`, `PATH`, and `jstack -h` |
| `Unable to open socket file` or attach failure | Wrong PID, JVM has stopped, different user/group, or attach is disabled | Verify the process, account, and JVM options |
| `Not enough permissions` | Current account lacks permission to access the JVM | Run with an authorized service account per policy |
| PID not found in `jps` | JVM is in another container/namespace or `jps` cannot list it | Find the PID using OS tools in the proper environment |
| Dump lacks required lock details | Ran default dump without lock flag | Use `jstack -l` or `jcmd Thread.print -l` |
| Output is too large | Application has many threads or deep stacks | Save to a file, filter by thread name, and consider separate virtual thread dumps |
| Windows reports missing `dbgeng.dll` | Missing Debugging Tools for Windows component needed for tool attach | Check platform requirements and install the appropriate component |
| JVM does not respond when attaching | JVM or OS is in a severely abnormal state | Collect logs, consider a core dump and `jhsdb` per diagnostic procedures |

Diagnostic commands and options may vary across vendors or JDK releases. When a command fails, read the exact error message and check `jstack -h` and `jcmd <PID> help` before changing configuration.

## 17. Practical Diagnostic Workflow

When an application hangs or responds slowly:

1. Record the timestamp, affected requests/jobs, CPU, memory, latency, and request rate.
2. Identify the exact host/container and JVM PID.
3. Check the runtime vendor and version.
4. Capture three thread dumps at short intervals using `jcmd <PID> Thread.print -l`.
5. Compare `RUNNABLE`, `BLOCKED`, `WAITING`, and `TIMED_WAITING` threads across snapshots.
6. If a deadlock is reported, trace the chain of threads holding and waiting on locks.
7. If many threads are waiting on the same dependency, check the database, network, connection pool, queues, and timeouts.
8. If `RUNNABLE` threads repeat the same stack, correlate with CPU usage and consider native stacks or JFR.
9. For virtual threads, also use `Thread.dump_to_file`, scheduler diagnostics, and JFR as supported by your JDK.
10. After applying a fix, capture new dumps and run load/concurrency tests to confirm the thread states have improved.

A good thread dump must be paired with the PID, timestamp, JDK version, environment, symptoms, and relevant metrics. Without context, the same thread state can easily be misinterpreted.

## 18. Summary

Thread dumps are an essential diagnostic tool for understanding what the JVM is doing at a given moment. They reveal which threads are running, which are waiting, which stacks repeat, and which locks may be causing bottlenecks.

Key takeaways:

- `jstack <PID>` captures stack traces of threads in a JVM.
- `jstack -l` adds ownable synchronizer and lock information.
- `jstack -e` displays extended thread information on JDKs that support this option.
- Oracle recommends `jcmd <PID> Thread.print` for modern diagnostics.
- `BLOCKED` is typically related to monitors; `WAITING` and `TIMED_WAITING` can be normal states.
- Use multiple dumps to distinguish transient states from persistent issues.
- Deadlocks must be analyzed through the dependency cycle between threads and locks.
- For virtual threads, check the capabilities of your specific JDK release and supplement with JFR when needed.
- For native stacks or core dumps, use `jhsdb jstack` within an appropriate diagnostic workflow.
- Protect thread dumps as internal operational data and do not store them in public locations.

**Official References:**

- [Oracle Java SE 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle Java SE 24 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- [Oracle Java SE 24 — Virtual Threads](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html)
- [Oracle Java SE 21 — The jstack Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html)
