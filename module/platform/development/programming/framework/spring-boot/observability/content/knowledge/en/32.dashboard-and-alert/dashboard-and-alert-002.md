# Error Rate Dashboard for Spring Boot

Error rate indicates the proportion of requests that end in failure over a time period. It is one of the most critical signals for evaluating the reliability of an HTTP service: latency may creep up slightly without users noticing, whereas an increasing error rate usually means requests are visibly failing. A good dashboard needs to show whether errors are rising or falling, which routes are affected, when the issue started, and whether it correlates with a dependency or a recent deployment.

The lesson **Error Rate Dashboard** belongs to the **Dashboard and Alert** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides you through setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

After this lesson, you will be able to define the numerator/denominator of error rate, distinguish HTTP 4xx and 5xx according to operational goals, build PromQL queries from HTTP server metrics, design dashboards by service/route/status, avoid inaccuracies at low traffic, configure time-windowed alerts, and link dashboards with logs/traces for investigation.

## 1. What Does Error Rate Measure?

Error rate is the proportion of requests considered failed out of the total requests evaluated within the same time period:

\[
\text{Error rate} =
\frac{\text{Failed requests}}{\text{Total requests}}
\times 100\%
\]

For example, if over 5 minutes a service receives 10,000 requests and 250 fail:

\[
\frac{250}{10\,000}\times 100\% = 2.5\%
\]

Both components must use the same scope and the same time window:

- **Numerator:** number of requests classified as errors.
- **Denominator:** total number of requests belonging to the same service/route/traffic scope.

If the numerator counts 5xx while the denominator only counts 2xx, the ratio no longer represents the error rate of traffic. If the numerator excludes probe traffic while the denominator still includes probe traffic, the ratio is also skewed.

Error rate is a ratio, not an absolute error count. 100 errors out of 1,000 requests equals 10%; 100 errors out of 1 million requests is only 0.01%. The dashboard should display both error count/rate and total request rate so viewers understand the scale of impact.

## 2. Choosing an Error Definition Suited to the Service

Not every HTTP 4xx is a server failure. For example, 400 may indicate invalid input, 401 unauthenticated, 403 insufficient permissions, and 404 a non-existent resource according to the API contract. These responses can be expected business outcomes.

A common classification:

| Group | Example | Counted toward service error rate? |
| --- | --- | --- |
| 2xx | 200, 201, 204 | No |
| 3xx | 301, 304 | Usually no, depends on semantics |
| Client 4xx | 400, 401, 403, 404, 409, 422 | Usually tracked separately |
| Service/gateway 5xx | 500, 502, 503, 504 | Usually yes |
| Transport failure | Timeout, connection reset, request with no response | Requires a separate metric or appropriate instrumentation |

The definition must follow the API's SLO and contract. For an API where 404 indicates a critical business failure, it can be tracked separately or included in a specific error budget. Do not apply a single global rule to every endpoint if their semantics differ.

There should be at least three indicators:

1. Server error rate: ratio of 5xx to total requests.
2. Client error rate: ratio of 4xx to total requests, optionally breaking out 401/403/404/409/422.
3. Request failure/timeout rate: failures that do not result in an HTTP response if instrumentation can capture them.

## 3. HTTP Server Metrics in Spring Boot

With Spring Boot Actuator and Micrometer, HTTP server requests are typically recorded via a Timer. In Prometheus, common series have names close to:

```text
http_server_requests_seconds_count
http_server_requests_seconds_sum
http_server_requests_seconds_max
```

Common labels include method, status, uri, exception, and outcome. Series/label names can vary depending on Spring Boot, Micrometer version, registry conventions, and framework adapters. Before authoring dashboards, inspect the application's own Prometheus endpoint to verify the actual metric names and label keys.

Example configuration to expose the Prometheus endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

This endpoint must be protected according to network/authentication policies. The Prometheus scraper must target the correct management endpoint, and service discovery must attach appropriate service/instance labels.

## 4. Building Numerator and Denominator with PromQL

Assume the application's metric has labels status, uri, method. The following query illustrates total request rate:

```promql
sum(rate(http_server_requests_seconds_count[5m]))
```

5xx request rate:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
```

5xx error rate:

```promql
100 *
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

This is a basic example. To compute the ratio for a specific service, add the same label filter to both numerator and denominator. If the dashboard covers multiple services, group by service on both sides:

```promql
100 *
sum by (service) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
sum by (service) (
  rate(http_server_requests_seconds_count[5m])
)
```

The `service` label must exist in the series. If Prometheus target labels are attached at the scrape layer, the query can use that label; otherwise, adjust to match the actual schema.

## 5. Error Rate by Route

Service-level error rate shows overall health, but does not pinpoint which endpoint is failing. You can group by route template:

```promql
100 *
sum by (uri) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
```

Use route templates such as /api/orders/{id}, not raw request URIs such as /api/orders/12345. Route templates help aggregate data and keep cardinality bounded.

When a route has low traffic, the ratio can jump from 0% to 100% because of a single failed request. Display request count/rate alongside the percentage and avoid ranking routes solely by percentage when the denominator is very small.

## 6. Tracking 4xx and 5xx Separately

Client error rate:

```promql
100 *
sum(rate(http_server_requests_seconds_count{status=~"4.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

Server error rate:

```promql
100 *
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

You can break down common statuses:

```promql
sum by (status) (
  rate(http_server_requests_seconds_count{status=~"4..|5.."}[5m])
)
```

Do not merge 4xx and 5xx into a single alert if operations teams need to take different actions. For example, a spike in 401s may indicate a client credential/configuration issue; a spike in 503s may indicate service overload or an unavailable dependency.

## 7. Handling Zero Traffic and Low Traffic

When the denominator is 0, error rate division is meaningless. PromQL may return no data/NaN depending on the expression and present series. Do not carelessly force the value to 0, because "no requests" is not the same as "requests with zero errors."

You can use a guarded query:

```promql
(
  100 *
  sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
  /
  sum(rate(http_server_requests_seconds_count[5m]))
)
and
sum(rate(http_server_requests_seconds_count[5m])) > 0
```

For alerts, combine error rate with a minimum request volume to avoid alerting on a single failed request:

```promql
(
  100 *
  sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
  /
  sum(rate(http_server_requests_seconds_count[5m]))
) > 5
and
sum(rate(http_server_requests_seconds_count[5m])) > 1
```

The thresholds of 5% and 1 request/second are examples only. Choose thresholds based on SLOs, traffic baseline, criticality, and error budget. For critical low-traffic routes, you may need alerts on absolute error counts or synthetic checks rather than ratios alone.

## 8. Excluding Health Probes and Non-User Traffic

Kubernetes liveness/readiness probes generate periodic requests. If probe traffic is included in the denominator, the service-level request rate can be inflated when user traffic is low. If a probe route fails, the error rate can rise due to orchestration checks rather than user requests.

If the metric has a stable route label, health paths can be excluded:

```promql
sum(
  rate(http_server_requests_seconds_count{
    status=~"5..",
    uri!~"/actuator/health.*"
  }[5m])
)
```

You must apply the same filter to the denominator. Do not exclude traffic by raw URI if the route label is not normalized. Also avoid excluding all internal requests in a way that hides real failures; clearly document whether the dashboard scope is user traffic, internal traffic, or all server requests.

## 9. Which Panels Should an Error Rate Dashboard Have?

A dashboard built for incident response should answer in sequence: are there errors, how severe is the impact, where are the errors occurring, and when did they start?

| Panel | Display | Question |
| --- | --- | --- |
| Service error rate | 5xx % over time | What is the current error rate and trend? |
| Request volume | Requests/second | Is the denominator large enough to interpret the ratio? |
| Error count/rate | 4xx and 5xx separately | How many errors are occurring and which type is increasing? |
| Error by status | 500/502/503/504 | Which status accounts for the majority? |
| Error by route | Top routes by 5xx rate/count | Which endpoint is affected? |
| Latency | p50/p95/p99 | Are errors accompanied by increased latency? |
| Instance breakdown | Error rate by instance/pod | Are errors concentrated on one replica? |
| Deployment markers | Version/release timeline | Does it coincide with a deploy/config change? |
| Dependency signals | DB, messaging, downstream errors | Is any dependency involved? |

Place service-level panels at the top of the dashboard, followed by route/instance breakdowns. Avoid putting hundreds of routes in a default panel; use top-k and drilldowns.

## 10. Combining Error Rate with Latency and Saturation

Error rate alone does not explain root cause. Combine the three RED signals:

- **Rate:** request rate.
- **Errors:** error rate/count.
- **Duration:** request latency distribution.

Add saturation signals such as CPU throttling, memory pressure, thread pool saturation, Hikari pending connections, queue depth, and downstream connection errors.

Some interpretation patterns:

| Error rate | Latency | Saturation/dependency | Investigation direction |
| --- | --- | --- | --- |
| Increasing | Increasing | High CPU | CPU saturation or new workload |
| Increasing | Increasing | High Hikari pending | DB connection pool or query/transaction |
| Increasing | Normal | Downstream 5xx increasing | Downstream failure or timeout mapping |
| Increasing | Normal | One pod failing | Instance-specific config/resource |
| 4xx increasing | Normal | No dependency errors | Client behavior, auth, or API contract |
| 5xx increasing after deploy | Increasing or normal | Unclear | Compare version, config, and traces |

These are directional hints, not automatic conclusions. Use traces/logs to verify whether a specific request failed in the controller, service, database, or downstream client.

## 11. Time-Windowed Error Rate Alerts

An alert based on a single short sample is overly sensitive to spikes. A simple rule:

```yaml
groups:
  - name: spring-boot-http-errors
    rules:
      - alert: HighHttp5xxRate
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
            /
            sum(rate(http_server_requests_seconds_count[5m]))
          ) > 0.05
          and
          sum(rate(http_server_requests_seconds_count[5m])) > 1
        for: 10m
        labels:
          severity: page
        annotations:
          summary: HTTP 5xx rate is elevated
          description: Check service error dashboard and recent traces.
```

This rule is illustrative only. Production requires adding service/environment labels, scope filters, a runbook URL, and SLO-based thresholds. If the metric has no series when the service has zero traffic, check the alerting system's no-data behavior.

For services with SLOs, alerting on error budget burn rate is often more useful than a fixed threshold. Burn-rate alerts combine multiple time windows to detect both fast, high-impact incidents and prolonged degradation. Use the same SLI definition as the SLO; do not use a different numerator between the dashboard and the alert.

## 12. Error Budget and SLO

If the availability SLO is 99.9%, the error budget allows at most 0.1% failed requests over the evaluation window. A 0.1% 5xx error rate is not necessarily safe at all times; if traffic is low or errors concentrate on a critical route, the impact can be significant.

For example:

\[
\text{Availability} = 1 - \text{Error rate}
\]

With a 0.2% error rate, availability by that definition is 99.8%. This is only valid when the numerator/denominator match the defined SLI exactly.

The dashboard should display:

- SLO target and current SLI.
- Error budget remaining.
- Burn rate across multiple windows.
- Total request volume.
- Critical routes/operations with separate error tracking if SLOs apply per route.

Do not treat all HTTP 4xx responses as availability failures if the SLO does not define them as service errors.

## 13. Cardinality and Labels

Error dashboards often group by status, method, route, service, environment, and instance. These labels must have a bounded or managed set of values:

- Use route templates, not raw paths.
- Do not use request IDs, trace IDs, user IDs, order IDs, or exception messages as metric labels.
- Do not include query strings in the uri label.
- Keep status as bounded codes/classes.
- Avoid labels containing dynamic hostnames or arbitrary tenant names if their count is large.

High cardinality increases Prometheus memory usage and query cost, and dashboards can slow down or exceed series limits. When you need to drill down by trace ID, pivot from metrics to exemplars/trace links or correlated logs.

## 14. Linking Dashboards to Logs and Traces

Metrics reveal trends and severity; logs/traces provide the details needed to find root cause.

Drilldown workflow:

1. Select the time window where the error rate increased.
2. Select the route/status/instance with prominent errors.
3. Open logs for the same time range, filtering by service, route, and error category.
4. If trace correlation/exemplars are available, open a representative error trace.
5. Inspect error spans, downstream latency, database calls, and messaging operations.
6. Cross-reference deployment markers, config changes, and dependency dashboards.

Do not turn trace IDs into metric labels. Use exemplars or links from log/trace context to jump from an aggregate metric to a specific execution.

## 15. Testing Error-Rate Dashboards and Alert Rules

Testing should verify both the SLI definition and the PromQL queries:

| Test | What to Prove |
| --- | --- |
| Numerator test | Only statuses defined as errors are counted |
| Denominator test | Total requests use the same scope/time window |
| 4xx/5xx split | Client and server errors are distinguished |
| Zero traffic test | Zero traffic is not misleadingly displayed as 0% error |
| Low traffic test | A single error does not trigger an out-of-policy alert |
| Probe exclusion test | Probes are excluded from both numerator and denominator if the dashboard covers user traffic |
| Route aggregation test | Route templates collapse IDs into a single series |
| Alert rule test | `for`/window/threshold behave according to SLO |
| Dashboard consistency | Panels and alerts use the same SLI definition |

Example logic test data:

```text
Window: 5 minutes
Total requests: 1000
2xx: 970
4xx: 20
5xx: 10

Server error rate = 10 / 1000 * 100 = 1%
Client error rate = 20 / 1000 * 100 = 2%
All non-2xx rate   = 30 / 1000 * 100 = 3%
```

Prometheus rule tests can use `promtool test rules` to verify alert expressions against series fixtures. Dashboard JSON/provisioning should also be version-controlled and reviewed alongside the SLI definition.

## 16. Common Pitfalls

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Abnormally high error rate | Numerator/denominator have different scopes | Compare filters and labels across both queries |
| Error rate always 0 | Wrong status label/meter name or 5xx not recorded | Inspect raw series and server instrumentation |
| Query returns no data | Service not scraped, label missing, or zero traffic | Check target health and series schema |
| Single error makes route 100% | Very small denominator | Display request volume and apply minimum traffic |
| Probes inflate denominator | Health traffic counted alongside user requests | Exclude probes from both numerator and denominator |
| 404 counted as server failure | Error policy merges all non-2xx | Separate 4xx/5xx per SLO |
| Route dashboard has too many series | Raw URI or ID in label | Use route templates and top-k |
| Flapping alerts | Short window, missing `for`/minimum volume | Use multi-window and baseline-aware thresholds |
| Alert does not fire when service is silent | No-data semantics not designed | Separate no-traffic alert from error-rate alert |
| Metric panel and alert diverge | Two places use different SLI definitions | Share common queries/recording rules |

## 17. Real-World Scenario: 5xx Spike After Deployment

**Hypothetical context:** After a deployment, orders-service sees its 5xx error rate climb from 0.05% to 4%. Request rate is unchanged, p95 latency increases, and errors are concentrated on route /api/orders/{id}.

Workflow:

1. **Confirm the SLI:** check numerator/denominator, exclude probe traffic, and compare the same time window before/after deployment.
2. **Isolate route/status:** inspect 500/502/503/504 and instance breakdown to see where errors are concentrated.
3. **Compare latency:** determine whether errors correlate with increased request duration.
4. **Open traces:** pick an error trace to inspect the exception/span and slow downstream dependencies.
5. **Cross-check logs:** filter by exception category and deployment version; do not log tokens or raw sensitive payloads.
6. **Check dependencies:** DB pool pending, query latency, messaging backlog, and downstream error rates.
7. **Decide rollback/fix:** based on impact, error budget, and verified root cause.
8. **Verify:** monitor error rate, request volume, latency, and alert state after remediation.

A good dashboard shortens the time from detection to isolation. It does not replace verification using traces, logs, and dependency data.

## 18. Self-Check Exercises

**Exercise 1.** Why do error rate numerator and denominator need the same scope?

*Hint:* If filters differ, the ratio no longer represents the failed portion of that specific total traffic.

**Exercise 2.** Should all 4xx responses be counted as server errors by default?

*Hint:* No. 4xx typically reflects client/input/auth semantics; track separately and apply SLO policy.

**Exercise 3.** A route has 1 request and 1 error. Why shouldn't you conclude the service has a 100% error rate?

*Hint:* The denominator is too small; check volume, service-level aggregate, and minimum traffic policy.

**Exercise 4.** Why must probe traffic exclusion be applied to both queries?

*Hint:* Excluding it only from the numerator or only from the denominator skews the ratio.

**Exercise 5.** Why are route templates better than raw URIs?

*Hint:* Route templates bound cardinality and group requests sharing the same endpoint semantics.

**Exercise 6.** When both 5xx and p95 latency increase together, where should you drill down?

*Hint:* Traces of error requests, logs by error category, DB/downstream latency, and saturation.

**Exercise 7.** Should an error rate dashboard and its alert use two different definitions?

*Hint:* No. They must use the same SLI definition to avoid a green dashboard while an alert is red, or vice versa.

**Exercise 8.** Why is zero traffic not synonymous with a 0% error rate?

*Hint:* Without a denominator, a ratio cannot be computed; no data/no traffic must be represented separately.

## 19. Key Takeaways

- Error rate is failed requests divided by total requests within the same scope/time window; also display request volume and error count.
- Separate 4xx and 5xx according to the API contract/SLO; do not assume all client errors are server availability failures.
- Use Micrometer's HTTP server request metrics and verify actual meter names/labels before writing PromQL.
- Compute numerator/denominator with identical filters; handle zero traffic and low traffic explicitly.
- Use route templates, status, method, service, and environment labels with controlled cardinality; do not put IDs or raw URIs in metrics.
- Dashboards should include error rate, request volume, status/route breakdown, latency, instance breakdown, and deployment/dependency context.
- Alerts need window, `for`, minimum traffic, and SLO/error-budget policies; panels and alerts must use the same SLI definition.
- Drill down from aggregate metrics to logs/traces using correlation/exemplars, then cross-reference DB, messaging, and downstream telemetry.
