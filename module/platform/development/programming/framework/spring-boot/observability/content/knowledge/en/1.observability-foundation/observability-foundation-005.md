# Observability Across the Application Lifecycle

A Spring Boot application may run fine on a developer's laptop yet respond slowly, partially fail, or behave unexpectedly when serving real users. To understand *why* that happens, development teams need data about internal system behavior, even when the questions to investigate were not known in advance. That is the purpose of **observability**.

Observability does not appear only after an application reaches production. It is a capability designed, implemented, tested, deployed, used, and continuously refined throughout the software lifecycle. In Spring Boot, **Micrometer Observation**, **metrics**, **logs**, and **distributed tracing** turn operations inside code into correlatable signals for pinpointing errors, analyzing latency, and understanding real-world application behavior.

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of observability at each stage from design through incident response and continuous improvement.
- Translate user journeys into SLIs, SLOs, measurement signals, and testing requirements.
- Distinguish metrics, logs, and traces, and correlate them when investigating a failed or slow request.
- Apply Micrometer Observation and context propagation mechanisms in a Spring Boot application.
- Recognize decisions that affect data cost and quality: tags/cardinality, sampling, exporters, security, and fault tolerance.
- Define observability acceptance criteria before deployment and use telemetry to improve the system.

## 1. From Monitoring to Observability in the Software Lifecycle

**Monitoring** typically starts with known questions: is CPU above 80%, is the HTTP 5xx count rising, is the service still available? **Observability** enables deeper inquiry into unforeseen phenomena: why is only one subset of requests slow, which step is slow, and is it tied to a new release or a downstream dependency?

The three signal types complement one another:

| Signal | Questions It Answers Well | Example in an Order Service | Limitations to Remember |
|---|---|---|---|
| **Metrics** | How many, how fast/slow, how are trends changing? | Request count, 5xx rate, p95 duration, active connections | Aggregated data rarely shows what happened inside *one* specific request |
| **Logs** | What event or decision did the application record at that moment? | Order rejected due to out-of-stock, inventory timeout, validation error | Unstructured or contextless logs are hard to search and correlate |
| **Distributed traces** | Which components did a request traverse and where was time spent? | Order API → reserve inventory → charge payment → persist order | Sampling may cause some requests to have no saved trace |

An **Observation** in Micrometer represents an operation to be observed. Depending on the configured handlers and libraries, the same observation can produce duration measurements for metrics and spans for tracing. Logs are usually emitted separately through a logging library, then linked to traces via context such as **trace ID** and **span ID**.

The observability adoption lifecycle looks like this:

~~~mermaid
flowchart LR
    A["Design goals and SLOs"] --> B["Develop and instrument"]
    B --> C["Test and verify signals"]
    C --> D["Deploy and evaluate changes"]
    D --> E["Operate and alert"]
    E --> F["Investigate, remediate, improve"]
    F --> A
~~~

Every iteration produces new insight: an incident may lead to adding a queue metric; a load test may reveal a tag with too many values; a rollback may clarify which signal truly predicts risk.

## 2. Design: Start From User Behavior and Service Goals

### 2.1. Identify Journeys and Failure Points

Suppose a system consists of **order-service** (Spring Boot), **inventory-service**, a database, and an event queue. The main journey is:

1. Client sends an order creation request.
2. order-service authenticates and validates the input.
3. order-service calls inventory-service to reserve stock.
4. The application persists the order to the database.
5. The application returns the result and publishes any required events.

Observability design questions should start from user impact:

- When order creation fails, how do we distinguish input errors (4xx), internal errors (5xx), and dependency failures?
- If a request takes 3 seconds, is the time mainly spent in validation, inventory calls, connection waits, or database queries?
- If HTTP 200/201 was returned but event publishing failed, what signal shows the business workflow is incomplete?
- Does a slow request increase queue depth or exhaust the connection pool?

Not every journey is measured by HTTP status. For asynchronous processing, also measure **job completion latency**, **retry count**, **oldest message age**, **dead-letter queue**, and relevant business states.

### 2.2. Turn Requirements Into SLIs, SLOs, and Acceptance Criteria

- **SLI (Service Level Indicator)**: a measure of user experience or reliability, such as the ratio of successful order creation requests or the ratio of requests completing within 800 ms.
- **SLO (Service Level Objective)**: the target for an SLI over a time window, such as at least 99.9% of valid requests succeeding over 30 days.
- **Error budget**: the allowable deviation from the SLO. Error-budget burn rate helps balance feature releases against reliability work.

Example design table for an order creation API:

| Concern | Illustrative SLI | Required Signals | Notes |
|---|---|---|---|
| Availability | Successful valid requests / total valid requests | Request count by route, method, status/outcome | Clarify which 4xx are client errors vs. service faults |
| Latency | Ratio of requests finishing under 800 ms; add p95 for diagnostics | Histogram of HTTP duration and each dependency's duration | Measure at the boundary users actually experience |
| Background work | Ratio of events processed before deadline | Outcome counters, duration histograms, queue age | HTTP success does not guarantee background work finished |
| System capacity | Queue depth, thread/connection pool utilization | Gauges and matching infrastructure metrics | Supporting indicators—do not replace user-experience SLIs |

**Important:** an SLO must define the calculation formula, request scope, time window, measurement system, and handling of missing data. Otherwise teams may all say "99.9%" while computing different numbers.

### 2.3. Define a Signal Contract Before Writing Code

For each measurement or event, specify:

- **Stable name and units:** seconds on the Prometheus side, counters for counts, gauges for instantaneous values where appropriate.
- **Attributes/tags:** e.g., normalized route, HTTP method, outcome, dependency type.
- **Resolution and retention:** distinguish short-term alerting data from long-term analytical data.
- **Correlation context:** trace ID, span ID, service name, environment, release version.
- **Ownership and action:** who reads the dashboard, who receives the alert, and which signals trigger rollback or investigation.

Never put emails, access tokens, street addresses, order IDs, user IDs, or unnormalized paths with arbitrary IDs into **metric tags**. A tag with millions of values can rapidly inflate time-series counts and collection cost. Keep only tags with bounded value sets that are useful for aggregation.

## 3. Development: Instrument at Meaningful Boundaries

Spring Boot combined with Actuator and Micrometer can automatically emit many metrics and observations for HTTP servers/clients, the JVM, and supported integrations. However, auto-instrumentation does not automatically understand domain steps like "inventory reserved" or "order event published".

### 3.1. Signal Flow Leaving the Application

~~~mermaid
flowchart TB
    App["Spring Boot: HTTP, business logic, data"] --> Obs["Micrometer Observation"]
    Obs --> Met["MeterRegistry / metrics"]
    Obs --> Tra["Tracing bridge / spans"]
    App --> Log["Application logs with trace ID"]
    Met --> Prom["/actuator/prometheus → Prometheus → Grafana"]
    Tra --> OTLP["OTLP exporter → Collector → trace backend"]
    Log --> Logs["Log collector → log backend"]
~~~

All three branches must be configured and verified independently. For example, traces flowing over OTLP do not mean logs automatically reach a log store; a trace ID appearing in logs does not prove the trace exporter succeeded either.

### 3.2. Reference Configuration for Spring Boot 3.x

Gradle example using Spring Boot dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Example configuration for a development environment running an OTLP Collector on localhost:

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  metrics:
    tags:
      application: order-service
    distribution:
      percentiles-histogram:
        http.server.requests: true
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces

logging:
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-}]"
~~~

Meaning and limits of this example:

- **Actuator** exposes management endpoints; when the Prometheus registry is present, **/actuator/prometheus** exposes metrics for Prometheus scraping. Endpoints must be access-restricted appropriately, especially in production.
- **Tracing bridge** connects Micrometer Tracing to OpenTelemetry. The **OTLP exporter** sends spans to the configured target; the Collector and trace backend must be running for data to be stored and queried.
- **Sampling probability = 0.1** samples roughly 10% of traces according to the probabilistic sampler. HTTP metrics continue aggregating regardless of whether a trace is sampled.
- **Histograms** increase series count and storage, yet enable percentile calculations in Prometheus. Enable them only for measurements that genuinely need percentile queries.
- The logging pattern shows how to include trace ID and span ID from MDC. If your project uses custom Logback or JSON logging configs, verify the actual output since default layouts may differ.

Artifact names, properties, and auto-configuration mechanisms can change across Spring Boot releases; when applying to a real project, verify against your exact Boot/Micrometer version. In production, OTLP endpoints, Actuator access control, TLS configuration, credentials, resource attributes, and sampling rates must be managed per environment.

### 3.3. Creating an Observation for a Business Operation

When reserving inventory is an important point for latency investigation, wrap it in an observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {
    private final ObservationRegistry observationRegistry;
    private final InventoryClient inventoryClient;

    public ReservationService(
            ObservationRegistry observationRegistry,
            InventoryClient inventoryClient) {
        this.observationRegistry = observationRegistry;
        this.inventoryClient = inventoryClient;
    }

    public void reserve(String sku, int quantity) {
        Observation.createNotStarted("inventory.reserve", observationRegistry)
                .lowCardinalityKeyValue("operation", "reserve")
                .observe(() -> inventoryClient.reserve(sku, quantity));
    }
}
~~~

In this example, **InventoryClient** is an application-defined component with a **reserve(sku, quantity)** method. **observe** manages the observation start/stop timestamps and records errors if the operation throws an exception. When the registry has suitable handlers, this operation can appear in both metrics and tracing.

An observation should represent an operation with clear meaning and boundaries. Do not create spans for every line of code, variable assignment, or element in a large loop: overly granular telemetry wastes resources and obscures key processing steps.

### 3.4. Propagating Context Across Services and Async Tasks

A trace can contain many spans. **Trace ID** identifies the entire execution chain; **span ID** identifies a single step. When service A calls service B, context must be sent over HTTP headers or an equivalent mechanism so both services belong to the same trace. The common standard is **W3C Trace Context**, using the **traceparent** header and optionally **tracestate**.

In Spring Boot, prefer HTTP clients built from Spring auto-configured builders such as **RestClient.Builder** or **WebClient.Builder** to inherit instrumentation and propagation. Building clients outside Spring's configuration can lose observations or trace propagation headers.

With thread pools, callbacks, or **@Async**, current context does not appear automatically on another thread. The following example shows how to attach **ContextPropagatingTaskDecorator** to a custom executor on Spring Framework 6.1+ (commonly paired with Spring Boot 3.2+):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncConfiguration {
    @Bean("observedExecutor")
    ThreadPoolTaskExecutor observedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

A method annotated with **@Async("observedExecutor")** uses this executor. With Reactor, messaging, or other execution libraries, verify their corresponding context propagation mechanisms. When a trace breaks at an async boundary, check propagation, client configuration, and the difference between **span not recorded** and **span dropped by sampling** before concluding a service never ran.

### 3.5. Structured Logs and Trace Correlation

Logs are most useful when they record the **business event**, **severity**, **error code**, **service**, **environment**, **timestamp**, and required correlation IDs. Example of a synthetic log:

~~~text
2026-11-22T10:15:23Z WARN [traceId=2b7a...,spanId=8c1e...]
event=inventory_reservation_failed reason=upstream_timeout
dependency=inventory-service duration_ms=2400
~~~

During an investigation, engineers can grab the trace ID from a log to open the trace, or pivot from a trace back to logs sharing the same context. In practice, log/trace backends need proper field mappings and correlation queries configured for smooth pivoting.

Never log tokens, payment details, passwords, or full request bodies by default. If a transaction identifier is needed for debugging, use an approved field complying with security and retention rules; never make it a metric tag. Avoid logging the same exception at every layer and then logging it once more at the controller, which adds noise and cost.

## 4. Testing: Observability Needs Acceptance Criteria Too

Functional tests asserting HTTP 201 prove only part of system behavior. For an observable system, test suites and acceptance checks must also verify that telemetry suffices to explain runtime outcomes.

| Stage | Observability Check | Pass/Fail Question |
|---|---|---|
| **Local development** | Send successful requests, 4xx requests, and simulated dependency failures | Do metrics increment accurately? Do logs include trace IDs when context is present? |
| **Integration/CI** | Call across two services and an asynchronous task | Does the trace link spans properly? Does a key measurement exist with stable tags? |
| **Performance test** | Steady load, bursts, timeouts, retries | Do percentiles, histograms, and saturation reflect the load? Is instrumentation overhead acceptable? |
| **Staging** | Production-like telemetry pipeline | Do exporters, collectors, and backends receive the data? Do dashboards and alerts fire as intended? |
| **Pre-release** | Compare against current release baseline | Can errors, latency, resources, and SLO impact be measured immediately after rollout? |

Local verification example while the app is running:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/prometheus
~~~

Prometheus output includes HTTP metrics only after matching requests have occurred; exact metric names depend on version and instrumentation. That the endpoint returns text does not prove Prometheus scraped successfully or that the trace exporter works—verify in the target backend.

A meaningful integration test should actively issue a request with a **known correlation ID**, inspect the trace in the receiving service, and verify at least one path lands in logs/traces. When sampling is enabled, use a test profile with full observability or a suitable verification hook; do not write tests assuming every production request keeps a trace.

### 4.1. Testing Failure Modes

Scenarios to test include: dependency timeouts, exhausted connection pools, queue backlogs, retried requests, new version rollouts, collector/exporter errors, and slow or unreachable observability backends. Business requests should not fail simply because a telemetry exporter is temporarily unable to ship data; meanwhile, operators need a separate signal to detect **telemetry loss**.

With synthetic test data, inspect distinct tag value counts. A route like **/orders/{id}** must be recorded as a route template or normalized label rather than turning each ID into a time series.

## 5. Deployment: Using Signals to Decide Roll-Forward vs. Rollback

Observability belongs in release checklists and rollout policies, not just operational dashboards:

1. **Before release:** capture baselines for request rate, error rate, p95/p99, resource usage, and key business SLIs; annotate the deployment timestamp.
2. **During canary/rolling deployment:** compare the new version against the stable version on comparable traffic where possible; check version, instance, and environment tags.
3. **When degradation appears:** use traces to isolate the slow step, logs to read failure conditions, and metrics to quantify impact; roll back or shift traffic according to agreed criteria.
4. **After release:** watch delayed effects such as backlogs, retries, and error-budget burn; update runbooks with newly observed signatures.

Comparisons must account for traffic volume and request mix. A canary handling light or skewed traffic can show noisy p95 swings; a single trace is never enough to condemn an entire release.

At release time, also deploy and validate **telemetry configuration**: exporter endpoints, secrets, quotas, retention, service/version labels, and access permissions. A release can behave correctly yet become hard to observe due to a misconfigured exporter, wrong service name, or clock skew.

## 6. Production: From Alerts to Root-Cause Investigation

### 6.1. Actionable Dashboards and Alerts

An operational dashboard typically needs signals close to user experience:

- **Traffic:** request rate or events processed per second.
- **Errors:** 5xx rate, timeouts, abnormal business rejections, event consumption errors.
- **Duration:** latency distributions and p95/p99 for critical journeys.
- **Saturation:** CPU, memory, connection pools, thread pools, queue depth, and wait times.

This is a practical way to apply **RED** (Rate, Errors, Duration) alongside resource/saturation signals. Avoid alerting on CPU spikes alone unless paired with a clear action; prioritize alerts tied to SLOs, user-facing errors, or imminent incident risk.

Reference PromQL queries for HTTP server metrics exported from Micrometer to Prometheus:

~~~promql
# HTTP 5xx ratio over 5 minutes (adjust label filters for your system)
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)
~~~

When histograms are enabled for the HTTP server timer, p95 can be computed from buckets:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{uri="/orders",method="POST"}[5m])
  )
)
~~~

These examples must be adapted to actual labels, metric names, traffic volume, time windows, and aggregation rules. When measuring an SLO for a single route, filter **both numerator and denominator** of the error rate over the same scope. Computing percentiles from histograms requires compatible buckets across instances; under low traffic, short-window percentiles are noisy. Without histograms enabled, the corresponding **_bucket** series may not exist.

Alerts should include thresholds, sustain durations, severity, owner, dashboard/runbook links, and service/environment context. For SLOs, prefer **error-budget burn-rate** alerts across multiple windows instead of one fixed 5xx threshold for every service.

### 6.2. Cross-Signal Investigation Scenario

Suppose after a release, order creation requests show p95 jumping from 450 ms to 2.8 seconds and the 5xx rate climbs. The numbers below illustrate the investigation method.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant DB as Database
    Client->>Order: POST /orders
    Order->>Inventory: reserve inventory (traceparent)
    Inventory-->>Order: timeout after 2.4 s
    Note over Order: span inventory.reserve records error
    Order-->>Client: 503 / timeout
    Note over Order,DB: Never reaches persist order step
~~~

Investigation workflow:

1. **Metrics show broad impact:** compare error rate, p95, request rate, and deployment timestamp. Confirm it is real degradation rather than a scraper outage or missing data.
2. **Traces reveal the path:** pick a slow trace if sampled and stored; observe the span where order-service waits on inventory-service for roughly 2.4 seconds. Compare with a healthy trace to pinpoint which step grew.
3. **Logs supply immediate cause:** filter logs by trace ID and time window to find **upstream_timeout** errors, retry counts, pool/connection details, and release version.
4. **Dependency metrics confirm the trend:** check inventory-service timeout rate, queue depth, and resource health; check whether other callers are affected too.
5. **Remediate and verify:** shed load, roll back, tune timeouts/circuit breakers, or fix the dependency bug based on actual cause. Re-check SLIs, traces, and logs afterward.
6. **Learn and harden:** add missing timeout tests, dashboards, or alerts; update runbooks and document fallback limits.

One slow trace is **evidence for that request**, not automatic proof for all traffic. Metrics quantify scope and trends; traces locate the execution segment; logs explain concrete conditions. Combining them makes conclusions defensible.

### 6.3. What If Traces Are Missing?

Not finding a trace in the backend does not mean the request never happened. Check in order:

- Did the request create an observation/span at that boundary?
- Did SDK/application and Collector sampling keep this request?
- Was **traceparent** propagated across proxies, HTTP clients, queues, and thread pools?
- Are the Exporter, Collector, and backend hitting errors, backpressure, or quotas?
- Are the service name, environment, time window, and search filters accurate?

**Head-based sampling** decides early with typically low overhead, yet can miss rare error requests. **Tail-based sampling** can retain traces based on outcome or latency after collecting spans, at the cost of Collector architecture and resources. At low sampling rates, lean more heavily on metrics and logs to detect issues. Also note that components running mismatched sampling policies can yield incomplete traces.

## 7. Managing Telemetry Quality as Software Quality

Observability creates value when signals are **accurate, sufficient, correlatable, and operable**. Common failure modes:

| Symptom | Likely Cause | How to Address |
|---|---|---|
| Time-series count spikes | Raw user IDs, order IDs, or unnormalized URLs in metric labels | Normalize routes; use bounded labels; audit cardinality pre-release |
| Metrics show slowness without showing where | Missing spans at business or dependency boundaries | Add observations for key steps; check instrumented clients |
| Traces split across services | Missing trace context propagation or thread switches dropping context | Check W3C headers, client auto-configuration, and executor/context propagation |
| Logs have trace IDs but trace won't open | Trace dropped by sampling, exporter failed, or backend missed ingestion | Check sampling, queues/exporters, Collector, and retention |
| Noisy alerts | Static thresholds on non-actionable signals | Design around SLOs, error budgets, sustain windows, and runbooks |
| Dashboards lose data after release | Renamed metrics/labels, wrong service name, or broken exporter | Validate telemetry contracts in CI/staging and version dashboards |
| Telemetry contains sensitive data | Logging request bodies, tokens, or identifying labels | Classify data, filter/redact, enforce access control and retention |
| Observability cost grows | Excessive sampling, histograms, or log volume | Tune to query value; cut duplicate logs, cardinality, and retention |

**Exporters and telemetry pipelines** must also be monitored: export error rate, dropped record count, ingest lag, queue memory, and quota usage. When the pipeline degrades, the app may keep serving requests while investigative capability drops. Keep bounded memory/queue limits and know how the app behaves when the backend is unreachable.

**Security and privacy** belong in the design: never put sensitive data into tags/spans/logs; separate access permissions for dashboards, logs, and traces; configure TLS, secrets, retention, and deletion policies properly. A trace ID is a correlation tool—not an authentication mechanism or blanket permission to view all related records.

## 8. Observability Acceptance Criteria for a New Feature

Before declaring an API or workflow production-ready, a team can check against these criteria:

| Criterion | Evidence of Completion |
|---|---|
| Critical journeys and SLIs/SLOs documented | Clear definitions of good/bad outcomes, windows, and traffic scope |
| Metrics reflect success, errors, and latency | Queries work in backend and match test request counts |
| Tracing spans key boundaries | Can inspect an end-to-end trace linking HTTP, business logic, and dependencies in test |
| Logs are correlated and data-safe | Logs queryable by trace ID; no unnecessary secrets or PII |
| Tags and histograms have acceptable cost | Label value counts, series volume, and telemetry throughput reviewed |
| Sampling is deliberately chosen | Sampling rate and limits on finding rare error traces understood |
| Exporters and backends verified | Signals appear in the exact tools on-call operators actually search |
| Dashboards, alerts, and runbooks ready | Responders know when to act, where to look, and first checks |
| Release usage workflow defined | Pre-deploy baseline, canary checks, rollback criteria, post-deploy verification |

You do not need to instrument every line of code to meet these criteria. Prioritize user-facing journeys, network/async boundaries, business steps that can fail, and latency-prone components.

## 9. Practice Exercise: Tracking an Order Flow Lifecycle

**Context:** You own a Spring Boot service receiving **POST /orders**, calling inventory-service, and writing to a database. The team wants confidence releasing a change to the inventory reservation step.

**Practice tasks:**

1. Write one availability SLI and one latency SLI for the API, specifying how valid requests and good requests are defined.
2. Use Spring Boot Actuator and Micrometer to observe HTTP requests; add an observation around the inventory reservation call.
3. Choose three bounded-cardinality metric labels. Explain why order ID must not be used as a label.
4. Verify that an order creation request traces across order-service and inventory-service. Try a path using **@Async** and check whether trace context is preserved.
5. Simulate an inventory-service timeout. Find the error signal in metrics, open a trace if available, look up logs by trace ID, and document your findings.
6. Propose canary monitoring thresholds and rollback criteria grounded in the system's SLIs/SLOs.

**Expected deliverable:** a brief description of the SLIs/SLOs, metrics/tracing/logging config, dashboard screenshots or query outputs, an illustrative trace, and a timeout investigation write-up. If a trace is absent due to sampling, note that limitation explicitly and prove the failure using the remaining signals.

## 10. Takeaways for Real Projects

Observability is part of the **engineering feedback loop**: operational requirements are set at design time; instrumentation is added in code; signals are verified in testing; data guides release decisions; and production lessons feed back into tests, SLOs, and architecture.

In Spring Boot, a practical starting point is **Actuator + Micrometer Observation**, then connecting **metrics**, **structured/correlated logs**, and **distributed tracing** via appropriate exporters and backends. How well you can answer questions during an incident depends equally on signal selection, context preservation across services and threads, tag/cardinality discipline, understanding sampling, and keeping the telemetry pipeline healthy.
