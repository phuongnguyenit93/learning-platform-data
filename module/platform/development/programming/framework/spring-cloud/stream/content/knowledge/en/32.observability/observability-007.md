# Micrometer Observation and Function Instrumentation

A function in Spring Cloud Stream may receive a message, call a business service, query a database, and emit an event to another broker. When a function slows down or fails, checking logs from a single instance is rarely enough to tell which step slowed the message down, where the error originated, and whether downstream consumers received the event.

Micrometer Observation provides a unified model for recording an operation in progress. An Observation can produce metrics and traces through `ObservationHandler` instances registered in the application. Spring Cloud Stream integrates observation at the Spring Cloud Function layer: imperative functions are wrapped by the framework to observe each invocation. With reactive functions, the application must explicitly choose which stream segment to observe because the function is only invoked once when assembling the pipeline.

This lesson guides you through enabling observation for functions, creating child observations for business steps, observing reactive functions, propagating trace context across messages, collecting metrics and binder health, and building dashboards for event-driven applications.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish logs, metrics, traces, and the role of Micrometer Observation.
- Explain ObservationRegistry, Observation, ObservationHandler, and ObservationConvention.
- Enable observability for imperative functions in Spring Cloud Stream.
- Manually create an observation for a business step using ObservationRegistry.
- Set low-cardinality and high-cardinality key-values properly.
- Observe reactive functions with Reactor tap and Micrometer.observation.
- Configure context propagation across threads and reactive pipelines.
- Export metrics via Actuator/Prometheus and traces via Micrometer Tracing/OTLP.
- Monitor Kafka consumer lag, Kafka Streams metrics, and binder health.
- Design dashboards, alerts, and runbooks for event flows.

## 1. Three pillars of system observability

Observability is commonly built from three signal types:

| Signal | Key question | Examples in Spring Cloud Stream |
|---|---|---|
| Logs | What happened? | Function received event, deserialization error, retry, publish failure |
| Metrics | How often does it happen and how long does it take? | Message rate, processing duration, error count, consumer lag |
| Traces | Which components did a single message traverse? | Producer → broker → consumer function → database → output topic |

The three signals complement each other. Metrics show that p95 processing time is rising, traces locate the slow span within an execution, and logs provide the exception and diagnostic details at that exact moment.

Micrometer Observation is the common API layer for describing an operation. When ObservationRegistry has the appropriate handlers, a single observation can create timers/counters and spans. The application does not need to write separate timing logic for each metrics and tracing system.

~~~mermaid
flowchart TD
    A["Spring Cloud Stream function invocation"] --> B["Micrometer Observation"]
    B --> C["ObservationRegistry"]
    C --> D["ObservationHandler"]
    D --> E["Metrics: timer, counter"]
    D --> F["Tracing: span, parent-child"]
    A --> G["Structured logs"]
    E --> H["Prometheus / metrics backend"]
    F --> I["OTel Collector / tracing backend"]
    G --> J["Log platform"]
~~~

An observation only records the operation. Exporting data to backends requires the corresponding registry, handler, exporter, and configuration. If the application lacks a handler or tracer bridge, part of the signals may not be exported even though code creates observations.

## 2. ObservationRegistry and the Observation lifecycle

Key components:

- ObservationRegistry: central registry used by instrumentation to create observations.
- Observation: an operation to be tracked, carrying a name, context, and key-values.
- ObservationHandler: receives start, error, event, and stop callbacks to produce metrics or traces.
- ObservationConvention: defines default observation names and metadata.
- ObservationPredicate: decides which observations are recorded.
- ObservationFilter: adjusts context or metadata before handlers process it.

Typical lifecycle:

1. Create an observation with a name describing the operation.
2. Attach key-values with appropriate cardinality.
3. Start the observation and place it in the current scope.
4. Perform the work.
5. Record any exception if thrown.
6. Stop the observation so handlers finalize timers/spans.

The `observe(...)` API manages start, scope, error, and stop automatically:

~~~java
Observation.createNotStarted("orders.validation", observationRegistry)
    .lowCardinalityKeyValue("operation", "validate")
    .observe(() -> validate(order));
~~~

If `validate(...)` throws an exception, Observation records the error and closes before the exception propagates. This ensures duration metrics and traces capture failed executions as well.

Spring Boot auto-configures ObservationRegistry when Actuator and the appropriate dependencies are present. You can inject the registry into services or functions to create business observations.

## 3. Enabling observability for imperative functions

Imperative functions typically take the form Function<T, R>, Consumer<T>, Supplier<T>, or synchronous message handlers. The framework invokes the function for each message. Spring Cloud Stream integrates with Spring Cloud Function using ObservationFunctionAroundWrapper to create an observation around each invocation.

With the required observability dependencies present, each imperative function invocation is observed on a per-message basis. The application can focus on business logic without manually wrapping the entire function in a timer.

### Required dependencies

Maven dependencies example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core-micrometer</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>

    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

This is one option using the OpenTelemetry bridge, OTLP exporter, and Prometheus registry. If your system uses Brave/Zipkin or another backend, swap in the corresponding tracer bridge/exporter. Let your project's Spring Boot and Spring Cloud BOM manage dependency versions; do not mix standalone versions outside the compatibility matrix.

### Example function receiving and emitting events

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    private final OrderService orderService;

    OrderFunctions(OrderService orderService) {
        this.orderService = orderService;
    }

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return orderService::accept;
    }
}
~~~

When the function is invoked, Spring Cloud Function's wrapper creates an observation for the invocation. If a tracing bridge is present, the observation can create a span; if a meter handler is present, it can create timers and corresponding metadata.

Do not wrap the whole function manually in another observation just to measure duration. Doing so can produce two nearly identical spans and clutter dashboards. Instead, create additional observations for specific business steps, such as inventory checks or pricing service calls.

## 4. Creating observations for business steps

Suppose the acceptOrder function calls a catalog service to verify a product. You can create a dedicated observation for that operation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Service;

@Service
class CatalogLookup {

    private final ObservationRegistry observationRegistry;
    private final CatalogClient catalogClient;

    CatalogLookup(
            ObservationRegistry observationRegistry,
            CatalogClient catalogClient) {
        this.observationRegistry = observationRegistry;
        this.catalogClient = catalogClient;
    }

    ProductInfo findProduct(OrderCreated event) {
        return Observation.createNotStarted(
                "orders.catalog.lookup",
                observationRegistry)
            .lowCardinalityKeyValue("dependency", "catalog")
            .lowCardinalityKeyValue("operation", "lookup")
            .highCardinalityKeyValue("eventId", event.eventId())
            .observe(() -> catalogClient.find(event.productId()));
    }
}
~~~

In this example:
- The observation name describes the concrete operation.
- dependency and operation have bounded value sets, making them suitable as low-cardinality metadata.
- eventId varies with every message, so it is marked high-cardinality to appear in traces without creating a separate time series per event.

If `catalogClient.find(...)` fails, the observation records the exception and ends. Traces can show this as a child span of the function invocation if current context is propagated properly.

### When should you create child observations?

Create observations for steps with independent diagnostic value:

- Calling external REST/gRPC services.
- Reading or writing a database if not already covered by automatic instrumentation.
- Transforming large payloads or performing expensive computations.
- Validating schemas or enriching events.
- Publishing to another destination when separating business processing time from send time.

Do not create an observation for every trivial statement. Overly fragmented spans increase tracing overhead and make it harder for operators to identify meaningful steps.

## 5. Low-cardinality and high-cardinality metadata

Micrometer distinguishes metadata by the number of distinct values that can appear.

| Type | Characteristics | Examples | Where appropriate |
|---|---|---|---|
| Low cardinality | Small, bounded set of values | function, operation, outcome, region, binder | Metrics and traces |
| High cardinality | Highly variable or nearly unique values | eventId, orderId, traceId, customerId | Traces and controlled logs |

Only low-cardinality key-values are used as meter tags. High-cardinality key-values go only into traces. Adding orderId or eventId as a metric tag lets every message create a new time series, increasing memory, storage costs, and query latency in the metrics backend.

Recommended pattern:

~~~java
Observation.createNotStarted("orders.persist", registry)
    .lowCardinalityKeyValue("operation", "persist")
    .lowCardinalityKeyValue("store", "orders-db")
    .highCardinalityKeyValue("eventId", event.eventId())
    .observe(() -> repository.save(order));
~~~

Avoid putting payloads, emails, phone numbers, tokens, credentials, or personal data into tags or span attributes. Include only necessary metadata in traces and comply with your system's data policies.

## 6. Observing reactive functions

Reactive functions have a different lifecycle from imperative functions. A function of the form Function<Flux<T>, Flux<R>> is typically called once at application startup to wire the source stream to the target stream. Afterward, Reactor drives processing of each item.

Because the function is only invoked during pipeline assembly, ObservationFunctionAroundWrapper cannot automatically create one observation per message as it does for imperative functions. Spring Cloud Stream does not automatically observe the entire reactive stream returned by the application.

Choose the unit to observe explicitly:
- Each item in the Flux.
- One processing segment per item.
- A batch.
- A long processing chain or a window.

The example below creates an observation per item using tap:

~~~java
import io.micrometer.observation.ObservationRegistry;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.observability.micrometer.Micrometer;

@Configuration
class ReactiveOrderFunctions {

    @Bean
    Function<Flux<OrderCreated>, Flux<OrderAccepted>> enrichOrders(
            ObservationRegistry registry,
            OrderService orderService) {

        return orders -> orders.flatMap(order ->
            Mono.fromCallable(() -> orderService.enrich(order))
                .tap(Micrometer.observation(registry))
        );
    }
}
~~~

`tap(...)` attaches the ObservationRegistry to a Reactor publisher segment. In this example, the Mono represents processing one order, so each item gets its own observation. Placing `tap(...)` outside the entire Flux would represent the whole subscription/stream rather than individual messages.

If the stream already carries an observation in Reactor Context, tap can create a child observation. If no upstream observation exists, it creates a new observation using the supplied registry.

### Context propagation in Reactor

ThreadLocal values are not automatically restored across every reactive operator. If trace context is lost when switching threads or schedulers, logs and child spans may no longer belong to the same trace.

You can enable Reactor's automatic context propagation at startup:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import reactor.core.publisher.Hooks;

@SpringBootApplication
class StreamApplication {

    public static void main(String[] args) {
        Hooks.enableAutomaticContextPropagation();
        SpringApplication.run(StreamApplication.class, args);
    }
}
~~~

With Spring Boot versions supporting context propagation configuration, you can use:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Pick the approach suited to your project's Reactor/Spring Boot version and test across scheduler boundaries. Do not assume injecting ObservationRegistry means context automatically flows through every external executor, callback, or async library.

## 7. Tracing context across message brokers

Distributed tracing is only useful when context propagates across process boundaries. When a producer publishes an event, tracing instrumentation can write trace context into message headers or metadata supported by the binder. Consumers read the message and continue or link the trace according to propagation conventions.

Common formats include W3C Trace Context (traceparent/tracestate) and B3. Micrometer Tracing can configure which propagation formats are consumed and produced.

Points to verify:
- Whether producer and consumer share the same propagation format or compatible configurations.
- Whether the binder preserves tracing headers across serialization/header mapping.
- Whether native encoding/decoding inadvertently drops headers.
- Whether middleware outside Spring preserves headers when forwarding messages.
- Whether a batch consumer combines messages from multiple distinct traces.

Not every binder exposes the same level of instrumentation or propagation. Verify with an integration test: emit an event, process it in a second service, and confirm the trace viewer shows the proper relationship across producer, broker, and consumer.

### Batch consumers and tracing

A batch can contain multiple records from different producers, topics, or partitions. You cannot assign a single trace ID to the whole batch when individual records belong to different traces. With the Kafka binder batch listener, tracing propagation is not directly supported the same way as record listeners; tracing headers may be provided per element in converted headers, but the application must handle each record individually if separate observations are required.

When clear per-message traces are needed, consider a record listener or manually creating observations per element. Do not use a single batch span and assume all records share the same origin.

## 8. Configuring Actuator, metrics, and tracing

Actuator provides endpoints to check health, inspect metrics, and export data to monitoring systems. A basic configuration:

~~~yaml
spring:
  application:
    name: order-stream
  reactor:
    context-propagation: auto

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
  health:
    binders:
      enabled: true
  tracing:
    sampling:
      probability: 0.1
  observations:
    key-values:
      service: order-stream
      environment: production
~~~

This configuration:
- Exposes health, info, metrics, and prometheus over HTTP.
- Enables the binder health indicator.
- Shows health details only to authorized callers.
- Samples 10% of traces in this example.
- Attaches service and environment to observations.

Actuator endpoints can expose internal details. Expose only needed endpoints and secure them with network policies, authentication/authorization, or a separate management port. Never expose metrics, env, configprops, or bindings to the public Internet.

### Prometheus

To export metrics in Prometheus format, add the dependency:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Once the application is running, Prometheus can scrape the endpoint:

~~~text
GET /actuator/prometheus
~~~

The `/actuator/metrics` endpoint lists metric names and inspects details of individual meters. Use it during discovery, while production dashboards should rely on the standardized metric names and labels of your deployed version.

### Tracing via OTLP

With Micrometer Tracing and the OpenTelemetry bridge, Spring Boot can send spans to an OpenTelemetry Collector over OTLP. Example properties for some Spring Boot 3.x releases:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Property names and exporter settings can change across Spring Boot generations. Follow the documentation for the exact BOM version managing your application. The Collector must be configured to accept OTLP HTTP or gRPC matching the exporter endpoint.

Sampling probability controls the fraction of traces recorded. A value of 1.0 records every trace; 0.1 samples roughly 10%. Sampling does not mean metrics are only recorded 10% of the time: metrics are still collected according to the meter registry mechanism. Choose the rate based on traffic, cost, and diagnostic needs.

## 9. Monitoring binders and functions with metrics

Metrics must reflect both business processing and message transport. A function may process quickly while consumer lag rises because the broker has too few partitions or producers emit faster than processing speed.

Recommended metric groups:

| Group | Metrics to monitor | Meaning |
|---|---|---|
| Function | Invocation count, duration, error count | Speed and stability of the function |
| Producer | Send rate, send failures, publish latency | Event emission capability |
| Consumer | Receive rate, processing duration, retry count | Message processing capability |
| Backlog | Consumer lag, queue depth, oldest message age | Accumulation level |
| Reliability | Redelivery, DLQ count, ack/checkpoint failures | Delivery quality |
| Runtime | JVM memory, GC, thread pool, CPU | Process resources |
| Tracing | Sampled trace count, error spans, trace duration | Investigating a specific execution flow |

Not all binders export the exact same metric names or labels. Treat binder metrics, broker metrics, and custom application metrics as complementary sources.

### Enabling observation for the Kafka binder

The Kafka binder has a dedicated property to enable Micrometer Observation on its bindings. This property defaults to false:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          enable-observation: true
~~~

With the reactive Kafka binder, producer bindings support observation when this property is enabled; publishing via StreamBridge and Supplier can also be observed. Reactive consumers need pipeline-level context and observation handling, especially when topics are published by systems outside Spring Cloud Stream. Do not enable this property and assume every consumer/binder behaves identically; verify against the binder implementation and test propagation end-to-end.

### Kafka binder offset lag

The Kafka binder provides the metric:

~~~text
spring.cloud.stream.binder.kafka.offset
~~~

This metric represents unconsumed records per topic/group based on committed offset and latest offset. It can be used to:
- Detect consumers falling behind producers.
- Compare lag across groups.
- Provide signals for autoscaling.
- Distinguish slow consumers from idle topics.

The Kafka binder offers settings controlling how offset lag is computed, such as computing on query or using periodically updated values. Check the metrics properties of your exact binder version because lag calculation can affect metadata load and metric response times.

### Kafka Streams metrics

The Kafka Streams binder exposes Kafka Streams metrics and can export them via Micrometer MeterRegistry. These metrics help monitor stream threads, tasks, state stores, record processing, and Kafka Streams internals.

Combine:
- Kafka consumer lag on input topics.
- Kafka Streams thread states.
- Processing rate and latency.
- State restoration and changelog activity.
- RocksDB/state store disk usage.

Do not look only at the RUNNING state. A topology can be RUNNING yet processing slowly, producing flat output, or accumulating high input lag.

## 10. Binder health and readiness

Spring Cloud Stream provides a binder health indicator registered under the name `binders`. It can be enabled with:

~~~yaml
management:
  health:
    binders:
      enabled: true
~~~

Endpoint:

~~~text
GET /actuator/health
~~~

The health indicator depends on the binder implementation. Some binders can check the broker connection, whereas others provide no health indicator. Therefore, you cannot assume all binders return the same data merely because they use Spring Cloud Stream.

### Kafka Streams health

The Kafka Streams binder provides a health indicator checking stream thread states. Details may include:
- Thread name.
- Thread state.
- Active tasks and partitions.
- Standby tasks and partitions.

Common states include CREATED, RUNNING, PARTITIONS_REVOKED, PARTITIONS_ASSIGNED, PENDING_SHUTDOWN, and DEAD. Health can report UP when all registered stream threads are in RUNNING.

If the application runs multiple Kafka Streams processors, health details are grouped by application ID. This helps identify which processor is not functioning.

### Liveness and readiness

Liveness answers whether the process is still alive and should be kept running. Readiness answers whether the instance is ready to accept traffic/messages.

Do not put every transient broker failure into liveness. If a broker outage causes liveness to fail, Kubernetes may continuously restart instances while the broker is still recovering. Typically:
- Liveness focuses on process survivability.
- Readiness can consider binder health and essential dependencies.
- Separate alerts handle broker unavailability, consumer lag, and processing errors.
- Allow grace periods for startup, rebalances, and state restoration.

## 11. Logs and correlation

Logs help pinpoint details of a specific message or exception. When tracing is configured, log patterns can include traceId and spanId on every line for cross-referencing with the trace backend.

Useful fields to log:
- eventId or messageId.
- function name and binding.
- topic/destination and consumer group.
- operation and outcome.
- retry attempt or delivery count if available.
- traceId and spanId when tracing context is present.

Do not log full payloads by default. Payloads can contain personal data, tokens, or sensitive business information. For serialization errors, log schema version, content type, and message ID instead of dumping secret data.

Structured log example:

~~~java
log.info(
    "Order event processed: eventId={}, orderId={}, outcome={}",
    event.eventId(),
    event.orderId(),
    "ACCEPTED"
);
~~~

Because eventId or orderId has high cardinality, keep them in logs/traces for per-message lookups. Never put them into metric tags.

## 12. Customizing ObservationConvention and filtering observations

When you need consistent naming and metadata conventions, use ObservationConvention. Conventions help services emit observations using the same schema: operation name, binder, function, outcome, and meaningful attributes.

Extension points on ObservationRegistry:
- ObservationPredicate: skip observations conditionally.
- ObservationFilter: enrich or adjust context.
- ObservationHandler: add export mechanisms.
- GlobalObservationConvention: apply shared conventions.
- ObservationRegistryCustomizer: customize the registry.

Spring Boot automatically registers matching beans with ObservationRegistry. If you only want to suppress an unnecessary observation, use a predicate/filter rather than layering overlapping instrumentation.

### @Observed annotation

Micrometer supports annotations such as @Observed, @Timed, and @Counted. In Spring Boot, enable:

~~~yaml
management:
  observations:
    annotations:
      enabled: true
~~~

And add an AspectJ weaver compatible with your Spring Boot version. If a method is already automatically instrumented by the framework, adding @Observed can produce duplicate observations. Only annotate methods lacking automatic instrumentation, or explicitly suppress duplicates via predicates/configuration.

## 13. Reading an operational scenario

Suppose a dashboard shows:
- Producer rate is steady.
- Consumer lag is rising continuously.
- Function processing p95 jumped from 40 ms to 900 ms.
- Error rate has not risen noticeably.
- JVM CPU is rising while memory stays stable.

How to investigate:
1. Inspect the longest-duration traces to identify slow child spans.
2. If the catalog lookup span is slow, check the downstream service and connection pool.
3. If function duration is high while child spans are fast, check serialization, schedulers, locks, or uninstrumented code.
4. Compare consumer concurrency against partition count.
5. Check broker throttling, rebalances, and network.
6. Inspect per-topic/partition lag to spot hot partitions.
7. Evaluate whether scaling will raise throughput or merely increase resource contention.

Another scenario: function duration is normal, yet oldest message age increases. This can happen when messages sit in the broker for a long time before a consumer receives them. You need backlog metrics and elapsed time from event timestamp to processing start, not just a function timer.

## 14. Recommended dashboards and alerts

A dashboard for Spring Cloud Stream should be organized into rows:

| Dashboard row | Charts | Operational question |
|---|---|---|
| Traffic | Input/output messages per second | Are producers and consumers active? |
| Latency | Function p50/p95/p99, end-to-end age | Is message processing slow? |
| Errors | Function exceptions, send failures, deserialization errors | Which layer is failing? |
| Backlog | Kafka lag, queue depth, oldest message age | Are consumers keeping up with producers? |
| Reliability | Retries, redeliveries, DLQ, ack/checkpoint failures | Are messages being redelivered or quarantined? |
| Runtime | CPU, memory, GC, thread pools | Are instances short on resources? |
| Broker health | Binder health, broker connections, partition/task state | Is the system connected and distributing load properly? |

Alerts should tie to business impact:
- Lag exceeds threshold for a sustained duration.
- Oldest message age breaches SLA.
- Sudden spike in DLQ.
- Rising publish failures or ack/checkpoint failures.
- Kafka Streams thread in DEAD or failing to reach RUNNING.
- Function error rate exceeds SLO.
- Tracing backend or metrics exporter stops receiving data.

Avoid alerting on a single brief spike. Use time windows, baselines, and severity tiers to reduce false positives.

## 15. Common issues

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Imperative function has no traces | Missing actuator, tracer bridge, or exporter | Check dependencies, ObservationRegistry, and sampling |
| Metrics exist but no traces | Tracer bridge/exporter not configured or traces sampled out | Check tracer setup and sampling probability |
| Reactive function only creates one observation at startup | Reactive functions are not auto-wrapped per message | Use tap(Micrometer.observation(registry)) on per-item segments |
| Trace breaks across scheduler switches | Context propagation not enabled | Configure Reactor context propagation and test across schedulers |
| Metrics explode in time series | eventId/orderId used as low-cardinality tag | Move that data to high-cardinality trace attributes or logs |
| Duplicate spans appear | Function is auto-wrapped and also manually wrapped at top level | Keep the wrapper; only add child observations for business steps |
| Binder health shows no details | Binder implementation has no health indicator | Use broker metrics and a custom HealthIndicator if needed |
| Kafka lag metric missing | Micrometer/binder metrics not configured or filtered out | Check MeterRegistry, metric configuration, and version |
| Kafka Streams health is DOWN | Thread not RUNNING, DEAD, or restoring/rebalancing | Check states, tasks, broker, and state restoration |
| Logs missing trace correlation | Trace context not entering MDC or lost across async boundaries | Check tracing bridge and context propagation |
| Batch trace does not match individual records | One batch holds messages from many traces | Track per-record or design batch spans with span links |
| Metrics endpoint returns 404 | Endpoint not exposed or missing registry | Check Actuator dependency and exposure properties |
| Prometheus cannot scrape | Missing registry or endpoint blocked | Add Prometheus registry and check security/network |
| Exporter creates high overhead | Unsuitable sampling, export batching, or timeouts | Tune sampling, exporter settings, and collector capacity |

## 16. Hands-on exercise: observing the acceptOrder function

Build an order-processing function and observe both the function execution and the catalog lookup step.

1. Add Actuator, reactor-core-micrometer, and a tracer bridge from the BOM.
2. Create an imperative `acceptOrder` function receiving `OrderCreated`.
3. Confirm function invocations automatically create observations.
4. Inject `ObservationRegistry` into `CatalogLookup`.
5. Create a child observation `orders.catalog.lookup` for the catalog call.
6. Add low-cardinality tags `operation` and `dependency`.
7. Attach `eventId` as a high-cardinality trace attribute.
8. Configure 10% sampling for a staging/production-like environment.
9. Expose `health`, `metrics`, and `prometheus` endpoints on the management network.
10. Enable binder health and check `/actuator/health`.
11. Send one valid event and one event triggering a catalog failure.
12. Verify duration/error metrics and the child trace span.
13. Convert the function to reactive `Flux` and use `tap(Micrometer.observation(registry))` per item.
14. Test trace context across scheduler boundaries.
15. Build a dashboard with message rate, function p95, error rate, consumer lag, and DLQ count.
16. Simulate a slow consumer and verify lag/oldest-message-age alerts.
17. Verify metric labels do not contain `eventId`, `orderId`, or sensitive data.

Acceptance criteria table:

| Item | Verification criteria |
|---|---|
| Dependencies | Actuator, Reactor Micrometer, and tracer bridge match BOM |
| Imperative function | Observation recorded per invocation/message |
| Custom observation | Child span created for the business step |
| Cardinality | Low/high cardinality classified accurately |
| Reactive function | Each item/segment produces an observation as designed |
| Context propagation | Traces remain intact across reactive schedulers |
| Metrics export | Queryable via Actuator/Prometheus |
| Trace export | Traces arrive at the target backend |
| Binder health | Shows broker/binder state when supported by implementation |
| Kafka lag | Per-topic/group metric and suitable alerts configured |
| Kafka Streams | Thread states, tasks, and runtime metrics tracked |
| Security | Management endpoints are private and never leak payloads |
| Dashboard | Covers traffic, latency, errors, backlog, and reliability |
| Alerts | Tied to SLAs with actionable runbooks |

## Conclusion

Micrometer Observation lets Spring Cloud Stream observe functions using a single model for both metrics and traces. For imperative functions, Spring Cloud Function provides ObservationFunctionAroundWrapper to instrument each invocation. For reactive functions, use Reactor tap and ObservationRegistry to choose the right observation unit because the framework does not automatically wrap the returned stream.

Combine function duration, error rates, broker lag, binder health, and distributed traces. The Kafka binder provides offset lag metrics; the Kafka Streams binder provides thread/task metrics and health; other binders may expose different signals, so complement them with broker-side metrics. Keep metric tags low-cardinality, propagate trace context via message headers, secure Actuator endpoints, and test both happy paths and failure paths.

## References

- [Spring Cloud Stream 5.0.4 – Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Cloud Stream – Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/health-indicator.html)
- [Spring Cloud Stream – Kafka Binder Metrics](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/metrics.html)
- [Spring Cloud Stream – Reactive Kafka Binder Observability](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/reactive_observability.html)
- [Spring Cloud Stream – Kafka Streams Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/health-indicator.html)
- [Spring Boot 3.5 – Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Micrometer – Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer – High Cardinality Tags](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
- [Reactor – Micrometer Integration](https://projectreactor.io/docs/core/release/reference/metrics.html)
