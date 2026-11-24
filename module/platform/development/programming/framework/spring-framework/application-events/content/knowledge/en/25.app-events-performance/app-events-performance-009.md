# Batching Post-Processing Tasks

## 1. What is post-processing batching?

In Spring Framework Application Events, a use case may publish `OrderPlaced` after an order is placed. Multiple components care about this event to perform **auxiliary work** (*post-processing*): writing audit logs, computing metrics, syncing search indexes, generating summaries, sending notifications, or updating integrated systems.

The straightforward approach maps each event to one I/O operation:

~~~text
OrderPlaced #101 -> listener -> INSERT audit 101
OrderPlaced #102 -> listener -> INSERT audit 102
OrderPlaced #103 -> listener -> INSERT audit 103
OrderPlaced #104 -> listener -> INSERT audit 104
~~~

When every round trip to a database or external service incurs fixed overhead, this approach consumes resources and raises latency. **Batching** groups multiple work units of the same kind into a single bounded processing pass:

~~~text
OrderPlaced #101 --+
OrderPlaced #102 --+-- buffer --> batch [101,102,103] --> process together
OrderPlaced #103 --+
OrderPlaced #104 -----------+--> batch [104,...]     --> process next round
~~~

Core idea:

1. **Fast intake:** the listener creates only a minimal task/snapshot and puts it into a buffer or durable queue.
2. **Bounded accumulation:** collect up to `maxBatchSize` items while enforcing a `maxWait` threshold so sparse events do not wait forever.
3. **Batch execution:** a worker calls an API with genuine batch support, such as JDBC batching, a bulk indexing request, or an integration API with a bulk endpoint.
4. **Recording outcomes and errors:** succeeded batches are ACKed; failed batches require retries, splitting, poison-item isolation, or dead-letter routing according to required reliability.

Batching is **not** simply adding `@Async` to each listener. `@Async` moves work to another thread, yet can still create **one task and one I/O call per event**. Batching reduces the number of I/O calls when conditions allow.

## 2. Why does batching improve performance?

Suppose writing one audit record takes roughly:

- `L`: fixed cost per database or HTTP call;
- `c`: processing cost per item;
- `N`: total number of items.

Without batching:

~~~text
T_single ≈ N × (L + c)
~~~

When split into batches of size `B`:

~~~text
T_batch ≈ ceil(N / B) × L + N × c + batching/serialization overhead
~~~

This is a simplified model to understand **why reducing round trips helps**, not a promise that real-world throughput always scales linearly. Database drivers, transactions, payload limits, network, contention, memory, and error-handling mechanisms all affect outcomes.

Purely as an illustration, if `N = 1000`, `B = 100`, fixed overhead `L = 5 ms`, and variable cost `c = 0.1 ms`:

| Approach | Call count | Estimated time per model |
| --- | ---: | ---: |
| Write each item individually | 1,000 | ~5,100 ms |
| Write in batches of 100 | 10 | ~150 ms before extra overhead |

Never use hypothetical numbers like these to claim SLOs. **Benchmark with a realistic workload** and compare throughput, p50/p95/p99 latency, CPU, connection pools, errors/retries, and backlog.

### Trading latency for throughput

Larger batches generally reduce per-item overhead while making an event **wait for other events**. If only one event arrives per minute and the policy is “flush only at 100 events”, that item may wait a very long time.

Therefore, define **two triggers**:

~~~text
Flush when:
    pendingCount >= maxBatchSize
            OR
    wait time of oldest item >= maxWait
~~~

This is *size-or-time batching*. Implementations using a periodic scheduler can guarantee wait times only **approximately** due to busy workers, delayed ticks, or backlogs. If an SLO demands a hard deadline, design clock/deadlines, scheduling, and monitoring accordingly.

## 3. Batching architecture in Spring Application Events

A sensible layout:

~~~text
Application service
      |
      v
ApplicationEventPublisher.publishEvent(...)
      |
      v
@EventListener or @TransactionalEventListener
      |
      |  lightweight work: map event -> immutable BatchItem
      v
Bounded queue / Outbox / Broker
      |
      | maxBatchSize / maxWait / retry policy
      v
Batch worker
      |
      +--> JDBC batchUpdate(...) / bulk API / search bulk request
      |
      +--> success: record ACK/completion
      |
      +--> failure: retry/backoff/DLQ per contract
~~~

**Distinction to keep clear:** Spring application events are by default **an in-memory dispatch mechanism within one application context**, not a durable message broker. If the process crashes, tasks sitting in a RAM queue can be lost. Using `@EventListener`, `@Async`, or `@Scheduled` does not create delivery guarantees on its own.

Selection table:

| Requirement | Usually sensible design |
| --- | --- |
| Optimize internal processing only; data loss on restart is acceptable | Bounded in-memory queue + periodic worker |
| Must run **only when the business transaction commits** | `@TransactionalEventListener(AFTER_COMMIT)` or an appropriate outbox mechanism |
| Must not lose tasks even on crash right after commit | **Transactional outbox** (written in the same transaction as domain state) |
| Multiple services/instances consuming, requiring durable retries | Durable broker/queue + batch consumer + ACK/retry |
| Must execute atomically with the business transaction | Execute inside that transaction; do not arbitrarily defer to a worker |
| Must run immediately; latency matters more than throughput | Avoid large batches; process directly or use tiny batches |

**Do not mistakenly batch work required to confirm success**: checking business invariants, reserving inventory, or updating core state may belong in the main transaction/use case. Simply because work “happens after an event” does not mean it may be delayed or made eventually consistent.

## 4. Parameters to define before implementation

### Batch size

`maxBatchSize` caps how many events are processed in one pass. Choose e.g. 100, 250, or 500 via benchmarking—**there is no universal optimal number**. Overly large batches can:

- increase heap/payload/serialization usage;
- hold database connections for too long;
- exceed HTTP request size or SQL parameter limits;
- raise retry cost when just one element fails;
- worsen p99 latency during prolonged flushes.

Combine both an **item count limit** and an **estimated byte limit** when payload sizes vary. For example, 100 tiny events and 100 large-data events do not consume the same RAM.

### Max wait / flush interval

`maxWait` bounds the desired delay for the oldest item. With `@Scheduled(fixedDelay = 200)`, the method runs 200 ms **after the previous run completes**; actual wait times can exceed 200 ms if flushes are slow or the scheduler is loaded. When a strict oldest-item deadline is needed, base flushing on item timestamps and explicit wakeups.

### Queue capacity / backpressure

`queueCapacity` must be **finite** to prevent unbounded RAM growth. When the queue is full:

- **Intentional rejection:** fail at enqueue time; the caller decides on retry. Fits when tasks must not be lost and callers can handle errors.
- **Bounded-timeout blocking:** applies backpressure onto the publisher; must accept higher request latency.
- **Route to durable channel:** use a queue/broker/outbox when delivery is mandatory.
- **Intentional drop:** only for droppable data (e.g., non-critical telemetry), with explicit alerting metrics.

Never call `offer()` and silently ignore `false`: the system would claim it accepted work while actually throwing events away.

### Concurrency and ordering

One worker can process sequentially in queue order within **a single instance**. When adding multiple workers, partitions, or instances:

- completion order across batches is not guaranteed by default;
- duplicate delivery can occur on retries;
- events for the same aggregate may need routing by `aggregateId`/partition and sequence to preserve relative order;
- do not split batches randomly when tasks have causal dependencies;
- persist `eventId` in the processing system to enforce idempotency when needed.

`ConcurrentLinkedQueue`, `ArrayBlockingQueue`, and broker partitions each offer different guarantees; never rely on a vague “FIFO” claim to assume global system ordering.

## 5. Runnable Java 17+ example: listener buffers to queue, worker flushes up to three items

To inspect the algorithm cleanly without relying on scheduler timing, the first example performs **manual flushing in `main`**. It illustrates two clear responsibilities: the listener **enqueues fast**, and the worker **drains a bounded batch**. Production triggers the worker via a scheduler or queue consumer instead of manual calls.

The project uses **Spring Framework 6.2.19** and Java 17+, requiring no database or Spring Boot.

### Structure

~~~text
event-postprocessing-batch/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/BatchPostProcessingDemo.java
    └── test/java/demo/BatchPostProcessingDemoTest.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'event-postprocessing-batch'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.BatchPostProcessingDemo'
}

test {
    useJUnitPlatform()
}
~~~

### src/main/java/demo/BatchPostProcessingDemo.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class BatchPostProcessingDemo {

    public record OrderPlaced(long orderId) {}

    @Bean
    EventBuffer eventBuffer() {
        // Capacity larger than the 7-event example, yet still bounded.
        return new EventBuffer(8);
    }

    @Bean
    OrderEventListener orderEventListener(EventBuffer buffer) {
        return new OrderEventListener(buffer);
    }

    @Bean
    BatchSink batchSink() {
        return new BatchSink();
    }

    @Bean
    BatchWorker batchWorker(EventBuffer buffer, BatchSink sink) {
        return new BatchWorker(buffer, sink, 3);
    }

    public static final class EventBuffer {
        private final BlockingQueue<OrderPlaced> queue;

        public EventBuffer(int capacity) {
            this.queue = new ArrayBlockingQueue<>(capacity);
        }

        public void enqueue(OrderPlaced event) {
            // Do not block the request; fail explicitly on overload.
            if (!queue.offer(event)) {
                throw new IllegalStateException(
                    "Batch queue is full"
                );
            }
        }

        public int drainTo(List<OrderPlaced> batch, int maxItems) {
            return queue.drainTo(batch, maxItems);
        }

        public int pending() {
            return queue.size();
        }
    }

    public static final class OrderEventListener {
        private final EventBuffer buffer;

        public OrderEventListener(EventBuffer buffer) {
            this.buffer = buffer;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            // Synchronous yet very lightweight: only enqueues.
            // If the queue is full, rejects rather than silently dropping.
            buffer.enqueue(event);
        }
    }

    public static final class BatchSink {
        private final List<List<Long>> completed =
            new ArrayList<>();

        // Simulates a bulk write: one call per batch.
        public void writeBatch(List<OrderPlaced> batch) {
            List<Long> ids = batch.stream()
                .map(OrderPlaced::orderId)
                .toList();

            completed.add(List.copyOf(ids));
            System.out.println(
                "batch " + completed.size()
                + ": ids=" + ids
            );
        }

        public List<List<Long>> completedBatches() {
            return List.copyOf(completed);
        }
    }

    public static final class BatchWorker {
        private final EventBuffer buffer;
        private final BatchSink sink;
        private final int maxBatchSize;

        public BatchWorker(
                EventBuffer buffer,
                BatchSink sink,
                int maxBatchSize) {
            this.buffer = buffer;
            this.sink = sink;
            this.maxBatchSize = maxBatchSize;
        }

        // One worker at a time in this demo.
        // synchronized prevents concurrent flushOnce calls on the same
        // object, but does not lock across application instances.
        public synchronized int flushOnce() {
            List<OrderPlaced> batch =
                new ArrayList<>(maxBatchSize);

            buffer.drainTo(batch, maxBatchSize);

            if (batch.isEmpty()) {
                return 0;
            }

            // DEMO ONLY: drain already removed items from RAM.
            // If writeBatch fails, there is no durable retry.
            sink.writeBatch(batch);
            return batch.size();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                BatchPostProcessingDemo.class)) {

            for (long id = 101; id <= 107; id++) {
                context.publishEvent(new OrderPlaced(id));
            }

            BatchWorker worker = context.getBean(
                BatchWorker.class
            );

            while (worker.flushOnce() > 0) {
                // Flush until the queue is empty in the demo.
            }

            System.out.println(
                "pending=" + context.getBean(
                    EventBuffer.class).pending()
            );
        }
    }
}
~~~

### Run command and output

~~~bash
gradle run --quiet
# With Gradle Wrapper: ./gradlew run --quiet
# On Windows: gradlew.bat run --quiet
~~~

Lines printed by the demo itself:

~~~text
batch 1: ids=[101, 102, 103]
batch 2: ids=[104, 105, 106]
batch 3: ids=[107]
pending=0
~~~

**Exact explanation:**

1. `publishEvent` is called seven times; each time `OrderEventListener` appends **one item** to the `ArrayBlockingQueue` of capacity 8.
2. No bulk write happens inside the listener. It only calls `offer`, simulating a short intake path.
3. `flushOnce()` calls `drainTo(..., 3)`, taking up to three items per batch; the three flushes return **3, 3, 1** respectively.
4. The final flush sees an empty queue and returns `0`, ending the loop.
5. `BatchSink` simulates a bulk endpoint by storing batch history in RAM. **It is not a real JDBC batch**, does not persist durably, and does not measure real performance.

The example intentionally flushes manually in `main` for reproducible output. To process **off the request thread**, a production worker should be driven by a scheduler or queue consumer on another thread—see the next section.

### Important limitation of the example

`BlockingQueue.drainTo(...)` **removes elements from the queue before `BatchSink.writeBatch(...)` succeeds**. If the sink throws after draining, those elements may be lost. Thus **this pattern is only for learning / best-effort tasks**, not as-is for mandatory auditing/notifications. Do not wrap it in `try/catch` and swallow exceptions as if ACKed.

Furthermore, if a synchronous listener throws due to a full queue, the exception can propagate back to `publishEvent(...)` under the default multicaster. If the publisher is inside a business transaction, that exception **can trigger a transaction rollback**, depending on call site and rollback rules; this is a real backpressure policy with real impact, not “free” performance.

## 6. Testing batch size, ordering, and backpressure with JUnit 5

Create `src/test/java/demo/BatchPostProcessingDemoTest.java`:

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BatchPostProcessingDemoTest {

    @Test
    void groupsSevenEventsIntoThreeBatches() {
        try (var ctx = new AnnotationConfigApplicationContext(
                BatchPostProcessingDemo.class)) {

            for (long id = 101; id <= 107; id++) {
                ctx.publishEvent(
                    new BatchPostProcessingDemo.OrderPlaced(id)
                );
            }

            var worker = ctx.getBean(
                BatchPostProcessingDemo.BatchWorker.class
            );

            assertEquals(3, worker.flushOnce());
            assertEquals(3, worker.flushOnce());
            assertEquals(1, worker.flushOnce());
            assertEquals(0, worker.flushOnce());

            var sink = ctx.getBean(
                BatchPostProcessingDemo.BatchSink.class
            );

            assertEquals(
                List.of(
                    List.of(101L, 102L, 103L),
                    List.of(104L, 105L, 106L),
                    List.of(107L)
                ),
                sink.completedBatches()
            );

            assertEquals(
                0,
                ctx.getBean(
                    BatchPostProcessingDemo.EventBuffer.class
                ).pending()
            );
        }
    }

    @Test
    void rejectsNewWorkWhenBufferIsFull() {
        try (var ctx = new AnnotationConfigApplicationContext(
                BatchPostProcessingDemo.class)) {

            // Queue capacity is 8.
            for (long id = 1; id <= 8; id++) {
                ctx.publishEvent(
                    new BatchPostProcessingDemo.OrderPlaced(id)
                );
            }

            assertThrows(
                IllegalStateException.class,
                () -> ctx.publishEvent(
                    new BatchPostProcessingDemo.OrderPlaced(9)
                )
            );

            assertEquals(
                8,
                ctx.getBean(
                    BatchPostProcessingDemo.EventBuffer.class
                ).pending()
            );
        }
    }
}
~~~

Run:

~~~bash
gradle test
# With wrapper: ./gradlew test
# Windows: gradlew.bat test
~~~

**Both tests** are expected to pass with default Spring configuration:

- Test 1 verifies the 3-item/batch cap, no duplicate/missing items, and an empty queue afterward.
- Test 2 verifies that once the queue holds 8 items, the 9th event **is not silently dropped**; `IllegalStateException` propagates to the caller under default synchronous dispatch.

These tests do **not** verify concurrent multi-worker execution, database write errors, transaction rollbacks, shutdown, or crash recovery. Those are separate mandatory checks for production deployment.

## 7. Time-triggered flushing with @Scheduled

Spring Framework supports `@EnableScheduling` and `@Scheduled` to invoke the worker periodically. An **illustrative supplementary example**, not part of section 5's main project:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Configuration
@EnableScheduling
class SchedulingConfig {}

@Component
class PeriodicBatchFlush {
    private final BatchPostProcessingDemo.BatchWorker worker;

    PeriodicBatchFlush(
            BatchPostProcessingDemo.BatchWorker worker) {
        this.worker = worker;
    }

    @Scheduled(fixedDelay = 200, initialDelay = 200)
    public void flushOnTimer() {
        // Only one batch of at most 3 items per tick in this example.
        worker.flushOnce();
    }
}
~~~

To use this snippet, register `SchedulingConfig`, `PeriodicBatchFlush`, and the example's beans in a single application context without duplicating beans; the snippet above **only illustrates scheduling** and is not enabled automatically in section 5's project.

`fixedDelay = 200` means **200 ms after the previous run finishes**. Therefore you cannot claim items always flush exactly 200 ms after arrival. When a backlog grows, the worker may process only 3 items per tick while the queue keeps growing.

To support true **size-or-time batching**, you can:

- use a worker with `BlockingQueue.poll(timeout)`: wait for the first item, then accumulate up to `maxBatchSize` or a `maxWait` deadline based on the oldest item;
- or combine a periodic scheduler with an early wakeup signal when pending items hit the threshold;
- always ensure one batch cannot be claimed by two workers simultaneously; to scale concurrently, define partitions and ACK semantics.

**Do not process the batch directly inside the listener the moment it hits the threshold** if the goal is cutting request-thread latency. When the 100th event arrives and a synchronous listener writes 100 DB rows inline, that 100th request suffers an abnormal latency spike.

### Size-or-time worker skeleton

Assuming `BlockingQueue<BatchItem>` with `BatchItem.receivedAt` (captured at enqueue time), the general algorithm:

~~~text
loop while running:
    first = queue.poll(waitForNextItem)
    if first == null:
        continue

    batch = [first]
    deadline = monotonicNow + maxWait

    while batch.size < maxBatchSize:
        remaining = deadline - monotonicNow
        if remaining <= 0:
            break
        next = queue.poll(remaining)
        if next == null:
            break
        batch.add(next)

    writeAndAcknowledge(batch)
~~~

This is **pseudocode**, not a standalone Java API. When tracking elapsed time for deadlines, prefer a monotonic clock like `System.nanoTime()` over wall-clock time, which can jump. Starting the timer when `first` is pulled from the queue is **not enough** to bound `maxWait` from actual **enqueue time**, especially during long backlogs; carry the enqueue timestamp or measure queue age and handle backlogs explicitly.

In production, use a broker/outbox to hold pending events, have workers poll/claim, process in batches, and ACK only after writes succeed.

## 8. Post-commit batching with @TransactionalEventListener

In transactional systems, events may be published **before the DB commits**:

~~~text
@Transactional placeOrder()
    BEGIN T1
    save(order)
    publishEvent(OrderPlaced)
    ...
    COMMIT or ROLLBACK
~~~

If a listener receives the event synchronously and enqueues immediately inside T1, an event may enter RAM even though T1 later **rolls back**. A post-processing task could then act on something absent from committed data.

For work that must start only after commit:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

// Illustrative listener inside an application bean.
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void acceptCommittedOrder(OrderPlaced event) {
    // Enqueue after transaction T1 commits successfully.
    buffer.enqueue(event);
}
~~~

The snippet above is **illustrative**, depending on `OrderPlaced`, `buffer`, and a managed bean. Points to weigh:

1. `@TransactionalEventListener` defaults to `AFTER_COMMIT`; declaring it explicitly improves readability.
2. By default the listener does not run when events are published **outside a transaction** with `fallbackExecution=false`. If non-transactional handling is needed, choose explicit semantics rather than toggling fallback to mask bugs.
3. The callback runs after commit, so **a full queue causing enqueue failure cannot roll back T1**. When post-commit errors occur, the application still needs detection and recovery.
4. Between **DB commit** and **enqueue to RAM**, the process can crash. `AFTER_COMMIT` addresses **timing**, not **durability**.
5. A post-commit listener writing new DB rows needs its own transaction, typically via a separate Spring-managed service opening a new transaction for its use case. Do not rely on T1 resources during cleanup as if they always start a fresh commit.
6. With reactive transactions, context lives in Reactor Context; use supported transaction-bound mechanisms such as `TransactionalEventPublisher` rather than relying on servlet ThreadLocals.

**Avoid claiming “`AFTER_COMMIT` + `Async` = events can never be lost”**: both in-process callbacks and local executors have crash windows.

## 9. Systems requiring high reliability: transactional outbox and bulk consumers

For events that must be processed even if the server crashes, the suitable architecture is usually:

~~~text
BEGIN T1
  INSERT orders(...)
  INSERT outbox(event_id, event_type, aggregate_id,
                payload, created_at, status='PENDING')
COMMIT T1

Outbox worker:
  claim up to B PENDING rows
  send/write batch to target system
  receive target ACK/commit
  mark rows DONE
  on error: retry/backoff or DLQ
~~~

This is **architectural pseudocode**. Claim/lock/lease mechanics depend on the DB and topology. Never implement this as an unprotected “SELECT pending then UPDATE” with two concurrent workers, as they can double-process rows.

Principles:

- **Source atomicity:** domain records and outbox rows must commit **in the same T1**.
- **ACK after success:** mark DONE only after the processor confirms success per contract. With bulk APIs returning partial success, ACK **per individual item** accurately rather than marking the whole batch DONE when one item failed.
- **Retries preserve identity:** one occurrence keeps its original `eventId`; delivery attempts may exceed 1.
- **Idempotency:** consumers use event IDs and an appropriate scope (e.g., unique constraints) to handle duplicates safely. “Sent once” and “processed exactly-once everywhere” do not come automatically just from using an outbox.
- **Dead-letter / poison items:** isolate permanently failing items so one bad record does not stall every batch.
- **Progress:** monitor pending count, oldest outbox age, retries, batch duration, throughput, and failure rate.
- **Retention:** define when to delete/archive DONE rows; outbox tables do not clean themselves forever.
- **Ordering:** if each aggregate has a sequence, preserve order during claim/batch/partition when consumers require it; multiple workers can reorder completions without coordination.

### Real JDBC batch example

In Spring JDBC, `JdbcTemplate.batchUpdate(...)` can group prepared statement executions to reduce overhead, depending on the driver. An **illustrative snippet inside a Spring-managed service**, requiring `JdbcTemplate jdbcTemplate` and the application's `OrderPlaced` type:

~~~java
public void writeAuditBatch(List<OrderPlaced> batch) {
    jdbcTemplate.batchUpdate(
        "INSERT INTO order_audit(order_id) VALUES (?)",
        batch,
        batch.size(),
        (ps, event) -> ps.setLong(1, event.orderId())
    );
}
~~~

Assumes schema and constraints exist. Empty batches should be skipped or handled explicitly. **Do not assume** a single `batchUpdate` call means “every item committed” if the method runs inside a transaction that may roll back or if the driver returns differing update counts.

If audit records must be consistent, run within proper transaction/commit boundaries. If a consumer reads an outbox and writes to a target DB, apply transactions and proper claim/ACK mechanics. JDBC batch APIs do not replace a durable queue.

## 10. Partial failures: what if one item in a batch fails?

Batches can fail at multiple levels:

~~~text
Batch [101,102,103,104]
  |
  +-- 101: OK
  +-- 102: OK
  +-- 103: invalid payload
  +-- 104: not yet processed
~~~

Depending on the driver/API, the outcome may be:

- **All-or-nothing:** one transaction rolls back the whole batch.
- **Partial success:** some items are committed/accepted while others error.
- **Ambiguous outcome:** a timeout occurs after the target may have already applied changes; the client does not know whether it succeeded.

Retry design must follow the **sink's contract**:

1. If all-or-nothing, retry the whole batch with backoff and bounded attempts (for transient errors).
2. If partial success, ACK succeeded items and retry failed items; avoid re-sending already-succeeded items where possible.
3. If the outcome is ambiguous, use an **idempotency key** for safe retries. Never assume a timeout means “definitely unprocessed”.
4. If one item fails permanently (poison), shrink/split the batch or route that item to a DLQ so healthy items continue.
5. If errors come from quotas or overload, apply backoff/circuit breakers and reduce concurrency or batch size; do not trigger retry storms.
6. Preserve `eventId`, `correlationId`, and necessary payload across all retries.

An **unsafe example** to avoid:

~~~java
List<OrderPlaced> batch = drainFromMemoryQueue();
try {
    bulkApi.send(batch);
} catch (Exception ignored) {
    // Wrong: the queue already removed the items, leaving no retry or alert.
}
~~~

The core issue is not “catching enough exceptions” but **the protocol for accepting and acknowledging work**. If at-least-once delivery is required, a broker/outbox provides durable accept/claim/ACK state; workers must still be idempotent.

## 11. Graceful shutdown and scaling workers

An app that works well in a lab can lose events during deployment:

~~~text
t0: 800 items enqueued in RAM
t1: Pod receives SIGTERM
t2: executor/scheduler stops
t3: RAM vanishes along with 800 unflushed items
~~~

When in-memory batching is acceptable, you can design controlled shutdown:

- Stop accepting new work or shift traffic to another instance.
- Prevent concurrent flush runs.
- Wait up to a bounded grace period for in-flight batches to finish.
- Flush remaining items if time permits and the sink is available.
- Emit metrics/logs if unfinished work remains.

However, **graceful shutdown cannot save power loss, crashes, `kill -9`, or sudden infrastructure loss**. For mandatory work, persist durably before ACKing the source. Moreover, `@PreDestroy` or shutdown hooks are not durable error-handling and retry mechanisms.

### Scaling horizontally

Suppose three Spring instances A/B/C each hold a RAM queue. Those queues **do not automatically share** backlogs. One instance dying loses its own queue. Dashboards must aggregate state across instances.

For work distribution:

- Brokers with partitions/consumer groups can divide load;
- Outbox workers can claim via leases/locks/partitions;
- Events for a single aggregate requiring order can route to the same partition;
- Optimal batch size must consider aggregate load rather than tuning one instance in isolation;
- Avoid endlessly adding workers when the target system is already saturated.

`synchronized` in the Java example protects only **one object in one JVM**, not a distributed lock. It cannot preserve ordering or prevent duplicates across multiple instances.

## 12. Measuring real effectiveness: do not just count batches

A good dashboard for post-processing batching includes:

| Metric | Meaning |
| --- | --- |
| `postprocess.enqueue.total` | Items accepted into the queue/outbox per contract |
| `postprocess.enqueue.rejected.total` | Items rejected due to overload |
| `postprocess.queue.depth` | Items currently waiting |
| `postprocess.queue.oldest_age.seconds` | Age of the oldest waiting item |
| `postprocess.batch.flush.total` | Flush attempts |
| `postprocess.batch.size` | Distribution of items per batch |
| `postprocess.batch.duration` | Processing time per batch |
| `postprocess.items.success.total` | Items processed successfully per sink outcome |
| `postprocess.items.failed.total` | Failed items |
| `postprocess.retry.total` | Retry attempts |
| `postprocess.dead_letter.total` | Items quarantined for manual handling |

Metric names are **application-level suggestions**, not metrics built into Spring.

With Micrometer, batch duration can use a `Timer`, batch size a `DistributionSummary`, queue depth a `Gauge`, and success/error counts a `Counter`. Never put `eventId`, `orderId`, `correlationId`, or message text in metric tags due to very high cardinality; put IDs in structured logs/traces.

Useful performance criteria:

- **Throughput:** items/s successfully processed, not merely items/s enqueued.
- **Batch fill ratio:** actual batch size / `maxBatchSize`. If consistently low, the batch interval is too short or traffic is low.
- **Queueing latency:** from enqueue to processing start, especially p95/p99.
- **End-to-end latency:** from business occurrence until side-effect completion.
- **Backlog age:** if rising steadily, the sink/worker is falling behind.
- **Retry amplification:** total processing attempts / unique items; retry storms can erase batching gains.

**Dangerous overload signs:** rising queue, rising oldest age, high CPU/connection pools, and flat successful items/s despite larger batch sizes or more workers. Adding concurrency may make things worse.

## 13. How to benchmark and tune

Instead of picking `maxBatchSize=1000` assuming “bigger is better”, experiment in a controlled way.

**Step 1 — Fix the workload.** Steady and peak events/second, payload sizes, event type mix, sink cost, failure rates, concurrency, consistency requirements, and latency SLAs.

**Step 2 — Establish a baseline.** Measure single-event processing: throughput, p95/p99, round-trip counts, CPU, DB connections, and lost/failed tasks.

**Step 3 — Sweep batch sizes.** For example 10, 50, 100, 250 with `maxWait` values like 50 ms, 200 ms, 1 s per requirements. Hold other variables relatively constant.

**Step 4 — Measure both low traffic and bursts.** Batches reach max size only under sufficient load. At low traffic, `maxWait` dominates latency.

**Step 5 — Exercise failure modes.** Sink returning 429/503, partial success, ambiguous timeouts, one poison event, worker crashes, shutdowns, full queues, transaction rollbacks, and retries.

**Step 6 — Lock in operational limits.** Max queue depth, max retry attempts, max payload bytes, max in-flight batches, oldest-age alerts, DLQ, and rollback/backoff policies.

Do not benchmark with `Thread.sleep` or by glancing at a few console lines. For databases, verify **the driver genuinely supports efficient batching** and measure on both the Java side and the target system.

## 14. Common design mistakes

### Mistake 1 — Putting @Async on every event and calling it batching

~~~java
@Async
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    jdbcTemplate.update(
        "INSERT INTO audit(order_id) VALUES (?)",
        event.orderId()
    );
}
~~~

Each event still runs a separate `UPDATE/INSERT` and may consume an executor task. This is **asynchronous processing**, not bulk batching. When batching is needed, collect events into a queue/stream and call an appropriate bulk API.

### Mistake 2 — Unbounded queues

`new LinkedBlockingQueue<>()` allows the queue to grow up to an enormous integer cap. If the publisher outpaces the consumer, RAM grows until the application hits memory pressure. Use a bounded queue or a broker with quotas/backpressure.

### Mistake 3 — Flushing only when B items accumulate, with no timeout

If traffic drops or the system prepares to shut down, the remainder can sit indefinitely. You need time triggers, bounded flush-on-shutdown, and/or a durable queue.

### Mistake 4 — Flushing directly on the request thread when a batch fills

Whichever request happens to cross the threshold suffers an abnormally slow response. If the goal is reducing request latency, keep the worker off the request thread.

### Mistake 5 — Draining the queue and swallowing exceptions

Once the sink fails, the items are already out of the queue. Without error/ACK/retry handling, data can be lost. Decide delivery obligations before choosing a buffer.

### Mistake 6 — Treating @TransactionalEventListener(AFTER_COMMIT) as durable

A post-commit callback avoids running before data commits, yet a process crash between commit and callback/enqueue still loses tasks. Use an outbox when durability is required.

### Mistake 7 — Retrying whole batches endlessly without idempotency

One permanently bad item can block the queue; bulk retries can also duplicate items from partial successes. Use bounded retries, DLQs, partial ACKs, and stable event IDs.

### Mistake 8 — Ignoring ordering and partitioning when scaling

Multiple workers can let `OrderCancelled` finish before `OrderPlaced` at the destination. When consumers require per-aggregate order, use partitions/sequences and proper synchronization rules.

### Mistake 9 — Batching every event type into one bulk call

Events with different schemas, destinations, or SLAs may not share a single bulk API. Group by target, event type, tenant/partition, or an appropriate key **without leaking sensitive info** and without creating excessive queues.

### Mistake 10 — Counting publish as completed processing

Returning from `publishEvent` does not prove transaction commit, worker ACK, or sink success. Instrument at the exact enqueue, flush, ACK, and retry points.

## 15. Pre-production checklist

- [ ] Confirmed whether **post-processing work** may be deferred and allow eventual consistency.
- [ ] Locked down whether **data loss is acceptable**; if not, use an outbox/broker instead of RAM alone.
- [ ] Set `maxBatchSize`, `maxWait`, `queueCapacity`, and byte limits.
- [ ] Added a flush path for low traffic and partial batches.
- [ ] Defined explicit backpressure/rejection/timeout behavior when the queue is full.
- [ ] Verified listeners enqueue fast and never unexpectedly run bulk I/O on request threads.
- [ ] Ensured only **committed** events are processed when business rules require it.
- [ ] Batch workers implement claim/ACK/retry, idempotency, and DLQ per sink contract.
- [ ] Partial successes and ambiguous timeouts are handled properly.
- [ ] Ordering for dependent aggregates is not accidentally broken.
- [ ] Tested bursts, low traffic, crashes, shutdowns, retries, full queues, poison items, and transaction rollbacks.
- [ ] Monitored queue depth, oldest age, batch size, throughput, errors, and p95/p99 latency.
- [ ] Benchmarked with realistic data instead of assuming “larger batches are always faster”.

### Key takeaways

~~~text
One event -> one side effect
    easy to reason about, but high I/O overhead at high volume.

Many events -> one batch
    increases throughput when the sink supports bulk operations,
    in exchange for wait time, RAM, backpressure, and error logic.

@EventListener
    in-process dispatch, does not guarantee durability on its own.

@Async
    switches threads, does not batch automatically.

@Scheduled / worker
    can trigger flushes; requires size/time bounds.

@TransactionalEventListener(AFTER_COMMIT)
    binds timing to post-commit, does not survive crash windows.

Transactional outbox + batch consumer + ACK/idempotency
    when durability and reliable processing are required.
~~~

**Conclusion:** batching post-processing tasks is an exercise in **controlled I/O optimization**, not just adding a Spring annotation. A sound design specifies what gets grouped, when it flushes, how a full queue behaves, how failed batches are retried/ACKed, and whether committed events can be lost when the process stops.

## Official documentation

- [Spring Framework 6.2 — ApplicationContext Events and asynchronous listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [SimpleApplicationEventMulticaster — Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [JdbcTemplate — Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Micrometer — Timers, Counters, Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts.html)
