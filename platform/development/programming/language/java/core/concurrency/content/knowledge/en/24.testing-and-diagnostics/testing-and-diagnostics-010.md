# Deadlock Analysis with ThreadMXBean in Java

## 1. Objectives

A **deadlock** is a situation in which a group of threads becomes stuck because each thread is waiting for a resource held by another thread in the group, forming a **wait cycle** that cannot resolve itself by waiting longer. In Java, a deadlock bug usually does not throw an exception immediately: the program may keep running, yet some requests or tasks never complete.

Java provides **ThreadMXBean** in the standard **java.management** module, which can inspect threads, capture stack traces, and detect certain types of deadlocks directly inside the JVM. This lesson focuses on:

1. Understanding lock wait cycles and distinguishing deadlocks from other slow-thread conditions.
2. Using **ManagementFactory.getThreadMXBean()**, **findMonitorDeadlockedThreads()**, **findDeadlockedThreads()**, and **getThreadInfo(...)**.
3. Reading **ThreadInfo** to identify **which thread holds a lock**, **which thread is waiting for a lock**, and **which code paths are involved**.
4. Practicing controlled deadlock creation in Java 17+, diagnosing it, and fixing it with a lock-ordering rule.
5. Recognizing detection limitations, operational overhead, and appropriate response steps when a real incident occurs.

The scope is **Java/JDK** concurrency, without framework dependencies.

## 2. How Does a Deadlock Form?

Consider two Java monitors, **lockA** and **lockB**:

~~~text
Thread T1                            Thread T2
-----------                          -----------
synchronized(lockA)                  synchronized(lockB)
  holding lockA                        holding lockB
  wants lockB                          wants lockA
  => BLOCKED                           => BLOCKED

        T1 --waits for lockB--> T2
        T2 --waits for lockA--> T1
~~~

**T1** cannot acquire **lockB** because **T2** holds it; **T2** cannot acquire **lockA** because **T1** holds it. Each thread must exit its synchronized block to release its lock, yet neither can proceed. That is a wait cycle.

The four classic conditions that must hold simultaneously for a deadlock to occur:

- **Mutual exclusion:** a resource can be held by only one owner at a time.
- **Hold and wait:** a thread holds one resource while waiting for another resource.
- **No preemption:** a resource cannot be forcibly and safely taken away from its owner.
- **Circular wait:** a cycle of waiting exists among resource owners.

Breaking just one appropriate condition by design is enough to prevent that class of deadlock. A common approach when dealing with multiple locks is to **enforce a consistent lock acquisition order**.

### 2.1. Deadlock Is Not Synonymous with Every WAITING/BLOCKED State

| Phenomenon | Common Symptom | Is It Automatically a Deadlock? |
|---|---|---|
| **BLOCKED** | Thread is waiting to enter a **synchronized** monitor held by another thread. | No; it may just be short-term contention. |
| **WAITING** | Thread is waiting indefinitely in **Object.wait()**, **Thread.join()**, **LockSupport.park()**, or another mechanism. | No; it may be waiting normally for a condition. |
| **TIMED_WAITING** | Thread is waiting with a time limit, such as **sleep()**, timed wait, or timed park. | No; there is usually a timeout path. |
| **Starvation** | A thread is repeatedly denied the resources or CPU time it needs to proceed. | Not necessarily a lock ownership cycle. |
| **Livelock** | Threads keep running/changing state without making forward progress. | Not necessarily stuck on a lock. |
| **Deadlock** | A wait cycle exists in which none of the threads in the cycle can advance. | Yes, within the scope of the diagnosed lock types. |

Therefore, **do not conclude deadlock from a thread dump merely having many BLOCKED lines**. You must construct the **thread → awaited lock → owning thread** relationship and identify a cycle.

## 3. What Is ThreadMXBean?

**ThreadMXBean** is the JVM's thread management interface in **java.lang.management**. A JVM provides one MXBean representing its thread management information.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

// Illustrative snippet, placed inside a method:
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
~~~

This is a **JDK API** and requires no external libraries. It is meant for monitoring and diagnostics, not as a primitive to automatically release locks. **ThreadMXBean** tells you what threads are doing; once the cause is identified, **the developer must fix the lock ordering or synchronization design**.

### 3.1. Key APIs

| API | Purpose | Notes |
|---|---|---|
| **findMonitorDeadlockedThreads()** | Finds threads in a wait cycle over Java **object monitors** (**synchronized**). | Does not include cycles involving only ownable synchronizers. |
| **findDeadlockedThreads()** | Finds wait cycles over **object monitors or ownable synchronizers**. | May throw **UnsupportedOperationException** if the JVM does not support ownable synchronizer monitoring. |
| **isSynchronizerUsageSupported()** | Checks whether the JVM supports tracking **ownable synchronizers**. | Check before requesting the corresponding details. |
| **isObjectMonitorUsageSupported()** | Checks support for retrieving monitors currently held by threads. | Useful when calling the **getThreadInfo** overload that requests locked monitors. |
| **getThreadInfo(ids, maxDepth)** | Retrieves **ThreadInfo** and stack traces up to the specified depth. | Does not populate the full list of all monitors/synchronizers held by a thread. |
| **getThreadInfo(ids, lockedMonitors, lockedSynchronizers)** | Retrieves detailed information including stack traces and, if requested/supported, lists of held locks. | Set flags according to JVM capabilities. |
| **dumpAllThreads(...)** | Collects information on all JVM threads supported by the API, including non-deadlocked threads. | Reads more data and can be more expensive. |

Both **find...DeadlockedThreads()** methods return a **long[]** array containing the IDs of threads participating in a deadlock, or **null** if none are found. **Returning null does not prove the application is free of concurrency issues**, because the API only detects cycles of supported lock types at the moment the snapshot is taken.

An **object monitor** is a lock associated with a **synchronized** block or method. An **ownable synchronizer** is a synchronizer with exclusive single-thread ownership semantics, such as locks built on **AbstractOwnableSynchronizer** and **ReentrantLock**. Not every wait mechanism in an application falls into these two categories.

### 3.2. Choosing the Right Detection Method

~~~java
// Illustrative snippet placed inside a method:
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

long[] deadlockedIds;
if (bean.isSynchronizerUsageSupported()) {
    deadlockedIds = bean.findDeadlockedThreads();
} else {
    deadlockedIds = bean.findMonitorDeadlockedThreads();
}

if (deadlockedIds == null) {
    System.out.println("No supported deadlock cycle detected");
}
~~~

If you also need to detect cases using **ReentrantLock**, prefer **findDeadlockedThreads()**. If the JVM does not support ownable synchronizer info, the fallback **findMonitorDeadlockedThreads()** has a **narrower scope** and must not be interpreted as covering all lock types.

In practice, deadlock detection APIs are for **troubleshooting**, not workflow control conditions called after every update operation. Do not use them as a substitute for proper synchronization, locks, timeouts, or deadlock-avoidance protocols.

## 4. Runnable Example: Creating a Deadlock and Detecting It with ThreadMXBean

This example deliberately creates a wait cycle between two **synchronized** monitors, then asks **ThreadMXBean** to find the cycle and retrieve lock-owner details. It uses a **CountDownLatch** to ensure both workers have acquired their first monitor before attempting to acquire the second.

**Practical warning:** This is a demo that **intentionally creates a deadlock**. Both workers are marked **daemon** so the JVM can exit after `main` prints the report; never copy this opposing lock-order pattern into request-handling code.

Create **DeadlockAnalysis.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.CountDownLatch;

public final class DeadlockAnalysis {
    private static Runnable takeBoth(Object first, Object second,
                                     CountDownLatch bothHoldingOne) {
        return () -> {
            synchronized (first) {
                bothHoldingOne.countDown();
                try {
                    bothHoldingOne.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                synchronized (second) {
                    System.out.println("unreachable");
                }
            }
        };
    }

    public static void main(String[] args) throws InterruptedException {
        Object left = new Object();
        Object right = new Object();
        CountDownLatch ready = new CountDownLatch(2);

        Thread a = new Thread(takeBoth(left, right, ready), "A-then-B");
        Thread b = new Thread(takeBoth(right, left, ready), "B-then-A");

        a.setDaemon(true);
        b.setDaemon(true);
        a.start();
        b.start();

        ThreadMXBean mxBean = ManagementFactory.getThreadMXBean();
        long[] ids = null;

        // Wait up to about 2 seconds for the deadlock to form.
        for (int attempt = 0; attempt < 100 && ids == null; attempt++) {
            ids = mxBean.findMonitorDeadlockedThreads();
            if (ids == null) Thread.sleep(20);
        }

        if (ids == null) {
            System.out.println("No deadlock observed within timeout");
            return;
        }

        ThreadInfo[] info = mxBean.getThreadInfo(ids, 16);
        Arrays.sort(info, Comparator.comparing(ThreadInfo::getThreadName));

        System.out.println("Deadlocked threads: " + info.length);
        for (ThreadInfo t : info) {
            System.out.println(t.getThreadName() + ": " + t.getThreadState()
                    + "; waits for " + t.getLockOwnerName());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 DeadlockAnalysis.java
java DeadlockAnalysis
~~~

When the JVM supports monitor tracking and detects the deadlock within the timeout, the expected output is:

~~~text
Deadlocked threads: 2
A-then-B: BLOCKED; waits for B-then-A
B-then-A: BLOCKED; waits for A-then-B
~~~

If the environment is heavily loaded, behaves differently, or does not detect it in time, the demo may print **No deadlock observed within timeout** instead of the report. This prevents **main** from waiting indefinitely and is not proof that no deadlock exists.

### 4.1. Step-by-Step Breakdown

1. **A-then-B** enters **synchronized(left)**. **B-then-A** enters **synchronized(right)**.
2. Each thread decrements the **ready** latch and calls **ready.await()** while still holding its first monitor. Once both arrive, the latch opens.
3. Thread A attempts to acquire **right**, which thread B holds; thread B attempts to acquire **left**, which thread A holds.
4. Both become **BLOCKED** at the **synchronized(second)** statement.
5. **findMonitorDeadlockedThreads()** finds the monitor wait cycle. **getThreadInfo(ids, 16)** retrieves state, name, and lock owner; sorting by name makes the output order predictable.
6. **setDaemon(true)** only lets the demo process terminate when `main` finishes. It **does not release the deadlock** or fix broken code. In a real application, deadlocked threads holding locks remain a serious incident.

The example uses **CountDownLatch** to make the deadlock reproducible; merely adding random **Thread.sleep(...)** calls to two workers makes reproduction flaky. In an automated test, a timeout is required to avoid hanging the entire test suite.

### 4.2. Visualizing the Cycle

~~~text
        holding LEFT                           holding RIGHT
      +-------------+                        +-------------+
      | A-then-B    | ---- wants RIGHT ----> | B-then-A    |
      | BLOCKED     | <---- wants LEFT ----- | BLOCKED     |
      +-------------+                        +-------------+

   A-then-B.getLockOwnerName() = "B-then-A"
   B-then-A.getLockOwnerName() = "A-then-B"
~~~

Thread names are just diagnostic labels; **thread IDs** are the identifiers used in MXBean data. In real systems, there may be dozens of threads, many monitors, and cycles longer than two nodes.

## 5. Reading ThreadInfo to Find the Root Cause

After detecting the IDs, do not stop at "two threads are deadlocked." You must identify **the code location waiting for the lock**, **the lock being awaited**, **who holds that lock**, and **the code location that previously acquired the held lock**.

Core methods of **java.lang.management.ThreadInfo**:

| Method | Meaning During Investigation |
|---|---|
| **getThreadId()**, **getThreadName()** | Identifies the thread in the snapshot. |
| **getThreadState()** | **BLOCKED** typically indicates waiting on an object monitor; with ownable synchronizers, you may see **WAITING** when parked. |
| **getLockInfo()**, **getLockName()** | The lock object the thread is waiting on. The name may include the class name and identity hash, **not** a business label. |
| **getLockOwnerId()**, **getLockOwnerName()** | The thread owning the awaited lock, if determinable; if there is no owner, these may be **-1/null**. |
| **getStackTrace()** | Method locations and stack frames at the time of capture. |
| **getLockedMonitors()** | Monitors currently held by the thread **when collection of this list was requested**. |
| **getLockedSynchronizers()** | Ownable synchronizers currently held **when collection of this list was requested**. |

### 5.1. Retrieving a Detailed Report for the Deadlocked Group

This is an **illustrative snippet placed inside a method**, where **bean** is a **ThreadMXBean** obtained from **ManagementFactory**, and **ids** is the array of detected IDs:

~~~java
boolean withMonitors = bean.isObjectMonitorUsageSupported();
boolean withSynchronizers = bean.isSynchronizerUsageSupported();
ThreadInfo[] details =
        bean.getThreadInfo(ids, withMonitors, withSynchronizers);

for (ThreadInfo t : details) {
    if (t == null) continue; // The thread may have terminated between the two reads.

    System.out.printf("Thread=%s id=%d state=%s%n",
            t.getThreadName(), t.getThreadId(), t.getThreadState());
    System.out.printf("Waiting for=%s owned by=%s (id=%d)%n",
            t.getLockInfo(), t.getLockOwnerName(), t.getLockOwnerId());

    for (StackTraceElement frame : t.getStackTrace()) {
        System.out.println("    at " + frame);
    }
    for (java.lang.management.MonitorInfo monitor : t.getLockedMonitors()) {
        System.out.println("    holds monitor " + monitor);
    }
    for (java.lang.management.LockInfo lock : t.getLockedSynchronizers()) {
        System.out.println("    holds synchronizer " + lock);
    }
}
~~~

**Important notes:**

- The **withMonitors** and **withSynchronizers** flags are queried from JVM capabilities before requesting info to avoid calling an unsupported overload.
- **getThreadInfo(ids, 16)** captures up to 16 stack frames per thread, but **does not request the full list of held monitors/ownable synchronizers**. To inspect those lists, call the overload with the corresponding flags as shown above.
- The data is a **snapshot**. Between finding the IDs and reading details, a thread may terminate; in that case, the corresponding element in **ThreadInfo[]** may be **null**.
- Do not log only **getThreadState()**. You need **getLockInfo()**, **getLockOwnerId()**, and **getStackTrace()** together to reconstruct the wait cycle.
- Stack frames show **the thread's execution path at capture time**; they do not by themselves prove which line originally created the lock or the underlying design cause. **getLockedMonitors()** can help point to the frame that acquired the monitor, but you still need to inspect the code and lock ordering to draw a conclusion.

### 5.2. Sequence for Investigating a Deadlock

1. **Identify symptoms:** which requests/tasks are stuck, is the thread pool out of workers, which deadlines are being missed?
2. **Capture state:** detect deadlocks and collect ThreadInfo/stack traces, preferably saving them to your existing diagnostics system.
3. **Build the wait graph:** for each stuck thread, record the awaited lock and its owner thread. Follow owners step by step to find a cycle.
4. **Read each stack:** locate the statement attempting to acquire the second lock and the earlier code that acquired the first lock.
5. **Find the opposing order:** for example, code path 1 acquires **lockA → lockB**, while code path 2 acquires **lockB → lockA**.
6. **Fix the synchronization structure:** unify lock ordering, shrink lock scopes, eliminate unnecessary lock nesting, or use an appropriate timeout-based approach.
7. **Reproduce and regression-test:** exercise multiple interleavings, add timeouts to tests so failures are controlled, and verify completion after the fix.

## 6. Distinguishing synchronized and ReentrantLock During Detection

### 6.1. Monitor Deadlocks with synchronized

When two threads hold and wait on each other's **synchronized** monitors, their state is typically **BLOCKED**. Both **findMonitorDeadlockedThreads()** and **findDeadlockedThreads()** can find this cycle if the JVM supports the respective method.

### 6.2. Deadlocks via Ownable Synchronizers

With **java.util.concurrent.locks.ReentrantLock**, threads do not contend for a monitor at a **synchronized** statement. Instead, they may wait on **AbstractQueuedSynchronizer/LockSupport**, commonly observed as **WAITING** or **TIMED_WAITING** depending on how they wait.

Two code paths acquiring ReentrantLocks in opposite order can also form a lock ownership cycle:

~~~text
T1 holds lockA (ReentrantLock) → calls lockB.lock(), must wait for T2
T2 holds lockB (ReentrantLock) → calls lockA.lock(), must wait for T1
~~~

**findMonitorDeadlockedThreads()** does not cover a cycle consisting only of ownable synchronizers. **findDeadlockedThreads()** can detect this form **when the JVM supports ownable synchronizer monitoring**. Check **isSynchronizerUsageSupported()** before relying on it.

**tryLock(timeout, unit)** can help avoid waiting indefinitely, but you must handle expiration, release any already-acquired locks in **finally**, and decide on an appropriate retry/backoff strategy. Replacing **lock()** with **tryLock()** without proper rules and cleanup can introduce other bugs.

### 6.3. Limitations to Remember

ThreadMXBean **is not a tool that proves an entire program is deadlock-free**. For instance:

- Threads waiting on **Future.get()**, **join()**, **CountDownLatch.await()**, **Condition.await()**, I/O, or an RPC can hang indefinitely due to waiting logic, yet may not form a lock-owner cycle detectable by **find...DeadlockedThreads()**.
- Waiting on an external service or deadlocks spanning **multiple JVMs/processes** cannot be inferred from a single JVM's ThreadMXBean alone.
- Native locks, custom waiting protocols, and other execution mechanisms may not appear as supported monitors/ownable synchronizers.
- On Java versions with **virtual threads**, check version-specific limitations: ThreadMXBean deadlock detection methods are specified for **platform threads**; do not assume their results cover all virtual threads.

Keep the boundary clear: **"No deadlock found via MXBean"** is the result of a specific check, **not** equivalent to "there is no deadlock, starvation, or hang."

## 7. Diagnosing a Running Application

### 7.1. Using In-Process JDK Code

An application can expose an internal diagnostic command invoked on demand, such as in a protected operational endpoint or during error collection. A basic snippet:

~~~java
// Example snippet placed inside a diagnostic method:
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

long[] ids = bean.isSynchronizerUsageSupported()
        ? bean.findDeadlockedThreads()
        : bean.findMonitorDeadlockedThreads();

if (ids != null) {
    ThreadInfo[] infos = bean.getThreadInfo(
            ids,
            bean.isObjectMonitorUsageSupported(),
            bean.isSynchronizerUsageSupported()
    );
    for (ThreadInfo info : infos) {
        if (info != null) {
            System.err.println(info);
        }
    }
}
~~~

For thorough investigation, persist the **ID**, **thread name**, **thread state**, **lock owner**, and **stack frames** as described in Section 5. Some **toString()** implementations may cap the number of printed stack frames; when you need the full trace, iterate **getStackTrace()** rather than relying solely on **ThreadInfo.toString()**.

**Do not run deadlock detection on every request**: scanning threads and locks has overhead and is intended for troubleshooting. If you include it in periodic monitoring, choose an appropriate interval, measure overhead, and provide a way to disable it when needed.

### 7.2. Using External JDK Tools

When you know the JVM's PID and have appropriate process access, you can capture a thread dump with JDK tools (the following commands are terminal examples; replace PID with the actual process ID):

~~~bash
jcmd <PID> Thread.print -l
~~~

In some environments, you can use:

~~~bash
jstack -l <PID>
~~~

**-l** requests additional lock information supported by the tool. Read the **Java-level deadlock** section if the tool generates a deadlock analysis, while also verifying the stack/owner relationships yourself. Commands and output may vary by JDK/JVM version and environment; appropriate JDK tools and attach permissions are required.

A useful thread dump typically contains sections similar to the following, which is only an **illustrative diagram**, not a guaranteed verbatim output:

~~~text
"A-then-B" ... BLOCKED
  waiting to lock RIGHT, owned by B-then-A
  locked LEFT

"B-then-A" ... BLOCKED
  waiting to lock LEFT, owned by A-then-B
  locked RIGHT
~~~

If you need to compare how the situation changes over time, take multiple dumps at reasonable intervals. A single dump may show a thread **BLOCKED** during a completely normal moment; multiple dumps and lock-owner relationships help distinguish brief contention from a persistent hang.

### 7.3. JMX and Operational Security

Because **ThreadMXBean** is an MXBean, environments may access it via **JMX/MBeanServer** with appropriate configuration and permissions. In production applications, restrict who can trigger thread dumps or retrieve stack traces: method names, parameters/implementation details, and file paths can expose internal information. Expose diagnostic interfaces only as broadly as necessary.

These methods primarily collect data; they **do not stop threads** and **do not fix deadlocks automatically**.

## 8. The Fix: Enforcing a Consistent Lock Acquisition Order

In the deadlock example, one worker acquires **left → right** while the other acquires **right → left**. If both always acquire in the order **left → right**, a wait cycle over those two monitors cannot form from those two call sequences.

Create **OrderedLocks.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class OrderedLocks {
    public static void main(String[] args) throws InterruptedException {
        Object first = new Object();
        Object second = new Object();
        AtomicInteger finished = new AtomicInteger();

        Runnable job = () -> {
            synchronized (first) {
                synchronized (second) {
                    finished.incrementAndGet();
                }
            }
        };

        Thread a = new Thread(job, "A");
        Thread b = new Thread(job, "B");
        a.start();
        b.start();

        a.join();
        b.join();
        System.out.println("finished=" + finished.get());
    }
}
~~~

Run with Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 OrderedLocks.java
java OrderedLocks
~~~

Output:

~~~text
finished=2
~~~

Explanation: threads may wait on **first** because only one thread holds the monitor at a time, but no thread ever holds **second** while attempting to acquire **first**. Thus, there is no opposing-order pair capable of forming a cycle like in the earlier demo. **AtomicInteger** here simply counts completed work; the increment occurs inside the already-synchronized region.

**In production code**, when multiple lock objects exist, you must establish an ordering rule that is **stable and consistent across all code paths**. If you order by a comparison key, you must also handle ties when two keys compare equal; never assume **identityHashCode()** is an absolute ordering key that can never collide.

Other ways to reduce risk:

- **Shrink lock-holding regions:** avoid holding a monitor while performing I/O, invoking external callbacks, making remote queries, or running overly long computations unless truly necessary.
- **Avoid nested locks:** reorganize data or move to a simpler single synchronization point when possible.
- **Use controlled timeouts:** for locks supporting **tryLock**, handle the failure branch and release all locks in **finally**.
- **Choose appropriate thread-safe structures:** for example, JDK concurrent collections/abstractions can reduce the number of manually managed locks; still verify atomicity for compound operations.
- **Do not try to fix deadlocks by adding sleep:** delays only alter interleaving; they do not eliminate the underlying wait cycle.
- **Do not use Thread.stop():** it is dangerous because it can abort operations while invariants are broken; the right fix is correcting lock design and lifecycle management.

## 9. Reproducible Testing and Diagnostics

### 9.1. Creating Deliberate Interleavings

Use **CountDownLatch**, **CyclicBarrier**, or similar coordination to force threads to reach the exact contention point. In the Section 4 demo, the latch ensures both threads hold their first lock before seeking the second, avoiding reliance on random CPU scheduling.

### 9.2. Bounding Test Execution Time

A test that intentionally triggers a deadlock must have a **timeout**. If the test calls an unbounded **join()** on deadlocked threads, the entire test suite can hang. When reproducing a monitor deadlock, **interrupt()** generally **does not unblock** a thread waiting to enter **synchronized**; do not rely on interrupt as a general recovery mechanism for this kind of deadlock.

In the example, marking both workers **daemon** lets the demo exit after `main` finishes printing. Daemon threads are appropriate for demonstrating the behavior in a lesson; in real applications, stuck daemon threads can still cause lost work or correctness bugs.

### 9.3. What to Verify After Fixing

- No **lockA → lockB → lockA** cycle remains across any relevant execution paths.
- Two or more threads can complete their work under stress tests with timeouts.
- Under high load, threads being **BLOCKED** briefly can still be normal; also monitor throughput and latency to spot bottlenecks.
- Error, interrupt, and cancellation paths do not hold locks longer than necessary.
- Thread pools, latches, or futures depending on the involved workers still have a clear completion or cancellation path.
- If a deadlock occurred in production, compare stack traces against the **deployed** code version (the actual build/release), not just the current development branch.

## 10. Common Pitfalls When Using ThreadMXBean

1. **Seeing many BLOCKED threads and calling it a deadlock.** You must prove a lock ownership cycle; isolated BLOCKED states may just be normal contention.
2. **Calling only findMonitorDeadlockedThreads() to find ReentrantLock deadlocks.** That method only checks object monitors; use **findDeadlockedThreads()** when ownable synchronizers are supported.
3. **Getting null and asserting the program cannot deadlock.** A null result only means no deadlock within the tool's scope was found at sampling time.
4. **Printing only thread names and states without owners and stacks.** This omits the details needed to trace the two opposing lock-acquisition paths.
5. **Calling getLockedMonitors() after only calling getThreadInfo(ids, depth).** To get held-lock lists, you must call the overload with the appropriate boolean flags.
6. **Treating every WAITING state as a deadlock.** WAITING may be normal waiting on a signal, worker queue, or timer; inspect the primitive and owner relationship.
7. **Confusing monitors with ownable synchronizers.** **synchronized** and **ReentrantLock** can report different thread states and require appropriate scanning methods.
8. **Throwing exceptions or interrupting to make synchronized release an awaited lock.** A thread **BLOCKED** on a monitor cannot generally be rescued by interrupt.
9. **Assuming deadlock detection means automatic recovery.** ThreadMXBean only provides diagnostics; you must fix the code structure or follow an impact-assessed restart procedure.
10. **Continuously scanning all threads without measuring cost.** Collecting stacks and lock states has overhead; use it only when needed and at a controlled frequency.
11. **Ignoring waits outside the lock-owner graph.** Futures, latches, I/O, native code, distributed systems, or virtual threads in various Java versions may require additional tools/methods.
12. **Writing deadlock tests without timeouts.** A test can hang forever even when the bug is successfully reproduced.

## 11. Incident Investigation Checklist

- **Symptoms:** are thread pools stalled, requests hanging, CPU low while blocked threads rise?
- **Scope:** does the application use **synchronized**, **ReentrantLock**, or other waiting primitives?
- **JVM capabilities:** check **isSynchronizerUsageSupported()** and **isObjectMonitorUsageSupported()** before requesting locked synchronizers/monitors.
- **Detection results:** which IDs did **findDeadlockedThreads()** or the monitor-only fallback return? Did it return null?
- **Data consistency:** read the same set of IDs with **getThreadInfo(...)**; handle threads that terminated or snapshot changes.
- **Cycle:** explicitly record **thread A waits for lock held by B**, **B waits for lock held by A**, and any longer cycle segments if present.
- **Stack trace:** do you have method/file/line info for where the lock is requested and which monitors/synchronizers are held?
- **Fix:** have you applied a consistent lock order, reduced lock nesting, or added proper timeouts and resource cleanup?
- **Verification:** do you have interleaving tests with timeouts and sufficient stress testing?
- **Operations:** are valid thread dumps/snapshots saved, access controls enforced, and diagnostic overhead bounded?

**Conclusion:** **ThreadMXBean** turns the symptom "threads are not making progress" into concrete data: **threads, awaited locks, owners, stack traces**, and, when supported, deadlock cycles. To fix the root cause, you must trace back to **lock acquisition ordering** and synchronization design; diagnostic tools are no substitute for that.

## 12. Official JDK Documentation

- [ThreadMXBean — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadInfo — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [ManagementFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [ReentrantLock — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
