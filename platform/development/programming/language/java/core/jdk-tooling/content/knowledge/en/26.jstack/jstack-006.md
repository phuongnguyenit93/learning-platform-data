# Analyzing Blocked Threads with jstack

## 1. What is a blocked thread?

In Java, a thread is in the `BLOCKED` state when it is waiting to acquire an intrinsic monitor to enter or re-enter a `synchronized` block or method. A monitor is the synchronization mechanism the JVM uses to protect a section of code so that only one thread can own it at a time.

For example, if thread A is executing inside `synchronized (lock)`, thread B must wait if it tries to enter another `synchronized (lock)` block using the same object. While it has not yet acquired the monitor, thread B has the `BLOCKED` state.

A blocked thread is not necessarily a bug. A brief lock wait can be normal behavior when multiple threads update the same data structure. It becomes an issue worth investigating when wait times grow, the number of blocked threads increases, requests fail to complete, or throughput drops.

`jstack` captures a thread dump to identify which threads are waiting, which thread holds the monitor, the stack traces of both sides, how many workers are affected, and whether contention persists across multiple snapshots.

## 2. Distinguishing BLOCKED from other thread states

| State | Meaning | Example |
|---|---|---|
| `RUNNABLE` | The thread is executing or ready to be scheduled CPU time by the OS. | Running application code or a native call. |
| `BLOCKED` | Waiting to acquire an intrinsic monitor to enter `synchronized`. | Thread B waiting for a monitor held by thread A. |
| `WAITING` | Waiting indefinitely for another action. | `Object.wait()`, `Thread.join()` without a timeout, `LockSupport.park()`. |
| `TIMED_WAITING` | Waiting for a specified period of time. | `Thread.sleep()`, `Object.wait(timeout)`, `Thread.join(timeout)`. |

Key points:

- A thread calling `Object.wait()` releases the monitor it holds while waiting. When woken up, it must re-acquire the monitor before continuing; while waiting to re-acquire the monitor, it may be in the `BLOCKED` state.
- `Thread.sleep()` does not release an intrinsic monitor. If a thread calls sleep inside `synchronized`, it continues holding the lock for the entire sleep duration.
- `BLOCKED` describes waiting for an intrinsic monitor, not every type of lock wait in Java.
- A thread waiting on `ReentrantLock.lock()` typically parks via `LockSupport` and may appear as `WAITING` or `TIMED_WAITING`, not necessarily `BLOCKED`.

Do not conclude that a thread is stuck based solely on its state name. Inspect the stack trace, lock owner, wait duration, and subsequent snapshots.

## 3. Common causes of blocked threads

A thread holding a monitor for a long time can force many other threads to wait. Common causes include:

**Overly long critical section.** A `synchronized` block performs too much work, processes a large collection, or calls many other methods.

**I/O or external calls inside a lock.** A thread holds a monitor while calling a database, HTTP service, reading a file, or waiting on another resource. Dependency response times can extend how long the lock is held.

**Inappropriate sleep or wait.** Calling `Thread.sleep()` inside a `synchronized` block holds the monitor during the sleep. This can block every thread that needs the same monitor.

**Multiple threads contending on the same object.** A global lock or a shared object across many requests can become a bottleneck.

**Nested locks acquired in inconsistent order.** Two threads acquiring multiple monitors in opposite orders can cause a deadlock.

**Callbacks calling back into shared code.** A callback or listener invoked while a lock is still held can acquire additional locks and expand the dependency chain.

**Blocked processing in a thread pool.** If many workers are blocked together, the pool can run out of available threads, forcing new requests to wait even while CPU usage remains low.

## 4. Identifying the JVM and capturing a thread dump

First, find the application's PID:

~~~bash
jcmd -l
~~~

Example:

~~~text
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

Capture a basic thread dump:

~~~bash
jstack 18420
~~~

Capture additional monitor, lock, and ownable synchronizer information:

~~~bash
jstack -l 18420
~~~

In JDK 24, `jstack` supports:

| Option | Meaning |
|---|---|
| `-l` | Long listing; prints additional lock information. |
| `-e` | Extended listing; prints additional extended thread information. |
| `-h` or `-?` | Displays help. |

Examples:

~~~bash
jstack -e 18420
jstack -h
~~~

On Windows PowerShell, save the dump to a file:

~~~powershell
jstack 18420 | Out-File -Encoding utf8 thread-dump.txt
jstack -l 18420 | Out-File -Encoding utf8 thread-dump-locks.txt
~~~

On Linux/macOS:

~~~bash
jstack 18420 > thread-dump.txt
jstack -l 18420 > thread-dump-locks.txt
~~~

`jstack` attaches to a JVM on the same machine. The user running the tool usually must match the user running the JVM, the JVM must allow the Attach mechanism, and the PID must be visible in the environment where the command runs. In containers, check the PID namespace and attach permissions.

## 5. Reading thread headers and states

A thread dump typically has headers like:

~~~text
"worker-7" #42 prio=5 os_prio=0 cpu=18.75ms elapsed=32.41s
  tid=0x... nid=0x... waiting for monitor entry
  java.lang.Thread.State: BLOCKED (on object monitor)
~~~

Common fields:

- The name in quotes is the thread name.
- `#42` is the thread's sequence number in the JVM.
- `prio` is the priority.
- `cpu` and `elapsed` are timing details on supported JDKs.
- `tid` is the thread identifier in the JVM.
- `nid` is the native thread ID.
- `waiting for monitor entry` indicates the thread is waiting to enter a monitor.
- `java.lang.Thread.State: BLOCKED` is the Java thread state.

PID, thread ID, lock address, and CPU time values change across runs. Use them to correlate data within the same dump, not as fixed identifiers across restarts.

## 6. Using jstack -l to find the thread holding a lock

In a long listing, the key lines typically look like:

~~~text
"demo-blocked-contender" #36 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at BlockedThreadDemo.lambda$main$1(BlockedThreadDemo.java:32)
        - waiting to lock <0x000000011f019370> (a java.lang.Object)

"demo-lock-holder" #35 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Thread.java:513)
        - locked <0x000000011f019370> (a java.lang.Object)
~~~

Both entries reference the same monitor address:

- Thread `demo-blocked-contender` is waiting to acquire monitor `0x...`.
- Thread `demo-lock-holder` owns that monitor.
- The holder's stack trace shows the code holding the lock.
- The contender's stack trace shows the code trying to enter the synchronized block.

This is how you identify the lock owner in a dump: find the `waiting to lock` line on the blocked thread, note the monitor address, and then search for the thread with a `locked` line for that same address.

Addresses in examples are illustrative only. In a real dump, match the exact address string within the same file.

Do not confuse `waiting to lock` with `waiting on`. A thread calling `Object.wait()` typically shows wait/notify monitor waiting info and releases the monitor while waiting. A `BLOCKED` thread needs to acquire the monitor to enter a synchronized block.

## 7. Distinguishing blocked threads from lock-holding threads

In a contention scenario, the blocked thread and the thread causing the wait play different roles:

| Role | Indicator in dump | Question to answer |
|---|---|---|
| Blocked thread | `BLOCKED`, `waiting to lock <id>` | What operation is the thread trying to perform? |
| Lock-holding thread | `- locked <id>` | In which method is the thread holding the lock? |
| Other waiting threads | Same `waiting to lock <id>` | How many requests or workers are affected? |

For example, a request-handling thread might hold a monitor while calling an external service. Ten other threads wait on the same monitor. Reading only the stacks of the ten blocked threads tells you they are waiting, but not why. The lock-holding thread's stack reveals the long-running work inside the critical section.

Therefore, always inspect both the waiting threads and the lock owner. If the owner does not appear clearly in the dump, check the entire monitor/synchronizer output, take another snapshot, and consider whether the lock is managed by a library or native code.

## 8. Java 17 example: one thread holding a lock, one thread blocked

Create `BlockedThreadDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class BlockedThreadDemo {
    private static final Object SHARED_LOCK = new Object();

    public static void main(String[] args) throws Exception {
        CountDownLatch lockHeld = new CountDownLatch(1);
        CountDownLatch contenderStarted = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (SHARED_LOCK) {
                System.out.println("holder acquired lock");
                lockHeld.countDown();

                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-holder");

        Thread contender = new Thread(() -> {
            try {
                lockHeld.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            System.out.println("contender attempting lock");
            contenderStarted.countDown();

            synchronized (SHARED_LOCK) {
                System.out.println("contender acquired lock");
            }
        }, "demo-blocked-contender");

        holder.start();
        lockHeld.await();
        contender.start();
        contenderStarted.await();

        System.out.println("BlockedThreadDemo ready");
        Thread.currentThread().join();
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 BlockedThreadDemo.java
java BlockedThreadDemo
~~~

Stdout before taking the dump:

~~~text
holder acquired lock
contender attempting lock
BlockedThreadDemo ready
~~~

The program intentionally has the holder thread sleep inside the `synchronized` block. The sleeping thread still holds `SHARED_LOCK`. The contender thread has started running but cannot enter the synchronized block, so it is in the `BLOCKED` state.

In another terminal, find the PID with `jcmd -l` and take a dump:

~~~bash
jstack -l 18420
~~~

Verified output on JDK 24.0.2 shows:

~~~text
"demo-lock-holder" ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
   - locked <0x...> (a java.lang.Object)

"demo-blocked-contender" ...
   java.lang.Thread.State: BLOCKED (on object monitor)
   - waiting to lock <0x...> (a java.lang.Object)
~~~

The lock addresses on both lines match. This confirms the contender is waiting for the monitor owned by the holder. After practicing, stop the sample program in the terminal or terminate the process with an OS tool; do not run this intentional lock-holding example in production.

## 9. Why a BLOCKED thread does not automatically mean deadlock

Lock contention occurs when one thread holds a lock and other threads must wait. If the owner finishes its work and releases the lock, waiting threads proceed one by one.

Deadlock is a more severe case: there is a dependency cycle where each thread holds one resource and waits for a resource held by another thread. No thread in the cycle can make progress on its own.

Two-lock deadlock example:

- Thread A holds lock A and waits for lock B.
- Thread B holds lock B and waits for lock A.

In a thread dump, the JVM can detect and print:

~~~text
Found one Java-level deadlock:
=============================

"thread-A":
  waiting to lock monitor ...,
  which is held by "thread-B"

"thread-B":
  waiting to lock monitor ...,
  which is held by "thread-A"
~~~

A single blocked thread does not constitute a deadlock. Multiple threads waiting on one owner can also be simple contention if the owner can still finish and release the lock.

The absence of `Found one Java-level deadlock` does not guarantee the system is free of all deadlocks. Wait cycles across databases, networks, queues, or application protocols can fall outside what the JVM detects.

## 10. Identifying sustained lock contention across multiple dumps

A thread dump is a point-in-time snapshot. To tell whether a thread is blocked for a long time or only waiting briefly, capture multiple snapshots a few seconds apart.

Linux/macOS:

~~~bash
PID=18420
jstack -l "$PID" > thread-1.txt
sleep 5
jstack -l "$PID" > thread-2.txt
sleep 5
jstack -l "$PID" > thread-3.txt
~~~

Windows PowerShell:

~~~powershell
$targetPid = 18420
1..3 | ForEach-Object {
    $file = "thread-$_.txt"
    jstack -l $targetPid | Out-File -Encoding utf8 $file
    Start-Sleep -Seconds 5
}
~~~

When comparing dumps:

1. Look for the same thread names and stack frames.
2. Check whether the threads remain `BLOCKED` across snapshots or have transitioned to another state.
3. Compare the monitor address each thread is waiting on in each dump.
4. Find the corresponding owner and check whether the owner's stack trace is making progress.
5. Count how many threads are waiting on the same monitor.
6. Correlate with request latency, queue depth, throughput, and CPU.

Signs of sustained contention include multiple threads blocked on the same monitor across several snapshots, the owner remaining in the same critical section, and rising request latency. If the owner changes or threads quickly leave `BLOCKED`, it may be short-lived contention.

Do not compare monitor addresses across JVM restarts as stable identifiers. Addresses can change when a process or object is recreated.

## 11. Assessing impact on thread pools and requests

Blocked threads reduce the number of workers available to handle requests. For example, if an executor has 20 workers and 15 are blocked on the same monitor, only 5 workers remain to do other work.

When reading a server application dump:

- Group threads by pool name, such as `http-nio-...-exec` or `pool-...-thread`.
- Check whether multiple workers are blocked at the same stack frame.
- Determine whether the monitor owner is handling a slow request or calling an external dependency.
- Check whether the executor queue is growing and new requests are waiting.
- Correlate dump timestamps with request logs and latency metrics.

Do not simply increase the thread pool size to mask the problem. If every worker needs the same lock, adding more workers may only increase the number of waiting threads and stack memory usage without improving throughput.

## 12. How to fix the root causes of blocked threads

The right fix depends on what the lock-holding code is doing:

**Shorten the critical section.** Hold the lock only around the shared state update. Perform independent calculations, data transformations, and request preparation outside the synchronized block.

**Avoid I/O or external calls while holding a monitor.** File I/O, database queries, HTTP calls, or queue waits can take unpredictable amounts of time. If needed, take a data snapshot under the lock and call the dependency after releasing it.

**Do not sleep inside a synchronized block.** If a delay is needed, release the lock before waiting. `Thread.sleep()` does not release the monitor.

**Use a consistent lock acquisition order.** If multiple operations require two locks, all code paths must acquire them in the same global order to prevent wait cycles.

**Reduce sharing scope.** Split a global lock into per-resource or partitioned locks when correctness allows. Consider concurrent collections or immutable data to reduce manual synchronization.

**Use timeouts when the lock API supports them.** With `ReentrantLock`, `tryLock(timeout, unit)` lets you bail out or retry if the lock cannot be acquired within the specified time. The intrinsic monitor of `synchronized` does not support timed acquisition.

**Do not hold locks across uncontrolled callbacks.** A callback can call back into other code and introduce additional lock dependencies. Consider copying the needed data and releasing the lock before invoking the callback.

## 13. Example of redesigning lock acquisition order

Suppose multiple methods need both `LOCK_A` and `LOCK_B`. A simple rule is to always acquire A before B:

~~~java
private static final Object LOCK_A = new Object();
private static final Object LOCK_B = new Object();

static void updateBoth() {
    synchronized (LOCK_A) {
        synchronized (LOCK_B) {
            updateSharedState();
        }
    }
}
~~~

Every code path accessing both locks must follow the same order. If another method acquires B and then A, the deadlock risk remains.

For code with many locks, you can define an ordering based on resource IDs or a fixed object order. Enforcing a consistent order eliminates wait cycles caused by those locks.

This snippet illustrates the synchronization rule; the `updateSharedState()` method must be provided by the application. Avoid calling slow code or I/O inside both lock blocks if it can be moved outside.

## 14. Distinguishing BLOCKED on synchronized from waiting on ReentrantLock

`BLOCKED` in Java thread states specifically describes waiting for an intrinsic monitor, typically associated with `synchronized`.

With `ReentrantLock`, a thread waiting for a lock usually parks. The thread dump may show a stack like:

~~~text
java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
    at java.util.concurrent.locks.ReentrantLock.lock(...)
~~~

When using `jstack -l`, the `Locked ownable synchronizers` section can help identify which lock a thread owns. Match the waiting thread's stack trace against the synchronizer info of the lock-holding thread.

Do not ignore `WAITING (parking)` threads just because you are investigating blocked threads. In an application, both intrinsic monitors and explicit locks can cause contention; their states and dump representations simply differ.

## 15. Using jcmd and other tools for cross-checking

`jcmd` provides the `Thread.print` diagnostic command to print a thread dump:

~~~bash
jcmd 18420 Thread.print
jcmd 18420 Thread.print -l
~~~

Save a thread dump to a file:

~~~bash
jcmd 18420 Thread.dump_to_file -format=plain thread-dump.txt
jcmd 18420 Thread.dump_to_file -format=json thread-dump.json
~~~

In JDK 24, `Thread.dump_to_file` supports plain or JSON formats. The `-overwrite` option allows overwriting an existing file; by default it does not overwrite. Check `jcmd PID help Thread.dump_to_file` to confirm syntax on the target JVM.

Other diagnostic tools serve different purposes:

| Tool | Primary data | When to use |
|---|---|---|
| `jstack` | Thread state, stack trace, monitors, and deadlocks at capture time. | Investigating blocked threads, lock contention, and deadlocks. |
| `JFR` | Stream of runtime events over time. | Investigating latency, allocations, GC, I/O, and thread activity. |
| Heap dump | Object graph and heap state at a point in time. | Investigating memory leaks or abnormal heap growth. |
| CPU profiler | CPU samples or time by method. | Finding CPU-intensive methods. |

A thread dump does not show all objects occupying the heap and does not replace a CPU profiler. Choose the tool based on the symptoms; you can combine thread dumps with JFR to understand both the current state and prior event history.

## 16. Common mistakes when analyzing blocked threads

| Symptom or wrong conclusion | Cause | How to handle |
|---|---|---|
| Seeing one BLOCKED thread and concluding deadlock | BLOCKED only means waiting for a monitor; the owner may release it soon. | Identify the owner and take more snapshots before concluding. |
| Reading only the waiting thread's stack trace | Missing the code holding the monitor. | Find the same monitor ID in the owner's `- locked` lines. |
| Seeing the holder in TIMED_WAITING and assuming it holds no lock | `Thread.sleep()` does not release monitors. | Check `- locked` lines and sleep calls inside synchronized blocks. |
| Seeing no BLOCKED threads while requests still wait on locks | Threads may be waiting on a ReentrantLock or synchronizer via park. | Look for `WAITING (parking)`, `LockSupport.park`, and ownable synchronizers. |
| Many workers blocked while CPU is low | Threads waiting on locks do not consume much CPU while waiting. | Check the owner, critical section, queue depth, and latency. |
| Owner missing from filtered output | Output was truncated or the owner is elsewhere in the dump. | Read the full dump and search for the same monitor ID. |
| Lock addresses differ across snapshots | Objects or processes changed; addresses are not stable IDs. | Match thread names, stacks, and locks within each individual dump. |
| Increasing thread pool size does not improve throughput | New workers contend on the same lock. | Fix the critical section and the synchronization bottleneck. |
| No Java-level deadlock line | It is contention, or a deadlock outside JVM-detected monitors. | Check lock ordering, databases, queues, networks, and multiple snapshots. |
| Thread dump tool fails to connect to JVM | Wrong PID, different user, Attach disabled, or wrong PID namespace. | Check `jcmd -l`, permissions, and the attach environment. |

## 17. Production investigation workflow for blocked threads

1. Record when requests slowed down along with latency, throughput, and queue depth.
2. Identify the PID, host/container, JDK version, and JVM user.
3. Capture a thread dump with `jstack -l PID` to include lock information.
4. Find `BLOCKED` threads and group them by monitor ID.
5. For each monitor with multiple waiting threads, find the owner with `- locked` for that same ID.
6. Read the owner's stack trace to identify the critical section holding the lock.
7. Capture two or three more snapshots a few seconds apart to confirm sustained contention.
8. Correlate the owner with logs, requests, database, network, and dependency metrics.
9. Fix the code or configuration based on the actual root cause; avoid blindly increasing thread pool sizes.
10. Retest under representative load and collect new thread dumps to confirm reduced wait times.

Thread dumps can contain package names, class names, method names, file paths, and internal details. Store files with appropriate permissions, limit retention, and review them before sharing outside your organization.

## 18. Pre-closure investigation checklist

- Identified the correct JVM and PID.
- Used `jstack -l` to capture monitor information.
- Distinguished `BLOCKED` threads from `RUNNABLE`, `WAITING`, and `TIMED_WAITING`.
- Found the monitor ID that threads are waiting on.
- Found the owner holding the same monitor ID.
- Read the stack traces of both waiting threads and the lock-holding thread.
- Checked for `Thread.sleep()` inside synchronized blocks.
- Considered `ReentrantLock` and ownable synchronizers if no `BLOCKED` threads are obvious.
- Captured multiple snapshots when needed to confirm sustained contention.
- Checked for deadlocks and external non-JVM dependencies.
- Correlated waiting thread counts with queue depth, latency, and throughput.
- Identified a fix for the critical section or lock ordering.
- Retested after fixing and protected dump files according to data policies.

## 19. References

- [The jstack Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstack.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Thread.State — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.State.html)
- [Intrinsic Locks and Synchronization — Java Tutorials](https://docs.oracle.com/javase/tutorial/essential/concurrency/locksync.html)

`jstack` helps investigate blocked threads by combining the `BLOCKED` state, stack traces, and monitor information from `jstack -l`. Identify both the waiting threads and the lock-holding thread, compare multiple snapshots, and fix the critical section or lock acquisition order based on the confirmed root cause.