# Trace context via Kafka headers

In a Spring Kafka system, a single request can traverse multiple services before completing: an API receives the request, an order service publishes an event, a payment consumer processes it, an inventory service updates stock, and another service sends notifications. When one step is slow or fails, checking individual service logs alone is often not enough to see the entire path taken.

Distributed tracing solves this by linking spans into a single trace. When a message is sent through Kafka, the trace context needs to travel with the record so consumers can continue the producer's trace. Kafka supports this via record headers. Headers live outside the JSON payload and are stored alongside the record by the broker, allowing producers and consumers to exchange tracing metadata without altering event contracts.

In Spring Kafka, Micrometer Observation and Micrometer Tracing can automatically inject and extract trace context when observation is enabled on `KafkaTemplate` and listener containers. This lesson focuses on trace context structure, propagation through Kafka headers, Spring Boot configuration, inspecting headers, handling retries/DLTs, baggage, asynchronous flows, and testing propagation.

## Learning objectives

After this lesson, you will be able to:

- Explain trace, span, traceId, spanId, and parent span.
- Describe the role of Kafka record headers in distributed tracing.
- Distinguish trace context from correlation ID and event ID.
- Recognize W3C headers such as traceparent, tracestate, and baggage.
- Configure Micrometer Tracing with Spring Boot.
- Enable observation for `KafkaTemplate` and listener containers.
- Explain how the sender injects and the receiver extracts trace context.
- Inspect trace headers inside `ConsumerRecord`.
- Preserve trace context when forwarding records through retry topics and DLTs.
- Propagate context properly when processing on another thread.
- Restrict baggage and avoid placing sensitive data in headers.
- Test trace continuity between producer and consumer.

## 1. What is trace context?

Trace context is metadata that allows multiple services to correlate operations into a distributed flow. A trace typically consists of multiple spans. Each span represents an operation with a start time, end time, name, and attributes.

Example of an order processing flow:

~~~text
Trace: 4bf92f3577b34da6a3ce929d0e0e4736

API request
  spanId: 00f067aa0ba902b7
      |
      v
Kafka producer send
  spanId: 11f067aa0ba902b7
  parent: 00f067aa0ba902b7
      |
      v
Kafka consumer process
  spanId: 22f067aa0ba902b7
  parent: 11f067aa0ba902b7
      |
      +--> Database query
      |
      +--> Kafka producer send payment event
                |
                v
          Payment consumer
~~~

Key concepts:

| Component | Meaning |
|---|---|
| Trace | The complete journey of a request or processing flow |
| Span | An operation with a start and end time |
| traceId | Shared ID identifying the trace |
| spanId | ID of a specific span |
| parentSpanId | Parent span that triggered the current operation |
| Trace context | Metadata required to establish relationships between spans |
| Baggage | Additional contextual data transmitted alongside the trace per configuration |

Spans within the same trace share the same `traceId` but have different `spanId`s. When a service receives a message and continues processing, it creates a new span linked to the received context. Tracing tools can thus display the producer, consumer, and dependencies along one unified journey.

Trace context is not business state. It does not indicate whether an order has been paid, nor does it replace `eventId` or `requestId`.

## 2. Why does Kafka need to transmit trace context via headers?

Kafka is an asynchronous messaging system. A producer sends a record and may finish the initial HTTP request before any consumer processes the record. Consumers may run in a different process, host, or at a different time.

Without propagating context, a consumer typically starts a brand-new trace. Tracing dashboards then cannot link the publish operation with the consume operation.

A Kafka record has three important parts:

~~~text
ProducerRecord
  key
  value
  headers
      |
      v
Kafka broker
      |
      v
ConsumerRecord
  key
  value
  headers
~~~

Trace context is placed in `headers`. The payload remains the business event, such as `OrderCreated`. Headers hold metadata like `traceparent`, `tracestate`, or `baggage`.

The broker does not need to understand `traceparent`. It stores and forwards headers alongside the record. Producer and consumer instrumentation is responsible for injecting and extracting context.

Benefits:

- Track publish and consume timings.
- Identify which service produced a failing message.
- View consumer lag and processing time within the same trace.
- Correlate logs across multiple services via `traceId`/`spanId`.
- Analyze retries, DLTs, and downstream steps.
- Pinpoint bottlenecks when an event passes through multiple consumers.

If producer and consumer use different tracing frameworks, they must agree on a propagation format. If one side sends W3C Trace Context while the other only reads B3, the trace can break even though headers are present.

## 3. Common W3C headers

W3C Trace Context defines standard fields for transmitting trace context.

| Header | Contents | Role |
|---|---|---|
| traceparent | version, trace-id, parent-id, and trace-flags | Core context to link traces |
| tracestate | Vendor-specific state information | Preserves metadata for tracing implementations |
| baggage | Optional key/value pairs | Transmits contextual data across service boundaries |

A version `00` `traceparent` looks like:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Structure:

~~~text
version-trace-id-parent-id-trace-flags
  00     32 hex     16 hex       2 hex
~~~

In the example:

- `00` is the header format version.
- `4bf92f3577b34da6a3ce929d0e0e4736` is the trace ID.
- `00f067aa0ba902b7` is the parent operation's span ID.
- `01` is flags, where the sampled bit is set.

Do not construct `traceparent` manually with UUIDs or string concatenation. The tracing library must generate IDs, validate formatting, and inject the proper format. A malformed `traceparent` value can be ignored by receivers.

### tracestate

`tracestate` carries vendor-specific supplemental data. Applications usually do not need to modify this header themselves. Let the propagator manage it to avoid losing or overwriting metadata needed by the tracing backend.

### baggage

Baggage carries key/value pairs such as:

~~~text
baggage: tenant=tenant-42,region=ap-southeast-1
~~~

Baggage can be useful when keeping certain contextual attributes across services. However, all baggage can traverse multiple systems and be stored in Kafka headers. Permit only necessary fields, and do not transmit tokens, passwords, emails, phone numbers, or unnecessary personal data.

## 4. Trace context differs from correlation ID and event ID

These three types of IDs serve different purposes and must not be used interchangeably.

| Identifier | Purpose | Lifecycle |
|---|---|---|
| traceId | Links spans of a single trace | Follows the tracing journey |
| spanId | Identifies a single operation | Per span |
| correlationId | Links logs or messages belonging to a business workflow | Follows business convention |
| eventId | Uniquely identifies an event | Per event, preserved when replaying the same event |
| requestId | Identifies a business request | Follows logical request |

One request can produce multiple events, each with its own `eventId`. Those events may share one trace or be processed in separate traces depending on how asynchronous flows are designed.

A `correlationId` is typically used to find all logs related to an order or workflow. A `traceId` is used by the tracing backend to build parent-child relationships between spans. Do not use `traceId` as an idempotency key because retries or replays may generate different traces.

If the system already carries a `correlationId` in payloads or business headers, keep it independent from `traceparent`. Both values can be logged together to support both technical tracing and business investigation.

## 5. From which version does Spring Kafka support Micrometer Observation?

Spring Kafka supports Micrometer Observation for `KafkaTemplate` and listener containers starting in version 3.0. Observation creates instrumentation points for sending and receiving messages. When Micrometer Tracing is configured, observations become spans and propagators inject/extract trace context.

Two key properties:

- `KafkaTemplate.observationEnabled`: enables observation for send operations.
- `ContainerProperties.observationEnabled`: enables observation for listener containers.

By default, these properties are `false`. If enabled only on the producer and not on the consumer, the producer can create spans and inject headers, but the consumer container will not create the corresponding receive observation.

When observation is enabled, traditional Micrometer Timers on the template/container are managed through observation. Do not assume enabling tracing takes effect automatically if `ObservationRegistry` or an appropriate tracing handler is missing.

For batch listeners, observation support and scope vary by Spring Kafka version. Some older versions do not create observations for batch listeners; newer versions can create observations for the batch or per record via the `recordObservationsInBatch` setting. Check the documentation for your exact version rather than assuming record listeners and batch listeners behave identically.

### Dependencies with Spring Boot

With Spring Boot 3.x, a common configuration uses Actuator, a Micrometer Tracing bridge, and an OTLP exporter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>

<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

Dependency versions should be managed by Spring Boot dependency management/BOM. With Spring Boot 4.x, the OpenTelemetry starter may be packaged differently; follow the documentation for your exact Boot version rather than mixing independent versions.

You can use OpenTelemetry or Brave as the tracer implementation. Services in the same system must agree on propagation format, such as both using W3C Trace Context or configuring multiple propagators under a shared policy.

## 6. Enabling observation in Spring Boot

Spring Boot provides configuration properties for Kafka template and listener observation.

~~~yaml
spring:
  kafka:
    template:
      observation-enabled: true
    listener:
      observation-enabled: true

management:
  tracing:
    sampling:
      probability: 1.0
~~~

In this example, sampling probability is `1.0` to observe every trace during development and testing. Production usually adjusts sampling to balance cost, traffic, and investigation needs.

Spring Kafka observation defaults to `false`. Setting only sampling probability is not enough if `KafkaTemplate` or listener observation is not enabled.

If using Spring Boot auto-configuration, the properties above apply to the default template and listener container. If you create custom `KafkaTemplate` or container factory beans, confirm they also receive observation configuration.

### Java configuration

You can enable it directly in Java config:

~~~java
@Bean
public KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);

    return template;
}
~~~

Enable observation on the listener factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);

    return factory;
}
~~~

If you already use Spring Boot's auto-configured template/factory, there is no need to create new beans just to enable observation. Configuring via `application.yml` is usually easier to manage.

## 7. Inject and extract flow for trace context

When a tracing-capable `ObservationRegistry` is configured, the send/receive flow typically proceeds as follows:

~~~mermaid
sequenceDiagram
    participant A as API / Application
    participant P as KafkaTemplate
    participant K as Kafka Broker
    participant C as Listener Container
    participant S as Consumer Service

    A->>P: Send OrderCreated
    P->>P: Create producer observation/span
    P->>P: Propagator injects trace context
    P->>K: Record + traceparent/tracestate/baggage
    K->>C: ConsumerRecord + headers
    C->>C: Propagator extracts trace context
    C->>C: Create consumer observation/span
    C->>S: Invoke @KafkaListener
    S->>S: Execute business logic
~~~

### Producer side

1. The application has an active trace or span.
2. `KafkaTemplate` starts an observation for the send operation.
3. The tracing handler creates a message send span.
4. The propagator injects context into the Kafka record headers.
5. The producer sends the record to the broker.

### Consumer side

1. The listener container polls the record and receives headers.
2. The consumer observation extracts context from headers.
3. The tracing handler creates a processing span linked to the received context.
4. The span is placed in scope while the listener executes.
5. Logs and instrumented operations inside the scope can access the active `traceId`/`spanId`.

If the listener goes on to send another Kafka message, the producer observation can create a child span in the same trace and inject new context into the next record.

Automatic propagation depends on `ObservationRegistry` actually having a tracing handler and propagator. If only Micrometer metrics are present without a tracing bridge, the application may still record timers but will not produce distributed traces.

## 8. Inspecting trace headers in ConsumerRecord

You can read the header to verify the producer sent trace context:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void consume(ConsumerRecord<String, OrderEvent> record) {
    Header traceParentHeader =
            record.headers().lastHeader("traceparent");

    if (traceParentHeader != null) {
        String traceParent = new String(
                traceParentHeader.value(),
                StandardCharsets.UTF_8
        );

        log.debug(
                "Received Kafka record with traceparent={}, topic={}, partition={}, offset={}",
                traceParent,
                record.topic(),
                record.partition(),
                record.offset()
        );
    }

    billingService.process(record.value());
}
~~~

This snippet is only for observation/debugging. Do not parse `traceparent` to manually create spans when Spring Kafka observation already handles it. Reading the header does not mean the application extracted the context into the tracer.

If the header is missing, check:

- Is `KafkaTemplate` observation enabled?
- Does `ObservationRegistry` have a tracing handler?
- Is the producer sending via the configured template?
- Is any custom `ProducerInterceptor` or serializer modifying the record?
- Is any intermediate component creating a new record without copying headers?
- Do producer and consumer agree on the propagation format?

Do not log all headers in production if sensitive baggage or metadata may be present.

## 9. Trace context across multiple services

A practical example:

~~~text
order-api
   |
   | Kafka: orders.created
   | traceparent = T1 / producer-span
   v
billing-service
   |
   | Kafka: payments.requested
   | traceparent = T1 / billing-producer-span
   v
payment-service
   |
   | HTTP call to payment gateway
   | trace context propagated
   v
payment-gateway
~~~

When all services enable tracing and use compatible propagators, the tracing backend can display a single trace connecting the API, Kafka producer, consumer, and downstream HTTP call.

Kafka does not create new traces on the broker. Send and receive spans are created on the application side. The broker only stores records and headers.

If one service does not support propagation, the trace can fragment into separate parts. That service can still emit its own logs and metrics, but cannot establish parent-child span relationships across its boundary.

## 10. Trace context across retry topics and dead-letter topics

Retries and DLTs are alternate paths for the same record. If forwarding components preserve Kafka headers, trace metadata can continue traveling with the record through these topics.

Example:

~~~text
orders
  |
  | processing error
  v
orders-retry-1000
  |
  | processing error again
  v
orders-retry-5000
  |
  | retries exhausted
  v
orders-dlt
~~~

When designing tracing for retries/DLTs, note:

- Do not strip `traceparent`/`tracestate` when creating retry records.
- Do not manually generate `traceparent` headers with random IDs.
- If a custom recoverer creates a new `ProducerRecord`, define explicitly how headers are copied.
- Check whether retry publishers and DLT publishers have observation enabled.
- Record retry attempt and exception type in separate business headers/metadata.
- Do not use retry count as a span ID or trace ID.
- Verify the trace backend displays each attempt as intended.

A record may go through multiple processing attempts. Each retry may have a new processing span; span relationships depend on how the framework creates observations and forwards records. Inspect actual traces rather than assuming all retries share one span or create new traces.

### Original headers and header forwarding

`DeadLetterPublishingRecoverer` and the retry-topic infrastructure include mechanisms to retain record metadata when forwarding. However, custom recoverers, converters, or code constructing a new `ProducerRecord` can drop headers if only key/value are copied.

When forwarding records manually, retain required headers:

- `traceparent` and `tracestate`.
- Allowlisted baggage.
- `eventId` and `correlationId`.
- Source metadata such as topic/partition/offset if auditing requires it.
- Retry attempt or DLT exception metadata.

Do not blindly copy every header from untrusted sources. Filter permitted headers, avoid duplicate headers with unclear semantics, and cap total size.

## 11. Baggage via Kafka headers

Baggage is useful when a few contextual attributes need to cross services, such as tenant code or region. Baggage does not replace business payloads.

With Micrometer Tracing, you can create baggage in scope:

~~~java
@Service
public class OrderProcessingService {

    private final Tracer tracer;

    public OrderProcessingService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void processForTenant(String tenantCode) {
        try (BaggageInScope baggage =
                     tracer.createBaggageInScope("tenant", tenantCode)) {

            orderService.process();
        }
    }
}
~~~

Whether baggage propagates automatically depends on `BaggageManager` and propagation configuration. With W3C, baggage can be transmitted in the `baggage` header. With B3, baggage is not automatically propagated unless the corresponding remote fields are configured.

Creating baggage in scope requires an active span so the baggage attaches to that trace. If `createBaggageInScope` is called with no active span, do not assume the value will propagate automatically to the next message.

Allowlist only necessary baggage fields. Do not use baggage for large payloads, personal data, secrets, or credentials. Baggage traverses multiple services and can appear in Kafka headers, logs, or tracing backends.

Do not add tenant ID or user ID as high-cardinality metric labels. If you need to search traces by tenant, consider span attributes or controlled logging while respecting data policy.

## 12. Trace context across threads and async processing

Micrometer Tracing typically holds the active span in a thread-local scope. The Spring Kafka listener container manages the observation scope while invoking the listener. When the listener executes synchronously on that thread, logs and instrumented operations see the active context.

Context is not guaranteed automatically when the application switches threads using custom executors, `CompletableFuture`, or uninstrumented callbacks.

Risky example:

~~~java
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    CompletableFuture.runAsync(() -> {
        orderService.process(event);
    });
}
~~~

The listener returns right after submitting the task. The thread pool may not carry trace context from the listener thread to the worker thread. As a result, the business span may not belong to the original trace or logs may miss the expected `traceId`.

Solutions:

- Use Micrometer Context Propagation and `TaskDecorator` for executors.
- Capture/restore context when submitting async work.
- Create a new span with an explicit parent from the captured context.
- If offsets must only be committed after async processing completes, design acknowledgement and lifecycle separately; trace propagation does not solve offset semantics.

Never keep a `SpanInScope` open on one thread and close it on another. A scope must be closed on the thread that opened it. Use context propagation APIs instead of passing ThreadLocals manually.

## 13. Creating business spans inside a listener

Spring Kafka creates an observation for the listener invocation when configured. If you need to observe a long business step inside the listener, you can create child spans using Micrometer Tracer.

~~~java
@Component
public class OrderListener {

    private final Tracer tracer;
    private final OrderService orderService;

    public OrderListener(Tracer tracer, OrderService orderService) {
        this.tracer = tracer;
        this.orderService = orderService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-service"
    )
    public void consume(OrderEvent event) {
        Span span = tracer.nextSpan()
                .name("order.validate-and-save")
                .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            span.tag("order.type", event.type());
            orderService.process(event);
        }
        catch (RuntimeException ex) {
            span.error(ex);
            throw ex;
        }
        finally {
            span.end();
        }
    }
}
~~~

Child spans distinguish validation, database persistence, or dependency calls from total listener time. Do not create spans for every tiny line of code; create spans only at business or dependency boundaries worth investigating.

If an exception is rethrown, the Spring Kafka error handler can still handle retries/DLT. Marking a span as errored does not alter retry mechanics or offset commits.

## 14. Manual propagation with Micrometer Propagator

When sending messages using a Kafka client outside `KafkaTemplate` observation or integrating a custom transport, you can use Micrometer `Propagator` to inject/extract context.

Do not build `traceparent` strings yourself. The tracer's propagator generates headers according to the configured propagation format.

Example setter/getter for Kafka `Headers`:

~~~java
private static final Propagator.Setter<Headers> KAFKA_SETTER =
        (headers, key, value) -> {
            headers.remove(key);
            headers.add(
                    key,
                    value.getBytes(StandardCharsets.UTF_8)
            );
        };

private static final Propagator.Getter<Headers> KAFKA_GETTER =
        (headers, key) -> {
            Header header = headers.lastHeader(key);

            return header == null
                    ? null
                    : new String(
                            header.value(),
                            StandardCharsets.UTF_8
                    );
        };
~~~

On the producer side, inject the current span's context:

~~~java
Span currentSpan = tracer.currentSpan();

ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>(
                "orders.created",
                orderId,
                event
        );

if (currentSpan != null) {
    propagator.inject(
            currentSpan.context(),
            record.headers(),
            KAFKA_SETTER
    );
}

kafkaProducer.send(record);
~~~

On the consumer side, extract context and place the span in scope:

~~~java
Span span = propagator.extract(
                record.headers(),
                KAFKA_GETTER
        )
        .name("orders.consume")
        .start();

try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
    orderService.process(record.value());
}
catch (RuntimeException ex) {
    span.error(ex);
    throw ex;
}
finally {
    span.end();
}
~~~

This example shows a manual integration path. If `KafkaTemplate` and the listener container already have observation enabled with a tracing handler, do not add manual inject/extract logic alongside it, as doing so can produce duplicate headers or unintended nested spans.

In production code, handle missing context, malformed headers, and deserialization errors. The getter in the example uses `lastHeader()` to read the last value; if duplicate header names are allowed in your system, define clear selection and input validation rules.

## 15. Trace context and sampling

Sampling decides which traces are recorded or exported to the backend. It is not a mechanism guaranteeing messages are sent or consumers run.

Spring Boot may sample only a fraction of requests by default to reduce overhead. When a trace is sampled out, the system continues processing business logic normally. The presence or absence of a span in the backend does not prove whether a record was lost.

Example configuration in a development environment:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

A value of `1.0` samples all traces. Production should pick a ratio based on traffic, backend cost, and flow criticality. Sampling can be raised temporarily during incident investigation if operational policy permits.

Do not permanently force sampling to 100% in high-traffic systems without evaluating storage cost, exporter queues, network bandwidth, and span limits.

## 16. Observing traces in logs

Spring Boot with Micrometer Tracing can place `traceId` and `spanId` in MDC for log correlation. Producer and consumer logs can then be queried by trace.

Example format:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

Sample logs:

~~~text
[4bf92f3577b34da6a3ce929d0e0e4736,00f067aa0ba902b7]
Publishing OrderCreated eventId=e-100

[4bf92f3577b34da6a3ce929d0e0e4736,22f067aa0ba902b7]
Received OrderCreated eventId=e-100
~~~

The shared `traceId` finds both logs along the same journey, while distinct `spanId`s identify the specific operations.

There is no need to manually append `traceId` to every log message if MDC is already configured. When using async executors, verify MDC/context is propagated and restored cleanly so logs from an earlier task do not leak into the next task.

## 17. Trace context does not replace metrics

Tracing helps investigate a single request or message. Metrics help track trends and alert at system scale.

Use metrics for:

- `KafkaTemplate` send latency.
- Listener processing latency.
- Consumer lag.
- Success/failure record counts.
- Retry and DLT rates.
- Consumer rebalance counts.
- Deserialization error counts.

Use traces for:

- Why a specific event took a long time to process.
- Which service called a slow dependency.
- Which listeners an event passed through.
- Which operation originated an error.
- Which retry attempt caused a failure.

Do not use `traceId`, `spanId`, `eventId`, or `orderId` as high-cardinality metric labels. Those IDs belong in traces and logs, while metrics should use bounded-value tags such as listener name, result, or exception class.

When `observationEnabled` is on, Spring Kafka creates observations for `KafkaTemplate` and listeners. Micrometer can use observations to generate both timer metrics and spans; metrics carry low-cardinality tags suitable for aggregation.

## 18. Security and header limits

Kafka headers are metadata attached to records and may be retained according to topic retention. Downstream consumers, retry topics, and DLTs can continue holding those headers.

Principles:

- Do not put access tokens, passwords, or secrets in baggage.
- Do not put personal data in baggage without a clear reason and explicit authorization.
- Limit the number and size of baggage fields.
- Propagate only allowlisted fields.
- Do not trust external `traceparent` headers to make access decisions.
- Do not use trace context as proof of authentication or authorization.
- Control logging so sensitive headers are not printed in full.
- Avoid accumulating duplicate copies of headers with the same name when forwarding records.

Trace context is observability data, not a security token. A message sender can craft or alter headers if it has write access to a topic. Services must never rely on `traceId` or baggage to authorize business actions.

## 19. Common pitfalls

**Enabling observation only on the producer.** The producer injects trace context, but the consumer creates no receive observation. Enable observation on both `KafkaTemplate` and listener containers.

**Configuring only sampling probability.** Sampling alone does not enable Kafka observation. Check both `observation-enabled` properties.

**Missing tracing bridge.** Timers may still appear without spans or propagation. Install and configure a matching Micrometer Tracing implementation.

**Producer and consumer use different propagation formats.** Headers may be present yet unreadable by the consumer. Standardize on W3C or B3.

**Generating `traceparent` manually with UUIDs.** Invalid headers break traces. Let the propagator generate IDs.

**Using `correlationId` as `traceId`.** A business workflow and a trace have different lifecycles. Keep the two identifiers separate.

**Custom recoverer creates a new record without copying headers.** Trace context is lost across retries or DLTs. Selectively copy required headers.

**Baggage contains sensitive data.** Metadata spreads across services and persists in Kafka. Enforce an allowlist and data minimization.

**Async tasks lose context.** Logs and spans break after switching threads. Use Micrometer Context Propagation or start spans with explicit parents.

**Creating manual spans when auto observation is already active.** Can create duplicate spans or duplicate injected headers. Choose one propagation mechanism per boundary.

**Using `traceId` as an idempotency key.** Retries or replays may not share the same trace. Use stable `eventId`/`requestId` values for idempotency.

**Using `traceId` as a metric label.** Cardinality grows unboundedly. Keep IDs in traces and logs.

**Assuming a missing trace means the message was not processed.** Sampling may exclude the trace from the backend. Check offsets, listener logs, and metrics separately.

## 20. Testing trace context via Kafka headers

Tests should prove that trace context actually travels from producer to consumer, not just that observation beans exist.

Scenarios to include:

1. Producer sends a record while a span is active: the record carries a valid `traceparent`.
2. Consumer receives the record: the listener span shares the producer's `traceId`.
3. Consumer publishes a follow-up event: the new producer span links to the listener span.
4. Producer sends without an active span: behavior matches the application's root trace policy.
5. Consumer receives a record missing `traceparent`: the listener processes normally and tracing does not break business logic.
6. Consumer receives a malformed `traceparent`: the propagator handles it safely.
7. Record goes through a retry topic: required headers remain intact.
8. Record enters a DLT: trace metadata is retained per policy.
9. Custom recoverer creates a new record: header propagation is not lost.
10. Baggage allowlist: only permitted fields are propagated.
11. Async executor: span context is captured and restored properly.
12. Low sampling: business logic still executes even when traces are not exported.
13. Two concurrent events: `traceId` and `spanId` are not mixed across threads.
14. Duplicate header names: the application follows clear read and handling rules.

With Spring Kafka Test or Testcontainers, you can send a `ProducerRecord` with trace context and receive a `ConsumerRecord` to inspect headers. Use `TestObservationRegistry` or a test tracer to verify observations/spans in tests. Do not assert only log text because log formats can change independently of propagation.

## 21. Trace context configuration checklist

- [ ] A common propagation format is chosen across services.
- [ ] Appropriate Micrometer Tracing bridge and exporter are present.
- [ ] `ObservationRegistry` has tracing handlers registered.
- [ ] `KafkaTemplate` observation is enabled.
- [ ] Listener container observation is enabled.
- [ ] Producers and consumers use the same W3C/B3 configuration.
- [ ] Trace context is transmitted via Kafka record headers.
- [ ] `traceparent` is never manually constructed via strings or UUIDs.
- [ ] Correlation ID and event ID remain independent from trace ID.
- [ ] Retry/DLT forwarding retains required headers.
- [ ] Baggage contains only allowlisted fields.
- [ ] Async executors have proper context propagation.
- [ ] Sampling is tuned per environment.
- [ ] `traceId`/`spanId` appear in logs, not as metric labels.
- [ ] Producer-to-consumer trace continuity is tested.
- [ ] Missing, malformed, and duplicate headers are tested.
- [ ] Rules prevent logging sensitive baggage or metadata.

## Conclusion

Trace context travels across Kafka via record headers, enabling producers and consumers to connect spans into a distributed trace. In Spring Kafka, configure Micrometer Tracing and enable observation on both `KafkaTemplate` and listener containers so propagators automatically inject and extract context. Keep `traceId`, `correlationId`, and `eventId` in their proper roles; preserve headers when forwarding through retries/DLTs; use context propagation when switching threads; and restrict baggage to avoid leaking sensitive data. Tracing helps investigate message paths and latency, while offsets, retries, idempotency, and delivery guarantees must still be managed by the corresponding messaging mechanisms.

## References

- [Spring Kafka – Monitoring and Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka – Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing – Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Micrometer Tracing – Using Micrometer Tracing Directly](https://docs.micrometer.io/tracing/reference/api.html)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [W3C Baggage](https://www.w3.org/TR/baggage/)

