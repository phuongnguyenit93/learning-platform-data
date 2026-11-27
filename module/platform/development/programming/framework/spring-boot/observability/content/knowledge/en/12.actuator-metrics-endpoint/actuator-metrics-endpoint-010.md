# Do Not Treat the Actuator Metrics Endpoint as a Time-Series Backend

In the **Actuator metrics endpoint** chapter of the **SPRING_BOOT_OBSERVABILITY** module, it is essential to distinguish two very different activities: **inspecting meters currently present in a Spring Boot process** and **storing and querying system-wide metric history**. Spring Boot Actuator provides useful endpoints to verify which measurements the application records. However, the `/actuator/metrics` endpoint is not a time-series database, and `/actuator/prometheus` is where **metric samples are published for another system to collect**, not where history is stored or PromQL is executed.

This is foundational knowledge for setting up observability using **Micrometer Observation, metrics, logs, and distributed tracing**, while controlling tags/cardinality, exporters, and sampling. Confusing an endpoint with a backend can leave an operations team with empty dashboards, miscalculated error rates and p95, or lost history whenever a container restarts.

**Learning objectives:** after this lesson, learners can explain the roles of Actuator, `MeterRegistry`, exporters/scrapers, and a time-series backend; use the endpoint for on-the-spot diagnosis; use Prometheus/PromQL for time-based analysis; and know how to cross-check metrics with logs/traces during incident investigation.

## 1. Three Layers to Distinguish

Suppose an application receives requests, performs business operations, and records numbers via Micrometer. Data typically flows through these layers:

```text
Spring Boot application (each instance)
    |
    +-- HTTP/JVM/DataSource/custom Observation
    |              |
    |              v
    |         Micrometer MeterRegistry
    |              |
    |              +-- /actuator/metrics       JSON to inspect meters at the instance
    |              |
    |              +-- /actuator/prometheus    Exposition for Prometheus scraping
    |              |                |
    |              |                v
    |              |         Prometheus server / TSDB
    |              |           |    |      |
    |              |           |    |      +-- Retention / series history
    |              |           |    +--------- PromQL / query_range
    |              |           +-------------- Alerts / dashboards
    |              |
    |              +-- OTLP/other (if configured) --> compatible telemetry backend
    |
    +-- Logs ----------------------------------> log backend
    +-- Tracing instrumentation --------------> trace backend
                            (these paths have separate configurations)
```

| Component | Responsibility | What It Does Not Do |
| --- | --- | --- |
| **`MeterRegistry`** | Registers meters, holds state, and exposes measurements per implementation | Not by default a centralized historical store across multiple instances |
| **`/actuator/metrics`** | Lists meters, inspects measurements and tags in the instance's registry | Does not store and query hours/days of data over time ranges |
| **`/actuator/prometheus`** | Publishes data in exposition format for Prometheus when the matching registry is configured | Does not run PromQL or maintain retention/a time-series database |
| **Prometheus / TSDB** | Periodically collects samples, stores labeled time series with timestamps, enables PromQL, alerts, and retention | Cannot read application metrics automatically if scraping/exporting is not working |
| **Dashboard (e.g., Grafana)** | Visualizes and compares data from datasources/backends | Usually does not replace the metrics storage backend |

Some systems use push exporters (such as OTLP) instead of Prometheus scraping. That changes how **data is shipped out**, yet does not turn `/actuator/metrics` into a historical store. Always identify the exact registry and exporter in use.

## 2. What Does `/actuator/metrics` Tell You?

The Actuator metrics endpoint can:

- List meter names currently in the application's `MeterRegistry`.
- Show statistics such as `COUNT`, `TOTAL_TIME`, `MAX`, or `VALUE` depending on meter type and configuration.
- Show existing tag values; support filtering a metric by tag.
- Help verify whether a custom counter/timer has been recorded, or whether a DataSource/JVM meter appears.

Example after starting an application with Actuator configured:

```bash
curl -s http://localhost:8080/actuator/metrics

curl -s http://localhost:8080/actuator/metrics/http.server.requests

# View only metrics with specific tags; -G URL-encodes parameters:
curl -sG http://localhost:8080/actuator/metrics/http.server.requests \
  --data-urlencode 'tag=method:GET' \
  --data-urlencode 'tag=status:200'
```

A response **illustrating the structure**, not measurements from a live application:

```json
{
  "name": "http.server.requests",
  "baseUnit": "seconds",
  "measurements": [
    { "statistic": "COUNT", "value": 120.0 },
    { "statistic": "TOTAL_TIME", "value": 7.2 },
    { "statistic": "MAX", "value": 0.45 }
  ],
  "availableTags": [
    { "tag": "method", "values": ["GET", "POST"] },
    { "tag": "status", "values": ["200", "500"] },
    { "tag": "uri", "values": ["/orders", "/checkout"] }
  ]
}
```

Depending on version and instrumentation, names, units, labels, measurements, or even this meter itself may differ. A timer typically has a **recording count**, **total time**, and a **max** measurement. A timer's `MAX` value may be a time-windowed maximum of the measurement mechanism, **not the all-time historical maximum**. Never infer a historical pattern from a single response.

### Why Is This Not a Time-Series Backend?

Suppose you call the endpoint at three points in time. You may receive three JSON payloads with different values, yet the endpoint itself **does not retain all three values and their timestamps to answer**:

- "Over the past 24 hours, how did per-minute RPS fluctuate?"
- "At which deployment timestamp did `/checkout` p95 latency rise?"
- "How many instances had the highest error rate over 7 days?"
- "For how long did the 5xx ratio stay elevated before the alert fired?"

To answer those, you need a system that collects periodically, stores timestamps/labels, and executes time-windowed queries. Manually saving JSON responses can build your own history, yet **at that point your storage/query tool is acting as the backend**, not the Actuator endpoint.

Measurements in the registry can also reset when the process restarts. A meter may also appear only after the relevant code path runs—for example, an HTTP request meter for an unvisited route or an unregistered custom counter.

## 3. Another Endpoint: `/actuator/prometheus`

When an application has the Prometheus registry and the endpoint is exposed, `/actuator/prometheus` publishes samples in a format suited for **Prometheus server scraping**. A brief example:

```text
# HELP orders_completed_total ...
# TYPE orders_completed_total counter
orders_completed_total{application="orders-service",outcome="success"} 150
orders_completed_total{application="orders-service",outcome="error"} 5
```

*This is an illustrative sample of names and values, not a guarantee of exact backend names emitted by every Micrometer version.*

Even though the output looks like "time series", the endpoint only provides samples **at read time**. One `curl` call does not retrieve 24 hours or 7 days of history. Prometheus must hit the endpoint on a scrape schedule to attach timestamps, store results, and support queries/alerts. In a system with OTLP push, another exporter sends measurements to a collector/backend on its push schedule; how data is shipped still differs from historical storage.

| Question | Where to Check? |
| --- | --- |
| "Has the `orders.completed` meter been registered in this instance?" | `/actuator/metrics` |
| "What are the exact names/labels after Micrometer converts for Prometheus?" | `/actuator/prometheus` |
| "How did error rate change over 30 minutes?" | Prometheus/TSDB via time-range queries |
| "What was p95 latency over the past hour across all 10 replicas?" | Backend with appropriate histograms/time series |
| "Why did a specific request fail?" | Combine the metrics backend with traces and logs |

## 4. Sample Application Configuration

Maven example for Spring Boot using Actuator and Prometheus. The project assumes Spring Boot parent or BOM manages versions:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Example `application.yml`:

```yaml
spring:
  application:
    name: orders-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: orders-service
```

Notes:

1. `spring-boot-starter-actuator` provides framework-supported endpoints; exposing endpoints over HTTP depends on endpoint access and security configuration for your Spring Boot version.
2. `micrometer-registry-prometheus` provides the backend registry to generate Prometheus exposition. Simply enabling an HTTP endpoint without a matching registry does not make `/actuator/prometheus` ready.
3. The `application` label helps distinguish services when querying. When multiple instances exist, the backend typically adds target labels such as `job` and `instance` during scraping. Never attach request IDs/user IDs to metric labels.
4. In production, management endpoints must have restricted access: separate management port, internal network, authentication/authorization, or appropriate proxy. **Never expose Actuator indiscriminately on the Internet**, especially endpoints containing operational details.
5. Different Spring Boot versions may differ in property names, default metrics, or authorization mechanisms. Verify behavior on the actual application in use.

After running the app, check:

```bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/jvm.memory.used
curl -s http://localhost:8080/actuator/prometheus
```

If an endpoint returns 404/403, distinguish **missing endpoint, unexposed, blocked by security, or wrong path/port**; do not jump to concluding the meter was never created.

## 5. Configuring Prometheus Is What Creates History

An **illustrative** scrape configuration for a Prometheus server:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: spring-boot-orders
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - localhost:8080
```

This is **Prometheus configuration**, not configuration placed inside Spring Boot's `application.yml`. When Prometheus runs in another container, `localhost:8080` points to that container itself, **not** the Spring Boot application; use real DNS/hostnames and networking. In Kubernetes, deployments typically use appropriate service discovery/operators.

Once configured properly, the cycle typically runs as follows:

1. Prometheus calls `/actuator/prometheus` roughly every 15 seconds.
2. Each sample is tagged with a timestamp and target/service identifying labels.
3. The time-series database stores data according to configured retention.
4. PromQL computes rates, aggregations, histogram quantiles, and time-range queries.
5. Alerting or dashboards read results from the backend.

A failed scrape creates a data gap; it does not mean the application stopped serving requests. Conversely, a healthy running application does not guarantee scrapes are succeeding.

In Prometheus you can check:

```promql
up{job="spring-boot-orders"}
```

`up=1` indicates Prometheus **successfully scraped the target** at that evaluation; it **does not prove** order placement works correctly or the database is healthy. `up=0` may result from network, authentication, endpoint, TLS, or scrape errors, not necessarily a dead process.

## 6. Why Is a Single `COUNT` Value Not a Request Rate?

A typical `Counter` or `Timer.count` reflects the total occurrences since the meter/process was created, depending on registry type. From a single figure such as "12,300 requests", you cannot tell whether the system is receiving 1 or 1,000 requests per second.

Suppose the same series has these samples:

| Timestamp | Cumulative Counter |
| --- | ---: |
| 10:00:00 | 100 |
| 10:01:00 | 160 |
| 10:02:00 | 220 |

With no resets and identical labels on both samples, the increase per minute is **60 requests**, corresponding to roughly **1 request/second**. Yet when the process restarts, the counter can drop back to 0. Subtracting two values manually yields a negative number that does not reflect traffic.

A time-series backend stores timestamps and provides functions that handle resets and fluctuations properly. For a Prometheus counter, use:

```promql
rate(http_server_requests_seconds_count[5m])
```

In this example, `http_server_requests_seconds_count` assumes the counter series name exported from the HTTP timer `http.server.requests`. Verify the actual name, as naming conventions and versions can differ. `rate(...[5m])` estimates the average per-second rate of increase over a 5-minute window and handles counter resets per Prometheus semantics.

To get total request rate across all instances:

```promql
sum(rate(http_server_requests_seconds_count[5m]))
```

To get rate by URI route template if the `uri` label exists:

```promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
```

Do not use `rate()` on gauges like `jvm_memory_used_bytes` or `jdbc_connections_active` when your goal is simply viewing current usage; gauges can move up and down arbitrarily and are analyzed differently from counters.

### What Happens If the Service Has 10 Replicas?

The `/actuator/metrics` endpoint on a single pod normally reports figures for **that pod only**. One curl does not provide cluster-wide history. Prometheus scrapes each target individually, attaches identifying labels, and can:

- Sum request rates across instances.
- Compare an instance experiencing elevated errors.
- Spot a congested database connection pool on a single replica.
- Inspect trends before/after a rolling deployment.

Labels such as `instance`, `pod`, and `job` are determined by scraping/relabeling and infrastructure resources. Before summing, ensure you are not scraping the same target twice and **double-counting** data.

## 7. p95 Latency Requires Histograms or an Appropriate Distribution Source

A JSON payload at `/actuator/metrics/http.server.requests` with `COUNT`, `TOTAL_TIME`, and `MAX` is insufficient to accurately reconstruct **p95 latency over a time interval across multiple instances**. From total time and count, you can only compute the **mean** when semantics align; nor can you derive p95 from max.

To compute p95 from a Prometheus classic histogram, enable and export buckets for the relevant timer. Example configuration **applicable in Spring Boot versions supporting this property**:

```properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

Enabling histograms can multiply time-series counts by tag combinations and bucket counts; measure your cardinality budget, evaluate URI/status/method combinations, and do not enable it unconditionally on every meter. Other registries or metrics systems use different distribution/aggregation mechanisms; verify on your backend.

When the `http_server_requests_seconds_bucket` series and `uri` label actually exist, an illustrative query for the checkout endpoint is:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{uri="/checkout"}[5m])
  )
)
```

This expression works properly only when bucket names, labels, second units, and histograms match the active exporter. `sum by (le)` aggregates across instances and other filtered labels; if you want p95 per instance/service/status, retain those corresponding grouping labels. Quantiles from histograms are **bucket-dependent estimates**, not exact values across every individual request.

**Never average per-pod p95 values to get system-wide p95.** Quantiles are not additive or averageable like counters. Aggregate the underlying distribution data in the backend first, then compute the quantile.

## 8. Distinguishing Metric Tags, Trace Attributes, and Log Fields

Micrometer Observation lets a business operation provide metadata, and observation handlers can record metrics/tracing signals depending on configuration. Yet **not every piece of metadata is suitable as a metric label**.

| Metadata | Metric Label | Trace/Log Detail |
| --- | --- | --- |
| `outcome=success/error` | Suitable when value set is bounded | Also useful |
| `payment.provider=bank_a/bank_b` | Suitable when provider count is managed | Also useful |
| `uri=/orders/{id}` (route template) | Usually suitable | Usable |
| `orderId=...` | **Avoid**: high cardinality | Use only when needed and permitted by data policy |
| Raw URL containing query strings | Avoid as label | Filter sensitive info if logged |
| Verbatim exception message | Avoid as label | Use controlled diagnostic logs, avoiding secrets |

A single metric with 3 `provider` values, 4 `outcome` values, and 100,000 order IDs can generate up to **1,200,000 label combinations** before counting any other labels. Even if `/actuator/metrics` still returns JSON, the backend can suffer heavy load and cost. **Cardinality is a metric-identity risk, not a problem caused by the endpoint becoming a TSDB.**

For traces, sampling may retain only a subset of requests; logs with `traceId`/`spanId` require properly configured MDC/logging correlation; context propagation must work across threads, executors, and services. An unsampled trace **does not mean** counters/timers were skipped as well if the metric observation handler still records data.

## 9. Adding a Custom Business Metric and Verifying the Export Path

Suppose a payment authorization service classifies outcomes. A custom counter records only the distinct business event without using order IDs as tags:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentMetrics {
    private final MeterRegistry registry;

    public PaymentMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAuthorization(boolean approved) {
        String outcome = approved ? "approved" : "declined";
        Counter.builder("payment.authorizations")
                .description("Authorization decisions")
                .tag("outcome", outcome)
                .register(registry)
                .increment();
    }
}
```

Assuming the application calls this method **exactly once per decision**, the `payment.authorizations` metric measures business decision counts; it differs from HTTP client duration. With the Prometheus registry, the counter may be exported with a suffix such as `payment_authorizations_total`. Verify the actual output instead of writing queries against a guessed name.

Verification workflow:

1. Invoke the business flow several times with `approved` and `declined`.
2. Check `/actuator/metrics/payment.authorizations`: did the name, measurements, and available tags appear as expected?
3. Check `/actuator/prometheus`: what are the actual backend name and labels?
4. Check the target in Prometheus: did the scrape succeed and were samples stored?
5. Run PromQL over a sufficient window: are rates/total decisions by `outcome` reasonable?
6. Compare with logs/traces of a failing transaction when detailed investigation is required. Do not add `orderId` to the counter to trace a single order.

If the same event is recorded in both the service and an HTTP/queue adapter, counts can double even though the registry holds a single meter. In that case, fix the recording point rather than just the endpoint.

## 10. Common Misconceptions

**"I see `COUNT=500` at `/actuator/metrics`, so the backend has stored 500 historical points."** False. Count is a cumulative value of the meter; it is not 500 samples over time. How many samples the backend stores depends on scrape/step/export/retention.

**"`/actuator/prometheus` returns data, so Prometheus scraped successfully."** Not necessarily. You only proved the endpoint serves exposition to **the calling client**. Check target status, networking, authentication, scrape errors, and queries on the Prometheus server.

**"Having `MAX` is enough to compute 30-day p99."** False. A timer's max can carry time-window semantics; it does not replace distributions/histograms and history.

**"Counters increment while the app runs, so taking two snapshots and subtracting is exact."** That is only an approximation under very strict assumptions: same instance/series, no resets, no missed samples, no label changes. A backend with `rate()`/`increase()` is far better suited for ongoing operations.

**"Having `/actuator/metrics` guarantees tracing is active."** False. Metrics, tracing bridges, exporters, and log correlation are separate components with their own configurations.

**"Not seeing a meter in JSON means the code didn't run."** Not necessarily. The meter may not be registered yet, may be rejected by a `MeterFilter`, the observation may be dropped by an `ObservationPredicate`, instrumentation may be disabled, or a different registry may be in use.

**"Prometheus already stores data, so let's add order ID as a tag for investigation."** This drives up series counts, costs, and privacy risks. Use low-cardinality tags; use access-controlled traces/logs to look up specific transactions.

**"I just need to raise trace sampling to recover metrics data."** Sampling is a tracing decision; missing metrics usually require checking meters/handlers/registries/exporters/scrapes. The two issues can be independent.

## 11. Operational Scenario: Slow Requests After a Deployment

Suppose `orders-service` runs 6 replicas. After a deploy, users report slow checkout. An engineer calls `/actuator/metrics/http.server.requests` on one pod and sees a high `MAX`. This is an **initial clue**, insufficient to conclude about the whole system.

Investigation steps:

1. **Verify the data collection path:** is Prometheus scraping all 6 replicas? Are any targets unreachable? Does `up` show scrape failures?
2. **Assess scope:** query HTTP request rate and 5xx rate by service/URI to see when changes began. Do not rely solely on a single pod's counter snapshot.
3. **Measure latency:** use appropriate histograms to calculate p95/p99 before and after deploy; distinguish a single-instance fault from a cluster-wide issue.
4. **Isolate dependencies:** check pool metrics, external client metrics, CPU/GC, and database server metrics. A slow endpoint may stem from a connection pool or payment provider.
5. **Investigate a transaction:** from the degraded time range, open a sampled trace and inspect business observations and child spans. Use correlated logs to inspect error types and business decisions.
6. **Check propagation and sampling:** if traces break across executors/queues/services, fix context propagation; if a span is absent due to sampling, do not assume that business step never ran.
7. **Evaluate alerts:** base alerts on windowed rates/p95 and appropriate traffic volume; recognize scrape gaps to avoid false conclusions.

Example PromQL for overall 5xx ratio, when `status` labels and meter names match:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count[5m])),
  1e-9
)
```

This illustrative query should filter by the right service/job/URI in multi-application systems; zero traffic may still produce an empty result depending on existing series and PromQL matching. Error rates and durations must be analyzed alongside request volume to avoid noisy alerts when the system has virtually no load.

## 12. Quick Decision Table: Endpoint or Backend?

| Goal | Suitable Tool | Reason |
| --- | --- | --- |
| Find meter names and tags right on one instance | `/actuator/metrics` | Shows registry state/metadata at inspection time |
| Check Prometheus name after conversion | `/actuator/prometheus` | Shows the actual exposition the scraper reads |
| Confirm targets are being collected | Prometheus targets and `up` | Distinguishes running app from working scrape path |
| Plot per-minute RPS over 7 days | TSDB + PromQL/dashboards | Requires timestamps, range queries, and retention |
| Compute p95 across multiple replicas | TSDB with suitable histograms/summaries | Requires distribution data and semantically valid aggregation |
| Alert on error rate over 10 minutes | Backend alerting/queries | Requires time-windowed queries and evaluation schedules |
| Find root cause of a failing transaction | Trace backend + structured logs | Metrics do not retain per-request details |
| Reduce exploding series counts | Fix tags at source and meter policy | Endpoints do not solve cardinality |

## 13. Verification Exercise

A team deploys Spring Boot with Actuator and the Prometheus registry. They run:

```bash
curl -s http://localhost:8080/actuator/metrics/http.server.requests
curl -s http://localhost:8080/actuator/prometheus
```

Both commands return data. Yet the Grafana dashboard remains empty. The team concludes "Actuator isn't storing enough history" and plans to poll the endpoint every second to save the JSON into a SQL table.

**Question:** where did the team's reasoning go wrong, and what are the right investigation steps?

A reference answer:

1. The two endpoints only prove **the application currently has data and can publish exposition**, not that the Prometheus server is collecting it.
2. Check Prometheus `scrape_configs` or service discovery, target host/port, `metrics_path`, networking, and security. Remember `localhost` differs across containers.
3. Check target health and `up`, then query the actual series name in Prometheus. Compare `job`/`instance`/`application` labels with the query used by the dashboard.
4. Check time range, retention, scrape interval, and Grafana datasource configuration. Grafana must point to the right backend and use queries matching metric names/labels.
5. Only once the system has samples over time can rates, histogram quantiles, and alerts be built reliably.
6. If using an OTLP push architecture, verify exporter → collector → metrics backend along that path; do not force Prometheus scraping when the design uses push.

### Lesson Completion Criteria

Learners should be able to test the following scenarios themselves:

| Experiment | Expectation |
| --- | --- |
| Call `/actuator/metrics` before/after triggering business logic | See meters and measurements change when the registry records properly |
| Restart the application | Recognize in-process counts can reset; backend history remains per retention |
| Disable scraping while the app stays running | Endpoint may remain directly reachable, while Prometheus misses new samples |
| Call `/actuator/prometheus` directly | See exposition names/labels; no historical query API on the endpoint |
| Restore scraping | Samples accumulate over time; `rate()` queries work once enough samples exist |
| Enable appropriate histograms | Bucket series appear for computing p95 via PromQL if supported by exporter |
| Increase tag cardinality too high | Recognize label design and series counts as the cause; fix at telemetry source |
| Trace sampled out | Metrics can still appear; logs/tracing require separate config and propagation |

**Key takeaway:** `/actuator/metrics` is a tool for **diagnosing meters inside the application**; `/actuator/prometheus` is a tool for **publishing samples for scrapers**; the **time-series backend** is what collects, stores, and queries history by timestamps and labels. Using each layer for its intended role, standardizing tags/cardinality, and correlating with logs/traces enables accurate assessment of errors, latency, and Spring Boot behavior in production.
