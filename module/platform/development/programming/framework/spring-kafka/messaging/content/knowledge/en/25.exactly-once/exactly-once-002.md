# Distinguishing at-most-once, at-least-once, and exactly-once

When a consumer reads a Kafka record, the application must decide when to acknowledge the offset relative to when processing completes. If acknowledged too early, the process may stop and lose the opportunity to process the record. If acknowledged too late, the process may stop after creating a side effect but before the offset is saved, causing the record to be redelivered and the side effect to potentially repeat.

The three delivery semantics describe how a system balances those two risks:

- **At-most-once**: a record is processed at most once; records may be lost if a failure occurs after the offset has been acknowledged.
- **At-least-once**: records are not skipped due to early acknowledgment; in exchange, they may be processed multiple times when commit fails or the consumer restarts.
- **Exactly-once**: the business outcome within the protected scope is recorded effectively once. With Kafka, the strongest guarantee applies to consume-transform-produce pipelines when output and input offsets are committed in the same Kafka transaction.

This lesson belongs to the **Exactly-once** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on offset commit timing, failure windows, Spring Kafka configuration, and the limits of exactly-once when a listener creates effects outside Kafka.

## Learning outcomes

After this lesson, you will be able to:

- Explain the differences between at-most-once, at-least-once, and exactly-once.
- Draw the failure window between record processing and offset commit.
- Predict when a record is lost and when a record may be redelivered.
- Choose the appropriate AckMode in Spring Kafka.
- Understand the role of `enable.auto.commit=false` and acknowledgment timing.
- Distinguish an idempotent producer from exactly-once processing.
- Configure a transactional listener to atomically commit output and input offsets.
- Understand `isolation.level=read_committed`.
- Design idempotency for databases and external side effects.
- Accurately determine the guarantee scope and test each semantics.

## 1. What does delivery semantics address?

Delivery semantics describes the relationship between receiving a message, performing processing, and confirming progress. In this lesson, the focus is on the consumer side: how many times a record may be redelivered and what results the application can produce when the process, broker, or network fails.

A Kafka consumer reads records by partition offset. The committed offset is the next position the consumer wants to read, not the offset of the last record just processed.

Example:

| Record just processed | Committed offset |
|---:|---:|
| 40 | 41 |
| 41 | 42 |
| 42 | 43 |

A consumer group stores offsets separately for each partition. When a consumer restarts or a partition is assigned to another member, the consumer resumes from the committed offset according to the reset policy and data still within retention.

The core question of the three semantics is: **is the offset acknowledged before or after processing completes, and how are processing results and offsets made atomic?**

## 2. At-most-once: acknowledge first, process later

At-most-once prioritizes avoiding duplicate processing. The consumer acknowledges the offset before performing side effects. If the process stops after committing but before finishing processing, Kafka considers the record consumed and will not automatically redeliver it to the group.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant K as Kafka
    participant S as Business service
    C->>K: Poll record offset 40
    C->>K: Commit next offset 41
    K-->>C: Commit acknowledged
    C->>S: Process record 40
    Note over C,S: Process crashes before completion
    Note over K: Restart continues from offset 41
~~~

Advantages:

- Avoids the consumer reprocessing a record solely because offset commit failed after a side effect.
- Useful when duplicates have severe consequences and losing some records within the failure window is acceptable.
- Simple processing flow if business requirements allow skipping records when the process fails.

Disadvantages:

- Records can be lost if the consumer stops after committing the offset but before completing processing.
- Unsuitable for business cases that require guaranteeing every event is processed.
- Does not guarantee external side effects completed; the offset may advance even if a database or HTTP call never ran.

At-most-once means a record is handed to processing logic at most once according to acknowledged progress. It does not mean the listener is guaranteed to be called once: a record might be processed zero times.

## 3. Configuring at-most-once in Spring Kafka

To illustrate at-most-once with a record listener, manual acknowledgment can be used to acknowledge immediately before running business logic. Consumer auto commit must be disabled so the container does not commit independently on a schedule.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

Listener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-at-most-once"
)
public void consume(
        OrderCreatedEvent event,
        Acknowledgment acknowledgment) {

    // Commit offset before creating side effects.
    acknowledgment.acknowledge();

    orderService.handle(event);
}
~~~

With `AckMode.MANUAL_IMMEDIATE`, acknowledgment called on the consumer thread requests an immediate commit. If the process stops after the acknowledge line but before or during `orderService.handle`, the record may not be redelivered.

This approach only illustrates at-most-once semantics. Use it only when the business accepts potential record loss. Do not call acknowledgment before dispatching an asynchronous task and assume that task will definitely complete.

## 4. At-least-once: process first, acknowledge later

At-least-once prioritizes not losing records due to early commits. The consumer acknowledges the offset only after the listener processes successfully. If the process stops after side effects but before offset commit, Kafka may redeliver the record.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant S as Business service
    participant K as Kafka
    C->>K: Poll record offset 40
    C->>S: Process record 40
    S-->>C: Processing succeeded
    C->>K: Commit next offset 41
    K-->>C: Commit acknowledged
~~~

If the process stops after successful processing but before commit:

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant S as Business service
    participant K as Kafka
    C->>K: Poll record offset 40
    C->>S: Process record 40
    S-->>C: Side effect completed
    Note over C,K: Process crashes before offset commit
    C->>K: Restart and poll from committed offset 40
    K-->>C: Record 40 is delivered again
    C->>S: Process record 40 again
~~~

Advantages:

- Unacknowledged records can be redelivered after a crash or rebalance.
- Suitable for business flows that prioritize not missing events.
- A common choice for consumers processing orders, payments, inventory, and audits.

Disadvantages:

- The listener may process the same record multiple times.
- Non-idempotent side effects may be duplicated.
- Deduplication or idempotency must be designed at the business boundary.

At-least-once is the common semantics when a consumer processes a record and then commits the offset. This is usually the right starting point for Spring Kafka applications.

## 5. Configuring at-least-once in Spring Kafka

Disable auto commit and let the listener container commit after successful processing. You can choose `RECORD` to commit after each record or `BATCH` to commit after successfully processing the records of a poll.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

Listener example:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment"
)
public void consume(OrderCreatedEvent event) {
    orderService.handle(event);
}
~~~

With `AckMode.RECORD`, the container commits the offset after the listener successfully processes the record. If the listener throws an exception, the error handler decides on retry or recovery; the offset is not considered successfully processed merely because the listener was invoked.

With `AckMode.BATCH`, the container commits offsets for the poll's records after the batch is successfully processed according to container semantics. Both approaches can achieve at-least-once when commits occur after processing and auto commit is disabled.

Do not enable `enable.auto.commit=true` while assuming AckMode controls the entire commit timing. Auto commit can advance offsets independently of business processing.

## 6. Exactly-once: output and offset commit together

Exactly-once in Kafka consume-transform-produce is built with transactions. The consumer reads the input, the producer sends the output, and then the input offset is added to the same transaction. Kafka commits or aborts the entire unit.

~~~mermaid
flowchart TD
    A[Consume input record] --> B[Transform]
    B --> C[Begin Kafka transaction]
    C --> D[Produce output record]
    D --> E[Add input offset to transaction]
    E --> F{Commit transaction}
    F -->|Commit| G[Output visible and input offset advances]
    F -->|Abort| H[Output is aborted and input offset stays]
    H --> I[Input can be redelivered]
~~~

Result:

- Successful commit: the output is published and the input offset advances with the transaction.
- Abort: the transaction's output is not visible to `read_committed` consumers, the input offset is not committed in that transaction, and the record may be redelivered.
- Downstream consumers use `read_committed` to read only output from committed transactions.

Exactly-once does not mean the listener method is invoked only once. The listener may execute again after an abort or crash. What is guaranteed is that committed Kafka results are not duplicated by the failure window between output and input offset in a properly configured pipeline.

## 7. Comparing the three semantics

| Criterion | At-most-once | At-least-once | Exactly-once in Kafka |
|---|---|---|---|
| Acknowledgment timing | Before processing | After successful processing | In the same transaction as output |
| Can lose records on crash | Yes | No due to early commit, if retention and recovery suffice | No due to mismatch between output and offset in transaction |
| Can process repeatedly | Normally avoids redelivery after commit | Yes | Listener may still run again, but committed Kafka transaction output does not duplicate due to failure window |
| Main mechanism | Commit before side effect | Process then commit | Transactional producer + offset in transaction |
| Complexity | Low | Medium; requires idempotency | Higher; requires transactions and appropriate isolation |
| Suitability | Record loss is acceptable | Must not miss processing, accepts dedupe | Kafka consume-transform-produce requiring atomicity |

You can remember them by order:

- At-most-once: **commit → process**.
- At-least-once: **process → commit**.
- Exactly-once: **process + output + offset in the same transaction**.

## 8. Failure windows determine semantics

Consider a consumer reading record offset 40 and creating a business change.

| Timing when process stops | At-most-once | At-least-once | Exactly-once Kafka |
|---|---|---|---|
| Before processing | If offset is not committed, record may be read again; if committed, it may be lost | Offset not committed so record may be read again | Transaction not committed; input may be redelivered |
| After side effect but before commit | Offset was committed earlier; record is not redelivered even though side effect may or may not have finished | Record is redelivered; side effect may repeat | If side effect is Kafka output in an uncommitted transaction, output is aborted along with offset |
| After commit | Record is not redelivered per saved offset | Record is not redelivered per saved offset | Output and input offset are committed together |
| Commit response lost | May not know whether commit succeeded; need to inspect offset | May get redelivery if commit was not saved | Transaction protocol determines state; application must handle commit results per Kafka client |

This table assumes consumer group, offsets, and transactions are configured properly, while excluding retention deleting records before the consumer recovers.

Key point: Kafka exactly-once only closes the failure window for operations inside the Kafka transaction. If a listener updates a database outside the transaction and then the Kafka transaction aborts, the database may still have changed.

## 9. Producer idempotence is not the same as exactly-once

Producer idempotence helps Kafka eliminate duplicates from a producer retrying the same request at the protocol level, using producer ID and sequence number.

~~~properties
enable.idempotence=true
acks=all
~~~

This mechanism does not automatically guarantee:

- That a business event is not resent by the application from a new process.
- That a consumer does not reprocess a record after a crash.
- That output and input offset are committed atomically.
- That database or HTTP side effects are not repeated.

| Mechanism | Main guarantee |
|---|---|
| Idempotent producer | Reduces duplicates from retries at the producer protocol layer. |
| Consumer idempotency | One event ID does not create repeated business side effects. |
| Kafka transaction | Atomicity between multiple output records and input offsets in Kafka. |
| Outbox/inbox | Durable coordination between database and event publishing/receiving. |

An application can use an idempotent producer while still operating at-least-once on the consumer. For Kafka consume-transform-produce exactly-once, a transaction encompassing output and input offset is required.

## 10. Configuring transactional producer in Spring Boot

Spring Boot can configure a transaction ID prefix for the producer:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${HOSTNAME:orders-service}-tx-
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

The transaction ID prefix must be unique across concurrently running application instances. In Kubernetes, the pod name or a unique instance ID can be used. If every pod uses the same prefix without a distinguishing suffix, producers may fence each other.

When transactions are configured, Spring Kafka can create a transaction-supporting ProducerFactory and KafkaTransactionManager according to the auto-configuration mechanism of the corresponding Spring Boot version.

`read_committed` on the consumer ensures downstream receives only records from committed transactions. A `read_uncommitted` consumer can see records from uncommitted or aborted transactions, defeating the visibility guarantee that an exactly-once pipeline aims for.

## 11. Configuring a transactional listener container

For consume-transform-produce, the listener container starts a transaction before invoking the listener. KafkaTemplate sends output participating in that transaction. When the listener completes, the container adds the input offset to the transaction and commits.

Conceptual configuration example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
transactionalListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        KafkaTransactionManager<String, Object> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);

    return factory;
}
~~~

Listener:

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

Ensure KafkaTemplate uses the same transactional ProducerFactory compatible with the container's transaction. If the listener sends using an independent producer that does not participate in the transaction, the output may commit separately while the input offset rolls back.

Setter names and how the transaction manager is declared depend on the Spring Kafka version. Use the API compatible with the project's dependencies; then test both commit and rollback.

## 12. Transaction rollback and redelivery

If the listener throws an exception before the transaction commits, the container rolls back the transaction. Output records sent within the transaction are aborted; the input offset is not committed in that transaction.

Spring Kafka uses `DefaultAfterRollbackProcessor` to decide on redelivery, retry, or recovery of the record after a rollback. This is the mechanism to examine for transactional listeners; do not mechanically apply `DefaultErrorHandler` configurations from non-transactional flows.

A listener can still be invoked multiple times:

~~~text
Attempt 1:
  read input -> produce output -> exception -> abort

Attempt 2:
  read input again -> produce output -> success -> commit
~~~

Attempt 1's output is not visible to `read_committed` consumers. Attempt 2's output is published along with the input offset. That is how Kafka exactly-once protects the final result, even though processing code may execute multiple times.

If the listener creates side effects outside Kafka before throwing an exception, those side effects are not rolled back with the Kafka transaction. Use idempotency or outbox/inbox for that part.

## 13. Exactly-once with Kafka Streams

If the application uses Kafka Streams instead of manual listeners, you can configure the processing guarantee:

~~~properties
processing.guarantee=exactly_once_v2
~~~

Kafka Streams manages transactions for reading inputs, writing outputs, and updating state stores/changelogs according to framework semantics. `exactly_once_v2` is the modern choice for Kafka Streams applications in supported versions.

This is a Kafka Streams mechanism. In standard Spring Kafka listeners, you must configure the transactional producer, listener container, and offset-in-transaction as described above. Do not use a Kafka Streams property to enable exactly-once for a regular `@KafkaListener`.

## 14. Exactly-once and databases: idempotency or outbox/inbox is needed

Suppose a listener reads `orders.created`, updates a database, and emits `orders.accepted`. A Kafka transaction does not automatically roll back the database if the Kafka transaction aborts.

Two systems with independent transaction managers do not automatically become an atomic distributed transaction just by residing in the same Java method.

Options:

- **Idempotency**: use an event ID and unique constraint so one event does not create repeated side effects.
- **Inbox**: store the processed event ID in the same database transaction as the business change.
- **Outbox**: write the business change and an outbox row in the same database transaction; a relay/CDC publishes the outbox to Kafka.
- **Saga/compensation**: when a business process spans multiple independent systems, design compensating steps rather than assuming a global rollback.

Inbox example:

~~~java
@Transactional
public void handle(OrderCreatedEvent event) {
    if (inboxRepository.existsByEventId(event.eventId())) {
        return;
    }

    orderRepository.create(event);
    inboxRepository.insert(event.eventId());
}
~~~

In production, `event_id` needs a unique constraint, and the inbox insert must be in the same transaction as the business change. If you only check existence and then insert without a unique constraint, two concurrent executions could both pass the check.

## 15. Choosing semantics by business case

| Use case | Usually suitable semantics | Reason |
|---|---|---|
| Telemetry where losing a few samples is acceptable, duplicates are costly | At-most-once or best-effort | Data loss in the failure window is acceptable. |
| Audit logs, orders, payment events | At-least-once + idempotency | Prioritize not missing events; prevent duplicate side effects. |
| Consumer transforms topic A to B, needing atomic output and offset | Exactly-once Kafka | Transaction combines output and input offset. |
| Update database then emit Kafka | Outbox + at-least-once relay + idempotent consumer | Protects the DB/Kafka boundary. |
| Kafka Streams aggregate/stateful pipeline | Exactly-once v2 if requirements fit | Framework manages transactions for state and output. |
| Send email/SMS from events | At-least-once + idempotency/deduplication | Kafka transactions cannot recall a sent email. |

No semantics is automatically best for every use case. You must evaluate the cost of losing records, cost of duplicates, ordering requirements, and side-effect boundaries.

## 16. Common misconceptions

| Misconception | Reality |
|---|---|
| At-most-once means guaranteed processing exactly once | It may process zero times if the process stops after an early commit. |
| At-least-once means duplicates always happen | Duplicates can happen, but do not happen every time. |
| Exactly-once means the listener is called only once | The listener can run again; committed Kafka results are what is protected. |
| Producer idempotence gives end-to-end exactly-once | It mainly handles duplicates from producer protocol retries. |
| `read_committed` creates transactions by itself | It only controls visibility of transactional records. |
| Kafka transactions can roll back a database | Kafka transactions do not cover independent databases. |
| Successful offset commit proves business success | True only if commit timing is tied to business completion by design. |
| Exactly-once does not need idempotency | Side effects outside Kafka and replays still require idempotency. |

## 17. Testing the three delivery semantics

Tests should simulate crashes at different points, rather than only checking that the listener received a record.

| Scenario | At-most-once | At-least-once | Exactly-once Kafka |
|---|---|---|---|
| Crash before processing | Record may have been committed early and lost | Record is redelivered if not committed | Input not committed in transaction, can be redelivered |
| Crash after side effect before commit | Not redelivered if offset committed | Can redeliver and repeat side effect | Kafka output in transaction aborts; input can be redelivered |
| Successful commit | Not redelivered | Not redelivered | Output and offset commit together |
| Consumer restart | Resumes from acknowledged offset | May re-read uncommitted records | Resumes from transactionally committed offset |
| Downstream read isolation | Not relevant without transactions | Not relevant without transactions | Use read_committed to see only committed output |

Tests to include:

- Stop the consumer/process after commit before processing to verify at-most-once can lose records.
- Stop the process after side effects before commit to verify at-least-once redelivery.
- Abort the transaction after sending output to verify output is not visible to read_committed.
- Commit the transaction to verify output and input offset advance together.
- Resend the same event ID to verify database idempotency.
- Test producer fencing when a transactional ID is used concurrently.
- Read committed offsets using AdminClient after the test meets its condition.
- Use EmbeddedKafka or Testcontainers and Awaitility/latches with timeouts; do not use fixed Thread.sleep.

When testing exactly-once, create the test consumer with `isolation.level=read_committed`. Reading with `read_uncommitted` could let the test see records from uncommitted or aborted transactions and draw wrong conclusions.

## 18. Observability and operations

Metrics that help evaluate delivery semantics in production:

- Consumer lag and lag growth rate per partition.
- Listener failure, retry, and redelivery counts.
- Transaction commit/abort counts.
- Transaction duration and commit latency.
- Producer retries, timeouts, and fencing exceptions.
- Number of event IDs deduplicated in the inbox.
- Number of records routed to DLT.
- Success and failure rates of database/downstream side effects.

Logs should include topic, partition, offset, event ID, correlation ID, group ID, and necessary transaction state. Do not log sensitive payloads.

If a transaction stays open too long, `read_committed` consumers can be bounded by the Last Stable Offset (LSO), preventing subsequent records from being returned even though they are already written to the log. Monitor transaction duration, abort rate, and lag together to distinguish a slow broker from incomplete transactions.

## 19. Capstone exercise: comparing three semantics for OrderCreatedEvent

Build three independent listeners reading topic `orders.created`:

1. Listener A runs at-most-once using manual immediate acknowledgment before side effects.
2. Listener B runs at-least-once using `AckMode.RECORD` and auto commit disabled.
3. Listener C runs transactional consume-transform-produce, writing `orders.accepted` and committing the input offset in the same transaction.

Requirements:

- Send the same set of events with stable eventIds.
- Simulate process stopping before processing.
- Simulate process stopping after side effects but before commit.
- Simulate listener throwing an exception and transaction aborting.
- Read output using a `read_committed` consumer.
- Compare the number of listener invocations, committed output records, and database side effects.
- Add an inbox/unique constraint to the database to prevent duplicates.
- Use AdminClient to inspect group offsets after each scenario.
- Document which records can be lost, which can be redelivered, and which outcomes are guaranteed.
- Recommend semantics for the order flow and explain trade-offs.

The exercise is complete when you prove the failure window of each semantics and distinguish listener invocation counts from effective business outcome counts.

## 20. Learning path and completion criteria

| Stage | Core content | Self-check criterion |
|---|---|---|
| 1. Offset model | Next offset to read | Correctly compute the committed offset after a record. |
| 2. At-most-once | Commit before processing | Explain the failure window causing record loss. |
| 3. At-least-once | Process before commit | Explain redelivery and duplicates. |
| 4. Spring AckMode | RECORD, BATCH, MANUAL_IMMEDIATE | Choose the right acknowledgment timing. |
| 5. Producer idempotence | Retry protocol | Distinguish producer dedupe from consumer semantics. |
| 6. Kafka transaction | Output + input offset atomicity | Commit or abort both together. |
| 7. Read isolation | read_committed | Read only committed transactional output. |
| 8. External effects | Inbox, outbox, idempotency | Protect databases and services outside Kafka. |
| 9. Testing | Crash window and transaction rollback | Test loss, duplicates, and redelivery. |
| 10. Operations | Lag, abort, retry, and dedupe metrics | Properly monitor processing quality in production. |

The lesson is complete when you can accurately explain the commit timing of at-most-once and at-least-once, configure all three approaches in Spring Kafka, and clearly state what outcomes exactly-once protects in Kafka. You must also identify why databases, HTTP, and external side effects still need idempotency or outbox/inbox.

At-most-once trades potential record loss to avoid redelivery; at-least-once prioritizes not missing records but must tolerate duplicate processing; Kafka exactly-once coordinates output and input offsets within the same transaction. Choose semantics based on business risk and system boundaries, not just configuration names.

