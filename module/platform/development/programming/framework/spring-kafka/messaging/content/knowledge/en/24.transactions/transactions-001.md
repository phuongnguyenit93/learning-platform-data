# What Problems Do Kafka Transactions Solve?

A Kafka pipeline often involves multiple steps: a producer emits events, a consumer reads an event, processes it, and emits the result to another topic. If the application stops mid-flight, the system can end up in a partially completed state: one output topic has received a record while another topic has not, or the output has been written while the input offset has not been acknowledged. On restart, the consumer may redeliver the record and produce duplicate results.

**Kafka transactions** solve this class of consistency problems inside Kafka by grouping multiple record writes and offset acknowledgements into an atomic commit unit. Consumers using the appropriate read mode see either all committed results or none of the results from an aborted transaction.

This lesson belongs to the **Transactions** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on why Kafka needs transactions, the scope of transaction guarantees, how transactions coordinate producers and consumers, and the boundaries you must understand before using Spring Kafka transactions in real systems.

## Learning Outcomes

After this lesson, you will be able to:

- Identify partial writes and duplicate processing in Kafka pipelines.
- Explain how Kafka transactions guarantee atomicity across multiple records, partitions, and topics.
- Distinguish between an idempotent producer and a transactional producer.
- Describe consume-transform-produce and committing input offsets within the same transaction as outputs.
- Understand the role of `transactional.id`, the transaction coordinator, and producer fencing.
- Explain why consumers need `isolation.level=read_committed` to read only committed data.
- Configure transactions in Spring Kafka using a transaction-capable `ProducerFactory` and `KafkaTemplate`.
- Understand listener container transactions and how offsets are enlisted in a transaction.
- Recognize that Kafka transactions do not automatically cover databases, HTTP calls, email, or external systems.
- Choose outbox, inbox, and idempotency patterns when coordinating Kafka with other systems.

## 1. The first problem: a single business operation publishes multiple times

Suppose the Order Service receives a request to create an order. It needs to emit two events:

1. `orders.created` for Fulfillment to process the order.
2. `orders.audit` for Audit to store the history.

If the two sends are independent, the following situation can occur:

~~~text
Order Service
    |
    +---- send orders.created ----> SUCCESS
    |
    +---- send orders.audit ------> FAIL
                                      |
                                      v
                              Partial publication
~~~

One topic has the record, while the other topic does not. Downstream systems observe an incomplete state. If the application retries sending both records, `orders.created` may be emitted twice.

The issue is not merely whether the producer receives an acknowledgement. The application needs a way to tell Kafka that these records belong to the same unit of work: either all are committed, or the transaction is aborted.

## 2. The second problem: consume-then-produce can create a skew

A consumer commonly reads an input event, processes it, and emits an output event.

For example:

~~~text
orders.created
      |
      v
Fulfillment Consumer
      |
      +---- publish orders.accepted
      |
      +---- commit offset orders.created
~~~

If the output is published successfully but the process stops before committing the input offset, upon restart the consumer reads the old event again and may publish `orders.accepted` a second time.

If the offset is committed before publishing the output, the opposite situation can happen: the offset has advanced, but the output has not been written. When the process stops, the input record is not redelivered, while the output is missing.

The two operations must be coordinated:

- Writing the output records.
- Acknowledging the offset of the processed input record.

Kafka transactions allow both to be placed into the same Kafka transaction. When the transaction commits, the output and offset take effect together; when the transaction aborts, neither the output nor the offset belonging to that transaction is considered committed.

## 3. What do Kafka transactions guarantee?

Kafka transactions provide atomicity for the Kafka operations included in the same transaction. A single transaction can write multiple records to multiple partitions and multiple topics, and can include consumer group offsets.

| Scenario | Without transaction | With Kafka transaction |
|---|---|---|
| Writing to two topics | The first topic may succeed while the second fails | Both groups of records commit together or abort together. |
| Consumer reads then emits output | Output may be written while input offset is not committed | Output and input offset can be committed atomically. |
| Process stops before commit | May leave partially written output | Uncommitted transaction is aborted / not exposed to committed readers. |
| Consumer reads data from an aborted transaction | An unrestricted consumer may see uncommitted records | A `read_committed` consumer skips records from aborted transactions. |

Transactions do not mean everything in the application becomes a global ACID transaction. The scope of atomicity here is the Kafka operations enlisted in the transaction.

## 4. Atomicity across multiple topics and partitions

A transactional producer can send multiple records in the same transaction, including records belonging to different topics or partitions.

~~~mermaid
flowchart TD
    A[Begin Kafka transaction] --> B[Send record A]
    B --> C[Send record B]
    C --> D[Send record C]
    D --> E{All operations succeed?}
    E -->|Yes| F[Commit transaction]
    E -->|No| G[Abort transaction]
    F --> H[read_committed consumers see all committed records]
    G --> I[read_committed consumers see none of the aborted records]
~~~

For example, a transaction writes:

- One record to `orders.accepted-0`.
- One record to `orders.audit-2`.
- One record to `inventory.reservation-requested-1`.

These records can be written across multiple partitions. Consumers using `read_committed` only read records belonging to the transaction after the transaction commits.

Kafka does not establish a global order across partitions. Transactions guarantee atomicity of record visibility, not a single unified log or total ordering across them.

## 5. How do an idempotent producer and a transaction differ?

An idempotent producer and a transaction are related, but they solve two different problems.

| Mechanism | Solves | Does not solve by itself |
|---|---|---|
| Producer acknowledgement | Producer knows the broker received the request according to the configured acknowledgement level | Atomicity across multiple sends. |
| Idempotent producer | Prevents duplicates caused by producer retries of the same request within a producer session at the Kafka protocol level | Duplicates caused by the application actively resending the same business operation or from another process. |
| Kafka transaction | Atomically commits/aborts multiple records and optionally input offsets | Side effects in a database or HTTP service outside Kafka. |
| Consumer idempotency | Prevents duplicate business processing by event ID | Does not replace Kafka transactions when atomic output + offset is required. |

An idempotent producer protects retries at the protocol layer using a producer ID and sequence number. Transactions extend the scope to multiple write operations and commit/abort.

When enabling transactions in a Kafka producer, idempotence is enabled as required by a transactional producer. These two concepts should not be treated as identical: idempotence handles duplicates from send retries, while transactions handle atomicity across multiple Kafka operations.

## 6. How does a producer transaction work?

A transactional producer has a `transactional.id` identifier. The producer registers with the transaction coordinator, begins a transaction, writes records, and then commits or aborts.

High-level flow:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Producer as Transactional Producer
    participant TC as Transaction Coordinator
    participant Broker as Partition Leaders
    App->>Producer: beginTransaction
    Producer->>TC: Find/initialize transaction
    App->>Producer: send record A
    Producer->>Broker: Write A (transactional)
    App->>Producer: send record B
    Producer->>Broker: Write B (transactional)
    App->>Producer: commitTransaction
    Producer->>TC: End transaction: COMMIT
    TC-->>Producer: Commit result
~~~

Kafka uses transaction markers to determine the commit or abort state in the involved partitions. A `read_committed` consumer relies on transaction state to decide which records are allowed to be returned to the application.

If the application encounters an error before commit, it can abort the transaction. If the process loses connectivity or stops unexpectedly, the Kafka transaction coordinator handles the transaction state according to the protocol and configured timeout.

## 7. `transactional.id` and producer fencing

`transactional.id` identifies a logical transactional producer across initializations. It allows Kafka to detect that an old producer instance has been replaced and prevent the old producer from continuing to write.

If two producers simultaneously use the same transactional ID, the producer initialized later can **fence** the old one. The old producer receives an error such as `ProducerFencedException` and is no longer permitted to continue transactions.

Operational rules:

- Each concurrently active producer instance needs a unique transactional ID.
- Do not assign the same static transactional ID to every pod.
- When running multiple replicas, use a prefix that is unique per instance.
- Let Spring Kafka manage suffixes for concurrent producers created from the same factory.
- Treat fencing as a sign that another instance owns the same transactional ID; do not retry infinitely on a fenced producer.

In Spring Kafka, `transactionIdPrefix` is typically configured on the `ProducerFactory`. The prefix must be unique across concurrently running application instances; the factory can append a suffix for producers created inside the instance.

## 8. Consumers reading only committed transactions

A Kafka consumer has the property:

~~~properties
isolation.level=read_committed
~~~

Two main values:

| Value | Behavior |
|---|---|
| `read_uncommitted` | May return records belonging to uncommitted or aborted transactions. This is the common default for Kafka consumers. |
| `read_committed` | Returns only non-transactional records or records belonging to committed transactions; skips records from aborted and ongoing transactions. |

If an application uses Kafka transactions to ensure output only appears when the entire transaction succeeds, downstream consumers need `read_committed` to observe that exact commit boundary.

An open transaction can affect the Last Stable Offset (LSO). A `read_committed` consumer does not read past the LSO, because earlier transactions on the partition may not have completed yet. Long-running open transactions can therefore increase data visibility latency and observed consumer lag.

## 9. Consume-transform-produce and offsets in the same transaction

This is the case where Kafka transactions provide the most important guarantee for a processing pipeline:

1. The consumer reads an input record.
2. The application transforms and sends output records using a transactional producer.
3. The next offset of the input partition is sent into the same transaction.
4. The transaction commits.

If the commit succeeds, the output records and the input offset are published together. If the transaction aborts, the input offset is not committed in that transaction and the record can be read again.

~~~mermaid
flowchart TD
    A[Consume input record] --> B[Transform]
    B --> C[Begin/participate in Kafka transaction]
    C --> D[Produce output records]
    D --> E[Send consumed offsets to transaction]
    E --> F{Commit transaction}
    F -->|Commit| G[Output visible + input offset advanced]
    F -->|Abort| H[Output aborted + input offset not advanced]
    H --> I[Input record can be redelivered]
~~~

The committed offset is still the next position to read for each partition. For example, after processing input offset 41, the offset sent to the transaction is typically 42.

This mechanism is commonly referred to as exactly-once processing within the scope of Kafka consume-transform-produce. It does not mean the listener is physically invoked only once: the listener can run again after an abort or crash. What is guaranteed is that transactional outputs and input offsets have a consistent commit outcome for committed-read consumers.

## 10. Spring Kafka: enabling a transactional producer

With Spring Boot, you can configure the transaction ID prefix:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${HOSTNAME:orders-service}-tx-
      acks: all
    consumer:
      properties:
        isolation.level: read_committed
~~~

When `spring.kafka.producer.transaction-id-prefix` is configured, Spring Boot can create a transaction-capable `ProducerFactory` and `KafkaTransactionManager` via the auto-configuration mechanism of the corresponding Boot version.

In multi-replica deployments, the prefix value must differ across concurrently running instances. The example above uses `HOSTNAME` as the identifying component; in Kubernetes, you can use the pod name or a unique instance ID. Never give all pods the same static prefix.

If configuring `ProducerFactory` manually, set the transaction ID prefix on the factory. `ProducerFactory` manages transactional producers and appropriate suffixes for concurrently created producers.

## 11. Sending multiple records in one transaction with `KafkaTemplate`

When you only need to group multiple publishes into an atomic unit, you can use `KafkaTemplate.executeInTransaction`.

~~~java
public void publishOrderEvents(
        OrderCreatedEvent created,
        OrderAuditEvent audit) {

    kafkaTemplate.executeInTransaction(operations -> {
        operations.send(
                "orders.created",
                created.orderId(),
                created
        );

        operations.send(
                "orders.audit",
                audit.orderId(),
                audit
        );

        return null;
    });
}
~~~

Sends inside the callback participate in the same transaction managed by `executeInTransaction`. If the callback completes and the transaction commits successfully, both records are published. If the callback throws an exception, the transaction is aborted.

To use this API, `KafkaTemplate` must be created from a `ProducerFactory` configured for transactions. If the `ProducerFactory` does not support transactions, the operation will fail when attempting to start a transaction.

Do not call a send operation outside the callback and assume it automatically joins the transaction. Use the `KafkaTemplate`/operations bound to the active transaction.

## 12. Spring Kafka transactional listener container

For the consume-transform-produce model, the listener container can start a Kafka transaction before invoking the listener. Records sent with `KafkaTemplate` participate in the transaction bound to the consumer thread. When the listener completes, the container sends the processed offsets into the transaction and commits.

High-level configuration:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
transactionalListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        KafkaTransactionManager<String, Object> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);

    // Attach the Kafka transaction manager to the listener container.
    // The specific setter API depends on the Spring Kafka version.
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);

    return factory;
}
~~~

The listener can then send outputs:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        containerFactory = "transactionalListenerFactory"
)
public void process(OrderCreatedEvent event) {
    OrderAcceptedEvent output = fulfillmentService.accept(event);

    kafkaTemplate.send(
            "orders.accepted",
            event.orderId(),
            output
    );
}
~~~

When the container is configured as transactional properly, outputs sent from the listener join the container's transaction. The input offset is included in the transaction when the listener processes successfully.

If the listener throws an exception, the transaction rolls back. Spring Kafka uses an after-rollback mechanism to redeliver or recover the record as configured. With a transactional listener, do not mechanically apply a non-transactional `DefaultErrorHandler` example; configure an appropriate `DefaultAfterRollbackProcessor`.

The API name for configuring the transaction manager on `ContainerProperties` may vary by Spring Kafka version. Use the setter compatible with your project's dependency and verify that `KafkaTemplate` and `ProducerFactory` participate in the transaction properly.

## 13. What does exactly-once mean in Kafka?

Exactly-once is commonly used to describe a consume-transform-produce pipeline whose outputs and input offsets are committed atomically.

For example, a consumer reads `orders.created`, produces `orders.accepted`, and commits the input offset in the same transaction. Downstream consumers using `read_committed` see only outputs of committed transactions.

Scenarios:

| Moment the process fails | Outcome |
|---|---|
| Before sending output | No transactional output is committed; input offset has not advanced. |
| After sending output but before commit | Transaction aborts or is not committed; output is not visible to `read_committed`, input can be redelivered. |
| After transaction commit | Output is visible and input offset has advanced with the same transaction. |
| Listener runs again after rollback | May be invoked again; the previous transaction produced no committed output. |

Exactly-once does not eliminate all repeated executions. It guarantees that committed Kafka results are not duplicated in a properly designed and configured consume-transform-produce pipeline.

Key prerequisites include a transactional producer, sending offsets into the transaction, `read_committed` consumers where needed, a clear transaction boundary, and proper error/rollback handling.

## 14. Kafka transactions do not cover databases

Suppose a listener reads `orders.created`, updates a database, and then sends `orders.accepted` in a Kafka transaction.

If the database commits successfully but the Kafka transaction aborts, the database has changed while the Kafka output is not committed. Kafka cannot independently roll back a database transaction.

Conversely, if the database transaction fails yet the Kafka transaction still commits because the two transaction managers have independent commit boundaries or uncoordinated completion order, the two systems can also diverge in state. Putting two `@Transactional` annotations or two transaction managers on the same method does not automatically create an atomic distributed transaction.

| Side effect | Covered by Kafka transaction? |
|---|---|
| Sending multiple Kafka records | Yes |
| Sending output records across multiple topics/partitions | Yes |
| Committing consumer group offsets in the same Kafka transaction | Yes |
| Writing to a relational database | Not automatically |
| Calling an HTTP service | No |
| Sending email or SMS | No |
| Writing to a file or object storage | No |

You should not call this end-to-end exactly-once when the business flow involves a database or external service. You need outbox/inbox, idempotency, or a transaction coordination protocol suited to the system.

## 15. What do transactional outbox and inbox solve?

If an application needs to update a database and emit a Kafka event, the transactional outbox is a common choice.

Within the same database transaction:

1. Update the business tables.
2. Insert a row into the outbox table.
3. Commit the database transaction.

A relay or CDC connector reads the outbox and publishes the record to Kafka. If the relay publishes duplicates, downstream consumers use the event ID for idempotency.

~~~mermaid
flowchart TD
    A[Application command] --> B[Database transaction]
    B --> C[Update business tables]
    B --> D[Insert outbox row]
    C --> E[Commit DB]
    D --> E
    E --> F[Outbox relay / CDC]
    F --> G[Kafka topic]
    G --> H[Consumer with inbox/idempotency]
    H --> I[Database transaction]
~~~

The inbox pattern helps a consumer store processed event IDs in the same database transaction as the business state change. When a record is redelivered, the application detects that the event was already processed and avoids repeating side effects.

Outbox/inbox do not replace Kafka transactions in every scenario. They address the boundary between a database and Kafka or between systems with independent transaction managers.

## 16. Timeouts and long-running transactions

Kafka transactions must complete within the timeout limit. A transaction that runs too long can be timed out and aborted by the broker.

Notable configurations:

- `transaction.timeout.ms`: the maximum duration the producer requests for a transaction.
- `transaction.max.timeout.ms`: the broker-enforced upper limit for producer transaction timeouts.
- `max.block.ms`: how long the producer may block on certain operations such as fetching metadata or buffer space.
- Listener processing time: the actual business processing time spent inside the transaction.

Keep transactions short and avoid placing slow work such as long HTTP calls, waiting for user input, or overly large batches inside a transaction. Long-lived transactions tie up coordinator resources and can block `read_committed` consumers at the LSO on affected partitions.

Do not increase the transaction timeout to hide a slow listener without measuring. Monitor transaction duration, abort rate, commit latency, and consumer lag.

## 17. Fencing, aborts, and transaction errors

A transactional producer can encounter errors such as:

- Producer fenced because the transactional ID is already used by another instance.
- Transaction timeout.
- Broker or coordinator temporarily unavailable.
- Lost commit response requiring outcome handling per the client protocol.
- Serialization or send failure inside the transaction.
- Listener exception causing the container to roll back the transaction.

Not every error can be retried by simply calling commit again. For a fenced producer, the current instance no longer has permission to continue; lifecycle and transactional IDs must be addressed. For transient errors, the Kafka client and Spring Kafka have error-specific handling mechanisms, yet the application still needs clear logging and recovery.

If a transaction aborts, input records not acknowledged in that transaction can be redelivered. Listeners must be safe to re-run and avoid external side effects unprotected by Kafka transactions.

## 18. When should you use Kafka transactions?

| Need | Should you use Kafka transactions? | Reason |
|---|---|---|
| Publishing to two or more topics that must appear together | Yes | Atomic multi-topic/multi-partition write. |
| Consume-transform-produce within Kafka | Yes | Combines outputs and input offsets in the same transaction. |
| Sending a single simple record with no atomicity requirement | Likely unnecessary | An idempotent producer and acknowledgements may suffice. |
| Updating a database then publishing to Kafka | Kafka transactions alone are insufficient | Requires outbox or a DB/Kafka coordination mechanism. |
| Calling HTTP then committing Kafka offset | Kafka transactions do not cover HTTP | Requires idempotency, retries, and appropriate compensation. |
| Sending email/SMS from a listener | Kafka transactions cannot roll back sent emails | Use event/command workflows and idempotency. |
| Consumer only reads and emits no output | Usually no transactional producer needed | AckMode/commit strategy can handle this. |

Transactions carry coordination and latency overhead compared to regular publishing. Use them when specific atomicity is needed, not just to put the keyword `exactly-once` in configuration.

## 19. Testing Kafka transactions

Tests need to verify both committed data and aborted data.

| Scenario | What to verify |
|---|---|
| Multi-topic commit | A `read_committed` consumer sees all outputs. |
| Abort before commit | A `read_committed` consumer does not see aborted outputs. |
| Consume-transform-produce success | Both output and input offset advance. |
| Consume-transform-produce failure | Output is not committed and input can be redelivered. |
| Duplicate producer request | Idempotent producer does not create duplicates from protocol retries. |
| Producer fencing | Old instance is rejected when the transactional ID is taken over. |
| Transaction timeout | Transactions exceeding the timeout are aborted as configured. |
| Read isolation | `read_uncommitted` and `read_committed` reflect correct semantics. |
| Listener rollback | After-rollback processor redelivers/recovers properly. |
| External DB side effect | Test proves Kafka transactions do not independently roll back the database. |

You can use EmbeddedKafka or Testcontainers. When testing transactions, create a consumer with `isolation.level=read_committed` to verify committed data; if comparison is needed, run an additional `read_uncommitted` consumer.

To verify offsets, use `AdminClient` to read the group's committed offsets and wait with Awaitility or a timeout latch. Do not rely on fixed `Thread.sleep`. When testing aborts, wait for the transaction to finish or time out before concluding that records are not visible.

## 20. Common mistakes when using transactions

| Mistake | Consequence | Resolution |
|---|---|---|
| Using the same transactional ID across multiple pods | Old producer gets fenced or transactions conflict | Prefix must be unique per running instance. |
| Downstream consumer uses `read_uncommitted` | May see uncommitted or aborted records | Use `read_committed` when transaction visibility is required. |
| Assuming transactions cover databases | DB and Kafka states can diverge | Use outbox/inbox or a suitable coordination mechanism. |
| Using only idempotent producer while expecting multi-topic atomicity | Partial publication can still succeed | Use transactions for atomic multi-record writes. |
| Listener sends output via a non-transactional producer | Output may commit independently of input offset | Use a `KafkaTemplate`/`ProducerFactory` participating in the container transaction. |
| Transaction held open too long | Timeouts, LSO held back, increased latency and lag | Keep transactions short and measure duration. |
| Retrying external side effects after abort | HTTP/email/DB operations may execute repeatedly | Use idempotency or outbox/inbox. |
| Treating exactly-once as "listener runs only once" | Misunderstanding redelivery behavior | Exactly-once applies to committed Kafka results in a properly configured pipeline. |
| Not handling fencing | Old instance keeps attempting transaction operations | Handle `ProducerFencedException` and producer lifecycle. |

## 21. Capstone exercise: atomic consume-transform-produce

Build the pipeline:

- Input topic: `orders.created`.
- Output topic: `orders.accepted`.
- Audit topic: `orders.audit`.
- Consumer group: `orders-fulfillment`.

Requirements:

1. Enable a transactional producer in Spring Boot using a unique transaction ID prefix per instance.
2. Configure the consumer with `isolation.level=read_committed`.
3. Send two output records to `orders.accepted` and `orders.audit` within a single producer transaction.
4. Verify that a `read_committed` consumer sees both records after commit.
5. Intentionally throw an exception before commit and verify neither output is visible to `read_committed`.
6. Configure a transactional listener container with `KafkaTransactionManager`.
7. Send output from the listener and verify the input offset is committed in the same transaction.
8. Simulate a crash/rollback and verify the input record can be redelivered.
9. Start two producers using the same transactional ID to observe fencing in a test environment.
10. Create a long-running transaction to observe timeout and LSO impact.
11. Add a database side effect and demonstrate that Kafka transactions do not automatically roll back the DB.
12. Design an outbox or inbox to handle the DB/Kafka boundary.
13. Write integration tests for commit, abort, `read_committed`, and offsets.
14. Measure transaction duration, commit latency, abort rate, and consumer lag.

The exercise is complete when you prove that outputs and input offsets commit/abort together in Kafka, explain the scope of exactly-once, and identify the mechanisms required when business logic touches a database or external service.

## 22. Learning path and completion criteria

| Stage | Core focus | Self-check criteria |
|---|---|---|
| 1. Failure model | Partial writes and duplicates | Describe two skewed states when publishing/committing separately. |
| 2. Atomic writes | Multi-topic/partition transactions | Prove that all outputs commit or abort together. |
| 3. Producer identity | `transactional.id` and fencing | Configure a unique ID per instance. |
| 4. Isolation | `read_committed`/`read_uncommitted` | Explain what data consumers observe. |
| 5. Consume-transform-produce | Output + input offset | Enlist offsets in the same transaction as outputs. |
| 6. Spring Kafka | `KafkaTemplate` and `KafkaTransactionManager` | Configure transactional producers and listener containers. |
| 7. Exactly-once | Scope of guarantees in Kafka | Distinguish committed outcomes from listener execution counts. |
| 8. External systems | Outbox, inbox, idempotency | Properly handle DB/Kafka boundaries and side effects. |
| 9. Operations | Timeouts, fencing, LSO | Monitor transaction duration and errors. |
| 10. Testing | Commit, abort, offsets, isolation | Test both success and failure branches. |

The lesson is complete when you can explain how Kafka transactions resolve partial writes and skew between outputs and input offsets, configure transactional producers/consumers in Spring Kafka, and correctly identify the boundaries when business logic reaches a database or external service.

Kafka transactions provide atomicity for data and offsets residing inside Kafka. They are the foundation for exactly-once consume-transform-produce, yet they do not turn the entire distributed system into a single transaction. To ensure business consistency across databases and Kafka, design outbox/inbox, idempotency, and recovery aligned with each system's boundaries.

