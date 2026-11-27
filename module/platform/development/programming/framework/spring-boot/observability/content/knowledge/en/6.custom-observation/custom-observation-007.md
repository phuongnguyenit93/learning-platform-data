# Attaching high-cardinality metadata to Custom Observations in Spring Boot

When investigating a slow request, engineers often need to know **which specific attempt** failed. For instance, out of thousands of calls to `inventory-service`, one reservation attempt took 2.4 seconds and timed out. Metrics show that latency is climbing, yet cannot provide full details for each individual call. Distributed tracing can display a span representing that specific attempt, complete with metadata to aid root-cause analysis.

In Micrometer Observation, attributes with many distinct values—such as a unique attempt identifier per request—are called **high-cardinality key-values**. You can attach them to a **custom observation** using the `highCardinalityKeyValue(...)` API or supply them via an `ObservationConvention`. When an appropriate tracing handler is configured, they can become **span attributes** for investigating specific requests.

This lesson belongs to the **Custom observation** section of the **SPRING_BOOT_OBSERVABILITY** module: setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. It also explains context propagation across services and threads, tags and cardinality, exporters, sampling, and correlating signals during real incidents.

## Learning objectives

After this lesson, you will be able to:

1. Distinguish low-cardinality and high-cardinality metadata by purpose, cost, and where each is used.
2. Attach high-cardinality metadata using `Observation.highCardinalityKeyValue(...)` in a custom observation.
3. Build `Observation.Context` and `ObservationConvention` when multiple instrumentation points need a unified tag contract.
4. Explain how high-cardinality metadata appears in traces and why it does not automatically propagate to other services.
5. Prevent sensitive data leaks, avoid metric series explosion, and control tracing costs.
6. Test metadata at runtime, cross-reference metrics/traces/logs, and handle cases where traces are dropped by sampling or exporters.

## 1. What is high-cardinality metadata?

**Cardinality** is the number of distinct values a key can take. For example, `inventory.channel` only has `web` and `batch`, so its cardinality is low. `inventory.attempt.id` gets a fresh value on every call, so its cardinality is high.

| Key | Example value | Characteristic | Suitable purpose |
| --- | --- | --- | --- |
| `inventory.operation` | `reserve`, `release` | Low cardinality: bounded set | Group metrics by operation type |
| `inventory.channel` | `web`, `batch` | Low cardinality | Compare behavior by calling source |
| `inventory.outcome` | `success`, `failure` | Low cardinality | Track outcomes by group |
| `inventory.attempt.id` | `attempt-8d1...` | High cardinality: nearly unique per call | Locate one specific attempt in traces |
| `job.execution.id` | Identifier of a single job run | High cardinality | Analyze one specific background run |
| `http.request.raw_path` | `/orders/72834` | High cardinality | Do not use as a metric label; assess whether truly needed |
| `customer.email` | User email | High and sensitive | **Do not collect by default**, even in traces |

### 1.1. Distinguishing by system impact

A metrics system like Prometheus typically stores each combination of metric name and labels as a **time series**. If `inventory.attempt.id` changes on every invocation, the number of series can grow with request count, leading to heavy memory, storage, and query overhead.

In Micrometer Observation, **low-cardinality key-values** are typically used by metrics handlers to attach aggregatable labels. **High-cardinality key-values** are typically used by tracing handlers as span attributes to describe *one specific execution*. Which backend actually receives a key depends on active handlers, filters, exporters, sampling, and configuration.

For example, if a metric is grouped by 2 channels, 3 outcomes, 4 regions, and 50 instances, combinations can reach **2 × 3 × 4 × 50 = 1,200**. Adding a per-request `attempt_id` across 100,000 requests causes combinations to scale with requests and destroys aggregation utility.

**High cardinality does not mean the data is safe to collect.** A high-cardinality identifier could be personal info, an access token, or a secret; such data must still be stripped or handled per policy before entering traces or logs.

### 1.2. High-cardinality metadata is neither logs nor baggage

Keep three concepts separate:

- **Observation high-cardinality key-value:** metadata attached to `Observation.Context`; tracing handlers can put it onto the corresponding span.
- **Log field:** a field emitted by the logging system. It appears only when code or logging configuration explicitly writes it. Logs can carry a trace ID to link to spans, yet do not automatically inherit every high-cardinality Observation key.
- **Baggage:** contextual data that can propagate across service boundaries when configured. Adding `highCardinalityKeyValue` **does not automatically turn a key into baggage** and does not send that attribute to downstream services.

Never use high-cardinality metadata as durable business state storage. Traces can be sampled out, dropped, expired by retention, or lost by exporters.

## 2. Lifecycle of a custom observation

An Observation is usually created and started before the work, optionally enriched with key-values or events, records exceptions if any, and then stops. `observe(...)` handles the common steps:

~~~mermaid
flowchart LR
    A["Create Observation"] --> B["Attach low/high-cardinality key-values"]
    B --> C["start + open Scope"]
    C --> D["Execute business logic"]
    D --> E{"Exception?"}
    E -- Yes --> F["Record error"]
    E -- No --> G["Complete"]
    F --> H["Close Scope + stop"]
    G --> H
    H --> I["Handlers create metrics/spans per config"]
~~~

To ensure metadata is present when handlers process lifecycle callbacks, **attach known attributes before calling `observe(...)`** or before `start()`. When a value is only known at the end of the operation, you can attach it while the Observation is running, though you should verify that the target handler reads late-added metadata. Do not rely on mutating context after `stop()`.

### 2.1. Minimal example: attaching an attempt ID

Suppose `InventoryGateway` is an adapter calling the inventory system. We generate an internal pseudonymous code per invocation instead of placing order IDs or user data onto spans.

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class InventoryReservationService {
    private final ObservationRegistry observationRegistry;
    private final InventoryGateway inventoryGateway;

    public InventoryReservationService(
            ObservationRegistry observationRegistry,
            InventoryGateway inventoryGateway) {
        this.observationRegistry = observationRegistry;
        this.inventoryGateway = inventoryGateway;
    }

    public void reserve(String sku, int quantity) {
        String attemptId = UUID.randomUUID().toString();

        Observation.createNotStarted("inventory.reserve", observationRegistry)
                .lowCardinalityKeyValue("inventory.operation", "reserve")
                .lowCardinalityKeyValue("inventory.channel", "web")
                .highCardinalityKeyValue("inventory.attempt.id", attemptId)
                .observe(() -> inventoryGateway.reserve(sku, quantity));
    }
}

interface InventoryGateway {
    void reserve(String sku, int quantity);
}
~~~

In this example:

1. `inventory.reserve` is the **stable Observation name**, free of request IDs.
2. `inventory.operation=reserve` and `inventory.channel=web` are **low-cardinality tags**, suitable for grouping metrics.
3. `inventory.attempt.id` is a **high-cardinality tag**; each reservation gets a fresh UUID. Tracing handlers can attach it as a span attribute.
4. `observe(...)` runs the lambda inside the Observation's scope; on exception, this helper records the error, stops the Observation, and rethrows the exception.

The example hardcodes `web` for clarity. In a real application serving both APIs and jobs, pass a **normalized** value (`web` or `batch`) into the service; never pass free-form request strings as low-cardinality tags.

### 2.2. Commonly used APIs

| API | Meaning | When to use |
| --- | --- | --- |
| `Observation.createNotStarted(name, registry)` | Creates an unstarted Observation with a stable name | Defining operation boundaries |
| `lowCardinalityKeyValue(key, value)` | Adds a key-value with a bounded value set | Metric labels and grouping attributes |
| `highCardinalityKeyValue(key, value)` | Adds a key-value with many distinct values | Tracing specific executions |
| `lowCardinalityKeyValues(KeyValues)` | Adds a group of low-cardinality key-values | When multiple keys are prepared together |
| `highCardinalityKeyValues(KeyValues)` | Adds a group of high-cardinality key-values | When multiple related attributes apply |
| `observation.error(exception)` | Records an error during the operation | When managing lifecycle manually |
| `observe(Runnable)` / `observe(Supplier<T>)` | Runs work, manages lifecycle and scope | Concise approach for many operations |

Specific methods and overloads must match the Micrometer version used by your Spring Boot version. When sharing a key contract, define key names as constants or use `KeyName` in Observation documentation to prevent typos.

## 3. Attaching multiple high-cardinality key-values

When an invocation needs multiple attributes for analysis, `KeyValues` describes a group of metadata. Example with two **non-sensitive** values: attempt ID and subtask reference.

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;

KeyValues traceDetails = KeyValues.of(
        KeyValue.of("inventory.attempt.id", attemptId),
        KeyValue.of("inventory.step.reference", stepReference));

Observation.createNotStarted("inventory.reserve", observationRegistry)
        .lowCardinalityKeyValue("inventory.channel", "batch")
        .highCardinalityKeyValues(traceDetails)
        .observe(() -> inventoryGateway.reserve(sku, quantity));
~~~

In this example `stepReference` is an internal pseudonymous run reference that may take many distinct values. Attach it only when the data genuinely aids investigation. Even though `KeyValues` supports multiple attributes, never copy full request bodies, domain objects, or stack traces into tags.

### 3.1. Choosing stable key names

Prefer lowercase, namespaced, meaningful segments such as `inventory.attempt.id` and `inventory.operation`. Do not vary arbitrarily between `attemptId`, `attempt_id`, and `inventory.attempt.id`. Avoid dynamic data inside **key names**; values change per request, while key names must stay stable.

The `exception.message` field often varies widely and can contain payloads or sensitive data, so avoid attaching it carelessly. Prefer `error.type` or `failure.reason` with a fixed set of values when aggregating by failure kind; detailed diagnostics belong only in storage governed by appropriate retention policies.

## 4. When a shared contract is needed: using Observation.Context and ObservationConvention

Attaching key-values inline is convenient for small operations. However, when multiple services/modules instrument `inventory.reserve`, tag names easily diverge. In that case, extract the mapping from business data into tags into an **ObservationConvention**, keeping per-execution data in a strongly typed **Observation.Context**.

### 4.1. Declaring the business context

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;

final class InventoryReserveContext extends Observation.Context {
    private final String channel;
    private final String attemptId;

    InventoryReserveContext(String channel, String attemptId) {
        if (!"web".equals(channel) && !"batch".equals(channel)) {
            throw new IllegalArgumentException("Unsupported channel");
        }
        this.channel = channel;
        this.attemptId = attemptId;
    }

    String channel() {
        return channel;
    }

    String attemptId() {
        return attemptId;
    }
}
~~~

### 4.2. Convention generating consistent KeyValues

~~~java
package com.example.orders.observation;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

final class InventoryReserveConvention
        implements ObservationConvention<InventoryReserveContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(InventoryReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("inventory.operation", "reserve"));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.attempt.id", context.attemptId()));
    }
}
~~~

### 4.3. Creating an Observation with the convention

~~~java
InventoryReserveContext context =
        new InventoryReserveContext(channel, attemptId);

Observation.createNotStarted(
        null,                             // No custom convention passed yet.
        new InventoryReserveConvention(), // Default convention.
        () -> context,
        observationRegistry)
    .observe(() -> inventoryGateway.reserve(sku, quantity));
~~~

In convention-supporting factories, the typical selection order is: **explicitly passed custom convention**, then a **global convention in the registry supporting the context**, then the passed **default convention**. Therefore, if the application registers a matching `GlobalObservationConvention`, it can override the default in this example. When guaranteeing exact metadata output, verify which convention is actually chosen.

An enum implementing `ObservationDocumentation` can publish operation names, low/high-cardinality key names, and default conventions to generate instrumentation docs. It supports **the contract**, yet does not automatically block invalid tags at runtime or replace tests.

## 5. Getting metadata into tracing and correlating logs

Sequence diagram of an order creation request:

~~~mermaid
sequenceDiagram
    participant User as Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Backend as Trace backend
    User->>Order: POST /orders
    Note over Order: HTTP server span
    Order->>Order: Observation inventory.reserve
    Note over Order: high: inventory.attempt.id=attempt-...
    Order->>Inventory: HTTP + traceparent
    Inventory-->>Order: Timeout or result
    Order-->>Backend: Export span if kept by sampling
    Order-->>User: HTTP response
~~~

When the tracing bridge/handler creates a span for a custom observation, high-cardinality attributes identify **which specific reservation attempt** appears in the trace. When using OpenTelemetry via Micrometer Tracing, data still flows through an exporter (e.g., OTLP), a Collector, and a trace backend before appearing in the query UI.

A single request can simultaneously produce:

- **Metrics:** `inventory.reserve` processing time and error rate, grouped by `inventory.channel`.
- **Trace:** HTTP server, custom `inventory.reserve`, and HTTP client spans, sharing a trace ID when context is preserved.
- **Logs:** timeout events with error codes or dependency names, plus trace ID/span ID when logging is integrated with tracing.

### 5.1. High-cardinality attributes do not automatically propagate to other services

W3C Trace Context typically carries `traceparent` (and optionally `tracestate`) over HTTP to link spans across services. A **span attribute** like `inventory.attempt.id` is not automatically included in `traceparent`, so the receiving service **will not receive that value** merely because the caller attached `highCardinalityKeyValue`.

If a piece of metadata truly needs to cross to downstream services:

1. Clearly define its business purpose, scope, and data policy.
2. Pick an appropriate transport mechanism, such as a controlled business header or explicitly configured tracing baggage.
3. Restrict allowed fields, size, count, and data lifetime; avoid carrying tokens, emails, or personal content.
4. Verify on both ends that values arrive where expected without causing unnecessary metadata fan-out.

Never use baggage merely to "forward all span attributes," because metadata will traverse many services and can leak into logs, proxies, or trace backends. When correlation alone is needed, **trace ID** is usually sufficient to link signals together.

### 5.2. Preserving scope in asynchronous processing

When execution hops from an HTTP thread to `@Async`, an executor, Reactor, or messaging, trace context may not follow automatically. As a result, a custom observation inside an async task might start a brand-new root trace instead of nesting under the initial HTTP span.

In Spring Boot, use Spring-managed HTTP clients to receive built-in instrumentation. For executors, configure context propagation matching your Spring Framework/Micrometer version (e.g., `ContextPropagatingTaskDecorator` in Spring Framework 6.1+) and verify the trace hierarchy in the backend. **Attaching a high-cardinality key will not fix broken context propagation.**

### 5.3. Writing correlated logs without leaking metadata

Example structured log (illustrative data):

~~~text
2026-11-22T10:15:23Z WARN service=order-service
traceId=9cd1... spanId=7b21... event=inventory_reservation_failed
reason=upstream_timeout dependency=inventory-service duration_ms=2400
~~~

Look up the trace by trace ID to view the `inventory.reserve` span and its attributes; then pivot back to logs using the same trace ID to inspect timeout details. You do not need to copy every high-cardinality attribute into logs: include enough signal to investigate while respecting security, retention, and access controls.

## 6. Configuring Spring Boot to observe the results

In a Spring Boot application using Micrometer, enable Actuator and add the appropriate registry/tracing bridges:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // When distributed tracing with OpenTelemetry is needed:
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

An **illustrative configuration for Spring Boot 3.x in a development environment**, assuming an OTLP Collector is listening on localhost:

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
  tracing:
    sampling:
      probability: 1.0 # For testing only, increases chance of observing every trace
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces

logging:
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-}]"
~~~

Notes:

- `/actuator/prometheus` is only available with the Prometheus registry and matching exposure; in production, restrict access and network exposure.
- `probability: 1.0` keeps traces during hands-on labs, yet increases trace volume. In production, tune sampling based on traffic, budget, and investigative goals.
- OTLP configuration only defines where traces are sent; the Collector and backend must still be running, reachable, and properly configured.
- Property names, tracing settings, and auto-configuration vary across Spring Boot/Micrometer lines; cross-check against your project's actual version.
- The logging pattern example only illustrates MDC correlation; if the app uses JSON logging or custom Logback appenders, inspect the real output.

**Do not assume high-cardinality metadata exists in the backend just because the code was written.** You need the full chain of instrumentation, handlers, sampling, exporter, and backend.

## 7. Sampling and metadata visibility

A high-cardinality attribute usually helps investigations only when the span carrying it is **recorded and stored**. If the application samples 10% of traces, a specific failing request can easily fall among the 90% of requests whose traces are not saved.

| Situation | What may happen | Correct conclusion |
| --- | --- | --- |
| Observation runs, tracing unconfigured | Metrics may appear without spans | Check handler/bridge |
| Tracing configured, request not sampled | No trace in backend | Do not claim the request never ran |
| Span exists but attribute is missing | Convention/tag added at wrong time or handler ignores key | Inspect context and handler |
| Span created in app but exporter fails | Backend lacks the trace | Check queues, exporter errors, and Collector |
| Trace exists but splits between two services | Lost propagation or async scope | Check `traceparent`, client, and executor |
| Trace and high attribute exist | Can search request by attribute if backend indexes/filters it | Query performance depends on backend and setup |

**Head-based sampling** decides upfront, so it can miss rare errors. **Tail-based sampling** can retain traces based on error status or latency after collecting spans, though it requires a capable Collector pipeline and more resources. With either approach, **metrics and well-structured logs** remain essential for spotting trends across total traffic.

Beyond sampling, account for **retention, span attribute count limits, value length limits, ingest quotas, and indexing policies**. Overly long values may be truncated or dropped, and an attribute appearing on a span does not guarantee the backend supports cheap filtering by that attribute.

## 8. Security rules when attaching metadata

Traces are often broadly accessible to development and operations teams. Therefore, **high cardinality is not a safe zone for sensitive information**.

| Proposed data | Decision | Explanation |
| --- | --- | --- |
| Random UUID for one attempt | Acceptable | Useful for finding traces; reveals no user info by itself |
| Operation name or normalized error category | Use low-cardinality where appropriate | Easy to aggregate with few variants |
| Real Order ID | Evaluate and check policies | Can become a user-linkable identifier |
| Email, phone number, address | Do not collect by default | Personal data, unnecessary on every span |
| Access tokens, cookies, passwords | Never collect | Authentication secrets |
| Raw request/response bodies | Avoid collecting | May contain sensitive data and bloat size |
| Uncontrolled exception messages | Do not attach freely | May leak SQL, payloads, or identifiers |

Recommended practices:

1. **Minimize collection:** every key must have a clear investigative justification.
2. **Pseudonymize and normalize:** prefer internal IDs that cannot reveal personal data; never treat raw hashes of secrets as "anonymous."
3. **Bound sizes:** enforce maximum value lengths and attribute counts per span.
4. **Control access:** restrict who can view traces, logs, and query by attributes.
5. **Enforce retention and deletion policies:** do not keep data longer than needed and permitted.
6. **Review propagation:** a propagated key traverses more components than an attribute confined to the current span.

Never create high-cardinality metadata from user-supplied strings without validation, length limits, and data classification.

## 9. Testing metadata with TestObservationRegistry

`micrometer-observation-test` provides `TestObservationRegistry` to verify executed Observations **without starting a Collector or trace backend**. For `InventoryReservationService`, a test can verify that metadata lands in the right cardinality bucket.

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class HighCardinalityObservationTest {

    @Test
    void recordsAttemptIdAsHighCardinalityMetadata() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("inventory.channel", "web")
                .highCardinalityKeyValue("inventory.attempt.id", "attempt-demo-001")
                .observe(() -> { /* simulate successful reservation */ });

        assertThat(registry)
                .hasSingleObservationThat()
                .hasBeenStopped()
                .hasNameEqualTo("inventory.reserve")
                .hasLowCardinalityKeyValue("inventory.channel", "web")
                .hasHighCardinalityKeyValue(
                        "inventory.attempt.id", "attempt-demo-001")
                .doesNotHaveError();
    }
}
~~~

This test proves the name, lifecycle, and metadata at the **Observation runtime**. It does not prove the metadata made it into an OpenTelemetry span, was shipped by the exporter, or was indexed by the backend.

### 9.1. Additional tests worth writing

- **Error path:** lambda throws an exception; verify the Observation stops and records the error using your version's testing API.
- **Channel values:** allow only `web` and `batch`; reject arbitrary client-supplied labels.
- **No tag leakage:** use an appropriate metrics registry to prove `inventory.attempt.id` never appears in metric labels.
- **Convention:** verify default/global/custom conventions actually resolve the expected names and key classifications.
- **Tracing integration:** verify in a test environment with suitable sampling that a recorded trace carries expected attributes and valid span links.
- **Propagated context:** across HTTP and async hops, verify upstream/downstream trace IDs match when the flow requires correlation.
- **Security:** verify no tokens, personal info, or sensitive payloads appear in traces and logs.

Runtime check example:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/prometheus
~~~

With Prometheus, the timer can appear as duration and count series, yet **must not carry an `inventory_attempt_id` label**. Exact metric names may change per registry naming conventions; if missing, trigger at least one execution and inspect registry and handler configuration.

## 10. Investigating a slow request with high-cardinality metadata

Suppose order creation API p95 jumps from 450 ms to 2.8 seconds. A sampled trace shows the `inventory.reserve` span lasting 2.4 seconds with `inventory.attempt.id=attempt-demo-001`. Logs sharing the same trace ID show `upstream_timeout`.

Evidence-based investigation workflow:

1. **Metrics establish scale:** inspect request rate, 5xx ratio, p95/p99, and shifts across deployments, segmented by `channel` if designed in the contract.
2. **Trace pinpoints the bottleneck:** open the captured slow trace and inspect the timeline from HTTP server → custom `inventory.reserve` → HTTP client → upstream.
3. **High-cardinality metadata identifies the attempt:** use `inventory.attempt.id` to distinguish the failing attempt from retries or other steps, if the backend supports querying that attribute.
4. **Logs supply event details:** search logs by trace ID to examine timeout codes, dependency identity, retries, and related warnings.
5. **Dependency metrics confirm the trend:** look for connection pool saturation, growing queues, or timeouts in `inventory-service`.
6. **Remediate and re-measure:** adjust timeouts, bound concurrency, roll back, or fix upstream root causes; monitor error rates and latency afterward.

Never treat a single trace as proof that **all requests** fail the same way. Metrics show system-wide trends; traces depict one execution path; logs reveal specific conditions. If a trace is absent due to sampling, continue investigating with metrics and structured logs.

### 10.1. What if retries produce multiple attempts?

If one HTTP request calls `inventory-service` up to three times, you can have **one parent observation for the whole operation** and **one child observation per attempt**. Each child carries its own `inventory.attempt.id` or an appropriate retry index.

~~~mermaid
flowchart TB
    Parent["POST /orders - shared trace ID"] --> Reserve["Overall inventory.reserve"]
    Reserve --> A1["attempt 1: timeout"]
    Reserve --> A2["attempt 2: timeout"]
    Reserve --> A3["attempt 3: success"]
    A1 --> Attr1["high: attempt.id=A"]
    A2 --> Attr2["high: attempt.id=B"]
    A3 --> Attr3["high: attempt.id=C"]
~~~

This design helps when explicitly measuring retry overhead, yet avoid creating spans for trivial tight loops. Every span has a cost and should represent a meaningful technical boundary. Sometimes retry indices `1`, `2`, `3` are enough to clarify ordering without generating extra IDs if no correlation need exists.

## 11. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting request IDs in `lowCardinalityKeyValue` | Huge number of metric series | Move to high cardinality if genuinely needed, or remove |
| Attaching email/token in `highCardinalityKeyValue` | Sensitive data enters trace backend | Do not collect; use controlled pseudonymous IDs |
| Confusing high-cardinality metadata with baggage | Downstream does not receive expected value | Design explicit propagation with allowlists |
| Renaming keys inconsistently across services | Hard to search and compare | Standardize via shared convention/contract |
| Attaching attributes after `stop()` | Handlers may ignore them | Attach before or at the right point in lifecycle |
| Assuming metadata guarantees a trace | Data may be dropped by sampling/exporter | Verify tracing bridge, sampling, Collector/backend |
| Copying full request body into tags | High cost, potential data leak | Extract only essential metadata, truncate and validate |
| Treating traces as durable audit logs | Data lost via sampling/retention | Store business state in dedicated data stores |
| Adding too many attributes per span | Bloated payloads and truncation limits | Set metadata budgets, limit count and length |
| Only unit-testing Observation | Misses exporter/propagation bugs | Add pipeline integration tests |

## 12. Pre-production checklist

| Item to verify | Expected evidence |
| --- | --- |
| High-cardinality keys have clear purpose | Specific investigative question tied to each key |
| Stable key naming contract exists | Consistent documentation and conventions |
| No sensitive data included | Verified input sources, length limits, and access controls |
| Low-cardinality tags contain no dynamic IDs | Metrics have bounded label sets |
| Metadata attached at right lifecycle point | `TestObservationRegistry` verifies names, tags, and stop |
| Metrics verified independently | Queries/endpoints show data without high-cardinality labels |
| Tracing verified independently | Spans/attributes appear in backend when sampled |
| HTTP/async propagation works | Traces show accurate parent-child links |
| Logs are correlated yet safe | Trace ID present when needed without copying sensitive metadata |
| Exporters and retention monitored | Pipeline error signals and storage limits tracked |

## 13. Hands-on exercise

**Context:** A Spring Boot application exposes `POST /orders`, calls `inventory-service`, and saves the order. When upstream times out, the on-call team wants to distinguish individual attempts while keeping metrics low-cardinality.

**Tasks:**

1. Add a custom observation `inventory.reserve` around the stock reservation call.
2. Attach `inventory.channel` with values `web` or `batch` using `lowCardinalityKeyValue`.
3. Generate a pseudonymous UUID per attempt and attach `inventory.attempt.id` via `highCardinalityKeyValue`.
4. Write unit tests with `TestObservationRegistry` checking names, high/low metadata, lifecycle, and exception paths.
5. Inspect metrics from the appropriate registry and confirm the attempt ID never becomes a series label.
6. Configure test tracing with suitable sampling and an exporter to a backend; locate a span carrying `inventory.attempt.id`.
7. Test calls through another HTTP service and through an executor; explain when trace context breaks and why high-cardinality metadata does not travel over HTTP automatically.
8. Trigger a timeout error, correlate metrics, traces, and logs by trace ID; note which data might be missing due to sampling and exporter settings.
9. Assess the risk if a colleague proposes replacing `attempt.id` with customer email or the request body.

**Expected deliverables:** instrumentation code, observation tests, metric screenshots/queries free of dynamic IDs, one sample span showing the high-cardinality attribute (if ingested by the backend), and a brief analysis of timeouts, propagation, sampling, and privacy.

## 14. Key takeaways

Attaching **high-cardinality metadata** to a custom Observation helps explain **one specific execution** inside a distributed trace. `highCardinalityKeyValue(...)` fits multi-valued diagnostic details for investigation, while `lowCardinalityKeyValue(...)` is reserved for small bounded label sets used in metric aggregation. For larger systems, use `Observation.Context` and `ObservationConvention` to keep naming and key contracts uniform.

High-cardinality metadata **is not automatically baggage, is not automatically written to logs, does not guarantee a trace is saved, and is not a place for sensitive data**. Monitoring errors, latency, and application behavior in production requires pairing metadata properly with context propagation, sampling, exporters, metrics, logs, and thorough testing.

**References:**

- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
