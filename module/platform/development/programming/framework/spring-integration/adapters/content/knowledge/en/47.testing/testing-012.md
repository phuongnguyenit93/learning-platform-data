# Testing Concurrency and Ordering in Spring Integration Adapters

## 1. The Real-World Problem: Messages Arrive in Order Yet Produce Wrong Results

In the **SPRING_INTEGRATION_ADAPTERS** module, Spring Integration connects external systems via **inbound/outbound adapters**, **gateways**, **pollers**, and **MessageChannels**, spanning File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. Flows may ingest multiple messages concurrently, split messages across threads, process asynchronously, or retry on errors.

Suppose a partner sends three status updates for order O-274:

~~~text
sequence=1  CREATED
sequence=2  PAID
sequence=3  SHIPPED
~~~

The system receives all three in order, yet dispatches them to workers running in parallel:

~~~text
Received:   CREATED(1) --- PAID(2) --- SHIPPED(3)
Worker A:   CREATED(1) ---------------------- commit
Worker B:               PAID(2) -- commit
Worker C:                         SHIPPED(3) --- commit
Result:     2, 3, 1
~~~

If the handler simply overwrites order status with whichever event finishes last, the final status can end up `CREATED` even though the order was already `SHIPPED`. This is a **concurrency-induced ordering bug**. You cannot catch it by checking only whether `MessageChannel` received all three messages; you must verify **business-meaningful ordering** and **outcomes when steps finish out of order**.

**Testing concurrency and ordering** means verifying that when multiple messages, producers/consumers, pollers, or adapters execute concurrently, the system honors **ordering rules, isolation, atomicity, idempotency, concurrency caps, and error recovery**.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **arrival, enqueue, dequeue, start, completion, commit, and observation** order.
2. Describe the actual ordering guarantees of **`DirectChannel`, `QueueChannel`, `ExecutorChannel`, `PublishSubscribeChannel`**, and polling endpoints.
3. Select the right requirement: **global order**, **per-key order**, **causal order**, or **unordered**.
4. Use **`CountDownLatch`, `Semaphore`, `ExecutorService`, `QueueChannel`, and JUnit 5** to build deterministic, sleep-free tests.
5. Test race conditions, interleavings, duplicates, retries, crashes/restarts, backpressure, and thread safety.
6. Evaluate ordering behavior across File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC in integration flows.
7. Build a test matrix, observation evidence, runbooks, and a pre-production checklist.

## 2. Concurrency and Ordering Are Not Synonyms

**Concurrency** means multiple tasks coexist or make progress over overlapping time intervals. **Parallelism** means executing simultaneously across multiple threads/CPUs. **Ordering** means events must obey a defined before–after relation.

| Concept | Testing Question | Example |
|---|---|---|
| Arrival order | In what order do events enter the system? | HTTP request A arrives before B |
| Enqueue order | In what order are messages placed in the channel/queue? | `send(M1)` before `send(M2)` |
| Dequeue order | In what order do consumers pull messages? | `QueueChannel` returns M1 then M2 |
| Start order | In what order do handlers begin processing? | Worker 2 starts before Worker 1 |
| Completion order | In what order do handlers finish? | M2 finishes before M1 |
| Commit order | In what order do changes commit to the DB? | Version 2 commits before version 1 |
| Publish order | In what order does outbound emit to broker/topic? | Kafka producer emits event A then B |
| Observation order | In what order do external systems see outcomes? | Client reads `SHIPPED` before `CREATED` |

Two messages dequeued in FIFO order **do not guarantee** two asynchronous tasks will commit FIFO. Similarly, a handler finishing does not guarantee downstream HTTP or Kafka received data successfully.

### 2.1. Types of Ordering Requirements

| Type | Meaning | When Appropriate |
|---|---|---|
| **Global order** | Every message follows one single total order | Single-stream logs, certain global workflows |
| **Per-key order** | Order preserved per `orderId`/`accountId`/`tenantId` | Order statuses, account balances |
| **Causal order** | Dependent events execute after prerequisites | Never `SHIP` before `PAYMENT_CONFIRMED` |
| **Event-time order** | Processed by business timestamp in payload | Late-arriving sensor events |
| **No ordering requirement** | Outcomes are independent of order | Generating thumbnails for unrelated images |

Global ordering is rarely needed across millions of orders: **per-key ordering** preserves each order's state accurately while letting unrelated orders run in parallel. However, you must define how keys are derived and how duplicate sequences or late arrivals behave.

### 2.2. A Message Is Not a Transaction

A Spring `Message` carries payload/headers; channels route messages to endpoints. **Transactions** can wrap certain DB/broker steps, whereas network/HTTP/SFTP side effects occur outside that transaction. Concurrency tests must check **committed business decisions**, not stop at channel acceptance.

### 2.3. Ordering and Consistency

Even without transport-level ordering guarantees, applications can maintain consistency through **optimistic locking, expected versions, idempotency, key-based partitioning, deduplication, or state machines**. Conversely, queue FIFO alone will not protect against overwriting newer data if concurrent threads update the same record without version checks.

## 3. Defining a Testable Ordering Contract

Before writing tests, document answers to:

1. **Which key requires ordering?** `orderId`, `customerId`, `accountId`, or global stream?
2. **What defines order?** Sequence number, aggregate version, Kafka offset, timestamp, or business counter?
3. **Up to which point must order hold?** Dequeue, handler start, DB commit, event publish, or consumer observation?
4. **Are duplicate messages possible?** If so, deduplicate by `eventId` or `key + version`?
5. **What if a sequence is missing?** Wait, time out, request replay, quarantine, or skip?
6. **What if an old message arrives late?** Ignore stale version, audit it, or trigger compensation?
7. **Can distinct keys run concurrently?** Up to what concurrency limit?
8. **Do retries, crashes, and redeliveries alter order?** Which recovery mechanism owns it?

### 3.1. Example Contract for OrderEvent

~~~json
{
  "eventId": "evt-274-3",
  "orderId": "order-274",
  "version": 3,
  "type": "SHIPPED",
  "occurredAt": "2026-11-23T08:00:00Z",
  "payload": {
    "trackingId": "track-274"
  }
}
~~~

Illustrative policy:

- For each `orderId`, `version` must advance **monotonically** from the committed version.
- Two events with the same `eventId` apply business effects only once.
- Older versions never overwrite newer states.
- If an intermediate version is missing, waiting/quarantine/replay behavior is explicitly specified.
- Distinct `orderId`s may execute concurrently.

Never use `occurredAt` as the primary ordering key when producer clocks drift or networks delay messages. Timestamps aid observability, not proving business sequence.

### 3.2. Expressing Test Criteria

For the same key `K`, accepted events with versions 1, 2, 3:

~~~text
Accepted(K, 1) precedes Accepted(K, 2) precedes Accepted(K, 3)
No final state transition from version 3 back to version 1.
Duplicate(K, eventId=X) does not duplicate side effects.
Unrelated(K2) may complete in parallel with K.
~~~

**The ordering under test must be evidenced at the point of commitment**: e.g., `committedVersion` in the DB. Logging handler calls into an in-memory list does not prove DB transactions committed in that same order.

## 4. How MessageChannels Affect Ordering

### 4.1. DirectChannel

`DirectChannel` normally invokes the handler **synchronously on the sending thread**. With a single sequential producer, consecutive `send` calls preserve processing order until the flow hits an async boundary. However, if **two producer threads send concurrently**, calls interleave. `DirectChannel` does not serialize all application producers into a global FIFO queue.

### 4.2. QueueChannel

`QueueChannel` is a `PollableChannel` with queue semantics. With one producer and one sequential consumer, it cleanly preserves FIFO unless altered by priority/custom ordering policies. When **multiple consumers poll and process concurrently**, receive order does not guarantee completion/commit order. Also consider capacity, timeouts, and `MessageStore` durability.

### 4.3. ExecutorChannel

`ExecutorChannel` hands dispatching off to a task executor. With multiple worker threads, messages execute concurrently with **no completion-order guarantee**. Even a FIFO executor work queue never guarantees handlers finish FIFO. Task rejections, pool saturation, and exception handling also affect tests.

### 4.4. PublishSubscribeChannel

`PublishSubscribeChannel` broadcasts the same message to multiple subscribers. Without an async executor, dispatch usually runs synchronously on the sender's call stack; with an executor, subscribers run concurrently. **There is no guaranteed single business order among side effects across multiple subscribers** unless the application enforces coordination.

### 4.5. Other Channels

| Channel | Notable Capability | What Not to Assume |
|---|---|---|
| `PriorityChannel` | Orders messages via comparator/priority | Strict FIFO or starvation-freedom |
| `RendezvousChannel` | Synchronous sender–receiver handoff | Downstream commit ordering |
| `FluxMessageChannel` | Bridges reactive streams | Ordering when using `flatMap` or parallel schedulers |
| `DirectChannel` | Synchronous at send boundary | Global order across multiple senders |
| `QueueChannel` | Buffers messages prior to receive | Global completion order with multiple workers |
| `ExecutorChannel` | Dispatches via executor | FIFO completion/commit |
| `PublishSubscribeChannel` | Fans out to multiple subscribers | Single consumer or ordered cross-subscriber side effects |

In reactive pipelines, operators like `concatMap` and `flatMap` carry very different ordering semantics; verify actual operators and schedulers rather than guessing from channel names.

### 4.6. Diagram of an Async Boundary

~~~mermaid
flowchart LR
    IN["Inbound message"] --> DC["DirectChannel"]
    DC --> TRANS["Transformer"]
    TRANS --> EC["ExecutorChannel"]
    EC --> W1["Worker 1"]
    EC --> W2["Worker 2"]
    EC --> W3["Worker 3"]
    W1 --> DB["DB / external side effect"]
    W2 --> DB
    W3 --> DB
~~~

Initially, steps may execute sequentially on the sender thread. Beyond `ExecutorChannel`, **completion/commit order** depends on scheduling, processing times, locks, and transactions. Place assertions on DB/outbound outcomes whenever business correctness lives there.

## 5. Pollers and Concurrency: `maxMessagesPerPoll` Is Not `maxThreads`

Polling endpoints actively fetch messages on schedules—e.g., File/SFTP/JDBC inbound sources or `QueueChannel` consumers.

| Setting | Governs | Not Equivalent To |
|---|---|---|
| `fixedDelay`/`fixedRate`/cron | Poller wakeup schedule | Processing strictly in source order |
| `maxMessagesPerPoll` | Max messages fetched per poll cycle per config | Thread/parallelism cap |
| `taskExecutor` | How work is dispatched to threads | FIFO completion |
| `receiveTimeout` | Wait time polling a `PollableChannel` | HTTP retry timeout |
| `transactional` advice | Wrapped transaction boundary | Atomicity across external systems |
| `errorChannel`/error handler | Where errors publish if supported | Automatic retries or rollbacks |

With multiple pollers/instances on a shared source, records can be claimed in different orders. In JDBC, `ORDER BY` in a `SELECT` does **not** replace claiming/locking mechanisms. In File/SFTP, directory listing order or download completion times do not necessarily mirror business sequence.

### 5.1. Testing Poll Cycles

Tests should observe: tick counts, messages per receive, active task counts, completion timing, `null` receives, and error-handler reactions. When a poller sees no data or stops, no `ErrorMessage` is emitted; monitor heartbeats/last-successful-poll alongside error counts.

### 5.2. Concurrency Limits

Set a verifiable **concurrency limit** (e.g., at most 4 active tasks), then test peak in-flight execution under load. Do not inspect only `threadPoolSize = 4`: flows may involve additional task executors, async HTTP callbacks, or multiple app instances.

### 5.3. Boundary Ordering Must Be Explicitly Declared

If a File adapter must process sequentially by filename, constrain sources, apply sorting/readiness checks, assign one consumer per key, and avoid unintended thread splits. If only final versioned state matters, run in parallel using optimistic concurrency in the DB.

## 6. How to Make Concurrency Tests Repeatable

Concurrency testing differs from sequential unit tests because failures depend on **interleavings**: one worker reading state before another commits, a late callback, or queue contention. Reliable tests control critical timing points rather than hoping OS scheduling triggers a race by luck.

### 6.1. Deliberate Synchronization

| Tool | Used For | Caution |
|---|---|---|
| `CountDownLatch` | Waiting for N steps or gating workers | Always use timeouts so tests never hang |
| `CyclicBarrier` | Aligning threads at a point before proceeding | Handle broken barriers and timeouts |
| `Semaphore` | Limiting or observing concurrency | Does not replace business data locks |
| `ExecutorService` | Running concurrent tasks on a sized pool | Shut down in `finally`/teardown |
| `AtomicInteger`/`AtomicLong` | Counting active tasks accurately | Does not replace DB transactions |
| `ConcurrentHashMap` | Thread-safe test state tracking | Does not prove cluster-wide consistency |
| `QueueChannel.receive(timeout)` | Bounded wait for channel messages | Assert types and valid fields on receipt |
| Awaitility or polling assertions | Waiting on eventual outcomes where appropriate | Conditional waits; avoid fixed sleeps |
| Gated/latched fake service | Simulating latencies and completion order | Always open gates in `finally` on failure |

**Never use `Thread.sleep(100)` as proof of ordering.** Under heavy load, 100 ms may be too short; on a fast machine, a broken implementation might pass by sheer luck.

### 6.2. Two Testing Levels

**Channel and handler tests:** verify `DirectChannel`, `QueueChannel`, and `ExecutorChannel` behavior inside a Spring context or directly on channel classes. Fast and easy to control.

**Real adapter integration tests:** exercise filesystems, SFTP servers, HTTP servers, brokers, or databases using production-like topology, transactions, concurrency, and retries. Isolated channel tests never prove Kafka offsets, JMS acknowledgments, or JDBC commits.

### 6.3. Define an Oracle Before Running

A good test doesn't just say "looks right." Define an observable **oracle**:

- Exact count of accepted events completes within deadline;
- Zero duplicate side effects despite redeliveries;
- For any key, `committedVersion` never decreases;
- If sequential transitions are required, version n+1 commits only after n;
- At most N concurrent requests hit the API;
- Independent keys still achieve parallel throughput;
- Crashes/restarts lose zero durably guaranteed events;
- Timeouts with unknown outcomes never trigger duplicate side effects.

### 6.4. Repeated Runs and Perturbation

After deterministic latch-based tests, add **repeated/stress tests** with varied interleavings and many keys. Fixed random seeds aid reproducibility; log the seed on failures. Still, 1,000 passing runs never prove a race is impossible—pair them with **invariants, thread controls, and transaction isolation**.

## 7. Testing QueueChannel FIFO: What Is Guaranteed and What Is Not

First verify **message retrieval order** with one producer and one consumer. This tests the queue, **not** worker completion order.

### 7.1. JUnit 5: Sequential Send and Receive

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class QueueChannelOrderingTest {

    @Test
    void oneProducerOneConsumerReceivesInFifoOrder() {
        QueueChannel input = new QueueChannel(3);

        for (int sequence = 1; sequence <= 3; sequence++) {
            assertTrue(input.send(
                    MessageBuilder.withPayload(sequence).build()));
        }

        for (int expected = 1; expected <= 3; expected++) {
            Message<?> actual = input.receive(1_000);
            assertNotNull(actual);
            assertEquals(expected, actual.getPayload());
        }
    }
}
~~~

This uses an in-memory `QueueChannel` of capacity 3 with no competing consumers. With multiple producers, enqueue order depends on how `send` calls race; "event created first" does not guarantee "enqueued first."

### 7.2. Adding Two Polling Consumers

Two consumers can pull `sequence=1` and `sequence=2` FIFO while the second finishes first:

~~~text
Queue: [1, 2]
Consumer A: receive 1 ---- slow DB write -------- commit(1)
Consumer B: receive 2 -- fast DB write -- commit(2)

Dequeue order: 1, 2
Commit order:  2, 1
~~~

Tests must measure **commit order** or final version whenever business correctness depends on it. Tuning `maxMessagesPerPoll` or task executors does not enforce per-key sequentiality on its own.

### 7.3. Testing Multiple Producers

When producers A and B send concurrently, tag each message with **`producerId`, `sequenceInProducer`**, and an event ID. Never assert global ordering between A and B without a central sequencer. Valid checks include:

- Per-producer order holds where producers serialize sends;
- Every message is received once in fault-free runs;
- Zero drops/duplicates under backpressure and send timeouts;
- Consumers uphold all defined per-key invariants.

### 7.4. QueueChannel and Durability

In-memory `QueueChannel`s are convenient for unit tests, yet messages vanish on process restarts. When production uses durable `MessageStore`s or brokers, test durability, transaction synchronization, and error receive/ack semantics; **never substitute in-memory queue tests for production durability tests**.

## 8. Testing ExecutorChannel: Forcing Message 2 to Finish Before Message 1

This is a **deterministic test** proving what must never be assumed: multi-worker `ExecutorChannel`s **do not guarantee FIFO completion**.

### 8.1. Gated Scenario

1. Send M1 and let Worker 1 start, then **block it on a latch**.
2. Once M1 is confirmed started, send M2.
3. Wait for M2 to finish.
4. Release M1's latch.
5. Observed completion order must be M2, then M1.

### 8.2. JUnit 5: Example Running with 2 Workers

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.support.MessageBuilder;

class ExecutorChannelOrderingTest {

    @Test
    void completionCanDifferFromSendOrder() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondCompleted = new CountDownLatch(1);
        CountDownLatch bothCompleted = new CountDownLatch(2);
        List<Integer> observed = new CopyOnWriteArrayList<>();

        try {
            ExecutorChannel channel = new ExecutorChannel(pool);
            channel.subscribe(message -> {
                int sequence = (Integer) message.getPayload();
                try {
                    if (sequence == 1) {
                        firstStarted.countDown();
                        if (!releaseFirst.await(5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException("Gate timeout");
                        }
                    }
                    observed.add(sequence);
                    if (sequence == 2) {
                        secondCompleted.countDown();
                    }
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Interrupted while testing", exception);
                } finally {
                    bothCompleted.countDown();
                }
            });

            assertTrue(channel.send(MessageBuilder.withPayload(1).build()));
            assertTrue(firstStarted.await(5, TimeUnit.SECONDS));
            assertTrue(channel.send(MessageBuilder.withPayload(2).build()));
            assertTrue(secondCompleted.await(5, TimeUnit.SECONDS));

            releaseFirst.countDown();
            assertTrue(bothCompleted.await(5, TimeUnit.SECONDS));
            assertEquals(List.of(2, 1), observed);
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

**Scope limitation:** this proves out-of-order completion is **possible** under controlled interleaving. It does not prove every run reorders, nor does it test DB commits; write dedicated tests whenever invariants live in the database.

### 8.3. Why Are Latches Better Than Sleeps?

The test **knows for certain** M1 started before M2 was sent, and **knows for certain** M2 finished before releasing M1—zero guessing about CPU or network speed. Bounded timeouts catch deadlocks without hanging CI.

### 8.4. When Production Uses a Single Thread

With a single-worker executor and a FIFO queue without restarts/retries, completion is typically sequential. Yet that caps throughput, and multiple app instances or downstream async boundaries can still break system-wide ordering. Test the full topology rather than trusting pool size alone.

## 9. Testing Concurrency Limits and Race Conditions

### 9.1. Measure Executing Handlers, Not Just Configuration

To verify concurrency limit N, track active counts with `AtomicInteger`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger active = new AtomicInteger();
AtomicInteger peak = new AtomicInteger();

void processOne() {
    int current = active.incrementAndGet();
    peak.accumulateAndGet(current, Math::max);
    try {
        // Business operation, controlled gate, or fake downstream.
        doBusinessWork();
    } finally {
        active.decrementAndGet();
    }
}
~~~

This is a **code pattern**, not a standalone class: `doBusinessWork()` must be implemented. In tests, requests must genuinely overlap; if they finish too fast, `peak` stays 1 even when the executor supports N concurrent workers. Use latches/barriers to hold N workers simultaneously, then assert `peak` never exceeds the limit and progress resumes once released.

### 9.2. Read–Modify–Write Race Conditions

Code like:

~~~java
int current = repository.readCounter();
repository.writeCounter(current + 1);
~~~

is not protected merely because `MessageChannel` is thread-safe. Two workers can both read `current=10` and both write `11`, when the right answer is `12`. Tests should **force both workers to read before either writes** using a barrier or fake repository, assert the final value to expose the bug, and then fix it with atomic updates/transactions or optimistic locking in the real store.

### 9.3. Other Thread-Safety Pitfalls

- Singleton handlers holding unsynchronized **mutable fields**;
- Using non-thread-safe `HashMap`/`ArrayList` across multiple workers;
- Sharing mutable payload objects and mutating them across subscribers;
- Reusing HTTP clients/sessions/formatters unsafely against library docs;
- Emitting correlated logs/metrics out of order;
- Storing request data in `ThreadLocal` and crossing `ExecutorChannel` without context propagation.

Spring message headers hold metadata for a `Message`, yet **payload objects may still be mutable**. Passing an object through a channel does not make concurrent mutations thread-safe.

### 9.4. Shutting Down Executors and Preventing Thread Leaks

Any test creating an `ExecutorService` must shut it down during cleanup. For Spring context integration tests, stop lifecycle endpoints, broker connections, and File/SFTP sources in teardown. Thread leaks cause flaky subsequent tests or prevent builds from exiting.

## 10. When Completion Order Is Unguaranteed: Enforce Versions at Commit Time

A design can allow M2 to finish before M1 **and remain business-correct** if the data store prevents stale events from overwriting newer state.

### 10.1. Conditional Version Update Example

~~~sql
UPDATE order_projection
SET status = :newStatus,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version < :incomingVersion;
~~~

This preserves **monotonic versions** across out-of-order events when executed atomically by the DB. However, it can **skip intermediate events** (e.g., version 3 arrives before version 2); it fits only when projections need the latest state and carry full snapshot fields.

If business rules require every valid state transition (`CREATED → PAID → SHIPPED`), checking `version < incomingVersion` is **insufficient**. Enforce `expectedVersion = incomingVersion - 1`, state transitions, and missing-event handling.

### 10.2. Testing Protection Against Stale State Overwrites

~~~text
Given: order-274 version=0
When:  process event version=3, commits under latest-wins policy
Then:  version=3, status=SHIPPED
When:  event version=1 arrives late
Then:  does not overwrite version=3
And:   logs/audits stale event per policy
~~~

This is a **test scenario**. If the system requires a strict sequential state machine instead of latest-wins, version 3 arriving first must be held in pending/resequencing and never committed ahead of versions 1 and 2.

### 10.3. Deduplicating Events and Side Effects

Do not assert only final status: a duplicate `PAID` event can trigger a **double charge** even when the final status still reads `PAID`. Assert API call counts and ledger/outbox writes by `eventId` or business transaction ID. Unique constraints or idempotency stores prevent duplicate execution on broker redeliveries.

### 10.4. Testing Atomicity of Deduplication + Update

If the system records "`eventId` processed" **after** calling HTTP or writing the DB outside a shared transaction, crashing between the two steps duplicates side effects. Test fault injection **before commit, after commit, before ack, and after ack** to prove safe recovery.

## 11. Splitters, Aggregators, and Resequencers: Group-Level Ordering

Spring Integration offers **Splitter, Aggregator, and Resequencer** patterns for related messages. They shine when a large message splits into parts processed concurrently, provided group metadata and release rules are explicitly defined.

### 11.1. Message Sequence Headers

When a splitter attaches correlation/sequence metadata, split parts carry:

| Header | Meaning |
|---|---|
| `correlationId` | Identifies the group of related messages |
| `sequenceNumber` | Position of this message within the group |
| `sequenceSize` | Expected part count when known |
| `messageId` | Identifies a specific message instance, not necessarily the business `eventId` |

Never assume every inbound File/HTTP/JMS/Kafka message arrives with these headers pre-populated. **Splitter sequence metadata** is not automatically the **order's business version**; it tracks part positions within one specific split group.

### 11.2. What Does a Resequencer Solve?

~~~mermaid
flowchart LR
    SPLIT["Splitter: 1, 2, 3"] --> A["Worker A: part 1 slow"]
    SPLIT --> B["Worker B: part 2 fast"]
    SPLIT --> C["Worker C: part 3 fast"]
    A --> R["Resequencer group"]
    B --> R
    C --> R
    R --> O["Release 1, 2, 3"]
~~~

A resequencer reorders **parts that arrived** by sequence and releases them per configured strategy. It **cannot conjure up a missing part**, nor can it keep released messages ordered downstream if followed by an `ExecutorChannel` or unawaited async send.

### 11.3. Scenarios to Test

1. Parts arrive `3, 1, 2`, yet downstream receives `1, 2, 3` as required;
2. Missing `sequence=2`: group waits, times out, expires, or partially releases per policy;
3. Duplicate `sequenceNumber` or duplicate `eventId`;
4. Two groups A and B interleave without mixing parts across groups;
5. Large groups exceeding memory/capacity backed by an appropriate `MessageGroupStore`;
6. Restart mid-way through an incomplete group;
7. Late message arriving after the group completed/expired;
8. Resequencer releases in order, yet downstream async stages commit out of order.

### 11.4. Do Not Solve Every Ordering Bug with a Resequencer

If the event source lacks reliable versions, a resequencer cannot tell which `CREATED` came before another. Across independent producers, enforce domain version/sequence protocols at the source. When the requirement is simply preventing stale overwrites, **optimistic concurrency** is often simpler and faster than funneling everything through a resequencer.

### 11.5. Aggregators and Result Ordering

An aggregator groups messages using a **correlation strategy** and **release strategy**. Output part order should not be assumed to match arrival order unless explicitly configured. Tests should assert **completeness and part identities**, adding ordering assertions only when the business contract actually requires them.

## 12. File Adapters: Directory Listing Order Is Not Business Order

### 12.1. Distinct Ordering Sources

A file adapter can observe:

- Order returned by filesystem directory listings;
- Lexical/natural filename sort order if configured;
- Last-modified time or ready-marker timestamps;
- Order accepted by `FileListFilter`;
- Order the poller emits messages to the channel;
- Order handlers ingest or commit to the database.

Never assume **filesystem listing equals business sequence**. `file-10.csv` can sort ahead of `file-2.csv` lexicographically, and timestamps may not reflect when the sender finished writing.

### 12.2. Designing File Ordering Tests

Prepare files:

~~~text
orders-001.csv -> businessSequence=1
orders-003.csv -> businessSequence=3
orders-002.csv -> businessSequence=2
~~~

Test two distinct contracts:

1. If the app requires **receiving in sorted filename order**, configure an explicit comparator/selector with a matching single consumer and assert receive order.
2. If the app requires **committing in `businessSequence` order**, assert order at the database or via state versions; sorting filenames at input isn't enough when downstream runs concurrently.

### 12.3. Incomplete Files and Mid-Poll Mutations

A producer writing a large file may be seen by the poller mid-write. Enforce contracts like **write-to-temp then rename**, marker files, age/size stabilization, or file locks. Tests should create partial files and prove the adapter never processes them as complete.

### 12.4. Duplicates and Restarts

Accept-once or persistent filters mark files seen. If the handler fails after the filter updates state, the file might never re-poll. Conversely, if metadata isn't durably persisted before a crash, the file may be re-read. Test both **crash after receive before commit** and **crash after commit before archive**; verify business-key deduplication.

### 12.5. Multiple Instances Watching One Directory

When two app instances poll one directory, both can pick up the same file. File locking, shared metadata/claiming, and idempotency must match real storage. Single-JVM/`QueueChannel` tests never verify shared file ownership in a cluster.

### 12.6. An Easy-to-Write Yet Misleading Order Test

A test might observe:

~~~text
File channel received: 1, 2, 3   (PASS)
DB committed:         2, 3, 1   (FAIL business ordering)
~~~

Never conclude end-to-end ordering simply because input-channel assertions passed. **Place assertions at the commit boundary** whenever correctness depends on final persisted state.

## 13. SFTP Adapters: Listing, Downloads, Remote Renames, and Concurrency

### 13.1. SFTP Typically Has Two Lifecycles

**Remote lifecycle:** partner uploads file, renames/marks ready, file appears in listing, optionally renamed/deleted during sync.

**Local lifecycle:** app downloads file, local filter accepts, poller emits `Message`, handler processes and persists outcome.

Remote listing order, download completion order, and local message delivery order can diverge—especially under varying latencies, file sizes, or multiple pollers.

### 13.2. Fault Matrix to Inject Deliberately

| Scenario | How to Simulate in Test Env | What to Assert |
|---|---|---|
| Two files A/B appear together | Upload in controlled order | Selection rules hold; no global-order assumption |
| File B downloads faster than A | Vary sizes/delays | Downstream ordering obeys contract |
| Remote file still uploading | Create temp file then rename | Not ingested before ready |
| Disconnect mid-download | Drop test session | Partial file not parsed; retry/resume works |
| Two pollers watch same remote path | Run two instances or consumers | No duplicate processing outside policy |
| Same filename with new content | Controlled content/version update | Metadata filter follows contract |
| Restart between receive and commit | Fault injection | Zero lost work and zero duplicate side effects |

### 13.3. Test Independently of Server Clocks

Remote mtime may suffer timezone/clock skew or coarse granularity. When business ordering matters, carry **`businessSequence` in manifests/payloads** or explicit protocols rather than relying blindly on mtime to order orders.

### 13.4. When SFTP Errors Reach `errorChannel`

Connect/list failures can occur before any Spring `Message` exists, leaving `failedMessage` null. Parse errors after download carry a `File` payload. Tests must prove the system still tracks **which file was downloaded/accepted and whether it retries**, not just count `ErrorMessage`s.

## 14. HTTP Inbound/Outbound: Request Order and Response Order Are Independent

### 14.1. HTTP Inbound Gateways Do Not Provide Global FIFO

Two clients send request A then B closely together. Web server thread pools, networks, gateways, downstream executors, and DB locks can let B finish before A. **Network request start order is not a global ordering contract** unless explicitly defined by the API.

If two requests update the same account, enforce versions/preconditions or per-key serialization. For unrelated accounts, parallel execution is usually preferable.

### 14.2. HTTP Outbound Gateways

A polling flow calling HTTP outbound synchronously exerts backpressure on the sender. Still, when the target processes requests across a multi-node cluster, **HTTP response order** does not prove target commit order.

With async HTTP clients or executor-backed gateways, callback B can arrive before callback A. Tests must track stable request IDs and correlate responses rather than matching "first response to first request."

### 14.3. Testing Timeouts with Unknown Outcomes

~~~text
Client sends POST orderId=274, requestId=R1
Server commits order
Response is lost
Client sees timeout
Retry may occur
~~~

Assert:

- Retries of the same intent reuse a stable idempotency key when supported by the API;
- Downstream applies only one business side effect;
- Order responses correlate via `requestId`, not callback arrival position;
- When outcomes cannot be confirmed, state becomes `RESULT_UNKNOWN`/`NEEDS_RECONCILIATION`;
- Transient errors enforce bounded retries/backoff without storms.

### 14.4. Simulating Out-of-Order Responses

Use a mock HTTP server capable of holding response A, returning B first, and then releasing A. With async callbacks, assert each result maps to its exact correlation. For stateful order workflows, assert DB versions/transactions rather than just response lists.

### 14.5. HTTP 429 and Concurrent Requests

Send concurrent messages against a rate-limiting mock downstream. When returning `429`/`Retry-After`, handlers must coordinate retries rather than letting every worker retry simultaneously. Measure **in-flight calls** and **total attempts**; capping concurrency on one `taskExecutor` segment may not cap other HTTP clients in the system.

## 15. JMS and AMQP: Message Groups, Prefetch, and Redelivery

### 15.1. Key Distinctions

In broker messaging, there are at least three orders:

1. Order producers send or the broker accepts messages;
2. Order the broker delivers messages to specific consumers;
3. Order listeners process and **commit side effects**.

With multiple consumers, prefetching, or redeliveries, step 3 often diverges from steps 1 and 2.

### 15.2. JMS

JMS provides ordering guarantees under specific session/producer/consumer/provider conditions, yet never assume **global order across concurrent producers, sessions, and consumers**. Some brokers support **message grouping**, commonly via `JMSXGroupID` to pin messages of the same group to one consumer; verify your broker/provider's exact semantics.

Tests should cover:

- Within the same group/`orderId`, events process in valid business sequence;
- Two independent groups progress concurrently;
- Consumer dies, group fails over to another consumer, and redelivery obeys policy;
- Transaction rollbacks trigger redelivery without duplicating side effects;
- Poison messages and DLQs can leave sequence gaps; verify gap policy for subsequent events.

### 15.3. AMQP/RabbitMQ

Within one queue, enqueue and delivery order can be FIFO under basic conditions, yet **multiple consumers, prefetch, nack/requeue, priorities, multiple publishers, and redeliveries** alter completion order. A single consumer with prefetch 1 reduces concurrency to help preserve order, yet never proves downstream systems committed FIFO.

| Configuration | Testing Expectation |
|---|---|
| Single queue, single consumer, sequential processing | Observe normal-case ordering |
| Single queue, multiple consumers | Test out-of-order completion |
| High prefetch | Multiple messages in flight; verify ack/commit behavior |
| Nack/requeue first message | Check whether later messages overtake it |
| DLX/DLQ | Define policy when a sequence item is quarantined |
| Single active consumer (if used) | Test failover and redelivery on the chosen broker |

**Sending a message to a DLQ is not equivalent to completing the business chain.** For one `orderId`, if version 2 hits the DLQ while version 3 proceeds, decide explicitly whether to wait, skip with audit evidence, or reconcile.

### 15.4. Acknowledgments and Transactions

Spring Integration AMQP/JMS adapters cooperate with listener containers. If a handler throws, redelivery/rollback behavior depends on transaction/ack mode and error handling. If an error flow catches and returns normally as success, the broker may treat the message as completed. Tests must check **broker state and DB state**, not just `ErrorMessage`s.

### 15.5. Assertions to Avoid

Never assert that messages from two independent producers process in exact wall-clock order. Define **per-group keys, business sequences, deduplication, and commit policies**—asserting only what the contract genuinely mandates.

## 16. Kafka: Per-Partition Ordering, Not Topic-Wide

### 16.1. Core Guarantees

Kafka appends records **in offset order within each partition**. Consumers read a partition's records in offset order; **there is no global order across partitions**. Concurrent producers sending with the same key can even append out of expected business order without coordination.

To route events for the same `orderId` to the same partition, producers must pick a **stable partitioning key** and keep partition counts/partitioners consistent as designed. Changing partition counts or strategies shifts key routing over time and requires migration plans.

### 16.2. Spring Integration Kafka Adapters and Worker Concurrency

Kafka message-driven inbound adapters run inside **listener containers**. Reading offsets in order from a partition **does not guarantee** offset-ordered completion or DB commits if the flow hands off to an `ExecutorChannel` or unawaited async services.

~~~mermaid
flowchart TD
    K["Kafka partition P0: offsets 11,12,13"] --> L["Kafka listener"]
    L --> X["ExecutorChannel 3 workers"]
    X --> W11["Offset 11 slow"]
    X --> W12["Offset 12 fast"]
    X --> W13["Offset 13 fast"]
    W11 --> DB["DB commit"]
    W12 --> DB
    W13 --> DB
~~~

Tests must separate **listener received** from **business processing confirmed**, verifying offset commit/ack timing in the real configuration. Never commit offsets as complete while unrecovered async side effects are still running.

### 16.3. Errors and Retries Can Create Gaps

| Scenario | What to Verify |
|---|---|
| Offset 12 transient error | Does container retry/pause/seek, or do later records proceed? |
| Offset 12 routed to DLT | May version 13 process if 12 is missing? |
| Consumer rebalance | Are in-flight completions/commits still valid? |
| Producer retries | Are duplicates or reordering observed? |
| Idempotent producer / transactions | Do Kafka guarantees cover HTTP/JDBC? |
| Async handler finishes after listener acked | Is unfinished work durably backed/retried? |

Spring for Apache Kafka provides container error handling (such as `DefaultErrorHandler` in matching versions). Seek, retry, DLT, and commit behaviors depend on version, ack mode, and configuration. **Never assume a global Spring Integration `errorChannel` controls Kafka offsets.**

### 16.4. Per-Key Kafka Test Pattern

Send at least two keys A and B, each with sequence `1..N`. Process with varying latencies and fault injection:

- For A, final state reaches version N and never regresses;
- For B, final state reaches version N;
- A and B may interleave unless global order is required;
- Duplicate `eventId`s create zero extra side effects;
- Across rebalances/restarts, zero data is lost or duplicated outside policy;
- If sequential state transitions are required, later versions never commit while earlier versions are missing.

### 16.5. Producers and Business Sequences

**Increasing offsets do not prove valid business sequence.** A buggy/racy producer can publish `PAID` before `CREATED`. Keep **aggregate versions or business sequences** in payloads/headers, validate against source state, and never rely solely on offsets for business correctness.

## 17. JDBC Inbound/Outbound: ORDER BY Does Not Replace Transactions and Claiming

### 17.1. Multi-Worker Polling

A JDBC inbound adapter might query work like:

~~~sql
SELECT id, order_id, event_version, payload_ref
FROM integration_work
WHERE state = 'PENDING'
ORDER BY created_at, id;
~~~

`ORDER BY` defines **row order inside one query result**, not that two concurrent pollers claim work in global order or commit to the DB in that order. Across two app instances, both can read the same row without locking/claiming.

### 17.2. Atomic Claiming and Optimistic Concurrency

A simple pattern:

~~~sql
UPDATE integration_work
SET state = 'CLAIMED',
    claimed_by = :workerId,
    version = version + 1
WHERE id = :workId
  AND state = 'PENDING'
  AND version = :expectedVersion;
~~~

Only the worker observing **exactly one row affected** wins the claim. This statement is illustrative and does not yet handle batching, lease expiration, dead workers, isolation/locks, or query races. If using **`SELECT ... FOR UPDATE SKIP LOCKED`**, check DB syntax/support and recognize that skipping locked rows makes **completion order non-FIFO**.

### 17.3. Testing Lost Updates with Two Transactions

A high-value test:

1. DB holds account `balance=100, version=1`.
2. Two workers both read `balance=100` before updating.
3. Workers A and B both add 10.
4. Without protection, blind writes yield `110` instead of `120`.
5. Fix with atomic SQL updates/locking or optimistic compare-and-set with retries.
6. Re-test against a real DB verifying `balance=120` and accurate commit counts.

**Never run H2 in-memory and assume concurrency/locking matches PostgreSQL, MySQL, or Oracle**; differences in isolation, lock waits, `SKIP LOCKED`, and deadlocks require integration tests on the target DB engine.

### 17.4. Per-Order Event Versioning

When handling events for one `orderId`, atomically in one transaction:

- Check whether `eventId` was already processed;
- Validate version against business rules;
- Apply the state transition;
- Record `eventId` processed or insert outbox event;
- Commit.

If deduplication and updates live outside the same transaction, crashes can duplicate or drop events.

### 17.5. Outbox and Publish Ordering

An outbox keeps publish intent inside the DB transaction. Yet two publisher workers can grab outbox rows for the same key and send concurrently, making **publish order** differ from commit order. Tests must verify:

- Does outbox claiming serialize by `orderId`/version or global ID?
- How many workers may process the same key concurrently?
- If publishing version 2 fails, does version 3 send anyway?
- Do retry records preserve idempotency keys and correlation?
- After crashing between publish and mark-sent, do consumers deduplicate?

Outboxes **do not automatically provide end-to-end exactly-once** with HTTP or brokers; consumers still require deduplication and invariant checks.

## 18. When Errors, Retries, and Dead-Letters Alter Ordering

### 18.1. Three Post-Error Policies

~~~text
Source: 1 -> 2 -> 3

Policy A: Stop-and-retry
  1 succeeds, 2 fails, 2 retries, 3 waits
  -> preserves sequential policy but may block

Policy B: Skip-to-DLQ
  1 succeeds, 2 fails -> DLQ, 3 continues
  -> makes progress, but creates a gap

Policy C: Concurrent retry
  1 succeeds, 2 fails and retries asynchronously, 3 succeeds
  -> 3 can commit before 2
~~~

No single policy is universally right; the business contract decides whether **sequence gaps** are acceptable. Telemetry may happily take latest updates, whereas payment ledgers demand strict sequence and accuracy across every entry.

### 18.2. ErrorMessage Is Not a Rollback

In Spring Integration, an exception can reach **`errorChannel`** as an `ErrorMessage` via an error publisher. That **does not undo** a file read, JMS ack, Kafka offset commit, or partial DB write.

Tests need **two separate assertions**:

1. Error notification lands on the right channel with safe context;
2. Source/target state matches retry, rollback, quarantine, or compensation policies.

### 18.3. Testing Retry Budgets

Suppose a handler retries 3 times and the broker/container redelivers up to 4 times. Do not assert only each component's individual config; verify **total downstream invocations** and combined retry-storm effects using call-counting mocks.

### 18.4. Poison Messages and Head-of-Line Blocking

If per-key order requires version 2 before 3, a permanently failing message 2 can block that key. Define a policy:

- Keep the key `BLOCKED` and alert;
- Quarantine version 2 for reconciliation or manual fix;
- Allow skipping with auditing if the domain supports it;
- Never block unrelated keys indefinitely.

Tests must prove **only the affected key blocks**, while independent keys continue processing when architecture permits.

### 18.5. Retrying to the Head vs. Tail of a Queue

Requeueing to head/tail, seeking offsets, delay queues, or republishing to Kafka typically alters order. Never assume messages redeliver in their exact original slot across every broker/adapter. Test with real retry configs and verify sequence at commit time.

### 18.6. Crash Between Side Effect and Acknowledgment

A worker processes event 2, commits DB changes, and crashes before broker ack. After restart, the broker redelivers event 2. With proper idempotency, the business outcome happens once; without it, side effects repeat. Fault-injection tests right at this boundary matter far more than measuring receive order alone.

### 18.7. Compensation and Late Callbacks

If `CancelOrder` already ran and a stale `CreateOrder` callback arrives afterward, the state machine must never revert the order back to `CREATED`. Test late callbacks and version/expected-state guards. **Callback arrival time never grants authority to corrupt business state.**

## 19. Concurrency and Ordering Test Matrix

### 19.1. Layered Scope

| Level | Target | Goal | Evidence |
|---|---|---|---|
| Unit | Version guards, dedup, state machines | Business rules hold across interleavings | State/versions, duplicate counts |
| Channel | Queue/Executor/Direct/PubSub | Topology and dispatch semantics | Receive/start/completion order |
| Flow integration | `IntegrationFlow`, pollers, advice | Thread boundaries, retries, error routing | Handled events + `ErrorMessage` |
| Adapter integration | File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC | Real protocols and states | Remote files, broker offsets/acks, DB commits |
| System / end-to-end | Multiple services and instances | Per-key consistency and throughput | Business state, outbox, external effects |
| Recovery / chaos | Crashes, failovers, partitions, slow downstreams | Zero lost messages or policy-breaking duplicates | Replay audits, final state, lag |

### 19.2. Minimum Scenarios

| ID | Scenario | What Must Be Verified |
|---|---|---|
| C01 | 1 producer, 1 `QueueChannel` consumer | Deterministic FIFO receive |
| C02 | `ExecutorChannel` with 2 workers | M2 can finish ahead of M1 |
| C03 | N producers on same key | Version policy never violated |
| C04 | N producers on distinct keys | Parallelism without cross-contamination |
| C05 | Same `eventId` sent twice | Single business side effect |
| C06 | Version 3 arrives before 2 | Waits/skips/commits per explicit policy |
| C07 | Version 2 transient failure | Retries never regress state |
| C08 | Version 2 poison message | Key blocked/quarantined per policy |
| C09 | Worker crashes before DB commit | Safe retry, zero data loss |
| C10 | Worker crashes after DB commit, before ack | Deduplicated on redelivery |
| C11 | Two JDBC pollers claim same row | Single valid claim or deduplicated |
| C12 | Partial File/SFTP upload | Unready file not ingested |
| C13 | HTTP response B arrives before A | Accurate correlation and state |
| C14 | JMS/AMQP consumer failover | Ack/redelivery and per-group policy |
| C15 | Kafka partition rebalance | No duplicate side effects |
| C16 | Outbox publisher retry / late callback | Accurate `eventId`, version, and state |
| C17 | Error handler fails | Recovery not lost; alert emitted |
| C18 | Queue/executor overload | Rejections/backpressure handled |
| C19 | Application restart | Pending states/groups recover cleanly |
| C20 | No data arriving at poller | Heartbeat/freshness alerts accurate |

### 19.3. Anti-Flakiness Assertions

Instead of "sleep 2 seconds then assert," use latches and bounded eventual assertions. When proving **no side effect** occurs over an interval, recognize it only proves the **observation window**; pair with version guards/invariants and check queue/in-flight worker states.

### 19.4. Production-Representative Configuration

Never run tests with a 1-thread pool and declare a 16-thread pool safe. Include integration tests matching critical production parameters: consumer concurrency, prefetch, Kafka partitions, poller schedules, retries, transaction modes, and `MessageStore`s.

### 19.5. Test Data and Reproducibility

Tag test events with `eventId`, `businessKey`, sequence/version, source, timestamp, attempt, and correlation. Log seeds, topologies, and fault-injection points on failure. Clean databases, queues, directories, and topics per test scope so stale data never causes false failures.

## 20. Case Study: Two Parallel Orders, One Receiving Out-of-Order Events

### 20.1. Context

Platform A ingests order files from SFTP and update events from Kafka. After validation, the flow updates a JDBC projection and calls logistics HTTP. States:

~~~text
Order A: CREATED(v1), PAID(v2), SHIPPED(v3)
Order B: CREATED(v1), PAID(v2), SHIPPED(v3)
~~~

Requirement: strict order **within each order**, while A and B run concurrently. Duplicates/retries must never double-ship or double-charge.

### 20.2. Risky Topology

~~~mermaid
flowchart TD
    F["SFTP inbound / File poller"] --> N["Normalize OrderEvent"]
    K["Kafka inbound"] --> N
    N --> Q["QueueChannel"]
    Q --> P["Polling consumer"]
    P --> E["ExecutorChannel"]
    E --> W1["Worker 1"]
    E --> W2["Worker 2"]
    E --> W3["Worker 3"]
    W1 --> DB["JDBC order projection"]
    W2 --> DB
    W3 --> DB
    DB --> OUT["Outbox / HTTP logistics"]
~~~

Even when `QueueChannel` receives A1, A2, A3 FIFO, `ExecutorChannel` lets A3 finish before A2. Kafka preserves partition order only if producer keys/routing and post-listener handling don't break sequence.

### 20.3. Initial Failing Test

Have Worker 1 process A1 yet block before DB commit, while Worker 2 handles A2 and Worker 3 handles A3. Under a naive "write latest processed status" implementation:

~~~text
Commit order: A2 -> A3 -> A1
Final A status: CREATED   (WRONG)
Final B status: SHIPPED   (RIGHT)
~~~

Tests must force this schedule deterministically using gates/latches or controllable fake services—never inferring commit order from Kafka receive logs.

### 20.4. Two Remediation Approaches

**Approach A — Per-key serialization:** route messages with the same `orderId` to a sequential worker/partition/queue while key B runs on another worker. Test failovers, restarts, and retry gaps to confirm the same key never executes concurrently outside policy.

**Approach B — DB-level concurrency control:** attach versions to every event, update atomically, and reject stale versions. If intermediate states are mandatory, allow transitions only from `expectedVersion`, hold early arrivals in a pending store, and request replay on gaps.

Avoid stacking both blindly: serialization can cap throughput, while optimistic locking causes retry conflicts. Pick based on business ordering needs and load.

### 20.5. Post-Fix Verification

| Test Condition | Expectation |
|---|---|
| A3 arrives before A2 | Final state of A follows policy |
| Late A1 callback arrives | Never overwrites newer version |
| A2 retried 3 times | Single payment side effect |
| A2 routed to DLT | A3 waits or handles gap explicitly |
| A and B run in parallel | A failing never stalls B |
| HTTP shipment timeout | No duplicate shipment created |
| Restart while A pending | Resumes at exact version |
| Kafka rebalance mid-processing | Zero lost or duplicated side effects |
| SFTP file contains duplicate A1 | Deduplicated by `eventId`/`businessKey` |
| Any failing message | Error flow never marks false success |

### 20.6. Performance Metrics Paired with Correctness

High throughput cannot excuse corrupted data. Test reports should include:

- Throughput (messages/s) and p95/p99 processing latency;
- Peak in-flight counts per endpoint and per key;
- Version conflicts, retries, and blocked duplicates;
- Reorder counts across arrival/start/completion/commit;
- Backlogs/lag across File, `QueueChannel`, Kafka, and outbox;
- Dropped, poisoned, and manually reconciled message counts;
- Error rates and out-of-policy handler side effects.

Never fabricate benchmark numbers without running tests. These metrics are **recommended test measurements**, not empirical results from this article.

## 21. Integration Test with PollableChannel and Spring Integration Flow

### 21.1. Goal

Unlike section 7's direct `QueueChannel` test, this test boots a **Spring application context** and runs a real polling consumer reading from `QueueChannel`. It confirms basic wiring and receive order with **one poller and one sequential handler** before introducing `ExecutorChannel` or multiple consumers.

### 21.2. Spring + JUnit 5 Test Example

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(SinglePollerFlowTest.Config.class)
class SinglePollerFlowTest {

    @Autowired
    QueueChannel inputQueue;

    @Autowired
    QueueChannel outputQueue;

    @Test
    void onePollingConsumerRelaysThreeMessagesInOrder() {
        for (int version = 1; version <= 3; version++) {
            assertTrue(inputQueue.send(
                    MessageBuilder.withPayload(version).build()));
        }

        for (int version = 1; version <= 3; version++) {
            Message<?> actual = outputQueue.receive(5_000);
            assertNotNull(actual);
            assertEquals(version, actual.getPayload());
        }
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        QueueChannel inputQueue() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel outputQueue() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow relayFlow() {
            return IntegrationFlow.from(inputQueue(),
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofMillis(50))
                                    .maxMessagesPerPoll(1)))
                    .channel(outputQueue())
                    .get();
        }
    }
}
~~~

This uses common Java DSL and Spring Test APIs; **verify DSL overload signatures against your project's Spring Integration version**. The test assumes no competing consumers drain `inputQueue`, no executor sits between source and output, and bean lifecycles are managed by the Spring context.

### 21.3. What Does This Test Prove?

It tests **the path from a polling consumer to an output queue** in a simple topology. It does not prove:

- `QueueChannel` durability across restarts;
- Ordered commits of HTTP/JDBC/Kafka side effects;
- Single delivery across multiple pollers or app instances;
- That retries or error channels never reorder messages;
- Safety under high concurrency.

### 21.4. Scaling from One to Multiple Workers

Keep `inputQueue` while adding an executor after the poller; use a latch in the handler to force M2 ahead of M1. Update assertions from global FIFO completion to **business-state invariants** whenever the topology intentionally processes in parallel.

### 21.5. Inspecting Thread Identity

Tests can record `Thread.currentThread().getName()` into a thread-safe collector to prove executor boundaries and multi-threading. Even so, thread names are only supporting evidence; **correctness must be proven via persisted state and side effects**.

### 21.6. Fault Injection into Polling Flows

Add a deliberately throwing handler and configure a dedicated poller error channel; assert `ErrorMessage` publication and source state. Once a `Message` leaves `QueueChannel`, never assume it returns automatically. For File/SFTP tests, verify source filters and file references for replay.

## 22. Runbook for Investigating Ordering and Concurrency Bugs

### Step A — Pin Down What "Out of Order" Means

Ask explicitly:

- Is it **arrival**, **dequeue**, **start**, **finish**, **DB commit**, or **client observation** order?
- Is global order or per-key order required?
- Do events carry a **trusted version** and **`eventId`**?
- Are gaps allowed or must every version apply sequentially?
- Are duplicates, retries, or late callbacks occurring?

Without pinning down the observation point, teams waste hours tweaking `QueueChannel` when the bug lives in JDBC or async outbound calls.

### Step B — Map Sync/Async Boundaries

For each endpoint, record:

1. Channel type: `Direct`, `Queue`, `Executor`, `PublishSubscribe`, `Priority`, or reactive;
2. Poller/scheduler, `maxMessagesPerPoll`, task executor, and instance count;
3. Where handlers hand off to async HTTP, Kafka producers, or external services;
4. Broker partitions/groups/consumer concurrency/prefetch and retry rules;
5. DB transaction boundaries, broker acknowledgments, or file filters;
6. Which channel receives `ErrorMessage`s on failure.

**Map from source all the way to the final side effect**—never stop at a middle channel.

### Step C — Gather Evidence

Record per event:

~~~text
eventId, businessKey, version,
sourceAdapter, sourceReference,
arrivalAt, enqueuedAt, handlerStartAt,
handlerFinishedAt, committedAt, publishedAt,
threadName, instanceId, attempt,
correlationId, failureCategory, disposition
~~~

Not every endpoint exposes every timestamp. These form a **recommended observation schema**; cross-machine clocks can skew. To prove ordering, prioritize sequence/version numbers and **commit logs/correlation** over comparing timestamps across independent clocks.

### Step D — Reproduce the Bug

1. Create two events for the same key plus at least one independent key;
2. Block worker A with a latch/barrier;
3. Let worker B run ahead and record its commit;
4. Inject a duplicate and a late-arriving event;
5. Inject a timeout or crash right at the ack/commit boundary;
6. Test recovery/restarts and broker rebalances where applicable;
7. Capture seeds, topologies, and pool/partition/prefetch settings.

If a bug occurs only in production, extract sanitized metadata and reproduce the pattern in staging; never export raw customer data to unauthorized test environments.

### Step E — Isolate the Root Cause

| Observation | Likely Cause to Inspect |
|---|---|
| M1 and M2 enqueue out of order | Multiple producers, source listings, network or publisher races |
| Enqueued cleanly, dequeued out of order | Priority channels, groups/partitions, multiple consumers, replays |
| Dequeued cleanly, committed out of order | Executors/async handlers, DB locks, HTTP latency |
| Committed cleanly, read model regressed | Consumer projections and stale events |
| Right data, callback matched wrong request | Missing correlation IDs or positional response matching |
| Side effects repeated after retry | Broken idempotency/dedup or ack timing |
| Gap at v2 yet v3 still ran | Retry/DLQ policy violates sequential rules |
| Messages "lost" after poller failure | Non-durable filter/queue states preventing replay |
| Latency spike | Lock contention, head-of-line blocking, queue backlogs |

### Step F — Apply the Minimal Scoped Fix

- **Per-key serialization** when business logic demands strict sequence;
- **Optimistic locking / version checks** when out-of-order arrivals are allowed;
- **Resequencers / pending stores** when gaps must wait for missing parts;
- **Idempotency / deduplication** for duplicates and redeliveries;
- **Transactional outbox/inbox** for DB state and message consistency;
- **Bounded executors / backpressure** when in-flight tasks exceed limits;
- **Quarantine / manual reconciliation** for unrecoverable poison messages or gaps.

Never force the entire application onto one single thread just to "fix ordering" when only a subset of keys needs it; doing so needlessly throttles unrelated work.

### Step G — Verify and Close the Incident

Re-run deterministic tests, stress tests, and fault injection on the target topology. Final sign-off requires:

- Invariants hold on DBs/target services;
- Duplicates handled safely;
- Zero message loss outside policy;
- Accurate retry/ack/recovery states;
- Throughput, latency, and backlogs within limits;
- Logs, metrics, owners, and regression tests preventing recurrence.

## 23. Common Anti-Patterns

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming `send(M1)` before `send(M2)` ⇒ M1 commits before M2 | Stale state overwrites newer state | Measure/enforce commit order |
| Testing only one producer on one thread | Misses production race conditions | Test multiple producers/consumers |
| Increasing `ExecutorChannel` pool while asserting FIFO completion | Test tests wrong contract | Assert per-key invariants or serialize |
| Using `Thread.sleep` to "synchronize" tests | Flaky and CI-dependent | `CountDownLatch`/barriers + timeouts |
| Relying on timestamps as business sequence | Clock skew and late arrivals break order | Trusted domain sequence/version |
| Treating in-memory `QueueChannel` as durable | Messages lost on restart | Proper `MessageStore`/broker |
| Assuming `maxMessagesPerPoll` caps concurrency | Overload and races | Check executors, instances, and in-flight counts |
| Treating JDBC `ORDER BY` as global processing order | Multi-worker commits diverge | Atomic claims/locks and version guards |
| Trusting SFTP listing matches upload order | Dependent files processed out of order | Manifests/sequences, ready protocols |
| Assuming Kafka orders across the whole topic | Cross-partition state corruption | Per-key partitioning and business versions |
| Assuming broker FIFO guarantees HTTP/DB commit FIFO | Concurrent side effects reorder | Assert at target; control async stages |
| Letting Kafka listener ack while async job isn't durable | Lost messages on crash | Proper ack/work persistence |
| Skipping retries across sequence gaps | Gaps break state machines | Retry/hold/resequence per key |
| Skipping poison messages without recording gaps | Subsequent versions misapply | Quarantine and reconciliation |
| Checking only final status without side-effect counts | Double charges/shipments missed | Idempotency assertions |
| Unsynchronized mutable singleton state | Lost updates and data races | Immutable messages, atomic DB state |
| Sharing `ThreadLocal` across `ExecutorChannel` | Drops tenant/correlation context | Explicit context propagation |
| Unbounded outstanding tasks | Unbounded memory/queue growth | Bounded executors and backpressure |
| Testing on H2 and assuming production lock semantics | Fails on real DB | Target DB integration tests |
| Skipping crash-after-commit-before-ack tests | Duplicates on restart | Fault injection + deduplication |
| Observing only `ErrorMessage`s on failures | Misses stalled/stopped pollers | Heartbeats, last-success, backlogs |
| Using one global lock across all orders | Low throughput, head-of-line blocking | Per-key serialization or optimistic concurrency |
| Putting `orderId`/`eventId` in metric labels | High-cardinality explosion | Aggregate metrics; trace IDs in logs |

## 24. Design and Testing Checklist

### A. Ordering Contract

- [ ] Classified as global, per-key, causal, event-time, or unordered.
- [ ] Defined required arrival/dequeue/start/finish/commit/observation guarantees.
- [ ] Assigned business keys, `eventId`, and versions/sequences.
- [ ] Defined policies for duplicates, stale events, missing sequences, and late callbacks.
- [ ] Separated source order from commit/side-effect order.

### B. Spring Integration Topology

- [ ] Documented `DirectChannel`, `QueueChannel`, `ExecutorChannel`, and PubSub boundaries.
- [ ] Identified source/consumer pollers, schedules, `maxMessagesPerPoll`, and task executors.
- [ ] Configured per-endpoint in-flight caps and backpressure.
- [ ] Defined group/correlation/timeout/release policies for splitters/aggregators/resequencers.
- [ ] Clarified in-memory channels vs. durable `MessageStore`s.
- [ ] Defined error channels and recovery policies for failures.

### C. Adapters and Transactions

- [ ] File/SFTP have ready protocols, filters, and duplicate/restart tests.
- [ ] HTTP has correlation, timeouts, idempotency keys, or reconciliation.
- [ ] JMS has group/consumer concurrency, transaction/ack, and redelivery tests.
- [ ] AMQP has prefetch, requeue/DLQ, and consumer failover tests.
- [ ] Kafka has key partitioning, consumer concurrency, offsets/DLTs, and retry policies.
- [ ] JDBC has claim/version/transaction semantics tested on production-like DBs.
- [ ] Outbox/inbox and side effects verified at commit time.

### D. Concurrency Tests

- [ ] Tested single producer/consumer and multiple producers/consumers.
- [ ] Tested forced out-of-order completion via latches/gates.
- [ ] Tested peak in-flight counts and concurrency caps.
- [ ] Tested lost updates, optimistic conflicts, and monotonic versions.
- [ ] Tested duplicate `eventId`s, retries, poison/gaps, and late callbacks.
- [ ] Tested crashes before/after DB commit and before/after ack.
- [ ] Tested multi-instance runs and rebalances/failovers where applicable.
- [ ] All async tests enforce bounded timeouts and executor/resource cleanup.

### E. Observability and Operations

- [ ] `correlationId`, `eventId`, business keys, and stages logged within policy.
- [ ] Metrics cover throughput, in-flight counts, lag, retries, conflicts, and stale events.
- [ ] Alerts fire when pollers/consumers stall even with zero errors.
- [ ] Logs omit sensitive payloads, tokens, and unnecessary secrets.
- [ ] Runbooks and owners exist for gaps, DLQ/quarantine, replays, and reconciliation.
- [ ] Every change to concurrency, partitions, or prefetch triggers regression tests.

## 25. Self-Check Questions

**Question 1.** Message M1 is sent before M2. Why can we not conclude M1 will commit before M2?

**Answer:** Beyond `ExecutorChannel` boundaries, parallel consumers, async HTTP, or separate DB transactions, M2 can finish/commit ahead of M1. Send order is not side-effect order.

**Question 2.** Does `DirectChannel` guarantee global ordering when two producer threads send concurrently?

**Answer:** No. `DirectChannel` runs handlers synchronously on the sender's thread, so concurrent senders interleave. Enforce explicit serialization or version policies when global order is required.

**Question 3.** `QueueChannel` receives 1, 2, 3 FIFO. With three polling consumers, can 3 finish before 1?

**Answer:** Yes. FIFO dequeue does not mean FIFO completion when multiple consumers process and commit at different speeds.

**Question 4.** Does `maxMessagesPerPoll(10)` mean at most 10 handlers execute concurrently?

**Answer:** No. It caps how many messages are polled per cycle, not thread concurrency; inspect task executors and instance counts.

**Question 5.** Why does using `Thread.sleep` in ordering tests cause flakiness?

**Answer:** Sleep only guesses scheduling timing, which fluctuates under CI load. Latches/barriers pin exact interleavings and wait with bounded timeouts.

**Question 6.** An `ExecutorChannel` test must prove out-of-order completion is possible. How?

**Answer:** Hold M1 at a latch after its handler starts, send M2, wait for M2 to finish, then release M1; assert completion order is M2 then M1.

**Question 7.** How do global order and per-key order differ?

**Answer:** Global order applies across all messages. Per-key order preserves order only within each `orderId`/`accountId`, letting unrelated keys execute concurrently.

**Question 8.** If event version 3 arrives before version 2, is updating the DB whenever `version < incomingVersion` always enough?

**Answer:** Only for latest-wins projections where intermediate states can be skipped. When every transition must occur sequentially, hold/wait for version 2 or handle gaps per policy.

**Question 9.** Can timestamps from two producers serve as the authoritative ordering key?

**Answer:** Avoid this when strict order matters: clock skew, timestamp resolution, and network delays break ordering. Use trusted domain versions/sequences.

**Question 10.** Does a splitter setting `sequenceNumber` guarantee downstream commits in order?

**Answer:** No. Sequence headers track group positions; a resequencer can release parts in order, yet async downstream stages can still commit out of order.

**Question 11.** Do File adapters read files in upload order or business sequence by default?

**Answer:** Never assume so. Directory listings, comparators, mtimes, filters, and readiness vary. For strict ordering, use explicit sequences/manifests and test through commit.

**Question 12.** Why might the second SFTP file to finish downloading be processed before the first?

**Answer:** File sizes, network latency, multiple pollers, remote/local filters, and worker concurrency affect receive/completion timing. Enforce explicit contracts and coordination.

**Question 13.** HTTP request A is sent before B. Is response A guaranteed to return before B?

**Answer:** No. Networks, downstream workers, and async callbacks can reorder responses. Correlation/request IDs must match responses to requests.

**Question 14.** In JMS, what is `JMSXGroupID` used for?

**Answer:** On supporting providers, it routes messages sharing a group to a single consumer via message grouping. Verify exact provider behavior, failover, and transactions rather than assuming broker-wide global order.

**Question 15.** In AMQP, if a consumer requeues the first message, can subsequent messages be processed ahead of it?

**Answer:** Yes, depending on queues, prefetch, consumer counts, and requeue/redelivery behavior. Ordering tests must cover nack/requeue and commit outcomes.

**Question 16.** Does Kafka guarantee ordering across two partitions?

**Answer:** No global cross-partition order exists. Kafka orders by offset within each partition; business ordering requires key/partition strategies and preserving order after the listener.

**Question 17.** Kafka inbound preserves offset order, yet the handler routes into an `ExecutorChannel`. Can DB commits go out of order?

**Answer:** Yes. Async workers can finish out of order. Enforce per-key serialization or version checks/resequencing where side effects commit.

**Question 18.** Is `SELECT ... ORDER BY created_at` in JDBC enough to ensure two workers commit in order?

**Answer:** No. Concurrent claims, locks, transaction durations, and retries govern commit order. Pair atomic claiming/optimistic versions with business rules.

**Question 19.** Why is deduplicating by `eventId` essential even when final order status looks right?

**Answer:** Duplicates can double-charge, double-ship, or double-notify even when final status appears identical. Always assert side-effect counts.

**Question 20.** When a message lands in a DLT, can later versions for the same key proceed normally?

**Answer:** Depends on the business contract. Sequential state machines must hold the key and resolve/reconcile gaps; latest-wins systems can proceed under explicit audited rules.

**Question 21.** A worker commits DB changes then crashes before broker ack. What does the redelivery require?

**Answer:** Deduplication/idempotency and durable commit tracking to prevent repeating side effects; test with fault injection right at the commit–ack boundary.

**Question 22.** Does a passing `QueueChannel` test prove an SFTP inbound cluster won't duplicate files?

**Answer:** No. Clusters require testing remote/local filters, shared metadata/claims, locking, restarts, and business deduplication on real or compatible SFTP environments.

**Question 23.** If tests observe zero `ErrorMessage`s, can we conclude the poller is healthy?

**Answer:** No. A poller can stop running or receive nothing without throwing exceptions. Track last-poll, last-non-empty-poll, backlogs, and health metrics.

**Question 24.** Should we pick one global worker or parallel per-key processing to preserve order?

**Answer:** Depends on requirements and load. One worker caps concurrency and can bottleneck; per-key serialization or optimistic versioning lets unrelated keys scale concurrently.

**Question 25.** What is the most trustworthy evidence of end-to-end correctness?

**Answer:** Business invariants and side effects at the commit/target boundary, backed by retry, duplicate, recovery, and correlation audits. Channel receive order or log order alone is purely local evidence.

## 26. Conclusion

**Concurrency** lets Spring Integration handle higher throughput, while exposing the gap between **receive order, dispatch order, completion order, and commit order**. A `DirectChannel`, `QueueChannel`, polling endpoint, or Kafka partition only guarantees what its topology and protocol actually support; none automatically enforces your full business ordering contract.

To test reliably, start from the **business contract**: does the system need global order, per-key order, causal order, or merely monotonic state versions? Use **latches/barriers to provoke deliberate interleavings**, run **integration tests against real adapters**, verify **transactions, acknowledgments, retries, redeliveries, and side effects**, and enforce **idempotency, state machines, optimistic locking, or resequencers** where required.

For File/SFTP, watch listing/download order, file readiness, and filters. For HTTP, verify request–response correlation and unknown timeout outcomes. For JMS/AMQP, check message grouping, consumer concurrency, prefetch, acks, and DLQs. For Kafka, separate **per-partition ordering** from **post-listener processing/commit order**. For JDBC, `ORDER BY` orders result sets—it never replaces **transactional claiming, version checks, and concurrency control**.

A strong ordering test proves more than a sorted list of messages: it proves that **when messages arrive late, duplicate, retry, cross threads, or a worker crashes, the system still preserves accurate business state with zero bogus side effects**.

### Official References

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): `MessageChannel`, endpoints, pollers, aggregators, resequencers, adapters, and testing.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): listener containers, concurrency, acknowledgments, retries, and dead-letter topics.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): RabbitMQ listener containers, acknowledgments, concurrency, and retries.
- [Spring Framework TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): integration testing with Spring contexts.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter, assertions, parameterized and repeated tests.

Java, SQL, JSON, and Mermaid examples in this lesson are educational. Java DSL APIs, transaction support, thread scheduling, and broker ordering vary across versions and configurations. Always verify against your actual dependencies and test in production-representative environments before claiming concurrency/ordering guarantees.
