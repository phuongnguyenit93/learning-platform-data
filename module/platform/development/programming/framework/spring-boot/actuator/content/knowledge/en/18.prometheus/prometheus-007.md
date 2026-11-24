## Computing Request Rate and Error Rate from Counters over a Time Window

A recently restarted service can report a lower total request count than a service that has been running all day, even if it is currently handling more requests per second. Counters record cumulative counts. To know how many requests a service is handling and what percentage end in errors, measure the counter increase within the same time window.

### Choosing the right counter in Spring Boot Actuator

Spring Boot Actuator typically records HTTP processing times in a `Timer` with the Micrometer name `http.server.requests`. With Micrometer 1.13's default Prometheus export, `http_server_requests_seconds_count` is the number of requests recorded by the Timer. Even though the name contains `seconds`, the value of the `_count` series is a **count**. The `_sum` series of the same family measures total duration, in seconds.

Read `/actuator/prometheus` to confirm the exported names and labels. In this example, `status` is the HTTP status code as a string, while `job` is attached by Prometheus per the scrape configuration. Counters are often split into multiple series by instance, status code, method, and route. Each series has its own cumulative history.

### Request rate over 5 minutes

```promql
sum by (job) (
  rate(http_server_requests_seconds_count[5m])
)
```

At each evaluation timestamp, `[5m]` takes samples falling within the preceding 5 minutes, excluding the left boundary and including the right boundary. `rate` estimates the average increase **per second** of each series in the window. It adjusts when a counter decreases due to a reset and extrapolates to both ends of the window. At least two samples in the window are required to calculate a rate for a series. Then `sum by (job)` sums the rates of the instances and other label sets, keeping one result per `job`. The final unit is requests/second, counted over the request handling recorded by the Timer.

Order matters when an instance restarts. If you sum counter values across instances first, an increase in one instance can mask a decrease in another. Even if the sum still decreases, Prometheus does not know which instance's counter reset. Computing `rate` while each series is still separate lets Prometheus detect resets in the right place. A missed scrape can prevent Prometheus from seeing all resets or requests that occurred before a restart.

When you need to estimate the **number of requests across the entire window** rather than the rate, use `sum by (job) (increase(http_server_requests_seconds_count[5m]))`. `increase` is equivalent to `rate` multiplied by the number of seconds in the window, so the result can be fractional due to extrapolation. `irate` relies on the last two samples in the window and can be useful for viewing short spikes. `rate` over a window with enough samples is better suited when you need a stable value for monitoring or alerting.

### HTTP 5xx error rate

The numerator is the rate of requests with status codes from `500` to `599`. The denominator is the rate of **all** requests in the same scope and window, including those in the numerator. Choose `5xx` when the metric should reflect server error responses. If the business definition includes other specific codes, modify the numerator filter accordingly. Requests that fail at the network layer or ingress gateway before reaching the application may not appear in application-side counters.

The following expression calculates the percentage per `job`.

```promql
100 *
(
  sum by (job) (
    rate(http_server_requests_seconds_count{status=~"5[0-9][0-9]"}[5m])
  )
  or on (job)
  0 * sum by (job) (
    rate(http_server_requests_seconds_count[5m])
  )
)
/
(
  sum by (job) (
    rate(http_server_requests_seconds_count[5m])
  ) > 0
)
```

Two parts of the expression handle missing error series and zero traffic.

- `or on (job) 0 * ...` preserves the 5xx rate when a corresponding series exists. If a `job` has a measurable total rate but has never emitted a 5xx series, the expression uses 0 for the numerator. This works well when instrumentation and scraping are functioning normally. If the 5xx series disappears due to missing samples or label changes, a value of 0 can mask a scrape failure. Check target health using `up` and verify that the necessary series are still being exported.
- The `> 0` comparison in the denominator filters out `job`s whose total rate equals 0. The comparison acts as a filter, so it preserves the original rates of the remaining `job`s. When there are no requests, the rate is undefined. If the total rate is also absent due to missing data, the query returns no ratio for that `job`.

To calculate per route, use `sum by (job, uri)` in the sums and `or on (job, uri)` to match numerator and denominator properly. When filtering by `job`, `uri`, or `method`, apply the same scope filters to all branches. Only the error-counting branch adds the `status` condition.

### Verifying with two instances and one counter reset

Assume Prometheus scrapes every minute. In the data from minute 1 to minute 5, instance `a` handles 120 requests/minute, including 3 errors/minute. Instance `b` handles 30 requests/minute, including 6 errors/minute, and restarts between minute 2 and minute 3. The `200` counter of `b` is `300, 324, 24, 48, 72` respectively. The reset-adjusted increase between the first and last sample is `72 − 300 + 324 = 96` over 4 minutes, i.e., 24 `200` responses per minute. Adding 6 `500` responses per minute yields exactly 30 requests/minute.

| Instance | Requests/second | Errors/second | Error rate |
| --- | ---: | ---: | ---: |
| `a` | 2 | 0.05 | 2.5% |
| `b` | 0.5 | 0.10 | 20% |
| All of `checkout` | 2.5 | 0.15 | 6% |

The service-wide rate is `100 × 0.15 / 2.5 = 6%`. Taking the arithmetic mean of the two individual rates gives 11.25% because that calculation gives each instance equal weight, even though `a` handles four times as many requests as `b`.

Save the following data as `request-rate.test.yml` to test both queries with `promtool`. The `catalog` series has traffic but no 5xx samples. The `idle` series has a flat counter. The `late` series has only one sample, and `_` marks scrapes without samples. The percentage expression is rounded in the test check to avoid floating-point representation errors.

```yaml
rule_files: []
evaluation_interval: 1m
tests:
  - interval: 1m
    input_series:
      - series: 'http_server_requests_seconds_count{job="checkout",instance="a",status="200"}'
        values: '900 1017 1134 1251 1368 1485'
      - series: 'http_server_requests_seconds_count{job="checkout",instance="a",status="500"}'
        values: '20 23 26 29 32 35'
      - series: 'http_server_requests_seconds_count{job="checkout",instance="b",status="200"}'
        values: '276 300 324 24 48 72'
      - series: 'http_server_requests_seconds_count{job="checkout",instance="b",status="500"}'
        values: '24 30 36 6 12 18'
      - series: 'http_server_requests_seconds_count{job="catalog",instance="c",status="200"}'
        values: '100 160 220 280 340 400'
      - series: 'http_server_requests_seconds_count{job="idle",instance="d",status="200"}'
        values: '100 100 100 100 100 100'
      - series: 'http_server_requests_seconds_count{job="late",instance="e",status="200"}'
        values: '_ _ _ _ _ 42'
    promql_expr_test:
      - expr: >-
          sum by (job) (
            rate(http_server_requests_seconds_count[5m])
          )
        eval_time: 5m
        exp_samples:
          - labels: '{job="checkout"}'
            value: 2.5
          - labels: '{job="catalog"}'
            value: 1
          - labels: '{job="idle"}'
            value: 0
      - expr: >-
          round(
            100 *
            (
              sum by (job) (
                rate(http_server_requests_seconds_count{status=~"5[0-9][0-9]"}[5m])
              )
              or on (job)
              0 * sum by (job) (
                rate(http_server_requests_seconds_count[5m])
              )
            )
            /
            (
              sum by (job) (
                rate(http_server_requests_seconds_count[5m])
              ) > 0
            ),
            0.000001
          )
        eval_time: 5m
        exp_samples:
          - labels: '{job="checkout"}'
            value: 6
          - labels: '{job="catalog"}'
            value: 0
```

```bash
promtool test rules request-rate.test.yml
```

The expected result is `checkout` with 2.5 requests/second and 6% errors, `catalog` with 1 request/second and 0% errors, `idle` with rate 0 and no error rate, and `late` lacking enough samples to calculate a rate.

### Choosing a window and operational checks

- The window should contain multiple expected scrapes. If the scrape interval is 15 seconds, `[5m]` covers about 20 scheduled scrapes. A shorter window detects changes faster but is more prone to noise or missing samples. A longer window smooths more and keeps the impact of an error burst longer. The `[5m]` window is the data range at each query evaluation point, independent of the time step between points on a chart.
- Watch the request rate and error rate side by side. One error out of one request gives 100%, yet the metric has very little traffic. When an alert condition needs sufficient evidence, you can combine the error rate with a minimum request threshold in the same window.
- If a chart has gaps or abnormal drops, check `up` per target, sample counts, and the actual series labels. You can use `resets(http_server_requests_seconds_count[5m])` to see which series' counter decreased. Separately verify target completeness, since summation can still return numbers from the remaining instances with data when one instance is lost.

### References

- [Spring Boot 3.3 Actuator — HTTP metrics and Prometheus endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Prometheus — rate, increase, irate, and resets functions](https://prometheus.io/docs/prometheus/3.10/querying/functions/)
- [Prometheus — Operators and vector matching between labels](https://prometheus.io/docs/prometheus/latest/querying/operators/)
- [Prometheus — Unit testing PromQL expressions with promtool](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)