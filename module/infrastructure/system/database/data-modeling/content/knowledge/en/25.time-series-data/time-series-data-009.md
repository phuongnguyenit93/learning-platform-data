# Label Combinations and the Risk of Series Cardinality Explosion

## Learning Objectives

In the **DATABASE_DATA_MODELING** course, a sound data model turns business needs into meaningful, measurable, and verifiable structures—from relationships and constraints to physical storage. For **time-series data**, beyond timestamps and values, designers must understand **series-identifying labels/tags**. A poor label choice can cause series counts to grow vastly faster than the underlying business entities being observed.

After this lesson, you will be able to:

1. Explain how **a series is identified by metric name plus the entire label set**, and distinguish sample volume from series count.
2. Calculate **upper bounds on label combinations** while understanding why actual combinations can be lower than the theoretical product.
3. Identify **high-cardinality** and **high-churn** labels such as `user_id`, `request_id`, raw URLs, and short-lived pods/jobs.
4. Estimate impacts on ingested samples, memory, indexes, storage, query performance, and series continuity.
5. Design label sets rich enough for queries without turning every individual event into its own series.
6. Use SQL to inspect active series, series per metric, per-label distinct counts, and series creation rates.
7. Establish cardinality budgets, instrumentation tests, alerts, and controlled mitigation strategies.

## 1. A Time Series Differs from an Event Record

Suppose a system tracks HTTP requests per service. A counter metric might look like:

~~~text
http_requests_total{
    service="checkout",
    environment="prod",
    region="ap-southeast",
    route="/orders/{orderId}",
    status_class="2xx"
}
~~~

In this representation, **series identity** is determined by:

\[
\text{Series ID}
=
(\text{metric name},\ \text{label set}).
\]

A *label set* is a collection of `label_name=label_value` pairs. Pair ordering does not make them distinct labels, yet **changing a single label value** produces a distinct series identity. Above:

~~~text
http_requests_total{service="checkout",route="/orders/{orderId}",status_class="2xx"}
http_requests_total{service="checkout",route="/orders/{orderId}",status_class="5xx"}
~~~

are **two distinct series** even when all other labels remain identical.

Samples belonging to **the same series** look like:

~~~text
series: http_requests_total{service="checkout",region="ap-southeast",...}

2026-11-01T10:00:00Z  1802
2026-11-01T10:00:15Z  1815
2026-11-01T10:00:30Z  1828
~~~

**Timestamps and values are not part of series identity.** The three samples above belong to **one series**, not three. Conversely, changing `route` from a normalized template to a raw URL containing per-request IDs creates thousands of distinct series, each holding only one or a few samples.

### Distinguishing Three Concepts

| Concept | Question | Illustrative Unit |
|---|---|---|
| **Series cardinality** | How many distinct metric name + label-set combinations exist? | 7,200 series |
| **Sample volume** | How many data points are ingested over time? | 41,472,000 samples/day |
| **Series churn** | How many new series appear, disappear, or rotate label sets per window? | 2,000 new series vs. prior hour |

These three metrics are related yet **do not replace one another**. Lowering sampling frequency reduces sample volume **without reducing the number of series the system must track**.

## 2. Why Can Labels Cause a Combinatorial Explosion?

A metric is partitioned by five labels:

~~~text
service
environment
region
route
status_class
~~~

Suppose within our observed scope:

| Label | Assumed Distinct Values |
|---|---:|
| `service` | 6 |
| `environment` | 3 |
| `region` | 4 |
| `route` | 20 |
| `status_class` | 5 |

If **every combination is possible**, the upper bound on series for **one metric** is:

\[
C_{\max}
=
6\times3\times4\times20\times5
=7,200.
\]

So with just five seemingly modest labels, the system may already track **7,200 series for this single metric**.

Add `customer_id` with **1,000 values**, and the upper bound becomes:

\[
7,200\times1,000=7,200,000.
\]

That is **7.2 million potential combinations**, before counting any other metrics.

### Important: The Label Product Is an Upper Bound, Not Automatically the Actual Series Count

In practice:

- A service may run in only certain regions.
- Not every route exists on every service.
- Some route/status combinations never occur.
- `instance_id` typically binds to one specific service and region rather than spanning every combination.

Therefore:

\[
C_{\text{observed}}\leq\prod_{i=1}^{k}|L_i|
\]

where \(|L_i|\) is the distinct value count of label \(i\) within the **same scope**, and \(C_{\text{observed}}\) is the count of **label sets that actually occurred** for that metric. This inequality holds once **absent labels**, scope, and observation window are defined consistently.

Never claim “there are 7.2 million series” merely because multiplication produces that number. To know reality, **count distinct label sets**, not just per-column cardinalities.

### What Drives Rapid Multiplicative Growth?

If an initial label set has \(C\) combinations, adding a label with \(m\) values **independent of existing labels** can multiply series count up to:

\[
C'=C\times m.
\]

If labels correlate, actual growth is lower. Even so, many **moderate-cardinality** labels combined together still produce massive totals. Do not audit only labels with millions of values.

## 3. High Cardinality and High Churn Are Distinct Problems

### 3.1. High-Cardinality Labels

Examples:

~~~text
user_id = U000001 ... U999999
request_id = 8d2f... (unique per request)
session_id = 71c9... (unique per session)
raw_path = /users/12345/orders/67890
error_message = "failed for item 8934 at ..."
~~~

These attributes are invaluable in **logs, traces, and event records**, yet poorly suited as **labels on repeatedly sampled metrics**. Giving every request a `request_id` label turns an aggregated metric into millions of nearly single-sample series.

### 3.2. High-Churn Labels

Not every high-churn label has huge concurrent cardinality. Example:

~~~text
pod_id = checkout-7bc42      -- lives 15 minutes
pod_id = checkout-8d911      -- replaced after deploy
pod_id = checkout-c2a77      -- replaced after scale
~~~

At any instant only 20 pods may run, yet across deployments and autoscaling events the system spawns **hundreds or thousands of distinct label sets over time**.

Therefore, monitor together:

- **Active series:** series receiving samples within a defined recent window.
- **Historical distinct series:** all distinct label sets encountered over a longer window.
- **New / disappearing series:** series present in this window but absent in the previous window, and vice versa.
- **Series lifetime:** how long a typical series lives and whether it holds enough samples for meaningful math.

Looking solely at **active series** misses a system constantly churning through short-lived series. Looking solely at **historical distinct series** overstates how many series must stay resident in memory simultaneously.

### 3.3. Short-Lived Entity Labels Are Sometimes Necessary

`instance`, `pod`, or `node` are not **always wrong**. Diagnosing errors on a single failing instance can be operationally vital. Base the decision on:

- Do you truly need **per-instance** metric queries, or do service/region levels suffice?
- Are concurrent instance counts and replacement rates bounded?
- Do you need both service-level and instance-level metrics?
- Can per-instance detail live in logs/traces or a separate store instead?

The goal is **the resolution required for decisions**, not blindly banning all infrastructure labels.

## 4. How Do Histograms Multiply Series Counts?

HTTP latency metrics typically need **response-time distributions**, not just an average. With classic bucketed histograms, emitted series include:

~~~text
http_request_duration_seconds_bucket{...,le="0.1"}
http_request_duration_seconds_bucket{...,le="0.3"}
http_request_duration_seconds_bucket{...,le="1.0"}
...
http_request_duration_seconds_bucket{...,le="+Inf"}
http_request_duration_seconds_sum{...}
http_request_duration_seconds_count{...}
~~~

`le` is the bucket upper-bound label. **Each `le` value creates a separate bucket series** for the same remaining label set. Thus:

\[
\text{classic histogram series}
\approx
C_{\text{labelset}}\times(B+2),
\]

where \(B\) is the **number of bucket series** (including `+Inf`), and `+2` accounts for `_sum` and `_count`. This formula applies to **one full classic histogram** sharing a label set; native histograms or alternative metric representations may follow different scaling rules.

If the earlier example has **7,200 label-set combinations** and a histogram emits **10 bucket series plus one sum and one count**, total series can reach:

\[
7,200\times(10+2)=86,400.
\]

A high-cardinality label does not just inflate one counter: it multiplies the entire **histogram series family** for every combination.

### Should Histograms Be Dropped to Save Series?

Do not jump to that conclusion from cost alone. If latency SLOs or tail distributions matter, histograms are essential. Instead:

1. Identify which metrics genuinely need latency distributions.
2. Choose buckets aligned with business/SLO thresholds rather than dense arbitrary grids.
3. Trim **unnecessary labels** before sacrificing measurement fidelity.
4. Evaluate histogram formats (such as native histograms) and engine storage/query capabilities.

**Remember:** a metric's series count can be multiplied by **measurement structure** such as buckets, not only by application labels.

## 5. How Series Count Translates into Storage and Operational Cost

Return to the 7,200-series example sampled **every 15 seconds** all day, assuming zero dropped or skipped samples:

\[
\text{samples per series/day}
=\frac{24\times60\times60}{15}
=5,760.
\]

Daily samples for **one metric**:

\[
7,200\times5,760
=41,472,000\text{ samples/day}.
\]

For a classic histogram with 12 series per label set, potential daily samples reach:

\[
86,400\times5,760
=497,664,000\text{ samples/day}.
\]

These are **illustrative upper-bound sample emission estimates**, not byte measurements on a specific engine. Actual footprint depends on active series presence, uptime, scrape failures, compression, index structures, and retention policies.

### Components Under Pressure

| Component | Risk from High Series Count | Why Monitor It |
|---|---|---|
| **Memory / head index** | Tracking many series IDs, metadata, and write buffers | Scales with series count, not just compressed sample bytes |
| **Ingestion** | Many concurrent active streams receiving points | Raises CPU, serialization, and I/O overhead |
| **Label indexes** | Many new label sets and values | Increases inverted-index size and lookup cost |
| **Long-term storage** | More samples and series metadata retained | Expands disk and object/block storage cost |
| **Queries** | Filters and aggregations touch far more series | Raises CPU, RAM, and response latency |
| **Compaction / retention** | Many short-lived series or fragmented blocks | Increases background cleanup and compaction work |
| **Dashboards and alerting** | Broad queries and large result series sets | Slows UIs and increases alert noise |

### What Does Lowering Sampling Frequency Solve?

Increasing the scrape interval from **15 seconds to 60 seconds** cuts ideal sample volume **4×** when series count stays fixed. However, the count of existing label-set series **often stays unchanged**.

Hence:

~~~text
Optimize scrape interval → mainly reduces sample rate.
Optimize labelset       → reduces series count plus metadata/indexes.
Optimize retention      → bounds how long data is retained.
Optimize queries        → reduces query cost.
~~~

These levers complement one another—**they are not interchangeable substitutes**.

## 6. Which Labels Belong on Metrics and Which Belong Elsewhere?

Do not ask “how many values does this label have?” in isolation. Also ask **“do users need to group/filter metrics by it, is its value domain bounded, and does it churn constantly?”**

| Field | Suitable as a Metric Label? | Rationale / Alternative |
|---|---|---|
| `service` | Usually yes | Groups by service; count is typically manageable |
| `environment` | Usually yes | Separates prod/staging/dev |
| `region` | Usually yes | Regional infrastructure breakdown; finite domain |
| `http_method` | Conditionally | `GET`, `POST`, etc.—usually small finite set |
| `status_class` | Usually yes | `2xx`, `4xx`, `5xx` groups support error monitoring |
| `status_code` | Conditionally | Larger than class yet bounded; weigh against need |
| `route_template` | Yes, if governed | Must be stable templates, never URLs with IDs |
| `instance`/`pod` | Conditionally | Helpful for diagnostics, yet raises cardinality/churn |
| `tenant_id` | Evaluate case-by-case | Can be huge; per-tenant analytics may fit another model better |
| `customer_id` | Usually not for infra metrics | Easily millions of values; use event/BI data |
| `user_id` | Usually no | Both high-cardinality and potentially sensitive |
| `request_id`/`trace_id` | Usually no | Nearly unique per request; belongs in logs/traces |
| `session_id` | Usually no | Spawns masses of short-lived series |
| `url_path_raw` | No if dynamic IDs appear | Use `route_template` |
| `error_message` | Usually no | Free-form text generates unbounded values |
| `timestamp` as label | No | Time is already the sample axis; adding as label spawns new series |

### Raw URLs vs. Route Templates

Never emit metrics like:

~~~text
http_requests_total{path="/users/1001/orders/5001"}
http_requests_total{path="/users/1002/orders/5002"}
http_requests_total{path="/users/1003/orders/5003"}
~~~

If the business needs error rates **by endpoint pattern**, use:

~~~text
http_requests_total{route="/users/{userId}/orders/{orderId}"}
~~~

Route templates must be governed by **the router/instrumentation or a bounded registry**. Never blindly apply a regex replacing digits with `{id}` across arbitrary URLs: paths may contain slugs, resource names, arbitrary tokens, or unexpected variation.

Unmatched routes should map into a controlled bucket such as `route="unmatched"` per policy, while logging raw URLs in **logs/traces** if permitted. Never turn arbitrary unmatched paths into fresh metric labels.

### Free-Form Strings and Error Types

`error_message="timeout contacting tenant 983..."` can spawn millions of series. To track errors by category:

~~~text
error_type="dependency_timeout"
error_type="validation_failed"
error_type="internal_failure"
~~~

Keep the error taxonomy finite, owned, and change-controlled. Detailed messages belong in logs with appropriate traceability and retention.

## 7. Keep Granular Details in the Right Data Model

Different observability goals fit different data models:

| Question | Better-Suited Model | Why |
|---|---|---|
| Error rate by service, region, route | **Metrics** with bounded labels | Efficient aggregation and alerting |
| Why did request `REQ-123` fail? | **Traces / logs** with request ID | Inspects one specific execution |
| Which customer generates the most transactions? | **Fact table / event data** by user/tenant | Supports keys, timestamps, business joins, and detail |
| Detailed balance changes for one account | **Transaction events or audit log** | Avoids unbounded per-account metric series |
| Order volume by category/day | **Data mart** with explicit grain and dimensions | Easy reconciliation of measures and history |
| CPU health of active pods | **Metrics with instance/pod labels where needed** | Needed to diagnose infrastructure units |

This does not mean `tenant_id` or `user_id` is forbidden in **every** time-series system. A platform tracking per-account balances or per-device IoT telemetry may **intentionally** track millions of series because each device or account is the primary subject. In that case, **architect and provision explicitly for that cardinality** using partitioning/sharding and clear limits—rather than accidentally injecting such IDs into every infrastructure metric's label set.

### Connection to Facts and Dimensions

In a data warehouse, an event table:

~~~text
fact_orders(order_id, customer_id, product_id, confirmed_at, amount)
~~~

carries `customer_id` at transaction grain and analyzes millions of customers cleanly. That **does not mean** `http_latency_seconds{customer_id=...}` belongs in operational metrics. Event analytics and operational metric systems have **different** query targets, ingestion mechanics, and optimizations.

## 8. Design a Cardinality Budget Before Deployment

A practical discipline is setting a **series budget** per metric group and validating it prior to release.

### Budget Template

| Field | What to Specify |
|---|---|
| Metric or metric group | `http_requests_total`, latency histogram |
| Purpose | Error rates by service/route/status |
| Mandatory labels | `service`, `environment`, `route_template`, `status_class` |
| Optional labels | `region`, `instance` if justified |
| Expected value limits | Counts of services, routes, regions, statuses per interval |
| Actual label-set count | Distinct label sets over 15m / 1h |
| Churn | Label sets present in current window but absent in prior window |
| Metric type | Counter, gauge, classic/native histogram |
| Projected cost | Active series, samples/sec, storage, query load |
| Alert threshold | Tied to verified system capacity and headroom |
| Owner | Team owning instrumentation/service |
| Mitigations | Normalize routes, drop dynamic labels, cap bucket counts... |

No universal threshold like “every metric must stay under 1,000 series” fits all platforms. Allowable limits depend on total metrics, infrastructure, sampling rates, retention, architecture, and query SLAs.

### Two Distinct Estimates

**Before release**, multiply possible label values:

\[
C_{\max}=\prod_i |L_i|.
\]

This serves as a **design stress test**; it may overstate reality when labels correlate.

**After release**, measure directly:

\[
C_{\text{active}}
=
\left|\{(\text{metric},\text{label set})\text{ with samples in window}\}\right|.
\]

Also measure **new-series creation rate**, sample rate, query latency, and resource usage. A setup with 20,000 stable active series behaves very differently operationally from 20,000 active series rotating all labels every few minutes.

## 9. Verifiable SQL Model for Measuring Cardinality

This section uses **PostgreSQL as a modeling example** without claiming dedicated TSDBs physically store series identically. The goal is illustrating how to **identify series**, count label sets, and measure churn relationally.

### 9.1. Series Catalog and Sample Tables

~~~sql
CREATE TABLE metric_series (
    series_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metric_name TEXT NOT NULL,
    service TEXT NOT NULL,
    environment TEXT NOT NULL,
    region TEXT NOT NULL,
    route_template TEXT NOT NULL,
    status_class TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    UNIQUE (
        metric_name,
        service, environment, region,
        route_template, status_class, instance_id
    )
);

CREATE TABLE metric_samples (
    series_id BIGINT NOT NULL REFERENCES metric_series(series_id),
    sampled_at TIMESTAMPTZ NOT NULL,
    sample_value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (series_id, sampled_at)
);

CREATE INDEX idx_metric_samples_time
    ON metric_samples (sampled_at);
~~~

Here, **every label column is `NOT NULL`** so the `UNIQUE` constraint enforces consistent tuple uniqueness. If a metric omits `route_template` or `status_class`, the pipeline must encode **absent labels via an explicit non-colliding convention**. Real engines may support optional/nullable tags or schemaless label maps; never treat empty string and missing label as identical if the target engine distinguishes them.

**Key semantics:**

- `metric_series.series_id`: technical key for **one metric + one label set**.
- `UNIQUE` across identifying columns: prevents spawning **two series IDs** for the same normalized label set.
- `metric_samples(series_id, sampled_at)`: **one sample per timestamp per series** in this simplified model. Production ingestion needs rules for late, retried, or conflicting samples at equal timestamps.

`DOUBLE PRECISION` illustrates technical telemetry; **never substitute it for `NUMERIC` on monetary figures requiring exact decimal math**. Specify units, counter/gauge kind, and missing-data rules per metric.

### 9.2. Counting Total Registered Series

~~~sql
SELECT metric_name, COUNT(*) AS catalog_series
FROM metric_series
GROUP BY metric_name
ORDER BY catalog_series DESC, metric_name;
~~~

This returns **total label sets in the catalog** per metric, not necessarily active ones. A catalog that never expires stale series accumulates dead entries over time.

### 9.3. Counting Active Series in a Window

To count series with **at least one sample in a 15-minute window**:

~~~sql
WITH active AS (
    SELECT DISTINCT series_id
    FROM metric_samples
    WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 10:00:00+00'
      AND sampled_at <  TIMESTAMPTZ '2026-11-01 10:15:00+00'
)
SELECT s.metric_name, COUNT(*) AS active_series
FROM active AS a
JOIN metric_series AS s
  ON s.series_id = a.series_id
GROUP BY s.metric_name
ORDER BY active_series DESC, s.metric_name;
~~~

**Define windows explicitly.** A series failing scrapes shows up as “inactive” in this query even though its target still exists. Here “active” strictly means **observed at least one sample during the window**.

### 9.4. Counting Distinct Values per Label

~~~sql
WITH active AS (
    SELECT DISTINCT series_id
    FROM metric_samples
    WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 10:00:00+00'
      AND sampled_at <  TIMESTAMPTZ '2026-11-01 10:15:00+00'
)
SELECT
    s.metric_name,
    COUNT(DISTINCT s.service) AS services,
    COUNT(DISTINCT s.environment) AS environments,
    COUNT(DISTINCT s.region) AS regions,
    COUNT(DISTINCT s.route_template) AS routes,
    COUNT(DISTINCT s.status_class) AS status_classes,
    COUNT(DISTINCT s.instance_id) AS instances,
    COUNT(*) AS observed_labelsets
FROM active AS a
JOIN metric_series AS s
  ON s.series_id = a.series_id
GROUP BY s.metric_name
ORDER BY observed_labelsets DESC;
~~~

`observed_labelsets` is the **observed label-set count**, while `services`, `routes`, etc., are **per-dimension distinct counts**. Never multiply those columns and report the product as actual observed series, because labels often correlate.

### 9.5. Measuring Churn Between Consecutive Windows

~~~sql
WITH previous_window AS (
    SELECT DISTINCT series_id
    FROM metric_samples
    WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 09:00:00+00'
      AND sampled_at <  TIMESTAMPTZ '2026-11-01 10:00:00+00'
),
current_window AS (
    SELECT DISTINCT series_id
    FROM metric_samples
    WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 10:00:00+00'
      AND sampled_at <  TIMESTAMPTZ '2026-11-01 11:00:00+00'
),
appeared_vs_previous AS (
    SELECT series_id FROM current_window
    EXCEPT
    SELECT series_id FROM previous_window
)
SELECT s.metric_name, COUNT(*) AS appeared_vs_previous_hour
FROM appeared_vs_previous AS a
JOIN metric_series AS s
  ON s.series_id = a.series_id
GROUP BY s.metric_name
ORDER BY appeared_vs_previous_hour DESC;
~~~

This counts **series sampled in the current hour but absent in the previous hour**. A previously existing series resuming activity still appears here. Call this **“appeared relative to prior window”**, **not** “brand-new series created for the first time in history”.

Measuring *first-ever new series* requires tracking first-seen timestamps or reliable series creation logs. The symmetric churn direction—**series disappearing relative to prior window**—flips the two `EXCEPT` inputs.

### 9.6. Measuring Samples per Hour

~~~sql
SELECT
    DATE_TRUNC('hour', sampled_at) AS hour_utc_or_session_zone,
    COUNT(*) AS ingested_samples
FROM metric_samples
WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND sampled_at <  TIMESTAMPTZ '2026-11-02 00:00:00+00'
GROUP BY DATE_TRUNC('hour', sampled_at)
ORDER BY hour_utc_or_session_zone;
~~~

In PostgreSQL, `DATE_TRUNC` on `TIMESTAMPTZ` aligns to the **session timezone**. Standardize timezone and bounds when comparing across systems. Hourly sample counts complement active series counts without replacing distinct label-set counts.

### 9.7. SQL Is a Verification Tool, Not a Mandatory TSDB Architecture

The two-table model highlights:

- Labels need **stable, normalized identifiers** so casing or formatting variations never spawn extra series.
- One `series_id` accumulates many samples over time; **series identity and sample identity differ**.
- **Catalog cardinality**, **active cardinality**, **sample volume**, and **churn** must each be measured separately.

Purpose-built TSDBs use inverted indexes, segments/blocks, compression, and flexible tag storage; base physical choices on actual workloads and engine specs.

## 10. Prioritized Mitigations to Reduce Series Count

### 10.1. Fix at the Metric Emitter

This is usually the highest-leverage point:

- Replace raw URLs with router-normalized `route_template`.
- Replace free-form `error_message` with a finite, review-gated `error_type`.
- Never attach `request_id`, `trace_id`, `session_id`, or `user_id` indiscriminately to metrics.
- Add `tenant_id` only with clear per-tenant requirements and budgeted capacity.
- Avoid dynamic metric names like `orders_for_user_123_total`. Use bounded labels or move per-entity tracking to event stores.
- Keep route, environment, and region naming **consistently normalized** across deployments.

Stopping cardinality bloat at the source spares collection and storage layers from ever handling excess series.

### 10.2. Controls at Ingestion and Storage

Depending on platform capabilities:

- Drop unnecessary labels **before writing** to the metric store.
- Reject or flag metrics/label sets exceeding approved budgets.
- Enforce per-metric, per-service, or per-tenant limits with alerts when samples are dropped.
- Route fine-grained instance metrics to shorter-retention storage while keeping aggregated metrics longer.
- Shorten detailed retention where diagnostics and compliance permit.

**Warning:** dropping a label can **collapse two distinct series onto the remaining label set**. For counters, gauges, and histograms, you cannot drop a label and smash concurrent samples together arbitrarily—define **valid per-metric-kind aggregation rules** or conflict handling. Dropping `instance` also reduces per-node diagnostic visibility.

### 10.3. Pre-Aggregate Before Storage

If you only need error rates by service and route, consider storing a stream **pre-aggregated by service/route/status** rather than retaining fine-grained transactional labels long term.

However:

- For counters, handle **resets** per source series accurately before summing rates.
- For histograms, merge buckets/distributions using engine-supported methods—never average percentiles.
- For gauges, summing/averaging/taking max makes sense only when semantically valid.
- Once `instance` is dropped, per-instance queries can no longer be answered from stored aggregates.

**Running `sum by (...)` on a dashboard only shrinks query output; it never reduces series ingested or stored at the source.**

### 10.4. Misleading “Cardinality Reduction” Tactics

| Approach | Why It Fails to Solve Root Cause |
|---|---|
| Hashing `user_id` into a digest string | Distinct value count stays virtually identical; privacy re-identification risk may persist |
| Arbitrarily truncating IDs | Causes hash collisions and silent data corruption without business rules |
| Limiting rows displayed on dashboards | Shrinks UI output only, not stored series |
| Increasing scrape interval alone | Cuts sample volume, rarely cuts cardinality |
| Shortening retention alone | Shrinks old data window without stopping active-series bloat |
| Using `topk` at query time | Often still scans huge series sets to find top k |
| Moving `request_id` from label into metric name | Still spawns unbounded metric identifiers |
| Collapsing all errors into `status="other"` | Shrinks series while blinding critical error signals; keep useful buckets |

The goal is not merely achieving a small number, but **preserving required observability signals at controlled cost**.

## 11. Verifying Cardinality Before and After Rollout

### Step 1 — Confirm Which Questions Metrics Must Answer

Example: “By service/route, did 5xx error rate over 5 minutes breach the threshold?”. If nobody needs metric error rates broken down by `user_id`, that label cannot be justified.

### Step 2 — Inventory Metrics and Label Sets

Do not take the union of all labels and multiply it across every metric. Each **metric family** carries distinct labels, resolutions, and sample rates. A histogram with `le`, `_sum`, `_count` scales differently from a single-series counter.

### Step 3 — Estimate Upper-Bound Label Combinations

Compute \(C_{\max}\), mark labels as **independent** or **correlated**, estimate growth from any new label, and document churn assumptions.

### Step 4 — Load-Test with Representative Traffic

Monitor **active series**, **samples/sec**, **new series vs. prior window**, RAM, index size, query latency, and scrape failures. Simulate deployments, autoscaling, new tenants, new routes, and traffic bursts.

### Step 5 — Set Budgets and Ownership

Assign every metric family to an owning team with budgets, alerts, and review gates for new labels. Treat a new metric label like a **schema change**, not a harmless one-line code tweak.

### Step 6 — Verify Data Quality After Optimization

Compare pre- and post-change metrics over identical scope:

- Do total requests and total errors still reconcile with authoritative sources?
- Were route/status groups misclassified or SLO labels lost?
- Did dropping a label cause series collisions?
- Did dashboards or alerts shift semantics or lose visibility?
- Are request-level traces/logs still retained with required permissions and retention?

Never declare optimization successful merely because series counts dropped while ignoring **metric correctness**.

## 12. Query and Alerting Examples in a Metric System

In systems supporting **PromQL**-like syntax, request rate by service and route can be written:

~~~promql
sum by (service, route) (
  rate(http_requests_total[5m])
)
~~~

To compute 5xx error ratio relative to total requests per service, separate numerator and denominator over identical scope:

~~~promql
sum by (service) (
  rate(http_requests_total{status_class="5xx"}[5m])
)
/
sum by (service) (
  rate(http_requests_total[5m])
)
~~~

**Preconditions:** `http_requests_total` is a true counter, `status_class` is recorded consistently, selected series do not double-count requests, and the rate window fits sampling cadence. Handle zero denominators cleanly in dashboards/alerts. For resetting counters, compute `rate` on **each individual series before summing**.

### Classic Histograms

Estimating 95th-percentile latency per service from classic buckets:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

Accuracy depends on bucket boundaries, sample counts, and label sets. Never replace this with **the average of per-instance p95s**. Native histograms or other engines use different syntax and aggregation mechanics.

### Query-Time Aggregation Does Not Erase Source Ingestion Cost

Suppose `http_requests_total` carries `request_id`. Even though `sum by (service)` returns only a handful of lines, the engine **still had to ingest and index millions of `request_id` series**. Fix the problem in instrumentation or pre-aggregation pipelines, not merely in dashboard `GROUP BY` clauses.

## 13. Operational Alerts to Monitor

Good monitoring alerts before disks fill up. Track:

| Metric | Meaning | Signal Requiring Investigation |
|---|---|---|
| Active series by metric/service | Series sampled within window | Sudden jump after deployment |
| Historical distinct label sets | Total unique label sets seen in period | Steady climb while active entities stay flat |
| New-vs-previous series | Label sets present now but absent in prior window | Pod churn or runaway dynamic labels |
| Ingested samples/sec | Incoming point rate | Exceeds capacity or spikes cost |
| Label value count | Distinct values of route/tenant/instance... | Unmatched raw routes or new error strings leaking |
| Index / head memory | Resources managing series and label indexes | Growing faster than sample rate |
| Query duration / scanned series | Dashboard and alert evaluation cost | High fan-out from added labels or broad selectors |
| Scrape failures / dropped series | Missing or rejected telemetry | Budget limiters silently dropping signal |
| Series lifetime distribution | How long series live | High proportion of ultra-short-lived series |

Never impose one blanket threshold across every service. Establish **pre-deploy baselines**, infrastructure headroom, alerting needs, and normal operating cycles. Every alert needs an **owner and playbook**: pinpoint the new label, roll back instrumentation, fix route templates, or adjust configs safely.

## 14. Connections to Other Data Models

| Model | Time and Identity Representation | Pitfall to Avoid |
|---|---|---|
| **Tag-based TSDB** | Metric name + label set identifies series; many samples per series | Dynamic IDs in labels causing series explosion |
| **Relational** | `metric_series` holds label-set identity; `metric_samples` holds time/value | Conflating series key with sample key; bloated indexes as combinations grow |
| **Document / event log** | One doc/event per request with rich metadata | Forcing every event attribute into aggregated metric labels |
| **Graph** | Nodes/edges for entities and relationships; timestamps as event properties | Treating every path as a metric series; define query subjects clearly |
| **Columnar analytical warehouse** | Event facts with IDs, dates, dimensions, measures | Fanning out measures on JOINs; align group-by cardinality to grain |

For a platform tracking **millions of IoT sensors**, `device_id` itself is the core time-series identifier—an **intentional high-cardinality design**. Plan capacity, device/time partitioning, retention, downsampling, and targeted queries deliberately.

Conversely, for `service_http_latency`, `user_id` is rarely a valid service-SLO dimension. **Business purpose** dictates whether an identifier belongs in metric labels or event records.

## 15. Common Misconceptions

| Misconception | Why It Is Wrong | Fix |
|---|---|---|
| “Each sample is a series” | One series holds many samples over time | Separate series identity from timestamp/value |
| “Only one high-cardinality label is dangerous” | Multiplying several moderate labels still explodes | Estimate combinations and count distinct label sets |
| “Product of label counts equals active series” | Not every combination ever occurs | Measure active/observed sets; treat product as upper bound |
| “Few active series means no churn” | Labels may rotate rapidly | Measure appearing/disappearing series and lifetimes |
| “Hashing IDs reduces cardinality” | Distinct users still map to distinct hashes | Remove IDs from metrics; use logs/traces/events |
| “`path` is always bounded” | URLs carrying IDs are practically unbounded | Enforce normalized route templates |
| “`sum by (service)` lowers ingest cost” | Query output shrinks while source still stores fine series | Strip labels before storage or pre-aggregate |
| “Lowering scrape interval fixes label explosion” | Cuts sample rate, leaves series count intact | Fix label sets and churn directly |
| “A 10-bucket histogram is 10 total series” | Multiplies across every label set plus sum/count | Multiply series by histogram structure |
| “Dropping `instance` is always safe” | Loses node visibility and risks label-set collisions | Define aggregation semantics and diagnostic needs |
| “`tenant_id` must never be a label” | Some platforms explicitly need per-tenant metrics | Budget and provision capacity deliberately |
| “Using `topk` reduces stored series” | `topk` usually filters query output only | Drop/block at ingest or route to another tier |
| “Metric labels carry no security risk” | Can expose user/customer IDs or parameterized URLs | Enforce access controls, classification, and retention |
| “Fewer series means job done, skip KPI validation” | Dropping labels can mismerge errors or routes | Reconcile metrics before and after changes |

## 16. Practice Exercises with Solutions

### Exercise 1 — Computing Maximum Label Combinations

A metric has 4 `service`s, 3 `environment`s, 2 `region`s, 10 `route`s, and 5 `status_class`es. If every combination can occur, what is the maximum series count?

**Solution:**

\[
4\times3\times2\times10\times5=1,200.
\]

This is an **upper bound** assuming independent combinations, not automatically the active series count.

### Exercise 2 — Adding a Dynamic ID Label

To Exercise 1's metric, add `user_id` with 1,000 values. What is the new upper bound? Can you conclude the system definitely holds that many series?

**Solution:** \(1,200\times1,000=1,200,000\) potential series. **No**, you cannot guarantee exactly 1.2 million series exist, because many combinations never happen. Still, `user_id` introduces severe explosion risk and must be strictly justified if placed on metrics.

### Exercise 3 — Estimating Sample Volume

Suppose 1,200 series remain continuously active, sampled every 15 seconds. How many daily samples arrive if every scrape succeeds?

**Solution:** Each series produces \(86,400/15=5,760\) samples/day. Total:

\[
1,200\times5,760=6,912,000\text{ samples/day}.
\]

Sample count is not series count. Sampling every 60 seconds cuts ideal sample volume fourfold while leaving series count unchanged.

### Exercise 4 — Histograms Have More Series Than Counters

A classic histogram uses those same 1,200 label sets, with 8 bucket series (including `+Inf`), one `_sum`, and one `_count`. How many series exist?

**Solution:** \(1,200\times(8+2)=12,000\) series for this illustrative histogram. Engines using alternative histogram formats must be counted by their actual structure.

### Exercise 5 — Label Value Counts ≠ Label-Set Count

A metric has only `service` and `region`. There are two services `A, B` and two regions `R1, R2`, yet A runs only in R1 and B runs only in R2. What are the observed series count and theoretical upper bound, assuming one series per active pair?

**Solution:** Two observed series: `(A, R1)` and `(B, R2)`. The upper-bound product is \(2\times2=4\). Never report 4 series because `(A, R2)` and `(B, R1)` do not exist.

### Exercise 6 — Choosing Route Templates

A metric emits `path="/orders/12345"`, `path="/orders/12346"`, ... per request. SREs only need error rates by endpoint pattern. How should you redesign it?

**Solution:** Emit `route="/orders/{orderId}"` normalized by the router or registry, paired with a finite `status_class`. Move raw paths and request IDs to logs or traces governed by permissions and retention. Avoid ad-hoc regex URL stripping.

### Exercise 7 — Churn After Every Deployment

A service always runs 20 active pods. Every 15 minutes, all pod IDs rotate to new values. Active series stay flat, yet what issue still arises?

**Solution:** **High churn**: batches of new pod series appear while old ones disappear. Index memory, metadata, and historical lookups bear heavy load even with only 20 concurrent pods. Measure appearing/disappearing series per window, not active series alone.

### Exercise 8 — Does Hashing Cut Cardinality?

A system replaces `user_id="U123"` with `user_hash="e3ab..."` in metric labels, producing one distinct hash per user. Does series count drop meaningfully?

**Solution:** Usually **no**: almost every user still maps to a distinct value. Hashing also does not automatically protect against correlation or re-identification. Remove IDs from aggregated metrics and move per-user lookups to an appropriate data store.

### Exercise 9 — Optimizing Scrape Intervals

A system has 50,000 active series on a 10-second interval. Switching to 30 seconds reduces ideal sample volume by what factor? Does active series count drop threefold?

**Solution:** Ideal sample volume drops **3×** assuming identical active series and collection. Active series count **does not necessarily drop**: every label set can still remain active. Control cardinality separately.

### Exercise 10 — Aggregating Resetting Counters

A team wants service-wide request totals from per-instance counters. Should they sum raw instance counter readings first and take the rate afterward, ignoring instance resets?

**Solution:** Not blindly. Individual counter resets cause abrupt drops in a summed raw counter, distorting rates. In systems like Prometheus, compute **`rate` per individual series first, then `sum` by service**. Test behavior when instances start, stop, and reset.

### Exercise 11 — Counting Series Over Time

Hour 09 sees series `S1, S2, S3`. Hour 10 sees `S2, S3, S4`. What are active series per hour, appeared count vs. prior hour, and disappeared count?

**Solution:** Each hour has **3 active series**. `S4` appeared relative to the prior hour (**1**); `S1` disappeared (**1**). Active count stayed constant while the active label-set membership rotated. This metric alone does not prove `S4` never existed before Hour 09.

### Exercise 12 — Should Tenant Labels Be Banned Outright?

A platform with 300 tenants needs per-tenant SLOs. The team plans to add `tenant_id` to latency metrics across every endpoint, status, and pod without forecasting series counts. What is the right call?

**Solution:** Neither “ban all tenant labels” nor “ship blindly”. Validate per-tenant SLO requirements, current and projected tenant growth, existing labels, histogram buckets, churn, infrastructure capacity, and authorization rules. You may need tenant-aggregated metrics, a dedicated analytical store, or tiered retention—decide from budgets and testing.

## 17. Checklist Before Adding a Label to a Metric

- [ ] Identified the **operational/business question** truly requiring this label.
- [ ] Distinguished **metric series**, **sample**, and **individual event**.
- [ ] Defined **metric name + label set** as series identity.
- [ ] Estimated distinct values per label, including growth over time.
- [ ] Computed **upper-bound combinations** without mistaking them for actual series count.
- [ ] Measured **distinct label sets** per metric and active window rather than multiplying individual `COUNT(DISTINCT)` columns.
- [ ] Evaluated **churn** of pods, instances, sessions, or short-lived tags.
- [ ] Kept request IDs, trace IDs, user IDs, raw URLs, and timestamps out of unbounded aggregate labels.
- [ ] Governed routes, statuses, and error types via **finite normalized catalogs** with fallback rules for unknowns.
- [ ] Accounted for extra series from histogram buckets, `_sum`/`_count`, and related metric families.
- [ ] Projected impacts on **active series, sample rate, RAM, indexes, disk, and query latency**.
- [ ] Documented budgets and metric owners, with checks on new labels and deployments.
- [ ] When dropping/pre-aggregating labels, defined **counter reset, gauge, histogram**, and collision rules.
- [ ] Avoided using hashing, `topk`, or scrape-interval tweaks as substitutes for label design.
- [ ] Preserved detailed traceability in logs, traces, or fact/event stores with proper access control and retention.
- [ ] Verified metrics, alerts, and KPIs/SLOs before and after changes on realistic data.

**Key takeaway:** **one new label can multiply series counts by its domain size; combining several bounded labels can still explode cardinality**. The product of value counts is an upper bound for sizing, while real series load must be measured via **distinct label sets, active windows, and churn**. Keep labels essential for observability, move per-event IDs to the right stores, and verify both cost and metric accuracy before rollout.
