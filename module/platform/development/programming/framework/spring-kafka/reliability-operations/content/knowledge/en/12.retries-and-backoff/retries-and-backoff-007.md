# Delivery Attempts Header in Spring Kafka

When a Kafka listener fails to process a record, Spring Kafka can redeliver that same record according to the listener container's retry policy. In operations, a very common question is: "Is this record being processed for the first time, or has it already failed multiple times?". The **delivery attempts header** helps answer that question by attaching the record's delivery count to a header that the listener can read.

In Spring Kafka, the header name used for this mechanism is `KafkaHeaders.DELIVERY_ATTEMPT`. The delivery count starts at **1** for the first processing attempt and increments when the record is redelivered through the container/error handler's supported mechanism. The header serves retry diagnostics, logging, and observability. It is not a confirmation that an offset has been committed, not the producer's send attempt count, and does not guarantee that the entire retry history is preserved permanently across restarts.

This lesson explains how to enable the header, read its value inside a listener, accurately understand its counting scope, integrate it with `DefaultErrorHandler` and retry topics, and apply it to monitoring and incident response.

## 1. Distinguishing delivery attempts from other attempt types

An event can be retried at multiple layers. If counters are mixed together, dashboards and runbooks will draw wrong conclusions.

| Concept | What is being counted | Example |
|---|---|---|
| Producer retry | Producer client retrying a request to the broker | Request times out and is resent |
| Record delivery attempt | Listener container delivering a record to the listener for processing | Listener receives offset 42 a 1st, 2nd, 3rd time |
| Retry-topic attempt | An event moving across retry topics under a non-blocking policy | Event moves from main topic to retry topic |
| HTTP client retry | Client retrying a downstream API call | One Kafka processing run calls HTTP three times |
| Business retry | Business workflow re-executed at the application level | Payment request replayed after reconciliation |

For example, the listener receives a record on delivery attempt 2, yet during each processing attempt the HTTP service may try calling an API three times. Total HTTP requests can reach six while the Kafka delivery attempt is still just 2.

The delivery attempts header tells you **the delivery count within the context of the container and retry mechanism in use**. Do not use it as a global counter spanning producers, DLTs, replays, and all instances.

## 2. How does the delivery attempts header work?

When the container is configured to attach delivery attempt information to records and the error handler supports tracking deliveries, Spring Kafka adds the corresponding header before supplying the record to the listener.

For a record with a transient error, the processing flow can look like this:

~~~text
Kafka poll receives record at offset 42
                 |
                 v
       Listener, attempt = 1
                 |
         Exception occurs
                 |
                 v
        DefaultErrorHandler
           waits backoff
                 |
                 v
       Listener, attempt = 2
                 |
         Exception occurs
                 |
                 v
           Waits backoff
                 |
                 v
       Listener, attempt = 3
                 |
        Processing succeeds
                 |
                 v
    Container acknowledges offset
~~~

The header is added so the listener is aware of its redelivery state. The exact retry path depends on the error handler, seek/retain settings, transactions, and Spring Kafka version.

### 2.1. The first attempt is 1, not 0

Suppose the configuration allows two retries after the initial processing attempt:

| Listener invocation | Attempt value | Hypothetical outcome |
|---:|---:|---|
| 1 | 1 | Timeout |
| 2 | 2 | Timeout |
| 3 | 3 | Success or retries exhausted |

Therefore, **delivery attempt = 3 does not mean it has been retried three times**. It typically corresponds to the third delivery, meaning two previous processing attempts failed within that retry sequence.

If a record fails immediately with an exception classified as non-retryable, the recoverer can be invoked after attempt 1. Do not assume that a record entering the DLT must always have a high attempt number.

### 2.2. The header does not alter business payload

A Kafka record consists of key, value, timestamp, offset, partition, and headers. The delivery attempts header sits in the metadata portion of the record seen by the listener; it does not modify the business payload.

The listener can use the header for logging or assessing severity when a failure persists. However, the final decision to retry or recover still belongs to the policy of the error handler or retry-topic infrastructure. Do not manually reset offsets or commit solely because you see a high attempt number.

## 3. Prerequisites to enable the delivery attempts header

In Spring Kafka versions that support this feature, the container has a `deliveryAttemptHeader` property. It can be enabled via `ContainerProperties.setDeliveryAttemptHeader(true)`.

The error handler must also be capable of providing delivery counts, typically via the `DeliveryAttemptAware` contract. Common handlers like `DefaultErrorHandler` support this mechanism. For transactional flows, `DefaultAfterRollbackProcessor` in compatible versions can also track delivery attempts.

Practical prerequisites:

1. The listener is created from a container with the delivery attempt header enabled.
2. The error handler or after-rollback processor in use supports delivery attempts.
3. The listener receives records via the container mechanism managed by Spring Kafka.
4. Code reads the right header and handles the case where the header is absent.

If you simply create a raw Kafka consumer client and call `poll()` yourself, there is no reason to expect Spring Kafka to attach this header automatically. This is a listener-container-level feature.

### 3.1. Configuring on the listener container factory

A Java configuration example for a record listener:

~~~java
@Configuration
public class OrderListenerConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        factory.getContainerProperties()
                .setDeliveryAttemptHeader(true);
        return factory;
    }

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }
}
~~~

The snippet illustrates how to wire a listener factory with an error handler. In a real application, imports, serializers, generic types, and the DLT topic must be configured consistently. Verify the corresponding API for your project's Spring Kafka version.

Here, `FixedBackOff(1_000L, 2L)` allows two retries with a one-second wait after the initial processing attempt. If the listener continues to fail, the recoverer is invoked according to the error-handling policy.

### 3.2. Enabling only on the right factory

An application can have multiple listener factories. For example, the orders listener uses `ordersListenerFactory`, while an audit listener uses a different factory. Enabling `deliveryAttemptHeader` on the orders factory does not mean all listeners will receive the header.

~~~java
@KafkaListener(
        id = "ordersConsumer",
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "ordersListenerFactory")
public void consume(OrderEvent event) {
    // Order processing logic.
}
~~~

If a listener does not use the expected factory, the header configuration will not apply. When investigating a missing header, identify the exact container factory used by the annotation.

### 3.3. Configuring when creating a container directly

For a container created in Java instead of `@KafkaListener`:

~~~java
ContainerProperties properties =
        new ContainerProperties("orders.events");
properties.setGroupId("billing");
properties.setDeliveryAttemptHeader(true);

var container = new KafkaMessageListenerContainer<>(
        consumerFactory, properties);
~~~

This example only shows where to set the property. To have a working listener, the application still needs to attach a message listener and other required components before starting the container.

## 4. Reading the header with @Header in a listener

For annotation-driven listeners, you can instruct Spring Kafka to pass the header value into a Java parameter:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "ordersListenerFactory")
public void consume(
        OrderEvent event,
        @Header(
                name = KafkaHeaders.DELIVERY_ATTEMPT,
                required = false)
        Integer attempt) {

    int currentAttempt = attempt == null ? 1 : attempt;

    log.info(
            "Processing order event, attempt={}",
            currentAttempt);

    orderService.processIdempotently(event);
}
~~~

In Spring Kafka versions supporting argument conversion, `@Header(KafkaHeaders.DELIVERY_ATTEMPT) int` can receive the integer value converted from the header. Using `required = false` with `Integer` keeps the listener compatible with environments where the header is not enabled or record types lacking this header.

In the example, the default value `1` is an **application fallback convention** when the header is absent. It does not prove the record is truly being delivered for the first time. If diagnostic accuracy is needed, log a "no header" state instead of coercing every missing case into attempt 1:

~~~java
String attemptLabel =
        attempt == null ? "unknown" : attempt.toString();
~~~

Do not make a listener fail merely because a monitoring header is missing. If the header is required data under an internal contract, strictly verify versions and configuration before making it a required parameter.

## 5. Reading the header from ConsumerRecord

When a listener receives `ConsumerRecord`, it can access Kafka headers directly. The delivery attempt value of this mechanism is represented as a 4-byte integer.

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "ordersListenerFactory")
public void consume(
        ConsumerRecord<String, OrderEvent> record) {

    Header header = record.headers()
            .lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);

    Integer attempt = null;
    if (header != null
            && header.value() != null
            && header.value().length == Integer.BYTES) {
        attempt = ByteBuffer.wrap(header.value()).getInt();
    }

    log.info(
            "Received topic={}, partition={}, offset={}, attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            attempt == null ? "unknown" : attempt);

    orderService.processIdempotently(record.value());
}
~~~

`ByteBuffer` uses big-endian by default, matching the 4-byte integer encoding of this header. Examples should use `KafkaHeaders.DELIVERY_ATTEMPT` directly rather than typing the header name string manually to avoid typos.

### 5.1. Why check whether the header exists?

The header may be absent when:

- The container does not have `deliveryAttemptHeader` enabled.
- The listener uses a different factory than the configured one.
- The error handler in use does not provide delivery attempts under the corresponding contract.
- The record arrives via another path where the Spring Kafka container did not attach the header.
- The system was recently upgraded or redeployed and configurations are inconsistent.

Calling `ByteBuffer.wrap(header.value())` when `header` is `null` will cause the listener to throw a new error purely due to observability logic. Checking for `null` and a 4-byte length is a safe practice when reading raw headers directly.

### 5.2. Do not decode every header this way

Kafka Headers are sets of key/byte-array pairs. Each header can use a different encoding. There is no universal rule that every attempt header in every library is 4 bytes, or that every number is big-endian.

For instance, producer-created headers, retry-topic headers, and middleware headers may use different formats. Only apply decoding rules after confirming the contract of the exact header and library version.

## 6. Combining with DefaultErrorHandler

`DefaultErrorHandler` is used by Spring Kafka to decide how failed records are retried. The delivery attempt provides a signal indicating where the current processing run stands within the handler-managed retry sequence.

Example:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> template) {

    var recoverer =
            new DeadLetterPublishingRecoverer(template);

    var backOff = new FixedBackOff(2_000L, 3L);

    var handler = new DefaultErrorHandler(
            recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderEventException.class);

    return handler;
}
~~~

With a retryable exception occurring consistently, the listener can be invoked initially plus up to three retries. Delivery attempt values across those invocations are typically 1, 2, 3, and 4 within that sequence. If the exception is non-retryable, the error handler can route straight to recovery on the first failure.

Do not add `if (attempt >= 4) ...` logic inside the listener to replace the handler's retry policy. Maximum thresholds should be managed in one unified place; if the handler controls attempt counts, the listener only needs to run business logic and throw the proper exception type.

### 6.1. Exception classification matters more than attempt count

A record with a validation error should go straight to recovery, even on attempt 1. A record hitting a transient timeout is reasonable to retry with backoff. Looking solely at attempt count while ignoring exception type leads to inconsistent policies.

Examples:

| Exception | Retry? | Reason |
|---|---|---|
| Brief timeout | Yes, bounded | Can recover once the dependency stabilizes |
| HTTP 503 | Yes, within time budget | Dependent service may become available again |
| Database deadlock | Bounded | Transaction can rerun if idempotent |
| Schema-invalid payload | Usually no | Payload will not fix itself after backoff |
| Business rule rejection | Usually no | Business outcome has already been determined |
| Persistent authorization error | Usually no aggressive retries | Requires config/ACL changes |

Delivery attempt is **supplementary information**, whereas the retry decision relies on combining error type, elapsed time, attempt count, and business rules.

## 7. How do headers in retry topics differ?

Spring Kafka has two widely used retry models:

1. **Blocking retry:** The error handler keeps the record in the container's processing path, applies backoff, and lets the listener reprocess it. `KafkaHeaders.DELIVERY_ATTEMPT` is the right signal for tracking deliveries under this mechanism.
2. **Non-blocking retry:** The failed record is published to one or more retry topics. The main topic consumer continues processing other data; another listener container consumes records from the retry topic after wait intervals.

Retry topic infrastructure has its own attempt tracking and dedicated headers, such as `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` in Spring Kafka versions supporting that API. This counter has a different scope from a single listener container's delivery attempt.

| Scenario | What can change |
|---|---|
| Blocking retry of the same record in container | Delivery attempt increments per handler delivery |
| Record published to a retry topic | New record on another topic, carrying retry-topic metadata |
| DLT consumer reads the record | A new delivery in the DLT container; does not automatically continue the source listener's attempt count |
| DLT replayed back to main topic | A new processing flow; requires event ID to recognize the original event |
| Consumer restart/rebalance | Attempt counter state may reset or change |

Do not simply add `KafkaHeaders.DELIVERY_ATTEMPT` to retry-topic attempts or treat them as one durable counter. If the system needs statistics on total processing runs across topics, design dedicated metadata with a clear contract and preserve it across every republish.

### 7.1. @RetryableTopic example

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0))
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void consume(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

Here, `attempts = "4"` is the total number of attempts under the non-blocking retry policy, including the initial processing attempt. Exact topic creation, header names, and behavior depend on the Spring Kafka version and retry topic configuration.

This example does not automatically enable the container's delivery attempt header. If the application wants to read both kinds of information, configure and clearly distinguish the attempt sources.

### 7.2. Business ordering with retry topics

A record sent to a retry topic may be processed **after** newer records from the main topic, even when they share the same business key. Thus, retry topics can alter business completion order. The delivery attempts header does not solve this issue.

If the business requires strict ordering, consider blocking retry, sequential per-key processing, or version checks/idempotency in the database.

## 8. Is the delivery attempt persisted durably?

Do not treat a listener container's delivery attempt as a counter persisted across all failures. Depending on the handler and version, record failure state is maintained in memory or within the container's processing scope.

Scenarios to watch out for:

- **Application restart:** The consumer re-reads uncommitted records. A new retry chain may start back at attempt 1.
- **Rebalance:** The partition moves to another consumer. The new member may not know the previous member's in-memory retry history.
- **Successful recovery:** A record's retry state is typically cleared or reset when the handler moves on to another record.
- **DLT replay:** The event is processed in a new flow; the new container's attempt does not reflect the full prior history.
- **Retry topic:** Attempts managed by retry infrastructure have a different scope and can be carried via Kafka headers on republished records.

If business regulations require at most N processing runs over multiple days or across deployments, use a durable counter in a database or in explicitly managed event metadata. Do not rely on the delivery attempt header to enforce long-term policies.

## 9. Relationship to offset commits and acknowledgements

The header reflects record deliveries; it does not confirm the record was processed and does not change when offsets are committed.

With at-least-once:

1. The listener receives the record.
2. The listener executes business logic.
3. If successful, the container acks/commits according to configuration.
4. If failed, the error handler retries/recovers.
5. If side effects completed yet the process stops before committing the offset, the record can be redelivered.

In step 5, a redelivery after restart can start a fresh attempt counter even though the business operation already completed earlier. Therefore, the application still needs idempotency.

Example of an inbox table:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Write the event ID and business changes inside the same database transaction. If the event is redelivered, the unique constraint helps detect it was already processed and prevents duplicate side effects.

Never use the delivery attempt value as an idempotency key. It is not unique and can repeat across different records.

## 10. Logging delivery attempts properly

When investigating retries, logs should contain both the record identifier and the delivery attempt. Example of a listener receiving `ConsumerRecord` alongside the header:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "ordersListenerFactory")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        @Header(name = KafkaHeaders.DELIVERY_ATTEMPT,
                required = false) Integer attempt) {

    log.info(
            "Kafka record received: topic={}, partition={}, " +
            "offset={}, key={}, attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            attempt == null ? "unknown" : attempt);

    orderService.processIdempotently(record.value());
}
~~~

Only log the key when permitted by security policy. Kafka keys can contain identifying or sensitive data; when necessary, log only an anonymized correlation ID or an appropriate hash. Do not log the full payload merely to know the attempt.

In multi-instance systems, also include service name, consumer group, listener ID, and trace ID (in traces/logs) to correlate processing runs. Do not put event IDs or trace IDs directly into high-cardinality metric tags.

### 10.1. Logging at appropriate verbosity

Logging INFO for every record in a system handling millions of records per day can be very expensive in storage. Some options:

- Log DEBUG on the first attempt, WARN when attempts exceed a threshold.
- Log ERROR when a record exhausts retries or recovery fails.
- Use aggregated metrics to track trends and logs to investigate specific records.
- Use controlled sampling when volume is huge, without dropping logs for severe errors.

The header helps build contextual log messages; it does not force an application to emit a log line for every single delivery.

## 11. Metrics and alerts related to delivery attempts

Metrics should reflect both **redeliveries** and **business impact**. High attempt counts can hint at an unstable dependency, but the attempt count alone does not identify the cause.

| Metric | Purpose |
|---|---|
| Record processing duration | Time the listener spends per invocation |
| Retry/re-delivery rate | Rate at which records are reprocessed |
| Delivery attempt distribution | Share of records at attempt 1, 2, 3, or grouped over a threshold |
| Listener exception rate | Categorize errors causing retries |
| Consumer lag | Detect backlogs from prolonged retries |
| Oldest record age | Measure delay against SLA |
| DLT incoming rate | Detect records exhausting retries needing investigation |
| Recovery failure count | Detect unavailable recovery paths |

If you want to add attempts as a metric tag, bucket them into a small, stable set of values, such as `first`, `retry_2_3`, and `retry_4_plus`. Do not use offsets, event IDs, order IDs, or raw exception messages as tags.

### 11.1. Useful alerts

- Average retry/delivery attempts spike unusually after a deploy.
- Sustained rise in the proportion of records reaching high attempt numbers.
- Listener exception rate rises alongside consumer lag.
- DLT receives more records than baseline.
- Dependency timeouts rise during the same period.
- Recovery/DLT publish failures appear.

Thresholds should be based on SLOs and workload characteristics. A flow calling an auxiliary API might tolerate brief retries; a payment confirmation flow might require immediate reconciliation whenever timeout outcomes are ambiguous.

## 12. Runbook when attempts spike abnormally

### 12.1. Many records moving from attempt 1 to 2 or 3

1. Group errors by exception class and dependent service.
2. Compare when retries started rising against recent releases/config changes.
3. Check timeouts, throttling, network, and broker/consumer health.
4. Measure total backoff duration and downstream call counts.
5. Verify whether the exception is truly retryable.
6. Limit concurrency or adjust backoff if retries are adding extra load.
7. Monitor consumer lag and oldest record age until recovery.

### 12.2. Record is redelivered yet header remains 1

This could be a new retry sequence after a consumer restart/rebalance, a listener without the header enabled, or a record moved to another topic. Steps:

1. Verify the container has the delivery attempt header enabled.
2. Verify the listener uses the right factory and error handler.
3. Check consumer restarts, rebalances, and partition assignments.
4. Determine whether the record came from the main topic, a retry topic, or the DLT.
5. Check whether retry-topic attempts are being confused with delivery attempts.
6. Use the event ID and prior logs to verify actual history.

### 12.3. Listener does not receive the header

1. Check the Spring Kafka version.
2. Check `setDeliveryAttemptHeader(true)` on the running container.
3. Check whether the handler supports `DeliveryAttemptAware`.
4. If using annotations, check the header name and `required = false`.
5. If reading raw headers, check `lastHeader(...)` and byte array length.
6. Check whether the listener runs through a custom consumer path outside the container.

Do not rush to add a custom producer header with the same name to "compensate". Producer-created headers do not reflect container redelivery counts and can mislead diagnostics.

### 12.4. DLT grows while attempt is only 1

This may be expected if the exception is classified as non-retryable. Inspect error classification, `addNotRetryableExceptions(...)` configuration, and the actual root cause. Do not increase retries just to see higher attempt numbers; for schema-invalid payloads or validation errors, retrying multiple times only increases lag.

## 13. Testing the delivery attempts header

Integration tests should verify both header values and retry behavior. An illustrative scenario:

1. Create a test topic and a listener container with the delivery attempt header enabled.
2. Configure `DefaultErrorHandler` with two short retries.
3. Send a record with a stable event ID.
4. Make the listener throw a retryable exception on the first two attempts.
5. Make the listener succeed on the third attempt.
6. Record the attempt values observed by the listener.
7. Verify the three invocations correspond to attempts 1, 2, and 3 within the retry sequence.
8. Verify the offset is committed only after successful processing.
9. Test a non-retryable exception and verify it does not go through multiple attempts.
10. Test restarting mid-retry to observe the limits of the in-memory counter.

Also test a listener without the header enabled to confirm the code handles a missing header without throwing new errors. If using retry topics, separately test the retry-topic infrastructure's attempt metadata, since its counting scope differs from blocking retry.

### 13.1. Sample check inside a test listener

You can record received attempts to verify:

~~~java
List<Integer> observedAttempts =
        new CopyOnWriteArrayList<>();

@KafkaListener(
        topics = "orders.test",
        containerFactory = "ordersListenerFactory")
public void testListener(
        OrderEvent event,
        @Header(KafkaHeaders.DELIVERY_ATTEMPT) int attempt) {

    observedAttempts.add(attempt);

    if (attempt < 3) {
        throw new TemporaryInventoryException(
                "Injected test failure");
    }
}
~~~

This illustrates the mechanism for recording attempts, not a complete test class. In integration tests, synchronize waiting for all three processing runs, test state resets, and offset verification to avoid flaky tests.

## 14. Common mistakes

**Treating attempt 1 as "never failed before":** The consumer may have just restarted or the record may have been replayed. The header is not a durable retry history.

**Interpreting attempt 3 as three retries:** Attempt counts include the initial delivery, so it typically corresponds to two retries after the first attempt.

**Not enabling the header on the right container:** Configuring a different factory or setting a Kafka client property will not deliver the header to the listener.

**Assuming the header is always present:** Some processing paths lack the header. Use a nullable type and validate before decoding raw bytes.

**Reading raw bytes as a UTF-8 string:** Delivery attempts in this mechanism are encoded as a 4-byte integer; decoding wrongly yields meaningless values.

**Using attempt as an idempotency key:** Attempts are not unique and can reset or change. Use a stable business event ID.

**Mixing blocking and non-blocking attempts:** Retry topics have their own metadata mechanism. Be clear which counter is being referenced.

**Increasing retries just because the header value looks low:** Base retry decisions on exception types and SLAs, not on making attempt numbers climb.

**Putting event IDs into metric tags:** Cardinality will explode; keep detailed identifiers in logs/traces.

## 15. Deployment and operations checklist

### Configuration

- [ ] Verified Spring Kafka version and supported APIs.
- [ ] `deliveryAttemptHeader` enabled on the correct `ContainerProperties`.
- [ ] Error handler supports delivery attempts.
- [ ] Listener uses the right container factory.
- [ ] Header value is read safely when potentially absent.

### Retry policy

- [ ] Retryable and non-retryable exceptions classified.
- [ ] Bounded retry counts and backoff configured.
- [ ] Distinguished delivery attempts from producer retries and retry-topic attempts.
- [ ] DLT/recovery confirms success only when the record is safely stored.
- [ ] Consumer is idempotent when records are redelivered.

### Observability

- [ ] Logs include topic, partition, offset, and attempt where appropriate.
- [ ] Metrics track retries, exceptions, lag, and DLT.
- [ ] Dynamic keys or event IDs are not used as metric tags.
- [ ] Alerts configured for sustained high attempts or abnormal retry spikes.
- [ ] Runbook covers missing headers or resets after restart.

### Testing

- [ ] Immediately succeeding record has the expected initial attempt.
- [ ] Finite retries increment attempt within the same processing sequence.
- [ ] Non-retryable exceptions route to recovery per policy.
- [ ] Missing header does not break the listener.
- [ ] Restart/rebalance and DLT replay tested if relevant to the system.

## Conclusion

`KafkaHeaders.DELIVERY_ATTEMPT` provides a direct signal of which record delivery the listener is currently handling. When `ContainerProperties.setDeliveryAttemptHeader(true)` is enabled alongside a compatible error handler, Spring Kafka can populate the attempt count in the header for listeners to read via `@Header` or `ConsumerRecord.headers()`. The value starts at 1 and increments on redeliveries within the scope of the corresponding retry mechanism. Use it to observe errors, explain retries, and support operations; for long-term reliability, you still need exception classification, bounded backoff, recovery/DLT, idempotency, and a dedicated state store if the business must count attempts across multiple restarts or replays.
