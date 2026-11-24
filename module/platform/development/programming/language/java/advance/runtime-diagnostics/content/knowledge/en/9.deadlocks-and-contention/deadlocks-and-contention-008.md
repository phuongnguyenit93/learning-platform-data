# 9.8 — Combining Thread Dumps with JFR JavaMonitorEnter, JavaMonitorWait, and ThreadPark

## 1. Why Are Both Thread Dumps and JFR Needed?

When a Java application hangs, latency spikes, or throughput drops, a **thread dump** reveals the state of Java threads **at the moment of capture**: which threads are `BLOCKED`, `WAITING`, or `TIMED_WAITING`; where their stacks sit; which monitor they are `waiting to lock`; and which thread `locked` that monitor. This data is great for finding lock-wait relationships, yet a single dump cannot measure wait durations over the preceding minutes.

**Java Flight Recorder (JFR)** adds a **timeline** of events containing `startTime`, `duration`, `eventThread`, `stackTrace`, and fields specific to each wait type. On Java 17, the three core events for hangs and contention are:

- `jdk.JavaMonitorEnter`: thread **blocked trying to enter a Java object monitor** via `synchronized`.
- `jdk.JavaMonitorWait`: thread called `Object.wait(...)` and **is waiting for notification, timeout, or another wakeup event**; `wait` releases the monitor of the waited object.
- `jdk.ThreadPark`: thread parked via `LockSupport.park`/`parkNanos`/`parkUntil`; may involve AQS/`ReentrantLock`, conditions, `Future`, or an idle thread pool.

**A helpful mnemonic:** thread dumps answer **“who is waiting on whom right now?”**, while JFR answers **“which waits occurred, how long did they last, and from which call paths?”**. Both sources complement each other without replacing one another.

After this lesson, learners will be able to:

1. Accurately distinguish the three Java wait types and their three corresponding JFR events.
2. Capture a thread dump via `jcmd Thread.print -l` alongside a JFR recording on the exact same JVM.
3. Correlate using thread identity, timestamps, stacks, monitor information, and durations.
4. Understand when an event has not yet been recorded due to **being unfinished**, thresholds, or missing recording coverage.
5. Avoid confusing contention, notification waits, or idle parking with deadlock.
6. Run a compilable/runnable Java 17 example producing all three events and reading a real `.jfr` file.

## 2. Two Evidence Types with Different Scopes

| Property | Thread Dump | JFR |
| --- | --- | --- |
| Timing | Snapshot at command invocation | Events within the recording window |
| State | `BLOCKED`, `WAITING`, `TIMED_WAITING`, `RUNNABLE` | Event for a specific wait/contended acquisition |
| Stack | Frames at capture time | Event `stackTrace` when enabled |
| Lock ownership | `locked`, `waiting to lock`, ownable synchronizers, owner metadata | `previousOwner` exists only on `JavaMonitorEnter`; not a full live owner graph |
| Duration | One snapshot cannot prove total past wait duration | `duration` for recorded events |
| Deadlock detection | Can build waiter → owner graph and see deadlock summary | A long event **does not** prove a cycle by itself |
| Missing data cases | Threads exit or change state between captures | Event disabled, below threshold, outside window, or not yet committed |

A thread in `BLOCKED` when a dump is taken may **not yet** have a completed `JavaMonitorEnter` event in the JFR file: the monitor entry wait has not ended, so the event has not finished to be recorded. This is the single most important limitation when combining **current-state snapshots** with **duration-based events**.

## 3. JavaMonitorEnter — Contention Entering a Monitor

When a thread calls `synchronized(lock)` or a synchronized method whose monitor is held by another thread, it can enter `BLOCKED`. `jdk.JavaMonitorEnter` reflects **monitor contention**, **not every uncontended `synchronized` entry**.

Common event fields on OpenJDK/HotSpot Java 17:

| Field | Meaning | How to Read |
| --- | --- | --- |
| `startTime` | Start of the contended monitor-enter phase | Align with snapshot timestamps |
| `duration` | Duration blocked trying to enter the monitor | Not CPU time or total time inside the synchronized block |
| `eventThread` | Thread **waiting to enter the monitor** | Waiter, not owner |
| `monitorClass` | Class of the monitor object | Many objects share a class; insufficient alone to identify one lock |
| `address` | Runtime monitor address info | Does not automatically equal tokens in every thread dump |
| `previousOwner` | Previous monitor owner per event metadata | Does not guarantee who owns it at an arbitrary dump timestamp |
| `stackTrace` | Call path causing contention | May be disabled, truncated, or implementation-dependent |

An illustrative event:

```text
jdk.JavaMonitorEnter {
  startTime = 16:32:10.545
  duration = 1.90 s
  monitorClass = java.lang.Object
  previousOwner = "lab-owner"
  eventThread = "lab-contender"
  stackTrace = [
    JfrLockTriadDemo.lambda$main$1(...)
    java.lang.Thread.run()
  ]
}
```

This is abbreviated from a real test run; timestamps, thread IDs, addresses, source lines, and durations vary across JVMs. `lab-contender` had to wait while `lab-owner` held the monitor; the event completed once the contender acquired the lock.

### 3.1. Do Not Treat previousOwner as the Live Lock Owner

`previousOwner` means **the prior owner** per JFR metadata. The monitor could have been released, changed owners, or altered state between event start and end. If your goal is to identify **which thread holds the monitor at the exact moment of a dump**, use `- locked <L>` and `- waiting to lock <L>` inside **the same dump**, or `ThreadMXBean.getLockOwnerId()`.

A `JavaMonitorEnter` event with a large duration means the thread **experienced contention** and the event finished recording—it does not prove a deadlock by itself. An unresolved real monitor deadlock can even leave the contended enter event **unfinished**, meaning JFR has not recorded it yet.

## 4. JavaMonitorWait — Object.wait and Notification

`Object.wait` can only be called while the thread owns the object’s monitor. While awaiting notification/timeout, the thread **releases the monitor of the waited object**, then must reacquire it before proceeding. Hence a `WAITING/TIMED_WAITING (on object monitor)` thread with `waiting on <L>` is not equivalent to a `BLOCKED` thread with `waiting to lock <L>`.

Key fields:

| Field | Meaning | What Not to Misread |
| --- | --- | --- |
| `eventThread` | Thread calling `Object.wait` | Not the notifier |
| `monitorClass`, `address` | Waited monitor object | Does not identify who holds another lock |
| `duration` | Recorded wait event duration | Not how long a monitor was exclusively held |
| `timeout` | Maximum **requested** wait time | Not actual elapsed duration |
| `timedOut` | Whether the JVM reports the wait timed out | `false` does not always prove a specific notifier |
| `notifier` | Thread performing notification, if recorded | May be null/absent in other cases |
| `stackTrace` | Call path leading to `Object.wait` | May include `Object.wait` and deep application frames |

Example:

```text
jdk.JavaMonitorWait {
  duration = 901 ms
  monitorClass = java.lang.Object
  notifier = "lab-notifier"
  timeout = 1.70 s
  timedOut = false
  eventThread = "lab-waiter"
}
```

Here `lab-waiter` was awakened before the timeout. A ~900 ms duration does not mean another thread **held this monitor for 900 ms**. For most of that time, `Object.wait` had released the monitor. Wakeup can also be affected by interruptions, spurious wakeups, scheduling, and monitor reacquisition.

**Wait-for graph rule:** Never add a waiter → owner edge directly from `- waiting on <L>`. That is *awaiting notification*, not automatically *waiting to enter a monitor held by an owner*. To find why waits drag on, inspect code calling `notify`/`notifyAll`, condition logic, producers, and execution paths after signaling.

## 5. ThreadPark — Waiting via LockSupport/AQS

`LockSupport` provides `park`, `parkNanos`, and `parkUntil`. Many `java.util.concurrent` classes rely on this primitive: `ReentrantLock`, `Condition`, `Future`, `BlockingQueue`, and `ThreadPoolExecutor`. Therefore `jdk.ThreadPark` can represent **lock contention** or an **idle pool**, depending on stack and context.

| Field | Meaning | Notes |
| --- | --- | --- |
| `eventThread` | Parked thread | Not necessarily blocked on a `ReentrantLock` |
| `duration` | Recorded park duration | Can end due to unpark/timeout/interruption |
| `parkedClass` | Class of blocker object | Blocker does not automatically supply an owner |
| `address` | Address associated with blocker object | Not a universal monitor-owner mapping |
| `timeout` | Park timeout if any | May be `N/A` |
| `until` | Deadline for park-until if any | May be `N/A` |
| `stackTrace` | Where park occurred | Read full AQS/pool frames to identify purpose |

Example:

```text
jdk.ThreadPark {
  duration = 1.30 s
  parkedClass = java.lang.String
  timeout = 1.30 s
  until = N/A
  eventThread = "lab-parker"
  stackTrace = [
    jdk.internal.misc.Unsafe.park(...)
    java.util.concurrent.locks.LockSupport.parkNanos(...)
    JfrLockTriadDemo.lambda$main$4(...)
  ]
}
```

In the demo, `parkedClass=java.lang.String` appears because the program passed `"lab-park-blocker"` as the **blocker object** to `LockSupport.parkNanos`. **This String is not a lock owned by another thread.** Never infer `parkedClass` or `address` as a monitor owner.

### 5.1. A Long Park Is Not Necessarily a Hang

A thread in `ThreadPoolExecutor.getTask` or `BlockingQueue.take` can park for a long time when there are no tasks. If the queue is empty and throughput meets expectations, that is a valid idle state. Conversely, if backlog climbs while workers keep parking, inspect producers, signaling, task lifecycles, or pool shutdown. `ThreadPark` is only a starting point for investigation.

## 6. Thread Dump → JFR Cross-Reference Table

| Sign in Dump | Common Corresponding Event | Evidence Available | What Else to Check |
| --- | --- | --- | --- |
| `BLOCKED (on object monitor)` and `waiting to lock <L>` | `JavaMonitorEnter` | Trying to enter a Java monitor | Owner at snapshot, lock identity, duration after completion |
| `WAITING/TIMED_WAITING (on object monitor)` and `waiting on <L>` | `JavaMonitorWait` | Waiting in `Object.wait` | Notifier, timeout, signal path |
| `WAITING/TIMED_WAITING (parking)` and `Unsafe.park` | `ThreadPark` | Parked | AQS/condition/queue/idle, owner if any |
| `RUNNABLE` with `locked <L>` | May have no event for owner | Holding monitor | Code inside critical section, CPU/I/O |
| No `BLOCKED` thread in snapshot | May have `JavaMonitorEnter` before/after dump | Contention may have already ended | JFR timeline, frequency/threshold |
| Thread `BLOCKED` forever yet no completed event | Event unfinished or event disabled | Snapshot remains blocking proof | Deadlock graph, JFR settings, next dumps |

**There is no strict one-to-one correlation.** Thread states can change faster than operators capture dumps; JFR only stores **recorded** events inside the recording window exceeding active thresholds.

## 7. Correlating by Exact JVM, Thread ID, and Time

An evidence bundle should record:

```text
host/pod: app-node-02 / orders-3
pid_namespace: container-app
pid: 18432
jvm_start_utc: 2026-10-29T08:15:00Z
jdk_version: 17.x
dump_capture_utc: 2026-10-29T08:21:04Z
jfr_start_utc: 2026-10-29T08:20:00Z
jfr_end_utc: 2026-10-29T08:22:00Z
incident: increased request latency
```

This is **illustrative** metadata, not real output. PIDs can be reused; use host, PID namespace, and process start time to avoid pairing a dump from an old session with a JFR file from a new JVM.

### 7.1. Distinguishing Java Thread ID, Native ID, and Thread Name

JFR `eventThread` can print `javaThreadId` and thread name. HotSpot thread dumps include thread name, `#...`, `tid=...`, and `nid=...`. `nid` is typically the **native OS thread ID**, while `tid` is an implementation identifier—**neither automatically equals `javaThreadId`**.

Prefer joining by **Java thread ID within the same JVM instance**, using thread name and stack trace to cross-check. Names like `worker-1` can collide or be reused when threads die and respawn. If unsure which ID type is printed, never force a join on name string alone.

### 7.2. Does the Event Interval Cover the Dump Timestamp?

Analytically, a duration event covers `[startTime, startTime + duration]`. If `dump_capture_utc` falls within that interval **and** `eventThread`/call path match, it is likely the same wait seen in the dump. Be sure to convert timezones accurately; `jfr print` may format times in the local timezone of the tool’s host, whereas system logs use UTC.

An unfinished `JavaMonitorEnter` at dump time may appear **later** when the recording is dumped after contention clears. Avoid inferring event ordering solely from when files were saved.

### 7.3. Why Not Join Mechanically by Object Address?

Thread dumps print `<0x...>` tokens while JFR events have `address`. Monitor address representations, object lifecycles, GC compaction, monitor inflation, and identity reuse can differ across runtime contexts. **There is no universal contract that the two hex strings always match** or remain stable across snapshots.

For more reliable correlation, use **JVM instance + thread ID + timestamp + stack + monitorClass**, relying on owner/lock identity only when verified within the same dump or under confirmed runtime semantics.

## 8. Procedure to Capture Thread Dumps and JFR Recordings on Java 17

### 8.1. Identify the Exact JVM

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> help Thread.print
jcmd <PID> help JFR.start
jcmd <PID> help JFR.dump
```

Replace `<PID>` with the real PID without angle brackets. `jcmd` requires matching attach permissions and host/PID namespace for the target JVM; in containers, host PID and pod PID can differ. Never use `jcmd 0` for a single JVM, as it can dispatch commands to multiple JVMs.

### 8.2. Enable JFR Before the Suspect Window

```bash
jcmd <PID> JFR.start name=LockDiag settings=profile
jcmd <PID> JFR.check name=LockDiag verbose=true
```

`settings=profile` uses a JDK recording template. **Verify actual configuration**: whether all three events are enabled, what `threshold` is set, and whether `stackTrace` is recorded. Java 17 `default.jfc` and `profile.jfc` typically filter out very short waits with thresholds in the tens of milliseconds. Custom `.jfc` files or other vendors/runtimes may differ.

If the JVM already has a suitable recording running, you do not necessarily need to start another. `JFR.check` inspects active recordings and, with `verbose=true`, their event settings.

### 8.3. During the Incident: Capture Dumps

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
jcmd <PID> Thread.print -l > dump-1.txt
```

Example for **Linux bash**. `date -u` prints the UTC timestamp; `>` writes the file on the shell machine executing `jcmd`. If the app keeps hanging, take 1–2 additional timestamped dumps spaced reasonably apart. Do not dump tightly when the JVM has many threads or is resource-starved.

`-l` reveals monitors and ownable synchronizers when supported by the runtime. Dumping carries cost depending on thread count and JVM state; check `help Thread.print` / impact before running in production.

### 8.4. Export the Recording and Read Events

```bash
jcmd <PID> JFR.dump name=LockDiag filename=/var/tmp/lockdiag.jfr
jcmd <PID> JFR.stop name=LockDiag
jfr summary /var/tmp/lockdiag.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark --stack-depth 12 /var/tmp/lockdiag.jfr
```

`JFR.dump` writes the file on the **target JVM’s** filesystem, not necessarily the client shell’s directory; inside a container, the path belongs to the container filesystem. `JFR.dump` does not stop the recording; only run `JFR.stop` when collection is done and procedures allow. `jfr summary` shows event counts/types, while `jfr print` filters events and prints stack frames. You can also open the file in **JDK Mission Control** to view the timeline.

If the JFR file is dumped too early while a thread is still `BLOCKED`, the ongoing event may **not yet be committed**. Do not expect a JFR dump taken mid-block to already contain the unfinished event.

## 9. Method for Correlating a Real Scenario

Suppose an incident shows:

- `request-17` is `BLOCKED` waiting on monitor `L` in `Cache.get`.
- `cache-refresher` has `locked <L>` in cache update code.
- `pool-worker-4` is in `LockSupport.park` inside `ThreadPoolExecutor.getTask`.

The thread dump gives the graph:

```text
request-17 --waiting for monitor L--> cache-refresher
pool-worker-4 --parking for task--> owner not proven
```

After the incident finishes, JFR contains illustrative events:

```text
16:21:11.800 → 16:21:13.100
  JavaMonitorEnter, eventThread=request-17, duration≈1.30s
  monitorClass=CacheLock, previousOwner=cache-refresher

16:21:10.000 → 16:21:20.000
  ThreadPark, eventThread=pool-worker-4
  stack=BlockingQueue.take()/ThreadPoolExecutor.getTask()
```

This is **hypothetical scenario data**, not canonical output. How to conclude:

1. The dump proves `request-17` was waiting on monitor `L` and the owner at that instant was `cache-refresher`.
2. `JavaMonitorEnter` adds duration and call path, proving the request experienced a long wait.
3. `previousOwner` matches the owner in the example, yet **owner at snapshot time must be verified from the dump**, not inferred from the event.
4. `pool-worker-4` had a long park in idle queue code; there is no evidence it caused latency.
5. Inspect the same window’s request metrics, CPU/GC/I/O, queue depth, and application logs before selecting root cause.

**Deliverables to hand off:** affected threads/call paths, awaited monitor or condition, evidence-backed owner, duration/frequency in JFR, confidence level of correlating both sources, and specific code changes.

## 10. Java 17+ Demo: Generating All Three Events in One Recording

`JfrLockTriadDemo.java` runs three wait paths **concurrently**:

1. `lab-owner` holds `ENTER_LOCK` for ~1.9 seconds; `lab-contender` waits to enter `synchronized(ENTER_LOCK)`.
2. `lab-waiter` calls `WAIT_LOCK.wait(1700)`; `lab-notifier` calls `notifyAll()` after ~900 ms.
3. `lab-parker` calls `LockSupport.parkNanos` with a `String` blocker for ~1.3 seconds.

A programmatic `Recording` enables all three events with `stackTrace` and sets `threshold=0` for **local demo purposes**, then writes `triad-demo.jfr`. `RecordingFile` reads the file and verifies events matching **exact thread names**; the JFR runtime may also record internal events or `Thread.join` events from the main thread.

### 10.1. Complete `JfrLockTriadDemo.java` File

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.Set;
import java.util.HashSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.LockSupport;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordedEvent;

public class JfrLockTriadDemo {
    static final Object ENTER_LOCK = new Object();
    static final Object WAIT_LOCK = new Object();

    static void nap(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of(args.length == 0 ? "triad-demo.jfr" : args[0]);

        try (Recording r = new Recording()) {
            r.enable("jdk.JavaMonitorEnter")
             .withThreshold(Duration.ZERO).withStackTrace();
            r.enable("jdk.JavaMonitorWait")
             .withThreshold(Duration.ZERO).withStackTrace();
            r.enable("jdk.ThreadPark")
             .withThreshold(Duration.ZERO).withStackTrace();
            r.setToDisk(true);
            r.start();

            CountDownLatch ownerReady = new CountDownLatch(1);
            CountDownLatch waiterReady = new CountDownLatch(1);
            CountDownLatch parkReady = new CountDownLatch(1);

            Thread owner = new Thread(() -> {
                synchronized (ENTER_LOCK) {
                    ownerReady.countDown();
                    nap(1900);
                }
            }, "lab-owner");

            Thread contender = new Thread(() -> {
                await(ownerReady);
                synchronized (ENTER_LOCK) { }
            }, "lab-contender");

            Thread waiter = new Thread(() -> {
                synchronized (WAIT_LOCK) {
                    waiterReady.countDown();
                    try {
                        WAIT_LOCK.wait(1700);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            }, "lab-waiter");

            Thread notifier = new Thread(() -> {
                await(waiterReady);
                nap(900);
                synchronized (WAIT_LOCK) {
                    WAIT_LOCK.notifyAll();
                }
            }, "lab-notifier");

            Thread parker = new Thread(() -> {
                parkReady.countDown();
                LockSupport.parkNanos("lab-park-blocker",
                    Duration.ofMillis(1300).toNanos());
            }, "lab-parker");

            owner.start();
            contender.start();
            waiter.start();
            notifier.start();
            parker.start();

            ownerReady.await();
            waiterReady.await();
            parkReady.await();

            boolean allWaiting = false;
            for (int i = 0; i < 100; i++) {
                allWaiting =
                    contender.getState() == Thread.State.BLOCKED &&
                    waiter.getState() == Thread.State.TIMED_WAITING &&
                    parker.getState() == Thread.State.TIMED_WAITING;
                if (allWaiting) break;
                Thread.sleep(10);
            }
            if (!allWaiting) {
                throw new IllegalStateException("states not observed");
            }
            System.out.println("SNAPSHOT_WINDOW");

            owner.join();
            contender.join();
            waiter.join();
            notifier.join();
            parker.join();

            r.stop();
            r.dump(file);
        }

        Set<String> found = new HashSet<>();
        try (RecordingFile read = new RecordingFile(file)) {
            while (read.hasMoreEvents()) {
                RecordedEvent e = read.readEvent();
                String kind = e.getEventType().getName();

                if (!kind.equals("jdk.JavaMonitorEnter") &&
                    !kind.equals("jdk.JavaMonitorWait") &&
                    !kind.equals("jdk.ThreadPark")) {
                    continue;
                }
                if (e.getThread("eventThread") == null) continue;

                String thread = e.getThread("eventThread").getJavaName();
                if (kind.equals("jdk.JavaMonitorEnter") &&
                    thread.equals("lab-contender")) {
                    found.add("Enter");
                }
                if (kind.equals("jdk.JavaMonitorWait") &&
                    thread.equals("lab-waiter")) {
                    found.add("Wait");
                }
                if (kind.equals("jdk.ThreadPark") &&
                    thread.equals("lab-parker")) {
                    found.add("Park");
                }
            }
        }

        System.out.println("JavaMonitorEnter=" + found.contains("Enter"));
        System.out.println("JavaMonitorWait=" + found.contains("Wait"));
        System.out.println("ThreadPark=" + found.contains("Park"));
    }
}
```

This is a **complete Java program**, compilable with `javac --release 17` with no libraries outside the JDK. `Duration.ZERO` sets the event threshold to 0 to catch short events during **testing**; never enable this by default in production as it can generate huge event volumes.

### 10.2. Run and Read Stdout

```bash
javac --release 17 JfrLockTriadDemo.java
java JfrLockTriadDemo triad-demo.jfr
```

**Exact stdout from the verified test run:**

```text
SNAPSHOT_WINDOW
JavaMonitorEnter=true
JavaMonitorWait=true
ThreadPark=true
```

`SNAPSHOT_WINDOW` prints after the code confirms all three threads are in the right states: one `BLOCKED`, two `TIMED_WAITING`. The three `true` values are computed by reading the **actual recording file**, filtering by event type and thread name—not hardcoded prints.

On other JVMs/vendors or under load, durations and IDs vary; the state check in the program could also time out on extremely slow machines and throw `IllegalStateException`. In that case increase wait intervals in the test environment rather than faking printed output.

### 10.3. Print Events and Cross-Check

```bash
jfr summary triad-demo.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark --stack-depth 5 triad-demo.jfr
```

In an actual QA run, the file contained:

- `lab-contender`: `JavaMonitorEnter` duration ~**1.9 seconds**, `previousOwner=lab-owner`.
- `lab-waiter`: `JavaMonitorWait` duration ~**0.9 seconds**, `notifier=lab-notifier`, and `timedOut=false`.
- `lab-parker`: `ThreadPark` duration ~**1.3 seconds**, `parkedClass=java.lang.String`.
- Several other events generated by the JVM/JFR runtime and the main thread’s `Thread.join`.

Durations/addresses/thread IDs **are not fixed across runs**. What matters is accurately correlating **eventThread + event type + call path**.

### 10.4. Capture a Thread Dump While the Demo Is Waiting

In another terminal, right when `SNAPSHOT_WINDOW` appears before the JVM exits:

```bash
jcmd -l
jcmd <PID> Thread.print -l > snapshot.txt
```

The default sample window lasts only **a couple of seconds**, so for manual operation you may need to **increase `nap(1900)`, `WAIT_LOCK.wait(1700)`, and `parkNanos(1300 ms)` and recompile**, or automate capture right as the window opens. In a verified live run, `jcmd Thread.print -l` observes all three thread names in the target JVM.

Expected state patterns **inside the window**:

| Thread | State in Dump | Marker | Corresponding Event After Completion |
| --- | --- | --- | --- |
| `lab-contender` | `BLOCKED` | `waiting to lock` monitor held by `lab-owner` | `JavaMonitorEnter` |
| `lab-waiter` | `TIMED_WAITING (on object monitor)` | `Object.wait`, `waiting on` | `JavaMonitorWait` |
| `lab-parker` | `TIMED_WAITING (parking)` | `LockSupport.parkNanos` | `ThreadPark` |
| `lab-owner` | Usually `TIMED_WAITING (sleeping)` | `locked` monitor in `synchronized` | May have no monitor-enter contention event |
| `lab-notifier` | Sleeping or already notified | `notifyAll` after a delay | `notifier` field in `JavaMonitorWait` |

Do not conclude the demo failed if a dump captured **after the event ended** no longer shows waiting threads; JFR will still hold the completed events in the file.

## 11. Thread Dumps and JFR When Deadlock Is Suspected

Wait-for graph example of an **object monitor deadlock**:

```text
Thread A --waits for monitor L2--> Thread B
Thread B --waits for monitor L1--> Thread A
```

The thread dump can show matching `- waiting to lock <...>` and `- locked <...>` lines, or a `Found one Java-level deadlock` section. That is evidence constructing a **waiter → owner cycle in the same snapshot**.

JFR **is not a complete deadlock detector**: `JavaMonitorEnter` reports recorded contention events, `JavaMonitorWait` reports notification waits, and `ThreadPark` reports parks. An unresolved deadlock can prevent monitor-enter events from **ever finishing**, leaving no completed event to confirm a cycle.

When suspected:

1. From the dump, determine which lock each thread **is waiting on** and **the owner at snapshot time**.
2. Draw waiter → owner edges only with matching lock identity or explicit owner metadata.
3. Trace until stopping or repeating: `A → B → C → A` is a cycle.
4. Check `ThreadMXBean.findMonitorDeadlockedThreads()`/`findDeadlockedThreads()` if supported by the JVM; note monitor vs. ownable synchronizer scope.
5. Use JFR to analyze **leading up to the hang**: which code paths contended frequently, when durations climbed, and how many requests were impacted.
6. For DB locks, network waits, or distributed locks, thread dumps/JFR are only part of the picture; pull data from the resource-owning system.

## 12. Common Diagnostic Scenarios

### A. Latency Rises Yet Dumps Show No `BLOCKED`

Snapshots can easily miss brief bursts of contention. Timeline `JavaMonitorEnter` events in JFR show code paths and durations of events **exceeding threshold**. With `threshold=20ms`, repeated 5–10ms contentions will emit no events. Never treat event count 0 as zero contention.

### B. Many Thread Pool Workers Are `WAITING (parking)`

Long `ThreadPark` events in `ThreadPoolExecutor.getTask`/`BlockingQueue.take` may simply be idle workers. Check queue depth, active workers, task submissions, and throughput. If the application has no work, parking is normal; if backlog grows, inspect producers, schedulers, and pool state.

### C. Thread Is `BLOCKED` Yet Has No `JavaMonitorEnter`

Check `enabled`, threshold, recording window, dump timestamp, and thread identity. If contention is still ongoing, the event may **not be committed yet**; inspect the current owner from the snapshot and optionally wait until contention clears to view the completed event. If a deadlock cycle is found, you do not need a JFR event to trust the dump.

### D. Long `JavaMonitorWait` Duration

`Object.wait` releases the monitor; a long event does not prove a thread held a lock for a long time. Check `notifier`, `timedOut`, producer/signal paths, and business conditions. Even if `timedOut=false`, do not assume only one wakeup path exists.

### E. `ThreadPark` from `ReentrantLock`/`Condition`

Stacks may show `AbstractQueuedSynchronizer` or `ConditionObject.await`. Distinguish **waiting to acquire a `ReentrantLock`** from **condition await that released the lock**. On supporting runtimes, use `ThreadInfo.getLockOwnerId()` and locked ownable synchronizers in dumps; `parkedClass` alone is not enough to draw an owner edge.

### F. Many Threads Hung on Database/Network

JFR may show `SocketRead`/`SocketWrite` or `ThreadPark`, and dumps show I/O/Future stacks; however, the JVM cannot see the Java thread owner of a DB row lock or remote service. Combine DB lock graphs, network traces, downstream logs, and client timeout timestamps. Never fabricate a Java monitor deadlock.

## 13. Thresholds, Recording Windows, and Overhead

JFR event settings include `enabled`, `threshold`, and `stackTrace`. JDK `default.jfc` and `profile.jfc` templates enable various thread-stalling events with thresholds in the **tens of milliseconds**, e.g., 20ms in some default configs. JDK/vendor defaults or custom profiles may differ; run `JFR.check name=LockDiag verbose=true` rather than guessing.

| Setting | Result | Risk |
| --- | --- | --- |
| `enabled=false` | Event type not recorded | Cannot infer “no waits occurred” |
| `threshold=20ms` | Skips events shorter than 20ms | Misses frequent short contention |
| `threshold=10ms` | Captures more short events | Increases event volume |
| `threshold=0ms` | Captures even ultra-short events | Can create heavy overhead and huge data volume |
| `stackTrace=false` | Has duration without call path | Hard to trace back to code |
| `stackTrace=true` | Better grouping by stack | Adds stack/data overhead |

**Never set threshold 0 by default in production.** Use recordings with authorized duration, size, and scope; only lower thresholds for a specific diagnostic question. JFR files and thread dumps can expose class names, stacks, command lines, host details, or sensitive data; store them with restricted access, enforce retention policies, and redact before sharing.

`jcmd Thread.print -l` has cost proportional to thread count; taking rapid dumps on a many-thread JVM can also impact latency. Separate targeted incident investigation from routine monitoring.

## 14. Common Reasoning Mistakes

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| “`JavaMonitorEnter` logs every `synchronized` entry.” | Event specifically tracks monitor contention. | Interpret it strictly as contended acquisition. |
| “Thread is `BLOCKED` with no JFR event, so the dump is wrong.” | Event may be unfinished or filtered by threshold/window. | Trust the snapshot for state at capture time; check settings. |
| “`JavaMonitorWait` means holding the monitor throughout the wait.” | `Object.wait` releases that monitor. | Investigate notifier/condition. |
| “`ThreadPark` always means a `ReentrantLock` deadlock.” | Park can be an idle queue/future/condition. | Inspect stack/owner and work progress. |
| “`previousOwner` equals current owner in the dump.” | Semantics are **previous owner**. | Live owner at dump time must come from the snapshot. |
| “`notifier` is always present and `timedOut=false` means only notify.” | Multiple wakeup paths and null values exist. | Check Javadoc and signal paths. |
| “`address` in JFR must match `<0x...>` in the dump.” | No universal stable mapping exists. | Correlate by thread/time/stack and verify. |
| “`nid` equals `javaThreadId`.” | `nid` is typically the OS native ID. | Distinguish Java vs. native IDs. |
| “One long park proves deadlock.” | Could be normal idle pool waiting. | Look for a waiter → owner cycle in the same snapshot. |
| “No events means zero contention.” | Thresholds, disabled settings, window, and event lifetime apply. | Check configuration and timing. |
| “Matching JVM A dump with JVM B JFR by PID is enough.” | PIDs can be reused. | Verify host/namespace/start time. |
| “`JFR.dump` writes the file in the client shell directory.” | The target JVM writes the file. | Check target filesystem/container paths. |
| “Threshold 0 has no performance impact.” | Event counts and stack captures can be massive. | Use only in testing or bounded investigations. |
| “One long `JavaMonitorEnter` proves a cycle.” | Completed events do not prove a cycle. | Build the graph from dumps/`ThreadMXBean`. |

## 15. End-to-End Investigation Checklist

- [ ] Verified exact **host, PID namespace, JVM PID, process start time, and JDK/vendor**?
- [ ] Captured `Thread.print -l` dump during the symptom window and recorded UTC timestamps?
- [ ] Captured JFR recording covering the window and verified `enabled`/`threshold`/`stackTrace`?
- [ ] Used `jfr summary` and `jfr print --events ...` to confirm real events exist?
- [ ] Correlated using Java thread ID, name, and stack within the **same JVM session**, without mixing `nid`/`tid`?
- [ ] Distinguished `waiting to lock`, `waiting on`, and `parking to wait for`?
- [ ] For `JavaMonitorEnter`, checked `eventThread`/`previousOwner` while verifying **live owner** from the dump?
- [ ] For `JavaMonitorWait`, checked duration, timeout, `timedOut`, `notifier`, and producer signals?
- [ ] For `ThreadPark`, checked blocker/stack (idle pool vs. AQS wait) without inventing owners?
- [ ] Considered whether an ongoing wait event **has not committed yet because it has not ended**?
- [ ] When suspecting deadlock, looked for a **waiter → owner cycle within one snapshot**?
- [ ] Cross-checked request latency, throughput, queues, CPU/GC/I/O, and logs?
- [ ] Bounded recording duration, event thresholds, dump frequency, disk size, and access permissions?
- [ ] Conclusion clearly covers **evidence → hypothesis → verification → remediation**?

## 16. Official Java SE 17 Documentation

- [Oracle — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html): Java monitor blocked/wait, park, timelines, and thresholds.
- [Oracle — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print`, `JFR.start`, `JFR.check`, `JFR.dump`, and `JFR.stop`.
- [Oracle — The jfr Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `jfr summary`, `jfr print --events --stack-depth`.
- [Oracle — jdk.jfr package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html): `enabled`, `threshold`, and `stackTrace` settings.
- [Oracle — Recording](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): programmatic recording, enable/stop/dump.
- [Oracle — RecordingFile](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): reading `.jfr` events.
- [Oracle — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread owner/monitor deadlock detection.
- [Oracle — Object.wait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait()): monitor release/reacquire semantics.
- [Oracle — LockSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): parking, blockers, and unpark.

**Conclusion:** Use **thread dumps to see state and owners right at capture time** and **JFR to see event durations, timelines, and call paths**. `JavaMonitorEnter` is waiting **to enter a monitor**, `JavaMonitorWait` is **`Object.wait`**, and `ThreadPark` is **parking via `LockSupport`/AQS**. Never collapse them into a generic “hung thread” label; declare deadlock only with evidence of a **waiter → owner cycle**, never from a single long event alone.