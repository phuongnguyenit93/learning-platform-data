# How to Read a Thread Dump in Java

A thread dump is a snapshot of the stack traces and states of all threads in a JVM process at a specific point in time. It helps investigate hung applications, slow responses, deadlocks, lock contention, exhausted thread pools, or threads waiting on I/O.

In JDK 17, you can capture a thread dump using `jstack`, `jcmd`, or the JVM's Control+Break mechanism. This article focuses on reading each section of a dump: thread headers, states, stack frames, monitors, ownable synchronizers, and the relationship between waiting threads and lock-holding threads. The hands-on section creates a reproducible deadlock so you can compare it against the output.

> **Tooling recommendation:** Oracle marks `jstack` as an experimental tool. For new diagnostics, Oracle recommends `jcmd`; the corresponding command is `jcmd PID Thread.print -l`.

## 1. What Is a Thread Dump?

A thread dump is a record of the state of the threads visible to the JVM at the moment it is requested. It typically contains:

- The thread name and identifying metadata.
- Whether the thread is daemon or non-daemon.
- The current Java thread state, such as `RUNNABLE`, `BLOCKED`, or `WAITING`.
- The stack trace from the current frame back through earlier calls.
- Monitor locks that the thread is holding or waiting to acquire.
- Information about locks from `java.util.concurrent`, if lock listing is enabled.
- A deadlock diagnostic section if the JVM detects a lock cycle.

A thread dump is a snapshot, not a historical log. It shows where each thread is at the moment of capture, but a single snapshot is often insufficient to determine the root cause of an incident. To identify threads that are stuck over time, compare multiple dumps taken a few seconds apart.

Generating a thread dump does not terminate the application. The JVM continues running after printing the thread information.

## 2. Finding the JVM PID

First, identify the exact Java process to investigate:

~~~powershell
jps -lv
~~~

Example output:

~~~text
8120 com.example.ThreadDumpDeadlockDemo
9204 org.apache.catalina.startup.Bootstrap
10440 jdk.jcmd/sun.tools.jps.Jps
~~~

In this example, the application's PID is `8120`. You can also use `jcmd -l` to list the JVMs recognized by the tool:

~~~powershell
jcmd -l
~~~

Notes:

- Run the command on the same host as the target JVM.
- Use an account with appropriate attach permissions matching the account running the JVM.
- For Docker/containers, check the PID inside the target container or PID namespace.
- If the application runs as a service, find the PID of the JVM process itself, not the PID of a wrapper or shell script.

## 3. Capturing a Thread Dump with jstack

Basic command:

~~~powershell
jstack 8120
~~~

To include additional lock information:

~~~powershell
jstack -l 8120
~~~

The `-l` option instructs the tool to look for and print additional information about ownable synchronizers, including locks from `java.util.concurrent.locks`. Without `-l`, the output primarily shows Java monitor information.

Save the output to a file for analysis:

~~~powershell
jstack -l 8120 > thread-dump.txt
~~~

On Linux/macOS, you can use the corresponding shell command:

~~~bash
jstack -l 8120 > thread-dump.txt
~~~

If `jstack` is not on your PATH, invoke it directly from the JDK's `bin` directory. A minimal JRE/runtime may not include JDK diagnostic tools.

## 4. Using jcmd to Capture a Thread Dump

For JDK 17, this is Oracle's recommended approach for new JVM diagnostics:

~~~powershell
jcmd 8120 Thread.print
~~~

To also print lock information:

~~~powershell
jcmd 8120 Thread.print -l
~~~

You can request extended thread information if the JVM supports it:

~~~powershell
jcmd 8120 Thread.print -e
~~~

Check the options supported by the target process:

~~~powershell
jcmd 8120 help Thread.print
~~~

Save the output:

~~~powershell
jcmd 8120 Thread.print -l > thread-dump.txt
~~~

`Thread.print -l` serves the same role as `jstack -l` for reading lock details. The `-e` option on `Thread.print` requests extended thread information; check the help output of your exact JVM before using it.

## 5. Capturing a Dump via Control+Break or OS Signals

In addition to attach tools, the HotSpot JVM supports the Control+Break mechanism:

| Platform | How to request a dump | Where output is written |
|---|---|---|
| Linux | `kill -QUIT PID` or `kill -3 PID` | Standard output of the Java process |
| Linux terminal | Ctrl + backslash in the application console | Standard output of the process |
| Windows console | Ctrl + Break in the window running Java | Console or redirected log |
| Any platform with valid attach | `jcmd PID Thread.print -l` | Terminal running the command |

Example on Linux:

~~~bash
kill -QUIT 8120
~~~

The `SIGQUIT` signal asks the JVM to print a thread dump; it is not equivalent to `kill -9` and does not terminate the process. `kill -3 PID` sends the same signal on Linux. Check your application logs if standard output is redirected to a file or logging system.

On Windows, use Ctrl+Break when an appropriate console is attached. Ctrl+C typically sends an interrupt signal and can terminate the application; do not confuse Ctrl+C with Ctrl+Break.

If the JVM was started with `-Xrs`, the JVM's signal/console handling is reduced or disabled; thread dumps via `SIGQUIT` on Linux and Ctrl+Break on Windows may not be available. In that case, use `jcmd` if attach is permitted.

## 6. General Structure of a Thread Dump

A dump typically has a header banner, multiple thread entries, and optionally a deadlock section at the end.

Abbreviated example:

~~~text
2026-11-10 10:15:30
Full thread dump Java HotSpot(TM) 64-Bit Server VM (17.0.x mixed mode):

"main" #1 prio=5 os_prio=0 tid=0x000001 nid=0x100 waiting on condition
   java.lang.Thread.State: WAITING
        at java.lang.Object.wait(Native Method)
        at java.lang.Thread.join(Thread.java:...)
        at com.example.Main.main(Main.java:20)

"worker-1" #31 daemon prio=5 os_prio=0 tid=0x000002 nid=0x201 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Service.update(Service.java:42)
        - waiting to lock <0x00000001> (a java.lang.Object)
        - locked <0x00000002> (a java.lang.Object)

"worker-2" #32 daemon prio=5 os_prio=0 tid=0x000003 nid=0x202 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Service.refresh(Service.java:58)
        - waiting to lock <0x00000002> (a java.lang.Object)
        - locked <0x00000001> (a java.lang.Object)
~~~

This example illustrates the structure, not a fixed output format across all JVMs. Field names, identifiers, line numbers, and extensions can vary by JDK, operating system, and VM type.

Java threads are usually printed first, followed by internal VM threads. Each entry typically includes a header, Java thread state, stack frames, and lock information if applicable.

## 7. Reading the Thread Header

A HotSpot thread header may look like:

~~~text
"worker-1" #31 daemon prio=5 os_prio=0 tid=0x000002 nid=0x201 waiting for monitor entry
~~~

Meaning of common fields:

| Field | Meaning |
|---|---|
| `"worker-1"` | Thread name assigned by the application or runtime |
| `#31` | Java thread identifier number in the output |
| `daemon` | Daemon thread; the JVM does not wait solely for daemon threads to keep the process alive |
| `prio=5` | Java thread priority |
| `os_prio=0` | Operating-system-mapped priority, if applicable |
| `tid=...` | VM-side thread identifier/structure address |
| `nid=...` | Native thread ID assigned by the OS |
| `waiting for monitor entry` | Status hint indicating the thread is waiting to acquire a monitor |

Do not treat `tid`, `nid`, or address-like values as stable IDs across multiple dumps or restarts. They are useful for correlating within the same snapshot and alongside OS tools.

Thread names are often a very useful clue. For example, `http-nio-8080-exec-12` may be an HTTP request-handling worker; `pool-3-thread-2` may belong to an executor; `scheduler-1` may be a scheduling thread. Actual names depend on the framework and application naming conventions.

## 8. Reading Java Thread States

The state line typically looks like:

~~~text
java.lang.Thread.State: BLOCKED (on object monitor)
~~~

Java thread states:

| State | Meaning | Common indicators |
|---|---|---|
| `NEW` | Thread has been created but not started | Usually does not appear in a dump of running threads |
| `RUNNABLE` | Thread is executing or ready to be scheduled CPU time by the OS | Stack may be in application code or a native call |
| `BLOCKED` | Waiting to acquire an intrinsic monitor to enter a synchronized block/method | `waiting to lock` |
| `WAITING` | Waiting indefinitely for an action from another thread | `Object.wait()`, `Thread.join()` without timeout, `LockSupport.park()` |
| `TIMED_WAITING` | Waiting for a bounded period | `Thread.sleep()`, `wait(timeout)`, `join(timeout)`, `parkNanos()` |
| `TERMINATED` | Thread has finished execution | Usually no longer a live thread in the snapshot |

### 8.1. RUNNABLE Does Not Always Mean High CPU

`RUNNABLE` is a Java-level state. A thread may be actively executing on a CPU, ready to run, or inside certain native operations. Therefore, a `RUNNABLE` thread alone does not prove continuous CPU consumption.

To detect a high-CPU loop, capture multiple dumps a few seconds apart and compare the stack of the same thread. If the thread remains `RUNNABLE` and repeatedly appears in the same hot code path, that is a strong clue to investigate further with a profiler or Java Flight Recorder.

### 8.2. BLOCKED Refers Only to Monitors

`BLOCKED` means a thread is waiting to enter a monitor guarded by `synchronized`. It is not a generic label for all I/O or all forms of waiting.

A thread waiting on a `ReentrantLock`, `BlockingQueue`, `Future`, or `LockSupport.park()` typically shows `WAITING` or `TIMED_WAITING`, depending on the API and whether a timeout is used.

### 8.3. WAITING and TIMED_WAITING Can Be Normal

An idle thread pool may wait for new tasks. A scheduler thread may sleep between runs. A thread calling `Object.wait()` may be waiting for a legitimate notification.

Do not conclude an application is hung just because you see many `WAITING` threads. Examine the stack frames, thread names, lock relationships, and whether states change across multiple snapshots.

## 9. Reading Stack Frames

A Java stack frame typically looks like:

~~~text
at com.example.OrderService.submit(OrderService.java:84)
~~~

Read from top to bottom:

1. The top frame is closest to where the thread is currently executing or waiting.
2. Subsequent frames trace the call chain back to the caller.
3. Lower frames help trace the execution path that brought the thread to its current location.

Special frame forms:

- `Native Method`: the frame belongs to a native method or has no corresponding Java line number.
- `Unknown Source`: the runtime lacks source/line metadata for the frame.
- `Compiled Code`: some outputs may represent compiled frames in a specific way.
- `...`: documentation or examples may abbreviate stacks; real dumps can be much longer.

Look for the first frame belonging to your application's package. Frames above it may belong to frameworks, libraries, or the JDK; the application frame usually points directly to the method to inspect in source code.

If the stack stops at `SocketDispatcher.read0`, `FileDispatcherImpl.read0`, or a native I/O frame, the thread may be waiting on I/O. Check the endpoint, timeout, connection, and the thread owning that work. A thread waiting on I/O is not enough by itself to conclude the system is deadlocked.

## 10. Reading Monitors and Lock Information

When a thread holds or is waiting on an intrinsic monitor, the dump may show:

~~~text
- waiting to lock <0x00000001> (a java.lang.Object)
- locked <0x00000002> (a java.lang.Object)
~~~

Meaning:

- `waiting to lock`: the thread is trying to acquire the monitor with the given ID but has not obtained it yet.
- `locked`: the thread holds that monitor at the time of capture.
- Matching monitor IDs within a single dump lets you correlate which thread is waiting and which thread holds the lock.

For example, if thread A shows `waiting to lock <0x01>` and thread B shows `locked <0x01>`, thread B is the candidate holding the monitor A needs. Inspect B's stack next to understand why B has not released the lock or whether it is waiting on another monitor.

### 10.1. waiting on vs. waiting to lock

`waiting on <...>` is typically associated with `Object.wait()`. When calling `wait()`, the thread must own the monitor; the call releases the monitor while waiting for a notification or timeout, and must reacquire the monitor before resuming.

`waiting to lock <...>` means waiting to enter the monitor of a `synchronized` block or method.

These two states differ in mechanism and in how you identify the thread to investigate.

### 10.2. Ownable Synchronizers and ReentrantLock

Constructs such as `ReentrantLock` use `java.util.concurrent` synchronizers rather than just intrinsic monitors. Use `jstack -l` or `jcmd PID Thread.print -l` to include ownable synchronizer details.

Illustrative output:

~~~text
- parking to wait for <0x00000003> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
~~~

`parking to wait for` is typically associated with `LockSupport.park()` or AQS-based waiting. To see who holds the lock, check the ownable synchronizer section printed in the long listing and correlate across other threads.

## 11. Identifying Deadlocks

A deadlock occurs when a group of threads forms a cycle of resource waiting: each thread holds a lock and waits for a lock held by another thread in the cycle.

Example:

~~~text
Thread A holds Lock A and waits for Lock B
Thread B holds Lock B and waits for Lock A
~~~

Neither thread can proceed to release the lock the other needs.

HotSpot can print a deadlock detection section at the end of the dump:

~~~text
Found one Java-level deadlock:
=============================
"lock-A-then-B":
  waiting to lock monitor ..., which is held by "lock-B-then-A"
"lock-B-then-A":
  waiting to lock monitor ..., which is held by "lock-A-then-B"

Found 1 deadlock.
~~~

This is an illustrative example. Exact phrasing and ID details may vary by JVM version.

How to read it:

1. Note the first thread and the lock it is waiting for.
2. Identify which thread holds that lock.
3. Open the lock-holding thread's entry and find the next lock it is waiting for.
4. Repeat until you cycle back to the first thread.
5. Locate the application frames holding/waiting on those locks to determine the lock acquisition order causing the cycle.

`jstack` includes deadlock detection for Java-level deadlocks that the VM can recognize. However, not every waiting condition is a deadlock. For example, threads waiting on a database, network service, or distributed lock outside the JVM can hang requests without forming a monitor cycle in the dump.

## 12. Distinguishing Deadlock, Lock Contention, and Thread Pool Starvation

| Symptom | Indicators in dump | Investigation direction |
|---|---|---|
| Deadlock | Cycle of threads holding locks and waiting on others; may include a deadlock report | Lock acquisition order, nested `synchronized`, lock ownership |
| Lock contention | Multiple threads `BLOCKED` on the same monitor | Overly long critical sections, shared locks, I/O work inside `synchronized` |
| Thread pool starvation | Many tasks waiting on futures/queues; all workers busy or waiting on dependent tasks | Pool size, blocking tasks, dependent tasks sharing the same executor |
| I/O bottleneck | Stacks stop at socket/file/native I/O | Endpoints, timeouts, network, disk, connection pools |
| CPU bottleneck | A few `RUNNABLE` threads repeat the same stack across dumps | Hot methods, busy loops, profiler/JFR |
| Thread leak | Thread count grows over time; many threads in the same group or with the same creation stack | Executor lifecycle, thread creation, non-terminating tasks |

Lock contention is not necessarily a deadlock. A thread may wait on a lock because another thread is executing a long critical section and will eventually release it. Capture additional dumps to see whether the owner makes progress or remains stuck.

Thread pool starvation can occur when every worker in a pool is waiting for the result of another task that itself needs the very same saturated pool. When you see `Future.get()`, `CompletableFuture.join()`, or queue waits, trace which executor runs the outer task and which executor must run the remaining work.

## 13. Analyzing Multiple Thread Dumps Over Time

A single dump is an instantaneous snapshot. When investigating hangs or abnormal slowness, collect a series of snapshots—for example, three dumps taken about five seconds apart.

PowerShell:

~~~powershell
$javaPid = 8120
1..3 | ForEach-Object {
    "===== $(Get-Date -Format o) =====" | Out-File -Encoding utf8 -Append thread-dumps.txt
    jcmd $javaPid Thread.print -l | Out-File -Encoding utf8 -Append thread-dumps.txt
    Start-Sleep -Seconds 5
}
~~~

Linux/macOS:

~~~bash
java_pid=8120
for i in 1 2 3; do
    date -Is >> thread-dumps.txt
    jcmd "$java_pid" Thread.print -l >> thread-dumps.txt
    sleep 5
done
~~~

When comparing dumps, focus on:

- Which threads remain in the exact same state and stack across captures.
- Which threads remain `BLOCKED` on the same monitor.
- Whether the lock owner changes or makes progress.
- Whether thread counts in a named group grow abnormally.
- Which `RUNNABLE` threads repeat the same application frames.
- Threads waiting on the same endpoint, queue, or connection pool.

You do not need to capture dumps at an excessively high frequency. Large thread dumps can add overhead and generate significant data to store; choose an interval long enough to show progress while keeping the snapshots useful.

## 14. Hands-On Example: Creating a Reproducible Deadlock

Create `ThreadDumpDeadlockDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class ThreadDumpDeadlockDemo {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();
    private static final CountDownLatch BOTH_HOLD_FIRST_LOCK =
            new CountDownLatch(2);

    public static void main(String[] args) throws InterruptedException {
        Thread a = new Thread(
                () -> lockInOrder(LOCK_A, LOCK_B),
                "lock-A-then-B"
        );
        Thread b = new Thread(
                () -> lockInOrder(LOCK_B, LOCK_A),
                "lock-B-then-A"
        );

        a.start();
        b.start();

        // Keep main alive so we can attach and capture a thread dump.
        new CountDownLatch(1).await();
    }

    private static void lockInOrder(Object first, Object second) {
        synchronized (first) {
            BOTH_HOLD_FIRST_LOCK.countDown();

            try {
                BOTH_HOLD_FIRST_LOCK.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            synchronized (second) {
                System.out.println("Acquired both locks");
            }
        }
    }
}
~~~

This program intentionally creates a deadlock: thread A holds `LOCK_A` and waits for `LOCK_B`; thread B holds `LOCK_B` and waits for `LOCK_A`. The `CountDownLatch` ensures both threads have acquired their first lock before attempting to acquire the second.

Compile:

~~~powershell
javac ThreadDumpDeadlockDemo.java
~~~

Run the program:

~~~powershell
java ThreadDumpDeadlockDemo
~~~

The program does not print the success message because both threads deadlock before reaching `println`. It stays running so you can capture a dump from a second terminal.

Find the PID:

~~~powershell
jps -l
~~~

Capture the dump:

~~~powershell
jcmd <PID> Thread.print -l
~~~

Or:

~~~powershell
jstack -l <PID>
~~~

In the output, locate the two threads:

- `lock-A-then-B`
- `lock-B-then-A`

You will see both in the `BLOCKED (on object monitor)` state. Each thread has a `waiting to lock` line and a `locked` line. At the end of the dump, HotSpot typically detects the cycle and prints a `Found one Java-level deadlock` section.

Once you have inspected the output, return to the terminal running the program and press Ctrl+C to stop the demo.

## 15. What a Thread Dump Cannot Conclude Alone

Thread dumps are powerful, but they have limits:

- They do not show exact historical CPU usage per thread.
- They do not show how long a thread has been waiting before the capture.
- They do not fully explain the state of databases, brokers, networks, or distributed locks.
- They do not prove that a `RUNNABLE` thread is consuming high CPU.
- They do not show all local variables or full heap contents.
- They do not replace heap dumps, profilers, JFR, or application logs.

Combine multiple data sources:

| Question | Complementary tool |
|---|---|
| Is a thread consuming high CPU? | OS thread metrics, JFR, profiler |
| How long has a thread waited on a lock? | JFR lock events, multiple thread dumps |
| Are there long GC pauses? | GC logs, JFR, JDK Mission Control |
| Which objects are retained on the heap? | Heap dump and heap analyzer |
| Where is native memory growing? | Native Memory Tracking and OS tools |
| Which endpoint is slow for requests? | Application tracing, metrics, and redacted logs |

Oracle JDK 17 includes Java Flight Recorder. JFR can record thread samples, lock profiles, and runtime events over time, helping pinpoint bottlenecks that a single snapshot cannot reveal.

## 16. Protecting Thread Dumps Before Sharing

Thread dumps usually do not contain all local variables, yet they can still expose:

- Thread names containing tenant, user, job, or request identifiers.
- Application packages, classes, methods, and internal architecture.
- File paths, endpoints, or internal service names appearing in thread names or stack traces.
- Lock, pool, and operational topology details.
- Sensitive strings or data if the application embeds them in thread names or diagnostic messages.

Before uploading a dump to a ticket, sending it to support, or sharing it publicly:

1. Review and redact sensitive usernames, tenants, endpoints, and file paths.
2. Avoid attaching logs or heap dumps containing credentials unless necessary.
3. Restrict access permissions and retention time for dump files.
4. Record the PID, capture timestamp, JDK version, and accompanying symptoms.
5. Keep the original in a controlled incident repository if deeper investigation is needed.

Do not modify the original file before preserving it as evidence. If you need to share a redacted version, create a separate copy.

## 17. Common Errors When Capturing Thread Dumps

| Symptom | Common cause | Resolution |
|---|---|---|
| `jstack is not recognized` | JDK is not installed or its `bin` directory is not on PATH | Use a JDK and invoke the tool using its full path |
| `Unable to open socket file` | Wrong PID, wrong user, or restricted attach | Verify the PID, user account, and namespace |
| JVM not listed by `jps` | JVM is running in a different container namespace | Run the tool inside the target container or matching PID namespace |
| `jstack` does not respond | JVM or attach mechanism is experiencing issues | Try `jcmd PID Thread.print -l` per operational policy; do not kill the process arbitrarily |
| No `java.util.concurrent` locks in output | Long listing mode was not enabled | Use `jstack -l` or `jcmd PID Thread.print -l` |
| No deadlock report | No JVM lock cycle detected at capture time | Compare multiple dumps and check I/O, pools, databases, or external locks |
| No dump visible after `kill -QUIT` | Standard output is redirected or JVM uses `-Xrs` | Check log output and use `jcmd` if attach is available |
| Output is too long | Application has many threads or deep stacks | Save to a file, filter by thread name, and compare snapshots |

For a post-crash core dump, use the Serviceability Agent instead of attaching to a live process:

~~~bash
jhsdb jstack --exe /path/to/java --core /path/to/core
~~~

Depending on the OS and core file type, you must provide the matching executable and core file. Consult the `jhsdb` documentation for your JDK version before performing postmortem analysis.

## 18. Incident Investigation Workflow Using Thread Dumps

A practical workflow:

1. Record the symptoms, timestamp, and application PID.
2. Identify the JDK version, host/container, and user account running the JVM.
3. Capture a thread dump with `jcmd PID Thread.print -l`.
4. If the issue is ongoing, capture two additional snapshots a few seconds apart.
5. Group threads by name, state, and top application-code stack frame.
6. Look for `BLOCKED`, `waiting to lock`, `parking to wait for`, and any deadlock report section.
7. For each waited-on lock, locate the thread currently holding it.
8. If there is no deadlock, inspect I/O, executors, connection pools, and external dependencies.
9. Cross-reference with metrics, logs, tracing, and JFR.
10. Store the original dump under controlled access, redact any shared copy, and document your findings with evidence.

Do not modify code or increase thread pool sizes based on a single state line. First determine what the threads are waiting on, who owns the resource, and whether the state persists across multiple snapshots.

## 19. Thread Dump Reading Checklist

- [ ] Identified the exact PID and JDK of the target process.
- [ ] Captured the dump with `jcmd PID Thread.print -l` or `jstack -l PID`.
- [ ] Saved the full output to a file.
- [ ] Read thread names, daemon flags, IDs, and states.
- [ ] Located the first stack frame belonging to application code.
- [ ] Distinguished among `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `RUNNABLE`.
- [ ] Distinguished among `waiting to lock`, `waiting on`, `locked`, and `parking to wait for`.
- [ ] Correlated waiting threads with lock-holding threads.
- [ ] Checked the deadlock report section if present.
- [ ] Compared multiple snapshots when investigating hangs or high CPU.
- [ ] Checked I/O, executors, and connection pools if no deadlock was found.
- [ ] Combined metrics, logs, or JFR when additional evidence was needed.
- [ ] Redacted sensitive data before sharing the dump.

A thread dump is a snapshot of JVM thread stacks and states. Start with the thread header and `java.lang.Thread.State`, then read the stack frames to locate where execution sits in the application. Use `waiting to lock`, `locked`, `waiting on`, and `parking to wait for` to map relationships between threads and resources. When suspecting a hang or deadlock, capture multiple snapshots and check for wait cycles; on JDK 17, prefer `jcmd PID Thread.print -l` for new diagnostics.

## References

- Oracle, Java SE 17 Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Oracle, Java SE 17 — The jcmd Utility: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Java SE 17 — The jstack Utility: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html
- Oracle, Java SE 17 — The java Command and Control+Break Handler: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
