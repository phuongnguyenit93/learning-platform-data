# Log delivery attempt

In Spring Kafka Reliability Operations, **logging delivery attempts** is how you record **which processing attempt a Kafka record is on when delivered to the listener**. This information helps distinguish the first processing pass from redeliveries caused by retries, diagnose a record that fails repeatedly, measure backoff impact, explain why consumer lag grows, and trace the path toward a Dead Letter Topic (DLT).

A log line saying only "Failed to process record" is rarely enough for production. Operators need to know **which record**, **which consumer group**, **which topic/partition/offset**, **which attempt number**, **why it retried**, **whether retries remain**, and **whether the final outcome was success, recovery to DLT, or an infrastructure error**.

Spring Kafka provides a **delivery attempt header** mechanism and callbacks in error handling to obtain the attempt count. However, **the attempt count is not a global, permanent counter across all processing passes of the same event**. Its value may be scoped to a single error handler/container and can change upon consumer restarts, rebalances, retry-topic transitions, or manual data replays. For end-to-end investigation, combine the attempt count with Kafka record identity, event ID, trace ID, and processing outcome.

This lesson focuses on logging and diagnostics rather than turning delivery attempt logging into a retry mechanism. **The retry policy decides whether to redeliver; logging only helps observe that decision and its consequences.**

## 1. What does delivery attempt mean?

Suppose a listener receives an event:

~~~text
topic: orders.created
partition: 2
offset: 105
key: order-1001
~~~

On the first listener invocation, a dependency times out. The Spring Kafka error handler decides to retry and redeliver the record. With two retries:

~~~text
Delivery 1:
  orders.created/P2@105
  -> listener -> timeout

Backoff 1 second

Delivery 2:
  orders.created/P2@105
  -> listener -> timeout

Backoff 1 second

Delivery 3:
  orders.created/P2@105
  -> listener -> success
~~~

If the attempt count starts at 1, the three listener deliveries of the same record have attempts **1, 2, and 3**, respectively.

This differs from three easily confused concepts:

| Term | Meaning |
|---|---|
| **Delivery attempt** | Which delivery pass the record is on to the listener within a retry context |
| **Retry count** | Number of retries after the first processing attempt; usually equals attempt minus 1 in an unbroken sequence |
| **Backoff interval** | Wait time before the next retry attempt |
| **Committed offset** | The next position stored by the consumer group to resume reading on recovery |
| **Event ID** | Business identifier of the event, which can persist across multiple topics or publishes |

A record with delivery attempt = 3 does not prove the same business operation has only run three times across the entire system. That event could have been replayed earlier, copied to another topic, or processed by a different consumer group.

## 2. Why log the attempt?

During an incident:

~~~text
ERROR payment-service failed to process PaymentRequested
~~~

Operators cannot tell whether this is the first attempt, a transient error, or a poison message that has failed dozens of times.

A more useful structured log:

~~~text
event=kafka_record_processing_failed
listener=payment-requested-listener
group=payment-service
topic=payments.requested
partition=1
offset=482
delivery_attempt=3
retry_policy=blocking
error_category=downstream_timeout
retryable=true
record_event_id=evt-482
~~~

Attempt information helps answer:

1. Is the record being reprocessed?
2. Does the error self-recover on a subsequent attempt?
3. Is backoff slowing down consumer progress?
4. Is one record holding up a partition for a long time?
5. When does the error transition to a DLT?
6. Are many records failing once, or is one record failing repeatedly?
7. Does the incident stem from bad data, a transient dependency issue, or misconfiguration?

That is why attempt belongs in **structured logs and trace context**, but should not become an unbounded metric tag.

## 3. At which layer is delivery attempt tracked?

Inside a listener container, listener failures are handed to error handling. With **blocking retry**, a CommonErrorHandler such as **DefaultErrorHandler** manages delivery counts and decides between retry and recovery.

~~~text
KafkaConsumer.poll()
      |
      v
Listener container
      |
      +-- delivery attempt context
      |
      v
@KafkaListener
      |
      +-- success -> commit progress per AckMode
      |
      +-- throws exception
                  |
                  v
           DefaultErrorHandler
                  |
                  +-- retry with BackOff
                  |
                  +-- retries exhausted -> recoverer / DLT
~~~

Spring Kafka supports **DeliveryAttemptAware** on the corresponding error handlers/after-rollback processors so the container can attach the attempt to the record.

Important:

- The Kafka broker **does not automatically add KafkaHeaders.DELIVERY_ATTEMPT** to every message.
- Attempts in blocking retry are usually determined by the **Spring Kafka container/error handler**.
- If the error handler does not support delivery attempts, the header option is not enabled, or execution does not take the matching path, the header may be absent.
- Attempt tracking can differ across blocking retry, non-blocking retry topics, batch processing, and custom handlers.

Do not write code assuming every Kafka record always carries an attempt header.

## 4. KafkaHeaders.DELIVERY_ATTEMPT

Spring Kafka provides the constant **KafkaHeaders.DELIVERY_ATTEMPT** to access the header representing the delivery attempt in supported configurations.

~~~java
KafkaHeaders.DELIVERY_ATTEMPT
~~~

In a raw Kafka ConsumerRecord, Kafka headers are **byte[]**. For delivery attempts added by the Spring Kafka container via the corresponding mechanism, the raw format is typically a 4-byte integer per framework convention.

In Spring Messaging and @KafkaListener parameter binding, the framework can convert the header to **Integer** to pass into the listener method.

Two views to distinguish:

~~~text
ConsumerRecord.headers():
  Kafka Header -> byte[]

@Header(KafkaHeaders.DELIVERY_ATTEMPT):
  Spring Messaging conversion -> Integer
~~~

Do not blindly convert the byte[] header to a UTF-8 String and parse with Integer.parseInt(). For a 4-byte binary integer header, that yields wrong results.

The attempt value in documentation usually starts at **1** for the first delivery. However, when the header is missing or a custom error handler is used, represent it as **unknown** instead of asserting an unobserved retry history.

## 5. Enabling the delivery attempt header on the container

On a listener container factory:

~~~java
@Configuration
public class KafkaListenerLoggingConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);

        // Instruct the container to add the delivery attempt to record headers
        // when the error handler supports this mechanism.
        factory.getContainerProperties()
                .setDeliveryAttemptHeader(true);

        return factory;
    }
}
~~~

This example follows the Spring Kafka API supporting **setDeliveryAttemptHeader**. Verify your exact dependency version, as APIs, defaults, and applicability have changed across releases.

Key prerequisites:

1. This factory must be the factory **actually** used by @KafkaListener.
2. The error handler attached to the factory must support the delivery attempt mechanism.
3. Do not assume enabling the property guarantees every record on every listener receives the header.
4. For batch listeners or other error paths, verify support in your version.
5. If there are multiple listener factories, configure each intended factory rather than only an unused one.

An application may use Spring Boot auto-configuration. Even then, verify the actual listener container being configured rather than just checking that a bean exists.

## 6. Creating a DefaultErrorHandler with bounded retries

An example of blocking retry using BackOff:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    // 1 second between retries, up to two retry attempts.
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

In this example, for a retryable error unaffected by exception classification changes:

~~~text
Attempt 1 -> failure
  wait 1 second
Attempt 2 -> failure
  wait 1 second
Attempt 3 -> failure
  recoverer / DLT
~~~

**FixedBackOff(1000, 2) performs two retries after the first attempt**, not two deliveries total.

Considerations for real deployments:

- The DLT KafkaTemplate needs serializers matching the actual keys/values.
- DLT topic, partitions, permissions, and producer acknowledgements must be valid.
- Some exceptions may be classified as non-retryable and recovered immediately.
- The recoverer itself can fail; do not assume a record was handled successfully just because the recoverer was called.
- If the error handler resets state on exception changes, the attempt count may change when the exception type changes.

The example does not stake reliability solely on attempt logging; test recovery and offset commits too.

## 7. Reading the attempt from a @KafkaListener parameter

With Spring header binding in a listener method:

~~~java
@KafkaListener(
        id = "orders-created-listener",
        topics = "orders.created",
        groupId = "orders-service",
        containerFactory = "orderListenerFactory")
public void listen(
        ConsumerRecord<String, OrderEvent> record,
        @Header(
            name = KafkaHeaders.DELIVERY_ATTEMPT,
            required = false
        ) Integer deliveryAttempt) {

    String attemptText =
            deliveryAttempt == null
                    ? "unknown"
                    : deliveryAttempt.toString();

    log.info(
            "Kafka record received; topic={}, partition={}, " +
            "offset={}, deliveryAttempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            attemptText);

    orderService.process(record.value());
}
~~~

Setting **required = false** prevents the listener from failing solely because the header is absent in unsupported configs or when delivery attempt tracking is not enabled.

In some converter/container paths, @Header converts to Integer automatically; test the listener method with your Spring Kafka version and actual message types. To avoid relying on conversion, read raw ConsumerRecord headers and decode the byte[] directly.

Do not use **deliveryAttempt == null ? 1 : deliveryAttempt** in critical audit logs without explanation. A missing header means **the attempt was not observed**, not proof that this is the first delivery across the whole system.

## 8. Reading the raw delivery attempt header

When the listener receives a ConsumerRecord, you can read the header directly:

~~~java
import java.nio.ByteBuffer;
import java.util.OptionalInt;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.support.KafkaHeaders;

public final class DeliveryAttemptHeaders {

    private DeliveryAttemptHeaders() {
    }

    public static OptionalInt readAttempt(
            ConsumerRecord<?, ?> record) {

        Header header = record.headers()
                .lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);

        if (header == null
                || header.value() == null
                || header.value().length != Integer.BYTES) {
            return OptionalInt.empty();
        }

        int attempt = ByteBuffer.wrap(header.value()).getInt();

        return attempt > 0
                ? OptionalInt.of(attempt)
                : OptionalInt.empty();
    }
}
~~~

This example uses **byte[4]** for the raw delivery attempt header created by Spring Kafka's standard mechanism. If your application produces custom headers in a different format, standardize the format; do not apply this function blindly to arbitrary retry headers.

Why use **lastHeader**?

Kafka Headers allow multiple headers with the same key. A record forwarded/copied across topics or libraries may accumulate duplicate header keys. Picking the last header avoids accidentally reading an older value, though it is **not proof that all systems share the same encoding**.

If the header is missing or malformed, return OptionalInt.empty(), record unknown, and continue business processing per policy. Never fail a consumer just because logging could not decode the attempt.

## 9. How to log when the header does not exist?

Distinguish three cases:

| Case | Observed value | How to log |
|---|---|---|
| Header present, valid value | 1, 2, 3... | delivery_attempt as an integer |
| Header absent | Unknown | delivery_attempt=unknown |
| Header malformed | Invalid | delivery_attempt=unknown plus rate-limited technical log/counter |

Example:

~~~text
event=kafka_record_received
topic=orders.created
partition=2
offset=105
delivery_attempt=unknown
delivery_attempt_source=not_available
~~~

Avoid logging:

~~~text
delivery_attempt=0
~~~

which leads dashboards to think it is attempt 0, since Kafka delivery attempts by convention start at 1.

Also, do not attach raw malformed byte[] values to metric tags. To diagnose malformed headers, log the byte array length or a bounded error code while avoiding sensitive payload dumps.

## 10. Logging at the start of the listener

A useful listener-entry log:

~~~java
@KafkaListener(
        id = "orders-created-listener",
        topics = "orders.created",
        containerFactory = "orderListenerFactory")
public void handle(ConsumerRecord<String, OrderEvent> record) {
    OptionalInt attempt = DeliveryAttemptHeaders.readAttempt(record);

    log.debug(
            "Kafka delivery started: topic={}, partition={}, " +
            "offset={}, attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            attempt.isPresent() ? attempt.getAsInt() : "unknown");

    orderService.process(record.value());
}
~~~

However, **INFO logs for every record at high throughput can incur massive overhead**. If a system processes hundreds of thousands of records per second, logging each delivery spikes CPU, I/O, ingest costs, and makes critical incident logs harder to find.

A practical policy:

- **DEBUG** for per-delivery entry details, enabled selectively during investigations.
- **WARN** when an attempt fails but will retry.
- **ERROR** when final recovery fails or severe infrastructure errors occur.
- **INFO** for major lifecycle transitions or important successful recoveries, not necessarily every record under high load.

Align logging policy across the listener, error handler, and recoverer to avoid **logging the same error three times** with identical stack traces.

## 11. Using RetryListener to log failures by attempt

Instead of logging attempts only at listener entry, Spring Kafka's **DefaultErrorHandler** can register a **RetryListener** to observe failed attempts and recoveries.

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.setRetryListeners(new RetryListener() {

        @Override
        public void failedDelivery(
                ConsumerRecord<?, ?> record,
                Exception exception,
                int deliveryAttempt) {

            log.warn(
                    "Kafka delivery failed: topic={}, partition={}, " +
                    "offset={}, attempt={}, errorType={}",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    deliveryAttempt,
                    exception.getClass().getSimpleName());
        }

        @Override
        public void recovered(
                ConsumerRecord<?, ?> record,
                Exception exception) {

            log.info(
                    "Kafka record recovered: topic={}, partition={}, offset={}",
                    record.topic(),
                    record.partition(),
                    record.offset());
        }
    });

    return handler;
}
~~~

RetryListener overloads and callback signatures depend on the Spring Kafka version; this example shows the record-oriented RetryListener supported in matching releases. Batch retries have separate callbacks in supported versions.

**RetryListener.failedDelivery** is well suited for logging attempts on failure because the error handler holds retry context that a plain business listener may lack. However, distinguish **a callback reporting a failure** from **a guarantee of another retry**: the final attempt also passes through failedDelivery before the recoverer is invoked.

## 12. Illustrative RetryListener timeline

Suppose a 1-second backoff, two retries, and a DLT recoverer:

~~~text
t=00.000s   listener attempt 1
            -> TimeoutException
            -> RetryListener.failedDelivery(attempt=1)

t=01.000s   listener attempt 2
            -> TimeoutException
            -> RetryListener.failedDelivery(attempt=2)

t=02.000s   listener attempt 3
            -> ValidationException
            -> RetryListener.failedDelivery(attempt=3)
            -> policy decides recovery

t=02.050s   recoverer handles DLT
            -> RetryListener.recovered(...)
~~~

This timeline is illustrative; a changing exception type can cause the error handler to reset backoff/attempt state depending on configuration and version. Actual timing also depends on the poll loop, broker, scheduler, and listener processing latency.

Good logs should let you reconstruct the sequence:

~~~text
recordId = orders.created/P2@105
  attempt 1 -> timeout
  attempt 2 -> timeout
  attempt 3 -> validation
  recovery -> DLT
~~~

Do not rely solely on deliveryAttempt to join logs across records, since huge numbers of records share attempt=1 or attempt=2.

## 13. Recovery failed vs. recovered

In an error handler, distinguish three outcomes:

1. The listener failed on an attempt.
2. The recoverer handled the record successfully per recoverer semantics.
3. The recoverer failed and the record may continue to be reprocessed.

Some Spring Kafka versions provide the RetryListener callback **recoveryFailed(...)** alongside **recovered(...)**. This is a valuable hook to log:

~~~text
event=kafka_recovery_failed
topic=orders.created
partition=2
offset=105
attempt=3
recovery_target=orders.created.DLT
error_category=dlt_publish
~~~

**Do not treat invoking the recoverer as proof that the DLT publish was accepted by the Kafka broker and the offset committed.** The outcome depends on DeadLetterPublishingRecoverer configuration, producer acknowledgements, send-result verification, transaction/recovery boundaries, and container error handling.

When logging recovery outcomes, record states matching what can actually be confirmed:

- recovery_started
- recovery_succeeded
- recovery_failed
- commit_pending
- commit_failed_or_unknown

Do not log dlt_published_successfully at the top of a recoverer method before the publish result is confirmed.

## 14. When does the delivery attempt reset?

An operator may observe:

~~~text
12:00:00 attempt=1
12:00:01 attempt=2
12:00:02 attempt=3

12:01:00 consumer restart

12:01:05 attempt=1
~~~

This is **not necessarily a bug**. Attempt counts in blocking retry are usually tracked in memory by the container/error handler. When a process restarts, a consumer group rebalances, or error handler state resets, an uncommitted record can be redelivered starting at attempt=1 in a fresh sequence.

Factors that make attempts discontinuous:

- Process or pod restarts.
- Partition revocation followed by assignment to another consumer.
- Error handler retry state resets.
- Record republished to another topic.
- Retry topics creating a new processing stage.
- Operators replaying from a committed offset or seeking backward.
- Custom listeners/recoverers modifying headers.

**Attempt count is not a durable global retry counter.**

If business rules require capping total processing passes across restarts, use a durable state store, retry orchestration with explicit metadata, or another bounding mechanism. Logging KafkaHeaders.DELIVERY_ATTEMPT alone is insufficient.

## 15. Comparing attempts in blocking retry vs. non-blocking retry

Spring Kafka has two common retry families:

### Blocking retry

The record is redelivered through the container/error handler, potentially after BackOff. A partition is typically affected while the record retries, depending on seek/retain/pause mechanics.

~~~text
orders.created/P2@105
    |
    +-- attempt 1
    +-- attempt 2
    +-- attempt 3
    |
    v
Success or DLT
~~~

### Non-blocking retry topics

A failed record is forwarded to a retry topic and consumed by a listener container in the retry topology when due:

~~~text
orders.created
      |
      +-- error -> orders.created-retry-1000
      |                  |
      |                  +-- error -> orders.created-retry-5000
      |                                      |
      |                                      +-- error -> DLT
      |
      v
original consumer can continue processing other records
~~~

Topic names and topology are illustrative. In a retry-topic flow, **the original record has been republished to a different topic**. Current topic/partition/offset will differ from original topic/partition/offset.

Therefore, do not assume KafkaHeaders.DELIVERY_ATTEMPT from blocking retry reflects total attempts across all retry topics.

## 16. RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS

In retry-topic infrastructure, Spring Kafka maintains separate retry metadata, including the constant **RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS** in supported versions.

~~~java
RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS
~~~

This is a **separate concept** from KafkaHeaders.DELIVERY_ATTEMPT, and how the framework attaches/reads it may vary by Spring Kafka version.

When logging an application using @RetryableTopic:

1. Distinguish attempts in **container-internal blocking retry** from attempts in the **retry-topic topology**.
2. Do not blindly add the two numbers together.
3. Do not assume both headers are always present or share the same binary encoding.
4. Track both current topic and original source metadata.
5. Use event ID/correlation ID to join hops.

Logging example:

~~~text
event=kafka_delivery_failed
current_topic=orders.created-retry-5000
current_partition=1
current_offset=92
retry_topology_stage=retry_5s
blocking_attempt=1
retry_topic_attempt=3
original_topic=orders.created
original_partition=2
original_offset=105
~~~

These fields are an illustrative application log schema; record each attempt value only when actually obtained from the framework or application-managed metadata.

## 17. Original location vs. current location

A record moving through retry topics or a DLT can have two different locations:

~~~text
Original location:
  orders.created/P2@105

Current location:
  orders.created-retry-5000/P1@92
~~~

For diagnostics:

- **Current topic/partition/offset** locates the record being processed by the current consumer.
- **Original topic/partition/offset** locates the initial source record.
- **Event ID** links business identity when a record is copied/republished.
- **Attempt** explains delivery count within a single retry context.

Spring Kafka's Dead Letter Publishing Recoverer supports original location headers such as **KafkaHeaders.DLT_ORIGINAL_TOPIC**, **KafkaHeaders.DLT_ORIGINAL_PARTITION**, and **KafkaHeaders.DLT_ORIGINAL_OFFSET** in matching DLT flows.

Do not assume every retry topic automatically has full DLT headers or every producer attaches original offsets. Inspect your actual topology and log only fields backed by available metadata.

**Current offset is never proof of how many times a record was processed.** Each republish to another topic creates a brand-new Kafka record with a new offset.

## 18. DLT and delivery attempts

A DLT typically holds records after the retry policy decides not to continue processing on the main stream.

~~~text
Original consumer:
  orders.created/P2@105
  attempts 1, 2, 3 -> fail

Recoverer:
  publishes to orders.created.DLT

DLT consumer:
  current DLT offset = 44
~~~

When a DLT consumer processes the record, the **DLT consumer's** delivery attempt may start at 1. That is the attempt within a different consumer/retry context, not an automatic continuation of attempt=3 from the original consumer.

Accordingly, log schemas should avoid an ambiguous global attempt field:

~~~text
delivery_attempt=1
delivery_attempt_scope=dlt_consumer
original_processing_attempts=3   # Only when metadata is reliable
~~~

If original attempt count cannot be durably persisted, do not infer it from the DLT offset or count of Kafka headers.

DLT triage also needs:

- Original topic/partition/offset.
- Final exception class/category.
- Recovery timestamp.
- Payload schema/version when applicable.
- Security-vetted correlation ID/event ID.
- Replay outcomes and manual replay count.

## 19. Rebalancing can create duplicate deliveries

Suppose Consumer A processes offset 105 without committing. The consumer group rebalances and the partition moves to Consumer B:

~~~text
Consumer A:
  P2@105 delivered, attempt=1
  writes to database
  offset not committed yet

Rebalance:
  P2 moves to Consumer B

Consumer B:
  re-reads P2@105
  attempt=1 in fresh retry state
~~~

Both logs show attempt=1, yet the same source record was **delivered at least twice**.

This is why you must distinguish:

1. **Delivery attempt tracked by Spring Kafka within a retry cycle**.
2. **Actual redelivery caused by consumer restart/rebalance/uncommitted offsets**.
3. **Number of times business side effects executed**.

If you need to track business execution count across ownership changes, store event IDs and idempotency state outside the listener's retry state.

Do not treat duplicate attempt=1 logs as proof the event was never retried.

## 20. Kafka transactions and delivery attempts

With consumer-initiated Kafka transactions, the listener container can group Kafka output and consumed offsets into one transaction.

~~~text
Kafka transaction T1:
  consume P2@105
  delivery attempt 1
  produce output X
  exception -> ABORT

Kafka transaction T2:
  re-consume P2@105
  delivery attempt 2 (within retry context)
  produce output X
  send offset 106 to transaction
  COMMIT
~~~

Downstream consumers using **read_committed** do not see output X from the aborted transaction.

However, the listener may have called databases/APIs outside Kafka during both attempts. Kafka transactions do not automatically roll back those side effects.

Logs should reflect both dimensions:

~~~text
delivery_attempt=2
kafka_transaction_outcome=committed
db_side_effect_status=already_applied
~~~

Never use delivery attempt as a condition to skip idempotency. Attempt=1 does not guarantee the event was never processed, and attempt=2 does not guarantee the prior pass left no database state.

For transactional listeners, error handling may use **DefaultAfterRollbackProcessor** instead of the standard DefaultErrorHandler path; verify delivery attempt support and callbacks for your version.

## 21. Batch listeners and attempt semantics

A batch listener receives multiple ConsumerRecords in a single callback:

~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "batchListenerFactory")
public void handleBatch(
        List<ConsumerRecord<String, OrderEvent>> records) {

    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }
}
~~~

When a record mid-batch fails, the framework may reprocess the entire batch or a subset depending on configuration and exception type (e.g., BatchListenerFailedException). **Do not assume every record in a batch always carries KafkaHeaders.DELIVERY_ATTEMPT identically to a record listener**.

In some Spring Kafka versions, the delivery attempt header is tied to **record listeners** and is unsupported or behaves differently for batch listeners.

Therefore, batch logging should distinguish:

- **Batch invocation number** (if tracked by the application).
- **Record offsets within the batch**.
- **Failing record index** when identifiable.
- **RetryListener batch callbacks** when supported by the framework.
- **Consumer group/assignment** at retry time.

If no reliable per-record attempt source exists in a batch, log unknown rather than fabricating numbers from the record's list index.

## 22. Deserialization failures happen before the business listener

If Kafka key or value deserialization fails, the business listener may **never be invoked**. Thus, logging attempts only inside @KafkaListener misses these errors completely.

Spring Kafka provides **ErrorHandlingDeserializer** to attach deserialization failure details into the record/headers and route the error to error handling/recovery instead of crashing the poll loop unrecoverably.

~~~text
KafkaConsumer.poll()
       |
       v
Deserializer
       |
       +-- deserialize OK -> business listener
       |
       +-- deserialize error
                   |
                   v
              error handler / recovery
                   |
                   +-- retry
                   +-- DLT
~~~

Diagnostic logs need:

~~~text
event=kafka_deserialization_failed
topic=orders.created
partition=2
offset=105
delivery_attempt=unknown_or_observed_value
error_category=deserialization
business_listener_invoked=false
~~~

Do not dump raw payload bytes into logs just to "inspect bad data" if payloads can contain PII. A DLT can store raw bytes under appropriate policies; logs only need correlation metadata and redacted error details.

When errors happen before the listener, RetryListener or framework error logging is typically a better observation point than business listener logs.

## 23. When to log attempts in the listener vs. the error handler?

| Logging point | Knows record delivered? | Knows error? | Strengths |
|---|---|---|---|
| Start of @KafkaListener | Yes | Not yet | Measures delivery start, trace context |
| Catch block in listener | Yes | Yes | Business context, business classification |
| RetryListener.failedDelivery | Yes | Yes | Attempt supplied by error handler |
| Recoverer/DLT publishing | Yes | Yes | Recovery target/outcome |
| ConsumerStoppedEvent | Not tied to 1 specific record | Has lifecycle reason | Distinguishes fencing/auth/no-offset stops |
| NonResponsiveConsumerEvent | Not necessarily tied to 1 record | Has poll liveness context | Diagnoses blocked consumer threads |

A sound logging architecture typically combines:

1. Listener start logs at DEBUG with correlation context.
2. RetryListener failedDelivery logs at WARN with error classification.
3. Recovery success/failure logs per outcome.
4. Separate consumer lifecycle logs to distinguish infrastructure failures from record failures.

You do not need to log full exception stack traces at every single point.

## 24. Recommended structured log schema

JSON log example:

~~~json
{
  "event": "kafka_delivery_failed",
  "service": "orders-service",
  "listener": "orders-created-listener",
  "consumer_group": "orders-service",
  "topic": "orders.created",
  "partition": 2,
  "offset": 105,
  "delivery_attempt": 2,
  "delivery_attempt_scope": "blocking_retry",
  "event_id": "evt-1001",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "error_category": "downstream_timeout",
  "error_type": "TimeoutException",
  "retry_decision": "retry_pending",
  "processing_duration_ms": 240,
  "outcome": "failed"
}
~~~

These fields and values are an **illustrative application log schema**; Spring Kafka does not emit this exact JSON out of the box.

Groups of fields to standardize:

| Group | Fields |
|---|---|
| Source | service, environment, listener, consumer_group |
| Kafka location | topic, partition, offset |
| Correlation | event_id, trace_id, original location when available |
| Retry | delivery_attempt, scope, retry_decision, retry_policy |
| Error | error_category, error_type, root_cause |
| Outcome | success, failed, recovered, recovery_failed |
| Performance | duration_ms, backoff_ms if actually known |

Do not emit a field like **retry_decision=retry_pending** if the callback only reports a failed delivery and it is not yet certain the policy will retry. When the final decision is unknown, use **retry_decision=unknown** or log after the decision is clear.

## 25. Do not use record offset as a business ID

Topic/partition/offset identifies a Kafka record within a topic-partition:

~~~text
orders.created/P2@105
~~~

It is helpful for debugging and locating records. However:

- An event republished to a retry topic gets a new offset.
- An event replayed from a DLT back to the source topic gets a new offset.
- One message may be processed independently by multiple consumer groups.
- A topic might be deleted and recreated, stripping old offsets of global uniqueness across history.

Therefore, also include a **stable event ID** or business idempotency key when you need to identify business operations across multiple publishes.

A correlation log can include:

~~~text
event_id=evt-1001
original_location=orders.created/P2@105
current_location=orders.created-retry-5000/P1@92
delivery_attempt=1
~~~

There is no contradiction here: same event ID, different current Kafka record and retry context.

## 26. MDC to attach context to logs automatically

SLF4J MDC attaches thread-scoped context so logs from service methods within the same listener invocation include topic/partition/offset/attempt without passing them manually to every log call.

~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "orderListenerFactory")
public void handle(ConsumerRecord<String, OrderEvent> record) {

    String attempt = DeliveryAttemptHeaders.readAttempt(record)
            .isPresent()
            ? Integer.toString(
                    DeliveryAttemptHeaders.readAttempt(record).getAsInt())
            : "unknown";

    try (MDC.MDCCloseable topic =
                 MDC.putCloseable("kafka.topic", record.topic());
         MDC.MDCCloseable partition =
                 MDC.putCloseable("kafka.partition",
                         Integer.toString(record.partition()));
         MDC.MDCCloseable offset =
                 MDC.putCloseable("kafka.offset",
                         Long.toString(record.offset()));
         MDC.MDCCloseable delivery =
                 MDC.putCloseable("kafka.delivery_attempt", attempt)) {

        orderService.process(record.value());
    }
}
~~~

This example uses **MDC.putCloseable** to clean up keys automatically after the callback. You can compute OptionalInt once and reuse it to simplify the code; the snippet focuses on illustrating lifecycle cleanup.

**Cleaning up MDC in finally or try-with-resources is operationally mandatory.** Listener containers reuse consumer threads across many records. If offset 105's MDC lingers when offset 106 runs, logs will be attributed to the wrong record.

MDC is usually ThreadLocal: if the listener spawns async tasks on another thread, context **does not automatically propagate properly**. When propagation is required, use the framework's context propagation mechanisms with clear bounds and cleanup.

## 27. MDC leaks lead to misdiagnosis

An anti-pattern:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(ConsumerRecord<String, OrderEvent> record) {
    MDC.put("kafka.offset", Long.toString(record.offset()));

    orderService.process(record.value());

    // Missing MDC.remove/clear -> context can leak to the next record.
}
~~~

If an exception happens before cleanup, the fallout is even more obvious:

~~~text
Record 105:
  MDC kafka.offset=105
  exception -> method exits

Record 106:
  MDC still kafka.offset=105
  new logs mislabeled with offset 105
~~~

This misleads operators into thinking record 105 retried repeatedly, when the logs actually came from record 106.

For delivery attempt logging, **accurate correlation context is just as important as the attempt value itself**. Always clean up MDC keys set by the listener. If underlying framework code also uses MDC, avoid calling MDC.clear() indiscriminately and wiping framework context; restore/remove only keys owned by your code.

## 28. Be careful with @Async and CompletableFuture

A listener like:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderEvent event) {
    workerPool.execute(() -> orderService.process(event));
}
~~~

can return before business work finishes. In that case:

- Delivery attempt reflects how many times the container **called the listener**, not whether the worker finished.
- If the consumer offset commits when the listener returns, the record may be marked processed before the worker finishes.
- During retries/rebalances, the same business event can execute concurrently on multiple workers.
- MDC from the consumer thread is not automatically present on worker threads.

To stay safe, use an async acknowledgment/ownership model supported by Spring Kafka, track task completion, and enforce idempotency on external side effects.

Do not paper over broken acknowledgment semantics by increasing delivery attempt logging. Logs only expose the flaw; they do not fix the semantics.

If propagating MDC to an executor, capture context, apply it in the worker, and restore/clear it after the task completes to prevent context leaks across thread pool jobs.

## 29. Correlation ID and tracing

To connect Kafka deliveries with HTTP/database operations, use a trace ID or event correlation ID:

~~~text
Kafka input:
  event_id=evt-1001
  trace_id=abc123

Listener attempt 2:
  trace_id=abc123
  delivery_attempt=2

Downstream HTTP:
  trace_id=abc123

Database operation log:
  trace_id=abc123
~~~

In a tracing system, each retry pass may start a new span. Those spans can be linked via propagated trace context or span links depending on instrumentation design.

Do not assume trace IDs always remain identical across DLT/manual replays; an operator may initiate a fresh trace. Hence you need a **stable event ID** or explicit correlation link between original and replay.

The **delivery_attempt** field can be added as a span attribute where helpful. Avoid putting record payloads, customer secrets, or full exception messages containing sensitive data into traces.

Good delivery logs let you drill down from error dashboards to the trace of a specific attempt, rather than creating a separate metric per trace ID.

## 30. Log levels and retry storms

Suppose a downstream API goes down and 5,000 records retry three times. If every attempt logs a full stack trace at ERROR:

~~~text
5,000 records
  × 3 failed attempts
= 15,000 error stack traces
~~~

If the log pipeline has bounded throughput, the incident triggers a **logging storm**, consuming resources and delaying critical logs.

A sensible policy:

| Scenario | Suggested log level | Content |
|---|---|---|
| Delivery started | DEBUG | Kafka location, attempt, correlation |
| Attempt failed with retries remaining | WARN or DEBUG depending on volume | Error category, attempt, backoff context |
| Recovery to DLT succeeded | INFO/WARN per policy | Original location, recovery target, category |
| Recovery failed | ERROR | Error class, cause, Kafka location |
| Producer fencing / severe transaction failure | ERROR | Container/transaction context |
| Normal consumer rebalance | INFO/DEBUG | Assignment lifecycle |

No single log level fits every system. The goal is enough detail to investigate without repeating the same exception stack across multiple layers.

You can use sampling or rate limiting **for success logs or repetitive error logs**, while keeping durable DLT/audit state for mandatory business cases.

## 31. How should failure counts be measured with metrics?

Delivery attempt can appear in logs and in a metric. However, never use a dynamic raw attempt count as a tag if its values are unbounded.

Counter example:

~~~java
registry.counter(
        "app.kafka.delivery.failures",
        "listener", "orders-created",
        "outcome", "retryable",
        "error_category", "downstream_timeout")
    .increment();
~~~

If you want to analyze attempt distributions, use **bounded buckets**:

~~~text
attempt_bucket = first
attempt_bucket = second
attempt_bucket = third_to_fifth
attempt_bucket = more_than_five
attempt_bucket = unknown
~~~

Or use an appropriate DistributionSummary/Timer depending on your monitoring stack and metric semantics.

**Never use event_id, record key, original offset, exception message, or trace_id as metric labels.** Those are high-cardinality values and can overload Prometheus/Micrometer.

Metrics answer aggregate trends; logs/traces help locate individual records.

## 32. Example mapping attempts into bounded buckets

~~~java
public final class AttemptBuckets {

    private AttemptBuckets() {
    }

    public static String from(Integer attempt) {
        if (attempt == null || attempt <= 0) {
            return "unknown";
        }
        if (attempt == 1) {
            return "first";
        }
        if (attempt == 2) {
            return "second";
        }
        if (attempt <= 5) {
            return "third_to_fifth";
        }
        return "more_than_five";
    }
}
~~~

Metric example:

~~~java
registry.counter(
        "app.kafka.delivery.attempts",
        "listener", "orders-created",
        "attempt_bucket", AttemptBuckets.from(deliveryAttempt),
        "outcome", "failure")
    .increment();
~~~

Here the label combinations are bounded. If an error handler resets attempts on rebalance, the metric still shows the **distribution of observed attempts**, though not the total count of business executions.

Name and document the metric clearly as counting **delivery failures per observed attempt bucket**, not counting unique records.

## 33. Log budgets and PII

Delivery logging often touches keys, headers, payloads, and error messages. These fields can carry sensitive data:

~~~text
record.key() = customer email
record.value() = address and order details
exception.message = URL containing access token
headers = authorization token
~~~

Avoid logging:

~~~java
log.error(
        "Failed: record={}, headers={}",
        record,
        record.headers(),
        exception);
~~~

without knowing what the formatter will print.

Proper design:

- Log only **topic, partition, offset, attempt**, error category, and approved correlation IDs.
- Redact/mask record keys if keys contain PII.
- Do not dump raw payloads just to debug retries.
- Do not print raw exception messages if they might contain tokens/SQL/customer data.
- Limit log length and stack trace sampling.
- Apply access controls on logs/traces matching the sensitivity of business data.

Hashing a record key does not turn it into a low-cardinality metric tag. Hashing reduces direct readability while keeping nearly the same number of distinct values.

## 34. Idempotency cannot rely on attempt=1

A dangerous anti-pattern:

~~~java
if (deliveryAttempt == 1) {
    paymentClient.charge(payment);
}
~~~

The intent may be “only charge on the first pass, do not charge on retries.” However:

1. A consumer restart can reset attempt back to 1.
2. The same business event can travel to another consumer group.
3. Retry topics maintain separate retry state.
4. Manually replayed events can start a new delivery pass.
5. Headers may be missing or modified.

Therefore **attempt is not an idempotency key**.

A better design:

~~~java
paymentClient.charge(
        payment,
        payment.eventId()); // API-supported idempotency key
~~~

Or use a database unique constraint / processed_event table to block duplicate side effects. Kafka transactions only protect Kafka outputs and consumed offsets within that transaction; databases/APIs require separate idempotency.

## 35. Distinguishing retries caused by bad data vs. infrastructure

Two records both show attempt=3, yet have very different causes:

~~~text
Record A:
  ValidationException
  invalid business payload
  attempt=3

Record B:
  TimeoutException
  database connection pool exhausted
  attempt=3
~~~

Record A should likely route to a DLT early rather than retrying heavily. Record B may recover after backoff or a circuit breaker.

Delivery logs should include an error category:

~~~text
validation
deserialization
downstream_timeout
infrastructure
transaction
authorization
unknown
~~~

Error categories must come from a finite list stable across deployments. Do not build error categories from raw exception messages.

When classification is inaccurate, attempt logs may reveal a retry pattern without explaining why the policy keeps retrying an unrecoverable error.

## 36. Resetting retry state when the exception changes

Spring Kafka error handling provides policies for resetting backoff/retry state when the exception changes, depending on version and config (e.g., **resetStateOnExceptionChange**).

Consider a record:

~~~text
Attempt 1 -> TimeoutException
Attempt 2 -> TimeoutException
Attempt 3 -> ValidationException
~~~

If the handler resets state when the exception type changes, the subsequent retry sequence may start a fresh state/backoff. Delivery attempt logs may then stop forming a clean 1,2,3,4... sequence as operators expect.

What to do:

- Log the exception category/type on every failed attempt.
- Document the retry policy/version/configuration in operational docs.
- Do not infer remaining retries solely from attempt if reset is enabled.
- Verify exception classification and recoverer behavior.
- Test scenarios where the root cause changes between retries.

**Attempt count is a signal of error-handler state**, not a simple count of total exceptions system-wide.

## 37. RetryListener can duplicate logs with listener catch blocks

Example business listener:

~~~java
try {
    orderService.process(record.value());
}
catch (RuntimeException ex) {
    log.error("Process failed", ex);
    throw ex;
}
~~~

Then DefaultErrorHandler also logs:

~~~text
RetryListener.failedDelivery -> log.warn(..., ex)
~~~

And the recoverer logs:

~~~text
DLT published / recovery -> log.error(..., ex)
~~~

One attempt can emit 2–3 identical stack traces. During an incident, log volume multiplies alongside retries.

Solution:

1. Use listener catch blocks mainly to enrich business context or translate exception types.
2. Assign attempt failure logging to RetryListener as one unified place.
3. Log full stack traces only at the error handler/recovery layer or under a sampling policy.
4. Log recovery outcome separately without re-logging the same failure as a brand-new error.
5. Use trace ID/event ID to correlate logs rather than duplicating content.

**One log per failed delivery** is far easier to investigate than three logs pointing to the same exception.

## 38. Attempt alone does not reveal backoff duration

A record showing:

~~~text
attempt=3
~~~

is not enough to know how long it waited between attempts. A policy might be:

- Fixed backoff of 1 second.
- Exponential backoff.
- Backoff with jitter.
- Retry topic with a 5-minute delay.
- Container paused due to downstream overload.

To measure latency:

~~~text
failure_time
next_delivery_time
backoff_configured
actual_wait_time
~~~

Do not record **actual_wait_ms** by copying the configured value directly when worker threads, rebalances, or broker scheduling alter actual elapsed time.

For retry topics, a message may become due yet wait in the partition because of backlog or a paused container. Distinguish **configured retry delay** from **observed retry latency**.

## 39. How to correlate attempts across logs?

An investigation query can start with:

~~~text
service = orders-service
topic = orders.created
partition = 2
offset = 105
~~~

Then sort logs by timestamp:

~~~text
12:00:00.100 attempt=1 outcome=failed error=timeout
12:00:01.200 attempt=2 outcome=failed error=timeout
12:00:02.350 attempt=3 outcome=success
~~~

If records move to retry topics, search by **event_id** or original location metadata:

~~~text
12:00:00 original orders.created/P2@105
12:00:01 retry orders.created-retry-1000/P1@92
12:00:06 retry orders.created-retry-5000/P1@115
~~~

Do not correlate solely by key when keys are non-unique or reused across multiple business events. Prefer event ID when available.

When seeing attempt drop from 3 back to 1, check timestamps for restarts, rebalances, retry topology hops, or replays before concluding the system miscounted.

## 40. Log search queries and dashboards

Query syntax varies by log backend. A conceptual query:

~~~text
event = kafka_delivery_failed
AND listener = orders-created-listener
AND delivery_attempt >= 3
AND error_category = downstream_timeout
~~~

Dashboards can display:

- Failed deliveries per minute.
- Percentage of records succeeding on attempt 1.
- Percentage of records requiring >= 2 attempts.
- Unique records reaching the DLT.
- P95 time from first attempt to recovered.
- Retry storms by listener/topic family.
- Producer fencing and consumer rebalance rates.
- Consumer lag, especially with blocking retry.

Note when computing **unique records**: failed delivery log count does not equal unique Kafka records. One record retried 10 times produces 10 failure logs yet remains one source record.

To count unique event IDs, use a log query aggregation or an appropriate state store while weighing cost and sensitive data. Do not create a Prometheus time series per event ID just to count unique records.

## 41. Logging and consumer lag

Blocking retry can stall a partition's offset progress on a single failing record:

~~~text
P2:
  offset 105 -> retrying
  offset 106 -> waiting
  offset 107 -> waiting

Consumer lag on P2 grows.
~~~

If logs show:

~~~text
topic=orders.created
partition=2
offset=105
delivery_attempt=8
error_category=timeout
~~~

operators have evidence linking the lag to the retrying record.

Conversely, growing lag with **no delivery attempt failure logs** may be caused by:

- Consumer thread blocked before reaching the listener.
- Poll/rebalance problems.
- Deserialization failures not reaching the listener.
- Low downstream throughput.
- Consumer paused.
- Transaction read_committed waiting on an open transaction.
- Logging unconfigured or dropped/sampled.

Do not assume every consumer lag spike comes from a poison record, and do not raise retries indefinitely just to avoid a DLT.

## 42. Common mistakes when using RetryListener

| Symptom | Possible cause | What to check |
|---|---|---|
| RetryListener logs nothing | Handler bean not attached to the right factory | Check containerFactory and CommonErrorHandler |
| Attempt header always missing | deliveryAttemptHeader not enabled or unsupported handler | Check ContainerProperties and version |
| Listener keeps logging attempt=1 | Process restart/rebalance or retry state reset | Cross-check consumer group/lifecycle logs |
| Attempt increments differently than listener calls | Different retry context, exception state reset, or batch handling | Check error handler semantics |
| DLT consumer sees attempt=1 | Fresh retry context | Log original/current location and scope |
| No attempt log on deserialize error | Listener was never invoked | Inspect ErrorHandlingDeserializer/error handler |
| Header decodes to negative or nonsensical integer | Wrong byte/format decoding | Check 4-byte int, ByteBuffer, and header name |
| Same failure appears three times | Duplicate logging in listener, RetryListener, and recoverer | Define error logging ownership |
| WARN volume explodes on broker outage | Retry storm / logging storm | Rate limiting, bounded retries, alerts |
| Offset commits even though listener logged error | Exception swallowed or error handler recovered normally | Check exception flow, ack/transaction policy |

Do not fix logging errors by manually altering Kafka consumer positions or committing offsets before understanding the root cause.

## 43. When exceptions are swallowed in the listener

Code:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderEvent event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Processing failed", ex);
        // Not rethrown.
    }
}
~~~

If the listener returns normally, the container may consider the record processed under the AckMode/transaction policy. **DefaultErrorHandler is not necessarily invoked** and attempts do not increment as expected.

When retries are needed:

~~~java
catch (RuntimeException ex) {
    log.warn("Processing failed; handing exception to container");
    throw ex;
}
~~~

However, not every error should be retried. For non-retryable business validation errors, the error handler can recover early via DLT. What matters is **handing the exception to the right policy** instead of logging and swallowing it.

If business logic already executed external non-Kafka side effects before throwing, the next delivery may repeat those side effects; idempotency is required.

## 44. When producer send returns a Future yet the listener returns early

KafkaTemplate.send(...) can return a CompletableFuture. An anti-pattern:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderEvent event) {
    kafkaTemplate.send("orders.normalized", transform(event));
    // Does not wait for / check send errors.
}
~~~

If the send fails after the listener returns, the container may not see the exception in time. For transactional Kafka listeners, ensure send failures/transaction errors are handled within the proper transaction boundary.

Example synchronizing so failures surface before returning:

~~~java
kafkaTemplate.send("orders.normalized", transform(event)).join();
~~~

This is a simple example, not advice to block on every single send in high-throughput pipelines. You can collect futures and await them in a controlled way.

**Delivery attempt logging only reflects container deliveries to the listener**; it does not automatically catch producer errors ignored inside asynchronous callbacks.

## 45. Recovered does not guarantee business success

When DefaultErrorHandler sends a record to a DLT, RetryListener.recovered may fire per recovery semantics.

~~~text
Record business processing -> failed
Error handler -> recovered to DLT
~~~

Logs should distinguish:

~~~text
business_outcome=failed
recovery_outcome=success
~~~

Avoid logging:

~~~text
business_outcome=success
~~~

simply because the record moved to a DLT and the listener container moved on to subsequent offsets.

A DLT stores records for analysis or replay, not as proof a business requirement was fulfilled. If an operator replays the DLT, that is a new workflow with a fresh attempt context.

## 46. Log scenario when a consumer restarts mid-retry

Timeline:

~~~text
Pod A:
  10:00:00 attempt=1 -> timeout
  10:00:01 attempt=2 -> timeout

Pod A is killed

Pod B:
  10:00:30 assignment P2
  10:00:31 attempt=1 -> success
~~~

Looking only at attempt might suggest the record never failed before. Adding pod/consumer lifecycle fields:

~~~text
instance=pod-A consumer_session=A attempt=2
instance=pod-B consumer_session=B attempt=1
~~~

alongside the same original location shows operators the record crossed multiple process lifecycles.

**Consumer session ID** here is an application-defined log field or matching metadata source, not an auto-generated Kafka header. If generating session IDs as UUIDs, keep them in logs/traces; do not use them as metric labels.

## 47. Log scenario when DLT publish fails

Timeline:

~~~text
Attempt 1 -> validation failure
Attempt 2 -> validation failure
Recovery -> publish DLT
DLT broker/serializer/ACL error
Recovery -> failed
~~~

What operators need:

~~~text
source=orders.created/P2@105
attempt=2
error_category=validation
recovery_target=orders.created.DLT
recovery_outcome=failed
recovery_error_category=kafka_publish
~~~

If DLT publishing fails, the source record must not be treated as safely recovered when operational requirements demand persisting failed records. Recoverer and error handler design must handle failures according to your version/configuration semantics.

A "sent to DLT" log emitted right before calling KafkaTemplate.send is not enough to prove the publish succeeded.

## 48. Log scenario when a transaction is fenced

A transactional producer can hit **ProducerFencedException**, such as from duplicate transactional.id across active instances or lifecycle issues.

~~~text
consumer processing attempt=1
producer transaction commit -> fenced
container stop reason=FENCED (when configured)
~~~

This is an **infrastructure/lifecycle failure**, not necessarily a bad payload.

Logs should include:

~~~text
event=kafka_transaction_failed
failure_category=producer_fenced
listener=orders-created
input=orders.created/P2@105
delivery_attempt=1
transaction_outcome=failed_or_unknown
container_action=stop
~~~

Do not infinitely retry a ProducerFencedException on a fenced producer. Perform producer/container lifecycle recovery and find why transactional IDs collided or ownership was lost.

Attempt count does not explain why fencing happened; combine transaction logs with consumer group events.

## 49. Log scenario for idle or non-responsive consumers

A consumer can go idle because a topic is empty or awaiting data. During that time, **no new deliveries** occur to increment attempts.

A consumer that fails to poll on time can emit **NonResponsiveConsumerEvent** per monitoring settings. If the listener blocks inside a database call, the listener-entry attempt log may have fired without a matching final success/failure log.

~~~text
12:00:00 delivery_started attempt=1
12:00:30 non_responsive_poll_warning
12:01:00 db_timeout
12:01:01 delivery_failed attempt=1
~~~

A solid schema combines:

- delivery_started
- delivery_failed or delivery_completed
- consumer_non_responsive
- consumer_stopped/rebalance

Do not increment attempt when idle events or non-responsive events fire. Attempt measures **deliveries to the listener**, not poll counts or monitoring alert counts.

## 50. Test: first attempt and two retries

Test against a real test Kafka broker such as **EmbeddedKafka** or **Testcontainers Kafka** to observe actual handling.

### Setup

1. Configure DefaultErrorHandler with FixedBackOff(1000, 2).
2. Enable deliveryAttemptHeader on the listener container.
3. Create a listener that intentionally fails twice and succeeds on the third pass.
4. Collect attempts in a thread-safe test list/queue.
5. Wait for the listener to finish using a CountDownLatch or timed condition.

Expected result in a model supporting record delivery headers:

~~~text
Observed attempts:
  [1, 2, 3]

Business listener invoked:
  3 times

DLT recovery:
  not invoked because attempt 3 succeeded
~~~

Do not use fixed sleeps to assume retries finished. Wait with a timeout condition and verify record identity to avoid mixing records.

## 51. Test: exhausted retries routed to DLT

1. Have the listener always throw an exception classified as retryable.
2. Configure BackOff with finite retries.
3. Assert failedDelivery callbacks carry expected attempts.
4. Assert the recoverer is invoked after retries are exhausted.
5. Assert the DLT record exists using a separate consumer.
6. Assert original location metadata.
7. Assert the listener/source group advances per the configured recovery commit semantics.

Specifically, use a DLT consumer with matching serializers/deserializers, and inspect raw payloads when inputs fail deserialization.

Do not merely assert "RetryListener.recovered was called" and assume DLT publishing succeeded across every producer/recovery setup.

## 52. Test: missing attempt header

A test should cover missing headers:

~~~text
Record lacks KafkaHeaders.DELIVERY_ATTEMPT
    |
    v
DeliveryAttemptHeaders.readAttempt(...)
    |
    v
OptionalInt.empty()
    |
    v
Log delivery_attempt=unknown
    |
    v
Business listener continues processing
~~~

If the logging helper throws NullPointerException because the header is missing, the instrumentation itself triggers retries.

Also test edge cases:

- Missing header.
- 0-byte header.
- 2-byte header.
- 4-byte header holding 0 or a negative integer.
- Multiple headers with the same key.

Instrumentation must be resilient to invalid data.

## 53. Test: restart resets attempt back to 1

1. Send a record and have the listener fail twice.
2. Close the container/process before committing the source offset.
3. Start a new consumer in the same group.
4. Observe the record being reprocessed.
5. Assert logs record the new instance/session.
6. Do not assert that attempt must continue at 3 after restart.
7. Verify idempotency of business side effects.

This test proves **deliveryAttempt is not a durable counter**.

If total-attempt caps across restarts are required, build a dedicated state store and test it rather than stretching the Spring Kafka header beyond its scope.

## 54. Test: retry topics and current location

1. Configure @RetryableTopic per supported version.
2. Send an event with a fixed event ID.
3. Intentionally fail the listener so it forwards to retry topics.
4. Capture current topic/partition/offset on each hop.
5. Capture retry-topic attempt metadata when provided by the framework.
6. If blocking retry occurs inside a hop, record blocking attempt separately.
7. Assert logs correlate via event ID/original location.
8. Verify you do not add or conflate the two attempt sources.

Log example:

~~~text
event_id=evt-1001
current_topic=orders.created-retry-1000
retry_topic_attempt=2
blocking_attempt=1
~~~

Values are illustrative; tests must reflect actual retry topic names/headers of your Spring Kafka version.

## 55. Test: batch, deserialization, and transactional listeners

Three important paths to test separately:

**Batch listener:** one record in a batch throws an error. Verify retry callbacks and how batch index is logged; do not expect per-record headers if unsupported by your version.

**Deserialization failure:** producer sends bytes violating the schema. Verify the business listener may not be invoked, while error handler/recovery still logs record location and error details.

**Transactional listener:** listener produces output and then throws an exception. Verify the transaction aborts, downstream read_committed sees no aborted output, and retries carry proper log context; do not manually commit offsets to "complete" an error.

Keep tests isolated; avoid sharing consumer groups that could pollute attempt/rebalance state across test cases.

## 56. Formula for reconciling log counts

Suppose a system processes:

~~~text
100 unique source records

80 records:
  succeed on attempt 1

15 records:
  succeed on attempt 2

5 records:
  fail all 3 attempts then recover
~~~

Total listener deliveries across an uninterrupted retry chain:

~~~text
80 × 1
15 × 2
 5 × 3
------
125 delivery invocations
~~~

Unique source records remain 100, and recovered records are 5.

If a dashboard counts **listener invocations**, it shows 125. If it counts **unique source records**, it shows 100. If it counts **DLT recoveries**, it shows 5.

Do not compare these counters directly without understanding their semantics. In particular, sampled or dropped logs can make line counts lower than actual attempts.

## 57. Incident investigation workflow using delivery attempts

When receiving an alert for "Kafka consumer lag rising" or "DLT rate rising":

1. Identify the service, listener, and consumer group.
2. Check lag by topic-partition to pinpoint the affected partition.
3. Search failed delivery logs by current topic/partition/offset.
4. Sort attempts and exception categories chronologically.
5. Check logs for consumer restarts, rebalances, or producer fencing.
6. Determine whether blocking retry or non-blocking retry topics are used.
7. If the record moved across topics, search by original location or event ID.
8. Verify DLT publish/recovery outcomes, not just recovery requests.
9. Cross-check database/API side effects since the record may have been reprocessed.
10. Decide on retry, DLT replay, schema fix, or dependency remediation.
11. After remediation, monitor consumer lag, success rate, and remaining DLT records.
12. Record in the postmortem whether retry policies were appropriate and logs had sufficient correlation.

Never use attempt count to automatically discard failing records. Those records may carry critical business events and require an auditable recovery process.

## 58. Common misconceptions

**Delivery attempt is how many times the Kafka broker delivered the record across all history.** Incorrect. It is typically the attempt within Spring Kafka's error-handler/container retry context.

**Attempt=1 proves the business event was never processed before.** Incorrect. Restarts, rebalances, and replays can start a new attempt=1.

**Attempt=3 means Kafka retried 3 times.** Incorrect under 1-based counting: normally it is one initial delivery and two retries.

**The Kafka broker sets KafkaHeaders.DELIVERY_ATTEMPT on every record automatically.** Incorrect. The header relates to Spring Kafka error-handling configuration.

**Calling setDeliveryAttemptHeader(true) is sufficient for every listener.** Not guaranteed. The handler must support it, the right container factory must be used, and batch/other paths may differ.

**The raw header is a UTF-8 string "3".** Incorrect for the 4-byte integer attempt header typically produced by the container.

**If the header is missing, just default to attempt=1.** Inappropriate when logging needs to distinguish observed values from guesses.

**RetryListener.failedDelivery always means the record will keep retrying.** Incorrect. The final failure may proceed directly to recovery.

**RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS and KafkaHeaders.DELIVERY_ATTEMPT are the same.** Incorrect. They belong to different retry mechanisms.

**A record moved to a retry topic keeps its original offset.** Incorrect. The new record on the target topic receives a new current offset.

**DLT consumer attempt=1 means the source only failed once.** Incorrect. The DLT consumer has a fresh processing context.

**Recovered means business success.** Incorrect. The record may simply have been stored in the DLT for later handling.

**Logging attempt in @KafkaListener catches all deserialization errors.** Incorrect. Failures can occur before the business listener runs.

**Kafka transactions prevent listeners from being called again.** Incorrect. They protect Kafka outputs and consumed offsets committed atomically within the transaction.

**Delivery attempt is an idempotency key.** Incorrect. Use event IDs and idempotent side effects.

**Adding event ID as a metric label is a good way to drill down.** Incorrect. Event ID has high cardinality; use logs/traces instead.

**Logging full stack traces on every retry is always good.** Incorrect. It can cause a logging storm and drive up costs significantly.

## 59. Production implementation rules

When building logging for Spring Kafka delivery attempts:

1. Clearly identify the retry model: blocking retry, non-blocking retry topic, transactional after-rollback, or custom handler.
2. Enable the delivery attempt header only on supported listener factories and paths.
3. Read attempts via appropriate @Header binding or raw Kafka headers with proper byte[] decoding.
4. Log **unknown** when the header is missing or malformed; do not fabricate attempt numbers.
5. Use RetryListener or the corresponding error-handling hook to log failedDelivery/recovery outcomes.
6. Distinguish initial delivery from retry count: attempt 3 typically equals two retries in an unbroken sequence.
7. Always log current topic/partition/offset and listener/group; add original location when records traverse retry topics/DLT.
8. Use event ID/correlation ID to join records across hops/restarts, never attempt as the join key.
9. Record attempt scope and data source so blocking attempts are not confused with retry-topic attempts.
10. Do not log full payloads, sensitive headers, or unsanitized exception messages.
11. Use MDC with try/finally/closeable and avoid context leaks between consumer threads and async workers.
12. Avoid logging the same stack trace unnecessarily across the listener, RetryListener, and recoverer.
13. Use metrics with bounded tag values for outcomes/error categories; never tag by event ID/offset.
14. Monitor consumer lag, retry storms, DLT publish outcomes, and lifecycle events alongside attempt logs.
15. Protect external side effects with idempotency; attempt counts do not prevent duplicate processing.
16. Test first delivery, multiple retries, exhausted recovery, missing headers, restarts, rebalances, retry topics, deserialization failures, and transaction aborts.

**Logging delivery attempts** is a highly effective diagnostic tool when Spring Kafka faces transient errors, poison records, and lifecycle incidents. Its value comes from **knowing what attempt measures and in what scope**, paired with Kafka location, error category, recovery outcome, and correlation IDs. Good logging reveals which record is retrying, why it is retrying, what the final outcome was, and what happened during consumer restarts or rebalances — without overloading the logging pipeline or turning delivery counts into false assumptions about business exactly-once execution.
