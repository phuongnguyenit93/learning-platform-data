# Correlation ID in MDC

## 1. Why does a consumer need a Correlation ID?

In distributed systems, a single business request can traverse multiple services before completing. For example, Order API writes an event to Kafka; Order Fulfillment consumes the event and calls Inventory and Payment. When an error occurs at one step, looking only at one service's logs makes it hard to know which log lines belong to the same business flow.

**Correlation ID** is an identifier propagated throughout a processing flow to link related logs and events. With Spring Kafka, the producer puts the ID into a Kafka header; the consumer reads the header from ConsumerRecord and places the value into **Mapped Diagnostic Context (MDC)** so the logging framework automatically attaches it to log lines during processing.

~~~text
HTTP request
   |
   | correlation-id = req-7f31
   v
Order API
   |
   v
Kafka producer
   |
   | header correlation-id=req-7f31
   v
Topic: orders.created
   |
   v
Spring Kafka consumer
   |
   | ConsumerRecord.headers()
   | MDC.put("correlationId", "req-7f31")
   v
Order Fulfillment
~~~

MDC puts the correlation ID into log lines without passing the ID parameter into every logging statement. However, MDC is context tied to the current thread. It does not propagate automatically over Kafka, does not sync automatically across thread pools, and does not replace distributed tracing.

## 2. Correlation ID, Trace ID, Message ID, and Kafka offset

These identifiers can relate to each other yet serve different purposes.

| Identifier | Purpose | Scope |
|---|---|---|
| Correlation ID | Links logs of one business flow | Multiple services and multiple related messages |
| Trace ID | Links spans in a distributed trace | One trace per tracing model |
| Message/Event ID | Uniquely identifies one event | One message, often used for deduplication |
| Kafka offset | Record position in a partition | One topic-partition |

Example:

~~~text
correlation-id = order-flow-9281
trace-id       = 4bf92f3577b34da6a3ce929d0e0e4736
event-id       = evt-6a91
topic          = orders.created
partition      = 2
offset         = 1842
~~~

One order flow can generate multiple event IDs and multiple trace IDs when steps run asynchronously. Correlation ID can be preserved across the entire business lifecycle to link them.

Do not use offset as correlation ID because offset only has meaning within one partition. Do not use correlation ID as message ID when multiple events within the same flow must be distinguished.

## 3. What is MDC?

**Mapped Diagnostic Context (MDC)** is a mechanism in SLF4J and logging implementations to attach key/value pairs to the current logging context. The logging framework reads these values when rendering log lines.

~~~java
MDC.put("correlationId", "order-flow-9281");

log.info("Validating order");
log.info("Calling inventory");
log.info("Order accepted");

MDC.remove("correlationId");
~~~

If the Logback pattern includes the MDC key, logs can display:

~~~text
INFO correlationId=order-flow-9281 Validating order
INFO correlationId=order-flow-9281 Calling inventory
INFO correlationId=order-flow-9281 Order accepted
~~~

MDC is typically implemented using thread-local context. Two consumer threads can hold two different correlation IDs. However, thread pools reuse threads across tasks; if the prior task fails to remove MDC, the next task can log with the stale ID.

**MDC is not a global map and does not propagate automatically over Kafka.** Kafka only carries records and headers. Producers must write the ID into headers, and consumers must read the header and set MDC on the processing thread.

## 4. Standardizing the Kafka header

A common contract uses the header name:

~~~text
correlation-id
~~~

Producers and consumers must agree on header name, casing, encoding, length, allowed character set, rules when missing or duplicated, when to retain an existing ID vs. mint a new one, and how to preserve headers when republishing to retry topics or DLTs.

If an HTTP gateway receives X-Correlation-ID, the entry service can normalize that value into the Kafka header correlation-id.

## 5. Producer writing Correlation ID into Kafka headers

You can construct a ProducerRecord to attach headers explicitly:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

public void publish(
        String topic,
        String key,
        OrderCreated event,
        String correlationId) {

    ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>(topic, key, event);

    record.headers().add(
        "correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8)
    );

    kafkaTemplate.send(record);
}
~~~

If the producer is handling a request that already has a correlation ID, propagate that same ID onto related events. If the request lacks an ID, the entry service can mint a new ID using UUID or an agreed opaque format.

~~~java
String correlationId = incomingHeader;

if (correlationId == null || correlationId.isBlank()) {
    correlationId = UUID.randomUUID().toString();
}
~~~

Incoming external IDs must be validated and length-bounded. Never put emails, access tokens, session secrets, or unnecessary personal data into correlation IDs.

Do not generate a fresh ID at every service, or the log chain breaks. Mint a new one only when no valid ID exists or when a business flow intentionally begins a new correlation scope.

## 6. Consumer reading the header from ConsumerRecord

Spring Kafka can pass ConsumerRecord directly to the listener:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void consume(ConsumerRecord<String, OrderCreated> record) {
    String correlationId = CorrelationIds.from(record);
    orderService.process(record.value());
}
~~~

Kafka header values are byte[]. The consumer decodes per the encoding contract, usually UTF-8.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public final class CorrelationIds {

    private static final String HEADER = "correlation-id";

    private static final Pattern ALLOWED =
        Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    private CorrelationIds() {
    }

    public static String from(ConsumerRecord<?, ?> record) {
        Header header = record.headers().lastHeader(HEADER);

        if (header == null || header.value() == null) {
            return null;
        }

        byte[] bytes = header.value();

        if (bytes.length == 0 || bytes.length > 128) {
            return null;
        }

        String value = new String(bytes, StandardCharsets.UTF_8);

        if (!ALLOWED.matcher(value).matches()) {
            return null;
        }

        return value;
    }
}
~~~

The allowlist must fit the actual ID format. The example above accepts hex UUIDs with hyphens, dots, underscores, and colons within 128 characters.

### 6.1. Missing or invalid header

Older records may lack correlation-id. External producers may send malformed headers. Consumers need a consistent policy:

- Mint a new local ID to link logs from the consumer onward.
- Emit a missing marker to detect producers violating the contract.
- Reject/recover the record if correlation ID is a mandatory business requirement.

When generating a new ID, you can also log source=generated to avoid mistaking it for an ID propagated from the original request.

### 6.2. Multiple headers with the same name

Kafka allows duplicate header keys. lastHeader(name) returns the last matching header. If the contract permits only one header, count them and reject/fallback on duplicates. Do not silently pick one if a gateway or producer might append duplicate headers unexpectedly.

## 7. Setting MDC in try/finally

Set MDC before business logic and clean up in finally:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void consume(ConsumerRecord<String, OrderCreated> record) {
    String correlationId = CorrelationIds.from(record);

    if (correlationId == null) {
        correlationId = UUID.randomUUID().toString();
    }

    String previous = MDC.get("correlationId");
    MDC.put("correlationId", correlationId);

    try {
        orderService.process(record.value());
        log.info("Order event processed");
    }
    finally {
        if (previous == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", previous);
        }
    }
}
~~~

This snippet saves the previous value and restores it after processing. That is safer than unconditionally clearing all of MDC when an outer scope holds other keys.

**finally must run even when the business service throws an exception.** Removing only at the end of the happy path leaves the correlation ID on the consumer thread on exceptions, leaking to the next record.

### 7.1. AutoCloseable scope helper

You can encapsulate setup/cleanup to avoid boilerplate:

~~~java
public final class CorrelationMdcScope implements AutoCloseable {

    private final String previous;

    private CorrelationMdcScope(String correlationId) {
        this.previous = MDC.get("correlationId");

        if (correlationId == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", correlationId);
        }
    }

    public static CorrelationMdcScope open(String correlationId) {
        return new CorrelationMdcScope(correlationId);
    }

    @Override
    public void close() {
        if (previous == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", previous);
        }
    }
}
~~~

Usage:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(ConsumerRecord<String, OrderCreated> record) {
    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open(CorrelationIds.from(record))) {

        orderService.process(record.value());
        log.info("Order event processed");
    }
}
~~~

Try-with-resources ensures close() executes whether the method returns normally or throws an exception.

## 8. Configuring logging to display MDC

Logback reads MDC keys using pattern converters:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level [%thread] correlationId=%X{correlationId:-missing} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

The **%X{correlationId:-missing}** token reads the correlationId MDC key and prints missing if absent.

Example:

~~~text
2026-11-15T11:20:00.012 INFO [orders-consumer-1] correlationId=order-flow-9281 Order event received
2026-11-15T11:20:00.018 INFO [orders-consumer-1] correlationId=order-flow-9281 Inventory reservation started
2026-11-15T11:20:00.045 INFO [orders-consumer-1] correlationId=order-flow-9281 Order event processed
~~~

With Log4j2, use ThreadContext and the corresponding pattern converter instead of Logback syntax.

### 8.1. Structured JSON logging

If the application outputs JSON logs, MDC can be emitted as dedicated fields:

~~~json
{
  "timestamp": "2026-11-15T11:20:00.012Z",
  "level": "INFO",
  "service": "order-fulfillment",
  "thread": "orders-consumer-1",
  "correlationId": "order-flow-9281",
  "message": "Inventory reserved"
}
~~~

Field names should stay consistent across services. If one service uses correlationId and another uses correlation_id, the log backend requires mapping or normalization.

Do not log raw headers when validation fails; log only the invalid status to avoid leaking raw input data.

## 9. MDC cleanup and thread reuse

Consumer threads are long-lived and process many records consecutively. If record A sets correlationId=A without removing it, record B lacking a header will still log with ID A.

~~~text
Consumer thread-1

Record A:
  MDC.put(correlationId=A)
  processing done
  forgot cleanup

Record B:
  no correlation-id
  log processing
  MDC still contains A
~~~

This bug is subtle because logs still show a syntactically valid correlation ID while linking to the wrong request.

Rules:

1. Save prior context when nested scopes may exist.
2. Set the current correlation ID.
3. Run business logic inside try.
4. Restore/remove in finally.
5. Do not clean up before the final logs belonging to that scope.

Cleanup must execute on exceptions, timeouts, and recovery paths too—not just the happy path.

## 10. Record listeners vs. batch listeners

With a **record listener**, one invocation typically maps to one ConsumerRecord. Wrapping the whole method in one MDC scope fits naturally.

With a **batch listener**, one invocation can receive many records with different correlation IDs. One MDC context holds only one correlation ID at a time.

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "batchFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        try (CorrelationMdcScope ignored =
                 CorrelationMdcScope.open(CorrelationIds.from(record))) {

            orderService.process(record.value());
            log.info("Processed offset {}", record.offset());
        }
    }
}
~~~

Each record runs inside its own scope. After each iteration, MDC restores so the next record does not inherit the prior ID.

### 10.1. Batch-level logs

Do not pick the first record's correlation ID and apply it to the entire batch. When a batch spans multiple flows, batch-level logs should use a dedicated batch ID, batch size, listener ID, and duration. Per-record logs should emit inside each record's scope.

If the listener throws an exception, the failing record's finally block cleans up before the exception reaches the error handler. Error handler logs may lack MDC; when correlation ID is needed there, read it directly from ConsumerRecord inside the handler/recoverer.

## 11. Spring Kafka concurrency

With concurrency greater than one, Spring Kafka typically creates multiple child containers and consumer threads:

~~~text
ConcurrentMessageListenerContainer
        |
        +-- Consumer thread 0: MDC correlationId=A
        |
        +-- Consumer thread 1: MDC correlationId=B
        |
        +-- Consumer thread 2: MDC correlationId=C
~~~

MDC is normally bound per thread, giving each consumer thread an independent context. However, the same thread will process subsequent records, so cleanup remains mandatory.

Never store correlation ID in a shared static mutable String, as consumer threads will overwrite one another.

## 12. Async processing and TaskDecorator

If a listener submits work to an executor:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(ConsumerRecord<String, OrderCreated> record) {
    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open(CorrelationIds.from(record))) {

        executor.execute(() -> orderService.process(record.value()));
    }
}
~~~

MDC on the consumer thread **does not automatically appear** inside the thread pool task. When the listener returns, the scope cleans up while the task may run later.

A TaskDecorator can capture context at submission and restore it on the worker thread:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(captured);
                }

                delegate.run();
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
    }
}
~~~

Executor configuration:

~~~java
@Bean
public ThreadPoolTaskExecutor orderExecutor() {
    var executor = new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(16);
    executor.setQueueCapacity(500);
    executor.setThreadNamePrefix("order-worker-");
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.initialize();

    return executor;
}
~~~

The decorator restores prior context in finally because worker threads are reused.

**Propagating MDC does not solve Kafka acknowledgment.** If a listener submits a task and returns immediately, the container may commit the offset before async business processing completes depending on AckMode and design. Coordinate ack/transactions so records are considered complete only after required business outcomes finish.

## 13. CompletableFuture and callbacks

CompletableFuture callbacks can execute on different threads depending on the executor and where the future completes:

~~~java
service.callAsync()
    .thenApply(result -> {
        log.info("Received downstream response");
        return result;
    });
~~~

Do not assume thenApply or thenAccept always runs on the consumer thread. If the callback runs on another worker, MDC may be missing.

Options:

- Use an executor configured with MdcTaskDecorator.
- Capture/restore the MDC map when building callbacks.
- Use a suitable context propagation library.
- Avoid scattering ad-hoc manual context copying without a shared convention.

## 14. Retries, error handlers, and DLT

When a listener throws an exception, the Spring Kafka error handler can retry the record or recover it to a DLT.

~~~text
ConsumerRecord
     |
     v
Listener sets MDC
     |
     v
Business processing fails
     |
     v
finally restores MDC
     |
     v
Exception reaches error handler
     |
     +--> retry
     |
     +--> recover / DLT
~~~

The listener's MDC scope ends before the exception is handled outside the method. Thus, error handler logs may lack the correlation ID.

To preserve context:

- Log correlation ID right before throwing the exception.
- Inside custom error handlers/recoverers, read the ID directly from ConsumerRecord.
- Use an interceptor/wrapper if a scope must span the exact lifecycle.
- Preserve the correlation-id header when republishing to retry topics and DLTs.

Never rely on thread-local MDC to carry context across multiple retries.

### 14.1. Retry topics

With the retry-topic pattern, events are published to retry topics and consumed again after backoff. Producers sending retry records must keep the correlation-id header.

~~~text
orders.created
     |
     v
Listener failure
     |
     v
orders.created-retry
     |
     v
Retry consumer reads header
     |
     v
MDC is set again
~~~

If the header is lost during republishing, retry attempt logs lose their link to the original flow. Verify header propagation with integration tests.

### 14.2. Dead-letter topics

DLT records should keep the original correlation ID alongside source metadata such as original topic/partition/offset supplied by the recovery mechanism. DLT consumers should also populate MDC from the header.

Do not replace the original correlation ID with a new ID on every recovery pass. If you need to track individual recovery attempts, add a separate attempt ID.

## 15. RecordInterceptor and MDC

Spring Kafka provides **RecordInterceptor** for record listeners to execute logic before/after listener invocation. It can help with cross-cutting concerns like logging context.

However, cleanup must match your version's exact lifecycle and API. Interceptors expose callbacks for success/failure/afterRecord depending on version; never assume a single callback always runs in every situation.

For simple listeners, try/finally directly inside the method is easy to read and verify. When using an interceptor across endpoints, test:

- Listener returns normally.
- Listener throws an exception.
- Record is filtered/skipped.
- Error handler retries/recovers.
- Container stops mid-processing.
- Batch listeners if that interceptor supports them.

Never set up MDC in an interceptor and clean it up only in a callback skipped when exceptions happen.

## 16. Reading custom headers via @Header

Spring Kafka can map Kafka headers into method arguments:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(
        @Header(name = "correlation-id", required = false)
        String correlationId,
        OrderCreated event) {

    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open(correlationId)) {

        orderService.process(event);
    }
}
~~~

This is convenient when only one header is needed and the message converter maps the type properly. When strict control over bytes, duplicates, length, or validation is required, accepting ConsumerRecord directly is clearer.

Do not assume every converter maps custom headers to String identically. Verify the converter and write integration tests.

## 17. MDC vs. distributed tracing

MDC serves log correlation. Distributed tracing uses trace/span contexts and propagation standards like W3C Trace Context.

| Aspect | Correlation ID in MDC | Trace context |
|---|---|---|
| Purpose | Links log lines | Links spans |
| Context | MDC/thread-local | Observation/Tracing context |
| Over Kafka | Custom header contract | Propagator inject/extract |
| Parent/child spans | No | Yes |
| Timing/dependency graph | Not built-in | Yes |
| Log integration | Logging pattern reads MDC | Tracing integration can add trace/span IDs |

An application can use both: correlation ID for long-lived business flows and trace ID for a specific trace.

If using Micrometer Tracing/Spring Observation, let the tracing propagator extract trace context from supported headers. Do not manually parse traceparent and call MDC.put("traceId", ...) in place of the tracing library; doing so can break parent/child relationships, sampling, and baggage semantics.

## 18. Fallback when the header is absent

Three policies are common.

**Mint a new ID:** all consumer logs have an ID, though it begins at the consumer and does not link upstream requests.

~~~java
String id = CorrelationIds.from(record);

if (id == null) {
    id = UUID.randomUUID().toString();
}
~~~

**Use a missing marker:** makes producer contract violations easy to spot; logs have no ID to join on.

**Validation failure:** appropriate only if correlation ID is strictly required by the business event contract; do not turn observability requirements into hard validation failures unless upstream agrees.

When generating a new ID, also log source=generated. Never claim the ID propagated from the original request.

## 19. Trust boundaries and log injection

Correlation IDs can originate from HTTP clients, external producers, or message replays. Treat them as untrusted input.

Reject passwords, access tokens, JWTs, or session cookies; emails, phone numbers, or unnecessary PII; newlines/carriage returns that enable log injection; overly long strings causing log flooding; and arbitrary control characters or binary bytes.

An allowlist like [A-Za-z0-9._:-]{1,128} suits system-issued opaque IDs. If your organization uses another format, use an official validator.

Never use correlation ID as an authorization identity. Knowing an ID does not prove the caller has permission to access data.

## 20. Structured JSON logs

If the application uses a JSON encoder, MDC can be emitted as dedicated fields:

~~~json
{
  "timestamp": "2026-11-15T11:20:00.012Z",
  "level": "INFO",
  "service": "order-fulfillment",
  "thread": "orders-consumer-1",
  "correlationId": "order-flow-9281",
  "message": "Inventory reserved"
}
~~~

Field names should stay consistent across services. If one service uses correlationId and another uses correlation_id, the log backend requires mapping or normalization.

Do not log raw headers when validation fails; log only the invalid status to avoid leaking raw input data.

## 21. Never use Correlation ID as a metric label

Correlation ID has nearly a fresh value per request/message. Therefore it is **unsuitable as a Prometheus/Micrometer metric label**.

Avoid:

~~~java
meterRegistry.counter(
    "orders.processed",
    "correlationId",
    correlationId
).increment();
~~~

Use low-cardinality dimensions instead:

~~~text
event.family=order
result=success
topic=orders.created
listener=orders-consumer
~~~

To investigate one request, use logs/traces with correlation ID. Metrics aggregate rates, latencies, and throughput.

## 22. Testing MDC cleanup

Unit tests should prove the scope restores MDC upon completion:

~~~java
@Test
void restoresPreviousCorrelationId() {
    MDC.put("correlationId", "outer");

    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open("inner")) {
        assertThat(MDC.get("correlationId")).isEqualTo("inner");
    }

    assertThat(MDC.get("correlationId")).isEqualTo("outer");
    MDC.remove("correlationId");
}

@Test
void removesCorrelationIdWhenThereWasNoPreviousValue() {
    MDC.remove("correlationId");

    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open("record-1")) {
        assertThat(MDC.get("correlationId")).isEqualTo("record-1");
    }

    assertThat(MDC.get("correlationId")).isNull();
}
~~~

Test the exception path:

1. Business service logs while MDC is set.
2. Service throws an exception.
3. Assert the exception still reaches the error handler.
4. Assert MDC is restored after the invocation.
5. Process the next record on the same consumer thread.
6. Assert the prior record's ID does not appear.

### 22.1. Testing thread reuse

Use a single-thread executor:

- Submit a task with correlation ID A.
- Task finishes and cleans up.
- Submit a task without an ID.
- Assert the second task does not see A.

This is a useful test for catching MDC leaks caused by thread pool reuse.

## 23. Integration testing across Kafka

Use Embedded Kafka or Testcontainers to test real propagation:

1. Producer generates a stable correlation ID.
2. Producer sends a record with the correlation-id header.
3. Listener receives the record and reads the header.
4. Listener sets MDC.
5. Test appender captures logs inside the business service.
6. Assert logs carry the right correlation ID.
7. Send the next record with a different ID and assert no cross-contamination.
8. Send a record missing the header and verify fallback policy.
9. Trigger an exception to verify cleanup.
10. If retry topics/DLT exist, verify the header is preserved.
11. If an async executor exists, verify TaskDecorator propagates and cleans up context.

Mocking ConsumerRecord and calling a helper does not prove headers survive serializers, brokers, and deserializers/converters under production config.

## 24. Correlation ID in the error handler

MDC inside the listener is normally cleaned up as the method unwinds. The error handler may log afterward once MDC has reverted to its pre-invocation state.

If recovery logs need correlation ID:

- Read the header directly from ConsumerRecord inside a custom recoverer.
- Add the ID to a structured log field of the recovery operation.
- Do not depend on the already-exited listener's MDC.
- Preserve the header across retry and DLT republishes.
- Use a separate recovery/attempt ID to distinguish retry passes.

This is a crucial boundary between **context inside the listener method** and **context in the container/error handler**.

## 25. Runbook when correlation ID is missing or wrong

1. Identify the first service in the flow.
2. Check whether the request/gateway receives or generates a correlation ID.
3. Verify the producer sends the exact Kafka header name.
4. Check encoding and header bytes.
5. Check whether retry/DLT republishes preserve the header.
6. Verify the listener reads ConsumerRecord or the mapped header properly.
7. Verify MDC setup happens before business logs.
8. Verify finally/try-with-resources cleanup.
9. For async processing, verify TaskDecorator/context propagation.
10. Verify the Logback pattern or JSON encoder outputs the MDC field.
11. Look for services using inconsistent field names.
12. Verify IDs contain no PII/secrets and cannot trigger log injection.
13. Use integration tests to reproduce through Kafka.
14. Document fallback policy for missing/invalid headers.

If only one service lacks the ID, compare the header contract between producer and listener mapping. If all services lack it, inspect the gateway or propagation at the start of the flow.

## 26. Common mistakes

**Calling MDC.put without remove.** Consumer threads are reused; stale IDs appear in subsequent record logs.

**Cleaning up only on the happy path.** Exception paths still leak MDC; always use finally or try-with-resources.

**Assuming MDC travels over Kafka automatically.** Kafka requires explicit header propagation.

**Assuming MDC crosses executors automatically.** Thread pools require TaskDecorator or context propagation.

**Using one correlation ID for an entire batch.** A batch can contain messages from multiple flows.

**Using event ID or offset as correlation ID.** They have different semantics.

**Using correlation ID as a metric label.** Cardinality explodes.

**Trusting every producer-sent header.** Headers need validation and length/character limits.

**Dropping the ID across retry/DLT.** Later processing logs lose their link to the original flow.

**Confusing correlation ID with trace ID.** One links business logs; the other links tracing spans.

**Manually parsing traceparent to set MDC.** Use a tracing propagator for trace context.

**Relying on MDC in error handlers after listener unwind.** Listener finally blocks may have already cleaned up; error handlers should read the ID directly from the record.

## 27. Implementation checklist

- [ ] Standardize Kafka header name, encoding, and format.
- [ ] Producers preserve correlation ID across related messages.
- [ ] Consumers read the header from ConsumerRecord or mapped message headers.
- [ ] Validate length and characters.
- [ ] Define policy for missing or duplicate headers.
- [ ] Set MDC before business logs.
- [ ] Clean up/restore MDC in finally or try-with-resources.
- [ ] Batch listeners open a separate MDC scope per record.
- [ ] Async executors use TaskDecorator/context propagation.
- [ ] Retry topics and DLTs preserve the correlation header.
- [ ] Error handlers/recoverers extract ID from the record when needed.
- [ ] Logging patterns or JSON encoders output the MDC key.
- [ ] Never include correlation ID in metric labels.
- [ ] Never log secrets/PII or allow log injection.
- [ ] Distinguish correlation ID, trace ID, event ID, and offset.
- [ ] Test success, exceptions, missing headers, thread reuse, retries, and DLT.

## 28. End-to-end example: Order Fulfillment

Order API receives an order creation request with correlation ID **order-flow-9281**. The API publishes the event:

~~~java
ProducerRecord<String, OrderCreated> record =
    new ProducerRecord<>(
        "orders.created",
        orderId,
        event
    );

record.headers().add(
    "correlation-id",
    "order-flow-9281".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record);
~~~

Consumer:

~~~java
@KafkaListener(
    id = "order-fulfillment",
    topics = "orders.created",
    groupId = "fulfillment-workers"
)
public void consume(ConsumerRecord<String, OrderCreated> record) {
    String id = CorrelationIds.from(record);

    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open(id)) {

        log.info("Order event received");
        inventoryService.reserve(record.value());
        paymentService.authorize(record.value());
        log.info("Order fulfilled");
    }
}
~~~

Logs:

~~~text
INFO correlationId=order-flow-9281 Order event received
INFO correlationId=order-flow-9281 Inventory reserved
INFO correlationId=order-flow-9281 Payment authorized
INFO correlationId=order-flow-9281 Order fulfilled
~~~

If payment service runs asynchronously, context must be captured and restored in the executor. If the listener fails and the record retries, the retry record must keep the correlation-id header. Consumers re-establish MDC from the header on each attempt.

Correlation ID locates logs belonging to the same order flow. Event ID still deduplicates individual events; trace ID still investigates spans and parent/child relationships.

## 29. Key takeaways

**Correlation ID in MDC** makes logs from the same Kafka processing flow searchable together. Producers pass the ID via a Kafka header; Spring Kafka consumers read it from ConsumerRecord, validate it, and set MDC before business logic.

MDC is bound to threads, so it must be **cleaned up or restored in finally**. For batch listeners, open a separate scope per record; for async executors, capture/restore context via TaskDecorator or an appropriate propagation mechanism. Retries and DLTs must preserve the correlation header so downstream passes remain linked to the initial flow.

Correlation ID differs from trace ID, message ID, and Kafka offset. Use it in logs/traces per policy, never as a metric label, never containing PII/secrets, and never as an authorization mechanism. A reliable implementation requires clear header contracts, validation, logging configuration, idempotency, and integration tests over Kafka.
