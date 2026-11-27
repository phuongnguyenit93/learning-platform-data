# Testing Multiple Priority Levels in Spring Integration

## 1. Why Must Priority Testing Go Beyond a Numeric Comparison?

In an order-processing system, the business wants fraud-detection messages prioritized ahead of report-update messages. A basic test sends `priority=9` and `priority=1` into a `PriorityChannel` and asserts that 9 is dequeued first. That test is useful, yet **insufficient** to conclude the flow works properly in production.

In reality, with **HIGH/NORMAL/LOW**, messages may travel through a Gateway, Transformer, Filter, Router, Splitter, Aggregator, polling endpoint, retry, error channel, and a broker. All of the following can still happen even when a two-message test passes:

- A Transformer constructs a new `Message` and drops `priority` or changes `Integer` into `String`.
- HIGH arrives after LOW has already been dequeued, so it cannot reclaim execution.
- Multiple equal-priority messages dequeue out of FIFO order while tests accidentally assume stable ordering.
- Continuous HIGH arrivals leave LOW waiting indefinitely (**priority starvation**).
- Error flows retry HIGH infinitely, stealing capacity from valid work.
- Listeners use `ExecutorChannel` or multiple workers, causing **completion order** to differ from dequeue order.
- JMS/RabbitMQ fail to map priority headers properly; Kafka preserves records by offset rather than custom priority.
- A message is ACKed before the DB commits, or the DB commits and the message is redelivered, causing duplicate processing.

**Testing multiple priority levels** means testing an **end-to-end flow contract**: accurate classification, accurate metadata preservation, proper selection under deterministic conditions, no unapproved starvation of valid work, and clean recovery on failure.

This lesson belongs to the **Priority** chapter in the `SPRING_INTEGRATION_PATTERN` module, supporting the goal of implementing Enterprise Integration Patterns with Spring Integration in a loosely coupled, extensible, testable, and observable manner across every branch.

### Learning Objectives

After this lesson, you will be able to:

1. Design a **test matrix** covering HIGH/NORMAL/LOW, equal priorities, invalid priorities, and late arrivals.
2. Write JUnit 5 unit tests verifying `PriorityChannel`, comparators, dequeue order, and key invariants.
3. Separate **ordering** tests from **fairness, throughput, SLA, and durability** tests.
4. Verify `priority` across Transformer, Router, Filter, Splitter, Aggregator, and Gateway.
5. Test retries, error channels, dead-letter queues, redelivery, concurrency, and idempotency.
6. Separate pure-Java tests, Spring context integration tests, and real-broker tests.
7. Integrate tests into CI with measurable criteria, free of arbitrary `Thread.sleep` or random thread races.

## 2. Define the Priority Contract Before Writing Tests

First, clarify whether priority is a **business policy** or a **technical scheduler number**. We use three classes:

| Class | Internal `priority` header | Business example | Policy |
| --- | ---: | --- | --- |
| HIGH | `9` | Block risky transactions, urgent order cancellations | Prioritized while still waiting in the queue. |
| NORMAL | `5` | Confirm payments, update statuses | Must not lose all processing opportunity to unlimited HIGH. |
| LOW | `1` | Sync reports, periodic statistics | Receives quota/turns when fairness is required. |

This is an **illustrative convention**, not three mandatory Spring Integration values. With default `PriorityChannel`, larger numbers are prioritized when **dequeuing** waiting messages.

Publish explicitly:

- **Value range:** e.g., integers `0..9`, rejecting `"9"` strings unless passed through a controlled decoder.
- **Authority source:** only backend policy may decide HIGH; untrusted clients cannot self-escalate.
- **Missing header semantics:** reject, quarantine, or default to NORMAL/LOW with a recorded metric.
- **Identity:** stable `eventId` for deduplication; `MessageHeaders.ID` may change when building new messages.
- **Tie-breaking:** must equal-priority messages follow FIFO by `enqueueSequence`/timestamp?
- **Fairness:** is progress guaranteed for NORMAL/LOW under continuous HIGH? If so, via WRR, aging, deadlines, or reserved workers?
- **SLA/SLO:** when does latency start measuring—until processing begins or until business commit?

### Java Fixtures Used in Tests

The snippets below use Java 17+, Spring Integration, Spring Messaging, and JUnit Jupiter. When assembling into a project, place classes/methods in appropriate Java files with required imports.

~~~java
enum WorkClass {
    HIGH(9), NORMAL(5), LOW(1);

    private final int priority;

    WorkClass(int priority) {
        this.priority = priority;
    }

    int value() {
        return priority;
    }
}

record WorkEvent(String eventId, String type) {}

final class PriorityContract {
    static final String PRIORITY = "priority";
    static final String EVENT_ID = "businessEventId";
    static final String ENQUEUED_AT = "originalEnqueuedAt";

    private PriorityContract() {}

    static Message<WorkEvent> message(
            String eventId, WorkClass workClass) {
        return MessageBuilder.withPayload(
                    new WorkEvent(eventId, workClass.name()))
                .setHeader(PRIORITY, workClass.value())
                .setHeader(EVENT_ID, eventId)
                .build();
    }

    static int requirePriority(Message<?> message) {
        Object value = message.getHeaders().get(PRIORITY);
        if (!(value instanceof Integer priority)
                || priority < 0 || priority > 9) {
            throw new IllegalArgumentException(
                    "priority must be Integer in range 0..9");
        }
        return priority;
    }
}
~~~

Examples use the string header `priority` for readability. At HTTP/JMS/AMQP/Kafka boundaries, adapters may use **different headers or properties**; mapping tests must inspect the real target rather than comparing only this string key.

## 3. Test Matrix Before Writing Code

| Group | Input | Invariant to prove | Test level |
| --- | --- | --- | --- |
| **Three tiers** | LOW, HIGH, NORMAL, HIGH all enqueued | HIGH dequeues before NORMAL, NORMAL before LOW when priorities differ. | Unit |
| **Same tier** | HIGH-A, HIGH-B | No lost/duplicated messages; assert FIFO only if contract specifies a tie-breaker. | Unit |
| **Missing header** | No `priority` | Rejected/normalized per ingress policy; never escalates to HIGH automatically. | Unit + integration |
| **Wrong type** | `priority="9"`, null, or out of range | Validator rejects or decoder converts per rules. | Unit |
| **Late arrival** | LOW already dequeued, then HIGH arrives | Does not require preempting running work. | Unit + integration |
| **Across EIPs** | HIGH message through Transformer, Router, Filter, Splitter | Header preserved or recomputed per contract. | Spring integration |
| **Aggregator** | Child messages with priorities 1, 5, 9 | Output priority follows defined MAX/parent/deadline policy. | Unit + integration |
| **Fairness** | Continuous HIGH arrivals, LOW backlogged | LOW still dispatches within published budget. | Deterministic unit + load |
| **Retry** | HIGH fails three times | No infinite retries; identity/priority preserved across retries, proper error path. | Integration |
| **Concurrency** | Multiple producers/consumers | No loss/duplicates within promised scope; do not assert global completion order. | Integration + stress |
| **Broker** | Two messages with different priorities | Native JMS/AMQP property accurate; Kafka header decodes accurately without assuming reorder. | Broker integration |
| **Crash/rollback** | Failure before/after DB commit, before ACK | Safe duplicate handling or redelivery matching source mechanics. | Failure injection |

**One condition must always be explicit in test names/setup:** were messages already in the queue **before** polling, or did HIGH arrive after LOW was already picked up? Those are two different problems.

## 4. First Unit Test: Three Tiers HIGH > NORMAL > LOW

`PriorityChannel` is a `PollableChannel` with priority selection logic. For deterministic tests, **enqueue all messages before calling `receive`** on a single thread:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;

class PriorityChannelOrderingTest {

    @Test
    void dequeuesAllHigherPrioritiesBeforeLowerPriorities() {
        PriorityChannel channel = new PriorityChannel(20);

        channel.send(PriorityContract.message("L-1", WorkClass.LOW));
        channel.send(PriorityContract.message("H-1", WorkClass.HIGH));
        channel.send(PriorityContract.message("N-1", WorkClass.NORMAL));

        Message<?> first = channel.receive(0);
        Message<?> second = channel.receive(0);
        Message<?> third = channel.receive(0);

        assertNotNull(first);
        assertNotNull(second);
        assertNotNull(third);

        assertEquals(9, PriorityContract.requirePriority(first));
        assertEquals(5, PriorityContract.requirePriority(second));
        assertEquals(1, PriorityContract.requirePriority(third));

        assertNull(channel.receive(0));
    }
}
~~~

This is an **ordering unit test**, not a test of transactions, fairness, or SLAs. It verifies **dequeue order** in a single pre-populated channel.

### Check Payload and Event IDs Simultaneously

Checking only the priority sequence 9–5–1 does not prove zero message loss or duplication. You can also assert:

~~~java
Set<String> actualIds = List.of(first, second, third).stream()
        .map(message -> (String) message.getHeaders()
                .get(PriorityContract.EVENT_ID))
        .collect(Collectors.toSet());

assertEquals(Set.of("L-1", "H-1", "N-1"), actualIds);
~~~

If adding a fourth message, assert both **message count** and the **set of `eventId`s**. Use business IDs rather than `MessageHeaders.ID` to verify exactly-once semantics across retries and message reconstructions.

## 5. Unit Tests with Many Messages, Equal Priorities, and Tie-Breaking

### 5.1. When FIFO Within the Same Tier Is Not Required

A comparator-based priority queue may not guarantee FIFO among messages considered equal. Never write tests depending on HIGH-A before HIGH-B unless a secondary ordering key is configured.

~~~java
@Test
void messagesWithSamePriorityAreAllPresent() {
    PriorityChannel queue = new PriorityChannel(16);

    queue.send(PriorityContract.message("H-A", WorkClass.HIGH));
    queue.send(PriorityContract.message("H-B", WorkClass.HIGH));
    queue.send(PriorityContract.message("L-C", WorkClass.LOW));

    Message<?> first = queue.receive(0);
    Message<?> second = queue.receive(0);
    Message<?> third = queue.receive(0);

    assertEquals(9, PriorityContract.requirePriority(first));
    assertEquals(9, PriorityContract.requirePriority(second));
    assertEquals(1, PriorityContract.requirePriority(third));

    Set<Object> ids = Set.of(
            first.getHeaders().get(PriorityContract.EVENT_ID),
            second.getHeaders().get(PriorityContract.EVENT_ID));
    assertEquals(Set.of("H-A", "H-B"), ids);
}
~~~

### 5.2. When the Business Requires FIFO Within the Same Tier

Include a tie-breaker in the **contract**, such as an ascending `enqueueSequence` assigned at a deterministic enqueue boundary:

~~~java
Comparator<Message<?>> priorityThenSequence = (left, right) -> {
    int byPriority = Integer.compare(
            PriorityContract.requirePriority(right),
            PriorityContract.requirePriority(left));
    if (byPriority != 0) {
        return byPriority;
    }

    long leftSequence =
            ((Number) left.getHeaders().get("enqueueSequence")).longValue();
    long rightSequence =
            ((Number) right.getHeaders().get("enqueueSequence")).longValue();
    return Long.compare(leftSequence, rightSequence);
};

PriorityChannel queue =
        new PriorityChannel(32, priorityThenSequence);
~~~

Test:

~~~java
@Test
void customComparatorUsesSequenceWithinSamePriority() {
    PriorityChannel queue = new PriorityChannel(
            32, priorityThenSequence);

    queue.send(MessageBuilder.withPayload("H-2")
            .setHeader("priority", 9)
            .setHeader("enqueueSequence", 2L).build());
    queue.send(MessageBuilder.withPayload("N-1")
            .setHeader("priority", 5)
            .setHeader("enqueueSequence", 1L).build());
    queue.send(MessageBuilder.withPayload("H-1")
            .setHeader("priority", 9)
            .setHeader("enqueueSequence", 1L).build());

    assertEquals("H-1", queue.receive(0).getPayload());
    assertEquals("H-2", queue.receive(0).getPayload());
    assertEquals("N-1", queue.receive(0).getPayload());
}
~~~

Place the comparator and test in the same fixture/class or dedicated configuration bean; the snippets above illustrate pieces of one test. **Never assume global FIFO across multiple producers or multiple instances**: sequences must be allocated by an explicitly ordered mechanism. When using a persistent message store, verify whether that store supports comparators or corresponding ordering; an in-memory comparator does not automatically apply to a broker or database store.

### 5.3. Do Not Use a Dynamic Clock in the Default Comparator

A comparator reading `System.currentTimeMillis()` to boost priority by wait age generally **does not cause a heap to re-sort automatically over time**. Aging requires a scheduler that updates/promotes or re-evaluates messages at each selection; testing a standalone comparator does not prove real aging behavior.

## 6. Data Boundaries: Missing, Wrongly Typed, or Out-of-Range Priority

A good test does not wait for `PriorityChannel` to throw an exception to discover policy. **Validate at ingress** and test against your application's contract.

~~~java
record IncomingWork(String eventId, String type, Object requestedPriority) {}

final class PriorityPolicy {
    static int fromTrustedType(String type) {
        return switch (type) {
            case "FRAUD_ALERT", "RISK_CANCEL" -> 9;
            case "PAYMENT_CONFIRMED", "ORDER_UPDATED" -> 5;
            case "METRICS_REFRESH", "REPORT_REFRESH" -> 1;
            default -> throw new IllegalArgumentException(
                    "Unknown work type: " + type);
        };
    }

    static Message<WorkEvent> normalize(IncomingWork raw) {
        int priority = fromTrustedType(raw.type());
        return MessageBuilder.withPayload(
                    new WorkEvent(raw.eventId(), raw.type()))
                .setHeader(PriorityContract.PRIORITY, priority)
                .setHeader(PriorityContract.EVENT_ID, raw.eventId())
                .build();
    }
}
~~~

In this example, `requestedPriority` is untrusted: the backend **classifies independently** from validated business type. When authorized sources are allowed to suggest priority, enforce authorization before evaluating the requested value.

~~~java
@ParameterizedTest
@CsvSource({
        "FRAUD_ALERT, 9",
        "PAYMENT_CONFIRMED, 5",
        "METRICS_REFRESH, 1"
})
void serverPolicyAssignsCorrectPriority(String type, int expected) {
    Message<WorkEvent> output = PriorityPolicy.normalize(
            new IncomingWork("E-100", type, "FORGED_HIGH"));
    assertEquals(expected, PriorityContract.requirePriority(output));
}

@Test
void rejectsUnknownBusinessType() {
    assertThrows(IllegalArgumentException.class,
            () -> PriorityPolicy.normalize(
                    new IncomingWork("E-101", "UNRECOGNIZED", 9)));
}

@Test
void rejectsInvalidPriorityHeadersAtInternalBoundary() {
    Message<String> invalid = MessageBuilder.withPayload("WORK")
            .setHeader("priority", "9")
            .build();
    assertThrows(IllegalArgumentException.class,
            () -> PriorityContract.requirePriority(invalid));
}
~~~

### Concrete Boundary Matrix

| Input | Policy to test |
| --- | --- |
| `Integer(9)` | Accepted if HIGH is valid and authorized. |
| `Integer(0)` | Accepted or rejected per app range; never assume 0 equals LOW if contract says LOW=1. |
| `Integer(-1)` / `Integer(10)` | Rejected under example 0..9 range. |
| `String("9")` | Rejected at internal boundary, or decoded cleanly at adapter boundary. |
| `null` / missing header | Apply published default or route to error/quarantine. |
| `Long(9)` | Accept only if decoder defines explicit conversion rules; avoid silent coercion. |
| Client header self-assigning HIGH | Disallow escalation when caller lacks permission. |
| Retry of same business event | Retain `eventId` and priority policy source; never spawn an unintended new work item. |

**Never coerce unconditionally with `toString()`**, especially when source headers could hold non-serializable objects or incompatible types.

## 7. Testing Transformer: Priority Must Survive Payload Changes

In Spring Integration, a Transformer can accept a payload or `Message` and emit a new output. The framework has endpoint header-inheritance rules; custom transformers/adapters may overwrite or filter headers. The reliable test is **inspecting the flow's output**, not merely verifying the caller set a header.

Example of intentional handling:

~~~java
record RawWork(String eventId, String rawType) {}
record NormalizedWork(String eventId, String type) {}

final class NormalizingTransformer {
    Message<NormalizedWork> normalize(Message<RawWork> input) {
        RawWork raw = input.getPayload();
        int priority = PriorityContract.requirePriority(input);

        return MessageBuilder.withPayload(
                    new NormalizedWork(
                            raw.eventId(),
                            raw.rawType().trim().toUpperCase(Locale.ROOT)))
                .copyHeaders(input.getHeaders())
                .setHeader(PriorityContract.PRIORITY, priority)
                .build();
    }
}
~~~

Unit test:

~~~java
@Test
void transformerPreservesPriorityAndBusinessEventId() {
    Message<RawWork> input = MessageBuilder
            .withPayload(new RawWork("E-17", "fraud_alert"))
            .setHeader("priority", 9)
            .setHeader(PriorityContract.EVENT_ID, "E-17")
            .build();

    Message<NormalizedWork> result =
            new NormalizingTransformer().normalize(input);

    assertEquals(9, PriorityContract.requirePriority(result));
    assertEquals("E-17",
            result.getHeaders().get(PriorityContract.EVENT_ID));
    assertEquals("FRAUD_ALERT", result.getPayload().type());
}
~~~

When deploying a Transformer endpoint, also write a **channel-level integration test** to verify the adapter's real output. For instance, constructing a `MessageBuilder.withPayload(...)` without copying headers can drop metadata in custom code; on some endpoints, Spring Integration also merges/copies reply headers. **Do not claim every Transformer drops headers by default.**

### Testing Across Router and Filter Branches

With two branches:

~~~mermaid
flowchart LR
    I["input priority 9/5/1"] --> T["Transformer normalize"]
    T --> R{"Router by type"}
    R --> H["HIGH route"]
    R --> N["NORMAL/LOW route"]
    H --> Q["PriorityChannel"]
    N --> Q
    Q --> C["Consumer"]
~~~

Assertions should verify:

- Both HIGH and NORMAL/LOW branches retain `eventId` and normalized priority.
- Messages dropped by Filter per business rules **do not appear** in the queue; the `filtered` metric stays distinct from `priority_missing`.
- If a discard channel exists, messages sent there retain enough metadata for investigation.
- Router does not escalate priority merely because a branch is named `urgent`; any escalation must be an explicit tested policy.
- Do not assume a `DirectChannel` on the HIGH branch reorders two closely spaced sends.

## 8. Testing Splitter and Aggregator: Child Priority and Group Output

Splitter produces multiple messages from one parent message. An `Aggregator` collects results by `correlationId`. These two EIPs raise the question of **how new priorities are computed**.

### Example Policy

- Child messages **inherit** parent priority unless an override rule applies.
- If a specific item is critical, item priority can be `max(parentPriority, itemPriority)` per policy.
- Aggregator output picks the **highest priority** among group members; alternatively, it keeps parent priority when domain semantics call for it.

Example test for an Aggregator business helper:

~~~java
static int aggregatePriority(Collection<Message<?>> messages) {
    if (messages.isEmpty()) {
        throw new IllegalArgumentException("Cannot aggregate empty group");
    }
    return messages.stream()
            .mapToInt(PriorityContract::requirePriority)
            .max()
            .orElseThrow();
}

@Test
void aggregatedPriorityUsesMaximumOfChildren() {
    List<Message<?>> parts = List.of(
            PriorityContract.message("C-1", WorkClass.NORMAL),
            PriorityContract.message("C-2", WorkClass.HIGH),
            PriorityContract.message("C-3", WorkClass.LOW));

    assertEquals(9, aggregatePriority(parts));
}
~~~

In practice, when applying this to a real `@Aggregator` or Java DSL flow, also test:

| Scenario | Criteria |
| --- | --- |
| Three child messages 1, 5, 9 all arrive | Output priority follows MAX = 9, payload assembled accurately. |
| Messages arrive in reversed order | Output priority does not depend on first/last arrival. |
| One child message is redelivered | Does not inflate business item count or skew results arbitrarily. |
| Group timeout / partial release | Output applies explicit policy over **arrived messages** or stored parent metadata. |
| Aggregator persists state across restart | Priority/correlation and needed fields survive serialization. |
| Late message arrives after release | Explicit discard/reopen/reconcile policy prevents bogus events. |

`correlationId` and `sequenceNumber` support aggregation; they do not replace the business event ID. When testing Splitter, verify both priority and the correlation headers actually added by the endpoint.

## 9. Testing Gateway and Request–Reply

A synchronous Gateway submits a message into a flow and awaits a response. Test **request priority** at ingress, and decide whether the reply needs priority preservation or its own policy.

~~~java
@MessagingGateway(defaultRequestChannel = "priorityIngress")
interface PriorityGateway {
    void submit(Message<WorkEvent> work);
}
~~~

Sending:

~~~java
gateway.submit(PriorityContract.message("E-900", WorkClass.HIGH));
~~~

Integration tests should verify:

1. The actual message arriving at `priorityIngress` has `priority=9` and the expected event ID.
2. If the flow continues into `PriorityChannel`, that value remains intact prior to enqueuing.
3. If the Gateway accepts only a payload without headers, an internal **Header Enricher/policy** assigns priority rather than expecting it to appear automatically.
4. For request–reply Gateways, test request timeouts and reply metadata **independently**; a reply arriving after request timeout must not count as success for the timed-out request.
5. If handlers return a new `Message`, reply/error-channel headers must not be stripped unintentionally.

Priority 9 on a request **does not** prove the response will finish fast if handlers block on locks, downstreams, or brokers.

## 10. Unit Testing Fairness: LOW Progresses While HIGH Stays Backlogged

Strict priority and fairness are **two different policies**. `PriorityChannel` can follow its comparator faithfully while still starving LOW under continuous HIGH load. When the business requires a **minimum service share** for LOW, test alternative mechanisms such as weighted round-robin (WRR), aging, or reserved capacity.

### Sample 4:2:1 Scheduler

The example below uses three separate FIFO `PollableChannel`s with a 4 HIGH, 2 NORMAL, 1 LOW schedule. This is an illustrative message selector **for testing**, without durability, transactions, or ACKs.

~~~java
final class WeightedSelector {
    private static final int[] SLOTS = {0, 0, 0, 0, 1, 1, 2};

    private final PollableChannel[] queues;
    private int nextSlot;

    WeightedSelector(
            PollableChannel high,
            PollableChannel normal,
            PollableChannel low) {
        this.queues = new PollableChannel[]{high, normal, low};
    }

    synchronized Message<?> next() {
        for (int offset = 0; offset < SLOTS.length; offset++) {
            int index = (nextSlot + offset) % SLOTS.length;
            Message<?> value = queues[SLOTS[index]].receive(0);
            if (value != null) {
                nextSlot = (index + 1) % SLOTS.length;
                return value;
            }
        }
        nextSlot = (nextSlot + 1) % SLOTS.length;
        return null;
    }
}
~~~

To test 4:2:1, **enqueue sufficient backlog in every class before calling `next()`**:

~~~java
@Test
void lowMakesProgressEvenWithContinuousHighBacklog() {
    QueueChannel high = new QueueChannel(100);
    QueueChannel normal = new QueueChannel(100);
    QueueChannel low = new QueueChannel(100);

    for (int i = 0; i < 30; i++) {
        high.send(PriorityContract.message(
                "H-" + i, WorkClass.HIGH));
    }
    for (int i = 0; i < 20; i++) {
        normal.send(PriorityContract.message(
                "N-" + i, WorkClass.NORMAL));
    }
    for (int i = 0; i < 10; i++) {
        low.send(PriorityContract.message(
                "L-" + i, WorkClass.LOW));
    }

    WeightedSelector selector = new WeightedSelector(high, normal, low);
    List<Integer> actual = new ArrayList<>();

    for (int i = 0; i < 14; i++) {
        Message<?> message = selector.next();
        assertNotNull(message);
        actual.add(PriorityContract.requirePriority(message));
    }

    assertEquals(8, Collections.frequency(actual, 9));
    assertEquals(4, Collections.frequency(actual, 5));
    assertEquals(2, Collections.frequency(actual, 1));
    assertTrue(actual.subList(0, 7).contains(1));
    assertTrue(actual.subList(7, 14).contains(1));
}
~~~

This is a **turn-quota test**, not proof that a LOW message finishes within a fixed number of seconds. It assumes `next()` keeps getting called and downstream processing finishes in finite time.

### Testing with Empty Queues

~~~java
@Test
void idleHighAndNormalDoNotBlockLow() {
    QueueChannel high = new QueueChannel(10);
    QueueChannel normal = new QueueChannel(10);
    QueueChannel low = new QueueChannel(10);

    low.send(PriorityContract.message("L-1", WorkClass.LOW));
    low.send(PriorityContract.message("L-2", WorkClass.LOW));

    WeightedSelector selector = new WeightedSelector(high, normal, low);

    assertEquals("L-1", selector.next()
            .getHeaders().get(PriorityContract.EVENT_ID));
    assertEquals("L-2", selector.next()
            .getHeaders().get(PriorityContract.EVENT_ID));
    assertNull(selector.next());
}
~~~

This verifies the scheduler is **work-conserving**: it does not waste turns when HIGH/NORMAL have no work.

**Limit to keep separate:** three in-memory `QueueChannel`s do not support durable redelivery tied to JDBC transactions. For production, replace with an appropriate queue/store/broker and design ACK/rollback together.

## 11. Aging and Deadlines: Test with a Fake Clock, Not Long Sleeps

If LOW must gain priority after waiting too long, you can define:

~~~text
effectivePriority = basePriority + floor(waitSeconds / agingStepSeconds)
~~~

A test relying on `Thread.sleep(60_000)` is slow and flaky. Separate the priority calculation from the time source:

~~~java
record PendingWork(
        String id,
        int basePriority,
        Instant originalEnqueuedAt) {}

static int effectivePriority(PendingWork work, Instant now) {
    long age = Math.max(0L,
            Duration.between(work.originalEnqueuedAt(), now).toSeconds());
    long bonus = age / 10L; // Add 1 point every 10 seconds.
    return (int) Math.min(100L, work.basePriority() + bonus);
}

static PendingWork selectAt(
        List<PendingWork> waiting, Instant now) {
    return waiting.stream()
            .min(Comparator
                    .<PendingWork>comparingInt(
                            w -> -effectivePriority(w, now))
                    .thenComparing(PendingWork::originalEnqueuedAt))
            .orElseThrow();
}
~~~

Test:

~~~java
@Test
void oldLowCanOvertakeNewHighByAgingPolicy() {
    Instant start = Instant.parse("2026-01-01T00:00:00Z");
    PendingWork oldLow = new PendingWork("LOW-1", 1, start);
    PendingWork newHigh = new PendingWork(
            "HIGH-1", 9, start.plusSeconds(90));

    PendingWork selected = selectAt(
            List.of(oldLow, newHigh), start.plusSeconds(100));

    assertEquals("LOW-1", selected.id());
}
~~~

At 100 seconds, LOW has effective priority 11 while HIGH waiting 10 seconds has effective priority 10. **This tests the selection algorithm at instant `now`**, not an auto-reordering heap-backed `PriorityChannel`. A heap does not re-sort every second merely because a clock-dependent comparator exists. When using a persistent priority queue or scheduled promotion, test the **actual promote/reinsert/claim operation**.

### Deadlines and SLOs

If you define “LOW waits at most 60 seconds”, tests must verify *processing start time* or *business commit time* per your SLO definition, not just priority score after 60 seconds. Whenever total arrival rate exceeds capacity persistently, **no scheduler can meet every deadline** without scaling, admission control, or degradation policies.

## 12. Testing Multiple Producers/Consumers and Concurrency

A priority queue governs message selection order at one point, whereas **completion order** depends on workers/threads, processing durations, and contended resources.

Example:

~~~text
Worker A: dequeues HIGH-1 -> processes 2 seconds
Worker B: dequeues NORMAL-1 -> processes 20 ms

Dequeue order: HIGH-1 then NORMAL-1
Completion order: NORMAL-1 then HIGH-1
~~~

Therefore, concurrency tests **should not assert that all HIGH complete before NORMAL** unless the architecture explicitly enforces that processing/commit order.

### Better Invariants to Assert

- Each business event ID is recorded according to the idempotency policy (with at-least-once sources, duplicates may arrive yet produce **no double effect**).
- No loss of durably stored messages properly ACKed under contract.
- Completed + pending + dead-lettered + in-flight counts account for all inputs under a deterministic state model.
- HIGH meets p95/p99 queue-wait SLO under tested load conditions.
- LOW makes progress and hits its quota while queues stay continuously populated.
- No handler hangs indefinitely on locks, missing timeouts, or poison messages.

### Coordinating Concurrency Tests with Latches Instead of Arbitrary Sleeps

~~~java
CountDownLatch highEntered = new CountDownLatch(1);
CountDownLatch allowHighToFinish = new CountDownLatch(1);

// Inside fake HIGH handler:
highEntered.countDown();
if (!allowHighToFinish.await(2, TimeUnit.SECONDS)) {
    throw new AssertionError("Timeout waiting for test signal");
}

// Inside test:
assertTrue(highEntered.await(2, TimeUnit.SECONDS));
// Now inspect whether other messages are dequeued/processed
// according to the system's concurrency policy.
allowHighToFinish.countDown();
~~~

When using latches, always set timeouts so CI never hangs forever. Use `try/finally` in tests to release latches even if assertions fail. The snippet illustrates execution-order coordination, not an assumption about Spring Integration's default worker pool settings.

## 13. Retry, Redelivery, Error Channel, and DLQ Across Priorities

A repeatedly failing HIGH message can trigger redeliveries or retries that crowd out NORMAL/LOW. Priority testing must therefore cover **failure paths**:

~~~mermaid
flowchart TD
    A["Receive HIGH/NORMAL/LOW message"] --> B["Validate"]
    B --> C{"Valid message?"}
    C -->|"No"| D["Quarantine / DLQ"]
    C -->|"Yes"| E["Business handler"]
    E --> F{"Success?"}
    F -->|"Yes"| G["Commit/ACK per source"]
    F -->|"Transient error"| H["Bounded retry + backoff"]
    H --> I{"Retry budget left?"}
    I -->|"Yes"| E
    I -->|"No"| D
~~~

### Failure-Path Test Matrix

| Scenario | What to observe |
| --- | --- |
| HIGH fails permanently due to bad schema | No infinite retries; DLQ preserves business event ID, original priority, and reason. |
| HIGH fails transiently twice then succeeds | Attempt count accurate, no duplicate side effects, unchanged event ID. |
| NORMAL rolls back and redelivers | Priority restored/validated properly without shifting unexpectedly to LOW/HIGH. |
| `ErrorMessage` sent to `errorChannel` | Original failed message retrieved when needed; error payload is typically an exception, not the business payload. |
| HIGH retry loop in a strict priority queue | LOW still makes progress when fairness/retry budget is required. |
| Handler catches exception and returns | Source/poller may treat as success; test must verify real ACK/rollback, not just error logs. |
| DB commit succeeds before broker ACK | Redelivery may occur; idempotent consumer produces no extra side effects. |
| Source ACKs before business commit then crashes | Risk of data loss; tests must surface or explicitly acknowledge the contract. |

### Preserving Metadata Across Retries

~~~java
static Message<WorkEvent> retryCopy(
        Message<WorkEvent> failed, int nextAttempt) {
    int priority = PriorityContract.requirePriority(failed);
    String eventId = (String) failed.getHeaders()
            .get(PriorityContract.EVENT_ID);

    return MessageBuilder.withPayload(failed.getPayload())
            .setHeader(PriorityContract.PRIORITY, priority)
            .setHeader(PriorityContract.EVENT_ID, eventId)
            .setHeader("attempt", nextAttempt)
            .build();
}
~~~

Test:

~~~java
@Test
void retryKeepsBusinessEventIdAndPriority() {
    Message<WorkEvent> original =
            PriorityContract.message("E-17", WorkClass.HIGH);

    Message<WorkEvent> retried = retryCopy(original, 2);
    assertEquals(9, PriorityContract.requirePriority(retried));
    assertEquals("E-17",
            retried.getHeaders().get(PriorityContract.EVENT_ID));
    assertEquals(2, retried.getHeaders().get("attempt"));
}
~~~

This snippet copies only the two metadata fields needed for the invariant under test. In real flows, `correlationId`, initial enqueue time, security headers, and adapter properties also require a **versioned allowlist**. Never blindly copy all internal headers across brokers or HTTP.

## 14. JMS, RabbitMQ, and Kafka: Testing What the Transport Actually Supports

### JMS

JMS defines `JMSPriority` commonly in `0..9`; it is a **JMS message property**. A Spring `priority` header alone does not prove the real producer sets `JMSPriority` properly. Test:

1. Send HIGH and LOW priority messages via the real outbound adapter.
2. Inspect `JMSPriority` on the JMS message at the broker/consumer side.
3. Pass inbound messages through the Spring Integration adapter and verify mapping back to internal priority.
4. When testing ordering, enqueue **both before starting the consumer**; distinguish broker ordering from consumer prefetch, concurrency, and session transactions.

### RabbitMQ / AMQP

RabbitMQ uses `BasicProperties.priority`, and priority ordering requires a queue/type configured to support priorities (such as a classic priority queue with suitable `x-max-priority`).

Test:

- Outbound mapper sets the actual **priority property**, not merely an application string header named `priority`.
- Queue is declared with the right priority configuration.
- HIGH/LOW messages sit in the queue **before** the consumer starts pulling.
- Prefetch is tuned so the broker retains selection authority across pending messages.
- On retry/NACK/requeue, priority metadata and event IDs follow contract.

If a consumer already prefetched LOW before HIGH arrived, LOW finishing ahead of HIGH **does not prove priority mapping is broken**.

### Kafka

Kafka stores records by partition/offset. A custom `priority` header is merely metadata; **Kafka does not reorder records inside a partition by that number**.

Tests should separate:

1. **Header propagation:** producer serializes priority to bytes per wire contract; consumer decodes back to `Integer` per policy.
2. **Partition ordering:** verify offset/key ordering when required by business logic.
3. **Application scheduling:** if HIGH must run first, test a dedicated scheduler/queue/consumer pool; never write tests expecting Kafka to prioritize records based on a HIGH header.
4. **Offsets/transactions:** DB commits and Kafka offset commits have a failure window; test redelivery and consumer idempotency.

| Test result | Valid conclusion | Invalid conclusion |
| --- | --- | --- |
| `JMSPriority=9` on JMS message | Mapper/JMS producer assigned priority properly. | Consumers definitely finish before every lower priority. |
| AMQP priority property set and queue configured | Broker can prioritize pending deliveries. | Currently running work can be preempted immediately. |
| Kafka header `priority=9` survives encode/decode | Metadata crosses Kafka intact. | Kafka automatically reorders offsets by priority. |
| `PriorityChannel` dequeues 9 before 1 | Local priority selection works for that queued state. | End-to-end fairness, durability, or exactly-once delivery. |

## 15. Testing Transactions and Idempotency in Priority Handlers

Priority does not replace transactions. For consumers writing to a DB, test duplicate delivery handling using a stable business event ID.

Illustrative PostgreSQL schema:

~~~sql
CREATE TABLE work_effects (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_priority INTEGER NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Handler:

~~~java
@Service
class IdempotentWorkHandler {
    private final JdbcTemplate jdbc;

    IdempotentWorkHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void process(Message<WorkEvent> message) {
        int priority = PriorityContract.requirePriority(message);
        String eventId = (String) message.getHeaders()
                .get(PriorityContract.EVENT_ID);

        int inserted = jdbc.update("""
                INSERT INTO work_effects(event_id, processed_priority)
                VALUES (?, ?)
                ON CONFLICT (event_id) DO NOTHING
                """, eventId, priority);

        if (inserted == 0) {
            return; // Same event already committed from a prior delivery.
        }

        // Execute additional JDBC side effects here,
        // inside the SAME transaction as the deduplication marker.
    }
}
~~~

Integration test:

~~~java
@Test
void repeatedHighDeliveryProducesOnlyOneBusinessRow() {
    Message<WorkEvent> high =
            PriorityContract.message("E-200", WorkClass.HIGH);

    handler.process(high);
    handler.process(high); // Simulate redelivery.

    Integer count = jdbc.queryForObject("""
            SELECT COUNT(*) FROM work_effects WHERE event_id = ?
            """, Integer.class, "E-200");

    assertEquals(1, count);
}
~~~

This only proves a **database** invariant when run with real Spring proxies/transaction managers and an appropriate database. It does not prove broker redelivery or durable message-store ACKs. For HTTP/email actions, DB rollbacks do not undo external side effects; consider transactional outbox/inbox and idempotency at integration points.

## 16. Load/Stress Testing: Mixed Priorities Under Varying Ratios

Small ordering unit tests miss behaviors that surface only under load: deep backlogs, retry storms, prefetching, downstream locks, and tasks with skewed durations.

### Recommended Load Scenarios

| Scenario | Input distribution | Goal |
| --- | --- | --- |
| Balanced | HIGH:NORMAL:LOW = 1:1:1 | Baseline ordering and progress; no class abnormally starved. |
| HIGH-dominated | 80:15:5 | NORMAL/LOW make progress per fairness policy; watch oldest age. |
| Heavy LOW backlog | 10:20:70 | HIGH retains low latency; LOW is not dropped outside policy. |
| Burst traffic | 100% HIGH for 20s then return to normal | Recovery time and backlog drain per class. |
| Retry storm | 10% HIGH fail transiently | Retry budget, DLQ, and progress of healthy messages. |
| Heavy payloads | HIGH takes 10x longer than LOW | Does message-count WRR still satisfy SLOs? |
| Multi-tenant | One tenant emits 90% HIGH | Other tenants still receive minimum quota/turns. |
| Restart | Stop/restart consumers mid-backlog | Durability, redelivery, and business idempotency. |

### Metrics to Measure

- `enqueued_total{class}`, `dequeued_total{class}`, `completed_total{class}`.
- `queue_depth{class}` and `oldest_pending_age_seconds{class}`.
- `queue_wait_seconds{class}` p50/p95/p99.
- `end_to_end_latency_seconds{class}` per SLO definition.
- `retry_total{class,reason}`, `dead_letter_total{class}`.
- `duplicate_suppressed_total{class}`.
- `rejected_total{class}`, `worker_active{class}`, and connection-pool saturation.

**Never use dequeued counts as a proxy for business completion.** Completion can happen later, fail, or roll back; measure those checkpoints separately.

### An Important Mathematical Warning

If HIGH consumes 100% of a strict priority scheduler's capacity continuously, LOW can starve. If you use 4:2:1 WRR while LOW's arrival rate persistently exceeds **one-seventh of service capacity**, LOW's backlog will still grow without bound even though LOW keeps making progress. Turn fairness and **bounded backlog** are two different properties; load tests must check both.

## 17. Debugging Test Failures: Why Are Priority Tests Often Flaky?

| Anti-pattern | Why it is flaky/wrong | Replacement |
| --- | --- | --- |
| Sending LOW then HIGH with an active consumer and asserting HIGH always arrives first. | LOW can be dequeued before HIGH is sent. | Gate the consumer; enqueue everything before polling. |
| Asserting HIGH completes before LOW with multiple workers. | Dequeue order and completion order differ. | Assert invariants/correlation and measure latency separately. |
| Asserting FIFO for two equal-priority messages without a tie-breaker. | Comparator treats them as equal. | Assert full event ID sets or configure a sequence comparator. |
| Testing aging with multi-minute `Thread.sleep`. | Slow tests dependent on OS/CI scheduling. | Inject `Clock` or pass `Instant` to selection logic. |
| Using in-memory `PriorityChannel` to claim crash/restart safety. | RAM queues are not durable. | Test a real broker/persistent store plus ACK/transactions. |
| Mocking outbound adapters without checking broker properties. | Wire mapping remains unverified. | Broker integration tests checking native JMS/AMQP properties. |
| Assuming Kafka reorders by priority header. | Kafka preserves offset/partition ordering. | Test record headers separately from application schedulers. |
| Using fixed delays as “completion” test conditions. | CI jitter and variable load break timing. | Latches, bounded awaits, condition-based assertions. |
| Sharing the same queue/test data across parallel tests. | Test data collides, causing non-deterministic order. | Isolate queues/IDs/store groups per test. |
| Asserting only retry attempt counts while ignoring business effects. | Duplicate commits can happen even when attempt count matches. | Unique event IDs and final DB state assertions. |

### Test Organization Layers

**Layer 1 — Unit:** test comparators, policies, schedulers, and `aggregatePriority`; pure JVM, no Spring context needed.

**Layer 2 — Spring Integration tests:** test Header Enricher/Transformer, routes, Gateways, channel dispatch, and poller boundaries using wired beans and channels. Avoid active background pollers when testing deterministic queue order.

**Layer 3 — Broker/store tests:** run against real brokers or persistent stores (e.g., Testcontainers if used in the project). Verify wire mapping, ACKs, redelivery, restarts, and transactions.

**Layer 4 — Load/failure injection:** measure latency, fairness, retries, chaos/crashes, and concurrency boundaries under controlled conditions.

Do not run every slow broker suite on every small edit if CI needs fast feedback; group tests by cost tier while ensuring broker/failure tiers run before release.

## 18. Debugging When Multi-Level Priority Misbehaves

If HIGH waits behind LOW, trace **along the event ID's path**:

~~~text
1. Did the producer assign business priority per policy?
2. Did the ingress header have the right name, Integer type, and value?
3. Did any Transformer construct a new Message or overwrite headers?
4. Did the Router select the right priority-aware branch?
5. Did Splitter/Aggregator compute output priority explicitly?
6. Is the queue actually a PriorityChannel rather than a FIFO QueueChannel?
7. Does the comparator have the right direction and a tie-breaker?
8. Was HIGH already in the queue before LOW was dequeued?
9. Was a worker already holding LOW when HIGH arrived?
10. Were JMS/AMQP properties mapped properly and does the queue support them?
11. Does Kafka only carry a priority header or is there a separate scheduler?
12. Is there a retry storm, starvation, backpressure, prefetch, or DB lock?
13. Are metrics showing dequeue order or completion order?
14. Did original/effective priority change due to aging or tenant quotas?
~~~

Tracking `priority_assigned`, `priority_enqueued`, `priority_dequeued`, and `priority_processed` separately pinpoints where metadata was dropped and prevents blaming the channel when the cause is a worker or downstream system.

## 19. Exercises and Interview Questions

### Exercise 1 — Expanding from Two Tiers to Three

Extend `PriorityChannelOrderingTest` with at least three messages per tier, enqueue in random order, and assert **non-increasing dequeued priorities** (HIGH=9, NORMAL=5, LOW=1) while preserving the full event ID set. Do not assert order among equal priorities without a tie-breaker.

### Exercise 2 — Comparator for Equal Priority

Attach an `enqueueSequence` header to every message. Write a descending-priority, ascending-sequence comparator. Test equal-priority HIGH messages sent in reverse sequence order, then explain why allocating sequences across multiple instances is a distributed systems problem.

### Exercise 3 — Pipeline Across EIPs

Build Gateway → Transformer → Router → Filter → PriorityChannel → Service Activator. Give HIGH/NORMAL/LOW distinct event IDs. Test inputs, per-endpoint outputs, and final data; intentionally create a header-dropping Transformer so tests catch the regression.

### Exercise 4 — Splitter and Aggregator

Split an order into items with priorities 9, 5, and 1. Use a MAX aggregator policy. Test three arrival orders, duplicates, and timeout releases; explain what happens when the HIGH item arrives late.

### Exercise 5 — Preventing Starvation

Compare strict `PriorityChannel` with a 4:2:1 WRR scheduler under continuous HIGH arrivals. Prove LOW makes zero progress in a strict-priority poll streak yet gets at least one turn per WRR cycle while LOW remains backlogged.

### Exercise 6 — Aging Without Wall-Clock Sleeps

Write a test with a fake `Instant` for LOW waiting 100s and HIGH waiting 10s. Use an effective-priority function with a 10s step, then integrate it into a real promotion job; verify messages are properly **requeued/claimed** rather than merely computing a number.

### Exercise 7 — Retry and DLQ

Have HIGH fail three times before succeeding, NORMAL succeed, and LOW fail permanently. Measure attempt counts, event IDs, latency, and DLQ state. Ensure retries never escalate priority infinitely.

### Exercise 8 — From Local to Broker

Port the example to JMS or RabbitMQ. Read the **actual native priority property** on messages and test prefetch and retries. If using Kafka, prove headers propagate intact while partition offset order remains unchanged.

### Exercise 9 — Crash Idempotency Test

Have a consumer pick up HIGH, commit to DB, then crash before ACK. After redelivery with the same event ID, verify the business effect occurs exactly once; state explicitly which data belongs to which transaction.

### Self-Assessment Questions

**1. Why can a “send LOW then HIGH” test fail even when `PriorityChannel` works properly?** Because the consumer may have dequeued LOW before HIGH was enqueued. Control poll timing.

**2. Should you test default FIFO between two `priority=9` messages?** No, unless configuration/contract explicitly specifies tie-breaking.

**3. What does 4:2:1 WRR prove?** Dispatch-turn allocation across three queues while all remain backlogged and the scheduler advances; it does not prove wall-clock deadlines in seconds.

**4. Why use a fake clock when testing aging?** To test time milestones rapidly, deterministically, and independently of CI timing jitter.

**5. Will a Kafka record with priority header 9 be read before an earlier-offset record?** No. Kafka does not reorder within a partition by custom priority headers.

**6. Why test DB state in addition to dequeue order?** A message may be received and reprocessed after rollback/ACK failure; only committed state proves correct business side effects.

## 20. Checklist Before Concluding Testing Passes

- [ ] Contract published for HIGH/NORMAL/LOW, value range, header type, and trusted source.
- [ ] Queue ordering tests have **all messages ready before polling** and a single consumer when verifying order.
- [ ] Tested all three tiers, multiple messages, equal tiers, missing/wrongly typed headers, and out-of-range values.
- [ ] No FIFO assertions on equal priorities without a tie-breaker comparator.
- [ ] Verified zero message loss/duplication by `businessEventId`, not just priority sequence.
- [ ] Tested Transformer/Router/Filter, Gateway, and Splitter/Aggregator for priority and correlation headers.
- [ ] Separated `PriorityChannel` ordering from `DirectChannel` and `ExecutorChannel` execution.
- [ ] When fairness is required, tested continuous HIGH load and NORMAL/LOW quotas.
- [ ] When using aging, tested with a fake clock and verified the scheduler/store actually re-evaluates order.
- [ ] Tested empty queues, full queues, backpressure, and slow workers.
- [ ] Verified bounded retries, backoff, DLQ, and priority/event ID preservation across error paths.
- [ ] Tested concurrency with appropriate invariants; never conflated dequeue order with completion order.
- [ ] Ran real broker tests for JMS/AMQP properties or Kafka header encode/decode.
- [ ] For critical business logic, ran integration tests for transactions/ACK/redelivery and idempotency.
- [ ] CI uses isolated queues/IDs, latches/finite timeouts, and no arbitrary sleeps.
- [ ] Monitored oldest queue age, p95/p99 wait, class progress, retries, and deadline misses under load.
- [ ] Distinguished turn fairness, bounded backlog, and latency SLAs; planned capacity scaling when total load exceeds capacity.

**Key takeaway:** **Proper priority testing must verify *metadata values*, *dequeue selection order*, *progress across priority tiers*, and *business outcomes on failure*.** `PriorityChannel` solves local ordering of waiting messages; Spring Integration systems with Routers, Transformers, Splitters, Aggregators, Gateways, and brokers additionally require header contracts, fairness, transactions, retries, and end-to-end observability. A passing single-queue test cannot replace full-flow verification.

### Further Reading

- Spring Integration Reference: Message Channel Implementations, Message Channels, and PriorityChannel.
- Spring Integration Reference: Transformer, Router, Filter, Splitter, Aggregator, and Gateway.
- Spring Integration Reference: Error Handling, Transaction Support, and Polling Consumer.
- Documentation for your broker: JMS message priority, RabbitMQ Priority Queues, or Kafka partition/offset/header semantics.

*Java snippets illustrate test components and must be placed into appropriate fixtures/classes. Before using in a project, verify APIs against your exact Spring Integration and broker versions; these do not replace dedicated Content QA or environment integration testing.*
