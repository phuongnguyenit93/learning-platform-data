# Rollback When a Listener Fails

In Spring Kafka, a listener can run inside a Kafka transaction managed by the listener container. The container opens a transaction before invoking the listener method, then sends the processed offset into the same Kafka transaction. If the listener completes normally, the transaction commits and the offset is recorded together with any Kafka records emitted by the application inside the transaction. If the listener throws an exception, the transaction rolls back; the offset is not committed, so the record can be read and reprocessed.

This mechanism is especially useful for consume-process-produce flows: the consumer receives an event, runs business logic, and emits a follow-up event. When processing fails, Kafka can roll back both the output records and the input offset in the same transaction. However, rollback does not automatically undo side effects already committed to a database or external HTTP service. You must design idempotency, transaction synchronization, or outbox/inbox when the listener interacts with external systems.

This lesson belongs to the **Transactions** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while learning serialization, retries, dead-letter handling, transactions, exactly-once, concurrency, and testing to operate reliable messaging pipelines.

## 1. What is rollback in a listener container?

With a transactional listener container, a Kafka transaction wraps record or batch processing. The container is responsible for starting the transaction, invoking the listener, and finalizing the transaction based on the processing outcome.

Record listener flow:

~~~mermaid
flowchart TD
    A[Consumer polls record] --> B[Container begins Kafka transaction]
    B --> C[Invoke @KafkaListener]
    C --> D{Listener succeeds?}
    D -->|Yes| E[Send offset to transaction]
    E --> F[Commit Kafka transaction]
    D -->|No, throws exception| G[Rollback Kafka transaction]
    G --> H[AfterRollbackProcessor]
    H --> I[Retry and seek to re-read]
    H --> J[Recover or send to DLT]
~~~

When the transaction commits, the record's offset is committed with the transaction. When the transaction rolls back, the offset has not been committed in the group. The consumer can re-read that record after the container seeks or after the consumer restarts.

Rollback is triggered by an exception escaping the listener invocation. If the listener catches the exception and returns normally, the container generally treats the invocation as successful and proceeds to commit the transaction.

## 2. Configuring Kafka transactions for a listener container

For the listener container to manage Kafka transactions, `ProducerFactory` must be configured as transactional via a transaction ID prefix. Every concurrently running application instance needs a unique prefix to avoid transactional ID collisions and unwanted producer fencing.

Spring Boot example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-service-instance-a-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Key points:

- `transaction-id-prefix` enables transactional producers via `ProducerFactory`.
- The prefix must differ across concurrently running instances.
- `enable-auto-commit` must be disabled so the container manages offsets.
- `read_committed` ensures consumers read only records belonging to committed Kafka transactions.
- The consumer group needs permissions to read the topic and join the group; the producer needs topic write permissions and appropriate transactional ID permissions.

Do not use the same static transaction ID prefix across all replicas. In containerized environments, inject a stable, unique instance identity into the configuration.

## 3. Attaching `KafkaTransactionManager` to the container factory

You can create `KafkaTransactionManager` from `ProducerFactory` and attach it to container properties:

~~~java
@Bean
public KafkaTransactionManager<String, OrderEvent>
        kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTransactionManager);

    return factory;
}
~~~

`setKafkaAwareTransactionManager` is the API for a Kafka-aware transaction manager in modern Spring Kafka versions. In older versions, you may encounter the deprecated `setTransactionManager` API. Use the API matching your project's dependency version.

The listener specifies the factory:

~~~java
@KafkaListener(
    id = "orderProcessor",
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    orderService.process(event);
}
~~~

Only a container factory with the transaction manager attached creates a transactional boundary around listener invocations. Declaring a `KafkaTransactionManager` bean without attaching it to the container factory is insufficient to ensure the listener runs inside a Kafka transaction.

## 4. Listener succeeds: committing outputs and offsets

Suppose a listener receives `OrderCreated`, writes another event to Kafka, and completes normally:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    OrderValidated validated = orderService.validate(event);

    kafkaTemplate.send(
        "validated-orders",
        event.orderId(),
        validated
    );
}
~~~

If `KafkaTemplate` uses a transactional `ProducerFactory` compatible with the container transaction, the sent record joins the current transaction. When the listener completes successfully, the container sends the input offset into the Kafka transaction and commits.

For downstream consumers using `read_committed`, output records become visible only after the transaction commits. The input offset is also committed in the Kafka transaction, avoiding a state where output is committed while the input offset is still unrecorded in that same Kafka transaction.

This is the foundation of consume-process-produce transactions in Kafka. It does not cover database or HTTP side effects unless those resources have separate coordination mechanisms.

## 5. Listener throws an exception: what gets rolled back?

For example, a listener processes an event, emits output, and then fails at the final step:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    OrderValidated validated = orderService.validate(event);

    kafkaTemplate.send(
        "validated-orders",
        event.orderId(),
        validated
    );

    throw new IllegalStateException("Cannot complete processing");
}
~~~

When the exception escapes the listener:

1. The listener invocation fails.
2. The current Kafka transaction is rolled back.
3. Output records sent in the transaction are aborted and are not visible to `read_committed` consumers.
4. The input offset is not committed in that transaction.
5. `AfterRollbackProcessor` is invoked to decide seek, retry, or recovery.
6. The record can be redelivered.

Rolling back a Kafka transaction does not automatically undo an already-succeeded HTTP request, a sent email, or an independently committed database transaction. Those side effects require idempotency or a separate transaction coordination design.

## 6. Exceptions must escape the listener to trigger rollback

If the listener catches an exception and does not rethrow it, the container does not know business processing failed:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    try {
        orderService.process(event);
    }
    catch (Exception exception) {
        log.error("Order processing failed", exception);
        // Returns normally: the container may commit the transaction.
    }
}
~~~

This approach can cause the offset to commit even though business processing did not complete. To trigger rollback, rethrow the exception:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-processor",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    try {
        orderService.process(event);
    }
    catch (Exception exception) {
        log.error("Order processing failed", exception);
        throw exception;
    }
}
~~~

If you need to log or add context, preserve the original exception as the cause when wrapping:

~~~java
throw new OrderProcessingException(
    "Unable to process order " + event.orderId(),
    exception
);
~~~

Do not merely return an error result or log and return if the contract requires the container to retry the record.

## 7. Distinguishing container rollback from `@Transactional` on a service

Two transaction boundaries can exist inside a listener:

- The Kafka transaction managed by the listener container.
- A database transaction managed by a `DataSource`/JPA transaction manager inside a service.

Service example:

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final OrderRepository repository;

    @Transactional(transactionManager = "dbTransactionManager")
    public void process(OrderEvent event) {
        Order order = repository.findById(event.orderId())
            .orElseThrow();

        order.validate();
        repository.save(order);
    }
}
~~~

If the database transaction rolls back and the exception escapes the listener, the Kafka container transaction also rolls back. However, if the database transaction already committed successfully and a later step causes the Kafka transaction to roll back, the database does not automatically revert to its prior state.

In a listener container model where the Kafka transaction is primary, the database transaction is synchronized via Spring's mechanism when configured properly. Commit order and failure windows must be tested; never infer that both resources always commit atomically.

If the business logic must ensure database updates and event emission do not drift apart, consider transactional outbox on the producer side or inbox/idempotency on the consumer side.

## 8. Record listeners and batch listeners have different rollback scopes

Transaction scope corresponds to how the listener container invokes the listener:

| Mode | Unit of listener invocation | When the listener throws an exception |
| --- | --- | --- |
| Record listener | One record per invocation | The failing record's transaction rolls back; the failing record is reprocessed per after-rollback policy. |
| Batch listener | One batch from a poll per invocation | The batch's transaction rolls back; unacknowledged batch/records can be re-read per the processor. |

With a record listener, records successfully processed before the failing record have normally finished their own transactions. The failing record and remaining records from the poll can be sought for re-reading.

With a batch listener, multiple records are processed in a single invocation. If the method throws an exception, the entire batch transaction can roll back. This means records processed before the error in the same batch can also be redelivered. Batch code should be idempotent.

If you need to pinpoint the failing record in a batch, you can use a batch error handling mechanism suited to your Spring Kafka version, such as `BatchListenerFailedException` or `BatchToRecordAdapter` where appropriate. Never assume partial progress is automatically preserved once the batch transaction rolls back.

## 9. How are offsets managed in a transactional listener?

In a transactional listener container, processed record offsets are sent into the Kafka transaction via transactional offset commits. When the transaction commits, output records and input offsets commit as one Kafka transaction.

When the transaction rolls back:

- The input offset is not committed.
- Output records in the transaction are aborted.
- The container/`AfterRollbackProcessor` determines which records to seek or retry.
- Records can be re-read after rollback.

`enable.auto.commit` should be disabled to prevent the Kafka client from auto-committing offsets outside container-managed transactions. Do not manually call consumer `commitSync`/`commitAsync` inside a transactional listener without thoroughly understanding how it interacts with the container.

For downstream consumers, `read_committed` filters out records from aborted transactions. It does not replace error handling or idempotency; it only controls Kafka transaction visibility.

## 10. What does `AfterRollbackProcessor` do?

`AfterRollbackProcessor` is invoked by the listener container after a transaction rolls back. The processor decides how to handle incomplete records:

- Seek back to the failing record's offset to re-read it.
- Reprocess remaining records from the poll.
- Apply retry/backoff.
- After retries are exhausted, invoke a recoverer to send the failing record to a DLT or perform other recovery handling.
- In an appropriate configuration, commit the recovered record's offset in a new Kafka transaction.

`DefaultAfterRollbackProcessor` is the common implementation. It supports retry, backoff, and post-rollback recovery for transactional listener containers.

This is a dedicated mechanism for the rollback path of transactional containers. For listener containers not using Kafka transactions, errors are normally handled by a `CommonErrorHandler` such as `DefaultErrorHandler`. Do not equate the two mechanisms because their execution points and offset semantics differ.

## 11. Configuring `DefaultAfterRollbackProcessor`

You can configure post-rollback retries using `DefaultAfterRollbackProcessor` and `FixedBackOff`:

~~~java
@Bean
public DefaultAfterRollbackProcessor<String, OrderEvent>
        afterRollbackProcessor(
            DeadLetterPublishingRecoverer recoverer,
            KafkaTemplate<Object, Object> kafkaTemplate) {

    DefaultAfterRollbackProcessor<String, OrderEvent> processor =
        new DefaultAfterRollbackProcessor<>(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    processor.setCommitRecovered(true);
    processor.setKafkaTemplate(kafkaTemplate);

    return processor;
}
~~~

This example configures a one-second interval and two retries after the initial attempt. Once retries are exhausted, the recoverer is invoked to handle the failing record.

`setCommitRecovered(true)` instructs the processor to commit the recovered record's offset. You must supply a transactional `KafkaTemplate`, and the listener container must use `KafkaTransactionManager` so the recovered record's offset is committed in a new Kafka transaction. Consequently, a record successfully sent to the DLT is not repeatedly re-read merely because the source offset was not recorded.

The configuration above is an example for a record listener. Actual generic types, `KafkaTemplate`, and serializers must match your application's key/value types; for deserialization failures, the template must also support raw `byte[]` if preserving the raw payload is needed.

## 12. Attaching `AfterRollbackProcessor` to the container factory

Attach the processor to the factory used by the listener:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager,
            DefaultAfterRollbackProcessor<String, OrderEvent>
                afterRollbackProcessor) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTransactionManager);
    factory.setAfterRollbackProcessor(afterRollbackProcessor);

    return factory;
}
~~~

The factory has two related configurations with distinct responsibilities:

- `KafkaTransactionManager` opens/commits/rolls back the Kafka transaction around the listener.
- `AfterRollbackProcessor` decides how to handle records after a transaction rolls back.

If the application has multiple listener container factories, attach the processor to the right factory. Simply declaring a processor bean does not ensure every container automatically uses it.

## 13. Retry and backoff after rollback

Retries handle transient failures that may resolve on their own, such as temporary database unavailability or a downstream HTTP 503. Backoff inserts pauses between attempts to avoid flooding an overloaded dependency with continuous requests.

Example:

~~~java
new FixedBackOff(2_000L, 3L)
~~~

This configuration waits two seconds between retries and limits retries to three after the initial attempt. Total listener attempts are typically the initial attempt plus the retry count; inspect actual logs/metrics to avoid confusing `maxAttempts` with total invocations.

Classify errors before choosing retries:

| Error type | Suggested handling |
| --- | --- |
| Temporary database connection timeout | Finite retries with backoff. |
| HTTP 503 or rate limit | Retry with backoff, honoring `Retry-After` if supported by the application. |
| Event payload violates contract | Do not retry for long; recover to DLT per appropriate policy. |
| Permanent business rule violation | Do not auto-retry if the data cannot self-correct. |
| Code bug | Stop futile retry loops, alert, and escalate to investigation. |

You can configure non-retryable exceptions using the processor's classification API, for example:

~~~java
processor.addNotRetryableExceptions(InvalidOrderEventException.class);
~~~

Verify the API and semantics for your Spring Kafka version. Do not mark transient errors as non-retryable if the system can recover shortly.

## 14. Poison records and routing to DLT

A poison record is a record that consistently causes the listener to fail, such as an invalid payload or a contract-violating event. With infinite retries, the partition could stop making progress.

After a finite number of attempts, a recoverer can send the record to a DLT:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(dltTemplate);
}
~~~

With the common default resolver, records from the source topic are sent to a topic suffixed with `.DLT`, preserving the source partition index. The DLT must have matching partitions, or you must use a custom destination resolver suited to your topology.

When combined with `setCommitRecovered(true)`, the processor can publish the failing record and commit the recovered offset inside a new Kafka transaction. If the DLT publish fails, recovery is not treated as successful; the source record continues to be handled per retry/recovery policy.

The DLT should preserve source metadata such as topic, partition, offset, timestamp, and exception details for operational investigation. Do not log full payloads if they contain sensitive data.

## 15. Committing recovered offsets in a new transaction

Once retries are exhausted and the recoverer has processed the record, the application must ensure the consumer group advances past that record. If it only publishes to the DLT without committing the source offset, the record could be re-read after a restart/rebalance and sent to the DLT again.

`setCommitRecovered(true)` together with `KafkaTemplate` allows `DefaultAfterRollbackProcessor` to commit the recovered record's offset in a new transaction.

~~~mermaid
flowchart TD
    A[Listener fails] --> B[Rollback initial transaction]
    B --> C[Retry with backoff]
    C --> D{Retries left?}
    D -->|Yes| A
    D -->|No| E[Recoverer publishes to DLT]
    E --> F{Publish succeeds?}
    F -->|No| G[Recovery fails, continue error handling]
    F -->|Yes| H[Open new Kafka transaction]
    H --> I[Commit recovered record offset]
    I --> J[Commit new transaction]
    J --> K[Partition advances]
~~~

Publishing to the DLT and committing the recovered offset in a new transaction keeps those two Kafka operations consistent with each other. It does not include external database transactions and does not eliminate duplicates if recovery or the application fails at other boundaries.

## 16. Batch listener rollback and per-record processing

With a batch listener, the listener receives multiple records in a single invocation. If the method throws an exception, the batch invocation's transaction rolls back. Records processed earlier in the same batch before the failure can be redelivered, because the batch offset was not committed.

Example:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-processor",
    containerFactory = "orderBatchListenerFactory"
)
public void onBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }
}
~~~

If processing the third record fails and an exception escapes, the entire batch transaction can roll back. Earlier records that succeeded in the loop can still be re-read. Therefore, operations in a batch must be idempotent.

If you want per-record processing and retries, consider a record listener or an appropriate batch-to-record mechanism. `BatchToRecordAdapter` can help turn a batch into record listener invocations in some configurations; check the transaction and error handling semantics of your version.

Do not assume `BatchListenerFailedException` automatically creates an independent transaction per element. Commit/rollback scope depends on container mode and processor configuration.
## 17. Database side effects do not automatically roll back with Kafka

Example of a listener updating a database and then throwing an exception:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "billing-service",
    containerFactory = "transactionalListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    billingService.updateInvoice(event);
    throw new IllegalStateException("Error after updating database");
}
~~~

If `updateInvoice` already committed its own database transaction before the exception escaped, rolling back the Kafka transaction cannot undo that change. When the record is re-read, the invoice could be updated again.

Ways to reduce risk:

- Make the handler idempotent by event ID.
- Write an inbox/processed event marker in the same database transaction as the business change.
- Synchronize the database transaction with the Kafka transaction where appropriate and accept the failure window.
- Use outbox for emitting events from the database.
- Avoid invoking irreversible side effects before knowing the transaction will commit.

If a service method uses `@Transactional` and must roll back on checked exceptions, declare `rollbackFor` appropriately because default Spring transactions normally roll back on `RuntimeException` and `Error`, not automatically on every checked exception. The Kafka listener container still needs to receive the exception to roll back the Kafka transaction.

## 18. Non-blocking retry and transactional listeners

Non-blocking retry via retry topics is a different model from blocking retry after rollback. It moves records to retry topics and lets the source partition continue processing later records.

Do not combine retry topics with a transactional listener container by default. Spring Kafka has version-dependent compatibility constraints; non-blocking retry is not supported with container transactions in common configurations. When transaction rollback and retry are needed, prefer `AfterRollbackProcessor` with blocking retry, or redesign the retry flow as a separate pipeline not relying on a transactional listener container.

If choosing retry topics, understand that ordering can change: later events can be processed ahead of events waiting on a retry topic. This affects same-key aggregates and business sequences.

## 19. How do `DefaultErrorHandler` and `AfterRollbackProcessor` differ?

The two components serve similar roles, yet operate on different execution paths:

| Component | When used | Role |
| --- | --- | --- |
| `DefaultErrorHandler` | Listener containers not using Kafka transactions on the rollback path | Retries/recovers exceptions via common error handling. |
| `AfterRollbackProcessor` | Transactional listener containers after Kafka transaction rollback | Seeks/retries/recovers uncommitted records after rollback. |
| `DefaultAfterRollbackProcessor` | Default implementation of `AfterRollbackProcessor` | Provides backoff, retry, and recovery after rollback. |
| `DeadLetterPublishingRecoverer` | Used by error handlers/rollback processors | Publishes recovered records to a DLT. |

When using Kafka transactions for a listener, configure `AfterRollbackProcessor` to control the post-rollback retry path. Do not configure `DefaultErrorHandler` assuming it completely replaces after-rollback processing.

Read the documentation for your exact Spring Kafka version because error handling APIs and how containers combine handlers have evolved across versions.

## 20. Testing rollback when a listener fails

Integration tests should use real Kafka via Testcontainers or Embedded Kafka matching the project version. Verify transaction visibility, offsets, and retry behavior.

Scenarios:

1. Listener succeeds: output record and input offset commit.
2. Listener throws exception: Kafka transaction rolls back and output record is not visible to `read_committed` consumers.
3. Input record is re-read after rollback.
4. Retry/backoff executes the configured number of times.
5. Retries exhausted: recoverer publishes the record to DLT.
6. `commitRecovered=true`: source offset advances after DLT publish succeeds.
7. DLT publish fails: record is not treated as recovered and offset does not advance erroneously.
8. Batch listener fails: confirm the batch scope rolls back and records can be redelivered.
9. Listener catches exception and returns: confirm the container treats the invocation as successful under the current design.
10. Database side effect: confirm idempotency/inbox prevents duplicate side effects.
11. Downstream `read_committed` consumer does not see records from aborted transactions.
12. Rebalance/restart during retries: confirm no records are lost and duplicates are handled safely.

Use unique event IDs, latches, or Awaitility with timeouts. Do not only assert that the listener method was called; read output/DLT topics and inspect committed offsets or redelivery behavior.

## 21. Observing and operating rollbacks

Monitor the following metrics and logs:

- Kafka transaction commit and abort counts.
- Listener exception counts by topic/group.
- Rollback and retry counts per record.
- Backoff duration and listener processing time.
- DLT publish successes/failures.
- Consumer lag and offset progression.
- Producer fencing or transactional ID collisions.
- Duplicate events detected by idempotency/inbox.
- Rebalances while a listener is retrying.

Logs should include topic, partition, offset, group ID, event ID, and exception class. Do not log full payloads if they contain sensitive data.

If rollbacks spike, check producer schema changes, downstream availability, database connection pools, code bugs, and transaction timeouts. A recurring poison record on the same partition typically needs to be identified via source offset and retry count.

## 22. Rollback design checklist

Before deploying a transactional listener, confirm:

1. `ProducerFactory` has a unique transaction ID prefix per instance.
2. The listener container has `KafkaTransactionManager` attached.
3. Consumer auto-commit is disabled.
4. Consumers reading transactional outputs use `read_committed`.
5. Business exceptions escape the listener when rollback is needed.
6. Exceptions are not swallowed and returned unless commit is intended.
7. `AfterRollbackProcessor` is attached to the right factory.
8. Retry/backoff is finite and matched to the error type.
9. The DLT has compatible partition topology and serializers.
10. Committing recovered offsets is enabled only when recovery and the new transaction are configured properly.
11. Batch listeners account for the fact that rollback can redeliver the whole batch.
12. Database/HTTP side effects have idempotency or separate coordination mechanisms.
13. Checked exceptions have appropriate `rollbackFor` on database transactions.
14. Integration tests cover commit, rollback, retry, DLT, and redelivery.
15. Metrics/logs detect poison records, retry storms, and fencing.

When a listener fails inside a transactional container, Kafka transaction rollback prevents output records and input offsets from committing as a successful transaction. `AfterRollbackProcessor` controls seek, retry, and recovery; `DefaultAfterRollbackProcessor` can route failing records to a DLT and commit recovered offsets in a new transaction. Sound design accounts for record/batch scope, external side effects, idempotency, and failure-path testing.




