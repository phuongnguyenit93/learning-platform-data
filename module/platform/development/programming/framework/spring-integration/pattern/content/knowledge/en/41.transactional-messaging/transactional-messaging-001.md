# Transactional Channel and Transaction Boundaries in Spring Integration

## 1. The Problem to Solve

In an integration system, a message often passes through multiple **Enterprise Integration Patterns (EIP)**: a Gateway receives the request, a Filter checks conditions, a Transformer normalizes data, a Router chooses a branch, and then a Service Activator writes to a database or sends to another system. The key question is: **when one step fails, which steps are rolled back and which messages can be reprocessed?**

For example, with an order:

1. The application receives an order placement command and validates it.
2. Saves the order to the database.
3. Publishes an `OrderCreated` event to the inventory service.
4. The inventory service updates stock, then sends the result back for aggregation.

If step 2 succeeds but step 3 fails, an order may exist without a corresponding event. If step 3 succeeds but the application crashes before recording that it was sent, a retry may produce duplicate events. **Transactional messaging** is designing the flow so that commit/rollback boundaries, message delivery acknowledgements, retries, and duplicate handling are all clearly defined.

In Spring Integration, a **Transactional Channel** should be understood as *a way to organize sending/receiving and processing messages in coordination with resource transactions*, rather than a property that automatically turns every `MessageChannel` into a cross-system transaction. A **Transaction boundary** is the starting and ending point of a specific transaction, usually tied to a `PlatformTransactionManager` and one or a group of resources configured to participate.

After this lesson, learners can:

- Identify which steps actually belong to the same transaction when a flow passes through a `DirectChannel`, `ExecutorChannel`, or polling channel.
- Place a transaction on the service calling the Gateway or on a polling endpoint and predict the outcome when a handler throws an exception.
- Distinguish between rolling back a database and returning a message taken from a queue or already acknowledged to a broker.
- Design retries, error channels, idempotency, and the transactional outbox for multi-system flows.
- Test commit, rollback, reprocessing, and failure scenarios at transaction boundaries.

## 2. Which Resources Does a Transaction Cover?

A typical transaction ensures that operations **participating in that same transaction** have a consistent outcome: either commit or rollback. For example, two SQL statements using the same `DataSource` and an appropriate transaction manager can commit/rollback together. Calling HTTP, sending an email, or publishing a message to a broker **does not automatically** join a JDBC transaction just because the operations are in the same Java method.

Let's separate three concepts:

| Concept | Meaning | What does it NOT guarantee? |
| --- | --- | --- |
| **Transaction boundary** | The scope of a transaction, with a start point, commit or rollback, and participating resources. | Does not automatically span across threads, processes, or brokers. |
| **Message delivery boundary** | The point where a message is handed off to another handler, queue, or another system. | A successful `send()` does not necessarily mean downstream business logic has committed. |
| **Acknowledgement boundary** | The point where the source/broker confirms the message has been consumed. | ACK does not equate to committing another database unless there is a coordination mechanism. |

In Spring's common imperative transaction flows, transaction state is bound to the **currently executing thread**. Metadata such as `MessageHeaders.ID`, `correlationId`, or `sequenceNumber` helps identify and correlate messages, but **does not carry a JDBC transaction** across to another thread or service.

### Two Diagrams to Identify Boundaries

**Synchronous flow: all handlers can be within the same JDBC transaction.**

~~~mermaid
flowchart LR
  subgraph TX["TX-A: same thread, same JDBC transaction"]
    A["OrderService @Transactional"] --> B["Messaging Gateway"]
    B --> C["DirectChannel"]
    C --> D["Filter / Transformer"]
    D --> E["Service Activator"]
    E --> F[("Orders DB")]
  end
  E -. "Exception propagates back" .-> A
~~~

If the DB write at `E` fails and the exception propagates to the `@Transactional` call, the transaction can roll back (according to rollback rules). `DirectChannel` does not store the message; after a rollback, **the caller or message source must decide on retry**.

**Asynchronous flow: handing off a message usually creates a new boundary.**

~~~mermaid
flowchart LR
  subgraph TX1["TX-A: receiving thread"]
    A["Gateway"] --> B["Transformer"]
    B --> C["Send to ExecutorChannel"]
  end
  C -. "handoff to another thread" .-> D["Worker receives message"]
  subgraph TX2["TX-B if worker opens its own transaction"]
    D --> E["Service Activator"]
    E --> F[("Orders DB")]
  end
~~~

`TX-A` does not automatically propagate into the worker. If the worker uses `@Transactional` or a transactional poller, that is **another transaction**. Successful completion of the upstream send call is not proof that the worker has finished processing.

## 3. Transactional Behavior by Channel Type

| Spring Integration Component | Processing Behavior | Transaction Consequence |
| --- | --- | --- |
| `DirectChannel` | Dispatcher invokes subscribers **synchronously** on the sender's thread. | Handlers can use the transaction already opened by the caller; exceptions usually propagate back immediately. |
| `PublishSubscribeChannel` **without** a configured executor | Broadcasts to subscribers on the synchronous calling flow. | Handlers can share the same transaction if using the same resource; a failing branch only triggers a rollback if the error propagates out and rollback rules apply. |
| `ExecutorChannel` | Delegates work to a `TaskExecutor`, usually on another thread. | The caller's thread-bound transaction is not automatically propagated to the handler; a separate boundary is needed. |
| In-memory `QueueChannel` | `send` places the message into a queue; a poller retrieves it later. | The default queue is non-persistent and does not automatically join a JDBC transaction; a DB rollback does not automatically put the message back into the queue. |
| Polling endpoint | Periodically receives messages from a `PollableChannel` or polling source. | A transactional advice/poller can wrap the poll and synchronous downstream processing. You must verify whether the **source** participates in that transaction. |
| Queue with a suitable persistent `MessageStore` | Stores messages in a transactional storage system. | Can coordinate taking the message and writing business data in the same DB transaction if the store, business repository, datasource, and transaction manager are compatibly configured. |
| JMS/AMQP/Kafka adapter | Receives or sends messages via a broker with its own ACK/transaction mechanism. | Depends on the adapter, container, ACK mode, and transaction manager; a broker transaction is not implicitly a DB transaction. |

**Practical rule:** identify the *message source*, *channel type*, *execution thread*, *message storage*, *transaction manager*, and *ACK point*. Only then conclude whether a failure will undo work or redeliver the message.

### Quick Flow Check

Suppose `Gateway → DirectChannel → Filter → Transformer → Service Activator → JDBC`, with the service calling the Gateway annotated with `@Transactional`:

- A Filter rejecting by returning `null` or dropping a message per normal logic can finish processing **successfully**, so the DB transaction may commit. "Message filtered out" is not necessarily a transaction error.
- A Transformer throws a `RuntimeException` and the error propagates to the service: the JDBC transaction usually rolls back.
- A Service Activator catches the exception and only logs it without rethrowing: the transaction interceptor may treat the call as successful and commit.
- Adding an `ExecutorChannel` before the JDBC handler: the handler runs on a different thread; the transaction of the service calling the Gateway does not cover the write inside the worker.
- A Router forwards to a remote service: the receiving service's transaction must be designed independently; sharing a `correlationId` does not create a distributed transaction.

## 4. Example 1 — One Transaction Covering Gateway and DirectChannel

This example uses Spring Boot, Spring Integration Java DSL, and Spring JDBC. Suppose the application has configured a `DataSource` and `PlatformTransactionManager` for the following table:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);
~~~

Declare the message, Gateway, and synchronous integration flow:

~~~java
record OrderCommand(String orderId, BigDecimal amount) {}

@MessagingGateway(defaultRequestChannel = "ordersInput")
interface OrderGateway {
    void submit(OrderCommand command);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderIntegrationConfig {
    @Bean
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderFlow(OrderWriter writer) {
        return IntegrationFlow.from("ordersInput")
                .handle(writer, "insert")
                .get();
    }
}

@Component
class OrderWriter {
    private final JdbcTemplate jdbc;

    OrderWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(OrderCommand command) {
        jdbc.update(
                "INSERT INTO orders (order_id, amount) VALUES (?, ?)",
                command.orderId(), command.amount());
    }
}
~~~

`@MessagingGateway` creates a strongly-typed entry point, `DirectChannel` delivers the message on the same thread, and `.handle(writer, "insert")` invokes the Spring bean's method. Open the transaction at the **application service** calling the Gateway:

~~~java
@Service
class OrderFacade {
    private final OrderGateway gateway;

    OrderFacade(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @Transactional
    public void submit(OrderCommand command) {
        gateway.submit(command);
    }

    // Used in tests to prove INSERT will roll back.
    @Transactional
    public void submitThenFail(OrderCommand command) {
        gateway.submit(command);
        throw new IllegalStateException("Simulated failure");
    }
}
~~~

**Lifecycle of a `facade.submit(command)` call from outside the Spring bean:**

1. The Spring transaction interceptor starts a DB transaction before running `submit`.
2. The Gateway sends the message to `ordersInput`.
3. `DirectChannel` invokes the handler on the same thread. `JdbcTemplate` uses the connection already enlisted in the transaction.
4. When the call returns normally, the interceptor commits the transaction; if an error matching the rollback rules escapes, the interceptor rolls back.

With `submitThenFail`, the `INSERT`ed record will be rolled back even though the SQL statement executed *before* the exception occurred. Conversely, when using an `ExecutorChannel` between the Gateway and the handler, `submitThenFail` may roll back the caller's transaction while the worker's work has already committed or will commit in another transaction.

Notes:

- Spring's `@Transactional` rolls back by default on `RuntimeException` and `Error`; checked exceptions require configuring `rollbackFor` if rollback is desired. This rule must be evaluated alongside the actual transaction settings.
- The `@Transactional` method must be invoked through the appropriate proxy/interceptor. Internal self-calls like `this.submit(...)` normally bypass the Spring proxy's transaction advice.
- If there are multiple transaction managers, specify the manager corresponding to the `DataSource` in use; if JDBC steps use different datasources, do not assume they share the same transaction.
- A successful DB write inside a handler is not yet a **commit**: the commit happens when the transaction boundary finishes successfully.

### When Do You Need a Transaction on the Handler?

If the Gateway is called from a place **without** a transaction and the handler needs to protect its own DB operation, `@Transactional` can be placed on a dedicated processing Spring service. With a synchronous `DirectChannel`, the transaction opens at that service. Understand that the transaction then covers only the processing inside the handler; earlier steps have already completed outside the handler's boundary.

## 5. Example 2 — Transaction Starting at the Poller

Polling is often suitable when pulling work from a queue or message store. A transactional poller can be declared as follows (imports and datasource configuration omitted):

~~~java
@Bean
QueueChannel workQueue() {
    return new QueueChannel(100);
}

@Bean
IntegrationFlow workerFlow(
        OrderWriter writer,
        PlatformTransactionManager transactionManager) {
    return IntegrationFlow.from(
                    "workQueue",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(transactionManager)))
            .handle(writer, "insert")
            .get();
}
~~~

In this example, the transactional advice opens a transaction for the polling task and synchronous downstream processing. Because of `maxMessagesPerPoll(1)`, each poll processes at most one message, making test scope and failure analysis easier to understand. If `OrderWriter.insert` throws an exception, the JDBC operation can roll back.

**Important pitfall:** `workQueue()` above is an **in-memory** `QueueChannel`. A JDBC transaction does not make taking an element from memory transactional. After an error, do not assume the message automatically returns to the queue. Nor should you rely on this example to guarantee zero message loss on process crash.

To achieve recoverability, you need a message source that supports the corresponding mechanism:

- **JDBC-backed message store:** use a persistent store with appropriate transactional semantics and configure taking the message and writing business data on the same `DataSource`/transaction manager when atomicity within *one* DB is needed. Verify locking, fetching, and deletion behavior for the specific store and channel type.
- **Broker:** use a supported listener container/adapter and transaction/ACK mode so failures can trigger broker redelivery. Check broker-specific settings such as prefetch, requeue, redelivery, and DLQ.
- **External API:** polling over HTTP or an API has no native rollback; checkpoints, durable cursors, retries, and idempotency are typically required.

`transactional(poller)` only has meaning for **resources that actually participate in the transaction**. It does not make an in-memory queue durable, does not carry the transaction across threads, and does not make a remote API capable of rolling back.

## 6. The Boundary Between Database and Message Broker

Suppose a handler needs to both write `orders` to PostgreSQL and publish `OrderCreated` to RabbitMQ/Kafka/JMS. This is the **dual write** problem:

| Operation order | Failure point | Possible state |
| --- | --- | --- |
| Commit DB then publish event | Process crashes after commit, before publish | Order exists, but the event is missing. |
| Publish event then commit DB | DB rolls back after broker has received event | An event exists for an uncommitted order. |
| Publish, then record "sent" in DB | Broker received it, but process crashes before marking | Retry may publish a duplicate. |

JDBC `@Transactional` only solves the JDBC part. A broker-side transaction (or consumer ACK mechanism) only solves what the broker supports. To coordinate **true atomic commit across multiple resources**, you must evaluate XA/JTA, adapter, driver, and broker capabilities; cost and support depend on infrastructure. Do not assume Spring Integration commits these resources together simply because they are inside one IntegrationFlow.

### Transactional Outbox: A Common Option for Dual Writes

To avoid the case where **the DB commits but the event is lost**, write business data and an outbox record in the **same DB transaction**:

~~~mermaid
flowchart LR
  subgraph DBTX["DB Transaction: commit or rollback together"]
    A["Save Orders"] --> B["Save OutboxEvent"]
  end
  B --> C[("Outbox table")]
  C --> D["Outbox publisher / poller"]
  D --> E["Message broker"]
  E --> F["Idempotent consumer"]
~~~

~~~java
@Transactional
public void placeOrder(OrderCommand command) {
    ordersRepository.insert(command);
    outboxRepository.insert(
            command.orderId(),
            "OrderCreated",
            serializeEvent(command));
}
~~~

The publisher reads unsent outbox records, publishes them to the broker, and then marks them as sent using an appropriate strategy. If the publisher crashes after the broker receives the message but before marking it, the record may be republished. Therefore, an outbox typically aims for **at-least-once delivery** and requires an **idempotent** consumer (e.g., storing processed `eventId`s, using a unique constraint, or performing a guarded status update).

The outbox provides atomicity between **orders** and **outbox** within the same DB; it **does not** create a distributed transaction spanning the DB and the broker. This is why both replayability and duplicate prevention are needed.

### Consumer Transactions and ACK

A consumer can follow this sequence:

1. Receive the message from the broker, retaining delivery/offset metadata.
2. Start a DB transaction and process the message (check idempotency, update business state).
3. Commit the DB.
4. ACK/commit the offset according to the broker and adapter mechanism.

If the consumer crashes between step 3 and step 4, the broker may redeliver the message even though the DB has committed. **Redelivery is a normal scenario that must be tested**, and does not mean business logic is allowed to execute twice. With some brokers/adapters, ACK may be managed by the listener container and the exact ordering may differ from this illustration; always check the actual configuration.

## 7. Error Channel, Retry, and Rollback

Spring Integration supports error flows and retry strategies, but **how errors propagate** determines whether a transaction rolls back.

**Synchronous channels:** an exception from a `DirectChannel` handler normally returns to the sender. If the error escapes the `@Transactional` method and satisfies the rollback rules, the DB transaction rolls back.

**Asynchronous channels:** an exception in an executor, poller, or listener cannot simply propagate back through a Gateway call that has already returned. Depending on the endpoint, the error may be wrapped as an `ErrorMessage` sent to `errorChannel`, passed through a retry advice, or handled by a listener container. The transaction and ACK mechanism reside at the **consumer boundary**.

**Do not confuse "sent to errorChannel" with "rolled back":** if an error handler finishes handling the error and the flow returns normally, some configurations treat the work as successful. Conversely, throwing an error from an error flow can cause the poller/listener to roll back or trigger a retry depending on the endpoint. You must determine which endpoint catches the exception and what final outcome the transaction interceptor sees.

| Scenario | What to design / test |
| --- | --- |
| Temporary network or database error | Bounded retry with backoff, distinguishing transient errors from business errors. |
| Invalid data error | Reject/quarantine/DLQ with a clear reason, avoiding infinite retries. |
| Handler performed a side effect then timed out | Idempotency key and a way to look up the result before retrying. |
| Exception caught to log | Decide explicitly whether to rethrow to roll back or accept commit; logging alone does not roll back a transaction. |
| Retries exceeded maximum attempts | Persist error details and original message to durable storage/DLQ that can be operated on and replayed. |
| Failure after ACK or source commit | Define a compensation/reconciliation mechanism; do not assume the source will resend automatically. |

### Where Does Retry Live?

For synchronous operations within a DB transaction, retrying immediately inside a transaction that has already failed may be inappropriate if the transaction is marked `rollback-only` or the connection is broken. You typically need to place retry **outside a single execution that starts a fresh transaction** when retrying the entire unit of work. For broker consumers, retry/redelivery must be consistent with ACK and DLQ policies. Never use infinite retries to mask data errors or programming bugs.

Illustrative example:

~~~text
Receive message
  -> check idempotency key
  -> begin business transaction
  -> perform write / update
  -> commit transaction
  -> acknowledge delivery

Temporary failure -> retry / redelivery with backoff
Permanent failure -> durable error record or DLQ
Redelivery after prior commit -> detect duplicate and return safely
~~~

**The ordering of retry and transaction interceptors matters**: "one transaction per attempt" and "multiple attempts within one transaction" are not equivalent. The advice chain configuration must be inspected according to its actual execution order.

## 8. Combining Router, Splitter, Aggregator, and Correlation

Transactional boundaries are easily misunderstood in multi-branch flows:

~~~mermaid
flowchart LR
  A["Gateway"] --> B{"Router"}
  B --> C["Branch A: DirectChannel"]
  B --> D["Branch B: ExecutorChannel / broker"]
  C --> E["Handler A"]
  D --> F["Handler B"]
  E --> G["Aggregator"]
  F --> G
  G --> H["Aggregated result"]
~~~

- **Router** only decides the message's path. If it routes over synchronous channels on the same thread, subsequent steps *can* continue using the current transaction; if it routes to an executor/broker, the boundary changes.
- **Filter** dropping a message per business rules is usually a valid termination of that branch; if a rollback is desired, a corresponding error signal must be designed.
- **Transformer** can transform the payload and headers; preserving `correlationId` helps with tracking but does not share a transaction.
- **Splitter** produces multiple child messages. If messages are processed across multiple threads or processes, there is no default single local transaction spanning all branches.
- **Aggregator** uses `correlationId`, sequence/release strategies, and a message store to group results. The durability and transactionality of the message store determine recoverability of the aggregated state; all previous side effects cannot be automatically rolled back merely because the aggregator fails.
- **Gateway** makes it easy for clients to invoke a flow, but a synchronous return method only reflects **the steps that actually ran before returning**. An asynchronous branch may continue executing afterward.

For distributed processing, design each branch as an idempotent processing unit with persisted progress and its own retry/compensation mechanism. If a business process needs multiple recoverable steps that cannot share a single transaction, consider **Saga/compensating actions**. A "compensation" is a new business action to counteract an already-committed effect, **not a remote JDBC rollback**.

## 9. Choosing Boundaries Based on Business Goals

| Need | Suggested layout | Guarantees to verify |
| --- | --- | --- |
| Validate and write to one DB in a synchronous call | `@Transactional` on application service → Gateway → `DirectChannel` → JDBC handler. | Same datasource/transaction manager; exception propagation; rollback rules. |
| Background order processing worker | Durable queue/broker → transactional consumer/poller → handler. | Source transaction, ACK/redelivery, timeout, idempotency, and DLQ. |
| Update business data and emit an event in one DB | Write business row + outbox row in the same DB transaction; independent publisher. | Outbox scan/publish, retry, unique event ID, and idempotent consumer. |
| Multiple parallel branches needing aggregation | Splitter/Router → async branches → Aggregator persistent state. | Correlation, timeout, state persistence, late arrivals, duplicates, and compensation. |
| Call an HTTP API from a transactional handler | Bound call duration and use idempotency/compensation if needed. | Remote calls do not roll back with JDBC; avoid holding DB locks long during network calls. |

A long transaction wrapping multiple network calls easily holds DB connections/locks too long, increasing contention and making failures harder to recover from. Boundaries are usually more effective when small, clear about data ownership, and equipped with mechanisms to continue processing after commit.

## 10. Test Behavior, Not Just the Happy Path

### Testing Synchronous Rollback

With the `OrderFacade` configuration in section 4, you can use the following integration test (assuming Spring Boot, JUnit Jupiter, `JdbcTemplate`, and the test schema are ready):

~~~java
@SpringBootTest
class OrderTransactionIT {
    @Autowired OrderFacade facade;
    @Autowired JdbcTemplate jdbc;

    @Test
    void rollbackWhenCallerFailsAfterInsert() {
        String id = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> facade.submitThenFail(
                        new OrderCommand(id, new BigDecimal("125.00"))));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, id);
        assertEquals(0, count);
    }

    @Test
    void commitWhenFlowCompletesNormally() {
        String id = UUID.randomUUID().toString();
        facade.submit(new OrderCommand(id, new BigDecimal("125.00")));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, id);
        assertEquals(1, count);
    }
}
~~~

Do not annotate the test itself with `@Transactional` if that causes the result to be affected by an outer test transaction and masks the commit/rollback behavior of the application service. The test must call the Spring-proxied bean, query persisted state **after** the call returns, and use unique IDs to avoid colliding with other tests' data.

### Failure Matrix to Include in Hands-On Practice

| Scenario | Expected observation |
| --- | --- |
| Handler on `DirectChannel` writes SQL then throws an error | No committed record if in the same transaction and the exception triggers rollback. |
| Switch handler to `ExecutorChannel` | Caller transaction does not cover the worker; verify via DB state and worker error handling. |
| Poller takes from in-memory `QueueChannel` and handler fails | DB rollback may occur, but do not assume the message is put back into the queue. |
| Broker redelivers message after DB commit | Idempotent handler does not record the business effect twice. |
| Outbox publish succeeds but fails before marking sent | May be republished; receiver handles duplicates safely. |
| Filter drops message without throwing | Flow ends per filter logic; do not assume a transaction rollback. |
| Splitter creates multiple branches; one branch fails | Verify per-branch state, aggregator timeout, retry, and compensation. |

For clear observability, log `messageId`, `correlationId`, business identifier (`orderId`), attempt number, channel/endpoint, start timestamp and processing outcome, along with commit/rollback/ACK events where possible. Do not log sensitive information from payloads. Use metrics for retry counts, redeliveries, DLQ, and processing latency instead of merely logging “send success”.

## 11. Common Design Mistakes

1. **Assuming `DirectChannel` creates a transaction by itself.** A synchronous channel only preserves the call stack/thread; an application service, handler, poller, or interceptor must actually open the transaction.
2. **Assuming `@Transactional` travels with message headers.** When crossing threads/processes, define a separate consumer boundary.
3. **Assuming DB rollback equals queue rollback.** In-memory queues and external brokers have their own handling mechanisms; rollback only affects resources participating in the transaction.
4. **Assuming a successful `send()` means business completion.** With async processing, success may only mean buffered or handed off to an executor.
5. **Swallowing exceptions and expecting the transaction to roll back.** If the method returns normally and the transaction is not marked rollback-only, data may commit.
6. **Relying on "exactly once" as an absolute system-wide guarantee.** Guarantees differ across specific brokers and transactions; at the DB–broker boundary you still must evaluate duplicates, ACK, and recovery.
7. **Using correlation as a transaction lock.** Correlation serves message grouping and business tracking, whereas transactions are managed by resources and transaction managers.

## 12. Hands-On Exercises

**Exercise 1 — Draw the transaction boundary.** Given the flow `Gateway → DirectChannel → Transformer → ExecutorChannel → JDBC Handler` and a `@Transactional` service method calling the Gateway, draw the two threads and mark where the caller's transaction ends. If the worker writes to the DB successfully and then the caller throws an error, what data may still persist?

**Exercise 2 — Safe reprocessing.** A consumer receives `OrderCreated(eventId, orderId)` and updates inventory. The DB commits, but the consumer crashes before ACK. Propose a table storing processed `eventId`s with a unique constraint so redelivery does not deduct inventory a second time. Test receiving the same message twice.

**Exercise 3 — Outbox and Aggregator.** Design a flow emitting events from an order creation transaction; two asynchronous consumers handle inventory and payment; an aggregator combines status by `orderId`. Clearly specify where the outbox is stored, where commit/ACK happens, branch timeouts, idempotency keys, and how to handle payment failure after inventory has been reserved.

### Self-Assessment Questions

**1. Why is `DirectChannel` usually easy to use with `@Transactional`?** Because the handler runs synchronously on the same thread, allowing it to join the caller's existing transaction if compatible resources are used; the channel itself does not open a transaction.

**2. Does adding an `ExecutorChannel` automatically pass the caller's transaction to the worker?** No. The worker needs its own transaction and appropriate error reporting/processing guarantees.

**3. Does placing `Pollers...transactional(manager)` on an in-memory `QueueChannel` guarantee no message loss?** Not yet. It wraps participating resources in a transaction, but an in-memory queue does not guarantee durable persistence or transactional rollback of the dequeue.

**4. Why does an outbox still need idempotency?** The publisher can finish sending and then crash before marking the row as sent, resulting in republishing the same event.

**5. When must you inspect the error channel to determine rollback?** When an exception can be converted into an `ErrorMessage` or handled by a handler; you must check whether the error actually propagates to the transaction boundary.

## 13. Pre-Production Checklist

- [ ] Clearly identify who opens the transaction, when it commits/rolls back, and which resources the transaction manager manages.
- [ ] Diagram thread/process handoff points and where new consumer transactions begin.
- [ ] Document message store/queue durability and redelivery mechanisms on process crash.
- [ ] Define ACK/offset commit behavior and reactions to success, transient failure, or permanent failure.
- [ ] Choose an idempotency key and unique constraint or business state check to prevent duplicate processing.
- [ ] Use an outbox or suitable mechanism when DB changes must be synchronized with event publishing.
- [ ] Configure bounded retries, backoff, DLQ, and a procedure to replay failed messages.
- [ ] Test failures before/after DB commit, before/after broker ACK, across parallel branches, and on service restart.
- [ ] Monitor correlation, retry counts, duplicates, backlog, and processing latency without assuming correlation equals transaction.

**Takeaway:** Spring Integration helps compose EIP steps loosely and extensibly, but transactions only protect operations genuinely inside the boundary and corresponding resources. Flow reliability also depends on message storage, redelivery, error handling, and business idempotency.
