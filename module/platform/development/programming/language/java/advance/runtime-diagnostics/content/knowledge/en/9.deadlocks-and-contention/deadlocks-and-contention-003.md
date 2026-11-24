# 9.3 findMonitorDeadlockedThreads, findDeadlockedThreads, and Platform Thread Scope

## Learning Objectives

A Java application may stop responding even though the process is still running, CPU is not high, and request threads never leave a waiting state. One possibility to check is **deadlock**: multiple threads wait for locks in a cycle so no thread in the cycle can advance to release the lock another thread needs. The Java Management API provides two methods on `ThreadMXBean` to detect certain deadlock cycles right inside the JVM:

- `findMonitorDeadlockedThreads()`: finds cycles among **platform threads waiting for Java object monitors** (e.g., `synchronized`).
- `findDeadlockedThreads()`: finds cycles among **platform threads waiting for object monitors or ownable synchronizers** (e.g., `ReentrantLock`).

The two methods have similar names but **examine different lock sets**, have support conditions, and share a very important limitation: **Java SE 21 `ThreadMXBean` does not manage/monitor virtual threads**, so **cycles involving virtual threads are not found by either method**.

After this lesson, you will be able to:

1. Distinguish monitor deadlocks, ownable-synchronizer deadlocks, contention, starvation, and waits outside the inspection scope.
2. Understand the contract for the `long[]` return type, `null` value, thread IDs, `UnsupportedOperationException`, and the cost of detection calls.
3. From discovered IDs, collect `ThreadInfo`, lock owners, stacks, monitors, and synchronizers to build an evidence-backed **wait-for graph**.
4. Write and run a Java 17+ lab that intentionally creates both deadlock types, predict each method’s result, and keep the lab from hanging indefinitely.
5. Understand specifically why platform-thread metrics do not cover virtual threads in JDK 21, and how to extend investigations using thread dumps/JFR.
6. Design a safe production diagnostic approach that clearly distinguishes **“no deadlock detected within API scope”** from **“the system has no hang issue.”**

> Primary scope: Java 17+ with focus on **Java SE 21** semantics, specifically `ThreadMXBean` in the `java.management` module. Examples that intentionally create deadlocks are **for lab JVMs only**; never embed deadlock-inducing patterns in a production service.

## 1. Groundwork: A Deadlock Is a Lock-Waiting Cycle

### 1.1 A Two-Thread Cycle

Suppose:

- Platform thread **A** holds lock **L1**, then waits for lock **L2**.
- Platform thread **B** holds **L2**, then waits for **L1**.
- Neither thread can reach the line that releases its lock because it is waiting for the other lock.

Represented as a **wait-for graph**:

```text
Thread A --waits for lock L2 held by--> Thread B
Thread B --waits for lock L1 held by--> Thread A

Cycle: A -> B -> A
```

Without cancellation/timeouts or external intervention, both threads can remain stuck forever. Java-level deadlock detection looks for **ownership/waiting cycles** that the JVM can model per specific lock type, rather than trying to guess “this thread looks unhealthy.”

A system can hang **without any Java lock cycle**:

- A waits on a network read and downstream does not respond.
- Every worker waits on a queue/connection pool without owning locks that form a cycle.
- Livelock: threads keep running and changing state repeatedly without completing work.
- Starvation: a thread fails to receive CPU/work/resources due to scheduling or unfair contention.
- Deadlocks across DB transactions, multiple services, or external distributed locks.
- Virtual-thread cycles, certain native locks, or primitives outside the contract of both APIs.

Therefore **`null` is not evidence ruling out all forms of hang**.

### 1.2 Monitors vs. Ownable Synchronizers

An **intrinsic object monitor** is the locking mechanism bound to an object, used by `synchronized`, `synchronized(this)`, or static synchronized methods. Example:

```java
// Illustration snippet placed inside a method; not a standalone program.
synchronized (accountMonitor) {
    synchronized (ledgerMonitor) {
        updateLedger();
    }
}
```

The variables/methods above belong to the application. A thread trying to enter `synchronized` when the monitor is held by another thread normally has Java state `BLOCKED`.

An **ownable synchronizer** is a synchronizer that can be exclusively owned by one thread and relies on `AbstractOwnableSynchronizer` or a subclass to manage ownership. Per Java SE 21 documentation, **`ReentrantLock`** and the **write lock of `ReentrantReadWriteLock`** are two examples; the **read lock of `ReentrantReadWriteLock` is not an ownable synchronizer** in the same sense.

```java
// Illustration snippet; assumes lock is a ReentrantLock.
lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
```

When waiting in `ReentrantLock.lock()`, a thread may show `WAITING (parking)` instead of `BLOCKED`. Do not use a rule like “only `BLOCKED` is deadlock”; an **ownable-synchronizer cycle** can appear under wait states other than monitor entry.

### 1.3 Why Two Detectors Exist

A detector that only knows about object monitors will not necessarily recognize `ReentrantLock` ownership cycles. Java provides:

| API | Cycle Types Detected | Not Covered |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Platform threads waiting on **object monitors** in an ownership cycle | Ownable-synchronizer-only cycles, virtual threads, external locks |
| `findDeadlockedThreads()` | Platform threads waiting on **object monitors or ownable synchronizers** in a cycle | Virtual threads, waits outside those two lock types, and many resource deadlocks |
| `dumpAllThreads(...)` | **Snapshot info** of platform threads including stack/locks per VM capabilities | Does not automatically classify stuck threads as deadlocked; excludes virtual threads in Java 21 |

The task is **scoped detection**, not a final verdict on application health.

## 2. Where Does ThreadMXBean Live?

In Java:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

This is **illustrative code** that must be placed inside a method/class to compile. `ManagementFactory.getThreadMXBean()` returns the management bean of the **current JVM**, not another JVM on a remote machine. The same interface can be accessed via the **platform MBeanServer** or a secured JMX connector, using the standard ObjectName:

```text
java.lang:type=Threading
```

Key methods related to this lesson:

```java
long[] monitorIds = bean.findMonitorDeadlockedThreads();
long[] allIds = bean.findDeadlockedThreads();
boolean monitorSupported = bean.isObjectMonitorUsageSupported();
boolean synchronizerSupported = bean.isSynchronizerUsageSupported();
```

This snippet is **not a standalone program**; additionally, calling `findDeadlockedThreads()` must be guarded if the VM does not support ownable synchronizer usage.

### 2.1 Getting the Scope Right: Platform Threads

Java SE 21 explicitly states that `ThreadMXBean` supports monitoring and managing **platform threads**, which typically map onto kernel/OS threads. **Virtual threads** are another kind of `Thread`, managed flexibly by a scheduler, capable of mounting/unmounting from carrier platform threads.

`ThreadMXBean` **does not support managing/monitoring virtual threads** in Java 21; both detectors **do not find cycles involving virtual threads**. That is a documented limitation in the API contract, not a dashboard bug.

Consequences:

- `getThreadCount()` is the number of **live platform threads** per the bean, not total Java logical tasks/virtual threads.
- `getAllThreadIds()` returns IDs of **live platform threads**; it excludes virtual thread IDs.
- `dumpAllThreads(...)` returns info for **live platform threads**; it does not provide a complete list of virtual threads.
- `getThreadInfo(id)` with a **virtual thread ID** returns `null` per the Java 21 contract.
- `findMonitorDeadlockedThreads()` and `findDeadlockedThreads()` only examine **cycles consisting of platform threads**; they can miss cycles between virtual threads or mixed cycles containing a virtual thread.

An application with 20,000 virtual threads where `getThreadCount()` reports only a few dozen **does not mean** 19,970 threads exited; the two counts measure different populations.

## 3. findMonitorDeadlockedThreads(): Object Monitors Only

### 3.1 Exact Contract

Signature:

```java
long[] findMonitorDeadlockedThreads()
```

Semantics in Java SE 21:

- Finds **cycles of platform threads deadlocked waiting to acquire an object monitor**.
- Includes waiting to enter `synchronized` as well as certain cases of **waiting to reacquire a monitor after `Object.wait()`** per contract.
- A monitor deadlock occurs when each thread in the cycle waits for a monitor owned by the next thread in the cycle.
- Returns an **array of IDs of the deadlocked platform threads found**.
- If no deadlock within this scope is found, returns **`null`**, not necessarily `new long[0]`.
- Does not detect **cycles containing virtual threads**; also does not inspect ownable synchronizers such as `ReentrantLock`.
- Designed for **troubleshooting**, not synchronization control; may be expensive.

Example of reading the return value:

```java
long[] ids = bean.findMonitorDeadlockedThreads();
if (ids == null) {
    System.out.println("No monitor deadlock detected in platform threads");
} else {
    System.out.println("Monitor deadlocked platform threads: " + ids.length);
}
```

The snippet above only illustrates usage inside a method that has `bean`. The message should be understood as **“the detector found nothing within scope at invocation time,”** not “the application is not hung.”

### 3.2 Two-Monitor Deadlock

Suppose:

```text
platform-A:
  holds intrinsic monitor A
  waiting for intrinsic monitor B

platform-B:
  holds intrinsic monitor B
  waiting for intrinsic monitor A

monitor wait-for graph: platform-A -> platform-B -> platform-A
```

In a normally supported HotSpot JVM, once both have entered the wait state, both `findMonitorDeadlockedThreads()` and `findDeadlockedThreads()` **can** detect this cycle. The result is not guaranteed to order IDs by thread name, and there is no contract on which ID appears first.

### 3.3 Cases Typically Not Detected by This API

- A and B use `ReentrantLock` instead of `synchronized`: the monitor-only detector will not see pure ownable-synchronizer lock cycles.
- A is hung on an HTTP request with no timeout: no clear object monitor cycle exists.
- A thread waits on `Condition.await()`, an executor/queue, or long I/O: wait state alone does not create a monitor ownership cycle.
- A deadlock involving at least one virtual thread in Java 21: outside the API scope.
- Threads die/restart right during measurement: snapshots can be unstable; do not infer from a single `null` return that no issue occurred in the prior window.

## 4. findDeadlockedThreads(): Both Monitors and Ownable Synchronizers

### 4.1 Exact Contract

Signature:

```java
long[] findDeadlockedThreads()
```

The key difference is that this detector examines **object monitors or ownable synchronizers**. In a cycle:

- A might hold ownable synchronizer L1 and wait for L2.
- B holds L2 and waits for L1.
- Or, depending on structure, a cycle may contain both monitors and ownable synchronizers.

When detected, it returns a `long[]` of **platform thread IDs** in the cycle; when none is detected, it returns **`null`**. If the JVM **does not support monitoring ownable synchronizer usage**, the method may throw **`UnsupportedOperationException`**.

Therefore use:

```java
if (bean.isSynchronizerUsageSupported()) {
    long[] ids = bean.findDeadlockedThreads();
    // null => no cycle in API scope detected at measurement time
} else {
    // Do not call findDeadlockedThreads; record "unsupported".
}
```

This snippet is illustrative, not a standalone program. In managed environments with security restrictions, calls can also throw `SecurityException` if the caller lacks `ManagementPermission("monitor")` per the JDK 21 contract. Never turn an exception into “no deadlock detected.”

### 4.2 Comparing the Two APIs with ReentrantLock

Example scenario:

```text
platform-A:
  holds ReentrantLock L1
  calls L2.lock() and is waiting

platform-B:
  holds ReentrantLock L2
  calls L1.lock() and is waiting

ownable synchronizer wait-for graph: A -> B -> A
```

Once deadlocked on a supporting JVM:

- `findMonitorDeadlockedThreads()` typically returns **`null`** — there is no monitor cycle.
- `findDeadlockedThreads()` can return the IDs of **A and B** — because it checks ownable synchronizers.

**Do not assume every primitive in `java.util.concurrent` is understood by `findDeadlockedThreads()`.** For example, a `Semaphore` does not generally have a single exclusive owner per `AbstractOwnableSynchronizer`; the read lock of `ReentrantReadWriteLock` does not belong to the ownable synchronizer category like the write lock does. Read each primitive’s contract when evaluating detector coverage.

### 4.3 isObjectMonitorUsageSupported and isSynchronizerUsageSupported

These two capability probes query VM **usage monitoring** support:

| Method | Meaning |
| --- | --- |
| `isObjectMonitorUsageSupported()` | Can the VM provide object monitor usage info when dumping thread details? |
| `isSynchronizerUsageSupported()` | Can the VM provide ownable synchronizer usage info? |
| `findDeadlockedThreads()` | **Depends on ownable support**, may throw `UnsupportedOperationException` |
| `getThreadInfo(ids, true, true)` | Only enable locked monitors/synchronizers flags if supported; otherwise may throw `UnsupportedOperationException` |

Do not equate `isObjectMonitorUsageSupported() == false` with `findMonitorDeadlockedThreads()` definitely being forbidden: the contract for detecting monitor deadlocks and the contract for **enumerating all held monitors** are separate specifications. Check both actual errors and VM documentation.

## 5. What Is Returned Is Thread IDs, Not ThreadInfo

Both detectors return `long[]` (or `null`), **not `ThreadInfo[]`**, and they do not directly tell you source line numbers. For each ID, you must query further information with `ThreadMXBean.getThreadInfo(...)`.

Example of proper usage:

```java
// Placed inside a method, with bean obtained from ManagementFactory.
long[] ids = bean.isSynchronizerUsageSupported()
        ? bean.findDeadlockedThreads()
        : bean.findMonitorDeadlockedThreads();

if (ids != null) {
    boolean monitors = bean.isObjectMonitorUsageSupported();
    boolean ownables = bean.isSynchronizerUsageSupported();

    java.lang.management.ThreadInfo[] infos =
            bean.getThreadInfo(ids, monitors, ownables, 32);

    for (java.lang.management.ThreadInfo info : infos) {
        if (info == null) {
            continue; // Thread may have exited between the two measurements.
        }
        System.out.println(info.getThreadName());
        System.out.println(info.getThreadState());
        System.out.println(info.getLockName());
        System.out.println(info.getLockOwnerName());
    }
}
```

This is an **illustrative snippet**, not standalone. `getThreadInfo(long[], boolean, boolean, int)` retrieves info with a **maximum stack depth of 32** in the example; the flags requesting locked monitors/synchronizers must only be enabled if the VM supports them. A thread may terminate between when the detector returns IDs and when `ThreadInfo` is fetched; the API can return `null` elements. Thus workflows must account for **race conditions** rather than assuming multi-call snapshots are atomic.

### 5.1 What Does ThreadInfo Contain?

A `ThreadInfo` normally provides:

- `getThreadId()` — JVM thread ID, **not the native OS TID/PID**.
- `getThreadName()` — thread name; not required to be unique.
- `getThreadState()` — `BLOCKED`, `WAITING`, `TIMED_WAITING`, etc. per Java’s model.
- `getLockInfo()`/`getLockName()` — lock the thread is waiting on if available.
- `getLockOwnerId()`/`getLockOwnerName()` — thread known to own the lock this thread is waiting on; **`-1`** or `null` indicates unknown/no owner.
- `getStackTrace()` — stack frames helping locate the class/method and wait site.
- `getLockedMonitors()` — monitors held by the thread when requested/supported.
- `getLockedSynchronizers()` — ownable synchronizers held by the thread when requested/supported.

A Java monitor may print as `java.lang.Object@7f39...`. That is a class + identity-hash-based representation of the lock, **not a business name** and not a reliable raw heap pointer across every VM. `ThreadInfo.getLockOwnerId()` is more useful when constructing **thread → owner** wait edges.

### 5.2 Drawing the Wait-For Graph with Real Data

Suppose after fetching details you see:

```text
threadId=42, name=checkout-A, lockOwnerId=43, lock=java.lang.Object@aaa
threadId=43, name=checkout-B, lockOwnerId=42, lock=java.lang.Object@bbb
```

This is **simulated data**, not lab output. You have two edges:

```text
checkout-A (42) --waiting for lock owned by--> checkout-B (43)
checkout-B (43) --waiting for lock owned by--> checkout-A (42)
```

The two edges form the cycle A→B→A. To explain the cause in source code, inspect the **stack frames at the wait point**, the method holding the lock, and the call order. Do not rely solely on the names `checkout-A`/`checkout-B`, as thread names can collide or change during a lifecycle.

### 5.3 Do Not Mix IDs Across Different JVMs

`ThreadMXBean` thread IDs are meaningful within **one running JVM at a time**. A thread ID is a positive number, unique over that thread’s lifetime, but **may be reused after the thread dies**. Different processes can easily have identical thread IDs. Tag data with service, host/container, PID, **and process start time**, plus UTC timestamp before comparing snapshots.

In particular, `getThreadInfo(id) == null` may mean the thread died, does not exist, or is a virtual thread ID (Java 21); it **does not prove** the detector returned a bad ID or that the incident resolved itself.

## 6. Lab 1: Creating an Intrinsic Monitor Deadlock on Java 17+

The complete practice in section 8 has two modes: `monitor` and `ownable`. Before looking at the code, predict the `monitor` mode:

```text
Platform thread monitor-A:
  synchronized(A) {
      wait for monitor-B holding B
      synchronized(B) { ... }
  }

Platform thread monitor-B:
  synchronized(B) {
      wait for monitor-A holding A
      synchronized(A) { ... }
  }
```

A `CountDownLatch(2)` guarantees **both have acquired their first lock** before attempting the second lock. That avoids a race in which thread A acquires both A and B before B ever acquires B; without the latch, the lab might fail to form a deadlock.

Once both threads actually wait on each other:

| API | Expected on a Supporting HotSpot |
| --- | --- |
| `findMonitorDeadlockedThreads()` | Two IDs in the cycle, order not guaranteed |
| `findDeadlockedThreads()` | Also detects both IDs if ownable monitoring is supported |
| `getThreadInfo(...).getThreadState()` | Typically `BLOCKED` for both threads waiting on `synchronized` |
| `getLockOwnerId()` | ID of the thread currently holding the monitor the thread needs |

The API returns results **after the deadlock has formed**, so the lab avoids expecting both threads to enter the cycle at the exact nanosecond. That is why the code waits briefly and polls a bounded number of times.

### 6.1 What the Monitor Detector Does **Not** Tell You

The method does not tell you how to fix the lock order, cannot guarantee fetching stacks from an already-restarted process, and does not automatically release monitors. A detected cycle is strong evidence that platform threads are stuck under the lock model tracked by the VM. To determine where to fix it, find the prior lock acquisitions, acquisition order, nested callbacks/library layers, and all code paths sharing those lock objects.

**Never use `Thread.stop()` to “fix” a production deadlock**: it is deprecated because it is unsafe; killing a thread holding monitors can corrupt invariants or data. You must fix the locking design and follow incident-handling procedures.

## 7. Lab 2: ReentrantLock Deadlock Seen Only by the Broader Detector

For `ReentrantLock`, each thread owns a different `ReentrantLock`, and both proceed to acquire the second lock after a latch:

```text
Platform thread ownable-A:
  holds ReentrantLock L1
  tries lock(L2) --> waits for thread ownable-B

Platform thread ownable-B:
  holds ReentrantLock L2
  tries lock(L1) --> waits for thread ownable-A

Cycle: ownable-A -> ownable-B -> ownable-A
```

On a supporting HotSpot:

- `findMonitorDeadlockedThreads()` normally returns `null` because it is **not an intrinsic monitor cycle**.
- `findDeadlockedThreads()` finds both platform thread IDs stuck on **ownable synchronizers**.
- Thread states may be `WAITING (parking)`, not `BLOCKED`.
- `ThreadInfo.getLockedSynchronizers()` with the corresponding flag can show which lock each thread owns.

This is a critical lesson: **you cannot replace `findDeadlockedThreads()` with `findMonitorDeadlockedThreads()` in a system using `ReentrantLock` and trust a `null` result to mean “no deadlock.”**

### 7.1 Distinguishing Exclusive Locks and Semaphores

`ReentrantLock` has an exclusive owner per `AbstractOwnableSynchronizer`. `Semaphore` tracks permits and does not model a **single unique owner thread** under the same contract. Two tasks can wait forever for permits or form application-level circular dependencies that the detector will not recognize. Thus “using `java.util.concurrent`” is not enough to claim the broader detector covers every case.

Similarly, `Condition.await()` temporarily **releases its associated lock** while waiting and reacquires it upon completion per contract. A condition-waiting thread is not necessarily holding a lock in an identifiable wait-for cycle. Do not treat every `WAITING` in `LockSupport.park` as an ownable-synchronizer deadlock.

## 8. Complete Java 17+ Practice: Comparing Both Detectors

Create the file **`DeadlockMxBeanLab.java`**. The program has two command-line modes:

- `monitor` — intentionally creates a cycle using `synchronized`.
- `ownable` — intentionally creates a cycle using `ReentrantLock`.

**Run only in a lab terminal; never embed deadlock-creating code in a real application.** Threads are marked **daemon** so the process still exits after main prints results; `daemon` does not resolve the deadlock itself and is **not a way to handle production deadlocks**.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public final class DeadlockMxBeanLab {
    private static final Object MONITOR_A = new Object();
    private static final Object MONITOR_B = new Object();
    private static final ReentrantLock LOCK_A = new ReentrantLock();
    private static final ReentrantLock LOCK_B = new ReentrantLock();

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Lab interrupted", e);
        }
    }

    private static void monitorCycle(Object first, Object second,
                                     CountDownLatch firstLocksHeld) {
        synchronized (first) {
            firstLocksHeld.countDown();
            await(firstLocksHeld);
            synchronized (second) {
                // With two threads acquiring locks in reverse order, this block is unreachable.
            }
        }
    }

    private static void ownableCycle(ReentrantLock first, ReentrantLock second,
                                     CountDownLatch firstLocksHeld) {
        first.lock();
        try {
            firstLocksHeld.countDown();
            await(firstLocksHeld);
            second.lock();
            try {
                // With two threads acquiring locks in reverse order, this block is unreachable.
            } finally {
                second.unlock();
            }
        } finally {
            first.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("DeadlockMxBeanLab READY");
        String mode = args.length == 1 ? args[0] : "";
        if (!mode.equals("monitor") && !mode.equals("ownable")) {
            System.out.println("Usage: java DeadlockMxBeanLab monitor|ownable");
            return;
        }

        System.out.println("mode=" + mode);
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        if (mode.equals("ownable") && !bean.isSynchronizerUsageSupported()) {
            System.out.println("ownable detection unsupported on this JVM");
            return;
        }

        CountDownLatch firstLocksHeld = new CountDownLatch(2);

        Runnable a = mode.equals("monitor")
                ? () -> monitorCycle(MONITOR_A, MONITOR_B, firstLocksHeld)
                : () -> ownableCycle(LOCK_A, LOCK_B, firstLocksHeld);
        Runnable b = mode.equals("monitor")
                ? () -> monitorCycle(MONITOR_B, MONITOR_A, firstLocksHeld)
                : () -> ownableCycle(LOCK_B, LOCK_A, firstLocksHeld);

        Thread ta = new Thread(a, mode + "-A");
        Thread tb = new Thread(b, mode + "-B");
        ta.setDaemon(true);
        tb.setDaemon(true);
        ta.start();
        tb.start();

        firstLocksHeld.await(); // Both currently hold the first lock.

        long[] monitorIds = null;
        long[] allIds = null;
        for (int attempt = 0; attempt < 5; attempt++) {
            Thread.sleep(200L); // Allow both threads to enter the second lock.
            monitorIds = bean.findMonitorDeadlockedThreads();
            if (bean.isSynchronizerUsageSupported()) {
                allIds = bean.findDeadlockedThreads();
            }

            if (mode.equals("monitor") && monitorIds != null) {
                break;
            }
            if (mode.equals("ownable") && allIds != null) {
                break;
            }
        }

        System.out.println("monitorCycleDetected=" + (monitorIds != null));
        if (bean.isSynchronizerUsageSupported()) {
            System.out.println("allCycleDetected=" + (allIds != null));
        } else {
            System.out.println("allCycleDetected=unsupported");
        }

        long[] ids = allIds != null ? allIds : monitorIds;
        if (ids != null) {
            boolean monitors = bean.isObjectMonitorUsageSupported();
            boolean synchronizers = bean.isSynchronizerUsageSupported();

            ThreadInfo[] details =
                    bean.getThreadInfo(ids, monitors, synchronizers, 24);

            for (ThreadInfo info : details) {
                if (info != null) {
                    System.out.println("thread=" + info.getThreadName()
                            + " state=" + info.getThreadState()
                            + " waitsForOwner=" + info.getLockOwnerName());
                }
            }
        }

        System.out.println("DeadlockMxBeanLab DONE");
    }
}
```

Compile:

```bash
javac DeadlockMxBeanLab.java
```

Run each mode **in a separate lab JVM process**, since each run creates an unresolvable cycle inside that process:

```bash
java DeadlockMxBeanLab monitor
java DeadlockMxBeanLab ownable
```

**Exact first stdout line in both modes**:

```text
DeadlockMxBeanLab READY
```

The next line is **`mode=monitor`** or **`mode=ownable`** respectively. Subsequent detection values **depend on timing, implementation, and support**; byte-for-byte stdout is not promised on every JVM.

On HotSpot JDK 21 with ownable support active and the deadlock formed, **typical expectations**:

| Lab Run | monitorCycleDetected | allCycleDetected | Common Thread State |
| --- | --- | --- | --- |
| `java DeadlockMxBeanLab monitor` | `true` | `true` | Both threads in `BLOCKED` |
| `java DeadlockMxBeanLab ownable` | `false` | `true` | Both threads in `WAITING (parking)` |

When reading `thread=...` lines, the order of the two thread IDs **is not guaranteed by the API**. `waitsForOwner` depends on timing/VM, so do not set a fixed expected output. If the system does not support ownable usage, the program prints an unsupported message and **does not call** the broader detector in `ownable` mode.

### 8.1 Why Can Main Exit While Threads Are Deadlocked?

The two intentionally deadlocked threads have `daemon=true`, so **they do not keep the JVM running when only daemon threads remain**. Main can print `DONE` and return, and the VM exits. That merely keeps the lab from hanging indefinitely after observation, and **does not mean the deadlock was released**.

If you switch them to **non-daemon threads**, the JVM can keep running forever because deadlocked threads do not exit. In that case you must stop the lab using test termination procedures, **never treating `Thread.stop()` or `System.exit()` as a fix for production deadlocks**.

### 8.2 Why Must CountDownLatch Be Used?

Without `CountDownLatch`, the scheduler could let A acquire both the first and second lock and release them before B even starts; in that case **no deadlock occurs** and the detector returns `null` even though the source code has reversed lock orders. The latch ensures each thread already holds its first lock before both proceed to request the second lock.

This is a technique to create **controlled test conditions**, not a pattern to synchronize real software by holding locks across a wait phase.

### 8.3 Why Can Lab Results Differ from the Table?

- Non-HotSpot JVM or different capabilities.
- Lab had not formed the cycle yet at a snapshot; overloaded machine / delayed scheduling.
- Security policy blocking operations.
- An older process exited and you are reading the terminal of a new run.
- Lab code was modified, or threads were interrupted or errored while holding/acquiring locks.
- Detector overhead and timing differences across VM implementations.

To verify, attach to the PID, capture `jcmd <PID> Thread.print -l` **while the process is still running** (since the daemon lab exits quickly, you may need to keep main alive longer per a separate plan), or log additional `ThreadInfo`. Do not conclude from an out-of-window test that the API is broken.

### 8.4 How to Read Output Containing Owners

Suppose simulated output shows:

```text
monitorCycleDetected=true
allCycleDetected=true
thread=monitor-A state=BLOCKED waitsForOwner=monitor-B
thread=monitor-B state=BLOCKED waitsForOwner=monitor-A
```

The last two lines represent the A→B→A cycle; this is **not mandatory stdout** in exact line order or count on every VM. In `ownable` mode, state can be `WAITING` instead of `BLOCKED` while owner still reveals the cycle; do not rely on state alone to draw conclusions.

## 9. Java 21 Virtual Threads: A Limitation Proven by the API

Java 21 provides `Thread.startVirtualThread(...)`, yet `ThreadMXBean` only monitors **platform threads**. This section uses a **separate lab running only on JDK 21+** to check whether a live virtual thread appears in `getThreadInfo`.

Create the file **`VirtualThreadMxBeanScopeLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public final class VirtualThreadMxBeanScopeLab {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread virtual = Thread.startVirtualThread(() -> {
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        entered.await(); // Virtual thread has started and has not exited yet.
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        System.out.println("isVirtual=" + virtual.isVirtual());
        System.out.println("mxbeanInfoPresent=" +
                (bean.getThreadInfo(virtual.threadId()) != null));

        release.countDown();
        virtual.join();
    }
}
```

Compile and run on **JDK 21 or higher**, **not** JDK 17 because virtual thread APIs were not finalized in Java 17:

```bash
javac VirtualThreadMxBeanScopeLab.java
java VirtualThreadMxBeanScopeLab
```

**Exact stdout on Java SE 21 per contract:**

```text
isVirtual=true
mxbeanInfoPresent=false
```

Reason: the thread is indeed virtual (created via `startVirtualThread`); `ThreadMXBean.getThreadInfo` does not track virtual threads and thus returns `null` even while the thread is still waiting on the latch. **Do not interpret `false` as the virtual thread having terminated or having no work to process.**

### 9.1 Why Cannot Virtual Cycles Be Inferred from Platform-Thread Counters?

Virtual threads can **unmount** from carrier platform threads while waiting; logical task counts do not correspond to platform worker counts. For example:

- Two virtual threads both use `ReentrantLock` in reverse order and form a cycle.
- `findDeadlockedThreads()` may return `null` because both are virtual threads.
- `getAllThreadIds()` does not list virtual thread IDs, even while they are alive.
- A platform thread waiting on a virtual thread via `join` also does not automatically create a **platform-only monitor/ownable cycle** within detector scope.

JDK 21 documentation explicitly notes that cycles involving virtual threads **are not found by either method**. Therefore when running a virtual-thread-heavy application, “ThreadMXBean’s deadlock detector reported no deadlock” must be presented with **API scope limits**, not as confirmation that the system is completely unstuck.

### 9.2 Additional Data Sources for Virtual Threads

Depending on JDK/vendor, consider:

- `jcmd <PID> help Thread.dump_to_file` and then using the command if the **target supports it**; Java 21 includes dedicated thread dump instructions for virtual threads in text/JSON formats. The file is written by the **target JVM** on its own filesystem.
- **JFR** to observe virtual-thread-related events/samples, such as `jdk.VirtualThreadPinned` or `jdk.VirtualThreadSubmitFailed` if available in the running JDK’s JFR configuration.
- App-level timeouts/queues/request tracing, structured task scopes when supported, executor/scheduler metrics, or appropriate instrumentation.
- Suspected native locks, external DB/Redis/distributed locks: inspect the corresponding system rather than inferring from one MXBean.

A thread dump is only a snapshot at capture time; JFR must be enabled before an incident to hold prior timeline data. Do not assume every option in newer JDKs exists on the exact JDK 21 JVM running; **check `jcmd PID help` and vendor documentation**.

## 10. What Do the Two Detectors Not Find?

### 10.1 Normal Contention Is Not Deadlock

A thread holds a monitor for 10 ms, other threads become `BLOCKED`, and then all continue running—that is contention. It can raise latency, yet **there is no permanent wait cycle**. Deadlock detection returning `null` is still expected.

If contention is high, inspect `ThreadInfo`, JFR lock/park events, request p99, and lock hold durations; the issue may be wide lock scope rather than a deadlock cycle.

### 10.2 Starvation and Thread Pool Exhaustion

A thread pool has 20 workers, and all workers wait on futures submitted to **the same pool** with no free workers left to run those futures. This can be a **thread starvation deadlock** at the scheduling/queue level without necessarily forming an ownership cycle of object monitors or ownable synchronizers. Both Java lock-cycle methods may return `null`.

You must inspect queues, active worker counts, waiting/runnable tasks, dependency graphs, timeout policies, and structured concurrency/executor design. If possible, capture several thread dumps spaced appropriately and compare throughput.

### 10.3 I/O, DB, and Distributed Resource Deadlocks

- A Java thread waits on a socket read while downstream stalls.
- An SQL transaction is blocked by a database lock.
- One service holds a distributed lock in Redis while waiting for a result from another service that needs that lock.
- A library’s native code uses its own mutexes outside the object monitors/ownable synchronizers tracked by the Java Management API.

These phenomena can hang a system much like a deadlock, yet **detection by the two detectors is not guaranteed**. Inspect database lock graphs, traces/spans, network telemetry, native profilers, and logs with appropriate permissions.

### 10.4 Livelock

Livelock occurs when threads **keep working, changing state, and reacting to one another** while repeatedly failing to finish their goal. No thread may be waiting on a monitor in a clear cycle. Time-series progress, counters, traces, and profilers are needed to confirm.

### 10.5 Virtual Threads or Mixed Cycles

Having just one virtual thread in a cycle puts it **outside the scope of both methods** in Java 21. A platform thread may be waiting on a virtual thread or vice versa; the detectors have no contract to find all mixed cycle forms. Do not use `ThreadMXBean` output as a “deadlock-free certificate” for a virtual-thread-heavy system.

## 11. Distinguishing null, Unsupported, and Limited Information

Three very different states:

| State | Accurate Interpretation | Next Step |
| --- | --- | --- |
| `find...() == null` | Detector found no cycle within **its supported scope** at invocation time | Check lock types, virtual threads, capture timing; inspect metrics/dumps |
| `UnsupportedOperationException` on `findDeadlockedThreads()` | JVM does not support monitoring ownable synchronizers (or corresponding capability) | Use monitor-only detector if appropriate; record unsupported explicitly |
| `SecurityException` | Caller blocked by monitoring policy/permissions | Request valid authorization/diagnostic path; do not bypass |
| `getThreadInfo(id) == null` | Thread may have died/not exist or be a virtual ID; race between calls | Check identity/time and take a fresh snapshot |
| `ids != null` | Platform threads in a detected cycle were found | Collect ThreadInfo/stacks/owners, analyze lock acquisition order, and triage incident |

Never silently convert **unsupported** into `false` or `null` in telemetry. If a dashboard emits `deadlock_detected=0` when the detector did not actually run successfully, viewers will misread it as “checked and none found.” Separate the check’s **status** from its **result**:

```text
check_status = success | unsupported | denied | error
result       = found | not_found | unknown
scope        = platform_threads, object_monitors | object_monitors_and_ownable
captured_at  = timestamp
```

This is a proposed explanatory schema, **not an API output**. When the check cannot run, keep `result=unknown` to avoid creating false reassurance.

### 11.1 Reading ID Values Properly

A `ThreadMXBean` ID is a **long Java thread ID**, not:

- an OS process PID;
- a HotSpot native thread ID `nid=0x...` in text thread dumps;
- a VM internal `tid=0x...` pointer;
- a cluster-wide unique ID or persistent ID across JVM restarts.

When comparing `ThreadInfo` with `jcmd Thread.print`/`jstack`, match process identity, thread name, Java thread ID, and native ID per that JVM’s format. Do not guess based on two numbers having the same value.

### 11.2 The State-Reading Race Problem

A call sequence might look like:

```text
T0: findDeadlockedThreads() -> IDs
T1: getThreadInfo(IDs, ...) -> stack/lock details
T2: serialize/export data -> logs/dashboard
```

Because the JVM executes concurrently, information at T0 and T1 **is not an atomic snapshot transaction**. With a real monitor deadlock and no external intervention, the cycle typically persists; however, general-purpose code must still handle threads that died, restarted, or changed state. Never coerce a null `ThreadInfo` into a fake object.

## 12. Operational Impact: Do Not Use the Detector as a Synchronization Lock

The API docs explicitly state that both methods are intended for **troubleshooting**, not **synchronization control**, and can be expensive operations. Therefore:

- Do not call `findDeadlockedThreads()` on every HTTP request just to decide whether to acquire another lock.
- Do not use a `null` result to skip timeouts/lock ordering or feel “confident” the system is safe.
- Do not schedule checks every millisecond on a JVM with many platform threads without measuring overhead.
- Do not invoke across all replicas simultaneously during a CPU/memory pressure incident without weighing impact.
- If using remote JMX, restrict network/authentication/authorization; management endpoints may expose other operations that mutate JVM state.
- Do not expose lock/stack details that could reveal internal architecture, thread names, paths, or request identifiers as public data.

In production, a sound workflow is **symptom-triggered** (latency spike/stall), taking 1–3 timestamped snapshots combined with metrics/traces and documenting scope limits. If background monitoring is required, measure and set an appropriate cadence rather than polling the detector every 100 ms by default.

### 12.1 Should You Automatically “Break a Deadlock”?

A deadlock detector **does not fix source code or release locks**. Approaches like `Thread.stop()` are deprecated and unsafe; forcibly killing a thread holding monitors can corrupt invariants/data. Interrupting a thread that is `BLOCKED` waiting on an intrinsic monitor **is not guaranteed** to exit `synchronized`; `ReentrantLock.lockInterruptibly()` only supports interruption when **the code actually uses that API**.

Sustainable fixes usually involve:

- Defining a **consistent** lock acquisition order across all code paths.
- Reducing nested locking and lock-holding duration; avoiding I/O/blocking calls while holding locks.
- Using `try/finally` to release `ReentrantLock` properly.
- Considering `tryLock(timeout, unit)` for appropriate wait bounds and safe timeout handling.
- Designing task/executor dependencies to avoid starvation and circular joins.
- Testing under concurrency stress and checking deadlock conditions in integration tests.

### 12.2 Example of Changing Lock Order

**Unsafe — two code paths invert order**:

```text
Path A: acquire accountLock -> acquire ledgerLock
Path B: acquire ledgerLock  -> acquire accountLock
```

**Safer — same-order rule**:

```text
Path A: acquire accountLock -> acquire ledgerLock
Path B: acquire accountLock -> acquire ledgerLock
```

Unifying the order eliminates this illustrated **two-lock cycle** provided no other code paths break the rule. However, it does not prove the entire system is deadlock-free; other locks and external dependencies remain.

## 13. Inspecting from JConsole, JMX, or jcmd

### 13.1 Local Java API vs. Remote JMX

`ManagementFactory.getThreadMXBean()` reads the **JVM running that code**. A JConsole/JMX client connecting to ObjectName `java.lang:type=Threading` on a **target JVM** can invoke operations or read attributes exposed per JMX permissions. However:

- Remote JMX must configure authentication, TLS, network restrictions, and role permissions.
- Do not assume every operation is read-only or cheap; thread dumps and deadlock detection have overhead.
- If the target JVM disables remote attach/JMX, never open an unauthenticated port just for a quick look.
- ObjectName is identical across all processes, so **target endpoint/host/PID/start time** is what identifies which instance you are inspecting.

### 13.2 Comparison with jcmd and jstack

On HotSpot JDK 21, you can use:

```bash
jcmd 12345 Thread.print -l
jstack -l 12345
```

**12345 is a hypothetical PID**, never copy it onto a real host without checking. These commands produce a **thread dump**, unlike calling the detector which returns an array of IDs. The dump can include a Java-level deadlock section when supported by the VM, along with monitors/ownable synchronizers and stacks useful for finding acquisition sites.

- `jcmd Thread.print -l` is generally preferred when HotSpot supports it and the tool/permissions allow attaching.
- JDK 21 `jstack` is marked experimental/unsupported in its man page; check the tool options for the running JDK.
- Traditional text thread dumps **do not necessarily** list all unmounted virtual threads.
- If virtual threads are needed, check `jcmd PID help Thread.dump_to_file` on the target JDK 21 JVM to see whether the dedicated command and JSON/text output exist.
- `jcmd ... > file.txt` saves the file in the caller’s shell; `Thread.dump_to_file` writes the file on the **target JVM** side.

Even if `findDeadlockedThreads()` returns `null`, a few thread dump snapshots and JFR can help locate starvation, lock contention, or virtual-thread blocking outside detector scope.

## 14. Production Investigation Scenario: From Unresponsive to Evidence

### Step 1 — Confirm the Real Incident

Record the UTC incident window, service, pod/instance, host, PID, start time, JVM build, GC/JDK, workload, and error rate. “Requests are hanging” is not enough to classify deadlock immediately.

### Step 2 — Check Capabilities

Obtain `ThreadMXBean` from the right JVM and check `isSynchronizerUsageSupported()` and `isObjectMonitorUsageSupported()` to know which lock details can be collected. Log unsupported/permission errors explicitly rather than turning them into “false.”

### Step 3 — Run the Appropriate Detector

If only a synchronized monitor cycle is suspected, `findMonitorDeadlockedThreads()` can be a starting point. If the application uses `ReentrantLock`/ownable synchronizers and the VM supports it, use `findDeadlockedThreads()` for broader coverage. Both can be costly, so avoid calling too frequently.

### Step 4 — Collect Detailed Thread/Lock Info

When IDs are returned, retrieve `ThreadInfo` with an appropriate stack depth and locked monitors/synchronizers if supported by the VM. Record **thread name/ID, state, lockName, owner ID/name, and top relevant stack frames**. If output is truncated, note the limit clearly.

### Step 5 — Build the Wait-For Graph and Cross-Check Source

Construct edges from waiting threads to lock-owning threads. Confirm the cycle and check which code paths acquired locks in what order. Source line numbers must come from the **exact running JAR/build**, not from opening the current branch and guessing potentially mismatched line numbers.

### Step 6 — Check Outside Scope

If the detector returns `null` while the application is stuck, inspect **virtual threads**, pool starvation, network/DB waits, distributed locks, native locks, and livelocks. Use JFR, OS metrics, tracing, thread dumps, and DB diagnostics as needed.

### Step 7 — Fix Design and Test

Rewrite lock ordering/timeouts/scopes, add concurrency regression tests, benchmark contention/throughput, and monitor after rollout. Do not use kill/`Thread.stop()` as a long-term fix for a discovered deadlock.

A **hypothetical** report sample:

```yaml
captureTimeUtc: "2026-10-29T09:10:00Z"
service: "inventory-api"
instance: "inventory-2"
pid: 12345
processStartUtc: "2026-10-29T08:10:00Z"
javaVersion: "21.0.x"
detector: "ThreadMXBean.findDeadlockedThreads"
scope: "platform_threads, monitors_and_ownable_synchronizers"
capabilities:
  ownableSynchronizerUsage: true
result: "found"
threadCount: 2
cycle:
  - "worker-A waits for worker-B"
  - "worker-B waits for worker-A"
evidence: "ThreadInfo stack and lockOwnerId captured separately"
limitations:
  - "Virtual-thread cycles outside ThreadMXBean scope"
  - "Snapshots are not atomic across API calls"
```

The names, timestamps, and IDs above **only illustrate structure**, not a real case. When reporting an incident, replace them with observed data; never fill in `result=found` unless the detector ran successfully.

## 15. Common Pitfalls to Avoid

| Misconception | Accurate Interpretation |
| --- | --- |
| “Both APIs have similar names so they’re interchangeable.” | `findMonitorDeadlockedThreads` checks monitors only; `findDeadlockedThreads` also checks ownable synchronizers. |
| “A ReentrantLock deadlock is always in BLOCKED state.” | Usually shows `WAITING (parking)`; `BLOCKED` is characteristic of monitor entry. |
| “`findMonitorDeadlockedThreads() == null` means the whole app has no deadlock.” | No **monitor-only platform cycles** were found at measurement time. |
| “`findDeadlockedThreads()` covers all of `java.util.concurrent`.” | Only contract-compliant ownable synchronizers, not every semaphore/queue/read-lock/external wait. |
| “A null ID array equals UnsupportedOperationException.” | Null = none detected; exception = detector could not execute fully. |
| “The APIs automatically return source lines and root cause.” | They return IDs only; you need `ThreadInfo`/stacks/lock owners and source mapping. |
| “ThreadMXBean counts all Java 21 virtual threads.” | Platform threads only in Java 21; cycles with virtual threads go undetected. |
| “If threadInfo is null, the deadlock disappeared.” | The thread may have exited, not exist, or be a virtual thread ID; races exist. |
| “Calling isSynchronizerUsageSupported enables ownable monitoring.” | It is a **capability query**, not a setter; it changes no state. |
| “Any BLOCKED thread is a deadlock.” | Could be transient contention; an ownership cycle must exist. |
| “No Java monitor deadlock means no DB deadlock.” | DB/distributed/native resource locks lie outside this scope. |
| “Deadlock detection guarantees the thread scheduler never hangs.” | It is only a diagnostic snapshot for specific lock types; never use it for synchronization control. |
| “Check every request to prevent deadlocks.” | Can be expensive; use proper lock ordering, timeouts/metrics, and targeted diagnostics. |
| “Deadlocks can be solved with Thread.stop().” | Deprecated and unsafe, easily breaking invariants; fix code and coordinate safe recovery. |
| “Identical thread IDs on two pods mean the same thread.” | IDs are scoped to a JVM/lifetime and can be reused. |
| “Thread dumps always list all virtual threads.” | Traditional dumps focus on platform threads; choose sources that support virtual threads. |

## 16. Self-Check and Answers

**1.** Two platform threads hold two `synchronized` monitors in reverse order. Which method can detect this?

**Answer:** `findMonitorDeadlockedThreads()`; if the VM supports ownable synchronizer usage, `findDeadlockedThreads()` also covers monitor cycles.

**2.** Two platform threads deadlock on two `ReentrantLock`s. Does `findMonitorDeadlockedThreads()` returning `null` prove there is no deadlock?

**Answer:** No. The monitor-only detector does not cover `ReentrantLock` cycles. Use `findDeadlockedThreads()` if the VM supports it.

**3.** The JVM does not support ownable synchronizer monitoring and `findDeadlockedThreads()` throws `UnsupportedOperationException`. Should the dashboard emit `deadlockDetected=false`?

**Answer:** No. Record `check_status=unsupported` and `result=unknown`; you can run the monitor-only detector separately, while noting ownable coverage is missing.

**4.** `findDeadlockedThreads()` returns a `long[]` with two elements. Are those two PIDs or two native TIDs?

**Answer:** No. They are **Java thread IDs in the current JVM**; use `getThreadInfo` to read names/states/owners/stacks.

**5.** A DB outage causes request threads to wait 30 seconds, yet both detectors return `null`. Is that a contradiction?

**Answer:** No. DB locks and remote waits lie outside Java platform-thread monitor/ownable wait-for cycles.

**6.** Java 21 has 10,000 virtual threads waiting; `getThreadCount()` reports 40. Does that mean only 40 threads are alive?

**Answer:** No. The bean counts **platform threads**, excluding virtual threads per the Java 21 contract.

**7.** A virtual thread is alive; what happens when calling `getThreadInfo(virtual.threadId())` in Java 21?

**Answer:** It returns `null` per contract, which does not prove the virtual thread has finished.

**8.** Why check `isSynchronizerUsageSupported()` before calling `findDeadlockedThreads()`?

**Answer:** To know whether the VM supports ownable synchronizer usage; otherwise the method may throw `UnsupportedOperationException`. Permission exceptions should also be handled.

**9.** Why does the lab use `CountDownLatch(2)` before the two threads attempt the second lock?

**Answer:** To guarantee both **already own their first lock**, avoiding a race where one thread acquires and releases both locks before the other participates.

**10.** Why must `findMonitorDeadlockedThreads()` not be called every millisecond inside a request handler?

**Answer:** It is a potentially expensive diagnostic, not a synchronization control primitive; use properly designed locking, timeouts/metrics, and targeted diagnostics.

**11.** Seeing two threads `BLOCKED` on the same lock—is that enough to claim deadlock?

**Answer:** Not yet. There must be an ownership wait cycle. One thread holding and later releasing a lock is contention, not a cycle.

**12.** A cycle involves a platform thread and a virtual thread. Does the Java 21 detector guarantee finding it?

**Answer:** No. Documentation only guarantees finding cycles consisting of platform threads; cycles containing virtual threads are not found by these two APIs.

## 17. Practice Checklist

- Remember **`findMonitorDeadlockedThreads` = object monitors**, **`findDeadlockedThreads` = monitors + ownable synchronizers**.
- Both target **platform threads** in Java 21; virtual-thread cycles are out of scope.
- **`null`** = no cycle found within scope/timestamp, not “healthy.”
- `findDeadlockedThreads()` can throw **`UnsupportedOperationException`**; check `isSynchronizerUsageSupported()`.
- Use `getThreadInfo(ids, lockedMonitors, lockedSynchronizers, maxDepth)` to fetch owners/locks/stacks; handle `null` elements in results.
- Thread IDs are not OS PIDs/TIDs and do not apply across JVMs/restarts.
- Lock-ownership deadlocks differ from contention, starvation, livelock, and DB/distributed/native locks.
- Run the Java 17+ `DeadlockMxBeanLab` in **two separate processes** for `monitor` and `ownable`.
- Run the Java 21+ `VirtualThreadMxBeanScopeLab` to observe `getThreadInfo(virtualId) == null` even while the virtual thread is alive.
- Record timestamp, service/instance/PID/start time, capabilities, scope, result, and limitations.
- Never use detectors as **synchronization control**, never poll tightly, and never release locks via unsafe operations.
- Fix sustainably via **consistent lock ordering**, reducing lock-holding scope, timeout handling, and concurrency regression tests.

**Conclusion:** `ThreadMXBean`’s two deadlock detection methods are very useful when platform threads wait on object monitors and ownable synchronizers. However, they are **not equivalent in coverage**, have permission/support/cost constraints, and specifically **do not monitor virtual threads** in JDK 21. Reliable conclusions require combining IDs with `ThreadInfo`, lock-owner graphs, stack frames, and exact incident context; `null` only means “not detected within API scope,” not confirmation that the application has no hang.

### Official References

- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform thread scope, both detection methods, `isSynchronizerUsageSupported`, `getThreadInfo`, and exceptions.
- [Java SE 21 — ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html): owner ID/name, lockName, state, stack frames, locked monitors, and ownable synchronizers.
- [Java SE 21 — LockInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/LockInfo.html): definitions of object monitor/ownable synchronizer and ReentrantLock/write-lock examples.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): how to obtain the JVM’s ThreadMXBean.
- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual threads, dedicated thread dumps, and JFR events.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print`, diagnostic command support/impact.