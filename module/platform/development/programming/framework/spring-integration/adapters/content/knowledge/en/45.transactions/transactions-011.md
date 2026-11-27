# Avoiding Holding Transactions When Calling Slow Services in Spring Integration Adapters

## 1. The Goal: Short Transactions, Reliable Outcomes

In a **Spring Integration Adapters** system, a message may enter via file/SFTP, HTTP, JMS, AMQP, Kafka, or database, travel through `MessageChannel`, transformers, filters, and gateways, and ultimately produce an effect in another system. A common trap is opening a **database transaction**, updating a record, and then **holding that transaction open while waiting** for an HTTP API, SFTP server, broker, or third-party service to respond.

This implementation may appear fine in development, yet when external services slow down or time out, the system holds connections, locks, and transaction resources far longer than the database work requires. The consequences are contention, backlogs, cascading timeouts, deadlocks, pool exhaustion, inconsistent writes, and unsafe retries.

**Central principle:** wrap a transaction strictly around operations that genuinely require atomicity within **the same transactional resource scope**. When calling external services, design a clear split: **commit internal state first**, execute I/O outside the database transaction, and record outcomes in another short transaction; when reliable delivery is required, use a **transactional outbox + dispatcher + idempotent consumer/partner** rather than merely splitting with an async call.

After this lesson, you should be able to:

1. Explain why a slow remote call increases JDBC connection hold time, row locks, transaction logs, and contention.
2. Distinguish **database transactions**, **JMS/Kafka/broker transactions**, **Spring transaction synchronization**, and **cross-system business consistency**.
3. Identify where transactions propagate across `@Transactional`, `TransactionTemplate`, `DirectChannel`, pollers, `ExecutorChannel`, and gateways.
4. Design **short local transactions** that never hold DB resources while waiting on HTTP/SFTP/JMS/AMQP/Kafka.
5. Apply outbox, retry/backoff, idempotency keys, intermediate states, reconciliation, and compensation based on risk.
6. Write tests proving **external calls genuinely run outside the transaction**, not merely that a message was received.
7. Know when to accept synchronous trade-offs, when to use queues/outboxes, and how to operate when targets are slow or unavailable.

**Scope:** applies to Spring Boot + Spring Integration with inbound/outbound adapters, gateways, pollers, `MessageChannel`, and File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC flows. Illustrated APIs/annotations reflect modern Spring generations; always verify against your project's actual versions before applying.

## 2. What Is a Transaction, and What Does *Not* Belong Inside It?

A database transaction has boundaries such as **begin → JDBC/JPA operations → commit/rollback**. In a properly configured database, operations inside the transaction are atomic and honor isolation levels. Yet placing an HTTP POST or SFTP upload between those operations **does not make HTTP/SFTP part of the same local DB transaction**.

~~~mermaid
sequenceDiagram
    participant I as Input / MessageChannel
    participant S as Spring service
    participant D as Database
    participant P as Partner HTTP/SFTP
    I->>S: Process command
    S->>D: BEGIN + UPDATE order
    D-->>S: Row locked / DB resource held
    S->>P: POST /shipments (slow)
    Note over S,P: 20 s latency / timeout
    P-->>S: 201 / error / response lost
    S->>D: COMMIT or ROLLBACK
    S-->>I: Result / exception
~~~

If the remote call already executed its side effect while the response dropped, a DB rollback **cannot undo the effect on the partner side**. Conversely, if the DB commits before sending the remote request and the process dies right after commit, the request may **never be sent**. That is why **reliability** must be solved explicitly instead of stretching a transaction to "cover" a non-transactional protocol.

### 2.1. Four Concepts Too Easily Equated

| Mechanism | Guarantee it can provide | What must NOT be assumed |
|---|---|---|
| **Local JDBC/JPA transaction** | Atomicity/isolation for DB resources inside the TX | Cannot roll back HTTP requests or SFTP uploads |
| **JMS/AMQP transaction/ack** | Commit/ack/nack within broker session/delivery per config | Not automatically atomic with DB or REST APIs |
| **Kafka producer transaction** | Atomicity for Kafka operations inside that Kafka TX | Does not fold SQL/HTTP/SFTP into the Kafka TX |
| **Business workflow / saga / outbox** | Coordinates local TXs via state, events, retries, compensation | Not automatically end-to-end exactly-once everywhere |

**XA/2PC** can coordinate certain **supported transactional resources** under an appropriate transaction manager infrastructure, yet it is not a general-purpose answer for HTTP/SFTP and carries lock/availability costs and distinct operational risks. This lesson focuses on the more common pattern: **short local transactions + reliable external communication via state and idempotency**.

### 2.2. Does "Holding a Connection" Always Happen Right at `@Transactional` Entry?

Do not make absolute generalizations. Actual connection acquisition depends on the transaction manager, connection pool, JPA provider, and **lazy acquisition** mechanics. However, **once the transaction performs DB work**, the system may retain the JDBC connection and locks until completion. The longer the remote call, the longer those resources stay pinned. **Measure via metrics/tracing** rather than guessing from annotations.

## 3. Why Do Slow Remote Calls Cause Cascading Failures?

Suppose an endpoint handles 60 messages/second, with pure DB transactions taking 20 ms each. Adding a 3-second average remote HTTP call **inside the transaction** increases resource hold time more than a hundredfold. When transactions retain a connection continuously, pool pressure spikes sharply.

An estimation rule from **Little's Law** (in steady state):

\[
L \approx \lambda W
\]

With \(\lambda\) as throughput (requests/second) and \(W\) as average resource hold duration (seconds), \(L\) is the average number of concurrent requests holding resources. For instance, 40 requests/second × 2 seconds = **80 concurrent requests**; a 20-connection pool suffers heavy contention if each request holds a connection over that interval. This is an **illustrative model**, not measurements from a specific system; queries, lazy connections, batching, and actual concurrency shift the numbers.

| Impact | Common symptom |
|---|---|
| **Connection pool exhaustion** | Threads waiting on connections, Hikari timeouts, rising latency |
| **Lock contention** | Other transactions waiting on row/table locks, deadlocks, timeouts |
| **Long transactions** | Retaining undo/MVCC snapshots, vacuum/log pressure depending on DB |
| **Queue / poller backlog** | Queued messages piling up, falling consumer throughput, stacked retries |
| **Cascading timeouts** | HTTP/client timeouts → retries → higher load → more timeouts |
| **Uncertain outcomes** | Partner processed request while caller timed out and rolled back DB |
| **Disrupted shutdowns** | Process stops mid-transaction/remote call with unknown outcome |
| **Degraded availability** | Slow external service drags down the database and unrelated internal features |

**This is not merely a performance problem.** Long transactions raise retry rates and uncertainty around already-completed remote side effects.

## 4. Basic Anti-Pattern: Calling HTTP Inside `@Transactional`

Example:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final ShippingClient shipping;

    public OrderService(OrderRepository orders, ShippingClient shipping) {
        this.orders = orders;
        this.shipping = shipping;
    }

    @Transactional
    public void approveAndSend(String orderId) {
        Order order = orders.findForUpdate(orderId);
        order.markApproved();
        orders.save(order);

        // Wrong boundary: HTTP can stall for seconds or time out.
        ShipmentReceipt receipt = shipping.reserve(orderId);

        order.markSubmitted(receipt.shipmentId());
        orders.save(order);
    }
}
~~~

`OrderRepository`, `ShippingClient`, `Order`, and `ShipmentReceipt` are illustrative domain types. `findForUpdate` assumes a locking read; exact save/flush/lock behavior depends on your JPA/JDBC provider.

**Problems:**

1. The database transaction starts before `shipping.reserve(...)`.
2. After acquiring locks and updating, the transaction stays open across network wait time.
3. If HTTP times out after the remote already created the shipment, DB rollback does not cancel the shipment.
4. Retrying the whole method can **create two shipments** if the partner is not idempotent.
5. Pool exhaustion breaks flows completely unrelated to shipping.

**An incomplete "fix":** swapping `ShippingClient` for an async client while still calling `future.get()` / `join()` inside `@Transactional`. The transaction still waits on I/O. Likewise, placing `@Async` on the same class and calling via `this` bypasses the proxy.

## 5. Seeing Transaction Boundaries in Spring Integration

Spring Integration connects endpoints via channels; some channels/handlers execute synchronously on the same thread, while others switch threads or execute later.

~~~mermaid
flowchart LR
    A["@Transactional service"] --> D["DB write / locks"]
    D --> CH["DirectChannel"]
    CH --> H["HTTP outbound handler"]
    H --> R["Remote service - slow"]
    A -. "transaction scope stays open" .-> R
~~~

### 5.1. `DirectChannel`: Usually Preserves the Call Stack

`DirectChannel` normally dispatches to the handler **on the sender's thread**, and `send()` returns only after the handler finishes. If the sender is inside a Spring-managed transaction, the synchronous handler executes **within the same thread transaction context**, unless explicitly split by transaction configuration or another mechanism.

Example:

~~~java
@Transactional
public void process(OrderEvent event) {
    orders.markAccepted(event.orderId()); // DB operation
    outboundChannel.send(
        MessageBuilder.withPayload(event).build()
    ); // If DirectChannel -> synchronous HTTP handler.
}
~~~

Here `outboundChannel.send(...)` can stretch the DB transaction across HTTP latency. **Merely naming a channel "async" does not make it asynchronous.**

### 5.2. `ExecutorChannel`: Splits Threads, Does Not Guarantee Delivery

`ExecutorChannel` dispatches via an executor, so **the old thread's transaction context does not propagate to the new thread**. That creates a common transaction boundary, with two caveats:

- **No automatic durable handoff.** If DB commits and the process dies before the executor task runs, the message is lost.
- Operations on the worker thread need their **own transaction**; never assume they reuse the caller's transaction.

Use executors when events do not require strong durability or already come from a durable recoverable source. For business transactions needing reliable delivery, a **transactional outbox** is usually more appropriate.

### 5.3. `QueueChannel` and Pollers: Decouples Timing, Yet Check Where Transactions Open

`QueueChannel` is a `PollableChannel`; the sender enqueues and a consumer/poller pulls later. In memory, it **provides no crash durability**. When a polling consumer configures transaction advice, the transaction can wrap **polling and synchronous handlers** inside the poll, depending on configuration.

If a handler runs a slow remote call **inside the poller's transaction**, you still hold a long transaction despite using a queue channel. Always **inspect the call chain and poller advice**, not just the channel name.

### 5.4. Request–Reply Gateways Can Keep the Caller Waiting

Gateways offer synchronous or asynchronous replies depending on gateway type and config. If a `@Transactional` method calls a gateway and waits for an HTTP/JMS reply, the caller's transaction stays open throughout the wait—even if remote work runs on another thread.

**Switching threads does not shorten the caller's transaction hold time** if the caller still awaits the result before committing.

### 5.5. Orientation Table

| Topology | Potential transaction boundary | Trap |
|---|---|---|
| `@Transactional` → `DirectChannel` → HTTP handler | Likely same thread, same transaction | DB lock held across HTTP call |
| `@Transactional` → `ExecutorChannel` → handler | Worker does not inherit thread-bound TX | In-memory message lost after commit |
| `@Transactional` → `QueueChannel` → poller | Producer/consumer decoupled in time; poller TX configured separately | Poller TX may wrap slow handlers |
| JDBC polling with `TransactionInterceptor` → HTTP | Poll TX includes synchronous handling | Long DB TX held |
| Transacted JMS listener → HTTP → ack | Broker/session TX stays open until handler returns | Redeliveries, duplicates, consumer stalls |
| Kafka listener → handler → HTTP | Ack/offset per container, usually post-handler | Rebalances/timeouts, duplicates; not a DB TX by default |
| Short DB TX → outbox → dispatcher → partner | DB TX closes before external I/O | Requires outbox worker, retries/leases/idempotency |

## 6. Three Durations to Measure Separately

Transaction optimization must distinguish:

- **DB transaction duration**: how long the transaction is genuinely active, especially from lock/write to commit.
- **External call latency**: request/response time at HTTP/SFTP/broker/client layers.
- **Business workflow latency**: from receiving the command to final outcome, which may span multiple transactions.

~~~mermaid
gantt
    title Illustrative Model: Long Transaction vs. Split Boundaries
    dateFormat  X
    axisFormat %s
    section Before
    DB transaction held across remote I/O :a1, 0, 10
    section After
    DB transaction (state + outbox) :a2, 0, 2
    Remote I/O (outside DB tx) :a3, 2, 8
    DB transaction recording outcome :a4, 8, 10
~~~

**The diagram is a relative illustration**, not measured latencies. The goal is not necessarily shrinking total business-operation duration; the goal is **never holding transactional resources** during external waits.

## 7. Choosing a Solution Based on Required Reliability

| Context | Preferred pattern | Trade-off |
|---|---|---|
| Read DB data then call non-critical, recomputable API | Short read-only TX → HTTP outside TX | Must accept snapshot data may change |
| HTTP request needing immediate synchronous response | Short TX to read/update state, HTTP outside TX, short TX to persist result | Outcome uncertain on timeout; requires idempotency |
| Critical orders/payments/integrations | Transactional outbox + worker + idempotent receiver | Eventual consistency, added state and ops |
| Loss-tolerant one-way telemetry | Commit → in-memory executor/queue | No delivery guarantee on crash |
| JMS/AMQP/Kafka messages updating DB | Listener/handler aligns DB TX and acks cleanly, idempotent | Not automatically atomic between broker and DB |
| SFTP upload exporting business files | Staging/outbox → upload outside DB TX → verify/mark | Must handle partial files and retries |
| Multi-remote-service workflow | Saga/choreography/orchestration with compensation | No cross-system ACID |
| Client lacks idempotency and side effects are irreversible | Reconciliation, operation tracking, manual review | Never claim exactly-once from simple retries |

**Never call a design "safe" simply because HTTP moved to `@Async`.** Evaluate **durable intent, crash state, idempotency, uncertain outcomes, and reconciliation**.

## 8. Splitting Short Transactions in a Synchronous Service

When you only need a single immediate partner call, use **two short local transactions** with the HTTP call in between:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant S as Orchestration
    participant T as DB state service
    participant P as Partner
    C->>S: Submit order
    S->>T: markPending(orderId)
    T->>T: BEGIN → UPDATE PENDING → COMMIT
    S->>P: POST order (outside DB tx)
    P-->>S: result
    S->>T: markResult(orderId, result)
    T->>T: BEGIN → UPDATE result → COMMIT
    S-->>C: Result
~~~

One **concrete way** is `TransactionTemplate`. Logical example:

~~~java
@Service
public class ShippingOrchestrator {
    private final TransactionTemplate transactionTemplate;
    private final OrderRepository orders;
    private final ShippingClient client;

    public ShippingOrchestrator(
            TransactionTemplate transactionTemplate,
            OrderRepository orders,
            ShippingClient client) {
        this.transactionTemplate = transactionTemplate;
        this.orders = orders;
        this.client = client;
    }

    public ShipmentReceipt submit(String orderId) {
        // First short transaction.
        transactionTemplate.executeWithoutResult(status ->
                orders.markPending(orderId));

        // Outside the DB step's TransactionTemplate.
        ShipmentReceipt receipt = client.reserve(
                orderId, "shipment-" + orderId);

        // Next short transaction.
        transactionTemplate.executeWithoutResult(status ->
                orders.markSubmitted(orderId, receipt.shipmentId()));

        return receipt;
    }
}
~~~

`OrderRepository` and `ShippingClient` are illustrative business interfaces; `TransactionTemplate` must be configured with the right transaction manager. **Mandatory condition:** `submit` **must not be invoked from inside an outer transaction** if the goal is keeping the remote call outside all DB transactions. If the caller already opened a transaction, both `TransactionTemplate` blocks default to **joining the outer transaction** under `PROPAGATION_REQUIRED`.

Therefore, **verify entry boundaries** at controllers/message handlers rather than looking only at two `executeWithoutResult(...)` calls. Use a non-`@Transactional` entry service, invoke via proper bean/proxies, or configure propagation deliberately and test. **`REQUIRES_NEW` does not solve an outer transaction**: it only suspends and opens a new inner TX, after which the outer TX resumes and stays open during the remote call.

### 8.1. Where Does Reliability Still Fall Short?

The pattern above still has gaps:

1. `markPending` committed.
2. Process dies **before** `client.reserve` → order stays `PENDING` forever without recovery.
3. Partner succeeds yet client times out → true status unknown.
4. Partner succeeds then `markSubmitted` fails → retries risk resending.
5. Caller retries all of `submit` → requires idempotency to avoid duplicates.

**This is merely transaction splitting**, not reliable delivery. For critical work, persist **durable intent/outbox** in the same transaction as business state, and let a worker send and recover.

## 9. Transactional Outbox: Decoupling DB Commit from Remote I/O Without Losing Send Intent

**Transactional outbox** inserts an outbound record inside **the same database transaction** as the business update. After commit, a dispatcher pulls outbox records and calls HTTP/SFTP/JMS/AMQP/Kafka **outside any DB transaction**. Once outcomes arrive, the worker persists status in another short transaction.

~~~mermaid
flowchart LR
    REQ["Inbound command"] --> TX1["Short DB transaction"]
    TX1 --> BIZ["Orders / business rows"]
    TX1 --> OB["Outbox: PENDING"]
    OB --> WORKER["Dispatcher / poller"]
    WORKER --> REMOTE["HTTP / SFTP / broker"]
    REMOTE --> TX2["Short DB transaction: SENT / RETRY"]
    TX2 --> AUDIT["Outcome / audit"]
    WORKER -. "retry/idempotency" .-> REMOTE
~~~

**Key guarantee:** if the first transaction commits, send intent is **durably persisted** in the DB (per DB durability); if it rolls back, both business updates and outbox **roll back together**. The dispatcher processes afterward with retries and monitoring.

**No end-to-end exactly-once guarantee.** The dispatcher can send successfully and crash before marking `SENT`. Upon restart, it sends again. Enforce **idempotency keys at partners/consumers, deduplication, or reconciliation**.

### 9.1. States to Manage

A simple state machine:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> IN_FLIGHT: claim + lease
    IN_FLIGHT --> SENT: confirmed outcome
    IN_FLIGHT --> RETRY: transient error
    RETRY --> IN_FLIGHT: backoff expired
    IN_FLIGHT --> UNKNOWN: timeout / uncertain outcome
    UNKNOWN --> IN_FLIGHT: safe replay/reconcile
    UNKNOWN --> MANUAL_REVIEW: cannot determine
    IN_FLIGHT --> DEAD: permanent failure / policy exhausted
    SENT --> [*]
    DEAD --> MANUAL_REVIEW: operator decision
~~~

These states are a **reference model**, not built into Spring Integration. Real systems may add `CANCELLED`, `COMPENSATING`, `FAILED_FINAL`, or versions; define valid transitions and authorized actors.

### 9.2. Idempotency Keys

Use a **business-stable ID**, such as `shipment:order-42:v1`, saved alongside the outbox record and sent to remote APIs that support idempotency. Never generate a fresh UUID for the same event on each retry; attempt IDs may vary, while **the event/operation ID must stay stable** so receivers recognize duplicate attempts.

## 10. Auditable Outbox Data Model

**PostgreSQL**-style DDL example for `integration_outbox`; adjust schema and indexes to your workload and DB engine:

~~~sql
CREATE TABLE integration_outbox (
    id UUID PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    destination VARCHAR(120) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload_json JSONB NOT NULL,
    idempotency_key VARCHAR(180) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    leased_until TIMESTAMPTZ,
    lease_token UUID,
    remote_receipt_id VARCHAR(180),
    last_error_code VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT outbox_status_check CHECK (
        status IN ('PENDING', 'IN_FLIGHT', 'RETRY',
                   'UNKNOWN', 'SENT', 'DEAD')
    )
);

CREATE INDEX outbox_ready_idx
    ON integration_outbox (status, next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY', 'UNKNOWN');

CREATE INDEX outbox_expired_lease_idx
    ON integration_outbox (leased_until)
    WHERE status = 'IN_FLIGHT';
~~~

**Schema options:** you may also need tenant IDs, owners, trace IDs, `created_by`, event versions, destination partitions/keys, lease owners, and retention. Avoid storing access tokens, passwords, or unnecessary PII in payloads/outbox/error fields; encrypt and restrict access if sensitive data is present.

An outbox row represents **intent to work**, not proof of delivery. Update to `SENT` only after meaningful protocol/contract confirmation; a `MessageChannel.send()` into an in-memory queue is **not always sufficient**.

## 11. Claim Fast, Commit Immediately, Then Send: Avoid Holding Row Locks Over Network Waits

**Common outbox mistake:** a worker opens a transaction, runs `SELECT ... FOR UPDATE` on a row, **holds the row lock**, calls HTTP inside the transaction, and only then runs `UPDATE status=SENT` and commits. That merely **moves the anti-pattern** from the business transaction into the outbox dispatcher.

~~~text
WRONG:
  BEGIN
  SELECT ... FOR UPDATE
  POST /remote       <- holds row lock while waiting
  UPDATE status=SENT
  COMMIT

RIGHT DIRECTION:
  BEGIN
  CLAIM record + lease/fencing token
  COMMIT             <- releases DB lock
  POST /remote       <- outside DB transaction
  BEGIN
  MARK_SENT if token is still valid
  COMMIT
~~~

### 11.1. Claiming Rows Without Holding Locks Across Remote Calls

A PostgreSQL multi-worker strategy uses `FOR UPDATE SKIP LOCKED` to avoid contending on the same row. Run the SQL below **inside a short transaction**:

~~~sql
WITH picked AS (
    SELECT id
    FROM integration_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND next_attempt_at <= CURRENT_TIMESTAMP
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE integration_outbox AS o
SET status = 'IN_FLIGHT',
    attempts = o.attempts + 1,
    leased_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    lease_token = :new_lease_token,
    updated_at = CURRENT_TIMESTAMP
FROM picked
WHERE o.id = picked.id
RETURNING o.id, o.payload_json, o.destination,
          o.idempotency_key, o.lease_token, o.attempts;
~~~

This is a **PostgreSQL-oriented pattern**, not portable SQL for every DB. `:new_lease_token` is a fresh UUID generated by the dispatcher per claim; Spring JDBC needs named-parameter configuration to bind it. **Intentionally avoid auto-claiming `UNKNOWN` or expired leases for immediate resends:** an earlier attempt may have succeeded remotely. Reconcile the outcome or verify remote idempotency before transitioning back to `RETRY`. In practice, also cap batch sizes, enforce backoff, handle expired leases separately, enforce tenant fairness, and alert on backlogs.

Example transitioning expired leases to reconciliation in a separate short transaction:

~~~sql
UPDATE integration_outbox
SET status = 'UNKNOWN',
    leased_until = NULL,
    lease_token = NULL,
    last_error_code = 'LEASE_EXPIRED_OUTCOME_UNCERTAIN',
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'IN_FLIGHT'
  AND leased_until < CURRENT_TIMESTAMP
RETURNING id, idempotency_key;
~~~

A reconciler can move `UNKNOWN` to `SENT` once the remote confirms, or to `RETRY` when resending is safe. Never treat lease expiration as proof the remote never received the request.

**Never retain a connection/transaction** while HTTP/SFTP requests run. Copy the record fields into memory and close the claim transaction before calling the client.

### 11.2. Marking Outcomes with a Fencing Token

If a worker runs slower than `leased_until`, another worker can reclaim the row. To stop the old worker from overwriting the newer worker's state, guard updates with a **fencing/lease token**:

~~~sql
UPDATE integration_outbox
SET status = 'SENT',
    leased_until = NULL,
    lease_token = NULL,
    remote_receipt_id = :remote_receipt_id,
    last_error_code = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND status = 'IN_FLIGHT'
  AND lease_token = :lease_token
  AND leased_until > CURRENT_TIMESTAMP;
~~~

If `UPDATE` affects **0 rows**, **never** treat it as success; the worker likely lost lease ownership. Read/inspect the current state and reconcile if the remote succeeded. Define rules for late responses arriving after lease expiry (e.g., logging verified outcome without overwriting a newer attempt).

**A lease token does not stop duplicate remote requests.** It only prevents **stale DB state writes**. Preventing duplicate target side effects requires idempotency keys, status queries, or remote support.

### 11.3. Lease Duration Is Not the HTTP Timeout

If the HTTP timeout is 45 seconds while the lease is only 30 seconds, another worker can reclaim while the first request is still running. Options:

- Set a **hard timeout on remote calls** safely below the lease duration.
- Renew leases via heartbeats for long work with active monitoring.
- Enforce fencing tokens, accept at-least-once, and pair with idempotency.
- When remote operations cannot be cancelled or timeouts are ambiguous, reconcile before retrying.

Never set infinite leases because dead workers would strand rows forever. Never treat an active lease as proof the remote has not processed the request.

## 12. Java: Separating the Outbox Writer Service from the Remote Dispatcher

A testable design separates three roles:

1. **Command service:** inside a DB transaction, updates business state and inserts into the outbox.
2. **Claim/outcome service:** each method runs its own short DB transaction.
3. **Dispatcher:** holds no outer transaction; calls remote systems between short DB calls.

Skeleton example:

~~~java
public record OutboxJob(
        UUID id,
        String destination,
        String payloadJson,
        String idempotencyKey,
        UUID leaseToken,
        int attempts
) {}

public interface PartnerClient {
    SendReceipt send(String destination,
                     String payloadJson,
                     String idempotencyKey);
}

public record SendReceipt(String remoteOperationId) {}

public interface OutboxRepository {
    void insert(UUID id, String orderId, String payloadJson,
                String idempotencyKey);

    OutboxJob claimNext(UUID leaseToken);

    int markSent(UUID id, UUID leaseToken, String remoteOperationId);

    int scheduleRetry(UUID id, UUID leaseToken,
                      String errorCode, Instant nextAttemptAt);

    int markUnknown(UUID id, UUID leaseToken,
                    String errorCode, Instant reviewAt);
}
~~~

These interfaces/records are **application-defined**, not built-in Spring Integration APIs. A production `OutboxRepository` must implement atomic SQL, leases/fencing, transactions, and idempotency for your database.

### 12.1. Creating the Order and Outbox Share One Transaction

~~~java
@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderCommandService(OrderRepository orders,
                               OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID approve(String orderId, String payloadJson) {
        orders.markApproved(orderId);

        UUID eventId = UUID.randomUUID();
        String idempotencyKey = "shipment:" + orderId + ":v1";

        outbox.insert(eventId, orderId, payloadJson, idempotencyKey);
        return eventId;
    }
}
~~~

**Production requirements:** same `DataSource`/transaction manager and same transaction for both `orders.markApproved` and `outbox.insert`; idempotency constraints; handling duplicate requests; and updating aggregate version when emitting new events. Never rely on `UUID.randomUUID()` as an idempotency key: a fresh UUID on every retry creates separate records. This sample shows the structure without defining `OrderRepository` or SQL implementations.

### 12.2. Short DB Methods on a Dedicated Bean

~~~java
@Service
public class OutboxStateService {
    private final OutboxRepository outbox;

    public OutboxStateService(OutboxRepository outbox) {
        this.outbox = outbox;
    }

    @Transactional
    public OutboxJob claim() {
        return outbox.claimNext(UUID.randomUUID());
    }

    @Transactional
    public boolean complete(OutboxJob job, SendReceipt receipt) {
        return outbox.markSent(
                job.id(),
                job.leaseToken(),
                receipt.remoteOperationId()) == 1;
    }

    @Transactional
    public boolean retry(OutboxJob job, String errorCode,
                         Instant nextAttemptAt) {
        return outbox.scheduleRetry(
                job.id(), job.leaseToken(),
                errorCode, nextAttemptAt) == 1;
    }

    @Transactional
    public boolean uncertain(OutboxJob job, String errorCode,
                             Instant reviewAt) {
        return outbox.markUnknown(
                job.id(), job.leaseToken(),
                errorCode, reviewAt) == 1;
    }
}
~~~

**`@Transactional` proxy note:** these methods must be called **through a properly proxied Spring bean**, not via self-invocation inside the same class, and the outer dispatcher method must not hold an active transaction. In Spring AOP, internal `this.claim()` bypasses the interceptor. Using a separate bean keeps boundaries clear.

### 12.3. Dispatcher Calls Client *After Commit* and Before the Next Transaction

~~~java
@Component
public class OutboxDispatcher {
    private final OutboxStateService state;
    private final PartnerClient partner;

    public OutboxDispatcher(OutboxStateService state,
                            PartnerClient partner) {
        this.state = state;
        this.partner = partner;
    }

    public void dispatchOne() {
        OutboxJob job = state.claim();  // short tx, committed on return
        if (job == null) {
            return;
        }

        try {
            // No DB transaction wraps this method.
            SendReceipt receipt = partner.send(
                    job.destination(),
                    job.payloadJson(),
                    job.idempotencyKey());

            boolean recorded = state.complete(job, receipt); // fresh tx
            if (!recorded) {
                // Lease expired: route to reconciliation/alert,
                // never overwrite blindly to mark success.
                reportStaleLease(job.id());
            }
        }
        catch (UncertainOutcomeException ex) {
            // HTTP timeout after request may have been sent: do not re-POST blindly.
            if (!state.uncertain(job, safeErrorCode(ex), Instant.now())) {
                reportStaleLease(job.id());
            }
        }
        catch (TransientPartnerException ex) {
            Instant next = backoffFrom(job.attempts());
            if (!state.retry(job, safeErrorCode(ex), next)) {
                reportStaleLease(job.id());
            }
        }
        catch (PermanentPartnerException ex) {
            // Needs a transactional transition to DEAD/MANUAL_REVIEW,
            // handled by the state service per policy.
            markForReview(job, ex);
        }
    }
}
~~~

`reportStaleLease`, `backoffFrom`, `safeErrorCode`, `markForReview`, and the three exception classes are **helpers/interfaces to implement**, intentionally sketched rather than pretending to be immediately runnable code. In particular, **distinguish `UncertainOutcomeException` from pre-send errors**: an HTTP read timeout may mean the remote already applied the side effect, so transition to `UNKNOWN` and reconcile instead of auto-retrying. `markUnknown` and `scheduleRetry` must perform conditional updates guarded by lease token and expected state; `reviewAt` is the scheduled reconciliation time. This pattern illustrates state transitions, not a verified DB/HTTP client setup.

**Critical condition:** `dispatchOne()` has no `@Transactional` and must never be called inside another transaction if the remote call must stay outside DB transactions. If a poller accidentally attaches transaction advice around all of `dispatchOne()`, this pattern **loses its boundary**.

### 12.4. Why Not Put `@Transactional(REQUIRES_NEW)` on the Whole Dispatcher?

Putting `REQUIRES_NEW` on `dispatchOne()` causes the worker to open a new transaction wrapping `partner.send(...)`—repeating the original anti-pattern. `REQUIRES_NEW` helps only when **intentionally scoping a short DB write**, while accounting for outer transaction suspension/resumption. In this design, **the dispatcher itself has no transaction**, while the state service runs its own short transactions.

## 13. Spring Integration: Designing Flows That Never Hold DB Transactions Over HTTP/SFTP

### 13.1. Outbox-Driven Flow

~~~mermaid
flowchart TD
    CMD["Inbound Adapter / Gateway"] --> VALIDATE["Validate / map command"]
    VALIDATE --> TX["OrderCommandService @Transactional"]
    TX --> ORDER["Business row + outbox row commit together"]
    OUTBOX["DB outbox poller"] --> CLAIM["Claim service @Transactional (short)"]
    CLAIM --> SEND["HTTP/SFTP/JMS/AMQP/Kafka outbound (no DB tx)"]
    SEND --> COMPLETE["State service @Transactional (short)"]
    SEND -. "failure" .-> RETRY["Retry/reconcile/dead-letter state"]
    ORDER --> OUTBOX
~~~

Spring Integration can orchestrate the dispatcher, provided you place **transaction advice at the right spot**. Putting transaction advice on a JDBC inbound poller wired straight into a synchronous HTTP handler wraps the remote call in the DB transaction.

The clean split is letting the poller/handler **claim in a short transaction and return the committed `Job`**, then pass that `Job` to the remote handler **outside the claim transaction**. If a single `DirectChannel` flow uses poller transaction advice covering all downstream handlers, merely "splitting methods" may not split the transaction. Verify with a transaction probe.

### 13.2. Java DSL Example for Out-of-Transaction Dispatch

~~~java
@Configuration
@EnableIntegration
class OutboxFlowConfig {

    @Bean
    MessageChannel dispatchChannel(TaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    IntegrationFlow outboxDispatchFlow(
            OutboxDispatcher dispatcher) {
        return IntegrationFlow
                .from("dispatchChannel")
                .handle(message -> dispatcher.dispatchOne())
                .get();
    }
}
~~~

**This is an orchestration skeleton**, not a complete production outbox flow: you need a controlled trigger feeding `dispatchChannel` (such as a scheduled task/poller), capacity/backpressure controls, error handlers, and lifecycle management. `ExecutorChannel` only dispatches asynchronously **in memory**—it does not make tasks durable. **Durability lives in the outbox DB**, and workers must scan/retry records upon restart.

If an executor isn't needed, a scheduled worker can invoke `OutboxDispatcher.dispatchOne()` directly and use a channel only to publish events/metrics; that is often simpler and easier to verify boundaries on.

### 13.3. Never Confuse `@Async` with an Outbox

~~~text
Commit order
  -> applicationEventPublisher.publishEvent(...)
  -> @Async listener sends remote
~~~

When the event exists only in RAM, crashing after commit and before the listener runs **loses the send**. `@TransactionalEventListener(phase = AFTER_COMMIT)` does not make the event durable either: the callback still lives in the current process and can fail or vanish if the process dies. For mandatory delivery, insert an **outbox record** inside the transaction and back it with a recovering worker.

### 13.4. Traps of `@TransactionalEventListener(AFTER_COMMIT)`

An after-commit callback may still see the thread's transaction synchronization/resources in certain cases; Spring docs warn that interacting with resources inside an after-commit callback requires a new transaction to **genuinely commit new DB writes**. Never rely on this callback to replace an outbox, and if persisting results after commit, use an explicitly verified independent transaction.

## 14. Pollers: Transactions at Source, Consumer, and Handoff

Pollers can use transaction advice to protect source reads and status updates. Distinguish clearly:

- **Source polling transaction:** reading outbox rows, claiming leases, and updating DB status.
- **Downstream handler transaction:** persisting result state after the remote call.
- **Network call:** HTTP/SFTP/broker publish running **with no DB transaction**.

### 14.1. Anti-Pattern from Overly Broad Advice

~~~text
Polling endpoint:
  transactionAdvice: begin
  source.receive() -> read/lock outbox row
  downstream.handle() -> HTTP gateway call (slow)
  transactionAdvice: commit

=> Transaction spans both receive + handle.
~~~

**Fix principle:** bound the transaction to **claim/read-state**, or split the handoff out of the poller's transaction with verified boundaries. Never add a `QueueChannel` and assume the transaction automatically closes at the right point; it depends on which side of the channel the poller sits on and which handlers stay in scope.

### 14.2. When a JDBC Inbound Adapter Reads Multiple Rows

If a source reads a 100-row batch and a worker holds one transaction while calling 100 HTTP APIs, total lock duration scales with summed latencies. Split **claim batch → commit**, then process each job with bounded concurrency without holding row locks. Each job maintains independent status/lease/idempotency for retries.

### 14.3. Optimizing Batching and Backpressure

- `maxMessagesPerPoll` caps messages per poll, **not** total concurrent executions across executors or multiple instances.
- Cap concurrent remote calls to protect both partners and your own app.
- When backlogs grow, rely on metrics and scale workers within capacity limits.
- Never grow thread pools unboundedly just to "hide" HTTP latency.
- When source queues/brokers apply backpressure, ensure acks/offsets/leases align with actually completed work.

## 15. HTTP Outbound: Timeouts, Uncertain Outcomes, and Idempotency

HTTP outbound gateways/adapters are a classic source of remote latency. At minimum, configure:

| Timeout / policy | Purpose |
|---|---|
| **Connection timeout** | Caps time to establish TCP/TLS connection |
| **Read/response timeout** | Caps wait for response |
| **Total/deadline** | Overall operation deadline including retries |
| **Retry/backoff** | Bounded attempts and delays with jitter |
| **Circuit breaker / bulkhead** (when needed) | Stops one slow partner from starving the whole app |
| **Idempotency key** | Identifies repeated attempts after timeouts |
| **Reconciliation / status query** | Verifies outcome when responses drop |

**No single default timeout fits every service.** Tune to SLAs, server timeouts, pool capacity, and lease durations using real metrics. Business deadlines do not equal HTTP socket timeouts. Likewise, a test queue `receive(2000)` timeout **does not prove** HTTP read timeouts are configured.

### 15.1. An HTTP Timeout Does Not Prove Server Failure

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant API as Partner API
    participant DB as Local DB
    W->>API: POST /shipments key=shipment:42
    API->>API: Create shipment sh-42
    Note over W,API: Response lost / client timeout
    W->>DB: mark UNKNOWN / retry scheduled
    W->>API: GET /operations/shipment:42
    API-->>W: Already completed: sh-42
    W->>DB: Mark SENT with remote receipt
~~~

If the API offers neither status queries nor idempotency, choose among risky duplicate retries, manual reconciliation, or compensation. **Never claim exactly-once** simply because a retry template is configured.

### 15.2. Outbound Gateways and the Caller's Transaction

If an inbound API request must wait for an outbound gateway reply, the HTTP request itself takes longer, yet **the DB transaction does not have to stay open with it**. Model `PENDING/PROCESSING/SUBMITTED/FAILED` states with short transactions before and after the gateway. When low latency is needed against slow remotes, consider `202 Accepted` with an operation ID and status endpoint—noting that is an **API contract change** that must not be introduced silently.

## 16. SFTP: Never Hold Database Transactions Across File Transfers

SFTP uploads can take seconds or minutes, especially for large files. Opening a DB transaction to mark "exporting file" and waiting for upload holds connections and locks far too long.

Safer design:

1. Short transaction writes **export intent** with `exportId`, filename, checksum/version, validated remote path, and status `PENDING`.
2. Worker claims the job and commits DB.
3. Generate payload / stage file **outside the DB transaction** using snapshots/versions or checksums for stability.
4. Upload to a **temporary remote path** (if supported by server/contract).
5. Verify upload completion; rename to final path using server-supported mechanics.
6. Short transaction persists `SENT`/remote receipt; on timeout transition to `UNKNOWN` or retry/reconcile.
7. Clean up staging and temp files per retention/recovery policy.

**Temp upload + rename** improves the odds consumers see only complete files, yet does not guarantee atomicity on every SFTP server/filesystem. Verify server semantics, handle rename failures, and reconcile pre-existing files.

### 16.1. Idempotency for File Exports

Keys like `export:<business-id>:<version>` and deterministic remote filenames help spot duplicate transfers. Still, an existing remote path does not always prove valid contents: check size, checksum, or metadata, and distinguish files written by other processes.

### 16.2. File Inbound Carries Similar Risks

If a file inbound poller opens a DB transaction for the whole flow and then parses huge files or calls slow HTTP APIs, transactions drag on. Parse/validate outside the TX where appropriate, commit DB results in small batches, and use durable idempotency keys to avoid reprocessing files after restarts.

## 17. JMS and AMQP: Broker Transactions and Slow HTTP Handlers

A JMS/AMQP listener receives messages and feeds a Spring Integration flow. Broker transactions/acknowledgments are a separate boundary from local DB transactions.

### 17.1. Flow Prone to Backlogs

~~~text
Broker message received
  -> listener transaction / ack pending
  -> DB update @Transactional
  -> HTTP external call 30s
  -> local DB commit
  -> broker ack/commit (per config)
~~~

When the handler is slow, consumer slots stay occupied, unacked/in-flight counts climb on the broker, and redelivery/requeue/timeout risks grow. If a DB transaction stays open simultaneously, pools and locks suffer too.

### 17.2. Design Direction

- Consume the message and apply **DB mutation + outbox insert** inside a short DB transaction.
- Ack/commit the broker per defined semantics and ordering; if crashing between DB commit and broker ack, **the message may redeliver**, so enforce deduplication/inbox/unique business keys.
- A worker outside the broker listener executes remote HTTP/SFTP with retries and idempotency.
- Separate `INBOUND_ACCEPTED` from `EXTERNAL_DELIVERED` in audits and metrics.

**Subtlety:** "ack after DB commit" is a logical model; across different containers/providers, verify ack modes, transaction managers, and error handlers. Spring transaction synchronization can coordinate parts, yet **does not automatically make DB + JMS/AMQP one atomic transaction** without proper distributed transaction machinery.

### 17.3. Consumers Must Never Hold Transactions While Waiting on Retry/Backoff

If retry advice sleeps/backs off inside an active DB transaction, it holds resources throughout the sleep. Persist retry delays as **scheduled `next_attempt_at`** or use broker retry/delay topologies, and **end the transaction before** waiting for the next attempt.

## 18. Kafka: Offsets, Producer Transactions, and DBs Have Different Boundaries

Kafka has its own model: producer sends, broker append/acks, consumer poll/offset commits, and (when configured) Kafka transactions. None of these equal a DB transaction opened by `@Transactional`.

| Aspect | Key reminder |
|---|---|
| Async producer `send()` | Future may complete after handler returns; check callbacks/results |
| Kafka producer transaction | Can group Kafka operations; does not auto-include HTTP/SFTP/DB |
| Consumer offset | Committed offset marks read position, not remote side-effect confirmation |
| Redelivery | Crashing before offset commit replays events |
| Long processing | Affects consumer poll intervals, rebalances, and throughput |
| DB transaction | If opened before remote calls, still suffers lock/pool pressure |
| Exactly-once claims | Scope explicitly to Kafka transactions/streams, not the whole system |

### 18.1. Kafka → DB → HTTP Flow

Recommended path:

1. Consumer receives record, validates schema and business event ID.
2. In a short DB transaction, upsert state/dedup and insert an outbox intent. If already present, apply the idempotent decision.
3. Commit DB.
4. Commit offset/ack per container policy; if commit fails it re-reads, and dedup blocks duplicate inserts.
5. Outbox worker sends HTTP and persists outcomes in a short transaction.

**Test real crash windows** between DB commit and offset commit. No ordering eliminates every duplicate when two resources do not share one transaction. Ensuring **safe reprocessing** is far more practical than demanding zero re-reads.

### 18.2. When Kafka Is the Outbox Target

Workers can publish outbox events to Kafka. Mark `SENT` only after confirmation meeting policy—not immediately upon enqueuing a producer future if broker ack is required. Workers can crash after ack and before marking `SENT`; Kafka consumers should deduplicate by `eventId` whenever side effects are non-idempotent.

## 19. Waiting on Slow Services Stays Outside DB Transactions—Yet Still Needs Load Limits

Even after removing slow calls from DB transactions, remote calls still occupy threads and HTTP/SFTP/broker client connection pools. An app firing 10,000 outbox jobs simultaneously creates new bottlenecks.

Operational controls:

- Cap **concurrency per destination** or tenant, not only global thread counts.
- Size HTTP/SFTP client connection pools and timeouts appropriately.
- Use bounded executors/queues with explicit rejection/backpressure policies.
- Use jittered retries and circuit breakers to prevent retry storms.
- Separate permanent errors from transient errors; never retry schema/auth failures endlessly.
- Track queue age, oldest pending, `IN_FLIGHT` age, retry counts, and lease expirations.
- Ensure scanning/dispatching survives restarts, duplicates, and concurrent execution.

**Splitting transactions is necessary but not sufficient.** You also need capacity planning, durability, idempotency, and observability so you don't simply shift the bottleneck from the DB pool to a thread pool or partner.

## 20. Spring `@Transactional` Propagation: Useful Tool, Not a Magic Escape Hatch

Spring transaction management supports propagation modes such as `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `NOT_SUPPORTED`, `NESTED`, `MANDATORY`, and `NEVER`. **Avoiding holding transactions across slow services** requires knowing precisely when an older transaction still remains alive.

| Propagation | When caller already holds a DB TX | Relevance here |
|---|---|---|
| `REQUIRED` | Joins existing TX | Default on many services; easily stretches TX over slow I/O |
| `REQUIRES_NEW` | Suspends outer TX, starts new TX | Useful for isolated DB writes; **does not** release outer TX locks |
| `NOT_SUPPORTED` | Suspends outer TX, runs non-TX | Splits inner call stack, **yet** outer TX stays open holding resources |
| `SUPPORTS` | Joins if present, else non-TX | Cannot guarantee remote calls stay out of TX |
| `NEVER` | Throws if called inside a TX | Useful guardrail at remote-sending boundaries |
| `MANDATORY` | Requires active TX, else throws | Useful to enforce DB writes run inside a TX |
| `NESTED` | Savepoint inside active TX if supported | Does not isolate remote I/O into an independent transaction |

### 20.1. Traps of `NOT_SUPPORTED` and `REQUIRES_NEW`

~~~java
@Transactional
public void outerProcess(String orderId) {
    orders.updateWithLock(orderId);     // DB transaction holds lock
    remoteSender.sendOutsideTx(orderId); // @Transactional(NOT_SUPPORTED)
    orders.markReady(orderId);
}
~~~

`sendOutsideTx` executes with proxy transaction synchronization suspended, yet **the outer DB transaction has not committed**. It may still hold suspended row locks and connections until `outerProcess` exits. Therefore **`NOT_SUPPORTED` does not truly fix the problem** if the outer transaction already acquired locks/resources.

**Root fix:** commit the DB portion **before** entering remote orchestration—change the **call graph and transaction entrypoint**, not merely an annotation on a helper.

### 20.2. Self-Invocation

~~~java
@Service
class UnsafeService {

    public void handle(String orderId) {
        this.persistIntent(orderId); // self invocation
    }

    @Transactional
    public void persistIntent(String orderId) {
        // In standard AOP proxy mode, calling via `this`
        // can bypass the @Transactional interceptor.
    }
}
~~~

In standard Spring AOP proxy mode, internal `this.method()` calls bypass the proxy so the annotation on the target method may not apply. Move the transaction boundary onto a **separate Spring bean**, call externally through the proxy, or use `TransactionTemplate` explicitly. Note other weaving/proxy modes behave differently; always test in your real config.

### 20.3. Never Wrap Sleeps or Rate Limiters in a Transaction

If a retry policy sleeps for backoff or a rate limiter waits for a permit, perform that wait **before opening the DB transaction**. Never put `Thread.sleep`, semaphore waits, network waits, or executor waits inside a transaction.

## 21. Optimistic Concurrency: Instead of Holding Locks Until External Services Reply

One reason developers hold transactions over HTTP is wanting to **ensure the order doesn't change** while calling the partner. Holding row locks for seconds is rarely the right answer.

An alternative is **optimistic versioning and a state machine**:

~~~text
T0: short tx
  read order version=7
  mark state=SUBMITTING, increment version to 8
  persist operationId=shipment:42:v7
  commit

T1: remote I/O without DB transaction
  call partner with operationId

T2: short tx
  UPDATE order
  SET state=SUBMITTED, version=9
  WHERE id=42 AND version=8 AND state=SUBMITTING
~~~

`T0` **incremented version** from `7` to `8`, so `T2` must check against the **post-`T0` committed version** (`8`), not the stale `7` snapshot. This models the versioning idea; implementations must define exact expected state/version values:

~~~sql
-- Illustrative finalization step: expected_version is taken from
-- the committed T0 state, never from a stale prior snapshot.
UPDATE orders
SET state = 'SUBMITTED',
    version = version + 1,
    remote_receipt = :receipt
WHERE id = :order_id
  AND version = :expected_version
  AND state = 'SUBMITTING'
  AND operation_id = :operation_id;
~~~

If `UPDATE` modifies `0` rows, never overwrite unconditionally; the order may have been cancelled, altered by another worker, or completed already. Read current state, reconcile with the remote, and decide next steps.

**Never let stale snapshots cause wrong sends:** if order details must stay immutable for dispatch, store the approved payload snapshot/version in the outbox record. Consumers/partners receive the operation ID and version instead of reading "latest" mid-flight when a fixed snapshot is intended.

## 22. Building a State Machine for Asynchronous Operations

Never model a request that can time out or retry with a single boolean `sent=true/false`. Explicit states separate cases cleanly:

| State | Meaning | Next action |
|---|---|---|
| `PENDING` | Send intent committed, unclaimed | Worker claims when due |
| `IN_FLIGHT` | Worker holds lease and attempts send | Await result; monitor lease/deadline |
| `SENT` | Verified result per contract | Do not resend unless separate policy dictates |
| `RETRY` | Transient error; retry time scheduled | Scheduler waits for `next_attempt_at` |
| `UNKNOWN` | Request may have been processed remotely | Query/reconcile before risky retries |
| `DEAD` | Auto-retries stopped (permanent error / limit hit) | Owner / manual handling / compensation |
| `CANCELLED` | Business cancelled intent prior to completion | Block new dispatches; handle in-flight race |
| `COMPENSATING` | Compensation step executing | Monitor receipt, latency, and compensation failures |

Short transactions persist state transitions. Every transition should validate actor, operation ID, expected state/version, lease token, and audit trail so two workers never mark success simultaneously or cancel improperly.

### 22.1. Cancelling an Order While a Remote Call Is In Flight

If an order is cancelled while a worker already sent the request, "setting `CANCELLED` in the DB" **does not make the remote request vanish**. Decide explicitly:

- Cancelled before claim: never dispatch.
- Cancelled while `IN_FLIGHT`: block new attempts, while handling late results from the in-flight attempt.
- Remote already created shipment: call cancel/compensation API if supported.
- Remote lacks cancel API: manual review / state and risk reconciliation.

Never write DB rollback logic assuming it cancels remote operations across all cases.

## 23. Failure Windows: Commit, Send, Ack, Crash

Inspecting transaction boundaries requires listing **crash windows**:

| Crash / failure point | What survives | Recovery path |
|---|---|---|
| Before business + outbox commit | Both roll back per local DB TX | Caller retries command via business key |
| After commit, before dispatcher claim | `PENDING` outbox persists durably | Next worker or restart claims it |
| After claim, before remote call | `IN_FLIGHT` with lease, likely unsent | Lease expires → reclaimed |
| During remote call | Side effect may have occurred partially | `UNKNOWN` / reconcile / idempotency |
| Remote succeeded, before marking `SENT` | Outbox still in flight | Retry may repeat; target must be idempotent |
| DB `SENT` update fails | Remote likely succeeded, DB unconfirmed | Reconcile, safe retry |
| Broker publish ack lost | Producer unsure if broker accepted | Idempotency / dedup by event ID |
| DB commit succeeds, broker ack fails | Inbound event may redeliver | Inbox / dedup in DB |
| Lease expires before worker returns | Another worker may have claimed | Fencing token, remote idempotency |
| Shutdown mid-SFTP upload | Remote may hold temporary file | Resume / cleanup / checksum policy |

**A sound design does not prevent every duplicate run; it makes duplicate runs safe and explainable.**

### 23.1. Blocking Duplicates with Unique Business Keys

An outbox constraint `UNIQUE (idempotency_key)` prevents inserting two duplicate intents for the same key in the DB. Still, duplicates can hit the **remote** even from one outbox row if workers retry; enforce target-side idempotency or query/compensation logic.

### 23.2. Why Never Mark `SENT` Before Sending?

~~~text
BEGIN -> mark SENT -> COMMIT -> HTTP send
                               ^
                               process crashes here
~~~

Crashing after marking `SENT` and before sending causes restarted workers to skip the row → lost send. For remote I/O, mark success **after verified confirmation**; embrace retryability and idempotency.

### 23.3. Never Treat ACK as Business Completion

An HTTP `202 Accepted`, Kafka broker ack, or RabbitMQ publisher confirm usually signals **acceptance** at the target transport, not consumer business completion. Use distinct states: `PUBLISHED` / `REMOTE_ACCEPTED` / `REMOTE_COMPLETED`. Pick milestones per contract and report accurately.

## 24. Reconciliation: When Responses Drop or States Diverge

Reconciliation compares **desired DB state** against **actual remote state**, especially for `UNKNOWN` operations or expired leases.

Example:

~~~text
Local outbox:
  operationId = shipment:42:v1
  status      = UNKNOWN
  attempts    = 2

Partner:
  lookup operationId -> shipmentId=sh-42, state=CREATED

Action:
  short DB tx: mark SENT + store remote receipt
  no extra POST
~~~

If the remote returns "not found," retry the POST only when policy confirms the **lookup result is authoritative and strongly consistent**; an eventually consistent API might briefly return not found right after creation, risking duplicates on retry without idempotency. If the remote lacks lookup APIs, define manual-review thresholds and compensation scope.

### 24.1. Reconciliation Must Never Hold DB Transactions Open While Querying Remotes

A reconciler is also a remote client. Design it cleanly:

1. In a short transaction, claim a batch of `UNKNOWN` rows and copy keys to check.
2. Commit; call the partner query API outside any DB transaction.
3. In a short transaction, update outcomes guarded by expected state/version/lease.
4. If state changed meanwhile, respect fencing and never overwrite blindly.

Do not repeat the anti-pattern by running `SELECT ... FOR UPDATE` and querying 100 remote operations inside one transaction.

## 25. Error Handling, Retries, and Backoff by Category

| Error | Usually retryable? | Controls |
|---|---|---|
| Transient disconnect / HTTP 503 | Yes, if operation is idempotent and policy permits | Bounded retries + exponential backoff + jitter |
| HTTP 429 | Honor `Retry-After`/quota and policy | Rate limiting and avoiding retry storms |
| HTTP 400 / schema invalid | Usually no, until payload is fixed | `DEAD`/reject with an owner |
| HTTP 401/403 | Never retry indefinitely | Fix credentials/scopes, alert |
| HTTP timeout after body sent | Outcome **uncertain** | `UNKNOWN`, idempotency, query/reconciliation |
| Mid-stream SFTP transfer failure | Depends on partial file, temp rename, checksums | Verified cleanup/resume |
| JMS/AMQP consumer nack/redelivery | Per broker policy | Dedup, DLQ, no infinite loops |
| Kafka producer future failure | Depends on exception and broker config | Producer policy, record ID, ack handling |
| DB deadlock / serialization conflict | Yes, retry short **local transaction** | Idempotent DB operations, backoff |
| Data integrity / unique violation | Depends on business semantics; may be valid duplicate | Separate dedup from genuine errors |

Key rule: **never put backoff sleeps inside a DB transaction**, and never configure unbounded retries on handlers holding broker sessions, transactions, or critical threads.

### 25.1. Retries with Jitter

Sample wait formula:

\[
delay = \min(delay_{max}, delay_{base} \cdot 2^{attempt - 1}) + jitter
\]

Bound `jitter`, guard against overflow at high attempt counts, and honor server `Retry-After` headers when present. This is a reference formula, not a built-in Spring Integration default. Persist `next_attempt_at` in the DB so workers recover smoothly across restarts.

### 25.2. Dead-Lettering Is Not "Deleting Errors"

Dead-letter records or DLQs must carry operation ID, error category, attempts, source/destination, and owner for investigation—**without leaking secrets**. Enforce replay policies after fixing data/permissions, always verifying idempotency and requiring review before replaying high-impact operations.

## 26. Operational Observability: Measure Transactions and Slow Services with the Right Metrics

Metrics that expose the anti-pattern and verify improvements:

| Group | Metrics / items to monitor |
|---|---|
| **DB transactions** | Duration p50/p95/p99, long-transaction counts, lock waits, deadlocks, timeouts |
| **Connection pools** | Active/idle/pending connections, acquisition waits, pool exhaustion |
| **Remote I/O** | HTTP/SFTP/broker latency, error %, timeout %, retry attempts |
| **Outbox** | Backlog count, oldest pending age, `IN_FLIGHT` age, `UNKNOWN` count, lease expirations |
| **Delivery correctness** | Duplicates detected, idempotency hits, reconciliation outcomes |
| **Consumer health** | JMS/AMQP unacked, Kafka lag/rebalances, poller delays |
| **Business outcomes** | Time to externally delivered/completed, manual-review backlog |
| **Security** | Failed auth/TLS/SSH, secret exposure risks, audit access controls |

**Never measure only HTTP duration** and assume transactions got shorter. Instrument **actual transaction begin/end points**, pools/locks, and external send durations.

### 26.1. Tracing and Correlation

Propagate business `operationId`/`correlationId` across steps:

~~~text
trace/order:
  operationId=shipment:42:v1
  receive -> db.commitIntent -> outbox.claim -> http.send
          -> http.result -> db.markSent -> audit
~~~

Keep correlation IDs stable across retries to trace one business unit, while attempt IDs distinguish individual tries. Never put passwords, access tokens, private keys, or unnecessary PII into headers/logs for tracing.

### 26.2. Actionable Alerts

- DB connection pool approaching saturation alongside climbing transaction duration p99.
- HTTP timeouts spiking **together with** outbox `UNKNOWN` counts.
- `IN_FLIGHT` jobs exceeding `leased_until` abnormally long.
- Outbox oldest pending age breaching workflow limits.
- Partner duplicate/idempotency conflicts or compensation counts rising.
- Kafka consumer lag growing because handlers stall on slow remotes.

## 27. Testing: Remote Clients Must Execute Outside DB Transactions

A proper test **checks more than the final result**. It **explicitly verifies transaction boundaries**.

### 27.1. Simple Probe at the Remote Call Site

Inside a fake/test-double client:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.transaction.support.TransactionSynchronizationManager;

final class RecordingPartnerClient implements PartnerClient {
    private final AtomicBoolean wasTransactional =
            new AtomicBoolean(true);

    @Override
    public SendReceipt send(String destination,
                            String payloadJson,
                            String idempotencyKey) {
        wasTransactional.set(
            TransactionSynchronizationManager
                    .isActualTransactionActive());
        return new SendReceipt("remote-op-42");
    }

    boolean observedActiveTransaction() {
        return wasTransactional.get();
    }
}
~~~

In a Spring integration test wired with dispatcher, state service, and DB:

~~~java
// Fixture prepared a PENDING outbox row and injected dispatcher + recordingClient.
dispatcher.dispatchOne();

assertFalse(recordingClient.observedActiveTransaction(),
        "Remote call must not execute inside a DB transaction");

assertEquals("SENT", outboxRepository.findStatus(jobId));
~~~

**Condition:** `dispatcher.dispatchOne()` must run **through the real topology** you want to verify (poller advice, channel, proxies)—not a direct method call bypassing transaction interceptors. `TransactionSynchronizationManager.isActualTransactionActive()` proves the current thread has no active Spring transaction, yet **does not prove** no suspended outer transaction still holds locks or no transaction lives on another thread. Add integration tests verifying row lock and connection availability.

### 27.2. Testing That DB Locks Are Released During Slow HTTP

A stronger test:

1. Insert order/outbox rows into the test DB.
2. Use a fake HTTP client with a `CountDownLatch` to **block right inside the remote call**.
3. On another thread, attempt to update/read-lock the related DB row with a short bounded deadline.
4. Verify that update completes while the fake remote is still blocked, per DB isolation/locking rules.
5. Release the latch, let the worker finish, and verify final state.
6. If tests pass only on H2 while targeting PostgreSQL, run against the production DB engine to confirm real lock behavior.

**Do not expect zero locking everywhere:** claiming still holds resources during the **short transaction before** remote I/O; the test proves resources **were released before** the remote call blocked.

### 27.3. Anti-Pattern Regression Test

Keep a test asserting the contract:

~~~text
Given:
  PartnerClient blocks for 5 seconds.
When:
  Input flow triggers send.
Then:
  remoteClient observes transactionActive=false
  DB lock does not wait 5 seconds
  connection pool does not hold connections across the remote TX
  job completes cleanly once released
~~~

Do not hard-code fragile 5-second wall-clock checks in CI. Use latches/awaits with bounded timeouts, and name tests for the **contract** rather than just implementation details.

### 27.4. Testing Business + Outbox Atomicity

- Inject failure inserting outbox after business update: both must roll back.
- Inject failure updating business state: outbox must not appear.
- On clean commit: both business state and outbox intent exist.
- Replay the same command/event: unique key prevents duplicate outbox rows per policy.
- Invalid event schema: reject cleanly at the boundary without leaving broken intents behind.

Never mock `@Transactional` and claim atomicity is tested. Run **database tests** with a real transaction manager.

## 28. Failure and Replay Testing for Reliability

A realistic test suite should cover:

| Case | Simulation | What must be proven |
|---|---|---|
| C1: Outbox commit fails | DB exception | Business row and outbox roll back together |
| C2: Crash post-commit, pre-send | Stop/restart worker | `PENDING` job recovers |
| C3: Crash post-claim | Skip remote call, expire lease | Job reclaimed safely |
| C4: Remote 503 | Client returns transient error | `RETRY`/backoff without holding DB TX |
| C5: Remote 400 | Client returns permanent error | `DEAD`/rejected without endless retries |
| C6: Timeout post-remote commit | Fake server persists then drops response | `UNKNOWN`/reconcile or idempotent retry |
| C7: Remote succeeds, DB mark fails | Force DB error | Recovery produces zero duplicate side effects |
| C8: Two workers claim concurrently | Concurrent transactions | Only one lease owner at a time |
| C9: Old worker replies post-lease expiry | Delay > lease | Fencing token blocks overwrite |
| C10: Duplicate broker input | Redeliver same event ID | DB/inbox/outbox never duplicate |
| C11: Kafka producer future fails | `CompletableFuture` fails | Never falsely marks `SENT` |
| C12: Partial SFTP upload | Disconnect mid-transfer | Never treats incomplete file as final |
| C13: Shutdown | Stop in-flight worker | Lease/retry/audit recover cleanly |
| C14: API `202 Accepted` | Async remote job | Never confuses accepted with completed |
| C15: Cancel mid-send | Operation changes state | Race/compensation handled properly |
| C16: Backpressure | Slow partner, many jobs | Bounded concurrency, no pool starvation |
| C17: Secret in payload | Sensitive token/header | Logs/outbox leak zero secrets |
| C18: Uncorrelated HTTP reply | Broken mapping | Detected; never misattributed |

**Not every test belongs in one fast unit suite.** Use unit tests for state transitions, integration tests for DB/outbox/pollers, mock HTTP/SFTP servers for remote outcomes, broker tests for acks/offsets, and staging tests for production-like infrastructure.

## 29. Case Study: JDBC Inbound → Slow HTTP Shipping

Suppose an order system has a JDBC inbound poller reading `orders_to_ship` and calling an HTTP shipping service taking 2–20 seconds.

### 29.1. Initial Design

~~~mermaid
flowchart LR
    SQL["JDBC polling @Transactional"] --> CH["DirectChannel"]
    CH --> HTTP["HTTP outbound gateway (slow)"]
    HTTP --> UPDATE["Update order as SHIPPED"]
    UPDATE --> COMMIT["Commit transaction"]
~~~

**Consequence:** when transaction advice wraps the entire synchronous chain, DB rows/connections stay pinned for many seconds; 20 concurrent consumers exhaust most of the pool, and HTTP timeouts roll back DB without undoing shipments already created remotely.

### 29.2. Redesigned Flow

~~~mermaid
flowchart LR
    CMD["DB/source events"] --> TX["Short transaction"]
    TX --> O["orders + outbox record"]
    O --> WORKER["Dispatcher claims lease, commits"]
    WORKER --> HTTP["HTTP shipping outside DB tx"]
    HTTP --> SUCCESS["Result short transaction"]
    HTTP -. "timeout" .-> UNKNOWN["UNKNOWN + reconciliation"]
    SUCCESS --> DONE["SUBMITTED"]
~~~

Workflow:

1. Poller/handler checks message ID and updates order status **plus an outbox record in one short DB transaction**.
2. Commit before making remote calls.
3. Worker claims record, assigns lease token, and commits.
4. Worker calls HTTP with a stable `operationId`/idempotency key and bounded timeout.
5. On `201` with receipt: short TX marks `SENT`; on `202`: record `ACCEPTED` and track completion.
6. On `503`: retry with backoff; on uncertain timeout: query partner/reconcile before resending if needed.
7. If server created the shipment yet DB mark failed: retry never creates a second shipment thanks to idempotency.
8. Measure transaction duration, pool occupancy, backlog, and order completion time before vs. after.

### 29.3. Trade-Offs to State Explicitly

- **Eventual consistency:** orders remain `PENDING`/`PROCESSING` until remote processing completes.
- **Extra operational complexity:** outbox table, workers, leases, alerts, cleanup.
- **Not exactly-once:** duplicates can occur; requires idempotent receivers and reconciliation.
- **Business latency:** total completion time may not shrink, yet DB locks/connections drop drastically and resilience improves.
- **Throughput limits:** still bounded by partner APIs and worker capacity; enforce backpressure.
- **Least privilege:** workers and sources hold scoped DB/API credentials rather than sharing one unrestricted credential.

## 30. Case Study: Kafka/JMS Inbound, DB Write, and Remote Notification

### 30.1. Story

A consumer receives `OrderPaid` from Kafka or JMS. A business service updates `orders.payment_status`, then sends a notification via HTTP webhook or email provider. Keeping everything inside one `@Transactional` method while waiting on a slow webhook/email stretches the DB transaction and blocks the consumer, growing lag and unacked counts.

### 30.2. Recommended Model

~~~text
Kafka/JMS inbound event
  -> Validate schema + eventId
  -> DB transaction:
       INSERT inbox(eventId) if absent
       UPDATE order payment state
       INSERT outbox(notificationIntent)
     COMMIT
  -> acknowledge/commit inbound per container policy

Outbox dispatcher:
  claim + COMMIT
  remote webhook/email outside DB transaction
  mark result + COMMIT
~~~

**Inbox/dedup** here is a table/unique constraint ensuring safety when the broker redelivers the same event ID. If DB commits and broker ack/offset commit fails, the event arrives again: the inbox detects prior processing and skips duplicating business side effects. Real ack behavior depends on container/provider; test rather than assuming Spring Integration handles it by default.

### 30.3. Common Mistakes

- Acking input **before** durable DB intent commits: crashes lose notifications.
- Sending webhooks **before** DB mutations commit: partners receive events while DB rolls back.
- Using Kafka offsets as business event IDs: offsets are scoped per topic/partition and do not replace global operation IDs.
- Sending email via SMTP then rolling back DB: sent emails are never unsent.
- Holding a JMS transaction open across a 60-second webhook retry sleep: stalls consumers/sessions and builds backlogs.
- Using volatile `ApplicationEventPublisher` without an outbox and assuming `AFTER_COMMIT` gives durable messaging.

### 30.4. Verifying Completion Levels

With email providers, HTTP `202` or SMTP `250` often proves only that the provider **accepted** the request. "Email delivered" depends on provider delivery reports; never equate `ACCEPTED` with `DELIVERED`. With webhooks, HTTP `200` may confirm receipt per contract while still requiring side-effect verification when business rules demand it.

## 31. Anti-Patterns and Why They Fail to Fix the Root Cause

| Anti-pattern | Why it is insufficient or wrong | Fix |
|---|---|---|
| Calling HTTP/SFTP inside `@Transactional` | Holds DB TX across I/O; rollback can't undo remote | Commit DB first, send outside TX, persist result in short TX |
| Using `REQUIRES_NEW` on HTTP helper | Still opens TX around network call; outer TX holds locks | Fix entry boundaries and call graph |
| Using `NOT_SUPPORTED` inside lock-holding outer TX | Outer TX suspends without committing/releasing locks | Commit outer TX before remote calls |
| Using `ExecutorChannel` instead of outbox | In-memory queues lose work on crash | Durable outbox/queue with proper acks |
| `@Async` + `@TransactionalEventListener(AFTER_COMMIT)` | No durable post-commit handoff | Persist outbox inside the transaction |
| Poller transaction advice wrapping HTTP handlers | DB TX spans poll + slow downstream | Separate claim TX and remote handoff |
| `SELECT FOR UPDATE` then POST before commit | Holds row locks across slow partner | Claim + lease + commit, send afterward |
| Marking `SENT` before HTTP POST | Crash loses the send | Mark after meaningful confirmation |
| Marking `SENT` immediately on producer future enqueue | Async publish can still fail | Await result/callback/ack appropriately |
| Retrying HTTP timeouts with a new UUID | Creates duplicate effects at target | Stable idempotency key, query/reconcile |
| Only lowering read timeout | Doesn't fix locks/transaction boundaries | Short TX + remote timeout + durable retries |
| Treating 400 and 503 identically | Retries invalid payloads endlessly | Classify errors, backoff, `DEAD`/`MANUAL_REVIEW` |
| Sleeping for retries inside DB TX | Pins connections/locks during sleep | Schedule next attempt after commit |
| Omitting leases/fencing for multiple workers | Workers overwrite each other's claims/states | `SKIP LOCKED` + lease tokens + conditional updates |
| Lease shorter than HTTP timeout | Second worker claims while first is still running | Deadlines/heartbeats/fencing/idempotency |
| Infinite leases | Strands jobs if workers die | Bounded leases + expiry/recovery |
| Fresh event ID per retry | Receivers cannot deduplicate | Stable business operation ID |
| Equating broker ack with business success | Ack may mean only broker receipt | Separate `PUBLISHED`/`ACCEPTED`/`COMPLETED` |
| Putting transactions on every layer "just to be safe" | Obscures actual scope, creates unintended outer TXs | Clear transaction ownership, probes, tests |
| Testing only output channels | Misses external side effects, locks, crashes | DB/broker/mock-server integration tests |
| Logging full tokens/PII in outbox logs | Data exposure and audit violations | Minimize data, encrypt/ACL, redact |

## 32. Migration Plan from Long Transactions to Short Designs

A long-running production application should never switch to an outbox in one unplanned deploy.

### 32.1. Inventory

Trace every call chain:

~~~text
HTTP/JMS/Kafka/File/SFTP inbound
  -> @Transactional service?
  -> MessageChannel (Direct/Executor/Queue)?
  -> Poller/advice?
  -> Remote adapter/gateway?
  -> DB update?
  -> Retry/error handler?
~~~

Inspect stack traces and distributed traces to determine:
- Which method actually opens/closes the transaction.
- Whether remote I/O happens before or after commit.
- Whether targets support idempotency, status queries, or cancellation.
- When inbound sources get acked/marked consumed.
- Which critical records must commit atomically (business row + outbox).

### 32.2. Design States, Versions, and Durable Intent

Specify business states, outbox schemas, unique event IDs, retries/leases, ownership, retention, and `UNKNOWN` handling. **Finalize message contracts before writing the dispatcher** so replays never emit unparseable events.

### 32.3. Controlled Phased Rollout

A migration path:

1. Deploy the outbox table and monitoring.
2. Inside the existing business transaction, insert outbox intent **without enabling the new publisher yet** to reconcile counts.
3. Enable the dispatcher for one small destination/tenant; verify idempotency and receipts.
4. Gradually move outbound calls out of the old transaction.
5. Watch duplicates, `UNKNOWN`s, pool/lock durations, retries, and backlogs.
6. Remove legacy synchronous sends once single-path ownership is verified.
7. Prepare stateful rollbacks that never drop committed outbox rows or trigger uncontrolled double sends.

**Watch out for dual-writes:** during migration, keeping the old HTTP send while running the new outbox dispatcher for the same operation doubles side effects. Enforce feature flags / single-path ownership and unique idempotency keys.

### 32.4. When Is an Outbox Unnecessary?

Outboxes add complexity. For a **read-only** request that reads DB data and calls an external service with no durability requirement, simply **end the DB transaction before the network call** and apply timeouts/bulkheads. For background tasks cheaply recomputable from an authoritative source where dropping one attempt is harmless, an in-memory queue may suffice. Decide based on **the cost of crashes/duplicates**, not pattern fashion.

## 33. Code and Pull Request Review Checklist

- [ ] No slow HTTP/SFTP/broker calls or `Future.get()/join()` inside a DB transaction after acquiring locks.
- [ ] `@Transactional` boundaries have clear owners and are never accidentally wrapped by an outer transaction.
- [ ] `REQUIRES_NEW`/`NOT_SUPPORTED` are not used to mask an outer transaction still holding resources.
- [ ] If callers invoke synchronous gateways, verified whether callers hold DB transactions while awaiting replies.
- [ ] If pollers carry transaction advice, verified advice does not span slow downstream handlers.
- [ ] If using in-memory executors/queues, crash message-loss risks are explicitly accepted or backed by durable sources.
- [ ] When reliable delivery is required, business state + outbox intent commit atomically in the same DB.
- [ ] Outbox claiming uses short transactions without holding `SELECT FOR UPDATE` across remote I/O.
- [ ] Client timeouts/deadlines align cleanly with lease durations or heartbeats.
- [ ] Workers enforce lease expiry, conditional state updates, and fencing tokens.
- [ ] Partners/consumers enforce idempotency keys or reconciliation plans for uncertain outcomes.
- [ ] `eventId`/`operationId` stays immutable across retries, while `attemptId` may vary.
- [ ] Error classification separates transient, permanent, and ambiguous outcomes.
- [ ] Retries use bounded backoff/jitter without sleeping inside transactions.
- [ ] Never marks `SENT` before receiving meaningful contractual confirmation.
- [ ] Never confuses broker acks, HTTP `202`, or output channels with business completion.
- [ ] Handles shutdown/restart, stale leases, duplicates, and cancellation races cleanly.
- [ ] Outbox/audit records exclude secrets and unnecessary PII.
- [ ] Test probes verify remote calls never execute inside active DB transactions.
- [ ] DB lock-release tests exist where contention must be proven.
- [ ] Tested crash windows, dropped remote responses, DB mark failures, and idempotent replays.
- [ ] Metrics track transaction duration, pool occupancy, backlog age, `UNKNOWN` counts, and manual reviews.
- [ ] Safe reprocess/reconciliation runbooks and operator RBAC are in place.

## 34. Scenario Q&A with Explanations

### A. "If I call HTTP inside `@Transactional`, can it roll back the HTTP call?"

**No.** Local database transaction rollbacks affect only resources participating in that transaction. An HTTP POST may already have finished on the server. Use API idempotency, status lookups, compensation, or state-managed workflows.

### B. "Is switching `DirectChannel` to `ExecutorChannel` enough?"

**Not necessarily.** Thread-bound transactions do not automatically move to executor threads, yet callers may still await gateway replies inside a transaction, or in-memory messages may be lost on crash. Evaluate durable handoffs, outer transactions, exception handling, and correctness.

### C. "Does putting `@Transactional(NOT_SUPPORTED)` on the client release row locks?"

**Not if an outer transaction hasn't committed.** The outer TX suspends while still holding locks/resources. Commit the DB before remote calls via proper call graphs, not merely changing client annotations.

### D. "A worker runs `SELECT FOR UPDATE`, calls HTTP, then commits. Since we have an outbox, is that safe?"

**No.** Row locks stay held across I/O. Outbox dispatchers must claim/lease and commit before sending, then use fencing when persisting results.

### E. "Does an HTTP response timeout mean the server didn't create the shipment?"

**No.** The server may have committed while the response dropped. Retry with an idempotency key or query outcome; when indeterminate, manage via `UNKNOWN`/manual review.

### F. "What if the worker crashes after committing the order and before sending HTTP?"

A **transactional outbox** preserves send intent in the DB for another worker to pick up. An `@Async` in-memory event would be lost.

### G. "What if the worker crashes after HTTP succeeds and before marking `SENT`?"

It may resend. The receiver must be idempotent or support reconciliation/compensation; never claim end-to-end exactly-once without matching guarantees.

### H. "Does marking `SENT` first before sending prevent duplicates?"

It reduces certain retries at the cost of **losing messages** on crashes between the two steps. Reliable architectures prefer at-least-once with deduplication.

### I. "Does a lease token stop a remote request from being sent twice?"

**No.** Tokens fence DB state transitions. The remote target may already have received a request from an older worker; pair with remote idempotency and deadline policies.

### J. "Is a transacted JMS session automatically atomic with SQL?"

**Not automatically.** Verify transaction managers and resource enlistment; otherwise a crash window remains between DB commit and broker ack. Use inbox/outbox/dedup per architecture.

### K. "Do Kafka transactions handle all HTTP side effects?"

**No.** Kafka transactions are scoped to Kafka; they do not roll back HTTP or SFTP. Use workflows and idempotency outside Kafka.

### L. "Can I add a 30-second sleep inside `@Transactional` waiting for an API to recover?"

**Never.** Sleeping extends transactions/locks and crushes throughput. Persist `next_attempt_at`, commit, and retry on a later poll.

### M. "Is a transaction probe returning `false` enough to prove the DB pool isn't pinned?"

**Not enough.** It proves no active Spring transaction on that thread, yet a suspended outer TX or locks on another thread may still exist. Test DB locks and connections under real topology and load.

### N. "Why shouldn't HTTP `202` be marked `REMOTE_COMPLETED`?"

Because `202 Accepted` usually confirms only receipt of an unfinished task. Per API contract, record `ACCEPTED`/`PUBLISHED` and track completion via callbacks, queries, or receipts.

### O. "When should you use sagas/compensation?"

When workflows span multiple systems with independent local commits and a prior step must be undone after a later failure. Compensation is a **compensating business action** that can itself fail and requires tracking—it is **not an ACID rollback** of remote side effects.

### P. "We changed transaction boundaries yet throughput didn't rise—why?"

You may have removed the DB lock bottleneck while the partner API remains the bottleneck, executors are mis-sized, the HTTP connection pool is saturated, or retries are storming. Measure every layer instead of dismissing transaction splitting just because end-to-end latency stayed unchanged.

## 35. Capstone Lab Exercise

**Prompt:** Build a mini Spring Boot + Spring Integration service receiving shipment requests, writing to a DB, and calling a partner over HTTP. Implement two versions to compare risks.

### 35.1. Version A — Anti-Pattern

~~~text
@Transactional
  update orders
  HTTP POST shipping service (fake delay 2–5s)
  update orders with receipt
COMMIT
~~~

Use a test DB and a latched fake HTTP server to observe: long-held row locks/connections, timeouts after remote side effects already occurred, and duplicates when callers retry.

### 35.2. Version B — Outbox

~~~text
TX #1:
  update orders + insert outbox PENDING
COMMIT

dispatcher:
  TX claim lease -> COMMIT
  HTTP POST idempotency-key outside DB tx
  TX mark SENT / RETRY / UNKNOWN -> COMMIT
~~~

Test scenarios: happy path, HTTP 503, timeout after commit, DB mark failure, stale leases, duplicate inputs, worker restarts, and cancellation races.

### 35.3. Acceptance Criteria

| Criterion | Evidence |
|---|---|
| DB transaction never waits on HTTP | Probe + lock/concurrency tests |
| Business + outbox atomic | Rollback test on a real database |
| Remote calls bounded by timeouts | Mock server timeouts & retry policy |
| Side effects never duplicated | Stateful test with idempotency keys |
| Worker restarts never lose jobs | Durable `PENDING`/lease expiry tests |
| Only valid owner updates state | Fencing tokens / conditional updates |
| Uncertain outcomes handled safely | `UNKNOWN` + reconciliation/manual review |
| Load stays bounded | Bounded workers + backpressure metrics |
| Auditable end-to-end | `operationId`, `attemptId`, states, receipts |
| Zero data leaks | Secret redaction and access controls |

Report results **per layer**: DB transactions, remote I/O, business outcomes, and durability. Do not compare only end-to-end latency between A and B: Version B may complete business work slightly later while freeing DB resources from remote latency and surviving failures cleanly.

## 36. References

To verify APIs, transaction semantics, and configurations per actual version:

- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Integration — Transaction Support: https://docs.spring.io/spring-integration/reference/transactions.html
- Spring Integration — Poller: https://docs.spring.io/spring-integration/reference/endpoint.html
- Spring Integration — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration — JDBC Support: https://docs.spring.io/spring-integration/reference/jdbc.html
- Spring Integration — HTTP Support: https://docs.spring.io/spring-integration/reference/http.html
- Spring for Apache Kafka Reference: https://docs.spring.io/spring-kafka/reference/
- Spring AMQP Reference: https://docs.spring.io/spring-amqp/reference/

**Version note:** Dependencies, callbacks, and DSL overloads vary across Spring Boot/Spring Integration/driver/client versions. Snippets explicitly marked *illustrative* use assumed interfaces or helpers and are not proof of compilation/execution in a module. PostgreSQL claim/lease SQL examples require separate adaptation and testing for MySQL, Oracle, or other databases.

## Conclusion

**"Avoiding holding transactions when calling slow services"** is not merely a performance trick in Spring Integration Adapters—it is a **consistent boundary-design principle**: database transactions should wrap only operations requiring local atomicity, while HTTP/SFTP/JMS/AMQP/Kafka and external I/O must be handled with mechanisms matching their independent latency and failure modes. `DirectChannel`, synchronous gateways, and poller transaction advice can inadvertently stretch transactions; `ExecutorChannel` or `@Async` can split threads without guaranteeing durable delivery. For critical data, the durable solution is usually **business state + transactional outbox in one short commit**, followed by **claim/lease → commit → remote call outside transaction → commit outcome**, backed by bounded retries, stable idempotency keys, fencing, reconciliation, and observability. Only by measuring both lock/connection hold times and target outcomes can a team prove transactions stay short **without sacrificing business correctness**.
