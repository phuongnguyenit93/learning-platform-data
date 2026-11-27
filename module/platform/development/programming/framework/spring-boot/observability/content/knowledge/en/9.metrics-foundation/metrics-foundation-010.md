# Metric Names

> **Chapter:** Metrics Foundation  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — observing Spring Boot applications with Micrometer Observation, metrics, logs, and distributed tracing; using consistent metric names to investigate errors, latency, and application behavior alongside context propagation, tags/cardinality, exporters, and sampling.

## Learning Objectives

After this lesson, you will be able to:

- Explain what a **metric name** identifies and why names must remain stable over time.
- Distinguish **metric name**, **tags/labels**, **meter type**, **base unit**, **description**, and **observation name**.
- Name counters, gauges, timers, and distribution summaries following Micrometer conventions in Spring Boot; understand why names in a Prometheus backend may differ from names in Java.
- Identify names that cause high cardinality, unit ambiguity, or broken dashboards and alerts.
- Create and inspect real meters using `MeterRegistry`, Spring Boot Actuator, and an appropriate exporter.
- Correlate metrics with logs/traces using appropriate context without turning request IDs, trace IDs, or tenant IDs into part of the metric name.

## 1. Why Do Metric Names Matter?

Suppose an e-commerce platform has two Spring Boot services. The first records order creations as `orders.created`; the second uses `orderCreateCount`. A newer release records `order_created_success_count_v2`. All three names might measure the same behavior, yet cannot be automatically merged into one consistent time series.

When operations asks "did the order failure rate increase after this release?", the problem is not merely **having data**. Measurements must share a **naming and semantic contract** so queries, alerts, and comparisons remain valid across versions.

A **metric name** is the logical name of a measurement. In Micrometer, the name combines with the meter type and tag set to describe the measurement being collected. A good name is usually a **short, stable, meaningful, and consistent** string across services.

Examples:

```text
orders.created
checkout.duration
payment.requests
payment.queue.depth
inventory.reserved.items
```

These names describe the **type of phenomenon**, rather than an individual invocation.

A useful design question: **"After 6 months and 20 deployments, will a metric with this same name still have the exact same definition?"** If the answer is uncertain, clarify the semantics before putting that name into dashboards and alerts.

## 2. A Metric Name Is Not the Full Identity of a Time Series

An important point: **a metric name does not represent a single time series** if the metric has labels/tags.

Example logical meter:

```text
name = http.server.requests
type = TIMER
tags = {
  method: "POST",
  uri: "/orders",
  status: "500"
}
```

Under the same metric name, other combinations can exist:

```text
http.server.requests {method=GET,  uri=/orders, status=200}
http.server.requests {method=POST, uri=/orders, status=200}
http.server.requests {method=POST, uri=/orders, status=500}
```

Each tag combination can contribute distinct time series in the backend. For timers/histograms, one logical meter can be exported as **multiple numeric series** such as count, sum, and buckets. Therefore, naming must go hand in hand with choosing **meter type, unit, and tag cardinality**.

| Component | Used to Express | Example |
| --- | --- | --- |
| **Metric name** | Phenomenon being measured | `checkout.duration` |
| **Meter type** | How values are collected | `Timer`, `Counter`, `Gauge`, `DistributionSummary` |
| **Tags/labels** | Bounded grouping dimensions | `channel=web`, `outcome=success` |
| **Base unit** | Measurement unit, if applicable | `bytes`, `requests`, `items` |
| **Description** | Explains the measurement to readers | "Time spent processing checkout operation" |
| **Recorded value** | Observed measurement | `0.42 s` or `120 requests` |

In Micrometer, `Meter.Id` holds fields such as name, tags, base unit, description, and type. Across different registries, a **naming convention** may transform names/tags/units before export.

Do not confuse the **name of a measurement** with the **identifier of a request**. Values such as `orderId`, `traceId`, or `userId` do not belong as suffixes on metric names and are generally unsuitable as metric labels either.

## 3. How to Name Metrics in Micrometer

Micrometer encourages dot-separated names composed of logical segments:

```text
<domain>.<operation>.<measurement>
```

This is an **illustrative design pattern**, not a mandatory API syntax. Pick just enough detail to express a concrete measurement clearly.

Examples:

| Need | Suggested Logical Name | Meter Type | Reason |
| --- | --- | --- | --- |
| Count successfully created orders | `orders.created` | Counter | Cumulative event; no need for `success` in name if definition only counts created orders. |
| Measure checkout execution duration | `checkout.duration` | Timer | Needs count and total time; can show histograms/percentiles if configured. |
| Measure tasks waiting to be processed | `payment.queue.depth` | Gauge | Current value that can go up or down. |
| Count partner call attempts | `payment.requests` | Counter | Can slice by normalized `outcome` or `provider` tags. |
| Measure payload sizes | `message.payload.size` | DistributionSummary | Size distribution across individual messages. |
| Count retries | `payment.retries` | Counter | Each retry is one incrementing event. |

Design principles:

1. **Names describe the subject and quantity:** `payment.queue.depth` is clearer than `data1` or `processMetric`.
2. **Never embed dynamic values:** `orders.created.123456` makes every order spawn a new metric name.
3. **Never embed dimensions that belong in tags:** instead of `checkout.duration.mobile` and `checkout.duration.web`, prefer `checkout.duration` with `channel=mobile|web`.
4. **Avoid conflicting conventions:** never reuse the same metric name for measurements with different meanings or data types.
5. **Follow system-wide conventions:** stay consistent with `orders` vs. `order`, `latency` vs. `duration`; if your organization or framework already sets a standard, follow it.

Naming is only half the contract. Each metric should also document **when it is recorded**, **what its values mean**, **its unit**, **allowed tags**, and **what counts as error vs. success**.

### 3.1. How Stable Should a Metric Name Be?

Keep the same name if the measurement keeps the same semantics. For instance, payment calls are counted at call start: every attempt increments the counter whether it succeeds or fails. Then `payment.requests` with a bounded `outcome` tag works well for slicing.

If you switch from "counting attempts" to "counting payments successfully posted to the ledger," **the definition changed**. Do not silently keep the old name, because pre- and post-change time series will no longer be comparable. Create a new metric or execute a documented migration plan.

## 4. Name, Meter Type, and Unit Must Align

Meter types do not just differ in API; they produce data with different semantics. Do not label a request-count Gauge as "latency," or name a fluctuating value `requests.total`.

| Meter Type | Meaning | Java Example | Interpretation |
| --- | --- | --- | --- |
| **Counter** | Cumulative value, typically increasing on events | `Counter.builder("orders.created")` | Number of order-creation events recorded. |
| **Timer** | Operation count and duration | `Timer.builder("checkout.duration")` | Measures duration; registry may export count, sum, and histograms. |
| **Gauge** | Current value at read time | `Gauge.builder("payment.queue.depth", ...)` | Current queue depth. |
| **DistributionSummary** | Distribution of non-time values | `DistributionSummary.builder("message.payload.size")` | Message sizes, items per batch, etc. |
| **LongTaskTimer** | Tracks long-running active tasks | `LongTaskTimer.builder("batch.running.duration")` | Active tasks count and their elapsed time. |

**Notes on units:**

- For `Timer`, pass `Duration` or a `TimeUnit` via the proper API. Registries typically normalize time to the backend's preferred unit, such as seconds in Prometheus.
- For `DistributionSummary` or `Gauge`, declare units clearly; `baseUnit("bytes")` or another fitting unit helps readers interpret values.
- Do not append `.milliseconds` to a timer name assuming the backend exports milliseconds. If the backend displays seconds, such a name misleads readers.
- Names and units should be clear enough that dashboards never convert units twice.

Examples of coherent metric definitions:

```text
message.payload.size     type=DistributionSummary, unit=bytes
checkout.duration        type=Timer, unit=time
orders.created           type=Counter, unit=orders/events (by definition)
```

Appending unit suffixes or counter suffixes is the job of the **registry naming convention**. Do not bake exporter-generated suffixes into logical names when designing metric names.

## 5. From Micrometer Names to Prometheus Names

Spring Boot commonly uses Micrometer Metrics and can export to Prometheus. Micrometer uses dot-separated logical names, while Prometheus metric names use underscores and suffixes reflecting measurement type.

These examples are **illustrative**; verify actual output because Micrometer/Prometheus registry versions, distribution configs, and naming conventions can alter final names.

| Name in Java/Micrometer | Type | Possible Prometheus Output |
| --- | --- | --- |
| `orders.created` | Counter | `orders_created_total` |
| `payment.queue.depth` | Gauge | `payment_queue_depth` |
| `checkout.duration` | Timer | `checkout_duration_seconds_count`, `checkout_duration_seconds_sum` |
| `checkout.duration` with histogram enabled | Timer | May include `checkout_duration_seconds_bucket` alongside count/sum |
| `message.payload.size`, unit bytes | DistributionSummary | Corresponding count/sum series, optionally buckets per config |

Three lessons follow from this:

1. **Logical names differ from physical exported names.** In code, write `checkout.duration`; in PromQL, query the actual series exported by the registry, such as `checkout_duration_seconds_count`.
2. **Suffixes carry meaning:** `_count` indicates observation count in a timer/summary; `_sum` is total value; `_bucket` relates to histograms; counters usually end with `_total` per Prometheus convention.
3. **Never assume histograms exist automatically:** getting buckets for quantile estimation may require distribution/statistics settings or `publishPercentileHistogram()`, plus backend support.

Example PromQL query when matching series exist:

```promql
sum(rate(orders_created_total[5m]))
```

This is the counter's average growth rate over 5 minutes; it is **not** the total orders since the beginning of time. With bounded tags, you can group:

```promql
sum by (channel) (rate(orders_created_total[5m]))
```

For durations with `_sum` and `_count`, an estimate of **mean duration** over the query window is:

```promql
sum(rate(checkout_duration_seconds_sum[5m]))
/
sum(rate(checkout_duration_seconds_count[5m]))
```

The result is typically in **seconds per measurement**. To compute p95 from a histogram, matching buckets and `histogram_quantile()` are required; without `_bucket`, this histogram p95 formula cannot work.

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(checkout_duration_seconds_bucket[5m]))
)
```

This formula illustrates **classic histogram buckets**; native histograms or different distribution configs may require different queries. Verify series names and backend versions before deploying to production.

## 6. Creating Metrics with `MeterRegistry` in Spring Boot

The example below creates a counter and a timer using stable logical names. External `channel` values are normalized to `web`, `mobile`, or `other` to prevent cardinality growth from arbitrary strings.

```java
package example.metrics;

import java.util.function.Supplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {
    private final MeterRegistry registry;

    public CheckoutMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void orderCreated(String channel) {
        Counter.builder("orders.created")
                .description("Number of successfully created orders")
                .tag("channel", normalizeChannel(channel))
                .register(registry)
                .increment();
    }

    public <T> T measureCheckout(String channel, Supplier<T> operation) {
        return Timer.builder("checkout.duration")
                .description("Duration of a checkout operation")
                .tag("channel", normalizeChannel(channel))
                .register(registry)
                .record(operation);
    }

    private static String normalizeChannel(String value) {
        if ("web".equals(value) || "mobile".equals(value)) {
            return value;
        }
        return "other";
    }
}
```

Usage in a business service (`checkoutService` and `request` are illustrative variables):

```java
Order order = checkoutMetrics.measureCheckout(
        request.channel(),
        () -> checkoutService.createOrder(request)
);
checkoutMetrics.orderCreated(request.channel());
```

In this example, `orders.created` increments **only after order creation succeeds and returns**. If the system uses transactions that can roll back, decide precisely when order creation counts as complete; incrementing before a rollback makes the metric diverge from its definition.

Key behaviors:

- `MeterRegistry` manages meters; re-registering with the **same name and compatible tags** returns the existing meter, avoiding creating a new meter for every request sharing the same tags.
- Granular slicing comes from **tags**, not per-channel metric names.
- `Timer.record(operation)` measures the **synchronous** execution of the supplier; if the supplier returns an unfinished future, duration excludes the subsequent async work.
- `Counter` is for cumulative event counts; never use a counter for orders **currently waiting** because that value can drop and belongs in a gauge.
- A `Timer` also records the count of timed invocations. Avoid creating a redundant counter meaning "number of measured checkouts" when the timer's count already answers it.

**Never add `orderId`, `traceId`, `userId`, or URLs with specific IDs to metric names or tags** just to look up individual requests. Use logs/traces under appropriate data governance.

### 6.1. Conflicting Meter Types or Tags

Suppose initial code registers a `Counter` named `orders.created`, while another component registers a `Timer` with the same name and tags. That creates a semantic conflict in the registry/exporter; depending on implementation, registration may be rejected or fail.

Another issue: two code paths emit the same metric name with different **sets of tag keys**, or reuse a key with different meanings. Some backends require every series in a metric family to share a uniform label schema; missing a tag on one branch can cause exports to be rejected or queries to break.

To avoid drift:

1. Standardize **name, type, description, unit, and tag keys** for every metric.
2. Share constants or a common abstraction when multiple places instrument one domain.
3. When a tag has no value, emit a fixed fallback such as `unknown` if the metric contract requires that tag.
4. Verify the registry and exported endpoint, because successful compilation does not prove meters were registered properly.

## 7. Metric Names in `Micrometer Observation`

A Spring Boot project can use **Micrometer Observation** to measure operations and feed both metrics and distributed tracing:

```java
import java.util.function.Supplier;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class CheckoutObservations {
    private final ObservationRegistry registry;

    public CheckoutObservations(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T submit(Supplier<T> action) {
        return Observation.createNotStarted("checkout.submit", registry)
                .contextualName("submit checkout")
                .lowCardinalityKeyValue("channel", "web")
                .observe(action);
    }
}
```

Different concepts appear here:

| Property | Role |
| --- | --- |
| `checkout.submit` | **Observation name**, stable name for the operation kind. A metrics handler can use it to create metrics. |
| `submit checkout` | **Contextual name**, contextual description of the operation; a tracing handler may use it as the span name. |
| `channel=web` | **Low-cardinality key-value**, suitable as a grouping dimension on metrics. |
| `ObservationRegistry` | Manages callbacks/handlers; integrations decide whether observations emit metrics, spans, or both. |

**Observation name is not a 1:1 literal Prometheus series name.** Metrics handlers, conventions, and registry naming conventions all shape the final physical meter name. If a tracing handler is configured, spans may take the contextual name; logs still flow through your logging framework.

`ObservationConvention` helps standardize names and key-values across a family of observations. When designing shared names across services, check existing framework/instrumentation conventions before overriding them. For instance, `http.server.requests` emitted by the framework has fixed semantics; arbitrarily altering or reusing it for unrelated business work can break dashboards and SLOs.

### 7.1. Metric Names Are Not Correlation IDs

`traceId` identifies **one distributed trace**, and `spanId` identifies one span. They are indispensable in logs and tracing backends, yet have very high cardinality.

An investigation flow should work like:

**Metric `checkout.submit` shows rising latency** → filter by `channel`, route, or environment → find slow traces by timestamp/signal or exemplar if supported → open logs by `traceId` or correlation ID.

Never create names like:

```text
checkout.submit.trace-91be...
checkout.submit.order-004921...
http.requests.user-18491
```

And never attach those IDs as metric tags. Metric names and tags measure trends; logs and traces track down a specific execution.

## 8. Metric Names from Auto-Instrumentation

Beyond custom meters, Spring Boot Actuator/Micrometer can generate metrics for HTTP, JVM, process, datasources, and supported framework components.

Common logical names, depending on version/configuration:

| Illustrative Logical Name | Signal Group | Meaning |
| --- | --- | --- |
| `http.server.requests` | HTTP | Latency/count of instrumented server requests. |
| `http.client.requests` | HTTP client | Latency/count of instrumented HTTP client calls. |
| `jvm.memory.used` | JVM | Memory currently in use. |
| `jvm.threads.live` | JVM | Current live thread count. |
| `process.cpu.usage` | Process | Process CPU utilization. |

Verify actual names and tag keys in your Spring Boot version. Some stacks adopt updated semantic conventions across releases or instrumentation libraries; do not assume every example meter automatically appears.

When an HTTP server timer already exists, before adding a manual `api.requests.duration` with overlapping meaning, check whether you truly need a new metric or rather a **business observation** covering an unmeasured internal step. Duplicate measurement raises cost and causes rate/latency confusion.

### 8.1. Inspecting Meter Names via Spring Boot Actuator

When Actuator is present and endpoints are exposed per environment policy:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

You can query logical metric names:

```http
GET /actuator/metrics
```

Inspect a specific meter:

```http
GET /actuator/metrics/checkout.duration
```

With recorded tag key/values, the Actuator Metrics endpoint supports filtering via query parameters:

```http
GET /actuator/metrics/checkout.duration?tag=channel:web
```

The endpoint only lists meters and measurements **already registered/recorded**; if the operation hasn't executed yet, the meter may not show up.

To see names emitted by the Prometheus exporter, query:

```http
GET /actuator/prometheus
```

The `prometheus` endpoint requires the Prometheus registry and endpoint exposure. It will not appear with Actuator alone. A project using OTLP or another backend exports names and attributes per its own conventions.

**Security:** Actuator endpoints can disclose system internals. Expose only necessary endpoints, configure authentication/authorization and network restrictions, and never include personal data in metric names or tags.

## 9. Metric Names and Tag Cardinality

A stable metric name is not enough if tags hold dynamic values. Conversely, trying to "reduce tags" by embedding dynamic values into the metric name makes matters worse.

Wrong examples:

```java
// Wrong: every user creates a brand-new metric name.
registry.counter("orders.created.user." + userId).increment();

// Wrong: stable name, yet label still has huge cardinality.
registry.counter("orders.created", "user.id", userId).increment();
```

Right example when comparing channels:

```java
String normalized = "web".equals(channel) || "mobile".equals(channel)
        ? channel : "other";

registry.counter("orders.created", "channel", normalized).increment();
```

Suppose there are 8 routes, 5 status groups, 3 channels, and 4 deployment regions; potential label combinations equal:

\[
8 \times 5 \times 3 \times 4 = 480
\]

This is a **theoretical bound on the hypothetical combinations**, not a guaranteed count of active series. Timers and histograms emit multiple time series per combination, and instance/pod labels multiply series further. Adding a `tenant.id` with 10,000 values pushes theoretical combinations to `4,800,000`.

Questions to check when reviewing a metric:

- Does the name contain per-request, tenant, user, order, URL, or timestamp values?
- Are tag keys standardized everywhere that emits the same metric name?
- Are tag values bounded and known in advance?
- Over the next 12 months, will names/tags grow with user count or only with business categories?
- If the name changes, which dashboards, recording rules, and alerts depend on it?

## 10. Renaming Metrics in a Running System

A metric name is an **observability contract**. Renaming a metric can leave charts blank, silence alerts, break SLO queries, or split historical continuity.

For example, renaming `orders.created` to `checkout.orders.created` is a breaking change for anything querying the old name. Treat it like an API contract change:

1. **Inventory consumers:** dashboards, alerts, recording rules, SLO reports, docs, and external integrations.
2. **Check for semantic changes:** is it purely a name cleanup, or did counting timing, unit, tags, or type change? If semantics changed, document the data break.
3. **Plan migration:** if feasible, dual-emit old and new names temporarily or alias at the query/recording-rule layer. Avoid accidentally double-counting when aggregating both names.
4. **Migrate consumers:** update dashboards and alerts to the new name; verify live data and thresholds.
5. **Monitor and retire old name:** remove the legacy name only after confirming zero consumers still depend on it.

Do not append `.v2` merely because internal code was refactored if measurement semantics stayed identical. Conversely, if the definition changed materially, using a new name or explicit version may be necessary to avoid stitching incompatible datasets together.

## 11. Real-World Measurement: Slow Checkout Case

**Scenario:** Customers report slow checkouts at peak hours. The app emits:

```text
checkout.duration {channel=web}
checkout.duration {channel=mobile}
orders.created     {channel=web}
orders.created     {channel=mobile}
```

Investigation steps:

1. **Verify name and meter type:** is `checkout.duration` a timer or gauge? Does it cover the full checkout or just DB persistence? Check instrumentation code and descriptions.
2. **Inspect rate/duration:** view count, sum, and distributions by channel; compare before and after the anomaly. Without histograms, do not try to plot p95 from nonexistent series.
3. **Assess impact:** if duration climbs while `orders.created` drops, some requests may be failing or timing out; do not guess the cause without outcome/error metrics.
4. **Isolate via traces:** if tracing is enabled, open sampled slow traces and inspect HTTP/DB/payment spans to find where time goes.
5. **Cross-check logs:** search exceptions/timeouts by `traceId` or correlation ID. Metric tags like `channel` filter groups; logs/traces locate specific requests.
6. **Check exporters and sampling:** metrics might miss scrapes, traces might be sampled out, or collectors might drop signals.
7. **Verify after fixing:** ensure metric names/tags preserve semantics, error rate and latency return to acceptable levels, and telemetry flows continuously.

If investigation reveals one service's `checkout.duration` measures only enqueueing while another measures until payment response arrives, then despite **sharing the same name**, their numbers cannot be compared directly. Fix the instrumentation boundary and re-align the measurement contract.

## 12. Common Metric Name Pitfalls

| Symptom | Possible Cause | How to Check and Fix |
| --- | --- | --- |
| `checkout.duration` missing in Prometheus | Registry added unit/type suffixes, or meter has no data yet | Check `/actuator/metrics` and `/actuator/prometheus`; verify naming convention. |
| PromQL query finds no `_bucket` | Histograms disabled or incompatible histogram mode | Check distribution settings, registry, and live series output. |
| Dashboard loses data after deploy | Metric name or label key changed | Diff names/tags before and after; execute controlled migration. |
| Same name yet mismatched units | One service records milliseconds, another seconds outside standard APIs | Standardize type/unit, use Timer API properly, and check output. |
| Backend reports metric conflict | Same name registered with incompatible type or tag keys | Unify definitions; fix duplicate or mismatched meters. |
| Series count scales with traffic/tenants | Dynamic IDs embedded in names or tags | Remove IDs; use bounded tags and log/trace correlation for details. |
| Metrics doubled | Added a counter duplicating timer count, or double-instrumented boundary | Pick one authoritative measurement source and clarify meter roles. |
| `orders.created` rises despite rollbacks | Incremented before transaction confirmation | Move recording point to the agreed business milestone. |
| p95 conflicts with average time | Misread quantiles/histograms, missing buckets, or tiny sample count | Inspect distribution data, tags, and sample counts. |
| Metrics have tags yet logs lack trace ID | Logging lacks MDC integration or context dropped across async boundary | Inspect logging patterns, scopes, and context propagation. |

## 13. Hands-On Practice: Tracing Names from Java to Backend

In a test Spring Boot app with appropriate Micrometer/Actuator dependencies:

1. Create `CheckoutMetrics` from Section 6. Trigger several `web` and `mobile` requests and confirm both counter and timer record data.
2. Check `/actuator/metrics` and note the **logical names** of meters that appear. Query `/actuator/metrics/checkout.duration` and filter with `tag=channel:web`.
3. If the Prometheus registry is present, open `/actuator/prometheus` and locate matching series. Compare logical name `checkout.duration` with physical names ending in `_seconds_count`, `_seconds_sum`, or other suffixes.
4. Enable histograms on the timer in the test environment and verify buckets appear. Compute average latency from count/sum and p95 from buckets when suitable data exists.
5. Send an arbitrary channel `"partner-42"`; confirm your code normalizes it to `other` without expanding tag values.
6. Temporarily test a bad name like `orders.created.<requestId>` **only in a local test environment**, watch meter IDs multiply, and remove that code once you observe the impact.
7. Enable tracing if a bridge/exporter is available, emit a log during checkout, and compare metric name, span name, and trace ID. Explain why each plays a distinct role.
8. Simulate renaming a meter in a trial run, list affected charts/queries, and draft a migration plan.

**Completion criteria:** you can point out the metric name in `MeterRegistry`, its actual exported name, its type and unit, bounded tags, recording point, and its correlation (and limits of correlation) with tracing/logging. Base conclusions on real app output, not memorized example strings.

## 14. Self-Check Questions

**Question 1.** Are `checkout.duration` and `checkout.duration.web` equivalent ways to group by channel?  
**Hint:** No. The second embeds a grouping value in the name. Prefer one stable name with `channel=web|mobile|other` when appropriate.

**Question 2.** Does registering `Counter.builder("orders.created")` in Java guarantee Prometheus displays literally `orders.created`?  
**Hint:** No. Registries apply naming conventions, suffixes, and units; inspect exporter output for exact physical names.

**Question 3.** Can you compute p95 from `checkout_duration_seconds_count` and `checkout_duration_seconds_sum`?  
**Hint:** No. Those two series suffice for windowed averages, not p95; histogram buckets or a suitable distribution mechanism are required.

**Question 4.** Should you put `traceId` inside a metric name to jump from metrics to traces?  
**Hint:** No. That creates dynamic names with extreme cardinality; use logs/traces/exemplars where supported.

**Question 5.** Why must type/unit be part of the metric contract?  
**Hint:** They govern how values are recorded and interpreted. Reusing one name with different meter types or units breaks queries and misleads readers.

**Question 6.** If `Timer.record()` wraps a function returning an incomplete `CompletableFuture`, what duration does the timer measure?  
**Hint:** Only the synchronous execution time of creating/returning the future, not until the future finishes.

**Question 7.** Why must renaming a metric be planned?  
**Hint:** Dashboards, alerts, recording rules, and historical continuity may depend on the old name; uncoordinated renames leave data gaps.

**Question 8.** Can observation name and contextual name differ?  
**Hint:** Yes. Observation name is a stable name for the operation kind; contextual name can describe the span/operation in context. Physical metric names also depend on handlers and exporters.

**Key takeaway:** **A metric name is the contract defining a measurement**, while tags are grouping dimensions and meter type/unit tell you how to read the values. In Spring Boot/Micrometer, prefer stable dot-separated names, avoid embedding IDs or dynamic values, verify names after exporter conversion, and manage renames like API changes. Observability quality also depends on proper measurement boundaries, cardinality, context propagation, and connecting metrics with logs/traces across backends, exporters, and sampling.
