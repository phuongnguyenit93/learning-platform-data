# Reading Successful, Failed, and Not-Permitted Call Counts

When operating a circuit breaker in Spring Cloud, three metric groups must be read together: **successful calls**, **failed calls**, and **not-permitted calls**. They describe three distinct outcomes of the protection mechanism: the supplier returned a normal result, the supplier threw an exception, or the breaker blocked the call before the supplier ran.

Do not collapse all three into a single error count. Failed call counts help evaluate dependency quality; not-permitted call counts show how many requests the breaker is blocking; successful call counts show how much work is proceeding normally. By cross-referencing these figures with `CLOSED`, `OPEN`, and `HALF_OPEN` states, latency, and HTTP client metrics, operations teams can distinguish a failing backend from a breaker actively protecting the system.

## 1. The Three Main Call Outcomes

With Resilience4j, a call routed through a circuit breaker typically ends in one of the following outcomes:

| Outcome | Meaning | Does Supplier Run? | Impact on Breaker Statistics |
|---|---|---|---|
| Success | Supplier completes normally and returns a result | Yes | Recorded as a successful call |
| Error/Failed | Supplier throws an exception classified as a failure | Yes | Recorded as a failed call |
| Not permitted | Breaker does not grant permission, usually because it is `OPEN` or out of probe permits | No | Recorded as a not-permitted call; not a fresh failure returned by the backend |
| Ignored | Exception is configured to be ignored | Yes | Excluded from success and failure rates; may be tracked separately |

The crucial distinction is that `not permitted` is not a failed HTTP call. When the breaker rejects a call, the supplier is not executed, so the backend does not receive that request via the supplier. Conversely, `failed` means the call was attempted and the supplier threw an exception.

A `success` call also only means the supplier completed in a way the breaker treats as successful. It does not prove business data validity on its own. For example, if an HTTP client is configured to convert HTTP 404 into a result object, the breaker may record a success even though the business resource was not found. Mapping HTTP statuses to exceptions or results must align with the failure classification policy.

## 2. Resilience4j Calls Metrics

When integrated with Micrometer, Resilience4j can export metrics for each circuit breaker. A commonly used meter for tracking call outcomes is `resilience4j.circuitbreaker.calls`. This metric categorizes calls by `kind`, typically including values such as `successful`, `failed`, `not_permitted`, and `ignored`, along with the breaker name.

| Metric Group | Information to Read | Operational Question |
|---|---|---|
| Calls `successful` | Count and execution duration of successful calls | How many calls are completing normally? Is latency increasing? |
| Calls `failed` | Count and execution duration of failed calls | How often is the dependency failing? When did errors start rising? |
| Calls `not_permitted` | Number of calls rejected by the breaker | How many requests is the breaker blocking? |
| Calls `ignored` | Number of exceptions configured to be ignored | Are certain error types occurring frequently without counting toward failure rate? |

The `calls` meter usually provides execution duration alongside call counts; Micrometer backends may represent this as a Timer and translate it into corresponding time series. Meter names, tags, and exporter formatting can vary across Resilience4j, Micrometer, and registry versions. In deployment, inspect the actual meters exposed by the application rather than assuming final Prometheus names are always identical.

In addition to `calls`, observe breaker state and sliding window statistics. Metrics are typically found under the `resilience4j.circuitbreaker` group, such as state, failure rate, slow call rate, and buffered call counts. Confirm exact names and tag sets on the metrics endpoint of the version you are using.

## 3. Success Does Not Mean the Entire User Request Succeeded

The circuit breaker `success` metric reflects the outcome of the protected supplier. If the supplier returns a normal value, the breaker may record a success even if that value represents a business condition such as data not found, order rejected, or zero inventory.

Example:

```java
InventoryView view = circuitBreaker.run(
        () -> inventoryClient.find(sku),
        error -> InventoryView.unavailable(sku)
);
```

If `inventoryClient.find(sku)` returns `InventoryView.notFound()` as a normal return value, the breaker may record a success. If the supplier throws an exception, the breaker records a failure according to configuration and the fallback may return `InventoryView.unavailable(sku)`. Returning a fallback value to the caller does not turn a failed supplier call into a success in breaker statistics.

Therefore, distinguish between:

- **Circuit breaker success:** the supplier ran and completed normally under the classification rules.
- **HTTP success:** the HTTP client received a status considered successful under client configuration.
- **Business success:** the business operation fulfilled the user's request properly.

These three concepts may correlate, but they are not identical. Dashboards need separate business metrics if operations teams want to track order creation success rates, nonexistent SKU counts, or rejected transactions.

## 4. Reading Failed Call Counts in Context

A call is recorded as a failure when the supplier throws an exception that the circuit breaker policy classifies as an error. Common causes include:

- Connect timeouts or read/response timeouts.
- Connection refused, DNS failures, or network routing errors.
- HTTP 5xx responses converted into exceptions by the HTTP client.
- Exceptions from the downstream service or response decoding errors.
- Programming bugs inside the supplier, if not classified or ignored.

Not every exception should contribute to the failure rate. Resilience4j supports `recordExceptions`, `ignoreExceptions`, and predicates for classifying outcomes. Ignored exceptions are excluded from both success and failure counts in the sliding window. Consequently, the `failed` count on a dashboard must be read alongside the error classification configuration.

Example configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.net.ConnectException
          - java.net.UnknownHostException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
```

The list above is illustrative. If the HTTP client wraps exceptions in `ResourceAccessException` or `WebClientRequestException`, configure the actual exception classes received by the breaker or use a predicate that inspects the cause chain. Misclassification can prevent infrastructure errors from counting toward the failure rate or allow business errors to open the breaker unnecessarily.

## 5. Reading Not-Permitted Call Counts

The `not_permitted` metric reflects how many times the breaker refused execution permission. The most common case is when the breaker is `OPEN`. Once the wait duration expires and the breaker transitions to `HALF_OPEN`, probe calls are capped by `permittedNumberOfCallsInHalfOpenState`; extra calls arriving after permits are exhausted can also be rejected.

An increase in not-permitted calls is not necessarily a bad sign for the breaker itself. It may show that the mechanism is doing its job: blocking requests to avoid piling load onto a failing or overly slow dependency.

Example:

- The inventory service begins timing out and the breaker transitions to `OPEN`.
- Over the next 10 seconds, 500 requests arrive at the gateway.
- The breaker rejects calls to inventory, and the gateway returns an unavailable fallback status.
- The `not_permitted` metric rises, while the gateway's HTTP client metrics do not rise accordingly because the supplier never executes.

Looking at `not_permitted` alone can make a dashboard look like errors are surging. When compared against breaker state and HTTP client metrics, however, it shows the system prevented 500 requests from hitting the backend. This measures the impact of the protection policy, not fresh errors returned by the backend.

## 6. Calculating Failure Rate and Choosing the Right Denominator

Statistically, a circuit breaker's failure rate is based on calls recorded as success or failure in the sliding window; ignored exceptions do not participate in the calculation. Not-permitted calls are also not supplier success/failure outcomes.

A common interpretation is:

\[
\text{Failure rate} = \frac{\text{Failed calls}}{\text{Successful calls} + \text{Failed calls}} \times 100\%
\]

Do not add `not_permitted` into the denominator when calculating the supplier failure rate. Including rejected requests in the denominator artificially lowers the backend error rate precisely when the breaker is blocking heavy traffic.

Example over an observation interval:

| Outcome | Count |
|---|---:|
| Successful | 700 |
| Failed | 100 |
| Not permitted | 400 |
| Ignored | 20 |

The failure rate based on supplier outcomes is \(100 / (700 + 100) = 12.5\%\). The 400 not-permitted calls are excluded from this denominator because the supplier did not run. The 20 ignored calls are also excluded from both success and failure counts.

If the operational question is "how many user requests failed to receive data from the dependency?", define a separate metric that can combine supplier errors with breaker rejections. Do not call that metric the circuit breaker failure rate if its denominator and meaning differ from the breaker's internal statistics.

## 7. Cross-Referencing Counters with Breaker State

Counters are far more meaningful when read alongside current state and state transition events.

| Observation | Possible Interpretation | What to Check Next |
|---|---|---|
| Failed rising, state remains `CLOSED` | Errors are occurring, but sample count or threshold has not been reached | `minimumNumberOfCalls`, failure rate, sliding window |
| Failed rises, then state transitions to `OPEN` | Breaker detected dependency failures exceeding threshold | Exception class, transition timestamp, fallback |
| Not permitted rising, state `OPEN` | Breaker is actively blocking calls | Time spent in `OPEN`, prior error/slow-call rate |
| Not permitted rising in `HALF_OPEN` | Probe permits are exhausted or concurrent arrivals exceed limit | `permittedNumberOfCallsInHalfOpenState`, probe outcomes |
| Successful rises after `HALF_OPEN` to `CLOSED` | Probe calls indicate the dependency may have recovered | Latency and error rate once normal traffic resumes |
| Successful rises while slow-call rate also rises | Dependency returns results, but slowly | Latency percentiles, queues, connection pools, thread pools |
| Failed is low, but fallback is high | Many calls may be rejected or fallback triggered at another layer | Not-permitted count, dedicated fallback counter, client errors |

The state metric is typically represented as a gauge tagged by breaker name and state. Depending on the version, states may be encoded via tags or numeric values. Use the actual meters and tags emitted by your exporter rather than assuming a fixed encoding.

## 8. Distinguishing CircuitBreaker Counters from HTTP Client Metrics

The circuit breaker measures outcomes of the protected supplier. The HTTP client measures actual network exchanges. These two data sources complement each other.

| Question | Appropriate Metric |
|---|---|
| How many times did the supplier succeed through the breaker? | Circuit breaker calls `successful` |
| How many times did the supplier throw exceptions? | Circuit breaker calls `failed` and exception classification |
| How many requests did the breaker block? | Circuit breaker calls `not_permitted` |
| How many HTTP requests reached the backend? | HTTP client/server request counters |
| How many HTTP 5xx responses did the backend return? | HTTP client response status or server HTTP metrics |
| How long did connection and response take? | HTTP client latency, connect time, and trace spans |
| How many times did users receive a fallback? | Application-specific fallback metric |

A `not_permitted` request does not initiate a new HTTP exchange through the protected supplier. Therefore, `not_permitted` rising while HTTP request count stays flat can be expected behavior. If `failed` rises alongside HTTP 5xx, investigate backend errors. If `failed` rises while the HTTP client records no response, the cause may be DNS, connect timeout, or an error prior to receiving a response.

## 9. How Retry Changes Call Count Interpretation

When combining Retry and CircuitBreaker, nesting order determines whether the breaker counts each attempt or the final outcome of multiple attempts.

- **Retry inside CircuitBreaker:** the breaker wraps the entire retry sequence. One supplier execution inside the breaker may generate multiple HTTP attempts, while the breaker typically records only the final outcome of the retry chain.
- **CircuitBreaker inside Retry:** each attempt may pass through the breaker individually. In this setup, the breaker can record multiple success, failure, or rejection events for a single business request.

For example, a business request attempts HTTP three times before succeeding. The HTTP client may record three request attempts, whereas the circuit breaker records only one success if the breaker wraps outside retry. Thus, total circuit breaker calls should not be expected to always equal total HTTP requests.

When reading dashboards, verify the decorator/aspect ordering and track network attempt counts as well. If Retry sits outside the breaker, an `OPEN` breaker can produce multiple rejections within the same request depending on the retry policy; repeatedly retrying while `OPEN` usually only increases `not_permitted` counts and caller-side overhead.

## 10. Setting Up Metrics Endpoints in Spring Boot

To inspect metrics via Actuator, the application needs the Actuator dependency and an appropriate Micrometer registry. For Prometheus, add the corresponding registry and expose metrics endpoints according to your application's security policy.

Example configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: order-service

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
```

Do not expose management or metrics endpoints on public networks without proper access controls. In production, restrict exposed endpoints, require authentication, or permit access only from internal monitoring systems.

You can use the Actuator metrics endpoint to discover available meters, for example:

```text
GET /actuator/metrics/resilience4j.circuitbreaker.calls
GET /actuator/metrics/resilience4j.circuitbreaker.calls?tag=name:inventory&tag=kind:successful
```

Meter names and tags may vary by version. Check `availableTags` in the metrics endpoint response to see supported tags and valid values. For Prometheus, metric names are transformed according to registry rules; inspect `/actuator/prometheus` before writing queries or dashboards.

## 11. Building a Per-Breaker Dashboard

A useful dashboard should display metrics per breaker ID, such as `inventory`, `pricing`, or `recommendation`:

1. **Call rate by kind:** growth rate of `successful`, `failed`, `not_permitted`, and `ignored`.
2. **Failure rate:** ratio of `failed` over `successful + failed` in the sliding window or corresponding metric.
3. **State:** current state and elapsed time since the most recent state transition.
4. **Latency:** execution time, plus p50/p95/p99 if histograms are available from the client or tracing.
5. **Fallback:** number of fallback invocations and type of fallback returned.
6. **Backend health:** HTTP status codes, connect/read timeouts, actual request count, and connection pool utilization.

Example dashboard layout:

| Panel | Recommended Chart | Purpose |
|---|---|---|
| Calls by kind | Rate by `successful`, `failed`, `not_permitted`, `ignored` | Clearly see successful, failed, and blocked calls |
| Breaker state | Current state or state transition timeline | Know whether the breaker is `CLOSED`, `OPEN`, or `HALF_OPEN` |
| Failure/slow rate | Gauge or time-series line | Compare against circuit-opening thresholds |
| Dependency latency | p50/p95/p99 and timeout count | Detect slow dependencies before errors spike |
| Fallback count | Counter by fallback type | Assess impact on user-facing functionality |
| Backend request status | HTTP 2xx/4xx/5xx and request rate | Confirm whether requests actually reach the backend |

Do not display only a combined `failed + not_permitted` sum. Those two figures lead to different actions: `failed` requires investigating the dependency and exceptions; `not_permitted` requires checking state, open duration, and fallback strategy.

## 12. Reading a Dashboard Timeline Example

Suppose the dashboard for the `inventory` breaker shows three phases:

| Phase | Successful | Failed | Not permitted | State |
|---|---:|---:|---:|---|
| Normal | 950 | 10 | 0 | `CLOSED` |
| Dependency degrading | 120 | 80 | 0 | `OPEN` after crossing threshold |
| Protecting | 0 | 0 | 600 | `OPEN` |

In the first phase, most calls succeed. When the dependency degrades, `failed` rises and the breaker opens once enough samples are collected. During the protection phase, the supplier does not execute so `failed` stops rising; instead, `not_permitted` climbs as new traffic is blocked.

Looking only at `failed`, an operator might think the incident is over because new failures dropped near zero. However, `not_permitted` and the `OPEN` state show that dependent functionality is still cut off. Verify backend recovery, wait for the breaker to transition to `HALF_OPEN`, and observe probe outcomes before concluding the system is back to normal.

## 13. Reading Metrics Per Replica

Resilience4j circuit breakers typically keep state and statistics inside each process. If the application runs across multiple pods, each pod maintains its own breaker instance and sliding window. As a result, service-wide aggregated metrics can mask differences among replicas.

Example:

| Replica | Successful | Failed | Not permitted | State |
|---|---:|---:|---:|---|
| Pod A | 0 | 0 | 300 | `OPEN` |
| Pod B | 180 | 20 | 0 | `CLOSED` |
| Pod C | 40 | 10 | 0 | `HALF_OPEN` |

Pod A has opened its circuit, Pod B is still accepting calls, and Pod C is probing. A dashboard showing only service-wide totals might indicate many successful calls while hiding that a subset of replicas is rejecting every call.

Keep instance/pod labels in the metrics system when detailed investigation is needed, alongside a service-level overview dashboard. Avoid putting request or user identifiers into metric labels. In autoscaling environments, pod labels can change frequently; choose aggregation strategies that avoid excessive cardinality.

When a pod restarts, local counters and sliding windows reset with the new process. Use `rate` or `increase` on counters rather than comparing raw values across restarts. Correlate pod startup timestamps with breaker state to avoid drawing wrong conclusions from counter resets.

## 14. Multi-Signal Alerting

Do not alert solely because `not_permitted` is greater than 0. Some rejections while a breaker is `OPEN` can represent proper protective behavior. Alerts should be tied to user impact, sustained duration, and dependency status.

Alert conditions worth considering:

- Failed rate exceeds threshold for a sustained window while the backend shows rising HTTP 5xx or timeouts.
- Breaker stays `OPEN` longer than operationally acceptable.
- `not_permitted` spikes alongside a high fallback rate and degraded user functionality.
- Slow call rate is high even while failure rate remains low, because a slow dependency can exhaust threads or connections.
- Some replicas are `OPEN` while others stay `CLOSED`, indicating the issue may be localized to a node or network path.
- Fallback count rises without corresponding state transition events, which may indicate errors at another layer or fallback invocations outside the circuit breaker.

When defining alerts, specify the evaluation window, threshold, impact level, and noise suppression strategy. Use state transition metrics or log events to explain why an alert fired; do not create individual alerts for every single supplier error if the system already aggregates by SLO.

## 15. Common Pitfalls When Interpreting Counters

| Misconception | Accurate Interpretation |
|---|---|
| Not permitted means the backend returned an error | The breaker blocked the supplier; the request may never have crossed the network |
| Failed equals HTTP 5xx count | Failed can include timeouts, DNS, connection errors, and other exceptions per record policy |
| Success means business success | Success only reflects that the supplier completed normally per breaker classification |
| Ignored counts as success | Ignored participates in neither success nor failure statistics |
| Not permitted should be added to failure rate | Not permitted is not a supplier outcome and does not belong in the failure rate denominator |
| Calls counter equals HTTP attempts | Retries, fallbacks, and decorator order can make the two numbers differ |
| Failed dropping to 0 means the backend recovered | The breaker may be `OPEN` and rejecting all new calls |
| Service-wide aggregated metrics are enough to investigate | State and sliding windows are typically local to each replica |

## 16. Incident Metrics Investigation Workflow

When a dashboard signals an anomaly on a circuit breaker, follow this sequence:

1. Select the exact breaker ID and inspect current state across individual replicas.
2. Read the growth rates of `successful`, `failed`, `not_permitted`, and `ignored` over the same time window.
3. Compute failure rate from `successful` and `failed` per breaker definition; exclude `not_permitted` and `ignored` from the denominator.
4. Correlate `failed` with exception classes, HTTP statuses, connect/read timeouts, and dependency latency.
5. If `not_permitted` is rising, check when the breaker transitioned to `OPEN`, its wait duration, and `HALF_OPEN` permit count.
6. Check the fallback counter to determine how often users are receiving degraded responses.
7. Compare circuit breaker calls with HTTP client request metrics to see whether the supplier is actually making network attempts.
8. Check retry/decorator order to explain differences between logical call counts and HTTP attempts.
9. Inspect individual pods and restart timestamps before drawing conclusions about the entire service.
10. Confirm recovery via successful probe calls, state returning to `CLOSED`, and stable latency.

Reading successful, failed, and not-permitted calls separately decouples dependency behavior from circuit breaker protection decisions. `successful` and `failed` describe supplier outcomes; `not_permitted` shows calls blocked by the breaker; `ignored` reflects exceptions excluded from failure rate. Combining these counters with state, latency, fallback counts, HTTP client metrics, and per-replica data enables operations teams to pinpoint where action is needed and evaluate whether the circuit breaker is protecting the system effectively.
