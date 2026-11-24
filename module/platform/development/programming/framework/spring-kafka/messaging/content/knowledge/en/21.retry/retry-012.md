# Choosing Between Retry and Dead Letter

## Lesson Objectives

In the **Retry** chapter, this lesson guides how to choose the handling approach when a Kafka message fails in a listener: retry, route to a dead-letter topic (DLT), or combine both. Decisions should be based on root cause, recoverability, wait durations, ordering requirements, and impact on the consumer group.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing. Retry and DLT are two pillars of an error-handling strategy designed to keep messaging streams reliable when downstream systems fail or data is invalid.

After this lesson, learners can:

- Distinguish transient errors, data errors, and configuration/system errors.
- Decide when to retry and when to route straight to a DLT.
- Design bounded retries, backoff, and exception classification.
- Configure `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`.
- Understand blocking retry and non-blocking retry via retry topics.
- Evaluate impacts on ordering, partitions, consumer lag, and throughput.
- Design DLT consumers, replay workflows, and idempotency.
- Test retry counts, DLT publishing, and failure scenarios.

## 1. What Problems Do Retry and Dead Letter Solve?

Kafka stores records durably in topics. When a consumer receives a record, the listener either processes it successfully or throws an exception. If processing fails, the application must decide what happens next.

Two primary mechanisms:

- **Retry:** re-attempt processing the same record after a wait interval or on a retry schedule.
- **Dead letter:** move records that cannot be processed successfully to a separate topic for investigation, data repair, or later replay.

They are not mutually exclusive. A common strategy is retrying a bounded number of times with backoff, then routing failing records to a DLT.

~~~mermaid
flowchart TD
    A["Consumer receives record"] --> B["Listener processes"]
    B --> C{"Succeeded?"}
    C -->|Yes| D["Commit offset per AckMode"]
    C -->|No| E{"Recoverable error?"}
    E -->|Yes| F["Bounded retry"]
    F --> B
    E -->|No| G["Dead-letter topic"]
    F --> H{"Retries exhausted?"}
    H -->|No| B
    H -->|Yes| G
    G --> I["Investigate / fix / replay"]
~~~

The goal is not to retry every error. Retrying only helps when a later attempt has a chance of succeeding. For permanently malformed data, repeating the same operation usually just slows down the partition and adds load.

## 2. Classify Errors Before Choosing a Policy

Before configuring Spring Kafka, classify errors by recoverability.

| Error group | Examples | Typically appropriate action |
|---|---|---|
| Transient errors | Short timeout, HTTP 503, temporary database disconnect | Bounded retry with backoff |
| Rate-limit errors | HTTP 429, downstream asks to wait | Retry after an appropriate delay or route to a retry topic |
| Data errors (poison messages) | Missing required field, invalid enum, violated business rule | Immediate DLT, or very few retries if missing data might be supplemented |
| Serialization/deserialization errors | Malformed bytes, incompatible schema | Quarantine/DLT after configuring proper error handling |
| Prolonged config/infra errors | Wrong credentials, ACL, missing topic, wrong endpoint | Stop or alert and fix configuration; blind retries do not fix the root cause |
| Time-dependent business errors | Account not yet activated, waiting on another event | Time-bounded retry or retry topic aligned with business timing |

Examples:

- Database briefly disconnects for a few seconds: retry can succeed.
- Event missing `orderId`: the same payload will keep missing `orderId`, so retrying does not help.
- API returns 429 with `Retry-After`: respect the downstream wait duration.
- Revoked credentials: continuous retries create load and log noise while secrets/permissions must be fixed.

Exception classification must reflect the actual root cause. Do not rely solely on exception names if the same exception type can represent both transient and permanent failures.

## 3. When Should You Retry?

Retry fits when the error can resolve on its own without altering the message or code.

Examples:

- Brief network timeouts.
- Database connection resets.
- Downstream service deploying or restarting.
- Short-lived HTTP 503 responses.
- Rate limits with a known wait window.
- Database deadlocks where the transaction can be safely re-executed.

A good retry policy specifies:

1. Which exceptions are retried.
2. Maximum retry attempts.
3. Wait interval between attempts.
4. Maximum total time allocated for retries.
5. Action once retries are exhausted.
6. How repeated execution avoids duplicate side effects.

Retries must never be infinite. Infinite retries can stall a partition for a long time, driving up consumer lag and blocking trailing records in the partition.

## 4. When Should You Route Straight to a DLT?

A DLT fits when a record cannot succeed with its current data or requires human or external system intervention.

Common scenarios:

- Invalid payload or missing required data.
- Unsupported enum values or business codes.
- Incompatible schema that fails deserialization.
- Business rules reject the record.
- Retries were exhausted yet the error persists.
- Need to isolate the record so the main stream keeps moving.

Routing to a DLT does not mean deleting the error. The DLT preserves failed records for investigation and deciding next steps.

Do not send every error straight to a DLT immediately. If a downstream service is only disconnected for 2 seconds, the DLT would accumulate many records that could have succeeded once the service recovered, creating unnecessary replay work.

## 5. Decision Table: Retry vs. DLT

| Question | If yes | If no |
|---|---|---|
| Can the error resolve on its own shortly? | Bounded retry | Consider DLT or fixing configuration |
| Is the payload valid and complete? | Continue evaluating retry | DLT or reject per business rules |
| Does the downstream specify a retry delay? | Honor the wait duration if possible | Use designed backoff |
| Is the operation idempotent? | Safer to retry | Add idempotency first |
| Will waiting stall the partition? | Blocking retry may fit | Use retry topics or quarantine |
| Have retry count or time limits been exceeded? | Route to DLT | Continue per policy |

A practical rule of thumb:

- Short transient errors: bounded retry.
- Unfixable data errors: immediate DLT.
- Transient errors needing long waits: consider retry topics.
- Widespread configuration errors: alert, fix root cause, and control consumers instead of retrying endlessly.
- Exhausted retries: move to DLT and emit an operational signal to handle it.

## 6. Blocking Retry in Spring Kafka

With blocking retry, the consumer keeps handling the failed record in its processing thread and retries per backoff. This is usually configured via `DefaultErrorHandler`.

Example creating a handler with two retries spaced one second apart:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(backOff);
}
~~~

In this example, `FixedBackOff(1_000L, 2L)` means a 1,000 ms wait interval and up to two retries after the initial attempt. The listener can be called up to three times in total: once initially plus two retries.

Attaching the handler to the container factory:

~~~java
@Bean(name = "ordersKafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);

    return factory;
}
~~~

Listeners using this factory share the configured common error handler. If groups of listeners need different retry policies, create separate factories so each group gets an appropriate policy.

### 6.1. How Does Blocking Retry Affect Partitions?

Kafka guarantees order within a partition. When a record at the head of the stream fails and is retried in blocking mode, trailing records in that partition may have to wait.

Example:

~~~text
Partition 0:
offset 10 -> OrderCreated (failed, retrying)
offset 11 -> PaymentCaptured
offset 12 -> OrderCompleted
~~~

Until offset 10 is processed or recovered, the listener may hold off on processing subsequent records per error handler and container semantics.

This is the trade-off:

- Keeps processing flowing in partition order.
- Accepts that a failing record can delay trailing records.

If events do not depend on each other and can be processed independently, retry topics let the main stream keep advancing. However, moving to retry topics can alter original processing order.

## 7. Backoff: How Long to Wait Between Retries?

Backoff prevents relentless retries while a downstream service is experiencing trouble.

### 7.1. Fixed Backoff

Each retry waits the same fixed duration:

~~~java
FixedBackOff backOff = new FixedBackOff(1_000L, 3L);
~~~

Best for transient errors with short, predictable recovery times. The setting above defines three retries spaced one second apart.

### 7.2. Exponential Backoff

Wait durations grow progressively with each retry, e.g., 1 second, 2 seconds, 4 seconds, 8 seconds.

~~~java
ExponentialBackOff backOff =
    new ExponentialBackOff(1_000L, 2.0);

backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(backOff);
~~~

In this example, waiting starts at 1 second, doubles by a multiplier of 2, caps each wait at 10 seconds, and bounds total backoff time per configuration.

Exponential backoff fits when downstream systems need progressively more time to recover. When multiple consumers retry concurrently, consider jitter if supported by the retry layer so all consumers do not hit the downstream simultaneously.

### 7.3. Backoff Does Not Replace Retry Limits

Configuring a wait interval alone is not enough. You must cap maximum attempt counts or total retry duration. Otherwise, a failing record can stall a partition indefinitely.

Base limits on:

- Business stream SLOs.
- Expected downstream recovery time.
- `max.poll.interval.ms` and container processing time.
- Backlog depth in the partition.
- Capacity of the dependent service.

## 8. Classifying Exceptions in DefaultErrorHandler

Not every exception should be retried. You can mark exceptions as non-retryable:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    DefaultErrorHandler handler = new DefaultErrorHandler(
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class,
        UnsupportedOperationException.class
    );

    return handler;
}
~~~

For instance, an `IllegalArgumentException` caused by a bad payload can go straight to the recoverer after the initial attempt. Remaining exceptions use the handler's default retry policy unless classified further.

You can add retryable exceptions with `addRetryableExceptions(...)` when adjusting default classifications.

Classify exceptions carefully:

- Do not mark a base exception as non-retryable if it might wrap a transient network error.
- Do not retry validation errors that cannot change by waiting.
- Separate business exceptions from infrastructure exceptions.
- Log the root cause, not just a wrapper exception.
- Write tests confirming each error type executes the intended number of attempts.

## 9. Combining Retries with DeadLetterPublishingRecoverer

Once retries hit their limit, failed records can be published to a DLT using `DeadLetterPublishingRecoverer`.

Example:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(kafkaTemplate);
}

@Bean
public DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

With the default resolver, Spring Kafka typically appends `.DLT` to the source topic name and preserves the source partition. For example, a record from `commerce.order.created` on partition 2 is sent to `commerce.order.created.DLT` on partition 2.

Because partitions are preserved, the DLT usually needs at least as many partitions as the source topic. If routing to different partitions or a shared DLT, configure a custom destination resolver and verify distribution behavior.

The `KafkaTemplate` used for DLT publishing must be able to serialize the failed record's key/value. For deserialization errors, records may carry raw bytes and exception details; producer/recoverer configuration must support both normal payloads and object types if the app handles multiple record types.

### 9.1. Retry-Then-DLT Flow Diagram

~~~mermaid
flowchart TD
    A["Listener receives record"] --> B{"Processing succeeded?"}
    B -->|Yes| C["Commit offset"]
    B -->|No| D["DefaultErrorHandler"]
    D --> E{"Exception retryable?"}
    E -->|Yes| F["Backoff and retry"]
    F --> A
    E -->|No| G["Recoverer"]
    F --> H{"Retries exhausted?"}
    H -->|No| A
    H -->|Yes| G
    G --> I["DeadLetterPublishingRecoverer"]
    I --> J["orders.DLT"]
    J --> K["Investigate / fix / replay"]
~~~

### 9.2. DLT Publishing Can Also Fail

Never assume DLT publishing always succeeds. Possible failures include:

- The DLT does not exist and auto-create is disabled on the broker.
- The producer lacks write ACLs for the DLT.
- Serializers cannot serialize the key/value.
- The DLT lacks a partition matching the source partition.
- The broker or network is down.
- Publish times out or the send result fails.

Monitor recoverer errors, inspect publish outcomes per your API/version, and define behavior when the recoverer fails. If a record was not safely published, never mark it as handled and silently drop it.

## 10. What Should a DLT Record Contain?

Spring Kafka's `DeadLetterPublishingRecoverer` adds headers that help trace the original record and exception. Common metadata includes:

- Original topic.
- Original partition.
- Original offset.
- Original timestamp.
- Exception class.
- Exception message.
- Stack trace if configured.

In code, you can read DLT headers via `KafkaHeaders` constants, such as `DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, `DLT_ORIGINAL_OFFSET`, and `DLT_EXCEPTION_MESSAGE`. Verify exact names and support against your Spring Kafka version.

Do not merely log the error message and discard the payload. The DLT needs enough context for operators to identify which record failed, why, where, and how to replay it.

## 11. Handling Records in the DLT

A DLT should have a dedicated consumer or operational process. Never build a listener that blindly reads from the DLT and republishes straight back to the main topic in a loop, as that can create an infinite error cycle.

Example DLT inspection listener:

~~~java
@KafkaListener(
    topics = "commerce.order.created.DLT",
    groupId = "order-dlt-inspector"
)
public void inspect(ConsumerRecord<String, OrderCreated> record) {
    Header reasonHeader = record.headers().lastHeader(
        KafkaHeaders.DLT_EXCEPTION_MESSAGE
    );
    String reason = reasonHeader == null
        ? "unknown"
        : new String(reasonHeader.value(), StandardCharsets.UTF_8);

    log.error(
        "DLT record: topic={}, partition={}, offset={}, key={}, reason={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key(),
        reason
    );

    dltAuditService.store(record);
}
~~~

This example illustrates recording failed records. In real applications, handle nullable headers and decode byte values safely. If a record failed deserialization into `OrderCreated`, the DLT consumer must use a deserializer capable of reading raw bytes or the corresponding error payload.

A DLT consumer can:

- Store the record in an error management system.
- Alert the operations team.
- Tag error categories.
- Wait for data or schema fixes.
- Perform controlled replay once the root cause is confirmed fixed.
- Mark permanently skipped per business decision.

## 12. Replaying Records from a DLT

Replaying means re-introducing a quarantined record back into the processing stream once the underlying cause is fixed.

A controlled workflow should:

1. Identify the original record via topic/partition/offset headers.
2. Investigate the exception and payload.
3. Fix the data, schema, configuration, or faulty dependency.
4. Confirm the record is still valid under current business rules.
5. Choose the appropriate target topic and key.
6. Republish the record or corrected payload.
7. Record who performed the replay, when, and the outcome.
8. Monitor the consumer to confirm successful processing.

Never arbitrarily reset offsets on the main topic to replay a single record. Resetting offsets can cause the consumer to re-read many other records, producing duplicates and disrupting consumer group progress.

When replaying, preserve the original event ID or attach replay metadata so idempotency checks recognize previously processed events.

## 13. Retry Topics and Non-Blocking Retry

Blocking retry holds the record in the consumer's processing thread while waiting. When long waits are required, retry topics move records onto delay topics with appropriate wait intervals.

Spring Kafka supports non-blocking retries via `@RetryableTopic` in versions that include this feature.

Illustrative example:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 10_000
    ),
    dltTopicSuffix = ".DLT"
)
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.createInvoice(event);
}
~~~

Spring Kafka creates retry topics and a DLT per configuration. `attempts` expresses the maximum number of attempts before sending to the DLT and normally includes the initial delivery. Confirm exact semantics for your dependency version, especially when upgrading Spring Kafka.

Non-blocking retry fits when:

- Retry wait intervals exceed reasonable blocking durations.
- You do not want a failing record holding the main stream while waiting.
- Subsequent events can continue processing independently.
- Business rules tolerate ordering shifts caused by records traveling through retry topics.

Note that non-blocking retry has Spring Kafka version constraints; notably, it does not support batch listeners and cannot be combined with container transactions in setups documented by Spring Kafka. Check documentation for your exact version before adopting it.

### 13.1. How Blocking Retry and Retry Topics Differ

| Criterion | Blocking retry | Non-blocking retry topic |
|---|---|---|
| Retry method | Consumer retries the record in its processing thread | Publishes record to a retry topic |
| Source partition impact | Can force trailing records to wait | Main stream can continue |
| Long delays | Can hold consumer/partition for too long | Better suited for long wait schedules |
| Ordering | Easier to preserve partition order | Can alter order |
| Infrastructure | Error handler and backoff | Requires retry topics, DLT, and corresponding consumers |
| Operations | Centralized in the listener container | Requires monitoring more topics |
| Best suited for | Short retries, transient errors | Long-wait retries and independent events |

## 14. Choosing Retry Durations by Business Characteristics

Not every failure needs the same backoff.

| Error type | Recommended policy |
|---|---|
| Short database timeout | Few retries with increasing backoff |
| HTTP 503 | Bounded retries, respecting Retry-After if present |
| HTTP 429 | Wait per rate limit or use a retry topic |
| Validation error | Immediate DLT |
| Incompatible schema | Quarantine/DLT and schema alert |
| Account not yet ready | Retry topic with business-aligned delay |
| Wrong credentials | Stop/alert and fix config; avoid blind retries |
| Retries exhausted while dependency still down | DLT or controlled circuit breaker / listener pause per requirements |

Total retry duration must fit within or remain smaller than the event processing SLA. If an order must be processed within 30 seconds, a 24-hour retry schedule does not satisfy business requirements.

## 15. Idempotency: Essential for Safe Retries

Retries can cause a listener to execute the same business operation multiple times. Kafka consumers can also redeliver a record if processing succeeded before the offset committed, or after a rebalance.

Example invoice-creation listener:

~~~java
public void listen(OrderCreated event) {
    invoiceService.create(event);
}
~~~

If the initial attempt created an invoice before the consumer committed the offset, the event is redelivered next time and could create a second invoice.

Idempotent design can rely on event IDs and unique constraints:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within the same database transaction:

1. Attempt to insert the event ID into `processed_event`.
2. If the event ID already exists, skip re-applying side effects.
3. If the insert succeeds, execute the business logic.
4. Commit the processed marker and business state changes together.

Idempotency also matters when replaying from a DLT. Never rely on "the record will only be processed once" to protect external side effects.

## 16. Retries and Business Ordering

Kafka guarantees order only within each partition. Retries can affect how related events are processed.

With blocking retry, a failing record holds the partition stream during retries. This helps when later events depend on earlier ones.

With retry topics, a failing record leaves the main topic and may be processed after newer records. Example:

~~~text
Main topic:
OrderCreated(order-01) -> retry topic
PaymentCaptured(order-01) -> processed immediately
OrderCompleted(order-01) -> processed immediately
~~~

If business logic requires `OrderCreated` to complete before `PaymentCaptured`, non-blocking retry can invert business order.

Options:

- Use blocking retry when partition progression must be preserved.
- Use stable keys so events for the same entity share a partition.
- Build a state machine that rejects or defers out-of-order events.
- Include version/sequence numbers in events to detect late arrivals.
- Pick retry topics only when business rules allow out-of-order processing.

## 17. Retries, Consumer Lag, and Throughput

Retries consume resources and reduce capacity for processing new records.

Potential impacts:

- Consumer threads spend time on failing records.
- Partitions stall during blocking retries.
- Consumer lag grows.
- Downstreams keep receiving calls while overloaded.
- Retry topics increase topic counts, partitions, broker I/O, and metrics to monitor.
- DLTs introduce storage, investigation, and replay processes.

If a downstream suffers a widespread outage, per-record retries can trigger a retry storm. You may need a circuit breaker, controlled listener pausing/stopping, or rate limiting to avoid hammering the struggling downstream further.

Do not measure only total succeeded records. Track retry counts, DLT rate, consumer lag, processing time, recoverer publish latency, and age of the oldest record.

## 18. Handling Deserialization Errors

Deserialization errors happen before the listener receives a Java payload. For example, a producer sends malformed JSON or a consumer uses an incompatible schema.

Spring Kafka provides `ErrorHandlingDeserializer` to turn deserialization failures into structured info that the error handler can handle.

Configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
~~~

When deserialization fails, configure the error handler and DLT publisher to work with raw bytes and exception headers. Do not assume a DLT consumer can always deserialize failed records into normal event classes.

## 19. Testing Retries and DLTs

Tests must verify observable behavior, not merely check that an exception was logged.

Scenarios to cover:

| Test case | Expected verification |
|---|---|
| Listener fails first, succeeds next | Retries exact count and record is processed |
| Continuous retryable error | Stops at limit and moves to DLT |
| Non-retryable error | Skips unnecessary retries |
| DLT publish succeeds | Record appears in DLT with original metadata |
| DLT publish fails | Recoverer surfaces failure and record is not falsely marked succeeded |
| Deserialization error | Error handler receives error and raw record is quarantined |
| DLT replay | Record is processed after root cause is fixed |
| Duplicate delivery | Side effects are not duplicated thanks to idempotency |
| Retry topic | Record delivers on schedule and DLT receives exhausted attempts |
| Ordering | Verify related events are not processed out of order |

Example stubbing a service in an integration test for two failures followed by success:

~~~java
doThrow(new TransientDataAccessResourceException("Temporary failure"))
    .doThrow(new TransientDataAccessResourceException("Temporary failure"))
    .doNothing()
    .when(billingService)
    .createInvoice(event);
~~~

After publishing the event to the test topic, wait for the listener to process it and verify `billingService.createInvoice(event)` was called three times. The test must run the real listener container with `DefaultErrorHandler`; calling the listener method directly bypasses container retry mechanics. If multiple events run concurrently, verify invocation counts per event ID.

For DLT tests, send a failing record and consume from the DLT topic to verify:

- Key/value or raw bytes are preserved per configuration.
- Original topic, partition, and offset headers are present.
- Exception headers carry an appropriate reason.
- The record moves to the DLT only after the exact retry count.
- The main consumer group continues processing subsequent records per policy.

## 20. Operating a DLT and Handling Procedures

A DLT needs an owner, retention policy, and handling procedure. Otherwise, it becomes an unmonitored graveyard for failed records.

Define:

- Who gets alerted when DLT volume rises.
- How long the DLT retains records.
- Whether payloads contain sensitive data.
- Who is authorized to read/replay the DLT.
- How payloads or schemas are repaired.
- How duplicate replays are prevented.
- How replay actions are audited.
- When a record may be marked permanently skipped.

The DLT also needs adequate resources and access controls. Provision topics, partitions, retention, and ACLs per environment policies. Do not depend on auto-created topics in production when operational policy requires pre-managed topics.

## 21. Checklist for Choosing Retry vs. DLT

- [ ] Classified errors as transient, permanent, validation, or configuration?
- [ ] Retrying only recoverable exceptions?
- [ ] Retries have maximum attempt counts and total duration caps?
- [ ] Backoff matches SLAs and downstream capacity?
- [ ] Guarded against retry storms during dependency outages?
- [ ] Listener is idempotent before enabling retries?
- [ ] Assessed whether blocking retry will stall partitions?
- [ ] Evaluated whether retry topics alter business ordering?
- [ ] DLT topic exists with sufficient partitions?
- [ ] Producer publishing to DLT can serialize keys/values/raw bytes?
- [ ] DLT headers suffice to trace the original record?
- [ ] DLT consumer handles undeserializable data?
- [ ] Replays are controlled and preserve event IDs?
- [ ] Alerts exist for rising retry rates, DLT rates, or lag?
- [ ] Tested successful retries, exhausted retries, DLT publish failures, and replays?

## Conclusion

Retry fits transient errors that can heal on their own; DLT fits invalid data, errors that retrying cannot resolve, or records that exceed retry limits. A common strategy is classifying exceptions, retrying bounded times with backoff, and routing failed records to a DLT for investigation and controlled replay.

Blocking retry keeps the partition stream intact while handling a failing record, though trailing records may wait. Retry topics fit long delays and independent events, yet can shift order and carry constraints around listener types and transactions. Whichever approach you choose, design idempotency, verify DLT publishing, monitor consumer lag, and test the entire failure path so Kafka streams run reliably.
