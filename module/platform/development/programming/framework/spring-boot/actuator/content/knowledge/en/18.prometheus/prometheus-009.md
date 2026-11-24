# Distinguishing Per-Instance Aggregation from Per-Service Aggregation

Suppose the `checkout` service has two instances. Instance A handles most of the traffic and has only 1% errors. Instance B handles fewer requests but has 20% errors. If the monitoring dashboard only shows the error rate of the whole service, the errors on B can be hard to spot. If you only view each instance individually, the on-call engineer has to manually compute how many requests the entire service is serving and how many are failing.

## Choosing labels according to the question

| Scope | Which labels to keep when aggregating? | Questions it can answer |
| --- | --- | --- |
| Per instance | `service` and `instance` within the selected job scope. | Which instance receives low traffic, has high errors, or has high latency? |
| Per service | `service` and labels needed to separate environments. | How much traffic does the entire service receive? What error rate do users experience? |

In Prometheus, an `instance` is a scrape target, typically corresponding to a single process. By default, the `instance` label takes the `host:port` portion of the target. The `job` label identifies the scrape group, while `service` in this article is an operator-assigned label to identify the service. One job can scrape multiple services. Only use `job` as a proxy label for the service when the system maintains an appropriate mapping between the two concepts.

This example uses Actuator targets labeled with `service` directly in the Prometheus configuration:

~~~yaml
scrape_configs:
  - job_name: spring-apps
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ['checkout-a:8080', 'checkout-b:8080']
        labels:
          service: checkout
      - targets: ['catalog-a:8080']
        labels:
          service: catalog
~~~

Assume the target names resolve from Prometheus and the applications use the default Actuator path. If the system aggregates multiple clusters, add a label such as `cluster` to the grouping key when you need to keep each cluster's results separate. In the queries below, `service!=""` restricts the dataset to targets that carry a service label.

## Comparing two ways to calculate traffic

The example uses the request counter from Spring Boot's `http.server.requests`, exported to Prometheus as `http_server_requests_seconds_count`. One instance can export multiple series for the same meter due to different `uri`, `method`, or `status` values.

**Per instance**. Calculate requests per second for each series and aggregate auxiliary labels, keeping each instance as a separate result:

~~~promql
sum by (service, instance) (
  rate(http_server_requests_seconds_count{job="spring-apps", service!=""}[5m])
)
~~~

**Per service**. Use the same window and the same filters, but keep only `service`. The result sums the traffic of instances within each service:

~~~promql
sum by (service) (
  rate(http_server_requests_seconds_count{job="spring-apps", service!=""}[5m])
)
~~~

Apply `rate` before `sum` so Prometheus recognizes counter resets on an individual instance that just restarted. Suppose at a given time, the two `checkout` instances have traffic of 90 and 10 requests per second, while `catalog` has 40 requests per second. The per-instance query returns three results. The per-service query returns `checkout = 100` and `catalog = 40`.

## Service error rate must be computed from request counts

Suppose within the same measurement window, the two `checkout` instances have the following counts:

| Instance | Total requests | 5xx responses | 5xx rate |
| --- | ---: | ---: | ---: |
| `checkout-a:8080` | 900 | 9 | 1% |
| `checkout-b:8080` | 100 | 20 | 20% |
| `checkout`, combined across both instances | 1,000 | 29 | 2.9% |

The per-service rate is `(9 + 20) / (900 + 100)`. Taking the average of 1% and 20% gives 10.5% because that calculation assigns equal weight to both instances. The error rate users experience needs every request to have equal weight, so **aggregate the numerator and denominator separately before dividing**.

The following query returns the 5xx rate per service as a number from 0 to 1. To view as a percentage, multiply the result by 100.

~~~promql
sum by (service) (
  rate(http_server_requests_seconds_count{
    job="spring-apps", service!="", status=~"5[0-9][0-9]"
  }[5m])
)
/
sum by (service) (
  rate(http_server_requests_seconds_count{job="spring-apps", service!=""}[5m])
)
~~~

To find a failing instance, change both `sum by (service)` clauses to `sum by (service, instance)`. Both sides will match on the same label set. With either approach, apply the same measurement scope to numerator and denominator, except for the `status` filter reserved for the numerator.

If there is no 5xx series yet, the expression may return no result for that service. Once you have confirmed scrape data is complete and the absence of the 5xx series means no errors have occurred, you can fill in 0 on the matching grouping labels using `or on(service)` with `0 *` the total traffic in the denominator. When there is no traffic or insufficient scrape samples, display a missing-data state rather than interpreting the rate as 0%.

## For latency, aggregate the data as input to the calculation

- **Average latency**. Aggregate the increase rates of `_sum` and `_count` separately by the same key, then divide. `_sum` of a Prometheus timer is in seconds. Each instance's weight is the number of requests it served.
- **p95**. If instances export classic histograms with the same boundaries, aggregate bucket increase rates by the grouping label and keep `le` so Prometheus knows each bucket's boundary.

~~~promql
histogram_quantile(
  0.95,
  sum by (service, le) (
    rate(http_server_requests_seconds_bucket{job="spring-apps", service!=""}[5m])
  )
)
~~~

The result is the estimated p95 of measured requests in each service, in seconds. To view per-instance p95, use `sum by (service, instance, le)`. A p95 value computed separately on each instance lacks the distribution information needed to compute the p95 of the combined request set. If `_bucket` series are not present yet, check the histogram configuration before using the query.

## Reading both levels during incident investigation

1. Use per-service traffic and 5xx rate to identify the affected service.
2. Keep `instance` in the grouping key to find which instance contributes to errors. Compare both rate and request count to distinguish a high rate over few requests from errors affecting many users.
3. Check `up{job="spring-apps"}` per target to detect failed scrapes. The service can still return aggregated results from remaining instances with data. When total traffic is abnormally high, check whether the same target is being scraped twice across jobs or federated sources.

### References

- [Prometheus – Jobs, instances, and target labels](https://prometheus.io/docs/concepts/jobs_instances/)
- [Prometheus – Aggregation operators and vector matching](https://prometheus.io/docs/prometheus/latest/querying/operators/)
- [Prometheus – rate and histogram_quantile functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Spring Boot 3.3 – Spring MVC Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)