# AckMode COUNT in Spring Kafka

In Spring Kafka, **AckMode COUNT** allows the listener container to commit consumer offsets after processing a configured number of records. Instead of committing after every record or waiting for an entire poll batch to finish, the container accumulates the count of processed records and commits pending offsets when the `ackCount` threshold is reached.

This approach balances commit overhead and offset acknowledgment latency. Committing less frequently can reduce overhead at high throughput, but it also increases the number of records that may be re-read if the consumer stops abruptly before the next commit. Therefore, COUNT must be chosen alongside the acknowledgment mode, retry/error handler, concurrency, record rate, and the business logic's ability to handle duplicates.

## 1. Offsets and Acknowledgments in the Listener Container

Kafka stores offsets per partition. A consumer group commits an offset to record the next position to read in that partition. If the application has processed the record at offset 41 and successfully commits offset 42, on the next startup the consumer group can resume from position 42.

A Spring Kafka listener container manages polling, invoking the listener, tracking progress, and committing offsets. When the listener processes a record successfully, the container can place the processed position into the set of offsets pending commit. AckMode determines when the container sends those offsets back to Kafka.

~~~text
Topic orders, partition 0
  offset 40 --> record A
  offset 41 --> record B
  offset 42 --> record C
  offset 43 --> record D
                  |
                  v
        Spring Kafka listener
                  |
                  +--> process record
                  |
                  +--> record processed offset
                  |
                  +--> commit next offset
                              |
                              v
                       Consumer group
                       committed offset
~~~

An offset commit does not store the processed business payload. It only stores the consumer group's read position. If the application has updated the database without committing the offset, the record can be redelivered. If the application commits the offset before completing business work, the record can be skipped when the consumer restarts.

Therefore, the acknowledgment mode must accurately reflect the ordering between business processing and offset commits.

## 2. How Does AckMode COUNT Work?

With `ContainerProperties.AckMode.COUNT`, the container tracks how many records have been processed since the previous commit. When the count reaches the `ackCount` threshold, the container commits the pending offsets.

Example with `ackCount=5`:

~~~text
Record 1 --> listener finishes --> count = 1
Record 2 --> listener finishes --> count = 2
Record 3 --> listener finishes --> count = 3
Record 4 --> listener finishes --> count = 4
Record 5 --> listener finishes --> count = 5
                                      |
                                      v
                              COMMIT OFFSETS
                                      |
                                      v
                               count = 0
Record 6 --> listener finishes --> count = 1
...
~~~

With a record listener, the container processes each record and can check the threshold after the listener finishes. Once the threshold is reached, the container commits the accumulated progress for that consumer.

Several important points:

- `ackCount` is a record count, not a byte count, partition count, or duration.
- The threshold is tracked per consumer/container instance. It is not a global counter shared across the entire consumer group.
- If a consumer is assigned multiple partitions, records from all those partitions contribute together toward that consumer's threshold.
- When committing, Kafka receives offsets for the relevant partitions; the container does not commit a single global record count.
- If traffic is low and the threshold has not been reached, COUNT may go a long time without producing a new commit.
- Listener errors are still governed by the error handler, acknowledgment mode, and transactions. COUNT does not turn a failed record into a successful one.

COUNT is a commit-triggering threshold, not a timer. If the application needs to bound both the number of uncommitted records and the time between commits, see `COUNT_TIME`.

## 3. Configuring AckMode COUNT with Spring Boot

Spring Boot allows configuring the acknowledgment mode and record threshold under listener properties.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      ack-mode: count
      ack-count: 100
      concurrency: 3
~~~

Explanation:

- `enable-auto-commit: false`: lets the Spring Kafka listener container control offset commits.
- `ack-mode: count`: selects the record-count-based commit policy.
- `ack-count: 100`: requests a commit once a threshold of 100 records has been processed.
- `concurrency: 3`: creates up to three consumer child containers for the corresponding listener container, depending on partition count and factory configuration.

`ack-count` is only meaningful with COUNT and COUNT_TIME. If using RECORD, BATCH, TIME, or manual acknowledgment, this property does not govern commit timing the way COUNT uses it.

With `application.properties`, the equivalent configuration is:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=order-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.listener.ack-mode=count
spring.kafka.listener.ack-count=100
spring.kafka.listener.concurrency=3
~~~

Property names and binding support may depend on the Spring Boot version. Use a Spring Boot version compatible with your application's Spring Kafka version and verify the actual bound configuration at startup.

## 4. Configuring COUNT in Java

If the application creates its own listener container factory, AckMode and ack count can be set on `ContainerProperties`.

~~~java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.COUNT
        );
        factory.getContainerProperties().setAckCount(100);

        return factory;
    }
}
~~~

A listener using this factory:

~~~java
@Component
public class OrderConsumer {

    private final OrderService orderService;

    public OrderConsumer(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service",
            containerFactory = "orderListenerContainerFactory"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

When multiple factories exist, specify the right `containerFactory` on `@KafkaListener`. If the endpoint still uses another factory, configuring COUNT on the newly created factory will have no effect on that endpoint.

If the application uses the default factory created by Spring Boot, it can be configured via `spring.kafka.listener` without creating a new factory just to set ack count.

## 5. How Does COUNT Differ from RECORD, BATCH, TIME, and COUNT_TIME?

Spring Kafka offers multiple acknowledgment modes to match throughput and recovery requirements.

| AckMode | Commit Timing | Characteristics |
|---|---|---|
| RECORD | After the listener successfully processes each record | Frequent commits, small replay window |
| BATCH | After processing all records received from a single poll | Fits batching and reduces commit count |
| TIME | When time since the previous commit reaches `ackTime` | Time-based commits |
| COUNT | When processed record count reaches `ackCount` | Traffic-based commits |
| COUNT_TIME | When either `ackCount` or `ackTime` is reached, whichever comes first | Combines count and time limits |
| MANUAL | Listener calls acknowledge; container handles commits per batch semantics | Application decides when to acknowledge |
| MANUAL_IMMEDIATE | Commits immediately when acknowledge is called on the consumer thread | More explicit commit control |

### COUNT vs. RECORD

RECORD commits after each record the listener processes successfully. With COUNT, the container accumulates multiple records before committing.

If `ackCount=100`, a consumer processing 100 records can produce one commit instead of committing after each record. This can reduce commit calls at high throughput.

In return, if the consumer stops after processing 90 records without reaching the 100 threshold, those records can be re-read because their offsets have not been committed. Thus, COUNT creates a larger replay window than RECORD.

### COUNT vs. BATCH

BATCH commits after the listener processes all records received from a single poll. Batch size depends on `max.poll.records`, assigned partitions, and available data.

COUNT uses a record threshold accumulated across processing. If a poll returns few records, the container may need multiple polls to reach the threshold. If a poll returns many records, the threshold may be reached while processing that batch, depending on listener type and how the container processes it.

With a batch listener, the method receives an entire list of records in a single call. COUNT does not turn a batch callback into independent commits for each element in the list. If you need to process and commit each record individually, consider a record listener with RECORD; if using a batch listener, design around batch semantics and corresponding error handling.

### COUNT vs. TIME

TIME commits when elapsed time since the previous commit reaches `ackTime`. It is useful when you want commits based on time rather than traffic volume.

COUNT does not guarantee a maximum interval between commits. If there are not enough records, the threshold is not triggered.

Example: `ackCount=100`, yet the topic receives only 10 records in an hour. COUNT may not commit the new offsets during that period. If the application stops abruptly, processed-but-uncommitted records can be redelivered.

### COUNT vs. COUNT_TIME

COUNT_TIME combines both conditions. The container commits when the `ackCount` record count is reached or when `ackTime` has elapsed, whichever occurs first.

Example:

~~~yaml
spring:
  kafka:
    listener:
      ack-mode: count_time
      ack-count: 100
      ack-time: 5000
~~~

In this example, the container can commit once 100 records have been processed or once 5 seconds have elapsed since the previous commit. This avoids holding uncommitted offsets for too long during low traffic while still reducing commit overhead during high traffic.

If both a throughput-based and a time-based limit are needed, COUNT_TIME is usually worth considering over pure COUNT.

## 6. How Does COUNT Affect Duplicates and Recoverability?

AckMode COUNT does not provide exactly-once processing. It only decides when offsets are committed. When the application has executed side effects but has not yet committed offsets, records can be redelivered.

Example with `ackCount=10`:

~~~text
Consumer processes records 1..8
      |
      +--> Database has committed changes
      |
      +--> Kafka offset has not reached commit threshold
      |
      v
Process stops
      |
      v
Consumer restarts
      |
      v
Kafka redelivers records from the last committed offset
      |
      v
Records 1..8 may be reprocessed
~~~

If the listener creates invoices, deducts inventory, or records payments, reprocessing can cause duplicates. Business logic must be made idempotent.

A common approach is using a stable event ID and an inbox/processed-events table with a unique constraint. Recording the event ID and updating business data must happen within the same database transaction.

~~~java
@Transactional
public void process(OrderCreated event) {
    boolean firstDelivery =
            processedEventRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderRepository.apply(event);
}
~~~

`insertIfAbsent` represents a database insert guarded by a unique constraint. If the event has already been processed, the consumer does not repeat the business effect. If the transaction rolls back, both the processed-event record and the business update roll back together.

Several principles:

- Choose an event ID that remains stable across redeliveries.
- Do not rely on in-memory variables to prevent duplicates across restarts.
- Do not commit offsets before protected side effects complete.
- For external APIs, use an idempotency key if the API supports it.
- Monitor redelivery counts and duplicate rates at the business layer.

## 7. COUNT and Exception Handling

COUNT only governs commit timing during normal processing. When the listener throws an exception, the container delegates the error to the configured error handler. The error handler decides retries, recovery, DLT routing, and offset behavior.

Example:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-service"
)
public void onOrder(OrderCreated event) {
    orderService.process(event); // May throw an exception.
}
~~~

If the listener throws an exception:

1. The container receives the error from the listener.
2. `CommonErrorHandler`/`DefaultErrorHandler` applies retry and backoff.
3. If the listener succeeds on retry, the container continues handling offsets per the acknowledgment mode.
4. If retries are exhausted, the recoverer can route the record to a DLT.
5. Offsets advance only according to the container's recovery and commit policy.

Do not catch an exception just to log and return if you want the container to retry:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Processing failed", ex);
        // Without rethrowing, the container may treat the listener as successful.
    }
}
~~~

COUNT cannot rescue swallowed errors. When the method returns normally, the container may count the record toward processing progress and commit once the threshold is reached.

### Recovery and DLT

When using `DefaultErrorHandler` with `DeadLetterPublishingRecoverer`, unrecoverable records can be sent to a DLT after the configured number of retries. Verify the DLT publish outcome; recovery is only considered complete when the recoverer succeeds according to the container's policy.

COUNT does not decide whether a DLT message is sent. It only participates in offset commit timing for records that the error handler has finished handling.

## 8. COUNT with Concurrency and Multiple Partitions

When concurrency is configured, `ConcurrentMessageListenerContainer` creates multiple child containers. Each child manages one Kafka consumer and maintains its own progress counter.

Example:

~~~yaml
spring:
  kafka:
    listener:
      ack-mode: count
      ack-count: 100
      concurrency: 3
~~~

If there are three child consumers, each consumer tracks its own record count. This is not a shared counter waiting for the whole group to process 100 records.

Suppose a topic has six partitions and three consumers; each consumer may receive roughly two partitions depending on the partition assignment strategy. Records from partitions assigned to the same consumer contribute together toward that consumer's COUNT threshold.

Illustrative example:

~~~text
Child consumer 1: partition 0, 1 --> counts independently to 100 --> commits offset
Child consumer 2: partition 2, 3 --> counts independently to 100 --> commits offset
Child consumer 3: partition 4, 5 --> counts independently to 100 --> commits offset
~~~

Actual partition distribution per child may be uneven. If the topic has fewer partitions than concurrency, some children may receive no partitions and process no records.

This affects commit rate and replay exposure:

- Each child reaches the threshold at a different pace.
- A consumer handling high traffic may commit frequently.
- A consumer handling low traffic may hold offsets longer.
- During a rebalance, partitions move to other consumers; committed offsets serve as the reliable recovery point.
- COUNT sets no group-wide threshold and does not guarantee children commit at the same time.

## 9. How Does COUNT Relate to max.poll.records and Poll Interval?

`max.poll.records` caps the maximum number of records returned in a single poll. `ackCount` is the processed-record threshold between commits. The two settings serve different purposes.

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 500
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      ack-mode: count
      ack-count: 100
~~~

In this example:

- One poll can return up to 500 records.
- The container commits at a threshold of 100 processed records.
- Listener processing time must still fit within `max.poll.interval.ms`.

Do not assume `ack-count=100` means the consumer polls only 100 records. Poll size is still determined by consumer configuration and available records.

If the listener processes for too long, the consumer can exceed `max.poll.interval.ms`, leave the group, and trigger a rebalance. COUNT does not extend the poll interval and does not fix a stalled listener. Measure processing time and tune batch/poll size, concurrency, and dependency latency.

Also distinguish:

- `max.poll.records`: maximum records returned in one poll.
- `ack-count`: records that must be processed to trigger a commit under COUNT.
- `max.poll.interval.ms`: limit on the interval between polls that the consumer must obey.
- `ack-time`: time threshold used with TIME or COUNT_TIME.

## 10. COUNT with a Batch Listener

A record listener receives one record per method invocation. A batch listener receives multiple records at once. Choosing a batch listener affects how the application handles errors and offset progress.

Batch listener example:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchListenerFactory"
)
public void onOrders(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

The factory needs batch listener enabled:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
batchListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.COUNT
    );
    factory.getContainerProperties().setAckCount(100);

    return factory;
}
~~~

With a batch listener, the method is invoked with the batch received from the poll. The container cannot assume individual elements completed independently if the method has not returned or lacks an appropriate mechanism to report the failing record.

If one record in the batch fails, `BatchListenerFailedException` may be needed to indicate the failing record index to the error handler. If the index is not identified, the entire batch may be retried or recovered according to policy. Previously processed records may run again, so batch operations should be idempotent.

If the primary goal is committing individually after each record, a record listener with RECORD usually expresses the requirement more clearly. If the goal is batch processing and reducing commit count, design batch error handling carefully.

## 11. COUNT in a Transactional Listener Container

When the listener container uses a Kafka transaction manager, offsets are sent into the Kafka transaction and committed together with output records belonging to that transaction. If the listener throws an exception, the transaction can abort and records are reprocessed per transaction recovery.

AckMode determines how offset progress is enlisted into the transaction per container configuration. In transactional processing, distinguish committing offsets outside a transaction from committing offsets as part of a Kafka transaction.

~~~text
Kafka transaction begins
       |
       v
Listener processes record
       |
       +--> send output via KafkaTemplate
       |
       +--> listener completes
       |        |
       |        v
       |    Offset is added to transaction
       |        |
       |        v
       |    Commit transaction
       |
       +--> exception
                |
                v
             Abort transaction
                |
                v
       Rollback/recovery per configuration
~~~

If using COUNT with transactions, verify behavior on the exact Spring Kafka version and listener type being deployed. Do not treat the COUNT threshold as an independent transaction or an exactly-once guarantee for databases. Databases outside Kafka still require an appropriate transaction manager, inbox/outbox, or idempotency.

## 12. When Should You Choose COUNT?

COUNT is suitable when:

- The consumer processes relatively high throughput.
- Committing after every record creates measurable overhead.
- Business logic tolerates a bounded replay window and has idempotency.
- Traffic is steady enough that the record threshold is reached within a reasonable time.
- The system can observe commit latency, consumer lag, and redelivery.

COUNT is less suitable when:

- The topic has very low or bursty traffic.
- Business requirements expect offsets to be committed within a short time even when few records arrive.
- Duplicates are expensive and no idempotency mechanism exists.
- A batch listener needs per-record error handling without an appropriate design in place.
- Consumers frequently stop or rebalance before reaching the threshold.

If traffic is low yet you still want to reduce commit overhead, consider `COUNT_TIME` for a time bound. If you need immediate commits after each record, use `RECORD`. If you want to commit after each poll batch, use `BATCH`.

## 13. How to Choose ackCount

There is no single threshold right for every consumer. Choose based on throughput, commit cost, and replay tolerance.

### Small Threshold

For example, `ackCount=10`:

- More frequent commits.
- Fewer uncommitted records under steady traffic.
- More commits and potentially higher broker/network overhead.
- Can suit low-throughput consumers or replay-sensitive workloads.

### Large Threshold

For example, `ackCount=1000`:

- Reduces commit count under high traffic.
- Can improve processing efficiency if commit overhead is a measured bottleneck.
- Increases how many records can be redelivered after a crash before commit.
- Under low traffic, time to reach the threshold can be very long.

### Estimating Time to Reach the Threshold

If a child consumer processes an average of 200 records per second and `ackCount=100`, the theoretical time to reach the threshold is approximately:

~~~text
100 records / 200 records per second = 0.5 seconds
~~~

If the consumer processes only 2 records per minute, the same threshold of 100 could take about 50 minutes to trigger. This is why pure COUNT may not fit low-traffic workloads.

This estimate is only a directional guide. Actual throughput varies with partitions, batches, listener duration, rebalances, backpressure, and dependency failures.

### Selection Process

1. Measure throughput per consumer instance/child container.
2. Measure current commit rate and commit latency.
3. Determine how many records can acceptably be replayed after a crash.
4. Start with a small initial threshold, observe, and increase gradually if evidence shows commit overhead is a bottleneck.
5. Check low-traffic periods to observe intervals between commits.
6. Test restarts/rebalances both before and after reaching the threshold.
7. Verify consumer idempotency when records are redelivered.
8. If a time bound is needed, switch to `COUNT_TIME` and choose an appropriate `ackTime`.

## 14. Monitoring COUNT in Production

Monitor both processing progress and commit progress. Looking only at throughput does not show whether offsets are committing steadily.

| Metric | What to Observe |
|---|---|
| Consumer records consumed rate | Rate of processed records |
| Consumer commit rate | Frequency of offset commits |
| Commit latency | Time for broker to respond to commits |
| Consumer lag | Distance between current offset and committed offset |
| Records lag max | Partition with the largest lag |
| Rebalance rate | Frequency of consumer group partition reassignments |
| Listener processing time | Time to process each record or batch |
| Redelivery / retry count | Number of times records must be reprocessed |
| DLT publish count | Number of records recovered to DLT |

Exact metric names depend on the Kafka client, Micrometer, and exporter setup. Inspect the actual metrics exported in your application.

Signals to investigate:

- Consumer processes fast yet commit rate is unusually low.
- Consumer lag grows despite constant producer throughput.
- After a restart, many previously processed records are redelivered.
- One child container reaches COUNT quickly while another rarely commits.
- Commit latency increases under high broker load.
- Retry or DLT count spikes after a rebalance.

Logs should include group ID, topic, partition, offset, event ID, and commit/recovery timestamps when investigating. Avoid logging sensitive payloads solely to observe acknowledgments.

## 15. Common Configuration Mistakes

**Setting ack-mode=count but forgetting ack-count**

If the threshold is not set as intended, the application may use a default value or a value bound from elsewhere. Check `ContainerProperties.getAckCount()` or startup container configuration logs.

**Setting ack-count too large**

Under low traffic, offsets may remain uncommitted for a long time. Crashes can trigger large replays. Consider `COUNT_TIME` or a smaller threshold.

**Confusing ack-count with max.poll.records**

These two properties control different behaviors. `max.poll.records` caps poll size; `ack-count` sets the commit threshold.

**Confusing COUNT with manual acknowledgment**

COUNT is a container-managed mode that tracks record count automatically. MANUAL requires the listener to call `Acknowledgment.acknowledge()`. `ackCount` does not replace manual mode's acknowledge call.

**Catching exceptions without rethrowing**

The container may view the listener as finishing successfully, counting the record toward progress. If retries are needed, let exceptions propagate to the error handler or apply explicit recovery.

**Assuming COUNT provides exactly-once**

COUNT only controls offset commits. It does not bundle database updates into a Kafka transaction and does not prevent side effects from running twice after redelivery.

**Ignoring concurrency**

Each child consumer has its own threshold. Do not multiply or divide `ackCount` by concurrency and treat it as a group-wide counter.

## 16. Complete Configuration Example

An illustrative configuration for a record listener with steady traffic:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 300
    listener:
      ack-mode: count
      ack-count: 100
      concurrency: 3
      missing-topics-fatal: false
~~~

Listener:

~~~java
@Component
public class OrderConsumer {

    private final OrderService orderService;

    public OrderConsumer(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service"
    )
    public void consume(OrderCreated event) {
        orderService.processIdempotently(event);
    }
}
~~~

In this example:

- The container manages offset commits.
- Each child consumer accumulates processed record counts.
- Upon reaching 100 records, the container commits pending offsets for that consumer.
- `max-poll-records=300` limits the maximum records returned in one poll, independent of ack count.
- `concurrency=3` allows up to three child consumers, depending on partition assignment.
- `processIdempotently` represents duplicate-safe business logic.

If traffic is uneven and commits must happen within at most a desired time window, you can switch to:

~~~yaml
spring:
  kafka:
    listener:
      ack-mode: count_time
      ack-count: 100
      ack-time: 5000
~~~

Then the container commits when 100 records are reached or when the `ack-time` duration has elapsed since the previous commit. Verify the property's time unit against your Spring Kafka API/version; `ackTime` is configured in milliseconds on `ContainerProperties`.

## 17. Pre-Production Checklist for COUNT

- `enable.auto.commit` is disabled so the container manages offsets.
- The listener's actual factory uses `ContainerProperties.AckMode.COUNT`.
- `ackCount` is explicitly configured with an appropriate value.
- `ackCount` is distinguished from `max.poll.records` and `max.poll.interval.ms`.
- Each child consumer is understood to have its own independent counter.
- Both high-traffic and low-traffic periods have been measured to estimate time to reach the threshold.
- Maximum number of records that could be replayed after a crash is bounded and understood.
- The listener enforces idempotency for business side effects.
- Exceptions propagate to the error handler when retries are needed.
- Retry/backoff/recovery/DLT policies are bounded and observable.
- If a time bound between commits is needed, `COUNT_TIME` has been considered.
- If using a batch listener or Kafka transactions, listener and offset semantics are clearly defined.
- Commit rate, commit latency, consumer lag, rebalances, and redeliveries are monitored.
- Restarts and rebalances have been tested when processed records have not yet reached the threshold.

AckMode COUNT is useful when a consumer has sufficiently high throughput and needs to reduce offset commit frequency. In return, the application accepts a larger uncommitted record window and potential reprocessing after a crash. Choose `ackCount` based on per-consumer metrics, combine it with idempotency, and use `COUNT_TIME` when a time bound on commits is required.
