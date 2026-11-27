# OpenTelemetry Tracer Provider in Spring Boot

In the **Tracer implementation** chapter of the **SPRING_BOOT_OBSERVABILITY** module, the key question is not merely "how do we create a span?" but also **who supplies the Tracer, who decides sampling, who processes spans, and who sends data to the tracing backend?** In OpenTelemetry, these responsibilities are organized around the **TracerProvider**. Understanding this mechanism properly helps you configure Micrometer Observation, metrics, logs, and distributed tracing consistently in Spring Boot, avoiding multiple independent tracers or assuming that creating a span guarantees exporting a trace.

This lesson explains the **OpenTelemetry TracerProvider** (specifically `SdkTracerProvider`), its relationship to `Tracer` and `OpenTelemetrySdk`, how to configure it in Spring Boot via the **Micrometer Tracing bridge**, how to write a manual SDK example when genuinely needed, along with considerations for context propagation, samplers, exporters, cardinality, and correlating metrics–logs–traces.

## 1. Why Is a TracerProvider Needed?

In an ordering system, a single request may produce an HTTP server span, a business span `order.confirm`, an HTTP client span to the payment service, and a database span. If every library creates its own tracing setup, spans may not share the same Trace ID, may not use the same resource metadata, or may go to different exporters. A **consistently configured TracerProvider** supplies tracers that share the same infrastructure and tracing policies within a process.

```text
Spring Boot service
    |
    +-- HTTP instrumentation ---------+
    +-- Micrometer Observation -------+----> OpenTelemetry Tracer
    +-- Custom instrumentation -------+             |
                                                   v
                                           TracerProvider
                                                   |
                                        (SdkTracerProvider)
                                      /         |          \
                              Resource      Sampler     SpanProcessor
                                                           |
                                                    SpanExporter
                                                           |
                                                    OTLP / Collector
                                                           |
                                                   Tracing backend

W3C propagators: propagate trace context across HTTP/message boundaries
Metrics handlers and log correlation: independently configured signal paths
```

**Key distinction:** `TracerProvider` is neither a tracing backend nor a historical data store. It supplies `Tracer` instances; the SDK implementation manages sampling, span processing, and exporters. Data is only visible in the backend when span creation, sampling, export, and ingestion all work together.

## 2. Key Objects and Responsibilities

| Object | Role | Common Misconception |
| --- | --- | --- |
| `TracerProvider` | API providing `Tracer` instances by instrumentation scope | Mistaking it for a collector or backend |
| `Tracer` | API for creating spans for a library or component | Thinking a new tracer creates an isolated trace |
| `SdkTracerProvider` | SDK implementation managing tracers, resource, sampler, and span processors | Creating multiple uncontrolled SDK instances in the same app |
| `SpanBuilder` / `Span` | Creates an operation, attaches attributes/events/status, and manages lifecycle | Forgetting to close the span or scope |
| `Resource` | Metadata about the telemetry source: service name, environment, instance, etc. | Putting request ID or user ID into resource attributes |
| `Sampler` | Decides sampling at span creation time based on context/policy | Confusing sampling with dropping metrics or exporter errors |
| `SpanProcessor` | Receives lifecycle events for recording spans and prepares them for export | Confusing a processor with a propagator |
| `SpanExporter` | Sends span data outward (e.g., OTLP) | Thinking the exporter auto-instruments HTTP/JDBC |
| `ContextPropagators` | Defines how context is injected/extracted across transport boundaries | Assuming setting an exporter automatically sends Trace IDs across services |
| `OpenTelemetrySdk` | Bundles SDK providers and propagators for instrumentation to use | Thinking this is just an alias for `SdkTracerProvider` |

A `Tracer` is typically obtained from the provider using an **instrumentation scope name** such as `orders-business`, optionally with a version. The scope name identifies which library/component produces the telemetry; it is **not the service name**, nor is it a Trace ID. The service name lives in `Resource` and should remain stable per service.

### API Differs from SDK Implementation

OpenTelemetry separates **API** and **SDK**:

- **API** lets applications and libraries use `Tracer` and propagate context without committing to a specific exporter.
- **SDK** executes sampling, span processing, resource management, and export. `SdkTracerProvider` is the SDK implementation of the `TracerProvider` API.
- In an environment without an installed SDK/compatible tracing bridge, the API can operate in **no-op/non-recording** mode and export nothing. You cannot conclude tracing works merely because code compiles and `spanBuilder()` succeeds.

Examples in this lesson describe one common deployment path. Dependency names and auto-configuration properties may vary across Spring Boot/Micrometer/OpenTelemetry versions; always verify against your running stack.

## 3. Lifecycle of a Span Through TracerProvider

Suppose code creates a span for the `inventory.reserve` operation:

1. Instrumentation retrieves a `Tracer` from the provider.
2. `Tracer.spanBuilder("inventory.reserve")` creates a builder.
3. When `startSpan()` is called, the provider constructs span context using the current parent context and asks the **Sampler** whether to record/export.
4. If the span is recording, code can attach attributes, events, exceptions, and status.
5. Scope makes the span the **current span** for synchronous calls in the appropriate execution context.
6. `span.end()` completes the operation; the processor handles the finished span and the exporter can send the data out.

```text
TracerProvider
   |
   +--> Tracer
         |
         +--> SpanBuilder
                |
                +--> startSpan() -- Sampler decision
                       |
                       +--> makeCurrent() / Scope
                       |        |
                       |        +--> nested calls inherit parent context
                       |
                       +--> add attributes / recordException
                       |
                       +--> end()
                              |
                              +--> SpanProcessor
                                       |
                                       +--> Exporter --> Collector/backend
```

**Scope and span are distinct:** closing a `Scope` restores the previously active context; `span.end()` finishes the span. Closing a scope **does not automatically end** the span, and ending a span **does not restore** context. Both must be managed in the proper order.

A span may hold a valid Trace ID in context while being **non-recording** due to sampling; therefore, not every span creation call results in a record in the backend.

## 4. How Do Spring Boot and Micrometer Tracing Integrate?

In most Spring Boot applications using Actuator and **Micrometer Observation**, prefer letting **Spring Boot auto-configuration manage** the tracing infrastructure. Business code creates observations via `ObservationRegistry` or reads the current span via `io.micrometer.tracing.Tracer`; the OpenTelemetry bridge translates observation/tracing events into OpenTelemetry accordingly.

```text
Spring Boot instrumentation / custom Observation
                  |
                  v
        Micrometer ObservationRegistry
                  |
                  v
      ObservationHandler / Micrometer Tracing
                  |
                  v
        micrometer-tracing-bridge-otel
                  |
                  v
            OpenTelemetry SDK
        (SdkTracerProvider / propagators)
                  |
                  +--> OTLP exporter --> collector/backend
                  |
                  +--> trace context --> downstream HTTP/message
```

**Do not mix up the APIs:** `io.micrometer.tracing.Tracer` is the Micrometer Tracing abstraction; `io.opentelemetry.api.trace.Tracer` is the OpenTelemetry API. Both can participate in the same pipeline once the bridge is set up, but they are used differently. Avoid importing the wrong one and treating the two types as directly interchangeable.

### Dependency Example

A reference combination for Spring Boot versions supporting **Micrometer Tracing + OpenTelemetry bridge + OTLP exporter**:

```xml
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
</dependencies>
```

This example assumes the Spring Boot parent/BOM manages compatible versions. Across Spring Boot generations with newer starters and tracing configuration, check actual dependencies; do not arbitrarily combine two different bridges or create multiple SDKs just to "make sure traces appear."

### Application Configuration Example

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

In a Spring Boot stack supporting these properties, this configuration requests an approximate 10% head-based sampling probability per tracer policy and points to the collector's OTLP/HTTP endpoint. This is an **example**, not an optimal sampling rate or a guarantee that exactly 10% of traces appear.

- `spring.application.name` is typically the source for setting the service name in auto-configuration, but **verify the actual resource attributes** in the tracing backend.
- `management.otlp.tracing.endpoint` only takes effect when the matching dependencies, exporter, protocol, and auto-configuration are active.
- Port 4318 and `/v1/traces` are commonly used for OTLP/HTTP; OTLP/gRPC configurations typically use a different endpoint and protocol.
- Inside a container, `localhost` refers only to the running container's network namespace, not automatically to a collector in another container or pod.
- Span delivery also depends on the collector/backend pipeline, network security, retention, and sampling.

**Design recommendation:** if Spring Boot manages the SDK/provider, **do not simultaneously call** `OpenTelemetrySdk.builder()`, `GlobalOpenTelemetry.set(...)`, or construct a second `SdkTracerProvider` wired into the same HTTP/Observation handlers. Doing so easily creates inconsistent resources, samplers, propagators, and exporters.

## 5. Custom Observation Example in Spring Boot

A business step such as `order.confirm` should be instrumented with Micrometer Observation to unify metrics and tracing (when corresponding handlers are configured):

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationService {
    private final ObservationRegistry registry;
    private final OrderGateway gateway;

    public OrderConfirmationService(
            ObservationRegistry registry,
            OrderGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public void confirm(OrderCommand command) {
        Observation.createNotStarted("order.confirm", registry)
                .lowCardinalityKeyValue("channel", command.channel())
                .observe(() -> gateway.confirm(command));
    }
}
```

`OrderGateway` and `OrderCommand` are application-defined domain types, not part of Micrometer. `channel` should be normalized to a bounded set of values such as `web/pos/partner` before being used as a low-cardinality tag; never pass a raw client-supplied header directly.

When `ObservationRegistry` has a tracing handler via Micrometer Tracing and the OpenTelemetry bridge, this observation **can generate a business span** beneath the active HTTP server span. When a metrics handler is present, it can also record operation duration and counts. With only an empty registry and no handlers, the code still runs without automatically producing tracing/backend telemetry.

At the domain layer, there is no need to know which constructor built `SdkTracerProvider`. The configuration layer owns the provider, resource, sampler, and exporter; domain code owns observation **boundaries and semantics**.

## 6. Building SdkTracerProvider Manually When Genuinely Needed

There are cases where a standalone application, test tool, or bootstrap library **explicitly owns** the entire OpenTelemetry SDK without relying on Spring Boot auto-configuration. In those cases, you can build the provider manually. The snippet below illustrates a **standalone** flow—do not place it verbatim alongside the Spring Boot configuration from Section 4.

To compile, you need compatible versions of the OpenTelemetry API/SDK modules and OTLP exporter; dependency versions are managed by your stack's BOM. Class/import paths may change across versions.

```java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.api.baggage.propagation.W3CBaggagePropagator;
import io.opentelemetry.context.propagation.TextMapPropagator;
import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.samplers.Sampler;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import java.util.concurrent.TimeUnit;

public final class StandaloneTracingExample {
    public static void main(String[] args) {
        var exporter = OtlpHttpSpanExporter.builder()
                .setEndpoint("http://localhost:4318/v1/traces")
                .build();

        var serviceResource = Resource.getDefault().merge(
                Resource.create(Attributes.of(
                        AttributeKey.stringKey("service.name"),
                        "standalone-orders")));

        SdkTracerProvider provider = SdkTracerProvider.builder()
                .setResource(serviceResource)
                .setSampler(Sampler.parentBased(
                        Sampler.traceIdRatioBased(0.1)))
                .addSpanProcessor(
                        BatchSpanProcessor.builder(exporter).build())
                .build();

        OpenTelemetry otel = OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .setPropagators(ContextPropagators.create(
                        TextMapPropagator.composite(
                                W3CTraceContextPropagator.getInstance(),
                                W3CBaggagePropagator.getInstance())))
                .build();

        try {
            Tracer tracer = otel.getTracer("orders-instrumentation", "1.0");
            Span span = tracer.spanBuilder("inventory.reserve").startSpan();
            try (Scope ignored = span.makeCurrent()) {
                // Perform the measured work here.
                span.setAttribute("inventory.operation", "reserve");
            } catch (RuntimeException ex) {
                span.recordException(ex);
                span.setStatus(StatusCode.ERROR, "reserve failed");
                throw ex;
            } finally {
                span.end();
            }
        } finally {
            // When an application that owns the SDK exits:
            provider.shutdown().join(10, TimeUnit.SECONDS);
        }
    }
}
```

### Analyzing the Design Decisions in This Example

**Resource:** `service.name=standalone-orders` describes the service **producing** the spans. `Resource.getDefault()` preserves default attributes when merging the service name. Never put `orderId`, Trace ID, or user ID into a resource: a resource is shared across many spans and must remain stable.

**Sampler:** `Sampler.parentBased(Sampler.traceIdRatioBased(0.1))` respects an existing parent decision while applying the sampling ratio to newly initiated root traces in the corresponding branch. Exact sampling behavior observed in the backend also depends on sampled flags, remote parents, and other samplers/collectors.

**SpanProcessor:** `BatchSpanProcessor` buffers and exports spans in batches to reduce overhead on the request path. It maintains a queue, flush schedule, and backpressure behavior; it **does not guarantee** all spans are exported if the process crashes or the collector fails. `SimpleSpanProcessor` is convenient in small tests, but synchronously exporting every span can introduce heavy overhead if misused in production.

**Exporter:** `OtlpHttpSpanExporter` sends data to an OTLP/HTTP receiver. If the endpoint does not exist or cannot be reached, spans may still be created without appearing in the backend. That is an **export path failure**, not proof that Trace IDs or `SpanBuilder` are broken.

**Propagators:** `W3CTraceContextPropagator` and `W3CBaggagePropagator` define how context is serialized into/out of transport carriers. They **do not send HTTP headers by themselves**; HTTP client/server instrumentation must invoke inject/extract on actual requests/messages.

**Lifecycle:** keep the provider alive for the lifetime of the application; shut it down gracefully during controlled process termination to release processors/exporters and flush pending spans. In Spring Boot, let Spring manage lifecycle instead of manually calling shutdown on a provider bean the framework still uses.

**Scope of example:** this code creates one span for illustration. In real code, work inside the scope may throw exceptions; record exceptions/status appropriately, handle errors per business contract, and always close scopes and spans. Never conclude the tracer works merely from seeing a Trace ID in logs.

## 7. Resource, service.name, and Instrumentation Scope

In a tracing backend, spans are grouped by service and instrumentation source. If resource configuration is wrong, finding traces by service becomes difficult even when spans arrive at the backend.

| Metadata | Level | Example | Policy |
| --- | --- | --- | --- |
| `service.name` | Resource | `orders-service` | Stable per service |
| `deployment.environment.name` | Resource | `staging`, `production` | Controlled set of values |
| `service.version` | Resource | `2026.11.22` | Matches release version |
| Instrumentation scope | Tracer/instrumentation | `orders-business` | Identifies the component producing spans |
| Span name | Single operation | `order.confirm` | Stable, no dynamic IDs |
| Span attributes | Single execution | `payment.provider=bank_a` | Mind cardinality, security, and SDK limits |
| Trace ID / Span ID | Trace/span context | Hex string per propagator | Never use as metric labels |

**Resource is not baggage.** Resource describes the source emitting telemetry. Baggage, when enabled for propagation, can travel across multiple services and must be bounded in size, keys/values, and sensitivity. Do not confuse the process's `service.name` with details about the calling client or end user.

With multiple instances, the backend may also use instance/pod/node metadata. Infrastructure labels must be governed so dashboards query accurately by service and environment without exploding metric cardinality.

## 8. Sampling Is Not Exporting, and Propagation Is Not Sampling

These are three decisions frequently conflated:

1. **Sampling:** decides which traces/spans are recorded or exported by policy. An unsampled trace may still carry trace context downstream depending on implementation.
2. **Propagation:** passes Trace ID, parent Span ID, and flags across HTTP/messaging/async boundaries so downstream continues the same trace.
3. **Exporting:** transmits recorded span data to a collector/backend; this can fail or be delayed due to network, queues, configuration, or backend issues.

```text
A request enters the service
        |
        +--> Propagator extracts traceparent
        |
        +--> TracerProvider creates span & Sampler decides
        |         |
        |         +--> recording span --> processor --> exporter --> backend
        |         |
        |         +--> non-recording span/context (per SDK)
        |
        +--> HTTP client injects context --> downstream
```

If `Sampler.parentBased(...)` respects an unsampled parent, downstream may export no spans even though the Trace ID propagated properly. If the exporter fails, even recording spans disappear from the trace viewer. If propagation breaks, downstream may generate a **new Trace ID**, even when both services have working providers and exporters.

These separate decisions also explain why **traces do not appear while metrics still do**: the metrics `ObservationHandler`/`MeterRegistry` operates independently of tracer sampling.

## 9. Propagation Across HTTP, Threads, and Messaging

### HTTP Between Services

With W3C Trace Context, a typical `traceparent` header has the structure:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             vv ----------------trace-id-------- --------span-id--- flags
```

This is a valid header format example: `trace-id` is 32 hex chars, `parent-id` is 16 hex chars, and flags follow the W3C specification. All-zero identifiers are invalid. HTTP instrumentation must inject/extract via compatible propagators so Service B receives Service A's trace context.

A properly configured `TracerProvider` **does not by itself guarantee** headers are always transmitted. For example, an HTTP client built outside auto-instrumentation, a proxy stripping headers, or a server failing to extract context can split a trace.

### Worker Threads and Asynchronous Execution

A span scope is normally bound to the active **execution context**. Submitting a task to another executor without context propagation can leave `Span.current()` or Micrometer `Tracer.currentSpan()` disconnected from the parent request span.

In Spring Framework versions that provide `ContextPropagatingTaskDecorator`, an executor can be configured to restore context when running tasks:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class TracingExecutorConfig {

    @Bean
    ThreadPoolTaskExecutor tracingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

This example depends on a Spring Framework version containing this class and the corresponding Micrometer Context Propagation setup. Actual tasks **must be submitted to this configured executor**; `CompletableFuture.runAsync(...)` without an explicit executor may run on the common pool and bypass the configured decorator.

### Messaging and Long-Running Workflows

With message producers/consumers, instrumentation must inject/extract context via message headers; hours later, a consumer may intentionally start a new trace and use span links or business correlation instead of stretching one trace indefinitely. Never stuff entire payloads, tokens, or personal data into baggage just to "preserve context."

## 10. Trace ID, Logs, and Metrics: Correlating Signals Properly

Suppose `POST /checkout` slows down because of the payment provider:

```text
Metrics:
  http.server.requests{uri="/checkout",status="500"} increases
  payment.authorize{provider="bank_a",outcome="error"} increases

Trace (if sampled and exported successfully):
  traceId=T
    POST /checkout                 spanId=A
      order.confirm               spanId=B
        payment.authorize         spanId=C
          HTTP POST provider      spanId=D (slow)

Logs (if MDC correlation is enabled):
  orders-service  traceId=T spanId=B "checkout failed"
  payment-service traceId=T spanId=C "provider timeout"
```

**Metrics** reveal error rates and latency trends across the entire system. **Traces** reveal the execution path of recorded sample requests, and **logs** explain specific error types and business conditions at each step. The tracing provider handles only part of this pipeline; correlation also requires propagation and logging integration.

Never put `traceId`, `spanId`, order ID, raw URL, email, or exception messages into **low-cardinality metric tags**. Those values have extreme cardinality, potentially creating millions of time series and high storage costs. In trace/log attributes as well, avoid secrets, enforce access control, and bound metadata.

A Trace ID is not an authorization credential and must not be used to grant access to traces or logs. Seeing a Trace ID in a log **does not prove** the backend holds that trace: sampling, exporters, collectors, or retention may prevent it.

## 11. Common Issues with TracerProvider

| Symptom | Cause to Investigate | How to Verify |
| --- | --- | --- |
| Activity logs exist, no spans in backend | Missing SDK/handler, sampler dropped, exporter not running, collector error | Check bridge, sampling, processor/exporter, and backend |
| Spans appear under `unknown_service` or unexpected name | Resource `service.name` unset or overridden wrongly | Inspect actual resource attributes in backend |
| Service A and B show different Trace IDs for same transaction | Missing HTTP/message propagation, proxy rewrite, task lost context | Compare W3C headers, client instrumentation, and executors |
| Single request produces two near-identical span trees | Duplicate instrumentation or multiple providers/agents | Inventory auto-instrumentation, Micrometer bridge, and OTel Java agent |
| HTTP spans exist, custom business spans missing | Observation not created, missing tracing handler/predicate, or wrong scope | Inspect registry, observation names, and tracing bridge |
| Exporting per span causes high overhead | Wrong processor choice or slow backend | Prefer batch processor; monitor queues/drops/latency |
| Trace has spans, logs lack Trace ID | MDC not populated or logged outside scope | Check logging pattern/encoder and context propagation |
| Span has Trace ID but `recording=false` | Sampler chose not to collect | Check sampling policy / parent sampling; do not treat as exporter failure |
| Running Spring Boot while manually creating another `SdkTracerProvider` | Two inconsistent configuration sources | Establish a single owner for the tracing pipeline and lifecycle |

Specifically with the **OpenTelemetry Java agent**: the agent can auto-instrument many libraries. If framework and library instrumentation are enabled at the same time in overlapping ways, duplicate spans or inconsistent context can appear. Do not disable or swap the agent arbitrarily; assign clear ownership of instrumentation per boundary, verify actual trace outputs, and choose a compatible strategy.

### Why Avoid Using `GlobalOpenTelemetry` Arbitrarily?

Some standalone OpenTelemetry libraries rely on a global instance. Inside auto-configured Spring Boot apps, replacing the global instance manually after instrumentation has initialized can leave components using different providers or create bootstrap-order-dependent behavior. Prefer Spring Boot's DI and tracing infrastructure; if building the SDK manually, create one consistent pipeline and define its lifecycle clearly from bootstrap.

## 12. Verification Workflow from Service to Backend

A working tracing pipeline must be verified across multiple layers, not only in Java code:

1. **Confirm dependencies and versions:** Spring Boot Actuator, Micrometer Tracing bridge, and OpenTelemetry API/SDK/exporter are aligned; no accidental second provider.
2. **Confirm resource:** `service.name`, environment/version, and instrumentation scope appear accurately in the backend without sensitive metadata.
3. **Verify sampling:** test environments may use a high probability to make traces easy to see; production needs a cost- and diagnostics-balanced policy.
4. **Trigger a simple operation:** invoke an HTTP endpoint containing a business Observation and verify span start/end, parent-child links, and duration.
5. **Verify propagation:** call a downstream service via an instrumented client; Trace ID stays consistent across services with valid Span IDs and parent links.
6. **Verify async:** run through an executor/message consumer with context propagation; check log correlation and trace links/parents if needed.
7. **Verify exporter/collector:** check OTLP endpoint, protocol, TLS/auth, queues, dropped spans, retries, and ingestion status.
8. **Cross-check metrics and logs:** match which time window metrics report errors/latency, whether logs contain the Trace ID, and whether the tracing backend finds the sampled request.
9. **Verify cost controls:** bound span attributes/events, sampling, batch processor settings, and metric cardinality, and ensure no secrets enter telemetry.

### Minimum Diagnostic Matrix

| Test | Expected Result |
| --- | --- |
| Call `TracerProvider.get(...)` or `OpenTelemetry.getTracer(...)` | Returns a `Tracer` for instrumentation; not enough to prove the exporter works |
| Create a span with scope and call `end()` | Produces a recording span for the processor if sampled and a compatible SDK is active |
| Collector unreachable | App can still run; exporter logs errors/drops or retries, trace backend is missing data |
| Low sampling probability | Fewer spans exported; metrics may still appear via separate handlers |
| HTTP client/server share propagator | Trace ID preserved across services, new Span ID and proper parent created |
| Worker executor lacks context propagation | Current span/trace may be lost or a new trace started |
| Custom Observation without tracing bridge | Observation may still feed metrics, does not emit OTel spans on its own |
| Wrong service name | Trace exists, yet filtering by the expected service name finds nothing |
| Two instrumentations wrap one DB call | May emit redundant overlapping spans; re-evaluate instrumentation boundaries |

## 13. Case Study Exercise

A team deploys `orders-service` (Spring Boot) and `payment-service`. They add `micrometer-tracing-bridge-otel`, declare an OTLP exporter, and also write a configuration class creating a new `SdkTracerProvider` with `service.name=local-test` and `Sampler.alwaysOn()`. During testing:

```text
orders-service log: traceId=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
payment-service log: traceId=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

Backend A:
  service.name=orders-service
  shows a few HTTP spans

Backend B:
  service.name=local-test
  shows spans created via manual OTel API

Metrics:
  http.server.requests continues reporting steadily
```

**Question:** Can you conclude the fault is sampling or the backend? In what order should you troubleshoot?

**Analysis Hints:**

1. **Insufficient evidence** to blame sampling: two providers/exporters likely created two independent pipelines with different service names, and HTTP propagation between the two services may also be broken.
2. Establish a **single owner** for the provider in the Spring Boot application. If using the Micrometer bridge and auto-configuration, remove the unnecessary manual SDK pipeline and use the framework-supported configuration.
3. Verify the `service.name` resource, sampling policy, processor/exporter, and OTLP endpoint/protocol on the retained pipeline.
4. Check `traceparent` across the HTTP client and server, especially if code uses a manually instantiated client or a proxy alters headers.
5. Verify that logs capture the active span context / Trace ID from that unified pipeline. Having an ID in a log does not guarantee all spans were exported.
6. Use low-cardinality metrics (provider/outcome, HTTP latency/error rate) to assess impact instead of putting Trace ID into metric labels to "fix" correlation.

**Conclusion:** **OpenTelemetry TracerProvider is the configuration root for Tracers within a process**, while `SdkTracerProvider` implements resource metadata, sampling, and span processors to export traces. In Spring Boot, prefer letting the Micrometer Tracing bridge and framework manage the provider when using auto-configuration; only construct the SDK manually when you intentionally own the entire pipeline. Propagation, exporters, logs, and metrics are collaborating layers: consistent configuration and end-to-end verification matter far more than simply creating a span in code.
