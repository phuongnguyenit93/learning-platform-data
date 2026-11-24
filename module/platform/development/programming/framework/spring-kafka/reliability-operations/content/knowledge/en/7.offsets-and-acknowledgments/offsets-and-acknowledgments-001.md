# AckMode BATCH

## 1. What Is AckMode in Spring Kafka?

A Kafka consumer reads records by offset and needs to commit offsets to let the broker know the position the consumer group has processed up to. Offset commits directly affect the position where the consumer resumes reading after a restart, rebalance, or error.

Spring Kafka provides `AckMode` to determine when the listener container acknowledges processed records and sends an offset commit. **AckMode.BATCH** instructs the container to commit offsets after all records returned by a single `poll()` have finished processing.

This is the common default mode of the Spring Kafka listener container. It fits many applications that need to balance throughput and commit frequency: the container can process multiple records in a single poll and then commit offsets as a group instead of committing after every individual record.

Two concepts need to be distinguished:

- **Batch returned by poll:** the set of records `KafkaConsumer` returns in a single `poll()` call. This set can contain records from multiple partitions.
- **Batch listener:** a listener type that receives an entire list of records in a single method invocation, rather than being invoked separately for each record.

AckMode.BATCH does not require using a batch listener. With a record listener, the container can still receive a set of records from a poll, invoke the listener sequentially for each record, and then commit after all records from that poll have been processed.

## 2. How AckMode.BATCH Works

A simple cycle of the listener container:

1. The container calls `poll()` to fetch records from Kafka.
2. Kafka returns records belonging to the partitions currently assigned to the consumer.
3. The container passes each record to the listener, or passes the entire list if a batch listener is used.
4. The container tracks the processing outcome across the received set of records.
5. Once all records in the poll set have been processed successfully according to the container's semantics, the container commits the corresponding offsets.

For example, suppose a consumer receives three records from partition 0 and two records from partition 1:

~~~text
A single poll() returns:
  partition 0: offset 10, 11, 12
  partition 1: offset 20, 21

Container processes:
  p0/10  -> success
  p1/20  -> success
  p0/11  -> success
  p1/21  -> success
  p0/12  -> success

After the entire poll set completes:
  commit p0 -> offset 13
  commit p1 -> offset 22
~~~

Kafka stores the next offset the consumer group needs to read. Therefore, after processing offset 12, the consumer commits 13; after offset 21, it commits 22. Committed offsets are tracked independently per partition, even though a single commit request can carry offsets for multiple partitions.

### 2.1. Commit Timing

Suppose a poll returns 100 records. With AckMode.BATCH, the container does not commit immediately after the first record. It waits until all 100 records have finished processing within the container flow before sending the offset commit.

If a poll returns fewer records, the container only needs to process that actual number of records. A poll may return 1 record, a few records, or none at all; batch size is not fixed.

### 2.2. A Batch Does Not Mean a Single Partition

A poll can contain records from multiple partitions assigned to the same consumer. When committing, Kafka stores the offset separately for each partition. Therefore, the batch concept here refers to the set of records from one poll, not all records of a topic or a single partition.

If a consumer group has multiple consumers, each consumer has its own poll cycle and commit boundary. AckMode.BATCH does not combine records from all instances in the group into a single shared batch.

## 3. AckMode.BATCH vs. Other AckModes

Spring Kafka has multiple acknowledgment modes. Choose a mode based on processing boundaries, throughput, and replay tolerance.

| AckMode | Commit Timing | Common Use Case |
|---|---|---|
| `RECORD` | After the listener finishes processing each individual record | Want commits closely aligned per record, reducing records replayed after a failure |
| `BATCH` | After all records from a single poll are processed | Need to balance throughput and commit count |
| `TIME` | After finishing processing a batch and the commit time condition is met | Want to limit commit frequency by time |
| `COUNT` | After finishing processing a batch and the record count reaches the threshold | Want to commit based on the number of processed records |
| `COUNT_TIME` | When either the count or time condition is met after batch processing | Want to combine count and time thresholds |
| `MANUAL` | Listener calls acknowledge; container commits at the batch boundary | Application needs to decide when to acknowledge |
| `MANUAL_IMMEDIATE` | Listener calls acknowledge and commits immediately if called on the consumer thread; if called from another thread, the commit is handled via the container mechanism | Need explicit commit control |

`RECORD` and `BATCH` are the two options most commonly compared directly. With RECORD, one completed record can be committed before subsequent records in the same poll finish. With BATCH, the container waits for the entire poll set.

`TIME` and `COUNT` do not mean committing mid-way while the listener is still processing a batch. The container only commits once the required records in the poll have been processed; the time or count condition determines when the commit is triggered.

### 3.1. Comparing RECORD and BATCH

Suppose a poll returns offsets 10, 11, and 12 from the same partition.

With RECORD:

~~~text
Process offset 10 -> commit offset 11
Process offset 11 -> commit offset 12
Process offset 12 -> commit offset 13
~~~

With BATCH:

~~~text
Process offset 10
Process offset 11
Process offset 12
Entire poll completes -> commit offset 13
~~~

RECORD can produce more commits, but reduces the window of processed-yet-uncommitted records. BATCH reduces commit count when a poll contains many records; in return, if the process stops before the final commit, some or all uncommitted records from that poll may be redelivered depending on state and error handling.

## 4. Configuring AckMode.BATCH in Spring Boot

AckMode is a listener container setting, not a Kafka consumer property like `fetch.min.bytes` or `max.poll.records`.

In Spring Boot, it can be declared in `application.yml`:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: order-fulfillment
    listener:
      ack-mode: batch
      type: single
~~~

`ack-mode: batch` tells the listener container to use AckMode.BATCH. `type: single` indicates that the listener receives one record at a time; the container still commits per poll record set. If you want the listener method to receive a list of records, you need to configure the listener type as batch and write the corresponding method.

The Spring Kafka container generally disables Kafka auto-commit unless the application explicitly enables it. Declaring `enable-auto-commit: false` makes it explicit that offsets are managed by the container. Avoid enabling auto-commit while expecting the container to control commits via AckMode, because the Kafka client may commit periodically regardless of listener processing outcomes.

### 4.1. Java Configuration

When creating a `ConcurrentKafkaListenerContainerFactory` manually, you can set AckMode on ContainerProperties:

~~~java
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

If you want the listener to receive a batch, the factory needs batch listener enabled:

~~~java
factory.setBatchListener(true);
~~~

Then the listener method can accept a list of records:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "kafkaListenerContainerFactory"
)
public void handleBatch(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        fulfillmentService.process(record.value());
    }
}
~~~

The examples assume the application has already configured `ConsumerFactory`, deserializers, and the relevant imports. If Spring Boot already creates the default factory, there is no need to create a custom factory just to select AckMode; using `spring.kafka.listener.ack-mode` is usually simpler.

## 5. Record Listener with AckMode.BATCH

This is a common pattern when each listener invocation processes one event, while the container still commits per poll batch:

~~~java
@Service
public class OrderListener {

    private final FulfillmentService fulfillmentService;

    public OrderListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.process(event);
    }
}
~~~

Suppose `poll()` returns 50 records. The container calls the `consume()` method for each record. After all 50 invocations complete successfully, the container commits the offsets of the relevant partitions.

This does not mean the listener method receives 50 records at once. It still receives one event per invocation. Batch is the container's commit boundary.

### 5.1. When Is a Record Listener Appropriate?

A record listener is usually appropriate when:

- Each event has independent business logic.
- Errors can be handled and recorded per event.
- There is no need to coordinate data across multiple records within a single invocation.
- You want to leverage AckMode.BATCH to reduce commit overhead without writing batch-processing code.

If a record fails, the error handler decides whether to retry, recover, or route the failed record to a DLT. The remaining records in the poll are handled according to the semantics of the error handler and container. Do not assume that merely using BATCH means all records in a poll are always replayed together; exact behavior depends on error handling.

## 6. Batch Listener with AckMode.BATCH

A batch listener receives multiple records in a single method invocation. This is useful when group processing can be optimized, such as bulk inserts, bulk updates, or calling an API that supports multiple items.

Example:

~~~java
@Service
public class OrderBatchListener {

    private final FulfillmentService fulfillmentService;

    public OrderBatchListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment-batch",
        containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
        List<OrderCreated> events = records.stream()
            .map(ConsumerRecord::value)
            .toList();

        fulfillmentService.processBatch(events);
    }
}
~~~

The corresponding factory needs batch listener enabled:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

When the batch listener method completes normally, the container considers the set of records returned in the poll as processed and can commit the corresponding offsets.

If the method throws an exception, the container cannot treat the entire batch as successful. The error handler will perform retries or recovery as configured. If you need to handle individual failed records inside a batch, you can use `BatchListenerFailedException` to indicate the index of the failing record and coordinate with an appropriate `DefaultErrorHandler`.

### 6.1. Batch Size Is Not Fixed

The size of the list the listener receives depends on how many records Kafka returns in that poll and the relevant limits. `max.poll.records` sets the maximum number of records the consumer returns in a single poll; it does not guarantee that every poll will have that exact count.

A poll can return:

- Few records because the topic currently has low volume.
- Many records when producers generate high load.
- Records from multiple partitions assigned to the same consumer.
- No records if no matching data is available yet.

Therefore, batch processing must tolerate empty lists or lists smaller than an expected threshold in code paths that may receive those cases.

## 7. Offset Commits and Delivery Guarantees

AckMode.BATCH is commonly used in an at-least-once model where the container commits only after the listener finishes processing successfully. It reduces the chance of losing records due to premature commits, but can cause already-processed records to be redelivered if the application stops before committing.

Example:

1. A poll returns offsets 100, 101, 102.
2. The listener successfully processes all three records.
3. The process stops before committing offset 103.
4. The consumer restarts or the partition is assigned to another consumer.
5. The group reads again from the previously committed offset and may receive 100, 101, and 102 again.

This is normal replay behavior under at-least-once delivery. Therefore, consumers must handle duplicates safely.

### 7.1. Committing an Offset Means Committing the Next Position

Kafka commits the next offset the consumer will read. If the last processed record in a partition has offset 42, the committed offset is normally 43.

| Last Processed Record | Committed Offset | Next Read Position |
|---:|---:|---:|
| 9 | 10 | 10 |
| 42 | 43 | 43 |
| 1,024 | 1,025 | 1,025 |

The container tracks offsets per partition. It does not take the last offset of the topic or the number of records in the batch to compute a single shared offset.

### 7.2. Idempotent Consumer

Because batch commits can cause replays, business side effects should be resilient against duplicate processing.

A common approach is attaching a stable `eventId` to the event and storing processed IDs in an inbox table:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

The consumer uses a DB transaction to check and record the event ID alongside the side effect. If the event is redelivered, the unique constraint detects that the event has already been processed.

High-level logic example:

~~~java
@Transactional
public void process(OrderCreated event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    fulfillmentRepository.createWork(event);
    processedEventRepository.save(
        new ProcessedEvent(event.eventId(), Instant.now())
    );
}
~~~

The example above illustrates the idea; in concurrent implementations, you should rely on a unique constraint and duplicate-key handling within the same transaction rather than relying solely on a check-before-insert. If two consumers or two executions check at the same time, both may observe that the ID does not yet exist.

If the DB commits successfully but the Kafka offset has not been committed yet, the record may be redelivered. A DB transaction together with an inbox ensures the retry does not produce the side effect a second time.

## 8. Exception Handling in BATCH Mode

AckMode.BATCH only defines the normal commit boundary. When a listener throws an exception, the error handler decides which records are retried, seeked, recovered, or sent to a dead-letter topic.

Exact behaviors depend on the Spring Kafka version, listener type, error handler, retry policy, recoverer, and transaction configuration.

### 8.1. Record Listener Failure

Suppose a poll returns records A, B, and C. The listener processes A successfully, but B throws an exception. The container hands the error to the error handler.

An error handler may:

- Retry B according to backoff.
- Seek the partition back to the position that needs to be re-read.
- Recover B after retries are exhausted, for example by sending it to a DLT.
- Continue processing the remaining records according to the configured semantics.
- Commit offsets of completed records or recovered records according to the handler policy.

Do not assume that A is always replayed or always committed. Inspect the active error handler configuration and how the container manages pending offsets in your application's Spring Kafka version.

### 8.2. Batch Listener Failure

With a batch listener, if the method processes the entire list and throws an exception without indicating the failing record, the error handler may have to retry the whole batch because it does not know which record caused the error.

When using `DefaultErrorHandler`, a batch listener can throw `BatchListenerFailedException` with the index of the failed record. This lets the handler know which part has been processed and which part needs retry/recovery:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment-batch",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        try {
            fulfillmentService.process(records.get(i).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                "Could not process order event",
                ex,
                i
            );
        }
    }
}
~~~

When configuring a recoverer such as `DeadLetterPublishingRecoverer`, clearly verify which records are sent to the DLT and what condition counts as successful recovery. Do not mark a batch as successful merely because the error was logged.

### 8.3. Listener Swallowing Exceptions

If a listener catches an exception without rethrowing it or signaling a failure status to the container, the method returns normally. The container may treat the record or batch as successfully processed and commit the offset.

An example that easily causes lost processing:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    try {
        fulfillmentService.process(event);
    }
    catch (Exception ex) {
        log.error("Processing failed", ex);
        // Does not rethrow the exception and has no retry/recovery mechanism.
    }
}
~~~

If you want retries, let the exception propagate to the container/error handler or use an explicit recovery mechanism. Logging an error does not substitute for error-handling status.

## 9. Combining BATCH with Kafka Transactions

When the listener container is configured with a Kafka transaction manager, record processing and sending offsets can happen inside a Kafka transaction. The container starts the transaction, the listener processes the data, and then the container sends the offsets into the transaction and commits the transaction. If the transaction aborts, offsets inside the transaction are not committed alongside the output records.

For consume-transform-produce, this coordinates Kafka outputs and input offsets within the same transaction. Downstream consumers can use `isolation.level=read_committed` to read only committed records.

High-level example:

~~~java
@KafkaListener(topics = "orders.in", groupId = "order-transformer")
public void transform(OrderCreated event) {
    ValidatedOrder output = validator.validate(event);
    kafkaTemplate.send("orders.validated", event.orderId(), output);
}
~~~

When the listener container and KafkaTemplate are configured to participate in the same transaction, outputs and input offsets can be committed as one unit. How transaction ID prefix, transaction manager, and listener container are configured depends on the Spring Kafka version and how the application manages transactions.

A Kafka transaction does not automatically encompass relational database transactions or HTTP services. If the listener writes to a DB and then the Kafka transaction aborts, the DB does not automatically roll back. Outbox/inbox, DB transactions, and idempotency at system boundaries are required to manage side effects outside Kafka.

## 10. Interaction with poll, max.poll.records, and Concurrency

AckMode.BATCH is tied to the set of records from a single poll. Other consumer settings affect the size and processing cadence of that set.

### 10.1. max.poll.records

`max.poll.records` limits the number of records a consumer returns in a single poll. Increasing this value allows each batch to be larger, enabling the container to process more records before committing.

This can reduce commit overhead, but it also increases the time required to process a poll batch. If processing takes too long, the consumer may violate `max.poll.interval.ms` and be kicked out of the group.

### 10.2. max.poll.interval.ms

`max.poll.interval.ms` limits the interval between polls. With large batches or slow per-record processing, ensure the container can finish the work and invoke the next poll within the limit.

Do not increase `max.poll.interval.ms` mechanically. First measure p95/p99 processing time, poll batch size, downstream latency, and GC pause times. You may need to reduce `max.poll.records`, optimize processing, or split the workload.

### 10.3. Concurrency

A Spring Kafka listener container can run multiple consumers via concurrency. Each consumer has its own poll batch and offset commits.

Increasing concurrency can increase throughput when sufficient partitions and resources are available. However, concurrency higher than the useful number of assigned partitions can leave idle consumers with no partitions, while increasing connections and broker load. There is no single shared batch commit across consumers.

## 11. Observability and Diagnostics

To evaluate AckMode.BATCH, monitor commit behavior, consumer lag, processing latency, and retries together.

| Metric | What to Observe |
|---|---|
| Commit rate | Number of offset commits over time |
| Commit latency | Time to send and complete a commit |
| Records per poll | Average and maximum records in a single poll |
| Processing duration | Time to process each record or an entire batch |
| Consumer lag | Distance between log end offset and committed offset |
| Rebalance count | Frequency of consumer group assignment changes |
| Retry/recovery rate | Number of records or batches requiring retry/recovery |
| DLT rate | Number of events routed to a dead-letter topic |
| Duplicate detection | Number of events detected as already processed |
| End-to-end event age | Age of an event when business processing completes |

Exact metric names depend on the Kafka client, Spring Kafka, Micrometer, and the exporter. Some commit/processing details must be instrumented at the application or listener container layer because broker metrics alone cannot describe full business outcomes.

### 11.1. Operational Signals

- Commit rate decreases while throughput stays steady: BATCH is likely reducing commit overhead as intended.
- Consumer lag increases after increasing max.poll.records: larger batches may be lengthening processing time or saturating downstream systems.
- Duplicate detection increases after a restart: there may have been records processed but not yet committed before the process stopped.
- Rebalances increase alongside high processing duration: inspect max.poll.interval.ms, listener time, and GC.
- DLT rate increases: inspect exceptions, schemas, input data, and retry policy.
- Commit latency increases: inspect brokers, coordinator, network, and group health.

## 12. When Should You Use AckMode.BATCH?

BATCH is suitable when:

- The listener processes records relatively quickly and can finish the poll set within the poll interval limit.
- The workload has moderate or high throughput and wants to reduce commit frequency.
- The application tolerates replaying already-processed records if a failure occurs before commit.
- Side effects have idempotency or appropriate deduplication mechanisms.
- A batch listener can leverage bulk operations to improve efficiency.

Consider RECORD when individual records are expensive to process, when tighter commit boundaries are needed, or when you want to minimize the number of processed-yet-uncommitted records. However, per-record commits increase commit count and do not eliminate all duplicates in crash/rebalance scenarios.

If committing according to complex business logic is needed, MANUAL or MANUAL_IMMEDIATE may fit, provided acknowledgment ordering, consumer threads, and container behavior are clearly understood. Do not switch to manual solely to avoid duplicates; design idempotent side effects first.

## 13. Common Pitfalls

**Assuming BATCH means the listener must accept a List.** AckMode.BATCH is a per-poll commit policy. A record listener still works with it.

**Assuming a batch always has max.poll.records elements.** That is an upper bound, not a fixed size.

**Assuming committing after a batch eliminates duplicates.** The process can stop after side effects occur but before the commit. Uncommitted records can still be redelivered.

**Enabling enable.auto.commit alongside AckMode.BATCH.** Auto-commit can commit independently of the listener. Let the container manage offsets with auto-commit disabled.

**Swallowing exceptions inside the listener.** The container may treat the invocation as successful and commit offsets even though business logic did not complete.

**Assuming one batch belongs to a single partition.** A poll can contain records from multiple partitions and commit offsets separately per partition.

**Increasing max.poll.records without measuring processing time.** Larger batches can cause the consumer to exceed max.poll.interval.ms and trigger a rebalance.

**Assuming a Kafka transaction can roll back a DB.** A Kafka transaction covers only Kafka resources. DB side effects require their own transaction or outbox/inbox mechanism.

**Failing to inspect the error handler.** Retry, seek, recovery, and commit behavior when a listener fails depends on the error handler configuration and Spring Kafka version.

## 14. End-to-End Example: Processing Orders by Poll Batch

Suppose the `order-fulfillment` consumer group receives `OrderCreated` events. Each poll can return up to 200 records. The listener processes each record using a service that writes fulfillment status to a DB.

Configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      max-poll-records: 200
    listener:
      ack-mode: batch
      type: single
~~~

In one poll, the container receives 120 records spread across three partitions. The listener is invoked 120 times. Once all 120 invocations complete successfully, the container commits the next offset for each partition that had records in the poll.

If the process is stopped after writing to the DB for 90 records but before committing offsets, some or all uncommitted records may be redelivered after the consumer starts up. Therefore, the DB should store processed event IDs in the same transaction as the fulfillment update. When a record is redelivered, the consumer detects that the event has already completed and does not trigger the side effect a second time.

If a record causes an error, the exception must pass through the error handler. The operations team needs to define retry, backoff, DLT, and commit/recovery rules to ensure failed records are not silently skipped.

When measuring effectiveness, compare commit rate and commit latency before and after enabling BATCH, while tracking processing duration, lag, duplicate detection, and event freshness. Reducing commit count only helps if the consumer still finishes batches on time and processing quality does not degrade.

## 15. Implementation Workflow

1. Identify the actual Spring Kafka version and listener container in use.
2. Confirm `enable.auto.commit=false` so the container manages offsets.
3. Choose `AckMode.BATCH` in `spring.kafka.listener.ack-mode` or ContainerProperties.
4. Determine whether the listener is a record listener or batch listener; do not confuse listener type with AckMode.
5. Choose `max.poll.records` based on processing duration and downstream capacity.
6. Configure error handler, retry, backoff, and DLT for processing failures.
7. Make side effects idempotent to withstand replays prior to commit.
8. If using Kafka transactions, verify the transaction manager, producer factory, and `read_committed` on downstream consumers.
9. Measure commit rate, processing duration, lag, rebalances, duplicates, and event freshness under representative load.
10. Document commit and recovery policies in the runbook so the on-call team understands how records are handled during incidents.

## 16. Key Takeaways

AckMode.BATCH instructs the Spring Kafka listener container to commit offsets after all records returned in a single poll have been processed. It can reduce commit frequency and works with both record listeners and batch listeners.

In return, records that produced side effects but have not yet been committed can be redelivered after a crash or rebalance. Therefore, combine BATCH with an appropriate error handler, proper exception handling, an idempotent consumer, and processing-time measurements against max.poll.interval.ms. By understanding poll and commit boundaries clearly, operations teams can balance throughput, latency, and consumer recoverability.


