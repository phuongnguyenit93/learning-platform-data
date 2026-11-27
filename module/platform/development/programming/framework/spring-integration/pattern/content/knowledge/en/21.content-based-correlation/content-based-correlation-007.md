# Correlation Across Retries and Redelivery

> **Chapter:** Content-based correlation  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. Practice Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation alongside testing and observing processing branches. This lesson focuses on **preserving business identity and relationships between messages when the same work is retried or redelivered**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain **content-based correlation**: deriving correlation keys from normalized business data instead of relying solely on envelope IDs or delivery IDs.
2. Distinguish **correlation group**, **business operation identity**, **idempotency key**, **message ID**, **trace ID**, and **attempt/delivery count**.
3. Describe **in-process retry**, **broker redelivery**, **dead-letter replay**, and **intentional reprocessing**; understand why they do not necessarily share the same execution identity.
4. Design a stable, collision-free key across tenant/order/line/operation that stays unchanged when a broker redelivers a message.
5. Use Spring Integration **Java DSL + `RequestHandlerRetryAdvice`** to demonstrate retries, and test that a business operation commits only once in the test model.
6. Handle duplicate/reordered replies in **Aggregator/Scatter-Gather**, avoiding double-counting a result or spawning a new group from late replies.
7. Design idempotent consumers, inbox/outbox, durable state, header propagation, timeout/reconciliation, and observability over HTTP, AMQP/JMS/Kafka.

## 2. The Problem: How Many Times Does a Stock Reservation Execute?

Suppose the system receives a stock reservation command:

~~~json
{
  "tenantId": "shop-a",
  "commandId": "CMD-2026-901",
  "orderId": "ORD-901",
  "lineId": "LINE-2",
  "sku": "BOOK-42",
  "quantity": 2,
  "executionId": "RUN-901-A"
}
~~~

The service sends the request to the inventory system. The inventory system **successfully saves the reservation**, but the response is lost on the network. Unaware of this, the caller retries. Later, the worker restarts and the broker redelivers the message; over the weekend, an operator also replays the dead-letter queue (DLQ).

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    participant C as Spring Integration consumer
    participant W as Inventory
    P->>B: ReserveCommand(commandId=CMD-901)
    B->>C: Delivery #1
    C->>W: Reserve with stable business key
    W-->>W: Commit reservation
    W--xC: ACK lost / timeout
    C->>W: Local retry, same business key
    W-->>C: Existing reservation result
    C--xB: Consumer crashes before broker ACK
    B->>C: Redelivery #2, new attempt
    C->>W: Same operation, same business key
    W-->>C: Existing reservation result
    C-->>B: ACK after durable handling
~~~

**Core requirement:** Never reserve inventory twice for an order merely because **one business command** ran across multiple attempts.

At the same time, if policy permits placing a **new** reservation, the system must distinguish it from a replay of the old command. An overly broad key like `orderId` alone can suppress legitimate new operations.

## 3. Retry Differs from Redelivery, and Both Differ from Business Reprocessing

| Mechanism | Triggered By | What Usually Re-Executes? | Which Identity Must Stay Stable? |
| --- | --- | --- | --- |
| **Local retry** | `RetryTemplate`/`RequestHandlerRetryAdvice` or in-process caller | The failing handler invocation | Business command/operation ID |
| **Broker redelivery** | Kafka/JMS/AMQP consumer/container/broker per policy | Message unacknowledged/uncommitted at transport | Business operation ID; related correlation |
| **Retry topic / delayed queue** | Asynchronous retry mechanism | Copy of message/record on another channel | Stable business ID, metadata linking to original |
| **DLQ replay** | Tool/operator or recovery workflow | Message previously moved to dead-letter | Distinguish replaying *the same operation* from a new operation |
| **Business reprocessing** | Business requests re-running the entire flow | A new execution over old or corrected data | Business intent and execution policy must be explicit |

**Never assume** a local retry creates a new Spring `Message<?>`. An advice may re-invoke the handler with the same message within the same dispatch. Conversely, transport redelivery can create a **new envelope, header, or delivery tag** while the business intent remains **one** command.

### 3.1. At-Least-Once Does Not Mean Exactly-Once Side Effects

A broker or client may guarantee delivery/re-reads under certain semantics, but **side effects** in a DB, inventory API, or payment service sit outside the broker's transaction unless an explicit coordination mechanism is designed.

~~~text
Broker delivery attempt    !=  Business operation
MessageHeaders.id          !=  Business command ID
Successful send            !=  Business commit
Retry count                !=  Duplicate detection key
Correlation ID             !=  Idempotency key (without an explicit contract)
~~~

To achieve a **single business effect** when messages can be redelivered, you need idempotency/deduplication **where business state commits** and a meaningful stable key.

## 4. Six Commonly Confused IDs

| ID/Header | Question It Answers | Stable Across Retries/Redeliveries? | Should It Deduplicate Business Operations? |
| --- | --- | --- | --- |
| `MessageHeaders.ID` | Which envelope ID was created for this message? | Can change when rebuilding a message | **No**, unless under a specially verified contract |
| `businessCorrelationId` | Which activities relate to the same business request? | Should stay stable per request | Useful for tracing; **insufficient** to deduplicate every operation |
| `executionId` | Which *workflow execution run* do replies belong to? | Fixed within one execution; **may change** on a new run | Usually the group key; does not replace operation key |
| `commandId` / `operationId` | Is this the same state-change intent or a new command? | **Must persist** on retry/replay of the same command | Yes, when namespace and operation scope are explicit |
| `traceId` / `spanId` | Which spans make up a distributed execution path? | Depends on tracing; spans usually change | **No**, tracing is not deduplication |
| Delivery ID / broker offset / attempt | Which record/attempt did the broker deliver? | Varies by transport and delivery | **No**, only for transport/diagnostics |

For **Split → per-line processing → Aggregate**, one `commandId` can spawn **multiple child operations**. Each child needs `lineId` or `taskId` so all lines under one command are not treated as a single operation.

### 4.1. A Complete Example

~~~text
tenantId                shop-a
orderId                 ORD-901
commandId               CMD-2026-901
lineId                  LINE-2
operationType           RESERVE_STOCK

businessCorrelationId   ORD-901
executionId             RUN-901-A
idempotencyKey fields   shop-a/CMD-2026-901/LINE-2/RESERVE_STOCK

attempt #1              transient timeout after commit
attempt #2              local retry
delivery #2             broker redelivery
DLQ replay              manually re-published same command
~~~

All four executions may map to **one unique operation identity**. Yet a `RELEASE_STOCK` command or a new `RESERVE_STOCK` issued a new `commandId` by the business **must not** be falsely deduplicated.

## 5. What Is Content-Based Correlation?

**Content-based correlation** derives relationships from **business content** or verified metadata, such as:

- `tenantId` + `orderId` to trace messages related to an order.
- `executionId` to gather replies belonging to a Scatter-Gather run.
- `commandId` + `lineId` + `operationType` to identify a single side effect.
- `invoiceId` + `invoiceVersion` to process versioned events in order.

Instead of assuming two messages share `MessageHeaders.ID`, content-based correlation states explicit rules:

~~~text
sameOperation(a, b) :=
  a.tenantId     == b.tenantId
  AND a.commandId == b.commandId
  AND a.lineId    == b.lineId
  AND a.operation == b.operation

sameAggregationGroup(a, b) :=
  a.executionId == b.executionId
~~~

**The two definitions are intentionally different.** The same business operation can be retried within one execution or replayed in a new execution. Conversely, one execution can contain **many operations** across multiple `lineId`s.

### 5.1. Choose Keys from Immutable Parts of Data

Correlation/dedup keys must never include:

- `retryCount`, `JMSXDeliveryCount`, or attempt number.
- Timestamp of **the current processing attempt**.
- A fresh random UUID generated on each retry.
- Each Spring message envelope's ID.
- Mutable values such as order description or recalculated prices.

Use identifiers created **when the business originates the operation**, persist them durably, and carry them across every boundary.

### 5.2. Keys Need Namespacing

`orderId=123` can collide between tenant A and tenant B. Therefore a deduplication key using `orderId` alone is dangerous in multi-tenant systems.

A business key should include all required contract parts:

~~~text
ReservationIdentity(
    tenantId = shop-a,
    commandId = CMD-2026-901,
    lineId = LINE-2,
    operation = RESERVE_STOCK
)
~~~

In a database, you can store **separate columns with a UNIQUE constraint** instead of joining strings with collision-prone delimiters. If you must transmit a single string externally, define explicit canonical encoding/escaping or issue a UUID/opaque operation ID **once** with a durable mapping to the business identity.

### 5.3. Do Not Arbitrarily Hash Mutable Content as Identity

`SHA-256(payload JSON)` looks convenient, yet can yield **two different keys** for the same operation if JSON field order changes, metadata is added, timestamps shift, or serializers vary. Conversely, two valid distinct tasks with identical payloads could be falsely deduplicated.

If the contract genuinely requires a content hash, specify **canonicalization, version, scope, and collision handling**. Usually a **stable producer-issued operation ID** has clearer semantics than a raw payload hash.

## 6. Design Flow: Correlation Survives Multiple Executions

~~~mermaid
flowchart TD
    IN["Trusted inbound: Validate command and IDs"] --> D["Compute/restore stable operation identity"]
    D --> I{"Inbox / idempotency state"}
    I -->|"New"| H["Business handler"]
    I -->|"Already completed"| OLD["Reuse persisted outcome"]
    I -->|"In progress"| WAIT["Wait / retry later / reconcile"]
    H --> O["Commit business result + outbox where possible"]
    O --> R["Reply with executionId + lineId"]
    OLD --> R
    R --> A["Aggregator: group by executionId"]
    A --> F["Finalization once per execution"]
    WAIT --> E["Controlled error / delayed retry"]
~~~

**A redelivered message can enter the Inbox, be recognized as already processed**, and return the **recorded outcome**. However, if an old reply is redelivered to an already-completed Aggregator, the Aggregator itself also needs deduplication and a closed-group policy. Deduplication at the **business handler** and deduplication at **group/finalization** are two separate layers.

### 6.1. Correct Correlation Can Still Duplicate Side Effects

For instance, two messages sharing `businessCorrelationId=ORD-901` can still both invoke `reserveStock()`. Correlation only tells you they relate to each other; it **does not prevent** two commits.

Distinguish clearly:

~~~text
Correlation: finding relationships
Deduplication: recognizing duplicates
Idempotency: handling repeats without extra side effects
Ordering: deciding which message comes first
Exactly-once business outcome: result achieved via state/transactions
~~~

## 7. Java 17: Defining Stable Business Identity

We use a simple example for this lesson. DTOs are Java 17 `record`s, fitting an immutable contract. Classes can reside in separate Java files within the same package.

### 7.1. Command and Reservation Key

~~~java
import java.util.Objects;

record ReserveCommand(
    String tenantId,
    String commandId,
    String executionId,
    String orderId,
    String lineId,
    String sku,
    int quantity
) {
    ReserveCommand {
        requireNonBlank(tenantId, "tenantId");
        requireNonBlank(commandId, "commandId");
        requireNonBlank(executionId, "executionId");
        requireNonBlank(orderId, "orderId");
        requireNonBlank(lineId, "lineId");
        requireNonBlank(sku, "sku");
        if (quantity <= 0) {
            throw new IllegalArgumentException("INVALID_QUANTITY");
        }
    }

    private static void requireNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + "_MISSING");
        }
    }
}

record ReservationKey(
    String tenantId,
    String commandId,
    String lineId,
    String operationType
) {
    static ReservationKey from(ReserveCommand command) {
        return new ReservationKey(
            command.tenantId(),
            command.commandId(),
            command.lineId(),
            "RESERVE_STOCK");
    }
}
~~~

`executionId` is **not** inside `ReservationKey`. That is a deliberate choice in this contract: a replay in a new execution of the **same command** must still reuse the existing reservation outcome. Yet `executionId` remains in the request/reply so we know **which processing run is waiting**.

If the business permits **executing two separate reservations** for the same line item, the producer must issue a meaningful new `commandId`; never “bypass” idempotency by changing `executionId`.

### 7.2. Receipt and Reply for the Aggregator

~~~java
record ReserveReceipt(
    ReservationKey reservationKey,
    String executionId,
    String lineId,
    String outcome
) {}

record ItemReply(
    String executionId,
    String lineId,
    String outcome
) {
    ItemReply {
        if (executionId == null || executionId.isBlank()
                || lineId == null || lineId.isBlank()
                || outcome == null || outcome.isBlank()) {
            throw new IllegalArgumentException("INVALID_ITEM_REPLY");
        }
    }
}
~~~

`ReserveReceipt` contains both **business identity** and **execution identity**, serving distinct purposes. A consumer can retrieve the previously saved business result and construct a **new reply** with the current `executionId`; never pull an old `executionId` from a persisted receipt and inject it into a new group by mistake.

## 8. Java Demo: Simulating “Commit Then Lost ACK”

A very common failure: the backend committed successfully, while the caller sees only a timeout and retries. The following Java model intentionally **exercises that failure** by storing the result first and throwing an exception on the first call.

> This snippet is an **in-JVM fake for illustration/testing**. `ConcurrentHashMap` does not replace DB transactions, unique indexes, or idempotency in an external inventory service. Never use it as a production durability mechanism.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

final class SimulatedInventoryHandler {
    private final ConcurrentMap<ReservationKey, String> committed =
        new ConcurrentHashMap<>();
    private final AtomicInteger attempts = new AtomicInteger();
    private final AtomicInteger commits = new AtomicInteger();
    private final AtomicBoolean loseFirstAck = new AtomicBoolean(true);

    public ReserveReceipt reserve(ReserveCommand command) {
        attempts.incrementAndGet();

        ReservationKey key = ReservationKey.from(command);
        String outcome = committed.computeIfAbsent(key, ignored -> {
            commits.incrementAndGet();
            return "RESERVED";
        });

        // Simulate: side effect committed, but response was lost.
        if (loseFirstAck.compareAndSet(true, false)) {
            throw new IllegalStateException("SIMULATED_ACK_LOSS");
        }

        return new ReserveReceipt(
            key, command.executionId(), command.lineId(), outcome);
    }

    int attempts() {
        return attempts.get();
    }

    int committedOperations() {
        return commits.get();
    }
}
~~~

First call:

~~~text
attempt #1:
  computeIfAbsent(key) -> store "RESERVED", commits = 1
  throw SIMULATED_ACK_LOSS

attempt #2:
  same key -> return stored "RESERVED", commits still = 1
  return ReserveReceipt
~~~

If the request is redelivered again, `attempts` increases while `committedOperations` stays at **1** for the lifetime of the fake store.

### 8.1. Do Not Infer Production “Exactly-Once” from This Fake

- When the process restarts, `ConcurrentHashMap` loses all state.
- Two service instances have two separate maps with no shared unique constraint.
- If reserving in an external system happens **after** checking the map, a race still exists between “check not seen” and “send command.”
- An external API might have committed when the caller timed out; the local map recorded nothing.

Production requires **idempotency where the side effect executes** (or a reconciliation/status-checking protocol with the external service).

## 9. Spring Integration Java DSL: Retrying Handler Calls

Spring Integration provides `RequestHandlerRetryAdvice`, integrating with Spring Retry to re-invoke a handler on eligible exceptions. The illustrative configuration below runs in one JVM using `DirectChannel` and `QueueChannel` for easy observation.

### 9.1. Bean Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
class ReservationRetryFlowConfiguration {

    @Bean("reservations.in")
    DirectChannel reservationInput() {
        return new DirectChannel();
    }

    @Bean("reservations.out")
    QueueChannel reservationOutput() {
        return new QueueChannel();
    }

    @Bean
    SimulatedInventoryHandler inventoryHandler() {
        return new SimulatedInventoryHandler();
    }

    @Bean
    RequestHandlerRetryAdvice reserveRetryAdvice() {
        RetryTemplate retry = new RetryTemplate();
        retry.setRetryPolicy(new SimpleRetryPolicy(3));

        FixedBackOffPolicy backoff = new FixedBackOffPolicy();
        backoff.setBackOffPeriod(10L);
        retry.setBackOffPolicy(backoff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(retry);
        return advice;
    }

    @Bean
    IntegrationFlow reserveWithRetry(
            SimulatedInventoryHandler handler,
            RequestHandlerRetryAdvice retryAdvice) {
        return IntegrationFlow.from("reservations.in")
            .handle(handler, "reserve", e -> e.advice(retryAdvice))
            .channel("reservations.out")
            .get();
    }
}
~~~

**Dependencies:** the example uses Spring Integration Java DSL, Spring Messaging, Spring Retry, and Spring Test/JUnit for the tests below. If your application lacks Spring Retry, add a dependency compatible with your project's stack.

`SimpleRetryPolicy(3)` means the example allows **at most three attempts**, not “one initial attempt plus three retries.” A 10 ms backoff is **only for fast tests**, unsuitable for an external service at risk of overload.

### 9.2. What Is Preserved Across Local Retries?

When the advice re-invokes the handler within the same execution:

- `ReserveCommand.commandId`, `tenantId`, `lineId`, and `operationType` must remain unchanged.
- `ReserveCommand.executionId` still represents the same processing run.
- Never generate a new `commandId` inside the handler per attempt.
- Traces may show different span/attempt metadata, yet must not change business operation identity.

If retries run on a handler with side effects, the backend **must** be idempotent. Configuring `RetryAdvice` alone never guarantees an operation won't run twice.

### 9.3. Retryable vs Non-Retryable Errors

The example uses a generic `SimpleRetryPolicy` for demonstration. In production, classify errors explicitly:

| Error | Should You Retry the Same Command? | Reason |
| --- | --- | --- |
| Network timeout, HTTP 503 | Conditionally, bounded backoff | May be transient; side-effect state may be UNKNOWN |
| Throttling/rate limit | Conditionally, using backoff/`Retry-After` | Avoid creating a retry storm |
| Malformed payload schema | No | Same payload will always fail |
| Invalid tenant/forbidden | No | Retrying cannot fix permissions |
| Final business rejection | No | Terminal business outcome already reached |
| Already-committed duplicate | Do not re-execute side effect | Return cached/recorded outcome |
| Conflict: two payloads with same operation ID | Quarantine/reconcile | Never blindly pick the last record |

A **timeout after commit** is a special case: retrying is **safe** only if the receiver supports idempotency/reconciliation. Never treat a timeout alone as proof the transaction never happened.

## 10. Correlation Headers in Spring Messaging

Message headers can carry correlation info for downstream tracking or Aggregator reply matching. Example:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

ReserveCommand command = new ReserveCommand(
    "shop-a", "CMD-2026-901", "RUN-901-A",
    "ORD-901", "LINE-2", "BOOK-42", 2);

Message<ReserveCommand> request = MessageBuilder.withPayload(command)
    .setHeader("businessCorrelationId", command.orderId())
    .setHeader("commandId", command.commandId())
    .setHeader(
        IntegrationMessageHeaderAccessor.CORRELATION_ID,
        command.executionId())
    .build();

// inputChannel.send(request);
~~~

**Three layers of information:**

- Payload `commandId` and `lineId` identify the operation.
- Header `businessCorrelationId` aids per-order logging/tracing.
- Header `correlationId` is used by Spring Integration for **message-group semantics** when needed.

**Never treat a client-supplied header as an absolute source of truth.** At ingress, verify signatures/authentication, tenant, schema/version, and cross-check against the payload or workflow registry. If payload and header conflict, reject/quarantine instead of arbitrarily picking one side.

### 10.1. Header Propagation Has Limits

A Transformer may build a new envelope; an HTTP/Kafka/AMQP adapter has its own header mapper that may omit headers or alter types. When crossing boundaries:

1. Define the **header contract** to transmit.
2. Serialize correlation/command/execution IDs into stable types.
3. Verify authenticated identity on the receiving side.
4. Test round-trip messages, including retries and DLQ replays.
5. Never directly serialize an in-JVM `replyChannel` object meaningful only inside one JVM.

### 10.2. Never Derive Business ID from `MessageHeaders.ID`

~~~java
// Avoid: envelope ID does not represent a business command
String unstableOperationId = message.getHeaders().getId().toString();

// Prefer: stable business command identity from payload/registry
ReservationKey stableKey =
    ReservationKey.from((ReserveCommand) message.getPayload());
~~~

The second approach is safe only once the command has been validated and its origin authenticated. An untrusted sender could **spoof the same operation ID** to hijack an old result or trigger rejections; the store must be scoped by tenant/principal and check content consistency.

## 11. JUnit: Retrying at the Handler Does Not Duplicate Commits in the Fake

Integration example with Spring Test. The test verifies the handler is re-invoked after a simulated ACK loss while the business commit count in the fake stays at one.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.annotation.DirtiesContext;

@SpringJUnitConfig(ReservationRetryFlowConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ReservationRetryFlowTest {

    @Autowired @Qualifier("reservations.in")
    MessageChannel input;

    @Autowired @Qualifier("reservations.out")
    PollableChannel output;

    @Autowired
    SimulatedInventoryHandler handler;

    private static ReserveCommand command(String executionId) {
        return new ReserveCommand(
            "shop-a", "CMD-2026-901", executionId,
            "ORD-901", "LINE-2", "BOOK-42", 2);
    }

    @Test
    void localRetryKeepsBusinessOperationStable() {
        ReserveCommand c = command("RUN-901-A");

        assertTrue(input.send(
            MessageBuilder.withPayload(c).build()));

        Message<?> reply = output.receive(1000);
        assertNotNull(reply);
        assertInstanceOf(ReserveReceipt.class, reply.getPayload());

        ReserveReceipt result = (ReserveReceipt) reply.getPayload();
        assertEquals("RUN-901-A", result.executionId());
        assertEquals("LINE-2", result.lineId());
        assertEquals("RESERVED", result.outcome());

        assertEquals(2, handler.attempts());
        assertEquals(1, handler.committedOperations());
        assertNull(output.receive(0));
    }

    @Test
    void redeliveryCanCreateAnotherReplyButNotAnotherCommit() {
        ReserveCommand c = command("RUN-901-A");

        Message<ReserveCommand> delivery1 =
            MessageBuilder.withPayload(c).build();
        Message<ReserveCommand> delivery2 =
            MessageBuilder.withPayload(c).build();

        // Two new envelopes may have different IDs,
        // yet still carry the same business operation.
        assertNotEquals(
            delivery1.getHeaders().getId(),
            delivery2.getHeaders().getId());

        assertTrue(input.send(delivery1));
        assertNotNull(output.receive(1000));

        assertTrue(input.send(delivery2));
        assertNotNull(output.receive(1000));

        assertEquals(3, handler.attempts());
        assertEquals(1, handler.committedOperations());
    }

    @Test
    void newExecutionOfSameCommandStillReusesBusinessEffect() {
        assertTrue(input.send(MessageBuilder
            .withPayload(command("RUN-901-A")).build()));
        ReserveReceipt first =
            (ReserveReceipt) output.receive(1000).getPayload();

        assertTrue(input.send(MessageBuilder
            .withPayload(command("RUN-901-B")).build()));
        ReserveReceipt replay =
            (ReserveReceipt) output.receive(1000).getPayload();

        assertEquals(first.reservationKey(), replay.reservationKey());
        assertNotEquals(first.executionId(), replay.executionId());
        assertEquals(1, handler.committedOperations());
    }
}
~~~

**What these tests prove and do not prove:**

- Proves: inside one JVM with a fake idempotent map, **attempts can exceed commits**.
- Proves: redeliveries can emit **multiple replies** even with only one side effect.
- Proves: a new execution can reuse a prior business result while emitting a reply with the new `executionId`.
- **Does not prove:** durable deduplication across restarts, transactions with external inventory, broker acknowledgments, or exactly-once Aggregator outputs.

**Important consequence:** deduplicating the business operation **does not automatically stop** duplicate replies downstream. Aggregator and finalization still require their own policies.

## 12. Real Redelivery on JMS, AMQP, Kafka: No Universal Counter

When deploying with brokers, examine the exact semantics of the transport and connector.

| Transport | Mechanisms Commonly Involved in Redelivery | What to Verify |
| --- | --- | --- |
| **JMS** | Session transactions/acknowledgments and provider redelivery; some providers supply `JMSRedelivered`/`JMSXDeliveryCount` | Which counters the provider supports; commit/rollback and DLQ semantics |
| **AMQP/RabbitMQ** | Consumer ACK/NACK/reject, requeue, dead-letter, retry queues | `redelivered` flag, DLX/`x-death` headers, and requeue policies; never assume arbitrary delivery counts |
| **Kafka** | Consumer offsets, container retries or retry topics, rebalances/reprocessing | Offset commits, partitioning/ordering, record keys, retry-topic headers if used |
| **HTTP webhook** | Sender retries per its own policy, possibly sending new requests | Event ID, signatures, timestamp validity window, idempotency contract |
| **Internal queue** | Poller/executor/redelivery depending on channel/store | Whether the queue is durable and which endpoint handles retries/acks |

### 12.1. `deliveryCount` Is Not a Correlation Key

Counters increment per attempt and may reset or vanish when messages are republished to retry topics or DLQs. They are good for metrics and enforcing **retry limits**, but unstable for identifying operations.

### 12.2. Kafka Offset Is Not a Business ID

A Kafka record has a topic, partition, and offset, yet **a business operation can be republished to another topic or a new offset**. If you deduplicate by offset, a manual replay of the same `ReserveCommand` will slip through.

Choose Kafka record keys for partitioning/ordering when needed, while basing business idempotency on **command/operation identity**. When using Kafka transactions, remember they do not automatically extend atomicity to an external inventory API or arbitrary database outside the transaction.

### 12.3. AMQP and JMS: ACK After Achieving Appropriate Durability

If a worker ACKs the broker before business results are committed or safely persisted, a crash between the two steps can lose work. If it commits and then ACK fails, the broker will redeliver. Design to tolerate **both failure windows** using durable state and idempotency.

Never assume an ACK on an internal channel means an external provider has finished.

## 13. DLQ Replay: Same Operation or a New Workflow?

A message lands in the dead-letter queue after exhausting retries. Before replaying, ask:

1. Does the original payload still conform to the current contract?
2. Is this a **redelivery of the same command** or a new business request?
3. Might the target system have already committed the old operation?
4. Is the old correlation group still open or already `EXPIRED/COMPLETE`?
5. Which schema/policy version is the receiver running at replay time?

### 13.1. Replaying the Same Command

Keep `tenantId`, `commandId`, `lineId`, and `operationType` unchanged. You may assign a new `executionId` if starting an authorized reprocessed workflow run, provided clear mappings and policies prevent mixing replies from the old run.

~~~text
Original:
  operation key = (shop-a, CMD-901, LINE-2, RESERVE_STOCK)
  execution = RUN-901-A

DLQ replay:
  same operation key
  execution = RUN-901-B (new processing run)
  replayOf = RUN-901-A
~~~

Inventory results must deduplicate by **operation key**, while replies for the new run join group `RUN-901-B`.

### 13.2. New Business Operation

If an operator intentionally creates an additional command **distinct** from the old one, issue a new `commandId` and record proper justification/authorization. Never change `commandId` merely to “force a retry” of an operation that may already have committed.

### 13.3. Never Ignore Schema Version

A DLQ can hold messages for days. By replay time, current serializers/mappers may support only a newer schema. Maintain versioned decoders and migration policies; never interpret a `v1` message as `v2` if fields or currency units changed.

## 14. Aggregator and Scatter-Gather: Correlation Across Repeated Replies

A batch reservation command has three lines:

~~~text
execution RUN-901-A
expected LINE-1, LINE-2, LINE-3

Incoming:
  LINE-1 -> RESERVED
  LINE-2 -> RESERVED
  LINE-2 -> RESERVED (duplicate due to redelivery)
  LINE-3 -> not arrived
~~~

If the release strategy only checks `group.size() >= 3`, the group can **release prematurely** even though `LINE-3` is missing.

### 14.1. Group by Execution, Release by Unique Item ID

~~~text
Group key      = executionId
Unique item key = lineId
Release when   = all expected line IDs have terminal valid results
~~~

`executionId` must come from **verified payload/metadata**. `lineId` must belong to the expected set and never be altered by an external reply.

### 14.2. Illustrative Pure Java Release Policy

~~~java
import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

final class ReplyCompletionPolicy {
    private ReplyCompletionPolicy() {}

    static boolean allExpectedReceived(
            String executionId,
            Set<String> expectedLineIds,
            Collection<ItemReply> replies) {

        Map<String, ItemReply> unique = new HashMap<>();

        for (ItemReply reply : replies) {
            if (reply == null
                    || !executionId.equals(reply.executionId())
                    || !expectedLineIds.contains(reply.lineId())) {
                throw new IllegalArgumentException("UNEXPECTED_REPLY");
            }

            ItemReply previous =
                unique.putIfAbsent(reply.lineId(), reply);
            if (previous != null && !previous.equals(reply)) {
                throw new IllegalArgumentException(
                    "CONFLICTING_DUPLICATE_REPLY");
            }
        }

        return unique.keySet().equals(expectedLineIds);
    }
}
~~~

**Preconditions:** `expectedLineIds` comes from a trusted source and is non-empty when the workflow expects at least one part; the caller is responsible for validating the group key and policy prior to calling this function. This is a **pure policy**, not a full custom Aggregator with stores, timeouts, and side effects.

### 14.3. Testing Duplicates Before Release

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ReplyCompletionPolicyTest {

    @Test
    void duplicateDoesNotReplaceMissingLine() {
        Set<String> expected =
            Set.of("LINE-1", "LINE-2", "LINE-3");

        List<ItemReply> received = List.of(
            new ItemReply("RUN-901-A", "LINE-1", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-2", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-2", "RESERVED"));

        assertFalse(ReplyCompletionPolicy.allExpectedReceived(
            "RUN-901-A", expected, received));
    }

    @Test
    void receivesAllUniqueLinesOutOfOrder() {
        Set<String> expected =
            Set.of("LINE-1", "LINE-2", "LINE-3");

        List<ItemReply> received = List.of(
            new ItemReply("RUN-901-A", "LINE-3", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-1", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-2", "RESERVED"));

        assertTrue(ReplyCompletionPolicy.allExpectedReceived(
            "RUN-901-A", expected, received));
    }

    @Test
    void rejectsConflictingDuplicate() {
        Set<String> expected = Set.of("LINE-1");

        List<ItemReply> conflicting = List.of(
            new ItemReply("RUN-901-A", "LINE-1", "RESERVED"),
            new ItemReply("RUN-901-A", "LINE-1", "FAILED"));

        assertThrows(IllegalArgumentException.class, () ->
            ReplyCompletionPolicy.allExpectedReceived(
                "RUN-901-A", expected, conflicting));
    }
}
~~~

### 14.4. When to Deduplicate Replies Before the Aggregator?

A solid approach is deduplicating and validating replies at an **inbox upstream of the Gatherer**. If replies have already entered the group, the release strategy and output processor must still handle duplicates and conflicting results. If a duplicate can arrive **after the group closes**, you need a closed-group registry/tombstone or duplicate detector so no new group is opened.

## 15. Group Completed Yet Replies Keep Arriving

Suppose the Aggregator emitted `BatchOutcome(COMPLETE)` for `RUN-901-A` and removed the group from the store. Later, the broker redelivers the reply for `LINE-2`:

~~~text
RUN-901-A, LINE-2, RESERVED (redelivery)
    |
    v
Aggregator group no longer exists
    |
    v
Could create a new incomplete group with same key
~~~

A **closed-execution registry** helps distinguish:

~~~text
Incoming ItemReply
    |
    +--> execution OPEN
    |        -> validate + dedup + group
    |
    +--> execution COMPLETE
    |        -> duplicate audit / idempotent no-op
    |
    +--> execution EXPIRED
    |        -> late reply / reconcile
    |
    +--> execution UNKNOWN
             -> reject / quarantine
~~~

**Do not set `expireGroupsUponCompletion(true)` and assume late replies vanish harmlessly.** Once the group is deleted, new state can be spawned unless a policy blocks it.

### 15.1. Race Between Final Reply and Timeout

Two threads may observe state simultaneously:

~~~text
Thread A: final reply arrives, should COMPLETE
Thread B: deadline sees one missing, should EXPIRE
~~~

You need an **atomic** transition on the execution such as `OPEN → COMPLETE` **or** `OPEN → EXPIRED`. Whichever outcome wins by commit order, only **one final result** is emitted; use database CAS/transactions or an appropriate state machine + outbox.

### 15.2. Zero Replies Do Not Create a Group Automatically

If no replies ever arrive, the Aggregator may have no group for `groupTimeout` to fire on. A deadline watcher on the **request/execution registry** must produce the `NO_REPLIES` outcome rather than relying on the timeout of a non-existent group.

### 15.3. Replay After Timeout

If an execution is `EXPIRED` and an operator needs to rerun it, issue a **new execution ID** per policy (e.g., `RUN-901-B`), keeping the old business operation keys if it is still the **same command**. New replies map into the new group while still avoiding repeated side effects in the backend.

## 16. Durable Idempotency: In-Memory State Is Not Enough

Production must handle process restarts, multiple consumer nodes, broker redeliveries, and recovery after calling external APIs.

### 16.1. Unique Constraint on the Operation Key

An illustrative table:

~~~sql
CREATE TABLE reservation_operation (
    tenant_id       VARCHAR(80) NOT NULL,
    command_id      VARCHAR(120) NOT NULL,
    line_id         VARCHAR(120) NOT NULL,
    operation_type  VARCHAR(40) NOT NULL,
    request_hash    VARCHAR(64) NOT NULL,
    state           VARCHAR(30) NOT NULL,
    result_json     TEXT,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, command_id, line_id, operation_type)
);
~~~

**Purpose of `request_hash`:** it detects **the same identity with two conflicting payloads**. However, define canonicalization and versioning for business-relevant fields; never blindly hash raw JSON containing retry metadata. If two requests share an operation key yet differ in SKU or quantity, **never** return a cached success without comparing contracts—that can mask bugs or be abused to obtain wrong results.

### 16.2. Illustrative State Machine

~~~mermaid
flowchart LR
    N["NEW"] --> P["PROCESSING (claimed)"]
    P --> C["COMPLETED (durable result)"]
    P --> R["RETRYABLE / UNKNOWN"]
    R --> P
    P --> F["FAILED_FINAL"]
    C --> DUP["Duplicate -> same result, no new effect"]
    F --> DUPF["Duplicate -> same terminal error"]
~~~

You need a **unique insert/CAS** so only one worker claims an eligible operation. If a worker dies in `PROCESSING`, enforce a lease/timeout/recovery mechanism; never leave the operation stuck forever. If an external backend lacks idempotency, local state **cannot independently resolve** “external committed yet local failed to record result”; you need status lookup/reconciliation or an idempotency token protocol with the backend.

### 16.3. Inbox and Outbox Solve Different Problems

- **Inbox/processed-message ledger:** recognizes messages/operations already received and committed, blocking duplicate processing.
- **Outbox:** stores events to publish **in the same transaction** as business data in the DB-owning system so a publisher can retry without losing notifications.
- **Idempotent external API:** backend accepts a stable operation key and returns the same outcome across repeated calls.
- **Aggregator closed-state:** ensures one execution never emits two final outcomes.

A system may need **all four**. No single `retry=true` or `exactlyOnce=true` flag replaces these layers.

## 17. DB and External API Boundary: Wishful Thinking Does Not Make Transactions

Example handler:

~~~text
1. Begin DB transaction
2. Check command operation key
3. Call external Inventory API
4. Persist local result
5. Commit DB transaction
6. ACK broker
~~~

If step 3 commits in the inventory system but step 4 fails, the local DB **does not know the outcome**. A local DB transaction rollback does not roll back the external inventory system. If the broker redelivers, the handler must:

1. Query the operation by stable key on the backend (if supported).
2. Or re-invoke the idempotent API with the same key.
3. Or transition `UNKNOWN` to reconciliation/manual review.

**Never** assume it is “safe to retry” a charge/payment/reservation merely because the local DB has no `COMPLETED` row.

### 17.1. Where Side Effects Occur

An ideal design has the business owner store the operation key **in the same transaction as the mutation**:

~~~text
BEGIN
  INSERT operation_key IF ABSENT
  IF already committed: RETURN stored outcome
  ELSE apply business mutation
       SAVE outcome
COMMIT
~~~

Across multiple transactions or external systems, details vary, yet the principle holds: the idempotency check must sit inside **the same consistency boundary** as the side effect, or have reconciliation when the boundary cannot be atomic.

## 18. Header Propagation, Tracing, and Security

### 18.1. Headers Across Multiple Processing Steps

~~~text
Inbound:
  payload.commandId = CMD-901
  payload.executionId = RUN-901-A
  headers.businessCorrelationId = ORD-901

Retry within handler:
  same business identity, perhaps same envelope

Broker redelivery:
  new delivery metadata, business identity unchanged

DLQ replay:
  new envelope/transport headers may appear,
  stable operation identity must survive
~~~

`traceId` and `spanId` are not guaranteed to keep the same values across manual replays. When traces need linking, store `originalEventId` or `replayOf` in controlled metadata while keeping the new trace distinct from the old business transaction.

### 18.2. Do Not Trust Self-Declared `commandId` as Authorization

A client might set a `commandId` matching another tenant's operation to probe or hijack results. Scope idempotency by trusted tenant/principal; never expose cached results if the caller lacks permission to view that operation.

For HTTP webhooks, verify signatures, timestamps, replay windows, and sender identity. For brokers, verify ACLs, producer identity, schema/version, and tenant mapping. If business correlation headers conflict with the payload, return an explicit error rather than silently accepting.

### 18.3. Avoid PII in Keys and Metrics

Never use raw email addresses, phone numbers, or national ID numbers as dedup keys when unnecessary. Prefer stable opaque IDs with clear scope. `commandId`, `orderId`, and `executionId` are high-cardinality; keep them in access-controlled logs/traces rather than metric labels.

## 19. Retry Policies and Retry Budgets

Retries must not be unbounded. A transient failure when downstream is overloaded can cause the entire system to retry simultaneously and worsen an outage.

| Policy | Purpose | Application |
| --- | --- | --- |
| Max attempts | Prevent infinite loops | Configure per error type and SLA |
| Backoff + jitter | Prevent retry storms | Exponential/increasing delay with jitter |
| Per-attempt timeout | Bound external call duration | Never block threads indefinitely |
| End-to-end deadline | Bound total command/execution duration | Include queue wait + retries |
| Circuit breaker / rate limit | Protect downstream | Reject/defer under overload |
| Retryable exception set | Avoid retrying bad data or permanent rejections | Classify errors explicitly |
| DLQ + reconciliation | Preserve evidence for hard failures | Never assume side effect did not occur |

### 19.1. Retry Budget Differs from Delivery Count

A worker might retry 3 times locally, receive 2 broker redeliveries, and undergo a DLQ replay with 3 more local retries:

~~~text
3 local attempts × 2 broker deliveries + 3 replay attempts
= up to 9 handler attempts
~~~

This is merely an illustrative attempt calculation, not a Spring Integration default. **Coordinate retry budgets across layers** to avoid unbounded retries when each layer sets its own max attempts and hands off to the next.

### 19.2. Keep the Business Key Across All Layers

Even across 9 attempts, `ReservationKey(shop-a, CMD-901, LINE-2, RESERVE_STOCK)` remains **one operation**. Attempt count is diagnostic metadata, never part of the idempotency key.

## 20. Testing Matrix

| Scenario | Input / Progression | What to Assert |
| --- | --- | --- |
| Happy path | First delivery of one command | One commit and one accurate reply |
| Local retry | Commit succeeds, ACK lost | Attempts increase; business commit remains one |
| Broker redelivery | Same command, new envelope | Stable operation key; no extra commit |
| New execution of same command | `RUN-A` → `RUN-B` | New reply group, reused old business result |
| New command for same order/line | New command ID | Not falsely deduplicated when permitted |
| Different tenant, same command ID | `shop-a` and `shop-b` | Separate namespaces, no result leakage |
| Duplicate reply | `LINE-2` twice | Unique count does not increase |
| Conflicting duplicate | `LINE-2` `RESERVED` and `FAILED` | Reject/reconcile, never pick arbitrarily |
| Out-of-order replies | `LINE-3`, `LINE-1`, `LINE-2` | Proper group, completes by unique IDs |
| Missing one reply | 2/3 before deadline | Wait/partial/timeout per policy |
| Zero replies | No group yet | Request deadline watcher emits timeout |
| Late reply after completion | Group already closed | No second final outcome emitted |
| Reaper/group removed | Group metadata purged | Tombstone blocks unauthorized reopening |
| Process restart | Inbox state before/after crash | Durable deduplication/recovery |
| Two instances race | Same key reaches two workers | DB constraint/CAS prevents double commit |
| Retry count reset | Republished from DLQ | Operation key unchanged |
| Request payload conflict | Same key, different quantity | Never returns cached result of another command |
| Header mapping | Across JMS/AMQP/Kafka | Key IDs preserve type and meaning |
| AuthZ spoofing | Client uses another tenant's key | Denied, no cached data leaked |
| Tracing | New span on retry/replay | Linked for investigation without using span ID for dedup |
| Outbox republish | Event published repeatedly | Idempotent consumer/finalizer |
| External system `UNKNOWN` | Timeout after potential commit | Reconciliation; never blindly spawns a new command |

**Best practice:** besides asserting outputs **were produced**, assert side effects **were not repeated**. Do not assert only output message counts when the requirement is “reserve stock exactly once.”

## 21. Observability: Seeing Correlation Across Attempts

If a system only logs `message processed`, it is hard to tell whether two executions were two valid commands or one redelivery.

| Measurement Point | Signal | Purpose |
| --- | --- | --- |
| Ingress | Command accepted/rejected, source, schema version | Catch malformed data |
| Retry advice | Attempts, exception class, retries exhausted | Observe local retries |
| Broker consumer | Redelivery/rebalance/retry-topic volume | Observe transport retries |
| Idempotency layer | New, hit, conflict, in-progress | Measure duplicates and contention |
| Business backend | Operation committed/reused, latency | Know actual side effects |
| Aggregator | Open groups, unique replies, duplicates, late | Spot misgrouping |
| DLQ/replay | Backlog, replay reason, operator actions | Track reprocessing |
| Outbox | Pending age, publication retries | Ensure results are emitted |
| Finalization | `COMPLETE`/`EXPIRED` and final emit count | Prevent double finalization |

An illustrative log entry:

~~~json
{
  "event": "reservation_retry_completed",
  "tenant": "shop-a",
  "commandId": "CMD-2026-901",
  "lineId": "LINE-2",
  "executionId": "RUN-901-A",
  "businessResult": "RESERVED",
  "idempotency": "REUSED",
  "attempt": 2,
  "cause": "REMOTE_ACK_TIMEOUT"
}
~~~

This is an **illustrative application log schema**, not fields auto-generated by Spring Integration. For sensitive data, apply masking/tokenization and access controls. Avoid tagging metrics with command/line/execution IDs due to high cardinality.

## 22. Common Anti-Patterns

| Anti-Pattern | Consequence | Improvement |
| --- | --- | --- |
| Using `MessageHeaders.id` as idempotency key | New envelopes repeat side effects | Stable command/operation identity |
| Using `retryCount` as correlation ID | Each attempt enters a separate group | Keep attempt count as metadata only |
| Using only `orderId` for all operations | New lines/operations falsely skipped | Add `commandId`, `lineId`, `operationType` |
| Generating new `commandId` per attempt | Destroys idempotency | Generate once at producer and persist |
| Hashing raw JSON for deduplication | Metadata/field order causes false negatives | Operation ID or explicit canonical contract |
| Counting `group.size()` as enough replies | Duplicates mask missing items | Unique business item IDs |
| Deleting group and forgetting late replies | New group or second finalization | Tombstones/closed-state |
| Retrying all errors | Validation/permanent errors never succeed | Classify retryable vs terminal |
| Treating HTTP timeout as uncommitted | Side effects may already have occurred | Backend idempotency + status lookup |
| Checking idempotency outside DB transaction before commit | Race between two workers | Unique index/CAS inside consistency boundary |
| Using an in-memory map for durable dedup | State lost on restart/multi-node | Durable store, locks, conflict policy |
| DLQ replay with arbitrary new `commandId` | Repeats business operation | Keep key when replaying same command |
| Using `executionId` as sole operation key | Valid reprocessing duplicates commits | Keep group key and business key separate |
| Trusting client-supplied `correlationId` as authorization | Spoofing/IDOR/cross-tenant leaks | AuthN/AuthZ and trusted validation |
| Treating broker ACK = business success | False conclusions before commit | Track committed outcomes |
| Testing only retry happy paths | Misses ACK-loss window | Inject failure after commit |
| Logging PII or tokens in keys | Data leaks | Opaque stable IDs and secure logging |

## 23. Pre-Deployment Checklist

- [ ] Explicit business command/operation identity defined for every side effect.
- [ ] Operation key includes tenant/source namespace, `commandId`, `itemId`, and `operationType` where needed.
- [ ] Separate **group correlation key** defined for Aggregator/Scatter-Gather executions.
- [ ] Envelope ID, retry count, delivery tag, or trace span never used as business idempotency keys.
- [ ] Producer generates stable `commandId` once and preserves it across local retries, broker redeliveries, and DLQ replays.
- [ ] All incoming identities are validated against authentication/tenant/schema contracts.
- [ ] Policy exists for **same key, different payload**: reject/quarantine/compare request hash.
- [ ] Backend enforces durable idempotency or reconciliation when external APIs lack support.
- [ ] Inbox/outbox and ACK ordering protect against crash windows.
- [ ] `RequestHandlerRetryAdvice` defines retryable exception policies, max attempts, backoff, and timeouts.
- [ ] Cross-layer retry budgets avoid storms and infinite loops.
- [ ] Duplicate/late/out-of-order replies do not cause wrong Aggregator releases or double finalizations.
- [ ] Group store, closed-execution registry, and deadline watchers have retention matching the replay window.
- [ ] Header mappings are tested across JMS/AMQP/Kafka/HTTP if used.
- [ ] Unit/integration tests inject failure **after commit and before ACK**.
- [ ] Monitoring tracks retries, dedup hits, conflicts, stuck in-progress items, and DLQ depth.
- [ ] Logs/traces carry correlation without high-cardinality metric tags or sensitive data leaks.

## 24. Practice Exercise

A payment application receives `PaymentRequested` events carrying `tenantId`, `paymentId`, `commandId`, `executionId`, `amountMinor`, and `currency`. Events are sent to a **Payment Gateway**, and results are later combined in an **Aggregator** alongside fraud check and invoice creation steps.

**Conditions:**

- The same `commandId` can be redelivered by the broker multiple times per transport policy.
- The Gateway can charge successfully and then time out, leaving the worker without a reply.
- An operator can replay the DLQ a day later.
- If a customer intentionally makes a valid new payment, it must carry a new `commandId`.
- Two different `executionId`s may reprocess the same old business command.

**Requirements:**

1. Define `PaymentOperationIdentity`. Explain why `MessageHeaders.id`, Kafka offsets, and retry counts must not be used to prevent double charges.
2. Diagram the retry/redelivery flow and highlight the **charge committed → ACK lost** failure window.
3. Write Java records for `PaymentRequested`, `PaymentOutcome`, and `PaymentOperationKey`.
4. Design a Spring Integration `RequestHandlerRetryAdvice` with retryable and retry-exhaustion policies.
5. Design durable idempotency at the Payment Gateway or payment-owning DB with unique constraints and a request fingerprint.
6. Write tests: local retry after ACK loss, broker redelivery, DLQ replay, conflicting amount with same command ID, and valid new command.
7. Define the correlation group for fraud/payment/invoice replies by `executionId`; prevent a duplicate payment reply from counting as a third component.
8. For late replies after Aggregator completion, describe tombstones/reconciliation and how to prevent emitting a second final outcome.
9. If the Payment Gateway lacks an idempotency API yet has a transaction-lookup API, design pre-retry reconciliation to reduce double-charge risk.
10. Propose safe logging/metrics: retries, unique business operations, dedup hits, conflicts, timeouts, DLQ, and late replies—without logging sensitive payment details.

**Hint:** Use **one immutable business operation key** for the charge, a **separate execution ID** for the group, and **separate transport metadata** for diagnostics. Ensure no retry layer regenerates a new business intent when merely redelivering the same message.

## 25. Summary

**Correlation across retries and redelivery** requires distinguishing **“the same work”** from **“the same message delivery.”** Message envelopes, broker delivery tags, and attempt counts can change; **business operation identity** must stay stable when a command is retried or replayed. Meanwhile, the **Aggregator's correlation group** can change when a workflow is reprocessed, while the **idempotency key** must continue protecting the same command's side effect.

With Spring Integration, you can use Java DSL and `RequestHandlerRetryAdvice` for handler-level retries, combined with **deduplication/inbox, idempotent backends, durable transactions/outbox, error channels, DLQ replay policies, and a closed-group registry**. When a part is redelivered, the Aggregator counts **unique item results** rather than raw message counts; when replies arrive late, it never emits a second final result. The desired outcome is not just routing messages to the right branch, but achieving **the right business operation, the right correlation group, the exact intended side-effect count, and full traceability across every attempt**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Correlation Identifier, Message Sequence, Idempotent Receiver, Aggregator, Request-Reply, Guaranteed Delivery); Spring Integration documentation on Request Handler Advice/Retry, Aggregators, Message Channels, Error Handling, Message Stores, Java DSL, and Testing; Spring Retry documentation on `RetryTemplate`, `RetryPolicy`, and `BackOffPolicy`; Java SE documentation on `record`, `ConcurrentHashMap`, and concurrency primitives.
