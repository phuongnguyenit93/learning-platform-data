# Detecting Deadlocks in Java with `jstack`

A deadlock occurs when two or more threads wait for each other to release resources that the other thread is holding. None of the threads in the cycle can make progress, so the affected work stalls indefinitely.

`jstack` captures a thread dump of a running JVM and automatically checks for deadlocks. When a lock cycle is found, the output may contain a section like:

~~~text
Found one Java-level deadlock:
...
~~~

Common command:

~~~text
jstack -l <PID>
~~~

The `-l` option prints additional lock information, including ownable synchronizers such as `ReentrantLock`. In JDK 24.0.2, `jstack -e <PID>` adds extended thread information. Oracle recommends using `jcmd` for modern JVM diagnostics; the equivalent command is:

~~~text
jcmd <PID> Thread.print -l
~~~

This lesson explains how to capture a thread dump, read a lock cycle, distinguish deadlocks from normal waiting states, and reproduce the issue using Java 17+. The commands and outputs were verified with Zulu/OpenJDK 24.0.2.

## 1. What is a deadlock?

Suppose two threads both need two locks:

- Thread A acquires `LOCK_A`, then waits for `LOCK_B`.
- Thread B acquires `LOCK_B`, then waits for `LOCK_A`.

A cannot acquire `LOCK_B` because B is holding it. B cannot acquire `LOCK_A` because A is holding it. Both wait indefinitely.

~~~text
Thread A                         Thread B
--------                         --------
holds LOCK_A                     holds LOCK_B
waits for LOCK_B  -------------> held by B
held by A         <------------- waits for LOCK_A

A waits for B, and B waits for A.
No thread can make progress.
~~~

Deadlocks can occur with:

- `synchronized` and object monitors.
- `ReentrantLock` and other ownable synchronizers.
- Multiple locks acquired in an inconsistent order.
- Other application-level resource dependencies, such as two services waiting on each other or a task waiting for a result from an executor whose workers are exhausted.

`jstack` focuses on thread states and synchronization mechanisms observable by the JVM. A deadlock in a database, network, or distributed system can cause Java threads to wait, but it will not necessarily appear as a Java-level lock cycle that `jstack` can detect on its own.

## 2. Four conditions that commonly lead to deadlock

The Coffman model describes four conditions that must hold simultaneously for a deadlock to form:

1. **Mutual exclusion:** a resource can be held by only one thread at a time.
2. **Hold and wait:** a thread holds at least one resource while waiting for another.
3. **No preemption:** a resource cannot be forcibly taken away from the thread holding it.
4. **Circular wait:** a cycle of threads exists where each thread waits for a resource held by the next thread in the cycle.

The two-monitor example in the previous section satisfies all four conditions. An effective prevention strategy is to eliminate circular wait by enforcing a consistent lock acquisition order across the entire codebase.

Not every slowdown or `BLOCKED` thread indicates a deadlock. A thread may simply be waiting for a short-lived lock whose owner will release it soon. Always verify the owner/waiter relationship and check for a cycle before concluding there is a deadlock.

## 3. Deadlock detection based on a wait-for graph

Waiting relationships can be represented as a graph:

- Thread nodes represent threads.
- Lock nodes represent monitors or synchronizers.
- A thread → lock edge means the thread is waiting for the lock.
- A lock → thread edge means that thread owns the lock.

If the graph contains a cycle, the threads in that cycle are deadlocked on resources tracked by the JVM.

Example:

~~~text
Thread-A -> LOCK_B -> Thread-B -> LOCK_A -> Thread-A
~~~

When a deadlock is detected, the JVM can report which monitor/synchronizer each thread is waiting for and which thread holds it. This is the most important information when reading the end of a thread dump.

Object/monitor addresses such as `0x000000011f019580` are only identifiers for that specific snapshot. Do not use these addresses to compare across different runs or to infer variable names in source code. Use thread names, class names, method names, and stack frames to trace back to the code.

## 4. Selecting the right JVM and PID

Before capturing a thread dump, identify the target process:

~~~text
jps -l
~~~

Example output:

~~~text
18240 com.example.OrderService
29116 com.example.ReportWorker
~~~

PIDs change between runs. Look up the current PID, then confirm the application name and deployment environment using an appropriate process manager or command line.

You can verify further with:

~~~text
jcmd 18240 VM.version
jcmd 18240 VM.command_line
~~~

Do not confuse an application's PID on the host with its PID inside a container. If the JVM runs in a separate container/PID namespace, find the PID and run diagnostic tools from the appropriate environment or follow your platform's container access procedure.

## 5. `jstack` syntax and options

The JDK 24.0.2 help output shows:

~~~text
jstack [-l][-e] <pid>
~~~

| Command/Option | Description |
|---|---|
| `jstack <PID>` | Prints stack traces of threads in the JVM and performs deadlock detection |
| `jstack -l <PID>` | Prints additional lock information, including ownable synchronizers |
| `jstack -e <PID>` | Prints extended thread information |
| `jstack -l -e <PID>` | Combines lock information and extended thread information |
| `jstack -h` | Displays help |

Examples:

~~~text
jstack 18240
jstack -l 18240
jstack -e 18240
jstack -l -e 18240
~~~

If you need to diagnose `ReentrantLock`, prefer `-l`. Without `-l`, the thread dump still shows stacks and monitors, but it may omit ownable synchronizer details that threads are holding or waiting for.

`-e` does not replace `-l`: it adds thread information, whereas `-l` adds lock information.

## 6. Using `jcmd Thread.print` in modern JDKs

Oracle recommends `jcmd` over the legacy `jstack` utility for diagnosing the JVM and Java applications. `jcmd` also provides thread dumps and lock options:

~~~text
jcmd 18240 Thread.print
jcmd 18240 Thread.print -l
jcmd 18240 Thread.print -e
jcmd 18240 Thread.print -l -e
~~~

Check the syntax supported by the target JVM:

~~~text
jcmd 18240 help Thread.print
~~~

In JDK 24.0.2, the `Thread.print` help states:

- `-l`: prints information about `java.util.concurrent` locks.
- `-e`: prints extended thread information.
- Impact: Medium, depending on the number of threads.

`jcmd <PID> Thread.print -l` has been verified on a deadlocked JVM and produces a deadlock report similar to `jstack -l`.

A thread dump is a point-in-time snapshot. Running the dump command does not terminate the application; the JVM continues running after the output is generated.

## 7. How to read a thread dump

A thread entry typically includes:

- Thread name, such as `"worker-A"`.
- Thread ID and native thread ID.
- Priority and current state.
- Stack trace showing which method the thread is executing.
- Monitors or synchronizers the thread is waiting on and holding.

Abbreviated example:

~~~text
"worker-A" #35 prio=5 ... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.OrderService.update(OrderService.java:42)
    - waiting to lock <0x000000011f019590> (a java.lang.Object)
    - locked <0x000000011f019580> (a java.lang.Object)
~~~

How to read it:

- `BLOCKED (on object monitor)`: the thread is waiting to enter a `synchronized` block or method.
- `waiting to lock`: the monitor the thread wants to acquire.
- `locked`: the monitor the thread currently holds.
- Stack frame `OrderService.update(...:42)`: the code location waiting for the lock.

With `ReentrantLock`, the thread typically shows `WAITING (parking)` and the stack may pass through `LockSupport.park`, `AbstractQueuedSynchronizer`, or `ReentrantLock.lock`. This indicates waiting on a synchronizer; it is not necessarily a deadlock unless a cycle exists.

### 7.1. Thread states to distinguish

| State | Common interpretation |
|---|---|
| `RUNNABLE` | The thread is running or ready to run in the JVM; not necessarily consuming CPU continuously |
| `BLOCKED` | Waiting to acquire an object monitor |
| `WAITING` | Waiting indefinitely for another action, such as `Object.wait()` or park |
| `TIMED_WAITING` | Waiting for a bounded period, such as `sleep()` or timed wait |
| `TERMINATED` | The thread has finished execution |

A `BLOCKED` thread alone does not prove a deadlock. A `WAITING` or `TIMED_WAITING` thread can also be completely normal. Inspect the lock owner, stack frames, and the deadlock summary section.

## 8. Recognizing the deadlock summary section

When the JVM detects a cycle, the end of the output may look like:

~~~text
Found one Java-level deadlock:
=============================

"worker-A":
  waiting to lock monitor ... (object 0x..., a java.lang.Object),
  which is held by "worker-B"

"worker-B":
  waiting to lock monitor ... (object 0x..., a java.lang.Object),
  which is held by "worker-A"
~~~

This is clear evidence of a two-thread cycle:

- `worker-A` needs the monitor held by `worker-B`.
- `worker-B` needs the monitor held by `worker-A`.
- Neither thread can proceed to release the other monitor.

If there are multiple independent cycles, the output may report multiple deadlocks. Do not just count `BLOCKED` threads; a single deadlock can involve multiple threads and multiple locks.

The absence of a deadlock summary does not prove the application is completely free of stalls. Threads may be waiting on a database, network, future, executor, distributed lock, or business condition that the JVM cannot represent as a monitor/synchronizer cycle.

## 9. Monitor deadlocks with `synchronized`

`synchronized` uses object monitors. For example:

~~~java
synchronized (LOCK_A) {
    synchronized (LOCK_B) {
        // critical section
    }
}
~~~

If one thread acquires A then B, while another thread acquires B then A, the two threads can deadlock.

In a thread dump, monitors are typically displayed by object identity:

~~~text
- waiting to lock <0x...> (a java.lang.Object)
- locked <0x...> (a java.lang.Object)
~~~

Matching object IDs across threads helps identify whether a monitor one thread is waiting on is held by another thread. The summary section usually makes this explicit with `which is held by`.

When investigating source code:

1. Locate the method and line number from the stack frame.
2. Identify the object used as the monitor.
3. Find all code paths that can acquire the same monitor.
4. Check the acquisition order of multiple monitors.
5. Cross-reference with the other threads in the cycle.

Do not fix this by renaming threads or adding `sleep()`. Fix the synchronization order or redesign the critical section.

## 10. Ownable synchronizers and `ReentrantLock`

`ReentrantLock` does not use `synchronized` syntax; it relies on ownable synchronizers. Therefore, when investigating this type of lock, use `-l`:

~~~text
jstack -l 18240
~~~

Abbreviated example output:

~~~text
"lock-A":
   java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.locks.ReentrantLock.lock(...)
    - parking to wait for <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
   Locked ownable synchronizers:
    - <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)

"lock-B":
   java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.locks.ReentrantLock.lock(...)
    - parking to wait for <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
   Locked ownable synchronizers:
    - <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
~~~

The deadlock summary for ownable synchronizers may look like:

~~~text
Found one Java-level deadlock:

"lock-A":
  waiting for ownable synchronizer ...,
  which is held by "lock-B"

"lock-B":
  waiting for ownable synchronizer ...,
  which is held by "lock-A"
~~~

Key takeaways:

- `-l` adds information about `java.util.concurrent` locks.
- `WAITING (parking)` may indicate a thread waiting on a `ReentrantLock`.
- Conclude deadlock only when the owner/waiter relationships form a cycle.
- Call `unlock()` in a `finally` block to ensure the lock is released when leaving the critical section; this manages lock lifecycle but does not prevent circular wait on its own.

## 11. Java 17+ example: creating a reproducible deadlock

The following program creates two monitors and two threads. `CountDownLatch` coordinates the starting point so each thread holds one monitor before both attempt to acquire the other.

Create `DeadlockDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class DeadlockDemo {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();
    private static final CountDownLatch READY = new CountDownLatch(2);
    private static final CountDownLatch START = new CountDownLatch(1);

    private DeadlockDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        Thread first = new Thread(() -> {
            synchronized (LOCK_A) {
                READY.countDown();
                awaitStart();
                synchronized (LOCK_B) {
                    System.out.println("worker-A acquired both locks");
                }
            }
        }, "worker-A");

        Thread second = new Thread(() -> {
            synchronized (LOCK_B) {
                READY.countDown();
                awaitStart();
                synchronized (LOCK_A) {
                    System.out.println("worker-B acquired both locks");
                }
            }
        }, "worker-B");

        first.start();
        second.start();

        READY.await();
        START.countDown();

        System.out.println("DEADLOCK_DEMO_READY");
        Thread.sleep(300_000);
    }

    private static void awaitStart() {
        try {
            START.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Compile with Java 17+:

~~~text
javac --release 17 DeadlockDemo.java
~~~

Run:

~~~text
java DeadlockDemo
~~~

Stdout:

~~~text
DEADLOCK_DEMO_READY
~~~

Once the line above appears, open a second terminal and find the PID:

~~~text
jps -l
~~~

Assuming the PID of `DeadlockDemo` is `18240`, capture the thread dump:

~~~text
jstack -l 18240
~~~

Or use `jcmd`:

~~~text
jcmd 18240 Thread.print -l
~~~

Expected results include:

- Thread `"worker-A"` in `BLOCKED` state.
- Thread `"worker-B"` in `BLOCKED` state.
- One monitor held by each thread.
- One monitor waited on by each thread.
- A `Found one Java-level deadlock` section showing the two threads holding each other's locks.

Neither `worker-A acquired both locks` nor `worker-B acquired both locks` will be printed because the program intentionally deadlocks. When finished with the lab, stop the test process with `Ctrl+C` in the terminal running it or terminate the exact PID via your process manager. Do not leave the deadlocked program running in the background.

## 12. `ReentrantLock` variant

The same issue can be reproduced with two `ReentrantLock` instances:

~~~java
private static final ReentrantLock LOCK_A = new ReentrantLock();
private static final ReentrantLock LOCK_B = new ReentrantLock();

static void firstPath() {
    LOCK_A.lock();
    try {
        LOCK_B.lock();
        try {
            // critical section
        } finally {
            LOCK_B.unlock();
        }
    } finally {
        LOCK_A.unlock();
    }
}

static void secondPath() {
    LOCK_B.lock();
    try {
        LOCK_A.lock();
        try {
            // critical section
        } finally {
            LOCK_A.unlock();
        }
    } finally {
        LOCK_B.unlock();
    }
}
~~~

These two code paths demonstrate opposite lock acquisition orders. If two threads run concurrently and each acquires its first lock, they can wait indefinitely on the second lock.

To analyze this type of deadlock, use `jstack -l` or `jcmd <PID> Thread.print -l`. Do not omit `-l` when you need ownable synchronizer details.

## 13. Detecting deadlocks with `ThreadMXBean`

An application can also check for deadlocks using the Management API. `ThreadMXBean.findDeadlockedThreads()` finds cycles involving object monitors and ownable synchronizers on platform threads.

Example:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public final class DeadlockCheck {
    private DeadlockCheck() {
    }

    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long[] ids = bean.findDeadlockedThreads();

        if (ids == null) {
            System.out.println("NO_PLATFORM_DEADLOCK");
            return;
        }

        ThreadInfo[] infos = bean.getThreadInfo(ids, true, true);
        for (ThreadInfo info : infos) {
            if (info != null) {
                System.out.println(
                        "DEADLOCK_THREAD=" + info.getThreadName());
            }
        }
    }
}
~~~

Compile:

~~~text
javac --release 17 DeadlockCheck.java
~~~

This program must run inside the same JVM being inspected. It cannot inspect another JVM simply by calling `ManagementFactory.getThreadMXBean()`.

`findMonitorDeadlockedThreads()` only detects deadlocks involving object monitors. `findDeadlockedThreads()` extends detection to ownable synchronizers such as `ReentrantLock`. This API is intended for troubleshooting, not as a synchronization control mechanism in business logic; the operation can be expensive, and the JVM may not support monitor/synchronizer usage monitoring.

The JDK 24 API specifies that these methods detect deadlocks of platform threads; cycles involving virtual threads are not detected by these methods. If your application uses virtual threads, verify your JDK version's limitations and combine thread dumps, JFR, application tracing, and appropriate observability tools.

## 14. Capturing thread dumps in production

When production hangs or shows signs of deadlock:

1. Identify the exact host/container, service, and PID.
2. Record the timestamp, JDK version, and user-facing symptoms.
3. Capture a thread dump using `jcmd <PID> Thread.print -l`.
4. If needed, capture one or two more dumps a few seconds apart for comparison.
5. Preserve the timestamp and PID for each dump.
6. Look for the deadlock summary, thread names, lock owners, and stack frames.
7. Correlate with application logs, request IDs, database monitoring, and metrics.
8. Only restart or kill the process according to incident procedures after saving the necessary evidence.

Example saving output in PowerShell:

~~~powershell
$javaPid = 18240
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

jcmd $javaPid Thread.print -l |
    Set-Content -Encoding UTF8 ".\thread-dump-$stamp.txt"
~~~

macOS/Linux:

~~~sh
java_pid=18240
stamp=$(date +%Y%m%d-%H%M%S)

jcmd "$java_pid" Thread.print -l \
    > "thread-dump-$stamp.txt"
~~~

Thread dumps can contain class names, file paths, SQL, URLs, and business data present in stack traces or thread names. Protect these files like sensitive operational logs; share them only with authorized personnel.

Avoid taking thread dumps at high frequency while the system is overloaded. Each dump must attach and collect stacks across many threads; `jcmd Thread.print` has a Medium impact depending on thread count.

## 15. Deadlock, contention, starvation, and livelock

The following conditions have similar symptoms but different root causes:

| Phenomenon | Symptom | How to distinguish |
|---|---|---|
| Deadlock | A group of threads wait on each other indefinitely | Owner/waiter cycle or deadlock summary is present |
| Lock contention | Multiple threads compete for a single lock | Busy lock owner exists; no cycle required |
| Starvation | A thread is denied CPU, lock, or resources for too long | No lock cycle required |
| Livelock | Threads remain active, repeatedly yielding/changing state without completing | CPU may stay active; no deadlock lock cycle |
| I/O hang | Threads wait on network, file, or database | Stacks typically stop at I/O/JDBC/socket; JVM may not find a cycle |

If there is no deadlock summary but the application is still hung, check:

- Are threads waiting on `Future.get()` or `CompletableFuture.join()`?
- Has a thread pool run out of workers because tasks are waiting on each other?
- Are JDBC calls waiting on a database lock or connection pool?
- Do network requests have timeouts configured?
- Is there a distributed lock or message dependency between services?

`jstack` shows where threads are; it does not replace tracing, database deadlock reports, or cross-system dependency analysis.

## 16. How to prevent deadlocks

Practical prevention measures:

**Enforce a consistent lock order.** If code needs A and B, every code path must acquire A before B. Never let one path acquire B then A.

**Minimize critical section scope.** Hold locks only around the code that protects shared state. Avoid performing network I/O, database calls, or uncontrolled callbacks while holding a lock.

**Avoid nested locks when unnecessary.** Each nested lock layer increases the number of ordering relationships to manage.

**Use timeouts or interruptible acquisition when appropriate.** `ReentrantLock.tryLock(timeout, unit)` and `lockInterruptibly()` let you design escape paths; handle retries/backoff and business rollbacks properly.

**Do not wait on a Future inside an exhausted executor.** Design task dependencies and executor capacity to prevent thread pool starvation.

**Prefer immutable objects and concurrency utilities.** Reducing shared mutable state lowers the number of locks and the risk of circular wait.

**Document lock order.** Explicitly document lock ordering in APIs/classes with multiple critical sections and review it when adding new locks.

Using `try/finally` to call `unlock()` is mandatory with `ReentrantLock`, but it only guarantees lock release when exiting the locked region. It does not resolve a cycle where two threads are both waiting before entering `finally`.

## 17. Common troubleshooting

### `jstack` cannot attach to the process

**Cause:** wrong PID, process already exited, running as a different user, attach disabled, or process is in a different namespace.

**Resolution:** verify the PID with `jps -l` or the OS process manager, check the user and `-XX:+DisableAttachMechanism`, and run the tool on the matching host/container.

### Thread dump shows `BLOCKED` but no deadlock summary

**Cause:** the thread is waiting for a monitor whose owner may release it; no cycle exists yet.

**Resolution:** inspect the owner and stacks on both sides, capture another dump after a few seconds, and determine whether a cycle exists.

### `ReentrantLock` is missing from the output

**Cause:** the dump was captured without the long listing option.

**Resolution:** use `jstack -l <PID>` or `jcmd <PID> Thread.print -l`.

### Thread is in `WAITING (parking)` for an unclear reason

**Cause:** the thread may be waiting on a `ReentrantLock`, semaphore, condition, executor, or another parking mechanism.

**Resolution:** inspect stack frames around `LockSupport.park`, `AbstractQueuedSynchronizer`, `ReentrantLock`, and the owner/synchronizer details.

### No deadlock summary, but requests are still hanging

**Cause:** the application may be waiting on a database, network, future, queue, or distributed lock that the JVM does not recognize as a monitor cycle.

**Resolution:** combine thread dumps with application tracing, database monitoring, request logs, timeouts, and executor metrics.

### Deadlock disappears before the dump is captured

**Cause:** the issue is load- or timing-dependent; a thread exited the cycle before capture.

**Resolution:** capture dumps immediately when alerts fire, record timestamps, and correlate with logs. Consider JFR or telemetry to capture events before the incident ends.

### `ThreadMXBean.findDeadlockedThreads()` returns `null`

**Cause:** no platform-thread monitor/ownable synchronizer cycle at the time of the call, or the deadlock involves resources outside the API's scope.

**Resolution:** verify the timing of the check and investigate I/O, executors, databases, distributed locks, and virtual thread limitations.

## 18. Deadlock investigation checklist

- [ ] Identified the exact JVM, host/container, and PID.
- [ ] Recorded the JDK vendor/version and capture timestamp.
- [ ] Captured `jcmd <PID> Thread.print -l` or `jstack -l <PID>`.
- [ ] Used `-l` to inspect ownable synchronizers when `ReentrantLock` is involved.
- [ ] Checked the `Found one Java-level deadlock` section if present.
- [ ] Identified which thread is waiting for which lock and which thread holds it.
- [ ] Traced stack frames back to the class, method, and source line.
- [ ] Distinguished between `BLOCKED`, `WAITING`, and `TIMED_WAITING`.
- [ ] Captured additional thread dumps if needed to confirm a sustained state.
- [ ] Considered deadlocks in databases, networks, executors, or distributed systems.
- [ ] Protected the thread dump, as output may contain sensitive data.
- [ ] Identified the lock order or dependency causing circular wait.
- [ ] Fixed and re-tested the lock acquisition code paths.
- [ ] Verified system recovery and confirmed no deadlock cycles remain.

## 19. References

- Oracle JDK 24 — Diagnostic Tools, `jstack`, thread dumps, and deadlock detection: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — `jcmd` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Java SE 24 — `ThreadMXBean` API: https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 24 — `ReentrantLock` API: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html

`jstack -l` helps identify cycles between threads and monitors/ownable synchronizers; `jcmd <PID> Thread.print -l` is Oracle's recommended option for modern diagnostics. Rely on the deadlock summary, lock owners, and stack frames to locate the code causing circular wait, then fix the lock acquisition order or redesign the resource dependencies.