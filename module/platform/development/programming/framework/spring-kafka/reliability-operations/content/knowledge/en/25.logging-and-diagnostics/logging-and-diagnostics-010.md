# Structured logging in Spring Kafka

In a production Spring Kafka system, logs must answer: **which record did the consumer process, which listener handled it, where did processing happen, what was the outcome, and if it failed, how was the record retried or routed to a DLT?** A bare log line saying “Processing failed” is not enough to investigate when millions of records are processed concurrently.

**Structured logging** writes logs as clearly typed fields, commonly JSON. Instead of embedding all details inside a free-form string, each log event carries fields such as timestamp, level, service, listener ID, topic, partition, offset, event ID, trace ID, outcome, and exception type. Log backends can filter, group, search, and correlate these fields without re-parsing prose.

In Spring Kafka, structured logging should be designed around real operational boundaries: consumer polls, listener invocations, database/API side effects, retry/error handlers, DLT publishers, and DLT consumers. **Kafka record metadata, business correlation IDs, and tracing contexts are three distinct categories of data**; log each in its proper role without conflating them.

This lesson explains how to configure JSON logging, use SLF4J key-value pairs and MDC, manage context across consumer threads, log retries/DLTs, propagate context across executors, protect sensitive data, control log volume, and pair logs with metrics/traces.

## 1. Why is structured logging necessary?

Suppose hundreds of listener containers write plain text logs:

~~~text
Processing order failed
Retrying message
Consumer stopped
Dead letter published
Processing order failed
~~~

These lines fail to tell:

- Which listener threw the error?
- What were the record's topic, partition, and offset?
- Do two error lines refer to the same event or two different events?
- How many times has the record retried?
- Was the exception a validation or database failure?
- Did the DLT publish actually succeed or was it only requested?
- Which trace corresponds to this execution?
- Which pod/instance hosted the consumer?

Structured logging turns each log event into an object with fields:

~~~json
{
  "timestamp": "2026-11-15T10:21:30.123Z",
  "level": "ERROR",
  "service": "order-service",
  "logger": "OrderEventListener",
  "message": "Kafka record processing failed",
  "listener_id": "ordersListener",
  "consumer_group": "orders-service",
  "kafka_topic": "orders.events",
  "kafka_partition": 2,
  "kafka_offset": 105,
  "event_id": "evt-100",
  "event_type": "OrderCreated",
  "outcome": "failure",
  "exception_type": "DatabaseTimeoutException",
  "traceId": "7c2a..."
}
~~~

This is an illustrative example; real schemas should be standardized across the service. From these fields, log backends can find all failures on partition 2, group by listener, or jump from a record to its trace.

Structured logging is especially valuable when investigating:

- Growing consumer lag where it is unclear which listener is slow.
- A partition repeatedly hitting a poison pill.
- Rising retries after database saturation.
- Sudden spikes in DLT ingress.
- Events reprocessed multiple times after a rebalance.
- One pod failing while sibling pods remain healthy.
- Traces dropped by sampling or broken at async boundaries.

## 2. How do structured logs differ from plain text logs?

| Aspect | Text log | Structured log |
|---|---|---|
| Content | A free-form sentence | An object with fields |
| Searching by topic | Text parsing or regex | Filter by kafka_topic |
| Finding offsets | Must read the sentence | Filter by kafka_offset |
| Grouping by exception | Parse exception names | Group by exception_type |
| Linking traces | String search inside message | Filter by traceId/spanId |
| Schema evolution | Easily drifts into inconsistent formats | Governed field contracts |
| Log backend processing | Requires text parsing | Indexes fields directly |
| Risk | Changing wording breaks queries | Schema drift if field names are ungoverned |

Structured logging does not strictly require JSON, though JSON is standard for log shipping. Emit each event as a single-line JSON object, and encode stack traces safely in a dedicated field.

Do not cram everything into one message field and call it structured logging. Keep messages concise and place filterable attributes into separate fields.

## 3. Recommended fields for Kafka record processing

A practical log schema groups fields as follows:

| Group | Typical fields | Purpose |
|---|---|---|
| Runtime | timestamp, level, service, environment, version, instance | Identify app and deployment |
| Listener | listener_id, consumer_group, client_id | Identify handling consumer |
| Kafka source | kafka_topic, kafka_partition, kafka_offset | Source record coordinates |
| Business | event_id, event_type, aggregate_id | Identify logical event |
| Execution | attempt, outcome, duration_ms | Track processing pass |
| Error | exception_type, error_category, stack_trace | Diagnose failures |
| Tracing | traceId, spanId | Link to distributed trace |
| Recovery | recovery_action, destination_topic | Track retry/DLT |
| DLT origin | original_topic, original_partition, original_offset | Trace back to source record |

Not every log event requires all fields. A “consumer started” log has no record offset; a DLT publish log needs both source and destination coordinates when known.

Use consistent field names across services. For instance, avoid having Service A use topic, Service B use kafkaTopic, and Service C use sourceTopic for the same concept.

## 4. Distinguishing event ID, Kafka coordinates, and trace ID

Three identifiers are frequently mixed up:

**Event ID** is the logical event identifier defined by the business contract. It should remain stable across retries, redeliveries, DLTs, and replays when they represent the same event.

**Kafka coordinates** consist of topic, partition, and offset. This tuple pinpoints a specific record within a topic/partition's Kafka log. When a record is published to a retry topic or DLT, the destination gets new topic/partition/offset values; keep source coordinates separate.

**Trace ID** identifies a distributed trace in the tracing system. An event may be reprocessed under a new trace, replayed hours later, or lack a trace due to sampling. Trace ID is not a business event ID and should not serve as an idempotency key.

~~~text
Logical event:
  event_id = evt-100

Source record:
  topic = orders.events
  partition = 2
  offset = 105

DLT record:
  topic = orders.events.DLT
  partition = 0
  offset = 19

Tracing:
  traceId = 7c2a...
  spanId  = 31af...
~~~

When a DLT record is replayed, it may get new destination coordinates and a fresh trace context. Event ID paired with source coordinates links its history across runs.

If a business event has no eventId, you can use source topic/partition/offset as a correlation reference for that specific record. Never assume source coordinates remain unique once the record is copied across other topics.

## 5. Configuring JSON logging with Logback

A common Spring Boot setup pairs Logback with **logstash-logback-encoder**. This library provides encoders generating JSON fields from logging events, MDC, SLF4J key-value pairs, and exceptions.

Illustrative Maven dependency:

~~~xml
<dependency>
    <groupId>net.logstash.logback</groupId>
    <artifactId>logstash-logback-encoder</artifactId>
    <version>8.1</version>
</dependency>
~~~

Choose a version compatible with your project's Java, Logback, and Spring Boot versions; you do not have to use the exact version number shown.

Minimal Logback configuration:

~~~xml
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">

        <encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
            <providers>
                <timestamp/>
                <logLevel/>
                <loggerName/>
                <threadName/>
                <message/>
                <mdc/>
                <keyValuePairs/>
                <stackTrace/>
            </providers>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
~~~

Meaning of these providers:

- timestamp: log timestamp.
- logLevel: DEBUG, INFO, WARN, ERROR.
- loggerName: emitting class/package.
- threadName: current thread.
- message: short log message.
- mdc: fields from Mapped Diagnostic Context.
- keyValuePairs: fields added via SLF4J fluent logging.
- stackTrace: exception stack trace if present.

Verify provider names and encoder config against your actual logstash-logback-encoder version. If using Spring Boot's built-in structured logging or another logging backend, schema/output setup differs while field principles remain the same.

Sample JSON log:

~~~json
{
  "@timestamp": "2026-11-15T10:21:30.123Z",
  "level": "INFO",
  "logger_name": "com.example.orders.OrderEventListener",
  "thread_name": "org.springframework.kafka.KafkaListenerEndpointContainer#0-0-C-1",
  "message": "Kafka record processing completed",
  "listener_id": "ordersListener",
  "consumer_group": "orders-service",
  "kafka_topic": "orders.events",
  "kafka_partition": "2",
  "kafka_offset": "105",
  "event_id": "evt-100",
  "outcome": "success"
}
~~~

Some encoders serialize MDC values as strings, so partition and offset may appear as strings. When numeric types are needed in the log backend, use typed structured key-value fields or a parsing pipeline with an explicit schema.

## 6. Using SLF4J key-value pairs instead of string concatenation

With SLF4J 2, the fluent logging API attaches key-value pairs directly to a logging event:

~~~java
log.atInfo()
        .addKeyValue("listener_id", "ordersListener")
        .addKeyValue("consumer_group", "orders-service")
        .addKeyValue("kafka_topic", record.topic())
        .addKeyValue("kafka_partition", record.partition())
        .addKeyValue("kafka_offset", record.offset())
        .addKeyValue("outcome", "started")
        .log("Kafka record processing started");
~~~

The log message stays brief while encoders serialize fields separately. Error example:

~~~java
log.atError()
        .addKeyValue("listener_id", "ordersListener")
        .addKeyValue("kafka_topic", record.topic())
        .addKeyValue("kafka_partition", record.partition())
        .addKeyValue("kafka_offset", record.offset())
        .addKeyValue("outcome", "failure")
        .setCause(exception)
        .log("Kafka record processing failed");
~~~

Prerequisite: the application needs SLF4J 2.x and an encoder supporting key-value pairs. Spring Boot dependency management usually selects a compatible SLF4J; avoid overriding SLF4J API or Logback with mismatched versions.

Approach to avoid:

~~~java
log.info(
        "Processing failed topic=" + record.topic()
        + " partition=" + record.partition()
        + " offset=" + record.offset()
);
~~~

This remains a plain text message that the log backend must parse to extract fields. Moreover, string concatenation allocates strings/objects even when that log level is disabled, depending on how it is written.

## 7. Using MDC to attach context across multiple log lines

**Mapped Diagnostic Context (MDC)** is a map attached to the thread's execution context, used by logging frameworks to attach fields automatically to every log event.

For example, while processing a record, MDC might hold:

~~~text
listener_id = ordersListener
consumer_group = orders-service
kafka_topic = orders.events
kafka_partition = 2
kafka_offset = 105
event_id = evt-100
~~~

Once MDC is set, loggers inside services invoked synchronously on the same thread emit those fields without passing parameters into every log statement.

~~~text
Kafka listener thread
      |
      +--> MDC set from ConsumerRecord
      |
      +--> OrderListener log
      |
      +--> OrderService log
      |
      +--> Repository adapter log
      |
      +--> MDC restore/clear
~~~

MDC is convenient yet requires careful lifecycle management. Kafka listener threads are reused across many records. If context is not cleared or restored after each record, the next event's logs can carry the previous event's topic, offset, or eventId.

## 8. MDC must be cleaned up in finally

A simple helper example:

~~~java
public final class KafkaMdc {

    private KafkaMdc() {
    }

    public static Map<String, String> snapshot() {
        Map<String, String> values = new HashMap<>();

        Map<String, String> previous =
                MDC.getCopyOfContextMap();

        if (previous != null) {
            values.putAll(previous);
        }

        return values;
    }

    public static void setRecordContext(
            ConsumerRecord<?, ?> record,
            String listenerId,
            String groupId) {

        MDC.put("listener_id", listenerId);
        MDC.put("consumer_group", groupId);
        MDC.put("kafka_topic", record.topic());
        MDC.put("kafka_partition",
                Integer.toString(record.partition()));
        MDC.put("kafka_offset",
                Long.toString(record.offset()));
    }

    public static void restore(Map<String, String> previous) {
        if (previous == null || previous.isEmpty()) {
            MDC.clear();
        }
        else {
            MDC.setContextMap(previous);
        }
    }
}
~~~

Usage in a listener:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service"
)
public void handle(ConsumerRecord<String, OrderCreated> record) {

    Map<String, String> previous = KafkaMdc.snapshot();

    try {
        KafkaMdc.setRecordContext(
                record,
                "ordersListener",
                "orders-service"
        );

        log.atInfo()
                .addKeyValue("outcome", "started")
                .log("Kafka record processing started");

        orderService.process(record.value());

        log.atInfo()
                .addKeyValue("outcome", "success")
                .log("Kafka record processing completed");
    }
    catch (RuntimeException exception) {
        log.atError()
                .addKeyValue("outcome", "failure")
                .setCause(exception)
                .log("Kafka record processing failed");

        throw exception;
    }
    finally {
        KafkaMdc.restore(previous);
    }
}
~~~

Here snapshot preserves any context already present before the listener started. finally restores that context instead of clearing unconditionally, which helps when an outer context exists.

If the code has no nested contexts and prior MDC is always empty, MDC.clear() in finally also works. The core rule is **never let record context leak to the next execution**.

Never store the entire ConsumerRecord or payload in MDC. MDC should hold only short, normalized strings needed for log correlation.

## 9. Adding event ID safely to MDC

Event ID helps track a logical event through retries and DLTs. It can be read from the payload or headers per business contract.

Header helper example:

~~~java
private static String eventIdFromHeader(
        ConsumerRecord<?, ?> record) {

    Header header =
            record.headers().lastHeader("event-id");

    if (header == null || header.value() == null) {
        return "unknown";
    }

    String value = new String(
            header.value(),
            StandardCharsets.UTF_8
    );

    if (value.isBlank() || value.length() > 128) {
        return "invalid";
    }

    return value;
}
~~~

Then:

~~~java
MDC.put("event_id", eventIdFromHeader(record));
~~~

Bounding length prevents malformed headers from bloating logs. If eventId could contain PII, do not log raw values; use an observability-safe identifier or mask per policy.

If the record lacks an event ID, log source coordinates such as topic/partition/offset to locate it. Do not mint a fresh random ID on every retry if you want to correlate the same logical event across attempts.

Event ID can have high cardinality, yet **structured logs** can store it for search. Never promote that same eventId into a Micrometer metric tag.

## 10. MDC and Micrometer Tracing

When Spring Boot is configured with Micrometer Tracing, logging integration can place traceId and spanId into MDC or correlation fields per your stack's conventions.

A log entry may contain:

~~~json
{
  "message": "Order database update failed",
  "traceId": "7c2a9f...",
  "spanId": "31af...",
  "event_id": "evt-100",
  "kafka_topic": "orders.events",
  "kafka_partition": "2",
  "kafka_offset": "105"
}
~~~

This lets operators:

1. Search logs by eventId.
2. Copy traceId from the log.
3. Open the trace in the tracing backend.
4. Inspect producer, consumer, database, and downstream spans.
5. Pivot back to logs by traceId or spanId.

**MDC traceId does not create distributed traces by itself.** It only renders current context in logs. To propagate traces across Kafka, you need Observation/tracing instrumentation and propagators injecting/extracting headers properly.

Never mint a random traceId inside a listener, write it to MDC, and call it distributed tracing. Without a tracing system, use a business correlation ID and name it accurately to avoid confusion.

## 11. Structured logging in listeners: start, end, and error

A listener does not have to log INFO at every step for every record. At high throughput, per-record INFO logging creates huge log volume.

A common policy:

- DEBUG: record received or routine processing details.
- INFO: significant business state changes or aggregate summaries.
- WARN: retries, recoverable failures, or anomalies needing attention.
- ERROR: unprocessable records, failed recovery, or critical system failures.

Example:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service"
)
public void handle(ConsumerRecord<String, OrderCreated> record) {

    Map<String, String> previous = MDC.getCopyOfContextMap();

    try {
        KafkaMdc.setRecordContext(
                record,
                "ordersListener",
                "orders-service"
        );

        log.atDebug()
                .addKeyValue("event_type", "OrderCreated")
                .log("Kafka record received");

        orderService.process(record.value());

        log.atDebug()
                .addKeyValue("outcome", "success")
                .log("Kafka record processing completed");
    }
    catch (RuntimeException exception) {
        log.atError()
                .addKeyValue("outcome", "failure")
                .addKeyValue(
                        "exception_type",
                        exception.getClass().getSimpleName()
                )
                .setCause(exception)
                .log("Kafka record processing failed");

        throw exception;
    }
    finally {
        KafkaMdc.restore(previous);
    }
}
~~~

This snippet illustrates a synchronous record listener. If the listener uses async completion or batch processing, context and completion log timing must be designed separately.

**Never catch an exception, log it, and return without rethrowing** if the container needs to know the record failed for retry or recovery. Swallowing exceptions lets the listener return normally and commit offsets per AckMode.

## 12. Logging in error handlers and retries

The listener logs exceptions where business logic runs, while retry policy lives in the error handler. Log the retry pass, backoff interval, error type, and next decision clearly.

An error handler configuration:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L)
            );

    handler.addNotRetryableExceptions(
            InvalidOrderException.class
    );

    return handler;
}
~~~

This example illustrates configuring two retries under FixedBackOff before recovery; exact delivery counts and semantics must be verified against your Spring Kafka version and error handler.

Logs should distinguish:

~~~text
listener_failure
retry_scheduled
retry_attempt
recovery_started
dlt_publish_requested
dlt_publish_succeeded
dlt_publish_failed
~~~

Do not emit a single log saying “message failed” and treat it as describing the full lifecycle. Retrying is a framework decision; logs should surface attempts and policy so operators can verify them.

If the framework already provides retry/DLT metrics, do not add duplicate counters. Structured logs add per-record detail, while metrics track trends.

## 13. Structured logging in DeadLetterPublishingRecoverer

When retries exhaust or a non-retryable exception occurs, DeadLetterPublishingRecoverer routes the record to a DLT. You can wrap the recoverer to emit structured logs at entry and when the recoverer finishes.

~~~java
@Bean
DefaultErrorHandler loggingDltErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer delegate =
            new DeadLetterPublishingRecoverer(dltTemplate);

    delegate.setFailIfSendResultIsError(true);

    ConsumerRecordRecoverer loggingRecoverer =
            (record, exception) -> {

                log.atWarn()
                        .addKeyValue("recovery_action", "publish_dlt")
                        .addKeyValue("source_topic", record.topic())
                        .addKeyValue(
                                "source_partition",
                                record.partition()
                        )
                        .addKeyValue(
                                "source_offset",
                                record.offset()
                        )
                        .addKeyValue(
                                "exception_type",
                                exception.getClass().getSimpleName()
                        )
                        .setCause(exception)
                        .log("DLT recovery started");

                try {
                    delegate.accept(record, exception);

                    log.atInfo()
                            .addKeyValue(
                                    "recovery_action",
                                    "publish_dlt"
                            )
                            .addKeyValue(
                                    "source_topic",
                                    record.topic()
                            )
                            .addKeyValue(
                                    "source_partition",
                                    record.partition()
                            )
                            .addKeyValue(
                                    "source_offset",
                                    record.offset()
                            )
                            .log("DLT recoverer invocation completed");
                }
                catch (RuntimeException publishFailure) {
                    log.atError()
                            .addKeyValue(
                                    "recovery_action",
                                    "publish_dlt"
                            )
                            .addKeyValue(
                                    "source_topic",
                                    record.topic()
                            )
                            .addKeyValue(
                                    "source_partition",
                                    record.partition()
                            )
                            .addKeyValue(
                                    "source_offset",
                                    record.offset()
                            )
                            .setCause(publishFailure)
                            .log("DLT recovery failed");

                    throw publishFailure;
                }
            };

    return new DefaultErrorHandler(
            loggingRecoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
~~~

Keep in mind:

- setFailIfSendResultIsError exists in supported Spring Kafka versions and ensures send failures surface per the recoverer's contract.
- How the recoverer awaits producer results, timeouts, and thrown exception types depend on version/configuration.
- “DLT recoverer invocation completed” should only be interpreted as successful broker publish if config guarantees the send result was confirmed before accept returned.
- To distinguish send requested from broker acknowledged, name log events accurately or observe the KafkaTemplate future/result separately.
- DLT destination topic/partition may be chosen by a destination resolver; to log destination, share the resolver or a wrapper with the same policy rather than guessing topic names.

Never commit the source offset as recovered if DLT publishing failed and the system requires preserving the record.

## 14. Original Kafka coordinates and DLT headers

When a record moves to a DLT, it becomes a new record on the target topic. The DLT record has its own destination coordinates and can carry headers describing the source record.

Example:

~~~text
Source:
  topic = orders.events
  partition = 2
  offset = 105

DLT:
  topic = orders.events.DLT
  partition = 0
  offset = 19
~~~

DLT headers in Spring Kafka can provide original topic, partition, offset, and exception metadata depending on version/config. When logging in a DLT consumer, record both:

~~~text
destination_topic
destination_partition
destination_offset
original_topic
original_partition
original_offset
event_id
traceId
~~~

Do not mistake the DLT offset for the source offset. Operators need the original coordinates to find the record on the source topic.

Headers may be encoded as raw bytes or specific types. Do not assume all DLT headers are UTF-8 strings. Use KafkaHeaders constants and decoding matching your Spring Kafka version.

## 15. Structured logging for DLT consumers

DLT consumers are typically responsible for quarantining, filing tickets, displaying records to operators, or staging replays. They should log origin and action taken.

~~~java
@Component
public class OrderDltListener {

    @KafkaListener(
            id = "ordersDltListener",
            topics = "orders.events.DLT",
            groupId = "orders-dlt-investigation"
    )
    public void onDeadLetter(
            ConsumerRecord<byte[], byte[]> record) {

        log.atWarn()
                .addKeyValue("listener_id", "ordersDltListener")
                .addKeyValue("destination_topic", record.topic())
                .addKeyValue(
                        "destination_partition",
                        record.partition()
                )
                .addKeyValue(
                        "destination_offset",
                        record.offset()
                )
                .addKeyValue("recovery_state", "received")
                .log("Dead letter record received");

        quarantineService.store(record);
    }
}
~~~

This example uses raw bytes because DLTs can hold records that failed deserialization. QuarantineService should store bytes and headers under a secure schema; do not log raw values.

If quarantine storage succeeds, emit a separate log with outcome=stored. If storage fails, throw an exception so the container/error handler handles it per policy rather than marking the record investigated.

A DLT listener must not log “received” and commit the offset before quarantine persistence completes.

## 16. Logging deserialization errors

Some failures happen before the business listener is invoked. Invalid JSON or incompatible schemas cause deserializers to fail.

~~~text
KafkaConsumer.poll()
       |
       v
Deserializer
       |
       +--> SerializationException
       |
       v
ErrorHandlingDeserializer / error handler
       |
       v
Recovery / DLT
~~~

In this case, the listener method has not run, so any MDC set by the listener is absent.

With ErrorHandlingDeserializer, Spring Kafka can store exception details and raw data in headers for the error handler/recoverer. Emit structured logs on the error handling path, including source topic/partition/offset, exception class, error category, and recovery action.

Example log event:

~~~json
{
  "level": "ERROR",
  "message": "Kafka deserialization failed",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "exception_type": "SerializationException",
  "error_category": "deserialization",
  "recovery_action": "publish_dlt"
}
~~~

Never log raw payloads for debugging convenience if payloads can contain personal info, payment data, or secrets. If forensic payloads are required, store them in quarantine storage with access control, encryption, and explicit retention.

## 17. MDC and consumer threads

KafkaConsumer is not thread-safe; the Spring Kafka listener container runs each consumer on its own thread. For synchronous record listeners, the listener method and synchronous service calls execute on the consumer thread.

MDC is also typically thread-local. Consequently:

- MDC set on the listener thread appears in logs from synchronous services.
- Never share a static mutable Map across consumer threads.
- Never let a prior record's context leak to the next record.
- Never call KafkaConsumer directly from worker threads.
- Never assume MDC automatically crosses CompletableFuture or Executor boundaries.

With concurrency 3, there are three child consumers and potentially three consumer threads:

~~~text
ordersListener
    |
    +--> consumer thread 0 --> record A --> MDC A
    |
    +--> consumer thread 1 --> record B --> MDC B
    |
    +--> consumer thread 2 --> record C --> MDC C
~~~

Each thread needs its own context. Once a record finishes, restore/clear context before the thread picks up the next record.

## 18. MDC does not propagate automatically across Executors

A listener may dispatch work asynchronously:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {

    MDC.put("kafka_topic", record.topic());

    executor.execute(() -> orderService.process(record.value()));

    MDC.clear();
}
~~~

This code does not guarantee the worker thread sees kafka_topic. Thread pools reuse threads; MDC on the consumer thread does not transfer automatically to executor threads.

Using TaskDecorator to snapshot/restore MDC:

~~~java
@Bean
TaskDecorator mdcTaskDecorator() {

    return task -> {
        Map<String, String> captured =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous =
                    MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(captured);
                }

                task.run();
            }
            finally {
                if (previous == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(previous);
                }
            }
        };
    };
}
~~~

Attach TaskDecorator to the target executor. This propagates only **MDC values**; it does not automatically propagate full Micrometer Observation/trace contexts.

If the application needs Observation propagation across async boundaries, use Context Propagation integration and executor decorators compatible with your Spring/Micrometer version. Never try reconstructing a trace context solely from a traceId string.

Furthermore, async fire-and-forget inside a Kafka listener can cause the listener to return and commit offsets before the work finishes. Context propagation solves only log correlation; it **does not solve acknowledgment or durability**. Design async completion/ack or persist work durably before returning.

## 19. RecordInterceptor can centralize MDC

If many listeners need identical Kafka record context, consider RecordInterceptor to set context before the listener and clean up afterward.

Idea:

~~~text
ConsumerRecord
      |
      v
RecordInterceptor.intercept(...)
      |
      +--> Set MDC fields
      |
      v
@KafkaListener
      |
      +--> Application logs use MDC
      |
      v
RecordInterceptor cleanup callback
      |
      v
Restore MDC
~~~

A shared interceptor reduces boilerplate, though you must verify exact RecordInterceptor lifecycle callbacks for your Spring Kafka version. Specifically handle:

- Listener succeeds.
- Listener throws an exception.
- Record is discarded by the interceptor.
- Container retries/seeks.
- Batch listeners.
- Concurrent child consumers.
- Context restored even when a callback fails.

Do not set MDC in intercept() and forget cleanup. If your framework version offers success/failure/afterRecord callbacks, follow their exact semantics; do not assume the error handler runs within the same MDC scope after the interceptor completes.

For a few listeners, try/finally inside the listener is simpler to reason about. For many endpoints, an interceptor is helpful when thoroughly tested with a clear contract.

## 20. Writing structured logs for retry attempts

Retry logs must distinguish a retried record from a new event.

Useful fields:

~~~text
event_id
source_topic
source_partition
source_offset
listener_id
consumer_group
attempt
backoff_ms
error_category
exception_type
next_action
~~~

JSON example:

~~~json
{
  "level": "WARN",
  "message": "Kafka record retry scheduled",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "listener_id": "ordersListener",
  "attempt": 2,
  "backoff_ms": 1000,
  "error_category": "database",
  "next_action": "retry"
}
~~~

Attempt numbers must come from the retry mechanism or application-managed state. Never derive retry attempts from Kafka offsets, since offsets do not represent attempt counts.

With blocking retries, records are sought/redelivered on the same topic. With non-blocking retries, records are published to retry topics; source coordinates and current retry coordinates then differ. Keep both in logs when applicable.

Do not log every retry at ERROR if retrying is expected by policy. WARN suits retry attempts, while ERROR suits exhausted retries, recovery failures, or incidents requiring intervention.

## 21. Structured logging for recovery and DLT publishes

A DLT flow needs at least two log types:

**Recovery started / send requested**

~~~json
{
  "level": "WARN",
  "message": "Dead letter recovery started",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "destination_topic": "orders.events.DLT",
  "recovery_action": "publish_dlt",
  "error_category": "validation"
}
~~~

**Publish result**

~~~json
{
  "level": "INFO",
  "message": "Dead letter publish acknowledged",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "destination_topic": "orders.events.DLT",
  "destination_partition": 0,
  "destination_offset": 19,
  "publish_result": "success"
}
~~~

Do not log publish_result=success right after calling KafkaTemplate.send if the future has not completed or the recoverer has not confirmed the send per policy. Use statuses like requested, acknowledged, and failed to avoid equating requests with outcomes.

If publishing fails due to ACLs, serializers, missing topics, or broker unavailability, logs must retain source coordinates so the record stays traceable. Error handlers must not mark a record recovered if DLT publishing fails per app contract.

## 22. Logging in transactional listeners

In a transactional listener container, a listener failure can abort the Kafka transaction. Logs must distinguish **listener processing failure**, **transaction outcome**, and **recovery outcome**.

~~~text
Listener starts
     |
     v
Kafka transaction active
     |
     +--> Business processing
     |
     +--> Exception
             |
             v
       Transaction abort
             |
             v
       AfterRollbackProcessor
             |
             +--> retry
             |
             +--> DLT recovery
~~~

A listener failure log does not prove the transaction aborted cleanly; the transaction manager and container govern the outcome. Likewise, “recovery started” does not prove the DLT record committed.

Fields that may be needed:

- listener_id, consumer_group.
- source topic/partition/offset.
- event_id.
- exception_type/error_category.
- transaction outcome if framework/application has reliable visibility.
- retry/recovery action.
- DLT destination and publish result.

Never log transaction outcome=committed inside the listener before the container commits the transaction. To observe transaction outcomes, use lifecycle hooks/metrics/events or log from the layer with exact knowledge of the result.

## 23. Structured logging does not replace tracing

Logs and traces answer different questions:

| Logs | Traces |
|---|---|
| Record discrete events | Describe spans across a journey |
| Easily carry Kafka topic/partition/offset and exception details | Capture timing and parent-child/link relationships |
| Search by event ID | Track cross-service latency |
| Exist even if a trace is sampled out | Can suffer sampling or export failures |
| Do not inherently form a causal graph | Represent relationships among operations |
| Often hold detailed stack traces | Hold span events/statuses and attributes |

When Micrometer Tracing is configured, traceId/spanId can populate log correlation fields, letting you jump from logs to traces.

Never stuff full stack traces or exception messages into trace tags/metric labels. Use logs for details, traces for causal flow, and metrics for trends.

## 24. Structured logging does not replace metrics

A log event tells you one record failed. Metrics tell you how often errors occur and whether trends are worsening.

| Goal | Right tool |
|---|---|
| Locate a specific record by offset | Structured logs |
| See which listener failed an eventId | Logs |
| Measure p95 listener duration | Micrometer Timer |
| Track consumer lag | Kafka consumer/group metrics |
| Count DLT publish failures | Counters/metrics and logs |
| Follow end-to-end request paths | Distributed tracing |
| Monitor database saturation | Hikari/DB metrics |
| Inspect exception stack traces | Structured logs |

Never turn event_id, order_id, trace_id, or kafka_offset into metric tags simply because they exist in structured logs. High-cardinality fields belong in log searches, not metric time series.

## 25. Protecting sensitive data in logs

Kafka payloads may contain:

- Names, emails, phone numbers, addresses.
- Customer IDs or account numbers.
- Payment tokens or transaction details.
- Authorization headers or access tokens.
- Internal customer data.
- Secrets accidentally placed into headers by producers.

Never log full ConsumerRecord.toString(), JSON payloads, or all Kafka headers for debugging.

A safe policy:

1. Log only approved eventId/operationId fields.
2. Never log raw keys if keys can hold PII.
3. Never log payloads by default.
4. Log only allowlisted headers.
5. Redact tokens, credentials, and payment data.
6. Never place PII into trace baggage or MDC.
7. Bound message length and exception details.
8. Enforce access controls and retention on the log backend.
9. Never leave debug logging enabled accidentally in production.
10. Provide controlled access to forensic payloads in quarantine storage when truly necessary.

A field named customer_reference is not automatically safe; check data contracts and privacy policies. Hashing does not always anonymize data when the value space is guessable.

## 26. Log volume and Kafka throughput

A topic can receive hundreds of thousands of records per minute. Emitting 5 INFO log events per record generates far more log volume than necessary business data.

Controls:

- INFO for major state transitions and aggregate results.
- DEBUG for per-record details, off by default in production.
- WARN for retries or degradations needing monitoring.
- ERROR for failures requiring investigation.
- Rate-limit or sample repetitive logs during major incidents.
- Avoid logging the exact same exception at every layer without adding new information.
- Count failures with metrics rather than relying solely on log volume.
- Use async appenders with bounded queues and clear queue-full policies.
- Monitor disk/ingestion limits of the log pipeline.

If sampling, preserve 100% or higher probability for critical events like DLT publish failures, auth failures, or exhausted retries. Sampling logs must never drop mandatory business audit events.

## 27. JSON logging and multiline stack traces

Each JSON log should emit as a single-line object. Stack traces contain newlines; encoders must escape them as JSON strings or store them in structured fields so log shippers do not split one event into multiple lines.

Avoid concatenating stack traces into messages:

~~~java
log.error("Kafka failed: " + exception);
~~~

Instead:

~~~java
log.atError()
        .addKeyValue("error_category", "database")
        .setCause(exception)
        .log("Kafka record processing failed");
~~~

The encoder governs how exceptions/stack traces serialize per configuration. Test actual JSON output through your log shipper and backend, since misconfigured multiline rules can split stack traces across multiple log records.

## 28. Error classification for fast root-cause triage

Exception classes can be wrapped multiple layers deep. A listener receives ListenerExecutionFailedException, while the cause holds DataAccessResourceFailureException or SerializationException.

A simple classifier:

~~~java
private static String classifyError(Throwable error) {

    Throwable current = error;

    for (int depth = 0;
         current != null && depth < 10;
         depth++, current = current.getCause()) {

        if (current instanceof InvalidOrderException) {
            return "validation";
        }

        if (current instanceof SerializationException) {
            return "deserialization";
        }

        if (current instanceof TimeoutException) {
            return "timeout";
        }

        if (current instanceof DataAccessException) {
            return "database";
        }
    }

    return "other";
}
~~~

Adjust imports and exception hierarchy to your application. Bounding loop depth protects against anomalous cause chains or cyclic references.

Keep error_category within a finite set of values. You can log specific exception_type in a separate field, while keeping exception messages out of metric labels or high-cardinality tags.

## 29. Logging when consumers rebalance or partitions are revoked/lost

Structured logging also benefits lifecycle events:

~~~text
event = kafka_partition_revoked
consumer_group = orders-service
listener_id = ordersListener
topic = orders.events
partition = 2
last_safe_offset = 106
reason = rebalance
~~~

Distinguish:

- **Partitions revoked:** consumer is notified partitions are about to transfer; may have a chance to commit safe progress.
- **Partitions lost:** consumer already lost ownership; do not assume commits are still valid.
- **Partitions assigned:** consumer received new assignments.
- **Commit failed:** offset commit was not acknowledged.

Logs should record the partition subset supplied by the callback rather than assuming the entire assignment changed during cooperative rebalancing.

Do not log last_safe_offset unless the application truly computed a contiguous range of completed records. The most recent polled offset is not automatically safe to commit.

## 30. Logging pauses/resumes due to database overload

When a backpressure controller pauses a container, log reason and state:

~~~json
{
  "level": "WARN",
  "message": "Kafka listener pause requested",
  "listener_id": "ordersListener",
  "pause_reason": "DATABASE_SATURATION",
  "db_pool_active": 19,
  "db_pool_max": 20,
  "db_threads_waiting": 4,
  "container_state": "PAUSE_REQUESTED"
}
~~~

When the container actually pauses, emit a separate event:

~~~json
{
  "level": "INFO",
  "message": "Kafka consumer paused",
  "listener_id": "ordersListener",
  "partitions": ["orders.events-0", "orders.events-1"]
}
~~~

On resume:

~~~json
{
  "level": "INFO",
  "message": "Kafka consumer resumed",
  "listener_id": "ordersListener",
  "pause_duration_ms": 45000,
  "pause_reason": "DATABASE_SATURATION"
}
~~~

Do not log pause requested and actual paused as a single event. Containers apply pauses at poll boundaries. If multiple pause reasons exist, log each specific reason and resume only once all necessary conditions clear.

## 31. Correlation between source and DLT logs

A DLT record should be traceable back to its source record via:

- eventId/operationId.
- Original topic.
- Original partition.
- Original offset.
- DLT destination topic/partition/offset.
- traceId/spanId if available.
- Exception type/error category.
- Retry/recovery outcome.

Example pair of logs:

~~~json
{
  "message": "Source record processing failed",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "error_category": "validation"
}
~~~

~~~json
{
  "message": "DLT publish acknowledged",
  "event_id": "evt-100",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "destination_topic": "orders.events.DLT",
  "destination_partition": 0,
  "destination_offset": 19,
  "publish_result": "success"
}
~~~

Even if a trace is sampled out or the DLT producer runs outside the listener's observation scope, eventId and origin metadata keep investigations intact. Never replace eventId with traceId because one event can traverse multiple traces across retries and replays.

## 32. Log schemas must be governed

When multiple teams use Spring Kafka, structured log fields need a schema contract:

| Field | Type | Convention |
|---|---|---|
| timestamp | ISO-8601 | UTC |
| level | string | DEBUG/INFO/WARN/ERROR |
| service | string | Stable service name |
| environment | string | dev/staging/prod |
| listener_id | string | Listener endpoint ID |
| consumer_group | string | Consumer group |
| kafka_topic | string | Source/destination topic in separate fields |
| kafka_partition | integer/string | Per encoder contract |
| kafka_offset | integer/string | Per encoder contract |
| event_id | string | Normalized business ID |
| outcome | enum | started/success/failure |
| error_category | enum | validation/database/timeout/other |
| traceId | string | Tracing context if present |
| spanId | string | Span context if present |
| recovery_action | enum | retry/publish_dlt/replay |
| destination_topic | string | Only when a destination exists |

Use source_topic and destination_topic instead of one ambiguous topic field in DLT logs. Avoid changing field data types across services without a migration plan.

When adding fields, check whether the log backend indexes all fields or only declared ones. A clean schema keeps queries reliable and avoids unnecessary indexing overhead.

## 33. Testing structured logging

Tests should assert actual JSON output rather than only verifying a logger method was called.

Scenarios:

| Scenario | What to assert |
|---|---|
| Listener succeeds | Includes source coordinates and outcome success |
| Listener exception | Includes exception type/category and stack trace |
| Retry | Attempt/action recorded accurately |
| DLT publish | Source and destination metadata linked |
| DLT publish failure | Outcome failure, exception logged, no false success |
| Listener concurrency | MDC across consumer threads does not mix |
| Next record on same thread | Prior record's MDC is gone |
| Async executor | Context propagated/restored per policy |
| Missing header | Valid eventId fallback |
| Payload with PII | Raw payload and secrets absent |
| Deserialization failure | Logged on error handling path even if listener did not run |
| Rebalance | Partition revoked/lost distinguished |
| Pause/resume | Requested and actual states logged separately |
| JSON stack trace | Each log event remains valid JSON |
| High throughput | Log volume and async appender queue controlled |

Use Logback ListAppender or a suitable test appender to inspect event fields. In integration tests, verify the JSON encoder emits schema-compliant output parseable by your log shipper.

Do not test logs merely by asserting the message string contains a topic; verify topic is emitted as a structured field if that is the goal.

## 34. Troubleshooting structured logging

### Logs lack Kafka topic/partition/offset

MDC was not set, the listener does not receive ConsumerRecord, or logging happens before record context is established. Check where context setup and cleanup occur.

### Record B's log carries Record A's eventId

MDC was not cleared/restored in finally, or an async task reused a worker thread with stale context. Check lifecycle and TaskDecorator.

### Trace ID does not appear

Micrometer Tracing is unconfigured, the log encoder omits MDC/correlation fields, or trace context was not propagated. MDC eventId does not replace traceId.

### DLT logs report success yet topic has no record

Logs may have been written after send requested but before broker acknowledgment. Inspect producer futures, recoverer send-result behavior, serializers, ACLs, and broker errors.

### Retry logs lack attempt numbers

Do not infer attempt from offset. Obtain it from the error handler/retry context or store state per policy.

### One event emits multiple failure logs

Listener, error handler, and recoverer may all log the same exception. Keep one detailed log at the right boundary and have other layers log only new decisions/outcomes.

### JSON splits across multiple lines

Check the stacktrace provider, encoder, and log shipper multiline configuration. Each logging event must encode as one valid JSON document.

### Log volume spikes suddenly

Per-record INFO logs, retry storms, or repeated exception stack traces can inflate volume. Use log levels, intentional sampling/rate limiting, and metrics to track volume.

### Log backend cannot find a field

Check encoder providers, field name mappings, parser/index templates, and data types. Structured JSON on stdout fails if the shipper pipeline misparses it.

### Async logs lack correlation context

Context was not propagated to the executor or MDC was restored before the task ran. Use controlled context propagation without holding ConsumerRecord objects arbitrarily.

## 35. Runbook for investigating a failing record

When receiving an eventId or source coordinates from an operator:

1. Search structured logs by eventId.
2. If eventId is missing, search by source topic/partition/offset.
3. Identify listener ID, consumer group, pod, and timestamp.
4. Find the first processing pass and exception category.
5. Determine whether the record retried or routed straight to DLT.
6. Count attempts from logs/metrics; do not infer from offsets.
7. Check recovery action and DLT publish outcome.
8. Cross-check DLT destination coordinates and original metadata.
9. Open the trace via traceId if present.
10. Check whether database/API side effects already completed.
11. Determine whether the event was quarantined, replayed, or skipped per policy.
12. Before replaying, verify idempotency to prevent duplicate side effects.
13. Record the decision and final result for audit.

Structured logs supply the facts, while replay decisions require verifying business state. Kafka offsets/DLT do not automatically undo database or external API effects.

## 36. Production readiness checklist

- Log output is JSON with a clear schema.
- Every key record log includes listener ID and consumer group.
- Source topic/partition/offset are recorded as separate fields.
- Destination coordinates are kept separate from source coordinates.
- Event ID stays stable across retries/replays and is protected per privacy policy.
- TraceId/spanId come from proper tracing integration.
- TraceId is never used in place of eventId.
- MDC is snapshotted/restored or cleared in finally.
- MDC never mixes across concurrent consumer threads.
- Async executors use proper context propagation.
- Async processing never commits offsets before durable work finishes.
- SLF4J key-value pairs are emitted as structured fields by the encoder.
- Error handler logs capture retry/recovery decisions.
- DLT publish requested is separated from broker acknowledged.
- DLT send failures are never logged as success.
- Deserialization errors have a dedicated logging path.
- Exception types/error categories are normalized.
- Raw payloads, credentials, tokens, and PII are never logged.
- EventId/offset/traceId are never put into metric tags.
- Log volume, stack traces, and appender queues are controlled.
- JSON multiline/stack traces encode as valid JSON.
- Schema fields stay consistent across services.
- Log retention and access controls are in place.
- Dashboards link logs, metrics, and traces.
- Tested success, retries, DLT, concurrency, async context, rebalances, and malformed records.

**Conclusion:** Structured logging in Spring Kafka transforms scattered log sentences into searchable, correlatable operational data. When every log carries accurate **listener, consumer group, source coordinates, event ID, outcome, error category, and trace context**, operators can follow records through processing, retries, and DLTs. Quality depends on disciplined MDC lifecycle management, separating send requests from broker acknowledgments, controlling log volume, and protecting sensitive data. Structured logs complement Micrometer metrics and distributed tracing; they do not replace offset management, retry policies, or idempotent business processing.

