# Cloud Monitoring Metrics, Resource Labels, and Dashboards

When a Java application runs on Google Cloud, logs tell you which events occurred, while metrics show how the system is behaving over time. Steadily rising CPU, request latency crossing thresholds, changing instance counts, or growing queues are all signals that must be measured and tracked. Cloud Monitoring collects those measurements as time series, associates them with the originating resources, and provides tools for querying, visualization, dashboards, and alerting.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module. The module guides learners through Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners practice selecting services, protecting resources, automating releases, and monitoring reliability and cost. Within the scope of this lesson, we focus on Cloud Monitoring, the metric model, resource labels, creating application metrics, and building dashboards to observe services.

## Objectives

After this lesson, you will be able to:

- Explain metric types, monitored resources, time series, and data points.
- Distinguish between metric labels, resource labels, and resource metadata labels.
- Identify GAUGE, DELTA, and CUMULATIVE metric kinds and value types.
- Select built-in metrics or design custom metrics for an application.
- Use Metrics Explorer to filter, group, and aggregate time series.
- Build dashboards focused on service health and user experience.
- Control cardinality, access permissions, and metric collection costs.

## 1. Cloud Monitoring and the Role of Metrics

Cloud Monitoring is Google Cloud's observability service for collecting, querying, and displaying metrics from Google Cloud resources, custom applications, and certain external platforms. A metric is a measurement of an attribute over time, such as:

- CPU utilization of a VM.
- Number of requests handled by a Cloud Run service.
- API request latency.
- Amount of memory or disk space currently in use.
- Number of messages waiting in a queue.
- Number of orders created or payment failures.

Metrics complement logs and traces:

| Telemetry Type | Questions Answered | Example |
|---|---|---|
| Metrics | What is changing and by how much? | Error rate rose to 8% over 5 minutes |
| Logs | What specific event occurred? | Request for order ord-1042 failed due to upstream timeout |
| Traces | Which components did a request pass through and where did it slow down? | Span calling payment-provider took 2.4 seconds |

Metrics are suited for observing trends, comparing against thresholds, and detecting anomalies. Logs provide context for individual events; traces follow the request's execution path. Combining all three data types allows operations teams to spot an issue from metrics, find related events in logs, and pinpoint the slow component via traces.

### Common Metric Sources

- **Google Cloud metrics:** automatically produced by services, such as Compute Engine CPU or Cloud Run request count.
- **Agent or integration metrics:** collected from the OS, containers, applications, and third-party software.
- **Custom metrics:** defined by applications or users to measure workload-specific data.
- **Prometheus and OpenTelemetry metrics:** collected through respective integrations and ingested into the observability system.
- **Log-based metrics:** derived from log entries in Cloud Logging; these originate from logs rather than metrics written directly by an application via the Monitoring API.

There is no need to create custom metrics for everything. Check built-in metrics first, then supplement only with business or technical measurements that standard metrics do not capture.

## 2. The Metric Model: Metric Type, Resource, and Time Series

Cloud Monitoring organizes data into **time series**. Each time series contains timestamped data points, describes the metric being measured, and identifies the monitored resource producing the measurement.

~~~mermaid
flowchart TD
    A["Metric descriptor<br/>metric type, kind, value type, unit"]
    B["Metric labels<br/>categorize measurements"]
    C["Monitored resource<br/>resource type and resource labels"]
    D["Data points<br/>values and timestamps"]
    E["Time series"]
    A --> E
    B --> E
    C --> E
    D --> E
~~~

For example, CPU utilization may have the metric type **compute.googleapis.com/instance/cpu/utilization**. The monitored resource is a VM with resource type **gce_instance**. Data points record CPU levels at each point in time. If a project has multiple VMs, each VM has its own time series.

A time series is uniquely identified by its metric type, metric label values, and monitored resource along with its resource label values. Therefore, a single metric type can produce many time series when recorded across multiple resources or distinct label combinations.

### Metric Descriptor

A metric descriptor is the definition of a metric type. The descriptor specifies:

- **type:** unique identifier of the metric, such as compute.googleapis.com/instance/cpu/utilization.
- **metricKind:** whether the measurement is GAUGE, DELTA, or CUMULATIVE.
- **valueType:** data type of the value, such as DOUBLE or INT64.
- **unit:** unit of measurement, such as %, s, By, or {request}.
- **labels:** classification dimensions belonging to the metric type.
- **displayName** and **description:** metadata helping operators understand the metric.

Built-in metric types are defined by Google Cloud services. For custom metrics, development teams design descriptors so services, dashboards, and alerts share a consistent measurement meaning.

### Metric Kind and Value Type

Metric kind describes the relationship between consecutive measurements:

| Metric Kind | Meaning | Examples |
|---|---|---|
| GAUGE | Value at a point in time | Open connections, queue depth, CPU utilization |
| DELTA | Change over a time interval | Number of requests generated in 1 minute |
| CUMULATIVE | Running total accumulating from a start time | Total bytes sent since the process started |

Value type describes the data type:

| Value Type | Data | Examples |
|---|---|---|
| BOOL | True/false | On/off state |
| INT64 | 64-bit integer | Request count, items in queue |
| DOUBLE | Floating-point number | CPU utilization, latency |
| DISTRIBUTION | Distribution of multiple values | Request latency histogram |
| STRING | String in certain built-in metrics or external sources | Not supported for custom metrics |

Choose metric kind according to actual semantics. Queue depth is GAUGE because it can rise or fall at each sample. Requests occurring during an interval are typically DELTA. Total requests since process start are CUMULATIVE. Choosing the wrong kind can cause rate, delta, or aggregation calculations in charts to yield misleading conclusions.

Note when defining custom metrics: the general Cloud Monitoring model includes GAUGE, DELTA, and CUMULATIVE, but not every kind/value type combination is allowed for custom metrics. For metrics prefixed with custom.googleapis.com, the DELTA kind is not supported; STRING is also unsupported for custom metrics. The example in this lesson uses GAUGE and INT64, fitting direct time series writes via the Monitoring API. Cumulative metrics may need conversion via an appropriate alignment/aggregation before charting or alerting.

For latency, do not record only a single average if tail latency matters. Distribution metrics or histograms preserve distribution information so percentiles such as P50, P95, and P99 can be analyzed. A low average can easily hide a subset of very slow requests.

## 3. Resource Labels and Metric Labels

These are two distinct label groups that jointly identify a time series.

**Resource labels** describe the origin of the data: project, location, VM, cluster, pod, or service. Valid labels depend on the monitored resource type.

**Metric labels** describe the measurement itself: method, response code, operation type, or outcome. Valid labels are defined in the metric descriptor.

For example, a metric counting requests for a Cloud Storage bucket may have metric labels **method** and **response_code**, while the monitored resource **gcs_bucket** has resource labels **project_id**, **bucket_name**, and **location**. This lets operators break down requests by method and response code while identifying which bucket and region handled those requests.

### Examples of Resource Types and Resource Labels

| Source | Monitored Resource Type | Common Resource Labels |
|---|---|---|
| Compute Engine VM | gce_instance | project_id, instance_id, zone |
| GKE container | k8s_container | project_id, location, cluster_name, namespace_name, pod_name, container_name |
| Cloud Run revision | cloud_run_revision | project_id, location, service_name, revision_name, configuration_name |
| Cloud Storage bucket | gcs_bucket | project_id, bucket_name, location |

The exact label list depends on each resource type's descriptor and can vary by service. When writing filters or custom metrics, consult the corresponding descriptor rather than guessing label names.

### Resource Metadata Labels

Beyond required labels defined by the monitored resource type, Cloud Monitoring also provides resource metadata labels. Some metadata labels are system-supplied read-only fields; some resources allow users to attach metadata labels during resource configuration.

Metadata labels are useful for categorizing and filtering data in queries. However, they may be populated asynchronously and do not carry the same latency guarantees as labels defined directly in the monitored resource type or metric descriptor. Therefore, do not rely on metadata labels to trigger sensitive alerts or automated actions such as autoscaling. For high-reliability reactive conditions, use officially defined labels of the resource or metric type.

## 4. Cardinality: Why Label Design Matters

Cardinality is the number of label value combinations that can generate distinct time series. Each combination of metric labels and resource labels can become a separate time series. When a label's value space grows rapidly, the number of time series and the volume of data to store and query increase accordingly.

Suppose a metric has:

- 3 environments: dev, staging, production.
- 4 regions.
- 5 outcome types.
- 2 payment methods.

The maximum number of combinations is:

\[
3 \times 4 \times 5 \times 2 = 120
\]

Adding customerId with hundreds of thousands of values causes time series counts to explode. Adding request ID, order ID, or session ID makes nearly every event spawn a separate time series.

### What Should and Should Not Be Used as Labels

| Attribute | Recommendation | Reason |
|---|---|---|
| environment | Recommended | Small, stable set of values |
| region | Recommended | Bounded set of regions |
| status_class | Recommended | For example: 2xx, 4xx, 5xx |
| payment_method | Acceptable | Provided the set of methods is controlled |
| route | Use route template | /orders/{orderId} has much lower cardinality than full URLs |
| customerId | Not recommended | Large, continuously changing value set |
| orderId | Not recommended | Every order can create a new series |
| requestId or traceId | Not recommended | Nearly unique value per request |
| URL with query string | Not recommended | Can contain dynamic and sensitive data |
| timestamp or free-form error text | Not recommended | Generates excessive distinct values |

Identifiers such as customerId, orderId, and requestId belong in logs or traces, where queries target individual events. Metrics should stick to classification dimensions with bounded value sets.

Cardinality depends not only on the number of labels, but also on how many values each label can take and their cross-product. Estimate cardinality before releasing a custom metric, then monitor Metrics Management to spot metrics with unexpectedly growing time series counts.

## 5. Choosing Built-In Metrics for Cloud Run, GKE, and Compute Engine

Before creating a new metric, check Metrics Explorer or the Metrics list to see whether the service already exposes a suitable measurement.

Commonly tracked metric groups:

| Platform | Metrics to Monitor | Purpose |
|---|---|---|
| Cloud Run | Request count | Measure request traffic |
| Cloud Run | Request latency | Track processing time and tail latency |
| Cloud Run | Instance count | Track active serving instances |
| Cloud Run | Container CPU and memory utilization | Detect resource limits |
| Compute Engine | CPU utilization | Detect overloaded or idle VMs |
| Compute Engine | Disk bytes and disk utilization | Monitor storage capacity |
| GKE | Container CPU and memory | Monitor workload resources |
| GKE | Pod/container restarts or status | Detect unstable workloads |

Exact metric type names, labels, and units can differ by resource type and integration version. When writing filters, pick metrics in Metrics Explorer or consult the Metrics list to confirm exact names and corresponding monitored resources.

### Selecting Metrics by Goal

- To tell if traffic is rising or falling, monitor request count or throughput.
- To tell if users are encountering errors, monitor error count or error ratio.
- To tell if the service is responding slowly, monitor latency distribution and percentiles.
- To tell if resources are constrained, monitor CPU, memory, disk, and instance count.
- To tell if background processing is keeping up, monitor queue depth, oldest message age, and processing rate.

A single metric is rarely enough to draw a conclusion. For instance, high CPU might stem from normal traffic growth or from a tight error loop. Combine request count, latency, error rate, and resource utilization to understand root cause.

## 6. Creating Custom Metrics for a Java Application

Custom metrics measure application-specific data that built-in metrics do not expose, such as successfully created orders, pending jobs, or duration of a business step.

Google recommends using open, vendor-neutral instrumentation frameworks such as **OpenTelemetry** for new applications. OpenTelemetry provides measurement APIs and forwards data via appropriate exporters or collectors. If direct integration with the Cloud Monitoring API is needed, the Java client library can also write time series.

### Designing the Metric Before Writing Code

Example: measuring pending items for a worker:

| Property | Choice |
|---|---|
| Metric type | custom.googleapis.com/orders/queue_depth |
| Meaning | Number of pending items at measurement time |
| Metric kind | GAUGE |
| Value type | INT64 |
| Unit | {item} |
| Metric labels | None required in the basic example |
| Monitored resource | generic_task representing the application task |

Queue depth can increase or decrease, so use GAUGE. Do not use DELTA for an instantaneous backlog count. If you need to count new orders per time window, design an appropriate counter and define clearly how the counter converts to a rate.

### Enabling the API and Granting Metric Write Permissions

~~~bash
export PROJECT_ID="your-project-id"

gcloud config set project "$PROJECT_ID"
gcloud services enable monitoring.googleapis.com \
  --project="$PROJECT_ID"
~~~

The service account running the application needs metric write permissions, typically the **roles/monitoring.metricWriter** role. Grant permissions to the specific service account of the workload. When running on Google Cloud, use Application Default Credentials tied to the runtime identity; never embed JSON service account keys inside a JAR or container image.

### Adding the Java Client Library

With Maven, add the Cloud Monitoring client library. Projects should manage versions using the Google Cloud Libraries BOM so Google Cloud dependencies stay compatible.

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-monitoring</artifactId>
</dependency>
~~~

### Writing a GAUGE Time Series

The example below records a task's queue depth. generic_task describes the metric source using project, location, namespace, job, and task ID. Task ID should represent a stable, unique writer within an appropriate scope so multiple processes do not overwrite or emit out-of-order points for the same time series.

~~~java
import com.google.api.Metric;
import com.google.api.MonitoredResource;
import com.google.cloud.monitoring.v3.MetricServiceClient;
import com.google.monitoring.v3.CreateTimeSeriesRequest;
import com.google.monitoring.v3.Point;
import com.google.monitoring.v3.ProjectName;
import com.google.monitoring.v3.TimeInterval;
import com.google.monitoring.v3.TimeSeries;
import com.google.monitoring.v3.TypedValue;
import com.google.protobuf.util.Timestamps;

import java.io.IOException;

public final class QueueDepthPublisher {
    private QueueDepthPublisher() {
    }

    public static void publish(
            String projectId,
            String taskId,
            long queueDepth) throws IOException {

        if (queueDepth < 0) {
            throw new IllegalArgumentException(
                    "queueDepth cannot be negative");
        }

        TimeInterval interval = TimeInterval.newBuilder()
                .setEndTime(Timestamps.fromMillis(
                        System.currentTimeMillis()))
                .build();

        Point point = Point.newBuilder()
                .setInterval(interval)
                .setValue(TypedValue.newBuilder()
                        .setInt64Value(queueDepth))
                .build();

        Metric metric = Metric.newBuilder()
                .setType("custom.googleapis.com/orders/queue_depth")
                .build();

        MonitoredResource resource = MonitoredResource.newBuilder()
                .setType("generic_task")
                .putLabels("project_id", projectId)
                .putLabels("location", "asia-southeast1")
                .putLabels("namespace", "orders")
                .putLabels("job", "orders-api")
                .putLabels("task_id", taskId)
                .build();

        TimeSeries timeSeries = TimeSeries.newBuilder()
                .setMetric(metric)
                .setResource(resource)
                .addPoints(point)
                .build();

        CreateTimeSeriesRequest request =
                CreateTimeSeriesRequest.newBuilder()
                        .setName(ProjectName.of(projectId).toString())
                        .addTimeSeries(timeSeries)
                        .build();

        try (MetricServiceClient client =
                     MetricServiceClient.create()) {
            client.createTimeSeries(request);
        }
    }
}
~~~

This is a minimal example using the Cloud Monitoring API. The application requires ADC and the roles/monitoring.metricWriter role. Metric descriptors can be auto-created by Cloud Monitoring from the first write; in production, explicitly define descriptors when you need control over display name, description, unit, metric kind, value type, and labels. Once a descriptor is created, do not arbitrarily change the metric's semantics or data type.

In multi-instance systems, use a monitored resource that accurately identifies the writer. global only has the project_id label and can cause collisions or out-of-order writes if multiple processes write to the same time series. generic_task, generic_node, or a specific resource type is better suited when distinguishing individual tasks or nodes. On GKE, Google Cloud Managed Service for Prometheus or OpenTelemetry is usually preferable to building a custom per-container metric ingestion path.

### Reading and Verifying the Metric

After sending data points, open Metrics Explorer in Cloud Monitoring:

1. Select the metric custom.googleapis.com/orders/queue_depth.
2. Select monitored resource generic_task.
3. Filter by resource.label.namespace, resource.label.job, or resource.label.task_id.
4. Inspect queue depth values over time.
5. If no data appears, check the project, Monitoring API, metric writer permissions, required resource labels, and point timestamps.

Data points do not appear instantaneously in every chart. Check the query time range, ingestion latency, and filters before concluding metric writes failed.

## 7. Querying and Aggregating Metrics in Metrics Explorer

Metrics Explorer lets you select metric types, monitored resources, filters, and visualization options. A query typically includes:

- Metric type: specifies what is measured.
- Resource type: specifies the source.
- Metric labels: filter or group by measurement attributes.
- Resource labels: filter or group by resource attributes.
- Time range: time window to analyze.
- Alignment and aggregation: how data points are normalized and multiple time series are combined.

Example filter for a Cloud Run service's request count:

~~~text
metric.type = "run.googleapis.com/request_count"
AND resource.type = "cloud_run_revision"
AND resource.label.service_name = "orders-api"
~~~

To analyze a custom metric:

~~~text
metric.type = "custom.googleapis.com/orders/queue_depth"
AND resource.type = "generic_task"
AND resource.label.namespace = "orders"
~~~

Metric and label names must match the actual descriptor. When unsure, pick metrics and labels from the Metrics Explorer UI rather than guessing names.

### Alignment and Cross-Series Aggregation

When querying time series, Cloud Monitoring can divide data into regular time intervals and compute a representative value for each interval. This step is called alignment. For example, raw samples every 10 seconds can be aligned into the mean or maximum value per minute.

Cross-series aggregation combines multiple time series into one or more resulting series. For example, summing requests across all instances or averaging CPU by zone.

| Operation | Suitable Question |
|---|---|
| Align mean | What is the average value within each interval? |
| Align max | What is the peak value within each interval? |
| Align rate | What is the rate of increase of a counter per unit time? |
| Align delta | How much did the value change within each interval? |
| Reduce sum | What is the total traffic across all instances? |
| Reduce mean | What is the average across instances? |
| Group by resource label | Which region, zone, or service has elevated values? |

Choose alignment matching the metric kind. Cumulative counters typically need conversion to rate or delta before comparing over time. Gauges such as queue depth typically use mean or max depending on the goal. For latency distributions, choose a percentile display rather than taking an average and treating it as tail latency.

## 8. Building Dashboards in Cloud Monitoring

Dashboards gather essential charts and operational info onto one screen for operations teams to monitor systems. Cloud Monitoring provides built-in dashboards for many Google Cloud services and lets you build custom dashboards combining metrics, logs, traces, alerts, and SLOs.

A dashboard should answer concrete questions:

- Is the service receiving requests?
- Are error rates and latency above normal levels?
- Do CPU, memory, or instance counts indicate capacity pressure?
- Is the queue growing steadily or draining slowly?
- Which service, region, or revision did the incident start in?

### Commonly Used Widgets

| Widget | When to Use |
|---|---|
| Line chart | Observe how a metric changes over time |
| Stacked area chart | Compare contributions of multiple groups to a total |
| Heatmap | Observe value distributions, such as latency distributions |
| Scorecard or indicator | Display a single summary value against a threshold |
| Table | Compare multiple services, instances, or regions |
| Alert chart/list | Track status of alerting policies and incidents |
| Logs panel | View related logs directly on the dashboard |
| Text | Notes, guidance, or operational threshold definitions |

Do not cram every widget onto one dashboard. Each chart should have a title describing the metric, unit, resource scope, and aggregation method.

### Creating a Dashboard via Google Cloud Console

1. Open Google Cloud Console and select the appropriate project or metrics scope.
2. Navigate to **Monitoring → Dashboards**.
3. Click **Create custom dashboard**.
4. Give it a name reflecting the service or purpose, such as **Orders API - Service Health**.
5. Click **Add widget**, then add charts, scorecards, tables, or other needed widgets.
6. For each metric widget, select metric type, resource type, filters, alignment, aggregation, and display style.
7. Add dashboard-wide filters or variables if the dashboard serves multiple services, regions, or environments.
8. Arrange widgets in priority order and group into sections if the dashboard has substantial content.
9. Save the dashboard and share appropriate access via IAM.

Google Cloud's built-in dashboards offer a fast start with standard metrics. Custom dashboards fit when viewing multiple services together or tracking business indicators. Some service-specific dashboards are auto-generated and cannot be edited directly; you can copy relevant charts into a custom dashboard.

### Dashboard Layout for Orders API

~~~text
┌──────────────────────────────────────────────────────────────────┐
│ ORDERS API — SERVICE HEALTH                                      │
├────────────────────────┬────────────────────────┬────────────────┤
│ Request rate           │ Error ratio            │ P95 latency    │
│ requests / second      │ percent                │ milliseconds   │
├────────────────────────┴────────────────────────┴────────────────┤
│ Request count and errors over time                               │
│                                                                  │
├─────────────────────────────────┬────────────────────────────────┤
│ CPU / memory / instance count   │ Queue depth / processing rate  │
│ grouped by revision             │ grouped by worker               │
├─────────────────────────────────┴────────────────────────────────┤
│ Active alerts, recent incidents and related logs                 │
└──────────────────────────────────────────────────────────────────┘
~~~

This order puts request experience at the top, resources and workers in the middle, and alerts and logs supporting investigation at the bottom. Operators see user-facing symptoms first before drilling down into causes.

### Dashboard-Wide Filters and Variables

Dashboard-wide filters apply across multiple widgets simultaneously, such as filtering to a single region or environment. Variables can dynamically parameterize queries across selected widgets. On a dashboard shared by multiple services, a service variable lets on-call engineers switch context without editing individual charts.

Verify whether every widget supports the filter or variable. Some widgets have custom queries or data sources that may not respond to all global filters.

### Keeping Dashboards Readable and Fast-Loading

- Display only metrics that inform operational decisions.
- Use filters to restrict services, regions, zones, or namespaces.
- Reduce the number of time series per chart through appropriate grouping or aggregation.
- Never create separate charts per request or per user.
- Set a default time range matching shift workflows and observation goals.
- Provide clear titles, units, and legends; never force viewers to guess colors or axes.
- Split large dashboards into sections or separate dashboards by service and role.

Dashboard performance depends on the number of charts and the number of time series each chart loads. Dashboards with too many series load slowly and become hard to read. Filter and aggregate before adding widgets.

## 9. From Dashboards to Alerting Policies

Dashboards help operators observe proactively. Alerting policies let the system detect actionable conditions and notify responsible owners.

For example, a dashboard shows P95 latency climbing for 15 minutes. An alerting policy can evaluate whether latency stays above a threshold for a sustained duration and send notifications to a notification channel.

When designing alerts:

1. Select a metric that accurately represents user impact or operational risk.
2. Specify resources and filters so the alert applies only to the target service.
3. Choose an alignment period and aggregation suited to the metric kind.
4. Set thresholds based on baselines, SLOs, or business requirements.
5. Choose a duration window to suppress brief transient spikes.
6. Configure notification channels and incident handling instructions.
7. Test using test data or simulated scenarios.

Do not create an alert merely because a metric changed. Alerts should represent actionable situations, such as error ratio threatening an error budget or queue age growing enough to endanger an SLA. For critical signals, prefer officially defined metric labels and resource labels; avoid relying on resource metadata labels that may update asynchronously.

## 10. IAM and Cloud Monitoring Access Control

Required permissions depend on the role of the user or workload:

- Workloads writing custom metrics need write permissions, typically **roles/monitoring.metricWriter**.
- Users viewing dashboards and metrics need appropriate read permissions, typically **roles/monitoring.viewer**.
- Users creating or editing dashboards, alerting policies, and Monitoring settings need corresponding management permissions; grant according to actual duties.

Do not grant Monitoring admin permissions to every service account simply because an application needs to emit metrics. Separate metric-writing identities from dashboard-management identities. In multi-project environments, configure a metrics scope so operators can view data across authorized projects while maintaining access boundaries.

## 11. Cost and Managing Metric Usage

Metrics incur charges based on data type, ingestion volume, and usage. User-defined metrics are a billable feature. High cardinality can multiply time series counts and ingested data volume. A single metric with high-cardinality unique label values can cost far more than expected even when the number of metric types is small.

Cost controls:

- Reuse built-in metrics whenever appropriate.
- Design labels with bounded cardinality and drop unnecessary dimensions.
- Never create new series per customer, order, request, or session.
- Collect only at a frequency sufficient for operational goals.
- Check Metrics Management to inspect ingestion, samples, time series counts, metric usage, and unused metrics.
- Check which custom metrics are referenced by dashboards or alerting policies before deleting them.
- Estimate costs before rolling out metrics at scale.

Do not mechanically lower collection frequency or delete critical metrics just to cut costs. Identify which signals are essential for SLOs, alerts, investigation, and capacity planning, then optimize dimensions that provide little corresponding value.

## 12. Hands-On Exercise: Orders API Service Health Dashboard

Suppose a system has a Cloud Run service **orders-api** and a worker running on GKE. The operations team wants to track requests, errors, latency, and queue processing health.

Perform in a sandbox project:

1. Open Metrics Explorer and locate Cloud Run's request count, request latency, and instance count metrics.
2. Confirm the monitored resource type and resource labels for **cloud_run_revision**.
3. Add a filter selecting only service **orders-api**; compare data by revision or location.
4. Create custom metric **custom.googleapis.com/orders/queue_depth** for queue depth using GAUGE and a monitored resource suited to worker tasks.
5. Use metric labels or resource labels with small value sets, such as environment and region; do not put orderId or requestId in metric labels.
6. Create a custom dashboard **Orders API - Service Health**.
7. Add widgets for request rate, error ratio, P95 latency, CPU/memory, instance count, and queue depth.
8. Add filters to switch between region or environment if supported by the widgets.
9. Create a test alerting policy for when error ratio or queue depth crosses chosen thresholds.
10. Generate traffic and simulate slow worker processing; verify the dashboard reflects the changes accurately and the alert fires.
11. Check Metrics Management to evaluate cardinality and metric ingestion volume.

The expected outcome is a dashboard showing overall API and worker health while allowing drill-down from aggregate indicators to specific resources or revisions during investigation.

## 13. Pre-Release Checklist for Metrics and Dashboards

- [ ] Checked built-in metrics before creating custom metrics.
- [ ] Metric descriptors have meaningful names, descriptions, units, kinds, and value types.
- [ ] Monitored resource type accurately reflects the data source.
- [ ] Resource labels and metric labels are clearly separated.
- [ ] No unique IDs or dynamic URLs are used as metric labels.
- [ ] Cardinality is estimated upfront and monitored post-deployment.
- [ ] Gauge, delta, and cumulative are chosen accurately for the measurement.
- [ ] Alignment, aggregation, and percentiles match the metric type.
- [ ] Dashboards have clear goals, and widgets have titles and units.
- [ ] Dashboard filters and variables work correctly across widgets.
- [ ] Alerting policies include thresholds, evaluation durations, and remediation guidance.
- [ ] Service accounts hold only required Monitoring permissions.
- [ ] Metric ingestion and costs are reviewed periodically.

## Self-Check Questions

**1. Which components uniquely identify a time series in Cloud Monitoring?**

It binds a metric type and metric label values to a specific monitored resource along with its resource label values, storing timestamped data points over time.

**2. How do resource labels differ from metric labels?**

Resource labels describe the origin of the data, such as a VM, pod, or service. Metric labels describe classification dimensions of the measurement, such as method or response code.

**3. Why is queue depth typically a GAUGE?**

Because it represents the number of pending items at a point in time and can increase or decrease between measurements.

**4. Why should orderId not be placed in metric labels?**

Because each orderId can create a separate time series, rapidly inflating cardinality. orderId belongs in logs or traces.

**5. How does a dashboard differ from an alerting policy?**

A dashboard visualizes metrics for human observation. An alerting policy evaluates conditions over time and sends notifications when action is required.

**6. When should you use a custom metric?**

When you need to measure application-specific business or technical data not provided by built-in metrics, such as queue depth or processed order counts.

## References

- [Metrics, time series, and resources](https://docs.cloud.google.com/monitoring/api/v3/metrics)
- [Components of the metric model: labels and cardinality](https://docs.cloud.google.com/monitoring/api/v3/metric-model)
- [Structure of time series](https://docs.cloud.google.com/monitoring/api/v3/metrics-details)
- [Value types and metric kinds](https://docs.cloud.google.com/monitoring/api/v3/kinds-and-types)
- [Monitored resource types](https://docs.cloud.google.com/monitoring/api/resources)
- [User-defined metrics overview](https://docs.cloud.google.com/monitoring/custom-metrics)
- [Create user-defined metrics with the API](https://docs.cloud.google.com/monitoring/custom-metrics/creating-metrics)
- [Java client library sample: write time series](https://docs.cloud.google.com/monitoring/docs/samples/monitoring-quickstart)
- [Dashboards overview](https://docs.cloud.google.com/monitoring/dashboards)
- [Create and manage custom dashboards](https://docs.cloud.google.com/monitoring/charts/dashboards)
- [Cloud Monitoring quotas and limits](https://docs.cloud.google.com/monitoring/quotas)

## Conclusion

Cloud Monitoring turns infrastructure and application measurements into queryable, visualizable time series. Metric types define measurement semantics; monitored resources and resource labels identify origins; metric labels add analytical dimensions. Thoughtful label design controls cardinality and cost. Metrics Explorer supports filtering, alignment, and aggregation, while dashboards bring critical signals onto a single screen for operations teams. Combining built-in metrics, custom metrics, dashboards, and alerting policies enables development teams to track service health and detect issues before impact spreads.
