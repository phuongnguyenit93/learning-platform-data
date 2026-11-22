# jstack and jcmd: Capturing and Analyzing Thread Dumps

A thread dump is a point-in-time snapshot of the state of all threads in a JVM. It shows which threads are running, waiting, or blocked waiting for a lock, along with each thread's current stack trace. This is critical diagnostic data when an application hangs, processes requests slowly, experiences high CPU usage, or has multiple threads contending for resources.

Two common tools for this are `jstack` and `jcmd`. Both can capture a thread dump from a running JVM, but Oracle marks `jstack` as *experimental and unsupported* and recommends `jcmd` for new diagnostics. This article covers both commands so you can read legacy runbooks while building new workflows around `jcmd`.

## 1. What Questions Can a Thread Dump Answer?

A thread dump can help identify:

- Which code a thread was executing when the snapshot was taken.
- Which threads are waiting for a monitor or lock.
- Which threads are in the `WAITING` or `TIMED_WAITING` state.
- Whether multiple threads are waiting on the same lock held by another thread.
- Whether there is a lock-wait cycle forming a Java-level deadlock.
- Whether a thread pool has many workers stuck in the same method or waiting on the same dependency.

A thread dump is a snapshot, not a continuous recording. It only reflects the state at the moment of collection. A thread shown as `BLOCKED` in one snapshot might acquire the lock immediately afterward; a single stack trace is not enough to conclude that an application is deadlocked.

### 1.1. When to Capture a Thread Dump

| Symptom | What to look for in the dump |
|---|---|
| Hanging requests | Which method, lock, or I/O operation request-handling threads are waiting on |
| High CPU usage | `RUNNABLE` threads with stack traces repeatedly appearing in the same code path |
| Throughput drop | Thread pool workers that are blocked or all waiting on the same resource |
| Unresponsive application | What state the main thread, event loops, and workers are in |
| Deadlock | A cycle of threads waiting on locks held by other threads |
| Suspected lock contention | Multiple threads waiting on the same monitor/ownable synchronizer |

If you need to observe trends over time, combine multiple thread dumps or use Java Flight Recorder (JFR). A single thread dump cannot provide the full history of CPU usage, latency, or prior lock contention events.

## 2. Differences Between jstack and jcmd

### 2.1. jstack

`jstack` is a command-line utility that prints stack traces of Java threads for a Java process specified by its PID.

Basic syntax:

~~~bash
jstack <pid>
~~~

Print additional lock information:

~~~bash
jstack -l <pid>
~~~

The `-l` (*long listing*) option instructs the tool to find and print additional information about locks, including ownable synchronizers used by APIs such as `java.util.concurrent.locks`. This is useful when investigating `ReentrantLock` and other non-intrinsic-monitor locks.

Help:

~~~bash
jstack -h
~~~

The Oracle JDK 21 documentation only lists `-l` and `-h`/`-help` in its man page. Some newer JDK releases may offer additional options, such as `-e` to print extended thread information. Check `jstack -h` for the toolchain you are using before relying on a specific option.

### 2.2. jcmd

`jcmd` sends diagnostic commands directly to a running JVM. To print a thread dump, use the `Thread.print` command:

~~~bash
jcmd <pid> Thread.print
~~~

Include lock information:

~~~bash
jcmd <pid> Thread.print -l
~~~

Print extended thread information:

~~~bash
jcmd <pid> Thread.print -e
~~~

In JDK 21, `Thread.print` supports `-l` to print `java.util.concurrent` locks and `-e` to print extended information. Oracle describes the command's impact as *Medium*, depending on the number of threads.

You can query the target JVM for the exact syntax:

~~~bash
jcmd <pid> help Thread.print
~~~

### 2.3. Comparison Table

| Criterion | jstack | jcmd |
|---|---|---|
| Process selection | PID | PID or main class |
| Print thread dump | `jstack <pid>` | `jcmd <pid> Thread.print` |
| Print lock information | `-l` | `Thread.print -l` |
| Extended thread information | Version-dependent; check `jstack -h` | `Thread.print -e` |
| Write dump to file | Shell stdout redirection | Stdout redirection, or `Thread.dump_to_file` if supported by the JVM |
| Deadlock detection | Yes | `Thread.print` also displays deadlocks when detected by the JVM |
| Tool status | Experimental/unsupported | Diagnostic tool recommended by Oracle |
| Best suited for | Legacy runbooks and familiar manual workflows | New diagnostics and automation |

**Recommendation:** use `jcmd` for new workflows. Keep `jstack` knowledge for understanding commands in legacy runbooks or when your current environment still relies on it.

## 3. Finding the JVM PID

Before capturing a thread dump, you need to select the right Java process.

List JVMs discovered by `jcmd`:

~~~bash
jcmd -l
~~~

Example:

~~~text
5485 jdk.jcmd/sun.tools.jcmd.JCmd
2125 com.example.orders.OrderApplication
7810 org.example.worker.BatchWorker
~~~

You can also use `jps -l` or OS commands such as `ps` to find the process. In Docker, running `jcmd -l` from the host might not list a JVM running in a separate Docker process; check the PID inside the appropriate container/PID namespace.

Once you have identified the PID:

~~~bash
jstack -l 2125
jcmd 2125 Thread.print -l
~~~

`jstack` accepts the PID of a Java process. `jcmd` can accept a PID or a main class; if the main class matches multiple processes, the command may be sent to all matching processes. In multi-instance environments, use a specific PID to avoid capturing a dump from the wrong process.

### 3.1. Attach Requirements and Permissions

According to Oracle documentation, `jcmd` must run on the same machine as the target JVM and under the same effective user/group identifiers used to start the JVM. Attaching is also subject to OS permissions, container policies, and the state of the process's Attach API.

If the command reports that it cannot attach:

- Verify that the PID still exists and belongs to the intended application.
- Verify that the tool is running on the same host or inside the right container/PID namespace.
- Check the user/group of both the terminal and the process.
- Use the tool from a JDK version compatible with the target JVM.
- Check whether the JVM was started with `-XX:+DisableAttachMechanism`.

No network port needs to be opened for `jcmd` or `jstack`; this is a local attach mechanism. If remote diagnostics are needed, use an authenticated and secured remote management mechanism such as JMX or a monitoring platform.

## 4. Capturing a Thread Dump with jstack

### 4.1. Printing to the Terminal

~~~bash
jstack 2125
~~~

This command prints the stack traces of threads belonging to the JVM with PID `2125`. Each thread entry typically includes its name, thread number, native thread ID, state, and stack frames.

### 4.2. Including Locks and Owners

~~~bash
jstack -l 2125
~~~

Use `-l` when you need monitor/ownable synchronizer details. The output may contain lines such as:

~~~text
"worker-1" #35 prio=5 tid=... nid=... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.Service.update(Service.java:42)
    - waiting to lock <0x0000000123456780> (a java.lang.Object)
    - locked <0x0000000123456790> (a java.lang.Object)
~~~

How to read this:

- `waiting to lock`: the thread is waiting to acquire that lock.
- `locked`: the thread currently holds the corresponding lock.
- The object address inside `<...>` lets you cross-reference locks across threads in the same dump.
- Stack frames near the top generally indicate the method where the thread is blocked.

### 4.3. Saving Output to a File

On Linux/macOS:

~~~bash
jstack -l 2125 > thread-2125-01.txt 2>&1
~~~

On Windows PowerShell:

~~~powershell
jstack -l 2125 *> thread-2125-01.txt
~~~

Include the PID and a timestamp in the filename so you do not overwrite earlier snapshots. Store the file in a directory readable only by personnel authorized to handle incidents.

## 5. Capturing a Thread Dump with jcmd

### 5.1. Printing to the Terminal

~~~bash
jcmd 2125 Thread.print
~~~

This is the direct way to print a thread dump. The command includes all threads exposed by the JVM through the diagnostic interface, along with their stack traces.

### 5.2. Adding Lock Information

~~~bash
jcmd 2125 Thread.print -l
~~~

Use this option when lock contention is suspected, especially involving `java.util.concurrent` constructs. If you also need extended thread information:

~~~bash
jcmd 2125 Thread.print -e
~~~

Both options can be combined:

~~~bash
jcmd 2125 Thread.print -e -l
~~~

Diagnostic command options must match the syntax supported by the target JVM. Check first:

~~~bash
jcmd 2125 help Thread.print
~~~

### 5.3. Saving a Thread Dump to a File

The most broadly compatible approach is shell output redirection:

~~~bash
jcmd 2125 Thread.print -l > thread-2125-01.txt 2>&1
~~~

Starting from JDK 22, many JDK distributions also provide the `Thread.dump_to_file` diagnostic command to write thread dumps directly to a file in plain text or JSON format. Check whether the target JVM supports it:

~~~bash
jcmd 2125 help Thread.dump_to_file
~~~

If supported, you can run:

~~~bash
jcmd 2125 Thread.dump_to_file threads-2125.json
jcmd 2125 Thread.dump_to_file -format=json threads-2125.json
jcmd 2125 Thread.dump_to_file -format=plain threads-2125.txt
~~~

The JVM creates the file in the process's working directory if a relative path is passed. Use an absolute path when you need exact control over where the file is saved. If the path contains spaces, quote the argument according to both your shell's and the diagnostic command's quoting rules.

By default, the command does not overwrite an existing file. Only pass `-overwrite` when you explicitly want to replace an existing file:

~~~bash
jcmd 2125 Thread.dump_to_file -overwrite -format=json threads-2125.json
~~~

`Thread.dump_to_file` has Medium impact, depending on the number of threads. If you need lock details or deadlock analysis, prefer `Thread.print -l`; verify the output file format against your specific JDK version.

## 6. How to Read Thread States

Thread dumps typically display Java thread states via `java.lang.Thread.State`.

| State | Meaning | How to interpret |
|---|---|---|
| `RUNNABLE` | The thread is executing or ready to execute in the JVM | Inspect stack frames to see whether it is computing, processing, or in a native call |
| `BLOCKED` | The thread is waiting to enter a synchronized monitor | Find the thread currently holding the monitor it needs |
| `WAITING` | The thread is waiting indefinitely for another thread to perform an action | Check for `Object.wait`, `LockSupport.park`, `CountDownLatch.await`, `join` |
| `TIMED_WAITING` | The thread is waiting for a specified period | Check for `Thread.sleep`, timed wait, timed park, or timed join |
| `NEW` | The thread has not started yet | Usually does not appear as an active thread in dumps |
| `TERMINATED` | The thread has finished execution | No longer active for JVM diagnostics |

`RUNNABLE` does not guarantee that a thread is continuously consuming CPU. The thread may be waiting on I/O in native code or waiting to be scheduled by the OS scheduler. Read the stack trace and correlate it with OS-level metrics.

### 6.1. BLOCKED vs. WAITING

`BLOCKED` indicates waiting to acquire an intrinsic monitor, usually because another thread currently holds the requested lock. In the dump, look for:

~~~text
java.lang.Thread.State: BLOCKED (on object monitor)
- waiting to lock <0x...>
~~~

`WAITING` usually indicates that the thread is waiting on a condition or signal. For example:

~~~text
java.lang.Thread.State: WAITING (parking)
at java.util.concurrent.CountDownLatch.await(...)
~~~

The thread is waiting for the latch to open. That can be completely normal if it is waiting for another task to complete.

`TIMED_WAITING` can also be normal—for example, a scheduler thread sleeping until its next cycle. Never conclude that an application is hung based solely on the state name.

## 7. Detecting and Analyzing Deadlocks

A deadlock occurs when two or more threads form a circular wait for resources: each thread holds one lock and waits for a lock held by another thread. No thread can proceed to release its lock.

Two-thread example:

~~~text
Thread A holds LOCK_A and waits for LOCK_B
Thread B holds LOCK_B and waits for LOCK_A
~~~

Both `jstack` and `jcmd Thread.print` can detect Java-level deadlocks. The output looks like:

~~~text
Found one Java-level deadlock:
=============================

"demo-deadlock-A":
  waiting to lock monitor ... (object ..., a java.lang.Object),
  which is held by "demo-deadlock-B"

"demo-deadlock-B":
  waiting to lock monitor ... (object ..., a java.lang.Object),
  which is held by "demo-deadlock-A"
~~~

To read the result:

1. Identify which thread is waiting for a lock.
2. Identify which thread holds that lock.
3. Follow the lock that the holding thread is waiting on.
4. If the chain cycles back to the original thread, you have a deadlock.
5. Use the stack frames to locate the lines of code acquiring the locks and their acquisition order.

Not every `BLOCKED` thread is deadlocked. A thread may be temporarily blocked while the lock holder is still running normally. A deadlock requires a wait cycle that cannot resolve on its own.

### 7.1. A Hang Without a Deadlock

Even if the output does not contain `Found one Java-level deadlock`, the application can still hang due to:

- A thread waiting for an event or notification that never arrives.
- A thread waiting on I/O or an external dependency to respond.
- A monitor held for too long without forming a deadlock cycle.
- Thread pool exhaustion because all workers are waiting on the same resource.
- A thread waiting on a `Future`/`CompletableFuture` whose completion task is never executed.

In these cases, examine the stack traces of waiting threads, lock-holding threads, thread pool workers, and network/database-related threads. Compare multiple snapshots to distinguish transient states from long-lived stalls.

## 8. Comparing Multiple Thread Dumps Over Time

A single snapshot captures only one moment in time. When investigating a hang or CPU spike, capture a sequence of snapshots a few seconds apart—for example, three dumps spaced 5–10 seconds apart if the system allows.

Example:

~~~bash
jcmd 2125 Thread.print -l > dump-01.txt 2>&1
sleep 5
jcmd 2125 Thread.print -l > dump-02.txt 2>&1
sleep 5
jcmd 2125 Thread.print -l > dump-03.txt 2>&1
~~~

On Windows PowerShell:

~~~powershell
jcmd 2125 Thread.print -l *> dump-01.txt
Start-Sleep -Seconds 5
jcmd 2125 Thread.print -l *> dump-02.txt
Start-Sleep -Seconds 5
jcmd 2125 Thread.print -l *> dump-03.txt
~~~

When comparing, focus on:

- Threads with the same name/thread ID whose stack frames do not change across multiple snapshots.
- Threads that remain `BLOCKED` and are waiting on the same monitor.
- Thread pools where the number of blocked workers increases over time.
- `RUNNABLE` threads appearing in the same method across multiple snapshots during high CPU usage.
- Threads waiting on a dependency with no thread processing the corresponding result.

If a thread moves across different stack frames, it may still be making progress. If a thread stays frozen at the same stack frame across multiple snapshots, inspect the locks, I/O, and wait conditions. Correlate dump data with application logs, metrics, and traces.

## 9. Hands-On Java 17+: Creating a Deadlock and Thread States

The following example creates four threads that are easy to spot in a thread dump:

- `demo-deadlock-A` holds `LOCK_A` and then waits for `LOCK_B`.
- `demo-deadlock-B` holds `LOCK_B` and then waits for `LOCK_A`.
- `demo-waiting` waits on a `CountDownLatch` that is never counted down.
- `demo-sleeping` sleeps for a long duration.

File `ThreadDumpFixture.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class ThreadDumpFixture {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothOwnFirstLock = new CountDownLatch(2);

        Thread first = new Thread(() -> {
            synchronized (LOCK_A) {
                bothOwnFirstLock.countDown();
                await(bothOwnFirstLock);
                synchronized (LOCK_B) { }
            }
        }, "demo-deadlock-A");

        Thread second = new Thread(() -> {
            synchronized (LOCK_B) {
                bothOwnFirstLock.countDown();
                await(bothOwnFirstLock);
                synchronized (LOCK_A) { }
            }
        }, "demo-deadlock-B");

        Thread waiting = new Thread(() -> {
            try {
                new CountDownLatch(1).await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-waiting");

        Thread sleeping = new Thread(() -> {
            try {
                Thread.sleep(600_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-sleeping");

        first.start();
        second.start();
        waiting.start();
        sleeping.start();

        System.out.println("ThreadDumpFixture ready");
        new CountDownLatch(1).await();
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }
}
~~~

Compile and run in the first terminal:

~~~bash
javac --release 17 ThreadDumpFixture.java
java ThreadDumpFixture
~~~

Expected stdout:

~~~text
ThreadDumpFixture ready
~~~

The program is designed to stay running until you stop the process. This is a learning fixture; do not use this deadlocking logic in real applications.

### 9.1. Capturing a Dump with jstack

In a second terminal, replace `12345` with the actual PID of the fixture:

~~~bash
jstack -l 12345 > fixture-jstack.txt 2>&1
~~~

Look for the thread names:

~~~text
demo-deadlock-A
demo-deadlock-B
demo-waiting
demo-sleeping
Found one Java-level deadlock
~~~

The two deadlocked threads will be in the `BLOCKED` state. The thread waiting on the latch will be in `WAITING`, and the sleeping thread will be in `TIMED_WAITING`.

### 9.2. Capturing a Dump with jcmd

~~~bash
jcmd 12345 Thread.print -l > fixture-jcmd.txt 2>&1
~~~

You can include extended information:

~~~bash
jcmd 12345 Thread.print -e -l > fixture-jcmd-extended.txt 2>&1
~~~

On JDKs that support `Thread.dump_to_file`, you can save JSON:

~~~bash
jcmd 12345 Thread.dump_to_file -format=json fixture-threads.json
~~~

JDK 21 does not list `Thread.dump_to_file` in its command reference documentation; this command is documented starting in JDK 22. Always check `jcmd 12345 help Thread.dump_to_file` on the target JVM before using it.

Stop the fixture with `Ctrl+C` in the first terminal after you finish collecting the dumps.

## 10. Choosing the Right Tool for the Situation

| Need | Recommended tool |
|---|---|
| Quick snapshot from a running JVM | `jcmd <pid> Thread.print` |
| Investigating lock contention | `jcmd <pid> Thread.print -l` |
| Extended output needed | `jcmd <pid> Thread.print -e` if supported by the target |
| Writing dump to plain/JSON file | `Thread.dump_to_file` if provided by the target JDK |
| Reading legacy runbooks or scripts | `jstack <pid>` / `jstack -l <pid>` |
| Analyzing a core dump after a crash | `jhsdb jstack` |
| Tracking events over time, latency, or lock profiles | JFR and JDK Mission Control |

### 10.1. Analyzing Core Dumps with jhsdb jstack

If the JVM has crashed and produced a core dump, standard `jstack` is not the primary approach. Use the Serviceability Agent:

~~~bash
jhsdb jstack --exe /opt/jdk-21/bin/java --core /var/crash/core.12345
~~~

To print native stack frames as well:

~~~bash
jhsdb jstack --mixed --pid 12345
~~~

`--mixed` belongs to `jhsdb jstack`, not to the standard `jstack` command. For core dumps, the executable must match the binary that produced the core file. Postmortem analysis has specific OS and debugger requirements; use the matching JDK and architecture.

## 11. Permissions, Versions, and Limitations

### 11.1. Attaching Requires the Right Host and User

`jcmd` must run on the same machine as the JVM and with the same effective user/group identifiers per Oracle's documentation. OS permissions, containers, and the Attach API also affect attach capability.

If the process was started with `-XX:+DisableAttachMechanism`, attach tools will not be able to connect. In containers, the PID visible inside the container may differ from the PID on the host; run the tool in the right namespace and use the right PID.

### 11.2. Use a Tool Matching the Target JVM

Diagnostic tools can vary across JDK releases and vendors. Oracle JDK 21 marks `jstack` as experimental/unsupported and notes that it may be removed in a future JDK release.

Best practices:

- Use `jcmd` for new runbooks and automation.
- Use `jstack` when compatibility with legacy scripts or existing tested procedures is required.
- Check `jstack -h` and `jcmd <pid> help Thread.print` on the exact JDK in use.
- Use tools from a JDK matching the target JVM.
- When upgrading the JDK, re-verify options, output format, and pipeline parsers.

On Windows, if `dbgeng.dll` is missing, Oracle documentation notes that you may need to install Debugging Tools for Windows. `PATH` must include the location of the target process's `jvm.dll` or the directory corresponding to the core dump.

### 11.3. A Thread Dump Is Not a CPU Profiler

A thread dump provides a stack snapshot. It does not accurately measure per-method CPU time, record event history, or replace a profiler.

If CPU usage is high, compare multiple dumps and correlate OS thread IDs with CPU metrics. If you need to know which methods consume time, latency, or lock contention along a timeline, use JFR/JDK Mission Control or an appropriate profiler.

## 12. Protecting Sensitive Data in Thread Dumps

Thread dumps often contain thread names, class/method names, stack frames, lock identities, worker names, and environment details. Depending on the application, thread names or stack traces may expose customer IDs, URLs, tenant names, queue names, or internal details.

Operational guidelines:

- Store dumps only in directories with restricted read permissions.
- Do not upload dumps to public tickets or repositories.
- Redact sensitive data before sharing externally.
- Limit the number of snapshots and their retention period.
- Include the PID, hostname, timestamp, and JDK version in the filename or metadata.
- When capturing in production, record who performed the capture and why.

Thread dumps are generally lighter than heap dumps, but the command still carries an impact depending on the number of threads and JVM state. Avoid running it repeatedly at very short intervals on an already overloaded process.

## 13. Common Errors and How to Handle Them

| Symptom | Possible cause | Resolution |
|---|---|---|
| `jstack` cannot find PID | Wrong PID, process exited, or namespace mismatch | Re-verify with `jcmd -l` / `ps` |
| `AttachNotSupportedException` | Attach API disabled or unsupported runtime | Check startup flags, JDK, and runtime |
| `Operation not permitted` / access denied | User/group or OS policy blocks attach | Run as an authorized account and check permissions |
| `jcmd` does not see JVM in Docker | JVM is in a separate container/PID namespace | Run `ps` and the tool inside the right container |
| `Unknown diagnostic command` | Target JVM does not provide that command | Run `jcmd <pid> help` against the process itself |
| `Thread.dump_to_file` does not exist | JDK is too old or vendor does not provide it | Redirect output from `Thread.print` instead |
| No deadlock, yet app still hangs | Waiting on I/O, notification, pool exhaustion, or a long-held lock | Analyze waiting thread stacks and capture multiple snapshots |
| Dump is too large | JVM has many threads or deep stacks | Save to a file, limit capture frequency, and verify the PID |
| Cannot create dump file | Invalid working directory, write permissions, or disk space | Use a writable path with sufficient free space |
| Windows reports missing `dbgeng.dll` | Missing Debugging Tools for Windows | Install the debugging tools and check `PATH` |

## 14. Thread Dump Collection and Analysis Workflow

1. Confirm the symptoms and time of occurrence.
2. Identify the PID, main class, hostname/container, and JDK version.
3. Run `jcmd <pid> help Thread.print` to check available options.
4. Capture the first snapshot with `jcmd <pid> Thread.print -l`.
5. If the issue persists, capture 2–3 additional snapshots spaced a few seconds apart.
6. Look for `BLOCKED`, `WAITING`, `TIMED_WAITING`, and notable `RUNNABLE` threads.
7. Cross-reference monitors/ownable synchronizers and the deadlock report.
8. Compare stack frames across snapshots.
9. Correlate with logs, metrics, request traces, and thread pool status.
10. Save a redacted report and document the findings and remediation actions.

## 15. Pre-Conclusion Checklist

- [ ] Verified the correct PID and JVM instance.
- [ ] Used a JDK/tool version matching the target process.
- [ ] Captured thread dumps with lock details when lock contention is suspected.
- [ ] Checked the deadlock section if detected by the JVM.
- [ ] Distinguished between `BLOCKED`, `WAITING`, and `TIMED_WAITING`.
- [ ] Inspected stack frames of both lock-holding and waiting threads.
- [ ] Captured multiple snapshots when confirming a persistent state.
- [ ] Did not conclude a deadlock from a single `BLOCKED` thread.
- [ ] Correlated with logs, metrics, and external dependencies.
- [ ] Secured the dump files with clear timestamps and PIDs.

## 16. Summary

Both `jstack` and `jcmd` can capture thread dumps from a running JVM. `jstack -l` is familiar from legacy runbooks, but Oracle marks `jstack` as experimental/unsupported and recommends `jcmd` for new diagnostics.

Start with `jcmd <pid> Thread.print`; add `-l` when you need lock details and `-e` when you need extended thread information. On newer JDKs that provide `Thread.dump_to_file`, you can save dumps in plain text or JSON format. To find deadlocks, trace the cycle of threads waiting on locks; to investigate hangs, compare multiple snapshots and correlate with logs and metrics. If the JVM has crashed, use `jhsdb jstack` to analyze the core dump.

References:

- [The jstack Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html)
- [The jcmd Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Diagnostic Tools — Java SE 21](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — Java SE 22 (Thread.dump_to_file)](https://docs.oracle.com/en/java/javase/22/docs/specs/man/jcmd.html)
- [Troubleshooting Guide — Diagnose a Hung Process](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf)