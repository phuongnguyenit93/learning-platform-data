# Message Receive and Transactions in Spring Integration

## 1. The Problem: What Happens When Receiving a Message and Processing Fails?

The ordering system emits a `ReserveInventory` message for the inventory service to reserve stock. The inventory service receives the message, deducts inventory in the database, and acknowledges to the sender. There are two difficult scenarios:

- The database **rolls back** after the consumer has already taken the message. Will the message be redelivered for another attempt?
- The database **commits** successfully, but the consumer crashes before sending an acknowledgement (ACK) or committing the offset. When the source redelivers the message, will inventory be deducted twice?

That is the core of **message receive and transactions**: designing the **receive** point, the **transaction start/end** point, the **ACK** point, and **reprocessing** behavior so the system can recover from failures.

Within the `SPRING_INTEGRATION_PATTERN` module, Spring Integration helps compose **Enterprise Integration Patterns (EIP)** such as Gateway, Filter, Transformer, Router, Splitter, and Aggregator using loosely coupled channels and endpoints. However, transactions do not automatically travel with messages across every thread or process. To design a reliable flow, you must inspect the **message source**, **channel type**, **execution thread**, **transaction manager**, and each adapter's **acknowledgement mechanism**.

### Lesson Objectives

After this lesson, learners can:

1. Distinguish between a **polling consumer** and a **message-driven consumer**, and know where transactions typically start.
2. Explain what happens when `receive()`, the handler, database commit, and ACK succeed or fail.
3. Identify the effects of `DirectChannel`, `ExecutorChannel`, `QueueChannel`, persistent message stores, and inbound broker adapters.
4. Place transactions on the poller or handler, control retry/redelivery, and avoid swallowing exceptions that cause improper ACKs.
5. Use an **idempotent consumer/inbox** to safely reprocess messages and test critical failure windows.

## 2. Receive Does Not Mean Processing Is Complete

A message entering an application typically goes through these stages:

~~~mermaid
flowchart LR
    A["Source: broker / queue / DB"] --> B["Inbound adapter or poller"]
    B --> C["MessageChannel"]
    C --> D["Filter / Transformer / Router"]
    D --> E["Business handler"]
    E --> F[("Business DB")]
    B -. "ACK / offset / source transaction" .-> A
~~~

These milestones have distinct semantics:

| Milestone | Interpretation | What is guaranteed? |
| --- | --- | --- |
| **Receive** | Consumer receives or pulls the message from the source. | The message may not yet have been processed by business logic; some sources support returning it on error, others do not. |
| **Dispatch** | Adapter forwards the message into the Spring Integration flow. | With async channels, downstream work may still be running. |
| **Business commit** | The business DB transaction commits successfully. | Does not automatically ACK to the broker or commit offsets. |
| **ACK / offset commit** | Source marks delivery as received or progress as confirmed. | Does not prove updates on another DB definitely succeeded. |
| **Redelivery** | Source resends the message or consumer reads it again. | Does not guarantee this is the first processing attempt; deduplication design is needed. |

**ACK timing is a reliability decision.** If you ACK first and then update the DB, the process can crash and lose work. If you commit the DB before ACK, the process can crash in between and the message is redelivered. The common choice for critical systems is to accept **at-least-once delivery** while making business processing **idempotent**.

### Where Do You Receive From?

Spring Integration has two main types of receiving endpoints:

- **Polling endpoint**: a poller periodically invokes `MessageSource.receive()` or `PollableChannel.receive()`. Examples: reading queues, JDBC-backed stores, files, or any polling-capable source.
- **Message-driven endpoint**: the source actively pushes messages to the handler via a listener or callback, e.g. JMS/AMQP/Kafka depending on the adapter. ACK points, transactions, and retries are heavily influenced by the listener container and broker.

A `SubscribableChannel` like `DirectChannel` usually dispatches when a message is sent to the channel; a `PollableChannel` like `QueueChannel` lets consumers call `receive()`. **Not all channels share the same API or rollback properties.**

## 3. Four Boundaries to Draw Before Writing Code

In a message-receiving flow, separate:

1. **Receive boundary**: which source determines whether the message remains available to receive again or has been removed from the source?
2. **Execution boundary**: does the handler run on the same thread as the listener/poller, or is it handed off to another executor?
3. **Transaction boundary**: who opens the transaction, which resources participate, and which steps actually run before commit/rollback?
4. **Acknowledgement boundary**: when does the source consider delivery complete, and when will it redeliver?

### Synchronous Flow with One Consumer Transaction

~~~mermaid
sequenceDiagram
    participant Source as Message source
    participant Poller as Poller / Listener
    participant Flow as DirectChannel + Handler
    participant DB as Business DB
    Source-->>Poller: Deliver message
    Note over Poller,DB: Synchronous processing boundary
    Poller->>Flow: Dispatch
    Flow->>DB: BEGIN + UPDATE
    DB-->>Flow: COMMIT OK
    Flow-->>Poller: Complete
    Poller-->>Source: ACK / commit source transaction
    Note over Source,DB: ACK may be a separate step, non-atomic with DB
~~~

This diagram shows **a desired processing policy**, not a claim that every adapter automatically ACKs after DB commit. Brokers may manage ACK inside the listener container; some configurations use auto-ack; Kafka offset commit timing and JMS transactions differ. Always check the actual mechanism.

### When an Asynchronous Thread Is Present

~~~mermaid
flowchart LR
    subgraph T1["Thread A — listener/poller"]
      A["Receive"] --> B["ExecutorChannel.send()"]
      B --> C["Listener may finish / ACK"]
    end
    B -. "handoff" .-> D["Worker thread B"]
    subgraph T2["Separate transaction if opened"]
      D --> E["Business handler"]
      E --> F[("DB")]
    end
~~~

With `ExecutorChannel`, the listener/poller's thread-bound transaction **is not automatically propagated** to the worker. If the listener completes and ACKs upon handing off to the executor, a subsequent error in the worker may not cause the source to redeliver the message. To assess this, examine the channel, executor, container, and error handler together.

## 4. How Transactions Behave by Receiving Source Type

| Source or channel | When handler fails | What to inspect to predict redelivery |
| --- | --- | --- |
| In-memory `QueueChannel` | DB transaction may roll back. | Dequeuing from an in-memory queue is usually not part of the JDBC transaction; the message does not return automatically just because DB rolled back, and may be lost on crash. |
| `QueueChannel` with **persistent MessageStore** | Can coordinate queue operations with the store's transaction. | Store configuration, transaction support, group ID, datasource, and transaction manager; whether fetching/deleting the message truly shares the DB transaction. |
| JDBC/SQL polling source | DB operation can roll back if the source participates in the transaction. | Row claiming, locking, checkpointing, when processed status is updated, isolation, and multiple concurrent pollers. |
| JMS message-driven inbound | A transacted JMS session can roll back consumption on JMS and trigger redelivery. | `sessionTransacted`, listener container, error propagation, session type, and transaction manager. Whether JDBC shares a global transaction is a separate question. |
| AMQP/RabbitMQ inbound | Broker can redeliver when delivery is rejected/nacked or connection drops before ACK. | ACK mode, listener container, requeue, prefetch, DLQ, and broker/DB transactions. |
| Kafka inbound | Message is re-read if the corresponding offset has not been committed. | Ack mode, offset commit, partitions, rebalance, retry/error handler, producer transactions, and consumer group. |
| HTTP inbound gateway/webhook | Request is received over HTTP. | Response status, timeout, client retries; there is no remote request rollback like a JDBC transaction. |
| File poller | Can see files or move files across poll cycles. | Accept-once filter, rename/move, metadata store, checkpoints, restarts, and filesystem durability. |

The common rule is: **a handler's transaction only protects resources that actually participate**. For example, using `@Transactional` for PostgreSQL does not automatically turn RabbitMQ ACKs, Kafka offsets, or HTTP calls into part of the PostgreSQL transaction.

### A Case to Remember

A consumer receives `ReserveInventory(eventId = E-17)`:

1. The handler writes the inventory change and the DB commits.
2. The consumer crashes **before** acknowledging delivery.
3. The broker redelivers `E-17`.

**Redelivery in this scenario is expected.** The system must recognize that `E-17` was already processed and avoid deducting stock a second time; you cannot rely solely on transaction rollback.

## 5. Transactional Poller in Spring Integration

In a polling flow, one way to open a transaction is placing transaction advice on the **poller**. The following Java DSL example shows boundary placement (assuming `workQueue` and a `PlatformTransactionManager` for the business DB are configured):

~~~java
@Configuration
@EnableIntegration
class PollingFlowConfig {

    @Bean
    QueueChannel workQueue() {
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow orderWorker(
            PlatformTransactionManager transactionManager,
            InventoryHandler inventoryHandler) {
        return IntegrationFlow.from(
                        "workQueue",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(1_000)
                                        .maxMessagesPerPoll(1)
                                        .transactional(transactionManager)))
                .handle(inventoryHandler, "reserve")
                .get();
    }
}
~~~

**Execution flow:**

1. The poller fires on schedule and starts a transaction per configuration.
2. The poller retrieves at most one message from `workQueue` per poll.
3. If the endpoint continues synchronous processing through a JDBC handler, eligible DB operations can join that transaction.
4. If the handler finishes, the transaction commits; if an exception matching rollback rules escapes through the advice, the transaction rolls back.

`maxMessagesPerPoll(1)` helps observe individual units of work; it does not change the durability of the queue itself.

**Warning about this example:** `QueueChannel(100)` is an **in-memory** queue. If the poller removes the message and the handler then fails, JDBC rollback does not mean the queue dequeue is reversed. Avoid using this example to claim durable redelivery or message recovery across application restarts.

### When Durable Message Reception Is Needed

Replace the in-memory source with one that has well-defined storage and recovery mechanics:

- **Persistent channel/message store**: evaluate how messages are fetched/deleted within a transaction and whether it can share a transaction manager with the business database.
- **Broker**: use a listener container or adapter supporting ACK/redelivery; configure error handling so the broker redelivers, while enforcing idempotency.
- **Database polling**: use durable row status or claim tokens to avoid multiple workers grabbing the same row; include a reclaim strategy when workers die.

You cannot conclude “a poller with `transactional()` automatically puts the message back” without knowing whether the **message source** participates in the transaction.

## 6. How Is a Handler Transaction Different from a Poller Transaction?

Placing `@Transactional` on a business-processing Spring service can also protect the DB:

~~~java
@Service
class SimpleInventoryHandler {
    private final JdbcTemplate jdbc;

    SimpleInventoryHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(ReserveInventory command) {
        jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """, command.quantity(), command.sku(), command.quantity());
    }
}
~~~

Assume `ReserveInventory` is the incoming message payload type. With this handler, the Spring transaction interceptor can wrap the JDBC operation when the integration endpoint invokes it through the Spring bean proxy.

The two transaction placements have different scopes:

| Boundary placed at | Typical scope | Limitations |
| --- | --- | --- |
| **Poller** with `.transactional(manager)` | Can wrap one poll cycle and synchronous downstream steps. | Does not automatically make an in-memory queue transactional; async boundaries escape the transaction scope. |
| **Handler** with `@Transactional` | Wraps the business processing method. | Receive/ACK operations outside the method do not automatically join; if the caller swallows exceptions, the source may ACK. |
| **Listener container** with broker transaction | Wraps receive/processing per adapter or broker mechanics. | Does not automatically unify the broker transaction with a separate database transaction. |

In many systems, **the handler transaction and source ACK mechanism coordinate in order**, yet remain two independent resources. The design must handle the case where the DB commits but ACK fails.

### Placing Transactions on Services Invoked via Spring Proxy

If a `@Transactional` method is invoked via `this.reserve(...)` inside the same bean under standard Spring proxy mechanics, the advice may not run. Likewise, if the handler directly uses connections outside the transaction manager, the method annotation does not merge those resources into one shared transaction.

To be certain, test the DB state after handler failures rather than only checking for annotations in source code.

## 7. Message-Driven: ACK, Session Transactions, and Rollback

With broker-driven listeners, messages are normally delivered via a container/adapter to run the downstream flow. The sequence must be understood per **specific broker and adapter**.

### JMS: Transacted Sessions

A JMS listener container can be configured with `sessionTransacted = true`. Receiving the message then participates in a **JMS local transaction**: if the listener finishes successfully, the JMS session commits; if an appropriate error escapes, the session rolls back and the message can be redelivered by the broker.

Conceptual configuration outline:

~~~text
JMS queue "orders.reserve"
  -> JMS message-driven inbound adapter
  -> DirectChannel (synchronous processing)
  -> InventoryHandler.reserve(...)

JMS listener container:
  sessionTransacted = true
  error propagation  = preserve error so container can roll back

Business DB:
  uses corresponding PlatformTransactionManager
  handler updates DB in its own transaction if needed
~~~

**Distinguish the two transactions:** the JMS local transaction for consuming and the JDBC transaction for business work **do not automatically commit atomically together**. The DB can commit while the JMS session rolls back, causing redelivery. If the system requires cross-resource atomicity, you must evaluate XA/JTA capabilities, JDBC driver, JMS provider, and operational cost; do not infer it from `sessionTransacted = true`.

Do not insert an `ExecutorChannel` right after the adapter just to increase throughput without verifying ACK semantics: when the container only sees a successful dispatch to the executor, subsequent business errors may not affect the listener's JMS transaction.

### AMQP/RabbitMQ: ACK and Requeue

In RabbitMQ, the listener container determines when to ACK, reject/nack, and whether to requeue. An exception can trigger redelivery, routing to a DLQ, or consumption by an error handler depending on configuration. Verify:

- Container acknowledgement mode (container-managed, manual, or other adapter-supported modes).
- Consumer prefetch and multiple unacknowledged deliveries in flight.
- Whether errors propagate back to the listener or are handled by an error flow and treated as success.
- Requeue policy, retry limits, and dead-letter exchange/queue.

Using RabbitMQ transactions and a separate JDBC transaction does not automatically create a two-phase transaction. Redelivery after failure must still be safe for messages that previously updated the DB.

### Kafka: Offset Commit and Processing Transactions

Kafka tracks consumption progress via **offsets**. A consumer that has updated the DB without committing its offset may re-read the message after a crash or rebalance. Conversely, committing the offset before safe processing can prevent a message from being reprocessed even though the DB was not updated.

Kafka supports transactions for certain **consume-from-Kafka and produce-to-Kafka** scenarios, coordinating offsets within the Kafka transaction under appropriate producer/consumer settings. That **does not automatically place an external JDBC database into the same atomic transaction**. For DB side effects, you still need an idempotent consumer/inbox or a verified coordination mechanism.

### HTTP Webhooks: The Response Is the Completion Signal

An inbound HTTP gateway receives a request and returns a status. If a `2xx` response is sent **before async work truly finishes**, the client may consider the request successful and not retry. For critical webhooks, consider persisting a **durable inbox/command** before returning `2xx`; without durable storage, a crash can lose accepted work.

## 8. Building an Idempotent Consumer with an Inbox

To safely handle the scenario where **the DB commits but the source redelivers the message**, create a table storing processed `eventId`s. The example below uses PostgreSQL syntax and assumes each delivery has a stable business `eventId`:

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(80) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);

CREATE TABLE processed_messages (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Flow payload:

~~~java
record ReserveInventory(
        String eventId,
        String orderId,
        String sku,
        int quantity) {}
~~~

The handler processes the message as follows:

~~~java
@Service
class InventoryHandler {
    private final JdbcTemplate jdbc;

    InventoryHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(ReserveInventory command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        // PostgreSQL: an existing record with identical eventId is a duplicate delivery.
        int inserted = jdbc.update("""
                INSERT INTO processed_messages (event_id)
                VALUES (?)
                ON CONFLICT (event_id) DO NOTHING
                """, command.eventId());

        if (inserted == 0) {
            // Event was already committed in a prior processing attempt.
            return;
        }

        int updated = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """,
                command.quantity(),
                command.sku(),
                command.quantity());

        if (updated != 1) {
            throw new IllegalStateException(
                    "Unable to reserve inventory for " + command.sku());
        }
    }
}
~~~

**Why is inserting into `processed_messages` first safe?** Both the `INSERT` and `UPDATE inventory` execute **within the same DB transaction**. If inventory is insufficient, the exception escapes the method and the transaction rolls back **both the processed marker and the inventory change**. If everything commits, redelivery sees the same `eventId` and skips a second update.

This design avoids the naive `SELECT` then `INSERT` pattern prone to **race conditions** when two workers process the same `eventId`. The `PRIMARY KEY` constraint enforces uniqueness; `ON CONFLICT DO NOTHING` is PostgreSQL syntax and must be adapted for other databases. Under concurrent transactions, the unique index and database locking/isolation mechanics govern how the second transaction waits or resolves conflicts.

### Conditions for Correct Idempotency

1. `eventId` must remain **stable across retries and redeliveries** of the same event. Never generate a fresh UUID on each receive.
2. Define uniqueness scope: if multiple independent business consumers share the same deduplication store, the key may need to be `(consumer_name, event_id)` rather than just `event_id`.
3. Recording the processed marker and updating business state must share **the same DB transaction**. If across two separate non-transactional DBs, another solution is required.
4. The handler must not perform remote side effects **before** transaction completion if you assume rollback will undo everything. For email/HTTP, use an outbox/compensation or downstream idempotency.
5. Even when a duplicate is detected, the consumer must still complete delivery handling according to the adapter's ACK policy.

### Combining Inbox with Outbox

If processing an incoming message also needs to emit a new message, a common pattern is:

~~~text
Receive OrderPaid(eventId)
   -> begin DB transaction
        insert processed_messages(eventId) if absent
        update orders / inventory
        insert outbox_events(newEventId, payload)
      commit DB transaction
   -> acknowledge input delivery

Outbox relay
   -> publish outbox event
   -> mark sent (may retry and publish duplicates)
~~~

The inbox prevents duplicate processing **on input**. The outbox ensures the intent to emit a new event is durably stored **alongside business data**. Combining both patterns helps services communicate loosely while still requiring redelivery handling and backlog monitoring.

## 9. Where Exceptions Go Determines Retry and Rollback

A flow can throw errors in a Filter, Transformer, Router, Service Activator, handler, or Aggregator. You need to know what ultimately catches the error:

| Situation | How might transaction / ACK react? |
| --- | --- |
| Synchronous handler throws `RuntimeException` and it reaches the transaction interceptor. | DB transaction usually rolls back according to rollback rules. |
| Listener/poller receives exception and source config enables redelivery on error. | Source may redeliver, with backoff/requeue depending on configuration. |
| Handler catches exception, logs only, and returns normally. | Transaction may commit and container may ACK, even though business logic failed. |
| Exception is turned into an `ErrorMessage` and handled by an error flow. | Do not assume transaction rollback; verify the final outcome observed by transaction advice/container. |
| Async handler fails after adapter already acknowledged the source. | Failure may no longer affect the initial ACK; retry/durable queue is needed on the worker side. |
| A malformed message is repeatedly redelivered. | Bounded retries, DLQ/quarantine, and poison message handling are needed. |

### Never Swallow Errors That Require Rollback

~~~java
@Transactional
public void handleBadly(ReserveInventory command) {
    try {
        inventoryHandler.reserve(command);
    } catch (RuntimeException ex) {
        log.warn("Failed to reserve {}", command.orderId(), ex);
        // Call returns normally: callers may treat it as success.
    }
}
~~~

If you want rollback and source redelivery, ensure the error **propagates to the right boundary**. Still, do not add `throw` blindly: distinguish transient from permanent errors, decide where retries belong, and determine when messages go to the DLQ. In some cases a transaction is already marked `rollback-only` by a failed inner method; test the full transaction advice chain.

### Retry and Transaction Ordering Must Be Consistent

Consider two models:

~~~text
Model 1:
retry whole operation
  -> open NEW transaction per attempt
     -> process message
     -> commit/rollback

Model 2:
open transaction ONCE
  -> retry handler repeatedly inside same transaction
  -> commit/rollback
~~~

These two models **are different**. If the first attempt marks the transaction `rollback-only` or hits a connection/SQL error, retrying inside that same transaction may keep failing or fail to commit. When retrying the full unit of work, you usually want a **new transaction per attempt** (depending on the broker adapter, retry advice, and interceptor order).

Practical policies:

- Transient errors: bounded retries, backoff, with jitter where appropriate.
- Unrecoverable errors: record the clear root cause and route to DLQ/quarantine.
- Errors where prior completion is uncertain: keep the same `eventId` and process idempotently.
- After repeated failures: provide tooling to inspect, fix data, and **replay** messages safely.

## 10. Combining Receive with Router, Filter, Splitter, and Aggregator

After an inbound adapter, a message may traverse multiple patterns:

~~~mermaid
flowchart LR
    A["Inbound adapter"] --> B["DirectChannel"]
    B --> C["Transformer"]
    C --> D{"Router"}
    D --> E["Filter"]
    D --> F["Splitter"]
    E --> G["Handler A"]
    F --> H["ExecutorChannel / workers"]
    H --> I["Aggregator by orderId"]
    G --> I
~~~

- **Transformer** can fail converting the payload. If it happens inside a synchronous listener, the error can trigger source rollback; if consumed by an error flow, the outcome differs.
- **Filter** dropping a message is usually a **valid outcome** per filtering policy. If the consumer ACKs after the Filter drops the message, it will not be redelivered automatically. If dropping is a business error, define an explicit error path.
- **Router** selects the destination. A synchronous branch may remain in the current transaction; an async branch creates a different execution boundary.
- **Splitter** produces multiple child messages. A single source transaction **does not automatically cover** branches dispatched to multiple threads or processes.
- **Aggregator** collects messages via `correlationId`, sequence/release strategies, and a message store. If state recovery across restarts is needed, consider a persistent store, timeouts, duplicates, and partial completion.
- **Gateway** supports request intake or request-reply per contract. In an async flow, the initial response may only indicate task acceptance, not that all branches committed.

For example, an `OrderConfirmed` message is split by a Splitter into `ReserveInventory` and `ChargePayment`. If payment commits in one service while inventory fails in another, rolling back the initial consumer's transaction **cannot undo** the payment. The process needs compensation/Saga mechanisms or per-step tracking state, along with branch correlation and idempotency.

### Correlation Is Not a Transaction

Metadata like `orderId`, `correlationId`, `sequenceNumber`, and `eventId` is great for routing, aggregation, and tracing. Yet no header automatically carries a JDBC transaction or synchronizes ACKs across brokers. **Correlation is for tracking/semantics; transactions control resource state changes.**

## 11. Reliability Matrix: ACK Timing vs. Commit Timing

| Ordering | Failure window | Risk | Mitigation |
| --- | --- | --- | --- |
| **ACK first, then commit DB** | App crashes after ACK, before commit. | Message is not redelivered yet data is unupdated: **lost processing**. | Avoid premature ACK; use a durable source, ACK after commit, or persist to a durable inbox. |
| **Commit DB then ACK** | App crashes after commit, before ACK. | Message is redelivered, risking **duplicate processing**. | Idempotent consumer and unique constraint on `eventId`. |
| **DB rolls back and broker receives error** | Handler throws, listener returns failure. | Repeated retries, possible blocking by poison messages. | Retry/backoff/DLQ, classify permanent failures. |
| **DB rolls back but error is swallowed** | Handler returns normally. | Broker ACKs even though business logic failed. | Never swallow errors needing rollback; test error channel and container. |
| **Dispatch to worker before ACK** | Listener already ACKed, worker fails later. | No durable source to retry if task exists only in executor. | Durable queue/inbox; ACK after durable persistence or keep processing sync when appropriate. |
| **Transactional source + business DB under one valid transaction manager** | One operation in the transaction fails. | Participating changes can roll back together. | Verify store type, datasource, manager, and run crash/recovery tests. |

Do not claim **end-to-end exactly-once** solely because Kafka transactions, JDBC transactions, or JMS transacted sessions are present. Each technology has a specific **guarantee scope**; multi-system operations still require analyzing duplicates, crashes, and ambiguous confirmations.

## 12. Testing Receive and Transactions via Failure Injection

Good hands-on testing verifies **persisted outcomes** and **source behavior** after failure, not merely that a handler was invoked.

### Testing DB Idempotency

With `InventoryHandler.reserve` from section 8 and initial test data `inventory("SKU-1", available=10)`, an integration test can look like:

~~~java
@SpringBootTest
class InventoryReceiveIT {
    @Autowired InventoryHandler handler;
    @Autowired JdbcTemplate jdbc;

    @Test
    void duplicateEventChangesStockOnlyOnce() {
        String eventId = UUID.randomUUID().toString();
        ReserveInventory event = new ReserveInventory(
                eventId, "ORDER-1", "SKU-1", 3);

        handler.reserve(event);
        handler.reserve(event); // Simulate redelivery with the same eventId.

        Integer available = jdbc.queryForObject(
                "SELECT available FROM inventory WHERE sku = ?",
                Integer.class, "SKU-1");
        assertEquals(7, available);

        Integer applied = jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_messages WHERE event_id = ?",
                Integer.class, eventId);
        assertEquals(1, applied);
    }

    @Test
    void invalidReservationRollsBackProcessedMarker() {
        String eventId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> handler.reserve(new ReserveInventory(
                        eventId, "ORDER-2", "SKU-1", 1000)));

        Integer processed = jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_messages WHERE event_id = ?",
                Integer.class, eventId);
        assertEquals(0, processed);
    }
}
~~~

The example assumes schema and seed test data are created; each test should run on isolated data or reset state properly. When testing application commit/rollback, avoid annotating the test itself with `@Transactional`, which masks the handler's transaction. For duplicate tests, keep the **same eventId** across both calls.

### Testing Against a Real Broker

| Scenario | Observations to collect |
| --- | --- |
| Handler throws exception before DB commit | Did DB roll back? Did broker/adapter redeliver or move to DLQ as configured? |
| Handler commits DB, then connection/consumer drops before ACK | Does redelivery occur? Does DB avoid duplicate processing? |
| Consumer rebalances (Kafka) | Do offsets and partition processing resume accurately? |
| Listener pushes to `ExecutorChannel` and worker fails | Has the consumer already ACKed? Which error channel receives the error? |
| DB temporarily unavailable | Are retry/backoff bounded without causing a request storm or blocking queues indefinitely? |
| Malformed schema message | Does it go to DLQ/quarantine with full reason, avoiding a poison loop? |
| Two deliveries with same `eventId` run concurrently | Do unique constraint and transaction enforce only one update? |
| Application restarts with messages in an in-memory queue | Are messages lost? Should you switch to a durable source? |

At the integration test level, use a real test-environment broker or corresponding Testcontainers; results depend on specific configuration. Collect **DB state**, **delivery counts**, **ACK/offset**, **DLQ**, and **processed events**.

## 13. Operational Observability and Recovery

### Logging and Tracing

At message reception and processing completion, track:

- Stable `eventId` to detect duplicates.
- `orderId`/`correlationId` to link processing branches and Aggregators.
- Channel/endpoint name, consumer group/queue, partition–offset or delivery tag per broker.
- Processing outcome (`committed`, `rolled_back`, `duplicate_skipped`), attempt count, exception type.
- Acknowledgement status (`ACK`, `NACK`, `offset_commit`) when observable via the adapter.

Never log payloads containing sensitive information. Never treat a `"received"` log line as proof that processing finished.

### Key Metrics

| Metric | Signal requiring investigation |
| --- | --- |
| Consumer lag / queue depth | Slow or stalled consumer, growing backlog. |
| Redelivery count | Frequent transient errors or failed ACKs. |
| Duplicate detection count | Messages being replayed; abnormal spikes warrant checking producer/ACK. |
| Handler error rate and retry rate | Schema errors, DB issues, downstream dependency failures, or poison messages. |
| DLQ size / age | Unresolved work requiring intervention. |
| End-to-end latency | Time from event creation until business DB commit. |
| Stuck processing/lease age | Mid-flight worker crash or claiming mechanism failing to reclaim properly. |

**Recovery:** provide tooling to inspect a failed message, fix source data or configuration, perform controlled replay, and verify idempotency. If pending/in-progress states are persisted in a database, define a reclaim policy for missing heartbeats or expired leases.

## 14. Choosing the Right Design

| Requirement | Suggested design | What must be verified |
| --- | --- | --- |
| Local processing, no durability across restarts needed | In-memory `QueueChannel` and poller. | Accept message loss on crash; do not assume dequeue rollback. |
| Pulling work from a durable JDBC source | Transactional poller + persistent store/claim logic in the same DB. | Isolation, locking, transaction manager, reclaim, and multiple workers. |
| Receiving from JMS requiring redelivery | Message-driven adapter and listener container with appropriate session/transaction. | Exception propagation, JMS rollback/commit, separate DB transaction, DLQ. |
| Receiving from RabbitMQ | Inbound adapter with configured ACK/requeue/DLQ, idempotent handler. | ACK mode, broker confirms, prefetch, transient/permanent errors. |
| Receiving from Kafka and writing to a database | Consumer + DB transaction, idempotency by `eventId`, proper offset management. | Crash between DB commit and offset commit, rebalance, duplicates, and DLQ. |
| Webhook needing fast response | Save message/command into durable inbox then return HTTP response; worker processes in background. | Only return success after durable write; request retry/idempotency. |
| Multi-service branching workflow | Each consumer manages its own transaction + inbox/outbox; correlation/Saga tracking. | Retries, timeouts, compensation, and durable Aggregator state. |

Short per-consumer transactions are typically easier to recover than long transactions spanning network calls. In distributed EIP, business-level “exactly once” is generally achieved through **repeatable delivery + idempotent processing**, rather than expecting one local transaction to span the whole system.

## 15. Hands-On Exercises

**Exercise 1 — Identify boundaries.** Given `JMS listener → DirectChannel → Filter → Transformer → Service Activator JDBC`, draw the JMS session boundary and DB transaction boundary. Then replace `DirectChannel` with `ExecutorChannel` and explain why ACKing right after dispatch can neutralize rollback on downstream failures.

**Exercise 2 — Receiving from an in-memory queue.** Use the transactional poller from section 5. When the handler throws an error, inspect DB rollback and count remaining messages in the queue. Contrast the actual outcome with the false expectation that JDBC rollback automatically returns the dequeued item.

**Exercise 3 — Processing twice without deducting inventory twice.** Create `inventory` and `processed_messages`, and send the same `ReserveInventory(eventId)` twice. Verify inventory decreases only once; test two concurrent consumers with the same `eventId` to prove the unique constraint.

**Exercise 4 — Crash between DB commit and ACK.** Using a test broker, have the consumer commit the DB and then sever the connection before ACK. Observe redelivery and confirm the idempotent handler returns safely.

**Exercise 5 — Fault-tolerant Splitter/Aggregator.** Split an order into child messages by `correlationId`, process across multiple workers, and store results in an Aggregator with a persistent store. Inject a fault into one worker and verify retries, timeouts, and distinguishing late/duplicate messages.

### Self-Assessment Questions

**1. Does a transactional poller guarantee a message returns to an in-memory `QueueChannel` on DB rollback?** No. JDBC rollback only affects resources participating in the transaction; in-memory dequeuing and queue durability are separate concerns.

**2. Why can redelivery still happen after the DB has committed?** The consumer may crash or lose connection before ACK/offset commit, so the source does not know processing succeeded.

**3. Does `@Transactional` on a handler include Kafka/RabbitMQ ACKs?** Not by default. It manages resources of the corresponding transaction manager; ACK/offset is managed by the broker adapter/container.

**4. Why shouldn't you swallow exceptions in a consumer?** The listener/poller may treat the call as successful and ACK, even though the DB rolled back or business logic did not finish.

**5. What does an inbox solve?** It records processed `eventId`s in the same transaction as business updates so redeliveries do not execute duplicate side effects.

## 16. Pre-Production Checklist for Consumers

- [ ] Identify the message source and its receive, ACK/offset, redelivery, and restart mechanics.
- [ ] Explicitly specify where transactions start: poller, listener container, handler, or service.
- [ ] Check whether execution stays on the same thread or hands off to an executor/broker before ACK.
- [ ] Verify which resources truly participate in the transaction and the commit order.
- [ ] Never rely on an in-memory `QueueChannel` for durable redelivery.
- [ ] Design a stable `eventId`, deduplication/inbox table, or idempotent update.
- [ ] Ensure marking as processed and updating business data occur in the same appropriate transaction.
- [ ] Propagate rollback-triggering exceptions to the right interceptor/container; check the error channel.
- [ ] Configure bounded retries, backoff, DLQ, replay tooling, and poison message handling.
- [ ] Test at least three failure points: before DB commit, after DB commit/before ACK, and after ACK.
- [ ] Monitor lag, redeliveries, duplicates, DLQ, correlation, and end-to-end latency.
- [ ] For multi-branch flows, define boundaries, timeouts, and compensation per branch.

**Takeaway:** Receiving a message is only **the input to a unit of work**. In Spring Integration, consumer reliability depends on **resource transactions**, **error handling**, and **when the source confirms delivery**. Proactively design redelivery and idempotency so a message received multiple times still produces the exact desired business outcome.
