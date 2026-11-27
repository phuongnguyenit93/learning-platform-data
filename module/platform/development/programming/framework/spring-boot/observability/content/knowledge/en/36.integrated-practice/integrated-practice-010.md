# Building a Latency and Error Dashboard

## Context and Objectives

An API may still return HTTP 200 while responding so slowly that users abandon it. Another API may have low latency yet frequently return HTTP 500. If a dashboard only shows CPU, memory, or total request counts, operations teams will struggle to spot these two problems and find it even harder to identify which endpoint is causing the impact.

In this practice exercise, you build a RED-method (Rate, Errors, Duration) dashboard from HTTP metrics provided by Spring Boot Actuator and Micrometer, then visualize them in Grafana using Prometheus data:

- **Rate**: requests per second, overall and per route.
- **Errors**: error request rate and HTTP 5xx ratio. Track HTTP 4xx separately to distinguish client input errors from server-side processing failures.
- **Duration**: p50, p95, and p99 latencies. Percentiles reveal slow request cohorts that averages typically hide.

When complete, the dashboard should answer: what is current traffic, how long are users waiting, which endpoints concentrate errors, and when did those metrics change.

## 1. Data Flow and Prerequisites

Observability flow in this practice exercise:

~~~mermaid
flowchart LR
    A[Client sends HTTP request] --> B[Spring Boot application]
    B --> C[Micrometer Observation and Timer]
    C --> D[/actuator/prometheus]
    D --> E[Prometheus scrapes metrics]
    E --> F[Grafana dashboard]
~~~

The application needs Actuator and the Prometheus registry. With Gradle, declare the following dependencies; versions are managed by Spring Boot dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

If the project uses Maven, add spring-boot-starter-actuator and micrometer-registry-prometheus to dependencies, and let the Spring Boot parent or BOM manage versions.

Configure the Prometheus endpoint and HTTP server histograms in application.yml:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        "http.server.requests": true
      slo:
        "http.server.requests": 100ms,300ms,1s
~~~

http.server.requests is the Micrometer metric name before Prometheus normalization. percentiles-histogram instructs Micrometer to export histograms so Prometheus can compute percentiles over scraped data. The SLO boundaries add buckets at 100 ms, 300 ms, and 1 second; these are useful when a dashboard needs to measure the percentage of requests finishing under a specific threshold. Choose thresholds based on real service goals rather than treating example values as universal standards.

Only expose required endpoints. In a real deployment environment, protect /actuator/prometheus using internal networks, authentication, or appropriate access controls; never leave metrics endpoints publicly open to every client.

After starting the application, call a few APIs and verify:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Look for series whose names start with http_server_requests_seconds. Depending on Spring Boot version, registry, and tag configuration, names or tag sets may vary slightly. Inspect actual metrics before writing queries; subsequent queries assume the default HTTP timer metric is exported under the Prometheus names shown above.

Example Prometheus scrape config for an application running on the same Docker network with service name app:

~~~yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: spring-boot-app
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["app:8080"]
~~~

If running Prometheus directly on a developer machine, replace app:8080 with an address reachable by Prometheus, such as localhost:8080. In the Prometheus UI, verify the target state is UP and test querying http_server_requests_seconds_count before moving to Grafana.

## 2. Understanding the Metrics Before Writing PromQL

Micrometer records HTTP server requests using a timer. When exported to Prometheus, the timer typically produces these series:

| Series | Meaning | Usage |
|---|---|---|
| http_server_requests_seconds_count | Total recorded requests | Compute request rate and error ratio denominator |
| http_server_requests_seconds_sum | Cumulative processing duration in seconds | Compute average duration over an interval |
| http_server_requests_seconds_max | Maximum value over the timer's time window | Reference for spotting outliers; does not replace p95/p99 |
| http_server_requests_seconds_bucket | Request count with duration less than or equal to bucket bound le | Compute histogram quantiles and SLO compliance ratio |

Common HTTP tags include method, status, outcome, uri, and exception. uri should be the framework-provided route template, such as /api/orders/{id}, so requests to different IDs belong to the same metric series. Verify actual tags at /actuator/prometheus, especially when the application uses custom observation conventions or filters.

The unit of timers in Prometheus names is seconds. Hence, a p95 of 0.3 means 300 ms. When configuring Grafana panels, pick the seconds (s) unit or convert consistently to milliseconds; never label a value that is still in seconds as milliseconds.

Histogram buckets are cumulative: bucket le="0.3" counts requests completed in at most 0.3 seconds, while larger bounds include requests already counted in smaller buckets. When computing quantiles, keep the le label in the aggregation so histogram_quantile reconstructs the distribution. Never average per-instance p95 values because doing so does not yield a system-wide p95.

## 3. Writing PromQL Queries

Examples use the label job="$job", where $job is a Grafana dashboard variable. If you have not created this variable, replace the matcher with the actual job name or omit the job matcher when there is only one application. The filter uri!~"/actuator.*" excludes Actuator routes from business traffic; adjust the filter if the application uses a different management path.

### 3.1. Request Rate

Total requests per second over a 5-minute window:

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])
)
~~~

To compare traffic across routes and HTTP methods:

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])
)
~~~

rate() calculates the average per-second rate of increase from a counter over the selected window. A 5-minute window makes graphs less noisy than looking at a single scrape. If you need to investigate a very short traffic spike, narrow the window while keeping enough scrape samples for stable results.

### 3.2. p95 and p99 Latency

Overall application p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="$job",
      uri!~"/actuator.*"
    }[5m])
  )
)
~~~

p95 by route:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="$job",
      uri!~"/actuator.*"
    }[5m])
  )
)
~~~

Change 0.95 to 0.99 to compute p99. You can add method to sum by (le, uri, method) if you need to distinguish GET and POST. When aggregating across multiple instances, sum matching buckets first and only then call histogram_quantile; this preserves the combined distribution across exported buckets.

For comparison, average duration over 5 minutes is computed by dividing total duration by request count:

~~~promql
sum(rate(http_server_requests_seconds_sum{
  job="$job",
  uri!~"/actuator.*"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])),
  1e-9
)
~~~

Average is helpful for tracking broad trends but can mask a cohort of very slow requests. Operational dashboards should prioritize p95/p99 while keeping average as a reference metric if the team wants it.

### 3.3. HTTP 5xx Error Ratio

Compute the percentage of requests with 5xx status out of total requests:

~~~promql
100 *
sum(rate(http_server_requests_seconds_count{
  job="$job",
  status=~"5..",
  uri!~"/actuator.*"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])),
  1e-9
)
~~~

The result is a percentage, since both numerator and denominator are requests per second. clamp_min avoids division by zero when there is no traffic. When there are no requests, check the request rate panel to recognize idle traffic; a zero percentage alone is not enough to conclude the service is healthy.

5xx error rate by status helps identify which error group is rising:

~~~promql
sum by (status) (
  rate(http_server_requests_seconds_count{
    job="$job",
    status=~"5..",
    uri!~"/actuator.*"
  }[5m])
)
~~~

5xx ratio by route isolates problematic endpoints:

~~~promql
100 *
sum by (uri) (
  rate(http_server_requests_seconds_count{
    job="$job",
    status=~"5..",
    uri!~"/actuator.*"
  }[5m])
)
/
clamp_min(
  sum by (uri) (
    rate(http_server_requests_seconds_count{
      job="$job",
      uri!~"/actuator.*"
    }[5m])
  ),
  1e-9
)
~~~

HTTP 4xx should be displayed separately. Example query for 4xx rate:

~~~promql
sum by (status) (
  rate(http_server_requests_seconds_count{
    job="$job",
    status=~"4..",
    uri!~"/actuator.*"
  }[5m])
)
~~~

4xx responses can reflect invalid requests, denied access, or missing resources. They can still impact user experience, yet should not be lumped by default into the 5xx error ratio when assessing server reliability.

### 3.4. Ratio of Requests Meeting the Latency Threshold

Because the configuration added a 300 ms SLO bucket, you can measure the percentage of requests completing within 300 ms:

~~~promql
100 *
sum(rate(http_server_requests_seconds_bucket{
  job="$job",
  uri!~"/actuator.*",
  le="0.3"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="$job",
    uri!~"/actuator.*"
  }[5m])),
  1e-9
)
~~~

This query only works when the bucket series contains the exact label le="0.3". If that bucket is missing, check SLO configuration, histogram configuration, and actual exported data before creating the panel. You can replace 300 ms with the threshold agreed upon for your service.

## 4. Designing the Grafana Dashboard

Create a dashboard named Spring Boot - HTTP Latency & Errors and select Prometheus as the data source. Create a dashboard variable $job of type Query with label query:

~~~text
label_values(http_server_requests_seconds_count, job)
~~~

Set the variable to single-select or multi-select depending on how many services you want to compare. When using multi-select, adjust matchers to job=~"$job" so Prometheus accepts the regex generated by Grafana.

Suggested layout:

| Section | Panel | Query | Visualization |
|---|---|---|---|
| Overview | Request rate | Total request rate query from section 3.1 | Time series, unit req/s |
| Overview | HTTP 5xx ratio | 5xx ratio query from section 3.3 | Stat or time series, unit percent (0-100) |
| Overview | HTTP 5xx rate | Numerator of the 5xx ratio query | Time series, unit req/s |
| Overview | p95 latency | Overall p95 query from section 3.2 | Time series or Stat, unit seconds |
| Latency | p95 by route | p95 by route query | Time series, legend by uri |
| Latency | Overall p99 | Overall p99 query | Time series, unit seconds |
| Errors | 5xx by status | 5xx rate by status query | Time series, legend by status |
| Errors | 5xx ratio by route | 5xx ratio by route query | Table or time series |
| SLO | Requests under 300 ms | SLO bucket query from section 3.4 | Gauge or Stat, unit percent (0-100) |

Place key Stat panels in the top row so on-call engineers can read current status as soon as they open the dashboard. Use time series below to spot when metrics began changing. For the p95-by-route panel, limit the number of displayed routes or use a sorted table so the dashboard stays readable when an application has many endpoints.

A few settings make the dashboard easier to use:

- Pick a default time range such as 1 hour; allow expanding to 6 or 24 hours when investigating trends.
- Use a 30-second refresh or match operational cadence. Refreshing faster than the scrape interval does not produce newer data.
- Set consistent units: req/s for rates, seconds or milliseconds for latency, percent (0-100) for ratios.
- Add thresholds aligned with service SLOs. Example targets like 300 ms p95 or 1% error ratio are illustrative only; replace them with agreed commitments.
- Keep job and route filters clearly visible so viewers know which service a panel represents.
- Add panel descriptions documenting the rate(...[5m]) window, 5xx definition, and applied latency threshold.

## 5. Reading the Dashboard to Investigate Incidents

Read signals together rather than jumping to conclusions from a single panel.

**p95 rises, 5xx does not rise:** requests still succeed but run slowly. Check which route has elevated p95, check whether traffic spiked, then inspect traces to see whether time is spent in the database, downstream HTTP client calls, locks, or in-app processing. If only one route is affected, start from that route instead of changing service-wide settings.

**5xx rises on one or a few routes:** filter by route and status to scope the impact. Cross-reference logs by timestamp, exception, and trace ID to find specific failing requests. Metrics show trends and blast radius; logs provide event details; traces reveal which components the request traversed and where time was spent.

**4xx rises while 5xx stays flat:** check client changes, API contracts, authentication, or permissions. A burst of 404s could be crawlers or clients hitting deprecated endpoints; a burst of 401/403s could relate to token or policy configuration. Do not treat them as server errors without evidence.

**Request rate drops suddenly:** check whether the Prometheus target is still UP, whether the application restarted or lost connectivity, and whether inbound traffic actually dropped. If both request rate and other metrics vanish, check the scrape pipeline before concluding the app stopped receiving requests.

When jumping from the dashboard to distributed tracing, use the timestamp, route, and trace ID from logs to open the matching trace. Never add traceId, user ID, order ID, or URLs containing dynamic IDs as metric labels: each new value creates another time series, rapidly inflating cardinality and storage costs. Keep metrics aggregated, while request-level identifiers live in logs and traces. If exemplars are configured and your backend supports them, use exemplar links to jump from a histogram data point directly to a sample trace.

## 6. Practice and Verification

Complete the lab in the following order:

1. Add Actuator and the Prometheus registry, enable the prometheus endpoint, and configure histograms and SLO buckets.
2. Start the application, send requests to several APIs, and confirm http_server_requests_seconds_count increments in /actuator/prometheus.
3. Send requests to a test endpoint with slow responses and a test endpoint returning HTTP 5xx. Use existing endpoints in your app; do not inject error mechanisms into business endpoints solely for dashboard demos.
4. Configure the Prometheus scrape target and confirm the target is UP. Verify count, bucket, and status/uri labels carry data.
5. Add the Prometheus data source in Grafana, create the $job variable, then build panels for request rate, p95, 5xx ratio, and 5xx by route.
6. Send more successful and error requests, wait at least a few scrape cycles, and confirm the panels move in the expected direction.
7. Compare a query in Grafana against the exact same query run directly in Prometheus to catch matcher mistakes, variable issues, or unit mismatches.

### Completion Criteria

- Dashboard includes request rate, p95 latency, 5xx rate or ratio, 5xx by status, and latency by route.
- p95/p99 are computed from histogram buckets; aggregation preserves the le label and sums buckets across instances before computing quantiles.
- 4xx is observed separately from 5xx.
- Latency panels display proper seconds or milliseconds units; ratio panels display percentages.
- Dashboard has service filters, time range controls, and descriptions of calculation windows.
- No labels contain user IDs, resource IDs, trace IDs, or dynamic URLs causing high cardinality.
- When test error requests are sent, the dashboard reflects the relevant route and status after scrape intervals; when there is no traffic, viewers can tell from the request rate panel.

## 7. Common Issues and Troubleshooting

| Symptom | Common Causes | How to Check |
|---|---|---|
| No HTTP metrics present | Missing Prometheus registry, no requests sent yet, or different metric name | Check dependencies, call an API, and search for http_server_requests in Actuator |
| _count exists but _bucket is missing | Histograms not enabled or config not bound properly | Check management.metrics.distribution.percentiles-histogram and slo, then recheck Prometheus output |
| p95 shows no data | Wrong bucket metric name, mismatched job/uri filter, or no samples in window | Run raw bucket query, drop matchers one by one, and verify scrape target |
| Overall p95 skewed across multiple instances | Computing quantile per instance and averaging | Sum buckets by le before calling histogram_quantile |
| Error ratio is 0 despite errors | Status label mismatch, custom metric misses response, or filter excludes route | Check count series by status and confirm actual status codes |
| Dashboard generates too many series | Putting dynamic IDs, query strings, or arbitrary values into tags | Switch to route templates and keep only tags with finite value sets |
| Latency chart off by 1,000x | Confusing seconds with milliseconds | Check metric unit and Grafana unit; Prometheus timers in this example use seconds |

If the application uses custom observation conventions, a gateway, or another framework, tags and metric names may differ. In that case, take the actual series from /actuator/prometheus as your ground truth and update matchers and queries to match the exported schema.

## 8. Extension Exercises

1. Add a p99-by-route panel and identify the route with the highest p99 during a period with sufficient traffic.
2. Replace the 300 ms threshold with an agreed API SLO, then display the percentage of requests meeting the SLO and percentage breaching it.
3. Create an alert when error ratio exceeds a threshold over a sustained window, adding a minimum request rate condition to avoid noisy alerts during near-zero traffic.
4. Pick a timestamp when p95 spiked, find logs with the matching trace ID, and use the distributed trace to identify which span took the most time.

The final outcome of this practice is an operational RED dashboard: showing traffic, latency, and errors along a shared timeline, enabling filtering by service/route, and providing a clear starting point for deeper investigation with logs and distributed traces.
