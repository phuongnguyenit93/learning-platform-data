# AckMode BATCH

In Spring Kafka, **AckMode** determines when the listener container confirms read progress by committing consumer group offsets. With **AckMode.BATCH**, the container commits offsets after all records returned by a single poll have been processed successfully along the listener flow. This is the common default mode in Spring Kafka and is typically suitable when reducing commit frequency while retaining container-managed acknowledgment.

BATCH does not mean Kafka merges records into a single record, nor does it create an automatic business transaction. It defines when offsets are committed for polled partitions. To use it effectively, you must understand poll boundaries, how record listeners and batch listeners behave, and how errors affect offsets and record redelivery.

This lesson belongs to the **Listener container** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how Spring Kafka manages listeners, consumer groups, and offsets to operate reliable event streams.

## Learning outcomes

After this lesson, you will be able to:

- Explain AckMode.BATCH and when the container commits offsets.
- Distinguish a single poll from a single listener invocation.
- Understand BATCH in both record listeners and batch listeners.
- Configure AckMode.BATCH using Spring Boot or a listener container factory.
- Read committed offsets per partition.
- Analyze behavior when a listener throws exceptions, retries, or routes records to a DLT.
- Recognize the impact of batch size, processing duration, and rebalances.
- Design idempotent listeners to tolerate record redelivery.
- Test commit timing and error behavior using EmbeddedKafka or Testcontainers.

## 1. AckMode and the role of the listener container

A Kafka consumer reads records from partitions and maintains its read position. When the application confirms progress, the consumer commits offsets to Kafka so the group can resume from the proper position after a restart or rebalance.

Spring Kafka uses the listener container to manage the poll loop, invoke methods annotated with `@KafkaListener`, and commit offsets according to AckMode. Applications usually do not need to call commitSync or commitAsync manually inside a listener.

Cooperating components:

~~~mermaid
flowchart TD
    B[Kafka broker] --> P[Consumer poll]
    P --> C[Listener container]
    C --> L["@KafkaListener"]
    L --> R[Process record]
    R --> S{Processing succeeded?}
    S -->|Yes| A[AckMode.BATCH]
    A --> O[Commit offset per partition]
    S -->|No| E[Error handler]
    E --> RT[Retry / DLT / redelivery]
~~~

AckMode.BATCH tells the container that progress for a poll is committed after every record belonging to that poll has been processed successfully under listener and error handler rules. The container remains responsible for coordinating acknowledgment and commits.

In standard Spring Kafka configurations, the container manages commits so consumer auto-commit is disabled. Spring Kafka automatically sets enable.auto.commit=false unless the application explicitly re-enables it; declaring it explicitly in configuration helps prevent confusion.

## 2. What is a poll batch?

The consumer calls poll to fetch records from assigned partitions. A single poll can return:

- No records.
- One record from one partition.
- Multiple records from one partition.
- Multiple records from multiple partitions.

The maximum record count in a single poll is governed by max.poll.records and data currently available on the broker. A poll does not necessarily contain the full configured maximum.

For example, a single poll returns:

| Partition | Returned offsets |
|---|---|
| orders.created-0 | 10, 11, 12 |
| orders.created-1 | 4, 5 |
| orders.created-2 | 27 |

After these records are processed successfully, the container can commit progress per partition:

| Partition | Last record offset in poll | Next committed offset |
|---|---:|---:|
| orders.created-0 | 12 | 13 |
| orders.created-1 | 5 | 6 |
| orders.created-2 | 27 | 28 |

Kafka stores the next offset to read. Therefore, when record offset 12 has been processed and committed successfully, the committed offset is 13.

One poll can contain records from multiple partitions. Commits are tracked separately per partition; there is no global offset for the entire topic.

## 3. How AckMode.BATCH works with a record listener

A record listener is the most common way to use `@KafkaListener`: each method invocation receives one record. However, the consumer still polls in batches at the client layer.

With AckMode.BATCH:

1. The consumer polls and receives a set of records from partitions.
2. The listener container dispatches records one by one to the listener method.
3. The container tracks processing outcomes for the records in that poll.
4. Once all records in the poll succeed, the container commits offsets per partition.
5. The consumer proceeds to the next poll cycle.

Example listener:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment"
    )
    public void consume(OrderCreatedEvent event) {
        orderService.handle(event);
    }
}
~~~

Configuring BATCH on the listener container applies even when the method accepts one event at a time. The listener method does not receive a List simply because AckMode is BATCH.

This is a frequent point of confusion: **AckMode.BATCH is an offset commit policy; a batch listener is a method signature style receiving multiple records**. The two concepts are related but not identical.

## 4. How AckMode.BATCH works with a batch listener

If you want the listener method to receive the entire list of records from a single poll, enable batch listener mode on the container factory. Spring Kafka then delivers the batch of records to a single listener invocation.

Example factory configuration:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
orderBatchListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

Listener receiving a list of ConsumerRecord:

~~~java
@Component
public class OrderBatchListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-batch-processor",
            containerFactory = "orderBatchListenerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderCreatedEvent>> records) {

        for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
            orderService.handle(record.value());
        }
    }
}
~~~

With a batch listener, the method is called once for the batch returned by poll. When the method finishes normally, the container can commit the batch offsets under AckMode.BATCH.

Batch listeners are helpful when business logic can process multiple records together, such as bulk inserts or calling a batch-capable API. However, large batches increase processing duration and the scope of records that may be redelivered if an error occurs.

## 5. Configuring AckMode.BATCH in Spring Boot

You can configure listener type and ack mode in application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      type: single
      ack-mode: batch
~~~

In this configuration:

- type: single selects a record listener, where each listener call receives one record.
- ack-mode: batch selects committing after records from a poll have been processed.
- enable-auto-commit: false lets the container manage offset commits.
- group-id identifies the consumer group storing progress.

If you want listeners to receive whole batches, use type: batch in appropriate Spring Boot settings or configure a dedicated factory with setBatchListener(true). Check your Spring Boot/Spring Kafka version because listener properties and configuration options can vary across versions.

You can also configure directly in Java:

~~~java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);
~~~

AckMode.BATCH is also the default value of ContainerProperties in Spring Kafka. Even so, declaring it explicitly in the application helps readers understand the commit policy in use.

## 6. Comparing BATCH with other AckModes

AckMode defines commit timing; the right choice depends on latency, throughput, and reprocessing tolerance.

| AckMode | High-level commit timing | Typical consideration |
|---|---|---|
| RECORD | After each record listener completes successfully | Want per-record commit granularity. |
| BATCH | After all records from one poll complete successfully | Balances throughput and commit count. |
| TIME | When acknowledgments exist and the configured interval elapses | Want time-bounded commit cycles. |
| COUNT | When the configured acknowledgment count is reached | Want count-based commit thresholds. |
| COUNT_TIME | When either count or time threshold is reached | Combines both conditions. |
| MANUAL | Listener calls acknowledge explicitly; container commits per batch semantics | Business logic decides when to acknowledge. |
| MANUAL_IMMEDIATE | Listener acknowledges and container attempts immediate commit when called on consumer thread | Need explicit commit control. |

RECORD and BATCH are usually the easiest modes to compare. RECORD can generate more commits; BATCH reduces commits by grouping progress per poll. In exchange, if an error occurs mid-poll, understand your error handler policy to know which records get redelivered.

TIME, COUNT, and COUNT_TIME are not direct substitutes for batch processing in the listener. They govern commit thresholds based on acknowledgments and their configuration.

## 7. BATCH does not create a business transaction

Committing offsets per batch does not mean the entire business processing of the batch executes atomically.

Suppose a batch has three records:

1. Record A updates the database successfully.
2. Record B updates the database successfully.
3. Record C fails.
4. The listener throws an exception so the container cannot treat the entire poll as completed normally.

If database changes for A and B were committed individually, Kafka redelivering records after the failure can cause A and B to be processed a second time. BATCH only controls Kafka offsets; it does not automatically roll back the database.

If you want batch database updates in a single transaction, wrap the batch's database changes in an appropriate database transaction. Still, database transactions and Kafka offset commits remain two separate boundaries unless an explicit coordination mechanism is designed.

For repeatable business effects, you should:

- Use a stable eventId for each event.
- Add a unique constraint or inbox table to detect already-processed events.
- Ensure update operations are idempotent.
- Consider outbox/inbox patterns when coordinating databases and Kafka.
- Never assume a BATCH offset commit guarantees end-to-end business exactly-once semantics.

## 8. When a listener fails during a poll

When a listener throws an exception, the container delegates handling to the error handler. Retry, seek, redelivery, or DLT policies determine how the consumer proceeds.

For a record listener using AckMode.BATCH, the container processes each record in the poll. If one record fails, do not assume every preceding record definitely committed or that the entire poll is always re-read. Behavior depends on listener type, error handler, retry configuration, and exception handling.

For a batch listener, if the method throws a plain exception, Spring Kafka may have to reprocess the batch per error handler policy. When you need to pinpoint the failing record in a batch, throw BatchListenerFailedException so DefaultErrorHandler knows the failing record's position and handles earlier and remaining records appropriately.

Illustrative example:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-batch-processor",
        containerFactory = "orderBatchListenerFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreatedEvent>> records) {

    for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
        try {
            orderService.handle(record.value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                    "Cannot process order event",
                    record
            );
        }
    }
}
~~~

BatchListenerFailedException and partial-batch handling depend on the Spring Kafka version and configured error handler. Use a DefaultErrorHandler compatible with your application version and test the actual policy.

An error handler can retry a number of times and then recover the record by publishing it to a dead-letter topic. A DLT isolates unprocessable records, but requires monitoring and a replay workflow once the root cause is fixed.

If a listener catches an exception without rethrowing and without sending the record to a reliable recovery mechanism, the container may treat the call as successful and commit offsets. That can lose the chance to reprocess the record. Swallow exceptions only when business logic has recorded the failure and intentionally decided to skip it.

## 9. Impact of batch size and processing duration

BATCH groups offsets for records from a single poll. Consequently, poll size and processing time affect commit latency.

Notable properties:

- max.poll.records caps the maximum number of records returned in one poll.
- max.poll.interval.ms caps the allowed interval between successive polls before a consumer may be considered stalled.
- fetch.min.bytes and fetch.max.wait.ms affect how the broker waits and returns data for fetch requests.
- concurrency determines how many consumer workers the listener container can create.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
    listener:
      ack-mode: batch
      concurrency: 3
~~~

With a record listener, if a poll returns 100 records, the container can invoke the listener multiple times before committing the batch. With a batch listener, the method receives up to the number of records returned by poll based on limits and available data.

Large batches can improve commit efficiency and bulk processing, but can also:

- Increase processing time per poll.
- Increase offset commit latency.
- Increase how many records may be redelivered upon failure.
- Increase memory required for records and deserialized objects.
- Cause the listener to exceed max.poll.interval.ms if processing takes too long.

Do not raise max.poll.records just to reduce commit count. Measure p95/p99 processing time, payload size, lag, throughput, and downstream limits before tuning.

## 10. BATCH, concurrency, and rebalancing

When a listener container has concurrency greater than one, Spring Kafka creates multiple consumer workers. Each consumer polls and manages its assigned partitions. AckMode.BATCH applies per consumer's poll progress, not as a single global batch across all threads.

For example, if a topic has six partitions and listener concurrency is three, each consumer may receive two partitions. Each consumer has its own poll loop and batch offsets; one consumer finishing its poll does not mean the other consumers have finished theirs.

When a consumer leaves the group or rebalances, partitions can be reassigned to other members. Offsets committed via BATCH serve as the group's recovery point. Records already processed but not yet committed can be redelivered.

Therefore, listeners must be idempotent. If an event updates inventory counts, guard the operation so the same eventId does not deduct inventory twice when redelivered after a rebalance or error.

## 11. Synchronous and asynchronous commits

AckMode.BATCH determines when commits happen, while how commit requests are sent can be configured separately.

Spring Kafka ContainerProperties provides the syncCommits option. By default, containers typically use commitSync; commitAsync can be configured via syncCommits=false depending on requirements and version.

Synchronous commits wait for the broker's commit response, letting the container know the commit outcome at the cost of potential waiting time. Asynchronous commits do not wait in the same way, reducing blocking time while requiring careful consideration of commit failure handling.

Example configuration:

~~~java
factory.getContainerProperties().setSyncCommits(true);
~~~

Switch to async commits only after understanding callback behavior, commit errors, and recovery characteristics. Sync/async commit does not alter the meaning of AckMode.BATCH: offsets are still grouped per poll.

## 12. Testing AckMode.BATCH

Tests should verify both aspects: the listener processes records and the consumer group commits offsets at batch boundaries.

Testing layers:

| Test | What to verify |
|---|---|
| Configuration test | Container is configured with AckMode.BATCH and auto-commit disabled. |
| Record listener integration test | Records in the poll are processed before the poll's offsets are committed. |
| Batch listener integration test | Listener receives the list of records and commits after successful batch processing. |
| Multi-partition test | Offsets are committed separately per partition. |
| Failure test | Exception triggers the error handler and expected retry/redelivery behavior. |
| DLT test | Unrecoverable records are routed to the DLT as configured. |
| Rebalance test | Uncommitted records can be redelivered after partition ownership changes. |
| Idempotency test | Record redelivery does not duplicate business effects. |

You can use EmbeddedKafka for fast testing within a Spring context or Testcontainers when you need a broker closer to the deployment environment.

When checking offsets, use AdminClient to read consumer group offsets. Wait for the container to finish processing and committing with an explicit timeout; do not use fixed Thread.sleep calls. Committed offset is the next position to read, so if a test processes record offset 10, the expected committed value is usually 11.

To test a poll containing multiple records, prepare data and consumer timing in a controlled way. If records are sent while the listener is already running, the broker may deliver them across separate polls; do not assume consecutive sends will automatically land in the same batch.

## 13. Common mistakes when using AckMode.BATCH

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking BATCH means batch listener | Misunderstanding method signature and invocation count | Distinguish AckMode from listener type. |
| Enabling auto-commit alongside container-managed ack | Automatic commits can conflict with container policy | Keep enable.auto.commit=false. |
| Swallowing exceptions in the listener | Container may treat processing as successful and commit offsets | Rethrow errors or use deliberate recovery. |
| Oversized batches | Delayed commits, higher memory, and larger redelivery scope | Measure and tune max.poll.records. |
| Long processing exceeding max.poll.interval.ms | Consumer may leave group and trigger rebalances | Optimize processing, bound batches, and configure an appropriate interval. |
| Assuming BATCH is a database transaction | Database effects before an error may repeat on redelivery | Use proper DB transactions and idempotency. |
| Not testing multi-partition topics | Mistaking committed offsets as topic-wide | Inspect offsets separately per partition. |
| Assuming every error replays the whole batch | Can be wrong depending on error handler and partial batch handling | Inspect handler configuration and test failure paths. |

## 14. Capstone exercise: order batch processing listener

Build a listener for the orders.created topic and configure AckMode.BATCH.

Requirements:

1. Configure group ID orders-fulfillment and enable.auto.commit=false.
2. Create a record listener and verify the container commits after processing records from a poll.
3. Create a batch listener receiving List<ConsumerRecord<String, OrderCreatedEvent>>.
4. Send records to at least two partitions and verify separate offset commits.
5. Trigger a failure mid-batch and configure DefaultErrorHandler.
6. Try BatchListenerFailedException to pinpoint the failing record in the batch listener.
7. Configure bounded retries and a DLT for unrecoverable records.
8. Use eventId to guard against duplicate processing logic.
9. Tune max.poll.records and measure processing time, commits, and consumer lag.
10. Run with concurrency greater than one and observe each consumer's independent polls/commits.
11. Stop a consumer mid-processing to verify redelivery after rebalance.
12. Write integration tests verifying committed offsets and business processing outcomes.

Metrics to record include listener type, AckMode, partition count, concurrency, max.poll.records, processing time per poll, retry count, DLT record count, and consumer group lag.

## 15. Study sequence and completion criteria

| Stage | Core topic | Self-check criteria |
|---|---|---|
| 1. Offset commit | AckMode and listener container | Can explain when the container commits offsets. |
| 2. Poll batch | Polls and records per partition | Can calculate the next offset to commit for each partition. |
| 3. Record listener | BATCH with per-record listener | Understands multiple listener calls can belong to one poll. |
| 4. Batch listener | setBatchListener and List<ConsumerRecord> | Receives and processes the batch returned by poll. |
| 5. Configuration | Spring Boot and ContainerProperties | Configures BATCH properly and disables auto-commit. |
| 6. Failure handling | DefaultErrorHandler, retry, DLT | Controls redelivery and partial batch failures. |
| 7. Performance | max.poll.records, interval, concurrency | Balances throughput, commit latency, and lag. |
| 8. Reliability | Idempotency, transaction boundaries | Does not confuse batch offsets with business exactly-once. |
| 9. Testing | EmbeddedKafka/Testcontainers, AdminClient | Verifies offsets and failure behavior in tests. |

The lesson is complete when you can explain and configure AckMode.BATCH, distinguish record listeners from batch listeners, read committed offsets per partition, and handle failures within a poll properly. Most importantly, you must recognize that batch commits mark Kafka consumer progress; database consistency and business side effects still require dedicated design.

AckMode.BATCH reduces commit frequency by confirming progress after processing the records from a single poll. It fits many Spring Kafka applications, though reliability depends on the error handler, poll size, processing duration, idempotency, and how the application coordinates offsets with external effects.

