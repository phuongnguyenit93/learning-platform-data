# Blocking retry

In Spring Kafka, blocking retry is an error-handling approach that retries a record directly within the consumption thread of the consumer listener container. When the listener throws an exception, the error handler waits according to a backoff policy and then redelivers the record for processing. The consumer does not yet move the failed record out to a separate retry topic; the record still belongs to the original consumer group's processing flow.

Blocking retry is well suited for transient errors that are likely to recover after a short wait, especially when the application needs to preserve processing order within a partition. In exchange, the consumer thread must spend time on the failed record. If retries drag on, other partitions assigned to the same consumer can also be delayed, consumer lag increases, and the group risks a rebalance if processing time exceeds configured limits.

## 1. How does blocking retry work?

In Spring Kafka, the listener container invokes the listener to process a record. If the listener completes normally, the container continues processing according to the configured polling and offset commit mechanism. If the listener throws an exception, the error handler receives the failure and decides whether to retry or recover.

For a record listener and the default seek mechanism of `DefaultErrorHandler`, the high-level flow is as follows:

~~~text
Kafka consumer poll
        |
        v
Listener receives record
        |
        +------ Success ----------> continue processing
        |
        v
Listener throws exception
        |
        v
DefaultErrorHandler
        |
        v
Classify exception
        |
        +------ Do not retry -----> Recovery / DLT
        |
        v
BackOff wait
        |
        v
Consumer redelivers record
        |
        +------ Success ----------> continue processing
        |
        +------ Failure ----------> repeat per BackOff
                                      |
                                      v
                                Retries exhausted
                                      |
                                      v
                                Recovery / DLT
~~~

Blocking means the consumption flow must wait for the record's retry process to be resolved by the error handler. With standard synchronous processing, the listener thread does not proceed to subsequent work while waiting for the backoff interval.

In the default seek configuration, the error handler resets the offset of the failed record and the remaining records that need to be reprocessed to the appropriate position so the consumer can redeliver them in subsequent polls. Thus, the failed record can be retried without creating a copy in another topic.

Spring Kafka also supports keeping records in memory instead of seeking via the appropriate seek-after-error configuration. Regardless of which approach is used, it is still blocking retry if the listener container must wait for the failed record to be retried or recovered before processing continues according to policy.

## 2. DefaultErrorHandler and BackOff

In modern Spring Kafka versions, `DefaultErrorHandler` is the standard error handler for non-transactional listener containers. The handler takes a `BackOff` to determine the wait intervals and retry count, along with a recoverer to handle the record once retries are no longer performed.

Two key components:

- **BackOff**: determines the wait time between redeliveries and when the retry sequence ends.
- **ConsumerRecordRecoverer**: performs an action after retries are exhausted or when the error is classified as non-retryable, such as logging or publishing the record to a dead-letter topic.

Example using `FixedBackOff`:

~~~java
FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(backOff);
~~~

In this example, the wait interval is one second and there are at most two additional retries after the initial processing attempt. In total, the listener may be invoked three times for the record if all three attempts fail under the same backoff sequence and the exception remains retryable.

Do not confuse the number of retries with the total number of deliveries. With `FixedBackOff`, the `maxAttempts` parameter represents the number of retry attempts after the initial one. For example, `maxAttempts` equal to 2 means one initial attempt plus two retries.

Exponential backoff can be used to progressively increase the wait interval:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(backOff);
~~~

With the illustrated configuration, the wait interval starts at 500 ms, increases by a factor of 2, and does not exceed 10 seconds. Exponential backoff helps reduce pressure on a struggling dependency because retries do not occur repeatedly at the same frequency.

If no recoverer is provided, the handler may use default behavior to record that the record has exhausted its retries. In production, an explicit recovery action should be configured so it is clear how the record will be handled next.

## 3. Configuring blocking retry in Spring Kafka

The example below uses `FixedBackOff`, exception classification, and dead-letter recovery:

~~~java
@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler errorHandler =
                new DefaultErrorHandler(recoverer, backOff);

        errorHandler.addNotRetryableExceptions(
                IllegalArgumentException.class,
                InvalidOrderException.class);

        errorHandler.addRetryableExceptions(
                SocketTimeoutException.class,
                TransientDataAccessException.class);

        return errorHandler;
    }
}
~~~

Register the error handler with the listener container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "kafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

In this example:

- `FixedBackOff` waits one second between attempts and allows two retries after the initial attempt.
- `SocketTimeoutException` and `TransientDataAccessException` are treated as retryable errors.
- `IllegalArgumentException` and `InvalidOrderException` are not retried because they typically indicate invalid data or business rules.
- `DeadLetterPublishingRecoverer` sends the record to a dead-letter topic when the handler recovers the record.
- `setCommonErrorHandler` applies the handler to listeners using this container factory.

The `KafkaTemplate`, serializer, deserializer, and exception types must match the application. The code snippet illustrates the configuration structure; corresponding imports and infrastructure beans must be added in the project.

### Configuration in application.yml

Some basic consumer properties can be declared via Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      properties:
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 100
    listener:
      ack-mode: record
~~~

The configuration above illustrates the group ID, disabling auto-commit so the container manages commits, limiting the number of records per poll, and selecting the ack mode. The specific blocking retry policy is still configured in `DefaultErrorHandler` or the corresponding error handler, not merely through these properties.

## 4. Exception classification: which errors are retried?

Not every exception should be retried. Retrying is useful when the underlying cause is likely to self-recover, such as a brief network timeout or a database temporarily refusing connections. For data errors, schema errors, authorization errors, or business rule violations, retrying usually only slows down the partition.

`DefaultErrorHandler` has an exception classification mechanism. Certain exceptions such as deserialization errors, message conversion errors, or invalid method invocation errors are typically considered fatal/non-retryable by default. The application can add rules:

~~~java
errorHandler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class);

errorHandler.addRetryableExceptions(
        TemporaryDatabaseException.class,
        DownstreamTimeoutException.class);
~~~

An exception hierarchy should be designed to reflect recoverability:

~~~text
ApplicationException
  |
  +-- RetryableException
  |      +-- TemporaryDatabaseException
  |      +-- DownstreamTimeoutException
  |
  +-- NonRetryableException
         +-- InvalidOrderException
         +-- UnsupportedEventVersionException
~~~

A database or HTTP client adapter can translate library exceptions into application exceptions. This standardization keeps the error handler from depending too heavily on specific dependency implementations.

Do not wrap every exception in `RetryableException`. If an unrecoverable business error is misclassified as retryable, a bad record can hold up the partition for too long and cause consumer lag to grow.

## 5. How does blocking retry affect partitions?

A single consumer can own multiple partitions. When the listener processes synchronously and a record in one partition fails, the consumer thread must handle the retry and backoff. During the wait, that thread cannot continue executing the listener for other partitions assigned to the same consumer.

For example, consumer A owns P0, P1, and P2:

~~~text
Consumer A
  |
  +-- P0: failed record -> retry waits 10 seconds
  |
  +-- P1: new record -> waits for consumer thread
  |
  +-- P2: new record -> waits for consumer thread
~~~

In this example, P1 and P2 can be delayed even though they have no errors themselves. This is a critical impact of blocking retry: the wait time of a single record can affect every partition sharing the same consumer thread.

If a topic has many partitions and consumer concurrency is low, a single consumer typically owns multiple partitions. In that case, one failed record can slow down several partitions simultaneously. Increasing concurrency can reduce the number of partitions per consumer if unallocated capacity remains, but creating more threads also increases resource usage and rebalances.

It is not possible to split a single partition across multiple consumers in the same group simply by increasing concurrency. If a partition is held up by a failed record, adding consumer members will not let another consumer take over the same partition to skip that record.

## 6. Blocking retry and record ordering

Kafka guarantees record ordering within a single partition. Blocking retry is often suitable when this order must be preserved, because the failed record is reprocessed before the consumer advances to subsequent records in the partition according to the container's mechanism.

Example:

~~~text
Partition P0:
  offset 10: OrderCreated
  offset 11: OrderPaid
  offset 12: OrderShipped

offset 10 fails:
  retry offset 10
  retry offset 10
  successfully processed offset 10

Only then continue with offsets 11 and 12
~~~

This matters when later events depend on state created by earlier events. If a failed record is moved to a retry topic and processing continues on the original topic, a record at a later offset may be processed before the failed record. This is the primary trade-off between blocking retry and non-blocking retry.

However, blocking retry does not by itself guarantee that side effects execute only once. A listener may have already written to the database or called an API successfully before throwing an exception in a subsequent step. Upon retry, the first side effect may execute again. Therefore, business operations still require idempotency keys, event IDs, or appropriate transactions.

## 7. Backoff and wait times

Backoff determines the time interval between attempts. Choose backoff based on how long the dependency needs to recover and the latency limits acceptable to the business.

| Strategy | Behavior | Use case |
|---|---|---|
| FixedBackOff | Waits a fixed interval between retries | Short errors with relatively stable recovery time |
| Exponential backoff | Increases the wait interval after each failure | Dependency that may need progressively longer recovery time |
| Exponential backoff with max interval | Increases progressively but caps the wait time per attempt | Wanting to reduce pressure while still bounding latency |
| Custom BackOff | Defines a custom retry schedule | Specific business policy or specialized retry timing |

Example of `FixedBackOff`:

~~~java
new FixedBackOff(2_000L, 3L);
~~~

This example has a two-second wait interval and at most three additional retries. If all three retries fail and the exception remains retryable, the handler invokes the recoverer once the backoff is exhausted.

Do not set overly long wait times just to increase the probability of success. During that time, the consumer thread can be held up, lag continues to grow, and other partitions on the same consumer are delayed.

## 8. Thread sleep and ContainerPausingBackOffHandler

With blocking retry, the handler must perform the backoff. The simplest way is waiting on the consumer thread. If the wait is long, the thread does not call `poll` during that period; this can interact poorly with `max.poll.interval.ms` and cause the consumer to be kicked out of the group.

Spring Kafka provides `ContainerPausingBackOffHandler` to use pause/resume on the listener container during long backoff waits. The container continues polling as needed while paused, helping prevent the consumer from being considered overdue on polling merely because it is waiting to retry.

To use it, configure a `ContainerPausingBackOffHandler` instance as the `BackOffHandler` for `DefaultErrorHandler`, along with a `BackOff` that has an appropriate interval. Exact instantiation and wiring must follow the API of the Spring Kafka version in use; inspect the constructors and overloads of `DefaultErrorHandler` in your project's dependencies before copying a configuration.

For long backoffs, this is an option to consider instead of holding the consumer thread in a long sleep.

Pausing the container does not make the record process faster, nor does it eliminate the wait time. It only changes how the container waits, maintains the poll loop, and coordinates pause/resume. Actual pause durations should be measured to ensure the listener container can resume processing on schedule.

## 9. max.poll.interval.ms and blocking retry

`max.poll.interval.ms` limits the maximum time between consumer `poll` calls in the classic consumer group protocol. If record processing time and backoff prevent the consumer from calling `poll` within this limit, the consumer may be considered stalled and removed from the group.

Example:

~~~text
max.poll.interval.ms = 60 seconds

Listener processing:  10 seconds
Blocking backoff:     40 seconds
Retry processing:     15 seconds
--------------------------------
Total:                65 seconds
~~~

In this example, the total time between polls can exceed 60 seconds. The consumer risks being kicked out of the group and having its partitions reassigned to another member.

When evaluating configuration, account for:

- Normal listener processing time.
- Total backoff time across retries.
- Reprocessing time of the record after each backoff.
- Processing time for remaining records in the poll batch.
- Time for related callbacks or synchronous operations.

Increasing `max.poll.interval.ms` may be appropriate if long processing time is a legitimate requirement, but it only raises the threshold before a consumer is considered stalled. It does not improve throughput and does not address why the dependency is slow. For long backoffs, consider `ContainerPausingBackOffHandler` or non-blocking retry.

## 10. Recovery after retries are exhausted

When `BackOff` finishes its steps or the exception is classified as non-retryable, the error handler invokes the recoverer. Some options:

- Log and skip the record according to an approved policy.
- Publish the record along with error metadata to a dead-letter topic.
- Write the record to an error store for operator investigation.
- Call a recovery service with idempotency and auditing.

Example using `DeadLetterPublishingRecoverer`:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L));
~~~

Under common default configuration, the recoverer can route the record to a topic with a DLT suffix and the corresponding partition. In production, clearly verify:

- Whether the DLT topic exists and has enough partitions.
- Whether the producer has serializers suitable for the key/value and headers.
- Whether the application has permission to write to the DLT.
- Whether exception metadata, original topic, partition, offset, and timestamp are preserved for investigation.
- How the record will be handled if publishing to the DLT fails.

Invoking the recoverer must not be treated as proof that the DLT write succeeded. Publish results must be observed and recovery failure handling configured according to the Spring Kafka version.

## 11. Ack mode and offset commits

Blocking retry is directly tied to when offsets are committed. If the listener fails, the container should not commit an offset past a record that has not yet been processed or successfully recovered.

Spring Kafka supports multiple ack modes, such as `RECORD`, `BATCH`, `TIME`, `COUNT`, `COUNT_TIME`, `MANUAL`, and `MANUAL_IMMEDIATE`. Each mode has its own commit rules. You must understand the container's mode and how the error handler handles recovered records.

For normal record processing:

1. The consumer polls the record.
2. The listener processes the record.
3. If successful, the container marks the offset according to the ack mode.
4. If failed, the error handler retries or recovers.
5. Once the record is successfully recovered, the container handles the offset commit according to the handler and container configuration.

If the application uses `MANUAL` or `MANUAL_IMMEDIATE`, check how acknowledgment interacts with the error handler. Properties such as `ackAfterHandle` and `commitRecovered` are meaningful in certain configurations; do not enable `commitRecovered` arbitrarily when the ack mode does not support that commit behavior.

If a listener triggers side effects outside Kafka and then fails before committing, the record may be redelivered. Idempotent design is required to avoid duplicate transactions or duplicate data creation.

## 12. Batch listeners and blocking retry

With a record listener, the error handler knows which record failed. With a batch listener, a single listener invocation can receive many records, so the failing record or position must be identified.

If a batch listener throws a generic exception without indicating the failing record, the handler may have to retry the entire batch or apply the corresponding batch-handling policy. This can cause records that already succeeded in the batch to be reprocessed.

Spring Kafka supports `BatchListenerFailedException` to indicate the failing record or index in the batch. When this exception is used, the error handler can handle the preceding portion and retry from the failing position according to supported semantics.

Illustrative example:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void handle(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int i = 0; i < records.size(); i++) {
        try {
            process(records.get(i).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                    "Cannot process record in batch", ex, i);
        }
    }
}
~~~

Constructor signatures and batch listener APIs must match the Spring Kafka version. If a batch contains multiple records from multiple partitions, carefully check how the container determines offsets and the portion of the batch to retry. Listeners should avoid duplicate side effects for records processed before the batch failed.

## 13. Blocking retry in transactional listeners

When a listener container uses Kafka transactions, an exception from the listener typically rolls back the current transaction. The retry flow after rollback is coordinated by an `AfterRollbackProcessor`, typically `DefaultAfterRollbackProcessor`, rather than applying a non-transactional `DefaultErrorHandler` configuration as-is.

`DefaultAfterRollbackProcessor` can use a `BackOff` and a recoverer to retry the record after rollback, then recover once retries are exhausted. If sending to a DLT within the transaction is required, transaction configuration and offset commits must be designed properly so that recovery output and offsets have atomic semantics within Kafka's scope.

Do not take a non-transactional `DefaultErrorHandler` example and attach it to a transactional listener without reviewing the transaction manager and after-rollback processing. Determine which operations the transaction covers and whether external database side effects are part of that transaction.

Kafka transactions do not automatically roll back a REST API or a database that does not participate in the transaction. If a listener updates a database and the Kafka transaction subsequently rolls back, the database side effect may still persist. Use the outbox pattern, idempotency, or an appropriate transaction coordination design.

## 14. Blocking retry and non-blocking retry

Spring Kafka supports non-blocking retry via `@RetryableTopic`. When a listener fails, the record is forwarded to a retry topic with a configured delay. Consumers of the original topic can continue processing other records instead of waiting for the failed record to finish retrying.

| Criterion | Blocking retry | Non-blocking retry |
|---|---|---|
| Where retry occurs | In the original consumer listener container thread | Via retry topics |
| Consumer thread | Waits for backoff and reprocesses the record | Can continue processing the original topic after the record is forwarded |
| Ordering | Better suited when partition ordering must be preserved | Later records may be processed before a record waiting in a retry topic |
| Additional topics | No separate retry topics needed | Requires retry topics and routing configuration |
| Suitable errors | Transient errors, short wait times, ordering matters | Errors requiring long delays or when the main flow must not be blocked |
| Operations | Monitor backoff, retry state, and consumer threads | Monitor retry topics, forwarding counts, and DLT |

Example of non-blocking retry:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000))
@KafkaListener(
        topics = "orders",
        groupId = "orders-service")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Non-blocking retry frees up the original topic's processing flow, but changes the observable ordering between the failed record and later arrivals. It is not a faster version in every case. Choose based on ordering requirements, latency, and operability.

Do not layer blocking retry and non-blocking retry on top of each other without calculating total attempt counts, wait times, and where records may be routed. Check the compatibility limits of your Spring Kafka version and the listener model in use.

## 15. Observing and operating blocking retry

When blocking retry is active, monitor both listener errors and consumer group impact.

Information that should be captured in logs:

- Topic, partition, and offset.
- Group ID and listener ID.
- Exception class and root cause.
- Delivery attempt.
- Backoff interval.
- Elapsed time from first failure to recovery.
- DLT publish outcome, if applicable.

Metrics that should be monitored:

- Listener failure count and retry count.
- Recovered record count and failed recovery count.
- Consumer lag by partition.
- Listener processing time and p95/p99 latency.
- Time interval between polls.
- Rebalance count and rebalance duration.
- Commit latency and commit error rate.
- DLT publish rate.

Do not use topic, partition, and offset as high-cardinality metric labels. Those fine-grained details belong in logs or traces; metrics should use bounded-cardinality labels such as listener, exception category, and outcome.

When investigating a lagging partition:

1. Check whether the current record is retrying.
2. Inspect the exception and backoff interval.
3. Identify what other partitions that consumer owns.
4. Check whether other partitions on the same consumer are also slowed down.
5. Measure listener latency and downstream latency.
6. Check `max.poll.interval.ms` and rebalances.
7. Determine whether recovery or DLT publishing is failing.

If all partitions owned by the same consumer slow down simultaneously, blocking retry or a long-running listener operation may be the cause. If only one partition has high lag while others remain stable, investigate hot partitions, key skew, or a specific failing record.

## 16. Common misconceptions

**Blocking retry creates a retry topic.** False. Blocking retry reprocesses the record within the original consumer flow; retry topics are a non-blocking retry mechanism.

**Only the partition with the failed record is affected.** Not true in all cases. If the consumer thread is waiting synchronously on backoff, other partitions assigned to the same consumer can also be delayed.

**Increasing concurrency splits a failing partition across multiple consumers.** False. A partition has only one owner within the same group at any stable point in time.

**Retrying many times guarantees the record will eventually succeed.** False. `BackOff` has limits, and data or configuration errors cannot self-recover. Once retries are exhausted, the handler must recover according to policy.

**A listener failure means no side effects occurred.** False. The listener may have written to a database or called an API before throwing the exception. Retrying can re-execute that side effect; idempotency is required.

**Increasing `max.poll.interval.ms` makes retries faster.** False. It only changes the time limit between polls. Backoff durations and dependency speed remain unchanged.

**Successful DLT publishing means the business operation was processed.** False. The record was merely moved to an error stream for investigation or replay.

**Non-blocking retry is always better than blocking retry.** False. Non-blocking retry can alter the order between a failed record and subsequent records. Blocking retry is suitable when in-partition ordering is a priority.

## 17. Workflow for choosing and configuring blocking retry

When designing blocking retry for a listener, identify the error types, expected recovery times, and consequences if a partition is blocked.

A practical workflow:

1. List the exceptions that can arise from the listener and its dependencies.
2. Classify transient errors versus non-retryable errors.
3. Choose `FixedBackOff` or exponential backoff with a bounded retry count.
4. Configure `DefaultErrorHandler` and a recoverer for non-transactional listener containers.
5. If using transactions, configure `AfterRollbackProcessor` and the appropriate transaction manager.
6. Evaluate total processing time against `max.poll.interval.ms`.
7. Consider `ContainerPausingBackOffHandler` if backoffs are long.
8. Check the number of partitions per consumer to understand the blast radius when a thread blocks.
9. Design idempotent side effects and define the offset commit policy.
10. Configure a DLT, observe retries and recovery, and test both dependency-recovery and non-recovery scenarios.

Blocking retry is a useful choice when errors can self-recover quickly and record order within a partition must be maintained. Limit the retry count and wait time, classify exceptions clearly, monitor impact on consumer threads, and provide concrete recovery when a record cannot be processed. If retry durations are long or blocking a partition affects SLOs, consider container pausing or non-blocking retry with accepted ordering trade-offs.
