# JDK 21 vs. JDK 24+: Standard synchronized No Longer Causes Legacy Pinning

## Objectives

**JDK 24 implements JEP 491 — Synchronize Virtual Threads without Pinning.** This change allows a virtual thread going through Java's monitor mechanism (including `synchronized`, waiting to acquire a monitor, and `Object.wait()`) to yield its carrier thread in blocking situations that previously easily caused pinning in JDK 21. **There is no change to the syntax or mutual exclusion semantics of `synchronized`.**

This lesson is for general Java concurrency, using only the JDK and Java SE. Key takeaways:

1. Distinguish between **virtual thread**, **carrier**, **mount/unmount**, **blocking**, **pinning**, and **monitor contention**.
2. Understand the exact performance issue in JDK 21 when a virtual thread blocks inside `synchronized`, and what JEP 491 fixes starting in JDK 24.
3. Know which cases can still pin even on JDK 24+, how to read JFR, and how to decide whether to keep `synchronized` or switch to `ReentrantLock`.
4. Run a **Java 21+** program yourself to compare results across JDK versions without external libraries.

## 1. Virtual Threads and Carriers: When Does Pinning Occur?

Since Java 21 (JEP 444), a virtual thread is a `Thread` managed by the JVM, suited for tasks that frequently **wait** on I/O or synchronization signals. A virtual thread does not hold onto a single OS thread for its entire lifetime. When running, a virtual thread is **mounted** onto a scheduler platform thread, called a **carrier**; when waiting at a JVM-supported blocking point, it can **unmount**, returning the carrier to execute another virtual thread.

~~~text
                  When runnable
Virtual thread A ──────────────► Carrier #1 ─► CPU
       │                              │
       └─ blocking I/O / sleep ───────┤
          (can unmount)               └─ Carrier #1 runs virtual thread B

If pinned while blocking:
Virtual thread A ──────────────► Carrier #1 ─► waits with A
                                               (cannot be used for B)
~~~

**Pinning** occurs when a virtual thread must remain attached to its carrier at the moment it performs a blocking operation. The concerning impact is **occupying an OS thread just to wait** while many other virtual threads need a carrier. This situation can reduce throughput and scalability, though it **does not by itself make program results incorrect**.

Distinguish between three phenomena:

- **Blocked virtual thread:** the task is waiting; completely normal if the carrier is released.
- **Pinned virtual thread:** the task is waiting and the carrier cannot be released; wastes platform thread resources.
- **Monitor contention:** multiple threads compete for the same lock; even without pinning a carrier, threads must still wait for their turn to enter the critical section. JDK 24 does not turn a monitor into a lock that allows parallel execution.

Virtual threads do not make a CPU-bound section run faster. Their strength is the ability to serve many primarily I/O-waiting tasks with a limited number of carriers.

## 2. JDK 21: Why Can synchronized Cause Pinning?

On JDK 21, when a virtual thread **is inside a `synchronized` block or method** and calls a blocking operation such as `Thread.sleep()`, `BlockingQueue.take()`, or an I/O call capable of yielding the carrier, the JVM usually **cannot unmount the virtual thread** because it is holding a monitor. The carrier is held for the duration of the wait.

~~~java
private final Object monitor = new Object();

void process() throws InterruptedException {
    synchronized (monitor) {
        // Illustrates a long-waiting operation.
        Thread.sleep(200);
    }
}
~~~

This is a **code snippet inside a class**, not a standalone runnable program. On JDK 21, if `process()` is called from a virtual thread and `Thread.sleep(200)` actually waits, it can hold the carrier for about 200 ms. Many independent requests using **different monitors** that all block inside synchronized can still occupy many carriers simultaneously.

There are several common misconceptions:

- `synchronized` that only executes a few assignments or in-memory calculations **is not a scary scenario**: what matters is **long and frequent** blocking inside a monitor.
- Waiting on a lock due to contention is not synonymous with pinning; you need to look at whether **unmounting** is possible during that wait.
- Pinning does not bypass the monitor: `synchronized` still guarantees mutual exclusion, the appropriate happens-before relationship between unlock/lock, and Java monitor reentrancy.
- Pinning is different from deadlock. Deadlock is a cycle of lock dependencies that cannot make progress; JEP 491 does not automatically fix deadlocks, lost notifications, or race conditions.

### How to Reduce Pinning on JDK 21

If profiling shows that a `synchronized` region **frequently holds a carrier during long waits**, you can:

1. **Move I/O or waiting operations outside the critical section** when data invariants allow.
2. **Shorten the monitor hold duration** and re-verify atomicity.
3. **Use `ReentrantLock`** for the specific region that needs protection when blocking inside cannot be avoided: the waiting mechanism of AQS/`LockSupport` supports virtual-thread-friendly parking, avoiding the *monitor-specific* limitation present on JDK 21.
4. **Upgrade the JDK to 24+** if it fits your product lifecycle and testing, because JEP 491 directly resolves the Java monitor source of pinning.

Do not mechanically replace every `synchronized` with `ReentrantLock`: changing the lock can entail changes to how `wait/notify`, wait conditions, interrupt handling, unlock rules, and code complexity are managed.

## 3. JDK 24+: What Exactly Does JEP 491 Change?

JEP 491 was introduced in **JDK 24**. Normal monitor usage no longer necessarily forces a virtual thread to hold its carrier while blocked. The JVM supports **unmounting** virtual threads in the following key scenarios:

| Scenario | JDK 21 | JDK 24+ |
| --- | --- | --- |
| Virtual thread calls `Thread.sleep` or a blocking API inside `synchronized` | Can pin the carrier because a monitor is held | Standard monitors are no longer a reason to pin |
| Virtual thread waits to enter `synchronized` because the lock is held by another thread | Legacy monitor implementation limits can hold the carrier in some wait paths | Monitor mechanism is adjusted to wait while releasing the carrier |
| Virtual thread calls `Object.wait()` while owning a monitor | Can pin the carrier due to the monitor | Can wait while unmounting the carrier in normal execution paths |
| Critical section performs only short computation | Usually not significantly affected by pinning | Still needs the monitor to guarantee mutual exclusion |
| Blocking in a native/foreign frame | Can still pin | **Can still pin**; JEP 491 does not eliminate all causes |

To be precise: **JDK 24+ eliminates pinning caused by standard synchronized**, rather than claiming a virtual thread will *never* be pinned. For example, if a call inside synchronized also passes through a problematic native/foreign frame, it can still be pinned for **another reason**.

### Sequence Illustration

~~~text
Example: virtual thread executes synchronized(lock) { Thread.sleep(250); }

JDK 21:
  A is mounted on carrier-1
  A enters monitor lock
  A sleeps 250 ms
  carrier-1 is held while A sleeps (monitor-related pinning)
  A wakes up, exits monitor, finishes

JDK 24+:
  A is mounted on carrier-1
  A enters monitor lock
  A sleeps 250 ms, is unmounted (in the standard case)
  carrier-1 can run B
  A is ready, is remounted, continues preserving the same monitor logic as before
  A exits monitor, finishes
~~~

**Unmounting** does not mean `lock` is released while `A` sleeps. With `Thread.sleep` inside `synchronized`, A still **holds the monitor**; other threads wanting to enter the same monitor must wait for A to exit the critical section. By contrast, `Object.wait()` inherently has the semantics of **temporarily releasing the monitor, waiting, and then reacquiring the monitor** upon waking; this rule remains unchanged.

JEP 491 improves carrier utilization; it **does not** remove the serialization of critical sections, and it **does not** increase throughput if the lock itself or a downstream service is the bottleneck.

## 4. Complete Example Running on Java 21 and Java 24+

Create the file **`MonitorPinningDemo.java`**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class MonitorPinningDemo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    private static void pause() {
        try {
            Thread.sleep(250);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
    }

    private static void runWithMonitor() {
        synchronized (MONITOR) {
            pause();
        }
    }

    private static void runWithReentrantLock() {
        LOCK.lock();
        try {
            pause();
        } finally {
            LOCK.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual().name("pinning-demo").start(() -> {
            System.out.println("virtual=" + Thread.currentThread().isVirtual());
            runWithMonitor();
            System.out.println("monitor finished");
            runWithReentrantLock();
            System.out.println("lock finished");
        });
        worker.join();
    }
}
~~~

Run with **any JDK 21+**:

~~~bash
javac MonitorPinningDemo.java
java MonitorPinningDemo
~~~

Output of the program itself (excluding JVM/JFR startup logs if diagnostic tools are enabled):

~~~text
virtual=true
monitor finished
lock finished
~~~

The same program produces the same output on JDK 21 and JDK 24+, because **the lock semantics and results of both calls do not change**. The difference to verify using **JDK Flight Recorder (JFR)** or performance measurement under representative load is: on JDK 21, sleeping inside `synchronized` typically generates a pinning event; on JDK 24+, holding a monitor alone no longer causes this kind of pinning.

Because it creates only one virtual thread, this program **illustrates the mechanism and how to measure it**, not a benchmark to claim how much higher throughput JDK 24 achieves. Actual sleep duration and events may vary depending on the JDK, JFR settings, and environment.

## 5. Verifying Pinning with JFR

JFR records a `jdk.VirtualThreadPinned` event when a virtual thread is pinned to a carrier for longer than a configured threshold. On the JDK releases mentioned in the official documentation, this event is enabled by default with a threshold typically set to **20 ms**. Measure with a sufficiently long workload and run the same test on two runtimes with **clearly identified version/vendor/build**.

Run the program with JFR (first using the `java` command of JDK 21, then JDK 24+):

~~~bash
java -version
java -XX:StartFlightRecording=filename=pinning.jfr,dumponexit=true,settings=profile MonitorPinningDemo
jfr print --events jdk.VirtualThreadPinned pinning.jfr
~~~

The `java -XX:StartFlightRecording=...` command may print additional JFR startup logs. The `pinning.jfr` file is created when the recording finishes. Use separate filenames for each JDK if you want to compare them side by side.

**Reasonable expectations:**

- **JDK 21:** When `runWithMonitor()` sleeps for about 250 ms inside the monitor, you may see `jdk.VirtualThreadPinned` associated with `MonitorPinningDemo` and the `Thread.sleep` call path. `runWithReentrantLock()` does not cause pinning *solely from the monitor*, because it does not use a Java monitor for that lock.
- **JDK 24+:** A standard `Thread.sleep` inside `synchronized` will no longer generate a monitor-caused pinned event under JEP 491. **This does not mean JFR will have zero pinning events** when running other complex programs.

On **JDK 21**, there is also a quick diagnostic mode:

~~~bash
java -Djdk.tracePinnedThreads=full MonitorPinningDemo
~~~

If blocking is detected inside a monitor region, the JVM may print a stack trace with monitor information. The `-Djdk.tracePinnedThreads` option is a diagnostic tool tied to the legacy implementation; **do not use it as your primary check on JDK 24+**, where this tool has been removed. Prefer JFR for newer releases.

### Reading Results Correctly

A JFR trace worth inspecting should include at least: the **VirtualThreadPinned** event, **duration**, stack trace (call path), and, if supported by the runtime, **blockingOperation**, **pinnedReason**, and **carrierThread**. On newer JDKs, the reason field helps distinguish native/VM frames from other situations.

**Seeing no events** has several possible explanations:

- There is no pinning.
- Pinning is shorter than the configured threshold.
- The workload did not hit the code path that causes pinning, or the task finished before the recording.
- Event/stack trace/recording settings do not reflect the running workload.

Do not conclude "no pinning" just because a single local run had no events. For real systems, collect JFR under representative load and cross-reference carrier count, queue latency, throughput, and the blocking operations actually occurring.

Use `jcmd` to generate a thread dump when you need to inspect waiting virtual threads:

~~~bash
jcmd <PID> Thread.dump_to_file -format=json threads.json
~~~

Replace `<PID>` with the JVM process ID; the dump helps show waiting threads and stacks, but **does not replace** JFR pinning duration data. `jcmd` requires the matching JVM, appropriate permissions, and attach capability.

## 6. Cases Where JDK 24+ Can Still Pin

JEP 491 targets pinning **caused by Java monitors**. The following paths still require investigation:

| Potential source | Why it is still an issue | Mitigation approach |
| --- | --- | --- |
| **JNI/native methods** | A native frame can prevent a virtual thread from unmounting when blocking occurs | Profile the native boundary; avoid long waits on native paths or use an appropriate architecture |
| **Foreign Function & Memory API / foreign calls** | Transferring control into native code via FFM can still impose carrier constraints | Check duration/blocking and whether that work can be placed on another execution path |
| **Class initialization / acquiring class initialization lock** | Certain JVM paths serving class initialization and waiting for class initialization can hold the carrier | Pre-initialize critical resources; inspect traces/JFR |
| **Specific forms of I/O or non-unmountable JVM operations** | Depends on the API path and runtime; not every wait operation is virtual-thread-aware | Measure with JFR and observe actual carrier time |

The existence of these sources does not mean every section with JNI, file I/O, or class loading **will** pin. You need to look at the **actual execution path and blocking operation**. Similarly, JFR reporting `jdk.VirtualThreadPinned` in a program using `synchronized` on JDK 24+ **does not prove** JEP 491 failed: the cause may be an underlying native/VM frame.

## 7. Why Careful synchronized Design Is Still Needed

**Not pinning the carrier** only solves one of the costs under high concurrency. The example below still has a bottleneck on both JDK 21 and JDK 24+:

~~~java
private final Object shared = new Object();

void slowCriticalSection() throws InterruptedException {
    synchronized (shared) {
        // All callers using the same "shared" object still have to wait for each other sequentially.
        Thread.sleep(500);
    }
}
~~~

With many virtual threads competing for the **same shared**, only one thread enters the critical section at a time, creating a large queue even when waiting threads do not hold a carrier. If business requirements do not require holding the lock during the wait, place the wait outside the monitor and lock only the state update:

~~~java
private final Object shared = new Object();
private int completed;

void improvedStructure() throws InterruptedException {
    Thread.sleep(500); // Wait outside the monitor if protection by shared is not needed.
    synchronized (shared) {
        completed++;
    }
}
~~~

Both examples are **class member snippets**, not standalone programs. Moving a statement outside the monitor is **only valid when business invariants/atomicity are still preserved**: for example, if the I/O result and state update must be locked together, splitting them can introduce a race.

For real-world throughput, also monitor:

- **Critical section length** and monitor contention.
- **Downstream connection/resource counts** such as database pool, HTTP connection cap, and API rate limits.
- **Number of waiting tasks** and throughput, not just virtual thread count.
- **Native blocking** and scheduler starvation.
- **Memory** of waiting tasks and `ThreadLocal` variables newly created per task.

Virtual threads generally **do not need fixed-size thread pools**. When you need to limit access to scarce resources, use direct bounds such as a `Semaphore` or connection pool limits rather than artificially grouping virtual threads into a small pool.

## 8. Is ReentrantLock Still Needed in JDK 24+?

**Yes**, but the choice is now based on **lock features and code structure**, not a rule of "virtual threads must always avoid synchronized."

| Requirement | `synchronized` | `ReentrantLock` |
| --- | --- | --- |
| Short critical section needing simple mutual exclusion | Very suitable; auto-unlocks when exiting the block | Also works, but must `unlock` in `finally` |
| JDK 21, long blocking inside monitor and profiling shows pinning | May need refactoring | Can avoid monitor-caused pinning |
| JDK 24+, blocking inside standard monitor | No longer pins due to monitor under JEP 491 | Not mandatory to replace solely to avoid legacy pinning |
| Non-blocking lock attempt `tryLock()` | No direct equivalent method | Yes |
| Interruptible lock acquisition `lockInterruptibly()` | Entering a monitor has no direct equivalent API | Yes |
| Multiple independent wait conditions | `wait/notify/notifyAll` on the same monitor | `Condition` supports multiple wait sets |
| Optional fairness | No fairness constructor | Has optional fairness policy |

Example of switching locks to support a specific requirement (runnable inside a class containing the `lock` field):

~~~java
import java.util.concurrent.locks.ReentrantLock;

private final ReentrantLock lock = new ReentrantLock();

void updateWithInterruptibleLock() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        // Update shared state or task that must be protected.
    } finally {
        lock.unlock();
    }
}
~~~

This is a **class snippet**, which cannot compile standalone because the field/method are placed at the top level. `ReentrantLock` does not inherently make operations inside faster. Regardless of the lock type used, long critical sections and contention still affect latency. Switching `wait/notify` to `Condition.await/signal` requires redesigning the condition loop and signaling properly, not simply renaming the API.

## 9. Approach When Upgrading an Application from JDK 21 to JDK 24+

A sensible verification roadmap:

1. **Lock down the runtime version** of each environment, not just `sourceCompatibility` or `--release`. Running on JDK 21 still carries JDK 21's pinning limitations, even if the code was compiled with a different toolchain.
2. **Capture a baseline on JDK 21**: JFR `jdk.VirtualThreadPinned`, throughput, p95/p99 latency, and active carrier count under a representative workload.
3. **Test the same workload on JDK 24+**: keep code, workload, and comparison configuration consistent; verify that standard monitor-caused events decrease or disappear.
4. **Investigate remaining events**: inspect stack traces, native/VM causes, class initialization, and actual I/O paths before modifying code.
5. **Review old workarounds**: cases where `synchronized` was replaced with `ReentrantLock` *solely to avoid pinning* may no longer be necessary for performance on 24+, though there is no obligation to revert working code.
6. **Check the next bottleneck**: the same monitor still serializes access, database pools still have limits, and CPU-bound tasks are not sped up by virtual threads.

Do not optimize solely by a single `jdk.VirtualThreadPinned` number: pinning may be gone while contention or downstream limits still dominate overall throughput.

## 10. Common Pitfalls

1. **"JDK 24 makes synchronized no longer need locking."** False. Mutual exclusion, visibility/happens-before, and reentrancy remain unchanged.
2. **"A blocked virtual thread means it is pinned."** False. Being blocked while unmounted is how virtual threads work efficiently.
3. **"JDK 24 eliminates all pinning."** False. Native/foreign and certain VM paths can still pin.
4. **"If synchronized is in the stack, a pinning event on JDK 24 must be caused by the monitor."** False. You need to read **pinnedReason/stack trace**; the monitor may just be an outer call frame.
5. **"Upgrading the JDK will fix deadlocks."** False. Deadlocks, lock ordering, and races are separate correctness issues.
6. **"No JFR events means no pinning."** Not necessarily. Thresholds, recording start time, and workload can obscure them.
7. **"You must replace all synchronized with ReentrantLock when using virtual threads."** False, especially from JDK 24+ onward. Even on JDK 21, only regions that actually cause significant pinning should be changed.
8. **"Since it doesn't pin anymore, you can hold a monitor across arbitrary long I/O."** False. The monitor still blocks other threads wanting to access the same data.
9. **"Virtual threads make individual requests faster."** Not directly. The primary goal is scalability when many requests are waiting on I/O.
10. **"Verifying with the compile-time JDK is enough."** Not enough. Monitor pinning behavior depends on the **runtime JVM** version and must be measured at runtime.

## 11. Self-Check Questions

**Question 1.** On JDK 21, why can `synchronized(lock) { Thread.sleep(300); }` reduce scalability when there are many virtual threads?

Because while holding a monitor, a virtual thread cannot unmount under the legacy mechanism; each blocking call holds a carrier/OS thread. If the number of such operations is large and frequent, the scheduler has fewer free carriers to run other tasks.

**Question 2.** With the same code on JDK 24+, can another thread enter the same monitor while the first thread is sleeping?

**No.** JEP 491 allows releasing the *carrier*, not releasing the `synchronized` *monitor* while sleeping. Other threads must wait until the monitor is unlocked.

**Question 3.** On JDK 24+, why can native blocking still cause JFR to record `VirtualThreadPinned`?

Because JEP 491 resolves pinning caused by Java monitors and cannot guarantee safe unmounting across all native/foreign or VM frames.

**Question 4.** When should you keep `ReentrantLock` even after upgrading to JDK 24?

When you need `tryLock`, `lockInterruptibly`, `Condition`, fairness, or when the existing structure is already stable. There is no requirement to change everything back to `synchronized`.

**Question 5.** Why does the absence of `VirtualThreadPinned` not guarantee that throughput will increase?

Because the program can still be limited by CPU, contention on the same monitor, connection pools, rate limits, memory, or downstream services.

## Official References

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): foundations of virtual threads, carriers, and pinning in early releases.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): monitor change mechanism introduced in JDK 24.
- [Oracle — Virtual Threads on JDK 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): legacy `synchronized` limitations, `ReentrantLock`, JFR, and `jdk.tracePinnedThreads`.
- [Oracle — Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html): confirms JEP 491 is included in JDK 24.
- [Oracle — Virtual Threads on JDK 24](https://docs.oracle.com/en/java/javase/24/core/virtual-threads.html): remaining pinning from native/foreign, JFR, and guidance on using virtual threads.
- [OpenJDK — JEP 491 Implementation RFR](https://mail.openjdk.org/pipermail/core-libs-dev/2024-November/134311.html): the three key change paths—unmounting while holding a monitor, waiting to enter a monitor, and `Object.wait()`.

**Technical conclusion:** on **JDK 21**, long blocking inside `synchronized` is a source of pinning that needs to be measured and potentially addressed. Starting in **JDK 24**, JEP 491 fixes that mechanism, allowing you to keep standard synchronized usage without holding a carrier solely because of the monitor. Continue monitoring JFR for native/VM pinning and control contention and downstream resources according to actual requirements.