# 8.5 Reading held monitors, awaited locks, and ownable synchronizers

When a Java application hangs, times out, or drops in throughput, a thread dump often contains lines such as `- locked <0x...>`, `- waiting to lock <0x...>`, `- waiting on <0x...>`, or `- parking to wait for <0x...>`. Just a single word difference can completely change the diagnosis: **whether the thread holds a monitor**, **is contending to enter a monitor**, **is waiting for notification after `Object.wait()`**, or **is parked by a `java.util.concurrent`-style synchronization mechanism**.

For example, a thread in `BLOCKED` waiting to acquire a monitor is not necessarily deadlocked; it might just be waiting a few milliseconds. A thread in `WAITING (parking)` is not necessarily idle: it may be waiting on a `ReentrantLock` held by another thread, or waiting on a `Condition`, `CountDownLatch`, or pool work. A thread carrying `- locked <...>` owns the monitor at capture time, yet you **cannot** conclude that monitor is the sole cause of latency without connecting the “who is waiting on whom” edge.

This lesson provides a systematic way to read three groups of information in HotSpot/JDK 17+ thread dumps:

1. **Held monitors:** `synchronized` and `- locked` lines; identifying the owner thread and where the lock was acquired.
2. **Awaited locks:** `waiting to lock`, `waiting on`, `parking to wait for`, along with thread state and owner information if available.
3. **Ownable synchronizers:** exclusive-ownership synchronizers such as `ReentrantLock` managed via `AbstractOwnableSynchronizer`; reading the `Locked ownable synchronizers` section and explaining how they differ from object monitors.

By the end of this lesson, you will know how to distinguish **contention, waiting, long holds, and deadlocks** as well as cases with **insufficient evidence**; read `ThreadInfo`/`ThreadMXBean` via Java APIs; choose the right tools and avoid taking excessive dumps; and protect sensitive data before sharing.

## 1. Concept map: thread, monitor, and synchronizer

### 1.1 What is a Java monitor?

Every Java object can serve as a monitor for the `synchronized` mechanism. When a thread executes:

```java
synchronized (sharedObject) {
    doCriticalWork();
}
```

the thread **must acquire `sharedObject`'s monitor before entering the block**. If thread A holds the monitor and thread B tries to enter the same monitor, B must wait. On common Java/HotSpot platforms, B will show state `BLOCKED (on object monitor)` at capture time; A may be `RUNNABLE`, `TIMED_WAITING`, or `WAITING` depending on what work it is performing **while still holding the monitor**.

Therefore, when searching for the lock owner, **do not look only at `RUNNABLE` threads**. The owner thread may be sleeping, waiting on I/O, waiting on a latch, or running slowly while still inside `synchronized`.

### 1.2 What is an ownable synchronizer?

In `java.util.concurrent.locks`, `AbstractOwnableSynchronizer` provides the concept of a synchronizer with an **exclusively owning thread**. `AbstractQueuedSynchronizer` and several lock mechanisms use this information to manage/observe ownership. `ReentrantLock` is the classic example: the thread that successfully calls `lock()` owns the lock until it calls `unlock()` the matching number of times.

Key differences:

- `synchronized` uses a JVM-managed **object monitor**, directly tied to the object used as the lock.
- `ReentrantLock` uses a library-level synchronization mechanism; when contended, waiting threads typically **park** rather than entering the `BLOCKED` state reserved for monitor entry.
- In a HotSpot thread dump, an ownable synchronizer may appear as **the lock's internal object**, such as an instance of `ReentrantLock$NonfairSync`, rather than the outer `ReentrantLock` wrapper object.
- Not every object in `java.util.concurrent` is an ownable synchronizer: `CountDownLatch` and `Semaphore` are waiting/permit mechanisms that do not equate to exclusive ownership in the way `ReentrantLock` does.
- `ReentrantReadWriteLock` has differing semantics between read and write locks; do not conclude “every synchronizer in every implementation always displays full owner info”.

### 1.3 Three questions to ask separately

| Question | Required data | Why it matters |
| --- | --- | --- |
| **What is this thread waiting for?** | Thread state, `getLockInfo()`, stack frames, `waiting to lock/on/parking` | Distinguishes monitor entry, condition wait, and parking |
| **What is this thread holding?** | `- locked`, `MonitorInfo[]`, `Locked ownable synchronizers`, `LockInfo[]` | Locates monitor/ownable lock owners in the snapshot |
| **Who is waiting on whom?** | Lock object identity, `getLockOwnerId()`, chains, and dump timestamp | Maps ownership relationships, identifies cycles or bottlenecks |

A single stack line answers very little. You must **read both the waiting thread's block and the owner thread's block**, ideally across multiple intentionally spaced snapshots.

## 2. Common keywords in a HotSpot thread dump

A **simulated** excerpt (thread names, addresses, and line numbers are for learning only, not from an actual dump run):

```text
"worker-B" #42 prio=5 tid=0x... nid=0x... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at demo.InventoryService.update(InventoryService.java:72)
    - waiting to lock <0x0000000710101010> (a java.lang.Object)
    at demo.InventoryService.process(InventoryService.java:45)

"worker-A" #41 prio=5 tid=0x... nid=0x... waiting on condition
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
    at demo.InventoryService.update(InventoryService.java:81)
    - locked <0x0000000710101010> (a java.lang.Object)
```

The `0x...` notation in the example is **an internal VM/tool identifier representation for a single dump**, not an address accessible from Java and not an immutable ID across restarts. The other `...` markers indicate omitted details in the synthetic example, not mandatory syntax across every dump.

From this excerpt, you can form the hypothesis:

- B is `BLOCKED` because it wants to acquire the monitor of the object with identifier `<0x0000000710101010>`.
- A is inside `synchronized` holding **that exact identifier**.
- A is sleeping inside the critical section, so B cannot enter until A releases the lock.
- This is **lock contention/long hold**; **not yet a deadlock**, because there is no evidence A is waiting on a lock held by B.

**Do not** assert “thread B is permanently hung” from a single snapshot; if A is about to finish sleeping, B may proceed normally. Timing data and multiple snapshots are required.

### 2.1 Meaning of the markers

| Marker in dump | Practical reading | Must not infer |
| --- | --- | --- |
| `- locked <id>` | Thread currently holds the corresponding monitor at observation time | That this thread is always the root cause |
| `- waiting to lock <id>` | Thread is contending to acquire the monitor to **enter `synchronized`** | Guaranteed deadlock |
| `- waiting on <id>` | Thread is awaiting `Object.wait()`/notification on the associated monitor | That the thread still holds **the monitor it is waiting on** |
| `- parking to wait for <id>` | Thread is using park/`LockSupport` with a blocker object | That the blocker is necessarily owned by another thread |
| `Locked ownable synchronizers:` | Section listing ownable synchronizers currently owned by the thread | A list of all locks in general |
| `- None` in ownable section | No synchronizer of this kind recorded in the snapshot | That the thread holds no monitors at all |
| `java.lang.Thread.State: BLOCKED` | Waiting for monitor entry | Purely waiting for the OS CPU scheduler |
| `java.lang.Thread.State: WAITING/TIMED_WAITING` | Waiting/parking/Object.wait/sleeping depending on stack | Definitely idle and holding no resources |
| `RUNNABLE` | Java RUNNABLE state at snapshot time | Continuously burning CPU |

Displayed strings, marker placement, options, and which threads appear in a dump can vary by JDK/VM, especially with **virtual threads** in newer Java releases. Base your reading on the actual JVM and supplemental evidence rather than writing a parser expecting every line to match one fixed regex.

## 3. Held monitors: reading - locked lines

### 3.1 A monitor owner is not necessarily executing

A thread that successfully enters a `synchronized(lock)` block holds the monitor until it exits the block, even if code inside the block:

- Calls `Thread.sleep(...)`.
- Waits on a blocking I/O API.
- Waits on `CountDownLatch.await()`.
- Calls `LockSupport.park()`.
- Performs long CPU computation.
- Accesses a DB/network without an appropriate timeout.

None of these operations **automatically release the monitor**; they can leave other threads `BLOCKED`. Important exception: **`Object.wait()` releases the monitor of the specific object being waited on** during the wait, and must reacquire it before returning. It does **not** automatically release any other monitors the thread also holds.

### 3.2 Reading stack frames near the marker

Hypothetical example:

```text
"owner-thread" ...
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
    at demo.RemoteCall.awaitResponse(RemoteCall.java:118)
    at demo.Service.criticalSection(Service.java:60)
    - locked <0x0000000710111000> (a demo.Service)
```

The thread acquired `demo.Service`'s monitor in `criticalSection`, then parked inside an external call. When many other threads wait on the same ID, the question to investigate is **why the critical section lasts so long**, not merely “why do we see WAITING”.

A `- locked` line displayed near a frame helps locate where `synchronized` was acquired. With JIT/optimization or certain frame types, tool presentation may not map 1-to-1 to exact source lines; read the whole call stack and check against the source version.

### 3.3 What does MonitorInfo provide?

`java.lang.management.MonitorInfo` extends `LockInfo` and contains:

- `getClassName()`: class name of the monitor object.
- `getIdentityHashCode()`: identity hash code reported by the JVM; **not** a stable memory address.
- `getLockedStackDepth()`: stack frame index where the monitor was locked, which may be negative if unavailable.
- `getLockedStackFrame()`: the frame where the lock was acquired, which may be `null` if unavailable.

`ThreadInfo.getLockedMonitors()` returns the list of object monitors held by the thread **if locked monitor usage was requested at capture time and supported by the JVM**. An empty array can also result from *not requesting that information*, rather than proving the thread “definitely owns no monitors” in all contexts.

### 3.4 One thread can hold multiple monitors

Example:

```java
synchronized (orderLock) {
    synchronized (inventoryLock) {
        updateInventory();
    }
}
```

While inside the inner block, the thread holds both monitors. If another thread waits on `inventoryLock`, find the owner carrying `- locked <inventory-id>`; if that owner in turn waits on a third lock, keep following the chain. Acquiring multiple locks in inconsistent order can cause a deadlock if a cycle forms.

**Do not** rely on the order of `- locked` lines in a dump to infer the absolute acquisition order. When looking for lock-order inversion, cross-check the stack/source code and wait edges in the snapshot.

## 4. Awaited locks: distinguishing waiting to lock, waiting on, and parking

### 4.1 waiting to lock — contending for monitor entry

With `synchronized(lock)`, a thread wanting to enter while the lock is held can appear as:

```text
"contender" ...
   java.lang.Thread.State: BLOCKED (on object monitor)
    at demo.Service.criticalSection(Service.java:44)
    - waiting to lock <0x0000000710123000> (a java.lang.Object)
```

This is a **wait edge for acquiring a monitor**. To find the owner, search for another thread block containing `- locked <0x0000000710123000>` in **the same snapshot**, or use `ThreadInfo.getLockOwnerId()` if provided by the JVM. If no owner is visible, possibilities include: truncated dump, the thread just released the monitor, mismatched identities from mixing multiple snapshots, incomplete tool output, or an owner outside the collected thread set.

When multiple contenders wait for the same monitor, that is a **hot contention point**. Do not infer “every BLOCKED thread is waiting on each other”: dozens of threads may all be waiting on a single owner.

### 4.2 waiting on — Object.wait has monitor-release semantics

With code:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

While in `Object.wait()`, the thread **releases the `lock` monitor** and enters a state awaiting notification or timeout. Once notified or otherwise woken, it **must reacquire the `lock` monitor before `wait` returns**, and may therefore become `BLOCKED` while attempting to reacquire.

A simulated dump might show:

```text
"waiter" ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(Native Method)
    - waiting on <0x0000000710134000> (a java.lang.Object)
```

**Do not look for a `- locked` line on this same thread for the exact monitor it is calling `wait()` on** and conclude the waiter still owns it. If you see the thread holding a **different monitor**, that can happen because `wait()` releases only the monitor on which it was called, not all held monitors.

Distinguish `notify()`/`notifyAll()` from **actually reacquiring the monitor after wakeup**: being notified does not guarantee the waiter resumes running immediately.

### 4.3 parking to wait for — the park mechanism

`LockSupport.park(blocker)` and synchronization primitives using parkers can show:

```text
"reentrant-waiter" ...
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
    - parking to wait for <0x0000000710145000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

This is typically a thread waiting on **a `ReentrantLock`'s AQS synchronizer**. It may show `WAITING` or `TIMED_WAITING` depending on whether the path has a timeout and the implementation. **It does not have to be `BLOCKED`** because `Thread.State.BLOCKED` is for monitor entry. If you need to find the owner, inspect the ownable synchronizers section of other threads or the owner ID provided by `ThreadInfo` (if available).

However, `park` is also used in:

- Thread pools waiting for work.
- `Condition.await()`.
- `CountDownLatch.await()` or `Semaphore.acquire()`.
- `CompletableFuture.join()` or completion-waiting mechanisms.
- Library scheduling/coordination.

Thus, a displayed blocker object **does not mean an exclusive owner always exists**. Read the stack to identify the primitive type.

### 4.4 WAITING is not always a bug

A thread pool worker awaiting a task, a scheduler thread awaiting a deadline, a dispatcher awaiting a queue, or a thread awaiting a condition by design can routinely be in `WAITING`. Seeing many WAITING threads **does not by itself prove deadlock**; correlate throughput, queue buildup, latency, duration, and wake-up conditions.

Conversely, a `RUNNABLE` thread may be stuck in native I/O or making no progress; looking only at state does not prove the system is healthy either.

## 5. Ownable synchronizers: reading the dedicated thread dump section

### 5.1 Why is the Locked ownable synchronizers section needed?

Monitor locking and `java.util.concurrent.locks` use different mechanisms. If you only check `- locked` for `synchronized`, you can miss held `ReentrantLock` instances. On HotSpot, the option that prints `java.util.concurrent` lock details reveals a list like:

```text
"lock-holder" ...
   java.lang.Thread.State: WAITING (parking)
    ...
   Locked ownable synchronizers:
    - <0x0000000710156000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)

"lock-contender" ...
   java.lang.Thread.State: WAITING (parking)
    ...
    - parking to wait for <0x0000000710156000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
   Locked ownable synchronizers:
    - None
```

This is an **illustrative snippet** whose exact formatting may vary by version, not a line-by-line guarantee for a specific JDK. When the blocker identity and the synchronizer held by an owner match within **the same dump**, there is a strong clue of a wait edge, which should be verified with `ThreadInfo`/stacks if available.

**Do not** confuse the outer `ReentrantLock` wrapper with the internal `Sync` object. In HotSpot, the listing may print `java.util.concurrent.locks.ReentrantLock$NonfairSync` or the corresponding class depending on fairness/implementation. Addresses in the dump and Java identity hash codes must not be assumed convertible via simple arithmetic.

### 5.2 Why reading only one thread's block is insufficient

A thread waiting on a `ReentrantLock` has an AQS/LockSupport stack, which does not necessarily contain the name of the thread currently holding the lock. Find the owner by:

1. Reading the waiting thread's `LockInfo`, if present.
2. Checking `getLockOwnerId()`/`getLockOwnerName()` when known to the JVM.
3. Matching the object identity against `getLockedSynchronizers()` of candidate owner threads within the snapshot.
4. Checking the stack where the owner is executing and the business code holding the lock.
5. Confirming the phenomenon with a later snapshot or instrumentation.

`getLockedSynchronizers()` returns `LockInfo[]`, containing class name and identity hash, **without the frame location where the lock was acquired like `MonitorInfo` provides**. Therefore, the owner's stack/source and code structure are still required to identify the critical section.

### 5.3 Not every lock is ownable

`AbstractOwnableSynchronizer` only provides the foundation for **recording an exclusive owner**. Some primitives such as semaphores allow multiple permits, and latches/cyclic barriers manage conditions without a mutex-style owner, so the “locked ownable synchronizers” list is not an **inventory of all blocking dependencies**. A `Condition.await()` temporarily releases its associated lock while waiting; the thread may be waiting for a signal rather than holding a mutex.

This section is especially important when debugging **thread pool starvation** or a system stalling due to missing tasks/notifications: there can be many WAITING/parking threads with **zero owner-lock-owner cycles**.

## 6. Choosing dump tools to observe the right lock types

### 6.1 jcmd Thread.print and -l

On HotSpot/JDK 21, check help first:

```bash
jcmd 4242 help Thread.print
jcmd 4242 Thread.print
jcmd 4242 Thread.print -l
```

`4242` is an **example PID**, not an actual discovered JVM. `Thread.print` prints stack traces; `-l` requests locks from `java.util.concurrent` if supported by the JVM/tool. On some JDKs, `-e` requests extended thread information; verify via `help Thread.print` on the actual target/JDK.

**Note two different commands:**

- `jcmd -l`: **lists JVMs** visible to the tool.
- `jcmd 4242 Thread.print -l`: **prints the thread dump** of a specific JVM and requests ownable lock info.

Confusing these two `-l` usages easily leads to collecting incomplete data.

### 6.2 jstack -l

On compatible JDKs/tools:

```bash
jstack -l 4242
```

`jstack -l` requests ownable synchronizer details; version and attach permissions still matter. On modern JDKs, Oracle recommends `jcmd` for most diagnostic tasks and checking command availability against the actual JDK.

Do not collect dumps by targeting the wrong PID, especially when a host runs multiple JVMs; verify process start time/instance, permissions, host/container PID namespace, and JDK build. If attach is disabled or the process has exited, the tool will not bypass those constraints.

### 6.3 ThreadMXBean.dumpAllThreads via Java API

Inside the current JVM:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.lang.management.ThreadInfo;

ThreadMXBean mx = ManagementFactory.getThreadMXBean();
if (mx.isObjectMonitorUsageSupported()
        && mx.isSynchronizerUsageSupported()) {
    ThreadInfo[] infos = mx.dumpAllThreads(true, true);
}
```

This is an **illustrative snippet** that belongs inside a method/class. `dumpAllThreads(true,true)` requests both locked monitors and locked ownable synchronizers. On Java 17, the method returns information on live **platform threads** exposed by the JVM; lock observation may not be supported by every JVM implementation and throws `UnsupportedOperationException` if an unsupported feature is requested.

If you do not need all threads, use `getThreadInfo(long[], boolean, boolean)` with identified IDs. Frequent capture, very deep stacks, or applications with thousands of threads can incur CPU, memory, and pause overhead; never treat dumping as completely free.

### 6.4 Notes on virtual threads in Java 21+

JDK 21 made virtual threads an official feature. `ThreadMXBean.dumpAllThreads(...)` and deadlock detection methods are documented for **platform threads**, not as a full inventory of all virtual threads. Thread dump tools have differing formats and display support for virtual threads across releases.

Therefore, when a service uses virtual threads, the absence of a task name in a platform-thread dump **does not prove that task does not exist or is not waiting on a lock**. You need tools/formats supporting virtual threads for the running JDK, JFR, or appropriate instrumentation; do not apply legacy HotSpot parsers blindly to newer outputs.

## 7. Reading ThreadInfo and ThreadMXBean at the API level

`ThreadInfo` is the Java data structure representing a thread snapshot at a point in time. Key methods:

| API | Meaning | Limitations to remember |
| --- | --- | --- |
| `getThreadName()` | Thread name | Can be set dynamically, may contain sensitive IDs |
| `getThreadId()` | Java thread ID | Not the OS PID or `nid` in dumps |
| `getThreadState()` | State at snapshot time | Can change immediately after capture |
| `getLockInfo()` | Lock/blocker object the thread is waiting on, if any | `null` if not in a supported waiting case |
| `getLockOwnerId()` | ID of thread owning the awaited object, if known | `-1` when there is no owner or owner is unknown |
| `getLockOwnerName()` | Owner name, if available | `null` does not prove there is no lock |
| `getLockedMonitors()` | Monitors held by the thread | Empty if not requested or none held |
| `getLockedSynchronizers()` | Ownable synchronizers held by the thread | Does not list every synchronization primitive |
| `getStackTrace()` | Captured stack trace | May be empty if not requested |
| `getBlockedCount()` | Number of times blocked trying to enter a monitor | Counter; does not give per-event duration |
| `getBlockedTime()` | Cumulative blocked time when contention monitoring is enabled | May be `-1` if metrics are unavailable |
| `getWaitedCount()` | Number of waits/parks per JVM semantics | Does not identify the owner of each wait |
| `getWaitedTime()` | Cumulative wait time when supported/enabled | May be `-1` and is not p99 latency |

### 7.1 A LockInfo does not mean the thread awaits an object with an owner

Per Javadoc, `getLockInfo()` can describe:

- A monitor that a `BLOCKED` thread is trying to enter.
- An object monitor on which a thread is calling `wait()` for notification.
- The blocker object of `LockSupport.park`, which may be an ownable synchronizer or a `Condition`.

For `Object.wait`, the object may **have no exclusive owner** while the thread is waiting, because the waiter released the monitor. For `LockSupport.park` on a latch/condition, the blocker may have no mutex-style owner. Therefore `getLockInfo()!=null` does not equate to “another thread currently holds the lock”.

`getLockOwnerId() == -1` indicates **no owner is identified by the API** or the awaited object has no owner. Do not print `-1` as a real thread ID, nor infer “there is never any contention” simply because one snapshot reports no owner.

### 7.2 Distinguishing class name, identity hash, and text address

`LockInfo` provides `getClassName()` and `getIdentityHashCode()` to describe the lock object. In HotSpot dumps, the `<0x...>` marker is typically a hex identifier distinct from `System.identityHashCode`; **do not force-match them by base conversion**. To correlate information across two sources, verify tool semantics, JVM build, timing, object identity, and stability.

Object identities are also unstable across restarts; the JVM can reuse addresses/hashes in certain contexts. Compare lock identities **within the same artifact/snapshot** and record timestamp/PID/JVM instance.

### 7.3 MonitorInfo and monitor acquisition site

`MonitorInfo.getLockedStackDepth()`/`getLockedStackFrame()` help answer “in which frame was the monitor acquired?” if the JVM supplies the data. This is a useful distinction compared to ownable `LockInfo`: **do not** expect `getLockedSynchronizers()` to provide the source line where `ReentrantLock.lock()` occurred.

You must consult the actual source code, optimizations, and full stack to verify a critical section. Do not conclude a line number in a dump equals the exact lock hold duration.

### 7.4 Contention metrics are not enabled by default on every JVM

`ThreadMXBean.isThreadContentionMonitoringSupported()` returns support status; `isThreadContentionMonitoringEnabled()` tells whether it is enabled. By default on many JVMs, blocked/waited elapsed times are not collected, so `getBlockedTime()`/`getWaitedTime()` can be `-1`. Enabling monitoring via `setThreadContentionMonitoringEnabled(true)` is a **runtime change with overhead** requiring operational approval; do not toggle it arbitrarily in a read-only demo.

Cumulative count/time are also not event-level latencies; when you need p95 lock wait time, instrument a histogram or use an appropriate profiler/JFR rather than dividing total time by count and calling it p99.

## 8. Complete Java 17+ example: creating contention and observing both lock types

The following program **uses only standard Java 17+ APIs**, creating **four simulated platform threads inside the same JVM**:

- One thread holds a `synchronized` monitor; another tries to enter the monitor, typically `BLOCKED`.
- One thread holds a `ReentrantLock`; another calls `lock()`, typically `WAITING (parking)`.
- The main thread calls `ThreadMXBean.getThreadInfo(ids,true,true)` and prints snapshot information.
- All locks are released in `finally`, with no intentional deadlock, no killing threads, and no attaching to another JVM.

There is a **default mode** explaining the model via deterministic stdout; `--live` creates the threads and reads live numbers so results depend on JDK/scheduler. This separates stable conceptual knowledge from **race-sensitive** live observations.

Save file `ThreadLockReadingDemo.java`:

```java
import java.lang.management.LockInfo;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class ThreadLockReadingDemo {
    static void printModel() {
        System.out.println("MONITOR_ENTRY=BLOCKED");
        System.out.println("OBJECT_WAIT=RELEASES_WAITED_MONITOR");
        System.out.println("REENTRANT_LOCK_WAIT=USUALLY_PARKING");
        System.out.println("OWNABLE_SECTION=LOCKED_OWNABLE_SYNCHRONIZERS");
        System.out.println("THREAD_DUMP=ONE_SNAPSHOT_NOT_DEADLOCK_PROOF");
    }

    static void awaitRelease(CountDownLatch release) {
        try {
            release.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    static void report(String alias, ThreadInfo info) {
        if (info == null) {
            System.out.println(alias + ".info=UNAVAILABLE");
            return;
        }

        LockInfo awaited = info.getLockInfo();
        System.out.println(alias + ".state=" + info.getThreadState());
        System.out.println(alias + ".waiting_lock_present=" + (awaited != null));
        System.out.println(alias + ".owner_known="
                + (info.getLockOwnerId() >= 0));
        System.out.println(alias + ".monitors_held="
                + info.getLockedMonitors().length);
        System.out.println(alias + ".ownable_held="
                + info.getLockedSynchronizers().length);
    }

    static void runLive() throws Exception {
        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        if (!mx.isObjectMonitorUsageSupported()
                || !mx.isSynchronizerUsageSupported()) {
            System.out.println("LIVE_LOCK_DETAILS=UNSUPPORTED");
            return;
        }

        Object monitor = new Object();
        ReentrantLock ownable = new ReentrantLock();
        CountDownLatch monitorReady = new CountDownLatch(1);
        CountDownLatch ownableReady = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread monitorOwner = new Thread(() -> {
            synchronized (monitor) {
                monitorReady.countDown();
                awaitRelease(release);
            }
        }, "demo-monitor-owner");

        Thread ownableOwner = new Thread(() -> {
            ownable.lock();
            try {
                ownableReady.countDown();
                awaitRelease(release);
            } finally {
                ownable.unlock();
            }
        }, "demo-ownable-owner");

        Thread monitorWaiter = new Thread(() -> {
            synchronized (monitor) {
                // Completes only after monitorOwner releases the monitor.
            }
        }, "demo-monitor-waiter");

        Thread ownableWaiter = new Thread(() -> {
            ownable.lock();
            try {
                // Completes only after ownableOwner unlocks.
            } finally {
                ownable.unlock();
            }
        }, "demo-ownable-waiter");

        try {
            monitorOwner.start();
            ownableOwner.start();

            if (!monitorReady.await(3, TimeUnit.SECONDS)
                    || !ownableReady.await(3, TimeUnit.SECONDS)) {
                System.out.println("LIVE_SETUP=TIMED_OUT");
                return;
            }

            monitorWaiter.start();
            ownableWaiter.start();

            // Reduces race for the demo; does not make the snapshot atomic.
            for (int i = 0; i < 100; i++) {
                boolean monitorBlocked =
                        monitorWaiter.getState() == Thread.State.BLOCKED;
                boolean ownableWaiting =
                        ownableWaiter.getState() == Thread.State.WAITING
                        || ownableWaiter.getState()
                                == Thread.State.TIMED_WAITING;
                if (monitorBlocked && ownableWaiting) {
                    break;
                }
                Thread.sleep(10);
            }

            long[] ids = {
                monitorOwner.getId(), monitorWaiter.getId(),
                ownableOwner.getId(), ownableWaiter.getId()
            };
            ThreadInfo[] infos = mx.getThreadInfo(ids, true, true);

            String[] names = {
                "MONITOR_OWNER", "MONITOR_WAITER",
                "OWNABLE_OWNER", "OWNABLE_WAITER"
            };
            for (int i = 0; i < names.length; i++) {
                report(names[i], infos[i]);
            }
        } finally {
            release.countDown();
            monitorOwner.join(2000);
            ownableOwner.join(2000);
            monitorWaiter.join(2000);
            ownableWaiter.join(2000);
        }
    }

    public static void main(String[] args) throws Exception {
        printModel();
        if (args.length == 1 && "--live".equals(args[0])) {
            runLive();
        }
    }
}
```

Compile/run:

```bash
javac ThreadLockReadingDemo.java
java ThreadLockReadingDemo
```

**Exact stdout in default mode**:

```text
MONITOR_ENTRY=BLOCKED
OBJECT_WAIT=RELEASES_WAITED_MONITOR
REENTRANT_LOCK_WAIT=USUALLY_PARKING
OWNABLE_SECTION=LOCKED_OWNABLE_SYNCHRONIZERS
THREAD_DUMP=ONE_SNAPSHOT_NOT_DEADLOCK_PROOF
```

This is a **conceptual model printed from code**, not the thread observation result of a specific run.

To observe live execution:

```bash
java ThreadLockReadingDemo --live
```

The program prints the same five model lines first, followed by status lines prefixed with `MONITOR_OWNER.`, `MONITOR_WAITER.`, `OWNABLE_OWNER.`, `OWNABLE_WAITER.`. **Live output is not fixed**, because thread states/scheduler/JVM support can vary at sampling time. On a compatible HotSpot/JDK, you typically see:

- `MONITOR_OWNER.monitors_held` greater than 0 while the owner holds the monitor.
- `MONITOR_WAITER.state=BLOCKED` with `waiting_lock_present=true`.
- `OWNABLE_OWNER.ownable_held` greater than 0 if `ReentrantLock` is reported by the JVM as an ownable synchronizer.
- `OWNABLE_WAITER.state=WAITING` or `TIMED_WAITING` with a blocker object while waiting to acquire the lock.

These are **conditional expectations**, not guaranteed stdout on every JDK/OS. If the JVM does not support observing both lock groups, `LIVE_LOCK_DETAILS=UNSUPPORTED` is printed. If threads do not reach ready state within the wait limit, `LIVE_SETUP=TIMED_OUT` may appear. The command still creates no intentional deadlock.

### 8.1 Why hold a latch while holding a lock?

`monitorOwner` holds the monitor while waiting on `release.await()`, ensuring `monitorWaiter` actually has to wait on the monitor. `ownableOwner` holds the `ReentrantLock` and also waits on the latch, causing `ownableWaiter` to wait in `lock()`. This simulates a **controlled long hold**, not a good production pattern: holding a lock while waiting on another condition can cause severe contention.

`CountDownLatch.await()` on both owners puts the owners into **WAITING**, yet they still hold their acquired monitor/ownable lock. This demonstrates that **an owner's WAITING state does not mean the owner has released all locks**.

### 8.2 Why use ThreadMXBean instead of printing Thread stacks directly?

`Thread.getAllStackTraces()` and `Thread.getStackTrace()` do not provide complete locked monitors/ownable synchronizers under the same contract. `ThreadMXBean.getThreadInfo(ids,true,true)` returns `ThreadInfo[]` with the fields needed in this lesson, mappable by ID. Results may contain `null` if a corresponding thread terminated before the snapshot.

In production, to reduce impact, read only identified IDs. With many threads, `dumpAllThreads(true,true)` incurs cost proportional to thread count/stack depth; do not call it every few milliseconds to “catch a deadlock” while the system is under pressure.

### 8.3 When you need detailed class names or lock owner IDs

The `report` helper prints **whether the owner is known**, rather than printing IDs that change on every run. In real diagnostics, you can add:

```java
LockInfo waitingFor = info.getLockInfo();
if (waitingFor != null) {
    String lockClass = waitingFor.getClassName();
    int identityHash = waitingFor.getIdentityHashCode();
    long ownerId = info.getLockOwnerId();
}
```

This is an **illustrative snippet placed inside a method with `ThreadInfo info`**, not a standalone file. `getLockOwnerId()` may be `-1` when there is no owner or the owner is unknown. When comparing lock IDs, stay within the same snapshot and follow the object identity semantics provided by the API; do not try to convert IDs into memory addresses for direct access.

## 9. Building a “who is waiting on whom” graph from a thread dump

A systematic reading approach:

1. List threads **BLOCKED on monitors** and threads **WAITING/TIMED_WAITING due to parking** in lock-related stacks.
2. For each waiting thread, record the lock identity (same snapshot) and owner ID if present.
3. Find the owner thread via `- locked` or `Locked ownable synchronizers`/`ThreadInfo.getLockOwnerId()`.
4. Draw an edge **waiter → owner**, along with lock type and state/timestamp.
5. Read the owner's stack: is it doing long work, waiting on I/O, waiting on another condition, or waiting on yet another lock?
6. If the owner is waiting on a lock held by a third thread, keep following until you reach a thread that can progress or a cycle.
7. Confirm edges with another snapshot; an edge can disappear once a lock is released.

**Hypothetical** graph example:

```text
T-worker-3 --waits monitor A--> T-worker-1
T-worker-4 --waits monitor A--> T-worker-1
T-worker-1 --waits DB response--> external service
```

This is **not a strict Java monitor deadlock cycle**. It is a **lock convoy**: multiple workers stuck behind an owner waiting on I/O. It can be mitigated by reducing work inside the critical section, moving I/O outside the monitor, adding timeouts, and optimizing the bottleneck — while analyzing context and side effects.

Another graph:

```text
Thread A --waits monitor L2--> Thread B
Thread B --waits monitor L1--> Thread A
```

If each thread **is holding** the lock the other thread wants, this is a cycle consistent with deadlock. Verify owner IDs, lock IDs, and states within the same snapshot; never build a cycle from lock identifiers taken across different JVMs or restarts.

### 9.1 Recording table to avoid mix-ups

| Field | Example | Why it is needed |
| --- | --- | --- |
| Capture timestamp | 2026-10-29T08:00:00Z | Comparing snapshots |
| JVM identity | service-A, instance-1, process start | Avoiding mixing dumps from different JVMs |
| Thread alias | worker-3 | Names can contain PII, so use aliases when sharing |
| Java thread ID | 42 | Matching owner IDs within the same JVM |
| State | BLOCKED | Classifying wait type |
| Waiting lock | Object@hash-A | Matching with owner |
| Owner alias/ID | worker-1 / 41 | Building waits-for edges |
| Held monitors | Object@hash-A | Verifying monitor ownership |
| Held synchronizers | AQS@hash-B | Verifying ownable locks |
| Relevant stack | Service.update / RemoteCall | Locating code holding/awaiting locks |
| Next observation | State after 5 seconds | Distinguishing transient vs persistent waits |

All values in the table are **synthetic samples**, not real data. Do not include raw hostnames, emails, request payloads, or tokens in shares outside approved boundaries.

## 10. Deadlock detection: why one snapshot is not enough

### 10.1 Monitor deadlock

A classic two-thread cycle:

```java
// Thread A:
synchronized (lockA) {
    synchronized (lockB) { /* ... */ }
}

// Thread B:
synchronized (lockB) {
    synchronized (lockA) { /* ... */ }
}
```

These two snippets only **illustrate lock-order inversion**; they are not a standalone program and should not be run on a production JVM. If A acquires `lockA`, B acquires `lockB`, and both attempt to acquire the remaining lock, a permanent deadlock can occur unless the process is intervened upon or an escape mechanism exists.

A thread dump may show:

- A `- locked lockA`, `- waiting to lock lockB`.
- B `- locked lockB`, `- waiting to lock lockA`.

**Do not** infer from two threads both being BLOCKED that they definitely wait on each other: both might be waiting on **a third thread**.

### 10.2 Ownable synchronizer deadlock

`ReentrantLock` can also form a cycle if thread A holds lock1 waiting for lock2 while thread B holds lock2 waiting for lock1. Waiters usually appear as `WAITING (parking)`, not `BLOCKED`. A detector rule that looks only for `Thread.State.BLOCKED` will **miss** deadlocks involving ownable synchronizers.

### 10.3 Which detections does ThreadMXBean support?

| API | Deadlock type targeted | Notes |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Cycles of platform threads waiting to acquire **object monitors** | Does not cover ownable synchronizers |
| `findDeadlockedThreads()` | Cycles of platform threads waiting on **object monitors or ownable synchronizers** | May not be supported by the JVM and carries cost |
| `isSynchronizerUsageSupported()` | Does the JVM support tracking ownable synchronizers? | Must check before requesting the feature |
| `isObjectMonitorUsageSupported()` | Does the JVM support tracking monitors? | Must check before collecting locked monitors |

`findDeadlockedThreads()` returns `null` when no deadlock within its supported scope is found. **`null` does not prove the system is free of all liveness failures**: for example, thread pool starvation, infinite waits without cycles, hung I/O, queues losing workers, deadlocks involving external resources, or virtual threads (on APIs/versions not covering them) may go undetected.

### 10.4 Do not use the deadlock detector as a substitute for root-cause analysis

Even when a tool reports “Found one Java-level deadlock”, inspect the code:

- Which locks are acquired in opposite orders?
- Can one lock be eliminated, the critical section narrowed, or lock ordering unified?
- Is I/O or awaiting performed inside a lock, or are intrinsic monitors mixed with ownable locks?
- Does an operation have side effects if a timeout/interrupt occurs?
- Should retry/timeout/cancellation be designed rather than merely increasing pool size?

**Do not** try to fix a lock-holding cycle by adding CPU, heap, or worker threads. Those actions may fail to break the deadlock and only increase the number of waiting threads.

## 11. Reading multiple thread dumps without fooling yourself

### 11.1 Why is a series of snapshots needed?

One dump describes **one moment in time**, whereas we want to know “stalled for 30 seconds” or “this condition recurs under load”. Capturing several intentionally spaced snapshots can reveal:

- Whether the same lock identity/owner/call stack persists across multiple snapshots of the same JVM.
- Whether the number of waiters on a monitor grows or shrinks.
- Whether the owner is stuck in long I/O or changing stacks.
- Whether a thread makes progress, changes state, or disappears because the request completed.
- Whether a persistent cycle exists versus brief contention.

For example, 3 dumps spaced a few seconds apart during an incident can be more useful than hundreds of rapid-fire samples. **There is no universal default cadence for all JVMs**: account for thread count, pause/overhead, incident requirements, and data collection policies.

### 11.2 Information to preserve when comparing

- JVM PID along with **start time/instance**, not just PID alone (PIDs can be reused).
- UTC timestamps and actual capture intervals.
- Java/JVM vendor/version, collector/container scope if relevant.
- Tool used and flags such as `Thread.print -l`.
- Thread count, states, and lock/object identities within **the same snapshot**.
- Application workload: traffic/latency/CPU, dependency/DB state.
- Redacted content that still preserves consistent alias mappings for the same incident.

Never merge identical-looking monitor IDs across two JVM restarts and treat them as the same object.

### 11.3 Reading truncated or incomplete samples

Dumps with thousands of threads can be huge; terminal output, log collectors, or file transfers can truncate them. If you see a waiter without an owner, the owner may be in the truncated section or the VM/tool may not report ownership. Do not invent an owner as a “mysterious system thread”.

Check thread section counts, the end of the artifact, collector errors, command exit codes, and file size. When sharing, use authorized storage and security-reviewed excerpts; raw dumps can contain sensitive thread names, class names, file paths, request/session IDs, or URLs.

## 12. Distinguishing monitor waits from Condition.await and LockSupport.park

### 12.1 Object.wait() releases the waited-on monitor

Example:

```java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
}
```

During the wait phase, the thread **no longer holds `monitor`'s monitor**. When woken by notify, interrupt, or spurious wakeup, it must reacquire the monitor. Therefore, always use `while` to recheck the condition rather than `if` under the assumption that “notify guarantees the condition is true”.

### 12.2 Condition.await() releases the associated ReentrantLock

With a `Condition` created from `ReentrantLock.newCondition()`:

```java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
} finally {
    lock.unlock();
}
```

`condition.await()` releases the associated lock while waiting (and reacquires it before returning per contract). In a snapshot showing WAITING on a Condition, **do not assume the thread still owns the associated ReentrantLock**. Even so, it may still hold other locks outside that associated lock. Condition operations have differing interrupt/timed-wait semantics; check the Javadoc before inferring lifecycle behavior.

### 12.3 LockSupport.park() is not Object.wait()

`LockSupport.park()` does not require the thread to own the blocker's monitor and **does not automatically release any locks** the thread is holding. When a thread parks while holding a monitor or ReentrantLock, other threads can end up waiting on it. If a dump shows `parking to wait for`, that could be a `ConditionObject`, AQS sync, latch, or scheduler; inspect the stack and blocker type.

### 12.4 Ownerless situations

For example, a thread pool worker parks on a work queue because there are no tasks. In a waits-for graph, this is not an edge to a specific lock owner; it is waiting on a producer/future condition. Deadlock detectors based on object monitor/ownable cycles do not catch every case of “nobody will ever submit a task”.

Hence when handling `ThreadInfo.getLockOwnerId() == -1`, the proper conclusion is “no owner reported in the snapshot”, **not** “this thread is definitely safe”.

## 13. Analyzing real-world scenarios

### 13.1 Web request pool stuck behind one synchronized method

**Hypothetical observation:** 50 worker threads `BLOCKED`, all `waiting to lock` one monitor. The owner is a request worker `WAITING` on a network call inside `synchronized`.

**Explanation:** this may be a **lock convoy** caused by a critical section wrapping I/O; latency rises because the owner does not release the lock and many requests queue up. Measure the I/O duration, verify the owner keeps holding the monitor across snapshots, and check timeouts and business consistency.

**Remediation direction:** move I/O outside the critical section when semantics permit, shrink synchronization scope, and use appropriate concurrency primitives and timeouts. Do not hastily delete `synchronized` if a data race remains.

### 13.2 A ReentrantLock held by a thread waiting on a latch

**Hypothetical observation:** multiple waiters in `WAITING (parking)` in AQS; one owner has the matching `Locked ownable synchronizers` entry yet is `WAITING` in `CountDownLatch.await()`.

**Explanation:** not every WAITING state is harmless. The owner holds a mutex while waiting on another condition, leaving waiters stuck. Find who is supposed to call `countDown()` and whether it inversely depends on that same lock.

If the producer must acquire the very lock the owner holds in order to emit the signal, a wait cycle can form **that is not represented simply as a two-ownable-lock cycle**. Read the application flow and task scheduling rather than expecting `findDeadlockedThreads()` to catch every kind of liveness failure.

### 13.3 Graph A → B → C with no cycle

**Hypothetical observation:** A waits on B's monitor, B waits on C's ReentrantLock, C is burning CPU continuously or waiting on the DB.

**Explanation:** the issue may be a **bottleneck at C**. It is not yet a deadlock if C can make progress and release the lock. Measure CPU, check stacks after an interval, DB latency, and lock hold time; it may be contention/a choke point.

### 13.4 Two threads both BLOCKED without waiting on each other

**Hypothetical observation:** T1 and T2 both show `waiting to lock <M>`, while T3 holds M. There is no edge T1 → T2 or T2 → T1.

**Explanation:** multiple contenders on one lock do not form a two-way deadlock; inspect T3. Queue/concurrent request metrics can help gauge severity.

### 13.5 Ownable synchronizers section prints - None

**Observation:** a thread is `BLOCKED` waiting on `synchronized`, yet `Locked ownable synchronizers` says `- None`.

**Explanation:** the JVM reports it holds no ownable synchronizers. This **does not contradict** its waiting on a monitor or another thread holding the monitor. Read the monitor markers and stacks; the two sections do not substitute for each other.

### 13.6 JVM reports no owner and getLockOwnerId() == -1

**Observation:** a thread is `WAITING` in `LockSupport.park`, `getLockInfo()` returns an object, yet owner id is `-1`.

**Explanation:** the blocker may have no concept of an owner, the tool did not capture the info, or the state transitioned. Read the primitive in the stack and the condition/permit lifecycle; do not fabricate a fake owner.

### 13.7 Virtual threads make the list look incomplete

**Observation:** a Java 21 service uses virtual threads, yet `ThreadMXBean.dumpAllThreads(true,true)` shows fewer platform threads than request concurrency.

**Explanation:** this is an API/tool scope limitation, not proof that all requests have finished. Use dumps/diagnostics supporting virtual threads for the exact JDK, instrumentation, and application traces. Do not use `ThreadMXBean` as an absolute count of virtual tasks.

## 14. Common analysis mistakes

| Mistake | Consequence | Correction |
| --- | --- | --- |
| “BLOCKED means deadlock.” | Confuses brief contention with a permanent cycle | Find owner/cycle, compare multiple snapshots |
| “WAITING means the thread holds no locks.” | Misses an owner awaiting a latch/I/O inside a critical section | Check `- locked` and the ownable section |
| “- locked means the thread is waiting on a monitor.” | Inverts the relationship | `- locked` means **currently owning**; `waiting to lock` means wanting to acquire |
| “waiting on = waiting to lock.” | Confuses `Object.wait()` with monitor entry | Read stack/state and monitor-release semantics |
| “parking = blocked on synchronized.” | Misses AQS/Condition/pool waits | Inspect `LockSupport` stack and ownable locks |
| “ThreadInfo.getLockInfo() != null means owner known.” | Assigns fake owners to conditions/latches | Check `getLockOwnerId()` and primitive |
| “Ownable - None means no locks held at all.” | Ignores object monitors and other primitives | Read both held monitors and synchronizers |
| “jcmd -l prints full locks.” | Confuses the list-JVMs flag with the Thread.print flag | Use `jcmd PID Thread.print -l` |
| “Same lock ID across two JVMs means the same object.” | Builds invalid graphs from reused identities | Compare within the same JVM/snapshot |
| “One snapshot shows the thread was blocked for 30 seconds.” | No direct duration in a single dump | Take multiple snapshots or configured contended-time |
| “Blocked count = blocked time.” | Counter and elapsed time have different units | Read `getBlockedCount/Time` properly |
| “Empty MBean means Java has no locks.” | Capture/support may be disabled or platform-thread only | Check flags/support/APIs |
| “findDeadlockedThreads null = no liveness bug.” | Misses queue/I/O/starvation/virtual threads | Combine traces, metrics, and source |
| “Many WAITING threads -> increase thread pool.” | Can increase contention and memory usage | Find the wait cause and bottleneck |
| “Dump is only stacks, safe to publish.” | Thread names/paths/request IDs may be sensitive | Share filtered excerpts per policy |
| “jcmd Thread.print is always ultra-lightweight.” | Cost scales with thread count/stack depth | Collect with clear purpose, window, and authorization |

## 15. Incident handling workflow without losing evidence

When facing throughput drops or hung requests:

1. **Scope the incident:** service, JVM instance, PID in the right host/container namespace, UTC time window, and symptoms such as request p99/queues.
2. **Choose the command:** check help for the appropriate JDK, collect a thread dump with `-l` if ownable locks are needed. Do not use a stale PID/wrong replica, and do not run infinite capture loops.
3. **Protect artifacts:** store dumps in access-restricted locations; review thread names, stacks, URLs, and user/session IDs before sharing.
4. **Classify threads:** BLOCKED monitor entry, WAITING on Object.wait, WAITING/TIMED_WAITING parking, RUNNABLE/native I/O.
5. **Identify lock identities:** record each `waiting to lock`/`parking`/`locked` accurately, distinguishing monitors and ownable syncs.
6. **Match owners:** correlate owner IDs/held-lock lists within the same snapshot; mark UNKNOWN when unknown.
7. **Draw waits-for graphs:** focus on locks with many contenders or cycles; distinguish cycles from chains ending at I/O/CPU/work queues.
8. **Re-capture in a controlled manner:** compare stacks/states, waiter counts, lock identities, and application metrics to verify persistence/progress.
9. **Find the source root cause:** long critical sections, inverted lock order, missing signals, blocking I/O, executor starvation, or configuration.
10. **Remediate under control:** modify code/timeouts/lock ordering and test; if a restart is needed, follow the runbook and capture sufficient evidence beforehand.
11. **Post-check:** compare throughput/latency/blocked time/busy threads, lock waiter counts, and reproducibility; do not declare fixed just because one later dump shows fewer BLOCKED threads.

Do not attempt to arbitrarily interrupt threads with `Thread.stop()` (deprecated/unsafe), clear monitors via reflection, or kill a production JVM to “break a lock” without authorization and impact analysis.

## 16. Checklist for reading a thread dump

- [ ] Identified the exact JVM instance/PID, JDK/version, and capture timestamp.
- [ ] Dump includes monitor and ownable synchronizer details as needed (`-l` or MXBean flags).
- [ ] Distinguished `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `RUNNABLE` by stack, not label alone.
- [ ] Read `- locked` as **held monitor**, not confused with waiting.
- [ ] Read `- waiting to lock` as **blocked on monitor entry**.
- [ ] Read `- waiting on` as **Object.wait/notification**, releasing the waited monitor.
- [ ] Read `- parking to wait for` alongside primitive type (AQS, Condition, latch, pool).
- [ ] Treated `Locked ownable synchronizers` as covering ownable locks only, not replacing the full monitor list.
- [ ] Matched lock IDs/`LockInfo` within **the same snapshot** to locate owners.
- [ ] Checked `getLockOwnerId()==-1` and missing fields without inventing owners.
- [ ] Inspected the **owner's** stack: long work, blocking I/O, condition wait, or acquiring more locks?
- [ ] Distinguished lock convoys/long holds from true deadlock cycles.
- [ ] If virtual threads are used, accounted for `ThreadMXBean` and tool limits.
- [ ] Considered overhead of capturing multiple thread dumps and retention policy.
- [ ] Correlated latency/CPU/queue/GC/DB traces in the same time window.
- [ ] Stored and shared raw dumps and sensitive identifiers under proper access controls.
- [ ] Tied every conclusion to **evidence**, marking unclear points as “unverified”.

## 17. Self-check exercises

**Q1.** Thread A prints `- locked <L>`. Thread B prints `- waiting to lock <L>` with `BLOCKED`. What can be concluded?

**Answer:** In that snapshot, there is evidence A holds monitor `L` and B is waiting to enter monitor `L`. It is not enough to conclude deadlock: you must know whether A is waiting on a lock held by B or can complete its critical section.

**Q2.** Thread C is in `WAITING` yet has `Locked ownable synchronizers` containing an AQS sync. Does C hold a lock?

**Answer:** There is evidence C holds the corresponding ownable synchronizer in the dump, even though C is WAITING. C can hold a `ReentrantLock` while waiting on a latch or parked on another object.

**Q3.** Why is `Thread.State.BLOCKED` not a mandatory condition of ReentrantLock contention?

**Answer:** `BLOCKED` is for monitor entry. ReentrantLock typically uses AQS/LockSupport parking; waiters can be `WAITING` or `TIMED_WAITING`.

**Q4.** `getLockInfo()` returns an object, yet `getLockOwnerId() == -1`. Is this a JVM bug?

**Answer:** No. The object may be a Condition/latch blocker or the owner may be unknown; read the stack/primitive. No reported owner is not necessarily an error.

**Q5.** When `Object.wait()` executes inside `synchronized(monitor)`, does the thread hold that monitor while WAITING?

**Answer:** No; `wait()` releases the monitor it is waiting on and must reacquire it before returning. It may still hold other monitors.

**Q6.** A dump has 100 threads in `WAITING (parking)`, with no ownership cycle. Is it guaranteed there is no progress bug?

**Answer:** No. There could be thread pool starvation, lost signals, waiting on external dependencies, a lock convoy, or an asynchronous mechanism missing tasks. A liveness bug can exist without a monitor/ownable cycle.

**Q7.** How do `findMonitorDeadlockedThreads()` and `findDeadlockedThreads()` differ?

**Answer:** The first finds cycles on object monitors; the second also includes ownable synchronizers where supported. Neither detects every kind of liveness failure, and neither covers all virtual threads across APIs/versions.

**Q8.** Why should `<0x...>` from dump A not be compared with dump B after a JVM restart?

**Answer:** Markers are internal identities within each artifact/VM and can be reused. Record JVM instance/start time and compare only within guaranteed scope.

**Q9.** If a thread shows `- locked <M>` followed by `Thread.sleep` on its stack, what should be investigated?

**Answer:** The thread holds the monitor while sleeping; other contenders may be blocked. Inspect critical-section duration, why sleep occurs inside the lock, the owner's stack, and waiter count before changing code.

**Q10.** Does `Locked ownable synchronizers: - None` prove a thread holds no `synchronized` monitors?

**Answer:** No. That is a separate list. You must check `- locked`/`getLockedMonitors()` for monitors.

## References

- [Java SE 21 — ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html): thread states, `getLockInfo()`, owner, locked monitors, locked synchronizers, and snapshot limits.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): `dumpAllThreads`, `getThreadInfo`, monitor/ownable usage support, and deadlock detection.
- [Java SE 21 — MonitorInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MonitorInfo.html): class/identity, lock acquisition stack depth/frame.
- [Java SE 21 — LockInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/LockInfo.html): class name and identity hash code of the lock object.
- [Java SE 21 — AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html): exclusive owner semantics and ownership info limits.
- [Java SE 21 — ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock ownership, parking, unlocking, and fairness.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print`, `-l` option for `java.util.concurrent` locks.
- [Oracle JDK 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): `jstack -l`, interpretation, and cost of thread dumps.

**Key takeaway:** `- locked` refers to **an owned lock**; `- waiting to lock` refers to **a monitor being awaited for entry**; `- waiting on` refers to **`Object.wait()`**; `- parking to wait for` must be read alongside the stack since it may be an AQS lock, a Condition, or an ownerless wait. `Locked ownable synchronizers` supplements `java.util.concurrent` locks rather than replacing monitors. To diagnose effectively, **connect waiter → lock → owner**, read the owner's stack, verify duration/persistence, and only call it a deadlock when a valid cycle exists.