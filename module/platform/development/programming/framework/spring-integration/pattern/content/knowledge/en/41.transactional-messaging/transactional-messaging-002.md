# Message Send in a Transaction with Spring Integration

## 1. Why Does the Timing of Sending a Message Matter?

In **Spring Integration**, a system is composed of **Enterprise Integration Patterns (EIP)**: a Gateway receives a request, a Filter checks conditions, a Transformer converts the payload, a Router selects a branch, a Splitter splits work, and an Aggregator combines results. Each step can exchange data through a `MessageChannel` and operate synchronously or asynchronously.

Consider the order processing case:

1. Write the order to the `orders` table.
2. Send an `OrderCreated` message to the inventory service.
3. Commit the database transaction.

If at step 2, the broker or worker receives `OrderCreated` **before step 3 commits**, inventory might process an order whose creation transaction ultimately rolls back. Conversely, if you only send **after commit**, the application might crash between the two operations: the order exists, yet the event was never sent.

That is why we must distinguish:

- **Message send**: a call placing a message onto a specific channel or adapter.
- **Database commit**: the point at which the transaction's changes in the database become durable.
- **Delivery/acknowledgement**: the point at which the receiving system accepts or confirms having processed the message according to its protocol.

These three events **are not automatically one atomic operation**. This lesson focuses on *Message send in a transaction*: when to send, which transaction the send participates in, risks on rollback, and how to structure the flow to minimize loss or duplicate sending.

### Learning Objectives

After this lesson, you can:

- Explain the meaning of `MessageChannel.send()` when called inside a `@Transactional` method.
- Identify transaction boundaries as a message passes through a `DirectChannel`, `ExecutorChannel`, `QueueChannel`, message store, or outbound adapter.
- Choose between sending immediately inside a transaction, sending after commit, and the **transactional outbox**.
- Properly handle exceptions, retries, error channels, idempotency, correlation, and acknowledgements.
- Write tests proving data rollback in a synchronous flow and uncovering dual-write scenarios.

## 2. What Does a Successful `send()` Mean?

Spring Integration exchanges information via `Message<?>`, which contains a `payload` and `headers`. `MessageChannel` provides the method:

~~~java
boolean accepted = channel.send(message);
// Or channel.send(message, timeoutInMillis) if the channel supports timeout.
~~~

A `true` result means the channel **accepted the send according to its implementation contract**; it is not a universal guarantee that all downstream handlers have completed, all data has committed, or a remote consumer has ACKed.

For example:

| Channel or adapter | What can happen during send | What `send()` does not automatically guarantee |
| --- | --- | --- |
| `DirectChannel` | Dispatches the handler synchronously on the sender's thread. | That the database has committed if an outer transaction is still open; side effects on remote systems may not roll back. |
| `PublishSubscribeChannel` without an executor | Invokes subscribers synchronously in the publishing call flow. | That all subscribers have rollback mechanisms for external side effects or downstream async branches. |
| `ExecutorChannel` | Hands off the task to a `TaskExecutor`, typically on another thread. | That the worker handler has finished processing or participates in the sender's transaction. |
| In-memory `QueueChannel` | Enqueues the message for a poller to process later. | That the message survives process crashes; that dequeue rolls back with the database. |
| Channel using a **persistent message store** | Saves the message in a store that may support transactions. | That the store and business data necessarily share the same transaction; datasource/manager must be checked. |
| Outbound adapter to HTTP/JMS/AMQP/Kafka | Calls an API or producer according to adapter characteristics. | That the remote operation joins the caller's JDBC transaction; that a broker ACK equals a DB commit. |

A channel can accept a message and then fail downstream **at a later time**, especially with executors or queues. At the same time, a synchronous handler can throw an exception inside the `send()` call itself. Therefore, you must observe **error propagation paths** alongside **transaction boundaries**, instead of just logging `"send success"`.

### Three Questions You Always Need to Answer

1. **Who holds the transaction?** An application service, poller, listener container, or transaction interceptor?
2. **Where is the message processed?** On the same thread, in an internal queue, on a worker, or in another broker/process?
3. **Which resources participate in the transaction?** The same JDBC datasource, a persistent message store, a JMS session, or a separate broker-side transaction?

Standard transactions in imperative Spring applications are bound to threads. `correlationId`, `messageId`, and business headers **do not propagate a JDBC transaction** from one thread to another.

## 3. Timeline View: Send Before Commit vs. Send After Commit

### Case A — Sending an external message **before** DB commit

~~~mermaid
sequenceDiagram
    participant App as Order service
    participant DB as Orders DB
    participant Broker as Broker / external service
    App->>DB: BEGIN + INSERT order
    App->>Broker: send OrderCreated
    Broker-->>App: Accepted
    Note over App,DB: Business error occurs afterward
    App->>DB: ROLLBACK
    Note over Broker: Message may already be seen/processed
~~~

A message that has reached a broker, succeeded in an HTTP call, or produced side effects outside the database **does not disappear** when the DB rolls back. A consumer may see the event without seeing the data because the order-creation transaction never committed.

### Case B — Sending only **after** DB commit

~~~mermaid
sequenceDiagram
    participant App as Order service
    participant DB as Orders DB
    participant Broker as Broker
    App->>DB: BEGIN + INSERT order
    App->>DB: COMMIT
    Note over App: May crash here
    App->>Broker: send OrderCreated
    Broker-->>App: Accepted
~~~

Sending after commit avoids actively publishing events for rolled-back transactions, but creates an **event-loss window** if the process stops before sending. If the broker receives the message successfully yet the process fails to record the send result, a retry may emit **duplicates**.

### Case C — Storing the message **in the same** transaction as business data

~~~mermaid
flowchart LR
  subgraph TX["Database TX: atomic within a single DB"]
    A["INSERT orders"] --> B["INSERT outbox_events"]
  end
  B --> C[("Committed outbox")]
  C --> D["Post-commit publisher"]
  D --> E["Broker / consumer"]
~~~

Here, the transaction guarantees that *the order and the record to be sent* commit together or roll back together. An independent publisher reads the committed outbox and sends. This is the **transactional outbox**. It reduces the risk of losing events, though it requires retries and idempotency because the publisher may send duplicates.

## 4. When `send()` Is Inside a `@Transactional` Method

The example below simulates sending a message to a **synchronous handler that also writes to the same database**. This is a case where atomicity can be achieved within a single JDBC transaction without distributed transactions.

Assume the schema:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(20) NOT NULL
);

CREATE TABLE order_audit (
    event_id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(40) NOT NULL
);
~~~

Declare the message and integration flow, with standard imports omitted:

~~~java
record OrderCreated(String eventId, String orderId) {}

@Configuration
@EnableIntegration
class OrderMessageConfig {
    @Bean("auditEvents")
    MessageChannel auditEvents() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow auditFlow(OrderAuditWriter writer) {
        return IntegrationFlow.from("auditEvents")
                .handle(writer, "record")
                .get();
    }
}

@Component
class OrderAuditWriter {
    private final JdbcTemplate jdbc;

    OrderAuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void record(OrderCreated event) {
        jdbc.update("""
                INSERT INTO order_audit(event_id, order_id, event_type)
                VALUES (?, ?, ?)
                """, event.eventId(), event.orderId(), "OrderCreated");
    }
}
~~~

The application service opens a transaction and then uses `MessageChannel.send()`:

~~~java
@Service
class CheckoutService {
    private final JdbcTemplate jdbc;
    private final MessageChannel auditEvents;

    CheckoutService(
            JdbcTemplate jdbc,
            @Qualifier("auditEvents") MessageChannel auditEvents) {
        this.jdbc = jdbc;
        this.auditEvents = auditEvents;
    }

    @Transactional
    public void createOrder(String orderId) {
        writeAndSend(orderId);
    }

    @Transactional
    public void createOrderThenFail(String orderId) {
        writeAndSend(orderId);
        throw new IllegalStateException("Simulated failure before commit");
    }

    private void writeAndSend(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "CREATED");

        OrderCreated event = new OrderCreated(
                UUID.randomUUID().toString(), orderId);
        Message<OrderCreated> message =
                MessageBuilder.withPayload(event).build();

        boolean accepted = auditEvents.send(message);
        if (!accepted) {
            throw new IllegalStateException("auditEvents rejected message");
        }
    }
}
~~~

**Execution path when `createOrder()` is called via the Spring transaction proxy:**

~~~mermaid
flowchart LR
  subgraph TX["One JDBC transaction — same thread"]
    A["CheckoutService @Transactional"] --> B["INSERT orders"]
    B --> C["auditEvents.send()"]
    C --> D["DirectChannel"]
    D --> E["OrderAuditWriter.record()"]
    E --> F["INSERT order_audit"]
  end
  F --> G{"Return to service"}
  G -->|"Success"| H["COMMIT both tables"]
  G -->|"RuntimeException"| I["ROLLBACK both tables"]
~~~

Because `DirectChannel` runs the handler on the sending thread, JDBC statements in `CheckoutService` and `OrderAuditWriter` can share the transaction opened by `@Transactional`. When `createOrderThenFail` throws `IllegalStateException`, the transaction normally rolls back **both** `INSERT` statements, even though `send()` previously returned `true`.

Conditions for this conclusion to hold:

- The call goes through the Spring proxy so `@Transactional` takes effect.
- The handler runs **synchronously** and does not hand off to an executor/broker mid-flow.
- Both JDBC operations use resources participating in the same appropriate transaction manager.
- The exception propagates to the interceptor, is not swallowed, and is not configured to commit.

By default, `@Transactional` rolls back when a `RuntimeException` or `Error` escapes. For checked exceptions, check rollback rules or configure `rollbackFor`. **`DirectChannel` does not open a transaction itself**; the transaction here is owned by the application service.

### Easily Confused Scenario: Calling an External API from the Handler

If you replace `OrderAuditWriter.record()` with a handler calling HTTP to send an email, the sent email **cannot roll back** along with JDBC. Even if the email is called synchronously on `DirectChannel`, only operations on resources participating in the transaction can be undone. Thread synchronicity is **different** from cross-resource atomicity.

## 5. Switching Channels Changes the Meaning of Send

Keep `CheckoutService` as-is, but replace `auditEvents` with a channel backed by an executor:

~~~java
@Bean("auditEvents")
MessageChannel auditEvents(TaskExecutor taskExecutor) {
    return new ExecutorChannel(taskExecutor);
}
~~~

An asynchronous `TaskExecutor` normally hands processing off to another thread. In that case:

1. `CheckoutService` opens transaction A and writes to `orders`.
2. `auditEvents.send()` hands the message off to a worker, after which the sender can proceed.
3. The worker executes `OrderAuditWriter`, but transaction A **is not automatically propagated** to the worker.
4. `CheckoutService` commits or rolls back A independently of whether the worker succeeds or fails.

If the worker handler needs a DB transaction, put `@Transactional` on the service called by the worker or configure an appropriate transaction advice on the consumer. That transaction is **B**, not transaction A. Some executors can run directly on the calling thread; always inspect the actual `TaskExecutor` configuration before assuming.

### Comparing Three Send Locations

| Configuration | When the send call finishes | Does sender DB rollback undo the message? |
| --- | --- | --- |
| `DirectChannel` → JDBC handler sharing the same DB transaction | The synchronous handler has finished running if no error occurred. | Can roll back **DB writes in the same transaction**; does not roll back external side effects. |
| `ExecutorChannel` → separate worker | Usually the task has been handed off to the executor. | Does not automatically undo work done by the worker; requires a worker transaction. |
| In-memory `QueueChannel` → poller | The message has usually entered the queue. | Does not automatically undo the in-memory enqueue or guarantee survival across process crashes. |

With a `PublishSubscribeChannel` that has no configured executor, subscribers are invoked synchronously. However, if a subscriber forwards to an `ExecutorChannel` or external adapter, that creates a new handoff point. To evaluate accurately, trace the **entire path**.

## 6. Deferring Send Until After Commit

When you do not want to emit an event for a rolled-back order, you can publish an **application event inside the transaction** and use an `AFTER_COMMIT` phase listener to send the message. For example:

~~~java
record OrderStored(String eventId, String orderId) {}

@Service
class OrderApplicationService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            JdbcTemplate jdbc,
            ApplicationEventPublisher events) {
        this.jdbc = jdbc;
        this.events = events;
    }

    @Transactional
    public void create(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "CREATED");

        events.publishEvent(
                new OrderStored(UUID.randomUUID().toString(), orderId));
    }
}

@Component
class SendAfterCommit {
    private final MessageChannel outboundEvents;

    SendAfterCommit(
            @Qualifier("outboundEvents") MessageChannel outboundEvents) {
        this.outboundEvents = outboundEvents;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderStored(OrderStored event) {
        boolean accepted = outboundEvents.send(
                MessageBuilder.withPayload(event).build());
        if (!accepted) {
            throw new IllegalStateException("Event send rejected");
        }
    }
}
~~~

Assume `outboundEvents` is wired to an appropriate outbound flow. Spring will invoke the listener after the transaction containing the `OrderStored` event **commits successfully**. By default, `@TransactionalEventListener` does not handle events published outside a transaction unless `fallbackExecution` is enabled.

**The real meaning of `AFTER_COMMIT`:**

- Does not send from the listener when the source transaction rolls back.
- When the listener runs, the source transaction **has already committed**; an exception during send **cannot roll back** the committed data.
- The application can crash after commit but before the listener sends, losing the event.
- If an external caller retries after an ambiguous error, the event can be sent twice; the receiver needs idempotency.
- If the listener needs to perform **additional DB writes** after commit, do not assume it still has an active committable transaction; it usually must open a new transaction, for instance via a service annotated with `@Transactional(propagation = REQUIRES_NEW)`.

Therefore, `AFTER_COMMIT` suits certain notifications without durable delivery requirements. For critical business messages requiring crash recovery, the **transactional outbox** is a stronger option.

### Does `BEFORE_COMMIT` Solve It Completely?

No. A `BEFORE_COMMIT` callback can throw an exception preventing the source transaction from committing, but if a message was already accepted by an external broker/API before the failure occurred, rolling back the DB still will not automatically retract that message. Changing the callback phase **does not create a cross-resource atomic transaction**.

## 7. Transactional Outbox: Saving the Intent to Send Alongside Business Data

The goal of an outbox is to guarantee that **every committed order-creation transaction has a durable event record for the system to publish**, and when the transaction rolls back, both the order and the unsent event roll back together.

### Minimal Schema

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload_json TEXT NOT NULL,
    delivery_status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

One JDBC transaction executes two SQL statements on the same datasource:

~~~java
@Service
class OrderCommandService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    OrderCommandService(JdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Transactional
    public void placeOrder(String orderId) throws JsonProcessingException {
        String eventId = UUID.randomUUID().toString();
        String payload = json.writeValueAsString(
                new OrderStored(eventId, orderId));

        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "CREATED");

        jdbc.update("""
                INSERT INTO outbox_events
                  (event_id, aggregate_id, event_type, payload_json, delivery_status)
                VALUES (?, ?, ?, ?, ?)
                """, eventId, orderId, "OrderCreated", payload, "PENDING");
    }
}
~~~

**Note on rollback rules:** `JsonProcessingException` is a checked exception. The code computes the payload before writing to the DB, but if a checked exception occurs in another step *after writing*, appropriate rollback rules must be defined, such as `@Transactional(rollbackFor = Exception.class)` when the business logic requires rolling back on all checked exceptions.

After the DB transaction commits, a relay/publisher reads `outbox_events` and sends `PENDING` records. The relay can be triggered by a polling flow in Spring Integration. In real deployments, you need to:

1. **Claim/lock** records to send so multiple workers do not process them concurrently without coordination; locks/leases or a database-appropriate strategy can be used.
2. **Publish** with a fixed `eventId`, correlation headers, and necessary version/schema metadata.
3. Only mark `SENT` after receiving a success signal according to the corresponding broker/adapter mechanism.
4. On timeout, crash, or uncertain outcome, allow retries. Never assume a previous send definitely failed.
5. Have the consumer store processed `eventId`s or apply idempotent business operations to prevent executing side effects twice.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as DB + Outbox
    participant Relay as Outbox relay
    participant Broker as Broker
    participant Consumer as Consumer
    API->>DB: BEGIN; INSERT order + outbox
    API->>DB: COMMIT both
    Relay->>DB: Claim pending event
    Relay->>Broker: Publish(eventId)
    Broker-->>Relay: Publish confirmation
    Note over Relay: May crash before marking SENT
    Relay->>DB: Mark SENT
    Broker->>Consumer: Deliver(eventId)
    Consumer->>Consumer: Check idempotency, apply once
~~~

**Limitation to remember:** an outbox **does not** create a transaction spanning the database and the broker. If the relay publishes successfully and crashes before marking as sent, it will republish. Thus delivery is typically organized around **at-least-once**, while business logic must guard against duplicates.

### Idempotent Consumer When Messages Are Redelivered

A common approach is to store processed event keys in the **same** transaction as the business update:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Pseudocode:

~~~text
onMessage(event):
  begin DB transaction
    if processed_events already contains event.eventId:
      commit; acknowledge; return

    insert processed_events(event.eventId)
    apply business update (e.g., reserve inventory)
  commit DB transaction
  acknowledge delivery
~~~

Checking and inserting the key must handle **race conditions** when multiple workers receive the same event concurrently: a unique constraint and appropriate conflict/duplicate handling logic are needed within the same transaction as the business update. If the DB commits but the consumer crashes before ACK, the broker may redeliver; next time the consumer detects `eventId` was already processed and skips the side effect. In practice, exact ACK/offset commit timing depends on the listener container, broker, and adapter configuration.

## 8. When Does a Send Truly Participate in a Transaction?

Do not apply a single conclusion across all channel types. The minimum condition for two operations to commit/roll back together is **sharing the same transactional resource or having a configured transaction coordination mechanism**.

| Case | Achievable atomicity scope | What to verify |
| --- | --- | --- |
| `DirectChannel` to two JDBC handlers on the same datasource | JDBC operations share a transaction if both join the caller's transaction. | Same thread, `@Transactional` proxy, transaction manager, exception propagation. |
| Persistent channel using a transactional JDBC message store with the business DB | Saving the message to the store and writing business rows can share the DB transaction. | Store/channel type, datasource, transaction manager, actual enqueue/dequeue operations. |
| In-memory `QueueChannel` | No database transaction for the in-memory queue itself. | Message loss on restart, post-rollback behavior, retries, and durability. |
| Send to a broker with local transactions | Supported broker operations within the broker transaction. | Session/container/producer transaction, commit and ACK; whether DB participates. |
| JDBC DB + JMS/Kafka/AMQP | Usually **two transaction scopes** unless a platform-supported coordination mechanism is configured. | XA/JTA if supported, limits of transaction synchronization, commit order, and failure windows. |
| Send HTTP or email | Side effects in an external system. | Idempotency key, timeout, status lookup capability, and compensation. |

**Transaction synchronization** (such as post-commit callbacks) only determines *when work executes* relative to an active transaction. It does not mean every receiving system becomes a resource of that transaction. Some adapters support specific transaction integrations; read the documentation and test against your actual version/driver/broker before promising atomicity.

### Transaction at a Polling Endpoint

In a polling flow, the transaction usually begins at the **consumer**, not where `send()` was originally called. Example boundary placement:

~~~java
@Bean
IntegrationFlow pollingFlow(
        PlatformTransactionManager txManager,
        OrderAuditWriter auditWriter) {
    return IntegrationFlow.from(
                    "workQueue",
                    e -> e.poller(
                            Pollers.fixedDelay(1000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(txManager)))
            .handle(auditWriter, "record")
            .get();
}
~~~

Assume the `workQueue` bean is configured with the appropriate `PollableChannel` type. A transactional poller can wrap the poll and synchronous downstream processing. But if `workQueue` is an in-memory queue, a JDBC rollback **does not put the message back into the queue**. Durable redelivery requires a message source with matching fetch/ACK/transaction support.

## 9. Failed Sends: Exceptions, Retries, and Error Channels

### Failures in Synchronous Calls

With `DirectChannel`, exceptions from handlers usually propagate back through `send()`. If the error is a `RuntimeException` escaping the `@Transactional` method, the interceptor can roll back. If the application catches the error just to log it and returns normally, the transaction can commit even though the send step failed.

Example to avoid:

~~~java
@Transactional
public void createWithHiddenFailure(String orderId) {
    repository.insert(orderId);
    try {
        outboundChannel.send(createMessage(orderId));
    } catch (Exception ex) {
        log.warn("Unable to send event", ex);
        // Method still returns normally: transaction may COMMIT.
    }
}
~~~

If business rules require all-or-nothing **within a DB transaction**, rethrow the error and verify rollback policies. If the outside target is a broker/API, throwing and rolling back the DB **still cannot retract** messages already sent successfully earlier; choose an outbox or suitable compensation approach.

### Asynchronous Failures

With `ExecutorChannel`, polling endpoints, or remote-sending adapters, exceptions can occur **after the initial send method has already returned**. Errors may be routed to `errorChannel` as an `ErrorMessage`, handled by a listener container, or trigger retry advice depending on the endpoint.

Do not treat “the error flow received the error” as proof that the DB rolled back. The transaction interceptor decides solely based on the return outcome and exceptions it observes, together with rollback rules. When an error handler consumes the error without rethrowing, many configurations treat processing as complete.

### Choosing Where to Place Retries

| Where to retry? | Reasonable when | Risks to control |
| --- | --- | --- |
| Retry the sender's `send()` call | Channel is temporarily unavailable and the send outcome is clear. | A prior attempt may have succeeded despite caller timeout; requires a fixed ID. |
| Retry the entire business operation | You want to re-run a unit of work with a fresh transaction. | Each attempt must have a proper boundary; avoid reusing a rollback-only transaction. |
| Outbox relay retry | The event is durably persisted; broker/API fails transiently. | Duplicate publishing if ACK is unclear; idempotent consumer. |
| Broker redelivery or listener retry | Consumer fails or has not ACKed. | Configure retry/backoff, poison messages, DLQ, and deduplication. |

Do not infinitely retry messages with invalid schemas or business rule violations. For unprocessable messages, store the error and reference payload in a **dead-letter queue (DLQ)** or durable error store with a remediation/replay process.

## 10. Coordinating Router, Splitter, Aggregator, and Gateway

One send can fan out into multiple branches. You must analyze the boundary of **each branch**:

~~~mermaid
flowchart LR
  G["Gateway"] --> T["Transformer"]
  T --> R{"Router"}
  R --> F["Filter: branch A"]
  R --> S["Splitter: branch B"]
  F --> DC["DirectChannel"]
  S --> EC["ExecutorChannel"]
  DC --> A["Handler A: JDBC"]
  EC --> B["Workers B"]
  B --> AG["Aggregator by orderId"]
  A --> AG
~~~

- **Gateway** is a typed entry point. If the flow branches asynchronously, the Gateway returning does not imply all branches have committed.
- **Filter** validly dropping a message based on a condition usually terminates the branch normally. It does not automatically trigger a rollback just because a message was filtered out.
- **Transformer** alters the payload; preserving `eventId` and essential headers aids deduplication, but does not move the transaction.
- **Router** selects channels; a branch over synchronous `DirectChannel` can stay in the caller's transaction, while a branch over an executor/broker has its own boundary.
- **Splitter** creates child messages. Child messages processed across multiple threads or processes generally need separate transactions and retry plans.
- **Aggregator** uses `correlationId`, sequence/release strategies, and a message store to collect results; persistence, timeouts, duplicates, and readiness criteria must be defined. An aggregator cannot automatically roll back side effects already committed in other branches.

**Distinguish identifiers:** `messageId` typically identifies a specific message, `correlationId` groups messages belonging to the same workflow, and a business `eventId` prevents duplicate processing. Define a stable `eventId` across retries of **the same event**, rather than generating a new ID on every retry.

## 11. Testing Actual Send and Commit Scenarios

### Integration Test for `DirectChannel`

Using `CheckoutService` and the two tables from section 4:

~~~java
@SpringBootTest
class TransactionalSendIT {
    @Autowired CheckoutService checkoutService;
    @Autowired JdbcTemplate jdbc;

    @Test
    void successCommitsBothOrderAndAudit() {
        String orderId = UUID.randomUUID().toString();

        checkoutService.createOrder(orderId);

        assertEquals(1, count("orders", orderId));
        assertEquals(1, count("order_audit", orderId));
    }

    @Test
    void rollbackRemovesBothOrderAndAudit() {
        String orderId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> checkoutService.createOrderThenFail(orderId));

        assertEquals(0, count("orders", orderId));
        assertEquals(0, count("order_audit", orderId));
    }

    private int count(String table, String orderId) {
        String query = switch (table) {
            case "orders" ->
                    "SELECT COUNT(*) FROM orders WHERE order_id = ?";
            case "order_audit" ->
                    "SELECT COUNT(*) FROM order_audit WHERE order_id = ?";
            default -> throw new IllegalArgumentException(table);
        };
        return jdbc.queryForObject(query, Integer.class, orderId);
    }
}
~~~

Do not put `@Transactional` on the test itself if that causes a test transaction to wrap the service and hide actual commit/rollback behavior. Use a unique ID per case and inspect the data **after** the method returns.

### Failure Injection Matrix for Message Sending Systems

| Fault injection point | What to observe | Desired design outcome |
| --- | --- | --- |
| Synchronous JDBC handler throws error | Do both tables roll back together? | No committed rows remain if in the same DB transaction. |
| DB rolls back **after** outbound API accepted the message | Does the consumer see an event for a non-existent order? | Exposes pre-commit send risk; switch to outbox if guarantees are needed. |
| Process crashes after DB commit, before `AFTER_COMMIT` send | Is there a mechanism to replay the event? | If durability is required, the outbox record remains for the relay to process. |
| Broker receives event, relay crashes before `mark SENT` | Is the event resent? | May repeat; idempotent consumer keeps the business effect exactly once. |
| `ExecutorChannel` handler throws error | Has the sender already returned; where does the error go? | Independent worker transaction and error handling; logs/metrics/tracing exist. |
| In-memory queue loses messages after restart | Can messages be recovered? | Do not rely on in-memory queues for durable delivery. |
| Consumer commits DB then loses connection before ACK | Does redelivery cause duplicate side effects? | Deduplicate via eventId and unique constraint. |
| Filter drops message or Router picks a branch with no handler | How does the flow handle the error or terminate? | Clear business policy; do not assume every "no further send" is a rollback. |

Log and emit metrics with at least `orderId`, `eventId`, `correlationId`, endpoint/channel, send status, retry count, commit timestamp, and ACK status where possible. Avoid logging payloads containing sensitive data. Specifically, **a `"send accepted"` log cannot substitute for end-to-end measurement** from order creation to consumer completion.

## 12. Choosing the Right Sending Approach

| Need | Suitable implementation | Limitations to accept |
| --- | --- | --- |
| Call a synchronous handler writing to the same database in one use case | Open `@Transactional` on the service, send via `DirectChannel`, handler shares the DB transaction. | Atomic only for participating resources; excludes external APIs. |
| Only want to send lightweight notifications after DB commit | Application event + `@TransactionalEventListener(AFTER_COMMIT)`. | May lose notifications on process crash; unsuitable for durable delivery requirements. |
| Critical events must be sent after business data commits | Write outbox in the same DB transaction, relay sends after commit, idempotent consumer. | Requires operating pollers, retries, claim/locking, deduplication, and backlog monitoring. |
| Process messages asynchronously from a broker | Independent consumer transaction + appropriate ACK/redelivery. | May reprocess after timeout/crash; needs idempotency and DLQ. |
| Send to multiple systems not sharing transactional resources | Event-driven workflow and compensation/Saga if needed. | No default shared JDBC rollback; per-step progress management needed. |

The longer a transaction stretches across network calls, the longer locks and connections are held. For distributed business logic, prefer short local transactions, durable messages, and testable recovery mechanisms.

## 13. Hands-On Exercises

**Exercise 1 — Analyzing `send()` in a transaction.** Draw the timeline for `@Transactional service → INSERT orders → DirectChannel → JDBC handler → COMMIT`. Switch the channel to `ExecutorChannel` and identify which transaction manages the SQL statement in the worker. Explain the outcome if the caller rolls back after the worker has already written successfully.

**Exercise 2 — After commit is not safe enough.** Use `@TransactionalEventListener(AFTER_COMMIT)` to publish a message. Simulate a send failure or process crash immediately after commit. Identify why a callback alone cannot satisfy the requirement “every committed order has a replayable event”.

**Exercise 3 — Outbox and deduplication.** Implement an order creation feature saving `orders` and `outbox_events` in the same transaction. Create a relay reading `PENDING` records, simulate the broker receiving successfully while the relay fails to mark `SENT`. Re-run the relay and prove that a consumer using `processed_events(event_id)` does not deduct inventory twice.

**Exercise 4 — Multi-branch flow.** Design `Gateway → Router → Splitter → two ExecutorChannels → Aggregator`. Choose transaction boundaries, retries, and idempotency keys per branch; propose a plan when one branch fails to return a result before timeout.

### Self-Assessment Questions

**1. Does `channel.send(message)` returning `true` prove that DB data has committed?** No. It reflects the channel accepting the message per its own mechanism; the caller's transaction may still be open.

**2. Does `DirectChannel` make an external API join a JDBC transaction?** No. It enables synchronous processing on the same thread, but does not turn external side effects into JDBC transaction resources.

**3. Why can `AFTER_COMMIT` still lose events?** Because the DB commits before the callback sends; the application can crash in between with no durable record to recover from.

**4. What does an outbox solve, and what does it not solve?** It commits business data and the intent to send an event together in one DB; it does not guarantee atomic commit between the broker and DB, so duplicate publishing must be accepted and consumers must be made idempotent.

**5. What do you do when receiving a duplicate message after the consumer committed but before ACK?** Use a stable event identifier, check/insert the unique key in the same transaction as the business update, then ACK according to the adapter mechanism.

## 14. Pre-Production Checklist

- [ ] Clearly map where transactions begin and end across services, pollers, listeners, or handlers.
- [ ] Confirm whether channels run synchronously or cross threads/processes and the impact on errors/commits.
- [ ] Check what `send()` returns, when it throws exceptions, and when it merely hands off the message for later processing.
- [ ] Separate the states: send accepted, broker confirmed, consumer processed, and DB committed.
- [ ] Never treat an outbound send inside `@Transactional` as a guarantee of atomicity between DB and broker/API.
- [ ] For critical business events, write the outbox in the same transaction as the source data.
- [ ] Design the relay with claim/locking, retries, backoff, recoverability, and backlog monitoring.
- [ ] Use a stable `eventId` and an idempotent consumer to prevent duplicate side effects.
- [ ] Test crashes before/after commit, before/after publish, before/after ACK, and errors in async branches.
- [ ] Maintain an error channel/DLQ and procedures to handle and replay unrecoverable failed messages.

**Takeaway:** When speaking of “sending a message in a transaction”, specify **which resources the transaction protects** and **how far the message is actually delivered before commit**. Spring Integration helps organize and observe loosely coupled, extensible EIP flows; correctness under failure is determined by transaction boundaries, message durability, and retry/idempotency strategies.
