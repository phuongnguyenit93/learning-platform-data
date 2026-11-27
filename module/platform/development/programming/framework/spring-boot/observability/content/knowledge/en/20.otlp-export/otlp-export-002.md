# OTLP Traces: Exporting Distributed Traces From Spring Boot

A Spring Boot application can create Observations and spans for HTTP requests, yet operations teams still cannot find traces in the backend. The gap lies between **creating spans** and **exporting spans**: the tracing SDK must record spans, apply sampling, batch them, send them via OTLP, the Collector must receive and forward them, and finally the backend must store and make them queryable.

**OTLP (OpenTelemetry Protocol)** is OpenTelemetry's telemetry transmission protocol. **OTLP traces** is the signal used to transfer trace data consisting of Resource, instrumentation scope, and spans. With Spring Boot, Micrometer Observation and Micrometer Tracing can create spans; the OpenTelemetry bridge/SDK and OTLP exporter handle the export part according to configuration.

This lesson belongs to the **OTLP export** chapter of the **SPRING_BOOT_OBSERVABILITY** module: setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing, including context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and real-world application behavior.

## Learning Objectives

After this lesson, you will be able to:

1. Describe trace data structure and the path from Observation to the OTLP receiver/backend.
2. Distinguish OTLP/HTTP from OTLP/gRPC, along with commonly used endpoints and ports.
3. Configure Spring Boot/Micrometer Tracing to export spans using the OpenTelemetry OTLP exporter.
4. Set up an OpenTelemetry Collector to receive trace data, batch it, and forward it to a backend.
5. Understand SpanProcessor, batch queues, timeouts, retries, graceful shutdown, and risks of losing spans.
6. Distinguish export from trace context propagation, sampling, and metric/log exporters.
7. Test Resource, span hierarchy, and OTLP transport layer by layer.
8. Protect telemetry, control cardinality, and operate the traces pipeline in production.

## 1. What Are OTLP Traces?

A **trace** represents the path of a request or unit of work across one or more components. A trace contains one or more **spans**; each span describes an operation with start/end timestamps, span context, parent relationship, attributes, events, and status. When exported, spans are packaged together with **Resource** and **Instrumentation Scope** in the OTLP trace signal.

| Component | Meaning | Example |
| --- | --- | --- |
| Trace ID | Shared identifier of the trace | An order-creation request |
| Span ID | Identifier of one operation | HTTP server span |
| Parent Span ID | Direct parent span | HTTP client span calling downstream |
| Span name/kind | Name and role of the operation | `POST /orders`, `SERVER` |
| Attributes | Metadata of the operation | `http.request.method=POST` |
| Events | Milestone events inside the span | Exception event |
| Status | Outcome of the span | `OK`, `ERROR`, or `UNSET` |
| Resource | Telemetry emission source | `service.name=order-service` |
| Instrumentation Scope | Library that created the telemetry | Spring Web instrumentation |

A multi-service trace can contain spans with different Resources: `order-service` emits its spans, and `inventory-service` emits its own spans. Trace ID and parent relationships link them; Resource identifies the source that created each span.

### 1.1. OTLP Export Architecture

~~~mermaid
flowchart LR
    App["Spring Boot application"] --> Obs["Micrometer Observation"]
    Obs --> Bridge["Micrometer Tracing bridge"]
    Bridge --> SDK["OpenTelemetry SDK / TracerProvider"]
    SDK --> Processor["SpanProcessor / batch queue"]
    Processor --> Exporter["OTLP traces exporter"]
    Exporter --> Receiver["OTel Collector receiver"]
    Receiver --> Pipeline["Collector processors"]
    Pipeline --> BackendExporter["Collector exporter"]
    BackendExporter --> Backend["Trace backend"]
    Obs --> Metrics["Metrics handler"]
    Metrics --> MetricsBackend["Metrics registry/backend"]
    App --> Logs["Application logs"]
    Logs --> LogBackend["Log backend"]
~~~

**Having spans in code does not mean traces exist in the backend.** Each stage must be configured and verified independently.

OTLP can transport traces, metrics, and logs; each signal has its own data model, exporter, and endpoint. The OTLP trace exporter does not automatically export Prometheus metrics or Logback events. Even when going to the same Collector, all three pipelines still need matching receivers/processors/exporters.

## 2. OTLP Trace Data and Export Structure

In the OpenTelemetry Protocol, trace data is commonly represented through this structure:

~~~text
ExportTraceServiceRequest
└─ ResourceSpans
   ├─ Resource
   │  ├─ service.name
   │  ├─ service.version
   │  └─ deployment.environment.name
   └─ ScopeSpans
      ├─ InstrumentationScope
      │  ├─ name
      │  └─ version
      └─ Spans
         ├─ trace_id
         ├─ span_id
         ├─ parent_span_id
         ├─ name / kind
         ├─ start_time / end_time
         ├─ attributes
         ├─ events
         └─ status
~~~

This is a conceptual structure; the actual wire format is defined using Protocol Buffers. An OTLP receiver decodes requests according to the protocol, rather than reading arbitrary JSON with similar fields.

- **ResourceSpans** groups spans by the Resource that produced them.
- **Resource** contains `service.name`, `service.version`, environment, and runtime metadata.
- **ScopeSpans** groups spans by instrumentation scope.
- **Span** carries trace/span IDs, parent, timestamps, attributes, events, and status.

Resource indicates the telemetry emission source; instrumentation scope indicates the library that produced the telemetry. An `order-service` process can emit spans from Spring Web instrumentation and an internal library: their scopes differ while their Resource can be shared.

Do not put passwords, tokens, cookies, emails, request bodies, or payment data into span attributes. High-cardinality attributes inflate trace sizes and indexing costs; do not copy all baggage fields onto every span.

## 3. OTLP/HTTP and OTLP/gRPC

OTLP supports transport over HTTP and gRPC. Common default ports of the OpenTelemetry Collector:

| Property | OTLP/HTTP | OTLP/gRPC |
| --- | --- | --- |
| Default port | 4318 | 4317 |
| Transport | HTTP | gRPC over HTTP/2 |
| Trace endpoint | `/v1/traces` | gRPC service/method |
| Common payload | Protobuf (`application/x-protobuf`) | Protobuf |
| Metrics endpoint | `/v1/metrics` | gRPC service/method |
| Logs endpoint | `/v1/logs` | gRPC service/method |

### 3.1. OTLP/HTTP

The protocol's standard default traces endpoint is typically:

~~~text
http://collector:4318/v1/traces
~~~

The exporter sends an HTTP POST containing a protobuf payload. Illustrative request:

~~~http
POST /v1/traces HTTP/1.1
Host: collector:4318
Content-Type: application/x-protobuf

<binary ExportTraceServiceRequest>
~~~

This is a protocol illustration, not a copy-paste request to run with `curl`. The body must be valid protobuf or another format supported by the receiver per the OTLP specification.

### 3.2. OTLP/gRPC

With OTLP/gRPC, the exporter invokes a gRPC service over HTTP/2, typically on port 4317. Do not append `/v1/traces` to a gRPC URL as an HTTP path. The client and receiver must be compatible with gRPC/HTTP2, TLS, and proxies.

Choose HTTP or gRPC based on infrastructure: proxies/load balancers, service mesh, authentication, TLS, and your organization's observability stack. Do not assume default ports are always open; deployments can change them.

## 4. Configuring Spring Boot to Send OTLP Traces

Example Gradle dependencies for Spring Boot 3.x with the Micrometer Tracing OpenTelemetry bridge:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Roles:
- Actuator provides Spring Boot's observability integration.
- Micrometer Tracing bridge connects Micrometer to OpenTelemetry.
- OTLP exporter provides the telemetry sending mechanism.
- Prometheus registry (if used) serves metrics, not as a replacement for the tracing exporter.

Keep versions managed by the Spring Boot BOM. Do not pin Micrometer or OpenTelemetry API/SDK/exporter versions independently without verifying compatibility.

### 4.1. Configuring the OTLP/HTTP Endpoint

Example `application.yml` on a Spring Boot 3.x setup supporting OTLP tracing auto-configuration:

~~~yaml
spring:
  application:
    name: order-service
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Verify the endpoint property against your actual version. `probability` is head-based sampling in the integrated configuration, not tail sampling at the Collector.

### 4.2. Environment-Based Configuration

Do not hard-code `localhost` when deploying with separate containers. Use environment variables:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT:http://localhost:4318/v1/traces}
~~~

Example Collector Service DNS on Kubernetes:

~~~text
OTLP_TRACES_ENDPOINT=http://otel-collector.observability.svc.cluster.local:4318/v1/traces
~~~

The Service name is illustrative only. Use the actual host, namespace, port, and scheme. From inside the application container, `localhost` points only to that container/network namespace itself.

### 4.3. Resource Identity

Standard OpenTelemetry SDK Autoconfigure environment variables can be used when the tracing stack supports them:

~~~text
OTEL_SERVICE_NAME=order-service
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,service.version=2.4.1,deployment.environment.name=staging
~~~

These variables configure Resource identity, not span attributes. Verify whether the SDK/auto-configuration that Spring Boot actually uses reads those standard variables; not every provider configuration mechanism uses SDK Autoconfigure automatically.

### 4.4. Headers and TLS

When the Collector or gateway requires authentication, the exporter needs to send appropriate headers and TLS connections. How headers are configured depends on the Spring Boot/OpenTelemetry version and exporter implementation. Directional example for a version supporting the `headers` property:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT}
      headers:
        Authorization: ${OTLP_AUTH_HEADER}
~~~

Check the property binding for your exact version before using it in production. Credentials must come from a secret manager or protected environment; do not commit tokens to YAML. Use HTTPS/TLS, proper CAs, and hostname verification.

## 5. OpenTelemetry Collector: Receiving and Forwarding Traces

The Collector acts as an intermediary between applications and backends. It can receive OTLP, batch, filter by policy, and export to where traces are stored.

### 5.1. Experimental Collector Configuration

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  batch:
    timeout: 5s
exporters:
  debug:
    verbosity: basic
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [debug]
~~~

A Collector supporting these components will receive OTLP HTTP on 4318 and log data via the debug exporter. This is a learning configuration; do not use detailed debug logging in production because spans may contain sensitive data and generate large log volumes.

### 5.2. Backend Pipeline Configuration

When moving to production, use the actual exporter to your trace backend, while configuring auth, TLS, queue/retry, and policies. Example fragment for a Collector version supporting the `otlphttp` exporter and env expansion:

~~~yaml
exporters:
  otlphttp/backend:
    endpoint: https://trace-backend.example.internal
    headers:
      Authorization: ${env:TRACE_BACKEND_TOKEN}
~~~

In a complete configuration, declare the receiver/processor in their corresponding sections, wire the exporter in `service.pipelines.traces`, and check the exporter options of your Collector distribution. The hostname above is only an example.

### 5.3. Receivers Must Be Wired Into a Pipeline

Declaring `receivers.otlp` alone is not enough. `service.pipelines.traces` must reference the receiver, processors, and exporters. If the pipeline is not wired, the port may be open while trace data never reaches the intended destination.

In Docker/Kubernetes, the receiver must listen on a reachable interface; container networking, port mapping, DNS, network policies, and firewalls must be right. Do not use `localhost` for a Collector in another container. Check Collector readiness, health, and resources.

## 6. SpanProcessor, Batching, and Export Lifecycle

An ended span is not necessarily sent immediately. **SpanProcessor** receives span lifecycle callbacks and orchestrates processing:

- **SimpleSpanProcessor:** sends spans directly when they end; useful for testing/low traffic, but introduces synchronous overhead.
- **BatchSpanProcessor:** collects spans into a queue/batch and exports asynchronously; usually more suitable for production.

~~~mermaid
flowchart TD
    Span["Span ends"] --> Processor["SpanProcessor"]
    Processor --> Queue["Batch queue"]
    Queue --> Ready{"Batch size / timer / shutdown"}
    Ready --> Export["OTLP exporter"]
    Export --> Receiver["Collector"]
    Receiver --> Result{"Accepted?"}
    Result -- "Yes" --> Done["Batch completed"]
    Result -- "Transient error" --> Retry["Retry per policy"]
    Retry --> Export
    Result -- "Queue full / permanent error" --> Drop["Spans may be dropped"]
~~~

| Parameter | Impact | Trade-off |
| --- | --- | --- |
| Queue capacity | Number of spans waiting for export | Higher uses more RAM; lower drops easily during congestion |
| Max export batch size | Number of spans in one batch | Larger batches reduce request count but increase payload size |
| Schedule delay | Time to wait before flushing | Shorter reduces latency, increases overhead |
| Export timeout | Limit on how long the exporter waits | Too short may fail on slow networks |
| Retry/backoff | Retries transient errors | Can add load, does not guarantee delivery |
| Collector batch timeout/size | Groups data before sending to backend | Increases throughput, adds latency |
| Shutdown timeout | Time to flush on stop | Longer helps flush, extends shutdown duration |

Property names and BatchSpanProcessor configuration depend on the OpenTelemetry SDK/version and Spring Boot auto-configuration. Do not invent unsupported properties.

### 6.1. Graceful Shutdown

When an application stops, spans in the queue can be lost if the process is force-killed or the shutdown time is insufficient. Give the application a graceful shutdown window, let the SDK/span processor flush within the supported timeout, check exporter errors during rolling updates, and understand that an in-RAM queue is not durable storage.

Do not call synchronous flush on every request to "guarantee" traces are saved; doing so can make user latency depend on the Collector/backend.

## 7. Sampling and Trace Completeness

Sampling selects which traces are recorded/exported. Spring Boot can configure head-sampling probability:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

With head-based sampling, the decision is typically made early when the trace begins. If a request encounters an error seconds later but was dropped at the start, the OTLP exporter does not have a complete trace to send just because the final response was 500.

**Parent-based sampling** uses the sampling decision from the parent/remote parent as the basis for the child, helping services maintain consistency. W3C `traceparent` carries Trace ID, Parent ID, and trace flags. Sampling is not the same as baggage.

**Tail sampling** can wait for spans to reach the Collector and keep traces based on `ERROR` status, high latency, or other policies. It requires SDKs to send enough spans, routing spans of the same trace to the same decision point, sufficient Collector buffer/memory, and accurate attributes/status recorded by instrumentation. If the SDK already dropped a trace, the Collector cannot recover unexported spans.

A sampled set of traces, especially error-prioritized tail sampling, is not the default denominator for calculating error rates. Use HTTP metrics/counters/histograms for request rate, error ratio, p95/p99, and SLOs; use sampled traces to investigate specific requests.

## 8. Export and Cross-Service Propagation

OTLP export sends span data out to the Collector. **Propagation** passes trace context in requests so downstream services continue the same trace. The two activities must be configured separately.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Collector
    participant Backend
    Client->>Order: POST /orders
    Note over Order: Server span A
    Order->>Inventory: HTTP + traceparent
    Note over Inventory: Server span B, child of HTTP client span
    Inventory-->>Order: Response
    Order-->>Client: Response
    Order->>Collector: OTLP export order spans
    Inventory->>Collector: OTLP export inventory spans
    Collector->>Backend: Forward trace data
~~~

An illustrative W3C `traceparent`:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

The receiving service uses a propagator to extract context. If HTTP client/server instrumentation is configured properly, the `CLIENT` span and `SERVER` span share the same Trace ID and have the right Parent Span ID. The backend stitches spans together from each service's exported data.

When crossing threads via `@Async`/Executor or going through Reactor, context needs to be captured/restored. With Kafka/RabbitMQ, producer/consumer instrumentation needs to inject/extract context in headers. The OTLP exporter does not stitch parent-child links automatically if context was already lost; it only exports the spans that were created.

Trace context is shared, but Resource is not copied from upstream. Spans created by `inventory-service` must carry `inventory-service`'s Resource, such as `service.name=inventory-service`.

## 9. Testing OTLP Traces

You should test each layer to avoid confusing "Observation ran" with "trace reached the backend".

| Layer | How to Check | Evidence |
| --- | --- | --- |
| Observation | `TestObservationRegistry` | Name, tags, lifecycle, errors |
| Tracing SDK | In-memory span exporter/test handler | Trace ID, span ID, parent ID |
| OTLP transport | Test receiver that understands OTLP protobuf | Valid HTTP/gRPC request and payload |
| Collector | OTLP receiver + debug exporter | Collector received spans |
| Backend | Query trace by ID/service | Data ingested and searchable |
| Cross-service | Two instrumented services | Parent-child relationship and separate Resources |

### 9.1. Observation Unit Tests Do Not Prove Export

Tests using `TestObservationRegistry` can prove an Observation was created, has names/tags, and stopped properly. They do not send OTLP requests. A test creating a `Resource` object does not prove the Spring Boot provider actually used that `Resource`.

### 9.2. Testing Span Hierarchy in Memory

With an OpenTelemetry SDK test setup and an in-memory exporter:

1. Configure a sampler to keep spans during the test.
2. Create a parent span and a child span inside the parent's scope.
3. End both spans.
4. Collect spans via the in-memory exporter.
5. Assert identical Trace ID, distinct Span IDs, and `child.parentSpanId == parent.spanId`.
6. Check name, Resource, attributes, and error status.

This is a tracing SDK test; it does not yet verify OTLP network transport.

### 9.3. OTLP HTTP Smoke Test

1. Start a Collector with an OTLP HTTP receiver on port 4318 and a debug exporter.
2. Configure the application endpoint to `/v1/traces`.
3. Start Spring Boot with the tracing bridge/exporter and test-appropriate sampling.
4. Send an HTTP request that generates spans.
5. Wait for the batch processor to flush.
6. Inspect Collector logs/resource/spans.
7. If a test backend is available, query the Trace ID and verify spans.

Do not use `GET /v1/traces` or arbitrary JSON to conclude the exporter works. The receiver requires OTLP-compliant requests and payloads.

### 9.4. Testing Export Failures

In a test environment, stop the Collector to induce a connection failure; restart it and observe retry/queue behavior per SDK version; send malformed payloads via a mock receiver to verify protocol errors; and test graceful shutdown while batches are still pending. Do not claim zero span loss based solely on one Collector restart.

## 10. Pipeline Security and Operations

Trace data can contain URLs, dependency information, exception messages, SQL metadata, and business attributes. During export, data traverses networks and multiple storage systems.

| Risk | Control |
| --- | --- |
| Tokens/PII in span attributes | Attribute allowlist, redaction, payload testing |
| Publicly accessible Collector receiver | Private network, firewall, auth |
| Unencrypted OTLP traffic | TLS/HTTPS or equivalent transport protection |
| Leaked backend token | Secret manager, rotate as needed, do not log |
| High-cardinality attributes | Limit dynamic IDs, size, and indexing |
| Overloaded Collector | Memory limiter, batch sizing, queue/scaling |
| Trace data retained too long | Retention, access control, data governance |
| Excessive debug exporter logging | Use only in test environments |

Keep Resource stable: `service.name`, `service.version`, environment, and instance identity should be meaningful. Span attributes should describe operations; do not put emails, passwords, access tokens, request bodies, or payment data into traces. Do not copy all baggage into span attributes without review.

Trace IDs have nearly one unique value per trace. Using them as metric labels creates massive numbers of time series. If the backend supports exemplars, use exemplars to link metric samples to traces without creating a trace ID label on every series.

Monitor export requests/errors, retries, timeouts, dropped spans, queue occupancy, batch latency, Collector accepted/refused spans, exporter failures from Collector to backend, and backend ingestion latency. Specific metric names depend on SDK/Collector versions.

## 11. Troubleshooting OTLP Traces

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| No traces in backend | Tracing bridge/SDK not creating spans or sampler dropped | Check Observation, tracer, and sampling |
| Connection refused on port 4318 | Collector not listening or wrong container address | Check endpoint from app process and receiver |
| HTTP 404 | Wrong path or request hit the wrong server | Check `/v1/traces`, proxy routing |
| HTTP 400 | Invalid payload/content type/protocol | Check OTLP exporter, receiver logs |
| HTTP 401/403 | Wrong auth/tenant policy | Check headers/secrets/permissions |
| HTTP 429 | Quota or overloaded receiver | Reduce traffic/sampling, increase capacity per policy |
| HTTP 5xx | Collector/proxy/backend error | Check pipeline health, resources, and retries |
| TLS handshake error | Wrong certificate/CA/hostname/scheme | Check TLS trust chain and endpoint |
| Collector receives spans but backend is empty | Missing pipeline exporter or downstream export failed | Check `service.pipelines.traces` |
| Trace split across services | Lost propagation or mismatched protocol/header | Check `traceparent`, client/server instrumentation |
| Trace has only one branch | One service not exporting or sampled/dropped | Compare Resource `service.name` at Collector |
| Traces appear delayed | Batch schedule or Collector processor wait | Check batch/decision window |
| Some spans lost on shutdown | Queue not flushed or process force-killed | Check graceful shutdown and drop metrics |
| `unknown_service` | Missing Resource `service.name` | Check SDK Resource configuration |

### 11.1. Investigation Order

1. **Instrumentation:** did the request actually create an Observation/span?
2. **Sampling:** was the span recorded according to the sampler?
3. **SpanProcessor:** did the batch queue receive the span and is it full?
4. **Exporter:** are endpoint, protocol, path, TLS, and authentication correct?
5. **Collector:** did the receiver accept the request? Does `traces` pipeline wire processors/exporters?
6. **Backend:** are ingest, tenant, indexing, retention, and query right?
7. **Propagation:** if the trace is disconnected, inspect context separately; do not blame the exporter.

The OTLP receiver returning 503 is a telemetry pipeline error; `inventory-service` returning 503 is a business dependency error. Do not count export errors toward user-facing error rates if they do not cause business requests to fail. However, continuous exporter errors are still an operational issue that requires alerting.

## 12. Production Checklist

| Criterion | Evidence |
| --- | --- |
| Compatible dependencies | Spring Boot BOM, Micrometer Tracing bridge, and OTel exporter |
| Correct transport | OTLP/HTTP or OTLP/gRPC agreed upon |
| Valid endpoint | Host/port/path matching the actual receiver |
| Correct Resource | `service.name`/version/environment/instance |
| Working Collector pipeline | Receiver, processors, exporter wired |
| Protected TLS/auth | Secure credentials and trust chain |
| Appropriate sampling | Budgeted with understood head/tail behavior |
| Batch/queue sizing | Tested under peak load, timeouts, and shutdown |
| Tested propagation | Cross-service spans share trace ID/parent relationship |
| Safe attributes | No PII/secrets, controlled cardinality |
| Monitored exporter health | Errors, retries, drops, queue, ingest |
| Backend stores and finds traces | Queries work in staging/production with proper permissions |
| Metrics and logs properly correlated | SLIs from metrics; trace ID correlation |
| Graceful shutdown | Chance to flush within timeout |
| Upgrades have regression tests | Verify properties/protocols/semantic conventions |

## 13. Hands-On Exercise: Exporting Traces End-to-End

**Context:** a system has `order-service` calling `inventory-service`. Both run Spring Boot and need to send traces through an OpenTelemetry Collector to a trace backend.

**Tasks:**

1. Add Actuator, `micrometer-tracing-bridge-otel`, and the OTLP exporter using the project's BOM.
2. Configure `service.name`, `service.version`, environment, and the OTLP endpoint for the chosen transport.
3. Run a Collector OTLP receiver on HTTP 4318 or gRPC 4317 and declare `service.pipelines.traces`.
4. Enable 100% sampling in the test environment and call the order-creation endpoint several times.
5. Create a custom Observation for a business operation; use an instrumented HTTP client to call `inventory-service`.
6. Verify the Collector receives spans from both separate service Resources and that trace IDs/parent relationships match.
7. Switch from the debug exporter to a test backend and verify you can look up a trace by Trace ID.
8. Intentionally point the HTTP endpoint to the gRPC port, then fix it and document the transport error symptoms.
9. Stop the Collector while the application has traffic, observe exporter errors/queue/retries, and recover.
10. Reduce sampling to 10% and compare trace counts against request/error metrics still measured by instrumentation.
11. Add Observation, tracing SDK, and Collector smoke tests; state clearly which layer each test proves.
12. Write a runbook for the case where metrics/logs have data but traces do not appear.

**Expected outcome:** Spring Boot configuration, Collector pipeline, a trace with spans from both services, evidence of Resource/parent-child, layered tests, and a runbook covering endpoints, sampling, queues, exporter errors, and backend ingest.

## 14. Key Takeaways

**OTLP traces** is the way OpenTelemetry trace data moves from an application to a Collector or backend. In Spring Boot, Micrometer Observation and the Tracing bridge create/manage spans; the OpenTelemetry SDK and SpanProcessor handle sampling/batching; the OTLP exporter sends data over HTTP or gRPC; and the Collector receives, processes, and forwards it to trace storage.

Export differs from propagation: `traceparent` carries context as requests traverse services, while OTLP moves spans out of the process. For complete traces, you need proper Resource, span hierarchy, sampling, transport, endpoint, Collector pipeline, and backend ingestion. Use metrics for trends/SLOs, logs for events, and trace samples for investigation; protect attributes and monitor the telemetry pipeline itself.

**References:**

- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)
- [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- [OpenTelemetry — SDK Trace](https://opentelemetry.io/docs/specs/otel/trace/sdk/)
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
