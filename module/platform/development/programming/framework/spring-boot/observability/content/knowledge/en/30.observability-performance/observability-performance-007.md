# Cardinality Budget

In the **Observability Performance** chapter of the **SPRING_BOOT_OBSERVABILITY** module, a cardinality budget is an intentional cap on the number of time series a service's metrics are allowed to produce. Each combination of metric name and label/tag values can become a separate series in the metrics backend. When tags contain user IDs, request IDs, dynamic URLs, or SQL text, combinations grow rapidly, driving up memory, CPU, network, indexing, and query costs.

Micrometer standardizes meters and tags, but cannot know on its own what cardinality fits your workload or infrastructure budget. Engineering teams must decide which dimensions provide operational value, bound the number of values per dimension, and track usage over time. A cardinality budget turns "don't create too many tags" into a rule that can be reviewed, tested, and alerted on.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain cardinality and its impact on the metrics backend.
2. Estimate time series count from metric names, tags, and histogram buckets.
3. Distinguish low-cardinality metric dimensions from high-cardinality trace/log attributes.
4. Build a cardinality budget by service and metric family.
5. Identify sources of cardinality growth such as URLs, exceptions, tenants, and SQL.
6. Normalize routes, dependencies, and outcomes into bounded value sets.
7. Use `MeterFilter` to cap or reject tag values by policy.
8. Evaluate the cost of histograms, percentiles, and multiple registries.
9. Test cardinality with representative data and load tests.
10. Monitor the budget and troubleshoot abnormal series growth.

## 2. What Is Cardinality?

The cardinality of a metric dimension is the number of distinct values that dimension can take. For a metric with multiple tags, combinations of tag values determine the number of time series.

Example HTTP metric dimensions:
- `method`: GET, POST, PUT, DELETE (4 values).
- `status`: 200, 400, 404, 500 (4 values).
- `uri`: 20 route templates.
- `outcome`: SUCCESS, CLIENT_ERROR, SERVER_ERROR (3 values).

Estimated maximum combinations:

~~~text
4 * 4 * 20 * 3 = 960 time series
~~~

This is a simple upper bound if every combination appears. Actual counts may be lower because some combinations are invalid, but budgets should be based on the largest combinations likely to arise, not on a quiet day's traffic.

If you add `customerId` with 100,000 values, the upper bound becomes:

~~~text
4 * 4 * 20 * 3 * 100000 = 96,000,000 time series
~~~

A single tag that seems convenient for debugging can blow a metric family up from hundreds to tens of millions of series.

## 3. Time Series and Backend Cost

In Prometheus-style metrics, a time series is identified by the metric name and the entire label set. Whenever any label value changes, a different series is created.

~~~text
http_server_requests_seconds_count{method="GET",uri="/orders/{id}",status="200"}
http_server_requests_seconds_count{method="GET",uri="/orders/{id}",status="404"}
http_server_requests_seconds_count{method="POST",uri="/orders",status="201"}
~~~

Series with the same metric name but different label values are distinct series. The backend must store metadata and samples for each series, handle ingestion, index labels, and serve queries.

High cardinality can cause:
- Higher RAM and disk usage.
- Higher ingestion/network cost.
- Longer indexing and query times.
- Higher active series count and churn.
- Slow dashboards or query timeouts.
- Backend hitting series/tenant limits and rejecting samples.
- Unpredictable cost spikes as traffic or identifier counts grow.

Cardinality is not sample rate. A frequently scraped single series produces many samples; millions of infrequently scraped series still create massive metadata/indexing and active-series tracking costs.

## 4. Calculating a Budget per Metric Family

List key metric families and their dimensions. Estimate the upper bound as the product of allowed values per dimension:

~~~text
series_budget(metric) =
    product(allowed_values_per_tag)
    * series_multiplier(metric_type)
~~~

For simple counters/gauges, the multiplier is typically 1 per label set. For histograms, include buckets and aggregate series such as count/sum according to the exporter format. Exact representation depends on the registry.

Example initial budget for HTTP request metrics:

| Dimension | Allowed values | Limit |
| --- | ---: | --- |
| method | 5 | GET, POST, PUT, PATCH, DELETE |
| route | 30 | Registered route templates |
| status | 8 | Allowed status codes/groups |
| outcome | 4 | SUCCESS, CLIENT_ERROR, SERVER_ERROR, UNKNOWN |

Upper bound:

~~~text
5 * 30 * 8 * 4 = 4,800 label combinations
~~~

This is a conservative design figure. If method/status/outcome are mutually exclusive in places, actual combinations are lower. When setting a budget, document assumptions and the source of route/status counts so reviewers can verify them.

Do not set only a single service-wide budget. Splitting by metric family helps pinpoint which metric drives series growth while allowing higher budgets for metrics that genuinely need more dimensions.

## 5. Which Dimensions Belong in Metrics?

Metrics answer aggregate questions: which requests are slow, which dependency is failing, how throughput is changing, or whether a pool is exhausted? Choose dimensions with finite, stable value sets.

| Dimension | Metrics? | How to use |
| --- | --- | --- |
| HTTP method | Yes | Finite set of methods. |
| Route template | Yes | `/orders/{orderId}`, never raw paths. |
| Status/outcome | Yes | Controlled set of statuses/outcomes. |
| Service/dependency name | Yes if list is stable | Normalize to a logical service name. |
| Region/zone | Yes if deployment set is bounded | Use only when serving operational analysis. |
| Tenant ID | Usually no | Use controlled logs/traces or group by tenant tier. |
| User/customer ID | No | Per-person identifiers create high cardinality. |
| Request/trace ID | No | Correlate in logs/traces; use exemplars if backend supports them. |
| Full URL/query string | No | Use route templates and drop query values. |
| Raw SQL/exception message | No | Use operation/error type or bounded query fingerprint. |

A dimension that is theoretically finite can still be too large in practice. For example, tenant IDs might be finite yet grow into hundreds of thousands. Budgets must consider both count and growth rate, not merely whether values are "finite".

## 6. Cardinality Grows Multiplicatively

Multiple tags of moderate cardinality can still combine into a massive number of combinations when multiplied together.

~~~text
route:       40 values
method:       5 values
status:      10 values
region:       8 values
tenant:     500 values
--------------------------------
upper bound = 8,000,000 combinations
~~~

When reviewing a metric, ask:
- Is this tag required by any dashboard or alert?
- Does it multiply with existing dimensions?
- Can new values appear continuously?
- Can it be normalized into a smaller group?
- Can details move to logs/traces instead?

Avoid multiplying dimensions just to support every conceivable dashboard filter. Every label is a storage and operational cost choice.

## 7. Route and URI Normalization

HTTP metrics are a common source of high cardinality when the `uri` tag contains raw paths:

~~~text
/orders/1001
/orders/1002
/orders/1003
~~~

Use a route template:

~~~text
/orders/{orderId}
~~~

Spring MVC/WebFlux instrumentation can usually use the route pattern once a request is matched. For custom filters, gateway metrics, or client calls, inspect actual emitted values. When a route is unmatched, use a safe group such as `UNKNOWN` or `NOT_FOUND` rather than falling back to the raw URI.

For HTTP clients, invoke URIs using template APIs and normalize destinations into logical service names. Never put query parameters containing search terms, emails, tokens, or IDs into tags.

Verification steps:
1. Send requests with many different IDs.
2. Query the meter's available tag values.
3. Confirm `uri` stays as the route template.
4. Send an unmatched path and check the fallback value.
5. Check gateway/client instrumentation separately.

## 8. Exceptions, SQL, and Business Identifiers

Do not use exception class names if hundreds of dynamic proxy/generated class names exist; prefer error categories or stable exception groups. Never use exception messages because messages can contain hosts, SQL, user input, or identifiers.

For SQL, use operations such as `SELECT`/`INSERT`/`UPDATE` and the datasource name. If query-level analysis is needed, use a normalized query fingerprint with a bounded set; never use raw SQL text or bind values as metric dimensions.

For business identifiers, shift the question from "which specific tenant?" to "which tenant tier?" if the dashboard goal is capacity. For instance, `free`/`standard`/`enterprise` tiers may fit if the group count is small and governed. Investigating a specific request/tenant should rely on trace/log search with proper access control, retention, and sampling policies.

## 9. Histograms Multiply Series Counts

Histograms create multiple series per label set. With Prometheus classic histograms, each bucket is a separate series, usually alongside `_count` and `_sum`. If a histogram has 12 finite buckets plus the `+Inf` bucket, each label set can create 14 series (13 bucket series plus count/sum), depending on exposition format.

Example:

~~~text
base label combinations = 4,800
finite buckets           = 12
+Inf bucket              = 1
_count and _sum          = 2

approx series = 4,800 * (12 + 1 + 2)
              = 72,000
~~~

This estimates classic histograms; native histograms or other registries have different semantics. Check your actual exposition format and backend.

Enabling histograms on many metrics with many tag combinations multiplies series count in both dimensions. Enable histograms only for latency metrics needed for percentiles/SLOs; choose appropriate bucket boundaries; evaluate series cost before adding new tags; aggregate percentiles at the backend from histogram buckets when needed. Never sum or average client-side percentiles.

## 10. Cardinality Budgets for Metrics and Detail for Traces/Logs

Not all high-cardinality information needs to be stripped from observability. Place it in the right signal:

- **Metrics**: bounded dimensions for aggregation and alerting.
- **Traces**: attributes can carry request-specific context when permitted, with appropriate sampling and retention.
- **Logs**: structured fields for locating specific events, with access control and masking.
- **Exemplars**: link a metric sample to a trace ID when supported by registry/backend, letting you jump from a metric spike to a trace without making trace ID a metric label.

Instead of adding `traceId` to every metric series, use exemplars or correlation fields in logs. This keeps metric cardinality stable while still supporting deep investigation. Traces/logs still require privacy reviews, masking, sampling, access controls, and retention.

## 11. Enforcing Limits with Micrometer MeterFilter

Micrometer `MeterFilter` can cap tag values or drop tags/meters by policy. For example, using `maximumAllowableTags` to cap `uri` values for a meter name:

~~~java
@Configuration(proxyBeanMethods = false)
class MetricsCardinalityConfiguration {

    @Bean
    MeterFilter httpUriCardinalityLimit() {
        return MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny());
    }
}
~~~

This filter illustrates a protective guard: once the allowed tag values are exceeded, new meters with tag values beyond the threshold are denied. Exact behavior depends on filter ordering and the registry. It does not replace route normalization; if the first 100 raw paths already entered the registry, cardinality is still poor.

You can use a filter to strip unnecessary tags:

~~~java
@Bean
MeterFilter removeUserTag() {
    return MeterFilter.ignoreTags("userId", "customerId", "requestId");
}
~~~

Verify API names/behavior for the Micrometer version managed by Spring Boot. Filters should be configured centrally and tested against a real registry. Do not rely on filters to mask design flaws at the instrumentation source if the tag source can be fixed.

Limits to understand:
- A filter may deny new meters, but does not necessarily remove previously registered series.
- The registry may already hold meters and state in memory.
- The backend may keep storing old series until retention/staleness policies expire them.
- Filters do not automatically sanitize logs, spans, or baggage.
- A single filter limit does not guarantee every metric family stays within budget.

When cardinality needs fixing, prioritize fixing the instrumentation/tag source first, then deploy and monitor series churn.

## 12. Service-Level Budgets and Ownership

An operational budget should have an owner and a review cadence. Example:

| Metric family | Target budget | Owner | Review trigger |
| --- | ---: | --- | --- |
| HTTP request timers | 5,000 label combinations | API team | Adding a new route/tag. |
| HTTP client timers | 2,000 | Integration team | Adding a dependency/destination. |
| JDBC operation metrics | 500 | Data team | Adding a datasource/operation. |
| Scheduler/task metrics | 300 | Platform team | Adding a task type/outcome. |
| JVM/runtime metrics | Per binder baseline | Platform team | Upgrading binder/Boot version. |

These numbers are illustrative examples, not universal limits. Real budgets must reflect backend capacity, scrape interval, retention, replica counts, histogram configuration, and query needs.

Establish clear ownership:
- Teams owning instrumentation are responsible for tags.
- The platform/observability team monitors active series and backend capacity.
- Reviewers check budgets whenever metrics/tags/routes are added.
- The release process can require comparing cardinality before and after changes.

## 13. Measuring and Monitoring Actual Cardinality

Do not trust design calculations alone. Monitor active series and series churn in the backend. With Prometheus, you can use self-metrics such as TSDB series count and head series; exact metric names depend on version and deployment.

Illustrative query example:

~~~promql
prometheus_tsdb_head_series
~~~

Track series counts by job/tenant/backend if your metrics backend provides those dimensions. Distinguish:
- Current active series.
- New series rate/churn.
- Total series within retention.
- Ingestion samples/second.
- Cardinality by metric name and label.

One metric family can produce many series even at low samples/second. Conversely, a few series with a high scrape rate still create substantial ingestion load.

Compare against per-service/release baselines. When adding a new tag or route, measure before and after deploy; inspect series counts, memory, and query latency.

## 14. Testing the Cardinality Budget

Tests should send varied inputs belonging to the same logical route/operation to verify tags are normalized.

Conceptual test example with `SimpleMeterRegistry`:

~~~java
@Test
void uriTagUsesRouteTemplate() {
    MeterRegistry registry = new SimpleMeterRegistry();

    // Record requests with different IDs.
    recordRequest(registry, "/orders/{orderId}", "GET");
    recordRequest(registry, "/orders/{orderId}", "GET");
    recordRequest(registry, "/orders/{orderId}", "GET");

    Set<String> uriValues = registry.find("http.server.requests")
            .meters()
            .stream()
            .flatMap(meter -> meter.getId().getTags().stream())
            .filter(tag -> tag.getKey().equals("uri"))
            .map(Tag::getValue)
            .collect(Collectors.toSet());

    assertThat(uriValues).containsExactly("/orders/{orderId}");
}
~~~

This is an illustrative skeleton; the `recordRequest` helper must exercise actual application instrumentation rather than manually passing the template tag so the test always passes. Integration tests should send real HTTP requests to varied path IDs and inspect the meter registry after the framework resolves routes.

Tests should verify:
1. Multiple IDs on the same route produce only one `uri` tag value.
2. Raw query parameters never appear in tags.
3. User/request/tenant IDs are absent from metric tags.
4. Exception messages are never used as dimensions.
5. Tag value counts stay within configured limits.
6. Histogram bucket counts stay within estimate.
7. Meter filters behave as expected for your version.
8. Load tests generate a route/destination distribution representative of production.

## 15. Troubleshooting

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Active series spike suddenly | New tag contains IDs, URLs, or exception messages. | Break down series by metric name and labels. |
| `uri` has thousands of values | Raw paths used instead of route templates. | Inspect MVC/WebFlux/gateway/client instrumentation. |
| Metrics backend rejects samples | Series/tenant limit or ingestion capacity exceeded. | Check backend limits and series churn. |
| Histograms create more series than expected | Bucket count multiplied by label combinations. | Inspect exposition format and bucket config. |
| Meters denied past threshold | `maximumAllowableTags` blocked new tag values. | Locate tag source and normalize at source. |
| Slow dashboard queries | Query scans too many series/label combinations. | Reduce dimensions and scope queries. |
| Old series remain after fixing tag | Backend retention/staleness and registry lifecycle. | Watch expiry; do not expect filters to delete historical data. |
| Only one replica has high cardinality | Different input distribution or config across replicas. | Compare build/config and tag values per instance. |
| Hard to search traces/logs after removing ID tag | Correlation was not designed. | Use trace IDs, structured logs, or exemplars. |
| Budget grows after upgrade | Instrumentation/binder added tags or routes. | Compare metric metadata and series baselines before/after. |

## 16. Runbook: Cardinality Exceeds Budget

1. Identify the backend, tenant, and service with rising active series.
2. Find the metric families contributing the most series.
3. Compare label names/values against the approved budget.
4. Identify the new tag or continuously growing tag value.
5. Check route normalization, destination naming, and exception mapping.
6. Temporarily block further series growth if possible via appropriate filters/config.
7. Fix the instrumentation source to remove IDs/raw URLs/SQL or normalize into a bounded group.
8. Test with representative data and verify the new upper bound.
9. Deploy with a rollout monitoring active series, ingestion, and memory.
10. Assess impact on dashboards/alerts that relied on removed dimensions.
11. Wait for backend retention/staleness to age out old series; check deletion policies if needed.
12. Update budgets, owners, and regression tests to prevent recurrence.

Do not resolve by raising backend limits before identifying the cardinality source. Raising limits can delay failure while accelerating cost growth.

## 17. Self-Check Exercises

### Exercise 1 — Series Math

A metric has 6 method values, 12 route values, and 5 status values. What is the upper bound of label combinations?

**Answer:** 6 × 12 × 5 = 360 combinations, assuming every combination can occur.

### Exercise 2 — Adding Tenant ID

The metric above adds a `tenant` tag with 2,000 values. What is the new upper bound?

**Answer:** 360 × 2,000 = 720,000 combinations. One dimension sharply multiplies cardinality even when the first three dimensions are small.

### Exercise 3 — Raw URI

Requests to `/orders/1`, `/orders/2`, `/orders/3` produce three `uri` values. How do you fix it?

**Answer:** Use the route template `/orders/{orderId}` or a stable fallback route. Never use raw paths as metric tags.

### Exercise 4 — Histograms

A metric has 1,000 label combinations and a classic histogram with 10 finite buckets, one `+Inf`, `_count`, and `_sum`. Estimate the series count?

**Answer:** 1,000 × (10 + 1 + 2) = 13,000 series, under the assumed classic histogram export format.

### Exercise 5 — Finding a Specific Request

Operations wants to filter metrics by trace ID. Should you add trace ID as a tag?

**Answer:** No. Use the trace backend, structured logs, or exemplars if supported to link a metric sample to a trace.

### Exercise 6 — Filter Blocked New Values

After adding `maximumAllowableTags`, old series still remain in the backend. Does this mean the filter isn't working?

**Answer:** Not necessarily. The filter blocks new meters beyond the threshold; it does not automatically delete already-created series or historical backend data.

## 18. Implementation Checklist

- [ ] Each metric family has a list of dimensions and an upper-bound budget.
- [ ] Budgets are calculated as the product of tag values, not each tag individually.
- [ ] Histogram buckets/count/sum are included in series estimates.
- [ ] HTTP metrics use route templates instead of raw paths/query strings.
- [ ] Dependency/datasource/task names are normalized and have bounded value sets.
- [ ] User, tenant, request, trace, order IDs, and timestamps are never used as metric tags.
- [ ] Raw SQL and exception messages are never used as dimensions.
- [ ] High-cardinality details are placed in logs/traces with masking, sampling, and access policies.
- [ ] Exemplars are considered for metric-to-trace correlation when supported by the backend.
- [ ] `MeterFilter` limits are configured and tested; they are not treated as a substitute for normalization.
- [ ] Histograms are enabled only on metrics needed for latency/SLO analysis.
- [ ] Budgets have owners and are reviewed whenever metrics/tags/routes are added.
- [ ] Integration/load tests use an input distribution representative of production.
- [ ] Active series, churn, ingestion, and backend limits are monitored.
- [ ] A runbook exists to identify the metric family/tag driving cardinality growth.
- [ ] Dashboards/alerts are reviewed whenever dimensions are removed.

**Key takeaway:** A cardinality budget controls series counts by capping combinations of metric names and tag values. Estimate by multiplying dimensions, include histogram buckets, normalize routes/destinations/errors, and keep identifiers in logs/traces rather than metric labels. Use `MeterFilter` as a protective guardrail, test with representative data, and monitor active series/churn to catch budget overruns before the backend overloads.
