# Buffering Early-Arriving Messages

## 1. Problem: Message #3 Arrives Before Message #1

A shipping system processes events for the same shipment in business sequence:

~~~text
1. SHIPMENT_CREATED
2. ITEMS_PACKED
3. HANDOVER_CONFIRMED
4. DELIVERED
~~~

In an integration environment, events may traverse executors, queues, HTTP gateways, or message brokers. If workers process in parallel or paths have different latencies, **arrival order at the consumer can differ from event creation order**:

~~~text
Business order:  1  2  3  4
Arrival order:   3  1  4  2
~~~

If a handler runs `HANDOVER_CONFIRMED` before `SHIPMENT_CREATED`, it may fail to find the shipment record or update state incorrectly. **Resequencer** in Enterprise Integration Patterns (EIP) handles this situation by **holding early-arriving messages in a buffer**, waiting for missing parts, and then emitting messages in sequence order.

In this lesson, "early-arriving" does not mean an earlier timestamp or a faster clock: it means **the message's `sequenceNumber` is higher than the position the group is currently waiting for**.

~~~mermaid
flowchart LR
    I["Arrival: #3, #1, #4, #2"] --> R[Resequencer]
    R --> B["Buffer by correlation key"]
    B --> C{Release condition met?}
    C -->|No| W["Wait for #2 / check deadline"]
    C -->|Yes| O["Output: #1 → #2 → #3 → #4"]
    O --> H[Ordered Handler]
~~~

**Key point:** Resequencer does not turn a distributed channel into "exactly-once and always ordered" under every circumstance. It requires **group identification**, **sequence numbers**, **release conditions**, a **message store**, **timeout/duplicate rules**, and appropriate guarantees when emitting downstream.

This lesson belongs to the **Resequencer** chapter of the `SPRING_INTEGRATION_PATTERN` module. The module focuses on implementing Enterprise Integration Patterns with Spring Integration, building loosely coupled and extensible message flows while coordinating Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channels, correlation, testing, and monitoring across branches.

### Objectives

After this lesson, you will be able to:

1. Explain why messages arrive out of order and why messages "ahead" of the expected position must be buffered.
2. Distinguish **Resequencer**, **Aggregator**, **Splitter**, **Filter**, FIFO queues, and **Message Store**.
3. Design `correlationId`, `sequenceNumber`, `sequenceSize`, and business identifiers per group.
4. Compare **waiting for the full sequence** with **releasing eligible contiguous segments**.
5. Configure a Spring Integration flow using Resequencer and test message emission order.
6. Handle missing sequences, duplicates, late arrivals, timeouts, group expiration, memory pressure, and restarts.
7. Observe inputs, buffers, outputs, and errors to distinguish "waiting" from "successfully processed."

## 2. How Does Resequencer Work?

### 2.1. One Group, Multiple Positions in Sequence

Each message must belong to **one logical group**, such as events for shipment `SHIP-42` in a particular dispatch run `RUN-7`:

~~~text
Group: SHIP-42 / RUN-7
sequenceSize: 4

sequenceNumber=1 -> SHIPMENT_CREATED
sequenceNumber=2 -> ITEMS_PACKED
sequenceNumber=3 -> HANDOVER_CONFIRMED
sequenceNumber=4 -> DELIVERED
~~~

If message `#3` arrives first, Resequencer cannot emit it as the first message when the contract requires order starting at `#1`. It must **hold #3** and keep waiting.

### 2.2. Buffer Progression Under Contiguous-Segment Release Policy

An intuitive model maintains `nextExpected=1`, emitting only contiguous positions starting from it:

| Arrival | Incoming | Buffer After Receive | `nextExpected` Before Release | Eligible to Emit |
|---|---|---|---|---|
| 1 | `#3` | `{3}` | 1 | No `#1` yet → do not emit |
| 2 | `#1` | `{1,3}` | 1 | Emit `#1` if partial release is allowed |
| 3 | `#4` | `{3,4}` | 2 | Still missing `#2` → wait |
| 4 | `#2` | `{2,3,4}` | 2 | Emit `#2, #3, #4` contiguously |

The downstream result under this policy is still:

~~~text
#1 -> #2 -> #3 -> #4
~~~

However, **two release styles must be distinguished**:

- **Full-sequence release:** holds the entire group until complete, then emits messages in order. For arrival `3,1,4,2`, there is no output on the first three arrivals.
- **Partial-sequence release:** allowed to emit an available **contiguous prefix**, e.g., emitting `#1` after the second arrival, then holding `#3, #4` until `#2` arrives.

In Spring Integration, partial release behavior must be configured and verified for your exact Resequencer version; **do not treat it as an implicit property of every Aggregator/Resequencer**. The `3,2,1` scenario in the integration test applies to both styles: nothing can emit before `#1` arrives, and final order must be `1,2,3`.

### 2.3. "Early Arrival" Is Not "Early Processing"

Message `#3` can be **received and stored in the buffer**, yet not **emitted to the business handler**. Logs should distinguish:

~~~text
MESSAGE_RECEIVED  group=SHIP-42 seq=3
MESSAGE_BUFFERED  group=SHIP-42 seq=3
... waiting for seq=1,2 ...
MESSAGE_RELEASED  group=SHIP-42 seq=3
HANDLER_COMPLETED group=SHIP-42 seq=3
~~~

This is an illustrative application log schema, not Spring Integration's default output. **Buffered** does not mean **processed**, and **released** does not mean downstream has committed.

## 3. Resequencer vs. Aggregator and FIFO Queues

| Component | Goal | Typical Input/Output | Auto-Recovers Lost Messages? |
|---|---|---|---|
| **Resequencer** | Re-emit messages in proper sequence order. | N messages → original messages in order. | No; needs timeout/recovery. |
| **Aggregator** | Combine multiple messages into one shared result per rule. | N messages → one result payload/group. | No; needs release/expiration policy. |
| **Splitter** | Split a payload into multiple child messages. | One batch → multiple item messages. | No; only creates parts. |
| **FIFO queue** | Preserve *enqueue* order within queue semantics. | Enqueue → dequeue in same queue order. | Does not restore business order scrambled before enqueue. |
| **Filter** | Drop messages failing a predicate. | One message → forwarded or dropped. | May leave Resequencer waiting on missing sequence. |
| **Message Store** | Persist message/group state per implementation. | State used by endpoints. | Durability depends on store type and transactions. |

Suppose a queue receives `3,1,2`. A FIFO queue will emit **3,1,2** because that is the enqueue order. If business logic requires **1,2,3**, a mechanism using sequence/correlation is needed to reorder.

### 3.1. Can You Replace It by Sorting a List?

If all messages are already in a complete `List`, sorting is simpler:

~~~java
events.stream()
        .sorted(java.util.Comparator.comparingInt(
                ShipmentEvent::sequenceNumber))
        .toList();
~~~

Resequencer becomes valuable when messages **arrive scattered over time**, potentially from different threads/queues, without knowing which message arrives next. That requires group state, release conditions, timeouts, and buffer monitoring.

### 3.2. Resequencer Does Not Replace Business Transactions

Even when `#1, #2, #3` are emitted in order, a downstream handler may fail on `#2` while `#3` is dispatched concurrently under an async mechanism. "Emitted in order" **does not automatically guarantee** handlers **committed sequentially**. If business rules require strict sequential execution, also verify channels, consumer concurrency, transaction boundaries, and acknowledgment rules.

## 4. Required Information for Safe Buffering

### 4.1. Correlation Key: Which Group Is Waiting?

Suppose two shipments both receive `sequenceNumber=2`:

~~~text
SHIP-42 / RUN-7 / #2
SHIP-99 / RUN-3 / #2
~~~

They **must not enter the same message group**. Spring Integration typically uses `correlationId` in Resequencer to group at the infrastructure level. In the business payload, retain sufficiently distinct keys:

- `shipmentId`: business entity.
- `runId` or `streamVersion`: a specific sequence instance, preventing mixing replays or new releases.
- `eventId`: event identifier, useful for deduplication/observability.
- `sequenceNumber`: position in the sequence.
- `sequenceSize`: total parts if known and part of the contract.

**Do not default `correlationId` to `shipmentId` alone** if the same shipment can be reprocessed across multiple runs. A group key might be `shipmentId + ":" + runId`, ensuring collision-free encoding compatible with the transport schema.

### 4.2. Sequence Number and Size

| Field | Example Constraint | Why? |
|---|---|---|
| `sequenceNumber` | Positive integer, starting at 1. | Each position has a well-defined meaning. |
| `sequenceSize` | Positive integer, fixed within the group. | Identifies when a finite sequence is complete. |
| `sequenceNumber <= sequenceSize` | Mandatory in finite problems. | Prevents out-of-bounds positions. |
| Unique sequence position | One event per final position. | Prevents duplicates/conflicts. |
| Stable group key | Unchanged across retries and adapters. | Prevents group splitting or mixing. |

When a sequence **has no upfront size** (long-lived streams, dynamic fragment counts), `sequenceSize` may be unknown or lack a complete value. Do not mechanically enforce "1 through N complete" when N is undefined; use an **end-of-stream marker**, watermark, another release rule, or an appropriate workflow state.

### 4.3. Scenarios You Must Classify

| Scenario | Example | Right Perspective |
|---|---|---|
| Valid out-of-order | `#3` arrives before `#2`. | Hold `#3`, wait for missing parts. |
| Missing message | `#1, #3` arrive, `#2` never appears. | Head-of-line blocking; needs deadline/recovery. |
| Pending duplicate | `#3` received twice before `#2`. | Must not count as two distinct positions. |
| Already-released duplicate | `#1` arrives again after `#1` was emitted. | Dedupe/late-delivery policy; do not emit twice unintentionally. |
| Inconsistent size | Same group has one reply size=3, another size=5. | Schema/group contract error. |
| Foreign message | `#2` of RUN-8 enters RUN-7. | Never merge mistakenly; verify correlation. |
| Gap timeout | Waiting for `#2` exceeds deadline. | Expiration/partial failure/quarantine. |
| Late missing message | `#2` arrives after group expired. | Explicit late-arrival policy; do not reopen arbitrarily. |
| Consumer fails after release | Messages emitted in order but handler failed. | Downstream failure, not a sorting bug. |

## 5. Immutable Java Data Example

We use **Java 17+, Spring Boot 3.x, Spring Integration 6.x** in these examples. Simulated types are assumed to be in the same package; in production, split `public` types into their own files.

~~~java
record ShipmentEvent(
        String shipmentId,
        String runId,
        String eventId,
        int sequenceNumber,
        int sequenceSize,
        String eventType) {

    ShipmentEvent {
        if (shipmentId == null || shipmentId.isBlank()
                || runId == null || runId.isBlank()
                || eventId == null || eventId.isBlank()
                || eventType == null || eventType.isBlank()
                || sequenceSize <= 0
                || sequenceNumber <= 0
                || sequenceNumber > sequenceSize) {
            throw new IllegalArgumentException(
                    "INVALID_SHIPMENT_SEQUENCE_EVENT");
        }
    }
}

record SequenceGroup(String shipmentId, String runId) {
    SequenceGroup {
        if (shipmentId == null || shipmentId.isBlank()
                || runId == null || runId.isBlank()) {
            throw new IllegalArgumentException("INVALID_GROUP_KEY");
        }
    }
}
~~~

In this lesson, `ShipmentEvent` is an **illustrative business DTO**. Shipping state must not be applied to a real system merely because the `eventType` string says `DELIVERED`; production also checks authorization, business state machine transitions, and event provenance.

Some example events:

~~~java
ShipmentEvent first = new ShipmentEvent(
        "SHIP-42", "RUN-7", "EVT-1", 1, 3, "CREATED");
ShipmentEvent second = new ShipmentEvent(
        "SHIP-42", "RUN-7", "EVT-2", 2, 3, "PACKED");
ShipmentEvent third = new ShipmentEvent(
        "SHIP-42", "RUN-7", "EVT-3", 3, 3, "HANDED_OVER");
~~~

Here messages have `sequenceSize=3`; a fourth event for a shipment must belong to **a different sequence contract** or choose size=4 initially. Do not mutate the size of an in-flight group just because a new event appears.

## 6. Buffer Algorithm to Understand Resequencer Internals

Before configuring Spring Integration, let us model a simple buffer in plain Java. This model **releases contiguous prefixes as they become ready**; it helps illustrate why early messages must wait for missing positions, but **does not replace Spring Integration's implementation**, especially regarding message stores, release strategies, transactions, and error handling.

### 6.1. Return Data After Each Acceptance

~~~java
import java.util.List;

record BufferUpdate(
        List<ShipmentEvent> ready,
        int pendingCount,
        int nextExpected,
        boolean complete) {

    BufferUpdate {
        ready = List.copyOf(ready);
    }
}
~~~

Meaning:

- `ready`: messages newly eligible for emission **on this acceptance**.
- `pendingCount`: number of messages held back due to remaining gaps.
- `nextExpected`: next position needed.
- `complete`: the entire finite sequence from 1 to N has passed through the algorithm.

`complete` at the buffer level **does not prove** downstream handlers succeeded or side effects committed.

### 6.2. An In-Memory Buffer Partitioned by Key

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

final class SequenceBuffer {

    private final Map<SequenceGroup, PendingGroup> groups =
            new HashMap<>();

    synchronized BufferUpdate accept(ShipmentEvent event) {
        Objects.requireNonNull(event, "event");

        SequenceGroup key = new SequenceGroup(
                event.shipmentId(), event.runId());

        PendingGroup state = groups.get(key);
        if (state == null) {
            state = new PendingGroup(event.sequenceSize());
            groups.put(key, state);
        }

        if (state.declaredSize != event.sequenceSize()) {
            throw new IllegalArgumentException(
                    "INCONSISTENT_SEQUENCE_SIZE");
        }
        if (state.complete) {
            throw new IllegalStateException(
                    "SEQUENCE_ALREADY_COMPLETED");
        }
        if (event.sequenceNumber() < state.nextExpected) {
            throw new IllegalStateException(
                    "DUPLICATE_OR_LATE_SEQUENCE");
        }
        if (state.pending.putIfAbsent(
                event.sequenceNumber(), event) != null) {
            throw new IllegalStateException(
                    "DUPLICATE_PENDING_POSITION");
        }

        List<ShipmentEvent> ready = new ArrayList<>();

        // Emit only a contiguous segment starting from nextExpected.
        while (true) {
            ShipmentEvent next =
                    state.pending.remove(state.nextExpected);
            if (next == null) {
                break;
            }
            ready.add(next);
            state.nextExpected++;
        }

        state.complete =
                state.nextExpected > state.declaredSize;

        return new BufferUpdate(
                ready,
                state.pending.size(),
                state.nextExpected,
                state.complete);
    }

    private static final class PendingGroup {
        final int declaredSize;
        int nextExpected = 1;
        boolean complete;
        final TreeMap<Integer, ShipmentEvent> pending =
                new TreeMap<>();

        PendingGroup(int declaredSize) {
            this.declaredSize = declaredSize;
        }
    }
}
~~~

### 6.3. Walking Through Key Logic

1. `SequenceGroup(shipmentId, runId)` separates messages into independent groups. Messages with the same sequence number from different runs are never merged.
2. `declaredSize` captures group size from the first message and checks that subsequent messages agree.
3. `pending` is a `TreeMap` keyed by position, tracking which messages are currently held.
4. `putIfAbsent` detects **duplicates at unreleased positions** instead of silently overwriting.
5. If an already-released position arrives again, `sequenceNumber < nextExpected` throws **duplicate/late**.
6. The `while` loop emits only while `nextExpected` exists; while waiting for `#2`, `#3` cannot jump ahead even if already buffered.
7. `synchronized` makes reading/updating state and building `ready` consistent **within a single JVM and a single buffer instance**.

### 6.4. Concrete Simulation

~~~java
SequenceBuffer buffer = new SequenceBuffer();

BufferUpdate a = buffer.accept(third);
// a.ready() = []
// a.pendingCount() = 1; a.nextExpected() = 1

BufferUpdate b = buffer.accept(first);
// b.ready() = [first]
// b.pendingCount() = 1; b.nextExpected() = 2

BufferUpdate c = buffer.accept(second);
// c.ready() = [second, third]
// c.pendingCount() = 0; c.nextExpected() = 4
// c.complete() = true
~~~

This trace uses **partial-prefix release**; under full-sequence release, `first` stays buffered in the group and `first, second, third` emit together once all three arrive. Both yield **the same final order**, with different latency and timeout semantics.

### 6.5. Practical Limitations of the Illustrative Algorithm

`SequenceBuffer` intentionally **lacks** support for:

- TTL, memory caps, maximum group size, eviction policies, and durable snapshots.
- Mid-stream sequenceSize changes or streams with unknown N.
- Emitting messages transactionally together with cursor updates.
- Exactly-once broker publication or crash recovery mechanisms.
- Late replies and idempotency after group cleanup.
- Distinguishing **identical-content** duplicates from **conflicting-content** duplicates at the same sequenceNumber.
- Parallel delivery of `ready` results downstream.

**Risk to remember:** `synchronized accept(...)` only guarantees **computation** order. If thread A receives `ready=[#1]` and has not published yet while thread B receives `ready=[#2,#3]` and publishes first, downstream can still see `#2` before `#1`. To guarantee **publication order**, serialize emission per group, design a single-writer/ordered outbox, or use endpoints and channels with matching contracts. Do not deploy this buffer as a production resequencer just because unit tests pass.

## 7. Unit Tests for "Early-Arriving Messages"

### 7.1. `#3` Must Be Held Until Predecessors Arrive

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SequenceBufferEarlyArrivalTest {
    private final SequenceBuffer buffer =
            new SequenceBuffer();

    private static ShipmentEvent event(int number) {
        return new ShipmentEvent(
                "SHIP-42", "RUN-7", "EVT-" + number,
                number, 3, "TYPE-" + number);
    }

    @Test
    void buffersFutureMessagesUntilMissingPredecessorArrives() {
        BufferUpdate after3 = buffer.accept(event(3));
        assertTrue(after3.ready().isEmpty());
        assertEquals(1, after3.pendingCount());
        assertEquals(1, after3.nextExpected());

        BufferUpdate after1 = buffer.accept(event(1));
        assertEquals(List.of(1),
                after1.ready().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
        assertFalse(after1.complete());

        BufferUpdate after2 = buffer.accept(event(2));
        assertEquals(List.of(2, 3),
                after2.ready().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
        assertEquals(0, after2.pendingCount());
        assertTrue(after2.complete());
    }

    @Test
    void reversedArrivalStillReleasesInOrder() {
        BufferUpdate after3 = buffer.accept(event(3));
        BufferUpdate after2 = buffer.accept(event(2));
        BufferUpdate after1 = buffer.accept(event(1));

        assertTrue(after3.ready().isEmpty());
        assertTrue(after2.ready().isEmpty());
        assertEquals(List.of(1, 2, 3),
                after1.ready().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
        assertTrue(after1.complete());
    }
}
~~~

The second test captures the core scenario of this lesson: **messages #3 and #2 arrive before #1**, so nothing is emitted on the first two arrivals. Once `#1` arrives, all three are ready and can be emitted in order.

### 7.2. Interleaved Groups Must Not Affect Each Other

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SequenceBufferGroupIsolationTest {
    @Test
    void twoGroupsKeepIndependentNextExpected() {
        SequenceBuffer buffer = new SequenceBuffer();

        ShipmentEvent a2 = new ShipmentEvent(
                "SHIP-A", "RUN-1", "A-2", 2, 2, "PACKED");
        ShipmentEvent b1 = new ShipmentEvent(
                "SHIP-B", "RUN-1", "B-1", 1, 2, "CREATED");
        ShipmentEvent a1 = new ShipmentEvent(
                "SHIP-A", "RUN-1", "A-1", 1, 2, "CREATED");
        ShipmentEvent b2 = new ShipmentEvent(
                "SHIP-B", "RUN-1", "B-2", 2, 2, "PACKED");

        assertTrue(buffer.accept(a2).ready().isEmpty());
        assertEquals(List.of("B-1"),
                buffer.accept(b1).ready().stream()
                        .map(ShipmentEvent::eventId).toList());
        assertEquals(List.of("A-1", "A-2"),
                buffer.accept(a1).ready().stream()
                        .map(ShipmentEvent::eventId).toList());
        assertEquals(List.of("B-2"),
                buffer.accept(b2).ready().stream()
                        .map(ShipmentEvent::eventId).toList());
    }
}
~~~

Two groups can **interleave in global output**, while maintaining order within each group. Do not force the whole system to emit all of `SHIP-A` before `SHIP-B` when business rules do not require global ordering; that reduces throughput and creates unnecessary cross-group head-of-line blocking.

### 7.3. Duplicates, Inconsistent Sizes, and Late Positions

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class SequenceBufferInvalidTest {
    private final SequenceBuffer buffer =
            new SequenceBuffer();

    private static ShipmentEvent e(int position, int total) {
        return new ShipmentEvent(
                "SHIP-1", "RUN-1", "EVT-" + position,
                position, total, "TYPE-" + position);
    }

    @Test
    void duplicateBufferedPositionIsRejected() {
        buffer.accept(e(3, 3));
        assertThrows(IllegalStateException.class, () ->
                buffer.accept(e(3, 3)));
    }

    @Test
    void duplicateAlreadyReleasedPositionIsRejected() {
        buffer.accept(e(1, 3));
        assertThrows(IllegalStateException.class, () ->
                buffer.accept(e(1, 3)));
    }

    @Test
    void inconsistentSequenceSizeIsRejected() {
        buffer.accept(e(2, 3));
        assertThrows(IllegalArgumentException.class, () ->
                buffer.accept(e(1, 4)));
    }

    @Test
    void sequenceNumberOutsideDeclaredRangeIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                e(4, 3));
    }
}
~~~

In production, duplicates happen normally under at-least-once brokers. **Throwing an exception** here demonstrates detection in the lesson, but is **not the only operational strategy**. A system can deduplicate by operation ID, increment a metric, and acknowledge valid duplicates, while raising an error if two conflicting payloads share the same position.

## 8. Integrating Resequencer in Spring Integration Java DSL

### 8.1. Flow Architecture

Spring Integration provides **Resequencer** for Spring `Message` objects carrying appropriate group/sequence metadata. Essentially, it is a message group processor that **reorders and emits messages** rather than combining all payloads into one aggregated payload like a typical Aggregator.

~~~mermaid
flowchart LR
    P[Message Producer] --> I[(shipment.events.in)]
    I --> R[Spring Integration Resequencer]
    R --> S[(Message Group Store)]
    S -->|Release condition met| R
    R --> O[(shipment.events.ordered)]
    O --> H[Ordered Handler]
~~~

This pattern cleanly separates three responsibilities:

1. **Upstream** supplies correlation/sequence metadata per contract.
2. **Resequencer** manages groups, buffers messages, and decides when to release.
3. **Downstream** executes business logic in emitted message order.

### 8.2. Configuring Two Channels and a Resequencer

Java DSL example targeting **Java 17+ and Spring Integration 6.x**:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

final class OrderedEventProbe {
    private final List<ShipmentEvent> observed =
            new CopyOnWriteArrayList<>();

    void record(ShipmentEvent event) {
        observed.add(event);
    }

    List<ShipmentEvent> snapshot() {
        return List.copyOf(observed);
    }
}

@Configuration
@EnableIntegration
class ShipmentResequencerConfiguration {

    @Bean(name = "shipment.events.in")
    MessageChannel incomingEvents() {
        return new DirectChannel();
    }

    @Bean(name = "shipment.events.ordered")
    MessageChannel orderedEvents() {
        return new DirectChannel();
    }

    @Bean
    OrderedEventProbe orderedEventProbe() {
        return new OrderedEventProbe();
    }

    @Bean
    IntegrationFlow reorderShipmentEvents() {
        return IntegrationFlow.from("shipment.events.in")
                .resequence()
                .channel("shipment.events.ordered")
                .get();
    }

    @Bean
    IntegrationFlow handleOrderedEvents(OrderedEventProbe probe) {
        return IntegrationFlow.from("shipment.events.ordered")
                .handle(ShipmentEvent.class, (event, headers) -> {
                    probe.record(event);
                    return null; // Terminal handler in this lesson.
                })
                .get();
    }
}
~~~

In this demo configuration, `DirectChannel` keeps dispatch synchronous with the caller. This lets tests verify how many events the probe received once release conditions are met. However, **buffering and group lifecycle** remain the responsibility of Resequencer, not `DirectChannel`.

The code uses `.resequence()` in Java DSL. In production, verify the **exact API/version** of `spring-integration-core`, message store configuration, partial sequence release, timeouts, and group expiration handling. The example above **does not** include a durable store or production retry/error flows, and should not be used for critical workflows without completing those parts.

### 8.3. Building Messages with Correlation and Sequence Headers

This is essential: Spring Integration Resequencer cannot deduce that "eventType=PACKED is #2" if you only send a payload without defining ordering or proper headers.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class ShipmentMessageFactory {

    static Message<ShipmentEvent> toMessage(
            ShipmentEvent event) {
        String correlationKey =
                event.shipmentId() + ":" + event.runId();

        return MessageBuilder.withPayload(event)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        correlationKey)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        event.sequenceNumber())
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        event.sequenceSize())
                .build();
    }
}
~~~

**Notes:**

- `correlationId` here is an **application-constructed** string. When input fields can contain arbitrary delimiters, use collision-free encoding or normalized group IDs.
- `sequenceNumber` in this example is an integer from 1 to N, not a timestamp.
- `sequenceSize` is uniform across the group, enabling release of a finite sequence.
- `MessageHeaders.ID` is the ID of an individual message; never use it in place of `shipmentId` or `runId`.
- If an upstream **Splitter** already created sequence headers, do not overwrite them arbitrarily; inspect which headers are retained and whether they match the group to be resequenced.

If events traverse HTTP/Kafka/JMS/AMQP, adapters may map headers to different wire formats or filter them out. Test header propagation across the exact transport boundary. Having `shipmentId` in the payload **is not enough** if Resequencer groups by a header that was dropped.

## 9. Integration Test: Messages #3 and #2 Are Buffered Before #1

### 9.1. Testing the Real Flow, Not Just Sorting a List

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(ShipmentResequencerConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ShipmentResequencerIntegrationTest {

    @Autowired
    @Qualifier("shipment.events.in")
    private MessageChannel input;

    @Autowired
    private OrderedEventProbe probe;

    private ShipmentEvent event(int number) {
        return new ShipmentEvent(
                "SHIP-42", "RUN-7", "EVT-" + number,
                number, 3, "TYPE-" + number);
    }

    private void send(ShipmentEvent event) {
        assertTrue(input.send(
                ShipmentMessageFactory.toMessage(event), 1_000));
    }

    @Test
    void earlyThirdAndSecondWaitUntilFirstArrives() {
        send(event(3));
        assertTrue(probe.snapshot().isEmpty());

        send(event(2));
        assertTrue(probe.snapshot().isEmpty());

        send(event(1));
        assertEquals(List.of(1, 2, 3),
                probe.snapshot().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
    }

    @Test
    void alreadyOrderedInputIsEventuallyReleasedInOrder() {
        send(event(1));
        send(event(2));
        send(event(3));

        assertEquals(List.of(1, 2, 3),
                probe.snapshot().stream()
                        .map(ShipmentEvent::sequenceNumber)
                        .toList());
    }
}
~~~

**Why choose arrival `3,2,1`?** It clearly tests "buffering early messages" **without assuming** whether Resequencer emits a partial prefix if `#1` arrives before `#3`. Until `#1` arrives, no contiguous prefix starting at 1 exists. Once `#1` arrives, the whole group is complete and outputs `1,2,3`.

**Test limitations:** it tests channels and Resequencer inside a single JVM, without testing broker durability, restarts, timeouts, or exactly-once delivery. If using a customized release strategy, verify assertions for when a prefix emits against your exact contract.

### 9.2. Testing That Two Shipments Do Not Mix

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(ShipmentResequencerConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ShipmentResequencerIsolationTest {

    @Autowired
    @Qualifier("shipment.events.in")
    private MessageChannel input;

    @Autowired
    private OrderedEventProbe probe;

    private void send(String shipment, int sequenceNumber) {
        ShipmentEvent e = new ShipmentEvent(
                shipment, "RUN-1",
                shipment + "-E" + sequenceNumber,
                sequenceNumber, 2, "TYPE");
        assertTrue(input.send(
                ShipmentMessageFactory.toMessage(e), 1_000));
    }

    @Test
    void interleavedGroupsAreOrderedIndependently() {
        send("SHIP-A", 2);
        send("SHIP-B", 2);
        send("SHIP-B", 1);
        send("SHIP-A", 1);

        Map<String, List<Integer>> byShipment =
                probe.snapshot().stream().collect(
                        Collectors.groupingBy(
                                ShipmentEvent::shipmentId,
                                Collectors.mapping(
                                        ShipmentEvent::sequenceNumber,
                                        Collectors.toList())));

        assertEquals(List.of(1, 2), byShipment.get("SHIP-A"));
        assertEquals(List.of(1, 2), byShipment.get("SHIP-B"));
    }
}
~~~

This test does **not** try to enforce a global order between SHIP-A and SHIP-B. It only ensures each group maintains its own order, allowing different groups to progress independently.

### 9.3. Why Use `@DirtiesContext`?

`OrderedEventProbe` retains state across messages in the same Spring context; Resequencer may also retain group state in its Message Store. To keep tests isolated, use `@DirtiesContext` or an explicit reset mechanism. Never let a first test create an incomplete group and a subsequent test reuse the same group ID, causing unpredictable results.

### 9.4. Configuring Partial Release Is an Option

If business logic wants `#1` emitted as soon as it arrives even though `#2` is missing, consider Resequencer's **release partial sequences** option. Conceptually:

~~~text
Arrival: 3 -> 1 -> 2

Wait-for-all:
  after 3: output []
  after 1: output []
  after 2: output [1,2,3]

Contiguous partial release:
  after 3: output []
  after 1: output [1]
  after 2: output [2,3]
~~~

When configuring with Java DSL, check the `releasePartialSequences` API and release conditions supported by **the Spring Integration version you are running**. Never copy expectations from wait-for-all into a partial-release setup or vice versa. In particular, emitting prefixes before group completion changes **timeout, duplicate, and group cleanup semantics**.

### 9.5. Do Not Infer Business Completion from `send=true`

In both tests above, final results come from `OrderedEventProbe` after the handler. `MessageChannel.send(...)` only indicates ingress dispatch succeeded per channel semantics; message `#3` can be **successfully buffered** by Resequencer without a single `ShipmentEvent` reaching the downstream handler yet. That is the intended behavior.

## 10. When a Missing Message Never Arrives

### 10.1. Head-of-Line Blocking

Suppose Resequencer receives:

~~~text
Group SHIP-42/RUN-7

received = {1, 3, 4, 5}
missing  = {2}
~~~

Under a strict ordering policy, message `#3` cannot be emitted before `#2`. Consequently, **a single missing position can block all subsequent arrived messages**. This phenomenon is **head-of-line blocking** within a sequence.

~~~mermaid
flowchart LR
    B["Buffer: 3,4,5"] --> G{"nextExpected = 2"}
    G -->|No #2 yet| WAIT["Wait / check deadline"]
    G -->|#2 arrived| RELEASE["Emit 2 → 3 → 4 → 5"]
    WAIT --> TIMEOUT["Expiration / recovery"]
~~~

### 10.2. How Long Should You Wait?

Define deadlines based on business needs:

| Flow | Expectation | Suggestion |
|---|---|---|
| Lossy sensor telemetry | Tolerates some gaps with missing-data markers. | Windows/watermarks, gap reports, partial policy. |
| Order must be created before delivery | Never emit delivery before creation. | Fail closed, replay/recover missing message. |
| Audit log needing complete order | Cannot silently omit events. | Durable store, missing alerts, retention. |
| Low-sensitivity stats dashboard | Can skip gaps after a grace period. | Expiration and explicit gap-describing metadata. |

**There is no universal default timeout suitable for every system.** Waiting forever leaks memory/state; expiring too early drops valid slow events.

### 10.3. Group Timeout vs. Business Timeout

Depending on configuration, Spring Integration can manage **group timeout, group expiration, discard/expired group handling**, or partial sequence release on related components. Distinguish:

- **Group waiting time:** from when messages in the group start buffering until policy triggers timeout.
- **Upstream delivery timeout:** how long the producer/broker waited to send or receive an ack.
- **Downstream handler timeout:** after Resequencer releases, how long the handler takes to process.
- **Business deadline:** how long the shipping/approval workflow allows waiting.

These can be completely separate clocks. **Do not assume a Gateway timeout automatically expires a Resequencer group**, or that group expiry automatically cancels running workers.

### 10.4. Options Upon Expiration

1. **Quarantine the whole group:** retain metadata, lists of present/missing positions, and reason so operators can intervene.
2. **Request redelivery:** ask upstream/broker or event store to resend message `#2`.
3. **Emit partial with missing-state flags:** only when business rules allow, using a schema with missing/gap markers.
4. **Halt the workflow and raise an error:** prevent processing later events without prerequisites.
5. **Drop group per retention policy:** only when results need no recovery and data loss is acceptable.

Never **advance `nextExpected` from 2 to 3** merely because the timer expired if business rules forbid skipping step 2.

## 11. Inspecting Gaps Independently and Deterministically

To test **which messages have not arrived** without relying on thread scheduling, you can write a pure Java inspector separate from Resequencer. This inspector reads a current snapshot and **does not release groups itself**.

### 11.1. Waiting State Snapshot

~~~java
import java.time.Instant;
import java.util.Set;

record SequenceObservation(
        SequenceGroup group,
        int sequenceSize,
        Set<Integer> received,
        Instant firstObservedAt) {

    SequenceObservation {
        if (group == null || firstObservedAt == null
                || sequenceSize <= 0 || sequenceSize > 1000) {
            throw new IllegalArgumentException(
                    "INVALID_SEQUENCE_OBSERVATION");
        }
        received = Set.copyOf(received);
        if (received.stream().anyMatch(
                n -> n == null || n < 1 || n > sequenceSize)) {
            throw new IllegalArgumentException(
                    "INVALID_RECEIVED_POSITION");
        }
    }
}

record GapReport(
        SequenceGroup group,
        java.util.List<Integer> missingPositions,
        boolean deadlineReached) {

    GapReport {
        missingPositions = java.util.List.copyOf(missingPositions);
    }
}
~~~

The `sequenceSize <= 1000` limit is an **illustrative application rule** to avoid generating huge lists; it is not a Spring Integration default constant. Production should choose limits based on capacity and policy.

### 11.2. Function to Compute Gaps and Deadlines

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.stream.IntStream;

final class GapInspector {

    GapReport inspect(
            SequenceObservation observation,
            Instant now,
            Duration maxWait) {

        if (now == null || maxWait == null
                || maxWait.isNegative() || maxWait.isZero()
                || now.isBefore(observation.firstObservedAt())) {
            throw new IllegalArgumentException(
                    "INVALID_GAP_INSPECTION_TIME");
        }

        List<Integer> missing =
                IntStream.rangeClosed(1, observation.sequenceSize())
                        .filter(n -> !observation.received().contains(n))
                        .boxed()
                        .toList();

        boolean deadlineReached =
                !now.isBefore(
                        observation.firstObservedAt().plus(maxWait));

        return new GapReport(
                observation.group(), missing, deadlineReached);
    }
}
~~~

This is **observation** logic, not the framework's auto-expiration trigger. For groups using partial release, `received` must represent **all positions ever received**, including already-released ones, if you want to compute missing positions across the entire sequence. Reading only messages still in `MessageGroupStore` would omit released positions and report false gaps.

### 11.3. Testing Without `Thread.sleep`

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GapInspectorTest {

    @Test
    void missingTwoIsVisibleBeforeAndAfterDeadline() {
        Instant first = Instant.parse("2026-01-01T00:00:00Z");
        SequenceObservation observed = new SequenceObservation(
                new SequenceGroup("SHIP-42", "RUN-7"),
                4,
                Set.of(1, 3, 4),
                first);

        GapInspector inspector = new GapInspector();

        GapReport before = inspector.inspect(
                observed,
                first.plusSeconds(20),
                Duration.ofSeconds(30));
        assertEquals(List.of(2), before.missingPositions());
        assertFalse(before.deadlineReached());

        GapReport after = inspector.inspect(
                observed,
                first.plusSeconds(30),
                Duration.ofSeconds(30));
        assertEquals(List.of(2), after.missingPositions());
        assertTrue(after.deadlineReached());
    }

    @Test
    void completeGroupHasNoMissingPositions() {
        Instant first = Instant.EPOCH;
        SequenceObservation observed = new SequenceObservation(
                new SequenceGroup("SHIP-1", "RUN-1"),
                3, Set.of(1, 2, 3), first);

        GapReport report = new GapInspector().inspect(
                observed,
                first.plusSeconds(5),
                Duration.ofSeconds(10));

        assertTrue(report.missingPositions().isEmpty());
        assertFalse(report.deadlineReached());
    }
}
~~~

**Benefit:** such a test reproduces "after 30 seconds, #2 is still missing" without waiting 30 seconds in CI. However, to prove **Spring Integration's group timeout/expiration handler actually fires**, an integration test configuring timeout and a clock/scheduler or bounded wait mechanism matching the framework is required.

## 12. Buffer Memory Is Not Infinite

### 12.1. When Many Groups Miss One Position

An operational example:

~~~text
10,000 groups
Each group receives #2..#20 without #1

Pending messages = 10,000 × 19 = 190,000
~~~

Those numbers are **purely illustrative arithmetic**, not Spring Integration benchmarks. If messages also carry large JSON payloads or attachments, memory/disk usage grows rapidly.

### 12.2. Limits to Enforce

| Limit | Why Needed? | Response When Exceeded |
|---|---|---|
| Maximum sequence size | Prevent huge size declarations from bugs/forged input. | Validate/reject before buffering. |
| Maximum pending per group | Prevent one group from holding too many messages. | Quarantine/backpressure per policy. |
| Maximum active groups | Bound total footprint. | Admission control, spill to durable store, or controlled reject. |
| Group TTL/idle timeout | Clean up long-stalled incomplete groups. | Expiration/recovery and late-arrival policy. |
| Message size | Block oversized payloads. | Validate, chunk, or store object references. |
| Store capacity | Prevent heap/disk/DB exhaustion. | Alert and apply backpressure instead of silent drops. |
| Retry attempts | Stop resend loops on unrecoverable gaps. | DLQ/manual repair past deadline. |

These limits are **application and operational policies**, not automatically enforced merely by calling `.resequence()`. Even with a persistent `MessageGroupStore`, monitor group count, storage usage, transaction contention, and cleanup.

### 12.3. Where Does Backpressure Happen?

In a synchronous flow, if Resequencer cannot buffer more items, upstream may receive an error or block on send. In an asynchronous flow, queues/brokers may keep accepting messages while Resequencer consumes slowly, shifting the backlog elsewhere.

Never fix memory exhaustion by **silently dropping early-arriving messages without logging**. If policy allows dropping, it must be an explicit decision with metrics, auditing, or business state. Otherwise, apply backpressure, input rate limits, and recovery paths.

## 13. Durability and Restart Recovery

### 13.1. In-Memory Group Store

A Resequencer keeping state inside the JVM might hold:

~~~text
SHIP-42/RUN-7:
  buffered = {#3, #4}
  waiting = #1, #2
~~~

If the process dies, **in-memory state may be lost**. When the consumer restarts, the broker may or may not redeliver unacked messages depending on transaction/ack policies. Never treat an in-memory buffer as durable just because Resequencer "accepted" the message.

### 13.2. Persistent Message Group Store

When high recoverability is required, evaluate a `MessageGroupStore` with appropriate persistence (such as a JDBC-backed store or another supported implementation in your stack), transaction boundaries, and cleanup.

~~~mermaid
flowchart LR
    B[(Broker / Input)] --> R[Resequencer]
    R --> S[(Durable Group Store)]
    R --> O[(Ordered Output)]
    O --> H[Handler]
    H --> D[(Business DB)]
~~~

Questions to answer:

- How does the store persist **payload, correlation, sequence, and group state**?
- Is a message **acked** before or after being persisted in the store?
- Does releasing messages downstream share the same transaction as updating group state?
- If a crash occurs after release but before ack, can outputs be re-emitted?
- When a group expires, how long are state/tombstones retained?
- Will serialization schemas of older stored messages still deserialize after deployments?

**A durable group store does not create end-to-end exactly-once semantics across broker, message store, and handler DB.** You may still need outbox/inbox patterns, transactional channel adapters, deduplication, and idempotency by operation key.

### 13.3. Restarts and Already-Released Messages

Example:

~~~text
T1: Resequencer receives #1, #2, #3
T2: Releases #1 and #2 downstream
T3: Process crashes before release state is durably saved
T4: Restart, broker redelivers
~~~

If downstream already committed `#1` and `#2`, re-emitting them can cause duplicate side effects. Therefore:

- Business logic should carry an **idempotency key** scoped to group + sequence/event ID.
- Handlers must recognize previously processed messages.
- Broker redeliveries must be distinguishable from new events.
- Recovery must account for group replay policies rather than assuming "in order" means "exactly once."

## 14. Duplicates and Late Arrivals: Do Not Merge Into Closed Groups

### 14.1. Two Types of Duplicates

1. **Pending duplicate:** `#3` is received twice while `#2` is still missing.
2. **Post-release duplicate:** `#1` is resent after the consumer/resequencer already emitted `#1`.

In the plain Java example, both are rejected. In Spring Integration, how a message group handles duplicates depends on message identity, store, and processor settings. **Do not assume identical `sequenceNumber` values are automatically deduplicated as one business operation** without checking configuration and testing.

### 14.2. Conflicting Payloads at the Same sequenceNumber

~~~text
SHIP-42 / RUN-7 / seq=2:
  eventId=A, eventType=PACKED, quantity=5

SHIP-42 / RUN-7 / seq=2:
  eventId=B, eventType=PACKED, quantity=50
~~~

These two events cannot simply follow "last-write-wins" if package quantity affects business state. Verify:

- Is this a redelivery of the same event or two data revisions?
- Is there an explicit update/correction protocol?
- Which producers are authorized to emit this sequence?
- Is quarantine or operator review required?

Never let an alien payload occupy slot `#2` just because the sequence number matches. Enforce identity, schema, and authorization checks.

### 14.3. Tombstones for Completed/Expired Groups

If group `SHIP-42/RUN-7` completed and was purged from the store, a late-arriving `#3` could be misinterpreted as **starting a new group** without a mechanism to recognize closed groups.

One design approach is storing minimal state/tombstones:

~~~text
groupKey = SHIP-42/RUN-7
state = COMPLETED
completedAt = ...
lastSequence = 3
retentionUntil = ...
~~~

**Tombstones are a suggested application/storage design pattern**, not a guarantee that every `MessageGroupStore` emits that exact record. Choose retention based on replay horizon, storage limits, and security.

### 14.4. Late Missing Message After Timeout

Suppose `#3` was held due to missing `#2`, the group expired after 30 seconds, and `#2` finally arrives at second 35. Options:

- **Reconcile from a durable event log:** rebuild the proper sequence per policy and emit compensating events if needed.
- **Quarantine late arrival:** operator reviews before replay.
- **Ignore with audit trail:** only if business rules deem stale data obsolete.
- **Resume group:** only when state, side effects, and versions remain compatible; do not silently stitch onto an expired group.

Never start a new group treating `#2` as the start of a fresh sequence, as that mixes **old and new processing runs**.

## 15. Emission Order Does Not Automatically Guarantee Completion Order

### 15.1. Resequencer Works Correctly, Yet Workers Can Still Finish Out of Order

Suppose Resequencer emits:

~~~text
#1 -> #2 -> #3
~~~

Then messages enter an `ExecutorChannel` with three workers:

~~~text
Worker A takes #1, takes 2 seconds
Worker B takes #2, takes 100 ms
Worker C takes #3, takes 50 ms

Commit order can become: #3, #2, #1
~~~

Thus Resequencer **restored dispatch order**, yet an async consumer can scramble **business commit order** without further coordination.

### 15.2. Choose the Semantics You Actually Need to Guarantee

| Requirement | Measures Likely Needed |
|---|---|
| Downstream only needs to **receive** in order. | Resequencer + order-preserving send/receive channels. |
| Handler must **start** in order. | Consumer serialization / per-key ordering and lifecycle checks. |
| Side effects must **commit** in order. | Per-group serialization, transactions/state machine, idempotency. |
| Independent shipments processed in parallel. | Partition/shard by shipment group, single writer per group. |
| Cross-service ordering required. | Event versions, ordered outbox/inbox, durable correlation/replay. |

A system can choose **strict order within each shipment while running shipments in parallel**. This usually balances correctness and throughput without serializing the entire system into a single lane.

### 15.3. FIFO Cannot Override Transport Boundaries

Even when an in-JVM output channel preserves order, a downstream adapter or consumer group may route messages into multiple partitions. If `#1` and `#2` of the same shipment land on **two different broker partitions**, there is no general guarantee consumers process them in sequence.

Verify:

- Is the partition key preserved by `shipmentId`/group key?
- What are consumer thread counts and acknowledgment semantics?
- Do retries move messages to another queue and break order?
- Can dead-letter/replays skip over an older event?
- Does the handler check expected version/sequence in the business store?

**Resequencing at one point does not create ordering across all subsequent boundaries.**

## 16. Combining with Other EIPs

### 16.1. Splitter → Resequencer → Aggregator

A flow may run:

~~~mermaid
flowchart LR
    A["Batch 3 items"] --> S[Splitter]
    S --> P[Parallel processing]
    P --> R[Resequencer]
    R --> G[Aggregator]
    G --> O["Batch Result"]
~~~

Meaning:

- **Splitter** creates parts and typically attaches sequence/correlation metadata when configured.
- Workers may complete in different orders.
- **Resequencer** emits messages in the desired sequence.
- **Aggregator** combines results into a single payload if required by business logic.

However, not every flow needs both **Resequencer and Aggregator**. If Aggregator can collect by ID regardless of arrival order and sort the output list itself, adding Resequencer may just add latency and buffering. Choose the model matching the downstream contract.

### 16.2. A Filter Before Resequencer Can Create a Permanent Gap

~~~text
Splitter creates #1, #2, #3 with sequenceSize=3

Filter:
  #1 -> accepted
  #2 -> rejected/discarded
  #3 -> accepted

Resequencer receives #1 and #3, missing #2
~~~

If Filter silently discards `#2` while Resequencer still waits for the original full sequence, the group may **never complete**.

Design options:

1. **Do not discard—emit a placeholder/tombstone for position #2** if the contract allows, letting downstream know the slot was intentionally filtered.
2. **Recompute sequences after Filter** only if it can be done completely and consistently for the entire group; never arbitrarily alter numbers/sizes per message.
3. **Move Filter after Resequencer** if business policy allows and original order must be preserved prior to filtering.
4. **Adjust release/expiration policy** if business rules allow omitting some parts.

Example placeholder:

~~~text
Position 2:
  sequenceNumber = 2
  outcome = FILTERED_OUT
  reason = NOT_ELIGIBLE
~~~

This is a **proposed application schema**, not a message generated automatically by Resequencer. Consumers must understand a placeholder does not mean business processing succeeded at that position.

### 16.3. Router Can Create Divergent Arrival Paths

If a Router splits a group across two queues before Resequencer, messages may arrive with different latencies—one valid reason for Resequencer. However, if each branch produces a **different `correlationId`** or only one branch leads to Resequencer, the flow cannot reconstruct the original sequence.

Verify:

- Do all messages of a sequence converge back into the **same group**?
- Does the Router send exactly one message per position, or duplicate copies?
- Do channels and adapters preserve sequence headers?
- Does a failed branch emit a placeholder/error outcome or have an explicit deadline?
- If routing depends on policy version, do replayed old messages still group properly?

### 16.4. Transformer Must Not Strip Sequence Context

A Transformer may return a new payload:

~~~java
record NormalizedEvent(
        String shipmentId,
        String runId,
        int sequenceNumber,
        String normalizedType) {}

NormalizedEvent normalize(ShipmentEvent event) {
    return new NormalizedEvent(
            event.shipmentId(),
            event.runId(),
            event.sequenceNumber(),
            event.eventType().trim().toUpperCase());
}
~~~

When the payload changes, sequence headers needed by Resequencer **must still propagate per framework/adapter contract**. Do not confuse `NormalizedEvent.sequenceNumber` inside the payload with `IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER` read by Resequencer; if the header is lost, having a payload field alone will not necessarily make the framework reorder automatically.

### 16.5. Content Enricher and Sequence Latency

A Content Enricher calling Customer Profile Service might make message `#2` slower than `#3`. A downstream Resequencer restores order once both finish, but does not remove the underlying latency. If latency spikes persistently, measure **enricher latency**, **gap age**, **buffered count**, and **timeouts** instead of just bumping group timeouts.

### 16.6. Gateway Request–Reply and Resequencer Output

A Gateway expecting **one reply per request** may not fit when Resequencer holds a message waiting for other events in the group. Example:

~~~text
Gateway sends message #3, waits 2 seconds for reply
Resequencer buffers #3 because #1 and #2 are missing
Gateway times out after 2 seconds
#1 and #2 arrive after 5 seconds
~~~

Message `#3` may later be released, after the caller already timed out. Do not assume Gateway timeout automatically removes `#3` from the group. If a message must wait for multiple separate events, prefer an async API / operation status model over holding synchronous request–reply open too long.

## 17. Error Handling: Who Owns Each Stage?

### 17.1. Different Failure Classes

~~~mermaid
flowchart TD
    I[Incoming Message] --> V{Valid header + payload?}
    V -->|No| E1[Input validation / malformed]
    V -->|Yes| B[Resequencer buffer]
    B -->|Store error/full| E2[Store / capacity failure]
    B -->|Missing sequence| W[Wait / timeout]
    W --> E3[Group expiration / recovery]
    B -->|Releasable| D[Ordered dispatch]
    D -->|No subscriber| E4[Delivery failure]
    D -->|Handler receives| H[Business handler]
    H -->|Failure| E5[Processing failure]
    H -->|Success| OK[Business outcome]
~~~

**Do not lump everything into one `resequencer_failed` metric.** Schema errors, group timeouts, store failures, dispatch failures, and downstream processing errors require different remediations.

### 17.2. Synchronous vs. Asynchronous

With `DirectChannel`, exceptions from an endpoint can propagate back to the sender on the call stack. With `ExecutorChannel`, `QueueChannel`/pollers, or brokers, errors may happen after upstream already received acknowledgment; error flows must then match the **execution context**.

Spring Integration supports `ErrorMessage` and `errorChannel` when configured appropriately, but:

- Not every error goes to the same global error channel.
- An event buffered waiting on a gap **is not automatically an error** sent to the error channel.
- Group expiration needs its own timeout/cleanup and recovery strategy.
- An error flow receiving `Throwable` does not automatically know missing positions across the whole group without inspecting state/context.
- Retries on an adapter can re-inject an old message into a group, requiring duplicate handling.

### 17.3. Where Should Retries Live?

If a broker drops connection while delivering `#2` into the flow, retrying **delivery/reception of `#2`** can fill the gap. However, if the business handler for `#2` already committed and the ack was lost, retrying can cause duplicate side effects.

Distinguish:

1. Retrying **transport of a message into Resequencer**.
2. Retrying **persisting a message into the group store**.
3. Retrying **dispatching a message after release**.
4. Retrying **the business handler** after receipt.

These are distinct retry scopes with different safety profiles. Operations with side effects require idempotency keyed by a stable operation key.

### 17.4. Expiration Needs Actionable Investigation Data

A useful expiration record:

~~~text
event=RESEQUENCE_GROUP_EXPIRED
  shipmentId=SHIP-42
  runId=RUN-7
  expectedSequenceSize=4
  observedPositions=[1,3,4]
  missingPositions=[2]
  groupAgeMs=30000
  action=QUARANTINE
~~~

This is an application log schema, **not** data automatically emitted by every Resequencer configuration. If a group performed partial release, retain a snapshot of received/emitted positions so already-released positions are not falsely reported as missing.

## 18. Testing with Transports and Parallel Execution

### 18.1. Unit Tests Are Not Enough

`SequenceBuffer` unit tests prove the algorithm holds `#3` when `#2` is missing, but they do not verify:

- Header mapping across Kafka/HTTP/JMS.
- Spring Integration buffering and transactional message stores.
- Group expiry and cleanup when Resequencer actually runs.
- Broker behavior on redelivery or consumer restarts.
- Commit ordering of async downstream handlers.

Add integration/system tests matching every failure boundary that can occur.

### 18.2. An End-to-End Test Plan

~~~text
Producer
  -> send #3
  -> send #1
  -> send #2
  -> broker input (with correlation/sequence headers)
  -> Spring Integration Resequencer
  -> broker output (partitioned by shipment)
  -> ordered consumer
  -> business DB + observed outcomes
~~~

Verify:

1. After `#3`, the group buffer holds the message while the ordered consumer has not seen `#3`.
2. After `#1`, release behavior matches the configured full/partial profile.
3. After `#2`, the consumer observes exact sequence `1,2,3`.
4. On mid-flight restart, recovery matches store/ack contracts.
5. When `#2` is sent repeatedly, no duplicate side effects occur.
6. When `#2` never arrives, group expiration/recovery works properly.
7. When output goes to multiple partitions, per-shipment ordering holds.
8. When an input payload has a mismatched sequenceSize, it is not blindly merged into a valid group.

### 18.3. Do Not Use `Thread.sleep` to Guess Emission Timing

In async tests, use `CountDownLatch` or a `BlockingQueue` inside a test handler and `poll(timeout)` to await output. Do not assert immediately after `send` unless synchronous execution is confirmed. Latches can also simulate a slow second worker, always releasing in `finally` and shutting down executors cleanly.

### 18.4. Scenario for Testing Post-Release Commit Order

If business rules require ordered **commits**:

~~~text
Given:
  Resequencer has received #1, #2, #3.
  Downstream handler #1 is blocked on a latch.

When:
  #1 has not yet completed.

Then:
  #2 must not commit before #1 per contract.

When:
  Release the latch for #1.

Then:
  #1, #2, #3 commit sequentially by business version.
~~~

This test checks more than Resequencer—it also verifies **consumer/transaction configuration and business state**. If a multi-worker `ExecutorChannel` causes `#2` to commit before `#1`, Resequencer is not the only component needing fixes.

## 19. Observability: Where Is the Message?

### 19.1. Milestones to Record

~~~text
event=SEQUENCE_MESSAGE_RECEIVED
  group=SHIP-42/RUN-7 seq=3 total=4

event=SEQUENCE_MESSAGE_BUFFERED
  group=SHIP-42/RUN-7 seq=3 waitingFor=1

event=SEQUENCE_MESSAGE_RECEIVED
  group=SHIP-42/RUN-7 seq=1 total=4

event=SEQUENCE_PREFIX_RELEASED
  group=SHIP-42/RUN-7 positions=[1]

event=SEQUENCE_GAP_DETECTED
  group=SHIP-42/RUN-7 nextExpected=2 pending=[3]

event=SEQUENCE_GROUP_EXPIRED
  group=SHIP-42/RUN-7 missingPositions=[2,4]
~~~

These events are **suggested structured logging**. Under full-group release, `SEQUENCE_PREFIX_RELEASED positions=[1]` will **not appear** until the whole group completes; do not assume a partial-release log pattern applies to every flow.

### 19.2. Important Fields

| Field | Answers |
|---|---|
| `shipmentId`/`runId` | Which group and run does the message belong to? |
| `sequenceNumber`/`sequenceSize` | Which position arrived, and what is the valid total? |
| `nextExpected` | Which position is awaited next, if releasing by prefix? |
| `bufferedPositions` or `bufferedCount` | Which parts are still held? |
| `receivedPositions` | Which positions ever arrived, including released ones if tracked? |
| `groupCreatedAt`/`lastReceivedAt` | How old is the group, and how long since the last part arrived? |
| `groupState` | OPEN, WAITING, COMPLETED, EXPIRED, RECOVERING? |
| `policyVersion` | Which sequence/release rules applied? |
| `traceId` | Correlate logs across adapters/threads/services. |
| `errorCode` | Size mismatch, duplicate, timeout, store error? |

Avoid logging full event payloads containing customer data, shipping addresses, or tokens. Business IDs may also be sensitive; apply retention, masking, and access controls per operational policy.

### 19.3. Useful Metrics

| Illustrative Metric | Meaning |
|---|---|
| `resequencer_messages_received_total` | Inbound messages observed. |
| `resequencer_messages_buffered_total` | Times messages were buffered waiting. |
| `resequencer_messages_released_total` | Messages emitted in sequence. |
| `resequencer_groups_active` | Incomplete groups. |
| `resequencer_pending_messages` | Messages held in buffer/store. |
| `resequencer_group_age_seconds` | Age of open groups. |
| `resequencer_gap_wait_seconds` | Gap wait time or time until release. |
| `resequencer_groups_expired_total` | Groups expired / moved to recovery. |
| `resequencer_duplicates_total` | Duplicates detected. |
| `resequencer_invalid_headers_total` | Messages with invalid sequence/correlation metadata. |
| `resequencer_store_failures_total` | Group store read/write failures. |
| `ordered_handler_failures_total` | Downstream failures after message release. |

These are **application-suggested metric names**, not default meters in every Spring Integration version. Keep labels bounded (component, reason, environment); **never** use `shipmentId`, `runId`, `eventId`, or `traceId` as high-cardinality metric labels. Use logs/tracing or audit stores to inspect specific groups.

### 19.4. Message History Does Not Replace Sequence Auditing

Spring Integration Message History can show which components a message passed through when tracking is enabled. However, it does not automatically store:

- The **expected** set of sequence positions for every group.
- Which messages are currently buffered.
- Which gaps lack messages and how long they have waited.
- Downstream **commit** order.
- Retry/replay outcomes after a JVM crash.

When investigating a stuck group, combine **message headers, group state, message store, structured logs, tracing, and business outcomes**. A log line saying "passed Resequencer" is not enough to prove a business event completed.

## 20. Test Matrix for "Buffering Early-Arriving Messages"

| ID | Input / Scenario | Expected Outcome | Must Not Happen |
|---|---|---|---|
| RS-01 | Single message size=1, seq=1 | Emit exactly one message. | Waiting indefinitely. |
| RS-02 | Arrival `1,2,3` | Output `1,2,3`. | Reordering out of sequence. |
| RS-03 | Arrival `3,2,1` | Buffer `3`, `2`, then output `1,2,3`. | Emitting `3` before `1`. |
| RS-04 | Arrival `2,3,1` | Nothing emitted before `1`; final output in order. | Relying on arrival order. |
| RS-05 | Arrival `3,1,2`, full release | Wait until complete, then emit `1,2,3`. | Emitting prefixes against contract. |
| RS-06 | Arrival `3,1,2`, partial release | Can emit `1` on arrival, then `2,3`. | Emitting `3` while `2` is missing. |
| RS-07 | Two interleaved shipments | Correct order within each group. | Mixing SHIP-A messages into SHIP-B. |
| RS-08 | Same shipment, different runs | Two separate groups. | Old replay filling a new run's gap. |
| RS-09 | `sequenceNumber=0` | Reject malformed. | Treating position 0 as valid. |
| RS-10 | `sequenceNumber > sequenceSize` | Reject malformed. | Unbounded buffering. |
| RS-11 | Same group with conflicting sequenceSize | Error/quarantine. | Silently changing N. |
| RS-12 | Duplicate pending `#3` | Tested dedup/duplicate policy. | Counting as two positions. |
| RS-13 | Duplicate already-released `#1` | Idempotency/late policy. | Duplicate downstream side effects. |
| RS-14 | Same position, two eventIds with different payloads | Detect conflicting position. | Silent last-write-wins without audit. |
| RS-15 | Missing `#2` after receiving `1,3,4` | Gap detected. | Declaring group complete. |
| RS-16 | Deadline reached while gap remains | Expiration/recovery per policy. | Group living forever unobserved. |
| RS-17 | `#2` arrives after expiration | Late-arrival policy. | Reopening group as if no history existed. |
| RS-18 | Maximum sequence size exceeds app threshold | Input blocked. | Creating unbounded buffer. |
| RS-19 | Active groups exceed capacity | Backpressure/reject/recovery. | Silent drop. |
| RS-20 | Downstream handler throws when releasing `#2` | Processing error observed. | Blaming sorting or missing group. |
| RS-21 | Resequencer outputs to multi-worker executor | Separate commit-order contract test. | Assuming dispatch order equals commit order. |
| RS-22 | Filter drops `#2` before resequencer | Placeholder/release/expiration policy present. | Hanging forever undetected. |
| RS-23 | Transformer creates new payload | Sequence/correlation headers preserved. | Losing group context. |
| RS-24 | Splitter generates sequence headers | Resequencer reads right group/size. | Attaching another batch's group. |
| RS-25 | Nested split | Sequence/correlation scoped to right level. | Mixing parent/child levels. |
| RS-26 | Broker redelivery after crash | Recovery/dedup per contract. | Treating duplicate as a new event. |
| RS-27 | In-memory group store + crash | Limitation documented/tested. | Claiming buffer is durable. |
| RS-28 | Durable store + restart | Group recovered per transaction/ack policy. | Silently losing buffered messages. |
| RS-29 | Header mapping via Kafka/JMS/HTTP | Correlation/sequence round-trip intact. | Misordering due to dropped headers. |
| RS-30 | Gateway timeout while group is waiting | Caller status and group state clear. | Assuming timeout canceled all tasks. |
| RS-31 | Streaming sequence with unknown N | End-of-stream/window policy present. | Using fake infinite `sequenceSize`. |
| RS-32 | Sequence complete but downstream fails | Separate released vs. processed metrics. | Reporting business success just on group release. |
| RS-33 | Resequencer after slow Content Enricher | Measure gap/buffer/lookup latency. | Blindly increasing timeout. |
| RS-34 | Many groups missing first position | Capacity, group age, and cleanup monitored. | Unalerted OOM/disk exhaustion. |

### 20.1. Choosing the Right Test Level

| Test Level | What It Should Verify | What It Does Not Automatically Prove |
|---|---|---|
| **Unit test** | Waiting positions, buffering, duplicates, validation, gap/deadline math. | Framework routing/store works properly. |
| **Spring Integration test** | `.resequence()`, headers, correlation, group release, output channel. | Broker restart/serialization if no broker is used. |
| **Adapter integration test** | Header mapping, ACK, redelivery, partitioning, reply routing. | Business DB commit if mocked. |
| **System/load test** | Buffer capacity, hot groups, backpressure, failover, recovery. | Every production failure under all conditions. |

Do not turn every unit test into a slow end-to-end test. However, for risks that can break ordering or lose data, have at least one test at **the exact layer where that risk occurs**.

## 21. How to Diagnose a Resequencer Not Emitting Messages

Suppose `SHIP-42` has `#3` and `#4`, yet downstream receives nothing.

1. **Verify the goal:** is output supposed to start at `#1` or another position? Is full or partial release configured?
2. **Check input headers:** do `correlationId`, `sequenceNumber`, and `sequenceSize` have valid types/values and consistency?
3. **Check the group key:** did messages land in separate groups due to `runId`, tenant, policy version, or string encoding?
4. **Check the message store:** does the group exist, what positions are buffered, and has it expired?
5. **Check missing positions:** are `#1`/`#2` genuinely missing, or did a Filter/Router send them elsewhere?
6. **Check ingress adapters:** did the broker deliver `#1`/`#2`, and what happened with ack/delivery/retry?
7. **Check capacity:** is the group store or executor bottlenecked, slowing processing?
8. **Check release strategy:** wait-for-all vs. partial, or did custom timeout/expiration delete the group?
9. **Check downstream channels:** did Resequencer release, only for the output channel to have no subscribers, a stopped handler, or a full queue?
10. **Check late/duplicate handling:** did the group already complete/expire, and how are incoming messages handled under policy?
11. **Check business outcomes:** did the receiving handler commit, or was it only dispatched?
12. **Record the root cause:** add regression tests, metrics, and logs to distinguish gaps from delivery errors next time.

If a group is waiting for `#2`, **adding threads to the downstream handler** will not make `#2` appear. If messages already released and the handler failed, **increasing `groupTimeout`** will not fix the cause either. Locate the earliest point where the message disappeared.

## 22. Common Mistakes

| Misconception | Consequence | Right Practice |
|---|---|---|
| "Resequencer is a FIFO queue." | Cannot restore business order once arrival order scrambles. | Rely on correlation and sequence, not just enqueue order. |
| "Message #3 arrived first, so emit #3." | Breaks downstream state machine. | Buffer until a valid release condition is satisfied. |
| "Smallest timestamp is always first in sequence." | Clock skew / unsynchronized clocks. | Use reliable `sequenceNumber`/ordering contracts. |
| "`correlationId` is just `shipmentId` for all runs." | Replies/replays across runs mix together. | Include run/version in the group key when needed. |
| "`sequenceSize` can change per message." | Group cannot tell when it is complete. | Lock in a consistent sequence contract. |
| "Using `DirectChannel` means messages were processed." | Buffered, not yet released. | Observe milestones separately. |
| "Resequencer released means DB committed." | Downstream handler can still fail. | Test commits/order at consumer and transaction boundaries. |
| "Partial release is always on or always off." | Wrong semantics tested or unexpected latency. | Configure and verify against your framework version. |
| "A Filter dropping a part has no impact." | Group waits on a gap forever. | Deliberate placeholder/release/expected-set design. |
| "Message ID suffices for deduplication." | Rebuilt/redelivered messages get new IDs. | Business operation key, event ID, and version. |
| "A duplicate can fill a missing position." | Wrong release despite a real missing item. | Deduplicate by sequence position and identity. |
| "Group timeout equals Gateway timeout." | Caller times out while group lives, or vice versa. | Define deadlines per layer. |
| "Group store is durable by default." | State lost on restart. | Choose persistent store, ack/transaction policies. |
| "Resequencer prevents all concurrent processing." | Downstream executor commits out of order. | Per-group serialization/partitioning where needed. |
| "In-JVM ordering guarantees order over Kafka." | Consumer partitions can reorder. | Partition keys and consumer ordering contracts. |
| "Just grow the buffer endlessly." | Memory/disk exhaustion. | Capacity limits, group expiration, and backpressure. |
| "Message History lists what is missing." | Lacks expected input set and store state. | Gap inspector + group state/audit. |
| "Late events can reopen old groups automatically." | Reprocessing and duplicate side effects. | Tombstone/reconciliation/late-arrival policies. |
| "Missing event #2 means event #2 failed business validation." | Confuses delivery loss with business failure. | Distinguish not received, received, released, processed. |
| "Having an `errorChannel` alerts on all stuck groups." | Groups wait forever without raising an error event. | Configure timeout/expiration monitoring and recovery. |

## 23. Practice Exercises

1. **Fully reversed order:** use `SequenceBuffer` to send `#4, #3, #2, #1` in one group, `sequenceSize=4`. Assert nothing emits before `#1` and final output is `1,2,3,4`.
2. **Partial-prefix release:** send `#3, #1, #4, #2`. Record `ready` at each arrival and show how the gap affects `#3`.
3. **Wait-for-all:** modify the simulation so no prefix emits until the entire sequence arrives, then compare latency and buffered volume against partial release.
4. **Single message:** send `sequenceSize=1` and `sequenceNumber=1`; verify no extra waiting.
5. **Two interleaved groups:** send A#2, B#2, B#1, A#1; verify per-group ordering without enforcing global order.
6. **Replay across runs:** send events for the same shipment under `RUN-1` and `RUN-2`; prove group keys do not mix runs.
7. **Pending duplicate:** send `#3` twice before `#1` arrives. Design a deduplication or error policy by `eventId`/position.
8. **Already-released duplicate:** resend `#1` after its prefix emitted; verify no duplicate business output occurs.
9. **Wrong sequenceSize:** send `#2/3` then `#1/4` in the same group; verify the input/schema error is caught.
10. **Missing part:** supply `#1,#3,#4`, use `GapInspector` to detect missing `#2`, and evaluate before/after-deadline states with fixed timestamps.
11. **Late arrival:** simulate an expired group where `#2` arrives late; design quarantine or recovery without reopening a new group automatically.
12. **Memory limits:** generate many groups receiving `#2..#20` without `#1`; propose max active groups and a backpressure policy with metrics.
13. **Java DSL:** build `ShipmentResequencerConfiguration`, send `#3,#2,#1` via `ShipmentMessageFactory`, and verify `OrderedEventProbe`.
14. **Header test:** inspect `correlationId`, `sequenceNumber`, and `sequenceSize` on messages before Resequencer and after a mock adapter.
15. **Full/partial profiles:** create two test contexts with different release strategies; verify when `#1` is received for arrival `3,1,2` matches each profile's contract.
16. **Filter gap:** place a Filter dropping message `#2` before Resequencer, then design a placeholder or group expiration so it does not hang forever.
17. **Transformer:** convert payload to `NormalizedEvent` while preserving sequence metadata; verify Resequencer still emits properly.
18. **Splitter + Resequencer:** split a batch into three parts, process asynchronously to produce reversed output, then resequence to restore order if downstream requires it.
19. **Commit order:** emit ordered output to a multi-worker executor; block `#1` and observe whether `#2` can finish first. Propose proper per-group serialization.
20. **Message group store:** use a store compatible with your Spring Integration version; verify pending groups and expiration/cleanup per contract rather than looking only at the probe.
21. **Restart:** simulate a process restart after buffering `#3` and before `#1/#2` arrive. Compare in-memory vs. persistent group stores and replay correctness.
22. **Broker retry:** simulate handler `#2`'s side effect committing while the ack is lost; apply a business idempotency key to prevent duplicate updates.
23. **Monitoring:** implement `SEQUENCE_MESSAGE_BUFFERED`, `SEQUENCE_PREFIX_RELEASED`, and `RESEQUENCE_GROUP_EXPIRED` logs plus dashboards for pending groups and gap age.
24. **Security:** send a message with a huge `sequenceSize` or a `correlationId` spoofing another tenant. Block it before Resequencer, verifying allowlists and isolation.
25. **Unknown-N streams:** design a watermark or end-of-stream marker for an event stream, explaining why waiting on a fixed `sequenceSize` is impossible.

### 23.1. Practice Evaluation Criteria

A reliable implementation should answer:

- How does it hold early-arriving `#3` while `#1/#2` are still missing?
- Does the group key prevent mixing shipments, tenants, and replays?
- Is release order **full sequence** or **contiguous prefix**?
- Can duplicates or mismatches cause a group to emit wrongly?
- Do missing sequences have clear deadlines and recovery paths?
- Do buffers/stores have proper limits, durability, and cleanup?
- After release, does downstream actually need ordered commits?
- Do tests exercise real channels/adapters beyond unit algorithms?
- Are logs/metrics sufficient to locate stuck groups and missing positions?

## 24. Self-Check Questions

**Question 1:** For sequence `1,2,3`, message `#3` arrives first. Can it be emitted immediately?

**No**, if the contract requires starting at `#1`. `#3` must be buffered until the release condition is met.

**Question 2:** Does "early-arriving message" here mean a smaller timestamp than other messages?

**No.** It means a `sequenceNumber` ahead of the awaited position that **arrived before** its predecessors. Ordering should rely on trustworthy sequence/causal contracts, not timestamps alone.

**Question 3:** Does Resequencer guarantee group completion when `#2` is missing?

**No.** It requires timeout/expiration/recovery or an intentional gap-skipping policy. Infinite buffering will not recover a message that never arrives.

**Question 4:** Does a FIFO queue receiving `3,1,2` automatically emit `1,2,3`?

**No.** FIFO preserves queue arrival order; Resequencer uses sequence metadata to restore the desired order.

**Question 5:** How does Resequencer differ from Aggregator?

**Resequencer** reorders and re-emits individual messages by sequence; **Aggregator** combines multiple messages into one result per policy. Both can use groups/correlation, but their output contracts differ.

**Question 6:** Do `sequenceNumber=2` from two different shipments belong to the same group?

**No.** They must have separate correlation/group keys; `sequenceNumber` alone is insufficient.

**Question 7:** Should `sequenceSize=4` on the first message and `size=5` on a later message in the same group be accepted?

**No** under this lesson's finite-group contract. That is a metadata error to handle before release.

**Question 8:** How does arrival `3,1,2` behave differently under full-sequence release vs. partial-prefix release?

**Full release** holds the whole group until complete and then emits `1,2,3`. **Partial release** may emit `1` first, then `2,3` once the gap fills; configure and test against your framework version.

**Question 9:** With `DirectChannel`, if `send(...)` returns true after sending `#3`, has the ordered handler received `#3`?

**Not yet.** Resequencer may simply have buffered it; the handler has not been called.

**Question 10:** If `#1` already released and the broker redelivers it, does Resequencer automatically prevent duplicate business side effects?

**Not by default.** You need duplicate/replay policies and idempotency right where side effects occur.

**Question 11:** With a persistent `MessageGroupStore`, are all messages emitted downstream guaranteed exactly once?

**No.** Group state durability does not imply end-to-end exactly-once delivery across brokers, output channels, and databases.

**Question 12:** After Resequencer sits a three-worker `ExecutorChannel`. Is commit order guaranteed to match release order?

**No.** You must add per-group sequential processing/commit constraints if business rules require it.

**Question 13:** A Filter drops message `#2` in a three-part group. Does Resequencer know automatically it was validly skipped?

**No.** You must design placeholders, expected-set/release policies, or timeouts/recovery.

**Question 14:** When a Gateway times out and `#2` arrives afterward, is the group guaranteed to cancel and workers to stop?

**No.** Gateway timeout, group timeout, and downstream processing have separate lifecycles.

**Question 15:** Must `sequenceNumber` be kept in both payload and headers?

**Not mandatory in every design**. However, if business lineage across adapters is needed, having sequence in the payload can help; Resequencer must receive metadata per framework API and mapping rules. Both copies must stay consistent.

**Question 16:** Can `MessageHeaders.ID` replace `eventId` for idempotency?

**It should not.** Messages can be recreated across adapters/retries with different IDs; the key should reflect the same business operation.

**Question 17:** A group has a complete sequence, yet downstream fails on `#2`. Can the whole workflow be marked successful?

**No.** Group release is only one milestone; business processing/commit must be tracked separately.

**Question 18:** When many groups lack `#1`, what prevents memory exhaustion?

Capping group and pending message counts, TTL/expiration, durable stores when needed, backpressure, monitoring, and recovery policies—not endlessly increasing heap size.

## 25. Conclusion

**Buffering early-arriving messages** is a core responsibility of **Resequencer**: when messages of the same sequence arrive out of order, messages ahead of missing positions must be **held**, then **emitted in sequence** once conditions are met. To do this safely, a system needs a **proper group key, consistent sequence headers, explicit release strategy, buffer limits, timeouts/expiration, and handling for duplicates and late arrivals**.

In Spring Integration, Resequencer supports grouping and reordering messages; however, **full-group release** and **partial-prefix release** carry different semantics. Emitting in order does not automatically guarantee downstream processing, commits, or acks happen in order, especially across distributed executors/brokers. Persistent message stores help recover state but do not provide exactly-once delivery on their own; combine idempotency, transactions, and correlation.

For the `SPRING_INTEGRATION_PATTERN` module, a solid practice workflow is **unit testing buffer logic → integration testing Resequencer and headers → adapter testing for transport → system testing for timeouts/retries/restarts**. Coordinate Router, Filter, Transformer, Splitter, Aggregator, Gateway, error channels, and tracing by contract so operators can always answer: **"Which messages arrived early, which positions are awaited, when were they released, and how far has downstream processed?"**