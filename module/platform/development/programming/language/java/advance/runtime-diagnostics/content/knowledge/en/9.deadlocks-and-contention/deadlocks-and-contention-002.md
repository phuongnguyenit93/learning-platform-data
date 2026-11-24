# 9.2 — Tracing the Lock Ownership Chain and Building Wait-For Graphs from Thread Dumps

## 1. Problem: Which Thread Is Waiting on Whom?

When a Java application makes no progress, many threads may be in the `BLOCKED`, `WAITING`, or `TIMED_WAITING` state. Looking at state alone is not enough to conclude deadlock: a worker may be waiting for a task normally; a thread may be waiting on a database; several threads may all be waiting for a monitor held by another thread. The more important diagnostic question is:

> **Which lock L is thread T waiting on? Which thread H currently holds L? What is H doing — is it in turn waiting on a lock held by another thread?**

By chaining **waiter → owner** relationships from a thread dump, we build a **wait-for graph**. If we find a directed cycle, such as `A → B → C → A`, and the edges accurately represent waiting for lock ownership, that is evidence of a **lock-cycle deadlock** at the time of the snapshot.

After this lesson, learners should be able to:

1. Read headers, thread states, stack frames, `waiting to lock`, `locked`, and the `Locked ownable synchronizers` section.
2. Match **exact lock identities** between a waiting thread and the owning thread, rather than matching merely by thread name or class.
3. Build a directed graph from `waiter → owner` chains, detect cycles, and distinguish a **wait chain that has not formed a cycle** from a deadlock.
4. Distinguish `synchronized` monitors from `ReentrantLock`/`AbstractOwnableSynchronizer` and wait types that have no visible owner.
5. Reproduce a wait cycle using Java 17, take a thread dump with `jcmd`, and cross-check with `ThreadMXBean.findMonitorDeadlockedThreads()`.
6. Understand the limitations of snapshots, attach permissions, sampling timing, and remediation steps.

**Key takeaway:** a thread dump is **evidence of a single point in time**, not an automatic explanation for every kind of hang. Draw an edge only when there is evidence that a thread is genuinely **waiting to acquire lock ownership held by another thread**.

## 2. Components to Observe in a Thread Dump

A HotSpot thread dump on JDK 17 typically contains each thread’s header, stack trace, monitor annotations, and under appropriate options, ownable synchronizer details. *Structural illustration example*:

```text
"worker-A" #17 prio=5 tid=0x... nid=0x... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at demo.Service.step(Service.java:42)
        - waiting to lock <0x00000007abc01000> (a java.lang.Object)
        - locked <0x00000007abc02000> (a java.lang.Object)
```

The numbers `#17`, `tid`, `nid`, object addresses, and line numbers here **are examples only**, not fixed output. In Java/HotSpot, field formatting can vary by JDK/OS.

| Indicator | Practical Meaning | What Not to Infer |
| --- | --- | --- |
| `"worker-A"` | Thread name, helpful for human reading | Thread names are not necessarily unique |
| `#17` | Typically the Java thread ID in HotSpot headers | Not the JVM PID |
| `nid=0x...` | OS native thread ID in hex according to HotSpot | Not the decimal Java thread ID |
| `tid=0x...` | HotSpot internal thread pointer/identifier | Not the same kind of ID as `nid` |
| `BLOCKED (on object monitor)` | Thread is waiting to enter or reenter a Java monitor | Does not indicate wait duration without other metrics |
| `- waiting to lock <L>` | Thread is attempting to acquire monitor with identity `L` | Does not say which thread holds it from this line alone |
| `- locked <M>` | Thread already holds monitor `M` at the corresponding frame | Does not mean it is waiting on `M` |
| `Locked ownable synchronizers` | Ownable synchronizers held by the thread when dumped | Does not equate to all synchronization primitives or external resources |
| `Found one Java-level deadlock` | JVM diagnostic detected a lock cycle within its supported scope | Absence of this line does not prove all hangs are harmless |

**Lock identities in a dump must be compared within the same JVM and the same snapshot.** `<0x...>` is a reference/identity representation in the dump, not a source-code variable name like `LEFT`/`RIGHT`, and not a stable address across GCs or restarts.

### 2.1. Three Easily Confused Lines

- `waiting to lock <L>`: waiting to **acquire monitor ownership**; this is normally a candidate for a graph edge if an owner can be identified.
- `waiting on <L>`: in `Object.wait()`, the thread has **released the monitor of the waited object itself** while awaiting notification; it does not automatically create an edge “waiting on the thread holding L.”
- `parking to wait for <L>`: waiting via `LockSupport.park`/AQS; may be a `ReentrantLock`, condition, queue, or scheduler. Only connect a corresponding lock edge when there is evidence of an **ownable synchronizer and owner**.

Stack frames like `Object.wait`, `LockSupport.park`, `ConditionObject.await`, or `Thread.sleep` describe the **wait mechanism**, and do not automatically mean another thread is holding a lock.

## 3. Wait-For Graph Model: Defining Nodes and Edges

Use a **wait-for graph** directed from the **waiting thread** to the **lock-holding thread**:

```text
Thread A --waits for lock held by B--> Thread B
Thread B --waits for lock held by C--> Thread C
Thread C --waits for lock held by A--> Thread A
```

Compact notation: `A → B`, `B → C`, `C → A`. The directed cycle is `A → B → C → A`.

**Do not reverse edge directions.** `A → B` reads “A **is waiting for** B to release a lock”; **not** “A holds a lock that B needs.”

To construct an edge you need at minimum:

1. Thread `T` is waiting to **acquire** lock `L` at snapshot time;
2. Lock `L` is confirmed to be held by thread `H` or linked to `H` by JVM owner metadata;
3. `T` and `H` are two threads in the **same JVM session**, and the identity of `L` is matched accurately.

Then add edge `T → H`, optionally labeled with the lock:

```text
T --[waiting for Lock L]--> H
```

If the dump shows `T` waiting but **no owner is visible**, record `OWNER_UNKNOWN`; do not invent an owner from class names, similar stack frames, or guesswork.

### 3.1. Two Useful Graph Views

**Bipartite thread–lock graph** keeps both resources and threads:

```text
T_A --waits-for--> L_B --owned-by--> T_B
T_B --waits-for--> L_A --owned-by--> T_A
```

**Thread wait-for graph** collapses each `L_B → T_B` pair into one edge:

```text
T_A --waits for L_B--> T_B
T_B --waits for L_A--> T_A
```

The first form makes it easy to **audit evidence** from individual `waiting to lock` and `locked` lines. The second form makes it easy to find cycles over the thread set. A runbook should record **lock ID, owner ID, and state** rather than copying an A/B diagram without traceable data.

## 4. A Two-Thread, Two-Monitor Example

Suppose two Java monitors `L1` and `L2`:

- `worker-A` holds `L1` and then needs `L2`.
- `worker-B` holds `L2` and then needs `L1`.

A thread dump snapshot may contain two sections like this (**shortened addresses, illustrative only**):

```text
"worker-A" #17 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at demo.Service.step(...)
        - waiting to lock <0xB200> (a java.lang.Object)
        - locked <0xA100> (a java.lang.Object)

"worker-B" #18 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at demo.Service.otherStep(...)
        - waiting to lock <0xA100> (a java.lang.Object)
        - locked <0xB200> (a java.lang.Object)
```

Tracing:

| Waiting Thread | Wants Lock | Owner Proven By | Edge |
| --- | --- | --- | --- |
| `worker-A` | `0xB200` | `worker-B` has `- locked <0xB200>` | `worker-A → worker-B` |
| `worker-B` | `0xA100` | `worker-A` has `- locked <0xA100>` | `worker-B → worker-A` |

Graph:

```text
         waits for L2
worker-A ---------> worker-B
worker-A <--------- worker-B
         waits for L1

=> cycle: worker-A → worker-B → worker-A
```

**Key step:** match `0xB200` on A’s waiting line with `0xB200` on B’s locked line; likewise for `0xA100`. Do not conclude a wait cycle merely because both are `BLOCKED` or running the same method.

If HotSpot can detect a deadlock in the dump, it usually appends a `Found one Java-level deadlock` section specifying which monitor each thread is waiting for and who holds that monitor. That section is an independent verification source for your manually constructed graph, though do not limit investigations solely to grepping for that phrase.

## 5. Step-by-Step Thread Dump Reading Process

### Step 1 — Capture from the Right JVM at the Right Time

On the right host and within the appropriate permissions/PID namespace context:

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> help Thread.print
jcmd <PID> Thread.print -l > thread-dump.txt
```

`<PID>` is a placeholder to replace with the **actual** PID, without angle brackets when running. `jcmd` on JDK 17 must run on the same host as the JVM with matching effective user/group permissions to attach. Containers may use separate PID namespaces; do not arbitrarily swap host/container PIDs.

`-l` on `Thread.print` requests additional `java.util.concurrent` lock info when supported by the runtime. This is a diagnostic operation whose **impact** depends on thread count, so do not invoke it in a tight loop in production. Read `help Thread.print` for exact syntax and impact on the target JVM.

**Record:** UTC timestamp of the dump, host/pod, PID, **process start time**, JDK version, and incident context. PIDs can be reused after restarts; thread names can also be reused.

### Step 2 — Select Candidate Threads

Look for threads that are:

- `BLOCKED (on object monitor)` with `- waiting to lock <...>`;
- `WAITING (parking)` or `TIMED_WAITING (parking)` in AQS/`ReentrantLock` frames, where the owner still needs verification;
- threads **holding** a lock that many other threads are waiting on;
- threads belonging to a request/worker pool that has stopped making progress per metrics/traces.

Do not ignore a `RUNNABLE` thread if it is the **owner of a monitor** awaited by many threads: the owner might be stuck on I/O or running too long inside a critical section. A `WAITING` thread may also hold another monitor; always read its `- locked` lines before concluding.

### Step 3 — Record Each Thread’s Awaited Lock and Held Locks

Build an extraction table without jumping to matches:

| Thread identity | Thread state | Waiting for lock | Held locks | Stack top |
| --- | --- | --- | --- | --- |
| `worker-A/#17` | `BLOCKED` | `0xB200` | `0xA100` | `Service.step` |
| `worker-B/#18` | `BLOCKED` | `0xA100` | `0xB200` | `Service.otherStep` |

This is an **illustrative** table. Owner info, if present in the deadlock summary or via `ThreadInfo.getLockOwnerId()`, is used for cross-checking. When thread names collide, prefer Java thread ID, native ID, and JVM instance rather than joining by name.

### Step 4 — Connect Waiters to Owners

Build an index `lock identity → owning thread`, then for each `waiting to lock <L>` line find the thread with `locked <L>` in the **same dump**. For ownable synchronizers, check the held synchronizers list and `lockOwnerId` info if available.

No owner found → mark an **unknown** edge rather than assigning an arbitrary thread. If two dumps from different times show conflicting data, never mix lock IDs/owners across two snapshots to “complete” a false cycle.

### Step 5 — Trace the Chain and Find Cycles

Start from a hung thread of interest:

```text
T0 → owner(T0) → owner(owner(T0)) → ...
```

Stop when:

- reaching a thread not waiting on any lock held by another thread → **chain ends**, no cycle;
- reaching a lock with unknown owner → **insufficient evidence**;
- encountering a thread **already visited in the current path** → there is a **cycle**;
- noticing data comes from different JVM sessions/timestamps → stop connecting.

To verify on a HotSpot JVM, cross-check the deadlock summary section or `ThreadMXBean.findDeadlockedThreads()` (if the lock types are supported). Document the evidence for every edge.

### Step 6 — Repeat in a Controlled Manner

If no cycle is seen while symptoms persist, take 2–3 dumps spaced appropriately for the incident, e.g., a few seconds apart, and compare thread IDs and stack positions. A thread holding a monitor for a long time can be **lock contention/convoy**, not a cycle. If a genuine Java monitor cycle exists, the involved threads will not advance on their own unless the application has an appropriate recovery/intervention mechanism.

**Do not read a single snapshot as a timeline**: repetition only checks persistence, and does not directly give when waiting started or total blocked duration.

## 6. Cycle-Detection Algorithm in a Wait-For Graph

When each thread has at most one blocking lock acquisition at a time, the waiter → owner graph has **at most one outgoing edge** per thread. We can follow successors while tracking nodes visited in the **current path**:

```text
for each starting thread S:
    path = []
    indexInPath = {}

    T = S
    while T exists:
        if T already in indexInPath:
            report cycle = path[indexInPath[T] .. end] -> T
            break

        if T was already fully analyzed:
            break

        indexInPath[T] = length(path)
        append T to path
        T = ownerThreadOfLockWaitedBy(T)

    mark path nodes analyzed
```

This is **pseudocode**, not Java syntax. When multiple outgoing edges exist in a broader dependency model (e.g., locks in a distributed system), use DFS to find back edges or strongly connected components (Tarjan/Kosaraju). For simple monitor relationships, following owners sequentially is sufficient.

Example **without a cycle**:

```text
T1 → T2 → T3
           |
           +-- T3 is not waiting on any owned lock
```

This may be long contention or T3 waiting on I/O. Do not conclude a Java-level deadlock just because T1/T2 make no progress for a few seconds.

Example of **one owner with multiple waiters**:

```text
T1 ──┐
T2 ──┼──> H
T3 ──┘
```

That is **fan-in / lock convoy**, not a cycle unless H waits back on a node in the path. Distinguishing this prevents applying deadlock fixes to an overly long critical section.

## 7. `synchronized` Monitors and Ownable Synchronizers

### 7.1. Intrinsic Java Monitors

A block:

```java
synchronized (lockA) {
    synchronized (lockB) {
        // critical section
    }
}
```

is merely an illustrative snippet. If another thread holds `lockB`, the current thread becomes `BLOCKED` when attempting to enter the monitor. The thread dump normally shows `- waiting to lock <lockB>`, while the owning thread shows `- locked <lockB>`.

A classic deadlock occurs when A acquires `lockA → lockB` and B acquires `lockB → lockA`. Avoid it using **global lock ordering** consistently across all code paths.

`synchronized` acquisition is not interruptible in the way `ReentrantLock.lockInterruptibly()` supports; simply calling `Thread.interrupt()` does not guarantee releasing a monitor deadlock.

### 7.2. ReentrantLock and AbstractOwnableSynchronizer

`java.util.concurrent.locks.ReentrantLock` uses AQS/ownable synchronizers. A thread dump with `jcmd Thread.print -l` may contain:

```text
"worker-C" ... WAITING (parking)
   at jdk.internal.misc.Unsafe.park(Native Method)
   at java.util.concurrent.locks.LockSupport.park(...)
   at java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
   at java.util.concurrent.locks.ReentrantLock.lock(...)

   Locked ownable synchronizers:
     - <0x00000007abc03000> (a ...ReentrantLock$NonfairSync)
```

The excerpt above **only illustrates structure** and does not claim thread C is both waiting on and holding the same synchronizer. In a real thread dump, `Locked ownable synchronizers` lists the **synchronizers currently held by the thread**, while the stack/parking block shows where the thread is waiting. You must match **actual object identities and owners**.

With `ThreadMXBean`, `findDeadlockedThreads()` can detect cycles involving both monitors and ownable synchronizers if supported by the JVM; `findMonitorDeadlockedThreads()` detects only monitor deadlocks. Before requesting ownable synchronizers via `getThreadInfo(ids, true, true)`, check `isObjectMonitorUsageSupported()` and `isSynchronizerUsageSupported()` to avoid `UnsupportedOperationException` on unsupported runtimes.

### 7.3. Wait Types Without Clear Owner Edges

- `Object.wait()` **releases the monitor of the waited object** while awaiting notification. A `waiting on` line does not mean another thread owns that lock.
- `Condition.await()` tied to a `Lock` **releases the lock during await**, then reacquires it before returning. A condition-waiting thread is not automatically a waiter in the current lock-acquisition graph.
- `LockSupport.park()` often only indicates parking; not every park has an ownable synchronizer owner.
- `Semaphore`, `CountDownLatch`, `BlockingQueue`, `Future.get`, network/DB/file I/O, and distributed locks can create dependencies outside the owner-of-monitor model. Some cases require event logs, tracing, or external resources to construct a broader wait graph.
- `ReentrantReadWriteLock`, `StampedLock`, custom locks, and native mutexes have distinct semantics; do not assign a single owner unless the implementation provides evidence.
- Deadlocks across **multiple resources** such as database row locks between services are not necessarily reported by JVM thread dumps or `ThreadMXBean`.

**Absence of “Found one Java-level deadlock” ≠ absence of deadlock in the whole system.** It only states that the tool detected no cycle of a recognizable type at that moment.

## 8. Java 17+ Demo: Deterministic Deadlock Creation and Wait-Graph Printing

The following demo creates **two object monitors**, lets two threads each hold their first monitor, and then simultaneously try for the other monitor. `CountDownLatch` ensures both genuinely hold the first lock before the second wait edge forms. The program uses `ThreadMXBean.findMonitorDeadlockedThreads()` to detect the exact monitor deadlock just created.

**Run only in a test environment.** The program intentionally creates a deadlock; do not embed this pattern in a real service. Both workers are **daemon threads** so the demo JVM can exit after the sample hold period without leaving an endlessly hung Java process.

### 8.1. Complete `LockWaitGraphDemo.java` File

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;

public class LockWaitGraphDemo {
    private static final Object LEFT = new Object();
    private static final Object RIGHT = new Object();

    static void lockInOrder(Object first, Object second, CountDownLatch ready) {
        synchronized (first) {
            ready.countDown();
            try {
                ready.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            synchronized (second) {
                System.out.println("unreachable");
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        long holdMillis = args.length == 0 ? 60_000L : Long.parseLong(args[0]);
        CountDownLatch bothHoldingFirst = new CountDownLatch(2);

        Thread a = new Thread(() ->
            lockInOrder(LEFT, RIGHT, bothHoldingFirst), "worker-A");
        Thread b = new Thread(() ->
            lockInOrder(RIGHT, LEFT, bothHoldingFirst), "worker-B");
        a.setDaemon(true);
        b.setDaemon(true);
        a.start();
        b.start();

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        long[] ids = null;
        for (int i = 0; i < 100; i++) {
            ids = mx.findMonitorDeadlockedThreads();
            if (ids != null && ids.length >= 2) break;
            Thread.sleep(25);
        }
        if (ids == null || ids.length < 2) {
            throw new IllegalStateException("monitor deadlock not detected");
        }

        ThreadInfo[] infos = mx.getThreadInfo(ids, 16);
        Arrays.stream(infos)
            .filter(Objects::nonNull)
            .sorted(Comparator.comparing(ThreadInfo::getThreadName))
            .forEach(info -> System.out.println(
                info.getThreadName() + " -> " + info.getLockOwnerName()));
        System.out.println("cycleDetected=true");
        System.out.flush();
        Thread.sleep(holdMillis);
    }
}
```

**Mechanism explanation:**

1. `worker-A` acquires `LEFT`, `worker-B` acquires `RIGHT`.
2. Each thread calls `ready.countDown()` while **holding its first monitor**, then awaits the latch reaching 0. Waiting on the latch **does not release** the `LEFT`/`RIGHT` monitor acquired via `synchronized`.
3. Once both enter, the latch opens; A tries to acquire `RIGHT` held by B, while B tries to acquire `LEFT` held by A. Both become `BLOCKED` at `synchronized(second)`.
4. `findMonitorDeadlockedThreads()` detects the threads forming a **monitor acquisition** cycle and returns their IDs; `getThreadInfo(ids, 16)` fetches each thread’s name and lock owner.
5. `Comparator` sorts by name so stdout of the two workers has a deterministic order.
6. The main thread sleeps so learners can take an external dump; daemon workers will not keep the JVM alive once main finishes.

### 8.2. Compile and Run

```bash
javac --release 17 LockWaitGraphDemo.java
java LockWaitGraphDemo
```

**Exact stdout verified on the test JDK:**

```text
worker-A -> worker-B
worker-B -> worker-A
cycleDetected=true
```

The first two lines represent the `waiter → owner` graph, not the startup order of the threads. The last line confirms the JVM detected the monitor cycle. The program has a default hold duration of **60 seconds** after printing so you can capture a thread dump. Meanwhile the main thread is sleeping and is not part of the cycle.

To quickly check stdout without keeping the JVM alive for long, you can run:

```bash
java LockWaitGraphDemo 0
```

In this example `0` is the `holdMillis` argument to the **demo program**, not a PID for `jcmd`. Using `jcmd 0 Thread.print` has a different meaning and can send the command to multiple JVMs, so **do not do that**.

### 8.3. From a Second Terminal: Capture the Demo Thread Dump

While the program is still sleeping:

```bash
jcmd -l
jcmd <PID> help Thread.print
jcmd <PID> Thread.print -l > deadlock-demo.txt
```

Replace `<PID>` with the PID of `LockWaitGraphDemo` reported by `jcmd -l`; do not use an example PID from documentation. Observe:

- Two threads `worker-A` and `worker-B` with state `BLOCKED (on object monitor)`.
- A `- waiting to lock <...>` line in each thread and a `- locked <...>` line in the other thread.
- In a HotSpot build supporting detection, a `Found one Java-level deadlock` section stating which thread waits on which monitor held by which thread.

**Volatile data:** PID, Java thread IDs, `nid`, `tid`, object IDs, source line numbers, and the rest of the dump vary across runs. Do not treat them as “canonical stdout”; the three-line output from the program is the fixed result in the verified run.

### 8.4. Technical QA of the Example

The code **compiled with `javac --release 17`**, ran, and printed the exact three lines above. Against a live test JVM, `jcmd <PID> Thread.print -l` succeeded and the dump contained both worker names along with the **deadlock summary**. Temporary processes/files used for verification were cleaned up after testing.

This demonstrates **both verification paths**: the `ThreadMXBean` API from inside the JVM and the `jcmd` tool from outside.

## 9. Using ThreadMXBean to Cross-Check Dump Results

`ThreadMXBean` in module `java.management` provides:

| API | Scope | Results and Limitations |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Wait cycles on **object monitors** | Thread IDs or `null`; excludes ownable synchronizers |
| `findDeadlockedThreads()` | Object monitors **and ownable synchronizers** | Thread IDs or `null`; may throw `UnsupportedOperationException` if JVM does not support tracking ownable synchronizers |
| `getThreadInfo(ids, 16)` | Stack/lock owner for IDs | `ThreadInfo[]`, terminated threads may be `null` |
| `getThreadInfo(ids, true, true)` | Adds held monitors and ownable synchronizers | Requires capability checks; can be expensive |
| `isObjectMonitorUsageSupported()` | Can locked monitors be collected? | Use before requesting `lockedMonitors=true` |
| `isSynchronizerUsageSupported()` | Can locked ownable synchronizers be collected? | Use before requesting `lockedSynchronizers=true` |
| `ThreadInfo.getLockInfo()` | Lock object the thread is blocked/waiting on | May be `null` when not applicable |
| `ThreadInfo.getLockOwnerId()` | Java thread ID of owner (if known) | May be `-1` when unknown |
| `ThreadInfo.getLockOwnerName()` | Name of owner thread | May be `null` |
| `ThreadInfo.getLockedMonitors()` | Monitors currently held by the thread | Only present when the `ThreadInfo` retrieval requested/supported that info |
| `ThreadInfo.getLockedSynchronizers()` | Ownable synchronizers currently held by the thread | Only present when requested/supported |

The lines:

```java
ThreadInfo info = mx.getThreadInfo(threadId, 16);
long ownerId = info == null ? -1 : info.getLockOwnerId();
```

are an **illustrative snippet**, requiring a real `ThreadMXBean mx` and `threadId` variable. It helps create the edge `threadId → ownerId` when `ownerId > 0` and lock type/state match; however, `ownerId == -1` **does not prove** the thread is making progress or that no deadlock exists outside the monitored scope.

**Do not run `findDeadlockedThreads()` continuously on hot paths.** The JavaDoc notes it is a troubleshooting operation and can be expensive; distinguish incident-time diagnostics from lightweight per-request metrics. When a JVM is unresponsive to attach or MXBean queries, use logs/OS/JFR and the corresponding incident procedure; missing output does not mean no deadlock exists.

## 10. Cases That Are Not Deadlock Cycles

### 10.1. Idle Thread Pool

A `pool-worker` that is `WAITING` inside `BlockingQueue.take()` or `LockSupport.park()` may simply be waiting for tasks. There is no evidence it is waiting on a lock held by another worker. **Do not draw an edge** merely because you see `WAITING`.

### 10.2. Lock Convoy / Long-Running Owner

`T1`, `T2`, and `T3` are all `BLOCKED` waiting for monitor `L` held by `H`. If `H` is running or waiting on external I/O **without waiting for any lock in the graph**, we have:

```text
T1 ──┐
T2 ──┼──> H
T3 ──┘
```

That is contention/fan-in, not a cycle. Inspect `H`’s stack, critical section length, I/O inside the lock, pauses/GC, and actual load. Starvation or high latency can occur even without a deadlock.

### 10.3. Object.wait or Condition.await

A consumer waiting for notification or a condition normally **releases the monitor/lock tied to the wait operation** before sleeping, so it does not automatically create a waiter → owner edge for that lock. However, the thread may still hold **other locks**; to conclude safely, read all held locks and related resources.

### 10.4. Threads Waiting on I/O, DB, or External Locks

A request can hang due to a socket read, database row lock, RPC, or downstream queue. The JVM dump shows a “waiting” stack, but does not provide a Java thread owner for an out-of-process resource. Do not fabricate a Java monitor cycle without evidence; combine database lock graphs, network metrics, distributed traces, or the remote side’s thread dumps when permitted.

### 10.5. Starvation and Livelock

Starvation occurs when a thread cannot run or acquire a resource for a long time; livelock is when threads keep changing state without making business progress. A static wait-for graph may have **no cycle** in both of these situations. Observe multiple samples and business progress instead of searching only for `Found one Java-level deadlock`.

## 11. Checking Multiple Dumps to Avoid False Conclusions

An investigation typically takes **2–3 thread dumps** at separate points suited to the symptoms, e.g., a few seconds apart. Label them:

```text
host: node-03
pid: 18432
process_start_utc: 2026-10-29T08:00:00Z
snapshot_utc: 2026-10-29T08:15:02Z
command: jcmd 18432 Thread.print -l
incident: elevated request latency
```

This is **illustrative** metadata, not tool output. Each snapshot must be analyzed **internally** before linking across snapshots:

- Are the thread IDs and JVM start time consistent? Are thread names duplicated/recycled?
- Is the same thread waiting on the **same lock** in each snapshot, or changing continually?
- Who is the current owner, and does the stack change?
- Is there a **cycle proven within a single snapshot**, or merely a wait chain stitched together from different timestamps?
- Does the JVM-provided deadlock summary appear and match the manually built graph?

**Avoid combining “A waits on B in dump 1” with “B waits on A in dump 2” and claiming a simultaneous cycle.** Two edges at two different times are not enough to prove a deadlock. If the JVM may relocate objects or change address representations, do not rely solely on `<0x...>` to correlate identity across dumps.

## 12. When a Cycle Is Found: Locating the Fix in Code

The wait-for graph answers **who waits on whom**; to fix it, you must find **why the code acquires locks in conflicting orders**.

Process:

1. For each edge `A → B`, locate A’s frame right at `waiting to lock` and where B holds the lock with the same identity (`locked`/`getLockedMonitors` lines).
2. Map the acquisition order from code: e.g., `processOrder()` acquires `accountLock → inventoryLock` while `reserveInventory()` acquires `inventoryLock → accountLock`.
3. Inspect call paths going through callbacks, listeners, or synchronous RPCs executing **inside** a critical section.
4. Propose a **consistent global lock order**: always acquire `accountLock` before `inventoryLock` on every path.
5. When using `ReentrantLock`, consider `tryLock(timeout)`/`lockInterruptibly()` if appropriate, remember to `unlock()` in `finally`, and handle rollback when acquisition fails.
6. Shrink critical sections, avoid long I/O or uncontrolled calls while holding locks, and replace shared mutable state with an actor/queue model or immutable data where sensible.
7. Write a regression test reproducing both threads and verify that after the fix **no cycle remains** and both complete real work.

**Do not treat `Thread.stop()`, `Thread.suspend()`, or arbitrarily killing workers as a safe solution.** These operations can break invariants or corrupt state; if production is genuinely deadlocked and needs recovery, follow a controlled incident/restart procedure and preserve evidence first.

### 12.1. Consistent Lock Acquisition Order

Symmetric fix example:

```java
// Both code paths use the exact same order.
synchronized (accountLock) {
    synchronized (inventoryLock) {
        updateState();
    }
}
```

This is an **illustrative snippet**; `accountLock`, `inventoryLock`, and `updateState()` must exist in a real class. Not every problem needs two locks held simultaneously; sometimes a single lock around small state or switching to message passing suffices.

With dynamically created locks (e.g., per-account-ID locks), use a consistent order sorted by ID and handle equal-key cases. If external callbacks are invoked, verify beforehand whether a callback can reacquire locks in the opposite direction.

## 13. Common Reasoning Mistakes

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| “Two threads are `BLOCKED`, so it’s a deadlock.” | Waiting together on one owner can just be contention. | Trace owners and look for a directed cycle. |
| “`WAITING` always means waiting on another thread’s monitor.” | Could be a queue, `Object.wait`, condition, sleep/park. | Classify the wait mechanism before drawing an edge. |
| “`- waiting on` = `- waiting to lock`.” | `Object.wait` releases the monitor while awaiting notification. | Only connect a monitor-acquisition edge with evidence. |
| “Thread names are enough.” | Names can collide; threads can terminate/be recreated. | Use Java thread ID, native ID, and JVM instance. |
| “`nid` is the Java thread ID.” | `nid` is the native ID in HotSpot. | Do not mix it with `ThreadMXBean` IDs. |
| “Object ID 0x... persists across all dumps.” | Address/identity representations can change. | Match within the same snapshot, with lifecycle context. |
| “Seeing `locked <L>` means the thread is waiting on L.” | `locked` describes **holding**. | Edge direction is waiter → owner. |
| “A waiter can be matched to an owner by lock class.” | Many objects of the same class have different identities. | Match the **exact lock identity**. |
| “`LockSupport.park` means a ReentrantLock deadlock.” | Parking has many causes and does not always have an owner. | Read ownable synchronizers and owner IDs. |
| “No deadlock summary means no hang.” | JVM does not see DB/I/O/external deadlocks or unknown owners. | Use logs/metrics/traces and external tools. |
| “Merge two snapshots into one graph.” | Edges might not exist simultaneously. | Build a separate graph per timestamp. |
| “Use `jcmd 0` to diagnose one JVM.” | PID 0 can target multiple JVMs. | Select the exact PID and process start time. |
| “One dump proves a thread waited 10 minutes.” | A dump does not record continuous wait duration. | Use historical monitoring and multiple snapshots. |
| “Spot a cycle and kill the thread to unlock.” | There is no general safe way to release locks externally. | Fix ordering and recover in a controlled manner. |

## 14. Production Incident Handling Procedure

### A. Before Capturing

- Choose the **exact host/pod/PID namespace**, PID, process start time, and JVM owner. Do not rely on main class/JAR when multiple identical replicas exist.
- Verify the appropriate JDK/JVM, attach permissions, and security requirements. `jcmd` must run on the right machine per JDK 17 documentation.
- Record symptom onset time, affected systems, throughput/latency/CPU/GC; avoid overly frequent snapshots on a heavily loaded JVM.
- Determine whether output contains stack/class names, paths, or sensitive data; store it with proper permissions.

### B. Collecting Evidence

```bash
jcmd <PID> Thread.print -l > dump-1.txt
# After an appropriate interval:
jcmd <PID> Thread.print -l > dump-2.txt
```

This is a shell example; `<PID>` must be replaced. The `>` redirect creates files in the **client shell** environment. Run only against authorized JVMs; if high-impact warnings occur or the JVM does not respond, prioritize the incident procedure.

### C. Building and Verifying the Graph

- Parse each thread block within **a single dump**.
- Record thread ID/name/state, awaited lock, held monitors, and locked ownable synchronizers.
- Connect waiter → owner using **lock identity or explicit owner metadata**.
- Branch to `OWNER_UNKNOWN` when evidence is missing.
- Find cycles, verifying against `Found ... Java-level deadlock` and/or `ThreadMXBean` if supported.
- If no cycle exists, examine fan-in, owner stack, OS I/O, GC/logs, and out-of-JVM components.

### D. Remediation and Verification

- When a cycle exists, locate the source code causing conflicting acquisition orders or callbacks under locks.
- Choose a fix for global ordering / critical sections / lifecycle accompanied by race tests, rather than merely tweaking sleep durations.
- If a production restart is required for recovery, preserve evidence and follow change/incident policy.
- After the fix, run multithreaded regression tests, replay load, and compare thread dumps and metrics to confirm progress.

## 15. Result Verification Checklist

- [ ] Verified the **exact JVM instance, PID, start time, and namespace**?
- [ ] Captured dump with `-l` and understood the impact of `Thread.print`?
- [ ] Properly distinguished thread ID, name, `nid`, and `tid`?
- [ ] Every `waiter → owner` edge backed by **lock identity/owner evidence**?
- [ ] Distinguished `waiting to lock` from `waiting on`/`parking to wait for`?
- [ ] Searched for cycles **within a single snapshot**, without stitching edges across timestamps?
- [ ] Does `found deadlock` match the graph? If absent, considered lock-type and data limitations?
- [ ] If only fan-in is present, inspected the **owner stack/critical section**?
- [ ] If AQS/ReentrantLock is involved, checked `Locked ownable synchronizers` and corresponding capabilities?
- [ ] Separated Java monitor deadlocks from DB/I/O/distributed lock waits?
- [ ] Saved timestamp, JVM session, command, format, and redaction for the evidence?
- [ ] Implemented a code change resolving lock ordering and a confirming regression test?

## 16. Java SE 17 References

- [Oracle — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print`, `-l`, PID selection, help, and impact.
- [Oracle — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): `findMonitorDeadlockedThreads`, `findDeadlockedThreads`, `getThreadInfo`, locked monitors, and ownable synchronizers.
- [Oracle — ThreadInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): `getLockInfo`, `getLockOwnerId`, `getLockedMonitors`, `getLockedSynchronizers`, and thread state.
- [Oracle — LockInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/LockInfo.html): representation of awaited/held lock information.
- [Oracle — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): semantics of `BLOCKED`, `WAITING`, and `TIMED_WAITING`.
- [Oracle — Object.wait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait()): monitor release during wait.
- [Oracle — Lock / Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): semantics of `await` and lock release/reacquire.

**Technical conclusion:** From a thread dump, accurately identify **which lock is awaited → which thread holds that lock → who the owner is waiting on**. Draw directed waiter → owner edges using the exact lock identity, and trace until stopping or repeating. A **same-timestamp cycle** signals a monitor/ownable-synchronizer deadlock within diagnostic scope; **no cycle** can still be contention, starvation, or an external wait. Tracing the lock ownership chain leads you from the “hung thread” symptom straight to the acquisition order that needs fixing in code.