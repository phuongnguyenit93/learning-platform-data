# OTLP HTTP Exporter in Spring Boot: Sending Distributed Traces to the Collector

A Spring Boot application has `Observation` around business logic and logs displaying `traceId`, yet when opening the tracing UI, the operations team still finds no traces. It does not necessarily mean code failed to create spans: data must still travel through **sampling, the span processor, the exporter, the Collector, and the trace backend**. A failure at even one hop makes traces vanish from the monitoring system.

**OTLP** (*OpenTelemetry Protocol*) is the protocol for transmitting observability data. The **OTLP HTTP exporter** is the component that sends spans over HTTP to an OTLP receiver—typically the OpenTelemetry Collector or an OTLP-capable backend. On the standard wire path, it uses **Protocol Buffers** (`application/x-protobuf`) and the `/v1/traces` endpoint.

This lesson belongs to the **Tracer implementation** chapter of the **SPRING_BOOT_OBSERVABILITY** module: setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing. It also distinguishes propagation, tags/cardinality, sampling, exporters, and how to combine metrics–logs–traces to investigate errors, latency, and application behavior in real environments.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of the OTLP HTTP exporter in the chain **Observation → tracing SDK → Collector → backend**.
2. Distinguish **OTLP/HTTP** from **OTLP/gRPC** in transport, port, and endpoint.
3. Configure Spring Boot 3.x to send spans to a Collector using Micrometer Tracing and OpenTelemetry.
4. Set up a test Collector pipeline with an OTLP HTTP receiver and a debug exporter.
5. Understand sampling, batching, queues, retries, timeouts, potential data loss, and export latency limits.
6. Secure telemetry using TLS, authentication, and safe span attribute policies.
7. Test layer by layer and diagnose why metrics/logs have data while traces are missing or split across services.

## 1. Where Does the Exporter Sit in the Architecture?

An `Observation` describes an operation's lifecycle. When the application configures matching handlers and a tracing bridge, that operation can become a span recorded by the tracer. The exporter receives span data from the tracing SDK/span processor, encodes it, and sends it outward.

~~~mermaid
flowchart LR
    App["Spring Boot HTTP / Business code"] --> Obs["Micrometer Observation"]
    Obs --> Bridge["Micrometer Tracing / OTel bridge"]
    Bridge --> SDK["OpenTelemetry SDK / SpanProcessor"]
    SDK --> Export["OTLP HTTP exporter"]
    Export -- "POST /v1/traces" --> Receive["Collector OTLP receiver"]
    Receive --> Process["Processors / exporters"]
    Process --> Store["Trace backend"]
    Obs --> Handler["Metrics handler"]
    Handler --> Meter["MeterRegistry / metrics backend"]
    App --> Log["Application logs<br/>traceId, spanId when present"]
~~~

| Component | Function | What It Does Not Guarantee |
| --- | --- | --- |
| `ObservationRegistry` | Manages Observations, scopes, conventions, and handlers | Does not send HTTP requests to the trace backend itself |
| Micrometer Tracing bridge | Connects Micrometer to the tracer/SDK | Does not guarantee every trace is sampled |
| OpenTelemetry SDK / SpanProcessor | Manages recording, batching, and span lifecycles | Does not provide durable span storage by default |
| **OTLP HTTP exporter** | Encodes and sends span batches over HTTP | Does not guarantee the Collector/backend persisted them |
| Collector OTLP receiver | Receives OTLP data | Not durable trace storage by default |
| Collector processors/exporters | Processes and forwards telemetry | No pipeline exists unless configured |
| Trace backend | Stores and allows querying spans/traces | Cannot recover spans that were never exported |

The typical microservices pattern: **each service exports its own spans**, either to a shared Collector or to separate Collector agents/gateways. The backend stitches spans together using trace IDs and parent/span IDs; the Collector does not "replay requests" to construct traces.

### 1.1. Export Differs from Propagation

There are two independent flows:

- **Propagation:** `order-service` sends `traceparent` when calling `inventory-service` to establish a parent–child relationship across two processes' spans.
- **Export:** `order-service` and `inventory-service` each send their own span data to the Collector via OTLP HTTP.

If **propagation fails**, both services may export successfully yet the backend shows **two disconnected traces**. If **export fails in one service**, the backend sees a trace missing one branch even though propagation worked. Do not confuse seeing a trace ID in logs with the Collector having received that span.

## 2. What Does OTLP/HTTP Send? Which Port and Path?

OTLP defines how to transmit **traces, metrics, and logs**. This lesson focuses exclusively on **span data**; metrics and logs exporters are separate pipelines.

| Signal | Common OTLP/HTTP Endpoint | Role |
| --- | --- | --- |
| Traces | `http://collector:4318/v1/traces` | Sends spans |
| Metrics | `http://collector:4318/v1/metrics` | Sends metrics via OTLP |
| Logs | `http://collector:4318/v1/logs` | Sends log records via OTLP |

You cannot simply swap `/v1/traces` for `/v1/metrics` and expect a span exporter to turn into a metrics exporter. Each signal type requires its own serializer, receiver pipeline, and configuration.

### 2.1. OTLP/HTTP vs. OTLP/gRPC

| Property | OTLP/HTTP | OTLP/gRPC |
| --- | --- | --- |
| Transport | HTTP, commonly using protobuf | gRPC over HTTP/2 |
| Common default port | **4318** | **4317** |
| Traces target | **`/v1/traces`** | gRPC service/method |
| Common content type | `application/x-protobuf` | Protocol Buffers over gRPC |
| Error response | HTTP status and receiver error details | gRPC status and error details |
| Load balancer/proxy | Must forward HTTP requests/paths properly | Must support gRPC/HTTP2 properly |

A common mistake is setting `http://localhost:4317/v1/traces` for an **HTTP exporter**. Port 4317 is typically the gRPC receiver, so an HTTP request to `/v1/traces` will not be handled as expected. For OTLP HTTP/protobuf, the typical local address is:

~~~text
http://localhost:4318/v1/traces
~~~

**`localhost` is always resolved relative to the sending process/container**, not automatically pointing to a Collector running in another container or host.

### 2.2. HTTP Request Shape

The exporter typically sends an encoded batch:

~~~http
POST /v1/traces HTTP/1.1
Host: collector:4318
Content-Type: application/x-protobuf
Authorization: Bearer TOKEN_PLACEHOLDER

<binary OTLP ExportTraceServiceRequest>
~~~

This illustrates the protocol, **not a curl command you can copy-paste and run**. The body is binary protobuf. The `Authorization` header appears only when authentication is enabled and must use real credentials from a secret store or environment variable—never commit tokens into documentation, repos, or logs.

A successful HTTP response indicates the receiver handled the request at the protocol level; **it does not prove** the data reached trace storage: batching, filtering policies, Collector exporters, backend ingestion, and retention still apply. Some OTLP responses can also report **partial success/rejected spans**; when investigating data loss, inspect receiver/Collector details rather than just the HTTP status code.

## 3. Configuring Spring Boot Dependencies

Gradle example for **Spring Boot 3.x** using Micrometer Tracing with the OpenTelemetry bridge:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Use OpenTelemetry as Micrometer's tracing implementation.
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'

    // Export spans using OTLP.
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    // Optional: Prometheus metrics independent of the traces exporter.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Each dependency handles a distinct job:

1. **Actuator:** provides Spring Boot observability integration.
2. **Micrometer Tracing bridge:** connects Observation/Tracing APIs to OpenTelemetry.
3. **OTLP exporter:** handles shipping span data out of the application.
4. **Prometheus registry (if needed):** serves metrics; does not replace the tracing exporter.

**Do not pin arbitrary Micrometer, OpenTelemetry, and Spring Boot versions**; rely on your project's BOM/dependency management and check version-specific docs. Differences across Spring Boot lines can affect property names, auto-configuration, and HTTP/gRPC transport selection.

### 3.1. Example application.yml for OTLP/HTTP

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 1.0  # Use only for low-traffic practice.
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

`management.otlp.tracing.endpoint` is the property used in Spring Boot 3.x versions supporting OTLP tracing auto-configuration. Verify against your **actual project version**; in other versions, exporter configuration may differ.

`probability: 1.0` makes traces easy to see in a test environment, but should not be deployed across high-traffic production systems because high volume increases span counts, CPU, memory, network traffic, and ingestion cost.

### 3.2. Using Environment Variables on Deployment

~~~yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT:http://localhost:4318/v1/traces}
~~~

Example Collector Service endpoint in Kubernetes:

~~~text
OTLP_TRACES_ENDPOINT=http://otel-collector.observability.svc.cluster.local:4318/v1/traces
~~~

This is an **illustrative DNS name**, not a guaranteed pre-existing service name. Verify the actual address, namespace, port, DNS, and network policies for your deployment environment.

### 3.3. Service Name and Resource Attributes

`spring.application.name` is typically used by Spring Boot as context for the application/tracing service name, yet whenever the backend displays `unknown_service`, inspect the **actual resource attributes included in OTLP by the SDK/exporter**.

| Resource Attribute | Example | Meaning |
| --- | --- | --- |
| `service.name` | `order-service` | Distinguishes services in the backend |
| `service.version` | `1.8.2` | Correlates with a release |
| `deployment.environment` | `staging` | Filters by environment |
| `service.instance.id` | Bounded instance ID | Investigates per-instance differences |

Never use access tokens, user IDs, or personal data as resource attributes. The property/API used to attach extra resource attributes depends on your Spring Boot/OpenTelemetry version.

### 3.4. Authentication and TLS

When the Collector or backend requires authentication, mechanisms exist to set headers for OTLP tracing. Illustrative example for Spring Boot versions supporting `management.otlp.tracing.headers`:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT}
      headers:
        Authorization: ${OTLP_AUTH_HEADER}
~~~

`OTLP_AUTH_HEADER` should be supplied via a secret management system. Verify property binding for your actual version: not every Spring Boot release or exporter reads headers from the same property namespace.

Production must use **HTTPS/TLS**, proper certificates/CAs, explicit receiver access controls, and network policies. If a proxy or mTLS is involved, configure the exporter and Collector accordingly; **never disable TLS verification** as a permanent fix.

## 4. Setting Up an OpenTelemetry Collector to Receive OTLP/HTTP

The Collector decouples telemetry ingestion from the application: it receives spans, batches them, filters by policy, enriches resource attributes, forwards them, and monitors pipeline health.

A test configuration:

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s

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

With a Collector supporting the `debug` exporter, Collector logs print the received spans after batching. This is a **learning configuration**: do not run detailed debug verbosity in production because logs may contain sensitive span attributes and large data volumes.

~~~mermaid
flowchart LR
    A["Spring Boot<br/>OTLP HTTP exporter"] -- "POST :4318/v1/traces" --> B["Collector<br/>OTLP HTTP receiver"]
    B --> C["Batch processor"]
    C --> D["Debug exporter (test)"]
    C -. "Production: backend exporter" .-> E["Trace storage / backend"]
~~~

### 4.1. The Collector Must Have a Service Pipeline

Declaring `receivers.otlp` alone is not enough. `service.pipelines.traces` must connect receivers, processors, and exporters. With only the debug exporter, the Collector can **receive and log spans** without storing long-lived traces for UI search.

In production, configure the right target exporter (OTLP/HTTP, OTLP/gRPC, or a backend-supported protocol), along with authentication, TLS, retries, a memory limiter, and batching per deployment needs. Using HTTP on the receiver **does not force** the downstream exporter to use HTTP as well.

### 4.2. Running in Containers and Kubernetes

- The receiver must listen on an interface matching the intended traffic path. `0.0.0.0:4318` accepts traffic on container network interfaces, so enforce firewalls/network policies to protect it.
- If Spring Boot and the Collector run in **two separate containers**, `localhost:4318` inside Spring Boot is not the Collector.
- If the Collector is deployed as a Kubernetes Service, use the assigned Service DNS/port and verify the namespace.
- The Collector image/version must include the `otlp`, `batch`, and `debug` components. Older releases may use different exporter names.
- If the pipeline is misconfigured or defines a receiver without an exporter, having an open port does not mean spans are stored.

### 4.3. Checking Receiver Status

A TCP check to port 4318 verifies network reachability, **not valid OTLP payload handling**. Sending `GET /v1/traces` with curl may return 404/405 because the receiver expects POST/protobuf; do not conclude the export endpoint is broken from a single GET result.

Better evidence: Spring Boot sends a real batch and the Collector logs span/resource details, or a test receiver decodes an OTLP `ExportTraceServiceRequest`.

## 5. Instrumenting Business Logic with Micrometer Observation

There is no need to craft OTLP HTTP requests manually per operation. Application code should use `Observation`; the tracing SDK/handler/exporter handles telemetry delivery.

~~~java
package com.example.orders.tracing;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class InventoryReservationService {
    private final ObservationRegistry registry;
    private final InventoryGateway inventory;

    public InventoryReservationService(
            ObservationRegistry registry, InventoryGateway inventory) {
        this.registry = registry;
        this.inventory = inventory;
    }

    public void reserve(String sku, int quantity) {
        String attemptId = UUID.randomUUID().toString();

        Observation.createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("dependency.name", "inventory")
                .lowCardinalityKeyValue("inventory.operation", "reserve")
                .highCardinalityKeyValue("inventory.attempt.id", attemptId)
                .observe(() -> inventory.reserve(sku, quantity));
    }
}

interface InventoryGateway {
    void reserve(String sku, int quantity);
}
~~~

In this example:

1. `inventory.reserve` is a stable name with no dynamic IDs.
2. Low-cardinality tags represent operation type and dependency, making them suitable for metric grouping.
3. `inventory.attempt.id` is high-cardinality metadata; the tracing handler can add it to span attributes when configured. An opaque pseudonymous UUID helps trace an attempt without putting user data into the trace.
4. `observe(...)` manages lifecycle and scope, recording exceptions per API behavior.
5. The span may be exported **after the Observation stops**, since the SDK can batch before making the HTTP request.

If Spring MVC/HTTP clients are already instrumented, avoid adding another custom Observation solely to duplicate existing HTTP spans. Instrument **meaningful business boundaries** such as checkout, inventory reservation, and payment validation.

### 5.1. Do Not Call the Exporter Inside Request Handlers

Never write logic like "create a span per request and manually POST to `/v1/traces`" inside a business service. That tightly couples business code to telemetry, breaks batching/retry control, and can turn Collector issues into user-facing latency.

If near-real-time trace visibility is needed, tune the SDK/Collector within budget; never force synchronous flushing on every request.

## 6. Propagation via traceparent Differs from OTLP Export

Suppose `order-service` calls `inventory-service`. To get a cross-service span tree, HTTP client/server instrumentation must **propagate and extract trace context**, typically via W3C Trace Context:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

| Part | Meaning |
| --- | --- |
| `00` | Header version |
| 32 hex chars | Trace ID |
| 16 hex chars | Sender's Span ID, used as remote parent |
| `01` | Trace flags; sampled bit is enabled in this example |

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Order as order-service
    participant Inv as inventory-service
    participant Collector as OTel Collector
    Client->>Order: POST /orders
    Note over Order: HTTP SERVER span A
    Order->>Order: inventory.reserve span B
    Order->>Inv: HTTP + traceparent, CLIENT span C
    Note over Inv: HTTP SERVER span D, parent C
    Inv-->>Order: HTTP response
    Order-->>Client: Response
    Order->>Collector: OTLP HTTP sends spans A,B,C
    Inv->>Collector: OTLP HTTP sends span D
~~~

- Child spans share the **same trace ID** as the parent, while receiving a **new span ID** and setting `parentSpanId` to the parent span.
- Both services **export independently**; the backend reconstructs the tree from the identifiers inside spans.
- If one service fails to export, the backend shows a missing branch even though trace context propagated properly.
- If propagation fails, the backend shows two separate traces even though both exporters succeeded.

### 6.1. Async, Reactor, and Messaging

`@Async`, `Executor`, Reactor, messaging, or batch processing can change execution context. If the active trace context is not captured and restored, new spans can become separate roots.

With Spring Framework 6.1+ and Micrometer Context Propagation, `ContextPropagatingTaskDecorator` can propagate context for compatible executors once accessors are configured. Reactor requires its own context handling; messaging requires the right propagators/headers. **Fixing the OTLP URL cannot re-stitch parent–child links once context has been lost.**

### 6.2. High-Cardinality Metadata Is Not Automatically Baggage

`Observation.highCardinalityKeyValue(...)` attaches metadata to an Observation/span; it is **not automatically transmitted to other services** via `traceparent`. If a business value genuinely needs to propagate, design a controlled header or baggage key with bounded size and no sensitive data.

## 7. Sampling: Which Spans Get Exported?

**Sampling** decides which spans/traces are recorded for potential export. The OTLP HTTP exporter cannot recover spans that the sampler already dropped.

~~~mermaid
flowchart TD
    A["Observation created"] --> B{"Does Tracing SDK record span per sampling?"}
    B -- "No" --> C["No recorded span to export"]
    B -- "Yes" --> D["Span finishes"]
    D --> E["SpanProcessor queue / batching"]
    E --> F["OTLP HTTP POST"]
    F --> G{"Receiver accepts?"}
    G -- "Yes" --> H["Collector pipeline → backend"]
    G -- "Transient error" --> I["Retry if policy allows"]
    I --> F
    G -- "Unrecoverable / budget exhausted" --> J["Spans may be lost"]
~~~

### 7.1. Head-Based Sampling vs. Tail-Based Sampling

**Head-based sampling** decides early—for instance, with a 10% probability—and the sampling flag can be propagated. It reduces overhead but can miss traces of rare errors.

**Tail-based sampling** typically lives in the Collector/ingestion tier to prioritize slow or failing traces after observing part or all of the trace. It requires queues, memory, and proper policy configuration. If the SDK already dropped spans via head sampling before export, the Collector **cannot recover spans that never arrived**.

**10% sampling does not mean only 10% of HTTP requests are processed**; the application handles all requests normally, and metrics continue measuring every instrumented request.

### 7.2. Sampling and Parent–Child Spans

An unrecorded root span can result in no trace in the backend. If policies differ incompatibly across services or a service samples independently, traces can be incomplete. Therefore, beyond probability configuration, verify **remote sampling state** and context inheritance across services.

Do not use the number of stored traces directly as the denominator for system-wide error rates unless your sampling design statistically justifies it. For user-facing SLIs/SLOs, prefer aggregated HTTP metrics with clear scope.

## 8. Batching, Retries, Queues, and Data Loss

The exporter normally works with a **BatchSpanProcessor**, collecting completed spans into batches and sending them over HTTP according to configured batch size and schedule. Consequently, spans may not appear in the backend instantaneously.

| Option / Mechanism | Effect | Risk |
| --- | --- | --- |
| Batch size | Number of spans grouped per send | Too large increases memory; too small increases HTTP overhead |
| Export interval | Scheduled flush frequency | Too long delays trace visibility |
| Queue capacity | Spans buffered while awaiting export | Full queue causes drops |
| HTTP timeout | Max wait time for receiver response | Too short triggers false failures on slow networks |
| Retry/backoff | Recovers from transient errors | Does not guarantee delivery if retry budget runs out |
| Collector batch processor | Batches data before backend export | Boosts throughput but adds latency/memory |
| Collector memory limiter | Prevents Collector OOM | May reject or drop data under pressure |

Not every option lives under `management.otlp.tracing.*` across all Spring Boot versions. Some live in the OpenTelemetry SDK/span processor, and others in the Collector. Check documentation for your **exact version** to avoid adding nonexistent properties and assuming they took effect.

### 8.1. Does the Exporter Keep Spans When the Collector Fails?

Some implementations retry transient errors, yet **there is no default guarantee of durable persistence for all spans**. If the application is killed while batches sit in RAM, data can be lost. If the Collector is overloaded, the exporter or Collector may drop/reject spans once limits are exceeded.

Therefore:

1. Monitor export error rates, queue occupancy, and dropped spans if exposed by SDK/Collector telemetry.
2. Use graceful shutdown so the SDK can flush within its timeout budget.
3. Never use traces as a durable business audit log or source of truth for transactions.
4. Never force synchronous per-span export, as it can slow down request paths.
5. Budget sampling and retention around traffic, peaks, and cost.

### 8.2. Retries Do Not Fix Configuration Errors

Retries help when a receiver is temporarily overloaded or the network blips. With an invalid token, wrong endpoint path, or mismatched transport, adding retries only adds load and delays detection. Before changing retry policies, classify whether the error is transient or a static misconfiguration.

## 9. Telemetry Security and Sensitive Data

Spans can cross multiple systems and remain stored for days or weeks. A span attribute helpful during local debugging may not be permissible outside application infrastructure.

| Data | Should It Be Exported? | Handling |
| --- | --- | --- |
| `service.name`, `service.version` | Yes | Clear resource attribute contract |
| Operation type, dependency | Yes | Stable names, bounded values |
| `http.route=/orders/{id}` | Usually yes | Route template instead of raw URL |
| Internal pseudonymous attempt ID | Consider | Bounded high cardinality; cannot identify users |
| Email, phone number, address | Not by default | Personal data (PII) |
| Password, token, cookie | **No** | Authentication secrets |
| Request/response body | Avoid by default | May contain sensitive data and be very large |
| Unbounded exception message | Controlled | May leak SQL, URLs, or payloads |

**Production principles:**

- Attach only metadata genuinely required for investigative questions; cap attribute lengths and counts.
- Never put user IDs, trace IDs, or order IDs into **low-cardinality metric labels**: they explode time series.
- Be cautious with **high-cardinality span attributes**; even without exploding metric series, they increase trace storage/indexing costs and security exposure.
- Protect traffic to the Collector with TLS, network policies, and proper authentication.
- Keep credentials in a secret store; never commit tokens directly into `application.yml` in source control.
- Set explicit retention and access controls for traces and logs; restrict who can view sensitive spans.
- Never run the `debug` exporter at `detailed` verbosity in production unless strictly controlled.

### 9.1. Resource Attributes vs. Span Attributes

**Resource attributes** such as `service.name` describe the telemetry producer, whereas **span attributes** such as `dependency.name` describe a specific operation. Both travel in OTLP payloads, yet the backend may display or index them differently. Do not conclude the exporter dropped an attribute simply because a UI filter does not index that field for search.

## 10. Testing the OTLP HTTP Exporter Layer by Layer

No single test proves end-to-end tracing completely. Verify from instrumentation all the way through transport and backend.

| Layer | Tool / Approach | Evidence |
| --- | --- | --- |
| Observation unit test | `TestObservationRegistry` | Observation has expected name/tags/lifecycle |
| Tracing SDK test | In-memory exporter or test span handler | Spans and `parentSpanId` match expectations |
| HTTP transport test | Mock OTLP receiver understanding protobuf | POST request and payload are valid |
| Collector smoke test | OTLP HTTP receiver + debug exporter | Collector receives resource/spans |
| Backend integration | Staging trace backend | Trace searchable by ID/service |
| Cross-service test | Two services with W3C propagation | Seamless parent–child across HTTP |

### 10.1. Unit Testing Micrometer Observation

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.Test;

class InventoryObservationTest {
    @Test
    void recordsOperationMetadata() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("dependency.name", "inventory")
                .highCardinalityKeyValue(
                        "inventory.attempt.id", "attempt-test-001")
                .observe(() -> { /* simulate successful business work */ });

        TestObservationRegistryAssert.assertThat(registry)
                .hasSingleObservationThat()
                .hasBeenStopped()
                .hasNameEqualTo("inventory.reserve")
                .hasLowCardinalityKeyValue("dependency.name", "inventory")
                .hasHighCardinalityKeyValue(
                        "inventory.attempt.id", "attempt-test-001")
                .doesNotHaveError();
    }
}
~~~

This test verifies the Observation runtime; **it makes no OTLP HTTP requests**. Proving the exporter and Collector work requires tests at lower layers.

### 10.2. Testing Span IDs with an In-Memory Exporter

With OpenTelemetry SDK test utilities and a recording sampler:

1. Create a parent Observation inside an active scope.
2. Create a child Observation inside the parent's scope.
3. Complete the child and parent.
4. Collect span data via an in-memory exporter.
5. Verify parent and child share the **same trace ID**.
6. Verify child has its **own span ID** and `child.parentSpanId == parent.spanId`.
7. Verify span names, attributes, and error/status per policy.

This verifies the tracing SDK and instrumentation; **it does not verify HTTP transport or the Collector**.

### 10.3. Real Collector Smoke Test

Steps:

1. Start the Collector with the `otlp` HTTP receiver and `debug` exporter from the learning config.
2. Point both Spring Boot and the Collector to the same real endpoint and port.
3. In the test environment, set sampling to `1.0` and send a few requests with Observations.
4. Wait past the batching interval, then inspect Collector logs for `service.name`, `traceId`, and span names.
5. If the Collector forwards to a staging backend, look up the trace ID and inspect the parent–child tree.
6. Temporarily stop the Collector to observe exporter errors/retries; bring it back and verify recovery within queue limits.

**Do not send a hand-crafted JSON string to `/v1/traces` and treat HTTP 200/400 as full proof of the exporter.** A real transport test must use a valid OTLP payload and the expected content type.

### 10.4. Distinguishing Unit Tests from End-to-End

`TestObservationRegistry` catches naming/tag/lifecycle bugs quickly. An in-memory exporter proves span recording. Collector debug proves the receiver accepted payloads. Backend queries prove data is stored and searchable. **A passing result at one layer must never be extrapolated to all remaining layers.**

## 11. Diagnosing HTTP Export Errors

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| `Connection refused` on `localhost:4318` | Collector stopped, wrong container namespace, receiver not listening | IP/DNS from app process, port bindings, receiver config |
| DNS timeout / network timeout | Service DNS, network policy, firewall, proxy | Reachability, routing, proxy/TLS |
| HTTP **404** | Wrong `/v1/traces` path or hitting wrong server | Actual endpoint and reverse proxy |
| HTTP **400** | Invalid payload/protocol | OTLP/HTTP protobuf, content type, Collector logs |
| HTTP **401/403** | Missing/invalid auth or tenant permissions | Headers, secrets, gateway policy |
| HTTP **429** | Quota exceeded or receiver/backend overloaded | Sampling, traffic volume, retry/backoff, queue |
| HTTP **5xx** | Transient receiver/proxy/backend failure | Pipeline health, resource pressure, retry policy |
| TLS handshake failed | Wrong CA/certificate/hostname | Endpoint scheme, trust store, TLS config |
| Collector sees spans, backend has none | Missing target exporter, auth error, wrong pipeline | Collector service pipelines and exporter logs |
| Backend shows one service, misses another | Other service's exporter misconfigured or sampling | Compare service resources / Collector receivers |
| Trace split in two | `traceparent` not injected/extracted | HTTP client/server instrumentation and propagation |
| Logs have `traceId`, trace UI is empty | Dropped by sampler or missing exporter/Collector/backend | Check from tracing SDK through backend |
| Spans appear late | Batch schedule, Collector queue | Observe pipeline latency |
| `unknown_service` | Incorrect `service.name` resource | Resource attributes and service naming |

### 11.1. Inspect from Closest to Farthest

1. **Code/Observation:** does business code actually execute inside an Observation? Do unit tests for names/tags pass?
2. **Tracing SDK:** are recording spans created? Does the sampler keep them? Is the processor configured?
3. **Exporter:** are HTTP/Protobuf and the `:4318/v1/traces` URL right? Do connectivity, TLS, and auth work?
4. **Collector:** is the receiver listening? Does `service.pipelines.traces` connect to an exporter? Is it rejecting spans?
5. **Backend:** has it ingested, stored, and displayed data for the right tenant/time range/service?
6. **Propagation:** if spans exist but the tree is disconnected, inspect `traceparent` headers and context across threads.

Do not tweak the Prometheus scrape interval to fix trace export errors. Metrics and tracing are separate pipelines.

### 11.2. Do Not Confuse Telemetry Errors with Business Errors

An HTTP **503 from the OTLP receiver** indicates a **telemetry pipeline** failure; an HTTP **503 from `inventory-service`** is a business dependency failure. Log and monitor them in separate categories. Applications should generally not fail user transactions just because the trace exporter cannot connect, yet telemetry loss must still be tracked as an operational incident.

## 12. Monitoring the Tracing Pipeline Itself

Tracing is used to investigate incidents, yet the tracing pipeline itself can break right when you need it most. Maintain dashboards and alerts for:

| Signal | Operational Question |
| --- | --- |
| Exporter requests/errors | Are sends to the receiver succeeding? |
| Exporter queue / dropped spans | Is the SDK buffering too much or dropping data? |
| Export latency/retries | Is the network or receiver congested? |
| Collector accepted/refused spans | How much data is the receiver accepting? |
| Collector exporter send failures | Is the Collector receiving spans but failing to send to the backend? |
| Batch processor latency | Where is visibility delay coming from? |
| Backend ingest/retention | Is data persisted and still queryable? |

Exact metric names depend on OpenTelemetry SDK and Collector versions; inspect the actual metrics your deployment exposes before writing recording rules or alerts. Avoid alerting solely on "low span count," since sampling and traffic shifts also affect span counts.

### 12.1. Graceful Shutdown

Shutting down an application while spans remain in in-memory queues can lose data. During rolling deployments:

- Allow a reasonable graceful shutdown period.
- Ensure the tracing SDK/span processor gets a chance to flush within the timeout.
- Monitor exporter failures during rollouts.
- Never rely on traces as mandatory, zero-loss business records.

### 12.2. Distinguish User SLOs from Telemetry SLOs

A user SLO might be "99% of `POST /orders` under 500 ms." An observability pipeline SLO might track telemetry availability, export error rates, or dropped spans relative to policy. Never divide **stored traces / total HTTP requests** directly as a success rate when tracing is sampled and one request creates multiple spans.

## 13. Scenario: p95 Rises While the inventory-service Branch Is Missing

**Assumption:** after a deploy, `POST /orders` p95 rises from 350 ms to 2.5 seconds. Both HTTP metrics and logs show `inventory_timeout` errors, yet the trace backend only displays spans from `order-service`.

~~~text
Expected trace:
POST /orders                       order-service
└─ orders.checkout                 order-service
   └─ inventory.reserve            order-service
      └─ HTTP POST inventory       order-service
         └─ POST /reserve          inventory-service
            └─ DB stock lookup     inventory-service

Actual trace:
POST /orders                       order-service
└─ orders.checkout                 order-service
   └─ inventory.reserve            order-service
      └─ HTTP POST inventory       order-service
      (no spans visible from inventory-service)
~~~

Investigation workflow:

1. **Use metrics to scope impact:** did request rate, HTTP 5xx errors, p95/p99, retry rate, and inventory latency change?
2. **Use the remaining trace to isolate the hop:** is `order-service`'s HTTP CLIENT span waiting for a long time?
3. **Propagation:** was `traceparent` sent to inventory? Does inventory's SERVER span share the trace ID?
4. **Inventory SDK:** are the tracing bridge, sampler, and instrumentation active?
5. **OTLP exporter:** does `localhost:4318` inside the inventory container mistakenly point to itself instead of the Collector Service? Do logs show connection refused, 401, or 404?
6. **Collector:** does the receiver see `service.name=inventory-service`? Does the traces pipeline forward it?
7. **Fix:** resolve the endpoint/network/auth/propagation issue based on verified evidence and re-measure.
8. **Continue business investigation:** restoring the exporter only restores **observability**. You still need to find the root cause of the 2.5 seconds (DB pool, timeouts, saturation, retries, etc.).

**Never conclude every request is slow from a single trace**; use metrics to quantify scope, traces to inspect a specific request's path, and logs for error events.

## 14. Production Checklist

| Criterion | Required Evidence |
| --- | --- |
| Compatible dependencies and versions | Boot BOM, Micrometer Tracing OTel bridge, OTLP exporter |
| Right protocol | OTLP/HTTP matching receiver support, not confused with gRPC |
| Right endpoint | `/v1/traces`, port, and DNS from the application's perspective |
| Environment-based config | Endpoint via config/secret, no hard-coded production `localhost` |
| Correct service name/resource | Backend distinguishes service, version, environment |
| Verified TLS/auth | Secured receiver; matching headers/CA/policies |
| Collector traces pipeline | Receiver, processors, and target exporter wired |
| Controlled sampling | High in dev if desired, budgeted in production |
| Sensible queue/retry/timeout | Metrics for export errors and dropped-span indicators |
| Graceful shutdown | Chance to flush during scale-down / rolling updates |
| Verified HTTP/async propagation | Same trace ID, accurate `parentSpanId` |
| Safe span attributes | No tokens, emails, raw bodies, or sensitive data |
| Metrics and logs still correlate | Request rate, p95, error rate, and trace ID in logs within scope |
| Backend actually stores traces | Traces queryable by ID, service, and time window |

## 15. Practice Exercise: From Observation to an OTLP HTTP Collector

**Context:** two Spring Boot services, `order-service` and `inventory-service`, run alongside an OpenTelemetry Collector in a development environment. The goal is to observe a trace from the HTTP entry point to the reservation step while systematically catching exporter failures.

**Tasks:**

1. Add Actuator, `micrometer-tracing-bridge-otel`, and `opentelemetry-exporter-otlp` to both services.
2. Configure `management.otlp.tracing.endpoint` to the Collector's OTLP/HTTP `/v1/traces`; verify port 4318 and real DNS.
3. Run the Collector with an OTLP HTTP receiver and debug exporter in a test environment.
4. Create a custom `Observation` named `inventory.reserve` in `order-service`. Use an instrumented HTTP client to call `inventory-service`.
5. Enable `1.0` sampling for visibility; send 5 successful requests and 2 timeout requests.
6. In Collector logs, verify `service.name` resources for both services, spans, and trace IDs.
7. In the staging backend (if available), inspect the span tree sharing a trace ID and verify proper HTTP CLIENT → SERVER linkage.
8. Use `TestObservationRegistry` to verify names/tags/lifecycle, then explain why that test does not prove the HTTP exporter works.
9. Intentionally change the HTTP endpoint to the gRPC port `4317`; observe the error, fix the URL, and confirm recovery.
10. Stop the Collector temporarily, generate traffic, inspect exporter retry/queue/drop behavior within configured limits, and restore it.
11. Reduce sampling from 100% to 10% in testing and compare present traces against HTTP request counts/metrics.
12. Write a short report: when p95 rises while traces are missing, which hops do you inspect first?

**Expected deliverables:** application and Collector configs, at least one received trace (when the pipeline is healthy), proof of correct path/protocol, a troubleshooting table for exporter failures, and policies for sampling, authentication, cardinality, and data protection.

## 16. Takeaways

The **OTLP HTTP exporter** transports **recorded traces** from the OpenTelemetry SDK over **HTTP/protobuf**, commonly to `http://collector:4318/v1/traces`. It does not create parent–child spans on its own, does not replace Micrometer Observation, does not dictate all sampling policies, and does not guarantee traces are persisted in the backend.

For reliable operations, inspect the full chain **Observation → tracing bridge/SDK → sampling/span processor → exporter → Collector → backend**. `traceparent` context stitches spans across services; metrics reveal error/latency trends, while logs and traces explain specific instances. Success depends on network/TLS/auth configuration, capacity/retries, sampling, tags/cardinality, retention, and multi-signal correlation.

**References:**

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)
- [OpenTelemetry — SDK Trace](https://opentelemetry.io/docs/specs/otel/trace/sdk/)
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
