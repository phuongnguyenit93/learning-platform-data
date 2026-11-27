# Preventing Priority Starvation in Spring Integration

## 1. The Problem: Continuous High Priority Prevents Normal Requests from Ever Being Processed

An order-processing service has three event categories:

- **HIGH**: cancel risky transactions, block fraudulent orders, process critical alerts.
- **NORMAL**: update order status, confirm payments.
- **LOW**: synchronize reports, update statistical metrics, and run maintenance tasks.

The system uses a `PriorityChannel` to dequeue high-priority messages first. During peak hours, HIGH events arrive so rapidly that whenever a consumer finishes a task, a new HIGH message is already waiting. LOW messages remain in the channel with no errors raised, yet **their turn never arrives**.

This is **priority starvation**: a class of valid work is delayed indefinitely or excessively because the scheduler continuously serves another higher-priority class. Unlike messages failing or getting lost, messages may persist reliably yet **make no progress**.

In the `SPRING_INTEGRATION_PATTERN` module, the goal of Enterprise Integration Patterns is to organize Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation into loosely coupled, easily extensible message flows. For a priority flow to operate reliably, **business prioritization** must be combined with **fairness, wait-time bounds, and observability**.

### Learning Objectives

After this lesson, you will be able to:

1. Explain why a default `PriorityChannel` can cause starvation even while operating strictly as designed.
2. Distinguish **priority ordering**, **FIFO**, **fairness**, **aging**, **backpressure**, and **latency guarantees**.
3. Design a flow using multiple `QueueChannel`s and weighted round-robin so LOW gets guaranteed processing opportunities.
4. Understand the limitations of custom `Comparator<Message<?>>` and why you cannot rely solely on a clock to age an already-populated priority heap.
5. Design retries, error channels, poison-message handling, idempotency, and durable handoffs without reintroducing starvation.
6. Write continuous-load tests and monitor age/lag per priority tier in production.

## 2. What Does PriorityChannel Actually Do?

`PriorityChannel` is a `PollableChannel` in Spring Integration. Rather than dequeuing messages strictly in queue-entry order like a regular FIFO queue, this channel prioritizes messages using the **`priority` header** or a configured comparator.

Example:

~~~java
@Configuration
@EnableIntegration
class PriorityChannelConfiguration {
    @Bean("priorityInput")
    PollableChannel priorityInput() {
        return new PriorityChannel(200);
    }
}
~~~

Sending messages with different priorities:

~~~java
Message<String> urgent = MessageBuilder.withPayload("CANCEL_RISKY_ORDER")
        .setHeader("priority", 9)
        .setHeader("businessEventId", "E-HIGH-01")
        .build();

Message<String> regular = MessageBuilder.withPayload("UPDATE_REPORT")
        .setHeader("priority", 1)
        .setHeader("businessEventId", "E-LOW-01")
        .build();

priorityInput.send(regular);
priorityInput.send(urgent);

// In the default configuration, urgent can be dequeued before regular,
// even though regular arrived earlier.
Message<?> first = priorityInput.receive(0);
~~~

In standard Spring Integration versions, priority is read from the `priority` header; **larger values take higher priority**. You can pass a `Comparator<Message<?>>` to customize ordering:

~~~java
@Bean("customPriorityInput")
PollableChannel customPriorityInput() {
    Comparator<Message<?>> comparator = (left, right) -> {
        int p1 = ((Number) left.getHeaders()
                .getOrDefault("priority", 0)).intValue();
        int p2 = ((Number) right.getHeaders()
                .getOrDefault("priority", 0)).intValue();
        return Integer.compare(p2, p1); // Higher priority first.
    };
    return new PriorityChannel(200, comparator);
}
~~~

**Important distinction:** configuring `PriorityChannel` determines how *the next message* is chosen; it does not define an anti-starvation mechanism. If HIGH continuously enters before every consumer poll, LOW can wait forever.

> Never assume two messages with the same priority are always processed FIFO solely because they share the same header. In a comparator-sorted queue, tie order when the comparator returns `0` can be unstable; if FIFO within the same level is required, add a secondary ordering key or use separate FIFO queues per class.

### Priority Is Not an SLA

If the business defines “HIGH is processed earlier than LOW”, that is **relative ordering**. If the business defines “LOW is processed within at most 60 seconds”, that is a **wait-time commitment**. A strict priority queue can fulfill the first well yet remain insufficient for the second.

## 3. Demonstrating Starvation with a Finite Example

Suppose each time the consumer is ready to receive a message, a producer submits another HIGH message:

~~~text
T0: enqueue LOW-1
T1: enqueue HIGH-1  -> receive HIGH-1
T2: enqueue HIGH-2  -> receive HIGH-2
T3: enqueue HIGH-3  -> receive HIGH-3
...
Tn: enqueue HIGH-n  -> receive HIGH-n

LOW-1: remains in the queue at every point in time.
~~~

This is not a message-loss bug. The scheduler is faithfully selecting higher-priority work according to the configured rule.

### Small Test to Reproduce

~~~java
@Test
void continuousHighPriorityTrafficCanDelayLowForever() {
    PriorityChannel channel = new PriorityChannel(100);

    channel.send(MessageBuilder.withPayload("LOW")
            .setHeader("priority", 1).build());

    for (int i = 0; i < 50; i++) {
        channel.send(MessageBuilder.withPayload("HIGH-" + i)
                .setHeader("priority", 9).build());

        Message<?> received = channel.receive(0);
        assertNotNull(received);
        assertTrue(received.getPayload().toString().startsWith("HIGH-"));
    }

    Message<?> remaining = channel.receive(0);
    assertNotNull(remaining);
    assertEquals("LOW", remaining.getPayload());
}
~~~

This finite loop shows that whenever a new HIGH appears before a poll, LOW stays behind. In production, if HIGH continues arriving without pause, LOW's wait time can grow without bound.

### Capacity Perspective

Let:

- `λ_H`: arrival rate of HIGH (messages/second).
- `λ_L`: arrival rate of LOW.
- `μ`: total processing capacity, assuming roughly comparable processing cost per message.

If `λ_H ≥ μ` and consumers always pick HIGH first, LOW can **receive zero service slots** even while the system processes many messages per second. Even when `λ_H < μ`, large HIGH bursts or variable processing times can push LOW past its allowed wait threshold.

If `λ_H + λ_L > μ` persistently, **no turn-sharing algorithm can keep the total backlog bounded** with fixed capacity. Fairness only allocates scarce capacity; you still need scaling, admission throttling, or policy-driven load shedding.

## 4. Distinguishing Starvation from Other Issues

| Phenomenon | Symptom | Do not confuse with |
| --- | --- | --- |
| **Priority starvation** | LOW queue has messages yet almost zero dequeues; oldest message age rises. | Message loss due to crash. |
| **Head-of-line blocking** | One slow/failing message stalls the processing slot even after the scheduler picked it. | Broken priority comparison itself. |
| **Priority inversion** | A HIGH task waits for a resource/lock held by a LOW task. | LOW starvation caused by HIGH hogging the scheduler. |
| **Capacity starvation** | Queue/broker is full of HIGH; LOW is rejected at enqueue time. | LOW was accepted but never gets its turn. |
| **Retry starvation** | A failing message retries continuously at high priority, consuming processing slots. | Natural growth in valid HIGH traffic. |
| **Tenant starvation** | One customer/tenant emits huge volume while other tenants wait indefinitely. | Having only two classes HIGH/LOW. |

A system can suffer from multiple phenomena simultaneously. For example, unbounded HIGH retries keep the HIGH queue non-empty, starving LOW while simultaneously spiking the error rate.

## 5. Anti-Starvation Strategies

| Solution | Principle | Advantages | Limitations |
| --- | --- | --- | --- |
| **Weighted round-robin (WRR)** | Cycles through multiple queues according to chosen weights. | Easy to explain; guarantees service turns by **message count** as long as scheduler advances. | Does not balance CPU time if per-class processing durations differ widely. |
| **Aging** | Increases effective priority as a message waits longer. | Old messages gradually rise to the front. | Requires a data structure/scheduler that actually re-evaluates order; capped bonuses may be insufficient. |
| **Oldest-first override / deadline** | Once a message exceeds an age threshold, grant it a turn regardless of normal priority. | Directly tied to wait-age goals. | Cannot guarantee hard wall-clock deadlines if workers hang or traffic saturates resources. |
| **Reserved capacity** | Dedicates workers or minimum quota to LOW/NORMAL. | Isolates progress of lower-priority classes. | Can leave capacity idle without work stealing. |
| **Admission control / backpressure** | Throttles HIGH traffic and returns overload signals. | Prevents unbounded backlog growth; protects shared resources. | Requires business rules for retries, rejections, or degradation. |
| **Per-source/tenant rate limiting** | Limits any single producer from monopolizing queues or downstreams. | Prevents one source from starving the entire system. | Requires source identification keys and anti-circumvention controls. |
| **Deficit round-robin / weighted fair queuing** | Allocates credits based on weights and estimated processing cost. | Fairer when messages vary in size/cost. | More complex than WRR; requires known or measured costs. |

In many enterprise systems, **multiple FIFO queues + weighted scheduler + age threshold + backpressure** is a far more testable starting point than a single dynamic comparator.

## 6. Approach 1 — Splitting Messages into HIGH, NORMAL, and LOW

Instead of pushing all message types into one strict-priority `PriorityChannel`, use a `Router` to classify and route them to three `QueueChannel`s. Each queue processes **FIFO within its own class**.

~~~mermaid
flowchart LR
    A["Gateway / Inbound adapter"] --> B["Validate + Transformer"]
    B --> R{"Priority Router"}
    R --> H["highQueue: FIFO"]
    R --> N["normalQueue: FIFO"]
    R --> L["lowQueue: FIFO"]
    H --> W["Weighted Fair Dispatcher"]
    N --> W
    L --> W
    W --> D["DirectChannel"]
    D --> S["Service Activator / DB"]
    S --> E["Completion / metrics"]
~~~

Example channel configuration:

~~~java
@Configuration
@EnableIntegration
@EnableScheduling
class FairChannelConfiguration {

    @Bean("highQueue")
    PollableChannel highQueue() {
        return new QueueChannel(500);
    }

    @Bean("normalQueue")
    PollableChannel normalQueue() {
        return new QueueChannel(500);
    }

    @Bean("lowQueue")
    PollableChannel lowQueue() {
        return new QueueChannel(500);
    }

    @Bean("processingInput")
    DirectChannel processingInput() {
        return new DirectChannel();
    }
}
~~~

This is an **in-memory exercise**, not an architecture guaranteeing zero data loss on application crash. Default `QueueChannel` has no durable storage, and dequeuing from RAM does not roll back alongside JDBC.

### Defining Priority at the Ingestion Boundary

Never trust arbitrary `priority` values sent by external clients. For instance, an unauthorized client tagging thousands of report messages as HIGH would break quotas. Normalize and classify inside the service:

~~~java
enum WorkClass {
    HIGH, NORMAL, LOW
}

record WorkItem(
        String eventId,
        String tenantId,
        String type,
        Instant submittedAt) {}

static WorkClass classify(WorkItem item) {
    return switch (item.type()) {
        case "FRAUD_ALERT", "RISK_CANCELLATION" -> WorkClass.HIGH;
        case "ORDER_CONFIRMED", "PAYMENT_RECEIVED" -> WorkClass.NORMAL;
        default -> WorkClass.LOW;
    };
}
~~~

Classifying **by trusted business rules** also prevents situations where every producer marks itself HIGH, rendering priority meaningless.

## 7. Approach 2 — Weighted Round-Robin with a Guaranteed Slot for LOW

Instead of “always HIGH first”, define a service cycle as follows:

~~~text
HIGH, HIGH, HIGH, HIGH, NORMAL, NORMAL, LOW
  1     2     3     4       5       6      7
  |__________________ one cycle _______________|
~~~

If **all three queues continuously have work**, in every seven selections LOW receives one turn, NORMAL receives two turns, and HIGH receives four turns. The ratio by **task count** is 4:2:1, not an absolute CPU-time allocation guarantee.

When a queue is empty, the scheduler can be **work-conserving**: pull from another queue rather than leaving workers idle. When LOW has work again, its next LOW turn still appears because the schedule cursor is preserved.

### Java: Single-Worker, Easily Testable Dispatcher

~~~java
@Component
class WeightedFairDispatcher {
    // 4 HIGH slots, 2 NORMAL slots, 1 LOW slot.
    private static final int[] SCHEDULE = {0, 0, 0, 0, 1, 1, 2};

    private final PollableChannel[] input;
    private final MessageChannel processingInput;
    private int nextSlot;

    WeightedFairDispatcher(
            @Qualifier("highQueue") PollableChannel high,
            @Qualifier("normalQueue") PollableChannel normal,
            @Qualifier("lowQueue") PollableChannel low,
            @Qualifier("processingInput") MessageChannel processingInput) {
        this.input = new PollableChannel[]{high, normal, low};
        this.processingInput = processingInput;
    }

    // Invoked periodically by @Scheduled; public so tests can call directly.
    @Scheduled(fixedDelay = 50)
    public synchronized void scheduledTick() {
        dispatchOnce();
    }

    public synchronized boolean dispatchOnce() {
        // If the queue for the current slot is empty, try subsequent slots.
        for (int offset = 0; offset < SCHEDULE.length; offset++) {
            int slot = (nextSlot + offset) % SCHEDULE.length;
            PollableChannel candidate = input[SCHEDULE[slot]];
            Message<?> message = candidate.receive(0); // Non-blocking.

            if (message == null) {
                continue;
            }

            nextSlot = (slot + 1) % SCHEDULE.length;

            // DirectChannel -> synchronous handler on the scheduler thread.
            boolean accepted = processingInput.send(message);
            if (!accepted) {
                throw new IllegalStateException(
                        "Processing channel rejected message");
            }
            return true;
        }

        // No queue has work; avoid pinning the cursor.
        nextSlot = (nextSlot + 1) % SCHEDULE.length;
        return false;
    }
}
~~~

Explaining one iteration:

1. `nextSlot` identifies the expected slot along the weighted sequence.
2. `receive(0)` attempts to pull a message **without blocking** on an empty queue.
3. If that queue is empty, it scans subsequent slots to utilize available capacity.
4. Once a message is dequeued, it advances the cursor **before processing** so the next call continues the cycle.
5. `processingInput` is a `DirectChannel`, so the handler runs synchronously. Handler execution duration dictates how fast the scheduler advances.

**Conditional guarantee:** If the scheduler keeps running, each dispatch finishes in finite time, and LOW continuously has work, then even when other queues always have work, LOW gets **at least one opportunity in every seven-pick cycle**. This does not automatically create a 60-second bound if a handler takes minutes or a worker hangs.

**Distinguishing progress from stable backlog:** When all three queues always have work, one-seventh of selections go to LOW. If LOW's arrival rate exceeds the processing capacity of that one-seventh share over a long period, LOW's backlog and wait time still grow even though LOW is no longer completely starved. To stabilize, increase LOW's weight/capacity, throttle inbound load, or apply quotas and backpressure; when per-class processing times differ, allocate by **service time** rather than message counts alone.

### Why Not Attach @Scheduled Independently to Each Queue?

Three independent pollers sharing a pool can produce **accidental** fairness, especially when the pool is small and HIGH handlers keep occupying threads. If you want a 4:2:1 quota, you need a **central coordinator**, partitioned worker pools, or a scheduling mechanism that enforces true quotas. Creating three queues without specifying turn allocation **does not solve starvation**.

### Example Handler Behind DirectChannel

~~~java
@Service
class WorkHandler {
    public void process(WorkItem work) {
        // Check idempotency, run business logic,
        // and record latency/queue wait by work.type().
    }
}

@Bean
IntegrationFlow processingFlow(WorkHandler handler) {
    return IntegrationFlow.from("processingInput")
            .handle(handler, "process")
            .get();
}
~~~

**Reliability warning:** Once `receive(0)` pulls a message from an in-memory `QueueChannel`, if the handler throws an exception, `dispatchOnce()` does not automatically return the message to the queue. Never use this illustrative snippet as a production template requiring **at-least-once** delivery. For critical data, use a durable source with dequeue/ACK + transaction/error handling, or persist work into a durable inbox before acknowledging.

## 8. Testing Fairness Under Continuous HIGH Traffic

Do not only test “LOW is processed when the HIGH queue is empty”, because that is not the starvation scenario. Keep HIGH continuously populated and prove the scheduler **still allocates slots to LOW**.

### Pure Channel Unit Test

~~~java
@Test
void lowPriorityMakesProgressWhileHighHasBacklog() {
    QueueChannel high = new QueueChannel(100);
    QueueChannel normal = new QueueChannel(100);
    QueueChannel low = new QueueChannel(100);
    DirectChannel processing = new DirectChannel();

    List<String> processed = new ArrayList<>();
    processing.subscribe(message ->
            processed.add((String) message.getPayload()));

    for (int i = 0; i < 35; i++) {
        high.send(MessageBuilder.withPayload("H-" + i).build());
    }
    for (int i = 0; i < 14; i++) {
        normal.send(MessageBuilder.withPayload("N-" + i).build());
    }
    for (int i = 0; i < 7; i++) {
        low.send(MessageBuilder.withPayload("L-" + i).build());
    }

    WeightedFairDispatcher dispatcher =
            new WeightedFairDispatcher(high, normal, low, processing);

    for (int i = 0; i < 14; i++) {
        assertTrue(dispatcher.dispatchOnce());
    }

    // When all three queues stay non-empty, two cycles yield two LOW slots.
    long lowProcessed = processed.stream()
            .filter(value -> value.startsWith("L-"))
            .count();
    assertEquals(2L, lowProcessed);
    assertTrue(processed.subList(0, 7).contains("L-0"));
}
~~~

The test populates enough HIGH/NORMAL messages so every queue retains a backlog across all 14 dispatches. With a 4:2:1 schedule, LOW is chosen at the end of the first and second cycles. If the scheduler were accidentally switched to strict priority, this test would fail.

### Property-Based / Stress Tests

For variable workloads, also verify these properties:

- LOW continuously pending and handlers always complete → LOW dequeue count **never stalls** across cycles.
- No LOW traffic → scheduler still utilizes full available capacity for HIGH/NORMAL.
- When LOW resumes → does not wait for HIGH to drain completely before being served.
- When HIGH pauses → NORMAL/LOW utilize workers without artificial throttling.
- Continuous HIGH retries → budget remains for valid LOW messages.
- Multiple producers/tenants entering the same queue → one tenant does not consume all slots of a priority tier.

Unit tests on dispatch counts verify the algorithm; integration tests with real brokers, databases, and workers verify **latency, ACK, durability, and concurrency**.

## 9. Approach 3 — Aging: Raising Priority Over Wait Time

Aging makes a lower-priority message “more deserving of earlier service” once it has waited in the queue too long.

An illustrative formula:

~~~text
effectivePriority(t)
    = basePriority
      + floor((t - originalEnqueueTime) / agingStep)

Example:
  basePriority LOW = 1
  agingStep = 10 seconds
  LOW waits 40 seconds -> effectivePriority = 5
~~~

For an aged LOW message to overtake a newly arrived HIGH message, **the growth must be large enough** or a deadline/age override rule must apply. If the bonus caps at 2 points while HIGH is always 100, LOW can still starve.

### Pitfall: A Clock-Based Comparator Does Not Re-Order a Heap

A seemingly plausible idea that **should not be applied directly**:

~~~java
Comparator<Message<?>> dynamicComparator = (a, b) -> {
    long now = System.currentTimeMillis();
    int aScore = basePriority(a) + ageBonus(a, now);
    int bScore = basePriority(b) + ageBonus(b, now);
    return Integer.compare(bScore, aScore);
};
~~~

In a priority heap/queue, the comparator is generally invoked during **insertion, removal, or rebalancing**; the queue has no obligation to re-evaluate every element as wall-clock time advances. A message gaining score over time **is not guaranteed to bubble to the top of the heap automatically**. A time-varying comparator also undermines reasoning about heap order stability.

**More reliable approaches:**

1. Persist `originalEnqueueTime` durably.
2. Run a periodic job to **promote** aged messages to a higher priority tier, or have the scheduler query/claim messages by effective priority at selection time.
3. Perform tier promotion safely using transactions or ACK/retry mechanics when backed by durable storage.
4. Preserve `eventId`, `originalEnqueueTime`, and attempt counts during promotion; do not turn an old message into a brand-new business event.
5. Test under continuous HIGH load to confirm promoted messages **actually receive turns**.

Example policy:

| Wait age since initial enqueue | Action |
| --- | --- |
| Under 15 seconds | Keep original priority class. |
| 15–45 seconds | Promote one class or grant dedicated turns for aged tasks. |
| Over 45 seconds | Mark as deadline-prioritized if source and resources allow. |
| Over 60 seconds | Alert on SLO breach, scale capacity / escalate; never promise automatic completion if resources are saturated. |

If a WRR scheduler already ensures proportional progress for LOW yet still misses **maximum latency** targets, combine it with aging or oldest-first override instead of endlessly inflating weights.

## 10. Approach 4 — Protecting Deadlines and Message Age

A system might define:

~~~text
HIGH: low latency priority, p99 queue wait <= 2 seconds
NORMAL: p99 queue wait <= 10 seconds
LOW: p99 queue wait <= 60 seconds
~~~

These numbers are **SLO examples**, not default Spring Integration behavior. In operations, monitor:

- **Queue wait**: from durable receipt until processing starts.
- **End-to-end latency**: from business event creation until business side effects commit.
- **Oldest pending age**: age of the longest-waiting message per class.
- **Deadline miss rate**: percentage of messages exceeding their deadline.
- **Time since last completed LOW**: elapsed time since LOW last made progress.

An override algorithm might look like:

~~~text
each scheduling decision:
  if oldest LOW waiting >= threshold:
      choose LOW, provided processing resources available
  else if oldest NORMAL waiting >= threshold:
      choose NORMAL
  else:
      follow weighted schedule 4:2:1
~~~

When multiple classes exceed their thresholds simultaneously, define a clear tie-break order (e.g., earliest deadline first, or a business rule never to delay critical-risk HIGH items). **Do not** apply a single threshold like `LOW > 30s` blindly without considering processing cost; a 10-minute LOW job can still cause HIGH to miss its SLO if only one worker exists.

### Mathematical Limits

WRR guarantees **selection turns** assuming the scheduler and handlers make progress; it cannot guarantee completion before an absolute wall-clock cutoff when:

- Handlers hang or hold locks indefinitely.
- Total arrival rate persistently exceeds processing capacity.
- One class contains abnormally slow messages.
- Upstream/downstream dependencies fail, brokers/DBs are unavailable, or retries drag out.
- A shared resource bottlenecks everything (connection pool, CPU, DB locks, downstream rate limits).

For stronger SLO compliance, combine **timeouts, bulkheads, admission control, worker capacity, and direct wait-age monitoring**—not just a comparator tweak.

## 11. Approach 5 — Reserved Capacity and Bulkheads

For very expensive HIGH jobs or multi-tenant workloads, a shared scheduler can still be blocked by long-running handlers. Dedicate **separate worker pools** per tier:

~~~mermaid
flowchart LR
    R["Router"] --> H["HIGH Queue"]
    R --> N["NORMAL Queue"]
    R --> L["LOW Queue"]
    H --> HP["HIGH workers: 4"]
    N --> NP["NORMAL workers: 2"]
    L --> LP["LOW worker: 1"]
    HP --> DB[("DB / downstream")]
    NP --> DB
    LP --> DB
~~~

For instance, with seven workers, allocate 4/2/1 workers to HIGH/NORMAL/LOW. Even if HIGH floods, the single LOW worker continues independently, **provided** the shared downstream still has capacity.

Trade-offs:

- The LOW worker may sit idle when only HIGH work exists.
- Seven workers contending for a tiny connection pool can still stall LOW progress.
- If the downstream enforces a shared rate limit, enforce quotas/reservations at the **downstream boundary itself**.
- If using work stealing to avoid idle workers, never steal the **minimum reserved capacity** promised to LOW.

Bulkheads fit well when you must protect progress for one class or tenant despite heavy load in another. They do not replace backpressure when total demand exceeds available resources.

## 12. Backpressure and Capacity: Do Not Reject LOW at the Door

Starvation can begin **before the scheduler even runs**: HIGH traffic fills all memory/broker queue capacity, causing LOW enqueues to be rejected.

Example with a bounded `QueueChannel`:

~~~java
@Bean("lowQueue")
PollableChannel lowQueue() {
    return new QueueChannel(200);
}

boolean accepted = lowQueue.send(message, 250);
if (!accepted) {
    // Queue full / wait timed out.
    // Apply retry policy, durable fallback, or signal overload.
}
~~~

Depending on channel and configuration, `send(message, timeout)` waits for capacity up to the timeout and then returns failure. **Do not** equate a failed send with the message being durably saved somewhere.

Ways to protect capacity:

1. **Throttle HIGH ingress** by producer/tenant and event type.
2. **Reserve capacity or quotas** for LOW/NORMAL instead of letting HIGH fill one shared queue.
3. **Deduplicate before enqueuing** when noisy producers or retries emit identical messages.
4. **Coalesce** aggregatable report messages, but only when the domain permits skipping intermediate states.
5. **Durable fallback/retry** for critical work; never silently drop messages on queue full.
6. **Scale workers** or reduce handler cost when sustained arrival rate exceeds capacity.

Capacity should be sized across message count, payload size, backlog age, and resource consumption (RAM, DB, connections, broker quotas)—not just a single `capacity` number.

## 13. Retries and Error Channels Can Reintroduce Starvation

A HIGH message with an invalid schema that fails and retries immediately at priority 9 can consume almost every HIGH slot. With unbounded retries or constant broker redelivery, both valid HIGH and LOW messages suffer delays.

### Bounded Retry Rules

~~~text
Receive event
  -> Validate payload
      -> permanent error: quarantine / DLQ
  -> Process in business transaction
      -> success: commit + acknowledge according to source
      -> transient error: rollback, retry with bounded backoff
      -> retries exhausted: durable error record / DLQ
~~~

Here:

- **Transient errors**: brief DB disconnect, downstream timeout, lock contention; retry with backoff and appropriate jitter.
- **Permanent errors**: invalid schema, forbidden event, missing required fields; send to an inspectable error sink.
- **Ambiguous outcome errors**: the receiver may have committed despite caller timeout; rely on stable `eventId` and idempotency.
- **Retry budget** should have its own quota so retrying messages do not starve new work.

### Error Channel

In Spring Integration, errors can be wrapped in an `ErrorMessage` and sent to an `errorChannel` depending on the endpoint. However, an error flow receiving an exception **does not prove** that the transaction rolled back or that the broker will redeliver.

| Situation | Impact on starvation/delivery |
| --- | --- |
| Synchronous handler throws exception back to transactional poller. | DB may roll back; source may or may not redeliver depending on resource and ACK. |
| Handler catches exception, only logs, and returns. | Poller/listener may consider the message processed even though business logic did not complete. |
| Error handler retries infinitely at high priority. | Poison message causes retry storms and starvation. |
| Retries scheduled onto a separate **delayed queue**. | Prevents one failing message from monopolizing the scheduler; requires durable retry and attempt limits. |
| Error flow sends to DLQ and returns. | Must ensure DLQ persistence succeeds per policy before ACKing the original message if zero loss is required. |

**Do not** use an in-memory `PriorityChannel` + catch exception + infinite `send()` loop as a production redelivery mechanism. It risks losing messages on process crash, creating error loops, and starving other classes.

## 14. Durable Messaging, Transactions, and Idempotency in Production

The WRR example in Section 7 uses three in-memory queues to illustrate the algorithm. When events carry business value, use a durable source:

- **JMS/AMQP**: separate queues by priority or routing key; each consumer/dispatcher has proper adapter ACK/redelivery.
- **Kafka**: partition/topic grouping and appropriate consumer progress; you cannot arbitrarily delete or merge offsets like an in-memory queue.
- **JDBC-backed MessageStore**: persist messages in a DB with properly configured transactions and pollers.
- **Durable inbox**: receive the message and write the request and metadata into the DB inside a transaction before returning success inbound.

### Choosing Implementation by Guarantees

| Setup | Fairness | Recoverability | Additional design required |
| --- | --- | --- | --- |
| Single in-memory `PriorityChannel`, strict priority | No guarantee for LOW under continuous HIGH. | Lost on process crash. | Aging/quotas, durable store if needed. |
| Three in-memory `QueueChannel`s + WRR | Dispatch-turn quota while scheduler advances. | Not durable. | Durable handoff, retry/ACK, idempotency. |
| Multiple durable queues + weighted consumers | Dedicated quotas/workers possible. | Depends on store/broker and ACK/transaction. | Rebalancing, concurrency, retry, DLQ, monitoring. |
| Single persistent priority store | Durable storage and store-level priority order. | Depends on store; does not imply fairness. | Anti-starvation in scheduler or class splitting. |

When using a priority-capable message store, check the **store's** API and sorting rules. Per Spring Integration documentation, configuring a priority channel backed by a message store requires a `PriorityCapableChannelMessageStore` implementation; depending on configuration, **do not combine in-memory queue comparator/capacity options with the message-store option**. Never assume an in-memory custom comparator automatically applies to a JDBC/Redis/Mongo priority store.

### ACK, Transactions, and Redelivery

If the scheduler dequeues a message from a durable queue before the handler commits, a crash can trigger redelivery. Conversely, if the scheduler commits ACK/dequeue too early and the handler fails afterward, the message can be lost.

A safe design explicitly defines:

1. **When is the message claimed/received?**
2. **When does the business transaction commit?**
3. **When is the ACK/offset committed or the record deleted from the durable store?**
4. **If a crash occurs between steps 2 and 3, can the message be redelivered?**
5. **How does idempotency prevent duplicate side effects?**

Example consumer writing to a database:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

~~~java
@Transactional
public void handleImportantEvent(WorkItem item) {
    int claimed = jdbc.update("""
            INSERT INTO processed_events(consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """, "work-handler", item.eventId());

    if (claimed == 0) {
        return; // Redelivery: already committed previously.
    }

    // Perform business writes in the same transaction.
    applyBusinessChange(item);
}
~~~

The SQL above illustrates PostgreSQL. Both the marker and JDBC side effects must share the same transaction. If `applyBusinessChange` fails, the transaction rolls back the marker too. If the DB commits yet ACK fails, redelivery reusing `eventId` avoids duplicate updates. `correlationId` tracks workflow correlation and does not replace `eventId`.

If processing also emits downstream events to another system, consider the **transactional outbox**: write the outbound event alongside the business update, have a relay publish after commit, and keep downstream consumers idempotent. Outbox durably preserves publishing intent without requiring a global transaction across DB and broker.

## 15. Fairness Across Tenants and Priority Classes

Priority starvation does not occur only between HIGH and LOW. Tenant A can emit 90% of HIGH traffic and block Tenant B even though both are tagged HIGH.

Two-level model:

~~~mermaid
flowchart LR
    A["Messages with tenantId + business priority"] --> P["Router by class HIGH/NORMAL/LOW"]
    P --> T["Per-tenant dispatcher within each class"]
    T --> W["Weighted scheduler across classes"]
    W --> H["Workers / business handlers"]
~~~

Recommendations:

- **Per-tenant quota/token bucket** so one tenant cannot create an unbounded backlog.
- **Round-robin or deficit round-robin** among tenants that have waiting messages in the same priority tier.
- **Per-tenant concurrency limits** so one tenant's slow jobs cannot occupy all workers.
- **Server-assigned priorities**, never letting clients escalate `priority` arbitrarily.
- **Per-tenant and per-class SLOs**; global averages can hide small tenants being starved.

Tenant fairness and work-type prioritization are **two orthogonal dimensions**. Model policies along both axes rather than overloading a single priority integer.

## 16. Observability: Which Signals Reveal Starvation?

Do not track only messages processed per second. A system with high HIGH throughput can still be starving LOW.

| Metric | How to read it | Action when unhealthy |
| --- | --- | --- |
| `queue_depth{class}` | Waiting messages per class. | Check capacity, stalled consumers, or producer spikes. |
| `oldest_pending_age_seconds{class}` | Age of the oldest waiting message per class. | Look for starvation/poison messages; trigger age priority. |
| `queue_wait_seconds{class}` p95/p99 | Latency from enqueue to processing start. | Tune weights, workers, or admission control. |
| `completed_total{class}` | Actual progress per class. | If LOW pending > 0 while completions stay flat, investigate immediately. |
| `deadline_miss_total{class}` | Count of wait-SLO breaches. | Consider oldest-first override and capacity scaling. |
| `retry_total{class,reason}` | How retries consume service slots. | Tune backoff, retry budget, and DLQ. |
| `rejected_total{class}` | Messages rejected at ingress due to full queue. | Apply backpressure/fallback; never silently drop. |
| `active_handlers{class}` | Which class is holding workers. | Apply bulkheads, timeouts, and concurrency limits. |
| `last_progress_timestamp{class}` | Last time a class committed business work. | Detect non-empty queues making zero progress. |

**Illustrative alerts:**

~~~text
IF low_pending > 0
AND oldest_low_age > 45s:
    alert("LOW approaching wait-time SLO")

IF low_pending > 0
AND low_completions_last_60s == 0:
    alert("Possible starvation or stalled worker")
~~~

Also track:

- **Queue wait measured from the first enqueue**, not reset upon retry or promotion from LOW to NORMAL.
- **Actual processing time** per class so WRR can be calibrated if HIGH uses far more CPU than LOW.
- **Consumer lag, broker ACK, transaction rollbacks, and DLQ** for durable sources.
- **Correlation ID and event ID** to locate stalled messages and distinguish duplicates from new events.
- **Base priority and effective priority** after aging to explain why a message was picked.

Avoid logging payloads or sensitive data unnecessarily. A log line saying “receive succeeded” does not prove business side effects committed.

## 17. Advanced Testing: Failures, Concurrency, and Wait Times

| Scenario | Expected behavior |
| --- | --- |
| HIGH continuously enqueued before every poll. | LOW is still dispatched within budget under WRR; strict PriorityChannel can delay indefinitely. |
| Only HIGH in the queues. | Work-conserving scheduler does not leave workers needlessly idle. |
| HIGH/NORMAL empty, LOW has work. | LOW uses all available processing capacity without waiting for special slots. |
| LOW resumes after being empty. | Within a bounded number of picks, LOW is served without getting stuck on cursor state. |
| A HIGH handler hangs. | Timeouts/bulkheads prevent it from consuming all capacity needed for LOW. |
| A HIGH poison message retries continuously. | Bounded retries, backoff, and DLQ; LOW does not lose all service turns. |
| LOW queue is full. | Producer receives overload signal with clear retry/fallback; no silent loss. |
| Worker crashes after DB commit before ACK. | Redelivery creates no duplicate side effects thanks to event ID and idempotency. |
| Message promoted to higher priority via aging. | Original enqueue time and event ID are not reset; no duplicate processing occurs. |
| Multiple workers / multiple instances. | Fairness is designed at a shared layer or via quotas/sharding, not accidental local counters. |
| One tenant floods HIGH messages. | Per-tenant quotas ensure other tenants keep making progress. |
| Sustained load exceeds processing capacity. | Backpressure, alerts, scaling, or graceful degradation engage instead of claiming all SLOs hold. |

### Wait-Time Tests Must Control the Clock

To test aging, use a **fake/controllable clock** instead of calling `Thread.sleep(60_000)`. Create messages with a fixed `originalEnqueueTime`, advance the test clock, and invoke the scheduler or promotion job at deterministic points. This keeps tests fast, repeatable, and independent of CI machine timing.

For retries and redelivery, test against a real broker/MessageStore in integration tests when durable delivery is required; WRR unit tests alone do not prove ACK, rollback, or crash recovery.

## 18. Practice Exercises

**Exercise 1 — Reproduce starvation.** Use `PriorityChannel` with priority headers 9 and 1. Enqueue LOW first, then in a loop enqueue HIGH and call `receive(0)`. Explain why LOW is delayed even though the queue holds messages.

**Exercise 2 — Build a 4:2:1 schedule.** Create three `QueueChannel`s and a WRR dispatcher. Test 70 dispatches when all three queues stay backlogged: expect roughly 40 HIGH, 20 NORMAL, and 10 LOW selections, assuming handlers do not stall the scheduler.

**Exercise 3 — Test empty queues.** Enqueue only LOW while keeping HIGH/NORMAL empty. Verify the dispatcher does not waste 6/7 of turns and gives available capacity to LOW.

**Exercise 4 — Add aging.** Define `originalEnqueueTime` and promote classes when a message waits over 30 seconds. Use a fake clock to prove promotion works and wait age is not reset after retry.

**Exercise 5 — Priority and deadlines.** Define SLOs HIGH p99 ≤ 2s, LOW p99 ≤ 60s. Simulate HIGH handler duration increasing 10x. Compare message-count WRR with reserved workers and deadline override.

**Exercise 6 — Retries without starving queues.** Create a HIGH message that always throws exceptions, add a max retry budget of 3 with backoff. Verify the message moves to a DLQ and LOW continues progressing.

**Exercise 7 — Multi-tenancy.** Tenant A sends 90% of HIGH traffic, Tenant B sends 10%. Add per-tenant quotas and measure Tenant B's throughput and wait age under heavy load.

**Exercise 8 — Production readiness.** Replace the three in-memory queues with an appropriate durable message source; define exact dequeue/ACK, business transactions, retries, idempotency, worker loss handling, and scheduler resumption after restart.

### Self-Assessment Questions

**1. Does `PriorityChannel` prevent starvation by default?** No. It picks messages by priority; continuous HIGH traffic can leave LOW waiting indefinitely.

**2. What does 4:2:1 weighted round-robin guarantee?** While queues remain non-empty and the scheduler advances, it allocates **message selection turns** proportionally; it does not by itself guarantee wall-clock deadlines in seconds.

**3. Why shouldn't you use a `System.currentTimeMillis()` comparator to age a priority heap?** Because a heap does not automatically re-order all elements as time passes; you need an actual re-evaluation/rebuild/promotion mechanism.

**4. Is splitting into three queues sufficient for fairness?** No. You still need a worker/turn allocation policy across the queues.

**5. Why can LOW still be slow even with WRR?** Other handlers run too long, workers are scarce, downstreams are bottlenecked, total load is too high, or workers hang.

**6. What happens if a message is dequeued from an in-memory QueueChannel and the handler fails?** The message is not automatically returned merely by a JDBC rollback; reliability requires a durable source, ACK, and redelivery.

**7. When are outbox/inbox patterns needed?** When you must avoid losing publishing intent after a DB commit or prevent duplicates when consumers redeliver messages from external resources.

## 19. Pre-Production Checklist for Priority Flows

- [ ] Priorities are assigned by trusted business logic, never escalated arbitrarily by producers.
- [ ] Wait SLOs and minimum budgets are defined for each class.
- [ ] Strict priority is not mistaken for fairness; WRR, aging, deadline overrides, or reserved capacity are in place where needed.
- [ ] If using WRR, both **continuously full queues** and **empty queues** are tested.
- [ ] If using aging, real promotion/re-heap/selection logic exists rather than just a clock-reading comparator.
- [ ] Within-class FIFO is preserved if required by the business, retaining event ID and ordering metadata.
- [ ] Producer/tenant rate limits, backpressure, and queue-full policies are implemented.
- [ ] Timeouts and bulkheads protect other classes from slow or hung tasks.
- [ ] Retries are bounded with backoff, DLQ, and quotas so poison HIGH messages cannot occupy all workers.
- [ ] Critical messages use durable sources, proper ACK/transactions, and idempotency.
- [ ] Original enqueue time, eventId, and correlationId are preserved across retries and promotions.
- [ ] Oldest pending age, p95/p99 wait, low progress, queue depth, retries, and deadline misses are monitored.
- [ ] Overload, crashes, multiple instances, noisy tenants, duplicates, and partial failures are tested.
- [ ] Capacity limits are acknowledged: fairness does not replace scaling and admission control when sustained load exceeds capacity.

**Key takeaway:** **Priority puts important work first; fairness ensures lower-priority work still progresses.** `PriorityChannel` is an ordering tool, not a complete fair-scheduling system. In Spring Integration, preventing priority starvation requires deliberately designing quotas, aging/deadlines, or reserved workers, then testing them under continuous HIGH arrival, retries, and failures—matching real high-load production conditions.

### References

- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): `PriorityChannel` and channel types.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): `priority` header, comparators, capacity, and priority-capable message stores.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): transaction boundaries during message processing.

*Examples use in-memory queues to keep the algorithms and fairness tests easy to follow. In production deployments, verify APIs against your Spring Integration version, channel limits, broker/store contracts, and transaction/ACK settings; do not treat the sample scheduler as an out-of-the-box durable delivery solution.*
