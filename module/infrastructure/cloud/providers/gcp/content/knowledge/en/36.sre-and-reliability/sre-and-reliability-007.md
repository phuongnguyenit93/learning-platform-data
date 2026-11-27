# Capacity Planning and Quota Management for High Load

A system can run smoothly on normal days yet fail when a sales campaign, major release, or unexpected event causes traffic to surge. The root cause may be a shortage of CPU, memory, database connections, IP addresses, network bandwidth, or an API quota. Capacity planning forecasts the resources required for current and future load; quota management ensures the project is permitted to provision and consume enough resources when demand spikes.

Within the scope of **CLOUD_PROVIDERS_GCP**, this lesson connects capacity planning to operating projects, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases. The goal is to forecast load on a sound footing, maintain adequate headroom, understand each service's limits, monitor quotas before exhaustion, and prepare plans for scaling or controlled degradation.

After this lesson, you will be able to:

- Measure load demand using throughput, concurrency, latency, data size, and growth patterns.
- Estimate CPU, memory, network, storage, and connection capacity.
- Determine headroom for autoscaling, zonal failures, and burst traffic.
- Distinguish between quotas, system limits, service configuration limits, and physical capacity.
- Track quotas by service, project, and region; configure alerts and submit quota increase requests.
- Plan high-load capacity for Cloud Run, GKE, Compute Engine, and Cloud SQL.
- Validate plans using load tests, SLOs, error budgets, and controlled degradation scenarios.

## 1. What Is Capacity Planning?

Capacity planning is the process of determining how many resources a system needs to serve projected load at its committed performance and reliability levels. A plan must answer three questions:

1. What does the shape of current and future load look like?
2. Which resource will become the bottleneck first before reaching target load?
3. How much capacity must be prepared, provisioned, or reserved to preserve SLOs during load growth or component failures?

Capacity is more than VM counts. An API might have spare CPU yet exhaust its Cloud SQL connection pool; GKE might have spare CPU quota yet run out of subnet IPs; Cloud Run might scale up instances while a downstream dependency cannot handle the concurrent connections. System capacity is bounded by the narrowest component along the request path.

### 1.1. Core Load Metrics

| Metric | Meaning | Operational Question |
|---|---|---|
| Throughput | Requests or messages processed per unit of time | How many requests/second must the system handle? |
| Concurrency | Operations being processed simultaneously | How many request slots or connections are needed? |
| Latency | Time to complete an operation | Will p95/p99 still meet the SLO under higher load? |
| Error rate | Percentage of failed operations | Does high load trigger timeouts or quota errors? |
| Utilization | Resource usage relative to available capacity | Are CPU, memory, disk, or network nearing saturation? |
| Queue depth/age | Pending work count and oldest waiting time | Are consumers keeping up with producer speed? |
| Growth rate | Pace of demand growth over time | When will additional resources or quotas be required? |

Do not use CPU utilization as the sole proxy for capacity. A system can bottleneck on database locks, thread pools, file descriptors, connection pools, API quotas, or instance limits even while CPU stays low.

### 1.2. Distinguishing Average, Peak, and Burst Load

- **Average load** is useful for cost estimation and baseline utilization.
- **Peak load** is the highest load within a defined time window, such as a 5-minute or 1-hour peak.
- **Burst load** is a rapid surge over a short span. Autoscalers take time to spin up instances or nodes and cannot always respond instantaneously.
- **Seasonal load** is cyclical variation by hour, day, season, or campaign.
- **Failure load** is the residual load when a zone, node pool, or dependency fails and traffic shifts elsewhere.

Measure across multiple time windows. A 10-second spike gets smoothed away in a 1-hour average; conversely, sustained elevated load can fill connection pools or memory even without hitting an extreme peak throughput.

## 2. Gathering Data Before Forecasting

A trustworthy capacity plan begins with real data. Collect at least one representative operational cycle covering weekdays, weekends, peak hours, and campaigns if applicable.

### 2.1. Data to Collect

- Request rate by endpoint, tenant, or transaction type.
- p50, p95, and p99 latency; error rate; timeout and retry counts.
- CPU, memory, instance/pod/node counts, scale-up duration, and restart counts.
- Database connections, query latency, locks, IOPS, and storage growth.
- Network throughput, egress, connection counts, and payload sizes.
- Queue depth, oldest message age, producer rate, and consumer rate.
- Quota usage/limits by service, project, region, and dimension.
- Known release schedules, batch jobs, campaigns, imports/exports, and planned traffic increases.

Distinguish service-level metrics from infrastructure-level metrics. Node CPU may be low while a pod is CPU-throttled; spare aggregate cluster memory does not mean a pod can be scheduled if no single node has enough contiguous resources.

### 2.2. Defining the Workload Model

Group traffic by distinct behavioral profiles:

| Workload | Characteristics | Planning Approach |
|---|---|---|
| Interactive API | Latency-sensitive, bursty | Measure RPS, concurrency, p95/p99, and scale-up time |
| Background worker | Can be queued and processed asynchronously | Measure per-worker throughput, queue age, and drain time |
| Batch job | Heavy load within a defined window | Estimate completion time, CPU, memory, and I/O |
| Data ingestion | Load driven by producer pace | Measure bytes/second, message rate, buffering, and retention |
| Database | Shared across multiple apps | Measure connections, query mix, CPU, memory, IOPS, and locks |

Do not lump all workloads into one aggregate figure if they consume different resources or have different SLOs. A batch job can be allowed to run slower to preserve capacity for an interactive API.

## 3. Estimating Capacity with Simple Models

Initial models surface shortfalls before load testing begins. The formulas below are approximations and must be calibrated with load tests and real telemetry.

### 3.1. Estimating Concurrency with Little's Law

Little's Law:

\[
L = \lambda \times W
\]

Where:

- \(L\): average number of operations inside the system.
- \(\lambda\): average throughput, such as requests/second.
- \(W\): average time an operation spends in the system, in seconds.

For example, an API receives 250 requests/second with an average response time of 0.8 seconds:

\[
L = 250 \times 0.8 = 200
\]

On average, roughly 200 requests are actively processing or waiting in the system. If latency doubles to 1.6 seconds at the same throughput, average concurrency rises to roughly 400. That can raise required threads, connections, and memory.

Little's Law uses averages in a steady-state system. During bursts, rapidly growing queues, or stalled requests, measure concurrency and queue age directly instead of relying solely on the formula.

### 3.2. Estimating CPU

If you know the average CPU time consumed per request, you can estimate vCPUs:

\[
\text{vCPUs needed} \approx
\frac{\text{RPS} \times \text{CPU seconds/request}}
{\text{Target utilization}}
\]

Example:

- Peak throughput: 500 requests/second.
- Average CPU time: 0.04 core-seconds/request.
- Target utilization at peak load: 65%.

\[
\frac{500 \times 0.04}{0.65} \approx 30.8\ \text{vCPU}
\]

The initial plan calls for roughly 31 vCPUs for this workload before adding headroom for failures, growth, or concurrent jobs. CPU time/request must be measured via profiling or load testing; never treat total latency as CPU time because latency also includes network and wait times.

### 3.3. Estimating Memory

Memory depends on process baseline, concurrent requests, payload sizes, caches, buffers, and how the runtime manages its heap.

A simple model:

\[
\text{Memory} \approx
\text{Baseline} +
(\text{Concurrency} \times \text{Memory/request})
\]

For example, a process uses 450 MiB at baseline; each active request holds an average of 1.5 MiB; there are 300 concurrent requests:

\[
450 + (300 \times 1.5) = 900\ \text{MiB}
\]

This is a starting estimate. Actual memory can grow non-linearly due to caches, garbage collection, buffers, and long-lived allocations. Measure working set and peak memory in soak tests to determine safe limits.

### 3.4. Estimating Network and Storage

If each request transfers 40 KB on average and the system processes 500 requests/second, one-way payload volume is roughly:

\[
500 \times 40\ \text{KB} = 20\ \text{MB/s}
\]

This equals roughly 160 Mbit/s before accounting for protocol overhead, responses, TLS, retries, replication, and background traffic. For bidirectional traffic, calculate ingress and egress separately.

Storage should account for daily new data volume, retention, indexes, replicas, backups, temporary files, and growth rate. Do not plan only from current disk usage; forecast when disk thresholds will be hit and how long expansion takes.

## 4. Headroom, Redundancy, and Fault Tolerance

**Headroom** is the spare capacity left after serving projected load. Headroom absorbs bursts, workload variance, and autoscaler spin-up time.

No single headroom percentage fits every system. Choose it based on:

- Traffic volatility.
- Startup times for instances, pods, nodes, or databases.
- SLO criticality.
- Ability to shed load or queue work.
- Lead time to request quotas or purchase/reserve capacity.
- Scenarios where a zone or dependency is lost.

### 4.1. Provisioning for Failure Scenarios

A production plan should simulate these scenarios:

1. Normal weekday peak traffic.
2. Traffic doubling within a few minutes.
3. One zone becoming unavailable with traffic shifting to remaining zones.
4. A node pool or instance group losing serving capacity.
5. A slow database dependency holding requests open longer and increasing concurrency.
6. A consumer stopping and causing queue backlogs to grow.

If the system must stay operational during a zonal outage, remaining capacity across the other zones must suffice for target load. Setting a high autoscaling maximum alone does not guarantee capacity is immediately available in every zone.

### 4.2. Capacity Reservations and Quotas Are Two Different Things

A quota specifies how much of a resource a project is permitted to request or use along a given dimension. Physical capacity is the actual hardware available in the infrastructure at a specific time and location.

With Compute Engine, having CPU or GPU quota does not guarantee matching machines are available in a given zone. When VM capacity must be guaranteed by location and machine shape, evaluate Compute Engine reservations or appropriate capacity options. Reservations do not replace quotas; you still need sufficient quota to consume reserved resources.

For other managed services, capacity is governed by each product's mechanisms. Check quotas, configuration limits, and real serving capacity; never assume raising a quota automatically creates physical capacity.

## 5. Autoscaling and Limits Across GCP Services

Autoscaling adjusts resource counts based on load signals. It reduces manual operational work, but it does not replace capacity planning. You must configure scale-up thresholds, maximum bounds, scaling speed, dependency capacity, and platform quotas.

### 5.1. Cloud Run

- Use concurrency to control how many requests a single instance handles simultaneously.
- Set maximum instances to protect dependencies and control costs.
- Consider minimum instances when reducing cold starts or serving steady baseline traffic.
- Track CPU/memory, request latency, instance count, startup latency, and 429/5xx errors.
- Calculate required instances from throughput, target concurrency, and per-instance performance under load.
- Check regional Cloud Run quotas and related project-level limits.

Example: if one instance handles 40 concurrent requests steadily and peak load requires 800 concurrent requests, the initial model needs 20 instances. Add headroom for variance, scale-up lag, and unhealthy instances, while verifying downstream dependencies can handle 800 concurrent connections.

Maximum instances can be set at the service/revision level while platform quotas also apply. Updating service configuration does not raise project quotas automatically.

### 5.2. Google Kubernetes Engine

- Use Horizontal Pod Autoscaler (HPA) to scale replicas based on CPU, memory, or suitable custom/external metrics.
- Use Vertical Pod Autoscaler (VPA) to observe or recommend/update container requests and limits per deployment policy.
- Use Cluster Autoscaler to add or remove nodes when pods cannot be scheduled due to resource shortages.
- Set resource requests close to actual need; overly high requests waste capacity and block scheduling, while overly low requests overcommit nodes.
- Check Compute Engine quotas for CPU, GPU, disk, IPs, and node pool resources per region/zone.
- Verify Pod IP ranges, secondary ranges, and subnet capacity before scaling nodes or pods.
- Reserve capacity for system pods, DaemonSets, rolling updates, and critical workloads.

HPA can add pods faster than Cluster Autoscaler can provision new nodes. While waiting for nodes, pods stay Pending and requests can slow down or fail. Test end-to-end scaling latency from pod creation to node readiness.

### 5.3. Compute Engine and Managed Instance Groups

- Use Managed Instance Group autoscalers driven by CPU, load balancing serving capacity, or appropriate custom metrics.
- Set minimum/maximum replicas according to load, quotas, and application limits.
- Choose machine types based on CPU, memory, network, and disk profiling.
- Evaluate regional MIGs when distributing across multiple zones.
- Check quotas for CPU, GPU, persistent disks, external IPs, and dependent resources.
- Consider reservations when capacity guarantees are required for critical workloads.
- Measure boot time, startup scripts, image pulls, health checks, and warm-up time.

A MIG with a high maximum replica count but insufficient CPU quota cannot scale to target. Conversely, sufficient quota in a capacity-constrained zone can still fail to provision VMs.

### 5.4. Cloud SQL and Databases

Databases are often the hardest dependency to scale horizontally. Planning must examine:

- CPU, memory, storage, IOPS, and throughput.
- Concurrent connections and per-service connection pools.
- Query latency, locks, transaction durations, and replication lag.
- Read replica capacity, HA/failover behavior, and failover duration.
- Backups, point-in-time recovery, and storage headroom needed for restores.
- Connection limits or product limits by machine tier and database configuration.

Never scale up application instances without sizing connection pools. For instance, 30 instances each configured with a max pool of 80 connections can open 2,400 database connections at full pool utilization. Database limits may be hit long before application CPU saturates.

Use connection pooling, per-service connection caps, timeouts, and backpressure. When the database is the bottleneck, optimize queries, add caching, introduce read replicas, or tune database sizing before simply adding more app replicas.

## 6. Quotas and System Limits in Google Cloud

A quota limits how much of a resource or API Google Cloud allows a scope to consume—typically per project, service, region, or specific dimension. Quotas help control usage, protect shared infrastructure, and curb runaway resource creation from misconfigurations or buggy automation.

### 6.1. Common Quota Categories

| Category | Example | Typical Unit / Scope |
|---|---|---|
| Allocation quota | Allocated vCPUs, GPUs, persistent disks, or IPs | Resource count, typically per region or project |
| Rate quota | API requests over a time interval | Requests/second, requests/minute, or another time unit |
| Concurrent quota | Active operations or requests in flight | Concurrent operations |
| Service-specific quota | Limits specific to Cloud Run, GKE, BigQuery, or other services | Depends on service and dimension |

Category names and accounting vary by product. Read the exact quota descriptions on the Quotas & System Limits page for the service you use.

### 6.2. Quotas, System Limits, and Service Configuration

| Concept | Meaning | How to Handle |
|---|---|---|
| Quota | Usage limit that can be adjusted in certain cases | Monitor usage, request increases, or redistribute load |
| System limit | Fixed limit or product limit that cannot be raised arbitrarily | Redesign workload or pick another service/configuration |
| Service configuration limit | Operator-configured bound, such as max instances or max replicas | Adjust configuration after checking dependencies and quotas |
| Physical capacity | Actual hardware available in a zone/region | Use reservations, choose another zone/machine type, or coordinate with provider |

A quota may be raisable while a product system limit remains fixed. A max instances setting may be raised while project quotas or dependency capacity fall short. When encountering resource-exhausted errors, identify the exact limit type before acting.

### 6.3. Project and Regional Quotas

Many quotas are tracked separately by project and region. A project may have spare quota in region A while exhausting quota in region B. Some API quotas are tracked per project or consumer; others carry dimensions by location, user, or method.

When inspecting quotas, record:

- Service name and quota metric.
- Specific limit name or dimension.
- Project/consumer subject to the quota.
- Region/location if the quota is scoped geographically.
- Current usage, limit, and reset schedule for periodic quotas.
- Unit and calculation basis.

Do not sum quotas across multiple projects as if they formed a shared pool. If an application spans multiple projects, check each project against its actual consumer and resource footprint.

## 7. Inspecting and Monitoring Quotas

### 7.1. Using Cloud Console

In Google Cloud Console:

1. Select the target project.
2. Open **Quotas & System Limits** under IAM & Admin, or the service's dedicated quota page.
3. Filter by service, quota name, metric, region, or status.
4. Inspect usage, limit, utilization percentage, and editability.
5. Open a specific quota to view dimensions and increase-request requirements.
6. Record quotas tied to the capacity plan along with their accountable owner.

The UI may vary by service and Console updates. Some quotas are managed on product-specific pages or require a Support request.

### 7.2. Tracking Quotas with Cloud Monitoring

Cloud Monitoring provides quota metrics for many services. Common metrics in the Service Runtime family include:

- **serviceruntime.googleapis.com/quota/allocation/usage**
- **serviceruntime.googleapis.com/quota/limit**
- **serviceruntime.googleapis.com/quota/rate/net_usage**
- **serviceruntime.googleapis.com/quota/rate/limit**

Available metrics and labels depend on the service and quota type. Inspect metric descriptors in your project rather than assuming every quota emits the exact same metrics.

When building dashboards, plot usage alongside limit for the exact same dimensions. A chart showing usage without limit makes remaining headroom hard to see. For regional quotas, split series by location so aggregation does not hide a region nearing exhaustion.

### 7.3. Alerting Before Quotas Run Out

Alert thresholds should reflect usage growth rate and the lead time needed to process a quota increase. For example:

| Alert Level | Suggested Action |
|---|---|
| Watch | Usage starts growing faster than baseline; investigate the cause |
| Early warning | Enough lead time remains to project exhaustion date/time; open a quota increase plan |
| Urgent warning | Headroom drops below operational buffer; prepare load shedding or traffic shifting |
| Exhausted | Resource creation/API calls are already being rejected; trigger incident playbook |

Do not apply one flat percentage threshold to every quota. For slow-growing quotas that take several days to approve, alert at a lower threshold. For per-minute rate quotas, evaluate against bursts and reset intervals.

You can estimate time to exhaustion:

\[
\text{Time to exhaustion} \approx
\frac{\text{Limit} - \text{Current usage}}
{\text{Net usage growth per unit time}}
\]

If usage fluctuates seasonally or in bursts, use cyclical forecasts and percentiles instead of linear extrapolation from a short interval.

## 8. Quota Increase Request Process

Never wait until production starts failing resource creation to request a quota increase. Prepare ahead based on forecasts, load tests, and release schedules.

Recommended workflow:

1. Identify the exact quota metric, limit name, service, project, and region needing an increase.
2. Confirm it is genuinely an adjustable quota rather than a system limit or physical capacity constraint.
3. Measure current usage, peak usage, and growth rate.
4. Calculate target demand including projected load, headroom, failover, and growth horizon.
5. Check related quotas; raising a single quota may not help if the workload also needs more IPs, disks, or CPUs simultaneously.
6. Submit the request via Quotas & System Limits or the service/Cloud Customer Care process.
7. Provide business justification, project, region, current limit, requested limit, expected load, and target date.
8. Track request status, verify the updated quota once approved, and update the capacity plan.

Quota increase requests can require review time and are not automatically approved. Some quotas cannot be raised or require additional conditions. Raising quotas can also increase potential spend; align with the budget owner.

### 8.1. Sample Request Justification

~~~text
Service: Compute Engine API
Project: production-project
Region: asia-southeast1
Quota: Regional CPUs
Current limit: 200
Requested limit: 320

Reason:
The service will add two production node pools and increase the
regional managed instance group capacity for a planned traffic event.
Load testing indicates a peak requirement of 220 vCPUs. The requested
limit includes failover headroom and the next planned growth period.
The workload, rollout window, monitoring plan and rollback procedure
have been reviewed by the service owner.
~~~

This is an illustrative template; replace quota names, figures, regions, and rationale with measured data. Avoid requesting excessively large limits without a usage model and cost plan.

## 9. Load Testing to Validate Capacity

Calculated models must be verified through load testing. Test environments should closely match production in machine types, runtime configuration, data, network paths, databases, autoscaling, and quotas.

### 9.1. Types of Load Tests

| Test Type | Purpose | What to Observe |
|---|---|---|
| Baseline | Measure performance at normal load | Latency, CPU, memory, and error rate |
| Load test | Validate projected target load | SLOs, throughput, autoscaling, and quotas |
| Stress test | Push load beyond design capacity to find breaking points | Saturation, queues, errors, and overload behavior |
| Spike test | Apply sudden traffic surges | Scale-up delay, cold starts, and burst quotas |
| Soak test | Sustain load over an extended duration | Memory leaks, connection leaks, queue growth |
| Failover test | Simulate loss of a zone, node, or dependency | Remaining capacity and ability to uphold SLOs |

### 9.2. Load Testing Workflow

1. Define targets: peak RPS, concurrency, latency percentiles, error rate, and test duration.
2. Prepare representative data and workload mixes; avoid hitting only one trivial endpoint.
3. Verify quotas, budgets, service limits, and notify relevant teams.
4. Ramp load in steps, holding long enough for autoscalers to stabilize.
5. Record CPU, memory, connections, queues, network, storage, quota usage, and instance/node counts.
6. Ramp up to target load, then test bursts or stress within safe bounds.
7. Analyze bottlenecks and refine the capacity model.
8. Repeat after significant configuration changes.

Never run stress tests against production without operational approval and dependency-protection plans. A load test can exhaust shared quotas, inflate costs, or impact other tenants in the same project.

### 9.3. Pass Criteria

A load test passes when:

- Target throughput is sustained for the test duration.
- p95/p99 latency and error rates stay within SLOs.
- No unexpected quota exhaustion occurs.
- CPU, memory, connections, and queues retain planned headroom.
- Autoscalers scale out and scale in within acceptable timeframes.
- Databases and dependencies do not become bottlenecks.
- The system recovers after load drops; queue backlogs drain and resources scale in safely.

## 10. Protecting the System When Limits Are Reached

A capacity plan must define how the system responds when it can no longer scale out. The goal is to keep critical functions running and prevent cascading failures.

### 10.1. Backpressure and Queuing

- Cap concurrent requests to protect dependencies.
- Use queues for work that can be processed asynchronously.
- Set limits on backlog depth and oldest message age; alert before queues grow out of control.
- Tune consumer counts to real throughput and downstream quotas.
- Return retryable errors with backoff and jitter hints; avoid retry storms.
- Reject excess requests early rather than holding connections open indefinitely.

### 10.2. Graceful Degradation

When capacity becomes scarce:

- Prioritize core business flows and critical tenants/service tiers.
- Disable or defer secondary features such as heavy reports, recommendations, or non-urgent background tasks.
- Serve cached read data where appropriate and guard against cache stampedes.
- Restrict batch jobs and non-critical traffic during peak windows.
- Use circuit breakers to stop failing dependencies from taking down the entire service.
- Communicate retryable error statuses and supply `Retry-After` where appropriate.

### 10.3. Controlling Retries and Timeouts

Retries add load when a dependency is already degraded. Set timeouts within request latency budgets, cap retry attempts, and use exponential backoff with jitter. Retry only safe operations or those with idempotency keys. Never retry all 4xx or quota errors in tight loops.

## 11. Project-Level Quota and Capacity Governance

Quotas can be consumed by multiple teams and workloads sharing a project. Without governance, a test environment or batch job can starve production of quota.

Controls to apply:

- Separate production, staging, and development projects along clear governance boundaries.
- Assign owners to each critical quota and document consuming workloads.
- Apply labels and maintain inventories to trace resources, environments, and costs.
- Periodically review unused quotas, long-lived resources, and max autoscaling settings.
- Maintain a capacity calendar for campaigns, migrations, batch runs, and major releases.
- Enforce an approval workflow for bursty workloads or large-scale resource creation.
- Check cross-region quotas when using active-active or failover topologies.
- Assess cost impact when raising quotas and expanding autoscaling limits.

Separating projects can isolate quotas for many services and workloads, though not every quota shares the exact same scope. Verify each quota's dimensions before finalizing project isolation boundaries.

## 12. Hands-On Example: Preparing an API for a High-Traffic Campaign

An e-commerce API currently serves 180 requests/second during peak hours. An upcoming campaign expects 450 requests/second for 30 minutes, with short bursts up to 600 requests/second.

Current load test figures:

- CPU time: 0.035 core-seconds/request.
- Average latency: 0.45 seconds.
- Target CPU utilization at high load: 65%.
- Target concurrency at 450 RPS: roughly 450 × 0.45 = 203 requests.

CPU estimate:

\[
\frac{450 \times 0.035}{0.65} \approx 24.2\ \text{vCPU}
\]

If losing a zone or node group could remove 25% of capacity, the plan must verify remaining capacity can still serve critical load. You may need nominal provisioned capacity higher than 24.2 vCPUs and confirm autoscalers/placement can deliver it in time.

Preparation steps:

1. Run a load test at 450 RPS over at least a representative window and a spike test up to 600 RPS.
2. Determine required Cloud Run instances or GKE pods/nodes from measured concurrency and throughput.
3. Check Cloud Run/GKE/Compute Engine quotas by region and project.
4. Check Cloud SQL connections, CPU, storage, and query latency under matching load.
5. Set max instances/replicas with headroom without exceeding database capacity.
6. Set up quota alerts and dashboards tracking usage alongside limits.
7. Prepare caching, queues, rate limits, and feature toggles for secondary features.
8. Confirm budget approvals and on-call staffing during the campaign window.

If the database can sustain only 300 requests/second, scaling Cloud Run instances to serve 600 RPS can overload the database. In that case, reduce connection usage, add caching, optimize queries, or move work asynchronous before increasing frontend capacity.

## 13. Capacity and Quota Checklist

### Demand Forecasting

- [ ] Baseline, peak, burst, and seasonal load data are available.
- [ ] Throughput, concurrency, latency percentiles, and error rates are measured.
- [ ] Workload mix and critical dependencies are identified.
- [ ] Growth forecasts exist with concrete timelines.

### Resource Capacity

- [ ] CPU, memory, network, storage, and connection capacities are estimated.
- [ ] Headroom accounts for autoscaling lag and failure scenarios.
- [ ] Instance/node startup and warm-up times are factored in.
- [ ] Queues, backpressure, and backlog drain capacity are verified.
- [ ] Databases and downstream dependencies have matching capacity.

### Quotas

- [ ] Quotas are inventoried by service, project, region, and dimension.
- [ ] Quotas, system limits, service configurations, and physical capacity are distinguished.
- [ ] Usage and limits are monitored side by side.
- [ ] Alerts fire early enough for quota increase processing lead times.
- [ ] Related quotas are increased together rather than raising one metric in isolation.
- [ ] New quotas are verified and the capacity plan is updated after approval.

### Testing and Operations

- [ ] Appropriate baseline, load, spike, stress, soak, or failover tests have run.
- [ ] Load tests meet SLOs without unexpected quota exhaustion.
- [ ] Playbooks exist for graceful degradation and retry/backoff controls.
- [ ] Owners, on-call schedules, and rollback plans are ready for high-load events.
- [ ] Budgets and costs for autoscaling, egress, and storage have been reviewed.

## 14. Common Pitfalls

**Designing peak capacity from average load.** Averages hide bursts and peak hours. Use percentiles, windowed peaks, and a workload calendar.

**Assuming raising quotas guarantees capacity.** Quotas only permit resource usage up to a limit; physical capacity and service limits can still block scaling.

**Checking only CPU quotas.** Workloads may simultaneously need disk, GPU, IP, forwarding rule, API request, or connection quotas. List every dependency.

**Raising max instances without checking the database.** Rapid frontend scaling can open too many connections and collapse downstream dependencies.

**Setting autoscaling max too low.** The system hits max replicas even with spare quota. Conversely, setting max too high can spike costs and overwhelm dependencies.

**Ignoring scale-up time.** Autoscalers need time to provision instances/nodes and boot the app. Rapid bursts can arrive before new capacity is ready.

**Skipping failover tests.** Total aggregate capacity may look sufficient while remaining capacity after losing one zone falls short.

**Requesting quota increases too late.** Review workflows take time or require follow-up info. Use forecasts and time-to-exhaustion to submit requests early.

**Omitting retries from load calculations.** Retry storms push real request rates above user traffic. Enforce timeouts, backoff, jitter, and idempotency.

## 15. Official References

- [Google Cloud quotas overview](https://cloud.google.com/docs/quotas/overview)
- [View and manage quotas](https://cloud.google.com/docs/quotas/view-manage)
- [Request a quota adjustment](https://cloud.google.com/docs/quotas/help/request_increase)
- [Cloud Monitoring quota metrics](https://cloud.google.com/monitoring/quotas)
- [Compute Engine quotas](https://cloud.google.com/compute/quotas)
- [Compute Engine reservations](https://cloud.google.com/compute/docs/instances/reserving-zonal-resources)
- [Cloud Run autoscaling](https://cloud.google.com/run/docs/about-instance-autoscaling)
- [GKE cluster autoscaler](https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler)
- [Cloud SQL performance overview](https://cloud.google.com/sql/docs/postgres/monitor-instance)
- [Site Reliability Engineering: Managing Load](https://sre.google/sre-book/handling-overload/)

Capacity planning is an iterative practice, not a one-time calculation before launch day. After every high-load event, compare forecasts against actual usage, update models, review quotas, and tune autoscaling. With solid telemetry, headroom, quotas, and clear playbooks, teams can scale the right components, uphold SLOs, and avoid the costs or risks of over- or under-provisioning.
