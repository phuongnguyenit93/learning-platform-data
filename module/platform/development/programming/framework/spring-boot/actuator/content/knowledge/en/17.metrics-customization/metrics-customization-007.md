# Application-Computed Percentiles vs. Histogram-Computed Percentiles

When monitoring HTTP latency, p95 answers the question "What duration threshold covers about 95% of requests in the set under consideration?". If a service's 5-minute p95 is around 300 ms, roughly 95% of requests recorded in that window completed in 300 ms or less. To understand this number, identify which application instances, routes, and time range comprise that request set.

Spring Boot Actuator uses Micrometer to measure latency. For the same `Timer`, there are two ways to send latency distribution information to Prometheus.

| Question | Application-Computed Percentiles | Histogram-Computed Percentiles |
| --- | --- | --- |
| Who computes? | Micrometer estimates percentiles inside each process, per meter name and tag set. | Prometheus estimates percentiles when executing a query. |
| What does the application export? | A precomputed value for each configured percentile, e.g., a series with label `quantile="0.95"`. | Cumulative counters for each threshold, e.g., `_bucket` series with label `le="0.3"`. |
| Where does the time window live? | Micrometer's statistical window, tuned via `expiry` and `buffer-length`. | The query window, e.g., `[5m]` in `rate()` over scraped counters. |
| How are multiple instances combined? | You can view or compare each instance's p95. From individual p95s alone you cannot compute a combined p95, even if request counts are known. | Sum observations at each corresponding threshold, then compute the percentile over the combined distribution. Combined series must use the same unit and compatible threshold sets. |

## Computing at the Application

The following configuration exports p50 and p95 of the `http.server.requests` meter recorded by Spring Boot for HTTP requests. Place it in `application.properties` of a web application with Actuator and the `io.micrometer:micrometer-registry-prometheus` dependency.

```properties
management.endpoints.web.exposure.include=health,prometheus
management.metrics.distribution.percentiles.http.server.requests=0.50,0.95
```

After the application records requests, an exported sample may look like this. Other meter labels are omitted to focus on the percentile.

```text
http_server_requests_seconds{method="GET",uri="/orders",quantile="0.95"} 0.1
```

The value `0.1` is the estimated latency in seconds, i.e., 100 ms. Each tag combination is measured separately. Prometheus also attaches scrape target labels such as `job` and `instance`, allowing you to inspect each instance's p95 for the same route. Changing the chart's display time range only changes which stored p95 points the viewer sees. It does not cause Micrometer to recompute p95 across all requests in that range.

## Computing in Prometheus from Histograms

To view a service-wide p95, try the following configuration in a separate run. `percentiles-histogram` enables buckets chosen by Micrometer for the meter. `slo` adds a 300 ms boundary to directly count requests meeting that threshold.

```properties
management.endpoints.web.exposure.include=health,prometheus
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=300ms
```

In a classic Prometheus histogram, `le` is an inclusive upper bound. For an HTTP timer, `le="0.3"` counts all requests taking at most 0.3 seconds. A 100 ms request appears in every bucket with a threshold of 100 ms or higher, so do not sum buckets with different `le` values to find total requests. The `le="+Inf"` bucket contains all observations and equals `_count` for the same label combination.

Once Prometheus has scraped the service instances under `job="orders"`, the following query produces one p95 value for `GET /orders` requests across all instances over a 5-minute window. Assume `/orders` is the actual exported `uri` label value.

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{job="orders", method="GET", uri="/orders"}[5m])
  )
)
```

1. `rate(...[5m])` estimates the average increase rate of each bucket counter. Compute on each series first so Prometheus can handle a counter resetting to 0 when an instance restarts.
2. `sum by (le)` sums rates per matching threshold and aggregates away remaining labels. If you need per-route p95, remove the `uri` filter and keep both `uri` and `le` in `sum by (uri, le)`.
3. `histogram_quantile` locates the bucket containing the 95% mark and linearly interpolates within that finite bucket. The result is in seconds. Wide buckets around the target mark increase potential error. If the mark falls into the `+Inf` bucket, the function returns the highest finite upper bound, so it may fail to reflect a slow tail beyond that bound.

## Example of Two Instances with Uneven Traffic

In the same window, instance A handles 1,000 requests all taking 100 ms, while B handles 10 requests all taking 900 ms. Examining the sorted samples directly, A's p95 is 100 ms and B's p95 is 900 ms. The average of the two p95s is 500 ms, whereas 1,000 out of 1,010 requests completed within 100 ms. The combined p95 by nearest rank is the 960th observation, which is 100 ms. Even a request-count-weighted average is still just an average of two thresholds and cannot recover observation ordering.

Here are the **cumulative counts per threshold in the window** with an illustrative bucket set. The table shows observation counts for easy hand calculation. Actual queries operate on rates per bucket.

| Upper Bound | A | B | Total |
| --- | ---: | ---: | ---: |
| 80 ms | 0 | 0 | 0 |
| 120 ms | 1,000 | 0 | 1,000 |
| 300 ms | 1,000 | 0 | 1,000 |
| 1,000 ms | 1,000 | 10 | 1,010 |
| `+Inf` | 1,000 | 10 | 1,010 |

Prometheus interpolates at rank `0.95 × 1,010 = 959.5`, which lies in the interval (80 ms, 120 ms]. Assuming samples are uniformly distributed in that interval, the result is `80 + (120 − 80) × (959.5 − 0) / (1,000 − 0) = 118.38 ms`. The real samples in that bucket all sit at 100 ms. Histograms keep counts per interval, so Prometheus can aggregate two instances while only estimating p95 inside the interval.

If the question is "What percentage of requests completed in at most 300 ms?", use the 300 ms bucket and total request count directly. With the data in the table, the ratio is `1,000 / 1,010 ≈ 99.01%`.

```promql
sum(rate(http_server_requests_seconds_bucket{job="orders", method="GET", uri="/orders", le="0.3"}[5m]))
/
sum(rate(http_server_requests_seconds_count{job="orders", method="GET", uri="/orders"}[5m]))
```

The query returns a ratio from 0 to 1 when requests exist. Both numerator and denominator need the same label scope and time range. When there are no requests, the ratio is undefined.

## How to Verify When Applying

- Inspect `/actuator/prometheus` after generating traffic. Look for `quantile="0.95"` under the application-computed configuration, or `http_server_requests_seconds_bucket` with `le` labels under the histogram configuration. Check actual labels in Prometheus before applying filters.
- If p95 looks surprising, check request count in the window, scraped instances, and boundaries near p95. Low-traffic windows fluctuate easily. Classic histograms require the `+Inf` series to compute percentiles.
- When changing bucket configuration, verify consistency across instances before aggregating. If a boundary exists on only some instances, the sum at that boundary only counts instances with that series. Each bucket adds a time series per label combination, so enable histograms selectively for meters you need to measure and pick boundary ranges suited to the latencies you want to observe.
- Use application-computed percentiles when observing individual instances separately or when the monitoring system only accepts precomputed values. Use histograms when aggregating multiple instances, changing query windows, or computing attainment ratios for a configured threshold.

## References

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html)
- [Micrometer 1.13 — Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)
- [Prometheus — histogram_quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile)
- [Prometheus — rate](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate)
