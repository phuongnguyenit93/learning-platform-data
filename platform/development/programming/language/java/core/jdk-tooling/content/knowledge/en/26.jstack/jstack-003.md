# Thread States in Java and How to Read a Thread Dump

A **thread state** describes the state of a thread at a given point in time inside the JVM. When an application is slow, hung, unresponsive, or showing signs of a deadlock, a thread dump helps determine whether threads are running, waiting for a monitor, waiting for a signal, or waiting for a timeout. Two commonly used tools are `jstack` and `jcmd Thread.print`.

Java defines six states in `java.lang.Thread.State`: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `TERMINATED`. These are JVM-level states, not a direct mirror of operating system thread states.

## 1. Why Understanding Thread States Matters

A Java application can create tens, hundreds, or thousands of threads. When a system runs into trouble, looking only at CPU usage or thread count is rarely enough to find the root cause.

Thread states help answer questions such as:

- Is a thread executing code or waiting?
- Is a thread blocked trying to enter a `synchronized` region?
- Is a thread waiting on a condition, another thread, or a time interval?
- Which thread holds the monitor that other threads need?
- Is there a lock-waiting cycle forming a deadlock?
- Are threads in a thread pool normally waiting for work, or are they stuck?

A thread dump is a snapshot of state at the moment the dump is taken. It helps locate positions and lock relationships, but it does not explain all business logic on its own. To identify trends, you usually need to capture multiple dumps a few seconds apart and compare stack traces, states, lock owners, and CPU time.

## 2. The Six States of Thread.State

Java defines exactly six states:

| State | Meaning |
|---|---|
| `NEW` | The thread has been created, but `start()` has not been called yet. |
| `RUNNABLE` | The thread is executing in the JVM or ready to run; it may be waiting for operating system resources such as CPU. |
| `BLOCKED` | The thread is waiting to acquire a monitor lock to enter or re-enter a synchronized block/method. |
| `WAITING` | The thread is waiting indefinitely for another thread to perform a particular action. |
| `TIMED_WAITING` | The thread is waiting for an action for a bounded period of time. |
| `TERMINATED` | The `run()` method has completed normally or exited due to an uncaught exception. |

A thread can be in only one of the six states at any given point in time. Its state changes as execution progresses and synchronization operations occur.

## 3. NEW — Thread Not Yet Started

A newly created thread starts in the `NEW` state:

~~~java
Thread worker = new Thread(() -> System.out.println("working"));
System.out.println(worker.getState());
~~~

Output:

~~~text
NEW
~~~

After calling:

~~~java
worker.start();
~~~

The JVM begins scheduling the thread, and it leaves the `NEW` state. Do not call `run()` directly if your goal is to start a new thread; calling `run()` like a regular method executes it on the current thread.

Because a thread in the `NEW` state has not started running, it typically does not appear in a thread dump of a running JVM. You can inspect this state programmatically with `Thread.getState()`.

## 4. RUNNABLE — Running or Ready to Run

`RUNNABLE` is the state of a thread executing in the JVM. The thread may be actively using CPU or waiting for the operating system to allocate resources to continue.

Example:

~~~java
Thread worker = new Thread(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        doSmallUnitOfWork();
    }
});
worker.start();
~~~

In a thread dump:

~~~text
"worker-1" #31 ... 
   java.lang.Thread.State: RUNNABLE
    at com.acme.Worker.run(Worker.java:18)
~~~

Do not assume `RUNNABLE` means the thread is definitely consuming CPU at the exact instant the dump was captured. The Java state does not fully represent the operating system's scheduler, CPU, or I/O state. When investigating high CPU, compare multiple dumps and correlate them with CPU time or OS-level tools.

A `RUNNABLE` thread appearing repeatedly at the same line of code across multiple dumps may be in a hot loop, processing excessive data, or spinning due to contention. However, a single `RUNNABLE` snapshot alone is not enough to conclude there is a bug.

## 5. BLOCKED — Waiting for a Monitor Lock

`BLOCKED` has a narrow meaning: the thread is waiting for a monitor lock to enter a synchronized block or synchronized method, or to re-acquire the monitor after `Object.wait()` returns.

Example:

~~~java
private static final Object LOCK = new Object();

static void update() {
    synchronized (LOCK) {
        // Critical section
    }
}
~~~

If thread A already holds `LOCK` and thread B calls `update()`, thread B may transition to `BLOCKED` until A releases the monitor.

In a thread dump:

~~~text
"blocked-on-monitor" #38 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.acme.Service.update(Service.java:42)
    - waiting to lock <0x000000011f01af90> (a java.lang.Object)
~~~

The `waiting to lock` line identifies the object monitor the thread is waiting for. Look for another thread with `locked <same address>` to find the thread holding the monitor.

`BLOCKED` does not mean every waiting operation produces this state. For example, a thread waiting on a `ReentrantLock` is typically parked and may appear as `WAITING` or `TIMED_WAITING`, depending on how it was called. Do not use the `BLOCKED` thread count as a proxy for all forms of lock contention.

## 6. WAITING — Waiting Indefinitely

A thread is in the `WAITING` state when it is waiting for an action from another thread without a timeout. Common APIs that produce this state:

- `Object.wait()` with no timeout argument.
- `Thread.join()` with no timeout argument.
- `LockSupport.park()`.

Example:

~~~java
synchronized (signal) {
    signal.wait();
}
~~~

The thread waits until it receives `notify()` or `notifyAll()`, is interrupted, or the wait condition changes according to the corresponding mechanism.

A thread dump might show:

~~~text
"waiting-on-object" #39 ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(...)
    - waiting on <0x000000011f01afa0> (a java.lang.Object)
~~~

With `LockSupport.park()` or synchronizer-based constructs, the stack trace may show the thread parked and waiting on a synchronizer rather than an object monitor.

Many `WAITING` threads in a thread pool can be completely normal: workers are waiting for tasks to arrive in the queue. Always read the stack trace and understand what condition the thread is waiting on before treating it as an incident.

## 7. TIMED_WAITING — Waiting with a Timeout

`TIMED_WAITING` is similar to `WAITING`, but with a bounded wait duration. Common APIs:

- `Thread.sleep(timeout)`.
- `Object.wait(timeout)`.
- `Thread.join(timeout)`.
- `LockSupport.parkNanos(timeout)`.
- `LockSupport.parkUntil(deadline)`.

Example:

~~~java
Thread.sleep(2_000);
~~~

Thread dump:

~~~text
"timer-worker" #40 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(...)
~~~

A thread sleeping on a schedule or waiting for a timeout is usually not a bug. If many threads are in `TIMED_WAITING` at the same wait site, determine whether it is retry/backoff, a timer, polling, or a business timeout.

### Differences Between WAITING and TIMED_WAITING

| WAITING | TIMED_WAITING |
|---|---|
| No finite timeout on the wait operation. | A bounded wait duration is specified. |
| Examples: `Object.wait()`, `join()`, `park()`. | Examples: `sleep()`, `wait(timeout)`, `join(timeout)`. |
| Requires a signal or another action to resume, or an interrupt. | Can resume when signaled, interrupted, or when the timeout expires. |

## 8. Common Confusions Between States

### BLOCKED Is Not the Same as WAITING

- `BLOCKED`: trying to acquire a monitor to enter a synchronized block/method.
- `WAITING`: has called an indefinite wait operation, such as `Object.wait()` or `LockSupport.park()`.

A thread waiting on `ReentrantLock.lock()` usually does not have the `BLOCKED` state because `ReentrantLock` is built on a park/synchronizer mechanism.

### Object.wait() and Thread.sleep() Are Not the Same

`Object.wait()` must be called while the thread owns the object's monitor. While waiting, it releases that monitor and must re-acquire it before continuing after being woken up.

`Thread.sleep()` does not release any monitor the thread currently holds. Therefore, a thread can be in `TIMED_WAITING` while still holding a monitor and causing other threads to be `BLOCKED`.

Example:

~~~java
synchronized (LOCK) {
    Thread.sleep(5_000);
}
~~~

During the sleep interval, other threads trying to enter `synchronized (LOCK)` still have to wait. This is a common reason a thread dump shows the monitor-holding thread in `TIMED_WAITING` while other threads are `BLOCKED`.

## 9. Lifecycle and State Transitions

A typical flow:

1. Create a `Thread` object → `NEW`.
2. Call `start()` → the thread becomes active and transitions to `RUNNABLE`.
3. Wait for a monitor → `BLOCKED`.
4. Call `wait()` or `park()` → `WAITING`.
5. Call `sleep()` or a timed wait operation → `TIMED_WAITING`.
6. Resume execution → typically returns to `RUNNABLE`.
7. `run()` finishes → `TERMINATED`.

Not every thread passes through all states. States can change very quickly; a thread can be woken up and continue running before the dump tool captures it.

`Thread.getState()` is designed for monitoring purposes. Do not use its return value as a synchronization mechanism or assume a thread will still be in that state after checking it.

## 10. What Is a Thread Dump?

A thread dump is a record of the stack traces and state information of threads at the time of sampling. It typically includes:

- Thread name.
- Java thread ID and native thread ID, if available.
- Daemon status and priority.
- Java state, such as `RUNNABLE` or `BLOCKED`.
- Stack trace with class, method, and line numbers when available.
- Monitor/synchronizer information when lock output is enabled.
- Additional information depending on the JDK and tool.

A thread dump is not a historical log. It does not show how long a thread has been in its current state or what its previous state was, unless the tool includes timing metrics. To distinguish normal waiting from an issue, compare consecutive dumps.

## 11. Capturing a Thread Dump with jstack

`jstack` prints stack traces of Java threads in a Java process.

Find the PID using:

~~~bash
jcmd -l
~~~

Or:

~~~bash
jps -l
~~~

Capture the dump:

~~~bash
jstack <pid>
~~~

Use `-l` to print additional lock information:

~~~bash
jstack -l <pid>
~~~

In the verified Azul OpenJDK 24.0.2 build, `jstack -h` also lists `-e` to print extended thread information:

~~~bash
jstack -e <pid>
~~~

The `-e` option does not appear in the referenced Oracle JDK 24 man page; check `jstack -h` on your specific vendor/JDK before using it in scripts.

`jstack` is marked experimental and unsupported by Oracle; the tool may change or be removed in future JDK releases. For new diagnostic workflows, prefer `jcmd Thread.print`.

## 12. Capturing a Thread Dump with jcmd

`jcmd` sends diagnostic commands to a running JVM. List local JVMs:

~~~bash
jcmd -l
~~~

View the commands supported by the JVM:

~~~bash
jcmd <pid> help
~~~

Print a thread dump:

~~~bash
jcmd <pid> Thread.print
~~~

Include lock information:

~~~bash
jcmd <pid> Thread.print -l
~~~

In the verified JDK 24.0.2 build, `Thread.print` also supports `-e` to print extended information:

~~~bash
jcmd <pid> Thread.print -e
~~~

`jcmd` is the preferred choice in modern diagnostic workflows. Available commands and options depend on the target JVM, so run `jcmd <pid> help Thread.print` against the actual process.

## 13. Saving a Thread Dump to a Plain or JSON File

JDK 24.0.2 provides the `Thread.dump_to_file` diagnostic command to write a thread dump to a file.

Write in plain format:

~~~bash
jcmd <pid> Thread.dump_to_file -format=plain threads.txt
~~~

Write in JSON format:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

If the file already exists, you can pass `-overwrite` when you explicitly want to overwrite it:

~~~bash
jcmd <pid> Thread.dump_to_file -overwrite -format=json threads.json
~~~

During testing, both plain and JSON formats were generated and read successfully. JSON is well suited for automated processing by tools; plain is convenient for quick inspection in an editor or text search.

A thread dump may contain class names, file paths, request details, or internal data on the stack. Restrict file access permissions and review dumps before sharing them.

## 14. How to Read a Thread Dump Entry

Condensed example:

~~~text
"blocked-on-monitor" #38 ... daemon prio=5 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.acme.Service.update(Service.java:42)
    - waiting to lock <0x000000011f01af90> (a java.lang.Object)
~~~

Meaning:

- `"blocked-on-monitor"` is the thread name.
- `#38` is the Java thread number in the dump.
- `daemon` indicates that it is a daemon thread.
- `java.lang.Thread.State: BLOCKED` is the Java thread state.
- `Service.java:42` shows the code location where it is waiting.
- `waiting to lock <...>` is the monitor the thread wants to acquire.

Look for another thread with the line:

~~~text
- locked <0x000000011f01af90> (a java.lang.Object)
~~~

That thread holds the monitor at the same address. Compare the stack traces of both the waiting thread and the lock-holding thread to determine the cause.

For park-based synchronizers, you may see a line like:

~~~text
- parking to wait for <0x...> (a java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject)
~~~

The exact address and class depend on the lock implementation. Read the thread name, state, stack trace, and lock information together.

## 15. Detecting Deadlocks with a Thread Dump

A deadlock occurs when threads form a cycle waiting for resources such that none of them can proceed. For example:

- Thread A holds lock X and waits for lock Y.
- Thread B holds lock Y and waits for lock X.

In code, this can happen when two threads acquire the same pair of locks in opposite orders:

~~~java
synchronized (lockA) {
    synchronized (lockB) {
        // work
    }
}
~~~

In a thread dump, a common symptom is multiple `BLOCKED` threads, each waiting on a monitor held by another thread.

When running `jstack -l`, JDK 24.0.2 in testing printed the following report section:

~~~text
Found one Java-level deadlock:
=============================
"deadlock-one":
  waiting to lock monitor ..., which is held by "deadlock-two"
"deadlock-two":
  waiting to lock monitor ..., which is held by "deadlock-one"
Found 1 deadlock.
~~~

This is evidence of a specific monitor cycle. Not every `BLOCKED` thread indicates a deadlock; a thread may simply be waiting briefly for a lock. Conversely, business-level deadlocks or deadlocks involving resources outside the JVM may not be recognized by the Java-level deadlock detector.

How to prevent deadlocks:

- Acquire multiple locks in the same order everywhere.
- Keep synchronized regions short.
- Avoid calling external code, I/O, or callbacks while holding a monitor.
- Prefer higher-level concurrency constructs such as executors, concurrent collections, and timed locks where appropriate.
- Design timeouts, cancellation, and recovery mechanisms for long-running wait operations.

## 16. Analyzing Common State Patterns

| Observed Pattern | Possibilities to Check |
|---|---|
| One or a few `RUNNABLE` threads with the same stack across multiple dumps and high CPU | Hot loop, excessive computation, retry without backoff, or spin contention. |
| Many `BLOCKED` threads waiting on the same monitor | Lock contention; find the thread holding the monitor and the code holding the lock. |
| Two or more `BLOCKED` threads forming an owner/waiter cycle | Possible deadlock; check the deadlock report section and monitor addresses. |
| Many `WAITING` threads in an executor | Likely idle workers waiting for tasks; check the queue, stack, and task count. |
| Many `TIMED_WAITING` threads in sleep | Likely a scheduler, retry/backoff, or polling; verify duration and frequency. |
| Thread waiting in `Object.wait()` for a long time | Identify which thread is supposed to call notify/notifyAll and whether a wake-up condition could be missed. |
| Thread parked on a lock/condition | Inspect the synchronizer, condition, queue, and the thread responsible for unparking/signaling. |

A single dump is rarely enough to draw a conclusion. If a thread keeps the same stack and state across several consecutive dumps, it is much more likely to be stuck. Correlate with CPU, request latency, queue depth, GC, and application logs to determine the real impact.

## 17. Limitations and Caveats of Thread States

- A state is a point-in-time snapshot; a thread can change state immediately afterward.
- Java's six states do not fully reflect OS thread states.
- `RUNNABLE` does not always mean high CPU usage.
- `BLOCKED` only describes waiting on a monitor, not all types of lock contention.
- `WAITING` and `TIMED_WAITING` can be normal behavior for thread pools, timers, or schedulers.
- `NEW` and `TERMINATED` typically do not appear in dumps of active threads.
- A thread dump does not replace profilers, JFR, logs, metrics, or heap analysis.
- `jstack` is experimental/unsupported in JDK 24 documentation; prefer `jcmd` for new workflows.
- `jcmd` must run on the same machine and under the same effective user/group that started the target JVM. Inside containers, you need the right PID namespace; `jcmd -l` will not list JVMs running in separate Docker processes.
- Dumps can contain internal information; protect the files and restrict read access.

## 18. Complete Example: Creating Thread States to Inspect

The Java 17+ example below creates threads in different states so you can observe them in a thread dump:

- `NEW`: a thread created but not started.
- `TERMINATED`: a thread that has finished running and been joined.
- `BLOCKED`: a thread waiting on a monitor held by another thread.
- `WAITING`: a thread calling `Object.wait()` without a timeout.
- `TIMED_WAITING`: a thread calling `Thread.sleep()`.
- `RUNNABLE`: a thread running a loop with `Thread.yield()`.

Create the file `src/com/acme/ThreadStateDemo.java`:

~~~java
package com.acme;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadStateDemo {
    private static final Object LOCK = new Object();
    private static final Object WAIT_MONITOR = new Object();
    private static volatile boolean keepRunning = true;

    private static void awaitState(Thread thread, Thread.State expected)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (thread.getState() != expected && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }
        if (thread.getState() != expected) {
            throw new IllegalStateException(thread.getName() + " expected "
                    + expected + " but was " + thread.getState());
        }
    }

    public static void main(String[] args) throws Exception {
        Thread neverStarted = new Thread(() -> { }, "never-started");
        Thread alreadyFinished = new Thread(() -> { }, "already-finished");
        alreadyFinished.start();
        alreadyFinished.join();

        CountDownLatch lockHeld = new CountDownLatch(1);
        Thread holder = new Thread(() -> {
            synchronized (LOCK) {
                lockHeld.countDown();
                try {
                    Thread.sleep(30_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "monitor-holder");
        holder.setDaemon(true);
        holder.start();
        if (!lockHeld.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("monitor was not acquired");
        }

        Thread blocked = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("blocked thread acquired monitor");
            }
        }, "blocked-on-monitor");
        blocked.setDaemon(true);
        blocked.start();
        awaitState(blocked, Thread.State.BLOCKED);

        Thread waiting = new Thread(() -> {
            synchronized (WAIT_MONITOR) {
                try {
                    WAIT_MONITOR.wait();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "waiting-on-object");
        waiting.setDaemon(true);
        waiting.start();
        awaitState(waiting, Thread.State.WAITING);

        Thread timed = new Thread(() -> {
            try {
                Thread.sleep(30_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "timed-sleep");
        timed.setDaemon(true);
        timed.start();
        awaitState(timed, Thread.State.TIMED_WAITING);

        Thread runnable = new Thread(() -> {
            while (keepRunning) {
                Thread.yield();
            }
        }, "cpu-runnable");
        runnable.setDaemon(true);
        runnable.start();
        awaitState(runnable, Thread.State.RUNNABLE);

        System.out.println("NEW=" + neverStarted.getState());
        System.out.println("TERMINATED=" + alreadyFinished.getState());
        System.out.println("READY");
        Thread.sleep(20_000);
        keepRunning = false;
    }
}
~~~

### Step 1: Compile

From the project root directory:

~~~bash
javac --release 17 -d out src/com/acme/ThreadStateDemo.java
~~~

### Step 2: Run the Program

~~~bash
java -cp out com.acme.ThreadStateDemo
~~~

Exact stdout:

~~~text
NEW=NEW
TERMINATED=TERMINATED
READY
~~~

The program keeps the JVM alive for about 20 seconds so you have time to capture a dump. Open a second terminal and find the PID:

~~~bash
jcmd -l
~~~

### Step 3: Capture the Dump

~~~bash
jstack -l <pid>
~~~

Or:

~~~bash
jcmd <pid> Thread.print -l
~~~

In the output, look for these thread names:

| Thread name | Expected state |
|---|---|
| `monitor-holder` | `TIMED_WAITING` |
| `blocked-on-monitor` | `BLOCKED` |
| `waiting-on-object` | `WAITING` |
| `timed-sleep` | `TIMED_WAITING` |
| `cpu-runnable` | `RUNNABLE` |

`monitor-holder` sleeps while still inside `synchronized (LOCK)`, so it holds the monitor. `blocked-on-monitor` wants the same monitor, so it is in the `BLOCKED` state. `waiting-on-object` waits on a different monitor and releases that monitor during `wait()`. This example illustrates why looking only at state names without reading the stack trace and lock details can lead to the wrong conclusion.

The `Thread.yield()` loop exists solely to produce a `RUNNABLE` thread for capturing a dump. Do not use a busy loop like this instead of proper waiting or synchronization mechanisms in real applications.

## 19. Recommended Diagnostic Workflow

When an application is slow or appears hung:

1. Find the right JVM with `jcmd -l` or `jps -l`.
2. Capture the first thread dump with `jcmd <pid> Thread.print -l`.
3. Repeat two or three more times, a few seconds apart, if the issue persists.
4. Compare states, stack traces, lock addresses, and thread owners across dumps.
5. Check whether `RUNNABLE` threads have high CPU or repeat at the same stack frame.
6. For `BLOCKED` threads, find the monitor-holding thread and any lock-waiting cycle.
7. For `WAITING`/`TIMED_WAITING` threads, identify the condition, timeout, and thread responsible for waking them up.
8. Use the deadlock report if present; verify each owner/waiter before concluding.
9. Correlate with metrics, logs, CPU, GC, and request latency.
10. Store dumps in an access-controlled location and delete them according to your retention policy.

Thread states help explain what threads are doing inside the JVM, while thread dumps provide stack traces and lock details to trace the root cause. Distinguish the six states accurately, understand the difference between monitor contention and other waiting mechanisms, and combine multiple dumps with runtime data to pinpoint the problem. In modern JDKs, `jcmd Thread.print` is the preferred choice for collecting thread dumps; `jstack` remains useful when you need a familiar tool or quick check in supported environments.

## 20. References

- Oracle JDK 24 — [Thread.State API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.State.html).
- Oracle JDK 24 — [The jstack Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstack.html).
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html).
- Oracle JDK 24 — [Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf).