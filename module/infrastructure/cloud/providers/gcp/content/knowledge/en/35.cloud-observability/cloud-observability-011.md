# Managed Service for Prometheus on GKE

When running multiple applications on Google Kubernetes Engine (GKE), operations teams need to know which workloads are running, whether error rates are climbing, how latency is shifting, and whether cluster resources remain sufficient. Prometheus provides a periodic metric scraping model, time-series storage, and PromQL querying. Google Cloud Managed Service for Prometheus provides a managed, Prometheus-compatible backend for storing and querying metrics at Google Cloud scale without self-operating full Prometheus servers.

On GKE, **managed collection** deploys Google-managed metric collection components inside the cluster. Operators declare workloads and scrape endpoints using Kubernetes resources such as `PodMonitoring` or `ClusterPodMonitoring`; data is sent to Cloud Monitoring for PromQL querying, dashboards, and alerting.

This lesson focuses on designing, enabling, and operating Managed Service for Prometheus on GKE—from endpoint configuration and data verification to security, cost, and troubleshooting.

## 1. Prometheus and Managed Service for Prometheus

Prometheus is a time-series-based monitoring system. Each data sample consists of a metric name, a label set, a value, and a timestamp. Example:

```text
http_requests_total{method="GET",status="200"} 1842
```

In this example:

- `http_requests_total` is the metric name.
- `method` and `status` are labels describing the series.
- `1842` is the counter value recorded at sample time.

Prometheus typically operates on a pull model: a collector visits the application's metrics endpoint on a schedule, reads data in exposition format, and stores it as time series. PromQL computes over data across time windows, aggregates by labels, and detects abnormal conditions.

Google Cloud Managed Service for Prometheus provides Prometheus-compatible storage and querying. Data is stored in Cloud Monitoring's managed backend. Users can run PromQL in the Cloud Monitoring UI, dashboards, alerting policies, and compatible integrations.

Distinguish two parts:

| Component | Responsibility |
|---|---|
| Managed collection | Discovers targets and scrapes metrics from workloads inside the cluster |
| Managed Service for Prometheus backend | Ingests, stores, indexes, and serves time-series queries |
| Cloud Monitoring | Provides metrics scopes, dashboards, alerting, IAM, and operational integration |
| PromQL | Query language for Prometheus data |
| Kubernetes monitoring resources | Declares Pods and endpoints the collector should scrape |

Managed Service for Prometheus does not automatically discover every endpoint in an application. Development teams must expose metrics endpoints and platform teams must declare how to scrape them.

## 2. Managed Collection Architecture on GKE

When managed collection is enabled, GKE installs and manages the required collector components inside the cluster. Collectors discover Pods matched by monitoring resources, scrape metrics periodically, and forward data to the Google Cloud backend.

~~~mermaid
flowchart TD
    A[Application Pods] --> B[/metrics endpoint]
    C[PodMonitoring or ClusterPodMonitoring] --> D[Managed collectors in GKE]
    B --> D
    D --> E[Google Cloud Managed Service for Prometheus]
    E --> F[Cloud Monitoring metrics scope]
    F --> G[PromQL queries and dashboards]
    F --> H[Alerting policies]
    H --> I[Notification channels]
~~~

Workflow:

1. Applications expose metrics via an HTTP endpoint, typically `/metrics`.
2. `PodMonitoring` or `ClusterPodMonitoring` selects Pods by label and declares port, path, and interval.
3. Managed collectors in GKE discover targets and scrape data.
4. Metrics are sent to the Managed Service for Prometheus backend.
5. Operators query data with PromQL, build dashboards, and configure alerts in Cloud Monitoring.

Managed collection can also collect certain built-in Kubernetes and node metrics depending on GKE configuration. Application-specific metrics still need to be exposed and configured. System metric coverage can vary by cluster type, version, and configuration; verify actual targets before relying on a metric in dashboards.

Managed collection reduces the operational burden of running collectors and backends, but does not eliminate metric design responsibilities. Teams still need to control series counts, labels, scrape intervals, access permissions, and alert quality.

## 3. Preparing the Project and GKE Cluster

Before enabling Managed Service for Prometheus, identify the project hosting the cluster, its location, deployer permissions, network egress to Google APIs, and the project used to view metrics.

### Enabling Required APIs

The Cloud Monitoring API must be enabled in the project:

~~~bash
gcloud services enable monitoring.googleapis.com \
  --project="PROJECT_ID"
~~~

The operator needs permission to enable service APIs. If the organization uses a separate management project or metrics scope, clarify which project hosts the cluster and which project acts as the scoping project for querying.

### Enabling Managed Collection on an Existing Cluster

For an existing GKE cluster, enable managed collection via the Google Cloud CLI:

~~~bash
gcloud container clusters update "CLUSTER_NAME" \
  --location="LOCATION" \
  --enable-managed-prometheus \
  --project="PROJECT_ID"
~~~

When creating a new cluster, the corresponding option can be enabled in the cluster creation command or cluster configuration. Exact syntax may vary by cluster type and Google Cloud CLI version; check `gcloud container clusters create --help` or applicable GKE docs before running in production.

After enabling, wait for managed components to deploy and check cluster status. Do not assume a successful update command means every application target is already being scraped.

### Checking Status Inside the Cluster

Inspect monitoring resources and collectors:

~~~bash
kubectl get podmonitoring -A
kubectl get clusterpodmonitoring
kubectl get pods -n gmp-system
~~~

If the cluster does not yet have `PodMonitoring` resources, the first command returns an empty list. If the collector namespace differs from expectations or the cluster has not finished deploying, check managed collection status and Kubernetes events before concluding collectors failed.

For clusters with private nodes, verify connectivity paths to Google APIs, DNS, proxies, or Private Google Access per your network architecture. Collectors must send metrics to the backend; overly restrictive firewalls or egress policies can disrupt metric delivery.

## 4. Exposing Metrics from Applications

Applications must serve a metrics endpoint reachable by collectors over the Pod network. The endpoint typically uses HTTP and path `/metrics`, though both can be customized.

Example: a container declaring a port named `metrics`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION
          ports:
            - name: http
              containerPort: 8080
            - name: metrics
              containerPort: 9090
~~~

The application must actually listen on port 9090 and serve data in Prometheus exposition format. Declaring `containerPort` alone does not create a metrics endpoint. Prometheus client libraries for application languages typically support counters, gauges, histograms, and summaries.

Common metric types:

| Type | Meaning | Examples |
|---|---|---|
| Counter | Monotonically increasing value unless the process restarts | Total requests, exceptions, processed messages |
| Gauge | Value that can increase or decrease | In-flight requests, queue length |
| Histogram | Observed distribution across buckets | Request duration, payload size |
| Summary | Observed distribution and client-side quantiles | Per-process latency quantiles |

Prefer histograms when aggregating latency across multiple Pods. Quantiles computed independently by each Summary generally cannot be aggregated accurately into cluster-wide quantiles.

### Designing Metric Names and Labels

Metric names should convey meaning, unit, and data type. Examples:

- `http_requests_total`: total processed requests.
- `http_request_duration_seconds_bucket`: request duration histogram buckets.
- `queue_messages_pending`: pending message count.
- `process_resident_memory_bytes`: process resident memory.

Labels should have bounded, stable value sets, such as `method`, `status_code`, `namespace`, `app`, or `region`. Avoid labels with nearly unique values per request or user.

Never use fields like user ID, email, session ID, request ID, trace ID, or URLs containing identifiers as metric labels. Every label combination creates a time series; rapidly growing cardinality increases cost, storage, and query latency.

## 5. Declaring PodMonitoring

`PodMonitoring` is a namespaced Kubernetes resource. It selects Pods in the same namespace as the resource and declares endpoints to scrape. This is the standard way to configure metrics for a specific application.

The example below selects Pods labeled `app: orders-api` in the `production` namespace:

~~~yaml
apiVersion: monitoring.googleapis.com/v1
kind: PodMonitoring
metadata:
  name: orders-api
  namespace: production
spec:
  selector:
    matchLabels:
      app: orders-api
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
~~~

Save as `pod-monitoring.yaml` and apply:

~~~bash
kubectl apply -f pod-monitoring.yaml
kubectl describe podmonitoring orders-api -n production
~~~

Key fields:

- `metadata.namespace`: namespace containing the PodMonitoring resource.
- `spec.selector.matchLabels`: label selector choosing Pods to scrape.
- `endpoints.port`: container port name or supported port value.
- `endpoints.path`: HTTP path serving metrics.
- `endpoints.interval`: scrape interval; shorter intervals generate more samples and higher load.

The `metrics` port name in PodMonitoring must match the port exposed by the Pod. If the application serves metrics on port 9090 but the config points to HTTP port 8080, collectors may hit the wrong endpoint or fail to parse metrics.

Multiple endpoints can be declared inside one PodMonitoring when a workload exposes multiple metrics endpoints. Keep configurations clear so operators can easily tell which targets belong to which application.

### PodMonitoring and ClusterPodMonitoring

These two resources differ in scope:

| Resource | Pod Selection Scope | Use Case |
|---|---|---|
| PodMonitoring | Within the resource's namespace | Metrics for an application or workload group in one namespace |
| ClusterPodMonitoring | Across the entire cluster | Shared components needing to scrape Pods across multiple namespaces |

Example ClusterPodMonitoring for an exporter deployed with the same label across namespaces:

~~~yaml
apiVersion: monitoring.googleapis.com/v1
kind: ClusterPodMonitoring
metadata:
  name: shared-exporter
spec:
  selector:
    matchLabels:
      app: shared-exporter
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
~~~

Because cluster-scoped resources can match Pods in any namespace, selectors must be specific enough to avoid unintended scraping or duplicate targets. Use ClusterPodMonitoring only when cluster-wide scope is truly necessary; if a workload lives in one namespace, PodMonitoring is easier to govern.

### Avoiding Duplicate Scraping

A Pod can be matched by multiple monitoring resources. This creates duplicate targets, increases ingestion, and causes confusion in queries. When designing selectors, inspect all active PodMonitoring and ClusterPodMonitoring resources, including those deployed by platform teams or Helm charts.

If a cluster uses Prometheus Operator with `ServiceMonitor` or `PodMonitor`, do not assume managed collection automatically reads those custom resources. Migrate configurations to monitoring resources supported by GKE Managed Service for Prometheus or deploy a verified compatible collection setup.

## 6. Querying Metrics with PromQL

PromQL computes counter increase rates, aggregates by labels, derives percentiles from histograms, and compares values over time.

Open Cloud Monitoring, go to Metrics Explorer, and switch to PromQL mode to query Prometheus metrics. Select the right project or metrics scope containing the data and an appropriate time range.

### Calculating Request Rate

Suppose the application exposes the `http_requests_total` counter:

~~~promql
sum by (namespace, method, status_code) (
  rate(http_requests_total[5m])
)
~~~

`rate()` calculates the average per-second increase over a 5-minute window. Use `rate()` on counters instead of treating the raw counter value as instantaneous traffic.

Total requests by namespace:

~~~promql
sum by (namespace) (
  rate(http_requests_total[5m])
)
~~~

### Calculating Error Ratio

Suppose the metric has a `status_code` label:

~~~promql
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))
~~~

This expression returns the ratio of 5xx requests to total requests over a 5-minute window. Account for zero denominators and verify the exact label names emitted by your application.

### Calculating p95 Latency from a Histogram

If the application exposes the `http_request_duration_seconds_bucket` histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

The expression aggregates buckets across Pods before computing the p95 quantile. To break down by namespace or service, include those labels in `sum by`.

### Checking Target Health

Prometheus provides the `up` metric for target scrape status:

~~~promql
up
~~~

A value of 1 generally indicates a successful scrape; 0 indicates the most recent scrape failed. Filter by namespace or job after confirming available labels in your data:

~~~promql
up{namespace="production"}
~~~

Do not assume every cluster shares the exact same label set. Explore actual series in the PromQL editor before writing dashboards and alerts.

### Understanding Metric Names in Cloud Monitoring

Prometheus metrics appear in the Cloud Monitoring ecosystem with Prometheus-convention metric types, typically prefixed with `prometheus.googleapis.com/`. Metric names, kinds, and labels can appear as Cloud Monitoring metric descriptors. Using PromQL lets you work with familiar Prometheus metric names, while Metrics Explorer also supports viewing metadata and associated resources.

## 7. Dashboards and Alerting

Metrics are valuable only when they help operators answer questions and act on time. Dashboards should reflect service health, resource consumption, and user experience.

### Designing Dashboards Around Operational Signals

For an API running on GKE, organize dashboards into groups:

| Group | Suggested Metric or Query | Question Answered |
|---|---|---|
| Traffic | Requests/second by service, namespace | Is traffic changing abnormally? |
| Errors | 4xx/5xx ratio, exception rate | Are users encountering errors? |
| Latency | p50, p95, p99 from histograms | Are requests slower than normal? |
| Saturation | CPU, memory, queue depth, throttling | Are workloads nearing limits? |
| Availability | `up`, ready replicas, Pod restarts | Are targets and workloads healthy? |
| Dependencies | Connection pools, DB latency, downstream errors | Are external dependencies causing impact? |

Create dashboards in Cloud Monitoring and save PromQL queries with clear names. In multi-project setups, metrics scopes allow querying data across scoped projects; IAM permissions continue to apply per resource and project.

### Alerting with PromQL

Cloud Monitoring supports creating alerting policies with PromQL conditions. For example, detecting unscrapable targets in the production namespace:

~~~promql
sum by (namespace, job) (
  up{namespace="production"} == 0
) > 0
~~~

Configure a persistence duration, such as 5 minutes, to avoid paging on a brief single scrape failure. Attach appropriate notification channels such as email, PagerDuty, or organization-approved webhooks.

A good alert needs:

- A name indicating the service and impact.
- A condition sensitive enough to catch issues without noise.
- Appropriate duration or evaluation window.
- Severity and accountable owner.
- Remediation steps or a runbook link.
- Deduplication and grouping to avoid flooding notifications.

Do not alert solely on brief CPU spikes without understanding load behavior. Combine saturation with latency, error rate, traffic, and replica status to confirm real impact.

### Recording Rules and Alert Rules

For repeated queries or complex dashboards, recording rules precompute expressions for fast, consistent querying. Alert rules evaluate conditions and fire alerts when conditions persist per policy. With GKE Managed Service for Prometheus, you can use supported rule evaluation mechanisms in your organization's deployment or use Cloud Monitoring alerting policies with PromQL. Pick one clear place to manage rules so two systems do not alert redundantly for the same condition.

## 8. Security and Access Control

While metrics rarely carry secrets, they can still reveal system topology, service names, tenants, internal endpoints, error codes, or user behavior. Treat metrics as controlled operational data.

### IAM Permissions

Separate metric-writing permissions from metric-viewing permissions:

- Workloads or collectors need metric write permissions per the configured GKE managed collection mechanism.
- Dashboard viewers and query users typically need appropriate Monitoring Viewer permissions.
- Creators of alerts, dashboards, or monitoring configs need corresponding administrative roles.
- Never grant project-wide admin roles merely so a team can read dashboards.

Common roles include `roles/monitoring.viewer` for viewing and querying, and `roles/monitoring.metricWriter` for principals writing metrics. With managed collection, verify identities and permissions configured by GKE per platform docs; avoid granting overly broad roles to node service accounts or all workloads unnecessarily.

### Protecting Metrics Endpoints

- Allow only authorized collectors and monitoring components to access endpoints.
- Never expose metrics ports to the public Internet.
- Use NetworkPolicies or suitable network controls to restrict access flows.
- Never put tokens, passwords, personal data, or request contents into metric labels.
- If an endpoint requires TLS or authentication, use supported scrape config mechanisms and manage credentials via Secret Manager.
- Never share a single broad-privilege credential across multiple applications.

### Protecting Data and Queries

Restrict access to projects, metrics scopes, dashboards, and alerting policies by team. Audit access logs and monitoring configuration changes. When sharing dashboards, ensure labels or series names do not leak customer details or internal environment specifics.

## 9. Performance, Cardinality, and Cost

Costs and performance of Managed Service for Prometheus depend on the volume of data scraped and sent to the backend. Two factors commonly driving unexpected growth are overly short scrape intervals and high cardinality.

### Estimating Time Series Counts

A metric can have multiple labels. If a metric has 5 method values, 6 status values, 20 routes, and 10 instances, the maximum combinations can reach:

\[
5 \times 6 \times 20 \times 10 = 60{,}000
\]

This is a theoretical combination estimate; actual series depend on observed data. Adding user IDs or request IDs with millions of values causes cardinality to surge rapidly.

### Tuning Scrape Intervals

Example:

| Scrape Interval | Samples per Series per Hour | Notes |
|---|---:|---|
| 15 seconds | 240 | Fits signals requiring high resolution; increases ingestion |
| 30 seconds | 120 | Common balance for application metrics |
| 60 seconds | 60 | Reduces ingestion; fits slowly changing signals |

These are theoretical sample counts assuming every scrape succeeds. Total volume also depends on target count, metric count, and labels.

Do not set overly short intervals for every workload. For capacity planning metrics, 30 or 60 seconds may suffice; certain operational signals require finer resolution. Weigh detection requirements, system limits, and budget before choosing.

### Reducing Cardinality

- Use labels with bounded value sets.
- Never attach unique identifiers per request or user.
- Avoid exporting duplicate metrics from multiple exporters.
- Use metric relabeling or supported filtering to drop unnecessary series.
- Cap label count and label size by design.
- Monitor active series counts, ingestion, and sudden jumps after every release.

Do not drop critical metrics solely to cut cost. Identify which signals support SLOs, incident handling, and capacity planning, then eliminate redundant or low-value data.

### Monitoring Costs

Cloud Monitoring bills according to the service's current pricing model; Managed Service for Prometheus incurs charges tied to ingested samples and used features. Consult the Billing page, SKU reports, and current pricing docs to determine unit rates per region/account. Never hardcode a static price in runbooks without checking current rates.

## 10. Operating Across Multiple Clusters and Projects

An organization may run multiple GKE clusters across environments or regions. Design labels and metrics scopes so cross-project queries remain possible while still distinguishing data sources.

Standardize identifying dimensions:

- `project_id`: project containing the cluster.
- `location`: region or zone.
- `cluster`: cluster name.
- `namespace`: Kubernetes namespace.
- `job` or app label: logical workload.

Keep cluster and namespace names consistent across environments. Do not reuse an `environment` label inconsistently when the same value means different things across workloads. Standardize naming conventions and avoid overlapping labels.

### Metrics Scope

A metrics scope enables a scoping project to view Cloud Monitoring data from one or more projects added to that scope. With multiple clusters, pick an operations project as the scoping project and attach the cluster projects.

This lets dashboards and PromQL query multiple sources within one scope. Adding a project to a metrics scope does not automatically grant data read permissions; principals still need appropriate IAM roles on the underlying projects.

### Separating Environments

Production and non-production can use separate scoping projects or dashboards depending on control requirements. This reduces confusion during incidents, limits access scope, and supports per-environment cost tracking.

## 11. Troubleshooting Collection and Query Issues

When metrics are missing or dashboards show gaps, inspect systematically from endpoint to backend. Avoid changing multiple configurations simultaneously, as that obscures the root cause.

| Symptom | Possible Causes | How to Check |
|---|---|---|
| No targets found | Managed collection disabled, CRD unrecognized, selector mismatch with Pods | Check cluster settings, PodMonitoring, Pod labels |
| Target exists but scrapes fail | Wrong port/path, app not listening, blocked by NetworkPolicy | Check container ports, endpoints, Pod logs, and networking |
| Target exists but expected series missing | App not exposing metric or different metric name/labels | Curl endpoint inside cluster and inspect exposition output |
| PromQL returns empty | Wrong project/metrics scope, time range, label, or metric name | Check scope, time range, explore series |
| Delayed data | Scrape cycle, shipping, ingestion, or query latency | Compare sample timestamps and target status |
| Sudden cost spike | Cardinality, duplicate targets, overly short interval | Inspect active series, selectors, and scrape configs |
| Some Pods lose metrics | Pod label changes, restarts, readiness, or unstable endpoint | Check rollouts, Pod events, and target health |

### Inspecting Kubernetes Configuration

~~~bash
kubectl get podmonitoring -A -o yaml
kubectl get clusterpodmonitoring -o yaml
kubectl get pods -n production --show-labels
kubectl describe podmonitoring orders-api -n production
~~~

Compare label selectors against actual Pod labels. Verify ports are named accurately and applications listen on addresses reachable by collectors.

### Checking Endpoints from Inside the Cluster

You can run an approved diagnostic Pod to query internal endpoints:

~~~bash
kubectl run metrics-check \
  -n production \
  --rm -it \
  --restart=Never \
  --image=curlimages/curl \
  -- curl -sS http://POD_IP:9090/metrics
~~~

Replace host and port with the actual in-cluster endpoint. Whether using Pod IP or Service DNS, ensure the command mirrors how collectors reach targets. Delete diagnostic Pods afterward and avoid printing sensitive data to the terminal.

### Checking Queries and Metrics Scope

If scraping succeeds but PromQL returns nothing:

1. Select the right project or metrics scope in Cloud Monitoring.
2. Widen the time range to cover recent scrape times.
3. Run `up` to verify whether the target has data.
4. Check actual metric names and labels.
5. Check whether dashboard or alert filters are excluding the series.
6. Inspect collector logs and metric write errors if you have access.

Do not assume the collector is broken just because one specific metric is missing; the metric might only be emitted upon an event or may not yet be registered by the application.

## 12. Hands-On Scenario: Monitoring orders-api on GKE

A team deploys `orders-api` on cluster `gke-prod`, namespace `production`. The app exposes metrics on port 9090, path `/metrics`, with request counters and latency histograms.

### Step 1 — Enable Managed Collection

Confirm the Monitoring API is enabled and managed collection is enabled on the cluster:

~~~bash
gcloud services enable monitoring.googleapis.com \
  --project="PROJECT_ID"

gcloud container clusters update "gke-prod" \
  --location="asia-southeast1" \
  --enable-managed-prometheus \
  --project="PROJECT_ID"
~~~

### Step 2 — Verify Pod Labels and Ports

The Deployment's Pod template needs label `app: orders-api` and container port named `metrics`. Verify:

~~~bash
kubectl get pods -n production --show-labels
kubectl get deployment orders-api -n production -o yaml
~~~

### Step 3 — Create PodMonitoring

~~~yaml
apiVersion: monitoring.googleapis.com/v1
kind: PodMonitoring
metadata:
  name: orders-api
  namespace: production
spec:
  selector:
    matchLabels:
      app: orders-api
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
~~~

Apply and inspect:

~~~bash
kubectl apply -f pod-monitoring.yaml
kubectl describe podmonitoring orders-api -n production
~~~

### Step 4 — Verify Metrics

In the Cloud Monitoring PromQL editor, run:

~~~promql
up{namespace="production"}
~~~

Then check request rate:

~~~promql
sum by (status_code) (
  rate(http_requests_total{namespace="production"}[5m])
)
~~~

And p95 latency:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_request_duration_seconds_bucket{namespace="production"}[5m])
  )
)
~~~

Metric names and labels must match what the application actually emits. If queries return empty, verify targets, endpoints, and metrics scope before editing queries.

### Step 5 — Create Alerts

Create a PromQL alert condition detecting unscrapable targets:

~~~promql
sum by (namespace, job) (
  up{namespace="production"} == 0
) > 0
~~~

Set an appropriate persistence duration, assign severity, attach notification channels, and link a runbook. Add separate alerts for error rate or latency once the team sets SLO-based thresholds.

### Step 6 — Move to Operations

- Associate dashboards with the service owner and environment.
- Test alerts during a game day or drill.
- Monitor series counts and ingested sample volumes.
- Review any new labels after every release.
- Place PodMonitoring manifests under reviewed configuration management.
- Periodically audit IAM permissions, metrics scopes, and notification channels.

Once complete, the team can observe traffic, errors, latency, and scrape health for `orders-api` from Cloud Monitoring without operating a standalone Prometheus backend for the cluster.

## 13. Deployment and Operations Checklist

### Before Enabling

- [ ] Identified project, cluster, location, and metrics scope.
- [ ] Enabled Cloud Monitoring API.
- [ ] Verified deployment permissions and metric-writing permissions under the GKE model.
- [ ] Checked egress to Google APIs and network policies.
- [ ] Standardized metric names, labels, and scrape intervals.

### When Configuring Collection

- [ ] Managed collection enabled on the cluster.
- [ ] Application exposes a valid metrics endpoint.
- [ ] PodMonitoring or ClusterPodMonitoring selects the intended Pods.
- [ ] Port, path, and interval match the application.
- [ ] No duplicate targets or overly broad selectors.
- [ ] Verified data using `up` and a real PromQL query.

### Before Production

- [ ] Dashboards cover traffic, errors, latency, and saturation.
- [ ] Alerts include severity, duration, notification channels, and runbooks.
- [ ] IAM follows least privilege.
- [ ] Metrics endpoints are not unintentionally public.
- [ ] Labels contain no sensitive data and avoid high cardinality.
- [ ] Ingestion, active series, and costs are monitored.

### Ongoing Operations

- [ ] Review failing targets and missing metrics.
- [ ] Check selectors whenever Deployments change labels.
- [ ] Review dashboards, alerts, and notification channels.
- [ ] Audit metrics scopes and cross-project access permissions.
- [ ] Re-evaluate cardinality and scrape intervals as workloads grow.
- [ ] Practice alert response drills and keep runbooks updated.

Managed Service for Prometheus on GKE pairs familiar Prometheus scraping with Google Cloud's managed backend. When applications expose clean metrics, PodMonitoring targets the right workloads, labels stay controlled, and PromQL powers meaningful dashboards and alerts, operations teams can monitor workload health across one or many clusters without managing Prometheus storage infrastructure themselves.
