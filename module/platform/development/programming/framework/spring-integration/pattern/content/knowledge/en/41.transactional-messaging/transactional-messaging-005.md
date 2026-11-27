# Commit, Rollback, and Redelivery in Spring Integration

## 1. The Most Important Question: What Happens When Processing Fails After Receiving a Message?

A sales system sends an `OrderPaid` event to the inventory service. The consumer receives the message, deducts inventory, and then informs the source that the message has been processed. The network or process can fail at any step:

1. The message reaches the listener before the handler has run.
2. The handler starts a transaction and updates the database.
3. The database **commits**, but the listener has not yet sent an ACK or committed the offset.
4. The broker decides to redeliver the message because the previous processing attempt was not confirmed.

If the consumer treats the second delivery as a brand-new order, one event can deduct inventory twice. Conversely, if the consumer ACKs too early and the database then rolls back, work can be **lost** because the source thinks the message is done.

**Commit, rollback, and redelivery** must be designed together:

- **Commit** confirms the changes of *a specific transaction* on participating resources.
- **Rollback** undoes *uncommitted* changes belonging to that transaction; it does not automatically retract side effects in external systems.
- **Redelivery** is when a source gives a message to a consumer again, typically after an error, timeout, disconnection, or unconfirmed progress.

In the `SPRING_INTEGRATION_PATTERN` module, Spring Integration lets you compose Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation into loosely coupled flows. However, messages passing through those patterns **do not automatically carry a single transaction across threads, processes, and brokers**. This lesson helps you place transaction boundaries, ACKs, retries, and idempotency in the right places so a redelivered message still yields the exact right business outcome.

### Expected Outcomes

After this lesson, you can:

1. Accurately draw the boundaries of **DB transactions**, **message source/broker transactions**, and **ACK/offsets**.
2. Distinguish between JDBC rollback, JMS session rollback, RabbitMQ requeue, and Kafka offset replay.
3. Predict consequences when a message fails before commit, after commit but before ACK, or after ACK.
4. Configure synchronous flows / transactional pollers in sensible positions without mistaking an in-memory queue for a durable source.
5. Build idempotent consumers with stable event keys and test retry/redelivery using failure injection.

## 2. Three Boundaries to Distinguish

### Transaction Boundary

A transaction manages a set of resource-supported operations, such as SQL statements using the same `DataSource` and transaction manager. Spring typically starts/ends transactions via `@Transactional`, `TransactionTemplate`, transaction interceptors, or polling endpoint advice.

In the common imperative transaction model, transaction context is bound to the **executing thread**. If downstream execution runs through `DirectChannel` on the same thread, the handler can join the open transaction. If `ExecutorChannel` is used, tasks typically move to another thread; the original transaction does not follow automatically.

### Delivery Boundary

A message may be received from:

- an in-memory `QueueChannel`;
- a persistent channel/message store in a database;
- JMS, RabbitMQ/AMQP, or Kafka;
- a file, HTTP webhook, or another `MessageSource`.

Each source has its own mechanism determining whether a message remains available to receive again, has been removed from the queue, is awaiting ACK, or has an offset marked. You cannot apply one source's rollback rules to all other sources.

### Acknowledgement Boundary

An ACK, JMS session commit, or Kafka offset commit signals progress *at the message source*. A DB commit is the outcome *at the business resource*. These two actions can happen at different times.

| Event | What does it indicate? | What does it NOT prove on its own? |
| --- | --- | --- |
| `receive()` returns a message | Consumer pulled/received a message. | That the handler finished processing or data committed. |
| `MessageChannel.send()` succeeds | Channel accepted the message per its contract. | That all async workers finished processing. |
| JDBC `COMMIT` succeeds | Participating JDBC changes committed. | That the broker ACKed or another consumer received the event. |
| JMS session commit | JMS operations participating in the JMS session transaction committed. | That a separate database committed atomically with it. |
| RabbitMQ ACK | Delivery is confirmed per broker mechanics. | That an independent business DB committed. |
| Kafka offset commit | Consumer group's offset progress was recorded. | That side effects on an external DB definitely committed. |
| Redelivery | Message/record is delivered again for processing. | That the previous attempt definitely produced no side effects. |

**Rule:** When reading a flow, you must be able to answer “which resources get rolled back?”, “who decides redelivery?”, and “where is the actual acknowledgement point?”.

## 3. State Machine of a Received Message

~~~mermaid
flowchart TD
    A["Available at source"] --> B["Delivered / In-flight"]
    B --> C["Consumer runs business logic"]
    C --> D{"Business DB commit succeeds?"}
    D -->|"Yes"| E["Committed business effect"]
    D -->|"No"| F["Business rollback"]
    E --> G{"Source receives ACK / offset commit?"}
    G -->|"Yes"| H["Delivery complete"]
    G -->|"No / disconnected"| I["Source may redeliver"]
    F --> J{"Source policy"}
    J -->|"Retry / requeue"| I
    J -->|"Reject / DLQ"| K["Quarantine / dead letter"]
    I --> B
~~~

The diagram depicts an **operational pattern**. How each broker defines in-flight, ACK, reject, requeue, retry, and dead-letter behavior depends on the adapter/container/configuration. For sources that do not support redelivery (such as a pure in-memory queue), the retry branch **does not exist automatically**.

### At-Most-Once, At-Least-Once, and Exactly-Once

| Strategy | Characteristics | Risks to accept |
| --- | --- | --- |
| **At-most-once** | May not reprocess after failure; typically uses early confirmation or non-durable sources. | Lost work when failure occurs after the source considers the message handled. |
| **At-least-once** | Capable of redelivering unconfirmed messages. | A message may be processed **multiple times**; requires idempotency. |
| **Exactly-once within a specific scope** | Some systems support transactions/deduplication within a defined resource scope. | Does not automatically guarantee **end-to-end exactly-once** across Kafka/JMS, another database, and external APIs. |

In real-world systems, the **at-least-once delivery + idempotent business processing** model is usually easier to verify than an exactly-once promise spanning multiple independent systems.

## 4. Timeline of Three Critical Failure Windows

### Scenario A — Rollback Before DB Commit

~~~mermaid
sequenceDiagram
    participant S as Source/Broker
    participant C as Consumer
    participant DB as Business DB
    S->>C: Deliver(eventId=E-17)
    C->>DB: BEGIN + UPDATE inventory
    DB-->>C: SQL / business rule error
    C->>DB: ROLLBACK
    Note over S,C: Error propagates to source adapter
    C-->>S: Reject / rollback source transaction
    S->>C: May redeliver per policy
~~~

If JDBC rollback succeeds, uncommitted changes in that transaction are undone. **Whether the message is redelivered** depends on the source: the source must still hold the message/offset and have a redelivery policy on error.

### Scenario B — DB Commits, Then Consumer Crashes Before ACK

~~~mermaid
sequenceDiagram
    participant S as Source/Broker
    participant C as Consumer
    participant DB as Business DB
    S->>C: Deliver(eventId=E-17)
    C->>DB: BEGIN + UPDATE inventory
    C->>DB: COMMIT
    DB-->>C: Commit OK
    Note over C: Crash before ACK
    S->>C: Redeliver(eventId=E-17)
    C->>DB: Check processed_messages(E-17)
    DB-->>C: Already processed
    C-->>S: ACK after verification
~~~

Here, rollback **cannot undo** the already-committed DB transaction. Redelivery is expected. The consumer must recognize `E-17` was already processed and avoid applying the business effect a second time.

### Scenario C — ACK Too Early, Then DB Rollback

~~~mermaid
sequenceDiagram
    participant S as Source/Broker
    participant C as Consumer
    participant DB as Business DB
    S->>C: Deliver(eventId=E-17)
    C-->>S: ACK / commit offset
    C->>DB: BEGIN + UPDATE inventory
    DB-->>C: Error
    C->>DB: ROLLBACK
    Note over S,C: Source may not redeliver
~~~

Early ACK is only reasonable if the application has **transferred processing responsibility to another durable source**, such as writing the message into a durable inbox before ACKing. If it only hands the message to an in-memory executor and ACKs, a process crash can lose work.

## 5. Commit and Rollback in Spring Transactions

### Transactions with JDBC

Example of an application service:

~~~java
@Service
class InventoryApplicationService {
    private final JdbcTemplate jdbc;

    InventoryApplicationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserveStock(String sku, int quantity) {
        int updated = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """, quantity, sku, quantity);

        if (updated != 1) {
            throw new IllegalStateException(
                    "Insufficient stock for " + sku);
        }
    }
}
~~~

If the handler is called through the Spring proxy and `JdbcTemplate` uses a datasource belonging to the transaction manager, an escaping `RuntimeException` normally rolls back the transaction. If the method finishes normally, the transaction interceptor can commit.

Important notes:

1. `@Transactional` rolls back by default on `RuntimeException` and `Error`; **checked exceptions** require evaluating `rollbackFor`/rollback rules.
2. If you catch the exception and return normally, the transaction may commit despite business failure; the exception is when the transaction was already marked `rollback-only` or hits a separate commit error.
3. Internal self-calls `this.reserveStock(...)` normally bypass the Spring proxy, so the called method's advice may not run.
4. `Propagation.REQUIRES_NEW` creates an independent transaction; a committed inner transaction **is not automatically rolled back** if the outer transaction later rolls back.
5. A database transaction does not automatically include HTTP calls, broker publishing, file moves, or message ACKs.

### Rollback-Only and Retries

A transaction already marked `rollback-only` cannot "just retry a few more SQL statements" and expect to commit. For errors requiring retrying the entire business logic, it is usually better for **each attempt to have a new transaction**, with retry and transaction advice ordered explicitly.

~~~text
Retry boundary
  attempt 1 -> begin TX-1 -> handler -> rollback
  backoff
  attempt 2 -> begin TX-2 -> handler -> commit
~~~

In practice, advice ordering, transaction propagation, and endpoint error handlers decide whether each attempt gets its own transaction. With brokers, in-memory consumer retries and broker redelivery are **two layers** that can interact; avoid infinite loops.

## 6. Role of Channels in Redelivery

| Spring Integration Component | When running | When handler fails |
| --- | --- | --- |
| `DirectChannel` | Synchronous dispatch on the sender's thread. | Exceptions usually propagate back to sender/listener; active transaction can roll back if error propagates properly. |
| `PublishSubscribeChannel` without executor | Invokes subscribers synchronously. | Partial side effects may occur in earlier subscribers; rollback applies only to resources participating in the transaction. |
| `ExecutorChannel` | Usually hands processing off to a worker thread. | Worker errors happen after send; do not automatically roll back the sender's transaction/ACK. |
| In-memory `QueueChannel` | Stores messages in a RAM queue for a poller to pull later. | JDBC rollback does not automatically return dequeued messages to the RAM queue; restarts can lose queued messages. |
| Persistent channel/message store | Stores messages in durable storage, potentially supporting transactions. | Depends on fetch/delete mechanics, store type, datasource, and transaction manager; recoverability must be verified. |
| Inbound adapter/listener | Receives from a broker or external source. | ACK/redelivery follows container/source and error propagation; not independently decided by the channel. |

### Synchronous Flow Example

~~~mermaid
flowchart LR
    A["Message-driven inbound"] --> B["DirectChannel"]
    B --> C["Transformer"]
    C --> D["Filter / Router"]
    D --> E["Business handler"]
    E --> F[("DB")]
    F --> G["Return to listener"]
    G --> H["Source decides ACK / retry"]
~~~

Placing an `ExecutorChannel` before the business handler changes the model:

~~~mermaid
flowchart LR
    A["Listener thread: receive"] --> B["ExecutorChannel.send()"]
    B --> C["Listener may finish and ACK"]
    B -. "handoff" .-> D["Worker thread"]
    D --> E["Business handler in another TX"]
    E --> F[("DB")]
~~~

Some executors can run synchronously depending on configuration; inspect the specific `TaskExecutor`. With an async executor, if you want to ACK only after work is **truly durable**, you need a dedicated coordination mechanism or durable inbox persistence prior to ACK.

## 7. Transactional Poller and the Difference Between DB Rollback and Dequeue

Spring Integration allows applying transaction advice on a polling endpoint. Example:

~~~java
@Configuration
@EnableIntegration
class PollingConfiguration {
    @Bean
    QueueChannel workQueue() {
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow workFlow(
            PlatformTransactionManager transactionManager,
            InventoryConsumer consumer) {
        return IntegrationFlow.from(
                    "workQueue",
                    e -> e.poller(
                            Pollers.fixedDelay(1_000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(transactionManager)))
                .handle(consumer, "process")
                .get();
    }
}
~~~

The DSL snippet assumes `InventoryConsumer.process(...)` is a public method with a compatible payload and the transaction manager is suitably configured. The poller opens a transaction around one poll and its **synchronous** downstream steps within the advice scope.

**Common misconception:** `QueueChannel(100)` in the example stores messages in RAM. A JDBC transaction wrapping the handler **does not** turn taking an item from a RAM queue into a transactional operation. If the handler fails:

- SQL statements participating in the JDBC transaction can roll back.
- The message removed from `QueueChannel` is not automatically put back.
- A process crash can lose messages waiting in RAM.

To gain recoverability, you need a **durable source**: a broker with ACK/redelivery, a database-backed message store with compatible transactions, or a work table with claim/lease and reclaim. Verify atomicity between message fetch/deletion and business writes for the specific storage type.

### Polling Multiple Messages in One Transaction?

Settings like `maxMessagesPerPoll` control how many messages are processed per poll cycle, yet how many share a transaction also depends on how the poller/transaction advice operates and task configuration. Avoid assuming an entire batch committed/rolled back together solely from this parameter. For business logic needing per-message isolation, test with `maxMessagesPerPoll(1)` and verify transaction scope with integration tests.

## 8. JMS, RabbitMQ, and Kafka: Three Different Redelivery Models

### 8.1. JMS — Transacted Session Rollback

In JMS, a listener container can use a **transacted JMS session**. When a message is processed synchronously and succeeds, the container can commit the session; when a matching exception occurs, the container rolls back the JMS session and the broker may redeliver the message.

~~~text
JMS queue
  -> listener container (sessionTransacted = true)
  -> Spring Integration inbound adapter
  -> DirectChannel
  -> JDBC business handler

Handler error -> error propagates to listener
              -> rollback JMS session
              -> broker may redeliver
~~~

**JMS local transactions** and **JDBC transactions** are two separate scopes unless a coordination mechanism is configured. What can happen:

- DB commits, yet JMS session rolls back → redelivery of the same message.
- DB rolls back, yet JMS session commits because the error was swallowed → message is not redelivered.

If atomicity between JMS and another DB is required, evaluate **XA/JTA** support across the provider, JDBC driver, and transaction manager. Never assume `sessionTransacted = true` alone gives a shared transaction.

### 8.2. RabbitMQ / AMQP — ACK, NACK, Requeue, and DLQ

RabbitMQ manages delivery acknowledgements. Depending on the listener container/adapter, it can:

- ACK when work is considered successful.
- Reject/NACK after error, choosing whether to requeue or not.
- Use a dead-letter exchange/queue to store unprocessable messages.
- Redeliver unacknowledged messages when a consumer channel/connection closes.

Configurations to verify per adapter/version: acknowledgement mode, prefetch, retry interceptor, error handler, default requeue policy, dead-letter configuration, and consumer concurrency.

**Example:** the consumer commits the DB successfully but loses connection before ACK. The broker may redeliver the message; **the consumer must be idempotent**. Conversely, if an error handler consumes the exception and the container treats the invocation as successful, the container may ACK a message even though business logic failed.

Broker transactions or confirms do not automatically become JDBC datasource transactions. Distinguish publisher confirms, consumer acknowledgements, and broker local transactions, as they serve different points in time and responsibilities.

### 8.3. Kafka — Offsets and Re-Reading Records

Kafka stores records in a log and tracks consumption progress via consumer group **offsets**. There is no "put message back at the front of the queue" operation as in some brokers: records remain in the log per retention; re-reading depends on offsets, partitions, consumer group, and retry policy.

Example:

1. Consumer reads record at offset 120.
2. Handler updates PostgreSQL and commits DB.
3. Process crashes before the corresponding offset is committed.
4. The next consumer can re-read offset 120.

Kafka transactions support atomicity for certain **Kafka-read → Kafka-write** pipelines and offset operations under appropriately configured Kafka mechanisms. It **does not automatically** make PostgreSQL a resource of the Kafka transaction. Thus, for consumers writing to a database, you need idempotency/inbox and proper offset commit settings.

### Quick Comparison

| Source | “Processed” is typically determined via | Common triggers for reprocessing | What to inspect |
| --- | --- | --- | --- |
| JMS | Session commit/ACK per container. | Session rollback or connection error before commit. | Transaction mode, exception propagation, redelivery policy, DLQ. |
| RabbitMQ | Consumer ACK. | NACK/requeue, reject policy, lost connection while unACKed. | ACK mode, prefetch, requeue, DLX/DLQ, retry. |
| Kafka | Offset commit / consumer group progress. | Unrecorded offset, rebalance, or retry/seek. | Ack/commit mode, offsets, partitions, retry handler, DLT. |
| DB work queue | Row/claim/lease status or dequeue operation. | Unpersisted state, expired claim, transaction rollback. | Isolation, locking, leases, reclaim, and atomicity. |

## 9. How Errors Going Through Error Channel Affect Commit

With synchronous flows over `DirectChannel`, exceptions from Filter, Transformer, Router, Service Activator, or handlers can propagate back to the inbound adapter or caller. But when moving to `ExecutorChannel`, pollers, or message-driven sources, errors may be wrapped in an `ErrorMessage` and routed to `errorChannel` per configuration.

What must be determined is **not just whether `errorChannel` receives the error**, but:

1. Does the transaction interceptor observe an exception or a successful return?
2. Does the inbound listener receive the exception to roll back/NACK?
3. Did the error flow handle the error and return normally, or rethrow it?
4. Does ACK happen before or after the exception is handled?

| Behavior | Possible outcome |
| --- | --- |
| Synchronous handler exception escapes `@Transactional`. | DB rolls back per rollback rules. |
| Handler catches exception, only logs, and returns. | DB may commit; listener may ACK if treated as success. |
| Error flow sends error to DLQ and completes normally. | Initial delivery may be treated as handled; acceptable if DLQ persists durably and policy allows it. |
| Async worker fails after caller already ACKed. | Failure does not trigger redelivery from the original source. |
| Local retries exhaust and error is thrown back to listener. | Broker may redeliver or dead-letter per policy. |

### Anti-pattern: Swallowing Errors While Expecting Rollback

~~~java
@Transactional
public void processBadly(ReserveInventory event) {
    try {
        inventoryService.apply(event);
    } catch (RuntimeException exception) {
        log.warn("Reserve failed, orderId={}", event.orderId(), exception);
        // Without rethrowing and if the transaction isn't rollback-only,
        // the call may be treated as successful.
    }
}
~~~

When business logic needs the source to redeliver, errors must **reach the boundary capable of requesting retry/redelivery**. However, never throw every error indefinitely: malformed schemas or business rule violations can become poison messages and stall the consumer.

## 10. Retry, Redelivery, and Dead-Letter: Where Does Responsibility Belong?

Distinguish:

- **In-handler retry**: re-invoking processing before returning to the listener. Same delivery, multiple attempts.
- **Broker/source redelivery**: the source delivers the message again because the prior delivery was unconfirmed or rejected.
- **Operational replay**: proactively replaying events from a DLQ, durable inbox, outbox, or event log.

| Error category | Typical appropriate handling | Limits |
| --- | --- | --- |
| Brief DB disconnect | Bounded retries with exponential backoff and jitter where appropriate. | Give each attempt a fresh transaction; avoid reusing rollback-only transactions. |
| Broker/network timeout | Retry with a stable event identifier and idempotency. | Timeout does not prove the receiver definitely did not process it. |
| Invalid schema payload | Reject/quarantine/DLQ with a clear reason. | Infinite retries cannot fix invalid data. |
| Insufficient inventory | Decide per business policy: controlled rejection, store failure outcome, or wait for state change. | Do not default to infinite retries. |
| Consumer dies after DB commit | Source redelivers while unACKed; consumer checks event ID. | Must prove side effects are not applied twice. |
| One Splitter branch fails | Per-branch retries, timeouts, partial status; Saga/compensation if needed. | Rolling back one local transaction does not undo another branch's committed work. |

### Dead-Letter Does Not Mean “Delete the Error”

A DLQ or dead-letter topic stores unprocessable messages for **inspection, triage, data repair, and replay**. Track the original message, `eventId`, failure cause, attempt count, failure timestamp, endpoint, and schema version. When replaying, preserve the event identifier or apply explicit transformation rules so idempotency is not broken.

A common policy:

~~~text
Receive
  -> Validate schema
     -> Permanent error: quarantine / DLQ
  -> Start business transaction
     -> Temporary failure: rollback + bounded retry/backoff
     -> Success: commit
  -> Complete delivery using source ACK/offset policy

After retries exhausted:
  -> durable error record / DLQ
  -> alert + manual/automatic replay with deduplication
~~~

Do not assume routing a message to an external system's DLQ is **atomic** with DB rollback; if that is a business requirement, design durable state persistence and corresponding recovery.

## 11. Safe Deduplication: Idempotent Consumer with PostgreSQL

The **idempotent consumer** pattern stores the completed event ID in the same transaction as the business update. If the same message arrives again, the consumer returns normally after confirming it was already handled.

### Data Design

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(80) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);

CREATE TABLE processed_messages (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

The `(consumer_name, event_id)` key lets different business consumers process the same event independently. If there is only one consumer, `event_id` alone can serve as the unique key.

### Payload and Handler

~~~java
record ReserveInventory(
        String eventId,
        String orderId,
        String sku,
        int quantity) {}

@Service
class InventoryConsumer {
    private static final String CONSUMER_NAME = "inventory-reservation";

    private final JdbcTemplate jdbc;

    InventoryConsumer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void process(ReserveInventory event) {
        if (event.eventId() == null || event.eventId().isBlank()
                || event.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid inventory event");
        }

        // PostgreSQL: unique key also handles concurrent duplicate deliveries.
        int claimed = jdbc.update("""
                INSERT INTO processed_messages(consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """, CONSUMER_NAME, event.eventId());

        if (claimed == 0) {
            // Same event already committed in a previous attempt.
            return;
        }

        int changed = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """,
                event.quantity(), event.sku(), event.quantity());

        if (changed != 1) {
            throw new IllegalStateException(
                    "Cannot reserve stock for " + event.sku());
        }
    }
}
~~~

**Why insert `processed_messages` before updating inventory?** Because *both SQL statements* are in one DB transaction:

- If the update fails, the exception rolls back the transaction, and **the processed marker rolls back too**. Future redeliveries can still try again.
- If the update and commit succeed, subsequent deliveries see the existing key and **do not deduct stock again**.
- When two workers process the same event concurrently, the unique constraint and database transaction/locking mechanics prevent both from committing the business effect for the same key.

`ON CONFLICT ... DO NOTHING` is PostgreSQL syntax; replace with appropriate upsert/conflict handling on other DBs. Never use an unprotected `SELECT` then `INSERT` pattern because two workers can both read "not found".

### Placing the Handler in a Synchronous IntegrationFlow

~~~java
@Configuration
@EnableIntegration
class InventoryFlowConfiguration {
    @Bean("inventoryInput")
    MessageChannel inventoryInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow reserveInventoryFlow(InventoryConsumer consumer) {
        return IntegrationFlow.from("inventoryInput")
                .handle(consumer, "process")
                .get();
    }
}
~~~

This example demonstrates **a synchronous processing branch**, and does not configure inbound brokers or ACKs itself. If a listener adapter sends a message to `inventoryInput` and waits for the handler to finish, errors can propagate back per the adapter's contract. Separate configuration for JMS/RabbitMQ/Kafka matching your Spring Integration version and source policy must be added.

### Limitations of Idempotency

1. `eventId` must remain **stable** across retries/redeliveries; never mint a new UUID on each attempt processing the same message.
2. `consumer_name` defines the **business scope** for the unique constraint; do not share improperly across distinct consumers.
3. The processed marker and business change must share a transaction on compatible resources.
4. External side effects like email/HTTP do not automatically roll back with the two SQL statements; for critical outbound events, write an **outbox record** alongside the business update.
5. If the same `eventId` arrives with a conflicting payload, detect and alert (e.g., store a payload hash or version), rather than silently ignoring tampered messages.
6. For business rules like insufficient inventory, distinguish **permanent** failures from **transient** errors to decide between saving status, DLQ, or retry.

## 12. When the Consumer Also Emits Events: Combining Inbox and Outbox

Suppose a `PaymentConfirmed` message updates the order in the DB and needs to emit `OrderReady`. If the consumer publishes directly to the broker **inside** the DB transaction, the broker may receive the message while the DB rolls back. If it publishes **after** DB commit, the event can be lost if the process crashes before publishing.

A safer pattern within one database:

~~~mermaid
flowchart LR
    A["Inbound broker"] --> B["Consumer"]
    subgraph TX["One DB transaction"]
      C["INSERT processed_messages"] --> D["UPDATE orders"]
      D --> E["INSERT outbox_events"]
    end
    B --> C
    E --> F[("Committed DB")]
    F --> G["Outbox relay"]
    G --> H["Outbound broker"]
    H --> I["Idempotent downstream consumer"]
~~~

Steps:

1. Receive the message and check the idempotency key.
2. Within the **same DB transaction**, mark processed, update business data, and insert the outbox event.
3. Commit the DB; the listener completes source acknowledgement per policy.
4. The relay reads committed outbox rows and publishes with a fixed `eventId`.
5. Once the broker confirms per protocol, the relay marks sent; it may republish if it crashes before marking.

Inbox/outbox addresses both sides of reliability: **duplicate input processing** and **losing outbound send intent**. It still requires backlog monitoring and idempotent consumers; the broker and DB do not become a distributed transaction simply by applying this pattern.

## 13. Router, Filter, Splitter, Aggregator: How Far Does Rollback Reach?

In complex flows, a message may branch:

~~~mermaid
flowchart LR
    A["Gateway or inbound adapter"] --> B["Transformer"]
    B --> C{"Router"}
    C --> D["Filter + DirectChannel"]
    C --> E["Splitter"]
    D --> F["Handler A: JDBC"]
    E --> G["ExecutorChannel / workers"]
    G --> H["Handler B: remote"]
    F --> I["Aggregator"]
    H --> I
~~~

- **Transformer** can fail on invalid payloads. If running synchronously inside the consumer boundary and exceptions propagate back, the transaction can roll back and the source can redeliver per policy.
- **Filter** typically drops messages per business rules and ends the flow **successfully**. If a message is filtered out while the inbound adapter ACKs, it may not be redelivered. If dropping should be treated as an error, route intentionally to an error branch.
- **Router** selects branches. A branch through `DirectChannel` can stay in the current thread's transaction; a branch handed off to an executor/broker usually has its own transaction.
- **Splitter** creates multiple child messages. If branches run on different threads or services, no default local rollback erases all committed side effects.
- **Aggregator** needs a correlation key, release strategy, and suitable store. When a branch redelivers, the aggregator must guard against duplicate results, handle late arrivals, and manage timeouts; a correlation ID does not make branch transactions atomic.
- **Gateway** synchronous calls only return results for steps completed before return; an asynchronous branch may still be running even though the caller already got an ACK/response.

If a business process spans multiple independently committable steps, use Saga/compensation and persist progress. Compensation is a **new business action** (such as issuing a refund after charging), not rolling back another service's transaction.

### Correlation, Message ID, and Business Event ID

| ID | Purpose | Use for deduplicating business side effects? |
| --- | --- | --- |
| `MessageHeaders.ID` | Identifies a message instance in Spring Integration. | Should not be relied upon alone; newly constructed retry messages can have different IDs. |
| `correlationId` or `orderId` | Groups messages belonging to the same workflow/order. | Only when the domain defines the exact unique scope of work. |
| Business `eventId` | Identifies **one event** stably across redeliveries. | Usually appropriate as the consumer's idempotency key. |
| `sequenceNumber` | Order of child messages in Splitter/Aggregator. | Does not replace an event ID or transaction ID. |

## 14. Testing Rollback and Redelivery Behavior

### 14.1. Testing Idempotency in the Database

With the schema and `InventoryConsumer` shown earlier:

~~~java
@SpringBootTest
class InventoryConsumerIT {
    @Autowired InventoryConsumer consumer;
    @Autowired JdbcTemplate jdbc;

    @Test
    void redeliveryDoesNotReserveTwice() {
        String sku = "SKU-" + UUID.randomUUID();
        String eventId = UUID.randomUUID().toString();

        jdbc.update(
                "INSERT INTO inventory(sku, available) VALUES (?, ?)",
                sku, 10);

        ReserveInventory message =
                new ReserveInventory(eventId, "ORDER-1", sku, 3);

        consumer.process(message);
        consumer.process(message); // Simulate redelivery.

        Integer available = jdbc.queryForObject(
                "SELECT available FROM inventory WHERE sku = ?",
                Integer.class, sku);

        Integer processedCount = jdbc.queryForObject("""
                SELECT COUNT(*) FROM processed_messages
                WHERE consumer_name = ? AND event_id = ?
                """, Integer.class, "inventory-reservation", eventId);

        assertEquals(7, available);
        assertEquals(1, processedCount);
    }

    @Test
    void rollbackKeepsEventEligibleForRetry() {
        String sku = "SKU-" + UUID.randomUUID();
        String eventId = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO inventory(sku, available) VALUES (?, ?)",
                sku, 2);

        assertThrows(IllegalStateException.class,
                () -> consumer.process(new ReserveInventory(
                        eventId, "ORDER-2", sku, 5)));

        Integer markers = jdbc.queryForObject("""
                SELECT COUNT(*) FROM processed_messages
                WHERE consumer_name = ? AND event_id = ?
                """, Integer.class, "inventory-reservation", eventId);
        assertEquals(0, markers);
    }
}
~~~

The example assumes Spring Boot test, JUnit Jupiter, schema, and datasource are present. Avoid putting `@Transactional` on the test itself if that causes an outer transaction to mask handler commit/rollback outcomes. The two tests prove idempotency and rollback **at the DB**, not yet that the real source redelivers.

### 14.2. Testing Real Message Sources

To verify redelivery, write integration tests with a real broker/container and explicit ACK configuration:

| Fault injection scenario | What to observe | Pass criteria |
| --- | --- | --- |
| Handler throws exception **before** DB commit. | DB state, ACK/NACK/offset, delivery count. | No business row committed; retry/DLQ matches source policy. |
| Handler commits DB, consumer loses connection **before** ACK. | Message redelivered and count of business effects. | Source can redeliver; side effect applied only once. |
| Consumer ACKs/commits offset **before** DB commit then crashes. | Are messages stuck or redelivered? | Exposes lost-work risk; fix ordering or use a durable inbox. |
| One worker receives duplicate message concurrently with another worker. | Unique constraint, transaction isolation, and inventory result. | Only one business effect commits. |
| Repeated retries due to SQL error. | Fresh transaction per attempt, backoff, retry count. | Does not exceed retry budget or hold failed transactions. |
| Poison message (invalid schema). | DLQ, error record, consumer backlog. | No infinite retries; controlled recovery/replay possible. |
| Handler behind `ExecutorChannel` fails after listener returns. | Initial ACK, error channel, and task state. | Async limits understood; durable handoff exists or ACK redesigned. |
| Splitter spawns multiple branches, one branch fails. | Correlation, duplicates, aggregator timeout, compensation. | No lost or double-counted results; explicit partial-failure handling. |

Testcontainers with JMS/RabbitMQ/Kafka helps build realistic test environments, though you must check the broker, adapter, and framework versions used by the project. For crash cases, you typically need an explicit hook/fixture stopping **after DB commit before ACK**, then restarting the consumer and verifying data.

## 15. Operational Observability

A reliable system must be able to explain *why* a message was redelivered. Record:

- Stable business `eventId`; `orderId` and `correlationId` when multiple branches exist.
- Endpoint/channel name, consumer group or queue; partition/offset or delivery tag if provided by the source.
- Timestamps for `received`, `business_committed`/`rolled_back`, `acknowledged`/`offset_committed`.
- Local attempt count, redelivery count, dedupe result, and exception type.
- Pending message count, latency from publish to business commit, DLQ size/age, and retry success rate.

Do not log sensitive data in payloads. A `"received message"` or `"send true"` log line is not enough to prove the transaction or end-to-end processing finished.

### Incident Investigation Signals

| Signal | Suspicions to investigate |
| --- | --- |
| Sharp rise in redeliveries | Repeated consumer rollbacks, failed ACKs, rebalances, or crash loops. |
| Spike in duplicate skips | Frequent source redeliveries or producer republishing the same event. |
| Rising queue depth / Kafka lag | Slow consumer, stuck transactions, poison messages, or resource exhaustion. |
| Growing/aging DLQ | Missing triage/replay procedure or hard-to-fix schema errors. |
| DB has record but downstream event missing | Dual-write bug, missing outbox, lost post-commit callback, or stalled relay. |
| Duplicate processing despite dedupe table | `eventId` changing across retries, wrong key scope, or side effects outside the transaction. |

## 16. Choosing an Architecture Matching Requirements

| Requirement | Design pattern | Risks to verify |
| --- | --- | --- |
| Temporary in-process handling, loss on restart acceptable | In-memory `QueueChannel` + poller. | Dequeue does not roll back with JDBC; crashes lose messages. |
| DB-backed work queue sharing the business DB | Transactional poller + store/claim with matching transactions. | Isolation, leases, concurrency, reclaim, and committing on the same resource. |
| Receive from JMS/RabbitMQ/Kafka and write to DB | Synchronous inbound adapter + DB transaction + idempotent consumer; source-appropriate ACK. | Crash after DB commit before ACK, broker-specific retries, and DLQ. |
| Background consumer processing yet listener needs fast ACK | Durable inbox/queue handoff then ACK. | ACK only after data is durably persisted. |
| New business event must be emitted after DB update | Write outbox in the same transaction, relay, and idempotent consumer. | Publisher resending duplicates after crash; requires retries and backlog monitoring. |
| Multi-service Router/Splitter where Aggregator waits for results | Per-consumer transactions + correlation + persistent state + compensation. | Partial commits, timeouts, late arrivals, and duplicates. |

In multi-resource systems, **short local commits + durable sources + idempotency + bounded retries** typically yield a clear recovery model. A long transaction stretching across network calls does not magically add atomicity and can increase connection/lock hold times.

## 17. Hands-On Exercises

**Exercise 1 — Draw two transactions.** Given `RabbitMQ listener → DirectChannel → InventoryConsumer @Transactional → PostgreSQL`, draw the timeline for receive, DB commit, and ACK. If the process crashes immediately after DB commit, predict what the broker and handler will do when the same message is redelivered.

**Exercise 2 — Verify QueueChannel.** Create `QueueChannel(100)` and a poller using `.transactional(transactionManager)`. Inside the handler, insert a row and throw an error. Observe the DB rollback and remaining item count in the queue. Explain why the result cannot be used to claim durable redelivery.

**Exercise 3 — Poison message.** Send a payload missing `eventId` or with an invalid quantity. Design permanent errors to route to a DLQ instead of retrying infinitely; provide a process to fix the schema and replay the message under the same business key.

**Exercise 4 — Two concurrent deliveries.** Have two workers simultaneously receive `ReserveInventory(eventId="E-17")`. Use a unique constraint and transaction to prove only one worker modifies inventory; verify behavior if the first worker rolls back.

**Exercise 5 — Inbox and outbox.** Consumer receives `PaymentConfirmed`, updates `orders`, and inserts `OrderReady` into the outbox. Simulate the relay publishing successfully then crashing before marking `SENT`. When the relay runs again, prove the downstream consumer still applies business logic only once.

### Self-Check Questions

**1. Does a JDBC rollback automatically make RabbitMQ put the message back?** No. Redelivery depends on listener/container ACK/NACK/requeue; JDBC rollback only affects participating JDBC resources.

**2. Why can redelivery still happen after the DB has committed?** The source has not received an ACK or committed the offset, such as when the process crashes after DB commit before ACK.

**3. Does placing `@Transactional` on a handler automatically include Kafka offset commits?** Not by default. Offsets belong to Kafka/adapter mechanics, whereas the JDBC transaction manager manages the database.

**4. What does `DirectChannel` guarantee?** Synchronous dispatch on the same thread, allowing caller exceptions and transaction context to relate to the handler; it does not guarantee non-JDBC side effects roll back together.

**5. Which ID should be used for best deduplication?** A business `eventId` stable across redeliveries, paired with a unique constraint in the same transaction as business updates; do not rely on every message transfer having the same `MessageHeaders.ID`.

**6. When is a DLQ needed?** When a message cannot be processed after bounded retries or is permanently invalid; preserve error context for repair and controlled replay.

## 18. Pre-Production Checklist for Consumers

- [ ] Identify whether the message source is in-memory, a persistent store, JMS, RabbitMQ, Kafka, HTTP, or another type.
- [ ] Draw transaction boundaries and specify which resources each transaction manager commits/rolls back.
- [ ] Know when the listener/poller starts and finishes processing; define ACK/offset policies.
- [ ] Inspect thread handoff points at `ExecutorChannel` and all asynchronous processing branches.
- [ ] Distinguish handler rollback from source rollback/requeue; verify actual redelivery behavior.
- [ ] Never ACK before business completion **or** durable persistence at a recoverable handoff point.
- [ ] Ensure `eventId` stays stable across retries and the idempotency table shares the transaction with business updates.
- [ ] Never swallow exceptions in a way that gives listeners a false success signal; inspect error channels and retry advice.
- [ ] Have bounded retries, backoff, DLQ/quarantine, and a replay procedure.
- [ ] If the consumer also emits new events, consider inbox + outbox to preserve send intent.
- [ ] Test failures before DB commit, after DB commit before ACK, and immediately after ACK.
- [ ] Test concurrent duplicates, broker disconnects, restarts, poison messages, and multi-branch flows.
- [ ] Monitor queue depth/consumer lag, redeliveries, duplicates, error rate, DLQ, correlation, and end-to-end latency.

**Takeaway:** **Commit/rollback only affects resources genuinely inside the transaction; redelivery is determined by the message source and ACK/offset mechanism.** With Spring Integration, combine clear transaction boundaries, proper error routing, durable messages, and idempotent consumers. That is the foundation enabling Router, Filter, Transformer, Splitter, Aggregator, and Gateway flows to recover from failures without duplicate side effects.
