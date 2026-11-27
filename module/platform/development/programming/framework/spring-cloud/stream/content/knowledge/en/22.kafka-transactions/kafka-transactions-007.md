# Rollback, AfterRollbackProcessor, and Retry After Rollback

A Kafka consumer can process messages inside a transaction to combine reading records, updating state, and emitting output messages within a single transaction boundary. When the listener raises an error, the transaction is rolled back. The application must understand what happens to offsets, consumed records, and side effects to decide how to retry.

In Spring for Apache Kafka, `AfterRollbackProcessor` is the component invoked by the container after a listener's transaction rolls back. The default processor is `DefaultAfterRollbackProcessor`; it repositions the consumer so unprocessed records are read again. You can configure backoff, a recoverer, and dead-letter publishing to control retry counts and how persistently failing records are handled.

The Spring Cloud Stream Kafka binder supports transactions via Spring Kafka. When the binder is configured as transactional, the listener container starts a transaction; records sent on the consumer thread can join that transaction. When the listener finishes normally, the container sends the offset into the transaction and commits. When the listener throws an exception, the transaction rolls back and `DefaultAfterRollbackProcessor` governs retry/recovery. This lesson covers rollback, seek/redelivery, post-rollback retry, recovery, DLT, and configuration in Spring Cloud Stream.

## Learning Objectives

After this lesson, you will be able to:

- Explain transactional listeners and why listener exceptions lead to rollback.
- Distinguish Kafka transaction rollback from database transaction rollback.
- Understand how offsets and records are reprocessed after rollback.
- Describe the role of `AfterRollbackProcessor` and `DefaultAfterRollbackProcessor`.
- Configure post-rollback retry/backoff and a recoverer when retries are exhausted.
- Understand `commitRecovered`, `KafkaTemplate`, and the new transaction for recovery operations.
- Integrate transactions and rollback with the Spring Cloud Stream Kafka binder.
- Design DLT, idempotency, and failure/recovery testing.

## 1. Transactions in Kafka consumers

Kafka transactions allow producers to write multiple records into Kafka as an atomic unit. Consumers can read committed records according to an appropriate isolation level. In the consume-process-produce model, a listener can read a record, process it, send output records, and commit the offset within the same Kafka transaction.

For example, a service receives `OrderCreated`, produces `OrderValidated`, and sends the result to another topic:

~~~text
Consumer reads OrderCreated
       |
       v
Container starts Kafka transaction
       |
       v
Listener executes business logic
       |
       v
Send OrderValidated
       |
       v
Send input offset into transaction
       |
       v
Commit transaction
~~~

If the transaction commits, the output record and input offset are committed as one unit. If the transaction rolls back, the output record in the transaction is discarded and the input offset does not advance via that transaction; the record can be read again.

### 1.1. Transactional listeners

In Spring Kafka, a container can be configured with `KafkaTransactionManager`. The listener is then invoked within a Kafka transaction started by the container. If the listener throws an exception outward, the container rolls back the transaction.

Example listener following the Spring Kafka model:

~~~java
@KafkaListener(topics = "orders", groupId = "order-validator")
public void validate(OrderCreated event) {
    OrderValidated result = orderService.validate(event);
    kafkaTemplate.send("orders.validated", event.orderId(), result);
}
~~~

The snippet only illustrates the business flow. For the listener to actually be transactional, the container factory must be configured with a compatible `KafkaTransactionManager`. When using Spring Cloud Stream, the binder can configure transactions for bindings and listener containers; do not copy plain Spring Kafka configuration into a binder application without checking how your running version configures it.

### 1.2. Kafka transactions do not automatically include databases

A Kafka transaction covers only the Kafka operations participating in that transaction. It does not automatically roll back an already committed JPA/JDBC transaction.

Example:

1. The listener updates the database.
2. The listener sends a record to Kafka.
3. The Kafka transaction rolls back.

If the database committed independently, database data remains while the Kafka output record is rolled back. Coordinate transaction managers, use outbox/inbox, or design idempotency when business logic spans both a database and Kafka.

## 2. What happens when a listener rolls back?

When a transactional listener throws an exception, the container rolls back the transaction. The consumer needs to resume from the record that was not processed successfully.

For record listeners, Spring Kafka by default seeks the partition back to the failed record and any unprocessed records so the next poll redelivers them. For batch listeners, the entire batch is redelivered because the container does not know exactly which record in the batch caused the failure. `AfterRollbackProcessor` is responsible for controlling this behavior.

~~~mermaid
flowchart TD
    A[Container starts Kafka transaction] --> B[Poll and deliver record to listener]
    B --> C[Listener processes and sends output]
    C --> D{Listener succeeds?}
    D -->|Yes| E[Commit transaction and offset]
    D -->|No| F[Rollback transaction]
    F --> G[AfterRollbackProcessor]
    G --> H[Seek back to record to retry]
    H --> I[Next poll redelivers record]
    I --> B
~~~

Rollback does not mean the broker deletes the input record. The record still exists in the log; the consumer group has not finalized the corresponding offset, so it can be read again.

### 2.1. Uncommitted offsets

Kafka tracks consumer progress using offsets per partition. In a transactional listener, the offset is sent into the transaction alongside output records. If the transaction rolls back, the offset is not committed as part of that transaction.

This avoids the situation where output is committed while the input offset also advances in a failed transaction. On retry, the application must be ready to receive the same record again.

### 2.2. Side effects outside Kafka

If a listener calls an HTTP service, sends an email, or commits a database independently before throwing an exception, Kafka rollback does not undo that side effect. When the record is redelivered, the side effect may repeat.

Use idempotency keys, inbox/outbox, appropriate database transactions, or a compensating workflow for side effects outside Kafka. Do not equate Kafka transactions with exactly-once across the entire distributed system.

## 3. What is AfterRollbackProcessor?

`AfterRollbackProcessor` is a Spring Kafka extension point invoked after a listener's transaction rolls back. The processor decides where the consumer should seek back to, whether to continue retrying, or whether to route the record to a recovery step.

The default implementation is:

~~~java
org.springframework.kafka.listener.DefaultAfterRollbackProcessor
~~~

In the basic case, the processor seeks the partition back to the unprocessed record so the next poll can redeliver it. This is post-rollback retry, which differs from retrying directly inside the listener method.

### 3.1. In-listener retry vs. post-rollback retry

| Mechanism | Timing | Characteristics |
|---|---|---|
| In-listener retry | Re-invokes processing before the listener returns control to the container | May remain inside the same transaction; attempts do not create separate rollback boundaries |
| Post-rollback retry | Listener throws error, transaction rolls back, processor drives the next delivery | Each redelivery goes through a new container/transaction cycle |
| Retry topic | Record is sent to a retry topic for later processing | A separate pipeline, not a simple seek |
| DLT recovery | Failed record is sent to a dead-letter destination after retries are exhausted | Must coordinate publishing and committing the recovery offset |

With transactional listeners, post-rollback retry is usually easier to reason about: each time the listener fails, the transaction rolls back and the processor decides when the record is redelivered.

### 3.2. DefaultAfterRollbackProcessor

The default processor can configure:

- A `BackOff` to set the wait interval between attempts.
- A `ConsumerRecordRecoverer` to handle the record once retries are exhausted.
- A `KafkaTemplate` and `commitRecovered` to publish the recovered record and then commit the offset in a new recovery transaction when configured appropriately.
- Batch- and transaction-related options depending on the Spring Kafka version.

Spring Kafka retries failed records by default; after the default failure count, the default recoverer logs the failed record. You can change the retry count and supply a custom recoverer. How the initial delivery and retry counts are counted should be verified against the `BackOff` in use.

## 4. Configuring post-rollback retry/backoff

`BackOff` defines the wait interval between retries. Example using `FixedBackOff`:

~~~java
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.util.backoff.FixedBackOff;

ConsumerRecordRecoverer recoverer = (record, exception) -> {
    log.error(
            "Recovering record topic={} partition={} offset={}",
            record.topic(),
            record.partition(),
            record.offset(),
            exception);
};

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(1_000L, 2L));
~~~

The example illustrates invoking the recoverer after the retry policy permits no further retries. `FixedBackOff` takes the interval and retry count; the initial delivery is not counted as a retry. Check the API of your Spring Kafka version and verify listener invocation counts with tests.

`BackOff` can be fixed or exponential. Exponential backoff is suitable when a dependency needs time to recover; jitter can help avoid multiple consumers retrying simultaneously. Avoid excessively long backoffs if the partition must maintain low latency.

### 4.1. Bounded vs. infinite retries

Bounded retries prevent a permanently failing record from stalling a partition forever. After retries are exhausted, the recoverer can:

- Send the record to a DLT.
- Record the error and store the payload in a quarantine store.
- Trigger a business data-correction workflow.
- Stop processing and require operational intervention.

Infinite retries may suit rare transient errors where skipping is unacceptable, but can block the entire partition if a record is unrecoverable. Choose the policy based on error type and ordering requirements.

### 4.2. Exception classification

Not every exception should have the same retry count:

| Error Type | Example | Recommended Action |
|---|---|---|
| Transient | Timeouts, brief broker/dependency interruption | Retry with backoff |
| Overload | HTTP 429, exhausted database connection pool | Backoff, throttle rate |
| Invalid data | Missing required fields, bad schema | Few or no retries; route to DLT |
| Configuration error | Wrong credentials, missing topic | Alert, fix configuration |
| Programming bug | Logic bug, unexpected null | Limit retries and investigate |

Spring Kafka supports exception classification in retry/recovery components. With the Spring Cloud Stream transactional binder, you can configure `defaultRetryable` and `retryableExceptions` per binding. Exceptions explicitly marked retryable or non-retryable are applied in `DefaultAfterRollbackProcessor`.

## 5. Recoverer and dead-letter topic

When retries are exhausted, the recoverer is invoked to handle records that cannot be processed normally. A common choice is `DeadLetterPublishingRecoverer`, which sends the failed record to a dead-letter topic (DLT).

Illustrative example with Spring Kafka:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(1_000L, 2L));
~~~

In real deployments, the DLT destination must exist or be properly provisioned. Verify the DLT naming strategy—for example, appending a DLT suffix to the original topic name, along with the matching partition if the routing strategy requires it.

### 5.1. DLT headers and metadata

`DeadLetterPublishingRecoverer` can attach metadata about the original topic, partition, offset, and exception to the headers of the record sent to the DLT. This metadata aids investigation and replay.

The DLT should retain:

- Original payload.
- Source topic, partition, and offset.
- Exception or recovery reason.
- Timestamp when the failure was detected.
- Event ID/correlation ID if available.
- Attempt count or delivery attempt information if provided.

Do not write secrets or full stack traces into headers without evaluating size limits and security policies.

### 5.2. Successful recovery and offset commit

In a transactional listener, sending a record to the DLT and committing the recovered record's offset must be coordinated. `DefaultAfterRollbackProcessor` supports `commitRecovered` mode when configured with an appropriate `KafkaTemplate`. When properly enabled, the processor can send the recovered record in a new transaction and send the processed offset into that transaction.

If the DLT publish succeeds but the offset is not committed, the original record may be redelivered and the DLT may receive duplicates. If the offset is committed while the DLT publish fails, the record may be lost from the retry flow. Therefore, transaction recovery configuration must be tested.

### 5.3. Do not confuse DLT with retry topics

A DLT is typically for records that have exhausted retries or cannot be processed. A retry topic is an architecture that routes records to another topic to be retried after a delay. Retry topics allow subsequent records to proceed, but can alter per-key ordering.

`AfterRollbackProcessor` with seek/redelivery keeps the record in the original partition stream. It does not automatically create retry topics.

## 6. Configuring recovery on the container factory

In a plain Spring Kafka application, you can attach the processor to the listener container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultAfterRollbackProcessor<String, OrderCreated> processor,
        KafkaTransactionManager<String, OrderCreated> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setAfterRollbackProcessor(processor);
    factory.getContainerProperties().setKafkaAwareTransactionManager(transactionManager);
    return factory;
}
~~~

This is a Spring Kafka example; setter signatures and generic types must match your project's Spring Kafka version. The transaction manager must use the same `ProducerFactory` that `KafkaTemplate` uses so send operations join the corresponding transaction.

When using the Spring Cloud Stream Kafka binder, listener containers are created and managed by the binder. You can customize containers with `ListenerContainerCustomizer` in supported versions. Do not create a separate `KafkaListener` container factory and assume the binder will automatically use it.

## 7. Transactions in the Spring Cloud Stream Kafka binder

To enable transactions in the Kafka binder, set a non-empty transaction ID prefix:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: tx-orders-instance-a-
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
        processOrder-out-0:
          destination: orders.validated
~~~

`transaction-id-prefix` must be unique across concurrently running application instances. In a processor application, the consumer starts the transaction; records sent on the consumer thread participate in that transaction. When the listener completes normally, the container sends the offset into the transaction and commits. Producer bindings use a shared producer factory configured under `transaction.producer`; certain per-binding producer properties are no longer applied as they are when the binder is non-transactional.

### 7.1. Retry behavior of the transactional binder

When transactions are enabled, do not use normal binder retry and dead-lettering in the non-transactional way. Normal retries can run inside the initial transaction; if the transaction rolls back, any retry/DLT records published inside that transaction are also rolled back.

Instead, when retry is enabled via `maxAttempts`, the Kafka binder configures container-level retries via `DefaultAfterRollbackProcessor`. Exception-specific retry can be configured:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              default-retryable: false
              retryable-exceptions:
                java.lang.IllegalStateException: true
                java.lang.IllegalArgumentException: false
~~~

In the example, `IllegalStateException` is retried, while `IllegalArgumentException` is not. Exception types must be subclasses of `Exception`. The `retryableExceptions` configuration only controls exception classification; attempt counts and backoff still depend on the binding's retry properties and binder version.

Do not enable in-listener retry alongside post-rollback retry without understanding the transaction boundaries. Define a single policy per error type.

### 7.2. Committing offsets after recovery

The Kafka binder provides the `txCommitRecovered` property for consumer bindings. With the transactional binder, the offset of a recovered record—such as after sending to a DLT—is committed by default via a new transaction. Setting `txCommitRecovered` to `false` disables committing the recovered offset through this mechanism.

Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              tx-commit-recovered: true
~~~

Verify the actual DLT and recovery configuration in your binder version. Do not assume that invoking the recoverer means the offset was committed; verify the recovery transaction outcome.

### 7.3. Customizing binder-created listener containers

When you need to attach a custom processor or change backoff/recoverer behavior beyond binder properties, you can use `ListenerContainerCustomizer` if supported by your version. With the transactional binder, you can obtain the transactional `ProducerFactory` from the Kafka binder, create a `KafkaTemplate` from that factory, and configure `DefaultAfterRollbackProcessor` with a recoverer, `BackOff`, template, and `commitRecovered`.

Illustrative configuration skeleton using binder APIs:

~~~java
@Bean
ListenerContainerCustomizer<AbstractMessageListenerContainer<?, ?>> rollbackCustomizer(
        BinderFactory binderFactory) {

    KafkaMessageChannelBinder binder =
            (KafkaMessageChannelBinder) binderFactory.getBinder(
                    null, MessageChannel.class);
    ProducerFactory<byte[], byte[]> producerFactory =
            binder.getTransactionalProducerFactory();
    KafkaTemplate<byte[], byte[]> template = new KafkaTemplate<>(producerFactory);

    DefaultAfterRollbackProcessor<byte[], byte[]> processor =
            new DefaultAfterRollbackProcessor<>(
                    new DeadLetterPublishingRecoverer(template),
                    new FixedBackOff(2_000L, 2L),
                    template,
                    true);

    return (container, destination, group) ->
            container.setAfterRollbackProcessor(processor);
}
~~~

This skeleton illustrates a single Kafka binder. If the application has multiple binders, select the exact binder name rather than passing `null`. Verify generic types, customizer APIs, and DLT provisioning against your library version. Do not share a single processor across all bindings if different bindings require different retry or DLT policies.

## 8. Post-rollback retry and partition ordering

When a record in a partition fails and the processor seeks back to it, subsequent records in that partition may have to wait for the failing record to be processed or recovered, depending on listener and batch mode. This preserves ordering but can create head-of-line blocking.

Example:

~~~text
Partition 2:
offset 100: OrderCreated       -> succeeded
offset 101: PaymentAuthorized -> failed, rollback
offset 102: OrderShipped       -> waiting on record 101
~~~

If record 101 is retried multiple times, offset 102 can be delayed. This is the trade-off when prioritizing in-partition ordering.

If a DLT or retry topic is used and record 101 is skipped so 102 proceeds, business ordering can be broken. Determine:

- Is strict per-aggregate ordering required?
- Can failing records be isolated while subsequent records proceed?
- Can consumers handle out-of-order versions?
- Should aggregate versions be checked to detect gaps?

Kafka only guarantees ordering within a single partition. If events for the same aggregate must be sequential, the producer must use a stable key and the consumer must control asynchronous processing.

### 8.1. Batch listeners

With a batch listener, if a transaction rolls back, the entire batch is typically redelivered because the container does not know which record in the batch caused the failure. `DefaultAfterRollbackProcessor` cannot isolate and recover a single individual record without knowing which record failed.

If per-record error handling is needed inside a batch, you can use `BatchToRecordAdapter` so the container invokes the listener per record while maintaining batch structure. Check the API and support in your Spring Kafka version.

## 9. Transaction recovery and commitRecovered

A critical scenario is when a record exhausts retries and is recovered to a DLT. The application needs two consistent operations:

1. Publish the original record to the DLT.
2. Commit the input offset so the record is not redelivered again.

In `DefaultAfterRollbackProcessor`, `commitRecovered` together with `KafkaTemplate` enables recovery to run in a new transaction when configured appropriately for transactions. This recovery transaction is separate from the initial listener transaction that rolled back.

~~~text
Listener transaction T1
  - process record
  - fail
  - rollback T1

AfterRollbackProcessor
  - retry per BackOff
  - retries exhausted
  - invoke recoverer

Recovery transaction T2
  - publish record to DLT
  - send recovered offset
  - commit T2
~~~

If T2 commits, the DLT record and recovered offset commit together. If T2 rolls back, the source record can be redelivered for another recovery attempt.

Setter names and configuration details may differ by Spring Kafka version. Consult the exact version's API docs and test transaction recovery behavior rather than merely checking logs to see if the recoverer was called.

## 10. Testing rollback and retry

Tests must prove that the transaction actually rolls back, the record is redelivered, and recovery only advances the offset once recovery succeeds.

### 10.1. Testing listener rollback

A listener can be configured to fail on the first attempt and succeed on the next:

~~~java
AtomicInteger attempts = new AtomicInteger();

@KafkaListener(topics = "orders", groupId = "order-test")
public void process(OrderCreated event) {
    if (attempts.incrementAndGet() == 1) {
        throw new IllegalStateException("temporary failure");
    }
    orderService.process(event);
}
~~~

With a transactional container and configured `AfterRollbackProcessor`, the test can verify the listener is invoked again and business logic only completes on the successful attempt. This example describes the behavior; tests should use a real transactional container rather than calling the method directly.

### 10.2. Testing backoff and attempt counts

Use `FixedBackOff` or an observable test `BackOff` to verify:

- The listener is re-invoked the expected number of times.
- Wait intervals between attempts stay within bounds.
- The recoverer is called only after the retry policy is exhausted.
- The record is not marked complete when the handler fails and recovery has not succeeded.

To keep tests fast, use short backoffs or an appropriate timing mechanism if supported by your version's API. Avoid tests that rely on unnecessarily long sleeps.

### 10.3. Testing DLT and offset recovery

With a Kafka test broker or Testcontainers:

1. Create input and DLT topics.
2. Send a record with a stable event ID.
3. Configure the listener to always fail so the recoverer is triggered.
4. Verify the record is sent to the DLT with source metadata.
5. Verify the input offset is committed per the recovery configuration.
6. Restart the consumer and verify the record is not unexpectedly reprocessed.
7. Force the DLT publish to fail and verify the input offset is not falsely committed.

### 10.4. Testing transactional output

In a consume-process-produce listener:

- When the listener succeeds, verify the output record and input offset commit together.
- When the listener throws an exception, verify output records in the transaction roll back and the input record is redelivered.
- When the listener sends multiple outputs and then fails, verify no partial output is committed.

Test consumers should use an appropriate isolation level, such as `read_committed`, if you want to see only committed transactional records.

## 11. Observability and operations

Post-rollback retries can stall a partition for a long time or continuously route records to the DLT. Monitor:

| Metric | Meaning |
|---|---|
| Listener failure count | Number of times the listener raises an error |
| Rollback count | Number of listener transactions rolled back |
| Retry attempt count | Number of post-rollback retry attempts |
| Recovery count | Number of records recovered |
| DLT publish success/failure | Outcome of sending failed records |
| Consumer lag by partition | Which partition has growing backlog |
| Time between attempts | Interval between retry attempts |
| Transaction duration | Duration of listener/recovery transactions |
| Rebalance count | Group assignment changes caused by slow or stopped consumers |

If one partition's lag grows while other partitions remain healthy, investigate the failing record and retry duration. A single failing record can block all subsequent records in that partition.

### 11.1. Alerting

Alert when:

- Rollbacks spike suddenly.
- Continuous retries exceed a threshold.
- DLT inflow rises abnormally.
- DLT publishing fails.
- Consumer lag grows over an extended period.
- Transaction timeouts or repeated rebalances occur.

Do not alert on a single isolated rollback if retries succeed quickly and SLA is unaffected.

## 12. Common mistakes

1. **Assuming Kafka rollback also rolls back the database**: A Kafka transaction does not automatically cover an independent database transaction. Use outbox/inbox or an explicit coordination mechanism.
2. **Catching an exception and not re-throwing it**: The container may commit the transaction even though business processing failed. Propagate errors or handle them per a defined policy.
3. **Confusing in-listener retry with post-rollback retry**: The two mechanisms have different transaction lifecycles. Choose the mechanism suited to transactional listeners.
4. **Leaving the post-rollback processor unconfigured**: The application falls back to defaults without clear retry/recovery bounds. Explicitly define `BackOff` and a recoverer.
5. **Retrying a data-error record infinitely**: The partition can remain blocked forever. Classify exceptions and use bounded retries for unrecoverable errors.
6. **Committing the offset before DLT publishing succeeds**: The record can vanish from the stream without a DLT copy. Coordinate recovery and offset commit in a new transaction.
7. **Assuming calling the recoverer means the offset was committed**: The recovery callback and offset commit are two coordinated steps. Test `commitRecovered`.
8. **Using a `KafkaTemplate` not participating in the active transaction**: Output may commit independently of the listener. Verify the producer factory and transaction manager.
9. **Treating DLT and retry topics as the same**: A DLT isolates failed records; a retry topic is a separate retry pipeline. Design distinct semantics.
10. **Not handling duplicates after a crash**: The broker may have received output before the listener knew the result. Use event IDs and idempotency.
11. **Ignoring partition ordering**: Retry topics or recovery can allow later records to overtake failing ones. Define ordering per aggregate.
12. **Testing only by calling the listener method directly**: Such tests do not exercise transactions, seeks, offsets, or recovery. Integration test against real Kafka.

## 13. Procedure for implementing rollback and retry

When deploying a transactional Kafka consumer:

1. Identify which Kafka operations must belong to the same transaction.
2. Enable transactions on the Kafka binder with a unique per-instance transaction ID prefix.
3. Define which errors trigger listener rollback and avoid swallowing exceptions.
4. Choose `DefaultAfterRollbackProcessor` or a custom processor.
5. Configure `BackOff` and retry counts by error category.
6. Choose a recoverer and DLT for unprocessable records.
7. If using the transactional binder, configure retry behavior via `maxAttempts` and exception classification.
8. Verify `txCommitRecovered` and the new transaction for recovered record offsets.
9. Review partition keys and ordering requirements during retries or DLT routing.
10. Test rollback, redelivery, DLT, offsets, and transactional outputs with a Kafka test broker.
11. Monitor rollbacks, retries, recovery, DLT, and consumer lag after deployment.

## Conclusion

When a transactional Kafka listener fails, the container rolls back the transaction and `AfterRollbackProcessor` controls seeking, retrying, or recovering the record. `DefaultAfterRollbackProcessor` supports backoff and recoverers; once retries are exhausted, the record can be sent to a DLT. Under appropriate transactional configuration, `commitRecovered` together with `KafkaTemplate` allows publishing the recovered record and committing the offset in a new recovery transaction.

The Spring Cloud Stream Kafka binder configures post-rollback retry at the container level when transactions are enabled; normal binder retry/DLT does not work the same way as in non-transactional mode because publishes inside a rolled-back transaction are rolled back too. Use a unique per-instance transaction ID prefix and verify retry, recovery, and offset commits against your deployed binder version.

Rollback covers only operations participating in the Kafka transaction. Databases, HTTP calls, or external side effects require dedicated mechanisms such as outbox, inbox, and idempotency. To achieve reliable delivery, test listener transactions, redelivery, recovery transactions, DLT publishing, and offset commits on a real broker.

## References

- [Spring for Apache Kafka — After Rollback Processor](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Cloud Stream — Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html)
