# Alerting on Latency Percentiles in Spring Boot

Latency percentiles indicate the response time within which a given percentage of requests completed over a time period. `p95 = 800 ms` means roughly 95% of observed requests completed in 800 ms or less; the remaining ~5% were slower. `p99` focuses even deeper on the slower tail. Percentiles reveal the experience of the slow request cohort that average latency can obscure.

The lesson **Alerting on Latency Percentiles** belongs to the **Dashboard and Alert** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides you through setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

After this lesson, you will be able to distinguish histograms and summaries, configure appropriate histograms with Micrometer/Prometheus, calculate p95/p99 using PromQL, design alerts based on latency SLOs and traffic volume, avoid false alerts during low traffic, and investigate alerts using route metrics, logs, and traces.

## 1. What Do Percentiles Tell Us?

Average latency can mask tail latency. If 99 requests take 100 ms and one request takes 10 seconds, the average is around 199 ms; that number does not make clear that the slowest request impacted a user.

Percentiles sort request times and pick a point in the distribution:

- **p50:** median; half of requests are faster than or equal to this value.
- **p90:** 90% of requests are faster than or equal to this value.
- **p95:** 95% of requests are faster than or equal to this value.
- **p99:** 99% of requests are faster than or equal to this value.
- **p99.9:** focuses on the extreme tail, typically requiring high traffic volume for a stable estimate.

For example, `p95 = 750 ms` and `p99 = 2.4 s` show that most requests respond quickly, yet a small group experiences high tail latency. Do not interpret p99 as "the worst request"; it is a quantile of the distribution.

## 2. Choosing Percentiles for Operational Goals

Percentiles must align with user experience and SLOs—do not pick p99 simply because sample dashboards have it.

| Percentile | Common Usage | Limitations |
| --- | --- | --- |
| p50 | Track baseline and typical latency shifts | Does not show the tail |
| p90/p95 | Alert on the experience of most users | Can miss very slow tails |
| p99 | Monitor tail latency for critical endpoints | Fluctuates at low traffic |
| p99.9 | Investigate extreme tails in high-traffic systems | Requires many observations and sufficiently fine histograms |

Set targets per route/operation if they have different latency budgets. A cache-read endpoint does not necessarily share the same threshold as a report-generation or payment-processing endpoint.

## 3. Histograms and Summaries

To compute percentiles in Prometheus, you need to understand metric representations:

| Metric Type | How It Works | Where Are Percentiles Computed? |
| --- | --- | --- |
| Histogram | Counts observations into cumulative buckets | Backend can calculate quantiles from bucket counts |
| Summary | Client calculates quantiles and exports configured quantiles | Quantiles computed in-process; cannot be accurately aggregated across instances like histogram buckets |

With Prometheus, histograms are generally more suitable when you need aggregated service-wide or per-route percentiles across multiple pods. Summary quantiles from multiple instances cannot be summed or averaged to produce an accurate cluster-wide quantile.

A histogram quantile is an estimate based on bucket boundaries; accuracy depends on bucket layout and data distribution. Buckets should cover the target latency region and the tail you need to monitor.

## 4. Enabling Histograms for HTTP Server Requests

Spring Boot/Micrometer can enable percentile histograms for the HTTP server request Timer via distribution configuration. Illustrative example:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Meter filter names and property bindings should be verified against your Spring Boot/Micrometer version. Some projects use the meter name `http.server.requests`; Prometheus exports typically normalize this to `http_server_requests_seconds`. Verify scrape output before writing queries.

If you need specific bucket boundaries, configure service-level SLO boundaries or explicit buckets as supported by your registry/version. Do not broadly enable histograms for every meter without first evaluating cardinality and storage costs.

## 5. Histogram Buckets and Prometheus Series

A Prometheus histogram typically exports the following series:

```text
http_server_requests_seconds_bucket{le="0.1",...}
http_server_requests_seconds_bucket{le="0.25",...}
http_server_requests_seconds_bucket{le="0.5",...}
http_server_requests_seconds_bucket{le="1.0",...}
http_server_requests_seconds_bucket{le="+Inf",...}
http_server_requests_seconds_count{...}
http_server_requests_seconds_sum{...}
```

The `le` label denotes the bucket's upper bound. Bucket counts are cumulative: the `le="1.0"` bucket includes observations less than or equal to 1 second, including observations already counted in smaller buckets.

Histograms multiply the number of series for every label combination. With many routes, methods, statuses, exceptions, instances, and custom tags, series cost can escalate quickly. Use route templates and bounded labels; only enable histograms for meters that need percentiles.

## 6. Computing p95 with histogram_quantile

PromQL to compute service-wide p95:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

To compute p99, replace `0.95` with `0.99`. Apply `rate()` to bucket counters before aggregating to handle per-instance counter resets.

Do not drop the `le` label from aggregation before calling `histogram_quantile`; the function needs bucket boundaries to interpolate the quantile.

## 7. Percentiles by Service, Route, and Method

By service, if the `service` label exists:

```promql
histogram_quantile(
  0.95,
  sum by (service, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

By route:

```promql
histogram_quantile(
  0.95,
  sum by (uri, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

By method and route:

```promql
histogram_quantile(
  0.99,
  sum by (method, uri, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Labels in these examples are illustrative only. Only group by labels actually present in the series and needed for operational decisions. Use URI route templates, not raw URLs containing IDs or query parameters.

## 8. Choosing the Time Window

Percentiles are computed over observations within the query window. Short windows react quickly but are noisy; long windows are more stable but can delay incident detection.

| Window | Characteristics | When to Use |
| --- | --- | --- |
| 1m | Fast reaction, sensitive to bursts | Investigation dashboards or high traffic |
| 5m | Balances speed and stability | Common alert window for steady-traffic services |
| 15m | Smoother, slower reaction | Trends and sustained degradation alerts |
| 1h | Long-term trend | Capacity planning; unsuitable for fast incident detection |

No single window fits every service. Check your scrape interval, evaluation interval, request volume, and how fast the workload changes. With a 30-second scrape interval, a 1-minute window has very few samples.

## 9. Alerting When p95 Exceeds Latency Objectives

Example Prometheus alert rule when p95 stays above 800 ms:

```yaml
groups:
  - name: spring-boot-latency
    rules:
      - alert: HttpP95LatencyHigh
        expr: |
          histogram_quantile(
            0.95,
            sum by (service, le) (
              rate(http_server_requests_seconds_bucket[5m])
            )
          ) > 0.8
        for: 10m
        labels:
          severity: page
        annotations:
          summary: HTTP p95 latency is above objective
          description: Inspect route latency, errors and dependency traces.
```

The threshold `0.8` is in seconds, not milliseconds. Both the value and `for` are examples only; set them based on SLOs, route criticality, and baselines. Add `service`/`environment` labels matching your Prometheus schema.

A p95-only alert is not enough if traffic is low. Combine it with a minimum request volume to avoid alerting on just a few observations:

```promql
histogram_quantile(
  0.95,
  sum by (service, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
) > 0.8
and
sum by (service) (
  rate(http_server_requests_seconds_count[5m])
) > 1
```

The 1 request/second threshold is an example only. For low-traffic but critical endpoints, use synthetic monitoring or alerts on transaction-specific SLIs.

## 10. Tail Latency and SLOs

Latency SLOs often define the percentage of requests completing under a threshold, e.g., 99% of requests under 500 ms. This is closer to a good-event ratio than simply watching a p99 line on a dashboard.

If the histogram has a bucket boundary at 0.5 seconds, you can compute the proportion of requests under the threshold:

```promql
sum(rate(http_server_requests_seconds_bucket{le="0.5"}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

This is the ratio of requests with duration at most 500 ms according to the bucket. The bucket boundary must exist with that exact label value; if there is no `le="0.5"` bucket, configure the boundary or use the nearest bucket with an understanding of the approximation error.

For latency SLOs, alerting on the good-event ratio can be easier to interpret and better aligned with error budgets than a single p99 threshold. Percentiles remain useful for debugging the tail and visualizing the distribution.

## 11. Multi-Window and Burn-Rate Alerts

A brief p95 spike may self-resolve, whereas moderate sustained degradation can consume significant error budget. Multi-window alerts combine:

- A short window to detect high-impact incidents immediately.
- A long window to confirm degradation is sustained.
- Traffic volume to avoid drawing conclusions from few samples.
- SLO burn rate to tie alerts to the budget.

Do not apply the same percentile threshold to all routes. Endpoints with different latency objectives need separate rules or managed labels/policies. For SLO-driven systems, prefer multi-window burn rates over an agreed latency good-event ratio.

## 12. Excluding Non-User Traffic

Health probes, synthetic checks, and internal calls can skew percentiles. Before excluding traffic, clarify whether the dashboard measures user experience or total server workload.

If probes have dedicated routes, filter consistently across all bucket and count series:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri!~"/actuator/health.*"
    }[5m])
  )
)
```

Do not exclude traffic merely because it is internal if that traffic itself represents a critical dependency. Clearly document the scope and filters of panels/rules so viewers know which request group the percentile represents.

## 13. Cardinality and Bucket Design

Histogram series count scales by the number of buckets multiplied by the number of label combinations. Keep cardinality within budget:

- Use route templates instead of raw URIs.
- Do not add request IDs, trace IDs, user IDs, or exception messages as labels.
- Enable percentile histograms only on necessary meters.
- Choose buckets concentrated around the latency objective and tail you monitor.
- Review series counts after adding new routes or custom tags.

Buckets that are too wide make percentiles imprecise in the critical region. Buckets that are too dense inflate series/storage costs. If the SLO is 500 ms, have a boundary near 500 ms rather than only having 0.1 s and 1 s buckets.

## 14. Testing Alert Rules

Testing must verify both metric data and alert semantics:

| Test | What to Prove |
| --- | --- |
| Histogram enabled | Bucket series appear on the scrape endpoint |
| p95 query | Quantile computes accurately against known bucket fixtures |
| p99 query | Tail query uses the right quantile and aggregation labels |
| Instance aggregation | Counter resets do not corrupt rates/aggregates |
| Low traffic | Minimum-volume guard prevents false pages |
| No traffic | Rule handles no data according to policy |
| Route filter | Probe/route exclusions apply consistently |
| SLO bucket | Required boundary exists and good-event ratio is accurate |
| Alert duration | `for` and evaluation windows behave as expected |

Prometheus `promtool test rules` can run alert rule tests against series fixtures. Use fixtures with multiple instances and bucket boundaries to catch missing `le` in aggregations or mismatched denominators.

## 15. Common Pitfalls

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| p95 query has no data | Histogram disabled or wrong metric name | Check scrape output and meter configuration |
| p95 is 0 or nonsensical | Bucket aggregation missing `le` or wrong labels | Inspect raw bucket series and PromQL grouping |
| p99 fluctuates wildly | Low traffic or overly sparse buckets | Increase volume window; check p95 and good-event ratio |
| Alert always firing | Threshold below baseline or ms/seconds unit mix-up | Verify units and SLO threshold |
| Alert not firing | Missing histogram buckets, label mismatch, or no data | Query directly and inspect rule evaluation |
| Per-pod percentile differs from service-level | Quantiles computed individually then wrongly aggregated | Sum bucket rates before `histogram_quantile` |
| Series count explodes after enabling histograms | Many labels combined with many buckets | Reduce labels and enable histograms selectively |
| Probes make p95 look artificially good | Very fast probe requests dominate the denominator | Clarify scope and filter probes uniformly |
| SLO latency query returns no data | Exact bucket boundary does not exist | Configure explicit bucket at the threshold |
| Summary quantiles fail to aggregate | Summary quantiles do not merge accurately across instances | Use histogram buckets for aggregated quantiles |

## 16. Real-World Scenario: p99 Rises Under Increased Database Pool Load

**Hypothetical context:** After a traffic surge, `orders-service` p50 stays around 90 ms, but p99 climbs from 700 ms to 3.2 seconds. Error rate has not risen noticeably. The p99 alert fires continuously.

Investigation workflow:

1. **Verify the query:** check that histograms are enabled, bucket boundaries, seconds unit, and aggregation across all instances.
2. **Check traffic:** inspect request rate to confirm the quantile has enough observations and is not dominated by probe traffic.
3. **Isolate routes:** group p95/p99 by route template and method to find the endpoint contributing tail latency.
4. **Cross-check saturation:** inspect Hikari pending/acquire time, database query latency, CPU throttling, and thread pools.
5. **Open traces:** pick an exemplar/trace representing a slow request and identify the prolonged downstream span.
6. **Compare deployment/config:** inspect pool size, concurrency, and query/index changes around the alert timestamp.
7. **Verify:** monitor p99, the percentage of requests under the latency objective, request volume, and error rate after remediation.

A stable p50 does not prove the system is healthy; tail latency can degrade a small but critical user segment. Use percentiles alongside good-event ratios and traces to assess impact.

## 17. Self-Check Exercises

**Exercise 1.** What does `p95 = 800 ms` mean?

*Hint:* Roughly 95% of observations have a duration no greater than 800 ms within the measurement window.

**Exercise 2.** Why can't you average each pod's p99 to get the service-wide p99?

*Hint:* Quantiles cannot be summed or averaged; aggregate histogram buckets first and then compute the quantile.

**Exercise 3.** How do histograms differ from summaries when aggregating across multiple instances?

*Hint:* Histogram buckets can be aggregated; summary quantiles are calculated locally and cannot be merged accurately.

**Exercise 4.** Why does a p99 alert need a minimum traffic guard?

*Hint:* A handful of observations can make the quantile swing wildly and trigger false alerts.

**Exercise 5.** Which label must `histogram_quantile` preserve when aggregating?

*Hint:* Keep `le` so the function knows bucket boundaries; also keep service/route if grouping along those dimensions.

**Exercise 6.** If the latency SLO is 500 ms, why do you need a bucket at or near 0.5 seconds?

*Hint:* A threshold-based good-event ratio requires the matching bucket boundary; the closest bucket affects accuracy.

**Exercise 7.** What does a stable p50 combined with a rising p99 suggest?

*Hint:* A small cohort of requests is slow; investigate routes, DB pools, downstream dependencies, and saturation.

**Exercise 8.** When should you alert on a good-event ratio instead of p99 alone?

*Hint:* When the SLO defines the percentage of requests completing under a latency threshold and the alert needs to tie into the error budget.

## 18. Key Takeaways

- Percentiles describe the latency distribution; p95/p99 reveal tail behavior that averages can hide.
- Histograms are suitable for aggregating quantiles across multiple instances; summary quantiles cannot be accurately merged via addition/averaging.
- Enable Micrometer percentile histograms deliberately and verify actual Prometheus bucket series/labels.
- Apply `histogram_quantile` to `rate()` of bucket counters; aggregate before computing the quantile and preserve the `le` label.
- Choose percentiles, thresholds, and windows based on SLOs, route criticality, scrape interval, and request volume.
- Combine minimum traffic guards, no-data handling, and seconds vs. milliseconds awareness to reduce false alerts.
- Design buckets around latency objectives; manage label cardinality and avoid raw IDs/URLs.
- For latency SLOs, good-event ratio/burn-rate alerts complement p95/p99; drill down via routes, saturation, logs, and traces.
