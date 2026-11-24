# Transactions with Brokers

In Spring Batch, a step can receive messages from a broker, process the data, and then send messages to another broker. The broker might be a JMS provider such as ActiveMQ/Artemis, Apache Kafka, or another messaging system. When a chunk both updates a database and acknowledges input messages or publishes output messages, the critical question is: do those operations commit or roll back together?

A Spring Batch transaction does not automatically cover every resource your code touches. A transaction manager manages a specific resource type or a specific transaction coordinator. Database transactions, JMS local transactions, and Kafka transactions have different scopes. If they do not participate together in a distributed transaction, failures between commit steps can result in lost messages, duplicate messages, or database state diverging from the broker.

The design must clearly define transaction boundaries, commit ordering, redelivery policy, idempotency, and recovery mechanisms. For many systems, transactional outbox/inbox is a more practical choice than trying to construct a distributed transaction across every resource.

## 1. What Is a Broker Transaction?

A message broker stores and routes messages between producers and consumers. Certain broker operations can be managed within a transaction:

- Receiving messages and acknowledging them only when the transaction commits.
- Sending messages and making them visible to consumers only after the transaction commits.
- Committing consumer offsets/positions together with published messages, if the broker supports transactions for that flow.
- Rolling back the transaction so input messages are redelivered or output messages are not published.

Broker transactions group messaging operations into a unit of commit according to the broker's semantics. However, a broker transaction does not implicitly include a database or file system.

For example, a consumer receives an `OrderCreated` message, writes the order to the database, and then sends `OrderAccepted` to the broker. There are at least three operations:

1. Receive/acknowledge `OrderCreated`.
2. Write order data to the database.
3. Publish `OrderAccepted`.

If the database commits but the broker rolls back, the data and messages are out of sync. If the broker commits first but the database rolls back, the consumer may have already confirmed the message while the business data was not saved.

## 2. Transaction Boundaries in a Chunk-Oriented Step

Spring Batch typically executes one chunk within one transaction:

```text
Begin chunk transaction
       |
       v
Read item(s)
       |
       v
Process item(s)
       |
       v
Write chunk
       |
       v
Update ItemStream / ExecutionContext
       |
       v
Commit transaction
```

The transaction manager passed to `chunk(size, transactionManager)` manages the chunk's transaction. The reader, processor, and writer can perform broker operations, but those operations belong to the chunk's transaction only if they genuinely participate in the same transaction manager/coordinator and the resources are enlisted properly.

For example, `DataSourceTransactionManager` manages a JDBC connection. It does not automatically manage a JMS `Session` or a Kafka producer transaction. Similarly, `JmsTransactionManager` manages a JMS `ConnectionFactory`; it does not automatically commit a database transaction. Being inside the same step does not mean all resources are automatically atomic.

## 3. Local Transactions vs. Distributed Transactions

A **local transaction** covers only one resource or one transaction domain. Examples:

- A JDBC transaction on a single database.
- A JMS transacted session on a single `ConnectionFactory`.
- A Kafka producer transaction on a single Kafka cluster.

A **distributed transaction** coordinates multiple resources through a transaction coordinator, typically using XA/JTA and two-phase commit if all resources support XA.

| Management Approach | Resources Covered | Primary Limitation |
|---|---|---|
| `DataSourceTransactionManager` | One JDBC `DataSource` | Does not automatically enlist JMS/Kafka |
| `JmsTransactionManager` | One JMS `ConnectionFactory` | Does not automatically enlist a database |
| `KafkaTransactionManager` | Kafka producer transaction | Does not automatically enlist a JDBC database |
| `JtaTransactionManager` with XA | Enlisted XA resources | Requires XA support, coordinator, recovery, and greater operational complexity |
| Outbox/inbox | Multiple local transactions coordinated via durable data and retries | Eventual consistency; requires idempotency/deduplication |

Do not choose XA just because you want "one transaction for everything." Verify that the broker, database, drivers, transaction coordinator, and deployment environment all support XA and recovery. Otherwise, outbox/inbox is usually easier to operate.

## 4. Receiving JMS Messages in a Transaction

With JMS, a transacted `Session` can receive messages and complete acknowledgement only when the transaction commits. If the transaction rolls back, messages can be redelivered according to broker configuration.

Spring provides `JmsTransactionManager` to manage local transactions for a JMS `ConnectionFactory`:

```java
@Bean
public PlatformTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
```

If a step handles only JMS resources and does not require an atomic commit with a database, this transaction manager can be used for the chunk step. JMS operations executed via a Spring-managed `JmsTemplate` can participate in the active transaction if they use the same `ConnectionFactory` and are configured appropriately.

Remember that `JmsTransactionManager` is a local transaction manager. If the step's writer also performs JDBC writes using another `DataSource`, database operations are not automatically inside the JMS transaction.

## 5. Publishing JMS Messages in a Transaction

A `JmsTemplate` can send messages within the active JMS transaction. Example writer emitting an event per item:

```java
@Bean
public ItemWriter<OrderAccepted> jmsOrderWriter(JmsTemplate jmsTemplate) {
    return chunk -> {
        for (OrderAccepted event : chunk) {
            jmsTemplate.convertAndSend("orders.accepted", event);
        }
    };
}
```

If `JmsTemplate` uses the right `ConnectionFactory` and participates in the transaction managed by `JmsTransactionManager`, messages are sent within the same JMS transaction. When the transaction commits, the broker finalizes delivery; on rollback, sends belonging to that transaction are rolled back per provider semantics.

If `JmsTemplate` uses a different `ConnectionFactory`, creates sessions outside the active transaction, or is configured non-transactionally, you cannot assume sends roll back with the chunk. Inspect the actual configuration and test against the target broker.

## 6. A JMS Transaction Is Not Automatically Atomic with a Database

Suppose a step uses `DataSourceTransactionManager` and calls `JmsTemplate` inside the writer:

```text
Database transaction                 JMS resource
---------------------                 -----------
BEGIN DB
INSERT order
                                      SEND OrderAccepted
COMMIT DB
                                      JMS send uncommitted / failed
```

If the database commits successfully but the JMS send is not committed, the order exists in the database while the event was never sent. Reversing the commit order carries the opposite risk: the message is sent while the database rolls back.

An ordinary transaction manager cannot undo an already-committed transaction on another resource. Calling `commit()` sequentially does not create distributed atomicity.

If both resources need an atomic commit, you need a coordinator supporting XA/JTA or an outbox design that records the intent to emit an event within the database transaction.

## 7. XA/JTA for Database and JMS

If both the database and JMS provider supply XA resources, they can be coordinated in a JTA transaction. `JtaTransactionManager` works with a transaction coordinator; an XA-aware `DataSource` and an XA `ConnectionFactory` are enlisted in the transaction.

Conceptual two-phase commit flow:

```text
Application / Spring Batch
          |
          v
JTA Transaction Coordinator
          |
          +------> XA Database Resource
          |
          +------> XA JMS Resource
                    |
          Phase 1: prepare
          Phase 2: commit / rollback
```

During the prepare phase, resources confirm they can commit. The coordinator then instructs them to commit or roll back per the collective decision. If the process or coordinator crashes between phases, a transaction may enter an in-doubt state requiring recovery.

Deployment prerequisites:

- The database provides a suitable XA `DataSource`/driver.
- The JMS provider provides an XA `ConnectionFactory`.
- The JTA coordinator is configured with a durable transaction log.
- Resources are properly enlisted in the transaction.
- Recovery credentials and resource identities are stably configured.
- Timeouts, pools, and connection limits are tuned appropriately.

XA adds complexity, round trips, and resource-holding duration. Not every broker or database supports XA in every deployment mode. Check official provider documentation and test crash/recovery, not just the happy path.

## 8. Configuring a Transaction Manager for a Step

If the architecture uses JTA to span both database and JMS XA resources, the step needs the JTA transaction manager:

```java
@Bean
public Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager jtaTransactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderAccepted> processor,
        ItemWriter<OrderAccepted> writer) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<Order, OrderAccepted>chunk(100, jtaTransactionManager)
            .reader(orderReader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

This snippet only selects the transaction manager for the chunk. It does not turn a `DataSource`/JMS `ConnectionFactory` into XA resources on its own. Configuring XA pools, the JTA coordinator, and enlistment must be done at the infrastructure/application-server layer or via a transaction coordinator library.

`JobRepository` must also be considered separately: if the repository uses the same JTA transaction and is configured appropriately, checkpoint metadata can participate in the transaction. If the repository uses a different resource/transaction manager, do not assume metadata and business data commit atomically.

## 9. Kafka Transactions Differ from JMS Transactions

Kafka provides a transactional API for producers. A producer transaction can send multiple records and commit or abort them as a single unit. For consume-transform-produce, Kafka supports transactional processing in which output records and consumer offsets can be committed in the same Kafka transaction when configured appropriately.

Spring Kafka provides `KafkaTransactionManager` to manage Kafka producer transactions:

```java
@Bean
public KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
        ProducerFactory<String, OrderEvent> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
```

The producer factory must be configured with an appropriate transactional ID prefix. Spring Kafka can manage producer transactions via `KafkaTemplate` and the transaction manager.

A Kafka transaction is not like a JMS local transaction, nor does it enlist a JDBC database. It manages transactions within the Kafka cluster, covering sent records and offsets when executed in the proper consume-transform-produce flow.

## 10. Kafka Consume-Transform-Produce and Offset Commits

In a Kafka consume-transform-produce flow, a consumer reads input records, the application processes them, and a producer sends output records. With Kafka transactions, output records and input offsets can be committed within the same Kafka transaction.

```text
Kafka input topic
       |
       v
Consumer reads records
       |
       v
Transform / validate
       |
       v
Producer sends output records
       |
       v
Kafka transaction commits
       |
       +--> Output records visible to read_committed consumers
       +--> Input offsets committed
```

If the transaction aborts, output records are not treated as committed by consumers using `isolation.level=read_committed`, and offsets are not committed in that transaction. The input can be reprocessed.

This supports exactly-once semantics within the scope of Kafka consume-transform-produce when configuration and processing satisfy Kafka's requirements. It does not cover side effects such as writing to an external database, making HTTP calls, or writing files.

## 11. KafkaTransactionManager in Spring Batch

If a step performs work strictly within a Kafka transaction, you can configure the chunk step with `KafkaTransactionManager` and publish through a `KafkaTemplate` bound to that transaction.

Example writer:

```java
@Bean
public ItemWriter<OrderEvent> kafkaOrderWriter(
        KafkaTemplate<String, OrderEvent> kafkaTemplate) {
    return chunk -> {
        for (OrderEvent event : chunk) {
            kafkaTemplate.send(
                    "orders.processed",
                    Long.toString(event.orderId()),
                    event
            );
        }
    };
}
```

The step can use `KafkaTransactionManager` as its transaction manager if the entire transaction boundary fits Kafka. However, the Spring Batch `JobRepository` usually stores metadata in a database. If `JobRepository` does not participate in the same transaction, metadata commits and Kafka commits can diverge.

When designing a step with a Kafka writer and a database-backed `JobRepository`, explicitly decide which resource holds the primary transaction, how secondary transactions synchronize, and how to recover if one commit succeeds while the other fails. Do not assume selecting `KafkaTransactionManager` automatically covers the repository database.

## 12. Database and Kafka: Transaction Synchronization Is Not XA

Spring Kafka can coordinate a Kafka transaction with another transaction manager via transaction synchronization in certain configurations. This allows ordering the commits between a database transaction and a Kafka transaction, but the two local transactions still do not become a single atomic XA transaction.

For example, if the database commits first and Kafka commits afterward:

```text
DB commit succeeds
       |
       v
Kafka commit fails
       |
       v
Database changed, but event not published
```

If the commit order is reversed, a message may be published even though the database rolls back or fails to commit. Transaction synchronization helps coordinate ordering and rollback across some phases, but cannot roll back a resource that has already committed independently.

With a database plus Kafka, transactional outbox is a common pattern: persist business data and the outbox event in the same database transaction; a separate publisher sends outbox events to Kafka and marks them sent. Downstream consumers process idempotently.

## 13. Transactional Outbox

Outbox solves the dual-write problem: an application both updating a database and publishing a message. Rather than writing to the database and broker directly in the same flow, the application writes business data and an outbox record in the same database transaction.

Example table:

```sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(100) PRIMARY KEY,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(100) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
```

Inside the order-processing transaction:

```java
@Transactional
public void acceptOrder(Order order) {
    orderRepository.save(order);

    OutboxEvent event = new OutboxEvent(
            UUID.randomUUID().toString(),
            order.getId().toString(),
            "ORDER_ACCEPTED",
            serialize(order)
    );
    outboxRepository.save(event);
}
```

If the transaction commits, both the order and the outbox row exist. If it rolls back, neither exists. A Spring Batch job or separate publisher reads the outbox and sends events to the broker.

Outbox does not create an atomic commit between the database and the broker. It guarantees the intent to publish is stored durably alongside the business update; the publisher can retry until the broker accepts the event.

## 14. Outbox Publisher in Spring Batch

A job can read unpublished outbox rows, send messages, and update their status:

```text
Outbox table
    |
    v
ItemReader<OutboxEvent>
    |
    v
ItemProcessor (serialize / validate)
    |
    v
ItemWriter (publish to broker)
    |
    v
Mark published / update outbox state
```

If the publisher writes `published_at` in the same database transaction as reading/claiming the outbox, while the Kafka/JMS publish is a separate local transaction, a failure window still exists between the broker commit and the database commit. For instance, if the broker accepts the message and the process crashes before marking the outbox published, the next run will resend the message.

Consequently, outbox typically provides **at-least-once publication**. Consumers need to deduplicate using `event_id` or process idempotently. Never mark an event as published before sending to the broker; if sending fails after marking, the event can be lost.

One implementation approach is claiming events via `NEW` → `IN_PROGRESS` status with a lease, publishing, and then marking `PUBLISHED`. If a worker crashes, the lease expires and the event is reclaimed. Ensure multiple publishers do not process the same event concurrently by mistake.

## 15. Inbox Pattern for Idempotent Consumers

An inbox helps consumers handle duplicate messages safely. The consumer persists the message ID in an inbox table in the same transaction as the business data update.

Example:

```sql
CREATE TABLE inbox_message (
    message_id   VARCHAR(100) PRIMARY KEY,
    received_at  TIMESTAMP NOT NULL
);
```

Processing flow:

1. Receive a message with a stable `message_id`.
2. Start a database transaction.
3. Insert the message ID into the inbox.
4. If a unique constraint indicates the ID already exists, the message was already processed; skip the business update.
5. If the new insert succeeds, update the business data.
6. Commit the database transaction.
7. Acknowledge/commit the offset at the broker per the consumer mechanism.

If the process crashes after the database commit but before the broker ack, the broker can redeliver the message. On the next attempt, the inbox detects `message_id` already exists and does not reapply the business update.

The inbox works only when inserting the inbox row and updating business data occur in the same database transaction. If you write to the inbox first and update business data in another transaction, a failure can leave the message marked processed while business data was never updated.

## 16. At-Most-Once, At-Least-Once, and Exactly-Once

Delivery terms describe how many times a message may be processed:

| Semantics | Meaning | Risk |
|---|---|---|
| At-most-once | Message is delivered/processed at most once | Messages can be lost if ack/offset commits before durable processing |
| At-least-once | Message is delivered at least once until confirmed | Duplicates can occur if processing finishes but ack has not committed |
| Exactly-once | Processing effect is guaranteed exactly once within a defined scope | Requires transactions/deduplication and a clearly defined guarantee boundary |

In distributed systems, "exactly once" must specify *where*. Kafka can provide exactly-once for consume-transform-produce inside a Kafka transaction. That does not mean an external database update, an email, and an HTTP call also occur only once.

For side effects outside the broker, idempotency and inbox/outbox are usually the foundation for achieving an effective business outcome equivalent to exactly-once despite transport redeliveries.

## 17. Acknowledging Input Messages and Database Commits

If a step receives messages from a broker and then writes to a database, commit order matters:

**Ack broker first, commit database second:** if the database rolls back after the broker has confirmed the message, the message may not be redelivered and data is lost.

**Commit database first, ack broker second:** if the database commits successfully but the process crashes before the ack, the broker redelivers the message. The database may receive the same message again; inbox/idempotency is needed.

```text
Database-first:
  DB commit ---- crash ---- Broker ack
      |                         |
      +-- business data saved   +-- may be redelivered
```

With two local transactions and no XA, it is usually preferable to avoid data loss by committing business state before acknowledging messages, then handling duplicates with an inbox/unique key. The exact mechanism depends on the broker's acknowledgement model and listener/reader framework.

## 18. Reading Messages with Spring Batch

Spring Batch can use a custom `ItemReader` or integration components to receive messages from a broker. With JMS, a reader may use `JmsTemplate`; with Kafka, a reader may use the consumer API or an integration adapter. Ensure message receipt and acknowledgement follow the chosen transaction model.

Do not write a reader that simply calls `receive()` and immediately acks if the chunk can still roll back. If a message is acked before the database writer commits, a writer failure can lose the message.

A transactional reader must clarify:

- Until when is the message retained?
- Does ack happen when `read()` returns the item, when the chunk commits, or in a separate callback?
- When the chunk rolls back, is the message redelivered?
- Does Spring Batch buffer already-read items for replay within the same process?
- On process restart, does the `JobRepository` checkpoint match the broker offset/ack state?

For queue/broker readers with transactional semantics, configure the reader and transaction manager according to the corresponding integration documentation. Do not assume a custom `ItemReader` implementing `ItemStream` is enough to make broker messages roll back; `ItemStream` only manages checkpoint/lifecycle and does not make message consumption transactional on its own.

## 19. Sending Messages with ItemWriter

A writer can emit an event for each item in a chunk:

```java
public class OrderEventWriter implements ItemWriter<OrderEvent> {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventWriter(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderEvent> chunk) {
        for (OrderEvent event : chunk) {
            kafkaTemplate.send(
                    "orders.events",
                    Long.toString(event.orderId()),
                    event
            );
        }
    }
}
```

This code shows chunk-based publishing, but transaction behavior depends on `KafkaTemplate` and the transaction manager. If all sends in a chunk must belong to a Kafka transaction, you must configure the producer factory, Kafka transaction manager, and step transaction boundary appropriately.

If the step also writes to a database, choose a consistent model: XA if all resources support it, or outbox if not. Never just slap `@Transactional` around the writer and assume Kafka sends become atomic with JDBC.

## 20. Retries and Redelivery

Brokers typically redeliver messages when a consumer fails to acknowledge/commit offsets within the timeout or when a transaction rolls back. Spring Batch also has retry/skip policies at the item/chunk level. These two mechanisms can interact and cause a message to be processed multiple times.

Example:

```text
Broker delivers message M
       |
       v
Batch reads M
       |
       v
Processor / Writer fails
       |
       v
Chunk rollback
       |
       v
Message redelivery or item replay
       |
       v
Retry processing M
```

Clarify which errors are retried within the same step, which roll back the chunk, which trigger broker redelivery, and the total attempt count. If both Spring Retry and broker redelivery retry, actual attempts can exceed each layer's limit.

Principles:

- Retry transient errors such as broker timeouts or database deadlocks with limits and backoff.
- Do not infinitely retry schema errors, malformed payloads, or missing writers.
- Use stable message IDs to deduplicate.
- Maintain a dead-letter/quarantine policy for poison messages.
- Track delivery count, retry count, and root cause.
- Ensure writers are idempotent when chunks are re-invoked.

## 21. Poison Messages and Dead-Letter Queues

A poison message is a message that always fails processing—for example, malformed JSON, an unsupported schema version, or invalid business data. If the broker redelivers continuously, a single message can block consumer progress.

A handling policy might look like:

1. Retry transient infrastructure errors within limits.
2. For permanent data errors, write safe payload/metadata to quarantine or a dead-letter queue.
3. Acknowledge/commit the input only once moving to the DLQ has completed per transaction policy.
4. Record the message ID, source topic/queue, partition/offset or delivery tag, and error code.
5. Have a procedure for fixing data and replaying from the DLQ.

Do not log entire messages if they contain tokens, personal data, or payment information. A dead-letter policy must preserve enough detail for investigation while controlling access permissions and retention.

## 22. Idempotency in Writers

An idempotent writer can receive the same item multiple times without creating unintended additional business effects.

Database example using a unique event ID:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    order_id BIGINT NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
```

When writing, you can insert with a unique constraint and handle duplicates per policy. Upsert syntax depends on the database. Avoid catching every `DataIntegrityViolationException` and ignoring it, as other constraint violations can be masked.

With Kafka, using stable message keys/event IDs helps partitioning and consumer-side deduplication. Kafka producer idempotence reduces duplicates caused by producer protocol retries, but does not replace business idempotency if the application intentionally sends the same event twice in two different transactions.

## 23. Spring Batch ExecutionContext and Broker Offsets

Spring Batch persists checkpoints in `ExecutionContext`; the broker also maintains its own consumption position such as JMS acknowledgement state or Kafka consumer offsets. These are two distinct types of progress.

```text
JobRepository                         Broker
-------------                         ------
StepExecutionContext                  Consumer offset / ack state
  - item count                          - partition offset
  - reader checkpoint                   - message acknowledgement
  - resource position                   - committed position
```

If the two checkpoints do not commit atomically, drift can occur:

- `JobRepository` advances ahead of the broker: a job restart assumes items were committed, yet the broker may redeliver them.
- The broker advances ahead of `JobRepository`: the broker will not resend messages, yet the job checkpoint did not record them; the job may be unable to recover those items.

To avoid message loss, design commit ordering and deduplication. With Kafka, Kafka transactions can commit outputs and offsets in the same Kafka transaction when the entire consume-transform-produce stays inside Kafka. With databases outside Kafka, outbox/inbox or XA are options depending on infrastructure.

Do not store offsets solely in `ExecutionContext` and commit independently from the broker without a recovery strategy. An offset written to `JobRepository` does not acknowledge messages on the broker, and a broker offset does not update the batch checkpoint.

## 24. Choosing a Model by Use Case

| Use Case | Model to Consider |
|---|---|
| Receive JMS messages only and process within JMS transaction | `JmsTransactionManager` if reader/consumer participate in the same local transaction |
| Publish Kafka records only within a chunk | `KafkaTransactionManager` and transactional producer |
| Receive JMS and update database needing atomicity | XA/JTA if both JMS and database support it; otherwise, inbox/idempotency |
| Update database then emit Kafka event | Transactional outbox + publisher + idempotent consumer |
| Consume Kafka, transform, and produce to Kafka | Kafka transaction with offsets/output in the same transaction |
| Consume Kafka and update database | Inbox/idempotency or a verified coordination model; do not assume Kafka offsets and DB commits are atomic |
| Send email/HTTP after database commit | Outbox or retryable dispatch; already-executed side effects cannot be rolled back |

## 25. XA or Outbox/Inbox?

XA/JTA fits when:

- Business requirements genuinely require an atomic commit across database and broker.
- All resources support XA.
- The system has a transaction coordinator and durable recovery.
- Operations teams can handle in-doubt transactions, timeouts, and recovery logs.
- The throughput/latency cost of 2PC is acceptable.

Outbox/inbox fits when:

- Short-lived eventual consistency is acceptable.
- You want to keep database transactions local and simple.
- The broker or database does not support XA.
- Explicit retries, replays, and audits are needed.
- Consumers/writers can be designed idempotently.

Outbox/inbox do not cause messages to be delivered only once. They turn duplicates into recognizable situations that can be handled safely. This is often a more manageable trade-off than a complex distributed transaction.

## 26. Transaction Timeouts and Resource Lifecycle

A chunk transaction can hold a database connection, JMS `Session`, or Kafka producer transaction open during processing. If a processor calls a slow API or runs heavy CPU work, the transaction can time out.

Consider:

- Chunk size and processing duration per chunk.
- Database transaction timeout.
- Broker transaction timeout and producer transaction timeout.
- Consumer session/visibility timeout or max poll interval depending on the broker.
- Connection/session/producer pool capacity.
- Deadlocks and lock duration.
- Shutdown/rebalance while a step is processing.

Do not hold a transaction open while waiting on user input or calling external services with unbounded latency. For long-running work, split into short steps, persist durable state, and use a retryable workflow.

## 27. Transactional Listeners and Spring Batch

An application can use a message listener to receive messages that trigger a job rather than having a step directly consume every payload. In that model, the listener typically:

1. Receives a message containing a batch ID or input reference.
2. Validates and constructs `JobParameters`.
3. Launches the Spring Batch job.
4. Acknowledges the message per policy after the job request has been recorded.

Do not keep a broker transaction open for the entire duration of a job if the job runs for minutes or hours. Instead, persist the launch request durably, use an idempotency key for the job request, and let `JobRepository` manage the job's lifecycle.

If the listener acks the message right after calling `JobLauncher.run()` but before the job request is durably saved, a process crash can lose the request. Clarify synchronous/asynchronous `JobLauncher` behavior, `JobRepository` commit timing, and how the listener handles redelivery.

## 28. Observing and Operating Broker Transactions

To investigate failures, track both batch metadata and broker metadata:

- `JobInstance`/`JobExecution`/`StepExecution` IDs.
- Batch ID and message ID/event ID.
- Topic/queue, partition, offset, or delivery tag.
- Transaction begin/commit/rollback outcomes.
- Redelivery count and retry count.
- Outbox/inbox status.
- Dead-letter count and error codes.
- Transaction timeouts, coordinator recovery, and in-doubt status if using XA.
- Database commit status and broker publish/ack status.

Logs should carry a correlation ID across reader, processor, writer, and consumer. Avoid logging raw payloads containing sensitive data.

For outbox, monitor counts of `NEW`, `IN_PROGRESS`, and `PUBLISHED` events, age of unpublished events, and retry counts. For inbox, monitor duplicate counts and processing errors. For XA, monitor transaction recovery and resource health.

## 29. Testing Transactions with Brokers

Unit tests mocking the writer cannot prove broker transactions commit/roll back properly. You need integration tests with production-like brokers/databases or appropriate test containers.

Key scenarios:

1. Successful publish and transaction commit; consumer receives the message.
2. Writer throws an exception before commit; output message does not appear when sending belongs to the transaction.
3. Database writer succeeds but broker commit fails; verify recovery/outbox behavior.
4. Broker publish succeeds but process stops before marking outbox; consumer handles duplicate safely.
5. Consumer commits database then crashes before ack; message redelivery does not repeat business updates.
6. Chunk rollback; verify input messages are replayed or redelivered per configuration.
7. Kafka consume-transform-produce aborts; outputs and offsets are not committed as part of the transaction.
8. Poison message exceeds retry limit and moves to DLQ per policy.
9. Job restarts after a chunk has committed; `JobRepository` and broker position do not lose messages.
10. XA coordinator/process crashes during prepare/commit phases and recovery completes properly.
11. Transaction timeouts, broker unavailability, and connection pool exhaustion.
12. Multiple workers claim outbox events concurrently; one event is not published with duplicate business effects.

Tests must verify the final state in both database and broker, not merely assert a step exception. For XA, test real recovery rather than only in-process rollbacks. For outbox/inbox, simulate crashes in the window between the two local commits.

## 30. Common Misconceptions

**Assuming chunk transactions automatically cover the broker.** Only resources participating in the right transaction manager/coordinator commit with the chunk.

**Assuming `JmsTransactionManager` commits the database.** It is a local transaction manager for a JMS `ConnectionFactory`.

**Assuming `KafkaTransactionManager` enlists JDBC.** Kafka transactions manage Kafka resources; databases need their own transaction manager and coordination mechanism.

**Assuming calling send in the writer means the message is committed.** Sends may commit only when the transaction completes; semantics depend on template/session/producer configuration.

**Acking messages inside `read()` before writing to the database.** If the database rolls back after acking, messages can be lost.

**Assuming retries never create duplicates.** Redeliveries and retries can invoke the writer multiple times; idempotency is required.

**Assuming Kafka exactly-once covers databases and HTTP.** EOS applies only to the boundary protected by Kafka transactions; external side effects need outbox/inbox or dedicated mechanisms.

**Assuming transaction synchronization is XA.** Synchronizing commit order between two local transactions does not provide atomic rollback once one resource has committed.

**Marking outbox rows published before the broker accepts the message.** A subsequent crash can lose the event. Publishing then marking can create duplicates, so consumers need deduplication.

**Saving broker offsets only in `ExecutionContext` and treating that as an ack.** `JobRepository` checkpoints and broker offsets are two separate state stores.

## 31. How to Design Transactions with Brokers

First, list every side effect of a chunk: where messages are received, where the database is updated, where messages are published, and where checkpoints are stored. Identify which resource the step's transaction manager controls, whether readers/writers truly participate in that transaction, and what data-loss or duplication windows the commit order can create.

When working with a single broker, use the matching transaction manager and configure acknowledgement/producer transactions properly. When atomic commits between a database and JMS are required, use XA/JTA only when every resource and piece of infrastructure fully supports it. For database plus Kafka or non-XA systems, prefer transactional outbox/inbox, stable message IDs, and idempotent writers/consumers.

For input messages, avoid acknowledging before business state is durably stored. For output messages, persist the intent to publish alongside business updates in an outbox, then publish/retry separately. Synchronize Spring Batch checkpoints with broker positions using a recoverable strategy rather than treating two metadata stores as one automatic transaction.

Test crash points between commits, rollbacks, redeliveries, retries, and restarts. Transactions with brokers are not just an annotation setting; they are a decision about atomicity scope, delivery semantics, and the recoverability of the entire pipeline.
