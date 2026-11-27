# PrometheusMeterRegistry in Spring Boot: Registering, Exporting, and Querying Metrics

A Spring Boot application already has `Counter`, `Timer`, or `Gauge` instruments, yet the Prometheus dashboard shows no data. The root cause may not be in instrumentation at all: the meters are recorded correctly, but the application lacks a Prometheus registry, the endpoint is not exposed, Prometheus is scraping the wrong address, labels do not match the query, or the time series were dropped by configuration. To investigate accurately, you need to understand the role of **`PrometheusMeterRegistry`** across the entire metrics pipeline.

Within the **SPRING_BOOT_OBSERVABILITY** module, setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing requires clearly separating **collecting metrics**, **translating metrics into a backend-compatible format**, **propagating trace context**, and **exporting traces**. This lesson belongs to the **Meter registry and exporter** chapter and focuses on `PrometheusMeterRegistry`: how the registry turns meters into Prometheus data, configuring it via Actuator, testing scrapes, managing histograms and tags/cardinality, and combining metrics with logs and traces to diagnose errors and latency in production environments.

## Learning Objectives

After this lesson, you will be able to:

1. Explain `PrometheusMeterRegistry`, Prometheus's **pull/scrape** model, and how it differs from the generic `MeterRegistry`.
2. Set up `spring-boot-starter-actuator` with `micrometer-registry-prometheus` for a Spring Boot application.
3. Register or observe `Counter`, `Gauge`, `Timer`, and histograms, inspect scrape output, and verify metric names and units.
4. Write PromQL queries for request rate, error ratio, p95, and SLO threshold compliance when histograms are properly configured.
5. Bound label cardinality, secure metrics endpoints, and pinpoint mismatches between the registry, scrape target, and backend.
6. Test the registry without a Prometheus server, then verify the end-to-end pipeline in a staging environment.
7. Distinguish a metrics exporter from a tracing exporter, sampling, and propagation, and correlate observability signals.

## 1. What Is PrometheusMeterRegistry?

Micrometer provides the `MeterRegistry` abstraction so applications can measure data without coupling business logic to a specific backend. `PrometheusMeterRegistry` is the implementation for Prometheus: it holds and exposes meter representations in a format Prometheus can scrape. Instead of the application actively calling an API to push every counter increment to Prometheus, **the Prometheus server actively requests data from an HTTP endpoint**.

| Component | Role | Example |
| --- | --- | --- |
| `Counter` | Counts monotonically increasing events | Total orders processed |
| `Timer` | Records count and duration of completed operations | Order creation latency |
| `Gauge` | Reads current state | Number of pending orders |
| `MeterRegistry` | Stores/registers meters and coordinates representation | Bean injected into a Spring service |
| `PrometheusMeterRegistry` | Registry that formats metrics for Prometheus | `registry.scrape()` |
| Actuator `/actuator/prometheus` | HTTP endpoint exposing the registry's data | URL for Prometheus to scrape |
| Prometheus server | Scrapes periodically, stores time series, and runs PromQL | Dashboards, recording rules, alert rules |
| Grafana or another UI | Visualizes and analyzes metrics | p95, error rate, backlog panels |

A `PrometheusMeterRegistry` **is not a Prometheus server** and does not build dashboards on its own. It is just one link in the application's metrics pipeline.

### 1.1. Data Flow from Spring Boot to Dashboard

~~~mermaid
flowchart LR
    Service["Spring Boot<br/>Business code"] --> Observation["Micrometer Observation"]
    Service --> Meters["Counter / Timer / Gauge<br/>JVM, HTTP, business"]
    Observation --> MeterHandler["MeterObservationHandler"]
    MeterHandler --> Meters
    Meters --> Registry["PrometheusMeterRegistry"]
    Registry --> Endpoint["Actuator /actuator/prometheus"]
    Prom["Prometheus server"] -- "HTTP GET per scrape_interval" --> Endpoint
    Endpoint -- "Time series + labels + values" --> Prom
    Prom --> Query["PromQL / recording rules"]
    Query --> Grafana["Dashboard / Alerting"]
~~~

In the standard **pull** model:

1. Code and instrumentation record measurements into meters, or gauges supply values when read.
2. `PrometheusMeterRegistry` prepares a representation suitable for the scrape format.
3. Actuator serves the registry's output at `/actuator/prometheus`.
4. The Prometheus server samples periodically per `scrape_interval` and stores the data in its TSDB.
5. Dashboards or alerts execute PromQL to analyze time windows.

**Without a scrape, Prometheus has no data**, even if Actuator is displaying the meter accurately. Conversely, Prometheus reporting a target as `UP` only proves the scrape succeeded; it does not prove every expected business metric has been registered or has received traffic.

### 1.2. Distinguishing Push vs. Pull

| Property | Prometheus pull/scrape | Push-based metrics exporter |
| --- | --- | --- |
| Initiator | Prometheus server calls the endpoint | Application/agent/collector sends data |
| Data path | HTTP scrape of the target | Periodic or batched push |
| Port exposure | Prometheus needs access to the endpoint | Application needs connectivity to the receiver |
| Failing target detection | Typically based on `up` and scrape health | Depends on pipeline, queues, and exporter signals |
| Usage in Spring Boot | `PrometheusMeterRegistry` + Actuator | Another registry/exporter, e.g., OTLP metrics |

**Prometheus Pushgateway** is a specialized component and should not be treated as the default replacement for scraping long-running services. For continuously running HTTP applications, pull/scrape is usually the easiest baseline model to operate.

## 2. Setting Up Spring Boot and Actuator

This example targets a **Spring Boot 3.x** application with matching dependency management/BOM. In `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

`spring-boot-starter-actuator` integrates Micrometer and observability endpoints. `micrometer-registry-prometheus` provides the Prometheus registry implementation. When auto-configuration conditions are met, Spring Boot creates and configures the registry and appropriate meters; **you do not need to manually declare a `PrometheusMeterRegistry` bean in every service**.

### 2.1. Configuring application.yml

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  metrics:
    tags:
      application: order-service
      environment: staging
~~~

This is a **staging/test environment** configuration. In production, protect the endpoint using a management network, ingress rules, authentication/authorization, or equivalent controls; do not expose `/actuator/prometheus` to the public internet. Common tags such as `application` and `environment` associate time series with a service/environment, but they must have bounded, stable values.

The endpoint usually appears at `http://localhost:8080/actuator/prometheus` if the application runs on port 8080 and does not change the management base path or port. For different setups, verify the actual URL.

### 2.2. Checking Each Layer

~~~bash
curl -i http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/prometheus
~~~

Do not conflate these three endpoints:

- `/actuator/health` returns application health status from configured indicators; `UP` does not guarantee all business metrics have data.
- `/actuator/metrics` is Spring Boot Actuator's diagnostic endpoint for listing and inspecting meters by Micrometer name.
- `/actuator/prometheus` serves the **scrape format** for Prometheus. Names at this endpoint may differ from the original meter names.

Send at least one request to a business route and then check `http.server.requests` and your custom meters. Some meters only appear after they are registered or receive measurements.

### 2.3. Configuring Prometheus Server to Scrape

A minimal `prometheus.yml` example for local development when Prometheus and Spring Boot can reach each other directly via `localhost:8080`:

~~~yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "order-service"
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["localhost:8080"]
        labels:
          environment: staging
~~~

If Prometheus runs **inside another container**, `localhost:8080` points to the Prometheus container itself, **not automatically to the Spring Boot application**. Replace the target with a reachable DNS/service name in that network, such as `order-service:8080` when the container environment provides that name. In Kubernetes, target discovery and scraping can be handled by service discovery, Prometheus Operator, or `ServiceMonitor`/`PodMonitor`; this is not an automatic feature of a single Java bean.

In the Prometheus UI, check the target status and query:

~~~promql
up{job="order-service"}
~~~

`up=1` generally indicates the target scrape succeeded; `up=0` indicates the scrape failed. If the target does not appear at all, it is likely a discovery or configuration issue rather than the application itself. Do not use `up` to confirm a specific metric exists: query that series name directly.

## 3. Metric Names, Labels, and Prometheus Format

Micrometer uses dot-separated names like `http.server.requests`, `jvm.memory.used`, and `orders.checkout.duration`. The Prometheus registry converts names and units into the appropriate metrics format. Common illustrative examples:

| Micrometer Meter | Common Prometheus Output | Explanation |
| --- | --- | --- |
| `http.server.requests` (Timer) | `http_server_requests_seconds_count` and `_seconds_sum` | Request count and total seconds |
| `orders.checkout.duration` (Timer) | `orders_checkout_duration_seconds_count` | Timer with normalized name/unit |
| `jvm.memory.used` (Gauge) | `jvm_memory_used_bytes` | Memory value in bytes |
| `orders.processed` (Counter) | `orders_processed_total` | Cumulative counter |
| `orders.queue.pending` (Gauge) | Gauge name may include unit such as `_tasks` | Current value reading |

These are **common conventions**, not guaranteed output names across every version/provider. Always inspect `/actuator/prometheus` before using names in queries or alerts.

### 3.1. Counters and Resets After Restart

A counter is a cumulative value over a process's lifetime, for example:

~~~text
# Simulated text example, not verbatim scrape output
orders_processed_total{application="order-service",channel="web"} 1250
~~~

If the process restarts, the counter resets to its initial value. To measure processing rate, use:

~~~promql
sum(rate(orders_processed_total{application="order-service"}[5m]))
~~~

`rate` calculates the per-second rate of increase over the window, handling counter resets according to Prometheus semantics. If you want to estimate **the number of events** in a window, use `increase(...[5m])`. Never manually subtract two raw scrape numbers when restarts or scrape failures can occur.

### 3.2. Gauges Are Point-in-Time Observations

A gauge like `orders.queue.pending` represents the current backlog. Do not apply `rate(gauge[5m])` as if it were a counter. You can inspect the raw series directly, or use `avg_over_time` and `max_over_time` to analyze average or peak levels **across scraped samples**.

A backlog that spikes and drains completely between two scrapes may go unobserved. If you want to count total work received and completed, add corresponding counters rather than relying solely on a gauge.

### 3.3. Micrometer Tags Become Prometheus Labels

~~~java
Counter counter = Counter.builder("orders.processed")
        .description("Number of processed orders")
        .tag("channel", "web")
        .register(meterRegistry);

counter.increment();
~~~

The tag `channel=web` may be exported as label `channel="web"`. Deployment setups often add `job`, `instance` from target configuration, and other labels. A label that changes on every request, such as `order_id` or `trace_id`, can cause cardinality to explode.

**Never put passwords, access tokens, emails, phone numbers, request payloads, or user IDs into metric labels.** Distinguish labels with finite value sets (suitable for metrics) from high-cardinality metadata (consider putting into tracing only when truly needed and safe).

## 4. Using PrometheusMeterRegistry Directly

In Spring Boot, prefer injecting the generic `MeterRegistry` managed by the framework. When testing a registry in isolation, writing a standalone library, or demonstrating the API, you can instantiate `PrometheusMeterRegistry` manually.

**Version note:** Micrometer uses the newer Prometheus Java client in modern releases (for example Micrometer 1.13+). The new registry import is `io.micrometer.prometheusmetrics.PrometheusMeterRegistry`. Older guides using `io.micrometer.prometheus.PrometheusMeterRegistry` and the `micrometer-registry-prometheus-simpleclient` module may not apply to configurations using the new client. Choose the dependency, package, and API matching the **Spring Boot BOM you are running**; do not mix the two client branches arbitrarily.

### 4.1. Java Example Without a Spring Container

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;

import java.time.Duration;

public class PrometheusRegistryDemo {
    public static void main(String[] args) {
        try (PrometheusMeterRegistry registry =
                     new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {

            Counter processed = Counter.builder("orders.processed")
                    .tag("channel", "web")
                    .register(registry);
            processed.increment(3);

            Timer reservation = Timer.builder("orders.reservation")
                    .description("Duration of reserving inventory")
                    .tag("operation", "reserve")
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(Duration.ofMillis(500))
                    .register(registry);
            reservation.record(Duration.ofMillis(120));
            reservation.record(Duration.ofMillis(750));

            String scrapeText = registry.scrape();
            System.out.println(scrapeText);
        }
    }
}
~~~

The code above:

1. Creates a standalone registry and registers a `Counter` and a `Timer`.
2. Records three processed orders and two inventory reservation durations.
3. Enables a histogram and a bucket at the 500 ms threshold for the timer (if supported by the registry).
4. Calls `scrape()` to obtain the **text payload** without running a Prometheus server.
5. Closes the registry when the example finishes.

Actual output may include series such as `orders_processed_total`, `orders_reservation_seconds_count`, `orders_reservation_seconds_sum`, and buckets `orders_reservation_seconds_bucket`. Exact names, HELP/TYPE metadata, and formatting depend on the client/registry version.

**In a Spring Boot application, do not repeat this registry initialization on every request or inside every service.** If you instantiate your own registry separate from the bean exposed by Actuator, metrics recorded to it will not appear at `/actuator/prometheus`.

### 4.2. Injecting the Registry into a Spring Boot Service

A cleaner pattern in real applications:

~~~java
package com.example.orders;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderMetrics {
    private final Counter processedWebOrders;

    public OrderMetrics(MeterRegistry registry) {
        this.processedWebOrders = Counter.builder("orders.processed")
                .description("Processed orders")
                .tag("channel", "web")
                .register(registry);
    }

    public void processedSuccessfully() {
        processedWebOrders.increment();
    }
}
~~~

The counter is registered **once when the bean is created**, then incremented whenever the business event succeeds. If `orders.processed` is defined as completed orders, **do not increment the counter before the transaction actually succeeds**. For `web`/`batch` sources, normalize the channel and keep a bounded set of meters.

When the system already has an `Observation` and a metrics handler measuring the same operation, designate a single primary source to avoid registering or double-counting metrics with the same meaning.

## 5. Histograms, Percentiles, and SLOs with PrometheusMeterRegistry

In systems that need to track p95/p99 latency, `Timer` can export a **classic histogram** with cumulative buckets. Example Spring Boot configuration:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms, 300ms, 500ms, 1s
      minimum-expected-value:
        http.server.requests: 1ms
      maximum-expected-value:
        http.server.requests: 5s
~~~

These properties apply to the `http.server.requests` meter when the corresponding HTTP instrumentation is active:

- `percentiles-histogram`: enables buckets used to compute percentiles on the backend.
- `slo`: adds specific boundaries chosen for operational targets, such as exactly **500 ms**.
- `minimum-expected-value` / `maximum-expected-value`: guides the range of generated buckets to avoid useless thresholds; **these are not timeouts and do not drop requests exceeding the max**.

A classic histogram exports series of the form `_bucket{le="..."}`, `_count`, and `_sum`. `le` stands for **less than or equal to**, and for HTTP Timers exported to Prometheus the unit is typically **seconds**:

~~~text
# Illustrative data with simplified labels
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.1"} 4
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.3"} 8
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.5"} 9
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="+Inf"} 10
http_server_requests_seconds_count{method="POST",uri="/orders"} 10
http_server_requests_seconds_sum{method="POST",uri="/orders"} 3.225
~~~

Buckets are **cumulative**; do not sum buckets together to get the request count. Out of 10 requests in the example, 9 completed within 500 ms, which is 90%. This is hypothetical data to explain the formula, not automatic Spring Boot output.

### 5.1. p95 for the /orders Route

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      method="POST", uri="/orders"
    }[5m])
  )
)
~~~

In a **classic histogram**, you must preserve the `le` label when summing buckets. `histogram_quantile` interpolates across buckets, so it is an **estimate**, not an exact per-request measurement. For p99, replace `0.95` with `0.99`.

Never average p95 values across multiple instances to estimate cluster-wide p95. Sum the rate of increase of **matching bucket boundaries** first, then compute the percentile. If instances are configured with different bucket sets, aggregation becomes misleading; maintain a consistent bucket contract.

### 5.2. Share of Requests ≤ 500 ms

~~~promql
sum(rate(http_server_requests_seconds_bucket{
  method="POST", uri="/orders", le="0.5"
}[30m]))
/
sum(rate(http_server_requests_seconds_count{
  method="POST", uri="/orders"
}[30m]))
~~~

This expression returns the fraction of requests within the filtered scope that completed in at most 0.5 seconds. If your SLI definition only counts valid or successful requests, apply the **exact same filter** to both numerator and denominator, and remember that "fast" and "successful" are two distinct properties.

### 5.3. Request Rate and Error Ratio

Request throughput per second:

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/orders", method="POST"
}[5m]))
~~~

Example 5xx error ratio based on the `status` label when the real series includes it:

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/orders", method="POST", status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  uri="/orders", method="POST"
}[5m]))
~~~

With very low traffic, the denominator can be 0. Dashboards and alerts need rules for handling missing data, evaluation windows, and minimum traffic thresholds. Histograms and timers do not automatically include an error label on every custom meter: that depends on your application's conventions and instrumentation.

### 5.4. Classic Histograms vs. Native Histograms

The queries using `_bucket` and `le` in this lesson target **classic histograms**. Newer Prometheus versions can handle **native histograms** using a different data type and slightly different expressions. Do not run classic queries verbatim against a system that only exports/stores native histograms. Before choosing queries, verify the registry, scrape protocol, and actual Prometheus backend configuration.

## 6. Labels, Cardinality, and Cost Control

In Prometheus, each unique combination of **metric name + label set** creates a separate time series. If a histogram has many buckets, the series count is also multiplied by the number of bucket thresholds.

Suppose an HTTP timer has:

- 8 normalized routes;
- 3 HTTP methods;
- 4 status/outcome groups;
- 20 instances;
- 25 buckets.

The modeled bucket series count alone can reach **8 × 3 × 4 × 20 × 25 = 24,000**, before counting `_count`, `_sum`, and other labels. This number illustrates how cardinality multiplies, **not a fixed series count that Spring Boot always produces**.

| Label | Illustrative Values | Recommendation |
| --- | --- | --- |
| `application` | `order-service` | Stable, useful |
| `environment` | `staging`, `production` | Finite value set |
| `method` | `GET`, `POST` | Usually aggregatable |
| `uri` | `/orders/{id}` | Use route template, never raw URL |
| `status` | `200`, `500` | Finite, needed for error ratio |
| `instance` | Target assigned by Prometheus | Needed for operations, scales with instances |
| `order.id` | One value per order | **Never put in a metric label** |
| `trace.id` | One value per trace | **Never put in a metric label** |
| `exception.message` | Free-form string | Unsuitable; may contain sensitive data |

### 6.1. Common Tags and MeterFilter

In Spring Boot, `management.metrics.tags.*` can add stable common tags. For more complex requirements, `MeterFilter` can:

- deny meters that do not need to be exported;
- rename or transform specific tags within a controlled scope;
- enforce limit policies or manage metadata before registration.

However, `MeterFilter` does not replace proper design in business code. If a team registers a new counter for **every order ID**, fix the underlying design rather than relying on a filter to clean up after cardinality has already grown.

### 6.2. Keeping the Metric Contract Stable

Changing the name `orders.processed`, the `channel` label, or the time unit can break dashboards and alerts silently without causing HTTP request failures. Before changing a schema:

1. Inventory the PromQL queries, recording rules, and alerts in use.
2. Check the resulting series names after the registry applies naming conventions.
3. Estimate cardinality and cost when adding labels or buckets.
4. Plan a transition period if both old and new queries must be supported.
5. Record the rollout timestamp, verify the new series, and remove the old metric only when safe.

**Metrics are an operational interface**: metric contract changes should be reviewed just like application compatibility changes.

## 7. Securing and Operating the Scrape Endpoint

The `/actuator/prometheus` endpoint can reveal service names, resource metrics, routes, error states, and environment details. Therefore:

- Expose only necessary endpoints; restrict networks, ingress, and access permissions.
- Protect the transport according to your deployment environment (e.g., TLS or a private network).
- Use appropriate authentication if scraping traverses infrastructure requiring auth.
- Never put PII, tokens, or secrets into metric names, descriptions, or labels.
- Bound the number of metrics, series, and scrape payload size to avoid overloading the application or Prometheus.
- Track Micrometer, registry, and Prometheus versions; client upgrades can affect names and formats.

### 7.1. Scrape Interval and Freshness

With `scrape_interval=15s`, Prometheus normally samples every 15 seconds when the target is healthy. A gauge that fluctuates faster than the interval can miss peaks. A cumulative counter can still derive event counts between two successful samples, provided process restarts and resets are handled properly.

When a dashboard displays stale data:

1. Check target `up` status and last scrape timestamp.
2. Check network, timeouts, HTTP status, authentication, and response format.
3. Verify the application is still creating/updating that meter.
4. Check recording rules, query labels, and retention.

Shorter scrape intervals increase collection and storage cost. Choose the interval based on incident-detection requirements and metrics budget rather than assuming shorter is always better.

### 7.2. Restarts, Pod Churn, and Disappearing Series

In Kubernetes or autoscaling environments, instances come and go. Prometheus marks unscraped series stale according to staleness rules; dashboards should aggregate appropriately across active instances. Use `rate` on counters instead of treating cumulative counter values across two pods as directly comparable.

Do not attach pod UID or deployment hashes to **custom business labels** just for request debugging; infrastructure usually already manages sufficient target labels. Frequently changing labels multiply historical series and retention costs.

## 8. Testing PrometheusMeterRegistry

To verify instrumentation is registered and scrapeable, you can write an in-memory unit test. This test **does not require a Prometheus server**.

### 8.1. Unit Test for Counter and Timer

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;

class PrometheusMeterRegistryTest {

    @Test
    void exposesCounterAndTimerForScrape() {
        try (PrometheusMeterRegistry registry =
                     new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {
            Counter counter = Counter.builder("orders.processed")
                    .tag("channel", "web")
                    .register(registry);
            counter.increment(2);

            Timer timer = Timer.builder("orders.reservation")
                    .tag("operation", "reserve")
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(Duration.ofMillis(500))
                    .register(registry);
            timer.record(Duration.ofMillis(120));

            String output = registry.scrape();

            assertThat(counter.count()).isEqualTo(2.0);
            assertThat(timer.count()).isEqualTo(1L);
            assertThat(output).contains("orders_processed_total");
            assertThat(output).contains("orders_reservation_seconds_count");
            assertThat(output).contains("orders_reservation_seconds_bucket");
            assertThat(output).contains("channel=\"web\"");
        }
    }
}
~~~

**Read the assertions in context:** this test verifies the output of **the chosen Prometheus registry line**. If a Micrometer/Prometheus client upgrade changes format or naming conventions, inspect the real output and update the test intentionally rather than weakening assertions just to make it pass.

If your current dependencies use the legacy Prometheus client, adjust the imports and API to match that branch. Do not add both Prometheus registry artifacts to the classpath without evaluating the auto-configuration impact.

### 8.2. Integration Tests in Spring Boot

In a real application, integration tests should verify:

1. Spring creates `PrometheusMeterRegistry` or a registry/`CompositeMeterRegistry` wired to the Prometheus registry as configured.
2. Services inject the Spring-managed `MeterRegistry` rather than creating an isolated registry.
3. Calling business operations increments Counters or Timers as specified by the contract.
4. `/actuator/prometheus` returns HTTP 200 in a test environment where it is exposed, containing the expected series.
5. Labels such as `application`, `method`, and `uri` are normalized and free of dynamic IDs or PII.
6. Histograms include the necessary SLO buckets if the project requires p95/p99 or threshold compliance rates.

Endpoint tests should use `MockMvc` or an appropriate HTTP test client to avoid spinning up an external Prometheus instance. Unit tests check the registry and metric content, integration tests check **bean/Actuator/configuration wiring**, and end-to-end tests verify the actual Prometheus scrape and dashboard.

### 8.3. Verifying the Real Pipeline

In staging, generate a known burst of traffic, then verify each stage:

| Stage | Evidence |
| --- | --- |
| Java instrumentation | Counter/Timer changes after the operation |
| Spring registry | Meter appears in `/actuator/metrics` |
| Prometheus endpoint | Scrape text has the right series and tags |
| Prometheus target | `up=1`, no scrape errors |
| Prometheus TSDB | PromQL finds series with recent timestamps |
| Dashboard/alert | Query, window, and thresholds reflect real traffic |

If the dashboard shows no data while `/actuator/prometheus` is accurate, **do not rush to change instrumentation**. Check target discovery, networking, labels, and backend queries first.

## 9. How Do Metrics, Logs, and Distributed Tracing Work Together?

A Prometheus histogram can reveal that p95 for `POST /orders` jumped from 250 ms to 1.4 seconds over 10 minutes, but it cannot tell you which specific request stalled at the database or `inventory-service`. Traces and logs solve that part of the investigation.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Prom as Prometheus
    participant Trace as Trace backend
    Client->>Order: POST /orders
    Note over Order: HTTP Observation / Timer
    Order->>Inventory: HTTP + traceparent
    Inventory-->>Order: timeout
    Order-->>Client: HTTP 503
    Note over Order: Metrics count, error, duration
    Prom->>Order: GET /actuator/prometheus
    Order-->>Prom: Counter, histogram buckets, labels
    Order-->>Trace: Spans via exporter if kept by sampling
~~~

A sound investigation workflow:

1. **Metrics detect the trend:** request rate, error ratio, p95/p99, CPU, connection pools, queue backlog.
2. **Traces explain the path:** pick a slow trace showing the HTTP server span, business operation, and HTTP client call to `inventory-service`.
3. **Logs provide event details:** search error codes/timeouts by trace ID or within the same time window, avoiding logging sensitive payloads.
4. **Cross-check dependencies:** compare `inventory-service` latency/5xx rates, connection pool state, and rollout timestamps.
5. **Remediate and re-measure:** verify that SLOs, error budgets, and related metrics recover.

### 9.1. Trace Sampling Is Not Default Metric Sampling

With 10% trace sampling, many requests **have no stored trace**, yet the application's Timers and Counters can still record all instrumented executions. Never use "no trace found" as proof that no requests or errors occurred.

Conversely, an existing trace does not prove Prometheus scraped successfully. Pipelines can fail independently:

| Pipeline | Checkpoints |
| --- | --- |
| Metrics | Micrometer meter → `PrometheusMeterRegistry` → Actuator → scrape target → Prometheus |
| Traces | Micrometer Observation → tracing bridge/handler → sampling → exporter/Collector → trace backend |
| Logs | Logging framework → MDC/trace correlation → log transport → log backend |

### 9.2. Context Propagation and Exemplars

For spans from `order-service` and `inventory-service` to share the same trace, HTTP clients and servers must propagate and extract compatible context, such as the W3C `traceparent` header. With `@Async` or executors, proper propagation is needed across thread boundaries. **`PrometheusMeterRegistry` does not propagate trace context on its own**.

Some environments support **exemplars**: a metric sample or bucket can carry a trace reference so you can jump straight to a trace from a dashboard. Support depends on the Prometheus client, Micrometer, tracing setup, scrape format, and backend; simply adding a dependency does not guarantee exemplars work. Never put trace IDs into labels for **all time series** as a workaround, as that causes cardinality explosion.

## 10. Common Issues and Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `/actuator/prometheus` returns 404 | Missing dependency, endpoint not exposed, or wrong path/port | Check classpath, Actuator exposure, and management port |
| `/actuator/metrics` has meter, Prometheus endpoint does not | Prometheus registry not configured, meter filtered, or different registry | Inspect registry bean, dependencies, and scrape output |
| Endpoint outputs metric, Prometheus has no series | Target not discovered, scrape failing, or wrong network/auth/TLS | Check targets, `up`, and scrape errors |
| Prometheus `up=1`, but business metric missing | Meter not registered, no traffic yet, or query filters wrong labels | Search series in scrape text, then compare with PromQL |
| Counter drops after deployment | Process restarted, resetting the counter | Use `rate`/`increase` over a window |
| Gauge has no value | Observed object was GC'd or callback failed | Keep a strong reference and check callback |
| Histogram has no `_bucket` | Histogram/SLO buckets not enabled or unsupported by registry | Check distribution config and meter name |
| p95 wrong when aggregating instances | Averaged percentiles or dropped `le` | Use `sum by(le)(rate(bucket))` |
| Error ratio query returns no data | Wrong `status`/`uri` label, no traffic, or denominator is 0 | Check actual labels and request count |
| Cardinality spikes | Raw URLs, user IDs, trace IDs, or too many buckets | Bound labels, use route templates, set metrics budget |
| Metrics exist, traces are missing | Sampling, propagation, OTLP exporter, or Collector issue | Check the tracing pipeline separately |
| Traces exist, logs are uncorrelated | MDC/log pattern or scope not maintained | Check logging setup and trace/span IDs |

### 10.1. Diagnose in Order to Avoid Guessing

If `/actuator/prometheus` returns empty output or is missing a metric, start at the **application**: does the registry bean exist, has the meter been created, and is the endpoint enabled? If the endpoint has data but PromQL finds nothing, move to **Prometheus**: target, labels, network, scrape errors, retention, and query syntax. Only modify configuration or instrumentation after identifying where the data drops off.

Never try to fix a broken scrape by increasing tracing sampling; the two mechanisms are independent.

## 11. Production Configuration Checklist

| Check Item | Passing Evidence |
| --- | --- |
| Compatible Micrometer and Prometheus registry | Dependencies aligned with BOM, right Prometheus client branch |
| Spring Boot uses a unified registry | Services inject the Boot-managed registry |
| Scrape endpoint accurate and secured | Correct path/port, protected by network/auth |
| Prometheus target healthy | `up=1`, scrape duration and errors monitored |
| Clear time-series names/units | Counters, Timers, Gauges have sensible descriptions and labels |
| Histograms enabled selectively | SLO/percentile buckets only where needed |
| Bounded label cardinality | No request IDs, user IDs, or raw URLs |
| Queries handle resets/low traffic | Proper `rate`/`increase`, division-by-zero guarded |
| Multi-signal investigation ready | Able to correlate metrics with logs/traces when needed |
| Sampling/propagation understood | No false conclusions when traces are absent |
| Metrics budget in place | Series count, scrape payload, retention, and cost tracked |
| Schema changes reviewed | Dashboards, recording rules, and alerts updated together |

## 12. Hands-On Exercise: From Counter/Timer to a Prometheus Dashboard

**Context:** `order-service` has a `POST /orders` endpoint calling `inventory-service`. The operational goal is to detect rising 5xx errors and p95 latency exceeding 500 ms, while being able to pinpoint the slow step in a sample trace.

**Tasks:**

1. Add `spring-boot-starter-actuator` and `micrometer-registry-prometheus` to Spring Boot, and enable `/actuator/prometheus` in a test environment.
2. Declare a `Counter` `orders.processed` with a `channel` tag accepting only `web` or `batch`. Record the event only when the business operation completes.
3. Use built-in HTTP instrumentation or a business `Timer` to measure latency; if p95 or SLO ≤ 500 ms is needed, enable histograms and configure matching buckets.
4. Run the application, send both fast and slow requests, and inspect `/actuator/metrics` and `/actuator/prometheus`. Note the exact series names, units, and labels.
5. Configure a Prometheus scrape target, confirm `up=1`, and query `orders_processed_total`.
6. Write PromQL queries for request rate, error ratio, p95, and the fraction of requests ≤ 500 ms, using only labels that actually appear in the data.
7. Restart the application and explain why the counter resets and why `rate` is better than subtracting raw values.
8. Trigger an `inventory-service` timeout error; correlate metrics, logs by trace ID, and a slow trace if retained by sampling.
9. Intentionally misconfigure `metrics_path` in the test environment; confirm the target fails, then fix it **without modifying business code**.
10. Estimate the series count if adding 3 regions, 4 status groups, and 20 buckets across 20 instances. Explain why `order.id` must not be added to labels.

**Expected outcomes:** the application has a working Prometheus registry, a secured scrape endpoint, grounded queries, unit/integration tests verifying output, and an incident troubleshooting note distinguishing registry/scrape failures from tracing/exporter issues.

## 13. Key Takeaways

**`PrometheusMeterRegistry`** bridges Micrometer `Meter`s to the **Prometheus format collected via pull/scrape**. In Spring Boot, combining Actuator with the appropriate registry exposes `/actuator/prometheus` for the Prometheus server to scrape. Exported meter names, tags, buckets, units, and labels must always be verified in practice before using them in PromQL, dashboards, or alerts.

A reliable pipeline requires **a unified managed registry**, a secured endpoint, healthy scrape targets, low-cardinality labels, and queries that handle counter resets and histograms properly. When combined with Micrometer Observation, logs, and distributed tracing, metrics detect the scope of an incident while traces and logs explain the path and root cause; correlation still depends on each signal's sampling, context propagation, and exporter/Collector.

**References:**

- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Micrometer — Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Prometheus endpoint](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.export.prometheus)
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Prometheus — Histogram and Summary](https://prometheus.io/docs/practices/histograms/)
