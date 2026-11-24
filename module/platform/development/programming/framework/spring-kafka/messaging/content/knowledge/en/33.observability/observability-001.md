# Producer and consumer logging in Spring Kafka

Logging helps Kafka stream operations answer key questions: which event was sent, which topic/partition/offset the broker acknowledged, which consumer group processed it, how processing ended, and whether errors are being retried or routed to a DLT. Useful logs need enough context to locate a record again, without exposing payloads or generating excessive log volume in high-throughput streams.

With Spring Kafka, you should combine business logging in publishers/listeners, listener container lifecycle logging, and Kafka client logging at appropriate levels. Logs do not replace metrics or distributed tracing: logs explain a specific event, metrics show trends and magnitude, and traces connect steps across multiple services.

## 1. Goals of logging in Kafka

Producers and consumers have different perspectives:

| Component | Operational questions | Important metadata |
|---|---|---|
| Producer | Which event was sent? Where was it sent? Did the broker acknowledge it? | event ID, topic, key, partition, offset, timestamp, send result |
| Consumer | Which group received the record? Did the listener succeed or fail? | event ID, group ID, topic, partition, offset, key, attempt |
| Retry handler | Is the record still retrying or have attempts been exhausted? | exception type, retry attempt, source topic/partition/offset, retry topic |
| DLT handler | Which record was sent to the DLT? | original topic/partition/offset, DLT topic, exception type |
| Container lifecycle | Did the consumer start, stop, pause, resume, or rebalance? | listener ID, group ID, client ID, partition assignment |

The goal is not to log everything. The goal is to build a log chain that can be correlated by event ID and Kafka metadata while keeping storage cost and noise under control.

## 2. Standardizing the set of log fields

Field names should be standardized across producers, consumers, and related services:

| Field | Meaning | Notes |
|---|---|---|
| eventId | Stable ID of the business event | Used for cross-service lookup and detecting duplicate processing |
| correlationId | ID linking a broader business flow | May differ from event ID |
| traceId, spanId | Distributed tracing context | Obtained from tracing instrumentation |
| service | Name of the service emitting the log | Used for centralized log filtering |
| listenerId | ID of the KafkaListener | Useful when an application has multiple listeners |
| groupId | Consumer group | Should be recorded clearly when diagnosing assignment/lag |
| topic | Relevant topic | For retry/DLT consumers, record both the current topic and original topic if available |
| partition, offset | Record position | Offset is meaningful only within a partition |
| key | Kafka record key | Log only if the key contains no sensitive data |
| attempt | Processing/retry attempt count | Distinguishes initial processing from retries |
| outcome | Outcome of send/process/recovery | Use conventional values such as success, failed, recovered |
| exceptionType | Exception class name | Do not use the message as a high-cardinality metric label |

A record is identified in Kafka logs by the combination of topic, partition, and offset. Offset 42 in partition 0 is not the same record as offset 42 in partition 1. Always preserve all three fields when looking up records.

Do not use `eventId` alone as a replacement for Kafka metadata. An event can be republished into multiple records with different offsets; metadata identifies the exact occurrence under investigation.

## 3. Logging send results from KafkaTemplate

Since Spring Kafka 3.0, `KafkaTemplate.send(...)` returns `CompletableFuture<SendResult<K,V>>`; older versions used `ListenableFuture`. A `send()` call returning a future only indicates that the producer accepted the request at the API level; broker acknowledgment or the final failure is represented when the future completes.

Example of a publisher logging the final result:

```java
@Service
public class OrderEventPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private static final String TOPIC = "orders.created.v1";

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        String eventId = event.eventId();
        String key = event.orderId();

        try {
            CompletableFuture<SendResult<String, OrderCreated>> future =
                    kafkaTemplate.send(TOPIC, key, event);

            log.debug(
                    "kafka.publish.submitted eventId={} topic={} key={}",
                    eventId, TOPIC, key);

            return future.whenComplete((result, exception) -> {
                if (exception != null) {
                    log.error(
                            "kafka.publish.failed eventId={} topic={} key={}",
                            eventId, TOPIC, key, exception);
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.info(
                        "kafka.publish.acknowledged eventId={} topic={} " +
                        "partition={} offset={} timestamp={}",
                        eventId,
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset(),
                        metadata.timestamp());
            });
        }
        catch (RuntimeException exception) {
            // Synchronous error before send() returns a future.
            log.error(
                    "kafka.publish.submit_failed eventId={} topic={} key={}",
                    eventId, TOPIC, key, exception);
            throw exception;
        }
    }
}
```

The example uses an `OrderCreated` record with `eventId()` and `orderId()` accessors. Adjust this to your application's actual model.

If a compacted topic can contain tombstones, `record.value()` may be `null`. Check the value before reading `eventId` or invoking services; log tombstones with topic, partition, offset, and key if logging the key is permitted.

Three states should be distinguished:

- submitted: the application called the send API and received a future.
- acknowledged: the future completed successfully and has `RecordMetadata`.
- failed or submit_failed: asynchronous send failed or the API threw a synchronous error.

Do not log `acknowledged` right after the `send()` line. Log it only when the future completes successfully. `send()` can also throw a synchronous error, for example if the producer is already closed or an error occurs before the request is queued for sending.

## 4. Distinguishing send success logs from transaction commits

For a regular producer, a future completing successfully indicates that the broker acknowledged the record according to the `acks` configuration. For a transactional producer, a successful send callback does not mean the transaction has committed. A record may be written inside a transaction that is later aborted.

Therefore, when using Kafka transactions:

- Log the record send callback as `record_sent_in_transaction` or an equivalent message.
- Log `transaction_committed` only after the transaction operation completes successfully.
- When a transaction aborts, log the abort result along with the transaction context and reason.

Do not name a log `published_and_committed` inside individual `send()` callbacks if the transaction has not yet committed. This leads dashboards and incident investigations to falsely conclude that consumers are guaranteed to read the record.

## 5. Logging inside @KafkaListener

Consumers need to log record metadata before or after processing. You can accept `ConsumerRecord` directly to obtain topic, partition, offset, key, timestamp, and headers:

```java
@Component
public class OrderListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderListener.class);

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orders-projection-listener",
            topics = "orders.created.v1",
            groupId = "orders-projection"
    )
    public void onOrder(ConsumerRecord<String, OrderCreated> record) {
        OrderCreated event = record.value();
        String eventId = event.eventId();

        if (eventId != null) {
            MDC.put("eventId", eventId);
        }
        try {
            log.debug(
                    "kafka.consume.started groupId={} topic={} " +
                    "partition={} offset={} key={}",
                    "orders-projection",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    record.key());

            orderService.process(event);

            log.debug(
                    "kafka.consume.processed eventId={} groupId={} " +
                    "topic={} partition={} offset={}",
                    eventId,
                    "orders-projection",
                    record.topic(),
                    record.partition(),
                    record.offset());
        }
        catch (RuntimeException exception) {
            log.error(
                    "kafka.consume.failed eventId={} groupId={} " +
                    "topic={} partition={} offset={} exceptionType={}",
                    eventId,
                    "orders-projection",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    exception.getClass().getSimpleName(),
                    exception);
            throw exception;
        }
        finally {
            if (eventId != null) {
                MDC.remove("eventId");
            }
        }
    }
}
```

The example logs `started` and `processed` at DEBUG to avoid writing two INFO lines for every record under high throughput. Error logs with stack traces are recorded at the listener boundary; if the error handler also logs the same exception at ERROR, choose one place to own the stack trace to avoid duplicate logs.

Do not catch an exception and ignore it. When a listener requires retry, the exception must propagate to the container/error handler according to the configured policy. If code catches the exception and does not rethrow it, Spring Kafka may treat the listener as having completed normally and handle offsets according to the configured `AckMode`.

## 6. A processed log does not mean the offset was committed

This is a very important point when reading consumer logs.

A `kafka.consume.processed` line only indicates that the listener method finished its business processing without throwing an exception. It does not by itself prove that the offset was committed to the broker.

For example:

1. The listener updates the database successfully.
2. The listener writes a `processed` log.
3. The JVM stops before the offset is committed.
4. The consumer restarts and receives the record again.
5. The same event may produce another `processed` log line.

Therefore:

- Use `processed` for the processing outcome at the listener layer.
- Log `offset_committed` only when there is evidence from a callback/event matching the actual `AckMode` and commit strategy.
- Do not infer commit success solely from a log at the end of the method.
- Design idempotent consumers to tolerate redelivery.

With `AckMode.RECORD`, `BATCH`, `MANUAL`, or `MANUAL_IMMEDIATE`, commit timing differs. Logging must reflect the actual configuration rather than assigning one generic commit meaning to every listener.

## 7. Event ID and correlation ID

An event ID should be generated where the event originates and preserved across application-level retries or replays. A correlation ID can link multiple events in a single business workflow; a trace ID links spans within a distributed trace.

Example:

```json
{
  "eventId": "evt-2026-000184",
  "correlationId": "order-flow-42",
  "orderId": "order-42",
  "eventType": "OrderCreated"
}
```

These IDs serve different roles:

| ID | Purpose |
|---|---|
| eventId | Identifies a single business event |
| correlationId | Links multiple steps or events in a workflow |
| traceId | Links a distributed trace |
| spanId | Identifies an operation within a trace |

Do not use email addresses, phone numbers, account numbers, or tokens as correlation IDs. Choose random/opaque IDs that contain no personal data.

If a producer resends the same event during a retry, keep the same `eventId`. If creating a new business event, generate a new ID. This distinguishes an application resend from two distinct events with identical payloads.

## 8. Using MDC to attach context to every log line

MDC (Mapped Diagnostic Context) lets you attach fields such as `eventId`, `correlationId`, and `traceId` to logs without passing them into every logger statement.

Example:

```java
if (event.eventId() != null) {
    MDC.put("eventId", event.eventId());
}
if (event.correlationId() != null) {
    MDC.put("correlationId", event.correlationId());
}
try {
    orderService.process(event);
}
finally {
    if (event.eventId() != null) {
        MDC.remove("eventId");
    }
    if (event.correlationId() != null) {
        MDC.remove("correlationId");
    }
}
```

MDC must be cleared in `finally`. Kafka listeners typically run on reused threads; if not cleared, the next event may mistakenly inherit the previous record's `eventId` or `correlationId`. Similarly, `CompletableFuture` callbacks from the Kafka producer execute on the producer callback thread; MDC from the thread calling `KafkaTemplate.send()` is not automatically propagated there. If you need trace/event context in the callback, capture the context at send time, then restore and clean it up in the callback via a controlled propagation mechanism.

If a listener offloads processing to an executor or `CompletableFuture`, MDC is not guaranteed to propagate automatically to another thread. Use a context propagation mechanism/`TaskDecorator` or capture and restore context at the executor boundary. Do not copy MDC while forgetting to restore the target thread's previous context.

For applications using Micrometer Tracing or OpenTelemetry, let the instrumentation manage trace context and bridge it to MDC. Avoid inventing fake trace IDs or manually parsing arbitrary headers when a tracing library is already present.

## 9. Reading correlation metadata from Kafka headers

Headers can carry `event-id`, `correlation-id`, or W3C trace context. Example of reading a header:

```java
Header header = record.headers().lastHeader("event-id");
String headerEventId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);
```

If the payload already includes an event ID, standardize on a canonical source of truth. Do not silently use the payload ID on the producer while using the header ID on the consumer if the two values could diverge.

Headers may come from external producers, so treat them as untrusted input:

- Validate length and format.
- Strip newlines/control characters before logging.
- Do not log all headers because they may contain tokens or private data.
- Do not use client-supplied headers to make authorization decisions.

Trace context should be propagated using the W3C standard through compatible tracing instrumentation, rather than inventing an arbitrary custom header and treating it as full distributed tracing.

## 10. Configuring logging levels for Spring Kafka

Loggers can be tuned via `application.yml`:

```yaml
logging:
  level:
    root: INFO
    com.example.messaging: INFO
    org.springframework.kafka: INFO
    org.apache.kafka: WARN
```

Replace `com.example.messaging` with your application's package. A reasonable baseline is:

- Application publisher/listener: INFO for important events, DEBUG for each successful record.
- `org.springframework.kafka`: INFO to observe lifecycle and configuration; temporarily raise to DEBUG when investigating.
- `org.apache.kafka`: WARN in production unless investigating a specific client issue.

Do not enable TRACE for all of `org.apache.kafka` or `org.springframework.kafka` long-term in production. Overly verbose client logs can grow storage rapidly and expose internal metadata.

When temporarily enabling DEBUG:

1. Limit to the specific package/class under investigation.
2. Set a clear time window for leaving it enabled.
3. Monitor log volume and latency.
4. Disable it again once sufficient evidence is collected.

## 11. Including MDC in the console pattern

With Logback, Spring Boot lets you customize the console pattern:

```yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] traceId=%X{traceId:-} eventId=%X{eventId:-} %logger{36} - %msg%n"
```

When MDC has `eventId`, logs display that field on every line. When absent, the pattern falls back to an empty default value.

In production systems, it is usually better to emit logs in JSON format with discrete fields instead of relying solely on text strings. The log platform can filter by `eventId`, `topic`, `partition`, `offset`, `groupId`, and `traceId` without complex regexes.

## 12. Structured logging

Structured logging helps centralized log systems parse fields reliably. A log record can look like this:

```json
{
  "timestamp": "2026-11-17T09:30:12.420Z",
  "level": "INFO",
  "service": "order-service",
  "event": "kafka.publish.acknowledged",
  "eventId": "evt-2026-000184",
  "topic": "orders.created.v1",
  "partition": 2,
  "offset": 98124,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Field names should be consistent across services. Do not log `topicName` in one place, `destination` in another, and `kafkaTopic` elsewhere if all represent the current topic.

If using a JSON encoder for Logback, configure the encoder and dependencies according to the project's logging stack. Do not serialize entire message objects into JSON logs; structured logging should contain only a selected field allowlist.

## 13. Choosing log levels by severity

| Level | Usage in Kafka messaging | Examples |
|---|---|---|
| ERROR | Failed operation requiring investigation or intervention | Final publish failure, DLT publish failure, unrecoverable listener error |
| WARN | Abnormal situation where the system can continue | Retry attempt, abnormal rebalance, consumer approaching timeout |
| INFO | Important operational event occurring infrequently | Listener start/stop, transaction commit, consumer group configuration |
| DEBUG | Per-record or per-attempt processing details | Consume start/success, full metadata |
| TRACE | Very deep protocol/client details | Enable only short-term during targeted investigation |

Do not log every record at INFO if a topic receives thousands or millions of records per minute. You can use DEBUG for record-level logs, INFO for periodic summaries, and ERROR for final failures.

## 14. Logging during retries and error handling

A record can be delivered multiple times due to blocking retry, non-blocking retry, rebalance, or crashing before commit. Therefore, multiple log lines for the same event ID do not automatically mean the producer published a duplicate.

When logging retries, include:

- `eventId`.
- Current topic, partition, and offset.
- Original topic if processing a retry/DLT record.
- Exception class.
- Current attempt and attempt limit if available.
- Retry destination or backoff if the system provides metadata.

Example message:

```text
WARN kafka.consume.retry eventId=evt-2026-000184
     topic=orders-retry-1000 partition=1 offset=72
     originalTopic=orders.created.v1
     attempt=2 exceptionType=InventoryUnavailableException
```

Do not log the full stack trace on every attempt if transient errors occur at high frequency. You can log attempts at WARN/DEBUG and only record the full stack trace when retries are exhausted or an unexpected error occurs. Ensure the final exception details are not lost.

If the listener logs an exception and rethrows it, the error handler may also log the same error. Choose one layer to own the final stack trace log: the listener boundary or the error handler/recoverer. Other layers should log only metadata at DEBUG if needed.

## 15. Logging when sending a record to a DLT

The DLT is the terminal point of an error-handling branch, so logs need enough information to operate replays:

| Field | Purpose |
|---|---|
| eventId | Look up the business event |
| originalTopic | Source topic |
| originalPartition, originalOffset | Original record position |
| dltTopic, dltPartition, dltOffset | Record position after DLT publish if available |
| exceptionType | Error category |
| attempts | Number of processing attempts performed |
| recoveryOutcome | Whether the DLT publish succeeded or failed |

Log `dlt.published` only after the recoverer confirms the publish succeeded. If DLT publishing fails, log the recovery error and preserve the configured error-handling mechanism; do not log as if the record were safely stored.

Do not write payloads or exception messages containing sensitive data into DLT logs. Stack traces, SQL messages, and HTTP responses can contain input data or credentials.

## 16. Logging in batch listeners

For batch listeners, logging a single summary line per batch is usually more efficient than logging every record at INFO:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-batch",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    if (records.isEmpty()) {
        return;
    }

    ConsumerRecord<String, OrderCreated> first = records.get(0);
    long partitionCount = records.stream()
            .map(ConsumerRecord::partition)
            .distinct()
            .count();

    log.info(
            "kafka.consume.batch.started groupId={} topic={} " +
            "recordCount={} partitionCount={} firstPartition={}",
            "orders-batch",
            first.topic(),
            records.size(),
            partitionCount,
            first.partition());

    orderService.processBatch(
            records.stream().map(ConsumerRecord::value).toList());

    log.info(
            "kafka.consume.batch.processed groupId={} topic={} recordCount={}",
            "orders-batch",
            first.topic(),
            records.size());
}
```

The example logs the number of partitions present in the batch and metadata of the first record. If you need to log offset ranges, group by topic-partition first; a single poll batch can contain records from multiple partitions, and offsets are not necessarily contiguous.

If a batch contains a failing record, also log the position of the offending record according to the listener/error handler semantics. Avoid logging the entire list of payloads.

## 17. Logging consumer lifecycle and rebalances

Business logs alone cannot explain why a consumer stopped receiving records. You need to monitor container lifecycle and consumer group events:

- Listener/container started and stopped.
- Consumer paused and resumed.
- Partition assignment and revocation.
- Rebalance started/ended.
- Consumer failing to poll or not responding in time.
- Authentication, authorization, or broker connectivity failures.

Spring Kafka emits application events for several lifecycle changes, such as `ConsumerPausedEvent`, `ConsumerResumedEvent`, `ListenerContainerIdleEvent`, and `NonResponsiveConsumerEvent`. You can use `@EventListener` to log the listener ID, container ID, and related details; check the event API of your Spring Kafka version before accessing specific properties.

When partitions are revoked, log the previous assignment and the reason if available. When reassigned, log the new partition list. This helps correlate redeliveries with rebalances instead of mistakenly concluding the producer sent duplicates.

Do not log every successful poll at INFO. Use lifecycle events, rebalance callbacks, and consumer metrics for visibility without scaling log volume with poll frequency.

## 18. Distinguishing logging, metrics, and tracing

These three signals complement one another:

| Signal | Answers | Example |
|---|---|---|
| Logs | What happened to a specific record? | Event evt-1001 failed at offset 42 due to timeout |
| Metrics | How frequently or severely is an issue occurring? | Retry rate rising, consumer lag growing, publish latency p99 |
| Traces | What path did a request take across services? | API → order service → Kafka publish → inventory consumer |

Do not create metric labels with `event ID`, `order ID`, or `offset`, as cardinality will grow unboundedly. Use dimensions with a bounded set of values such as `service`, `topic`, `result`, `exception family`, or `consumer group` as planned.

Logs can contain specific IDs for lookup. Metrics should be aggregated. Traces should show relationships between operations without containing sensitive payloads.

## 19. Logging must not expose sensitive data

Do not log entire events or all Kafka headers by default. Payloads can contain emails, addresses, account numbers, tokens, payment information, or personal data.

Apply these practices:

- Log event ID, topic, partition, offset, and outcome; add business keys only if permitted.
- Use an allowlist for fields permitted in logs.
- Mask or tokenize data that must be partially displayed.
- Never log passwords, SASL JAAS configs, access tokens, cookies, private keys, or secrets.
- Redact exception messages if they might contain request/response bodies.
- Restrict log read permissions and log platform retention.
- Sanitize user-controlled values to prevent log injection.

Masking example:

```java
String maskedEmail = email == null
        ? null
        : email.replaceAll("(^.).*(@.*$)", "$1***$2");

log.info("customer.contact eventId={} email={}", eventId, maskedEmail);
```

Masking must comply with policy and must not be treated as anonymization. If an email is not needed for operations, it is better not to log it at all.

## 20. Avoiding log injection and uncontrolled log volume

Record keys, headers, and payload fields can be sent by external systems. Writing strings containing newlines or control characters directly lets an attacker forge multiple log lines or disrupt queries.

Validate/sanitize untrusted values before logging:

- Limit length.
- Strip CR/LF and unnecessary control characters.
- Do not concatenate log strings with arbitrary user data.
- Use parameterized logging (`{}`) to avoid unsafe formatting.
- Do not log large or binary payloads.

For high-throughput topics, control volume with DEBUG, sampling, or summary logs. Do not apply sampling to audit events that must be retained; auditing requires a dedicated pipeline and retention policy.

## 21. Testing logging

Logging can be tested at both unit and integration levels:

1. Producer logs `acknowledged` only after the future completes successfully.
2. Producer logs `failed` when the future completes exceptionally.
3. Producer logs `submit_failed` when the API throws a synchronous error.
4. Consumer logs the correct topic, partition, offset, group ID, and event ID.
5. Consumer exceptions propagate to the error handler rather than being swallowed.
6. MDC is cleared after the listener finishes or throws an exception.
7. Logs do not contain payloads, passwords, tokens, or forbidden fields.
8. Retry logs distinguish the original topic from the current retry topic.
9. DLT logs report recovery success only after publish is confirmed.
10. Transaction logs distinguish records sent in a transaction from transaction commits.

You can use Logback `ListAppender` or output capture to verify messages/structured fields. For integration tests, use a test broker to verify producer and consumer metadata. Do not assert entire stack traces or absolute timestamps because they vary at runtime.

## 22. Common pitfalls

**Logging send() success immediately after the API call:** the future has not completed yet; change the log to `submitted` and log `acknowledged` only inside the success callback.

**Consumer logs processed yet the record is redelivered:** listener completion does not mean the offset was committed. Check `AckMode`, commit timing, and crash windows.

**Multiple logs share the same event ID:** may be caused by retries, redelivery, or application resend. Cross-check topic/partition/offset and attempt before concluding duplicates.

**MDC from a previous record appears on the next record:** missing `MDC.remove()` in `finally` or context not properly restored on an executor.

**Logs contain payloads or tokens:** replace object logging with a metadata allowlist; redaction must also apply to exceptions/APM.

**Every retry writes multiple stack traces:** multiple layers are logging the same exception. Pick one layer to own the final stack trace and reduce logging in the others.

**Not knowing which retry topic a record came from:** log the current topic alongside the original topic/partition/offset when metadata is available.

**Unable to locate a record by offset:** logging only the offset without topic and partition. Always log the full triple.

**Enabling DEBUG for the entire Kafka client in production:** log volume spikes rapidly. Enable only the necessary loggers during an investigation window.

**Using event ID as a metric label:** unbounded cardinality growth. Keep IDs in logs/traces and use low-cardinality metric dimensions.

## 23. Production checklist

- Producers have clear `submitted`, `acknowledged`, and `failed` logs.
- Consumers log event ID, group ID, topic, partition, offset, and processing outcome.
- Business processing logs are distinguished from offset commits.
- Transactional sends are distinguished from transaction commits.
- Event IDs and correlation IDs are stable across services.
- MDC is set and cleared in `finally`; async contexts have explicit propagation.
- Retry and DLT logs include attempt, exception type, and original record location.
- Listener lifecycle, pause/resume, and rebalances are observed.
- Log levels do not produce excessive record-level INFO volume.
- Structured fields follow consistent naming.
- Payloads, secrets, PII, and sensitive headers are not logged outside policy.
- User-controlled values are sanitized to prevent log injection.
- Log retention, access control, and auditing match data requirements.
- Metrics and traces complement logs rather than replacing them.
- Tests cover success, failure, retry, DLT, MDC cleanup, and redaction.

Good producer and consumer logging must connect business events with their Kafka position and processing outcome. Use event IDs together with topic/partition/offset, log send results after the future completes, log listener outcomes accurately with commit semantics, and always clear MDC. Combine logs with metrics and traces while restricting payloads/secrets in logs so the system remains both easy to debug and safe to operate.

## References

- [Spring for Apache Kafka – Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring for Apache Kafka – Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Boot – Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [SLF4J – Manual](https://www.slf4j.org/manual.html)
