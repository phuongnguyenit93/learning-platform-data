# Linking traces across topics and listeners

In a Spring Kafka system, a request may start at an HTTP API, emit an event onto Kafka, pass through several consumer groups, and only then complete its business flow. Services may function correctly while incident investigation remains hard if every component logs in isolation: when an order is slow, you do not know whether latency sits in the producer, broker, listener, database, or a retry attempt.

**Linking traces across topics and listeners** is the process of propagating trace context from the record sender through **Kafka headers**, then restoring that context on the receiver so observed spans connect inside a distributed tracing system. In modern Spring Kafka, this model is built primarily on **Micrometer Observation**, **Micrometer Tracing**, and a tracer implementation such as OpenTelemetry or Brave.

The goal is seeing a continuous logical journey:

    HTTP POST /orders
         |
         v
    order-api: HTTP server span
         |
         +--> validate command span
         |
         +--> Kafka producer span: orders.created
                      |
                      v
                 Kafka topic
                      |
                      v
    inventory-worker: Kafka listener span
         |
         +--> inventory DB span
         |
         +--> Kafka producer span: inventory.reserved
                      |
                      v
                 Kafka topic
                      |
                      v
    billing-worker: Kafka listener span
         |
         +--> payment API span

A trace helps identify related segments of work, yet **a trace is not a message delivery mechanism**, does not guarantee exactly-once processing, and does not replace offsets, consumer lag, or event IDs. Tracing must be deployed alongside Kafka's built-in reliability mechanisms.

## 1. What are trace, span, and trace context?

**Trace** represents a logical workflow spanning multiple components. It is identified by a trace ID.

**Span** represents a single operation within a trace, such as an HTTP request, sending a Kafka record, or processing a record in `@KafkaListener`. A span has a span ID, start/end timestamps, parent/link relationships per the tracer model, tags/attributes, and an optional error status.

**Trace context** is the information sufficient for a receiver to tell which trace chain a record belongs to. Context typically includes the trace ID, span ID of the relevant operation, sampling flags, and additional fields per the propagation format.

Conceptual example:

    TraceId = 8c0e...d742

    Span A: HTTP POST /orders
       |
       +-- Span B: kafka send orders.created
             |
             +-- Span C: consume orders.created
                    |
                    +-- Span D: SQL INSERT inventory

A tracing system may display parent-child relationships or span links depending on instrumentation and tracing conventions for asynchronous messaging. Never force every messaging span into a single parent-child tree if the library or processing model uses different links.

## 2. How does trace context cross Kafka?

A Kafka record holds a **key**, **value**, topic/partition/offset metadata, and **headers**. Kafka does not understand trace IDs itself, but headers let producers attach context that consumers can read.

    Producer JVM
        |
        | current tracing context
        v
    Trace propagator INJECTS into Kafka Headers
        |
        v
    Kafka ProducerRecord
      topic: orders.created
      key: O-100
      value: {...}
      headers:
        traceparent: ...
        tracestate: ...
        baggage: ...       (if enabled)
        event-id: evt-100  (separate business header)
        |
        v
    Broker stores record and headers
        |
        v
    ConsumerRecord
        |
        v
    Trace propagator EXTRACTS from headers
        |
        v
    Spring Kafka listener Observation / Span
        |
        v
    @KafkaListener business code

The broker **does not create a span for every record by default** simply because the record carries tracing headers. The broker only stores and serves records. Instrumentation in producers, consumers, and involved services creates the spans.

If a producer does not inject tracing context, the consumer may start a new trace. If a consumer fails to extract context, both services may create valid spans yet fail to link together.

## 3. A topic is neither a span nor a trace ID

A topic holds millions of messages from many requests and workflows. A topic name is only a transport channel, insufficient to identify a specific journey.

Distinction:

| Concept | Example | Purpose |
|---|---|---|
| Topic | `orders.created` | Message channel |
| Partition | `3` | Ordering / local parallelism |
| Offset | `7281` | Record position in a partition |
| Event ID | `evt-100` | Business event identifier |
| Correlation ID | `cmd-987` | Connects steps of a workflow |
| Trace ID | `4bf9...4736` | Trace chain identifier |
| Span ID | `00f0...e0e1` | Single operation identifier in a trace |
| Consumer group | `inventory-worker` | Independent consumption unit |

Event IDs should persist across retries and re-drives to support idempotency. Trace IDs serve observability and may differ across separate replay runs depending on tracing policy.

Never use trace ID instead of event ID as a deduplication key: sampling, fresh root traces, or event replays can change the tracing context.

## 4. Scenarios requiring trace linking

There are several communication patterns:

1. **HTTP → Kafka → Listener:** track from the incoming request to consumer processing.
2. **Listener → Kafka → Another listener:** follow an event-processing pipeline chain.
3. **Scheduler → Kafka → Listener:** no HTTP parent; the scheduler can start a root observation.
4. **One record → multiple topics:** a listener emits several downstream events with appropriate context.
5. **One topic → multiple consumer groups:** the same record is processed independently by multiple groups.
6. **Retry/DLT/re-drive:** a record is processed multiple times, needing visibility into each attempt and cause.
7. **Batch/aggregate:** one output depends on multiple inputs; trace relationships no longer have a single parent.

Tracing goals differ between synchronous and asynchronous flows. Do not assume one trace always represents an entire multi-day workflow; for long-running processing, a fresh trace with span links or business correlation IDs may work better.

## 5. Micrometer Observation and Micrometer Tracing

In modern Spring Kafka, the participating components are:

**Micrometer Observation** provides the API to create an observation around an operation, attaching key-values, errors, and lifecycle hooks. Observations can turn into metrics, traces, or both depending on configured handlers.

**Micrometer Tracing** bridges Observations to a tracer implementation. With a tracing handler present, an observation can create spans and participate in context propagation.

**OpenTelemetry/Brave bridge** supplies the tracer implementation and connects to exporters or tracing backends.

**Spring Kafka instrumentation** creates observations for send/receive paths when enabled on `KafkaTemplate` and listener containers.

Overview flow:

    KafkaTemplate.send()
       |
       v
    Micrometer Observation
       |
       v
    Tracing handler / Tracer
       |
       v
    Context propagator -> Kafka Headers
       |
       v
    Broker

    ConsumerRecord.Headers
       |
       v
    Context propagator extract
       |
       v
    Listener Observation
       |
       v
    Tracer span + @KafkaListener execution

Merely adding an OpenTelemetry dependency to the classpath **does not guarantee** `KafkaTemplate` and containers propagate context automatically; verify instrumentation and `ObservationRegistry` are actually configured.

## 6. Common dependencies

Gradle example with Spring Boot 3.x, assuming Spring Boot dependency management:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    // Actuator + Observation/metrics integration.
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Choose a suitable tracing bridge; e.g. OpenTelemetry.
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'

    // If exporting traces via OTLP to a collector/backend.
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    // Optional: if scraping metrics with Prometheus.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Use versions managed by the framework BOM rather than mixing incompatible Micrometer/OTel versions manually.

Another project may choose the Brave bridge instead of OpenTelemetry:

~~~gradle
implementation 'io.micrometer:micrometer-tracing-bridge-brave'
~~~

Normally **do not enable two tracer bridges simultaneously** without an explicit design. Having an exporter does not mean the collector is receiving data; endpoint, sampling, networking, and backend must all be working.

Spring Boot 4 and newer Spring Kafka releases may change starter/property names and defaults. When upgrading, check the exact dependency documentation instead of copying an old dependency list verbatim.

## 7. Enabling observation on KafkaTemplate and listeners

A Spring Kafka 3.x example configured explicitly in Java:

~~~java
@Configuration
public class KafkaObservationConfiguration {

    @Bean
    KafkaTemplate<String, OrderEvent> observedKafkaTemplate(
            ProducerFactory<String, OrderEvent> producerFactory) {

        KafkaTemplate<String, OrderEvent> template =
                new KafkaTemplate<>(producerFactory);

        // Enable producer observation/tracing for send().
        template.setObservationEnabled(true);

        return template;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);

        // Enable listener observation for record listeners.
        factory.getContainerProperties()
                .setObservationEnabled(true);

        return factory;
    }
}
~~~

Key imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
~~~

`OrderEvent` is an application DTO. The example assumes `ConsumerFactory`, `ProducerFactory`, serializers, and appropriate `ObservationRegistry`/tracing infrastructure already exist in the Spring context.

In many Spring Boot apps, Boot auto-configured templates/factories can be controlled via corresponding properties. If defining custom beans, confirm your custom beans are actually instrumented. Do not create an observed `KafkaTemplate` and accidentally inject a different template into your publishing service.

## 8. Spring Boot Kafka observation configuration

An orienting example for Spring Boot 3.x releases supporting these properties:

~~~yaml
spring:
  application:
    name: order-service
  kafka:
    bootstrap-servers: localhost:9092
    template:
      observation-enabled: true
    listener:
      observation-enabled: true
    consumer:
      group-id: order-workers
      enable-auto-commit: false

management:
  tracing:
    sampling:
      probability: 1.0
~~~

Sampling `1.0` is generally suitable for learning or testing, **not by default for production**, since span volume on high-record systems can become huge.

Actual bound properties and auto-configured beans depend on the Spring Boot version; if the project uses custom listener factories or custom `KafkaTemplate` beans, inspect Java configuration and runtime observations instead of assuming YAML took effect.

To export traces to an OpenTelemetry Collector, add exporter/tracing endpoints matching your Boot version and infrastructure. Never put a tracing endpoint into `Kafka bootstrap-servers`: the collector/exporter and the Kafka broker are separate targets.

## 9. Producer: active context is injected on send

Suppose an API receives `CreateOrderCommand` and emits an event:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderEvent event) {
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
    }
}
~~~

If the HTTP server request holds an active Observation/tracing context and `KafkaTemplate` has observation enabled, instrumentation can create a producer span and inject context into the sent record's headers.

    HTTP trace context
           |
           v
    Controller -> Service -> observed KafkaTemplate
                                |
                                v
                  Producer observation/span
                                |
                                v
                      Kafka record headers

You do not need to manually set `traceparent` by taking a trace ID and writing an arbitrary header string. A valid trace context needs consistent format, span ID, sampling flags, and propagator handling; let tracing instrumentation manage it.

For proper linking, the producer must execute within a scope where tracing context is active. If `send()` runs on another thread without context transfer, the record may start a new trace.

## 10. Consumer: extracting context before running the listener

Record listener:

~~~java
@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "orders.created",
        groupId = "order-workers",
        containerFactory = "ordersListenerFactory"
    )
    public void onOrder(ConsumerRecord<String, OrderEvent> record) {
        orderService.process(record.value());
    }
}
~~~

When the listener container enables observation and its propagator matches the producer's, Spring Kafka can extract context from `ConsumerRecord.headers()` to start an observation/span for that execution.

Once the tracer exports data, the tracing backend can show the consumption span linked to the producer span according to the relationship defined by active instrumentation and semantic conventions.

Even without producer context, listener observation remains useful: it can start a new root span for receiving that record. What you must verify is **correct trace linking when headers exist**, not merely that the consumer produces any span at all.

## 11. End-to-end example across two topics

Suppose Service A receives an order, Service B checks inventory, and Service C sends a notification.

    Service A:
      HTTP POST /orders
      |
      +-- send orders.created
              |
              v
           Topic 1
              |
              v
    Service B:
      @KafkaListener orders.created
      |
      +-- inventoryService.reserve(...)
      |
      +-- send inventory.reserved
              |
              v
           Topic 2
              |
              v
    Service C:
      @KafkaListener inventory.reserved
      |
      +-- notificationService.notify(...)

To link traces across two topics, proper instrumentation is needed on **both senders** and **both receivers**:

| Component | What is needed? |
|---|---|
| Service A `KafkaTemplate` | Inject tracing headers |
| Topic `orders.created` | Preserve Kafka record headers |
| Service B listener container | Extract tracing headers |
| Service B `KafkaTemplate` | Inject current context onto new record |
| Topic `inventory.reserved` | Carry new headers |
| Service C listener container | Extract tracing headers |
| Tracing backends | Receive spans from all three services |
| Sampling policy | Do not drop the spans needed for comparison |

Common mistake: Service B has an observed listener, yet publishes output with a `KafkaTemplate` whose observation is disabled. Service C can still create its own span, but lacks producer B's context to connect the chain.

## 12. Common header propagation: W3C Trace Context

A widely used propagation format is **W3C Trace Context**, comprising headers such as:

- **`traceparent`:** encodes version, trace ID, parent span ID, and flags.
- **`tracestate`:** additional vendor/tracer metadata when used.
- **`baggage`:** can carry extra contextual key-values if corresponding propagation is enabled.

Syntactic example of a `traceparent` value:

~~~text
traceparent:
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

This is a valid W3C-formatted example, not an ID generated for a real event. Kafka header values are byte arrays; instrumentation encodes/decodes them via the propagator.

Another deployment may use B3 propagation or multiple propagation formats simultaneously. If the producer emits B3 while the consumer only understands W3C, context extraction fails even though the Kafka record still carries headers.

**Standardize the propagation format across services** or configure a propagation bridge during migrations. Never work around mismatches by copying a plain text trace ID into a custom header and calling it complete distributed tracing.

## 13. What happens when tracing headers are absent?

A record may come from a legacy producer, CLI tool, batch import, or connector without tracing integration:

~~~text
topic: orders.created
key: O-100
value: {...}
headers:
  event-id: evt-100
~~~

The listener can still read and process the record. If observation is enabled, the system can start a new consumer span unlinked to any prior producer span.

This is not necessarily a data error. Recommended handling:

1. Keep consumer logic working when `traceparent` is missing.
2. Track the ratio of records with/without tracing context if needed.
3. Roll out propagation gradually to producers.
4. Use `eventId`/`correlationId` for business tracing when a distributed trace is absent.
5. Never reject a record merely for lacking a tracing header unless an exceptional contract explicitly mandates it.

Tracing serves observability—it must never become a hard gate halting event delivery whenever observability infrastructure misbehaves.

## 14. Sampling and why a trace may miss spans

Tracing can generate huge data volumes at high Kafka throughput. Sampling selects which traces are recorded/exported to control costs.

Example:

    Input: 10,000 records/s
    Producer + consumer: at least 2 spans per record
    At 100% sampling:
      >= 20,000 spans/s, excluding HTTP/DB/other spans

In production, lower sampling reduces storage and network usage, though some events will lack full traces in the backend.

Reasons a trace may appear incomplete:

- Parent was or was not sampled per tracer policy.
- Consumer failed to read the right propagation header.
- Span was created, yet the exporter failed to send it.
- Tracing backend filtered or rate-limited ingest.
- Some services do not have observation enabled.
- Root trace lasted too long or hit retention limits.
- Consumer uses a different propagation format from producer.

Never treat "trace not found" as proof a message was lost. Always check `eventId`, topic/partition/offset, consumer group committed offsets, and processing logs in parallel.

## 15. Baggage is not a place for business payloads

**Baggage** lets small key-values travel alongside tracing context across services. It can be helpful for tiny policy-compliant metadata, such as a sanitized workload classification code.

However:

- Baggage can propagate across many services and external systems.
- Some headers/baggage may appear in logs or exporters.
- Baggage increases Kafka header size.
- Baggage can be abused if accepted from untrusted sources.
- Not every baggage field automatically becomes a span attribute or log field.

Never put passwords, access tokens, personal emails, card numbers, full customer profiles, or sensitive payloads into baggage. Use event payloads and proper schema/authorization policies for business data.

If tenant identification is needed, consider a controlled tenant ID as separate business metadata, exposing it in traces only under clear security and retention policies.

## 16. Trace ID, correlation ID, and event ID serve different jobs

A well-designed system usually needs all three.

Example:

    eventId = evt-100
    correlationId = order-flow-99
    traceId = 9a2b...17de

**`eventId`** stays constant across retries and re-drives of the same event. Consumers use `eventId` for deduplication and audit lookups.

**`correlationId`** can connect multiple events within one business workflow spanning minutes or days, such as an entire ordering and payment lifecycle.

**`traceId`** describes an observed execution path. A retry hours later can appear as a new trace linked via `eventId`/`correlationId` or span links.

Never use trace IDs to authorize money transfers, confirm payments, or enforce idempotency. An event can process successfully even when sampling is off or the tracing backend is down.

## 17. Adding business spans inside a listener

While consumer observation is active, you can add a child observation around a slow business step to pinpoint where latency lies.

~~~java
@Service
public class InventoryService {

    private final ObservationRegistry observationRegistry;
    private final InventoryRepository repository;

    public InventoryService(
            ObservationRegistry observationRegistry,
            InventoryRepository repository) {

        this.observationRegistry = observationRegistry;
        this.repository = repository;
    }

    public void reserve(OrderEvent event) {
        Observation.createNotStarted(
                "inventory.reserve",
                observationRegistry)
            .lowCardinalityKeyValue("operation", "reserve")
            .observe(() -> repository.reserve(event.orderId()));
    }
}
~~~

Required imports:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;
~~~

This example assumes `repository.reserve()` is synchronous; the observed lambda starts and finishes its lifecycle on the same thread.

Depending on `ObservationRegistry` handlers and tracing configuration, this observation can emit a child span, a metric, or both. Use stable observation names; never attach `orderId`, `eventId`, or Kafka offset as **low-cardinality metric tags**.

If you need to find a specific event, place identifiers into structured logs or trace attributes per security policy rather than turning random IDs into metric labels.

## 18. Observing an asynchronous Kafka send

`KafkaTemplate.send()` typically returns a `CompletableFuture` with the send outcome. Returning a future does not mean the broker acknowledged or a producer transaction committed.

Example:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error("Kafka send failed for eventId={}",
                event.eventId(), error);
    }
});
~~~

`KafkaTemplate` observation captures the send operation via framework instrumentation. However, the callback running when the future completes may execute on a different thread where the original HTTP request's thread-local tracing context is no longer active.

Do not assume logs inside `whenComplete` will carry the same `traceId`/`spanId` just because the callback was registered on the request thread. If your application needs tracing inside callback logic, configure **context propagation** across executors/callbacks using your framework's mechanism.

When using Kafka transactions, send success / observation success also does not prove the transaction committed. Delivery analysis still requires transaction commit outcomes and broker confirmations.

## 19. Thread-local context and async executors

Most tracing context attaches to the active scope, commonly backed by thread-locals or framework context abstractions.

A synchronous listener:

    Consumer thread
       |
       +-- Listener Observation active
       |
       +-- inventoryService.reserve()
       |
       +-- kafkaTemplate.send()
       |
       v
    Listener Observation closes

Trace context flows naturally across synchronous calls on the same thread.

With async execution:

    Consumer thread
       |
       +-- executor.submit(task)
       |
       v
    Listener returns

    Worker thread
       |
       +-- task sends another Kafka event

Without transferring context, the worker thread may start a new trace. More importantly, if the listener returns before the task finishes, **the container may commit offsets too early**. Context propagation fixes trace linking, but **does not fix business durability**.

In Spring Framework 6.1+, `ContextPropagatingTaskDecorator` is available for compatible executors; example:

~~~java
@Bean
ThreadPoolTaskExecutor observedTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setTaskDecorator(
        new ContextPropagatingTaskDecorator()
    );

    executor.initialize();
    return executor;
}
~~~

Ensure dependencies and Spring Core / Task Executor imports match your version. This is a context propagation mechanism, not permission for early acknowledgment. When offloading Kafka records, implement completion/ack handling, bounded queues, and rebalance fencing.

## 20. Correlating logs with traces via MDC

In properly configured Micrometer Tracing / Spring Boot setups, tracing integration populates `traceId` and `spanId` into the active thread's MDC. When log patterns or JSON layouts support it, producer and consumer logs can be queried by the same trace.

Structured log example:

~~~text
timestamp=2026-11-15T10:00:00Z
service=inventory-worker
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
topic=orders.created
partition=2
offset=178
eventId=evt-100
message="Reservation processed"
~~~

Merely adding a tracing dependency does not guarantee every logging layout prints MDC fields automatically. Verify Logback/Log4j configuration, correlation patterns, and context propagation on executing threads.

If logs emitted by a worker thread lack `traceId`, inspect where Observation scopes open/close and cross threads rather than manually copying an old `traceId` into MDC and forgetting to clear it. Leaked MDC across tasks can stamp two different customers' logs with the wrong `traceId`.

## 21. How to investigate failures using trace IDs

A practical investigation workflow:

1. Grab a valid `traceId` from an HTTP response or application log if recorded.
2. Open the tracing backend and locate the trace containing the HTTP server span.
3. Inspect the producer span for the target topic.
4. Locate the consumer span associated with that record.
5. Compare the time gap between producer and consumer.
6. Inspect database/HTTP spans inside the listener.
7. If the consumer span is missing, check sampling, propagation, exporter, and listener observation.
8. Use `eventId` to reconcile records and logs even when traces are incomplete.
9. Check consumer lag and retry/DLT if delay lies primarily within Kafka.
10. Distinguish producer send / transaction completion from listener processing completion.

Traces reveal instrumented application steps. Without broker-level telemetry or event enqueue timestamps, the gap between producer span and consumer span is only an **estimate** of queue wait time—not an exact metric of Kafka broker latency.

## 22. Topic-to-listener latency vs. processing latency

Distinguish three measurements:

**Produce/send latency:** time for the producer to send and receive broker acknowledgment per the API/instrumentation used.

**Queue/transport wait:** interval from when a record becomes available on Kafka until a consumer starts processing it. This is affected by consumer lag, partition ordering, pauses, retries, and scheduling.

**Listener processing latency:** time spent by business code processing the record.

Example:

    Producer ACK at T0
    Consumer listener starts T0 + 25 s
    Listener finishes T0 + 25.040 s

Here the listener took only 40 ms, yet total path latency is around 25 seconds. Optimizing the business method from 40 ms down to 20 ms helps little if the bottleneck is backlog.

A trace can display producer and consumer spans, but **does not always hold a single span spanning the entire time the record sat in Kafka**. To monitor queue age, use record timestamps with appropriate metadata and metrics rather than fabricating an artificial multi-hour span.

## 23. Handling timestamps when measuring queue age

Kafka records carry a timestamp—either `CreateTime` or `LogAppendTime` depending on broker/topic settings. This timestamp is not necessarily when the producer tracing span ended.

An approximation:

    QueueAge = ConsumerStartTime - RecordTimestamp

Example listener reading `ConsumerRecord`:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    long ageMillis =
            System.currentTimeMillis() - record.timestamp();

    // Age metric; never use eventId as a metric tag.
    queueAgeRecorder.record(
        record.topic(),
        Math.max(ageMillis, 0L)
    );

    orderService.process(record.value());
}
~~~

`queueAgeRecorder` is an application-defined metric recorder. Values may be imprecise due to clock skew, timestamp policy, producer/broker delays, and replayed old records. Never treat this value as "broker processing time."

For messages replayed days later, `queueAge` can look huge even while the consumer processes rapidly. Separate original event age, replay age, and per-retry-topic delay.

## 24. How retrying a record affects traces

A record may be processed multiple times by a listener:

    orders.created offset 90
        |
        +-- attempt 1 -> database timeout
        |
        +-- attempt 2 -> database timeout
        |
        +-- attempt 3 -> success

If each attempt is instrumented, multiple consumer/listener observations may correspond to those attempts. Trace shape depends on the framework, error handler, sampling, and context handling.

Do not assume three listener attempts must share **the exact same span ID**. Each processing attempt is a separate execution, so spans naturally have distinct identities even when tied to the same record/tracing context.

For reliable retry observability, record:

- Stable event ID.
- Source topic, partition, and offset.
- Delivery attempt or retry stage when exposed by the API.
- Exception class.
- Delay/backoff and recovery attempt.
- Trace/span IDs of instrumented attempts.
- Offset commit or DLT outcome.

Traces do not replace retry counters. Sampling can drop some attempts, so never count actual processing attempts solely from visible spans.

## 25. Retry topics and trace propagation

With non-blocking retries, a record can traverse retry topics:

    orders.created
         |
         v
    orders.created-retry-1000
         |
         v
    orders.created-retry-5000
         |
         v
    orders.created-dlt

Producers/recoverers forwarding records to retry topics or DLTs may preserve or regenerate headers. Tracing stays continuous only if those publish/consume paths are instrumented or preserve context per your contract.

In Spring Kafka, `@RetryableTopic` and retry/DLT infrastructure can create their own listener containers and producer components. Enabling observation on one custom factory/template **does not automatically guarantee** every internal retry publisher is instrumented identically.

Check your Spring Kafka version and inspect actual record headers at each hop. If a retry topic producer does not inject new tracing context yet preserves the old `traceparent`, downstream consumers may still link back to the original upstream; however, that does not mean a retry publish span was recorded.

Trace design should reflect the real execution path rather than forcing every retry into one span stretched across long backoff delays.

## 26. Dead-letter topics and diagnosability

When processing still fails after retries, records typically route to a DLT with source details and exception metadata.

Example:

    Input:
      topic=orders.created
      partition=2
      offset=90
      eventId=evt-100
      tracing headers=...

    DLT:
      topic=orders.created.DLT
      eventId=evt-100
      original topic/partition/offset
      exception metadata
      tracing headers depending on recovery path

DLT metadata and tracing context serve two jobs:

- **DLT original headers:** locate the failed record and root cause.
- **Tracing headers:** locate related spans/logs in the trace backend.

Do not strip all headers on error republishing, as that can drop both trace context and `eventId`. Conversely, do not accumulate unbounded exception stack traces or sensitive baggage across multiple DLT hops.

When using `DeadLetterPublishingRecoverer`, verify serializer/template setup, header propagation, and framework exception-header stripping policies. Traces aid investigation, while the DLT record and `eventId` remain the durable data evidence.

## 27. Re-driving a DLT: continue the old trace or start a new one?

An event replayed hours or days later should not necessarily continue the same trace ID as the initial failure.

Example:

    Day 1:
      Trace A: producer -> listener -> error -> DLT

    Day 3:
      Operator fixes schema
      Re-drives DLT record
      Trace B: re-drive job -> listener -> success

For investigations, it is often cleaner for Trace B to be a fresh activity linked back to Trace A via:

- Event ID.
- Replay ID.
- Correlation ID.
- DLT original topic/partition/offset.
- Span links if supported by the tracing API/runtime.
- Audit records or logs keyed by `eventId`.

If re-drive copies raw DLT tracing headers verbatim, consumers may extract a parent from the old trace. That is not always wrong, though it can produce multi-day traces that are hard to interpret. Choose an intentional policy: preserve history via business correlation or trace links, or continue the parent context only when recovery is short-lived.

**Never alter `traceparent` by manually rewriting part of the trace ID.** To start a fresh trace or attach a span link, use the framework's tracing API and propagator to maintain valid semantic conventions.

## 28. Fan-out: one record read by multiple consumer groups

Kafka lets multiple consumer groups process the same record:

    Topic: orders.created
          |
          +--> Group inventory-service
          |
          +--> Group fraud-service
          |
          +--> Group notification-service

All three groups can read the same tracing headers and each produce its own consumer span. All relate to the original record while running at different times and in different environments.

This means:

- A single producer event can yield multiple consumer spans.
- Never treat one consumer span as proof every group processed the record.
- Each group maintains independent committed offsets and retry policies.
- One group may fail/DLT while another group succeeds.
- Sampling rates can differ per service, making traces appear partial.

If you need confirmation that all consumer groups finished business work, use workflow tracking or application-level acknowledgments rather than inferring from trace topology.

## 29. Fan-in: multiple records producing one output

A service may wait for three events before emitting one output:

    payment.approved (trace A) ----+
                                  |
    stock.reserved (trace B) ------+--> order.completed (trace ?)
                                  |
    shipment.ready (trace C) ------+

No single parent span fully represents all three sources. Picking the last event's context as the sole parent can mislead trace viewers into thinking the output depended only on that source.

Options:

1. Start a fresh trace for the aggregation step, carrying business correlation IDs.
2. If supported by your tracer, add **span links** to the contexts of participating inputs.
3. Record input event IDs in structured audit logs.
4. Never cram an unbounded list of trace contexts into an arbitrary Kafka header.

In batch/aggregation flows, span links and workflow audits express reality far better than a forced single parent-child tree.

## 30. Batch listeners have distinct limitations

Record listeners have clear context per `ConsumerRecord`. Batch listeners receive multiple records that can hold **many different tracing contexts**.

Example:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "batchOrdersFactory"
)
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }
}
~~~

If a batch holds 200 records from 200 HTTP requests, you cannot arbitrarily pick the first record's tracing context as parent for the whole batch and claim all 200 belong to one trace.

Different Spring Kafka versions support Observation on batch listeners to different degrees; check the exact capabilities and limits of your running version. When strict per-record trace continuity is required, record listeners usually offer a simpler tracing model.

If batch throughput is still required:

- Retain each record's event ID.
- Measure batch processing duration separately.
- Never assume one consumer span automatically links to all trace contexts.
- Use span links or per-record instrumentation where supported.
- Avoid creating thousands of spans/records on one thread without benchmarking performance.

## 31. Transactions and the "send succeeded" illusion

Inside a Kafka transaction, a producer can send outputs and then the transaction can abort:

    Listener starts Kafka transaction
       |
       v
    KafkaTemplate.send()
       |
       v
    Producer receives ACK
       |
       v
    Business exception
       |
       v
    abortTransaction()
       |
       v
    Output is not visible to read_committed consumers

A producer span may show the send call completed, which **is not enough to conclude the Kafka transaction committed**.

To investigate EOS, also monitor:

- Producer transaction begin/commit/abort.
- Transaction duration and errors.
- Input consumer offsets committed.
- Output visibility under `read_committed`.
- DLT/recovery transaction outcomes if applicable.

Likewise, a finished consumer span does not guarantee DB side effects committed if the listener offloaded async work and returned early. Distributed tracing records instrumented execution paths, not durable transaction proofs.

## 32. Trace propagation and deserialization errors

Deserialization errors can occur **before `@KafkaListener` ever receives an object**. With `ErrorHandlingDeserializer`, Spring Kafka places error metadata into headers for the container/error handler to process.

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
~~~

During deserialization failures:

- Original tracing headers may still be present on `ConsumerRecord` unless stripped upstream.
- The business listener method may not be invoked.
- A recoverer may publish raw bytes to a DLT.
- Specific listener observations and spans depend on the version/framework error-handling path.

If a trace lacks a business listener span while a DLT holds the failed record, check whether an exception fired before the listener. Never treat the absence of a listener span as proof the consumer never polled the record.

## 33. Header size, sensitive data, and load

Tracing headers are normally small compared to payloads, yet not free. When records bounce through retries/DLTs repeatedly or applications attach too much baggage, header sizes grow.

Impacts:

- Larger records increase network and storage usage.
- Producers/brokers may reject records exceeding size limits.
- Headers can be read by any consumer authorized on the topic.
- Tracing baggage may leak into logs/telemetry.
- Size and cardinality grow if custom headers are added without rules.

Principles:

1. Propagate only context needed for tracing.
2. Never serialize whole observation/span objects into Kafka headers.
3. Never store tokens, secrets, or PII in baggage.
4. Never duplicate `traceparent` on every retry via unbounded appending.
5. Keep `eventId`/`correlationId` in dedicated business contracts.
6. Enforce ACLs and retention on DLTs carrying exception context.
7. Monitor header byte sizes when record growth is suspected.

Kafka headers can hold multiple entries with the same key. During debugging, inspect the full list `headers(name)` instead of only `lastHeader()` if you suspect a producer/recoverer appended duplicates.

## 34. Inspecting tracing headers in ConsumerRecord

To debug in a test environment, inspect the propagation headers actually received by the consumer:

~~~java
@KafkaListener(topics = "orders.debug")
public void inspect(ConsumerRecord<String, byte[]> record) {

    for (Header header : record.headers()) {
        String name = header.key();

        if ("traceparent".equals(name)) {
            String value = new String(
                header.value(),
                StandardCharsets.US_ASCII
            );

            log.debug("traceparent present: {}", value);
        }
    }
}
~~~

Imports:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
~~~

This is an **illustrative debug snippet**; in production, avoid logging raw `traceparent` on every record. Recording a context present/missing metric and logging trace IDs via tracing/MDC suffices.

If the application uses B3 propagation, searching only for `traceparent` is inconclusive. Verify the propagation formats and header names actually configured on the tracer.

## 35. Why do producer and consumer traces fail to link?

Diagnostic table:

| Symptom | Possible cause | How to check |
|---|---|---|
| Producer span exists, consumer starts a new trace | Consumer fails to extract context | Listener observation, propagator, headers |
| Consumer span exists, no producer span | Producer observation disabled or span not exported | Template config, sampling, exporter |
| Headers present, no trace in backend | Sampling or export/collector failure | Trace sampling, OTLP metrics/logs |
| Context lost only across an intermediary service | Service uses another producer or recreates records without context | Actual `KafkaTemplate`, header injection |
| Context lost only in async workers | Thread context not propagated | Executor/decorator/callback |
| Retry topic spans disconnected | Internal retry publisher/consumer uses different instrumentation | Retry infrastructure, actual headers |
| DLT has `eventId` but no trace | DLT republished via uninstrumented path | Recoverer `KafkaTemplate`, header policy |
| Giant trace spanning multiple days | Re-drive kept old remote parent context | Replay policy, span links/correlation |
| Logs lack `traceId` while backend has spans | Missing MDC/log pattern or thread context | Logging config and scope |
| Traces cross-link between two requests | Thread-local/MDC scope leaked | Executor reuse, manual MDC edits |

Verify each hop in sequence: **does the record have headers? → does the consumer extract them? → is a span created? → does the exporter send it? → does the backend store it?**. Walking this order is faster than blindly tweaking sampling or restarting Kafka.

## 36. Observing traces in multi-instance environments

Consider a consumer group with three pods and multiple partitions:

    orders.created P0/P1 -> pod A
                   P2/P3 -> pod B
                   P4/P5 -> pod C

The same trace can cross pod A and then pod C if steps traverse different topics. To follow the route:

- Assign a stable `service.name` to each application.
- Capture instance/pod identity in appropriate resource attributes.
- Record topic/destination and operation on messaging spans per instrumentation.
- Use `eventId` to query specific logs by partition/offset.
- Never use pod IP as a business correlation ID.
- During consumer rebalances, a record may be reprocessed on a different pod.

If only one pod exports traces while other pods do not, the trace viewer shows gaps even though the pipeline works fine.

For high-cardinality resource identities like pod UID, follow exporter/backend policies to avoid abnormal telemetry costs.

## 37. Sampling on retries and high-volume topics

A consumer handling 50,000 records/second does not necessarily need to export every producer/consumer span. Choose a sampling policy aligned with requirements.

Approaches:

**Head-based sampling:** decides sampling at the start of the trace; decisions propagate easily via headers, though errors occurring later may go unsampled if the trace was dropped upfront.

**Tail-based sampling:** collector/backend decides after seeing spans, helpful for prioritizing errors/latency; requires collector memory and buffering time.

**Service/workload-based sampling:** prioritizes sensitive topics or error paths without breaking the propagation contract.

Never turn `eventId` into a metric label or dump full payloads into spans to compensate for low sampling. For DLTs/incidents, structured logs and audits are more reliable because they follow dedicated retention policies.

If the backend lacks strong tail sampling or link support, do not assume every retry attempt can be retrieved in one continuous trace.

## 38. A minimal tracing contract across teams

In an organization with multiple producers and consumers, agree on:

- Propagation format: W3C `traceparent`/`tracestate` or chosen standard.
- Instrumentation mechanisms on producers and consumers.
- Enabling observation on the factories/templates actually in use.
- Service names and span/observation naming rules.
- Production sampling policy.
- `eventId` and `correlationId` as business contracts, independent of tracers.
- Tracing policy for retries, DLTs, and re-drives.
- Policy forbidding secrets/PII in baggage/headers.
- Monitoring exporters and missing spans.
- Runbooks for tracing records across Kafka topic/partition/offset.

When producers are Java/Spring and consumers are Go/Python/Node.js, test instrumentation on both sides. Simply both using OpenTelemetry does not guarantee identical propagation if one service uses W3C and another uses a different format.

## 39. Integration test: HTTP → Kafka → listener

A meaningful integration test must prove **propagation**, not merely span presence.

Scenario:

1. Run the application with suitable tracing / test `ObservationRegistry`.
2. Send an inbound HTTP request carrying a controlled trace context.
3. Have the service call an observed `KafkaTemplate` to publish an event with a fixed `eventId`.
4. Have a test consumer read the raw record and assert the expected tracing header is present.
5. Let the observation-enabled listener container process the event.
6. Collect spans with an in-memory exporter / test tracer.
7. Assert both producer and consumer observations/spans exist.
8. Assert trace linkage matches your instrumentation version.
9. Assert topic, `eventId`, source offset, and business side effects match expectations.
10. Verify processing still succeeds when the tracing exporter is unavailable.

In tests, you can configure 100% sampling with a collector / in-memory span exporter to avoid random drops. Never use 100% test sampling to assume production will capture every trace.

Testing only that `ConsumerRecord` has `traceparent` proves the producer injected the header; it does not yet prove the consumer extracted it and linked spans.

## 40. Integration test: consumer forwarding to a second topic

Multi-hop test:

    HTTP trace -> Topic A -> Listener A
                       |
                       v
                     Topic B -> Listener B

Steps:

1. Publish an event to Topic A using an observed producer.
2. Listener A processes within an active observation.
3. Listener A calls an observed `KafkaTemplate` to send to Topic B.
4. Read Topic B and verify the new propagation headers.
5. Listener B extracts context and processes.
6. Collect spans from both listeners and both producer operations.
7. Verify trace contexts and parent/link relationships per version.
8. Verify outcomes remain correct when Listener A retries once.

If the second hop splits into a new trace, inspect which template is injected into Listener A and whether sending to Topic B actually executes within the listener observation scope. If sent asynchronously, check context propagation across the executor.

## 41. Integration test: DLT/replay

A recovery test should verify:

1. Incoming record carries valid `eventId`, `correlationId`, and tracing header.
2. Listener fails and the error handler retries up to its limit.
3. Record is recovered to the DLT.
4. DLT still holds `eventId` and source metadata needed for investigation.
5. Tracing headers are preserved or updated per the **chosen policy**.
6. Re-drive the record after fixing the data.
7. If a fresh trace starts, logs/audits still link via the original `eventId`.
8. If using span links, verify links are exported properly.
9. Under varying sampling, business outcomes and offsets remain unaffected.
10. If the DLT producer or tracing exporter fails, the system does not conflate the two failures.

Tracing must never block DLT publishing just because a tracing exporter is temporarily down. Isolate telemetry failures from Kafka delivery failures as strictly as possible.

## 42. Testing context loss in async execution

A targeted test:

1. Listener receives a record with `traceparent`.
2. Listener submits a task to an executor.
3. Task calls an HTTP client or observed `KafkaTemplate`.
4. Capture spans and logs on the worker thread.
5. With an uninstrumented executor, observe the risk of a new root span appearing.
6. Enable the appropriate context propagation / decorator.
7. Confirm trace linkage is preserved accurately.
8. Simultaneously verify the listener does not acknowledge the record before the task durably completes.

Step 8 is critical. A tracing test can pass while the system still loses data if Kafka offsets commit while the task sits in an in-memory queue.

## 43. Dashboards combining traces and metrics

A Kafka reliability monitoring dashboard should link:

| Metric group | Role |
|---|---|
| Producer send rate/latency/errors | How fast and reliably records are published |
| Consumer records consumed rate | Topic consumption speed |
| Listener processing duration | Business execution time |
| Consumer lag / record age | Wait time before processing |
| Retry/backoff/DLT counts | Error handling and recovery volume |
| Commit latency / commit failures | Durability of offset progress |
| Observation spans/traces | Cross-service execution path |
| Exporter dropped spans | Whether telemetry is being lost |
| JVM/CPU/network | Resource bottlenecks |
| Downstream DB/HTTP latency | Bottlenecks beyond the listener |

Trace viewers excel when investigating one specific event; metrics excel at spotting trends across millions of records. Never use span counts as a throughput metric unless instrumentation/sampling is strictly controlled, because sampling makes span counts differ from message counts.

A dashboard can link from structured logs carrying `traceId` to the tracing backend and from traces back to logs filtered by `eventId`. That gives a better workflow than cramming all business data into span attributes.

## 44. Runbook: broken trace link across a topic

When a producer → Kafka → listener flow suddenly splits traces:

1. **Identify the failing hop:** between which service and topic does the trace break?
2. **Confirm the record:** did the producer emit to the expected topic/key/`eventId`?
3. **Inspect tracing headers:** does the record have `traceparent`/B3 in the chosen format?
4. **Check producer config:** does the actual template have observation enabled?
5. **Check consumer config:** does the actual listener factory have observation enabled?
6. **Check tracer bridge:** do services have Micrometer Tracing and compatible tracers?
7. **Check propagator:** do W3C/B3 settings match across services?
8. **Check sampling/export:** were spans dropped or did the exporter fail?
9. **Check async hops:** was context lost across a thread switch?
10. **Check retry/DLT:** does the recoverer create/copy headers per policy?
11. **Check versions:** are Spring Kafka, Boot, Micrometer, and OpenTelemetry compatible?
12. **Check security:** are proxies or custom serializers stripping/altering headers?
13. **Run a small test:** publish one event with a known trace context.
14. **Monitor after fixing:** track the percentage of records with context and span linkage, not just raw trace counts.

Never modify production Kafka data simply because a trace split. First verify business delivery remains safe, then fix instrumentation separately.

## 45. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Enabling Observation only on producer | Consumer may start a fresh trace | Enable on listener factory |
| Enabling only on consumer | No incoming upstream context | Enable on sending `KafkaTemplate` |
| Missing tracer bridge/exporter | Observations exist yet no spans appear in backend | Check tracing pipeline |
| Producer W3C, consumer B3-only | Context cannot be extracted | Align propagators |
| Manually writing trace ID as text header | Missing span ID, flags, and semantic context | Use propagator |
| Using `traceId` as dedup key | Replays/new traces hide duplicates | Use `eventId` |
| Putting PII/tokens in baggage | Data leak, header bloat | Enforce safe baggage bounds |
| Sending on async thread without context propagation | Trace splits on next hop | Add context propagation |
| Acknowledging before async completion | Risk of losing work on crash | Ack after durable completion |
| Copying all tracing headers across DLTs forever | Confusing long traces, bloated headers | Clear retry/replay policy |
| Using one parent for a 200-record batch | Misleading trace relationships | Span links / per-record policy |
| Counting spans as message counts | Wrong due to sampling | Use Kafka/client metrics |
| Treating Kafka send span as transaction commit | False EOS conclusion | Track commits/aborts separately |
| Confusing listener latency with queue wait | Optimizing the wrong bottleneck | Measure event age/lag separately |
| Halting Kafka processing when exporter is down | Availability loss from telemetry | Decouple observability from processing |
| Attaching `eventId` as a metric tag | Cardinality explosion | Put in logs/traces per policy |
| Treating traces as permanent audits | Traces sample out and expire | Store durable audits/`eventId` separately |

## 46. Production rollout checklist

- Have producer and consumer agreed on a consistent propagation format?
- Does the actual `KafkaTemplate` in use enable observation?
- Does the actual listener container factory in use enable observation?
- Are `ObservationRegistry`, Micrometer Tracing bridge, and exporter working?
- Does sampling fit throughput and storage budgets?
- Do topics/records preserve tracing headers across intermediate hops?
- Can records without tracing context still process without data loss?
- Do logs include `traceId`/`spanId` within active scopes?
- Do async executors propagate context when needed?
- Does offset acknowledgment wait for durable completion of side effects?
- Are `eventId` and `correlationId` separated from `traceId`?
- Do retry/DLT/re-drive have clear policies for keeping or starting fresh context?
- Are baggage limits enforced and sensitive data kept out of headers?
- Is tracing sensibly designed for batch/fan-in if those patterns are used?
- Are queue age and consumer lag measured independently of traces?
- Have multi-hop, retry, DLT, async, and exporter outage scenarios been tested?
- Is there a runbook for diagnosing broken traces between topics and listeners?
- Are exporter drop rates and collector health monitored so missing traces are not mistaken for lost messages?

## 47. Conclusion

**Linking traces across topics and listeners** is the practice of propagating trace context through Kafka headers and restoring it in Spring Kafka listener observations. An observation-enabled `KafkaTemplate` creates/injects producer context; an observation-enabled listener container extracts context and instruments processing. Micrometer Tracing and an appropriate tracer/exporter turn those observations into distributed traces searchable in your backend.

Tracing tracks execution paths across topics and services, yet never replaces consumer lag, offset commits, Kafka transactions, retries, DLTs, or idempotency. In production, handle sampling, async context propagation, retry/replay semantics, header security, and the separation among `eventId`, `correlationId`, and `traceId` carefully.

A reliable Kafka system knows not only **where a record went**, but **why it slowed down, which attempt failed, where the bottleneck sits, and whether recovery completed safely**. Distributed tracing provides an essential piece of that picture when combined with metrics, logs, and durable business state.
