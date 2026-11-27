# Alerting on Error Rate in Spring Boot

Error rate indicates the proportion of requests or operations that fail over a period of time. It is a critical signal for detecting post-deployment regressions, dependency outages, configuration errors, and incidents degrading user experience. However, a percentage alone is not enough to decide whether to wake up an on-call engineer: a 100% error rate on a single request in one minute may just be very low traffic, whereas a 1% error rate across tens of thousands of requests per minute can impact many users.

**Alerting on error rate** means alerting based on the ratio of failed operations to total eligible operations over a time window. For an alert to be meaningful, you must clearly define the numerator, denominator, traffic scope, error classification, minimum traffic, and impact according to the SLO. In Spring Boot, Micrometer records request metrics; Prometheus or an equivalent system collects and evaluates time series; Alertmanager or an alerting platform routes notifications to the responsible team.

This lesson belongs to the **Dashboard and Alert** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides you through setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments. This lesson focuses on defining error-rate SLIs, writing queries, choosing thresholds, and building actionable alerts.

## Learning Objectives

1. Define error rate with a consistent numerator and denominator.
2. Distinguish HTTP server errors, business failures, and dependency errors.
3. Build an error-rate SLI from Micrometer metrics.
4. Write PromQL to calculate error ratios over time windows.
5. Handle low traffic, counter resets, and missing data.
6. Choose alert thresholds based on SLOs and impact.
7. Apply multi-window, multi-burn-rate alerts.
8. Reduce false positives using minimum traffic and proper grouping.
9. Route alerts by severity, service, and ownership.
10. Test alert rules and use logs/traces for investigation.

## 1. What Is Error Rate?

Error rate is the proportion of operations classified as failed out of the total observed operations:

```text
error_rate = failed_operations / total_operations

error_rate_percent = error_rate * 100
```

For example, if there are 10,000 HTTP requests in 5 minutes and 250 requests are classified as errors:

```text
error_rate = 250 / 10000 = 0.025 = 2.5%
```

The formula is only meaningful when the numerator is a subset of the denominator and both use the same scope, label dimensions, and time window.

### 1.1. Choosing the measured operation

For an HTTP API, you can use completed server requests. For a message consumer, you can use message processing attempts or business messages processed. For scheduled tasks, you can use execution failures over total executions. Do not mix operations with different semantics into the same error-rate SLI.

### 1.2. HTTP status is not all of business errors

HTTP 5xx are usually server-side failures; 4xx usually represent invalid requests or rejections under the contract. However, SLI classification depends on the product:
- 5xx are typically counted as service errors.
- Client-caused 4xx may be excluded from the availability SLI.
- 429 may indicate overload/throttling and require separate tracking.
- An API might return HTTP 200 while the payload indicates a failed business operation; if users care about that outcome, a separate business metric is needed.

Do not treat every 4xx status as a service outage, nor ignore 429s if users cannot complete their workload.

## 2. Defining the Numerator and Denominator

Before writing alerts, write down the SLI definition clearly:

| Component | Example for HTTP API |
|---|---|
| Scope | One service or route class |
| Denominator | Total valid completed requests |
| Numerator | Requests belonging to the error group per policy |
| Window | 5 minutes, 1 hour, or 6 hours |
| Exclusions | Health probes, static assets, or non-SLO routes |
| Grouping | service, environment, route template |
| Owner | Team responsible for the service |

Numerator and denominator must share the same filters. If the denominator excludes health checks while the numerator still includes health-check failures, the ratio will be wrong.

### 2.1. Route templates, not raw paths

Use route templates such as `/orders/{id}` or a stable route label. Raw paths containing order IDs can create high cardinality and split alerts into thousands of series. Route templates also help identify which endpoint has errors without leaking identifiers.

### 2.2. Intentional error classification

Separate errors into useful categories:
- server error;
- timeout;
- throttling;
- dependency failure;
- validation/client error;
- business rejection.

Do not add exception messages or raw SQL/URLs as labels. Use a small, standardized set of error categories.

## 3. Metrics in Spring Boot

Spring Boot Actuator and Micrometer can record HTTP server request metrics when appropriate instrumentation is enabled. A common meter is `http.server.requests`; the registry transforms the name according to its convention—for example, Prometheus typically uses a form like `http_server_requests_seconds_count` for the timer count.

Actual names and tags depend on Spring Boot, Micrometer, web stack, and registry versions. Before writing rules, inspect `/actuator/metrics`, `/actuator/prometheus`, or the application's scrape output.

Commonly useful dimensions:
- method;
- uri/route template;
- status;
- outcome;
- exception;
- service/environment via resource or scrape labels.

Do not assume every version provides the same tag keys. Inspect actual series and avoid putting user IDs, request IDs, trace IDs, raw URLs, or exception messages into metric labels.

### 3.1. Counters and timers

A Micrometer Timer typically provides count and total time; the Prometheus registry may expose the timer count as a counter. Error-rate queries typically apply `rate()` to the count counter, rather than using total duration to compute an error ratio.

### 3.2. Counter resets

When a process restarts, counters may reset to 0. Prometheus `rate()` handles counter resets when calculating the rate of increase over a range vector. Do not manually subtract two instant samples and divide without handling resets and scrape gaps.

## 4. PromQL to Calculate Error Rate

Assume Prometheus scrapes `http_server_requests_seconds_count` with `status` and `service` labels. Example query:

```promql
sum(rate(http_server_requests_seconds_count{
  service="checkout",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  service="checkout"
}[5m]))
```

The result is the ratio of 5xx requests to total requests over 5 minutes. To express as a percentage, multiply by 100.

### 4.1. Avoiding division by zero

When there is no traffic, the denominator is 0 or no series exist. Do not unconditionally treat NaN/absent as a 0 error rate. Alerts should require sufficient traffic volume or use a separate no-traffic alert if the service is expected to have continuous traffic.

### 4.2. By route

You can group by route template:

```promql
sum by (uri) (
  rate(http_server_requests_seconds_count{
    service="checkout",
    status=~"5.."
  }[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count{
    service="checkout"
  }[5m])
)
```

Use low-cardinality route labels. For dashboards, group by service/route; for paging, usually rely on the aggregate service SLI to avoid low-traffic routes generating many small alerts.

### 4.3. Choosing status filters

If the SLI only counts 5xx, `status=~"5.."` is an example filter. If 429 belongs to the error policy, include status 429 or use a normalized outcome/error category. If 4xx client errors are outside the SLO, exclude them from the numerator.

## 5. Low Traffic and Minimum Request Volume

A ratio over a small denominator fluctuates easily. For instance, one failed request out of two gives a 50% error rate, yet the absolute impact may be negligible. Combine ratios with request volume.

Example traffic condition:

```promql
sum(rate(http_server_requests_seconds_count{
  service="checkout"
}[5m])) * 300 > 100
```

This illustrative expression requires more than 100 requests in the 5-minute window. Choose the minimum volume based on traffic profile and risk; do not copy the example threshold for every service.

### 5.1. Zero traffic can also be an incident

For a service that should receive continuous traffic, a request rate of 0 may indicate a routing/DNS/gateway failure. That is a separate availability/traffic alert—do not force error rate to 100% when there are no requests.

### 5.2. Traffic bursts

During sudden traffic surges, error rate may fluctuate due to rollouts, autoscaling, or dependency warm-up. Use a sufficiently long window and multi-window evaluation to distinguish very short spikes from sustained burn.

## 6. SLO-Based Alert Thresholds

If the availability SLO is 99.9% over 30 days, the corresponding error budget allows 0.1% of requests to fail during the period. Alert thresholds should reflect how fast the budget is consumed (burn rate), not just an arbitrary percentage.

```text
error_budget_fraction = 1 - availability_slo
burn_rate = observed_error_rate / error_budget_fraction
```

For example, with a 99.9% SLO, `error_budget_fraction = 0.001`. If the current error rate is 1%, `burn_rate = 10` times the average allowed rate.

### 6.1. Error budget and user impact

The same error rate can have different impacts depending on traffic, endpoint, and user journey. A failing checkout route may be more severe than an optional route. Define SLIs around user workloads and agreed SLOs.

### 6.2. Warning and paging

- Warning: errors are elevated, but budget is not burning excessively fast or impact remains limited.
- Page: burn rate is high, sustained, and likely to exhaust the error budget before the SLO period ends.

Severity should tie to specific actions: warnings create tickets/notify the team; pages wake up on-call.

## 7. Multi-Window, Multi-Burn-Rate Alerts

A long window reflects trends but detects slowly; a short window reacts quickly but is sensitive to noise. Multi-window alerts combine both so paging occurs only when burn rate is high in both short and long windows.

Example burn-rate query for a 99.9% SLO:

```promql
(
  sum(rate(http_server_requests_seconds_count{service="checkout",status=~"5.."}[5m]))
  /
  sum(rate(http_server_requests_seconds_count{service="checkout"}[5m]))
) > 14.4
and
(
  sum(rate(http_server_requests_seconds_count{service="checkout",status=~"5.."}[1h]))
  /
  sum(rate(http_server_requests_seconds_count{service="checkout"}[1h]))
) > 14.4
```

The example uses a burn-rate threshold of 14.4 times the error budget and two windows (5 minutes and 1 hour). Production rules must add minimum traffic, handle zero denominators, and verify windows suited to the SLO period. Other window pairs can be chosen based on desired detection time.

### 7.1. Burn rate is not error percentage

Burn rate is error rate divided by error budget fraction. For a 99.9% SLO, a burn rate of 14.4 corresponds to a 1.44% error rate (`14.4 × 0.1%`). Read units carefully to avoid confusing thresholds.

### 7.2. Long-term alerts

Use longer windows such as 6 hours or 24 hours to catch slow but steady budget consumption. These alerts typically carry a lower severity than fast pages, depending on on-call policy.

## 8. Illustrative Prometheus Alert Rule

Simple example rule:

```yaml
groups:
  - name: checkout-error-rate
    rules:
      - alert: CheckoutHighErrorRate
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              service="checkout",
              status=~"5.."
            }[5m]))
            /
            sum(rate(http_server_requests_seconds_count{
              service="checkout"
            }[5m]))
          ) > 0.02
        for: 10m
        labels:
          severity: warning
          team: commerce
        annotations:
          summary: "Checkout API error rate is elevated"
          description: "5xx ratio exceeded 2% for 10 minutes."
```

This rule illustrates the structure of a Prometheus alerting rule; you must add guards for low traffic/zero denominators and adjust service labels to match your scrape config. A 2% threshold is not a default suited to every system.

### 8.1. `for` duration

`for: 10m` requires the expression to remain continuously true for 10 minutes before the alert fires. It reduces short-lived noise but delays detection. For burn-rate pages, short/long combined windows are commonly used instead of merely extending `for`.

### 8.2. Labels and annotations

Labels are used for grouping/routing: severity, team, service, environment. Annotations describe the issue and link to runbooks/dashboards. Do not attach request IDs, trace IDs, or raw exceptions to alert labels; they create distinct alert fingerprints and cause alert floods.

## 9. Error Rate Dashboard

The dashboard should display side by side:
- Error rate (%) by service and route class.
- Failed requests/sec and total requests/sec.
- 4xx, 5xx, and 429 broken out separately if useful.
- Latency p50/p95/p99.
- Traffic volume.
- Deployment markers.
- Dependency errors/latency.
- SLO/error budget burn rate.

### 9.1. Ratio and absolute volume

High error rate with low volume and high error count with high volume are two different situations. Display both the percentage and failed requests per second so on-call can assess the scale of impact.

### 9.2. Grouping

Overview dashboard by service; drill-down by route template, method, status, and dependency. Do not group by user/session/request ID.

### 9.3. Correlating deployments

Add deployment annotations or release markers to the dashboard. If error rate climbs right after a rollout, compare versions/replicas, error traces, and configuration changes. Do not assume deployment is the cause by default; rely on evidence.

## 10. Error Classification and Ownership

An alert must answer who handles it and which layer the error belongs to. Standardize error categories and service ownership. For example:
- application: unhandled exception or bug;
- dependency: database/remote API failure;
- capacity: saturation, throttling, or queue overload;
- client: malformed/unauthorized request;
- unknown: uncategorized.

If high error rate stems from a shared dependency, alerts from multiple services may fire simultaneously. Grouping by dependency/impact and linking runbooks prevents multiple duplicate pages for the same incident.

## 11. Testing Alert Rules

Alert rules must be tested before going to production. With Prometheus, use `promtool test rules` or an equivalent test framework.

Scenarios should include:
1. Zero errors, normal traffic.
2. Error rate continuously exceeding threshold.
3. Error spike shorter than `for`/window.
4. Low traffic with a few errors.
5. Zero traffic.
6. Counter reset after restart.
7. One route failing while overall service remains within SLO.
8. Elevated 429s due to throttling.
9. Missing series/scrape target down.
10. Multi-window burn-rate firing only when both windows meet conditions.

### 11.1. Synthetic time series

Create test samples for success/failure counters across multiple timestamps. Verify alert states (`pending`/`firing`/`inactive`) as well as labels/annotations. Do not evaluate queries at a single instant only, since `for` duration requires history.

### 11.2. Testing routing

Use an Alertmanager test receiver or a mock notification sink to verify grouping, inhibition, repeat intervals, and receivers. Do not send test pages to production on-call.

## 12. Diagnosing Error Rate Alerts

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Alert firing while users see no errors | 4xx/client errors counted in numerator | Check SLI classification |
| 100% error rate at low traffic | Very small denominator | Minimum volume and absolute count |
| Error rate is NaN | Zero denominator/missing series | Query guard and no-traffic alert |
| Alert not firing despite rising 5xx | Wrong labels/status tags or query | Inspect raw series and PromQL |
| Alert fires after restart | Counter reset or scrape gap | Use `rate()` and check target |
| One route generates many alerts | Raw paths/high-cardinality labels | Route templates and alert grouping |
| Alert fires late | Window/`for` too long | Multi-window and detection budget |
| Flapping alert | Short window, low traffic, or sensitive threshold | Volume guard and sustained condition |
| Dashboard and alert numbers differ | Different filters/windows/aggregations | Align SLI definitions |
| Multiple services page at once | Shared dependency outage | Group by dependency/incident |
| 429s go undetected | Policy omits throttling from error category | Separate SLI for throttling |
| Alert has no owner | Missing team/service labels | Ownership metadata and routing |

### Investigation workflow

1. Confirm the alert expression, window, labels, and severity.
2. Check raw numerator/denominator series.
3. Verify status/outcome classification.
4. Check traffic volume and scrape gaps.
5. View error rate alongside failed requests/sec and latency.
6. Compare routes, service versions, and deployment markers.
7. Open representative error traces to find the dependency/exception.
8. Cross-reference logs by trace ID; do not put trace ID into metric labels.
9. Determine whether errors concentrate in app, dependency, capacity, or client.
10. Record the incident timeline and tune the rule based on evidence.

## 13. Anti-Patterns to Avoid

| Anti-pattern | Consequence | Better Approach |
|---|---|---|
| Alerting on a single error | Noise at low traffic | Minimum volume and sustained window |
| Treating all 4xx as server failures | Inflated error rate | SLI classification |
| Percentage only | Hides absolute impact | Show request volume/error count |
| Dividing by zero/missing series | NaN or false clear | Guards and separate no-traffic alerts |
| Using raw URLs as labels | Cardinality and alert floods | Route templates |
| Using exception messages as labels | Series/alert fingerprint explosion | Error categories |
| Thresholds unrelated to SLO | Too many or too late pages | Burn-rate policy |
| Short window only | False positives | Multi-window |
| Overly long `for` for every page | Late detection | Window matched to detection objective |
| Grouping unrelated services with different owners | Unclear who responds | Service/team routing |
| Using trace sampling as error counter | Sampled traces don't represent total requests | Unsampled metric counters |
| Skipping rule tests | Broken queries/routing in production | `promtool` and mock receivers |

## 14. Production Checklist

1. **SLI:** are numerator/denominator defined and approved?
2. **Scope:** is service/route/workload clearly specified?
3. **Classification:** are 4xx, 5xx, 429, and business failures classified?
4. **Metrics:** are counter/timer labels stable and low-cardinality?
5. **Query:** does `rate()` use the right counters and identical filters?
6. **Traffic:** are minimum volume and no-traffic behavior handled?
7. **SLO:** are thresholds/burn rates tied to the error budget?
8. **Windows:** do short/long windows match the detection objective?
9. **Severity:** do warning/page have clear actions and owners?
10. **Routing:** are service/team/environment labels accurate?
11. **Annotations:** are dashboard, runbook, and impact descriptions included?
12. **Dashboard:** does it display rate, absolute count, traffic, and latency?
13. **Correlation:** is deployment/dependency context available?
14. **Cardinality:** no IDs, raw paths, or exception messages?
15. **Tests:** tested low traffic, resets, missing series, spikes, and sustained errors?
16. **Routing tests:** verified with mock receivers without paging production?
17. **Runbook:** does on-call have steps to check numerator/denominator and traces?
18. **Review:** are SLIs/rules reviewed when API contracts or SLOs change?

## 15. Self-Assessment Questions

**Question 1.** How is error rate calculated?

**Hint:** Number of failed operations divided by total eligible operations within the same scope and time window.

**Question 2.** Why must numerator and denominator be defined before writing queries?

**Hint:** Both sets must share the same scope/filters; if they differ, the ratio will not accurately reflect the SLI.

**Question 3.** Should all HTTP 4xx responses be counted as service errors?

**Hint:** Not by default. Classify according to the contract; client errors are typically separated from the availability SLI, while 429 needs its own policy.

**Question 4.** Why might a 50% error rate across two requests not warrant a page?

**Hint:** Low volume; minimum traffic and absolute impact are needed to prevent false positives.

**Question 5.** How does Prometheus `rate()` help during counter resets?

**Hint:** It estimates the rate of increase and accounts for counter resets within the range vector.

**Question 6.** What is burn rate?

**Hint:** Observed error rate divided by the allowed error budget fraction under the SLO.

**Question 7.** What is the benefit of multi-window alerts?

**Hint:** Combines the fast reaction of a short window with the stability of a long window.

**Question 8.** Why shouldn't raw paths or trace IDs be used as alert labels?

**Hint:** They create high cardinality/fingerprints, fragmenting alerts and making grouping difficult.

**Question 9.** What else should an error rate dashboard display besides percentages?

**Hint:** Total traffic, failed requests/sec, latency, route breakdown, and deployment markers.

**Question 10.** When an alert fires, where should the investigation begin?

**Hint:** Check numerator/denominator, volume, classification, route/version, then open representative traces/logs.

## Conclusion

**Alerting on error rate is only reliable when the SLI has a consistently defined numerator, denominator, and traffic scope.** In Spring Boot, use Micrometer request metrics to record request outcomes, Prometheus `rate()` to compute ratios, and alert rules to evaluate conditions over time windows. Combine minimum traffic, absolute error volume, SLO burn rates, and multi-window evaluation to minimize false positives while still detecting incidents quickly. Dashboards should display error rate alongside traffic, latency, and deployment markers; alerts need owners, severity, runbooks, and routing tests. When an alert fires, inspect raw series and then use logs/traces to pinpoint root cause across application, dependency, or capacity.
