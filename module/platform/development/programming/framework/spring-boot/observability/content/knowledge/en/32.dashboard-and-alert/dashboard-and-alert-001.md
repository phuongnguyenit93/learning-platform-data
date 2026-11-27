# Request Rate Dashboard in Spring Boot

When a service starts slowing down, the first question is usually whether traffic has changed. A sudden spike in request rate can saturate thread pools, database connections, or downstream services. A sharp drop in request rate can signal a routing error, a failed deployment, or clients being unable to reach the application. A good request rate dashboard makes it easy to observe traffic over time, compare by route and method, and place this signal alongside latency and error rate to understand operational impact.

In Spring Boot, Micrometer and Actuator can export HTTP server request metrics; Prometheus collects the time series and Grafana renders the dashboard. A dashboard is only useful when metric dimensions are normalized: use route templates like /api/orders/{id}, not raw URLs containing order IDs. How labels are defined determines both analytical capability and cardinality cost.

The lesson **Request Rate Dashboard** belongs to the **Dashboard and Alert** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module focuses on setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain request rate and how to read the requests/second unit.
- Understand Counter/Timer HTTP metrics and how Prometheus calculates rate.
- Write PromQL using rate() and increase() for request counters.
- Design dashboards broken down by service, method, route template, and status class.
- Combine request rate with latency and error rate following the RED method.
- Avoid high cardinality caused by raw paths, user IDs, or request IDs.
- Design panels, variables, and time ranges in Grafana.
- Configure alerts with appropriate windows, thresholds, and traffic floors.

## 2. What is Request Rate?

Request rate is the number of requests processed per unit of time, typically expressed in requests per second (req/s or RPS). For a cumulative counter, the request rate is calculated from the counter increase over a time window.

For example, if a service receives 12,000 requests in 5 minutes:

\[
\text{Average RPS} = \frac{12,000}{5 \times 60} \approx 40
\]

This is the average over a 5-minute window. Actual traffic may have per-second bursts; the dashboard should allow selecting an appropriate observation window.

### Why view rate over time?

- Rapid rate increase: could be normal traffic, a campaign, a retry storm, or a client loop.
- Abnormal rate drop: could be caused by an outage, routing/configuration issue, or upstream failing to send requests.
- Stable rate but increasing latency: could be caused by a slow dependency or resource contention.
- Decreasing rate and increasing error ratio: a portion of requests may be failing before completion or getting blocked at the gateway.

Do not interpret a single rate data point in isolation as proof of an outage. Compare against hourly/daily baselines, deployment events, and other RED signals.

## 3. HTTP Request Metrics in Spring Boot

With Spring Boot Actuator and appropriate Micrometer instrumentation, HTTP server requests are typically recorded using a Timer such as http.server.requests. A Timer provides count and duration; the Prometheus registry typically exports the corresponding time series, where count can be used to compute request rate.

Typically required dependencies:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

The Spring Boot BOM manages compatible versions. Meter names, labels, and export formats may vary by Spring Boot/Micrometer version and web stack; verify using Actuator metrics or the application's Prometheus exposition.

### Expose the Prometheus endpoint

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

The scrape endpoint is usually /actuator/prometheus. Only expose it within an appropriate network/authorization policy. If the management server uses a separate port or a different base path, update the Prometheus target accordingly.

### Inspect meters before building a dashboard

In a development environment, you can inspect:

```text
GET /actuator/metrics/http.server.requests
GET /actuator/prometheus
```

The Actuator metrics endpoint helps inspect meters and available tags. The Prometheus exposition shows the exact series/label names that the scraper receives. Do not guess labels from sample dashboards; use the output from your exact application and version.

## 4. Counter, Timer, and Prometheus Rate

A Counter is a value that increases monotonically with events. A Timer in Micrometer records count and duration; when exported to Prometheus, a Timer usually produces count/sum and may include histogram buckets if enabled.

For the HTTP request Timer, the count series is usually exported under a name similar to http_server_requests_seconds_count in the Prometheus naming convention. The exact name depends on the registry and naming convention; check the exposition before writing queries.

### rate()

rate(counter[5m]) estimates the average per-second rate of increase of a counter over a 5-minute window. Prometheus handles counter resets, such as when a process restart resets the counter to 0.

Example PromQL:

```promql
sum by (service) (
  rate(http_server_requests_seconds_count[5m])
)
```

The query above calculates the total request rate per service if the series has a service label. If service identity is attached at the scrape target under job or application, replace the label accordingly. Avoid using labels that do not exist.

### increase()

increase(counter[1h]) estimates the total increase in requests over one hour. This is useful for summarizing total call counts over a time interval:

```promql
sum by (uri) (
  increase(http_server_requests_seconds_count[1h])
)
```

Only group by uri if that label is a route template with a bounded set of values. If the label contains raw paths, the query can generate too many series and make the dashboard hard to read.

## 5. Designing Request-Rate Panels

| Panel | Question | Unit/Suggestion |
| --- | --- | --- |
| Total request rate | What is the current total traffic? | req/s |
| Rate by route | Which routes receive the most traffic? | req/s, top routes |
| Rate by method | How are GET/POST/PUT/DELETE distributed? | req/s |
| Rate by status class | How many 2xx/4xx/5xx requests are there? | req/s |
| Rate by instance | Is traffic unevenly distributed across replicas? | req/s |
| Request volume | What is the total number of requests in the selected range? | requests |

The overview panel should display the service-level rate. Breakdown panels help pinpoint the source of traffic. Do not put dozens of dimensions on the same chart; use dashboard variables or drill-downs to keep charts readable.

### Total request rate

```promql
sum(
  rate(http_server_requests_seconds_count[5m])
)
```

This query sums all series. When Prometheus scrapes multiple replicas, summing typically gives the total service rate. Verify that the same target is not scraped redundantly across multiple jobs; duplicate scraping can double-count the rate.

### Rate by route and method

```promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count[5m])
)
```

If actual labels use route instead of uri, adjust the query. Only group by labels with stable semantics.

### Rate by status class

If the status label is the HTTP status code:

```promql
sum by (status) (
  rate(http_server_requests_seconds_count[5m])
)
```

To aggregate by status class 2xx/4xx/5xx, you need a label already normalized into a class or use an appropriate recording rule/label transformation. Do not assume regex grouping automatically creates a new label in PromQL.

## 6. RED Method: Placing Request Rate Alongside Latency and Errors

RED is a methodology for observing the service request path through:

- **Rate:** requests per second.
- **Errors:** the number or ratio of failed requests.
- **Duration:** request processing time, typically viewed as percentiles.

Request rate alone cannot determine whether a service is healthy. For example, RPS can remain high while 50% of requests return 5xx. A dashboard should place total rate, error ratio, and p95/p99 latency close together so on-call engineers can compare them over the same time range.

### Error ratio

Example when the status label is the HTTP status code:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count[5m])),
  1e-9
)
```

This query returns the 5xx ratio over the total request rate. If the status label or meter naming differs, adjust accordingly. At low traffic, ratios can fluctuate sharply; alerts should add a minimum request volume or use a longer window.

### Latency percentile

If histogram buckets are enabled and exported as a Prometheus histogram:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

This is the aggregated p95 latency. Ensure histogram buckets are actually exported; percentiles cannot be accurately calculated from count/sum alone. For Micrometer percentile histograms, configuration and series names should be verified per registry/version.

## 7. Route Normalization and Cardinality

Request-rate dashboards often need breakdowns by route. Use route templates:

| Raw request path | Route template |
| --- | --- |
| /api/orders/1001 | /api/orders/{id} |
| /api/orders/1002 | /api/orders/{id} |
| /api/customers/abc-9 | /api/customers/{id} |

If each ID creates a different uri label, every request can create a new time series. As a result, Prometheus memory grows, queries slow down, and top routes become noisy with thousands of paths.

Do not add request IDs, trace IDs, customer/order/user IDs, raw query strings, emails, tokens, session IDs, payload fields, or exception messages into metric labels.

If framework instrumentation does not yet provide the proper route template, use an observation convention/customizer to normalize routes according to framework-supported route patterns. Do not fall back to using raw URIs.

## 8. Grafana Dashboard: Variables and Layout

A practical dashboard typically includes variables:

- service: selected service/job.
- environment: dev/staging/prod.
- instance: specific replica, usually with an All option.
- route: route templates that have traffic.

Variables must be based on existing, controlled labels. Do not create variables from customer IDs or request IDs.

### Recommended layout

```text
Row 1: Total RPS | 5xx ratio | p95 latency | p99 latency
Row 2: RPS by route | RPS by method | RPS by status class
Row 3: RPS by instance | Request volume | Deployment annotations
```

Set a default dashboard time range suited for on-call shifts (e.g., 1 hour) and a refresh interval that is not too short relative to the scrape interval. If scraping happens every 15 seconds, refreshing every 1 second does not make data fresher—it only increases query load.

### Dashboard annotations

Add annotations for deployments, config changes, incident start/end, or scaling events. When RPS changes, annotations help distinguish normal traffic patterns from changes caused by releases or infrastructure.

## 9. Alerts from Request Rate

Alerts should reflect a specific failure mode. Some examples:

- Request rate drops near 0 during hours when the service is expected to have traffic.
- Request rate spikes abnormally above baseline and causes saturation.
- 5xx ratio rises while traffic is sufficiently high.
- Traffic is severely skewed across instances.

Do not alert solely on low RPS if the service has irregular traffic or no traffic at night. Use schedules, baselines, or upstream signals to determine when low traffic is abnormal.

### Example alert for 5xx ratio

```yaml
groups:
  - name: spring-boot-http
    rules:
      - alert: HighHttp5xxRatio
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
            /
            clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)
          ) > 0.05
          and
          sum(rate(http_server_requests_seconds_count[5m])) > 1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: HTTP 5xx ratio is above 5 percent
```

This is an example rule; metric names/labels must be replaced according to actual scrape output. The 5% threshold and 1 RPS traffic floor are only starting points; choose them based on SLOs, traffic profiles, and error budgets.

### Alert for traffic drop

Traffic drops should be compared against a baseline for the same time period or a minimum expected rate. A simple expression:

```promql
sum(rate(http_server_requests_seconds_count[10m])) < 0.1
```

This is only suitable for services expected to have continuous traffic. If traffic naturally varies by hour, use a time-of-week baseline or synthetic probes instead of an absolute threshold.

## 10. Scrape Interval, Rate Window, and Dashboard Refresh

The Prometheus scrape interval determines how frequently samples are collected. The rate window should span several scrape intervals to have enough samples and reduce noise. For example, with a 15-second scrape interval, you can start with rate(...[5m]).

| Parameter | Role | Notes |
| --- | --- | --- |
| Scrape interval | Frequency of Prometheus scrapes | Balance freshness and load |
| Rate window | Data range used to calculate RPS | Too short causes noise/missing samples |
| Dashboard refresh | Frequency Grafana re-runs queries | No need to be faster than new data |
| Alert evaluation interval | Frequency of rule evaluation | Choose to match detection objective |
| for duration | Time alert condition must hold continuously | Reduces short-lived false positives |

Do not confuse rate window with alert `for`: rate window calculates the rate from samples; `for` requires the alert condition to persist continuously before firing.

## 11. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Dashboard RPS is 0 | Wrong metric name/labels or scrape target down | Check /actuator/prometheus and Prometheus targets |
| RPS is doubled | Duplicate target/job scraping or query summing duplicate series | Check scrape configuration and labels |
| Route panel has thousands of lines | uri label contains raw paths/IDs | Normalize route templates |
| Rate query has no data | Rate window too short or missing samples | Increase window and check scrape interval |
| RPS fluctuates wildly | Low traffic, short window, or scrape jitter | Increase window and inspect request volume |
| 5xx ratio spikes at very low traffic | Small denominator | Add traffic floor and `for` duration |
| p95/p99 not displayed | Histogram buckets not enabled/exported | Check `_bucket` series |
| Dashboard differs from Actuator count | Aggregation window, scrape gap, or duplicate registry | Compare raw counter and PromQL window |
| Traffic drops but service is healthy | Service has no expected traffic at that time | Compare against baseline/synthetic probe |
| Uneven instance traffic | Load balancing, sticky sessions, or replica health | Check ingress, routing, and instance metrics |
| Dashboard queries are slow | Too many label combinations or heavy panels | Reduce cardinality, use recording rules |

### Verification Checklist

1. Confirm the Actuator Prometheus endpoint returns HTTP metrics.
2. Confirm Prometheus targets are UP and scraping is not duplicated.
3. Verify actual metric names, counter suffixes, and labels.
4. Verify the route label is a template and contains no IDs.
5. Compare rate() with increase() over the same time range.
6. Set the rate window longer than several scrape intervals.
7. Cross-reference RPS with errors, latency, and deployment annotations.
8. Verify dashboard variables only use labels with appropriate cardinality.

## 12. Hands-on: Building a Request Rate Dashboard for order-service

**Context:** order-service runs three replicas, scraped by Prometheus every 15 seconds. The operations team needs to view total RPS, traffic by route, and detect 5xx spikes.

### Part A — Preparation

1. Add Actuator and the Prometheus registry.
2. Expose /actuator/prometheus on the internal network.
3. Confirm http.server.requests and the count series appear in the exposition.
4. Configure Prometheus to scrape the three replicas with service/environment/instance labels.
5. Verify the route label is a route template.

### Part B — Create Panels

| Panel | Starting PromQL | Unit |
| --- | --- | --- |
| Total RPS | sum(rate(http_server_requests_seconds_count[5m])) | req/s |
| RPS by route | sum by (uri) (rate(http_server_requests_seconds_count[5m])) | req/s |
| RPS by method | sum by (method) (rate(http_server_requests_seconds_count[5m])) | req/s |
| 5xx ratio | 5xx rate / total rate | percent |
| Request volume | sum(increase(http_server_requests_seconds_count[1h])) | requests |

Replace metric names and labels according to actual exposition. Add service/environment/instance variables, dashboard annotations, and a 1-hour time range.

### Part C — Verification

| Case | Action | Expected Observation |
| --- | --- | --- |
| A — Normal traffic | Send steady traffic | Total RPS reflects the sum of three replicas |
| B — Route distribution | Increase traffic to one route | Corresponding route panel increases |
| C — Error burst | Generate controlled 5xx errors | 5xx rate/ratio increases |
| D — Traffic drop | Stop load generator | RPS drops after the rate window |
| E — Restart replica | Restart one instance | Counter reset is handled by rate() |
| F — Duplicate scrape | Temporarily configure duplicate scrape in test | Observe RPS being double-counted |
| G — Dynamic path | Send various IDs | Route series remain grouped by template |
| H — Alert duration | Trigger errors shorter and longer than `for` | Only sustained errors fire |

### Part D — Self-Assessment Questions

1. How does request rate differ from total request count?
2. Why is Prometheus rate() suitable for counters?
3. In which panels is increase() useful?
4. Why is a route template needed instead of a raw URL?
5. Which RED signals should request rate be placed alongside?
6. Why does a traffic drop alert need expected traffic/baseline?
7. How does the rate window relate to the scrape interval?
8. How does `for` duration differ from the rate window?
9. How does duplicate scraping distort RPS?
10. When RPS is stable but p95 increases, which signals should you investigate next?

## 13. Key Takeaways

**A request rate dashboard** shows how many requests per second a service receives and processes, how traffic is distributed by route/method/status, and when traffic changes. Spring Boot/Micrometer provides HTTP request Timer metrics; Prometheus uses rate() to calculate RPS and increase() to estimate request volume over a time period. Grafana presents these queries along with variables, time ranges, and deployment annotations.

Place request rate alongside error ratio and latency according to the RED method to understand impact rather than reading RPS in isolation. Use route templates and low-cardinality dimensions; raw URLs, request IDs, and customer IDs are not suitable as metric labels. Choose the rate window based on the scrape interval, set alerts based on SLOs/baselines, and add a traffic floor and `for` duration to reduce noisy alerts. Verify metric names, labels, and scrape targets from actual exposition before putting a dashboard into production.
