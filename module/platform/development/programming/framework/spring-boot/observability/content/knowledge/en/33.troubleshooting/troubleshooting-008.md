# Abnormal Cardinality Spike

In the **Troubleshooting** chapter of the **SPRING_BOOT_OBSERVABILITY** module, an abnormal cardinality spike occurs when the number of time series or distinct label/tag values on metrics grows rapidly beyond baseline or budget. In Spring Boot, common culprits include tags containing raw URIs, request/user/tenant IDs, exception messages, SQL text, or new dimensions added to an `ObservationConvention`. Newly enabled histograms, increased replica counts, and instrumentation changes after upgrades can also increase series counts without a broken tag.

A cardinality spike can cause Prometheus or the metrics backend to consume excessive RAM, index space, and ingestion capacity; slow down queries; drop scrapes/exports; or hit tenant limits. Effective diagnosis requires identifying which metric family creates additional series, which label has an expanding value set, which changes appeared prior to the spike, and whether the increase stems from replicas/histograms or dynamic values. You then need to contain the source, normalize instrumentation, and verify post-deploy telemetry.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Recognize a cardinality spike via active series, churn, and backend symptoms.
2. Distinguish series growth from samples-per-second growth.
3. Isolate the metric family and label causing the increase.
4. Distinguish tag explosion from replica scaling, histograms, and deployment changes.
5. Trace tags back to Micrometer binders, `Observation` conventions, and custom instrumentation.
6. Normalize URIs, dependencies, SQL operations, and error categories.
7. Use `MeterFilter` as a bounded containment layer.
8. Estimate the impact of series counts on the backend and histograms.
9. Verify fixes with integration/load tests and monitor post-deployment.
10. Update budgets, ownership, and runbooks to prevent recurrence.

## 2. Symptoms of a Cardinality Spike

A cardinality spike typically manifests through one or more symptoms:
- Active series grow rapidly in a short time window.
- New series per minute spike even though traffic barely changed.
- Prometheus head memory or TSDB index size grows.
- The metrics backend reports series/tenant limits, ingestion rejections, or metadata pressure.
- Dashboards and PromQL queries slow down.
- Scrape/export durations increase or samples are dropped.
- A metric family has an unusually high number of label values.
- A recent release added a route, tag, binder, or histogram configuration.

Distinguishing signals:

| Signal | Meaning | Example Cause |
| --- | --- | --- |
| Active time series | Number of currently active metric/label-set series. | Adding a `requestId` tag with a unique value per request. |
| Samples per second | Rate of ingested samples. | Shorter scrape interval or increased traffic. |
| Series churn | Rate at which series are created and go stale. | Raw path IDs or ephemeral tenant IDs. |
| Histogram bucket series | Series emitted per histogram label set. | Enabling extra buckets or adding a tag to a `Timer`. |

Increased traffic can raise samples per second without necessarily increasing cardinality. If active series grow linearly with requests or distinct entities, suspect a tag receiving dynamic values.

## 3. Fast Isolation Workflow

~~~mermaid
flowchart TD
    Spike["Cardinality spike detected"]
    Spike --> Time["Mark first-seen time / release"]
    Time --> Families["Rank metric families by series"]
    Families --> Labels["Inspect label names and value counts"]
    Labels --> Cause{"Likely cause?"}
    Cause -->|Dynamic values| Source["Trace tag to instrumentation"]
    Cause -->|Histogram| Buckets["Check buckets and distribution config"]
    Cause -->|Replica growth| Replicas["Compare per-instance series"]
    Cause -->|Backend/query| Backend["Check ingestion and TSDB limits"]
    Source --> Fix["Contain and normalize tags"]
    Buckets --> Fix
    Replicas --> Fix
    Backend --> Fix
    Fix --> Verify["Test budget and verify after deploy"]
~~~

Collect at a minimum:
1. Start time of the increase and the latest release/config change.
2. Current active series compared to baseline.
3. Top metric names by series count.
4. Label names and distinct value counts for the suspected metric.
5. Number of replicas/targets and scrape interval.
6. Histogram bucket configuration.
7. Backend warnings, dropped samples, and ingestion errors.

Do not start by raising backend limits. First find the dimension driving growth to avoid enlarging costs and the blast radius.

## 4. Inspecting Prometheus and the Metrics Backend

With Prometheus, you can start with TSDB self-metrics:

~~~promql
prometheus_tsdb_head_series
~~~

This metric reports the number of series in the head block; exact name and availability may depend on version. Also inspect self-metrics for series creation/removal, memory, WAL, and scrape samples if your deployment exposes them.

To inspect scrape targets:

~~~promql
up{job="spring-boot"}
~~~

To estimate series counts by metric name within a selector:

~~~promql
count by (__name__) ({job="spring-boot"})
~~~

Adjust selectors and query semantics to match actual labels. For large backends, use an appropriate cardinality explorer/TSDB status API rather than repeatedly running massive queries.

For remote-write/managed metrics backends, check active series per tenant/project, ingestion rate and rejected samples, cardinality/series limit events, top metrics and top label names, plus per-service/per-job breakdowns if supported by the backend.

Do not assume internal Prometheus metric names are identical across versions or managed backends. Check the self-metrics actually scraped in your environment.

## 5. Identifying the Metric Family Causing Growth

Look for metric names whose series count grew sharply compared to baseline. Common families to check in Spring Boot:
- `http.server.requests` or its exported equivalent.
- `http.client.requests`.
- JDBC/datasource and connection pool metrics.
- Business timers/counters with custom tags.
- Messaging, scheduler, and executor metrics.
- Metrics generated from `Observation` conventions.
- Histogram families with buckets.

Once you find the family, compare the label set before and after the spike. For instance, an HTTP metric previously had `method`, `uri`, `status`; after a release, `tenantId` appeared. Or `uri` switched from a route template to a raw path.

Inspect distinct values per label, not just total series count. One label with 10,000 values is usually easier to spot than a metric with 10,000 combinations from multiple small labels.

## 6. Spotting Tags with Dynamic Values

The following tags are frequent sources of uncontrolled cardinality:

| Tag/Value Source | Symptom | Fix |
| --- | --- | --- |
| `uri` raw path | `/orders/1001`, `/orders/1002` | Use route template `/orders/{id}`. |
| `requestId` / `traceId` | Different UUID per request | Remove from metric tags; use logs/traces/exemplars. |
| `userId` / `tenantId` | One series per user/tenant | Use bounded groups/tiers if aggregation is needed. |
| `exception.message` | Message embeds input, host, or SQL | Map to a stable error category. |
| Raw SQL | Varying literal values | Use operation or a normalized, bounded fingerprint. |
| Full URL/query | Query string holds search terms/IDs | Use route template and strip query values. |
| Dynamic dependency host | Changing pod/IP/host | Use a logical dependency/service name. |

Check tag key aliases too, such as `user_id`, `user-id`, `customer`, `tenant`. A blacklist matching only one exact spelling can miss another convention.

## 7. Tracing Tags in Spring Boot and Micrometer

Once the growing label is identified, find where values are attached to the meter:
- `MeterRegistry.counter/timer/gauge` and `Tags.of(...)`.
- `MeterFilter` or custom registry configuration.
- `ObservationConvention.getLowCardinalityKeyValues(...)`.
- `Observation.lowCardinalityKeyValue(...)`.
- `@Timed` extra tags and custom aspects.
- Web MVC/WebFlux filters, interceptors, and HTTP client instrumentation.
- Database, messaging, and executor instrumentation.
- Auto-configured binders after upgrading Spring Boot/Micrometer versions.

Search the codebase by tag key and metric name, then trace callers to see which request/context provides the value. With `Observation`, explicitly verify which key-values are low-cardinality versus high-cardinality; never put request-specific values into low-cardinality key-values.

A safe convention adds only bounded values:

~~~java
class OrderObservationConvention
        implements ObservationConvention<Observation.Context> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context.getName() != null
                && context.getName().startsWith("order.");
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            Observation.Context context) {
        return KeyValues.of(
                KeyValue.of("operation", "order.process"),
                KeyValue.of("outcome", "success")
        );
    }
}
~~~

Adapt this illustrative example's context/convention to your actual instrumentation. Never read principal, request ID, raw URL, or entity ID to construct low-cardinality tags.

## 8. Checking URI and HTTP Instrumentation

Raw URIs are a common culprit because every resource ID creates a new label value. Compare:

~~~text
/orders/1001
/orders/1002
/orders/1003
~~~

with a route template:

~~~text
/orders/{orderId}
~~~

Send multiple requests with different IDs and inspect the `uri` tag in `MeterRegistry`. If framework instrumentation already uses a route pattern, preserve that behavior; if a custom filter creates its own meter, obtain the route template from mapping metadata rather than the raw request URI.

For unknown routes, use a stable fallback such as `UNKNOWN` or `NOT_FOUND`; never record raw paths. Never put query strings, emails, or search terms into tag values.

Inspect HTTP clients separately: the destination should be a logical service name or normalized URI template, not a dynamic host/IP or a full URL with query parameters.

## 9. Checking Exception, SQL, and Business Tags

If the spike began when a custom error metric was added, check tags like `exception`, `error`, `message`, or `sql`. Exception messages can contain SQL statements/literals, hostnames/ports, user input, UUID/request IDs, or downstream response text.

Map errors into a small taxonomy, such as `timeout`, `validation`, `dependency`, `database`, `unexpected`. Use a stable exception family if a class-based taxonomy makes sense; avoid dynamically generated class names.

For databases, use operations like `SELECT`/`INSERT`/`UPDATE`, a stable datasource name, and a normalized query fingerprint if needed. Never use raw SQL or bind values as metric tags.

For tenants, consider a small-set `tenant_tier` dimension such as `standard`/`enterprise` if dashboards genuinely need it. Per-tenant investigations belong in secured logs/traces.

## 10. Histograms and Replica Multiplication

Series counts do not grow from tag values alone. Classic Prometheus histograms emit multiple series per label set: one series per bucket, plus `_count` and `_sum`.

For example, 10 finite buckets, one `+Inf`, count, and sum produce roughly 13 series per label combination. If base combinations are 2,000:

~~~text
2,000 * (10 + 1 + 2) = 26,000 series
~~~

Adding one tag with 100 values raises the estimate to 2,600,000 series under the same assumptions. Check the exporter format, as native histograms/OTLP use different representations.

Replica counts can also raise total series. Each replica may export the same metric family with a distinct `instance` label. Compare per-instance series, active target/replica counts, series counts before/after autoscaling, new tag values per instance, and histogram configuration across environments.

Replica scaling yields roughly linear growth with instance count; tag explosion typically causes per-instance series to grow with input diversity. Distinguish these two sources before changing code.

## 11. Using MeterFilter for Containment

Micrometer's `MeterFilter.maximumAllowableTags` can stop a meter from creating additional values past a threshold:

~~~java
@Bean
MeterFilter uriCardinalityGuard() {
    return MeterFilter.maximumAllowableTags(
            "http.server.requests",
            "uri",
            100,
            MeterFilter.deny()
    );
}
~~~

This is a safety guardrail, not a normalization fix. If the first 100 raw URIs were already registered, the registry still keeps those meters. Nor does a filter delete historical series in the backend or apply to logs/traces.

Use the filter when you need to bound the blast radius while fixing the tag source. Monitor meter registration/rejection if your implementation provides diagnostics. Register the filter before meters are created, and verify the exact meter name, tag key, and filter ordering.

Do not raise the cap merely to silence an alert. Pick limits based on an approved budget and document the rationale.

## 12. Containment Measures During an Active Incident

When the backend nears its limit:
1. Identify the metric family and label values driving growth.
2. If possible, disable the instrumentation or tag source causing the spike via safe configuration.
3. Apply an appropriate `MeterFilter` limit to stop new series, once its behavior has been tested.
4. Pause the rollout/release that introduced the new tag to production.
5. Avoid increasing scrape frequency or enabling extra histograms during investigation.
6. Monitor active series, ingestion rejections, and backend memory.
7. Assess dashboards/alerts that depend on the tag being removed.
8. Do not wipe data or restart the entire monitoring stack without understanding the impact.

Containment requires coordination with platform/observability owners because a filter change can drop meters needed for alerting. Prioritize preserving core signals such as request rate, error rate, and latency with bounded dimensions.

## 13. Testing the Fix and Verifying Post-Deploy

Before deploying the fix:
- Generate varied user/tenant/order/request IDs.
- Send multiple requests through real routes.
- Assert the count of `uri` tag values equals the number of route templates.
- Assert no request/user/tenant/trace IDs appear in metric tags.
- Assert error categories belong to an allowlist.
- Test `MeterFilter` behavior when exceeding the threshold.
- Recalculate the histogram multiplier and per-replica series budget.
- Inspect Prometheus exposition or exporter output.

Post-deploy, monitor active series and new-series rate, top metric families/labels, series per instance and replica count, scrape/export errors and rejected samples, Prometheus memory/TSDB head growth, query latency, and dashboards/alerts.

Do not declare the fix successful just because total series drop within a few minutes—or fail to drop immediately; the backend retains old series until staleness/retention policies expire them. Compare the trend and new series created post-release.

## 14. Troubleshooting

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| Active series grow while traffic is steady | Dynamic tag values or new histogram | Top metric families and distinct label values |
| Series grow roughly proportionally to replica count | Autoscaling or new instance label | Compare per-instance series and target count |
| One HTTP metric spikes abruptly | Raw URI/query or new tag | Inspect `uri`, `method`, `status`, and custom conventions |
| `uri` contains resource IDs | Custom instrumentation uses raw path | Obtain route template from framework mapping |
| Series grow only on error paths | Exception message/class used as a tag | Map errors to a bounded taxonomy |
| Series grow after Boot/Micrometer upgrade | Binder/convention/default tags changed | Compare meter metadata before/after upgrade |
| Histogram series surge | Added buckets or enabled histograms on many meters | Check distribution config and exposition format |
| `MeterFilter` does not block | Wrong meter name/key, registered late, or wrong order | Check registry config and exact meter ID |
| Backend still shows old series after fix | Staleness/retention not expired or registry retains meters | Watch series churn and backend retention |
| Scrapes/exports dropped | Backend limit, network, or exporter queue pressure | Check target status, dropped samples, and exporter diagnostics |
| Slow queries despite flat active series | Samples/second, query scope, or backend contention | Separate ingestion rate from cardinality |

## 15. Runbook: Abnormal Cardinality Spike

1. Record spike start time, service, environment, and latest release.
2. Verify active series, churn, and samples/second to distinguish cardinality from ingestion volume.
3. Rank metric families by series count.
4. Find labels with sharply rising distinct value counts.
5. Compare against changes in tags, routes, binders, histograms, and replica counts.
6. Trace the tag to `MeterRegistry`, `MeterFilter`, `ObservationConvention`, or specific instrumentation.
7. Check whether the tag contains IDs, raw URIs, queries, SQL, exception messages, or dynamic hosts.
8. Contain the source of new series; consider `MeterFilter` and pausing rollouts.
9. Normalize values to route templates, logical dependency names, or bounded error categories.
10. Update integration/property-based tests and cardinality budgets.
11. Deploy with monitoring; verify new active series stabilize and the exporter is not dropping data.
12. Update dashboards, alerts, owners, and the incident record.

## 16. Self-Check Exercises

### Exercise 1 — Traffic or Cardinality?

Traffic doubles while active series remain nearly unchanged; samples/second doubles. Is this a cardinality spike?

**Answer:** Not necessarily. This is primarily increased ingestion/sample volume. Cardinality measures the number of distinct label sets; check active series and churn.

### Exercise 2 — Raw URI

`http.server.requests` grows to millions of series and `uri` contains `/orders/12345`. Cause and fix?

**Answer:** Raw paths containing resource IDs are becoming tag values. Use a route template `/orders/{id}` or a bounded fallback for unknown routes.

### Exercise 3 — Replica Scaling

Series count rises from 10,000 to 20,000 at the same time replicas scale from 5 to 10, while per-instance series stays unchanged. What does this suggest?

**Answer:** The growth is likely due to replica multiplication. Check the `instance` label, target count, and total budget across replicas.

### Exercise 4 — Histogram

Base label combinations are 2,000; a classic histogram has 10 finite buckets, one `+Inf`, `_count`, and `_sum`. Estimate series?

**Answer:** 2,000 × (10 + 1 + 2) = 26,000 series under the assumed exposition format.

### Exercise 5 — MeterFilter

After adding `maximumAllowableTags`, old series still exist. Is the filter broken?

**Answer:** Not necessarily. The filter stops new meters past the threshold; it does not delete already-created meters or historical data in the backend.

### Exercise 6 — Exception Tag

Metric `app.operation` has an `error` tag whose values are raw exception messages. How should this be fixed?

**Answer:** Map errors to bounded groups such as `timeout`, `validation`, `dependency`, or `unexpected`; keep necessary details in controlled logs/traces.

## 17. Recurrence Prevention Checklist

- [ ] Active series and churn baselines exist per service/metric family.
- [ ] Every metric family has a cardinality budget and owner.
- [ ] Request/user/tenant/trace IDs are never used as metric tags.
- [ ] HTTP metrics use route templates and strip query parameters.
- [ ] Dependency tags use stable logical names.
- [ ] Exception/error tags use a bounded taxonomy.
- [ ] Raw SQL and bind values never appear in metric labels.
- [ ] Histogram buckets are accounted for in the series budget.
- [ ] Replica count and per-instance series are monitored separately.
- [ ] `MeterFilter` guardrails are configured before meter creation and tested.
- [ ] Integration tests send diverse identifiers through real instrumentation.
- [ ] Regression tests cover route normalization and error categories.
- [ ] Backend active series, churn, ingestion rejections, and query latency are monitored.
- [ ] A containment runbook and owner coordination path exist when the backend nears limits.
- [ ] Post-deploy verification confirms new series stabilize rather than checking only instantaneous total series.
- [ ] Cardinality is reviewed when upgrading Boot/Micrometer or adding binders/tags/histograms.

**Key Takeaway:** When cardinality spikes abnormally, find the metric family and label values first, then separate tag explosion from histograms, replica scaling, and sample volume. Trace the tag back to Spring Boot/Micrometer instrumentation, normalize dynamic values, use `MeterFilter` for containment, and verify the fix with tests and post-deploy backend telemetry. Never simply raise metrics backend limits before removing the source of unbounded series growth.
