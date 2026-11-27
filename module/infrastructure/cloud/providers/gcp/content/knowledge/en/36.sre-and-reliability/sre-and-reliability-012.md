# Hands-On: Building an SLO Dashboard for a Java API

A Java API can return HTTP 200 most of the time yet still frustrate users with high latency, intermittent error bursts, or a dependency that frequently times out. Infrastructure dashboards show CPU, memory, and instance counts; an SLO dashboard adds a more critical perspective: whether the service is meeting the quality commitments users actually experience, and how much error budget remains to keep releasing changes.

On Google Cloud, Cloud Monitoring provides Service Monitoring (now organized under SLO monitoring documentation) to define Service Level Indicators (SLIs), Service Level Objectives (SLOs), error budgets, and burn-rate alerts. You can surface these indicators on custom dashboards alongside metrics, logs, traces, and incidents so developers, SREs, and on-call engineers share one operational picture.

This lab builds a dashboard for a Java API running on Cloud Run or GKE. The example uses OpenTelemetry to collect request counts and latency, creates a custom service, defines availability and latency SLOs, and places SLO status alongside operational signals on a Cloud Monitoring dashboard.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between SLI, SLO, SLA, and error budget in API operations.
- Select a request-based availability SLI and a latency SLI suited to a Java API.
- Design metrics with metric kinds, value types, and labels compatible with Cloud Monitoring SLOs.
- Instrument a Java application with OpenTelemetry to record request counts, outcomes, and latency.
- Create custom services and SLOs in Cloud Monitoring.
- Build dashboards displaying SLO health, compliance, error budgets, traffic, errors, and latency.
- Create fast-burn and slow-burn alerts to detect rapid error budget consumption.
- Validate telemetry, handle missing metrics, and avoid misleading dashboards.

## 1. Lab Problem Statement and Architecture

Suppose a development team operates the `orders-api` service for creating and querying orders. The API runs on Cloud Run or GKE and receives requests from web applications and internal services. The team wants to track two objectives:

1. **Availability:** at least 99.9% of eligible requests are processed successfully over a 30-day window.
2. **Latency:** at least 99% of eligible requests complete within at most 300 ms over a 30-day window.

These targets are starter examples for the lab. For production adoption, product and SRE teams must pick thresholds grounded in user experience, actual traffic, endpoint behavior, and reliability history.

### Overall Architecture

~~~mermaid
flowchart LR
    A[Client] --> B[Java API: Cloud Run / GKE]
    B --> C[OpenTelemetry SDK]
    C --> D[OTLP]
    D --> E[OpenTelemetry Collector]
    E --> F[Cloud Monitoring metrics]
    B --> G[Structured logs]
    G --> H[Cloud Logging]
    B --> I[Trace spans]
    I --> J[Cloud Trace]
    F --> K[Custom Service and SLO]
    K --> L[SLO dashboard]
    K --> M[Burn-rate alert policies]
    F --> L
    H --> L
    J --> L
    M --> N[Notification channels / on-call]
~~~

Each component plays a distinct role:

| Component | Role in This Lab |
|---|---|
| Java API | Emits requests, response statuses, and latency |
| OpenTelemetry SDK | Collects metrics and traces inside the application |
| OpenTelemetry Collector | Receives OTLP and exports telemetry to Google Cloud |
| Cloud Monitoring | Stores metrics, computes SLIs/SLOs, renders dashboards and alerts |
| Cloud Logging | Stores application logs and error events |
| Cloud Trace | Investigates latency across spans and dependencies |
| Notification channel | Delivers alerts to on-call responders or ticketing systems |

Cloud Monitoring does not automatically infer every SLI from Java code. With a custom service, you must choose metrics and define how good requests, bad requests, and total requests are classified. Accurate application instrumentation is the foundation for dashboards that faithfully reflect service quality.

## 2. Distinguishing SLI, SLO, SLA, and Error Budget

These concepts are related yet hold distinct meanings:

| Concept | Meaning | Example for `orders-api` |
|---|---|---|
| SLI (Service Level Indicator) | Metric measuring actual quality | Ratio of successful requests or ratio of requests under 300 ms |
| SLO (Service Level Objective) | Quantitative target for an SLI over a time span | 99.9% successful requests over 30 days |
| SLA (Service Level Agreement) | Customer commitment, typically with clauses and remedies | Availability commitment with service credit terms |
| Error budget | Allowable shortfall in quality while remaining within SLO | For a 99.9% SLO, up to 0.1% of eligible requests may fail |

An SLI describes how quality is measured; an SLO describes the target to achieve; an SLA is an external commitment carrying contractual consequences. Do not treat an internal SLO as an SLA without matching terms and commitment boundaries.

### Error Budget Formula

Given an SLO goal (G), the error budget fraction is:

$$
B = 1-G
$$

If the SLO is 99.9%:

$$
B = 1-0.999 = 0.001 = 0.1\%
$$

With 1,000,000 eligible requests in the compliance period:

1,000,000 x 0.001 = 1,000 requests

The team can tolerate up to 1,000 bad requests before missing the period's availability target. This budget is counted in requests, not minutes of downtime. For a request-based SLO, actual request volume determines error budget size.

For a 99% latency SLO, 1% of requests may exceed the 300 ms threshold during the period. The latency SLO error budget is tracked separately; never combine it with the availability error budget because the two SLIs measure different quality dimensions.

### Choosing the Compliance Period

Cloud Monitoring supports two evaluation modes:

- **Rolling window:** continuously evaluates over a sliding span, such as the most recent 30 days. As each new day begins, the system recalculates over the preceding 30 days.
- **Calendar period:** evaluates from the start of a calendar interval such as day, week, fortnight, or month. When the period ends, the error budget resets for the next period.

This lab uses a 30-day rolling window so the team continuously monitors recent quality. If an organization requires reporting by fiscal month or contractual cycle, consider a calendar period.

## 3. Designing SLIs for a Java API

Before creating a service in Cloud Monitoring, agree on which requests count toward the SLI and which count as good.

### Defining Eligible Requests

Example for an HTTP API:

- Requests to business routes such as `/v1/orders` or `/v1/orders/{orderId}` are counted.
- Requests to health endpoints, metrics endpoints, and internal probes are excluded from business SLIs.
- Requests rejected due to invalid input data (certain 4xx codes) can be treated as client errors and excluded as bad service requests.
- HTTP 5xx, server-side timeouts, internal processing errors, and HTTP 429 from service throttling can be classified as bad requests.
- Classification rules must be agreed upon across product, backend, and SRE teams. Never alter rules just to make numbers look better.

In this example, eligible requests are classified as:

| Result | outcome | Accounting |
|---|---|---|
| HTTP 2xx | `good` | Good request |
| HTTP 3xx intentionally supported by the API | `good` | Good request if valid API behavior |
| HTTP 4xx caused by client data or permissions | Excluded from request SLI or classified per policy | Do not automatically treat every 4xx as a service failure |
| HTTP 429 due to service rate limits | `bad` | Bad request in this example |
| HTTP 5xx | `bad` | Bad request |
| Timeout or exception before returning a response | `bad` | Bad request |

If you want 4xx responses included in total requests, explicitly decide how to classify them. Crucially, the numerator and denominator metrics must share the exact same eligible-request definition.

### Availability SLI

A request-based availability SLI is computed as:

SLI_availability = good requests / eligible total requests

For a custom service, you can use `TimeSeriesRatio` to filter good and total metrics. Metrics must have kind `DELTA` or `CUMULATIVE`; `GAUGE` cannot be used for request-based SLIs.

### Latency SLI

A latency SLI measures the ratio of requests completing within a time threshold:

SLI_latency = requests with latency <= 300 ms / eligible total requests

For a custom SLI, Cloud Monitoring can use `DistributionCut`: a distribution metric paired with a value range considered good. The metric must have value type `DISTRIBUTION` and metric kind `DELTA` or `CUMULATIVE`.

### Metrics to Collect

A simple metric design:

| Illustrative Metric Type | Kind / Value Type | Labels | Purpose |
|---|---|---|---|
| `custom.googleapis.com/java_api/request_count` | CUMULATIVE / INT64 | `outcome`, `route` | Count eligible requests, separating good and bad |
| `custom.googleapis.com/java_api/request_latency` | CUMULATIVE / DISTRIBUTION | `route` | Measure latency distribution in seconds |

These metric types are illustrative target names. If your Collector or exporter produces different names, inspect the exact metric type in Metrics Explorer and substitute that name into your SLI filters. Always verify the actual metric descriptor after exporting.

### Avoiding Excessive Cardinality

Never put per-request changing values into metric labels:

- Never use `request_id`, `trace_id`, `user_id`, email, order ID, or raw URLs.
- Use route templates like `/v1/orders/{orderId}` rather than paths with real IDs.
- Keep `outcome` to a small, stable set such as `good` and `bad`.
- Add `region`, `service`, or `version` only when needed for analysis and cardinality remains bounded.

High-cardinality metrics inflate time-series counts, costs, and query complexity; they are also unsuitable for SLIs.

## 4. Instrumenting the Java Application with OpenTelemetry

The example below uses the OpenTelemetry API to create a counter and histogram. The app records one data point per eligible request along with that request's latency.

### Initializing Instruments

~~~java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;

public final class ApiMetrics {
    private static final AttributeKey<String> OUTCOME =
        AttributeKey.stringKey("outcome");
    private static final AttributeKey<String> ROUTE =
        AttributeKey.stringKey("route");

    private final LongCounter requestCount;
    private final DoubleHistogram requestLatency;

    public ApiMetrics(Meter meter) {
        this.requestCount = meter.counterBuilder("api.request.count")
            .setDescription("Eligible API requests by outcome")
            .setUnit("{request}")
            .build();

        this.requestLatency = meter.histogramBuilder("api.request.duration")
            .setDescription("Eligible API request duration")
            .setUnit("s")
            .build();
    }

    public void record(
        String routeTemplate,
        int statusCode,
        long elapsedNanos,
        boolean timedOut
    ) {
        // Exclude client 4xx errors from the SLI; 429 still counts as a service-side failure.
        boolean clientError = statusCode >= 400
            && statusCode < 500
            && statusCode != 429;
        if (!timedOut && clientError) {
            return;
        }

        boolean good = !timedOut
            && statusCode >= 200
            && statusCode < 400;

        String outcome = good ? "good" : "bad";

        Attributes requestAttributes = Attributes.of(
            ROUTE, routeTemplate,
            OUTCOME, outcome
        );

        requestCount.add(1, requestAttributes);

        // Latency SLI uses eligible requests only.
        requestLatency.record(
            elapsedNanos / 1_000_000_000.0,
            Attributes.of(ROUTE, routeTemplate)
        );
    }
}
~~~

This snippet illustrates how to structure instruments and classify requests. In a real application, call `record` where the final outcome of the request is known, including timeouts and exceptions. Never double-record metrics when a request is retried or passes through multiple filters/interceptors.

In this example, client 4xx responses (excluding 429) are omitted from the SLI; 429, 5xx, and timeouts are recorded as `bad`. If your team's policy includes all 4xx responses in the denominator, remove the early `return` branch and align good/bad criteria with product owners.

### Exporting Telemetry to Google Cloud

Use an OpenTelemetry Collector to receive OTLP from the Java SDK and export metrics and traces to Google Cloud. In environments supporting a Collector, Google recommends a collector-based architecture to decouple instrumentation from the destination backend.

General steps:

1. Initialize the OpenTelemetry SDK in the Java app.
2. Configure the OTLP exporter targeting the Collector.
3. Configure the Collector to receive OTLP and export metrics/traces to Google Cloud.
4. Grant telemetry write permissions to the service account running the Collector or workload.
5. Verify metrics and traces appear in the right project.
6. Inspect the metric descriptor to verify metric kind, value type, resource type, and labels.

When using the Google-Built OpenTelemetry Collector or Telemetry API, metric names and resource mappings depend on exporter configuration. Never assume instrument name `api.request.count` automatically becomes `custom.googleapis.com/java_api/request_count`. Check the actual metric type before creating SLIs.

### Enabling APIs and Granting IAM

In the project hosting the workload or telemetry destination, enable the required APIs:

~~~bash
gcloud services enable \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  telemetry.googleapis.com \
  --project=PROJECT_ID
~~~

Reference roles:

| Identity | Role | Purpose |
|---|---|---|
| Service account writing metrics | `roles/monitoring.metricWriter` | Write metrics to Cloud Monitoring |
| Service account writing logs | `roles/logging.logWriter` | Write application logs |
| Service account writing traces via Telemetry API | `roles/telemetry.tracesWriter` | Write traces |
| Service/SLO/dashboard creator | `roles/monitoring.editor` | Manage Monitoring and SLOs |
| Dashboard viewer | `roles/monitoring.viewer` | View metrics and dashboards |
| Trace investigator | `roles/cloudtrace.user` | Access traces per granted permissions |

If using a quota project for telemetry, the identity may need `roles/serviceusage.serviceUsageConsumer` on that quota project. For production, grant roles to workload/Collector service accounts rather than personal user credentials.

## 5. Verifying Metrics Before Creating SLOs

Never create an SLO while metrics still have no data or the wrong schema.

### Checking in Metrics Explorer

1. Open Monitoring > Metrics Explorer.
2. Select the request count metric exported by the Java app or Collector.
3. Check the metric type and monitored resource type.
4. Confirm data points arrive over time and `outcome` and `route` labels carry expected values.
5. Filter `outcome="good"` to verify the numerator has data.
6. Verify total requests include both good and bad outcomes.
7. Select the latency distribution and view distributions by route.
8. Confirm units are seconds and the histogram excludes requests outside SLO eligibility.

### Checking the Metric Descriptor

For request-based SLIs, metrics require `CUMULATIVE` or `DELTA`; value type must be `INT64` or `DOUBLE`. For distribution-cut latency SLIs, metrics require value type `DISTRIBUTION` and kind `CUMULATIVE` or `DELTA`. Specifically for user-defined metrics under `custom.googleapis.com`, use `GAUGE` or `CUMULATIVE`; this example uses `CUMULATIVE` for both the counter and histogram.

If a metric is currently `GAUGE`, it cannot be used directly for a request-based SLI. Update instrumentation/exporting to represent request counts as an appropriate cumulative or delta counter.

### Illustrative SLI Filters

Suppose the actual metric descriptor matches the sample names and the resource type is `cloud_run_revision`.

Good requests filter:

~~~text
metric.type="custom.googleapis.com/java_api/request_count"
AND resource.type="cloud_run_revision"
AND metric.label.outcome="good"
~~~

Total requests filter:

~~~text
metric.type="custom.googleapis.com/java_api/request_count"
AND resource.type="cloud_run_revision"
~~~

Latency distribution filter:

~~~text
metric.type="custom.googleapis.com/java_api/request_latency"
AND resource.type="cloud_run_revision"
~~~

If the API runs on GKE, Compute Engine, or another resource type, replace `resource.type` with the actual monitored resource and ensure both numerator and denominator select the exact same request set.

## 6. Creating a Custom Service and SLOs in Cloud Monitoring

For a custom service, Cloud Monitoring has no built-in predefined SLO matching your API. You must create the service, pick metrics for SLIs, and define targets.

### Creating a Custom Service

1. Open Google Cloud Console and select the project holding telemetry.
2. Go to Monitoring > Services or SLO monitoring.
3. Open Services Overview.
4. Click Define service.
5. Choose custom service if the API was not auto-discovered.
6. Set display name to `orders-api`.
7. Choose the resource or scope matching the workload; for Cloud Run, verify the revisions belonging to the service being monitored.
8. Save the service.

The service name is a logical identifier grouping SLOs and dashboards. If an API has multiple versions or deployment regions, decide whether they share one service or separate services based on team ownership and how error budgets should be tracked.

### Creating the Availability SLO

1. Open the `orders-api` service.
2. Click Create SLO.
3. In the Set your SLI step, select metric type `Other` because custom services require custom SLIs.
4. Choose Request-based evaluation.
5. Choose Time-series ratio indicator.
6. Set the good numerator using the `outcome="good"` filter.
7. Set the total denominator using the total requests filter.
8. Inspect the preview to verify the ratio lies between 0 and 1 and shows data.
9. Set compliance period to Rolling window 30 days.
10. Set performance goal to 99.9% (0.999).
11. Name the SLO `Availability 99.9% - 30d`.
12. Review and click Create SLO.

A request-based SLI computes good requests divided by eligible total requests. `TimeSeriesRatio` requires specifying exactly two of the three fields `good`, `bad`, and `total`; when `good` and `total` are supplied, Cloud Monitoring derives `bad` from their relationship.

### Creating the Latency SLO

Repeat the SLO creation workflow on the same service:

1. Select metric type `Other`.
2. Choose Request-based evaluation.
3. Choose Distribution-cut indicator.
4. Select the latency distribution metric.
5. Set the range to `min=0`, `max=0.3` (seconds).
6. Set compliance period to Rolling window 30 days.
7. Set performance goal to 99% (0.99).
8. Name it `Latency under 300ms - 99% - 30d`.
9. Review the preview and save.

`DistributionCut` counts observations inside the distribution that fall within the range considered good. In this example, requests with latency at or below 300 ms count as good. Verify your metric's units before setting the range; if recorded in milliseconds, the upper bound must be 300 rather than 0.3.

### Example SLO Resource via the API

After creating the service, you can use the Cloud Monitoring API to create SLOs. The body below defines the availability SLO; replace metric types and resource types with values verified in Metrics Explorer:

~~~json
{
  "displayName": "Availability 99.9% - 30d",
  "goal": 0.999,
  "rollingPeriod": "2592000s",
  "serviceLevelIndicator": {
    "requestBased": {
      "goodTotalRatio": {
        "goodServiceFilter": "metric.type=\"custom.googleapis.com/java_api/request_count\" AND resource.type=\"cloud_run_revision\" AND metric.label.outcome=\"good\"",
        "totalServiceFilter": "metric.type=\"custom.googleapis.com/java_api/request_count\" AND resource.type=\"cloud_run_revision\""
      }
    }
  }
}
~~~

Send the request to the resource path:

~~~bash
ACCESS_TOKEN=$(gcloud auth print-access-token)

curl -X POST \
  "https://monitoring.googleapis.com/v3/projects/PROJECT_ID/services/SERVICE_ID/serviceLevelObjectives" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @availability-slo.json
~~~

For the latency SLO, the `serviceLevelIndicator` block can use this structure:

~~~json
{
  "serviceLevelIndicator": {
    "requestBased": {
      "distributionCut": {
        "distributionFilter": "metric.type=\"custom.googleapis.com/java_api/request_latency\" AND resource.type=\"cloud_run_revision\"",
        "range": {
          "min": 0,
          "max": 0.3
        }
      }
    }
  }
}
~~~

In the SLO API, `rollingPeriod` must be an integer multiple of one day and cannot exceed 30 days. `goal` is a ratio greater than 0 up to 0.9999. For instance, 99.9% is represented as 0.999.

## 7. Creating an SLO Dashboard in Cloud Monitoring

A dashboard should quickly answer four questions:

1. Is the API currently meeting its SLO targets?
2. How much error budget remains?
3. Which signal is degrading quality: traffic, errors, or latency?
4. Which logs, traces, or incidents should the on-call engineer open to investigate?

### Recommended Dashboard Layout

| Position | Widget | Content | Purpose |
|---|---|---|---|
| Row 1 | SLO health | Availability and latency health | Quick view of target status |
| Row 1 | Error budget | Remaining budget as % or absolute value | Gauge release risk level |
| Row 2 | Request volume | Total, good, and bad requests over time | Spot traffic shifts and errors |
| Row 2 | Latency | Latency distribution or p50/p95/p99 | Identify API slowdowns |
| Row 3 | Burn-rate alerts | Open alerts and budget burn speed | Prioritize response |
| Row 3 | Logs / traces | ERROR logs and correlated traces | Pinpoint root cause |

### Adding SLO Widgets

1. Open Monitoring > Dashboards.
2. Click Create dashboard.
3. Name it `orders-api-slo-dashboard`.
4. Click Add widget.
5. Select the SLO widget type.
6. Select service `orders-api`.
7. Select SLO `Availability 99.9% - 30d`.
8. Choose chart type Health or Compliance.
9. Add another SLO widget for `Latency under 300ms - 99% - 30d`.
10. Add widgets showing absolute or fractional remaining error budget for each SLO.
11. Apply and save the dashboard.

SLO widgets display SLO health, compliance, and error budgets. A dashboard can hold multiple widgets, up to 100 widgets. Dashboard SLO widgets support Google Cloud projects; with App Hub configurations, select the appropriate host project or management project.

### Adding Metric Charts

Add standard charts to explain root causes:

**Request volume**

- Metric: `custom.googleapis.com/java_api/request_count`.
- Group by: `outcome` or `route`.
- Because the counter is `CUMULATIVE`, use `ALIGN_DELTA` to show requests per interval or `ALIGN_RATE` to show requests/second; never chart raw cumulative values directly.
- Display both good and bad counts alongside traffic.

**Latency**

- Metric: `custom.googleapis.com/java_api/request_latency`.
- Convert the cumulative distribution into per-interval deltas (such as `ALIGN_DELTA`), then choose an appropriate distribution/percentile view.
- Group by route template.
- Mark the 300 ms threshold line to spot endpoints breaching the target.

**Error rate**

- Use good and total requests to display good or bad ratios.
- If charting error ratio, verify the numerator is bad requests and the denominator is total requests.
- Avoid averaging percentages across routes without weighting by request volume.

**Application logs**

- Add a logs widget or link to Logs Explorer.
- Filter logs by service, `ERROR` severity, and incident timeframe.
- Ensure logs include trace IDs to pivot straight to Cloud Trace.

**Trace data**

- Add a trace widget or link to Trace Explorer.
- Use traces to inspect API spans and slow dependencies.
- Compare total request latency against time spent in each dependency.

### Dashboard Variables and Filters

If the API spans multiple routes or regions, create dashboard filters for `route`, `location`, or `service_name`. Viewers can focus on affected endpoints without maintaining separate dashboards per route.

Never use request IDs or user IDs as dashboard variables. They are not stable analytical dimensions and can drive huge cardinality growth.

### Distinguishing Dashboard Time Range from SLO Compliance Period

The dashboard time range controls the span displayed by metric, log, and trace charts. By contrast, SLO widgets render SLOs over their configured compliance period, such as a rolling 30 days. Thus, when viewing the last 1 hour on the dashboard, the SLO widget may still evaluate over rolling 30 days. Document this clearly in the dashboard description so viewers do not confuse the two time spans.

## 8. Creating Error-Budget Burn-Rate Alerts

An SLO dashboard shows remaining budget; burn-rate alerts detect abnormal budget consumption speeds before the SLO is breached.

Burn rate is normalized against the sustainable consumption pace. A burn rate of 1 means the service is consuming its budget at exactly the pace that depletes it at the end of the compliance period. A burn rate greater than 1 indicates that if the current error rate persists for the period, the service will breach its SLO.

### Fast Burn vs. Slow Burn

| Alert Type | Reference Lookback | Reference Threshold | Meaning |
|---|---:|---:|---|
| Fast burn | 1–2 hours | 10x | Sharp error spike threatening to consume the entire budget rapidly |
| Slow burn | 24 hours | 2x | Prolonged quality degradation that could exhaust the budget before period end |

The 10x and 2x figures are starting points for tuning, not mandatory thresholds for every API. Low traffic and hourly fluctuations can make burn rates noisier; examine request counts, impact severity, and sustain durations before finalizing thresholds.

### Creating Alerts from the UI

1. Open Monitoring > Services Overview.
2. Select service `orders-api`.
3. Under Current status, locate the availability SLO.
4. Click Create SLO alert.
5. Set lookback duration to 1 hour and burn-rate threshold to 10 for fast burn.
6. Select the on-call team's notification channel.
7. Write documentation covering symptom, dashboard link, log query, and runbook.
8. Save the policy.
9. Create a second policy with a 24-hour lookback and threshold 2 for slow burn.

Cloud Monitoring offers suggested values when creating an alert from a specific SLO. Review lookback, threshold, and notification channels before saving.

### Example Condition via Cloud Monitoring API

SLO burn-rate alerts use the `select_slo_burn_rate` time-series selector. The example below creates a fast-burn condition for the availability SLO:

~~~json
{
  "displayName": "orders-api availability fast burn",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "Availability SLO burn rate above 10 over 1 hour",
      "conditionThreshold": {
        "filter": "select_slo_burn_rate(\"projects/PROJECT_ID/services/SERVICE_ID/serviceLevelObjectives/AVAILABILITY_SLO_ID\", \"60m\")",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 10,
        "duration": "0s"
      }
    }
  ],
  "notificationChannels": [
    "projects/PROJECT_ID/notificationChannels/CHANNEL_ID"
  ],
  "documentation": {
    "mimeType": "text/markdown",
    "content": "orders-api is consuming its availability error budget at more than 10x the sustainable rate. Check the SLO dashboard, recent releases, HTTP 5xx, dependency latency, and traces. Follow the incident runbook."
  }
}
~~~

Replace `PROJECT_ID`, `SERVICE_ID`, `AVAILABILITY_SLO_ID`, and `CHANNEL_ID` with actual resource names. A slow-burn policy uses the same selector with lookback `24h` and threshold `2`.

Cloud Monitoring does not support querying burn-rate alerts with a compliance period longer than 24 hours. Therefore, even when the target SLO uses a 30-day rolling window, alerts use shorter lookbacks for operational responsiveness. This does not alter the SLO's compliance period; it only defines the window used to compute burn rate for the alert.

## 9. Reading the Dashboard and Handling Scenarios

When the dashboard indicates the availability SLO is dropping, combine SLO widgets with traffic, errors, logs, and traces.

### Scenario A: Rapid Drop in Availability

Symptoms:

- SLO health turns unhealthy.
- Remaining error budget drops quickly.
- Request volume holds steady while bad requests climb.
- Fast-burn alert fires.

Investigation steps:

1. Identify affected routes and regions.
2. Compare error onset against the latest deployment timestamp.
3. Filter Cloud Logging by `ERROR` severity and service.
4. Open sample traces to determine whether failures occur in API handlers or dependencies.
5. Check Cloud SQL, Pub/Sub, or downstream services if spans show timeouts.
6. If linked to a release, roll back per the approved runbook.
7. Monitor SLIs and burn rate after remediation.

### Scenario B: Latency SLO Drops While Availability Stays Healthy

Symptoms:

- Availability SLO continues meeting its target.
- Latency SLO declines.
- p95/p99 climb without a major spike in HTTP 5xx.
- Latency error budget is burning.

Investigation steps:

1. Identify which route has the highest p95/p99.
2. Compare request latency against span durations for each dependency.
3. Inspect connection pools, database queries, cache misses, and external APIs.
4. Check workload CPU, memory, instance counts, and concurrency.
5. Check for payload or response size changes.
6. Evaluate code, query, or capacity optimizations before simply scaling up resources.

### Scenario C: Dashboard Shows No Data

Symptoms:

- SLO widget shows no data or preview lacks history.
- Metric charts are empty.
- Service was newly created or workload was just deployed.

Investigation steps:

1. Verify the service account holds the Monitoring Metric Writer role.
2. Confirm the Collector is exporting telemetry without export errors.
3. Check project ID, monitored resource, and metric types.
4. Confirm both numerator and denominator have active time series.
5. Check whether metric kind and value type match SLI requirements.
6. Wait for newly ingested data, then refresh Metrics Explorer and SLO preview.
7. Check whether route/outcome filters are excluding all data.

A newly created service can define SLOs before historical data exists, though preview charts will lack past data. Dashboards should clearly indicate missing data rather than assuming 100% attainment.

## 10. End-to-End Verification Workflow

Execute this in a test project or staging environment before promoting the dashboard to production.

### Step 1: Generate Valid Traffic

Send requests to several API routes:

~~~bash
curl -i https://YOUR_API_HOST/health
curl -i https://YOUR_API_HOST/v1/orders
~~~

Health endpoints should stay excluded from business request SLIs. Send valid business requests alongside controlled error test cases in staging to generate both `good` and `bad` outcomes.

### Step 2: Verify Metrics

In Metrics Explorer, confirm:

- Request counter increments as the API receives requests.
- `outcome` label contains both `good` and `bad` after running test scenarios.
- Latency distribution shows data with the right units.
- `route` label uses templates without real IDs.
- Metric descriptors have valid kinds and value types.

### Step 3: Verify SLOs

Open service details and inspect each SLO:

- Availability SLI has valid numerator and denominator series.
- Latency SLI uses the distribution metric and 300 ms range.
- Goals match 99.9% and 99%.
- Compliance period is rolling 30 days.
- Preview charts update as fresh data arrives.

### Step 4: Verify the Dashboard

- SLO widgets display the right service and SLOs.
- Error budget accurately reflects remaining percentage.
- Request chart distinguishes good and bad requests.
- Latency chart shows distribution and threshold line.
- Logs/traces enable drilling deeper into investigations.
- Time range and compliance period are clearly documented.

### Step 5: Test Alerts

Never cause a production outage intentionally to test burn-rate alerts. Use staging or a test policy against controlled metrics. Confirm notifications reach the right channel and include the runbook.

### Step 6: Record Configuration and Ownership

Document:

- Service owner and on-call rotation.
- Eligible request definition.
- Metric types and labels used as SLIs.
- SLO goals and compliance periods.
- Dashboard link.
- Fast/slow burn policies and notification channels.
- Next scheduled target review date.

## 11. Common Pitfalls When Building SLO Dashboards

| Symptom | Possible Cause | Remedy |
|---|---|---|
| Cannot select metric for request-based SLI | Metric is `GAUGE` or invalid value type | Under `custom.googleapis.com`, use a `CUMULATIVE` `INT64` counter; use `DELTA` only when supported by the source |
| Availability SLI stays near 100% | Bad requests are not recorded or numerator filter is too broad | Inspect outcome classification and numerator/denominator filters |
| Error budget drops unexpectedly | 4xx, health checks, or probes are counted in request SLIs | Review eligibility and classification policy |
| Latency SLO has no data | Histogram is not `DISTRIBUTION` or metric kind is unsupported | Check metric descriptor and exporter config |
| Latency SLI stays consistently low | Units mismatch the range threshold | Standardize seconds/milliseconds and fix the range |
| SLO preview lacks history | Newly created service or metrics not yet ingested | Check Collector and wait for ingestion |
| Dashboard fails to show SLO | Missing service/SLO or wrong project selected | Create the SLO and select the right project/service |
| Dashboard has many charts but is hard to read | Mixed units or missing filters | Split charts, group by route, and label units clearly |
| Burn-rate alert never triggers | Wrong lookback/filter or missing data | Verify SLO resource name and selector |
| Burn-rate alert is too noisy at low traffic | Low threshold or spiky traffic | Combine fast/slow burn, check request volume, and tune |
| Metric cardinality explodes | Labels contain request IDs, user IDs, or raw URLs | Switch to route templates and bounded labels |
| SLO fails to reflect user experience | Measures status codes only, ignoring latency or dependencies | Maintain separate availability and latency SLOs |

## 12. Best Practices and SLO Governance

- **Pick targets from user experience:** avoid choosing 99.99% merely because it sounds impressive; weigh operational capacity and cost.
- **Define eligibility clearly:** document which requests count and how 4xx, 429, timeouts, retries, and health checks are handled.
- **Separate SLIs by quality dimension:** availability and latency should have distinct SLOs so error budgets remain meaningful.
- **Measure real requests:** use application counters and histograms rather than substituting CPU or instance counts for API quality.
- **Control cardinality:** restrict labels to necessary route templates, outcomes, regions, or services.
- **Alert on burn rate:** use fast burn to catch major outages and slow burn to spot prolonged degradation.
- **Assign owners to every SLO:** every target needs an accountable team, dashboard, and runbook.
- **Use error budgets in release decisions:** when budget burns quickly, prioritize reliability work before continuing risky changes.
- **Never treat dashboards as sole truth:** cross-check metrics, logs, traces, and client-side telemetry.
- **Review periodically:** adjust targets as user behavior, traffic, and API architecture evolve.
- **Protect telemetry:** keep personal data, tokens, sensitive URLs, and order details out of metric labels and uncontrolled logs.

## Conclusion

An SLO dashboard shows operations teams how well an API meets quality targets and how much error budget remains. For a Java API, accurate instrumentation is the foundation: a request counter separating good/bad outcomes, a latency distribution with clear units, and low-cardinality labels.

Cloud Monitoring consumes those metrics to power custom services, request-based availability SLOs, and latency SLOs. SLO widgets surface health, compliance, and error budgets, while metric, log, and trace charts explain underlying causes. Fast-burn and slow-burn alerts notify on-call responders before the budget runs dry. When backed by clear ownership, consistent SLI definitions, and actionable runbooks, the dashboard becomes a practical tool for guiding release decisions and improving API reliability.

## References

- [SLO monitoring overview](https://cloud.google.com/monitoring/slo-monitoring)
- [Creating an SLO](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-slo)
- [Creating a service-level indicator](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/identifying-custom-sli)
- [Cloud Monitoring ServiceLevelObjective API](https://cloud.google.com/monitoring/api/ref_v3/rest/v3/services.serviceLevelObjectives)
- [Display SLOs on a custom dashboard](https://cloud.google.com/monitoring/dashboards/slos)
- [Alerting on your burn rate](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate)
- [Create an SLO alerting policy](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-alert)
- [Working with the SLO API](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/using-api)
- [Java instrumentation sample with OpenTelemetry](https://cloud.google.com/trace/docs/setup/java-ot)
- [Enable telemetry signals in Cloud Client Libraries for Java](https://cloud.google.com/java/docs/observability)
- [User-defined metrics overview](https://cloud.google.com/monitoring/custom-metrics)
- [Value types and metric kinds](https://cloud.google.com/monitoring/api/v3/kinds-and-types)
- [Create and manage dashboards by API](https://cloud.google.com/monitoring/dashboards/api-dashboard)
