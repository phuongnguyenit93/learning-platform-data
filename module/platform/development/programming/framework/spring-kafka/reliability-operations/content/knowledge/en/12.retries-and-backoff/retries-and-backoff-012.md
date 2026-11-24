# Batch Retries

## 1. Batch retries in Spring Kafka

A Kafka consumer can read multiple records in a single `poll` call. When using a **batch listener** in Spring Kafka, the listener method receives an entire list of records to process. This approach fits bulk inserts, calling services that accept multiple items, or optimizing throughput.

However, if even one record fails, the application must decide how to retry: rerun the **entire batch**, or continue from the **failing record and unprocessed remainder**. That decision affects duplicate processing counts, consumer lag, offset commit timing, and data in target systems.

Example:

~~~text
Delivered batch:
   R0    R1    R2    R3    R4
   |     |     |     |     |
   OK    OK    X     ?     ?
               ^
           error at R2
~~~

If R0 and R1 already wrote to the database successfully and the batch is rerun, those two records may be processed again. If the entire batch executes inside a single database transaction that rolls back completely on failure, retrying the whole batch may fit.

In Spring Kafka, two key approaches are:

- **Retry the entire batch:** the listener throws a regular exception and the handler does not know which specific record failed.
- **Retry from the failing record:** the listener throws **BatchListenerFailedException** with the index of the failing record so **DefaultErrorHandler** has the information to handle the preceding and trailing portions.

Retries handle transient errors. They do not automatically guarantee exactly-once semantics for side effects in databases, HTTP APIs, or external systems outside Kafka.

## 2. Distinguishing poll batches, batch listeners, and producer batches

| Concept | Meaning |
|---|---|
| Producer batch | Producer groups records together to send to brokers more efficiently |
| Consumer poll batch | Set of records returned by `KafkaConsumer` from a single poll; may span multiple partitions |
| Batch listener | Spring Kafka method receiving a list of records in one invocation |
| Batch retry | Policy for reprocessing records in the batch when the listener fails |

Batch listener example:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderBatchContainerFactory"
)
public void handle(List<ConsumerRecord<String, OrderCreated>> records) {
    fulfillmentService.processBatch(records);
}
~~~

The number of delivered records is not fixed. **max.poll.records** is an upper bound per poll, not a mandatory count the listener must receive. A single poll can also fetch records from multiple partitions owned by the consumer.

~~~text
Index 0 -> partition 0, offset 40
Index 1 -> partition 0, offset 41
Index 2 -> partition 1, offset 98
Index 3 -> partition 1, offset 99
~~~

The index in the list is not a Kafka offset. An error handler needs the actual partition and offset to manage commits and redeliveries.

## 3. Why can one record's error affect the entire batch?

Suppose a listener processes five records sequentially and the third record fails. The method does not return normally, so the container cannot treat the batch as completed.

When the listener throws only a **RuntimeException**, the framework does not know whether the first, middle, or last record in the batch caused the error. With **DefaultErrorHandler**, this case is handled via fallback batch retry: the entire batch may be retried per `BackOff`, then routed to recovery once attempts run out.

~~~text
poll -> [A, B, C, D]
            |
            v
      processBatch()
            |
          error
            |
            v
    DefaultErrorHandler
            |
       BackOff left?
        /       \
      Yes       No
       |         |
       v         v
 retry batch   recovery per
                 policy
~~~

Consequently, a single failing record can trigger repeated runs for records that already succeeded. If each record triggers its own side effect, idempotency mechanisms are required to prevent duplicate business impacts.

### 3.1. When retrying the entire batch fits

Retrying the entire batch is usually suitable when:

- The entire batch runs inside a single DB transaction capable of true rollback.
- A bulk API reports errors at the batch level without identifying the failing element.
- Side effects are idempotent, so re-invoking does not alter the outcome a second time.
- A transient dependency fault is likely resolved on a fresh attempt.
- Business consistency requires processing the whole batch as a single unit.

If the listener already committed a few records before failing, retrying the entire batch may still satisfy at-least-once semantics while adding extra cost. When the failing record can be identified, consider reporting the failed index explicitly.

### 3.2. Bulk processing without transactions

Suppose a batch of 100 records is written to an external system outside Kafka. The API returns an error after writing 70 records, without telling you which records succeeded. Retrying everything may resend all 70 records. To stay safe, the dependency must support idempotency keys or the business needs a durable state reconciliation mechanism.

Merely logging "batch failed" is not enough to decide which offsets are safe to commit.

## 4. Identifying the failing record with BatchListenerFailedException

**BatchListenerFailedException** belongs to the **org.springframework.kafka.listener** package. A listener can throw it with the index of the failing record in the current list.

~~~java
throw new BatchListenerFailedException(
    "Fulfillment event failed",
    originalException,
    failedIndex
);
~~~

**failedIndex** is zero-based. If the third record fails, use index 2.

Example of a sequential processing listener:

~~~java
@Service
public class OrderBatchListener {

    private final FulfillmentService fulfillmentService;

    public OrderBatchListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "orderBatchContainerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (int index = 0; index < records.size(); index++) {
            var record = records.get(index);

            try {
                fulfillmentService.processIdempotently(record.value());
            }
            catch (RuntimeException ex) {
                throw new BatchListenerFailedException(
                    "Failed to handle order event",
                    ex,
                    index
                );
            }
        }
    }
}
~~~

When index 2 fails, the handler knows indices 0 and 1 precede the failure point. It can commit progress corresponding to the processed portion, then redeliver the failing record and remainder according to configuration.

| Data | Example | Use as failedIndex? |
|---|---|---|
| Position in `List` | `records.get(2)` | Yes |
| Kafka offset | `record.offset() = 120` | No |
| Partition | `record.partition() = 3` | No |
| Event ID | `order-102` | No |

Do not confuse index with offset. A batch can span multiple partitions, so there is no single offset for the entire list anyway.

### 4.1. Do not assume every record before the index committed

If the application processes records in parallel, index 4 might complete before index 2. In that situation, the index position does not accurately describe the side-effect state of every record.

**BatchListenerFailedException** works best when the listener knows for certain which records completed before the failure was detected. If processing in parallel, synchronize outcomes and make side effects idempotent before choosing a redelivery mechanism.

## 5. Configuring batch listeners in Spring Boot

You can enable a batch listener and let Spring Kafka manage offsets as follows:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      max-poll-records: 200
      auto-offset-reset: earliest
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
~~~

Meaning of the settings:

- **listener.type=batch:** endpoint uses a batch listener.
- **ack-mode=batch:** container manages commits per poll batch of records in normal processing flows.
- **enable-auto-commit=false:** prevents the Kafka client from committing offsets on its own timer before the listener finishes.
- **max-poll-records=200:** caps the number of records returned per poll.
- **concurrency=3:** listener container can spawn three child consumers running concurrently across assigned partitions.

Concurrency does not make two consumers in the same group read one partition in parallel. Each child consumer has its own poll batches and offset commits.

If the application defines a custom **ConcurrentKafkaListenerContainerFactory**, you must configure batch mode and the error handler on that exact factory; do not assume properties from an auto-configured factory are inherited.

## 6. Combining DefaultErrorHandler with BackOff

**DefaultErrorHandler** can use a **BackOff** to define retry counts and wait times between attempts. Example with **DeadLetterPublishingRecoverer** to handle records after retries run out:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    public DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer =
            new DeadLetterPublishingRecoverer(dltKafkaTemplate);

        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderBatchContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    DefaultErrorHandler ordersErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(ordersErrorHandler);

        return factory;
    }
}
~~~

In the **FixedBackOff(1_000L, 2L)** example:

- Wait interval between retries is roughly 1 second.
- There are at most two retries after the initial processing attempt per `FixedBackOff` semantics.
- Once retries are exhausted, the recoverer is invoked via the handler's error branch.

The snippet assumes suitable **ConsumerFactory**, `KafkaTemplate`, and serializers/deserializers already exist. If the DLT receives data of multiple types, ensure `KafkaTemplate` uses compatible serializers. The DLT topic and `WRITE` permissions are also required.

### 6.1. Choosing between FixedBackOff and ExponentialBackOff

**FixedBackOff** keeps a constant wait interval. It is predictable and fits transient errors with short recovery times.

For dependencies that recover more slowly, **ExponentialBackOff** can be used:

~~~java
var backOff = new ExponentialBackOff();
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(8_000L);
backOff.setMaxElapsedTime(30_000L);

var handler = new DefaultErrorHandler(recoverer, backOff);
~~~

Configuration values must match latency SLAs, record volume, and dependency load capacity. Set clear retry limits; prolonged retries keep failures lingering, increase lag, and delay subsequent batches.

### 6.2. BackOff applies only on errors

A succeeding batch does not wait merely because the handler is configured with `FixedBackOff`. Only when a batch fails does the handler apply the retry/recovery policy. Actual total duration also includes processing time, network time, downstream calls, and DLT send time.

## 7. Full-batch retry vs. retry from failed index

The two mechanisms differ in how much work must be repeated:

| Criterion | Full-batch retry | Retry from failed index |
|---|---|---|
| Common exception | `RuntimeException` or exception not identifying failed record | `BatchListenerFailedException` |
| Does handler know failing record? | No | Yes |
| Portion retried | Potentially the entire batch | Failing portion and remaining records per handler |
| Impact on already-processed records | May be invoked again | Can reduce records needing rerun |
| Best suited for | Bulk transactions or monolithic operations | Sequential record processing pinpointing specific errors |
| Requires idempotency | Yes | Still yes due to crashes/rebalances |

Example:

~~~text
Poll batch:   A   B   C   D   E
              OK  OK  X   ?   ?

RuntimeException:
  handler may retry [A, B, C, D, E]

BatchListenerFailedException(index=2):
  handler can handle progress of [A, B]
  then redeliver [C, D, E]
~~~

Exact semantics depend on the Spring Kafka version, error handler, `AckMode`, and how records are retained or sought. For listeners with Kafka transactions, check rollback mechanics separately.

## 8. Seeking and seek-free redelivery

When handling errors, the consumer must re-receive incomplete records. Spring Kafka supports different ways to achieve this.

### 8.1. Seeking to offset

With seek handling, the handler can reset read positions on partitions containing unprocessed records so `KafkaConsumer` rereads them.

~~~text
Partition 0:
  offset 10 -> OK
  offset 11 -> OK
  offset 12 -> FAILED
  offset 13 -> not yet processed

Can commit progress up to offset 12
and seek/redeliver from offset 12
~~~

Kafka commits **the next offset to read**. If offset 11 completed, the corresponding committed position is 12.

### 8.2. Redelivering from retained records

In supported Spring Kafka versions, setting **seekAfterError=false** can make the container retain unprocessed records to resend after a consumer-maintaining poll, instead of always seeking `KafkaConsumer`.

~~~java
var handler = new DefaultErrorHandler(
    recoverer,
    new FixedBackOff(1_000L, 2L)
);
handler.setSeekAfterError(false);
~~~

Not seeking does not mean the records were committed. It is simply a redelivery mechanism. Check effective configuration and semantics in your actual Spring Kafka version.

## 9. Retries and offset commits

Batch retries must align with offset commits. Consumer groups store offsets separately per partition.

Suppose a poll receives:

~~~text
index 0 -> P0 offset 10  : OK
index 1 -> P1 offset 50  : OK
index 2 -> P0 offset 11  : FAIL
index 3 -> P1 offset 51  : not yet processed
~~~

The failing record is P0 offset 11. The handler must compute progress for P0 and P1 separately—it cannot commit based on a single offset taken from index 2.

If the process crashes after writing to the database yet before committing to Kafka, uncommitted records can be redelivered. Thus, even when using `failedIndex` properly, the application still needs idempotency for critical side effects.

### 9.1. Disabling auto-commit when the container manages retries

If the Kafka client commits periodically in the background while the listener is processing, offsets can advance before side effects finish. This can cause lost processing when the process stops.

When using a Spring Kafka listener container and `DefaultErrorHandler`, set **enable.auto.commit=false** and an appropriate `AckMode` policy. Do not enable auto-commit independently of container-managed offsets.

### 9.2. Do not swallow exceptions

Improper example:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "orderBatchContainerFactory"
)
public void consume(List<OrderCreated> orders) {
    try {
        fulfillmentService.processBatch(orders);
    }
    catch (Exception ex) {
        log.error("Batch failed", ex);
        // Returns normally even though business logic failed.
    }
}
~~~

If the listener catches errors and returns normally, the container may treat the batch as successful and commit offsets. For the handler to retry, throw an exception or execute a clearly defined recovery mechanism.

## 10. Manual retries with nack(index, sleep)

Batch listeners can also use **Acknowledgment.nack(index, sleep)** when configured with an appropriate manual `AckMode`.

Example:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "manualOrderBatchContainerFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records,
        Acknowledgment ack) {

    for (int i = 0; i < records.size(); i++) {
        try {
            fulfillmentService.process(records.get(i).value());
        }
        catch (TemporaryDependencyException ex) {
            ack.nack(i, Duration.ofSeconds(2));
            return;
        }
    }
    ack.acknowledge();
}
~~~

The container factory requires manual ack mode:

~~~java
factory.setBatchListener(true);
factory.getContainerProperties()
    .setAckMode(ContainerProperties.AckMode.MANUAL);
~~~

When calling **nack(index, sleep)** in a batch listener, the container can commit progress for records before `index`, seek the remainder, and pause before continuing. The call must occur on the consumer thread and has interaction limits with **asyncAcks**. Check the API of the Spring Kafka version being deployed.

Comparison:

| Mechanism | Who controls retries? | Backoff |
|---|---|---|
| `BatchListenerFailedException` + `DefaultErrorHandler` | Error handler | Configured `BackOff` |
| `Acknowledgment.nack(index, sleep)` | Listener explicitly | Sleep requested by listener |

Do not both throw an exception and call `nack` for the same failure without clear rules, as that can make redelivery unpredictable.

## 11. Classifying errors before retrying

Not every error should be retried. A record with an invalid schema will not become valid after a few seconds. A database timeout, however, may recover.

| Error type | Example | Handling direction |
|---|---|---|
| Transient error | DB timeout, HTTP 503, connection reset | Bounded retry with backoff |
| Data error | Missing required field, invalid enum | Recovery/DLT, usually no prolonged retries |
| Configuration error | Missing Kafka permissions, wrong topic | Fix configuration or ACLs |
| Recoverable business error | Dependent state not yet synchronized | Retry within business deadline |
| Permanent error | Data violating unfixable invariant | DLT or manual handling |

Non-retryable exceptions can be configured on `DefaultErrorHandler`:

~~~java
handler.addNotRetryableExceptions(InvalidOrderException.class);
~~~

Understand the root exception, wrappers, and causes seen by the handler. With `BatchListenerFailedException`, the business exception may sit inside `cause`. Error classification policies must match the actual system.

### 11.1. Errors occurring before the listener

A deserialization error can happen inside the Kafka consumer before the listener receives the list. In that case, the listener cannot throw a failed index because no deserialized record exists yet.

You can use **ErrorHandlingDeserializer** and an appropriate container/error-handler policy to handle this class of errors. Do not assume every data-reading failure can be caught with `try/catch` inside a batch listener.

## 12. DLT and recovery after retries are exhausted

**DeadLetterPublishingRecoverer** is a common choice for moving unprocessable records to a dead-letter topic.

~~~java
var recoverer = new DeadLetterPublishingRecoverer(dltKafkaTemplate);

var handler = new DefaultErrorHandler(
    recoverer,
    new FixedBackOff(1_000L, 2L)
);
~~~

If the handler knows the failed index, it can target recovery at the failing record per supported semantics. If the entire batch fails without a failed index, fallback batch retry and recovery must be understood separately, because the handler may treat the whole batch without knowing which single record is poison.

A DLT should have:

- Enough topics and partitions for the destination resolver.
- Appropriate serializers for keys/values of records being published.
- `WRITE` permission for the DLT producer principal.
- Source metadata: topic, partition, offset, and exception.
- Backlog, ingress metrics, and alerts.
- Procedures for investigation, replay, and duplicate control on replay.

When DLT publishing fails, recovery must not be considered successful without evidence that the record was stored. Check how the recoverer handles publish results and how the handler reacts when the recoverer fails.

DLT does not mean the business operation is complete. It is a quarantine area for data requiring further handling.

## 13. Batch retries and @RetryableTopic

Spring Kafka supports non-blocking retry via retry topics and **@RetryableTopic** for many record listener cases. For batch listeners, **non-blocking retries are not supported in Spring Kafka's standard retry-topic mechanism**.

Therefore, do not rely on merely annotating a batch listener with **@RetryableTopic** expecting per-record non-blocking retries to work automatically.

If long delays are desired without holding the poll thread during retries, you can:

- Switch to a record listener if Spring Kafka's built-in retry-topic mechanism is needed.
- Build a dedicated custom retry pipeline with dedicated topics and producers.
- Clearly define ordering, offset commits, retry schedules, and idempotency.
- Consider a DLT if records cannot be processed.

Multi-minute delays may be unsuitable for consumer-blocking retries when trailing batches are waiting.

## 14. Preventing duplicates with an idempotent consumer

Batch retries typically go hand in hand with at-least-once delivery semantics. Even when the error handler commits the completed portion properly, the process can crash after side effects and before committing.

~~~text
Receive batch
   |
   +-- R0 -> DB commit succeeds
   +-- R1 -> DB commit succeeds
   +-- R2 -> timeout
   |
   +-- JVM crash before Kafka commit
   |
   v
Restart
   |
   v
R0, R1, R2 may be redelivered
~~~

To protect business logic, use a stable event ID and persist processed event state in the database:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

A single DB transaction should write both the side effect and the processed marker. A unique constraint prevents two runs of the same event from producing duplicate results. Merely checking **existsById** before inserting is insufficient under race conditions.

If the dependency is an external API, you need an idempotency key or reconciliation mechanism on the dependency. Kafka offsets and Kafka transactions cannot automatically roll back side effects in an HTTP service.

### 14.1. Full-batch retry and DB transactions

When an entire batch runs inside a single database transaction, failure can roll back all changes. Retrying the whole batch is then easier to reason about, though large batches can hold locks longer and increase contention.

When each record has its own transaction, some records may commit successfully before the error. Retrying from the failed index reduces repeated work, yet idempotency is still required for crashes and rebalances.

## 15. Transactional listeners and AfterRollbackProcessor

With Kafka transactions, error-handling flows differ from non-transactional `DefaultErrorHandler`. Exceptions can abort the transaction, and **AfterRollbackProcessor** decides how records are redelivered or recovered.

Example in consume-transform-produce:

1. Consumer reads input records.
2. Listener sends outputs to Kafka inside the transaction.
3. Input offsets are included in the transaction.
4. When the transaction commits, outputs and offsets commit as a single Kafka unit.
5. When the transaction aborts, uncommitted outputs and offsets in the transaction are not persisted.

This does not cover DB transactions or HTTP calls. If the listener successfully wrote to the DB before the Kafka transaction aborted, the DB does not automatically roll back. Therefore, design outbox/inbox or idempotent side effects.

Do not take non-transactional `DefaultErrorHandler` commit/seek behavior and apply it verbatim to transactional batch listeners. Verify the exact transaction manager, `AfterRollbackProcessor`, and Spring Kafka version in use.

## 16. Max poll interval, latency, and consumer liveness

Retries and backoff can lengthen the interval between polls. If the consumer fails to keep polling properly and exceeds **max.poll.interval.ms**, it may be deemed inactive in the consumer group.

Spring Kafka has poll, pause, and retry mechanisms to keep consumers valid in many situations. Nevertheless, a listener that sleeps manually for long stretches or runs blocking I/O without timeouts can still lose group membership.

Account for total duration:

- Processing time of records or bulk batches.
- Number of retries.
- Total backoff.
- Downstream timeouts.
- DLT publish and recovery time.
- GC pauses or resource contention waits.

Suppose a batch has 200 records, each averaging 20 ms when processed sequentially:

~~~text
200 records x 20 ms = 4,000 ms = 4 seconds
~~~

If one record hits a 5-second timeout and retries three times with 2-second backoff, batch duration increases noticeably. Measure p95/p99 rather than averages alone.

Risk-reduction options:

- Reduce `max.poll.records` when batches are too large.
- Set explicit timeouts on DB/HTTP calls.
- Choose bounded retry counts and backoff.
- Monitor rebalances and consumer lag.
- For long delayed retries, consider a separate asynchronous pipeline or a record listener with retry topics.

Never raise `max.poll.interval.ms` indefinitely to mask a hanging downstream service.

## 17. Impact on throughput and ordering

A single failing record in a batch can delay processing of trailing records. If a consumer manages multiple partitions, listener retry duration can also slow down the consumer's overall progress.

~~~text
Consumer A: partition P0, P1
    |
    +-- batch contains poison record in P0
    |
    +-- retry/backoff
    |
    +-- records belonging to P1 may also be delayed
~~~

Kafka guarantees order within each partition, with no global order across partitions. If business logic needs ordering by order ID, use proper keys/partitioning. Skipping failing records or moving them to a DLT lets progress continue, yet you must evaluate the impact of that missing record on ordering and business state.

Increasing concurrency only helps when there are sufficient partitions, resources, and downstream capacity. It does not make multiple consumers in the same group read a single partition in parallel.

## 18. Observability and metrics for batch retries

In operations, measure both per-record failures and full-batch failures.

| Metric | Question to answer |
|---|---|
| Batch size | How many records does each poll typically deliver? |
| Batch duration p95/p99 | Are batches processing fast enough? |
| Retry attempts | Are retries spiking by exception type? |
| Failed index | Do errors typically occur near the start or end of a batch? |
| Backoff accumulated time | How long are consumers waiting due to errors? |
| Recovery success/failure | Are recoverer/DLT publishes succeeding? |
| DLT ingress | How many records are being quarantined? |
| Consumer lag per partition | Which partitions are blocked? |
| Rebalance count | Are retries impacting group membership? |
| Commit latency/failures | Are offsets being persisted properly? |
| Event freshness | Does business completion time meet SLOs? |

Logs should include topic, partition, offset, batch index, exception class, and retry attempt:

~~~text
listener=order-batch
groupId=order-fulfillment
topic=orders.created
partition=2
offset=5130
batchIndex=18
exception=InventoryTimeoutException
retryAttempt=2
action=retry
~~~

Avoid using event ID, order ID, or offset as metric labels due to high cardinality. Keep those IDs in controlled logs/traces.

If retries rise alongside lag, a record may be blocking progress. If DLT volume spikes suddenly, check schemas, validation, and recent deployments. If rebalances rise alongside batch duration, inspect `max.poll.interval.ms` and blocking calls.

## 19. End-to-end example: Order Fulfillment

Order Fulfillment receives events from topic **orders.created**, processes each record via a service with an idempotency key, and routes failed records to a DLT once retries are exhausted.

Spring Boot configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      max-poll-records: 100
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderBatchContainerFactory"
)
public void handle(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int i = 0; i < records.size(); i++) {
        try {
            fulfillmentService.processIdempotently(
                records.get(i).value()
            );
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                "Order processing failed",
                ex,
                i
            );
        }
    }
}
~~~

Error handler:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
        dltKafkaTemplate
    );

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
~~~

Suppose a batch has 80 records and record index 25 hits a DB timeout. The listener throws **BatchListenerFailedException(index=25)**. The handler has the information to pinpoint the failing record and apply the retry policy. If the DB recovers, the flow continues. Once retries run out, the handler invokes the recoverer per configuration.

If the error is permanently invalid data, retrying repeatedly does not help. The policy can classify the error for earlier recovery. The DLT must have a handling procedure, because events entering the DLT have not yet completed the original business process.

If a pod crashes after the DB commits record index 20 yet before Kafka commits the offset, that record may be redelivered. **processIdempotently** must ensure the side effect does not happen a second time.

## 20. Common mistakes

**Assuming DefaultErrorHandler always knows which record failed.** If the listener only throws a generic `RuntimeException`, the handler may have to retry the entire batch.

**Passing offset instead of failed index.** `failedIndex` is a zero-based position in the listener's list.

**Retrying the entire batch even when side effects are non-idempotent.** Records that succeeded before the error may be processed again.

**Catching exceptions and only logging.** The container may treat the batch as successful and commit offsets.

**Configuring unlimited retries for poison records.** Permanent data errors need a DLT or manual handling, not endlessly growing consumer lag.

**Assuming recovery succeeded while DLT publishing still fails.** Verify the publisher and how the handler treats recovery errors.

**Putting @RetryableTopic on a batch listener expecting non-blocking retry to work automatically.** Standard retry-topic mechanisms do not support batch listeners.

**Ignoring max.poll.interval.ms.** Large batches, blocking calls, and long retries increase rebalance risk.

**Assuming Kafka transactions roll back databases.** Kafka transactions cover only Kafka resources; external side effects must be handled separately.

**Increasing concurrency to cure a hot partition.** A partition is still assigned to only one consumer in the group.

## 21. Adoption workflow

1. Confirm the listener receives batches and the actual factory has batch mode enabled.
2. Define transaction boundaries for side effects.
3. Choose between full-batch retry and retry from failed index.
4. If the failing record can be identified, throw `BatchListenerFailedException` with the zero-based index.
5. Configure `DefaultErrorHandler` and a bounded `BackOff`.
6. Classify non-retryable and retryable exceptions.
7. Configure DLT, serializers, topics, partitions, and ACLs.
8. Use event IDs and idempotency to guard against duplicate processing.
9. Choose `max.poll.records` and timeouts aligned with SLAs.
10. Measure retry attempts, lag, batch duration, DLT, and rebalances.
11. Test failures at the first, middle, and last record of a batch, plus restarts before commit.
12. Document retry/recovery policies clearly in runbooks.

## 22. Key takeaways

Batch retries require accurately identifying **which part failed** and **which offsets are safe to commit**. Without a failed index, `DefaultErrorHandler` may retry the entire batch. When the listener throws `BatchListenerFailedException` with the exact index, the handler can process the preceding portion and redeliver the incomplete portion according to policy.

`BackOff` dictates retry cadence, the recoverer defines handling once retries run out, and idempotency protects side effects when records are redelivered. Monitor latency, consumer lag, and DLTs to ensure retries help the system recover without corrupting business outcomes.

