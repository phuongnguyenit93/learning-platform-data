# Latency Dashboard for Spring Boot

In the **Dashboard and Alert** chapter of the **SPRING_BOOT_OBSERVABILITY** module, a latency dashboard answers three questions: which requests are slow, at which layer is latency increasing, and is the impact significant enough to warrant an alert? A good dashboard presents latency over time, by percentiles, and grouped by stable operations, while also allowing you to jump from aggregated figures to traces/logs to investigate representative requests.

Latency should not be represented solely by an average value. Mean can hide a cohort of very slow requests; p95/p99 reveal the user experience at the tail of the distribution. However, percentiles are only meaningful when histograms are configured properly, sample sizes are large enough, and series are aggregated along consistent dimensions. Dashboards must accompany latency with error rate, throughput, and saturation to explain why latency happens.

In **SPRING_BOOT_OBSERVABILITY**, Micrometer metrics provide measurements from Spring Boot HTTP server/client, database pools, and custom observations; tracing provides details for individual requests/operations. This lesson designs a latency dashboard from service overview down to endpoints/dependencies, explains histograms and percentiles, provides PromQL examples, alert windows, exemplars, and how to validate the dashboard.

## 1. What Is Latency and Where Should It Be Measured?

Latency is the time an operation takes to complete. In a web application, measurement boundaries must be clearly defined:

- **HTTP server latency:** from when the server receives the request until the response completes at the instrumentation boundary.
- **HTTP client latency:** time spent calling a downstream service.
- **Database latency:** time for JDBC/transaction operations or query spans per instrumentation.
- **Messaging latency:** publish time or consumer processing time; queue wait time is a separate quantity.
- **Business operation latency:** time to complete a business step instrumented with Observation.

Do not sum these latencies directly if their boundaries overlap. For instance, HTTP server duration already includes database and HTTP client wait times; adding server duration to dependency durations will double-count.

```text
Client
  |
  v
HTTP server observation -------------------- total request latency
  |
  +--> application processing
  |
  +--> database observation ---------------- DB duration
  |
  +--> HTTP client observation ------------- downstream duration
  |
  +--> messaging publish observation ------- send duration
```

Overview dashboards usually start with server latency. Drill-down dashboards use client/database/business operation latency to locate the slow layer. Traces show the spans inside a specific request and the relationships between them.

## 2. Mean, Median, and Percentiles

| Statistic | Meaning | When to Use |
| --- | --- | --- |
| Mean (average) | Total duration divided by number of observations | Track general trends; must be read alongside percentiles |
| p50 | 50% of observations have a duration no greater than this value | Represents the middle of the distribution |
| p90 | 90% of observations have a duration no greater than this value | Observe requests slower than the majority of traffic |
| p95 | 95% of observations have a duration no greater than this value | Track common tail latency |
| p99 | 99% of observations have a duration no greater than this value | Track severe tail latency |
| Max | Slowest observation in the window/series | Spot outliers; sensitive to a single sample |

For example, p95 = 800 ms means roughly 95% of observations in the calculation scope took at most 800 ms; the remaining ~5% were slower. It does not mean every request took 800 ms.

Percentiles are calculated over the distribution within a specific window and set of series. Do not take the p95 of each instance and average them to get a service-wide p95; percentiles are not additive like sum/count. With Prometheus histograms, aggregate bucket counts first before calculating the quantile.

## 3. Histograms and Distribution Configuration

To compute percentiles that can be aggregated across instances, histogram buckets must be exported. A Micrometer timer can publish count, total time, and histogram buckets depending on the registry/configuration.

Example distribution configuration for HTTP server requests:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms,300ms,500ms,1s,2s
```

Properties and meter names should be verified against your Spring Boot/Micrometer version. SLO boundaries serve as useful buckets for latency targets; histogram configuration increases the number of time series, so dimensions and bucket counts must be controlled.

Histograms can be enabled for custom timers via the corresponding convention/configuration. Do not enable histograms for all meters using a wildcard without evaluating cardinality, storage, and scrape volume first.

### Histogram vs. Summary

| Type | Characteristics | Aggregability |
| --- | --- | --- |
| Histogram | Exports bucket counts alongside count/sum | Buckets can be summed across instances before computing quantiles |
| Client-side summary/percentile | Computes quantiles in-process and exports results | Percentiles cannot be combined into an accurate service-wide percentile |

If you need service-wide p95/p99 across multiple replicas, histograms are usually more suitable. Verify how your registry supports histograms and how the exporter converts metrics.

## 4. Dashboard Overview: RED Method

RED is a way to organize dashboards for request-driven services:

- **Rate:** requests per second.
- **Errors:** proportion of failed requests.
- **Duration:** request processing time.

| Panel | Content | Question |
| --- | --- | --- |
| Request rate | Requests/second | Has traffic changed? |
| Error rate | 5xx or outcome error / total requests | Are many requests failing? |
| Latency p50/p95/p99 | Server request duration | How long are users waiting? |
| Requests by route | Rate by route template | Which endpoints receive the most traffic? |
| Latency by route | p95/p99 by route template | Which routes contribute to tail latency? |

Do not lump all status codes into errors if you need to distinguish client errors from server errors. Some systems treat 4xx as business/client errors, while availability SLOs only count 5xx or outcomes per contract. Clearly define error classification before authoring panels.

## 5. PromQL Examples for Latency

Prometheus typically converts timer histograms into series suffixed with `_bucket`, `_sum`, `_count`. Actual metric names may be normalized from Micrometer meter names, such as `http_server_requests_seconds_bucket`; verify the exposition endpoint before using queries.

### Request rate

```promql
sum(rate(http_server_requests_seconds_count[5m]))
```

### Mean latency

```promql
sum(rate(http_server_requests_seconds_sum[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

### Service-wide p95

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

### Service-wide p99

```promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

### p95 by route

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

These queries are examples for Prometheus classic histograms. Actual labels may be `uri`, `method`, `status`, `outcome`, `exception`, or other names depending on the Micrometer version/convention. Keep route templates instead of raw paths with path variables. If histograms are not enabled/exported, quantile queries cannot return meaningful results.

## 6. Choosing Dimensions and Controlling Cardinality

| Dimension | Use? | Notes |
| --- | --- | --- |
| Service name | Yes | Identifies the workload |
| Instance/pod | Selectively | Useful for spotting an anomalous replica |
| HTTP method | Yes | Small set of values |
| Route template | Yes | e.g., /orders/{id}, do not use raw URLs |
| Status/outcome | Yes | Bounded set of values |
| Dependency name | Yes | Stable service/database name |
| Tenant ID/user ID | No | High cardinality and potentially personal data |
| Request ID/Trace ID | No | Nearly a unique value per request |
| Query string | No | Dynamic data and potentially sensitive |

If a dashboard needs to view latency by tenant, use controlled analytics/log queries or policy-compliant trace searches rather than adding tenant ID to default metric labels.

## 7. Drill-Down from Service to Endpoint and Dependency

A latency dashboard should be structured from overview to detail:

1. **Service overview:** rate, error rate, p50/p95/p99, and saturation.
2. **Route view:** latency and error rate by route template/method.
3. **Dependency view:** HTTP client, datasource pool, database operations, and messaging.
4. **Instance view:** compare replicas to spot a misbehaving pod.
5. **Trace view:** open a representative trace from an exemplar or query the trace backend.

You do not need to put every metric on a single dashboard. Use dashboard links/variables to transition from the service overview to route/dependency panels with the same service and time range.

### Linking latency with saturation

Increased latency can stem from CPU, thread pool, connection pool, queue, or downstream saturation. Read latency alongside these signals:

| Signal | Metric concept | How to interpret |
| --- | --- | --- |
| CPU pressure | Process/system CPU | High CPU alongside rising latency can indicate compute saturation |
| JVM pauses | GC pause duration/count | Long pauses can cause latency spikes |
| Thread pool | Active threads, queue/rejected tasks | Queue wait or pool exhaustion |
| HTTP client pool | Active/pending connections, acquire time | Slow downstream connection acquisition |
| Datasource pool | Active/idle/max/pending, acquire time | JDBC requests waiting for connections |
| Messaging | Queue depth, oldest age, consumer rate | Async workflow experiencing backlog |

Latency panels only show the symptom; saturation panels and traces help pinpoint the cause.

## 8. Using Traces to Explain Tail Latency

When p99 increases, open several slow traces within the same time range. Compare server span duration, database spans and the number of database calls, HTTP client spans/retries/timeouts, lock/wait or custom business spans, async boundaries, and context propagation.

A single trace is just an example, not representative of the entire distribution. Select multiple slow traces and one normal trace for comparison. If the backend supports exemplars, histogram buckets can link metric samples to a Trace ID without adding Trace ID as a label.

Exemplar availability depends on the registry, exporter, backend, and scrape configuration. Not every Prometheus deployment automatically displays trace links; check the actual integration.

## 9. Choosing Time Windows and Avoiding Misleading Dashboards

The time window affects percentile stability:

- Window too short: few observations, p99 fluctuates wildly or lacks sufficient buckets.
- Window too long: masks short spikes and reacts slowly to new incidents.
- Low traffic: p99 may be unstable due to low sample count.
- Time-of-day varying traffic: must compare against the same time-of-day window or an appropriate baseline.

| Window | Used For |
| --- | --- |
| 1–5 minutes | Investigating an active incident |
| 15–30 minutes | Observing recent trends and recovery |
| 1–6 hours | Analyzing load changes throughout the day |
| 7 days | Daily/weekly traffic cycle baseline |

These are suggestions, not fixed thresholds. Choose the range based on traffic volume, scrape interval, histogram configuration, and SLO targets.

Do not compare the p99 of two services with different traffic volumes while ignoring sample counts. Display request count/rate next to percentiles so viewers know whether the sample size is large enough.

## 10. Alerts Based on Latency and SLO

Dashboards help operators understand the state; alerts should fire when user experience exceeds thresholds for a sufficient duration. Base thresholds on the service's SLO/contract rather than copying a generic number.

Policy examples:

- p95 exceeds the latency objective continuously over a window.
- The proportion of requests exceeding a latency boundary rises.
- Error rate and latency increase together.
- High latency occurs specifically on a critical route.
- Tail latency rises alongside datasource/HTTP client pool saturation.

For latency SLOs phrased as "percentage of requests completing under T," histograms can compute the percentage of observations falling under bucket T. This is often a better basis than alerting on p99 alone during low traffic.

### Multi-window alerts

Multi-window alerts help avoid reacting to brief spikes: a short window detects severe current violations; a longer window confirms the violation is sustained and has meaningful impact.

For availability/error-budget SLOs, multi-window burn-rate alerts can be appropriate. For latency SLOs, define good/bad events by the latency boundary and use the bad-event ratio; do not blindly apply an availability formula if the latency SLO is defined differently.

## 11. Example Alert Using Latency Buckets

Suppose a service has an objective: at least 99% of requests complete within 500 ms. With a classic histogram having bucket `le="0.5"`, you can calculate the proportion of requests exceeding 500 ms:

```promql
1 -
(
  sum(rate(http_server_requests_seconds_bucket{le="0.5"}[5m]))
  /
  sum(rate(http_server_requests_seconds_count[5m]))
)
```

The result is the proportion of requests slower than 500 ms over a 5-minute window (mindful of bucket and metric labels). You can alert when the bad-event ratio exceeds the error budget allowance for a long enough duration and sample count meets a minimum threshold.

Do not set thresholds based solely on the 1% example. Translate SLOs into alert thresholds according to violation severity, traffic, and acceptable impact duration. Add a `for` duration and a minimum traffic condition to prevent alerts when only a few requests occur.

## 12. Latency Dashboards for Different Layers

| Dashboard | Latency Panels |
| --- | --- |
| HTTP server | p50/p95/p99 by route, method, and status/outcome |
| HTTP client | p95 by dependency/remote service, timeouts, and retries |
| Database | JDBC acquire/usage time, query span duration, transaction duration |
| Messaging | Producer send duration, consumer processing duration, queue age |
| Business operations | Observation timer by operation name and outcome |
| JVM/runtime | GC pauses, thread scheduling, and process saturation for cross-reference |

Do not use datasource connection usage time as a substitute for query duration; usage may cover the entire time a connection is held. Do not use consumer processing duration as a substitute for queue wait age; messages can wait a long time before a consumer processes them.

## 13. Validating Dashboards Before Production Use

Dashboards should be tested like an operational product:

1. Confirm metric names, units, and labels from `/actuator/prometheus` or the actual registry.
2. Verify histogram buckets are exported and include buckets matching the latency objective.
3. Generate test traffic with normal latency and controlled slow latency.
4. Compare count/sum/buckets against the number of observations generated.
5. Verify p95/p99 are computed after aggregating histogram buckets, not by averaging quantiles across replicas.
6. Verify route templates do not create series per path variable.
7. Verify the dashboard displays sample count/rate alongside percentiles.
8. Verify trace exemplars/links work if configured.
9. Test alerts with simulated data both exceeding and staying within the objective.
10. Verify dashboard variables/time ranges do not inadvertently filter out a service or instance.

### Dashboard test matrix

| Scenario | Expected Result |
| --- | --- |
| Zero traffic | Percentiles meaningfully show no data/empty, not a fake 0 ms |
| Normal traffic | Rate, count, and latency are reasonable |
| One slow route | Route panel reflects increased p95/p99 |
| One slow instance | Instance breakdown highlights the outlier replica |
| Slow database | Dependency panel and traces reveal DB contribution |
| Histogram disabled | Dashboard clearly warns/displays missing percentile data |
| Low traffic | Percentiles are read alongside sample count |
| Route path with ID | Series still use the route template |
| Latency SLO violated | Alert fires according to window/policy |
| Recovery | Alert resolves and latency returns to baseline |

## 14. Case Study

A Spring Boot API has 20 replicas. The dashboard shows mean latency of 120 ms, p50 of 90 ms, p95 of 700 ms, and p99 of 2.4 seconds. Request rate increases 30% during peak hours. Datasource active connections are frequently near max, pending threads are rising, while HTTP client latency to pricing-service remains stable.

**Questions:**

1. Why is a 120 ms mean insufficient to conclude the API is performing well?
2. Which dashboard panels help identify the database pool as the suspect?
3. Why shouldn't you average the p95 of the 20 replicas to compute the service p95?
4. Which traces should you inspect to confirm the database contribution?
5. If the objective is 99% of requests under 500 ms, which bad-event ratio should you track?

**Analysis hints:**

- p95/p99 reveal significant tail latency even though most requests are fast; the mean hides the slow cohort.
- Inspect datasource active/idle/max/pending, acquire duration, usage duration, DB query spans, lock waits, and HTTP server p95 by route.
- Percentiles do not aggregate linearly; aggregate histogram buckets before computing service-wide quantiles.
- Open several slow traces and a normal trace within the same window; compare DB spans, transaction duration, and other dependency spans.
- Use the 500 ms histogram bucket to calculate the proportion of requests exceeding the boundary, along with sample count and a multi-window policy.

### Completion Checklist

| Topic | Able to Explain/Verify |
| --- | --- |
| Latency boundaries | Distinguish server, client, DB, messaging, and business duration |
| Percentiles | Read mean, p50, p95, p99, and sample count |
| Histograms | Configure appropriate buckets and understand cardinality |
| RED dashboard | Combine rate, errors, and duration |
| PromQL | Aggregate histogram buckets before quantiles |
| Dimensions | Use stable route templates/services/dependencies |
| Drill-down | Move overview → route → dependency → trace |
| Exemplars | Link metric samples with traces if backend supports it |
| Alert/SLO | Alert based on latency objectives and time windows |
| Validation | Verify data, queries, variables, and alert behavior |

**Key Takeaways:** A latency dashboard must show distributions, not just the mean. Use p50/p95/p99 alongside request count/rate, error rate, and saturation; enable histograms with SLO-aligned buckets and aggregate buckets before calculating service-wide quantiles. Choose low-cardinality dimensions such as service, method, route template, and dependency; avoid request/user/trace IDs as metric labels. Drill down from HTTP server to database/client/messaging and open representative traces. Alert on latency objectives and sufficiently stable windows, and validate dashboards with test traffic before relying on them in production.
