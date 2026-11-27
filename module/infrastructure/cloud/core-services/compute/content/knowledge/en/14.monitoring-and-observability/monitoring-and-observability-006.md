# Building Dashboards for Traffic, Errors, Latency, and Saturation

A good operational dashboard helps teams quickly answer four questions: how much work is the system processing, how much of that work is failing, how long are users waiting, and do resources still have capacity to handle load? These four signal groups are commonly called the **Four Golden Signals**: Traffic, Errors, Latency, and Saturation.

For cloud compute workloads, dashboards must connect application-level figures to CPU, memory, storage, network, queues, and dependent services. Looking only at a VM's CPU does not tell you whether users are experiencing errors; looking only at a service-wide error rate can mask a single failing instance or zone.

After this lesson, you will be able to:

- Explain and select metrics for traffic, errors, latency, and saturation.
- Design overview dashboards and drill-down views by service, instance, zone, or version.
- Calculate request rate, error rate, and latency percentiles from appropriate metric data.
- Combine application signals with CPU, RAM, disk, network, and queues to locate bottlenecks.
- Set alert thresholds based on SLOs and impact, avoiding arbitrary single-number alerts.
- Avoid high cardinality, improper aggregations, and misleading charts.

## 1. The Four Golden Signals of a System

The Four Golden Signals observe a service from the perspective of users and system serving capacity.

| Signal | Question | Representative metrics |
|---|---|---|
| Traffic | How much work is arriving or being processed? | Requests/second, transactions/second, message throughput, concurrent requests, bytes in/out |
| Errors | How much work is failing or not meeting expected outcomes? | Error count, error rate, HTTP 5xx, timeouts, failed jobs, retries, and exception rate |
| Latency | How long does a request or task take? | p50, p90, p95, p99 response time; queue wait; dependency latency |
| Saturation | How close are resources or queues to their limits? | CPU, memory pressure, disk I/O, network capacity, connection pools, queue depth, and throttling |

The four signals must be viewed together. Rising traffic could mean normal growth or an attack. Rising latency could stem from saturated CPU, a slow database, or an external dependency. High CPU is not necessarily an incident if throughput is also climbing, latency stays within SLO, and sufficient headroom remains.

    Traffic ─┐
    Errors ──┼──> Assess service health ──> Overview dashboard
    Latency ─┤                           └─> Drill-down and action
    Saturation┘

## 2. Defining Dashboard Scope and Audience

Before creating panels, define who the dashboard serves and what decisions it must support.

- **Operations/on-call dashboard:** must show whether users are impacted, severity, which component is abnormal, and links to runbooks.
- **Application team dashboard:** needs drill-downs by route, operation, dependency, version, and deployment outcomes.
- **Infrastructure dashboard:** needs CPU, RAM, disk, network, instances, nodes, zones, quotas, and utilization over time.
- **Capacity/cost dashboard:** needs traffic trends, utilization, instance counts, headroom, and cost per workload.

A single dashboard should not try to display every metric of every system on one screen. Overview pages must let you spot issues in seconds; detail pages support root cause investigation.

### Choosing units of observation

For applications running across multiple VMs or Pods, observe at multiple levels:

1. **Service/fleet:** total traffic, error rate, latency, and saturation across the entire service.
2. **Instance/Pod:** catch an individual machine experiencing high CPU, OOM, errors, or outlier latency.
3. **Zone/region/node pool:** catch localized failures along a fault domain or infrastructure group.
4. **Operation/route:** identify which endpoint or task is slow, failing, or consuming excessive resources.
5. **Dependency:** measure duration and error rates when calling databases, caches, queues, or external APIs.

Always keep an aggregate chart to show overall service impact, then provide links or filters for granular dimensions. Do not use per-instance charts as a substitute for service charts, because instance counts change during autoscaling.

## 3. Designing the Traffic Dashboard

Traffic indicates the rate and volume of work the system is receiving or completing. Units must fit the workload type.

### Recommended metrics

| Metric | Common unit | Meaning |
|---|---|---|
| Request rate | requests/second (RPS) | Number of requests received or processed per second |
| Transaction rate | transactions/second (TPS) | Number of business transactions completed per second |
| Message throughput | messages/second | Number of messages received, processed, or acknowledged per second |
| Concurrent requests | concurrent requests | Number of requests actively in flight at a point in time |
| Bytes in/out | bytes/s or bits/s | Inbound and outbound data volume |
| Active connections | connections | Number of open connections to the application or dependencies |
| Queue arrival/completion | messages/s | Work arrival rate compared to processing rate |

Do not equate received requests with successfully completed requests. An API may receive 1,000 RPS yet complete only 700 RPS if queues are growing or requests are timing out. Whenever possible, display accepted rate, completed rate, and queue depth together.

### Suggested Traffic panels

- Service-wide request rate over time.
- Request rate by critical route or operation.
- Traffic by version, region, or zone.
- Concurrent requests and active connections.
- Ingress/egress bytes or network throughput.
- Queue arrival rate versus processing/completion rate.

### How to read

- Traffic rises alongside rising latency and errors: check saturation, autoscaling, dependency limits, and load capacity.
- Traffic stays flat while completed rate drops: workers may be slow, queues backed up, or dependencies failing.
- Traffic drops suddenly: check DNS, load balancers, ingress, client behavior, or the telemetry pipeline before assuming user demand vanished.
- Traffic spikes on one route or tenant: verify whether it is legitimate load, a product change, or anomalous activity.

## 4. Designing the Errors Dashboard

The error signal indicates work failing to achieve expected outcomes. Define errors in the context of the application rather than relying solely on HTTP status codes.

### Classifying errors

- **Server error:** failure inside the application or server-side service, e.g., HTTP 5xx.
- **Client error:** invalid request or unauthorized user, usually HTTP 4xx. Some codes such as 429 may reflect rate limiting or intentional overload protection.
- **Timeout:** request or dependency fails to respond within the allotted deadline.
- **Dependency failure:** database, cache, queue, or external API returns an error or is unreachable.
- **Business failure:** transaction rejected by business rules; not always a technical failure.
- **Background job failure:** job fails, exceeds retries, or lands in a dead-letter queue.

Do not lump all HTTP 4xx responses into the server error rate. For instance, invalid user input legitimately generates 400s; however, a sudden spike in 429s may signal capacity limits or overly aggressive rate-limit policies firing.

### Calculating error rate

For an API, technical request error rate can be calculated as:

    Error rate (%) = (Failed requests in period / Total requests in period) × 100

For example, in 5 minutes there are 60,000 requests, of which 420 return server errors or timeouts:

    Error rate = (420 / 60,000) × 100 = 0.7%

If the SLO allows at most 0.1% technical errors in the evaluation window, 0.7% requires investigation. The denominator must be consistent: exclude health checks, synthetic probes, or internal traffic if they are outside SLO-covered user traffic, while never excluding genuine failed requests just to make the ratio look better.

### Suggested Errors panels

- Service-wide and per-route error rate (%).
- Error counts grouped by 4xx, 5xx, timeouts, and dependencies.
- Top operations or dependencies generating the most errors.
- Retry rate, failed jobs, and dead-letter queue counts.
- Error rate by version to catch post-deployment regressions.
- Count of instances/Pods restarting, OOMKilled, or crash-looping.

Display both percentages and absolute counts. A 50% rate across 2 requests may be a single isolated error; 0.2% across millions of requests can impact thousands of users.

## 5. Designing the Latency Dashboard

Latency is the time from when a unit of work starts until it finishes within a defined measurement boundary. Standardize start and end boundaries so versions and components can be compared fairly.

### Do not look only at averages

Suppose 99 requests take 100 ms and one request takes 10 seconds. The average is 199 ms, whereas p99 exposes the severe slow tail clearly. For interactive systems, users feel those slow requests even when the average stays low.

Common percentiles:

- **p50:** median; half of requests are faster than or equal to this value.
- **p90:** 90% of requests complete within this duration or faster.
- **p95:** represents the slowest 5% of requests and above.
- **p99:** tracks tail latency, where a small fraction of requests can be severely slow.
- **Maximum:** highest observed value; useful for investigation but sensitive to outliers and measurement noise.

Display p50 alongside p95/p99. p50 reflects typical experience; p95/p99 expose the distribution tail. Never sum or average per-instance percentiles to derive a service-wide percentile; compute them from properly aggregated histograms/buckets or distribution data.

### Breaking down latency components

Total response time can include:

- DNS lookup and TCP/TLS connection setup.
- Wait time at load balancers, ingress, or queues.
- Processing time inside the application.
- Waiting on CPU, locks, thread pools, or connection pools.
- Time spent calling databases, caches, queues, and external APIs.
- Data transfer and serialization/deserialization time.

Distributed tracing breaks duration down by span. Latency dashboards tell you there is a problem; traces show which segment consumes the time.

### Suggested Latency panels

- p50, p95, and p99 response time over time.
- Latency by route, operation, and version.
- Latency by dependency: database queries, caches, queues, external APIs.
- Separate queue wait time and processing time.
- Latency distribution heatmap if the metric system supports histograms.
- Count of requests breaching the SLO threshold.

Specify units clearly (ms or s), maintain consistent measurement boundaries, and never mix client-side latency with server-side latency in the same series without labeling it.

## 6. Designing the Saturation Dashboard

Saturation reflects how close a workload is to resource or serving capacity limits. CPU utilization is only part of the picture; a service can saturate RAM, disk, network, connection pools, or queues while CPU remains low.

### CPU

Monitor:

- CPU utilization per instance, node, and fleet.
- CPU usage per critical container or process.
- CPU throttling for containers with CPU limits.
- Load average, run queue, or CPU pressure.
- CPU credit/burst balance if the instance type uses bursting.

Sustained high CPU paired with rising latency and growing queues typically points to insufficient capacity or inefficient processing. High CPU with healthy latency and rising throughput may indicate efficient resource usage. Interpret in the context of workload and SLOs.

### Memory

Monitor:

- Working set/used memory and available memory.
- Memory utilization relative to limits or VM capacity.
- Swap-in/out, page faults, or memory pressure.
- OOM kills, container restarts, and steady upward memory trends.
- Heap, garbage collection, and native memory for JVM or similar runtimes.

Do not look solely at free memory. Linux uses RAM for page cache; inspect available memory and working set. For containers, memory limits can trigger OOM kills even when the underlying node still has free RAM.

### Storage and I/O

- Used capacity and filesystem growth rate.
- IOPS, throughput, and read/write latency.
- I/O queue depth or I/O wait time.
- Disk pressure, inode usage, and filesystem errors.
- Volume or storage service IOPS/throughput limits.

Low CPU paired with high latency can mean processes are waiting on disk I/O. Nearly full disk capacity can also break applications when writing logs, creating temp files, or updating data.

### Network

- Inbound/outbound throughput relative to NIC or instance limits.
- Packet drops, retransmissions, and interface errors.
- Connection count, connection tracking, or socket exhaustion.
- Network latency to dependencies and cross-zone/region traffic.
- Limits on NAT gateways, load balancers, or network services if applicable.

### Queues and service limits

- Queue depth and age of the oldest message.
- Active workers relative to maximum worker capacity.
- Connection pool usage, pending acquisitions, and timeouts.
- Thread pool queues, request concurrency, and rate limits.
- API quotas, database connection limits, and external service limits.

### Suggested Saturation panels

- CPU and memory per instance/node, with limits/quotas overlaid.
- CPU throttling and OOM/restarts.
- Disk I/O latency, IOPS, throughput, and capacity.
- Network throughput, drops, and retransmissions.
- Queue depth, oldest message age, and worker concurrency.
- Database connection pools, active connections, and query wait time.
- Autoscaling desired/current/min/max capacity.

## 7. Combining the Four Signals for Diagnosis

No single metric explains every incident. Compare all four signals within the same time window.

| Traffic | Errors | Latency | Saturation | Hypothesis to verify |
|---|---|---|---|---|
| Rising | Rising | Rising | High CPU | CPU-bound, insufficient instances, or slow autoscaling reaction |
| Steady | Rising | Rising | Low CPU, high disk I/O | Slow database or storage, locks, or I/O-bound |
| Steady | Rising | Rising | Network drops/retransmissions | Network issue, connection limit, or link congestion |
| Steady | Low | Rising | Growing queue depth | Workers cannot keep up with arrival rate or concurrency is capped |
| Dropping | Rising | Rising | Normal resources | Dependency failure, deployment regression, DNS/ingress, or client retries |
| Rising | Low | Steady | Resources have headroom | Normal growth; keep monitoring capacity and cost |
| Steady | Low | Steady | One instance saturated | Hot spot, uneven load distribution, or mismatched instance config |

These are initial hypotheses, not conclusions. Verify using logs, traces, deployment events, and dependency metrics.

## 8. Practical Dashboard Layout

An overview dashboard for a compute service can follow these rows:

| Row | Panels | Purpose |
|---|---|---|
| Row 1 | SLO status, request rate, error rate, p95/p99 latency, saturation summary | Quickly spot user impact |
| Row 2 | Traffic by route/zone/version; completed rate and queue arrival | Pinpoint where load is growing or stalling |
| Row 3 | Error rate by code/dependency/version; failed jobs | Isolate error types and involved components |
| Row 4 | Latency percentiles and heatmap; dependency latency | Identify tail latency and slow segments |
| Row 5 | CPU, RAM, throttling, OOMs, disk I/O, network | Locate resource constraints |
| Row 6 | Instance count, autoscaling, queue depth, database pool | Check capacity and scaling headroom |
| Row 7 | Deployments, maintenance events, incidents, and annotations | Correlate changes over time |

### Presentation rules

- Name panels after operational questions, not solely internal metric names.
- Specify units, scope, data source, and aggregation method.
- Use identical time ranges and timezones across related panels.
- Annotate deployments, maintenance, and incidents on timelines.
- Use consistent colors for normal, warning, and critical states; never rely on color alone to convey status.
- Render data gaps differently from zero values. Missing metrics do not mean zero requests or zero errors.
- Provide links to logs, traces, runbooks, and detailed dashboards.
- Avoid overcrowding with too many panels; prioritize information that drives decisions.

## 9. Label and Aggregation Design

Metrics typically carry labels for grouping, such as `service`, `environment`, `region`, `zone`, `instance`, `route`, `method`, `status_class`, and `version`.

### Recommended labels

- **service:** stable service name.
- **environment:** `production`, `staging`, `development`.
- **region/zone:** deployment location.
- **instance/pod:** for drill-downs, not necessarily shown individually on overview pages.
- **route or operation:** use stable route templates such as `/orders/{id}`.
- **status_class:** grouped `2xx`, `4xx`, `5xx`, or error category.
- **version:** application version for before/after deployment comparisons.

### Avoiding high cardinality

Never put values that change on nearly every request into metric labels, such as:

- User ID, email, session ID, or request ID.
- Raw URLs containing resource IDs or arbitrary query strings.
- Exception text, messages, or payloads.
- Individual client source IPs when the value space is large without a clear operational need.

High cardinality inflates time series counts, memory consumption, ingestion cost, and query latency. Request-level investigative details belong in controlled logs or traces linked via trace IDs—do not turn them into metric labels.

### Proper aggregation

- Service-wide request rate: sum rates across instances.
- Error rate: total errors divided by total requests in the same scope and window, never a simple average of per-instance percentages.
- Latency percentiles: compute from aggregated histograms/buckets, never by averaging per-instance p95 values.
- Fleet CPU: inspect both weighted averages and per-instance values; a fleet-wide average can hide a single saturated node.
- Queue depth: total message count and oldest message age may need separate panels; total queue count does not reflect the delay of the oldest message.

## 10. Illustrative PromQL Query Examples

The following queries illustrate calculations with Prometheus-style metrics. Actual metric names depend on the framework, exporter, and instrumentation. Verify that your metrics carry the right semantics, units, and labels before using them in dashboards.

### Service-wide request rate

    sum by (service) (
      rate(http_server_requests_total[5m])
    )

`rate()` estimates the per-second counter increase over a 5-minute window. Sum instances by service to see the total request rate.

### 5xx error rate

    100 *
    sum by (service) (
      rate(http_server_requests_total{status=~"5.."}[5m])
    )
    /
    sum by (service) (
      rate(http_server_requests_total[5m])
    )

If metrics use different labels such as `code` or `status_class`, adjust the selector accordingly. Ensure the request counters in the numerator and denominator count identically.

### p95 latency from histogram

    histogram_quantile(
      0.95,
      sum by (le, service) (
        rate(http_request_duration_seconds_bucket[5m])
      )
    )

Histograms must have buckets tuned to the application's latency range. If buckets are too coarse or miss the SLO threshold, estimated percentiles will lack accuracy.

### CPU utilization per instance

    100 * (
      1 - avg by (instance) (
        rate(node_cpu_seconds_total{mode="idle"}[5m])
      )
    )

This query illustrates deriving non-idle CPU from Node Exporter. For containers or cloud VMs, metrics and calculations may differ; verify CPU quotas, throttling, and how the exporter reports per-core figures.

### Container CPU throttling ratio

    100 *
    sum by (namespace, pod, container) (
      rate(container_cpu_cfs_throttled_periods_total[5m])
    )
    /
    sum by (namespace, pod, container) (
      rate(container_cpu_cfs_periods_total[5m])
    )

This computes the throttled period ratio using common cAdvisor metrics. Do not confuse it with CPU utilization percentage; inspect it alongside CPU usage and latency.

### Memory working set vs. limit

    100 *
    container_memory_working_set_bytes
    /
    container_spec_memory_limit_bytes

In real environments, filter for application containers, exclude containers without valid limits, and guard against zero or missing limit values.

## 11. From Dashboards to SLO-Based Alerts

Dashboards help operators explore system state. Alerts must notify when a condition requires action. Do not create alerts for every panel or every brief threshold crossing.

### Setting thresholds from service objectives

For example, an API has the following SLOs:

- 99.9% of valid requests complete successfully over a 30-day window.
- p95 latency under 300 ms for the order creation route.
- Oldest queued message does not exceed 60 seconds.

Alerts should reflect error budget consumption, breach duration, and affected users. An 80% CPU threshold can serve as a capacity warning, yet it is not necessarily an incident if latency and errors remain within SLO.

### Error budgets and burn rate

With a 99.9% availability SLO, the error budget is 0.1% of requests in the evaluation window. Burn rate measures how fast the error budget is being consumed relative to the sustainable SLO pace.

If the current error rate is 1% against a 0.1% error budget, the proportional consumption rate is roughly 10 times the allowable pace. If sustained, the error budget drains rapidly. Multi-window alerts can combine a short window to catch severe outages quickly with a long window to filter brief noise.

### Useful alert categories

- **User impact:** error rate breaching SLO, sustained p95/p99 threshold breach, dropping request success.
- **Capacity:** sustained CPU pressure or throttling, memory near limit, OOMs, disk nearly full, network near limits.
- **Queue/dependency:** rising queue age, exhausted connection pools, rising dependency latency/errors.
- **Availability:** ready instances below minimum threshold, zone losing backends, autoscaling failing to launch instances.
- **Telemetry health:** failed metric scrapes, empty dashboards, interrupted log/trace pipelines.

Every alert needs an owner, severity, clear condition, dashboard link, and runbook. Actionable urgent alerts should page on-call; trend or capacity warnings can route to separate monitoring channels.

## 12. Correlating Metrics, Logs, and Traces

Metrics reveal trends and scope; logs record concrete events; traces show which components a request traversed and where time was spent.

    Request -> API -> Database
                 -> Queue -> Worker

    Metrics: rate / errors / latency / saturation
    Logs: events, exceptions, and trace_id
    Traces: spans and dependency timing

Investigative example: a dashboard shows p99 latency climbing on the order creation API. The operator filters traces by route and finds the database span consuming most of the time. Logs matching the `trace_id` show query timeouts; the saturation dashboard simultaneously shows the connection pool nearing exhaustion. Combining all three sources pinpoints database connections or queries instead of adding vCPUs to the VM.

### Correlation rules

- Carry trace IDs or request IDs in logs/traces, never as high-cardinality metric labels.
- Synchronize clocks across applications, VMs, containers, and dependencies.
- Use consistent service names, environments, versions, and regions across telemetry.
- Mask or strip tokens, passwords, personal data, and sensitive payloads.
- Configure retention and access controls based on data classification.

## 13. End-to-End Dashboard Creation Workflow

    Identify users and decisions to support
        -> Select SLIs/SLOs and service scope
        -> Instrument traffic, errors, and latency
        -> Collect saturation and dependency metrics
        -> Standardize labels, units, and aggregations
        -> Design overview and drill-down views
        -> Correlate logs, traces, and deployment events
        -> Test queries and missing-data behavior
        -> Configure alerts and runbooks
        -> Review and prune unhelpful panels

### Step 1: define operational questions

Write down the questions the dashboard must answer, such as: "Is the API failing for users?", "Did the new release raise p99?", "Are workers keeping up with messages?", or "Is a single zone saturating?".

### Step 2: select SLIs and SLOs

Pick indicators reflecting user experience or business outcomes. Define valid request scope, error counting rules, latency thresholds, and evaluation windows. Document which traffic classes are excluded from SLOs and why.

### Step 3: instrument the application

Count requests and outcomes, measure duration with histograms, and track concurrency, queues, and dependencies. Use standard metrics or appropriate OpenTelemetry instrumentation. Ensure counters do not reset unexpectedly and histograms have buckets covering key thresholds.

### Step 4: collect saturation metrics

Pull metrics from cloud monitoring, node/container exporters, databases, storage, load balancers, and networking. Verify metric units and semantics per service; never mix metrics with different semantics on the same panel.

### Step 5: standardize labels and aggregations

Standardize service names, environments, versions, regions, and route templates. Avoid labels with unique IDs. Define service-level aggregate panels and instance/zone drill-down panels.

### Step 6: design overview and drill-downs

Place the Four Golden Signals at the top. Underneath, place breakdowns by route, version, zone, dependency, and resources. Add annotations for deployments, maintenance, and incidents.

### Step 7: verify data

Generate controlled load, inject test errors, and inspect percentiles. Confirm dashboards distinguish zero from no data, avoid double-counting retried requests, and automatically include new instances during autoscaling.

### Step 8: alert and iterate

Create alerts tied to SLOs, capacity, and telemetry health. Attach runbooks, owners, and clear actions. After incidents, review which panels helped, which added noise, and add any missing metrics.

## 14. Example Dashboard for an Order Processing API

An API runs across multiple VMs or Pods behind a load balancer, writes orders to a database, and publishes events to a queue. An overview dashboard could show:

| Group | Panels | Example goal |
|---|---|---|
| Traffic | Request rate, completed orders/s, active requests | Spot load spikes and gaps between accepted and completed work |
| Errors | 5xx rate, timeouts, payment dependency failures | Track technical errors and critical dependencies |
| Latency | p50/p95/p99 of `POST /orders` | Compare against SLO and spot tail latency |
| Saturation | CPU, memory, throttling, disk I/O, DB pool, queue age | Spot resources or dependencies approaching limits |
| Availability | Ready instances by zone, healthy backends | Verify sufficient capacity during maintenance or instance loss |
| Change context | Deployment version, maintenance annotations | Correlate incidents with recent changes |

Suppose over 10 minutes:

- Request rate rises from 300 to 650 RPS.
- 5xx error rate climbs from 0.05% to 1.2%.
- p95 latency rises from 180 ms to 900 ms.
- p95 CPU across API VMs hits 92%, and CPU throttling rises on a group of containers.
- Queue age climbs from 5 seconds to 75 seconds.

Together, the signals show the system is carrying load beyond its current processing capacity. The on-call team can inspect autoscaling, CPU limits, worker throughput, and database capacity. Looking only at error rate obscures the cause; looking only at fleet-average CPU could hide the throttled container group.

Another scenario: traffic stays flat, error rate stays low, yet p99 surges sharply; CPU remains low while database query latency and connection pool waits climb. In that case, adding vCPUs to the API likely will not fix the problem. Investigate the database, query plans, locks, and connection pools instead.

## 15. Common Mistakes

**Showing only CPU and RAM.** Dashboards missing traffic, errors, and latency fail to show user impact. Add the Four Golden Signals at the service level.

**Looking only at averages.** Averages conceal tail latency, hot instances, and brief error bursts. Use percentiles, breakdowns, and time-series charts.

**Averaging per-instance error rates or percentiles.** This aggregation is wrong whenever traffic is uneven across instances. Compute from raw counters/histograms using proper aggregation.

**Counting all 4xx as server errors.** Some 4xx codes represent valid client behavior or business rules. Classify errors by semantics and SLO.

**Using request ID or user ID labels.** Cardinality spikes dramatically and can leak data. Put granular identifiers into controlled logs/traces.

**Treating no data as zero.** A broken metric pipeline leaves dashboards empty while looking healthy. Monitor telemetry health separately.

**Alerting on every threshold crossing.** Noisy alerts cause on-call fatigue and missed pages. Alert on SLO impact, sustained duration, and clear actionability.

**Skipping deployment and maintenance markers.** Makes it difficult to tie changes to when latency or errors began climbing. Add annotations or event overlays.

**Crowding too many charts onto the front page.** Makes spotting problems harder during incidents. Keep the overview concise and link to drill-downs as needed.

## 16. Four Golden Signals Dashboard Checklist

### Metrics and semantics

- [ ] Traffic includes request rate, completed rate, or throughput suited to the workload.
- [ ] Errors distinguish server errors, client errors, timeouts, dependencies, and business failures.
- [ ] Latency includes p50 and tail percentiles p95/p99 with clear units and measurement boundaries.
- [ ] Saturation covers CPU, memory, storage, network, and queue/connection limits as appropriate.
- [ ] Metrics clearly document units, sources, labels, and aggregation methods.
- [ ] Histogram buckets cover the latency/SLO thresholds being observed.

### Dashboards and investigation

- [ ] Overview displays all four signals at the service level.
- [ ] Drill-downs exist by route, version, instance, zone, and dependency.
- [ ] Panels include autoscaling, ready instance count, and queues where needed by the workload.
- [ ] Annotations mark deployments, maintenance, and incidents.
- [ ] Links connect metrics to logs, traces, and runbooks.
- [ ] No data is distinguished from zero; the telemetry pipeline has dedicated health alerts.

### Data quality and alerting

- [ ] High-cardinality labels such as user ID, request ID, or raw URLs are excluded.
- [ ] Error rates and percentiles are properly aggregated from underlying raw data.
- [ ] SLOs, error budgets, and alert windows are defined.
- [ ] Alerts include owners, severities, conditions, and concrete actions.
- [ ] Dashboards are tested under realistic load, failure, and dependency scenarios.
- [ ] Access controls, retention, and sensitive data masking are configured.

## 17. Self-Check

1. What are the Four Golden Signals? Why must they be viewed together?
2. A service receives 1,000 RPS but completes only 700 RPS. Which additional metrics should you inspect to explain the gap?
3. Why are p95/p99 more useful than average latency alone for an interactive API?
4. Why should you not average per-instance p95 values to calculate service-wide p95?
5. Does a rising 4xx rate always indicate a server incident? How should it be classified?
6. What bottlenecks can low CPU paired with rising latency and queue age indicate?
7. How does high cardinality affect a metrics system? Which labels should be avoided?
8. How do you distinguish a metric value of 0 from a telemetry pipeline failing to send data?
9. How does an SLO/error-budget alert differ from a fixed CPU threshold alert?
10. When API p99 rises after a deployment, in what order would you use metrics, logs, and traces to investigate?

A well-designed dashboard turns operational data into actionable answers. When traffic, errors, latency, and saturation are consistently defined, properly aggregated, and linked to logs, traces, and SLOs, teams can detect user impact early, pinpoint the true bottleneck, and make evidence-based decisions on scaling, optimization, or recovery.
