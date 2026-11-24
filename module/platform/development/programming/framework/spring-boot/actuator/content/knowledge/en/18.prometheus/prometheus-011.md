# Identifying Counter Resets, Unstable Labels, and Intermittent Data

When a request count chart drops or suddenly has gaps, inspect the **raw series per scrape target**. A counter may decrease within the same series, a deployment may create a new series due to label changes, or Prometheus may be missing samples. These three phenomena require different verification approaches.

The examples use `http_server_requests_seconds_count`, the observation count series of the HTTP `Timer` that Micrometer typically exports for Spring Boot. `job="orders"` identifies the service's target group and `instance` identifies each target. Adjust filters to match the actual labels in the environment under test.

| Observation | Symptom in raw series | What to check |
| --- | --- | --- |
| Counter reset | Value decreases between two consecutive numeric samples of the same name and label set. | `resets()`, process startup time, or meter recreation. |
| Label change | Old and new series differ by at least one label. Each series has its own history. | Label sets before and after the event, tag configuration, and target discovery configuration. |
| Intermittent data | One or more timestamps are missing samples for the target series. | `up`, scrape errors, sample count in the window, and whether the application still exports that metric. |

## Counter reset within the same series

A counter accumulates event occurrences. When the process restarts, the in-memory counter may start again from 0, though the first sample scraped afterward may already be greater than 0. For example, the series of `app-a:8080` has four samples `100 → 112 → 5 → 18`. Prometheus interprets the `112 → 5` transition as a reset when using counter functions.

```promql
resets(http_server_requests_seconds_count{job="orders"}[15m])
```

The query returns the number of observed decreases for each series in a 15-minute window. A positive number is a signal to cross-check against startup times, deployment logs, or meter recreation. If the counter resets and then increases past its previous value between two scrapes, the two numeric samples may still increase and `resets()` will not see that reset.

To compute the request rate for the entire job, handle resets on each series before aggregating.

```promql
sum by (job) (
  rate(http_server_requests_seconds_count{job="orders"}[5m])
)
```

`rate()` returns the average rate in requests per second. `increase()` uses the same reset-handling principle to estimate the increase within the window. With the four samples above, the adjusted increase between the first and last sample is `(112 − 100) + 5 + (18 − 5) = 30` under the reset-to-zero model. Actual `increase()` results also depend on sampling timestamps and extrapolation to window boundaries. It can yield fractional numbers, and it cannot recover increases that were not scraped before the reset.

Summing raw values before computing the rate can mask resets. If one instance decreases by 107 while another increases by 150 between two scrapes, the sum still increases by 43. Computing `rate()` on each series preserves the decrease signal of the first instance.

## Label changes create a new series

A series' identity consists of the **metric name and the full label set**. Suppose the same address `app-b:8080` has `release="v1"` with samples `200 → 208` before deployment, and then `release="v2"` with samples `4 → 12` afterward. These are two distinct series. `resets()` may return 0 for both because each series is increasing. If the process also restarted, that is an event to check independently of the PromQL result.

To observe both label sets, query at the time of the event or inspect a time range spanning before and after.

```promql
http_server_requests_seconds_count{job="orders", instance="app-b:8080"}
```

- For HTTP tags, use a route template such as `/orders/{id}` for the `uri` dimension. Putting individual concrete IDs or request codes into labels increases the number of series and often leaves each series with very few samples.
- Determine which labels are needed to distinguish sources, such as `instance`, and which dimensions should be kept in the result, such as `uri`. You can aggregate by `job` and `uri` **after** `rate()` if the series measure the same kind of request.
- Check both tags exported by the application and labels attached by Prometheus. Changing a target address can also change `instance`. A new series needs enough samples to calculate a rate, so during target transitions a chart may show a brief gap.

## Intermittent data and zeros

A value of 0 is a valid sample. For instance, a counter that is consistently scraped yet remains flat has a rate of 0. When data is missing, a query may return an empty vector. For a series marked stale, instant selectors drop that series until a new sample arrives. A longer window may still contain samples from before the outage and still be able to compute a rate. That only indicates the window still has data to compute with.

Start with target health. `up=1` means a successful scrape, `up=0` means a failed scrape. When a target leaves discovery configuration, its `up` series may disappear. A successful scrape only confirms Prometheus received a valid response from the target. If a specific metric is missing, check the `/actuator/prometheus` response, label filters in the query, and metric filtering rules at scrape time.

```promql
up{job="orders", instance="app-a:8080"}
```

Count samples in the window and detect when a specific filter completely lacks samples.

```promql
count_over_time(http_server_requests_seconds_count{job="orders", instance="app-a:8080"}[5m])
```

```promql
absent_over_time(http_server_requests_seconds_count{job="orders", instance="app-a:8080"}[5m])
```

`count_over_time()` counts stored samples per series. When the filter has at least one sample in the window, `absent_over_time()` returns an empty vector. If the entire filter lacks samples, the function returns a single sample with value 1. When you need to detect an individual target missing a metric, filter for that specific target or cross-check against the expected target set. A filter across the whole job may still have data from other targets. Keep visual gaps to distinguish missing data from zero traffic.

## Hands-on with simulated data

Save the configuration below to `counter-series-test.yml`. Each position is one minute apart. `_` denotes a missing sample and `stale` denotes a staleness marker in the test data.

```yaml
rule_files: []
evaluation_interval: 1m

tests:
  - interval: 1m
    input_series:
      - series: 'http_server_requests_seconds_count{job="orders",instance="app-a:8080"}'
        values: '100 112 5 18 stale _'
      - series: 'http_server_requests_seconds_count{job="orders",instance="app-b:8080",release="v1"}'
        values: '200 208 stale _ _ _'
      - series: 'http_server_requests_seconds_count{job="orders",instance="app-b:8080",release="v2"}'
        values: '_ _ 4 12 21 30'
      - series: 'up{job="orders",instance="app-a:8080"}'
        values: '1 1 1 1 0 0'

    promql_expr_test:
      - expr: 'resets(http_server_requests_seconds_count{job="orders"}[4m])'
        eval_time: 3m
        exp_samples:
          - labels: '{instance="app-a:8080",job="orders"}'
            value: 1
          - labels: '{instance="app-b:8080",job="orders",release="v1"}'
            value: 0
          - labels: '{instance="app-b:8080",job="orders",release="v2"}'
            value: 0
      - expr: 'absent_over_time(http_server_requests_seconds_count{job="orders",instance="app-a:8080"}[90s])'
        eval_time: 5m
        exp_samples:
          - labels: '{instance="app-a:8080",job="orders"}'
            value: 1
      - expr: 'up{job="orders",instance="app-a:8080"}'
        eval_time: 5m
        exp_samples:
          - labels: 'up{instance="app-a:8080",job="orders"}'
            value: 0
```

Run with `promtool` from the Prometheus distribution.

```bash
promtool test rules counter-series-test.yml
```

The expected result is that all three checks pass. At minute 3, `app-a` has one decrease within the same series. `app-b` has two series that both increase even though the value at the start of release v2 is lower than at the end of v1. At minute 5, `app-a`'s 90-second window has no valid counter samples, while the `up` series still has sample 0 recording the failed scrape.

## References

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Prometheus — Data model and label sets](https://prometheus.io/docs/concepts/data_model/)
- [Prometheus — PromQL functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Staleness in queries](https://prometheus.io/docs/prometheus/latest/querying/basics/#staleness)
- [Prometheus — Jobs, scrape targets, and up](https://prometheus.io/docs/concepts/jobs_instances/)
- [Prometheus — Unit testing rules and expressions](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
