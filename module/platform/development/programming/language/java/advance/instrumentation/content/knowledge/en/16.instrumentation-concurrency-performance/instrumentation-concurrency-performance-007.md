# Bounded Queues, Event Sampling, and Overload Policies

## 1. Why Does Instrumentation Need an Overload Policy?

Java instrumentation can place measurement points at the entry/exit of methods, record traces, logs, metrics, or emit events to an observability system. In high-load applications, the **event-producing path (producer)** often runs on the same thread as the business logic. If a measurement point directly writes to the network, writes to disk, or pushes unbounded events into RAM, the observability layer can become the cause of application slowdowns, out-of-memory errors, or deadlocks.

Suppose a method is called 40,000 times per second. If each call generates two events, `ENTER` and `EXIT`, the potential input rate is 80,000 events/second. If the exporter can only send 30,000 events/second, **the backlog grows by 50,000 events every second** if unbounded, even while the business logic is still operating normally.

This lesson belongs to the **Concurrency and Performance** group of Java instrumentation. We will combine three mechanisms:

1. **Bounded queue:** has a finite capacity and a clear reaction when full.
2. **Event sampling:** decides to keep a subset of information to reduce the number of records that must be processed, prioritizing consistency within an invocation/trace.
3. **Overload policy:** decides whether to block the thread, drop new/old records, degrade, persist to durable storage, or stop exporting data — and measures the resulting data loss.

**Operational goal:** **protect the health of the application first**, keep instrumentation overhead within measurable bounds, and **never report data as “complete” when sampling or dropping has occurred**. A bounded queue only limits a single buffer; it does not automatically bound all resources or guarantee that every event will be successfully sent.

### 1.1. Distinguishing “Event Created” from “Successfully Exported”

~~~text
Business invocation
     |
     v
Entry hook / Recorder
     |
     +--> Minimal business counter (can run for every invocation)
     |
     v
Sampling decision
     |                    \
     | not selected        \ selected
     v                      v
Increment sampledOut       Create small record/snapshot
                            |
                            v
                    Bounded in-memory queue
                      |               |
                      | offer OK      | queue FULL
                      v               v
                 Consumer/worker   Overload policy
                      |               |
                      v               v
                 Serializer       droppedQueueFull++
                      |
                      v
                  Exporter
                      |
                      +--> accepted by sink / retry / failure
~~~

Here, **accepted by queue ≠ exported ≠ persisted by backend**. At least three metric layers are needed: **selected for recording**, **accepted into the buffer**, and **ultimately received by the backend**. A successful `offer` only confirms that the queue accepted the record.

## 2. What Is a Bounded Queue?

In Java 17, `ArrayBlockingQueue<E>` is a `BlockingQueue<E>` implementation backed by a fixed-size array. When creating one:

~~~java
BlockingQueue<TelemetryEvent> queue = new ArrayBlockingQueue<>(1024);
~~~

This is a **code snippet** inside a program that has already declared the `TelemetryEvent` record/class and imported `BlockingQueue` and `ArrayBlockingQueue`; it is not yet a standalone program.

A capacity of 1,024 is the **number of elements**, not the number of bytes. A record with a stack trace or large payload can consume significant RAM even though it counts as a single element. Achieving a hard memory budget requires additional limits on payload size, byte-weight, label count, maximum string length, and memory controls across producers/exporters.

### 2.1. Four Basic Operations and Their Consequences

| Java 17 API | When Queue Is Full/Empty | Suitable for Hot Hooks? |
| --- | --- | --- |
| `queue.offer(event)` | Full: returns `false` immediately if unable to add, **does not wait for a slot** | **Suitable** for a drop-new policy |
| `queue.add(event)` | Full: typically throws `IllegalStateException` | Less suitable; throwing exceptions on every overload is costly |
| `queue.put(event)` | Full: **blocks** the producer until space is available (or interrupted) | Usually **should not** be used in a transformer/advice |
| `queue.offer(event, timeout, unit)` | Waits up to the timeout for space; then returns a boolean | Only when bounded latency is acceptable |
| `queue.poll()` | Empty: returns `null` | Used for non-blocking draining/reading |
| `queue.take()` | Empty: blocks the consumer waiting for an item | Used in a dedicated worker with proper shutdown |

**Technical detail:** `ArrayBlockingQueue.offer` does not wait for the buffer to become non-full, but the implementation may still use a short lock to synchronize the queue. Therefore, “non-blocking at the capacity-waiting policy level” **does not mean lock-free or zero latency**.

`remainingCapacity()` is useful for observability, **not** as an atomic reservation mechanism. Incorrect pattern:

~~~java
if (queue.remainingCapacity() > 0) {
    queue.add(event); // Another thread could take the slot.
}
~~~

Between the two calls, another producer may intervene. Better is:

~~~java
if (!queue.offer(event)) {
    queueDropped.increment();
}
~~~

Both snippets above are **code fragments** assuming `queue`, `event`, and the `queueDropped` counter exist. `offer` checks capacity and inserts in a single queue operation; no pre-check is needed.

### 2.2. Why Are Unbounded Queues Dangerous?

`LinkedBlockingQueue` can be constructed with a capacity, but the default constructor sets the limit to `Integer.MAX_VALUE`, making it practically unbounded for many systems. `ConcurrentLinkedQueue` also enforces no hard capacity. If producers outpace consumers for several minutes, memory and GC pressure grow until the application degrades or hits an OOME.

Do not turn a queue that “has `size()`” into a “bounded” one merely by writing:

~~~java
if (queue.size() < limit) {
    queue.add(event); // Check-then-add is not atomic.
}
~~~

This is an **incorrect code snippet** under multiple producers. You need a genuinely bounded queue or a synchronized admission mechanism, not a `size` check followed by an add as a limit.

## 3. Sampling: Deciding to Drop Before Creating Expensive Data

If raw data volume is too high, **sampling** reduces the amount that must be retained and exported. Key concepts:

- **Head-based:** decides when a request/trace/invocation starts, before knowing the full eventual outcome. Low cost, allowing you to avoid recording payloads for dropped items.
- **Tail-based:** decides after knowing the latency, outcome, or full trace; requires **buffering/storing first** and having expiration/capacity policies.
- **Probability/rate-based:** selects roughly a fraction `p`; you must specify whether it applies per **invocation, event, or trace**, as each behaves differently.
- **Parent-based/consistent trace sampling:** children reuse or stay compatible with the parent/trace decision, avoiding broken trace trees caused by each span sampling independently.
- **Adaptive sampling:** the rate can decrease as pressure rises, but must avoid wild oscillation and preserve critical bounds.

Sampling **is not the same as dropping when the queue is full**. `sampledOut` occurs **by the sampling policy**; `queueDropped` occurs due to **insufficient buffer capacity** after selection. They must be counted separately because their causes and statistical biases differ.

### 3.1. The Sampling Decision for the Same Invocation Must Be Consistent

If recording two events:

~~~text
ENTER(id=72)
EXIT (id=72)
~~~

do not draw lots independently:

~~~java
if (randomAtEnter()) emitEnter(id);
if (randomAtExit())  emitExit(id);
~~~

This is **Java pseudocode** with undefined functions. Two independent selections can produce an `ENTER` without an `EXIT` or vice versa.

The right approach: create a **token/scope** at entry, store `sampled` on the token, and use **that same decision** when exiting the method. If sampling at the trace level, propagate the decision along with the trace context across threads/processes, rather than re-randomizing in each child.

### 3.2. Stable Hashing Is Better Than Sequence Parity in Production

The runnable example in Section 7 uses `id % 2 == 0` so that the output is **completely reproducible**. That is **only a deterministic test exercise**, **not a production sampling algorithm**. Sequential IDs can correlate with request order, tenants, or bursts and introduce bias.

In production, consider:

- Using a trace ID with sufficient entropy and a stable hash function to decide according to the rate; all components must share a consistent convention.
- Or using `ThreadLocalRandom.current().nextDouble() < p` for **a single decision at entry**, keeping that decision until exit. If cross-service consistency is required, independent local randomness is not enough.
- When sampling by tenant/endpoint, track each group's rate explicitly; do not treat sampled data as a uniform random sample if certain types are prioritized.
- A 10% sampling rate does **not** mean keeping exactly 10% in every small window; it is the expected distribution with proper random samplers.

### 3.3. Head Sampling Does Not Guarantee Catching Every Error

If a failed request is only known **after it finishes**, an early-deciding head sampler cannot guarantee keeping every failed request. There are three options:

1. **A small, always-on error counter:** keeps a `failures` metric for every invocation without storing the full event payload.
2. **Tail sampling:** holds events in a bounded buffer to decide later, trading off higher memory/latency cost.
3. **Recording an additional out-of-sample “error summary”:** upon failure, attempt to submit a priority record to a channel with separate admission; it can still be dropped when the buffer is full, and cannot promise “zero loss”.

Do not claim that a 1% head sampler “captures 100% of errors” without an additional mechanism or an explicit priority model.

## 4. Policies When the Queue Is Full: Choose Upfront, Do Not Improvise in the Hook

| Policy | When No Slot Remains | Benefits | Risks/Conditions |
| --- | --- | --- | --- |
| **Drop-new** | `offer` returns false, increment counter, discard current event | Producer latency is bounded by a short queue operation; simple | Loses new events, may miss newly occurring errors |
| **Drop-oldest** | Evicts an old record to make room for the new one | Keeps the most recent data, suitable for some dashboards | Breaks history/sequences, can starve older events |
| **Bounded wait** | `offer(timeout)` waits up to a time limit | Reduces drops during short bursts | Increases tail latency, can accumulate across a request |
| **Block/put** | Waits until the queue has a slot | May avoid drops while the consumer still makes progress | Hot path held indefinitely, deadlock/throughput collapse |
| **Spool to disk** | Persists to a secondary bounded-quota buffer | Survives longer exporter outages | Disk I/O/FS full, replay, security, durability, and cleanup complexity |
| **Reduce/aggregate** | Keeps only counters/histograms or summaries | Useful when detailed traces are not essential | Loses detailed correlation/stack traces |
| **Disable/degrade instrumentation** | Temporarily reduces/suspends expensive probes | Protects the application during severe incidents | Observability gaps; requires alerts and recovery mechanisms |
| **Fail-closed** | Rejects business requests because telemetry was lost | Suitable only for mandatory audit requirements by design | Should not be used for normal tracing/metrics |

**Default recommendation for a performance observability agent:** choose **bounded queue + early-decision sampling + drop-new with counters**; run the exporter on a dedicated thread, and never let the producer wait on network/disk. This is a **fail-open policy**: instrumentation does not cause business requests to fail merely because telemetry cannot be sent. It is an operational choice, **not** a requirement of the Java API.

For **regulatory audit or mandatory-recording transaction** systems, losing events may be unacceptable. In those cases, you must use a dedicated transactional/durable log/conditional-commit design, rather than “sneaking” them into the same tracing queue and promising zero data loss.

### 4.1. Drop-Oldest Can Break ENTER/EXIT Pairs

Suppose the queue holds two events `ENTER(id=1)` and `ENTER(id=2)`. To make room for `EXIT(id=1)`, drop-oldest will evict `ENTER(id=1)` — leaving an `EXIT` with no entry. Drop-new, conversely, could drop `EXIT` and leave an orphaned `ENTER`.

Therefore, if you need **per-invocation integrity**, merely choosing “drop-new or drop-oldest” is **not enough**. You must design the format/admission: a complete envelope, atomic record groups, or an “incomplete”/reconciliation marker.

### 4.2. Why Is `put` Dangerous in an Agent?

A business method holding a lock calls an instrumentation point. If the queue is full, `put` waits for the exporter. If the exporter or a component it relies on also depends on a lock/resource held by the business thread, a **wait cycle** can form. Even without a deadlock, waiting causes bad p99 latency and stalls thread pools.

In particular, performing blocking I/O inside `ClassFileTransformer.transform` can stall class loading, leading to reentrancy or class initialization dependencies. A bounded queue **must be paired with an appropriate drop/wait policy**, not just a capacity limit.

## 5. Keeping Event Pairs Intact: One Complete Envelope Instead of Two Enqueues

When the goal is to record a completed method invocation, you can represent the outcome as **a single record**:

~~~text
CompleteCall {
    invocationId,
    methodKey,
    outcome: OK | ERROR,
    startNanos?,
    durationNanos?,
    traceId?,
    attributes?
}
~~~

Instead of enqueuing `ENTER` and `EXIT` independently, the recorder stores the sampling decision and context on a **frame/token while the method runs**, then **enqueues one `CompleteCall` in `finally`**. A single `offer` either **accepts the whole record or rejects the whole record**; it cannot lose only `ENTER` due to a full queue.

**Trade-off:** the record only appears after the method finishes. For very long-running invocations or if the JVM crashes mid-call, the backend **has no “in-progress” trace yet**. If live span monitoring is required, you need a dedicated design for streaming event pairs with capacity headroom, correlation IDs, TTLs, and incomplete-marking support.

~~~text
ENTRY
  -> assign invocationId
  -> decide sampled once
  -> create small scope on call stack
  -> run business method
EXIT in finally
  -> if sampled: combine outcome + duration into ONE record
  -> offer(record) ONCE
  -> if full: increment droppedQueueFull
~~~

**Note:** the producer can still die/crash before `finally`; a single envelope avoids **partial admission**, but does not guarantee “every invocation has a record.” Data-loss policies must still have counters/diagnostics.

## 6. Avoiding Counter Confusion Under Sampling + Overload

We can separate the stages:

| Counter | Incremented When | Not |
| --- | --- | --- |
| `calls` | An invocation enters the hook | Number of exported events |
| `businessFailures` | The business body exits via an exception caught by the hook | Number of retained error records |
| `sampled` | An invocation is selected by the head sampler | Number of events that entered the queue |
| `notSampled` | The sampler intentionally skips the invocation | Events lost to overload |
| `accepted` | `queue.offer(record)` succeeds | Confirmation that the backend persisted it |
| `queueDropped` | `queue.offer(record)` returns false due to full queue | Unselected sampling decisions |
| `exported` | The consumer completes a local export operation as defined | Guarantee of end-to-end durable persistence if exporter has not acknowledged |
| `exportFailures` | Exporter send fails or exhausts retries | All business failures |

When **all invocations have finished** and the exporter has not yet run:

~~~text
calls   = sampled + notSampled
sampled = accepted + queueDropped
queue.size() = accepted      (only in the demo if the queue has not drained)
~~~

After the **consumer successfully drains the entire queue** and no new producers are running:

~~~text
exported = accepted
queue.size() = 0
~~~

These are **invariants for a single-producer demo with no retries**. In a continuously running multi-threaded system, `LongAdder.sum()` is not an atomic snapshot; do not assert those equalities via separate reads while updates are in flight. Production also has rejections, serializer errors, worker crashes, and dedicated counters for them.

**The meaning of “loss” depends on the observation boundary:** head-sampled-out is **intentional sampling**, queue-drop is **overload**, and export failure is a **delivery failure**. Merging all three into a single `dropped` counter leaves operators unable to tell whether to enlarge the queue, scale the exporter, or adjust the sampling rate.

## 7. Standalone Java 17 Example: Queue Capacity 2, 1/2 Sampling, Drop-New

The following example produces **deterministic** stdout. It intentionally **does not start a consumer** until all producers finish, to demonstrate a full queue and `offer` behavior reproducibly. In production, the consumer must run continuously on a dedicated worker with bounded resources.

**Complete file: `BoundedTelemetryDemo.java`**

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class BoundedTelemetryDemo {
    record CompleteCall(long id, String method, String outcome) { }

    static final class Recorder {
        private final AtomicLong sequence = new AtomicLong();
        private final ArrayBlockingQueue<CompleteCall> queue =
                new ArrayBlockingQueue<>(2);
        private final LongAdder calls = new LongAdder();
        private final LongAdder businessFailures = new LongAdder();
        private final LongAdder sampled = new LongAdder();
        private final LongAdder notSampled = new LongAdder();
        private final LongAdder accepted = new LongAdder();
        private final LongAdder queueDropped = new LongAdder();
        private final LongAdder exported = new LongAdder();

        void invoke(String method, Runnable body) {
            long id = sequence.incrementAndGet();
            calls.increment();
            boolean keep = id % 2 == 0;  // Only for a deterministic demo.
            if (keep) {
                sampled.increment();
            } else {
                notSampled.increment();
            }
            String outcome = "OK";
            try {
                body.run();
            } catch (RuntimeException | Error exception) {
                outcome = "ERROR";
                businessFailures.increment();
                throw exception;
            } finally {
                if (keep) {
                    CompleteCall result = new CompleteCall(id, method, outcome);
                    if (queue.offer(result)) {
                        accepted.increment();
                    } else {
                        queueDropped.increment();
                    }
                }
            }
        }

        void reportAndDrain() {
            System.out.println("calls=" + calls.sum());
            System.out.println("businessFailures=" + businessFailures.sum());
            System.out.println("sampled=" + sampled.sum());
            System.out.println("notSampled=" + notSampled.sum());
            System.out.println("accepted=" + accepted.sum());
            System.out.println("queueDropped=" + queueDropped.sum());
            System.out.println("queueDepthBeforeDrain=" + queue.size());
            CompleteCall item;
            while ((item = queue.poll()) != null) {
                System.out.println("event=" + item.id() + "|"
                        + item.method() + "|" + item.outcome());
                exported.increment();
            }
            System.out.println("exported=" + exported.sum());
            System.out.println("queueDepthAfterDrain=" + queue.size());
            boolean accounting = calls.sum() == sampled.sum() + notSampled.sum()
                    && sampled.sum() == accepted.sum() + queueDropped.sum()
                    && exported.sum() == accepted.sum() && queue.isEmpty();
            System.out.println("accounting=" + accounting);
        }
    }

    public static void main(String[] args) {
        Recorder recorder = new Recorder();
        for (int i = 1; i <= 10; i++) {
            final int call = i;
            try {
                recorder.invoke("work", () -> {
                    if (call == 4 || call == 9) {
                        throw new IllegalStateException("business failure");
                    }
                });
            } catch (IllegalStateException expected) {
                // Keep the demo running; no producer-side logging.
            }
        }
        recorder.reportAndDrain();
    }
}
~~~

### 7.1. Compile and Run

Requires only JDK 17 or later, with no Java agent or third-party libraries:

~~~bash
javac --release 17 BoundedTelemetryDemo.java
java BoundedTelemetryDemo
~~~

**Exact stdout**, verified on OpenJDK 21 with `javac --release 17`:

~~~text
calls=10
businessFailures=2
sampled=5
notSampled=5
accepted=2
queueDropped=3
queueDepthBeforeDrain=2
event=2|work|OK
event=4|work|ERROR
exported=2
queueDepthAfterDrain=0
accounting=true
~~~

Explanation:

1. There are **10** `work` invocations.
2. Two calls, ID 4 and ID 9, throw `IllegalStateException`, so `businessFailures=2` even when records are not kept for both.
3. The demo decides to keep **even** IDs, so `sampled=5` (2, 4, 6, 8, 10) and `notSampled=5` (1, 3, 5, 7, 9).
4. The buffer of capacity **2** is not drained while the producer runs: ID 2 and ID 4 are accepted; IDs 6, 8, and 10 get `false` from `offer`.
5. Hence `accepted=2` and `queueDropped=3`. **ID 9 has a business failure but is not in the sample** — a concrete illustration that head sampling does not retain every error.
6. `event=4|work|ERROR` is a **complete record** containing both ID and outcome; there are no separate ENTER/EXIT events to pair across two queue operations.
7. After draining, `exported=2` by the definition of **successfully printing to stdout**, not real network export; the queue is empty and the accounting equations hold.

**Do not misread the output:** `exported` in the demo only means the consumer printed the record to stdout. Production must measure ack/ingest or the exporter/backend's own guarantees; do not use this term to promise that data has been durably persisted in an external system.

### 7.2. Analyzing Key Code Instrumentation Points

**A. Generating a Unique ID and Counting Every Invocation**

`AtomicLong sequence` assigns a unique ID within a `Recorder`, even across multiple producer threads. `calls.increment()` runs **before** sampling. Thus total counting does not depend on the backend, when the goal is to count all calls rather than only sampled records.

**B. Sampling Once at Entry**

`boolean keep` is bound to the current invocation and is not re-drawn in `finally`. The demo uses even/odd parity for exact reproducibility; with a real trace ID hash or head sampler, you still keep one `keep` per invocation.

**C. Recording the Outcome at the Exact Boundary**

`try/catch/finally` catches `RuntimeException | Error` from `Runnable.run()`, records `ERROR`, and **rethrows the same exception**. `finally` emits the complete record when selected. A business-body error is never turned into a successful return just because of the recorder. However, recorder code in `finally` can still hit severe errors such as OOME; production code must have proper fail-open design and allocation bounds.

**D. Using `offer` Instead of `put`**

When the queue is full, increment `queueDropped` and let the business thread continue without waiting for the consumer. This is an explicit drop-new policy.

**E. Consumer Drain as a Separate Step**

`queue.poll()` takes each record, prints it, and increments `exported`. The demo waits for the producer to finish before draining so all results are deterministic. Production uses a dedicated consumer/exporter so the system runs continuously; in that case, never assume the queue is always full with exactly two records.

### 7.3. Small Variation Exercises

Try changing the capacity from 2 to 3 and re-running. With the same sampled IDs and no early drain, `accepted` is expected to rise to 3, `queueDropped` to drop to 2, and the queue to hold the first three selected IDs (2, 4, 6). `calls` remains 10 and `businessFailures` remains 2: telemetry capacity **should never alter business outcomes**.

Try replacing `id % 2 == 0` with `id % 5 == 0`: across 10 invocations, IDs 5 and 10 will be selected. This is still just a deterministic exercise, not unbiased sampling under real traffic.

## 8. Why Does the Example Not Run a Continuous Consumer Thread?

For learning purposes, we need to separate two properties:

- **Behavior when full:** there must be a way to fill the queue in a verifiable order.
- **Operating system:** the consumer should drain concurrently with producers, with batching, export, retries, and shutdown.

If a real consumer ran in the deterministic demo, thread scheduling could cause it to take items before the producer finished; `accepted`/`queueDropped` would no longer be fixed across runs. The demo intentionally **separates phases** so stdout can be verified 100% exactly.

A production consumer might be structured like:

~~~java
while (running || !queue.isEmpty()) {
    Event event = queue.poll(100, TimeUnit.MILLISECONDS);
    if (event != null) {
        exporter.send(event);
    }
}
~~~

This is **Java pseudocode**; `running`, `Event`, `queue`, `exporter`, and handling of `InterruptedException`/exporter exceptions must be defined; **it is not a standalone program**. In practice, you must bound flush time, retry count, and batch size, and ensure shutdown does not keep the JVM alive forever.

Never treat `queue.poll()` returning `null` as meaning the exporter is completely empty across the whole system: another producer may enqueue immediately afterward, and records may still be in batches or in-flight over the network.

### 8.1. Batching and Metric Accounting

The consumer can use `drainTo(batch, maxBatchSize)` and send a batch, saving syscalls/network round trips compared to one request per event. However:

- If sending **a batch fails**, decide whether to retry **the whole batch or individual records** and cap the retry count.
- If the backend can ingest a partial batch, a single overall ACK does not necessarily prove all records were persisted; understand the exporter contract.
- Use a correlation key/sequence/traceId if the backend must deduplicate on retries.
- Do not create unbounded batches with `drainTo(all)` and hold a huge list under heavy load; cap `maxBatchSize` and the number of in-flight batches.
- Protect shutdown: a worker must not retry indefinitely when the downstream system is down, preventing the application from exiting.

A single consumer produces FIFO dequeue order in `ArrayBlockingQueue`, but **does not automatically guarantee arrival order at the backend** when there are multiple workers, retries, batching, or network transit. If per-trace ordering matters, you need an appropriate partitioning/ordering strategy and event IDs.

## 9. Multithreaded Correctness: Bounded Queues and Counters

`ArrayBlockingQueue` supports multiple concurrent producers and consumers. `AtomicLong` provides sequence numbers safely, and `LongAdder` is suited for aggregating high-frequency counters. Even so, several details must be understood:

1. **`offer` is atomic for adding a single item**, not atomic with `accepted.increment()`. A thread may enqueue and then be paused while another thread reads the counters before it increments; this is a transient snapshot, not corruption.
2. **`LongAdder.sum()` is not an atomic snapshot** while multiple threads are updating; do not assert cross-counter equations while the system is active.
3. **`ArrayBlockingQueue.size()` changes continuously**; treat it only as a point-in-time pressure indicator, not proof of end-to-end loss.
4. **`remainingCapacity()` does not reserve a slot** under multiple producers; rely on the return value of `offer`.
5. **Each invocation keeps its own `sampled` state**; never share a static boolean across nested calls or threads.
6. With `ThreadLocal<Scope>` or a stack, clean up after the outermost exit so thread pools do not retain stale context. If handing off to another async thread, propagate context intentionally.
7. Helper/recorder/logger classes must be excluded from instrumentation scope to avoid the tool generating recursive events from itself.

### 9.1. A Bounded Queue Does Not Mean the Whole Pipeline Is Bounded

Even when `queue` has a capacity of 1,024:

~~~text
Producer stack/context/payload still held
         |
         v
Queue 1024 records
         |
         v
Consumer batch 500 records
         |
         v
HTTP in-flight 20 requests x 500 records
         |
         v
Retry buffer / spool
~~~

Total telemetry-related memory also lives in producers, batches, network clients, retry buffers, serialization buffers, text strings, and stack traces. Stability requires **separate budgets for each layer**, including limits on concurrent exports and timeouts.

### 9.2. Fairness and Overhead

`ArrayBlockingQueue` has a constructor accepting `fair=true`. Fairness can reduce starvation of waiting threads, but the Javadoc notes it usually lowers throughput. With an `offer` strategy that drops new events, **do not enable fairness thinking the queue will become “fair per tenant”** — lock/wait fairness is not a per-tenant quota. You need separate partitions/counters for fairness across tenants or services.

## 10. Capacity Estimation and Identifying Overload

Let:

- `R` = invocations/s entering the recorder;
- `p` = sampling rate kept at entry (0–1);
- `e` = queue records per selected invocation (with a **complete envelope**, `e = 1`; with two separate events, typically `e = 2`);
- `λ = R × p × e` = rate of records **trying to enter the queue**;
- `μ` = sustainable consumer/exporter processing rate in the same unit (records/s);
- `C` = queue capacity in records.

If `λ > μ` persists, the backlog grows by roughly `λ - μ` records/s until the queue hits `C`. Assuming the queue starts empty and rates are relatively steady, the time to fill is **approximately**:

~~~text
time_to_full ~= C / (lambda - mu)  (if lambda > mu)
~~~

This is an **average capacity estimate**, not a formula for predicting exact timing in bursty/concurrent systems.

**Example:** an application has `R=20,000` calls/s, keeps `p=10%`, and each kept call produces one envelope. Thus `λ=2,000` records/s. The exporter only processes `μ=1,500` records/s. If `C=500`, the backlog grows by about **500 records/s**; the buffer fills in roughly **1 second** if rates stay constant.

Even if the exporter is fast enough on average (`λ < μ`), the buffer can still fill during short bursts or exporter pauses (GC, DNS, network). Capacity should be sized based on **burst tolerance**, exporter latency, and acceptable memory/latency bounds, not just average frequency.

### 10.1. A Finite Queue Capacity Does Not Set a Hard Byte Budget

If an event payload averages 256 bytes, 500 records correspond to at least about 128,000 bytes **considering only average payload**. Actual heap size also includes object headers, references, backing string/byte[] arrays, alignment, unusually large records, batches, and client buffers. **Never** multiply 500 × 256 and claim total heap usage is guaranteed to be only 128 KB.

You should bound payloads (class/method names, stack trace depth, baggage, attribute count, and value length) and measure actual JVM allocation. For payloads of highly variable size, you may need a queue tracking a **byte budget** via a semaphore/weight alongside the count cap.

### 10.2. When Does Increasing Capacity Fail to Solve the Problem?

If `λ > μ` continuously, increasing `C` only **delays** the time until full. Sustainability requires reducing the input rate (sampling, aggregation, filtering) or increasing export capacity (batching, appropriate workers, backend capacity). When the exporter/network is completely down (`μ≈0`), even a huge buffer will eventually fill.

Do not assume “queue size equals 0” is always good: it could mean producers are idle or instrumentation was disabled. Always read it alongside `calls`, `sampled`, `accepted`, `queueDropped`, and export throughput.

## 11. Sampling, Statistics, and Bias Under Queue Drops

A sampler with probability `p` can allow estimating total events from the sample **when sampling conditions are appropriate**. However, if **overload drops** also happen after sampling, the final retention probability is no longer just `p` and may depend on time, method, tenant, payload size, or exporter latency.

Example:

~~~text
100,000 calls
  | head sampling 10%
  v
10,000 selected
  | queue full, only 4,000 accepted
  v
4,000 accepted
  | exporter errors, backend receives only 3,800
  v
3,800 observed records
~~~

If a dashboard multiplies 3,800 × 10 to conclude there were 38,000 calls, it is **wrong**, because it ignores queue drops and export failures. If sampling is not uniformly random or prioritizes errors/slow requests, multiplying by `1/p` can be wrong even without queue drops.

In practice, prefer:

- **Always-on, low-cardinality counters:** total calls/failures/latency histograms from a controlled source, not derived from raw trace samples when complete metrics are needed.
- **Sampled traces:** used to diagnose example execution paths, not assumed to be the complete population.
- **Loss accounting:** shows how many records were selected, dropped due to queue full, or rejected/exhausted retries at the exporter.
- **Sampling rate by version/time/tenant:** provides context for statistical analysis and avoids mis-scaling.
- **Latency statistics:** control for sampling bias; if slow requests are prioritized, the retained trace distribution is not the true underlying distribution.

### 11.1. Do Not Let Metric Labels Explode

Incrementing `queueDropped` on each drop is cheap when label count is small. However, creating a metric label for `invocationId`, `rawUrl`, `exceptionMessage`, or a full stack trace per record causes massive cardinality/memory/CPU overhead inside the telemetry system itself.

Relatively safe labels may include `service`, `methodGroup`, `dropReason`, `exporter`, or a bounded/well-defined tenant identifier by design. Store detailed data only inside sampled records under quota.

## 12. Adaptive Sampling Under Changing Pressure

A fixed rate (e.g., 5%) may suffice under steady load. Under bursts, however, a controller can adjust `p` to keep pressure within bounds.

Conceptual pattern:

~~~text
Each monitoring window:
  offeredRate, acceptedRate, dropRate, queueFillRatio,
  exporterLatency, exporterErrorRate

If fillRatio is persistently high and dropRate rises:
  step down sampleProbability within bounds

If fillRatio is persistently low and exporter is stable:
  recover sampleProbability more slowly

Always enforce minRate/maxRate, hysteresis, cooldown,
and a mechanism to keep critical metrics outside raw sampling.
~~~

This is a **descriptive algorithm**, not a drop-in production program. Mandatory points:

- **Do not re-draw for the same invocation** if `p` changes between `ENTER` and `EXIT`; store `sampled` in the scope/token.
- When trace-level sampling is used, propagate the decision to children/upstream/downstream per convention; do not apply a new rate mid-trace and break the trace.
- Use **hysteresis/cooldown** to prevent `p` from oscillating rapidly with queue fluctuations.
- Do not react solely to `queue.size()`: include drop rate, exporter errors, latency, and offered rate.
- Set a floor so observability is not lost completely unless system policy requires shutting it off; exceptions/audits may need a separate channel.
- Record `sampleProbability` alongside exported data if the goal is population estimation over time.

**Important:** adaptive sampling reduces recording demand, but **does not guarantee** zero record loss when full. The consumer can still lose connectivity completely, so the queue must still have an explicit drop/spool policy.

## 13. Protecting the Hot Path: Fail-Open Must Be Implemented Carefully

Java agents are often injected into bytecode on very hot methods or sensitive classes. Instrumentation logic needs to:

1. **Skip early** classes/methods that do not need measurement; avoid parsing or building payloads when sampling has already excluded the call.
2. **Never call loggers/network/exporters synchronously** inside hot transformers/advice; the logging framework itself might be instrumented, causing reentrancy.
3. **Minimize allocations** on the hot path: do not build stack traces or JSON strings for every call if only 1% are kept.
4. **Use low-cardinality counters** to distinguish business failures, sampled-out, queue-full, serializer failures, and export failures.
5. **Create a token per invocation**, storing decision/outcome/time per frame for nested/recursive calls.
6. **Never block class loading** due to a full queue; avoid `put` and lock cycles around network I/O.
7. **Never alter business method semantics** because an event was dropped: business exceptions must be preserved and return values unchanged.
8. **Never swallow severe underlying errors:** handling of `OutOfMemoryError`, `ThreadDeath`, crashes, or recorder errors must be designed and tested explicitly; do not catch `Throwable` and pretend everything succeeded.

**Distinguishing demo from production:** `BoundedTelemetryDemo` is intentionally simple, allocates `CompleteCall` in `finally`, and lacks guards against recursion from logging libraries. In real agent bytecode advice, isolate helpers/recorders from instrumentation scope, guard safely when allocation or enqueuing fails, and establish explicit fail-open diagnostic policies. Do not copy the demo and claim all JVM-level edge cases are handled.

### 13.1. Do Not Force Audit Reliability Onto a Queue Built for Performance Telemetry

If regulations or business contracts require **every transaction to have a durable audit record**, putting audits into a sampled queue with drop-new on full violates that requirement. Such designs require a transactional outbox, durable storage, or an appropriate commit policy. Note the differences:

| Goal | Priority | Example Approach |
| --- | --- | --- |
| Performance trace | Protect the application; accept counted loss | Bounded queue, head sampling, drop-new |
| Diagnostic error summary | Needs higher retention; still bounded by quota | Separate priority lane, always-on counters, bounded buffering |
| Mandatory audit | Must not silently drop records per business rules | Durable/transactional write, fail-closed when required by policy |
| Local dev debugging | Temporary overhead acceptable | Higher sampling, controlled direct logging |

Do not apply one policy to all data just because everything is called an “event.”

## 14. Consumer/Exporter: Failures Behind the Queue Are Still Data Loss

A producer may enqueue successfully, yet the exporter can:

- Time out or return an HTTP error.
- Deliver only part of a batch.
- Retry and create duplicates if an ACK is lost.
- Be shut down before flushing.
- Hit bandwidth/quota limits or be rejected by the backend for cardinality/size.
- Fail to verify that records were actually persisted at the sink.

Therefore:

- Maintain separate **exporter failure counters**, retry counters, and queue/worker shutdown metrics.
- If using retries, **bound attempts, elapsed time, backoff, and the number of retained records**, avoiding turning the retry queue into unbounded memory.
- Use **idempotency/correlation keys** if the backend supports them to reduce duplicates on retry.
- On shutdown, stop/throttle producers, drain up to a deadline, and report remaining records; do not claim a flush succeeded merely because `shutdown()` was called.
- If shutdown/crash can lose the in-memory queue, **document the guarantee clearly**: an in-memory queue is not durable across process death.

**Never synthesize a fake “EXIT OK”** to fill in a trace missing an event due to exporter failure. Missing data must be marked dropped/unknown/incomplete depending on the model, never fabricated into a business outcome.

## 15. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using an unbounded `ConcurrentLinkedQueue` for all events | Heap/GC grows to OOME when exporter is slow | Bounded buffer + limits on other layers |
| Using `put` in Java advice | Business threads wait, p99 spikes or deadlocks | `offer`/bounded wait with a clear policy |
| Checking `remainingCapacity` then calling `add` | Race condition under multiple producers | Single `offer` and check the return value |
| Using `queue.add` and letting full-queue exceptions leak into the app | Telemetry breaks business logic | Handle saturation without exceptions |
| Independent random draws at ENTER/EXIT | Orphaned event pairs | Store sampling decision in scope |
| Keeping only `ENTER` or `EXIT` when queue has space | Torn traces | One complete envelope or paired admission |
| Using sequence parity as a production sampler | Can be biased by traffic/order | Trace ID hash/parent-based or a designed sampler |
| Calling `sum()` on multiple `LongAdder`s under load and asserting equality | No atomic snapshot | Test after quiescence or use synchronized snapshots |
| Assuming capacity 1,024 means 1,024 bytes | Payloads can still be huge | Bound bytes/event and auxiliary data |
| Increasing queue capacity endlessly when exporter is chronically slower | Only delays time to full | Reduce λ or increase μ |
| Treating accepted as durably exported | Loss can still happen after queue/worker/network | Count accepted/exported/ack separately |
| Multiplying observed trace count by 1/p despite queue drops | Biased estimates | Always-on counters and loss accounting |
| Using one metric for sampled-out, queue-drop, and export failure | Cannot diagnose root cause of data loss | Separate counters with reason labels |
| Spawning a new thread per event | Thread/stack/GC explosion | Bounded worker pool |
| Letting the agent instrument its own exporter | Recursive emission, queue self-fills | Exclude agent/helper/logger/exporter |
| Not cleaning up `ThreadLocal` in thread pools | Old request context leaks to new requests | Remove/restore context when outermost scope exits |
| Unbounded retries with no quota | “Bounded queue” defeated by retry layer | Bounded retries/timeouts/backoff |
| Using drop-oldest for enter/exit streams | Can drop entry and keep exit | Atomic envelope or reconciliation |
| Giving all errors “unlimited priority” | Priority queue also overloads | Dedicated quota, clear fail-open/audit policy |
| Not checking plugin/module/class loaders | Helpers fail to resolve or static counters split | Proper class-loader visibility/bridge design |

## 16. Test Suite Needed Before Production Rollout

**Logic tests:**

- [ ] `ArrayBlockingQueue` of capacity 2 accepts exactly 2 records; the 3rd add is rejected before draining.
- [ ] `offer` when full does not wait for the consumer to free space; tests avoid overly tight timing thresholds to prevent flakiness.
- [ ] `calls` does not depend on sampling/queue/export succeeding.
- [ ] `ERROR` outcome is preserved when an exception crosses the method boundary; errors are never turned into normal returns.
- [ ] One invocation uses **one sampling decision** from entry to exit.
- [ ] When using streaming pairs, test queue-full between ENTER and EXIT; verify incomplete-handling design.
- [ ] After **all tasks have completed**, verify `calls = sampled + notSampled` and `sampled = accepted + queueDropped` within the corresponding test scope.
- [ ] Exporter retries/partial success do not cause false acks or uncontrolled duplicates.

**Load tests:**

- [ ] Producer rate lower than, equal to, and higher than consumer rate.
- [ ] Short bursts, network outages, and exporter pauses or multi-minute slowdowns.
- [ ] Multiple producers/consumers, thread pool reuse, and concurrent class loading.
- [ ] Large event payloads/deep stack traces; measure heap/GC and allocations at the hook.
- [ ] Sampling rate changes mid-invocation; token still uses the initial decision.
- [ ] With trace-level sampling, verify parent/child continuity across threads/processes.
- [ ] Different JVM runtime configurations, deadline-based shutdown, and flushing on lost connections.
- [ ] Drop counters increment with accurate reasons; dashboards distinguish dropped vs. intentionally sampled-out.

**Instrumentation safety tests:**

- [ ] Agent does not re-instrument its own helpers/recorders/loggers/exporters.
- [ ] When the exporter is down, business logic still returns the right result/exception per fail-open policy.
- [ ] No blocking I/O or unbounded queue waits inside `ClassFileTransformer`.
- [ ] High-cardinality metrics are controlled; samples/payloads stay within quota.
- [ ] Bounded behavior under memory pressure; no self-triggering logging loops.
- [ ] If the system requires lossless audit, use a separate durable path and test fail-closed behavior as required, never silent drop-new.

### 16.1. Self-Check Questions

1. How do `ArrayBlockingQueue.offer(e)` and `put(e)` differ when the queue is full?
2. Why is checking `remainingCapacity() > 0` before `add` unsafe with multiple producers?
3. How do `sampledOut`, `queueDropped`, and `exportFailures` differ?
4. Why must a head sampling decision be stored throughout an invocation?
5. What kind of event loss does a complete-call envelope solve, and what kind does it **not** solve?
6. Why can events still be lost even when `queue.offer` returns true?
7. With `R=20,000` calls/s, `p=0.1`, `e=1`, `μ=1,500` records/s, and `C=500`, roughly how long until the buffer fills if there are no changing bursts?
8. When `businessFailures=2` but the queue only has one error record left, should the business failure counter be adjusted down to 1?
9. Why is `id % 2 == 0` only suitable as a deterministic demo?
10. Why is `LongAdder.sum()` unsuitable for asserting cross-counter consistency while the system is running?
11. When is a drop-new policy disallowed due to audit/transaction requirements?
12. Why does increasing capacity not save a pipeline if producers **continuously** outpace the exporter?
13. When wanting to tail-sample all slow/error requests, what state-storage budget is needed?
14. Why can a record-count-bounded queue still cause RAM usage to spike?
15. How can you know which records the tracer kept without altering business method results?

**Remember:** For performance instrumentation, **sample early and consistently**, **put small records into a bounded queue**, use an **explicit full-queue policy**, and **count telemetry loss causes accurately**. `offer` + drop-new is usually more suitable than `put` on the hot path; however, accepted does not mean persisted. A post-invocation envelope avoids losing half of an event pair due to a full queue, while bounded queues and adaptive sampling are only effective alongside **bounded consumers, bounded retries, clean shutdown, and monitored resources**. The goal is not to save every trace at all costs, but to protect the application and always know how much data is missing.

### References

- [Java 17 — ArrayBlockingQueue: capacity, offer, put, poll, fairness](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [Java 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [Java 17 — AtomicLong and LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Java 17 — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html)
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [OpenTelemetry — Trace sampling: head/tail/parent-based and trade-offs](https://opentelemetry.io/docs/concepts/sampling/)
