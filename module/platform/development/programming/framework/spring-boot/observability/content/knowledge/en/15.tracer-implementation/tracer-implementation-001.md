# OpenTelemetry with OTLP

In the **Tracer implementation** chapter of the **SPRING_BOOT_OBSERVABILITY** module, **OpenTelemetry** is an implementation choice for distributed tracing in Spring Boot, while **OTLP (OpenTelemetry Protocol)** is the protocol that transports telemetry from the application to a Collector or observability system. By combining **Micrometer Observation**, the **Micrometer Tracing bridge for OpenTelemetry**, and the **OTLP exporter**, you can go from an HTTP request in the application to a trace composed of multiple spans in the backend, and then use that information to investigate errors, latency, and relationships between services.

It is important not to conflate the components: `ObservationRegistry` is not a Collector, OpenTelemetry is not a storage backend, and configuring OTLP **tracing** does not automatically export all **metrics** or **logs**. This lesson clearly explains the boundaries, how to configure it, end-to-end data verification, sampling, context propagation, tags/cardinality, and common mistakes when deploying in real environments.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **Micrometer Observation**, **Micrometer Tracing**, **OpenTelemetry**, **OTLP**, the **Collector**, and a **trace backend**.
2. Configure a Spring Boot 3.x application to export tracing spans using OTLP over HTTP to the OpenTelemetry Collector.
3. Understand the difference between the commonly used OTLP/HTTP port **4318** and the commonly used OTLP/gRPC port **4317**.
4. Create custom observations, record errors and appropriate trace attributes, and verify parent–child span relationships.
5. Explain the role of `traceparent`, `traceId`, `spanId`, and propagation across HTTP, threads, and reactive pipelines.
6. Choose sampling in the application and understand when the Collector can apply different processing policies.
7. Verify each hop: application → exporter → Collector → backend, without guessing from a YAML configuration alone.
8. Control metadata, cardinality, sensitive data, TLS/authentication, and trace storage costs.
9. Combine traces with metrics and logs to investigate a slow or failing request.

## 2. Component Map

These names frequently appear side by side, yet they solve different problems:

| Component | Responsibility | What It Is Not |
| --- | --- | --- |
| **Micrometer Observation** | Describes the lifecycle of an operation; provides names, key-values, events, errors, and scope. | A trace storage system or exporter. |
| **Micrometer Tracing** | Abstraction for creating spans, accessing the tracer/context, and linking instrumentation with a tracing implementation. | A network protocol for transporting telemetry. |
| **OpenTelemetry** | Ecosystem of APIs, SDKs, and semantic conventions for generating and processing telemetry. | By default, a long-term data storage system. |
| **Micrometer Tracing OpenTelemetry bridge** | Connects the Micrometer Tracing abstraction to the OpenTelemetry SDK/tracing implementation. | Automatically a Collector. |
| **OTLP** | Protocol for transmitting spans, metrics, or logs as distinct signals to a supported receiver. | A database or dashboard. |
| **OpenTelemetry Collector** | Receives, processes, batches, routes, and exports telemetry to backends. | Mandatory in every OTLP topology. |
| **Trace backend** | Stores and allows querying traces, such as Jaeger, Tempo, or a compatible system. | The Micrometer library inside the application itself. |

In a typical Spring Boot deployment:

~~~mermaid
flowchart LR
    User["HTTP Client"]
    Svc["Spring Boot service"]
    Observation["Micrometer Observation"]
    Bridge["Micrometer Tracing OTel bridge"]
    SDK["OpenTelemetry SDK / Span exporter"]
    Collector["Collector's OTLP receiver"]
    Backend["Trace backend"]
    Logs["Logs with traceId/spanId"]
    Metrics["MeterRegistry / metrics backend"]

    User -->|"Request + traceparent if present"| Svc
    Svc --> Observation
    Observation --> Bridge --> SDK
    SDK -->|"OTLP/HTTP or gRPC"| Collector --> Backend
    Svc --> Logs
    Observation -->|"Metrics handler if enabled"| Metrics
~~~

The diagram illustrates **independent yet linkable** flows. Tracing spans can be created from an observation; a metrics handler can measure the same operation; logs can carry trace context via MDC. Not every observation becomes a stored span: that also depends on the **tracing bridge, sampler, exporter, and backend**.

### What Data Model Is a Trace?

A **trace** consists of related **spans**. Each span describes a unit of work: a server handling an HTTP request, a database call, an outgoing HTTP client request, or executing a business step.

~~~text
Trace ID: 4f17c38a927d4b55a90714b02f8e6d19
└── SERVER GET /orders/{id}                780 ms
    ├── INTERNAL order.lookup                45 ms
    └── CLIENT POST inventory-service       690 ms
        └── SERVER POST /inventory/reserve   650 ms
~~~

In this hypothetical example, the trace helps pinpoint the time-consuming branch. However, nested durations **cannot be added arbitrarily**: a parent span encompasses the time of its child spans, and branches may execute concurrently.

- **Trace ID** links the entire trace together.
- **Span ID** identifies an individual span.
- **Parent span ID** indicates the parent–child relationship.
- **Attributes** describe details such as HTTP method, route, dependency, or outcome.
- **Status/events** can explain errors or notable milestones.
- **Resource attributes** describe the process/service, such as `service.name`.

## 3. Preparing Spring Boot and Dependencies

The examples in this lesson assume **Spring Boot 3.x** with Java 17 or higher, a Spring MVC application, and dependency versions managed by the **Spring Boot BOM**. Exact configuration may vary across minor releases, so verify the behavior in your running project.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Role of each dependency:

1. `spring-boot-starter-actuator` provides the Micrometer Observation infrastructure and common management/metrics integrations.
2. `micrometer-tracing-bridge-otel` is the bridge between Micrometer Tracing and OpenTelemetry.
3. `opentelemetry-exporter-otlp` provides the capability to send data to a compatible OTLP receiver; when Spring Boot auto-configuration is active, the application can export spans to the configured endpoint.
4. `spring-boot-starter-web` is only needed for the HTTP server example in this lesson; WebFlux, messaging, or batch applications have their corresponding integrations.

Do not add both the OpenTelemetry bridge and the Brave bridge simultaneously to the same pipeline just to get "more tracing." Choose one tracing implementation, manage versions consistently, and inspect the actual beans. Manually configuring a separate OpenTelemetry SDK alongside the SDK auto-configured by Spring Boot can create duplicate or competing pipelines.

### OTLP/HTTP Configuration for a Lab Environment

~~~yaml
spring:
  application:
    name: order-api

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Here:

- `spring.application.name` supplies the application name; check the `service.name` resource attribute in the trace backend to confirm the actual service name.
- `management.tracing.sampling.probability: 1.0` is used for a **low-traffic lab**, helping retain all spans for inspection. Do not treat this as a cost-safe default for production.
- `management.otlp.tracing.endpoint` points to an **OTLP/HTTP traces receiver**, typically using the `/v1/traces` path.
- `localhost` refers to the **application's host or network namespace**. If Spring Boot runs in one container and the Collector runs in another container, `localhost:4318` usually points back to the application container itself by mistake.

The application must be started with a compatible configuration, and the Collector/backend must be running at that address. A valid YAML file **is not sufficient proof** that the exporter has actually sent data.

## 4. OTLP Is a Protocol, Not Just Any URL

OTLP has different transport mechanisms. Distinguish them before configuring:

| Property | OTLP/HTTP | OTLP/gRPC |
| --- | --- | --- |
| Transport | HTTP, typically with protobuf payloads. | gRPC, typically using HTTP/2 and protobuf. |
| Commonly used port | **4318** | **4317** |
| Example address | `http://localhost:4318/v1/traces` | `http://localhost:4317` for a matching gRPC configuration. |
| Signal routing | Typically uses `/v1/traces`, `/v1/metrics`, `/v1/logs` paths. | Uses OTLP RPC services/protocols. |
| Verification | By HTTP response, receiver logs, and OTLP/HTTP-compatible tools. | By gRPC status, receiver logs, and OTLP/gRPC-compatible tools. |

**The port is not the absolute definition of the protocol.** A Collector can be configured to listen on a different port. However, you must ensure the exporter and receiver **use the same transport**. Do not simply change `4318` to `4317` in an HTTP URL and expect gRPC to work.

Three configuration mistakes are common:

1. **Wrong port/transport:** the exporter uses HTTP while the receiver only enables gRPC.
2. **Wrong path:** configuring the HTTP traces endpoint at root `/` instead of `/v1/traces`, depending on the exporter API.
3. **Wrong host:** a containerized application calls `localhost` instead of the Collector service's DNS name.

When an environment uses HTTPS/TLS or mTLS, configure the exporter and Collector appropriately; do not simply replace `http` with `https` while ignoring certificates and identity.

## 5. A Lab Collector to See Spans

An easy way to test the export path is to run an **OpenTelemetry Collector** with an OTLP receiver and a `debug` exporter. This is a **lab-only** setup that lets you read span data from the Collector's output; it does not yet store traces in a searchable backend UI.

Example `otel-collector.yaml` (illustrative; creating this file is not required in this lesson):

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

processors:
  batch: {}

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

If Spring Boot and the Collector run on the same host/network namespace, the loopback address in the example is appropriate. If they run in **two different containers**, the Collector needs to listen on the appropriate container network interface and the application sends to the Collector's service name, for example:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

In a containerized setup, the receiver typically needs to bind `0.0.0.0:4318` **inside a controlled container network** and must have appropriate network policies. Do not expose an unauthenticated receiver to the public Internet just for testing convenience.

Once you have the corresponding Collector binary, an illustrative run command is:

~~~bash
otelcol-contrib --config=otel-collector.yaml
~~~

The binary name depends on the installed distribution. On some installations, the binary is named `otelcol`; the Collector components and version must also be compatible with the configuration file.

**How to verify:** generate requests in the application, then inspect the Collector output to see whether spans and resource attributes from `order-api` appear. Debug output may contain sensitive data in attributes; only enable detailed verbosity in test environments, control read access, and do not use it as a long-term production pipeline.

### What Do You Need to Store Traces?

A production Collector typically exports onward to **Jaeger, Tempo, or a suitable backend** via an exporter supported by that backend. You need to configure receivers/exporters, authentication, TLS, retries, batching, resource limits, and appropriate retention. The Collector **is not automatically a long-term trace store**; with only the `debug` exporter, you have verified that the Collector receives spans, without a backend UI for historical investigation.

The Collector is also **not protocol-mandatory** if the exporter sends directly to an OTLP-capable backend. However, a Collector is often useful for centralizing processing policies, routing, security, and pipeline observability.

## 6. Creating a Custom Observation to Test Tracing

You can use Micrometer Observation without calling the OpenTelemetry SDK directly. Once the bridge and tracing handler are auto-configured, an observation with a complete lifecycle can become a tracing span.

Illustrative business service example:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderValidationService {

    private final ObservationRegistry registry;
    private final FraudGateway fraudGateway;

    public OrderValidationService(ObservationRegistry registry,
                                  FraudGateway fraudGateway) {
        this.registry = registry;
        this.fraudGateway = fraudGateway;
    }

    public Decision validate(OrderInput input) {
        return Observation.createNotStarted("order.validate", registry)
                .contextualName("validate order")
                .lowCardinalityKeyValue("operation", "validate")
                .lowCardinalityKeyValue("dependency", "fraud-gateway")
                .observe(() -> fraudGateway.evaluate(input));
    }

    public interface FraudGateway {
        Decision evaluate(OrderInput input);
    }

    public record OrderInput(String category, long amountMinorUnits) {}
    public record Decision(boolean accepted) {}
}
~~~

This is an example that can be placed into a Spring Boot project with the matching dependencies. The `FraudGateway` implementation is defined by the application. Key points:

- `order.validate` is a **stable name**; do not embed an order ID or request ID into the name.
- `operation` and `dependency` have a bounded set of values, making them suitable for low-cardinality metric tags and basic metadata.
- `observe(...)` manages `start`, scope, `stop`, and errors inside a synchronous lambda according to Micrometer conventions.
- If the tracer handler is configured, the resulting span can appear within the parent HTTP request trace.
- If the metrics handler is also active, the operation can emit timing metrics as well; do not confuse a timer metric with a single span.

When you need explicit lifecycle control, especially if you must attach an outcome based on the result:

~~~java
Observation observation = Observation
        .createNotStarted("order.validate", registry)
        .lowCardinalityKeyValue("operation", "validate");

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    Decision decision = fraudGateway.evaluate(input);
    observation.lowCardinalityKeyValue(
            "outcome", decision.accepted() ? "accepted" : "rejected");
    return decision;
} catch (RuntimeException exception) {
    observation.lowCardinalityKeyValue("outcome", "error");
    observation.error(exception);
    throw exception;
} finally {
    observation.stop();
}
~~~

This snippet illustrates the body of a method where `registry`, `fraudGateway`, and `input` are already defined. `openScope()` keeps the observation current on the synchronous thread, giving tracing and log correlation the active context; `stop()` completes the lifecycle. **Closing a scope and stopping an observation are two distinct operations.**

Do not call `start()` and then call `observe(...)` again on the same observation just to "make sure there is a span." Use **one** consistent lifecycle management style.

## 7. How Does a Trace Travel Across Services?

A distributed trace is linked via **context propagation**, not because the Collector happens to receive two spans with similar names.

With HTTP, W3C Trace Context typically uses `traceparent`. For example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: order-api
traceparent: 00-4f17c38a927d4b55a90714b02f8e6d19-3a9c31cdb4dcbd74-01
~~~

Where:

- `00` is the header format version.
- `4f17...` is the 32-hex-character trace ID.
- `3a9...` is the 16-hex-character parent span ID.
- `01` represents the tracing flags, typically related to the sampling decision.

A properly instrumented HTTP client can **inject** `traceparent` into an outgoing request; the downstream HTTP server **extracts** the context to create a server span belonging to the same trace. When multiple services do this correctly, the backend can display the client/server span relationships.

### Using an HTTP Client Configured by Spring Boot

In Spring Boot 3.2+ with Spring Framework's `RestClient`, the common approach is to inject a Spring Boot–managed `RestClient.Builder` rather than instantiating the client completely manually:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PricingClient {

    private final RestClient restClient;

    public PricingClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://pricing-service:8080")
                .build();
    }

    public Price fetchPrice(String sku) {
        return restClient.get()
                .uri("/api/prices/{sku}", sku)
                .retrieve()
                .body(Price.class);
    }

    public record Price(long minorUnits, String currency) {}
}
~~~

`pricing-service` is only an illustrative hostname; running this requires an actual service and a matching naming system. Spring Boot instruments the managed builder when the appropriate tracing/observability support is enabled. If code creates a `RestClient`, `RestTemplate`, or custom HTTP client outside the instrumentation mechanism, propagation **may not happen**.

To verify end-to-end:

1. Call an HTTP endpoint on `order-api`.
2. Inspect the trace ID in the logs or in the Collector/backend.
3. Verify that the request from `order-api` to `pricing-service` propagates the context properly.
4. Check that the backend shows both the **CLIENT span** and the related **SERVER span**, sharing the same trace ID and correct parent links.
5. If the two services produce two separate traces, inspect the instrumentation/propagator rather than tweaking the OTLP exporter before checking headers.

A Collector can receive spans from multiple services, but **it cannot repair broken parent–child relationships** if propagation was lost upstream.

## 8. Async, Reactor, and MDC: Boundaries Where Context Is Easily Lost

In synchronous processing, an observation scope usually allows code executing inside it to access the current tracing context. Across a thread pool, `CompletableFuture`, `@Async`, or Reactor, however, context may require additional propagation mechanisms.

A misleading example:

~~~java
Observation.createNotStarted("fraud.async", registry)
        .observe(() -> CompletableFuture.supplyAsync(
                () -> fraudGateway.evaluate(input)));
~~~

The lambda above may only measure **the time to create and schedule the task**, because the `CompletableFuture` completes after `observe(...)` has already closed the observation. If code on the worker thread does not carry the context, its spans may lose their parent or logs may miss the trace ID.

With async/reactive code:

- Align the observation lifecycle with **when the actual work executes and completes**.
- Use the context propagation utilities of the stack in use; do not hold an `Observation.Scope` open and pass it directly across arbitrary threads.
- With Reactor, remember that publishers can be lazy; creating a `Mono` does not mean the work has executed yet.
- Verify the context in logs on the executing thread, not just the original calling thread.
- When an operation is cancelled, errors, or times out, design proper completion/error cleanup to avoid dangling spans or lost data.

**MDC is not the canonical trace context.** MDC is typically where the logging framework reads `traceId` and `spanId`; inter-service propagation relies on carriers such as HTTP headers or message metadata. Copying a `traceId` string into logs does not automatically establish parent–child span relationships.

## 9. Correlating Traces with Logs

When Micrometer Tracing and logging integration are active, logs can carry `traceId` and `spanId` in MDC. Example log line (illustrative):

~~~text
2026-11-22T10:30:12Z WARN order-api traceId=4f17c38a927d4b55a90714b02f8e6d19 spanId=3a9c31cdb4dcbd74 Validation dependency slow
~~~

In some Spring Boot setups, log correlation is supported out of the box via built-in configuration. If you need to define a custom pattern, an example for a lab environment is:

~~~yaml
logging:
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-}]"
~~~

When changing the log pattern, check your logging configuration/version so you do not accidentally drop correlation fields provided by default. In production, structured JSON logs usually make querying by trace ID much more reliable than a parser reading free-form text.

A common investigation workflow:

1. Search error logs by service and timestamp.
2. Extract the trace ID from the log if present.
3. Look up the trace ID in the tracing backend to inspect the request path.
4. Read span durations, events, and errors to pinpoint where to investigate.
5. Use metrics to measure the impact across all traffic rather than relying on a single trace.

**If a trace is sampled out**, logs may still contain a trace ID or request ID from the active context, even though a complete trace will not be found in the backend. Logs are not automatically deleted just because the tracing sampler drops a trace.

## 10. How Does Sampling Change the Data You See?

Traces can become very large when a service handles many requests per second. **Sampling** is the mechanism for deciding which traces are collected/recorded, balancing cost and coverage.

In a low-traffic lab:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

In production, you might choose a smaller ratio, for example:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

This is only an **example of a 10% policy**, not a default recommendation for every system. The right ratio depends on traffic volume, SLOs, analytical value, backend cost, and the nature of rare incidents.

### Head Sampling in the Application

A tracing SDK can make its **sampling decision near the start of the trace**. With parent-based sampling, an upstream sampling decision propagated downward can influence the choice in child services. Therefore, setting `probability: 1.0` on a downstream service **does not necessarily** produce stored spans for every request that was unsampled upstream.

### Tail Sampling in the Collector

The Collector can be configured to process traces based on decisions made at the end of the trace, such as prioritizing traces with errors or high latency. However, to have the data needed for a tail-sampling decision, the relevant spans must **actually be sent to the Collector**. If the application's head sampler has already dropped the spans, the Collector cannot reconstruct what was never exported.

Tail sampling also requires managing memory, span wait windows, load balancing, and appropriate pipeline components. You cannot simply add one processor and assume you have every error trace.

### Are Metrics Sampled the Same Way?

No. Metrics such as HTTP request counts and latencies via `MeterRegistry` continue aggregating executions even when only a fraction of traces are retained. Therefore:

- Do not treat the number of stored traces as the exact request count for SLOs.
- Use metrics to find **frequencies, rates, and trends**.
- Use representative traces to understand **execution paths and dependencies**.
- Use logs to inspect specific events when a trace is no longer available.

## 11. Attributes, Tags, and Cardinality

In Micrometer Observation, there is a useful distinction:

- `lowCardinalityKeyValue(...)`: typically suited for bounded dimensions such as `operation=validate`, `outcome=success/error`, `dependency=fraud-gateway`. The metrics handler can use these to create metric labels.
- `highCardinalityKeyValue(...)`: intended for more detailed metadata in tracing when supported by the handler; not appropriate to turn directly into metric labels.

Example:

~~~java
Observation.createNotStarted("order.validate", registry)
        .lowCardinalityKeyValue("operation", "validate")
        .lowCardinalityKeyValue("outcome", "accepted")
        .highCardinalityKeyValue("business.reference", safeReference);
~~~

Here, `safeReference` is a value that **has already passed a privacy review**—not every available ID is allowed in a trace. High-cardinality trace attributes still incur indexing/storage costs and may be truncated or dropped by the exporter/backend according to policy. Do not put email addresses, access tokens, card numbers, request bodies, or personal data into spans by default.

### Safe Span Naming

Avoid:

~~~java
// Avoid: observation name varies per order.
Observation.createNotStarted("order.validate." + orderId, registry);
~~~

Use a stable name instead:

~~~java
Observation.createNotStarted("order.validate", registry);
~~~

Keeping names and attributes consistent across services makes backend searches easier and avoids high cardinality and cost. Tracing also has semantic conventions (for example, HTTP/DB attributes) that evolve across instrumentation versions; verify the actual attribute names before building fixed dashboards or span queries.

### Does an OTLP Exporter Solve Privacy Automatically?

No. It transports telemetry as configured and does not automatically sanitize sensitive data. You should control data **at the source**; if needed, add deliberate attribute filtering/redaction policies in the Collector and backend. Never assume a pipeline is safe simply because it uses OpenTelemetry.

## 12. Securing OTLP and the Collector

For a local lab, unencrypted `http://localhost:4318/v1/traces` may be acceptable when all components run inside an isolated development environment. In production, you must explicitly design transport security and access control:

| Risk | Mitigation |
| --- | --- |
| OTLP receiver exposed to the Internet | Bind only to internal networks and apply firewalls/network policies. |
| Spans traversing an unencrypted network | Use TLS/mTLS or protect the transport path according to architecture standards. |
| Unauthenticated clients | Enforce authentication/authorization at the receiver, gateway, or proxy. |
| Leaked tokens/certificates | Store in a secret manager, rotate regularly, and apply least-privilege permissions. |
| Attributes containing sensitive data | Restrict at instrumentation and Collector layers; audit payloads/samples. |
| Overloaded Collector | Configure batching, memory limits, retries/queues, and monitor dropped spans. |
| Excessive backend retention | Design appropriate retention, sampling, and query access controls. |

Do not hard-code real API keys or credentials into `application.yml` files committed to the repository. Choose exporter header configuration, certificate trust, proxies, or environment variables appropriate to your Spring Boot and OpenTelemetry SDK versions. **Do not disable TLS verification** as a permanent workaround when encountering certificate errors.

The Collector itself also needs observability: track received/sent/dropped data, exporter errors, queues, and CPU/memory. If the application is sending spans but the Collector pipeline is dropping data, looking at application logs alone will not be enough.

## 13. Verifying Traces End-to-End

A low-risk testing workflow:

### Step 1 — Verify Configuration

Check in the running test application:

- Actuator and `micrometer-tracing-bridge-otel` are present.
- The OTLP tracing exporter is auto-configured.
- `management.otlp.tracing.endpoint` points to the right OTLP/HTTP receiver.
- Sampling is set appropriately for the lab.
- The Collector has a traces receiver and a pipeline with the appropriate exporter.

### Step 2 — Generate Real Traffic

Call an instrumented HTTP endpoint:

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

The address is an example; the endpoint must actually exist in your test application. You may want to call it a few times in case some requests are sampled out or still queued before reaching the Collector/backend.

### Step 3 — Inspect the Application and Collector

Look for these signs:

- The HTTP request executed and produced expected logs.
- Logs include trace ID / span ID when logging correlation is active.
- The Collector debug output receives `ResourceSpans`, `Span`, or equivalent entries with `service.name=order-api`.
- Attributes and operation names look reasonable and contain no sensitive data.

**Seeing data in the Collector proves it crossed the exporter/receiver hop**, not that the backend stored or indexed it successfully.

### Step 4 — Check the Trace Backend

If the Collector is connected to a backend:

1. Search for service `order-api` and the timestamp of your test request.
2. Look up the trace by the ID from the logs or from the trace list.
3. Verify the server span and the custom `order.validate` span, if that code path ran.
4. If an instrumented dependency was called, check that the client/server spans share the same trace ID and have sensible parent/child relationships.
5. Inspect duration, status, errors/events, attributes, and resource metadata.

### Step 5 — Cross-Check with Metrics

If the application has a metrics observation handler and an appropriate `MeterRegistry`, look up timing metrics for HTTP and the custom operation. Do not expect trace counts to match request counts; sampling and the tracing pipeline cause them to differ.

To view metrics via Prometheus, you must add the corresponding **metrics registry/exporter** and scrape endpoint. **An OTLP tracing exporter is not a Prometheus registry.**

## 14. Common Troubleshooting Table

| Symptom | Likely Cause | How to Verify |
| --- | --- | --- |
| HTTP metrics exist, no traces | Missing tracing bridge/exporter, sampler dropping traces, or misconfigured Collector/backend. | Check dependencies, sampling, and the tracing pipeline separately. |
| No spans visible on Collector | Wrong endpoint, port/transport/path, DNS/network, TLS/auth, or exporter not initialized. | Verify app→receiver connectivity and Collector listener/logs. |
| Sending HTTP to port 4317 fails | Port 4317 receiver is typically OTLP/gRPC, not OTLP/HTTP. | Use matching transport; HTTP usually targets `4318/v1/traces`. |
| Collector receives spans, backend is empty | Pipeline lacks a backend exporter, exporter errors, or backend filtering/indexing delay. | Inspect pipeline config, Collector exporter errors, and backend ingestion. |
| Incorrect service name | Resource attributes/config differ from expectations. | Check `service.name` in the Collector/backend payload. |
| Two services produce two separate traces | Missing `traceparent`, uninstrumented client/server, or context lost across async boundaries. | Inspect HTTP headers, tracing scopes, and executor/Reactor context. |
| Logs lack trace ID | Logging pattern/MDC, tracing integration, or scope not active. | Check logging config and an actually instrumented request. |
| Custom span missing or detached from parent | Observation did not run full lifecycle, no scope opened, or code ran outside context. | Check `observe`/`start/openScope/stop` and context propagation. |
| Traces appear intermittently | Sampling, batching, network/exporter retries, or very low traffic. | Test in lab with appropriate sampling; observe Collector/backend over time. |
| Trace contains sensitive data | Instrumentation puts PII/credentials into attributes, logs, or headers. | Audit instrumentation, Collector filtering, and access controls. |
| Collector overloaded, dropping spans | High traffic, queue/backpressure, or memory limits. | Monitor dropped spans, retries, batching, and resource usage. |
| Increasing sampling to 1.0 still misses some traces | Upstream parent sampling, exporter/backend errors, or uninstrumented requests. | Check trace flags, end-to-end instrumentation, and Collector logs. |

### Don't Fix the Wrong Layer

If **no span is created**, changing the OTLP endpoint will not help. If **spans reach the Collector but not the backend**, adding a custom `Observation` will not fix backend exporting. If **spans exist but parent–child links are broken**, adjusting the sampler is no substitute for context propagation.

Find the **first boundary without evidence**, and fix the issue at that boundary.

## 15. Investigation Scenario: Slow Checkout After a Deploy

Suppose after a deployment, the P95 latency of `POST /checkout` rises from 250 ms to 1.4 seconds. The system consists of a gateway, an order service, and an inventory service, all exporting traces through an OTLP Collector.

A structured investigation approach:

1. **Confirm scope with metrics:** check request rate, 5xx rate, and P95 by route/service/instance. Do not look at just one request.
2. **Search logs for events:** timeouts, retries, "connection pool exhausted," trace IDs, and deployment timing.
3. **Query the tracing backend by trace ID:** pick a few slow requests, compare them against normal requests, and inspect the critical path.
4. **Read the waterfall:** if the client span to inventory is long, compare it with the server span in inventory. If duration increased only on the client side, check network, queues, connection pools, and retries before concluding the server is slow.
5. **Check trace completeness:** if the inventory server span is missing, inspect propagation and the exporter on inventory rather than assuming inventory never processed the request.
6. **Account for sampling:** a failing request might not have a retained trace. Use metrics/logs and Collector telemetry to identify where data is missing.
7. **Form a hypothesis and verify:** add metrics for pools/DB/service latency, then re-measure after making changes.

In this scenario, **OTLP only transports spans**. The investigative value comes from proper instrumentation, meaningful metadata, intact propagation, appropriate sampling, and a backend that stores the important spans.

## 16. Self-Check Exercises

### Exercise 1 — OTLP/HTTP or gRPC?

An application uses the endpoint `http://localhost:4317/v1/traces`, while the Collector only enables gRPC on port 4317 and HTTP on 4318. Why do no traces appear?

**Answer:** The application is sending an OTLP/HTTP-style URL to a gRPC port. Configure the exporter to use the matching gRPC transport or switch to the HTTP receiver and endpoint `http://localhost:4318/v1/traces`.

### Exercise 2 — Collector Has Spans, Backend Does Not

The Collector debug exporter prints spans for `order-api`, but the trace backend cannot find this service. Should you fix Micrometer Observation first?

**Answer:** No. Spans have already passed through the application and the receiver. Check the Collector pipeline/exporter to the backend, TLS/auth, data dropping, indexing/retention, and query permissions in the backend.

### Exercise 3 — Two Different Trace IDs

Service A calls Service B; both export spans to the same Collector, yet B's trace ID differs from A's. Did the Collector fail to stitch the traces?

**Answer:** A Collector generally cannot stitch two traces together if the upstream service did not propagate the parent context. Check `traceparent` on the HTTP call, client/server instrumentation, and context propagation across async boundaries.

### Exercise 4 — Metrics and Sampling

The system records metrics for 10,000 HTTP requests, while the trace backend has roughly 1,000 traces. Can you conclude that 9,000 requests were lost?

**Answer:** No. Tracing sampling ratios and exporter/collector behavior can cause the number of traces to be smaller than the request count. Metrics still aggregate all requests; cross-check the pipelines before drawing conclusions.

### Exercise 5 — Which Attributes Are Appropriate?

A team wants to add `customerEmail`, `requestId`, `operation=validate`, and `dependency=fraud-gateway` to every span and timer metric. How should this be handled?

**Answer:** `operation` and `dependency` can be low-cardinality key-values if their value sets are bounded. Email is sensitive data and must not be recorded arbitrarily into telemetry. Request ID has high cardinality and should not be placed in metric labels; only consider it in logs or trace attributes per policy. Not every span needs to carry all metadata.

### Exercise 6 — Why Is the Async Span Wrong?

An observation wraps a `CompletableFuture.supplyAsync(...)` call and finishes before the actual work completes. What is wrong?

**Answer:** The observation is measuring scheduling overhead rather than the full asynchronous work. Manage the lifecycle around the async task's completion, along with context propagation and proper cleanup on the execution context.

## 17. Checklist for Implementing OpenTelemetry with OTLP

- [ ] Choose **one** tracing implementation compatible with Spring Boot/Micrometer; do not mix bridges accidentally.
- [ ] Include Actuator, the Micrometer Tracing OTel bridge, and a compatible OTLP exporter.
- [ ] Verify the OTLP endpoint has the right **transport, host, port, path, and TLS/auth**.
- [ ] Only use `localhost` when the application and receiver share the appropriate network namespace.
- [ ] Ensure the Collector has a traces receiver and an exporter pipeline to the intended destination; use the debug exporter for labs only.
- [ ] Confirm `service.name`, operation names, and attributes appear clearly in the backend.
- [ ] Ensure custom observations have a complete lifecycle, with outcomes and errors handled properly.
- [ ] Verify HTTP/messaging context propagation preserves trace IDs and parent links across services.
- [ ] Verify async/Reactor context propagation so you do not accidentally measure only task creation.
- [ ] Choose sampling suited to traffic/cost; understand the impact of parent-based and tail sampling.
- [ ] Never use high-cardinality or sensitive fields as metric labels; enforce data policies on traces as well.
- [ ] Ensure logs include correlation fields when tracing context is active, while keeping the logging pipeline working independently.
- [ ] Provide observability for the Collector and trace backend covering export errors, dropped spans, and resource usage.
- [ ] Run an end-to-end test from a real request to the Collector and backend rather than only checking YAML configuration.
- [ ] During incident investigation, combine metrics to scope impact, logs for specific events, and traces for execution paths.

**Remember:** **OpenTelemetry** provides the tracing ecosystem, **OTLP** transports spans, the **Collector** processes and routes telemetry, and **Micrometer Observation** is how Spring Boot describes operations inside the application. Only when instrumentation, context propagation, sampling, exporters, and backends all work together does distributed tracing let you correlate requests across services and pinpoint root causes of errors or latency with concrete evidence.
