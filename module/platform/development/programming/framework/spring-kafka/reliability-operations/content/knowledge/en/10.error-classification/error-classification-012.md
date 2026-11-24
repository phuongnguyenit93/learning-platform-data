# Error policy by record type

In Spring Kafka, not every failing record should be handled the same way. A payment event may need retries when a banking service is temporarily unavailable; an event with an unsupported schema may need routing to a quarantine flow; a notification event may be skipped after logging the error if business rules permit. Error policies must combine record type, error cause, recoverability, and impact of reprocessing.

Spring Kafka provides error handlers, backoff, retry listeners, and recoverers to control retries or route records to a Dead Letter Topic (DLT). However, `DefaultErrorHandler` classifies primarily by exception type. If multiple event types share one topic and require different policies, the application must add rules based on record metadata or split listeners/containers by stream type.

## 1. Why is an error policy by record type needed?

A consumer may receive several record groups with different characteristics:

- Critical business events such as `OrderCreated`, `PaymentAuthorized`, or `InventoryReserved` must avoid data loss and typically require retrying transient errors.
- Events with invalid data, missing required fields, or unsupported schema versions usually cannot succeed by retrying the same payload.
- Auxiliary events such as email notifications or analytics may have lower priority and different recovery policies than payment flows.
- Events calling dependent systems may fail due to timeouts, rate limits, or outages; the cause may clear after a backoff period.

If every record is retried infinitely, a poison record can stall a partition and delay valid records behind it. If every error is sent straight to a DLT, a brief database outage can quarantine large batches of records that would succeed a few seconds later. Policies must distinguish temporary errors from errors unfixable by retry.

## 2. Classifying records before choosing an action

Records should carry enough metadata to identify the event type and trace them. An envelope typically includes `eventId`, `eventType`, `schemaVersion`, `occurredAt`, and payload. If the event type is carried in a Kafka header, consumers can route by header without guessing from payload contents.

Example event envelope:

```json
{
  "eventId": "evt-8f31",
  "eventType": "PaymentAuthorized",
  "schemaVersion": 2,
  "occurredAt": "2026-11-15T10:15:30Z",
  "payload": {
    "paymentId": "pay-1042",
    "orderId": "ord-208"
  }
}
```

When using headers, producers can attach event type and schema version:

```java
ProducerRecord<String, PaymentEvent> record =
        new ProducerRecord<>("business-events", event.orderId(), event);

record.headers().add(
        "event-type",
        "PaymentAuthorized".getBytes(StandardCharsets.UTF_8));
record.headers().add(
        "schema-version",
        "2".getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
```

Headers are metadata aiding routing and observability; they do not replace payload validation. If headers and payload conflict, consumers need rules defining the authoritative source and must log inconsistencies.

A baseline policy matrix:

| Record group | Example errors | Appropriate action |
|---|---|---|
| Critical business events | Database timeout, HTTP 503, rate limit | Retry with backoff and bounded attempts; then recovery/DLT |
| Malformed payload | Missing field, wrong data type, unparseable JSON | Do not repeatedly retry same payload; quarantine to DLT/quarantine |
| Unsupported schema or event version | Consumer does not understand new version | Quarantine, alert, and process after updating consumer or schema mapping |
| Business rule violation | Negative amount, invalid state transition | Usually no retry; record business error and DLT if investigation needed |
| Temporary dependency failure | Database unavailable, timeout, flaky downstream broker | Retry with backoff, jitter, or appropriate circuit breaker |
| Skippable auxiliary events | Non-essential analytics | Recover per business SLO; may DLT or log controlled skip |

This policy follows business requirements. Never decide retries solely by topic name or exception name without verifying whether retrying the same record has a chance of succeeding.

## 3. Classifying error causes

### Transient errors

Transient errors can resolve on their own without altering the payload. Examples include connection timeouts, HTTP 429/503, temporary inability to acquire a database connection, or a recovering dependency. These errors usually suit retries with pauses.

Retries must have limits and backoff. Tight retries without pauses can overload a struggling downstream system further. For rate-limit errors, respect `Retry-After` if readable by the application and design policies accordingly.

### Non-retryable data or business errors

Unparseable payloads, events missing required identifiers, unsupported schema versions, or violated business rules rarely become valid after a few retries. Retrying the same payload wastes resources and can stall partitions.

This group should typically be marked non-retryable and routed to a DLT or quarantine after the initial failure. The DLT must store enough metadata for operations to investigate and decide whether to fix data, upgrade consumers, or discard records per policy.

### Programming or configuration errors

Null pointers, class casts, bean wiring errors, or wrong serializer configurations can affect many records at once. Per-record retries rarely fix the root cause. Distinguish an isolated bad payload from a widespread deployment bug. If all records fail together, alert and consider stopping the stream to avoid flooding the DLT with the entire backlog.

### Unknown errors

When the cause cannot yet be classified, use bounded retries and observable recovery. Never assume every unfamiliar error is a data error or a temporary error. Log the root exception, record metadata, and delivery attempts for investigation.

## 4. Spring Kafka exception classification with DefaultErrorHandler

In modern Spring Kafka, `DefaultErrorHandler` is the common error handler for listener containers not using transaction rollback flows. The handler receives exceptions from listeners, applies backoff, retries records, and invokes the recoverer when retries exhaust or an exception is classified as non-retryable.

Non-retryable exceptions can be configured via `addNotRetryableExceptions()` and retryable exceptions via `addRetryableExceptions()`:

```java
@Bean
DefaultErrorHandler businessErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class,
            UnsupportedEventVersionException.class,
            BusinessRuleViolationException.class);

    handler.addRetryableExceptions(
            TemporaryInventoryException.class,
            TransientDataAccessException.class);

    return handler;
}
```

`FixedBackOff(1_000L, 3L)` represents a one-second pause between retries and at most three retries after initial delivery. If all three retries fail, the recoverer is invoked. Exceptions classified as non-retryable go directly to recovery without waiting through these retries.

Default exception lists and behavior may vary by Spring Kafka version. Modern `DefaultErrorHandler` already treats several exception types as fatal/non-retryable by default, such as deserialization, message conversion, or method argument resolution errors. When configuring policies, verify the classifier for your version and explicitly register application business exceptions.

An exception can be wrapped inside another exception as it passes through listener adapters or framework layers. Inspect actual exceptions in logs and verify how your version's classifier evaluates the cause chain. Never add a generic wrapper to the retryable list if doing so inadvertently turns non-retryable data errors into retryable ones.

## 5. Classifying by exception is not classifying by record type

By default, `DefaultErrorHandler` makes decisions based on exceptions. For example, `InvalidOrderPayloadException` is treated as non-retryable for any record throwing that exception. The handler does not automatically know that `PaymentAuthorized` needs three retries while `AnalyticsEvent` needs only one if both throw the same exception type.

If record types require different retry policies, there are three design options:

1. Split topics or listeners by business group and configure separate error handlers/backoffs per listener container.
2. Use a shared listener while building custom error handling capable of reading record metadata such as headers, topic, key, or event type.
3. Keep a shared retry policy while customizing the recoverer to route records to different DLTs/quarantines by record type.

Option one is usually easiest to operate when streams have distinct SLOs, retry budgets, and owning teams. Option two fits when multiple event types must share one topic and genuinely need different backoffs. Option three changes the recovery destination by record type, though by itself it does not vary retry counts.

### Dedicated listener factory per stream type

Example where payment and notification topics have different policies:

```java
@Bean
DefaultErrorHandler paymentErrorHandler(
        KafkaTemplate<Object, Object> template) {
    var recoverer = new DeadLetterPublishingRecoverer(template);
    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(2_000L, 4L));
    handler.addNotRetryableExceptions(
            InvalidPaymentException.class,
            UnsupportedPaymentVersionException.class);
    return handler;
}

@Bean
DefaultErrorHandler notificationErrorHandler(
        KafkaTemplate<Object, Object> template) {
    var recoverer = new DeadLetterPublishingRecoverer(template);
    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(500L, 1L));
    handler.addNotRetryableExceptions(
            InvalidNotificationException.class);
    return handler;
}
```

Each `ConcurrentKafkaListenerContainerFactory` attaches its corresponding error handler:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
paymentListenerFactory(
        ConsumerFactory<String, PaymentEvent> consumerFactory,
        DefaultErrorHandler paymentErrorHandler) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(paymentErrorHandler);
    return factory;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, NotificationEvent>
notificationListenerFactory(
        ConsumerFactory<String, NotificationEvent> consumerFactory,
        DefaultErrorHandler notificationErrorHandler) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, NotificationEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(notificationErrorHandler);
    return factory;
}
```

Listeners select their corresponding factories:

```java
@KafkaListener(
        id = "payments-listener",
        topics = "payments",
        containerFactory = "paymentListenerFactory")
public void handlePayment(PaymentEvent event) {
    paymentService.process(event);
}

@KafkaListener(
        id = "notifications-listener",
        topics = "notifications",
        containerFactory = "notificationListenerFactory")
public void handleNotification(NotificationEvent event) {
    notificationService.send(event);
}
```

By separating factories, each stream gets its own backoff and exception classification. Ensure consumer factories, deserializers, and producers used for DLTs match their respective data types.

## 6. Routing DLTs by record type

When event types share a topic, `DeadLetterPublishingRecoverer` can use a destination resolver to select a DLT based on headers. Example:

```java
@Bean
DeadLetterPublishingRecoverer eventDeadLetterRecoverer(
        KafkaTemplate<Object, Object> template) {

    return new DeadLetterPublishingRecoverer(template, (record, exception) -> {
        Header typeHeader = record.headers().lastHeader("event-type");
        String eventType = typeHeader == null
                ? "unknown"
                : new String(typeHeader.value(), StandardCharsets.UTF_8);

        String dltTopic = switch (eventType) {
            case "PaymentAuthorized" -> "payments.DLT";
            case "OrderCreated" -> "orders.DLT";
            case "InventoryReserved" -> "inventory.DLT";
            default -> "unknown-events.DLT";
        };

        return new TopicPartition(dltTopic, record.partition());
    });
}
```

This snippet requires Java with switch expression support. The resolver runs when a record needs recovery; it chooses the topic from the header and preserves the corresponding partition. If the DLT keeps the exact partition number, the target topic must have enough partitions to accept every source partition. If partition counts differ, choose another partitioning strategy instead of letting DLT publishing fail.

`DeadLetterPublishingRecoverer` can add headers containing source details such as topic, partition, offset, timestamp, and exception metadata. These headers are vital for investigation and replay. Do not strip them if operational workflows need traceability to the original record.

Routing DLTs by event type only decides where to store the record after recovery. If `PaymentAuthorized` needs four retries while `OrderCreated` needs one, you need per-record backoff/classification logic or separate listeners/containers. Do not expect a DLT resolver to alter retry counts on its own.

## 7. Deserialization errors and ErrorHandlingDeserializer

Some errors occur before the listener receives a Java object—for example, malformed JSON, improperly formatted byte payloads, or a deserializer unable to instantiate an object. If the consumer deserializer throws directly inside `poll()`, the listener has no chance to inspect the record or handle errors in business code.

Spring Kafka provides `ErrorHandlingDeserializer` to catch deserialization errors and pass error details in record headers, allowing the container error handler or recoverer to process them. Example value deserializer configuration in Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.BusinessEvent
        spring.json.trusted.packages: com.example.events
```

The delegate deserializer parses the payload. If parsing fails, `ErrorHandlingDeserializer` stores exception details in headers so error handling can process the record. Actual configuration must align serializers, type mappings, trusted packages, and Spring Kafka versions; never widen trusted packages excessively if the application consumes data from untrusted sources.

When publishing to a DLT for deserialization-failed records, the payload may still be the raw byte array rather than a deserialized object. The DLT producer needs serializers able to handle both byte arrays and normal object types, or an appropriate serializer strategy. If the serializer rejects the actual data type, recovery can fail and the record still needs error handler intervention.

Deserialization errors are usually classified as non-retryable for the same payload. If the error stems from a producer sending the wrong schema or a truncated payload, retrying will not change the bytes. Route to DLT/quarantine and alert the producer or schema owner.

## 8. Validation and business errors after deserialization

Once the payload is converted to an object, listeners or business services can verify conditions:

- Required fields are populated.
- IDs, currencies, amounts, or timestamps are valid.
- Event type and schema version are supported.
- Current state permits transitioning to the new state.
- The record does not violate idempotency or uniqueness rules.

Example:

```java
@KafkaListener(topics = "payments", groupId = "payment-service")
public void handle(PaymentEvent event) {
    if (event.paymentId() == null || event.amount().signum() <= 0) {
        throw new InvalidPaymentException(
                "paymentId and amount must be valid");
    }

    paymentService.authorize(event);
}
```

`InvalidPaymentException` should be classified as non-retryable if input data must be corrected by the producer or business workflow. For errors such as a database timeout inside `authorize()`, use a dedicated exception expressing transience for controlled retries.

Avoid using a generic exception like `RuntimeException` for validation, timeouts, and programming bugs alike. When all errors share one type, the error handler cannot reliably apply distinct policies. Creating exceptions by business cause clarifies logs, retry classification, and metrics.

## 9. Batch listeners and identifying failing records

With record listeners, an exception thrown during an invocation naturally maps to the single record being processed. With batch listeners, one invocation can contain many records. Throwing a generic exception leaves the error handler unable to tell which record in the batch failed, potentially forcing a retry of the whole batch.

Spring Kafka supports `BatchListenerFailedException` so listeners can pinpoint the failing record or index. Example:

```java
@KafkaListener(topics = "orders", groupId = "order-projection")
public void handleBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderEvent> record = records.get(i);
        try {
            orderProjectionService.apply(record.value());
        }
        catch (InvalidOrderPayloadException ex) {
            throw new BatchListenerFailedException(
                    "Invalid order payload",
                    ex,
                    i);
        }
    }
}
```

When using `DefaultErrorHandler` with a batch listener, record/index metadata helps the handler determine completed progress and the record to retry or recover. If the exception does not specify the failing record, the handler may have to retry the entire batch. Pick an approach matching batch atomicity and ensure previously completed side effects tolerate replay.

Do not catch exceptions inside the loop and continue to subsequent records if business logic requires ordering or batch integrity. If part of a batch already produced side effects and the batch retries, per-event idempotency or an appropriate database transaction is required.

## 10. Retry budgets and backoff

Retries must be bounded by a time budget and attempt count. A single record can hold a partition for a long time if retried continuously. Consider:

- Processing duration per attempt.
- Maximum number of retries.
- Wait interval between retries.
- Expected dependency outage duration.
- `max.poll.interval.ms` and impact of retries on the consumer group.
- Record priority and processing SLOs.

Example using exponential backoff:

```java
BackOff backOff = new ExponentialBackOffWithMaxRetries(5);
((ExponentialBackOffWithMaxRetries) backOff).setInitialInterval(500L);
((ExponentialBackOffWithMaxRetries) backOff).setMultiplier(2.0);
((ExponentialBackOffWithMaxRetries) backOff).setMaxInterval(8_000L);

DefaultErrorHandler handler = new DefaultErrorHandler(recoverer, backOff);
```

With the settings above, retries start after roughly 500 ms, grow by a factor of 2, and cap each pause at 8 seconds for at most five retries. Actual duration also depends on per-attempt processing time and scheduling. If jitter is needed to keep multiple consumers from retrying simultaneously after an outage, add a jittered backoff mechanism compatible with your version/framework or coordinate retries via a dedicated system.

Once the retry budget is spent, the recoverer must perform an observable action: publish to DLT, save to quarantine, or log an approved skip. Never allow recovery to fail while still treating the record as processed.

## 11. Retry topics and isolating long-running error streams

For errors requiring long waits, in-place retries can hold the partition and block subsequent records. Retry topics allow moving records to retry topics with wait intervals, where another consumer picks them up later. Spring Kafka supports non-blocking retry topics via `@RetryableTopic` in compatible versions.

Illustrative example:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        include = {TemporaryInventoryException.class},
        exclude = {InvalidOrderPayloadException.class})
@KafkaListener(topics = "orders", groupId = "order-projection")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}
```

Retry topic annotations and attributes vary by Spring Kafka version; check your project's version and compatibility with listener types, transaction modes, and DLT routing. Retry topics create multiple auxiliary topics and can alter processing order among records with the same key. Use them only when that behavior is acceptable and operational processes exist to manage retry topics.

Non-blocking retry topics fit when long waits are needed without stalling the source partition. For short errors, blocking retries inside `DefaultErrorHandler` can be simpler. Do not enable multiple retry layers simultaneously without calculating total deliveries and wait times; HTTP client, service-layer, error-handler, and retry-topic retries can multiply call counts unexpectedly.

## 12. DLT and recovery workflows

A DLT retains records that exhausted retries or were deemed non-retryable. A DLT record must carry enough information for operators to answer:

- Which source topic, partition, and offset did the record come from?
- Which consumer group processed it?
- What are the event ID, key, event type, and schema version?
- Which exception class, message, and stack trace occurred?
- How many times was the record attempted, and when was the last attempt?
- Can the data be fixed and replayed, or must it be marked terminal?

Recovery procedures should include:

1. Categorize records in the DLT by event type and cause.
2. Determine whether the error stems from data, consumer version, or dependency.
3. Fix the data or deploy a consumer capable of handling that schema/event version.
4. Perform controlled replays, preserving the original event ID and source metadata.
5. Monitor replay results and verify records are processed or closed per policy.

Never automatically replay the entire DLT back to the original topic without knowing the root cause. If the error persists, records loop back into the DLT. Replays must be idempotent so impacts completed prior to the failure or earlier stop are not duplicated.

## 13. Retries, offset commits, and transactions

For non-transactional consumers, `DefaultErrorHandler` coordinates seek/retry and offset commits per ack mode. Once a record is successfully recovered, the container can advance the offset past that record per handler configuration. If DLT publishing fails, recovery must be treated as failed so the record is not silently skipped.

For listener containers running inside Kafka transactions, listener errors normally trigger transaction rollback. Retry/recovery policies are managed through the transaction rollback flow, typically using `DefaultAfterRollbackProcessor` rather than applying `DefaultErrorHandler` alone like a non-transactional listener. You can configure a recoverer and backoff on the after-rollback processor; when committing the recovered record's offset alongside DLT publishing, configure transactions accordingly.

Do not mix non-transactional error handler configuration examples into transactional listener containers without examining rollback flows. Determine whether a listener participates in Kafka transactions before choosing a handler, because offset commit points, rollbacks, and recovery differ.

Kafka transactions can protect Kafka outputs and input offsets within the same transaction. They do not automatically protect side effects in databases or HTTP APIs. For side effects outside Kafka, use idempotency, inbox/outbox, or proper database transactions so retried records do not duplicate impacts.

## 14. Observing error policies

An error policy is only effective when operations can measure it. At a minimum, monitor:

- Retry counts by topic, event type, and exception class.
- Records routed to DLT/quarantine by cause.
- Ratio of transient errors vs. permanent errors.
- Time from initial delivery to successful processing or recovery.
- Consumer lag, rebalances, and time partitions are stalled by retries.
- DLT publish failures and DLT backlog counts.
- Duplicate rates caught by idempotency or inbox tables.

Logs should include topic, partition, offset, key, event ID, event type, schema version, consumer group, delivery attempt, and exception class. Avoid logging sensitive payloads. Whenever possible, use low-cardinality metric tags; never use event ID as a metric label because value cardinality can grow unboundedly.

A `RetryListener` can record each retry attempt:

```java
handler.setRetryListeners((record, exception, deliveryAttempt) -> {
    log.warn(
            "Retry topic={} partition={} offset={} attempt={} exception={}",
            record.topic(),
            record.partition(),
            record.offset(),
            deliveryAttempt,
            exception.getClass().getSimpleName());
});
```

Exact callback signatures may vary across versions; use the Spring Kafka API matching your project. Combine logs with metrics and alerts to catch when one record type suddenly floods into the DLT.

## 15. Example policy design for a multi-event-type topic

Suppose topic `business-events` holds `OrderCreated`, `PaymentAuthorized`, and `InventoryReserved`. Each event carries an `event-type` header and a stable ID.

| Event type | Transient errors | Permanent errors | DLT |
|---|---|---|---|
| `OrderCreated` | Retry up to 3 times with short backoff | DLT to investigate order data | `orders.DLT` |
| `PaymentAuthorized` | Retry up to 5 times with longer backoff | DLT and alert payment team | `payments.DLT` |
| `InventoryReserved` | Short retry, then DLT | DLT and inspect inventory state | `inventory.DLT` |
| Unknown event type | Do not retry unrecognized payload | Quarantine and alert schema/producer | `unknown-events.DLT` |

If only distinct DLTs are needed with shared retries, a single `DefaultErrorHandler` with a header-routing recoverer may suffice. If retry counts/backoffs differ by event type, split listeners/containers or implement custom error handling capable of reading record metadata. Do not try to express all record policies through one global exception list when the same exception means different things for different event types.

With a topic carrying multiple event types, listeners can deserialize into a common envelope and dispatch by `eventType`. If deserialization fails before the envelope is created, `ErrorHandlingDeserializer` and a policy for unrecognizable records are required. This is why event type metadata should be passed reliably in headers or a readable envelope structure.

## 16. Design principles

- Classify errors by recoverability: transient, permanent, programming/configuration, and unknown.
- Distinguish exception classification from record-type policies; `DefaultErrorHandler` classifies by exception by default.
- Use specific business exceptions to express retryable and non-retryable errors.
- Bound retries and use suitable backoff to avoid overloading dependencies.
- Use `ErrorHandlingDeserializer` for errors occurring before the listener receives an object.
- Use DLT/quarantine for records needing investigation and preserve source metadata for replay.
- Split listeners/containers when record groups have different retry budgets or SLOs.
- For batch listeners, identify failing records with `BatchListenerFailedException` when appropriate.
- Do not mix non-transactional error handler setups with transactional listener rollback flows without examining semantics.
- Protect side effects outside Kafka with idempotency or inbox/outbox.
- Monitor retries, DLT, consumer lag, and recovery errors by event type.

Error policies by record type help consumers handle errors according to the business characteristics of each event. Identify records using stable metadata, distinguish retryable errors from those needing isolation, choose backoff and recovery per retry budget, and measure results. When record types have markedly different policies, split listeners/containers or add custom error handling to decide based on record metadata rather than solely on exception class.
