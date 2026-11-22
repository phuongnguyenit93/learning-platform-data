# Thread Commands in jcmd

`jcmd` is a diagnostic tool included with the JDK that lets you send diagnostic commands directly to a running JVM. Within the thread-related command group, `Thread.print` is the most commonly used command: it prints a thread dump containing threads and their stack traces at the moment of capture. Thread dumps help investigate hung applications, slow requests, thread pool exhaustion, lock contention, and deadlocks.

On JDK 21 and later, `Thread.dump_to_file` is also available, which can generate thread dumps in text or JSON format and lists both platform threads and virtual threads. The two commands serve different purposes: `Thread.print` is useful when you need traditional stack traces and lock information; `Thread.dump_to_file` is useful when you need to inspect a large number of threads, especially virtual threads.

A thread dump is a diagnostic snapshot at a single point in time, not a complete record of activity history. When investigating an incident, combine multiple snapshots, application logs, metrics, and Java Flight Recorder (JFR) to find the root cause.

## 1. What is a thread dump?

A thread dump is a description of the state of threads in the JVM at the time of the request. For each thread, a dump typically includes:

- The thread name and identifying information.
- The thread state, such as `RUNNABLE`, `BLOCKED`, or `WAITING`.
- A stack trace showing which methods the thread is executing or waiting in.
- Monitor/lock information that the thread is holding or waiting on, if supported by the dump type and options.
- Additional JVM information such as daemon status, priority, thread ID, and native thread ID depending on the format.

Thread dumps help answer questions such as:

- Which threads are processing requests?
- Which threads are waiting on a monitor or lock?
- Are multiple threads blocked by the same lock?
- Is there a deadlock cycle among threads?
- Are executor worker threads busy, waiting for work, or stuck?
- Are threads spending time in application code, I/O, or external libraries?

A single thread dump does not show full CPU usage over time, how many times a method was called, or the root cause of every latency issue. It shows the state and stack at the time of capture; it must be correlated with other observability sources.

## 2. Finding the target JVM process

Open Terminal or PowerShell on the same machine as the target JVM. List the JVMs visible to `jcmd`:

```sh
jcmd -l
```

The command displays the process ID (PID), main class, and command line used to launch the JVM. Running `jcmd` without passing a PID or command name has the same effect as `jcmd -l`.

Illustrative example output:

```text
24680 com.example.OrderService
27110 com.example.WorkerMain
```

PIDs change on every restart. Identify the right application by its main class, command line, and deployment details; do not pick a PID solely based on its position in the list.

If you need to check OS-level process information, you can use the appropriate tool:

```sh
ps -ef
```

On Windows:

```powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
```

In container environments, `jcmd -l` does not list JVMs running in an isolated Docker process outside the namespace the tool is observing. Find the PID inside the container using a tool like `ps` and run `jcmd` in the proper environment/container.

## 3. Requirements for jcmd to connect to a JVM

According to the JDK documentation, `jcmd` must run on the same machine as the target JVM and use the same effective user/group ID as the account that launched the JVM.

Practical requirements include:

- Use the exact machine or container where the process is running.
- Run with the same OS account as the target JVM, or equivalent privileges per system policy.
- Use the `jcmd` tool from a JDK compatible with the JVM being inspected.
- Verify that the process is still alive and the PID has not been reused.
- Check that the attach mechanism is not disabled or blocked by the deployment environment.
- Check access permissions and runtime security configuration.

If the JVM runs in a container, the PID on the host may differ from the PID inside the container. Use the PID within the same namespace where `jcmd` is executed.

`jcmd` is a local diagnostic tool, not a command sent over the network to an arbitrary JVM. For remote machines, access the target host through approved operational procedures and run the tool there.

## 4. Viewing help for Thread.print

The list of diagnostic commands depends on the JVM and HotSpot version. Before using options, query the target JVM itself:

```sh
jcmd 24680 help
```

View the syntax for the specific command:

```sh
jcmd 24680 help Thread.print
```

In the examples, `24680` is an illustrative PID; replace it with the actual PID.

As of JDK 21, `Thread.print` has the following main options:

| Option | Effect |
|---|---|
| No options | Prints a thread dump with stack traces |
| `-l` | Prints additional `java.util.concurrent` lock information |
| `-e` | Prints extended thread information |

Boolean options are passed using key or key=value syntax. For example, `-l` or `-l=true` depending on what the tool invocation accepts. Always confirm the exact syntax for the running JVM with `help Thread.print`.

## 5. Capturing a basic thread dump with Thread.print

Basic command:

```sh
jcmd 24680 Thread.print
```

The target JVM prints the thread dump to the output of the `jcmd` command. The output usually starts with a timestamp and a header like:

```text
2026-11-10 10:15:30
Full thread dump OpenJDK 64-Bit Server VM (17.0.x+... mixed mode):
```

This is followed by thread groups and stack traces. The JVM name, version, timestamp, thread IDs, and thread count vary by process; do not treat the example above as fixed output.

To save the output to a file from the shell:

```sh
jcmd 24680 Thread.print > thread-dump.txt
```

In PowerShell:

```powershell
jcmd 24680 Thread.print | Out-File -Encoding utf8 thread-dump.txt
```

Saving to a file helps you compare multiple snapshots, search for threads by name, and share results with the investigation team. Include the PID and timestamp in the filename if you need to save multiple dumps to avoid overwriting.

## 6. Printing additional lock information with Thread.print -l

When you suspect threads are stuck on locks, use:

```sh
jcmd 24680 Thread.print -l
```

The `-l` option requests additional information about `java.util.concurrent` locks. Traditional output also shows monitors that threads are waiting on or holding when the JVM has that information.

Common indicators:

- `- waiting to lock`: the thread is waiting to acquire a monitor.
- `- locked`: the thread is holding a monitor.
- `- waiting on`: the thread is waiting on an object or corresponding condition.
- `Locked ownable synchronizers`: list of synchronizers the thread is holding, when supported by the dump.

Exact line names and formatting depend on the JVM. During investigation, compare object/lock identities between the waiting thread and the thread holding that lock.

If there is a wait cycle among multiple threads, HotSpot may print a deadlock section, such as `Found one Java-level deadlock`. Read the entire chain of lock owners and waiters to identify the cycle, rather than looking at only a single warning line.

## 7. Printing extended information with Thread.print -e

The `-e` option instructs the JVM to print extended thread information:

```sh
jcmd 24680 Thread.print -e
```

Example combining both options:

```sh
jcmd 24680 Thread.print -e -l
```

Extended information can be helpful when correlating Java threads with OS threads or performing deeper analysis. The exact fields depend on the JDK version and JVM implementation.

Avoid enabling every option on every capture without a clear goal. Start with a basic dump, then add lock or extended information when your investigation requires it.

## 8. Thread states in a thread dump

Java thread states are represented by `java.lang.Thread.State`. Common states include:

| State | Meaning | Example |
|---|---|---|
| `NEW` | Thread has been created but not yet started | Constructor called, `start()` not yet called |
| `RUNNABLE` | Thread is running or ready to run in the JVM | Executing Java code or certain native operations |
| `BLOCKED` | Waiting to acquire an intrinsic monitor to enter a synchronized block/method | Another thread is holding the monitor |
| `WAITING` | Waiting indefinitely for another thread/action | `Object.wait()`, `Thread.join()` without timeout, `LockSupport.park()` |
| `TIMED_WAITING` | Waiting for a bounded amount of time | `Thread.sleep()`, timed wait/join/park |
| `TERMINATED` | Thread has exited | Runnable completed or terminated due to an exception |

Important notes:

- `RUNNABLE` does not necessarily mean the thread is actively consuming CPU. The thread may be in native I/O or waiting on an external resource.
- `BLOCKED` in the Java model typically relates to waiting for an intrinsic `synchronized` monitor.
- `WAITING` and `TIMED_WAITING` are not necessarily errors; idle worker threads in an executor are normally parked waiting for work.
- `Object.wait()` releases the monitor held on that object; the thread then waits to be notified/interrupted or meet another condition.
- A thread that remains `BLOCKED` for an unusually long time should be correlated with the thread holding the monitor.

Do not conclude that an application is hung simply because you see many `WAITING` threads. Read the stack traces, lock owners, wait durations, and each thread's role in the application architecture.

## 9. Reading the structure of a thread entry

A traditional entry might look like this (abbreviated and illustrative):

```text
"demo-worker" #28 prio=5 os_prio=0 cpu=12.50ms elapsed=30.10s tid=0x... nid=0x... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderService.process(OrderService.java:42)
        - waiting to lock <0x00000000...> (a java.lang.Object)
```

How to read it:

- `"demo-worker"`: thread name.
- `#28`: thread ID in the dump display.
- `prio`: Java thread priority.
- `cpu` and `elapsed`: CPU/time statistics if provided by the JVM.
- `tid`: address/identifier of the VM's internal thread structure.
- `nid`: native thread ID.
- `BLOCKED`: thread is waiting on a monitor.
- `at ...` lines: stack frames; the top line is the most recent/current execution point.
- `waiting to lock`: the monitor the thread wants to acquire.

A thread holding a monitor may have an entry like:

```text
"demo-lock-owner" #27 ... TIMED_WAITING (sleeping)
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.LockDemo.lambda$main$0(LockDemo.java:18)
        - locked <0x00000000...> (a java.lang.Object)
```

If the monitor identity on the `waiting to lock` line matches the monitor on the `locked` line, the second thread is waiting for the first thread to release the lock.

Do not rely on a single stack trace line to determine the root cause. Trace the frames in application code and correlate all involved threads.

## 10. Java 17+ example to reproduce lock contention for practice

The following program creates one thread that holds a monitor for a period of time and another thread that waits on that monitor. It prints the PID so you can invoke `jcmd` from a second terminal.

Create `ThreadCommandDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadCommandDemo {
    private static final Object LOCK = new Object();
    private static final CountDownLatch OWNER_READY =
            new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                OWNER_READY.countDown();
                try {
                    Thread.sleep(TimeUnit.MINUTES.toMillis(1));
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-owner");

        Thread waiter = new Thread(() -> {
            try {
                OWNER_READY.await();
                synchronized (LOCK) {
                    System.out.println("Lock acquired");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-lock-waiter");

        owner.start();
        OWNER_READY.await();
        waiter.start();

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(5);
        while (waiter.getState() != Thread.State.BLOCKED
                && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        new CountDownLatch(1).await();
    }
}
```

Compile and run:

```sh
javac ThreadCommandDemo.java
java ThreadCommandDemo
```

Initial output:

```text
PID=24680
```

Your actual PID will differ. The program keeps the main thread waiting indefinitely so the JVM stays alive. After about one minute, the owner releases the monitor and the waiter may print:

```text
Lock acquired
```

Open a second terminal and replace the PID with the actual value:

```sh
jcmd 24680 Thread.print -l
```

Look for the two threads named `demo-lock-owner` and `demo-lock-waiter`. The owner thread is `TIMED_WAITING` in `Thread.sleep` while still holding the monitor; the waiter thread is in the `BLOCKED` state because it is trying to enter the synchronized block.

Stop the program with Ctrl+C once you finish practicing. Do not use this demo in production; it intentionally creates contention to help you practice reading dumps.

## 11. How to identify deadlocks

A deadlock occurs when two or more threads hold resources that other threads need, forming a wait cycle that cannot make progress on its own.

Logical example:

- Thread A holds lock X and waits for lock Y.
- Thread B holds lock Y and waits for lock X.
- A cannot acquire Y until B releases Y.
- B cannot release Y because it is waiting for X held by A.

When you suspect a deadlock:

1. Capture a dump with `Thread.print -l`.
2. Look for the deadlock report section if detected by the JVM.
3. Record which thread is holding which lock.
4. Identify which thread is waiting for that lock.
5. Follow the chain until you see a cycle returning to the starting thread.
6. Locate the code acquiring multiple locks and check the acquisition order.
7. Capture another dump to confirm the cycle persists.

Common remediation approaches:

- Enforce a consistent lock acquisition order across the entire codebase.
- Narrow synchronized scopes to reduce lock hold times.
- Avoid calling external code or performing I/O while holding a lock.
- Use timeouts or appropriate coordination mechanisms when using explicit locks.
- Separate shared state or use concurrency utilities with clear contracts.

A thread waiting briefly for a lock is not a deadlock. A deadlock requires a dependency cycle; distinguish it from transient lock contention or a slow thread that has not yet released its lock.

## 12. Distinguishing BLOCKED, WAITING, and TIMED_WAITING during investigation

These states are often misunderstood:

**BLOCKED** usually indicates waiting for an intrinsic monitor. Find the thread holding the monitor and examine its stack trace. If the owner is stuck in application code or I/O while holding the lock, waiters can pile up.

**WAITING** usually indicates waiting for a condition or signal. For example, thread pool workers park to wait for tasks; this can be completely normal. If all workers are waiting on a future while no thread is left to complete that future, examine task dependencies.

**TIMED_WAITING** usually has a time limit. Sleeping may be intentional retry/backoff; timed waiting may be a timeout counting down. Check the stack trace and the interval between dumps to see whether state is progressing.

`RUNNABLE` also requires careful reading. A thread with a stack in a socket read or native method may be waiting on I/O even though its state is still `RUNNABLE`. Look at the first application code frame and the library frames beneath it.

## 13. Capturing multiple dumps to distinguish transient vs. persistent issues

A single dump only shows one point in time. When an application is slow or hung, capture several dumps spaced by a short interval, such as 5–10 seconds depending on the situation:

```sh
jcmd 24680 Thread.print -l > dump-1.txt
```

Wait a short interval, then:

```sh
jcmd 24680 Thread.print -l > dump-2.txt
```

And again:

```sh
jcmd 24680 Thread.print -l > dump-3.txt
```

Compare:

- Do threads keep the exact same stack traces across snapshots?
- Are multiple threads still waiting on the same monitor?
- Did the lock owner thread change state?
- Are any worker threads in the thread pool completing tasks?
- Are stack traces advancing, or is every thread stuck at the exact same point?

If threads are moving across stacks or lock owners are changing, the system may be making progress slowly. If the same lock cycle or wait point repeats across multiple dumps, investigate further.

Do not capture continuously at an overly high frequency. `Thread.print` has Medium impact depending on thread count; collecting too frequently can add load and generate large logs.

## 14. Saving thread dumps to a file with Thread.dump_to_file

JDK 21+ provides the `Thread.dump_to_file` command to write a thread dump directly to a file, in text or JSON format:

```sh
jcmd 24680 Thread.dump_to_file -format=text thread-dump.txt
```

JSON format:

```sh
jcmd 24680 Thread.dump_to_file -format=json thread-dump.json
```

This command lists both platform threads and virtual threads. This dump format is well suited when you need to inspect large numbers of virtual threads or feed data into automated analysis tools.

Understand the trade-off: JDK 21 documentation explicitly notes that this format does not include object addresses, locks, JNI statistics, heap statistics, and certain other details present in traditional thread dumps. When you need to analyze monitor/lock contention, use `Thread.print -l`; when you need a virtual thread inventory, use `Thread.dump_to_file`.

The file is written on the target JVM's machine. Choose a path where the account running the JVM has write permission and ensure sufficient disk space. For an existing file, only enable the overwrite option if you truly intend to replace the old contents and that syntax is confirmed by `help Thread.dump_to_file` on your JDK.

## 15. Analyzing virtual threads

Virtual threads are threads managed by the Java runtime rather than having a fixed one-to-one mapping to OS threads. An application can create a very large number of virtual threads, so traditional dumps may not be the most convenient way to inspect all of them.

With JDK 21+:

```sh
jcmd 24680 Thread.dump_to_file -format=text virtual-threads.txt
```

Or:

```sh
jcmd 24680 Thread.dump_to_file -format=json virtual-threads.json
```

This format makes it easier to inspect thread names, states, and stack traces of platform/virtual threads in an analyzable structure. JSON is useful when you want to filter by thread name, state, or stack frame using scripts or tools.

To investigate virtual threads:

- Find threads waiting on the same endpoint or resource.
- Inspect stack traces at I/O, lock, or future wait points.
- Distinguish a large virtual thread count from the carrier/platform thread count.
- Inspect pinning and virtual thread events via JFR if needed.
- Check synchronized code and native calls that can reduce the scheduler's ability to unmount carrier threads.

Text/JSON thread dump files do not contain the full lock/object details of traditional dumps. Use the right format for your investigation question; do not treat the two dump types as complete replacements for each other.

## 16. Comparing Thread.print with related tools

| Tool | Purpose | When to use |
|---|---|---|
| `jcmd PID Thread.print` | Traditional thread dump, stack traces | Investigating thread states, stacks, and deadlocks |
| `jcmd PID Thread.print -l` | Adds `java.util.concurrent` lock information | Investigating lock contention and deadlocks |
| `jcmd PID Thread.dump_to_file` | Text/JSON thread dump including platform and virtual threads | Inspecting virtual threads or tool-based analysis |
| `jstack PID` | Prints JVM thread stack traces | Alternative traditional dump method |
| `kill -QUIT PID` on Linux | Requests the JVM to print a thread dump to standard output/log | When `jcmd` cannot attach and the log destination is known |
| `ThreadMXBean` | Captures thread info from within the application | Monitoring or diagnostics embedded in code |
| `JFR` | Records JVM events over time | Investigating intermittent issues, thread scheduling, and prolonged contention |

`jcmd` is Oracle's recommended choice for many JVM diagnostic tasks. Regardless of which tool you use, verify the right process and protect the output files.

## 17. Using ThreadMXBean for in-application diagnostics

If you want to integrate thread observability into an internal endpoint or monitoring tool, the Java Management API provides `ThreadMXBean`.

Example reading thread info and checking for deadlocks:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public class ThreadMonitor {
    public static void main(String[] args) {
        ThreadMXBean bean =
                ManagementFactory.getThreadMXBean();

        ThreadInfo[] threads =
                bean.dumpAllThreads(true, true);

        for (ThreadInfo info : threads) {
            System.out.println(
                    info.getThreadName() + " : " + info.getThreadState());
        }

        long[] deadlocked = bean.findDeadlockedThreads();
        System.out.println(
                "Deadlocked threads: "
                + (deadlocked == null ? 0 : deadlocked.length));
    }
}
```

Compile and run:

```sh
javac ThreadMonitor.java
java ThreadMonitor
```

The output depends on the process's threads; there is no fixed count. `dumpAllThreads(true, true)` requests information about held monitors and synchronizers if supported by the JVM. `findDeadlockedThreads()` finds deadlock cycles involving monitors or ownable synchronizers that the implementation can detect.

This is an example of the management API, not a replacement for all capabilities of `jcmd`. When exposing this data through an application, restrict access because thread names and stack traces can reveal internal structure.

## 18. When should you use Java Flight Recorder?

A thread dump provides a snapshot at a single point in time. If a bug occurs intermittently or lasts only a few milliseconds, a few dumps may miss the root cause.

Java Flight Recorder records events over time, which can help investigate:

- Thread start/end.
- Thread park and unpark.
- Monitor enter/contention.
- CPU sampling and execution samples.
- Virtual thread lifecycle/pinning events on supported JDKs.
- Related GC, allocation, and I/O events.

You can check running recordings:

```sh
jcmd 24680 JFR.check
```

Start a time-bounded recording:

```sh
jcmd 24680 JFR.start name=ThreadInvestigation settings=profile duration=2m filename=thread-investigation.jfr
```

Once complete, open the file with Java Mission Control or use `jfr print` to view relevant events. The `profile` configuration collects more data than `default` and has higher overhead; use it only for a duration suited to your investigation goal.

JFR is suited for understanding behavior over time; thread dumps are suited for inspecting stacks and locks at a specific moment. The two data sources complement each other.

## 19. Common errors when running Thread commands

| Symptom | Common cause | Resolution |
|---|---|---|
| `Could not find process` | Wrong PID, process stopped, or tool cannot see the process | Run `jcmd -l` and re-identify the PID |
| `AttachNotSupportedException` | Attach mechanism disabled, process/container disallows attach, or unsupported runtime | Check JVM flags, container namespace, and OS permissions |
| JVM not visible in `jcmd -l` | JVM running in a separate container or under another user | Run in the target container/namespace and use the right account |
| `Operation not permitted` or access denied | Mismatched user/group or blocked by system policy | Use the correct operational account and check permissions |
| `Unknown diagnostic command` | Target JVM does not support the command or command name is wrong | Use `jcmd PID help` and `help Thread.print` |
| `-l`/`-e` option not recognized | Different JVM version or wrong option syntax | Check command help on the target JVM |
| Dump too large | Process has many threads or deep stacks | Save to a file, filter, and analyze by thread name/state |
| Expected virtual threads missing | Wrong dump type used or different runtime version | Use `Thread.dump_to_file` on JDK 21+ |
| No deadlock section | No deadlock at capture time or dump format lacks required info | Capture `Thread.print -l` and compare multiple snapshots |
| Application slows down during capture | Dump has impact proportional to thread count | Reduce frequency, limit count, and choose an appropriate time |
| Dump file not created | Path does not exist or JVM user lacks write permission | Use an absolute path with write permission and check disk space |
| Cannot distinguish idle pool threads from stuck threads | Looking only at state without reading stack/context | Correlate tasks, queues, lock owners, and multiple snapshots |

Do not conclude that the JVM is broken just because one attach command fails. Verify the PID, account, container namespace, runtime version, and command availability before switching collection methods.

## 20. Incident investigation workflow using Thread commands

When an application hangs or requests are slow:

1. Identify the time and symptoms: whether the entire application is unresponsive or only a single endpoint.
2. Find the right PID using `jcmd -l` or OS tools.
3. Check available commands with `jcmd PID help Thread.print`.
4. Capture the first dump using `Thread.print -l`.
5. Save the file with a timestamp and JDK version info.
6. Look for threads in `BLOCKED`, repeated stack traces, lock owners, and deadlock reports.
7. Capture one or two more dumps a few seconds apart to confirm persistent states.
8. If the application uses many virtual threads, also capture `Thread.dump_to_file` in text/JSON format.
9. If the issue is intermittent, consider JFR to collect events over time.
10. Correlate with logs, request IDs, thread pool metrics, and CPU/memory metrics.
11. Identify the code or resource causing the wait.
12. Fix the root cause, add a reproducing test, and verify with data after the change.

In incident reports, note the JDK version, PID, capture timestamp, command used, and where the dump is stored. Do not post thread dumps publicly because stack traces can contain internal class names, packages, endpoints, and deployment details.

## 21. Storing and sharing thread dumps safely

Thread dumps do not usually contain local variable values like a debugger, but they can still expose:

- Internal class, package, and method names.
- Code or library paths.
- Thread names containing tenant, request, or job identifiers.
- Hostnames, endpoints, or service names in stack traces.
- Executor structure, frameworks, and deployment architecture.

Therefore:

- Store dumps in a diagnostic directory with restricted access permissions.
- Use filenames containing the PID and timestamp to avoid overwriting.
- Do not attach full dumps to public issues.
- Redact sensitive data if sharing outside the organization.
- Delete temporary copies per retention policy after the investigation concludes.
- Record the command and JDK version so others can reproduce it.

## 22. Checklist

- [ ] Identified the correct JVM PID and environment/container.
- [ ] Used the correct OS account to attach.
- [ ] Checked `jcmd PID help Thread.print` to confirm syntax.
- [ ] Captured a basic dump with `Thread.print`.
- [ ] Used `-l` when lock analysis is needed.
- [ ] Used `-e` when extended thread information is needed.
- [ ] Understood `RUNNABLE`, `BLOCKED`, `WAITING`, and `TIMED_WAITING` states.
- [ ] Traced lock owners and waiters instead of looking at only a single thread.
- [ ] Captured multiple snapshots if needed to confirm persistent states.
- [ ] Used `Thread.dump_to_file` on JDK 21+ when virtual thread inspection is needed.
- [ ] Considered JFR for intermittent issues.
- [ ] Saved dumps with timestamps and protected access permissions.
- [ ] Correlated findings with logs, metrics, and application code.

## 23. References

- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 21 Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java 21 Core Libraries — Virtual Threads, Viewing Virtual Threads in jcmd Thread Dumps: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Java SE 21 API — `java.lang.management.ThreadMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html

`Thread.print` is the core command for capturing stack traces and investigating thread states in a running JVM. Use `-l` when you need lock details, `-e` when you need extended information, and `Thread.dump_to_file` on JDK 21+ when you need an inventory of platform/virtual threads. Combine multiple snapshots, JFR, and application logs to find the root cause instead of drawing conclusions from a single isolated state.