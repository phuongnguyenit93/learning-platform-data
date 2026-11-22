# Practical Exercise: Reading Thread Dumps and Finding Where Threads Are Blocked

## Objective

When a Java application is still alive but a request or a worker does not complete, a **thread dump** shows what each thread is doing and which call stack led it to its current state. This is a JDK diagnostic tool, not a process self-recovery mechanism.

By the end of this lesson, you should be able to execute the workflow: **find the right JVM → capture the dump → locate the affected thread → read its state and stack → identify the monitor/condition being waited on → trace back to the owner or signaler → pinpoint the code location to inspect → verify the fix**.

This exercise uses Java 17+ and JDK tools, without Spring.

## 1. Understanding states and data in a thread dump

A traditional thread dump contains a header for each thread, its state, its stack trace, and depending on the tool/version, monitor or synchronizer information.

| State | What it usually means | What to do |
|---|---|---|
| **RUNNABLE** | Eligible to run; may also be inside a native/I/O call. | Inspect the stack, CPU usage, and I/O information. |
| **BLOCKED** | Waiting to acquire a synchronized **object monitor**. | Find the monitor ID and the thread holding it. |
| **WAITING** | Waiting indefinitely in wait, join, park, latch, or future. | Find who sends the signal or completes the task. |
| **TIMED_WAITING** | Waiting with a timeout, such as sleep or timed park. | Check the deadline and post-timeout behavior. |
| **NEW** | Thread has not started yet. | Check the lifecycle. |
| **TERMINATED** | Thread has finished. | Check errors/lifecycle if relevant. |

**BLOCKED does not by itself prove a deadlock.** It can be normal contention: one thread holds the monitor for a few milliseconds while another temporarily waits. Similarly, **WAITING is not necessarily an incident**; a worker waiting on an empty queue may be completely by design.

A common point of confusion: **ReentrantLock.lock()** typically waits via **LockSupport.park()**, so it can appear in the **WAITING** state instead of **BLOCKED**. You must read the stack to identify the waiting primitive.

### Abbreviated dump example (illustrative, not fixed verbatim output)

~~~text
"worker-B" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at sample.Cache.refresh(Cache.java:81)
    - waiting to lock <0xABC> (a java.lang.Object)

"worker-A" ... java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.CountDownLatch.await(...)
    at sample.Cache.hold(Cache.java:57)
    - locked <0xABC> (a java.lang.Object)
~~~

From these two excerpts, **worker-B** cannot acquire the monitor identified as **0xABC**, while **worker-A** is holding that monitor and waiting on a latch. The blocked location for B is **Cache.java:81**; the deeper cause may lie at **Cache.java:57** or in the thread responsible for opening the latch. There is not yet enough evidence of a deadlock cycle.

## 2. Capturing a thread dump from the right process

First, list the JVMs visible to the tool:

~~~bash
jcmd -l
~~~

Match the PID against the main class, launch arguments, and environment. Inside containers, PID namespaces, attach permissions, and JRE-only images can affect tool availability.

Capture a dump on Java 17+ with HotSpot:

~~~bash
jcmd <PID> Thread.print -l
~~~

**<PID>** is a placeholder; replace it with the actual PID number. The **-l** option requests printing additional lock information from java.util.concurrent supported by the tool. You can save the output to a file using terminal redirection. If **jstack** is available on the machine, you can also use:

~~~bash
jstack -l <PID>
~~~

Check the capabilities of the target JVM with:

~~~bash
jcmd <PID> help
~~~

If the issue is not occurring at the moment of capture, the dump might not contain the state you are looking for. For prolonged issues, take **2–3 dumps** spaced at an appropriate interval and compare the same threads/stacks. Do not scan threads continuously per request because collecting data has overhead.

### Java 21+ and virtual threads

When an application uses virtual threads, JDK 21+ provides the command:

~~~bash
jcmd <PID> Thread.dump_to_file -format=text threads.txt
jcmd <PID> Thread.dump_to_file -format=json threads.json
~~~

This dump format supports large numbers of virtual threads, but its structure and lock details differ from **Thread.print -l**, especially in early JDK releases. **Do not apply Java 21+ Thread.dump_to_file to Java 17** without checking the version/support of the target JVM.

## 3. Exercise A: reproducing a blocked-thread scenario

We create four threads:

- **demo-owner** holds the **gate** monitor while waiting on a CountDownLatch.
- **demo-blocked** attempts to enter synchronized(gate), so it must wait for demo-owner.
- **demo-waiting** waits on a separate latch and does not contend for gate.
- **demo-sleeping** sleeps for a fixed duration.

**This is an intentional practice exercise, not production-ready sample code.** Main has a path to open the latches, so this is not an immutable deadlock.

Create the file **DumpExercise.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public final class DumpExercise {
    static void hold(Object gate, CountDownLatch entered,
                     CountDownLatch release) {
        synchronized (gate) {
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }

    static void enter(Object gate) {
        synchronized (gate) {
            // Runs only after acquiring the monitor.
        }
    }

    static void waitOnLatch(CountDownLatch signal) {
        try {
            signal.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        Object gate = new Object();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);
        CountDownLatch releaseWaiter = new CountDownLatch(1);

        Thread owner = new Thread(
                () -> hold(gate, entered, releaseOwner), "demo-owner");
        Thread blocked = new Thread(
                () -> enter(gate), "demo-blocked");
        Thread waiting = new Thread(
                () -> waitOnLatch(releaseWaiter), "demo-waiting");
        Thread sleeping = new Thread(() -> {
            try {
                Thread.sleep(30_000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "demo-sleeping");

        owner.start();
        entered.await();
        blocked.start();
        waiting.start();
        sleeping.start();

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        long[] ids = {owner.getId(), blocked.getId(),
                      waiting.getId(), sleeping.getId()};

        try {
            ThreadInfo[] snapshot = null;
            boolean ready = false;
            for (int attempt = 0; attempt < 200; attempt++) {
                snapshot = mx.getThreadInfo(ids, 16);
                ready = snapshot[0] != null && snapshot[1] != null
                        && snapshot[2] != null && snapshot[3] != null
                        && snapshot[0].getThreadState() == Thread.State.WAITING
                        && snapshot[1].getThreadState() == Thread.State.BLOCKED
                        && snapshot[2].getThreadState() == Thread.State.WAITING
                        && snapshot[3].getThreadState() ==
                           Thread.State.TIMED_WAITING;
                if (ready) break;
                Thread.sleep(10);
            }

            if (!ready) {
                System.out.println("States not observed before timeout");
                return;
            }

            for (ThreadInfo t : snapshot) {
                String ownerName = t.getLockOwnerName();
                System.out.println(t.getThreadName() + ": "
                        + t.getThreadState() + "; owner="
                        + (ownerName == null ? "-" : ownerName));
            }

            if (args.length == 1 && "--capture".equals(args[0])) {
                System.out.println("Capture now; press Enter to release.");
                System.in.read();
            }
        } finally {
            releaseOwner.countDown();
            releaseWaiter.countDown();
            sleeping.interrupt();
            owner.join();
            blocked.join();
            waiting.join();
            sleeping.join();
        }
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 DumpExercise.java
java DumpExercise
~~~

Output when the expected states are observed:

~~~text
demo-owner: WAITING; owner=-
demo-blocked: BLOCKED; owner=demo-owner
demo-waiting: WAITING; owner=-
demo-sleeping: TIMED_WAITING; owner=-
~~~

In a heavily loaded environment or if the states are not caught in time, the program prints **States not observed before timeout**. Instead of using Thread.sleep to guess when the worker has acquired the monitor, the program uses the **entered** latch to know when owner has entered the synchronized block. The **finally** block releases the latches, interrupts the sleeper, and joins the workers once main reaches this block.

**Why is owner WAITING while still holding the lock?** **CountDownLatch.await()** does not automatically release outer synchronized monitors. Therefore, while owner waits on the latch, blocked still cannot acquire gate. This differs from **Object.wait()**, which releases the monitor being waited on according to its API contract.

### Capturing a dump from another terminal

First terminal:

~~~bash
java DumpExercise --capture
~~~

When the screen prints **Capture now; press Enter to release.**, keep the program open. Second terminal:

~~~bash
jcmd -l
jcmd <PID> Thread.print -l
~~~

Substitute the correct PID of DumpExercise and look for the four thread names. After capturing, press Enter in the first terminal to release the latches and exit. If the 30-second sleep expires or stdin closes/reaches EOF, the states may change before capture; re-run if needed.

## 4. Exercise B: finding the exact BLOCKED location

### Step 1: locate the suspect thread

Find **demo-blocked** in the text dump. Example abbreviated display:

~~~text
"demo-blocked" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at DumpExercise.enter(DumpExercise.java:20)
    - waiting to lock <0xABC> (a java.lang.Object)
~~~

**Line number 20 and address 0xABC here are examples only.** The important line is the application frame **DumpExercise.enter(...)**, which points to:

~~~java
static void enter(Object gate) {
    synchronized (gate) { // Point where the monitor is requested.
    }
}
~~~

This is the **blocked location**, not necessarily the **root cause**. Removing synchronized without checking data invariants can introduce a race condition.

### Step 2: find the monitor and its owner

Search the dump for a thread with a **- locked** line sharing the same monitor identifier. In the example, thread **demo-owner** holds the gate monitor inside **DumpExercise.hold(...)**. Relying only on the same class name **java.lang.Object** is insufficient, because multiple Object instances can be distinct monitors.

In the Java API, **ThreadInfo.getLockOwnerName()** on demo-blocked returns **demo-owner** at the moment of observation. Dependency diagram:

~~~text
demo-blocked waits for gate
        |
        v
demo-owner holds gate
        |
        v
demo-owner waits for releaseOwner latch
        |
        v
main calls releaseOwner.countDown()
~~~

This evidence shows that owner is what needs deeper inspection. In the exercise, main opens the latch on exit; if in production code the signal had to be sent by the blocked thread itself, an unresolvable dependency cycle could arise.

### Step 3: inspect a WAITING thread with no owner

**demo-waiting** has **owner=-** yet is still WAITING. This is waiting on a latch, not waiting on a monitor with an explicit owner. You must locate the method calling **countDown()** rather than concluding "there is no issue".

The same applies to **Future.get()**, **CompletableFuture.join()**, **Condition.await()**, or I/O: the source that allows progress may be a task, a callback, or an external system, not necessarily a thread holding a monitor.

## 5. Table for identifying wait sources from the stack

| Indicator | What to check |
|---|---|
| **BLOCKED**, **waiting to lock** | Find the monitor ID, **locked** in another thread, and the owner's stack. |
| **Object.wait()** | Find the wait condition predicate and the **notify/notifyAll** path. |
| **CountDownLatch.await()** | Find all **countDown()** paths and failure cases before signaling. |
| **Future.get() / join()** | Find the task producing the result, the executor, and the task's dependencies. |
| **LockSupport.park()** | Check frames below to distinguish ReentrantLock, queue, semaphore, or condition. |
| **Thread.sleep()** | Check sleep duration, timeout, retry, and deadline. |
| **RUNNABLE** in socket/file read | May be in native I/O; check I/O timeouts and the peer. |
| **RUNNABLE** looping in computation code | Cross-check CPU usage, multiple dumps, and loop exit conditions. |

Read the stack **from the JDK mechanism down to the nearest application frame**. The **Unsafe.park** frame only says the thread is parked; the application frame or primitive below it reveals the business reason.

## 6. Programmatically retrieving ThreadInfo from ThreadMXBean

**ThreadMXBean** can return thread information directly inside the JVM. In a method that already has **mx** and **ids** as in Exercise A, the following prints more detail:

~~~java
ThreadInfo[] details = mx.getThreadInfo(ids, 32);
for (ThreadInfo t : details) {
    if (t == null) continue;
    System.out.printf("thread=%s id=%d state=%s%n",
            t.getThreadName(), t.getThreadId(), t.getThreadState());
    System.out.printf("waiting=%s owner=%s (%d)%n",
            t.getLockInfo(), t.getLockOwnerName(), t.getLockOwnerId());
    for (StackTraceElement frame : t.getStackTrace()) {
        System.out.println("    at " + frame);
    }
}
~~~

This is a **snippet**, not a standalone program. **getThreadInfo(ids, 32)** retrieves up to 32 stack frames; threads that have terminated may yield **null** elements. If you want the list of locks a thread is holding, use the corresponding overload with boolean parameters and check JVM support:

~~~java
boolean monitorSupport = mx.isObjectMonitorUsageSupported();
boolean synchronizerSupport = mx.isSynchronizerUsageSupported();
ThreadInfo[] richer = mx.getThreadInfo(
        ids, monitorSupport, synchronizerSupport);
~~~

Then read **getLockedMonitors()** and **getLockedSynchronizers()**. Do not assume the default **getThreadInfo(ids, maxDepth)** already returns all of these lists.

### Finding deadlocks

~~~java
// Illustrative snippet placed inside a method:
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
long[] deadlocked = mx.isSynchronizerUsageSupported()
        ? mx.findDeadlockedThreads()
        : mx.findMonitorDeadlockedThreads();
if (deadlocked != null) {
    System.out.println("Deadlocked: " + deadlocked.length);
}
~~~

**findMonitorDeadlockedThreads()** detects cycles of synchronized object monitors; **findDeadlockedThreads()** can also include ownable synchronizers such as ReentrantLock if supported by the JVM. Finding none **does not prove** the application has no hang caused by latches, futures, I/O, or other logical deadlocks.

## 7. Distinguishing contention, deadlock, and starvation

**Contention:** thread A holds a monitor briefly; thread B is BLOCKED but then proceeds. A thread dump taken at the exact moment of contention can look alarming, but if throughput/latency are acceptable, it may not be an incident.

**Deadlock:** thread A holds LOCK-1 and waits for LOCK-2 held by B; B holds LOCK-2 and waits for LOCK-1 held by A:

~~~text
A -> waits for B -> waits for A
~~~

There is a dependency cycle over the same locks. You must match lock identities and thread stacks to conclude this. Common fixes are enforcing a consistent lock acquisition order or removing unnecessary nested locking.

**Starvation:** worker A waits on a future for task B, but B is sitting in an executor's queue where all workers are busy waiting. There may be no monitor ownership cycle for the JVM to report as a deadlock. You must inspect task queues, worker counts, dependencies, and blocking-wait design.

**Livelock:** multiple threads keep running/changing state without making progress. A single dump is usually not enough; observations over time are needed.

## 8. Investigation workflow from real failure to code fix

1. **Record the symptom:** which request/job is stuck, wait duration, PID, JDK version, and running build.
2. **Capture dumps at the right time:** while the symptom is active, using the right tool for platform/virtual threads.
3. **Locate relevant threads:** by name, stack methods, log correlation, or task ID if available.
4. **Identify application frames:** find where synchronized, await, join, lock, I/O read, or CPU loop code is called.
5. **Trace the waited resource:** if BLOCKED, find the monitor ID; if WAITING, find the latch/future/queue condition.
6. **Trace the owner or signal source:** which thread holds the lock, which task will complete the future, who calls countDown?
7. **Build the dependency graph:** is there a wait cycle or just one long wait chain?
8. **Cross-check additional evidence:** multiple dumps, logs, per-thread CPU, queue depth, throughput.
9. **Fix the root cause:** shorten lock hold times, use consistent lock ordering, avoid blocking waits while holding needed resources.
10. **Verify:** write tests with timeouts, force interleaving with latches, test under contention, and verify data correctness.

### Example: do not hold a monitor while waiting on an unnecessary result

Dangerous pattern (snippet assuming variables are already declared):

~~~java
synchronized (sharedLock) {
    Result value = future.join();
    updateSharedState(value);
}
~~~

If the task completing the future needs sharedLock, a dependency cycle can occur. If invariants allow, wait outside and only protect the update:

~~~java
Result value = future.join();
synchronized (sharedLock) {
    updateSharedState(value);
}
~~~

**Both excerpts are snippets, not standalone runnable files.** You must re-evaluate invariants: state may change between waiting and acquiring the lock. Do not simply delete synchronized to make threads less BLOCKED and introduce a new race condition.

With ReentrantLock, release the lock in finally once acquired:

~~~java
lock.lock();
try {
    doProtectedWork();
} finally {
    lock.unlock();
}
~~~

**tryLock(timeout, unit)** can avoid waiting indefinitely, but failure and cleanup must be handled properly.

## 9. Practice questions and answers

### Scenario A

~~~text
"job-B" BLOCKED
    at app.Service.save(Service.java:80)
    - waiting to lock <0x123>

"job-A" WAITING
    at java.util.concurrent.CompletableFuture.join(...)
    at app.Service.flush(Service.java:54)
    - locked <0x123>
~~~

**Answer:** B is blocked at **save:80**; A holds the monitor while waiting on a future at **flush:54**. You need to find the task completing the future and check whether it depends on B or this monitor. There is not yet enough evidence to conclude a deadlock.

### Scenario B

~~~text
"consumer" WAITING
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.ArrayBlockingQueue.take(...)
    at app.Consumer.run(Consumer.java:31)
~~~

**Answer:** this may simply be an empty queue and a consumer waiting legitimately. If the system reports that data was sent, check the right queue, put/offer paths, producer, and lifecycle.

### Scenario C

~~~text
"task-A" BLOCKED, waiting to lock <LOCK-B>, locked <LOCK-A>
"task-B" BLOCKED, waiting to lock <LOCK-A>, locked <LOCK-B>
~~~

**Answer:** A waits for B and B waits for A on two locks, which is a clear sign of deadlock if the lock IDs correspond accurately within a single dump. Find the two opposite lock orders in the source code and unify the order.

## 10. Common mistakes

1. **BLOCKED means deadlock.** False: a cycle must be proven; many cases are just contention.
2. **WAITING is always a bug.** False: an empty queue or waiting for a valid event can be normal.
3. **Only looking at the affected thread.** Ignoring the lock owner or signal source leads to fixing the wrong place.
4. **Confusing the same class with the same lock object.** You must match monitor identity.
5. **RUNNABLE always uses CPU.** False: this state can appear during native I/O.
6. **Reading only Unsafe.park.** You must trace the caller/primitive and application frames.
7. **A null owner means no waiting condition.** False for latches, futures, and many waits.
8. **No deadlock found via MXBean means the application is healthy.** False because detection scope is limited.
9. **Comparing a dump against source from a different build.** Method names and line numbers may differ.
10. **A single dump is enough to prove a prolonged condition.** You must compare across time and telemetry.
11. **Fixing by adding sleep or threads.** This can mask symptoms without removing the faulty dependency.
12. **Forgetting timeouts and cleanup in tests.** Concurrency tests can hang the entire CI pipeline indefinitely.
13. **Capturing dumps continuously under load or sharing them without control.** This adds overhead and can expose internal information.
14. **Using tools for the wrong JDK or thread type.** Check help and virtual thread support.

## 11. Investigation checklist

- [ ] Correct PID, instance, JDK, build.
- [ ] Dump captured while the symptom is present.
- [ ] Identify the blocked thread and application frames.
- [ ] If BLOCKED: find the monitor ID and the holding thread.
- [ ] If WAITING: find the latch, future, queue, condition, or I/O.
- [ ] Trace owner/signal source to the root cause.
- [ ] Determine whether there is a deadlock cycle or legitimate wait/contention.
- [ ] Cross-check additional dumps, logs, and metrics.
- [ ] Fix the code while preserving invariants.
- [ ] Test with timeouts and cleanup.

**Quick reading mnemonic:** **thread → state → stack → lock/wait condition → owner or signal producer → root cause → test the fix**.

## 12. JDK documentation

- [Thread.State (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html)
- [ThreadMXBean (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadInfo (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [CountDownLatch (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [jcmd (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Virtual Threads (Java 21)](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Troubleshoot Process Hangs and Loops](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-process-hangs-and-loops.html)
