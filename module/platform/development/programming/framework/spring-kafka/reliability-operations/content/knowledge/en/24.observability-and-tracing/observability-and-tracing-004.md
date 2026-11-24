# Producer trace context

In a Spring Kafka system, a business operation rarely passes through a single Java method. For example, an HTTP request creating an order is handled in service A, which writes to a database and publishes an `OrderCreated` event to Kafka. Service B consumes the event, calls a payment API, and then publishes `PaymentRequested`. If all those components only write timestamped logs, operations teams struggle to answer: **which request created this Kafka record, how long did the producer step take, and is an error in a downstream consumer tied to the original request?**

**Producer trace context** is the information used to link the **Kafka record send** step to an existing distributed trace while providing data for the consumer to continue the trace in the receiving service. With Spring Kafka and Micrometer Observation/Tracing, context is typically propagated via **Kafka record headers** according to the configured propagator—for example, W3C Trace Context containing `traceparent` and optionally `tracestate`.

This topic goes beyond "adding a trace ID to logs." You must distinguish the **active context in the producer thread**, the **producer span**, the **Kafka headers injected on send**, the **context extracted at the consumer**, and the **actual state of the record** (successful send, transaction commit, retry, or DLT). Tracing illuminates execution flow, but does not replace offset commits, idempotency, or error handling.

This lesson covers the concepts, producer observation configuration, context flow from HTTP/Kafka listeners to `KafkaTemplate`, issues at async thread boundaries, retries/transactions, testing, security, and operational runbooks.

## 1. What questions does trace context answer?

Distributed tracing describes an operation spanning multiple components as a set of causally related **spans**. Each span represents an operation, such as an HTTP server request, database query, Kafka producer send, or Kafka listener processing.

Common cases needing trace context:

- Investigating which HTTP request published a failing event.
- Linking a Kafka producer span in service A to a Kafka consumer processing span in service B.
- Determining whether latency arises during Kafka publish or in the consumer/downstream.
- Following services along one processing path when many messages interleave on the same topic.
- Correlating a retry or DLT record with its initial emission.
- Distinguishing the same business event reprocessed multiple times from distinct new events.

Topology example:

~~~text
Trace T1

HTTP POST /orders   (orders service)
        |
        v
createOrder span
        |
        v
Kafka producer span: orders.events
        |
        | Kafka record + trace headers
        v
Kafka topic: orders.events
        |
        v
Kafka consumer span: billing listener
        |
        v
chargePayment span
        |
        v
Kafka producer span: billing.results
        |
        | Kafka record + trace headers
        v
Kafka topic: billing.results
~~~

When propagation works properly, spans can be linked within one trace or via span links depending on the tracing model and tooling. The exact relationship between producer and consumer spans depends on instrumentation, propagator, and library versions; do not assume every tracing backend always renders the exact same parent-child tree.

## 2. How do trace ID, span ID, and trace context differ?

| Term | Meaning | Example purpose |
|---|---|---|
| **Trace ID** | Trace identifier across multiple spans | Locate the entire request/event flow |
| **Span ID** | Identifier of a single operation within a trace | Locate a specific Kafka send attempt |
| **Parent context** | Context that a new span builds upon | Link producer span to the preceding step |
| **Sampling flag** | Sampling policy signal | Decide whether spans are recorded/exported |
| **Trace state** | Tracing vendor metadata per the corresponding spec | Support propagation across heterogeneous systems |
| **Baggage** | Metadata allowed to propagate alongside context | Non-sensitive correlation fields, if truly needed |

A trace ID is **not** a Kafka record key. A span ID is **not** an offset. A single trace can contain multiple sends, multiple records, and even multiple topics. Conversely, the same event can be reprocessed in multiple new traces if retries/replays do not preserve or link the original context.

### 2.1. Two layers of context

Within a producer application, context falls into two layers:

1. **Local/current context**: the tracing context active on the thread or execution scope when `KafkaTemplate.send(...)` is called.
2. **Propagated context**: metadata injected into Kafka record headers so another process can restore or link the trace.

Having a local span without injecting headers usually breaks the trace at the Kafka boundary. Having headers on the Kafka record without consumer extraction or a tracing bridge prevents the receiving side from building the desired trace relationship.

### 2.2. Producer span vs. record headers

A producer span is observability telemetry that can hold start/end timestamps, topic, send outcome, and traceable attributes. Kafka headers carry only **enough context to link the trace**—they do not hold the full span, full processing duration, or proof that the broker committed the record.

## 3. W3C Trace Context in Kafka headers

With a W3C propagator configured, common metadata consists of:

- `traceparent`: version, trace ID, parent span ID, flags.
- `tracestate`: standard extension metadata, optional.

Value structure:

~~~text
Kafka record headers:
  traceparent = "00-<32 hex trace-id>-<16 hex parent-id>-01"
  tracestate  = "<provider-specific entries>"   (if present)
~~~

This is an **illustrative structural representation**, not a valid header literal to copy directly: angle-bracket placeholders must be replaced with real identifiers matching standard lengths and formats.

Kafka headers are key and `byte[]` pairs, not HTTP headers. The tracing propagator handles encoding and decoding the required values. Avoid hand-crafting `traceparent` strings by concatenating trace IDs and span IDs when instrumentation already handles injection, as manual construction can produce wrong relationships or invalid formats.

### 3.1. Trace propagation is not limited to W3C

Another system may use B3 or a different propagation format. Both services need **compatible propagators** to understand headers. A producer writing W3C `traceparent` while a consumer only reads B3 can cause the receiver to start a new trace.

When migrating from B3 to W3C, plan a coordinated propagation config rollout across all involved producers and consumers. Never let individual services invent custom header names without a clear contract.

### 3.2. Kafka headers can repeat the same key

Kafka permits multiple headers with the same key. A custom producer or middleware accidentally injecting `traceparent` a second time can produce duplicates:

~~~text
traceparent = old context
traceparent = new context
~~~

Consumers and propagators may pick among duplicates differently. Avoid manual injection on top of automatic instrumentation; if records pass through multiple republish layers, verify header replace/preserve policies so headers match the current send.

## 4. Context flow from producer to consumer

A typical flow:

~~~text
Request/service handling thread
        |
        | Current Observation/Trace context active
        v
KafkaTemplate.send(...)
        |
        +--> Create or record producer observation/span
        |
        +--> Propagator injects trace context into headers
        |
        v
Kafka ProducerRecord<K,V>
        |
        v
Kafka broker stores record + headers
        |
        v
Kafka consumer receives record
        |
        +--> Instrumentation extracts headers
        |
        +--> Start consumer observation/span
        |
        v
@KafkaListener executes business logic
~~~

For a trace to span two services, both sides must be ready:

1. The producer is instrumented with an appropriate `ObservationRegistry`/tracing bridge.
2. A propagator is configured to inject context into Kafka headers.
3. The consumer receives those headers and has compatible instrumentation/extractors.
4. The tracing backend receives sampled/exported spans.

Missing any piece leaves a gap in the trace even while Kafka sends and consumption continue working normally.

## 5. Micrometer Observation vs. Micrometer Tracing

Modern Spring Kafka releases integrate **Micrometer Observation** for Kafka operations. Observation provides an instrumentation API that connects to both metrics and tracing.

| Component | Role |
|---|---|
| `ObservationRegistry` | Registers handlers and manages observations |
| Micrometer Observation | Models Kafka send/receive operations as observations |
| Micrometer Tracing bridge | Connects observations to a tracer such as OpenTelemetry or Brave |
| Propagator | Injects/extracts trace context via Kafka headers |
| Tracing exporter/collector | Receives spans and forwards them to the tracing backend |
| Spring Kafka producer observation | Instruments `KafkaTemplate` sends when enabled |
| Spring Kafka listener observation | Instruments listener/consumer processing when enabled |

**Enabling Observation does not automatically guarantee distributed traces.** If an application has `ObservationRegistry` without a tracing bridge or tracing handlers, you can get observations/metrics with no trace headers or exported spans.

### 5.1. Practical prerequisites

A Spring Boot/Spring Kafka application using tracing typically needs:

- A Spring Kafka version supporting producer observation.
- Appropriate Micrometer Observation/tracing dependencies.
- A tracing bridge (such as OpenTelemetry).
- An exporter or tracing backend integration.
- Propagation and sampling configuration.
- Observation enabled on the producers/listeners to track.

Do not treat seeing `micrometer-core` in the dependency graph as proof that tracing is fully enabled.

## 6. Enabling producer observation on KafkaTemplate

In Spring Kafka 3.x and versions with the matching API, `KafkaTemplate` exposes:

~~~java
kafkaTemplate.setObservationEnabled(true);
~~~

Example creating a template with `ObservationRegistry`:

~~~java
@Configuration
public class TracedKafkaProducerConfig {

    @Bean
    KafkaTemplate<String, OrderEvent> ordersKafkaTemplate(
            ProducerFactory<String, OrderEvent> producerFactory,
            ObservationRegistry observationRegistry) {

        KafkaTemplate<String, OrderEvent> template =
                new KafkaTemplate<>(producerFactory);

        template.setObservationRegistry(observationRegistry);
        template.setObservationEnabled(true);

        return template;
    }
}
~~~

Generic types, serializers, and producer factories must match the real application. `ObservationRegistry` must be configured with proper tracing handlers/propagators; an empty or NOOP registry yields no end-to-end traces.

### 6.1. When Spring Boot auto-configures KafkaTemplate

If Spring Boot creates `KafkaTemplate` via auto-configuration, the application may need to enable Observation through bean customization or version-appropriate configuration. When defining your own `KafkaTemplate`, ensure the template actually injected into services is the one with Observation enabled.

Do not assume a YAML property introduced in another Spring Boot version exists in the version you are running. Rather than guessing property names, verify effective values via bean configuration and integration tests.

### 6.2. Multiple KafkaTemplate beans

A service may have:

- A JSON template for `orders.events`.
- A `byte[]` template for DLTs.
- A template for a second Kafka cluster.
- A transactional template.

Enabling Observation on one template does not automatically enable it on others. Map out ownership and verify every publish path, especially error recovery/DLT paths.

## 7. Dependencies and tracing backends

In Spring Boot 3.x applications, tracing setup typically builds on Actuator, a Micrometer Tracing bridge, and an exporter. Reference Gradle snippet:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Actual dependencies/versions must follow Spring Boot's dependency management and your tracing backend. This is an orienting example, not a rigid list across all Spring Boot versions.

Common sampling/export endpoint configuration in Boot 3 releases:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

A value of `0.1` means the sampling policy targets roughly one-tenth of traces under suitable conditions, not a strict promise of one trace out of every 10 records. Property names and OTLP configuration can change across Boot versions, so verify against the documentation for your deployed dependency.

### 7.1. Trace exporters can fail while Kafka keeps working

The tracing backend is not the Kafka broker. If the exporter/collector is temporarily unavailable, business sends can still succeed depending on tracing configuration. Never let an unavailable exporter cause lost Kafka records or infinite business retries.

Monitor exporter queues/drops/errors separately, because missing spans may stem from observability infrastructure rather than the producer failing to inject headers.

## 8. Example: producer sending an event inside an active trace

Suppose an HTTP controller calls an order creation service. HTTP server tracing has already established an active context. `KafkaTemplate` observation builds on that context to instrument the send and propagate context via Kafka headers when fully configured.

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>>
    publish(OrderEvent event) {

        return kafkaTemplate.send(
                "orders.events",
                event.orderId(),
                event);
    }
}
~~~

You do not need to manually attach `traceparent` here once `KafkaTemplate` observation and the propagator are working. Producer trace context is derived from the active observation when `send(...)` executes.

If the request thread **has no active tracing context**, instrumentation can start a new trace for the producer operation (depending on tracing handlers and sampling). That is valid, though it will not link to an unknown upstream request.

### 8.1. Tracking send outcomes

`KafkaTemplate.send(...)` returns a future in modern Spring Kafka releases. Producers must observe the result:

~~~java
publisher.publish(event).whenComplete((result, error) -> {
    if (error != null) {
        log.error(
                "Kafka publish failed: eventType=OrderEvent",
                error);
        return;
    }

    log.debug(
            "Kafka publish acknowledged: topic={}, partition={}, offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset());
});
~~~

This snippet illustrates callback logging; real applications must persist errors/retries according to durability requirements. Callbacks may run on another thread, so **never assume the request thread's trace context remains active inside the callback**. If a callback needs to start a span or publish another event, handle context propagation explicitly.

### 8.2. Producer spans do not replace send acknowledgments

Seeing a producer span in the tracing backend does not prove the broker acknowledged the record, let alone that a transaction containing the record committed. A send can start a span and still fail. Combine spans with:

- Future success/failure handling.
- Producer error metrics.
- Kafka transaction commits/aborts when transactions are used.
- Downstream consumption or business completion metrics.

## 9. Wrapping publish in a business observation

If you want the "process order creation command" step represented in the same trace, wrap the Kafka send in a business observation:

~~~java
@Service
public class ObservedOrderCommandService {

    private final ObservationRegistry observationRegistry;
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public ObservedOrderCommandService(
            ObservationRegistry observationRegistry,
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.observationRegistry = observationRegistry;
        this.kafkaTemplate = kafkaTemplate;
    }

    public void submit(OrderEvent event) {
        Observation.createNotStarted(
                "orders.submit",
                observationRegistry)
                .observe(() -> {
                    kafkaTemplate.send(
                            "orders.events",
                            event.orderId(),
                            event).join();
                });
    }
}
~~~

The example waits on the future to illustrate scope and errors; production code needs proper deadlines/timeouts rather than waiting indefinitely. The `orders.submit` business observation is a separate span/observation wrapping the producer observation; with tracing handlers configured properly, the Kafka producer span links to the active operation.

Avoid creating endless nested observations for every tiny helper. Pick meaningful business boundaries so traces stay readable and sampling/overhead stays reasonable.

## 10. Propagating trace context from @KafkaListener to KafkaTemplate

A Kafka-to-Kafka pipeline typically looks like:

~~~text
orders.events
     |
     v
@KafkaListener (billing service)
     |
     v
BillingService.process()
     |
     v
KafkaTemplate.send("billing.results", ...)
~~~

For the second send's producer span to link to the consumed record, instrument both **consumer** and **producer**.

Example listener factory with observation enabled:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
observedOrdersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        ObservationRegistry observationRegistry) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setObservationRegistry(observationRegistry);
    factory.getContainerProperties()
            .setObservationEnabled(true);

    return factory;
}
~~~

Listener method:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "observedOrdersListenerFactory")
public void onOrder(OrderEvent event) {
    BillingResult result = billingService.process(event);
    billingKafkaTemplate.send(
            "billing.results", event.orderId(), result);
}
~~~

This skeleton illustrates the flow; matching beans and serializers are required. Spring Kafka tracing integration attempts to extract context from incoming headers when consumer observation is enabled, and producer observation can then inject context for the next send.

### 10.1. Same JVM does not imply same trace

Kafka listeners, HTTP controllers, and scheduled jobs can run on different threads and scopes. Simply residing in the same application does not give them a shared parent context. A scheduled Kafka publisher typically starts a new trace; an instrumented listener can continue the trace context from the incoming record.

## 11. Thread boundaries: a common source of broken traces

Micrometer Tracing typically relies on context scopes bound to the current execution/thread. When a producer send runs on a different thread, context does not automatically follow.

Example:

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {
    executor.submit(() -> {
        kafkaTemplate.send("orders.audit", event.orderId(), event);
    });
}
~~~

Here, the task is submitted from the consumer thread but executes on an executor thread. Without context propagation, the worker's producer observation may lack a parent trace and start a new one.

**Reliability warning:** Beyond tracing, returning from the listener before the worker finishes can allow offsets to be acknowledged/committed while the Kafka send is not yet durable. Fixing trace context **is not enough** to protect data; handle acknowledgments, transactions, and task durability separately.

### 11.1. Using Micrometer Context Propagation when appropriate

In Micrometer Context Propagation versions that support it, you can capture and restore context across threads:

~~~java
ContextSnapshot snapshot =
        ContextSnapshotFactory.builder()
                .build()
                .captureAll();

executor.submit(() -> {
    try (ContextSnapshot.Scope ignored =
                 snapshot.setThreadLocals()) {
        kafkaTemplate.send(
                "orders.audit",
                event.orderId(),
                event);
    }
});
~~~

This snippet illustrates **context propagation**, not a complete reliable Kafka processing flow. It requires the context-propagation library, accessors, and matching registry. Exact APIs and auto-configuration vary by Micrometer/Spring Boot version.

### 11.2. Never hold scopes open indefinitely

Every task must close its scope via `try-with-resources` or an equivalent safe pattern. Forgetting to close scopes on a thread pool leaks the prior request's context into subsequent tasks, corrupting traces and risking cross-tenant metadata leakage.

### 11.3. CompletableFuture and callbacks

`whenComplete(...)` may execute on whichever thread completes the future, not the originating thread. If the callback creates a new span or publishes another record, explicitly capture/restore context using the appropriate API. Do not grab a `ThreadLocal` trace ID manually and pass it through every callback when standard context propagation exists.

## 12. Trace context from scheduled producers and batch jobs

A producer may not originate from an HTTP call or Kafka consumer—for instance, a periodic job scanning an outbox and publishing events.

~~~text
@Scheduled / outbox publisher
             |
             v
        KafkaTemplate.send()
             |
             v
         Kafka topic
~~~

With no parent request, producer observation can start a new trace. That is completely valid; there is no need to invent a fixed trace ID for an entire job run.

Prefer:

- One observation for the batch/job execution if helpful.
- Stable event IDs or outbox IDs for business reconciliation.
- Producer observations per send or at an appropriate scope.
- Links between logs and event state when records are replayed.

Do not force every event from a multi-hour cron job onto the same trace ID just to see a single trace on a dashboard. Traces have size, duration, and sampling limits; long-lived work relationships belong in business correlation IDs and state stores.

## 13. ProducerRecord trace context and KafkaHeaders

`KafkaTemplate` supports sending records with keys, values, and headers. Example adding business metadata:

~~~java
ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>(
                "orders.events",
                event.orderId(),
                event);

record.headers().add(
        "event-id",
        event.eventId().getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
~~~

When producer observation is enabled, tracing context is injected on send. `event-id` is application-managed business metadata; it is distinct from `traceparent` managed by the propagator.

### 13.1. Do not manually add traceparent when auto-injection is active

Anti-pattern to avoid:

~~~java
record.headers().add(
        "traceparent",
        myManualTraceparent.getBytes(StandardCharsets.UTF_8));
kafkaTemplate.send(record); // template also injects context automatically.
~~~

This creates duplicate or stale propagation metadata. Manage headers manually only if the system genuinely lacks instrumentation, and even then follow propagation/encoding standards and trust-boundary rules.

### 13.2. Trace context vs. KafkaHeaders.CORRELATION_ID

Spring Kafka defines headers like `KafkaHeaders.CORRELATION_ID` for request-reply/correlation in certain flows. They **do not replace** `traceparent`.

| Data | Purpose |
|---|---|
| `traceparent` | Distributed trace propagation |
| `KafkaHeaders.CORRELATION_ID` | Match a request with a reply per a specific contract |
| Application-defined `event-id` | Business idempotency/deduplication |
| Kafka record key | Partition routing and ordering |
| Kafka topic/partition/offset | Physical record location |

An event can carry trace context, a correlation ID, and an event ID simultaneously. Never mix their roles.

## 14. Kafka header names and encoding

Kafka header keys are strings and values are byte arrays. Propagators encode text context into appropriate bytes. For tooling inspection, you only need to know the header name and encoding; avoid logging all headers in production.

Example reading `traceparent` from `ConsumerRecord` during debugging:

~~~java
private static String traceparentOrNull(
        ConsumerRecord<?, ?> record) {

    Header header = record.headers().lastHeader("traceparent");
    if (header == null || header.value() == null) {
        return null;
    }

    return new String(
            header.value(),
            StandardCharsets.US_ASCII);
}
~~~

This snippet is a **debug utility**, not an implementation for manually extracting and activating trace context. The tracing library's propagator should handle validation, sampling flags, relationships, and baggage consistently.

### 14.1. Avoid logging all headers

Some headers can carry tokens, user metadata, stack traces, or other payloads. Use an allowlist for diagnostics—for instance, logging only `traceparent present=true`, topic, and protected event IDs.

### 14.2. Validate length and input data

Producers and middleware may receive trace info from untrusted upstreams. Never feed an oversized or malformed header into metric tags or unbounded database columns. Let the propagator library parse and validate per standard, and let the application enforce header limits based on trust boundaries and security policy.

## 15. Sampling and why some events lack traces

Traces are normally sampled to control storage costs:

- Some requests are sampled and export spans.
- Some requests are unsampled, leaving no spans in the backend.
- Some spans are dropped due to exporter/collector failures.
- Some records never had a parent trace to begin with.

**Not finding a trace in the backend does not necessarily mean the record lacked trace context or the producer failed to send to Kafka.** Trace propagation and span export are two separate stages.

### 15.1. Sampling flag in traceparent

W3C `traceparent` includes flags where the sampled bit typically conveys the sampling decision. Propagators/tracing bridges interpret this. Do not manually flip the sampled flag on Kafka headers to force every trace to appear; actual retention still depends on samplers, remote parents, and tracing policies.

### 15.2. High Kafka throughput and tracing cost

A producer emitting hundreds of thousands of messages per second can generate enormous span volumes at 100% sampling.

Considerations:

- Tune sampling per service and business flow.
- Choose head-based or tail-based sampling suited to your stack.
- Maintain sufficient aggregate metrics to track throughput/errors even when traces are sampled.
- Raise sampling temporarily during controlled investigations.
- Monitor exporter drops and storage costs.

Never rely solely on traces to count **total Kafka records sent**; metrics/counters are built for complete statistics.

## 16. Low-cardinality and high-cardinality attributes

Observations can carry attributes/tags for tracing and metrics. Distinguish:

| Attribute | Cardinality | Where to use? |
|---|---|---|
| Service name | Low | Metrics/traces |
| Kafka topic (bounded set) | Usually low–medium | Metrics/traces if controlled |
| Operation type | Low | Metrics/traces |
| Result success/failure | Low | Metrics/traces |
| Normalized exception class | Bounded | Metrics/traces as needed |
| Trace ID | Very high | Logs/traces, never a metric label |
| Event ID / order ID / customer ID | Very high | Correlation logs/state, never a metric label |
| Kafka offset | Very high | Selective debug logs/traces, never a metric label |
| Exception message / raw header | Unbounded and potentially sensitive | Avoid in metrics; sanitize in logs |

A custom observation convention can add helpful metadata, but placing event IDs or trace IDs into low-cardinality tags can trigger time-series explosion.

### 16.1. Treat tracing baggage as widely propagated data

Baggage can travel from producer through Kafka, consumers, and multiple downstream services. Never place:

- Passwords, access tokens, API keys.
- Emails, phone numbers, home addresses.
- Full customer profiles or card data.
- Sensitive business payload contents.

If tenant correlation is needed, choose a security-classified, bounded, allowlisted ID that is not auto-exported into every span/metric. Importantly: **baggage propagation may be restricted or disabled by default**, depending on library configuration.

## 17. Trace context and Kafka transactions

In Spring Kafka, a transactional `KafkaTemplate` can execute multiple sends and then commit or abort the same Kafka transaction.

~~~text
BEGIN Kafka transaction
       |
       +-- KafkaTemplate.send(record A)
       |       producer observation/span A
       |
       +-- KafkaTemplate.send(record B)
       |       producer observation/span B
       |
       v
COMMIT or ABORT Kafka transaction
~~~

The trace contexts of A and B may share the same trace or parent observation, yet **individual send spans are not final confirmation of the transaction**.

### 17.1. A successfully sent record is not necessarily committed

A `send()` future can acknowledge that the broker received a record inside a transaction, and the transaction can later abort. Consumers using `read_committed` will not process records from an aborted transaction. The tracing backend may still display the producer span for the send that occurred.

Therefore, when investigating "traces show the producer sent it, yet the consumer never saw it," check:

- Did the Kafka transaction commit or abort?
- Are downstream consumers configured with `read_committed`?
- Was there a transaction timeout or fencing event?
- What do producer and transaction coordinator logs show?
- What are the exact topic, partition, event ID, and offset?

### 17.2. Kafka exactly-once does not mean traces emit exactly once

Kafka read-process-write EOS protects Kafka output state and consumed offsets. A listener can be re-invoked after an abort, producing additional traces and producer spans for failed attempts. Never deduplicate traces solely by Kafka offset.

Tracing reflects **execution attempts**, including failed ones; committed Kafka data and business state must be verified separately.

## 18. Trace context during producer retries

Kafka producers internally retry requests on transient failures. At the Spring Kafka layer, `KafkaTemplate.send(...)` typically represents one logical publish operation, while the Kafka client may perform multiple network attempts underneath.

Do not assume:

- Every network retry creates a separate producer span.
- One producer span equals exactly one network request.
- Trace duration equals broker processing time.
- Seeing a span means Kafka accepted exactly one business event.

To analyze internal retries, pair tracing spans with Kafka producer metrics (retry rate, request latency, record error metrics).

### 18.1. Application-level retries create new operations

If a service explicitly calls `send(...)` again after a failure, that may become a new producer observation. The two sends may share a trace if the parent context is still active, or belong to different traces if the retry happens later in a new job.

The event ID must **remain unchanged** so downstream consumers can deduplicate. Trace ID is not an idempotency key and can change across replays.

## 19. Trace context across retry topics and DLT

A failing record can be published by Spring Kafka infrastructure to a retry topic or dead-letter topic:

~~~text
orders.events
      |
      | listener fails
      v
orders.events-retry-...
      |
      | still fails
      v
orders.events-dlt
~~~

Republished records may retain certain original headers plus added retry/DLT metadata. **Whether trace headers are preserved, replaced, or instrumented as a new span** depends on the recoverer, template, custom header logic, observation configuration, and Spring Kafka version.

Do not assume every retry/DLT message gets a fresh `traceparent` or necessarily keeps the original record's trace ID. Verify actual behavior in an integration test.

### 19.1. Store event IDs outside trace IDs

When a record moves to retry/DLT, preserve:

- A stable event ID.
- Source topic/partition/offset when available.
- Retry attempt and failure reason in framework-supported formats.
- Trace context when policy allows and propagation fits.

Event IDs serve reconciliation/replay; trace IDs serve execution-attempt visibility. A trace can expire due to sampling/retention while the event still needs recovery days later.

### 19.2. DLT is not a tracing system

A DLT stores failed records according to Kafka retention. A trace backend stores spans according to its own retention/sampling. Never rely on "having a trace" instead of persisting DLT/recovery state, and never treat a Kafka DLT as a store for all logs/traces.

## 20. Producer interceptors and custom KafkaProducer

Spring Kafka observation integrates with the `KafkaTemplate` send path. If part of an application uses `org.apache.kafka.clients.producer.KafkaProducer` directly or another producer library, you cannot assume it is instrumented like `KafkaTemplate`.

Options:

1. Standardize publishing through Observation-enabled `KafkaTemplate`.
2. Use compatible instrumentation for native producers.
3. If using manual propagation, follow the protocol and avoid duplicate injection.
4. Test headers and spans on each publish path.

### 20.1. Header ordering matters with interceptors

Producer interceptors and custom serializers can modify record headers. An interceptor that strips or overwrites headers after instrumentation injects them will drop trace context. Conversely, an interceptor injecting its own headers can stack on top of template-added headers.

Therefore, when debugging propagation:

- List every component that touches `ProducerRecord`.
- Inspect the actual headers received by the consumer.
- Avoid uncontrolled mutation of record headers.
- Verify serializer and framework integration for your version.

Never fix a broken trace by copying trace headers from an unrelated record; that fabricates false trace relationships.

## 21. Producer–consumer span relationships are not always a single tree

In messaging, a single record can be:

- Consumed by multiple consumer groups.
- Republished to multiple topics.
- Batched alongside many records.
- Aggregated with other events.
- Replayed hours or days later.

When an operation processes multiple messages carrying different trace contexts, a simple parent-child model can fall short. Tracing systems use **span links** to reference multiple contexts. Specific instrumentation decides when to use parent-child vs. links.

Never force all messages in a batch into one trace by picking the first record's `traceparent`. Doing so merges independent requests into a misleading trace and loses traceability to the original events.

### 21.1. Batch producers

If an application publishes thousands of records in a loop, each send can have its own producer observation. Wrap the batch in a parent observation if helpful for understanding the job, but avoid creating an unbounded trace containing millions of spans.

### 21.2. Consumer group fan-out

One Kafka record can be processed independently by multiple consumer groups. Each consumer processing operation can create its own spans linked to the same producer context. Kafka does not guarantee only one consumer span per record across the cluster.

## 22. An integration test verifying header propagation

A unit test verifying only that `kafkaTemplate.send(...)` was called does not prove headers were actually injected. An integration test should send a record through Kafka and inspect headers at the consumer.

Scenario:

1. Configure `KafkaTemplate` with `ObservationRegistry` and a tracing bridge.
2. Select a consistent W3C propagator.
3. Start a parent observation/tracing scope in the test.
4. Send a Kafka record via the template.
5. Wait for the send future to succeed.
6. Have a test consumer read the record from the topic.
7. Assert Kafka headers contain valid trace context per the propagator.
8. Confirm consumer observation can extract/link the context.
9. Verify trace IDs/spans with an in-memory span exporter if supported by your stack.

Do not merely assert a raw header is non-null while ignoring malformed values. Test extraction using the same propagator the application uses.

### 22.1. Example checking headers in a consumer test

~~~java
ConsumerRecord<String, OrderEvent> received =
        KafkaTestUtils.getSingleRecord(
                consumer,
                "orders.events",
                Duration.ofSeconds(10));

Header traceHeader =
        received.headers().lastHeader("traceparent");

assertThat(traceHeader)
        .as("W3C trace context must propagate")
        .isNotNull();

String traceparent = new String(
        traceHeader.value(),
        StandardCharsets.US_ASCII);

assertThat(traceparent).startsWith("00-");
~~~

This is an illustrative test snippet, not a complete class; helper/assertion APIs must match your test library versions. Checking the `00-` prefix is only a basic check for W3C version `00` and **does not replace full validation**. In more thorough tests, extract with the propagator and assert trace ID / parent relationships.

### 22.2. Testing without an active parent

Send a record from a scheduled context with no parent span, and confirm instrumentation creates valid context per config or expected NOOP behavior. Do not assert that a trace ID matches a nonexistent HTTP request.

### 22.3. Testing asynchronous producer callbacks

Execute a send and handle `whenComplete` on another thread. If the callback starts a new operation, verify context propagation works and scopes are closed. Also verify send failures are never swallowed.

### 22.4. Testing sampling

Run tests with a sampler configured not to record spans and verify Kafka business logic still works. Then run with full sampling to test trace relationships. Separate "record delivery" from "span export" so tests do not fail purely due to sampling policy.

## 23. Testing across two microservices

An end-to-end test can cover:

~~~text
Service A
  HTTP request with trace context
    |
    v
  KafkaTemplate.send("orders.events")
    |
    v
Kafka broker
    |
    v
Service B
  @KafkaListener receives record
    |
    v
  KafkaTemplate.send("billing.results")
    |
    v
Test consumer or Service C
~~~

The test should verify:

- Producer A sends headers matching the propagator.
- Consumer B extracts the context.
- Producer B injects context linked to the active processing operation.
- Traces in the backend / in-memory exporter reflect the causal flow.
- Event IDs / record keys stay intact per contract.
- When B retries, no duplicate side effects occur if business rules forbid them.

Do not treat the trace UI as the sole oracle. Even when a trace has all spans, verify Kafka send/commit state and business state.

## 24. Troubleshooting: producer span exists, but consumer starts a new trace

Symptom: the trace backend shows Service A's Kafka producer span, while Service B's consumer span uses a different trace ID.

Steps:

1. Check whether Service A's `KafkaTemplate` has observation enabled.
2. Check Service A's Micrometer Tracing bridge and propagator.
3. Inspect actual headers on a safe test record in the topic.
4. Confirm `traceparent` or the chosen propagation format is present and valid.
5. Check whether Service B's listener container enables observation/extraction.
6. Check whether B uses the same propagation format or is still using B3.
7. Check whether consumer B processes records through a custom adapter that skips context extraction.
8. Check whether the event passed through retry/DLT/custom republishers that altered headers.
9. Check whether an async worker inside B lost the active context before creating a new span.
10. Check sampling/exporters before concluding the trace broke.

Never "fix" this by copying one static trace ID onto every record. Link the real context of each operation.

## 25. Troubleshooting: record has traceparent, but no trace appears in backend

Having a header does not guarantee a span was exported.

1. Check sampling probability and the sampled flag.
2. Check the tracing bridge and `ObservationHandlers`.
3. Check the exporter/collector endpoint, auth, and network.
4. Check exporter queues, dropped spans, and errors.
5. Check service name and resource attributes.
6. Check trace backend ingestion delay and retention.
7. Confirm the backend query uses the right trace ID and time window.
8. Check whether the record carries trace context from an older producer while the current service has tracing disabled.

Kafka records and headers can outlive tracing backend retention. An event replayed days later may carry the original trace ID even after the old trace has expired from the UI; that is not necessarily a Kafka fault.

## 26. Troubleshooting: producer callback shows a different trace

When `KafkaTemplate.send(...)` completes, the future callback may run on a producer network thread or another executor.

Steps:

1. Log the originating send thread and callback execution thread in a test environment.
2. Check whether the callback starts a new observation/span.
3. Check context propagation on the executor/callback.
4. Ensure the context snapshot is captured before leaving the original scope.
5. Restore context inside a short scope and close it cleanly.
6. Never leak or pass arbitrary `ThreadLocal` state across a shared thread pool.
7. Confirm send success/failure handling runs independently of tracing.

If the callback only logs the send outcome, it may not need a new span; structured logs with correlation identifiers suffice without dragging the whole trace scope into every log statement.

## 27. Troubleshooting: trace "reports send succeeded" but consumer never receives it

Do not start with tracing headers. Check Kafka delivery correctness first:

1. Check whether the send future actually succeeded, or only a producer span started.
2. If the producer is transactional, did the transaction commit or abort?
3. Check topic, partition, key, ACLs, and serialization.
4. Check consumer group subscriptions/assignments.
5. Check committed offsets and consumer lag.
6. Check consumer `read_committed` and open transactions/LSO.
7. Check deserialization/conversion errors.
8. Check retry/DLT recovery paths.
9. Reconcile the event ID in the business store.

Traces only locate the send attempt; they do not replace broker metadata or consumer group offsets.

## 28. Troubleshooting: trace context is duplicated or points to the wrong request

Symptoms:

- Multiple `traceparent` headers on the same record.
- Consumer displays a parent span belonging to an unrelated request.
- A worker processing event B logs the trace ID from event A.
- Trace data leaks across tenants.

Check:

1. Is manual injection running alongside `KafkaTemplate` auto-instrumentation?
2. Is a mutable `ProducerRecord` or `Headers` instance being reused?
3. Is an interceptor or custom republisher copying stale tracing headers?
4. Are context scopes on thread pools closed after every task?
5. Do producer and consumer propagators resolve header values consistently?
6. Are two instrumentation libraries double-instrumenting the same send?
7. Is an async callback capturing/retaining context at the wrong moment?

If trace context leaks across tenants, treat it as a serious security/correlation incident, not just a UI glitch.

## 29. Tracing and idempotency are separate concerns

A producer can send event A twice due to a retry outside a Kafka transaction:

~~~text
event-id = evt-100

Attempt 1: KafkaTemplate.send(...) -> unknown outcome
Attempt 2: KafkaTemplate.send(...) -> success
~~~

The two attempts may carry the same trace ID or different trace IDs depending on timing and execution context. Downstream consumers must never use trace IDs to decide whether a record is a duplicate.

Idempotency must rely on:

- Stable event IDs.
- Business command IDs / idempotency keys.
- Unique constraints or inbox state.
- Proper transaction/offset semantics.

Trace IDs observe a unit of work, not a unique business event identity. One trace can span multiple events, and one event can appear in multiple traces after replays.

## 30. Security rules when propagating context across Kafka

Kafka topics may be read by multiple consumer groups, retained long-term, and governed by varying access permissions. When injecting context:

- Transmit only fields required for tracing.
- Never put PII/secrets into `tracestate` or baggage.
- Treat headers arriving from producers outside your trust boundary as untrusted input.
- Bound header sizes and counts to prevent header amplification.
- Verify ACLs, TLS, retention, and topic access permissions.
- Never export raw payloads or secrets as span attributes.
- Allowlist tenant/correlation metadata.
- Never use trace IDs or event IDs as metric labels.
- Never treat `traceparent` as a cryptographic signature or proof of origin.

W3C trace context is correlation metadata, **not an authentication or authorization mechanism**. An untrusted producer can easily fabricate a syntactically valid `traceparent`.

### 30.1. Cross-tenant boundaries

In multi-tenant systems, decide whether to continue trace context arriving from an external tenant/source. Across certain security boundaries, starting a fresh trace and recording a controlled link may be safer than trusting arbitrary remote context.

Never dump tenant IDs, customer IDs, or request bodies into baggage merely to make trace searches convenient.

## 31. Dashboards and metrics alongside traces

Traces excel at investigating one specific journey; metrics excel at overall trends.

| Operational question | Right signal |
|---|---|
 How many records/s is the producer sending? | Kafka producer send/record metrics |
| Is the send failure rate rising? | Producer error counters, send failures |
| How is send latency changing? | Kafka client request metrics, observation duration |
| Which request produced the failing record? | Trace context + structured logs/event ID |
| Is the consumer group keeping up? | Committed lag, fetch lag, completion rate |
| Did the transaction commit or abort? | Transaction metrics/logs |
| Is there a retry/DLT backlog? | Retry topic lag, DLT rate, and recovery state |
| Is the tracing collector dropping spans? | Exporter/collector drops/errors |

Never alert solely because a single span is missing. Check sampling and exporter health. During major incidents, use metrics/logs/offsets to gauge impact, and traces to pinpoint the causal path.

### 31.1. Using exemplars when the stack supports them

Some observability stacks link metric samples to trace IDs via exemplars. This gives a useful jump from a latency spike to a concrete trace without turning trace IDs into high-cardinality labels on every time series.

Visibility depends on backend, exporter, and sampling; do not assume every Grafana/Prometheus setup enables exemplars automatically.

## 32. Implementation checklist for producer trace context

### Instrumentation

- [ ] Spring Kafka version supports producer observation.
- [ ] Actual `KafkaTemplate` in use has `setObservationEnabled(true)`.
- [ ] Appropriate `ObservationRegistry` is attached to the template.
- [ ] Micrometer Tracing bridge and tracer backend/exporter are configured per architecture.
- [ ] Producer and consumer agree on a propagation format (e.g., W3C).
- [ ] Sampling policy matches throughput and investigation needs.

### Kafka headers

- [ ] Integration test proves trace context is injected into records.
- [ ] Consumer extracts context with the matching propagator.
- [ ] No manual `traceparent` injection duplicating auto-instrumentation.
- [ ] No mutating or copying stale tracing headers across records.
- [ ] Policy defined for headers arriving from untrusted sources.
- [ ] No tokens, PII, or secrets passed in baggage.

### Threading and lifecycle

- [ ] Context propagation explicitly designed for async tasks/callbacks.
- [ ] Context scopes properly closed to prevent thread-pool bleed.
- [ ] Kafka offsets are not committed prematurely on async handoff just because tracing works.
- [ ] Transaction commits/aborts observed separately from producer spans.
- [ ] Retry/DLT/replay preserves event IDs and source metadata per contract.

### Operations

- [ ] Metrics track Kafka send success/failure, latency, and consumer lag.
- [ ] Logs include correlation metadata without leaking sensitive data.
- [ ] Tracing exporter/collector exposes health metrics.
- [ ] Runbooks exist for missing traces, split traces, and duplicate headers.
- [ ] Tested sampling, broker send failures, and Kafka transaction aborts.
- [ ] Trace IDs are never treated as idempotency keys or proof of Kafka delivery.

## Conclusion

**Producer trace context** lets a `KafkaTemplate.send(...)` operation connect with upstream work and carry context to consumers through Kafka record headers. In modern Spring Kafka, this typically means enabling **Micrometer Observation** on `KafkaTemplate`, wired with `ObservationRegistry`, a Micrometer Tracing bridge, and a consistent propagator such as W3C Trace Context. Both producer and consumer need proper instrumentation, especially across multiple services, thread pools, retry topics, and DLTs.

Tracing helps answer **"which flow produced this message?"**, but does not fully answer **"was the record committed by Kafka and did the business operation complete?"** Send futures, transaction commits, committed offsets, consumer lag, idempotency, and recovery state remain essential sources of truth for reliability. Keep trace context within its proper boundaries, avoid duplicate headers, handle async context carefully, control baggage and sampling, and verify real Kafka header propagation with integration tests before relying on tracing during an incident.
