# Non-Blocking Retry Does Not Support Batch Listeners

## 1. The Core Issue

Spring Kafka provides **non-blocking retry** to forward failed records to retry topics and reconsume them after a delay, typically configured via `@RetryableTopic` or `RetryTopicConfiguration`. This mechanism suits **record listeners**: each invocation receives and processes one record, and when it fails, the framework knows the exact record to route to a retry topic.

**Spring Kafka's non-blocking retry does not support batch listeners.** When a listener receives a batch of multiple records in a single call, you cannot directly pair a batch listener with retry-topic configuration in a framework-supported way. Combining `@RetryableTopic` with a batch listener does not yield a reliable per-element retry strategy.

Example of the difference:

~~~text
Record listener:
  Kafka record A -> listener(A) -> error -> retry topic -> listener(A) later
  Kafka record B -> listener(B) -> success -> continue

Batch listener:
  Kafka poll -> [A, B, C] -> listener([A, B, C])
                               |
                               +-- B fails
~~~

In the batch case, the framework would also need to know which record failed, which records already produced side effects, what may be committed, whether to replay the whole batch or just record B, and per-partition ordering. These requirements differ from forwarding a single record to a retry topic.

Therefore, when designing Spring Kafka Reliability Operations, explicitly choose one of two models:

- Keep the batch listener and use batch-appropriate error handling, typically `DefaultErrorHandler` with blocking retry/recovery.
- Switch to a record listener if non-blocking retry via retry topics is strictly required.
- If both batch processing and delayed per-record retries are needed, build a custom business retry mechanism with explicit offset contracts, idempotency, and DLT.

## 2. How Does Non-Blocking Retry Actually Work?

### 2.1. Retrying via Intermediate Topics

Unlike blocking retry, non-blocking retry does not hold the consumer thread waiting out backoff. When a record fails processing, the framework uses a producer to send it to a retry topic and lets the original topic's consumer keep processing other records per container policy.

After the configured delay, the listener bound to the retry topic receives the record and re-executes processing logic. If it still fails and retries remain, the record moves to the next retry topic or attempt; once exhausted, it can be forwarded to a dead-letter topic (DLT).

~~~mermaid
flowchart LR
    A[Topic orders] --> B[Record listener]
    B -->|Success| C[Processing complete]
    B -->|Retryable error| D[Retry topic]
    D -->|Wait elapsed| E[Retry listener]
    E -->|Success| C
    E -->|Still failing| F{Retries left?}
    F -->|Yes| D
    F -->|No| G[DLT]
~~~

This is a logical diagram: the number of topics created, topic names, topic reuse behavior, and routing depend on your Spring Kafka version's retry-topic configuration.

Non-blocking retry does not mean all processing is asynchronous or threadless. Consumers on the main topic and retry topics still run on threads/containers; what is avoided is holding a thread directly across long backoff waits.

### 2.2. One Record Is the Unit of Failure and Retry

With a record listener, the framework has full metadata to identify the failing record: topic, partition, offset, key, value, and related headers. The retry infrastructure can create a new record on a retry topic carrying metadata and headers for attempt tracking.

Example:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000L, multiplier = 2.0)
)
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrder(OrderCreated event) {
    billingService.applyIdempotently(event);
}
~~~

This example uses the annotation in Spring Kafka with retry-topic support and corresponding imports. `attempts = "4"` expresses total deliveries per annotation semantics, including the initial attempt and retries. The initial wait is one second and can double with multiplier 2.

If the record succeeds on an attempt, it stops advancing to further retry topics. If retries exhaust, the record routes to the DLT per configuration.

### 2.3. Strict Per-Partition Ordering Is Not Preserved

When record A fails and moves to a retry topic, the original topic can keep processing record B arriving after A. Thus, non-blocking retry can make business completion order differ from original offset order.

~~~text
Main topic (partition P0): A(offset 10), B(offset 11)

A fails -> moved to retry topic, wait 5 seconds
B succeeds immediately
A is retried and succeeds later

Completion order: B -> A
~~~

If events for the same order, account, or aggregate require strict ordering, evaluate carefully before adopting retry topics. This applies equally to record listeners; converting a batch listener to a record listener does not restore ordering once non-blocking retry is enabled.

## 3. What Is a Batch Listener?

A batch listener receives a list of records from a poll or a group of records delivered by the container, rather than a single record.

Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

The factory must be configured in batch mode:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);

    return factory;
}
~~~

A single batch can hold records from multiple partitions assigned to the same consumer. Actual batch size depends on available records, `max.poll.records`, fetch settings, and poll conditions.

Batch listeners are useful when downstreams support batch operations, such as writing hundreds of rows in one database transaction or reducing network round-trips. In return, error handling and offset commits become complex when some elements succeed while others fail.

## 4. Why Can't Non-Blocking Retry Be Paired Directly with Batch Listeners?

### 4.1. Unit of Failure Does Not Match Unit of Retry

The retry-topic infrastructure operates on individual records. A batch listener receives a collection, and an exception inside the listener may represent a single-record failure or an entire-batch failure.

Suppose a batch contains:

~~~text
Partition orders-0:
  offset 100: event A -> DB write succeeded
  offset 101: event B -> timeout error
  offset 102: event C -> not yet processed
~~~

Forwarding the entire batch to a retry topic as one payload would not automatically preserve each record's original metadata under the record-listener model. Forwarding only B requires the app to distinguish whether A finished, whether C ran, and which offsets may be committed.

Spring Kafka provides dedicated error handling for batch listeners, whereas the non-blocking retry-topic infrastructure has no contract supporting batch listeners as part of that mechanism.

### 4.2. A Batch Can Span Multiple Partitions

A batch can contain:

~~~text
orders-0 offset 100
orders-0 offset 101
orders-1 offset 45
orders-1 offset 46
~~~

Offset commits are stored per topic-partition. A failed batch does not map to a single offset. If some records completed, the container must track contiguous progress per partition; it must never commit past an unprocessed or unrecovered record.

### 4.3. Forwarding One Record to a Retry Topic Affects Source Commits

With non-blocking retry, a failed record is published to a retry topic and handled in the retry flow. The source topic consumer's progress must honor the handoff contract: if retry publishing fails yet the source offset advances, events can be lost; if publishing succeeds yet the source offset is not committed, duplicate retry records can be produced on restart.

The record-listener mechanism is built for this path. Batch listeners add partial success, partial commits, and batch-level errors that make that path substantially more complex.

### 4.4. Batch Ordering and Transactions Can Break

If `processBatch(events)` wraps the whole batch in one database transaction, moving a single failed element to a retry topic may break the atomicity of the original operation. Conversely, if records commit individually in the database, retrying the entire batch can repeat side effects.

Accordingly, this support boundary is a design constraint to respect when selecting a retry architecture.

## 5. Example of an Incompatible Configuration

The snippet below illustrates attempting to combine two features Spring Kafka does not support together on the same endpoint:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000L)
)
@KafkaListener(
    topics = "orders",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

The problem is that the container factory uses a batch listener while `@RetryableTopic` is intended for record-listener non-blocking retry. Depending on version and configuration, the application may fail when creating the endpoint/container or lack expected supported retry behavior. Never assume that a configuration happening to boot has valid recovery semantics.

Nor can you fix it by raising `concurrency`, changing `ack-mode`, or adding `@DltHandler`. Those changes do not turn non-blocking retry into a batch-listener-supported mechanism.

## 6. Option 1: Keep the Batch Listener and Use DefaultErrorHandler

This is a common choice when batch efficiency is prioritized, container-level blocking retries are acceptable, and per-index error control is needed.

### 6.1. Configuring the Batch Container and Error Handler

~~~java
@Configuration
public class BatchConsumerConfiguration {

    @Bean
    public DefaultErrorHandler batchErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate
    ) {
        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            batchKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler batchErrorHandler
            ) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(batchErrorHandler);

        return factory;
    }
}
~~~

This example uses Spring Kafka's `DefaultErrorHandler`. `FixedBackOff(1_000L, 2L)` allows two additional retries, one second apart. Once retries exhaust, the recoverer can publish failed records to the DLT per configuration.

The DLT publisher must be configured with matching serializers, destination topics, partitions, and write permissions. If recovery fails, the record must not be treated as recovered.

### 6.2. Identifying the Failed Record with BatchListenerFailedException

If a batch is processed sequentially element-by-element and the listener knows which index failed, it can throw `BatchListenerFailedException`:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
    List<ConsumerRecord<String, OrderCreated>> records
) {
    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderCreated> record = records.get(i);

        try {
            billingService.applyIdempotently(record.value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Cannot process record at batch index " + i,
                ex,
                i
            );
        }
    }
}
~~~

`BatchListenerFailedException` carries the failing index (or record), helping the error handler distinguish completed items from remaining ones. How offsets before the failed record are committed, redelivery, and recovery depend on container/error handler configuration and Spring Kafka version.

This is **blocking retry via batch error handling**, not non-blocking retry through retry topics. The consumer handles the failing record within the container and may delay subsequent records until retry/recovery finishes.

If a batch includes records from multiple partitions, rely on the error handler and acknowledgment mode to manage each partition's offset; never assume the entire batch shares one offset.

### 6.3. When the Failing Record Is Unknown

If the batch method throws a generic exception without identifying the failing element, `DefaultErrorHandler` can fall back to batch-level retry. In that case, the entire batch may be retried, and records that already caused side effects previously may be reprocessed.

Example:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    billingService.processBatch(events); // Error does not specify index
}
~~~

This model fits better when `processBatch` is wrapped in an atomic database transaction: on success the whole batch commits, on failure all database work rolls back. If the batch committed partial side effects, retrying the whole batch requires per-event idempotency.

## 7. How Does Blocking Retry Affect Operations?

Blocking retry holds the record/batch on the consumer container's processing path while executing retries and backoffs. This can slow down that partition or other partitions owned by the same consumer.

For example, a batch listener processes 500 records and one element hits a database timeout. If the error handler retries several times with long backoffs, consumer lag can grow during that time.

Factors to control:

| Configuration / factor | Impact |
|---|---|
| `max.poll.records` | Maximum records returned per poll; affects batch size |
| `max.poll.interval.ms` | Maximum time between polls; overly long processing can trigger rebalances |
| `FixedBackOff` / `ExponentialBackOff` | Number of retries and wait times |
| `AckMode` | How the container commits progress after processing |
| Listener processing duration | Business execution time |
| `concurrency` | Number of consumers in container, bounded by partitions |
| DLT recoverer | Destination once retries are exhausted |

Do not set unbounded backoffs if a poison record can block the entire stream. For unrecoverable errors like malformed schemas, classify them as non-retryable and route to recovery per policy.

## 8. Option 2: Switch to a Record Listener to Use @RetryableTopic

If the core requirement is **retrying individual records after a delay without blocking the main consumer**, a record listener is the supported path.

### 8.1. Complete Example

~~~java
@Component
@RequiredArgsConstructor
public class OrderConsumer {

    private final BillingService billingService;

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2_000L, multiplier = 2.0),
        autoCreateTopics = "false"
    )
    @KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        containerFactory = "recordKafkaListenerContainerFactory"
    )
    public void onOrder(OrderCreated event) {
        billingService.applyIdempotently(event);
    }

    @DltHandler
    public void onDlt(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String receivedTopic
    ) {
        log.error("Order could not be processed from {}", receivedTopic);
        // Record event ID and status requiring manual handling.
    }
}
~~~

This example illustrates the required annotations; the project must also configure producer/consumer serialization, retry/DLT topics, and corresponding imports. With `autoCreateTopics = "false"`, retry and DLT topics must be provisioned beforehand.

This endpoint's container factory must be in **record listener** mode:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        recordKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(false);

    return factory;
}
~~~

Depending on Spring Kafka version, additional retry-topic configuration, beans, and KafkaTemplate may be needed for the framework to create the retry infrastructure. Do not attach a batch factory to this endpoint.

### 8.2. Batching Can Still Happen in the Kafka Client

A record listener does not mean the Kafka client fetches one record at a time. A single `poll()` can still return many records, while the container dispatches them to the listener method one by one.

What is removed is the business callback receiving an entire collection at once. That lets the framework pinpoint which record failed and forward it to a retry topic.

### 8.3. If Throughput Needs Optimization

You can optimize a record listener by:

- Increasing concurrency sensibly relative to partition count and replicas.
- Reducing per-event database overhead.
- Using caching or statement batching at the repository layer with explicit transactions.
- Enforcing idempotent processing to handle duplicates.
- Setting timeouts on HTTP/database calls.
- Measuring throughput and consumer lag before tuning.

If you want to buffer received records for batched database writes, you can use a bounded business buffer, but you must define when the listener counts as succeeded. If the listener returns before the buffer is durably flushed, the container may advance offsets prematurely, risking data loss if the process stops.

## 9. Option 3: Separate Record-Level Ingestion from Downstream Batch Processing

Another architecture uses a record listener with non-blocking retry at the ingestion layer, then writes validated events into a durable queue or outbox for batched processing by another worker/service.

~~~mermaid
flowchart TD
    A[Kafka orders] --> B[Record listener + @RetryableTopic]
    B -->|Validation/ingestion succeeds| C[Durable inbox or work queue]
    B -->|Transient error| R[Retry topic]
    R --> B
    B -->|Attempts exhausted| D[DLT]
    C --> E[Batch worker]
    E --> F[Database batch operation]
~~~

This design draws two clear boundaries:

- **Kafka ingestion:** each record is durably persisted to an inbox/queue before the listener returns success.
- **Batch processing:** a worker reads stored items, batches them by size/time, processes them, and updates status.

The upside is combining retry topics for ingestion failures with batch operations downstream. However, the system needs durable storage, work-item lifecycle management, idempotency, separate retries for the batch worker, and recovery when the worker fails.

Never use an in-memory `List` as the sole queue and return from the listener as if the event were durably processed.

## 10. Option 4: Custom Non-Blocking Retry for Failed Records in a Batch

Some systems must keep a batch listener while deferring only a few failed records. In that case, you can build a custom path forwarding failed records to a retry topic:

1. The batch listener receives the list of records.
2. The application processes records under an explicit policy, identifying succeeded vs. failed records.
3. Failed records are published to a dedicated retry topic carrying event ID, original topic/partition/offset, and attempt info.
4. Only after retry publishing is confirmed per chosen durability criteria does the application consider the handoff complete.
5. Source offsets are committed without skipping any unprocessed or unconfirmed record.
6. A separate record listener consumes the retry topic and applies retry/DLQ policy.

This is a **custom design**, not `@RetryableTopic` directly supporting batch listeners. When building it, you must solve several error-prone edges:

- If retry publishing succeeds yet source offset commit fails, records can reappear; idempotency is required.
- If source offsets commit before retry publishing completes, records can be lost on crash.
- If a partition's record is unfinished yet commits advance past it, consumer restarts can skip that record.
- If a batch spans multiple partitions, progress must be tracked per partition.
- If the retry topic falls behind, dedicated retention, DLT, replay, alerts, and quotas may be needed.
- If business rules require per-key ordering, moving records to a retry topic can change completion order.
- If retry publishing times out, the broker may still have written it; resending can create duplicates.

Weigh implementation and operational costs before picking this approach. For typical requirements, `DefaultErrorHandler` for batches or a record listener with `@RetryableTopic` is easier to govern.

## 11. Committing Offsets When Batch Processing Fails

### 11.1. Offsets Always Belong to Each Topic-Partition

Suppose a poll returns:

~~~text
orders-0: offsets 30, 31, 32
orders-1: offsets 10, 11
~~~

If `orders-0` offset 31 fails, you must not commit offset 33 for partition 0 before record 31 is safely processed/recovered. Meanwhile, partition 1's progress is independent of partition 0; the container and error handler must manage them according to policy.

The committed offset is the **next** position the group will read, not the offset of the last processed record.

### 11.2. Batch Retries Can Cause Redeliveries

If a listener writes to the database for offset 30 and crashes before committing the offset, Kafka can redeliver offset 30 after restart. Therefore, even when using `BatchListenerFailedException`, business logic should still use stable event IDs, unique constraints, an inbox, or idempotent upserts.

Conceptual example:

~~~java
@Transactional
public void applyIdempotently(OrderCreated event) {
    if (!inboxRepository.insertIfAbsent(event.eventId())) {
        return;
    }

    orderRepository.updateFromEvent(event);
}
~~~

Inbox insertion and business updates must share the same database transaction. If the update fails, the inbox insert also rolls back. When redelivered, the unique constraint detects the already-processed event and avoids duplicate side effects.

### 11.3. Do Not Treat DLT as an Automatic Commit

Publishing a failed record to a DLT is a recovery step. How source offsets commit depends on the error handler and acknowledgment mode. If the DLT publisher fails, never silently consider the record recovered.

When using `DeadLetterPublishingRecoverer`, verify send-result checks, timeouts, and recovery retry behavior. Distinguish the producer accepting a send call from the broker confirming the record.

## 12. BatchListenerFailedException vs. Unknown-Index Failures

Spring Kafka distinguishes cases where the listener knows which record in the batch failed from cases where only the whole batch failed.

| Scenario | How failure is reported | Consequence |
|---|---|---|
| One record fails at a clear index | Throw `BatchListenerFailedException` | Error handler can handle completed vs. remaining items by index |
| Atomic batch operation fails | Throw a normal exception | May need whole-batch retry or full side-effect rollback |
| Multiple independent records fail in one batch | Requires an explicit app policy | A single index cannot represent multiple independent failures |
| Deserialization fails before creating objects | Requires deserializer/container error handling | Listener may not receive normal objects |
| Recovery/DLT publish fails | Recoverer throws exception | Record may not be recovered; further handling needed |

Never catch an exception and return normally if unprocessed records remain. When a listener returns normally, the container may consider the batch done and commit offsets, depending on mode.

If processing element-by-element and collecting multiple failures only at the end of the batch, design failure storage and progress commits so no unfinished offset range is skipped.

## 13. Batch Listeners with Transactions

If a batch writes to a database inside one transaction, committing/rolling back the whole batch reduces partial success at the database layer. For instance, a `@Transactional` service method writes the whole batch and rolls back on exception.

~~~java
@Service
@RequiredArgsConstructor
public class BatchBillingService {

    private final OrderRepository repository;

    @Transactional
    public void processBatch(List<OrderCreated> events) {
        for (OrderCreated event : events) {
            repository.apply(event);
        }
    }
}
~~~

This provides atomicity only within the database transaction boundary. Kafka offset commits remain a separate operation unless the architecture has proper transaction coordination. After database commit yet before offset commit, the batch can still be redelivered; idempotency remains mandatory.

Another limitation: Spring Kafka's non-blocking retry infrastructure does not support batch listeners, and also has limitations when combining non-blocking retry with container transactions. Do not enable multiple transaction and retry mechanisms simultaneously and assume they automatically coordinate into exactly-once across databases and Kafka.

If business logic requires atomic batch processing, retrying the whole batch inside the container can preserve simpler semantics than splitting individual records to retry topics.

## 14. DLT Across Both Approaches

Both batch error handlers and non-blocking retry for record listeners can send unrecoverable records to a dead-letter topic, though their paths differ.

| Characteristic | Batch + DefaultErrorHandler | Record + @RetryableTopic |
|---|---|---|
| Where failure originates | Batch listener | Record listener |
| How retries work | Blocking in container or batch-handling mechanism | Forwarded to retry topics, reconsumed after delay |
| Unit of failure to identify | Record index or whole batch | Single record |
| After retries exhaust | Recoverer, can publish to DLT | Retry-topic infrastructure routes to DLT |
| Ordering | Can maintain stricter sequence during blocking retries | Later records can complete first |
| Resources | Consumer/container waits during retries | Extra topics, producers, and retry consumers |
| Operations | Monitor batch failures, handler, lag | Monitor retry topics, DLT lag, delays, attempts |

Never judge reliability solely by a DLT existing. Track DLT publish successes/failures, retention periods, pending record counts, and replay procedures.

DLT consumers must handle duplicates safely, especially when timeouts leave uncertainty about whether a record was published.

## 15. Impact on Ordering and SLAs

### 15.1. When Ordering Is Prioritized

If `OrderCreated`, `OrderPaid`, and `OrderShipped` must be applied in strict order, moving the first event to a retry topic while later events keep processing can break business invariants.

In that case, consider per-partition blocking retry with bounded wait times and explicit poison-record handling. You can also use a state machine supporting late events or storing pending events, though that requires business architecture changes.

### 15.2. When Throughput Is Prioritized

If records are independent, can be processed in any order, and downstream recovery times vary, non-blocking retry on a record listener lets the main topic advance when one record fails.

However, retry topics add load on brokers, producers, consumers, and monitoring. If failure rates spike, retry topics can grow large backlogs. Configure retry policies, DLTs, and alerts accordingly.

### 15.3. When Batch I/O Is Prioritized

If batched database operations save substantial time and network overhead, keeping a batch listener with `DefaultErrorHandler` is often the practical choice. Load-test batch sizes, concurrency, and backoffs to ensure `max.poll.interval.ms` is not breached by slow processing.

## 16. Designing a Retry Policy for Batch Listeners

A sound retry policy classifies errors:

- **Transient:** database timeouts, transient disconnects, HTTP 503. Can retry with bounded backoff.
- **Permanent:** schema-violating payloads, missing required fields, invalid data types. Typically recover or route to DLT early.
- **Valid duplicate:** event ID already processed; listener can return success without repeating side effects.
- **Ambiguous-outcome error:** database transaction or DLT publish timeout. Inspect durable state and apply idempotency.

Example classification on a handler:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

handler.addNotRetryableExceptions(
    IllegalArgumentException.class
);
~~~

The exception list must match the domain. Some errors like unique constraint violations may indicate valid duplicates or serious business bugs; never hard-classify without understanding the cause.

Backoffs must be bounded. An unprocessable poison record must not hold a partition forever and drive unbounded consumer lag.

## 17. Consumer and Batch Size Configuration

Batch listeners cannot be paired with retry topics, yet many parameters still govern reliability and throughput.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      max-poll-records: 200
      auto-offset-reset: earliest
    listener:
      type: batch
      concurrency: 3
      ack-mode: batch
~~~

This example uses Spring Boot with the listener properties listed above. Verify effective configuration if the app defines a custom factory, as custom factories can override Boot properties.

Explanation:

- `max-poll-records` caps records returned per poll; it does not guarantee every batch has exactly 200 items.
- `concurrency` controls container consumers; maximum parallelism depends on partition and replica counts.
- `ack-mode: batch` commits according to container-managed poll/batch progress.
- `enable-auto-commit: false` prevents timer-based auto-commits detached from listener outcomes.

If increasing batch size pushes processing past `max.poll.interval.ms`, consumers can rebalance and records can be redelivered. Tune batch size, concurrency, downstream timeouts, and retry durations together.

## 18. Observability When a Batch Listener Fails

Collect the following data to determine which record failed and whether recovery worked:

| Info / metric | Purpose |
|---|---|
| Original topic, partition, offset | Trace the exact source record |
| Consumer group and client ID | Identify the processing instance |
| Batch size | Measure data volume during failure |
| Failed record index | Distinguish single-element failure from whole-batch failure |
| Exception class and root cause | Classify transient vs. permanent errors |
| Retry attempts, backoff | Determine how many tries occurred |
| Recovery/DLT send result | Confirm whether the failed record was durably handed off |
| Per-partition consumer lag | Detect stalled partitions |
| Listener processing duration | Predict risk of breaching max poll interval |
| DLT topic lag | Detect operational backlog |

Avoid logging full payloads if they contain personal data or secrets. Log event IDs, correlation IDs, topics, partitions, offsets, and exception types instead.

With non-blocking retry, separately monitor throughput and lag of retry topics, waiting record counts, actual retry delays, and the DLT. Never fold retry successes into original-topic success metrics if that causes double counting.

## 19. Test Scenarios to Validate Architectural Choice

### 19.1. Batch + DefaultErrorHandler

1. Create a test topic with at least one partition.
2. Send multiple records in a single poll.
3. Make a record at a known index throw an exception on the first attempt.
4. Use `BatchListenerFailedException` and `FixedBackOff`.
5. Confirm items before the failure, the failing item, and items after it are handled per policy.
6. Confirm committed offsets do not advance past unfinished records.
7. Trigger recoverer/DLT behavior after retries exhaust.
8. Verify duplicates and idempotency after restarting the consumer.

### 19.2. Record + @RetryableTopic

1. Create main, retry, and DLT topics per configuration.
2. Make record A throw an exception on its first attempt.
3. Send record B after A on the same partition.
4. Confirm A moves to a retry topic while B can be processed on the main topic.
5. Confirm A is retried after the expected delay.
6. When A keeps failing, confirm the event routes to the DLT per policy.
7. Observe changes in completion order and consumer lag.
8. Verify a failed retry-topic publish does not cause the source record to be skipped.

### 19.3. Migrating a Batch Listener to a Record Listener

During migration, also test:

- Throughput under identical load and partition counts.
- Database connection pools and transaction counts.
- p95/p99 processing times.
- Side-effect execution counts on redeliveries.
- Per-key ordering and how the app handles late-arriving events.
- Retry topic counts, retention, and DLT processing capacity.

Do not assume the app becomes faster or more reliable merely by switching to a record listener. Measure both the lost batch I/O efficiency and the benefit of isolating failing records.

## 20. Common Design Mistakes

**Attaching `@RetryableTopic` to a batch listener:** this is an unsupported combination; never use it as a production retry path.

**Assuming the annotation can retry individual List elements:** the framework provides no such batch retry-topic contract.

**Using `BatchListenerFailedException` as a way to enable non-blocking retry:** this exception supports batch error handling with a compatible error handler; it does not turn a batch listener into a record listener.

**Retrying a whole batch after committing partial side effects:** can repeat updates or event publishes; requires transactions or idempotency.

**Catching errors and returning normally:** the container may commit offsets even though the batch did not finish processing.

**Committing past unfinished records:** loses the chance to process records on consumer restart.

**Manually publishing failed records to a retry topic without waiting for results:** if source offsets commit before retry publishing is durable, records can be lost.

**Ignoring ordering:** later records can complete before records waiting in retry topics.

**Unbounded backoffs:** a single failing record can stall the batch listener indefinitely and grow consumer lag.

**Not provisioning retry/DLT topics:** missing topics, missing partitions, or missing ACLs can break recovery right when needed most.

**Not checking the DLT publisher:** the recoverer can fail or time out; a record cannot yet be assumed safely handed off.

**Using an in-memory queue as a durable boundary:** process crashes can lose events after offsets were committed.

## 21. Rules for Choosing a Production Solution

| Primary requirement | Recommended option | What to protect |
|---|---|---|
| Need batched database ops and retry on batch failure | Batch listener + DefaultErrorHandler | Transactions, failing index, commits, and idempotency |
| Need delayed per-record retry while main topic advances | Record listener + @RetryableTopic | Ordering, retry/DLT topics, and idempotency |
| Need downstream batching plus independent per-record retry | Record listener + durable inbox/queue + batch worker | Atomic handoff, backpressure, worker retries |
| Atomic batch processing, must roll back entirely on error | Batch listener + transaction + batch error handling | DB commit and Kafka offset commit |
| Need to handle permanent errors without blocking forever | DLT/recoverer with verification | DLT reliability and replay |
| Need strict per-key ordering | Prefer retries that do not overtake failed records or stateful handling | Partition ordering and deadlines |
| Need custom forwarding of failed batch records to retry topics | Custom solution with explicit contracts | Partial commits, duplicates, and ownership |

An effective decision workflow:

1. Determine whether batch side effects are atomic or per-record independent.
2. Determine whether completing later records before a failed record is acceptable.
3. Determine maximum retry delay and whether the container can wait during that window.
4. Measure throughput with a record listener versus a batch listener.
5. Pick the retry path supported by Spring Kafka for that listener type.
6. Design offset commits, idempotency, DLT, and metrics before rollout.
7. Test failures between database commit, retry/DLT publish, and Kafka offset commit.

**Spring Kafka's non-blocking retry does not support batch listeners**—a boundary that must be factored into design from the start. If retry-topic retries are needed, use a record listener and actively manage ordering. If batch processing is needed, use batch-compatible error handlers and control partial failures, transactions, and offsets. If both requirements must be met, separate record-level ingestion from batched processing using a durable storage layer with idempotency.
