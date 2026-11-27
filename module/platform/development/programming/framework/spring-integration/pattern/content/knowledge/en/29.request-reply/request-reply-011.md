# Request-Reply Over Asynchronous Systems

> **Chapter:** Request reply  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. Practice Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing processing branches. This lesson focuses on **designing request–reply when requests and results traverse queues, topics, executors, or distributed systems**, where the sender, processor, and reply receiver may operate at different times.

## 1. Learning Objectives

After this lesson, you can:

1. Explain why **request–reply is a communication contract**, not a requirement that the transport be synchronous.
2. Distinguish **internal asynchronous processing where the caller still awaits a reply** from an **end-to-end asynchronous protocol** (accepted → later result).
3. Design a request envelope containing `requestId`, `operationId`, `correlationId`, `replyTo`, `deadline`, `schemaVersion`, and source identity, and identify **which fields are issued by trusted parties**.
4. Build the path request queue → worker → reply queue/topic → caller/registry; handle multiple concurrent pending requests without mixing replies.
5. Select appropriate Gateway, Service Activator, channels, message adapters, and reply correlation in Spring Integration; understand limits of local temporary `replyChannel` versus a remote broker.
6. Separate **ACK**, **accepted**, **processed**, **committed**, and **reply delivered** into distinct events.
7. Design timeouts/deadlines, pending state, late/duplicate replies, backpressure, retries, DLQs, and reconciliation without triggering duplicate side effects.
8. Write Java 17 and Spring Integration Java DSL illustrating an async handler, typed reply result, unit/integration tests, and a production test matrix.
9. Combine request–reply correlation with Splitter/Aggregator, Router, Filter, error channel, and idempotent receiver in complex workflows.

## 2. Scenario: Reservation Command Through a Queue, Reply Arriving Later

The Order Service application sends a command:

~~~json
{
  "tenantId": "shop-a",
  "operationId": "RSV-901",
  "requestId": "req-7f31",
  "orderId": "ORD-901",
  "sku": "BOOK-42",
  "quantity": 2
}
~~~

The Inventory Worker processes the request, potentially calling a database/warehouse or taking hundreds of milliseconds to several seconds. Once a business outcome is ready, the Worker sends:

~~~json
{
  "requestId": "req-7f31",
  "operationId": "RSV-901",
  "orderId": "ORD-901",
  "status": "RESERVED",
  "reasonCode": null
}
~~~

When requests and replies traverse a broker, **no Java stack frame spans both services**. Order Service must know **which request attempt** reply `req-7f31` belongs to, whether it is still waiting, and whether the `RESERVED` outcome corresponds to the requested **operation**.

~~~mermaid
sequenceDiagram
    participant C as Order Service
    participant RQ as Request queue
    participant W as Inventory Worker
    participant DB as Inventory DB
    participant RP as Reply queue
    C->>C: Register pending(req-7f31)
    C->>RQ: ReserveCommand + correlation/replyTo
    RQ-->>C: Broker accepted (not business success)
    RQ->>W: Deliver request
    W->>DB: Reserve with operationId=RSV-901
    DB-->>W: Committed result
    W->>RP: ReserveReply(req-7f31, RESERVED)
    RP->>C: Deliver reply
    C->>C: Match pending + validate + complete
~~~

### 2.1. Why Doesn't a Reply Automatically Return to the Sender?

An HTTP call over a single TCP connection typically has an obvious response path. A queue/topic, however, only knows **which destination a message was published to**. It has no inherent awareness of which JVM/process holds a waiting Java call.

You need one of the following:

- `replyTo` or a controlled reply destination to know **where to send the response**.
- `requestId`/correlation key to know **which request the reply belongs to**.
- A pending registry or workflow state store to link the reply back to the waiting caller or persisted state.
- A timeout/expiration policy if the reply never arrives or arrives late.

### 2.2. Enqueueing a Request Does Not Mean Stock Reservation Succeeded

~~~text
Publisher send success
    != Consumer received
    != Handler completed
    != DB transaction committed
    != Reply published
    != Caller received reply
~~~

No step automatically implies all subsequent steps occurred. That is why an `ACCEPTED` outcome is often more truthful than `RESERVED` when the system has only enqueued the request.

## 3. Two "Asynchronous" Models to Distinguish

### 3.1. Internally Async, Caller Still Invokes Request–Reply

~~~text
Java caller: ReserveReply reply = gateway.reserve(command);
        | blocks/waits
        v
Messaging Gateway -> ExecutorChannel / broker
                              |
                              v
                         Worker handles
                              |
                              v
                         Reply to Gateway
        |
        v
Java caller receives ReserveReply
~~~

The worker may run on a separate thread or process, yet the caller still waits until a reply arrives or times out. A `@MessagingGateway` returning a POJO is a straightforward example.

**Pros:** simple API for the caller, compatible with synchronous logic.  
**Trade-offs:** caller ties up resources while waiting; timeouts, late replies, and concurrency limit scalability.

### 3.2. Async End-to-End: Accept First, Result Later

~~~text
POST /reservations
  -> validate/auth + enqueue
  <- HTTP 202 Accepted + operationId

Later:
  Worker commits / rejects reservation
  -> publishes ReservationOutcome

Caller:
  GET /reservations/{operationId}
  or receives webhook / subscription result
~~~

Here, there is no need to hold an HTTP/Gateway thread waiting for the entire task. Results are retrieved via a **status API**, subscription, webhook, or event topic.

**Pros:** fits long-running work, survives restarts, reduces open waiting requests.  
**Trade-offs:** requires managing operation lifecycle, versioning, callback/status retries, auth, and reconciliation.

### 3.3. Do Not Call Both "Fire-and-Forget"

| Model | Business Reply Exists? | Caller Waits? | What Is Needed |
| --- | --- | --- | --- |
| Direct request–reply | Yes | Usually yes | Reply destination and timeout |
| Async worker, sync Gateway | Yes | Yes, up to deadline | Correlation, bounded waiting |
| Async end-to-end | Yes, arrives later | Does not need to block | Operation status / callback / event |
| One-way event/command | Not under that interaction's contract | No | Never infer business success from send |
| Scatter-Gather | May yield aggregated reply | Depends on interface | Group correlation, release policy |

"Async" describes **execution scheduling**; "reply" describes **protocol contract**. Request–reply can run entirely over asynchronous messaging.

## 4. Anatomy of Request and Reply Envelopes

Beyond the business payload, distributed systems usually need an explicit envelope.

~~~text
RequestEnvelope
  requestId                req-7f31
  operationId              RSV-901
  businessCorrelationId    ORD-901
  tenantId                 shop-a
  producerId               order-service
  schemaVersion            reserve-command-v1
  replyTo                  inventory.replies.order-service
  deadlineAt               2026-11-21T08:00:15Z
  payload                  ReserveCommand(...)

ReplyEnvelope
  correlationId            req-7f31
  operationId              RSV-901
  tenantId                 shop-a
  producerId               inventory-service
  schemaVersion            reserve-reply-v1
  status                   RESERVED / REJECTED / UNKNOWN
  payload                  ReserveReply(...)
~~~

### 4.1. Meaning of Each Key

| Field | Used For | Notes |
| --- | --- | --- |
| `requestId` | Identifying **one request–reply exchange** | May be fresh for a new API invocation |
| Reply `correlationId` | Linking the reply back to the exact request | Equals `requestId` in this example |
| `operationId` | Idempotency of **one business mutation** | Must remain stable across retries of the same command |
| `businessCorrelationId` | Tracing multiple steps of the same order/case | Can span multiple operations |
| `executionId` | Grouping child replies of one workflow run | Critical for Aggregator |
| `tenantId` | Namespace and authorization scope | Must be verified; never trust self-declared strings |
| `producerId` | Authenticated emitting source | Derived from trusted transport identity/registry |
| `replyTo` | Reply destination | Never accept arbitrary external queues/topics |
| `deadlineAt` | Exchange expiration deadline | Not an automatic transactional cancellation |
| `schemaVersion` | Selecting decoder/contract | Version request and reply separately |
| Transport message ID/offset | Delivery metadata | Not an operation idempotency key |

### 4.2. Can `requestId` Change on Retry?

It depends on which layer retries:

- **Broker redelivery of the same request:** normally keeps both `requestId` and `operationId`, while delivery metadata/offset may change.
- **Caller opens a new exchange after timeout:** may mint a new `requestId` for the new pending wait, **but must keep `operationId`** if it represents the same business command.
- **A genuinely new business command:** needs a new `operationId` and explicit intent.

Never collapse all three into `UUID.randomUUID()` generated inside every Handler invocation.

### 4.3. Header and Payload Must Agree

If `payload.operationId=RSV-901` while `header.operationId=RSV-902`, never arbitrarily pick one to process. Define field authority, verify provenance, and reject with `OPERATION_ID_CONFLICT` or apply an audited policy.

A matching `correlationId` alone is **insufficient** to accept a reply. Also verify tenant, expected operation, producer identity, valid schema/status, and permission to read the result.

## 5. States: Never Confuse Accepted Commands with Completed Commands

An explicit state machine prevents callers from assuming "timed out means never processed."

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> PENDING: validate + register/persist
    PENDING --> DISPATCHED: publish request
    DISPATCHED --> PROCESSING: worker accepted
    PROCESSING --> COMPLETED: business commit + outcome
    PROCESSING --> REJECTED: terminal business decision
    DISPATCHED --> TIMED_OUT: wait deadline exceeded
    PROCESSING --> TIMED_OUT: wait deadline exceeded
    TIMED_OUT --> COMPLETED: late successful outcome
    TIMED_OUT --> REJECTED: late business rejection
    PENDING --> FAILED_DISPATCH: publish failed
    COMPLETED --> [*]
    REJECTED --> [*]
    FAILED_DISPATCH --> [*]
~~~

**Conceptual diagram:** `TIMED_OUT` may represent only the **waiting exchange** state, not the terminal state of the operation. Production systems usually separate them cleanly:

- **Exchange/wait state:** `WAITING`, `TIMED_OUT`, `DELIVERED`.
- **Business operation state:** `RECEIVED`, `PROCESSING`, `COMPLETED`, `REJECTED`, `UNKNOWN`.

A late reply can transition the **business operation** to `COMPLETED` even if the initial HTTP request timed out. Combining both into one enum and locking `TIMED_OUT` as "business FAILED" corrupts reconciliation.

### 5.1. The `UNKNOWN` Business State

`UNKNOWN` is useful when a request may have committed yet the caller/broker received no proof. Never automatically turn every timeout into `REJECTED` or blindly retry under a new operation ID.

### 5.2. Terminal Rejections Differ from Retryable Technical Errors

| State / Error | Retry Same Business Command? | Action |
| --- | --- | --- |
| `REJECTED: INVALID_QUANTITY` | No, not with identical data | Fix input or return user error |
| `REJECTED: UNAUTHORIZED` | No, never to bypass security | Verify permissions |
| `COMPLETED: RESERVED` | Do not execute effect again | Return persisted outcome |
| `UNKNOWN after timeout` | Can poll status / retry with same key | Reconcile before side effects |
| Broker unavailable | Bounded retry while ensuring publish status | Backoff + monitoring |
| Worker crash after commit | Redeliver with same operation key | Idempotent receiver |
| Reply queue unavailable | Retry publishing result; do not re-reserve | Outbox/reply repair |

## 6. Correlation: Matching Replies to the Right Request

With 10,000 pending requests, replies can arrive **out of order**:

~~~text
Request order:  A, B, C, D
Reply order:    D, B, A, C
~~~

If a listener simply uses a shared `QueueChannel` and hands the "first reply" to the "first caller," data gets mixed up. Correlation must be an explicit map:

~~~text
pending[req-A] -> waiting caller A
pending[req-B] -> waiting caller B
pending[req-C] -> waiting caller C
pending[req-D] -> waiting caller D

reply(correlationId=req-D) -> complete only pending[req-D]
~~~

### 6.1. Within What Scope Must a Correlation ID Be Unique?

A high-entropy UUID `requestId` may be practically globally unique, yet safe logic must still scope by:

~~~text
(tenantId, requester/service namespace, requestId)
~~~

Never allow one tenant to consume another tenant's reply just by knowing a `requestId`. When multiple app instances consume a reply topic, ensure **replies reach the instance holding the waiter** or use **shared state** to complete the exchange accurately.

### 6.2. When Is `replyTo` Needed?

Across a broker, the Worker typically does not know where the caller is running. `replyTo` can be:

- A queue provisioned/allowlisted for the calling service.
- A shared topic with a per-tenant/service partition or routing key.
- An adapter-managed temporary reply queue with a clear lifecycle.
- Omitted if the protocol uses **one default result topic** known to both sides.

**Security warning:** never read `replyTo` from untrusted JSON/HTTP headers and send sensitive results to an arbitrary destination. Maintain a registry mapping producer identity → allowed reply destinations, IAM/ACLs, and validation.

### 6.3. Request Correlation Across JMS/AMQP/Kafka

| Transport | Protocol Primitives | What Not to Confuse |
| --- | --- | --- |
| JMS | `JMSReplyTo`, `JMSCorrelationID`, `JMSMessageID` | Message ID is not automatically a business operation ID |
| AMQP | reply-to/correlationId properties, reply queues, broker acks | ACK is not a business outcome |
| Kafka | request/reply topics, record headers/key, partition/offset | Offsets are unstable across retry topics |
| HTTP async | operation resource, webhook/polling | HTTP 202 is not completion |
| Spring in-JVM | Gateway-managed `replyChannel` header/temporary channel | Java channel objects do not serialize across brokers |

There is no automatic 1:1 mapping across every protocol. When using Spring Integration outbound/inbound Gateways or adapters, explicitly configure **header mappers**, serializers, response channels, and versions, then test against a real broker.

## 7. Timeouts, Deadlines, and Late Replies

Request–reply over an async worker needs at least three bounds:

1. **Send/publish timeout:** unable to place the request onto the channel/broker in time.
2. **Reply wait timeout:** caller/Gateway receives no reply within the wait window.
3. **Business operation deadline:** past this timestamp, business rules may prefer not executing **if not yet committed**.

These limits are **not identical**. A Gateway with `defaultReplyTimeout=3s` does not automatically cancel the worker after 3 seconds.

### 7.1. Timeline with a Late Reply

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant W as Worker
    participant DB as DB
    C->>G: reserve(RSV-901)
    G->>W: request(req-7f31)
    Note over G: Wait up to 3s
    G-->>C: Timeout at 3s
    W->>DB: Commit at 5s
    DB-->>W: RESERVED
    W-->>G: Reply at 6s
    Note over G: Original waiter gone
~~~

**Never conclude automatically:** caller timeout means the worker stopped, the request was canceled, or inventory was left untouched.

### 7.2. Deadline Propagation

An envelope carrying `deadlineAt` lets the Worker decide whether it is **allowed to start** or should reject an already-expired request. Still, a race always exists between checking the deadline and committing; if strict cancellation is required, enforce transactions, state machines, and explicit cancellation at the business owner.

Do not rely on a single machine's wall clock when services experience clock skew. Define UTC instants, synchronize clocks, and enforce margins/authority at boundaries.

### 7.3. Four Policies for Handling Late Replies

| Policy | When to Use | Caveat |
| --- | --- | --- |
| **Ignore for expired waiter** | Old caller closed, no need to unblock | Still update operation status if committed |
| **Persist outcome** | Supports polling/reconciliation | Enforce proper auth and retention |
| **Notify via callback/event** | Async end-to-end | Handle delivery/retry/duplicate callbacks |
| **Compensate** | Business allows reversing the effect | Not every effect is reversible |

Never deliver a late reply to a **new request** merely because both messages share `orderId`. Always verify `requestId`/operation identity and permissions.


## 8. Spring Integration: Async Worker While Gateway Still Returns a Result

This example demonstrates **in-JVM asynchronous execution** to illustrate how a Messaging Gateway preserves request–reply when the handler runs on an executor thread. It does **not** replace a durable broker queue and does not preserve pending state across process restarts.

### 8.1. Request and Reply DTOs in Java 17

~~~java
import java.util.Objects;

record ReserveCommand(
    String tenantId,
    String requestId,
    String operationId,
    String orderId,
    String sku,
    int quantity
) {
    ReserveCommand {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(operationId, "operationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(sku, "sku");
    }
}

record ReserveReply(
    String tenantId,
    String requestId,
    String operationId,
    String orderId,
    String status,
    String reasonCode,
    String workerThread
) {
    ReserveReply {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(operationId, "operationId");
        Objects.requireNonNull(status, "status");
    }
}
~~~

Here `requestId` illustrates exchange identity. Inside an in-JVM Gateway, the framework also manages internal reply routing/correlation; when moving to a **remote broker**, design correlation/idempotency contracts independent of Java object references.

### 8.2. Service Activator Simulating a Worker

~~~java
final class ReservationWorker {

    public ReserveReply reserve(ReserveCommand cmd) {
        String worker = Thread.currentThread().getName();

        // Demo only computes result; performs no DB mutation.
        if (cmd.tenantId().isBlank()
                || cmd.requestId().isBlank()
                || cmd.operationId().isBlank()
                || cmd.orderId().isBlank()
                || cmd.sku().isBlank()) {
            return new ReserveReply(
                cmd.tenantId(), cmd.requestId(),
                cmd.operationId(), cmd.orderId(),
                "REJECTED", "MISSING_FIELD", worker);
        }

        if (cmd.quantity() < 1 || cmd.quantity() > 500) {
            return new ReserveReply(
                cmd.tenantId(), cmd.requestId(),
                cmd.operationId(), cmd.orderId(),
                "REJECTED",
                "INVALID_QUANTITY", worker);
        }

        return new ReserveReply(
            cmd.tenantId(), cmd.requestId(),
            cmd.operationId(), cmd.orderId(),
            "RESERVED", null, worker);
    }
}
~~~

**Note:** `RESERVED` in this demo does not prove stock was reserved in a DB. When replacing with a real service, enforce transactions + idempotency at the business owner rather than placing "deduct stock again" logic inside a retryable handler.

### 8.3. Gateway Interface

~~~java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
    defaultRequestChannel = "reservations.async.requests",
    defaultRequestTimeout = "500",
    defaultReplyTimeout = "3000")
interface ReservationGateway {

    ReserveReply reserve(ReserveCommand command);
}
~~~

In this example, the method returns `ReserveReply`: **the caller waits**. The worker runs on a different thread, yet the caller's Java API remains synchronous. `defaultReplyTimeout` is for demo purposes; with `DirectChannel` or blocking I/O, effective deadlines may differ. Verify on your actual topology.

### 8.4. Java DSL and ExecutorChannel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class AsyncReservationFlowConfiguration {

    @Bean
    ThreadPoolTaskExecutor reservationExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();
        pool.setThreadNamePrefix("reserve-worker-");
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(32);
        return pool;
    }

    @Bean("reservations.async.requests")
    ExecutorChannel asyncRequestChannel(
            ThreadPoolTaskExecutor reservationExecutor) {
        return new ExecutorChannel(reservationExecutor);
    }

    @Bean
    ReservationWorker reservationWorker() {
        return new ReservationWorker();
    }

    @Bean
    IntegrationFlow processReservations(
            ReservationWorker worker) {
        return IntegrationFlow
            .from("reservations.async.requests")
            .handle(worker, "reserve")
            // Do not attach a static output channel that blocks
            // the Gateway's reply route in request metadata.
            .get();
    }
}
~~~

**Flow semantics:**

1. Gateway converts `reserve(command)` into a request message with an internal reply route.
2. `ExecutorChannel` dispatches to a thread owned by `reservationExecutor`.
3. `ReservationWorker.reserve` runs as a Service Activator and returns `ReserveReply`.
4. The handler/flow sends the reply back to the route awaited by the Gateway per endpoint semantics.
5. Gateway receives the reply and converts the payload to `ReserveReply` for the caller.

### 8.5. Why Not Just Use `DirectChannel`?

`DirectChannel` typically invokes the handler on the sender's thread: behavior can still be request–reply, but it **does not illustrate running the worker on a separate thread**. `ExecutorChannel` makes the async boundary, capacity constraints, thread context, and deadlines explicit.

**Never** choose an unbounded executor. When the queue/pool fills up, sending requests can be rejected; you need bounded capacity, metrics, backpressure, and appropriate error/HTTP 429/503 responses. This code is a demo and does not configure broker durability.

### 8.6. What If the Handler Returns `null`?

A handler returning `null` normally **produces no ordinary reply**. The waiting Gateway may time out or the flow may raise an error if `requiresReply` is configured on the handler. For business rejections, return `ReserveReply(status="REJECTED")` with a reason rather than `null`.

## 9. JUnit 5: Proving Async Execution While Keeping Request–Reply Accurate

### 9.1. Unit Tests for the Worker

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ReservationWorkerTest {

    private final ReservationWorker worker =
        new ReservationWorker();

    private static ReserveCommand command(int quantity) {
        return new ReserveCommand(
            "shop-a", "req-101", "RSV-101",
            "ORD-101", "BOOK-42", quantity);
    }

    @Test
    void acceptsValidCommand() {
        ReserveReply reply = worker.reserve(command(2));

        assertEquals("req-101", reply.requestId());
        assertEquals("RSV-101", reply.operationId());
        assertEquals("RESERVED", reply.status());
        assertNull(reply.reasonCode());
    }

    @Test
    void rejectsQuantityWithTypedReply() {
        ReserveReply reply = worker.reserve(command(0));

        assertEquals("REJECTED", reply.status());
        assertEquals("INVALID_QUANTITY", reply.reasonCode());
    }
}
~~~

### 9.2. Integration Tests with Spring Context

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(AsyncReservationFlowConfiguration.class)
class AsyncReservationGatewayIntegrationTest {

    @Autowired
    ReservationGateway gateway;

    private static ReserveCommand command(
            String requestId, String operationId,
            int quantity) {
        return new ReserveCommand(
            "shop-a", requestId, operationId,
            "ORD-901", "BOOK-42", quantity);
    }

    @Test
    void receivesTypedReplyFromExecutorThread() {
        ReserveReply reply = gateway.reserve(
            command("req-a", "RSV-901", 2));

        assertNotNull(reply);
        assertEquals("req-a", reply.requestId());
        assertEquals("RSV-901", reply.operationId());
        assertEquals("RESERVED", reply.status());

        // Thread name shows dispatch through ExecutorChannel.
        assertTrue(
            reply.workerThread().startsWith("reserve-worker-"));
    }

    @Test
    void businessRejectionStillReturnsReply() {
        ReserveReply reply = gateway.reserve(
            command("req-b", "RSV-902", -3));

        assertEquals("req-b", reply.requestId());
        assertEquals("REJECTED", reply.status());
        assertEquals(
            "INVALID_QUANTITY", reply.reasonCode());
    }
}
~~~

### 9.3. Limitations of the Integration Test

- This is a **single-JVM test**; Spring Gateway and `ExecutorChannel` manage replies internally.
- It does not prove requests/replies survive process crashes, Kafka/JMS/AMQP serialization, ACLs, DLQs, or database commits.
- Worker thread naming confirms dispatch through the executor, not that all messages run on one fixed thread or execute in order.
- This test does not create a controlled timeout; testing late replies requires a **latch-controlled worker** and explicit reply timeout, avoiding arbitrary `Thread.sleep(...)` calls that flake in CI.

### 9.4. Testing Concurrency and Correlation

An advanced integration test should exercise many concurrent calls:

~~~text
Given:
  100 requests with distinct requestId and operationId
  20 concurrent callers
  worker reply times intentionally reordered

Assert:
  for each caller:
    reply.requestId == its own request.requestId
    reply.operationId == its own operationId
  no reply delivered to another caller
  timeout/rejection handled independently
~~~

When using a shared reply queue/topic or multiple service instances, verify correlation **after serialization and receipt**, not only inside a single Gateway proxy.

## 10. Designing Request–Reply Over a Real Broker

The following pattern applies to messaging systems with a request destination, reply destination, and at-least-once delivery. Exact header attachment depends on the AMQP/JMS/Kafka adapter; this is a **logical protocol**, without assuming a single provider automates every step.

~~~mermaid
flowchart TD
    API["Order API / Gateway"] --> STATE[("Operation + pending state")]
    API --> OUT[("Outbox request")]
    OUT --> PUB["Request publisher"]
    PUB --> REQQ[("inventory.requests queue/topic")]
    REQQ --> WORK["Inventory worker + inbox/idempotency"]
    WORK --> DB[("Inventory DB")]
    WORK --> OREPLY[("Outbox reply")]
    OREPLY --> REPLYQ[("order-service.replies")]
    REPLYQ --> LIST["Reply listener"]
    LIST --> VALID["Validate producer/correlation/schema/tenant"]
    VALID --> STATE
    STATE --> STATUS["Status API / webhook / pending waiter"]
~~~

### 10.1. What Is the Sender (Requester) Responsible For?

1. Authenticate the caller and create/validate `operationId` (stable business identity).
2. Create `requestId` for the exchange and record its mapping to the operation.
3. **Persist operation/pending metadata** if state must survive restarts.
4. Write the request to an **outbox in the same transaction** as the operation record when atomic state + publish intent is needed.
5. Publish the request envelope with schema version, correlation, deadline, and allowlisted reply destination.
6. Run a reply listener that reads outcomes, authenticates the source, and matches correlation.
7. Return status to callers / complete pending futures if still waiting.
8. Clean up pending waiters by TTL, but **never delete business operation status** just because a caller timed out.

### 10.2. What Is the Processor (Responder) Responsible For?

1. Consume the request; validate schema/version and authenticated source.
2. Check deadline/policy/authorization; never trust arbitrary `tenantId`/`replyTo` values.
3. Deduplicate the business operation by `(tenantId, operationId)` and request fingerprint.
4. Execute the side effect once within the strongest achievable consistency boundary.
5. Persist the outcome, then publish a reply with `correlationId=requestId`.
6. If publishing the reply fails after commit, retry **emitting the reply**, never re-running the effect.
7. If the request is redelivered, return the stored outcome for the current valid exchange.
8. Manage retries, DLQs, poison messages, and reconciliation.

### 10.3. A New `requestId` Can Receive the Same Persisted Business Result

~~~text
First exchange:
  requestId = req-a
  operationId = RSV-901
  outcome committed but reply lost

Second exchange:
  requestId = req-b
  operationId = RSV-901  (SAME mutation)
  worker returns persisted RESERVED
  reply correlationId = req-b
~~~

Here the responder **creates no new side effect**, yet still emits a **fresh reply** for the new exchange. That avoids mistakenly delivering `req-a`'s reply into `req-b`'s waiter.

### 10.4. Reply Publishing Must Not Sit Inside a "Re-Reserve" Retry

A flawed implementation:

~~~java
// Wrong when retrying publisher by re-invoking the entire handler
void onRetry(ReserveCommand command) {
    warehouse.reserveStock(command); // may repeat effect
    broker.sendReply(buildReply(command));
}
~~~

A sound design separates **business operation outcome** from **reply delivery attempts**, such as persisting the outcome and using a reply outbox so the publisher can retry multiple times without touching inventory again.

## 11. Java 17: In-Memory Registry to Understand Correlation

To make clear how many pending requests match out-of-order replies, we can write a small `CompletableFuture`-based registry. This example is **for a single JVM only** and does not replace durable registries, authentication, or distributed correlation routing.

### 11.1. Properly Scoped Pending Key

~~~java
record PendingKey(
    String tenantId,
    String requesterId,
    String requestId
) {}

record ExpectedReply(
    String operationId,
    java.util.concurrent.CompletableFuture<ReserveReply> future
) {}
~~~

### 11.2. Registry with Register-Before-Publish

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;

final class PendingReplyRegistry {

    private final ConcurrentMap<PendingKey, ExpectedReply> pending =
        new ConcurrentHashMap<>();

    CompletableFuture<ReserveReply> register(
            PendingKey key, String operationId,
            Duration timeout) {
        CompletableFuture<ReserveReply> future =
            new CompletableFuture<>();
        ExpectedReply expected =
            new ExpectedReply(operationId, future);

        if (pending.putIfAbsent(key, expected) != null) {
            throw new IllegalStateException(
                "DUPLICATE_REQUEST_ID");
        }

        // Timeout only closes the waiter; it DOES NOT cancel the remote worker.
        future.orTimeout(
                timeout.toMillis(), TimeUnit.MILLISECONDS)
            .whenComplete((reply, error) ->
                pending.remove(key, expected));

        return future;
    }

    boolean onReply(
            PendingKey key, ReserveReply reply) {
        ExpectedReply expected = pending.get(key);
        if (expected == null) {
            // Late reply or waiter already gone.
            return false;
        }

        if (!key.tenantId().equals(reply.tenantId())
                || !key.requestId().equals(reply.requestId())
                || !expected.operationId().equals(
                    reply.operationId())) {
            // Never complete the wrong waiter.
            return false;
        }

        // Only one complete wins; duplicate -> false.
        return expected.future().complete(reply);
    }

    void failBeforePublish(
            PendingKey key, Throwable cause) {
        ExpectedReply expected = pending.get(key);
        if (expected != null) {
            expected.future().completeExceptionally(cause);
        }
    }
}
~~~

**Mandatory rule:** call `register(...)` **before** publishing, because a very fast reply can arrive right after publish. If you register the waiter after publishing, the reply listener may receive the result, find no pending entry, and drop it.

### 11.3. Limitations of the In-Memory Design

- The registry disappears if the JVM dies, and no instance can complete another JVM's waiter.
- `CompletableFuture.orTimeout` closes only the **waiting future**, not the remote operation or broker delivery.
- `onReply` checks identity fields but does not itself authenticate the **producer**. The listener must verify source via broker identity, schema, and ACLs before calling it.
- Because pending entries have a TTL, late replies must feed into **business status persistence/reconciliation**, not simply be discarded.
- Call `failBeforePublish` only when you are certain the message **was never published**. A publisher timeout after the broker may already have received the request is an **UNKNOWN** state, not unsent.
- Validate `Duration` (reject negative or excessively large timeouts); production needs bounds, resource limits, and metrics to prevent memory exhaustion.
- Failing the waiter via `CompletableFuture.completeExceptionally` does not mean marking the business operation `FAILED`.

### 11.4. Usage Example

~~~java
PendingKey key = new PendingKey(
    "shop-a", "order-service", "req-7f31");

// Register first:
var awaiting = registry.register(
    key, "RSV-901", java.time.Duration.ofSeconds(3));

// Publish request envelope with requestId=req-7f31.
// Reply listener receives and authenticates producer.
// Then:
registry.onReply(key, new ReserveReply(
    "shop-a", "req-7f31", "RSV-901",
    "ORD-901", "RESERVED", null, "inventory-worker"));

// The waiting caller can now get the typed reply.
ReserveReply reply = awaiting.join();
~~~

The snippet above shows **operation ordering** and the registry API; `registry` is assumed to exist in the fixture. Do not copy it as production broker-handling code without persistence, auth, scheduling, and a late-reply policy.


## 12. Testing the Correlation Registry Under Out-of-Order Replies

Even an in-memory registry needs race testing. The JUnit 5 tests below verify two independent requests without using `Thread.sleep` to "fake concurrency."

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;

class PendingReplyRegistryTest {

    private final PendingReplyRegistry registry =
        new PendingReplyRegistry();

    private static ReserveReply reply(
            String requestId, String operationId) {
        return new ReserveReply(
            "shop-a", requestId, operationId,
            "ORD-901", "RESERVED", null, "worker");
    }

    @Test
    void outOfOrderRepliesCompleteCorrectWaiters() {
        PendingKey keyA =
            new PendingKey("shop-a", "order-service", "req-a");
        PendingKey keyB =
            new PendingKey("shop-a", "order-service", "req-b");

        CompletableFuture<ReserveReply> pendingA =
            registry.register(
                keyA, "RSV-A", Duration.ofSeconds(5));
        CompletableFuture<ReserveReply> pendingB =
            registry.register(
                keyB, "RSV-B", Duration.ofSeconds(5));

        // B replies before A: B's reply must not go to A.
        assertTrue(registry.onReply(
            keyB, reply("req-b", "RSV-B")));
        assertTrue(registry.onReply(
            keyA, reply("req-a", "RSV-A")));

        assertEquals("RSV-A",
            pendingA.join().operationId());
        assertEquals("RSV-B",
            pendingB.join().operationId());
    }

    @Test
    void wrongOperationMustNotCompleteWaiter() {
        PendingKey key =
            new PendingKey("shop-a", "order-service", "req-a");
        CompletableFuture<ReserveReply> awaiting =
            registry.register(
                key, "RSV-A", Duration.ofSeconds(5));

        assertFalse(registry.onReply(
            key, reply("req-a", "RSV-OTHER")));
        assertFalse(awaiting.isDone());

        assertTrue(registry.onReply(
            key, reply("req-a", "RSV-A")));
        assertEquals("RSV-A",
            awaiting.join().operationId());
    }

    @Test
    void duplicateReplyIsNotDeliveredTwice() {
        PendingKey key =
            new PendingKey("shop-a", "order-service", "req-a");
        CompletableFuture<ReserveReply> awaiting =
            registry.register(
                key, "RSV-A", Duration.ofSeconds(5));

        assertTrue(registry.onReply(
            key, reply("req-a", "RSV-A")));
        assertFalse(registry.onReply(
            key, reply("req-a", "RSV-A")));

        assertEquals("RESERVED",
            awaiting.join().status());
    }
}
~~~

The third test does not prove the **business effect** committed only once; it only shows the local pending waiter completed once. Test idempotency at the DB/business owner separately.

### 12.1. Testing Timeouts Without Flaky Sleeps

A negative test can register a short timeout and expect `CompletableFuture` to fail exceptionally:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.CompletionException;
import org.junit.jupiter.api.Test;

@Test
void timeoutClosesWaiterButNotRemoteOperation() {
    PendingReplyRegistry registry =
        new PendingReplyRegistry();
    PendingKey key =
        new PendingKey("shop-a", "order-service", "req-timeout");

    var future = registry.register(
        key, "RSV-901", Duration.ofMillis(50));

    assertThrows(
        CompletionException.class, future::join);

    // A late reply cannot complete the old waiter.
    assertFalse(registry.onReply(
        key, new ReserveReply(
            "shop-a", "req-timeout", "RSV-901",
            "ORD-901", "RESERVED", null, "worker")));
}
~~~

This snippet only tests Java-level future timeout, **without** dispatching messages or canceling workers. For large CI suites, use appropriate timeout/clock abstractions and scheduler injection to prevent timing flakiness.

### 12.2. Security Tests: Wrong Tenant or Request ID

Add fixtures with a reply having `tenantId=shop-b` while `PendingKey` belongs to `shop-a`, or a reply with `requestId=req-other`. `onReply` must return `false` and leave `shop-a`'s pending waiter uncompleted.

Still, verify **authenticated producer** in the listener; anyone able to publish forged replies with valid IDs can corrupt outcomes unless ACLs, producer authentication, or signature/channel validation are enforced.

## 13. Durable Request Submission: Never Publish to Broker Before Persisting the Operation

In systems that must not lose work on crashes, operation order is critical.

### 13.1. How Messages Are Easily Lost

~~~text
1. HTTP handler inserts operation=PENDING into DB.
2. It commits DB transaction.
3. Process crashes BEFORE publishing broker request.
4. Operation remains PENDING forever.
~~~

Or in reverse order:

~~~text
1. Publish broker request successfully.
2. Process crashes BEFORE persisting operation.
3. Worker processes; reply returns but no state exists.
~~~

Two independent systems (DB and broker) do not share an atomic commit. When durability is required, use a **transactional outbox** or another proven consistency pattern.

### 13.2. Outbox on the Requester

~~~text
BEGIN DATABASE TRANSACTION
  insert/get operation(tenantId, operationId, status=RECEIVED)
  reject mismatched request fingerprint for reused operationId
  insert outbox message(
    requestId, operationId,
    destination=inventory.requests,
    payload, schemaVersion
  )
COMMIT

Outbox publisher:
  read unpublished rows
  send request to broker
  mark published / retry safely
~~~

This durably links **publish intent** with operation state. However, the publisher can still send duplicates if it publishes successfully and crashes before marking the row published. Therefore, the Worker needs an **idempotent receiver**.

### 13.3. How Should `HTTP 202 Accepted` Be Interpreted?

You can return:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/reservations/RSV-901
~~~

~~~json
{
  "operationId": "RSV-901",
  "status": "RECEIVED",
  "statusUrl": "/api/reservations/RSV-901"
}
~~~

If the API promises **durable acceptance**, return 202 only after the request intent/operation is durably committed. 202 does not prove `RESERVED`; the subsequent business outcome may still be `REJECTED`.

Never return 201/200 "stock reserved successfully" merely because the request was pushed onto a queue.

### 13.4. Operation Status Endpoint

~~~text
GET /api/reservations/RSV-901

Possible responses:
  RECEIVED
  PROCESSING
  COMPLETED { status: RESERVED, ... }
  REJECTED  { reasonCode: ... }
  UNKNOWN   { guidance: retry/reconcile }
~~~

The status endpoint must authenticate callers, verify tenant/ownership, enforce rate limits, and avoid leaking other users' operation IDs. A high-entropy `operationId` **never replaces authorization**.

### 13.5. Webhooks/Callbacks Instead of Polling

If the business prefers pushing results, emit a webhook when the operation finishes. However, webhook delivery can retry and duplicate:

- Callback endpoints must be pre-registered and **verified/allowlisted**, preventing SSRF/open-redirect-style `replyTo` abuse.
- Sign/authenticate callbacks using an approved scheme; prevent replay attacks.
- Attach stable `operationId` and `eventId`.
- Receivers must process events idempotently per event/operation semantics.
- Separate "business completed" state from "webhook delivered" state.

## 14. Worker-Side Idempotency: Preventing Double Reservation

A request may be redelivered due to broker at-least-once semantics; the handler runs multiple times yet **must never commit the same mutation twice**.

### 14.1. Properly Scoped Business Key

~~~text
UNIQUE (tenant_id, operation_id)
Stored record:
  request_fingerprint
  state = IN_PROGRESS / COMPLETED / REJECTED
  stored_reply
  updated_at
~~~

Do not use `orderId` alone if one order has distinct valid RESERVE, RELEASE, and ADJUST commands. Also never use transport message IDs or Kafka offsets: those change on redelivery/replay.

### 14.2. Logical Processing Flow

~~~mermaid
flowchart TD
    REQ["Delivered ReserveCommand"] --> AUTH["Validate auth/schema/deadline"]
    AUTH --> CLAIM{"Atomically claim operation key"}
    CLAIM -->|"New"| EXEC["Execute mutation once"]
    CLAIM -->|"Completed same fingerprint"| STORED["Load stored outcome"]
    CLAIM -->|"In-progress"| WAIT["Wait/defer/reconcile"]
    CLAIM -->|"Same key, different request"| CONFLICT["IDEMPOTENCY_CONFLICT"]
    EXEC --> COMMIT["Commit mutation + persist outcome"]
    COMMIT --> OUT["Reply outbox"]
    STORED --> OUT
    OUT --> PUB["Publish reply for current requestId"]
    CONFLICT --> ERR["Typed rejection"]
~~~

**Important:** compute `request_fingerprint` from a canonicalized business command covering tenant, operation type, resource, and parameters affecting side effects. Hashing raw JSON bytes causes false conflicts on key/whitespace differences; an under-specified fingerprint lets two different intents share one key undetected.

### 14.3. Races Between Two Worker Instances

A `ConcurrentHashMap` protects only one JVM. If instances A and B both observe an absent operation, both may execute the effect unless claim-or-insert is atomic.

You need a shared DB unique constraint, atomic claim/locking, or a backend supporting idempotency. If the effect is a **remote HTTP call**, a local DB claim alone does not guarantee exactly-once effects at the destination; use an idempotency token honored by the remote API or reconcile when responses are lost.

### 14.4. Crash After Commit, Before Reply Publish

~~~text
Worker commits RESERVE
    |
Process crashes before reply publish
    |
Broker redelivers request
    |
Worker finds COMPLETED and stored result
    |
Worker publishes ReserveReply again
~~~

Never invoke `reserveStock` a second time. Separating **business state** from **reply delivery** allows using an outbox to deliver replies durably after commit.

### 14.5. Duplicate Replies Are Normal Under At-Least-Once Delivery

If a Worker publishes a reply and crashes before ACKing the request, the request gets redelivered and the reply gets published a second time. The reply listener must:

- Deduplicate by reply event ID or `(tenantId, requestId, replyVersion)` per contract.
- Never complete the same pending exchange twice.
- Never transition an operation into an invalid state because an old reply arrived later.
- Enforce sequence/version guards when an outcome can transition multiple times.

Reliable request–reply **does not promise every reply appears once**; it promises callers and state machines tolerate duplicates and retries.

## 15. Retries and Error Channels: Two Different Failure Surfaces

### 15.1. Request-Side Errors

| Failure Point | Example | Action |
| --- | --- | --- |
| Ingress validation | Missing tenant/operation ID | Reject with code; do not publish |
| Persist request/outbox | DB unavailable | Return non-durable failure; controlled retry |
| Publish request | Broker timeout | May already be published; reconcile outbox state |
| Wait reply | Reply timeout | Exchange timed out; operation `UNKNOWN`/`PROCESSING` |
| Reply parsing | Unsupported reply schema | Quarantine raw safely; do not complete waiter |
| Reply identity | Wrong tenant/operation/requestId | Drop/quarantine + security alert |
| Reply destination | Reply queue missing | Retry publish or retain persisted outcome |

### 15.2. Responder-Side Errors

| Failure Point | Example | Action |
| --- | --- | --- |
| Deserialize | Malformed payload | Terminal rejection/DLQ; avoid poison loop |
| Authorization | Tenant unauthorized | Deny; never retry to bypass |
| Business validation | Invalid quantity | Typed `REJECTED` reply |
| DB temporary outage | Timeout/deadlock | Bounded retry + backoff |
| External API timeout | Unknown if remote committed | Status lookup + same idempotency key |
| Outbox publish | Reply broker unavailable | Retry reply delivery; do not re-run effect |
| Callback send | Client endpoint unavailable | Retry callback per policy; operation stays complete |

### 15.3. Spring Integration `errorChannel` Does Not Equal a Business Reply

`errorChannel`, `ErrorMessage`, and `MessagingException` serve **error flows**. A technical error message does not automatically become `ReserveReply(status=REJECTED)`.

- With synchronous `DirectChannel`, handler exceptions can propagate to the caller.
- With `ExecutorChannel`, pollers, and broker adapters, errors route into error handling/error channels per endpoint configuration.
- For remote request–reply, listeners should translate errors into **protocol-level replies/terminal statuses** when permitted and valid correlation exists; otherwise use DLQ/reconciliation rather than dropping silently.

**Never** catch every `Exception` and return `RESERVED` or `INVALID_QUANTITY`; that hides infrastructure failures and breaks retry policies.

### 15.4. Never Retry a Terminal Business Rejection

If `quantity=-2`, resending the identical bytes 10 times will not make quantity valid. Emit `ReserveReply(status=REJECTED, reasonCode=INVALID_QUANTITY)`, finalize the outcome, and return it to the caller or status API.

Conversely, a broker timeout does not prove the quantity was wrong. Use **infrastructure retries** with bounded attempts, backoff/jitter, circuit breakers, and idempotency.

## 16. Security: Both Correlation and `replyTo` Must Be Authenticated

An external request could try sending:

~~~json
{
  "tenantId": "victim-tenant",
  "operationId": "RSV-901",
  "replyTo": "attacker-controlled-queue",
  "quantity": 2
}
~~~

If the Worker blindly trusts these fields, it could mutate the wrong tenant and exfiltrate data to an unauthorized destination.

### 16.1. Proper Trust Boundary

~~~text
External request
  -> AuthN producer/principal
  -> AuthZ tenant/resource/action
  -> Size/schema/version validation
  -> Assign/verify operationId, requestId
  -> Resolve reply destination from allowed registry
  -> Safe internal request envelope
  -> Queue / Worker
~~~

A header named `trustedTenant` grants no trust on its own. Adapters must verify provenance. In multi-tenant systems, Workers still enforce authorization at commit time rather than relying solely on edge checks.

### 16.2. Reply Listeners Must Not Trust Correlation ID Alone

If a reply carries `correlationId=req-7f31` from a producer outside the inventory service, or specifies a different tenant, reject it. A guessed/captured request ID must never complete someone else's pending call.

Check at minimum:

- Broker authentication/ACLs or appropriate message signatures/provenance.
- Request/operation/tenant match.
- Valid reply schema version and status.
- Expected service type for the producer.
- Allowlisted payload size and fields.
- Never log secrets/PII when rejecting replies.

### 16.3. `replyTo` Is Not an Arbitrary URL

A `replyTo` containing an HTTP URL introduces SSRF/data-exfiltration risks; an arbitrary queue name can leak data across tenants. Derive reply destinations from **authenticated identity and configuration** or strict allowlists/ACLs. Never forward raw Authorization/JWT tokens or Java `MessageChannel` objects across a broker.

### 16.4. Encryption, Retention, and Data Minimization

Requests and replies may carry PII, monetary amounts, addresses, and order IDs. Encrypt data in transit and at rest per your threat model, enforce per-tenant access controls, set retention limits on inbox/outbox/DLQ/status stores, and enforce deletion policies. Never put unbounded `tenantId`/`operationId` values into metric tags causing high cardinality.


## 17. Request–Reply Over JMS, AMQP, and Kafka

Each messaging technology offers different primitives. The EIP pattern stays the same, but you cannot copy one config/header mapper and expect identical semantics.

| Infrastructure | Request Dispatch | Common Reply Path | Key Risk |
| --- | --- | --- | --- |
| **JMS** | Request destination via JMS producer | `JMSReplyTo` + `JMSCorrelationID`/adapter | Temporary queue lifecycle, sessions/ACK, provider semantics |
| **AMQP/RabbitMQ** | Exchange + routing key to queue | Reply queue, reply-to, correlation properties | Connection loss, manual ack, duplicates, direct reply-to |
| **Kafka** | Request topic with key/headers | Reply topic + key/correlation header | Reply partitions, consumer groups, rebalances, retention |
| **Spring in-JVM** | Direct/Executor/QueueChannel | Gateway-managed `replyChannel` header | No durability across process crashes |
| **HTTP 202 + status** | POST + durable operation write | GET status, webhook, or event | Callback auth, eventual consistency, retention |

### 17.1. JMS: `replyTo` and Correlation Must Align

JMS messages carry `JMSMessageID`, `JMSCorrelationID`, and `JMSReplyTo`. A requester can supply a reply destination and correlation key; the responder sends the reply to that destination, and the listener correlates using the key.

However:

- Never automatically use the request's `JMSMessageID` as a business mutation's `operationId`.
- Never assume every provider/adapter maps `JMSCorrelationID` from `requestId` with the same default.
- Temporary reply queues may vanish if the requester restarts; durable replies need a different destination/lifecycle.
- Session transactions/ACKs protect only the transport boundary—they do not create an atomic DB+JMS+HTTP transaction.

When using Spring Integration JMS Gateways/Adapters, configure reply listeners, converters, correlation strategies, consumer concurrency, and error handling for your **exact library version**, then test against a real broker.

### 17.2. AMQP/RabbitMQ: ACKs and Direct Reply-To

AMQP reply patterns can use a reply queue or **direct reply-to**. Direct reply-to is convenient and lightweight in certain RPC flows, yet carries limits on reply durability and lifecycle; never treat it as an infinitely retrievable workflow result.

Verify:

- Which reply destinations the responder is authorized to publish to.
- That correlation properties are written and read with exact byte/type fidelity.
- Whether the consumer ACKs the request before or after persisting the outcome/outbox.
- What publisher confirms prove about broker acceptance—and what they **do not** prove.
- Where operation status/retries recover if a reply is lost.

Never rely on an in-memory reply queue as the source of truth for business outcomes.

### 17.3. Kafka: Reply Topics Need Matching Consumer Topology

Kafka is not an RPC transport by default. One implementation choice is:

~~~text
inventory.requests topic:
  key = tenantId + ":" + orderId (for partition affinity)
  headers: requestId, operationId, replyTopic, schemaVersion
  value = ReserveCommand

inventory.replies topic:
  key = requestId or partition key per protocol
  headers: correlationId=requestId, schemaVersion
  value = ReserveReply
~~~

This is an **example protocol**. Define key encoding carefully to avoid concatenation collisions; if relying on partition ordering, pick consistent partition keys.

Differences from JMS:

- A reply topic read by a consumer group **can deliver a reply to an instance not holding the local waiter**.
- If each instance keeps an in-memory registry while sharing one consumer group, replies landing on arbitrary instances become a major bug.
- You need **instance-specific reply routing**, deterministic partition assignment, or **shared persistent workflow state**, rather than hoping the consumer group "magically knows" which caller is waiting.
- Offsets are not business operation identities. Reply topic retention does not replace a durable operation ledger.
- Rebalances/retry topics can shift where messages are processed; support duplicates, out-of-order delivery, and concurrency.

### 17.4. Broker Exactly-Once Does Not Mean External Side-Effect Exactly-Once

Broker transactions can provide guarantees **within broker scope**, but cannot roll back an HTTP call to a warehouse or external database when a network response drops.

To protect business integrity, enforce idempotency at the data owner, unique operation keys, outcome persistence, and reconciliation. Never document "Kafka exactly-once prevents double reservations" when external side effects sit outside any shared transaction.

### 17.5. Message Headers Can Be Lost During Serialization

Spring `MessageHeaders` permits arbitrary object types, whereas transports support specific primitive types/encodings. Across adapters, verify:

- IDs and correlation keys are String/UUID/binary per contract.
- Internal `replyChannel`/`errorChannel` objects are never serialized onto the broker.
- Content type reflects serialized bytes, not the in-JVM Java record.
- Consumers understand schema versions and define policies for unknown fields.
- Never copy JWTs/secrets, stack traces, or exception objects into replies.
- Header mappers use allowlists and are tested **on the wire**.

## 18. Request–Reply Combined with Router, Filter, and Transformer

A multi-source async flow often looks like:

~~~mermaid
flowchart TD
    IN["Request topic/queue"] --> AUTH["Authenticate + validate envelope"]
    AUTH --> ROUTE["Router by trusted source / command type"]
    ROUTE --> T1["Translator A to canonical"]
    ROUTE --> T2["Translator B to canonical"]
    T1 --> FILTER{"Business validation"}
    T2 --> FILTER
    FILTER -->|"Valid"| SVC["Service Activator / handler"]
    FILTER -->|"Invalid"| REJ["Typed REJECTED reply"]
    SVC --> RES["Persist outcome + reply outbox"]
    REJ --> RES
    RES --> PUB["Publish reply with original requestId"]
~~~

### 18.1. Filter Drops Are Dangerous in Request–Reply

If a Filter **silently drops** a request on validation failure, the caller sees only a timeout even though the input was rejected. In request–reply flows where callers need outcomes:

- Emit a typed rejection reply `INVALID_QUANTITY`, or
- Record a terminal operation status + reason for async end-to-end flows, or
- Provide an error/rejection channel observable by the API.

A drop-only Filter works only when the contract permits **no reply**; never use it as a default error mechanism.

### 18.2. Transformers Must Preserve Correlation

If Service A sends `requestId=req-7f31` and a Transformer converts the schema before the Worker, preserve all required correlation/operation identities. Never mint a random new `requestId` inside a Transformer when merely translating **the same request exchange**.

If the target broker uses different header names, map them explicitly. Return-path reply translators must likewise preserve the request ID so the listener matches the right pending entry.

### 18.3. Routers Need Error Paths for Unknown Command Types

Suppose a new `commandType=CANCEL` arrives before the Worker supports it: never route it to RESERVE via a default branch, and never drop it silently. Return `UNSUPPORTED_COMMAND` or quarantine alongside operation status, per protocol and security policy.

## 19. Async Request–Reply with Splitter, Aggregator, and Scatter-Gather

One request may split into multiple child work items. The caller still expects **one consolidated reply** or one overall status.

~~~mermaid
flowchart TD
    REQ["ReserveBatch(requestId=req-700)"] --> SPLIT["Splitter: 3 lines"]
    SPLIT --> A["Worker LINE-1"]
    SPLIT --> B["Worker LINE-2"]
    SPLIT --> C["Worker LINE-3"]
    A --> OUT1["LineOutcome RESERVED"]
    B --> OUT2["LineOutcome REJECTED"]
    C --> OUT3["LineOutcome RESERVED"]
    OUT1 --> AGG["Aggregator by executionId"]
    OUT2 --> AGG
    OUT3 --> AGG
    AGG --> BR["BatchReply(correlationId=req-700)"]
~~~

### 19.1. Three Distinct Correlation Roles

| Identity | Scope | Example |
| --- | --- | --- |
| `requestId` | Exchange caller ↔ batch reply | `req-700` |
| `executionId` | Group for one workflow run | `RUN-700-A` |
| `childId` | Unique subtask within the group | `LINE-2` |
| `operationId` | Unique side effect of a child | `RSV-700-LINE-2` |
| `businessCorrelationId` | Broader order/case tracing | `ORD-700` |

**Receiving all child replies differs from all children succeeding.**

~~~text
Expected: LINE-1, LINE-2, LINE-3
Received: 3/3 unique outcomes
Business result: 2 RESERVED, 1 REJECTED
Batch outcome: PARTIAL / FAILED (policy-dependent)
~~~

### 19.2. Never Count a Duplicate Reply as a New Child

If `LINE-1` is redelivered twice and the Aggregator checks `group.size()==3`, it could release early upon seeing `LINE-1`, duplicate `LINE-1`, and `LINE-3`, while `LINE-2` has not arrived yet.

Release based on the **expected unique child set**, deduplicating by `(executionId, childId)`, and define a policy if outcomes for the same child conflict.

### 19.3. Zero Replies Never Triggers a Group Timeout

If all three workers send no reply, the Aggregator receives no message to even create a group; `groupTimeout` on a nonexistent group solves nothing. You need an **execution-level deadline watcher**, durable expected-child registry, or independent workflow timeout.

### 19.4. Partial Results, Cancellation, and Compensation

Suppose a batch hits its deadline when `LINE-1` already reserved successfully and `LINE-3` is still running. Options include:

- **Return PARTIAL** with an explicit per-child outcome list so consumers decide next steps.
- **Await later completion** via status API/callback.
- **Compensate** committed side effects if the business contract is all-or-nothing and compensation is feasible.
- **Mark UNKNOWN** for unresolved children; never misreport them as `REJECTED`.

Gateway timeouts stop only one waiter; they do not automatically roll back child mutations.

### 19.5. Finalize Once

A late batch reply can re-trigger the Aggregator after the group was evicted. Maintain a closed-execution registry/tombstone, result version, and idempotent finalizer so two final decisions are never published when the contract forbids it.

## 20. Ordering, Concurrency, and Backpressure

### 20.1. Replies Have No Global Order

Async Workers/Executors/brokers can deliver replies out of send order. Request–reply correlation must match by ID, **never** by FIFO order on a shared reply queue.

Even if a Kafka request partition preserves order, outbound Worker concurrency or retry topics can scramble reply order. If business logic requires sequential processing, add explicit domain versioning/sequencing and reordering policies.

### 20.2. Never Let Stale Status Overwrite Newer Status

Suppose:

~~~text
t1: Reserve operation completes (RESERVED)
t2: Caller starts separate CANCEL operation
t3: CANCEL commits (CANCELLED)
t4: Late RESERVE reply arrives
~~~

If the listener updates order status purely in **reply arrival order**, it can wrongly overwrite `CANCELLED` back to `RESERVED`. Enforce domain event versions/aggregate revisions/operation sequencing and state-transition guards.

### 20.3. Pending Registries Must Be Bounded

If 100,000 callers hold open pending futures for 5-minute tasks, memory, threads, and connection pools exhaust quickly. Enforce:

- Max pending requests and per-tenant quotas.
- Bounded executor queues and consumer concurrency.
- Deadline/TTL eviction and pending-age metrics.
- Rate limiting/load shedding and backpressure returning clear errors.
- **202 + polling/webhook** for long-running tasks.
- Size/TTL limits on DLQs, outboxes, reply topics, and operation status stores.

### 20.4. Never Ignore Consumer Lag

If the request queue has a 10,000-message backlog while Gateway reply timeout is 2 seconds, most callers time out before a worker even starts. Do not "fix" this with infinite timeouts; size capacity, service time, queueing delay, and switch to end-to-end async where appropriate.

## 21. Observability: Measuring Every Stage of Request–Reply

A log line `request_published=true` proves only that the publisher observed a send event, not that the operation succeeded.

| Suggested Signal / Metric | Question Answered |
| --- | --- |
| `requests_received_total` | How many requests entered? |
| `outbox_pending_total` | How many publish intents remain unsent? |
| `request_publish_failures_total` | Is broker publishing failing? |
| `request_queue_depth/lag` | Are workers keeping up? |
| `worker_processing_duration` | How long does the business service take? |
| `operation_completed_total` | How many operations committed? |
| `operation_rejected_total` by reason | How many terminal rejections occurred? |
| `reply_publish_failures_total` | Result exists, yet reply sending failed? |
| `pending_replies_active` | How many waiters are currently held? |
| `reply_received_total` | How many reply messages arrived? |
| `reply_correlation_miss_total` | Replies finding no pending key? |
| `reply_identity_mismatch_total` | Wrong tenant/operation/request ID? |
| `reply_duplicates_total` | How many duplicate replies arrived? |
| `reply_timeout_total` | How many exchanges expired? |
| `late_reply_total` | How many results arrived past wait deadline? |
| `idempotency_reused_total` | How many stored results were replayed? |
| `dlq_backlog/oldest_age` | Are poison messages piling up unnoticed? |
| `status_reconciliation_backlog` | How many `UNKNOWN` operations need resolution? |

These metric names are **instrumentation suggestions**, not a claim that Spring Integration emits all of them automatically. Combine Micrometer/Observation, broker metrics, and business ledgers.

### 21.1. Structured Logs Without Leaking Data

~~~json
{
  "event": "reply_correlated",
  "sourceService": "inventory-service",
  "requestSchema": "reserve-command-v1",
  "replySchema": "reserve-reply-v1",
  "outcome": "RESERVED",
  "correlationResult": "MATCHED",
  "late": false,
  "duplicate": false
}
~~~

Debugging specific exchanges may require `requestId`/`operationId` in access-restricted logs/traces. Never put high-cardinality IDs or raw PII into metric labels. Enforce masking, access control, and retention policies on logs.

### 21.2. Trace Spans Across Brokers

Spans may look like:

~~~text
order.api.accept
  -> outbox.persist
  -> broker.publish.request
      -> inventory.consumer.receive
          -> reservation.commit
          -> broker.publish.reply
              -> order.reply.listener
                  -> pending.complete / status.persist
~~~

Propagate trace/span IDs using standard headers, but never treat tracing as authorization or business idempotency. Never trust client-supplied `traceparent` headers to identify tenants.

### 21.3. Critical Alerts

Alert when:

- Reply correlation misses spike suddenly.
- Late replies climb after timeout changes.
- Outbox publisher backlog grows while request queues receive nothing.
- Worker commit rate stays steady while reply publish failures spike.
- Pending registry approaches capacity.
- Reply identity mismatches occur (possible mapping bug or injection).
- `UNKNOWN` operations exceed SLA without reconciliation.
- Retry storms or DLQ oldest age breach thresholds.
- Batch executions fail to collect enough child outcomes before deadlines.


## 22. Common Anti-Patterns

| Anti-Pattern | Consequence | Remedy |
| --- | --- | --- |
| Treating async request–reply as fire-and-forget | Caller never learns operation outcome | Explicit reply/status protocol |
| Treating broker ACK as business success | Reports `RESERVED` before worker runs | Separate accepted, processed, committed |
| Assigning first reply to first caller | Cross-talk across requests | Correlate by `requestId` |
| Correlating solely by `orderId` | Concurrent exchanges for one order collide | Scope by `requestId`/tenant/requester |
| Using `MessageHeaders.ID` or Kafka offset as operation ID | Redelivery mints new IDs | Stable business operation ID |
| Generating a fresh `UUID` inside Worker retries | Double reserve/charge | Preserve operation ID across attempts |
| Registering pending waiter after publish | Fast reply arrives before registration | Register-before-publish |
| Treating an in-memory pending registry as durable | Crashes lose waiters/state | Persistent operation/ledger, shared routing |
| Shared reply consumer group with private per-instance pending maps | Replies land on the wrong instance | Instance-routed replies or shared state |
| Failing to authenticate reply producers | Forged replies complete requests | Broker auth/ACL, schema, identity checks |
| Checking `requestId` only, skipping tenant/operation | Cross-tenant leak, wrong status | Validate expected tenant, operation, producer |
| Accepting arbitrary `replyTo` from clients | Data exfiltration/SSRF | Allowlists + trusted identity |
| Treating timeouts as business rollback | Operation may already have committed | `UNKNOWN` + reconciliation |
| Treating Gateway `replyTimeout` as cancellation | Worker keeps running after timeout | Explicit cancellation/state policy |
| Re-running remote effect when reply publish fails | Duplicate side effects | Persist result + reply outbox |
| Checking Redis/HashMap then mutating DB non-atomically | Race across Worker instances | Atomic claim + consistency boundary |
| Assuming outbox publisher is exactly-once | Duplicate publish after crash | Idempotent consumer |
| Retrying terminal invalid inputs indefinitely | Poison loop / DLQ storm | Typed rejection and terminal handling |
| Mapping technical errors to `REJECTED INVALID_QUANTITY` | Prevents legitimate retries | Separate technical and business errors |
| One unbounded global timeout | Memory/thread exhaustion | Bounded waits + 202/status API |
| Old reply overwriting newer operation status | Resurrects canceled state | Version/state transition checks |
| Filter dropping failed child items | Aggregator stalls missing outcomes | Typed rejected child result |
| `group.size()` counting duplicates as new parts | Premature release / corrupt batch | Unique child IDs + expected set |
| Relying solely on group timeout | Zero-reply executions get orphaned | Execution-level deadline watcher |
| Testing in-JVM Gateway and claiming broker durability | Misses crashes and header mapping | Transport/broker contract tests |
| Copying raw payload/PII into headers/logs | Data leakage | Minimal metadata, protected logs |
| Using `requestId` as a metric label | High cardinality | Bounded metric tags, ACL-protected traces |

## 23. Pre-Production Checklist

### 23.1. Protocol Contract

- [ ] Define whether callers **wait for a reply** or use **accepted + later status**.
- [ ] Version request/reply schemas; define explicit outcome enums and error codes.
- [ ] Distinguish `requestId`, `operationId`, `businessCorrelationId`, `executionId`, and transport IDs.
- [ ] Replies include correlation key, operation ID, and tenant scope sufficient for matching.
- [ ] Define idempotency contracts for every business mutation.
- [ ] Define explicit protocol rules for missing replies, terminal rejections, transient failures, and `UNKNOWN`.
- [ ] Never equate broker ACK / HTTP 202 with business `COMMITTED`.

### 23.2. Routing and Consistency

- [ ] Derive reply destinations from a trusted registry/identity or allowlist.
- [ ] Requester registers pending state **before publishing**.
- [ ] Pending cleanup enforces TTL/resource bounds without losing business outcomes.
- [ ] Multi-instance deployments use shared state or valid instance affinity for reply listeners.
- [ ] Requester writes durable operation/outbox records when promising durable acceptance.
- [ ] Responder enforces atomic claims / idempotent receivers at the business owner.
- [ ] Stored outcomes are reused on redelivery with the same operation key.
- [ ] Reply outbox enables retrying reply publish without repeating side effects.
- [ ] Header mapping across brokers/HTTP neither loses correlation nor leaks Java channel objects.
- [ ] Schema evolution/replay defines version-mapping policies and reconciliation.

### 23.3. Deadlines, Security, and Operations

- [ ] Send timeout, reply wait timeout, and business deadline are defined separately.
- [ ] Gateways/HTTP use bounded waits; long work moves to status APIs/callbacks.
- [ ] Late replies update operation state or reconcile per policy.
- [ ] Duplicate/out-of-order replies neither complete wrong waiters nor overwrite newer states.
- [ ] AuthN/AuthZ/tenant/producer validation is enforced on both sides.
- [ ] Callbacks/`replyTo` disallow arbitrary client-supplied endpoints.
- [ ] Pending registries/executors/broker queues enforce capacity bounds, rate limits, and backpressure.
- [ ] Error channels and terminal business rejections are handled separately.
- [ ] DLQ, outbox, inbox, and operation status retention match the replay window.
- [ ] PII/secrets are encrypted, with restricted logs/metric tags and access controls.
- [ ] Metrics cover publish, commit, reply, timeout, duplicate, late, and `UNKNOWN`.
- [ ] Runbooks cover stuck requests, orphaned replies, consumer lag, and broker outages.

### 23.4. Testing

- [ ] Unit tests cover Worker business outcomes without confusing them with real DB commits.
- [ ] Spring Integration tests cover `ExecutorChannel` + typed Gateway replies.
- [ ] Tests verify **out-of-order** replies and concurrent multi-caller correlation.
- [ ] Tests verify duplicate replies complete pending waiters at most once.
- [ ] Tests verify wrong tenant/`requestId`/`operationId` never complete pending waiters.
- [ ] Tests verify timeouts close exchanges without marking business operations `FAILED`.
- [ ] Tests verify register-before-publish with ultra-fast replies.
- [ ] Tests verify process crash after DB commit and before reply publish causes no double effect.
- [ ] Tests verify outbox publisher duplicates and idempotent Worker/Consumer behavior.
- [ ] Tests verify reply consumers across rebalances/restarts, shared registries, or instance routing.
- [ ] Tests verify missing replies, unknown schemas, poison messages, and DLQs.
- [ ] Tests verify zero-reply batches and duplicate/late child outcomes.
- [ ] Authorization tests verify requesters cannot pick unauthorized reply destinations.
- [ ] Tests verify status endpoints/webhooks block cross-tenant reads.
- [ ] Tests verify bounded resource usage when pending maps/queues approach capacity.

## 24. Practice Exercise: Asynchronous Shipment Creation

An e-commerce system receives `CreateShipment` requests. The Shipping Worker may take 30 seconds to generate shipping labels, and occasionally the carrier API times out after already creating the shipment.

**Input:**

~~~json
{
  "tenantId": "shop-a",
  "operationId": "SHIP-CREATE-901",
  "requestId": "request-sh-901-a",
  "orderId": "ORD-901",
  "carrierCode": "CARRIER_A",
  "weightGrams": 1250
}
~~~

**Response Contract:**

~~~json
{
  "correlationId": "request-sh-901-a",
  "operationId": "SHIP-CREATE-901",
  "status": "CREATED",
  "shipmentId": "SHP-901",
  "reasonCode": null
}
~~~

### 24.1. Design Tasks

1. Choose between **Gateway waiting for reply** and **HTTP 202 + status API**, and justify your choice for a 30-second task.
2. Design request/reply envelopes including schema version, authenticated tenant/producer, `requestId`, `operationId`, `replyTo`, and deadline.
3. Draw the sequence: request queue → Worker → Carrier API → reply outbox → reply listener.
4. Explain why HTTP 202 does not mean the shipment has been created.
5. Design the requester's operation table and outbox inside one transaction.
6. Design an idempotent Worker so carrier API timeouts never create a second shipment on retry.
7. If Carrier A does not support idempotency tokens, propose status lookup/reconciliation instead of blind retries.
8. Specify how `requestId` behaves when retrying the same operation vs. opening a new exchange.
9. Write strongly typed Java records `CreateShipmentCommand`, `ShipmentReply`, and `PendingKey`.
10. Write a `CompletableFuture`-based `PendingReplyRegistry` solely to demonstrate correlation.
11. Test A and B replies arriving out of order without mixing tenants/operations.
12. Test a late reply after deadline not completing the old HTTP caller while still updating durable shipment status.
13. Design safe callbacks/webhooks without accepting arbitrary client-supplied URLs.
14. Design Reply Listener validation: schema, producer, tenant, operation, and correlation.
15. Add a new field in `shipment-reply-v2`; state the migration and unknown-field policy for v1 consumers.
16. For 50 shipments, use Splitter/Aggregator with typed child outcomes; describe the zero-reply deadline.
17. Explain why a Kafka consumer group can deliver a reply to an instance lacking the in-memory waiter.
18. Design an appropriate reply topic/partition/instance-routing topology or shared status store.
19. Select metrics for accepted, pending, processing, committed, reply published, timeout, late, duplicate, and `UNKNOWN`.
20. Write a runbook for handling operations stuck in `PROCESSING` past SLA without assuming failure.
21. Write broker integration tests for publisher retries and consumer redelivery after commit.
22. Verify no PII/raw payloads are logged and request IDs are never used as high-cardinality metric tags.

### 24.2. Acceptance Criteria

Your solution passes when it proves **four independent properties**:

1. **Correlation correctness:** replies match the right tenant, request, and operation, even out of order.
2. **Outcome correctness:** callers distinguish `ACCEPTED/PROCESSING/CREATED/REJECTED/UNKNOWN` without equating timeouts to `FAILED`.
3. **Idempotency correctness:** retries, redeliveries, and crashes never create two shipments for one business operation.
4. **Recovery correctness:** process restarts, lost replies, outbox retries, and late results all have clear continuation/reconciliation paths.

Merely testing "Gateway returns a valid DTO" is insufficient for a distributed request–reply protocol.

## 25. Summary

**Request-reply over asynchronous systems** lets senders and processors communicate via queues, topics, executors, or brokers while preserving a result-returning contract. Callers can **wait** as with a Messaging Gateway, or **receive 202 and track outcomes later** via a status API/webhook. Both differ in user experience and resource lifecycle, yet both require correlation and clear processing states.

The hard part is not invoking a method or publishing two messages—it is handling **out-of-order replies, duplicates, timeouts, late replies, process crashes, broker redeliveries, and cross-instance routing**. Reserve `requestId` for the exchange and `operationId` for idempotent business mutations; never equate broker ACKs, Java returns, or Gateway timeouts with DB commits. Reliable systems require durable operations/outboxes, atomic idempotency at the business owner, persisted outcomes, and reply listeners that authenticate emitters before completing pending waits.

In Spring Integration, `@MessagingGateway`, `ExecutorChannel`, Service Activator, Router, Filter, Transformer, error channel, and Splitter/Aggregator implement individual pieces of the flow, yet do not automatically guarantee exactly-once external side effects. Combine **explicit contracts, boundary security, bounded waiting, reconciliation, and unit/integration/broker tests** so request–reply reaches the **right recipient, executes the right business logic, recovers cleanly, and avoids duplicate side effects**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Request-Reply, Correlation Identifier, Messaging Gateway, Return Address, Service Activator, Idempotent Receiver, Aggregator, Dead Letter Channel); Spring Integration Reference on Messaging Gateways, Message Channels, ExecutorChannel, Service Activators, Routers, Error Handling, and Testing; Spring Framework/Java SE on `TaskExecutor`, records, `CompletableFuture`, and concurrency; JMS, RabbitMQ/AMQP, and Apache Kafka protocol docs, plus production transactional outbox/inbox patterns.








