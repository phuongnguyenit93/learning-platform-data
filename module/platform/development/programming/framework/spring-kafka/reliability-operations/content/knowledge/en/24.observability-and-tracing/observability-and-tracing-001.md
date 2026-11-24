# observationEnabled

In Spring Kafka, a Kafka record can traverse multiple services, multiple topics, and retry attempts before reaching its final business state. When an incident occurs, inspecting only the logs of a single `@KafkaListener` is often not enough to answer: where the record originated, which service published it, which stage is slow, and whether the error happened in Kafka operations or in a downstream database/HTTP call. **Micrometer Observation** provides a unified instrumentation model for **metrics and distributed tracing**, helping connect the stages of a processing flow.

Spring Kafka's **`observationEnabled`** property enables Micrometer Observation for the **listener container** and/or **`KafkaTemplate`**. Once properly configured with an `ObservationRegistry`, a metrics registry, and an appropriate tracing bridge, the application can collect listener processing times, Kafka send durations, trace/span context, and tags that aid incident investigation.

It is important to understand the boundary: enabling `observationEnabled` **does not automatically create Kafka transactions, guarantee exactly-once delivery, fix serialization errors, route records to a DLT, or turn every HTTP/database call into a complete span**. It only activates the corresponding instrumentation path. To obtain cross-service traces, you still need a tracing implementation, exporter, sampling, header propagation, and instrumentation in the relevant components.

## 1. How Observation differs from logs, metrics, and traces

A simple pipeline:

~~~text
HTTP request
    |
    v
Order API
    |
    +-- KafkaTemplate.send("orders.created")
             |
             v
         Kafka topic
             |
             v
        @KafkaListener
             |
             +-- Database write
             +-- KafkaTemplate.send("billing.requested")
                            |
                            v
                      Billing consumer
~~~

Three types of signals answer three different questions:

| Signal | Primary question | Example |
|---|---|---|
| Log | What happened at a specific point in time? | `OrderCreated processing failed` |
| Metric | How are frequency, latency, and error rates trending? | Listener p95 = 180 ms |
| Trace/span | How are related operations within a flow connected? | HTTP → Kafka send → Kafka listener → DB |

Micrometer Observation provides the **Observation API**, an abstraction that lets handlers react together when an observation starts, stops, or encounters an error. There are handlers dedicated to creating Timer metrics, handlers dedicated to creating tracing spans, and custom handlers.

An application can enable Observation and only receive **metrics** if a tracing bridge/exporter has not been configured. Conversely, a trace backend might not show spans due to sampling, network, or collector configuration even when Observation is already active.

## 2. Primary effects of observationEnabled

Spring Kafka has supported Micrometer Observation for `KafkaTemplate` and listener containers since **Spring Kafka 3.0**.

The two configuration points are independent:

~~~java
// Listener container:
factory.getContainerProperties().setObservationEnabled(true);

// Kafka producer template:
kafkaTemplate.setObservationEnabled(true);
~~~

Meaning:

- **Listener container observation:** creates an observation around Kafka listener processing within the framework-supported scope; enables generating metrics and tracing spans for consumer-side work.
- **KafkaTemplate observation:** creates an observation when sending a record through the template; enables metrics/spans for producer-side sends.
- **When both are enabled:** trace context can be injected into record headers and continued on the downstream consumer if compatible tracing handlers/propagators are configured.

Enabling one side **does not automatically enable the other**. If the producer uses `KafkaTemplate` without Observation enabled, it may neither create a send span nor inject tracing headers via that instrumentation path. If the consumer does not have Observation enabled, it can read values normally but will not produce consumer-side spans via this mechanism.

## 3. Observation diagram in consume–process–produce

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant K1 as Kafka topic orders
    participant B as Service B
    participant K2 as Kafka topic billing
    participant C as Service C
    A->>A: KafkaTemplate Observation / producer span
    A->>K1: Produce record + trace context headers
    K1-->>B: ConsumerRecord + headers
    B->>B: Listener Observation / consumer span
    B->>B: Business processing
    B->>B: KafkaTemplate Observation / producer span
    B->>K2: Produce next record + context headers
    K2-->>C: ConsumerRecord + headers
    C->>C: Listener Observation / consumer span
~~~

If services use the same trace propagator and a shared trace backend, operators can correlate spans within the same trace. Whether spans represent parent-child relationships or messaging links depends on the implementation and semantic conventions; you should not force every system into a single tree diagram.

Kafka data flows remain **asynchronous** by nature. A trace shows relationships between operations, but does not prove that the producer committed every DB change, that offsets were acknowledged, or that the business event completed.

## 4. Default value of observationEnabled

In recent Spring Kafka versions, `ContainerProperties.observationEnabled` defaults to **`false`**. Therefore, merely having Spring Boot Actuator and Micrometer on the classpath is usually **not enough** to conclude that the listener container is using Observation.

~~~java
ContainerProperties properties = factory.getContainerProperties();

properties.setObservationEnabled(true);
~~~

For `KafkaTemplate`:

~~~java
template.setObservationEnabled(true);
~~~

Comparison table:

| Setting | Status / purpose |
|---|---|
| `observationEnabled=false` | Does not enable Micrometer Observation on that component |
| `observationEnabled=true` | Enables the Observation path for that component |
| `micrometerEnabled=true` | Enables legacy Micrometer Timers when used by the framework and a registry is present |
| `ObservationRegistry` | Registers and coordinates Observation handlers |
| Micrometer Tracing bridge | Translates Observations into spans according to the tracing implementation |
| Trace exporter | Sends spans to the collector/backend |
| MeterRegistry/Prometheus | Collects and exposes metrics |

**Enabling Observation replaces legacy Micrometer Timer instrumentation** for Observation-supported code paths, because Observation manages the corresponding Timer itself. This matters when migrating dashboards that rely on legacy tags.

For batch listeners, Observation behavior varies across versions and must be verified separately; do not infer it from record listeners.

## 5. Basic Spring Boot configuration

For example, with Spring Boot 3.x / Spring Kafka 3.x, you can add these dependencies:

~~~kotlin
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Metrics via Prometheus:
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    // Tracing with OpenTelemetry:
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Newer Spring Boot versions may provide **tracing starters** with different dependency coordinates and configuration properties. The example above illustrates the dependency architecture for Boot 3.x; in production deployments, use the versions managed by the Boot BOM rather than arbitrarily mixing Micrometer, OpenTelemetry, and Spring Kafka versions.

Partial metrics/tracing configuration for Boot 3.x:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-processing
  tracing:
    sampling:
      probability: 0.20
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

`sampling.probability: 0.20` is an illustrative configuration that samples a fraction of traces; it does not mean only 20% of Kafka records are processed, but rather affects whether spans are recorded/exported according to the tracer configuration. Metrics are typically recorded independently of trace sampling.

For Spring Boot 4.x, tracing dependencies and property namespaces have evolved; follow the documentation for the exact deployed version instead of blindly copying Boot 3.x configuration.

## 6. Enabling Observation for listener containers via Java configuration

A specifically configured listener factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaObservationConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    observedOrdersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);

        return factory;
    }
}
~~~

A listener using that exact factory:

~~~java
@Component
public class OrdersConsumer {

    private final OrderProjectionService projection;

    public OrdersConsumer(OrderProjectionService projection) {
        this.projection = projection;
    }

    @KafkaListener(
        id = "orders-observed-consumer",
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "observedOrdersListenerFactory")
    public void onOrder(OrderCreated event) {
        projection.apply(event);
    }
}
~~~

If `containerFactory` is omitted, Spring Kafka may select the default factory bean named `kafkaListenerContainerFactory`. When multiple listener factories exist, do not enable Observation on one factory and expect all listeners to be instrumented.

Container properties act as a template for created containers. Configuring them before listener containers start prevents a situation where the first few records go unobserved.

## 7. Enabling Observation for KafkaTemplate

An explicitly created and configured `KafkaTemplate`:

~~~java
@Bean
KafkaTemplate<String, BillingRequested> observedBillingTemplate(
        ProducerFactory<String, BillingRequested> producerFactory) {

    var template =
        new KafkaTemplate<String, BillingRequested>(producerFactory);

    template.setObservationEnabled(true);
    return template;
}
~~~

A service sending records:

~~~java
@Service
public class BillingPublisher {

    private final KafkaTemplate<String, BillingRequested> template;

    public BillingPublisher(
            KafkaTemplate<String, BillingRequested> observedBillingTemplate) {
        this.template = observedBillingTemplate;
    }

    public void publish(BillingRequested event) {
        template.send(
            "billing.requested",
            event.orderId(),
            event
        );
    }
}
~~~

When running in a Spring Boot application that already auto-configures a `KafkaTemplate`, check which template is being injected. Defining an extra template bean can make qualifier/primary bean resolution ambiguous. Another option is to customize the existing template during bean wiring, ensuring this is done **before it is used to send records**.

Observation applies only to sends routed through the `KafkaTemplate` with Observation enabled. If another module uses a raw `KafkaProducer` or a different uninstrumented `KafkaTemplate`, you cannot rely on this template's settings to observe those sends.

## 8. ObservationRegistry as the central coordinator

Micrometer Observation uses `ObservationRegistry` to register handlers and coordinate an observation's lifecycle. With Spring Boot Actuator properly configured, the registry is usually auto-configured.

Conceptual lifecycle:

~~~text
Observation started
        |
        +-- Meter observation handler starts timing
        |
        +-- Tracing handler creates span/context (if configured)
        |
        +-- Business operation
        |
        +-- Record error if any
        |
Observation stopped
        |
        +-- Timer sample is recorded
        +-- Span is finished and may be exported per sampling
~~~

If `ObservationRegistry` only has no-op behavior or lacks suitable handlers, `observationEnabled=true` may produce no useful data in your backend.

You can use the Observation API for custom business steps:

~~~java
@Service
public class OrderProjectionService {

    private final ObservationRegistry observationRegistry;
    private final OrderRepository repository;

    public OrderProjectionService(
            ObservationRegistry observationRegistry,
            OrderRepository repository) {

        this.observationRegistry = observationRegistry;
        this.repository = repository;
    }

    public void apply(OrderCreated event) {
        Observation
            .createNotStarted("business.order.persist", observationRegistry)
            .lowCardinalityKeyValue("operation", "upsert")
            .observe(() -> repository.apply(event));
    }
}
~~~

This instrumentation measures the persistence step separately. If it runs inside an active listener observation scope on the same thread, an appropriate trace handler can link the business span to the listener span. Do not stuff `eventId` or `orderId` into a **low-cardinality** metric tag.

## 9. Observation does not automatically mean the tracing exporter is working

Three operational levels are frequently confused:

| Level | Configuration | What is observed |
|---|---|---|
| Observation with registry/metrics handler only | Observation enabled, `MeterRegistry` present | Timer metrics |
| Observation with tracing bridge | Micrometer Tracing implementation and handler present | Spans/trace context can be created |
| Observation with exporter/backend | OTLP/Zipkin collector, network, and sampling configured | Spans appear in the tracing system |

Therefore, someone seeing `spring.kafka.listener` in Prometheus but no spans in Jaeger/Tempo should not immediately conclude that `observationEnabled` is broken. Metrics may be working while the tracing exporter is missing or misconfigured.

Conversely, low trace sampling can cause many operations to be absent from the tracing UI even though the application is processing every record normally.

## 10. Context propagation via Kafka headers

A cross-Kafka trace needs to link context between producer and consumer. For Kafka messaging, context propagation metadata is typically placed in **record headers**, not in the business JSON payload.

~~~text
Producer:
  Current trace context
       |
       v
  KafkaTemplate observation
       |
       +-- inject propagation headers
       |
       v
  ProducerRecord(topic, key, value, headers)

Kafka broker:
  Retains record and headers

Consumer:
  ConsumerRecord with headers
       |
       v
  Listener observation
       |
       +-- extract trace context
       |
       v
  Span/context for listener processing
~~~

Depending on the chosen tracing implementation and propagator, headers may use W3C Trace Context—for example `traceparent`—or another propagation standard. Do not hardcode header names when the framework already supports injecting/extracting via the tracing context.

The Kafka broker **does not create distributed traces itself** and does not interpret trace headers semantically. It simply stores and forwards headers alongside the record.

## 11. Trace context diagram across two services

Example:

~~~text
Service A
  HTTP request trace=abc
    |
    +-- KafkaTemplate sends OrderCreated
          -> trace context in record headers

orders.created topic
    |
    v
Service B
  @KafkaListener receives OrderCreated
    |
    +-- Listener observation links trace context
    |
    +-- DB call (if instrumented)
    |
    +-- KafkaTemplate sends BillingRequested
          -> propagation headers for the next hop

billing.requested topic
    |
    v
Service C
  @KafkaListener receives BillingRequested
~~~

With proper instrumentation and propagation, traces can visualize asynchronous communication across services. However:

- A producer may publish an event multiple times due to retries/recovery.
- A record may be processed independently by multiple consumer groups.
- A listener may roll back a Kafka transaction after a span has already been created.
- A "send attempted" span does not prove the output was committed in a Kafka transaction.
- A trace is not a source of truth for accounting, idempotency, or consumer offset audits.

Traces are meant to **explain behavior**; state correctness still depends on database transactions, Kafka delivery semantics, and application invariants.

## 12. Why enable Observation on both producer and consumer?

Suppose Service A enables `KafkaTemplate.observationEnabled`, while Service B has not enabled listener observation:

~~~text
Service A:
  Kafka send span + headers   -> OK

Service B:
  Consumer still deserializes and processes records
  but has no listener observation span along this path
~~~

Conversely, if Service B enables listener observation while the producer does not attach trace headers, B can still generate a local observation/span. However, upstream context may not be automatically linked into the same trace.

Therefore, for a pipeline requiring distributed tracing, you should:

1. Enable Observation on `KafkaTemplate` in producers sending records.
2. Enable Observation on listener containers in consumers.
3. Configure compatible tracing/propagation conventions across services.
4. Ensure Kafka headers are forwarded intact across brokers/proxies.
5. Verify with a real record flowing from producer to consumer and inspect spans in the backend.
6. For retries/DLT, decide whether to preserve the existing trace context or start a new one.
7. Verify sampling and exporters across all involved services.

You do not need to enable tracing for services outside the flow; just understand that an uninstrumented hop can create a gap in the trace.

## 13. Default observation names

Spring Kafka defines these observation names:

| Component | Observation name | Primary metric/span |
|---|---|---|
| Listener | `spring.kafka.listener` | Timer + listener span |
| KafkaTemplate | `spring.kafka.template` | Timer + template/send span |

In addition to Timers, Micrometer Observation documentation describes long task timers such as:

~~~text
spring.kafka.listener.active
spring.kafka.template.active
~~~

A traditional `Timer` primarily records duration when an invocation finishes. A long task timer helps observe in-flight tasks depending on the registry and instrumentation. Do not treat a long task timer as consumer lag or open Kafka transaction count; it is a metric belonging to the Observation lifecycle.

When exported to Prometheus, metric names may convert dots to underscores and append a unit suffix. Inspect the actual endpoint rather than assuming exact time-series names.

## 14. Low-cardinality and high-cardinality tags

Micrometer distinguishes information suitable for metrics from information that should only live in traces/logs.

**Low-cardinality key values** have a relatively small, bounded set of values. They are suitable as Prometheus dimensions.

**High-cardinality key values** have very large value sets—such as offsets, request IDs, or business event IDs; turning them into metric labels causes time-series explosion.

| Tag/attribute | Recommended type | Why |
|---|---|---|
| `spring.kafka.listener.id` | Low cardinality | Finite set of listener IDs |
| `messaging.system=kafka` | Low cardinality | Stable value |
| `messaging.source.name` | Low cardinality if topics are managed | Finite set of topics |
| Consumer group | Low cardinality if controlled | Group count is typically bounded |
| `event.kind=order_paid` | Low cardinality if whitelisted | Finite set of event types |
| `messaging.kafka.message.offset` | High cardinality | Changes on every record |
| Event ID/UUID | High cardinality | Nearly unique per event |
| Kafka key/order ID | High cardinality | Grows with business volume |
| Trace ID/span ID | High cardinality | Unique per trace/span |
| Raw exception message | Should not be a metric label | Unbounded free-form text, potentially sensitive |

Do not put Kafka payloads, access tokens, emails, payment data, or customer IDs into low-cardinality tags. Tracing data must also comply with access controls and data retention policies, as span attributes can contain sensitive information if added by the application.

## 15. Default tags and metadata of listener observation

According to Spring Kafka's Micrometer Observation documentation, listener observation includes several low-cardinality keys:

| Low-cardinality key | Meaning |
|---|---|
| `spring.kafka.listener.id` | Listener ID / container bean name |
| `messaging.system` | Messaging system, typically Kafka |
| `messaging.operation` | Messaging operation type |
| `messaging.source.name` | Source topic |
| `messaging.source.kind` | Source kind |
| `messaging.kafka.consumer.group` | Consumer group |

Span attributes may additionally include:

- `messaging.kafka.client_id`.
- `messaging.kafka.message.offset`.
- `messaging.kafka.source.partition`.
- `messaging.consumer.id`.

The exact list and names may evolve as Spring Kafka/Micrometer updates semantic conventions. For production dashboards, verify the actual tag keys in `/actuator/prometheus` and your trace backend against the **running version** rather than copying directly from another version's documentation.

Do not confuse low-cardinality observation tags with legacy timer tags `name`, `result`, and `exception`; the two mechanisms follow different conventions.

## 16. Legacy Micrometer Timer and Observation are not identical

Before Observation, Spring Kafka listeners created Micrometer Timers directly when Micrometer and a `MeterRegistry` were present. The `spring.kafka.listener` Timer typically had:

~~~text
name=<container name>
result=success|failure
exception=none|ListenerExecutionFailedException
~~~

When `observationEnabled=true`, Spring Kafka switches instrumentation to Micrometer Observation for supported paths. Even though the Timer may still be named `spring.kafka.listener`, **its tags may differ**.

| Aspect | Legacy Micrometer Timers | Micrometer Observation |
|---|---|---|
| Enablement | `micrometerEnabled` | `observationEnabled` |
| Instrument | Direct Timer | Observation, producing Timers and optionally spans |
| Listener identifier | `name` | `spring.kafka.listener.id` per convention |
| Failure dimension | `result` and `exception` | `error` / other convention depending on version |
| Tag customization | `micrometerTags` / `micrometerTagsProvider` | `KafkaListenerObservationConvention` |
| Trace spans | Not generated by Timer alone | Can generate spans when tracing handlers are ready |
| Batch behavior | Measures batch invocation per legacy behavior | Depends on version and batch observation policy |

If dashboards query:

~~~promql
spring_kafka_listener_seconds_count{result="failure"}
~~~

after enabling Observation when the `result` tag is no longer emitted in the legacy format, panels may go blank. This is a **dashboard/tag convention migration**, not necessarily broken metrics.

Your upgrade plan must include updating PromQL queries, Grafana panels, alert rules, and any business metric aggregations that depend on tag names.

## 17. Custom listener ObservationConvention

To add tags for per-pipeline analysis, use `KafkaListenerObservationConvention` instead of the legacy Timer's `micrometerTagsProvider`.

An example in Spring Kafka 3.x/4.x supporting the relevant API:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.kafka.support.micrometer.KafkaListenerObservation;
import org.springframework.kafka.support.micrometer.KafkaRecordReceiverContext;

public class OrderListenerObservationConvention
        extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("pipeline", "order-projection"));
    }
}
~~~

Attach it to the listener factory:

~~~java
factory.getContainerProperties()
       .setObservationConvention(new OrderListenerObservationConvention());
factory.getContainerProperties().setObservationEnabled(true);
~~~

The example above adds a fixed `pipeline` tag with small cardinality. Subclassing the default convention is beneficial because it retains the standard tags provided by Spring Kafka and appends only the required business field.

Depending on the version, `getLowCardinalityKeyValues` may have different nullability annotations. Rely on the API of your pinned dependency when compiling.

## 18. Safe dynamic tags from ConsumerRecord

Starting from Spring Kafka 3.0.6, observation contexts hold a reference to the Kafka record, allowing tags derived from key/header/value.

However, do **not** put arbitrary Kafka headers or business IDs into metric tags. A safe approach is to whitelist event types:

~~~java
public class OrderListenerObservationConvention
        extends KafkaListenerObservation.DefaultKafkaListenerObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordReceiverContext context) {

        var record = context.getRecord();

        var header = record.headers().lastHeader("event-type");

        String kind = "other";
        if (header != null && header.value() != null) {
            String raw = new String(
                header.value(),
                StandardCharsets.UTF_8
            );

            kind = switch (raw) {
                case "OrderCreated" -> "order_created";
                case "OrderPaid" -> "order_paid";
                case "OrderCancelled" -> "order_cancelled";
                default -> "other";
            };
        }

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("event.kind", kind));
    }
}
~~~

The code uses a Java switch expression and `StandardCharsets.UTF_8`; import the corresponding classes. If the application targets an older Java version without switch expressions, replace it with `if/else` or an enum mapping.

Why whitelisting is necessary:

- A buggy producer could emit millions of unknown event type values.
- Using raw event types as tags creates a new time series for every distinct value.
- A small tag set keeps dashboards and alerts stable.
- High-cardinality fields can still appear in logs or span attributes if permitted by security policy.

If multiple topics have different contracts, use separate conventions per factory or branch by source topic, avoiding applying an arbitrary classifier across every consumer.

## 19. Custom KafkaTemplateObservationConvention

The producer path has its own `KafkaTemplateObservationConvention` interface and corresponding default implementation.

An example:

~~~java
public class BillingTemplateObservationConvention
        extends KafkaTemplateObservation.DefaultKafkaTemplateObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            KafkaRecordSenderContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("pipeline", "billing"));
    }
}
~~~

Attach it to an Observation-enabled `KafkaTemplate`:

~~~java
template.setObservationConvention(
    new BillingTemplateObservationConvention()
);
template.setObservationEnabled(true);
~~~

The corresponding imports live in package:

~~~java
org.springframework.kafka.support.micrometer.KafkaTemplateObservation
org.springframework.kafka.support.micrometer.KafkaRecordSenderContext
~~~

On the producer side, the observation context contains `ProducerRecord`. If you want to add message type metadata, whitelist headers/metadata just like on the consumer. Do not put raw keys, UUIDs, customer IDs, or payment references into low-cardinality keys.

## 20. Batch listeners are an exception requiring version-specific checks

**Do not assume `observationEnabled=true` has identical semantics on record listeners and batch listeners.**

Spring Kafka 3.1 documentation states that batch listeners are not supported by Observation in the same way as record listeners, so legacy Micrometer Timers are used instead. In Spring Kafka 4.1.x, documentation notes that when a batch listener enables `observationEnabled`, **per-record observations are not created by default**; you can enable `recordObservationsInBatch=true` to create per-record observations, though those observations **do not automatically propagate into the batch listener method**.

In the in-development 4.2 branch documentation, new behavior introduces a default batch-level observation when `recordObservationsInBatch=false`. Therefore, you must verify the **exact release** you are deploying.

Orientation table:

| Version / track | Key note |
|---|---|
| Spring Kafka 3.0–3.1 | Batch Observation is limited; check Timer fallback |
| Spring Kafka 4.1.x | Supports `recordObservationsInBatch`; does not create per-record observations by default |
| Spring Kafka 4.2 development | Describes default batch-level observation; verify stable release before adopting |
| Record listener | Observation wraps each listener invocation via the framework mechanism |

Do not write a tracing policy around `recordObservationsInBatch` without verifying compatibility and span context inside the batch method.

## 21. Configuring recordObservationsInBatch

On a supported Spring Kafka version:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
observedBatchFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);

    factory.getContainerProperties().setObservationEnabled(true);
    factory.getContainerProperties()
           .setRecordObservationsInBatch(true);

    return factory;
}
~~~

When per-record batch observations are enabled, the framework may create an observation for each record in the batch, but in some versions those observations **are not set as the current scope** when invoking the shared batch listener method. Consequently, HTTP/DB calls inside the batch method do not automatically become children of one of the many per-record spans.

If you need per-record tracing with business steps inside a batch, the application must design manual observation scopes or switch to a record listener if the semantics fit. Do not arbitrarily create a single current span for the entire batch and attach all records to it if accurate attribution is required.

## 22. Observation and Kafka client metrics are two distinct groups

Listener observation primarily measures **application invocations**, whereas Kafka client metrics measure `KafkaConsumer`/`KafkaProducer` behavior.

| Category | Example | Question |
|---|---|---|
| Listener Observation Timer | `spring.kafka.listener` | Is the listener processing slowly? |
| KafkaTemplate Observation Timer | `spring.kafka.template` | Is sending records via the template slow? |
| Kafka client fetch metrics | Fetch latency/rate | Is the consumer fetching data slowly from brokers? |
| Kafka coordinator metrics | Commit/rebalance/heartbeat | Is the group stable? |
| Consumer lag | Committed offset vs. log-end | How large is the backlog? |
| Retry/DLT metrics | Retry count, DLT volume | Are there unprocessable records? |
| Business event metrics | Orders applied, payments confirmed | Did the business operation actually complete? |

A listener taking 10 ms to process while consumer lag climbs may be caused by insufficient concurrency, hot partitions, pauses, or an excessive producer rate. Observation Timers do not measure all of those conditions on their own.

Spring Kafka provides `MicrometerConsumerListener` and `MicrometerProducerListener` to bind Kafka client metrics to a Micrometer `MeterRegistry`. They complement rather than replace `observationEnabled`.

## 23. When do traces break between Kafka producer and consumer?

A trace flowing from Service A to B can lose its link if:

1. The producer `KafkaTemplate` does not have Observation enabled.
2. The consumer listener container does not have Observation enabled.
3. There is no tracing bridge or tracing handlers registered in `ObservationRegistry`.
4. Producer and consumer use incompatible propagation formats.
5. A custom Kafka interceptor/forwarder accidentally strips trace headers.
6. A record is republished by a producer without preserving/carrying context.
7. An async thread boundary drops the observation scope.
8. Sampling or exporter settings prevent some spans from appearing in the backend.
9. A component uses the Kafka client directly instead of going through an instrumented template/container.
10. The retry/DLT mechanism creates new records without a defined tracing policy.

Before adding custom headers manually, check whether Spring Kafka and Micrometer Tracing are already injecting/extracting context properly. Manually inserting a malformed `traceparent` can break propagation or produce an invalid parent context.

## 24. Async thread boundaries and Observation scope

Micrometer Observation scopes are normally bound to the **current thread**. If a listener offloads work to an executor:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "observedOrdersListenerFactory")
public void onOrder(OrderCreated event) {

    CompletableFuture.runAsync(() -> {
        orderProjectionService.apply(event);
    });

    // Listener returns before the actual task completes.
}
~~~

Work inside `runAsync` can lose the current observation/tracing context if the executor is not instrumented or lacks proper context propagation. At the same time, the Kafka container may treat the listener as succeeded even though the DB task has not finished—a semantic bug far more serious than a missing span.

If async execution is needed:

- Ensure the listener does not report success before mandatory side effects complete.
- Use an executor instrumented with Micrometer Context Propagation or the framework's tracing mechanism for your version.
- Consider `ContextSnapshot`/`ContextExecutorService` or a task decorator when supported.
- Never pass a raw Kafka `Consumer` across threads.
- Clearly define which span owns the business logic, timeouts, failures, and retries.

Observation can expose gaps in instrumentation, but it does not automatically propagate transaction context or solve thread safety.

## 25. Trace propagation with HTTP clients

A listener may call a downstream HTTP API:

~~~text
Kafka listener observation
      |
      v
OrderValidationService
      |
      v
RestClient / WebClient / RestTemplate
      |
      v
Validation API
~~~

For the HTTP call to continue the trace context, the client also needs appropriate instrumentation and propagation. With Spring Boot, use **auto-configured builders** or framework-supported mechanisms; instantiating an HTTP client directly and bypassing configuration can prevent trace headers from being injected.

Do not assume that `observationEnabled=true` on a Kafka listener automatically instruments every JDBC driver, HTTP client, or third-party SDK. Each integration has its own Observation/Tracing capabilities and configuration.

## 26. Retry, DLT, and trace lineage

A record may pass through a chain:

~~~text
orders.created
    |
    +-- listener failure
          |
          v
orders-retry-1000
    |
    +-- failure
          |
          v
orders-retry-2000
    |
    +-- terminal
          |
          v
orders.DLT
~~~

Each time a consumer receives a record, it can create a new observation/span. You should not merge every attempt into a single span lasting minutes or days; asynchronous boundaries and retry delays are usually represented as separate spans linked via trace/context or a business correlation ID according to policy.

Things to decide:

- Does the retry producer have Observation enabled?
- Does the retry topic consumer have Observation enabled?
- When forwarding records, which trace headers are preserved/forwarded?
- Is DLT publishing instrumented, and does it track success/failure?
- Should a manual replay days later continue the old trace or start a new trace while retaining `eventId`/`replayId` for correlation?
- Does DLT event metadata retain original topic/partition/offset details?

**Trace ID is not an idempotency key.** A business event may be processed under multiple different traces via replays; conversely, a single trace may contain multiple business events. Use a durable `eventId` or operation ID for business deduplication.

## 27. Kafka transactions and observationEnabled

A Kafka transaction can include Kafka output records and input offsets in the same transaction when the container is properly configured. `observationEnabled` does not alter transaction boundaries.

Example:

~~~text
Consumer record
     |
     v
Listener observation starts
     |
     v
Kafka transaction begins/participates per container configuration
     |
     v
Listener sends output via observed KafkaTemplate
     |
     v
Listener returns success
     |
     v
Container attempts commit transaction + offsets
~~~

Observation caveats:

- A successful listener span may only reflect that the listener method returned, not that **the entire transaction committed**.
- A successful `KafkaTemplate` send span does not necessarily prove the record is visible to downstream `read_committed` consumers if the transaction has not committed yet.
- If the transaction rolls back, the record may be reprocessed and generate additional spans.
- Database side effects do not automatically roll back with a Kafka transaction.
- If output is sent via a non-transactional template, Observation can still create spans, but delivery semantics differ.

To monitor commits/rollbacks, add Kafka transaction metrics, logs, error events, and business state indicators; do not rely solely on the `spring.kafka.listener` Timer.

## 28. KafkaAdmin clusterId and remoteServiceName

Spring Kafka observation contexts can set `remoteServiceName` based on the Kafka cluster ID. To retrieve the ID, the framework uses `KafkaAdmin` and the `describeCluster` operation when needed.

If `KafkaAdmin` lacks permissions or the network blocks admin calls, fetching the cluster ID can fail or cause delays if the application retries repeatedly. Documentation from Spring Kafka 3.1 allows configuring a **manual clusterId** in appropriate scenarios; Spring Kafka 4.1.1 adds failure caching and retries after `clusterIdRetryInterval` (default 5 minutes) to reduce overhead when `describeCluster` fails.

In operations:

1. Check whether the service has permission to execute `describeCluster`.
2. Review `KafkaAdmin` operation timeouts and network paths.
3. If the cluster ID cannot be read, evaluate supplying a stable value according to your version.
4. Avoid configuring a dummy cluster ID that does not match the actual cluster.
5. If Observation increases send/receive latency after deployment, check logs for cluster ID lookup failures.

Do not confuse `clusterId` with bootstrap server hostnames or consumer group IDs: they represent distinct concepts.

## 29. Sampling and distributed tracing overhead

If an application processes 20,000 Kafka messages/second and creates spans for both producer and consumer at each hop, 100% tracing can impose heavy CPU, memory, exporter network, and trace backend costs.

Sampling is the cost-control mechanism:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

This example samples 10% according to the appropriate Spring Boot tracer/sampler policy; it does not mean every trace gets exactly one-tenth of its spans randomly dropped within the same trace.

Considerations:

- Metrics should remain representative of all invocations rather than being tied to trace sampling.
- Low trace sampling means some requests will not appear in the backend; do not treat this as record loss.
- When investigating rare incidents, you may need advanced sampling policies or log correlation.
- Do not enable 100% tracing across all of production indefinitely just to hunt down one bug if the overhead is unsustainable.
- Do not log raw payloads/keys as span attributes to avoid PII exposure and storage bloat.

If you need to investigate a specific event, an event ID in structured logs combined with the trace ID can aid correlation without turning event IDs into metric labels.

## 30. Metrics exported to Prometheus

Observation generates metrics via observation handlers and `MeterRegistry` when fully configured. Example metric names that may be exported look like:

~~~text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_template_seconds_count
spring_kafka_template_seconds_sum
~~~

Actual time-series names and tags depend on Spring Kafka, Micrometer, Prometheus registry versions, and the Observation convention. To inspect metrics via Actuator:

~~~text
GET /actuator/metrics
GET /actuator/metrics/spring.kafka.listener
GET /actuator/prometheus
~~~

These endpoints only work when Actuator, the registry, and appropriate exposure/security settings are configured.

Do not hardcode PromQL filters using legacy `result`/`exception` after migrating to Observation conventions; inspect the actual scraped data and use available keys such as `spring.kafka.listener.id`, `messaging.source.name`, and `error` if emitted by your backend.

## 31. Querying latency from Observation Timer

Example computing average listener duration over 5 minutes:

~~~promql
sum by (spring_kafka_listener_id) (
  rate(spring_kafka_listener_seconds_sum[5m])
)
/
clamp_min(
  sum by (spring_kafka_listener_id) (
    rate(spring_kafka_listener_seconds_count[5m])
  ),
  0.000000001
)
~~~

Note: the Prometheus exporter may normalize dots in tag keys into underscores. `spring_kafka_listener_id` here is only a **common normalized label name**; verify the actual output.

For p95/p99, histogram buckets must be enabled:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, spring_kafka_listener_id) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
~~~

If histograms are not enabled, `_bucket` may not exist; do not create alerts referencing nonexistent metrics. Choose histogram boundaries and retention based on SLOs.

The Observation Timer measures framework-instrumented execution time, **not how long a record sat in the broker**, retry delays, or total time from producer publish to business completion.

## 32. Consumer lag and tracing must be combined

A pipeline can exhibit very short listener spans while accumulating large consumer lag:

~~~text
Producer ingress = 5,000 records/s
Consumer throughput = 3,000 records/s
Listener p95 = 20 ms

=> Lag grows by roughly 2,000 records/s even though each invocation looks fast.
~~~

Causes may include partition count limiting concurrency, hot keys, poll/fetch latency, downstream queues, pauses, or consumer group rebalances. Observation does not replace:

- Consumer group lag metrics.
- Kafka client fetch/poll metrics.
- `NonResponsiveConsumerEvent` and idle events.
- Retry topic backlog and DLT volume.
- Business success/failure counters.
- Database/HTTP dependency metrics.

Traces are useful for seeing *where a specific execution slowed down*, while metrics answer *how many executions are slowing down and how widespread the impact is*.

## 33. Log correlation with traceId and spanId

When Micrometer Tracing is configured with logging integration, MDC can hold `traceId` and `spanId` so structured logs correlate with spans. Example log:

~~~text
2026-11-15T10:00:00Z INFO traceId=4f5a... spanId=a7c2...
  listener=orders-observed-consumer
  eventId=evt-205
  result=ORDER_APPLIED
~~~

Trace IDs help investigate operations within a flow. Event IDs identify the business operation even when a retry hours later starts a new trace.

Notes:

- MDC is not guaranteed to propagate automatically to every async executor thread.
- Do not rely on trace IDs to deduplicate DB writes.
- Do not log tokens, PII, or raw message payloads simply because tracing is enabled.
- If trace sampling drops a span, log correlation behavior may vary by implementation; verify in your actual environment.
- An event going through DLT replay may need an extra `replayId` to distinguish processing attempts.

## 34. Verifying propagation with a sample flow

A verification plan in a test environment:

1. Enable Observation for `KafkaTemplate` in Service A.
2. Enable Observation for the listener container in Service B.
3. Configure the Micrometer Tracing bridge and exporter in both services.
4. Share the same propagation format and inspect headers.
5. Send a record with a known event ID from A.
6. Confirm B receives and successfully processes the record.
7. Locate send/receive spans in the trace backend.
8. Inspect trace IDs, parent/links, and topic metadata.
9. Verify that listener exceptions produce error telemetry per convention.
10. Verify record retry/republish and trace context against the intended policy.
11. Test async processing to determine whether context is preserved.
12. Verify metrics still collect samples even when trace sampling is configured low.

This is a **verification plan** for practitioners to apply, not test results from this article. Each application must clearly define which component is responsible for propagation.

## 35. Runbook: observationEnabled is on but no metrics appear

1. Verify the container factory actually calls `setObservationEnabled(true)`.
2. Check which `KafkaTemplate` is sending and whether Observation is enabled on it.
3. Confirm `ObservationRegistry` is present in the application context.
4. Confirm metrics handlers and `MeterRegistry`/Prometheus registry are configured.
5. Check Actuator endpoint exposure and access permissions.
6. Confirm the listener actually has invocations; an empty topic produces no samples.
7. Check whether a `MeterFilter` is blocking or renaming meters.
8. Search metrics by `spring.kafka.listener`/`spring.kafka.template`, not only legacy tags.
9. Check whether the container is record or batch mode and verify your version's batch observation policy.
10. Check for multiple registries, child containers, or factories.
11. Inspect startup logs and Micrometer/Kafka dependency versions.
12. After fixing, inspect the concrete time series before modifying alert rules.

If metrics do not appear, do not immediately create a custom Timer with the same name; that can cause duplicate instrumentation once the configuration issue is fixed.

## 36. Runbook: Metrics exist but no traces appear

1. Confirm a Micrometer Tracing bridge is included in dependencies.
2. Confirm a tracing handler/implementation is wired into `ObservationRegistry`.
3. Check sampling probability and sampler policy.
4. Check exporter, collector endpoint, TLS/auth, and network connectivity.
5. Check trace backend ingest and logs.
6. Confirm both producer and consumer have Observation enabled.
7. Verify records carry trace context headers in the expected format.
8. Check whether custom Kafka interceptors strip headers.
9. Check async thread context propagation.
10. Check batch listener limitations for your Spring Kafka version.
11. Check application logs for `traceId`/`spanId`.
12. Test with a sample record under appropriate sampling in a test environment.

Do not turn on 100% tracing across all of production as a knee-jerk reaction. Pick a safe environment or sampling window to isolate the issue.

## 37. Runbook: Trace has disconnected spans or wrong parent

Scenario: Service A has a producer span and Service B has a consumer span, but they are not in the same trace.

Investigation paths:

- Do tracing propagators in A and B use the same W3C/B3/format?
- Does A's `KafkaTemplate` have `observationEnabled` and send via that exact template?
- Does B's listener have `observationEnabled` on the right factory?
- Are record headers being stripped by a custom forwarder/serializer/interceptor?
- Is B manually creating a root observation instead of adopting the extracted context?
- Does retry/DLT create a new producer record without forwarding headers?
- Is an async executor losing the current observation scope?
- Is sampling/exporting causing part of the spans not to appear?
- Are two different collectors/backends being used in the same environment?

Once the cause is found, decide on the desired trace structure: a messaging chain does not necessarily have to look like a synchronous HTTP parent-child tree. Span links or trace correlation may be more appropriate in fan-out workflows.

## 38. Runbook: Metrics/trace overhead increases after enabling Observation

1. Compare CPU, memory, GC, and container processing duration before/after deploy.
2. Check spans/second and exporter queue capacity.
3. Review sampling strategy and number of instrumented services.
4. Check whether low-cardinality tag values accidentally contain event IDs or Kafka keys.
5. Inspect histogram buckets and total number of time series.
6. Check for tracing backend ingest throttling or OTLP exporter retries.
7. Check `KafkaAdmin` `describeCluster` failures, timeouts, and cluster ID lookup behavior.
8. Check whether custom observation conventions parse heavy JSON payloads per record.
9. Check whether logging/alerting inside observation handlers performs synchronous blocking I/O.
10. Reduce cost with tag whitelisting, sampling, and appropriate exporter batching.
11. Do not sacrifice critical error observability just to shave off a minor cost.
12. Monitor throughput, consumer lag, and error rates after every change.

Observation must support reliability—not turn the consumer itself into a bottleneck due to tag cardinality or a slow collector.

## 39. Security, privacy, and trace data

Kafka headers and span attributes can contain extensive system information. Tracing replicates part of that metadata to a storage backend outside Kafka, so controls are needed:

- Use only approved low-cardinality tags.
- Avoid customer IDs, emails, tokens, and payment data in metric tags.
- Never attach raw event payloads to spans.
- If event IDs are needed as high-cardinality attributes, evaluate retention and access permissions.
- Secure `/actuator/prometheus` and tracing collector endpoints.
- Check how long the trace backend retains data and who has access to view it.
- Never use `traceparent` as a credential or authentication token.
- Do not assume all headers from upstream are trustworthy; tracing context is observability metadata, not proof of identity.

A trace ID aids correlation but does not prove user authorization. Security checks must remain independent.

## 40. Implementation checklist for observationEnabled

- [ ] Verified Spring Kafka version supports Micrometer Observation (3.0+).
- [ ] Enabled `ContainerProperties.observationEnabled=true` on the right listener factory.
- [ ] Enabled `KafkaTemplate.observationEnabled=true` on producers requiring trace propagation.
- [ ] `ObservationRegistry` and metrics handlers are active.
- [ ] `MeterRegistry`/Prometheus configured if metrics are needed.
- [ ] Micrometer Tracing bridge and exporter configured if distributed spans are needed.
- [ ] Both producer and consumer use a compatible propagation format.
- [ ] Verified trace headers are not stripped during forwarding/retry/DLT.
- [ ] Distinguished legacy Timer tags from Observation convention tags.
- [ ] Checked batch listener semantics for the specific Spring Kafka version.
- [ ] Implemented custom `KafkaListenerObservationConvention`/`KafkaTemplateObservationConvention` where additional tags are needed.
- [ ] Low-cardinality tags are whitelisted; event IDs/offsets are never used as metric labels.
- [ ] Sampling strategy and exporter/backend budget defined.
- [ ] Context propagation across async threads addressed where required.
- [ ] Dashboards combine listener timers with consumer lag, Kafka client metrics, retries, and DLT.
- [ ] Spans are not treated as proof of Kafka transaction/DB commit success.
- [ ] Runbooks exist for missing metrics, missing spans, broken context, and increased overhead.
- [ ] Security, retention, and access policies established for trace data.

## 41. References

- [Spring Kafka Reference — Monitoring & Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka Reference — Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka Reference — Micrometer Observation conventions](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)
- [Spring Kafka API — DefaultKafkaListenerObservationConvention](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/micrometer/KafkaListenerObservation.DefaultKafkaListenerObservationConvention.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Reference — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)

**Conclusion:** `observationEnabled` brings Spring Kafka listeners and `KafkaTemplate` into Micrometer Observation to collect **metrics and tracing** under a unified model. Enable both producer and consumer paths appropriately, configure `ObservationRegistry` alongside your tracing exporter, and manage trace context propagation via Kafka headers. When migrating from legacy Micrometer Timers, audit metric tags and dashboards; when using batch listeners, track version-specific differences closely. For reliability, Observation is an **observability and diagnostics** layer—it does not replace offset management, retries, Kafka transactions, idempotency, or business-state validation.
