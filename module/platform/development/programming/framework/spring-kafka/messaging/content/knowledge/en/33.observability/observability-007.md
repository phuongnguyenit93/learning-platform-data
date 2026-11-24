# Correlation ID in logs

## 1. Why is a Correlation ID needed in logs?

In a Spring Kafka system, a single business process can span multiple services and multiple topics. For example, an API receives an order creation request, Order service writes an `OrderCreated` event, Inventory service reserves stock, Payment service handles payment, and Notification service sends an alert. Each service maintains its own logs and each consumer processes records on its own thread.

When a step fails, searching solely by topic name or timestamp is often insufficient to connect logs belonging to the same business flow. A Correlation ID is an identifier propagated alongside messages across services to group related logs together.

```text
HTTP request
  correlationId = c-8a91
       |
       v
Order service
  log: order accepted, correlationId=c-8a91
       |
       | Kafka record + x-correlation-id=c-8a91
       v
orders topic
       |
       v
Inventory service
  log: stock reserved, correlationId=c-8a91
       |
       | Kafka record + x-correlation-id=c-8a91
       v
payments topic
       |
       v
Payment service
  log: payment declined, correlationId=c-8a91
```

When searching for `c-8a91` in a centralized logging system, operators can view all related processing steps even though they live across multiple applications.

Correlation IDs are especially helpful when:

- One request produces multiple Kafka events or multiple processing steps.
- Many records are processed concurrently and logs interleave.
- A consumer retries or routes a record to a dead-letter topic (DLT).
- A service receives an event and emits subsequent events.
- You need to investigate a specific business transaction across multiple services.

## 2. Distinguishing Correlation ID, Trace ID, Request ID, and Event ID

These identifiers can appear together in logs, yet they serve different purposes:

| Identifier | Scope | Purpose |
|---|---|---|
| Correlation ID | A business flow or related request | Groups logs and messages belonging to the same processing flow |
| Trace ID | A distributed trace | Links spans and shows timing relationships across services |
| Request ID | A single API call or command | Identifies a request at ingress and for auditing |
| Event ID | A specific event | Deduplication, idempotency, and event traceability |
| Kafka key | A Kafka record | Selects partition and preserves ordering by key within a partition |

For example, an order creation request may emit `OrderCreated`, `InventoryReserved`, and `PaymentRequested`. All three events can share the same correlation ID because they belong to the same business flow, while each event has its own event ID. If the system starts a new trace per consumer message, trace IDs may differ while still carrying the same correlation ID to link the business flow.

Do not use correlation ID instead of event ID in an idempotency table. A correlation ID can appear on multiple valid events; deduplicating by correlation ID can cause consumers to mistakenly drop distinct events within the same flow.

Nor is correlation ID a trace context. When distributed tracing is needed, propagate W3C Trace Context (`traceparent`, `tracestate`) or the format used by your tracing system. Correlation ID supports business search in logs; trace ID supports span, latency, and dependency analysis.

## 3. Choosing header names and Kafka transmission conventions

For standard event-driven flows, you can use a dedicated business header, such as:

```text
x-correlation-id
```

This is an application-defined header name. Standardize the name, encoding, and ID generation rules across services. Use UTF-8 for string values so different languages can read the same header consistently.

Spring Kafka also provides the constant `KafkaHeaders.CORRELATION_ID`. That header is used by default for request-reply, especially with `ReplyingKafkaTemplate`. When using request-reply, do not overwrite the value Spring Kafka uses to match responses to requests. For business event flow correlation IDs, a separate `x-correlation-id` header keeps the two purposes distinct.

A Kafka header is a name and byte array pair. Header names can repeat, so applications should establish a convention of sending only one correlation ID value per record. On the receiving side, `lastHeader(name)` retrieves the last value if multiple headers share the same name. If unexpected duplicate headers are detected, log a warning and either reject or select a value according to the agreed contract.

## 4. Generating Correlation IDs at request ingress

A correlation ID should be generated at ingress if the incoming request lacks a trustworthy ID. If a client sends an ID via an HTTP header, the application can accept it after validating format and length.

Simple helper example:

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.regex.Pattern;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public final class CorrelationIds {

    public static final String HEADER = "x-correlation-id";
    public static final String MDC_KEY = "correlationId";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    private CorrelationIds() {
    }

    public static String resolve(String supplied) {
        if (supplied != null && SAFE_ID.matcher(supplied).matches()) {
            return supplied;
        }
        return UUID.randomUUID().toString();
    }

    public static String readFrom(ConsumerRecord<?, ?> record) {
        Header header = record.headers().lastHeader(HEADER);
        if (header == null || header.value() == null) {
            return null;
        }
        return new String(header.value(), StandardCharsets.UTF_8);
    }
}
```

Restricting characters prevents log injection via newlines or malformed strings. If generated by the application, UUID is a simple choice. Some systems use ULIDs or IDs issued by an API gateway; what matters is uniqueness within the search scope and consistent propagation.

Do not use emails, phone numbers, access tokens, or personal data as correlation IDs. The ID should be an opaque value containing no secrets or sensitive information.

Example at an HTTP controller/service where, after resolving the ID, the application attaches it to the Kafka record:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class OrderCommandService {

    private static final Logger log = LoggerFactory.getLogger(OrderCommandService.class);
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderCommandService(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event, String incomingCorrelationId) {

        String correlationId = CorrelationIds.resolve(incomingCorrelationId);
        ProducerRecord<String, OrderCreated> record = new ProducerRecord<>(
                "orders", event.orderId(), event);

        record.headers().add(new RecordHeader(
                CorrelationIds.HEADER,
                correlationId.getBytes(StandardCharsets.UTF_8)));

        try (MdcScope ignored = MdcScope.with(CorrelationIds.MDC_KEY, correlationId)) {
            log.info("Publishing order event: orderId={}", event.orderId());
            return kafkaTemplate.send(record);
        }
    }
}
```

In systems with multiple producer paths, encapsulate header attachment in a shared publisher/helper so some events do not end up with correlation IDs while others are missing them.

The `CompletableFuture` declaration above uses Spring Kafka 3.0 or later. In Spring Kafka 2.x, `KafkaTemplate.send()` returns `ListenableFuture`; adjust the return type or convert the future according to your project's version API.

The MDC scope in the example wraps only the `send()` call and the synchronous log before sending. Send completion is asynchronous; if you need to log inside the future callback, capture `correlationId` and open a new MDC scope inside the callback because the calling thread's MDC does not automatically propagate to the producer callback thread.

## 5. Reading Correlation IDs from ConsumerRecord

`@KafkaListener` can accept `ConsumerRecord<K,V>` directly. This is a clear way to read native Kafka headers, especially when handling raw byte arrays or checking for missing headers.

```java
@Component
public class OrderListener {

    private static final Logger log = LoggerFactory.getLogger(OrderListener.class);

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders", groupId = "inventory-service")
    public void onOrder(ConsumerRecord<String, OrderCreated> record) {
        String correlationId = CorrelationIds.readFrom(record);

        log.info("Received order event: topic={}, partition={}, offset={}, correlationId={}",
                record.topic(), record.partition(), record.offset(), correlationId);

        orderService.reserveStock(record.value());
    }
}
```

This snippet demonstrates reading and logging the ID. In production, place the correlation ID into MDC or Observation context so logs inside `orderService` automatically include the same field, rather than passing the parameter through every log call.

If using Spring Message conversion instead of `ConsumerRecord`, you can receive the header with `@Header`:

```java
@KafkaListener(topics = "orders", groupId = "inventory-service")
public void onOrder(
        OrderCreated event,
        @Header(name = "x-correlation-id", required = false) byte[] correlationHeader) {

    String correlationId = correlationHeader == null
            ? null
            : new String(correlationHeader, StandardCharsets.UTF_8);

    orderService.reserveStock(event, correlationId);
}
```

Header conversion behavior depends on the message converter and header mapper. When you need exact control over native header bytes or repeated headers, receiving `ConsumerRecord` directly is more straightforward.

## 6. Putting Correlation ID into MDC

MDC (Mapped Diagnostic Context) is SLF4J's mechanism for attaching contextual values to log events. With Logback, patterns can read MDC values using `%X{correlationId}`.

If you only log the correlation ID in a single statement, you can pass it as a log field. But when a service calls multiple components that all write logs, MDC automatically adds the ID to all synchronous logs on the same thread.

Example helper for saving and restoring MDC:

```java
import org.slf4j.MDC;

public final class MdcScope implements AutoCloseable {

    private final String key;
    private final String previousValue;

    private MdcScope(String key, String value) {
        this.key = key;
        this.previousValue = MDC.get(key);

        if (value == null) {
            MDC.remove(key);
        } else {
            MDC.put(key, value);
        }
    }

    public static MdcScope with(String key, String value) {
        return new MdcScope(key, value);
    }

    @Override
    public void close() {
        if (previousValue == null) {
            MDC.remove(key);
        } else {
            MDC.put(key, previousValue);
        }
    }
}
```

Usage inside a listener:

```java
@KafkaListener(topics = "orders", groupId = "inventory-service")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    String correlationId = CorrelationIds.readFrom(record);

    try (MdcScope ignored = MdcScope.with(CorrelationIds.MDC_KEY, correlationId)) {
        log.info("Start processing orderId={}", record.value().orderId());
        orderService.reserveStock(record.value());
        log.info("Finished processing orderId={}", record.value().orderId());
    }
}
```

`try-with-resources` guarantees MDC restoration even when the service throws an exception. Restoring the previous value is also safer than calling `MDC.clear()`, because the thread may already hold other MDC keys set by tracing or the framework.

## 7. Automatically setting MDC with RecordInterceptor

If you want the correlation ID available before the listener method executes, you can use `RecordInterceptor`. The interceptor is invoked before the listener and provides callbacks after the listener completes normally or throws an exception.

Since Spring Kafka 2.8, `afterRecord()` is invoked after `success()` or `failure()`. This is the right place to restore MDC on a reused consumer thread.

```java
@Component
public class CorrelationMdcInterceptor
        implements RecordInterceptor<String, OrderCreated> {

    private static final String MDC_KEY = "correlationId";
    private final ThreadLocal<String> previousValue = new ThreadLocal<>();

    @Override
    public ConsumerRecord<String, OrderCreated> intercept(
            ConsumerRecord<String, OrderCreated> record,
            Consumer<String, OrderCreated> consumer) {

        previousValue.set(MDC.get(MDC_KEY));
        String correlationId = CorrelationIds.readFrom(record);

        if (correlationId == null) {
            MDC.remove(MDC_KEY);
        } else {
            MDC.put(MDC_KEY, correlationId);
        }

        return record;
    }

    @Override
    public void afterRecord(
            ConsumerRecord<String, OrderCreated> record,
            Consumer<String, OrderCreated> consumer) {

        String previous = previousValue.get();
        if (previous == null) {
            MDC.remove(MDC_KEY);
        } else {
            MDC.put(MDC_KEY, previous);
        }
        previousValue.remove();
    }

}
```

Register the interceptor on the listener container factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> orderListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        CorrelationMdcInterceptor correlationMdcInterceptor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setRecordInterceptor(correlationMdcInterceptor);
    return factory;
}
```

Listener using this factory:

```java
@KafkaListener(
        topics = "orders",
        groupId = "inventory-service",
        containerFactory = "orderListenerFactory")
public void onOrder(OrderCreated event) {
    log.info("Processing orderId={}", event.orderId());
    orderService.reserveStock(event);
}
```

In this example, `ThreadLocal` stores the prior MDC value before the interceptor writes the new correlation ID. `afterRecord()` restores the prior value and removes the `ThreadLocal` entry so no data is retained across records. Calling `MDC.put()` without cleanup can cause the next record on the same consumer thread to log the previous record's correlation ID by mistake.

In Spring Kafka 2.7, `success()` and `failure()` exist while `afterRecord()` does not yet; cleanup can be performed in both callbacks. From 2.8 onward, use `afterRecord()` to centralize cleanup in one place. Do not let this interceptor return `null`; returning `null` skips the record and the listener will not run.

## 8. MDC and thread reuse in consumer concurrency

`KafkaMessageListenerContainer` processes records on a single consumer thread. `ConcurrentMessageListenerContainer` creates multiple child containers for parallel processing; each child has its own consumer thread.

MDC is `ThreadLocal`-based. That means:

- During a single synchronous listener invocation, logs on the same thread see the same correlation ID.
- With multi-consumer concurrency, each thread has its own MDC.
- Consumer threads are reused across many records, so MDC must be cleared or restored after each record.
- MDC does not automatically propagate to thread pools, `@Async`, `CompletableFuture` callbacks, or other schedulers.

If a service starts asynchronous work, pass the correlation ID explicitly into the task or use Micrometer Context Propagation/Observation to capture and restore context. Do not assume the consumer thread's MDC automatically appears on background worker threads.

Example passing the ID explicitly:

```java
String correlationId = MDC.get("correlationId");
executor.execute(() -> {
    try (MdcScope ignored = MdcScope.with("correlationId", correlationId)) {
        backgroundService.run();
    }
});
```

When using a shared executor, always clean up MDC inside the task using a similar scope. Thread pools also reuse threads, so context leakage bugs can occur there as well.

## 9. Configuring Logback to print Correlation ID

Once MDC is populated, the Logback pattern can include the correlation ID field:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] corr=%X{correlationId:-none} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Logs can look like this:

```text
2026-11-17T10:15:22.105+07:00 INFO  [org.springframework.kafka.KafkaListenerEndpointContainer#0-0-C-1] corr=c-8a91 OrderService - Start processing orderId=ORD-42
2026-11-17T10:15:22.143+07:00 INFO  [org.springframework.kafka.KafkaListenerEndpointContainer#0-0-C-1] corr=c-8a91 InventoryService - Stock reserved for orderId=ORD-42
```

`%X{correlationId:-none}` prints `none` when MDC does not have the key. This prevents an empty field in logs and alerts operators when a message arrived without a correlation ID.

If using a JSON encoder, configure the MDC key to output as a discrete `correlationId` JSON field instead of merely appending it to the message text. Structured logging makes log platform filtering and querying by field more accurate.

## 10. Using @Header instead of ConsumerRecord

If the listener only needs the payload and correlation ID without the full native record, you can accept the header directly:

```java
@KafkaListener(topics = "orders", groupId = "inventory-service")
public void onOrder(
        OrderCreated event,
        @Header(name = "x-correlation-id", required = false) byte[] rawCorrelationId) {

    String correlationId = rawCorrelationId == null
            ? null
            : new String(rawCorrelationId, StandardCharsets.UTF_8);

    try (MdcScope ignored = MdcScope.with("correlationId", correlationId)) {
        log.info("Received orderId={}", event.orderId());
        orderService.reserveStock(event);
    }
}
```

When using `@Header`, the header mapper/converter participates in converting native Kafka headers into Spring Message headers. If your application needs exact raw bytes or needs to inspect repeated headers, accepting `ConsumerRecord` directly gives tighter control.

Other record metadata can also be injected via `@Header`, such as `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.RECEIVED_PARTITION`, and `KafkaHeaders.OFFSET`. These metadata fields are helpful for logging the Kafka position alongside the correlation ID.

## 11. Writing Correlation ID when publishing follow-up events

When a consumer receives an event and publishes a new event, the correlation ID should be forwarded. Do not generate a new correlation ID at every hop if the events belong to the same business flow.

Example:

```java
public void publishInventoryReserved(
        ConsumerRecord<String, OrderCreated> inbound,
        InventoryReserved event) {

    Header inboundHeader = inbound.headers().lastHeader(CorrelationIds.HEADER);
    String correlationId = inboundHeader == null || inboundHeader.value() == null
            ? UUID.randomUUID().toString()
            : new String(inboundHeader.value(), StandardCharsets.UTF_8);

    ProducerRecord<String, InventoryReserved> outbound = new ProducerRecord<>(
            "inventory.reserved", event.orderId(), event);
    outbound.headers().add(new RecordHeader(
            CorrelationIds.HEADER,
            correlationId.getBytes(StandardCharsets.UTF_8)));

    kafkaTemplate.send(outbound);
}
```

If the correlation ID was already resolved in a listener/interceptor, it can be read from the current context or passed as a parameter. Explicit passing is often easier to test when services perform async processing. Either way, ensure the ID is not altered between hops.

If starting an independent sub-workflow, you may generate a new correlation ID and store the parent ID in a separate header such as `causation-id` or `parent-correlation-id` per your organization's event contract. Do not arbitrarily swap IDs when the event still belongs to the same transaction.

## 12. Correlation ID in retries and dead-letter topics

When a listener fails, the same record may be delivered multiple times. The correlation ID must remain present in logs for every attempt so operators can link the initial execution, retries, and recovery.

Example logs:

```text
INFO  corr=c-8a91 orderId=ORD-42 attempt=1 Processing order
WARN  corr=c-8a91 orderId=ORD-42 attempt=1 Inventory service unavailable
INFO  corr=c-8a91 orderId=ORD-42 attempt=2 Retrying order
ERROR corr=c-8a91 orderId=ORD-42 attempt=2 Sending record to orders.DLT
```

You can read the delivery attempt header provided by Spring Kafka when `deliveryAttemptHeader` is enabled on the listener container. Correlation ID and delivery attempt serve different roles: correlation ID links the business flow; delivery attempt indicates which delivery attempt the listener received under the active retry mechanism.

When using `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`, verify with an integration test that custom correlation headers are preserved on DLT records. If a custom recoverer builds a new `ProducerRecord`, copy the correlation ID header to the target record. Do not assume a custom publisher automatically preserves all headers.

With retry topics (`@RetryableTopic`), business headers should be preserved as records move across retry topics. Test the original header, retry metadata, and DLT to confirm dashboards/logs can locate the same correlation ID throughout the chain.

## 13. Correlation ID in request-reply

Spring Kafka uses `KafkaHeaders.CORRELATION_ID` by default so `ReplyingKafkaTemplate` can match responses to waiting requests. The responder must echo this header back in the reply. The header has native type `byte[]`.

If request-reply flows also need a business correlation ID in logs, you can:

- Carry the business ID in a custom `x-correlation-id` header while keeping `KafkaHeaders.CORRELATION_ID` dedicated to the reply protocol.
- Or use `KafkaHeaders.CORRELATION_ID` as the sole ID if your application contract explicitly defines that value as both the protocol and business correlation ID.

Do not overwrite `KafkaHeaders.CORRELATION_ID` while `ReplyingKafkaTemplate` is managing a Future. Changing that value prevents the response from matching the request and causes the Future to time out.

Example listener receiving both:

```java
import java.util.Base64;

@KafkaListener(topics = "order.requests", groupId = "order-query")
@SendTo
public OrderReply handle(
        OrderRequest request,
        @Header(KafkaHeaders.CORRELATION_ID) byte[] requestReplyId,
        @Header(name = "x-correlation-id", required = false) byte[] businessCorrelationId) {

    String correlationId = businessCorrelationId == null
            ? Base64.getUrlEncoder().withoutPadding().encodeToString(requestReplyId)
            : new String(businessCorrelationId, StandardCharsets.UTF_8);

    try (MdcScope ignored = MdcScope.with("correlationId", correlationId)) {
        log.info("Handling requestId={}", request.requestId());
        return orderQueryService.handle(request);
    }
}
```

In this example, `KafkaHeaders.CORRELATION_ID` is treated as opaque bytes and Base64 URL-safe encoded only when used as a fallback value for logging. Do not assume the byte array generated by `ReplyingKafkaTemplate` is always UTF-8 text; if you need a human-readable business ID, use a dedicated custom header.

For request-reply, Spring Kafka listener infrastructure echoes the correlation header for response routing. When using custom headers, configure echoing/propagation according to your version and protocol; do not assume a custom header automatically replaces the default header.

## 14. Correlation ID and Micrometer Observation/Tracing

Spring Kafka supports Micrometer Observation for `KafkaTemplate` and listener containers starting in version 3.0. You can enable observation to record message send and receive operations:

```java
@Bean
KafkaTemplate<String, OrderCreated> kafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {

    KafkaTemplate<String, OrderCreated> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
```

For the listener container factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> orderListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);
    return factory;
}
```

When Micrometer Tracing and a compatible propagator are configured, Observation can create spans for producer/consumer operations and transmit trace context via message headers. This is a separate tracing mechanism from your business `x-correlation-id`. Both can be used together: trace ID to open distributed traces, correlation ID to query logs across a business flow.

When Observation is enabled on `KafkaTemplate` or a container, traditional Micrometer timers for that component are managed via observation rather than legacy timers. For batch listeners, observation behavior depends on version; in Spring Kafka 4.1, observations are not created by default for batch listeners alone, and `recordObservationsInBatch` can be enabled to create per-record observations.

Default observation conventions add low-cardinality tags such as `bean.name` for templates and `listener.id` for listeners. You can customize conventions to add required metadata. Do not add correlation ID, event ID, order ID, or offset as metric tags; those values are high-cardinality and belong in logs or traces.

## 15. Correlation ID in batch listeners

A batch can contain many records with different correlation IDs. Therefore, do not put a single correlation ID into MDC for the entire batch and process all records under it; logs for other records would carry the wrong ID.

Instead, iterate record by record and open a separate MDC scope:

```java
@KafkaListener(
        topics = "orders",
        groupId = "inventory-service",
        containerFactory = "batchOrderListenerFactory")
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        String correlationId = CorrelationIds.readFrom(record);

        try (MdcScope ignored = MdcScope.with("correlationId", correlationId)) {
            log.info("Processing batch record orderId={}, partition={}, offset={}",
                    record.value().orderId(), record.partition(), record.offset());
            orderService.reserveStock(record.value());
        }
    }
}
```

If processing a batch in parallel with an executor, each task must receive its corresponding record's correlation ID and open an MDC scope on the executing thread. Do not share one MDC map across records.

## 16. Correlation ID and structured logging

In production, logs should be structured data rather than merely appending correlation IDs to plain text sentences. An event log can contain:

```json
{
  "timestamp": "2026-11-17T10:15:22.105+07:00",
  "level": "INFO",
  "service": "inventory-service",
  "message": "Stock reserved",
  "correlationId": "c-8a91",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "eventId": "evt-10042",
  "topic": "orders",
  "partition": 2,
  "offset": 108,
  "consumerGroup": "inventory-service"
}
```

These fields enable searching by correlation ID, verifying the exact event ID, or drilling down to the record's position in Kafka. Include only fields genuinely available in context; do not guess partition/offset when logging from a service layer that lacks record metadata.

Key guidelines:

- Use the same field name (`correlationId`) across all services.
- Include `service`, `environment`, `topic`, `partition`, `offset`, and `consumerGroup` when helpful for investigations.
- Keep `eventId` separate from correlation ID.
- Do not log full payloads if they contain sensitive data.
- Standardize exception classes and error codes; log stack traces only where appropriate.
- Avoid embedding IDs inside `message` text when they can be emitted as discrete fields.

## 17. Correlation ID and metrics: avoiding high cardinality

Correlation IDs are nearly unique per request. Placing this ID into a Micrometer tag can create a new time series for every request, increasing memory usage, scrape overhead, and metrics storage cost.

Do not do this:

```java
Counter.builder("app.kafka.processed")
        .tag("correlationId", correlationId)
        .register(meterRegistry)
        .increment();
```

Use tags with a bounded set of values instead:

```java
Counter.builder("app.kafka.processed")
        .tag("topic", record.topic())
        .tag("listener", "orders")
        .tag("result", "success")
        .register(meterRegistry)
        .increment();
```

Correlation IDs belong in logs and traces; metrics are for aggregating by topic, listener, result, exception class, or environment.

## 18. Security and trustworthiness of Correlation IDs

A correlation ID can originate from an HTTP client or external service, so treat it as untrusted input.

- Restrict length, charset, and format.
- Never use the ID to authenticate callers or grant access permissions.
- Never include tokens, passwords, payment details, or personal data.
- Strip control characters, newlines, and characters that could forge multiple log lines.
- If a gateway is responsible for issuing canonical IDs, downstream services should follow the gateway's trust policy.
- Never write unvalidated header values directly to logs.

A correlation ID does not need to be secret, but you must prevent external parties from controlling log formatting or creating unbounded cardinality in search backends.

## 19. Testing Correlation ID in logs

Tests should verify that headers are transmitted and MDC is set and cleaned up properly when listeners both succeed and fail.

1. **Producer adds header:** send a record and verify `x-correlation-id` exists with expected UTF-8 bytes.
2. **Consumer reads header:** verify the listener receives the expected correlation ID.
3. **Logs inside service:** use a Logback `ListAppender` or test appender to verify the MDC field appears in logs.
4. **Missing header:** verify logs show `none` or a fallback ID per policy.
5. **Consecutive records:** process two records with different IDs on the same consumer thread and verify the previous record's ID does not leak.
6. **Listener throws exception:** verify the `afterRecord()` interceptor still restores MDC.
7. **Retry:** verify each redelivery keeps the same correlation ID while delivery attempt updates appropriately.
8. **DLT:** verify the custom header is retained or copied onto the DLT record.
9. **Event forwarding:** verify downstream service producers pass the exact correlation ID onto the next topic.
10. **Batch:** verify each record logs its own ID rather than sharing one ID across the batch.
11. **Async task:** verify context is passed explicitly to the executor and cleaned up after the task.
12. **Invalid ID:** verify overly long headers or ones containing newlines are replaced with a new ID or rejected per policy.
13. **Metrics:** verify correlation ID never appears in metric tags.

With `spring-kafka-test` or Testcontainers Kafka, you can test end-to-end header delivery. For logs, use a test appender to inspect each `ILoggingEvent`'s MDC map; do not assert only formatted message strings because console patterns can omit or alter MDC fields.

## 20. Common pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Consumer logs lack correlation ID | Producer did not add header or header mapper did not expose it | Inspect native record headers and standardize header names |
| All records log the same correlation ID | MDC was not cleaned up on consumer thread | Use `try/finally`, `MdcScope`, or interceptor `afterRecord()` |
| Service logs have ID but async logs do not | MDC does not automatically cross threads | Pass ID into the task or use Micrometer Context Propagation |
| `ReplyingKafkaTemplate` times out | Overwriting `KafkaHeaders.CORRELATION_ID` breaks reply matching | Preserve Spring Kafka's request-reply correlation header |
| Correlation ID changes between services | Publishers generate a new ID at every hop | Propagate the original ID; create new IDs only for independent sub-workflows |
| DLT cannot be linked to original logs | Custom recoverer omits header copy or logs omit ID | Preserve headers and test the DLT path |
| Metrics cardinality spikes | Correlation ID used as a tag | Move IDs to logs/traces; use bounded tags |
| Header has multiple values | Producer appended duplicate headers with the same name | Write a single header; define a policy for duplicate headers |
| Log injection or oversized fields | Trusting caller-supplied IDs without validation | Enforce format/length limits and sanitize before logging |
| Batch logs carry the wrong ID | Setting MDC once for the entire batch | Open a dedicated MDC scope per record |

## 21. Implementation workflow

1. Decide whether correlation IDs are generated at the API gateway or service ingress.
2. Standardize header name, encoding, format, and length limits.
3. Keep correlation ID distinct from trace ID, request ID, event ID, and Kafka key.
4. Attach the correlation header on all producer paths, including retries, DLTs, and event forwarding.
5. Read the header in consumers via `ConsumerRecord` or `@Header`.
6. Put the ID into MDC using a `try/finally` scope or a `RecordInterceptor` with cleanup.
7. Configure Logback/JSON encoders to emit `correlationId` as a dedicated field.
8. When using async or batch processing, propagate context individually per task/record.
9. Enable Micrometer Observation/Tracing when distributed traces are needed; keep business correlation IDs separate.
10. Never use correlation ID as a metric tag and never log sensitive data.
11. Test success, exception, retry, DLT, forwarding, batch, and thread-reuse scenarios.
12. Build dashboards/log queries to look up all logs by correlation ID.

## 22. Summary

- Correlation IDs group logs of a single business flow across multiple services and topics.
- For regular event flows, you can use a custom Kafka header `x-correlation-id`; `KafkaHeaders.CORRELATION_ID` is used by default for request-reply.
- Kafka headers are byte arrays; use UTF-8 consistently and avoid duplicate header names.
- Read the correlation ID from `ConsumerRecord` or `@Header`, then put it into MDC so synchronous components on the same thread include the ID automatically.
- Consumer threads are reused, so MDC must be restored/cleared after each record; `RecordInterceptor.afterRecord()` has been available since Spring Kafka 2.8.
- MDC does not automatically cross to executors or async tasks; propagate context explicitly.
- Preserve correlation IDs through retries, DLTs, and event forwarding; keep event ID separate for idempotency.
- Micrometer Observation/Tracing supports distributed tracing; trace ID and correlation ID serve different purposes.
- Never put correlation IDs into metric tags due to high cardinality; use logs and traces instead.
- Validate incoming IDs and avoid PII, secrets, and log injection.

When correlation IDs are consistently carried in Kafka headers and managed in MDC with proper lifecycle cleanup, logs from multiple services can be queried as one continuous business flow. This speeds up debugging errors, retries, and late events without leaking correlation IDs across records processed on the same consumer thread.

## References

- [Spring Kafka Reference — Message Listener Containers and RecordInterceptor](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka Reference — Sending Messages and Request/Reply Headers](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka Reference — Micrometer Observation and Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka API — KafkaHeaders](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/KafkaHeaders.html)
- [Micrometer Tracing — Context Propagation](https://docs.micrometer.io/tracing/reference/configuring.html)
