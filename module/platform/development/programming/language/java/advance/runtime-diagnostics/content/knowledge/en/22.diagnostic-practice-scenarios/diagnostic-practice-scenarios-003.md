# 22.3 Reproducing a Deadlock and Building a Wait-For Graph from Multiple Evidence Sources

## Objective

A **deadlock** is a state where a group of threads cannot make progress because each thread is waiting for a resource held by another thread in the same group, forming a **circular wait relationship**. In Java, an easily verifiable example is two platform threads acquiring two monitors in opposite orders.

This practice lab walks through:

1. **Intentionally and reproducibly triggering a deadlock** with `synchronized`, two object locks, and `CountDownLatch`; rather than merely nudging probability with `Thread.sleep`.
2. Reading **`ThreadMXBean.findMonitorDeadlockedThreads()`**, **`findDeadlockedThreads()`**, **`ThreadInfo.getLockOwnerName()`**, thread states, and held monitors.
3. Capturing **`jcmd PID Thread.print -l`** or **`jstack -l`**, matching `waiting to lock`/`locked` lines by identical monitor identity, and cross-checking the owner from MXBean.
4. Recording **JFR custom events** marking points before entering BLOCKED, reading summary/metadata/print, and understanding why an infinite-wait `jdk.JavaMonitorEnter` event may be absent from the recording.
5. Building a directed **wait-for graph**, verifying edges A → B and B → A, and detecting the cycle.
6. Fixing the bug via **global lock ordering**, verifying with an appropriate regression test, and distinguishing monitor deadlock from contention, starvation, sleep/park, I/O stalls, and distributed deadlocks.

**Safety:** the first program intentionally leaves two threads stuck permanently. Run it only in an authorized lab environment, never in a production service; never use `Thread.stop` or `kill -9` to "test" a live application.

## 1. How Does a Wait Cycle Form?

Suppose two shared objects have monitors given readable names LEFT and RIGHT.

~~~text
worker-A                      worker-B
--------                      --------
synchronized(LEFT)            synchronized(RIGHT)
  holds LEFT                    holds RIGHT
        |                             |
  requests RIGHT                requests LEFT
        |                             |
  B holds RIGHT                 A holds LEFT
        |                             |
        +----------- cycle -----------+
~~~

Two levels of representation:

~~~text
Resource graph:
  worker-A --> RIGHT --> worker-B --> LEFT --> worker-A

Thread-only wait-for graph:
  worker-A --> worker-B
  worker-B --> worker-A
~~~

By convention, **T → U** means T is waiting for a lock held by U. Two opposing edges create a cycle; a Java monitor belongs to only one thread at a time, so neither thread can acquire the next lock and complete on its own.

### Four Conditions to Understand

- **Mutual exclusion:** a monitor cannot be owned simultaneously by two threads.
- **Hold and wait:** each thread holds one lock while waiting for another lock.
- **No preemption:** there is no safe mechanism to forcibly take a monitor away from its owning thread.
- **Circular wait:** A waits for B and B waits for A.

A single **BLOCKED** thread does not prove a deadlock: it may simply be waiting for another thread to finish work. You must prove a **closed wait cycle** or equivalent deadlock evidence.

**`synchronized` has no timed try-acquire** like `ReentrantLock.tryLock(timeout,...)`. When a worker is BLOCKED trying to enter an intrinsic monitor, a regular interrupt does not make it release its held monitor or cancel the lock acquisition.

## 2. Evidence to Collect

| Source | Questions It Can Answer | Limitations |
| --- | --- | --- |
| **Source code** | Which lock acquisition orders could form a cycle? | Code shows possibility, does not prove runtime state |
| **ThreadMXBean** | Which threads are BLOCKED, waiting on which lock, who is the owner? Is there a monitor cycle? | Mainly platform threads and resource kinds supported by the JVM |
| **jcmd Thread.print -l** | Stack, state, waiting-to-lock identity, and locked identity at capture time? | Snapshots can add latency; format varies by JVM/JDK |
| **JFR custom event** | When did A/B hold the first lock and attempt the second lock? | Application milestones, not independent proof of current owner |
| **JFR built-in events** | Was there contention/park/wait before the incident? | Subject to event settings, thresholds, and incomplete ongoing waits |
| **OS/JVM metrics** | Right PID? Is the process alive? Did CPU/threads change? | OS does not decode Java monitor ownership by itself |

More files do not automatically mean more truth. **Thread dumps and ThreadMXBean** prove the owner graph; **JFR** proves the timeline leading into that state; **source code** explains why that sequence creates a wait cycle.

## 3. Why Use CountDownLatch Instead of Thread.sleep?

A naive example using `Thread.sleep` hoping both threads hold their first lock at the same instant might **never reproduce** the deadlock under another scheduler.

We use two `CountDownLatch` instances:

1. Worker A enters `synchronized(LEFT)`, records that A owns LEFT, and opens latch A.
2. Worker B enters `synchronized(RIGHT)`, records that B owns RIGHT, and opens latch B.
3. A is allowed to try `synchronized(RIGHT)` only after knowing B already holds RIGHT.
4. B is allowed to try `synchronized(LEFT)` only after knowing A already holds LEFT.
5. Both continue **holding their first lock** while waiting/attempting the second lock, so the wait cycle reliably forms.

While waiting on the latches, threads may show state **WAITING**. Once both latches open and they contend for the second lock, they transition to **BLOCKED (on object monitor)**. Pick the right moment to capture the thread dump.

## 4. Standalone Java 17+ Program: DeadlockEvidenceLab.java

The program creates a monitor deadlock, records custom JFR events **lab.LockMilestone**, detects the cycle with `ThreadMXBean`, exports **deadlock-evidence.jfr**, and keeps the JVM alive for about 120 seconds so you can take a thread dump from another terminal.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.CountDownLatch;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class DeadlockEvidenceLab {
    private static final Object LEFT = new Object();
    private static final Object RIGHT = new Object();

    private static final CountDownLatch LEFT_HELD =
            new CountDownLatch(1);
    private static final CountDownLatch RIGHT_HELD =
            new CountDownLatch(1);

    @Name("lab.LockMilestone")
    @Label("Lock Milestone")
    @Category({"Lab", "Concurrency"})
    public static class LockMilestone extends Event {
        @Label("Worker")
        public String worker;
        @Label("Action")
        public String action;
        @Label("Lock Name")
        public String lockName;
    }

    private static void emit(String worker, String action,
                             String lockName) {
        LockMilestone event = new LockMilestone();
        if (event.isEnabled()) {
            event.worker = worker;
            event.action = action;
            event.lockName = lockName;
            event.commit();
        }
    }

    private static void launch(String name,
                               Object first, String firstName,
                               Object second, String secondName,
                               CountDownLatch own,
                               CountDownLatch other) {
        Thread worker = new Thread(() -> {
            synchronized (first) {
                emit(name, "ACQUIRED_FIRST", firstName);
                own.countDown();

                try {
                    other.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }

                emit(name, "TRY_SECOND", secondName);
                synchronized (second) {
                    // Intentional deadlock: execution will not reach here.
                    emit(name, "ACQUIRED_SECOND", secondName);
                }
            }
        }, name);

        // Only so main can exit after the lab window:
        worker.setDaemon(true);
        worker.start();
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable(LockMilestone.class)
                    .withoutThreshold();
            recording.start();

            launch("worker-A", LEFT, "LEFT", RIGHT, "RIGHT",
                    LEFT_HELD, RIGHT_HELD);
            launch("worker-B", RIGHT, "RIGHT", LEFT, "LEFT",
                    RIGHT_HELD, LEFT_HELD);

            ThreadMXBean bean =
                    ManagementFactory.getThreadMXBean();
            long[] ids = null;

            // Lab: wait up to ~5 seconds to check for the cycle.
            // Do not poll this tightly in production.
            for (int attempt = 0; attempt < 100; attempt++) {
                ids = bean.findMonitorDeadlockedThreads();
                if (ids != null && ids.length == 2) {
                    break;
                }
                Thread.sleep(50L);
            }
            if (ids == null || ids.length != 2) {
                throw new IllegalStateException(
                        "Expected a two-thread monitor deadlock");
            }

            ThreadInfo[] infos =
                    bean.getThreadInfo(ids, true, true);
            Arrays.sort(infos, Comparator.comparing(
                    ThreadInfo::getThreadName));

            System.out.println("Deadlocked threads: "
                    + infos.length);
            for (ThreadInfo info : infos) {
                System.out.println(info.getThreadName()
                        + " -> " + info.getLockOwnerName()
                        + " (" + info.getThreadState() + ")");
            }

            recording.stop();
            recording.dump(Path.of("deadlock-evidence.jfr"));

            System.out.println("JFR saved: deadlock-evidence.jfr");
            System.out.println("PID: "
                    + ProcessHandle.current().pid());
            System.out.println("Snapshot window: 120 seconds");

            Thread.sleep(120_000L);
        }
    }
}
~~~

**Compile and run** on JDK 17+ HotSpot/OpenJDK with the `jdk.jfr` module:

~~~bash
javac --add-modules java.management,jdk.jfr DeadlockEvidenceLab.java
java --add-modules java.management,jdk.jfr DeadlockEvidenceLab
~~~

**Lines printed by the program on a successful run** (PID changes per run):

~~~text
Deadlocked threads: 2
worker-A -> worker-B (BLOCKED)
worker-B -> worker-A (BLOCKED)
JFR saved: deadlock-evidence.jfr
PID: <actual PID>
Snapshot window: 120 seconds
~~~

**`<actual PID>` is an illustrative placeholder**, not literal Java output. Aside from the PID, the two edges and order of those two lines are deterministic because they are sorted by thread name. Actual JFR output has scheduler-dependent timestamps and event ordering.

If JFR is unsupported in the runtime, the file cannot be written, or the thread detector hits permission/VM capability errors, the example may throw an exception; fix the environment rather than treating this as "no deadlock".

### Notes on Key Points

- **`CountDownLatch`** guarantees both threads have entered their first lock before attempting the second lock; no fake sleeps "hoping for lucky timing".
- **`ThreadMXBean.findMonitorDeadlockedThreads()`** returns IDs of threads in an object monitor cycle, or **null** if no cycle within its supported scope is found.
- **`getThreadInfo(ids, true, true)`** requests lock ownership details; HotSpot normally supports monitors and ownable synchronizers.
- **`Recording.stop()` then `dump(Path)`** saves the custom milestone events before the learner runs `jcmd`, so the file is readable while the JVM remains alive.
- **`setDaemon(true)`** does not "fix" a deadlock; it only allows the JVM to exit once `main` and other non-daemon threads finish. Never apply this to fix a real service.
- **Snapshot window 120 seconds** is simply a window for opening another terminal. It is not a guarantee about tool or system deadlines.

### Why Will This Program Form a Wait Cycle?

At the moment each latch counts down, that thread is **inside `synchronized(first)`**. `LEFT_HELD` and `RIGHT_HELD` open together only after A holds LEFT and B holds RIGHT. Both monitors remain held when `await` returns. A needs RIGHT held by B; B needs LEFT held by A. Consequently neither thread can proceed until the other releases its lock, and the other cannot release its lock while blocked.

Both **ACQUIRED_FIRST** custom events occur before the same worker's **TRY_SECOND** event. However, ordering between A and B is not fixed. **ACQUIRED_SECOND** does not appear in a normal recording because neither thread acquires the second lock.

## 5. Detection via ThreadMXBean

**`java.lang.management.ThreadMXBean`** provides thread state and lock ownership data inside the JVM. APIs to distinguish:

| API | Scope |
| --- | --- |
| **findMonitorDeadlockedThreads()** | Cycles of platform threads waiting on **object monitors** (`synchronized`) |
| **findDeadlockedThreads()** | Cycles of platform threads waiting on **object monitors or ownable synchronizers** such as `ReentrantLock` when supported by the VM |
| **getThreadInfo(ids, true, true)** | Stacks and locked monitor/ownable synchronizer details for the given IDs |
| **dumpAllThreads(true, true)** | Snapshot of live **platform threads**, potentially expensive when thread count is very high |

In **Java 21**, `ThreadMXBean` does not support monitoring **virtual threads**; returning `null` from the detector does not prove the whole system is deadlock-free, especially for cycles involving virtual threads, database locks, or distributed JVMs.

### ThreadInfo: Fields to Record

- **`getThreadName()` / `getThreadId()`**: thread name and Java thread ID at snapshot time; Java ID is not OS TID/`nid`.
- **`getThreadState()`**: `BLOCKED`, `WAITING`, `TIMED_WAITING`, `RUNNABLE`...
- **`getLockName()` / `getLockInfo()`**: the object the thread is waiting on.
- **`getLockOwnerName()` / `getLockOwnerId()`**: the thread owning the awaited monitor/ownable synchronizer.
- **`getLockedMonitors()`**: monitors held by the thread.
- **`getLockedSynchronizers()`**: ownable synchronizers held by the thread.
- **`getStackTrace()`**: frames/code path currently blocked.
- **`getBlockedTime()`**: may return `-1` when contention monitoring is disabled or unsupported.

An **edge** is created whenever there is a clear relation: "thread T waits on a lock held by thread U" → **T → U**.

~~~text
worker-A state=BLOCKED
  waiting=RIGHT; owner=worker-B; holds=LEFT
  => worker-A --> worker-B

worker-B state=BLOCKED
  waiting=LEFT; owner=worker-A; holds=RIGHT
  => worker-B --> worker-A
~~~

In real output, `ThreadMXBean` knows lock identities/owners but does not inherently know business labels **LEFT/RIGHT** unless code describes them; that mapping comes from combining with source. Always use owner IDs/monitor identities from **the same snapshot** when building the graph, rather than matching thread names alone.

### BLOCKED, WAITING, and TIMED_WAITING

- **`BLOCKED`** means waiting to enter/reenter a held intrinsic monitor.
- **`WAITING`** can come from `Object.wait()`, `CountDownLatch.await()`, `Thread.join()`, or `LockSupport.park()`; it does not automatically mean deadlock.
- **`TIMED_WAITING`** can come from `Thread.sleep()`, timed await/park; usually carries a normal timeout.
- **`RUNNABLE`** does not guarantee a thread is actively consuming CPU at OS measurement time; it may be in native operations.

Early in the demo run, threads waiting on the latch may show **WAITING**. Once both try `synchronized(second)`, they become **BLOCKED**. That is why capturing at the right time and, when time permits, repeating a few seconds later matters.

## 6. Independent Source: jcmd Thread.print -l and jstack -l

While the JVM is still alive, open another terminal on **the same host/namespace able to attach to the JVM**.

### 6.1. Finding the Right PID

~~~bash
jcmd -l
jcmd <PID> help Thread.print
~~~

Replace **`<PID>`** with the process number printed by the program. Angle brackets are placeholders; do not type them literally in the shell. With Docker/Kubernetes, PIDs inside a container and on the host may differ; `jcmd` requires attach permissions and matching effective user/group.

### 6.2. Capturing a Thread Dump

~~~bash
jcmd <PID> Thread.print -l > deadlock-thread-dump.txt
~~~

In JDK 21, **`Thread.print -l`** prints stacks and lock/concurrent synchronizer details; it usually includes a Java-level deadlock section when the VM detects one. Exact flags and fields should be verified with **`jcmd PID help Thread.print`** per JDK version.

You can also use:

~~~bash
jstack -l <PID> > deadlock-jstack.txt
~~~

Oracle documentation recommends preferring `jcmd` for most diagnostic tasks. When little time remains before a restart, prioritize **one complete snapshot** instead of waiting for multiple tools. Thread dumps can introduce overhead when thread counts are huge or the VM is unresponsive to attach.

### 6.3. Abbreviated Sample Thread Dump

This is a **structural example**, not fixed stdout; addresses, line numbers, `nid`, and formatting vary by JVM:

~~~text
"worker-A" ... java.lang.Thread.State: BLOCKED (on object monitor)
  - waiting to lock <0x0000BBBB> (a java.lang.Object)
  - locked <0x0000AAAA> (a java.lang.Object)

"worker-B" ... java.lang.Thread.State: BLOCKED (on object monitor)
  - waiting to lock <0x0000AAAA> (a java.lang.Object)
  - locked <0x0000BBBB> (a java.lang.Object)

Found one Java-level deadlock:
  worker-A waits for monitor held by worker-B
  worker-B waits for monitor held by worker-A
~~~

How to reason from it:

1. A is waiting for monitor **BBBB**.
2. B has **locked BBBB**.
3. B is waiting for monitor **AAAA**.
4. A has **locked AAAA**.
5. Therefore **A → B → A**, a cycle from which neither thread can advance.

**Do not assume values `0xAAAA`/`0xBBBB` are fixed.** In real output, match exact monitor ID tokens within **the same thread dump**. Do not compute **`System.identityHashCode(obj)`** and compare it directly with VM object addresses: they are different concepts/representations.

### 6.4. If the State Is Uncertain

Take a second snapshot after a short delay if the process is still alive:

~~~bash
sleep 5
jcmd <PID> Thread.print -l > deadlock-thread-dump-2.txt
~~~

In a true deadlock, the owner cycle repeats and threads make no progress. However, long monitor contention can also appear unchanged across two snapshots; **the ownership/waiting cycle itself** is the decisive criterion.

If `jcmd` fails to attach, log the error with a timestamp instead of concluding "no deadlock". Some HotSpot builds on Linux print a dump on **SIGQUIT** per runbook, though that requires permissions, the right process, and output management. Never send `kill -9` or intentionally destroy evidence.

## 7. Timeline Source: JFR Custom Milestone Events

In the lab program, the recording is configured with:

~~~java
recording.enable(LockMilestone.class)
        .withoutThreshold();
recording.start();
~~~

Once the detector finds the cycle, the program calls **`stop()` then `dump()`** to write the JFR file. Custom type **`lab.LockMilestone`** has fields:

| Field | Example | Meaning |
| --- | --- | --- |
| `worker` | `worker-A` | Thread emitting the milestone |
| `action` | `ACQUIRED_FIRST`, `TRY_SECOND` | Code checkpoint reached |
| `lockName` | `LEFT`, `RIGHT` | Developer-defined business label |
| `startTime`/`eventThread` | Recorded by JVM if enabled | Timestamp/thread producing the event |

Commands:

~~~bash
jfr summary deadlock-evidence.jfr
jfr metadata --events lab.LockMilestone deadlock-evidence.jfr
jfr print --events lab.LockMilestone deadlock-evidence.jfr
~~~

- **summary**: recording start/duration, instance counts per type, and serialized size.
- **metadata**: event name, category, field schema.
- **print**: individual instances, field values, and timestamps.

On a clean run, there are **four milestone records**: A and B each emit **ACQUIRED_FIRST** and **TRY_SECOND**. Example of one valid sequence:

~~~text
worker-A  ACQUIRED_FIRST  LEFT
worker-B  ACQUIRED_FIRST  RIGHT
worker-B  TRY_SECOND      LEFT
worker-A  TRY_SECOND      RIGHT
~~~

Ordering between A and B can vary. **There is no ACQUIRED_SECOND** because `synchronized(second)` is never entered. Do not infer from custom JFR events alone which thread actually owns a lock: code-emitted milestones describe the timeline, while thread dumps/`ThreadInfo` serve as independent proof of current ownership.

### Why Might `jdk.JavaMonitorEnter` Miss the Deadlocking Event?

In JFR, **`jdk.JavaMonitorEnter`** describes contended monitor entry and is typically a duration event. For a wait that **never finishes**, the event has no completion point to commit under normal mechanics; the file may contain no matching instance. Events also depend on **`enabled`/`threshold`/recording period**.

Distinguish:

- **`jdk.JavaMonitorEnter`**: contention when entering a monitor.
- **`jdk.JavaMonitorWait`**: related to `Object.wait()`, not the same as every `BLOCKED` monitor entry.
- **`jdk.ThreadPark`**: thread parking (e.g., in certain `java.util.concurrent` waits), not standalone proof of every deadlock.
- **JFR `JavaMonitorEnter` Count=0**: does not prove there is no deadlock, since the event may still be waiting to finish or disabled.

For another production recording (the file must actually exist):

~~~bash
jfr summary incident.jfr
jfr metadata --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark incident.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark incident.jfr
~~~

These events mainly provide **contention/park context before getting stuck**, whereas current cycle proof should come from thread snapshots/`ThreadMXBean` while the JVM is alive. A recording started **after a deadlock already formed** cannot reconstruct earlier `ACQUIRED_FIRST` milestones.

### Why Not Enable High-Frequency Custom Lock Events Everywhere in Production?

Recording an event on every lock at millions per second can add significant overhead. Instrument only critical sections or high-value workflows, keep fields small, configure appropriate thresholds/retention, and never log secrets. Telemetry can also perturb timing; corroborate with independent data.

## 8. Combining Evidence into a Matrix and Graph

| Question | MXBean | jcmd dump | JFR | Code |
| --- | --- | --- | --- | --- |
| Is A currently BLOCKED? | `getThreadState` | `BLOCKED` entry | Not necessarily | Possible |
| Is A waiting for a lock held by B? | `getLockOwnerName`/`Id` | `waiting`/`locked` same identity | `TRY_SECOND(RIGHT)` | LEFT → RIGHT |
| Is B waiting for a lock held by A? | `getLockOwnerName`/`Id` | `waiting`/`locked` same identity | `TRY_SECOND(LEFT)` | RIGHT → LEFT |
| Is there a cycle? | `findMonitorDeadlockedThreads` | Deadlock section and owner graph | Context, insufficient alone | Design can form a cycle |
| Initial timeline? | Snapshot time | Dump timestamp | `ACQUIRED_FIRST`/`TRY_SECOND` timestamps | Lacks runtime timestamps |
| Any progress? | Same state on re-check | Multiple dumps | No `ACQUIRED_SECOND` in demo | Operation never enters next critical section |

**Strong conclusion:** MXBean confirms A waits on B and B waits on A, `jcmd` shows the same relation via monitor IDs, and JFR gives the milestones leading to the waited objects. **Weak conclusion:** merely seeing two BLOCKED threads or one long JFR `ThreadPark`.

### Building a Wait-For Graph Step by Step

1. Make each **platform thread ID** a vertex, keeping the thread name as a label.
2. For each thread T with a verified lock owner U, add directed edge **T → U**.
3. Attach edge metadata: waiting monitor identity, owner identity, thread state, timestamp.
4. Run DFS with **WHITE/GRAY/BLACK** states to detect a back-edge to a GRAY vertex; or run strongly connected components.
5. If a closed cycle exists, reconstruct the sequence of thread IDs and monitors in the cycle.
6. Confirm with a second source from the same time window; never merge snapshots from different restarts or PIDs into one graph.

DFS complexity is **O(V+E)** for V threads and E edges once lock ownership is properly read. If `getLockOwnerId() == -1` or owner is `null`, the graph is **incomplete**; never invent edges by guessing.

A chain A → B → C where C is running and able to release its lock **does not form a cycle**; that is contention/backpressure or another stall, not yet proof of a Java deadlock.

## 9. Distinguishing Similar-Looking Scenarios

| Phenomenon | Symptoms | How to Prove |
| --- | --- | --- |
| Intrinsic monitor deadlock | `BLOCKED` and owner cycle | `jcmd`/MXBean monitor identities |
| `ReentrantLock` deadlock | `WAITING`/park, ownable synchronizers held in a cycle | `findDeadlockedThreads` + lock ownership |
| Lock contention | A waits on B, but B is still running and can release the lock | Multiple snapshots, owner progresses |
| Thread pool starvation | Tasks wait on each other/queue with no free worker | Queue/task dependency graph; MXBean may return `null` |
| Livelock | Threads `RUNNABLE`/retrying yet making no progress | CPU, retry counters, JFR/progress |
| Socket/file I/O stall | Stack in network/file call | I/O latency/timeout, downstream metrics |
| Normal `Object.wait` | `WAITING` on monitor | Notifier/condition and wait contract |
| Distributed deadlock | Transactions/services locking resources across processes | DB locks, transaction IDs, traces |
| Virtual-thread cycle | Java 21 MXBean lacks full visibility | Virtual-thread-aware tools and dependency graphs |

**Do not assume every hang is a monitor deadlock.** In particular, database row locks are outside Java object monitors; use database diagnostics when the wait cycle lives there.

## 10. Fixing the Bug with a Consistent Lock Order

For two monitors, the straightforward fix is requiring **every code path** to acquire LEFT before RIGHT, never RIGHT before LEFT while already holding a lock.

Illustrative snippet (runs only when LEFT/RIGHT are declared in the class):

~~~java
private static void updateSafely() {
    synchronized (LEFT) {
        synchronized (RIGHT) {
            // Update shared state.
        }
    }
}
~~~

This eliminates **wait cycles caused by inverted lock acquisition order**. Contention can still occur, however, and another bug can still cause deadlock if inner calls acquire additional locks in inconsistent orders.

Do not treat increasing thread counts, HTTP timeouts, or making threads daemon as fixes for a deadlock. None of those break a monitor cycle.

### Why Must the Old Test Harness Be Replaced?

The original demo required **both workers to hold their `first` lock** before attempting the second lock. Once both A and B use **LEFT → RIGHT**, worker A can acquire LEFT and then wait for worker B to signal that it holds LEFT; B cannot acquire LEFT to signal, so the **`CountDownLatch` barrier itself** becomes an infinite wait point. If you keep the old barrier, you would mistakenly think the fix failed.

Therefore, testing the fix uses a **start latch before entering any monitor**, letting both workers start close together and then joining with a timeout. Never use test synchronization that demands two threads simultaneously hold the same exclusive monitor.

## 11. Second Java 17+ Program: SafeLockOrderDemo.java

This standalone program verifies that both workers using a shared global lock order complete cleanly.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class SafeLockOrderDemo {
    private static final Object LEFT = new Object();
    private static final Object RIGHT = new Object();
    private static final CountDownLatch START =
            new CountDownLatch(1);

    private static void work() {
        synchronized (LEFT) {
            synchronized (RIGHT) {
                // Both workers use the same lock order.
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread a = new Thread(() -> {
            try {
                START.await();
                work();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "worker-A");

        Thread b = new Thread(() -> {
            try {
                START.await();
                work();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "worker-B");

        a.start();
        b.start();
        START.countDown();

        a.join(TimeUnit.SECONDS.toMillis(5));
        b.join(TimeUnit.SECONDS.toMillis(5));

        if (a.isAlive() || b.isAlive()) {
            throw new IllegalStateException(
                    "Workers did not finish in time");
        }
        System.out.println("Both workers completed");
    }
}
~~~

~~~bash
javac SafeLockOrderDemo.java
java SafeLockOrderDemo
~~~

On normal completion, **exact stdout**:

~~~text
Both workers completed
~~~

**Properly scoped conclusion:** this small program completes without a monitor cycle across the two tested critical sections. It **does not prove** all call paths in a production application are deadlock-free. You need code review of lock ordering, regression tests on nested call paths, and reproducible load/chaos tests.

### When Timeouts Are Needed to Avoid Infinite Waits

**`ReentrantLock.tryLock(timeout, unit)`** lets you back off from acquiring the second lock and release the first lock in `finally`; however, `ReentrantLock` still deadlocks if `lock()` is called in opposite orders. Infinite retries after timeout risk **livelock**. Timeouts/retries must follow business contracts, maintain idempotency/backoff, and protect shared-state invariants.

The fragment below is purely illustrative when `first`/`second` are two `ReentrantLock` instances and `updateState`/`reportRetry` are application-defined methods:

~~~java
if (first.tryLock()) {
    try {
        if (second.tryLock(100, TimeUnit.MILLISECONDS)) {
            try {
                updateState();
            } finally {
                second.unlock();
            }
        } else {
            reportRetry();
        }
    } finally {
        first.unlock();
    }
}
~~~

You must handle the case where **`first.tryLock()` returns `false`** (e.g., retry or fail). Do not copy this fragment as a standalone program; it requires the surrounding class, variables, and imports.

### Ways to Reduce Deadlock Risk in a Codebase

- Enforce a **global lock order** by resource IDs across all call paths.
- Never perform network, DB I/O, or uncontrolled callback/plugin calls while holding locks.
- Minimize nested locking; use immutable snapshots, actor/message passing, or concurrent collections where appropriate.
- Avoid ordering multi-object locks by identity hash without collision tie-breaking.
- Document and enforce lock ordering in API contracts and automate reviews where feasible.
- Monitor queued/blocked threads in production, while avoiding overly aggressive deadlock-detector polling due to overhead.

## 12. Response Procedure When a Deadlock Hits a Live System

1. **Verify the exact JVM**: timestamp, PID, container ID/Pod UID, host, JVM start time, version/build, and request status.
2. **Capture a thread dump immediately** if hung/blocked threads are the primary symptom. Do not start with a huge heap dump when there is no evidence of heap retention.
3. **Dump any running JFR** if available to preserve the timeline before restarting. A fresh recording cannot reconstruct the past.
4. **Build edges** T → owner from lock identities/`ThreadInfo`; confirm the cycle and stack frames leading to the acquisition order.
5. If time allows, take a second snapshot and correlate `ThreadMXBean`/JFR with request queues/GC/I/O.
6. Perform restarts/mitigations only once approved; secure diagnostic artifacts first.
7. After fixing, write a deterministic reproduction test and verify correctness/throughput, not just "no deadlock seen in one run".

JFR data, thread dumps, and logs can contain method names, business details, paths, and even secrets depending on instrumentation. Protect them with access control, encryption/retention policies; never share production HPROF/JFR/thread dumps publicly.

## 13. Common Mistakes

1. Seeing two BLOCKED threads and concluding deadlock without checking the owner cycle.
2. Confusing `WAITING` on `CountDownLatch` with monitor entry `BLOCKED`.
3. Relying on `Thread.sleep` to guarantee race reproduction.
4. Trusting source code without capturing runtime state.
5. Treating custom JFR `TRY_SECOND` as independent proof of the current monitor owner.
6. Seeing no `jdk.JavaMonitorEnter` and denying a deadlock exists.
7. Seeing `findDeadlockedThreads()` return `null` and denying deadlocks outside MXBean's scope.
8. Keying the graph by thread name when multiple threads share a name; use thread IDs.
9. Confusing Java thread ID with Linux TID/`nid`.
10. Comparing Java `identityHashCode` with internal monitor addresses in a dump.
11. Merging edges from two PIDs or two snapshots from different times.
12. Treating Java monitor deadlock and distributed database deadlock as the same detection scope.
13. Assuming `ReentrantLock` automatically prevents all deadlocks.
14. Using `Thread.stop` or interrupting a BLOCKED `synchronized` thread as a fix.
15. Changing lock order while keeping a test barrier that relies on the inverted order.
16. Enabling heavy profiling or event recording on an already strained production JVM.
17. Running `jcmd` repeatedly when the JVM cannot attach, wasting the evidence window.
18. Concluding a fix is complete because one small test passed, ignoring other call paths.

## 14. Self-Check Exercises

**Question 1.** A thread dump shows A BLOCKED waiting on lock X held by B; B BLOCKED waiting on lock Y held by A. Is there a cycle?  
**Answer:** Yes, if those waiting/owner relationships belong to the same snapshot: **A → B → A**.

**Question 2.** A is BLOCKED waiting on B, while B is RUNNABLE doing I/O and will release the lock. Is it definitely a Java deadlock?  
**Answer:** Not yet. There is only A → B, without B → A forming a cycle. It may be contention or an I/O stall.

**Question 3.** JFR `lab.LockMilestone` records 4 events and no `ACQUIRED_SECOND`. Does that alone prove a deadlock?  
**Answer:** No. It proves code reached `TRY_SECOND`, not independent confirmation of lock ownership; you need `ThreadInfo`/thread dumps.

**Question 4.** Why might a thread waiting forever on `synchronized` fail to produce a `jdk.JavaMonitorEnter` instance in JFR?  
**Answer:** Contention events are duration events typically committed when monitor entry completes; an infinite wait may have no end point, alongside `enabled`/`threshold` constraints.

**Question 5.** How do `findMonitorDeadlockedThreads` and `findDeadlockedThreads` differ?  
**Answer:** The former checks only object monitors; the latter also checks ownable synchronizers on platform threads when supported by the JVM.

**Question 6.** Why can changing both threads to LEFT → RIGHT while keeping two latches waiting for "each worker holds its first lock" hang the test?  
**Answer:** Because the first lock is now identical and mutually exclusive: one worker holds LEFT waiting for the other to signal it holds LEFT, which cannot happen. The harness must be redesigned.

**Question 7.** In Java 21, does `ThreadMXBean` returning `null` prove no virtual-thread deadlock exists?  
**Answer:** No. The API does not support virtual-thread monitoring; appropriate tools and dependency graphs are required.

**Question 8.** A dump shows `waiting to lock 0xABC` on A and `locked 0xABC` on B. What do you do next?  
**Answer:** Add edge A → B, check whose monitor B is waiting on, look for a cycle, and cross-check with MXBean in the same JVM/snapshot window.

## 15. References

- [Oracle JDK 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform thread scope, `findMonitorDeadlockedThreads`, `findDeadlockedThreads`, and lock information.
- [Oracle JDK 21 — ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html): `Thread.State`, `getLockOwnerId`/`Name`, `getLockedMonitors`, and `getLockedSynchronizers`.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print -l`, `help`, attach permissions, and impact.
- [Oracle JDK 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): capturing thread dumps with `jcmd`/`jstack` and analyzing deadlocks/hangs.
- [Oracle JDK 21 — JFR Recording](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): `enable`, `start`, `stop`, `dump`, and custom event lifecycle.
- [Oracle JDK 21 — JFR Event](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html): custom events, `isEnabled`, and `commit`.
- [Oracle JDK 21 — jfr command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `metadata`, and `print`.
- [Oracle JDK 21 — Troubleshooting JFR](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html): `JavaMonitorEnter`/`Wait`, `ThreadPark`, event thresholds, and latency.