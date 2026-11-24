# Per-Record Retry

In a Spring Kafka consumer, not every record is processed successfully on the first try. A database may lose connectivity for a few seconds, an HTTP API may return 503, a business key may experience contention, or a record's data may be invalid. **Per-record retry** is a controlled way to handle a failing record: retry when the error is recoverable, limit the number of attempts and wait duration, and then perform recovery or route the record to a Dead Letter Topic (DLT) if failures persist.

In the **Retries and Backoff** chapter of Spring Kafka Reliability Operations, what matters is not merely writing a retry loop. Retries must work properly with the Kafka consumer poll loop, offset commits, partition ordering, rebalances, and duplicate handling. A flawed retry policy can turn a transient glitch into prolonged consumer lag or a retry storm, while a flawed recovery policy can cause records to be silently skipped forever.

This lesson covers retrying record listeners with **DefaultErrorHandler**, defining backoff and exception classification, recovering via DLT, the differences between blocking and non-blocking retry, and operational scenarios to verify.

## 1. What is per-record retry?

A record listener receives a single `ConsumerRecord` or payload per listener invocation. When the listener throws an exception, the Spring Kafka container delegates the error to the error handler. The handler decides which record must be reprocessed, how long to wait, when to stop retrying, and when to recover.

Listener example:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "order-processing",
        topics = "orders",
        groupId = "order-processing-prod"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

If `orderService.process()` throws an exception, the container must not treat processing of that record as successful. If the retry policy permits, the listener is invoked again with the failed record. Once retries expire, the recoverer handles it according to configured policy.

A common implementation pattern:

~~~mermaid
flowchart TD
    P["Consumer polls records"] --> L["Record listener processes record A"]
    L --> Q{"Listener succeeds?"}
    Q -->|Yes| S["Continue records and commit per AckMode"]
    Q -->|No| E["DefaultErrorHandler receives exception"]
    E --> C{"Exception retried?"}
    C -->|Yes| B["BackOff: wait per policy"]
    B --> R["Re-invoke listener with record A"]
    R --> Q
    C -->|No| D["Recoverer handles record A"]
    E --> X{"Retries exhausted?"}
    X -->|Yes| D
    D --> Y{"Recovery succeeds?"}
    Y -->|Yes| N["Skip failed record per policy and continue"]
    Y -->|No| F["Keep error for reprocessing; alert"]
~~~

The diagram conveys the idea. In practice, the handler coordinates retry state, offsets, and the remaining records from the poll. Retrying is not simply calling a method in an infinite loop.

### 1.1 Retry and redelivery are different

Two phenomena can cause the same record to be processed multiple times:

- **Retry in the error handler**: the listener throws an exception and Spring Kafka actively retries per `BackOff`.
- **Redelivery from Kafka**: the record was read, yet its offset has not been committed; after a restart, rebalance, or seek, the consumer can receive the record again.

Both can result in repeated processing. Therefore, even if the handler restricts retries to a single attempt, the application must still expect a record to return after a process crash.

### 1.2 Why retry at the record level?

Per-record retry makes it possible to pinpoint the failing record, tune attempt counts, classify exceptions, and choose recovery independently of records that already succeeded.

For instance, a poll returns A, B, C, D; the listener succeeds on A and B, and fails on C. With a record listener, the container knows C is the failing record and can retry C. Subsequent records must still be processed safely according to per-partition offsets and ordering. Handler configuration determines how remaining records are retained or refetched.

Per-record retry is especially suitable when:

- A single failing record can be clearly identified.
- Each record has its own side effects or idempotency key.
- You want to separate transient errors from poison records.
- You need to send the exact failing record to a DLT.
- You want to avoid reprocessing many records that already succeeded within the same poll.

## 2. Four decisions required before enabling retries

A complete retry policy must answer four questions:

1. **Which errors to retry?** Connection timeouts and HTTP 503 are often recoverable; data missing required fields usually is not.
2. **How many times to retry and how long to wait?** Bound attempt counts and calculate total impact on the consumer.
3. **Where to retry?** Hold the consumer thread via blocking retry, or route the record through retry topics for later processing.
4. **What to do after retries are exhausted?** Publish to DLT, persist error state in a durable store, halt processing, or alert operators depending on business requirements.

Example policy for an order-creation event:

| Error group | Example | Handling approach |
|---|---|---|
| Transient | Database connection timeout | Bounded retry with backoff |
| Transient requiring long wait | Downstream rate limit | Retry topic or appropriate delay mechanism |
| Unrecoverable | Payload missing `orderId` | Do not retry repeatedly; DLT and alert |
| Widespread configuration error | Wrong Kafka ACL, expired secret | Restore configuration; avoid aggressive retries |
| Ambiguous | HTTP timeout after downstream may have received request | Retry with idempotency key and reconcile outcome |

Do not decide whether to retry based on exception name alone without knowing the real cause. The same `TimeoutException` can happen before a request reaches the server or after the server finishes processing yet the response is lost.

## 3. DefaultErrorHandler for record listeners

In modern Spring Kafka versions, **DefaultErrorHandler** is the standard component for record listener error handling. It replaces older error handlers and supports `BackOff`, exception classification, recoverers, and offset handling.

Basic configuration example:

~~~java
@Configuration
public class KafkaRetryConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler() {
        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(backOff);
    }
}
~~~

Here **FixedBackOff(1_000L, 2L)** represents a 1,000 ms delay between retries and at most two retries after the initial processing attempt. A record can be processed by the listener up to three times in the corresponding attempt sequence: one initial attempt and two retries.

Do not confuse **maxAttempts** in other APIs with **maxRetries** in `FixedBackOff`. Names and counting conventions depend on the API; when configuring, clearly document the actual listener invocation count permitted by the business.

### 3.1 Attaching the handler to the right listener container factory

If using a dedicated factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    factory.setConcurrency(3);

    return factory;
}
~~~

Listener referencing the factory:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-processing-prod",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

If a project has multiple factories, a `DefaultErrorHandler` bean in the application context does not prove every listener uses that bean. Verify which factory the annotation uses, which `CommonErrorHandler` is registered on the factory, and whether auto-configuration or customizers override it.

### 3.2 What does the handler manage?

`DefaultErrorHandler` coordinates with the listener container to:

- Receive the exception of the failed record.
- Track failure counts per record and retry sequence.
- Apply `BackOff` before the listener is invoked again.
- Seek the consumer or retain unprocessed records to redeliver them to the listener on the appropriate cycle.
- Invoke the recoverer after retry attempts are exhausted.
- Coordinate offset commits with `AckMode` and recovery state.

Remember that the handler cannot undo side effects executed before the exception. If the listener writes to a database successfully and then fails on an HTTP call, retrying the entire listener can write to the database again if the code is not idempotent.

## 4. Blocking retry: retrying on the consumer processing thread

With blocking retry, the failed record is reprocessed on the consumer container thread according to `BackOff`. During that time, processing of trailing records in the same partition can be blocked; other partitions on the same consumer can also be affected depending on how the container handles remaining records.

Example of a single partition:

~~~text
Partition orders-2
offset 200  A  -> success
offset 201  B  -> error -> retry -> retry -> recovery
offset 202  C  -> waits for B to be processed or recovered
offset 203  D  -> waits
~~~

This is the trade-off to preserve processing order: trailing records are not allowed to arbitrarily overtake a failing record.

### 4.1 How remaining records are handled after an exception

When a listener throws an exception partway through records from a poll, the handler must ensure the failed record and unfinished records are still processed. In common Spring Kafka configurations:

- The handler may use consumer seeks so the next poll rereads the failed record and the portion needing processing.
- When **seekAfterError=false** is configured in supported versions, the container can retain unprocessed records and resubmit them to the listener on the next cycle instead of physically seeking.
- The container can perform polls to keep the consumer alive while paused or waiting on retries per framework mechanics.

Option example:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler() {
    DefaultErrorHandler handler =
        new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));

    handler.setSeekAfterError(false);
    return handler;
}
~~~

The `seekAfterError` option affects the delivery mechanism inside the container. It does not change idempotency requirements or guarantee that a record executes exactly once.

### 4.2 How does blocking retry affect latency?

Suppose a consumer receives a failing record with 4 retries, each waiting 5 seconds. Wait time alone can reach roughly 20 seconds, excluding listener execution and recovery operations. During that window, other records may not be processed at normal speed.

If a dependency experiences a widespread outage, many consumer threads can simultaneously wait on backoff and retries, causing lag to spike rapidly. Measure total partition hold time and cap retries per SLA.

### 4.3 Poll interval and long backoffs

The Kafka consumer has **max.poll.interval.ms** to limit the time between `poll` calls. If processing logic or backoff blocks for too long without the container polling on time, the consumer can lose partition ownership and trigger a rebalance.

Do not merely set `max.poll.interval.ms` to an enormous value to mask downstream failures. For long delays, consider:

- Using **ContainerPausingBackOffHandler** when supported by your Spring Kafka version and suitable for the case, so the container pauses and polls to maintain consumer membership.
- Using non-blocking retry topics.
- Reducing batch size or per-record processing duration.
- Setting timeouts on downstream calls.
- Monitoring poll gaps, rebalances, heartbeats, and lag.

How backoff executes depends on the version and configured `BackOffHandler`. Never assume every `BackOff` automatically pauses the consumer safely for minutes.

## 5. FixedBackOff, ExponentialBackOff, and jitter

**Backoff** is the wait interval between retries. Retrying immediately while a dependency is failing can generate massive request volume without improving recovery odds.

### 5.1 FixedBackOff

`FixedBackOff` uses a constant delay:

~~~java
new FixedBackOff(2_000L, 3L)
~~~

This policy retries up to three times after the first attempt, waiting 2 seconds between attempts. It is a simple choice for transient errors with short recovery times.

Illustrative timeline:

~~~text
t=0s   attempt 1 -> error
t=2s   retry 1 -> error
t=4s   retry 2 -> error
t=6s   retry 3 -> error
       retries exhausted -> recoverer
~~~

Timestamps illustrate wait times only; listener execution time can make total duration longer.

### 5.2 ExponentialBackOff

`ExponentialBackOff` increases the delay after consecutive failures:

~~~java
ExponentialBackOff backOff =
    new ExponentialBackOff(1_000L, 2.0);

backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

DefaultErrorHandler handler = new DefaultErrorHandler(backOff);
~~~

With a 1-second initial interval and multiplier of 2, delays can progress through 1, 2, 4, and 8 up to a 10-second ceiling. Total elapsed limits must be configured appropriately for the API in use.

Exponential backoff helps when external services need recovery time, yet it still holds the record in retry scope when using blocking retry. Very long delays should be evaluated alongside consumer polling and partition availability.

### 5.3 Jitter

If hundreds of consumers hit an error together and retry on the exact same fixed cadence, they can all hit the recovering dependency simultaneously. This is a **retry storm**.

Jitter adds controlled randomness to delays to reduce synchronized request waves. Jitter support depends on the `BackOff` implementation or retry mechanism chosen by the project. When implementing custom jitter, keep delays within SLA bounds and avoid creating unlimited retries.

### 5.4 Do not multiply retries uncontrollably

A listener can have multiple retry layers:

~~~text
Spring Kafka retry: 3 attempts
HTTP client retry: 3 attempts per call
Database driver retry: 2 attempts per call
~~~

If retry layers nest, actual requests hitting downstream can be far higher than any single layer's configuration suggests. Define which layer owns retries, maximum attempts, overall timeouts, and circuit breakers/backpressure where appropriate.

## 6. Classifying retryable and non-retryable exceptions

Not every error improves upon retry. `DefaultErrorHandler` has an exception classification mechanism to skip backoff for unrecoverable errors.

Example:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        ConsumerRecordRecoverer recoverer) {

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L)
        );

    handler.addNotRetryableExceptions(
        InvalidOrderPayloadException.class,
        UnsupportedEventVersionException.class
    );

    handler.addRetryableExceptions(
        TransientDataAccessException.class
    );

    return handler;
}
~~~

The business classes in the example are application-defined classes. The default list of exceptions treated as fatal/non-retryable in Spring Kafka can vary by version; understand your framework's current policy.

| Error type | Typical cause | Usually appropriate action |
|---|---|---|
| `TransientDataAccessException` | Brief database disruption | Retry with backoff |
| `SocketTimeoutException` | Slow network or lost response | Retry with idempotency |
| HTTP 429 | Downstream throttling load | Backoff per `Retry-After` or defer |
| Payload validation | Record missing required fields | Non-retryable, recovery/DLT |
| `ClassCastException` from schema | Consumer and producer incompatible | Fix contract, avoid infinite retries |
| Authorization failure | Invalid secret or ACL | Fix configuration, trigger broad alert |
| Permanent business conflict | Invalid business state | DLT or record rejection status |

### 6.1 Classifying at the root-cause level

An exception can be wrapped by `ListenerExecutionFailedException` or another framework exception. When classifying, inspect root causes and the classifier mechanics of the handler version in use.

Do not place all `RuntimeException`s into the non-retryable group, as many infrastructure failures are runtime exceptions too. Conversely, retrying every exception can cause poison messages to be retried repeatedly with zero chance of success.

### 6.2 Resetting backoff when exception type changes

In certain Spring Kafka versions, the handler has an option to reset retry state when the exception type changes. This helps when the same record encounters different errors sequentially—for instance, a network timeout first and a parsing error next.

Decide semantics based on business requirements and verify against your version. Whether resetting or preserving retry counts, enforce overall limits and observability so records are not held indefinitely.

## 7. Recovery after retries are exhausted

Retries must have an endpoint. When retries are exhausted or an exception is classified as non-retryable, **ConsumerRecordRecoverer** is invoked to handle the record under the recovery policy.

Recovery can mean:

- Publishing the record to a Dead Letter Topic.
- Saving the error and record details into a durable store.
- Recording a traceable rejection state.
- Throwing an error so the container keeps retaining the record for later handling.

Do not assume a recoverer that merely logs an error and returns is safe for every business case. If the recoverer returns normally, the handler may consider the record handled and allow the offset to advance per policy. For mandatory events, that can lose the opportunity to complete business processing.

### 7.1 DeadLetterPublishingRecoverer

Example:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    handler.addNotRetryableExceptions(
        InvalidOrderPayloadException.class
    );

    return handler;
}
~~~

When a record in topic **orders**, partition 2 exhausts retries, the recoverer per the routing above sends it to **orders.DLT**, partition 2.

Prerequisites:

- The DLT has been created with the target partition present. If preserving source partitions, the DLT needs at least as many partitions.
- The producer publishing to the DLT has serializers compatible with recovered records, including deserialization-error cases.
- The principal has write permission on the DLT.
- Retention, replication, alerts, and replay procedures are in place.
- Failed DLT publishes must surface as recovery failures; never treat the record as handled.

If you want the DLT to have a different partition count than the source, design custom routing; never send to a non-existent partition.

### 7.2 DLT is a quarantine zone

A record entering the DLT does not mean the business action succeeded. It means primary processing failed per policy and the record was moved to an investigation or reprocessing stream.

Store and trace:

- Original topic, partition, and offset.
- Group ID and listener ID.
- Event ID or business key.
- Exception type and appropriate error message.
- Failure timestamp and retry count.
- Schema version or content type when relevant.

Do not log or copy sensitive payloads without controls. The DLT is part of the data system and requires commensurate ACLs, retention, and deletion workflows.

### 7.3 Recovery failure

If the DLT fails or the recoverer throws an exception, the handler must not silently drop the record. Maintain redelivery capability, fire alerts, and check causes such as missing topics, wrong ACLs, broken serializers, insufficient ISR, or broker timeouts.

One scenario to watch is asynchronous DLT publishing by the producer. Calling `send` and getting a future back does not by itself guarantee broker ACK. Configure or check outcomes using `DeadLetterPublishingRecoverer` capabilities for your Spring Kafka version so records are not marked recovered before confirming the publish truly succeeded.

## 8. Offset commits and record retries

A Kafka consumer group stores committed offsets per topic-partition. The offset indicates the next position a consumer will read after a restart or rebalance.

If a record fails processing yet its offset is still committed as successful, the record may be skipped on subsequent reads. If a record succeeds yet the process dies before committing, the record may be reread.

### 8.1 AckMode.RECORD

With a record listener and container-managed offset commits, `AckMode.RECORD` lets the container commit the offset after each record is successfully processed by the listener per container mechanics.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

When the listener throws an exception, the error handler's flow decides retry or recovery. Understand the recoverer's status before considering a record complete.

### 8.2 AckMode.BATCH and record listeners

`AckMode.BATCH` can also be used with a record listener. Within a poll containing multiple records, the container can commit after processing the entire poll batch successfully. When one record fails, previously processed offsets and unprocessed offsets are managed via the error handler and commit policy.

Thus, the term **record listener** does not force the application to use `AckMode.RECORD`. Choose the ack mode based on throughput needs, commit latency, and redelivery tolerance.

### 8.3 Manual acknowledgment

With manual ack, the listener controls when records are acknowledged. Acknowledge only after business effects are guaranteed complete according to the business model.

Conceptual example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void handle(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    orderService.process(record.value());
    acknowledgment.acknowledge();
}
~~~

This example requires the container to be configured with a manual acknowledgment `AckMode`. If `process()` throws an exception, `acknowledge()` is not called.

Do not place `acknowledge()` in a `finally` block or call it before async tasks genuinely finish. If combining manual ack with recovery, determine who is responsible for committing the offset of recovered records.

### 8.4 commitRecovered

`DefaultErrorHandler` has configuration related to committing offsets for recovered records—for example, **setCommitRecovered(true)** when using `AckMode.MANUAL_IMMEDIATE` per API requirements.

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

handler.setCommitRecovered(true);
~~~

Enable this option only when the container ack mode and recovery policy meet the conditions. Do not add it mechanically to every factory. If committing happens when DLT publishing has not actually succeeded, the record can be skipped without a copy in the DLT.

### 8.5 At-least-once and idempotency

Even when retries and commits are implemented properly, a crash can happen between the business effect and the offset commit:

~~~text
Listener processes order 1001
Database commit succeeds
Process stops before offset commit
Consumer restarts
Order 1001 is redelivered
~~~

This is an at-least-once scenario. You need idempotency keys, unique constraints, inbox/deduplication, or side effects designed to be safe on repetition.

Retry counts can never be used to prove a record produced only one side effect.

## 9. Blocking retry and non-blocking retry topics

In addition to `DefaultErrorHandler` retries on the consumer, Spring Kafka supports **non-blocking retry** via retry topics, commonly using `@RetryableTopic` in supported versions.

### 9.1 Blocking retry

~~~text
orders -> listener
         error
         wait backoff on processing thread
         retry record
         succeed or recover
~~~

Characteristics:

- Easier to preserve per-partition record order while a record is retrying.
- Requires no extra retry topics.
- Short backoff fits transient errors.
- A failing record can hold the consumer/partition and cause lag to rise.

### 9.2 Non-blocking retry topics

~~~text
orders -> listener fails
              |
              v
         orders-retry-... -> retry listener
              |
          fails again
              v
         orders-retry-... -> retry listener
              |
          exhausted
              v
         orders-DLT
~~~

The record is moved to a retry topic with a delay mechanism, allowing the main-topic consumer to keep processing. This suits errors requiring long waits or when main-topic throughput cannot be blocked.

However, record B can be processed before record A retrying on another topic, even if A and B share the same key or originate from the same source partition. Therefore, non-blocking retry can alter business processing order.

### 9.3 @RetryableTopic example

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0
    )
)
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void handle(OrderCreated event) {
    orderService.process(event);
}
~~~

This example expresses up to four attempts under the annotation's semantics, including the initial processing attempt, with exponential backoff. Verify topic creation capabilities, topic names, DLT handlers, retry-topic configuration, and your actual version before deploying.

Retry topics are not the default choice for every system. They add topics, consumer groups/endpoints, offsets, and monitoring. They may not fit strict ordering requirements, certain transaction models, or existing recovery workflows.

### 9.4 Selection table

| Criterion | Blocking retry | Non-blocking retry topic |
|---|---|---|
| Short delay | Suitable | May be overly complex |
| Delay of minutes or longer | Requires checking poll/lifecycle | Usually more suitable |
| Preserving per-partition order | Easier to preserve | Can change |
| Main topic speed when a record fails | Can be blocked | Can continue |
| Extra infrastructure | No retry topics needed | Needs retry topics and DLT |
| Operations | Monitor handler and consumer | Monitor both main topic and retry topics |
| Error type | Fast-recovering transient errors | Slow-recovering errors needing deferral |

You can combine a few short blocking retries before moving to a retry topic if supported by the framework and policy. When doing so, calculate total attempts across all layers.

## 10. Distinguishing record listeners and batch listeners

Per-record listener retries are straightforward because the framework knows which record just failed. With a batch listener, a single invocation receives many records, so a generic exception may lack enough information to pinpoint the failing record.

| Aspect | Record listener | Batch listener |
|---|---|---|
| Input | Single record or payload | List/batch of records |
| Failing record | Container knows the record currently being processed | May require `BatchListenerFailedException` to know position |
| Default retry without failed position | Retries the failed record | May retry the entire batch |
| Duplicate side effects | Can repeat the failing record | Can repeat already-succeeded records in the batch |
| Tuning | `DefaultErrorHandler` and `BackOff` | `DefaultErrorHandler`, fallback batch retry, partial failure |

If a batch handler is configured to identify the failed index, retry logic and committing the portion of the batch before the error must be understood separately. Do not use a record listener example to deduce exact batch listener behavior.

## 11. Retrying in listeners with Kafka transactions

When a listener container is configured to run Kafka transactions, error handling differs from non-transactional containers. Exceptions typically roll back the transaction; an **AfterRollbackProcessor**, such as `DefaultAfterRollbackProcessor`, coordinates redelivery or recovery after rollback.

Do not assume `DefaultErrorHandler` is the sole class deciding retries in a transactional listener.

For a consume-transform-produce flow:

1. Consumer reads input record.
2. Listener sends output via a transactional `KafkaTemplate`.
3. An exception occurs.
4. The Kafka transaction rolls back.
5. Transaction outputs are invisible to `read_committed` downstream consumers.
6. Input offsets in the transaction do not commit, so the input can be reprocessed.

Side effects outside Kafka such as database writes, emails, or HTTP calls do not automatically roll back with the Kafka transaction. They still require idempotency or appropriate coordination mechanisms.

When using transactional containers, verify the transaction manager, listener container configuration, `AfterRollbackProcessor`, `BackOff`, recoverer, and DLT in your exact Spring Kafka version.

## 12. Deserialization errors and records never reaching the listener

There is an easily overlooked case: errors occurring **before the listener is invoked**, such as an un-deserializable payload. If using standard Kafka deserializers and deserialization throws an exception during `poll`, the listener never receives the `ConsumerRecord` in the expected form.

Spring Kafka provides **ErrorHandlingDeserializer** to turn deserialization error details into metadata suitable for error handling.

Illustrative configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

The configuration above illustrates only the wrapper and delegates, excluding type mappings, trusted packages, and system-specific event contracts.

If a deserialization error stems from a permanently invalid payload, retrying repeatedly will not magically turn the payload into valid data. Route to appropriate recovery/DLT, store enough metadata for investigation, and ensure the DLT producer has serializers compatible with the raw data.

Do not confuse exceptions inside the listener method with poll/deserialization errors. Log exception class, topic, partition, and offset where the framework safely provides metadata.

## 13. Retries and downstream side effects

Retrying a record can invoke the same business operation multiple times. Safeguards against duplication are needed at side-effect boundaries.

### 13.1 Database idempotency

Example of an event with a unique `eventId`:

~~~java
@Transactional
public void apply(OrderCreated event) {
    if (processedEvents.existsByEventId(event.eventId())) {
        return;
    }

    ordersRepository.insertIfAbsent(
        event.orderId(),
        event.customerId()
    );

    processedEvents.save(
        new ProcessedEvent(event.eventId())
    );
}
~~~

This is a conceptual example. In real deployments, use unique constraints or atomic operations to prevent two concurrent consumers from both passing the `exists` check and writing duplicates. Saving the processed event and business data should live in the same database transaction if atomicity is required.

### 13.2 HTTP idempotency key

If the listener calls a payment or shipping API, a timeout does not prove the server has not executed the request. On retry, send the same business-stable idempotency key so downstream returns the prior result or ignores the duplicate call, if the API supports it.

~~~text
Record eventId: evt-1001
HTTP Idempotency-Key: evt-1001
Retry 1: evt-1001
Retry 2: evt-1001
~~~

Never generate a new UUID on each retry; doing so makes downstream treat every retry as a brand-new command.

### 13.3 Transactional outbox and inbox

For business logic needing database and Kafka synchronization, a **transactional outbox** persists the intent to emit an event within the business transaction. On the consumer side, **inbox/deduplication** detects already-processed records.

Kafka transactions can coordinate Kafka outputs and input offsets, yet do not automatically encompass database or HTTP service side effects. Retries must be designed around that boundary.

## 14. Poison records and partition blocking

A **poison record** is a record on which the listener always fails under the same conditions, such as a bad schema or missing business key. With unlimited retries, the consumer cannot advance past that record.

Example:

~~~text
orders-0 offset 700: valid record
orders-0 offset 701: poison record
orders-0 offset 702: valid record
orders-0 offset 703: valid record
~~~

If record 701 is continuously retried using blocking retry, records 702 and 703 on the same partition typically remain unprocessed. Lag grows even though only a single record is the fault source.

Controlled solution:

1. Classify unrecoverable errors.
2. Retry only within a short enough limit, or skip retries once known to be bad data.
3. Publish the record to a DLT or equivalent durable store.
4. After successful recovery, let the consumer continue processing subsequent records.
5. Investigate, fix data, and replay per runbook.

If the business requires strict ordering and record 702 must not be processed before 701 is fixed, moving 701 to the DLT and continuing could violate invariants. In that case, design partition isolation, processing pauses, or data-repair workflows instead of automatically skipping.

## 15. Observing per-record retries

Retries require metrics and logs at the record, partition, and consumer group levels. A running consumer does not mean business processing is making progress.

| Layer | Key signals |
|---|---|
| Listener | Processing duration, success/error rate, exception class |
| Error handler | Retry attempts, elapsed backoff, recovery attempts, recoverer failures |
| Consumer | Poll gaps, rebalances, commit latency, assignments |
| Partition | Consumer lag, offset progression, age of oldest pending record |
| Downstream | Timeouts, 429/503, connection pool saturation, queue depth |
| DLT | Published record count, publish errors, age, replay status |
| Business | Event ID, duplicate detection, completed side-effect count |

A helpful log when a record fails:

~~~text
listenerId=order-processing
groupId=order-processing-prod
topic=orders
partition=2
offset=701
eventId=evt-1001
exception=TransientDataAccessException
attempt=2
action=retry
~~~

Not every field is necessarily built into the framework out of the box. You can use Kafka headers, `RecordInterceptor`, retry listeners, or application instrumentation depending on version.

### 15.1 RetryListener

`DefaultErrorHandler` can register a `RetryListener` to observe failures and recoveries per your Spring Kafka version's API.

Conceptual example:

~~~java
handler.setRetryListeners(new RetryListener() {

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception ex,
            int deliveryAttempt) {

        log.warn(
            "Retry record topic={} partition={} offset={} attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            deliveryAttempt,
            ex
        );
    }
});
~~~

The example illustrates the observation mechanism; check the exact interface and method signatures matching your project's version. Avoid logging full payloads, especially with sensitive data.

### 15.2 Delivery attempt header

Some Spring Kafka configurations can provide a delivery attempt header to the listener. Header availability and counting depend on the listener container, error handler, and version.

Do not use this header as an idempotency key. A record can be reprocessed in a fresh consumer session with a different attempt counter.

### 15.3 Progress-based alerting

Alerting only on high error rates is insufficient. A partition can be stuck retrying without emitting errors every second. Add alerts for:

- Committed offset not advancing while producers keep writing.
- Lag or record age breaching SLA.
- A single event ID retrying repeatedly.
- DLT publish failures.
- Repeated consumer rebalances.
- Downstream timeouts rising across multiple listeners simultaneously.

Distinguish lag caused by rising producer traffic from lag caused by a consumer retrying one record for too long.

## 16. Incident workflow for continuous retries

When observing a listener retrying continuously or lag failing to drop:

1. Identify the failing group ID, listener ID, topic, partition, and offset.
2. Retrieve the event ID and exception root cause; no need to log the full payload.
3. Determine whether the error is transient, bad data, or a widespread configuration fault.
4. Inspect the effective retry policy: `BackOff`, `maxRetries`, classifier, and recoverer.
5. Correlate consumer polls, rebalances, lag, committed offsets, and assignments.
6. Check the called dependency: database pool, HTTP status, timeouts, rate limits.
7. Check idempotency and which side effects already committed before the exception.
8. If retries are exhausted, verify DLT/recovery actually succeeded.
9. Upon recovery, confirm trailing records process and offsets resume advancing.
10. Document the root cause and refine the retry policy or runbook accordingly.

Do not immediately reset offsets upon seeing a poison record, because that can drop records or replay many records. Snapshot offsets and assess business impact before changing read positions.

### 16.1 When a dependency fails broadly

If many consumers fail together because a database is unavailable, raising retry counts can overwhelm the database the moment it comes back. Consider lowering concurrency, applying longer backoff with jitter, bounding connection pools, or pausing listeners in a controlled manner.

If the error is an authentication or configuration fault, fix the root cause. Retrying immediately on every record rarely helps.

### 16.2 When only a single record fails

If other records succeed while one event ID consistently fails at the same spot, inspect the payload contract and business rules. You may classify it non-retryable and move it to the DLT sooner to reduce partition blocking, provided policy allows subsequent records to continue.

## 17. Testing per-record retries

Tests should run in an integration environment with a Kafka broker and isolated test data. Each test should know the expected event ID, topic, partition, and offset.

### 17.1 Transient error

- Send a valid record.
- Make the downstream fail on the first one or two attempts.
- Configure `FixedBackOff` with a retry count greater than the failure count.
- Verify the listener is re-invoked at the appropriate wait intervals.
- Verify side effects complete only once per idempotency policy.
- Verify the offset advances after success.

### 17.2 Non-retryable error

- Send a record missing a required field.
- Throw an exception classified as non-retryable.
- Verify the handler routes to the recoverer per policy.
- Verify the DLT receives the right record and metadata.
- Verify the next record continues processing if permitted by policy.

### 17.3 Retries exhausted

- Make the dependency always fail.
- Configure a finite `BackOff`.
- Count listener invocations.
- Verify the recoverer is invoked once retries are exhausted.
- Check offsets and subsequent records.
- Verify there are no infinite retries or retry storms.

### 17.4 DLT publish failure

- Make the DLT temporarily unavailable in the test environment.
- Drive the record to the retry-exhausted state.
- Verify the recovery failure is recorded.
- Ensure the record is not silently marked as succeeded.
- Restore the DLT and verify recovery can complete.

### 17.5 Crash between side effect and offset commit

- Let the listener write to the database successfully.
- Stop the process before the offset commits.
- Restart the consumer.
- Verify the record can be redelivered.
- Verify idempotency prevents duplicate side effects.

### 17.6 Ordering and retry topics

- Send events with the same business key in order.
- Make the first event fail and move to a retry topic.
- Verify the possibility that later events are processed before the first event.
- Evaluate business ordering requirements.
- Choose blocking retry or an appropriate coordination mechanism if strict ordering is mandatory.

## 18. Misconceptions to avoid

**"Per-record retry guarantees exactly-once."** No. Retries and redeliveries can re-invoke the same business logic; idempotency or appropriate transactions are required.

**"Once retries run out, Kafka automatically puts the record in the DLT."** Not automatically. You must configure a recoverer or retry-topic/DLT workflow.

**"FixedBackOff with two retries means the listener is invoked twice total."** No. Under the illustrated `FixedBackOff` API, there is one initial attempt plus two retries.

**"Retries always affect only a single record."** Not entirely. Blocking retries can stall partition progress and affect other records on the same consumer.

**"With a long BackOff, the consumer will not rebalance."** Not guaranteed. Check `BackOffHandler`, poll lifecycle, and `max.poll.interval.ms`.

**"Every exception should be retried."** No. Permanent data errors require recovery rather than repeated retries.

**"Publishing to the DLT means business processing succeeded."** No. The DLT is a quarantine area for investigation or replay.

**"An offset commit proves the database write happened."** No. Offsets and external side effects outside Kafka have separate transaction boundaries.

**"Increasing concurrency always reduces lag during retries."** No. Concurrency is bounded by partition counts and downstream capacity; excessive concurrency can trigger more timeouts.

**"Non-blocking retry preserves per-partition record order."** Not by default. Records on a retry topic can finish after newer records on the main topic.

**"Retries in DefaultErrorHandler work the same as retries in a transactional container."** Not completely. Transactional containers typically use rollback and `AfterRollbackProcessor`.

## 19. Design and operations checklist

**Retry policy**

- [ ] Classify transient, permanent, and configuration errors.
- [ ] Bound retry counts and backoff intervals.
- [ ] Set overall timeouts for downstream calls and record processing.
- [ ] Evaluate long backoffs alongside poll intervals and partition availability.
- [ ] Avoid multi-layer retries causing request explosions.

**Spring Kafka**

- [ ] Record listener uses the intended container factory.
- [ ] `DefaultErrorHandler` is registered on the actual factory.
- [ ] `BackOff` and exception classification match business rules.
- [ ] `AckMode`, offset commits, and recovered-record semantics are clearly understood.
- [ ] Transactional listeners use the right rollback/recovery model.

**Recovery and data**

- [ ] Recoverer or DLT configured for exhausted/non-retryable records.
- [ ] DLT has appropriate partitions, retention, replication, and ACLs.
- [ ] Recovery publish failures are monitored.
- [ ] Record metadata and event IDs are preserved for investigation.
- [ ] Side effects use idempotency keys, unique constraints, or deduplication.

**Observability**

- [ ] Monitor retry attempts, recovery, listener errors, and processing latency.
- [ ] Monitor lag, offset progression, rebalances, and poll intervals.
- [ ] Alerts configured for poison records and DLT publish failures.
- [ ] Runbooks exist for DLT replay and duplicate reconciliation.
- [ ] Tested transient failures, exhausted retries, crashes, and ordering in appropriate environments.

Per-record retry is a mechanism for controlling recoverable errors at the consumer boundary. With `DefaultErrorHandler`, Spring Kafka can retry failing records per `BackOff`, classify exceptions, and invoke a recoverer when processing cannot continue. Actual reliability depends on offset commit timing, partition hold duration, DLT publish reliability, and side-effect idempotency. A sound retry policy helps the system recover when transient faults clear and terminates cleanly when errors cannot self-heal.

