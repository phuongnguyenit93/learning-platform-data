# OTLP gRPC Exporter in Spring Boot

The **OTLP gRPC exporter** is the component that sends telemetry from an application to an OTLP receiver using gRPC over HTTP/2. For distributed tracing, the exporter takes spans recorded by the OpenTelemetry SDK and turns them into OTLP requests sent to the OpenTelemetry Collector or a compatible backend. In Spring Boot, the exporter must be properly wired to Micrometer Tracing/Observation or the OpenTelemetry SDK to avoid creating multiple duplicate tracing pipelines.

In the **SPRING_BOOT_OBSERVABILITY** module, the exporter connects instrumentation to the telemetry ingestion system. This lesson belongs to the **Tracer implementation** chapter, focusing on dependency/version compatibility, creating the exporter, `BatchSpanProcessor`, `SdkTracerProvider`, `Resource`/samplers/propagators, Spring Boot integration, TLS/authentication, lifecycle/shutdown, the Collector, and troubleshooting.

## 1. What Does the OTLP gRPC Exporter Do?

The OpenTelemetry SDK creates spans while the application processes requests. The exporter sends the spans selected for recording by the SDK to the receiver.

```mermaid
flowchart LR
    A["Spring MVC / WebFlux instrumentation"] --> B["Micrometer Observation"]
    B --> C["Micrometer Tracing bridge"]
    C --> D["OpenTelemetry SDK"]
    D --> E["SpanProcessor"]
    E --> F["OTLP gRPC SpanExporter"]
    F --> G["Collector OTLP receiver"]
    G --> H["Processors / Exporters"]
    H --> I["Trace backend"]
```

| Component | Responsibility |
| --- | --- |
| Observation/instrumentation | Detects operations to observe |
| Tracing bridge | Connects Micrometer Tracing to the tracing implementation |
| TracerProvider | Configures tracers, Resource, sampler, and processors |
| SpanProcessor | Handles span lifecycle, typically batching before export |
| SpanExporter | Sends spans to the receiver |
| Collector | Receives, processes, and forwards telemetry |
| Backend | Stores, indexes, and serves trace queries |

The exporter does not instrument controllers by itself, does not assign a Trace ID to every request on its own, and does not guarantee all spans are stored. Instrumentation, sampling, the processor, transport, and the backend must all work together.

## 2. OTLP gRPC vs. OTLP HTTP

OTLP can be transported over gRPC or HTTP. This lesson focuses on the gRPC exporter.

| Characteristic | OTLP gRPC | OTLP HTTP |
| --- | --- | --- |
| Transport | gRPC over HTTP/2 | HTTP request/response |
| Common default port | 4317 | 4318 |
| Exporter | `OtlpGrpcSpanExporter` | `OtlpHttpSpanExporter` |
| Endpoint | Target/URI per exporter API | URL typically includes `/v1/traces` |
| Proxy | Requires gRPC/HTTP2 compatibility | Requires standard HTTP routing |
| Payload | OTLP gRPC service calls | OTLP/HTTP protobuf or JSON |

Example gRPC target in a lab:

```text
http://otel-collector:4317
```

Example HTTP endpoint:

```text
http://otel-collector:4318/v1/traces
```

Do not append `/v1/traces` to a gRPC target. Both transports share the OTLP data model, yet one cannot be swapped for the other merely by changing the port or URL path.

## 3. Dependencies and Version Compatibility

With Spring Boot 3.x, an application can use the Micrometer Tracing bridge for OpenTelemetry and the OpenTelemetry SDK's OTLP exporter.

Maven dependencies example:

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

Use the Spring Boot BOM/parent and dependency management to select compatible versions. Avoid upgrading a single OpenTelemetry artifact independently past the version tested with the Micrometer bridge and Boot integration.

### 3.1. Checking the Dependency Tree

The goal when inspecting the dependency tree is to catch multiple versions of OpenTelemetry API/SDK/exporter coexisting, or an exporter missing from the runtime classpath.

Do not add an SDK manually if Spring Boot already auto-configures the tracing SDK unless you have defined a clear integration strategy. Two independent SDKs/providers can produce incompatible contexts, duplicate spans, or double exports.

### 3.2. Exporter Artifact vs. Bridge

- `micrometer-tracing-bridge-otel` connects Micrometer Tracing to OpenTelemetry.
- `opentelemetry-exporter-otlp` provides OTLP exporters.
- `opentelemetry-sdk` provides SDK providers and processors.
- `micrometer-registry-otlp` is a registry for Micrometer metrics, not a tracing exporter.

Adding the OTLP metrics registry does not ship spans. Adding the tracing bridge does not decide the endpoint/protocol on its own if no exporter is configured.

## 4. Creating OtlpGrpcSpanExporter

The OpenTelemetry Java SDK provides a gRPC span exporter. Example:

```java
import io.opentelemetry.exporter.otlp.trace.OtlpGrpcSpanExporter;
import java.time.Duration;

OtlpGrpcSpanExporter spanExporter =
        OtlpGrpcSpanExporter.builder()
                .setEndpoint("http://otel-collector:4317")
                .setTimeout(Duration.ofSeconds(10))
                .build();
```

The example endpoint uses plaintext in a lab network. Endpoint API and scheme behavior may depend on the exporter version; production should configure TLS and proper authentication.

The exporter has a lifecycle. When the provider shuts down, the processor/exporter must be flushed and released. Never create a new exporter per request.

### 4.1. Environment-Based Endpoint

You can externalize the endpoint via an environment variable:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

OpenTelemetry environment variables have specific semantics, and the exporter implementation must actually read them. If code explicitly calls `setEndpoint`, the builder/configuration value may take precedence. Do not assume every Spring Boot property automatically maps to a manual gRPC exporter.

### 4.2. Generic vs. Traces-Specific Endpoint

OpenTelemetry defines both a generic OTLP endpoint variable and per-signal variables in the SDK environment variable specification. For gRPC, do not append the HTTP signal path `/v1/traces` to the endpoint. Check your exporter/version semantics when using generic vs. traces-specific endpoints.

## 5. BatchSpanProcessor

You should not send each span individually the moment it finishes. `BatchSpanProcessor` buffers spans in a queue and exports them in batches to reduce network and exporter call overhead.

```java
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;

BatchSpanProcessor spanProcessor =
        BatchSpanProcessor.builder(spanExporter)
                .setScheduleDelay(Duration.ofSeconds(5))
                .setMaxQueueSize(2048)
                .setMaxExportBatchSize(512)
                .setExporterTimeout(Duration.ofSeconds(10))
                .build();
```

Method/API names may vary across OpenTelemetry SDK versions. These numbers are illustrative; measure traffic, span sizes, receiver latency, and memory limits before choosing production values.

| Parameter | Meaning |
| --- | --- |
| Schedule delay | Wait interval before the next scheduled export |
| Max queue size | Maximum number of spans buffered in the queue |
| Max export batch size | Maximum number of spans per batch |
| Exporter timeout | Time limit for a single export call |
| Shutdown flush | Attempts to ship remaining spans when the provider closes |

### 5.1. Full Queue and Dropped Spans

If the receiver is slow or unreachable, the queue can fill up. Once limits are exceeded, new spans may be dropped according to processor policy. Monitor exporter failures, queue utilization, Collector receiver metrics, and backend ingestion.

Increasing queue size is not a silver bullet: a larger queue consumes more memory and can prolong recovery spikes. Balance throughput, latency, memory, and acceptable telemetry loss.

## 6. Building SdkTracerProvider

`SpanExporter` connects to the SDK through a `SpanProcessor` registered on `SdkTracerProvider`.

```java
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.samplers.Sampler;

SdkTracerProvider tracerProvider =
        SdkTracerProvider.builder()
                .setResource(Resource.getDefault())
                .setSampler(Sampler.parentBased(
                        Sampler.traceIdRatioBased(0.10)))
                .addSpanProcessor(spanProcessor)
                .build();

OpenTelemetrySdk openTelemetry =
        OpenTelemetrySdk.builder()
                .setTracerProvider(tracerProvider)
                .setPropagators(
                        ContextPropagators.create(
                                W3CTraceContextPropagator.getInstance()))
                .build();
```

This is a standalone SDK example, not a full Spring Boot auto-configuration setup. `traceIdRatioBased(0.10)` selects root traces at the configured sampler ratio; parent-based behavior lets child spans follow the parent's sampling decision. Choose the ratio according to traffic and telemetry budget.

`Resource.getDefault()` obtains the SDK's default Resource. Real applications must attach service identity, version, and environment using the appropriate mechanism.

### 6.1. Resource Identity

Example Resource:

```text
service.name = order-service
service.version = 2.4.1
deployment.environment.name = staging
service.namespace = commerce
```

Resource attributes help the backend group spans by service and deployment. Never use request IDs, Trace IDs, or user IDs as Resource attributes, as they are high-cardinality or sensitive.

### 6.2. Propagators

`W3CTraceContextPropagator` injects and extracts `traceparent` and matching context. If the application uses Baggage, configure a propagator aligned with policy and transmit only permitted fields. The exporter does not handle propagation; instrumentation and propagators manage context transmission over HTTP.

## 7. Integrating with Spring Boot and Micrometer Tracing

Spring Boot can manage `ObservationRegistry`, the Micrometer Tracing bridge, tracers, and exporters via auto-configuration. When using the OpenTelemetry bridge, clarify how the exporter is provided to the tracing implementation.

Two main architectural paths:

1. **Spring Boot–managed tracing:** let Boot/Micrometer construct the tracer/provider and configure the exporter using extension points or properties supported by that version.
2. **SDK-managed tracing:** instantiate the OpenTelemetry SDK/provider/exporter yourself and wire it into Spring/Micrometer via an explicit bridge contract.

Do not mix both paths haphazardly. If you create a separate `OpenTelemetrySdk` while Boot already creates another SDK, instrumentation may use a different provider from the exporter you just built.

### 7.1. Avoiding Duplicate Spans

Symptoms when two tracing pipelines run concurrently:
- A single request produces two similar spans.
- The backend receives duplicate traces/spans.
- Trace IDs differ between log correlation and the exporter.
- Context propagation breaks inconsistently.
- Two exporters ship the same span.

Audit the Java agent, Boot auto-configuration, custom SDK beans, and the tracing bridge. Maintain a single clear tracing provider and ownership model for primary instrumentation.

### 7.2. Do Not Confuse Boot's OTLP HTTP Property with gRPC

Some Spring Boot OTLP tracing endpoint properties target OTLP/HTTP. Putting port 4317 into an HTTP property does not turn the exporter into gRPC. If you need gRPC, verify that your auto-configuration/version supports that transport or supply a gRPC exporter via a supported integration.

Do not treat `setEndpoint` in an SDK snippet as if Spring Boot calls that builder automatically. There must be an actual bean/configuration wired into the tracing bridge.

## 8. Creating a Spring Configuration for a Custom SDK

When intentionally managing the OpenTelemetry SDK yourself, you can declare a configuration bean and close the provider with Spring's lifecycle.

```java
@Configuration
class OpenTelemetryConfiguration {

    @Bean(destroyMethod = "close")
    SdkTracerProvider tracerProvider() {
        OtlpGrpcSpanExporter exporter =
                OtlpGrpcSpanExporter.builder()
                        .setEndpoint("http://otel-collector:4317")
                        .build();

        BatchSpanProcessor processor =
                BatchSpanProcessor.builder(exporter).build();

        return SdkTracerProvider.builder()
                .setResource(Resource.getDefault())
                .addSpanProcessor(processor)
                .build();
    }
}
```

This snippet illustrates the provider bean's lifecycle. It **does not by itself guarantee the Micrometer Tracing bridge uses that provider**. You must follow the integration/bean contract supported by your Spring Boot and Micrometer Tracing versions. Do not instantiate a second provider solely to configure a gRPC endpoint.

In production, externalize endpoint, TLS, timeout, Resource, and sampler settings via controlled configuration rather than hardcoding them.

## 9. TLS and Authentication

Production exporters typically need TLS or mTLS when transmitting across untrusted or shared networks. The backend may also require authentication metadata such as a bearer token or API key.

### 9.1. TLS

- Use a hostname matching the certificate SAN.
- The trust store must contain the required CA.
- Monitor expiration and rotation.
- For mTLS, the client must present its certificate and key.
- Never disable certificate verification to bypass errors.

TLS configuration APIs depend on the OpenTelemetry exporter version and gRPC channel setup. Do not copy HTTP client config blindly into a gRPC channel without verifying.

### 9.2. Authentication Metadata

The exporter may support headers/metadata or custom gRPC credentials. Exact mechanics depend on the SDK and backend.

- Never hardcode tokens in source code.
- Fetch secrets from a secret manager or deployment secret injection.
- Never log credentials or auth metadata.
- Use least-privilege credentials.
- Have rotation and expiration procedures.
- Distinguish TLS (securing the channel) from authentication (verifying client identity).

## 10. Timeouts, Retries, and Graceful Shutdown

Because the exporter ships telemetry over the network, it needs bounded timeouts and handling for transient failures.

| Scenario | Consequence | Operational Handling |
| --- | --- | --- |
| Receiver unavailable | Export fails | Monitor errors and retry per policy |
| Slow network | Batches delayed | Set sensible timeouts; inspect latency |
| Queue full | Spans may be dropped | Monitor queues; increase capacity within bounds |
| Backend throttling | Exports rejected/slowed | Tune rates, batching, and capacity |
| Process shutdown | Spans remain in queue | Flush/close provider per lifecycle |

Do not assume infinite retries or guaranteed delivery for every span. Retry behavior depends on the exporter implementation and version. Excessive backlogs increase memory usage and cause traffic bursts when the backend recovers.

### 10.1. Closing the Provider Properly

`SdkTracerProvider.close()` flushes the processor and releases the exporter cleanly. In Spring, declaring a bean with `destroyMethod = "close"` is one way to manage lifecycle when that bean truly owns the provider.

In Kubernetes, the termination grace period must be long enough for the application to shut down. If the process is forcefully killed before flushing finishes, spans still in the queue can be lost.

Never close the exporter after each request, and never synchronously flush on a request thread.

## 11. Configuring the OpenTelemetry Collector

The Collector accepts OTLP/gRPC on the common port 4317:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

The debug exporter is useful in a lab to confirm the Collector receives spans; it is not a trace storage backend. Production requires an exporter for your target backend along with proper TLS and authentication.

### 11.1. Verifying the Receiver

Check the Collector's startup logs to confirm the receiver bound the expected interface and port. From the application environment, the hostname and port must resolve and be reachable. Inside containers, `localhost` points to the current container, not another Collector container.

### 11.2. Collector Downstream Exporters

The Collector can chain batch, memory limiter, filtering, or resource processors before exporting. Verify the `traces` pipeline connects receivers, processors, and exporters. Metrics and logs require separate pipelines if you want to ingest those signals as well.

## 12. Sampling and the Exporter

The sampler decides whether spans are recorded/sampled per policy before export. The exporter only ships spans that reach the processor/export path; it cannot resurrect spans dropped by the sampler.

Head sampling decides early at the trace root. Parent-based sampling makes child spans honor the sampled decision from parent context. Tail sampling in the Collector can select traces after receiving spans, yet it cannot inspect spans that were already dropped at the application.

Distinguish between:
- No trace in the backend.
- The sampler dropped the trace.
- The exporter failed to send.
- A Collector processor dropped the trace.
- The backend failed to ingest/index/retain the trace.

Verify each layer using corresponding metrics and logs.

## 13. Security and Cardinality

The exporter transmits telemetry outside the process, so inspect and control its contents before sending.

Do not put into spans:
- Passwords, API keys, or bearer tokens.
- Cookie or Authorization headers.
- Raw request/response bodies containing PII.
- Query strings containing sensitive data.
- Customer identifiers without an approved business need.

Maintain an allowlist for Resource and span attributes, use route templates instead of raw IDs, and filter baggage by policy. TLS does not make sensitive data safe to store long-term in a backend.

Receiver ports must not be exposed publicly without proper authentication, TLS, and network policies.

## 14. Troubleshooting the OTLP gRPC Exporter

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| No spans visible in Collector | Exporter not created or sampler dropped | Check provider, processor, sampler |
| Connection refused | Wrong hostname/port or receiver not listening | Check Collector receiver and networking |
| `UNAVAILABLE` / deadline exceeded | Proxy, DNS, network, or overloaded receiver | Check HTTP/2 path, timeouts, and logs |
| TLS handshake failure | Wrong CA, certificate, or SNI/hostname | Check trust chain and certificates |
| `UNAUTHENTICATED` | Missing or invalid credential metadata | Check secret injection and auth config |
| Collector receives spans, backend is empty | Downstream exporter/pipeline failed | Check Collector pipeline and backend |
| Duplicate spans | Multiple providers/agents/exporters instrumenting | Check auto-config, Java agent, SDK beans |
| Trace ID differs between logs and backend | Multiple tracing contexts/providers | Check bridge, provider ownership, and MDC |
| Queue full | Receiver/backend slow or disconnected | Check queue, batching, retries, and ingest rate |
| Spans lost on shutdown | Provider not closed or short grace period | Check lifecycle and termination |
| Only metrics export succeeds | Confused metrics registry with tracing exporter | Check the dedicated span exporter |
| HTTP 404/405 | Used an HTTP path against a gRPC target | Verify protocol and endpoint |
| Traces missing Resource | SDK provider did not attach expected Resource | Check provider's Resource |
| No child spans | Downstream propagation/instrumentation inactive | Check propagators and client instrumentation |

### Debugging Workflow

1. Identify who owns the OpenTelemetry provider in the application.
2. Confirm `OtlpGrpcSpanExporter` is actually created and attached to a `SpanProcessor`.
3. Confirm the sampler permits spans to be recorded/exported.
4. Check endpoint, DNS, port, and gRPC/HTTP2 connectivity.
5. Check TLS certificates, authority, and authentication metadata.
6. Check `BatchSpanProcessor` queue, timeouts, and export errors.
7. Confirm the Collector receives spans and its downstream pipeline works.
8. Check backend ingestion, indexing, query filters, and time range.
9. Check for duplicate instrumentation and Trace ID correlation.
10. Verify shutdown flushing and absence of sensitive data.

## 15. Practice Exercise: Sending Spans with the OTLP gRPC Exporter

The goal is to configure a lab application that creates spans and sends them to a Collector using the gRPC exporter.

### Preparation

- A Spring Boot 3.x application.
- Micrometer Observation/Tracing or a standalone OpenTelemetry SDK with clear integration.
- Compatible OpenTelemetry OTLP exporter version.
- OpenTelemetry Collector with the gRPC receiver enabled.
- A trace backend or debug exporter in the lab.

### Step 1 — Enable the Collector Receiver

Configure the OTLP receiver on `0.0.0.0:4317`. In the lab, you can use the debug exporter to inspect received spans.

### Step 2 — Verify Dependencies

Use the appropriate BOM to align OpenTelemetry API/SDK/exporter and the Micrometer bridge. Confirm the exporter class is on the runtime classpath.

### Step 3 — Create the Exporter

Build `OtlpGrpcSpanExporter` pointing at the Collector endpoint. Set a suitable timeout. Do not include the `/v1/traces` HTTP path.

### Step 4 — Create Processor and Provider

Attach the exporter to `BatchSpanProcessor`, then attach the processor to `SdkTracerProvider`. Configure `Resource`, sampler, and W3C propagator according to lab requirements.

### Step 5 — Wire Instrumentation

Ensure Micrometer Tracing / Spring instrumentation uses the exact provider you configured. If Boot already manages another provider, pick a supported integration path before proceeding.

### Step 6 — Generate Requests

Send HTTP requests to an instrumented controller. Confirm a server span is created and selected by the sampler.

### Step 7 — Verify at the Collector

Inspect debug output or Collector receiver metrics. Confirm Trace ID, span name, service Resource, and timestamps.

### Step 8 — Test Connection Failures

Temporarily set a wrong hostname or port in the lab. Observe exporter errors; restore the valid endpoint and verify export recovers.

### Step 9 — Test Shutdown

Close the provider via proper lifecycle hooks. Confirm the final batch flushes during graceful application shutdown.

### Step 10 — Verify No Duplicates and Privacy

Confirm only one expected server span appears, Trace IDs stay continuous, no tokens/PII are present, and Resource identity is accurate.

### Acceptance Checklist

| What to Prove | Expected Outcome |
| --- | --- |
| OTLP transport | Distinguishes gRPC from HTTP |
| Exporter | `OtlpGrpcSpanExporter` created properly |
| Processor | `BatchSpanProcessor` wired to the exporter |
| Provider | `SdkTracerProvider` owns the processor |
| Spring integration | Instrumentation uses the intended provider |
| Sampling | Traces selected per policy |
| Propagation | W3C context links spans |
| Collector | Receives spans over gRPC |
| Security | TLS/auth configured for environment |
| Lifecycle | Flushes/closes cleanly on shutdown |
| No duplicates | No two tracing pipelines exporting the same span |
| Privacy | No secrets/PII exported |

## 16. Principles to Remember

1. **The OTLP gRPC exporter sends spans over gRPC/HTTP2**, typically to a receiver on port 4317.
2. **The exporter does not replace instrumentation or the sampler.** It only ships spans recorded by the SDK and passed through the processor.
3. **`BatchSpanProcessor` batches spans to cut overhead**, yet queue size, timeouts, and batch size must be tuned to traffic and memory.
4. **`SdkTracerProvider` ties together Resource, sampler, propagators, and span processors.** Configure the exact provider that instrumentation actually uses.
5. **Spring Boot/Micrometer bridge and the OpenTelemetry SDK need a clear ownership model.** Avoid parallel providers and duplicate spans.
6. **Do not confuse OTLP HTTP endpoint properties with a gRPC exporter.** Changing the port does not change the transport.
7. **Design TLS/authentication and secret rotation for production.** Never hardcode credentials or disable certificate validation.
8. **Lifecycle/shutdown affects data still in the queue.** Flush/close the provider properly and allow an adequate termination grace period.
9. **The Collector and backend are separate layers.** Spans reaching the Collector do not prove the backend stored and indexed them.
10. **Sampling and export failures are distinct causes.** Distinguish sampled-out traces, exporter errors, Collector drops, and backend ingest issues.
11. **Protect telemetry metadata.** Control Resource/span attributes, baggage, cardinality, and PII prior to export.

The OTLP gRPC exporter provides a transport channel for spans from the OpenTelemetry SDK to a Collector or compatible backend. When the exporter is wired into the provider used by Spring/Micrometer instrumentation, batching and timeouts are tuned properly, and TLS/auth/lifecycle are managed, distributed traces flow reliably through the pipeline. Verifying from span creation through the Collector and backend helps separate instrumentation, sampling, and export issues in real environments.
