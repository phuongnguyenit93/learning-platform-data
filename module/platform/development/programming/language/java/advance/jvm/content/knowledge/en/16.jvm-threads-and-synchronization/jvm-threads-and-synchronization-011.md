# Distinguishing Deadlock, Lock Waiting, and JVM Background Work

## 1. The problem: if a thread stops making progress, is it definitely a JVM deadlock?

In Java, an application can "hang", an HTTP request can take tens of seconds, or a thread dump can contain many **WAITING**, **TIMED_WAITING**, **BLOCKED** lines without **any deadlock occurring**. Conversely, an actual deadlock might involve only two application threads; the JVM's GC threads or compiler threads continue operating normally.

At least four kinds of phenomena must be distinguished:

1. **Deadlock:** there is a resource-wait dependency cycle in which the involved threads cannot make progress to release the locks they hold without external intervention or an appropriate change in conditions.
2. **Lock contention / lock waiting:** a thread wants to acquire a monitor or lock, but another thread temporarily holds it; the owner can still complete, release, and let the waiter continue. Lock waiting is not automatically a deadlock.
3. **Condition waiting / I/O / completion:** a thread may be waiting for a signal, a task, network data, or a timeout by design; there is no evidence of a lock cycle.
4. **JVM background work:** GC, JIT compilation, reference processing, service/runtime work, and JVM support threads can run, sleep, or wait periodically without indicating that the application is stuck.

Hypothetical scenario:

~~~text
The service returns HTTP responses slower than normal.

Thread dump at 10:00:
  http-worker-1     BLOCKED on object monitor A
  http-worker-2     RUNNABLE
  background-poller WAITING on BlockingQueue
  C2 CompilerThread RUNNABLE
  G1 concurrent GC thread RUNNABLE

What needs to be known:
  Who holds monitor A?
  What is the owner doing?
  Is there a wait cycle, or does the owner just need to release the monitor?
  Is the queue/poller waiting for work or missing a signal?
  Are GC/JIT just running background work or actually consuming CPU?
  Is HTTP slow because of DB/network, locks, GC pauses, CPU starvation, or something else?
~~~

**Do not conclude deadlock just from the word BLOCKED or WAITING.** You must build a concrete wait relationship, find the owner, and determine whether it has a path to make progress.

### Learning objectives

After this lesson, you need to:

- Correctly read Java 17's **Thread.State**: NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, TERMINATED.
- Distinguish **intrinsic object monitors (synchronized)** and **ownable synchronizers** such as ReentrantLock; know when a thread dump/JMX can find deadlocks.
- Draw a **wait-for graph** to distinguish a normal wait edge from a deadlock cycle.
- Recognize **starvation, livelock, condition-wait hang, thread-pool starvation**, and **I/O wait** that are not necessarily reported by the JVM's deadlock detector.
- Know that **Object.wait() temporarily releases the receiver monitor**, whereas **Thread.sleep()** and **LockSupport.park() do not automatically release intrinsic monitors**.
- Understand JVM **GC/JIT/background threads**, safepoints, and why a JVM still uses CPU even while business threads are waiting.
- Use **jcmd Thread.print**, **jstack**, **ThreadMXBean**, **jcmd Compiler.queue**, **GC logs**, and **JFR** for analysis.
- Run Java 17+ examples and explain deterministic stdout versus timing-dependent snapshots.
- Design **lock ordering, timeouts, cancellation, condition predicates**, and appropriate instrumented diagnostics.

**Version:** core knowledge follows Java SE 17; diagnostic examples/flags are based on **HotSpot Java 17**. Internals, thread names, GC algorithms, virtual-thread handling, and diagnostic outputs vary by JDK version/vendor/OS. Java 17 does not yet have virtual threads as a production feature; for Java 21+, consult the corresponding runtime documentation.

## 2. From "application hung" to a cause model

A service that does not respond to requests may still have a JVM making progress:

~~~text
Client request
      |
      v
  HTTP worker
      |
      +-- BLOCKED waiting for synchronized(lock)
      |
      +-- WAITING for Future/get()/join()
      |
      +-- TIMED_WAITING due to sleep/timeout
      |
      +-- RUNNABLE but consuming CPU in a hot loop
      |
      +-- RUNNABLE but native socket read waiting for I/O
      |
      +-- CPU-throttled by container/OS scheduler
      |
      +-- hitting GC safepoints, allocation stalls, or backpressure
      |
      +-- stuck in a multi-lock deadlock cycle
~~~

A JVM can still write GC logs, run the compiler, clean up references, or update metrics while business threads produce no further results at all.

**You must investigate the specific cause**, not label every lack of progress as "JVM deadlock".

### 2.1. Safety and liveness

- **Safety:** no incorrect results such as reading inconsistent state, lost updates, or invariant violations.
- **Liveness:** the program can eventually make progress/complete under the assumed conditions.
- **Deadlock:** a liveness failure caused by a wait cycle.
- **Starvation:** a thread may fail to be granted CPU/lock/permit for long enough even though other threads still make progress.
- **Livelock:** threads remain active/changing state, but their interaction prevents useful work from completing.
- **Prolonged condition wait:** a thread waits for a predicate or event that has not occurred; sometimes this is expected behavior, sometimes a bug.

There is no guarantee that "because a program is thread-safe, it always makes progress": code can avoid data races and still deadlock or starve.

## 3. Java 17's Thread.State: reading its true meaning

**Thread.State** is the enum set of Java-level thread states. These are **not** one-to-one native kernel scheduler states.

| State | Java-level meaning | Common examples | Proves deadlock by itself? |
| --- | --- | --- | --- |
| **NEW** | Thread object created, not yet started | new Thread(task) | No |
| **RUNNABLE** | Executing or ready in the VM; may be waiting for OS resources | CPU loop, some native I/O | No |
| **BLOCKED** | Waiting for an **intrinsic object monitor** | Waiting for synchronized(lock) | No |
| **WAITING** | Waiting for another action, without a specified timeout | Object.wait(), join(), LockSupport.park() | No |
| **TIMED_WAITING** | Waiting with a deadline/timeout | Thread.sleep, wait(timeout), join(timeout), parkNanos | No |
| **TERMINATED** | Execution has finished | run() completed | No |

### 3.1. RUNNABLE does not mean 100% CPU usage

A RUNNABLE thread may be:

- Running Java code on a CPU.
- Ready to run but waiting for the scheduler.
- In native code or an I/O operation depending on the implementation.
- Running in a CPU-consuming spin loop.
- Experiencing container CPU throttling that leaves little actual progress.

You need to correlate **CPU usage per thread**, stack frames, native I/O, profiling, and multiple snapshots before saying a RUNNABLE thread "is the culprit".

### 3.2. BLOCKED has a very specific meaning

**BLOCKED** means a Java thread is waiting for the **object monitor** of a synchronized statement/method, or waiting to reacquire the monitor after Object.wait(). It is not a generic state for "waiting for any lock".

A thread waiting for **ReentrantLock.lock()** may appear as **WAITING** or **TIMED_WAITING** involving LockSupport.park/AQS; it is not necessarily BLOCKED. You must inspect the lock owner and stack.

### 3.3. WAITING can be completely normal

States that can be valid by design:

- Thread pool worker waiting for a task in BlockingQueue.take().
- Consumer waiting on CountDownLatch.await().
- Main thread waiting on worker.join().
- Object.wait() waiting for a predicate/notify.
- LockSupport.park() used to manage work scheduling.
- Scheduled executor waiting for the next run.

If no task has arrived and no request waiting for a response is affected, a WAITING thread is "resting in the right place", not a bug.

### 3.4. TIMED_WAITING does not promise exact duration

**Thread.sleep(100)** requests sleeping for an approximate duration, but elapsed duration can be affected by the OS scheduler, timer precision, GC, or CPU contention. If a Thread sleeps inside a synchronized block, it **still owns that monitor**.

Do not use thread state polling as a coordination protocol: **getState() is only a snapshot**, and the state can change immediately after reading.

## 4. A single wait edge is not yet a deadlock

Suppose there are two threads:

~~~text
Thread T1:
  owns monitor M
  performs 10 ms work
  releases M

Thread T2:
  tries synchronized(M)
  BLOCKED while T1 owns M
  then enters after T1 unlocks
~~~

This is **normal lock contention**. T2 is not making progress at the moment of observation, but T1 has a path to finish and release the resource.

Relationship model:

~~~text
T2 --waits-for M--> T1 (owner)
T1 --doing work--> eventually unlock(M)

Wait-for graph:
  T2 ----> T1
          (no cycle)
~~~

Even if T2 has waited several seconds, you still need to see what T1 is doing. T1 may be performing an unreasonably long task or be stuck on I/O — but **there is not automatically a monitor deadlock cycle**.

### 4.1. Lock convoy

When multiple threads all need one global lock, successive owners can keep lengthening the queue:

~~~text
T1 owns M
T2 waits for M
T3 waits for M
T4 waits for M

T1 releases -> one contender acquires -> others continue waiting
~~~

This can be a **throughput bottleneck / lock contention**, with no circular wait. Increasing the number of threads can worsen contention; it usually requires shortening the critical section or partitioning state/locks.

### 4.2. Owner holds a lock while sleeping or doing I/O

~~~java
// Illustration inside a method, not a standalone class.
synchronized (lock) {
    Thread.sleep(300);
}
~~~

The thread still holds the monitor while sleeping. Other threads trying synchronized(lock) can become BLOCKED. An operation such as a DB call inside synchronized also extends lock hold time.

To fix it, check the invariant design and move I/O or parts that do not require exclusivity outside the critical section when safe.

## 5. Java 17+ Demo #1: waiting for a monitor then continuing, no deadlock

Create **MonitorContentionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class MonitorContentionDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object lock = new Object();
        CountDownLatch holderReady = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);
        AtomicInteger completedSections = new AtomicInteger();

        Thread holder = new Thread(() -> {
            synchronized (lock) {
                holderReady.countDown();
                try {
                    releaseHolder.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                completedSections.incrementAndGet();
            }
        }, "lock-holder");

        Thread contender = new Thread(() -> {
            synchronized (lock) {
                completedSections.incrementAndGet();
            }
        }, "lock-contender");

        holder.start();
        holderReady.await();
        contender.start();

        releaseHolder.countDown();

        holder.join();
        contender.join();

        System.out.println("completedSections="
                + completedSections.get());
        System.out.println("bothTerminated="
                + (!holder.isAlive() && !contender.isAlive()));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 MonitorContentionDemo.java
java MonitorContentionDemo
~~~

**Exact stdout when there is no external interruption and the process is given CPU to complete:**

~~~text
completedSections=2
bothTerminated=true
~~~

Explanation:

1. Holder acquires the lock, signals **holderReady**, then waits on releaseHolder **while still owning the intrinsic monitor**.
2. Main only starts contender after holderReady has been signaled. Contender needs the same lock, so it cannot enter before holder releases.
3. Main signals releaseHolder; holder continues, increments the counter, then exits synchronized.
4. Contender acquires the lock, increments the counter, then exits.
5. Main joins both and prints the deterministic result.

**No circular wait:** holder waits on a latch controlled by main; main does not need the monitor lock to signal. If holder waited forever because main never signaled, the program could hang due to a missing signal, but there is no evidence of an intrinsic-monitor deadlock cycle.

**Timing observation:** Do not assume that at a specific System.out.println contender is definitely in state BLOCKED, because it may not have been scheduled yet or holder may have already released. To capture a state, you must hold the workload at a point long enough with diagnostic tools; do not use a single getState() call as proof.

## 6. Deadlock is a wait cycle: wait-for graph

Classic monitor deadlock pattern:

~~~text
Thread T1:
    synchronized (A) {      // owns A
        synchronized (B) {  // waits B held by T2
            ...
        }
    }

Thread T2:
    synchronized (B) {      // owns B
        synchronized (A) {  // waits A held by T1
            ...
        }
    }
~~~

If T1 already holds A and T2 already holds B, and then both try to acquire the other's lock:

~~~text
        owns A                   owns B
         T1                       T2
          |                        |
          +-- waits for B -------->+
          <-------- waits for A ---+

Wait-for graph:
     T1 ------> T2
      ^         |
      |         v
      +---------+
      CYCLE
~~~

T1 cannot acquire B because T2 will not release before exiting the block; T2 cannot acquire A because T1 will not release before exiting the block. With intrinsic monitor entry, threads waiting for a lock normally cannot resolve this by themselves via a timeout because synchronized has no **tryLock(timeout)** API.

### 6.1. Four classic conditions

The Coffman conditions are commonly used to explain resource deadlock:

1. **Mutual exclusion:** a resource cannot be used concurrently in an exclusive manner.
2. **Hold and wait:** a thread holds at least one resource and waits for another resource.
3. **No preemption:** a resource cannot simply be taken away from an arbitrary owner while preserving invariants.
4. **Circular wait:** owners form a dependency wait cycle.

If at least one condition is eliminated through proper design, the corresponding deadlock type can be prevented. For example, **global lock ordering** prevents circular wait for the set of locks where it is obeyed.

### 6.2. Do not confuse deadlock with "thread A is blocked for a long time"

T1 waits for B held by T2, while T2 is computing and will release B: **not yet a deadlock cycle**.

T1 waits for B, T2 waits for A, and each thread holds the other's monitor: **there is a wait cycle**; if there is no valid release path, this is a deadlock.

T1 holds A then calls **Object.wait() on B** while still holding A; T2 wants to acquire A so it can notify B: this can cause a **condition/lock dependency deadlock** even though the states in the dump show a combination of WAITING and BLOCKED, not just two BLOCKED threads.

### 6.3. Deadlock is a property of the entire dependency set

A thread dump showing "waiting to lock B owned by T2" only gives one edge. You must investigate what T2 is waiting for, and continue until:

- You see a cycle back to a previously visited thread ⇒ there is a circular wait.
- You encounter an owner thread not waiting on any other resource ⇒ there is a possible path to make progress.
- You encounter a wait on an unobservable external system/condition ⇒ inconclusive; logs, runtime state, or external-system diagnostics are needed.

## 7. Distinguishing object monitor and ReentrantLock

Java has multiple synchronization mechanisms:

| Mechanism | How acquired | Typical wait seen | Release mechanism |
| --- | --- | --- | --- |
| **synchronized(obj)** | JVM monitorenter/implicit method monitor | Contender typically BLOCKED | Automatic on block/method exit |
| **ReentrantLock.lock()** | java.util.concurrent.locks | Typically uses AQS/LockSupport.park, may be WAITING | Programmer calls unlock in finally |
| **ReentrantLock.lockInterruptibly()** | Interruptible acquisition | Can handle interruption | unlock in finally after acquiring |
| **ReentrantLock.tryLock(timeout)** | Timed attempt | Can be timed wait | unlock when acquire succeeds |
| **ReadWriteLock** | Read/write lock permits | Depends on implementation and mode | Corresponding unlock |

**Java's Thread.State.BLOCKED only refers to an object monitor**; waiting on a java.util.concurrent synchronizer may be reported as WAITING/TIMED_WAITING. Choosing ReentrantLock does not automatically prevent deadlock; two ReentrantLocks can still form a wait cycle.

### 7.1. Ownable synchronizer

Some synchronizers have a concept of an owner (for example, ReentrantLock and ReentrantReadWriteLock.WriteLock). JVM management APIs can detect deadlocks involving **object monitors** and **ownable synchronizers** where supported.

Do not assume every lock type is recognized by **ThreadMXBean**: custom locks, semaphores, latches, distributed locks, futures, or external resources do not necessarily appear as cycles in the Java monitor/ownable-synchronizer graph.

### 7.2. A reentrant monitor does not deadlock with itself

A thread that already owns intrinsic monitor M can reenter synchronized(M) multiple times; the JVM tracks reentrant depth until exits balance out. Therefore:

~~~java
synchronized (lock) {
    synchronized (lock) {
        // Same owner thread re-entering the same monitor: valid.
    }
}
~~~

It does not deadlock merely because of nested synchronized blocks. However, if nested locks are **A then B** in one thread and **B then A** in another thread, circular wait can still occur.

## 8. ThreadMXBean: Java API for diagnosing deadlocks

**java.lang.management.ThreadMXBean** provides:

- **findMonitorDeadlockedThreads():** finds cycles involving object monitors.
- **findDeadlockedThreads():** finds cycles involving object monitors **and ownable synchronizers** supported by the implementation.
- **getThreadInfo(...):** thread details, lock owner, stack trace, and monitor/synchronizer metadata depending on the overload.
- **dumpAllThreads(...):** snapshot of threads with stack traces and lock information when supported by the VM.
- **getThreadCpuTime(...):** per-thread CPU time if enabled/supported.

**Null** from a deadlock finder means **no cycle within its inspection scope was detected at the sampling time**, not proof that the program is completely free of liveness bugs.

### 8.1. Runnable Java 17 demo: diagnosing existing cycles

Create **DeadlockInspector.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;

public class DeadlockInspector {
    public static void main(String[] args) {
        ThreadMXBean bean =
                ManagementFactory.getThreadMXBean();

        long[] ids = bean.findMonitorDeadlockedThreads();

        System.out.println("monitorCycleDetected="
                + (ids != null && ids.length > 0));

        if (ids != null) {
            System.out.println("affectedThreadCount="
                    + ids.length);
            ThreadInfo[] infos =
                    bean.getThreadInfo(ids, true, true);
            for (ThreadInfo info : infos) {
                if (info != null) {
                    System.out.println(
                            "thread=" + info.getThreadName());
                    System.out.println(
                            "state=" + info.getThreadState());
                    System.out.println(
                            "lock=" + info.getLockName());
                    System.out.println(
                            "owner=" + info.getLockOwnerName());
                }
            }
        }

        try {
            long[] allTypes = bean.findDeadlockedThreads();
            System.out.println("broaderCycleDetected="
                    + (allTypes != null
                    && allTypes.length > 0));
        } catch (UnsupportedOperationException unsupported) {
            System.out.println("broaderCycleSupported=false");
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 DeadlockInspector.java
java DeadlockInspector
~~~

**There is no single absolute stdout for every JVM** because counts and thread names reflect process state and synchronizer management capabilities. In a normal JVM with no deadlock:

~~~text
monitorCycleDetected=false
broaderCycleDetected=false
~~~

This is **typical output in a deadlock-free environment**, not an absolute contract. A JVM might support monitor detection but not broad ownable-synchronizer detection, or have unusual background/runtime state. If code prints thread names, order/names vary per run.

**Important:** this demo only inspects **the program's own JVM**. Running a brand-new inspector program cannot find deadlocks in another server process. To diagnose a server, use **jcmd/jstack/JMX in the target process** or integrate ThreadMXBean into an authorized service.

### 8.2. Why does getThreadInfo add information?

ThreadInfo can provide:

- Thread name, ID, state.
- Lock name being waited on to acquire/wait.
- Lock owner name/ID when known.
- Stack trace at snapshot time.
- Locked monitors and ownable synchronizers depending on overload.

However, a dump has a race: a thread can release/acquire a lock right after the snapshot. No public API guarantees that a dump is a history of all interleavings.

## 9. Some phenomena that are not Java monitor deadlocks

### 9.1. Waiting for a condition that has not happened yet

Thread A waits on CountDownLatch.await() and thread B has not finished processing its task yet. If B can still complete and call countDown, that can be **legitimate waiting**. If the producer forgets to call countDown, the system can hang due to a **missing signal**; the deadlock detector will not necessarily report a cycle.

### 9.2. Thread-pool starvation/self-deadlock

Suppose an ExecutorService has only **one worker thread**. Task A runs on that worker, submits task B to the **same executor**, and then calls **futureB.get()**. Task B sits in the queue with no other worker to run it; A waits for B, and B waits for the worker that A is occupying.

~~~text
Single-thread executor:
 Worker-1 executes Task A
    |
    +-- submits Task B to same executor
    |
    +-- waits Future.get(B) indefinitely

 Task B stays queued:
    cannot start because Worker-1 blocked in Task A
~~~

This is an **executor starvation deadlock** in terms of system liveness, **not necessarily a monitor/ownable-lock deadlock** recognized by ThreadMXBean.findDeadlockedThreads.

How to avoid it: do not block inside a task waiting for another task that can only run on the same pool with no remaining capacity; use completion composition, appropriate worker capacity, or separate executors based on resource constraints.

### 9.3. External resource deadlock

Two requests can deadlock on database row locks, distributed locks, or file locks. The JVM stack may only show socket I/O waiting for a DB response, usually without forming a Java-level lock ownership cycle. You need DB deadlock graphs, slow queries, and resource-level diagnostics.

### 9.4. Starvation

A thread may wait for a lock or CPU for a very long time because the lock is repeatedly won by other threads or the process is CPU-throttled. Having no circular wait does not mean latency meets requirements.

### 9.5. Livelock

Two threads both "yield" and retry according to an ineffective rule, continuously changing state without completing. They may show up as RUNNABLE instead of BLOCKED/WAITING. CPU usage may be high.

### 9.6. Busy spin

~~~java
// Bug illustration, do not use as a solution:
while (!ready) {
    // ready is an ordinary non-volatile field.
}
~~~

This can cause high CPU, does not guarantee visibility due to a data race, and does not create a wait-for graph. **Thread.onSpinWait** is a performance hint and does not turn an ordinary read into a volatile read.

## 10. Java 17+ Demo #2: valid WAITING via CountDownLatch

Create **LegitimateWaitingDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LegitimateWaitingDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch workerReady = new CountDownLatch(1);
        CountDownLatch mayProceed = new CountDownLatch(1);
        AtomicInteger result = new AtomicInteger();

        Thread worker = new Thread(() -> {
            workerReady.countDown();
            try {
                mayProceed.await();
                result.set(7);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "legitimate-waiter");

        worker.start();
        workerReady.await();

        mayProceed.countDown();
        worker.join();

        System.out.println("result=" + result.get());
        System.out.println("terminated=" + !worker.isAlive());
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 LegitimateWaitingDemo.java
java LegitimateWaitingDemo
~~~

**Stdout if there is no external interruption and it runs successfully:**

~~~text
result=7
terminated=true
~~~

The worker may transition to WAITING while waiting on the latch, but the thread state snapshot is not printed by the program and **you should not assign a fixed expected intermediate state** because main can call countDown very early. What matters is that **the worker has a path to complete** after the signal, and main uses join to obtain a deterministic result.

### 10.1. Why use a latch instead of sleep?

CountDownLatch has a protocol and memory consistency effects: actions before countDown **happen-before** actions after the corresponding successful await. **Thread.sleep** only pauses a thread for a duration, without guaranteeing that the other side has reached a milestone or published results.

### 10.2. Timeout is a diagnostic tool, not a correctness fix

~~~java
// Illustration requires importing TimeUnit:
boolean signaled =
        latch.await(5, java.util.concurrent.TimeUnit.SECONDS);
if (!signaled) {
    throw new IllegalStateException("Wait exceeded deadline");
}
~~~

A timeout can help a service avoid waiting indefinitely, but it does not make the producer emit the signal by itself. When a timed await returns false, do not rely on the latch's success happens-before contract.

## 11. How Object.wait(), Thread.sleep(), and LockSupport.park() differ

| API | Typical state | Automatically releases currently held intrinsic monitor? | Notes |
| --- | --- | --- | --- |
| **Object.wait()** on M | WAITING/TIMED_WAITING | **Yes, for receiver monitor M** | Requires thread to own M; reacquires M before returning |
| **Thread.sleep()** | TIMED_WAITING | **No** | Has no synchronization semantics of its own |
| **LockSupport.park()** | WAITING | **Does not automatically release intrinsic monitors** | May be unparked/interrupted or spuriously return |
| **Thread.join()** | WAITING/TIMED_WAITING | **Does not automatically release arbitrary monitors** | Completion synchronization with target thread |
| **CountDownLatch.await()** | Usually WAITING/TIMED_WAITING via AQS | **Does not automatically release intrinsic monitors** | Latch signal uses coordination protocol |
| **ReentrantLock Condition.await()** | Usually WAITING/TIMED_WAITING | Releases **associated ReentrantLock** per contract | Differs from intrinsic monitor; use proper lock discipline |

### 11.1. A hard-to-spot deadlock from wait()

~~~java
// Bug pattern: holding A while waiting on condition on B.
synchronized (a) {
    synchronized (b) {
        b.wait();
    }
}
~~~

**Object.wait() on B** temporarily releases acquisitions of B and reacquires them before returning, but **does not release A**. If the notifier needs synchronized(a) first before it can execute synchronized(b) and b.notifyAll(), the entire system can get stuck due to the dependency cycle on A and the signal on B.

Do not say "wait() releases all locks that the thread owns". It releases **the monitor of the receiver object**, not unrelated locks automatically.

### 11.2. notifyAll does not hand over the monitor immediately

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
    // Notifier still holds the monitor until the block ends.
}
~~~

Awakened waiters must reacquire the lock before returning from wait. If the notifier continues doing long work inside synchronized, waiters still make no progress.

### 11.3. Condition predicates must be rechecked

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

Use **while**, not just if, because of spurious wakeups, multiple waiters, and the condition possibly changing before the thread reacquires the lock. This is a correctness protocol, not performance tuning.

## 12. Java 17+ Demo #3: monitor wait with a completion path

Create **MonitorWaitDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class MonitorWaitDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        boolean[] ready = {false};
        boolean[] observed = {false};

        Thread waiter = new Thread(() -> {
            synchronized (monitor) {
                entered.countDown();
                while (!ready[0]) {
                    try {
                        monitor.wait();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                observed[0] = true;
            }
        }, "monitor-waiter");

        waiter.start();
        entered.await();

        synchronized (monitor) {
            ready[0] = true;
            monitor.notifyAll();
        }

        waiter.join();
        System.out.println("condition=" + ready[0]);
        System.out.println("observed=" + observed[0]);
        System.out.println("terminated=" + !waiter.isAlive());
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 MonitorWaitDemo.java
java MonitorWaitDemo
~~~

**Deterministic stdout when there is no external interrupt and it completes:**

~~~text
condition=true
observed=true
terminated=true
~~~

The synchronization edges:

- Waiter calls entered.countDown while still holding the monitor.
- Main calls entered.await(), then wants synchronized(monitor). If waiter has not called wait yet, main waits; when waiter calls wait, it releases the monitor.
- Main sets ready=true and calls notifyAll.
- Waiter reacquires the monitor, reads ready, proceeds, and updates observed.
- Main join ensures seeing the result after waiter finishes.

If waiter experiences a spurious wakeup before ready=true, the while loop rechecks the condition so it does not proceed erroneously.

## 13. JVM background threads: being RUNNABLE or WAITING can be completely normal

A HotSpot JVM typically has threads serving the runtime, for example:

| Group | Role | What must not be inferred |
| --- | --- | --- |
| **GC worker/concurrent threads** | Collecting, marking, processing heap, sometimes concurrent with application | RUNNABLE GC thread does not mean GC deadlock |
| **C1/C2 CompilerThread** | Compiling hot bytecode into native machine code | JIT CPU usage does not prove a business thread is deadlocked |
| **Reference Handler** | Serving reference processing mechanisms per VM design | WAITING is not broken by default |
| **Finalizer (if present)** | Supporting historical finalization that has been discouraged/deprecated | Do not use thread name as a guarantee every JDK has a finalizer |
| **Common-Cleaner / cleaners** | Cleaning resources via cleaning mechanisms | WAITING when there are no tasks is normal |
| **Service Thread / VM Thread** | Internal VM work and coordination | Thread names/states vary by build |
| **Attach Listener (if created)** | Serving attach/diagnostic operations | Not a business HTTP worker |
| **Signal Dispatcher** | Handling signaling/runtime events on supported platforms | WAITING state is usually valid |
| **Sweeper / code-cache support** | Monitoring parts of compiled code cache when present | Does not mean the app has finished warm-up |
| **User-created background pool threads** | Scheduled tasks, HTTP clients, executor maintenance | Not automatically JVM internal threads |

**Actual names vary by JDK, collector, architecture, flags, and subsystem initialization status.** Do not require a thread dump to contain this exact list to be considered Java 17.

### 13.1. Concurrent GC is not full-time stop-the-world

For example, a collector has **concurrent mark threads** running while mutators also run. GC threads use CPU, but that does not mean application threads are paused throughout that phase.

Conversely, when the JVM has a **GC STW pause/safepoint**, many application threads can simultaneously stop making progress for an interval, but that is **not a deadlock between application locks**. Correlate GC logs/safepoint logs with p99 latency and timestamps.

### 13.2. The JIT compiler can consume CPU while the application is still healthy

C1/C2 compiler threads generate optimized native code when methods become hot. During warm-up, JIT CPU can be high and application response times can fluctuate due to resource competition.

If the application loses throughput, you must distinguish:

- Is JIT compiling many methods and holding CPU?
- Is the code cache full, throttling compilation?
- Is there CPU quota/cgroup throttling?
- Is GC also consuming CPU?
- Is the business code itself busy-spinning?

**A RUNNABLE CompilerThread is not a sign of deadlock.** Use JFR, compiler logs, and jcmd Compiler.queue/codecache to verify JIT activity.

### 13.3. Background threads waiting for work are normal

A pool thread with a stack at **LinkedBlockingQueue.take** or **ScheduledThreadPoolExecutor delayed queue** may be idle by design.

If there is no backlog and requests are still processed normally, there is no issue. If the task queue keeps growing while workers are all WAITING in an abnormal way, you need to verify whether there is a producer/consumer handoff, permits, cancellation, or task submission bug.

## 14. Daemon threads and JVM process lifetime

**Daemon thread** is an attribute that affects the condition for the JVM exiting when no non-daemon threads remain alive. Daemon **does not mean** "internal JVM thread" or "low-CPU-priority thread".

Correct points:

- An application can create its own daemon threads.
- The JVM has runtime threads with varying policies.
- A WAITING daemon thread can be completely normal.
- The JVM can exit when only daemon threads remain, without waiting for them to finish business work.
- A non-daemon thread WAITING indefinitely can keep the JVM process alive.
- A deadlocked daemon thread is still a bug if work depending on it is affected, regardless of daemon status.

Do not turn all threads into daemons to "fix hanging on shutdown"; fix lifecycle, task cancellation, and the executor shutdown protocol.

### 14.1. Shutdown issues differ from deadlock

A server failing to exit after a shutdown request may be due to:

- Non-daemon executor workers not shut down.
- Scheduled tasks still active.
- Consumers waiting on a queue not signaled/canceled.
- Socket listener not closed.
- A thread holding a monitor being stuck, possibly deadlocked or in a long wait.
- Shutdown hook waiting on an external resource.
- The JVM genuinely doing work that the application has not accounted for.

Use thread dumps at shutdown and check executor shutdownNow/awaitTermination per protocol; **do not call System.exit on your own** to hide the root cause in library design.

## 15. The JVM is still working: how to correlate logs with thread dumps

A real-world scenario:

~~~text
14:00:00 Request starts
14:00:01 HTTP thread waiting
14:00:02 JIT/compiler activity
14:00:03 GC concurrent mark
14:00:04 Request still waiting
14:00:05 New thread dump
~~~

This **does not prove** JIT or GC is the reason the request has not finished. Build a data-driven timeline:

1. Does the request trace show it is waiting for a lock, DB, socket, future, or task?
2. Does the thread dump show the waiting location and lock owner?
3. Does the GC log have an STW pause at the exact time, and what is its duration?
4. Does the CPU profile show compiler/GC threads consuming most of the CPU quota?
5. Do service metrics show a queue backlog, exhausted connection pool, or request concurrency spike?
6. Are thread states identical across multiple snapshots spaced intentionally apart?

**Correlation is not enough for causation.** GC/JIT can be concurrently present as background noise during an incident caused by an application deadlock.

## 16. jcmd: the first step to see a live JVM

On HotSpot JDK 17, from the appropriate machine/process namespace:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> Thread.print
jcmd <PID> Thread.print -l
~~~

**<PID>** is a placeholder to replace with the actual process ID, not a literal string. Attach permissions usually require the same user/appropriate permissions; in containers, pay attention to the PID namespace. If a jcmd command is not supported, read **jcmd <PID> help** on the target build.

**Thread.print -l** can add java.util.concurrent ownable synchronizer information. A thread dump has overhead (impact is usually medium, depending on thread count); avoid taking them too frequently on machines with many threads.

### 16.1. jstack

~~~bash
jstack <PID>
jstack -l <PID>
~~~

jstack can print full thread dumps and lock details depending on the JDK build/attach support. Use **jcmd Thread.print** as the primary observation choice on modern HotSpot; do not assume jstack is deprecated or absent across all Java 17 distributions.

### 16.2. How to read a stack fragment

~~~text
"http-worker-7" ... java.lang.Thread.State: BLOCKED
    at com.example.Service.update(Service.java:77)
    - waiting to lock <0xABC> (a java.lang.Object)

"http-worker-3" ... java.lang.Thread.State: RUNNABLE
    at com.example.Service.persist(Service.java:32)
    - locked <0xABC> (a java.lang.Object)
~~~

This is an **illustrative thread-dump example**, not output captured from a real JVM. It shows that worker-7 wants to acquire monitor **0xABC**, and worker-3 holds that monitor at dump time.

To diagnose, continue investigating what worker-3 is doing, whether it is waiting on I/O or other locks, and how long until it releases.

### 16.3. Thread dump ID/lock identity

- Thread names are set by the application/JVM and can duplicate or change.
- The Thread ID in the Java API differs from the **native OS thread ID** depending on the platform.
- A stack may display hexadecimal **nid** and **tid** as a VM ID/native pointer depending on dump format.
- Lock identity in a thread dump is typically a VM object identity/address-like token, **not a public API Java reference**.
- Do not compare only by object class name when identifying the same monitor; you need the exact lock identity.

### 16.4. Multi-snapshot: two or three points in time

Take one dump, wait an interval useful for the service (for example, 5–10 seconds if appropriate), then take another:

~~~bash
jcmd <PID> Thread.print -l
# After an appropriate observation interval:
jcmd <PID> Thread.print -l
~~~

Goals:

- Is the same thread still waiting on the same lock?
- Has the lock owner changed or not?
- Is the owner stack changing or "stuck" on one call?
- Is the same monitor cycle present across multiple snapshots?
- Is the request queue backlog increasing/decreasing?
- Is GC/JIT background activity changing?
- Do per-thread CPU counters/stack sampling show threads actually working?

**Do not treat "identical stack twice" as absolute proof of deadlock.** A blocking read or polling loop can also have the same stack across multiple captures.

## 17. Procedure for building a wait-for graph from a thread dump

Suppose the dump has:

~~~text
T1: BLOCKED waiting to lock B; owns A
T2: BLOCKED waiting to lock C; owns B
T3: BLOCKED waiting to lock A; owns C
~~~

Draw:

~~~text
T1 --waits for B owned by--> T2
T2 --waits for C owned by--> T3
T3 --waits for A owned by--> T1

Cycle: T1 -> T2 -> T3 -> T1
~~~

If the lock info is reliable and no change breaks the cycle, this is a Java monitor deadlock.

### 17.1. Step-by-step verification

1. Pick a thread directly affecting requests/SLA.
2. Record the lock identity the thread is trying to acquire.
3. Find the owner thread of that lock in the snapshot.
4. Read the owner's stack and the resource the owner is waiting on.
5. Continue following the owner→waiter relationship until there is a cycle, a dead end, or an external wait.
6. If there is a cycle, cross-check with **ThreadMXBean.findDeadlockedThreads()** / dump diagnostics when available.
7. If there is no cycle, investigate long-held locks, I/O, starvation, or missing signals.
8. Compare against the request/GC/CPU timeline to determine actual impact.

### 17.2. Deadlock detection does not cover the entire world

Situations that can escape the standard detector:

- Thread-pool starvation due to Future.get() on the same worker pool.
- Distributed lock / DB row deadlocks outside the JVM.
- Missing CountDownLatch countdown.
- Logical condition cycles not represented by ownable lock owners.
- A deadlock that occurs only briefly and is then resolved by timeout/interrupt.
- Mismatch between JMX visibility and virtual-thread implementations in newer JDKs.

Therefore, **findDeadlockedThreads()==null does not mean all threads have a progress guarantee**.

## 18. Java Flight Recorder (JFR) to measure lock contention and waiting

JFR supports recording events to correlate thread behavior with a timeline. Depending on Java 17 recording settings:

- **jdk.JavaMonitorEnter**: relevant contended monitor entry events.
- **jdk.JavaMonitorWait**: Object.wait related.
- **jdk.ThreadPark**: LockSupport park-related events.
- **GC events**: GC pauses/concurrent phases.
- **Execution/CPU samples**: business or compiler/GC CPU activity when the corresponding event is enabled.

Example starting an app main class:

~~~bash
java -XX:StartFlightRecording=filename=thread-diag.jfr,duration=60s,settings=profile MyService
~~~

A real MyService class and an environment supporting JFR are required. If the app stops before 60s, recording duration and output depend on lifecycle/settings.

Read with the CLI:

~~~bash
jfr summary thread-diag.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark thread-diag.jfr
~~~

**Having no events does not prove the code has no synchronized or park.** Events may be disabled, filtered by a duration threshold, or not appear within the sampling interval.

### 18.1. Observing a running process with jcmd JFR

~~~bash
jcmd <PID> JFR.start name=threadcase settings=profile duration=60s filename=threadcase.jfr
jcmd <PID> JFR.check
~~~

Option syntax depends on the HotSpot JDK build; read **jcmd <PID> help JFR.start** to confirm. Recording has CPU/disk/storage overhead depending on configuration, so retention must be managed.

### 18.2. Using JFR to measure instead of counting BLOCKED snapshots

A request might be BLOCKED for 2 ms each time, yet happen thousands of times/s, causing throughput problems; one snapshot every 10s might never hit the BLOCKED moment. JFR duration-based events provide better visibility into contention frequency/time distribution when enabled with appropriate thresholds.

## 19. GC logs and safepoints: distinguishing JVM pauses from application lock waits

On HotSpot Java 17, enable Unified Logging selectively:

~~~bash
java -Xlog:gc=info -Xlog:safepoint=info MyService
~~~

**MyService** is an illustrative class with main. Verify tag availability/format with:

~~~bash
java -Xlog:help
~~~

When the JVM performs a stop-the-world GC phase, application threads may pause so GC can proceed. Those threads **cannot create a lock cycle by themselves** solely from a GC pause.

### 19.1. GC overhead vs application stall

| Observation | Possibility | Additional evidence needed |
| --- | --- | --- |
| GC pause log coincides with request p99 spike | Possibly due to STW GC | Request trace, duration correlation |
| Prolonged GC concurrent marking | Possibly GC consuming concurrent CPU | CPU profile, GC logs, and app throughput |
| Many BLOCKED on the same monitor | Lock contention | Owner stack, hold time, wait-for graph |
| WAITING at BlockingQueue.take | Possibly valid idle | Task queue depth, producers, pending requests |
| RUNNABLE C2 CompilerThread | JIT consuming CPU | Compiler.queue/codecache, CPU load |
| CPU throttled by container | Lack of CPU progress | cgroup/OS metrics |
| JVM heap near max and allocation stalls | Memory pressure | GC/heap telemetry |
| Future.get() waiting for task on single-thread pool | Pool starvation | Executor queue and worker stacks |

### 19.2. "The JVM is active" does not prove requests are progressing

GC/JIT/Reference Handler threads may still be working while HTTP threads are deadlocked. The process might still respond to health checks using a different thread pool, masking a failure on the business path.

Therefore, health checks should verify appropriate readiness/end-to-end components, not merely "JVM PID exists".

## 20. JIT work: monitoring compiler queue and code cache

In Java 17 HotSpot:

~~~bash
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.codelist
~~~

- **Compiler.queue:** compilation tasks waiting or managed according to the tool.
- **Compiler.codecache:** layout/usage of the generated native code cache.
- **Compiler.codelist:** live compiled methods printed by the tool.

A RUNNABLE CompilerThread can be valid JIT warm-up. If the compiler queue backlog persists and JIT CPU consumes significant resources, request throughput may be affected even without a deadlock.

**Do not treat a single empty queue snapshot as proof that the JVM is not running JIT.** Tasks may have finished processing; the code cache still holds compiled methods.

### 20.1. Background thread consuming CPU without causing deadlock

Possible causes:

- Startup/warm-up compilation.
- Concurrent GC marking.
- Reference processing backlog.
- Scheduled internal VM operations.
- Application logging/metrics daemon threads.
- An application busy loop disguised as a daemon service.

You need thread CPU samples by name/native thread ID and stack, not just Thread.State.

### 20.2. CPU throttling does not create a Java monitor cycle

An owner thread can take a lot of wall-clock time to release a lock because it is not granted CPU by the OS scheduler. Waiters will be BLOCKED for a long time, but the root cause is CPU quota/oversubscription, not lock-order inversion. This is especially important in containers with cgroup quotas.

## 21. How to avoid deadlock: designing lock ordering

One way to prevent deadlocks across multiple object monitors is **global lock order**.

Suppose there are two fixed locks A and B; all threads always acquire A before B, and release in lexical nesting order:

~~~java
synchronized (a) {
    synchronized (b) {
        // Update state involving both a and b.
    }
}
~~~

Do not allow any code path to acquire B then A; if followed consistently, an A→B/B→A wait cycle cannot form for those two locks.

### 21.1. Java 17+ Demo #4: multiple threads with lock order

Create **OrderedLocksDemo.java**:

~~~java
public class OrderedLocksDemo {
    private static final Object FIRST = new Object();
    private static final Object SECOND = new Object();
    private static int count;

    private static void increment() {
        synchronized (FIRST) {
            synchronized (SECOND) {
                count++;
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread[] workers = new Thread[4];

        for (int t = 0; t < workers.length; t++) {
            workers[t] = new Thread(() -> {
                for (int i = 0; i < 2_000; i++) {
                    increment();
                }
            });
        }

        for (Thread thread : workers) {
            thread.start();
        }
        for (Thread thread : workers) {
            thread.join();
        }

        System.out.println("count=" + count);
        System.out.println("expected=" + (4 * 2_000));
        System.out.println("correct="
                + (count == 4 * 2_000));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 OrderedLocksDemo.java
java OrderedLocksDemo
~~~

**Exact stdout upon normal termination:**

~~~text
count=8000
expected=8000
correct=true
~~~

- Each worker performs 2,000 increments.
- Each increment acquires FIRST then SECOND, with no code path reversing the order.
- count++ is inside the shared critical section so there are no lost updates.
- Main joins all threads and then reads count.
- **The output does not prove every other design in the system is deadlock-free**; it only shows that this example has ordering and normal progress.

### 21.2. What if locks depend on dynamic object identity?

If you need to acquire two account locks based on dynamic objects, choose a **stable total order** such as a unique account ID and always acquire from smaller ID to larger ID. Avoid relying on hashCode/identityHashCode alone as a total order if collisions are possible; on collision, you need a tie-breaker lock or an additional deterministic resolution. Simply ordering by variable names a, b in each caller is not enough if callers reverse arguments.

## 22. ReentrantLock: timeouts and interruption

With intrinsic synchronized, **there is no built-in tryLock(timeout)**, and a thread that is BLOCKED waiting for monitor entry does not exit simply because you call interrupt as it would with an interruptible lock API.

ReentrantLock supports:

~~~java
// Example method in a class with ReentrantLock lock:
if (lock.tryLock(100,
        java.util.concurrent.TimeUnit.MILLISECONDS)) {
    try {
        // Critical section.
    } finally {
        lock.unlock();
    }
} else {
    // Timeout: log, retry/backoff, or fail fast according to the contract.
}
~~~

Catch/declare InterruptedException appropriately. A tryLock timeout gives the **failed to acquire lock** path a handleable outcome, but does not automatically fix all deadlocks: if a thread holds A and then times out on B, you must still **properly release A in finally** and handle state consistency.

### 22.1. lockInterruptibly

**ReentrantLock.lockInterruptibly()** allows abandoning lock waiting upon interrupt, unlike intrinsic synchronized entry. A good cancellation design can use this method, but must ensure that once acquired, it unlocks in finally.

### 22.2. Do not relax synchronization by deleting locks

If an app deadlocks due to wrong lock order, removing synchronized can introduce data races, lost updates, or corrupted state. You must fix the protocol: unify ordering, reduce scope, use immutable messages, actor pattern/queues, or locks with timeouts and proper rollback logic.

## 23. Long-held locks and I/O in critical sections

A bad pattern:

~~~java
synchronized (lock) {
    databaseCall(); // May block due to DB/network.
    cache.put(key, value);
}
~~~

If databaseCall takes 20 seconds, other threads needing the lock will wait for the full 20 seconds. That can be a **lock convoy caused by blocking I/O**, not a circular deadlock in the JVM.

Consider:

~~~java
Result result = databaseCall();

synchronized (lock) {
    cache.put(key, result);
}
~~~

But only do this if the **business invariant** does not require the DB call and cache update to be within the same atomic protocol. If there are ordering/versioning/transaction requirements, redesign carefully rather than mechanically moving code outside the lock.

### 23.1. Lock scope is both a correctness and latency issue

- Scope too wide: contention, tail latency, risk of holding a lock across I/O.
- Scope too narrow: breaks invariants and creates check-then-act races.
- Inconsistent nested locks: deadlock risk.
- Calling externally supplied callbacks under a lock: hard to predict which locks external code might acquire.
- Synchronized on public objects/String literals: risk of unrelated code accidentally sharing a monitor.

Document clearly which state belongs to which lock and where transaction boundaries lie.

## 24. What does a thread dump tell you and what does it not?

**Can help find:**

- Thread names/IDs and states at snapshot time.
- Current stack frames.
- Location waiting to acquire a monitor/ownable synchronizer.
- Lock owner/held locks when provided by the JVM/tool.
- Some Java-level deadlock cycles.
- JVM runtime/background threads currently present.

**Not sufficient to assert:**

- Total CPU usage over several minutes.
- Whether downstream I/O operations completed.
- Deadlocks on external DB row locks.
- The exact root cause of all request latency.
- That a WAITING thread is a leak or deadlock.
- That a RUNNABLE background JVM thread means application threads are stopped.
- That no new output means Java heap GC has stopped working.
- That lock acquisition order is correct on every code path.

You must combine dumps with logs, traces, counters, and service-specific conditions.

## 25. Priority-ordered production investigation method

### Step 1 — Record symptoms and scope

- Is the whole JVM unresponsive or just one endpoint?
- Are new requests still being accepted?
- Is throughput zero or merely reduced?
- Does the health check accurately reflect business readiness?
- CPU%, RSS, heap/GC, network/DB state?
- Since which deploy/traffic change did the incident occur?

### Step 2 — Record JDK and configuration

~~~bash
java -version
jcmd <PID> VM.version
jcmd <PID> VM.flags
jcmd <PID> VM.uptime
~~~

VM.flags may contain options related to GC/JIT/logging/CPU. Do not use a list of HotSpot background thread names from a different JDK as a standard.

### Step 3 — Safely collect multiple thread dumps

~~~bash
jcmd <PID> Thread.print -l
~~~

Save output with timestamps; after a useful interval, take another snapshot. Avoid recording credentials or sensitive request payloads in reports because stacks/dumps can contain class names, identifiers, and business context.

### Step 4 — Classify affected threads

- BLOCKED on which object monitor?
- WAITING at wait/join/park/latch/future?
- RUNNABLE in a business loop or native I/O?
- TIMED_WAITING on a normal timeout?
- Which threads are app workers, and which are JVM internal?
- Is one owner holding multiple locks?

### Step 5 — Build the wait-for graph

Follow lock owners to find cycles. If there is a cycle, check the ThreadMXBean/jcmd deadlock report and the class/method order that led to the inversion.

### Step 6 — If no cycle is found, look for missing progress

- Is a future/task waiting for a pool that has free workers?
- Did a producer forget countDown/notify/completion?
- Does I/O have timeouts and circuit breakers?
- Is a CPU quota throttling the owner thread?
- Is a thread spinning or in a valid blocking state?
- Do GC/safepoint pauses or allocation stalls coincide with p99?

### Step 7 — Compare JVM vs service timelines

- GC log/safepoint log.
- JFR monitor enter/wait/park, CPU samples.
- Request traces, queue depth, and DB timings.
- Compiler.queue/codecache if JIT warm-up is suspected.
- Thread CPU consumption using the appropriate tool.

### Step 8 — Apply the fix matching the root cause

- Lock-order deadlock → unify global order, reduce nesting.
- Long-held lock → reduce I/O inside critical sections if safe.
- Missing signal → fix predicate/cancellation/notifyAll protocol.
- Pool starvation → eliminate synchronous dependencies within the same pool or increase capacity appropriately.
- CPU throttling → fix quotas/scaling/expensive work, do not blame "synchronized deadlock".
- GC pause → tune/reduce allocations, but only after logs confirm.
- JIT overhead → warm-up/CPU budget/diagnostics, do not delete synchronized arbitrarily.
- External DB locks → fix transaction order at the DB layer.

### Step 9 — Prevent recurrence

- Write stress/liveness tests with reasonable timeouts.
- Instrument lock wait time, queue age, pending futures, executor active/queued tasks.
- Alert on request p99, throughput, CPU throttling, GC pauses, backlog.
- Tag thread names with subsystem ownership.
- Use graceful shutdown/cancellation.
- Code-review lock graphs when adding new synchronization.

## 26. Diagnostic scenarios with solutions

### Scenario A — A thread is BLOCKED for 2 seconds, owner is processing

**Facts:** T2 waits on M held by T1, T1 is not waiting on another lock; T1 is persisting data. This is **contention/long-held lock**, not yet proof of deadlock. Check I/O duration, critical section scope, T1 progress; if T1 releases, T2 can run.

### Scenario B — Two threads are both BLOCKED on each other's monitors

**Facts:** T1 holds A waits B; T2 holds B waits A. There is a circular wait, which is a **monitor deadlock** if the dependencies persist. Fix lock ordering and avoid hold-and-wait.

### Scenario C — 100 pool workers WAITING at BlockingQueue.take()

**Facts:** Queue is empty, no pending requests. This can be **idle by design**. No deadlock fix needed.

### Scenario D — 100 workers WAITING while request queue is growing

**Facts:** There is a mismatch between incoming tasks and dispatch/permits/wakeup. Check whether you are looking at the right queue and right executor, producer flow, task submission, and pool lifecycle. Do not rush to conclude JVM deadlock.

### Scenario E — G1 concurrent GC thread RUNNABLE, HTTP thread WAITING

**Facts:** These may be two independent conditions. The GC thread is doing background work; the HTTP thread may be waiting on a future. Use timestamps/GC logs/CPU data to verify causality.

### Scenario F — C2 CompilerThread using 80% of one CPU

**Facts:** May be warm-up or compilation churn; not a deadlock. Check Compiler.queue, codecache, JFR/CPU profile, JVM uptime, and throughput.

### Scenario G — Single-thread executor A waits for B executed by the same pool

**Facts:** A holds the sole worker and Future.get waits for queued B; this is a **thread-pool starvation deadlock**, not necessarily reported by the monitor deadlock detector. Fix the task dependency architecture or executor capacity.

### Scenario H — Thread.sleep inside synchronized

**Facts:** The thread still holds the monitor, and contenders can become BLOCKED. This is lock contention / possibly poor design, not sleep releasing the lock.

### Scenario I — Thread is in Object.wait()

**Facts:** The waiter has temporarily released the receiver monitor and must reacquire it before returning. If the notifier forgot to signal the predicate/signal, this is missing condition progress. If the notifier is stuck on an unrelated lock that the waiter still holds, it can become a liveness deadlock.

### Scenario J — findDeadlockedThreads returns null, service still hung

**Facts:** No covered owner cycles were found at measurement time, but there may be external resource waits, pool starvation, condition waits, livelock, starvation, or CPU/GC problems. Continue investigating.

### Scenario K — HTTP worker RUNNABLE in native socketRead

**Facts:** RUNNABLE does not necessarily mean a busy CPU loop. The thread may be waiting on I/O depending on the implementation; check socket/DB/network timeouts.

### Scenario L — JVM has only daemon threads left and is about to exit

**Facts:** This is process lifetime semantics, not proof of deadlock by itself. Check which business tasks are running in daemon workers and whether shutdown cancels properly.

## 27. 25 self-check questions with answers

**Question 1.** Does one BLOCKED thread prove a deadlock?

**Answer:** No. BLOCKED means waiting for an object monitor; it may be contention if the owner will release.

**Question 2.** What does a classic monitor deadlock require besides a thread waiting for a lock?

**Answer:** It requires a wait cycle, for example T1 owns A waits B and T2 owns B waits A.

**Question 3.** Does RUNNABLE mean a thread is definitely using 100% CPU?

**Answer:** No; it may be ready to run, in native I/O, or not yet granted CPU by the scheduler.

**Question 4.** Is an idle thread pool commonly having WAITING a bug?

**Answer:** No, if it is waiting on a valid task/condition and there is no neglected backlog.

**Question 5.** Does Thread.sleep release a currently held monitor?

**Answer:** No.

**Question 6.** Does Object.wait release a monitor?

**Answer:** Yes, it releases the receiver monitor according to the rules and must reacquire before returning; it does not release unrelated locks.

**Question 7.** Does notifyAll hand the monitor to a waiter immediately?

**Answer:** No; the notifier still holds the monitor until it unlocks.

**Question 8.** WAITING at Future.get on a single-thread executor can be what liveness bug?

**Answer:** Thread-pool starvation/self-deadlock when a running task waits for a task queued into the same sole-worker pool.

**Question 9.** Does a RUNNABLE JVM background GC thread prove the entire JVM is STW?

**Answer:** No; concurrent GC work can run alongside application threads.

**Question 10.** Is a C2 CompilerThread consuming CPU a monitor deadlock?

**Answer:** No; it may be compiling code.

**Question 11.** Is a ReentrantLock.lock() wait always BLOCKED?

**Answer:** No; AQS/LockSupport may display WAITING/TIMED_WAITING.

**Question 12.** Which API finds monitor-only deadlock cycles?

**Answer:** ThreadMXBean.findMonitorDeadlockedThreads().

**Question 13.** Which API also finds ownable synchronizers when supported?

**Answer:** ThreadMXBean.findDeadlockedThreads().

**Question 14.** Does findDeadlockedThreads returning null prove there are no liveness bugs?

**Answer:** No; the detector does not cover external locks, missing signals, pool starvation, and all conditions.

**Question 15.** What jcmd command prints a thread dump?

**Answer:** jcmd <PID> Thread.print; add -l to observe java.util.concurrent locks when supported.

**Question 16.** Why are multiple snapshots needed?

**Answer:** To distinguish a temporary wait from a prolonged state, determine owner progress, and correlate timelines.

**Question 17.** Is knowing the lock class is Object enough to identify the same monitor?

**Answer:** No; you need the exact object identity/lock token, not just the class type.

**Question 18.** Does nested synchronized on the same monitor by the owner deadlock with itself?

**Answer:** No, Java intrinsic monitors are reentrant.

**Question 19.** What risk does nested A→B versus B→A create?

**Answer:** Lock-order inversion, a circular wait deadlock if an appropriate interleaving occurs.

**Question 20.** How does lock ordering prevent deadlock?

**Answer:** All paths acquire multiple locks in a total order, preventing cycles from forming for the involved locks.

**Question 21.** Is waiting on a DB row lock guaranteed to be seen by the Java monitor detector?

**Answer:** No; DB diagnostics / external resource waits are needed.

**Question 22.** A thread sleeps inside synchronized for 30s, causing 50 threads to be BLOCKED. Appropriate root cause?

**Answer:** Long-held monitor due to sleep/I/O inside a critical section, not necessarily a circular deadlock.

**Question 23.** What happens to daemon threads when only they remain in the JVM?

**Answer:** The JVM can exit without waiting for daemon tasks to complete, per process lifetime semantics.

**Question 24.** A thread dump shows WAITING on BlockingQueue and the queue is empty: what to fix?

**Answer:** Possibly nothing; this is valid idle state. Verify the right executor/task backlog.

**Question 25.** What are the three main groups of data to analyze a service not making progress?

**Answer:** Thread dumps/wait-for graph, application traces/queue/resource state, and JVM/OS metrics such as CPU/GC/JIT/safepoint timing.

## 28. End-of-lesson checklist

- **Deadlock ≠ BLOCKED ≠ WAITING**; these terms represent different layers of information.
- A single waiter→owner edge is not yet a deadlock; look for a **cycle**.
- **Thread.State** does not map 1–1 to native OS thread states.
- WAITING on an idle queue, join, or latch is usually valid.
- **Thread.sleep does not release monitors** and creates no synchronization.
- **Object.wait releases the receiver monitor** and reacquires it before returning.
- **Intrinsic synchronized is reentrant**; nesting the same lock does not self-deadlock.
- **ReentrantLock** waits may appear as WAITING/TIMED_WAITING, not necessarily BLOCKED.
- **ThreadMXBean** finds monitor/ownable-synchronizer cycles within its supported scope; null does not prove the whole system is live.
- **JVM GC/JIT/runtime background threads** can continue operating when application workers are not making progress.
- JIT/GC CPU activity is not proof of the cause of request latency without a timeline.
- **jcmd Thread.print -l** and JFR help observe, but snapshots/events must be interpreted properly.
- **Global lock ordering** is an important measure to prevent circular wait.
- **Missing signals / pool starvation / external DB locks** can hang even when the Java deadlock detector reports nothing.
- Keep lock scope reasonable, avoid slow I/O under a global lock, and have cancellation/timeouts where appropriate.
- After diagnosing, fix the actual cause and re-measure throughput/p99/liveness, rather than only changing JVM flags.

### Official documentation

- **Java SE 17 — Thread.State enum:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- **Java SE 17 — Thread API, sleep, join, daemon threads:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- **Java SE 17 — ThreadMXBean deadlock detection:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Java SE 17 — ThreadInfo (lock owner, monitor info):** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- **Java SE 17 — jcmd command and Thread.print:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **Java SE 17 — jstack command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html
- **Java SE 17 — jfr command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- **Java SE 17 — Java Flight Recorder guide:** https://docs.oracle.com/en/java/javase/17/jfapi/
- **Java SE 17 — Object.wait/notify:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html
- **Java SE 17 — LockSupport:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html
- **Java SE 17 — ReentrantLock:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html
- **Java SE 17 — CountDownLatch:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- **JLS SE 17 — Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- **OpenJDK — JEP 444 Virtual Threads (JDK 21):** https://openjdk.org/jeps/444

**Conclusion:** A Java application can have many BLOCKED/WAITING threads, have RUNNABLE GC/JIT threads, and still not be deadlocked. **A real deadlock requires identifying a resource-wait dependency cycle**; whereas temporary monitor waiting, unsignaled conditions, pool starvation, slow I/O, and JVM background work have different causes and remedies. The right process is to **read the thread dump, trace the owner and wait-for graph, and correlate multiple snapshots with the request/GC/JIT/CPU timeline**, then fix the exact lock ordering, signals, pool design, or resource bottleneck instead of diagnosing from a single Thread.State.
