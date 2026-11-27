# Transactional Resources and Message Channels in Spring Integration

## 1. Opening Question: What Is the Transaction Protecting?

Suppose an application processes an order:

1. Saves an `orders` record to PostgreSQL.
2. Places a `ReserveInventory` message onto a Spring Integration `MessageChannel`.
3. A consumer pulls the message, deducts stock in the database, and completes processing.

If the order-creation transaction rolls back, does the message in step 2 disappear? If the consumer fails to update inventory, is the message removed from the channel returned for retry? **You cannot answer solely from the `MessageChannel` name or the presence of `@Transactional`.**

You must know which **transactional resource** genuinely participates in the transaction:

- With `DirectChannel`, the channel itself only dispatches messages synchronously; downstream JDBC handlers *can* join the caller's transaction.
- With a default in-memory `QueueChannel`, enqueue/dequeue do not become transactional JDBC operations simply because an outer `@Transactional` exists.
- With a `QueueChannel` backed by a **transactional JDBC message store**, storing or taking messages *can* share the same database transaction with business data.
- With JMS, RabbitMQ, Kafka, or an external API, the message source has its own transaction/ACK; `DataSourceTransactionManager` does not automatically manage those resources.

This lesson **Transactional Resources and Message Channels** belongs to the *Transactional messaging* chapter of the `SPRING_INTEGRATION_PATTERN` module. Its goal is to build Enterprise Integration Patterns (Router, Filter, Transformer, Splitter, Aggregator, Gateway...) that are loosely coupled, scalable, and explicit in retries and error handling **without misunderstanding transaction boundaries**.

### Learning Outcomes

After this lesson, you can:

1. Distinguish *message channel*, *message store*, *transaction manager*, and *transactional resource*.
2. Evaluate rollback effectiveness across `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and persistent channels.
3. Configure a `QueueChannel` with `JdbcChannelMessageStore` and a transactional poller in a PostgreSQL context.
4. Design cases for sending within an order-creation transaction and receiving within a business-update transaction.
5. Distinguish resource-local transactions from cross-resource coordinated transactions; identify when outbox, inbox, and idempotent consumers are needed.
6. Test crashes, rollbacks, redeliveries, retries, error channels, and branched processing.

## 2. Four Components to Separate

| Component | Role | Examples |
| --- | --- | --- |
| **Message** | Carries `payload` and `headers` through the flow. | `Message<ReserveInventory>`, `eventId`, `correlationId`. |
| **MessageChannel** | Defines delivery mechanics from sender to consumer/handler. | `DirectChannel`, `ExecutorChannel`, `QueueChannel`, `PublishSubscribeChannel`. |
| **Resource** | Holds state or produces side effects, with or without transaction support. | PostgreSQL, JMS session, Kafka producer, memory, HTTP system. |
| **Transaction manager** | Opens, commits, and rolls back transactions for resources configured to participate. | `JdbcTransactionManager`, `DataSourceTransactionManager`, `JmsTransactionManager`, JTA manager. |

**Key point:** A channel is a message-exchange mechanism. A resource is what can truly *commit/roll back*. One flow may have multiple channels yet only a single DB transaction; conversely, two similar-looking channels may write to different resources and **not** commit atomically together.

### A Simple Mental Model

~~~mermaid
flowchart LR
    G["Gateway"] --> DC["DirectChannel"]
    DC --> A["Service Activator"]
    A --> DB[("Business PostgreSQL")]
    DC --> Q["QueueChannel"]
    Q --> MS[("MessageStore")]
    MS --> P["Transactional poller"]
    P --> H["Handler"]
    H --> DB
    T["Transaction manager"] -. "manages enlisted resources" .-> DB
    T -. "if store shares DB/manager" .-> MS
~~~

Inside a JDBC transaction, `JdbcTemplate` normally obtains the connection bound by Spring to the thread. If `JdbcChannelMessageStore` uses **the same datasource and a compatible transaction manager**, store operations can join that physical transaction. If the message store uses a different datasource, do not assume both writes commit atomically.

## 3. “Transactional Channel” Is Not an Attribute of Every MessageChannel

Spring Integration classifies channels into two primary communication groups:

- **`SubscribableChannel`**: subscribed handlers receive messages dispatched by the channel. Common types: `DirectChannel`, `ExecutorChannel`, `PublishSubscribeChannel`.
- **`PollableChannel`**: consumers actively pull messages via `receive()`. Common types: `QueueChannel`, `PriorityChannel`, `RendezvousChannel`.

All are channels, yet they differ in threading, storage, and rollback capability for insert/remove operations.

| Channel | Mechanism | Relationship with transactions |
| --- | --- | --- |
| `DirectChannel` | Dispatches handler synchronously on the sending thread. | Lets downstream JDBC handlers use the active transaction, though the channel itself provides no durable storage. |
| `PublishSubscribeChannel` without executor | Dispatches subscribers synchronously. | Handlers can join the active transaction; external side effects in earlier subscribers are not necessarily reversible. |
| `ExecutorChannel` | Hands processing off via a `TaskExecutor`, usually to another thread. | Does not automatically propagate thread-bound transactions; sender and worker have separate boundaries. |
| Default `QueueChannel` | Stores in a RAM queue; consumer polls later. | DB rollback does not automatically reverse RAM enqueue/dequeue; restarts can lose messages. |
| Default `PriorityChannel` | RAM queue ordered by priority. | Has durability/transaction traits similar to RAM queues; ordering is not a transaction. |
| `RendezvousChannel` | Direct handoff via synchronization between sender and receiver. | Synchronized handoff timing does not mean a shared transaction across threads. |
| `QueueChannel` + transactional `ChannelMessageStore` | Stores messages in a resource such as a JDBC DB. | Store operations can roll back if participating in a properly configured transaction. |
| JMS/AMQP-backed channel or inbound/outbound adapter | Relies on external broker/session/ACK. | Depends on broker transaction, confirmation, and acknowledgement mechanics; does not automatically join a JDBC transaction. |

`send()` returning `true` only means success per the channel's contract: for example, dispatched or accepted into the queue. It is **not universal proof** that an async handler committed the DB or a broker confirmed business processing.

## 4. Why the Same @Transactional Gives Different Results Across Two QueueChannels

Consider this code:

~~~java
@Transactional
public void placeOrder(CreateOrder command) {
    jdbc.update(
            "INSERT INTO orders(order_id, state) VALUES (?, ?)",
            command.orderId(), "CREATED");

    boolean accepted = messageChannel.send(
            MessageBuilder.withPayload(
                    new ReserveInventory(
                            command.eventId(),
                            command.orderId(),
                            command.sku(),
                            command.quantity()))
                    .build());

    if (!accepted) {
        throw new IllegalStateException("Message channel rejected event");
    }
}
~~~

This snippet alone is insufficient to conclude whether the message survives or disappears on transaction rollback. Swap different implementations for `messageChannel`:

### Option A: `QueueChannel(100)`

~~~java
@Bean("messageChannel")
PollableChannel messageChannel() {
    return new QueueChannel(100);
}
~~~

`send()` can place the message in RAM successfully. Later the `orders` transaction rolls back, yet the queued message **is not automatically removed**; a consumer may receive an uncommitted order. If the process crashes, the RAM queue may lose messages.

### Option B: `QueueChannel` with a transactional JDBC message store

~~~text
BEGIN TX-A (business DB)
  INSERT orders
  INSERT message into JDBC channel store (same DB/TX-A)
COMMIT or ROLLBACK TX-A
~~~

If both inserts use the same physical DB transaction, both **the order and the store message record** commit or roll back together. Consumers do not read uncommitted messages under appropriate isolation (such as READ_COMMITTED).

### Option C: Broker channel outside the DB transaction

~~~text
BEGIN TX-A (business DB)
  INSERT orders
  PUBLISH message to broker (different resource)
  ROLLBACK TX-A
~~~

The broker may already have received the message despite the database rollback. Putting a publish call inside `@Transactional` **does not** automatically enlist the broker in the JDBC transaction. Even if the broker/session has its own local transaction, commit ordering between the two resources must still be addressed.

### Quick Matrix

| Channel resource | Caller DB rollback | App crash | Best suited for |
| --- | --- | --- | --- |
| RAM queue | Does not roll back enqueue/dequeue by default. | Messages may be lost. | Internal handoffs where data loss is acceptable. |
| JDBC store **same transaction** | Store insert/remove can roll back with DB. | Committed records can be recovered. | DB-centric flows needing atomicity with business rows. |
| JDBC store **different datasource/transaction** | Does not automatically roll back with business DB. | May persist independently. | Requires dual-write / idempotency design. |
| JMS/AMQP/Kafka | Depends on the broker's own resource/transaction. | Can be durable per broker configuration. | Cross-process integration, consumer scaling. |

## 5. Configuring a JDBC-Backed QueueChannel with Spring Integration

A persistent queue in Spring Integration can use `JdbcChannelMessageStore` from the `spring-integration-jdbc` module. This store persists messages into tables whose DDL is provided by Spring Integration; with PostgreSQL, configure the corresponding query provider.

### 5.1. Prerequisites

- The application has a `DataSource` pointing to PostgreSQL and a `PlatformTransactionManager` bound to that datasource.
- Spring Integration JDBC has been added and the JDBC channel message store schema/tables have been created using the **official script for your version**.
- Producer/consumer agree on the queue's region and group ID; group names do not collide with other queues.
- Payloads and headers must be compatible with the store's serialization/message conversion mechanism; keep business identifiers stable across recovery.
- Do not invent a minimal custom queue schema replacing the internal tables and expect `JdbcChannelMessageStore` to work.

To run the business examples below, you can create two separate application tables (without replacing Spring Integration's schema):

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(24) NOT NULL
);

CREATE TABLE inventory (
    sku VARCHAR(80) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
~~~

### 5.2. Example Payloads

~~~java
record CreateOrder(
        String eventId,
        String orderId,
        String sku,
        int quantity) {}

record ReserveInventory(
        String eventId,
        String orderId,
        String sku,
        int quantity) implements java.io.Serializable {}
~~~

`Serializable` illustrates one option for storing payloads with the default serializer; if using JSON or a custom converter, ensure schema evolution and readability across deployed application versions.

### 5.3. Java Configuration

~~~java
@Configuration
@EnableIntegration
class DurableQueueConfig {

    @Bean
    JdbcChannelMessageStore orderChannelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        store.setRegion("order-service");
        return store;
    }

    @Bean("pendingReservations")
    PollableChannel pendingReservations(
            JdbcChannelMessageStore orderChannelStore) {
        return new QueueChannel(
                new MessageGroupQueue(
                        orderChannelStore, "pending-reservations"));
    }
}
~~~

This Java configuration illustrates wiring `JdbcChannelMessageStore` with `MessageGroupQueue`, which is a `BlockingQueue` implementation backed by `MessageGroupStore`. Class and method names must be verified against your actual **Spring Integration version** when adopting in a project.

**Understand the role of `region` and `groupId`:**

- `region` partitions data among applications/channel groups sharing the message store tables.
- `groupId` identifies the message group belonging to that logical queue.
- Nodes sharing the same durable queue must agree on identifiers, while unrelated queues must stay separate to prevent cross-reading messages.

Do not configure a RAM queue's `capacity=100` assuming it caps a JDBC-backed queue. With a message store, capacity is normally governed by retention policies and DB resources; monitor backlog, table size, indexes, and polling rates.

### 5.4. Why Does a `QueueChannel` Java Bean Not Create a Transaction by Itself?

`new QueueChannel(new MessageGroupQueue(...))` only changes the queue's **storage location**. Transactions take effect when Spring opens a transaction and the store's JDBC operations use the participating datasource/connection.

In other words:

> **Persistent** is the ability to survive restarts; **transactional** is the ability for store operations to commit or roll back together with the associated transaction. These two properties are related, not identical.

Sending a message into a JDBC store *outside* `@Transactional` may auto-commit immediately in the database. Receiving from a JDBC-backed queue without a transactional poller may delete the message from the store before a business handler fails. Store durability **does not replace** proper transaction boundaries.

## 6. Producer: Writing Data and Sending Messages in One JDBC Transaction

Using `pendingReservations` from section 5, we can write:

~~~java
@Service
class OrderCommandService {
    private final JdbcTemplate jdbc;
    private final PollableChannel pendingReservations;

    OrderCommandService(
            JdbcTemplate jdbc,
            @Qualifier("pendingReservations")
            PollableChannel pendingReservations) {
        this.jdbc = jdbc;
        this.pendingReservations = pendingReservations;
    }

    @Transactional
    public void place(CreateOrder command) {
        writeAndEnqueue(command);
    }

    @Transactional
    public void placeThenFail(CreateOrder command) {
        writeAndEnqueue(command);
        throw new IllegalStateException("Simulated rollback");
    }

    private void writeAndEnqueue(CreateOrder command) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                command.orderId(), "CREATED");

        ReserveInventory event = new ReserveInventory(
                command.eventId(),
                command.orderId(),
                command.sku(),
                command.quantity());

        boolean accepted = pendingReservations.send(
                MessageBuilder.withPayload(event)
                        .setHeader("businessEventId", command.eventId())
                        .build());

        if (!accepted) {
            throw new IllegalStateException("Durable channel rejected event");
        }
    }
}
~~~

Both public methods demonstrate success and rollback cases, sharing a write/send helper **that does not open its own transaction** and verifying channel acceptance. `placeThenFail` does not call `this.place(...)` relying on an internal proxy call; the transaction is opened by `placeThenFail`'s own interceptor.

Assuming `orders` and `JdbcChannelMessageStore` share the same `DataSource` and transaction manager:

~~~mermaid
sequenceDiagram
    participant API as OrderCommandService
    participant DB as PostgreSQL
    participant Q as JDBC-backed QueueChannel
    API->>DB: BEGIN TX-A
    API->>DB: INSERT orders (TX-A)
    API->>Q: send(ReserveInventory)
    Q->>DB: INSERT channel message (TX-A)
    alt Success
        API->>DB: COMMIT TX-A
        Note over DB,Q: Order + message both durable
    else Error before commit
        API->>DB: ROLLBACK TX-A
        Note over DB,Q: No uncommitted order or message remains
    end
~~~

**Caveat:** Atomicity holds only when the store truly uses **the same transactional resource as business JDBC**. If code dispatches the message through an `ExecutorChannel`, a network listener, or a separate datasource before reaching the store, that atomicity is no longer guaranteed.

## 7. Consumer: Transactional Poller and Rolling Back Message Retrieval

The second aspect of transactional channels is **receive**. Spring Integration documentation notes that a persistent `QueueChannel` with a transactional store can roll back removing a message from the store if a poller processes within a transaction and that transaction rolls back.

### Java DSL

~~~java
@Configuration
@EnableIntegration
class ReservationConsumerFlow {

    @Bean
    IntegrationFlow reservationFlow(
            PlatformTransactionManager transactionManager,
            InventoryHandler inventoryHandler) {
        return IntegrationFlow.from(
                        "pendingReservations",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(1_000)
                                        .maxMessagesPerPoll(1)
                                        .transactional(transactionManager)))
                .handle(inventoryHandler, "reserve")
                .get();
    }
}
~~~

The handler uses the same PostgreSQL instance:

~~~java
@Service
class InventoryHandler {
    private final JdbcTemplate jdbc;

    InventoryHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve(ReserveInventory event) {
        int count = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """,
                event.quantity(), event.sku(), event.quantity());

        if (count != 1) {
            throw new IllegalStateException(
                    "Cannot reserve stock: " + event.sku());
        }
    }
}
~~~

Here, if the poller's transaction manager manages the same datasource as the message store and business data, **dequeuing** and updating `inventory` can execute inside **one physical JDBC transaction**:

~~~mermaid
sequenceDiagram
    participant Poller as Transactional poller
    participant Store as JdbcChannelMessageStore
    participant Handler as InventoryHandler
    participant DB as PostgreSQL
    Poller->>DB: BEGIN TX-P
    Poller->>Store: receive()
    Store->>DB: Fetch/delete message in TX-P
    Poller->>Handler: reserve(event)
    Handler->>DB: UPDATE inventory (TX-P)
    alt Handler succeeds
        Poller->>DB: COMMIT TX-P
        Note over DB,Store: Stock change and message removal commit together
    else Handler throws
        Poller->>DB: ROLLBACK TX-P
        Note over DB,Store: UPDATE rolls back; message is not permanently deleted
    end
~~~

### Conditions for Receive Rollback to Make the Message Reappear

1. **Transactional store**: fetch/delete operations execute against a JDBC resource supporting rollback.
2. **Poller transaction**: transaction advice wraps both `receive` and synchronous downstream handlers.
3. **Matching transaction manager/datasource**: store operations and business updates join compatible transactions, typically the same datasource.
4. **Errors propagate out**: exceptions reach the advice and match rollback rules, rather than being handled by an error flow that returns as success.
5. **No async boundary before business update**: if the poller merely hands off to an executor and completes, message deletion may commit before the worker processes it.

With a RAM `QueueChannel(100)`, condition (1) does not exist: even if the poller opens a JDBC transaction, dequeuing from memory is not automatically rolled back. With a JDBC store where the handler runs on a different datasource, rollback may protect **only the store operation**, while the business DB commits independently or vice versa.

### Another Limitation: Redelivery Does Not Equal Exactly-Once

If business processing makes an HTTP call or updates an independent database before the store transaction rolls back, the message may be received again while the external side effect already completed. Consumers **still need idempotency** for any activity outside the shared resource transaction.

## 8. When the Message Store Uses a Different Database from the Business Database

Consider two datasources:

~~~text
DataSource A -> PostgreSQL "business"
DataSource B -> PostgreSQL "integration-message-store"
~~~

A `DataSourceTransactionManager` managing A **does not** automatically control commits/rollbacks on B. Even if both are PostgreSQL or run on the same cluster, separate connections/resources/transaction scopes still risk **dual writes**.

| Write order | Crash/failure window | Consequence |
| --- | --- | --- |
| Write business A then channel store B | Business A commits; store B fails to write/commit. | Order exists without a message. |
| Write store B then commit business A | Store B commits; business A rolls back. | Message exists for a non-existent order. |
| Handler commits business B then dequeue commits on store A | Worker crashes between the two commits. | Message is redelivered, risking duplicate processing. |
| Dequeue commits on store A then business B rolls back | Worker crashes / DB fails after dequeue. | Message lost if source does not redeliver. |

### Choosing a Coordination Strategy

- **Single DB transaction**: when architecturally viable, persist business rows and durable intent/messages in the same database with one transaction manager; in-DB atomicity is then easy to reason about and test.
- **XA/JTA/2PC**: consider only when *all* resources support coordinated transactions, operational cost is acceptable, and failure semantics are thoroughly tested. Having two `PlatformTransactionManager` beans does not automatically create a global transaction.
- **Transactional outbox/inbox**: write send intent/processed markers into the business DB and transfer messages between services using durable mechanics and idempotency. This is the practical approach when multiple resources cannot commit atomically.
- **Saga/compensation**: when multiple services commit independently, persist workflow state and run compensating business actions; never treat compensation as rolling back another JDBC transaction.

## 9. Specific Resources of JMS, AMQP, and Kafka

Message brokers can offer durability, ACK, and transaction semantics **different** from a JDBC-backed message store.

| Technology | Resource / confirmation point | Key understanding |
| --- | --- | --- |
| **JMS** | JMS `Session`, session transactions, or listener-container-managed acknowledgements. | `JmsTransactionManager` provides JMS local transactions, not atomicity with a JDBC business DB; session rollback can trigger redelivery. |
| **RabbitMQ / AMQP** | Connection/channel, ACK/NACK/requeue, broker transactions, or publisher confirms depending on adapter. | Consumer ACK differs from publisher confirms. Broker transactions do not automatically join PostgreSQL transactions. |
| **Kafka** | Producer transactions, consumer offsets, and configured offset commits. | Kafka transactions can support atomicity for Kafka-read→Kafka-write pipelines; they do not automatically include a JDBC DB in a Kafka transaction. |
| **JDBC MessageStore** | Database rows/transactions of the datasource. | Send/dequeue can share a DB transaction if the store and handler use matching resources/managers. |
| **Redis or other NoSQL stores** | Depends on the store implementation and product transaction mechanics. | Never infer dequeue rollback solely from the word "persistent"; verify the specific API/adapter. |
| **HTTP/email/external API** | Remote side effects and responses. | A JDBC rollback does not automatically retract an email or API request already sent. |

### Example: JMS Local Transaction Does Not Cover the Business DB

~~~text
JMS listener receives OrderPaid
  -> JDBC handler opens transaction and updates orders
  -> JDBC COMMIT succeeds
  -> JMS session COMMIT fails
  -> JMS may redeliver OrderPaid
~~~

A JMS session transaction protects the session's own JMS operations. If JDBC committed independently, redelivery can repeat the business effect. Use stable event identifiers and idempotent consumers. Similarly, `@Transactional` on a JDBC handler does not automatically govern RabbitMQ ACKs or Kafka offsets.

### Never Confuse “Transactional Broker” with “End-to-End Exactly-Once”

A broker can offer exactly-once or transactional guarantees **within the scope defined by its documentation**. Yet a system spanning a broker, an external database, email, and HTTP does not gain a global transaction just because each component supports some form of local transaction.

## 10. Propagation and Threading Determine Which Resource Is Used

With a Spring bean handler:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void handle(ReserveInventory event) {
    int changed = jdbc.update("""
            UPDATE inventory
               SET available = available - ?
             WHERE sku = ? AND available >= ?
            """, event.quantity(), event.sku(), event.quantity());
    if (changed != 1) {
        throw new IllegalStateException("Unable to reserve inventory");
    }
}
~~~

`REQUIRED` joins the active transaction on the current thread; if none exists, it opens a new transaction via the selected manager. Other propagation modes to weigh:

| Propagation | Meaning when called via `DirectChannel` from an outer transaction | Flow risks |
| --- | --- | --- |
| `REQUIRED` | Joins the current physical transaction. | Outer rollback rolls back handler JDBC writes; caught exceptions can leave rollback-only state. |
| `REQUIRES_NEW` | Suspends outer, opens independent transaction. | Inner may commit even if outer rolls back; store and business updates may lose expected atomicity. |
| `NESTED` | Can use savepoints when manager supports them. | Inner does not commit independently; does not roll back non-DB side effects. |
| `MANDATORY` | Requires caller to hold a transaction. | Fails if handler runs from a worker/executor without a transaction. |
| `SUPPORTS` | Joins if present, otherwise runs without an actual transaction. | Should not be used when store/dequeue must be atomic with the business DB. |
| `NOT_SUPPORTED` | Suspends outer, runs without a transaction. | JDBC/store writes inside the method may commit separately and not roll back with outer. |
| `NEVER` | Rejects calls carrying a transaction. | Unsuitable for paths requiring a transaction. |

### Same Channel, Different Outcome Due to Thread Change

~~~mermaid
flowchart LR
    S["Gateway / Poller with TX-A"] --> D{"Channel"}
    D -->|"DirectChannel"| H1["Handler on thread A, can use TX-A"]
    D -->|"ExecutorChannel"| H2["Worker thread B, does not inherit TX-A"]
    H1 --> DB[("Business DB")]
    H2 --> TB["Transaction B if handler opens one"]
    TB --> DB
~~~

With an asynchronous executor, the poller may commit **dequeuing from the durable store** right after handing the task to the executor; if the worker fails later, the message is already durably deleted. For safe async processing, use a **durable handoff** or adjust ACK/dequeue so completion occurs only after a genuinely durable processing milestone.

Some `TaskExecutor` configurations can execute inline, so inspect the actual setup before assuming the worker definitely runs on a different thread.

## 11. Error Channel, Retry, and Transactional Resources

### Synchronous Handler Failures

When `DirectChannel` dispatches a handler synchronously and it throws an exception, the error usually propagates back to the poller/listener/caller. If the transaction interceptor sees an exception matching rollback rules, changes on participating resources can roll back.

~~~java
@Transactional
public void process(ReserveInventory event) {
    jdbc.update("UPDATE inventory SET ...");
    throw new IllegalStateException("Simulated handler failure");
}
~~~

### Anti-Pattern: Catching the Error and Returning Normally

~~~java
public void processAndHideFailure(ReserveInventory event) {
    try {
        inventoryHandler.reserve(event);
    } catch (Exception ex) {
        log.error("Cannot reserve inventory", ex);
        // If caller simply returns, poller or container may treat it as success.
    }
}
~~~

If the source is a JDBC-backed queue with a transactional poller, an error handler returning normally can cause the poller transaction to **commit the dequeue** even though the business handler failed. If the source is a broker, the listener may ACK. Exact behavior depends on rollback-only state and the advice chain; never just check error logs and assume redelivery will happen.

### Retry Outside vs. Inside a Transaction

~~~text
Retry outside transaction:
  attempt 1 -> BEGIN TX-1 -> receive/process -> ROLLBACK
  backoff
  attempt 2 -> BEGIN TX-2 -> receive/process -> COMMIT

Retry inside same transaction:
  BEGIN TX-A
    attempt 1 -> error, TX-A may be rollback-only
    attempt 2 -> handler re-runs
  COMMIT attempt -> may throw UnexpectedRollbackException
~~~

Once a transaction is marked rollback-only, retrying in the same physical transaction cannot guarantee commit. When retrying the entire JDBC unit of work, usually **open a new transaction per attempt**, verifying the actual order of retry advice and transaction advice.

### DLQ and Poison Messages

If an invalid message keeps rolling back to a JDBC store indefinitely, a poller may repeatedly pick up **the same poison message**. Enforce bounded attempts, backoff, quarantine/dead-letter storage, and controlled replay after fixing data. If moving a failed message to a **DB error table** in a new transaction, never accidentally commit deleting the original message while saving the error record fails.

When routing to an error channel, determine:

- Is the failure a **tolerable error message persisted durably**, or a signal that must trigger rollback?
- Does the error handler run on the same thread and transaction, or across another executor?
- Does moving to a DLQ have its own duplicate and retry policies?
- When the error flow returns normally, will the poller or broker treat the delivery as successful?

## 12. Inbox/Outbox Pattern When Not Sharing a Transactional Resource

If the inbound source and business DB do not share one physical transaction, a common pattern is **at-least-once delivery + idempotent consumer**. If the business DB must also emit new events, add a transactional outbox.

### Illustrative Schema

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

### Idempotent Handler

~~~java
@Service
class IdempotentInventoryHandler {
    private final JdbcTemplate jdbc;

    IdempotentInventoryHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(ReserveInventory event) {
        int marked = jdbc.update("""
                INSERT INTO processed_events(consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """, "inventory", event.eventId());

        if (marked == 0) {
            return; // Message already committed in a prior attempt.
        }

        int changed = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """, event.quantity(), event.sku(), event.quantity());

        if (changed != 1) {
            throw new IllegalStateException("Cannot reserve stock");
        }
        // If OrderReserved must be published, insert outbox row here
        // using the same JdbcTemplate/transaction.
    }
}
~~~

The SQL uses PostgreSQL syntax. `PRIMARY KEY` protects against two workers concurrently processing the same `eventId`; the processed marker and business update must share the same transaction. If business logic fails, rollback erases both the marker and inventory change. If redelivered after commit but before ACK, the next run detects the duplicate and avoids deducting stock again.

### Why Both Inbox and Outbox May Be Needed

~~~mermaid
sequenceDiagram
    participant Broker as Inbound broker
    participant C as Consumer
    participant DB as Business DB
    participant Relay as Outbox relay
    participant Downstream as Outbound broker
    Broker->>C: Deliver eventId=E-42
    C->>DB: BEGIN
    C->>DB: INSERT processed_events(E-42) if absent
    C->>DB: UPDATE business rows
    C->>DB: INSERT outbox_events(newEventId)
    C->>DB: COMMIT
    C-->>Broker: ACK per policy
    Relay->>DB: Read pending outbox
    Relay->>Downstream: Publish newEventId
    Downstream-->>Relay: Confirmation
    Relay->>DB: Mark SENT (may retry)
~~~

The inbox handles **inbound redeliveries**. The outbox ensures **outbound send intent** commits alongside business rows. If the relay publishes successfully and crashes before marking `SENT`, it may republish: downstream consumers must be idempotent.

**Do not confuse an outbox with a JDBC channel store:** both can store messages in a database and join transactions; however, an outbox is an architectural *pattern* with an event table, relay, publish status, and cross-service integration. A JDBC-backed `QueueChannel` is an internal channel implementation backed by `MessageStore`. Choose based on the problem, not just the word "durable".

## 13. Router, Filter, Splitter, and Aggregator with Transactional Resources

A real-world flow can branch:

~~~mermaid
flowchart LR
    G["Gateway"] --> T["Transformer"]
    T --> R{"Router"}
    R --> F["Filter"]
    R --> S["Splitter"]
    F --> D["DirectChannel -> DB handler"]
    S --> Q["Persistent QueueChannel"]
    Q --> P["Transactional poller"]
    P --> W["Worker / handler"]
    D --> A["Aggregator"]
    W --> A
~~~

At each step, mark the **resource** and **boundary**:

- **Transformer/Filter** running synchronously can remain in the active transaction. A Filter dropping a message is usually a valid result and does not automatically trigger rollback.
- **Router** can route from a synchronous channel to a persistent queue. When sending to the store uses the same DB transaction, queue rows can commit/roll back with business data; using a different store creates a dual write.
- **Splitter** produces child messages. If all enqueue into the same transactional store within one transaction, the enqueues can commit atomically inside that DB scope; **processing** the child messages in workers later happens in separate transactions.
- **Aggregator** needs a `correlationId`, sequence/release strategy, and a durable message store if state must survive restarts. Persistent aggregator state does not implicitly share a transaction with every consumer branch; inspect its store and manager separately.
- **Error channel** is usually a separate flow; if errors are consumed before the poller commits, the source may consider the message processed regardless of whether business side effects succeeded.
- **Gateway** returning success does not mean async branches finished; distinguish an “accepted” response contract from “processed”.

### Event ID Is Not Message ID

| Identifier | Function | Use for deduplicating reprocessing? |
| --- | --- | --- |
| `MessageHeaders.ID` | Identifies a message instance in Spring Integration. | Do not rely on solely: recreated messages may carry different IDs. |
| `correlationId` | Groups messages belonging to a workflow/order. | Used for joining branches, not implicitly a unique event ID. |
| `sequenceNumber` | Order of child messages after a Splitter. | Does not represent a global business execution unit. |
| Business `eventId`/`commandId` | Stable identifier of work/event across retries. | Usually the right key for an idempotent consumer. |

Transactions protect resources, whereas correlation/idempotency solve **distributed state** that a single local transaction cannot span.

## 14. Common Design Mistakes

### Mistake 1 — “Because `@Transactional` is present, an in-memory `QueueChannel` rolls back”

False. `@Transactional` only manages transactions for participating resources. Enqueue/dequeue in RAM queues do not roll back with JDBC.

### Mistake 2 — “A persistent `QueueChannel` guarantees redelivery”

Insufficient. If dequeue commits **before** the handler finishes or the poller has no transaction, the message can be deleted from the store when the handler fails. Inspect transaction scope across **both receive and downstream handlers**.

### Mistake 3 — “Two JDBC datasources mean one transaction”

Not by default. Same framework/driver does not guarantee the same physical transaction. Check datasources, connections, transaction managers, and if truly needed, transaction coordination mechanisms.

### Mistake 4 — “`ExecutorChannel` preserves the caller's JDBC transaction”

Normally false. Imperative transactions are thread-bound. Async boundaries create separate consumer transactions; durable handoffs and idempotency are needed.

### Mistake 5 — “Sending to Kafka/JMS inside JDBC `@Transactional` is atomic”

Not by default. Broker and database resource-local transactions are two separate scopes. Messages can leak for rolled-back DB work, or DB commits can miss messages; use an outbox when send intent must be guaranteed.

### Mistake 6 — “Once rolled back, duplicates are impossible”

False if side effects on another resource already committed. Moreover, a consumer can commit the DB before source ACK and get redelivered. Idempotency remains mandatory at the right boundaries.

### Mistake 7 — “Messages in a JDBC store always have strict FIFO and unlimited throughput”

Ordering depends on query provider, priorities, and concurrency. PostgreSQL-backed stores also require managing locking, indexes, serialization, backlog, and table bloat. For high-volume streams, a dedicated broker may fit better than turning a business DB into a high-throughput queue.

## 15. Testing Send/Receive in the Same Transaction

To prove a channel store's transaction works, do not merely assert that a handler was called. Inspect **records in the business DB** and **whether the message can still be received from the store** after the transaction finishes.

### Test A — Producer Rollback Leaves No Message

Suppose a `PollableChannel pendingReservations` uses `JdbcChannelMessageStore`, and in the test configuration **pollers are disabled** so message retrieval is controlled manually.

~~~java
@SpringBootTest
class DurableChannelProducerIT {
    @Autowired OrderCommandService service;
    @Autowired JdbcTemplate jdbc;

    @Autowired
    @Qualifier("pendingReservations")
    PollableChannel queue;

    @Test
    void rollbackRemovesBothOrderAndQueuedMessage() {
        String orderId = UUID.randomUUID().toString();
        String eventId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> service.placeThenFail(new CreateOrder(
                        eventId, orderId, "SKU-1", 2)));

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, orderId);

        assertEquals(0, rows);
        assertNull(queue.receive(0));
    }
}
~~~

**Test conditions:** `orders` and store schemas exist, the DB is empty or uses an isolated queue/group ID for this test, and no competing poller/worker consumes concurrently. The test calls the service through its proxy so the annotation applies.

### Test B — Poller Rollback Keeps the Message Receivable

`TransactionTemplate` can simulate the exact semantics of a transactional poll:

~~~java
@SpringBootTest
class DurableChannelRollbackIT {
    @Autowired
    @Qualifier("pendingReservations")
    PollableChannel queue;
    @Autowired PlatformTransactionManager transactionManager;

    @Test
    void failedReceiveTransactionKeepsMessageAvailable() {
        String eventId = UUID.randomUUID().toString();
        ReserveInventory command = new ReserveInventory(
                eventId, "ORDER-TEST-1", "SKU-1", 1);
        queue.send(MessageBuilder.withPayload(command).build());

        TransactionTemplate tx = new TransactionTemplate(transactionManager);

        assertThrows(IllegalStateException.class,
                () -> tx.executeWithoutResult(status -> {
                    Message<?> received = queue.receive(0);
                    assertNotNull(received);
                    throw new IllegalStateException("Simulated failure");
                }));

        Message<?> redelivered = tx.execute(status -> queue.receive(0));
        assertNotNull(redelivered);
        ReserveInventory payload = (ReserveInventory) redelivered.getPayload();
        assertEquals(eventId, payload.eventId());
    }
}
~~~

**Test limitation:** in this example, the second `receive(0)` executes **inside a transaction that commits when the callback finishes**, so it removes the message from the store upon commit. Run the test on an isolated queue with a compatible store and transaction manager. Different store types or polling with an executor may yield different outcomes.

### Test C — Proving Business DB and Store Share a Transaction

Open a transaction on the poller, receive a message, update inventory, and throw a `RuntimeException`. Observe after rollback:

1. Inventory is unchanged.
2. The message can still be received again from the store.
3. No audit/outbox row committed if they shared the transaction.

Repeat with a succeeding handler: the message is permanently removed from the store and inventory decreases exactly once.

## 16. Failure Injection Matrix and What to Observe

| Fault injection point | Source/channel | Verification expectation |
| --- | --- | --- |
| Producer writes `orders` then rolls back before commit | JDBC store same DB/TX | No business row or uncommitted message remains. |
| Producer writes `orders` then rolls back before commit | RAM `QueueChannel` | RAM message may still remain despite DB rollback. |
| Producer publishes to broker then DB rolls back | Broker (different resource) | Message may already reach broker; outbox/compensation needed. |
| Consumer receives from JDBC store then throws before commit | Transactional poller same DB | Business update rolls back; message is not permanently deleted. |
| Consumer receives from JDBC store without opening a transaction | JDBC store auto-commits dequeue | Downstream handler error can lose the message. |
| Consumer takes message then dispatches to executor | JDBC store + poller | Dequeue may commit before worker finishes. |
| Worker commits DB, broker loses ACK | JMS/AMQP/Kafka | Source may redeliver; consumer is idempotent. |
| Two workers concurrently receive same `eventId` | Distributed broker/store | Unique constraint / DB transaction prevents duplicate side effects. |
| Malformed schema message repeatedly rolls back | Durable queue | Bounded retries, DLQ/quarantine, and replay required. |
| One Splitter branch commits, another rolls back | Multiple resources/workers | No automatic cross-branch rollback; Saga/compensation needed. |

In these cases, log at least: `eventId`, `correlationId`, channel/source, transaction ID if supported, thread, commit/rollback status, delivery attempt, ACK/offset, and dedupe count. Never treat a `"send successful"` or `"received message"` log as an end-to-end result.

## 17. Operational and Performance Observability

| Metric | Meaning |
| --- | --- |
| Queue depth / pending store rows | Unprocessed messages; continuous growth signals slow or failing consumers. |
| Oldest message age | Maximum delay of pending work, often more revealing than count alone. |
| Commit/rollback ratio | Data quality and stability of handlers/transactional resources. |
| Retry/redelivery attempts | Failing sources, workers not ACKing, or poison tasks. |
| Duplicate suppressed count | Consumer received duplicates yet skipped side effects via idempotency. |
| Handler latency / DB lock wait | Overly long transactions or multiple pollers contending on rows. |
| DLQ/quarantine backlog | Work needing repair/controlled replay. |
| Connection pool utilization | Connection starvation from concurrency or `REQUIRES_NEW`/nested transactions. |

For JDBC-backed queues, pay attention to transaction isolation, message fetch queries, indexes, DB vacuum/cleanup, serialized payload sizes, and concurrent poller counts. For high-volume flows, evaluate a dedicated broker (JMS/AMQP/Kafka) or combine with an outbox instead of turning a business DB into a high-throughput queue by default.

## 18. Choosing an Architecture by Requirement

| Need | Suggested approach | Guarantees / limits |
| --- | --- | --- |
| Synchronous message passing between JDBC handlers on one DB | `DirectChannel` + outer `@Transactional` + handlers joining the same TX. | Rolls back DB operations on the same resource; does not roll back HTTP/email. |
| Internal handoff not needing crash recovery across restarts | RAM `QueueChannel` with capacity. | Not transactional and not durable under JDBC. |
| Persist messages with business DB before background processing | `QueueChannel` + `JdbcChannelMessageStore` on same DB/TX, transactional poller. | Requires managing schema, DB workload, concurrency, and error paths. |
| Multiple independent services/consumers with a dedicated broker | JMS/AMQP/Kafka + consumer transactions + idempotency. | DB and broker do not atomically commit together. |
| Emit business events reliably after DB commit | Transactional outbox + relay + idempotent downstream. | May publish duplicates; requires backlog monitoring and retries. |
| Receive event from broker, update DB, and emit downstream event | Inbox/deduplication + business update + outbox in same DB transaction. | Source-appropriate ACK, handling redeliveries and duplicates. |
| Multi-branch flow needing aggregated results | Correlation + persistent aggregator state + per-branch transactions with compensation. | Committed branches are not automatically rolled back by aggregator. |
| True cross-resource atomicity required | Verify XA/JTA/2PC when supported by all resources, or redesign architecture. | High operational complexity; never infer from separate local transaction managers. |

**Design principle:** first identify *which resource holds real data that must be protected*, then pick channels and transaction boundaries so operations on that resource commit/roll back together. Whenever a step crosses resources, threads, or processes, add **durable handoffs, idempotency, retries, and reconciliation**.

## 19. Hands-On Exercises

**Exercise 1 — Compare two QueueChannels.** Configure a RAM `QueueChannel(20)` and a queue backed by `JdbcChannelMessageStore`. Inside a `@Transactional` service, insert `orders`, send the event, and throw an exception. Observe DB data and remaining messages in each queue.

**Exercise 2 — Transactional receive.** With the JDBC-backed queue, configure a poller transaction and a handler updating inventory; inject an error right after the update. Prove the business row rolls back and the message is received again. Then remove the transaction from the poller and explain the difference.

**Exercise 3 — Switch to ExecutorChannel.** Insert an `ExecutorChannel` before the handler. Diagram threads and transactions of the poller/worker; trigger a worker error after the poller finishes and determine whether the message is recovered. Propose a durable handoff.

**Exercise 4 — Two datasources.** Put the business DB and channel store on separate datasources. List crash windows in the dual write and choose among XA/JTA, outbox, or idempotent retries as required.

**Exercise 5 — Poison message.** Send an undeserializable payload or negative quantity into the persistent queue. Design bounded retries, lossless quarantine, error alerts, and replay after fixing the payload.

**Exercise 6 — Router/Splitter/Aggregator.** A Gateway receives a request, a Splitter splits three items, and a Router sends them to durable queues. Each worker commits independently. Design correlation IDs, timeouts, deduplication, and compensation when one item fails.

### Self-Check Questions

**1. Is `DirectChannel` a transactional resource?** No. It dispatches synchronously; the resources used by handlers determine commit/rollback scope.

**2. Why doesn't a RAM `QueueChannel` roll back enqueues with JDBC?** Because an in-memory queue is not a JDBC resource managed by the transaction manager.

**3. When can `JdbcChannelMessageStore` help messages and business rows commit together?** When both use compatible datasources/transaction managers with one physical transaction wrapping store operations and business SQL.

**4. Why is a transactional poller needed when consuming from a JDBC-backed QueueChannel?** So receiving/removing and synchronous downstream processing share one transaction; on rollback, deleting the message from the store can be undone.

**5. Does using a different database for the store automatically create a global transaction?** No. You must configure an appropriate coordination mechanism or switch to outbox/inbox/idempotency.

**6. Why do retries still need a stable `eventId`?** One execution can commit on one resource yet fail/not ACK on another; the same message can reappear and cause duplicate side effects.

## 20. Pre-Production Checklist

- [ ] Document the transactional resource for every step: JDBC datasource, store, broker/session, external API.
- [ ] Know which channels are synchronous, which switch threads, and which store in memory vs. durable stores.
- [ ] Never treat `@Transactional` as a guarantee that all channels/brokers roll back together.
- [ ] For JDBC stores, use the schema/query provider matching your DB and version, managing `region`/group IDs cleanly.
- [ ] Configure the transaction manager on the right datasource; prove business rows and store operations truly share a physical transaction when atomicity is required.
- [ ] Wrap **receive and synchronous downstream processing** in a transactional poller when dequeue rollback is desired.
- [ ] Never hand off to an executor without a durable handoff or appropriate error-handling policy.
- [ ] Evaluate whether differing resources require XA/JTA or outbox/inbox; never implicitly assume distributed transactions.
- [ ] Keep `eventId` stable across retries/redeliveries; enforce unique constraints and idempotent consumers for critical side effects.
- [ ] Never swallow exceptions in a way that tricks transactions/ACKs into treating failed processing as success; check error channels and rollback rules.
- [ ] Have bounded retries/backoff, DLQ/quarantine, fix/replay procedures, and backlog monitoring.
- [ ] For Router/Splitter/Aggregator, design correlation, timeouts, durable state, and compensation.
- [ ] Test producer rollback, consumer rollback, crashes between commits, redelivery, and worker concurrency.
- [ ] Monitor queue depth, message age, DB locks, connection pools, retries, duplicates, DLQ, and end-to-end latency.

**Takeaway:** **MessageChannel determines how messages are transferred; transactional resources determine which operations can truly commit or roll back.** When a Spring Integration flow uses the same JDBC resource and transaction manager, a persistent channel store lets messages and business data share a transaction. Whenever a flow crosses RAM queues, executors, brokers, separate datasources, or external APIs, explicitly design durability, ACKs, redelivery, and idempotency rather than assuming transactions follow messages automatically.

### References

- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): distinguishing channels and configuring persistent QueueChannels.
- [Spring Integration — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html): query providers, schemas, concurrency, and characteristics of JDBC-backed channels.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): propagation modes and transaction scopes.

*Examples are written to illustrate architecture. When applying them, verify APIs, schemas, transaction managers, and adapters against the Spring Integration/Spring Framework versions in your project; verify with integration tests rather than treating an annotation or channel name as sufficient proof of atomicity.*
