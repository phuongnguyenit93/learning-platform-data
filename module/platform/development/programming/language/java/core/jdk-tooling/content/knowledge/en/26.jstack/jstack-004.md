# Stack Traces with jstack

**`jstack`** is a JDK diagnostic tool used to print stack traces of threads in a running Java Virtual Machine (JVM). The output is commonly called a **thread dump**. It shows which threads are running, waiting, or blocked, which locks they hold, and which methods they are executing at the time of capture.

A thread dump is a snapshot of the JVM's state, which is very useful when investigating hung applications, slow responses, thread pool bottlenecks, lock contention, or deadlocks. In modern JDKs, Oracle recommends using `jcmd` with the `Thread.print` command for routine diagnostics; `jstack` may still appear in operational runbooks and older documentation, but it is marked as experimental/unsupported.

## 1. How Do a Stack Trace and a Thread Dump Differ?

A **stack trace** describes the chain of method calls for a single thread at a point in time. Each frame typically shows the class, method, and source code location if available.

Example:

```text
at com.example.service.OrderService.load(OrderService.java:42)
at com.example.web.OrderController.get(OrderController.java:18)
at java.base/java.lang.Thread.run(Thread.java:1583)
```

You can read it from top to bottom: the thread is currently at the first frame, and the frames below it are the calls that led to the current location.

A **thread dump** is a collection of stack traces for multiple threads in the same JVM, typically including:

- Thread name and state.
- Thread ID and native thread ID.
- Stack frames for each thread.
- Monitors or synchronizers that the thread holds or is waiting for.
- Deadlock detection information, if any.

A single stack trace helps locate the execution point of one thread. A thread dump provides a complete view of the relationships between threads and locks in the process.

## 2. When Should You Take a Thread Dump?

A thread dump is useful when you need to answer questions such as:

- Which thread is consuming CPU or looping in a piece of code?
- Why is a request not completing?
- Is a thread waiting on a database, network, queue, or lock?
- Are any threads blocked trying to acquire an intrinsic monitor?
- Is there a deadlock between two or more threads?
- Has a thread pool run out of workers, or are too many threads waiting?
- Is the application stuck at the same location across multiple samples?

A single thread dump only shows the state at one moment in time. To distinguish a normal transient wait from a thread that is stuck for a long time, you typically need to take multiple dumps a few seconds apart and compare their stacks, states, and locks.

## 3. Finding the JVM PID

Before invoking `jstack`, identify the correct Java process.

List observable JVMs:

```bash
jps -l
```

Sample output:

```text
18420 com.example.app.Main
29116 org.apache.catalina.startup.Bootstrap
```

In this example, `18420` is the PID/LVMID of the application to inspect. PIDs change on each run; do not copy the sample PID into a real environment.

If running inside a container, the PID seen from the host may differ from the PID inside the container's PID namespace. You may need to run `jps` or `jstack` inside the container, under the same user account that owns the JVM.

## 4. jstack Syntax and Options

Syntax on modern JDKs:

```text
jstack [-l] [-e] <pid>
```

Where:

- `pid` is the process ID of the target JVM.
- `-l` prints additional lock information, including ownable synchronizers and `java.util.concurrent` locks.
- `-e` prints extended thread information on JDK versions that support this option.
- `-h` or `-help` displays help.

Check the options for your installed JDK:

```bash
jstack -h
```

On JDK 24 tested for this lesson, the help output shows:

```text
Usage:
    jstack [-l][-e] <pid>

Options:
    -l  long listing. Prints additional information about locks
    -e  extended listing. Prints additional information about threads
    -? -h --help -help to print this help message
```

Do not assume every version or JVM vendor shares the exact same options. Always check the help output of the target JDK and JVM.

## 5. Taking a Basic Thread Dump

Use the JVM's PID:

```bash
jstack 18420
```

The command prints the stack traces of Java threads and internal VM threads that the tool can collect. The JVM continues running after the dump is printed; the command does not stop the application.

You can save the output to a file for analysis:

```bash
jstack 18420 > thread-dump-1.txt
```

In PowerShell:

```powershell
jstack 18420 | Out-File -Encoding utf8 thread-dump-1.txt
```

If you need more detailed lock information:

```bash
jstack -l 18420 > thread-dump-locks.txt
```

If you need extended thread information:

```bash
jstack -e 18420 > thread-dump-extended.txt
```

Dump files may contain internal class names, packages, source paths, and operational details. Protect the files before sharing them.

## 6. Reading the Thread Dump Structure

A thread entry typically consists of a header, state, and stack trace.

Illustrative example:

```text
"worker-1" #35 prio=5 os_prio=0 tid=0x000001f5b47a5950 nid=14944 waiting on condition
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.worker.Poller.run(Poller.java:28)
```

Common fields:

| Field | Meaning |
| --- | --- |
| `"worker-1"` | Thread name |
| `#35` | Java thread ID |
| `prio=5` | Java thread priority |
| `os_prio=0` | Operating system-level priority, if available |
| `tid=...` | Address/identifier of the thread structure in the VM |
| `nid=14944` | Native thread ID |
| `waiting on condition` | Brief VM-level description of the wait state |
| `Thread.State` | Java state of the thread |
| `at ...` lines | Stack frames, tracing backward from the current location through method calls |

The header format varies across JVM versions. Newer JDKs may add elapsed time, CPU time, allocated bytes, or extended thread fields. Do not write parsers that tightly depend on a single fixed thread dump format.

## 7. Meaning of Thread States

Java defines thread states in `Thread.State`. The states commonly seen in dumps are:

| State | Meaning | How to interpret during investigation |
| --- | --- | --- |
| `RUNNABLE` | The thread is runnable in the JVM; it may be executing or waiting for an OS resource | Check the stack and CPU usage; it does not necessarily mean it is actively using CPU |
| `BLOCKED` | The thread is waiting to acquire an intrinsic monitor to enter or re-enter a synchronized block/method | Find the thread currently holding that monitor |
| `WAITING` | The thread is waiting indefinitely for an action from another thread | Check for `Object.wait`, `Thread.join`, or `LockSupport.park` |
| `TIMED_WAITING` | The thread is waiting for a specified period | Check for `Thread.sleep`, `wait(timeout)`, `join(timeout)`, or a timed park |
| `NEW` | The thread has been created but not yet started | Usually does not appear as an active thread in a dump |
| `TERMINATED` | The thread has finished executing | No longer running; usually does not appear in the list of active threads |

Key points:

- `RUNNABLE` does not prove a thread is consuming CPU. The thread may be in native I/O or waiting on an underlying resource.
- `BLOCKED` is typically associated with the intrinsic monitor of `synchronized`.
- `WAITING` is not automatically an error. A worker waiting on an empty queue or a thread waiting for a condition can be normal behavior.
- `TIMED_WAITING` caused by `Thread.sleep` can be completely normal.
- Always read the stack trace and lock state together rather than drawing conclusions from the state label alone.

## 8. Reading Stack Frames and Locating Code

A stack frame typically has the form:

```text
at package.ClassName.methodName(FileName.java:123)
```

Example:

```text
at com.example.payment.PaymentService.charge(PaymentService.java:87)
at com.example.web.PaymentController.submit(PaymentController.java:34)
```

How to analyze:

1. Read the top frame to see where the thread currently is.
2. Follow the frames below it to trace the call chain.
3. Find the first frame belonging to your application code.
4. Open the corresponding source file and line.
5. Examine the thread state and locks around that frame to understand why the thread stopped there.

Some frames may not have a source line:

- `Native Method`: executing in a native method or JNI.
- `Unknown Source`: the JVM does not have source line information.
- `Generated/lambda frame`: code automatically generated by the compiler or runtime.
- `Reflection` or framework frame: calls passing through reflection, proxies, or frameworks before reaching application code.

Do not ignore library frames. For example, a thread might be waiting in `SocketInputStream.read` or a JDBC driver; the application frames below it help identify which request triggered that I/O operation.

## 9. Distinguishing BLOCKED, WAITING, and RUNNABLE in Practice

### BLOCKED: waiting for an intrinsic monitor

Example:

```text
"request-12" #48
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.cache.Cache.refresh(Cache.java:71)
        - waiting to lock <0x000000011f019920> (a java.lang.Object)
```

The thread is waiting for the monitor at the corresponding address. Use the `- locked` information in other threads to find the monitor owner.

### WAITING: waiting for a condition

Example:

```text
"queue-worker" #52
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
        at java.util.concurrent.LinkedBlockingQueue.take(LinkedBlockingQueue.java:...)
```

The worker may be waiting for a new item in the queue. This is usually normal when there is no work.

### TIMED_WAITING: waiting with a timeout

Example:

```text
"heartbeat" #53
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.monitor.Heartbeat.run(Heartbeat.java:25)
```

The thread is sleeping until the next cycle. If a thread should respond immediately but is repeatedly sleeping or waiting on a long timeout, check the logic and timing configuration.

### RUNNABLE: executing or active in native code

Example:

```text
"worker-cpu" #54
   java.lang.Thread.State: RUNNABLE
        at com.example.math.Matrix.multiply(Matrix.java:112)
        at com.example.service.Analytics.run(Analytics.java:58)
```

If the same stack appears across multiple dumps and the thread's CPU usage is high, there may be a CPU-intensive loop. If the stack is in native I/O, the `RUNNABLE` state does not necessarily mean the thread is actively computing.

## 10. Reading Monitor and Lock Information with jstack -l

The `-l` option adds lock information, including ownable synchronizers that a basic dump may not display in full.

Example:

```text
"worker-A" #35
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.LockDemo.first(LockDemo.java:40)
        - waiting to lock <0x000000011f019920> (a java.lang.Object)
        - locked <0x000000011f019910> (a java.lang.Object)
```

How to read this:

- `waiting to lock`: the thread is waiting to acquire the monitor at the displayed address.
- `locked`: the thread currently holds the monitor.
- The object address links the waiting thread to the thread holding the same monitor elsewhere in the dump.
- The class name after the address indicates the type of object used as the lock.

With `java.util.concurrent.locks`, such as `ReentrantLock`, ownable synchronizer information helps identify which thread holds the synchronizer and which threads are waiting. Use `jstack -l` or `jcmd <pid> Thread.print -l` when you need this detail.

Do not conclude there is a deadlock simply because a thread shows `waiting to lock`. You must identify a dependency cycle: A waits for a lock held by B while B waits for a lock held by A, or a longer cycle.

## 11. Detecting Deadlocks

A deadlock occurs when a group of threads wait on resources in a cycle and none of them can proceed.

Example:

- Thread A holds lock X and waits for lock Y.
- Thread B holds lock Y and waits for lock X.
- A cannot acquire Y until B releases Y.
- B cannot acquire X until A releases X.

Run:

```bash
jstack -l 18420
```

If HotSpot detects a Java-level deadlock, the end of the output may contain:

```text
Found one Java-level deadlock:
"left-worker":
  waiting to lock monitor ... (object ..., a java.lang.Object),
  which is held by "right-worker"
"right-worker":
  waiting to lock monitor ... (object ..., a java.lang.Object),
  which is held by "left-worker"
```

This is a clear indicator of a lock cycle. For more complex deadlocks, the report may list multiple threads and monitors involved in the cycle.

The absence of a deadlock report does not prove the application is not hung. The cause could be I/O, network, queues, external services, starvation, or a form of waiting not detected as a Java-level monitor deadlock.

## 12. Java 17 Hands-On Example: Creating an Intentional Deadlock

The example below creates two threads, each holding one lock and waiting for the other. The goal is to observe thread states and the deadlock report. Do not run this example in a production application.

Create the directory structure:

```text
project/
  src/
    com/example/diagnostics/
      DeadlockTarget.java
  out/
```

File **`src/com/example/diagnostics/DeadlockTarget.java`**:

```java
package com.example.diagnostics;

import java.util.concurrent.CountDownLatch;

public final class DeadlockTarget {
    private static final Object FIRST = new Object();
    private static final Object SECOND = new Object();
    private static final CountDownLatch READY = new CountDownLatch(2);

    private DeadlockTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        Thread left = new Thread(
            () -> lock(FIRST, SECOND),
            "left-worker"
        );
        Thread right = new Thread(
            () -> lock(SECOND, FIRST),
            "right-worker"
        );

        left.start();
        right.start();

        System.out.println("PID=" + ProcessHandle.current().pid());
        Thread.sleep(120_000);
    }

    private static void lock(Object first, Object second) {
        synchronized (first) {
            READY.countDown();

            try {
                READY.await();
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return;
            }

            synchronized (second) {
                System.out.println("unreachable");
            }
        }
    }
}
```

The two workers acquire locks in opposite orders. `CountDownLatch` ensures both have acquired their first lock before attempting to acquire the second lock.

Compile:

```bash
javac --release 17 -d out src/com/example/diagnostics/DeadlockTarget.java
```

Run:

```bash
java -cp out com.example.diagnostics.DeadlockTarget
```

Initial output:

```text
PID=19092
```

The PID shown here is just an example from one run; use the actual PID printed by the program.

Open a second terminal:

```bash
jstack -l 19092
```

The key output looks like:

```text
"left-worker" #35
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.diagnostics.DeadlockTarget.lock(DeadlockTarget.java:...)
        - waiting to lock <0x...> (a java.lang.Object)
        - locked <0x...> (a java.lang.Object)

"right-worker" #36
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.diagnostics.DeadlockTarget.lock(DeadlockTarget.java:...)
        - waiting to lock <0x...> (a java.lang.Object)
        - locked <0x...> (a java.lang.Object)

Found one Java-level deadlock:
"left-worker":
  waiting to lock monitor ... which is held by "right-worker"
"right-worker":
  waiting to lock monitor ... which is held by "left-worker"
```

Monitor addresses, thread IDs, and line numbers may vary across compilations and runs. The key takeaway is that both workers are `BLOCKED`, each holding one object and waiting for the object held by the other.

Stop the test program with Ctrl+C in the terminal running the application. Taking a thread dump does not resolve a deadlock on its own.

## 13. Taking Multiple Thread Dumps to Find Persistent Issues

A thread can briefly be `WAITING` or `BLOCKED` without any error. To tell whether a state is persistent, take several dumps a few seconds apart.

Example on Linux/macOS:

```bash
jstack -l 18420 > dump-1.txt
sleep 5
jstack -l 18420 > dump-2.txt
sleep 5
jstack -l 18420 > dump-3.txt
```

PowerShell:

```powershell
jstack -l 18420 | Out-File -Encoding utf8 dump-1.txt
Start-Sleep -Seconds 5
jstack -l 18420 | Out-File -Encoding utf8 dump-2.txt
Start-Sleep -Seconds 5
jstack -l 18420 | Out-File -Encoding utf8 dump-3.txt
```

Compare:

- Does the thread keep the exact same stack trace across dumps?
- Is the thread always `BLOCKED` on the same monitor?
- Is the thread continuously waiting on the same queue or external call?
- Is a `RUNNABLE` thread repeating the same code path?
- Is the number of threads in the same state growing?
- Is the thread holding the lock making progress, or is it also waiting elsewhere?

Three identical dumps may indicate a prolonged hang, but you still need to correlate metrics, logs, CPU, and dependencies to determine the root cause.

Do not capture dumps in an overly tight loop. Large thread dumps can add overhead and generate unnecessary files.

## 14. Using jcmd Thread.print in Modern JDKs

Oracle recommends using `jcmd` instead of `jstack` for modern JVM diagnostics. `Thread.print` prints thread stack traces and supports options for lock and extended information.

Basic syntax:

```bash
jcmd 18420 Thread.print
```

Include lock information:

```bash
jcmd 18420 Thread.print -l
```

Include extended thread information:

```bash
jcmd 18420 Thread.print -e
```

Combine both:

```bash
jcmd 18420 Thread.print -l -e
```

Command help on the target JVM:

```bash
jcmd 18420 help Thread.print
```

On the tested JDK 24, the help output shows:

- Command: `Thread.print`.
- Description: print all threads with stacktraces.
- Impact: Medium, depending on the number of threads.
- `-l`: print `java.util.concurrent` locks.
- `-e`: print extended thread information.

`jcmd` uses the same local attach mechanism. Choose the right PID and the account running the JVM; check the target JVM's help output because command options can vary by version.

## 15. jstack vs. jhsdb jstack

Two different use cases:

| Tool | Input | Purpose |
| --- | --- | --- |
| `jstack <pid>` | Running JVM | Print a thread dump from a live process |
| `jcmd <pid> Thread.print` | Running JVM | Thread diagnostics using the recommended diagnostic command |
| `jhsdb jstack --exe ... --core ...` | Java executable and core dump | Analyze thread stacks after a JVM crash or when a core dump has been generated |

Core dump analysis example:

```bash
jhsdb jstack --exe /path/to/java --core /path/to/core
```

The executable path must match the JVM that produced the core dump. Core dump analysis requires matching files and environment; do not use `jstack`'s PID syntax as a substitute for postmortem analysis.

## 16. Attach Permissions and Common Errors

`jstack` needs to attach to the target JVM. Common requirements:

- The JVM must be a Java process compatible with the tool.
- The tool needs OS-level permissions to attach.
- It usually must run under the same user that owns the JVM or an account with equivalent privileges.
- The JVM may disable the Attach Mechanism via startup configuration.
- Containers, PID namespaces, sandboxes, or security policies may restrict attach.
- On Windows, the debugging/native tooling environment and matching runtime paths can affect dump capture.

Common errors:

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `Unable to open socket file` | Attach mechanism unavailable, wrong user, or different temp directory | Check the user, JVM options, and temp directory |
| `Access is denied` | Insufficient permissions to access the process | Use an authorized account and check policies |
| `No such process` | Wrong PID or the JVM has already exited | Re-run `jps -l` or check OS processes |
| `Not a Java process` | The PID points to a non-compatible or non-JVM process | Verify the PID before running |
| No deadlock report | No Java-level deadlock detected at the time of sampling | Check multiple dumps, I/O, queues, CPU, and external dependencies |
| Missing lock information | Used a basic dump or a command without lock details enabled | Use `jstack -l` or `jcmd Thread.print -l` |
| Process not visible in container | Different PID namespace or user | Run the tool inside the container or in the matching namespace |
| Thread dump too large | JVM has many threads or deep stacks | Redirect to a file, collect during controlled windows, and filter during analysis |

Do not attempt to bypass attach protections or run under another account without authorization.

## 17. Limitations and Operational Considerations

Thread dumps are very helpful, but they do not explain every incident:

- They are point-in-time snapshots, not continuous recordings.
- They do not show a thread's full history prior to the dump.
- They do not display full local variable values like a debugger.
- A `RUNNABLE` stack frame does not by itself prove CPU consumption.
- The absence of a deadlock report does not rule out all hangs or starvation.
- Large thread dumps can affect response times depending on the number of threads.
- Output may contain internal packages, paths, and sensitive operational details.
- `jstack` is an experimental/unsupported tool in JDK documentation; it may change or be removed in the future.

For production applications, prefer `jcmd Thread.print`, JFR, Java Mission Control, metrics, and logs. Choose the method that matches the urgency and acceptable overhead.

## 18. Recommended Thread Dump Analysis Workflow

When receiving a report that an application is hung or slow:

1. Identify the correct JVM using `jps -l` or a process management tool.
2. Record the PID, JDK version, timestamp, host/container, and symptoms.
3. Use `jcmd <pid> Thread.print -l` to capture the first dump.
4. If needed, capture two more dumps a few seconds apart.
5. Look for `BLOCKED` threads and the monitors they are waiting on.
6. Check for `Found one Java-level deadlock` at the end of the output.
7. Check `RUNNABLE` threads for high CPU usage and repeating stacks.
8. Inspect `WAITING` threads in queues, pools, futures, or locks.
9. Cross-reference stack frames with source code, logs, metrics, and dependency status.
10. If deeper time-series data is needed, use JFR or an appropriate monitoring tool.
11. Store dumps securely and redact sensitive data before sharing.
12. Propose a fix for the root cause; taking a dump does not unstick deadlocked threads.

## 19. Key Takeaways

- A stack trace is the frame sequence of a single thread; a thread dump is the set of stack traces and states of multiple threads in a JVM.
- Use `jstack <pid>` to print a thread dump; `-l` adds lock information and `-e` adds extended thread information on supported JDKs.
- Headers typically include thread name, Java thread ID, native thread ID, and state.
- `RUNNABLE` does not always mean a thread is using CPU.
- `BLOCKED` usually indicates a thread waiting on an intrinsic monitor.
- `WAITING` and `TIMED_WAITING` can be normal behavior; read the stack frames to understand the cause.
- `jstack -l` can display locks and report Java-level deadlocks.
- Take multiple dumps a few seconds apart to distinguish transient snapshots from persistent states.
- Oracle recommends `jcmd <pid> Thread.print` for modern diagnostics; `jstack` is experimental/unsupported.
- Protect thread dumps because the output can expose internal application structure.

Understanding how to read thread headers, states, stack frames, and locks turns a thread dump into actionable evidence for investigating deadlocks, thread bottlenecks, and slow-responding applications.

## References

- [Oracle Java SE 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 24 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- [Oracle Java SE 11 — jstack and jcmd diagnostics](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html)
