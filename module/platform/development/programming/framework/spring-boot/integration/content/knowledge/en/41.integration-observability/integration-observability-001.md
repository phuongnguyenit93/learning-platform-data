# Micrometer Observation and Spring Boot-Supported Integrations

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, a processing flow can pass through an HTTP controller, WebClient, database, cache, message broker, and Spring Integration endpoints. When an order is processed slowly or an event is redelivered multiple times, the operational question is not just "whether an error occurred", but also **at which step latency occurred, how far the flow progressed, and whether the error affected the business outcome**.

This lesson belongs to the **Integration Observability** chapter and focuses on **Micrometer Observation** and how Spring Boot wires observability components together. Spring Boot helps configure metrics, tracing, and supported integration points; the application still must define measurement names, business boundaries, tags, completion timing, error handling, and data security.

After this lesson, you will be able to:

- Distinguish **logs, metrics, and traces** and the role of `Observation`.
- Explain `ObservationRegistry`, `ObservationHandler`, `ObservationConvention`, and low/high-cardinality key values.
- Use Spring Boot configuration to collect metrics/traces and create custom observations for integration business logic.
- Know what additional conditions HTTP, messaging, database, cache, and Spring Integration integrations require for real-world observability.
- Propagate context across threads, reactive pipelines, and other systems without confusing `traceId` with an idempotency key.
- Test, monitor, and diagnose integration flows using meaningful signals.

> **Important limitation:** "Having Observation" does not mean all three signals are already available in the monitoring system. Metrics require a registry/exporter, tracing requires a tracer/exporter and propagation, and logs require corresponding application logging and a log collection pipeline.

## 1. Why Does an Integration Flow Need Observability?

Consider an order-submission event flow:

1. The HTTP API receives `OrderSubmitted`.
2. The service checks previously processed records to avoid duplicate `eventId`s.
3. It calls the Catalog API with `WebClient` to verify product information.
4. It writes the state to the database and outbox in a local transaction.
5. The publisher sends the outbox entry to the message broker.
6. The consumer receives the event, updates the cache, and calls the delivery system.

In this flow, an HTTP request can finish **before** the consumer finishes processing the event. A database transaction can commit successfully while the publisher has not yet sent to the broker. A timeout in the delivery call does not prove the partner did not perform the operation.

~~~mermaid
flowchart LR
    A["HTTP / Gateway"] --> B["Idempotency check"]
    B --> C["Catalog WebClient"]
    C --> D["DB + outbox"]
    D --> E["Broker publisher"]
    E --> F["Broker / consumer"]
    F --> G["Cache + delivery API"]
    A -. "request span" .-> H["Tracing"]
    B -.-> H
    C -.-> H
    D -.-> H
    E -.-> H
    F -.-> H
    G -.-> H
    A -. "rates & latency" .-> I["Metrics"]
    C -.-> I
    D -.-> I
    E -.-> I
    F -.-> I
    G -.-> I
    G -. "structured events" .-> J["Logs"]
~~~

The diagram illustrates the observability goal; it **does not guarantee** that all spans are pre-created or that trace context automatically crosses every adapter. You must verify the auto-configuration and instrumentation conditions of each library.

The three signals answer different questions:

| Signal | Primarily answers | Examples |
| --- | --- | --- |
| **Metrics** | Is there an abnormal trend in errors, latency, or load? | Timeout rate, p95, queued message count |
| **Traces** | Which components did a specific task pass through and where was time spent? | HTTP inbound → WebClient → DB → broker |
| **Logs** | What event happened at a point in time, and with what context? | Event rejected due to unsupported schema version |

Do not turn metrics into a per-event log: putting an `orderId` or `eventId` tag on every execution causes the number of time series to grow rapidly. Conversely, having only logs without metrics makes it difficult to evaluate error rates, backlog, or p99 at system scale.

## 2. What Is Micrometer Observation?

`Micrometer Observation` is an abstraction for **an activity with a start and end**, optionally accompanied by a name, attributes, events, and errors. It allows the same instrumentation point to send data to different handlers, instead of business code calling metrics and tracing APIs everywhere.

Components:

| Component | Responsibility |
| --- | --- |
| `Observation` | Represents an activity being measured; calls `start`, opens scope, records error/event, and calls `stop` |
| `ObservationRegistry` | Central point for configuring and registering observations/handlers; Spring Boot can provide an integrated bean |
| `Observation.Context` | Holds information for an observation, used by handlers and conventions |
| `ObservationHandler` | Reacts to lifecycle callbacks; can create timers, spans, or custom processing |
| `ObservationConvention` | Standardizes observation name, contextual name, and key/value sets |
| `ObservationPredicate` | Decides which observations are ignored |
| `ObservationFilter` | Adjusts context/tags according to shared policies |

~~~mermaid
flowchart TB
    A["Business adapter / HTTP instrumentation"] --> B["Observation"]
    B --> C["ObservationRegistry"]
    C --> D["Convention / Predicate / Filter"]
    C --> E["Meter ObservationHandler"]
    C --> F["Tracing ObservationHandler"]
    E --> G["MeterRegistry"]
    F --> H["Micrometer Tracing"]
    G --> I["Prometheus / OTLP / monitoring"]
    H --> J["OTLP collector / trace backend"]
~~~

An observation can produce a timer measuring the `start → stop` interval when wired to a meter handler, and can create a span when wired to a tracing handler. Without the corresponding handler or exporter, results may not appear in the monitoring system.

### 2.1. Lifecycle of an Observation

Typical lifecycle:

1. Create an observation via `ObservationRegistry`.
2. Attach meaningful name/attributes before starting.
3. `start()`.
4. `openScope()` when the observation needs to be placed into the current thread context.
5. Run the logic.
6. Record `observation.error(exception)` if an error occurs.
7. Close the scope and call `stop()` in all cases.

The `observe(...)` API provides a shorthand for **synchronous** work, automatically handling start/scope/error/stop:

~~~java
import io.micrometer.observation.Observation;

Observation.createNotStarted("integration.order.validate", registry)
        .lowCardinalityKeyValue("source", "http")
        .observe(() -> {
            validateOrder(order);
        });
~~~

In this example, `registry` and `order` are existing variables in the component; `validateOrder` is illustrative business logic. The name `integration.order.validate` describes the activity type and does not contain individual order IDs.

### 2.2. Low Cardinality and High Cardinality

**Cardinality** is the number of distinct values a key can take.

| Data | Recommended scope | Why |
| --- | --- | --- |
| `flow=order-ingestion` | Low cardinality | Finite set of flows, suitable for metrics and traces |
| `operation=validate/apply/publish` | Low cardinality | Small value set, comparable across runs |
| `outcome=success/rejected/error` | Low cardinality | Suitable for dashboards and error rates |
| `partner=catalog/delivery` | Low cardinality if partner set is controlled | Useful for per-downstream alerts |
| `eventId=evt-...` | Do not put in metric tags | Nearly unique per event |
| `orderId`, `userId`, `tenantId` | Avoid metric tags; consider security even in traces/logs | Easily creates high cardinality or leaks data |
| Full URL with query parameters | Avoid metric tags | Arbitrary paths and tokens can be exposed |
| Route template `/orders/{id}` | Low cardinality | Finite, easy to measure per endpoint |

`lowCardinalityKeyValue(...)` typically goes into **metrics and traces**. `highCardinalityKeyValue(...)` should only go into **traces**, with appropriate security and retention policies. High cardinality does not mean "safe to record every ID"; the tracing backend still incurs cost and requires data protection.

**Principle:** define the tag set from business design before instrumenting; do not take raw user input as metric tags.

## 3. Bootstrapping Infrastructure with Spring Boot Actuator

For a Spring Boot application with Spring Integration, add dependencies for infrastructure and exporting metrics:

~~~groovy
// build.gradle - Gradle Groovy DSL
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // If exporting metrics in Prometheus format:
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

These starters allow Boot to auto-configure many Micrometer components when dependencies and conditions match. Some starters/package groups were reorganized between Spring Boot 3.x and 4.x, so let Boot manage dependency versions and check the corresponding reference documentation.

Basic configuration for a test environment:

~~~yaml
spring:
  application:
    name: order-integration

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-integration
  tracing:
    sampling:
      probability: 0.1
~~~

Meaning:

- `/actuator/health`: checks status according to configured health indicators.
- `/actuator/metrics` and `/actuator/metrics/{name}`: inspects metric names and exported tags/measurements.
- `/actuator/prometheus`: serves scraping when a Prometheus registry and endpoint are available.
- `management.metrics.tags.application`: adds a stable application tag to metrics.
- `management.tracing.sampling.probability`: trace sampling rate; **not** a metric drop rate.

The example above does not configure an OTLP endpoint to export traces. Exporting traces requires adding a tracing implementation/exporter in the next section.

> **Security:** `management.endpoints.web.exposure.include` exposes endpoints on the HTTP management interface; use appropriate network policy, authentication/authorization, gateway, or management port. Do not expose all Actuator endpoints publicly, and do not send secrets in metric labels.

### 3.1. Enabling Tracing with OpenTelemetry: Differences by Boot Version

Spring Boot supports Micrometer Tracing and backends such as OTLP/Zipkin when the corresponding dependencies and configuration are present.

With **Spring Boot 4.x**, the official documentation introduces a convenient starter for OpenTelemetry + OTLP:

~~~groovy
// Spring Boot 4.x
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Then configure the exporter using `management.opentelemetry.tracing.export.otlp.*` keys matching the protocol/collector. Provide endpoints and credentials from environment configuration rather than hard-coding access tokens.

With **Spring Boot 3.x**, a common configuration uses separate dependencies:

~~~groovy
// Spring Boot 3.x: illustrative OpenTelemetry + OTLP choice
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

OTLP tracing properties in 3.x typically belong to `management.otlp.tracing.*`; **do not copy 4.x configuration verbatim onto 3.x**. Check the reference guide for your Boot version and choose an exporter supported by your monitoring environment.

Distinctions:

- **Micrometer Observation**: API for marking work to be measured.
- **Micrometer Tracing**: API/bridge supporting spans and propagation.
- **OpenTelemetry/Brave**: tracer implementation and corresponding propagation/export format.
- **Collector/backend**: service that receives, stores, and queries traces.
- **Prometheus/OTLP MeterRegistry**: metrics export pipeline; does not mean the same tracer backend automatically receives metrics.

You can enable only metrics without tracing initially, while keeping naming/tags consistent for later expansion.

## 4. Creating Custom Observations for Integration Business Logic

An automatically measured HTTP request typically only reports total request latency. Business teams also need to know how much time was spent **applying the event to the database**, **waiting on a downstream**, or **publishing a message**.

Suppose there is a DTO and a persistence port:

~~~java
// OrderEvent.java
public record OrderEvent(
        String eventId,
        String orderId,
        String source) {
}
~~~

~~~java
// OrderPersistencePort.java
public interface OrderPersistencePort {
    void apply(OrderEvent event);
}
~~~

A service instruments a **synchronous activity with clear boundaries**:

~~~java
// OrderProcessingService.java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderProcessingService {

    private final OrderPersistencePort persistencePort;
    private final ObservationRegistry observationRegistry;

    public OrderProcessingService(
            OrderPersistencePort persistencePort,
            ObservationRegistry observationRegistry) {
        this.persistencePort = persistencePort;
        this.observationRegistry = observationRegistry;
    }

    public void process(OrderEvent event) {
        Observation.createNotStarted(
                        "integration.order.apply",
                        observationRegistry)
                .lowCardinalityKeyValue("flow", "order-ingestion")
                .lowCardinalityKeyValue("operation", "apply")
                .observe(() -> persistencePort.apply(event));
    }
}
~~~

When `persistencePort.apply(event)` throws an exception out of the lambda, `observe(...)` automatically records the error and stops the observation before the exception propagates to the caller. This measurement covers the **actual execution time of the synchronous call**; it does not replace measuring transaction commit if commit happens in another layer after the method returns.

When you need to distinguish **caught-and-handled errors** from true success, use the explicit lifecycle:

~~~java
Observation observation = Observation.createNotStarted(
                "integration.partner.lookup",
                observationRegistry)
        .lowCardinalityKeyValue("partner", "catalog")
        .start();

try (Observation.Scope scope = observation.openScope()) {
    invokePartner(); // Illustrative method; may throw RuntimeException
} catch (RuntimeException exception) {
    observation.error(exception);
    // Apply the adapter's fallback/throw contract here.
    throw exception;
} finally {
    observation.stop();
}
~~~

Ensure `stop()` is in `finally` to prevent dangling observations on errors. If a fallback successfully handles an internal error, clearly define what "success" means at that activity level; you can add an outcome tag with a finite value set or create a separate observation for the fallback.

### 4.1. Attaching an Observation to a Spring Integration Flow

With Java DSL and the service bean above:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class OrderFlowConfiguration {

    @Bean
    IntegrationFlow orderFlow(OrderProcessingService service) {
        return IntegrationFlow.from("orders.input")
                .handle(service, "process")
                .get();
    }
}
~~~

This flow connects the `orders.input` channel to the service activator. If messages are sent via a `DirectChannel` and the handler executes on the same thread, the observation in `OrderProcessingService` runs in the synchronous processing path. If switched to an `ExecutorChannel`, poller, or broker, the transaction/trace context boundary can change.

**It is not mandatory to place manual Observations on every endpoint.** Spring Integration has its own instrumentation mechanism; use custom observations for spans of work with specific business meaning and avoid double-measuring the same operation under different names.

### 4.2. Using @Observed

Micrometer provides the `@Observed` annotation to measure methods. Spring Boot's annotation scanning support must be explicitly enabled and appropriate AOP support must be available.

~~~yaml
management:
  observations:
    annotations:
      enabled: true
~~~

In Spring Boot 4.x, the documentation instructs adding `org.springframework.boot:spring-boot-starter-aspectj` if weaving/AOP support is not already present. With Spring Boot 3.x, verify the `org.aspectj:aspectjweaver` requirement and configuration on your running version.

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    @Observed(
            name = "integration.price.calculate",
            lowCardinalityKeyValues = {
                    "component", "pricing-service"
            })
    public int calculate(int quantity, int unitPrice) {
        return quantity * unitPrice;
    }
}
~~~

`@Observed` is convenient for synchronous methods, but remember:

- If a method calls another method within the **same object** via self-invocation, proxy-based advice may not run.
- Already auto-instrumented components like HTTP controllers may create **duplicate observations** if annotations are added indiscriminately.
- Choose one measurement approach with clear boundaries: annotation, manual API, or built-in instrumentation as needed.

## 5. Integrations Supported by Spring Boot

The degree of automation varies by library, version, and configuration.

| Area | What can be observed | Practical conditions/boundaries |
| --- | --- | --- |
| **HTTP inbound (Spring MVC/WebFlux)** | Request count, latency, status, HTTP server spans | Requires web stack and appropriate observation/metrics/tracing configuration |
| **WebClient** | HTTP client metrics/traces; trace header propagation | Use Boot auto-configured `WebClient.Builder`; do not build a standalone client bypassing Boot config |
| **RestClient/RestTemplate** | HTTP client observations and trace propagation | Use Boot-managed builder/template or appropriate customizers |
| **JDBC/DataSource** | Pool metrics; optional SQL observations via extra instrumentation | Pool metrics **differ** from query tracing; JDBC query spans require components like Datasource Micrometer |
| **R2DBC** | Connection pool/driver metrics or observations | Boot's R2DBC observability requires supporting dependency/config, e.g., `r2dbc-proxy` |
| **Cache** | Provider metrics like hits/misses/evictions when instrumented | Depends on Caffeine/Redis/provider; not every `@Cacheable` gets spans by default |
| **Kafka/Rabbit/JMS** | Send/receive, listener/container, or client metrics/spans | Depends on adapter, listener/template observation flags, transport, and exporter |
| **Spring Integration** | Gateway, producer/channel, handler, and endpoint metrics/traces | Requires Observation infrastructure + appropriate Integration management configuration |
| **Thread pools/schedulers** | Active threads, queue, task metrics depending on bean/provider | Does not guarantee trace context automatically crosses every executor |
| **Application logic** | Domain operation latency, outcome, error | Deliberately create `Observation`/`@Observed` |

For databases, distinguish **"how many connections are left in the pool"** from **"which query is slow"**. Having Hikari metrics alone does not prove per-SQL-query tracing is enabled. Similarly, a broker client may have good network metrics, yet if the listener does not propagate trace context, it will be hard to see a single trace across producer and consumer.

### 5.1. Keeping Boot-Managed HTTP Builders

Example using an injected `WebClient.Builder`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class CatalogHttpConfiguration {

    @Bean
    WebClient catalogWebClient(WebClient.Builder bootBuilder) {
        return bootBuilder
                .baseUrl("https://catalog.example.org")
                .build();
    }
}
~~~

The URL above is illustrative only; real systems load URLs from `@ConfigurationProperties`. The Boot-provided builder is the key hook for receiving connector settings, observation registry, and tracing propagation configuration. Creating clients directly via `WebClient.create(...)` or `WebClient.builder()` **does not automatically** inherit Boot's full instrumentation setup.

When the app makes an outbound HTTP call, the HTTP client activity can appear as a child span of the inbound request **if an active observation context and compatible tracer exist**. If the call runs on another thread, additional context propagation is required (Section 7).

### 5.2. Brokers, Databases, and Caches: Do Not Generalize from HTTP

For brokers, a successful `publish()` does not mean the consumer committed the business effect; minimal observability should distinguish **send, acknowledgment, receive, process, retry, and dead-letter**. For Kafka/AMQP, enable observation on listener/template/adapter according to the library version; do not assume every broker adapter automatically creates spans just by adding Actuator.

For caches, indicators like hit ratio or evictions only exist if the provider has corresponding instrumentation. Cache misses can slow down the overall request, but to know whether latency comes from cache lookup or downstream, separate observations clearly and avoid putting sensitive data keys into tags.

## 6. Observing Spring Integration Endpoints

Modern Spring Integration provides `IntegrationManagement` and supports Micrometer metrics/Observation. An easy-to-miss detail: **having an `ObservationRegistry` bean does not mean all Integration endpoints are instrumented**.

According to Spring Integration documentation, `@EnableIntegrationManagement` allows configuring which components to monitor via `observationPatterns`. By default, Observation is not automatically enabled for all `IntegrationManagement` components.

Example enabling broadly for exploration in a test environment:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegrationManagement;

@Configuration(proxyBeanMethods = false)
@EnableIntegrationManagement(observationPatterns = "*")
public class IntegrationObservabilityConfiguration {
}
~~~

- `observationPatterns = "*"` requests instrumentation of supported components whose names match.
- In production with many flows/endpoints, select only the groups needing observation via naming conventions to reduce overhead and cardinality.
- Requires properly configured `ObservationRegistry` and handlers. Do not confuse `observationPatterns` with trace sampling policy.
- Metric names and conventions can vary by version; verify actual endpoints in `/actuator/metrics`.

Documented Spring Integration observation/metric names include:

| Observation/metric | Meaning | Example bounded-cardinality tags |
| --- | --- | --- |
| `spring.integration.gateway` | Gateway request-reply processing time | Component name, type, outcome |
| `spring.integration.handler` | Time spent in message handler | Component name, type |
| `spring.integration.producer` | Message creation/sending activity from instrumented component | Component name, type |
| `spring.integration.*.active` | Long-task timer for in-progress activity, when supported | Tags present at start time |

Component names must remain stable across deployments. Do not name channels/endpoints with `orderId`, tenant, or user information, because component names can become metric labels.

### Observing Flows vs. Measuring Business Logic

In the flow `orders.input → filter → transformer → handler`:

- The **gateway** observation shows intake/interaction work.
- The **handler** observation shows processing time at an endpoint.
- The custom observation `integration.order.apply` explains a step with business meaning.
- The **HTTP client** observation represents an external service call.
- The **DB** observation reflects pool/query instrumentation level.

These durations can be **nested**. Summing the durations of all observations double-counts overlapping time and does not equal end-to-end latency. Use distributed tracing to view parent/child relationships and analyze the critical path.

## 7. Trace Context Across Threads, Reactive Pipelines, and Brokers

A trace typically has a `traceId` linking multiple spans; each span has its own `spanId`. When work crosses to another thread, process, or broker, **trace context** must be propagated so the consumer can continue the relationship.

~~~mermaid
sequenceDiagram
    participant API as HTTP API
    participant S as Order Service
    participant C as WebClient/Catalog
    participant B as Broker
    participant W as Worker Consumer
    API->>S: request + trace context
    S->>C: outbound HTTP + trace headers
    C-->>S: response
    S->>B: event + propagated context
    B-->>W: redelivery/delivery
    W->>W: consumer span + business processing
~~~

The diagram assumes **producer/consumer instrumentation actually injects and extracts propagation headers**; a broker does not do this automatically just because the payload contains `correlationId`.

### 7.1. Reactive Context and Thread-Locals

In synchronous code, the active observation typically lives in a thread-local scope. Reactor can switch execution to different threads, so thread-local values are not automatically available in every operator.

Spring Boot has the property:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

When using `auto`, Boot can enable Reactor automatic context propagation according to the capabilities of the current version and libraries. This introduces some runtime overhead, so test actual spans on flows using `publishOn`, `subscribeOn`, `flatMap`, or async clients.

**Common measurement trap in reactive code:**

~~~java
// Wrong if the goal is to measure full network I/O:
return Observation.createNotStarted("catalog.fetch", registry)
        .observe(() -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class));
~~~

`bodyToMono(...)` returns an unsubscribed publisher. The `observe(...)` lambda here finishes right after **creating the publisher**, before actual network I/O completes. To measure reactive latency, use instrumentation whose lifecycle is bound to `subscription → terminal signal` with proper context propagation; do not time `Mono` creation as if it were HTTP time.

With WebClient, prefer the built-in instrumentation from the Boot-provided builder. For custom Reactor pipelines, use the observation/tracing support for your Reactor version or tie start/stop to terminal and cancellation signals.

### 7.2. Executors, @Async, and Pollers

When processing via `ExecutorChannel`, `@Async`, or a Spring Integration poller, caller and consumer often run on different threads. Note:

- Submitting work to an executor does not guarantee transferring the full observation scope to the new thread.
- If using a Boot auto-configured `AsyncTaskExecutor`, some Boot versions support `spring.task.execution.propagate-context`; verify the property for your version before using.
- If declaring a custom executor, you may need `ContextPropagatingTaskDecorator` or an equivalent propagation mechanism.
- Propagating trace context does not mean propagating transaction context; a JDBC transaction on the sending thread does not automatically span across an `ExecutorChannel`.

### 7.3. Propagation and Idempotency Are Two Different Contracts

| Value | Purpose | Should it be used for deduplication? |
| --- | --- | --- |
| `traceId` | Links request/process traces across spans | **No**; one business operation can have multiple attempts/traces |
| `spanId` | Identifies one unit of measurement in a trace | **No** |
| `correlationId` | Links messages belonging to the same business workflow | Only if the contract explicitly defines its semantics |
| `eventId`, `idempotencyKey` | Identifies business event/action to guard against duplicate delivery | **Yes**, with a store/unique constraint and atomic rules |
| `outboxId` | Tracks records awaiting publishing | Useful for publish/retry workflows, but insufficient for consumer idempotency |

Do not copy all baggage or source request headers into broker messages. Forward only standardized trace context and validated business metadata.

## 8. Observing Errors, Retries, Transactions, and Duplicate Handling

Observability must reflect the **actual outcome** of the flow, not merely count exceptions.

Suppose a consumer hits a timeout calling the delivery service:

1. The broker delivered `OrderReady` to the consumer.
2. The consumer sends an HTTP POST to the delivery service.
3. The HTTP request times out; it is uncertain whether the partner received it.
4. The consumer retries with the same `idempotencyKey`.
5. If the partner supports idempotency, it may return the result of the first call.
6. Only ack the broker when the consumer/broker contract permits confirming completion.

Observation points should be separated:

| Event | What to measure? | Notes |
| --- | --- | --- |
| Message received | Number of deliveries to the consumer | Includes redeliveries, not unique business count |
| Duplicate discarded | Number of events skipped by idempotency | Count by stable event type |
| Business apply | Latency + outcome of business logic | Only "success" when effects are committed at the proper boundary |
| HTTP outbound attempt | Latency/status/exception of **each attempt** | Multiple retries generate multiple HTTP attempts |
| Final delivery result | Final outcome of the operation per retry policy | Differs from per-attempt error rate |
| Outbox publish | Backlog, record age, send attempts, acknowledged | Send success does not mean consumer done |
| DLQ/recovery | Messages exhausting retries and backlog age | Requires replay/reconciliation process |

If an exception is caught and a fallback is returned, the HTTP outbound span may record an error while the business observation returns success per contract. Do not "rewrite" HTTP metrics to success to make numbers look clean. Instead, define each layer's outcome according to its responsibility.

### Observation and Transactions

When measuring latency **through DB commit**, the observation start/stop must wrap the commit boundary itself (e.g., an outer wrapper around the `@Transactional` call), rather than only measuring inside a method whose transaction has not yet committed.

With a flow running via `DirectChannel` on the same thread, a local transaction can span compatible DB steps if configured. Crossing an `ExecutorChannel`/broker does not provide a shared ACID transaction by default. A trace connects steps to show execution flow, but **does not provide atomicity or delivery guarantees**.

### Retries and Sampling

If the sampling rate is low, specific traces of rare errors may be missed. Total error metrics and latencies can still be captured with full instrumentation while the trace backend stores only samples. For critical errors requiring investigation, combine:

- Counter/timer metrics by low-cardinality **outcome**.
- Structured logs containing `traceId`/`spanId` when tracing context is present.
- Sampling tuned to SLO/cost, and collector tail-based sampling if supported by the architecture.
- Business event IDs in audit/inbox/outbox stores (with controlled access), not as metric labels.

## 9. Recommended Measurement Plan for an Integration System

From the same order ingestion flow, pick a few indicators that inform concrete operational actions:

| Group | Suggested metric/observation | Purpose |
| --- | --- | --- |
| HTTP ingress | Request rate, 4xx/5xx, p95/p99 | Detect errors at API edge |
| HTTP downstream | Duration and timeouts by `partner` | Detect Catalog/Delivery degradation |
| Business operation | `integration.order.apply` by `outcome` | Measure business processing success/error |
| Idempotency | Duplicate events / total events | Detect redelivery or upstream duplicates |
| DB | Pool active/idle/pending; query latency if instrumented | Distinguish pool exhaustion vs. slow queries |
| Cache | Hit ratio, misses, evictions, backend errors | Verify whether cache helps or hurts |
| Broker | Consumer lag, queue depth, redelivery, DLQ | Detect backlog |
| Outbox | Rows pending, oldest age, publish attempts | Detect DB → broker sync stalls |
| Spring Integration | Gateway/handler/producer duration | Identify slow endpoint processing |

A pragmatic dashboard should place **request rate, error rate, p95/p99 latency, and saturation/backlog** side by side so operators can spot trends. For async flows, add **latency from event receipt to business effect completion** based on standardized timestamps with clock-skew awareness.

A meaningful SLO might be: "99% of valid events are applied within 30 seconds of broker receipt", but only set such a target if you have timestamps/acks and measurements to verify it. Do not assume inbound HTTP latency equals total workflow latency when consumers run later.

## 10. Testing Observations and Auto-Configuration

Tests should prove **actual observable behavior** occurred, rather than only verifying that an `ObservationRegistry` bean exists.

### 10.1. Unit Testing Lifecycle and Metric Names

You can test a synchronous observation with a simple Micrometer Registry without an external backend:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderObservationTest {

    @Test
    void recordsOneCompletedOperation() {
        var meterRegistry = new SimpleMeterRegistry();
        var observationRegistry = ObservationRegistry.create();

        observationRegistry.observationConfig()
                .observationHandler(
                        new DefaultMeterObservationHandler(meterRegistry));

        Observation.createNotStarted(
                        "integration.order.apply",
                        observationRegistry)
                .lowCardinalityKeyValue("flow", "order-ingestion")
                .observe(() -> {
                    // Illustrative synchronous operation.
                });

        assertEquals(
                1L,
                meterRegistry.get("integration.order.apply")
                        .tag("flow", "order-ingestion")
                        .timer()
                        .count());
    }
}
~~~

These test classes use Micrometer and JUnit. Here `SimpleMeterRegistry` confirms the observation **was converted to a timer by the handler**, though it does not prove trace export, HTTP propagation, or integration auto-configuration.

### 10.2. Spring Boot Integration Tests

In a `@SpringBootTest`, verify:

1. `ObservationRegistry` is injected by Boot and has handlers/registries according to dependencies.
2. Flows or HTTP adapters receive Boot auto-configured clients/builders.
3. Calling simulated endpoints via HTTP stubs or broker test fixtures produces metrics/spans when components are instrumented.
4. Timeouts/HTTP 5xx/duplicates produce observable outcomes per contract.
5. Flows with `@EnableIntegrationManagement` and `observationPatterns` produce instrumentation for the intended endpoint group.
6. If tracing is enabled, verify context propagation between inbound request and outbound calls, or producer and consumer.

**Note:** Spring Boot may disable **trace reporting/export** in certain `@SpringBootTest` setups to avoid sending spans externally from tests. To assert spans, use an appropriate test registry/tracer or configure an in-memory exporter for fixtures; do not conclude tracing is broken because a production backend received no spans during tests.

### 10.3. Testing Context Loss and Sensitive Data

High-value tests:

- Replace `DirectChannel` with `ExecutorChannel` or a `publishOn` in Reactor; verify parent-child traces.
- Send an event through a broker stub and verify trace headers are injected/extracted.
- Inspect metric names/tags and assert no `userId`, `eventId`, access token, or raw URL query appears.
- Generate 100 distinct `eventId`s; metric series count must not grow per event.
- Inject an exception inside a handler; verify the observation stops and records the appropriate error/outcome.
- Replay an already committed event to verify duplicate metrics increment while business apply does not.

## 11. Common Implementation Pitfalls

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Actuator present but no traces visible | Missing tracing implementation/exporter, sampling, or collector | Check dependencies, exporter endpoint, sampling rate, collector |
| `ObservationRegistry` present but no business metrics | Missing meter handler, observation never stopped, missing registry/exporter | Check lifecycle, handlers, and `/actuator/metrics` |
| WebClient lacks trace headers | Client created outside Boot's builder or no active trace context | Inject Boot-managed `WebClient.Builder` and check propagation |
| Spring Integration flow lacks observations | Missing `@EnableIntegrationManagement(observationPatterns=...)` or registry | Check component names/patterns and version conditions |
| Spans break across thread boundaries | Thread-local context not propagated | Check executor, Reactor context propagation, adapter transport |
| Timer shows microseconds despite slow HTTP | Timed **`Mono` creation** instead of subscription | Use HTTP client instrumentation or reactive lifecycle operators |
| Bad p95 yet trace not found | Sampling retains only a fraction of traces | Check metrics/logs; adjust sampling in a controlled way |
| Metric store uses excessive memory | Names/tags contain per-request IDs | Bound cardinality, normalize routes/endpoints |
| Database pool metrics exist without SQL spans | Query layer not instrumented | Add supported JDBC/R2DBC instrumentation |
| Added `@Observed` but metrics duplicate | Manual/annotation instrumentation layered over auto-instrumentation | Remove one layer or separate distinct boundaries |
| Retries increase request count while "order failed" is low | Per-attempt metric vs. final outcome metric differ | Create separate dashboard panels for attempts and final outcomes |
| Traces visible but no audit/idempotency | Observation does not guarantee single-execution business effects | Use eventId, unique constraints, inbox/outbox, and transactional design |

## 12. Pre-Deployment Checklist

- [ ] Three-signal architecture in place: logs, metrics, traces, each with appropriate backend and retention policy.
- [ ] Use Boot-configured `ObservationRegistry` when instrumenting business logic.
- [ ] Stable observation names and low-cardinality tag sets defined; no IDs or secrets in metrics.
- [ ] Outbound HTTP uses Boot-managed builders to preserve instrumentation and propagation.
- [ ] For Spring Integration, `@EnableIntegrationManagement` and `observationPatterns` scope verified.
- [ ] Context propagation tested across threads, Reactor pipelines, and brokers per actual flow.
- [ ] Metrics separate retry attempts from final outcomes and business commit status.
- [ ] Alerts configured for error rate, latency, queue lag, outbox age, and DLQ as needed.
- [ ] Tests prove observations are stopped, errors recorded, and no high-cardinality metric labels are emitted.
- [ ] Actuator/collector/exporters secured; no secret payloads or PII sent in logs, spans, or tags.

**Remember:** Spring Boot and Micrometer provide a unified Observation foundation that lets multiple libraries emit metrics and traces under a shared standard. An integration flow is truly observable only when you **measure the right business boundaries, choose proper names/tags, propagate context across transports, and understand when an effect is committed**. Observation helps reveal problems so you can act, but it does not replace data contracts, transactions, retries, and idempotency.

## References

- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): `ObservationRegistry`, handlers, context propagation, annotations, and JDBC/R2DBC integration.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registries, metric instrumentation, and metric export.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, tracer implementations, OTLP, sampling, and HTTP propagation.
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): cross-checking dependencies and properties for the 3.x branch.
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): observation model and event recording.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): registry, context, handlers, conventions, cardinality, and metric conversion.
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): `@EnableIntegrationManagement`, `observationPatterns`, and observation conventions.
