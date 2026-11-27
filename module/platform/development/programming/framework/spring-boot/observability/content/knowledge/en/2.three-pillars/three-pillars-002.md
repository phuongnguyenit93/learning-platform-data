# Metrics: Measuring Behavior and Health of Spring Boot Applications

> **Chapter:** Three Pillars · **Lesson:** Metrics  
> **Module:** SPRING_BOOT_OBSERVABILITY — Establish observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. What Are Metrics and What Questions Do They Answer?

A **metric** is a quantitative measurement collected over time, typically represented as a *time series*. A typical data point consists of a metric name, value, timestamp, and a set of *tags/labels* for slicing across dimensions such as HTTP method, status code, or service.

For example, instead of only knowing that one `POST /api/orders` request was slow, metrics reveal how many requests per second **the entire system** is handling, whether the 5xx error rate is rising, and how the response time distribution has changed over the last 15 minutes.

Among the three pillars of observability:

| Signal | Key Questions | Examples |
| --- | --- | --- |
| **Metrics** | *How many? How fast/slow? What is the trend?* | Traffic volume, error rate, p95 latency, heap usage |
| **Logs** | *What specific event occurred?* | Exceptions, processing decisions, business details with sensitive data filtered out |
| **Traces** | *Which steps did a request pass through, and where was it slow?* | Spans for database calls, HTTP clients, queues, and related services |

Metrics are particularly well suited for dashboards, alerting, and tracking Service Level Objectives (SLOs) because millions of events can be aggregated into compact numerical series. On the other hand, aggregated metrics **cannot by themselves point to** the exact failing request; when you need to investigate individual cases, switch to correlated logs and traces.

### Illustrative Scenario

An order creation API normally handles 30 requests/second with a 0.2% error rate and a p95 latency of around 180 ms. After a deployment, the dashboard shows 30 requests/second, a 3% error rate, and a 900 ms p95 latency. We know the system **is degrading**, even though traffic has not increased. The next step is to slice metrics by `uri`, `status`, or downstream dependencies, and then use logs/traces to identify the specific cause.

## 2. Types of Metrics to Distinguish

Micrometer provides a measurement API independent of the target storage backend. Common instruments include:

| Type | How It Works | When to Use | Notes |
| --- | --- | --- | --- |
| **Counter** | Monotonically increases over the process lifetime | Request counts, retry counts, failure event counts | Use `rate()`/`increase()` on scraped series; restarts can reset counters to 0 |
| **Gauge** | Reads the value at the moment of measurement | Queued jobs, current memory usage, active connections | Do not accumulate gauges over time like counters |
| **Timer** | Records duration and execution count | Latency of requests, queries, business operations | Typically exports `count`, `sum`, and optionally histogram buckets |
| **DistributionSummary** | Records the distribution of non-time values | Payload sizes, item counts per batch | Differs from Timer in units and value semantics |
| **LongTaskTimer** | Tracks tasks that are still running | Long-running batch jobs, data synchronization | Shows the number of active tasks and total elapsed active time |

Choose the right instrument for the measurement semantics. For instance, `queue.depth` should be a Gauge; `orders.created` should be a Counter; `orders.processing.duration` should be a Timer. Do not use a Gauge for cumulative event counts if you want accurate rate and growth calculations.

### Average Latency Does Not Represent the Tail of the Distribution

Suppose 95 requests complete in 50 ms, while 5 requests take 3 seconds. The average is around 198 ms, yet the slowest group of users has to wait 3 seconds. Therefore, monitor **p95/p99 latency** and histogram distributions as well, especially for latency-sensitive APIs.

**Local percentiles** computed independently on each instance cannot be averaged to derive a system-wide percentile. If you need cluster-wide p95 in Prometheus, prefer histograms with compatible bucket boundaries across instances, then sum sample counts per bucket before calling `histogram_quantile()`.

## 3. Collection Pipeline in Spring Boot

`Spring Boot Actuator` integrates with **Micrometer**, providing many default metrics and supporting custom business metrics. With Prometheus, a common pipeline is:

~~~mermaid
flowchart LR
    A["HTTP, JVM, connection pools, business tasks"] --> B["Micrometer MeterRegistry"]
    B --> C["Actuator /actuator/prometheus"]
    C -->|periodic scrape| D["Prometheus"]
    D --> E["Grafana Dashboard"]
    D --> F["Alerting"]
    F --> G["Investigation via logs and traces"]
~~~

- `MeterRegistry` holds and exports meters. The specific registry implementation determines how they are represented on the backend (Prometheus, OTLP, etc.).
- Spring Boot automatically instruments several components when matching dependencies and auto-configuration are present: HTTP server, JVM, system, datasources/connection pools, etc. Available metrics depend on the libraries on the classpath.
- `/actuator/metrics` is primarily for **inspecting metric names and tags**; it is not the Prometheus scrape format.
- `/actuator/prometheus` exposes Prometheus-formatted time series when the corresponding registry is present and the endpoint is exposed.
- Prometheus actively **scrapes** on a schedule, stores time series, and serves PromQL queries. The scrape interval determines observation granularity; scraping does not mean the application processes only one request per interval.

Micrometer metric names typically use dots, such as `http.server.requests`. When exported to Prometheus, names are normalized according to conventions and units: such a Timer typically exports series like `http_server_requests_seconds_count`, `http_server_requests_seconds_sum`, and `http_server_requests_seconds_bucket` when histograms are enabled. Do not write rules based solely on guessed names: inspect the actual exporter output.

## 4. Hands-On: Enabling Actuator and Prometheus

The example below uses the familiar **Spring Boot 3.x + Micrometer** configuration style. For projects using other versions, verify the corresponding dependencies and properties.

### 4.1. Maven Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

When managing dependencies via the Spring Boot BOM/parent, you typically do not need to declare explicit versions for these two dependencies. If the project uses Gradle, declare the two equivalent modules.

### 4.2. `application.yml` Configuration

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
    distribution:
      percentiles-histogram:
        "http.server.requests": true
      slo:
        "http.server.requests": 100ms,300ms,1s
~~~

In this example:

1. Expose `metrics` for inspection and `prometheus` for monitoring scrapes; `health` and `info` serve operational checks.
2. Adding the `application=order-service` tag distinguishes services when multiple applications report to the same backend.
3. Enabling histograms and latency boundaries supports distribution queries across multiple instances. This is an **illustrative configuration**: each bucket combined with the tag set creates additional time series, so only enable histograms for measurements truly needed in production.

Ensure management/Actuator ports have proper access controls in real environments; do not expose monitoring endpoints to the public Internet simply for convenient scraping.

### 4.3. Verifying on the Application

After starting the application and calling a few APIs:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/http.server.requests
curl http://localhost:8080/actuator/prometheus
~~~

On the `metrics` endpoint, look up metric names and the `availableTags` list. On `prometheus`, check for `..._count`, `..._sum`, and `..._bucket` series (when histograms are enabled). If HTTP metrics do not appear yet, send a real request first; some meters are registered only after a measurement sample occurs.

Example Prometheus scrape configuration when running on the **same machine and network namespace** as the application:

~~~yaml
scrape_configs:
  - job_name: spring-boot-orders
    scrape_interval: 15s
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["localhost:8080"]
~~~

If Prometheus runs inside a separate container, `localhost` inside that container refers to the container itself. Replace `targets` with a hostname or service name reachable from the Prometheus container.

## 5. Creating Business Metrics with MeterRegistry

Default metrics reflect the technical health of the application, but sometimes cannot answer business questions such as “how many order processing attempts succeeded or failed.” Measure directly where the business operation executes, with stable names and meaningful tags.

The following example measures the **attempt count** and **execution duration** of a synchronous operation:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class OrderMetricsService {
    private final MeterRegistry meterRegistry;

    public OrderMetricsService(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void execute(Runnable operation) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String result = "success";

        try {
            operation.run();
        } catch (RuntimeException | Error ex) {
            result = "error";
            throw ex;
        } finally {
            sample.stop(
                Timer.builder("orders.processing.duration")
                    .description("Duration of an order processing attempt")
                    .tag("result", result)
                    .register(meterRegistry)
            );

            meterRegistry.counter("orders.processed", "result", result)
                .increment();
        }
    }
}
~~~

Explanation:

- `orders.processed` increments by one **per attempt**, including failures; it does not necessarily equal the number of orders successfully created. If you need two distinct meanings, use metric names that clearly express each definition.
- `orders.processing.duration` is a Timer recording processing duration; the Timer's count can also count attempts. The additional Counter here illustrates a separate business measurement.
- `result` has only two values, `success` and `error`, making it far safer than a tag taken from arbitrary error messages.
- The `finally` block records duration even when the operation throws an exception. For asynchronous flows, measure until the task actually completes—do not stop the Timer immediately after scheduling the work.

**Do not** place `userId`, `orderId`, `requestId`, full URLs, or exception messages into metric tags. Per-request details belong in logs/tracing under appropriate policies; metrics require dimensions with bounded value sets.

## 6. Tags and Cardinality: Limiting Costs by Design

A time series in Prometheus is uniquely identified by its **metric name and label combination**. Cardinality is the number of distinct label combinations. This is one of the biggest risks when designing metrics.

As a hypothetical example, a metric with 20 URI patterns, 4 HTTP methods, 5 status groups, and 10 instances already produces **20 × 4 × 5 × 10 = 4,000 series**. Enabling histograms with many buckets multiplies the series count significantly further. Adding `userId` with hundreds of thousands of values causes storage and query costs to skyrocket.

| Tag to Consider | Tag to Avoid | Reason |
| --- | --- | --- |
| `method=GET/POST` | `requestId=...` | Request IDs are almost always unique |
| `status=200/404/500` or `outcome` | `exceptionMessage=...` | Error messages can be unbounded and may contain sensitive data |
| `uri=/api/orders/{id}` (route template) | `uri=/api/orders/12345` (actual URL) | IDs create a new value for every record |
| `region`, `service`, `result` with bounded sets | `email`, `sessionId`, `userId` | User-identifying dimensions are unsuitable for metrics |

Practical principles:

1. Define the operational question before adding a metric or tag. Every dimension must have a clear use in queries or alerts.
2. Use **route templates** instead of URLs containing IDs; constrain tag values to controlled enumerations.
3. Estimate the total number of series after adding tags, multiplied across instances, buckets, and runtime environments.
4. Monitor the metrics backend itself (series count, storage cost, scrape duration, query latency). Meter filtering/renaming configuration can be used when generated data must be constrained.

With Micrometer Observation, **low-cardinality** key-values can feed metrics, while **high-cardinality** details are better suited for trace spans. Whether using Observation or MeterRegistry directly, you must always control the value count of every label.

## 7. Reading and Querying Metrics with PromQL

The queries below assume Prometheus output from default HTTP server metrics and the `application="order-service"` tag. Exact names may differ depending on version, instrumentation, and registry. Verify them via `/actuator/prometheus` before use.

### 7.1. Request Rate (RPS)

~~~promql
sum(
  rate(http_server_requests_seconds_count{application="order-service"}[5m])
)
~~~

`rate(counter[5m])` estimates the per-second increase over a 5-minute window and accounts for counter resets caused by process restarts. `sum` aggregates results across series, such as across multiple instances.

### 7.2. 5xx Request Rate

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    application="order-service",status=~"5.."
  }[5m])
)
/
sum(
  rate(http_server_requests_seconds_count{
    application="order-service"
  }[5m])
)
~~~

The result is a ratio from 0 to 1 (multiply by 100 for a percentage). When there is no traffic, the denominator can be 0 and the query will not yield a meaningful ratio; dashboards and alerts must handle zero-sample or very-low-traffic cases separately. If your system formats `status` differently, adjust the filter to match the actual label.

### 7.3. p95 Latency of the Order Creation API

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      application="order-service",uri="/api/orders"
    }[5m])
  )
)
~~~

Histogram timers export in **seconds** to Prometheus, so multiply the result by 1000 to display milliseconds. This query is only meaningful when the corresponding metric actually exports `_bucket` series. To inspect latency per route or method, retain that label via `sum by (le, uri)` or `sum by (le, method)`, keeping cardinality in mind.

### 7.4. Business Processing Throughput

~~~promql
sum by (result) (
  rate(orders_processed_total{application="order-service"}[5m])
)
~~~

This is an example for the `orders.processed` Counter after Prometheus normalizes it to `orders_processed_total`; check the actual series name produced by your registry. This metric represents *attempts* per second by outcome, so it may differ from HTTP request count because a single request can execute multiple operations or trigger retries.

## 8. From Metrics to SLIs, SLOs, and Alerting

An **SLI (Service Level Indicator)** is a measurement reflecting service quality. An **SLO (Service Level Objective)** is a quantitative target set for an SLI over a given time period.

Example for an order API:

| SLI | How to Measure | Illustrative SLO |
| --- | --- | --- |
| Request availability | Ratio of successful requests according to system convention | ≥ 99.9% over 30 days |
| Latency | Percentage of requests completing within 300 ms | ≥ 95% over 30 days |
| Business correctness | Ratio of successful order processing, excluding defined invalid requests | ≥ 99.5% over 30 days |

These targets are only **examples**, not Spring Boot defaults. You must agree on denominators, excluded events, measurement windows, and metric sources before creating alerts.

Common operational methodologies:

- **RED** for request-serving services: *Rate* (traffic), *Errors* (failures), *Duration* (latency).
- **USE** for resources: *Utilization* (usage), *Saturation* (queuing/backlog), *Errors* (resource errors).
- Also observe latency, traffic, errors, and saturation per the four golden signals, then select SLIs that reflect user experience.

A useful alert requires stable conditions and should avoid firing on a single isolated error in a low-traffic system. For example, the Prometheus rule below alerts only when the 5xx ratio exceeds 2% and RPS is greater than 1 continuously for 10 minutes:

~~~yaml
groups:
  - name: spring-boot-service
    rules:
      - alert: HighHttp5xxRate
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              application="order-service",status=~"5.."
            }[5m]))
            /
            sum(rate(http_server_requests_seconds_count{
              application="order-service"
            }[5m]))
          ) > 0.02
          and
          sum(rate(http_server_requests_seconds_count{
            application="order-service"
          }[5m])) > 1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "order-service HTTP 5xx rate elevated"
~~~

In production, thresholds should derive from SLOs and traffic characteristics; for services with SLOs, alerts can be designed around **error-budget burn rate** to balance fast detection against noisy paging.

## 9. Combining Metrics, Logs, and Traces During Incident Investigation

Consider an order scenario where p95 rises from 180 ms to 900 ms and 5xx increases to 3% after a deployment:

1. **Detect (Metrics):** The dashboard shows steady request rate, while errors and latency increase. Slice by `uri`, `status`, instance, deployment version, or tagged dependencies.
2. **Narrow Down (Metrics):** Compare DB connection wait time, active connections, JVM GC duration, and CPU load. If they rise concurrently, form hypotheses around pool exhaustion, database saturation, or CPU bottlenecks.
3. **Find Events (Logs):** Filter logs by time range, endpoint, and timeout indicators. Structured logs carrying `traceId`/`spanId` make lookups more consistent when tracing is enabled.
4. **Break Down Latency (Traces):** Open a trace of a slow request to see whether DB spans, HTTP client spans, or application logic dominate the time. Tracing may be **sampled**, so not every request will have a trace.
5. **Confirm and Monitor (Metrics):** After applying a fix, verify p95/p99, RPS, error rate, and resource metrics return to expected thresholds for an adequate observation window.

**Do not put `traceId` as a metric label** to “link” the three signals. Correlation is normally performed via time range, service/route names, logs containing trace IDs, and trace context propagated across components. Some backends support **exemplars** to attach a measurement sample to a specific trace; this capability depends on the registry, exporter, and tracing setup, and is not present by default in every project.

## 10. Common Pitfalls and How to Check Them

| Symptom | Likely Cause | Check |
| --- | --- | --- |
| `/actuator/prometheus` returns 404 | Missing registry, endpoint not exposed, or different management path | Check dependencies, management config, and actual endpoint path |
| Prometheus shows target DOWN | Wrong host/port, container unreachable, TLS/auth, or firewall | Inspect Prometheus Targets and test HTTP from the network where Prometheus runs |
| Endpoint exists but expected metric is missing | No events recorded yet, different metric name, or instrumentation disabled | Send sample requests and compare `/actuator/metrics` with exporter output |
| No `_bucket` series to compute p95 | Histogram not enabled for the target meter | Check distribution config and actual metrics after generating requests |
| Dashboard has too many series or slow scrapes | Tag has unbounded values, too many buckets/instances | Review tags, route templates, and total series count |
| Rate/latency differs from application counts | Wrong query window, units, counter reset, aggregation, or filters | Check meter type, labels, and query predicates |

Do not infer root cause from a single chart alone. When metrics show rising latency, traces and logs help confirm whether the culprit is truly the database, a downstream service, a thread pool, or a specific code path.

## 11. Self-Check Exercise

A Spring Boot service runs across 3 instances and exposes `POST /api/orders` and `GET /api/orders/{id}`. Complete the following steps:

1. Enable Actuator and the Prometheus registry; send requests to confirm HTTP server metrics appear.
2. Add measurements for order processing duration and attempt counts split by `success`/`error` outcomes.
3. Design a dashboard showing RPS, 5xx rate, p95 latency, and order processing attempts per second; compare across instances when needed.
4. Simulate several failing or slow requests and observe changes over a 5-minute window. Verify whether PromQL data matches the number of generated events.
5. Try defining an `orderId` tag, estimate the resulting series count for 100,000 orders, and then replace it with a bounded-value tag such as `result`.

**Completion criteria:** You can explain Counter/Gauge/Timer, read units and time windows accurately, write at least one rate query and one p95 histogram query, and explain why individual IDs must not be used as metric labels.

## Key Takeaways

- Metrics describe **trends and magnitude** across the system; logs describe events, and traces describe the path and timing of individual requests.
- In Spring Boot, **Actuator + Micrometer registry + exporter** forms the pipeline from instrumentation to the monitoring backend.
- Choose the appropriate instrument, define measurement semantics clearly, and use `rate()` for Counters.
- **Cardinality is a design concern**: keep tags low-cardinality, control histograms, and inspect actual series counts.
- Compute cluster-wide p95 using histograms with consistent buckets; combine metrics with logs/traces to investigate root causes and verify remediation.
