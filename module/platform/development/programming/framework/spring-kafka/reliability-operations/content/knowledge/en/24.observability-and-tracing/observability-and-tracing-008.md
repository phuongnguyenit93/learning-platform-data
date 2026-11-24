# Correlation ID in headers

## 1. Why is a Correlation ID needed when using Spring Kafka?

In an event-driven architecture, a business request typically traverses multiple services and multiple Kafka topics. For example, a customer places an order via an HTTP API; the order service publishes `OrderCreated`, the inventory service receives it and publishes `StockReserved`, the payment service publishes `PaymentConfirmed`, and the notification service finally sends a notification.

Each service has its own logs, metrics, and traces. When one step fails, operators need to know which logs and events truly belong to the same business flow. A **Correlation ID** is the identifier used to tie those related steps together.

Example:

~~~text
HTTP POST /orders
  correlationId: 5e85d52f-5a98-44f4-b29c-635a8994643f
       |
       v
orders.created
  header x-correlation-id = 5e85d52f-5a98-44f4-b29c-635a8994643f
       |
       v
Inventory listener
  log correlationId=5e85...
  publish stock.reserved with same correlationId
       |
       v
Payment listener
  log correlationId=5e85...
  publish payment.confirmed with same correlationId
       |
       v
Notification listener
  log correlationId=5e85...
~~~

**Correlation ID in headers** means placing the ID in the Kafka record's metadata rather than forcing it into every business event's payload.

Kafka does not automatically generate or propagate a business correlation ID for every event. Applications must agree on header names, encoding, creation points, reading, forwarding, and handling when headers are missing or malformed.

## 2. How do Kafka headers store data?

A Kafka record contains topic, partition, offset (once written), key, value, timestamp, and headers. Headers are pairs of names and **`byte[]` values**.

~~~text
ProducerRecord
  topic: orders.created
  key: order-42
  value: OrderCreated(...)
  headers:
    x-correlation-id: [UTF-8 bytes]
    x-event-id:       [UTF-8 bytes]
    traceparent:      [bytes managed by tracing instrumentation]
~~~

Kafka clients expose these APIs:

| API | Role |
|---|---|
| `ProducerRecord.headers()` | Add/read headers before publishing |
| `ConsumerRecord.headers()` | Read headers from a received record |
| `Header.key()` | Header name |
| `Header.value()` | Byte array value |
| `Headers.lastHeader(name)` | Get the last header with the given name |
| `Headers.headers(name)` | Get all headers with the given name |
| `RecordHeader` | An implementation for creating a header |

Kafka allows **multiple headers with the same name**. Producers should standardize writes so conflicting `x-correlation-id` headers are never emitted, and consumers must adopt a clear policy when reading duplicate headers.

Headers sit outside the business payload schema. A JSON message might look like:

~~~json
{
  "eventId": "cb7fa3fa-bdfc-4dfa-8a24-121746bfd181",
  "orderId": "order-42",
  "amountCents": 99000
}
~~~

While the separate Correlation ID lives in a Kafka header:

~~~text
x-correlation-id = 5e85d52f-5a98-44f4-b29c-635a8994643f
~~~

However, a Kafka Streams/Connect pipeline, bridge, or custom republisher may **construct a new `ProducerRecord`**. Never assume every intermediary automatically preserves custom headers; test actual propagation.

## 3. Distinguishing correlation ID, event ID, causation ID, and trace ID

Each identifier serves a distinct purpose:

| ID | Scope | Purpose |
|---|---|---|
| **Correlation ID** | A workflow/request spanning multiple steps | Group logs and events belonging to the same flow |
| **Event ID** | A single business event | Audits, inbox/idempotency, deduplication |
| **Causation ID** | The event/command that directly led to the current event | Reconstruct causal relationships |
| **Trace ID** | A distributed trace | Connect spans inside a tracing system |
| **Span ID** | A single operation in a distributed trace | Track an individual execution interval |

Example:

~~~text
Order creation workflow
  correlationId = C1

OrderCreated
  eventId = E1
  correlationId = C1

StockReserved
  eventId = E2
  correlationId = C1
  causationId = E1

PaymentConfirmed
  eventId = E3
  correlationId = C1
  causationId = E2
~~~

Three valid events share the **same correlation ID** while having three distinct event IDs. Using correlation ID as the unique key of an inbox table would cause the listener to process E1 and mistakenly skip E2/E3.

**Correlation ID is not the Kafka record key.** The Kafka key might be `order-42` to guarantee aggregate routing/ordering within a topic; a correlation ID can span multiple aggregates or multiple topics. Never replace the Kafka key with correlation ID when business rules require partitioning by order/account.

Trace ID also does not have to match correlation ID. A workflow replayed days later gets a new trace while keeping the same business correlation ID.

## 4. Defining a clear header contract

Standardize header names across services:

~~~text
x-correlation-id
x-event-id
x-causation-id
~~~

These are **application-chosen names**, not mandatory Kafka headers. A production contract should specify:

1. Exact header name, e.g., `x-correlation-id`.
2. UTF-8 encoding—never platform default charset.
3. Data format: canonical UUID string or bounded opaque ID format.
4. Maximum length and allowed character set.
5. Which entry points are authorized to generate a new ID.
6. When to propagate an existing ID.
7. Missing-header policy: generate a new ID, warn, or reject.
8. Invalid-header / duplicate-header policy.
9. Propagation across retries, DLTs, outbox, bridges, fan-out, and replays.
10. How to emit structured logs, traces, and metrics.
11. Security limits when values arrive from untrusted sources.

Example contract:

~~~text
Name:           x-correlation-id
Encoding:       UTF-8
Format:         UUID string
Max length:     128 bytes
Creation:       HTTP/API or new event source at entry boundary
Propagation:    preserved on downstream events in the same workflow
Missing:        fallback allowed during migration while tracking missing rate
Invalid:        never log raw data, handle per policy
Security:       not an authentication token
~~~

When consumers run across multiple languages (Java, Python, Go), inspect the raw bytes of the same record header to ensure all parties decode identically.

## 5. When to generate a new Correlation ID?

Generate a new ID only when genuinely starting **a new business flow**. For instance, at an HTTP endpoint:

~~~text
External request
    |
    v
Validation/trust boundary
    |
    +-- Valid correlation ID present -> keep or map per policy
    |
    +-- Absent -> generate UUID
    |
    v
Business service
    |
    v
ProducerRecord with x-correlation-id
~~~

When a Kafka consumer reads a record belonging to flow C1 and produces a downstream event, it should preserve C1. If every consumer generates a fresh UUID on every receive, traceability breaks at every hop.

### 5.1. Is a Correlation ID from an HTTP client trustworthy?

Not by default. A header sent by an external client may be overly long, contain newlines, carry sensitive payloads, or deliberately reuse an ID to mix logs across requests.

Options:

- Accept only canonical UUID strings within length bounds.
- Generate a new internal ID and store the external request ID in a separate field.
- If the business contract mandates preserving the external ID, apply validation and enforce a clear trust boundary.

Correlation ID carries zero authorization weight. Never use this ID to select a tenant or bypass authorization checks.

### 5.2. Legacy records missing the header

An older consumer or producer may have written records without `x-correlation-id`. Two policies exist:

- **Compatibility:** on the first processing step where absence is detected, generate C2 to track subsequent hops; log/metric the missing correlation and propagate C2 onward.
- **Strict contract:** treat a missing header as a data error; route the record through appropriate recovery/DLT if processing cannot continue.

Never silently generate a new ID without telemetry, as that hides upstream contract violations.

## 6. Sending Correlation ID with KafkaTemplate and ProducerRecord

The transparent approach is constructing a `ProducerRecord` and adding a `RecordHeader`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    public static final String CORRELATION_HEADER =
        "x-correlation-id";

    private final KafkaTemplate<String, OrderCreated> template;

    public OrderPublisher(
        KafkaTemplate<String, OrderCreated> template
    ) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event,
        String correlationId
    ) {
        ProducerRecord<String, OrderCreated> record =
            new ProducerRecord<>(
                "orders.created",
                event.orderId(),
                event
            );

        record.headers().add(
            new RecordHeader(
                CORRELATION_HEADER,
                correlationId.getBytes(StandardCharsets.UTF_8)
            )
        );

        record.headers().add(
            new RecordHeader(
                "x-event-id",
                event.eventId().toString()
                    .getBytes(StandardCharsets.UTF_8)
            )
        );

        return template.send(record);
    }
}
~~~

This example assumes `OrderCreated` has `orderId()` and `eventId()`; real projects supply matching Kafka serializers.

In Spring Kafka 3.x, `KafkaTemplate.send(ProducerRecord)` returns `CompletableFuture<SendResult<...>>`. Older versions may use a different future type. Never adopt a Java snippet without matching your dependency version.

### 6.1. Send success does not guarantee transaction commit

If the producer runs inside a Kafka transaction, a successful record send future **does not** prove the transaction ultimately committed. The transaction can still abort due to an exception, timeout, or fencing.

Correlation ID helps link producer/transaction logs with downstream events, but never replaces Kafka transactions, idempotent producers, or retry policies.

### 6.2. Keep header sizes reasonable

Header bytes add to Kafka record size. Never stuff entire HTTP headers, JSON requests, or large trace objects into `x-correlation-id`. A UUID string of a few dozen bytes is normally plenty for correlation.

## 7. Reading Correlation ID from ConsumerRecord

A record listener can accept `ConsumerRecord` to inspect raw Kafka headers:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryConsumer {

    @KafkaListener(
        topics = "orders.created",
        groupId = "inventory-service"
    )
    public void onOrder(
        ConsumerRecord<String, OrderCreated> record
    ) {
        Header header =
            record.headers().lastHeader("x-correlation-id");

        String correlationId =
            header == null || header.value() == null
                ? null
                : new String(
                    header.value(),
                    StandardCharsets.UTF_8
                );

        inventoryService.reserve(
            record.value(),
            correlationId
        );
    }
}
~~~

This is the basic read pattern. In production, validate bytes and format before use. Never pass unchecked raw headers into structured logs.

### 7.1. @Header instead of ConsumerRecord

Spring Kafka also supports binding headers into listener parameters via Spring Messaging:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service"
)
public void onOrder(
    OrderCreated event,
    @Header(
        name = "x-correlation-id",
        required = false
    ) byte[] correlationBytes
) {
    String correlationId = correlationBytes == null
        ? null
        : new String(
            correlationBytes,
            StandardCharsets.UTF_8
        );

    inventoryService.reserve(event, correlationId);
}
~~~

Supported bound types and converters depend on the endpoint's header mapper / message converter. When you need raw `byte[]` and control over duplicate header names, `ConsumerRecord.headers()` depends less on mapping behavior.

## 8. Shared helper to encode and decode headers

When multiple producers and consumers share a contract, place the logic in a helper so each component does not pick different encodings and validation rules.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeader;

public final class CorrelationHeaders {

    public static final String NAME = "x-correlation-id";

    private static final int MAX_BYTES = 128;

    private static final Pattern SAFE_ID = Pattern.compile(
        "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
    );

    private CorrelationHeaders() {
    }

    public static void put(Headers headers, String id) {
        validate(id);

        // Leave no duplicate values with the same name on republish.
        headers.remove(NAME);
        headers.add(new RecordHeader(
            NAME,
            id.getBytes(StandardCharsets.UTF_8)
        ));
    }

    public static String read(Headers headers) {
        Header header = headers.lastHeader(NAME);

        if (header == null || header.value() == null) {
            return null;
        }

        byte[] bytes = header.value();

        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException(
                "Invalid correlation header length"
            );
        }

        String id = new String(bytes, StandardCharsets.UTF_8);
        validate(id);
        return id;
    }

    public static void validate(String id) {
        if (id == null || !SAFE_ID.matcher(id).matches()) {
            throw new IllegalArgumentException(
                "Invalid correlation ID format"
            );
        }

        if (id.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES) {
            throw new IllegalArgumentException(
                "Correlation ID exceeds byte limit"
            );
        }
    }
}
~~~

The regex above illustrates a bounded format, not a Kafka standard. If your contract allows only UUIDs, validate canonical UUID strings more strictly.

### 8.1. Duplicate header names

Kafka allows multiple headers with the same name. `lastHeader` reads the last value, yet if a record from an untrusted source carries two conflicting correlation IDs, the consumer needs an explicit policy:

- Reject / route to DLT if conflicting values exist.
- Accept the last value and increment a duplicate-header metric.
- Accept only a single value if the integration contract mandates uniqueness.

The `put()` helper calls `remove(NAME)` before adding to prevent duplicates on the producer side. The reader can add `headers.headers(NAME)` checks as required.

### 8.2. Invalid encoding

`new String(bytes, UTF_8)` replaces malformed bytes with replacement characters. If strict UTF-8 is required, use a `CharsetDecoder` configured with `CodingErrorAction.REPORT`. Never silently rewrite a malformed correlation ID, as that produces an ID differing from upstream.

### 8.3. Do not infinitely retry header errors

If a malformed ID is a permanent error, retrying the same record thousands of times will not make it valid. Classify the exception and route to recovery/DLT or apply a flagged fallback per migration policy.

## 9. Propagating ID through consume–process–produce

A common pattern reads the ID from input and passes it explicitly to the producer output:

~~~mermaid
flowchart LR
    A[orders.created] -->|C1| B[Inventory Consumer]
    B --> C[Reserve Inventory]
    C --> D[stock.reserved]
    D -->|C1| E[Payment Consumer]
    E --> F[payment.confirmed]
~~~

Example:

~~~java
@Component
public class StockConsumer {

    private final StockService stockService;
    private final StockPublisher publisher;

    public StockConsumer(
        StockService stockService,
        StockPublisher publisher
    ) {
        this.stockService = stockService;
        this.publisher = publisher;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "inventory-service"
    )
    public void onOrder(
        ConsumerRecord<String, OrderCreated> record
    ) {
        String correlationId =
            CorrelationHeaders.read(record.headers());

        if (correlationId == null) {
            // Fallback for legacy data; should not stay silent.
            correlationId = UUID.randomUUID().toString();
        }

        StockReserved output =
            stockService.reserveIdempotently(record.value());

        publisher.publish(output, correlationId);
    }
}
~~~

Relevant domain classes, logger, and imports must be supplied by the project. `StockPublisher.publish` must add `x-correlation-id` to the output record using the same helper.

**Reliability note:** when a service writes to a database and emits Kafka output, those two side effects do not commit atomically just because they share a correlation ID. Use inbox/outbox, transactions, or an appropriate consistency design.

### 9.1. Fan-out keeps the same correlation ID

One event E1 may produce E2 and E3:

~~~text
Input E1 / correlation C1
    |
    +--- Output E2 / correlation C1 / causation E1
    |
    +--- Output E3 / correlation C1 / causation E1
~~~

Output event IDs differ while remaining part of business flow C1.

### 9.2. Fan-in from multiple correlation IDs

When a batch aggregator consumes inputs from C1 and C2 and produces a new report, no single old correlation ID fits cleanly.

~~~text
Input A / correlation C1
Input B / correlation C2
           |
           v
     Aggregate report
           |
           v
     New workflow correlation C3
     Provenance: parents C1, C2
~~~

You can assign a fresh ID to the report and store parent IDs in audit/provenance records. Never arbitrarily pick C1 and drop the link to C2.

## 10. Putting correlation ID into logs via MDC

SLF4J's MDC (Mapped Diagnostic Context) lets logs on the same thread include metadata without passing the ID into every log statement.

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.MDC;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service"
)
public void onOrder(
    ConsumerRecord<String, OrderCreated> record
) {
    String correlationId =
        CorrelationHeaders.read(record.headers());

    if (correlationId == null) {
        correlationId = "missing";
    }

    try (MDC.MDCCloseable ignored =
             MDC.putCloseable("correlationId", correlationId)) {

        log.info(
            "Processing order, topic={}, partition={}, offset={}",
            record.topic(),
            record.partition(),
            record.offset()
        );

        inventoryService.reserveIdempotently(record.value());

        log.info("Order processed");
    }
}
~~~

`log` is the class's SLF4J logger. `MDC.putCloseable` ensures cleanup after the callback even if the service throws an exception.

With Logback, the pattern can look like:

~~~xml
<pattern>
  %d{ISO8601} %-5level [%thread]
  trace=%X{traceId} correlation=%X{correlationId}
  %logger - %msg%n
</pattern>
~~~

Or configure a JSON logger to output a `correlationId` field. Use one consistent field name across services to search logs across JVMs.

### 10.1. Why must MDC be cleaned up?

Spring Kafka consumer threads are reused across many records. If a listener calls `MDC.put("correlationId", "C1")` without removing it, the next record may log C1 even though it belongs to workflow C2.

Always use `try/finally` or `MDC.MDCCloseable`. Never allow one record's context to leak into the next record.

### 10.2. Does MDC still exist inside error handler logs?

If the listener throws an exception, `try-with-resources` cleans up MDC as the exception leaves the listener. The error handler/container logs **afterward**, so those logs are not guaranteed to retain C1 from the listener's MDC.

To include correlation IDs in error handler/recoverer logs, read the ID from `ConsumerRecord.headers()` on the recovery path or use a suitably designed interceptor/context lifecycle. Never leave MDC dirty indefinitely on a consumer thread.

## 11. Asynchrony: MDC does not automatically cross to new threads

A common mistake:

~~~java
@KafkaListener(topics = "orders.created")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    String id = CorrelationHeaders.read(record.headers());
    MDC.put("correlationId", id);

    CompletableFuture.runAsync(() -> {
        // Worker thread may not have MDC correlationId.
        log.info("Async stock processing");
    });

    MDC.remove("correlationId");
}
~~~

MDC is typically thread-local. The straightforward, explicit approach is passing the ID as a parameter and setting MDC inside the worker:

~~~java
public CompletableFuture<Void> processAsync(
    OrderCreated event,
    String correlationId,
    Executor executor
) {
    return CompletableFuture.runAsync(() -> {
        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", correlationId)) {
            stockService.reserveIdempotently(event);
        }
    }, executor);
}
~~~

In systems using Micrometer Context Propagation, you can use context capture/restore mechanisms integrated with the executor; still verify that context actually propagates in practice.

**Note:** accurate MDC does not guarantee accurate Kafka offsets. If a listener returns while a task is still running and the container commits on listener return, a process crash can lose side effects. Use version-appropriate async acknowledgment or persist work to a durable queue/inbox before returning from the listener.

## 12. Batch listeners and correlation IDs

One batch callback may contain records from many workflows:

~~~text
Record A -> correlation C1
Record B -> correlation C2
Record C -> correlation C1
Record D -> correlation C3
~~~

Never grab the first record's correlation ID and apply it to the entire batch. When processing sequentially:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "batchListenerFactory"
)
public void onBatch(
    List<ConsumerRecord<String, OrderCreated>> records
) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        String correlationId =
            CorrelationHeaders.read(record.headers());

        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable(
                     "correlationId",
                     correlationId == null ? "missing" : correlationId
                 )) {

            stockService.reserveIdempotently(record.value());
        }
    }
}
~~~

If batch processing shares a single database transaction, you can add a `batchId` to connect logs of that batch execution while still preserving each record's own correlation ID.

If one record fails mid-batch, offset commits and retries must follow batch listener mechanisms such as `DefaultErrorHandler`/`BatchListenerFailedException` where appropriate. Correlation ID only helps investigate the failing record; it does not resolve partial commits on its own.

## 13. RecordInterceptor and centralized context handling

In Spring Kafka, `RecordInterceptor` can inspect records before the listener runs. This helps when many listeners share identical logic:

~~~java
public class CorrelationLoggingInterceptor<K, V>
        implements RecordInterceptor<K, V> {

    @Override
    public ConsumerRecord<K, V> intercept(
        ConsumerRecord<K, V> record,
        Consumer<K, V> consumer
    ) {
        String correlationId =
            CorrelationHeaders.read(record.headers());

        log.debug(
            "Received record correlation={}, topic={}, partition={}, offset={}",
            correlationId,
            record.topic(),
            record.partition(),
            record.offset()
        );

        return record;
    }
}
~~~

This example requires imports for `RecordInterceptor`, `ConsumerRecord`, `Consumer`, and a logger. This interceptor only logs. To manage MDC inside an interceptor, also implement the corresponding lifecycle callbacks (`success`, `failure`, `afterRecord` depending on Spring Kafka version) and ensure exact cleanup.

Never simply call `MDC.put()` inside `intercept()` without cleanup. With concurrent listeners and retry/error paths, that leaks correlation IDs or attaches them to the wrong record.

## 14. How do Correlation ID and distributed tracing differ?

An ID helps search logs, whereas **distributed tracing** also captures timings, parent/child spans, sampling, and trace propagation across service boundaries.

In modern Spring Boot, typical pieces are Micrometer Observation, Micrometer Tracing, and OpenTelemetry or a matching tracer bridge.

~~~mermaid
flowchart LR
    A[HTTP API span] --> B[Kafka producer span]
    B --> C[Kafka consumer span]
    C --> D[Database span]
    C --> E[Kafka producer span]
    E --> F[Downstream consumer span]
~~~

Tracing context travels through Kafka headers using standards such as W3C `traceparent`. Never overwrite `traceparent` with an arbitrary business ID:

~~~text
Invalid:
  traceparent = order-42
~~~

When you need a business correlation ID, use a separate custom `x-correlation-id`. Trace IDs may change when a workflow is replayed, while the business correlation ID remains preserved for auditing and support.

### 14.1. Why do logs need both traceId and correlationId?

- `traceId` leads to the trace of a specific execution.
- `correlationId` links multiple executions or business events belonging to one workflow.
- `eventId` identifies an event across replays/retries.
- Topic/partition/offset locates a specific Kafka record.

A structured log can carry all four pieces of information, provided each has clear semantics.

## 15. Spring Kafka Observation

Spring Kafka 3.x integrates Micrometer Observation for `KafkaTemplate` and listener containers when the registry and instrumentation dependencies are properly configured.

Producer template example:

~~~java
@Bean
public KafkaTemplate<String, OrderCreated> observedTemplate(
    ProducerFactory<String, OrderCreated> factory
) {
    KafkaTemplate<String, OrderCreated> template =
        new KafkaTemplate<>(factory);

    template.setObservationEnabled(true);
    return template;
}
~~~

Container factory example:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        observedListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {
    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setObservationEnabled(true);

    return factory;
}
~~~

Configure `ObservationRegistry`, tracing bridge/exporter, and listener factory wiring appropriate for your actual Spring Boot/Spring Kafka version. Some configuration may be auto-configured by Boot, though property names are not identical across every version.

**Enabling Observation does not mean the framework auto-generates a business `x-correlation-id`.** Tracing context and correlation headers are two separate integrations that must be tested independently.

### 15.1. Testing tracing propagation

An integration test should verify the producer actually writes tracing headers, the consumer extracts context, logs contain `traceId`/`spanId`, and custom C1 still carries through downstream events. Do not merely check that the trace exporter connects and assume messaging propagation is complete.

## 16. Do not overwrite request/reply KafkaHeaders.CORRELATION_ID

Spring Kafka includes `ReplyingKafkaTemplate` for Kafka request/reply. The framework uses a correlation token, commonly accessed via `KafkaHeaders.CORRELATION_ID`, to match replies to waiting requests.

That token **is not necessarily the business correlation ID**.

~~~text
Business workflow:
  x-correlation-id = C1

Kafka request/reply A:
  framework correlation token = T1

Kafka request/reply B:
  framework correlation token = T2

Requests A and B may share C1 yet need distinct T1/T2
so ReplyingKafkaTemplate matches replies accurately.
~~~

Never use `x-correlation-id` to replace the request/reply correlation token, and never overwrite `KafkaHeaders.CORRELATION_ID` with C1 when the framework manages that field.

If an application constructs reply `ProducerRecord` instances manually, preserve the reply headers required by the request/reply protocol (such as reply topic/partition and token), while copying the custom business correlation ID if needed.

## 17. Correlation ID during blocking retries

With Spring Kafka's `DefaultErrorHandler`, a listener can retry the same record after transient errors.

~~~text
orders.created, partition 1, offset 220
  x-correlation-id = C1

Attempt 1 -> database timeout
Attempt 2 -> database timeout
Attempt 3 -> success
~~~

Every attempt for the same business event should use C1. Never generate C2/C3 just because the listener is retrying.

When a record is redelivered, the original record's headers remain the metadata source for logging. Ensure error handlers/recoverers can read the header once the listener's MDC has been cleaned up.

Desired logs:

~~~text
correlation=C1 event=E1 attempt=1 failed
correlation=C1 event=E1 attempt=2 failed
correlation=C1 event=E1 attempt=3 completed
~~~

Kafka headers do not replace retry metadata; track attempt index, exception category, and timing separately where needed.

## 18. Correlation ID across retry topics and DLTs

With non-blocking retry topics for record listeners, failed records are published to retry topics and consumed after a delay. If retries exhaust, records can move to a DLT.

~~~text
orders.created
  x-correlation-id = C1
       |
       v
orders.created-retry-...
  x-correlation-id = C1
       |
       v
orders.created-dlt
  x-correlation-id = C1
~~~

This is the **intended propagation contract behavior**. Kafka retry infrastructure can copy original headers and append metadata, though custom producers, recoverers, message converters, or bridges may alter headers.

Verify in real tests that:

1. The input record carries C1.
2. The retry record still carries C1.
3. The DLT record still carries C1.
4. Event ID still identifies the same business event.
5. Retry topics may assign new topic/partition/offset, so never use them instead of event identity.
6. Recovery logs record source topic, source offset, and correlation ID.
7. DLT replays retain C1 per policy and get a separate replay attempt identity if needed.

Spring Kafka non-blocking retry has restrictions across listener modes; in particular, do not assume `@RetryableTopic` directly supports batch listeners.

### 18.1. DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` sends failed records to a DLT, appending source and exception metadata. Do not assume every custom header is preserved automatically if you configured custom header mapping or a custom record creator.

If an incident finds C1 missing in the DLT, check the recoverer/template before concluding the original producer omitted the ID.

## 19. Correlation ID, Kafka transactions, and Idempotency

Correlation ID is metadata. It does **not** guarantee:

- Exactly-once processing.
- Atomic commits across records.
- Ordering across Kafka topics.
- Successful consumer group offset commits.
- Database transaction commits.
- Absence of duplicate side effects.
- That all records sharing the ID belong to the same Kafka transaction.

Example of two Kafka transactions:

~~~text
Transaction T1:
  E2 StockReserved, correlation C1
  E3 StockAudit, correlation C1

Transaction T2:
  E4 PaymentConfirmed, correlation C1
~~~

Even with the same C1, T1 and T2 remain two separate transactions.

If producer/consumer retries redeliver E2, you need `eventId=E2` and an inbox/unique constraint to prevent duplicates. Never use C1 as an inbox unique key when multiple events E1, E2, E3 belong to that workflow.

## 20. Inbox and Outbox must store IDs properly

### 20.1. Inbox

For Kafka → database:

~~~text
Consumer receives E1, C1
  |
  v
Database transaction
  INSERT inbox(event_id=E1)
  UPDATE business tables
  COMMIT
~~~

The inbox should be unique by event ID or an appropriate business operation ID—not correlation ID. Making C1 the unique key would cause other events in the same workflow to be skipped.

### 20.2. Outbox

When a business service writes an outbox row so a Kafka publisher emits the event after database commit, the correlation ID must be persisted **durably** in the outbox:

~~~text
outbox_row:
  event_id       = E2
  aggregate_id   = order-42
  event_type     = StockReserved
  correlation_id = C1
  payload        = ...
~~~

A publisher running on another thread/process reads C1 from the row and adds it to the Kafka header. Never rely solely on the HTTP thread's MDC at order creation time: thread context does not survive across job boundaries.

### 20.3. Crash window

If the database commits successfully before Kafka publishing or offset commits complete, the Kafka record may be re-sent. Correlation ID helps trace retries but does not eliminate duplicates. You still need outbox publisher idempotency and consumer inbox/unique constraints.

## 21. HTTP ↔ Kafka boundary

### 21.1. HTTP → Kafka

~~~text
HTTP request
  X-Correlation-ID: C1
        |
        v
HTTP filter/controller
  validate or generate C1
        |
        v
Business service passes C1
        |
        v
Kafka ProducerRecord
  x-correlation-id: C1
~~~

If the event is published immediately on the HTTP thread, you can log C1 via MDC. If published via an outbox or separate job, persist C1 in durable storage for the publisher to retrieve.

### 21.2. Kafka → HTTP

~~~text
Kafka input record header x-correlation-id=C1
        |
        v
Listener/business service
        |
        v
External HTTP request
  X-Correlation-ID: C1, if external API contract allows
~~~

An external API may assign its own request ID. In that case, store a mapping between internal C1 and the external request ID rather than overwriting IDs arbitrarily.

For external services, check PII/trust policies before forwarding any header.

## 22. Security: never trust correlation headers blindly

A correlation header can be freely crafted by any producer authorized to write to a topic or an external client at an entry boundary.

Safeguards:

- Validate format, characters, and byte length.
- Strip newlines/control characters to mitigate log injection.
- Never use emails, phone numbers, tokens, or session cookies as IDs.
- Never use correlation IDs as authentication tokens.
- Never grant tenant access based on this header.
- Never log the entire header collection if sensitive headers are present.
- Protect access to logs, traces, and DLTs.
- Separate external IDs from internal IDs when trust boundaries require it.
- Enforce a duplicate-header-names policy.
- Never construct a correlation string from the entire payload.

Even an opaque UUID without direct personal data can be used to look up order/payment records in logs, so it still requires protection under your system's data policies.

## 23. Metrics and structured logs

Metrics worth tracking:

| Metric | Purpose |
|---|---|
| Missing correlation header count | Detect producers/bridges violating the contract |
| Invalid correlation header count | Detect encoding/format/length violations |
| Duplicate correlation header count | Detect ambiguity |
| Producer propagation success | Measure ratio of outputs carrying valid headers |
| Retry/DLT propagation coverage | Ensure error traceability |
| Listener processing duration | Spot slow steps |
| Consumer lag | Monitor backlog |
| DLT count | Measure unprocessable errors |
| Trace sampling/export errors | Detect lost tracing telemetry |

Never turn correlation ID into a **Prometheus label**. Every workflow gets its own ID, causing cardinality to grow rapidly. Labels should include service, topic, consumer group, and header status such as `present`, `missing`, `invalid`.

Sample JSON log:

~~~json
{
  "service": "inventory-service",
  "groupId": "inventory-service",
  "topic": "orders.created",
  "partition": 2,
  "offset": 1045,
  "eventId": "cb7fa3fa-bdfc-4dfa-8a24-121746bfd181",
  "correlationId": "5e85d52f-5a98-44f4-b29c-635a8994643f",
  "traceId": "00112233445566778899aabbccddeeff",
  "stage": "reserve-stock",
  "outcome": "success"
}
~~~

Logs should carry event ID and topic/partition/offset to pinpoint the exact record. A single correlation ID can span hundreds of events; without event ID, distinguishing retries of one event from multiple distinct events in the same workflow becomes hard.

## 24. Runbook when a flow loses Correlation ID

If Order API logs C1 yet Payment Consumer has no logs matching C1:

1. Locate the initial record by event ID / topic / partition / offset.
2. Verify the producer added `x-correlation-id=C1` to `ProducerRecord`.
3. Confirm Kafka producer send and transaction commit succeeded where applicable.
4. Read the record from the topic using an appropriately authorized tool/test consumer to inspect raw headers.
5. Verify Inventory Consumer received C1 accurately.
6. Check whether header validation rejected or overwrote the ID.
7. Verify the `stock.reserved` publisher copied C1 to its output.
8. Check whether an outbox, bridge, Kafka Streams, Connect, or converter created a new record.
9. Verify retry topics/DLTs preserve the header.
10. Distinguish an ID lost inside the Kafka record from MDC lost on an async thread.
11. Confirm the log schema uses `correlationId` consistently.
12. If tracing is enabled, use the prior step's `traceId` to pinpoint where context propagation dropped.
13. Verify the request/reply framework correlation header was not overwritten.
14. Fix the failing boundary and add an integration test for the drop scenario.
15. Never reset Kafka offsets or replay production data solely to locate a correlation ID.

Log tracing exists for investigation; production recovery/replay actions require their own runbooks and side-effect controls.

## 25. Unit testing the header helper

A unit test without a Kafka broker:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;

class CorrelationHeadersTest {

    @Test
    void roundTripUtf8() {
        var headers = new RecordHeaders();

        String id = "5e85d52f-5a98-44f4-b29c-635a8994643f";

        CorrelationHeaders.put(headers, id);

        assertEquals(
            id,
            CorrelationHeaders.read(headers)
        );

        assertArrayEquals(
            id.getBytes(StandardCharsets.UTF_8),
            headers.lastHeader(CorrelationHeaders.NAME).value()
        );
    }

    @Test
    void rejectsControlCharacters() {
        var headers = new RecordHeaders();

        assertThrows(
            IllegalArgumentException.class,
            () -> CorrelationHeaders.put(headers, "bad\nid")
        );
    }

    @Test
    void overwritesExistingCorrelationHeader() {
        var headers = new RecordHeaders();

        CorrelationHeaders.put(headers, "flow-1");
        CorrelationHeaders.put(headers, "flow-2");

        assertEquals(
            "flow-2",
            CorrelationHeaders.read(headers)
        );
    }
}
~~~

Tests can also assert that only a single header entry exists for the name, enforce byte-length limits, and verify missing-header and duplicate-input policies.

## 26. Integration testing Kafka propagation

Using EmbeddedKafka, Testcontainers Kafka, or a test cluster:

1. Create E1 with C1.
2. Publish E1 to `orders.created` with the header.
3. Wait for Inventory Consumer to receive it.
4. Confirm the consumer reads C1 and produces a new E2.
5. Read output record E2 from `stock.reserved` with a test consumer.
6. Assert `E2 != E1` while correlation ID remains C1.
7. Have the downstream listener publish E3 and confirm C1 is still preserved.
8. Trigger a retryable error; confirm attempts retain C1.
9. Exhaust retries and read the DLT; confirm the custom header still carries C1.
10. Test missing and invalid headers under compatibility/strict policies.
11. Test duplicate header names; confirm policy is unambiguous.
12. Test MDC leaks using two records with C1 and C2.
13. Test that async executors do not drop log context.
14. Test that an outbox publisher restart still reads C1 from the DB row.
15. If Observation is enabled, verify trace context works independently of business correlation ID.

**Do not test only the encode/decode helper.** If the system uses custom DLT recoverers/bridges, test real records flowing through Kafka to confirm headers are actually preserved.

### 26.1. Batch test

Send a batch containing records with C1 and C2 and verify the listener uses each record's own correlation ID rather than assigning C1 to the whole batch.

### 26.2. Replay test

Replay E1 from the DLT with correlation C1 and verify business idempotency and traceability. You can generate a separate `replayExecutionId` to distinguish the new run; never alter the business event ID just to count retries.

## 27. Common implementation mistakes

**Setting MDC only at the HTTP entry point without adding a Kafka header:** consumers in another process cannot read the HTTP thread's thread-local.

**Generating a new correlation ID at every hop:** logs cannot be connected across services.

**Using correlation ID as event ID or inbox unique key:** skips valid subsequent events in the same workflow.

**Using correlation ID as Kafka key regardless of ordering requirements:** breaks per-aggregate partitioning.

**Reading headers as Strings without checking encoding:** Kafka header values are raw bytes.

**Ignoring multiple headers with the same name:** picks the wrong ID or accepts untrusted values.

**Passing request/reply `KafkaHeaders.CORRELATION_ID` as a business ID:** can break response matching.

**Setting `traceparent` to an arbitrary UUID:** breaks W3C tracing format.

**Forgetting to copy the ID when creating a new `ProducerRecord`:** outbox, Kafka Streams, Connect, or bridges drop metadata.

**Failing to preserve the ID through the DLT:** incidents cannot correlate failure logs with recovery logs.

**Setting MDC without cleanup:** reused consumer threads stamp subsequent logs with the wrong ID.

**Using async executors without propagating context:** logs lose correlation ID.

**Thinking MDC makes offset commits safe:** correctness and observability are separate problems.

**Attaching correlation ID as a Prometheus label:** causes massive cardinality.

**Using correlation ID for authorization:** headers are unauthenticated.

**Logging all headers/payloads:** risks leaking PII or secrets.

**Assuming same correlation ID means same Kafka transaction:** headers do not define transaction boundaries.

**Omitting the ID from the outbox table:** outbox publishers running outside the original thread break propagation.

## 28. Quick decision table

| Goal | What to do | What to avoid |
|---|---|---|
| Link a workflow across multiple events | `x-correlation-id` | Generating a new ID per hop |
| Deduplicate a single event | `eventId` / inbox unique key | Uniqueness by correlation ID |
| Reconstruct causal history | `x-causation-id` | Confusing with trace/span ID |
| Kafka producer adds header | `ProducerRecord.headers().add` | Assuming custom headers auto-generate |
| Consumer reads header | `ConsumerRecord.headers()` | Ignoring byte encoding / duplicate headers |
| Logging | MDC with cleanup, structured logs | Leaking thread-locals |
| Async tasks | Pass ID / context propagation | Committing offsets early |
| Distributed tracing | Micrometer/OpenTelemetry | Overwriting `traceparent` |
| Request/reply | Keep framework correlation token | Overwriting `KafkaHeaders.CORRELATION_ID` |
| Retry/DLT | Preserve custom header on recovery path | Assuming every mapper auto-copies |
| Outbox | Persist ID durably in outbox row | Relying on old thread's MDC |
| Monitoring | Count missing/invalid headers by topic/service | Per-ID metric labels |
| External input | Validate and enforce trust boundary | Treating header as auth |
| Production diagnosis | Event ID + C1 + topic/partition/offset | Resetting offsets when trace is missing |

## 29. Production operating principles

- Pick one stable header name, encoding, and clear format.
- Generate Correlation ID at entry boundaries; preserve it across downstream Kafka events.
- Separate correlation ID, event ID, causation ID, and trace ID.
- Validate untrusted data; bound sizes and exclude PII.
- Use a shared encode/decode helper for consistent behavior.
- Read raw Kafka headers when needed to avoid message converter dependencies.
- Use MDC/structured logs, cleaning up after every record.
- Pass IDs explicitly to async workers rather than relying on thread-locals.
- Ensure retry/DLT and outbox preserve correlation ID across the lifecycle.
- Reserve `KafkaHeaders.CORRELATION_ID` for Spring Kafka request/reply when used by the framework.
- Enable Observation/Tracing for your exact version and let tracing instrumentation own trace context.
- Never substitute correlation ID for Kafka transactions, business idempotency, or offset correctness.
- Never attach correlation ID as a metric label.
- Test multi-hop, retry, DLT, async, batch, replay, and restart scenarios.
- Maintain a runbook for investigating when a step loses its correlation header.

## 30. Conclusion

**Correlation ID in Kafka headers** is a foundational mechanism for observing event-driven chains in Spring Kafka. Because headers store raw bytes, you need a clear contract covering name, encoding, format, and validation. Producers must attach the ID, consumers must read and forward it, and retry/DLT, batch, outbox, and async steps must preserve the ID across the intended business scope.

Correlation ID connects logs across processes and topics, yet does not by itself provide distributed tracing, ordering, exactly-once delivery, or database idempotency. Paired with structured logging, Micrometer/OpenTelemetry, proper error handling, and clean transaction boundaries, it makes production systems far easier to trace and recover from incidents.
