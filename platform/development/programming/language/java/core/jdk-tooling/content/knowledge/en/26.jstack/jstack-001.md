# Using the jstack Command to Analyze Java Thread Dumps

## 1. What is jstack used for?

`jstack` is a command-line tool included with the JDK, used to obtain thread dumps from a running Java Virtual Machine (JVM). A thread dump is a snapshot of thread states at a point in time, including thread names, states, stack traces, and optional lock information.

Thread dumps help investigate scenarios such as:

- An application responding slowly or hanging.
- Requests waiting for a long time, thread pool exhaustion, or workers no longer processing additional tasks.
- Multiple threads in the `BLOCKED` state due to monitor contention.
- Threads remaining in `WAITING` or `TIMED_WAITING` longer than expected.
- Deadlocks between threads.
- Threads looping in a section of code or frequently waiting on I/O.
- Needing to compare thread states before and after an incident.

`jstack` does not modify application state, does not terminate threads, and is not a CPU profiler. The tool captures data for operators to analyze. For short-lived issues, a single thread dump may miss the root cause; collect multiple snapshots a few seconds apart and correlate them with logs, metrics, JFR, or a profiler.

## 2. Syntax and options

JDK 24 syntax:

~~~bash
jstack [-l][-e] <pid>
~~~

Where `pid` is the process ID of the running JVM. The tool help lists the following options:

| Option | Purpose |
|---|---|
| `-l` | Long listing: prints additional information about locks, monitors, and synchronizers. |
| `-e` | Extended listing: prints additional extended information about threads. |
| `-h`, `-?`, `-help` | Displays help. |

Examples:

~~~bash
jstack 18420
jstack -l 18420
jstack -e 18420
jstack -h
~~~

- Run the command without options when you only need basic stack traces.
- Use `-l` when investigating lock contention or deadlocks.
- Use `-e` when you need additional thread information, such as CPU time, elapsed time, allocated bytes, or the number of defined classes on supported JDKs.

The list of options depends on the JDK version. In the verified JDK 24.0.2 environment, `jstack -h` lists `-l` and `-e`. Some older guides may mention `-F` or `-m`; do not assume those options exist on your JDK. Always check `jstack -h` before adding commands to a runbook.

## 3. Finding the PID of a Java application

Before taking a thread dump, find the right JVM:

~~~bash
jcmd -l
~~~

Example output:

~~~text
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

The number at the beginning of each line is the PID. If multiple Java applications are running, check the main class or command line to select the right process.

You can also use OS tools to find the PID:

~~~bash
# Linux
ps -ef | grep java

# Windows PowerShell
Get-CimInstance Win32_Process -Filter "Name = 'java.exe'" |
    Select-Object ProcessId, CommandLine
~~~

Prefer targeting a specific PID rather than picking a Java process at random. Record the PID, application name, host/container, and collection timestamp so snapshots can be correlated accurately.

## 4. Requirements for connecting to the target JVM

`jstack` attaches to a JVM on the same machine. Common requirements include:

- Run the command on the host where the target JVM is running, or in a container environment that can see the JVM's PID.
- The user running `jstack` usually must match the user that started the JVM.
- The JVM must allow the Attach mechanism; if attach is disabled or the environment blocks attach, the tool may fail to connect.
- Use the tool from a JDK matching the application's runtime to minimize version differences.
- The target JVM must be alive and able to respond to diagnostic requests.

`jstack` is not a remote connection tool over an IP address. For a JVM on another machine, access the appropriate host or use the remote diagnostic mechanism deployed by your organization.

In containers, the PID inside the container may differ from the PID seen from the host. Run the tool in the appropriate PID namespace or use the corresponding host PID while ensuring the required permissions.

## 5. Taking a basic thread dump

Once you have the PID, run:

~~~bash
jstack 18420
~~~

The output typically begins with a timestamp and JVM information:

~~~text
2026-11-10 19:03:25
Full thread dump OpenJDK 64-Bit Server VM (24.0.2+12 mixed mode, sharing):
~~~

Next is the list of threads, each consisting of a header and a stack trace. An illustrative snippet:

~~~text
"main" #3 prio=5 os_prio=0 cpu=46.88ms elapsed=0.96s tid=0x... nid=55784
   java.lang.Thread.State: WAITING (on object monitor)
        at java.lang.Object.wait0(Native Method)
        at java.lang.Object.wait(Object.java:389)
        at java.lang.Thread.join(Thread.java:1860)
~~~

Memory addresses, PIDs, thread IDs, CPU times, and stack line numbers vary across runs. Do not treat these values as fixed outputs in test scripts.

To save the output to a file:

~~~bash
jstack 18420 > thread-dump.txt
~~~

In PowerShell:

~~~powershell
jstack 18420 | Out-File -Encoding utf8 thread-dump.txt
~~~

Thread dumps are diagnostic data; store them in a directory with appropriate access permissions and name files with the application name, PID, and collection timestamp.

## 6. Capturing lock information with the -l option

When you need to see which thread holds a lock and which thread is waiting for a lock, use:

~~~bash
jstack -l 18420
~~~

The output may contain lines such as:

~~~text
"worker-A" #37 prio=5 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderService.update(OrderService.java:42)
        - waiting to lock <0x000000011f019408> (a java.lang.Object)
        - locked <0x000000011f0193f8> (a java.lang.Object)
~~~

Meaning:

- `waiting to lock`: the thread is waiting to acquire the monitor at the listed address.
- `locked`: the thread owns the corresponding monitor.
- Monitor addresses help link waiting and ownership information across threads within the same dump.

For `ReentrantLock` or synchronizers based on `java.util.concurrent`, additional information about ownable synchronizers may appear in the long listing. Read the lock section together with the stack trace to identify which code holds the lock and which code is waiting.

Do not conclude there is a deadlock simply because a single thread is `BLOCKED`. A thread may wait briefly for a lock and then proceed. Examine the ownership/waiting chain across multiple threads and check whether the state persists across multiple snapshots.

## 7. Capturing extended thread information with the -e option

Run:

~~~bash
jstack -e 18420
~~~

In JDK 24, extended listing may add fields such as:

- `cpu`: recorded CPU time for the thread.
- `elapsed`: how long the thread has existed.
- `allocated`: amount of memory allocated by the thread.
- `defined_classes`: number of classes defined by the thread.
- `tid` and `nid`: thread identifiers in the JVM and operating system.

Example header:

~~~text
"demo-sleeping" #35 [63112] daemon prio=5 os_prio=0
  cpu=0.00ms elapsed=1.27s allocated=1296B defined_classes=2
  tid=0x... nid=63112 waiting on condition
~~~

Fields and formatting may vary by JDK. CPU time in a single snapshot does not replace a CPU profiler; compare multiple snapshots or combine with metrics to identify threads continuously consuming CPU.

## 8. Understanding thread states

Java defines thread states in `java.lang.Thread.State`. A thread dump typically displays the state after the header:

~~~text
java.lang.Thread.State: RUNNABLE
~~~

Main states:

| State | Meaning | Common indicators |
|---|---|---|
| `NEW` | The thread has been created but `start()` has not been called yet. | Usually does not appear as a running thread in the dump. |
| `RUNNABLE` | The thread is executing in the JVM or ready to be scheduled CPU time by the OS. | May be executing code, handling a native call, or waiting on OS resources. |
| `BLOCKED` | The thread is waiting to acquire an intrinsic monitor to enter or re-enter a `synchronized` block/method. | Contains a `waiting to lock` line. |
| `WAITING` | The thread is waiting indefinitely for another thread to perform an action. | `Object.wait()`, `Thread.join()`, or `LockSupport.park()` without a timeout. |
| `TIMED_WAITING` | The thread is waiting for a bounded amount of time. | `Thread.sleep()`, `wait(timeout)`, `join(timeout)`, or `parkNanos()`. |
| `TERMINATED` | The thread has finished execution. | Usually no longer present in the list of live threads. |

Important notes:

- `RUNNABLE` does not necessarily mean the CPU is actively executing the thread at every instant. The thread may be waiting on I/O or native resources.
- `BLOCKED` is specifically waiting for a monitor; it is distinct from `WAITING` caused by `Object.wait()` or `LockSupport.park()`.
- A thread calling `Object.wait()` releases the monitor it holds while waiting; when awakened, it must re-acquire the monitor before continuing.
- `Thread.sleep()` does not release any intrinsic monitors held by the thread.
- A `WAITING` thread can be completely normal, such as a worker waiting on a queue for tasks.

Combine the thread state with its stack trace, lock owner, and observation duration. Do not judge application health solely by the count of threads in a particular state.

## 9. Reading a thread's stack trace

A stack trace in a thread dump shows the method call chain from the current frame back up to the callers.

Example:

~~~text
"pool-1-thread-3" #28 prio=5 ...
   java.lang.Thread.State: RUNNABLE
        at com.example.service.OrderService.calculate(OrderService.java:85)
        at com.example.service.OrderService.process(OrderService.java:51)
        at com.example.worker.OrderWorker.run(OrderWorker.java:29)
        at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1144)
        at java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:642)
        at java.lang.Thread.run(Thread.java:1583)
~~~

Read from top to bottom:

1. The first line is the current frame or the point where the thread is currently paused.
2. Subsequent frames show the call path that brought the thread to that point.
3. Application code frames help identify the service, method, and source line to investigate.
4. JDK or framework frames indicate which executor, queue, lock, socket, or runtime API the thread is in.

Some frames may display `Native Method` or omit source line numbers if the class lacks debug line information.

When multiple threads in an executor share the same stack, check whether they are all waiting on a queue, executing the same method, or blocked on the same lock. This helps distinguish idle workers from stuck workers.

## 10. Detecting deadlocks

A deadlock occurs when threads hold resources that other threads need, forming a waiting cycle that cannot make progress on its own.

Example:

- Thread A holds lock A and waits for lock B.
- Thread B holds lock B and waits for lock A.
- A cannot acquire B because B holds it.
- B cannot acquire A because A holds it.

When the JVM detects a monitor deadlock, the thread dump may print:

~~~text
Found one Java-level deadlock:
=============================

"demo-deadlock-A":
  waiting to lock monitor ...,
  which is held by "demo-deadlock-B"

"demo-deadlock-B":
  waiting to lock monitor ...,
  which is held by "demo-deadlock-A"
~~~

This is a clear indicator of a lock cycle. The following section usually lists the Java stack information for each thread in the deadlock, pointing to the source lines that are waiting and the locks being held.

The absence of `Found one Java-level deadlock` does not prove the system is free of all forms of deadlock. A thread dump may not detect logical cycles across databases, networks, queues, callbacks, or application protocols, or the issue may not have occurred at the moment the snapshot was taken.

## 11. Java 17 deadlock example for practice

Create `JstackDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class JstackDemo {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();
    private static final Object WAIT_LOCK = new Object();

    public static void main(String[] args) throws Exception {
        Thread sleeper = new Thread(() -> {
            while (true) {
                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "demo-sleeping");
        sleeper.setDaemon(true);
        sleeper.start();

        Thread waiter = new Thread(() -> {
            synchronized (WAIT_LOCK) {
                try {
                    WAIT_LOCK.wait();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-waiting");
        waiter.setDaemon(true);
        waiter.start();

        CountDownLatch bothOwnLocks = new CountDownLatch(2);

        Thread first = new Thread(() -> {
            synchronized (LOCK_A) {
                bothOwnLocks.countDown();
                try {
                    bothOwnLocks.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                synchronized (LOCK_B) {
                    System.out.println("first acquired both locks");
                }
            }
        }, "demo-deadlock-A");

        Thread second = new Thread(() -> {
            synchronized (LOCK_B) {
                bothOwnLocks.countDown();
                try {
                    bothOwnLocks.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                synchronized (LOCK_A) {
                    System.out.println("second acquired both locks");
                }
            }
        }, "demo-deadlock-B");

        first.start();
        second.start();
        System.out.println("JstackDemo ready");
        Thread.currentThread().join();
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 JstackDemo.java
java JstackDemo
~~~

Stdout before taking the dump:

~~~text
JstackDemo ready
~~~

The program intentionally creates a deadlock between two non-daemon threads so the JVM stays running. The `demo-sleeping` thread is in `TIMED_WAITING`, `demo-waiting` is in `WAITING` due to `Object.wait()`, and the two deadlocked threads are in `BLOCKED`.

In another terminal, find the PID:

~~~bash
jcmd -l
~~~

Assuming the PID is `18420`, take the dumps:

~~~bash
jstack 18420
jstack -l 18420
jstack -e 18420
~~~

In dumps verified on JDK 24.0.2, the JVM reports `Found one Java-level deadlock` and indicates that thread A is waiting for the monitor held by B, while B is waiting for the monitor held by A. Actual lock addresses, PIDs, and source line numbers will vary per run.

After practicing, stop the sample program by terminating the process in the terminal running it or using OS tools. Do not use this deadlock program in production environments.

## 12. Analyzing a dump to find the root cause

A practical dump-reading workflow:

1. Verify the header has the expected JVM, version, and timestamp.
2. Search for `Found one Java-level deadlock` if a deadlock is suspected.
3. Find `BLOCKED` threads and match `waiting to lock` with the thread that has `locked` the same monitor.
4. Group threads by name, pool, or identical stack traces.
5. Check whether `RUNNABLE` threads are all paused at the same method, loop, or native call.
6. Check whether `WAITING` threads are legitimately waiting on a queue, future, latch, or condition.
7. Compare subsequent dumps to determine whether states persist or change.
8. Correlate with logs, request latency, CPU, GC, database, and network metrics.

For example, if many threads from the same request pool are `BLOCKED` at a `synchronized` line while another thread holds that monitor and its stack trace is inside a slow operation, that is a high-priority lead to investigate.

If many workers are `WAITING` at `LinkedBlockingQueue.take()`, they may simply be idle workers waiting for tasks. If all workers are waiting on an external service or a lock, check the dependency and wait times.

## 13. Collecting multiple thread dumps over time

A single snapshot shows the state at one instant. For hangs or high CPU issues, taking several snapshots a few seconds apart helps distinguish transient states from stuck ones.

Example on Linux/macOS:

~~~bash
PID=18420
jstack -l "$PID" > thread-1.txt
sleep 5
jstack -l "$PID" > thread-2.txt
sleep 5
jstack -l "$PID" > thread-3.txt
~~~

PowerShell example:

~~~powershell
$targetPid = 18420
1..3 | ForEach-Object {
    $file = "thread-$_.txt"
    jstack -l $targetPid | Out-File -Encoding utf8 $file
    Start-Sleep -Seconds 5
}
~~~

Comparison:

- Threads remaining at the exact same stack frame across multiple dumps may be waiting for a long time or stuck.
- `RUNNABLE` threads whose stacks change continuously may be making normal progress.
- Multiple threads waiting on the same monitor across several dumps indicate prolonged lock contention.
- Deadlocked threads typically preserve their lock waiting/holding relationship until intervention.

Do not collect dumps too frequently or without limiting the number of files. Thread dumps can be large on JVMs with thousands of threads; include timestamps in filenames and retain only the needed snapshots.

## 14. Using jcmd as an alternative

`jcmd` can capture thread dumps from a running JVM without invoking `jstack` directly.

Print a thread dump to the terminal:

~~~bash
jcmd 18420 Thread.print
~~~

Include lock information:

~~~bash
jcmd 18420 Thread.print -l
~~~

Include extended thread information:

~~~bash
jcmd 18420 Thread.print -e
~~~

In JDK 24, `Thread.print` supports `-l` and `-e` for the same purposes as the `jstack` options.

You can save a thread dump to a file in plain text or JSON format using `Thread.dump_to_file`:

~~~bash
jcmd 18420 Thread.dump_to_file -format=plain thread-dump.txt
jcmd 18420 Thread.dump_to_file -format=json thread-dump.json
~~~

This command has an `-overwrite` option if you need to allow overwriting an existing file; by default, it does not overwrite. Run `jcmd 18420 help Thread.dump_to_file` on the target JVM to confirm the syntax.

Use `jstack` for quick, familiar terminal operations. Use `jcmd` when operational procedures standardize on diagnostic commands or when you need JSON output for processing by other tools.

## 15. Distinguishing jstack from JFR and heap dumps

JVM diagnostic tools provide different types of data:

| Tool | Primary data | When to use |
|---|---|---|
| `jstack` | Thread state, stack traces, locks, and deadlocks at the time of capture. | Investigating hangs, lock contention, and deadlocks. |
| `JFR` | Sequence of runtime events over time. | Investigating latency, GC, allocation, I/O, and thread activity. |
| Heap dump | Object graph and heap state at a point in time. | Investigating memory leaks, retained objects, and abnormal heap growth. |
| CPU profiler | Samples or CPU time per method. | Finding CPU-intensive methods. |

A thread dump does not show which objects are occupying the heap, nor is it complete proof of CPU hot paths. Choose the tool based on the symptoms; you can combine thread dumps with JFR to understand both the state at capture time and the preceding event history.

## 16. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `jstack` command not found | JDK `bin` is not in `PATH`. | Check `JAVA_HOME` and invoke the executable inside the `bin` directory. |
| PID not found | Incorrect PID or the process has exited. | Re-run `jcmd -l` or inspect processes using OS tools. |
| `AttachNotSupportedException` | JVM disabled the Attach mechanism or the environment blocks attach. | Check JVM options, user, and container/host permissions. |
| File write error | Target directory does not exist or lacks write permission. | Create the directory and check filesystem permissions. |
| Thread dump lacks lock details | Run without `-l`. | Re-capture the dump with `jstack -l PID`. |
| No deadlock shown in dump | Deadlock has not occurred yet, is not a Java monitor deadlock, or the cycle is outside detection scope. | Capture multiple dumps, inspect lock chains, and check database, queue, network, or application protocols. |
| Many `RUNNABLE` threads | Threads may be executing, waiting on native I/O, or scheduled by the OS. | Compare multiple dumps and correlate with CPU metrics/JFR. |
| Many `WAITING` threads | Workers may be waiting on a queue, future, latch, or condition. | Read stack frames and identify the wake-up condition. |
| Option from older guides unrecognized | Option does not exist in the current JDK version. | Run `jstack -h` to see actual supported options. |
| Dump file is too large | JVM has many threads or deep stack traces. | Save to a directory with sufficient disk space, collect a reasonable number of snapshots, and filter during analysis. |
| Thread dumps differ across captures | Threads are changing state or the application continues processing. | Record timestamps for each dump and compare thread names, stacks, states, and locks. |

## 17. Production investigation checklist

- Identified the correct JVM, PID, host/container, and JDK version.
- Verified the user has permission to attach to the process.
- Saved at least one basic dump and one dump with lock details when needed.
- Used `-e` if extended thread information is needed and supported by the JDK.
- Inspected thread states together with stack traces rather than drawing conclusions from a single state.
- Checked for `Found one Java-level deadlock` and lock owners if present.
- Collected additional snapshots a few seconds apart when needed to confirm persistent states.
- Correlated with logs, CPU, latency, GC, and dependency metrics.
- Recorded the timestamp, PID, and application name alongside each dump file.
- Protected thread dump files because they can expose packages, classes, methods, and internal structure.
- Terminated any sample processes or test recordings after practicing.
- Documented conclusions and evidence from specific stack frames/locks.

## 18. References

- [The jstack Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstack.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Thread.State — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.State.html)

`jstack` provides thread dumps to observe the states, stack traces, and locks of a running JVM. Start with the exact PID, use `-l` when investigating locks, use `-e` when you need extended thread information, then compare multiple snapshots and correlate with logs and metrics to pinpoint the cause of hangs, contention, or deadlocks.
