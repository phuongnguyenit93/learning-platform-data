# Thread Dumps for Analyzing Waiting, Locks, and Deadlocks in Java 17

**Topic:** Java 17 → Diagnostics and JFR  
**Focus:** Collecting and reading thread dumps to find waiting threads, lock contention, stalled thread pools, and deadlocks; understanding thread states, monitors, ownable synchronizers, lock owners, and combining multiple snapshots with JDK 17 diagnostic tools.

A thread dump is a snapshot of the state of JVM threads at a single point in time. It shows which stack frame each thread is executing in, which monitor or synchronizer it is waiting on, which thread holds a lock, and whether the JVM has detected a deadlock cycle. This is essential data when an application responds slowly, a request hangs, CPU spikes, or workers stop making progress.

In JDK 17, the practical way to capture a thread dump from a running JVM is **`jcmd <pid> Thread.print -l`**. The `-l` option requests printing additional information about `java.util.concurrent` locks. A single dump reflects only one instant; to distinguish normal waiting from a stuck thread, you usually need to collect multiple dumps spaced apart over time and compare them.

## 1. What Does a Thread Dump Contain?

A thread dump typically includes these groups of information:

- **Thread header:** thread name, thread ID, priority, native state, or CPU/timing details if provided by the JVM.
- **Thread state:** `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and other lifecycle states.
- **Stack trace:** the chain of method calls at capture time.
- **Monitor information:** monitors that the thread holds, is waiting to enter, or is waiting to be notified on.
- **Ownable synchronizers:** synchronization locks such as `ReentrantLock` and synchronizers based on `AbstractOwnableSynchronizer`.
- **Deadlock report:** if the JVM detects a deadlock lock cycle at capture time.

A thread dump is a diagnostic snapshot. It is not a full thread history, does not tell you exactly how long a thread has been in that state without supplementary data, and does not itself explain the business reason behind a waiting call.

## 2. Capturing Thread Dumps with jcmd on JDK 17

`jcmd` is a diagnostic tool bundled with the JDK. It sends diagnostic commands to a running JVM on the same machine and returns the output. With Java 17, the typical commands are:

~~~shell
jcmd -l
~~~

This command lists the Java processes the tool can detect. Once you identify the application's PID:

~~~shell
jcmd <pid> Thread.print -l
~~~

For example, if the PID is `12345`:

~~~shell
jcmd 12345 Thread.print -l
~~~

`Thread.print` prints thread stack traces. The `-l` option prints additional information about `java.util.concurrent` locks, which is helpful when investigating `ReentrantLock` or similar synchronizers.

### 2.1. Saving Dumps to a File

On Linux/macOS:

~~~shell
jcmd 12345 Thread.print -l > thread-dump-01.txt 2>&1
~~~

On Windows PowerShell:

~~~powershell
jcmd 12345 Thread.print -l | Out-File -Encoding utf8 thread-dump-01.txt
~~~

Record the timestamp, PID, hostname/container, and system load alongside the dump file. When comparing multiple snapshots, this metadata confirms which dumps belong to the same JVM and under what conditions they were collected.

### 2.2. Extended Options

JDK 17 supports these `Thread.print` options:

| Command | Meaning |
| --- | --- |
| `jcmd <pid> Thread.print` | Print thread dump and stack traces. |
| `jcmd <pid> Thread.print -l` | Also print information about `java.util.concurrent` locks. |
| `jcmd <pid> Thread.print -e` | Print extended thread information. |
| `jcmd <pid> Thread.print -e -l` | Combine extended information and lock information. |

You can view the exact command description on the running JDK with:

~~~shell
jcmd <pid> help Thread.print
~~~

Supported options depend on the command and JDK version. When investigating in production, prefer concise commands that provide sufficient detail and check `help` on the target JVM itself.

### 2.3. jstack as an Alternative

The JDK also provides `jstack` to print thread stack traces:

~~~shell
jstack -l 12345
~~~

`-l` requests printing additional lock information. `jstack` is still present in JDK 17, though in modern diagnostic workflows `jcmd` is often preferred because it provides a unified interface for sending many diagnostic commands to the JVM.

### 2.4. Operating System Signals

On Unix-like operating systems, sending `SIGQUIT` to a Java process usually causes HotSpot to print a thread dump to the JVM's standard output (the console/log the process writes to):

~~~shell
kill -3 12345
~~~

This signal is handled by the JVM to generate a dump; it does not ask the JVM to exit like `SIGTERM`. The dump typically appears in the process's log or console, not necessarily in the terminal running `kill`.

On Windows, `Ctrl+Break` in a console attached to the Java process can instruct the JVM to print a thread dump. For service/container environments without an interactive console, using `jcmd` is usually more convenient.

## 3. Conditions for jcmd to Connect to the JVM

`jcmd` generally needs to run on the same machine as the target Java process and under an appropriate matching user. Several factors can interfere:

- The JVM runs in a different container or namespace, causing PIDs/attach paths to differ from the host.
- The current user lacks permission to attach to the process.
- The JVM was launched with the attach mechanism disabled.
- The JDK used to run `jcmd` is incompatible or cannot locate the target process.
- The process is overloaded or in a state where attach requests do not respond quickly.

If `jcmd -l` does not list the process, verify the PID at the OS level, the user, the container, and the application's JDK. Do not conclude the JVM has stopped just because `jcmd`'s list does not show it.

In production, remember that thread dumps may contain class names, paths, usernames, SQL, URLs, or sensitive data appearing in stack traces and thread names. Protect dump files according to your system's logging and operational data policies.

## 4. Understanding Java Thread States

`java.lang.Thread.State` defines six states:

| State | Meaning |
| --- | --- |
| `NEW` | Thread has been created but `start()` has not been called yet. |
| `RUNNABLE` | Thread is executing in the JVM or ready to be scheduled CPU by the OS; it may also be performing native I/O. |
| `BLOCKED` | Thread is waiting to acquire an intrinsic monitor to enter a `synchronized` block/method. |
| `WAITING` | Thread is waiting indefinitely for an action from another thread. |
| `TIMED_WAITING` | Thread is waiting for a bounded amount of time. |
| `TERMINATED` | Thread has finished execution. |

Thread dumps typically focus on live threads. Not every state in the enum appears in every dump.

### 4.1. RUNNABLE

`RUNNABLE` does not guarantee a thread is actively consuming CPU at the exact moment of capture. The thread may be:

- Executing bytecode.
- Ready to run while waiting for CPU scheduling.
- Inside a native or I/O call where the JVM still reports `RUNNABLE`.

To determine whether a `RUNNABLE` thread is causing high CPU, inspect the stack trace and correlate with CPU time, OS threads, or JFR. One snapshot shows where the thread is, which is not enough to prove it is a CPU hot spot.

### 4.2. BLOCKED

`BLOCKED` means a thread is waiting to acquire an intrinsic monitor, usually because another thread currently holds the lock on a `synchronized` block or method.

Example:

~~~java
public class SharedCounter {
    private int value;

    public synchronized void increment() {
        value++;
    }
}
~~~

If thread A is inside `increment()` holding the `SharedCounter` monitor, thread B calling `increment()` on the same object must wait. In the dump, B may appear as:

~~~text
java.lang.Thread.State: BLOCKED (on object monitor)
    at SharedCounter.increment(SharedCounter.java:5)
    - waiting to lock <0x00000000...> (a SharedCounter)
~~~

A `BLOCKED` thread does not yet own the monitor it is waiting on. Find the thread holding that exact monitor to understand why it has not been released.

### 4.3. WAITING

`WAITING` is an indefinite wait for another event or action. Common causes include:

- `Object.wait()` without a timeout.
- `Thread.join()` without a timeout.
- `LockSupport.park()`.
- Synchronization constructs based on `AbstractQueuedSynchronizer`, such as `ReentrantLock`, `Condition`, `CountDownLatch`, or `FutureTask`.

In a dump, you may see:

~~~text
java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
~~~

This stack typically appears when a thread parks to wait on a synchronizer or event. It does not automatically mean a deadlock. For instance, an idle worker thread waiting for a task from a queue can be completely normal.

When calling `Object.wait()`, the thread must own the corresponding monitor; the JVM releases that monitor while the thread waits, and the thread only resumes after being notified (`notify`/`notifyAll`), woken by an interrupt, or another relevant condition. This differs from `BLOCKED`, where the thread is waiting to acquire the monitor and has not entered the synchronized region yet.

### 4.4. TIMED_WAITING

`TIMED_WAITING` is waiting with a timeout. Examples:

- `Thread.sleep(timeout)`.
- `Object.wait(timeout)`.
- `Thread.join(timeout)`.
- `LockSupport.parkNanos(...)` or `parkUntil(...)`.

Dump example:

~~~text
java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
~~~

A thread sleeping on a schedule or waiting with a timeout may be expected behavior. Check the code path, timeout, and loop frequency to decide whether anything is abnormal.

## 5. Distinguishing Monitors and Ownable Synchronizers

Java has multiple locking mechanisms. Thread dumps must be read with the right lock type in mind to avoid confusion.

### 5.1. Intrinsic Monitors

A monitor is the synchronization mechanism associated with every Java object and used by `synchronized`.

Example:

~~~java
synchronized (lock) {
    updateState();
}
~~~

A thread entering the synchronized block owns `lock`'s monitor. Another thread attempting to enter a synchronized block on the same object must wait.

A thread dump may show:

~~~text
- locked <0x00000000...> (a java.lang.Object)
- waiting to lock <0x00000000...> (a java.lang.Object)
- waiting on <0x00000000...> (a java.lang.Object)
~~~

Meaning:

- `locked`: the thread currently holds the monitor.
- `waiting to lock`: the thread is waiting to acquire the monitor.
- `waiting on`: the thread called `Object.wait()` on the monitor and is waiting to be notified.

### 5.2. Ownable Synchronizers

Locks like `ReentrantLock` do not use the `synchronized` keyword, yet still have ownership and waiting semantics. They are commonly based on `AbstractOwnableSynchronizer` or `AbstractQueuedSynchronizer`.

When using:

~~~java
ReentrantLock lock = new ReentrantLock();

lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
~~~

A thread waiting for the lock may appear in `WAITING (parking)` rather than `BLOCKED`, because it parks inside the synchronizer mechanism. When running `Thread.print -l`, the additional lock section can show which ownable synchronizer is being held.

Example at the end of a dump entry:

~~~text
Locked ownable synchronizers:
    - <0x00000000...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
~~~

Do not search only for `BLOCKED` when investigating lock contention. With `ReentrantLock`, `Semaphore`, and other concurrent utilities, waiting threads can be in waiting/parking states.

## 6. Reading the Structure of a Thread Entry

An illustrative entry might look like:

~~~text
"worker-3" #28 prio=5 os_prio=0 cpu=120.00ms elapsed=42.10s
   tid=0x000001f... nid=0x2a34 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.service.OrderService.update(OrderService.java:84)
    at com.example.worker.OrderWorker.run(OrderWorker.java:41)
    - waiting to lock <0x00000000...> (a com.example.service.OrderService)
~~~

Common fields:

| Field | Meaning |
| --- | --- |
| `"worker-3"` | Thread name assigned by the application or runtime. |
| `#28` | Thread ID in the JVM dump. |
| `prio=5` | Thread priority. |
| `cpu=...` | CPU time if provided by the format/runtime. |
| `elapsed=...` | How long the thread has existed or elapsed information per the dump format. |
| `tid=...` | JVM internal thread identifier. |
| `nid=...` | Native thread ID in the operating system. |
| `java.lang.Thread.State` | Java-level thread state. |
| `at ...` | Stack frames, usually read from the top frame downward. |
| `waiting to lock` | Monitor the thread is waiting on. |

Exact formatting varies across JVM vendors and JDK versions. Do not parse thread dumps using brittle regexes based on a single example if tooling must support multiple runtimes.

## 7. Analyzing Lock Contention

Lock contention occurs when multiple threads need the same lock concurrently and must queue up to wait. It can degrade throughput even without a deadlock.

### 7.1. Signs in a Dump

- Multiple threads in the `BLOCKED` state.
- Multiple stack traces sharing the same frame waiting on a monitor.
- Threads waiting on the same object ID.
- One thread holding that monitor with a stack trace inside a slow operation.
- With synchronizers, multiple threads in `WAITING (parking)` and the ownable synchronizer section pointing to the same lock owner.

### 7.2. Finding the Lock Owner

Suppose a dump shows:

~~~text
"request-12":
    java.lang.Thread.State: BLOCKED (on object monitor)
    - waiting to lock <0x1234> (a com.example.Cache)

"request-15":
    java.lang.Thread.State: BLOCKED (on object monitor)
    - waiting to lock <0x1234> (a com.example.Cache)

"cache-maintenance":
    java.lang.Thread.State: RUNNABLE
    - locked <0x1234> (a com.example.Cache)
    at com.example.Cache.rebuild(Cache.java:120)
~~~

Two requests are waiting on the same monitor `<0x1234>`. The thread `cache-maintenance` holds that monitor and is executing `Cache.rebuild`. This indicates contention around the cache critical section.

Next, inspect:

1. Does `rebuild` perform I/O, network calls, or database queries while holding the lock?
2. Is there a long-running loop or heavy operation inside?
3. Can the `synchronized` scope be narrowed or heavy work moved outside the lock?
4. Can one global lock be replaced by per-key/partitioned locks?

Do not conclude contention purely from the count of `BLOCKED` threads. Brief waits can be normal; multiple snapshots showing the same owner and the same stack trace provide much stronger evidence of sustained contention.

## 8. Identifying Deadlocks

A deadlock occurs when a group of threads holds resources needed by other threads in the group, forming a wait cycle that cannot make progress on its own.

Two-lock example:

~~~java
final Object lockA = new Object();
final Object lockB = new Object();

Thread first = new Thread(() -> {
    synchronized (lockA) {
        synchronized (lockB) {
            System.out.println("first completed");
        }
    }
}, "first");

Thread second = new Thread(() -> {
    synchronized (lockB) {
        synchronized (lockA) {
            System.out.println("second completed");
        }
    }
}, "second");
~~~

If `first` holds `lockA` and waits for `lockB`, while `second` holds `lockB` and waits for `lockA`, the two threads form a cycle:

~~~text
first  holds lockA  ── waits for lockB
  ^                                  |
  |                                  v
second waits for lockA  ── holds lockB
~~~

Neither thread can enter its second synchronized block to release the lock it currently holds. This is a deadlock.

### 8.1. Deadlock Indicators in a Thread Dump

HotSpot typically appends a notice at the end of the dump when it detects a Java-level deadlock, for example:

~~~text
Found one Java-level deadlock:
=============================

"first":
  waiting to lock monitor 0x... (object ...)
  which is held by "second"

"second":
  waiting to lock monitor 0x... (object ...)
  which is held by "first"
~~~

The exact format may vary. Read the relationships:

- Which thread is waiting on which lock?
- Which thread holds that lock?
- Is the owner waiting on another lock?
- Does the owner/waiter chain loop back to the original thread?

If there is a cycle, the JVM may explicitly report a deadlock. Even when this report section is absent, inspect the lock graph manually if you suspect a deadlock across synchronizers or resources outside the JVM.

### 8.2. Deadlocks with ReentrantLock

Deadlocks do not occur only with `synchronized`. Two threads can acquire `ReentrantLock` instances in opposite order:

~~~java
ReentrantLock lockA = new ReentrantLock();
ReentrantLock lockB = new ReentrantLock();

// Thread 1: lockA.lock(); then lockB.lock()
// Thread 2: lockB.lock(); then lockA.lock()
~~~

In a dump, threads waiting on `ReentrantLock` typically appear as `WAITING (parking)`. When using `-l`, the ownable synchronizers section identifies which lock is held. `Thread.print -l` is therefore much more useful than a stack-trace-only dump when investigating this lock type.

### 8.3. Not Every Wait Cycle Is a Java Deadlock

Thread dumps may not fully detect situations such as:

- Deadlocks across multiple processes or services via databases, message brokers, or the network.
- Threads waiting on native resources or callbacks not managed by the JVM as a monitor.
- Application-logic dependency cycles that do not form a JVM-recognized monitor/synchronizer cycle.
- Starvation or thread pool exhaustion preventing progress even without a lock cycle.

Thus, a “No deadlocks found” result does not prove the overall system is free of deadlocks at the database, distributed system, or application-logic layer.

## 9. Taking Multiple Thread Dumps to Spot Stuck States

A single dump is just a snapshot. For instance, seeing a thread in `WAITING` may be completely normal if it is waiting on a queue. To assess forward progress, collect multiple snapshots spaced at an interval appropriate for the workload.

Example:

~~~shell
jcmd 12345 Thread.print -l > dump-01.txt
~~~

After a short interval:

~~~shell
jcmd 12345 Thread.print -l > dump-02.txt
~~~

And again:

~~~shell
jcmd 12345 Thread.print -l > dump-03.txt
~~~

For hung-request incidents, you can start with three dumps spaced roughly 5–10 seconds apart, then adjust based on normal processing times and system load. This is a practical reference interval, not a rigid rule.

When comparing:

- Threads with the same ID and identical stack trace across multiple dumps may be waiting long-term or repeating the same code path.
- `RUNNABLE` threads with the same stack trace across multiple dumps, accompanied by rising CPU time, may be spinning in a loop or doing CPU-bound work.
- Multiple threads consistently waiting on the same monitor and the same owner indicate sustained contention.
- Thread pool workers in `WAITING` changing along with the task queue are usually normal.
- If a thread disappears in a later dump, it may have completed or terminated.

Thread names can be reused. When correlating across dumps, prioritize thread IDs, native IDs, and application context, keeping in mind that IDs are only meaningful within that process's lifetime.

## 10. Distinguishing Common Problems

| Scenario | Common Signs | Investigation Direction |
| --- | --- | --- |
| Idle thread pool | Many workers `WAITING (parking)` in queue take/poll. | Check if the queue has tasks; idle state may be normal. |
| Lock contention | Many threads waiting on the same monitor/synchronizer; one owner holds the lock long. | Inspect owner's stack and lock hold duration. |
| Deadlock | Cycle of threads waiting for locks held by one another; possible deadlock report at end of dump. | Draw the lock graph, identify the cycle and lock acquisition order. |
| CPU hot loop | `RUNNABLE` threads, identical stack trace across dumps, increasing CPU time. | Correlate per-thread CPU with JFR/OS profiler. |
| Thread pool exhaustion | Request threads waiting on futures/tasks; worker pool has no free workers or workers wait on each other. | Check pool size, queue, nested task submission, and dependencies. |
| Slow I/O | Threads `RUNNABLE` in native I/O or stacks in client/socket/database calls. | Check external service latency, sockets, and JFR/network metrics. |
| Starvation | Some threads do not run even without an explicit deadlock cycle. | Check scheduler, lock fairness, pool sizing, and load. |

### 10.1. Many WAITING Workers Can Be Normal

Example of an idle thread pool:

~~~text
"pool-1-thread-1":
    java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.LinkedBlockingQueue.take(...)
~~~

The worker is waiting to pull a task from the queue. If the queue is empty and the application has no incoming requests, this idle state is expected. Only when there is a backlog and workers are not processing it—or tasks are stuck on a dependency—is deeper investigation needed.

### 10.2. Thread Pool Exhaustion from Waiting on Subtasks

A design bug can happen when all workers in a pool run parent tasks, and each parent submits subtasks into the exact same pool and blocks on `Future.get()`. No free workers remain to run the subtasks, so all parent tasks wait forever.

The dump may show all workers `WAITING` inside `FutureTask.get` or `CompletableFuture.join` while the queue still holds pending tasks. This is not necessarily a monitor deadlock; it is starvation caused by pool usage structure.

Remediation:

- Avoid synchronously blocking on subtasks submitted to the same bounded worker pool.
- Use asynchronous composition instead of blocking for results where appropriate.
- Separate executors for work with different lifecycles.
- Evaluate pool sizing and dependency graphs rather than blindly increasing thread counts.

## 11. Using ThreadMXBean to Detect Deadlocks in Code

Beyond reading dumps, the Java Management API provides `ThreadMXBean` to query deadlocks programmatically.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public class DeadlockDetector {
    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long[] ids = bean.findDeadlockedThreads();

        if (ids == null || ids.length == 0) {
            System.out.println("No monitor or ownable-synchronizer deadlock found.");
            return;
        }

        ThreadInfo[] infos = bean.getThreadInfo(ids, true, true);
        for (ThreadInfo info : infos) {
            System.out.println(info);
        }
    }
}
~~~

`findDeadlockedThreads()` finds deadlock cycles involving intrinsic monitors and ownable synchronizers if the JVM supports that check. It is broader than `findMonitorDeadlockedThreads()`, which only checks monitor deadlocks.

These methods only detect deadlocks recognizable by the JVM through managed locking mechanisms. They do not detect distributed deadlocks, database deadlocks, or all forms of starvation.

### 11.1. Comparing the Two Methods

| API | Scope |
| --- | --- |
| `findMonitorDeadlockedThreads()` | Finds wait cycles involving intrinsic monitors (`synchronized`). |
| `findDeadlockedThreads()` | Finds wait cycles involving monitors and ownable synchronizers such as `ReentrantLock`, if supported. |

If the application uses `ReentrantLock` or other synchronizers, `findDeadlockedThreads()` is the more comprehensive choice.

## 12. How to Read a Stack Trace to Find the Cause

Read a thread entry in order:

1. **Name and state:** identify which thread is affected and what state it is in.
2. **Top frame:** identify the current call or immediate wait point.
3. **Lower frames:** trace the call path from application code down into libraries/JDK.
4. **Lock annotations:** identify which monitor is awaited or held.
5. **Lock owner:** locate the thread holding the referenced lock.
6. **Other snapshots:** determine whether the thread progresses or remains stuck at the same spot.

Example:

~~~text
"http-worker-7":
    java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.cache.Cache.get(Cache.java:72)
    at com.example.service.ProductService.load(ProductService.java:118)
    at com.example.web.ProductController.show(ProductController.java:44)
    - waiting to lock <0xabc> (a com.example.cache.Cache)
~~~

Reading top-down: the thread is waiting for a monitor in `Cache.get`; the request entered through `ProductService.load` and `ProductController.show`. Find the entry containing `- locked <0xabc>` to identify the owner, then inspect what the owner is doing while holding the cache monitor.

Do not stop at the top frame. A thread may be waiting in `Unsafe.park` or `Object.wait`, while the lower frames reveal whether it is waiting on a queue, future, condition, or a specific mechanism.

## 13. Common Causes of Deadlocks and How to Prevent Them

### 13.1. Acquiring Locks in Different Orders

Thread A acquires lock A then B; thread B acquires lock B then A. Both can hold one lock and wait on the other.

**Prevention:** enforce a global lock acquisition order, such as always acquiring locks in ascending ID order. Every code path must follow the same rule.

### 13.2. Calling External Code While Holding a Lock

A thread holds a monitor while calling the network, database, a callback, or a plugin. External code may wait on another thread that needs that same monitor.

**Prevention:** minimize critical sections; gather needed data under the lock, release the lock, and then perform I/O or invoke callbacks.

### 13.3. Nested Locks and Object-Level Locking

Multiple classes managing locks independently can produce inconsistent lock ordering, especially when callbacks call back into another class.

**Prevention:** define clear lock ownership, document lock ordering, reduce lock nesting, and use a clear synchronization strategy.

### 13.4. Intentional Use of tryLock and Timeouts

With `ReentrantLock`, `tryLock(timeout, unit)` can help avoid indefinite waits in certain designs. However, a timeout only gives the execution flow a chance to recover; it does not automatically solve data consistency or roll back partially completed operations.

If using timeouts, clearly define:

- When lock acquisition fails, do you return an error, retry, or drop the task?
- Is retrying safe?
- Are retry counts and backoff bounded?
- Is another lock being held while waiting?

## 14. Thread Dumps and JFR Complement Each Other

Thread dumps provide snapshots of stacks and lock states. Java Flight Recorder (JFR) records events over time, useful for viewing trends and correlations among threads, CPU, monitor contention, I/O, and JVM operations.

| Thread Dump | JFR |
| --- | --- |
| Snapshot at a single point in time. | Event data over a period of time. |
| Great for viewing full stacks and owner/waiter relationships. | Great for seeing when contention occurred and how long it lasted. |
| Can show JVM-detected deadlock cycles. | Can provide monitor contention events and timing context, depending on recording configuration. |
| Usually easy to capture while an incident is happening. | Well suited for continuous monitoring and post-incident analysis. |

If a dump shows a monitor frequently contended without revealing frequency, JFR can add timing evidence and contention stack traces. Conversely, if JFR reveals long wait durations, a thread dump during the incident helps locate the owner and states of all involved threads.

## 15. Practical Workflow When an Application Hangs

A workflow you can apply:

### Step 1: Record the Context

Record the incident time, PID, JDK version, hostname/container, CPU load, memory, pending request count, and dependent services.

### Step 2: Collect Multiple Dumps

~~~shell
jcmd <pid> Thread.print -l > dump-01.txt
jcmd <pid> Thread.print -l > dump-02.txt
jcmd <pid> Thread.print -l > dump-03.txt
~~~

Choose the capture interval based on normal processing times and severity. Do not generate rapid-fire dumps continuously without reason.

### Step 3: Check the Deadlock Report Section

Look for `Found one Java-level deadlock` lines or descriptions of threads waiting on locks held by other threads. If a cycle exists, list the involved threads and locks.

### Step 4: Group Threads by State and Stack

Count `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `RUNNABLE` threads. Group by top application frame, lock ID, queue, or synchronizer.

### Step 5: Find Lock Owners and Lock-Holding Code

For monitors, search for `- locked <id>`. For ownable synchronizers, inspect `Locked ownable synchronizers` and the owning thread. Trace the owner's stack to locate long-running work.

### Step 6: Compare Snapshots

Check which threads remain at the exact same location, whether owners change, whether queues drain, and whether CPU time increases. Distinguish brief normal waits from zero forward progress.

### Step 7: Correlate with JFR, Logs, and External Systems

If stacks wait on a database, socket, or future, inspect external service latency, connection pools, timeouts, and corresponding logs. If a CPU hot loop is suspected, use JFR or a profiler to quantify it.

### Step 8: Fix the Root Cause and Verify

Fix lock ordering, shrink critical sections, adjust pool architecture, or handle timeouts based on the actual cause. After deployment, re-verify thread dumps and metrics under representative load to confirm contention/deadlocks dropped.

## 16. Common Mistakes

| Mistake | Why It Misleads | Better Approach |
| --- | --- | --- |
| Seeing `WAITING` and concluding threads are hung | Idle workers, queue consumers, or signal-waiting threads may be normal. | Inspect the stack trace and workload. |
| Searching only for `BLOCKED` to find lock contention | `ReentrantLock` and synchronizers typically park in `WAITING`. | Capture dumps with `-l` and inspect ownable synchronizers. |
| Seeing `RUNNABLE` and concluding high CPU usage | JVM state does not guarantee continuous CPU execution. | Correlate CPU time, OS threads, and JFR. |
| Using one dump to conclude a deadlock | A single snapshot may catch a brief normal wait. | Capture multiple snapshots and find an owner/waiter cycle. |
| Seeing no deadlock report and assuming no deadlock exists | Deadlocks can occur in databases, native code, or distributed layers. | Inspect external dependencies and lock graphs beyond the JVM. |
| Inspecting only waiting threads | Without finding the owner, you do not know why the lock is held. | Find the held monitor/synchronizer and read the owner's stack. |
| Assuming every `WAITING (parking)` is an error | Queues, futures, conditions, and locks can park normally. | Identify what is being waited on and its wake-up condition. |
| Capturing dumps too frequently | Generates huge files and can add system overhead. | Choose an interval long enough to observe progress. |
| Omitting timestamps and PIDs | Hard to correlate dumps and logs. | Attach metadata to each file. |
| Sharing dumps without review | Stacks can contain sensitive information. | Protect files and redact data before sharing. |

## 17. Frequently Asked Questions

**Should I use `jcmd` or `jstack` in Java 17?**  
Both are included in JDK 17. `jcmd <pid> Thread.print -l` is a convenient way to capture a dump with lock details; `jstack -l <pid>` is an alternative.

**How does `BLOCKED` differ from `WAITING`?**  
`BLOCKED` is waiting to acquire an intrinsic monitor to enter a `synchronized` region. `WAITING` is waiting indefinitely for an event, such as `Object.wait`, `Thread.join`, or `LockSupport.park`.

**Why are threads waiting on ReentrantLock usually WAITING instead of BLOCKED?**  
`ReentrantLock` uses a park/unpark-based synchronizer, not the intrinsic monitor of `synchronized`. Use `Thread.print -l` to inspect ownable synchronizer ownership.

**Do many WAITING threads indicate a deadlock?**  
No. Workers waiting on queues, schedulers, or conditions can be normal. A deadlock requires a cycle of threads waiting on resources held by each other.

**Can a single thread dump detect a deadlock?**  
HotSpot can print a Java-level deadlock report when it detects a monitor or ownable synchronizer cycle. However, dumps do not cover deadlocks in databases, native code, or distributed systems.

**How many thread dumps should I capture?**  
Three snapshots spaced roughly 5–10 seconds apart is a practical starting point for many incidents, though you should adjust for normal processing times, workload type, and impact.

**Does a thread dump show which thread consumes the most CPU?**  
Some formats include CPU time, but identifying hot threads reliably requires comparing multiple snapshots and using tools like JFR or an OS profiler.

**Can I capture a dump when the JVM is unresponsive?**  
You can usually still try `jcmd` or OS signals, though success depends on JVM state, the attach mechanism, permissions, and runtime environment. If the JVM is deeply stuck or unresponsive, OS-level diagnostics may be needed.

**Do thread dumps replace JFR?**  
No. Dumps are stack/lock snapshots; JFR records events over time. The two tools complement each other.

## 18. Official References

- [Java SE 17 Tool Specifications — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): syntax for sending diagnostic commands to a running JVM.
- [Java SE 17 Tool Specifications — jstack](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html): capturing Java thread stack traces.
- [Java SE 17 API — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): definitions of thread states.
- [Java SE 17 API — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): querying threads and detecting deadlocks.
- [Java SE 17 API — ThreadInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): thread details, held monitors, and synchronizers.
- [Java SE 17 API — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): ownable synchronizer lock.
- [Java Flight Recorder Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html): configuring and using JFR to record runtime events.

**Guiding Principle:** Capture thread dumps with `jcmd <pid> Thread.print -l`, read states and stack traces, identify the monitor/synchronizer a thread is waiting on, and locate the lock owner. Compare multiple snapshots to distinguish normal waiting from sustained contention or stalled progress; use JFR, logs, and system metrics to verify the root cause before changing code.
