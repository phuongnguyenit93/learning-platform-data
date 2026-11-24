# 6.9. Memory threshold notifications and avoiding heavy work inside callbacks

When a Java application experiences memory pressure, waiting until `OutOfMemoryError` to react is usually too late. The JVM provides **MemoryPoolMXBean** to monitor individual memory pools and set usage thresholds, and **MemoryMXBean** to emit JMX notifications when a threshold condition is detected. This mechanism is useful for **load shedding, checking memory trends, alerting, and handing off coordination to another component**.

However, the `NotificationListener.handleNotification(...)` callback **is not the place to run heap dumps, full GCs, data queries, network calls, or heavy analysis**. The callback may execute inside the JVM's notification dispatch mechanism; if it blocks or allocates many objects while memory is tight, it can delay other notifications, increase memory pressure, and worsen the incident.

This lesson belongs to **6. MXBeans** and focuses on:

1. Distinguishing **usage threshold** from **collection usage threshold**.
2. Identifying which memory pools actually support thresholds, choosing thresholds, and interpreting `MemoryUsage`.
3. Registering a listener on `MemoryMXBean` and reading `MemoryNotificationInfo` with the right types.
4. Designing an **ultra-short callback → bounded queue / signal → dedicated worker**.
5. Preventing duplicate processing, queue overflow, logging storms, and overload-inducing reactions when the JVM lacks memory.
6. Practicing with Java 17+ along with limitations, testing strategies, and a production checklist.

## 1. Model: MemoryPoolMXBean sets thresholds, MemoryMXBean emits notifications

A JVM has different memory regions: **heap** (holding Java objects) and **non-heap** (e.g., metaspace, code cache), each of which may be represented by one or more **memory pools**. Pool names and support levels depend on collector, vendor, and version; never hard-code that every JVM has pools named `G1 Old Gen`, `PS Old Gen`, or `Tenured Gen`.

Two APIs play distinct roles:

| Component | Role | Key API |
| --- | --- | --- |
| `ManagementFactory.getMemoryPoolMXBeans()` | Discover memory pools in the current JVM | Returns a list of `MemoryPoolMXBean` |
| `MemoryPoolMXBean` | Read usage and set thresholds **per pool** | `getUsage()`, `getCollectionUsage()`, `isUsageThresholdSupported()`, `setUsageThreshold(long)`, `isCollectionUsageThresholdSupported()`, `setCollectionUsageThreshold(long)` |
| `ManagementFactory.getMemoryMXBean()` | Obtain the MXBean representing overall heap/non-heap and emitting memory notifications | `getHeapMemoryUsage()`, `getNonHeapMemoryUsage()` |
| `NotificationEmitter` | Register/unregister JMX listeners | `addNotificationListener(...)`, `removeNotificationListener(...)` |
| `MemoryNotificationInfo` | Decode data attached to a notification | `from(CompositeData)`, `getPoolName()`, `getUsage()`, `getCount()` |

Basic flow:

~~~text
JVM monitors each MemoryPoolMXBean
        |
        | usage/collection threshold condition detected
        v
MemoryMXBean emits a JMX Notification
        |
        v
NotificationListener.handleNotification(...)
        |
        | check type, try to enqueue a tiny signal
        v
Bounded queue / atomic flag
        |
        v
Dedicated worker reads MXBeans/metrics, checks trends,
rate-limits alerts, or recommends load shedding
~~~

**Common point of confusion:** you **set thresholds on MemoryPoolMXBean**, yet **register the listener on MemoryMXBean**—do not attach listeners directly to a `MemoryPoolMXBean` as if each pool were an independent emitter. Because `MemoryMXBean` emits notifications for multiple pools, the worker must check `poolName` to tell them apart.

## 2. MemoryUsage: know what you are comparing

`MemoryUsage` carries four numbers—`init`, `used`, `committed`, and `max`—in **bytes**:

- `init`: initial memory the JVM requested for the pool; may be undefined.
- `used`: estimated bytes currently used in the pool; may include uncollected objects if it is a GC-managed pool.
- `committed`: memory currently guaranteed available for the JVM to use; need not equal `used`.
- `max`: maximum usable size for the pool **if known by the JVM**, often `-1` when undefined.

Illustrative example:

~~~text
pool=example-old
init=0
used=314572800
committed=402653184
max=536870912
~~~

The example above represents `used` around 300 MiB, `committed` 384 MiB, and `max` 512 MiB. These are simulated numbers, **not output from a specific JVM**.

**Never mix units:**
- `setUsageThreshold(long)` and `setCollectionUsageThreshold(long)` take **bytes**, not MiB or percentages.
- Convert 1 MiB to bytes via `1024 × 1024`. For example, `384L * 1024 * 1024` equals 402,653,184 bytes.
- If `getMax() == -1`, you **cannot** compute "80% of max" by direct multiplication; use a policy based on other metrics or do not use percentage-based thresholds.
- Pool/heap `used` **is not process RSS or cgroup memory usage**; the JVM also uses native buffers, thread stacks, metaspace, code cache, and other areas.

`getUsage()` is an *estimated* snapshot at call time. Some pools may incur cost to compute usage, and a pool can become invalid (in which case `getUsage()` may return `null`). Do not poll continuously at high frequency inside callbacks or treat data as instantaneous zero-latency readings.

## 3. Two types of thresholds to distinguish

### 3.1. Usage threshold — pool usage reaches or exceeds the threshold

To enable usage threshold monitoring for a **supporting pool**, use:

~~~java
if (pool.isUsageThresholdSupported()) {
    pool.setUsageThreshold(thresholdBytes);
}
~~~

This is an **illustrative API snippet**, assuming `pool` and `thresholdBytes` are defined and validated. Some pools lack support, especially young-generation pools with high allocation rates: the JVM may avoid per-allocation threshold checks due to overhead.

When the JVM detects that a pool's usage has **reached or exceeded** the threshold, `MemoryMXBean` can emit a notification of type:

`MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED`

Key details to understand:
- To emit another notification for a **new** crossing, usage must first **drop below** the threshold and then cross it again.
- The JVM checks at **the most suitable time**, typically tied to GC; there is no guarantee the callback arrives at the exact microsecond the threshold is crossed.
- `getUsageThresholdCount()` is the number of times the JVM detected crossings; `MemoryNotificationInfo.getCount()` holds the count at the moment the notification was created.
- Seeing no notification **does not prove** heap never crossed the boundary during a short observation window.
- Setting the threshold to **0** disables usage threshold monitoring for that pool; a positive value enables checking. Check whether the pool supports it before reading/setting.

This is a mechanism for detecting **elevated usage**, not a guaranteed advance warning of OOM.

### 3.2. Collection usage threshold — remaining level after GC

For a pool with `isCollectionUsageThresholdSupported() == true`, you can configure:

~~~java
if (pool.isCollectionUsageThresholdSupported()) {
    pool.setCollectionUsageThreshold(thresholdBytes);
}
~~~

This is likewise an **API illustration**, not a standalone program. Notification type:

`MemoryNotificationInfo.MEMORY_COLLECTION_THRESHOLD_EXCEEDED`

Its semantics differ from usage threshold:
- The JVM checks usage **after attempting to reclaim objects** in a suitable collection cycle.
- When post-collection memory is **greater than or equal to** the threshold, the JVM may emit a collection threshold notification.
- It helps observe **live/retained heap pressure after GC** rather than a transient pre-GC spike, yet **does not by itself prove a memory leak**: intentional caches, workload bursts, fragmentation, or collector effects can also keep retained usage high.
- It can fire on appropriate GCs whenever post-collection usage stays high; do not mechanically apply the usage-threshold rearm rule.
- `getCollectionUsageThresholdCount()` and `getCollectionUsage()` are the corresponding data. `getCollectionUsage()` may be `null` if the pool is invalid or lacks suitable data yet; always check.

### 3.3. Comparison table

| Criterion | Usage threshold | Collection usage threshold |
| --- | --- | --- |
| Support check | `isUsageThresholdSupported()` | `isCollectionUsageThresholdSupported()` |
| Set threshold | `setUsageThreshold(bytes)` | `setCollectionUsageThreshold(bytes)` |
| Related value | `getUsage().getUsed()` | `getCollectionUsage().getUsed()` after suitable GC |
| Notification type | `MEMORY_THRESHOLD_EXCEEDED` | `MEMORY_COLLECTION_THRESHOLD_EXCEEDED` |
| Count | `getUsageThresholdCount()` | `getCollectionUsageThresholdCount()` |
| Primary meaning | Pool usage is high / crossed threshold | Pool remains high after reclamation effort |
| Limitations | Not emitted on every allocation; depends on JVM check timing | Only on supporting pools; depends on GC activity |
| How to disable | Set threshold to 0 | Set threshold to 0 |

Neither condition means "call `System.gc()` right now", "take a heap dump immediately", or "the JVM is definitely about to die". They are **signals** to guide observation and coordination.

## 4. Choosing pools and thresholds on a sound basis

### 4.1. Always ask the JVM what it supports

A program can inspect each pool:

~~~java
for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
    System.out.printf(
            "%s type=%s valid=%s usageSupported=%s collectionSupported=%s%n",
            pool.getName(),
            pool.getType(),
            pool.isValid(),
            pool.isUsageThresholdSupported(),
            pool.isCollectionUsageThresholdSupported()
    );
}
~~~

This snippet uses classes from `java.lang.management`; it is an **illustration inside a method with imports**, not a complete Java file. Pool names, collector types, and support vary across runtimes. On Java 17, do not assume G1/Parallel/ZGC/Shenandoah names match or that every non-heap pool supports thresholds.

### 4.2. Choosing thresholds based on actual behavior

There is no single "80% heap" figure right for every application. Consider:
- Actual heap and pool types, and whether `getMax()` is defined.
- Baseline usage and normal fluctuation between GCs.
- GC collector, allocation rate, peaks, and memory headroom.
- Notification frequency, recovery time, queue/cache sizes, and business behavior when shedding load.
- Container memory limit and memory regions **outside the Java heap**.

One starting approach in a test environment: pick a usage threshold as a suitable fraction of `max` on a **genuinely supporting pool**; too low yields noisy events/false positives; too high makes notifications arrive too late for load balancing. Tune against error rates, GC pressure, and latency rather than guessing by intuition.

**API rules:**
- `setUsageThreshold(long)` and `setCollectionUsageThreshold(long)` accept **non-negative** byte counts.
- If the pool has a defined max and the threshold **exceeds max**, the call may throw `IllegalArgumentException`; if unsupported, it may throw `UnsupportedOperationException`.
- Runtime management permission controls may apply; setting a threshold is a **JVM-wide monitoring-state change**, not private to the calling code.
- If multiple components set thresholds on the same pool, one component can **overwrite** another; centralized configuration/ownership is required. Restoring the old threshold at the end of an example is safe only when the runner owns that configuration.

### 4.3. Hysteresis to avoid flapping

If the worker reacts by pausing new load admission at a high watermark, do not automatically reopen right at that exact boundary. Pattern:

~~~text
used >= HIGH_WATERMARK --> enter load-shedding mode
used <= LOW_WATERMARK  --> recover only after N stable checks
LOW_WATERMARK < HIGH_WATERMARK
~~~

A notification is the trigger bringing the worker into its check loop; **when to recover** should rely on cadence-controlled polling, GC/heap trends, and hysteresis, not just waiting for another notification. Across shutdowns or differing GCs, responses must have timeouts and never fire unboundedly once per event.

## 5. Registering a JMX NotificationListener properly

`ManagementFactory.getMemoryMXBean()` returns a `MemoryMXBean` that implements `NotificationEmitter` on standard JDK 17 JVMs. Registering a listener:

~~~java
NotificationEmitter emitter =
        (NotificationEmitter) ManagementFactory.getMemoryMXBean();

NotificationListener listener = (notification, handback) -> {
    // Only check type and hand off quickly to a worker.
};

emitter.addNotificationListener(listener, null, null);
~~~

This is an **illustrative API snippet**, requiring imports for `javax.management.NotificationEmitter` and `javax.management.NotificationListener`. When no longer needed:

~~~java
emitter.removeNotificationListener(listener);
~~~

Important points:
- **Never register a listener per request**; register once per service/component lifecycle and remove cleanly at shutdown.
- For a listener receiving both notification types, filter by `notification.getType()`, then **in the worker** decode `(CompositeData) notification.getUserData()` and `MemoryNotificationInfo.from(...)`.
- `getPoolName()` identifies the signaling pool; `getUsage()` is the snapshot when the notification was created; `getCount()` is the count for that threshold type.
- The callback may be invoked **concurrently**; shared state must be atomic/thread-safe.
- Notifications may arrive delayed; ordering and arrival time do not replace independently sampled timelines/metrics.
- `MemoryMXBean`/`MemoryPoolMXBean` are JVM memory management mechanisms—**not a business event bus**, with no end-to-end exactly-once guarantee, and no substitute for external heap monitoring.

### Be careful with JMX userData

Auxiliary data of a memory notification is represented via `javax.management.openmbean.CompositeData`. Decoding pattern **inside the worker**:

~~~java
if (notification.getUserData() instanceof CompositeData data) {
    MemoryNotificationInfo info = MemoryNotificationInfo.from(data);
    if (info != null) {
        String poolName = info.getPoolName();
        long usedBytes = info.getUsage().getUsed();
        long count = info.getCount();
        // Record metric or make decision on worker; never inside callback.
    }
}
~~~

If receiving a notification with an unexpected type, abnormal `userData`, or a removed pool, do not guess or cast blindly. Filter `type` first; the complete example in Section 7 does this.

## 6. Why must you strictly avoid heavy work inside callbacks?

Oracle JDK 17 explicitly states `handleNotification` should do **very little work** and return without delay; the listener can also be invoked from multiple threads. When the JVM lacks headroom, heavy callbacks create two classes of risk:

### 6.1. Slowing down the notification dispatch mechanism

Operations prone to blocking:
- `Thread.sleep(...)`, `BlockingQueue.put(...)`, or `Future.get()` inside the callback.
- HTTP/DB requests, sending emails, calling cloud APIs, or alerting chat services.
- File/network reads, synchronous I/O, or flushing loggers with slow appenders.
- Acquiring locks that business threads may hold, risking lock inversion or prolonged contention.
- Running `GC.heap_dump` / `HotSpotDiagnosticMXBean.dumpHeap(...)` or calling explicit GC.
- Scanning all objects, serializing large stack traces, heap histograms, or querying batches of MXBeans.

A blocked callback can delay other notifications. Because dispatch mechanics depend on the JVM/transport, never rely on a fixed invocation order or a single dispatch thread.

### 6.2. Increasing memory pressure right when memory must be conserved

When memory is high:
- Allocating thousands of alert objects, large JSON payloads, or stack-trace strings adds allocation/GC pressure.
- Calling `Executors.newSingleThreadExecutor()` or spawning `new Thread` **per notification** creates extra threads and stacks.
- Pushing notifications to an **unbounded queue** can grow without limit if the worker falls behind.
- Writing a heap dump directly consumes I/O/disk and can trigger pauses; resources may not even suffice or the dump may not be needed.
- Logging ERROR with full environment/payloads inside the callback can cause log storms or leak secrets.

Recommended design: **the callback only filters type, tries a non-blocking `offer` into a fixed queue, increments a drop counter if full, and returns**. If immediate admission control changes are needed, set a simple non-blocking `AtomicBoolean`/`volatile` flag and leave decision logic to a bounded worker with timeouts.

### 6.3. What does a "lightweight" callback look like?

~~~java
NotificationListener listener = (notification, handback) -> {
    if (MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED
            .equals(notification.getType())) {
        if (!events.offer(notification)) {
            dropped.incrementAndGet();
        }
    }
};
~~~

**Illustrative snippet**, assuming `events` is a pre-created `ArrayBlockingQueue<Notification>` and `dropped` is an `AtomicLong`. `offer` does not wait for queue space; never call `put` (which can block). A dedicated worker parses `CompositeData`, records metrics, and takes operational actions. The `Notification` object was already created by the JVM before the callback; the queue holds only a bounded reference.

**Note:** do not allocate `ArrayBlockingQueue` *inside* the callback. Create the queue and worker **once** at initialization with bounded capacity, drop/coalesce metrics, and graceful shutdown; heavy actions must be rate-limited.

## 7. Complete Java 17+ example: lightweight listener, bounded queue, dedicated worker

This sample **runs standalone with only JDK 17+**, needing no SLF4J or external libraries. It:

1. Finds a **HEAP pool supporting usage thresholds** with a defined `max`.
2. Saves the old threshold to restore at exit **in a single-owner test context**.
3. Registers a listener on `MemoryMXBean`; the callback only filters type, calls `offer` into a 32-element queue, and increments a counter if full.
4. The worker reads `MemoryNotificationInfo`, filters `poolName`, and prints a summary line. Console output happens **outside the callback**.
5. Watches for up to 15 seconds without forcing heap allocations, calling `System.gc()`, or taking heap dumps. Notifications may **not fire** if the threshold is not crossed during this window.

Save as **MemoryThresholdWatch.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryNotificationInfo;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationEmitter;
import javax.management.NotificationListener;
import javax.management.openmbean.CompositeData;

public final class MemoryThresholdWatch {
    private static final BlockingQueue<Notification> EVENTS =
            new ArrayBlockingQueue<>(32);
    private static final AtomicLong DROPPED = new AtomicLong();

    public static void main(String[] args) throws Exception {
        MemoryPoolMXBean selected = null;
        long selectedMax = -1L;

        for (MemoryPoolMXBean candidate :
                ManagementFactory.getMemoryPoolMXBeans()) {
            if (candidate.getType() != MemoryType.HEAP
                    || !candidate.isUsageThresholdSupported()
                    || !candidate.isValid()) {
                continue;
            }
            MemoryUsage usage = candidate.getUsage();
            if (usage != null && usage.getMax() > 0) {
                selected = candidate;
                selectedMax = usage.getMax();
                break;
            }
        }

        if (selected == null) {
            System.out.println("No supported heap usage-threshold pool.");
            return;
        }

        final MemoryPoolMXBean pool = selected;
        final String poolName = pool.getName();
        long oldThreshold = pool.getUsageThreshold();

        // About 80% of the selected pool max; only a DEMO value.
        // max - max/5 avoids overflow from max * 80 / 100.
        long demoThreshold = Math.max(1L,
                selectedMax - selectedMax / 5L);

        NotificationEmitter emitter =
                (NotificationEmitter) ManagementFactory.getMemoryMXBean();

        NotificationListener listener = (notification, handback) -> {
            if (!MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED
                    .equals(notification.getType())) {
                return;
            }
            if (!EVENTS.offer(notification)) {
                DROPPED.incrementAndGet();
            }
        };

        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Notification n = EVENTS.poll(
                            500L, TimeUnit.MILLISECONDS);
                    if (n == null
                            || !(n.getUserData() instanceof CompositeData data)) {
                        continue;
                    }
                    MemoryNotificationInfo info =
                            MemoryNotificationInfo.from(data);
                    if (info == null
                            || !poolName.equals(info.getPoolName())) {
                        continue;
                    }

                    // Parsing and output happen OUTSIDE the callback.
                    System.out.printf(
                            "memory.signal pool=%s usedBytes=%d count=%d%n",
                            info.getPoolName(),
                            info.getUsage().getUsed(),
                            info.getCount());
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } catch (RuntimeException ex) {
                    System.err.println(
                            "Cannot process memory signal: "
                            + ex.getClass().getSimpleName());
                }
            }
        }, "memory-monitor-worker");
        worker.setDaemon(true);

        emitter.addNotificationListener(listener, null, null);
        boolean started = false;
        boolean changedThreshold = false;
        try {
            pool.setUsageThreshold(demoThreshold);
            changedThreshold = true;
            worker.start();
            started = true;

            System.out.println("Monitoring pool: " + poolName);
            System.out.println("Threshold bytes: " + demoThreshold);
            Thread.sleep(15_000L);
        } finally {
            try {
                if (changedThreshold) {
                    pool.setUsageThreshold(oldThreshold);
                }
            } finally {
                emitter.removeNotificationListener(listener);
                if (started) {
                    worker.interrupt();
                    worker.join(1_000L);
                }
                System.out.println(
                        "Dropped queue events: " + DROPPED.get());
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac MemoryThresholdWatch.java
java MemoryThresholdWatch
~~~

**Output depends on the JVM and memory pressure; there is no fixed stdout**. For instance, a run *might* print only:

~~~text
Monitoring pool: G1 Old Gen
Threshold bytes: 3435973836
Dropped queue events: 0
~~~

This is **illustrative output**, not a prediction of pool names or byte counts on a learner's machine. If the JVM has no suitable pool, the program prints a single line:

~~~text
No supported heap usage-threshold pool.
~~~

If the JVM detects a threshold crossing during the run, the worker may print one or more `memory.signal ...` lines. If none occur, **that is not an error**: the program intentionally avoids stressing the heap. Sleep duration is approximate; a process may be stopped/interrupted or subject to OS scheduling.

**Intentional limitations of the example:**
- It configures only a **usage** threshold (not a collection threshold) and picks one heap pool; other pools can still emit notifications if another component set thresholds on them. The worker filters by `poolName`.
- Picking the pool and 80% is purely illustrative; in production, configure/evaluate based on collector, workload, and actual limits.
- Notification data sits in a bounded queue while the worker processes outside the callback. A full queue increments the drop counter without blocking the caller.
- At shutdown, the worker is interrupted; notifications still sitting in the queue may remain unprocessed. Production requires shutdown lifecycle/flushing per requirements and must not treat an in-memory queue as durable.
- If multiple subsystems manage thresholds, never arbitrarily set or restore old values like this demo; enforce a **single owner** or coordination.
- `MemoryNotificationInfo.from(...)` reads the notification's CompositeData; do not assume every JMX notification carries the same `userData`.
- Writing to `System.out` on the worker can still block if the stdout pipe stalls; the crucial point is **not doing it inside the listener**. If the worker stalls, the queue is bounded and has a drop metric.

### 7.1. Brief notes on runnability and thread-safety

- Java 17 supports pattern matching `instanceof CompositeData data` alongside text blocks/records; the program uses only `instanceof` patterns and stable APIs.
- `ArrayBlockingQueue` is thread-safe; `offer` is non-blocking; `AtomicLong` protects the counter under concurrent listener invocations.
- `NotificationEmitter.addNotificationListener(...)` and `removeNotificationListener(...)` pass the exact same `listener` instance.
- In `finally`, the threshold is restored and then the listener is removed; cleanup must also handle the case where the worker hasn't started yet.
- This code is an **observation demo**, without business load-shedding decision logic. It does not assume the JVM emits an exact notification count and avoids synthetic allocations that trigger OOM.

## 8. Production design: tiny signals, bounded workers, safe reactions

### 8.1. Bounded handoff and behavior when the queue is full

| Handoff approach | Benefit | Risks to know |
| --- | --- | --- |
| `ArrayBlockingQueue.offer(signal)` | Non-blocking, explicit capacity | May drop if queue is full; needs a metric |
| `AtomicBoolean.compareAndSet(false, true)` | Coalesces many notifications into one `pending` state | Drops per-event details; worker must reset carefully |
| `BlockingQueue.put(signal)` | Retains all events briefly | **Blocks listener** when queue is full: unsuitable in callbacks |
| `ExecutorService.submit(...)` per notification | Decouples execution from caller | Can spawn many tasks, unbounded queue; overload and allocation |
| Spawning `new Thread(...)` per notification | Easy to write in toy samples | Thread explosion, memory/stack/CPU overhead; never use |

If the goal is **"pool is high, check status and admission"**, you usually do not need to process every notification as a separate transaction. You can **coalesce**: multiple events while the worker is busy simply maintain `needsCheck=true`, and the worker reads the latest usage and decides once. If the goal is auditing every crossing, MXBean notifications are not a guaranteed delivery pipeline; use threshold counts + metrics, and a durable event channel if strictly required.

### 8.2. Coalescing hint with AtomicBoolean

**API illustration**, not a standalone runnable program; assumes a single worker waiting to wake on a queue of capacity 1:

~~~java
if (pending.compareAndSet(false, true)) {
    if (!queue.offer(SIGNAL)) {
        dropped.incrementAndGet();
        pending.set(false);
    }
}
~~~

The worker handles the signal and resets `pending` in `finally`. You must also design against missed wakeups if a new notification arrives while the worker is executing; one way is a `dirty` flag or re-reading latest usage and checking count deltas before clearing. Do not oversimplify to "setting pending=false is enough" without analyzing races. When the need is state observation rather than counting every event, conditional polling on the worker is often easier to verify.

### 8.3. What should the worker do?

Depending on goals:
1. Re-read current usage/collection usage and metrics from reliable sources rather than relying solely on the snapshot inside the notification.
2. Compare `used/committed/max` trends, threshold crossing counts, GC activity, allocation rate, pool growth, and container/cgroup memory.
3. Apply **hysteresis, cooldown, and debounce** so alerts or admission modes do not flap when usage oscillates.
4. If conditions are met, emit **one structured event** with `poolName`, `usedBytes`, `thresholdBytes`, `count`, and `timestamp`, preventing log storms.
5. Coordinate load shedding/offloading per business design, with timeouts and recovery capability.
6. If a heap dump/JFR is genuinely needed, the worker should only **recommend or schedule** it via an approved workflow checking disk/CPU/latency—never trigger it indiscriminately.
7. Monitor `queue_dropped`, worker backlog, callback latency, alert counts, admission state transitions, and recovery duration.

Never let a worker repeatedly call `System.gc()` when usage is high: explicit GC may not yield the expected reclamation, causes large pauses, and does not fix whatever retains objects. Load shedding must look at **both application and JVM/container memory pressure**, not just a single memory pool number.

## 9. Ensuring the callback does not worsen incidents

### 9.1. Things acceptable inside the callback

- Comparing notification types against predefined string constants.
- Attempting a non-blocking `offer` into a pre-initialized bounded queue.
- Updating a lightweight `AtomicBoolean` / `AtomicLong` / counter.
- Returning quickly without opening network connections or blocking.
- Under tight latency constraints, setting only a flag/marker for the latest signal so the worker pulls fresh data itself.

No API guarantees "100% zero-allocation callbacks" on every JVM, yet you should avoid **deliberate large allocations and unbounded work**. Use metrics to detect how long callbacks take or whether they fire continuously; do not instrument by emitting a bulky log event on every callback.

### 9.2. Things that must move to a dedicated worker

- Parsing/formatting large `CompositeData`, calling `getUsage()` periodically across pools, comparing states and trends.
- Writing to loggers, pushing metrics, external notifications, or HTTP requests.
- Retries/backoff, file/database operations, state persistence.
- Trend analysis, workload pause/resume decisions, cooldowns.
- Conditional, bounded heap histograms/heap dumps/JFR with data protection procedures.
- Exception/stack-trace inspection or profiling, when operationally approved.

**Why avoid even logging inside the callback?** Logging can be synchronous, format long strings, contend on an appender lock, or write to a stalled stdout pipe. Under low memory, loggers themselves may allocate. Use a small metric/counter instead and let the worker write aggregated logs over time windows.

### 9.3. Do not expect an "early OOM alarm"

Per the JDK, threshold monitoring is meant for load management / work balancing, **not for reliably detecting and recovering from out-of-memory conditions**. The JVM may:
- Exhaust heap so rapidly that the callback is never delivered in time.
- Hit an OOME in another region unrelated to the pool with the configured threshold.
- Get killed by the container due to cgroup limits/native memory even while Java heap stays below threshold.
- Stall or shut down before the worker processes the signal.

Therefore, combine notifications with **periodic metrics, GC logs/JFR, container memory, and infrastructure alerts**, alongside appropriate admission control/fallbacks. Never rely on a listener as your sole safety mechanism.

## 10. Using counts and snapshot data to avoid misinterpretation

`MemoryNotificationInfo` provides:

| API | Data | Meaning |
| --- | --- | --- |
| `getPoolName()` | String | Pool that triggered the notification |
| `getUsage()` | `MemoryUsage` | Usage snapshot **when the notification was created** |
| `getCount()` | long | Number of times the JVM recorded that threshold type up to notification creation |

Illustrative example: the worker receives:

~~~text
type=java.management.memory.threshold.exceeded
pool=ExampleOld
count=8
usedBytes=430000000
~~~

Yet when the worker samples `pool.getUsage().getUsed()`, it reads `350000000`. This **is not data corruption**; the instant the notification was created and the instant live usage was read can differ, and memory/GC changed in between. Count `8` is not the number of notifications processed by the worker from the queue: the queue may have dropped/coalesced while the count kept rising. Track separately:
- `threshold_count` from the MXBean,
- `notifications_received` by the listener,
- `notifications_enqueued` / `notifications_dropped`,
- `alerts_emitted` / `actions_taken` by the worker.

From a discrepancy between `count` and observed events, **do not immediately assume JMX lost events** without checking other pools, other threshold types, capture times, and the fact that thresholds do not re-fire continuously while usage stays high. Correlate notifications by **same pool + same threshold type + same process lifetime**.

## 11. Testing properly without forcing JVM OOM

### 11.1. Unit testing callback logic separately from the JVM

Since JVM notifications depend on collector and load, **unit test** the queue design directly:
- Call `listener.handleNotification(...)` with mock `Notification` objects having matching and non-matching `type`s.
- Verify non-matching types are not enqueued.
- With a small queue capacity, dispatch many signals and verify `offer` never blocks while the dropped counter increments.
- Verify the worker handles valid `CompositeData`, filters the right pool, and bounds handling of invalid data.
- Verify exceptions in the worker do not prevent subsequent signals from being processed.
- Test shutdown: listener removed, worker stopped, queue drained/closed, and no sensitive info logged.

You do not need heavy memory pressure to test the non-blocking contract.

### 11.2. Integration testing on the target JDK/collector

1. Print the `MemoryPoolMXBean` list and both support flags; pick a pool with defined max and save the old threshold.
2. Use a **bounded-allocation** workload inside a test environment with resource limits while watching memory/GC. Never run an infinite allocation loop just to "force a notification".
3. Set a threshold low enough to exercise in tests without starving the heap, with a restoration procedure.
4. Attach the listener, capture `poolName, usageBytes, count, timestamp` and related metrics; accept that events may arrive delayed or not at all in short windows.
5. Test raising/lowering usage past the threshold if the workload permits to verify rearm semantics; never turn listener call counts into exact timing assertions.
6. When testing collection thresholds, do so only on pools with `isCollectionUsageThresholdSupported()==true` while understanding the collector's GC behavior; never force explicit GC in production.
7. Artificially stall/load the **signal-processing worker** in tests to verify the callback never blocks and the queue drops/coalesces cleanly.
8. Stop the app and verify the listener is removed, the worker stops, and the threshold is restored per ownership policy.

**There is no fixed stdout for integration tests** because every JVM has different pool names, collectors, MaxHeap, and GC timing. Assert **invariants** (right type, right pool, non-blocking callback, bounded queue, accurate metadata) rather than expecting a fixed event count like a golden snapshot.

### 11.3. Key test scenarios

| Scenario | Expected observation |
| --- | --- |
| No pool supports usage threshold | Does not throw; app exits cleanly or falls back to metrics |
| `getMax() == -1` | Does not compute bogus percentages or set nonsensical thresholds |
| Memory crosses usage threshold | Event may appear; count and snapshot make sense, without demanding instant delivery |
| Memory drops below then crosses again | Can rearm and emit events per JVM mechanics |
| Post-GC retained memory exceeds collection threshold | Collection-type event if supported by pool/JVM |
| Queue full | Callback returns quickly, `dropped` counter increments, no blocking |
| Slow worker/collector | Queue stays bounded, with cooldown/log suppression and graceful degradation |
| Callback receives another pool | Worker filters it out without triggering wrong service decisions |
| Listener invoked concurrently | Queue/atomic state stays consistent without corruption races |
| Shutdown/exception | Listener and worker clean up with no leaked threads/tasks |
| Container OOMKilled | Do not rely on memory thresholds as a guaranteed advance alarm |

## 12. Common mistakes

- **Registering the listener on a pool bean instead of MemoryMXBean.** Memory notifications are emitted by `MemoryMXBean`, while thresholds are set on each `MemoryPoolMXBean`.
- **Skipping support checks and calling `setUsageThreshold`.** Not every pool supports it; can throw `UnsupportedOperationException`.
- **Confusing collection usage threshold with usage threshold.** One watches high usage, the other watches what remains after an appropriate GC effort.
- **Believing a threshold notification fires on the exact allocation crossing the line.** The JVM checks at suitable times with no hard delivery deadline.
- **Confusing pool `used` with total process RSS.** Native memory, thread stacks, code cache, and container limits also contribute to memory exhaustion.
- **Setting a threshold above defined max or passing -1.** `set...Threshold` requires non-negative bytes within API bounds.
- **Using the callback to take a heap dump or run GC.** Heavy operations can pause, require I/O, and worsen memory pressure.
- **Calling `BlockingQueue.put`, `Future.get`, or HTTP inside the callback.** Can block notification delivery.
- **Creating a new executor/thread per event.** Risks thread explosion and allocation under low memory.
- **Using an unbounded queue out of fear of losing events.** The queue can grow large enough to cause a secondary OOM.
- **Logging full stack traces inside the callback.** Causes log storms, allocations, and stdout blocking.
- **Missing a dropped counter.** Silently losing signals misleads diagnostics.
- **Assuming notification `count` is how many times the worker processed it.** It is the JVM's detected threshold count, not the queue's processed count.
- **Treating every signal as an isolated incident.** Notifications can arrive repeatedly or late; use debounce/cooldown/hysteresis.
- **Waiting solely for a new notification to resume admission.** Recovery should rely on worker re-checks; there is no automatic "all clear" notification.
- **Forgetting to remove the listener or restore the threshold.** Can leak lifecycle resources or overwrite another component's configuration.
- **Using notifications as the sole OOM protection system.** No guarantee, especially for native/cgroup memory or sudden allocation spikes.

## 13. Production implementation checklist

**On registration:**
1. Identify the exact JVM, collector, pool, memory type, `isValid`, and support flags.
2. Determine whether `max` is meaningful, set threshold in bytes, and establish ownership policy.
3. Clarify whether you want to monitor elevated usage or post-GC retained usage.
4. Set thresholds during controlled lifecycle stages; never mutate them from business requests.
5. Register the listener on `MemoryMXBean` and unregister it on component shutdown.

**Inside the callback:**
1. Filter notification type accurately.
2. Do minimal work, never block, no I/O/network/heap dump/GC.
3. Only `offer` to a bounded queue or flip an atomic flag; maintain dropped/coalesced counters.
4. Never hold huge object payloads or spawn a new worker per event.
5. Guarantee thread-safety if invoked concurrently.

**On the worker:**
1. Parse `CompositeData` into `MemoryNotificationInfo` and filter `poolName`.
2. Re-read live usage/collection usage appropriately instead of treating the old snapshot as current state.
3. Correlate threshold counts with polling, GC metrics, and container signals.
4. Apply cooldown, hysteresis, and rate limits before logging/alerting/changing admission.
5. Handle worker errors, full queues, slow sinks, and shutdown per policy; avoid actions that add memory pressure.
6. Emit compact structured metrics/logs: pool, type, used/committed/max bytes, threshold, count, timestamp, action/outcome.
7. Never trigger heap dumps or explicit GC automatically on every threshold crossing.

**Verification:**
1. Test with real target JVMs/collectors without expecting fixed notification counts.
2. Exercise unsupported pools, undefined max, full queues, and concurrent callbacks.
3. Correlate notifications against memory trends, GC, and container signals.
4. Verify callback duration stays tiny, creates no backlog, and causes no p99 regression.
5. Document clearly that thresholds are **early coordination signals**, not guaranteed recovery from OOME.

**Remember:** `MemoryPoolMXBean` **sets thresholds per pool**, `MemoryMXBean` **emits notifications**, and `MemoryNotificationInfo` **carries the snapshot + count**. Keep `handleNotification` **fast—filter, hand off a tiny signal, and return**; let a dedicated worker decide after reading current state, applying cooldown/hysteresis, and checking resources. That is how you use MXBeans to observe memory pressure without weakening the JVM right when it needs to respond.

### References

- Oracle JDK 17, `MemoryPoolMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html
- Oracle JDK 17, `MemoryMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Oracle JDK 17, `MemoryNotificationInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryNotificationInfo.html
- Oracle JDK 17, `MemoryUsage`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html

Examples and percentage thresholds in this lesson are for learning purposes; verify support levels and notification behavior on your exact running JVM/version before production rollout.