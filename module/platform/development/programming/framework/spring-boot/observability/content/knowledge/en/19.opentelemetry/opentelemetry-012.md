# Micrometer and OpenTelemetry: Combining Instrumentation in Spring Boot

> **Chapter:** OpenTelemetry  
> **Lesson:** Micrometer and OpenTelemetry  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Which Parts of Observability Do the Two Projects Solve?

In a Spring Boot application, development teams need to measure HTTP processing times, count orders, track database calls, and link traces across multiple services. Micrometer and OpenTelemetry frequently appear in the same architecture, yet they are not two names for the same library.

**Micrometer** provides a Java instrumentation facade, metrics and Observation APIs, and a registry ecosystem for exporting metrics to many backends. **OpenTelemetry (OTel)** defines standards and provides APIs/SDKs to generate, process, and export telemetry such as traces, metrics, and logs. Both ecosystems can integrate via bridges and exporters.

In Spring Boot, a helpful mental model is:

- Micrometer Observation provides an abstraction describing an observed operation.
- Observation handlers can turn one Observation into one or more signals, such as a meter and a span.
- Micrometer Tracing provides a unified tracing API that can connect to implementations like Brave or OpenTelemetry.
- OpenTelemetry API/SDK provides the OTel-standard tracing/metrics/logging model and corresponding processors/exporters.
- Exporters and registries determine which backend receives the data.

~~~mermaid
flowchart TD
  A["Spring Boot application"] --> B["Micrometer Observation"]
  B --> C["Observation handlers"]
  C --> D["Micrometer meters / MeterRegistry"]
  C --> E["Micrometer Tracing API"]
  E --> F["Brave bridge or OpenTelemetry bridge"]
  F --> G["Tracer / Span processor"]
  G --> H["OTLP or Zipkin exporter"]
  D --> I["Prometheus / OTLP / vendor metrics"]
  H --> J["Collector / tracing backend"]
  I --> K["Metrics backend"]
  J --> L["Trace backend"]
  K --> M["Dashboards and alerts"]
  L --> M
~~~

This diagram outlines several integration options. An application does not need every component installed at once. Choose your stack based on backends, instrumentation, standardization requirements, and operational policies.

## 2. What Is Micrometer?

Micrometer is an instrumentation library for the JVM, often described as a metrics facade. Applications use a stable API to declare `Counter`, `Timer`, `Gauge`, `DistributionSummary`, and other meters; concrete registries deliver measurements to their respective backends.

Example:

~~~java
Counter counter = registry.counter(
        "orders.created",
        "channel", "web");
counter.increment();

Timer timer = registry.timer("orders.processing.duration");
timer.record(() -> processOrder());
~~~

Business code does not manually craft HTTP requests to push metrics to a backend. `MeterRegistry` records the measurements, while the registry/exporter handles reading, aggregating, or pushing data per implementation semantics.

Micrometer also provides the **Observation API**. An Observation models an operation with a lifecycle: create, start, open scope, update context, report error, and stop. Observation handlers can convert that shared context into metrics or tracing.

### 2.1. How Do Meter and Observation Differ?

| Concept | Goal | Example |
| --- | --- | --- |
| `Meter` | Record a measurement or statistic | Counter of created orders |
| `Timer` | Measure count and duration | Payment processing duration |
| `Observation` | Describe the lifecycle of an operation | Calling the inventory service |
| `ObservationHandler` | Convert Observation context into signals | Metrics handler, tracing handler |
| `MeterRegistry` | Manage and export meters | `PrometheusMeterRegistry` |
| `Tracer` | Manage spans and trace context | Tracer from Brave/OTel bridge |

Not every meter needs a span, and not every span automatically creates a business-meaningful metric. Observation is the integration point that can use handlers to produce multiple signals from a single operation.

## 3. What Is OpenTelemetry?

OpenTelemetry is a suite of specifications, APIs, SDKs, and tools for generating, processing, collecting, and exporting telemetry. It defines data models and protocols to instrument polyglot applications and funnel telemetry through a unified pipeline.

Key parts:

- **OTel API:** interfaces used in code to create spans, metric instruments, context, and related primitives.
- **OTel SDK:** implementation handling recording, sampling, resources, processors, and exporters.
- **Instrumentation libraries:** libraries that automatically create spans/metrics for frameworks or clients.
- **OTLP:** protocol for transmitting telemetry to a Collector or supported backend.
- **Collector:** component that receives, processes, and forwards telemetry.
- **Semantic conventions:** naming and attribute conventions so telemetry stays consistent across libraries and languages.

Example using the OpenTelemetry API directly:

~~~java
Span span = tracer.spanBuilder("orders.create").startSpan();
try (Scope scope = span.makeCurrent()) {
    processOrder();
} catch (RuntimeException ex) {
    span.recordException(ex);
    span.setStatus(StatusCode.ERROR, "order processing failed");
    throw ex;
} finally {
    span.end();
}
~~~

This API creates and ends a span. To export the span to a backend, the application also needs a configured SDK/provider, sampler, processor, and exporter. Having the API on the classpath does not automatically mean data is recorded and shipped.

## 4. Comparing Micrometer and OpenTelemetry

| Criterion | Micrometer | OpenTelemetry |
| --- | --- | --- |
| Primary focus | Metrics and Observation instrumentation in the JVM | Multi-signal, multi-language telemetry standardization |
| Metrics abstraction | `Counter`, `Timer`, `Gauge`, `MeterRegistry` | Metrics API, `MeterProvider`, `Meter`, instruments |
| Lifecycle abstraction | `Observation` and `ObservationRegistry` | Tracing API/Span, context, and instrumentation APIs |
| Tracing in Spring | Micrometer Tracing facade and bridges | Trace API/SDK, Span, propagators, processors |
| Export | Backend-specific registries, OTLP registry, and bridges | Exporter/OTLP SDK, Collector |
| Resource identity | Registry/bridge mapping depending on integration | Resource model and semantic attributes |
| Spring Boot integration | Actuator, Observation, Micrometer registries/handlers | Via Micrometer OTel bridge, OTel agent, or SDK |
| Multi-language use | Micrometer instrumentation API is primarily JVM | Shared standard across languages and platforms |

**You do not always have to pick one and discard the other.** In Spring Boot, Micrometer is often the ergonomic instrumentation API deeply integrated with the framework; OpenTelemetry can serve as the unified telemetry standard and transport for the broader system.

However, clearly decide which component owns each instrumentation boundary. If both Micrometer Observation and the OTel Java Agent create spans for the same HTTP request, traces will show duplicate spans or confusing waterfalls.

## 5. Observation as the Key Bridge in Spring Boot

Spring Boot Actuator and Micrometer Observation provide a unified way to describe operations. For example, a service calling inventory can create an Observation:

~~~java
Observation.createNotStarted("inventory.reserve", registry)
    .lowCardinalityKeyValue("channel", "web")
    .observe(() -> inventoryClient.reserve());
~~~

The observation lifecycle can be illustrated as:

~~~mermaid
sequenceDiagram
  participant App as Application
  participant Obs as Observation
  participant MH as Metrics handler
  participant TH as Tracing handler
  App->>Obs: createNotStarted
  App->>Obs: start
  Obs->>MH: onStart
  Obs->>TH: onStart
  App->>Obs: openScope / execute
  Note over App: Business operation
  App->>Obs: error(ex), if any
  App->>Obs: stop
  Obs->>MH: onStop
  Obs->>TH: onStop
~~~

When matching handlers are registered:

- The metrics handler can create meters or record measurements from the Observation.
- The tracing handler can start a span, set the current span, attach attributes, and end the span.
- The error callback informs handlers that the operation failed.
- Scope makes the active context accessible during execution.

Do not assume every Observation emits both metrics and traces. Outcomes depend on registered handlers, predicates/filters, configuration, and supported context types.

### 5.1. Low-Cardinality and High-Cardinality Metadata

Observation lets you attach metadata by purpose:

~~~java
Observation.createNotStarted("orders.create", registry)
    .lowCardinalityKeyValue("channel", "web")
    .highCardinalityKeyValue("order.reference", reference)
    .observe(this::createOrder);
~~~

Low-cardinality values suit metric dimensions with bounded value sets. High-cardinality values can help locate a specific execution on a trace, though indexing, retention, and sensitive data must be evaluated.

Do not turn order ID, user ID, email, or request ID into a metric label. Attaching high-cardinality metadata to an Observation does not mean every handler/backend treats it identically; check actual mappings and policies.

## 6. Micrometer Tracing Bridge to OpenTelemetry

Micrometer Tracing is the tracing facade of the Micrometer ecosystem. A bridge connects that facade to a concrete tracer implementation.

One option in Spring Boot is the OpenTelemetry bridge, typically via:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
~~~

Another option is the Brave bridge:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-brave</artifactId>
</dependency>
~~~

These are mutually exclusive choices for the tracing implementation in a standard architecture. Do not add both as though two exporters were needed to send the same span.

With the OpenTelemetry bridge, the Micrometer Tracing API connects to the OTel tracer. Spring Boot can configure tracing integration so `Observation` creates spans. Exporters to Zipkin/OTLP and provider/resource setup depend on the specific stack.

### 6.1. Bridge Is Not the Same as the OTel Java Agent

A bridge is an adapter between two API/tracing abstractions. The Java agent is a JVM-level instrumentation/auto-configuration mechanism capable of instrumenting supported libraries automatically.

| Component | Role |
| --- | --- |
| Micrometer OTel bridge | Connects Micrometer Tracing to the OTel tracing implementation |
| OTel Java Agent | JVM-level instrumentation and autoconfiguration |
| OTel SDK | Creates providers, samplers, processors, and exporters |
| OTLP exporter | Ships spans/metrics/logs via OTLP |
| OTel Collector | Receives, processes, routes, and exports telemetry |

A system can use the bridge without the Java agent, or use the agent without adding the Micrometer bridge for instrumentation already covered by the agent. Avoid wrapping the same operation in two instrumentation systems.

## 7. Common Integration Models

### Model A — Spring Boot and Micrometer Metrics Registry

~~~text
Spring Boot
  -> Micrometer MeterRegistry
  -> Prometheus registry
  -> Prometheus scrape
  -> Metrics backend / dashboard
~~~

Suitable when the primary goal is metrics via Actuator/Prometheus and a unified OTel pipeline for traces/logs is not yet needed.

### Model B — Micrometer Observation/Tracing via the OTel Bridge

~~~text
Spring Boot Observation
  -> Micrometer Observation handlers
  -> Micrometer Tracing
  -> OTel bridge
  -> OTel SDK / span processor
  -> OTLP exporter
  -> OTel Collector
  -> Trace backend
~~~

Suitable when the application wants to use Spring's Observation API while exporting traces over an OpenTelemetry pipeline.

### Model C — OpenTelemetry Java Agent (OTel Java Agent)

~~~text
JVM + OTel Java Agent
  -> supported library instrumentation
  -> OTel SDK
  -> OTLP exporter
  -> OTel Collector
~~~

Suitable when rapid auto-instrumentation for agent-supported libraries is needed, especially without manually instrumenting every client.

### Model D — Intentional Hybrid

An application can use Micrometer for metrics and business Observations alongside the OTel bridge/SDK for tracing, while some teams also use the agent for libraries lacking custom instrumentation.

The condition is clear ownership assignment: does the framework or the agent create HTTP server spans? Does the builder or the agent create HTTP client spans? Which business Observations does code create? Which exporter ships them? Inspect real traces to eliminate duplication.

## 8. Configuring Spring Boot with Micrometer and OpenTelemetry

A minimal Maven example for Spring Boot 3.x using Actuator and the Micrometer OTel bridge:

~~~xml
<dependencies>
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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Configuration example:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

This example applies to Spring Boot 3.x and its matching dependency management. Verify property names and auto-configuration for your exact version. Minor versions and exporter options may differ.

Explanation:

- Actuator integrates management and Observation in Spring Boot.
- The OTel bridge connects Micrometer Tracing to the OpenTelemetry tracer.
- The OTLP exporter sends spans to the configured endpoint.
- Sampling probability selects a fraction of traces per policy.
- Service name is managed by Spring/Resource configuration; do not assume the exporter infers it accurately in every integration style.

In container environments, `localhost` may not point to the Collector. Use the proper network service DNS, e.g., `collector:4318`.

## 9. When to Use the OTel API Directly?

Not all code has to call the OTel API directly if a Spring Boot app standardizes on Micrometer Observation. Direct API usage helps when:

- An internal library is designed independently of Spring/Micrometer and needs OTel instrumentation.
- An application is polyglot or needs the standard OTel API across modules.
- A specific OTel feature lacks a corresponding Micrometer abstraction.
- The organization adopts the OTel API as its instrumentation contract for shared libraries.

OTel API example:

~~~java
Span span = tracer.spanBuilder("inventory.reserve").startSpan();
try (Scope scope = span.makeCurrent()) {
    return reserveInventory();
} catch (RuntimeException ex) {
    span.recordException(ex);
    span.setStatus(StatusCode.ERROR, "inventory reservation failed");
    throw ex;
} finally {
    span.end();
}
~~~

If the application already uses Micrometer Observation for the same boundary, calling the OTel API directly to create a second span can duplicate trace entries. Pick one API to own that operation, or wire a clear bridge/handler so it is not instrumented twice.

Never mix direct OTel API examples with Brave-specific code, as their classes and lifecycles differ. Use the interface matching your actual implementation.

## 10. Context Propagation Between Micrometer and OpenTelemetry

A cross-service trace requires trace context to persist during execution and be injected/extracted at transport boundaries.

Micrometer Observation/Tracing and OpenTelemetry each have context models, while the bridge connects contexts according to the integration. Do not maintain a custom `ThreadLocal` to replace framework context propagation.

~~~mermaid
sequenceDiagram
  participant A as order-service
  participant M as Micrometer Observation
  participant B as OTel bridge / context
  participant N as inventory-service
  A->>M: start observation
  M->>B: create/current span
  A->>N: HTTP call via instrumented client
  Note over A,N: Inject trace context headers
  N->>B: Extract context
  B-->>N: server span with parent context
  N-->>A: Response
  A->>M: stop observation
~~~

When using an instrumented HTTP client, outgoing requests carry W3C Trace Context or B3 headers per propagator config. The receiving server must support extracting the matching format. If context is lost across thread switches, child spans become root spans or split the trace.

### 10.1. Async and Reactive Execution

Thread context does not automatically cross every executor. With `CompletableFuture`, custom executors, or Reactor, use the context propagation mechanisms supported by Spring/Micrometer/OTel integration.

Ensure that:

- Context is captured at task submission time.
- Context is restored inside the callback/worker.
- Scope is closed on the right thread and lifecycle boundary.
- Observation/span stops only when the work actually completes.
- You never open a scope on thread A and close it on thread B.

Verify using trace ID, parent span ID, and duration. A log carrying a trace ID does not prove downstream HTTP requests propagated context properly.

## 11. Resource and Service Identity

OpenTelemetry Resource describes the telemetry-emitting entity. A resource typically includes attributes such as:

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
service.instance.id = pod-7f9c
~~~

Micrometer and Spring Boot can supply service identity to instrumentation/exporters depending on integration configuration. When using the OTel SDK or bridge, check where the resource is built and whether it merges cleanly with environment settings.

Do not confuse:

- Resource attribute: `service.name`, `service.version`.
- Span attribute: `http.request.method`, `db.system`.
- Observation key-value: metadata on an operation; handlers determine mapping.
- Metric attributes/tags: dimensions shaping time series.
- Baggage: metadata propagated along trace context when configured.
- MDC: process-local logging context.

Having the right service name on traces does not guarantee Prometheus metrics carry the exact same label; each pipeline builds resources/labels differently. Verify each signal individually.

## 12. Exporters, Registries, and the Collector

A Micrometer registry and an OpenTelemetry exporter are not the same thing:

| Component | Data | Model |
| --- | --- | --- |
| `PrometheusMeterRegistry` | Micrometer meters | Exposes endpoint for Prometheus scraping |
| OTLP `MeterRegistry` | Metrics | Pushes OTLP per registry configuration |
| OTel span exporter | Spans | SDK processor forwards spans to exporter |
| OTel log exporter | Logs | SDK/log bridge forwards log records |
| OpenTelemetry Collector | One or more signals | Receives, processes, batches, filters, routes, exports |

An architecture may use Micrometer's Prometheus registry for metrics and OTel's OTLP exporter for traces. That does not mean the same exporter ships both.

The Collector can aggregate, filter, or transform data. It does not replace in-app instrumentation and cannot synthesize business spans the application never instrumented.

### 12.1. OTLP Push vs. Prometheus Pull

- Prometheus pull: Prometheus actively scrapes the application's metrics endpoint.
- OTLP push: the application/exporter sends telemetry to the Collector or backend.
- Zipkin reporter: sends spans using the Zipkin protocol.
- Collector export: the Collector forwards telemetry down configured pipelines.

Do not use trace sampling settings to control metrics scrape intervals. Never point Prometheus scraping at an OTLP endpoint.

## 13. Avoiding Double Instrumentation and Duplicate Spans

A frequent error occurs when the same operation is instrumented by two sources.

For instance, an HTTP request might receive spans from:
- Spring Boot server instrumentation.
- OTel Java Agent.
- Custom OTel filter.
- Custom Micrometer Observation wrapping the same boundary.

If all run simultaneously, the trace can contain near-identical spans or unexpected parent-child nesting.

### How to Control It

1. List all automatic instrumentation active in the agent/framework.
2. Identify which boundaries are already instrumented by server/client libraries.
3. Add manual `Observation`s only for unmeasured business operations.
4. When custom attributes are needed, prefer enriching the existing Observation/span instead of nesting a second span with the same meaning.
5. Send a test request and inspect the waterfall by name, kind, parent ID, and duration.
6. Disable duplicate instrumentation one by one in a test environment to confirm span sources.

Do not delete instrumentation purely based on span count without understanding semantics; an HTTP client span and server span represent two sides of one request and are usually both valuable.

## 14. Sampling and Signal Consistency

Trace sampling can leave some requests without a stored trace in the backend while metrics still record all traffic. This is normal.

Micrometer metrics do not automatically scale down with tracing sampling probability. The OTel span sampler and metrics recording policies are separate components. Logs also have their own filtering and retention policies.

If the backend shows rising error `Counter`s yet few error traces:

- A head-based sampler may have dropped the trace early.
- The exporter/Collector may have dropped spans.
- The Observation may not have reported the error to the tracing handler.
- A parent sampling decision may have prevented recording child spans.
- Traces may exist under a different query, service name, or time window.

Metrics detect and quantify trends; traces reveal execution paths for sampled runs; logs record discrete events. Do not infer error rates from `ERROR` span counts unless sampling is accounted for.

## 15. Choosing a Stack for a Spring Boot Project

Decide based on requirements and operational maturity:

| Need | Common Choice |
| --- | --- |
| JVM/application metrics with Actuator | Micrometer `MeterRegistry` |
| Prometheus scraping | Micrometer Prometheus registry |
| Unified Observation for metrics and tracing | Micrometer Observation + handlers |
| Tracing aligned with OTel ecosystem | Micrometer OTel bridge or OTel API/SDK |
| Broad library instrumentation with minimal code edits | OTel Java Agent, if libraries are supported |
| Centralized export to multiple backends | OTLP and OpenTelemetry Collector |
| Framework-independent shared library | Standardized instrumentation API, often the OTel API |

### 15.1. Architecture Checklist

- One clear choice of tracing implementation.
- Consistent `service.name` and `service.version` resources.
- Clear instrumentation owner for every HTTP/database/messaging boundary.
- Business Observations have stable names and low-cardinality values.
- Uniform propagation format across services.
- Sampling sized to traffic and budget.
- Exporter/Collector configured with proper queues, timeouts, retries, and self-monitoring.
- Metric labels free of individual IDs.
- Logs carry trace/span correlation without leaking sensitive data.
- No duplicate spans from agent, framework, and custom instrumentation.

## 16. Real-World Scenario: Standardizing Observability for `order-service`

**Context:** a team runs Spring Boot `order-service`. Actuator already exports metrics via Prometheus. Some spans are produced by the OTel Java Agent; the team wants to add Observation for the order creation step and send traces to an OTel Collector.

### Step 1 — Inventory Current Instrumentation

Identify which server spans, HTTP client spans, and JDBC spans the agent already produces. Inspect active dependencies and configuration. Do not add duplicate custom spans around controllers or HTTP clients.

### Step 2 — Add Business Observation

~~~java
@Service
public class OrderService {
    private final ObservationRegistry registry;

    public OrderService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public String create(String channel) {
        return Observation.createNotStarted("orders.create", registry)
            .lowCardinalityKeyValue("channel", normalize(channel))
            .observe(() -> {
                reserveInventory();
                return "created";
            });
    }

    private void reserveInventory() {
        // Business operation.
    }

    private String normalize(String value) {
        return "web".equals(value) || "mobile".equals(value)
                ? value : "other";
    }
}
~~~

The business Observation models the order creation step. When a tracing handler is wired appropriately, it creates a span; a metrics handler records measurements per config. No second OTel span is needed on that same boundary.

### Step 3 — Keep the Existing Metrics Pipeline

Prometheus continues scraping the metrics endpoint. Traces flow through the OTel exporter/Collector. Both pipelines can share consistent resource/service identity while operating on independent collection schedules.

### Step 4 — Inspect the Trace Waterfall

Send a test request. The trace should show the server span, the `orders.create` span, and client spans for instrumented downstream calls. Confirm parent-child links, trace ID, durations, attributes, and absence of duplicate spans.

### Step 5 — Verify Signal Correlation

Metrics confirm request counts and latency; traces show processing steps; logs are searchable by trace ID when logging correlation is enabled. Confirm `service.name` matches and no order ID appears as a metric tag.

**Expected outcome:** business instrumentation managed by Observation, library spans created by the appropriate integration, and metrics/traces routed through separate pipelines with consistent resource identity.

## 17. Practice Exercises and Self-Check Questions

### Exercise A — Compare APIs

Write two ways to measure the same operation:
- Micrometer `Timer`/`MeterRegistry`.
- Micrometer `Observation` with a metrics handler.

Compare the code, lifecycle, and extra context a tracing handler can provide. Explain why a standalone meter does not automatically produce a full trace.

### Exercise B — Configure the OTel Bridge

Create a Spring Boot 3.x app with Actuator and the Micrometer OTel bridge. Configure a matching exporter/endpoint, emit a business Observation, and verify the span in the backend. Document resource and context propagation.

### Exercise C — Detect Double Instrumentation

Enable the OTel Java Agent and add a custom Observation wrapping an already auto-instrumented HTTP endpoint. Inspect the waterfall, identify which spans duplicate the boundary, and fix ownership. Keep client/server spans that carry distinct semantics.

### Exercise D — Separate Metrics/Traces Pipelines

Export metrics via Prometheus registry and traces via OTLP. Change trace sampling probability and observe:
- Does the request counter drop?
- Does the number of backend traces change?
- Does the Prometheus scrape interval change?
- Do logs follow trace sampling?

Explain why each signal maintains its own policy.

### Exercise E — Architecture Review

For a service using HTTP, JDBC, and a message consumer, build an instrumentation ownership table for each boundary. Specify which API is used, which bridge operates, which exporter ships data, resource attributes, and how context propagates.

### Self-Check Questions

1. Which parts of observability do Micrometer and OpenTelemetry solve?
2. How does a `Meter` differ from an `Observation`?
3. Does the OpenTelemetry API export telemetry on its own without an SDK/exporter?
4. How does an Observation handler turn lifecycle events into signals?
5. What is the role of the Micrometer Tracing bridge?
6. Should the Brave bridge and OTel bridge run together for the same tracer?
7. How does the OTel Java Agent differ from a bridge?
8. When should you use the OTel API directly in a Spring Boot application?
9. How do resource attributes differ from span attributes and metric labels?
10. Why might Micrometer metrics and OTel traces use different exporters?
11. How does lost context propagation affect the trace waterfall?
12. How do you detect duplicate spans from an agent and custom instrumentation?
13. Does trace sampling reduce Micrometer `Counter` values?
14. Does the OpenTelemetry Collector replace in-application instrumentation?
15. What must be verified to ensure metrics, traces, and logs share a consistent service identity?

**Completion criteria:** distinguish Micrometer metrics/Observation from the OTel API/SDK; explain bridges, handlers, exporters, and Collector; configure a Spring Boot stack; assign instrumentation ownership; understand resource and propagation; avoid duplicate spans; and separate trace sampling from metrics/logs.

## 18. Key Takeaways

- Micrometer provides metrics and Observation APIs integrated with Spring Boot; OpenTelemetry provides cross-language standards, APIs/SDKs, and telemetry pipelines.
- Observation describes an operation's lifecycle; handlers can turn it into metrics and spans when configured.
- The Micrometer Tracing bridge connects the Micrometer tracing facade to an implementation such as Brave or OpenTelemetry.
- The OTel Java Agent is an auto-instrumentation/autoconfiguration mechanism, not a bridge. Avoid instrumenting the same boundary twice.
- Resource describes the service/process emitting telemetry; span attributes describe operations; metric tags create dimensions; baggage propagates along context.
- Micrometer registries and OTel exporters can export different signals. Prometheus pull is not OTLP push.
- Context propagation and sampling must be coordinated across services; metrics and logs keep their own policies.
- Choose a stack based on needs, manage ownership, and inspect real waterfalls and resources; never draw conclusions from dependency lists alone.

## References

- [Micrometer Reference — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Reference — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [OpenTelemetry — Concepts](https://opentelemetry.io/docs/concepts/)
- [OpenTelemetry — Java instrumentation](https://opentelemetry.io/docs/languages/java/)
- [OpenTelemetry — OTLP](https://opentelemetry.io/docs/specs/otlp/)
