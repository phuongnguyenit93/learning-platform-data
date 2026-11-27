# Testing That a Bridge Does Not Lose Messages

## 1. Problem: Adding a Bridge to Connect Two Channels, Yet Some Events Vanish

An application receives order events, routes them through a buffer channel, and invokes a handler to update state:

~~~text
Producer
  → orders.in
  → Bridge
  → orders.process
  → OrderEventHandler
  → Database
~~~

In development, a simple test sends one message and sees the handler invoked:

~~~java
assertTrue(inputChannel.send(message));
~~~

Yet in production, harder questions arise:

- If the downstream channel has no subscriber, is the message lost or is an error reported back upstream?
- If the Bridge is polling a `QueueChannel`, a message is pulled out and the handler throws—who retains responsibility for retrying?
- If connected to an `ExecutorChannel`, `send()` returns before the business method runs: does a crash in between lose the event?
- When reprocessing after broker redelivery, how do you distinguish a **lost message**, a **slow message**, and a **twice-executed message**?
- If the output has multiple subscribers or its channel type changes, does the one-to-one forwarding assumption still hold?
- If upstream ACKs before downstream durably persists, can the Bridge save the event across a restart?

**This lesson teaches how to test the Bridge's true contract as well as the gap between message forwarding and durable delivery guarantees.** These are two distinct levels; you should never treat a happy-path integration test as proof of “zero message loss ever.”

~~~mermaid
flowchart LR
    PUB["Producer"] --> IN["Input channel"]
    IN --> BR["Bridge endpoint"]
    BR --> OUT["Output channel"]
    OUT --> H["Business handler"]
    H --> DB["Durable business state"]
    BR -. "Forwarding success" .-> OBS["Metrics / assertions"]
    DB -. "Completion proof" .-> OBS
~~~

This lesson belongs to the **Bridge** chapter of the **SPRING_INTEGRATION_PATTERN** module: learning to implement Enterprise Integration Patterns with **Spring Integration**, building loosely coupled and extensible message flows, practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing processing branches.

**Learning outcomes:** understand the role of `BridgeHandler`/DSL `.bridge()`, write tests for forwarding and message contents, verify error paths across `DirectChannel`/`QueueChannel`/`ExecutorChannel`, identify data-loss windows around ACKs/transactions, design retries/idempotency, and build a repeatable fault-injection test suite.

## 2. What Does a Bridge Do in Spring Integration?

A **Bridge** connects a source message channel to a target channel. It is appropriate when **no payload transformation is needed**, no content-based routing decision is needed, and no business method needs to be invoked.

~~~text
inputChannel → Bridge → outputChannel
~~~

In Spring Integration, a Bridge endpoint can be configured with Java DSL `.bridge()` or with `BridgeHandler` wired to appropriate input/output channels.

A Bridge **does not by itself**:

1. Turn an in-memory channel into a persistent queue.
2. Create a distributed transaction across a broker and a database.
3. Infinitely retry a message when downstream fails.
4. Preserve completion order if the target uses a concurrent executor.
5. Verify authorization, business idempotency, or payload schema.
6. Prove an external receiver committed merely because sending to a channel completed.

**It forwards messages according to the semantics of the endpoint and connected channels.** Zero-message-loss guarantees depend especially on the source, target, acknowledgments, error paths, and handoff durability.

## 3. Bridge vs. Router, Transformer, Service Activator, and Channel Adapter

| Component | Primary Question | Typical Output |
|---|---|---|
| **Bridge** | How do we connect two channels without processing content? | Forwarded message |
| **Transformer** | How should the payload or message representation change? | Transformed payload/message |
| **Filter** | Should this message continue? | Pass through or reject/discard |
| **Router** | Which branch should this message take? | Selects one or more channels per policy |
| **Service Activator** | Which business method runs? | Method result, possibly with side effects |
| **Channel Adapter** | How do we connect to an external transport/source/target? | One-way inbound/outbound integration |
| **Gateway** | Does the caller need request–reply and response correlation? | Contracted request and reply |

Example:

~~~text
Kafka inbound adapter
  → orders.in
  → Bridge
  → orders.process
  → Service Activator
  → DB commit
~~~

The Kafka adapter receives from the broker; the Bridge connects channels; the Service Activator executes business logic. **Do not call the Bridge the Kafka consumer** if it merely receives messages produced by the adapter; Kafka offset commits belong to the listener/container policy.

The name **Messaging Bridge** in Enterprise Integration Patterns is also sometimes used for **connecting two messaging systems**. In this lesson, the focus is the **Spring Integration Bridge endpoint forwarding messages between Spring channels**. Connecting two brokers/processes still requires inbound/outbound adapters, protocols, ACKs/retries, and durable handoffs.

## 4. “Zero Message Loss” Must Have a Verifiable Definition

We need at least four invariants, depending on the business contract:

| Invariant | Meaning | Appropriate Evidence |
|---|---|---|
| **Integrity** | Payload and required business headers are not corrupted | Compare message fields |
| **No unintended drop** | Valid messages do not vanish silently along an unhandled failure path | Received IDs, error/recovery IDs |
| **Durable responsibility** | When the source is ACKed, work has completed or been durably handed off | DB commits, durable store/queue, and crash tests |
| **No duplicate effect** | Retries/redeliveries do not cause duplicate business side effects | Unique constraints, inbox, committed results |

For a measurement window of N durably accepted logical messages:

\[
N_{\text{accepted}} =
N_{\text{completed}} + N_{\text{durable pending}}
+ N_{\text{durable terminal failures}}
\]

This is a **mutually exclusive state-accounting equation**, not a built-in Spring Integration metric. Ensure a logical message is never counted twice, and only count a message as `accepted` after a clearly defined milestone.

**Do not use `receivedCount == successCount` as a universal invariant for systems with retries, quarantine, or legitimate in-flight work.** Track the state of **each individual business message ID**.

## 5. Scoping Tests: Forwarding Differs from Business Completion

Two claims are frequently confused:

1. **Bridge forwarding correctness:** a message travels from the input channel to the output channel carrying the expected payload and headers.
2. **End-to-end delivery correctness:** a message retains a durable processing or recovery path across crashes/timeouts and produces the right business outcome.

A simple unit/integration test can prove (1) within a given topology. To prove (2), you must test **source ACKs, store durability, transaction boundaries, downstream failures, restarts, and retries**.

~~~text
Input DirectChannel
  → Bridge
  → Output QueueChannel in memory

Test: send() → receive() == original payload
  ✔ Proves normal forwarding.
  ✘ Does not prove messages survive a process restart.
~~~

**Do not label a Bridge “exactly-once.”** It does not control remote brokers, databases, and retry outcomes on its own.

## 6. Bridge and Semantics of Payload, Headers, and Message Identity

When a Bridge is used in its proper role, verify:

- The payload arrives at the destination with a compatible value/type.
- **Essential business headers** such as `eventId`, `correlationId`, and `tenantScope` remain intact.
- The destination receives the exact number of **logical messages**.
- No unintended serialize/deserialize step drops fields or mangles types.
- If the flow uses reply/error metadata, it remains valid within the supported scope.

Do not base correctness solely on **Spring's `MessageHeaders.ID` remaining identical byte-for-byte**. Some endpoints, transformations, header enrichers, or adapter boundaries can rebuild messages and change framework-level IDs/timestamps. The **business event ID in the payload/header** is the stable identifier across retries, transports, and replays.

Example message:

~~~java
Message<String> event = MessageBuilder
    .withPayload("ORDER_CREATED:O-501")
    .setHeader("eventId", "EV-501")
    .setHeader("businessCorrelationId", "tenant-a|O-501")
    .setHeader("schemaVersion", 1)
    .build();
~~~

Tests should assert that `EV-501`, correlation, and schema version match at the output, rather than relying on two framework IDs as comparison keys.

## 7. Java DSL Example: Connecting Input and Output with a Bridge

An isolated, easy-to-test configuration:

~~~java
@Configuration
@EnableIntegration
class BridgeFlowConfiguration {

    @Bean("orders.bridge.input")
    MessageChannel bridgeInput() {
        return new DirectChannel();
    }

    @Bean("orders.bridge.output")
    PollableChannel bridgeOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow ordersBridgeFlow() {
        return IntegrationFlow
            .from("orders.bridge.input")
            .bridge()
            .channel("orders.bridge.output")
            .get();
    }
}
~~~

Here:

- Input is a `DirectChannel`, dispatching synchronously to the Bridge handler.
- The Bridge forwards to the output channel.
- The `QueueChannel` output allows integration tests to call `receive(timeout)` to inspect results.

This is an **intentional test topology**, not a recommendation to use an in-memory `QueueChannel` as a durable production queue. Requires Spring Integration dependencies, imports, and the corresponding Spring test context; verify DSL APIs against your actual version when compiling.

## 8. Happy-Path Test: One Message Reaches the Right Output Channel

JUnit 5 example with Spring test context:

~~~java
@SpringJUnitConfig(BridgeFlowConfiguration.class)
class BridgeFlowTest {

    @Autowired
    @Qualifier("orders.bridge.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.bridge.output")
    PollableChannel output;

    @Test
    void forwardsPayloadAndBusinessHeaders() {
        Message<String> sent = MessageBuilder
            .withPayload("ORDER_CREATED:O-501")
            .setHeader("eventId", "EV-501")
            .setHeader("businessCorrelationId", "tenant-a|O-501")
            .setHeader("schemaVersion", 1)
            .build();

        assertTrue(input.send(sent));

        Message<?> received = output.receive(1_000);
        assertNotNull(received);
        assertEquals("ORDER_CREATED:O-501",
            received.getPayload());
        assertEquals("EV-501",
            received.getHeaders().get("eventId"));
        assertEquals("tenant-a|O-501",
            received.getHeaders().get("businessCorrelationId"));
        assertEquals(1,
            received.getHeaders().get("schemaVersion"));
    }
}
~~~

**The test sample requires the corresponding JUnit/Spring imports.** It verifies input → Bridge → output **within a single running JVM**. No broker, database, retry, or process crash is involved, so **never claim this proves durability**.

## 9. Testing No Extra Messages: Zero Duplicates on the Normal Path

After receiving one message, confirm the output queue does not hold an unintended duplicate:

~~~java
@Test
void oneInputHasOneOutputWithoutRetry() {
    Message<String> sent = MessageBuilder
        .withPayload("ORDER_CREATED:O-501")
        .setHeader("eventId", "EV-501")
        .build();

    assertTrue(input.send(sent));

    Message<?> first = output.receive(1_000);
    assertNotNull(first);
    assertEquals("EV-501",
        first.getHeaders().get("eventId"));

    Message<?> unexpected = output.receive(100);
    assertNull(unexpected);
}
~~~

The test above should use a **Spring test instance/context whose queue is cleaned** before each case, or an isolation strategy; if an earlier test leaves messages behind, duplicate assertions can break. `receive(100)` only proves **no second message arrived during that observation window**, not that a late duplicate cannot arrive 10 minutes later or after a restart.

## 10. Testing N Messages: Compare ID Sets, Not Just Counts

Checking 200 independent events:

~~~java
@Test
void allLogicalMessagesArriveExactlyOnceInHealthyFlow() {
    int total = 200;
    Set<String> expected = new HashSet<>();

    for (int i = 0; i < total; i++) {
        String id = "EV-" + i;
        expected.add(id);
        assertTrue(input.send(
            MessageBuilder.withPayload("event:" + i)
                .setHeader("eventId", id)
                .build()));
    }

    Map<String, Integer> observedCounts = new HashMap<>();
    for (int i = 0; i < total; i++) {
        Message<?> received = output.receive(1_000);
        assertNotNull(received);
        String id = (String)
            received.getHeaders().get("eventId");
        observedCounts.merge(id, 1, Integer::sum);
    }

    assertEquals(expected, observedCounts.keySet());
    assertTrue(observedCounts.values().stream()
        .allMatch(count -> count == 1));
    assertNull(output.receive(100));
}
~~~

Checking only `receivedCount == 200` is insufficient: `EV-19` could be lost and `EV-20` duplicated, still totaling 200. **Comparing ID sets plus multiplicity** catches both loss and duplication.

This is still only a **healthy in-memory forwarding** test, not an exactly-once guarantee when producers/brokers redeliver. Use reasonable timeouts so tests do not hang indefinitely if a message is lost.

## 11. Testing Payload Type and Required Header Preservation

A Bridge is not a Transformer. If the source sends:

~~~java
record OrderEvent(
    String eventId,
    String orderId,
    int version,
    String type
) {}
~~~

The output should preserve the event contents per contract:

~~~java
OrderEvent original =
    new OrderEvent("EV-501", "O-501", 3, "CREATED");

assertTrue(input.send(MessageBuilder
    .withPayload(original)
    .setHeader("tenantScope", "tenant-a")
    .build()));

Message<?> received = output.receive(1_000);
assertNotNull(received);
assertInstanceOf(OrderEvent.class, received.getPayload());
assertEquals(original, received.getPayload());
assertEquals("tenant-a",
    received.getHeaders().get("tenantScope"));
~~~

With an immutable record, `equals()` compares component values. If a payload is a mutable POJO, the output holding the same object reference **does not prove it wasn't mutated after sending**. Use immutable DTOs or snapshot fields when testing; transport serialization boundaries may create copies and change representation.

## 12. Testing Message Ordering: Defining the Right Scope

With a **DirectChannel → Bridge → QueueChannel** path, a test sending sequentially on one thread and reading the queue sequentially can assert output order:

~~~java
@Test
void sequentialBridgePreservesArrivalOrderInTestTopology() {
    for (int i = 0; i < 20; i++) {
        assertTrue(input.send(MessageBuilder
            .withPayload(i)
            .setHeader("eventId", "EV-" + i)
            .build()));
    }

    for (int i = 0; i < 20; i++) {
        Message<?> item = output.receive(1_000);
        assertNotNull(item);
        assertEquals(i, item.getPayload());
    }
}
~~~

**Do not generalize this conclusion to all channel types.** If the output after the Bridge is a multithreaded `ExecutorChannel`, handler completion can reorder; Kafka provides log ordering per partition only, not global business ordering.

Ordering must be tested at **the point where side effects actually commit**, not just when the Bridge forwards.

## 13. Risk Matrix by Input/Output Channel Type

| Topology | Normal Behavior | Failure Risks |
|---|---|---|
| `DirectChannel → Bridge → DirectChannel` | Synchronous dispatch on call stack | No default durability; errors can unwind to sender |
| `DirectChannel → Bridge → QueueChannel (memory)` | Puts into buffer, consumer reads later | Queue lost on process death; send success is not business success |
| `QueueChannel → poller → Bridge → DirectChannel` | Poller removes message from queue and forwards | Gap between removal and handler completion |
| `QueueChannel (persistent) → poller → Bridge → handler` | Content can reside in durable store | Needs transaction/recovery if receive/remove and downstream fail |
| `DirectChannel → Bridge → ExecutorChannel` | Enqueues into executor and returns control | In-memory task lost on crash; completion may reorder |
| `Broker adapter → Bridge → business handler` | Transports message into `IntegrationFlow` | ACK/offset must align with durable processing |
| `Bridge → outbound broker adapter` | Sends to external broker | Publish confirm and upstream ACK are not atomic by default |

**Naming the Bridge class alone is not enough to infer delivery guarantees.** Tests must explicitly state channel types, thread boundaries, message stores, source ownership, and committed completion points.

## 14. DirectChannel: Synchronous Execution, Yet Not Crash-Durable

With:

~~~text
Producer thread
  → DirectChannel(input)
  → Bridge
  → DirectChannel(output)
  → Handler
~~~

In a standard synchronous topology, if the output handler throws an exception, it can propagate back to the `send()` caller. This is an **opportunity for the caller/inbound adapter to perform recovery**, not a retry guarantee by itself.

If the producer does:

~~~java
try {
    input.send(message);
} catch (Exception failure) {
    logger.warn("event dropped");
}
~~~

then **the caller itself may have dropped responsibility** by swallowing the exception without durable retries. `DirectChannel` cannot rescue a message that was neither persisted nor resent.

**Tests must examine failure propagation and recovery policies**, not just happy-path sends.

## 15. Testing an Output Channel with No Subscriber

An isolated test configuration:

~~~java
@Configuration
@EnableIntegration
class BrokenBridgeConfiguration {

    @Bean("broken.input")
    MessageChannel brokenInput() {
        return new DirectChannel();
    }

    @Bean("broken.output")
    MessageChannel brokenOutput() {
        // Intentionally do not register a subscriber.
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow brokenBridge() {
        return IntegrationFlow.from("broken.input")
            .bridge()
            .channel("broken.output")
            .get();
    }
}
~~~

Test:

~~~java
@SpringJUnitConfig(BrokenBridgeConfiguration.class)
class BrokenBridgeTest {

    @Autowired
    @Qualifier("broken.input")
    MessageChannel input;

    @Test
    void missingSubscriberMustNotBeTreatedAsSuccess() {
        Message<String> message = MessageBuilder
            .withPayload("EV-501")
            .setHeader("eventId", "EV-501")
            .build();

        assertThrows(
            MessagingException.class,
            () -> input.send(message));
    }
}
~~~

On a synchronous `DirectChannel` with the default dispatcher, having no subscriber typically causes a dispatch failure in the `MessagingException` hierarchy. **Verify the exact exception/cause for your Spring Integration version**.

This test assumes a condition: the caller has **not durably ACKed yet**; if the caller already ACKed before sending into the Bridge, an exception will not undo an improperly confirmed source record.

## 16. Testing a Downstream Handler Throwing an Exception

A handler that has already received a message can also fail:

~~~java
@Bean
IntegrationFlow failingDownstreamFlow() {
    return IntegrationFlow.from("bridge.fail.input")
        .bridge()
        .handle(
            String.class,
            (payload, headers) -> {
                throw new IllegalStateException(
                    "SIMULATED_DB_UNAVAILABLE");
            })
        .get();
}
~~~

With a synchronous `DirectChannel`, the caller test:

~~~java
assertThrows(MessagingException.class,
    () -> failingInput.send(
        MessageBuilder.withPayload("EV-501").build()));
~~~

**This flow requires an input channel `bridge.fail.input` in the test context.** Spring may wrap handler exceptions in a messaging wrapper; do not treat raw exception message text as a strict contract. When adding advice/error handlers or switching to async, update the expected exception path accordingly.

To prove **zero message loss**, also verify the caller/adapter **does not commit progress** before durable recovery and that the message can retry per policy.

## 17. QueueChannel: Poll/Receive Can Drop Processing Responsibility

An in-memory `QueueChannel`:

~~~text
Producer sends EV-501 → QueueChannel (memory)
Poller receives EV-501 → removed from queue
Bridge forwards → handler throws
Process crashes
~~~

Without a transactional message store, durable retry queue, or requeue/recovery protocol, **the message does not automatically reappear**. Polling means the consumer actively takes the item; **removing from the queue** differs from **succeeding in business processing**.

~~~mermaid
sequenceDiagram
    participant Q as QueueChannel
    participant P as Poller
    participant B as Bridge
    participant H as Handler
    P->>Q: receive()
    Q-->>P: EV-501 removed
    P->>B: forward(EV-501)
    B->>H: process(EV-501)
    H--xB: failure
    Note over P,H: Without recovery, responsibility may be lost
~~~

**A `QueueChannel` is not a durable message broker just because it has “queue” in its name.** Check whether it is memory-backed or persistent-store-backed, and whether transactions span receive/remove together with downstream processing.

## 18. A Pollable Source Bridged Outward Requires a Poller

Example where the source is a `QueueChannel`:

~~~java
@Bean("bridge.pollable.source")
PollableChannel pollableSource() {
    return new QueueChannel();
}

@Bean("bridge.pollable.target")
MessageChannel pollableTarget() {
    return new DirectChannel();
}

@Bean
IntegrationFlow bridgePollableChannel() {
    return IntegrationFlow
        .from("bridge.pollable.source",
            c -> c.poller(Pollers.fixedDelay(200)
                .maxMessagesPerPoll(5)))
        .bridge()
        .channel("bridge.pollable.target")
        .get();
}
~~~

This is the **polled Bridge endpoint pattern when the source is a pollable channel**. Do not register another flow consuming from `bridge.pollable.source` if the test expects a single consumer.

**API note:** check Java DSL signatures `IntegrationFlow.from(..., c -> c.poller(...))`/`Pollers` against your actual Spring Integration version; the conceptual requirement is that a pollable source needs an explicit poller/scheduler.

With this in-memory source there is still **no durability**. You can configure transaction advice/retry/error channel on the poller, yet you must verify it against a store/transaction manager rather than inferring durability from `fixedDelay` alone.

## 19. Testing the Real Poller Without Stealing Messages via `receive()`

Test topology:

~~~text
source QueueChannel
  → bridge poller
  → target DirectChannel
  → capture handler
~~~

Steps:

1. Send `EV-501` to **source QueueChannel**.
2. Wait for the **capture handler after the Bridge** to observe `eventId`.
3. Assert payload and business headers are not corrupted.
4. Assert no duplicates arrive within the test window.
5. Ensure no other test shares the same source and poller.

**Never send to the source and then call `source.receive()` to verify**: doing so can **steal the message from the poller**. Observe the target or durable downstream state instead.

Wait using latches, bounded Awaitility, or a test sink; never use a fixed `Thread.sleep(5000)` assuming the poller ran.

## 20. Testing Poller Failure: Is a Dequeued Message Recovered?

Fault injection:

~~~text
Source QueueChannel holds EV-501.
Poller receives EV-501.
Bridge forwards to handler.
Handler throws SIMULATED_DB_DOWN.
Poller error path runs.
~~~

**Never assume EV-501 is still in `QueueChannel`.** With an un-transacted in-memory queue, it has already left the source. Proper tests must verify the failure policy:

- Durable transactional receive/rollback makes the message available again per store semantics.
- Durable retry/DLQ recoverer writes the message to a recovery destination before releasing the source.
- If neither exists, **a no-loss test must fail**, even if an error channel logged the error.

A logged error **does not mean responsibility for processing the message was preserved**.

## 21. A Persistent QueueChannel Does Not Create Distributed Exactly-Once

A `QueueChannel` backed by a persistent message group store helps preserve data across restarts under proper configuration and test conditions. However:

~~~text
DB-1: MessageGroupStore stores EV-501
DB-1: Poller removes EV-501
DB-2: Business handler writes OrderCreated
~~~

If the removal in DB-1 commits before the write in DB-2, a crash between the two steps can still lose work. If DB-2 commits while the removal rolls back, retries can duplicate unless idempotent.

**To make receive/remove and business writes atomic**, ensure the store and handler share the same transaction manager/resource, or use appropriate recovery/outbox patterns. Two separate databases do not automatically join a single JDBC transaction.

A persistent store makes the buffer durable; it **does not replace designing commit boundaries for the whole workflow**.

## 22. ExecutorChannel: `send()` May Only Mean In-Memory Enqueue

~~~text
Producer
  → DirectChannel
  → Bridge
  → ExecutorChannel
  → worker executes handler later
~~~

If `ExecutorChannel` accepts the task, upstream `send()` can finish **before the handler runs**. A JVM crash between enqueue and execution can lose the in-memory task.

~~~mermaid
sequenceDiagram
    participant U as Upstream
    participant B as Bridge
    participant E as ExecutorChannel
    participant W as Worker
    U->>B: send(EV-501)
    B->>E: enqueue(EV-501)
    E-->>B: accepted to executor
    B-->>U: send returns
    Note over E,W: Process crashes before worker runs
~~~

**Never use `send() == true` as proof that the downstream handler committed.** If a source broker ACKs at this moment, messages can be lost because the worker lacks durable ownership.

## 23. Testing Async Handoff with Latches Instead of Arbitrary Sleeps

A test plan:

1. Create an `ExecutorChannel` with a test executor capable of holding tasks before execution.
2. Send a message through the Bridge.
3. Verify upstream `send()` returned/was accepted.
4. Before releasing the latch, assert the business handler has not executed yet.
5. Release the latch and wait for the handler to run and commit.
6. Simulate shutdown before step 5 in a separate test to check whether a durable handoff exists.

~~~text
send accepted != business completed
~~~

With an in-memory `ExecutorChannel` lacking a durable queue, a crash test proves **the design does not meet no-loss requirements**, not that the Bridge itself is buggy.

## 24. A Bridge Is Not a Persistent Work Queue by Default

| Case | Is a Bridge Reasonable? | What Else Is Needed to Avoid Losing Work |
|---|---|---|
| DirectChannel to DirectChannel in a sync request | Yes | Propagate failure so caller retries |
| Lightweight in-JVM buffering | Yes | Accept loss or replace with durable store |
| Durable broker source, ACK after commit | Yes | Offset/ACK boundary and idempotency |
| Multi-minute async task | Bridge is only one hop | Durable work queue + status/retry |
| Bridging two external brokers | Possible + adapters | Publish confirms, source ACK, dedupe |
| Payment/Inventory mutation | Bridge does not solve side effects | Stable command ID, remote idempotency, reconcile |

**A Bridge does not implement Kafka, AMQP, or HTTP ACK protocols.** That responsibility belongs to adapters, containers, outbox/inbox tables, and domain services.

## 25. Kafka Inbound Adapter → Bridge: Offset Commit Is a Critical Decision

A flow:

~~~text
Kafka orders.events
  → Kafka inbound adapter
  → bridge.input
  → Bridge
  → business.handler
  → Database
~~~

Suppose the handler writes a projection. Two failure windows exist:

~~~text
Case A: source offset committed BEFORE DB commit
  Kafka record EV-501 delivered
  offset committed
  DB unavailable, handler fails
  → source cursor advanced; risk of lost business work

Case B: DB commits BEFORE source offset commit
  Kafka record EV-501 delivered
  DB commits event + projection
  process crashes before offset commit
  → record may redeliver; business idempotency required
~~~

**A generally safer design under at-least-once:** durable business commit before confirming source progress, combined with an idempotent consumer. Still, verify Kafka ACK modes, consumer transactions, containers, and async worker boundaries against your exact configuration.

A Kafka offset is **not** a stable business event ID across republishing/repartitioning. Put `eventId` or a logical operation ID in the payload/wire contract; record `topic + partition + offset` as metadata for audit/replay.

## 26. Testing Kafka: Crashes Before and After Commit

Design two tests using a dedicated test broker:

| Failure Timing | Expected After Restart | Evidence |
|---|---|---|
| Before DB commit, offset uncommitted | Event is reprocessed | Final business effect count = 1 |
| After DB commit, offset uncommitted | Redelivery may occur | Inbox flags duplicate; no second write |
| After source ACK and before durable handoff | **Must catch loss window** if topology allows it | Message absent from DB/queue/retry store |
| After durable handoff, before source ACK | Duplicate may arrive | Duplicate detected by business ID |

Procedure:

1. Use a test Kafka broker with a dedicated topic/consumer group.
2. Send a fixed `eventId`.
3. Place fault-injection hooks **before and after DB commit**, not merely stubbing a mock return.
4. Stop the consumer process/container at a controlled point.
5. Restart the same logical consumer group.
6. Compare `eventId` across the database, inbox, and source progress.
7. Assert **zero lost processing responsibility** and **zero duplicate business effects**.

This test must use an `OrderEventHandler` with real transactions/idempotency or a well-specified durable store fake. An in-memory test-only `QueueChannel` cannot prove broker recovery semantics.

## 27. AMQP/JMS Inbound → Bridge: Different Offsets, Same ACK Problem

RabbitMQ/JMS acknowledge and redeliver differently from Kafka:

~~~text
Broker delivery
  → inbound channel adapter
  → Bridge
  → Service Activator
  → durable business store
  → broker ACK according to container policy
~~~

If the consumer ACKs before an async worker persists business state, a crash can lose work. If business state commits and the connection drops before ACK, redelivery can occur.

Test scenarios:

- Worker crashes before ACK → source broker can redeliver per transport semantics.
- Business committed yet ACK fails → idempotency blocks duplicate effects.
- Handler throws a permanent error → routed to DLQ/quarantine after durable recovery.
- DLQ publish fails → never silently ACK/drop the source message.
- Message content/headers map accurately through the inbound adapter; never trust raw untrusted headers for authorization.

**Do not copy the Kafka offset model directly onto RabbitMQ/JMS.** Queue delivery ACKs, prefetch, requeue, dead-lettering, and provider transactions differ from group offsets; test the actual running adapter/container.

## 28. Bridge Between Two External Brokers: Transport Adapters Needed on Both Sides

Diagram:

~~~mermaid
flowchart LR
    KA["Kafka topic A"] --> IA["Kafka inbound adapter"]
    IA --> IN["Input channel"]
    IN --> B["Bridge"]
    B --> OUT["Output channel"]
    OUT --> OA["AMQP outbound adapter"]
    OA --> RB["RabbitMQ queue B"]
~~~

In this topology, the `Bridge` only connects Spring channels. **Consuming Kafka records** and **publishing AMQP messages** are handled by the two adapters.

Failure window:

~~~text
1. Kafka record read.
2. Bridge forwards to outbound adapter.
3. RabbitMQ stores message and confirms publish.
4. Process crashes before Kafka offset commit.
5. Kafka event redelivered; RabbitMQ message may publish twice.
~~~

Conversely, if Kafka commits before RabbitMQ's durable confirm, a crash can **lose the message at the destination**. There is no default shared local transaction across two brokers.

**Practical design:** at-least-once transport handoff + deduplication at the destination, or a persistent outbox/staging store for coordination and recovery. A “Message Bridge” does not execute atomic commits across two message brokers on its own.

## 29. Testing Outbound Publisher Confirms and Source Progress

When a Bridge sends to an outbound broker adapter:

1. Inject failure **before the publisher sends**.
2. Inject failure **after the outbound broker stores**, before confirmation.
3. Inject failure **after confirmation**, before source ACK.
4. Count distinct business IDs at the destination.
5. Verify source messages **are not confirmed as done** without a durable handoff.
6. Verify duplicate deliveries are detected and create no duplicate business side effects.

A publish API returning a `Future` or success callback may indicate broker delivery per producer config; it **does not prove the target consumer finished business processing**.

**Define “durably handed off” according to the specific transport.** For instance, RabbitMQ publisher confirms and Kafka producer acknowledgments provide guarantees determined by broker/producer settings; when strict guarantees are required, check durability/replication/availability settings as well.

## 30. Transactional Outbox: Preserving Messages Without Atomic Cross-System Commits

A pattern:

~~~text
BEGIN local DB transaction
  update order state
  insert outbox event EV-501
COMMIT

Outbox publisher
  → Bridge / outbound adapter
  → external broker
  → mark outbox delivered after acceptable confirmation
~~~

If the publisher crashes before marking sent, the event may be published again. **An outbox prioritizes zero lost work**, yet still requires consumer idempotency because duplicate deliveries can occur.

What to test:

- Outbox record exists if the business transaction committed.
- Business rollback → no separate “successful” outbox event exists.
- Outbound broker down → outbox stays pending without dropping.
- Publish confirmed then crash → replay may duplicate; receiver deduplicates.
- Schema change/redeploy → pending outbox rows still decode and send properly.

If a Bridge merely connects an in-memory `QueueChannel` to an outbound adapter, it **does not replace a transactional outbox**.

## 31. Inbox/Idempotency: Blocking Duplicate Side Effects After Replay

A business message:

~~~java
record OrderEvent(
    String tenantId,
    String eventId,
    String orderId,
    int aggregateVersion,
    String type
) {}
~~~

An inbox design:

~~~sql
CREATE TABLE processed_order_event (
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    payload_fingerprint VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);
~~~

Within one local transaction:

1. Validate/authorize event and tenant from trusted context.
2. Claim event ID with the unique constraint.
3. On duplicate, compare payload fingerprint against the committed record.
4. If already completed and fingerprint matches, return without **creating another business effect**.
5. On first processing, validate aggregate version/state transition and write the business effect.
6. Commit the inbox marker and business writes **in the same transaction/resource** whenever possible.

Do not place an inbox marker in a cache non-atomic with the DB and treat it as proof of business commit. If a Bridge connects two separate data stores, transaction manager/resource boundaries must be proven rather than guessed.

## 32. Idempotency Unit Tests vs. Bridge Integration Tests

A pure handler unit test:

~~~java
@Test
void duplicateEventDoesNotInvokeWriteTwice() {
    OrderEvent event = new OrderEvent(
        "tenant-a", "EV-501", "O-501", 1, "CREATED");

    handler.applyIdempotently(event);
    handler.applyIdempotently(event);

    assertEquals(
        1, orderRepository.countByEventId("EV-501"));
}
~~~

Here `handler`/`orderRepository` are test fixtures whose implementation/transactions must be supplied by the project. Testing against a real database and unique constraint is stronger for verifying concurrency/restarts.

**This test does not prove the Bridge never drops messages**; it only protects downstream from duplicate effects. Combine **ID forwarding tests**, **ACK/durable recovery tests**, and **business idempotency tests**.

## 33. Error Channel: Logging Errors Differs from Persisting Messages for Retry

In an asynchronous flow:

~~~text
Poller / executor
  → Bridge
  → handler throws
  → ErrorMessage(Throwable)
  → errorChannel
~~~

An `ErrorMessage` can carry `MessagingException` and `failedMessage` when present, yet these details may be absent or wrapped differently depending on where the failure happened.

**Merely seeing an error message does not mean source work is still recoverable.** If a poller pulled EV-501 from an in-memory queue and the error handler logs and returns, the event does not automatically return.

Recovery tests must assert one of these outcomes:

- The message remains **reprocessable from a durable source**.
- The message exists in a **durable retry queue**.
- The message was written to an **owned DLQ/quarantine**.
- The business operation completed durably.

When none of those outcomes holds, the test must report **lost responsibility**, even if logs contain a detailed stack trace.

## 34. Synchronous vs. Asynchronous: Error Paths Are Not Identical

| Failure Source | Typical Execution Context | What to Verify |
|---|---|---|
| DirectChannel handler throws | Caller thread | Exception propagation and caller retry |
| QueueChannel poller handler throws | Poller thread | Error handler, transaction/poll recovery |
| ExecutorChannel handler throws | Worker thread | `ErrorMessage`/recoverer, durable handoff |
| Kafka deserializer fails | Before Spring `Message` | Container error handler/DLT |
| AMQP broker connection down | Adapter/container | Reconnect/ACK policy |
| Outbound publish timeout | Outbound handler/transport | Unknown publish outcome, confirm/retry |

Never claim every error enters the global `errorChannel`. Spring Integration error flows depend on channel type, poller, adapter, and configuration; deserialization failures can occur **before** the Bridge is ever called.

If an error handler swallows an exception and ACKs the source, ensure a durable terminal/retry outcome exists; never simply write `catch(Exception) { log(); }`.

## 35. Retries Can Cause Duplicates: Use a Logical ID

A message may be retried multiple times:

~~~text
Original: eventId=EV-501; attempt=1
Retry:    eventId=EV-501; attempt=2
Retry:    eventId=EV-501; attempt=3
~~~

Keep separate:

| ID | Purpose |
|---|---|
| `eventId` | Logical event identity for deduplication |
| `attemptId` | Identifier for a specific retry/recovery attempt |
| `businessCorrelationId` | Workflow/Splitter/Aggregator grouping |
| `MessageHeaders.ID` | Spring message instance identity |
| Broker offset/delivery tag | Transport source position/ACK |
| `replyChannel` | Request–reply return address, if any |

A Bridge only forwards messages per configuration; it does not generate a **stable business event ID** for the producer. If a retry mints a new `eventId`, downstream can treat it as a different event and cause duplicate business side effects.

**No-loss + no-duplicate effect does not necessarily mean each handler is invoked only once.** At-least-once delivery typically allows duplicate invocations paired with idempotent commits.

## 36. Testing an Error Retry Followed by Success

An intentional scenario:

~~~text
EV-501 first attempt
  → Bridge
  → handler throws transient DB error
  → message remains recoverable
  → retry same eventId
  → handler commits once
  → source progress acknowledged
~~~

Assertions:

- The message is **not** marked completed when the handler throws.
- A valid recovery record or source retry exists.
- `eventId`/fingerprint remains unchanged across attempts.
- After retry, the database holds one committed event effect.
- No stale DLQ entry remains marked terminal if retry succeeded.
- Logs/metrics show `attempt=2` while business completed count increases by one.

**Inject faults at the exact transaction boundary.** If tests always simulate exceptions **before** the service starts writing, they never test the post-business-commit / pre-source-ACK window.

## 37. Testing Permanent Failures: No-Loss Does Not Mean Infinite Retries

Malformed message:

~~~text
EV-502 with unsupported schemaVersion
  → validation fails permanently
  → durable quarantine/DLQ
  → source progress advances according to recovery policy
~~~

A failure can be considered **terminal rejected** once a record is safely persisted with enough metadata for investigation/replay. No-loss here does not mean running the handler forever, but **never erasing unprocessed commands or failure evidence**.

Test:

1. Send a malformed message.
2. Assert the business handler creates no side effects.
3. Assert the recovery record contains the logical ID, source reference, and sanitized reason code.
4. Confirm DLQ publish/store succeeds **before** source ACK per policy.
5. Simulate an unavailable DLQ and verify the source does not silently drop.
6. Test replay after fixing the decoder, preserving business idempotency.

Do not let quarantine store raw bearer tokens, secrets, or unnecessary PII; replayability also depends on retention, access control, and schema evolution.

## 38. Bridge in Request–Reply: Never Lose the Return Address

A Gateway can route a request into a flow containing a Bridge:

~~~text
Java @MessagingGateway
  → request channel
  → Bridge
  → Service Activator
  → reply message
  → Gateway return address
~~~

A Bridge is not a request–reply gateway itself. It **forwards** the message so the downstream Service Activator can return a result to the return address established by the Gateway.

Tests should verify:

- Request payload and critical headers reach the expected handler.
- The final reply returns to **the right caller**.
- Two concurrent requests with reordered replies **do not get mixed up**.
- Filters dropping or `void` handlers on a reply-expecting path are caught rather than turning into mysterious timeouts.
- Across brokers/processes, JVM `replyChannel` objects are not portable; use protocol reply-to/correlation mappers.

**An Aggregator's business correlation ID differs from a Gateway's reply address.** Do not use one ID to stand in for both unless the contract explicitly defines it that way.

## 39. Testing Two Concurrent Requests: Replies Must Never Cross

A Bridge shared across callers on the same channel:

~~~text
Request A (eventId=EV-A, correlation=Q-A)
Request B (eventId=EV-B, correlation=Q-B)
  → shared DirectChannel
  → Bridge
  → downstream handler
~~~

In the test:

1. Build two requests with distinct payloads, business IDs, and correlations.
2. Use a barrier so two threads send nearly simultaneously.
3. Have downstream finish request B before A.
4. Assert each result returns to the matching caller/request.
5. Do not treat an uncorrelated shared `QueueChannel.receive()` as a safe reply manager.
6. Check `eventId`/business entity at the destination, not just `count=2`.

A Bridge **does not create request correlation on its own**; for request–reply via `@MessagingGateway`, the Gateway/protocol and flow must preserve the reply path accurately.

## 40. Testing Multiple Concurrent Producers and ID Set Integrity

In a load test, multiple producers send independent IDs:

~~~text
Producer-1: EV-0 ... EV-99
Producer-2: EV-100 ... EV-199
Producer-3: EV-200 ... EV-299
Producer-4: EV-300 ... EV-399
~~~

A test harness can use `ExecutorService` and `CountDownLatch` to publish concurrently and collect results:

~~~java
int producers = 4;
int messagesPerProducer = 100;
int expectedTotal = producers * messagesPerProducer;

Set<String> completedIds =
    ConcurrentHashMap.newKeySet();
CountDownLatch completed = new CountDownLatch(expectedTotal);

// Inside the output capture handler:
// completedIds.add(eventId);
// completed.countDown();

assertTrue(completed.await(10, TimeUnit.SECONDS));
assertEquals(expectedTotal, completedIds.size());
~~~

**The snippet above is an assertion/capture pattern**, omitting producer setup, context, and `eventId` extraction. Using only a `Set` misses duplicates once all unique IDs arrive: track a `Map<eventId, AtomicInteger>` and assert every count equals 1 on the happy path.

Do not claim the Bridge preserves global ordering across four producers; concurrency tests focus on **no missing IDs**, with ordering scoped per producer/key and at the committed handler.

## 41. Testing Ordering per Business Key, Without Requiring Global Order

Two orders:

~~~text
O-501: CREATED(v1) → PAID(v2) → CANCELLED(v3)
O-502: CREATED(v1) → PAID(v2)
~~~

If the Bridge connects to an `ExecutorChannel` or a partitioned broker:

- Ordering between O-501 and O-502 **does not need to be global** if they are independent.
- Ordering of state transitions **within O-501** may need to be enforced.
- If events for the same order dispatch concurrently, the handler uses a version guard or serialized execution lane.
- Redeliveries can arrive after a newer version and must not overwrite stale state.

A no-loss test can PASS (all IDs present) while business state is corrupt because version 3 processed before version 2. Beyond set equality, assert **domain ordering/state invariants** where applicable.

## 42. Testing Bridge Combined with Splitter/Aggregator

~~~text
Order O-501
  → Splitter
      → Child A: stock
      → Child B: price
      → Child C: fraud
  → Bridge on each branch
  → Aggregator
  → OrderDecision
~~~

“Zero message loss” must count **the right unit**:

- One parent can spawn three children, so `outputCount != inputCount` is normal.
- Children carry `parentCorrelationId` and a distinct `memberId`.
- Expected member manifest is A/B/C (or a sequence contract).
- A duplicate child A must not count in place of a missing child C.
- A failing child B must have an explicit failure outcome/policy rather than being dropped and hanging the group forever.
- Group release/expiry must not trigger a second completion on late replies.

Compare:

~~~text
expectedChildren(parent=O-501) = {A,B,C}
observedTerminalOutcomes(parent=O-501) = {A,B,C}
~~~

and each member has a success/failure/terminal state; while any member is pending, do not report whole-group success.

## 43. Testing That Filters Before/After a Bridge Do Not Discard Unintentionally

A flow:

~~~text
Source → Filter → Bridge → Handler
~~~

Test suite:

- Valid event passes Filter → Bridge forwards.
- **Intentionally** rejected event → skipped/rejected status per contract.
- Infrastructure error in the Filter predicate is **not** converted into `false`.
- With a reply-expecting Gateway, a Filter discard produces a typed rejection/error path rather than a silent timeout.
- If the Filter sits after the Bridge, counters distinguish **forwarded** from **handler accepted**.

**Do not label an event that a Filter is authorized to discard as “Bridge lost a message,”** yet do not count it as business-completed without a terminal decision either.

## 44. Testing Header Mapping Across Bridge and Transport

Inside the JVM:

~~~text
Message<OrderEvent>
  headers:
    eventId=EV-501
    businessCorrelationId=tenant-a|O-501
    schemaVersion=1
    traceId=trace-501
~~~

Across an external transport, adapters may selectively serialize headers or reconstruct messages:

1. Assert `eventId` and business correlation exist in the trusted wire schema/headers.
2. Do not rely on `MessageHeaders.ID` as a stable business identity.
3. Do not send raw `replyChannel` JVM objects over Kafka/HTTP.
4. Whitelist headers; never forward bearer tokens or untrusted channel names.
5. Missing required header → intentional rejection/recovery.
6. Different schema version → Transformer/parser handles or quarantines.

**A Bridge can forward headers inside the JVM, yet does not decide the transport serialization policy** of inbound/outbound adapters.

## 45. Backpressure: Sending Succeeds While the Queue Floods

If the producer outpaces the consumer:

~~~text
Inbound rate  = 1,000 messages/s
Handler rate  =   350 messages/s
Queue growth  =   650 messages/s
~~~

This is a **steady-rate estimate**, not a production measurement. An unbounded `QueueChannel` can exhaust JVM RAM, losing all pending in-memory messages.

Controls:

- Bounded queue/capacity and explicit send timeouts.
- Slow down producers or pause source consumption via the adapter.
- Bound executor threads and in-flight messages.
- Persistent store/broker if survival across restarts is needed.
- Metrics for queue depth, enqueue age, and end-to-end pending latency.
- Overflow/rejection policy that **never drops silently**.

**Increasing queue capacity does not make the handler faster.** Tests must verify callers receive backpressure/errors when capacity is full.

## 46. Testing a Full Output Queue or Blocked Handler

Bounded queue in tests:

~~~java
@Bean("bridge.bounded.output")
PollableChannel boundedOutput() {
    return new QueueChannel(1);
}
~~~

Scenario:

1. Send EV-1 and keep it in the queue.
2. Send EV-2 with the configured send timeout/rejection policy.
3. Verify the producer **does not receive a false success** when EV-2 could not be enqueued.
4. Pull EV-1 out and retry EV-2 with the same business ID.
5. Verify a logical ID appears exactly once on the normal path.
6. Test restarts separately if the source requires durability.

**QueueChannel capacity is not a durable delivery mechanism.** On a send timeout, callers must recognize failure/unknown state per topology to retry safely.

## 47. Graceful Shutdown: Drain or Durable Handoff?

~~~text
T0 application begins stopping
T1 inbound adapters stop accepting new messages
T2 in-flight Bridge/poller tasks remain
T3 downstream handlers commit or durable-handoff
T4 source ACKs/offsets finalized when safe
T5 workers stop
~~~

If the process stops while an in-memory queue/executor holds pending items, messages can be lost. Graceful shutdown reduces risk, yet **does not protect against hard crashes or power loss**.

Test:

- Stop source adapters before draining work per topology.
- Wait up to a bounded deadline for in-flight tasks.
- Check queue depth and durable pending state.
- Never ACK the source before durable completion/handoff.
- If the deadline expires, leave the source uncommitted or write durable recovery state.
- Restart and verify unfinished IDs are reprocessed.

**Shutdown hooks do not replace durable queues or source redelivery semantics.**

## 48. Restart Tests: In-Memory Queue vs. Persistent Queue

| Topology | Experiment | Expected Conclusion |
|---|---|---|
| In-memory `QueueChannel` | Enqueue, kill process, restart | Pending items can be lost |
| Persistent `MessageGroupStore`-backed queue | Enqueue, durable commit, kill/restart | Items remain recoverable if store/receive protocol is sound |
| Durable Kafka/AMQP source | Receive without ACK, kill/restart | Redelivery occurs per transport |
| Outbox store | Business + outbox commit, stop publisher, restart | Pending events are published/retried |

**Do not simulate a restart merely by recreating beans in the same JVM without reopening the store.** Durability tests require an external test process/container or state verified across a real restart.

A message reappearing is not automatically a bug: if business state committed while ACK was lost, **redelivery is valid**, and deduplication prevents double effects.

## 49. Testing Per-Message State Instead of One Aggregate Counter

An end-to-end test should record per ID:

~~~text
EV-501 → COMPLETED
EV-502 → DURABLE_PENDING
EV-503 → TERMINAL_QUARANTINED
EV-504 → COMPLETED
~~~

For every accepted logical ID, there must exist **one durable state sufficient to continue or terminate meaningfully**. Avoid counting duplicate attempts as new logical IDs.

A test fixture structure:

~~~java
enum ProcessingState {
    COMPLETED,
    DURABLE_PENDING,
    TERMINAL_QUARANTINED
}

record MessageAudit(
    String eventId,
    ProcessingState state
) {}
~~~

These types are **designed for testing**, not generated automatically by Spring Integration APIs. When unknown external outcomes must be distinguished, include a `PENDING_RECONCILIATION` state persisted durably and classified under pending rather than guessing success/failure.

Test assertion:

~~~java
Set<String> acceptedIds = new HashSet<>(sourceAcceptedIds);
Map<String, ProcessingState> finalStates =
    durableAuditStore.loadStates();

assertEquals(acceptedIds, finalStates.keySet());
assertTrue(finalStates.values().stream()
    .allMatch(Objects::nonNull));
~~~

**Precondition:** `sourceAcceptedIds` must come from a durable/verified source, not merely an `AtomicInteger` lost on a JVM crash. `durableAuditStore` is an application test fixture/implementation that must enforce transitions so an ID is never both COMPLETED and PENDING.

## 50. Test Matrix for Zero-Message-Loss Bridges

| Test Case | Topology / Fault | What to Verify |
|---|---|---|
| One message happy path | Direct → Bridge → Queue | Payload + business headers accurate |
| Many messages happy path | 200 IDs | Full ID set present, no duplicates in window |
| Sequential order | Direct → Bridge → Queue | Ordering in test topology |
| Wrong payload type | Invalid schema/type | Meaningful rejection, no silent drop |
| Missing required header | `eventId` null | Validation/recovery per contract |
| No downstream subscriber | Direct output | Error reaches caller/recoverer |
| Downstream exception | Handler throws | No improper ACK; recoverable |
| Async poller | Queue → poller → Bridge | Latch/capture at target; do not consume source |
| Poller crash | After dequeue, before handler | Durable rollback/recovery or detected loss |
| In-memory queue restart | Kill process | Do not claim durability |
| Persistent queue restart | Reopen message store | Pending items survive when protocol holds |
| Executor handoff | Enqueue then crash | Exposes loss window if durability is missing |
| Output capacity full | Bounded QueueChannel | Clear send failure/backpressure |
| Kafka offset after DB commit | Crash before ACK | Redelivery causes no double effect |
| Kafka offset before DB commit | Crash | Test catches improper ACK |
| AMQP requeue | Consumer crash | Redelivery per adapter |
| Outbound broker confirm missing | Uncertain publish | Retry/reconcile and destination dedupe |
| Two-broker handoff | Publish then crash before source ACK | Duplicates possible, yet no double business effect |
| Transient failure | Bounded retry | Single committed effect |
| Permanent failure | Invalid schema | Durable quarantine/DLQ |
| DLQ unavailable | Recovery cannot persist | Never silently drop source |
| Multiple producers | Concurrent IDs | No missing logical IDs |
| Reordering | Executor pool | State machine/version guard |
| Gateway through Bridge | Two concurrent requests | Replies reach right callers |
| Splitter children | A,B,C + duplicate B | No premature/wrong group release |
| Header mapping | Broker boundary | Business IDs/tenant scope preserved |
| Graceful shutdown | Drain in-flight | No ACK until durable |
| Hard crash/restart | Durable store/broker | Pending items replayed |
| Authorization failure | Untrusted tenant header | No business effect written |
| Backpressure overload | Producer rate exceeds handler | Never treat enqueue/drop as completed |

**Permitted conclusions must match test scope.** An in-memory `QueueChannel` test verifies forwarding, yet cannot replace crash/ACK tests with real brokers and durable stores.

## 51. Observability: Messages Crossing a Bridge Do Not Equal Completions

The metrics below are **recommendations**, not default Spring Integration meters:

| Metric | Interpretation |
|---|---|
| `bridge.input.accepted.count` | Logical messages accepted upstream per contract |
| `bridge.forward.attempt.count` | Forward attempts (may include retries) |
| `bridge.forward.success.count` | Forwards to next channel completed per channel semantics |
| `bridge.forward.failure.count` | Failed forwards |
| `bridge.downstream.completed.count` | Durable business completions |
| `bridge.downstream.duplicate.count` | Business duplicates blocked |
| `bridge.durable.pending.count` | Events still under durable ownership/recovery |
| `bridge.terminal.quarantined.count` | Terminally rejected events with recorded audit |
| `bridge.queue.depth` | Queue backlog |
| `bridge.queue.oldest.age` | Age of oldest pending message |
| `bridge.handoff.latency` | Time from accepted to durable handoff |
| `bridge.end_to_end.latency` | Time from accepted to terminal outcome |
| `bridge.retry.attempt.count` | Retry amplification |
| `bridge.error.unhandled.count` | Errors lacking durable recovery |
| `bridge.source.ack.failure.count` | Source ACK/commit failures |
| `bridge.outbound.confirm.failure.count` | Unconfirmed external handoffs |

**A Bridge forwarding 10,000 messages does not prove 10,000 business operations committed.** If output is an `ExecutorChannel`, handlers may still be pending; if a downstream Filter intentionally skips an event type, completed count can legitimately be lower.

Metric labels should belong to a low-cardinality set such as `flowName`, `channelType`, `operation`, `outcome`, and `reasonCode`. **Never use `eventId`, `commandId`, `orderId`, `email`, raw payload, or `traceId` as metric labels**. IDs belong in structured logs/traces with proper access control and retention.

## 52. Structured Logging for a Bridge Hop

Forwarded:

~~~text
eventId=EV-501
sourceChannel=orders.bridge.input
bridgeEndpoint=orders-bridge
targetChannel=orders.bridge.output
forwardAttempt=1
forwardResult=CHANNEL_ACCEPTED
durableBusinessOutcome=PENDING
~~~

Downstream commit:

~~~text
eventId=EV-501
handler=OrderEventHandler.apply
transactionOutcome=COMMITTED
businessOutcome=SUCCEEDED
idempotencyOutcome=FIRST_COMMIT
~~~

Redelivery:

~~~text
eventId=EV-501
sourceDeliveryAttempt=2
idempotencyOutcome=DUPLICATE_COMPLETED
businessSideEffectCount=0
~~~

Never log `businessOutcome=SUCCEEDED` at the Bridge merely because the output channel accepted the message. **CHANNEL_ACCEPTED** and **BUSINESS_COMMITTED** are two distinct milestones.

When errors occur, log logical ID, source position, `reasonCode`, retry count, recovery destination, and deadline per access policies; never log raw credentials or secrets from headers.

## 53. Runbook: What to Check When “The Bridge Lost Messages”

When an alert fires that “100 events were sent yet the DB only has 97”:

1. **Identify all 100 IDs** from a durable source; do not rely on volatile counters.
2. **Locate the three missing IDs** and check their source ACK/offset status.
3. **Check Bridge input:** did the messages actually enter the input channel?
4. **Check Bridge output:** were there forward failures, timeouts, or capacity rejections?
5. **Inspect downstream channel type:** Direct, memory/persistent Queue, Executor, or adapter?
6. **Inspect pollers:** did another worker or test steal from the `PollableChannel` via `receive()`?
7. **Inspect error paths:** was an exception caught and logged/ACKed without durable retry?
8. **Inspect source progress:** did broker ACK/offset commit before business/durable handoff?
9. **Inspect in-memory backlog:** were queue/executor items pending when the process restarted?
10. **Inspect downstream DB:** commits, rollbacks, deadlocks, unique constraints, version guards?
11. **Inspect idempotency:** were the three IDs falsely treated as duplicates due to an overly coarse key?
12. **Inspect Filter/Router:** were they intentionally discarded or routed to another channel?
13. **Inspect Splitter/Aggregator:** were child messages missing or duplicates miscounted?
14. **Inspect outbound transport:** did broker publish confirm or reply timeout leave unknown outcomes?
15. **Inspect DLQ/retry store:** are quarantined messages durable and accessible?
16. **Reconcile:** classify every ID as COMPLETED, DURABLE_PENDING, or TERMINAL_QUARANTINED.
17. **Remediate:** fix the ACK/handoff boundary, add idempotency/retry/outbox, and write a test reproducing the crash window.

If you discover the source ACKed prematurely before a durable handoff, merely “adding more logs” will not fix it. You must **change the handoff protocol** so every message has an explicit owner after every transition, and establish how to recover any IDs whose responsibility was lost.

## 54. Common Misconceptions

**“`.bridge()` guarantees no messages are lost.”** False. A Bridge only forwards according to channel semantics.

**“`send() == true` proves the handler committed.”** False when downstream is asynchronous or merely enqueued.

**“`QueueChannel` is a durable queue.”** False when in-memory; even persistent stores need transaction/recovery wiring.

**“Once the poller pulls a message, it is finished.”** False. Receive/remove and business commit are two separate steps.

**“`DirectChannel` is always safe because it is synchronous.”** False. Callers can swallow exceptions or crash before persistence.

**“`ExecutorChannel` preserves tasks across restarts.”** Not by default.

**“An `ErrorMessage` in the global `errorChannel` means the message will be retried.”** False. You need an explicit durable recovery policy.

**“A successful DLQ just needs to log the message contents.”** False. You need a durable destination, ownership, and a replay policy.

**“Adding a Bridge between two brokers creates an atomic transaction.”** False. Inbound and outbound adapters manage two independent transports.

**“Kafka offset commit equals DB commit.”** False unless using a proven specific protocol, and external DBs do not automatically join Kafka transactions.

**“At-least-once delivery means the handler always runs once.”** False. Duplicate invocations can occur; idempotency is required.

**“Comparing total input and output counts is enough.”** False. Losing one ID and duplicating another cancel out in aggregate counts.

**“Comparing a Set of IDs is enough to detect duplicates.”** False unless tests also assert multiplicity/attempt counts.

**“A Spring Message UUID is a good business idempotency key.”** False across rebuilds and replays.

**“A Bridge must preserve every framework header and object reference across brokers.”** False. Adapter mapping and serialization introduce their own boundaries.

**“In a flow with a Filter, lower output than input always means the Bridge dropped messages.”** False. Account for intentional rejections.

**“One parent splitting into three children with `outputCount=3` is duplication.”** False. Count against the expected member manifest.

**“Adding more executor threads guarantees no backlog.”** False when the handler or DB is the bottleneck, and it can break ordering.

**“A restart test in the same JVM proves a durable queue.”** False. Test real persistent store reopening/restarts.

**“A Bridge timeout means downstream created no side effects.”** False. Remote or async effects can happen before the caller receives the timeout.

## 55. Practice Lab: Building BridgeNoLossLab

Build a test project with Spring Integration:

1. Create an input `DirectChannel`, output `QueueChannel`, and `IntegrationFlow.bridge()`.
2. Write a test for a single message with payload/headers `eventId` and correlation.
3. Write a test sending 200 events, verifying ID sets and occurrence counts.
4. Test sequential sending and verify ordering in the synchronous topology.
5. Replace output with a `DirectChannel` lacking a subscriber and assert failure propagation.
6. Add a handler that intentionally throws and verify the source does not ACK and lose work.
7. Switch the source to a `QueueChannel` with a poller and test the handler using a latch.
8. Simulate a failure after receive and before business commit, demonstrating the need for recovery.
9. Test an in-memory queue restart: observe the loss risk rather than calling it a passing durability test.
10. Use a persistent store/queue or standalone test broker; run a hard restart test.
11. Connect the Bridge to an `ExecutorChannel`, stop the worker before execution, and analyze the loss window.
12. Add a transactional inbox/business repository with a unique constraint.
13. Inject a crash after DB commit and before source ACK; assert redelivery creates no double effect.
14. Add an outbox when forwarding events to another broker.
15. Test outbound broker confirms and crashing before marking the source completed.
16. Send a malformed message and verify durable quarantine.
17. Make the DLQ unavailable and assert the source does not ACK/drop silently.
18. Send 400 IDs from four concurrent producers using thread-safe counts.
19. Set output queue bound = 1 and test backpressure.
20. Add a Filter that intentionally skips events and separate skipped metrics from lost metrics.
21. Test a Splitter with three child members, duplicate one member, fail one member, and verify Aggregator release policy.
22. Test two Gateway callers through a Bridge with out-of-order replies.
23. Run graceful shutdown and hard crash tests, reconciling every ID's state.
24. Measure queue depth, retry counts, forward failures, and durable completions.
25. Write a runbook for the scenario where 100 IDs entered yet only 97 completed.

**Completion criteria:** prove the Bridge forwards accurately on the normal path, **never ignores failure paths**, never ACKs the source before durable responsibility is established, recovers/replays across restarts, and **never creates duplicate business effects**. State precisely which topology guarantees which property rather than concluding a Bridge provides exactly-once on its own.

## 56. Key Takeaways

**A Bridge in Spring Integration connects two message channels**, keeping flows clear and decoupling endpoints without transforming business payloads. Testing that a Bridge does not lose messages has **two layers**: forwarding tests (payload, headers, logical IDs, channel-scoped ordering) and system-wide delivery/recovery tests (ACKs/transactions, durable handoffs, retries, crashes, idempotency, DLQ).

**Synchronous `DirectChannel` is not durable by default; in-memory `QueueChannel` does not survive restarts; `ExecutorChannel` may only confirm enqueueing into RAM.** With pollable sources, receive/remove before commit opens a failure window; with broker sources, ACK/offset before durable completion risks losing work; across two external brokers, send-confirm and source-ACK are not atomic by default.

Define a stable **logical message ID**, account for every ID as completed/durable pending/terminal quarantined, test crashes before and after commits, and protect side effects with transactions/inbox/outbox/idempotency. **A successful forward is only one successful hop**, never proof that business processing is complete.

### References

- Enterprise Integration Patterns, **Messaging Bridge**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingBridge.html
- Spring Integration Reference, **Message Bridge**: https://docs.spring.io/spring-integration/reference/bridge.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference, **Poller**: https://docs.spring.io/spring-integration/reference/polling-consumer.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Message Stores**: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration Reference, **Kafka Support**: https://docs.spring.io/spring-integration/reference/kafka.html
- Spring Integration Reference, **AMQP Support**: https://docs.spring.io/spring-integration/reference/amqp.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Framework Reference, **Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
